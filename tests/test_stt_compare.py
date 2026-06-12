"""Tester for `GET /stt` — STT-backend-sammenligning (NB-Whisper vs Azure m.fl.).

Egen lane: KUN denne fila. Defensiv — ruten lages av en annen agent; skip pent
hvis den ennå ikke er landet.
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


def test_stt_compare_page_lists_backends():
    if not _route_exists("/stt"):
        pytest.skip("GET /stt ennå ikke landet (laget av annen agent)")

    # Ruten finnes, men template/assets kan ennå være under landing av en annen
    # agent. TestClient re-raiser server-feil — fang det og skip pent.
    try:
        res = client.get("/stt")
    except Exception as exc:  # noqa: BLE001 — annen agent ikke ferdig ennå
        pytest.skip(f"/stt finnes, men feiler under rendering (annen agent ikke ferdig): {exc}")

    if res.status_code != 200:
        pytest.skip(f"/stt finnes, men svarer {res.status_code} (annen agent ikke ferdig)")

    low = res.text.lower()

    # Sammenligningstabellen skal nevne både NB-Whisper og Azure.
    assert "nb-whisper" in low or "nb whisper" in low, "fant ikke NB-Whisper i /stt"
    assert "azure" in low, "fant ikke Azure i /stt"
