"""
WebSocket manager for real-time alert streaming
"""
from typing import Dict, Set
from fastapi import WebSocket
import json
import logging

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages active WebSocket connections"""

    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {
            "alerts": set(),
            "video": set(),
            "status": set()
        }

    async def connect(self, websocket: WebSocket, channel: str = "alerts"):
        await websocket.accept()
        if channel not in self.active_connections:
            self.active_connections[channel] = set()
        self.active_connections[channel].add(websocket)
        logger.info(f"WebSocket connected: {channel}, total: {len(self.active_connections[channel])}")

    def disconnect(self, websocket: WebSocket, channel: str = "alerts"):
        if channel in self.active_connections:
            self.active_connections[channel].discard(websocket)
        logger.info(f"WebSocket disconnected: {channel}")

    async def send_personal_message(self, message: str, websocket: WebSocket):
        try:
            await websocket.send_text(message)
        except Exception as e:
            logger.error(f"Error sending personal message: {e}")

    async def broadcast(self, message: dict, channel: str = "alerts"):
        """Broadcast message to all connections in a channel"""
        if channel not in self.active_connections:
            return

        disconnected = set()
        message_str = json.dumps(message)

        for connection in self.active_connections[channel]:
            try:
                await connection.send_text(message_str)
            except Exception as e:
                logger.error(f"Error broadcasting to {channel}: {e}")
                disconnected.add(connection)

        # Clean up disconnected connections
        for conn in disconnected:
            self.active_connections[channel].discard(conn)

    def get_connection_count(self, channel: str = "alerts") -> int:
        return len(self.active_connections.get(channel, set()))


# Global manager instance
manager = ConnectionManager()
