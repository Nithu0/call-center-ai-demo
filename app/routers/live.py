"""LIVE tale-til-tekst — Loyaltys #1 use case, live i nettleseren.

Egen lane (KUN nye filer): denne fila + templates/live.html + static/live.js
+ static/live.css. Ingen andre filer røres.

Siden bruker nettleserens **Web Speech API** (klient-side STT) for å vise tekst
live mens man snakker (`nb-NO`, `continuous`, `interimResults`). Når opptaket
stoppes kan teksten sendes til `POST /analyze-text` (laget av en annen agent)
og hele AI-analysen (sammendrag, sentiment, scorecard %, flagg, coaching) vises
i samme side.

Fallback: nettlesere uten Web Speech API (ikke-Chrome) får et tekstfelt der man
kan lime inn / skrive en samtale manuelt og likevel analysere — så demoen alltid
virker.

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


@router.get("/live", response_class=HTMLResponse)
def live(request: Request) -> HTMLResponse:
    """Live STT-side: snakk inn en samtale, se teksten live, analyser den."""
    return templates.TemplateResponse(
        request,
        "live.html",
        {"banner": _provider_banner()},
    )
