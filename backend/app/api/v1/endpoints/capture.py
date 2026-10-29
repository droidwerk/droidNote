from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.v1.deps import AppContainer, get_container
from app.core.i18n import ui_message
from app.core.logging import get_logger
from app.core.security import verify_token
from app.schemas.api import CaptureStartIn, CaptureStateOut, DeviceOut

router = APIRouter(prefix="/capture", tags=["capture"], dependencies=[Depends(verify_token)])
log = get_logger("capture.api")


@router.get("/devices", response_model=list[DeviceOut])
async def list_devices(request: Request) -> list[DeviceOut]:
    container = get_container(request.app)
    raw = container.capture.list_devices()
    return [
        DeviceOut(
            id=item["id"],
            name=item["name"],
            kind=item["kind"],
            recommended=str(item.get("recommended") or "").lower() in {"1", "true", "yes"},
        )
        for item in raw
    ]


def _state_out(state) -> CaptureStateOut:
    return CaptureStateOut(
        recording=state.recording,
        session_id=state.session_id,
        mic_only=state.mic_only,
        warning=state.warning,
        phase=getattr(state, "phase", "idle"),
        loopback_name=getattr(state, "loopback_name", None),
        started_at=getattr(state, "started_at", None),
    )


@router.get("/state", response_model=CaptureStateOut)
async def capture_state(request: Request) -> CaptureStateOut:
    return _state_out(get_container(request.app).capture.state)


@router.post("/start", response_model=CaptureStateOut)
async def start_capture(payload: CaptureStartIn, request: Request) -> CaptureStateOut:
    container = get_container(request.app)
    setup = await container.setup.status()
    if not setup.capture_ready:
        detail = setup.whisper.message or ui_message(container.settings.ui_language, "asr_not_ready")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
    try:
        state = await container.capture.start(
            microphone_id=payload.microphone_id,
            loopback_id=payload.loopback_id,
            mic_only=payload.mic_only,
            title=payload.title,
            participant_ids=payload.participant_ids,
            capture_mode=payload.capture_mode,
            template_id=payload.template_id,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    return _state_out(state)


@router.post("/stop", response_model=CaptureStateOut)
async def stop_capture(request: Request) -> CaptureStateOut:
    container = get_container(request.app)
    session_id = container.capture.state.session_id
    try:
        state = await container.capture.stop()
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    if session_id:
        asyncio.create_task(finish_session(container, session_id))
    return _state_out(state)


@router.get("/meeting")
async def meeting_status(request: Request) -> dict[str, object]:
    watcher = get_container(request.app).meetings
    if watcher is None:
        return {"available": False, "active": False}
    return watcher.status()


@router.post("/meeting/dismiss")
async def dismiss_meeting(request: Request) -> dict[str, object]:
    watcher = get_container(request.app).meetings
    if watcher is None:
        return {"available": False, "active": False}
    await watcher.dismiss()
    return watcher.status()


async def finish_session(container: AppContainer, session_id: str) -> None:
    """Pós-gravação: esvazia a fila, reagrupa vozes e atribui falantes."""
    await container.capture.wait_drain(session_id)
    try:
        await container.bus.publish(
            {"type": "speakers", "status": "start", "session_id": session_id}
        )
        voices = container.voices
        if voices is not None and voices.is_live(session_id):
            await voices.finish(session_id)
        await container.speakers.assign_from_context(session_id)
    except Exception:
        log.exception("speaker assign after stop failed session=%s", session_id)
    finally:
        await container.bus.publish(
            {"type": "speakers", "status": "done", "session_id": session_id}
        )
    await auto_summarize(container, session_id)


async def compare_memory(container: AppContainer, session_id: str) -> None:
    """Ata pronta: a memória da série ("o que mudou desde a última vez") sai logo depois."""
    memory = container.memory
    if memory is None:
        return
    try:
        result = await memory.recall(session_id)
        if result.mode != "after" or result.generated and not result.stale:
            return
        await container.bus.publish({"type": "memory", "status": "start", "session_id": session_id})
        await memory.compare(session_id)
        await container.bus.publish({"type": "memory", "status": "done", "session_id": session_id})
    except Exception:
        log.exception("memory compare failed session=%s", session_id)
        await container.bus.publish({"type": "memory", "status": "error", "session_id": session_id})


async def auto_summarize(container: AppContainer, session_id: str) -> None:
    """Gravação terminou: a ata sai sozinha, sem a pessoa precisar pedir."""
    if (await container.store.get_setting("auto_summary")) == "0":
        return
    if not await container.store.list_segments(session_id):
        return
    if await container.store.get_summary(session_id) is not None:
        return
    status = await container.setup.status()
    if not status.summarize_ready:
        await container.bus.publish(
            {"type": "summary", "status": "skipped", "reason": "engine", "session_id": session_id}
        )
        return
    await container.bus.publish({"type": "summary", "status": "start", "session_id": session_id})
    try:
        await container.summarize.summarize(session_id)
    except Exception:
        log.exception("auto summary failed session=%s", session_id)
        await container.bus.publish({"type": "summary", "status": "error", "session_id": session_id})
        return
    await compare_memory(container, session_id)
    await container.bus.publish({"type": "summary", "status": "done", "session_id": session_id})
    await container.bus.publish({"type": "tasks", "session_id": session_id})
