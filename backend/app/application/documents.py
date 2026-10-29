"""Documentos do chat: recebe o arquivo, lê com o LangChain e guarda os trechos.

O arquivo original não fica guardado: só o texto fatiado, que é o que o chat
usa. O temporário é apagado logo depois da leitura.
"""

from __future__ import annotations

import asyncio
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from app.domain.models import ChatDocument, DocumentChunk
from app.infrastructure.documents.readers import DocumentError, document_kind, read_document
from app.infrastructure.persistence.sqlite import SqliteStore, new_id

MAX_BYTES = 25 * 1024 * 1024
MAX_PER_CHAT = 10


class DocumentService:
    def __init__(self, store: SqliteStore, work_dir: Path) -> None:
        self._store = store
        self._work_dir = work_dir

    async def ingest(
        self, filename: str, data: bytes, *, chat_id: str | None = None, session_id: str | None = None
    ) -> ChatDocument:
        name = Path(filename or "documento").name[:160]
        kind = document_kind(name)
        if not data:
            raise DocumentError("empty")
        if len(data) > MAX_BYTES:
            raise DocumentError("too_large")
        if chat_id and len(await self._store.list_documents(chat_id=chat_id)) >= MAX_PER_CHAT:
            raise DocumentError("too_many")
        if session_id and len(await self._store.list_documents(session_id=session_id)) >= MAX_PER_CHAT:
            raise DocumentError("too_many")
        self._work_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=self._work_dir) as folder:
            path = Path(folder) / f"upload{Path(name).suffix.lower()}"
            path.write_bytes(data)
            pieces, pages = await asyncio.to_thread(read_document, path, name)
        document_id = new_id()
        chunks = [
            DocumentChunk(document_id=document_id, ord=index, text=piece.text, page=piece.page)
            for index, piece in enumerate(pieces)
        ]
        document = ChatDocument(
            id=document_id,
            chat_id=chat_id,
            session_id=session_id,
            name=name,
            kind=kind,
            size=len(data),
            pages=pages,
            chunks=len(chunks),
            chars=sum(len(chunk.text) for chunk in chunks),
            created_at=datetime.now(tz=UTC),
        )
        await self._store.save_document(document, chunks)
        return document

    async def list(self, chat_id: str) -> list[ChatDocument]:
        return await self._store.list_documents(chat_id=chat_id)

    async def list_for_session(self, session_id: str) -> list[ChatDocument]:
        return await self._store.list_documents(session_id=session_id)

    async def delete(self, document_id: str) -> None:
        if not await self._store.delete_document(document_id):
            raise KeyError(document_id)
