from __future__ import annotations

import numpy as np

from app.infrastructure.audio.resample import StreamResampler
from app.infrastructure.voice import diarize as diarize_module
from app.infrastructure.voice.diarize import Word, _Core, diarize_window
from app.infrastructure.voice.echo import EchoGate
from app.infrastructure.voice.fbank import NUM_MEL_BINS, cmn, fbank, mel_banks
from app.infrastructure.voice.tracker import (
    SpeakerTracker,
    agglomerate,
    blend_voiceprint,
    spectral_labels,
)


def _unit(vector: np.ndarray) -> np.ndarray:
    return (vector / np.linalg.norm(vector)).astype(np.float32)


def _voices(count: int, dim: int = 64, seed: int = 0) -> list[np.ndarray]:
    rng = np.random.default_rng(seed)
    return [_unit(rng.normal(size=dim)) for _ in range(count)]


def _sample(center: np.ndarray, rng: np.random.Generator, noise: float = 0.35) -> np.ndarray:
    return _unit(center + rng.normal(scale=noise / np.sqrt(center.size), size=center.size))


# ----------------------------------------------------------------- fbank


def test_fbank_matches_kaldi_frame_count_and_is_finite() -> None:
    audio = np.random.default_rng(1).normal(scale=0.05, size=16_000).astype(np.float32)
    features = fbank(audio)
    # snip_edges do Kaldi: 1 + (16000 - 400) // 160
    assert features.shape == (98, NUM_MEL_BINS)
    assert np.all(np.isfinite(features))
    normalized = cmn(features)
    assert np.allclose(normalized.mean(axis=0), 0.0, atol=1e-4)


def test_mel_banks_are_triangular_and_cover_the_band() -> None:
    banks = mel_banks()
    assert banks.shape == (NUM_MEL_BINS, 257)
    assert banks.min() >= 0.0
    assert banks.max() <= 1.0 + 1e-6
    assert np.all(banks.sum(axis=1) > 0)


def test_fbank_short_audio_returns_empty() -> None:
    assert fbank(np.zeros(100, dtype=np.float32)).shape == (0, NUM_MEL_BINS)


# ------------------------------------------------------------- resampler


def test_stream_resampler_keeps_block_size_and_removes_alias() -> None:
    src = 48_000
    t = np.arange(src * 2) / src
    speech_band = np.sin(2 * np.pi * 440 * t).astype(np.float32)
    above_nyquist = np.sin(2 * np.pi * 12_000 * t).astype(np.float32)
    clean = StreamResampler(src, 16_000)
    alias = StreamResampler(src, 16_000)
    out_clean = [clean.process(speech_band[i : i + 4800]) for i in range(0, speech_band.size, 4800)]
    out_alias = [alias.process(above_nyquist[i : i + 4800]) for i in range(0, above_nyquist.size, 4800)]
    assert {item.size for item in out_clean} == {1600}
    tone = np.concatenate(out_clean)[400:]
    assert abs(float(np.sqrt(np.mean(tone**2))) - 0.707) < 0.02
    # Sem filtro, 12 kHz dobraria para 4 kHz com amplitude cheia.
    assert float(np.sqrt(np.mean(np.concatenate(out_alias)[400:] ** 2))) < 0.01


def test_stream_resampler_handles_fractional_ratio() -> None:
    resampler = StreamResampler(44_100, 16_000)
    sizes = [resampler.process(np.zeros(4410, dtype=np.float32)).size for _ in range(50)]
    assert abs(sum(sizes) - 80_000) <= 2


def test_stream_resampler_same_rate_is_passthrough() -> None:
    data = np.arange(10, dtype=np.float32)
    assert np.array_equal(StreamResampler(16_000, 16_000).process(data), data)


# ------------------------------------------------------------------- eco


def test_echo_gate_silences_speaker_bleed_but_keeps_own_voice() -> None:
    rng = np.random.default_rng(2)
    remote = rng.normal(scale=0.08, size=16_000).astype(np.float32)
    gate = EchoGate()
    bleed = gate.process(remote * 0.3, remote)
    assert float(np.abs(bleed).max()) == 0.0
    assert gate.gated_ratio > 0.5

    own = rng.normal(scale=0.3, size=16_000).astype(np.float32)
    kept = gate.process(own, remote * 0.5)
    assert float(np.sqrt(np.mean(kept**2))) > 0.2


def test_echo_gate_without_system_audio_is_passthrough() -> None:
    data = np.full(3200, 0.1, dtype=np.float32)
    assert np.array_equal(EchoGate().process(data, None), data)


# ---------------------------------------------------------------- tracker


def test_tracker_separates_two_voices_and_keeps_them_stable() -> None:
    first, second = _voices(2)
    rng = np.random.default_rng(3)
    tracker = SpeakerTracker()
    keys = []
    for center in (first, second, first, second, first):
        match = tracker.assign(_sample(center, rng), 3.0, "loopback")
        assert match is not None
        keys.append(match.cluster)
    assert keys[0] == keys[2] == keys[4]
    assert keys[1] == keys[3]
    assert keys[0] != keys[1]
    assert len(tracker.clusters) == 2


def test_tracker_recognizes_saved_voiceprint() -> None:
    known, stranger = _voices(2, seed=4)
    tracker = SpeakerTracker({"ana": known})
    rng = np.random.default_rng(5)
    match = tracker.assign(_sample(known, rng), 4.0, "mic")
    assert match is not None and match.person_id == "ana"
    other = tracker.assign(_sample(stranger, rng), 4.0, "mic")
    assert other is not None and other.person_id is None


def test_tracker_short_piece_never_creates_a_voice() -> None:
    (voice,) = _voices(1, seed=6)
    tracker = SpeakerTracker()
    assert tracker.assign(voice, 0.5) is None
    assert tracker.clusters == {}


def test_spectral_finds_three_voices_and_one_voice() -> None:
    centers = _voices(3, seed=7)
    rng = np.random.default_rng(8)
    points = [_sample(center, rng, 0.9) for center in centers for _ in range(30)]
    labels = spectral_labels(points)
    assert len(set(labels)) == 3
    for block in range(3):
        assert len(set(labels[block * 30 : (block + 1) * 30])) == 1

    single = [_sample(centers[0], rng, 0.5) for _ in range(25)]
    assert len(set(spectral_labels(single))) == 1


def test_agglomerate_merges_only_close_points() -> None:
    first, second = _voices(2, seed=9)
    rng = np.random.default_rng(10)
    labels = agglomerate([_sample(first, rng), _sample(first, rng), _sample(second, rng)])
    assert labels[0] == labels[1] != labels[2]


def test_blend_voiceprint_moves_towards_new_samples() -> None:
    old, new = _voices(2, seed=11)
    blended, count = blend_voiceprint(old, 1, [(new, 9.0)])
    assert count == 2
    assert float(np.dot(blended, new)) > float(np.dot(old, new))


# -------------------------------------------------------------- diarizador


def test_diarize_window_splits_words_at_the_speaker_change(monkeypatch) -> None:
    first, second = _voices(2, seed=12)
    rng = np.random.default_rng(13)

    def fake_cores(embedder, samples, speech=None):
        cores = []
        for index in range(12):
            start = index * 0.75
            center = first if start < 4.5 else second
            cores.append(_Core(start, start + 0.75, _sample(center, rng, 0.2)))
        return cores

    monkeypatch.setattr(diarize_module, "window_embeddings", fake_cores)
    words = [Word(i * 0.5, i * 0.5 + 0.4, f" w{i}") for i in range(18)]
    turns = diarize_window(object(), SpeakerTracker(), np.zeros(16_000 * 9, dtype=np.float32), words)
    assert len(turns) == 2
    assert turns[0].cluster != turns[1].cluster
    assert turns[0].text.startswith("w0") and turns[1].text.endswith("w17")
    assert turns[0].end <= 4.6 <= turns[1].end
    assert turns[0].frames is not None and turns[0].frames.shape[1] == first.size


def test_diarize_window_without_embeddings_returns_single_unlabeled_turn(monkeypatch) -> None:
    monkeypatch.setattr(diarize_module, "window_embeddings", lambda *args, **kwargs: [])
    words = [Word(0.0, 0.4, " olá"), Word(0.5, 0.9, " mundo")]
    turns = diarize_window(object(), SpeakerTracker(), np.zeros(16_000, dtype=np.float32), words)
    assert len(turns) == 1
    assert turns[0].text == "olá mundo"
    assert turns[0].cluster is None
