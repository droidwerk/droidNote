# Chat exit beta (2026-11-13)

Chat context with several conversations, and the fixes that take the Chat out of beta. Desktop app only (`desktop/src`). Backend contract: `docs/backend/chat-escopo.md`.

## What changed

### A. Context with several conversations

- **Context bar** (`features/chat/ContextBar.tsx`), right above the composer in the empty and in the conversation view. One rule: the chips are what the answer uses; no chips means all conversations.
  - Chips "Título · 12/nov ×". After 4 chips a "+N" button opens the full list.
  - Line below: "Respondendo com base em: N conversas" + "Limpar", or "todas as conversas" with no chip.
  - An excerpt sent from a transcript stays as an extra dashed chip ("Trecho selecionado"). Its conversation is also a chip.
- **"+ Conversa" popover**: search by title, folder name or date (`12/nov`, `12/11/2026`, `12 de novembro`), "Recentes" first, multi-select with a checkbox, quick filters 7 dias / 30 dias / pasta that only narrow the list. "Marcar estas N" checks the filtered list. Limit 20 (`MAX_CONTEXT`). Keyboard: arrows move, Enter toggles (also from the search field), Space toggles on the list, Esc closes and returns focus to the button.
- **Request** (`pages/ChatPage.tsx`, `send`): every turn with chips sends `scope: { session_ids: [...] }` and `session_id` = first chip (or the excerpt's conversation). No chips: `scope: null`.
- **Reopening a thread**: the backend keeps only `focus_session_id`, so it comes back as the single chip.
- **Sources**: "Usar estas conversas na próxima pergunta" replaces the chips with the conversations cited in that answer.
- **ChatTune** keeps only Modo and "Só fontes". "Onde procurar" is gone, with its `chat.scope*` keys.

### B. Exit beta

1. **Stop**: while the answer streams, Send turns into a square button (`aria-label` "Parar resposta"). `askChat` takes an `AbortSignal`. The partial text stays, marked "Resposta interrompida".
2. **Errors** show inside the turn: "Não foi possível responder.", the reason (backend message, "A resposta chegou incompleta." or "Não foi possível falar com o DroidNote neste PC." when the local server does not answer), "Tentar de novo" and "Abrir configurações". Partial text stays. Upload and link errors still use the line above the composer.
3. **History**: groups Hoje / 7 dias / Antes, relative time per row (time today, weekday this week, day and month before), "…" menu with Apagar (ConfirmDialog), search when there are more than 15 threads. Renomear is not there: the API has no rename for a chat.
4. **Empty state**: title (22px, no InfoTip) + 3 suggestions (with documents attached, 3 document suggestions). Study commands and saved prompts moved into the "/" menu.
5. **"Gerar de novo"** on the last answer resends the last question. ArrowUp in the empty field brings back the last question.
6. **Scroll**: on send, the question goes to the top and the answer runs below it. When the answer grows past the screen, a floating "Nova resposta" button follows it to the bottom.
7. **Citations**: every `[n]` is a button with a popover (title, "p. N" for documents, excerpt), on hover and on keyboard focus. Document sources are focusable too. Conversation sources read "Abrir {título} em {hora}".
8. **Copy** (pt, all 7 catalogs): "Pergunte sobre suas conversas", "Pergunte, ou digite / para comandos", "Suas perguntas ficam aqui.", "Nova conversa" as a visible label on the rail button, "nota da conversa" instead of "gravação", no "Toque". The "▾" in Salvar is now an icon.
9. **Beta badge** removed from the sidebar; `common.beta` deleted.

Removed keys: `common.beta`, `recipes.hint`, `chat.scope*`, `chat.intro`, `chat.contextLabel`, `chat.contextHintFocused`, `chat.studyLabel`, `chat.studyHint`, `chat.placeholderSession`, `chat.sourceOpen`.

## Backend gaps

- **Rename chat**: no `PATCH /chat/{id}`. The "…" menu only has Apagar.
- **Stop**: on client disconnect the streaming task is cancelled. The question is already saved (`add_chat_message` runs before the model call) but the partial answer is not. After reload the thread shows the question without an answer. The frontend adopts the new thread by title so the next question lands in it.
- **Retry after an error** sends the question again, so the saved history holds the question twice.
- **Person filter** in the picker is missing: `GET /sessions` has no participants, so search covers title, folder and date only.

## How to run

```
cd desktop
npm run build   # tsc --noEmit && vite build
```

Manual check (Vite dev on :5173 with the backend up): Chat > "+ Conversa" > check two > ask. The `/chat/ask` body has `scope.session_ids` with both ids and `session_id` = the first one.
