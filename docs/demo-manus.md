# Demo-manus — call-senter AI (intervju / møte)

Manus for å vise demoen live på 5–7 minutter. Hvert steg: hva du **gjør** og
hva du **sier**. Holdes nøkternt — vis at det kjører, ikke selg luft.

## Før møtet (2 min oppsett, ikke del av tiden)

```bash
cd call-center-ai-demo
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # DEPLOY_TARGET=local — offline, ingen nøkler
./run.sh                    # → http://127.0.0.1:8000
```

Ha nettleseren åpen på `http://127.0.0.1:8000`. Default er lokal/offline, så
ingenting kan feile på dårlig wifi. Ha en terminal klar ved siden av for det
siste steget (Azure-bryteren).

---

## Steg 1 — Forsiden + portabilitets-tesen (ca. 45 sek)

**Gjør:** Åpne forsiden. Pek på banneret øverst.

**Si:**
> «Dette er en kjørbar demo av et call-senter-AI-system for norske samtaler.
> Legg merke til banneret: det viser `DEPLOY_TARGET=local` og hvilke providere
> som er aktive. Kjernepoenget står der — *samme kode, bytt to env-variabler, så
> kjører det på Azure*. Akkurat nå kjører alt offline, uten nøkler eller nett.
> Under ser dere en liste over demo-samtaler — salg, kundeservice, oppsigelse,
> faktura, inkasso, booking, teknisk support.»

---

## Steg 2 — Åpne en samtale: transkript + analyse (ca. 1,5 min)

**Gjør:** Klikk på et salgsanrop (f.eks. *salg_alarm*). Transkript til venstre,
AI-analyse til høyre.

**Si:**
> «Til venstre er transkriptet — i produksjon kommer dette fra tale-til-tekst på
> den norske lyden. Til høyre har AI-en gjort jobben automatisk: et sammendrag
> på to–tre setninger, sentiment, og nøkkelinfo — kundens intensjon, produkt,
> utfall og neste steg. Én agent gjør dette på minutter; her er det gjort i det
> samtalen lander, på *hver* samtale.»

---

## Steg 3 — Scorecard + compliance-flagg (ca. 1 min)

**Gjør:** Pek på QA-scorecardet (de seks punktene med farge) og på
compliance-flaggene.

**Si:**
> «Dette er auto-QA. Scorecardet scorer mot Loyaltys sjekkliste — hilsen,
> identifisering, behovskartlegging, løsning, samtykke, avslutning — med en kort
> begrunnelse per punkt. Her mangler *samtykke*, så det blir et compliance-flagg.
> I dag rekker en teamleder å lytte på kanskje 2–3 % av samtalene; dette kjører
> på 100 %, likt hver gang. Coaching-tipsene under er konkrete og knyttet til
> akkurat det som manglet i denne samtalen.»

---

## Steg 4 — Ledelses-dashboard (ca. 1 min)

**Gjør:** Gå til `/dashboard`.

**Si:**
> «Når dette kjører på alle samtaler får ledelsen et voice-of-customer-bilde:
> snitt-QA-score totalt og per samtale, sentiment-fordeling, de hyppigste
> compliance-flaggene, fordeling av henvendelsesårsaker, og en churn-oversikt
> med hvilke samtaler som er høy-risiko. Dette er aggregatet av nøyaktig den
> analysen dere så på forrige side — ingen ekstra manuell jobb.»

---

## Steg 5 — Eval / effekt (ca. 45 sek)

**Gjør:** Pek på at det finnes fasit-labels (`data/_labels.json`) for samtalene.

**Si:**
> «Et AI-system må kunne måles, ikke bare demonstreres. Vi har manuelle
> fasit-labels per samtale — riktig henvendelsesårsak, sentiment og QA-score.
> Det lar oss måle hvor godt modellen treffer, og kjøre samme måling igjen når
> vi bytter STT- eller LLM-leverandør. Så valget av leverandør kan tas på tall,
> ikke på magefølelse. Effekten i drift er enkel: QA fra stikkprøve til 100 %
> dekning, kortere etterarbeid per samtale, og compliance-avvik fanges samme dag.»

---

## Steg 6 — Bytt DEPLOY_TARGET → Azure (ca. 1 min)

**Gjør:** I terminalen, vis bryteren. (Uten Azure-nøkler stopper appen ved
integrasjonspunktet — det er poenget å *vise* bryteren, ikke å kjøre Azure live.)

```bash
# samme kode, samme image — kun env endres
export DEPLOY_TARGET=azure
```

**Si:**
> «Her er hele portabilitets-poenget. Jeg bytter *én* variabel — `DEPLOY_TARGET`
> fra local til azure. Da peker `app/config.py` STT-laget på Azure AI Speech med
> norsk `nb-NO`, og analyse-laget på Azure OpenAI i EU-region, Sweden Central.
> Ingen kodeendring. Integrasjonspunktene er allerede wiret i koden — se
> `AZURE-INTEGRASJONSPUNKT` i `stt.py` og `llm.py`. Samme container-image kjører
> lokalt og på Azure Container Apps; det eneste som skiller er env-variabler og
> nøkler. Det betyr at dere ikke er låst: dere kan kjøre STT lokalt for personvern
> og analyse i sky for skala, og bytte leverandør senere uten å bygge om.»

**Gjør:** Bytt tilbake til offline for trygghet.

```bash
export DEPLOY_TARGET=local
```

---

## Avslutning (15 sek)

**Si:**
> «Oppsummert: pluggbart provider-lag, fritt valg av norsk STT, auto-QA og
> dashboard på 100 % av volumet, og full portabilitet lokal ↔ Azure med én
> bryter. Demoen er offline-kjørbar, så dere kan teste den selv på sekunder.»

---

## Hvis noen spør

- **«Hvor er personvernet?»** → PII-maskering hører hjemme i STT-laget rett etter
  transkripsjon, før tekst lagres/sendes til LLM. STT kan kjøres lokalt så lyd
  aldri forlater huset. Se README «Produksjon» + `docs/arkitektur.md`.
- **«Er dette ekte AI eller bare regler?»** → Offline-demoen bruker en
  deterministisk mock så den alltid er grønn. Med `LLM_BACKEND=anthropic` eller
  `azure-openai` (+ nøkkel) kjører ekte LLM bak *samme* kontrakt — UI-et endrer seg ikke.
- **«Skalerer dette?»** → Stateless FastAPI, STT og LLM er separate lag som
  skaleres uavhengig på Azure Container Apps.
- **«Hvilken STT er best for norsk?»** → Det er nettopp et måle-spørsmål: test
  NB-Whisper mot Azure AI Speech bak samme kontrakt og bruk eval-labelene.
