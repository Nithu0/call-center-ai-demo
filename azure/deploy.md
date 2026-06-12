# Deploy til Azure — steg for steg

Denne guiden tar deg fra null til en kjørende `call-senter-AI-demo` på
**Azure Container Apps**, med **Azure AI Speech** + **Azure OpenAI**.
Skrevet for å kunne følges av en som er ny på Azure. Kopier kommandoene én og én.

> **Poenget:** Samme Docker-image kjører lokalt (`DEPLOY_TARGET=local`, mock)
> og på Azure (`DEPLOY_TARGET=azure`, ekte tjenester). Bicep setter
> `DEPLOY_TARGET=azure` automatisk på container-appen — ingen kodeendring.

---

## 0. Forutsetninger (engangs)

Installer Azure CLI:

- Windows: <https://aka.ms/installazurecliwindows>
- macOS: `brew install azure-cli`
- Linux: `curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash`

Installer Bicep-utvidelsen (brukes av `az deployment`):

```bash
az bicep install
az bicep version
```

Logg inn og velg abonnement:

```bash
az login
# Hvis du har flere abonnement, sett det riktige aktivt:
az account list --output table
az account set --subscription "<DITT-ABONNEMENT-NAVN-ELLER-ID>"
```

> **Azure OpenAI krever tilgang.** Hvis abonnementet ditt ikke har Azure
> OpenAI aktivert, søk om tilgang her: <https://aka.ms/oai/access>.
> Uten det vil OpenAI-ressursen i Bicep feile ved opprettelse.

---

## 1. Sett variabler (gjenbrukes i hele guiden)

```bash
# Velg en region med BÅDE Azure OpenAI og Speech (EU):
LOCATION=swedencentral          # alternativ: norwayeast / westeurope
RG=loyalty-callcenter-rg        # navn på resource group
PREFIX=loyaltycc                # 3-12 tegn, små bokstaver/tall
```

---

## 2. Opprett resource group

```bash
az group create --name "$RG" --location "$LOCATION"
```

---

## 3. Provisjoner infrastrukturen med Bicep

Dette oppretter Log Analytics, Container Apps Environment, ACR, Azure AI
Speech, Azure OpenAI + gpt-4o-deployment, og selve Container-appen.

> Første gang: appen peker på et image som ennå ikke er pushet. Vi deployer
> infra først, bygger+pusher imaget (steg 4), og oppdaterer appen (steg 5).

```bash
az deployment group create \
  --resource-group "$RG" \
  --template-file main.bicep \
  --parameters location="$LOCATION" namePrefix="$PREFIX"
```

Hent ut verdiene vi trenger videre (ACR-navn, app-navn, URL):

```bash
ACR_NAME=$(az deployment group show -g "$RG" -n main \
  --query properties.outputs.acrName.value -o tsv)
APP_NAME=$(az deployment group show -g "$RG" -n main \
  --query properties.outputs.containerAppName.value -o tsv)
APP_URL=$(az deployment group show -g "$RG" -n main \
  --query properties.outputs.appUrl.value -o tsv)

echo "ACR_NAME=$ACR_NAME"
echo "APP_NAME=$APP_NAME"
echo "APP_URL=$APP_URL"
```

> `-n main` er navnet på deploymenten (= filnavnet `main.bicep` uten endelse).

---

## 4. Bygg og push Docker-imaget til ACR

Enkleste vei: la Azure bygge imaget i skyen rett fra kildekoden (ingen lokal
Docker nødvendig). Kjør fra **repo-roten** (mappen med `Dockerfile`):

```bash
cd ..   # opp fra azure/ til repo-roten der Dockerfile ligger

az acr build \
  --registry "$ACR_NAME" \
  --image call-center-ai:latest \
  .
```

> Alternativ med lokal Docker:
> ```bash
> az acr login --name "$ACR_NAME"
> LOGIN_SERVER=$(az acr show -n "$ACR_NAME" --query loginServer -o tsv)
> docker build -t "$LOGIN_SERVER/call-center-ai:latest" .
> docker push "$LOGIN_SERVER/call-center-ai:latest"
> ```

---

## 5. Pek container-appen på det ferske imaget

Bicep-en satte image-referansen i steg 3, men registeret var tomt da. Nå som
imaget finnes, trigg en ny revisjon:

```bash
LOGIN_SERVER=$(az acr show -n "$ACR_NAME" --query loginServer -o tsv)

az containerapp update \
  --name "$APP_NAME" \
  --resource-group "$RG" \
  --image "$LOGIN_SERVER/call-center-ai:latest"
```

> Du trenger IKKE sette Azure-nøkler/endepunkter manuelt — Bicep injiserte
> dem allerede som container-app **secrets** + **env** (`DEPLOY_TARGET=azure`,
> `AZURE_SPEECH_KEY`, `AZURE_OPENAI_ENDPOINT`, ...). Se neste avsnitt hvis du
> vil endre dem.

---

## 6. (Valgfritt) Inspiser / endre env og secrets

List nåværende env-variabler på appen:

```bash
az containerapp show -g "$RG" -n "$APP_NAME" \
  --query "properties.template.containers[0].env" -o table
```

Sett/oppdater en enkelt env-variabel (eksempel: bytt språk):

```bash
az containerapp update -g "$RG" -n "$APP_NAME" \
  --set-env-vars AZURE_SPEECH_LANGUAGE=nb-NO
```

Legg til/roter en secret og referer den fra en env-variabel:

```bash
az containerapp secret set -g "$RG" -n "$APP_NAME" \
  --secrets azure-openai-key=<NY-NØKKEL>

az containerapp update -g "$RG" -n "$APP_NAME" \
  --set-env-vars AZURE_OPENAI_KEY=secretref:azure-openai-key
```

---

## 7. Verifiser at det kjører

```bash
echo "Åpne i nettleser: $APP_URL"

# Helsesjekk — skal vise status:ok + deploy_target:azure + azure-providere:
curl -s "$APP_URL/healthz"
```

Forventet JSON fra `/healthz`:

```json
{
  "status": "ok",
  "deploy_target": "azure",
  "stt_backend": "azure",
  "llm_backend": "azure-openai",
  "is_azure": true
}
```

Se logger om noe feiler:

```bash
az containerapp logs show -g "$RG" -n "$APP_NAME" --follow
```

---

## 8. Rydd opp (slett ALT)

Hele oppsettet ligger i én resource group. Slett den for å unngå kostnad:

```bash
az group delete --name "$RG" --yes --no-wait
```

---

## Feilsøking

| Symptom | Sannsynlig årsak / fiks |
|---|---|
| `az acr build` feiler med "image not found" på appen | Du kjørte steg 5 før steg 4. Bygg imaget først, så `containerapp update`. |
| OpenAI-ressurs feiler i deployment | Abonnementet mangler Azure OpenAI-tilgang → søk via <https://aka.ms/oai/access>. |
| gpt-4o-deployment feiler (kapasitet/region) | Velg annen `LOCATION`, eller juster `openAiModelVersion` til en versjon tilgjengelig i regionen. |
| `/healthz` viser `deploy_target: local` | `DEPLOY_TARGET` ble ikke satt — sjekk env i steg 6; Bicep skal sette den til `azure`. |
| Appen svarer ikke / 503 | Sjekk `az containerapp logs show`; vanlig årsak er at imaget mangler i ACR (steg 4). |
