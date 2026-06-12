# data/audio/ — generert norsk demo-lyd

Denne mappen holder syntetisert norsk tale av samtale-transkriptene i `data/`.
Poenget er å demonstrere "last opp lyd → transkriber"-veien **uten mikrofon**.

> Det ligger ingen lydfiler her ennå fordi ingen TTS-pakke var installert i
> miljøet da scriptet kjørte. Følg stegene under for å generere dem.

## Generer lyd

```bash
# 1) Installer en TTS-pakke (IKKE i requirements.txt — valgfri):
pip install gtts            # online, gir .mp3 (Google TTS, lang="no")
# ELLER offline:
pip install pyttsx3         # offline, gir .wav (systemstemme)

# 2) Generer én samtale (default = salg_alarm):
python scripts/gen_call_audio.py --call salg_alarm

# ...eller alle samtaler i data/:
python scripts/gen_call_audio.py --all
```

Resultat: én lydfil per samtale, f.eks. `data/audio/salg_alarm.mp3`
(gTTS) eller `data/audio/salg_alarm.wav` (pyttsx3). Scriptet leser
`data/<navn>.json` (skjema `{"turns": [{"speaker", "text"}, ...]}`) og slår alle
replikkene sammen til én sammenhengende lydfil.

## Bruk filene mot STT

Lydfilene mates mot `POST /transcribe` med ekte norsk STT slått på:

```bash
STT_BACKEND=faster-whisper curl -F audio=@data/audio/salg_alarm.mp3 \
    http://localhost:8000/transcribe
```

Da kjøres faktisk transkripsjon (ikke det forhåndslagde transkriptet), slik at
hele lyd-til-tekst-veien kan demonstreres.
