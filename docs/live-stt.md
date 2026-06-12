# Live STT — de to tale-til-tekst-veiene

Demoen har to måter å gjøre om norsk tale til tekst på. De løser samme oppgave,
men har ulik personvernsprofil og ulikt bruksområde. Dette dokumentet forklarer
forskjellen, når man bruker hvilken, og hvorfor norsk telefonlyd er den
vanskelige delen.

## Vei 1 — Nettleser Web Speech API (`/live`)

Siden `/live` bruker nettleserens innebygde **Web Speech API**
(`SpeechRecognition`, satt til `nb-NO`, `continuous`, `interimResults`).
Talegjenkjenningen skjer på klient-siden: du trykker «Start opptak», snakker, og
teksten kommer fram live mens du snakker. Når du stopper kan teksten sendes til
`POST /analyze-text` og hele AI-analysen (sammendrag, sentiment, scorecard,
flagg, coaching) vises i samme side.

- **Rask og live.** Tekst dukker opp mens du snakker, null oppsett, ingen
  nøkler, ingen modell som må lastes ned.
- **Personvern: nei for ekte kundedata.** Web Speech API i Chrome sender lyden
  til Googles servere for gjenkjenning. Det er greit for en demo eller intern
  test, men IKKE for sensitive ekte kundesamtaler — lyden forlater huset og går
  til en tredjepart utenfor din kontroll.
- **Krav:** Chrome eller Edge (Web Speech API støttes ikke i alle nettlesere),
  mikrofon, og at siden kjøres fra `localhost` eller over HTTPS (nettleseren
  gir ikke mikrofon-tilgang på usikret `http://` mot en ekstern host).
- **Fallback:** nettlesere uten Web Speech API får et tekstfelt der man kan lime
  inn eller skrive en samtale og analysere den med samme AI. Demoen virker
  dermed alltid, også uten talegjenkjenning.

Bruk denne til: demo foran kunde, intern utprøving, å vise flyten
tale → tekst → analyse uten oppsett.

## Vei 2 — Backend-STT (`POST /transcribe`)

Den private veien. `POST /transcribe` tar imot en opplastet lydfil
(mikrofon-opptak fra nettleseren eller en filopplasting), leser bytene og sender
dem gjennom STT-provider-laget (`app/providers/stt.py`). Talegjenkjenningen skjer
på server-siden, under din kontroll — ikke i nettleseren, og ikke hos Google.

To backends bak samme kontrakt:

- **NB-Whisper (self-hosted, lokalt).** Nasjonalbibliotekets norsk-tunede Whisper
  (`STT_BACKEND=nb-whisper`, alternativt `faster-whisper`). Kjører lokalt på egen
  maskin/GPU. Lyden forlater aldri huset — dette er det produksjon ville brukt
  når personvern veier tyngst.
- **Azure AI Speech (`nb-NO`, på Azure).** Driftet norsk talegjenkjenning
  (`STT_BACKEND=azure`, default når `DEPLOY_TARGET=azure`). Skalerer, men dataene
  går til Azure — holdes i EU-region (Sweden Central) under DPA.

Begge svarer med samme `Transcript`-modell som resten av appen, så UI og analyse
bryr seg ikke om hvilken backend som faktisk transkriberte. Akkurat som ellers
i demoen er det **samme `DEPLOY_TARGET`-bryter** som velger backend: `local`
(mock / lokal Whisper) ↔ `azure` (Azure AI Speech), uten kodeendring.

> Merk: i offline-demoen er aktiv STT-backend `mock` (ferdige transkript). Da
> svarer `/transcribe` 200 med et placeholder-transkript og et `note`-felt som
> forklarer at man må sette `STT_BACKEND=nb-whisper` / `faster-whisper` / `azure`
> for ekte transkripsjon av den opplastede lyden. Slik knekker demoen aldri.

Bruk denne til: produksjon, og alt som rører ekte kundelyd.

## Vei → personvern → bruk

| Vei | Hvor skjer STT | Personvern | Bruk |
|---|---|---|---|
| Web Speech API (`/live`) | Klient (nettleser → Googles servere) | Lyd til tredjepart — ikke for ekte kundedata | Demo, intern test, rask gjennomgang av flyten |
| NB-Whisper (`/transcribe`, `STT_BACKEND=nb-whisper`) | Lokal server (self-hosted) | Lyd forlater aldri huset — best personvern | Produksjon når personvern veier tyngst |
| Azure AI Speech (`/transcribe`, `STT_BACKEND=azure`) | Azure (`nb-NO`) | Data i EU-region (Sweden Central) under DPA | Produksjon når man trenger skala/drift |

Kort sagt: `/live` for å *vise* det live, `/transcribe` for å gjøre det *privat*.
Det er det samme provider-laget under — bare ulikt sted gjenkjenningen kjører.

## Hvorfor norsk telefonlyd er det vanskelige

Talegjenkjenning på norsk er hardere enn på engelsk av to grunner som forsterker
hverandre:

- **Dialekter og to målformer.** Norsk har stor dialektvariasjon (uttale,
  ordvalg, tonefall) og både bokmål og nynorsk. En modell trent mest på
  østnorsk standardtale treffer dårligere på f.eks. trøndersk eller nordnorsk.
  NB-Whisper er nettopp tunet på norsk for å redusere dette.
- **Telefonlyd.** Telefoni er smalbånds (typisk 8 kHz), komprimert og ofte med
  støy, overlappende tale og varierende mikrofon-kvalitet. Det fjerner nettopp
  de høyfrekvente detaljene som skiller lyder, så feilraten stiger sammenlignet
  med rent studio-opptak.

Konsekvensen er at valg av STT for norske kundesamtaler bør avgjøres på
**målte tall**, ikke på leverandørens påstander. Demoen legger til rette for
det: kjør NB-Whisper og Azure AI Speech bak samme `Transcript`-kontrakt og mål
resultatet mot eval-fasiten (`data/_labels.json`, se `/eval`), så beslutningen
tas på data — ikke på magefølelse eller innlåsing.
