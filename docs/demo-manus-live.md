# Demo-manus — call-senter AI MED live tale-til-tekst (intervju / møte)

Oppdatert manus på 5–8 minutter som inkluderer det nye live-STT-segmentet.
Hvert steg: hva du **gjør** og hva du **sier**. Holdes nøkternt — vis at det
kjører, ikke selg luft. (For grunnversjonen uten live-STT, se `demo-manus.md`.)

## Før møtet (2 min oppsett, ikke del av tiden)

```bash
cd call-center-ai-demo
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # DEPLOY_TARGET=local — offline, ingen nøkler
./run.sh                    # → http://127.0.0.1:8000
```

- Bruk **Chrome eller Edge** — live-STT (`/live`) krever Web Speech API.
- Tillat mikrofon-tilgang i nettleseren på forhånd, så du slipper en dialog midt
  i demoen. Siden må kjøres fra `localhost` (eller HTTPS) for mikrofon-tilgang.
- Ha en terminal klar ved siden av til det siste steget (Azure-bryteren).
- Default er lokal/offline, så ingenting feiler på dårlig wifi.

---

## Steg 1 — Forsiden + portabilitets-tesen (ca. 45 sek)

**Gjør:** Åpne `http://127.0.0.1:8000`. Pek på banneret øverst.

**Si:**
> «Dette er en kjørbar demo av et call-senter-AI-system for norske samtaler.
> Banneret viser `DEPLOY_TARGET=local` og hvilke providere som er aktive.
> Kjernepoenget står der — *samme kode, bytt to env-variabler, så kjører det på
> Azure*. Akkurat nå kjører alt offline, uten nøkler eller nett. Under ligger en
> liste demo-samtaler. Men la oss starte med det som er kjernen for dere: å gå
> fra ekte tale til ferdig analyse, live.»

---

## Steg 2 — Live tale-til-tekst (`/live`) (ca. 2 min)

**Gjør:** Gå til `/live`. Klikk «Start opptak». Snakk inn en kort norsk
oppsigelses-samtale, f.eks.:

> «Agent: Hei, du snakker med Loyalty, hva kan jeg hjelpe med?
> Kunde: Hei, jeg ringer egentlig for å si opp abonnementet mitt. Det har blitt
> for dyrt, og jeg bruker det nesten ikke lenger.»

Pek på at teksten kommer fram **live** mens du snakker.

**Si:**
> «Her snakker jeg inn en samtale og teksten dukker opp i sanntid. Dette er det
> Loyalty gjør tusenvis av ganger om dagen — en kunde ringer for å si opp. Legg
> merke til at det skjer på norsk, live, uten oppsett.»

**Gjør:** Stopp opptaket. Klikk «✨ Analyser denne samtalen».

**Si:**
> «Når samtalen er ferdig sender jeg teksten til analyse-laget — samme AI som
> kjører på de lagrede samtalene. Her til høyre kommer sammendraget, sentimentet,
> nøkkelinfo, QA-scorecardet og coaching-tipsene.»

**Gjør:** Pek på churn-risiko og coaching i analysen.

**Si:**
> «Dette er poenget: AI-en fanger at dette er en *oppsigelse* med høy churn-
> risiko — kunden sier ‘for dyrt’ og ‘bruker det ikke’. Det er nettopp samtalen
> en teamleder vil at agenten skal redde. Coaching-tipset er konkret og knyttet
> til akkurat denne samtalen — ikke en generisk sjekkliste. Tenk dette på *hver*
> oppsigelsessamtale, samme dag den skjer.»

---

## Steg 3 — Personvern: hvor lyden faktisk går (ca. 1 min)

**Gjør:** Bli stående på `/live`. Pek på banneret / nevn Web Speech API.

**Si:**
> «Viktig forbehold, og det er en feature, ikke en bug: live-veien her bruker
> nettleserens egen talegjenkjenning, som i Chrome sender lyden til Google. Det
> er helt greit til en demo, men *ikke* til ekte kundedata. I produksjon snur vi
> det: lyden går til **NB-Whisper** kjørt lokalt — da forlater den aldri huset —
> eller til **Azure AI Speech** med norsk `nb-NO` i EU-region under DPA. Samme
> flyt for dere; bare et privat sted gjenkjenningen kjører.»

---

## Steg 4 — Den private backend-veien (`/transcribe`) (ca. 1 min)

**Gjør:** Forklar `POST /transcribe` (kan vises via curl eller bare beskrives).
Pek på at svaret inneholder hvilken backend som transkriberte.

**Si:**
> «Den private veien er endepunktet `/transcribe`. Det tar imot lydfila —
> mikrofon-opptak eller opplasting — og kjører den gjennom *server-side* STT, ikke
> nettleseren. Akkurat nå, offline, er backenden `mock`, så svaret er et
> placeholder-transkript med en tydelig melding om at man setter
> `STT_BACKEND=nb-whisper` eller `azure` for ekte transkripsjon. Poenget: samme
> kontrakt, samme `Transcript`-modell — UI-et ser ingen forskjell på om lyden ble
> tatt lokalt eller i sky. Det er det som gjør at dere kan velge STT på
> personvern uten å bygge om systemet.»

> Detaljene står i `docs/live-stt.md` — de to veiene, personvern og hvorfor norsk
> telefonlyd er det vanskelige (dialekter + smalbånds telefonlyd).

---

## Steg 5 — Måling: STT-/LLM-valg på tall (`/eval`) (ca. 1 min)

**Gjør:** Gå til `/eval`. Pek på at det finnes fasit-labels
(`data/_labels.json`) per samtale.

**Si:**
> «Et AI-system må kunne *måles*, ikke bare demonstreres. Vi har manuelle
> fasit-labels per samtale — riktig henvendelsesårsak, sentiment og QA-score.
> Det lar oss kjøre samme måling igjen når vi bytter STT-leverandør: transkriber
> de samme samtalene med NB-Whisper og med Azure AI Speech bak samme kontrakt, og
> sammenlign treffsikkerheten mot fasiten. Så valget av norsk STT tas på data,
> ikke på leverandørens påstand — og det er nettopp innlåsingen dere unngår.»

---

## Steg 6 — Bytt DEPLOY_TARGET → Azure (ca. 1 min)

**Gjør:** I terminalen, vis bryteren. (Uten Azure-nøkler stopper appen ved
integrasjonspunktet — poenget er å *vise* bryteren, ikke å kjøre Azure live.)

```bash
# samme kode, samme image — kun env endres
export DEPLOY_TARGET=azure
```

**Si:**
> «Her er hele portabilitets-poenget. Jeg bytter *én* variabel — `DEPLOY_TARGET`
> fra local til azure. Da peker STT-laget på Azure AI Speech med norsk `nb-NO`,
> og analyse-laget på Azure OpenAI i EU-region, Sweden Central. Ingen kodeendring.
> Integrasjonspunktene er allerede wiret — se `AZURE-INTEGRASJONSPUNKT` i
> `stt.py` og `llm.py`. Samme container-image kjører lokalt og på Azure Container
> Apps; det eneste som skiller er env-variabler og nøkler. Dere er ikke låst: STT
> lokalt for personvern, analyse i sky for skala, og bytt leverandør senere uten
> å bygge om.»

**Gjør:** Bytt tilbake til offline for trygghet.

```bash
export DEPLOY_TARGET=local
```

---

## Avslutning (15 sek)

**Si:**
> «Oppsummert: live tale-til-tekst på norsk fra `/live`, en privat backend-vei
> via `/transcribe` (NB-Whisper lokalt eller Azure AI Speech), auto-QA og churn-
> deteksjon på 100 % av volumet, måling mot fasit slik at STT-valget tas på tall,
> og full portabilitet lokal ↔ Azure med én bryter. Demoen er offline-kjørbar, så
> dere kan teste den selv på sekunder.»

---

## Hvis noen spør

- **«Sender dere kundelyd til Google?»** → Bare på `/live`-demoveien (Web Speech
  API). I produksjon brukes `/transcribe` med NB-Whisper lokalt (lyd forlater
  aldri huset) eller Azure AI Speech i EU-region. Se `docs/live-stt.md`.
- **«Virker live-STT i alle nettlesere?»** → Nei — Web Speech API krever Chrome/
  Edge + mikrofon + localhost/HTTPS. `/live` har en fallback: et tekstfelt der
  man limer inn en samtale og analyserer den med samme AI, så demoen virker
  uansett.
- **«Hvilken STT er best for norsk?»** → Det er et måle-spørsmål. Norsk er hardt
  pga. dialekter, to målformer og smalbånds telefonlyd. Test NB-Whisper mot
  Azure AI Speech bak samme kontrakt og bruk eval-labelene (`/eval`).
- **«Er dette ekte AI eller bare regler?»** → Offline-demoen bruker en
  deterministisk mock så den alltid er grønn. Med `LLM_BACKEND=anthropic` eller
  `azure-openai` (+ nøkkel) kjører ekte LLM bak *samme* kontrakt — UI-et endrer
  seg ikke.
- **«Hvor er personvernet?»** → PII-maskering hører hjemme i STT-laget rett etter
  transkripsjon, før tekst lagres eller sendes til LLM. STT kan kjøres lokalt så
  lyd aldri forlater huset. Se README «Produksjon» + `docs/arkitektur.md`.
