# UI fixes A (2026-11-13)

Batch of fixes from the UI critic review. Desktop app only (`desktop/src`).

## What changed

- **Memory chips** (`features/memory/MemoryPanel.tsx`) show why a past meeting is in the series (`brief.reason_*`). New reason `folder` ("mesma pasta") in `shared/api/types.ts` and all 7 catalogs.
- **Memory tab** (Session and Live): `BriefCard` runs with `pendingOnly`, so it only adds the pending task list. It has no empty state and no meeting list there; `MemoryPanel` owns those.
- **AI engine off**: `MemoryPanel` reads `api.setupStatus().summarize_ready` itself. With the engine off it shows `memory.engineOff` and skips the automatic comparison. This covers every caller, so `SessionPage` needs no new prop.
- **Library first use** (`pages/LibraryPage.tsx`): with zero conversations it shows one sentence and a "Gravar a primeira conversa" button. The button only renders when the new optional prop `onGoLive` is passed. "Esta pasta está vazia" now shows only when the list is filtered.
- **Contrast** (`shared/styles/tokens.css`):
  - `--faint`: dark `#83838d` (5.0:1 on surface-2, 4.7:1 on surface-3), light `#6c6c74` (4.7:1 on bg, 4.5:1 on surface-3), paper `#72625a` (4.9:1 on bg, 4.6:1 on surface-3).
  - New `--accent-fill` / `--accent-fill-hi` for filled controls with text: dark and light `#c73600` (5.3:1 under white), hover `#b83200` (6.0:1); paper `#a8390a` (6.0:1 under `#fbf7ec`), hover `#9e3608` (6.6:1). The top gloss went from 20% to 10% white, so the worst point stays at 4.6:1. The brand orange `--accent` still drives accents, borders, LEDs and focus.
  - The memory chip date and labels went from 10px to 11.5px.
- **Focus**: the global `:focus-visible` is now a solid 2px `--accent` ring with a 2px offset. Every `outline: none` either went away (inputs with their own border) or got a `:has(:focus-visible)` ring on its framed parent (search field, chat composer, task composer, notes composer, palette, folder select, link row, note editor, model menu).
- **Tabs** (`shared/ui/Tabs.tsx`): roving tabindex, ArrowLeft/Right/Home/End with automatic activation, `aria-controls`, and a `tabpanel` with `aria-labelledby`. Used by `SideTabButton` on the Session and Live pages. The side tab CSS now lives in one rule in `tokens.css`. The copies in `library.css`, `graph.css` and `focus.css` are gone.
- **"Perguntas prontas" menu** (`recipes.title`, all languages): it has `aria-haspopup` and closes on an outside click or Esc. It shares `useMenuDismiss` with the Export menu.
- **Feedback**: success toasts after a rename (`session.renamed`) and after a folder change (`session.folderSaved`). The delete button has 12px extra space from Exportar.
- **Copy (pt)**: the UI uses Conversa, Ata, Gravar and Ao vivo instead of sessão and captura. The status bar reads "Transcrição neste PC" / "Transcrição na nuvem (OpenAI)", and the idle state reads "Pronto para gravar". The pt catalog has no em dashes. In other languages, only the keys whose meaning changed were updated.

## How to run

```
cd desktop
npm run build   # tsc --noEmit && vite build
```
