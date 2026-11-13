import { useEffect, useRef, type ReactNode } from "react";

const FOCUSABLE =
  'button, [href], input, select, textarea, summary, [tabindex]:not([tabindex="-1"])';

interface ModalProps {
  onClose: () => void;
  labelledBy: string;
  describedBy?: string;
  className?: string;
  /** Seletor do elemento que recebe o foco ao abrir; sem ele, o primeiro focável. */
  initialFocus?: string;
  children: ReactNode;
}

/** Diálogo modal acessível: overlay, foco preso, Esc fecha e o foco volta para onde estava. */
export function Modal({ onClose, labelledBy, describedBy, className, initialFocus, children }: ModalProps) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    const previouslyFocused = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const focusables = () =>
      Array.from(dialog.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
        (element) => !element.hasAttribute("disabled"),
      );
    const preferred = initialFocus ? dialog.querySelector<HTMLElement>(initialFocus) : null;
    (preferred ?? focusables()[0] ?? dialog).focus();

    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        closeRef.current();
        return;
      }
      if (event.key !== "Tab") return;
      const items = focusables();
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
    // Roda só ao abrir: o foco inicial não deve pular a cada render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div
      className="confirm-overlay"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) closeRef.current();
      }}
    >
      <div
        ref={dialogRef}
        className={className ? `confirm-dialog ${className}` : "confirm-dialog"}
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy}
        aria-describedby={describedBy}
        tabIndex={-1}
      >
        {children}
      </div>
    </div>
  );
}
