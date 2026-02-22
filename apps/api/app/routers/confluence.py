"""Confluence source module endpoints.
Full implementation in Phase 4.
"""
from fastapi import APIRouter, Depends
from app.core.auth import get_current_user
from app.core.rbac import require_permission

router = APIRouter()


@router.post("/test-connection")
async def test_connection(
    current_user: dict = Depends(require_permission("confluence", "view")),
):
    return {"status": "not_implemented", "message": "Phase 4"}


@router.get("/spaces")
async def list_spaces(
    current_user: dict = Depends(require_permission("confluence", "view")),
):
    return {"spaces": []}


@router.post("/extract")
async def extract_pages(
    current_user: dict = Depends(require_permission("confluence", "extract")),
):
    return {"status": "not_implemented", "message": "Phase 4"}
