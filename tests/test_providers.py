"""Tester for det pluggbare provider-laget.

Dekker:
  - provider-pluggability (bytte backend via Settings)
  - mock-analyse er deterministisk
  - QA-scorecard-logikk
  - config: DEPLOY_TARGET=azure setter Azure-backends
"""

from __future__ import annotations

import os

import pytest

from app.config import Settings, load_settings
from app.models import Transcript
from app.providers import llm, stt


# --------------------------------------------------------------------------- #
# Fixtures / helpers                                                           #
# --------------------------------------------------------------------------- #
def make_settings(deploy_target="local", stt_backend=None, llm_backend=None) -> Settings:
    """Bygg Settings direkte (uten å røre prosess-miljøet)."""
    if stt_backend is None:
        stt_backend = "azure" if deploy_target == "azure" else "mock"
    if llm_backend is None:
        llm_backend = "azure-openai" if deploy_target == "azure" else "mock"
    return Settings(
        deploy_target=deploy_target,
        stt_backend=stt_backend,
        llm_backend=llm_backend,
        azure_speech_key="",
        azure_speech_region="swedencentral",
        azure_speech_language="nb-NO",
        azure_openai_endpoint="",
        azure_openai_key="",
        azure_openai_deployment="gpt-4o",
        anthropic_api_key="",
        anthropic_model="claude-opus-4-8",
    )


@pytest.fixture
def salg() -> Transcript:
    return stt.transcribe("salg_alarm", cfg=make_settings())


@pytest.fixture
def service() -> Transcript:
    return stt.transcribe("kundeservice_faktura", cfg=make_settings())


# --------------------------------------------------------------------------- #
# Config / DEPLOY_TARGET                                                        #
# --------------------------------------------------------------------------- #
def test_deploy_target_local_uses_mock_backends():
    cfg = make_settings("local")
    assert cfg.stt_backend == "mock"
    assert cfg.llm_backend == "mock"
    assert cfg.is_azure is False


def test_deploy_target_azure_selects_azure_backends():
    """KJERNEPOENG: én variabel flytter hele systemet til Azure."""
    cfg = make_settings("azure")
    assert cfg.stt_backend == "azure"
    assert cfg.llm_backend == "azure-openai"
    assert cfg.is_azure is True


def test_load_settings_reads_deploy_target(monkeypatch):
    monkeypatch.setenv("DEPLOY_TARGET", "azure")
    monkeypatch.delenv("STT_BACKEND", raising=False)
    monkeypatch.delenv("LLM_BACKEND", raising=False)
    cfg = load_settings()
    assert cfg.deploy_target == "azure"
    assert cfg.stt_backend == "azure"
    assert cfg.llm_backend == "azure-openai"


def test_explicit_backend_overrides_default(monkeypatch):
    monkeypatch.setenv("DEPLOY_TARGET", "azure")
    monkeypatch.setenv("LLM_BACKEND", "mock")  # overstyr
    cfg = load_settings()
    assert cfg.llm_backend == "mock"
    assert cfg.stt_backend == "azure"  # ikke overstyrt -> azure-default


# --------------------------------------------------------------------------- #
# STT-pluggability                                                             #
# --------------------------------------------------------------------------- #
def test_stt_mock_loads_sample(salg):
    assert salg.name == "salg_alarm"
    assert salg.call_type == "salg"
    assert len(salg.turns) > 5
    assert salg.turns[0].speaker == "agent"


def test_stt_unknown_sample_raises():
    with pytest.raises(FileNotFoundError):
        stt.transcribe("finnes_ikke", cfg=make_settings())


def test_stt_azure_backend_selected_but_guarded():
    """Bytte til azure-backend: koden peker på Azure-stien, men feiler tydelig
    uten nøkkel (i stedet for å gjøre noe stille). Beviser pluggability."""
    cfg = make_settings(stt_backend="azure")
    assert stt.active_backend(cfg) == "azure"
    with pytest.raises(RuntimeError):
        stt.transcribe("salg_alarm", cfg=cfg)


def test_list_samples_returns_both():
    names = {t.name for t in stt.list_samples()}
    assert {"salg_alarm", "kundeservice_faktura"} <= names


# --------------------------------------------------------------------------- #
# LLM-pluggability + determinisme                                              #
# --------------------------------------------------------------------------- #
def test_mock_analysis_is_deterministic(salg):
    cfg = make_settings()
    a1 = llm.analyze(salg, cfg=cfg)
    a2 = llm.analyze(salg, cfg=cfg)
    assert a1.model_dump() == a2.model_dump()


def test_llm_azure_backend_selected_but_guarded(salg):
    cfg = make_settings(llm_backend="azure-openai")
    assert llm.active_backend(cfg) == "azure-openai"
    with pytest.raises(RuntimeError):
        llm.analyze(salg, cfg=cfg)


def test_unknown_llm_backend_raises(salg):
    cfg = make_settings(llm_backend="bogus")
    with pytest.raises(ValueError):
        llm.analyze(salg, cfg=cfg)


# --------------------------------------------------------------------------- #
# Analyse-innhold                                                              #
# --------------------------------------------------------------------------- #
def test_salg_analysis_fields(salg):
    a = llm.analyze(salg, cfg=make_settings())
    assert a.backend == "mock"
    assert a.sentiment in ("positiv", "nøytral", "negativ")
    assert "alarm" in a.summary.lower() or "salg" in a.summary.lower()
    assert a.key_info.intent
    assert a.key_info.next_step
    assert len(a.follow_up) >= 1


def test_service_sentiment_resolved_not_negative(service):
    """Klage som løses -> ikke negativ (kreditert/korrigert)."""
    a = llm.analyze(service, cfg=make_settings())
    assert a.sentiment in ("positiv", "nøytral")


# --------------------------------------------------------------------------- #
# QA-scorecard-logikk                                                          #
# --------------------------------------------------------------------------- #
def test_scorecard_has_six_checklist_items(salg):
    a = llm.analyze(salg, cfg=make_settings())
    keys = {i.key for i in a.scorecard.items}
    assert keys == {
        "hilsen",
        "identifisering",
        "behovskartlegging",
        "losning",
        "samtykke",
        "avslutning",
    }


def test_scorecard_percent_matches_total(salg):
    a = llm.analyze(salg, cfg=make_settings())
    sc = a.scorecard
    assert sc.max_score == 6
    assert sc.total == sum(i.score for i in sc.items)
    assert sc.percent == round(100 * sc.total / sc.max_score)
    assert 0 <= sc.percent <= 100


def test_scorecard_scores_are_binary(salg):
    a = llm.analyze(salg, cfg=make_settings())
    for item in a.scorecard.items:
        assert item.score in (0, 1)


def test_salg_call_scores_high(salg):
    """Velstrukturert salgsanrop bør score høyt (hilsen, behov, løsning, avslutning)."""
    a = llm.analyze(salg, cfg=make_settings())
    assert a.scorecard.total >= 5


def test_coerce_analysis_fills_missing_items():
    """Ekte-LLM-mapping fyller manglende sjekkpunkter som 0."""
    raw = {
        "summary": "x",
        "sentiment": "positiv",
        "scorecard": {"items": [{"key": "hilsen", "label": "H", "score": 1, "evidence": "ok"}]},
        "key_info": {"intent": "i"},
        "compliance_flags": [],
        "follow_up": [],
    }
    a = llm._coerce_analysis(raw, backend="anthropic")
    assert len(a.scorecard.items) == 6  # resten fylt med 0
    assert a.scorecard.total == 1
    assert a.backend == "anthropic"
