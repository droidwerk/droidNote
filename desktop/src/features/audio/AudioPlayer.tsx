import { useEffect, useRef, useState, type MouseEvent } from "react";

import { api } from "../../shared/api/client";
import { useT } from "../../shared/i18n";
import { formatClock } from "../../shared/lib/format";
import { cssVar, useTheme } from "../../shared/lib/theme";
import { Button } from "../../shared/ui/primitives";

interface AudioPlayerProps {
  sessionId: string;
  seekMs: number | null;
  onSeeked?: () => void;
  onTimeMs?: (ms: number) => void;
}

export function AudioPlayer({ sessionId, seekMs, onSeeked, onTimeMs }: AudioPlayerProps) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const peaksRef = useRef<number[]>([]);
  const [playing, setPlaying] = useState(false);
  const [durationMs, setDurationMs] = useState(0);
  const [currentMs, setCurrentMs] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const { theme } = useTheme();
  const t = useT();

  useEffect(() => {
    let revoked: string | null = null;
    let cancelled = false;
    setReady(false);
    setError(null);
    setPlaying(false);
    setCurrentMs(0);
    void (async () => {
      try {
        const blob = await api.sessionAudio(sessionId);
        if (cancelled) return;
        const buffer = await blob.arrayBuffer();
        const objectUrl = URL.createObjectURL(new Blob([buffer], { type: "audio/wav" }));
        revoked = objectUrl;
        const audio = audioRef.current;
        if (audio) {
          audio.src = objectUrl;
          audio.load();
        }
        try {
          const context = new AudioContext();
          const decoded = await context.decodeAudioData(buffer.slice(0));
          peaksRef.current = downsamplePeaks(decoded.getChannelData(0), 180);
          await context.close();
          drawWave(canvasRef.current, peaksRef.current, 0);
        } catch {
          peaksRef.current = [];
        }
        if (!cancelled) setReady(true);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : t("audio.missing"));
        }
      }
    })();
    return () => {
      cancelled = true;
      if (revoked) URL.revokeObjectURL(revoked);
    };
  }, [sessionId]);

  useEffect(() => {
    if (seekMs === null) return;
    const audio = audioRef.current;
    if (!audio || !ready) return;
    audio.currentTime = Math.max(0, seekMs / 1000);
    void audio.play().then(
      () => setPlaying(true),
      () => setPlaying(false),
    );
    onSeeked?.();
  }, [seekMs, ready, onSeeked]);

  useEffect(() => {
    drawWave(canvasRef.current, peaksRef.current, durationMs ? currentMs / durationMs : 0);
  }, [theme, durationMs, currentMs]);

  const toggle = () => {
    const audio = audioRef.current;
    if (!audio) return;
    if (audio.paused) {
      void audio.play().then(
        () => setPlaying(true),
        () => setPlaying(false),
      );
    } else {
      audio.pause();
      setPlaying(false);
    }
  };

  const seekCanvas = (event: MouseEvent<HTMLCanvasElement>) => {
    const audio = audioRef.current;
    const canvas = canvasRef.current;
    if (!audio || !canvas || !durationMs) return;
    const rect = canvas.getBoundingClientRect();
    const ratio = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width));
    audio.currentTime = (ratio * durationMs) / 1000;
  };

  return (
    <div className="audio-player">
      <audio
        ref={audioRef}
        onLoadedMetadata={(event) => setDurationMs(event.currentTarget.duration * 1000)}
        onTimeUpdate={(event) => {
          const ms = event.currentTarget.currentTime * 1000;
          setCurrentMs(ms);
          onTimeMs?.(ms);
          drawWave(canvasRef.current, peaksRef.current, durationMs ? ms / durationMs : 0);
        }}
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onEnded={() => setPlaying(false)}
      />
      <Button variant="primary" size="sm" onClick={toggle} disabled={!ready}>
        {playing ? t("audio.pause") : t("audio.play")}
      </Button>
      <div className="audio-player-wave">
        <canvas
          ref={canvasRef}
          width={720}
          height={48}
          onClick={seekCanvas}
          aria-label={t("audio.waveform")}
        />
      </div>
      <span className="audio-player-clock">
        {formatClock(currentMs)} / {formatClock(durationMs)}
      </span>
      {error ? <p className="muted">{error}</p> : null}
    </div>
  );
}

function downsamplePeaks(data: Float32Array, buckets: number): number[] {
  const size = Math.max(1, Math.floor(data.length / buckets));
  const peaks: number[] = [];
  for (let index = 0; index < buckets; index += 1) {
    const start = index * size;
    let peak = 0;
    for (let offset = 0; offset < size && start + offset < data.length; offset += 1) {
      peak = Math.max(peak, Math.abs(data[start + offset] ?? 0));
    }
    peaks.push(peak);
  }
  return peaks;
}

function drawWave(canvas: HTMLCanvasElement | null, peaks: number[], progress: number): void {
  if (!canvas) return;
  const context = canvas.getContext("2d");
  if (!context) return;
  const width = canvas.width;
  const height = canvas.height;
  context.clearRect(0, 0, width, height);
  const count = peaks.length || 1;
  const gap = width / count;
  const playedUntil = progress * width;
  peaks.forEach((peak, index) => {
    const x = index * gap;
    const bar = Math.max(2, peak * (height - 8));
    context.fillStyle = x < playedUntil ? cssVar("--record", "#ff6a14") : cssVar("--wave-idle", "rgba(255,255,255,0.22)");
    context.fillRect(x + 1, (height - bar) / 2, Math.max(1, gap - 2), bar);
  });
}
