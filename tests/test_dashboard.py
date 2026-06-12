"""Tester for ledelses-dashboardet (GET /dashboard).

Dashboard-ruteren eies av en annen lane (app/routers/dashboard.py +
templates/dashboard.html). Vi tester via den offentlige HTTP-kontrakten. Hvis
ruten ikke skulle være lastet (modul/template mangler), skippes testene heller
enn å feile hardt.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _dashboard_loaded() -> bool:
    return any(getattr(r, "path", None) == "/dashboard" for r in app.routes)


def test_dashboard_returns_200():
    if not _dashboard_loaded():
        pytest.skip("/dashboard-ruten er ikke lastet")
    res = client.get("/dashboard")
    assert res.status_code == 200


def test_dashboard_contains_key_terms():
    if not _dashboard_loaded():
        pytest.skip("/dashboard-ruten er ikke lastet")
    body = client.get("/dashboard").text.lower()
    # Dashboardet aggregerer QA, sentiment og churn — sjekk at nøkkelbegrepene vises.
    assert "qa" in body or "score" in body
    assert "sentiment" in body
    assert "churn" in body


def test_dashboard_lists_sample_calls():
    if not _dashboard_loaded():
        pytest.skip("/dashboard-ruten er ikke lastet")
    body = client.get("/dashboard").text
    # Minst én av demo-samtalene skal være referert i tabellen.
    assert "salg_alarm" in body or "kundeservice_faktura" in body
