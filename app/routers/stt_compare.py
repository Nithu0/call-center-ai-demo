"""STT-plattformvalg — Loyaltys EKSPLISITTE #1-oppgave, evaluert profesjonelt.

Egen lane (KUN nye filer): denne fila + templates/stt_compare.html.
Ingen andre filer røres.

Hvorfor denne siden finnes
--------------------------
Loyaltys nummer-én-oppgave er å VELGE STT-plattform for norske call-senter-
samtaler. Denne siden viser at valget er gjort som en ingeniør gjør det:
en kriterie-matrise over de reelle alternativene (NB-Whisper self-hosted,
Whisper large-v3, Azure AI Speech, Google STT, Deepgram), fargekodet på
norsk-nøyaktighet, kostnad, latens, personvern, diarisering og integrasjon —
pluss en tydelig anbefaling knyttet til DEPLOY_TARGET-tesen (samme kode kjører
lokal NB-Whisper ↔ Azure Speech, bytt to env-variabler).

Tallene er ESTIMATER (tydelig merket i UI) — poenget er rammeverket for valget,
ikke en benchmark vi later som er målt.

Banneret gjenbruker SAMME provider-kontrakt som app/main.py `_provider_banner`.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.providers import llm, stt

BASE_DIR = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter()


def _provider_banner() -> dict:
    """Samme banner-kontrakt som app/main.py `_provider_banner` — gjenbrukt her."""
    return {
        "deploy_target": settings.deploy_target,
        "stt_backend": stt.active_backend(),
        "llm_backend": llm.active_backend(),
        "is_azure": settings.is_azure,
    }


# --------------------------------------------------------------------------- #
# Kriterie-matrisen.                                                           #
#                                                                             #
# `rating` ∈ {"god", "middels", "dårlig"} → fargekoding i UI.                  #
# `note` er den korte begrunnelsen som vises i cella.                          #
# ALLE tall er ESTIMATER (merket i UI) — rammeverk, ikke målt benchmark.       #
# --------------------------------------------------------------------------- #
def _cell(rating: str, note: str) -> dict:
    return {"rating": rating, "note": note}


# Kriteriene som kolonner — rekkefølge styrer tabell-rekkefølgen.
CRITERIA: list[dict] = [
    {"key": "norsk", "label": "Norsk-nøyaktighet", "sub": "dialekt + telefonlyd"},
    {"key": "kostnad", "label": "Kostnad ved volum", "sub": "estimat, mange timer/mnd"},
    {"key": "latens", "label": "Latens", "sub": "sanntid vs. batch"},
    {"key": "personvern", "label": "Personvern", "sub": "on-prem/EU vs. US"},
    {"key": "diarisering", "label": "Diarisering", "sub": "agent vs. kunde"},
    {"key": "integrasjon", "label": "Integrasjon", "sub": "innsats i denne koden"},
]

# Radene — ett alternativ hver. `backend` matcher STT_BACKEND-verdiene der det
# finnes en faktisk implementasjon i app/providers/stt.py (markeres i UI).
OPTIONS: list[dict] = [
    {
        "name": "NB-Whisper (self-hosted)",
        "vendor": "Nasjonalbiblioteket · norsk-tunet Whisper",
        "backend": "nb-whisper",
        "hosting": "On-prem / egen GPU (EU)",
        "tagline": "Best norsk + full datakontroll — men du drifter GPU selv.",
        "cells": {
            "norsk": _cell(
                "god",
                "Trent på norsk tale (bokmål + nynorsk + dialekter). Klart best "
                "på dialekt og norsk-spesifikke ord av alternativene.",
            ),
            "kostnad": _cell(
                "god",
                "Ingen per-minutt-avgift. Kun GPU-drift. Marginalkostnad ~0 ved "
                "høyt volum — billigst når timene blir mange.",
            ),
            "latens": _cell(
                "middels",
                "Batch raskt på GPU. Ekte sanntid krever streaming-oppsett + "
                "varm modell; mer jobb enn en managed sanntids-API.",
            ),
            "personvern": _cell(
                "god",
                "Lyden forlater aldri infrastrukturen. On-prem/EU — enklest mulig "
                "GDPR/databehandler-historie for sensitive samtaler.",
            ),
            "diarisering": _cell(
                "middels",
                "Whisper gir ikke taler-id selv. Krever eget diariserings-steg "
                "(f.eks. pyannote) — mulig, men ekstra komponent å drifte.",
            ),
            "integrasjon": _cell(
                "god",
                "Allerede wiret: STT_BACKEND=nb-whisper i providers/stt.py "
                "(import-guardet transformers-pipeline).",
            ),
        },
    },
    {
        "name": "Whisper large-v3 (self-hosted)",
        "vendor": "OpenAI open-weights · faster-whisper",
        "backend": "faster-whisper",
        "hosting": "On-prem / egen GPU (EU)",
        "tagline": "Sterk generell modell, self-hosted — men ikke norsk-tunet.",
        "cells": {
            "norsk": _cell(
                "middels",
                "God på standard bokmål, svakere på brede dialekter og "
                "telefonlyd enn den norsk-tunede NB-Whisper.",
            ),
            "kostnad": _cell(
                "god",
                "Open-weights, ingen lisens/per-minutt. Kun GPU-drift — samme "
                "kostnadsprofil som NB-Whisper.",
            ),
            "latens": _cell(
                "middels",
                "large-v3 er tung; god batch-latens på GPU, men sanntid krever "
                "mindre modell eller streaming-oppsett.",
            ),
            "personvern": _cell(
                "god",
                "Self-hosted — lyden blir på egen infrastruktur (EU/on-prem).",
            ),
            "diarisering": _cell(
                "middels",
                "Samme som NB-Whisper: trenger eget diariserings-steg for "
                "agent/kunde-separasjon.",
            ),
            "integrasjon": _cell(
                "god",
                "Allerede wiret: STT_BACKEND=faster-whisper i providers/stt.py.",
            ),
        },
    },
    {
        "name": "Azure AI Speech",
        "vendor": "Microsoft · managed",
        "backend": "azure",
        "hosting": "Managed · EU-region mulig (Sweden Central)",
        "tagline": "Managed, nb-NO + innebygd diarisering, EU-region — pilot-vennlig.",
        "cells": {
            "norsk": _cell(
                "god",
                "Dedikert nb-NO-modell, solid på telefonlyd. Litt bak NB-Whisper "
                "på de breieste dialektene, men sterk og driftsfri.",
            ),
            "kostnad": _cell(
                "middels",
                "Per-time/per-minutt-pris. Helt grei i pilot; blir den dyreste "
                "linja når volumet vokser (derav flytt-til-self-hosted-planen).",
            ),
            "latens": _cell(
                "god",
                "Ekte sanntids-streaming-API ut av boksen — ingen egen "
                "infrastruktur å varme opp.",
            ),
            "personvern": _cell(
                "middels",
                "Kan låses til EU-region (Sweden Central) + DPA. Bedre enn US-"
                "default, men data går likevel til en ekstern databehandler.",
            ),
            "diarisering": _cell(
                "god",
                "ConversationTranscriber gir agent/kunde-separasjon innebygd — "
                "ingen ekstra komponent.",
            ),
            "integrasjon": _cell(
                "god",
                "Wiret integrasjonspunkt i providers/stt.py (STT_BACKEND=azure). "
                "Hjørnesteinen i DEPLOY_TARGET=azure-tesen.",
            ),
        },
    },
    {
        "name": "Google Speech-to-Text",
        "vendor": "Google Cloud · managed",
        "backend": None,
        "hosting": "Managed · US-tyngdepunkt",
        "tagline": "Moden API, men svakere norsk og US-default personvern.",
        "cells": {
            "norsk": _cell(
                "middels",
                "Støtter no-NO, men merkbart bak Azure/NB-Whisper på dialekt og "
                "norsk telefonlyd i praksis.",
            ),
            "kostnad": _cell(
                "middels",
                "Per-minutt-pris på linje med andre managed. Ingen self-host-"
                "exit, så kostnaden følger volumet hele veien.",
            ),
            "latens": _cell(
                "god",
                "Streaming-API med god sanntids-latens.",
            ),
            "personvern": _cell(
                "dårlig",
                "US-tyngdepunkt. EU-data-residency er mindre rett-fram enn Azures "
                "EU-region — tyngre GDPR-historie for sensitive samtaler.",
            ),
            "diarisering": _cell(
                "god",
                "Innebygd speaker diarization.",
            ),
            "integrasjon": _cell(
                "middels",
                "Ikke wiret i denne koden. Krever ny backend-gren i "
                "providers/stt.py (samme Transcript-kontrakt).",
            ),
        },
    },
    {
        "name": "Deepgram",
        "vendor": "Deepgram · managed (STT-spesialist)",
        "backend": None,
        "hosting": "Managed · US (on-prem/enterprise mulig)",
        "tagline": "Rask + rimelig, men norsk er ikke kjernespråket.",
        "cells": {
            "norsk": _cell(
                "middels",
                "Sterk engelsk-ytelse; norsk støttes, men er ikke der modellen er "
                "best. Risiko på dialekt + telefonlyd.",
            ),
            "kostnad": _cell(
                "god",
                "Blant de billigste managed-API-ene per minutt — attraktiv hvis "
                "norsk-kvaliteten holder for use-caset.",
            ),
            "latens": _cell(
                "god",
                "Bygget for lav-latens sanntid — et av de raskeste alternativene.",
            ),
            "personvern": _cell(
                "middels",
                "US-default. On-prem/enterprise-deploy finnes, men da mister man "
                "managed-enkelheten (nærmer seg self-host-kostnaden).",
            ),
            "diarisering": _cell(
                "god",
                "Innebygd diarisering.",
            ),
            "integrasjon": _cell(
                "middels",
                "Ikke wiret i denne koden. Krever ny backend-gren i "
                "providers/stt.py.",
            ),
        },
    },
]


@router.get("/stt", response_class=HTMLResponse)
def stt_compare(request: Request) -> HTMLResponse:
    """STT-plattformvalg: kriterie-matrise + anbefaling, knyttet til DEPLOY_TARGET."""
    active = stt.active_backend()
    return templates.TemplateResponse(
        request,
        "stt_compare.html",
        {
            "banner": _provider_banner(),
            "criteria": CRITERIA,
            "options": OPTIONS,
            "active_backend": active,
            "supports_audio": stt.supports_audio(),
        },
    )
