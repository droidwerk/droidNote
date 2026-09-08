from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.v1.deps import get_container
from app.core.security import verify_token
from app.schemas.api import TagIn, TagOut

router = APIRouter(prefix="/tags", tags=["tags"], dependencies=[Depends(verify_token)])


@router.get("", response_model=list[TagOut])
async def list_tags(request: Request) -> list[TagOut]:
    tags = await get_container(request.app).store.list_tags()
    return [TagOut.from_domain(item) for item in tags]


@router.post("", response_model=TagOut, status_code=status.HTTP_201_CREATED)
async def create_tag(payload: TagIn, request: Request) -> TagOut:
    try:
        tag = await get_container(request.app).store.create_tag(payload.name)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return TagOut.from_domain(tag)


@router.delete("/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tag(tag_id: str, request: Request) -> None:
    await get_container(request.app).store.delete_tag(tag_id)
