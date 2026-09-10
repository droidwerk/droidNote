from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.domain.models import Chat, ChatCitation, ChatMessage, Person, Session, Summary, Tag, TranscriptSegment


class HealthOut(BaseModel):
    status: Literal["ok"]
    capture: Literal["idle", "recording"]
    whisper_loaded: bool
    llm_ready: bool
    whisper_device: str = "cpu"


class DeviceOut(BaseModel):
    id: str
    name: str
    kind: str
    recommended: bool = False


class CaptureStartIn(BaseModel):
    microphone_id: str | None = None
    loopback_id: str | None = None
    mic_only: bool = False
    title: str | None = None
    participant_ids: list[str] = Field(default_factory=list)
    capture_mode: Literal["dictation", "lecture", "meeting"] = "meeting"


class CaptureStateOut(BaseModel):
    recording: bool
    session_id: str | None = None
    mic_only: bool = False
    warning: str | None = None
    phase: str = "idle"
    loopback_name: str | None = None
    started_at: datetime | None = None


class ActionItemOut(BaseModel):
    text: str
    owner: str | None = None
    due: str | None = None


class SummaryTopicOut(BaseModel):
    title: str
    points: list[str] = Field(default_factory=list)


class TagOut(BaseModel):
    id: str
    name: str

    @classmethod
    def from_domain(cls, tag: Tag) -> TagOut:
        return cls(id=tag.id, name=tag.name)


class TagIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)


class SessionTagsIn(BaseModel):
    tag_ids: list[str] = Field(default_factory=list)


class SessionOut(BaseModel):
    id: str
    title: str
    started_at: datetime
    ended_at: datetime | None
    status: Literal["recording", "stopped"]
    language: str | None = None
    duration_ms: int = 0
    capture_mode: Literal["dictation", "lecture", "meeting"] = "meeting"
    tags: list[TagOut] = Field(default_factory=list)
    has_audio: bool = False

    @classmethod
    def from_domain(
        cls,
        session: Session,
        *,
        tags: list[Tag] | None = None,
        has_audio: bool = False,
    ) -> SessionOut:
        end = session.ended_at or datetime.now(tz=session.started_at.tzinfo)
        duration = int((end - session.started_at).total_seconds() * 1000)
        return cls(
            id=session.id,
            title=session.title,
            started_at=session.started_at,
            ended_at=session.ended_at,
            status=session.status,
            language=session.language,
            duration_ms=max(duration, 0),
            capture_mode=session.capture_mode,
            tags=[TagOut.from_domain(item) for item in tags or []],
            has_audio=has_audio,
        )


class SegmentOut(BaseModel):
    id: str
    session_id: str
    start_ms: int
    end_ms: int
    text: str
    language: str | None = None
    speaker_id: str | None = None
    speaker_name: str | None = None
    source: str | None = None

    @classmethod
    def from_domain(
        cls,
        segment: TranscriptSegment,
        names: dict[str, str] | None = None,
    ) -> SegmentOut:
        speaker_name = None
        if segment.speaker_id and names:
            speaker_name = names.get(segment.speaker_id)
        return cls(
            id=segment.id,
            session_id=segment.session_id,
            start_ms=segment.start_ms,
            end_ms=segment.end_ms,
            text=segment.text,
            language=segment.language,
            speaker_id=segment.speaker_id,
            speaker_name=speaker_name,
            source=segment.source,
        )


class SummaryOut(BaseModel):
    id: str
    session_id: str
    overview: str = ""
    topics: list[SummaryTopicOut] = Field(default_factory=list)
    highlights: list[str]
    decisions: list[str]
    action_items: list[ActionItemOut]
    open_items: list[str] = Field(default_factory=list)
    language: str | None = None
    raw_text: str
    created_at: datetime
    notes_markdown: str = ""

    @classmethod
    def from_domain(cls, summary: Summary) -> SummaryOut:
        return cls(
            id=summary.id,
            session_id=summary.session_id,
            overview=summary.overview,
            topics=[
                SummaryTopicOut(title=topic.title, points=topic.points)
                for topic in summary.topics
            ],
            highlights=summary.highlights,
            decisions=summary.decisions,
            action_items=[
                ActionItemOut(text=item.text, owner=item.owner, due=item.due)
                for item in summary.action_items
            ],
            open_items=summary.open_items,
            language=summary.language,
            raw_text=summary.raw_text,
            created_at=summary.created_at,
            notes_markdown=summary.notes_markdown,
        )


class PersonOut(BaseModel):
    id: str
    name: str

    @classmethod
    def from_domain(cls, person: Person) -> PersonOut:
        return cls(id=person.id, name=person.name)


class SessionDetailOut(BaseModel):
    session: SessionOut
    segments: list[SegmentOut]
    summary: SummaryOut | None = None
    participants: list[PersonOut] = Field(default_factory=list)


class SessionUpdateIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class NoteUpdateIn(BaseModel):
    notes_markdown: str = Field(default="", max_length=200_000)


class SearchOut(BaseModel):
    query: str
    segments: list[SegmentOut]


class SetupComponentOut(BaseModel):
    status: Literal["missing", "downloading", "installing", "ready", "error"]
    progress: int
    message: str


class SetupStatusOut(BaseModel):
    llm: SetupComponentOut
    whisper: SetupComponentOut
    disclaimer_accepted: bool
    audio_ok: bool
    capture_ready: bool
    summarize_ready: bool
    audio_message: str = ""
    provider: str = "neste_pc"
    ram_gb: float = 0.0
    suggested_note_model: str = ""
    suggested_whisper_model: str = ""
    ollama_binary: bool = False
    save_recordings: bool = True
    disclaimer_kind: str = "local"
    setup_complete: bool = False


class DisclaimerIn(BaseModel):
    accepted: bool = True
    kind: Literal["local", "openai"] = "local"


class BootstrapIn(BaseModel):
    provider: str | None = None
    ollama_model: str | None = None
    whisper_model: str | None = None
    save_recordings: bool | None = None


class SetupPlanOut(BaseModel):
    ram_gb: float
    suggested_note_model: str
    suggested_whisper_model: str
    ollama_binary: bool
    ollama_online: bool
    current_note_model: str
    current_whisper_model: str
    provider: str
    whisper: list["ModelOptionOut"]
    ollama: list["ModelOptionOut"]
    asr_cloud: list["ModelOptionOut"] = Field(default_factory=list)
    llm_cloud: list["ModelOptionOut"] = Field(default_factory=list)
    save_recordings: bool = True
    vram_gb: float = 0.0
    free_disk_gb: float = 0.0
    download_gb: float = 0.0
    required_disk_gb: float = 0.0
    disk_ok: bool = True
    disk_margin: float = 1.2
    whisper_download_gb: dict[str, float] = Field(default_factory=dict)
    ollama_download_gb: dict[str, float] = Field(default_factory=dict)
    ollama_installer_gb: float = 0.0


class SettingsOut(BaseModel):
    whisper_model: str
    ollama_model: str
    mic_only_default: bool = False
    whisper_device: str = "auto"
    provider: str = "neste_pc"
    asr_cloud_model: str = "whisper-1"
    llm_cloud_model: str = "gpt-4o-mini"
    has_api_key: bool = False
    api_key_hint: str = ""
    language: str = "pt"
    ui_language: str = "pt"
    data_dir: str = ""
    recordings_dir: str = ""
    self_person_id: str = ""
    save_recordings: bool = True
    openai_disclaimer_accepted: bool = False
    disclaimer_kind: str = "local"


class SettingsIn(BaseModel):
    whisper_model: str | None = None
    ollama_model: str | None = None
    mic_only_default: bool | None = None
    whisper_device: str | None = None
    provider: str | None = None
    asr_cloud_model: str | None = None
    llm_cloud_model: str | None = None
    asr_api_key: str | None = None
    language: str | None = None
    ui_language: str | None = None
    recordings_dir: str | None = None
    self_person_id: str | None = None
    save_recordings: bool | None = None
    openai_disclaimer_accepted: bool | None = None


class TestKeyIn(BaseModel):
    asr_api_key: str | None = None


class TestKeyOut(BaseModel):
    ok: bool
    message: str


class PersonIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class ParticipantsIn(BaseModel):
    person_ids: list[str] = Field(default_factory=list)


class SegmentSpeakerIn(BaseModel):
    speaker_id: str | None = None
    name: str | None = None
    text: str | None = None
    apply_forward: bool = True


class ModelOptionOut(BaseModel):
    id: str
    label: str
    installed: bool = False
    source: Literal["whisper", "ollama", "openai"]
    detail: str = ""
    recommended: bool = False
    learn_more: str = ""


class ModelsCatalogOut(BaseModel):
    whisper: list[ModelOptionOut]
    ollama: list[ModelOptionOut]
    asr_cloud: list[ModelOptionOut] = Field(default_factory=list)
    llm_cloud: list[ModelOptionOut] = Field(default_factory=list)
    ollama_online: bool = False


class ChatAskIn(BaseModel):
    message: str = Field(min_length=1, max_length=8_000)
    chat_id: str | None = None
    session_id: str | None = None
    segment_ids: list[str] = Field(default_factory=list)
    # Idioma da interface: manda no idioma da resposta, independente do idioma
    # da transcrição. Vem do cliente para não depender de settings desatualizado.
    ui_language: str | None = None


class ChatCitationOut(BaseModel):
    session_id: str
    session_title: str
    segment_id: str | None = None
    start_ms: int = 0
    excerpt: str = ""

    @classmethod
    def from_domain(cls, item: ChatCitation) -> ChatCitationOut:
        return cls(
            session_id=item.session_id,
            session_title=item.session_title,
            segment_id=item.segment_id,
            start_ms=item.start_ms,
            excerpt=item.excerpt,
        )


class ChatMessageOut(BaseModel):
    id: str
    chat_id: str
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime
    citations: list[ChatCitationOut] = Field(default_factory=list)

    @classmethod
    def from_domain(cls, message: ChatMessage) -> ChatMessageOut:
        return cls(
            id=message.id,
            chat_id=message.chat_id,
            role=message.role,
            content=message.content,
            created_at=message.created_at,
            citations=[ChatCitationOut.from_domain(item) for item in message.citations],
        )


class ChatOut(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    focus_session_id: str | None = None

    @classmethod
    def from_domain(cls, chat: Chat) -> ChatOut:
        return cls(
            id=chat.id,
            title=chat.title,
            created_at=chat.created_at,
            updated_at=chat.updated_at,
            focus_session_id=chat.focus_session_id,
        )


class ChatDetailOut(BaseModel):
    chat: ChatOut
    messages: list[ChatMessageOut]
