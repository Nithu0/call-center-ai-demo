"""PII-maskering for norske samtaleopptak (ansvarlig-AI-showcase).

Samtaleopptak er sensitive persondata (GDPR art. 9 / personopplysningsloven).
Før et transkript sendes videre til logg, LLM-analyse, CRM eller lagring, bør
direkte identifikatorer maskeres. Denne modulen gjør det deterministisk med
regex — ingen eksterne kall, ingen modell, ingen nettverk.

Designvalg:
  - KONSERVATIV på fødselsnummer: heller maskere et tilfeldig 11-sifret tall
    for mye enn å lekke et personnummer. 11 sammenhengende siffer maskeres
    som [FNR] (med mindre de allerede er fanget av kontonummer-mønsteret med
    punktum-format).
  - Rekkefølgen på mønstrene er bevisst: de mest spesifikke/strukturerte
    mønstrene (e-post, kontonr med punktum, kortnr) kjøres FØR de generiske
    siffer-mønstrene, slik at de ikke spises av et bredere FNR-treff.

Offentlig API:
    redact(text) -> (maskert_tekst, funn)
        funn = liste av {type, original_maskert, posisjon}
        - `type`:  FNR | TLF | E-POST | KONTONR | KORTNR | NAVN
        - `original_maskert`: delvis maskert visning av treffet (for revisjon
          UTEN å gjenta hele PII-en, f.eks. "12•••••••89")
        - `posisjon`: [start, slutt] i ORIGINAL-teksten (tegn-indeks)
"""

from __future__ import annotations

import re

# --------------------------------------------------------------------------- #
# Maske-etiketter                                                              #
# --------------------------------------------------------------------------- #
PLACEHOLDER = {
    "FNR": "[FNR]",
    "TLF": "[TLF]",
    "E-POST": "[E-POST]",
    "KONTONR": "[KONTONR]",
    "KORTNR": "[KORTNR]",
    "NAVN": "[NAVN]",
}


# --------------------------------------------------------------------------- #
# Regex-mønstre                                                                #
# --------------------------------------------------------------------------- #
# E-post: enkel men robust nok for samtaletekst.
_RE_EPOST = re.compile(
    r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"
)

# Kontonummer norsk format: 4 sifre . 2 sifre . 5 sifre (xxxx.xx.xxxxx).
_RE_KONTONR_PUNKT = re.compile(r"\b\d{4}\.\d{2}\.\d{5}\b")

# Kortnummer: 16 sifre, evt. gruppert med mellomrom eller bindestrek (4x4).
_RE_KORTNR = re.compile(
    r"\b\d{4}[ \-]?\d{4}[ \-]?\d{4}[ \-]?\d{4}\b"
)

# Fødselsnummer / personnummer:
#   - 11 sammenhengende siffer, ELLER
#   - DDMMYY + 5 siffer separert med mellomrom/bindestrek (6+5).
# Konservativt: alle 11-sifrede tall tolkes som mulig FNR.
_RE_FNR = re.compile(
    r"\b\d{6}[ \-]?\d{5}\b"
)

# Telefonnummer (norsk):
#   - valgfri landkode +47 / 0047
#   - 8 sifre, kan grupperes (xx xx xx xx / xxx xx xxx / sammenhengende).
# Vi krever 8 "kjerne"-sifre for å unngå å fange korte tall.
_RE_TLF = re.compile(
    r"(?:(?:\+47|0047)[ ]?)?"          # valgfri landkode
    r"(?:\d[ ]?){7}\d"                  # 8 sifre med valgfrie enkelt-mellomrom
)

# Navn etter enkle markører: "mitt navn er X", "jeg heter X", "navnet mitt er X".
# Fanger 1-3 påfølgende Stor-bokstav-ord (norske bokstaver tillatt).
# Marker-alternasjonen er case-insensitiv (inline (?i:...)) slik at "Mitt navn
# er", "Jeg heter" osv. fanges uansett start-store-bokstav, mens selve navn-
# gruppen forblir case-sensitiv ([A-ZÆØÅ] = stor forbokstav er signalet).
_RE_NAVN = re.compile(
    r"(?P<markor>\b(?i:mitt navn er|navnet mitt er|jeg heter|jeg er)\s+)"
    r"(?P<navn>[A-ZÆØÅ][a-zæøåA-ZÆØÅ\-']+(?:\s+[A-ZÆØÅ][a-zæøåA-ZÆØÅ\-']+){0,2})",
    re.UNICODE,
)


# --------------------------------------------------------------------------- #
# Maskerings-visning for revisjon (uten å gjenta hele PII-en)                  #
# --------------------------------------------------------------------------- #
def _peek_mask(value: str) -> str:
    """Lag en delvis-maskert visning av et treff for funn-listen.

    Beholder kun ytterpunkter slik at en revisor kan kjenne igjen treffet uten
    at hele PII-en gjentas. F.eks. "12345678901" -> "12•••••••01",
    "ola@eksempel.no" -> "o••@•••.no".
    """
    if "@" in value:
        local, _, domain = value.partition("@")
        tld = domain.rsplit(".", 1)[-1] if "." in domain else ""
        lead = local[:1] or "•"
        return f"{lead}••@•••.{tld}" if tld else f"{lead}••@•••"
    digits_only = re.sub(r"\D", "", value)
    if len(digits_only) >= 4:
        return f"{digits_only[:2]}{'•' * (len(digits_only) - 4)}{digits_only[-2:]}"
    # Korte/ikke-numeriske treff (navn): vis kun første tegn.
    return f"{value[:1]}{'•' * max(len(value) - 1, 1)}"


# --------------------------------------------------------------------------- #
# Kjerne                                                                       #
# --------------------------------------------------------------------------- #
# Rekkefølge er VIKTIG: mest spesifikke/strukturerte mønstre først, slik at de
# ikke overskygges av et bredere siffer-treff (særlig FNR vs kontonr/kort).
_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("E-POST", _RE_EPOST),
    ("KONTONR", _RE_KONTONR_PUNKT),
    ("KORTNR", _RE_KORTNR),
    ("FNR", _RE_FNR),
    ("TLF", _RE_TLF),
    ("NAVN", _RE_NAVN),
]


def redact(text: str) -> tuple[str, list[dict]]:
    """Finn og masker norske PII-mønstre i `text`.

    Returnerer (maskert_tekst, funn). `funn` er sortert på posisjon i original.
    Deterministisk: ingen eksterne kall, samme input -> samme output.

    Overlapp håndteres ved at vi samler ALLE kandidat-treff først, så velger
    ikke-overlappende treff i prioritert rekkefølge (mest spesifikke vinner).
    """
    if not text:
        return text, []

    # 1) Samle kandidat-treff fra alle mønstre med prioritet (lav idx = høy).
    candidates: list[dict] = []
    for prio, (kind, pattern) in enumerate(_PATTERNS):
        for m in pattern.finditer(text):
            if kind == "NAVN":
                # Bare selve navnet maskeres, ikke markør-ordene.
                start, end = m.span("navn")
                original = m.group("navn")
            else:
                start, end = m.start(), m.end()
                original = m.group(0)
            # Trim ledende/etterfølgende mellomrom som regex kan ha dratt med.
            stripped = original.strip()
            if stripped != original:
                lead = len(original) - len(original.lstrip())
                start += lead
                end = start + len(stripped)
                original = stripped
            if not original:
                continue
            candidates.append(
                {
                    "kind": kind,
                    "prio": prio,
                    "start": start,
                    "end": end,
                    "original": original,
                }
            )

    # 2) Velg ikke-overlappende treff. Sorter på (start, prio) — ved overlapp
    #    vinner det som starter først; ved lik start vinner høyest prioritet.
    candidates.sort(key=lambda c: (c["start"], c["prio"]))
    chosen: list[dict] = []
    occupied_end = -1
    for c in candidates:
        if c["start"] >= occupied_end:
            chosen.append(c)
            occupied_end = c["end"]

    # 3) Bygg maskert tekst (bakfra, så indekser holder) + funn-liste.
    chosen.sort(key=lambda c: c["start"])
    parts: list[str] = []
    cursor = 0
    funn: list[dict] = []
    for c in chosen:
        parts.append(text[cursor : c["start"]])
        parts.append(PLACEHOLDER[c["kind"]])
        cursor = c["end"]
        funn.append(
            {
                "type": c["kind"],
                "original_maskert": _peek_mask(c["original"]),
                "posisjon": [c["start"], c["end"]],
            }
        )
    parts.append(text[cursor:])

    return "".join(parts), funn


def redact_transcript(full_text: str) -> tuple[str, list[dict]]:
    """Bekvemmelighet: masker et helt transkript (samme som `redact`).

    Egen navngitt inngang for ruteren slik at intensjonen er tydelig på
    samtale-nivå. Linje-strukturen i transkriptet bevares.
    """
    return redact(full_text)
