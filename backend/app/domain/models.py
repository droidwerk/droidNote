from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

SessionStatus = Literal["recording", "stopped"]
CaptureMode = Literal["dictation", "lecture", "meeting"]
DisclaimerKind = Literal["local", "openai"]


@dataclass(frozen=True)
class ActionItem:
    text: str
    owner: str | None = None
    due: str | None = None


@dataclass(frozen=True)
class SummaryTopic:
    title: str
    points: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Person:
    id: str
    name: str


@dataclass(frozen=True)
class Tag:
    id: str
    name: str


@dataclass(frozen=True)
class Session:
    id: str
    title: str
    started_at: datetime
    ended_at: datetime | None
    status: SessionStatus
    language: str | None = None
    capture_mode: CaptureMode = "meeting"


@dataclass(frozen=True)
class TranscriptSegment:
    id: str
    session_id: str
    start_ms: int
    end_ms: int
    text: str
    language: str | None = None
    speaker_id: str | None = None
    source: str | None = None


@dataclass(frozen=True)
class Summary:
    id: str
    session_id: str
    highlights: list[str]
    decisions: list[str]
    action_items: list[ActionItem]
    raw_text: str
    created_at: datetime
    overview: str = ""
    topics: list[SummaryTopic] = field(default_factory=list)
    open_items: list[str] = field(default_factory=list)
    language: str | None = None
    notes_markdown: str = ""


@dataclass
class AudioChunk:
    samples: list[float]
    sample_rate: int
    timestamp_ms: int
    mic: list[float] | None = None
    loopback: list[float] | None = None


@dataclass
class SetupComponentStatus:
    status: Literal["missing", "downloading", "installing", "ready", "error"] = "missing"
    progress: int = 0
    message: str = ""


@dataclass
class SetupStatus:
    llm: SetupComponentStatus = field(default_factory=SetupComponentStatus)
    whisper: SetupComponentStatus = field(default_factory=SetupComponentStatus)
    disclaimer_accepted: bool = False
    audio_ok: bool = False
    capture_ready: bool = False
    summarize_ready: bool = False
    audio_message: str = ""
    provider: str = "neste_pc"
    ram_gb: float = 0.0
    suggested_note_model: str = ""
    suggested_whisper_model: str = ""
    ollama_binary: bool = False
    save_recordings: bool = True
    disclaimer_kind: str = "local"
    setup_complete: bool = False
