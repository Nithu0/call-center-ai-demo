#!/usr/bin/env python3
"""WER (Word Error Rate) — enkel ord-nivå Levenshtein for STT-nøyaktighet.

`wer(referanse, hypotese) -> float` gir feilraten (0.0 = perfekt, 1.0 = alt
feil) målt som Levenshtein-avstand på ord-nivå delt på antall ord i referansen.
Tekst normaliseres først (lowercase, tegnsetting fjernet, whitespace kollapset),
slik at "Hei, på deg!" og "hei på deg" regnes som like.

Brukes til å sammenligne et STT-transkript mot en fasit-tekst.

Bruk:
    python scripts/wer.py "referanse-tekst" "hypotese-tekst"
    -> printer WER i prosent (+ antall ord og feil).
"""

from __future__ import annotations

import argparse
import re
import sys


def normalize(text: str) -> list[str]:
    """Normaliser tekst -> liste med ord.

    Lowercase, fjern tegnsetting (alt som ikke er bokstav/tall/whitespace,
    inkl. norske bokstaver via \\w med UNICODE), kollaps whitespace.
    """
    text = text.lower()
    # Behold ordtegn (inkl. æøå via Unicode \w) og whitespace; resten -> mellomrom.
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    return text.split()


def _levenshtein(ref: list[str], hyp: list[str]) -> int:
    """Levenshtein-avstand (edit distance) på to ord-lister."""
    n, m = len(ref), len(hyp)
    if n == 0:
        return m
    if m == 0:
        return n
    # Rullende DP-rad for O(min) minne.
    prev = list(range(m + 1))
    for i in range(1, n + 1):
        cur = [i] + [0] * m
        for j in range(1, m + 1):
            cost = 0 if ref[i - 1] == hyp[j - 1] else 1
            cur[j] = min(
                prev[j] + 1,        # sletting
                cur[j - 1] + 1,     # innsetting
                prev[j - 1] + cost,  # erstatning/match
            )
        prev = cur
    return prev[m]


def wer(referanse: str, hypotese: str) -> float:
    """Word Error Rate mellom referanse (fasit) og hypotese (STT-utdata).

    Returnerer feilrate (kan være > 1.0 hvis hypotesen har mange innsettinger).
    Tom referanse: 0.0 hvis hypotesen òg er tom, ellers 1.0.
    """
    ref = normalize(referanse)
    hyp = normalize(hypotese)
    if not ref:
        return 0.0 if not hyp else 1.0
    return _levenshtein(ref, hyp) / len(ref)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Beregn WER (Word Error Rate) mellom en referanse og en hypotese.",
    )
    parser.add_argument("referanse", help="Fasit-tekst (det som FAKTISK ble sagt).")
    parser.add_argument("hypotese", help="STT-utdata som skal sammenlignes.")
    args = parser.parse_args(argv)

    ref_words = normalize(args.referanse)
    score = wer(args.referanse, args.hypotese)
    n_err = round(score * len(ref_words)) if ref_words else 0

    print(f"WER: {score * 100:.1f}%  ({n_err} feil / {len(ref_words)} ord)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
