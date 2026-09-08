from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.v1.deps import AppContainer, get_container
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
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Modelo de transcrição ainda não está pronto",
        )
    try:
        state = await container.capture.start(
            microphone_id=payload.microphone_id,
            loopback_id=payload.loopback_id,
            mic_only=payload.mic_only,
            title=payload.title,
            participant_ids=payload.participant_ids,
            capture_mode=payload.capture_mode,
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
        asyncio.create_task(_assign_after_stop(container, session_id))
    return _state_out(state)


async def _assign_after_stop(container: AppContainer, session_id: str) -> None:
    await container.capture.wait_drain(session_id)
    try:
        await container.bus.publish(
            {"type": "speakers", "status": "start", "session_id": session_id}
        )
        await container.speakers.assign_from_context(session_id)
    except Exception:
        log.exception("speaker assign after stop failed session=%s", session_id)
    finally:
        await container.bus.publish(
            {"type": "speakers", "status": "done", "session_id": session_id}
        )
