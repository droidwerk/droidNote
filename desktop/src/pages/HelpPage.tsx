import { Fragment } from "react";

import { useT } from "../shared/i18n";
import { openExternal } from "../shared/lib/openExternal";
import { ISSUES_PAGE } from "../shared/lib/whatsNew";
import { KeySeal } from "../shared/ui/KeySeal";
import { Button } from "../shared/ui/primitives";
import { CHAPTERS, requestTour } from "../features/onboarding/tourScript";

const SECTIONS = ["start", "record", "minutes", "ask", "memory", "voices", "folders", "engines", "privacy", "shortcuts"] as const;
const FAQ = ["winWarning", "dataWhere", "internet", "openaiCost", "consent", "uninstall", "update"] as const;
/** Atalhos lidos do código: App.tsx (Ctrl K, Ctrl Shift R, Ctrl B), TranscriptList (1-9, Alt, L, F, Ctrl Enter), ChatPage (Enter). */
const SHORTCUTS: [string, string][] = [
  ["Ctrl K", "palette"],
  ["Ctrl Shift R", "record"],
  ["Ctrl B", "sidebar"],
  ["Esc", "close"],
  ["Enter · Shift Enter", "send"],
  ["1 … 9", "speaker"],
  ["Alt 1 … 9", "speakerOne"],
  ["L · F", "repeat"],
  ["Ctrl Enter", "saveEdit"],
];

/** "Ctrl Shift R" vira uma tecla por <kbd>; "Enter · Shift Enter" mantém as alternativas. */
function Keys({ combo }: { combo: string }) {
  return (
    <>
      {combo.split(" · ").map((alt, i) => (
        <Fragment key={alt}>
          {i ? <span className="help-keys-or"> · </span> : null}
          {alt.split(" ").map((key, j) => (
            <Fragment key={`${key}-${j}`}>
              {j ? " " : null}
              {key === "…" ? key : <kbd>{key}</kbd>}
            </Fragment>
          ))}
        </Fragment>
      ))}
    </>
  );
}

function Paragraphs({ text }: { text: string }) {
  return (
    <>
      {text.split("\n").map((line) => (
        <p key={line}>{line}</p>
      ))}
    </>
  );
}

/** Capítulos do tour, logo depois de Primeiros passos. A linha de baixo lista os passos. */
function TourSection() {
  const t = useT();
  return (
    <section id="help-tour" className="help-section" aria-labelledby="help-tour-h">
      <h2 id="help-tour-h">{t("help.tourSection")}</h2>
      <ol className="help-tour-list">
        {CHAPTERS.map((chapter) => {
          const title = t(`tour.ch.${chapter.id}.title`);
          return (
            <li key={chapter.id}>
              <div className="help-tour-head">
                <strong>{title}</strong>
                <Button size="sm" aria-label={t("help.tourSeeAria", { title })} onClick={() => requestTour(chapter.id)}>
                  {t("help.tourSee")}
                </Button>
              </div>
              <span className="muted">
                {t("tour.steps", { count: chapter.steps.length })}
                {": "}
                {chapter.steps.map((step) => t(`tour.ch.${chapter.id}.${step.id}.title`)).join(", ")}
              </span>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

export function HelpPage() {
  const t = useT();
  return (
    <div className="page help-page">
      <header className="page-head">
        <div className="page-head-copy">
          <span className="eyebrow">{t("help.eyebrow")}</span>
          <h1>{t("help.title")}</h1>
          <p className="muted">{t("help.summary")}</p>
        </div>
        <div className="page-actions">
          <Button onClick={() => requestTour()}>{t("help.tour")}</Button>
          <Button onClick={() => void openExternal(ISSUES_PAGE)}>{t("help.report")}</Button>
          <p className="help-report muted">{t("help.reportHint")}</p>
        </div>
      </header>

      <nav className="help-toc" aria-label={t("help.tocLabel")}>
        {SECTIONS.map((id) => (
          <Fragment key={id}>
            <a href={`#help-${id}`}>{t(`help.s.${id}.title`)}</a>
            {id === "start" ? <a href="#help-tour">{t("help.tourSection")}</a> : null}
          </Fragment>
        ))}
        <a href="#help-faq">{t("help.faqTitle")}</a>
      </nav>

      {SECTIONS.map((id) => (
        <Fragment key={id}>
        <section id={`help-${id}`} className="help-section" aria-labelledby={`help-${id}-h`}>
          <h2 id={`help-${id}-h`}>{t(`help.s.${id}.title`)}</h2>
          {id === "shortcuts" ? (
            <dl className="help-keys">
              {SHORTCUTS.map(([keys, label]) => (
                <div key={label}>
                  <dt>
                    <Keys combo={keys} />
                  </dt>
                  <dd>{t(`help.keys.${label}`)}</dd>
                </div>
              ))}
            </dl>
          ) : (
            <Paragraphs text={t(`help.s.${id}.body`)} />
          )}
          {id === "privacy" ? <KeySeal /> : null}
        </section>
        {id === "start" ? <TourSection /> : null}
        </Fragment>
      ))}

      <section id="help-faq" className="help-section" aria-labelledby="help-faq-h">
        <h2 id="help-faq-h">{t("help.faqTitle")}</h2>
        {FAQ.map((id) => (
          <details key={id} className="help-faq">
            <summary>{t(`help.faq.${id}.q`)}</summary>
            <Paragraphs text={t(`help.faq.${id}.a`)} />
          </details>
        ))}
      </section>
    </div>
  );
}
