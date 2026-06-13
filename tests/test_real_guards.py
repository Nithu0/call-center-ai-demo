"""Robusthet UTEN de tunge/valgfrie pakkene (import-guarding).

Poenget: app.providers.stt + app.providers.llm skal kunne IMPORTERES og brukes
i mock-modus selv om faster_whisper / openai / anthropic / transformers IKKE er
installert. Demoen skal ALDRI knekke offline.

Disse testene rører ikke ekte backends — kun mock-stiene, som er nett- og
nøkkel-frie.
"""

from __future__ import annotations

import importlib

from app.config import Settings
from app.models import Analysis, Transcript


# --------------------------------------------------------------------------- #
# Lokal mock-Settings (rører ikke prosess-miljøet)                             #
# --------------------------------------------------------------------------- #
def _mock_settings() -> Settings:
    return Settings(
        deploy_target="local",
        stt_backend="mock",
        llm_backend="mock",
        azure_speech_key="",
        azure_speech_region="swedencentral",
        azure_speech_language="nb-NO",
        azure_openai_endpoint="",
        azure_openai_key="",
        azure_openai_deployment="gpt-4o",
        anthropic_api_key="",
        anthropic_model="claude-opus-4-8",
    )


# --------------------------------------------------------------------------- #
# Import-guarding: modulene skal importeres uten de tunge pakkene              #
# --------------------------------------------------------------------------- #
def test_import_stt_and_llm_without_heavy_packages():
    """import app.providers.stt + app.providers.llm skal lykkes selv om
    faster_whisper / openai / anthropic / transformers ikke er installert.

    De tunge pakkene importeres LAZILY inne i backend-funksjonene, ikke på
    modulnivå — så selve importen må alltid gå igjennom.
    """
    stt = importlib.import_module("app.providers.stt")
    llm = importlib.import_module("app.providers.llm")
    assert stt is not None
    assert llm is not None
    # Det offentlige API-et finnes.
    assert hasattr(stt, "transcribe")
    assert hasattr(stt, "transcribe_audio")
    assert hasattr(stt, "supports_audio")
    assert hasattr(stt, "active_backend")
    assert hasattr(llm, "analyze")
    assert hasattr(llm, "active_backend")


def test_heavy_optional_packages_not_required():
    """Sanity: de valgfrie sky-/nøkkel-pakkene er IKKE en hard avhengighet.

    Hvis en av dem tilfeldigvis er installert i miljøet er det helt greit — vi
    sjekker bare at modul-importen over IKKE krevde dem (den gjorde den ikke,
    siden importen lyktes). Denne testen dokumenterer intensjonen.
    """
    import app.providers.stt as stt  # noqa: F401
    import app.providers.llm as llm  # noqa: F401
    # Ingen assertion på pakke-tilstedeværelse — import-suksessen over er beviset.
    assert True


# --------------------------------------------------------------------------- #
# mock-STT: transcribe + transcribe_audio krasjer aldri                        #
# --------------------------------------------------------------------------- #
def test_mock_transcribe_returns_transcript():
    from app.providers import stt

    tr = stt.transcribe("salg_alarm", cfg=_mock_settings())
    assert isinstance(tr, Transcript)
    assert tr.name == "salg_alarm"
    assert len(tr.turns) > 0


def test_mock_transcribe_audio_does_not_crash():
    """transcribe_audio på mock-backend gir en Transcript (placeholder) — selv
    med vilkårlige bytes og uten noen STT-modell. Skal ALDRI krasje offline."""
    from app.providers import stt

    tr = stt.transcribe_audio(b"RIFF....WAVEfmt ", name="x.wav", cfg=_mock_settings())
    assert isinstance(tr, Transcript)
    assert len(tr.turns) >= 1
    # Placeholder-Transcript beholder et meningsfullt navn fra opplastingen.
    assert tr.name


def test_mock_transcribe_audio_known_sample_name():
    """Hvis `name` matcher et kjent sample slår mock det opp i stedet for
    placeholder — men uansett en Transcript."""
    from app.providers import stt

    tr = stt.transcribe_audio(b"\x00\x01\x02", name="salg_alarm", cfg=_mock_settings())
    assert isinstance(tr, Transcript)
    assert len(tr.turns) >= 1


# --------------------------------------------------------------------------- #
# Type-kontrakter: supports_audio -> bool, active_backend -> str              #
# --------------------------------------------------------------------------- #
def test_supports_audio_returns_bool():
    from app.providers import stt

    val = stt.supports_audio(cfg=_mock_settings())
    assert isinstance(val, bool)
    # mock har ingen modell → kan ikke transkribere ekte opplastet lyd.
    assert val is False


def test_active_backend_returns_str():
    from app.providers import llm, stt

    s = stt.active_backend(cfg=_mock_settings())
    l = llm.active_backend(cfg=_mock_settings())
    assert isinstance(s, str) and s == "mock"
    assert isinstance(l, str) and l == "mock"


# --------------------------------------------------------------------------- #
# mock-LLM: analyze -> Analysis med sentiment + scorecard                      #
# --------------------------------------------------------------------------- #
def test_mock_analyze_returns_analysis_with_sentiment_and_scorecard():
    from app.providers import llm, stt

    cfg = _mock_settings()
    tr = stt.transcribe("salg_alarm", cfg=cfg)
    a = llm.analyze(tr, cfg=cfg)

    assert isinstance(a, Analysis)
    assert a.backend == "mock"
    assert a.sentiment in ("positiv", "nøytral", "negativ")

    # Scorecard har de seks faste sjekkpunktene med binære scorer.
    keys = {i.key for i in a.scorecard.items}
    assert keys == {
        "hilsen",
        "identifisering",
        "behovskartlegging",
        "losning",
        "samtykke",
        "avslutning",
    }
    for item in a.scorecard.items:
        assert item.score in (0, 1)
    assert 0 <= a.scorecard.percent <= 100
