"""Backend-STT-endepunkt — den PRIVATE tale-til-tekst-veien.

Egen lane (KUN denne fila). Demonstrerer den server-side STT-veien (NB-Whisper
lokalt / Azure AI Speech på Azure) — i kontrast til `/live`, som bruker
nettleserens Web Speech API (klient-side).

`POST /transcribe` tar imot en opplastet lydfil (mikrofon-opptak fra nettleseren
ELLER filopplasting), leser bytene og sender dem gjennom STT-provider-laget.
Samme provider-kontrakt + `Transcript`-modell som resten av appen, så UI-et
bryr seg ikke om hvilken backend som faktisk transkriberte.

Kontrakt (eies av provider-agenten — `app/providers/stt.py`):
    stt.transcribe_audio(data: bytes | str, name) -> Transcript
    stt.supports_audio() -> bool
    stt.active_backend() -> str

Defensivt: hvis den aktive backenden er mock (ingen ekte lyd-dekoding) svarer vi
likevel 200 med et placeholder-transkript + et tydelig `note`-felt som forklarer
hvordan man slår på ekte transkripsjon (STT_BACKEND=faster-whisper / nb-whisper /
azure). Slik virker demoen alltid, også uten tunge STT-pakker.

`python-multipart` kreves for `UploadFile` (følger med FastAPI-oppsettet). Hvis
importen feiler, ser man det som en oppstart-feil fra denne ruteren — den legges
IKKE til i requirements.txt her (det eies av en annen fil/lane).
"""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.providers import stt

router = APIRouter()


def _supports_audio() -> bool:
    """Støtter den aktive backenden ekte lyd-transkripsjon?

    Bruker `stt.supports_audio()` når den finnes (eies av provider-agenten).
    Hvis kontrakten ennå ikke er landet, faller vi tilbake til en konservativ
    heuristikk: mock-backenden støtter ikke ekte lyd, alt annet antas å gjøre det.
    """
    supports = getattr(stt, "supports_audio", None)
    if callable(supports):
        try:
            return bool(supports())
        except Exception:  # noqa: BLE001 — aldri la en provider-detalj knekke ruten
            pass
    return stt.active_backend() != "mock"


def _transcribe_bytes(data: bytes, name: str):
    """Send bytes gjennom provider-laget via `transcribe_audio`-kontrakten.

    Faller tilbake til `stt.transcribe(name)` (eksisterende sample-oppslag) hvis
    `transcribe_audio` ennå ikke er landet, slik at mock-veien funker i dag.
    """
    transcribe_audio = getattr(stt, "transcribe_audio", None)
    if callable(transcribe_audio):
        return transcribe_audio(data, name=name)
    # Fallback (kontrakt ikke landet): mock slår opp et ferdig sample på navn.
    return stt.transcribe(name)


@router.post("/transcribe")
async def transcribe(file: UploadFile = File(...)) -> dict:
    """Ta imot en lydfil og transkriber den via backend-STT-laget.

    Returnerer alltid 200 ved gyldig fil. Når den aktive backenden er mock
    (ingen ekte lyd-dekoding) følger et `note`-felt med som forklarer hvordan
    man slår på ekte transkripsjon.
    """
    # Defensivt på manglende fil — UploadFile uten filnavn/innhold.
    if file is None or not (file.filename or "").strip():
        raise HTTPException(status_code=400, detail="Mangler fil (felt 'file').")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Tom fil — ingen lyd-bytes mottatt.")

    name = file.filename or "opptak"
    supports_audio = _supports_audio()
    backend = stt.active_backend()

    try:
        transcript = _transcribe_bytes(data, name)
    except FileNotFoundError:
        # Mock-veien slår opp et ferdig sample på navn; et vilkårlig opplastet
        # filnavn finnes ikke som sample. Gi et tydelig placeholder-svar i stedet
        # for å feile, så demoen alltid svarer 200.
        from app.models import Transcript, Turn

        transcript = Transcript(
            name=name,
            call_type="ukjent",
            title=f"Placeholder-transkript (backend={backend}): {name}",
            turns=[
                Turn(
                    speaker="agent",
                    text="(Ingen ekte transkripsjon — mock-backend uten lyd-dekoding.)",
                )
            ],
        )

    payload: dict = {
        "transcript": transcript.model_dump(),
        "backend": backend,
        "supports_audio": supports_audio,
    }

    if not supports_audio:
        payload["note"] = (
            f"Aktiv STT-backend ({backend!r}) støtter ikke ekte lyd-transkripsjon — "
            "transkriptet over er placeholder. Sett STT_BACKEND=faster-whisper "
            "(eller nb-whisper / azure) for ekte transkripsjon av den opplastede lyden. "
            "Dette er den PRIVATE backend-STT-veien (server-side), i kontrast til "
            "/live som bruker nettleserens Web Speech API (klient-side)."
        )

    return payload
