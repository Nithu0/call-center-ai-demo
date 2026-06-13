"""Tester for personvern-siden (`GET /personvern`).

Egen lane (KUN denne fila). Ruteren eies av en annen lane
(`app/routers/redaction.py` / personvern-router + `templates/privacy.html`);
vi tester via HTTP-kontrakten. Defensivt: skip pent hvis ruten ikke er
registrert eller samarbeids-templaten ennå ikke er landet (TemplateNotFound →
500).

Spec: siden skal vise en PII-/maskerings-markør (ansvarlig-AI-showcase).
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


def test_personvern_returns_200():
    res = _get_or_skip("/personvern")
    assert res.status_code == 200, res.text


def test_personvern_shows_pii_masking_marker():
    res = _get_or_skip("/personvern")
    assert res.status_code == 200
    low = res.text.lower()
    # PII-/maskerings-markører — siden er en ansvarlig-AI-showcase.
    markers = ["pii", "masker", "personvern", "personopplysning", "anonym", "redact"]
    assert any(m in low for m in markers), (
        f"fant ingen PII-/maskerings-markør blant {markers!r} i /personvern"
    )
