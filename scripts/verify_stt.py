#!/usr/bin/env python3
"""Verifiser at EKTE STT (tale-til-tekst) fungerer på en lydfil.

Kjører den aktive STT-backenden (eller en valgt) mot en faktisk lydfil og
skriver ut backend, transkript og hvor mange sekunder transkripsjonen tok.
Bruker app/providers/stt.py — IKKE faster_whisper direkte (importen der er
guardet, så vi knekker aldri om pakken mangler).

Mangler en backend sin pakke/nøkkel? Da gir vi en tydelig melding om hva som
må installeres/settes, og avslutter pent (exit 0) — dette er et verifikasjons-
script, ikke en feiltest.

Bruk:
    python scripts/verify_stt.py data/audio/realtest.mp3
    python scripts/verify_stt.py realtest               # sample-navn under data/audio/
    python scripts/verify_stt.py realtest --backend faster-whisper --model small
    python scripts/verify_stt.py realtest --all-backends # sammenlign alle tilgjengelige

Flagg:
    --backend       overstyr STT_BACKEND for denne kjøringen
    --model         sett FASTER_WHISPER_MODEL (f.eks. tiny/base/small/medium)
    --all-backends  prøv faster-whisper, nb-whisper og openai på samme fil og
                    skriv ut hvert transkript + tid (hopp over utilgjengelige)
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

# Gjør app-pakken importérbar uansett hvor scriptet kjøres fra.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

AUDIO_DIR = ROOT / "data" / "audio"

# Ekte backends (mock teller ikke som "ekte STT").
REAL_BACKENDS = ["faster-whisper", "nb-whisper", "openai"]


def _resolve_path(audio_or_name: str) -> Path | None:
    """Løs en sti ELLER et sample-navn (data/audio/<navn>.<ext>) -> Path.

    Returnerer None hvis ingenting finnes (kalleren skriver feilmelding).
    """
    p = Path(audio_or_name)
    if p.exists():
        return p
    for ext in (".wav", ".mp3", ".m4a", ".ogg", ".flac"):
        cand = AUDIO_DIR / f"{audio_or_name}{ext}"
        if cand.exists():
            return cand
    return None


def _run_one(stt, audio_path: Path, backend: str, cfg) -> bool:
    """Kjør én backend mot fila. Returner True ved suksess, False ved hopp/feil.

    Skriver alt direkte til stdout. Fanger forventede mangler (pakke/nøkkel) og
    rapporterer dem tydelig uten å la scriptet krasje.
    """
    print(f"\n=== backend: {backend} ===")
    try:
        raw = audio_path.read_bytes()
    except OSError as e:
        print(f"  Kunne ikke lese lydfila: {e}")
        return False

    t0 = time.perf_counter()
    try:
        tr = stt.transcribe_audio(raw, name=audio_path.name, cfg=cfg)
    except RuntimeError as e:
        # Typisk: manglende API-nøkkel (openai/azure) eller manglende SDK.
        print(f"  Hopper over — {e}")
        return False
    except NotImplementedError as e:
        print(f"  Hopper over — {e}")
        return False
    except FileNotFoundError:
        # Ekte backend manglet pakken -> falt tilbake til mock, som så lette
        # etter et sample-transkript for temp-fila og ikke fant det. Den EKTE
        # årsaken er at backend-pakken ikke er installert (se advarselen over).
        hint = {
            "faster-whisper": "pip install faster-whisper",
            "nb-whisper": "pip install transformers torch",
            "openai": "pip install openai  (+ OPENAI_API_KEY)",
        }.get(backend, "installer backend-pakken")
        print(f"  Hopper over — {backend}-pakken er ikke installert ({hint}).")
        return False
    except Exception as e:  # noqa: BLE001 - verifikasjonsscript: rapportér, ikke krasj
        print(f"  Feil under transkripsjon ({type(e).__name__}): {e}")
        return False
    secs = time.perf_counter() - t0

    # full_text er en @property på Transcript (ikke en metode).
    text = tr.full_text if hasattr(tr, "full_text") else str(tr)
    # mock-backend forklarer seg selv i teksten; vis en hint hvis vi havnet der.
    if backend != "mock" and "mock-STT" in text:
        print(
            "  (NB: backend falt tilbake til mock — pakken er sannsynligvis "
            "ikke installert. Se advarselen over.)"
        )

    print(f"  tid: {secs:.2f} s")
    print(f"  tittel: {tr.title}")
    print("  transkript:")
    print("    " + text.replace("\n", "\n    "))
    return True


def _make_cfg(backend: str | None):
    """Lag en Settings med valgt backend (eller dagens aktive om None)."""
    from app.config import load_settings

    if backend:
        os.environ["STT_BACKEND"] = backend
    # Les på nytt slik at env-overstyringer (STT_BACKEND/FASTER_WHISPER_MODEL)
    # plukkes opp — modul-singletonen ble låst ved import.
    return load_settings()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verifiser ekte STT på en lydfil (backend + transkript + tid).",
    )
    parser.add_argument(
        "audio",
        help="Sti til lydfil ELLER sample-navn under data/audio/ (f.eks. realtest).",
    )
    parser.add_argument(
        "--backend",
        help="Overstyr STT_BACKEND (mock/faster-whisper/nb-whisper/openai/azure).",
    )
    parser.add_argument(
        "--model",
        help="Sett FASTER_WHISPER_MODEL (tiny/base/small/medium/large-v3).",
    )
    parser.add_argument(
        "--all-backends",
        action="store_true",
        help="Prøv alle ekte backends på samme fil og sammenlign.",
    )
    args = parser.parse_args(argv)

    if args.model:
        os.environ["FASTER_WHISPER_MODEL"] = args.model

    audio_path = _resolve_path(args.audio)
    if audio_path is None:
        print(
            f"Fant ikke lydfil for {args.audio!r}. Oppgi en sti eller et navn "
            f"under {AUDIO_DIR}.\n"
            "Tips: generer en demo-fil med `python scripts/gen_audio.py`."
        )
        return 0  # pent: ingen fil å verifisere mot er ikke en hard feil

    from app.providers import stt

    print(f"Lydfil: {audio_path}  ({audio_path.stat().st_size} bytes)")
    if args.model:
        print(f"FASTER_WHISPER_MODEL = {args.model}")

    if args.all_backends:
        any_ok = False
        for backend in REAL_BACKENDS:
            cfg = _make_cfg(backend)
            ok = _run_one(stt, audio_path, backend, cfg)
            any_ok = any_ok or ok
        if not any_ok:
            print(
                "\nIngen ekte backend var tilgjengelig. Installer minst én:\n"
                "  pip install faster-whisper            # lokal Whisper (anbefalt offline)\n"
                "  pip install transformers torch        # NB-Whisper (norsk-tunet)\n"
                "  pip install openai + OPENAI_API_KEY   # OpenAI Whisper API (sky)"
            )
        return 0

    # Enkelt-backend (valgt eller aktiv).
    cfg = _make_cfg(args.backend)
    backend = cfg.stt_backend
    print(f"Aktiv STT_BACKEND: {backend}")
    if backend == "mock":
        print(
            "\nNB: backend er 'mock' (ingen ekte modell). For EKTE transkripsjon, "
            "velg en backend:\n"
            "  --backend faster-whisper   (pip install faster-whisper)\n"
            "  --backend nb-whisper       (pip install transformers torch)\n"
            "  --backend openai           (pip install openai + OPENAI_API_KEY)"
        )
    _run_one(stt, audio_path, backend, cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
