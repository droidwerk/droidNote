# Meeting bubble: backend (pause, silence alert)

Spec: `docs/specs/meeting-bubble.md` (C8, C9, C10).

## What changed

- `CaptureState.paused` (also in the WS `capture` event, `CaptureStateOut` and the WS `hello`).
- `CaptureService.pause()` / `resume()`: while paused, `_on_chunk` drops audio (no ASR, no WAV write).
  The session stays `recording`. Paused time is subtracted from chunk timestamps, so segment times
  stay in sync with the WAV. On the first paused chunk the speech buffers are flushed, so no ASR
  window spans the pause.
- Silence alert (`idle_tick`, run every 1 s by a task started in `start()` and cancelled in `stop()`):
  - 300 s without speech on mic and system: WS `{"type":"idle_alert","status":"asked","kind":...}`.
    `kind="music"` when more than half of the chunks since the last speech had energy
    (`RMS_THRESHOLD`, mic measured before AGC) but no speech; otherwise `silence`.
  - 3 s of continuous speech after the question: `cleared`.
  - 120 s after the question without answer: `pause()` and `auto_paused`.
  - No timers while paused or with the `silence_alert` setting off (read at `start()`).
  - The pending question is `capture.idle_alert`; the WS `hello` sends it to windows that connect late.
- Endpoints (token required): `POST /capture/pause`, `POST /capture/resume`,
  `POST /capture/idle-alert/dismiss` (resets the timer, publishes `dismissed`). All return `CaptureStateOut`.
  "Encerrar e gerar nota" uses the existing `POST /capture/stop`.
- Setting `silence_alert` (default `true`) in `SettingsOut`/`SettingsIn`, stored like `auto_summary`.

## Known limits

- Speech detection for the alert uses Silero when `neural_vad` is on (the app default). Without it,
  speech is energy-only, so music counts as speech and `kind="music"` never fires.
- Silero can flag sung vocals as speech, which resets the timer.
- Paused keeps the mic stream open, so the OS mic indicator stays on.

## How to run

```
cd backend
.venv/Scripts/python.exe -m pytest -q tests/test_capture.py
```

Clock and thresholds are injectable (`CaptureService(clock=...)`, `IDLE_*` constants) so the tests run fast.
