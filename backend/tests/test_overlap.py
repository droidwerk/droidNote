from __future__ import annotations

from app.infrastructure.asr.overlap import strip_overlap


def test_strip_overlap_keeps_identical_utterance() -> None:
    assert strip_overlap("olá mundo", "olá mundo") == "olá mundo"


def test_strip_overlap_drops_repeated_prefix() -> None:
    previous = "vamos começar a reunião agora"
    current = "reunião agora e depois o café"
    assert strip_overlap(previous, current) == "e depois o café"


def test_strip_overlap_empty() -> None:
    assert strip_overlap("", "olá") == "olá"
    assert strip_overlap("olá", "") == ""
