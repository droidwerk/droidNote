from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status

from app.api.v1.deps import get_container
from app.application.documents import MAX_BYTES, DocumentService
from app.core.security import verify_token
from app.infrastructure.documents.readers import DocumentError
from app.schemas.api import DocumentOut

router = APIRouter(prefix="/documents", tags=["documents"], dependencies=[Depends(verify_token)])


def _service(request: Request) -> DocumentService:
    container = get_container(request.app)
    if container.documents is None:
        container.documents = DocumentService(container.store, container.settings.data_dir / "tmp")
    return container.documents


@router.post("", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    chat_id: str | None = Form(default=None),
) -> DocumentOut:
    if chat_id and await get_container(request.app).store.get_chat(chat_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="chat")
    data = await file.read(MAX_BYTES + 1)
    try:
        document = await _service(request).ingest(file.filename or "", data, chat_id=chat_id or None)
    except DocumentError as exc:
        # Código curto (unsupported, empty, unreadable, too_large, too_many); a interface traduz.
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    return DocumentOut.from_domain(document)


@router.get("", response_model=list[DocumentOut])
async def list_documents(request: Request, chat_id: str = Query(...)) -> list[DocumentOut]:
    return [DocumentOut.from_domain(item) for item in await _service(request).list(chat_id)]


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(request: Request, document_id: str) -> None:
    try:
        await _service(request).delete(document_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document") from exc
