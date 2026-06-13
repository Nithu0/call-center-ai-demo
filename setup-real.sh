#!/usr/bin/env bash
# =====================================================================
#  setup-real.sh — koble PÅ ekte verktøy for call-senter-AI-demoen
# =====================================================================
#  Idempotent. Installerer valgfrie ekte backends, genererer norsk
#  testlyd og kjører en smoke-transkripsjon — alt med ÉN kommando.
#
#  Bruk:
#     ./setup-real.sh              # default: alt UNNTATT torch/nb-whisper
#     ./setup-real.sh --minimal    # kun faster-whisper + gTTS (lokalt, ingen nøkkel)
#     ./setup-real.sh --nb-whisper # alt + transformers + torch (tungt)
#
#  Nøkkel-poeng:
#     faster-whisper = LOKAL STT. INGEN nøkkel, INGEN Azure (CPU/ctranslate2).
#     gTTS           = norsk TTS for testlyd. INGEN nøkkel (bruker nett).
#     openai/anthropic/azure = krever API-nøkkel i .env (se .env.example).
# =====================================================================
set -euo pipefail

cd "$(dirname "$0")"
ROOT="$(pwd)"

REQ_FILE="requirements-real.txt"
MODE="default"   # default | minimal | nb-whisper

# --- Parse argument ---
for arg in "$@"; do
  case "$arg" in
    --minimal)    MODE="minimal" ;;
    --nb-whisper) MODE="nb-whisper" ;;
    -h|--help)
      echo "Bruk: ./setup-real.sh [--minimal | --nb-whisper]"
      echo "  (ingen flagg) = alt unntatt torch/nb-whisper"
      echo "  --minimal     = kun faster-whisper + gTTS (lokalt, ingen nøkkel)"
      echo "  --nb-whisper  = alt + transformers + torch (tungt)"
      exit 0
      ;;
    *)
      echo "FEIL: ukjent argument '$arg'. Prøv --help." >&2
      exit 2
      ;;
  esac
done

echo "==============================================================="
echo " setup-real.sh — modus: ${MODE}"
echo "==============================================================="

# ---------------------------------------------------------------------
# STEG 1: Forutsett at .venv finnes og aktiver den.
# ---------------------------------------------------------------------
echo
echo "[1/5] Sjekker virtuelt miljø (.venv) ..."
if [ ! -d "${ROOT}/.venv" ]; then
  cat >&2 <<EOF
FEIL: fant ingen .venv i ${ROOT}.
Opprett den først, f.eks.:
    python3 -m venv .venv
    . .venv/bin/activate
    pip install -r requirements.txt
Kjør deretter ./setup-real.sh på nytt.
EOF
  exit 1
fi
# shellcheck disable=SC1091
. "${ROOT}/.venv/bin/activate"
echo "      .venv aktivert ($(python --version 2>&1))"

# ---------------------------------------------------------------------
# STEG 2: Installer ekte-verktøy-pakker etter valgt modus.
# ---------------------------------------------------------------------
echo
echo "[2/5] Installerer ekte-verktøy-pakker (modus: ${MODE}) ..."
if [ ! -f "${REQ_FILE}" ]; then
  echo "FEIL: fant ikke ${REQ_FILE} i ${ROOT}." >&2
  exit 1
fi

case "$MODE" in
  minimal)
    echo "      → kun faster-whisper + gTTS (lokalt, ingen nøkkel)"
    pip install "faster-whisper==1.0.3" "gTTS==2.5.1"
    ;;
  default)
    echo "      → alt i ${REQ_FILE} (torch/nb-whisper er allerede utkommentert der)"
    pip install -r "${REQ_FILE}"
    ;;
  nb-whisper)
    echo "      → alt i ${REQ_FILE} + transformers + torch (tungt, ~GB)"
    pip install -r "${REQ_FILE}"
    pip install "transformers==4.44.2" "torch==2.4.0"
    ;;
esac
echo "      Installasjon ferdig."

# ---------------------------------------------------------------------
# STEG 3: Generer norsk testlyd for samples (guard hvis scriptet mangler).
# ---------------------------------------------------------------------
echo
echo "[3/5] Genererer norsk testlyd for samples ..."
if [ -f "${ROOT}/scripts/gen_all_audio.py" ]; then
  python scripts/gen_all_audio.py --all || \
    echo "      ADVARSEL: lyd-generering feilet (fortsetter likevel)."
else
  echo "      HOPPER OVER: scripts/gen_all_audio.py finnes ikke ennå"
  echo "      (lages av en annen agent). Alternativt: python scripts/gen_call_audio.py --all"
fi

# ---------------------------------------------------------------------
# STEG 4: Smoke-transkripsjon med lokal faster-whisper (guard).
# ---------------------------------------------------------------------
echo
echo "[4/5] Smoke-transkripsjon (lokal faster-whisper, ingen nøkkel) ..."
SAMPLE=""
for cand in \
    "${ROOT}/data/audio/salg_alarm.mp3" \
    "${ROOT}/data/audio/salg_alarm.wav"; do
  if [ -f "$cand" ]; then SAMPLE="$cand"; break; fi
done
# Fallback: ta første lydfil som finnes i data/audio/.
if [ -z "$SAMPLE" ]; then
  SAMPLE="$(find "${ROOT}/data/audio" -maxdepth 1 -type f \
            \( -name '*.mp3' -o -name '*.wav' \) 2>/dev/null | head -n1 || true)"
fi

if [ -f "${ROOT}/scripts/verify_stt.py" ] && [ -n "$SAMPLE" ] && [ -f "$SAMPLE" ]; then
  echo "      Transkriberer: ${SAMPLE}"
  STT_BACKEND=faster-whisper FASTER_WHISPER_MODEL=base \
    python scripts/verify_stt.py "$SAMPLE" || \
    echo "      ADVARSEL: smoke-transkripsjon feilet (fortsetter til oppsummering)."
else
  echo "      HOPPER OVER smoke-transkripsjon:"
  [ -f "${ROOT}/scripts/verify_stt.py" ] || echo "        - scripts/verify_stt.py finnes ikke ennå (lages av annen agent)"
  [ -n "$SAMPLE" ] || echo "        - ingen lydfil funnet i data/audio/ (kjør steg 3 først)"
fi

# ---------------------------------------------------------------------
# STEG 5: Oppsummering — hvilke backends er klare?
# ---------------------------------------------------------------------
echo
echo "[5/5] Oppsummering — backend-status"
echo "---------------------------------------------------------------"

# Hjelper: er en python-modul importerbar?
_has_module() { python -c "import importlib.util,sys; sys.exit(0 if importlib.util.find_spec('$1') else 1)" 2>/dev/null; }
# Hjelper: er BÅDE transformers OG torch installert? (nb-whisper)
_has_nb_whisper() { _has_module transformers && _has_module torch; }
# Hjelper: er en env-variabel (ev. fra .env) satt?
_has_key() {
  # Sjekk miljøet først, deretter .env (uten å printe verdien).
  if [ -n "${!1:-}" ]; then return 0; fi
  [ -f "${ROOT}/.env" ] && grep -Eq "^[[:space:]]*$1[[:space:]]*=[[:space:]]*[^[:space:]]" "${ROOT}/.env"
}
_mark() { if "$@"; then printf "KLAR "; else printf "----- "; fi; }

echo "STT-backends (env STT_BACKEND):"
printf "  %s mock           (alltid tilgjengelig — offline placeholder)\n" "KLAR "
printf "  %s faster-whisper  (LOKAL, ingen nøkkel/Azure)\n"  "$(_mark _has_module faster_whisper)"
printf "  %s nb-whisper      (lokal; krever transformers + torch)\n" "$(_mark _has_nb_whisper)"
printf "  %s openai          (Whisper-API; krever OPENAI_API_KEY i .env)\n" "$( if _has_module openai && _has_key OPENAI_API_KEY; then printf 'KLAR '; else printf '----- '; fi )"
printf "  %s azure           (Azure AI Speech; krever azure-pakke + AZURE_SPEECH_KEY)\n" "$( if _has_module azure.cognitiveservices.speech && _has_key AZURE_SPEECH_KEY; then printf 'KLAR '; else printf '----- '; fi )"

echo
echo "LLM-backends (env LLM_BACKEND):"
printf "  %s mock           (alltid tilgjengelig — offline)\n" "KLAR "
printf "  %s anthropic       (Claude; krever ANTHROPIC_API_KEY i .env)\n" "$( if _has_module anthropic && _has_key ANTHROPIC_API_KEY; then printf 'KLAR '; else printf '----- '; fi )"
printf "  %s azure-openai    (Azure OpenAI; krever openai-pakke + AZURE_OPENAI_KEY)\n" "$( if _has_module openai && _has_key AZURE_OPENAI_KEY; then printf 'KLAR '; else printf '----- '; fi )"

echo
echo "Testlyd (norsk TTS for samples):"
printf "  %s gTTS            (norsk testlyd; ingen nøkkel, bruker nett)\n" "$(_mark _has_module gtts)"

echo "---------------------------------------------------------------"
echo "Forklaring:"
echo "  faster-whisper = LOKAL STT. INGEN nøkkel, INGEN Azure (CPU/ctranslate2)."
echo "  openai / anthropic / azure = krever API-nøkkel i .env (se .env.example)."
echo
echo "Neste steg:"
echo "  - Start demoen:        ./run.sh"
echo "  - Backend-status-side: http://127.0.0.1:8000/status"
echo "  - Dokumentasjon:       docs/ekte-verktoy.md"
echo "  - Slå PÅ lokal STT:    STT_BACKEND=faster-whisper ./run.sh"
echo "==============================================================="
