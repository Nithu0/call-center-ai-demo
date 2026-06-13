"""Backend-selvtest-ruter — GET /status.

Viser en side der man SER hvilke backends (STT + LLM) som faktisk er koblet
opp og klare RETT NÅ, uten å trigge noen ekte (betalte) API-kall.

For hver backend rapporterer vi KUN trygge sjekker:
  - Pakke installert?  via importlib.util.find_spec(...)  (ingen import-kjøring,
    ingen nettverk). mock har ingen pakke → alltid OK.
  - Nøkkel satt?       les os.environ / app.config.settings og vis BARE
    PRESENT/MISSING — ALDRI selve verdien.
  - Status:            "● aktiv" for den valgte backenden, ellers
    "✓ klar" / "⚠ mangler pakke (pip install …)" / "⚠ mangler nøkkel".

Ingen lyd transkriberes, ingen LLM kalles — dette er ren introspeksjon.

Lane: kun denne fila (+ templates/status.html). Ruteren auto-inkluderes av
app/main.py via `router`.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.providers import llm, stt

# status.py ligger i app/routers/ → tre nivåer opp = prosjektrot, der templates/ bor
# (samme katalog som app/main.py bruker for Jinja2Templates).
BASE_DIR = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter()


def _provider_banner() -> dict:
    """Samme banner-info som app/main.py — så header/banner ser likt ut."""
    return {
        "deploy_target": settings.deploy_target,
        "stt_backend": stt.active_backend(),
        "llm_backend": llm.active_backend(),
        "is_azure": settings.is_azure,
    }


def _pkg_installed(module: str) -> bool:
    """True hvis pakken kan importeres — uten å faktisk importere/kjøre den.

    find_spec laster ikke modulen (ingen side-effekter, ingen nettverk). For
    punktum-moduler (azure.cognitiveservices.speech) returnerer den None hvis
    en hvilken som helst del av stien mangler.
    """
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError, ModuleNotFoundError):
        # ImportError: foreldre-pakke finnes ikke. ValueError: rar spec.
        return False


def _key_present(env_name: str) -> bool:
    """PRESENT/MISSING for en env-nøkkel — leser ALDRI ut selve verdien."""
    return bool(os.environ.get(env_name, "").strip())


# --------------------------------------------------------------------------- #
# Backend-katalog. Hver rad er en ren deklarasjon: hvilken pakke + (evt) nøkkel #
# en backend krever. `pkg=None` → ingen pakke trengs (mock).                    #
# `env_key=None` → ingen nøkkel trengs (lokale modeller).                       #
# --------------------------------------------------------------------------- #
_STT_BACKENDS = [
    {
        "id": "mock",
        "label": "mock",
        "pkg": None,
        "pip": None,
        "env_key": None,
        "note": "ferdig demo-tekst, offline — ingen pakke, ingen nøkkel",
    },
    {
        "id": "faster-whisper",
        "label": "faster-whisper",
        "pkg": "faster_whisper",
        "pip": "faster-whisper",
        "env_key": None,
        "note": "lokal Whisper — ingen nøkkel, ingen Azure",
    },
    {
        "id": "nb-whisper",
        "label": "nb-whisper",
        "pkg": "transformers",
        "pip": "transformers torch",
        "env_key": None,
        "note": "Nasjonalbibliotekets norske Whisper — lokal, ingen nøkkel",
    },
    {
        "id": "openai",
        "label": "openai",
        "pkg": "openai",
        "pip": "openai",
        "env_key": "OPENAI_API_KEY",
        "note": "OpenAI Whisper API — krever nøkkel (betalt)",
    },
    {
        "id": "azure",
        "label": "azure",
        "pkg": "azure.cognitiveservices.speech",
        "pip": "azure-cognitiveservices-speech",
        "env_key": "AZURE_SPEECH_KEY",
        "note": "Azure AI Speech (EU) — krever nøkkel (betalt)",
    },
]

_LLM_BACKENDS = [
    {
        "id": "mock",
        "label": "mock",
        "pkg": None,
        "pip": None,
        "env_key": None,
        "note": "regelbasert, deterministisk — ingen pakke, ingen nøkkel",
    },
    {
        "id": "anthropic",
        "label": "anthropic",
        "pkg": "anthropic",
        "pip": "anthropic",
        "env_key": "ANTHROPIC_API_KEY",
        "note": "Claude (Anthropic) — krever nøkkel (betalt)",
    },
    {
        "id": "azure-openai",
        "label": "azure-openai",
        "pkg": "openai",
        "pip": "openai",
        "env_key": "AZURE_OPENAI_KEY",
        "note": "Azure OpenAI (EU) — krever nøkkel + endpoint (betalt)",
    },
]


def _evaluate(backend: dict, active_id: str) -> dict:
    """Avgjør status for én backend-rad — kun trygge sjekker.

    Rekkefølge på status-logikk:
      1. mangler pakke    → kan uansett ikke kjøre
      2. mangler nøkkel   → pakke ok, men ikke konfigurert
      3. klar             → alt på plass
    Den AKTIVE backenden får i tillegg "● aktiv"-flagget (kan være aktiv selv
    om noe mangler — da vises både aktiv-merket og advarselen).
    """
    pkg = backend["pkg"]
    env_key = backend["env_key"]

    pkg_ok = True if pkg is None else _pkg_installed(pkg)
    key_ok = True if env_key is None else _key_present(env_key)

    if not pkg_ok:
        state = "missing_pkg"
        status_text = f"⚠ mangler pakke (pip install {backend['pip']})"
    elif not key_ok:
        state = "missing_key"
        status_text = "⚠ mangler nøkkel"
    else:
        state = "ready"
        status_text = "✓ klar"

    return {
        "id": backend["id"],
        "label": backend["label"],
        "pkg": pkg,
        "pip": backend["pip"],
        "env_key": env_key,
        "note": backend["note"],
        "pkg_ok": pkg_ok,
        "key_ok": key_ok,
        # Vis "—" for backends som ikke trenger pakke/nøkkel.
        "pkg_cell": "—" if pkg is None else ("✓ installert" if pkg_ok else "✗ mangler"),
        "key_cell": "—" if env_key is None else ("PRESENT" if key_ok else "MISSING"),
        "state": state,
        "status_text": status_text,
        "is_active": backend["id"] == active_id,
    }


@router.get("/status", response_class=HTMLResponse)
def status_page(request: Request) -> HTMLResponse:
    """Backend-selvtest: hva er faktisk koblet opp og klart — uten ekte kall."""
    stt_active = stt.active_backend()
    llm_active = llm.active_backend()

    stt_rows = [_evaluate(b, stt_active) for b in _STT_BACKENDS]
    llm_rows = [_evaluate(b, llm_active) for b in _LLM_BACKENDS]

    # Er den aktive backenden faktisk klar? (pakke + nøkkel på plass)
    stt_active_row = next((r for r in stt_rows if r["is_active"]), None)
    llm_active_row = next((r for r in llm_rows if r["is_active"]), None)

    return templates.TemplateResponse(
        request,
        "status.html",
        {
            "banner": _provider_banner(),
            "stt_rows": stt_rows,
            "llm_rows": llm_rows,
            "stt_active": stt_active,
            "llm_active": llm_active,
            "stt_active_row": stt_active_row,
            "llm_active_row": llm_active_row,
            "supports_audio": stt.supports_audio(),
            "is_azure": settings.is_azure,
        },
    )
