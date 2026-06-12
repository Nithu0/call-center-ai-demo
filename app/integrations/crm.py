"""CRM-eksport — bygg en CRM-klar post fra en analyse og (valgfritt) push den.

`to_crm(transcript, analysis) -> dict`
    Bygger en flat, CRM-vennlig post: kunde-intent, produkt, utfall, neste_steg,
    sentiment, qa_score, churn_risk, prioritet og et kort sammendrag. Henter de
    utvidede analyse-feltene defensivt med `getattr(...)` slik at posten bygges
    uansett hvilken backend (mock/anthropic/azure) som produserte analysen, og
    uansett om et felt mangler.

`push_to_crm(payload, webhook_url=None) -> dict`
    Hvis `webhook_url` er satt: POST payloaden (httpx, import-guardet) og
    rapporter HTTP-status. Ellers: "dry-run" — returner payloaden uendret slik
    at demoen aldri trenger nett/CRM-konto for å vise flyten.

Lane: kun denne fila (+ telephony.py, routers/integrations.py). Ingen eksisterende
filer røres. CRM-strukturen speiler `Analysis.crm_export` men er beriket med
qa_score/sentiment/sammendrag slik at posten er selvstendig nyttig i et CRM.

Avhengigheter: bruker `httpx` (følger med FastAPI) for HTTP-push — IKKE lagt i
requirements.txt (allerede en kjerne-avhengighet via FastAPI TestClient). `requests`
er bevisst IKKE brukt (ikke garantert installert). Importen er guardet, så modulen
laster selv om httpx skulle mangle.
"""

from __future__ import annotations

from typing import Any


def _churn_to_prioritet(churn: str) -> str:
    """Map churn-risiko til en CRM-prioritet."""
    return {"høy": "høy", "middels": "middels"}.get(churn, "normal")


def to_crm(transcript: Any, analysis: Any) -> dict:
    """Bygg en CRM-klar post fra transkript + analyse.

    Defensiv: alle utvidede felt hentes med getattr og faller tilbake til
    fornuftige defaults, slik at posten bygges uansett backend/feltrekkefølge.
    """
    # Foretrekk analysens egen crm_export hvis backend la den ved, men berik
    # alltid med de feltene CRM-et trenger uavhengig av backend.
    base_export = getattr(analysis, "crm_export", {}) or {}
    key_info = getattr(analysis, "key_info", None)

    def _ki(field: str) -> str:
        # Hent fra crm_export (norske nøkler) eller key_info (engelske attr).
        norsk = {
            "intent": "intent",
            "product": "produkt",
            "outcome": "utfall",
            "next_step": "neste_steg",
        }
        if field in norsk and base_export.get(norsk[field]):
            return str(base_export[norsk[field]])
        if key_info is not None:
            return str(getattr(key_info, field, "") or "")
        return ""

    sentiment = getattr(analysis, "sentiment", "nøytral") or "nøytral"
    churn_risk = getattr(analysis, "churn_risk", "lav") or "lav"
    call_reason = getattr(analysis, "call_reason", "") or ""
    summary = getattr(analysis, "summary", "") or ""

    scorecard = getattr(analysis, "scorecard", None)
    qa_score = getattr(scorecard, "percent", 0) if scorecard is not None else 0

    samtaletype = (
        getattr(transcript, "call_type", "")
        or base_export.get("samtaletype", "")
        or "ukjent"
    )

    return {
        "samtale_id": getattr(transcript, "name", "") or "",
        "samtaletype": samtaletype,
        "kunde_intent": _ki("intent"),
        "produkt": _ki("product"),
        "utfall": _ki("outcome"),
        "neste_steg": _ki("next_step"),
        "henvendelsesarsak": call_reason,
        "sentiment": sentiment,
        "qa_score": qa_score,
        "churn_risk": churn_risk,
        "prioritet": _churn_to_prioritet(churn_risk),
        "sammendrag": summary,
    }


def push_to_crm(payload: dict, webhook_url: str | None = None) -> dict:
    """Push en CRM-post til en webhook, eller returner dry-run.

    - webhook_url=None  → {"status": "dry-run", "payload": payload}  (ingen nett)
    - webhook_url satt  → POST payload som JSON; rapporter HTTP-status.

    HTTP-klienten (httpx) importeres lazy og guardet, slik at modulen laster og
    dry-run alltid virker selv uten httpx installert.
    """
    if not webhook_url:
        return {"status": "dry-run", "payload": payload}

    try:
        import httpx
    except ImportError:  # pragma: no cover — httpx følger med FastAPI
        return {
            "status": "error",
            "error": "httpx ikke installert; kan ikke pushe til CRM-webhook.",
            "payload": payload,
        }

    try:
        resp = httpx.post(webhook_url, json=payload, timeout=10.0)
        return {
            "status": "pushed",
            "http_status": resp.status_code,
            "ok": resp.is_success,
            "webhook_url": webhook_url,
        }
    except Exception as exc:  # noqa: BLE001 — demo: rapporter, ikke krasj
        return {
            "status": "error",
            "error": f"{type(exc).__name__}: {exc}",
            "webhook_url": webhook_url,
            "payload": payload,
        }
