/**
 * Roteiro do tour (docs/uxui/tour-completo.md). Só seletores e ids: o texto vem de `tour.ch.<capítulo>.<passo>`.
 * `fallback` é tentado quando `selector` não acha nada; com ele, o corpo usa `tour.ch.<capítulo>.<passo>.alt`.
 */
export type TourView = "live" | "library" | "session" | "tasks" | "chat" | "settings";

export interface TourStep {
  id: string;
  selector: string;
  fallback?: string;
  /** Usa a última ocorrência na tela (ex.: as fontes da resposta mais recente). */
  last?: boolean;
}

export interface TourChapter {
  id: string;
  /** Tela para onde o tour vai antes de cada passo; sem ela, mantém a atual. */
  view?: TourView;
  /** Precisa de uma conversa gravada aberta. */
  session?: boolean;
  /** Controles que travam durante a gravação: o corpo recebe `tour.lockedNote`. */
  lockable?: boolean;
  steps: TourStep[];
}

const tour = (name: string) => `[data-tour="${name}"]`;

export const CHAPTERS: TourChapter[] = [
  {
    id: "basico",
    steps: [
      { id: "menu", selector: tour("nav") },
      { id: "recentes", selector: `${tour("recent")}:has(.session-group)`, fallback: tour("recent") },
      { id: "busca", selector: tour("search") },
      { id: "motor", selector: tour("engine") },
    ],
  },
  {
    id: "preparar",
    view: "live",
    lockable: true,
    steps: [
      { id: "tipo", selector: tour("mode") },
      { id: "idioma", selector: tour("capture-language") },
      { id: "modelo", selector: tour("template") },
      { id: "fontes", selector: tour("sources") },
    ],
  },
  {
    id: "gravar",
    view: "live",
    steps: [
      { id: "botao", selector: `${tour("record")}[aria-pressed="false"]`, fallback: tour("record") },
      { id: "aviso", selector: tour("consent") },
      { id: "mini", selector: tour("mini") },
      // Some sozinho durante a gravação e enquanto a agenda carrega: o passo é pulado.
      { id: "agenda", selector: tour("upcoming") },
    ],
  },
  {
    id: "conversas",
    view: "library",
    steps: [
      { id: "pastas", selector: tour("folders") },
      { id: "busca", selector: tour("library-search") },
      { id: "varias", selector: tour("library-select") },
      { id: "abrir", selector: tour("library-first"), fallback: ".library-empty" },
    ],
  },
  {
    id: "conversa",
    view: "session",
    session: true,
    steps: [
      { id: "nome", selector: tour("session-head") },
      { id: "player", selector: tour("audio"), fallback: tour("playback") },
      { id: "transcricao", selector: tour("transcript") },
      { id: "perguntar", selector: tour("session-ask") },
      { id: "exportar", selector: tour("export") },
    ],
  },
  {
    id: "abas",
    view: "session",
    session: true,
    steps: [
      { id: "ata", selector: "#side-tab-doc" },
      { id: "anotacoes", selector: "#side-tab-notes" },
      { id: "contexto", selector: "#side-tab-context" },
      { id: "mapa", selector: "#side-tab-mindmap" },
      { id: "memoria", selector: "#side-tab-memory" },
      { id: "vozes", selector: "#side-tab-voices" },
    ],
  },
  {
    id: "tarefas",
    view: "tasks",
    steps: [
      { id: "nova", selector: tour("task-new") },
      { id: "filtros", selector: tour("task-filters") },
      { id: "lista", selector: `.task-groups${tour("task-list")}`, fallback: `.task-empty${tour("task-list")}` },
    ],
  },
  {
    id: "chat",
    view: "chat",
    steps: [
      { id: "contexto", selector: tour("chat-context") },
      { id: "comandos", selector: tour("chat-study") },
      { id: "anexar", selector: tour("chat-attach") },
      { id: "opcoes", selector: tour("chat-tune") },
      { id: "fontes", selector: ".chat-sources", last: true, fallback: tour("chat-study") },
      { id: "historico", selector: tour("chat-rail") },
    ],
  },
  {
    id: "preferencias",
    view: "settings",
    steps: [
      { id: "abas", selector: tour("settings-tabs") },
      { id: "motor", selector: "#settings-tab-transcription" },
      { id: "pessoas", selector: "#settings-tab-people" },
      { id: "reunioes", selector: "#settings-tab-meetings" },
      { id: "templates", selector: "#settings-tab-templates" },
    ],
  },
];

export type ChapterId = (typeof CHAPTERS)[number]["id"];

/** O "?" da tela emenda o capítulo seguinte que mostra a mesma tela. */
export const FOLLOW: Record<string, string> = { preparar: "gravar", conversa: "abas" };

export const chapterIndex = (id: string) => CHAPTERS.findIndex((chapter) => chapter.id === id);

/** Âncora visível do passo; retângulo zerado conta como ausente. */
export function resolveAnchor(step: TourStep): { el: HTMLElement; alt: boolean } | null {
  const pick = (selector: string, last = false) => {
    const all = Array.from(document.querySelectorAll<HTMLElement>(selector)).filter((el) => {
      const rect = el.getBoundingClientRect();
      return rect.width > 0 && rect.height > 0;
    });
    return (last ? all[all.length - 1] : all[0]) ?? null;
  };
  const main = pick(step.selector, step.last);
  if (main) return { el: main, alt: false };
  const other = step.fallback ? pick(step.fallback) : null;
  return other ? { el: other, alt: true } : null;
}

export interface TourProgress {
  chapter: string;
  step: number;
  done: string[];
  finished: boolean;
}

const PROGRESS_KEY = "droidnote.tour.v1";

/** Sem acesso ao storage, o tour funciona e só não retoma. Id que não existe mais volta ao começo. */
export function loadProgress(): TourProgress | null {
  try {
    const raw = window.localStorage.getItem(PROGRESS_KEY);
    if (!raw) return null;
    const data = JSON.parse(raw) as Partial<TourProgress>;
    const index = chapterIndex(String(data.chapter));
    const chapter = CHAPTERS[index];
    return {
      chapter: chapter ? chapter.id : CHAPTERS[0]!.id,
      step: chapter && Number.isInteger(data.step) && data.step! >= 0 && data.step! < chapter.steps.length ? data.step! : 0,
      done: Array.isArray(data.done) ? data.done.filter((id) => chapterIndex(String(id)) >= 0) : [],
      finished: data.finished === true,
    };
  } catch {
    return null;
  }
}

export function saveProgress(progress: TourProgress): void {
  try {
    window.localStorage.setItem(PROGRESS_KEY, JSON.stringify(progress));
  } catch {
    /* modo privado ou storage bloqueado */
  }
}

/** Pedido de tour vindo de qualquer tela; o App escuta. Sem capítulo, abre o seletor. */
export const TOUR_EVENT = "droidnote:tour";

export function requestTour(chapter?: string): void {
  window.dispatchEvent(new CustomEvent(TOUR_EVENT, { detail: chapter ?? null }));
}
