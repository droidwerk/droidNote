from __future__ import annotations

from collections.abc import Sequence

from app.infrastructure.asr.vad import rms_level

MUSIC_EMPTY_RMS = 0.012
SCENE_MUSIC = "[música ou áudio sem fala]"


def annotate_transcript(text: str, samples: Sequence[float]) -> str:
    cleaned = (text or "").strip()
    if cleaned:
        return cleaned
    if rms_level(samples) >= MUSIC_EMPTY_RMS:
        return SCENE_MUSIC
    return ""
