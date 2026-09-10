import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { useT } from "../i18n";
import { Button } from "./primitives";

export type ConfirmTone = "danger" | "default";

export interface ConfirmOptions {
  title: string;
  description?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  tone?: ConfirmTone;
}

interface ConfirmRequest extends ConfirmOptions {
  resolve: (value: boolean) => void;
}

interface ConfirmContextValue {
  confirm: (options: ConfirmOptions) => Promise<boolean>;
}

const ConfirmContext = createContext<ConfirmContextValue | null>(null);
const FOCUSABLE =
  'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';

export function ConfirmProvider({ children }: { children: ReactNode }) {
  const t = useT();
  const [request, setRequest] = useState<ConfirmRequest | null>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const descriptionId = useId();

  const confirm = useCallback((options: ConfirmOptions) => {
    return new Promise<boolean>((resolve) => {
      setRequest({ ...options, resolve });
    });
  }, []);

  const settle = useCallback((value: boolean) => {
    setRequest((current) => {
      current?.resolve(value);
      return null;
    });
  }, []);

  useEffect(() => {
    if (!request) return;
    const dialog = dialogRef.current;
    if (!dialog) return;
    const previouslyFocused = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const focusables = () =>
      Array.from(dialog.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
        (element) => !element.hasAttribute("disabled"),
      );
    const cancel = dialog.querySelector<HTMLElement>(".confirm-actions .button-ghost");
    (cancel ?? focusables()[0])?.focus();

    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        settle(false);
        return;
      }
      if (event.key !== "Tab") return;
      const items = focusables();
      if (items.length === 0) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (!first || !last) return;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      previouslyFocused?.focus();
    };
  }, [request, settle]);

  const value = useMemo(() => ({ confirm }), [confirm]);
  const tone = request?.tone ?? "default";

  return (
    <ConfirmContext.Provider value={value}>
      {children}
      {request ? (
        <div className="confirm-overlay" onMouseDown={(event) => {
          if (event.target === event.currentTarget) settle(false);
        }}>
          <div
            ref={dialogRef}
            className={`confirm-dialog confirm-${tone}`}
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
            aria-describedby={request.description ? descriptionId : undefined}
          >
            <div className="confirm-copy">
              <h2 id={titleId}>{request.title}</h2>
              {request.description ? <p id={descriptionId}>{request.description}</p> : null}
            </div>
            <div className="confirm-actions">
              <Button onClick={() => settle(false)}>
                {request.cancelLabel ?? t("common.cancel")}
              </Button>
              <Button
                variant={tone === "danger" ? "danger" : "primary"}
                onClick={() => settle(true)}
              >
                {request.confirmLabel ?? t("common.ok")}
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </ConfirmContext.Provider>
  );
}

export function useConfirm(): (options: ConfirmOptions) => Promise<boolean> {
  const context = useContext(ConfirmContext);
  if (!context) {
    throw new Error("useConfirm precisa de ConfirmProvider");
  }
  return context.confirm;
}
