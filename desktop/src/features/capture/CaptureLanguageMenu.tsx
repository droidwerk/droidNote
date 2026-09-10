import { useEffect, useRef, useState } from "react";

import {
  CAPTURE_LANGUAGE_IDS,
  UI_LANGUAGES,
  useT,
  type CaptureLanguage,
} from "../../shared/i18n";
import { Button } from "../../shared/ui/primitives";

interface CaptureLanguageMenuProps {
  value: CaptureLanguage;
  disabled?: boolean;
  onChange: (id: CaptureLanguage) => void;
}

export function CaptureLanguageMenu({ value, disabled = false, onChange }: CaptureLanguageMenuProps) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const label = value === "auto" ? t("languages.autoShort") : nativeName(value);
  const hint = disabled ? t("live.captureLanguageLocked") : t("live.captureLanguageHint");

  useEffect(() => {
    if (!open) return;
    const onPointer = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  useEffect(() => {
    if (disabled) setOpen(false);
  }, [disabled]);

  return (
    <div className="export-menu capture-lang-menu" ref={menuRef}>
      <Button
        className="capture-lang-btn"
        disabled={disabled}
        aria-expanded={open}
        aria-haspopup="menu"
        aria-label={t("live.captureLanguageAria")}
        title={hint}
        onClick={() => setOpen((current) => !current)}
      >
        <GlobeGlyph />
        {label}
      </Button>
      {open && !disabled ? (
        <div className="export-menu-list capture-lang-menu-list" role="menu">
          {CAPTURE_LANGUAGE_IDS.map((id) => (
            <button
              key={id}
              type="button"
              role="menuitemradio"
              aria-checked={value === id}
              className={value === id ? "is-selected" : ""}
              onClick={() => {
                onChange(id);
                setOpen(false);
              }}
            >
              {id === "auto" ? t("languages.auto") : nativeName(id)}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function nativeName(id: Exclude<CaptureLanguage, "auto">): string {
  return UI_LANGUAGES.find((item) => item.id === id)?.native ?? id;
}

function GlobeGlyph() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.8" />
      <path
        d="M3.2 12h17.6M12 3c2.8 2.4 4.2 5.6 4.2 9s-1.4 6.6-4.2 9M12 3C9.2 5.4 7.8 8.6 7.8 12s1.4 6.6 4.2 9"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  );
}
