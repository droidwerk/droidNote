import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { useI18n } from "../i18n";

export type ToastTone = "success" | "error" | "info";

export interface ToastAction {
  label: string;
  onClick: () => void;
  /** Ctrl+Z (fora de campo de texto) roda esta ação enquanto o aviso está na tela. */
  undo?: boolean;
}

export interface ToastInput {
  tone?: ToastTone;
  title: string;
  description?: string;
  action?: ToastAction;
  /** Tempo na tela; padrão 5 s. Para enquanto o ponteiro ou o foco estão no aviso. */
  durationMs?: number;
  /** Um aviso novo com a mesma chave substitui o anterior. */
  key?: string;
}

interface ToastItem extends ToastInput {
  id: number;
  tone: ToastTone;
}

interface ToastContextValue {
  push: (toast: ToastInput) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);
const MAX_TOASTS = 3;
const AUTO_DISMISS_MS = 5000;

export function ToastProvider({ children }: { children: ReactNode }) {
  const { t } = useI18n();
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const nextId = useRef(1);
  const timers = useRef(new Map<number, number>());

  const dismiss = useCallback((id: number) => {
    const timer = timers.current.get(id);
    if (timer !== undefined) {
      window.clearTimeout(timer);
      timers.current.delete(id);
    }
    setToasts((current) => current.filter((item) => item.id !== id));
  }, []);

  const schedule = useCallback(
    (toast: ToastItem) => {
      if (toast.tone === "error") return;
      window.clearTimeout(timers.current.get(toast.id));
      timers.current.set(toast.id, window.setTimeout(() => dismiss(toast.id), toast.durationMs ?? AUTO_DISMISS_MS));
    },
    [dismiss],
  );

  const pause = (id: number) => {
    window.clearTimeout(timers.current.get(id));
    timers.current.delete(id);
  };

  const push = useCallback(
    (toast: ToastInput) => {
      const id = nextId.current;
      nextId.current += 1;
      const item: ToastItem = { ...toast, id, tone: toast.tone ?? "info" };
      setToasts((current) => {
        const kept = toast.key ? current.filter((old) => old.key !== toast.key) : current;
        return [...kept, item].slice(-MAX_TOASTS);
      });
      schedule(item);
    },
    [schedule],
  );

  const run = useCallback(
    (toast: ToastItem) => {
      toast.action?.onClick();
      dismiss(toast.id);
    },
    [dismiss],
  );

  // Ctrl+Z desfaz pelo aviso mais recente com "Desfazer"; em campo de texto, o Ctrl+Z é do texto.
  useEffect(() => {
    const undoable = [...toasts].reverse().find((item) => item.action?.undo);
    if (!undoable) return;
    const onKey = (event: KeyboardEvent) => {
      if (!(event.ctrlKey || event.metaKey) || event.shiftKey || event.key.toLowerCase() !== "z") return;
      const target = event.target as HTMLElement | null;
      if (target?.closest("input, textarea, select, [contenteditable='true']")) return;
      event.preventDefault();
      run(undoable);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toasts, run]);

  const value = useMemo(() => ({ push }), [push]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toast-region" aria-live="polite" aria-relevant="additions text">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={`toast toast-${toast.tone}`}
            onMouseEnter={() => pause(toast.id)}
            onMouseLeave={() => schedule(toast)}
            onFocus={() => pause(toast.id)}
            onBlur={(event) => {
              if (!event.currentTarget.contains(event.relatedTarget as Node | null)) schedule(toast);
            }}
          >
            <div className="toast-copy">
              <strong>{toast.title}</strong>
              {toast.description ? <p>{toast.description}</p> : null}
            </div>
            <div className="toast-actions">
              {toast.action ? (
                <button
                  type="button"
                  className="toast-action"
                  onClick={() => run(toast)}
                >
                  {toast.action.label}
                </button>
              ) : null}
              <button
                type="button"
                className="toast-close"
                aria-label={t("common.closeNotice")}
                onClick={() => dismiss(toast.id)}
              >
                <svg viewBox="0 0 16 16" aria-hidden>
                  <path d="M4 4l8 8M12 4l-8 8" />
                </svg>
              </button>
            </div>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error("useToast precisa de ToastProvider");
  }
  return context;
}
