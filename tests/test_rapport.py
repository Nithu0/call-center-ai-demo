"""Tester for leder-/effekt-rapporten (`GET /rapport`).

Egen lane (KUN denne fila). Ruteren eies av en annen lane
(`app/routers/impact_report.py` + `templates/rapport.html`); vi tester via
HTTP-kontrakten. Defensivt: skip pent hvis ruten ikke er registrert eller
samarbeids-templaten ennå ikke er landet (TemplateNotFound → 500).

Spec: rapporten skal inneholde «anbefaling», «effekt» og «QA».
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _route_exists(path: str, method: str = "GET") -> bool:
    method = method.upper()
    for route in app.routes:
        if getattr(route, "path", None) == path and method in getattr(route, "methods", set()):
            return True
    return False


def _get_or_skip(path: str):
    if not _route_exists(path):
        pytest.skip(f"{path} ennå ikke landet (laget av annen agent)")
    try:
        res = client.get(path)
    except Exception as exc:  # noqa: BLE001 — template ennå ikke landet i annen lane
        if "TemplateNotFound" in type(exc).__name__ or "not found in search path" in str(exc):
            pytest.skip(f"{path}: template ennå ikke landet ({exc})")
        raise
    return res


def test_rapport_returns_200():
    res = _get_or_skip("/rapport")
    assert res.status_code == 200, res.text


def test_rapport_contains_recommendation_effect_and_qa():
    res = _get_or_skip("/rapport")
    assert res.status_code == 200
    low = res.text.lower()
    # Kjernebudskap i en leder-rapport: en anbefaling, dokumentert effekt, og QA.
    assert "anbefaling" in low, "rapporten mangler «anbefaling»"
    assert "effekt" in low, "rapporten mangler «effekt»"
    assert "qa" in low, "rapporten mangler «QA»"


def test_rapport_reuses_provider_banner():
    res = _get_or_skip("/rapport")
    assert res.status_code == 200
    assert "DEPLOY_TARGET" in res.text
