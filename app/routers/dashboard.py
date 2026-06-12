"""Ledelses-dashboard — voice-of-customer-visning for Loyaltys ledelse.

Kjører AI-analyse på ALLE demo-samtaler og aggregerer på tvers:
  - Snitt QA-score (%) totalt + per samtale (søylegraf, ren CSS).
  - Sentiment-fordeling (positiv/nøytral/negativ).
  - Topp compliance-flagg (frekvens).
  - Henvendelsesårsak-fordeling (call_reason).
  - Churn-risiko-oversikt (antall lav/middels/høy + hvilke samtaler er høy).
  - Agent/samtale-tabell med lenke til /call/<navn>.

Bruker `getattr(analysis, 'felt', default)` for de utvidede feltene slik at
visningen er robust uansett hvilken backend (mock/anthropic/azure) som
produserte analysen, og uansett feltrekkefølge.

Egen lane: denne fila + templates/dashboard.html + static/dashboard.css.
Ingen andre filer røres. Banner gjenbruker SAMME provider-info som app/main.py.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.providers import llm, stt

BASE_DIR = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter()

# Sentiment- og churn-nivåer i fast rekkefølge (for stabil visning + farger).
_SENTIMENTS = ("positiv", "nøytral", "negativ")
_CHURN_LEVELS = ("lav", "middels", "høy")


def _provider_banner() -> dict:
    """Samme banner-kontrakt som app/main.py `_provider_banner` — gjenbrukt her."""
    return {
        "deploy_target": settings.deploy_target,
        "stt_backend": stt.active_backend(),
        "llm_backend": llm.active_backend(),
        "is_azure": settings.is_azure,
    }


def _build_dashboard() -> dict:
    """Analyser alle samtaler og bygg aggregerte ledelses-tall."""
    rows: list[dict] = []
    qa_percents: list[int] = []
    sentiment_counts: Counter = Counter()
    churn_counts: Counter = Counter()
    flag_counts: Counter = Counter()
    reason_counts: Counter = Counter()

    for transcript in stt.list_samples():
        analysis = llm.analyze(transcript)

        # Robust uthenting av utvidede felt (kan mangle / komme i vilkårlig rekkefølge).
        call_reason = getattr(analysis, "call_reason", "") or "Uklassifisert"
        churn_risk = getattr(analysis, "churn_risk", "lav") or "lav"
        compliance_flags = getattr(analysis, "compliance_flags", []) or []
        sentiment = getattr(analysis, "sentiment", "nøytral") or "nøytral"

        qa_percent = analysis.scorecard.percent
        qa_percents.append(qa_percent)
        sentiment_counts[sentiment] += 1
        churn_counts[churn_risk] += 1
        reason_counts[call_reason] += 1
        for flag in compliance_flags:
            flag_counts[flag] += 1

        rows.append(
            {
                "name": transcript.name,
                "title": transcript.title or transcript.name,
                "call_type": transcript.call_type,
                "qa_percent": qa_percent,
                "sentiment": sentiment,
                "churn_risk": churn_risk,
                "call_reason": call_reason,
                "flag_count": len(compliance_flags),
            }
        )

    total_calls = len(rows)
    avg_qa = round(sum(qa_percents) / total_calls) if total_calls else 0

    # Sentiment-fordeling i fast rekkefølge med prosent.
    sentiment_dist = [
        {
            "label": s,
            "count": sentiment_counts.get(s, 0),
            "percent": round(100 * sentiment_counts.get(s, 0) / total_calls) if total_calls else 0,
        }
        for s in _SENTIMENTS
    ]

    # Churn-fordeling i fast rekkefølge.
    churn_dist = [
        {
            "label": c,
            "count": churn_counts.get(c, 0),
            "percent": round(100 * churn_counts.get(c, 0) / total_calls) if total_calls else 0,
        }
        for c in _CHURN_LEVELS
    ]
    high_churn_calls = [r for r in rows if r["churn_risk"] == "høy"]

    # Topp compliance-flagg + årsaks-fordeling, sortert på frekvens.
    top_flags = [
        {"label": label, "count": count} for label, count in flag_counts.most_common()
    ]
    reason_dist = [
        {
            "label": label,
            "count": count,
            "percent": round(100 * count / total_calls) if total_calls else 0,
        }
        for label, count in reason_counts.most_common()
    ]

    return {
        "total_calls": total_calls,
        "avg_qa": avg_qa,
        "rows": rows,
        "sentiment_dist": sentiment_dist,
        "churn_dist": churn_dist,
        "high_churn_calls": high_churn_calls,
        "top_flags": top_flags,
        "reason_dist": reason_dist,
        "total_flags": sum(flag_counts.values()),
    }


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request) -> HTMLResponse:
    data = _build_dashboard()
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"banner": _provider_banner(), **data},
    )
