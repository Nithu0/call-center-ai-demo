# Makefile — call-senter-AI-demo
# Praktiske targets. Bruker .venv/bin/... direkte, så det funker uten aktivert venv.
# Kjør `make` (eller `make help`) for å liste alt.

VENV    := .venv
PY      := $(VENV)/bin/python
PIP     := $(VENV)/bin/pip
PORT    ?= 8000

.DEFAULT_GOAL := help

.PHONY: help install install-real audio verify-stt verify-llm status run test

help: ## Vis alle targets
	@echo "call-senter-AI-demo — make targets:"
	@echo ""
	@echo "  make install       Installer kjerne-avhengigheter (offline mock-demo)"
	@echo "  make install-real  Sett opp ekte verktøy (faster-whisper, API-klienter)"
	@echo "  make audio         Generer alle demo-lydklipp"
	@echo "  make verify-stt    Verifiser tale-til-tekst på et lydklipp"
	@echo "  make verify-llm    Verifiser LLM-koblingen"
	@echo "  make status         Påminnelse om /status-siden i nettleseren"
	@echo "  make run            Start API-en (uvicorn, reload, port $(PORT))"
	@echo "  make test           Kjør testene (pytest)"
	@echo ""
	@echo "Hurtigstart for ekte verktøy: se KOBLE-OPP.md"

install: ## Installer kjerne-avhengigheter
	$(PIP) install -r requirements.txt

install-real: ## Sett opp ekte verktøy (faster-whisper + API-klienter)
	bash setup-real.sh

audio: ## Generer alle demo-lydklipp
	$(PY) scripts/gen_all_audio.py --all

verify-stt: ## Verifiser tale-til-tekst på salg_alarm.mp3
	$(PY) scripts/verify_stt.py data/audio/salg_alarm.mp3

verify-llm: ## Verifiser LLM-koblingen
	$(PY) scripts/verify_llm.py

status: ## Påminnelse om /status-siden
	@echo "åpne http://127.0.0.1:8000/status i nettleseren"

run: ## Start API-en (uvicorn, reload)
	$(PY) -m uvicorn app.main:app --reload --port $(PORT)

test: ## Kjør testene
	$(PY) -m pytest -q
