"""Pluggbart provider-lag.

Hele systemets portabilitet bor her: `stt.transcribe()` og `llm.analyze()`
velger backend ut fra env-variabler. Samme kall-signatur uansett om vi
kjører mock (offline), lokal Whisper, Anthropic, eller Azure-tjenester.
"""
