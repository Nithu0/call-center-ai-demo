#!/usr/bin/env python3
"""Verifiser at LLM-analysen FAKTISK kjører med valgt backend (utenfor mock).

Henter et sample-transkript via STT-laget (mock-oppslag på navn), kjører
`llm.analyze()` med valgt backend, og skriver ut analysen:
backend, sentiment, churn-risiko, scorecard-%, sammendrag og coaching-tips.

Bruk:
    python scripts/verify_llm.py                       # bruker LLM_BACKEND fra env (default mock)
    python scripts/verify_llm.py --backend anthropic   # ekte Anthropic-AI (krever nøkkel + SDK)
    python scripts/verify_llm.py --call salg_alarm      # velg sample-samtale

Hvis backend=anthropic men ANTHROPIC_API_KEY mangler eller `anthropic`-pakken
ikke er installert, skrives en tydelig melding og scriptet avslutter pent
(exit 0) — det krasjer ikke.

NB: dette scriptet importerer ALDRI `anthropic` direkte. Den importeres kun
internt i app/providers/llm.py ved behov.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Sørg for at repo-roten er på sys.path så `import app` virker uansett CWD.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# Standard sample-samtale hvis ingen --call gis. Begge finnes i data/.
DEFAULT_CALL = "vanskelig_sint_kunde"
VALID_BACKENDS = ("mock", "anthropic", "azure-openai")


def _banner(backend: str) -> None:
    """Tydelig topp-banner: hvilken backend, og om det er ekte AI eller mock."""
    if backend == "mock":
        kind = "MOCK (deterministisk, offline — INGEN ekte AI-kall)"
    elif backend == "anthropic":
        kind = "EKTE AI — Anthropic (claude-modell via SDK)"
    elif backend == "azure-openai":
        kind = "EKTE AI — Azure OpenAI"
    else:
        kind = "UKJENT backend"

    line = "=" * 64
    print(line)
    print("  LLM-VERIFISERING — call-center-ai-demo")
    print(f"  Backend : {backend}")
    print(f"  Modus   : {kind}")
    print(line)


def _print_analysis(analysis, transcript) -> None:
    sc = analysis.scorecard
    print()
    print(f"Samtale     : {transcript.name}  ({transcript.call_type})")
    if transcript.title:
        print(f"Tittel      : {transcript.title}")
    print(f"Backend     : {analysis.backend}")
    print(f"Sentiment   : {analysis.sentiment}")
    print(f"Churn-risiko: {analysis.churn_risk}")
    print(
        f"Scorecard   : {sc.percent}%  ({sc.total}/{sc.max_score} punkter)"
        if sc.max_score
        else "Scorecard   : (tomt)"
    )
    if analysis.script_adherence:
        print(f"Manus-%     : {analysis.script_adherence}%")
    print()
    print("Sammendrag:")
    print(f"  {analysis.summary or '(tomt)'}")

    tips = analysis.coaching_tips[:4]
    if tips:
        print()
        print("Coaching-tips:")
        for tip in tips:
            print(f"  - {tip}")

    print()
    print("-> LLM-analyse fullført OK.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="verify_llm.py",
        description=(
            "Verifiser at LLM-analysen faktisk kjører med valgt backend "
            "(mock | anthropic | azure-openai)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Eksempler:\n"
            "  python scripts/verify_llm.py\n"
            "  python scripts/verify_llm.py --call salg_alarm\n"
            "  LLM_BACKEND=anthropic python scripts/verify_llm.py\n"
            "  python scripts/verify_llm.py --backend anthropic --call salg_alarm\n"
        ),
    )
    parser.add_argument(
        "--call",
        default=DEFAULT_CALL,
        help=f"Sample-samtale (navn i data/). Default: {DEFAULT_CALL}. "
        "F.eks. salg_alarm, vanskelig_sint_kunde.",
    )
    parser.add_argument(
        "--backend",
        choices=VALID_BACKENDS,
        default=None,
        help="Overstyr LLM_BACKEND for denne kjøringen (mock|anthropic|azure-openai).",
    )
    args = parser.parse_args(argv)

    # Overstyr backend FØR provider-import slik at modul-singleton-settings
    # plukker det opp. Vi bygger uansett en fersk Settings og sender som cfg.
    if args.backend:
        os.environ["LLM_BACKEND"] = args.backend
    # STT skal alltid kunne slå opp sample-transkriptet på navn — tving mock-STT
    # uansett LLM-backend, slik at vi kan teste ekte LLM uten lyd/Whisper/Azure.
    os.environ["STT_BACKEND"] = "mock"

    # Importer providers FØRST etter env-override. anthropic importeres IKKE her.
    try:
        from app.config import load_settings
        from app.providers import llm, stt
    except ModuleNotFoundError as e:
        print(
            "Klarte ikke importere app-modulene. Kjør fra repo-roten, f.eks.:\n"
            "    python scripts/verify_llm.py\n"
            f"(detalj: {e})"
        )
        return 1

    cfg = load_settings()
    backend = cfg.llm_backend
    _banner(backend)

    if backend not in VALID_BACKENDS:
        print(f"Ukjent LLM_BACKEND: {backend!r}. Velg en av: {', '.join(VALID_BACKENDS)}.")
        return 1

    # 1) Hent sample-transkript via STT-laget (mock = oppslag på navn).
    try:
        transcript = stt.transcribe(args.call, cfg=cfg)
    except FileNotFoundError:
        print(f"Fant ikke sample-samtale: {args.call!r}.")
        print("Tilgjengelige samples (data/*.json):")
        try:
            for t in stt.list_samples():
                print(f"  - {t.name}")
        except Exception:  # noqa: BLE001 — best effort liste
            pass
        return 1

    # 2) Kjør LLM-analysen. Fang manglende nøkkel/SDK pent (exit 0).
    try:
        analysis = llm.analyze(transcript, cfg=cfg)
    except RuntimeError as e:
        # Forventet ved backend=anthropic uten nøkkel eller uten SDK.
        print()
        print(f"Kan ikke kjøre backend={backend!r}: {e}")
        print()
        if backend == "anthropic":
            print(
                "Tips: Sett ANTHROPIC_API_KEY og `pip install anthropic`, "
                "eller kjør med LLM_BACKEND=mock for offline-demo."
            )
        elif backend == "azure-openai":
            print(
                "Tips: Sett AZURE_OPENAI_ENDPOINT/KEY og `pip install openai`, "
                "eller kjør med LLM_BACKEND=mock for offline-demo."
            )
        # Avslutt pent — dette er en konfig-tilstand, ikke en krasj.
        return 0
    except NotImplementedError as e:
        # azure-openai er wiret men ikke kjørt uten nøkkel.
        print()
        print(f"Backend={backend!r} er wiret men ikke aktiv: {e}")
        print("Kjør med LLM_BACKEND=mock for offline-demo.")
        return 0

    _print_analysis(analysis, transcript)
    return 0


if __name__ == "__main__":
    sys.exit(main())
