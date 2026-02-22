"""Databricks source module endpoints.
Full implementation in Phase 3 — porting from existing databricks_context_creation app.
"""
from fastapi import APIRouter, Depends
from app.core.auth import get_current_user
from app.core.rbac import require_permission

router = APIRouter()


@router.post("/test-connection")
async def test_connection(
    current_user: dict = Depends(require_permission("databricks", "extract")),
):
    return {"status": "not_implemented", "message": "Phase 3"}


@router.post("/extract/start")
async def start_extraction(
    current_user: dict = Depends(require_permission("databricks", "extract")),
):
    return {"status": "not_implemented", "message": "Phase 3"}


@router.get("/runs")
async def list_runs(
    current_user: dict = Depends(require_permission("databricks", "view")),
):
    return {"runs": []}


@router.post("/analysis/start")
async def start_analysis(
    current_user: dict = Depends(require_permission("databricks", "analyze")),
):
    return {"status": "not_implemented", "message": "Phase 3"}


@router.post("/llm/generate")
async def generate_docs(
    current_user: dict = Depends(require_permission("databricks", "generate")),
):
    return {"status": "not_implemented", "message": "Phase 3"}


@router.get("/llm/default-prompts")
async def default_prompts(
    current_user: dict = Depends(require_permission("databricks", "view")),
):
    return {"status": "not_implemented", "message": "Phase 3"}
