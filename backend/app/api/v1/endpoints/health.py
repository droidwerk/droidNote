from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse

from app.api.v1.deps import get_container
from app.core.security import verify_token
from app.schemas.api import HealthOut

router = APIRouter()


@router.get("/health", response_model=HealthOut)
async def health(request: Request) -> HealthOut:
    container = get_container(request.app)
    llm = await container.llm.status_component()
    return HealthOut(
        status="ok",
        capture="recording" if container.capture.is_recording() else "idle",
        whisper_loaded=container.capture.whisper_loaded(),
        llm_ready=llm.status == "ready",
        whisper_device=container.capture.asr_device,
    )


@router.get("/health/auth", response_model=HealthOut, dependencies=[Depends(verify_token)])
async def health_auth(request: Request) -> HealthOut:
    return await health(request)


@router.get("/ready")
async def ready(request: Request) -> JSONResponse:
    container = get_container(request.app)
    return JSONResponse(
        {
            "host": container.settings.host,
            "port": request.url.port,
            "ok": True,
        },
        status_code=status.HTTP_200_OK,
    )
