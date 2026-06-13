"""PILOT-RESULTAT / EFFEKT-rapport for Loyaltys ledelse (GET /rapport).

Loyalty vil ha "piloter med DOKUMENTERT EFFEKT". Denne ruten kjører AI-analysen
på ALLE demo-samtaler (`stt.list_samples()` → `llm.analyze`) og bygger en polert,
utskriftsvennlig leder-rapport med ekte aggregerte tall:

  - Executive summary + klar anbefaling (SKALER).
  - Nøkkeltall som store kort: QA-dekning (100 % vs ~1-2 % manuell stikkprøve),
    estimert tid spart (manuell QA ~8 min/samtale → AI sekunder) i timer/årsverk
    ved et gitt volum, antall høy-churn fanget tidlig, snitt-sentiment.
  - Enkle grafer i ren CSS/SVG (QA-fordeling, sentiment, churn-risiko).
  - "Hva AI-en fanget" — konkrete eksempler (compliance-flagg, churn-varsler)
    med lenke til /call/<navn>.
  - Print-vennlig (@media print) + "Skriv ut / lagre som PDF"-knapp.

Alle utledede driftstall er TYDELIG merket som ESTIMATER.

Egen lane: KUN denne fila + templates/rapport.html. Ingen andre filer røres.
Banner gjenbruker SAMME provider-info som app/main.py `_provider_banner`.
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

# Fast rekkefølge for stabil visning + farger.
_SENTIMENTS = ("positiv", "nøytral", "negativ")
_CHURN_LEVELS = ("lav", "middels", "høy")

# --------------------------------------------------------------------------- #
# ESTIMAT-forutsetninger (gjør tid-spart-regnestykket eksplisitt + justerbart) #
# --------------------------------------------------------------------------- #
# Manuell QA: en teamleder lytter gjennom samtalen + fyller scorecard.
MANUAL_QA_MINUTES = 8          # min per samtale, manuell stikkprøve-QA
MANUAL_SAMPLE_RATE = 0.015     # ~1,5 % av samtalene stikkprøves manuelt i dag
# Antatt produksjonsvolum for å skalere demoen til et leder-relevant tall.
ASSUMED_MONTHLY_VOLUME = 20_000   # samtaler/mnd (ett mellomstort team/konto)
WORK_HOURS_PER_FTE_YEAR = 1_695   # SSB-nær normal: ~37,5t/uke minus ferie/helligdag


def _provider_banner() -> dict:
    """Samme banner-kontrakt som app/main.py `_provider_banner` — gjenbrukt her."""
    return {
        "deploy_target": settings.deploy_target,
        "stt_backend": stt.active_backend(),
        "llm_backend": llm.active_backend(),
        "is_azure": settings.is_azure,
    }


def _build_report() -> dict:
    """Kjør AI-analysen på alle samtaler og bygg ledelses-tallene for rapporten."""
    rows: list[dict] = []
    qa_percents: list[int] = []
    sentiment_counts: Counter = Counter()
    churn_counts: Counter = Counter()
    flag_counts: Counter = Counter()

    # Konkrete funn AI-en fanget (for "Hva AI-en fanget"-seksjonen).
    churn_catches: list[dict] = []        # høy churn-risiko fanget tidlig
    compliance_catches: list[dict] = []   # samtaler med compliance-avvik

    for transcript in stt.list_samples():
        analysis = llm.analyze(transcript)

        qa_percent = analysis.scorecard.percent
        churn_risk = getattr(analysis, "churn_risk", "lav") or "lav"
        sentiment = getattr(analysis, "sentiment", "nøytral") or "nøytral"
        flags = list(getattr(analysis, "compliance_flags", []) or [])
        call_reason = getattr(analysis, "call_reason", "") or "Uklassifisert"

        qa_percents.append(qa_percent)
        sentiment_counts[sentiment] += 1
        churn_counts[churn_risk] += 1
        for flag in flags:
            flag_counts[flag] += 1

        row = {
            "name": transcript.name,
            "title": transcript.title or transcript.name,
            "call_type": transcript.call_type,
            "qa_percent": qa_percent,
            "sentiment": sentiment,
            "churn_risk": churn_risk,
            "call_reason": call_reason,
            "flags": flags,
        }
        rows.append(row)

        if churn_risk == "høy":
            churn_catches.append(
                {
                    "name": transcript.name,
                    "title": transcript.title or transcript.name,
                    "call_reason": call_reason,
                    "sentiment": sentiment,
                }
            )
        if flags:
            compliance_catches.append(
                {
                    "name": transcript.name,
                    "title": transcript.title or transcript.name,
                    "flags": flags,
                    "qa_percent": qa_percent,
                }
            )

    total_calls = len(rows)
    avg_qa = round(sum(qa_percents) / total_calls) if total_calls else 0

    # --- Fordelinger (fast rekkefølge, med prosent) --------------------------- #
    def _dist(counts: Counter, order: tuple[str, ...]) -> list[dict]:
        return [
            {
                "label": lvl,
                "count": counts.get(lvl, 0),
                "percent": round(100 * counts.get(lvl, 0) / total_calls) if total_calls else 0,
            }
            for lvl in order
        ]

    sentiment_dist = _dist(sentiment_counts, _SENTIMENTS)
    churn_dist = _dist(churn_counts, _CHURN_LEVELS)

    # QA-fordeling i grove bånd (lett å lese for ledelsen).
    qa_bands = [
        {"label": "Sterk (80–100 %)", "key": "strong", "count": sum(1 for p in qa_percents if p >= 80)},
        {"label": "Middels (50–79 %)", "key": "mid", "count": sum(1 for p in qa_percents if 50 <= p < 80)},
        {"label": "Svak (under 50 %)", "key": "weak", "count": sum(1 for p in qa_percents if p < 50)},
    ]
    for b in qa_bands:
        b["percent"] = round(100 * b["count"] / total_calls) if total_calls else 0

    top_flags = [
        {"label": label, "count": count} for label, count in flag_counts.most_common()
    ]

    high_churn = churn_counts.get("høy", 0)
    high_churn_share = round(100 * high_churn / total_calls) if total_calls else 0

    # --- ESTIMAT: tid spart ved AI-QA på 100 % vs manuell stikkprøve ---------- #
    # Demoen kjørte 100 % QA-dekning på alle samtaler. Manuell QA stikkprøver
    # bare ~1,5 % i dag. Vi viser BÅDE den direkte besparelsen på dagens
    # stikkprøve OG hva 100 % manuell QA ville kostet (det AI-en nå dekker gratis).
    minutes_per_call = MANUAL_QA_MINUTES
    # 1) Hva 100 % manuell QA ville krevd på antatt månedsvolum (det AI dekker nå):
    full_manual_hours_month = round(ASSUMED_MONTHLY_VOLUME * minutes_per_call / 60)
    full_manual_hours_year = full_manual_hours_month * 12
    full_manual_fte = round(full_manual_hours_year / WORK_HOURS_PER_FTE_YEAR, 1)
    # 2) Dekningsgap: i dag QA-es ~1,5 %; AI gir 100 %.
    coverage_now_pct = round(MANUAL_SAMPLE_RATE * 100, 1)

    estimates = {
        "manual_qa_minutes": minutes_per_call,
        "manual_sample_pct": coverage_now_pct,
        "assumed_monthly_volume": ASSUMED_MONTHLY_VOLUME,
        "hours_per_fte_year": WORK_HOURS_PER_FTE_YEAR,
        "full_manual_hours_month": full_manual_hours_month,
        "full_manual_hours_year": full_manual_hours_year,
        "full_manual_fte": full_manual_fte,
    }

    # Snitt-sentiment som ett ord (mest frekvente) for nøkkeltall-kortet.
    dominant_sentiment = (
        sentiment_counts.most_common(1)[0][0] if sentiment_counts else "nøytral"
    )
    positive_share = round(
        100 * sentiment_counts.get("positiv", 0) / total_calls
    ) if total_calls else 0
    negative_share = round(
        100 * sentiment_counts.get("negativ", 0) / total_calls
    ) if total_calls else 0

    return {
        "total_calls": total_calls,
        "avg_qa": avg_qa,
        "rows": rows,
        "sentiment_dist": sentiment_dist,
        "churn_dist": churn_dist,
        "qa_bands": qa_bands,
        "top_flags": top_flags,
        "total_flags": sum(flag_counts.values()),
        "high_churn": high_churn,
        "high_churn_share": high_churn_share,
        "churn_catches": churn_catches,
        "compliance_catches": compliance_catches,
        "estimates": estimates,
        "dominant_sentiment": dominant_sentiment,
        "positive_share": positive_share,
        "negative_share": negative_share,
    }


@router.get("/rapport", response_class=HTMLResponse)
def impact_report(request: Request) -> HTMLResponse:
    data = _build_report()
    return templates.TemplateResponse(
        request,
        "rapport.html",
        {"banner": _provider_banner(), **data},
    )
