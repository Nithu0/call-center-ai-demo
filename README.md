# Call-senter AI-demo (Loyalty)

Kjørbar demo av et call-senter-AI-system: transkriber norske kundesamtaler og
analyser dem automatisk (sammendrag, sentiment, QA-scorecard, nøkkelinfo,
compliance-flagg, foreslått oppfølging). Relevant for utkontraktert
kundedialog/salg med store norske samtalevolum.

## Portabilitets-tesen (kjernepoenget)

**Samme kode kjører LOKALT eller på AZURE — du bytter providere via
env-variabler, ikke kode.**

Systemet har et tydelig **pluggbart provider-lag**:

| Lag | Fil | Backends (env-styrt) |
|-----|-----|----------------------|
| Tale-til-tekst (STT) | `app/providers/stt.py` | `mock` (offline) · `faster-whisper` · `nb-whisper` · `azure` (Azure AI Speech) |
| Analyse (LLM) | `app/providers/llm.py` | `mock` (deterministisk, offline) · `anthropic` (claude-opus-4-8) · `azure-openai` (Azure OpenAI) |

Begge backends returnerer **samme pydantic-modeller** (`Transcript`,
`Analysis`), så web-UI-et er likegyldig til hvilken backend som kjørte.

### De TO env-variablene som flytter alt lokalt → Azure

```
DEPLOY_TARGET=azure
```

`DEPLOY_TARGET` er den ene bryteren. Når den settes til `azure` velger
`app/config.py` automatisk:

- `STT_BACKEND = azure`  → Azure AI Speech
- `LLM_BACKEND = azure-openai` → Azure OpenAI

Altså: **bytt `DEPLOY_TARGET` (én linje) → hele systemet peker på Azure**, helt
uten kodeendring. (Vil du mikse manuelt kan du sette `STT_BACKEND` og
`LLM_BACKEND` eksplisitt — de to variablene som faktisk bytter provider-lag.)

Default er `DEPLOY_TARGET=local`, som bruker mock-providere og kjører **helt
offline** — ingen nettverk eller nøkler kreves for å demonstrere alt.

---

## Kjøre lokalt (offline, ingen nøkler)

```bash
cd call-center-ai-demo
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # default DEPLOY_TARGET=local
```

Start serveren (venv må være aktivert) — én av:

```bash
source .venv/bin/activate && bash run.sh          # → http://127.0.0.1:8000
```

…eller uten å aktivere venv, på ÉN linje:

```bash
.venv/bin/python -m uvicorn app.main:app --port 8000
```

Åpne http://127.0.0.1:8000. Demoen har en full rute/feature-liste (se under) —
de viktigste sidene:

- **Forside** (`/`): liste over demo-samtaler + et banner som viser `DEPLOY_TARGET`,
  aktive providere, og teksten *"Samme kode — bytt 2 env-variabler → kjører på Azure"*.
- **Samtale-side** (`/call/<navn>`): transkript til venstre, AI-analyse til høyre
  (scorecard med farger, sammendrag, sentiment, nøkkelinfo, compliance-flagg,
  oppfølging) + en **"kjør analyse på nytt"**-knapp.
- **Live** (`/live`): live tale-til-tekst i nettleseren, analyser mens du snakker.
- **Dashboard** (`/dashboard`), **effekt/ROI** (`/eval`), **PII-maskering** (`/redaction`).

Demodata ligger i `data/` — salgs- og kundeservice-anrop (alarm/forsikring,
faktura-feil, oppsigelse, m.fl.). Ingen ekte PII.

## Ruter / funksjoner (komplett)

Full tabell rute → funksjon → Loyalty-use-case ligger i **[FEATURES.md](./FEATURES.md)**.
Gruppert oversikt:

**Kjerne**
- `GET /` — forside (samtale-liste + provider-banner)
- `GET /call/{navn}` — samtale + full AI-analyse
- `POST /call/{navn}/analyze` — kjør analysen på nytt (JSON)
- `GET /healthz` — helsesjekk + provider-info

**Ledelse / effekt**
- `GET /dashboard` — aggregert ledelses-dashboard (snitt-QA, sentiment, churn, flagg, årsaker)
- `GET /eval` — dokumentert effekt: nøyaktighet mot fasit + interaktiv ROI-kalkulator
- `GET /redaction` — PII-maskering før/etter (`?name=` / `?text=`, `?format=json`)

**Integrasjoner**
- `GET /integrations/crm/{navn}` — CRM-klar JSON-payload for én samtale (dry-run push)
- `POST /integrations/telephony/webhook` — contact-center-event → full pipeline (STT→LLM→CRM)

**Tale-til-tekst (STT)**
- `GET /live` — LIVE STT i nettleseren (Web Speech API, `nb-NO`) — **kun demo**, se personvern under
- `POST /analyze-text` — analyser vilkårlig samtaletekst (fritekst/innliming) → transkript + analyse
- `POST /transcribe` — den PRIVATE backend-STT-veien: lydfil → provider-laget (NB-Whisper / Azure Speech)
- `GET /stt` — STT-plattform-sammenligning: kriterie-matrise (NB-Whisper / Whisper large-v3 / Azure Speech / Google / Deepgram) + anbefaling

> STT-plattformvalg dekkes på to måter: `/stt` gir kriterie-matrisen med
> anbefaling, og du kan måle selv ved å bytte `STT_BACKEND`
> (`mock`/`faster-whisper`/`nb-whisper`/`azure`) og score backenden på `/eval`
> mot gull-fasit.

### Personvern: de to STT-veiene

- `/live` bruker **nettleserens Web Speech API** — i Chrome sendes lyden til
  Google. **Kun for demo.** Bruk aldri ekte sensitiv kundelyd her.
- **Produksjon bruker `POST /transcribe`**: lyden går server-side gjennom
  provider-laget — NB-Whisper lokalt (lyd forlater aldri huset) eller Azure AI
  Speech i EU-region.

### Tester

```bash
pytest -q
```

Dekker provider-pluggability (bytte backend), deterministisk mock-analyse,
QA-scorecard-logikk, og at FastAPI-endepunktene svarer 200.

---

## Kjøre med en ekte LLM (valgfritt, fortsatt "lokalt")

`DEPLOY_TARGET` forblir `local`, men du peker LLM-laget mot en ekte modell:

```bash
pip install anthropic
export LLM_BACKEND=anthropic
export ANTHROPIC_API_KEY=sk-ant-...
export ANTHROPIC_MODEL=claude-opus-4-8   # default
./run.sh
```

STT forblir `mock` (ferdige transkript) med mindre du også bytter `STT_BACKEND`.

---

## For Loyalty — hvilke use cases demoen dekker

Loyalty leverer utkontraktert kundedialog med store norske samtalevolum og har
en AI-roadmap med **13 use cases**. Demoen kjører i dag (offline, på demo-data)
funksjoner for disse:

| # | Use case | Hvor i demoen |
|---|----------|---------------|
| 1 | Tale-til-tekst (norsk) | `/live` (live, nettleser) + `POST /transcribe` (server-side NB-Whisper/Azure) + `/stt` (plattformvalg) + pluggbar STT (`STT_BACKEND`) |
| 2 | Auto-QA / samtalescoring | scorecard på `/call/{navn}` + `POST /analyze-text` |
| 3 | Sammendrag | `Analysis.summary` på samtale-siden |
| 4 | Sentiment | `Analysis.sentiment` |
| 5 | Churn-/oppsigelsesdeteksjon | `/dashboard` (churn-fordeling + høyrisiko-liste) |
| 6 | Agent-coaching | `Analysis.coaching_tips` |
| 7 | Compliance-overvåking | compliance-flagg på samtale-siden + `/dashboard` |
| 8 | Henvendelses-klassifisering | `/dashboard` (årsak-fordeling) |
| 9 | CRM-berikelse | `GET /integrations/crm/{navn}` + `POST /integrations/telephony/webhook` |
| 10 | Oppfølging / neste steg | `Analysis.follow_up` |
| 11 | Voice-of-customer / ledelse | `/dashboard` |
| 12 | Manus-/script-etterlevelse | `Analysis.script_adherence` |
| 13 | Måling / leverandør-eval | `/eval` (nøyaktighet mot fasit + ROI) |

Tverrgående: `/redaction` viser **PII-maskering** (ansvarlig AI / personvern).
Hele use-case-rammen er beskrevet i **[OVERVIEW.md](./OVERVIEW.md)**.

---

## EKSAKT Azure-oppskrift (dokumentasjon på "det kjører på Azure")

> Steg-for-steg-guiden (fra null til kjørende på Azure Container Apps, skrevet
> for Azure-nybegynnere) ligger i **[azure/deploy.md](./azure/deploy.md)**, med
> ferdig `azure/main.bicep`. Under er kortversjonen.

Målet: samme kodebase, men STT = **Azure AI Speech** (norsk, `nb-NO`) og LLM =
**Azure OpenAI** (EU / Sweden Central).

### 1. Env-variabler

```bash
# Den ene bryteren — setter STT=azure + LLM=azure-openai automatisk
export DEPLOY_TARGET=azure

# Azure AI Speech (norsk tale-til-tekst)
export AZURE_SPEECH_KEY=<speech-key>
export AZURE_SPEECH_REGION=swedencentral
export AZURE_SPEECH_LANGUAGE=nb-NO

# Azure OpenAI (EU-region for datalokasjon)
export AZURE_OPENAI_ENDPOINT=https://<din-resurs>.openai.azure.com
export AZURE_OPENAI_KEY=<openai-key>
export AZURE_OPENAI_DEPLOYMENT=gpt-4o     # navnet på din deployment

# Avhengigheter for Azure-backends
pip install azure-cognitiveservices-speech openai
```

Integrasjonspunktene er allerede wiret i koden — søk etter
`AZURE-INTEGRASJONSPUNKT` i `app/providers/stt.py` og `app/providers/llm.py`.
De kjøres ikke uten nøkkel; med nøkler satt er det de kommenterte kall-blokkene
som aktiveres.

### 2. Azure-ressurser du oppretter

| Tjeneste | Ressurs | Region | Merk |
|----------|---------|--------|------|
| Tale-til-tekst | **Azure AI Speech** | Sweden Central | Norsk (`nb-NO`); bruk `ConversationTranscriber` for agent/kunde-separasjon |
| Analyse (LLM) | **Azure OpenAI** | Sweden Central (EU) | Deploy f.eks. `gpt-4o`; EU-region holder data i EU |

### 3. Deploy (velg én)

**Azure Container Apps** (anbefalt for en stateless web-app):

```bash
# Dockerfile: python:3.11-slim, pip install -r requirements.txt,
# CMD uvicorn app.main:app --host 0.0.0.0 --port 8000

az containerapp up \
  --name loyalty-callcenter-ai \
  --resource-group <rg> \
  --location swedencentral \
  --source . \
  --ingress external --target-port 8000 \
  --env-vars DEPLOY_TARGET=azure \
             AZURE_SPEECH_REGION=swedencentral AZURE_SPEECH_LANGUAGE=nb-NO \
             AZURE_OPENAI_DEPLOYMENT=gpt-4o
# Nøkler (AZURE_SPEECH_KEY, AZURE_OPENAI_KEY, AZURE_OPENAI_ENDPOINT) settes som
# secrets i Container Apps, ikke som klartekst.
```

**Azure App Service** (alternativ):

```bash
az webapp up --runtime PYTHON:3.11 --location swedencentral \
  --name loyalty-callcenter-ai --resource-group <rg>
# Startkommando:
#   uvicorn app.main:app --host 0.0.0.0 --port 8000
# Sett app settings (env-vars) i portalen / via `az webapp config appsettings set`.
```

Poenget: **ingen kodeendring** mellom lokal og Azure — kun `DEPLOY_TARGET` +
nøkler/endepunkter. Det er nettopp dette som gjør at "det kjører på Azure".

---

## Produksjon (utenfor demoens scope)

Demoen har bevisst **ingen sikkerhet** for å holde den enkel å kjøre. I
produksjon hører følgende hjemme — her er hvor:

- **Auth / tilgangsstyring**: foran FastAPI (`app/main.py`) — f.eks. OAuth2 /
  Entra ID, rollebasert tilgang per agent/teamleder. Egne middleware-lag.
- **PII-maskering**: i STT-laget (`app/providers/stt.py`), rett etter
  transkripsjon — skjul personnummer, fødselsdato, kontonummer og kortnummer i
  `Transcript.turns` **før** teksten lagres, vises eller sendes til LLM. (I
  demoens transkript er det ekte-utseende navn/fødselsdato nettopp for å vise
  *hvor* maskeringen må skje.)
- **Samtykke**: registrer og verifiser samtykke til opptak/analyse før en
  samtale behandles; QA-scorecardens `samtykke`-punkt er kun en *indikator*, ikke
  en juridisk logg.
- **Audit-logg**: hvem så hvilken samtale/analyse, når — eget append-only logglag.
- **Kryptering**: i transitt (TLS, gitt) og i ro (transkript/analyse lagret
  kryptert; Azure Storage/DB med CMK).
- **Databehandleravtale (DPA)**: med Microsoft for Azure-tjenestene, og EU-region
  (Sweden Central) for datalokasjon. Vurder ZDR/retention-krav for LLM.

---

## Filstruktur

```
call-center-ai-demo/
├── app/
│   ├── config.py            # DEPLOY_TARGET → backend-valg (portabilitets-bryteren)
│   ├── models.py            # pydantic: Transcript, Analysis, Scorecard, ...
│   ├── main.py              # FastAPI: kjerne-ruter (/ /call /healthz) + auto-include av routers/
│   ├── redaction.py         # PII-maskeringslogikk
│   ├── providers/
│   │   ├── stt.py           # transcribe() / transcribe_audio() — mock | faster-whisper | nb-whisper | azure
│   │   └── llm.py           # analyze() — mock | anthropic | azure-openai
│   ├── integrations/        # crm.py, telephony.py
│   └── routers/             # auto-inkluderte feature-ruter:
│       ├── dashboard.py     #   /dashboard
│       ├── eval.py          #   /eval
│       ├── redaction.py     #   /redaction
│       ├── integrations.py  #   /integrations/crm/{navn}, /integrations/telephony/webhook
│       ├── live.py          #   /live
│       ├── analyze_text.py  #   POST /analyze-text
│       ├── transcribe.py    #   POST /transcribe
│       └── stt_compare.py   #   /stt (plattform-sammenligning)
├── templates/               # base, index, call, _analysis, dashboard, eval, live (Jinja2)
├── static/                  # css/js (kjør-på-nytt-knapp, live-STT, arkitektur-svg)
├── data/                    # norske demo-transkript + _labels.json (gull-fasit)
├── docs/                    # arkitektur.md, demo-manus.md
├── azure/                   # deploy.md (steg-for-steg) + main.bicep
├── tests/                   # pytest: pluggability, determinisme, scorecard, API, redaction
├── FEATURES.md              # rute → funksjon → use-case (én side)
├── OVERVIEW.md              # hva/hvorfor + 13-use-case-rammen
├── requirements.txt
├── .env.example
└── run.sh
```
