from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.v1.deps import get_container
from app.core.security import verify_token
from app.schemas.api import PersonIn, PersonOut

router = APIRouter(prefix="/people", tags=["people"], dependencies=[Depends(verify_token)])


@router.get("", response_model=list[PersonOut])
async def list_people(request: Request) -> list[PersonOut]:
    people = await get_container(request.app).speakers.list_people()
    return [PersonOut.from_domain(item) for item in people]


@router.post("", response_model=PersonOut, status_code=status.HTTP_201_CREATED)
async def create_person(payload: PersonIn, request: Request) -> PersonOut:
    try:
        person = await get_container(request.app).speakers.create_person(payload.name)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return PersonOut.from_domain(person)


@router.delete("/{person_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_person(person_id: str, request: Request) -> None:
    await get_container(request.app).speakers.delete_person(person_id)
