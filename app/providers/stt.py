"""STT-provider (tale-til-tekst) — env-styrt backend.

`transcribe(audio_or_name) -> Transcript`

Backends via STT_BACKEND:
  - mock            : returnerer ferdig norsk transkript som matcher sample-navnet
                      (offline, ingen nettverk/nøkler).
  - faster-whisper  : lokal Whisper (import-guardet, valgfri).
  - nb-whisper      : Nasjonalbibliotekets norske Whisper (import-guardet).
  - azure           : Azure AI Speech (azure-cognitiveservices-speech).

Portabilitets-poenget: når DEPLOY_TARGET=azure settes default STT_BACKEND=azure,
og DETTE filen peker mot Azure-tjenesten — uten at resten av koden endres.
Mock og Azure returnerer SAMME `Transcript`-modell.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

from app.config import Settings, settings
from app.models import Transcript, Turn

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
AUDIO_DIR = DATA_DIR / "audio"


# --------------------------------------------------------------------------- #
# Felles hjelp: løs opp sti til lydfil + enkel taler-separasjon                #
# --------------------------------------------------------------------------- #
def _resolve_audio_path(audio_or_name: str) -> Path:
    """Godta enten en full sti ELLER et sample-navn (data/audio/<navn>.<ext>).

    For ekte STT-backends må `audio_or_name` peke på en faktisk lydfil. For
    bekvemmelighet kan demoen gi bare et navn (f.eks. "demo_no"), så slår vi
    opp i data/audio/.
    """
    p = Path(audio_or_name)
    if p.exists():
        return p
    for ext in (".wav", ".mp3", ".m4a", ".ogg", ".flac"):
        cand = AUDIO_DIR / f"{audio_or_name}{ext}"
        if cand.exists():
            return cand
    raise FileNotFoundError(
        f"Fant ikke lydfil for {audio_or_name!r}. Forventet en sti eller en fil "
        f"under {AUDIO_DIR}. Generer en demo-fil med: python scripts/gen_audio.py"
    )


def _segments_to_turns(texts: list[str]) -> list[Turn]:
    """Enkel diariserer: alternér agent/kunde over segmentene.

    Whisper (uten et eget diariserings-steg) gir ikke taler-id. For demoen
    holder det å alternere — agenten åpner, så vil partene veksle. Hvis vi bare
    har ett segment, blir det én tur fra agenten.
    """
    turns: list[Turn] = []
    for i, text in enumerate(texts):
        text = text.strip()
        if not text:
            continue
        speaker = "agent" if i % 2 == 0 else "kunde"
        turns.append(Turn(speaker=speaker, text=text))
    if not turns:
        turns.append(Turn(speaker="agent", text="(tom transkripsjon)"))
    return turns


# --------------------------------------------------------------------------- #
# Hjelp: les ferdig demo-transkript fra data/<name>.json                       #
# --------------------------------------------------------------------------- #
def _load_sample(name: str) -> Transcript:
    path = DATA_DIR / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"Fant ikke sample-transkript: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return Transcript.model_validate(data)


def list_samples() -> list[Transcript]:
    """Alle demo-samtaler tilgjengelig i data/."""
    out: list[Transcript] = []
    for path in sorted(DATA_DIR.glob("*.json")):
        # Hopp over hjelpe-/metadatafiler (konvensjon: prefiks "_", f.eks.
        # data/_labels.json) som ikke er transkript-samples.
        if path.name.startswith("_"):
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        out.append(Transcript.model_validate(data))
    return out


# --------------------------------------------------------------------------- #
# Backend-implementasjoner                                                      #
# --------------------------------------------------------------------------- #
def _transcribe_mock(audio_or_name: str) -> Transcript:
    """Offline: slå opp ferdig transkript på sample-navn.

    I produksjon ville `audio_or_name` vært en lydfil/stream; her er det
    sample-navnet, slik at demoen alltid kjører uten lyd eller nettverk.
    """
    return _load_sample(audio_or_name)


def _transcribe_faster_whisper(audio_or_name: str) -> Transcript:
    """Lokal Whisper via faster-whisper — EKTE transkripsjon, import-guardet.

    Aktiver med:  pip install faster-whisper   og   STT_BACKEND=faster-whisper
    `audio_or_name` skal her være en sti til en lydfil (wav/mp3) ELLER et navn
    som finnes under data/audio/ (f.eks. "demo_no").

    Pakke (IKKE i requirements.txt — tung, valgfri): `faster-whisper`.
    Modellstørrelse styres av env FASTER_WHISPER_MODEL (default "small").
    Om pakken mangler: fall tilbake til mock med en advarsel, slik at offline-
    kjøring aldri knekker.
    """
    import os

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        warnings.warn(
            "faster-whisper er ikke installert — faller tilbake til mock. "
            "Kjør `pip install faster-whisper` for ekte lokal Whisper.",
            RuntimeWarning,
            stacklevel=2,
        )
        return _transcribe_mock(audio_or_name)

    audio_path = _resolve_audio_path(audio_or_name)
    model_size = os.environ.get("FASTER_WHISPER_MODEL", "small")
    # CPU + int8 er den portable defaulten; sett device/compute via env ved behov.
    device = os.environ.get("FASTER_WHISPER_DEVICE", "cpu")
    compute_type = os.environ.get("FASTER_WHISPER_COMPUTE", "int8")

    model = WhisperModel(model_size, device=device, compute_type=compute_type)
    segments, _info = model.transcribe(str(audio_path), language="no")
    texts = [seg.text for seg in segments]

    return Transcript(
        name=audio_path.stem,
        call_type="ukjent",
        title=f"Ekte transkripsjon (faster-whisper/{model_size}): {audio_path.name}",
        turns=_segments_to_turns(texts),
    )


def _transcribe_nb_whisper(audio_or_name: str) -> Transcript:
    """nb-whisper (NB-Whisper, norsk-tunet) via transformers — EKTE, import-guardet.

    Aktiver med:  pip install transformers torch   og   STT_BACKEND=nb-whisper
    Modell: NbAiLab/nb-whisper-small (env NB_WHISPER_MODEL kan overstyre).

    Pakker (IKKE i requirements.txt — tunge, valgfrie): `transformers`, `torch`.
    Om pakkene mangler: fall tilbake til mock med en advarsel.
    """
    import os

    try:
        from transformers import pipeline
    except ImportError:
        warnings.warn(
            "transformers/torch er ikke installert — faller tilbake til mock. "
            "Kjør `pip install transformers torch` for ekte NB-Whisper.",
            RuntimeWarning,
            stacklevel=2,
        )
        return _transcribe_mock(audio_or_name)

    audio_path = _resolve_audio_path(audio_or_name)
    model_name = os.environ.get("NB_WHISPER_MODEL", "NbAiLab/nb-whisper-small")

    asr = pipeline("automatic-speech-recognition", model=model_name)
    # chunk_length_s gjør at lengre opptak transkriberes uten å sprenge minnet.
    result = asr(
        str(audio_path),
        chunk_length_s=28,
        generate_kwargs={"language": "no", "task": "transcribe"},
    )
    text = result["text"] if isinstance(result, dict) else str(result)

    # NB-Whisper gir én sammenhengende tekst; splitt grovt på setninger for at
    # den enkle agent/kunde-alterneringen skal ha noe å jobbe med.
    import re

    parts = [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]
    return Transcript(
        name=audio_path.stem,
        call_type="ukjent",
        title=f"Ekte transkripsjon (nb-whisper): {audio_path.name}",
        turns=_segments_to_turns(parts or [text]),
    )


def _transcribe_azure(audio_or_name: str, cfg: Settings) -> Transcript:  # pragma: no cover
    """Azure AI Speech (azure-cognitiveservices-speech).

    AZURE-INTEGRASJONSPUNKT. Kjøres ikke uten nøkkel — wiret med tydelig
    kommentar slik at samme kode peker på Azure når DEPLOY_TARGET=azure.

    Aktiver med (se README for full oppskrift):
        pip install azure-cognitiveservices-speech
        AZURE_SPEECH_KEY=...   AZURE_SPEECH_REGION=swedencentral
        AZURE_SPEECH_LANGUAGE=nb-NO
    """
    try:
        import azure.cognitiveservices.speech as speechsdk  # noqa: F401
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "azure-cognitiveservices-speech er ikke installert. "
            "pip install azure-cognitiveservices-speech"
        ) from e

    if not cfg.azure_speech_key:
        raise RuntimeError(
            "AZURE_SPEECH_KEY mangler. Sett nøkkel + region for å bruke "
            "STT_BACKEND=azure. Til demo: bruk DEPLOY_TARGET=local (mock)."
        )

    # AZURE-INTEGRASJONSPUNKT (kjøres IKKE i demoen — krever gyldig nøkkel/region):
    #   audio_path = _resolve_audio_path(audio_or_name)
    #   speech_config = speechsdk.SpeechConfig(
    #       subscription=cfg.azure_speech_key, region=cfg.azure_speech_region)
    #   speech_config.speech_recognition_language = cfg.azure_speech_language  # nb-NO
    #   audio_config = speechsdk.audio.AudioConfig(filename=str(audio_path))
    #
    #   # For ekte agent/kunde-separasjon bruk ConversationTranscriber (diarisering
    #   # innebygd) i stedet for SpeechRecognizer:
    #   transcriber = speechsdk.transcription.ConversationTranscriber(
    #       speech_config, audio_config)
    #   texts: list[str] = []
    #   done = threading.Event()
    #   transcriber.transcribed.connect(lambda evt: texts.append(evt.result.text))
    #   transcriber.session_stopped.connect(lambda evt: done.set())
    #   transcriber.start_transcribing_async()
    #   done.wait()
    #   transcriber.stop_transcribing_async()
    #   return Transcript(name=audio_path.stem, turns=_segments_to_turns(texts))
    raise NotImplementedError(
        "Azure Speech-backend er wiret men ikke kjørt uten nøkkel. "
        "Se AZURE-INTEGRASJONSPUNKT i app/providers/stt.py."
    )


def _transcribe_openai(audio_or_name: str) -> Transcript:
    """OpenAI Whisper API (sky) — EKTE transkripsjon med bare en API-nøkkel.

    Den enkleste BETALTE backenden: ingen lokal modell, bare OPENAI_API_KEY.
    Billig (whisper-1 ~$0.006/min). NB: lyd sendes til OpenAI (USA) — for
    sensitive EKTE kundedata bruk self-hosted NB-Whisper eller Azure Speech (EU).

    Aktiver:  pip install openai  ·  STT_BACKEND=openai  ·  OPENAI_API_KEY=...
    Modell via OPENAI_STT_MODEL (default whisper-1; gpt-4o-transcribe er nyere/bedre).
    """
    import os

    try:
        from openai import OpenAI
    except ImportError:
        warnings.warn(
            "openai-pakken er ikke installert — faller tilbake til mock. "
            "Kjør `pip install openai` for OpenAI Whisper API.",
            stacklevel=2,
        )
        return _transcribe_mock(audio_or_name)

    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError(
            "STT_BACKEND=openai krever OPENAI_API_KEY i miljøet/.env. "
            "Til demo uten nøkkel: bruk DEPLOY_TARGET=local (mock)."
        )

    import re

    audio_path = _resolve_audio_path(audio_or_name)
    model = os.environ.get("OPENAI_STT_MODEL", "whisper-1")
    client = OpenAI()
    with audio_path.open("rb") as fh:
        resp = client.audio.transcriptions.create(model=model, file=fh, language="no")
    text = (getattr(resp, "text", "") or "").strip()
    segments = [s for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    return Transcript(
        name=audio_path.stem,
        call_type="ukjent",
        title=f"Ekte transkripsjon (OpenAI {model}): {audio_path.name}",
        turns=_segments_to_turns(segments or [text]),
    )


def _diarized_words_to_turns(words: list[dict]) -> list[Turn]:
    """Gjør ElevenLabs Scribe sine diariserte ord om til agent/kunde-replikker.

    Hvert ord har `speaker_id`. Første taler som dukker opp = agent, neste = kunde
    (gjelder en 2-parts samtale; flere talere enn 2 mappes vekselvis).
    """
    order: dict[str, int] = {}
    turns: list[Turn] = []
    cur_sp: str | None = None
    buf: list[str] = []

    def flush() -> None:
        text = "".join(buf).strip()
        if text:
            label = "agent" if order.get(cur_sp, 0) % 2 == 0 else "kunde"
            turns.append(Turn(speaker=label, text=text))

    for w in words:
        sp = w.get("speaker_id") or "speaker_0"
        if sp not in order:
            order[sp] = len(order)
        if cur_sp is not None and sp != cur_sp:
            flush()
            buf.clear()
        cur_sp = sp
        buf.append(str(w.get("text", "")))
    flush()
    return turns or [Turn(speaker="agent", text="(tom transkripsjon)")]


def _transcribe_elevenlabs(audio_or_name: str) -> Transcript:
    """ElevenLabs Scribe (sky) — PROFESJONELL STT med innebygd taler-separasjon.

    Krever bare ELEVENLABS_API_KEY (ingen GPU, ingen egen modell). Diariserer
    agent/kunde automatisk — bedre enn Whisper som trenger et eget diariserings-steg.
    NB: lyd sendes til ElevenLabs (utenfor EU) — vurder personvern for ekte kundedata.

    Aktiver:  STT_BACKEND=elevenlabs  ·  ELEVENLABS_API_KEY=...   (bruker httpx, ingen ekstra pakke)
    Modell via ELEVENLABS_STT_MODEL (default scribe_v1).
    """
    import os

    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        raise RuntimeError(
            "STT_BACKEND=elevenlabs krever ELEVENLABS_API_KEY i miljøet/.env. "
            "Til demo uten nøkkel: bruk DEPLOY_TARGET=local (mock)."
        )
    try:
        import httpx
    except ImportError:  # pragma: no cover
        warnings.warn("httpx mangler — faller tilbake til mock.", stacklevel=2)
        return _transcribe_mock(audio_or_name)

    audio_path = _resolve_audio_path(audio_or_name)
    model = os.environ.get("ELEVENLABS_STT_MODEL", "scribe_v1")
    with audio_path.open("rb") as fh:
        resp = httpx.post(
            "https://api.elevenlabs.io/v1/speech-to-text",
            headers={"xi-api-key": key},
            data={"model_id": model, "diarize": "true"},  # språk auto-detekteres
            files={"file": (audio_path.name, fh, "audio/mpeg")},
            timeout=180,
        )
    resp.raise_for_status()
    data = resp.json()
    words = data.get("words") or []
    turns = (
        _diarized_words_to_turns(words)
        if words
        else [Turn(speaker="agent", text=(data.get("text") or "").strip() or "(tom)")]
    )
    return Transcript(
        name=audio_path.stem,
        call_type="ukjent",
        title=f"Ekte transkripsjon (ElevenLabs Scribe): {audio_path.name}",
        turns=turns,
    )


# --------------------------------------------------------------------------- #
# Opplastet lyd (bytes ELLER sti) — brukt av /transcribe-endepunktet            #
# --------------------------------------------------------------------------- #
def _known_sample_names() -> set[str]:
    """Navn på ferdig-lagrede demo-transkript (data/<name>.json, uten "_")."""
    return {p.stem for p in DATA_DIR.glob("*.json") if not p.name.startswith("_")}


def supports_audio(cfg: Settings | None = None) -> bool:
    """True hvis aktiv backend kan transkribere EKTE opplastet lyd.

    `mock` har ingen modell og kan ikke transkribere ukjent lyd — den slår
    bare opp ferdige samples. De øvrige backendene (faster-whisper, nb-whisper,
    azure) kan gjøre ekte lyd→tekst (forutsatt at pakke/nøkkel er på plass).
    """
    return (cfg or settings).stt_backend in (
        "faster-whisper", "nb-whisper", "openai", "elevenlabs", "azure",
    )


def transcribe_audio(
    data: bytes | str,
    name: str = "opplastet",
    cfg: Settings | None = None,
) -> Transcript:
    """Transkriber OPPLASTET lyd → Transcript.

    `data` er enten rå lyd-bytes (fra en HTTP-opplasting) eller en filsti
    (str som peker på en eksisterende fil). Bytes skrives til en temp-fil før
    en ekte backend kjøres på den.

    Backend velges som ellers (cfg.stt_backend):
      - faster-whisper / nb-whisper → ekte lokal transkripsjon (språk "no"),
        import-guardet (faller tilbake til en tydelig mock-placeholder hvis
        pakken mangler — krasjer aldri offline).
      - azure → Azure Speech (wiret integrasjonspunkt; krever nøkkel).
      - mock (default) → ingen ekte modell. Hvis `name` matcher et kjent sample
        slår vi det opp; ellers en kort placeholder-Transcript som forklarer at
        man må bruke faster-whisper/azure for ekte transkripsjon.

    Skal ALDRI krasje offline.
    """
    cfg = cfg or settings
    backend = cfg.stt_backend

    # --- mock: ingen modell. Slå opp kjent sample, ellers placeholder. ----- #
    if backend == "mock":
        # Tillat at en sti/utvidelse sniker seg inn i `name` (f.eks. en filsti
        # eller "demo_no.wav") — match mot sample-stammen.
        stem = Path(str(name)).stem if isinstance(data, str) else Path(name).stem
        candidate = stem or str(name)
        if candidate in _known_sample_names():
            return _load_sample(candidate)
        return Transcript(
            name=str(name) or "opplastet",
            call_type="ukjent",
            title="mock-STT (demo)",
            turns=[
                Turn(
                    speaker="agent",
                    text=(
                        "mock-STT: last opp via faster-whisper/azure for ekte "
                        "transkripsjon."
                    ),
                )
            ],
        )

    # --- ekte backends: trenger en faktisk fil på disk. -------------------- #
    # bytes → temp-fil; str → behandles som sti (gjenbruker _resolve_audio_path
    # i selve backenden via en sti-streng).
    tmp_path: Path | None = None
    try:
        if isinstance(data, (bytes, bytearray)):
            import tempfile

            # Behold en utvidelse hvis `name` har en (hjelper noen dekodere).
            suffix = Path(str(name)).suffix or ".wav"
            fd, tmp_name = tempfile.mkstemp(suffix=suffix, prefix="stt_upload_")
            tmp_path = Path(tmp_name)
            import os as _os

            with _os.fdopen(fd, "wb") as fh:
                fh.write(bytes(data))
            audio_arg = str(tmp_path)
        else:
            # str: en sti (eller sample-navn som _resolve_audio_path forstår).
            audio_arg = str(data)

        if backend == "faster-whisper":
            tr = _transcribe_faster_whisper(audio_arg)
        elif backend == "nb-whisper":
            tr = _transcribe_nb_whisper(audio_arg)
        elif backend == "openai":
            tr = _transcribe_openai(audio_arg)
        elif backend == "elevenlabs":
            tr = _transcribe_elevenlabs(audio_arg)
        elif backend == "azure":
            tr = _transcribe_azure(audio_arg, cfg)
        else:
            raise ValueError(f"Ukjent STT_BACKEND: {backend!r}")

        # Behold et meningsfullt navn fra opplastingen (temp-stammen er støy).
        if tmp_path is not None:
            tr = tr.model_copy(update={"name": Path(str(name)).stem or "opplastet"})
        return tr
    finally:
        if tmp_path is not None:
            try:
                tmp_path.unlink()
            except OSError:
                pass


# --------------------------------------------------------------------------- #
# Offentlig API                                                                 #
# --------------------------------------------------------------------------- #
def transcribe(audio_or_name: str, cfg: Settings | None = None) -> Transcript:
    """Transkriber lyd (eller slå opp ferdig sample) -> Transcript.

    Backend velges av cfg.stt_backend (default fra DEPLOY_TARGET).
    """
    cfg = cfg or settings
    backend = cfg.stt_backend

    if backend == "mock":
        return _transcribe_mock(audio_or_name)
    if backend == "faster-whisper":
        return _transcribe_faster_whisper(audio_or_name)
    if backend == "nb-whisper":
        return _transcribe_nb_whisper(audio_or_name)
    if backend == "openai":
        return _transcribe_openai(audio_or_name)
    if backend == "elevenlabs":
        return _transcribe_elevenlabs(audio_or_name)
    if backend == "azure":
        return _transcribe_azure(audio_or_name, cfg)

    raise ValueError(f"Ukjent STT_BACKEND: {backend!r}")


def active_backend(cfg: Settings | None = None) -> str:
    return (cfg or settings).stt_backend
