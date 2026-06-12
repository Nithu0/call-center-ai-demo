"""Tester for integrasjonslaget — CRM-eksport + telefoni-webhook.

Dekker:
  - to_crm(): strukturen på CRM-posten (alle ventede nøkler, fornuftige verdier).
  - push_to_crm(): dry-run uten webhook.
  - handle_call_event(): pipeline kjører fra et sample-event.
  - POST /integrations/telephony/webhook → 200 + ok.
  - GET  /integrations/crm/{name} → 200 + payload, og 404 for ukjent.

Defensiv: hvis integrasjons-ruteren ikke skulle være lastet (annen agent / modul
mangler), skippes rute-testene heller enn å feile hardt. Enhetstestene mot
crm.py / telephony.py kjører uansett (egen lane).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.integrations.crm import push_to_crm, to_crm
from app.integrations.telephony import handle_call_event
from app.main import app
from app.providers import llm, stt

client = TestClient(app)

# Forventede nøkler i en CRM-post (kontrakten denne lane eier).
_CRM_KEYS = {
    "samtale_id",
    "samtaletype",
    "kunde_intent",
    "produkt",
    "utfall",
    "neste_steg",
    "henvendelsesarsak",
    "sentiment",
    "qa_score",
    "churn_risk",
    "prioritet",
    "sammendrag",
}


def _route_exists(method: str, path: str) -> bool:
    """Sjekk om en rute er registrert (defensiv mot manglende moduler)."""
    for route in app.routes:
        if getattr(route, "path", None) == path and method.upper() in getattr(
            route, "methods", set()
        ):
            return True
    return False


# --------------------------------------------------------------------------- #
# Enhetstester: CRM-eksport                                                     #
# --------------------------------------------------------------------------- #
def test_to_crm_has_expected_structure():
    transcript = stt.transcribe("salg_alarm")
    analysis = llm.analyze(transcript)
    post = to_crm(transcript, analysis)

    assert set(post.keys()) == _CRM_KEYS
    assert post["samtale_id"] == "salg_alarm"
    assert post["samtaletype"] == "salg"
    assert post["sentiment"] in ("positiv", "nøytral", "negativ")
    assert post["churn_risk"] in ("lav", "middels", "høy")
    assert post["prioritet"] in ("normal", "middels", "høy")
    assert isinstance(post["qa_score"], int)
    assert 0 <= post["qa_score"] <= 100
    assert isinstance(post["sammendrag"], str) and post["sammendrag"]


def test_to_crm_prioritet_follows_churn():
    # En oppsigelse-samtale skal gi høy churn → høy prioritet.
    transcript = stt.transcribe("retention_oppsigelse")
    analysis = llm.analyze(transcript)
    post = to_crm(transcript, analysis)
    assert post["churn_risk"] == "høy"
    assert post["prioritet"] == "høy"


def test_push_to_crm_dry_run_without_webhook():
    payload = {"samtale_id": "x", "prioritet": "normal"}
    res = push_to_crm(payload)  # ingen webhook_url
    assert res["status"] == "dry-run"
    assert res["payload"] == payload


# --------------------------------------------------------------------------- #
# Enhetstest: telefoni-ingestion                                               #
# --------------------------------------------------------------------------- #
def test_handle_call_event_runs_pipeline_from_sample():
    event = {"call_id": "c-1", "platform": "puzzel", "recording": "kundeservice_faktura"}
    result = handle_call_event(event)

    assert result["status"] == "ok"
    assert result["call_id"] == "c-1"
    assert result["platform"] == "puzzel"
    assert result["transcript"]["name"] == "kundeservice_faktura"
    assert result["transcript"]["num_turns"] > 0
    # Full analyse + CRM-payload finnes.
    assert "analysis" in result and "summary" in result["analysis"]
    assert set(result["crm_payload"].keys()) == _CRM_KEYS


def test_handle_call_event_accepts_inline_transcript():
    event = {
        "call_id": "c-2",
        "platform": "genesys",
        "transcript": {
            "name": "inline_test",
            "call_type": "kundeservice",
            "title": "Inline",
            "turns": [
                {"speaker": "agent", "text": "Hei, du snakker med support."},
                {"speaker": "kunde", "text": "Jeg har et spørsmål om fakturaen min."},
            ],
        },
    }
    result = handle_call_event(event)
    assert result["status"] == "ok"
    assert result["transcript"]["name"] == "inline_test"
    assert result["transcript"]["num_turns"] == 2


def test_handle_call_event_missing_recording_is_error():
    result = handle_call_event({"call_id": "c-3", "platform": "puzzel"})
    assert result["status"] == "error"


# --------------------------------------------------------------------------- #
# Rute-tester (defensive mot manglende ruter)                                  #
# --------------------------------------------------------------------------- #
def test_telephony_webhook_200():
    if not _route_exists("POST", "/integrations/telephony/webhook"):
        pytest.skip("telephony-webhook-ruten er ikke lastet")
    res = client.post(
        "/integrations/telephony/webhook",
        json={"call_id": "w-1", "platform": "puzzel", "recording": "salg_alarm"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["call_id"] == "w-1"
    assert "crm_payload" in data


def test_crm_export_route_200_and_dry_run():
    if not _route_exists("GET", "/integrations/crm/{name}"):
        pytest.skip("crm-export-ruten er ikke lastet")
    res = client.get("/integrations/crm/salg_alarm")
    assert res.status_code == 200
    data = res.json()
    assert data["name"] == "salg_alarm"
    assert set(data["crm_payload"].keys()) == _CRM_KEYS
    assert data["push"]["status"] == "dry-run"


def test_crm_export_route_unknown_404():
    if not _route_exists("GET", "/integrations/crm/{name}"):
        pytest.skip("crm-export-ruten er ikke lastet")
    res = client.get("/integrations/crm/finnes_ikke")
    assert res.status_code == 404
