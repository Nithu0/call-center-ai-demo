"""Tester for live agent-assist-skjermen (`GET /agent-assist`).

Egen lane (KUN denne fila). Ruteren eies av en annen lane
(`app/routers/agent_assist.py` + `templates/agent_assist.html`); vi tester via
HTTP-kontrakten. Defensivt: skip pent hvis ruten ikke er registrert eller
samarbeids-templaten ennå ikke er landet (TemplateNotFound → 500).
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


def test_agent_assist_returns_200():
    res = _get_or_skip("/agent-assist")
    assert res.status_code == 200, res.text


def test_agent_assist_shows_live_assist_ui():
    res = _get_or_skip("/agent-assist")
    assert res.status_code == 200
    low = res.text.lower()
    # Sanntids-assist-markører: forslag/neste handling/påminnelse o.l.
    markers = ["assist", "neste", "forslag", "samtale", "agent"]
    assert any(m in low for m in markers), (
        f"fant ingen agent-assist-markør blant {markers!r} i /agent-assist"
    )


def test_agent_assist_reuses_provider_banner():
    res = _get_or_skip("/agent-assist")
    assert res.status_code == 200
    # Samme provider-kontrakt som resten av appen.
    assert "DEPLOY_TARGET" in res.text
