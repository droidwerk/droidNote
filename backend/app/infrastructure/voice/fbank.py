"""Filterbank log-mel compatível com `kaldi.fbank` (torchaudio), em numpy puro.

Os modelos de impressão vocal (WeSpeaker, 3D-Speaker) foram treinados com essa
feature. Reproduzir o Kaldi aqui evita puxar torch/torchaudio para o sidecar.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np

SAMPLE_RATE = 16_000
FRAME_LENGTH = 400  # 25 ms
FRAME_SHIFT = 160  # 10 ms
FFT_SIZE = 512
NUM_MEL_BINS = 80
LOW_FREQ = 20.0
PREEMPHASIS = 0.97
_EPS = float(np.finfo(np.float32).eps)


def _mel(freq: np.ndarray | float) -> np.ndarray:
    return 1127.0 * np.log(1.0 + np.asarray(freq, dtype=np.float64) / 700.0)


@lru_cache(maxsize=4)
def mel_banks(num_bins: int = NUM_MEL_BINS, fft_size: int = FFT_SIZE, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    """Matriz (num_bins, fft_size/2 + 1) igual à `get_mel_banks` do Kaldi."""
    num_fft_bins = fft_size // 2
    nyquist = 0.5 * sample_rate
    bin_width = sample_rate / fft_size
    mel_low = _mel(LOW_FREQ)
    mel_high = _mel(nyquist)
    delta = (mel_high - mel_low) / (num_bins + 1)
    index = np.arange(num_bins, dtype=np.float64)[:, None]
    left = mel_low + index * delta
    center = mel_low + (index + 1.0) * delta
    right = mel_low + (index + 2.0) * delta
    mel = _mel(bin_width * np.arange(num_fft_bins, dtype=np.float64))[None, :]
    up = (mel - left) / (center - left)
    down = (right - mel) / (right - center)
    banks = np.maximum(0.0, np.minimum(up, down))
    banks = np.pad(banks, ((0, 0), (0, 1)))
    return banks.astype(np.float32)


@lru_cache(maxsize=4)
def _window(kind: str, size: int = FRAME_LENGTH) -> np.ndarray:
    n = np.arange(size, dtype=np.float64)
    if kind == "hamming":
        win = 0.54 - 0.46 * np.cos(2.0 * np.pi * n / (size - 1))
    else:  # povey
        win = np.power(0.5 - 0.5 * np.cos(2.0 * np.pi * n / (size - 1)), 0.85)
    return win.astype(np.float32)


def frame_count(num_samples: int) -> int:
    if num_samples < FRAME_LENGTH:
        return 0
    return 1 + (num_samples - FRAME_LENGTH) // FRAME_SHIFT


def fbank(
    samples: np.ndarray,
    *,
    window: str = "povey",
    scale: float = 1.0,
) -> np.ndarray:
    """Log-mel (frames, 80). `samples` em float a 16 kHz."""
    audio = np.asarray(samples, dtype=np.float32).reshape(-1) * np.float32(scale)
    count = frame_count(audio.size)
    if count == 0:
        return np.zeros((0, NUM_MEL_BINS), dtype=np.float32)
    starts = np.arange(count) * FRAME_SHIFT
    frames = audio[starts[:, None] + np.arange(FRAME_LENGTH)[None, :]].astype(np.float32)
    frames = frames - frames.mean(axis=1, keepdims=True)
    shifted = np.concatenate([frames[:, :1], frames[:, :-1]], axis=1)
    frames = frames - PREEMPHASIS * shifted
    frames = frames * _window(window)
    spectrum = np.abs(np.fft.rfft(frames, n=FFT_SIZE, axis=1)) ** 2
    energies = spectrum.astype(np.float32) @ mel_banks().T
    return np.log(np.maximum(energies, _EPS)).astype(np.float32)


def cmn(features: np.ndarray) -> np.ndarray:
    """Normalização de média por enunciado (o que os dois modelos esperam)."""
    if features.size == 0:
        return features
    return features - features.mean(axis=0, keepdims=True)
