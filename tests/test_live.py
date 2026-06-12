"""Tester for live-STT-siden `GET /live` (Web Speech API, klient-side STT).

Egen lane: KUN denne fila. Defensiv — hvis ruten ennå ikke er landet
(lages av en annen agent), skip pent i stedet for hard-fail.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _route_exists(path: str, method: str = "GET") -> bool:
    """True hvis `app` har en rute som matcher path + metode."""
    method = method.upper()
    for route in app.routes:
        if getattr(route, "path", None) == path and method in getattr(route, "methods", set()):
            return True
    return False


def test_live_page_returns_200_with_recording_ui():
    if not _route_exists("/live"):
        pytest.skip("GET /live ennå ikke landet (laget av annen agent)")

    res = client.get("/live")
    assert res.status_code == 200, res.text
    body = res.text

    # Opptaks-UI-markør: en «Start»-knapp/etikett skal finnes.
    assert "Start" in body, "fant ingen «Start»-markør i live-UI-et"

    # Minst én live-STT-markør (Web Speech / nb-NO / mikrofon-tekst).
    low = body.lower()
    markers = ["web speech", "nb-no", "mikrofon", "🎙", "opptak"]
    assert any(m in low for m in markers), (
        f"fant ingen live-STT-markør blant {markers!r} i /live"
    )


def test_live_page_reuses_provider_banner():
    if not _route_exists("/live"):
        pytest.skip("GET /live ennå ikke landet (laget av annen agent)")

    res = client.get("/live")
    assert res.status_code == 200
    # Banneret gjenbruker samme provider-kontrakt som forsiden (DEPLOY_TARGET).
    assert "DEPLOY_TARGET" in res.text
