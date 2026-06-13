#!/usr/bin/env python3
"""Generer NORSK testlyd for ALLE samtaler i data/*.json -> data/audio/<navn>.

Samle-script: leser hvert samtale-transkript i `data/<navn>.json`
(skjema: {"turns": [{"speaker": ..., "text": ...}, ...]}), slår replikkene
sammen til én norsk monolog og syntetiserer tale til én lydfil per samtale.
Filer med `_`-prefiks (f.eks. `_labels.json`) hoppes over — de er ikke
transkripter.

Hensikten er å gjøre "last opp lyd -> /transcribe -> verify_stt"-veien
kjørbar på EKTE norsk lyd UTEN mikrofon.

TTS-backend (lazy import — IKKE i requirements.txt, valgfritt):
  1. gTTS     -> data/audio/<navn>.mp3   (online, Google TTS, lang="no"/"nb")
  2. pyttsx3  -> data/audio/<navn>.wav   (offline, systemstemme — fallback)

Ingen TTS-pakke installert/fungerende -> tydelig melding + exit-kode 1.
(`--help` og innlesing/sammenslåing virker uansett — krasjer ikke uten TTS.)

Idempotent: hopper over samtaler som allerede har en lydfil, med mindre
`--force` er satt.

Bruk:
    python scripts/gen_all_audio.py --all                 # alle samtaler
    python scripts/gen_all_audio.py --call salg_alarm     # én samtale
    python scripts/gen_all_audio.py --all --force         # overskriv
    python scripts/gen_all_audio.py --all --out /tmp/lyd  # annet utdata-dir
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DEFAULT_AUDIO_DIR = DATA_DIR / "audio"


# --------------------------------------------------------------------------- #
# Innlesing / sammenslåing
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


def merge_turns(data: dict) -> str:
    """Slå sammen alle replikkene til én norsk monolog (i rekkefølge).

    Linjeskift mellom replikker gir et naturlig opphold i TTS-en.
    """
    parts: list[str] = []
    for turn in data.get("turns", []):
        text = (turn or {}).get("text", "").strip()
        if text:
            parts.append(text)
    return "\n".join(parts)


def discover_calls() -> list[str]:
    """Alle data/*.json som ser ut som transkripter (har 'turns', ikke `_`-prefiks)."""
    names: list[str] = []
    for path in sorted(DATA_DIR.glob("*.json")):
        if path.stem.startswith("_"):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(data.get("turns"), list) and data["turns"]:
            names.append(path.stem)
    return names


# --------------------------------------------------------------------------- #
# TTS-backends (lazy import — guard mot manglende pakker)
# --------------------------------------------------------------------------- #
def _gen_gtts(data: dict, out_base: Path) -> Path:
    """gTTS -> én MP3. Skjøter per-replikk-MP3 binært sammen (ingen ffmpeg).

    MP3-rammer kan trygt konkateneres binært; whisper/ffmpeg og de fleste
    spillere dekoder den sammenslåtte strømmen som én sammenhengende lyd.
    Prøver lang="no", faller tilbake til "nb" om "no" ikke godtas.
    """
    from gtts import gTTS  # lazy

    out = out_base.with_suffix(".mp3")
    turns = [(t or {}).get("text", "").strip() for t in data.get("turns", [])]
    turns = [t for t in turns if t]

    for lang in ("no", "nb"):
        try:
            with out.open("wb") as fh:
                for text in turns:
                    gTTS(text=text, lang=lang).write_to_fp(fh)
            return out
        except ValueError:
            # ugyldig språk-kode for denne gTTS-versjonen -> prøv neste
            continue
    # siste forsøk: la feilen propagere med "no"
    with out.open("wb") as fh:
        for text in turns:
            gTTS(text=text, lang="no").write_to_fp(fh)
    return out


def _gen_pyttsx3(data: dict, out_base: Path) -> Path:
    """pyttsx3 -> én WAV (offline). Syntetiserer hele monologen i ett pass."""
    import pyttsx3  # lazy

    out = out_base.with_suffix(".wav")
    engine = pyttsx3.init()
    # Velg norsk stemme hvis systemet har en.
    for voice in engine.getProperty("voices"):
        meta = f"{getattr(voice, 'id', '')} {getattr(voice, 'name', '')}".lower()
        if "nor" in meta or "nb" in meta or "/no" in meta:
            engine.setProperty("voice", voice.id)
            break
    engine.save_to_file(merge_turns(data), str(out))
    engine.runAndWait()
    return out


BACKENDS = {"gtts": _gen_gtts, "pyttsx3": _gen_pyttsx3}
BACKEND_ORDER = ["gtts", "pyttsx3"]
# Suffikser en backend kan produsere — for idempotent skip-sjekk.
POSSIBLE_SUFFIXES = (".mp3", ".wav")


def existing_audio(out_dir: Path, name: str) -> Path | None:
    """Returner eksisterende lydfil for `name` i out_dir, om noen finnes."""
    for suffix in POSSIBLE_SUFFIXES:
        candidate = out_dir / f"{name}{suffix}"
        if candidate.exists():
            return candidate
    return None


def synth_one(data: dict, out_base: Path) -> Path:
    """Generer lyd for én (allerede innlest) samtale med første fungerende backend."""
    errors: list[str] = []
    for backend in BACKEND_ORDER:
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
        description="Generer norsk testlyd for alle (eller én) samtale i data/*.json.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Eksempler:\n"
            "  python scripts/gen_all_audio.py --all\n"
            "  python scripts/gen_all_audio.py --call salg_alarm\n"
            "  python scripts/gen_all_audio.py --all --force\n"
            "\n"
            "Lydfilene brukes mot POST /transcribe (STT_BACKEND=faster-whisper)\n"
            "for å kjøre verify_stt på ekte norsk lyd uten mikrofon."
        ),
    )
    ap.add_argument("--call", default=None, help="Generer kun denne samtalen (data/<navn>.json).")
    ap.add_argument("--all", action="store_true", help="Generer for alle samtaler i data/.")
    ap.add_argument(
        "--out",
        default=None,
        help=f"Utdata-mappe (default: {DEFAULT_AUDIO_DIR}).",
    )
    ap.add_argument("--force", action="store_true", help="Overskriv lydfiler som finnes fra før.")
    args = ap.parse_args()

    if not args.all and not args.call:
        ap.error("Oppgi --all eller --call <navn>.")

    out_dir = Path(args.out) if args.out else DEFAULT_AUDIO_DIR

    if args.all:
        names = discover_calls()
        if not names:
            print("Fant ingen samtale-transkripter i data/.", file=sys.stderr)
            return 1
    else:
        names = [args.call]

    # Les + slå sammen først (virker uten TTS) — rapporter ugyldige tidlig.
    loaded: list[tuple[str, dict]] = []
    skipped: list[str] = []
    for name in names:
        try:
            data = load_call(name)
        except (FileNotFoundError, ValueError) as e:
            print(f"HOPPER OVER {name}: {e}", file=sys.stderr)
            skipped.append(name)
            continue
        merged = merge_turns(data)
        print(f"Klargjort {name}: {len(data['turns'])} replikker, {len(merged)} tegn.")
        loaded.append((name, data))

    if not loaded:
        print("Ingen gyldige samtaler å generere.", file=sys.stderr)
        return 1

    out_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    already: list[Path] = []
    last_err = ""
    for name, data in loaded:
        if not args.force:
            existing = existing_audio(out_dir, name)
            if existing is not None:
                print(f"FINNES (hopper over, bruk --force): {existing}")
                already.append(existing)
                continue
        out_base = out_dir / name
        try:
            path = synth_one(data, out_base)
            print(f"OK: {name} -> {path}")
            written.append(path)
        except RuntimeError as e:
            last_err = str(e)
            break  # ingen backend -> ingen vits å fortsette

    print(
        f"\nOppsummering: {len(written)} generert, {len(already)} fantes fra før, "
        f"{len(skipped)} hoppet over."
    )
    if written:
        print(
            f"Lydfiler i {out_dir}. Test ekte STT:\n"
            f"  STT_BACKEND=faster-whisper curl -F audio=@{written[0]} "
            "http://localhost:8000/transcribe"
        )

    if last_err:
        print("\n" + last_err, file=sys.stderr)
        return 1
    if not written and not already:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
