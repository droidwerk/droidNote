import { useEffect, useRef, useState } from "react";

import type { ChatStyle, SolveTarget } from "../../shared/api/types";
import { useT } from "../../shared/i18n";
import { Icon } from "../../shared/ui/Icon";

export const STYLES: ChatStyle[] = ["normal", "fast", "study", "solve"];
export const SOLVE_TARGETS: SolveTarget[] = ["generic", "claude", "codex", "cursor"];

export function readStyle(): ChatStyle {
  try {
    const stored = window.localStorage.getItem("droidnote.chatStyle");
    return STYLES.includes(stored as ChatStyle) ? (stored as ChatStyle) : "normal";
  } catch {
    return "normal";
  }
}

export function readSolveTarget(): SolveTarget {
  try {
    const stored = window.localStorage.getItem("droidnote.chatSolveTarget");
    return SOLVE_TARGETS.includes(stored as SolveTarget) ? (stored as SolveTarget) : "generic";
  } catch {
    return "generic";
  }
}

interface ChatTuneProps {
  style: ChatStyle;
  grounded: boolean;
  solveTarget: SolveTarget;
  disabled?: boolean;
  onStyle: (style: ChatStyle) => void;
  onGrounded: (value: boolean) => void;
  onSolveTarget: (value: SolveTarget) => void;
}

/** Engrenagem no campo de pergunta: modo da resposta e "só fontes". Onde procurar é a barra de contexto. */
export function ChatTune({
  style,
  grounded,
  solveTarget,
  disabled = false,
  onStyle,
  onGrounded,
  onSolveTarget,
}: ChatTuneProps) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return undefined;
    const close = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const changed = style !== "normal" || grounded;
  const summary = [
    style !== "normal" ? t(`chat.mode_${style}`) : "",
    grounded ? t("chat.groundedShort") : "",
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <div data-tour="chat-tune" className="chat-tune" ref={ref}>
      <button
        type="button"
        className={changed ? "chat-tune-btn is-on" : "chat-tune-btn"}
        disabled={disabled}
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-label={t("chat.tune")}
        title={summary ? `${t("chat.tune")}: ${summary}` : t("chat.tune")}
        onClick={() => setOpen((value) => !value)}
      >
        <Icon name="gear" size={16} />
        {changed ? <i className="chat-tune-dot" aria-hidden /> : null}
      </button>
      {open ? (
        <div className="chat-tune-pop" role="dialog" aria-label={t("chat.tune")}>
          <div className="field">
            <span>{t("chat.modeLabel")}</span>
            <div className="chat-modes" role="radiogroup" aria-label={t("chat.modeLabel")}>
              {STYLES.map((item) => (
                <button
                  key={item}
                  type="button"
                  role="radio"
                  aria-checked={style === item}
                  className={style === item ? "chat-mode is-on" : "chat-mode"}
                  onClick={() => onStyle(item)}
                >
                  <strong>{t(`chat.mode_${item}`)}</strong>
                  <small>{t(`chat.modeHint_${item}`)}</small>
                </button>
              ))}
            </div>
          </div>
          {style === "solve" ? (
            <label className="field">
              <span>{t("chat.solveTarget")}</span>
              <select value={solveTarget} onChange={(event) => onSolveTarget(event.target.value as SolveTarget)}>
                {SOLVE_TARGETS.map((item) => (
                  <option key={item} value={item}>
                    {t(`chat.solveTarget_${item}`)}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          <label className="check-control chat-tune-check">
            <input type="checkbox" checked={grounded} onChange={(event) => onGrounded(event.target.checked)} />
            <span className="check-box" />
            <span>{t("chat.grounded")}</span>
          </label>
        </div>
      ) : null}
    </div>
  );
}
