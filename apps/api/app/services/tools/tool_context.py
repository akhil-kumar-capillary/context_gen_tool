"""ToolContext — runtime context injected into every tool execution.

This is NOT visible to the LLM. It carries authentication, database session,
and WebSocket connection details so tools can perform authenticated side-effects.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.core.websocket import WebSocketManager


@dataclass(frozen=True)
class ToolContext:
    """Immutable context injected into every tool invocation."""

    # User info (from JWT)
    user: dict  # {user_id, email, is_admin, capillary_token, cluster, base_url}
    org_id: int

    # Database
    db: "AsyncSession"

    # WebSocket (for streaming tool progress to frontend)
    ws_manager: "WebSocketManager"
    ws_connection_id: str

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
