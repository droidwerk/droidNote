import type { Provider } from "../api/types";
import { useT } from "../i18n";

interface EngineSwitchProps {
  value: Provider;
  disabled?: boolean;
  onChange: (value: Provider) => void;
}

export function EngineSwitch({ value, disabled = false, onChange }: EngineSwitchProps) {
  const t = useT();
  const cloud = value === "openai";
  return (
    <div
      className={cloud ? "engine-switch is-cloud" : "engine-switch"}
      role="radiogroup"
      aria-label={t("engine.aria")}
    >
      <button
        type="button"
        role="radio"
        aria-checked={!cloud}
        disabled={disabled}
        className={!cloud ? "on" : ""}
        onClick={() => onChange("neste_pc")}
      >
        {t("engine.local")}
      </button>
      <button
        type="button"
        role="radio"
        aria-checked={cloud}
        disabled={disabled}
        className={cloud ? "on" : ""}
        onClick={() => onChange("openai")}
      >
        {t("engine.openai")}
      </button>
    </div>
  );
}
