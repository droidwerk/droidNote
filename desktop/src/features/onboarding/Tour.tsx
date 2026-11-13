import { useEffect, useId, useRef, useState, type CSSProperties, type KeyboardEvent as ReactKeyboardEvent, type ReactNode } from "react";

import { useI18n } from "../../shared/i18n";
import { Icon } from "../../shared/ui/Icon";
import { Button } from "../../shared/ui/primitives";
import { CHAPTERS, FOLLOW, chapterIndex, loadProgress, requestTour, resolveAnchor, saveProgress, type TourView } from "./tourScript";

/** Botão "?" do cabeçalho: roda só o capítulo daquela tela. */
export function TourButton({ chapter }: { chapter: string }) {
  const { t } = useI18n();
  const label = t("tour.pageButton");
  return (
    <button type="button" className="tool-btn is-icon" onClick={() => requestTour(chapter)} title={label} aria-label={label}>
      <Icon name="help" size={15} />
    </button>
  );
}

export type TourStart = { kind: "picker" } | { kind: "chapter"; chapter: string };

type Phase = "picker" | "run" | "paused" | "noSession" | "nothing" | "end";

const ALL = CHAPTERS.map((_, index) => index);
const POP_MAX = 340;
const NARROW = 640;
const modalOpen = () => document.querySelector('[aria-modal="true"]') !== null;

function chain(id: string): number[] {
  const index = Math.max(0, chapterIndex(id));
  const follow = FOLLOW[CHAPTERS[index]!.id];
  return follow ? [index, chapterIndex(follow)] : [index];
}

/**
 * Tour em capítulos: um balão ancorado por vez, sem fundo escuro e sem bloquear cliques.
 * Só troca de tela e abre a conversa mais recente; nunca clica, grava, troca aba ou muda preferência.
 */
export function Tour({
  start,
  view,
  recording,
  hasSession,
  onNavigate,
  onOpenSession,
  onEnd,
}: {
  start: TourStart;
  view: string;
  recording: boolean;
  hasSession: boolean;
  onNavigate: (view: TourView | "help") => void;
  /** Usa a conversa aberta ou abre a mais recente; false quando não há nenhuma. */
  onOpenSession: () => boolean;
  onEnd: () => void;
}) {
  const { t } = useI18n();
  const titleId = useId();
  const bodyId = useId();
  const [saved] = useState(loadProgress);
  const single = start.kind === "chapter";
  const [phase, setPhase] = useState<Phase>(single ? "run" : "picker");
  const [order, setOrder] = useState<number[]>(() => (start.kind === "chapter" ? chain(start.chapter) : ALL));
  const [pos, setPos] = useState({ index: 0, step: 0 });
  const [done, setDone] = useState<string[]>(saved?.done ?? []);
  const [placed, setPlaced] = useState<{ top: number; left: number; width: number; alt: boolean } | null>(null);
  const [hidden, setHidden] = useState(false);
  const popRef = useRef<HTMLDivElement>(null);
  const primaryRef = useRef<HTMLButtonElement>(null);
  const dir = useRef<1 | -1>(1);
  const shownInChapter = useRef(0);
  const viewRef = useRef(view);
  viewRef.current = view;

  const chapter = CHAPTERS[order[pos.index] ?? 0]!;
  const step = chapter.steps[pos.step];
  const lastStep = pos.step === chapter.steps.length - 1;
  const moreChapters = pos.index + 1 < order.length;

  // Ao sair, o foco volta para onde estava quando o tour começou.
  useEffect(() => {
    const before = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    return () => {
      if (before?.isConnected) before.focus();
    };
  }, []);

  // Grava a posição a cada passo; "Sair" e Esc só fecham, a posição já está salva.
  useEffect(() => {
    if (phase === "end") saveProgress({ chapter: CHAPTERS[0]!.id, step: 0, done, finished: true });
    else if (phase !== "picker") saveProgress({ chapter: chapter.id, step: pos.step, done, finished: false });
  }, [phase, chapter.id, pos.step, done]);

  const goChapter = (markDone: boolean) => {
    const nextDone = markDone && !done.includes(chapter.id) ? [...done, chapter.id] : done;
    setDone(nextDone);
    dir.current = 1;
    shownInChapter.current = 0;
    if (moreChapters) {
      setPos({ index: pos.index + 1, step: 0 });
      setPhase("run");
    } else if (single) {
      saveProgress({ chapter: chapter.id, step: pos.step, done: nextDone, finished: false });
      onEnd();
    } else {
      setPhase("end");
    }
  };
  const next = () => {
    dir.current = 1;
    if (!lastStep) setPos({ ...pos, step: pos.step + 1 });
    else goChapter(true);
  };
  const back = () => {
    dir.current = -1;
    if (pos.step > 0) setPos({ ...pos, step: pos.step - 1 });
    else if (pos.index > 0) {
      shownInChapter.current = 1;
      setPos({ index: pos.index - 1, step: CHAPTERS[order[pos.index - 1]!]!.steps.length - 1 });
    } else next();
  };
  // Passo sem âncora: segue no sentido em que a pessoa andava.
  const skip = () => {
    if (dir.current === -1) back();
    else if (lastStep && shownInChapter.current === 0) setPhase("nothing");
    else next();
  };
  const skipRef = useRef(skip);
  skipRef.current = skip;
  const navRef = useRef({ onNavigate, onOpenSession });
  navRef.current = { onNavigate, onOpenSession };

  useEffect(() => {
    if (phase !== "run" || !step) return undefined;
    let navigated = false;
    if (chapter.session) {
      navigated = viewRef.current !== "session";
      if (!navRef.current.onOpenSession()) {
        setPhase("noSession");
        return undefined;
      }
    } else if (chapter.view && viewRef.current !== chapter.view) {
      navigated = true;
      navRef.current.onNavigate(chapter.view);
    }
    // A tela acabou de trocar: espera a âncora aparecer (mais tempo quando a tela carrega dados).
    const wait = navigated ? 3000 : 600;
    let startedAt = performance.now();
    let anchor: HTMLElement | null = null;
    let stopped = false;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const place = (el: HTMLElement, alt: boolean) => {
      const rect = el.getBoundingClientRect();
      const vw = window.innerWidth;
      const vh = window.innerHeight;
      const width = Math.min(POP_MAX, vw - 24);
      const height = popRef.current?.offsetHeight ?? 170;
      let top: number;
      let left: number;
      if (vw >= NARROW && rect.left < vw / 3 && rect.right + width + 24 < vw) {
        top = Math.max(12, Math.min(rect.top, vh - height - 12));
        left = rect.right + 12;
      } else {
        left = Math.min(Math.max(12, rect.left), vw - width - 12);
        const below = rect.bottom + 10 + height + 12 < vh;
        top = below ? rect.bottom + 10 : Math.max(12, rect.top - height - 10);
      }
      setPlaced((prev) =>
        prev && prev.top === top && prev.left === left && prev.width === width && prev.alt === alt ? prev : { top, left, width, alt },
      );
    };

    const tick = () => {
      if (stopped) return;
      if (modalOpen()) {
        // Boas-vindas, confirmação ou paleta abertas: o balão espera.
        startedAt = performance.now();
        setHidden(true);
        return;
      }
      setHidden(false);
      const found = resolveAnchor(step);
      if (!found) {
        if (anchor) {
          // A pessoa saiu da tela do passo: pausa, sem arrastar de volta.
          stopped = true;
          setPhase("paused");
        } else if (performance.now() - startedAt > wait) {
          stopped = true;
          skipRef.current();
        }
        return;
      }
      if (found.el !== anchor) {
        const first = anchor === null;
        anchor?.classList.remove("tour-target");
        anchor = found.el;
        anchor.classList.add("tour-target");
        if (first) {
          shownInChapter.current += 1;
          anchor.scrollIntoView({ block: "nearest", behavior: reduced ? "auto" : "smooth" });
        }
      }
      place(anchor, found.alt);
    };

    tick();
    const timer = window.setInterval(tick, 150);
    window.addEventListener("resize", tick);
    window.addEventListener("scroll", tick, true);
    return () => {
      stopped = true;
      window.clearInterval(timer);
      window.removeEventListener("resize", tick);
      window.removeEventListener("scroll", tick, true);
      anchor?.classList.remove("tour-target");
      setPlaced(null);
    };
    // Roda a cada passo; a troca de tela feita pela pessoa é tratada dentro do tick.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase, pos, order]);

  // Foco no botão primário a cada passo mostrado e a cada cartão (a pílula de pausa não rouba foco).
  const shownKey = phase === "run" ? (placed ? `${pos.index}.${pos.step}` : null) : phase;
  useEffect(() => {
    if (shownKey && phase !== "paused") primaryRef.current?.focus({ preventScroll: true });
  }, [shownKey, phase]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !modalOpen()) onEnd();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onEnd]);

  const runFrom = (index: number, stepIndex = 0) => {
    dir.current = 1;
    shownInChapter.current = stepIndex > 0 ? 1 : 0;
    setOrder(ALL);
    setPos({ index, step: stepIndex });
    setPhase("run");
  };

  const dialog = (className: string, body: ReactNode, style?: CSSProperties) => (
    <div
      ref={popRef}
      className={`tour-pop ${className}`.trim()}
      role="dialog"
      aria-modal="false"
      aria-labelledby={titleId}
      aria-describedby={bodyId}
      style={style}
    >
      {body}
    </div>
  );
  const primary = (label: string, onClick: () => void) => (
    <button ref={primaryRef} type="button" className="button button-primary button-sm" onClick={onClick}>
      {label}
    </button>
  );

  if (phase === "picker") {
    const resume = saved && !saved.finished ? saved : null;
    const onListKey = (event: ReactKeyboardEvent<HTMLOListElement>) => {
      if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
      event.preventDefault();
      const items = Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>("button"));
      const at = items.indexOf(document.activeElement as HTMLButtonElement);
      items[(at + (event.key === "ArrowDown" ? 1 : -1) + items.length) % items.length]?.focus();
    };
    return dialog(
      "tour-picker is-corner",
      <>
        <div className="tour-head">
          <strong id={titleId}>{t("tour.pickerTitle")}</strong>
          <button type="button" className="tour-x" onClick={onEnd} aria-label={t("tour.close")} title={t("tour.close")}>
            <Icon name="close" size={14} />
          </button>
        </div>
        <p id={bodyId}>{t("tour.pickerBody")}</p>
        <ol className="tour-chapters" onKeyDown={onListKey}>
          {CHAPTERS.map((item, index) => {
            const here = resume?.chapter === item.id;
            const aux = here
              ? t("tour.stoppedAt", { step: resume!.step + 1, steps: item.steps.length })
              : item.session && !hasSession
                ? t("tour.needsSession")
                : t("tour.steps", { count: item.steps.length });
            return (
              <li key={item.id}>
                <button type="button" className={here ? "tour-chapter is-here" : "tour-chapter"} onClick={() => runFrom(index)}>
                  <span className="tour-chapter-mark" aria-hidden>
                    {saved?.finished || done.includes(item.id) ? <Icon name="check" size={13} /> : index + 1}
                  </span>
                  <span className="tour-chapter-name">{t(`tour.ch.${item.id}.title`)}</span>
                  <span className="tour-chapter-aux">{aux}</span>
                </button>
              </li>
            );
          })}
        </ol>
        <div className="tour-actions">
          {resume ? (
            <>
              <Button size="sm" onClick={() => runFrom(0)}>
                {t("tour.fromStart")}
              </Button>
              {primary(t("tour.resume"), () => runFrom(Math.max(0, chapterIndex(resume.chapter)), resume.step))}
            </>
          ) : (
            primary(t("tour.fromStart"), () => runFrom(0))
          )}
        </div>
      </>,
    );
  }

  if (phase === "paused") {
    return dialog(
      "tour-pill is-corner",
      <>
        <strong id={titleId}>{t("tour.paused")}</strong>
        <span id={bodyId} className="tour-pill-chapter">
          {t(`tour.ch.${chapter.id}.title`)}
        </span>
        <Button size="sm" variant="quiet" onClick={onEnd}>
          {t("tour.exit")}
        </Button>
        {primary(t("tour.continue"), () => setPhase("run"))}
      </>,
    );
  }

  if (phase === "noSession" || phase === "nothing") {
    const noSession = phase === "noSession";
    return dialog(
      "is-center",
      <>
        <span className="eyebrow">{t(`tour.ch.${chapter.id}.title`)}</span>
        <strong id={titleId}>{t(noSession ? "tour.noSessionTitle" : "tour.nothingTitle")}</strong>
        {noSession ? <p id={bodyId}>{t("tour.noSessionBody")}</p> : null}
        <div className="tour-actions">
          {noSession ? (
            <Button
              size="sm"
              onClick={() => {
                onNavigate("live");
                setPhase("paused");
              }}
            >
              {t("tour.goLive")}
            </Button>
          ) : null}
          {primary(moreChapters || !single ? t("tour.skipChapter") : t("tour.close"), () => goChapter(false))}
        </div>
      </>,
    );
  }

  if (phase === "end") {
    return dialog(
      "is-corner",
      <>
        <strong id={titleId}>{t("tour.endTitle")}</strong>
        <p id={bodyId}>{t("tour.endBody")}</p>
        <div className="tour-actions">
          <Button
            size="sm"
            onClick={() => {
              onNavigate("help");
              onEnd();
            }}
          >
            {t("tour.openHelp")}
          </Button>
          {primary(t("tour.close"), onEnd)}
        </div>
      </>,
    );
  }

  if (!step) return null;
  const progress = single
    ? t("tour.progressSingle", { step: pos.step + 1, steps: chapter.steps.length })
    : t("tour.progress", { chapter: (order[pos.index] ?? 0) + 1, chapters: CHAPTERS.length, step: pos.step + 1, steps: chapter.steps.length });
  const key = `tour.ch.${chapter.id}.${step.id}`;
  const text = t(`${key}.${placed?.alt ? "alt" : "body"}`);
  // No passo alternativo o alvo é outro (ex.: a faixa no lugar do player): o título pode mudar junto.
  const altTitle = placed?.alt ? t(`${key}.altTitle`) : "";
  const title = altTitle && altTitle !== `${key}.altTitle` ? altTitle : t(`${key}.title`);
  // Renderiza invisível antes de posicionar, para medir a altura real do balão.
  return dialog(
    "",
    <>
      <div className="tour-copy" aria-live="polite">
        <span className="tour-count">{progress}</span>
        <span className="eyebrow">{t(`tour.ch.${chapter.id}.title`)}</span>
        <strong id={titleId}>{title}</strong>
        <p id={bodyId}>{chapter.lockable && recording ? `${t("tour.lockedNote")} ${text}` : text}</p>
      </div>
      <div className="tour-actions">
        <Button size="sm" variant="quiet" onClick={onEnd}>
          {t("tour.exit")}
        </Button>
        {moreChapters || !single ? (
          <Button size="sm" variant="quiet" onClick={() => goChapter(false)}>
            {t("tour.skipChapter")}
          </Button>
        ) : null}
        <span className="tour-spacer" />
        <Button size="sm" disabled={pos.index === 0 && pos.step === 0} onClick={back}>
          {t("tour.back")}
        </Button>
        {primary(!lastStep ? t("tour.next") : moreChapters ? t("tour.nextChapter") : t("tour.done"), next)}
      </div>
    </>,
    placed && !hidden
      ? { top: placed.top, left: placed.left, width: placed.width }
      : { top: 0, left: 0, width: Math.min(POP_MAX, window.innerWidth - 24), visibility: "hidden" },
  );
}
