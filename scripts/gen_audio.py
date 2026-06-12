#!/usr/bin/env python3
"""Generer en kort NORSK lyd-sample til ekte STT-testing.

Poenget: gi `STT_BACKEND=faster-whisper` (eller nb-whisper/azure) en faktisk
lydfil å transkribere, slik at ekte transkripsjon kan demonstreres.

TTS-backend (lazy import, valgfri — IKKE i requirements.txt):
  1. gTTS      -> data/audio/demo_no.mp3   (krever nett — Google TTS)
  2. pyttsx3   -> data/audio/demo_no.wav   (offline, systemstemme)

Ingen av delene installert -> tydelig melding + exit-kode 1 (knekker ikke import
av app-en; dette er et frittstående script).

Bruk:
    python scripts/gen_audio.py
    python scripts/gen_audio.py --text "Egen norsk setning her."
    python scripts/gen_audio.py --backend pyttsx3
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

AUDIO_DIR = Path(__file__).resolve().parent.parent / "data" / "audio"

DEFAULT_TEXT = (
    "Hei, du snakker med Sondre fra TryggHjem Sikkerhet. "
    "Vi har en kampanje på boligalarm i ditt nabolag akkurat nå. "
    "Komplett-pakken koster tre hundre og nittini kroner i måneden, "
    "og installasjonen er gratis i kampanjeperioden. "
    "Ja, det høres greit ut, men jeg må diskutere det med mannen min først."
)


def _gen_gtts(text: str, out: Path) -> Path:
    from gtts import gTTS  # lazy

    out = out.with_suffix(".mp3")
    gTTS(text=text, lang="no").save(str(out))
    return out


def _gen_pyttsx3(text: str, out: Path) -> Path:
    import pyttsx3  # lazy

    out = out.with_suffix(".wav")
    engine = pyttsx3.init()
    # Prøv en norsk stemme hvis tilgjengelig på systemet.
    for voice in engine.getProperty("voices"):
        meta = f"{getattr(voice, 'id', '')} {getattr(voice, 'name', '')}".lower()
        if "nor" in meta or "nb" in meta or "/no" in meta:
            engine.setProperty("voice", voice.id)
            break
    engine.save_to_file(text, str(out))
    engine.runAndWait()
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Generer norsk demo-lyd for STT.")
    ap.add_argument("--text", default=DEFAULT_TEXT, help="Norsk tekst å syntetisere.")
    ap.add_argument(
        "--backend",
        choices=("auto", "gtts", "pyttsx3"),
        default="auto",
        help="TTS-backend (auto prøver gTTS, så pyttsx3).",
    )
    ap.add_argument(
        "--out",
        default=str(AUDIO_DIR / "demo_no"),
        help="Utdata-sti uten suffiks (suffiks settes av backend).",
    )
    args = ap.parse_args()

    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    out_base = Path(args.out)

    order = (
        ["gtts", "pyttsx3"]
        if args.backend == "auto"
        else [args.backend]
    )

    errors: list[str] = []
    for backend in order:
        try:
            if backend == "gtts":
                written = _gen_gtts(args.text, out_base)
            else:
                written = _gen_pyttsx3(args.text, out_base)
        except ImportError as e:
            errors.append(f"  - {backend}: ikke installert ({e})")
            continue
        except Exception as e:  # nett-feil (gTTS) e.l. — prøv neste backend
            errors.append(f"  - {backend}: feilet ({e})")
            continue

        print(f"OK: skrev {written}")
        print(
            "Test ekte STT:\n"
            f"  STT_BACKEND=faster-whisper python -c "
            f"\"from app.providers.stt import transcribe; "
            f"print(transcribe('{written}').full_text)\""
        )
        return 0

    print("Ingen TTS-backend tilgjengelig. Installer én av:", file=sys.stderr)
    print("  pip install gtts       # online, mp3", file=sys.stderr)
    print("  pip install pyttsx3    # offline, wav", file=sys.stderr)
    if errors:
        print("Detaljer:", file=sys.stderr)
        print("\n".join(errors), file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
