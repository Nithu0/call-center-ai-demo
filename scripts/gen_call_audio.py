#!/usr/bin/env python3
"""Generer NORSK tale av en hel samtale-transkript -> én lydfil per samtale.

Formål: gjøre "last opp lyd -> transkriber"-veien demonstrerbar UTEN mikrofon.
Vi leser et eksisterende samtale-transkript fra `data/<navn>.json`
(skjema: {"turns": [{"speaker": ..., "text": ...}, ...]}), syntetiserer norsk
tale av alle replikkene, slår dem sammen til ÉN lydfil og lagrer den under
`data/audio/<navn>.mp3` (gTTS) eller `data/audio/<navn>.wav` (pyttsx3).

Filene mates så mot:  POST /transcribe   (med STT_BACKEND=faster-whisper)
slik at ekte norsk transkripsjon kan demonstreres.

TTS-backend (lazy import, valgfri — IKKE i requirements.txt):
  1. gTTS     -> data/audio/<navn>.mp3   (krever nett — Google TTS, lang="no")
  2. pyttsx3  -> data/audio/<navn>.wav   (offline, systemstemme)

Ingen TTS-pakke installert -> tydelig melding + exit-kode 1. (--help virker
uansett.) Dette er et frittstående script; det knekker ikke import av app-en.

Bruk:
    python scripts/gen_call_audio.py                  # salg_alarm (default)
    python scripts/gen_call_audio.py --call inkasso_betaling
    python scripts/gen_call_audio.py --all            # alle data/*.json
    python scripts/gen_call_audio.py --backend pyttsx3
    python scripts/gen_call_audio.py --call salg_alarm --out data/audio/min.mp3
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
AUDIO_DIR = DATA_DIR / "audio"

# Filer i data/ som IKKE er samtale-transkripter (skjema-avvik).
SKIP_STEMS = {"_labels"}


# --------------------------------------------------------------------------- #
# Innlesing
# --------------------------------------------------------------------------- #
def load_call(name: str) -> dict:
    """Les data/<name>.json og valider at det ser ut som et transkript."""
    path = DATA_DIR / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"Fant ikke samtale-fil: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    turns = data.get("turns")
    if not isinstance(turns, list) or not turns:
        raise ValueError(f"{path} mangler en ikke-tom 'turns'-liste.")
    return data


def turns_text(data: dict) -> str:
    """Slå sammen alle replikkene til én norsk monolog (i rekkefølge)."""
    parts: list[str] = []
    for turn in data["turns"]:
        text = (turn or {}).get("text", "").strip()
        if text:
            parts.append(text)
    # Pause mellom replikker via setningsskille — gir naturlig opphold i TTS.
    return "  ".join(parts)


def discover_calls() -> list[str]:
    """Alle data/*.json som ser ut som transkripter (har 'turns')."""
    names: list[str] = []
    for path in sorted(DATA_DIR.glob("*.json")):
        if path.stem in SKIP_STEMS:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(data.get("turns"), list) and data["turns"]:
            names.append(path.stem)
    return names


# --------------------------------------------------------------------------- #
# TTS-backends
# --------------------------------------------------------------------------- #
def _gen_gtts(data: dict, out: Path) -> Path:
    """gTTS: syntetiser hver replikk og skjøt sammen MP3-ene til én fil.

    MP3-rammer kan trygt konkateneres binært — ffmpeg/whisper og de fleste
    spillere dekoder den sammenslåtte strømmen som én sammenhengende lyd.
    """
    from gtts import gTTS  # lazy

    out = out.with_suffix(".mp3")
    with out.open("wb") as fh:
        for turn in data["turns"]:
            text = (turn or {}).get("text", "").strip()
            if not text:
                continue
            gTTS(text=text, lang="no").write_to_fp(fh)
    return out


def _gen_pyttsx3(data: dict, out: Path) -> Path:
    """pyttsx3: syntetiser hele monologen i én pass -> én WAV (offline)."""
    import pyttsx3  # lazy

    out = out.with_suffix(".wav")
    engine = pyttsx3.init()
    # Velg en norsk stemme hvis systemet har en.
    for voice in engine.getProperty("voices"):
        meta = f"{getattr(voice, 'id', '')} {getattr(voice, 'name', '')}".lower()
        if "nor" in meta or "nb" in meta or "/no" in meta:
            engine.setProperty("voice", voice.id)
            break
    engine.save_to_file(turns_text(data), str(out))
    engine.runAndWait()
    return out


BACKENDS = {"gtts": _gen_gtts, "pyttsx3": _gen_pyttsx3}


def synth_one(name: str, backend_order: list[str], out_override: Path | None) -> Path:
    """Generer lyd for én samtale med første fungerende backend."""
    data = load_call(name)
    out_base = out_override if out_override is not None else (AUDIO_DIR / name)

    errors: list[str] = []
    for backend in backend_order:
        try:
            return BACKENDS[backend](data, out_base)
        except ImportError as e:
            errors.append(f"  - {backend}: ikke installert ({e})")
        except Exception as e:  # nett-feil (gTTS) e.l. -> prøv neste backend
            errors.append(f"  - {backend}: feilet ({e})")

    raise RuntimeError(
        "Ingen TTS-backend tilgjengelig.\n"
        "Installer én av:\n"
        "  pip install gtts       # online, mp3\n"
        "  pip install pyttsx3    # offline, wav\n"
        "Detaljer:\n" + "\n".join(errors)
    )


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(
        description="Generer norsk tale fra et samtale-transkript (data/<navn>.json).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Eksempler:\n"
            "  python scripts/gen_call_audio.py --call salg_alarm\n"
            "  python scripts/gen_call_audio.py --all\n"
            "\n"
            "Filene brukes mot POST /transcribe med STT_BACKEND=faster-whisper."
        ),
    )
    ap.add_argument("--call", default="salg_alarm", help="Samtale-navn (data/<navn>.json). Default: salg_alarm.")
    ap.add_argument("--all", action="store_true", help="Generer for alle samtaler i data/.")
    ap.add_argument(
        "--backend",
        choices=("auto", "gtts", "pyttsx3"),
        default="auto",
        help="TTS-backend (auto prøver gTTS, så pyttsx3).",
    )
    ap.add_argument(
        "--out",
        default=None,
        help="Utdata-sti (kun med én samtale). Suffiks settes av backend om det mangler.",
    )
    args = ap.parse_args()

    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    backend_order = ["gtts", "pyttsx3"] if args.backend == "auto" else [args.backend]

    if args.all:
        names = discover_calls()
        if not names:
            print("Fant ingen samtale-transkripter i data/.", file=sys.stderr)
            return 1
        out_override = None  # --out gir ikke mening med --all
    else:
        names = [args.call]
        out_override = Path(args.out) if args.out else None

    written: list[Path] = []
    failed: list[str] = []
    last_err = ""
    for name in names:
        try:
            path = synth_one(name, backend_order, out_override)
            print(f"OK: {name} -> {path}")
            written.append(path)
        except (FileNotFoundError, ValueError) as e:
            print(f"HOPPER OVER {name}: {e}", file=sys.stderr)
            failed.append(name)
        except RuntimeError as e:
            last_err = str(e)
            failed.append(name)
            break  # ingen backend -> ingen vits å fortsette

    if written:
        print(
            f"\nFerdig: {len(written)} lydfil(er) i {AUDIO_DIR}.\n"
            "Test ekte STT (last opp mot /transcribe):\n"
            f"  STT_BACKEND=faster-whisper curl -F audio=@{written[0]} http://localhost:8000/transcribe"
        )
        return 0

    if last_err:
        print("\n" + last_err, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
