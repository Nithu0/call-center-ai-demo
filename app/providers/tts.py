"""TTS-lag — gjør agent-replikker til hørbar tale (ElevenLabs).

Brukes av /samtale (live salgssamtale) så AI-agenten faktisk SNAKKER mens den
prøver å selge. Samme nøkkel som STT (ELEVENLABS_API_KEY).

Ingen nøkkel → `synthesize()` returnerer None, og frontend faller tilbake til
nettleserens egen talesyntese (speechSynthesis, nb-NO). Demoen virker uansett.
"""
from __future__ import annotations

import os

_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice}"
VOICE_AGENT_DEFAULT = "JBFqnCBsd6RMkjVDRZzb"  # "George" — varm, fortellende
VOICE_KUNDE_DEFAULT = "EXAVITQu4vr4xnSDxMaL"  # "Sarah"  — moden, trygg


def active_backend() -> str:
    """'elevenlabs' hvis nøkkel finnes, ellers 'browser' (speechSynthesis)."""
    return "elevenlabs" if os.environ.get("ELEVENLABS_API_KEY") else "browser"


def available() -> bool:
    return bool(os.environ.get("ELEVENLABS_API_KEY"))


def _voice_for(speaker: str) -> str:
    if speaker == "kunde":
        return os.environ.get("ELEVENLABS_VOICE_KUNDE", VOICE_KUNDE_DEFAULT)
    return os.environ.get("ELEVENLABS_VOICE_AGENT", VOICE_AGENT_DEFAULT)


def synthesize(text: str, speaker: str = "agent") -> bytes | None:
    """mp3-bytes for teksten, eller None (ingen nøkkel / pakke / nettfeil).

    None er ikke en feil — det er signalet til frontend om å bruke
    nettleserens egen tale i stedet, så demoen aldri står stille.
    """
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key or not text.strip():
        return None
    try:
        import httpx
    except ImportError:  # pragma: no cover
        return None
    model = os.environ.get("ELEVENLABS_TTS_MODEL", "eleven_multilingual_v2")
    try:
        r = httpx.post(
            _TTS_URL.format(voice=_voice_for(speaker)),
            headers={"xi-api-key": key, "Accept": "audio/mpeg"},
            json={"text": text, "model_id": model},
            timeout=60,
        )
        r.raise_for_status()
        return r.content
    except Exception:  # pragma: no cover — fail soft til browser-tale
        return None
