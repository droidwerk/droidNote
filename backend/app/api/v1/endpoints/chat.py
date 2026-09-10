from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from app.api.v1.deps import get_container
from app.core.i18n import ui_message
from app.core.security import verify_token
from app.schemas.api import ChatAskIn, ChatCitationOut, ChatDetailOut, ChatMessageOut, ChatOut

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


@router.delete("/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat(request: Request, chat_id: str) -> None:
    await get_container(request.app).chat.delete(chat_id)


@router.post("/ask")
async def ask_chat(request: Request, payload: ChatAskIn) -> StreamingResponse:
    container = get_container(request.app)
    queue: asyncio.Queue[tuple[str, object]] = asyncio.Queue()

    def on_token(token: str) -> None:
        queue.put_nowait(("token", token))

    async def run() -> None:
        try:
            chat, message, citations = await container.chat.ask(
                payload.message,
                chat_id=payload.chat_id,
                session_id=payload.session_id,
                segment_ids=payload.segment_ids,
                on_token=on_token,
                ui_language=payload.ui_language or container.settings.ui_language,
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
            fallback = ui_message(container.settings.ui_language, "chat_no_reply")
            queue.put_nowait(("error", str(exc) or fallback))

    async def events():
        task = asyncio.create_task(run())
        try:
            while True:
                kind, data = await queue.get()
                if kind == "token":
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
