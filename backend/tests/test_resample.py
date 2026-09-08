from __future__ import annotations

import numpy as np

from app.infrastructure.audio.resample import block_frames, candidate_rates, resample_mono


def test_candidate_rates_puts_preferred_first() -> None:
    rates = candidate_rates(48_000)
    assert rates[0] == 48_000
    assert 16_000 in rates


def test_resample_48000_to_16000_keeps_shape() -> None:
    # 100 ms of 440 Hz at 48 kHz
    n = 4800
    t = np.arange(n, dtype=np.float32) / 48_000
    wave = np.sin(2 * np.pi * 440 * t).astype(np.float32)
    out = resample_mono(wave, 48_000, 16_000)
    assert 1550 < out.size < 1650
    assert float(np.max(np.abs(out))) > 0.2


def test_resample_same_rate_is_noop() -> None:
    data = np.array([0.1, 0.2, 0.3], dtype=np.float32)
    out = resample_mono(data, 16_000, 16_000)
    assert np.allclose(out, data)


def test_block_frames_100ms() -> None:
    assert block_frames(16_000) == 1600
    assert block_frames(48_000) == 4800
