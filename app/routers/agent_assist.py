"""AGENT-ASSIST — live agent-skjerm under en pågående samtale (Loyaltys use case
«real-time agent assist»).

Egen lane (KUN nye filer): denne fila + templates/agent_assist.html. Ingen andre
filer røres.

Siden simulerer hva en agent ser PÅ SKJERMEN MENS SAMTALEN PÅGÅR:

  VENSTRE  — samtalen rulles inn replikk for replikk («▶ Neste replikk» eller
             auto «▶▶ Spill av»). Ingenting er avslørt på forhånd.
  HØYRE    — et sanntids assist-panel som oppdaterer seg etter hvert som
             replikkene kommer:
               · Neste beste handling  (kontekst-forslag)
               · Kunnskaps-svar        (oppleses-info)
               · Compliance-påminnelser (angrerett, samtykke, ID …)
               · Live QA-måler          (fylles når sjekkliste-punkter treffes)

Forslagene er REGELBASERTE (nøkkelord i replikkene) og kjøres KLIENT-SIDE i
JS — deterministisk, ingen LLM-kall, alltid responsivt og offline-trygt. Selve
samtaledataene kommer fra `stt.transcribe(name)` (samme provider-kontrakt som
resten av appen), så ekte transkript ville fungere likt.

Banneret gjenbruker SAMME provider-kontrakt som app/main.py `_provider_banner`.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.providers import llm, stt

BASE_DIR = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter()

# Default-sample: en retention-/salgssamtale gir mange assist-triggere
# (oppsigelse → lojalitetstilbud, samtykke, angrerett, bindingstid …).
DEFAULT_SAMPLE = "retention_oppsigelse"


def _provider_banner() -> dict:
    """Samme banner-kontrakt som app/main.py `_provider_banner` — gjenbrukt her."""
    return {
        "deploy_target": settings.deploy_target,
        "stt_backend": stt.active_backend(),
        "llm_backend": llm.active_backend(),
        "is_azure": settings.is_azure,
    }


def _pick_default(samples: list) -> str:
    """Velg en fornuftig default-samtale hvis DEFAULT_SAMPLE ikke finnes."""
    names = [s.name for s in samples]
    if DEFAULT_SAMPLE in names:
        return DEFAULT_SAMPLE
    # Foretrekk en salgs-/retention-samtale, ellers første tilgjengelige.
    for s in samples:
        if s.call_type == "salg":
            return s.name
    return names[0] if names else DEFAULT_SAMPLE


@router.get("/agent-assist", response_class=HTMLResponse)
def agent_assist(request: Request, name: str | None = None) -> HTMLResponse:
    """Live agent-assist-skjerm. `?name=` velger samtale; default = retention."""
    samples = stt.list_samples()
    chosen = name or _pick_default(samples)

    try:
        transcript = stt.transcribe(chosen)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Ukjent samtale: {chosen}")

    # Send replikkene som ren liste til templaten — JS avslører dem én etter én
    # og kjører de regelbaserte assist-forslagene lokalt.
    turns = [{"speaker": t.speaker, "text": t.text} for t in transcript.turns]

    return templates.TemplateResponse(
        request,
        "agent_assist.html",
        {
            "banner": _provider_banner(),
            "transcript": transcript,
            "turns": turns,
            "samples": samples,
            "chosen": chosen,
        },
    )
