# Meeting bubble (frontend)

Spec: `docs/specs/meeting-bubble.md`. Mockup: `docs/uxui/proposals/meeting-bubble-simple.html`.

## What changed

- `desktop/src/features/mini/MiniConsole.tsx`: the `mini` window is now the bubble (44 px). Views: bubble, "Gravar" card (idle click), meeting card ("Começou uma conversa. Gravar?", 20 s then `dismissMeeting`), amber alert card (`idle_alert asked`: "Sim, continuar" calls `/capture/idle-alert/dismiss`, "Encerrar e gerar nota" calls stop), and the mini panel (tabs Ao vivo / Perguntar / Contexto, "Marcar" with the 4 markers, note field, Continuar when paused, end button, Recolher / Esc).
  - Looks: grey idle, orange with a level ring from the WS `monitor` rms, amber "?" for a question, grey pause icon plus "Pausado" chip when paused.
  - A `ResizeObserver` on `.bubble-box` resizes the window to its content.
  - Pointer drag over 4 px calls `startDragging`; a plain click opens the card or panel.
  - Listens to `main-window-state` (show on minimized/hidden, hide on restored/shown) and `mini-open-panel`.
- `desktop/src/shared/lib/miniWindow.ts`:
  - `resizeMiniWindow(w, h)` keeps the bottom-right corner fixed and clamps the window to the monitor's top and left edges.
  - `setMiniFocus(on)` calls `setFocusable` and, when `on` is true, also focuses the window.
  - `openMiniPanel()` is the main window "mini" button: it emits `mini-open-panel` and minimizes the main window.
  - `setTrayHint(text)` sets the tooltip on tray id `main`.
  - Removed: `openMiniWindow`, `closeMiniWindow`.
- `desktop/src/app/App.tsx`:
  - The mini window no longer opens by itself when a recording starts.
  - Handles the `idle_alert` WS event and `hello.idle_alert`, and carries `paused` through the capture state.
  - Shows an in-window banner (`CaptureAlertBanner` in `features/meeting/MeetingBanner.tsx`): the 2-button question, or "Pausado" with "Continuar".
  - The tray tooltip mentions the question while it waits for an answer.
- `desktop/src/pages/SettingsPage.tsx`, "Reuniões" card:
  - "Iniciar com o Windows" uses `invoke("autostart_get" / "autostart_set")` and is hidden when the result is `null` or outside Tauri.
  - "Ao perceber uma conversa": Perguntar / Gravar / Nada (`meeting_detection` ask / auto / off).
  - "Avisar depois de 5 min sem fala" (`silence_alert`).
  - The "Mini console ao gravar" toggle is gone. The `droidnote.miniAuto` localStorage key is no longer read.
- `shared/api`: `pauseCapture`, `resumeCapture`, `dismissIdleAlert`, `CaptureState.paused`, `Settings.silence_alert`.
- i18n: new `mini.*` keys in all 7 catalogs. `meeting.mode_off`/`mode_auto` are now Nada / Gravar, and `meeting.settingsTitle` is now Reuniões.
- CSS (`shared/styles/workflow.css`):
  - The `html.is-mini` background is now transparent.
  - New `.bubble*` rules.
  - `.meeting-banner.is-ask` uses amber.
  - `prefers-reduced-motion` turns off the pulse, the grow animation and the ring motion.

## Shell needs (not in this slice)

- Capabilities: `core:window:allow-set-position`, `core:window:allow-set-focusable` and `core:window:allow-minimize`.
- The tray needs `TrayIconBuilder::with_id("main")`.
- The `mini` window is created hidden, transparent, without a shadow, and with `focusable(false)`.

## How to run

- Type check: `cd desktop && npx tsc --noEmit`.
- Browser dev: `npm run dev`, then open `http://localhost:5173/#mini` to see the bubble. Tauri calls are guarded, so resizing, focus and window events do nothing in a normal browser.
