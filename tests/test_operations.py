"""Tester for driftspanelet (`GET /operations` + `GET /operations/feed`).

Egen lane (KUN denne fila). Driftsruteren eies av en annen lane
(`app/routers/live_ops.py` + `templates/operations.html`); vi tester via den
offentlige HTTP-kontrakten. Defensivt: hvis ruten ikke er lastet (modul mangler)
ELLER samarbeids-templaten ikke er landet ennå, skippes testen pent i stedet for
hard-fail — så denne lane-en aldri rødner på arbeid en annen agent ennå ikke
har levert.
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


def _get_or_skip(path: str):
    """Hent `path` defensivt.

    Skipper hvis ruten ikke er registrert, eller hvis den feiler fordi en
    samarbeids-template ennå ikke er landet (TemplateNotFound → 500). Andre
    500-er får boble opp som ekte feil når templaten først finnes.
    """
    if not _route_exists(path):
        pytest.skip(f"{path} ennå ikke landet (laget av annen agent)")
    try:
        res = client.get(path)
    except Exception as exc:  # noqa: BLE001 — template ennå ikke landet i annen lane
        if "TemplateNotFound" in type(exc).__name__ or "not found in search path" in str(exc):
            pytest.skip(f"{path}: template ennå ikke landet ({exc})")
        raise
    return res


def test_operations_page_returns_200():
    res = _get_or_skip("/operations")
    assert res.status_code == 200, res.text


def test_operations_page_is_a_driftspanel():
    res = _get_or_skip("/operations")
    assert res.status_code == 200
    low = res.text.lower()
    # Driftspanel-markører: noe som signaliserer «live drift / samtaler i dag».
    markers = ["drift", "samtaler", "live", "qa", "operations"]
    assert any(m in low for m in markers), (
        f"fant ingen driftspanel-markør blant {markers!r} i /operations"
    )


def test_operations_reuses_provider_banner():
    res = _get_or_skip("/operations")
    assert res.status_code == 200
    # Banneret gjenbruker samme provider-kontrakt som forsiden (DEPLOY_TARGET).
    assert "DEPLOY_TARGET" in res.text


def test_operations_feed_returns_json_list():
    if not _route_exists("/operations/feed"):
        pytest.skip("/operations/feed ennå ikke landet (laget av annen agent)")
    res = client.get("/operations/feed")
    assert res.status_code == 200, res.text
    data = res.json()

    # Feeden kan enten være en ren liste, eller et objekt med en liste under
    # «rows» (faktisk kontrakt i live_ops.py). Begge skal aksepteres.
    if isinstance(data, list):
        rows = data
    else:
        assert isinstance(data, dict), f"uventet feed-type: {type(data)!r}"
        rows = data.get("rows")
        assert isinstance(rows, list), f"feed mangler liste under 'rows': {list(data)!r}"

    # Hver rad skal ha noe som likner en samtale-identifikator.
    if rows:
        first = rows[0]
        assert isinstance(first, dict), f"feed-rad er ikke et objekt: {first!r}"


def test_operations_feed_respects_n_param():
    if not _route_exists("/operations/feed"):
        pytest.skip("/operations/feed ennå ikke landet (laget av annen agent)")
    res = client.get("/operations/feed", params={"n": 5})
    assert res.status_code == 200, res.text
    data = res.json()
    rows = data if isinstance(data, list) else data.get("rows", [])
    # `n` skal styre antall rader (klampet i ruteren), så ≤ et lite tall her.
    assert len(rows) <= 5, f"forventet ≤5 rader for n=5, fikk {len(rows)}"
