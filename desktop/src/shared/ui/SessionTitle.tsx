import { useEffect, useState } from "react";

interface SessionTitleProps {
  value: string;
  disabled?: boolean;
  onCommit: (title: string) => Promise<void>;
}

export function SessionTitle({ value, disabled = false, onCommit }: SessionTitleProps) {
  const [draft, setDraft] = useState(value);

  useEffect(() => {
    setDraft(value);
  }, [value]);

  const commit = () => {
    const next = draft.trim();
    if (!next) {
      setDraft(value);
      return;
    }
    if (next === value) return;
    void onCommit(next);
  };

  return (
    <input
      className="title-input"
      value={draft}
      disabled={disabled}
      aria-label="Título da sessão"
      onChange={(event) => setDraft(event.target.value)}
      onBlur={commit}
      onKeyDown={(event) => {
        if (event.key === "Enter") {
          event.currentTarget.blur();
        }
      }}
    />
  );
}
