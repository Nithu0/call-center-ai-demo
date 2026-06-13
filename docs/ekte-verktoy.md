# Koble opp EKTE verktøy (utenfor mock/Azure)

Denne guiden viser hvordan du bytter call-senter-AI-demoen fra mock-modus til
**ekte** tale-til-tekst (STT) og ekte LLM-analyse. Den er ærlig om hva som
krever nøkkel, hva som sender data til skyen, og hva som kjører helt lokalt.

> **Ærlighet om kommando-navn:** Noen kommandoer som har versert i intern
> dokumentasjon (`setup-real.sh`, `scripts/gen_all_audio.py`, `scripts/verify_stt.py`,
> `scripts/verify_llm.py`, endepunktet `/status`) finnes **ikke** i repoet i dag.
> Denne guiden bruker det som **faktisk** ligger her:
> `requirements-real.txt`, `scripts/gen_audio.py`, `scripts/gen_call_audio.py`,
> og helse-endepunktet `/healthz`. Der den gamle dokumentasjonen pekte feil,
> står det et eksplisitt merknad-avsnitt.

---

## TL;DR — anbefaling for testing

Vil du teste ekte STT **uten nøkkel og uten sky**: bruk **faster-whisper lokalt**.
Det er CPU-only, ingen API-nøkkel, ingen Azure. Modellen lastes ned én gang fra
Hugging Face, deretter kjører alt offline.

```bash
# 1. Installer ekte backends (ingen nøkkel for faster-whisper + gTTS)
pip install -r requirements-real.txt          # eller: pip install faster-whisper gtts

# 2. Generer norsk testlyd fra demo-samtalene (salg_alarm.mp3 m.fl.)
python scripts/gen_call_audio.py --all         # eller uten --all = bare salg_alarm

# 3. Kjør EKTE lokal transkripsjon på lyden
STT_BACKEND=faster-whisper python -c \
  "from app.providers.stt import transcribe; print(transcribe('data/audio/salg_alarm.mp3').full_text)"
```

---

## Backend-oversikt

| Backend | Type | Trenger nøkkel? | Personvern | Kommando (env) |
|---|---|---|---|---|
| `faster-whisper` | STT, lokal | **Nei** | Alt lokalt (CPU). Modell lastes ned én gang fra Hugging Face, så offline | `STT_BACKEND=faster-whisper` |
| `nb-whisper` | STT, lokal (norsk-tunet) | **Nei** | Alt lokalt. Tyngre (~GB torch-nedlasting), best norsk | `STT_BACKEND=nb-whisper` |
| `openai` | STT, sky | **Ja** (`OPENAI_API_KEY`) | Lyd sendes til OpenAI (USA). Ikke for sensitive ekte data | `STT_BACKEND=openai` |
| `azure` | STT, sky (EU) | **Ja** (`AZURE_SPEECH_KEY`) | Azure AI Speech, EU-region. Enterprise. Wiret integrasjonspunkt | `DEPLOY_TARGET=azure` |
| `mock` | STT, offline | Nei | Ingen ekte transkripsjon — slår opp ferdige samples. Default | `STT_BACKEND=mock` |
| `anthropic` | LLM, sky | **Ja** (`ANTHROPIC_API_KEY`) | Transkript sendes til Anthropic. Sky-uavhengig (ikke bundet til Azure) | `LLM_BACKEND=anthropic` |
| `azure-openai` | LLM, sky (EU) | **Ja** (`AZURE_OPENAI_KEY`) | Azure OpenAI, EU-region | `DEPLOY_TARGET=azure` |
| `mock` | LLM, offline | Nei | Ingen ekte analyse — deterministisk demo-svar. Default | `LLM_BACKEND=mock` |

To env-variabler styrer alt: `STT_BACKEND` og `LLM_BACKEND`. `DEPLOY_TARGET=azure`
setter automatisk begge til Azure-variantene. Alle backends returnerer **samme**
datamodell, så resten av appen er uendret uansett valg.

---

## 1. Lokal STT uten nøkkel — `faster-whisper` (anbefalt for "utenfor Azure")

Dette er den enkleste veien til ekte transkripsjon uten å sende noe til skyen.

```bash
# Installer (ingen nøkkel). faster-whisper kjører på CPU via ctranslate2; gTTS
# brukes bare for å lage norsk testlyd.
pip install -r requirements-real.txt          # eller: pip install faster-whisper gtts

# Generer norsk demo-lyd fra de innebygde samtalene.
# Default lager data/audio/salg_alarm.mp3. --all lager alle data/*.json.
python scripts/gen_call_audio.py --all
#   (gTTS krever nett for selve syntesen. Vil du ha en kort, offline systemstemme:
#    python scripts/gen_call_audio.py --backend pyttsx3, krever `pip install pyttsx3`.)

# Kjør EKTE transkripsjon på en av lydfilene:
STT_BACKEND=faster-whisper python -c \
  "from app.providers.stt import transcribe; print(transcribe('data/audio/salg_alarm.mp3').full_text)"
```

Hva som skjer:

- **Ingen nøkkel, ingen sky.** Alt kjøres på CPU.
- **Modellen lastes ned én gang** fra Hugging Face (cache i `~/.cache/huggingface`),
  deretter er kjøringen offline.
- **Modellvalg via `FASTER_WHISPER_MODEL`** — `tiny` / `base` / `small` (default) /
  `medium`. Større = mer nøyaktig, men tregere. For rask test: `tiny`.
- Andre knapper: `FASTER_WHISPER_DEVICE` (default `cpu`), `FASTER_WHISPER_COMPUTE`
  (default `int8`).

```bash
# Raskere/lettere modell:
FASTER_WHISPER_MODEL=tiny STT_BACKEND=faster-whisper python -c \
  "from app.providers.stt import transcribe; print(transcribe('data/audio/salg_alarm.mp3').full_text)"
```

> Robusthet: hvis `faster-whisper` ikke er installert, faller backenden tilbake
> til mock med en advarsel — den krasjer aldri offline.

---

## 2. NB-Whisper — norsk-tunet, lokal, ingen nøkkel

Nasjonalbibliotekets NB-Whisper gir vanligvis best norsk, men er tyngre (torch).

```bash
pip install transformers torch        # ingen nøkkel, men ~GB nedlasting

STT_BACKEND=nb-whisper python -c \
  "from app.providers.stt import transcribe; print(transcribe('data/audio/salg_alarm.mp3').full_text)"
```

- **Ingen nøkkel, alt lokalt.** Modell: `NbAiLab/nb-whisper-small`
  (overstyr med `NB_WHISPER_MODEL`).
- Tyngre enn faster-whisper (torch + transformers). Bruk denne når norsk kvalitet
  betyr mest; faster-whisper når du vil ha lett/rask.
- Mangler `transformers`/`torch`? → faller tilbake til mock med advarsel.

---

## 3. OpenAI Whisper API — betalt, krever nøkkel, sender lyd til USA

Enkleste **betalte** STT: ingen lokal modell, bare en nøkkel.

```bash
pip install openai
export OPENAI_API_KEY=sk-...           # eller legg i .env

STT_BACKEND=openai python -c \
  "from app.providers.stt import transcribe; print(transcribe('data/audio/salg_alarm.mp3').full_text)"
```

- **Krever `OPENAI_API_KEY`.** Uten nøkkel kaster backenden en tydelig feil.
- **Lyd sendes til OpenAI (USA).** Ikke bruk dette på sensitive ekte kundedata —
  bruk da lokal NB-Whisper/faster-whisper eller Azure Speech (EU).
- Billig (whisper-1 ~$0.006/min). Modell via `OPENAI_STT_MODEL`
  (default `whisper-1`; `gpt-4o-transcribe` er nyere/bedre).

> Merknad: `.env.example` lister i kommentaren STT-backendene som
> `mock | faster-whisper | nb-whisper | azure` (uten `openai`). Den kommentaren er
> utdatert — `STT_BACKEND=openai` **er** wiret i `app/providers/stt.py` og fungerer.

---

## 4. Anthropic Claude for analyse — betalt, krever nøkkel

Dette bytter **LLM-analysen** (klassifisering, oppsummering, neste-steg) fra mock
til ekte Claude. Sky-uavhengig: bundet verken til Azure eller OpenAI.

```bash
pip install anthropic
export ANTHROPIC_API_KEY=sk-ant-...     # eller legg i .env

# Kjør ekte analyse på en demo-samtale:
LLM_BACKEND=anthropic python -c \
  "from app.providers import stt, llm; t = stt.transcribe('salg_alarm'); print(llm.analyze(t).model_dump_json(indent=2))"
```

- **Krever `ANTHROPIC_API_KEY`.** Uten nøkkel kaster backenden en tydelig feil.
- **Transkript sendes til Anthropic.** Modell via `ANTHROPIC_MODEL`
  (default `claude-opus-4-8`).
- Kan kombineres fritt med en lokal STT, f.eks. lokal lyd→tekst med faster-whisper
  og deretter analyse med Claude:
  ```bash
  STT_BACKEND=faster-whisper LLM_BACKEND=anthropic python -c \
    "from app.providers import stt, llm; t = stt.transcribe('data/audio/salg_alarm.mp3'); print(llm.analyze(t).model_dump_json(indent=2))"
  ```

> Merknad: prompten/intern-dok refererer `scripts/verify_llm.py --backend anthropic`.
> Det scriptet finnes **ikke** i repoet i dag. Bruk one-lineren over, eller
> kjør appen og POST til `/call/<navn>/analyze` (se §6).

---

## 5. Azure — EU, enterprise (krever nøkler)

For enterprise-oppsett i EU bytter du hele systemet med én variabel.

```bash
# I .env:
DEPLOY_TARGET=azure
# DEPLOY_TARGET=azure setter automatisk STT_BACKEND=azure + LLM_BACKEND=azure-openai.

# Azure AI Speech (STT):
AZURE_SPEECH_KEY=...
AZURE_SPEECH_REGION=swedencentral
AZURE_SPEECH_LANGUAGE=nb-NO

# Azure OpenAI (LLM) — bruk EU-region:
AZURE_OPENAI_ENDPOINT=https://<din-resurs>.openai.azure.com
AZURE_OPENAI_KEY=...
AZURE_OPENAI_DEPLOYMENT=gpt-4o
```

```bash
pip install azure-cognitiveservices-speech openai
```

- **Krever nøkler.** Uten nøkkel kaster backendene en tydelig feil.
- **EU-region** (Sweden Central) — egnet for sensitive persondata.
- Ærlighet: Azure Speech-backenden er **wiret men ikke kjørt** i demoen
  (`NotImplementedError` uten gyldig nøkkel). Selve integrasjonsoppskriften
  ligger som AZURE-INTEGRASJONSPUNKT i `app/providers/stt.py` (bruk
  `ConversationTranscriber` for innebygd taler-separasjon). Azure OpenAI-LLM er
  tilsvarende wiret i `app/providers/llm.py`.

---

## 6. Verifiser at det funker

> Ærlighet: et eget `/status`-endepunkt og `scripts/verify_stt.py` /
> `scripts/verify_llm.py` finnes **ikke** i repoet i dag. Bruk i stedet
> `/healthz` (samme selvtest-info: aktivt deploy-target + STT/LLM-backend) og
> one-linerne under.

### a) Sjekk hvilke backends som er aktive — `/healthz`

```bash
./run.sh            # eller: uvicorn app.main:app --reload
curl -s localhost:8000/healthz
# -> {"status":"ok","deploy_target":"local","stt_backend":"faster-whisper","llm_backend":"mock", ...}
```

Front-sidens banner (`/`) viser de samme tre verdiene
(`deploy_target` / `stt_backend` / `llm_backend`), så du ser i UI hvilke
backends som er valgt.

### b) Verifiser STT direkte (uten å starte serveren)

```bash
STT_BACKEND=faster-whisper python -c \
  "from app.providers.stt import transcribe; print(transcribe('data/audio/salg_alarm.mp3').full_text)"
```

### c) Verifiser STT på opplastet lyd via API

```bash
STT_BACKEND=faster-whisper ./run.sh &
curl -F audio=@data/audio/salg_alarm.mp3 http://localhost:8000/transcribe
```

(Med `STT_BACKEND=mock` returnerer `/transcribe` en placeholder — ekte
transkripsjon krever en av de ekte backendene over.)

### d) Verifiser LLM-analyse

```bash
LLM_BACKEND=anthropic python -c \
  "from app.providers import stt, llm; print(llm.analyze(stt.transcribe('salg_alarm')).model_dump_json(indent=2))"
```

Eller via appen: start serveren og POST til `/call/salg_alarm/analyze`.

---

## Oppsummert anbefaling

**For testing: faster-whisper lokalt (null nøkkel, null sky).**
`pip install -r requirements-real.txt`, generer lyd med
`python scripts/gen_call_audio.py --all`, og kjør med
`STT_BACKEND=faster-whisper`. Trenger du best norsk: `nb-whisper`. Trenger du
ekte LLM-analyse: `LLM_BACKEND=anthropic` (nøkkel). For sensitive ekte kundedata:
hold STT lokal (faster-whisper/nb-whisper) eller bruk Azure (EU) — ikke OpenAI (USA).
