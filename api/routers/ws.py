"""WebSocket push. Week 6 replaces the echo with the real event fan-out.

Event envelope is frozen now so the frontend can build against it:
    {"type": "metric" | "incident" | "action" | "vote" | "explanation",
     "tenant_id": "...", "payload": {...}, "ts": "ISO-8601"}
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from core.logging import get_logger

log = get_logger(__name__)
router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    log.info("ws client connected")
    try:
        await websocket.send_json({"type": "hello", "payload": {"version": "0.1.0"}})
        while True:
            message = await websocket.receive_text()
            await websocket.send_json({"type": "echo", "payload": {"received": message}})
    except WebSocketDisconnect:
        log.info("ws client disconnected")
