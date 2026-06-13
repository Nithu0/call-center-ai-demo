"""Arkitektur — ærlig "slik henger systemet sammen, ledd for ledd".

Denne siden skjuler IKKE kompleksiteten. For hvert ledd i pipeline-en vises:
hva det er, hvor det kjører, hva det krever, og den ærlige avveiingen mellom
en enkel sky-vei (forutsigbar kostnad, rask) og en selvhostet vei (kompleks,
men full kontroll). Mål: at en leder/teknolog faktisk forstår hva som kreves.
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


@router.get("/arkitektur", response_class=HTMLResponse)
def arkitektur(request: Request) -> HTMLResponse:
    banner = {
        "deploy_target": settings.deploy_target,
        "stt_backend": stt.active_backend(),
        "llm_backend": llm.active_backend(),
        "is_azure": settings.is_azure,
    }
    return templates.TemplateResponse(request, "arkitektur.html", {"banner": banner})
