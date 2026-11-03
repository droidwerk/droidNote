import { useEffect, useRef, useState } from "react";

import { api } from "../../shared/api/client";
import type { ChatScope, ChatStyle, Person, SolveTarget, Tag } from "../../shared/api/types";
import { useT } from "../../shared/i18n";
import { Icon } from "../../shared/ui/Icon";

/** Escopo escolhido na tela; vira `ChatScope` na hora de enviar. */
export type ScopeKind = "auto" | "session" | "7" | "30" | "person" | "tag";

export interface ScopeChoice {
  kind: ScopeKind;
  personId?: string;
  tagId?: string;
}

export const STYLES: ChatStyle[] = ["normal", "fast", "study", "solve"];
export const SOLVE_TARGETS: SolveTarget[] = ["generic", "claude", "codex", "cursor"];

export function scopePayload(choice: ScopeChoice, focusSessionId: string | null): ChatScope | null {
  if (choice.kind === "session") return focusSessionId ? { session_ids: [focusSessionId] } : null;
  if (choice.kind === "7") return { days: 7 };
  if (choice.kind === "30") return { days: 30 };
  if (choice.kind === "person") return choice.personId ? { person_id: choice.personId } : null;
  if (choice.kind === "tag") return choice.tagId ? { tag_id: choice.tagId } : null;
  return null;
}

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
  scope: ScopeChoice;
  grounded: boolean;
  solveTarget: SolveTarget;
  hasFocus: boolean;
  disabled?: boolean;
  onStyle: (style: ChatStyle) => void;
  onScope: (scope: ScopeChoice) => void;
  onGrounded: (value: boolean) => void;
  onSolveTarget: (value: SolveTarget) => void;
}

/** Engrenagem no campo de pergunta: modo da resposta, fontes e onde procurar. */
export function ChatTune({
  style,
  scope,
  grounded,
  solveTarget,
  hasFocus,
  disabled = false,
  onStyle,
  onScope,
  onGrounded,
  onSolveTarget,
}: ChatTuneProps) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const [people, setPeople] = useState<Person[]>([]);
  const [tags, setTags] = useState<Tag[]>([]);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return undefined;
    void api.people().then(setPeople).catch(() => setPeople([]));
    void api.tags().then(setTags).catch(() => setTags([]));
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

  const scopeActive = scope.kind !== "auto" && !(scope.kind === "session" && !hasFocus);
  const changed = style !== "normal" || grounded || scopeActive;
  const summary = [
    style !== "normal" ? t(`chat.mode_${style}`) : "",
    grounded ? t("chat.groundedShort") : "",
    scopeActive ? t(`chat.scope_${scope.kind}`) : "",
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <div className="chat-tune" ref={ref}>
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
          <label className="field">
            <span>{t("chat.scopeLabel")}</span>
            <select value={scope.kind} onChange={(event) => onScope({ kind: event.target.value as ScopeKind })}>
              <option value="auto">{t("chat.scope_auto")}</option>
              {hasFocus ? <option value="session">{t("chat.scope_session")}</option> : null}
              <option value="7">{t("chat.scope_7")}</option>
              <option value="30">{t("chat.scope_30")}</option>
              {people.length ? <option value="person">{t("chat.scope_person")}</option> : null}
              {tags.length ? <option value="tag">{t("chat.scope_tag")}</option> : null}
            </select>
          </label>
          {scope.kind === "person" ? (
            <label className="field">
              <span>{t("chat.scopeWho")}</span>
              <select value={scope.personId ?? ""} onChange={(event) => onScope({ kind: "person", personId: event.target.value || undefined })}>
                <option value="">—</option>
                {people.map((person) => (
                  <option key={person.id} value={person.id}>
                    {person.name}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          {scope.kind === "tag" ? (
            <label className="field">
              <span>{t("chat.scopeWhich")}</span>
              <select value={scope.tagId ?? ""} onChange={(event) => onScope({ kind: "tag", tagId: event.target.value || undefined })}>
                <option value="">—</option>
                {tags.map((tag) => (
                  <option key={tag.id} value={tag.id}>
                    {tag.name}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
