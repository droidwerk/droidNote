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
