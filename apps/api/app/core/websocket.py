import json
import logging
from typing import Dict, Set
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class WebSocketManager:
    """Manages WebSocket connections and broadcasts progress messages."""

    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.user_connections: Dict[int, Set[str]] = {}

    async def connect(self, websocket: WebSocket, connection_id: str, user_id: int | None = None):
        await websocket.accept()
        self.active_connections[connection_id] = websocket
        if user_id:
            if user_id not in self.user_connections:
                self.user_connections[user_id] = set()
            self.user_connections[user_id].add(connection_id)
        logger.info(f"WebSocket connected: {connection_id}")

    def disconnect(self, connection_id: str, user_id: int | None = None):
        self.active_connections.pop(connection_id, None)
        if user_id and user_id in self.user_connections:
            self.user_connections[user_id].discard(connection_id)
            if not self.user_connections[user_id]:
                del self.user_connections[user_id]
        logger.info(f"WebSocket disconnected: {connection_id}")

    async def send_to_connection(self, connection_id: str, message: dict):
        ws = self.active_connections.get(connection_id)
        if ws:
            try:
                await ws.send_text(json.dumps(message))
            except Exception:
                self.disconnect(connection_id)

    async def send_to_user(self, user_id: int, message: dict):
        connection_ids = self.user_connections.get(user_id, set())
        for conn_id in list(connection_ids):
            await self.send_to_connection(conn_id, message)

    async def broadcast(self, message: dict):
        for conn_id in list(self.active_connections.keys()):
            await self.send_to_connection(conn_id, message)


ws_manager = WebSocketManager()


async def websocket_endpoint(websocket: WebSocket):
    import uuid
    connection_id = str(uuid.uuid4())

    # Extract user_id from query params if available
    token = websocket.query_params.get("token")
    user_id = None
    if token:
        from app.core.auth import decode_session_token
        try:
            payload = decode_session_token(token)
            user_id = payload.get("user_id")
        except Exception:
            pass

    await ws_manager.connect(websocket, connection_id, user_id)
    try:
        while True:
            data = await websocket.receive_text()
            # Handle incoming messages if needed
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await ws_manager.send_to_connection(
                        connection_id, {"type": "pong"}
                    )
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        ws_manager.disconnect(connection_id, user_id)
