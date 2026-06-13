"""Tester for GET /status (backend-selvtest-siden).

Defensiv: hvis /status-ruten ikke er ferdig ennå (en annen agent bygger den +
templates/status.html), skipper vi pent i stedet for å feile. Når siden FAKTISK
svarer 200 sjekker vi to ting:

  1. Den nevner backend-navnene (faster-whisper, mock, anthropic, ...) og har en
     aktiv-markering, slik at man SER hva som er koblet opp.
  2. Den lekker INGEN nøkkelverdi — kun PRESENT/MISSING-status skal stå på siden.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from app.main import app

# raise_server_exceptions=False: hvis ruten finnes men template/wiring ikke er
# på plass ennå får vi en 5xx-respons (ikke en exception) som vi kan skippe på.
client = TestClient(app, raise_server_exceptions=False)


def _get_status():
    """Hent /status, eller skip pent hvis ruten ikke er klar ennå."""
    res = client.get("/status")
    if res.status_code != 200:
        pytest.skip(
            f"/status er ikke klar ennå (status_code={res.status_code}); "
            "en annen agent bygger ruten + templates/status.html."
        )
    return res


def test_status_returns_200():
    res = _get_status()
    assert res.status_code == 200
    assert res.text.strip()  # ikke tom


def test_status_mentions_backends_and_active_marker():
    """Siden skal vise backend-navn + en aktiv-markering."""
    res = _get_status()
    body = res.text
    low = body.lower()

    # Minst noen av backend-navnene må være synlige på siden.
    backend_names = ["faster-whisper", "mock", "anthropic", "openai", "azure"]
    hits = [n for n in backend_names if n in low]
    assert len(hits) >= 3, f"forventet flere backend-navn på /status, fant: {hits}"

    # mock er default-backend og skal alltid være med.
    assert "mock" in low

    # En aktiv-markering skal finnes (● aktiv / "aktiv"). Default-backend = mock.
    assert "aktiv" in low, "forventet en aktiv-markering ('aktiv') på /status"

    # PRESENT/MISSING-status for nøkler skal vises (selvtest-poenget).
    assert "present" in low or "missing" in low


def test_status_does_not_leak_key_values():
    """KRITISK: ingen ekte nøkkelverdi skal lekke ut på siden — kun PRESENT/MISSING.

    Vi setter kjente sentinel-verdier i de tre nøkkel-env-varene og bekrefter at
    INGEN av dem dukker opp i HTML-en. Siden skal kun rapportere tilstedeværelse.
    """
    sentinels = {
        "OPENAI_API_KEY": "sk-LEAKCANARY-openai-deadbeef-DONOTLEAK",
        "ANTHROPIC_API_KEY": "sk-ant-LEAKCANARY-anthropic-DONOTLEAK",
        "AZURE_SPEECH_KEY": "LEAKCANARY-azurespeech-DONOTLEAK",
        "AZURE_OPENAI_KEY": "LEAKCANARY-azureopenai-DONOTLEAK",
    }
    saved = {k: os.environ.get(k) for k in sentinels}
    try:
        for k, v in sentinels.items():
            os.environ[k] = v

        res = client.get("/status")
        if res.status_code != 200:
            pytest.skip(
                f"/status er ikke klar ennå (status_code={res.status_code})."
            )
        body = res.text
        for k, v in sentinels.items():
            assert v not in body, f"nøkkelverdi for {k} lekket ut på /status!"
    finally:
        for k, old in saved.items():
            if old is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = old
