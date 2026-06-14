#!/usr/bin/env python3
"""gen_elevenlabs_audio.py — realistiske norske stemmer for sample-samtaler (ElevenLabs TTS).

Lager profesjonell, naturlig samtale-lyd: agent og kunde får hver sin stemme,
replikkene syntetiseres og settes sammen til én lydfil per samtale. Mye bedre
enn robot-TTS (gTTS) — gjør live-/opplastings-demoen troverdig.

Krever ELEVENLABS_API_KEY. Bruker httpx (ingen ekstra pakke).

Bruk (fra prosjektroten):
    .venv/bin/python scripts/gen_elevenlabs_audio.py --list-voices     # se tilgjengelige stemmer
    .venv/bin/python scripts/gen_elevenlabs_audio.py --call salg_alarm
    .venv/bin/python scripts/gen_elevenlabs_audio.py --all

Stemmer styres av ELEVENLABS_VOICE_AGENT / ELEVENLABS_VOICE_KUNDE (voice-id-er).
Modell via ELEVENLABS_TTS_MODEL (default eleven_multilingual_v2 — støtter norsk).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
AUDIO_DIR = DATA_DIR / "audio"
API = "https://api.elevenlabs.io/v1"

# Standard offentlige ElevenLabs-stemmer (kan overstyres via env). Sjekk dine egne
# med --list-voices hvis disse ikke finnes på kontoen din.
VOICE_AGENT = os.environ.get("ELEVENLABS_VOICE_AGENT", "JBFqnCBsd6RMkjVDRZzb")  # "George"
VOICE_KUNDE = os.environ.get("ELEVENLABS_VOICE_KUNDE", "EXAVITQu4vr4xnSDxMaL")  # "Sarah"
TTS_MODEL = os.environ.get("ELEVENLABS_TTS_MODEL", "eleven_multilingual_v2")


def _client():
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        print("Mangler ELEVENLABS_API_KEY. Sett den i miljøet/.env og prøv igjen.")
        sys.exit(1)
    try:
        import httpx
    except ImportError:
        print("httpx mangler. Kjør: .venv/bin/pip install httpx")
        sys.exit(1)
    return httpx, key


def list_voices() -> int:
    httpx, key = _client()
    r = httpx.get(f"{API}/voices", headers={"xi-api-key": key}, timeout=30)
    r.raise_for_status()
    for v in r.json().get("voices", []):
        print(f"  {v.get('voice_id')}  {v.get('name')}  ({v.get('labels', {}).get('language', '—')})")
    print("\nSett ELEVENLABS_VOICE_AGENT / ELEVENLABS_VOICE_KUNDE til ønskede id-er.")
    return 0


def _tts(httpx, key: str, text: str, voice_id: str) -> bytes:
    r = httpx.post(
        f"{API}/text-to-speech/{voice_id}",
        headers={"xi-api-key": key, "Accept": "audio/mpeg"},
        json={"text": text, "model_id": TTS_MODEL},
        timeout=120,
    )
    r.raise_for_status()
    return r.content


def gen_call(name: str, force: bool) -> bool:
    out = AUDIO_DIR / f"{name}.mp3"
    if out.exists() and not force:
        print(f"  hopper over {name} (finnes; bruk --force)")
        return True
    src = DATA_DIR / f"{name}.json"
    if not src.exists():
        print(f"  fant ikke data/{name}.json")
        return False
    turns = json.loads(src.read_text(encoding="utf-8")).get("turns", [])
    httpx, key = _client()
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    chunks: list[bytes] = []
    for t in turns:
        voice = VOICE_AGENT if t.get("speaker") == "agent" else VOICE_KUNDE
        text = (t.get("text") or "").strip()
        if text:
            chunks.append(_tts(httpx, key, text, voice))
    if not chunks:
        print(f"  {name}: ingen replikker")
        return False
    out.write_bytes(b"".join(chunks))  # binær mp3-konkat (ingen ffmpeg nødvendig)
    print(f"  ✓ {out}  ({len(turns)} replikker, {out.stat().st_size // 1024} KB)")
    return True


def _all_calls() -> list[str]:
    return sorted(p.stem for p in DATA_DIR.glob("*.json") if not p.name.startswith("_"))


def main() -> int:
    ap = argparse.ArgumentParser(description="Realistiske norske stemmer (ElevenLabs TTS).")
    ap.add_argument("--call", default="salg_alarm")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--list-voices", action="store_true")
    args = ap.parse_args()

    if args.list_voices:
        return list_voices()
    calls = _all_calls() if args.all else [args.call]
    print(f"Genererer ElevenLabs-lyd ({TTS_MODEL}) for {len(calls)} samtale(r)…")
    ok = all(gen_call(c, args.force) for c in calls)
    print("Ferdig." if ok else "Ferdig (noen feilet).")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
