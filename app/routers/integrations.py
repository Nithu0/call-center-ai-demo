"""Integrasjons-ruter — telefoni-webhook + CRM-eksport.

Eksponerer to endepunkter (auto-inkludert av app/main.py via `router`):

  POST /integrations/telephony/webhook
      Tar imot et contact-center-event (Puzzel/Genesys/...) og kjører hele
      pipelinen (stt → llm → CRM-payload) via telephony.handle_call_event.

  GET  /integrations/crm/{name}
      Bygger og returnerer en CRM-klar payload for én demo-samtale. Praktisk
      for å se hva som ville blitt sendt til CRM-et uten å trigge en webhook.

Begge svarer JSON. Ruteren bygger på den offentlige provider-kontrakten
(`from app.providers import stt, llm`) og integrasjonene i app/integrations/.

Lane: kun denne fila (+ integrations/crm.py, integrations/telephony.py).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException

from app.integrations.crm import push_to_crm, to_crm
from app.integrations.telephony import handle_call_event
from app.providers import llm, stt

router = APIRouter()


@router.post("/integrations/telephony/webhook")
def telephony_webhook(event: dict[str, Any] = Body(default_factory=dict)) -> dict:
    """Webhook for contact-center-plattformer.

    Kjører handle_call_event på det innkommende eventet. Returnerer alltid 200
    med en status-felt ('ok'/'error') i kroppen — plattformer forventer typisk
    2xx på en levert webhook og leser status i payloaden, ikke i HTTP-koden.
    """
    return handle_call_event(event)


@router.get("/integrations/crm/{name}")
def crm_export(name: str) -> dict:
    """Returner CRM-klar payload for én demo-samtale.

    Slår opp transkriptet (mock: data/<name>.json), kjører analysen og bygger
    CRM-posten. 404 hvis samtalen ikke finnes.
    """
    try:
        transcript = stt.transcribe(name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Ukjent samtale: {name}")

    analysis = llm.analyze(transcript)
    payload = to_crm(transcript, analysis)

    # Vis også hva en push ville gjort (dry-run, ingen webhook konfigurert her).
    push_result = push_to_crm(payload, webhook_url=None)

    return {
        "name": name,
        "crm_payload": payload,
        "push": push_result,
    }
