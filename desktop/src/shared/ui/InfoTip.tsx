import { useId, useState, type ReactNode } from "react";

interface InfoTipProps {
  /** A explicação que antes ocupava a tela; aparece ao passar o mouse ou focar. */
  text: ReactNode;
  /** Lado preferido do balão. */
  side?: "top" | "bottom";
  align?: "start" | "center" | "end";
  label?: string;
}

/** Ícone ⓘ com a explicação num balão: a tela mostra o essencial, o resto fica a um gesto. */
export function InfoTip({ text, side = "bottom", align = "start", label }: InfoTipProps) {
  const id = useId();
  const [open, setOpen] = useState(false);
  return (
    <span
      className={`info-tip is-${side} is-${align}${open ? " is-open" : ""}`}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <button
        type="button"
        className="info-tip-button"
        aria-label={label ?? (typeof text === "string" ? text : undefined)}
        aria-describedby={open ? id : undefined}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onClick={(event) => {
          // Dentro de <label> (caixas de seleção): mostrar a dica não pode marcar a opção.
          event.preventDefault();
          event.stopPropagation();
          setOpen((value) => !value);
        }}
        onKeyDown={(event) => {
          if (event.key === "Escape") setOpen(false);
        }}
      >
        <svg viewBox="0 0 16 16" width="13" height="13" aria-hidden>
          <circle cx="8" cy="8" r="6.6" fill="none" stroke="currentColor" strokeWidth="1.3" />
          <path d="M8 7.2v4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
          <circle cx="8" cy="4.9" r="0.85" fill="currentColor" />
        </svg>
      </button>
      {open ? (
        <span role="tooltip" id={id} className="info-tip-bubble">
          {text}
        </span>
      ) : null}
    </span>
  );
}
