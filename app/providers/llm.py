"""LLM-provider (samtaleanalyse) — env-styrt backend.

`analyze(transcript) -> Analysis`

Backends via LLM_BACKEND:
  - mock          : DETERMINISTISK regelbasert analyse. Alltid grønt offline,
                    ingen nettverk/nøkler. Samme input -> samme output.
  - anthropic     : Anthropic SDK (modell claude-opus-4-8) hvis ANTHROPIC_API_KEY satt.
  - azure-openai  : Azure OpenAI (EU/Sweden Central) — wiret integrasjonspunkt.

Alle backends returnerer SAMME `Analysis`-modell. UI-et bryr seg ikke om hvilken.
"""

from __future__ import annotations

import json
import re

from app.config import Settings, settings
from app.models import (
    Analysis,
    KeyInfo,
    Scorecard,
    ScorecardItem,
    Transcript,
)

# --------------------------------------------------------------------------- #
# QA-sjekkliste (det Loyalty scorer på)                                         #
# --------------------------------------------------------------------------- #
CHECKLIST: list[tuple[str, str]] = [
    ("hilsen", "Hilsen / presentasjon"),
    ("identifisering", "Identifisering / verifisering av kunde"),
    ("behovskartlegging", "Behovskartlegging"),
    ("losning", "Løsning / tilbud presentert"),
    ("samtykke", "Samtykke / compliance nevnt"),
    ("avslutning", "Tydelig avslutning / neste steg"),
]


# --------------------------------------------------------------------------- #
# Deterministisk mock-analyse (nøkkelord-regler)                                #
# --------------------------------------------------------------------------- #
def _norm(text: str) -> str:
    return text.lower()


def _any(text: str, *keywords: str) -> bool:
    return any(k in text for k in keywords)


def _score_hilsen(agent_text: str) -> tuple[int, str]:
    # Agenten presenterer seg / firma tidlig
    if _any(agent_text, "du snakker med", "velkommen til", "hei,", "hei ", "fra "):
        return 1, "Agenten hilser og presenterer seg/firma."
    return 0, "Ingen tydelig hilsen/presentasjon funnet."


def _score_identifisering(text: str) -> tuple[int, str]:
    if _any(
        text,
        "bekrefte navn",
        "fødselsdato",
        "snakker jeg med",
        "bekrefte",
        "født",
        "riktig kunde",
    ):
        return 1, "Kunden ble identifisert/verifisert."
    return 0, "Kunden ble ikke tydelig identifisert/verifisert."


def _score_behov(agent_text: str) -> tuple[int, str]:
    if _any(
        agent_text,
        "spørsmål",
        "har du",
        "bor dere",
        "hva kan jeg hjelpe",
        "kan du",
        "hvorfor",
    ):
        return 1, "Agenten kartla kundens behov/situasjon."
    return 0, "Lite behovskartlegging."


def _score_losning(agent_text: str) -> tuple[int, str]:
    if _any(
        agent_text,
        "anbefale",
        "pakke",
        "tilbud",
        "krediter",
        "løsning",
        "kroner",
        "rabatt",
        "korrigert",
    ):
        return 1, "En løsning/et tilbud ble presentert."
    return 0, "Ingen konkret løsning/tilbud presentert."


def _score_samtykke(text: str) -> tuple[int, str]:
    if _any(
        text,
        "binding",
        "bindingstid",
        "oppsigelse",
        "får jeg lov",
        "samtykke",
        "skriftlig",
        "e-post med tilbudet",
        "vilkår",
    ):
        return 1, "Vilkår/samtykke ble berørt."
    return 0, "Samtykke/vilkår ikke tydelig bekreftet."


def _score_avslutning(agent_text: str) -> tuple[int, str]:
    if _any(
        agent_text,
        "ringer deg tilbake",
        "avtale",
        "noterer",
        "innen",
        "virkedager",
        "ha en fin dag",
        "neste steg",
        "sender deg",
    ):
        return 1, "Tydelig avslutning / avtalt neste steg."
    return 0, "Uklar avslutning / mangler neste steg."


def _build_scorecard(transcript: Transcript) -> Scorecard:
    agent_text = _norm(
        " ".join(t.text for t in transcript.turns if t.speaker == "agent")
    )
    all_text = _norm(transcript.full_text)

    rules = {
        "hilsen": _score_hilsen(agent_text),
        "identifisering": _score_identifisering(all_text),
        "behovskartlegging": _score_behov(agent_text),
        "losning": _score_losning(agent_text),
        "samtykke": _score_samtykke(all_text),
        "avslutning": _score_avslutning(agent_text),
    }

    items = [
        ScorecardItem(key=key, label=label, score=rules[key][0], evidence=rules[key][1])
        for key, label in CHECKLIST
    ]
    return Scorecard(items=items)


def _sentiment(transcript: Transcript) -> str:
    text = _norm(transcript.full_text)
    neg = _any(
        text,
        "feil", "høyere enn vanlig", "skjønner ikke", "aldri bestilt", "klage",
        "misfornøyd", "skuffet", "irritert", "frustrert", "sint", "lei av",
        "si opp", "avslutte abonnement", "elendig", "forferdelig", "dårlig service",
        "ubrukelig", "krever", "uakseptabelt",
    )
    pos = _any(
        text,
        "så bra",
        "takk for rask hjelp",
        "passer fint",
        "supert",
        "hørtes greit",
        "bare hyggelig",
    )
    # Negativ start men positiv løsning -> nøytral/positiv hvis løst
    resolved = _any(text, "krediter", "korrigert", "løst", "ordner")
    if neg and not (pos or resolved):
        return "negativ"
    if pos:
        return "positiv"
    return "nøytral"


def _key_info(transcript: Transcript) -> KeyInfo:
    text = _norm(transcript.full_text)
    ctype = transcript.call_type

    if ctype == "salg":
        intent = "Vurdere kjøp av sikkerhetsløsning"
        product = "Boligalarm (Komplett-pakke)" if "komplett" in text else "Boligalarm"
        outcome = "Interessert, men må diskutere med partner"
        next_step = "Oppfølgingssamtale avtalt; skriftlig tilbud sendt på e-post"
    elif ctype == "kundeservice":
        intent = "Klage på for høy faktura"
        product = "Faktura / abonnement"
        outcome = "Feilføring bekreftet og kreditert"
        next_step = "Korrigert faktura sendes innen to virkedager"
    else:
        intent = ""
        product = ""
        outcome = ""
        next_step = ""

    return KeyInfo(intent=intent, product=product, outcome=outcome, next_step=next_step)


def _summary(transcript: Transcript, sentiment: str, key: KeyInfo) -> str:
    if transcript.call_type == "salg":
        return (
            "Utgående salgsanrop om boligalarm. Agenten presenterte en "
            "Komplett-pakke til 399 kr/mnd med gratis installasjon. Kunden var "
            "positiv, men ønsket å diskutere med partner; oppfølging ble avtalt."
        )
    if transcript.call_type == "kundeservice":
        return (
            "Innkommende kundeservice-anrop om en faktura som var nær dobbelt så "
            "høy som vanlig. Agenten identifiserte en feilført gebyrlinje og "
            "krediterte beløpet umiddelbart. Kunden var fornøyd med rask hjelp."
        )
    return f"Samtale ({transcript.call_type}). Sentiment: {sentiment}."


def _compliance_flags(scorecard: Scorecard, transcript: Transcript) -> list[str]:
    flags: list[str] = []
    by_key = {i.key: i for i in scorecard.items}
    text = _norm(transcript.full_text)

    if by_key["samtykke"].score == 0:
        flags.append("Samtykke/vilkår ikke tydelig bekreftet.")
    if by_key["identifisering"].score == 0:
        flags.append("Kundens identitet ikke verifisert.")
    if transcript.call_type == "salg" and "kroner" not in text and "pris" not in text:
        flags.append("Prisinfo ikke tydelig gitt.")
    if transcript.call_type == "salg" and "binding" not in text and "bindingstid" not in text:
        flags.append("Bindingstid ikke nevnt.")
    return flags


def _follow_up(transcript: Transcript, key: KeyInfo, flags: list[str]) -> list[str]:
    actions: list[str] = []
    if key.next_step:
        actions.append(f"Sørg for: {key.next_step}.")
    if transcript.call_type == "salg":
        actions.append("Send skriftlig tilbud og legg inn oppfølgingsoppgave (CRM).")
    if transcript.call_type == "kundeservice":
        actions.append("Verifiser at kreditering er bokført og send korrigert faktura.")
    for flag in flags:
        actions.append(f"Lukk compliance-avvik: {flag}")
    return actions


def _call_reason(transcript: Transcript, key: KeyInfo) -> str:
    """Klassifisert henvendelsesårsak — fra call_type + nøkkelord."""
    text = _norm(transcript.full_text)
    if _any(text, "si opp", "avslutte", "oppsigelse"):
        return "Oppsigelse / churn-henvendelse"
    if _any(text, "faktura", "regning", "for høy", "gebyr"):
        return "Fakturaspørsmål / reklamasjon"
    if transcript.call_type == "salg":
        return "Salg — utgående tilbud"
    if transcript.call_type == "kundeservice":
        return key.intent or "Generell kundeservice"
    return key.intent or "Uklassifisert henvendelse"


def _churn_risk(transcript: Transcript, sentiment: str) -> str:
    """Heuristisk churn-risiko."""
    text = _norm(transcript.full_text)
    if _any(text, "si opp", "avslutte", "misfornøyd", "oppsigelse", "bytte leverandør", "vurderer å slutte"):
        return "høy"
    if sentiment == "negativ" or _any(text, "klage", "irritert", "skuffet"):
        return "middels"
    return "lav"


def _coaching_tips(scorecard: Scorecard, transcript: Transcript) -> list[str]:
    """Konkrete coaching-tips basert på hva som mangler i scorecardet."""
    by_key = {i.key: i for i in scorecard.items}
    tips: list[str] = []
    missing = {
        "hilsen": "Åpne med tydelig hilsen og presentasjon av deg selv og firma.",
        "identifisering": "Verifiser kundens identitet før du deler kontoinfo.",
        "behovskartlegging": "Still flere åpne behovsspørsmål før du foreslår løsning.",
        "losning": "Presenter et konkret tilbud/løsning tilpasset kundens behov.",
        "samtykke": "Bekreft vilkår/samtykke eksplisitt (bindingstid, oppsigelse).",
        "avslutning": "Avslutt med tydelig oppsummering og avtalt neste steg.",
    }
    for key, tip in missing.items():
        if by_key.get(key) and by_key[key].score == 0:
            tips.append(tip)
    if transcript.call_type == "salg" and not tips:
        tips.append("Sterk samtale — be om en konkret forpliktelse for å lukke salget.")
    if not tips:
        tips.append("Godt gjennomført — oppretthold standarden.")
    return tips


def _crm_export(transcript: Transcript, key: KeyInfo, reason: str, churn: str) -> dict:
    """CRM-klar strukturert JSON."""
    prioritet = "høy" if churn == "høy" else ("middels" if churn == "middels" else "normal")
    return {
        "intent": key.intent,
        "produkt": key.product,
        "utfall": key.outcome,
        "neste_steg": key.next_step,
        "prioritet": prioritet,
        "henvendelsesarsak": reason,
        "samtaletype": transcript.call_type,
        "churn_risk": churn,
    }


def _analyze_mock(transcript: Transcript) -> Analysis:
    """Deterministisk analyse — kjernen i offline-demoen."""
    scorecard = _build_scorecard(transcript)
    sentiment = _sentiment(transcript)
    key = _key_info(transcript)
    summary = _summary(transcript, sentiment, key)
    flags = _compliance_flags(scorecard, transcript)
    follow_up = _follow_up(transcript, key, flags)

    # Utvidet analyse (deterministisk)
    reason = _call_reason(transcript, key)
    churn = _churn_risk(transcript, sentiment)
    tips = _coaching_tips(scorecard, transcript)
    adherence = scorecard.percent          # manus-etterlevelse avledet av scorecard
    crm = _crm_export(transcript, key, reason, churn)

    return Analysis(
        summary=summary,
        sentiment=sentiment,  # type: ignore[arg-type]
        scorecard=scorecard,
        key_info=key,
        compliance_flags=flags,
        follow_up=follow_up,
        call_reason=reason,
        churn_risk=churn,  # type: ignore[arg-type]
        coaching_tips=tips,
        script_adherence=adherence,
        crm_export=crm,
        backend="mock",
    )


# --------------------------------------------------------------------------- #
# Felles JSON-skjema-prompt for ekte LLM-backends                               #
# --------------------------------------------------------------------------- #
_ANALYSIS_SYSTEM_PROMPT = """Du er en QA-analytiker for et norsk call-senter (Loyalty).
Analyser samtaletranskriptet og returner KUN gyldig JSON som matcher dette skjemaet:
{
  "summary": "2-3 setninger på norsk",
  "sentiment": "positiv|nøytral|negativ",
  "scorecard": {"items": [{"key": "...", "label": "...", "score": 0|1, "evidence": "..."}]},
  "key_info": {"intent": "...", "product": "...", "outcome": "...", "next_step": "..."},
  "compliance_flags": ["..."],
  "follow_up": ["..."],
  "call_reason": "klassifisert henvendelsesårsak på norsk",
  "churn_risk": "lav|middels|høy",
  "coaching_tips": ["konkrete salgs-/service-coaching-tips til agenten"],
  "script_adherence": 0,
  "crm_export": {"intent": "...", "produkt": "...", "utfall": "...", "neste_steg": "...", "prioritet": "..."}
}
Scorecard skal ha nøyaktig disse key-ene: hilsen, identifisering, behovskartlegging,
losning, samtykke, avslutning. `churn_risk` skal være ett av: lav, middels, høy.
`script_adherence` er manus-/compliance-etterlevelse i prosent (heltall 0–100).
Svar kun med JSON, ingen forklaring rundt."""


def _checklist_labels() -> dict[str, str]:
    return {k: v for k, v in CHECKLIST}


def _coerce_analysis(raw: dict, backend: str) -> Analysis:
    """Map løs LLM-JSON til Analysis, og fyll manglende scorecard-labels."""
    labels = _checklist_labels()
    sc = raw.get("scorecard", {}) or {}
    items_in = sc.get("items", []) if isinstance(sc, dict) else []
    items: list[ScorecardItem] = []
    seen = set()
    for it in items_in:
        key = it.get("key", "")
        if key not in labels:
            continue
        seen.add(key)
        items.append(
            ScorecardItem(
                key=key,
                label=labels[key],
                score=int(it.get("score", 0)),
                evidence=str(it.get("evidence", "")),
            )
        )
    # Fyll inn manglende sjekkpunkter som 0
    for key, label in CHECKLIST:
        if key not in seen:
            items.append(ScorecardItem(key=key, label=label, score=0, evidence="Ikke vurdert."))

    ki = raw.get("key_info", {}) or {}

    # Utvidet analyse — robust mot manglende/ugyldige felt fra LLM
    churn = str(raw.get("churn_risk", "lav")).strip().lower()
    if churn not in ("lav", "middels", "høy"):
        churn = "lav"
    try:
        adherence = int(raw.get("script_adherence", 0))
    except (TypeError, ValueError):
        adherence = 0
    adherence = max(0, min(100, adherence))
    crm_raw = raw.get("crm_export", {}) or {}
    crm = crm_raw if isinstance(crm_raw, dict) else {}

    return Analysis(
        summary=str(raw.get("summary", "")),
        sentiment=raw.get("sentiment", "nøytral"),
        scorecard=Scorecard(items=items),
        key_info=KeyInfo(
            intent=str(ki.get("intent", "")),
            product=str(ki.get("product", "")),
            outcome=str(ki.get("outcome", "")),
            next_step=str(ki.get("next_step", "")),
        ),
        compliance_flags=[str(x) for x in raw.get("compliance_flags", []) or []],
        follow_up=[str(x) for x in raw.get("follow_up", []) or []],
        call_reason=str(raw.get("call_reason", "")),
        churn_risk=churn,  # type: ignore[arg-type]
        coaching_tips=[str(x) for x in raw.get("coaching_tips", []) or []],
        script_adherence=adherence,
        crm_export=crm,
        backend=backend,
    )


def _extract_json(text: str) -> dict:
    """Hent ut første JSON-objekt fra LLM-tekst (robust mot omkringliggende prosa)."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def _analyze_anthropic(transcript: Transcript, cfg: Settings) -> Analysis:  # pragma: no cover
    """Anthropic SDK — modell claude-opus-4-8.

    Kjøres kun hvis ANTHROPIC_API_KEY er satt. Bruker offisiell anthropic-SDK.
    """
    if not cfg.anthropic_api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY mangler. Sett nøkkel for LLM_BACKEND=anthropic, "
            "eller bruk LLM_BACKEND=mock for offline-demo."
        )
    try:
        from anthropic import Anthropic
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("anthropic-SDK ikke installert: pip install anthropic") from e

    client = Anthropic(api_key=cfg.anthropic_api_key)
    # Adaptiv tenking + JSON-skjema-prompt. claude-opus-4-8 bruker adaptive thinking.
    response = client.messages.create(
        model=cfg.anthropic_model,  # default: claude-opus-4-8
        max_tokens=2000,
        thinking={"type": "adaptive"},
        system=_ANALYSIS_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Samtaletype: {transcript.call_type}\n"
                    f"Transkript:\n{transcript.full_text}"
                ),
            }
        ],
    )
    text = "".join(b.text for b in response.content if getattr(b, "type", "") == "text")
    return _coerce_analysis(_extract_json(text), backend="anthropic")


def _analyze_azure_openai(transcript: Transcript, cfg: Settings) -> Analysis:  # pragma: no cover
    """Azure OpenAI (EU / Sweden Central).

    AZURE-INTEGRASJONSPUNKT. Kjøres ikke uten nøkkel — wiret slik at samme
    kode peker mot Azure OpenAI når DEPLOY_TARGET=azure.

    Aktiver med (se README):
        pip install openai
        AZURE_OPENAI_ENDPOINT=https://<resurs>.openai.azure.com
        AZURE_OPENAI_KEY=...   AZURE_OPENAI_DEPLOYMENT=gpt-4o
    """
    if not cfg.azure_openai_key or not cfg.azure_openai_endpoint:
        raise RuntimeError(
            "AZURE_OPENAI_ENDPOINT/KEY mangler. Til demo: bruk DEPLOY_TARGET=local."
        )
    try:
        from openai import AzureOpenAI  # noqa: F401
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("openai-SDK ikke installert: pip install openai") from e

    # AZURE-INTEGRASJONSPUNKT:
    #   client = AzureOpenAI(
    #       azure_endpoint=cfg.azure_openai_endpoint,
    #       api_key=cfg.azure_openai_key,
    #       api_version="2024-08-01-preview",
    #   )
    #   resp = client.chat.completions.create(
    #       model=cfg.azure_openai_deployment,           # f.eks. "gpt-4o" (EU-region)
    #       response_format={"type": "json_object"},
    #       messages=[
    #           {"role": "system", "content": _ANALYSIS_SYSTEM_PROMPT},
    #           {"role": "user", "content": transcript.full_text},
    #       ],
    #   )
    #   return _coerce_analysis(_extract_json(resp.choices[0].message.content), "azure-openai")
    raise NotImplementedError(
        "Azure OpenAI-backend er wiret men ikke kjørt uten nøkkel. "
        "Se AZURE-INTEGRASJONSPUNKT i app/providers/llm.py."
    )


# --------------------------------------------------------------------------- #
# Offentlig API                                                                 #
# --------------------------------------------------------------------------- #
def analyze(transcript: Transcript, cfg: Settings | None = None) -> Analysis:
    """Analyser et transkript -> Analysis. Backend velges av cfg.llm_backend."""
    cfg = cfg or settings
    backend = cfg.llm_backend

    if backend == "mock":
        return _analyze_mock(transcript)
    if backend == "anthropic":
        return _analyze_anthropic(transcript, cfg)
    if backend == "azure-openai":
        return _analyze_azure_openai(transcript, cfg)

    raise ValueError(f"Ukjent LLM_BACKEND: {backend!r}")


def active_backend(cfg: Settings | None = None) -> str:
    return (cfg or settings).llm_backend
