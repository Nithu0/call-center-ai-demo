"""Live salgssamtale — DU blir ringt opp av AI-agenten.  GET /samtale

Interaktiv demo: AI-agenten («Sondre» fra TrygHjem Sikkerhet) introduserer seg
og prøver å selge en boligalarm. DU spiller kunden og svarer med stemmen din
(nettleserens Web Speech API, nb-NO). Hver gang du svarer:

  1. agenten hører deg  (STT i nettleseren),
  2. agenten svarer      (manus-policy som reagerer på det du sier),
  3. agenten SNAKKER      (ElevenLabs TTS — fallback: nettleserens egen tale),
  4. samtalen analyseres LIVE (gjenbruker `llm.analyze` — samme motor som resten).

Egen lane: KUN denne fila + templates/samtale.html. Ruteren auto-inkluderes.

Hvorfor manus-policy og ikke en stor LLM for agent-replikkene? Robusthet: en
live-demo foran folk skal ALDRI henge på et eksternt kall. Policyen reagerer på
kundens signaler (pris, binding, nøling, avvisning, interesse) og er 100 %
forklarbar — du ser nøyaktig hvorfor agenten sier det den sier. Har du en
LLM-nøkkel, gjør analyse-laget allerede ekte LLM når LLM_BACKEND er satt.
"""
from __future__ import annotations

import base64
import os
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.models import Transcript, Turn
from app.providers import llm, stt, tts

BASE_DIR = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter()


def _provider_banner() -> dict:
    return {
        "deploy_target": settings.deploy_target,
        "stt_backend": stt.active_backend(),
        "llm_backend": llm.active_backend(),
        "is_azure": settings.is_azure,
    }


# --------------------------------------------------------------------------- #
# Kundesignal — hva kunden nettopp uttrykte. Forklarbar nøkkelord-deteksjon.    #
# Rekkefølgen er prioritert: avvisning slår pris slår binding osv.              #
# --------------------------------------------------------------------------- #
_SIGNALS: list[tuple[str, tuple[str, ...]]] = [
    ("avvisning", ("ikke interessert", "nei takk", "legg på", "ikke ring",
                   "fjern meg", "har alarm", "har allerede", "ikke aktuelt", "slutt")),
    ("pris",      ("dyrt", "pris", "koster", "råd", "billig", "rabatt", "hva blir", "for mye")),
    ("binding",   ("binding", "bindingstid", "oppsig", "angre", "hvor lenge", "låst", "forplikt")),
    ("nøling",    ("tenke", "diskutere", "kone", "mann", "samboer", "vurdere", "senere",
                   "ringe tilbake", "vet ikke", "usikker", "komme tilbake")),
    ("interesse", ("ja", "interessant", "høres bra", "greit", "kan tenke", "absolutt",
                   "gjerne", "ok", "spennende", "fortell", "hvordan funker")),
]

_SIGNAL_LABEL = {
    "start":     ("Samtalestart", "Åpne, bygg kontakt, kartlegg behov"),
    "avvisning": ("Avvisning", "Én myk gjenvinning — så respekter et nei"),
    "pris":      ("Pris-innvending", "Forsvar verdi: forsikringsrabatt + gratis montering"),
    "binding":   ("Spørsmål om vilkår", "Svar ærlig på binding + angrerett, bygg trygghet"),
    "nøling":    ("Nøling / utsettelse", "Tilby skriftlig tilbud + avtal oppfølging"),
    "interesse": ("Kjøpssignal", "Driv mot lukking: tilbud / befaring"),
    "ukjent":    ("Uklart", "Still ett avklarende behovsspørsmål"),
}


def _classify_signal(text: str) -> str:
    t = (text or "").lower()
    if not t.strip():
        return "start"
    for label, kws in _SIGNALS:
        if any(k in t for k in kws):
            return label
    return "ukjent"


# --------------------------------------------------------------------------- #
# Agent-policy — hva agenten svarer, gitt steg + kundesignal. Korte linjer      #
# (godt for TTS). Returnerer (tekst, done).                                     #
# --------------------------------------------------------------------------- #
_INTRO = (
    "Hei, du snakker med Sondre fra TrygHjem Sikkerhet — håper jeg ikke ringer "
    "helt ubeleilig? Grunnen til at jeg tar kontakt er at vi kjører en kampanje "
    "på boligalarm i nabolaget ditt denne uka. Har du noen form for alarm i dag?"
)


def _agent_reply(history: list[dict]) -> tuple[str, bool]:
    agent_turns = [t for t in history if t.get("speaker") == "agent"]
    n = len(agent_turns)
    if n == 0:
        return _INTRO, False

    # siste kunde-replikk
    last_cust = ""
    for t in reversed(history):
        if t.get("speaker") == "kunde":
            last_cust = t.get("text", "")
            break
    sig = _classify_signal(last_cust)

    # har vi allerede forsøkt å snu en avvisning?
    already_rebutted = any("respekterer" in t.get("text", "").lower()
                           or "skal være rask" in t.get("text", "").lower()
                           for t in agent_turns)

    if sig == "avvisning":
        if already_rebutted or n >= 4:
            return ("Helt greit — jeg respekterer det, og skal ikke oppta mer av "
                    "tiden din. Ha en fortsatt fin dag, og ta kontakt om det blir "
                    "aktuelt senere!"), True
        return ("Det skjønner jeg godt, og jeg skal være rask. Mange tenker akkurat "
                "det — helt til de hører at monteringen er gratis nå i kampanjen. "
                "Får jeg stille ett kjapt spørsmål: bor du i enebolig eller leilighet?"), False

    if sig == "pris":
        return ("Jeg forstår at pris betyr noe. Komplettpakken koster 399 kroner "
                "i måneden, men mange får rundt femten prosent avslag på "
                "husforsikringen fordi alarm senker risikoen — så netto blir det "
                "rimeligere enn folk tror. Skal jeg regne på hva det blir for deg?"), False

    if sig == "binding":
        return ("Godt spørsmål. Det er tolv måneders bindingstid, deretter løpende "
                "med én måneds oppsigelse — og full angrerett i fjorten dager etter "
                "montering. Føles det tryggere?"), False

    if sig == "nøling":
        return ("Det er helt forståelig at du vil tenke på det. La oss gjøre det "
                "enkelt: jeg sender deg tilbudet skriftlig på e-post, og ringer deg "
                "tilbake på torsdag når du har fått snakket med familien. Passer det?"), False

    if sig == "interesse":
        if n >= 3:
            return ("Helt supert! Da noterer jeg deg for en gratis og uforpliktende "
                    "befaring, og sender bekreftelsen på e-post med en gang. Takk for "
                    "praten — du kommer til å sove godt med dette på plass!"), True
        return ("Så bra! Da vil jeg anbefale komplettpakken vår: innbruddsalarm, "
                "røykvarsler og kameraovervåking med direkte vakthold. Den passer "
                "spesielt godt for en bolig som din. Skal jeg sette opp et tilbud?"), False

    # ukjent → behovsspørsmål, eller mild lukking hvis samtalen drar ut
    if n >= 5:
        return ("Jeg skal ikke holde deg lenge. Skal jeg sende deg et uforpliktende "
                "tilbud på e-post, så kan du se i fred og ro?"), True
    return ("Skjønner. Bare så jeg anbefaler riktig — er det innbrudd, brann, eller "
            "det å kunne sjekke hjemmet på mobilen som er viktigst for deg?"), False


# --------------------------------------------------------------------------- #
# Sanntidsanalyse — gjenbruker den EKTE analyse-motoren på samtalen så langt.   #
# --------------------------------------------------------------------------- #
def _live_analysis(history: list[dict], sig: str) -> dict:
    label, recommendation = _SIGNAL_LABEL.get(sig, _SIGNAL_LABEL["ukjent"])
    out: dict = {
        "signal": label,
        "recommendation": recommendation,
        "sentiment": "nøytral",
        "next_step": "",
        "follow_up": [],
        "coaching": [],
        "summary": "",
        "backend": llm.active_backend(),
    }
    has_customer = any(t.get("speaker") == "kunde" for t in history)
    if not has_customer:
        out["how"] = _how_text(out["backend"])
        return out
    try:
        tr = Transcript(
            name="live",
            call_type="salg",
            title="Live salgssamtale",
            turns=[Turn(speaker=t["speaker"], text=t["text"]) for t in history
                   if t.get("text", "").strip()],
        )
        a = llm.analyze(tr)
        out.update(
            sentiment=a.sentiment,
            next_step=a.key_info.next_step,
            follow_up=a.follow_up[:3],
            coaching=a.coaching_tips[:3],
            summary=a.summary,
            backend=a.backend,
        )
    except Exception:
        pass  # analyse skal aldri velte samtalen
    out["how"] = _how_text(out["backend"])
    return out


def _how_text(backend: str) -> str:
    if backend == "mock":
        return ("Regelbasert sanntidsanalyse: kjenner igjen nøkkelord (pris, binding, "
                "nøling, avvisning, kjøpssignal) + samtaleflyt. Ingen ekstern AI — "
                "alt kjøres lokalt og er fullt forklarbart.")
    return f"LLM-analyse via «{backend}» — samme motor som rapport-siden bruker."


# --------------------------------------------------------------------------- #
# Ruter                                                                         #
# --------------------------------------------------------------------------- #
# Public ElevenLabs ConvAI-agent (sikkerhet/signed-url kan legges til senere).
ELEVENLABS_AGENT_ID = os.environ.get(
    "ELEVENLABS_AGENT_ID", "agent_9801kvt5ws04e3araztj70bktww2"
)


@router.get("/samtale", response_class=HTMLResponse)
def samtale_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "samtale.html",
        {
            "banner": _provider_banner(),
            "tts_backend": tts.active_backend(),
            "agent_id": ELEVENLABS_AGENT_ID,
        },
    )


@router.post("/samtale/agent")
async def samtale_agent(request: Request) -> JSONResponse:
    """Ett agent-trekk: motta samtalehistorikk → svar + lyd + live-analyse."""
    body = await request.json()
    history = body.get("history") or []
    # rens
    history = [
        {"speaker": t.get("speaker"), "text": (t.get("text") or "").strip()}
        for t in history
        if t.get("speaker") in ("agent", "kunde")
    ]

    text, done = _agent_reply(history)

    # signal for analyse-panelet = kundens SISTE replikk
    last_cust = next((t["text"] for t in reversed(history)
                      if t["speaker"] == "kunde"), "")
    sig = _classify_signal(last_cust)
    analysis = _live_analysis(history, sig)

    audio = tts.synthesize(text, speaker="agent")
    audio_b64 = base64.b64encode(audio).decode("ascii") if audio else None

    return JSONResponse({
        "text": text,
        "done": done,
        "audio_b64": audio_b64,           # None → frontend bruker browser-tale
        "tts_backend": tts.active_backend(),
        "analysis": analysis,
    })
