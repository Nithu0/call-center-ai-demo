"""Tester for FastAPI-endepunktene (svarer 200, UI laster, analyse virker)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_index_returns_200_and_lists_calls():
    res = client.get("/")
    assert res.status_code == 200
    body = res.text
    assert "DEPLOY_TARGET" in body
    assert "Samme kode" in body
    assert "salg_alarm" in body
    assert "kundeservice_faktura" in body


def test_call_detail_salg_200():
    res = client.get("/call/salg_alarm")
    assert res.status_code == 200
    body = res.text
    assert "Transkript" in body
    assert "AI-analyse" in body
    assert "QA-scorecard" in body
    assert "Sentiment" in body


def test_call_detail_service_200():
    res = client.get("/call/kundeservice_faktura")
    assert res.status_code == 200
    assert "faktura" in res.text.lower()


def test_call_detail_unknown_404():
    res = client.get("/call/finnes_ikke")
    assert res.status_code == 404


def test_reanalyze_returns_full_analysis():
    res = client.post("/call/salg_alarm/analyze")
    assert res.status_code == 200
    data = res.json()
    assert data["name"] == "salg_alarm"
    a = data["analysis"]
    assert "summary" in a
    assert "scorecard" in a
    assert len(a["scorecard"]["items"]) == 6
    assert a["backend"] == "mock"
    assert "banner" in data
    assert data["banner"]["deploy_target"] == "local"


def test_reanalyze_unknown_404():
    res = client.post("/call/finnes_ikke/analyze")
    assert res.status_code == 404


def test_healthz():
    res = client.get("/healthz")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["llm_backend"] == "mock"
    assert data["stt_backend"] == "mock"
