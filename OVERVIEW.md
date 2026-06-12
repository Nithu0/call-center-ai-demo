# OVERVIEW — Call-senter AI-demo (Loyalty)

## Hva dette er

En kjørbar demo av et call-senter-AI-system for norske kundesamtaler: lyd →
tale-til-tekst (STT) → automatisk analyse (LLM) → dashboard + CRM-eksport.
Kjernen er et **pluggbart provider-lag** der STT og LLM byttes via env-variabler,
slik at *samme kode* kjører lokalt (offline) eller på Azure. Default kjører alt
offline uten nøkler.

Kjøring: se **[README.md](./README.md)**. Arkitektur: **[docs/arkitektur.md](./docs/arkitektur.md)**.
Live-demo: **[docs/demo-manus.md](./docs/demo-manus.md)**.

## Hvorfor det er relevant for Loyalty

Loyalty leverer utkontraktert kundedialog med 400+ ansatte og store norske
samtalevolum, og har en AI-roadmap med 13 use cases — der ett konkret valg er
**hvilken STT som skal brukes på norske samtaler**. Demoen treffer dette direkte:

- **Fritt STT-valg, ingen innlåsing.** Test NB-Whisper (norsk-tunet, lokal) mot
  Azure AI Speech (`nb-NO`, driftet) bak samme kontrakt. Bytt uten å røre resten.
- **Personvern + skala samtidig.** Kjør STT lokalt (lyd forlater aldri huset),
  analyse i sky (EU-region) for skala. PII-maskering hører hjemme i STT-laget.
- **Portabilitet med én bryter.** `DEPLOY_TARGET=local` ↔ `azure` flytter hele
  systemet uten kodeendring — leverandørvalg blir reversibelt.
- **Målbart.** Fasit-labels (`data/_labels.json`) lar leverandørvalget tas på
  tall, ikke magefølelse.

## 13-use-case-rammen — hvor demoen treffer

Typiske call-senter-use-cases, og hvilken demo-funksjon som dekker dem:

| # | Use case | Demo-funksjon | Hvor |
|---|---|---|---|
| 1 | **Tale-til-tekst (norsk)** | Pluggbar STT: NB-Whisper / Azure AI Speech | `app/providers/stt.py` |
| 2 | **Auto-QA / samtalescoring** | 6-punkts QA-scorecard med begrunnelse + score-% | `llm.py` → scorecard |
| 3 | **Sammendrag** | 2–3 setningers sammendrag per samtale | `Analysis.summary` |
| 4 | **Sentiment** | positiv / nøytral / negativ | `Analysis.sentiment` |
| 5 | **Churn-/oppsigelsesdeteksjon** | Churn-risiko lav/middels/høy + høyrisiko-liste | `Analysis.churn_risk` + dashboard |
| 6 | **Agent-coaching** | Konkrete coaching-tips knyttet til hva som manglet | `Analysis.coaching_tips` |
| 7 | **Compliance-overvåking** | Compliance-flagg (samtykke, identifisering, pris, binding) | `Analysis.compliance_flags` |
| 8 | **Henvendelses-klassifisering** | Klassifisert henvendelsesårsak + fordeling | `call_reason` + dashboard |
| 9 | **CRM-berikelse** | Strukturert JSON: intent, produkt, utfall, neste steg, prioritet | `Analysis.crm_export` |
| 10 | **Oppfølging / neste steg** | Foreslåtte oppfølgingshandlinger per samtale | `Analysis.follow_up` |
| 11 | **Voice-of-customer / ledelse** | Aggregert dashboard (snitt-QA, sentiment, flagg, churn) | `/dashboard` |
| 12 | **Manus-/script-etterlevelse** | `script_adherence` i prosent | `Analysis.script_adherence` |
| 13 | **Måling / leverandør-eval** | Fasit-labels for å score modell + sammenligne backends | `data/_labels.json` |

Funksjonene over kjører i dag på de medfølgende demo-samtalene (salg,
kundeservice, oppsigelse, faktura, inkasso, booking, teknisk support) — offline,
deterministisk, uten nøkler.

## Hva som bevisst er utenfor demoen

Auth, PII-maskering, samtykke-logg, audit-logg, kryptering i ro og DPA er holdt
utenfor for å gjøre demoen enkel å kjøre — README «Produksjon» beskriver hvor
hvert av dem hører hjemme.

---

Kjør den selv på sekunder: **[README.md](./README.md)** (`./run.sh` → http://127.0.0.1:8000).
