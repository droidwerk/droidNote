from __future__ import annotations

from fastapi import Header, HTTPException, Query, status, WebSocket

from app.core.config import get_settings
from app.core.i18n import ui_message

TOKEN_HEADER = "X-DroidNote-Token"


async def verify_token(x_droidnote_token: str | None = Header(default=None, alias=TOKEN_HEADER)) -> None:
    expected = get_settings().token
    if not x_droidnote_token or x_droidnote_token != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ui_message(get_settings().ui_language, "token_invalid"),
        )


async def verify_ws_token(
    websocket: WebSocket,
    token: str | None = Query(default=None),
) -> None:
    expected = get_settings().token
    header_token = websocket.headers.get(TOKEN_HEADER)
    provided = token or header_token
    if not provided or provided != expected:
        await websocket.close(code=4401)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ui_message(get_settings().ui_language, "token_invalid"),
        )
