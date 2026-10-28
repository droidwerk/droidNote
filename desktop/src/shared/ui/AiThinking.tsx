import { useEffect, useState } from "react";

const GLYPHS = "▓▒░<>/\\|=+*#01";
const STEP_MS = 2400;
const FRAME_MS = 45;

interface AiThinkingProps {
  /** Etapas mostradas em sequência ("Lendo a transcrição", "Escrevendo a ata"…). */
  steps: string[];
  /** Linhas de esqueleto abaixo, imitando o texto que vai chegar. */
  lines?: number;
  compact?: boolean;
  className?: string;
}

/** Carregamento dos processos de IA: núcleo em órbita, texto que se decodifica e varredura. */
export function AiThinking({ steps, lines = 0, compact = false, className }: AiThinkingProps) {
  const [step, setStep] = useState(0);
  const label = steps[step % Math.max(steps.length, 1)] ?? "";
  const shown = useDecode(label);

  useEffect(() => {
    if (steps.length < 2) return undefined;
    const timer = window.setInterval(() => setStep((value) => value + 1), STEP_MS);
    return () => window.clearInterval(timer);
  }, [steps.length]);

  return (
    <div
      className={["ai-thinking", compact ? "is-compact" : "", className ?? ""].filter(Boolean).join(" ")}
      role="status"
      aria-live="polite"
      aria-label={label}
    >
      <div className="ai-thinking-row">
        <span className="ai-core" aria-hidden>
          <span className="ai-core-ring" />
          <span className="ai-core-orbit">
            <i />
            <i />
            <i />
          </span>
          <span className="ai-core-dot" />
        </span>
        <span className="ai-thinking-label" aria-hidden>
          {shown}
          <span className="ai-caret" />
        </span>
      </div>
      <span className="ai-scan" aria-hidden />
      {lines > 0 ? (
        <div className="ai-skeleton" aria-hidden>
          {Array.from({ length: lines }, (_, index) => (
            <span key={index} style={{ width: `${[92, 78, 86, 64, 72, 58][index % 6]}%`, animationDelay: `${index * 120}ms` }} />
          ))}
        </div>
      ) : null}
    </div>
  );
}

/** Revela o texto da esquerda para a direita, com símbolos aleatórios na frente. */
function useDecode(text: string): string {
  const [frame, setFrame] = useState(0);
  const reduced = usePrefersReducedMotion();
  useEffect(() => {
    setFrame(0);
    if (reduced) return undefined;
    const timer = window.setInterval(() => {
      setFrame((value) => {
        if (value >= text.length + 4) {
          window.clearInterval(timer);
          return value;
        }
        return value + 1;
      });
    }, FRAME_MS);
    return () => window.clearInterval(timer);
  }, [text, reduced]);
  if (reduced || frame >= text.length + 4) return text;
  const revealed = text.slice(0, frame);
  const noise = Array.from({ length: Math.min(4, text.length - frame) }, () => GLYPHS[Math.floor(Math.random() * GLYPHS.length)]).join("");
  return revealed + noise;
}

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(() => {
    try {
      return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    } catch {
      return false;
    }
  });
  useEffect(() => {
    try {
      const query = window.matchMedia("(prefers-reduced-motion: reduce)");
      const listener = () => setReduced(query.matches);
      query.addEventListener("change", listener);
      return () => query.removeEventListener("change", listener);
    } catch {
      return undefined;
    }
  }, []);
  return reduced;
}
