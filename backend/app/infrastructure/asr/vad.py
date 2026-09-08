from __future__ import annotations

import math

import numpy as np

RMS_THRESHOLD = 0.004
FRAME_SAMPLES = 320  # 20 ms at 16 kHz


def rms_level(samples: list[float] | np.ndarray) -> float:
    data = np.asarray(samples, dtype=np.float32)
    if data.size == 0:
        return 0.0
    rms = float(np.sqrt(np.mean(np.square(data))))
    if math.isnan(rms):
        return 0.0
    return rms


def chunk_monitor(
    samples: list[float] | np.ndarray,
    bar_count: int = 16,
) -> tuple[float, bool, list[float]]:
    data = np.asarray(samples, dtype=np.float32)
    rms = rms_level(data)
    speech = has_speech(data)
    if data.size == 0:
        return 0.0, False, [0.0] * bar_count
    step = max(1, data.size // bar_count)
    bars: list[float] = []
    for index in range(bar_count):
        sl = data[index * step : (index + 1) * step]
        peak = rms_level(sl) if sl.size else 0.0
        bars.append(min(1.0, peak / 0.04))
    return rms, speech, bars


class SpeechBuffer:
    """Accumulate samples until silence or max length, then emit a window."""

    def __init__(
        self,
        sample_rate: int,
        *,
        min_ms: int = 600,
        max_ms: int = 6000,
        silence_ms: int = 400,
        overlap_ms: int = 300,
    ) -> None:
        self.sample_rate = sample_rate
        self.min_samples = max(FRAME_SAMPLES, int(sample_rate * min_ms / 1000))
        self.max_samples = int(sample_rate * max_ms / 1000)
        self.silence_samples = int(sample_rate * silence_ms / 1000)
        self.overlap_samples = int(sample_rate * overlap_ms / 1000)
        self.samples: list[float] = []
        self.start_ms = 0
        self.silence = 0
        self.speech_seen = False

    def reset(self) -> None:
        self.samples = []
        self.start_ms = 0
        self.silence = 0
        self.speech_seen = False

    def push(self, chunk: list[float], timestamp_ms: int) -> list[tuple[list[float], int, int]]:
        if not chunk:
            return []
        emitted: list[tuple[list[float], int, int]] = []
        offset = 0
        while offset < len(chunk):
            frame = chunk[offset : offset + FRAME_SAMPLES]
            offset += FRAME_SAMPLES
            if not frame:
                break
            speaking = has_speech(frame)
            frame_start = timestamp_ms + int((offset - len(frame)) * 1000 / self.sample_rate)
            if speaking:
                if not self.samples:
                    self.start_ms = max(timestamp_ms, frame_start)
                self.speech_seen = True
                self.silence = 0
                self.samples.extend(frame)
            elif self.speech_seen:
                self.silence += len(frame)
                self.samples.extend(frame)
                if self.silence >= self.silence_samples and len(self.samples) >= self.min_samples:
                    emitted.append(self._take(keep_overlap=False))
            if len(self.samples) >= self.max_samples:
                emitted.append(self._take(keep_overlap=True))
        return [item for item in emitted if item[0]]

    def flush(self) -> tuple[list[float], int, int] | None:
        if self.speech_seen and len(self.samples) >= self.min_samples:
            return self._take(keep_overlap=False)
        self.reset()
        return None

    def _take(self, *, keep_overlap: bool) -> tuple[list[float], int, int]:
        data = self.samples
        start_ms = self.start_ms
        end_ms = start_ms + int(len(data) * 1000 / self.sample_rate)
        if keep_overlap and self.overlap_samples > 0 and len(data) > self.overlap_samples:
            self.samples = data[-self.overlap_samples :]
            self.start_ms = end_ms - int(len(self.samples) * 1000 / self.sample_rate)
            self.speech_seen = True
            self.silence = 0
        else:
            self.reset()
        return data, start_ms, end_ms


def has_speech(samples: list[float] | np.ndarray, threshold: float = RMS_THRESHOLD) -> bool:
    data = np.asarray(samples, dtype=np.float32)
    if data.size == 0:
        return False
    if data.size < FRAME_SAMPLES:
        rms = float(np.sqrt(np.mean(np.square(data))))
        return (not math.isnan(rms)) and rms >= threshold
    usable = data[: data.size - (data.size % FRAME_SAMPLES)]
    frames = usable.reshape(-1, FRAME_SAMPLES)
    rms = np.sqrt(np.mean(np.square(frames), axis=1))
    finite = rms[np.isfinite(rms)]
    if finite.size == 0:
        return False
    return bool(np.any(finite >= threshold))
