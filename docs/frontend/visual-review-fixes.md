# Visual review fixes (2026-11-13)

Work order `visual-review-fixes`. Fixes from three visual critics on real screenshots, plus the chat scope contract (`docs/backend/chat-escopo.md`). Desktop app only (`desktop/src`). Copy changed in all 7 catalogs.

## What changed

### Chat (`pages/ChatPage.tsx`, `features/chat/ContextBar.tsx`)

- The "Escolher conversas" popover is anchored to `.chat-context-bar` (`position: relative`; `.chat-pick-wrap` is `display: contents`). It no longer moves sideways when the first chip shows up. It still moves up when the chips wrap to a second line.
- Copy: `chat.new` "Novo chat", `chat.addContext` "Escolher conversas". The rail header keeps toggle, "Novo chat" and "?" on one row. "Histórico" stays for screen readers only (`sr-only`).
- Timestamps in an answer with several sources open the citation whose time is closest (60 s window). When citations from more than one conversation fall in that window, the stamp shows the short title: "14:32 · SP3 - Parte 2".
- "Usar estas conversas na próxima pergunta" shows only on the last answer, and only when its sources differ from the chips.
- Answer text is max 72ch wide.
- "Resposta interrompida" uses `--text-soft`. On the last answer it has "Continuar" (asks the model to go on) and, for an answer stopped in this session, "Gerar de novo".
- History groups: Hoje, Ontem, 7 dias, Antes. Rows show the time (today and yesterday), the full weekday, or "4 de novembro".
- Context chips skip the date when the title already has one.
- Scope contract: `ChatThread.scope_session_ids` restores every chip when a thread opens. `askChat` takes `onChatId`. The first SSE event `{chat_id}` adopts a new thread by id. If `GET /chat/{id}` returns 404 (stopped before the question was saved), the thread is dropped. Adoption by title is gone.

### Tasks (`pages/TasksPage.tsx`)

- Edit: an "Editar tarefa" button on each row. On a focused task text, Enter or F2 also opens the field. Double-click still works.
- A relative due date is anchored to the meeting date: "Amanhã · 13/11", "Até amanhã · 13/11", and weekdays count to the next one after the meeting. The raw text is in `title`. Words handled: today, tomorrow, day after tomorrow and weekday names in the 7 languages.
- Owner filters split "A e B", "A, B", "A & B" into single people. A filter matches any task that names that person.
- `.task-meta` is a 3-column grid (owner | due | origin). The origin icon is neutral, with `role="img"` and `aria-label`.
- The "Central" eyebrow is gone (`tasks.eyebrow` deleted). The "Feitas" count is neutral (`.tab-count.is-neutral`).

### Settings (`pages/SettingsPage.tsx`)

- The engine toggle calls the same `switchProvider` as the sidebar `EngineSwitch` (`onEngineChange`). It applies at once and both always agree. Exception: OpenAI without a saved key shows the key field and the engine changes on Save.
- The download size comes only from the catalog, in the UI number format ("6,1 GB"). "Download de N GB" left all `modelHelp` texts.
- OpenAI prices are gone from the model texts. "Ver preços na OpenAI" opens https://openai.com/api/pricing/ via `openExternal`.
- GPT Transcribe text was cut ("do DroidNote, .") because `modelMeta` removed "neste PC" from any text. It now removes backend labels only when they are a whole "·" item.
- "{count} modelos Whisper neste PC" (with plural forms).
- "desta escuta" is now "desta conversa" (consent, cloud banner, files help). The key seal has no comma before "quando".
- KeySeal sits under the "Chave da API" field.
- "Atualizar lista" sits at the end of the models legend. The download block shows only when a chosen model is not installed or a download runs.
- Model descriptions use the body font.

### Conversation page

- Tab "Documento" is now "Ata" (`doc.tab`). Mind map empty text, tour "Ata e abas" step and Help start text follow ("a ata" in lowercase).
- Tour: `data-tour="audio"` on `AudioPlayer`. The `player` step points at it, with `playback` as fallback and an `alt` text for conversations without audio. "Quem falou quando" is quoted in the body. "Nome e pasta" says "Logo abaixo do nome". `POP_MAX` is 340.
- "Quem falou quando": not a scale bug. SP3 Parte 3 lasts 02:13:14 and the last speech ends at 01:26:14 (1288 segments, 10 min gap at 01:09). The rest is real silence. The timeline now shows "sem fala depois de 01:26:14" and hatches the silent part.
- Summary: "Template" label is "Modelo da ata". "Regenerar" is quiet when a summary exists and asks first when the summary was edited. Word count is "10.585 palavras". No more " — " in task lines and the PNG file name.
- Folder select: wider (240px), ellipsis, full name in `title`.
- Memory tab badge = "Segue em aberto" count (`api.memory` on open; the panel updates it after a comparison). Memory chips skip the date when the title has one. The reason chip uses `--muted`.

### Mind map (`features/mindmap/MindMapPanel.tsx`)

- Opens with `scaleFit()`. Below 0.45 the text is unreadable, so a very large map stays at 0.45 and centered.
- New icons `center` and `copy` (`shared/ui/Icon.tsx`). The fit button has `aria-label`. The tooltips say that "Refazer da ata" does not use AI and "Reorganizar com IA" does.
- Stray "3": no standalone text node in the panel. It was a node clipped at the frame edge at scale 0.72; fit-to-frame removes the clipping.

### Voices, Help, palette, Library, Live

- Voice roster: "Trocar nome de {nome}" on the name button, `role="img"` on the learned mark, "microfone · som do PC" instead of "MIC · SYS". Uncertain voice chip has an `aria-label` with the warning.
- Help: the tour section comes right after "Primeiros passos" (content and table of contents). The button sits next to the chapter name, with `aria-label` "Ver este capítulo: {título}". The second line lists the step titles (no new copy). Shortcuts render one `<kbd>` per key. "Ctrl Shift R" is the only format (palette, record button tooltip, sidebar tooltip, "Ctrl V" in consent hint).
- Memory reason text: "mesma pasta, título parecido, mesmas pessoas, ou título e pessoas juntos". Chips: `brief.reason_title` "título parecido", `brief.reason_both` "título e pessoas juntos".
- Palette, Library and sidebar Recentes do not repeat the date: the palette drops the meta date, Library and Recentes show the title without its trailing date (full title in `title`). Library folder column is `minmax(150px, 220px)`.
- Live: the top strip hides "Pronto para gravar" on Ao vivo (`hideIdle`). The deck keeps it.

## Not done / notes

- The popover still moves up when the chips wrap to a second line.
- Stamps with no citation within 60 s stay plain text.
- The mind-elixir context menu is in English (library default). Not in this order.

## How to run

```
cd desktop
npm run build   # tsc --noEmit && vite build
```

Manual check on Vite :5173 with the backend on 127.0.0.1:8777: Chat > open a thread with two sources (stamps link, short title when ambiguous); Tarefas > focus a task and press F2; Preferências > switch the engine and look at the sidebar; open "SP3 - Parte 3" (tab Ata, Memória badge = Segue em aberto, timeline hint).

## Rodada final (2026-11-13)

1. **Stamps in answers** (`shared/ui/Markdown.tsx`, `pages/ChatPage.tsx`): "[01:29 José Lessa]" and "[6:58]" lose their brackets. The time becomes the chip and the rest stays as text. Chips use `white-space: nowrap`. A stamp with no citation within 60 s is a muted time (`.chat-stamp.is-muted`) with title "Sem trecho correspondente nas fontes" (`chat.stampNoSource`). Stamps are linked only to a near citation, even with a single source.
2. **Mind map**: opens with only the root and the main branches (`expanded: false` on branches that have children; the user expands). Fit is clamped to 0.7–1. The Mapa tab uses the full width and hides the transcript panel (`.workspace.is-map`). The host is as tall as the work area. On SP3 Parte 3 at a 1227 px window: 11 nodes, scale 0.7, one branch 32 px past the right edge.
3. **Tasks**: due shows the short anchored form ("Amanhã · 13/11", weekday name capitalized). The full text is in `title`, and the date never disappears. `.task-meta` is `auto auto 16px`, owner and due max 140 px with an ellipsis, and the owner has a `title`.
4. **Tour**: `.tour-spacer` is `flex-basis: 100%`, so "Voltar · Próximo" sits on its own right-aligned row.
5. **Tour**: a step shown on its fallback target uses `altTitle` when the catalog has one. The player step says "Quem falou quando" (7 catalogs).
6. **Timeline**: "sem fala depois de 01:26:14 · 02:13:14", hint muted.
7. **Task owners**: a first name that starts exactly one full name joins it ("Giovanna" → "Giovanna Biasin"). The filter uses the same mapping.
8. **Picker**: the folder filter uses the same `select` style as "Mais recentes" (`.select`). List titles drop the trailing date, since the date column shows it.
9. **Ata panel**: the first `h1` (the conversation title) is hidden on screen only. Saved text and exports keep it.
10. **Settings**: "Atualizar lista" comes right after the legend help icon.
11. **Palette footer**: `--text-soft` at 11.5 px (12.6:1 on dark `--surface`).
