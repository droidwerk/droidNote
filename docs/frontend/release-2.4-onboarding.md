# Release 2.4 onboarding (2026-11-19)

What's new list for 2.4 and a "Start with Windows" step in the welcome. Desktop app only (`desktop/src`).

## What changed

- **What's new** (`shared/lib/whatsNew.ts`): `WHATS_NEW["2.4"]` with five items: `bubble`, `autostart`, `stillThere`, `pause`, `detectAsk`. Strings in `whatsNew.items.*` in the 7 catalogs. `newsBetween("2.3.x", "2.4.0")` returns them; a later 2.4 patch without its own list shows nothing.
- **Welcome** (`features/onboarding/Onboarding.tsx`, `WelcomeModal`): a fourth step "Iniciar com o Windows" (title reuses `mini.autostartTitle`, body `onboarding.step.autostartBody`) with a small ghost button "Ligar" that calls `autostart_set { enabled: true }`, then shows "Ligado" disabled and moves focus back to "Começar".
  - The modal reads `autostart_get` itself (`useAutostart`), so `App.tsx` did not change.
  - The step shows only when the first answer is `false`. `null` (dev build, browser) or `true` (already on) hides it.
  - Errors from `autostart_set` go to the toast, as in Preferences.
  - New strings: `onboarding.step.autostartBody`, `onboarding.autostartOn`, `onboarding.autostartDone`, `onboarding.autostartLabel`, `onboarding.autostartDoneLabel` (7 catalogs). CSS: `.welcome-inline-action` in `shared/styles/pages.css`.

## How to test

- `cd desktop && npx tsc --noEmit`.
- Welcome in the browser: `localStorage.removeItem("droidnote.welcomeSeen")` and `"droidnote.lastVersion"` with an empty data dir, reload. The autostart step is hidden (no Tauri).
- Welcome in the release build (`npm run tauri build`): fresh install with autostart off shows the step; "Ligar" turns it on (check Preferences > Reuniões).
- What's new: set `droidnote.lastVersion` to `2.3.1` and run a 2.4.0 build.
