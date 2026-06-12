// =====================================================================
//  Call-senter AI-demo (Loyalty) — Azure-infrastruktur (IaC)
// =====================================================================
//  Provisjonerer ALT som trengs for å kjøre demoen på Azure med
//  DEPLOY_TARGET=azure (Azure AI Speech + Azure OpenAI):
//
//    - Log Analytics Workspace        (logger/metrics for Container Apps)
//    - Container Apps Environment      (vert for container-appen)
//    - Azure Container Registry (ACR)  (lagrer Docker-imaget)
//    - Azure AI Speech (Cognitive Services, kind=SpeechServices)
//    - Azure OpenAI (kind=OpenAI) + én modell-deployment (gpt-4o)
//    - Container App                   (selve demoen) med env/secrets
//
//  Kjøres med:  az deployment group create ... (se azure/deploy.md)
//  Region parametrisert (default swedencentral — EU/Azure OpenAI-støtte).
// =====================================================================

// ---------------------------------------------------------------------
//  Parametre
// ---------------------------------------------------------------------

@description('Region for alle ressurser. Bruk en region med Azure OpenAI + Speech (EU: swedencentral / norwayeast).')
@allowed([
  'swedencentral'
  'norwayeast'
  'westeurope'
  'northeurope'
])
param location string = 'swedencentral'

@description('Kort, unikt navne-prefiks for ressursene (kun små bokstaver/tall, 3-12 tegn).')
@minLength(3)
@maxLength(12)
param namePrefix string = 'loyaltycc'

@description('Container-image (repository:tag) i ACR-en, f.eks. call-center-ai:latest. Pushes før containerapp-deploy.')
param containerImage string = 'call-center-ai:latest'

@description('Navn på Azure OpenAI modell-deployment som appen bruker (AZURE_OPENAI_DEPLOYMENT).')
param openAiDeploymentName string = 'gpt-4o'

@description('Azure OpenAI modell-navn.')
param openAiModelName string = 'gpt-4o'

@description('Azure OpenAI modell-versjon. Verifiser tilgjengelighet i valgt region.')
param openAiModelVersion string = '2024-08-06'

@description('Talegjenkjennings-språk for Azure AI Speech (AZURE_SPEECH_LANGUAGE).')
param speechLanguage string = 'nb-NO'

// Deterministisk suffiks for globalt-unike navn (ACR + Cognitive Services
// trenger globalt unike navn). Avledet av resource group sin id.
var uniqueSuffix = toLower(substring(uniqueString(resourceGroup().id), 0, 6))

var logAnalyticsName = '${namePrefix}-logs'
var containerEnvName = '${namePrefix}-env'
var containerAppName = '${namePrefix}-app'
var acrName = '${namePrefix}acr${uniqueSuffix}'        // ACR: kun alfanumerisk, 5-50 tegn
var speechName = '${namePrefix}-speech-${uniqueSuffix}'
var openAiName = '${namePrefix}-openai-${uniqueSuffix}'

// ---------------------------------------------------------------------
//  Log Analytics (kreves av Container Apps Environment)
// ---------------------------------------------------------------------

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: logAnalyticsName
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

// ---------------------------------------------------------------------
//  Azure Container Registry (lagrer Docker-imaget)
// ---------------------------------------------------------------------

resource acr 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' = {
  name: acrName
  location: location
  sku: {
    name: 'Basic'
  }
  properties: {
    // adminUser brukes for enkel image-pull i demoen. I produksjon:
    // bruk managed identity + AcrPull-rolle i stedet for admin-credentials.
    adminUserEnabled: true
  }
}

// ---------------------------------------------------------------------
//  Azure AI Speech  (Cognitive Services, kind=SpeechServices) -> STT
// ---------------------------------------------------------------------

resource speech 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: speechName
  location: location
  kind: 'SpeechServices'
  sku: {
    name: 'S0'
  }
  properties: {
    // Tillat nøkkel-basert auth (appen bruker AZURE_SPEECH_KEY).
    publicNetworkAccess: 'Enabled'
    customSubDomainName: speechName
  }
}

// ---------------------------------------------------------------------
//  Azure OpenAI  (kind=OpenAI) + modell-deployment -> LLM
// ---------------------------------------------------------------------

resource openAi 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: openAiName
  location: location
  kind: 'OpenAI'
  sku: {
    name: 'S0'
  }
  properties: {
    // customSubDomainName kreves for at endpointet skal bli
    // https://<navn>.openai.azure.com (AZURE_OPENAI_ENDPOINT).
    customSubDomainName: openAiName
    publicNetworkAccess: 'Enabled'
  }
}

resource openAiDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: openAi
  name: openAiDeploymentName
  sku: {
    // GlobalStandard gir bredest regional tilgjengelighet for gpt-4o.
    name: 'GlobalStandard'
    capacity: 10
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: openAiModelName
      version: openAiModelVersion
    }
  }
}

// ---------------------------------------------------------------------
//  Container Apps Environment
// ---------------------------------------------------------------------

resource containerEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: containerEnvName
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
  }
}

// ---------------------------------------------------------------------
//  Container App (selve demoen)
// ---------------------------------------------------------------------

resource containerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: containerAppName
  location: location
  dependsOn: [
    openAiDeployment
  ]
  properties: {
    managedEnvironmentId: containerEnv.id
    configuration: {
      ingress: {
        external: true
        targetPort: 8000           // Dockerfile binder $PORT (default 8000)
        transport: 'auto'
        traffic: [
          {
            latestRevision: true
            weight: 100
          }
        ]
      }
      registries: [
        {
          server: acr.properties.loginServer
          username: acr.name
          // ACR admin-passord lagres som container-app secret.
          passwordSecretRef: 'acr-password'
        }
      ]
      secrets: [
        {
          name: 'acr-password'
          value: acr.listCredentials().passwords[0].value
        }
        {
          name: 'azure-speech-key'
          value: speech.listKeys().key1
        }
        {
          name: 'azure-openai-key'
          value: openAi.listKeys().key1
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'call-center-ai'
          image: '${acr.properties.loginServer}/${containerImage}'
          resources: {
            cpu: json('0.5')
            memory: '1.0Gi'
          }
          env: [
            // --- Portabilitets-bryteren ---
            {
              name: 'DEPLOY_TARGET'
              value: 'azure'        // => STT=azure, LLM=azure-openai (app/config.py)
            }
            // --- Azure AI Speech (STT) ---
            {
              name: 'AZURE_SPEECH_KEY'
              secretRef: 'azure-speech-key'
            }
            {
              name: 'AZURE_SPEECH_REGION'
              value: location
            }
            {
              name: 'AZURE_SPEECH_LANGUAGE'
              value: speechLanguage
            }
            // --- Azure OpenAI (LLM) ---
            {
              name: 'AZURE_OPENAI_ENDPOINT'
              value: openAi.properties.endpoint
            }
            {
              name: 'AZURE_OPENAI_KEY'
              secretRef: 'azure-openai-key'
            }
            {
              name: 'AZURE_OPENAI_DEPLOYMENT'
              value: openAiDeploymentName
            }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/healthz'
                port: 8000
              }
              initialDelaySeconds: 10
              periodSeconds: 30
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/healthz'
                port: 8000
              }
              initialDelaySeconds: 5
              periodSeconds: 15
            }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 3
      }
    }
  }
}

// ---------------------------------------------------------------------
//  Outputs — verdier deploy.md/CI bruker for å verifisere + sette image
// ---------------------------------------------------------------------

@description('Offentlig URL til den kjørende demoen.')
output appUrl string = 'https://${containerApp.properties.configuration.ingress.fqdn}'

@description('ACR login-server (brukes ved docker push og containerapp-oppdatering).')
output acrLoginServer string = acr.properties.loginServer

@description('ACR-navn (brukes av `az acr build` / `az acr login`).')
output acrName string = acr.name

@description('Azure OpenAI-endepunkt (AZURE_OPENAI_ENDPOINT).')
output azureOpenAiEndpoint string = openAi.properties.endpoint

@description('Navn på container-appen.')
output containerAppName string = containerApp.name
