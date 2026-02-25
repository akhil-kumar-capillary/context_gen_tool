import asyncio
import json
import logging
from typing import Dict, Set
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class WebSocketManager:
    """Manages WebSocket connections and broadcasts progress messages.

    Uses an asyncio.Lock to protect mutable connection state from
    concurrent coroutine access (multiple users connecting/disconnecting
    at the same time).

    Per-connection send locks serialize sends to the same WebSocket
    (required by ASGI spec) while allowing parallel sends to different
    connections.
    """

    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.user_connections: Dict[int, Set[str]] = {}
        self._lock = asyncio.Lock()           # protects connection map mutations
        self._send_locks: Dict[str, asyncio.Lock] = {}  # per-connection send serialization

    async def connect(self, websocket: WebSocket, connection_id: str, user_id: int | None = None):
        await websocket.accept()
        async with self._lock:
            self.active_connections[connection_id] = websocket
            self._send_locks[connection_id] = asyncio.Lock()
            if user_id:
                if user_id not in self.user_connections:
                    self.user_connections[user_id] = set()
                self.user_connections[user_id].add(connection_id)
        logger.info(f"WebSocket connected: {connection_id} (user={user_id})")

    async def disconnect(self, connection_id: str, user_id: int | None = None):
        async with self._lock:
            self.active_connections.pop(connection_id, None)
            self._send_locks.pop(connection_id, None)
            if user_id and user_id in self.user_connections:
                self.user_connections[user_id].discard(connection_id)
                if not self.user_connections[user_id]:
                    del self.user_connections[user_id]
        logger.info(f"WebSocket disconnected: {connection_id}")

    async def send_to_connection(self, connection_id: str, message: dict):
        # Look up both ws and its send lock atomically under the manager lock
        async with self._lock:
            ws = self.active_connections.get(connection_id)
            send_lock = self._send_locks.get(connection_id)
        if ws and send_lock:
            try:
                async with send_lock:
                    await ws.send_text(json.dumps(message))
            except Exception:
                await self.disconnect(connection_id)

    async def send_to_user(self, user_id: int, message: dict):
        async with self._lock:
            connection_ids = list(self.user_connections.get(user_id, set()))
        for conn_id in connection_ids:
            await self.send_to_connection(conn_id, message)

    async def broadcast(self, message: dict):
        async with self._lock:
            conn_ids = list(self.active_connections.keys())
        for conn_id in conn_ids:
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
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await ws_manager.send_to_connection(
                        connection_id, {"type": "pong"}
                    )
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        await ws_manager.disconnect(connection_id, user_id)
