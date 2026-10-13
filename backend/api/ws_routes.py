"""WebSocket endpoints for real-time alerts and system status."""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, Query

from backend.auth.guards import verify_viewer_token
from backend.utils.websocket import manager

logger = logging.getLogger(__name__)
router = APIRouter(tags=["websockets"])


def _validate_ws_token(token: Optional[str]) -> bool:
    try:
        verify_viewer_token(token)
        return True
    except HTTPException:
        return False


@router.websocket("/ws/alerts")
async def websocket_alerts(
    websocket: WebSocket,
    token: Optional[str] = Query(default=None),
):
    if not _validate_ws_token(token):
        await websocket.close(code=1008)
        return

    await manager.connect(websocket, "alerts")
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, "alerts")


@router.websocket("/ws/status")
async def websocket_status(
    websocket: WebSocket,
    token: Optional[str] = Query(default=None),
):
    if not _validate_ws_token(token):
        await websocket.close(code=1008)
        return

    await manager.connect(websocket, "status")
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, "status")

