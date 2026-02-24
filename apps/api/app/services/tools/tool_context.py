"""ToolContext — runtime context injected into every tool execution.

This is NOT visible to the LLM. It carries authentication, database session,
and WebSocket connection details so tools can perform authenticated side-effects.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional, AsyncIterator

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.core.websocket import WebSocketManager


@dataclass(frozen=True)
class ToolContext:
    """Immutable context injected into every tool invocation.

    The `db` field may be None when the orchestrator doesn't hold a
    long-lived session.  Tools that need DB access should use the
    `get_db()` async context manager, which either reuses the existing
    session or opens a new short-lived one.
    """

    # User info (from JWT)
    user: dict  # {user_id, email, is_admin, capillary_token, cluster, base_url}
    org_id: int

    # Database — may be None (tools should use get_db() instead)
    db: Optional["AsyncSession"] = field(default=None)

    # WebSocket (for streaming tool progress to frontend)
    ws_manager: Optional["WebSocketManager"] = field(default=None)
    ws_connection_id: str = ""

    # Capillary API access (convenience shortcuts)
    @property
    def capillary_token(self) -> str:
        return self.user.get("capillary_token", "")

    @property
    def base_url(self) -> str:
        return self.user.get("base_url", "")

    @property
    def user_id(self) -> int:
        return self.user.get("user_id", 0)

    @property
    def is_admin(self) -> bool:
        return self.user.get("is_admin", False)

    @property
    def email(self) -> str:
        return self.user.get("email", "")

    def capillary_headers(self) -> dict:
        """Standard headers for proxying to Capillary APIs."""
        return {
            "Authorization": f"Bearer {self.capillary_token}",
            "x-cap-api-auth-org-id": str(self.org_id),
        }

    @asynccontextmanager
    async def get_db(self) -> AsyncIterator["AsyncSession"]:
        """Get a database session — reuses existing or creates a short-lived one.

        Usage:
            async with ctx.get_db() as db:
                result = await db.execute(...)
        """
        if self.db is not None:
            # Reuse the caller-provided session (don't close it)
            yield self.db
        else:
            # Open a fresh short-lived session from the pool
            from app.database import async_session
            async with async_session() as session:
                try:
                    yield session
                finally:
                    await session.close()
