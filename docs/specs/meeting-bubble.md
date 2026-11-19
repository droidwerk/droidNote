# Spec: meeting bubble, start with Windows, silence alert

Status: approved by the CEO on 2026-11-19 ("Pode construir essa versão. Deixe a bolha um pouco menor só mas com os mesmos comandos").
Reference mockup: `docs/uxui/proposals/meeting-bubble-simple.html` (the source of truth for layout, copy and states).
Branch: `feat/meeting-bubble`.

## Goal

DroidNote starts with Windows and waits in the tray. A small floating bubble replaces the separate mini window: it shows recording state, grows into the mini panel on click, appears when the main window is minimized, asks to record when a meeting starts, and asks "A reunião ainda está acontecendo?" after 5 minutes without speech during a recording.

## Non-goals

- "Detectar fala no microfone" (idle microphone listener). Needs a legal-lgpd opinion first. Not built, not shown in settings.
- Chat or template fixes (separate cycle).
- Any change to the installer beyond what is needed for the Run key (the NSIS uninstaller already removes `HKCU\...\Run\DroidNote`).

## Behaviour

### Start with Windows and tray

- Setting "Iniciar com o Windows" writes or removes `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` value `DroidNote` = `"<exe path>" --autostart`. Release builds only; in debug builds the command is a no-op that reports "unsupported" so dev never registers `target/debug`.
- The toggle reads its state from the registry when the settings page opens (registry is the source of truth).
- Launched with `--autostart`: the main window is not shown; the app lives in the tray.
- Closing the main window (X) hides it instead of exiting. "Sair" in the tray menu still exits and kills the sidecar.

### Bubble (replaces the mini window)

- One always-on-top, frameless, skip-taskbar, non-focus-stealing window. Bubble size 44 px (CEO asked for a bit smaller than the 52 px mockup). The window resizes when the bubble grows into a card or the mini panel, anchored at the bubble's corner.
- Three looks only:
  - grey = idle (paused shows grey with a pause icon and a "Pausado" chip);
  - orange = recording, with a thin ring that follows the audio level (from the existing `monitor` WS event);
  - amber with "?" = a question is waiting.
- Shown when: the main window is minimized or hidden AND (recording, paused, or app running). Never shown while the main window is visible and not minimized.
- Minimizing the main window shows the bubble; restoring/focusing the main window hides it.
- Click on the bubble:
  - recording or paused: grows into the mini panel (existing MiniConsole content: tabs Ao vivo / Perguntar / Contexto, 4 markers grouped behind one "Marcar" button, note field, end button; "Continuar" when paused). "Recolher" or Esc shrinks back to the bubble.
  - idle: opens a small card "Nada está gravando." with one button "Gravar". A stray click never starts a recording.
  - question waiting: focuses the question card.
- The setting "Abrir a mini janela ao gravar" is replaced: recording no longer opens a panel by itself.

### Conversation detected

- Uses the existing meeting watcher (`meetings.py`, WS `type:"meeting"`). No new microphone access.
- Mode "Perguntar": if the bubble is visible, the card "Começou uma conversa. Gravar?" (line: "O <app> está usando o microfone.") opens from it with "Gravar" and "Agora não". If the main window is visible, the existing in-window banner stays. Card disappears after 20 s (dismiss).
- Mode "Gravar" (auto) and "Nada" keep current behaviour.
- Settings segmented control labels: "Perguntar / Gravar / Nada" (maps to existing ask / auto / off).

### Silence or music alert (during a recording)

- Backend tracks, per recording, the last time speech was detected on either channel (existing VAD) and whether there was audio energy without speech.
- After 300 s with no speech on mic AND system: publish WS `{"type":"idle_alert","status":"asked","kind":"silence"|"music","session_id":...}`. `music` = audio energy above the silence threshold for most of the window but no speech; otherwise `silence`.
- Copy: title "A reunião ainda está acontecendo?"; line silence "Ninguém falou nos últimos 5 minutos."; music "Nos últimos 5 minutos só tocou música.".
- Two buttons only: "Sim, continuar" (resets the timer, `status:"dismissed"`) and "Encerrar e gerar nota" (stops capture; note generation follows the existing stop flow).
- Any speech of 3 s or more closes the alert by itself (`status:"cleared"`) and resets the timer.
- No answer in 120 s: capture pauses by itself (`status:"auto_paused"`). Never stops, never deletes.
- Shown in the bubble card (amber) when the bubble is visible; otherwise as a toast inside the main window. Tray icon tooltip mentions the question.
- Setting "Avisar depois de 5 min sem fala" (default on). Off = no alert.
- Timer runs only while recording and not paused; resets on resume.

### Pause

- New: `POST /capture/pause` and `POST /capture/resume`. While paused, audio chunks are dropped (no ASR, no WAV write), the session stays `recording`, state carries `paused: true`, WS `capture` event reflects it.
- Bubble and mini show "Pausado" with "Continuar".

## Acceptance criteria

- C1 `HKCU Run` value is written/removed by the toggle in release builds; debug builds never write it; toggle reflects the registry on open.
- C2 `--autostart` launch shows no main window; tray works; "Abrir DroidNote" shows the window.
- C3 Closing the main window hides it; tray "Sair" exits and kills the sidecar.
- C4 Minimizing the main window shows the 44 px bubble; restoring hides it; bubble never visible together with an unminimized main window.
- C5 Bubble looks: grey idle, orange recording with level ring, amber question, grey + pause icon + "Pausado" chip when paused.
- C6 Click on recording bubble opens the mini panel (tabs, "Marcar" with 4 markers, note field, end button); Recolher/Esc returns to bubble with focus on it. Idle click opens the "Gravar" card and does not record.
- C7 Meeting detected in "Perguntar" mode with bubble visible shows the card with Gravar / Agora não; auto-dismiss in 20 s.
- C8 Backend emits `idle_alert asked` after 300 s without speech while recording (time injectable for tests), `kind` silence vs music correct, `cleared` on ≥3 s speech, `auto_paused` 120 s after asked with no answer, nothing when the setting is off or capture is paused.
- C9 "Sim, continuar" resets the timer; "Encerrar e gerar nota" stops the capture.
- C10 Pause/resume endpoints work; paused drops audio and writes no WAV frames; resume continues the same session.
- C11 Settings card "Reuniões" shows: Iniciar com o Windows; Ao perceber uma conversa: Perguntar / Gravar / Nada; Avisar depois de 5 min sem fala. No "Detectar fala" control.
- C12 pt-BR copy exactly as above; other locales get equivalent strings; `npm run build` (tsc), `cargo check`, backend `pytest` all pass; prefers-reduced-motion disables bubble animations; keyboard and screen reader labels as in the mockup.
