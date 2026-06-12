"""Tester for `POST /transcribe` — den private backend-STT-veien.

Egen lane: KUN denne fila. Defensiv — skip pent hvis ruten ennå ikke er landet.
Bruker en liten dummy-lydfil (bytes) i `file`-feltet. På mock-backend svarer
ruten 200 med placeholder-transkript + et `note`-felt.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

# Liten dummy "lyd"-fil — innholdet betyr ingenting på mock-veien, men må være
# ikke-tomt (ruten avviser tomme bytes med 400).
_DUMMY_AUDIO = b"RIFF\x24\x00\x00\x00WAVEfmt \x00\x00\x00\x00data\x00\x00\x00\x00"


def _route_exists(path: str, method: str = "POST") -> bool:
    method = method.upper()
    for route in app.routes:
        if getattr(route, "path", None) == path and method in getattr(route, "methods", set()):
            return True
    return False


def test_transcribe_dummy_audio_returns_200():
    if not _route_exists("/transcribe"):
        pytest.skip("POST /transcribe ennå ikke landet (laget av annen agent)")

    res = client.post(
        "/transcribe",
        files={"file": ("opptak.wav", _DUMMY_AUDIO, "audio/wav")},
    )
    assert res.status_code == 200, res.text
    data = res.json()

    # Backend-feltet skal alltid følge med.
    assert "backend" in data, data

    # Transkriptet skal finnes (placeholder på mock-veien).
    assert "transcript" in data, data
    assert "turns" in data["transcript"]

    # På mock-veien (ingen ekte lyd-dekoding) skal et forklarende `note` følge med.
    if not data.get("supports_audio", False):
        assert "note" in data, data
        assert data["note"]


def test_transcribe_missing_file_returns_422_or_400():
    if not _route_exists("/transcribe"):
        pytest.skip("POST /transcribe ennå ikke landet (laget av annen agent)")

    # Ingen `file`-felt -> FastAPI validerer (422) eller ruten avviser (400).
    res = client.post("/transcribe")
    assert res.status_code in (400, 422), res.text


def test_transcribe_empty_file_returns_400():
    if not _route_exists("/transcribe"):
        pytest.skip("POST /transcribe ennå ikke landet (laget av annen agent)")

    res = client.post(
        "/transcribe",
        files={"file": ("tom.wav", b"", "audio/wav")},
    )
    # Tom fil (ingen lyd-bytes) avvises med 400.
    assert res.status_code == 400, res.text
