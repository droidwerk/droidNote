import { Badge } from "../../shared/ui/primitives";

interface CaptureMeterProps {
  recording: boolean;
  phase: string;
  elapsedMs: number;
  socketLive: boolean;
  stale: boolean;
  monitor: {
    rms: number;
    speech: boolean;
    bars: number[];
    queued: number;
    buffer_ms: number;
    whisper_loaded: boolean;
  } | null;
  asrBusy: boolean;
  asrEmpty: boolean;
  asrQueued?: number;
}

export function CaptureMeter({
  recording,
  phase,
  elapsedMs,
  socketLive,
  stale,
  monitor,
  asrBusy,
  asrEmpty,
  asrQueued = 0,
}: CaptureMeterProps) {
  const bars = normalizeBars(monitor?.bars);
  const status = statusCopy({ recording, phase, monitor, asrBusy, asrEmpty, stale, asrQueued });
  const speech = monitor?.speech === true;
  const signalTone = !recording
    ? "idle"
    : stale
      ? "stale"
      : speech
        ? "speech"
        : "listening";

  return (
    <section className={`meter meter-${signalTone}`}>
      <div className="meter-time">
        <span className="meter-state-dot" aria-hidden />
        <p className={recording ? "meter-clock live" : "meter-clock"}>{formatElapsed(elapsedMs)}</p>
      </div>
      <div className="vu" aria-hidden="true">
        {bars.map((value, index) => (
          <span
            key={index}
            className={speech ? "on" : ""}
            style={{ height: `${barHeight(value, index, recording && !monitor)}%` }}
          />
        ))}
      </div>
      <p className="meter-status">{status}</p>
      <div className="meter-badges">
        <Badge tone={!socketLive || stale ? "warning" : "success"}>
          {!socketLive ? "Reconectando" : stale ? "Sem sinal" : "Tempo real"}
        </Badge>
        <Badge tone={monitor?.whisper_loaded ? "success" : "neutral"}>
          {monitor?.whisper_loaded ? "Motor pronto" : "Motor em espera"}
        </Badge>
      </div>
    </section>
  );
}

function normalizeBars(values?: number[]): number[] {
  return Array.from({ length: 16 }, (_, index) => {
    const value = values?.[index];
    return typeof value === "number" && Number.isFinite(value)
      ? Math.max(0, Math.min(1, value))
      : 0;
  });
}

function barHeight(value: number, index: number, waiting: boolean): number {
  if (waiting) return 10 + ((index * 7) % 18);
  return Math.max(4, Math.min(100, value * 100));
}

function formatElapsed(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const minutes = String(Math.floor(total / 60)).padStart(2, "0");
  const seconds = String(total % 60).padStart(2, "0");
  return `${minutes}:${seconds}`;
}

function statusCopy(input: {
  recording: boolean;
  phase: string;
  monitor: CaptureMeterProps["monitor"];
  asrBusy: boolean;
  asrEmpty: boolean;
  stale: boolean;
  asrQueued: number;
}): string {
  if (!input.recording && input.asrBusy) {
    return input.asrQueued > 0
      ? `Captura parada. Ainda transcrevendo ${input.asrQueued} trecho${input.asrQueued === 1 ? "" : "s"}.`
      : "Captura parada. Ainda transcrevendo o resto do áudio…";
  }
  if (!input.recording) {
    return "Ligue a captura. As barras sobem quando o microfone ouve algo.";
  }
  if (input.stale) {
    return "O sinal de áudio parou de chegar. Tentando restabelecer a conexão…";
  }
  if (input.phase === "loading" || (input.recording && !input.monitor?.whisper_loaded && !input.monitor)) {
    return "Microfone já ouve. Carregando Whisper na memória…";
  }
  if (input.asrBusy) {
    return "Transcrevendo o bloco de áudio…";
  }
  if (input.monitor?.speech) {
    return "Fala no ar. O texto entra na pausa, ou no máximo a cada vinte segundos.";
  }
  if (input.monitor && input.monitor.buffer_ms > 0 && input.monitor.rms < 0.004) {
    return "Sinal muito baixo. Fale mais perto do microfone ou marque só o mic.";
  }
  if (input.asrEmpty) {
    return "O motor rodou neste bloco e não gerou texto. Continue falando.";
  }
  return "Ouvindo. Fale algo — as barras precisam se mexer se a captura estiver viva.";
}
