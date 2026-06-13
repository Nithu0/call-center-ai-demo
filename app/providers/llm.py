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


# --------------------------------------------------------------------------- #
# Innholds-ekstraksjon (deterministisk) — trekker ut KONKRETE fakta fra         #
# transkriptet slik at sammendrag/coaching kan referere faktisk innhold.        #
# --------------------------------------------------------------------------- #
_AGENT_FIRMA = re.compile(r"\bfra ([A-ZÆØÅ][\wæøåÆØÅ]+(?: [A-ZÆØÅ][\wæøåÆØÅ]+)?)")
_AGENT_NAVN = re.compile(r"\b(?:du snakker med|mitt navn er|jeg heter) ([A-ZÆØÅ][\wæøåÆØÅ]+)")
_KUNDE_NAVN = re.compile(r"\b(?:snakker jeg med|dette er|jeg heter) ([A-ZÆØÅ][\wæøåÆØÅ]+(?: [A-ZÆØÅ][\wæøåÆØÅ]+)?)")
_PRIS = re.compile(r"(\d[\d\s]*)\s*kr(?:oner)?")
# Månedspris kunden skal BETALE: prisen introduseres typisk med koster/til/på/kun,
# i motsetning til "sparer 400 kroner i måneden" (besparelse, ikke pris).
_MND_PRIS = re.compile(
    r"(?:koster|til|på|kun|pris[a-zæøå]*\s+er)\s*(\d[\d\s]*)\s*kr(?:oner)?\s*(?:i|per|/)\s*(?:måned|mnd|måneden)"
)
# Fallback: et hvilket som helst "<beløp> kr i måneden" som ikke følger "sparer".
_MND_PRIS_ANY = re.compile(r"(\d[\d\s]*)\s*kr(?:oner)?\s*(?:i|per|/)\s*(?:måned|mnd|måneden)")


def _first(pattern: re.Pattern, text: str) -> str:
    m = pattern.search(text)
    return m.group(1).strip() if m else ""


def _norm_amt(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _money_amounts(text: str) -> list[str]:
    """Beløp nevnt i samtalen, i rekkefølge, normalisert (uten doble mellomrom)."""
    out: list[str] = []
    for m in _PRIS.finditer(text):
        amt = _norm_amt(m.group(1))
        if amt and amt not in out:
            out.append(amt)
    return out


def _monthly_price(text: str) -> str:
    """Månedsprisen kunden faktisk skal betale (foretrekkes over løse beløp som
    forsikringssum/egenandel/engangsgebyr/besparelse)."""
    m = _MND_PRIS.search(text)
    if m:
        return _norm_amt(m.group(1))
    # Fallback, men hopp over treff som står rett etter "sparer".
    for m in _MND_PRIS_ANY.finditer(text):
        prefix = text[max(0, m.start() - 12):m.start()]
        if "sparer" in prefix:
            continue
        return _norm_amt(m.group(1))
    return ""


def _extract_context(transcript: Transcript) -> dict:
    """Plukk ut konkrete entiteter fra transkriptet (firma, navn, produkt, beløp,
    utfall). Alt heuristisk + deterministisk — ingen modell, ingen nett."""
    raw = transcript.full_text
    text = _norm(raw)
    agent_raw = " ".join(t.text for t in transcript.turns if t.speaker == "agent")
    kunde_raw = " ".join(t.text for t in transcript.turns if t.speaker == "kunde")

    # Produkt / tjeneste det handler om — første (mest spesifikke) treff vinner.
    product = ""
    product_map = [
        (("boligalarm", "innbruddsalarm", "komplett-pakke", "kameraovervåking"), "boligalarm"),
        (("innboforsikring", "innbo opptil", "tegne", "innboet"), "innboforsikring"),
        (("gigabyte", "datakvote", "mobilabonnement", "abonnement med 50"), "mobilabonnement"),
        (("wifi", "ruteren", "fiberkabel", "internett-tilkobling"), "internett/ruter"),
        (("strømavtale", "strømleverandør", "fastprisavtale", "kilowattime", "strømfaktura"), "strømavtale"),
        (("inkasso", "ubetalt faktura", "inkassovarsel"), "inkassosak"),
        (("faktura", "regning", "engangsgebyr"), "faktura/abonnement"),
        (("gjennomgang av strømavtalen", "booke en time", "timeavtale"), "rådgivningstime"),
    ]
    for keys, label in product_map:
        if _any(text, *keys):
            product = label
            break

    amounts = _money_amounts(text)
    monthly_price = _monthly_price(text)

    return {
        "raw": raw,
        "text": text,
        "agent_text": _norm(agent_raw),
        "kunde_text": _norm(kunde_raw),
        "firma": _first(_AGENT_FIRMA, raw),
        "agent_navn": _first(_AGENT_NAVN, raw),
        "kunde_navn": _first(_KUNDE_NAVN, raw),
        "product": product,
        "amounts": amounts,
        "monthly_price": monthly_price,
        # Utfalls-signaler
        "kreditert": _any(text, "krediter", "korrigert", "feilføring", "tilbakebetal"),
        "byttet_pakke": _any(text, "bytter deg over", "endret", "bytte til", "lettpakka", "bekrefter du"),
        "tekniker_bestilt": _any(text, "bestiller en tekniker", "tekniker hjem", "teknikerbesøk"),
        "lost_teknisk": _any(text, "på nett igjen", "ble grønt", "signalet tilbake", "fungerer"),
        "betalingsavtale": _any(text, "betalingsavtale", "to terminer", "dele det opp"),
        "booket": _any(text, "booket", "setter jeg deg opp", "ledig time", "ledige tider"),
        "ville_si_opp": _any(text, "si opp", "avslutte abonnement", "bytte leverandør", "vil bytte"),
        "beholdt": _any(text, "fortsetter hos oss", "slipper å si opp", "lojalitetstilbud", "lojalitetspris"),
        "tilbud_sendt": _any(text, "e-post med tilbudet", "sender deg en e-post", "avtalevilkårene på e-post", "tilbudet skriftlig", "uforpliktende"),
        "oppfolging": _any(text, "ringer deg tilbake", "ringe deg tilbake", "ringe oss tilbake"),
    }


def _sentiment(transcript: Transcript, ctx: dict | None = None) -> str:
    ctx = ctx or _extract_context(transcript)
    text = ctx["text"]
    kunde = ctx["kunde_text"]

    # Sterke negative signaler — primært fra KUNDENS replikker (agenten kan
    # gjenta "beklager"/"feil" som høflighet uten at det er kundens sentiment).
    hard_neg = _any(
        kunde,
        "oppgitt", "misfornøyd", "skuffet", "irritert", "frustrert", "sint",
        "lei av", "elendig", "forferdelig", "dårlig service", "ubrukelig",
        "uakseptabelt", "tredje gang", "ingen har fikset", "går utover",
        "vurderer å bytte", "vurderer å slutte",
    )
    # Sterke positive signaler — kunden er tydelig fornøyd ELLER tar et aktivt
    # ja/kjøp/bytte-valg. Disse løfter totalsentimentet til "positiv".
    strong_pos = _any(
        kunde,
        "supert", "hørtes greit", "hørtes faktisk bedre", "høres bedre",
        "det var jo enkelt", "tusen takk", "vil jeg gjerne ha", "jeg vil bytte",
        "tror jeg vil bytte", "det gjør vi", "passer fint", "passer bra",
        "høres rimelig", "det hadde vært fint",
    )
    # Milde, transaksjonelle bekreftelser ("så bra, takk", "det går fint") løfter
    # IKKE sentimentet til positiv alene — de gir nøytral. Bare strong_pos teller.
    pos = strong_pos
    # En negativ åpning som ENDER i en konkret løsning regnes normalt ikke som
    # negativ totalsentiment — med mindre kunden uttrykte STERK misnøye (gjentatt
    # problem, "ikke godt nok", aktiv churn-trussel). Da står sentimentet som
    # negativt selv om saken ble håndtert (kundeopplevelsen var dårlig).
    resolved = (
        ctx["kreditert"] or ctx["byttet_pakke"] or ctx["lost_teknisk"]
        or ctx["betalingsavtale"] or ctx["beholdt"] or ctx["booket"]
    )
    eskalert = _any(
        text,
        "tredje gang", "ingen har fikset", "lukket uten", "ikke godt nok",
        "vurderer å bytte leverandør", "går utover jobben", "klage internt",
        "saksnummer", "følges opp av en leder",
    )

    if hard_neg and eskalert:
        return "negativ"
    if hard_neg and not (pos or resolved):
        return "negativ"
    if pos:
        return "positiv"
    return "nøytral"


def _classify(transcript: Transcript, ctx: dict) -> str:
    """Bestem scenario-nøkkel ut fra innhold — driver reason/summary/coaching.

    Returnerer én av: oppsigelse, mersalg, klage, support, betaling, booking,
    skademelding, id_sikkerhet, salg, faktura, generell.
    Rekkefølgen er bevisst: mer spesifikke/alvorlige scenarioer sjekkes først.
    """
    text = ctx["text"]
    kunde = ctx["kunde_text"]
    ctype = transcript.call_type

    # Utgående salg vinner alltid — call_type er autoritativt her. (Hindrer at
    # ord som "oppsigelse" i et tilbuds-vilkår feilklassifiserer samtalen.)
    if ctype == "salg":
        return "salg"

    # Betaling/inkasso — sensitivt, sjekkes tidlig.
    if _any(text, "inkasso", "ubetalt faktura", "forfall", "purring", "betalingsavtale", "inkassovarsel"):
        return "betaling"

    # Oppsigelse/retention: kundens PRIMÆRE ærend er å avslutte. Bruk hensikts-
    # frasering ("ringer for å si opp"), ikke en løs churn-trussel inni en klage.
    cancel_purpose = _any(
        text, "ringer for å si opp", "for å si opp", "vil si opp", "si opp abonnementet",
        "si opp strømavtalen", "si opp avtalen",
    )
    if cancel_purpose and not (ctx["tekniker_bestilt"] or _any(text, "tredje gang", "ingen har fikset")):
        return "oppsigelse"

    # Klage/reklamasjon: gjentatt/uløst problem, kunde oppgitt, ofte tekniker +
    # kreditering + eskalering. Vinner over generell support.
    if ctx["tekniker_bestilt"] or _any(text, "tredje gang", "ingen har fikset", "klage internt", "ikke godt nok", "lukket uten"):
        return "klage"

    # Mersalg: kundeservice-henvendelse som ender i oppgradering til større/dyrere
    # pakke (datakvote brukt opp, lojalitetspris). Sjekkes før ren support.
    if _any(text, "gigabyte", "brukt opp", "større pakke", "50 kroner mer", "lojalitetspris", "oppgradering som passer") and ctx["byttet_pakke"]:
        return "mersalg"

    # Teknisk support: wifi/ruter/linje nede. ("treg på nett" alene -> kan være
    # mersalg/datakvote, derfor krever vi ruter/wifi/kabel-signaler her.)
    if _any(text, "wifi", "ruteren", "ruter blinker", "fiberkabel", "blinker rødt", "rødt lys", "koblet meg på", "omstart av ruter"):
        return "support"

    if ctx["booket"] or _any(text, "booke en time", "booket en time", "timeavtale"):
        return "booking"
    if _any(text, "skademelding", "melde en skade", "egenandel") and not _any(text, "innboforsikring", "tegne"):
        return "skademelding"
    if _any(text, "faktura", "regning", "for høy", "gebyr", "feilføring"):
        return "faktura"
    return "generell"


# Taksonomi: scenario-nøkkel -> ryddig henvendelsesårsak (call_reason).
_REASON_TAXONOMY: dict[str, str] = {
    "oppsigelse": "Oppsigelse / churn",
    "mersalg": "Mersalg / oppgradering",
    "klage": "Klage / reklamasjon",
    "support": "Teknisk support",
    "betaling": "Betaling / inkasso",
    "booking": "Booking / timeavtale",
    "skademelding": "Skademelding",
    "id_sikkerhet": "ID / sikkerhet",
    "salg": "Salg (utgående)",
    "faktura": "Fakturaspørsmål",
    "generell": "Generell kundeservice",
}


def _key_info(transcript: Transcript, ctx: dict, scenario: str) -> KeyInfo:
    product = ctx["product"]
    pris = f"{ctx['monthly_price']} kr" if ctx["monthly_price"] else ""

    if scenario == "salg":
        prod_label = {
            "boligalarm": "Boligalarm (Komplett-pakke)",
            "innboforsikring": "Innboforsikring (Standard-pakke)",
        }.get(product, "Sikkerhetsløsning")
        intent = "Vurdere kjøp etter utgående salgsanrop"
        outcome = (
            "Kunden takket ja og bekreftet avtale" if ctx["byttet_pakke"] and "bekrefter du" in ctx["text"]
            else "Interessert; ønsket betenkningstid / å diskutere først"
        )
        next_step = (
            "Skriftlig tilbud sendt på e-post; oppfølgingssamtale avtalt"
            if ctx["oppfolging"] else "Avtale opprettet; vilkår sendt på e-post"
        )
        return KeyInfo(intent=intent, product=f"{prod_label} ({pris}/mnd)" if pris else prod_label,
                       outcome=outcome, next_step=next_step)

    info = {
        "oppsigelse": (
            "Kunde ringte for å si opp",
            "Beholdt på rimeligere avtale (retention)" if ctx["beholdt"]
            else ("Tilbud sendt uforpliktende; kunde vurderer" if ctx["tilbud_sendt"] else "Oppsigelse registrert"),
            "Bekreftelse på e-post; avtale endret fra neste faktura" if ctx["beholdt"]
            else "Tilbud på e-post; kunde ringer tilbake ved ja",
        ),
        "betaling": (
            "Oppfølging av ubetalt/forfalt faktura",
            "Betalingsavtale opprettet; inkasso satt på vent" if ctx["betalingsavtale"] else "Betaling avklart",
            "KID og avtale sendt på e-post; e-postadresse oppdatert",
        ),
        "klage": (
            "Klage på gjentatt/uløst problem",
            "Tekniker bestilt + kreditert; sak eskalert til leder" if ctx["tekniker_bestilt"]
            else "Klage registrert og fulgt opp",
            "Bekreftelse + saksnummer på SMS; intern oppfølging",
        ),
        "support": (
            "Teknisk feil — fikk ikke koblet til",
            "Feil løst i samtalen (løs kabel + omstart)" if ctx["lost_teknisk"] else "Feilsøking startet",
            "Kort guide sendt på SMS",
        ),
        "mersalg": (
            "Kundeservice-henvendelse som ble mersalg",
            "Oppgradert til større/bedre pakke" if ctx["byttet_pakke"] else "Oppgradering foreslått",
            "Endring fra neste fakturaperiode; bekreftelse på SMS",
        ),
        "booking": (
            "Booke time / rådgivning",
            "Time booket" if ctx["booket"] else "Timeønske registrert",
            "Bekreftelse på SMS med endre/avbestill-lenke",
        ),
        "faktura": (
            "Spørsmål om for høy faktura",
            "Feilført gebyr bekreftet og kreditert" if ctx["kreditert"] else "Faktura gjennomgått",
            "Korrigert faktura på e-post innen to virkedager",
        ),
    }
    intent, outcome, next_step = info.get(
        scenario, ("Generell kundeservice-henvendelse", "Håndtert", "Ingen videre handling avtalt")
    )
    prod = product or "Abonnement / tjeneste"
    if pris:
        prod = f"{prod} ({pris}/mnd)"
    return KeyInfo(intent=intent, product=prod, outcome=outcome, next_step=next_step)


def _summary(transcript: Transcript, sentiment: str, key: KeyInfo, ctx: dict, scenario: str) -> str:
    """2-3 konkrete setninger som refererer faktisk innhold i samtalen."""
    firma = ctx["firma"]
    avsender = f"{firma}-" if firma else ""
    pris = f"{ctx['monthly_price']} kr/mnd" if ctx["monthly_price"] else ""
    retning = "Utgående" if (scenario == "salg" or scenario == "betaling") else "Innkommende"

    if scenario == "salg":
        prod = "boligalarm" if ctx["product"] == "boligalarm" else (
            "innboforsikring" if ctx["product"] == "innboforsikring" else "en sikkerhetsløsning")
        s1 = f"Utgående {avsender}salgsanrop om {prod}" + (f" til {pris}." if pris else ".")
        s2 = ("Kunden takket ja og bekreftet avtalen."
              if "positiv" == sentiment and "bekrefter du" in ctx["text"] and ctx["byttet_pakke"]
              else "Kunden var interessert, men ville tenke seg om / diskutere først.")
        s3 = "Skriftlig tilbud ble sendt og oppfølging avtalt." if ctx["oppfolging"] else "Vilkår sendes på e-post."
        return f"{s1} {s2} {s3}"

    bits: dict[str, str] = {
        "oppsigelse": (
            f"{retning} kundeservice: kunden ringte for å si opp, hovedsakelig pga. pris."
            + (" Agenten kartla forbruket og beholdt kunden på en rimeligere pakke."
               if ctx["beholdt"] else " Agenten sendte et uforpliktende tilbud kunden skal vurdere.")
            + (" Churn avverget i samtalen." if ctx["beholdt"] else " Utfallet er åpent.")
        ),
        "betaling": (
            "Utgående betalingsoppfølging på en forfalt faktura"
            + (f" på {ctx['amounts'][0]} kr." if ctx["amounts"] else ".")
            + (" Agenten verifiserte identitet og satte opp en betalingsavtale i to terminer, "
               "slik at inkassoprosessen ble stoppet." if ctx["betalingsavtale"]
               else " Agenten avklarte betalingen med kunden.")
        ),
        "klage": (
            f"{retning} klage: kunden var oppgitt over et gjentatt, uløst problem"
            + (" (internett-utfall som rammet hjemmekontoret)." if "internett" in ctx["text"] else ".")
            + (" Agenten beklaget, bestilte tekniker, krediterte for nedetid og eskalerte saken til en leder."
               if ctx["tekniker_bestilt"] else " Agenten registrerte og fulgte opp klagen.")
        ),
        "support": (
            f"{retning} teknisk support: kunden fikk ikke koblet seg på wifi (ruter med rødt lys). "
            + ("Agenten feilsøkte steg for steg, fant en løs fiberkabel og fikk linjen opp igjen i samtalen."
               if ctx["lost_teknisk"] else "Agenten startet feilsøking.")
        ),
        "mersalg": (
            f"{retning} kundeservice som ble mersalg: kunden lurte på treg mobil"
            + (" og hadde brukt opp datakvoten." if "gigabyte" in ctx["text"] else ".")
            + (f" Agenten foreslo en større pakke til {pris} og oppgraderte etter samtykke."
               if ctx["byttet_pakke"] and pris else " Agenten foreslo en oppgradering.")
        ),
        "booking": (
            f"{retning} booking: kunden ville sette opp en gjennomgang av strømavtalen. "
            + ("Agenten fant ledig tid, booket møtet og sendte SMS-bekreftelse."
               if ctx["booket"] else "Agenten registrerte timeønsket.")
        ),
        "faktura": (
            "Innkommende kundeservice om en faktura som var nær dobbelt så høy som vanlig"
            + (f" ({ctx['amounts'][0]} kr mot vanlig {ctx['amounts'][1]})." if len(ctx["amounts"]) >= 2 else ".")
            + (" Agenten fant en feilført gebyrlinje og krediterte beløpet umiddelbart."
               if ctx["kreditert"] else " Agenten gjennomgikk fakturaen med kunden.")
        ),
    }
    if scenario in bits:
        tail = " Kunden var fornøyd med håndteringen." if sentiment == "positiv" else (
            " Kunden var fortsatt misfornøyd ved samtaleslutt." if sentiment == "negativ" else "")
        return bits[scenario] + tail

    return f"{retning} {transcript.call_type}-samtale. Henvendelsesårsak: {key.intent or 'uklassifisert'}. Sentiment: {sentiment}."


def _compliance_flags(scorecard: Scorecard, transcript: Transcript, ctx: dict, scenario: str) -> list[str]:
    """Norsk-spesifikke compliance-avvik — kun når faktisk relevant for samtalen."""
    flags: list[str] = []
    by_key = {i.key: i for i in scorecard.items}
    text = ctx["text"]
    # En NY/endret avtale opprettes: salg, mersalg, betalingsavtale, eller en
    # oppsigelse som endte i pakkebytte (retention). Bare DA kreves samtykke.
    is_avtale = (
        scenario in ("salg", "mersalg", "betaling")
        or (scenario == "oppsigelse" and ctx["beholdt"])
    )

    # Samtykke kreves når en avtale opprettes/endres.
    if is_avtale and by_key["samtykke"].score == 0 and not _any(text, "bekrefter du", "samtykke"):
        flags.append("Samtykke til avtale ikke eksplisitt innhentet.")
    # ID-verifisering kreves spesielt ved sensitive saker (inkasso, kontoendringer).
    if by_key["identifisering"].score == 0:
        sev = " (skjerpet krav ved inkasso/betaling)" if scenario == "betaling" else ""
        flags.append(f"Kundens identitet ikke verifisert{sev}.")
    # Prisopplysning ved salg/mersalg.
    if scenario in ("salg", "mersalg") and not ctx["amounts"] and not _any(text, "kroner", "pris", "øre"):
        flags.append("Prisopplysning mangler / ikke tydelig oppgitt.")
    # Bindingstid skal opplyses ved salg av abonnement/avtale.
    if scenario in ("salg", "mersalg", "oppsigelse") and not _any(text, "binding", "bindingstid", "ingen bindingstid"):
        flags.append("Bindingstid ikke nevnt.")
    # Angrerett ved fjernsalg (telefonsalg til forbruker).
    if scenario in ("salg", "mersalg") and ctx["byttet_pakke"] and not _any(text, "angrerett", "fjorten dager", "14 dager"):
        flags.append("Angrerett ved fjernsalg ikke opplyst.")
    return flags


def _follow_up(transcript: Transcript, key: KeyInfo, flags: list[str], ctx: dict, scenario: str) -> list[str]:
    actions: list[str] = []
    if key.next_step:
        actions.append(f"Sørg for: {key.next_step}.")
    scenario_action = {
        "salg": "Send skriftlig tilbud og legg oppfølgingsoppgave i CRM før avtalt ringetidspunkt.",
        "mersalg": "Bekreft at abonnementsendringen er aktivert fra neste fakturaperiode.",
        "oppsigelse": ("Logg retention-utfallet (beholdt på lavere pakke) i CRM." if ctx["beholdt"]
                       else "Følg opp tilbudet; flagg som churn-risiko hvis kunden ikke svarer."),
        "betaling": "Verifiser at delbetaling er registrert og at inkasso er satt på vent; oppdater e-postadresse.",
        "klage": "Bekreft teknikerbesøk, at kreditering er bokført, og at klagen er eskalert til leder.",
        "support": "Send SMS-guide; logg feilårsak (løs fiberkabel) for evt. mønsteranalyse.",
        "booking": "Bekreft kalenderoppføring og at rådgiver har kundens kontekst før møtet.",
        "faktura": "Verifiser at kreditering er bokført og at korrigert faktura er sendt.",
    }.get(scenario)
    if scenario_action:
        actions.append(scenario_action)
    for flag in flags:
        actions.append(f"Lukk compliance-avvik: {flag}")
    return actions


def _call_reason(transcript: Transcript, ctx: dict, scenario: str) -> str:
    """Klassifisert henvendelsesårsak via ryddig norsk taksonomi."""
    return _REASON_TAXONOMY.get(scenario, "Uklassifisert henvendelse")


def _churn_risk(transcript: Transcript, sentiment: str, ctx: dict, scenario: str) -> str:
    """Heuristisk churn-risiko."""
    text = ctx["text"]
    # Aktiv oppsigelse/bytte-intensjon -> høy churn-risiko. Gjelder også når
    # kunden ble beholdt: risikoen VAR høy og bør synliggjøres for oppfølging.
    if scenario == "oppsigelse" or ctx["ville_si_opp"]:
        return "høy"
    if _any(text, "vurderer å bytte leverandør", "bytte leverandør"):
        return "høy"
    if sentiment == "negativ" or scenario == "klage" or _any(text, "irritert", "skuffet", "oppgitt"):
        return "middels"
    return "lav"


# Situasjonsbestemte coaching-tips: scenario -> liste av (betingelse, tips).
def _coaching_tips(scorecard: Scorecard, transcript: Transcript, ctx: dict, scenario: str) -> list[str]:
    """Konkrete, situasjonsbestemte coaching-tips — knyttet til hva agenten
    faktisk gjorde/manglet i nettopp denne samtalen, ikke generiske floskler."""
    by_key = {i.key: i for i in scorecard.items}
    tips: list[str] = []

    def missing(k: str) -> bool:
        return by_key.get(k) is not None and by_key[k].score == 0

    # --- Mangler i QA-scorecardet -> konkret, scenario-farget råd -------------
    if missing("hilsen"):
        tips.append("Åpne med navn + firma med en gang — kunden skal vite hvem som ringer innen første setning.")
    if missing("identifisering"):
        if scenario == "betaling":
            tips.append("Ved inkasso/betaling: verifiser ID før beløp nevnes — sensitiv sak krever streng identifisering.")
        else:
            tips.append("Bekreft kundens identitet (navn + fødselsdato/kundenr.) før du henter opp kontoinfo.")
    if missing("behovskartlegging"):
        tips.append("Still et par åpne behovsspørsmål før du foreslår løsning — tilbudet treffer bedre da.")
    if missing("losning"):
        # "Løsning" betyr noe ulikt per scenario — gi råd som passer samtalen.
        losning_tip = {
            "salg": "Landé en konkret, prislagt løsning i samtalen i stedet for å la den henge åpen.",
            "mersalg": "Knytt oppgraderingen tydelig til kundens forbruk og oppgi totalprisen klart.",
            "support": "Oppsummer feilårsaken og bekreft at problemet faktisk er løst før du avslutter.",
            "booking": "Bekreft tid, kanal og hva kunden bør forberede, så møtet blir effektivt.",
            "klage": "Gi kunden en konkret kompensasjon/handling, ikke bare en beklagelse.",
        }.get(scenario, "Sørg for å lande et konkret utfall kunden kan forholde seg til.")
        tips.append(losning_tip)
    if missing("samtykke"):
        if scenario in ("salg", "mersalg"):
            tips.append("Hent eksplisitt ja på avtalen ('bekrefter du ...?') og opplys bindingstid + angrerett før du registrerer.")
        elif scenario in ("oppsigelse", "betaling"):
            tips.append("Innhent og noter eksplisitt samtykke til endringen før den effektueres.")
        # For support/booking/faktura/klage opprettes ingen avtale -> ingen samtykke-nag.
    if missing("avslutning"):
        tips.append("Avslutt med en tydelig oppsummering og ett konkret neste steg med tidspunkt.")

    # --- Positive, situasjonsbestemte forsterkninger når QA er sterk ----------
    if not tips:
        strong = {
            "salg": ("Solid struktur — be alltid om en konkret forpliktelse eller et fast oppfølgingstidspunkt for å lukke."
                     if not ctx["byttet_pakke"] else
                     "Lærebokeksempel: behov → prislagt tilbud → samtykke. Bruk opptaket til kalibrering av teamet."),
            "mersalg": "Forbilledlig behovsdrevet mersalg — koblet kundens faktiske bruk til oppgraderingen. Del som beste praksis.",
            "oppsigelse": ("Sterk retention — fant kundens reelle behov og reddet kunden på lavere pakke uten å presse."
                           if ctx["beholdt"] else
                           "God tone, men oppsigelsen ble ikke snudd — test ett konkret retention-tilbud tidligere i samtalen."),
            "klage": "Eide problemet, beklaget, kompenserte og eskalerte — god håndtering av en opphisset kunde.",
            "support": "Effektiv, rolig feilsøking steg for steg helt til kunden var på nett igjen. God support-standard.",
            "betaling": "Håndterte en sensitiv inkassosamtale ryddig: verifiserte ID, fant en realistisk betalingsavtale.",
            "booking": "Ryddig booking med tydelig bekreftelse og forberedelse til møtet.",
            "faktura": "Rask rotårsaksanalyse og umiddelbar kreditering — kunden fikk svar og løsning i én samtale.",
        }.get(scenario, "Godt gjennomført — oppretthold standarden.")
        tips.append(strong)

    # --- Tverrgående, innholdsspesifikke tips --------------------------------
    if scenario == "oppsigelse" and ctx["beholdt"]:
        tips.append("Følg opp den beholdte kunden om ~30 dager for å sikre at den nye pakken oppleves riktig.")
    if scenario == "klage" and ctx["tekniker_bestilt"]:
        tips.append("Lukk loopen aktivt: ring kunden etter teknikerbesøket for å bekrefte at problemet er borte.")

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
    ctx = _extract_context(transcript)
    scenario = _classify(transcript, ctx)

    scorecard = _build_scorecard(transcript)
    sentiment = _sentiment(transcript, ctx)
    key = _key_info(transcript, ctx, scenario)
    summary = _summary(transcript, sentiment, key, ctx, scenario)
    flags = _compliance_flags(scorecard, transcript, ctx, scenario)
    follow_up = _follow_up(transcript, key, flags, ctx, scenario)

    # Utvidet analyse (deterministisk)
    reason = _call_reason(transcript, ctx, scenario)
    churn = _churn_risk(transcript, sentiment, ctx, scenario)
    tips = _coaching_tips(scorecard, transcript, ctx, scenario)
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
