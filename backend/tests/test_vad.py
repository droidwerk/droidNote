from __future__ import annotations

import numpy as np

from app.infrastructure.asr.vad import SpeechBuffer, chunk_monitor, has_speech


def test_has_speech_detects_burst_inside_silence() -> None:
    silence = np.zeros(16_000, dtype=np.float32)
    burst = np.full(1_600, 0.2, dtype=np.float32)
    window = np.concatenate([silence, burst, silence])
    assert has_speech(window.tolist()) is True


def test_has_speech_rejects_near_silence() -> None:
    quiet = np.full(8_000, 0.0004, dtype=np.float32)
    assert has_speech(quiet.tolist()) is False


def test_chunk_monitor_reports_bars() -> None:
    burst = np.full(1_024, 0.2, dtype=np.float32)
    rms, speech, bars = chunk_monitor(burst.tolist())
    assert speech is True
    assert rms > 0
    assert len(bars) == 16
    assert max(bars) > 0


def test_speech_buffer_emits_on_max_length() -> None:
    buf = SpeechBuffer(16_000, min_ms=600, max_ms=2000, silence_ms=400, overlap_ms=200)
    loud = [0.2] * 32_000
    windows = buf.push(loud, 0)
    assert windows
    samples, start_ms, end_ms = windows[0]
    assert len(samples) >= 16_000
    assert end_ms > start_ms


def test_speech_buffer_emits_after_silence() -> None:
    buf = SpeechBuffer(16_000, min_ms=400, max_ms=8000, silence_ms=200, overlap_ms=0)
    speech = [0.2] * 8_000
    silence = [0.0] * 8_000
    first = buf.push(speech, 0)
    assert first == []
    second = buf.push(silence, 500)
    assert second
    assert has_speech(second[0][0])
