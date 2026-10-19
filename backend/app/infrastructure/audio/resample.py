from __future__ import annotations

import numpy as np

CANDIDATE_RATES = (16_000, 48_000, 44_100, 32_000, 22_050, 8_000)


def candidate_rates(preferred: int = 16_000) -> tuple[int, ...]:
    ordered: list[int] = []
    for rate in (preferred, *CANDIDATE_RATES):
        if rate not in ordered:
            ordered.append(rate)
    return tuple(ordered)


def resample_mono(samples: np.ndarray | list[float], src_hz: int, dst_hz: int) -> np.ndarray:
    data = np.asarray(samples, dtype=np.float32).reshape(-1)
    if data.size == 0 or src_hz <= 0 or dst_hz <= 0 or src_hz == dst_hz:
        return data
    n_out = max(1, int(round(data.size * dst_hz / src_hz)))
    old_x = np.linspace(0.0, 1.0, num=data.size, endpoint=False)
    new_x = np.linspace(0.0, 1.0, num=n_out, endpoint=False)
    return np.interp(new_x, old_x, data).astype(np.float32)


def block_frames(sample_rate: int, block_ms: int = 100) -> int:
    return max(64, int(sample_rate * block_ms / 1000))


def lowpass_taps(src_hz: int, cutoff_hz: float, taps: int = 63) -> np.ndarray:
    """FIR passa-baixa (sinc com janela Blackman), ganho unitário em DC."""
    n = np.arange(taps, dtype=np.float64) - (taps - 1) / 2.0
    fc = cutoff_hz / src_hz
    kernel = 2.0 * fc * np.sinc(2.0 * fc * n) * np.blackman(taps)
    kernel /= kernel.sum()
    return kernel.astype(np.float32)


class StreamResampler:
    """Reamostragem contínua entre blocos, com anti-aliasing.

    A versão por bloco (`resample_mono`) interpolava cada 100 ms isolado e sem
    filtro: 48 kHz -> 16 kHz dobrava o que fica acima de 8 kHz para dentro da
    faixa de voz e criava degraus a cada 10 Hz. Aqui o filtro e a fase passam
    de um bloco para o outro.
    """

    def __init__(self, src_hz: int, dst_hz: int, taps: int = 63) -> None:
        self.src_hz = int(src_hz)
        self.dst_hz = int(dst_hz)
        self._passthrough = self.src_hz == self.dst_hz or self.src_hz <= 0 or self.dst_hz <= 0
        self._step = self.src_hz / self.dst_hz if not self._passthrough else 1.0
        self._kernel = (
            lowpass_taps(self.src_hz, 0.45 * min(self.src_hz, self.dst_hz), taps)
            if not self._passthrough and self.src_hz > self.dst_hz
            else None
        )
        self._history = np.zeros((taps - 1) if self._kernel is not None else 0, dtype=np.float32)
        self._last = np.float32(0.0)
        self._pos = 0.0

    def process(self, block: np.ndarray | list[float]) -> np.ndarray:
        data = np.asarray(block, dtype=np.float32).reshape(-1)
        if self._passthrough or data.size == 0:
            return data
        if self._kernel is not None:
            joined = np.concatenate([self._history, data])
            filtered = np.convolve(joined, self._kernel, mode="valid").astype(np.float32)
            self._history = joined[-(self._kernel.size - 1) :]
        else:
            filtered = data
        # x[0] é a última amostra do bloco anterior (posição -1).
        x = np.concatenate([[self._last], filtered]).astype(np.float32)
        length = filtered.size
        if self._pos > length - 1:
            self._pos -= length
            self._last = filtered[-1]
            return np.zeros(0, dtype=np.float32)
        positions = np.arange(self._pos, length - 1 + 1e-9, self._step)
        idx = positions + 1.0
        lo = np.floor(idx).astype(np.int64)
        hi = np.minimum(lo + 1, x.size - 1)
        frac = (idx - lo).astype(np.float32)
        out = x[lo] * (1.0 - frac) + x[hi] * frac
        self._pos = float(positions[-1] + self._step - length) if positions.size else self._pos - length
        self._last = filtered[-1]
        return out.astype(np.float32)
