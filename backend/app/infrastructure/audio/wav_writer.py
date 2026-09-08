from __future__ import annotations

import threading
import wave
from collections.abc import Sequence
from pathlib import Path

import numpy as np


class SessionWavWriter:
    def __init__(self, path: Path, sample_rate: int) -> None:
        self.path = path
        self._lock = threading.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)
        self._wav = wave.open(str(path), "wb")
        self._wav.setnchannels(1)
        self._wav.setsampwidth(2)
        self._wav.setframerate(int(sample_rate))

    def write(self, samples: Sequence[float]) -> None:
        audio = np.asarray(samples, dtype=np.float32)
        pcm = (np.clip(audio, -1.0, 1.0) * 32767.0).astype(np.int16)
        with self._lock:
            self._wav.writeframes(pcm.tobytes())

    def close(self) -> None:
        with self._lock:
            try:
                self._wav.close()
            except Exception:
                pass
