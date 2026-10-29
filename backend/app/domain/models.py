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
    template_id: str | None = None
    # A retenção apagou a fala desta sessão; ata, notas e tarefas continuam.
    transcript_purged_at: datetime | None = None


@dataclass(frozen=True)
class TaskItem:
    """Tarefa da central: nasce de uma ata (origin "ai") ou digitada (origin "manual")."""

    id: str
    text: str
    created_at: datetime
    session_id: str | None = None
    owner: str | None = None
    due: str | None = None
    done: bool = False
    done_at: datetime | None = None
    origin: Literal["ai", "manual"] = "ai"


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
    # Voz detectada pelo motor de voz ("v1", "v2"…), independente de ter nome.
    speaker_cluster: str | None = None
    speaker_confidence: float | None = None
    # Rótulo escolhido à mão neste trecho: o reagrupamento automático não mexe.
    speaker_locked: bool = False


@dataclass(frozen=True)
class UserNote:
    """Anotação que a pessoa digitou durante a gravação, presa ao momento da fala."""

    id: str
    session_id: str
    at_ms: int
    text: str
    created_at: datetime
    # decision, task, important, question — ou None para anotação livre.
    kind: str | None = None
    # O que a IA encontrou na fala em volta deste momento (preenchido pela ata).
    ai_context: str | None = None


NOTE_KINDS = ("decision", "task", "important", "question")


@dataclass(frozen=True)
class NoteTemplate:
    """Template de nota (kind "note") ou receita do chat (kind "recipe")."""

    id: str
    kind: Literal["note", "recipe"]
    name: str
    body: str
    capture_mode: str | None = None
    builtin: bool = False
    position: int = 0


@dataclass(frozen=True)
class SessionVoice:
    cluster: str
    index: int
    person_id: str | None
    talk_ms: int
    segments: int
    first_ms: int
    sources: tuple[str, ...] = ()
    confidence: float = 0.0


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


@dataclass(frozen=True)
class ChatCitation:
    session_id: str
    session_title: str
    segment_id: str | None = None
    start_ms: int = 0
    excerpt: str = ""
    # Citação de documento anexado ao chat (session_id fica vazio).
    document_id: str | None = None
    document_name: str = ""
    page: int | None = None


@dataclass(frozen=True)
class ChatDocument:
    """Documento enviado para o chat (PDF, Word, Excel…), já lido e fatiado em trechos."""

    id: str
    name: str
    kind: str
    size: int
    pages: int
    chunks: int
    chars: int
    created_at: datetime
    chat_id: str | None = None
    # Material de apoio de uma reunião ou aula (pauta, slides, contrato): a ata e o chat usam.
    session_id: str | None = None


@dataclass(frozen=True)
class DocumentChunk:
    document_id: str
    ord: int
    text: str
    page: int | None = None


@dataclass(frozen=True)
class ChatMessage:
    id: str
    chat_id: str
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime
    citations: list[ChatCitation] = field(default_factory=list)


@dataclass(frozen=True)
class Chat:
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    focus_session_id: str | None = None


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
    voice: SetupComponentStatus = field(default_factory=SetupComponentStatus)
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
