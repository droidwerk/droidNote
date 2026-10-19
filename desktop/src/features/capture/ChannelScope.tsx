import { useEffect, useRef } from "react";

import { cssVar, useTheme } from "../../shared/lib/theme";

interface ChannelScopeProps {
  /** Nível RMS do quadro mais recente (0..1) ou null sem sinal. */
  rms: number | null;
  speech: boolean;
  /** Muda a cada quadro do monitor; dispara um passo do osciloscópio. */
  tick: number;
  active: boolean;
  tone: "mic" | "system";
}

const HISTORY = 96;

/** Osciloscópio rolante: cada coluna é um quadro de ~80 ms do canal. */
export function ChannelScope({ rms, speech, tick, active, tone }: ChannelScopeProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const history = useRef<{ level: number; speech: boolean }[]>([]);
  const { theme } = useTheme();

  useEffect(() => {
    if (!active) {
      history.current = [];
    } else if (rms !== null) {
      history.current.push({ level: toLevel(rms), speech });
      if (history.current.length > HISTORY) history.current.shift();
    }
    draw();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tick, active, theme]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    const observer = new ResizeObserver(() => draw());
    observer.observe(canvas);
    return () => observer.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function draw() {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ratio = window.devicePixelRatio || 1;
    const width = Math.max(1, Math.round(canvas.clientWidth * ratio));
    const height = Math.max(1, Math.round(canvas.clientHeight * ratio));
    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
    }
    const context = canvas.getContext("2d");
    if (!context) return;
    context.clearRect(0, 0, width, height);
    const mid = height / 2;
    const color = cssVar(tone === "mic" ? "--channel-mic" : "--channel-system", "#ff4400");
    const idle = cssVar("--scope-idle", "rgba(255,255,255,0.16)");
    context.fillStyle = cssVar("--scope-axis", "rgba(255,255,255,0.08)");
    context.fillRect(0, Math.round(mid), width, Math.max(1, ratio));
    const step = width / HISTORY;
    const column = Math.max(1, step * 0.56);
    const items = history.current;
    for (let index = 0; index < items.length; index += 1) {
      const item = items[items.length - 1 - index];
      if (!item) continue;
      const x = width - (index + 1) * step;
      const amp = Math.max(ratio, item.level * (height / 2 - 2 * ratio));
      const fade = 1 - index / (HISTORY * 1.15);
      context.globalAlpha = Math.max(0.12, fade);
      context.fillStyle = item.speech ? color : idle;
      context.fillRect(x, mid - amp, column, amp * 2);
    }
    context.globalAlpha = 1;
  }

  return <canvas ref={canvasRef} className="scope" aria-hidden />;
}

/** RMS -> 0..1 em escala de dB (-60 dBFS a -6 dBFS). */
export function toLevel(rms: number): number {
  if (!Number.isFinite(rms) || rms <= 0) return 0;
  const db = 20 * Math.log10(rms);
  return Math.max(0, Math.min(1, (db + 60) / 54));
}
