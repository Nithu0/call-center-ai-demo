"""Tester for `POST /analyze-text` — fritekst-analyse av en vilkårlig samtale.

Egen lane: KUN denne fila. Defensiv — skip pent hvis ruten ennå ikke er landet.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _route_exists(path: str, method: str = "POST") -> bool:
    """True hvis `app` har en rute som matcher path + metode."""
    method = method.upper()
    for route in app.routes:
        if getattr(route, "path", None) == path and method in getattr(route, "methods", set()):
            return True
    return False


def test_analyze_text_oppsigelse_gives_high_churn():
    if not _route_exists("/analyze-text"):
        pytest.skip("POST /analyze-text ennå ikke landet (laget av annen agent)")

    res = client.post(
        "/analyze-text",
        json={"text": "agent: Hei\nkunde: Jeg vil si opp abonnementet"},
    )
    assert res.status_code == 200, res.text
    data = res.json()

    # Analysen skal finnes med sentiment + scorecard.
    assert "analysis" in data, data
    analysis = data["analysis"]
    assert "sentiment" in analysis
    assert "scorecard" in analysis
    # Scorecard er strukturert (items + prosent).
    assert "items" in analysis["scorecard"]

    # Oppsigelse -> høy churn-risiko.
    assert analysis.get("churn_risk") == "høy", analysis.get("churn_risk")


def test_analyze_text_parses_speaker_prefixes():
    if not _route_exists("/analyze-text"):
        pytest.skip("POST /analyze-text ennå ikke landet (laget av annen agent)")

    res = client.post(
        "/analyze-text",
        json={"text": "agent: Hei\nkunde: Jeg vil si opp abonnementet"},
    )
    assert res.status_code == 200, res.text
    data = res.json()
    # Transkriptet skal være parset til turns med agent + kunde.
    turns = data.get("transcript", {}).get("turns", [])
    speakers = {t["speaker"] for t in turns}
    assert {"agent", "kunde"} <= speakers, turns


def test_analyze_text_empty_returns_400():
    if not _route_exists("/analyze-text"):
        pytest.skip("POST /analyze-text ennå ikke landet (laget av annen agent)")

    res = client.post("/analyze-text", json={"text": ""})
    assert res.status_code == 400, res.text


def test_analyze_text_whitespace_only_returns_400():
    if not _route_exists("/analyze-text"):
        pytest.skip("POST /analyze-text ennå ikke landet (laget av annen agent)")

    res = client.post("/analyze-text", json={"text": "   \n  "})
    assert res.status_code == 400, res.text
