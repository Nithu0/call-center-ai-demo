# Koble opp ekte verktøy på din maskin

Demoen kjører offline med mock-providere ut av boksen. Vil du teste mot **ekte**
tale-til-tekst og LLM, følg de korteste kommandoene i rekkefølge:

```bash
make install-real     # setter opp faster-whisper + API-klienter (setup-real.sh)
make audio            # genererer demo-lydklippene i data/audio/
make verify-stt       # transkriberer data/audio/salg_alarm.mp3 (sjekker STT)
make verify-llm       # sjekker LLM-koblingen
make run              # start API-en, åpne så /status i nettleseren
```

Etter `make run`: åpne **http://127.0.0.1:8000/status** for å se hvilke
providere som er aktive (mock vs. ekte).

## Hva krever nøkkel?

- **faster-whisper (STT)** er **null-nøkkel og lokal** — kjører rett på din
  maskin, ingen API-konto nødvendig. `make verify-stt` funker etter
  `make install-real`.
- **API-veiene** (LLM + ev. sky-STT/TTS) krever nøkkel i `.env`. Kopier
  `.env.example` til `.env` og fyll inn nøklene før `make verify-llm`.

```bash
cp .env.example .env   # rediger .env og legg inn nøklene dine
```

Mangler en nøkkel, faller den veien tilbake til mock — demoen kjører fortsatt.
