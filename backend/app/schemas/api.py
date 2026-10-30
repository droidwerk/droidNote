from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.domain.models import (
    Chat,
    ChatCitation,
    ChatDocument,
    ChatMessage,
    NoteTemplate,
    Person,
    Session,
    SessionVoice,
    Summary,
    Tag,
    TaskItem,
    TranscriptSegment,
    UserNote,
)


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
    template_id: str | None = None


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
    template_id: str | None = None
    transcript_purged_at: datetime | None = None

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
            template_id=session.template_id,
            transcript_purged_at=session.transcript_purged_at,
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
    speaker_cluster: str | None = None
    speaker_confidence: float | None = None
    speaker_locked: bool = False

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
            speaker_cluster=segment.speaker_cluster,
            speaker_confidence=segment.speaker_confidence,
            speaker_locked=segment.speaker_locked,
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
    has_voiceprint: bool = False

    @classmethod
    def from_domain(cls, person: Person, *, has_voiceprint: bool = False) -> PersonOut:
        return cls(id=person.id, name=person.name, has_voiceprint=has_voiceprint)


class VoiceOut(BaseModel):
    cluster: str
    index: int
    person_id: str | None = None
    person_name: str | None = None
    talk_ms: int = 0
    share: float = 0.0
    segments: int = 0
    first_ms: int = 0
    sources: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    has_voiceprint: bool = False

    @classmethod
    def from_domain(
        cls,
        voice: SessionVoice,
        *,
        names: dict[str, str],
        total_ms: int,
        printed: set[str],
    ) -> VoiceOut:
        return cls(
            cluster=voice.cluster,
            index=voice.index,
            person_id=voice.person_id,
            person_name=names.get(voice.person_id or ""),
            talk_ms=voice.talk_ms,
            share=round(voice.talk_ms / total_ms, 4) if total_ms else 0.0,
            segments=voice.segments,
            first_ms=voice.first_ms,
            sources=list(voice.sources),
            confidence=voice.confidence,
            has_voiceprint=bool(voice.person_id and voice.person_id in printed),
        )


class VoicesOut(BaseModel):
    engine_ready: bool
    model: str = ""
    live: bool = False
    voices: list[VoiceOut] = Field(default_factory=list)
    segments: list[SegmentOut] = Field(default_factory=list)


NoteKind = Literal["decision", "task", "important", "question"]


class UserNoteIn(BaseModel):
    text: str = Field(min_length=1, max_length=4_000)
    at_ms: int | None = Field(default=None, ge=0)
    kind: NoteKind | None = None


class UserNoteUpdateIn(BaseModel):
    text: str | None = Field(default=None, min_length=1, max_length=4_000)
    kind: NoteKind | None = None


class UserNoteOut(BaseModel):
    id: str
    session_id: str
    at_ms: int
    text: str
    created_at: datetime
    kind: NoteKind | None = None
    ai_context: str | None = None

    @classmethod
    def from_domain(cls, note: UserNote) -> UserNoteOut:
        kind = note.kind if note.kind in {"decision", "task", "important", "question"} else None
        return cls(
            id=note.id,
            session_id=note.session_id,
            at_ms=note.at_ms,
            text=note.text,
            created_at=note.created_at,
            kind=kind,  # type: ignore[arg-type]
            ai_context=note.ai_context,
        )


class NoteExpandOut(BaseModel):
    text: str


class TemplateIn(BaseModel):
    kind: Literal["note", "recipe"] = "note"
    name: str = Field(min_length=1, max_length=80)
    body: str = Field(min_length=1, max_length=6_000)
    capture_mode: Literal["dictation", "lecture", "meeting"] | None = None


class TemplateUpdateIn(BaseModel):
    name: str | None = Field(default=None, max_length=80)
    body: str | None = Field(default=None, max_length=6_000)
    capture_mode: Literal["dictation", "lecture", "meeting"] | None = None


class TemplateOut(BaseModel):
    id: str
    kind: Literal["note", "recipe"]
    name: str
    body: str
    capture_mode: str | None = None
    builtin: bool = False

    @classmethod
    def from_domain(cls, template: NoteTemplate) -> TemplateOut:
        return cls(
            id=template.id,
            kind=template.kind,
            name=template.name,
            body=template.body,
            capture_mode=template.capture_mode,
            builtin=template.builtin,
        )


class TaskOut(BaseModel):
    id: str
    text: str
    owner: str | None = None
    due: str | None = None
    done: bool = False
    done_at: datetime | None = None
    origin: Literal["ai", "manual"] = "ai"
    created_at: datetime
    session_id: str | None = None
    session_title: str | None = None
    session_started_at: datetime | None = None

    @classmethod
    def from_domain(cls, task: TaskItem, session: Session | None = None) -> TaskOut:
        return cls(
            id=task.id,
            text=task.text,
            owner=task.owner,
            due=task.due,
            done=task.done,
            done_at=task.done_at,
            origin=task.origin,
            created_at=task.created_at,
            session_id=task.session_id,
            session_title=session.title if session else None,
            session_started_at=session.started_at if session else None,
        )


class TaskIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    owner: str | None = Field(default=None, max_length=80)
    due: str | None = Field(default=None, max_length=40)
    session_id: str | None = None


class TaskUpdateIn(BaseModel):
    text: str | None = Field(default=None, max_length=500)
    owner: str | None = Field(default=None, max_length=80)
    due: str | None = Field(default=None, max_length=40)
    done: bool | None = None


class BriefSessionOut(BaseModel):
    session_id: str
    title: str
    started_at: datetime
    reason: Literal["title", "people", "both"]
    overview: str = ""
    decisions: list[str] = Field(default_factory=list)
    open_items: list[str] = Field(default_factory=list)
    tasks: list[TaskOut] = Field(default_factory=list)


class BriefOut(BaseModel):
    title: str
    people: list[str] = Field(default_factory=list)
    related: list[BriefSessionOut] = Field(default_factory=list)
    pending: list[TaskOut] = Field(default_factory=list)


class CalendarEventOut(BaseModel):
    uid: str
    title: str
    start: datetime
    end: datetime
    location: str | None = None
    attendees: list[str] = Field(default_factory=list)
    brief: BriefOut


class UpcomingOut(BaseModel):
    configured: bool
    error: str | None = None
    events: list[CalendarEventOut] = Field(default_factory=list)


class CalendarTestIn(BaseModel):
    url: str = Field(min_length=8, max_length=2048)


class CalendarTestOut(BaseModel):
    ok: bool
    events: int = 0
    error: str | None = None


class RetentionOut(BaseModel):
    audio_files: int
    transcripts: int
    audio_days: int
    transcript_days: int


class VoiceAssignIn(BaseModel):
    person_id: str | None = None
    name: str | None = Field(default=None, max_length=80)


class MindMapOut(BaseModel):
    session_id: str
    origin: Literal["auto", "edited", "ai"]
    summary_id: str | None = None
    updated_at: datetime
    data: dict[str, Any]
    markdown: str = ""


class MindMapIn(BaseModel):
    data: dict[str, Any]


class MemoryThreadOut(BaseModel):
    session_id: str
    title: str
    started_at: datetime
    reason: Literal["title", "people", "both"]
    has_summary: bool = False
    decisions: list[str] = Field(default_factory=list)
    open_items: list[str] = Field(default_factory=list)


class MemoryResolvedOut(BaseModel):
    item: str
    how: str = ""
    task_id: str | None = None


class MemoryChangeOut(BaseModel):
    before: str
    now: str


class MemoryOut(BaseModel):
    session_id: str
    mode: Literal["before", "after"]
    generated: bool
    stale: bool = False
    language: str | None = None
    created_at: datetime | None = None
    thread: list[MemoryThreadOut] = Field(default_factory=list)
    resolved: list[MemoryResolvedOut] = Field(default_factory=list)
    still_open: list[str] = Field(default_factory=list)
    changed: list[MemoryChangeOut] = Field(default_factory=list)
    new_items: list[str] = Field(default_factory=list)
    watch: list[str] = Field(default_factory=list)
    pending: list[TaskOut] = Field(default_factory=list)


class SessionDetailOut(BaseModel):
    session: SessionOut
    segments: list[SegmentOut]
    summary: SummaryOut | None = None
    participants: list[PersonOut] = Field(default_factory=list)


class SessionUpdateIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class NoteUpdateIn(BaseModel):
    notes_markdown: str = Field(default="", max_length=200_000)


class NoteHitOut(BaseModel):
    id: str
    session_id: str
    at_ms: int
    text: str
    kind: str | None = None


class SummaryHitOut(BaseModel):
    session_id: str
    excerpt: str


class TaskHitOut(BaseModel):
    id: str
    session_id: str | None = None
    text: str
    done: bool


class SearchOut(BaseModel):
    query: str
    segments: list[SegmentOut]
    notes: list[NoteHitOut] = []
    summaries: list[SummaryHitOut] = []
    tasks: list[TaskHitOut] = []


class SetupComponentOut(BaseModel):
    status: Literal["missing", "downloading", "installing", "ready", "error"]
    progress: int
    message: str


class SetupStatusOut(BaseModel):
    llm: SetupComponentOut
    whisper: SetupComponentOut
    voice: SetupComponentOut | None = None
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
    total_ram_gb: float = 0.0
    free_ram_gb: float = 0.0
    gpu_name: str = ""
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
    asr_cloud_model: str = "gpt-transcribe"
    llm_cloud_model: str = "gpt-6-luna"
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
    meeting_detection: str = "ask"
    has_calendar: bool = False
    calendar_hint: str = ""
    consent_message: str = ""
    retention_audio_days: int = 0
    retention_transcript_days: int = 0
    auto_gain: bool = True
    auto_summary: bool = True


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
    meeting_detection: str | None = None
    # "" desliga o calendário.
    calendar_ics_url: str | None = Field(default=None, max_length=2048)
    consent_message: str | None = Field(default=None, max_length=2000)
    retention_audio_days: int | None = Field(default=None, ge=0, le=3650)
    retention_transcript_days: int | None = Field(default=None, ge=0, le=3650)
    auto_gain: bool | None = None
    auto_summary: bool | None = None


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
    document_ids: list[str] = Field(default_factory=list, max_length=10)
    # Idioma da interface: manda no idioma da resposta, independente do idioma
    # da transcrição. Vem do cliente para não depender de settings desatualizado.
    ui_language: str | None = None


class ChatCitationOut(BaseModel):
    session_id: str
    session_title: str
    segment_id: str | None = None
    start_ms: int = 0
    excerpt: str = ""
    document_id: str | None = None
    document_name: str = ""
    page: int | None = None

    @classmethod
    def from_domain(cls, item: ChatCitation) -> ChatCitationOut:
        return cls(
            session_id=item.session_id,
            session_title=item.session_title,
            segment_id=item.segment_id,
            start_ms=item.start_ms,
            excerpt=item.excerpt,
            document_id=item.document_id,
            document_name=item.document_name,
            page=item.page,
        )


class DocumentOut(BaseModel):
    id: str
    name: str
    kind: str
    size: int
    pages: int
    chunks: int
    chars: int
    created_at: datetime
    chat_id: str | None = None
    session_id: str | None = None

    @classmethod
    def from_domain(cls, item: ChatDocument) -> DocumentOut:
        return cls(
            id=item.id,
            name=item.name,
            kind=item.kind,
            size=item.size,
            pages=item.pages,
            chunks=item.chunks,
            chars=item.chars,
            created_at=item.created_at,
            chat_id=item.chat_id,
            session_id=item.session_id,
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
