# Tour completo (2026-11-13)

Work order `tour-completo`. Implements `docs/uxui/tour-completo.md`: 9 chapters, 41 steps. Desktop app only (`desktop/src`). Also wires the chat contract from `docs/backend/chat-escopo.md` (rename, interrupted answers, retry).

## What changed

### Tour

- `features/onboarding/tourScript.ts`: the script. Chapters, steps and selectors only, no text. Also the progress storage (`droidnote.tour.v1`, every access in `try/catch`) and `requestTour(chapter?)`, a window event the App listens to.
- `features/onboarding/Tour.tsx`: `Tour` (picker, step balloon, pause pill, cards) and `TourButton` (the "?" in each page header). The old 4-step `Tour` left `Onboarding.tsx`.
- Entries: welcome "Fazer o tour", Help header "Tour guiado", Help section `#help-tour` (one "Ver este capítulo" per chapter), the "?" on Ao vivo, Conversas, Conversa, Tarefas, Chat and Preferências, and the palette command "Fazer o tour". The tour never opens on its own.
- The "?" runs one chapter with "Passo n de m". Ao vivo continues into `gravar`, Conversa into `abas` (spec 5.2). "Pular capítulo" shows only when another chapter follows.
- Behaviour: no backdrop, nothing inert. The tour only changes the view (`setView`) and opens the most recent conversation (or keeps the open one). It never clicks, records, changes a tab or a preference. Settings opens without touching the selected tab.
- Anchor search: polls every 150 ms. Waits 600 ms, or 3 s when the tour just changed the view (the page loads data). Zero-size anchors count as missing. Missing anchor: uses `fallback` (with the `alt` body) or skips the step in the direction the person was moving. All steps missing: "Nada para mostrar aqui agora".
- If the anchor disappears because the person left the view, the balloon becomes the "Tour pausado" pill. "Continuar" goes back to the step's view.
- While a modal (`aria-modal="true"`: welcome, confirm, palette) is open, the balloon hides and Esc belongs to the modal.
- Under 640 px the balloon goes below or above the anchor, never beside it. Width `min(300px, 100vw - 24px)`; picker and cards `min(340px, 100vw - 24px)`.

### data-tour attributes

`nav`, `recent`, `search`, `engine`, `mode`, `capture-language`, `template`, `sources`, `record`, `consent`, `mini`, `upcoming`, `folders`, `library-search`, `library-select`, `library-first`, `session-head`, `playback`, `transcript`, `session-ask`, `export`, `task-new`, `task-filters`, `task-list`, `chat-context`, `chat-new`, `chat-study`, `chat-attach`, `chat-tune`, `chat-rail`, `settings-tabs`. `Button` (`shared/ui/primitives.tsx`) now passes `data-tour`.

### Differences from the spec

- **Chat chapter** follows the current `ChatPage` (`docs/frontend/chat-exit-beta.md`), not the old screen:
  - `chat.contexto` points at the context bar (`chat-context` on `ContextBar`), always visible. Text: "Clique em Conversa para escolher...". The `chat-new` fallback is not needed; the attribute is there.
  - `chat.comandos`: study commands moved into the "/" menu. `chat-study` sits on the composer form. Text tells to type /.
  - `chat.fontes` without an answer on screen falls back to the composer with the `alt` body.
- **i18n shape**: alternative bodies are `tour.ch.<chapter>.<step>.alt`, not `<step>Alt.body`.
- **Text**: `conversa.player` says "Ouça o áudio" instead of "Toque o áudio" (no "Toque" in the app).
- **Russian** `tour.steps` is "Шагов: {count}", so it needs no plural forms.

### Copy fixes

- pt: `nav.emptySessions` and `live.emptyIdle` say "Clique em Gravar".
- `chat.openSettings` (error card button): "Abrir preferências" in pt, and the same term as `palette.openSettings` in en, es, fr, it. de and ru already matched.
- Old keys removed from all 7 catalogs: `tour.count`, `tour.skip`, `tour.liveTitle`, `tour.liveBody`, `tour.libraryTitle`, `tour.libraryBody`, `tour.tabsTitle`, `tour.tabsBody`, `tour.askTitle`, `tour.askBody`.

### Chat contract

- `api.renameChat(id, title)` → `PATCH /chat/{id}`. Thread "…" menu has "Renomear": inline field, Enter or blur saves, Esc cancels, title trimmed to 120. Toast on success and on error.
- `ChatMessage.interrupted`: reloaded threads show "Resposta interrompida" from the backend field.
- `askChat` takes `retry`; "Tentar de novo" sends `retry: true` with the same `chat_id` and question.

## How to run

```
cd desktop
npm run build   # tsc --noEmit && vite build
```

Manual check on Vite :5173 with the backend up: Ajuda > Tour guiado > Começar do início, then "Próximo" through to "Tour concluído". To reset: `localStorage.removeItem("droidnote.tour.v1")`.
