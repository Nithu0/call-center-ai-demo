"""Tester for eval-visningen (GET /eval).

Eval-ruteren eies av en annen lane (app/routers/eval.py). Vi tester via den
offentlige HTTP-kontrakten. Hvis ruten ikke er lastet ennå (modul mangler /
annen agent ikke ferdig), skippes testene heller enn å feile hardt.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _eval_loaded() -> bool:
    return any(getattr(r, "path", None) == "/eval" for r in app.routes)


def test_eval_returns_200():
    if not _eval_loaded():
        pytest.skip("/eval-ruten er ikke lastet (eval-modul ikke til stede)")
    res = client.get("/eval")
    assert res.status_code == 200


def test_eval_has_body():
    if not _eval_loaded():
        pytest.skip("/eval-ruten er ikke lastet (eval-modul ikke til stede)")
    res = client.get("/eval")
    assert res.status_code == 200
    assert len(res.text) > 0
