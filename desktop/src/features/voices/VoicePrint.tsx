import type { CSSProperties } from "react";

import { voiceprintBars } from "../../shared/lib/voices";

interface VoicePrintProps {
  seed: string;
  color: string;
  active?: boolean;
  size?: "sm" | "md";
}

/** Assinatura visual da voz: estável por voz, viva quando ela está falando. */
export function VoicePrint({ seed, color, active = false, size = "md" }: VoicePrintProps) {
  const bars = voiceprintBars(seed, size === "sm" ? 9 : 14);
  return (
    <span
      className={["voiceprint", `voiceprint-${size}`, active ? "is-active" : ""].filter(Boolean).join(" ")}
      style={{ "--vp": color } as CSSProperties}
      aria-hidden
    >
      {bars.map((value, index) => (
        <i key={index} style={{ "--h": value, "--d": `${(index * 53) % 400}ms` } as CSSProperties} />
      ))}
    </span>
  );
}
