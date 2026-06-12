"""Sentral konfigurasjon — env-styrt provider-valg.

KJERNEPOENG: Samme kode kjører LOKALT eller på AZURE ved å bytte
`DEPLOY_TARGET`. Sett `DEPLOY_TARGET=azure` og hele systemet peker på
Azure-tjenester (Azure AI Speech + Azure OpenAI). Sett `DEPLOY_TARGET=local`
(default) og alt kjører offline med deterministiske mock-providere.

To env-variabler bytter lokalt -> Azure:
    DEPLOY_TARGET=azure
    (+ Azure-nøkler/endpoints satt, se README)

Du kan også overstyre enkeltprovidere direkte med STT_BACKEND / LLM_BACKEND.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass(frozen=True)
class Settings:
    deploy_target: str          # "local" | "azure"
    stt_backend: str            # "mock" | "faster-whisper" | "nb-whisper" | "azure"
    llm_backend: str            # "mock" | "anthropic" | "azure-openai"

    # Azure AI Speech
    azure_speech_key: str
    azure_speech_region: str
    azure_speech_language: str

    # Azure OpenAI
    azure_openai_endpoint: str
    azure_openai_key: str
    azure_openai_deployment: str

    # Anthropic (lokal/sky-uavhengig LLM-backend)
    anthropic_api_key: str
    anthropic_model: str

    @property
    def is_azure(self) -> bool:
        return self.deploy_target == "azure"


def load_settings() -> Settings:
    """Les konfig fra miljøet.

    `DEPLOY_TARGET` setter SMARTE defaults for provider-backends:
      - local  -> STT=mock,         LLM=mock          (offline, alltid grønt)
      - azure  -> STT=azure,        LLM=azure-openai  (peker på Azure-tjenester)

    STT_BACKEND / LLM_BACKEND kan settes eksplisitt og vinner over defaults.
    Dette er hele portabilitets-poenget: én variabel (DEPLOY_TARGET) flytter
    HELE systemet, uten kodeendring.
    """
    deploy_target = _env("DEPLOY_TARGET", "local").lower()
    if deploy_target not in ("local", "azure"):
        deploy_target = "local"

    if deploy_target == "azure":
        default_stt = "azure"
        default_llm = "azure-openai"
    else:
        default_stt = "mock"
        default_llm = "mock"

    stt_backend = _env("STT_BACKEND", default_stt).lower()
    llm_backend = _env("LLM_BACKEND", default_llm).lower()

    return Settings(
        deploy_target=deploy_target,
        stt_backend=stt_backend,
        llm_backend=llm_backend,
        azure_speech_key=_env("AZURE_SPEECH_KEY"),
        azure_speech_region=_env("AZURE_SPEECH_REGION", "swedencentral"),
        azure_speech_language=_env("AZURE_SPEECH_LANGUAGE", "nb-NO"),
        azure_openai_endpoint=_env("AZURE_OPENAI_ENDPOINT"),
        azure_openai_key=_env("AZURE_OPENAI_KEY"),
        azure_openai_deployment=_env("AZURE_OPENAI_DEPLOYMENT", "gpt-4o"),
        anthropic_api_key=_env("ANTHROPIC_API_KEY"),
        anthropic_model=_env("ANTHROPIC_MODEL", "claude-opus-4-8"),
    )


# Modul-nivå singleton — lastes ved import. Re-les med load_settings() i tester.
settings = load_settings()
