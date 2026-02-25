"""LLM operations — blueprint management."""
import logging
from pathlib import Path

import aiofiles
import aiofiles.os
from fastapi import APIRouter, Depends

from app.core.auth import get_current_user

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
