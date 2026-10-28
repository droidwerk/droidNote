import { useCallback, useState } from "react";

/** Liga/desliga lembrado neste PC (barra recolhida, painel aberto…). */
export function useFlag(key: string, initial = false): [boolean, () => void, (value: boolean) => void] {
  const [value, setValue] = useState(() => {
    try {
      const stored = window.localStorage.getItem(key);
      return stored === null ? initial : stored === "1";
    } catch {
      return initial;
    }
  });
  const set = useCallback(
    (next: boolean) => {
      setValue(next);
      try {
        window.localStorage.setItem(key, next ? "1" : "0");
      } catch {
        /* só conveniência */
      }
    },
    [key],
  );
  const toggle = useCallback(() => {
    setValue((current) => {
      const next = !current;
      try {
        window.localStorage.setItem(key, next ? "1" : "0");
      } catch {
        /* só conveniência */
      }
      return next;
    });
  }, [key]);
  return [value, toggle, set];
}
