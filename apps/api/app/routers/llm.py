"""LLM operations — sanitize/refactor, chat, blueprint management."""
import logging
from pathlib import Path

import aiofiles
import aiofiles.os
from fastapi import APIRouter, Depends

from app.core.auth import get_current_user
from app.core.rbac import require_permission

router = APIRouter()
logger = logging.getLogger(__name__)

BLUEPRINT_PATH = Path(__file__).parent.parent / "resources" / "blueprint.md"


@router.get("/blueprint")
async def get_blueprint(current_user: dict = Depends(get_current_user)):
    """Return the default blueprint text for context refactoring."""
    try:
        if await aiofiles.os.path.exists(BLUEPRINT_PATH):
            async with aiofiles.open(BLUEPRINT_PATH, encoding="utf-8") as f:
                content = await f.read()
            return {"blueprint": content}
    except Exception:
        logger.exception("Failed to read blueprint")
    return {"blueprint": None}


@router.post("/sanitize")
async def sanitize_contexts(
    current_user: dict = Depends(require_permission("context_management", "refactor")),
):
    """Start context refactoring/sanitization via LLM.
    Full implementation in Phase 2 — will stream via WebSocket.
    """
    return {"status": "not_implemented", "message": "Sanitize flow will be implemented in Phase 2"}


@router.post("/chat")
async def chat_with_contexts(
    current_user: dict = Depends(get_current_user),
):
    """Chat with LLM about contexts.
    Full implementation in Phase 2 — will stream via WebSocket.
    """
    return {"status": "not_implemented", "message": "Chat flow will be implemented in Phase 2"}
