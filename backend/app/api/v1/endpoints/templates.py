from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.api.v1.deps import get_container
from app.application.templates import TemplateService
from app.core.security import verify_token
from app.schemas.api import TemplateIn, TemplateOut, TemplateUpdateIn

router = APIRouter(prefix="/templates", tags=["templates"], dependencies=[Depends(verify_token)])


def _service(request: Request) -> TemplateService:
    container = get_container(request.app)
    return container.templates or TemplateService(container.store)


@router.get("", response_model=list[TemplateOut])
async def list_templates(request: Request, kind: str | None = Query(default=None)) -> list[TemplateOut]:
    return [TemplateOut.from_domain(item) for item in await _service(request).list(kind)]


@router.post("", response_model=TemplateOut, status_code=status.HTTP_201_CREATED)
async def create_template(payload: TemplateIn, request: Request) -> TemplateOut:
    try:
        template = await _service(request).create(
            kind=payload.kind, name=payload.name, body=payload.body, capture_mode=payload.capture_mode
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return TemplateOut.from_domain(template)


@router.patch("/{template_id}", response_model=TemplateOut)
async def update_template(template_id: str, payload: TemplateUpdateIn, request: Request) -> TemplateOut:
    try:
        template = await _service(request).update(
            template_id, name=payload.name, body=payload.body, capture_mode=payload.capture_mode
        )
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="template") from None
    except PermissionError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="builtin") from None
    return TemplateOut.from_domain(template)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(template_id: str, request: Request) -> None:
    try:
        await _service(request).delete(template_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="template") from None
    except PermissionError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="builtin") from None
