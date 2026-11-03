from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status

from app.api.v1.deps import get_container
from app.application.documents import MAX_BYTES, DocumentService
from app.core.security import verify_token
from app.infrastructure.documents.readers import DocumentError
from app.schemas.api import DocumentOut, DocumentUrlIn

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


@router.post("/url", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def attach_url(request: Request, payload: DocumentUrlIn) -> DocumentOut:
    """Link de página ou vídeo do YouTube vira documento do chat (texto ou legendas)."""
    if payload.chat_id and await get_container(request.app).store.get_chat(payload.chat_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="chat")
    try:
        document = await _service(request).ingest_url(
            payload.url, chat_id=payload.chat_id or None, transcribe=_audio_transcriber(request)
        )
    except DocumentError as exc:
        # Código curto (url_invalid, url_unreachable, no_captions, empty, too_large…); a interface traduz.
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    return DocumentOut.from_domain(document)


def _audio_transcriber(request: Request):
    """Vídeo sem legenda: o mesmo motor de voz das gravações transcreve o áudio, se já estiver pronto."""
    container = get_container(request.app)
    setup = getattr(container, "setup", None)
    asr = getattr(setup, "asr", None)
    # Só o motor local (Whisper neste PC): um link não pode mandar áudio para a
    # nuvem sem a pessoa esperar por isso, mesmo com a transcrição OpenAI ligada.
    local = getattr(asr, "local", None)
    if local is not None and getattr(asr, "provider", "neste_pc") == "openai":
        asr = local
    if asr is None or not asr.is_ready():
        return None

    def transcribe(samples, sample_rate):
        with_words = getattr(asr, "transcribe_words", None)
        if callable(with_words):
            words, _ = with_words(samples, sample_rate)
            return words
        text, _ = asr.transcribe_window(samples, sample_rate)  # motor sem tempo por palavra
        return [(0.0, len(samples) / float(sample_rate or 1), text)] if text else []

    return transcribe


@router.get("", response_model=list[DocumentOut])
async def list_documents(request: Request, chat_id: str = Query(...)) -> list[DocumentOut]:
    return [DocumentOut.from_domain(item) for item in await _service(request).list(chat_id)]


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(request: Request, document_id: str) -> None:
    try:
        await _service(request).delete(document_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document") from exc
