from __future__ import annotations

import numpy as np

from app.infrastructure.asr.scene import SCENE_MUSIC, annotate_transcript


def test_annotate_keeps_spoken_text() -> None:
    loud = np.full(1600, 0.2, dtype=np.float32).tolist()
    assert annotate_transcript("  olá  ", loud) == "olá"


def test_annotate_marks_loud_empty_as_music() -> None:
    loud = np.full(1600, 0.2, dtype=np.float32).tolist()
    assert annotate_transcript("", loud) == SCENE_MUSIC


def test_annotate_ignores_silence() -> None:
    quiet = np.zeros(1600, dtype=np.float32).tolist()
    assert annotate_transcript("", quiet) == ""
