"""Telefoni-ingestion — kobler en contact-center-plattform til AI-pipelinen.

Modellerer at en ekstern plattform (Puzzel, Genesys, Twilio, Five9, ...) sender
et ferdig samtale-event inn til oss når et opptak er klart. Eventet inneholder
typisk en peker til et opptak (audio_url / recording_id) eller et allerede
transkribert resultat. Vi kjører pipelinen stt → llm og returnerer analysen +
en CRM-klar payload.

`handle_call_event(event: dict) -> dict`

Eventet (eksempel, Puzzel-/Genesys-aktig):
    {
        "call_id": "abc-123",
        "platform": "puzzel",
        "recording": "salg_alarm",         # sample-navn ELLER sti til lydfil
        # ELLER, hvis plattformen allerede transkriberte:
        "transcript": {"name": "...", "call_type": "salg", "turns": [...]}
    }

I demoen er `recording` et sample-navn (data/<navn>.json) slik at flyten kjører
offline via mock-STT. I produksjon ville samme felt vært en sti/URL til et
opptak, og STT_BACKEND=azure/whisper transkriberte det — uten at denne koden
endres.

Lane: kun denne fila (+ crm.py, routers/integrations.py). Bruker den offentlige
provider-kontrakten `from app.providers import stt, llm` og `to_crm` fra crm.py.
"""

from __future__ import annotations

from app.integrations.crm import to_crm
from app.providers import llm, stt


def _event_recording_ref(event: dict) -> str | None:
    """Finn pekeren til opptaket/sample-navnet i et plattform-event.

    Aksepterer flere vanlige feltnavn slik at ulike plattformer kan mappes inn
    uten å endre kjernen.
    """
    for key in ("recording", "recording_id", "audio_url", "audio", "sample", "name"):
        val = event.get(key)
        if val:
            return str(val)
    return None


def handle_call_event(event: dict) -> dict:
    """Ta imot et contact-center-event → kjør pipeline → analyse + CRM-payload.

    To veier inn:
      1. Eventet har et ferdig `transcript`-objekt (plattformen transkriberte
         selv) → vi validerer det og hopper over STT.
      2. Eventet peker på et opptak/sample (`recording` o.l.) → vi kjører
         stt.transcribe() (mock slår opp data/<navn>.json offline).

    Returnerer en JSON-vennlig dict med call_id, plattform, transkript-meta,
    full analyse (model_dump) og en CRM-klar payload.
    """
    if not isinstance(event, dict):
        return {"status": "error", "error": "event må være et JSON-objekt (dict)."}

    call_id = event.get("call_id") or event.get("id") or ""
    platform = event.get("platform") or "ukjent"

    # --- 1. Hent/bygg transkript ------------------------------------------- #
    transcript = None
    raw_transcript = event.get("transcript")
    if isinstance(raw_transcript, dict) and raw_transcript:
        # Plattformen sendte et ferdig transkript — valider mot vår modell.
        from app.models import Transcript

        try:
            transcript = Transcript.model_validate(raw_transcript)
        except Exception as exc:  # noqa: BLE001
            return {
                "status": "error",
                "call_id": call_id,
                "platform": platform,
                "error": f"Ugyldig transcript i event: {type(exc).__name__}: {exc}",
            }
    else:
        ref = _event_recording_ref(event)
        if not ref:
            return {
                "status": "error",
                "call_id": call_id,
                "platform": platform,
                "error": (
                    "Event mangler både 'transcript' og en opptaks-peker "
                    "(recording/recording_id/audio_url)."
                ),
            }
        try:
            transcript = stt.transcribe(ref)
        except FileNotFoundError as exc:
            return {
                "status": "error",
                "call_id": call_id,
                "platform": platform,
                "error": f"Fant ikke opptak/sample: {exc}",
            }

    # --- 2. Analyser + bygg CRM-payload ------------------------------------ #
    analysis = llm.analyze(transcript)
    crm_payload = to_crm(transcript, analysis)

    return {
        "status": "ok",
        "call_id": call_id,
        "platform": platform,
        "transcript": {
            "name": transcript.name,
            "call_type": transcript.call_type,
            "title": transcript.title,
            "num_turns": len(transcript.turns),
        },
        "analysis": analysis.model_dump(),
        "crm_payload": crm_payload,
    }
