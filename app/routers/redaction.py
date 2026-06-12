"""PII-maskerings-ruter — ansvarlig-AI-showcase for Loyalty.

`GET /redaction` viser PII-maskering før/etter:
  - `?name=<sample>`  : hent demo-transkript via STT-laget og masker det.
  - `?text=<fritekst>`: masker vilkårlig tekst (lim inn et utdrag).
  - `?format=json`    : returner JSON i stedet for HTML (for API/integrasjon).

Personvern-poenget: samtaleopptak er sensitive persondata. Før transkript
logges, sendes til LLM-analyse eller eksporteres til CRM, kan direkte
identifikatorer (FNR, telefon, e-post, konto-/kortnummer, navn) maskeres
deterministisk. Demoen gjør tesen synlig: rå transkript til venstre, maskert
til høyre, med en revisjonsvennlig funn-liste (delvis maskert, aldri full PII).

Egen lane: denne fila + app/redaction.py + tests/test_redaction.py.
Ingen andre filer røres.
"""

from __future__ import annotations

import html

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse, JSONResponse

from app import redaction
from app.providers import stt

router = APIRouter()

# Et lite, trygt standard-eksempel (ingen ekte PII) som demoen faller tilbake på
# når verken ?name eller ?text er gitt — så siden alltid viser noe meningsfylt.
_DEMO_TEXT = (
    "Hei, mitt navn er Ola Nordmann. "
    "Personnummeret mitt er 01029012345, og du kan nå meg på +47 412 34 567. "
    "E-posten min er ola.nordmann@eksempel.no. "
    "Trekk det fra konto 1234.56.78903, eller bruk kortet 4111 1111 1111 1111. "
    "Takk for hjelpen!"
)


def _resolve_text(name: str | None, text: str | None) -> tuple[str, str]:
    """Finn teksten som skal maskeres + en kildebeskrivelse.

    Prioritet: eksplisitt ?text > ?name (transkript via STT) > demo-fallback.
    """
    if text:
        return text, "fritekst"
    if name:
        try:
            transcript = stt.transcribe(name)
        except FileNotFoundError:
            return (
                f"(Fant ikke samtale {name!r}. Prøv ?text=... eller et gyldig sample-navn.)",
                f"ukjent:{name}",
            )
        return transcript.full_text, f"transkript:{name}"
    return _DEMO_TEXT, "demo"


@router.get("/redaction")
def redaction_view(
    name: str | None = Query(default=None, description="Sample-navn (demo-samtale)"),
    text: str | None = Query(default=None, description="Fri tekst å maskere"),
    format: str = Query(default="html", description="html | json"),
):
    """Vis PII-maskering før/etter for et transkript eller fri tekst."""
    source_text, source = _resolve_text(name, text)
    masked, funn = redaction.redact(source_text)

    if format == "json":
        return JSONResponse(
            {
                "source": source,
                "original": source_text,
                "masked": masked,
                "funn": funn,
                "antall_funn": len(funn),
            }
        )

    return HTMLResponse(_render_html(source, source_text, masked, funn))


# --------------------------------------------------------------------------- #
# HTML-rendering (selvstendig — ingen template-fil, holder lane-en isolert)    #
# --------------------------------------------------------------------------- #
def _render_html(source: str, original: str, masked: str, funn: list[dict]) -> str:
    rows = "".join(
        f"<tr><td><span class='tag'>{html.escape(f['type'])}</span></td>"
        f"<td><code>{html.escape(f['original_maskert'])}</code></td>"
        f"<td>{f['posisjon'][0]}–{f['posisjon'][1]}</td></tr>"
        for f in funn
    )
    if not rows:
        rows = "<tr><td colspan='3'><em>Ingen PII funnet.</em></td></tr>"

    return f"""<!doctype html>
<html lang="no"><head><meta charset="utf-8">
<title>PII-maskering — Loyalty call-senter-AI</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 2rem; color: #1a1a2e; }}
  h1 {{ font-size: 1.4rem; }}
  .sub {{ color: #555; margin-bottom: 1.5rem; }}
  .cols {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }}
  .box {{ border: 1px solid #ddd; border-radius: 8px; padding: 1rem;
          background: #fafafa; white-space: pre-wrap; font-size: .92rem; }}
  .box.masked {{ background: #f0f7f0; border-color: #bcd9bc; }}
  .label {{ font-weight: 600; margin-bottom: .4rem; }}
  table {{ border-collapse: collapse; margin-top: 1.5rem; width: 100%; }}
  th, td {{ text-align: left; padding: .4rem .6rem; border-bottom: 1px solid #eee; }}
  .tag {{ background: #1a1a2e; color: #fff; border-radius: 4px;
          padding: .1rem .45rem; font-size: .8rem; }}
  code {{ background: #eee; padding: .1rem .3rem; border-radius: 3px; }}
  form {{ margin-bottom: 1.5rem; }}
  .note {{ margin-top: 2rem; color: #777; font-size: .85rem; max-width: 60ch; }}
</style></head><body>
<h1>PII-maskering (ansvarlig AI)</h1>
<div class="sub">Kilde: <code>{html.escape(source)}</code> — {len(funn)} treff maskert.
  Samtaleopptak er sensitive persondata; direkte identifikatorer maskeres
  deterministisk før logging / LLM-analyse / CRM-eksport.</div>
<form method="get" action="/redaction">
  <input type="text" name="text" placeholder="Lim inn tekst å maskere..." size="60">
  <input type="text" name="name" placeholder="eller sample-navn" size="20">
  <button type="submit">Masker</button>
</form>
<div class="cols">
  <div><div class="label">Før (rå)</div>
    <div class="box">{html.escape(original)}</div></div>
  <div><div class="label">Etter (maskert)</div>
    <div class="box masked">{html.escape(masked)}</div></div>
</div>
<table>
  <thead><tr><th>Type</th><th>Treff (delvis maskert)</th><th>Posisjon</th></tr></thead>
  <tbody>{rows}</tbody>
</table>
<div class="note">Funn-listen viser KUN delvis-maskerte treff (f.eks.
  <code>12•••••••01</code>), aldri full PII — slik at en revisor kan verifisere
  uten ny eksponering. Deterministisk regex, ingen eksterne kall.</div>
</body></html>"""
