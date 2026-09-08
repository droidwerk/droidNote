from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from app.api.v1.deps import get_container
from app.core.security import verify_token
from app.schemas.api import (
    BootstrapIn,
    DisclaimerIn,
    ModelsCatalogOut,
    SettingsIn,
    SettingsOut,
    SetupComponentOut,
    SetupPlanOut,
    SetupStatusOut,
    TestKeyIn,
    TestKeyOut,
)

router = APIRouter(prefix="/setup", tags=["setup"], dependencies=[Depends(verify_token)])


def _to_out(status) -> SetupStatusOut:
    return SetupStatusOut(
        llm=SetupComponentOut(
            status=status.llm.status,
            progress=status.llm.progress,
            message=status.llm.message,
        ),
        whisper=SetupComponentOut(
            status=status.whisper.status,
            progress=status.whisper.progress,
            message=status.whisper.message,
        ),
        disclaimer_accepted=status.disclaimer_accepted,
        audio_ok=status.audio_ok,
        capture_ready=status.capture_ready,
        summarize_ready=status.summarize_ready,
        audio_message=status.audio_message,
        provider=status.provider,
        ram_gb=status.ram_gb,
        suggested_note_model=status.suggested_note_model,
        suggested_whisper_model=status.suggested_whisper_model,
        ollama_binary=status.ollama_binary,
        save_recordings=status.save_recordings,
        disclaimer_kind=status.disclaimer_kind,
        setup_complete=status.setup_complete,
    )


@router.get("/status", response_model=SetupStatusOut)
async def setup_status(request: Request) -> SetupStatusOut:
    status = await get_container(request.app).setup.status()
    return _to_out(status)


@router.get("/plan", response_model=SetupPlanOut)
async def setup_plan(request: Request) -> SetupPlanOut:
    plan = await get_container(request.app).setup.plan()
    return SetupPlanOut.model_validate(plan)


@router.post("/disclaimer", response_model=SetupStatusOut)
async def accept_disclaimer(payload: DisclaimerIn, request: Request) -> SetupStatusOut:
    if payload.accepted:
        await get_container(request.app).setup.accept_disclaimer(payload.kind)
    status = await get_container(request.app).setup.status()
    return _to_out(status)


@router.post("/bootstrap", response_model=SetupStatusOut)
async def bootstrap(request: Request) -> SetupStatusOut:
    raw = (await request.body()).strip()
    payload = BootstrapIn.model_validate_json(raw) if raw else BootstrapIn()
    await get_container(request.app).setup.start_bootstrap(payload)
    status = await get_container(request.app).setup.status()
    return _to_out(status)


@router.get("/settings", response_model=SettingsOut)
async def get_settings(request: Request) -> SettingsOut:
    return await get_container(request.app).setup.settings_out()


@router.put("/settings", response_model=SettingsOut)
async def put_settings(payload: SettingsIn, request: Request) -> SettingsOut:
    container = get_container(request.app)
    try:
        await container.setup.apply_settings(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    self_id = payload.self_person_id
    if self_id is not None and container.capture.state.recording:
        container.capture.set_self_person(self_id or None)
    return await container.setup.settings_out()


@router.post("/test-key", response_model=TestKeyOut)
async def test_key(payload: TestKeyIn, request: Request) -> TestKeyOut:
    ok, message = await get_container(request.app).setup.test_api_key(payload.asr_api_key)
    return TestKeyOut(ok=ok, message=message)


@router.get("/models", response_model=ModelsCatalogOut)
async def list_models(request: Request) -> ModelsCatalogOut:
    catalog = await get_container(request.app).setup.list_models()
    return ModelsCatalogOut.model_validate(catalog)


@router.get("/diagnostics")
async def diagnostics(request: Request) -> FileResponse:
    path = get_container(request.app).setup.export_diagnostics()
    return FileResponse(
        path,
        filename="DroidNote-diagnostico.zip",
        media_type="application/zip",
        background=BackgroundTask(path.unlink, missing_ok=True),
    )
