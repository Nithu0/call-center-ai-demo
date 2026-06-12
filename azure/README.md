# Azure-deploy — portabilitets-beviset

Denne mappen beviser tesen: **samme kode, samme Docker-image, kjører lokalt
ELLER på Azure — kun env-variabler bytter providere.**

| | Lokalt | Azure |
|---|---|---|
| `DEPLOY_TARGET` | `local` (default) | `azure` |
| STT (tale→tekst) | mock / whisper (offline) | **Azure AI Speech** |
| LLM (analyse) | mock (deterministisk) | **Azure OpenAI** (gpt-4o) |
| Nøkler/nett | ingen | injiseres som Container App secrets |
| Image | `call-center-ai:latest` | **samme image** |

`app/config.py` leser `DEPLOY_TARGET` og velger backends automatisk. Ingen
`if cloud:`-greiner i forretningslogikken — bare provider-valg ved oppstart.

## Filer

- **`main.bicep`** — IaC: Container Apps Environment + Container App, Log
  Analytics, ACR, Azure AI Speech (Cognitive Services / SpeechServices) og
  Azure OpenAI med en gpt-4o-deployment. Setter `DEPLOY_TARGET=azure` +
  Azure-endepunkter/nøkler som env/secrets på appen.
- **`deploy.md`** — eksakte `az`-kommandoer, steg for steg, fra `az login`
  til verifisert `/healthz`. Følgbar for en Azure-nybegynner.
- **`../Dockerfile`** + **`../.dockerignore`** — bygger imaget begge steder.
- **`../.github/workflows/deploy.yml`** — CI: bygg image i ACR + deploy til
  Container Apps på push til `main`.

## Kjør lokalt (ingen Azure)

```bash
docker build -t call-center-ai:latest ..
docker run -e DEPLOY_TARGET=local -p 8000:8000 call-center-ai:latest
# -> http://localhost:8000  (mock-providere, alt grønt offline)
```

## Kjør på Azure

Følg [`deploy.md`](./deploy.md). Kort fortalt: `az group create` →
`az deployment group create` (main.bicep) → `az acr build` → `az containerapp
update` → `curl $APP_URL/healthz`.
