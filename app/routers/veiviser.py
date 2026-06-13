"""Veiviser — interaktiv "velg riktig oppsett"-hjelper.

Brukeren svarer på noen enkle spørsmål (datasensitivitet, volum, eie vs sky,
norsk-krav, tempo), og siden anbefaler LIVE (klient-side JS) hvilken STT- og
analyse-plattform + hvor det bør bygges (lokal server / Azure / sky-API), med
begrunnelse og ferdig `.env`. Ingen backend-logikk — all anbefaling skjer i
nettleseren slik at det oppdateres umiddelbart.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.providers import llm, stt

router = APIRouter()
BASE_DIR = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def _banner() -> dict:
    return {
        "deploy_target": settings.deploy_target,
        "stt_backend": stt.active_backend(),
        "llm_backend": llm.active_backend(),
        "is_azure": settings.is_azure,
    }


@router.get("/veiviser", response_class=HTMLResponse)
def veiviser(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "veiviser.html", {"banner": _banner()})
