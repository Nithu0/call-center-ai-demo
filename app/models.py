"""Pydantic-modeller for transkript og AI-analyse.

`Analysis` er kontrakten Loyalty bryr seg om: sammendrag, sentiment,
QA-scorecard, nøkkelinfo, compliance-flagg og foreslått oppfølging.
Både mock-LLM og ekte LLM-backends fyller SAMME modell — UI-et bryr seg
ikke om hvilken backend som produserte den.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, computed_field

Sentiment = Literal["positiv", "nøytral", "negativ"]
CallType = Literal["salg", "kundeservice", "ukjent"]


class Turn(BaseModel):
    """Én replikk i samtalen."""

    speaker: Literal["agent", "kunde"]
    text: str


class Transcript(BaseModel):
    """Resultat fra STT-laget (eller forhåndslagret demo-transkript)."""

    name: str = Field(description="Sample-navn / samtale-id")
    call_type: CallType = "ukjent"
    title: str = ""
    turns: list[Turn] = Field(default_factory=list)

    @property
    def full_text(self) -> str:
        return "\n".join(f"{t.speaker}: {t.text}" for t in self.turns)


class ScorecardItem(BaseModel):
    """Ett punkt i QA-sjekklisten."""

    key: str
    label: str
    score: int = Field(ge=0, le=1)           # 0 eller 1
    evidence: str = ""                         # kort begrunnelse


class Scorecard(BaseModel):
    """QA-scorecard mot Loyaltys sjekkliste."""

    items: list[ScorecardItem] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total(self) -> int:
        return sum(i.score for i in self.items)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def max_score(self) -> int:
        return len(self.items)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def percent(self) -> int:
        if not self.items:
            return 0
        return round(100 * self.total / self.max_score)


class KeyInfo(BaseModel):
    """Ekstrahert nøkkelinfo."""

    intent: str = ""                 # kundens intensjon
    product: str = ""                # produkt/tjeneste nevnt
    outcome: str = ""                # utfall
    next_step: str = ""              # neste steg


class Analysis(BaseModel):
    """Komplett AI-analyse av én samtale."""

    summary: str = ""                          # 2-3 setninger
    sentiment: Sentiment = "nøytral"
    scorecard: Scorecard = Field(default_factory=Scorecard)
    key_info: KeyInfo = Field(default_factory=KeyInfo)
    compliance_flags: list[str] = Field(default_factory=list)
    follow_up: list[str] = Field(default_factory=list)

    # --- Utvidet analyse (additivt — defaults, så eldre kode ikke knekker) --- #
    call_reason: str = ""                      # klassifisert henvendelsesårsak
    churn_risk: Literal["lav", "middels", "høy"] = "lav"
    coaching_tips: list[str] = Field(default_factory=list)   # coaching til agenten
    script_adherence: int = Field(default=0, ge=0, le=100)   # manus/compliance %
    crm_export: dict = Field(default_factory=dict)           # CRM-klar JSON

    # Sporbarhet — hvilken backend produserte denne analysen
    backend: str = "mock"
