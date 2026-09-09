import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { createPortal } from "react-dom";

import type { ModelOption } from "../api/types";

interface ModelSelectProps {
  label: string;
  value: string;
  options: ModelOption[];
  onChange: (id: string) => void;
}

export function modelMeta(detail?: string): string {
  if (!detail) return "";
  return detail
    .replace(/\bneste PC\b/gi, "")
    .replace(/\bnão instalado\b/gi, "")
    .replace(/\bBaixa na primeira geração de nota\b/gi, "")
    .replace(/[·•]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

export function StatusGlyph({ installed }: { installed: boolean }) {
  if (installed) {
    return (
      <svg className="status-glyph is-ready" viewBox="0 0 16 16" aria-hidden>
        <path
          d="M3.2 8.4 6.1 11.2 12.8 4.4"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    );
  }
  return (
    <svg className="status-glyph is-missing" viewBox="0 0 16 16" aria-hidden>
      <path
        d="M8 2.5v8.2M4.6 8.1 8 11.5l3.4-3.4M3.2 13.5h9.6"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function ModelSelect({ label, value, options, onChange }: ModelSelectProps) {
  const listId = useId();
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [menuBox, setMenuBox] = useState({ top: 0, left: 0, width: 0, maxHeight: 280 });
  const selected = options.find((item) => item.id === value) ?? options[0];
  const activeIndex = useMemo(
    () => Math.max(0, options.findIndex((item) => item.id === value)),
    [options, value],
  );
  const [highlight, setHighlight] = useState(activeIndex);

  const placeMenu = () => {
    const trigger = triggerRef.current;
    if (!trigger) return;
    const rect = trigger.getBoundingClientRect();
    const gap = 4;
    const maxHeight = 280;
    const spaceBelow = window.innerHeight - rect.bottom - 12;
    const openUp = spaceBelow < 160 && rect.top > spaceBelow;
    const height = Math.min(maxHeight, openUp ? rect.top - 12 : spaceBelow);
    setMenuBox({
      top: openUp ? rect.top - gap - height : rect.bottom + gap,
      left: rect.left,
      width: rect.width,
      maxHeight: height,
    });
  };

  useEffect(() => {
    if (!open) return undefined;
    setHighlight(activeIndex);
    placeMenu();
    const onDoc = (event: MouseEvent) => {
      const target = event.target as Node;
      if (triggerRef.current?.contains(target) || menuRef.current?.contains(target)) return;
      setOpen(false);
    };
    const onReposition = () => placeMenu();
    const frame = window.requestAnimationFrame(() => menuRef.current?.focus());
    document.addEventListener("mousedown", onDoc);
    window.addEventListener("resize", onReposition);
    window.addEventListener("scroll", onReposition, true);
    return () => {
      window.cancelAnimationFrame(frame);
      document.removeEventListener("mousedown", onDoc);
      window.removeEventListener("resize", onReposition);
      window.removeEventListener("scroll", onReposition, true);
    };
  }, [open, activeIndex]);

  useEffect(() => {
    if (!open) return;
    const active = menuRef.current?.querySelector(".is-active");
    if (active instanceof HTMLElement) active.scrollIntoView({ block: "nearest" });
  }, [highlight, open]);

  const choose = (id: string) => {
    onChange(id);
    setOpen(false);
    triggerRef.current?.focus();
  };

  const onTriggerKey = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (event.key === "ArrowDown" || event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      setOpen(true);
    }
  };

  const onMenuKey = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      setOpen(false);
      triggerRef.current?.focus();
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setHighlight((index) => Math.min(options.length - 1, index + 1));
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      setHighlight((index) => Math.max(0, index - 1));
      return;
    }
    if (event.key === "Home") {
      event.preventDefault();
      setHighlight(0);
      return;
    }
    if (event.key === "End") {
      event.preventDefault();
      setHighlight(options.length - 1);
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      const item = options[highlight];
      if (item) choose(item.id);
    }
  };

  const meta = selected ? modelMeta(selected.detail) : "";

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        className={open ? "model-select-trigger is-open" : "model-select-trigger"}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        aria-label={label}
        onClick={() => setOpen((current) => !current)}
        onKeyDown={onTriggerKey}
      >
        {selected ? (
          <ModelRow item={selected} meta={meta} />
        ) : (
          <span className="model-select-empty">Escolher modelo</span>
        )}
        <svg className="model-select-caret" viewBox="0 0 12 8" aria-hidden>
          <path
            d="M1.2 1.4 6 6.2 10.8 1.4"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </button>
      {open
        ? createPortal(
            <div
              ref={menuRef}
              id={listId}
              className="model-select-menu"
              role="listbox"
              aria-label={label}
              tabIndex={-1}
              style={{
                top: menuBox.top,
                left: menuBox.left,
                width: menuBox.width,
                maxHeight: menuBox.maxHeight,
              }}
              onKeyDown={onMenuKey}
            >
              {options.map((item, index) => (
                <div
                  key={item.id}
                  role="option"
                  aria-selected={item.id === value}
                  className={[
                    "model-select-option",
                    item.id === value ? "is-selected" : "",
                    index === highlight ? "is-active" : "",
                  ]
                    .filter(Boolean)
                    .join(" ")}
                  onMouseEnter={() => setHighlight(index)}
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => choose(item.id)}
                >
                  <ModelRow item={item} meta={modelMeta(item.detail)} />
                </div>
              ))}
            </div>,
            document.body,
          )
        : null}
    </>
  );
}

function ModelRow({ item, meta }: { item: ModelOption; meta: string }) {
  const status = item.installed ? "Já neste PC" : "Será baixado";
  return (
    <span className="model-select-row">
      <StatusGlyph installed={item.installed} />
      <span className="model-select-copy">
        <span className="model-select-name">{item.label}</span>
        {meta ? <span className="model-select-meta">{meta}</span> : null}
      </span>
      <span className="sr-only">{status}</span>
    </span>
  );
}
