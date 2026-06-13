"""Guide-side (`/guide`) — «SLIK FUNGERER DEMOEN».

Mål: en LEDER som åpner demoen for første gang skal kunne navigere trygt på
egen hånd — uten teknisk hjelp. Siden gir en kort intro, en nummerert
gjennomgang av funksjonene (hver med «Åpne →»-lenke), en anbefalt 5-minutters
demo-løype for et møte, og en rolig note om lokal↔Azure-portabiliteten.

Egen lane: KUN denne fila + templates/guide.html. Ingen andre filer røres.
Banner gjenbruker SAMME provider-info som app/main.py `_provider_banner`.
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


# Nummerert gjennomgang av funksjonene — hver vises som et eget kort med
# «Åpne →»-lenke. Rekkefølgen er bevisst: det en leder vil se først kommer øverst.
FEATURES = [
    {
        "icon": "🎙️",
        "title": "Live tale-til-tekst",
        "href": "/live",
        "desc": (
            "Snakk inn i mikrofonen, så skrives det du sier ut som tekst i sanntid — "
            "og AI-en analyserer samtalen mens den pågår. Den beste måten å vise "
            "hva løsningen faktisk gjør."
        ),
    },
    {
        "icon": "📊",
        "title": "Dashboard",
        "href": "/dashboard",
        "desc": (
            "Samlet oversikt over alle samtaler: sentiment, henvendelsesårsaker og "
            "kvalitetsscore på tvers. Her ser en leder helheten på sekunder."
        ),
    },
    {
        "icon": "📈",
        "title": "Effekt & ROI",
        "href": "/eval",
        "desc": (
            "Dokumentert effekt — hvor godt AI-en treffer en menneskelig fasit, og "
            "hvor mye tid og kroner den frigjør. Dra i sliderne for å regne på eget volum."
        ),
    },
    {
        "icon": "📋",
        "title": "Leder-rapport",
        "href": "/rapport",
        "desc": (
            "En kort, ferdig oppsummering laget for ledelsen — funn og anbefalinger "
            "samlet på én side, klar til å vise videre."
        ),
    },
    {
        "icon": "🧑‍💼",
        "title": "Agent-assist",
        "href": "/agent-assist",
        "desc": (
            "Hvordan AI-en hjelper kundebehandleren mens samtalen pågår — forslag, "
            "neste steg og påminnelser, slik at den ansatte slipper å huske alt selv."
        ),
    },
    {
        "icon": "🔒",
        "title": "Personvern",
        "href": "/personvern",
        "desc": (
            "Hvordan sensitive opplysninger håndteres og maskeres. Viser at løsningen "
            "tar personvern på alvor — viktig før en pilot settes i drift."
        ),
    },
    {
        "icon": "🎚️",
        "title": "STT-valg",
        "href": "/stt",
        "desc": (
            "Sammenligning av ulike tale-til-tekst-motorer. Lar dere velge den som "
            "passer best på pris, presisjon og hvor dataene skal ligge."
        ),
    },
    {
        "icon": "🔁",
        "title": "Drift",
        "href": "/operations",
        "desc": (
            "Hva som skal til for å sette løsningen i daglig drift — det praktiske rundt "
            "oppsett, oppfølging og videre arbeid."
        ),
    },
]


@router.get("/guide", response_class=HTMLResponse)
def guide_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "guide.html",
        {"banner": _provider_banner(), "features": FEATURES},
    )
