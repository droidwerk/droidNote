from __future__ import annotations

from fastapi import WebSocket, WebSocketDisconnect

from app.api.v1.deps import get_container
from app.core.config import get_settings

from fastapi import APIRouter

router = APIRouter(tags=["realtime"])


@router.websocket("/ws/transcript")
async def transcript_socket(websocket: WebSocket, token: str | None = None) -> None:
    expected = get_settings().token
    provided = token or websocket.headers.get("X-DroidNote-Token")
    if not provided or provided != expected:
        await websocket.close(code=4401)
        return
    await websocket.accept()
    container = get_container(websocket.app)
    queue = await container.bus.subscribe()
    try:
        state = container.capture.state
        await websocket.send_json(
            {
                "type": "hello",
                "recording": state.recording,
                "session_id": state.session_id,
                "started_at": state.started_at.isoformat() if state.started_at else None,
            }
        )
        while True:
            event = await queue.get()
            await websocket.send_json(event)
    except WebSocketDisconnect:
        pass
    finally:
        await container.bus.unsubscribe(queue)
