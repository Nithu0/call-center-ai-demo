"""Tester for PII-maskering (app/redaction.py) + ruteren.

Dekker:
  - FNR (11 siffer, sammenhengende + DDMMYY+5 med separator)
  - telefon (+47 og lokalt, gruppert + sammenhengende)
  - e-post
  - kontonummer (xxxx.xx.xxxxx)
  - kortnummer (16 siffer, gruppert)
  - navn etter markør ("mitt navn er X")
  - at vanlig tekst IKKE over-maskeres
  - funn-listens kontrakt (type, original_maskert, posisjon)
  - at funn-listen ALDRI lekker full PII
  - ruteren importerer + svarer (HTML + JSON)
"""

from __future__ import annotations

import re

import pytest

from app import redaction


# --------------------------------------------------------------------------- #
# Hjelpere                                                                     #
# --------------------------------------------------------------------------- #
def types_in(funn: list[dict]) -> set[str]:
    return {f["type"] for f in funn}


# --------------------------------------------------------------------------- #
# Fødselsnummer / personnummer                                                #
# --------------------------------------------------------------------------- #
def test_fnr_sammenhengende_maskeres():
    masked, funn = redaction.redact("FNR er 01029012345 takk.")
    assert "01029012345" not in masked
    assert "[FNR]" in masked
    assert "FNR" in types_in(funn)


def test_fnr_med_separator_maskeres():
    # DDMMYY + 5 siffer med mellomrom/bindestrek.
    for raw in ("010290 12345", "010290-12345"):
        masked, funn = redaction.redact(f"Nummeret mitt: {raw}")
        assert raw not in masked
        assert "[FNR]" in masked
        assert "FNR" in types_in(funn)


def test_fnr_konservativt_paa_elleve_siffer():
    """Konservativt: et tilfeldig 11-sifret tall maskeres heller for mye."""
    masked, _ = redaction.redact("Referanse 98765432101 noteres.")
    assert "98765432101" not in masked
    assert "[FNR]" in masked


# --------------------------------------------------------------------------- #
# Telefon                                                                      #
# --------------------------------------------------------------------------- #
def test_telefon_med_landkode():
    masked, funn = redaction.redact("Ring meg på +47 412 34 567.")
    assert "412 34 567" not in masked
    assert "[TLF]" in masked
    assert "TLF" in types_in(funn)


def test_telefon_lokalt_8_siffer():
    masked, funn = redaction.redact("Mobil: 98 76 54 32 er nummeret.")
    assert "98 76 54 32" not in masked
    assert "[TLF]" in masked
    assert "TLF" in types_in(funn)


def test_telefon_sammenhengende():
    masked, _ = redaction.redact("Nummeret er 41234567.")
    assert "41234567" not in masked
    assert "[TLF]" in masked


# --------------------------------------------------------------------------- #
# E-post                                                                       #
# --------------------------------------------------------------------------- #
def test_epost_maskeres():
    masked, funn = redaction.redact("Send til ola.nordmann@eksempel.no i dag.")
    assert "ola.nordmann@eksempel.no" not in masked
    assert "[E-POST]" in masked
    assert "E-POST" in types_in(funn)


# --------------------------------------------------------------------------- #
# Kontonummer                                                                  #
# --------------------------------------------------------------------------- #
def test_kontonummer_maskeres():
    masked, funn = redaction.redact("Konto 1234.56.78903 belastes.")
    assert "1234.56.78903" not in masked
    assert "[KONTONR]" in masked
    assert "KONTONR" in types_in(funn)


def test_kontonummer_ikke_forvekslet_med_fnr():
    """Punktum-formatert kontonr skal merkes KONTONR, ikke FNR."""
    _, funn = redaction.redact("Konto 1234.56.78903.")
    assert "KONTONR" in types_in(funn)
    assert "FNR" not in types_in(funn)


# --------------------------------------------------------------------------- #
# Kortnummer                                                                   #
# --------------------------------------------------------------------------- #
def test_kortnummer_gruppert():
    masked, funn = redaction.redact("Kort 4111 1111 1111 1111 brukt.")
    assert "4111 1111 1111 1111" not in masked
    assert "[KORTNR]" in masked
    assert "KORTNR" in types_in(funn)


def test_kortnummer_sammenhengende():
    masked, funn = redaction.redact("Kortnr 4111111111111111.")
    assert "4111111111111111" not in masked
    assert "[KORTNR]" in masked
    assert "KORTNR" in types_in(funn)


# --------------------------------------------------------------------------- #
# Navn etter markør                                                           #
# --------------------------------------------------------------------------- #
def test_navn_etter_markor():
    masked, funn = redaction.redact("Hei, mitt navn er Ola Nordmann og jeg ringer.")
    assert "Ola Nordmann" not in masked
    assert "[NAVN]" in masked
    assert "NAVN" in types_in(funn)
    # Markøren skal bestå — bare navnet maskeres.
    assert "mitt navn er" in masked


def test_navn_jeg_heter():
    masked, _ = redaction.redact("Jeg heter Kari Hansen.")
    assert "Kari Hansen" not in masked
    assert "[NAVN]" in masked


# --------------------------------------------------------------------------- #
# Ingen over-maskering av vanlig tekst                                         #
# --------------------------------------------------------------------------- #
def test_vanlig_tekst_ikke_overmaskeres():
    plain = (
        "Takk for at du ringte kundeservice. Vi skal hjelpe deg med "
        "alarmen i dag. Det koster 299 kroner i måneden."
    )
    masked, funn = redaction.redact(plain)
    assert masked == plain
    assert funn == []


def test_smaa_tall_ikke_maskert():
    """Korte tall (priser, antall, år) skal ikke trigge FNR/TLF/kort."""
    masked, funn = redaction.redact("Vi har 3 pakker fra 199 kr, gjelder 2026.")
    assert masked == "Vi har 3 pakker fra 199 kr, gjelder 2026."
    assert funn == []


# --------------------------------------------------------------------------- #
# Kombinert + funn-kontrakt                                                    #
# --------------------------------------------------------------------------- #
def test_kombinert_tekst_alle_typer():
    text = (
        "Mitt navn er Ola Nordmann, fnr 01029012345, "
        "tlf +47 412 34 567, e-post ola@eksempel.no, "
        "konto 1234.56.78903, kort 4111 1111 1111 1111."
    )
    masked, funn = redaction.redact(text)
    found = types_in(funn)
    assert {"NAVN", "FNR", "TLF", "E-POST", "KONTONR", "KORTNR"} <= found
    for placeholder in ("[NAVN]", "[FNR]", "[TLF]", "[E-POST]", "[KONTONR]", "[KORTNR]"):
        assert placeholder in masked


def test_funn_kontrakt_har_noklene():
    _, funn = redaction.redact("fnr 01029012345")
    assert funn, "forventet minst ett funn"
    f = funn[0]
    assert set(f.keys()) == {"type", "original_maskert", "posisjon"}
    assert isinstance(f["posisjon"], list) and len(f["posisjon"]) == 2
    assert f["posisjon"][0] < f["posisjon"][1]


def test_funn_lekker_ikke_full_pii():
    """Revisjons-visningen skal aldri inneholde hele den opprinnelige PII-en."""
    secrets = ["01029012345", "4111111111111111", "ola.nordmann@eksempel.no"]
    text = "fnr 01029012345 kort 4111111111111111 epost ola.nordmann@eksempel.no"
    _, funn = redaction.redact(text)
    for f in funn:
        for s in secrets:
            assert s not in f["original_maskert"]


def test_posisjon_peker_paa_original():
    text = "Ring 41234567 nå."
    _, funn = redaction.redact(text)
    tlf = next(f for f in funn if f["type"] == "TLF")
    start, end = tlf["posisjon"]
    assert text[start:end].strip() == "41234567"


def test_determinisme():
    text = "fnr 01029012345 tlf +47 412 34 567"
    assert redaction.redact(text) == redaction.redact(text)


def test_tom_tekst():
    assert redaction.redact("") == ("", [])


# --------------------------------------------------------------------------- #
# Ruter                                                                        #
# --------------------------------------------------------------------------- #
def test_router_importerer():
    from app.routers.redaction import router  # noqa: F401

    assert router is not None


def test_router_json_respons():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.routers.redaction import router

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    resp = client.get("/redaction", params={"text": "fnr 01029012345", "format": "json"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["antall_funn"] >= 1
    assert "[FNR]" in body["masked"]
    assert "01029012345" not in body["masked"]


def test_router_html_respons():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.routers.redaction import router

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    resp = client.get("/redaction", params={"text": "e-post ola@eksempel.no"})
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "[E-POST]" in resp.text
    # Den maskerte panelen skal ikke lekke PII. (Råteksten vises bevisst i
    # "Før"-panelen, så vi sjekker det maskerte utdraget spesifikt.)
    masked_panel = resp.text.split('class="box masked"', 1)[1].split("</div>", 1)[0]
    assert "ola@eksempel.no" not in masked_panel
