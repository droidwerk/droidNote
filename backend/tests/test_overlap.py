from __future__ import annotations

from app.infrastructure.asr.overlap import drop_covered_words, strip_overlap


def test_strip_overlap_keeps_identical_utterance() -> None:
    assert strip_overlap("olá mundo", "olá mundo") == "olá mundo"


def test_strip_overlap_drops_repeated_prefix() -> None:
    previous = "vamos começar a reunião agora"
    current = "reunião agora e depois o café"
    assert strip_overlap(previous, current) == "e depois o café"


def test_strip_overlap_empty() -> None:
    assert strip_overlap("", "olá") == "olá"
    assert strip_overlap("olá", "") == ""


def test_drop_covered_words_keeps_first_window() -> None:
    words = [(0.2, 0.6, "ok")]
    assert drop_covered_words(words, 0, None) == words


def test_drop_covered_words_cuts_short_phrase_on_boundary() -> None:
    words = [(0.2, 0.6, "ok"), (1.2, 2.0, "vamos")]
    assert drop_covered_words(words, 19_000, 20_000) == [(1.2, 2.0, "vamos")]
