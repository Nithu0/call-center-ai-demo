"""DAGENS SAMTALER — sanntids driftspanel for ledelsen.

Egen lane (KUN nye filer): denne fila + templates/operations.html.
Ingen andre filer røres.

Hva dette gir lederen: følelsen av SKALA + at det "kjører live". Vi tar de 8
demo-samtalene, analyserer hver UNIK sample ÉN gang (cache), og MULTIPLISERER
dem ut til en lang strøm av samtale-rader med varierte agent-navn og
tidsstempler. Variasjonen er DETERMINISTISK (indeks-basert, ikke ekte random),
så feeden er stabil og rask.

  - `GET /operations`        — driftssenter-siden (live-tickende KPI-er + tabell)
  - `GET /operations/feed`   — JSON-liste med samtale-rader (JS poller denne)

Banneret gjenbruker SAMME provider-kontrakt som app/main.py `_provider_banner`.
Hver rad lenker til /call/<sample-navn> (ekte samtale-detalj bak kulissene).
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.providers import llm, stt

BASE_DIR = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter()

# Fiktive agent-navn — driftssenteret "bemannes" av disse. Indeks-rotert per rad.
_AGENTS = (
    "Camilla R.",
    "Jonas H.",
    "Mariam A.",
    "Sondre K.",
    "Linnea T.",
    "Petter S.",
    "Aisha N.",
    "Henrik V.",
    "Ingrid B.",
    "Tobias L.",
    "Selma Ø.",
    "Ahmed F.",
)

# Hvor mange minutter mellom hver simulerte samtale (deterministisk "spacing").
# Vi varierer litt per indeks så strømmen ikke ser mekanisk ut.
_GAP_PATTERN = (3, 5, 2, 7, 4, 6, 3, 8)


def _provider_banner() -> dict:
    """Samme banner-kontrakt som app/main.py `_provider_banner` — gjenbrukt her."""
    return {
        "deploy_target": settings.deploy_target,
        "stt_backend": stt.active_backend(),
        "llm_backend": llm.active_backend(),
        "is_azure": settings.is_azure,
    }


@lru_cache(maxsize=1)
def _analyzed_samples() -> tuple[dict, ...]:
    """Analyser hver UNIK demo-sample ÉN gang og cache resultatet.

    Returnerer en tuple av "base-rader" (de rå AI-tallene per sample), som
    feeden senere multipliserer ut med agent-navn + tidsstempler. lru_cache
    gjør at LLM-analysen kun kjøres én gang per prosess → feeden er rask.
    """
    bases: list[dict] = []
    for transcript in stt.list_samples():
        analysis = llm.analyze(transcript)
        # Robust uthenting (samme mønster som dashboard) — feltene er additive.
        bases.append(
            {
                "name": transcript.name,
                "title": transcript.title or transcript.name,
                "call_type": transcript.call_type,
                "qa_percent": analysis.scorecard.percent,
                "sentiment": getattr(analysis, "sentiment", "nøytral") or "nøytral",
                "churn_risk": getattr(analysis, "churn_risk", "lav") or "lav",
                "call_reason": (getattr(analysis, "call_reason", "") or "")
                or (transcript.title or "Generell henvendelse"),
                "flag_count": len(getattr(analysis, "compliance_flags", []) or []),
            }
        )
    return tuple(bases)


def _vary(base_value: int, idx: int, spread: int) -> int:
    """Deterministisk liten variasjon rundt en base-verdi (ikke ekte random).

    Bruker en hash av indeksen for å spre verdiene jevnt, men reproduserbart.
    """
    h = int(hashlib.md5(str(idx).encode()).hexdigest(), 16)
    delta = (h % (2 * spread + 1)) - spread
    return base_value + delta


def _churn_for(base: str, idx: int) -> str:
    """La churn variere litt rundt sample-basen så strømmen ikke ser klonet ut."""
    h = int(hashlib.md5(f"churn{idx}".encode()).hexdigest(), 16) % 100
    order = ("lav", "middels", "høy")
    pos = order.index(base) if base in order else 0
    # ~15 % sjanse for å skifte ett hakk opp, ~10 % ett hakk ned.
    if h < 15 and pos < 2:
        pos += 1
    elif h < 25 and pos > 0:
        pos -= 1
    return order[pos]


def _build_feed(n: int) -> list[dict]:
    """Bygg `n` samtale-rader ved å multiplisere de cachede base-samplene.

    Tidsstemplene løper BAKOVER fra "nå" (nyeste øverst), med deterministisk
    spacing — så panelet ser ut som en levende logg over dagens samtaler.
    """
    bases = _analyzed_samples()
    if not bases:
        return []

    rows: list[dict] = []
    now = datetime.now()
    cursor = now

    for idx in range(n):
        base = bases[idx % len(bases)]

        # Tid løper bakover; nyeste rad først.
        gap = _GAP_PATTERN[idx % len(_GAP_PATTERN)]
        cursor = cursor - timedelta(minutes=gap)

        qa = max(0, min(100, _vary(base["qa_percent"], idx, 6)))
        churn = _churn_for(base["churn_risk"], idx)

        # Flagg varierer litt: høy churn / negativ sentiment trekker opp flagg.
        flags = base["flag_count"]
        hf = int(hashlib.md5(f"flag{idx}".encode()).hexdigest(), 16) % 100
        if churn == "høy" and hf < 55:
            flags += 1
        elif hf < 12:
            flags += 1

        sentiment = base["sentiment"]
        # Lav QA drar sentimentet ned av og til (deterministisk).
        if qa < 55 and (hf % 3 == 0) and sentiment == "positiv":
            sentiment = "nøytral"

        rows.append(
            {
                "id": idx,
                "time": cursor.strftime("%H:%M"),
                "agent": _AGENTS[idx % len(_AGENTS)],
                "name": base["name"],
                "title": base["title"],
                "call_reason": base["call_reason"],
                "call_type": base["call_type"],
                "qa_percent": qa,
                "sentiment": sentiment,
                "churn_risk": churn,
                "flag_count": flags,
            }
        )

    return rows


def _kpis(rows: list[dict]) -> dict:
    """Aggreger topp-KPI-er over feeden (samtaler i dag, snitt-QA, flagg, churn)."""
    total = len(rows)
    avg_qa = round(sum(r["qa_percent"] for r in rows) / total) if total else 0
    open_flags = sum(r["flag_count"] for r in rows)
    high_churn = sum(1 for r in rows if r["churn_risk"] == "høy")
    neg = sum(1 for r in rows if r["sentiment"] == "negativ")
    return {
        "calls_today": total,
        "avg_qa": avg_qa,
        "open_flags": open_flags,
        "high_churn": high_churn,
        "negative": neg,
    }


@router.get("/operations/feed")
def operations_feed(n: int = 24) -> dict:
    """JSON-feed som tabellen poller hvert par sekund.

    `n` = antall rader. Klampet til [1, 240] så en glipp i query ikke kan
    detonere en analyse-storm (analysen er cachet uansett, men holder feeden lett).
    """
    n = max(1, min(240, n))
    rows = _build_feed(n)
    return {
        "kpis": _kpis(rows),
        "rows": rows,
        "generated_at": datetime.now().strftime("%H:%M:%S"),
    }


@router.get("/operations", response_class=HTMLResponse)
def operations(request: Request) -> HTMLResponse:
    """Driftssenter-siden: live-tickende KPI-er + pollende samtale-tabell."""
    rows = _build_feed(24)
    return templates.TemplateResponse(
        request,
        "operations.html",
        {
            "banner": _provider_banner(),
            "kpis": _kpis(rows),
            "rows": rows,
        },
    )
