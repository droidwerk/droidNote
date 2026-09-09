import type { Provider } from "../api/types";

interface EngineSwitchProps {
  value: Provider;
  disabled?: boolean;
  onChange: (value: Provider) => void;
}

export function EngineSwitch({ value, disabled = false, onChange }: EngineSwitchProps) {
  const cloud = value === "openai";
  return (
    <div
      className={cloud ? "engine-switch is-cloud" : "engine-switch"}
      role="radiogroup"
      aria-label="Motor"
    >
      <button
        type="button"
        role="radio"
        aria-checked={!cloud}
        disabled={disabled}
        className={!cloud ? "on" : ""}
        onClick={() => onChange("neste_pc")}
      >
        Modelos locais
      </button>
      <button
        type="button"
        role="radio"
        aria-checked={cloud}
        disabled={disabled}
        className={cloud ? "on" : ""}
        onClick={() => onChange("openai")}
      >
        OpenAI
      </button>
    </div>
  );
}
