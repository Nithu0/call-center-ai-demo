"""FastAPI web-UI for call-senter-AI-demoen.

Forside:    liste over demo-samtaler + banner som viser DEPLOY_TARGET + aktive
            providere + "Samme kode — bytt 2 env-variabler → kjører på Azure".
Samtale:    transkript til venstre, AI-analyse til høyre (scorecard, sentiment,
            nøkkelinfo, flagg, oppfølging) + "kjør analyse på nytt"-knapp.

INGEN auth/PII-maskering — dette er en demo. Se README "produksjon" for hvor
auth, PII-maskering, samtykke, audit-logg, kryptering og DPA hører hjemme.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.providers import llm, stt

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="Call-senter AI-demo (Loyalty)")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# Auto-inkluder ALLE feature-rutere i app/routers/ som eksponerer `router`.
# Guardet: kjernen fungerer selv om en modul mangler/feiler.
import pkgutil

import app.routers as _routers_pkg

for _info in pkgutil.iter_modules(_routers_pkg.__path__):
    try:
        _m = __import__(f"app.routers.{_info.name}", fromlist=["router"])
        if hasattr(_m, "router"):
            app.include_router(_m.router)
    except Exception as _exc:  # noqa: BLE001 — demo: aldri la en modul knekke kjernen
        import logging

        logging.getLogger("uvicorn.error").info("ruter '%s' ikke lastet: %s", _info.name, _exc)


def _provider_banner() -> dict:
    """Info som vises i banneret — gjør portabilitets-tesen synlig i UI."""
    return {
        "deploy_target": settings.deploy_target,
        "stt_backend": stt.active_backend(),
        "llm_backend": llm.active_backend(),
        "is_azure": settings.is_azure,
    }


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    samples = stt.list_samples()
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "samples": samples,
            "banner": _provider_banner(),
        },
    )


@app.get("/call/{name}", response_class=HTMLResponse)
def call_detail(request: Request, name: str) -> HTMLResponse:
    try:
        transcript = stt.transcribe(name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Ukjent samtale: {name}")

    analysis = llm.analyze(transcript)
    return templates.TemplateResponse(
        request,
        "call.html",
        {
            "transcript": transcript,
            "analysis": analysis,
            "banner": _provider_banner(),
        },
    )


@app.post("/call/{name}/analyze")
def reanalyze(name: str) -> dict:
    """"Kjør analyse på nytt" — returnerer JSON (brukes av knappen på samtale-siden)."""
    try:
        transcript = stt.transcribe(name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Ukjent samtale: {name}")
    analysis = llm.analyze(transcript)
    return {
        "name": name,
        "banner": _provider_banner(),
        "analysis": analysis.model_dump(),
    }


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok", **_provider_banner()}
