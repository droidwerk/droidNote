# Onboarding B (2026-11-13)

Welcome, release notes, Help tab, tour and key seal. Desktop app only (`desktop/src`).

## What changed

- **Modal** (`shared/ui/Modal.tsx`): generic accessible dialog (overlay, focus trap, Esc, click outside, focus return, rich children). `ConfirmDialog` now renders through it; its API and behavior are the same. Each confirm request gets a key, so a new request remounts the dialog as before.
- **Update notice** (`shared/lib/useUpdateNotice.ts`) now returns `true` once the notice was closed or was not needed. App waits for it before any onboarding modal, so two modals never stack.
- **Welcome** (`features/onboarding/Onboarding.tsx`, `WelcomeModal`): shown once, only on a fresh install, after the Wizard. Three steps (Gravar, ler a Ata, Perguntar), "Fazer o tour" and "Começar", links to the product page, GitHub releases, the Help tab, and the DroidWerk about and products pages.
  - Fresh install = the Wizard opened in this run, or (install.ps1 path that skipped the Wizard) no local marks and zero conversations.
  - Existing users get `droidnote.welcomeSeen` written silently.
- **What's new** (`WhatsNewModal`, data in `shared/lib/whatsNew.ts`): shown once per major.minor to users who updated. `droidnote.lastVersion` stores the last version seen; a fresh install records it silently. Entries: `2.3` (chat Markdown/LaTeX, citations, modes, images/links/YouTube, exports) and `2.4` (memory follows the folder, Help tab, readability and keyboard). If this batch ships inside 2.3.0, move the `2.4` items into `2.3`.
- **Site links**: `siteUrl()` in `whatsNew.ts` maps the UI language to the site locale: `pt` to pt, `de` to de, everything else to en. `SiteCredit` in `Brand.tsx` uses it too.
- **Help** (`pages/HelpPage.tsx`, sidebar item "Ajuda", icon `help`): short sections with anchors, a keyboard shortcut list read from the code, a FAQ with `<details>`, "Refazer o tour" and "Informar um problema" (GitHub issues). No search box.
- **Tour** (`Tour` in `Onboarding.tsx`): four small anchored popovers (Ao vivo, Conversas, the tabs of the open conversation, Ctrl K search). Not modal, Esc or "Pular" ends it. A step whose anchor is not on screen is skipped. Starts only from the welcome or the Help page.
- **Key seal** (`shared/ui/KeySeal.tsx`): in Preferences under the OpenAI key field and in Help > Privacidade. Copy checked against `backend/app/core/secrets.py` (DPAPI, `asr_api_key` in `SECRET_SETTING_KEYS`) and the only hosts the key is sent to (`api.openai.com` transcription, chat and the key test). The test call is why the copy says "quando você usa a nuvem ou testa a chave".
- **Paper theme**: `--muted` is now `#66574a` (5.8:1 on `--bg`, 5.5:1 on `--surface-3`), darker than `--faint`.
- **Library**: `App.tsx` passes `onGoLive` to `LibraryPage`, so the first-use button shows.
- All new strings are in the 7 catalogs (`onboarding`, `whatsNew`, `tour`, `help`, `keySeal`, `nav.help`). CSS is at the end of `shared/styles/pages.css`.

## Language at first start

The welcome uses the language chosen at install, applied before it renders:

- NSIS installer: `hooks.nsh` writes `%APPDATA%\DroidNote\install-lang.txt`; the backend seeds `ui_language` from it (`main.py`, `read_install_language`).
- install.ps1: `DROIDNOTE_LANGUAGE` (or the Windows language) goes into `unattended.json`; `apply_unattended` saves `ui_language` before the API answers.
- App boot reads `getSettings().ui_language` and calls `setLocale` in the same update as `setReady(true)`. The welcome opens later (after the update check), so it never shows another language.

## How to test

```
cd desktop
npm run build   # tsc --noEmit && vite build
```

Manual, in the packaged app:

- Fresh install: clear `droidnote.welcomeSeen` and `droidnote.lastVersion` in the WebView storage and use a new data folder; the welcome shows once after the Wizard.
- Update: set `droidnote.lastVersion` to `2.2.10`; on 2.3.x the "Novidades" modal shows once.
- Existing user without marks: setup complete and at least one conversation; no welcome, release notes show.
