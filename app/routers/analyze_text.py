"""Fritekst-analyse-ruter — analyser en VILKÅRLIG samtale.

`POST /analyze-text` tar imot rå samtaletekst (fra live-STT, et innlimt
utdrag, eller hvilken som helst kilde — ikke bare forhåndslagrede demo-
samples), bygger et `Transcript` og kjører den vanlige `llm.analyze()`-
pipelinen. Returnerer både det parsede transkriptet og analysen som JSON.

Tekst-til-turns:
  - Linjer med `agent:`/`kunde:`-prefiks parses til turns med riktig speaker
    (synonymer som `kundeservice`/`customer`/`saksbehandler`/`bruker` mappes
    også til riktig speaker).
  - Ellers: hvis flere linjer, lag én turn pr. linje og alterner speaker
    (starter på agent). Med bare én linje: én turn med alt.

Samme `Analysis`-kontrakt som resten av systemet — UI/integrasjoner bryr
seg ikke om at kilden var fritekst i stedet for et lagret sample.

Egen lane: KUN denne fila. Ingen andre filer røres.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field

from app.models import CallType, Transcript, Turn
from app.providers import llm

router = APIRouter()


class AnalyzeTextRequest(BaseModel):
    """Innkommende fritekst-samtale som skal analyseres."""

    text: str = Field(description="Rå samtaletekst (linjer, evt. med agent:/kunde:-prefiks).")
    call_type: CallType = "ukjent"
    name: str = "live"


# Speaker-prefikser vi gjenkjenner i begynnelsen av en linje (case-insensitivt).
_AGENT_PREFIXES = ("agent", "selger", "saksbehandler", "kundeservice", "support", "rådgiver")
_CUSTOMER_PREFIXES = ("kunde", "customer", "bruker", "innringer", "client")


def _match_prefix(line: str) -> tuple[Literal["agent", "kunde"], str] | None:
    """Returner (speaker, resttekst) hvis linja starter med et kjent prefiks + ':'."""
    if ":" not in line:
        return None
    head, _, rest = line.partition(":")
    label = head.strip().lower()
    if label in _AGENT_PREFIXES:
        return "agent", rest.strip()
    if label in _CUSTOMER_PREFIXES:
        return "kunde", rest.strip()
    return None


def _build_turns(text: str) -> list[Turn]:
    """Bygg turns fra vilkårlig tekst.

    1) Har linjene agent:/kunde:-prefiks -> parse til riktig speaker.
    2) Ellers flere ikke-tomme linjer    -> én turn pr. linje, alterner speaker.
    3) Ellers (én linje)                 -> én turn med hele teksten (agent).
    """
    raw_lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in raw_lines if ln]

    # 1) Prefiks-basert parsing — krever at MINST én linje har et kjent prefiks.
    prefixed = [(_match_prefix(ln), ln) for ln in lines]
    if any(match is not None for match, _ in prefixed):
        turns: list[Turn] = []
        last_speaker: Literal["agent", "kunde"] = "agent"
        for match, ln in prefixed:
            if match is not None:
                speaker, body = match
                last_speaker = speaker
            else:
                # Fortsettelseslinje uten prefiks -> tilskriv forrige speaker.
                speaker, body = last_speaker, ln
            if body:
                turns.append(Turn(speaker=speaker, text=body))
        if turns:
            return turns

    # 2) Flere linjer uten prefiks -> alterner speaker (start på agent).
    if len(lines) > 1:
        return [
            Turn(speaker="agent" if i % 2 == 0 else "kunde", text=ln)
            for i, ln in enumerate(lines)
        ]

    # 3) Én linje (eller én sammenhengende blokk) -> alt i én agent-turn.
    return [Turn(speaker="agent", text=lines[0])]


@router.post("/analyze-text")
def analyze_text(req: AnalyzeTextRequest = Body(...)) -> dict:
    """Analyser en vilkårlig tekst-samtale og returner transkript + analyse."""
    if not req.text or not req.text.strip():
        raise HTTPException(
            status_code=400,
            detail="Tom tekst — send en ikke-tom 'text' med samtalen som skal analyseres.",
        )

    turns = _build_turns(req.text)
    name = req.name.strip() or "live"
    transcript = Transcript(
        name=name,
        call_type=req.call_type,
        title=f"Fritekst-analyse ({name})",
        turns=turns,
    )

    analysis = llm.analyze(transcript)

    return {
        "transcript": transcript.model_dump(),
        "analysis": analysis.model_dump(),
    }
