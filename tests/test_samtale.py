"""Tester for /samtale (live salgssamtale) — kjører i mock-default (ingen nøkkel)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_samtale_page_loads():
    r = client.get("/samtale")
    assert r.status_code == 200
    assert "Live salgssamtale" in r.text


def test_agent_opening_turn():
    """Tom historikk → agenten åpner, samtalen er ikke ferdig."""
    r = client.post("/samtale/agent", json={"history": []})
    assert r.status_code == 200
    d = r.json()
    assert d["text"]                      # agenten sier noe
    assert d["done"] is False
    # uten nøkkel skal TTS falle tilbake til browser-tale (ingen lyd fra server)
    assert d["audio_b64"] is None
    assert d["tts_backend"] == "browser"


def test_price_objection_is_classified():
    """Pris-innvending skal gjenkjennes og styre anbefalingen."""
    hist = [
        {"speaker": "agent", "text": "Hei, vi har en kampanje på boligalarm."},
        {"speaker": "kunde", "text": "Det høres dyrt ut, hva koster det?"},
    ]
    d = client.post("/samtale/agent", json={"history": hist}).json()
    assert d["analysis"]["signal"] == "Pris-innvending"
    assert "verdi" in d["analysis"]["recommendation"].lower()
    assert d["analysis"]["how"]           # transparens-forklaring finnes


def test_persistent_rejection_ends_call():
    """To avvisninger på rad → agenten avslutter høflig (done=True)."""
    hist = [
        {"speaker": "agent", "text": "Hei, kampanje på alarm."},
        {"speaker": "kunde", "text": "nei takk, ikke interessert"},
        {"speaker": "agent", "text": "Jeg skal være rask — enebolig eller leilighet?"},
        {"speaker": "kunde", "text": "nei, legg på"},
    ]
    d = client.post("/samtale/agent", json={"history": hist}).json()
    assert d["done"] is True
