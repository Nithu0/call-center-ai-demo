"""Effekt-side (`/eval`) — DOKUMENTERT EFFEKT for Loyalty.

Loyalty vil ha "piloter med dokumentert effekt". Denne siden viser nettopp det:

1. Nøyaktighet  — AI-analysen sammenlignes mot en gull-fasit (`data/_labels.json`,
                  håndlabelet av menneske). Per samtale: enighet i % på
                  scorecard-punkter + sentiment + henvendelsesårsak. Pluss en
                  total nøyaktighet på tvers.
2. Tidsbesparelse — manuell QA tar typisk ~8 min/samtale; AI gjør det på sekunder.
                  Spart tid vises ved et gitt månedsvolum.
3. Interaktiv ROI — slidere (samtaler/mnd, min/manuell QA, timekost) → vanilla JS
                  regner spart tid + kr/år live. Ingen eksterne libs.
4. Pilot-narrativ — baseline → pilot → måling, slik vi kjører en pilot med
                  målbar effekt.

Defensivt: hvis `data/_labels.json` mangler (lages av en annen agent), laster
siden likevel — da vises nøyaktighets-seksjonen som placeholder, og resten
(tidsbesparelse + ROI + narrativ) fungerer uansett.

Egen lane: KUN denne fila + templates/eval.html. Ingen andre filer røres.
Banner gjenbruker SAMME provider-info som app/main.py `_provider_banner`.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.providers import llm, stt

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
LABELS_PATH = DATA_DIR / "_labels.json"
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter()

# Standard-antakelser for tidsbesparelse/ROI (kan justeres live i UI-et).
DEFAULT_MIN_PER_MANUAL_QA = 8     # min en menneskelig QA-gjennomgang tar pr. samtale
DEFAULT_CALLS_PER_MONTH = 2_000   # typisk månedsvolum for et mindre call-senter
DEFAULT_HOURLY_COST = 450         # kr/time (lønn + sosiale kostnader) for QA-ressurs
AI_SECONDS_PER_CALL = 5           # AI-analyse pr. samtale (sekunder) — i praksis ~øyeblikkelig


def _provider_banner() -> dict:
    """Samme banner-kontrakt som app/main.py `_provider_banner` — gjenbrukt her."""
    return {
        "deploy_target": settings.deploy_target,
        "stt_backend": stt.active_backend(),
        "llm_backend": llm.active_backend(),
        "is_azure": settings.is_azure,
    }


def _load_labels() -> dict:
    """Les gull-fasit robust. Mangler/ugyldig fil → tom dict (siden krasjer ikke)."""
    try:
        if not LABELS_PATH.exists():
            return {}
        raw = json.loads(LABELS_PATH.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:  # noqa: BLE001 — defensiv: aldri la fasit-lesing knekke siden
        return {}


def _pct(part: int, whole: int) -> int:
    return round(100 * part / whole) if whole else 0


def _eval_one(analysis, gold: dict) -> dict:
    """Sammenlign én AI-analyse mot gull-fasit-oppføringen for samtalen.

    `gold` har form: {call_reason, sentiment, scorecard:{<key>:0/1}, total_pct}.
    Returnerer per-samtale enighet (treff/totalt + prosent) brutt ned på
    scorecard / sentiment / call_reason.
    """
    matches = 0          # antall sammenligningspunkter AI traff på
    total = 0            # antall sammenligningspunkter totalt

    # --- Scorecard: per-punkt-enighet (0/1 mot 0/1) ---------------------------
    gold_card = gold.get("scorecard") or {}
    ai_scores = {
        item.key: int(item.score)
        for item in getattr(analysis.scorecard, "items", [])
    }
    card_match = 0
    card_total = 0
    card_rows: list[dict] = []
    for key, gold_score in gold_card.items():
        try:
            gold_val = int(gold_score)
        except (TypeError, ValueError):
            continue
        ai_val = ai_scores.get(key)
        agree = ai_val is not None and ai_val == gold_val
        card_total += 1
        if agree:
            card_match += 1
        card_rows.append(
            {
                "key": key,
                "ai": ai_val if ai_val is not None else "—",
                "gold": gold_val,
                "agree": agree,
            }
        )
    matches += card_match
    total += card_total

    # --- Sentiment: eksakt match ---------------------------------------------
    gold_sentiment = gold.get("sentiment")
    ai_sentiment = getattr(analysis, "sentiment", "")
    sentiment_known = gold_sentiment is not None
    sentiment_agree = sentiment_known and ai_sentiment == gold_sentiment
    if sentiment_known:
        total += 1
        if sentiment_agree:
            matches += 1

    # --- Call reason: eksakt match -------------------------------------------
    gold_reason = gold.get("call_reason")
    ai_reason = getattr(analysis, "call_reason", "") or ""
    reason_known = gold_reason is not None
    reason_agree = reason_known and ai_reason == gold_reason
    if reason_known:
        total += 1
        if reason_agree:
            matches += 1

    return {
        "matches": matches,
        "total": total,
        "percent": _pct(matches, total),
        "card_rows": card_rows,
        "card_match": card_match,
        "card_total": card_total,
        "sentiment_known": sentiment_known,
        "sentiment_agree": sentiment_agree,
        "ai_sentiment": ai_sentiment,
        "gold_sentiment": gold_sentiment or "—",
        "reason_known": reason_known,
        "reason_agree": reason_agree,
        "ai_reason": ai_reason or "—",
        "gold_reason": gold_reason or "—",
    }


def _build_eval() -> dict:
    """Kjør AI på alle samtaler, sammenlign mot fasit, bygg effekt-tall."""
    labels = _load_labels()
    rows: list[dict] = []
    total_matches = 0
    total_points = 0

    samples = stt.list_samples()
    for transcript in samples:
        analysis = llm.analyze(transcript)
        gold = labels.get(transcript.name)

        row = {
            "name": transcript.name,
            "title": transcript.title or transcript.name,
            "call_type": transcript.call_type,
            "has_gold": gold is not None,
        }
        if gold is not None:
            ev = _eval_one(analysis, gold)
            total_matches += ev["matches"]
            total_points += ev["total"]
            row.update(ev)
        else:
            # Ingen fasit for denne samtalen ennå — vis AI-verdiene som referanse.
            row.update(
                {
                    "percent": None,
                    "ai_sentiment": getattr(analysis, "sentiment", "—"),
                    "ai_reason": getattr(analysis, "call_reason", "") or "—",
                    "card_total": len(getattr(analysis.scorecard, "items", [])),
                }
            )
        rows.append(row)

    labeled_rows = [r for r in rows if r["has_gold"]]

    return {
        "rows": rows,
        "labels_present": bool(labels),
        "n_total": len(samples),
        "n_labeled": len(labeled_rows),
        "total_matches": total_matches,
        "total_points": total_points,
        "overall_accuracy": _pct(total_matches, total_points),
        # Tidsbesparelse-antakelser (også startverdier for ROI-kalkulatoren).
        "min_per_manual_qa": DEFAULT_MIN_PER_MANUAL_QA,
        "calls_per_month": DEFAULT_CALLS_PER_MONTH,
        "hourly_cost": DEFAULT_HOURLY_COST,
        "ai_seconds_per_call": AI_SECONDS_PER_CALL,
    }


@router.get("/eval", response_class=HTMLResponse)
def eval_page(request: Request) -> HTMLResponse:
    data = _build_eval()
    return templates.TemplateResponse(
        request,
        "eval.html",
        {"banner": _provider_banner(), **data},
    )
