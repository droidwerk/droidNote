from __future__ import annotations

import asyncio
import base64
import binascii
import json
import re

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse, Response, StreamingResponse

from app.api.v1.deps import get_container
from app.application.chat import ChatImageIn, ChatScope
from app.application.export import export_markdown_docx, export_markdown_pdf
from app.core.i18n import ui_message
from app.core.security import verify_token
from app.schemas.api import ChatAskIn, ChatCitationOut, ChatDetailOut, ChatMessageOut, ChatOut, ChatRenameIn

router = APIRouter(prefix="/chat", tags=["chat"], dependencies=[Depends(verify_token)])


def _missing(request: Request | None = None) -> HTTPException:
    locale = "pt"
    if request is not None:
        locale = get_container(request.app).settings.ui_language
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=ui_message(locale, "chat_missing"))


@router.get("", response_model=list[ChatOut])
async def list_chats(request: Request) -> list[ChatOut]:
    chats = await get_container(request.app).chat.list_chats()
    return [ChatOut.from_domain(item) for item in chats]


@router.get("/{chat_id}", response_model=ChatDetailOut)
async def get_chat(request: Request, chat_id: str) -> ChatDetailOut:
    try:
        chat, messages = await get_container(request.app).chat.get(chat_id)
    except KeyError:
        raise _missing(request) from None
    return ChatDetailOut(
        chat=ChatOut.from_domain(chat),
        messages=[ChatMessageOut.from_domain(item) for item in messages],
    )


@router.patch("/{chat_id}", response_model=ChatOut)
async def rename_chat(request: Request, chat_id: str, payload: ChatRenameIn) -> ChatOut:
    try:
        chat = await get_container(request.app).chat.rename(chat_id, payload.title)
    except KeyError:
        raise _missing(request) from None
    return ChatOut.from_domain(chat)


@router.delete("/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat(request: Request, chat_id: str) -> None:
    await get_container(request.app).chat.delete(chat_id)


@router.get("/images/{image_id}")
async def get_chat_image(request: Request, image_id: str) -> Response:
    found = await get_container(request.app).store.get_chat_image(image_id)
    if found is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="image")
    image, data = found
    return Response(content=data, media_type=image.mime, headers={"Cache-Control": "private, max-age=3600"})


@router.get("/{chat_id}/messages/{message_id}/export")
async def export_chat_message(
    request: Request,
    chat_id: str,
    message_id: str,
    format: str = Query(default="markdown", pattern="^(markdown|pdf|docx)$"),
) -> Response:
    """Uma resposta do assistente como arquivo: Markdown puro, PDF ou Word com a cara do DroidNote."""
    container = get_container(request.app)
    try:
        chat, messages = await container.chat.get(chat_id)
    except KeyError:
        raise _missing(request) from None
    message = next((item for item in messages if item.id == message_id and item.role == "assistant"), None)
    if message is None:
        raise _missing(request)
    # Título: a pergunta que gerou a resposta, quando existe.
    index = messages.index(message)
    question = next((item.content for item in reversed(messages[:index]) if item.role == "user"), "")
    title = (question.strip().split("\n", 1)[0] or chat.title)[:120]
    base = _download_name(title)
    locale = container.settings.ui_language
    when = message.created_at.astimezone().strftime("%d/%m/%Y %H:%M")
    if format == "markdown":
        body = f"# {title}\n\n{message.content.strip()}\n"
        return PlainTextResponse(
            body,
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{base}.md"'},
        )
    if format == "pdf":
        payload = export_markdown_pdf(title, message.content, subtitle=f"DroidNote · {when}", locale=locale)
        return Response(
            content=payload,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{base}.pdf"'},
        )
    payload = export_markdown_docx(title, message.content, subtitle=f"DroidNote · {when}", locale=locale)
    return Response(
        content=payload,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{base}.docx"'},
    )


def _download_name(title: str) -> str:
    cleaned = re.sub(r"[^\w\- ]+", "", title, flags=re.UNICODE).strip().replace(" ", "-")
    return (cleaned or "resposta")[:60]


def _decode_images(payload: ChatAskIn, locale: str) -> list[ChatImageIn]:
    images: list[ChatImageIn] = []
    for item in payload.images:
        raw = item.data.split(",", 1)[1] if item.data.startswith("data:") else item.data
        try:
            data = base64.b64decode(raw, validate=True)
        except (binascii.Error, ValueError):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=ui_message(locale, "chat_image_too_large")) from None
        images.append(ChatImageIn(name=item.name, mime=item.mime, data=data))
    return images


@router.post("/ask")
async def ask_chat(request: Request, payload: ChatAskIn) -> StreamingResponse:
    container = get_container(request.app)
    queue: asyncio.Queue[tuple[str, object]] = asyncio.Queue()
    images = _decode_images(payload, payload.ui_language or container.settings.ui_language)
    scope = (
        ChatScope(
            days=payload.scope.days,
            person_id=payload.scope.person_id or None,
            tag_id=payload.scope.tag_id or None,
            session_ids=tuple(payload.scope.session_ids),
        )
        if payload.scope
        else None
    )

    def on_token(token: str) -> None:
        queue.put_nowait(("token", token))

    async def run() -> None:
        try:
            chat, message, citations = await container.chat.ask(
                payload.message,
                chat_id=payload.chat_id,
                session_id=payload.session_id,
                segment_ids=payload.segment_ids,
                document_ids=payload.document_ids,
                on_token=on_token,
                ui_language=payload.ui_language or container.settings.ui_language,
                style=payload.style,
                grounded=payload.grounded,
                solve_target=payload.solve_target,
                scope=scope,
                images=images,
                retry=payload.retry,
                on_chat=lambda chat: queue.put_nowait(("chat", chat.id)),
            )
            queue.put_nowait(
                (
                    "done",
                    {
                        "chat": ChatOut.from_domain(chat).model_dump(mode="json"),
                        "message": ChatMessageOut.from_domain(message).model_dump(mode="json"),
                        "citations": [
                            ChatCitationOut.from_domain(item).model_dump(mode="json")
                            for item in citations
                        ],
                    },
                )
            )
        except KeyError:
            queue.put_nowait(("error", ui_message(container.settings.ui_language, "chat_missing")))
        except ValueError as exc:
            queue.put_nowait(("error", str(exc)))
        except Exception as exc:
            locale = payload.ui_language or container.settings.ui_language
            # Motor de IA fora do ar (Ollama parado, sem rede): a frase técnica do
            # httpx não ajuda ninguém; diz o que está acontecendo no idioma da interface.
            if isinstance(exc, (httpx.HTTPError, ConnectionError, OSError)):
                queue.put_nowait(("error", ui_message(locale, "llm_not_ready")))
            else:
                queue.put_nowait(("error", str(exc) or ui_message(locale, "chat_no_reply")))

    async def events():
        task = asyncio.create_task(run())
        try:
            while True:
                kind, data = await queue.get()
                if kind == "chat":
                    yield f"data: {json.dumps({'chat_id': data})}\n\n"
                elif kind == "token":
                    yield f"data: {json.dumps({'token': data}, ensure_ascii=False)}\n\n"
                elif kind == "done":
                    yield f"data: {json.dumps({'done': True, **data}, ensure_ascii=False)}\n\n"
                    break
                else:
                    yield f"data: {json.dumps({'error': data}, ensure_ascii=False)}\n\n"
                    break
        finally:
            await task

    return StreamingResponse(events(), media_type="text/event-stream")
