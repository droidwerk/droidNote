# Meeting bubble: Rust shell

Slice of `docs/specs/meeting-bubble.md` that lives in `desktop/src-tauri/`.

## What the shell does

- **Start with Windows.** Commands `autostart_get() -> Option<bool>` and `autostart_set({ enabled }) -> Result<bool, String>`.
  They write or delete `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` value `DroidNote` = `"<exe>" --autostart` through `reg.exe` (no window, no new crate).
  Debug builds: `autostart_get` returns `null` and `autostart_set` fails with `"unsupported"`, so dev never registers `target/debug`.
- **`--autostart`.** The main window starts hidden (`"visible": false` in `tauri.conf.json`). Setup shows it unless the process has `--autostart`.
  A second launch with `--autostart` (single instance) does not open the main window.
- **Close to tray.** The X on the main window hides it (`prevent_close`). Tray "Sair" still exits and kills the sidecar.
- **Window `mini` (the bubble).** Created hidden at startup, 64x64 logical px (44 px bubble plus room for the level ring and the "Pausado" chip), bottom-right of the primary monitor work area, always on top, frameless, no taskbar entry, transparent, no shadow, not focusable.
  The TS side calls `setFocusable(true)` while a card or the panel is open, and resizes it anchored at the corner.
- **`main-window-state` event.** Payload `{ "state": "minimized" | "restored" | "hidden" | "shown" }`. It is sent on minimize (`Resized` + `is_minimized`), on restore (`Resized` while visible, or `Focused(true)`), on close (hidden) and on tray show, tray click, or a second launch (shown).
  The same state is never sent twice in a row. Rust also shows the bubble on `minimized`/`hidden` and hides it on `restored`/`shown`, because the main webview's JS is throttled while minimized.
- **Tray** has id `main`, so TS can set the tooltip with `TrayIcon.getById("main")` (`core:tray:default` includes `set-tooltip`).
- **Capabilities** added: `core:window:allow-set-position`, `core:window:allow-set-focusable`.

## Run and check

```
cd desktop/src-tauri
cargo check
cargo test --lib
```

Autostart can only be tried from a release build (`npm run tauri build`). Check it with `reg query HKCU\Software\Microsoft\Windows\CurrentVersion\Run /v DroidNote`.

## Rollback

- Code: revert the changes to `desktop/src-tauri/src/lib.rs`, `tauri.conf.json` and `capabilities/default.json` on this branch.
- A machine where autostart was turned on: turn the setting off, or run `reg delete HKCU\Software\Microsoft\Windows\CurrentVersion\Run /v DroidNote /f`.
