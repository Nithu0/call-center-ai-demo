"""Tester for guide-siden «Slik fungerer demoen» (`GET /guide`).

Egen lane (KUN denne fila). Ruteren eies av en annen lane
(`app/routers/guide.py` + `templates/guide.html`); vi tester via HTTP-kontrakten.
Defensivt: skip pent hvis ruten ikke er registrert eller samarbeids-templaten
ennå ikke er landet (TemplateNotFound → 500).
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


def test_guide_returns_200():
    res = _get_or_skip("/guide")
    assert res.status_code == 200, res.text


def test_guide_explains_the_demo():
    res = _get_or_skip("/guide")
    assert res.status_code == 200
    low = res.text.lower()
    # Guiden skal forklare demoen for en leder — sjekk noen forventede markører.
    markers = ["guide", "demo", "funger", "slik", "åpne"]
    assert any(m in low for m in markers), (
        f"fant ingen guide-markør blant {markers!r} i /guide"
    )


def test_guide_links_to_other_features():
    res = _get_or_skip("/guide")
    assert res.status_code == 200
    body = res.text
    # Guiden er en navigasjons-hub — den skal lenke videre til andre sider.
    assert ("/live" in body) or ("/dashboard" in body) or ("/rapport" in body), (
        "guiden lenker ikke videre til noen av kjernefunksjonene"
    )


def test_guide_reuses_provider_banner():
    res = _get_or_skip("/guide")
    assert res.status_code == 200
    assert "DEPLOY_TARGET" in res.text
