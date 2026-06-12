# FEATURES — rute → funksjon → Loyalty-use-case

Én-side oversikt over alle ruter i demoen, hva de gjør, og hvilken av Loyaltys
13 use cases de treffer (se `OVERVIEW.md` for hele use-case-rammen). Alle ruter
kjører offline med mock-providere som default (`DEPLOY_TARGET=local`).

| Rute | Metode | Hva den gjør | Loyalty-use-case |
|------|--------|--------------|------------------|
| `/` | GET | Forside: liste over demo-samtaler + provider-banner (DEPLOY_TARGET, aktiv STT/LLM, "bytt 2 env-variabler → Azure"). | Inngang / portabilitets-tese |
| `/call/{navn}` | GET | Samtale-side: transkript til venstre, full AI-analyse til høyre (scorecard, sammendrag, sentiment, nøkkelinfo, compliance-flagg, oppfølging) + "kjør analyse på nytt"-knapp. | 2 Auto-QA · 3 Sammendrag · 4 Sentiment · 6 Coaching · 7 Compliance · 10 Oppfølging |
| `POST /call/{navn}/analyze` | POST | Kjører analysen på nytt for én samtale og returnerer JSON (brukes av knappen). | 2 Auto-QA (re-kjør) |
| `/healthz` | GET | Helsesjekk: `status: ok` + provider-banner (deploy-target, aktive backends). | Drift / observability |
| `/dashboard` | GET | Ledelses-dashboard: aggregert snitt-QA, sentiment-fordeling, churn-fordeling, høyrisiko-liste, topp compliance-flagg, henvendelsesårsak-fordeling. | 5 Churn · 8 Klassifisering · 11 Voice-of-customer |
| `/eval` | GET | Dokumentert effekt: nøyaktighet mot gull-fasit (`data/_labels.json`), tidsbesparelse, interaktiv ROI-kalkulator (slidere), pilot-narrativ. | 13 Måling / leverandør-eval |
| `/redaction` | GET | PII-maskering før/etter for et transkript (`?name=`) eller fri tekst (`?text=`), med revisjonsvennlig funn-liste. `?format=json` for API. | Ansvarlig AI / personvern (tverrgående) |
| `/integrations/crm/{navn}` | GET | Bygger og returnerer CRM-klar JSON-payload for én samtale (intent, produkt, utfall, neste steg, prioritet) + dry-run push. | 9 CRM-berikelse |
| `POST /integrations/telephony/webhook` | POST | Tar imot contact-center-event (Puzzel/Genesys/...) og kjører hele pipelinen (STT → LLM → CRM-payload). | 9 CRM-berikelse / integrasjon |
| `/live` | GET | LIVE tale-til-tekst i nettleseren (Web Speech API, `nb-NO`, kontinuerlig): se tekst live mens du snakker, send til analyse. Fallback: lim inn tekst manuelt. | 1 Tale-til-tekst (live) |
| `POST /analyze-text` | POST | Analyserer VILKÅRLIG samtaletekst (fra live-STT, innliming, hvilken som helst kilde): bygger transkript + kjører `llm.analyze()`. Returnerer transkript + analyse som JSON. | 2 Auto-QA på fritekst (alle analyse-use-cases) |
| `POST /transcribe` | POST | Den PRIVATE backend-STT-veien: tar imot opplastet/innspilt lydfil → STT-provider-laget (NB-Whisper lokalt / Azure AI Speech). Svarer alltid 200; med mock-backend kommer et `note`-felt som forklarer hvordan ekte STT slås på. | 1 Tale-til-tekst (server-side) |
| `/stt` | GET | STT-plattform-sammenligning: kriterie-matrise over NB-Whisper, Whisper large-v3, Azure AI Speech, Google STT, Deepgram (norsk-nøyaktighet, kostnad, latens, personvern, diarisering, integrasjon) + anbefaling knyttet til DEPLOY_TARGET. Tall er merkede estimater. | 1 Tale-til-tekst (leverandørvalg) · 13 Leverandør-eval |

## Personvern-merknad om STT-veiene

- `/live` bruker **nettleserens Web Speech API** — i Chrome sendes lyden til
  Googles servere. **Kun for demo.** Ingen sensitiv kundelyd skal kjøres her.
- `POST /transcribe` er **produksjons-veien**: lyden går server-side gjennom
  provider-laget (NB-Whisper lokalt — lyd forlater aldri huset — eller Azure AI
  Speech i EU-region). Dette er STT-veien et reelt oppsett bruker.

## STT-plattformvalg

To komplementære veier til Loyaltys #1-oppgave (velg STT for norsk):

- **`/stt`** — kriterie-matrise som sammenligner de reelle plattformene
  (NB-Whisper, Whisper large-v3, Azure AI Speech, Google STT, Deepgram) med
  anbefaling. Estimater, tydelig merket — rammeverket for valget.
- **Mål det selv** — bytt `STT_BACKEND` (`mock` · `faster-whisper` · `nb-whisper`
  · `azure`) i det pluggbare provider-laget og score backenden mot gull-fasit på
  `/eval`.
