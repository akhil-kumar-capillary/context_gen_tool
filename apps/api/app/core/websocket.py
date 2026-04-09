import asyncio
import json
import logging
import time
from typing import Dict, Set
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

# Idle timeout: disconnect WebSockets with no activity for this many seconds.
# Client heartbeat ping (30s) keeps healthy connections alive.
_WS_IDLE_TIMEOUT = 300.0  # 5 minutes


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
        self._last_activity: Dict[str, float] = {}      # tracks last message time

    async def connect(self, websocket: WebSocket, connection_id: str, user_id: int | None = None, *, already_accepted: bool = False):
        if not already_accepted:
            await websocket.accept()
        async with self._lock:
            self.active_connections[connection_id] = websocket
            self._send_locks[connection_id] = asyncio.Lock()
            self._last_activity[connection_id] = time.monotonic()
            if user_id:
                if user_id not in self.user_connections:
                    self.user_connections[user_id] = set()
                self.user_connections[user_id].add(connection_id)
        logger.info(
            f"WebSocket connected: {connection_id} (user={user_id}) "
            f"[total={len(self.active_connections)}]"
        )

    async def disconnect(self, connection_id: str, user_id: int | None = None):
        async with self._lock:
            self.active_connections.pop(connection_id, None)
            self._send_locks.pop(connection_id, None)
            self._last_activity.pop(connection_id, None)
            if user_id and user_id in self.user_connections:
                self.user_connections[user_id].discard(connection_id)
                if not self.user_connections[user_id]:
                    del self.user_connections[user_id]
        logger.info(
            f"WebSocket disconnected: {connection_id} "
            f"[total={len(self.active_connections)}]"
        )

    def touch(self, connection_id: str):
        """Update last-activity timestamp for a connection."""
        self._last_activity[connection_id] = time.monotonic()

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

    # Accept connection first, then authenticate via first message.
    # Also supports legacy query-parameter auth for backward compatibility.
    await websocket.accept()

    token = websocket.query_params.get("token")
    user_id = None

    if token:
        # Legacy query-param auth
        from app.core.auth import decode_session_token
        try:
            payload = decode_session_token(token)
            user_id = payload.get("user_id")
        except Exception:
            pass
    else:
        # Message-based auth — first message must be {type: "auth", token: "..."}
        try:
            raw_auth = await asyncio.wait_for(websocket.receive_text(), timeout=10.0)
            auth_msg = json.loads(raw_auth)
            if auth_msg.get("type") == "auth" and auth_msg.get("token"):
                from app.core.auth import decode_session_token
                try:
                    payload = decode_session_token(auth_msg["token"])
                    user_id = payload.get("user_id")
                except Exception:
                    pass
        except (asyncio.TimeoutError, json.JSONDecodeError, Exception):
            pass

    if user_id is None:
        await websocket.close(code=4001, reason="Authentication required")
        return

    await ws_manager.connect(websocket, connection_id, user_id, already_accepted=True)
    try:
        while True:
            # Idle timeout: if no message for 5 min, assume client is dead.
            # Client heartbeat ping (30s) keeps healthy connections alive.
            data = await asyncio.wait_for(
                websocket.receive_text(), timeout=_WS_IDLE_TIMEOUT
            )
            ws_manager.touch(connection_id)
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await ws_manager.send_to_connection(
                        connection_id, {"type": "pong"}
                    )
            except json.JSONDecodeError:
                pass
    except asyncio.TimeoutError:
        logger.info(f"WebSocket idle timeout (connection={connection_id})")
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception(f"WebSocket error in general endpoint (connection={connection_id})")
    finally:
        # Guarantee cleanup even on unexpected exceptions
        if connection_id in ws_manager.active_connections:
            await ws_manager.disconnect(connection_id, user_id)
