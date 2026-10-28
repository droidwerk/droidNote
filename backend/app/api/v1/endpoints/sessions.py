from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response

from app.api.v1.deps import AppContainer, get_container
from app.application.export import export_docx, export_pdf
from app.application.speakers import UNSET
from app.core.config import session_recording_path
from app.core.i18n import ui_message
from app.core.security import verify_token
from app.domain.models import Session
from app.schemas.api import (
    NoteUpdateIn,
    ParticipantsIn,
    PersonOut,
    SearchOut,
    SegmentOut,
    SegmentSpeakerIn,
    SessionDetailOut,
    SessionOut,
    SessionTagsIn,
    SessionUpdateIn,
    SummaryOut,
    TagOut,
    UserNoteIn,
    UserNoteOut,
    UserNoteUpdateIn,
    VoiceAssignIn,
    VoiceOut,
    VoicesOut,
)

router = APIRouter(prefix="/sessions", tags=["sessions"], dependencies=[Depends(verify_token)])
_SAFE_NAME = re.compile(r"[^\w\s.-]+", re.UNICODE)


def _missing(request: Request | None = None) -> HTTPException:
    locale = "pt"
    if request is not None:
        locale = get_container(request.app).settings.ui_language
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=ui_message(locale, "session_missing"))


def _download_name(title: str, session_id: str, suffix: str) -> str:
    cleaned = _SAFE_NAME.sub("", title).strip() or session_id
    return f"{cleaned[:80]}{suffix}"


def _audio_ids(container: AppContainer) -> set[str]:
    folder = container.settings.resolve_recordings_dir()
    if not folder.is_dir():
        return set()
    return {path.stem for path in folder.glob("*.wav") if path.is_file() and path.stat().st_size > 44}


async def _session_out(
    container: AppContainer,
    session: Session,
    *,
    tags: list | None = None,
    has_audio: bool | None = None,
) -> SessionOut:
    resolved_tags = tags if tags is not None else await container.store.list_session_tags(session.id)
    audio = _audio_ids(container) if has_audio is None else None
    exists = session.id in audio if audio is not None else bool(has_audio)
    return SessionOut.from_domain(session, tags=resolved_tags, has_audio=exists)


async def _named_segments(request: Request, segments) -> list[SegmentOut]:
    names = await get_container(request.app).speakers.name_map()
    return [SegmentOut.from_domain(item, names) for item in segments]


@router.get("", response_model=list[SessionOut])
async def list_sessions(
    request: Request,
    tag_id: str | None = Query(default=None),
) -> list[SessionOut]:
    container = get_container(request.app)
    sessions = await container.sessions.list_sessions()
    tag_map = await container.store.tags_by_session_ids([item.id for item in sessions])
    audio = _audio_ids(container)
    if tag_id:
        sessions = [item for item in sessions if any(tag.id == tag_id for tag in tag_map.get(item.id, []))]
    return [
        SessionOut.from_domain(
            item,
            tags=tag_map.get(item.id, []),
            has_audio=item.id in audio,
        )
        for item in sessions
    ]


@router.get("/search", response_model=SearchOut)
async def search_all(
    request: Request,
    q: str = Query(min_length=1),
) -> SearchOut:
    segments = await get_container(request.app).sessions.search(q)
    return SearchOut(query=q, segments=await _named_segments(request, segments))


@router.get("/{session_id}", response_model=SessionDetailOut)
async def get_session(session_id: str, request: Request) -> SessionDetailOut:
    container = get_container(request.app)
    try:
        session = await container.sessions.get(session_id)
    except KeyError:
        raise _missing(request) from None
    segments = await container.sessions.segments(session_id)
    summary = await container.store.get_summary(session_id)
    participants = await container.speakers.participants(session_id)
    names = await container.speakers.name_map()
    return SessionDetailOut(
        session=await _session_out(container, session),
        segments=[SegmentOut.from_domain(item, names) for item in segments],
        summary=SummaryOut.from_domain(summary) if summary else None,
        participants=[PersonOut.from_domain(item) for item in participants],
    )


@router.patch("/{session_id}", response_model=SessionOut)
async def rename_session(session_id: str, payload: SessionUpdateIn, request: Request) -> SessionOut:
    container = get_container(request.app)
    try:
        session = await container.sessions.rename(session_id, payload.title)
    except KeyError:
        raise _missing(request) from None
    return await _session_out(container, session)


@router.put("/{session_id}/tags", response_model=list[TagOut])
async def set_session_tags(
    session_id: str,
    payload: SessionTagsIn,
    request: Request,
) -> list[TagOut]:
    container = get_container(request.app)
    try:
        await container.sessions.get(session_id)
    except KeyError:
        raise _missing(request) from None
    tags = await container.store.set_session_tags(session_id, payload.tag_ids)
    return [TagOut.from_domain(item) for item in tags]


@router.put("/{session_id}/note", response_model=SummaryOut)
async def save_note(session_id: str, payload: NoteUpdateIn, request: Request) -> SummaryOut:
    try:
        summary = await get_container(request.app).sessions.save_note(
            session_id, payload.notes_markdown
        )
    except KeyError:
        raise _missing(request) from None
    return SummaryOut.from_domain(summary)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(session_id: str, request: Request) -> None:
    try:
        await get_container(request.app).sessions.delete(session_id)
    except KeyError:
        raise _missing(request) from None


@router.get("/{session_id}/search", response_model=SearchOut)
async def search_session(
    session_id: str,
    request: Request,
    q: str = Query(min_length=1),
) -> SearchOut:
    try:
        await get_container(request.app).sessions.get(session_id)
    except KeyError:
        raise _missing(request) from None
    segments = await get_container(request.app).sessions.search(q, session_id=session_id)
    return SearchOut(query=q, segments=await _named_segments(request, segments))


@router.post("/{session_id}/summarize", response_model=SummaryOut)
async def summarize_session(
    session_id: str,
    request: Request,
    template_id: str | None = Query(default=None),
) -> SummaryOut:
    container = get_container(request.app)
    setup = await container.setup.status()
    if not setup.summarize_ready:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=setup.llm.message or ui_message(container.settings.ui_language, "llm_not_ready"),
        )
    try:
        summary = await container.summarize.summarize(session_id, template_id)
    except KeyError:
        raise _missing(request) from None
    await container.bus.publish({"type": "tasks", "session_id": session_id})
    return SummaryOut.from_domain(summary)


@router.put("/{session_id}/participants", response_model=list[PersonOut])
async def set_participants(
    session_id: str,
    payload: ParticipantsIn,
    request: Request,
) -> list[PersonOut]:
    container = get_container(request.app)
    try:
        await container.sessions.get(session_id)
    except KeyError:
        raise _missing(request) from None
    people = await container.speakers.set_participants(session_id, payload.person_ids)
    if container.capture.state.session_id == session_id:
        await container.capture.set_participants(session_id, payload.person_ids)
    return [PersonOut.from_domain(item) for item in people]


@router.patch("/{session_id}/segments/{segment_id}", response_model=SegmentOut)
async def patch_segment_speaker(
    session_id: str,
    segment_id: str,
    payload: SegmentSpeakerIn,
    request: Request,
) -> SegmentOut:
    container = get_container(request.app)
    speaker_id = payload.speaker_id if "speaker_id" in payload.model_fields_set else UNSET
    apply_forward = payload.apply_forward
    if speaker_id is UNSET and not payload.name:
        apply_forward = False
    voices = container.voices
    current = await container.store.get_segment(segment_id)
    speaker_change = speaker_id is not UNSET or bool(payload.name)
    clustered = bool(current is not None and current.speaker_cluster)
    by_voice = bool(speaker_change and clustered and voices is not None and payload.apply_forward)
    try:
        segment = await container.speakers.patch_segment(
            session_id,
            segment_id,
            speaker_id=speaker_id,
            name=payload.name,
            text=payload.text,
            apply_forward=apply_forward and not clustered,
            lock=speaker_change and not by_voice,
        )
        if by_voice and voices is not None and segment.speaker_cluster:
            # Nomear um trecho nomeia a voz inteira e ensina a impressão vocal.
            await voices.assign(session_id, segment.speaker_cluster, segment.speaker_id)
            refreshed = await container.store.get_segment(segment.id)
            segment = refreshed or segment
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ui_message(get_container(request.app).settings.ui_language, "segment_missing"),
        ) from None
    if container.capture.state.session_id == session_id:
        await container.capture.set_participants(
            session_id,
            [item.id for item in await container.speakers.participants(session_id)],
        )
        container.capture.note_speaker(segment.speaker_id, segment.source)
    names = await container.speakers.name_map()
    return SegmentOut.from_domain(segment, names)


@router.get("/{session_id}/notes", response_model=list[UserNoteOut])
async def list_user_notes(session_id: str, request: Request) -> list[UserNoteOut]:
    container = get_container(request.app)
    try:
        await container.sessions.get(session_id)
    except KeyError:
        raise _missing(request) from None
    return [UserNoteOut.from_domain(item) for item in await container.store.list_user_notes(session_id)]


@router.post("/{session_id}/notes", response_model=UserNoteOut, status_code=status.HTTP_201_CREATED)
async def add_user_note(session_id: str, payload: UserNoteIn, request: Request) -> UserNoteOut:
    from datetime import UTC, datetime

    from app.domain.models import UserNote
    from app.infrastructure.persistence.sqlite import new_id

    container = get_container(request.app)
    try:
        session = await container.sessions.get(session_id)
    except KeyError:
        raise _missing(request) from None
    now = datetime.now(tz=UTC)
    at_ms = payload.at_ms
    if at_ms is None:
        # Sem momento informado: o instante atual da gravação.
        end = session.ended_at or now
        at_ms = max(0, int((min(now, end) - session.started_at).total_seconds() * 1000))
    note = UserNote(id=new_id(), session_id=session_id, at_ms=at_ms, text=payload.text.strip(), created_at=now)
    await container.store.add_user_note(note)
    await container.bus.publish({"type": "note", "status": "added", "session_id": session_id, "note_id": note.id})
    return UserNoteOut.from_domain(note)


@router.patch("/{session_id}/notes/{note_id}", response_model=list[UserNoteOut])
async def update_user_note(session_id: str, note_id: str, payload: UserNoteUpdateIn, request: Request) -> list[UserNoteOut]:
    container = get_container(request.app)
    if not await container.store.update_user_note(session_id, note_id, payload.text.strip()):
        raise _missing(request)
    return [UserNoteOut.from_domain(item) for item in await container.store.list_user_notes(session_id)]


@router.delete("/{session_id}/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_note(session_id: str, note_id: str, request: Request) -> None:
    container = get_container(request.app)
    if not await container.store.delete_user_note(session_id, note_id):
        raise _missing(request)


async def _voices_out(container: AppContainer, session_id: str) -> VoicesOut:
    voices = container.voices
    segments = await container.store.list_segments(session_id)
    names = await container.speakers.name_map()
    printed = await container.store.voiceprint_people()
    summary = await voices.voices(session_id) if voices is not None else []
    total = sum(item.talk_ms for item in summary)
    return VoicesOut(
        engine_ready=bool(voices and voices.available()),
        model=voices.model_id() if voices else "",
        live=bool(voices and voices.is_live(session_id)),
        voices=[
            VoiceOut.from_domain(item, names=names, total_ms=total, printed=printed) for item in summary
        ],
        segments=[SegmentOut.from_domain(item, names) for item in segments],
    )


@router.get("/{session_id}/voices", response_model=VoicesOut)
async def session_voices(session_id: str, request: Request) -> VoicesOut:
    container = get_container(request.app)
    try:
        await container.sessions.get(session_id)
    except KeyError:
        raise _missing(request) from None
    return await _voices_out(container, session_id)


@router.post("/{session_id}/voices/refine", response_model=VoicesOut)
async def refine_voices(session_id: str, request: Request) -> VoicesOut:
    container = get_container(request.app)
    try:
        await container.sessions.get(session_id)
    except KeyError:
        raise _missing(request) from None
    voices = container.voices
    if voices is not None and voices.available():
        await voices.refine(session_id, final=not voices.is_live(session_id))
    return await _voices_out(container, session_id)


@router.put("/{session_id}/voices/{cluster}", response_model=VoicesOut)
async def assign_voice(
    session_id: str,
    cluster: str,
    payload: VoiceAssignIn,
    request: Request,
) -> VoicesOut:
    container = get_container(request.app)
    locale = container.settings.ui_language
    try:
        await container.sessions.get(session_id)
    except KeyError:
        raise _missing(request) from None
    voices = container.voices
    if voices is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=ui_message(locale, "voice_unavailable"))
    segments = await container.store.list_segments(session_id)
    if not any(item.speaker_cluster == cluster for item in segments):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=ui_message(locale, "voice_not_found"))
    person_id = payload.person_id or None
    if payload.name and payload.name.strip():
        person = await container.speakers.create_person(payload.name)
        person_id = person.id
    elif person_id and await container.store.get_person(person_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=ui_message(locale, "voice_not_found"))
    await voices.assign(session_id, cluster, person_id)
    if person_id:
        participants = [item.id for item in await container.speakers.participants(session_id)]
        if person_id not in participants:
            await container.speakers.set_participants(session_id, [*participants, person_id])
        if container.capture.state.session_id == session_id:
            await container.capture.set_participants(
                session_id, [item.id for item in await container.speakers.participants(session_id)]
            )
    return await _voices_out(container, session_id)


@router.post("/{session_id}/speakers/assign", response_model=list[SegmentOut])
async def assign_speakers(session_id: str, request: Request) -> list[SegmentOut]:
    container = get_container(request.app)
    try:
        await container.sessions.get(session_id)
    except KeyError:
        raise _missing(request) from None
    segments = await container.speakers.assign_from_context(session_id)
    names = await container.speakers.name_map()
    return [SegmentOut.from_domain(item, names) for item in segments]


@router.get("/{session_id}/audio")
async def session_audio(session_id: str, request: Request):
    container = get_container(request.app)
    try:
        session = await container.sessions.get(session_id)
    except KeyError:
        raise _missing(request) from None
    path: Path = session_recording_path(container.settings, session.id)
    if not path.is_file() or path.stat().st_size <= 44:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ui_message(container.settings.ui_language, "audio_missing"),
        )
    return FileResponse(
        path,
        media_type="audio/wav",
        filename=_download_name(session.title, session.id, ".wav"),
        headers={"Accept-Ranges": "bytes", "Cache-Control": "private, max-age=60"},
    )


@router.get("/{session_id}/export")
async def export_session(
    session_id: str,
    request: Request,
    format: str = Query(default="markdown", pattern="^(markdown|json|pdf|docx)$"),
):
    container = get_container(request.app)
    try:
        session = await container.sessions.get(session_id)
    except KeyError:
        raise _missing(request) from None
    filename_base = _download_name(session.title, session.id, "")
    locale = container.settings.ui_language
    if format == "markdown":
        content = await container.sessions.export_markdown(session_id, locale)
        return PlainTextResponse(
            content,
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename_base}.md"'},
        )
    if format in {"pdf", "docx"}:
        segments = await container.store.list_segments(session_id)
        summary = await container.store.get_summary(session_id)
        people = await container.store.list_people()
        if format == "pdf":
            payload = export_pdf(session, segments, summary, people, locale)
            return Response(
                content=payload,
                media_type="application/pdf",
                headers={"Content-Disposition": f'attachment; filename="{filename_base}.pdf"'},
            )
        payload = export_docx(session, segments, summary, people, locale)
        return Response(
            content=payload,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="{filename_base}.docx"'},
        )
    detail = await get_session(session_id, request)
    return JSONResponse(
        content=json.loads(detail.model_dump_json()),
        headers={"Content-Disposition": f'attachment; filename="{filename_base}.json"'},
    )
