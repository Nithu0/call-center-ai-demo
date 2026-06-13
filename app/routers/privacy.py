"""Personvern & ansvarlig-AI-ruter — tillits-siden for Loyalty.

`GET /personvern` samler det IT/ledelse spør om FØR de stoler på AI på ekte
kundedata, på ett rolig, profesjonelt sted:

  - **PII-maskering** med et LIVE før/etter-eksempel (kjører `redact()` på en
    eksempel-tekst med fnr / telefon / e-post — viser maskert resultat + en
    revisjonsvennlig funn-liste). Lenker videre til /redaction.
  - **Databehandling**: lokal (NB-Whisper) / EU (Azure-Norge) vs. US-tjenester
    — samtaleopptak er sensitive persondata, og `DEPLOY_TARGET` styrer HVOR de
    behandles. Tabell: vei → hvor data ligger → egnethet for ekte kundedata.
  - **Menneske-i-loop**: AI lager utkast/forslag, menneske godkjenner alt
    kundevendt.
  - **Sporbarhet**: audit-logg — hvem så hva, når.
  - **Samtykke & DPA**: databehandleravtale før ekte kundedata, sletting/
    retention.
  - **AI-transparens**: forslag vs. handling tydelig adskilt.

Egen lane: denne fila + templates/privacy.html. Ingen andre filer røres.
Banner gjenbruker SAMME provider-kontrakt som app/main.py `_provider_banner`.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app import redaction
from app.config import settings
from app.providers import llm, stt

BASE_DIR = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter()


# Eksempel-tekst for det LIVE PII-eksempelet. Ingen ekte PII — syntetiske
# verdier som dekker fnr / telefon / e-post (+ konto/kort) slik at maskeringen
# blir synlig på tvers av identifikator-typer.
_PII_EKSEMPEL = (
    "Hei, mitt navn er Ola Nordmann. Fødselsnummeret mitt er 01029012345, "
    "telefonen er +47 412 34 567 og e-posten er ola.nordmann@eksempel.no. "
    "Trekk beløpet fra konto 1234.56.78903."
)


def _provider_banner() -> dict:
    """Samme banner-kontrakt som app/main.py `_provider_banner` — gjenbrukt her."""
    return {
        "deploy_target": settings.deploy_target,
        "stt_backend": stt.active_backend(),
        "llm_backend": llm.active_backend(),
        "is_azure": settings.is_azure,
    }


# Databehandlings-matrise: vei → hvor data ligger → egnethet for ekte kundedata.
# `deploy` = DEPLOY_TARGET-verdien som velger denne veien.
_DATA_VEIER = [
    {
        "vei": "Lokalt / on-prem",
        "deploy": "local",
        "stt": "NB-Whisper (norsk, kjører på egen maskin)",
        "llm": "Lokal / selvhostet modell",
        "hvor": "Forlater aldri Loyaltys egne maskiner",
        "jurisdiksjon": "Norge — ingen overføring",
        "egnethet": "høy",
        "egnethet_tekst": "Egnet for sensitive kundedata uten ekstern overføring.",
    },
    {
        "vei": "EU / Azure-Norge",
        "deploy": "azure",
        "stt": "Azure AI Speech (region norwayeast/EU)",
        "llm": "Azure OpenAI (EU-region)",
        "hvor": "Microsoft Azure, datasenter i Norge/EU",
        "jurisdiksjon": "EU/EØS — under GDPR, DPA med Microsoft",
        "egnethet": "høy",
        "egnethet_tekst": "Egnet med signert databehandleravtale (DPA) og EU-region.",
    },
    {
        "vei": "US-tjenester",
        "deploy": "(ikke standard)",
        "stt": "US-baserte API-er",
        "llm": "US-baserte API-er",
        "hvor": "USA — utenfor EØS",
        "jurisdiksjon": "Tredjeland — krever overføringsgrunnlag (SCC m.m.)",
        "egnethet": "lav",
        "egnethet_tekst": "Ikke anbefalt for ekte kundedata uten eget vurderingsgrunnlag.",
    },
]


@router.get("/personvern", response_class=HTMLResponse)
def personvern(request: Request) -> HTMLResponse:
    """Personvern & ansvarlig-AI — tillits-siden, med live PII-eksempel."""
    masked, funn = redaction.redact(_PII_EKSEMPEL)

    return templates.TemplateResponse(
        request,
        "privacy.html",
        {
            "banner": _provider_banner(),
            "pii_original": _PII_EKSEMPEL,
            "pii_masked": masked,
            "pii_funn": funn,
            "data_veier": _DATA_VEIER,
            # Hvilken vei kjører vi akkurat nå (uthevet i tabellen)?
            "aktiv_vei": "azure" if settings.is_azure else "local",
        },
    )
