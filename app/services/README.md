# Services Module

The `app.services` package encapsulates modular sub-services:

- **Reminders & Scheduler:** Offline task scheduling and recurring reminders that persist across process restarts.
- **Journal:** Private reflective journaling with strict privacy boundaries and explicit user control.
- **Voice / TTS:** Android native integration (e.g. `termux-tts-speak` via Termux:API) to synthesize responses without needing cloud TTS providers.

