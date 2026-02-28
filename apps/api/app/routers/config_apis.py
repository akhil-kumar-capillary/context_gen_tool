"""Configuration APIs source — full extraction → analysis → generation pipeline.

Uses the authenticated user's Capillary token to fetch org-level configuration
from various Intouch API endpoints. Long-running ops are launched as background
tasks; progress is pushed via WebSocket.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.auth import get_current_user
from app.core.rbac import require_permission
from app.core.websocket import ws_manager
from app.core.task_registry import task_registry

from app.services.config_apis.storage import ConfigStorageService
from app.services.config_apis.extraction_orchestrator import (
    run_extraction,
    get_available_categories,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Request / Response Models ────────────────────────────────────────

class StartExtractionRequest(BaseModel):
    host: str = Field(..., description="Capillary platform host (e.g. eu.intouch.capillarytech.com)")
    org_id: int = Field(..., description="Organization ID")
    categories: list[str] = Field(
        default_factory=lambda: [
            "loyalty", "extended_fields", "campaigns",
            "promotions", "coupons", "audiences", "org_settings",
        ],
        description="Category IDs to extract",
    )
    category_params: Optional[dict] = Field(
        default=None,
        description="Per-category params, e.g. {\"campaigns\": {\"limit\": 50}}",
    )


class StartAnalysisRequest(BaseModel):
    run_id: str = Field(..., description="Extraction run UUID")


class GenerateDocsRequest(BaseModel):
    analysis_id: str = Field(..., description="Analysis run UUID")
    provider: str = Field(default="anthropic")
    model: str = Field(default="claude-opus-4-6")
    inclusions: Optional[dict] = Field(
        default=None,
        description="Per-doc-type inclusion toggles: {doc_key: {entity_path: bool}}",
    )
    system_prompts: Optional[dict] = Field(
        default=None,
        description="Custom system prompts: {doc_key: prompt_text}",
    )


class PayloadPreviewRequest(BaseModel):
    analysis_id: str = Field(..., description="Analysis run UUID")
    inclusions: Optional[dict] = Field(
        default=None,
        description="Inclusion toggles: {doc_key: {entity_path: bool}}",
    )
    include_stats: bool = Field(
        default=True,
        description="Include n/pct/count fields (True for UI preview, False for LLM view)",
    )


# ── WebSocket progress helper ────────────────────────────────────────

def _ws_progress_callback(user_id: int, channel: str):
    """Create a progress callback that sends events to the user's WebSocket."""
    async def _callback(*args):
        if len(args) == 1 and isinstance(args[0], dict):
            event = args[0]
        elif len(args) == 4:
            event = {
                "type": f"{channel}_progress",
                "phase": args[0],
                "completed": args[1],
                "total": args[2],
                "detail": args[3],
            }
        else:
            event = {"type": f"{channel}_progress", "data": args}

        event.setdefault("type", f"{channel}_progress")
        event["channel"] = channel
        await ws_manager.send_to_user(user_id, event)
    return _callback


# ══════════════════════════════════════════════════════════════════════
# CATEGORY METADATA
# ══════════════════════════════════════════════════════════════════════

@router.get("/categories")
async def list_categories(
    current_user: dict = Depends(require_permission("config_apis", "view")),
):
    """List all available API categories with param schemas."""
    return {"categories": get_available_categories()}


# ══════════════════════════════════════════════════════════════════════
# EXTRACTION ENDPOINTS
# ══════════════════════════════════════════════════════════════════════

@router.post("/extract/start")
async def start_extraction(
    req: StartExtractionRequest,
    current_user: dict = Depends(require_permission("config_apis", "extract")),
):
    """Start a config API extraction pipeline (background task).

    Returns immediately with a run_id; progress is pushed via WebSocket.
    """
    token = current_user.get("capillary_token")
    if not token:
        raise HTTPException(401, "No Capillary token found in session.")

    run_id = str(uuid.uuid4())
    user_id = current_user["user_id"]
    progress_cb = _ws_progress_callback(user_id, "config_extraction")

    async def _run():
        try:
            result = await run_extraction(
                run_id=run_id,
                host=req.host,
                token=token,
                org_id=req.org_id,
                user_id=user_id,
                categories=req.categories,
                category_params=req.category_params,
                on_progress=progress_cb,
            )
            await ws_manager.send_to_user(user_id, {
                "type": "config_extraction_complete",
                "run_id": run_id,
                "result": result,
            })
        except asyncio.CancelledError:
            logger.info(f"Config extraction {run_id} cancelled")
            storage = ConfigStorageService()
            await storage.cancel_extraction_run(run_id)
            await ws_manager.send_to_user(user_id, {
                "type": "config_extraction_cancelled", "run_id": run_id,
            })
        except Exception as e:
            logger.exception(f"Config extraction {run_id} failed")
            storage = ConfigStorageService()
            await storage.fail_extraction_run(run_id, str(e))
            await ws_manager.send_to_user(user_id, {
                "type": "config_extraction_failed",
                "run_id": run_id,
                "error": str(e),
            })

    task_registry.create_task(
        _run(), name=f"config-extraction-{run_id}", user_id=user_id
    )
    return {"run_id": run_id, "status": "started"}


@router.post("/extract/cancel/{run_id}")
async def cancel_extraction(
    run_id: str,
    current_user: dict = Depends(require_permission("config_apis", "extract")),
):
    """Cancel a running extraction task."""
    cancelled = task_registry.cancel_task(f"config-extraction-{run_id}")
    if not cancelled:
        raise HTTPException(404, "No active extraction task found for this run_id")
    return {"cancelled": True, "run_id": run_id}


@router.get("/extract/runs")
async def list_extraction_runs(
    org_id: Optional[int] = Query(default=None),
    current_user: dict = Depends(require_permission("config_apis", "view")),
):
    """List past extraction runs."""
    storage = ConfigStorageService()
    runs = await storage.get_extraction_runs(
        user_id=current_user["user_id"], org_id=org_id
    )
    return {"runs": runs}


@router.get("/extract/runs/{run_id}")
async def get_extraction_run(
    run_id: str,
    current_user: dict = Depends(require_permission("config_apis", "view")),
):
    """Get details of a single extraction run."""
    storage = ConfigStorageService()
    run = await storage.get_extraction_run(run_id)
    if not run:
        raise HTTPException(404, "Extraction run not found")
    return run


@router.delete("/extract/runs/{run_id}")
async def delete_extraction_run(
    run_id: str,
    current_user: dict = Depends(require_permission("config_apis", "extract")),
):
    """Delete an extraction run and all associated data."""
    storage = ConfigStorageService()
    run = await storage.get_extraction_run(run_id)
    if not run:
        raise HTTPException(404, "Extraction run not found")
    await storage.delete_extraction_run(run_id)
    return {"status": "deleted", "run_id": run_id}


# ══════════════════════════════════════════════════════════════════════
# EXTRACTION — CALL LOG & RAW DATA
# ══════════════════════════════════════════════════════════════════════

@router.get("/extract/runs/{run_id}/call-log")
async def get_extraction_call_log(
    run_id: str,
    category: Optional[str] = Query(default=None, description="Filter by category"),
    current_user: dict = Depends(require_permission("config_apis", "view")),
):
    """Get per-API-call result metadata for an extraction run.

    Returns structured log with status, duration, item count, errors per API call.
    Optionally filtered by category.
    """
    storage = ConfigStorageService()
    log = await storage.get_api_call_log(run_id, category=category)
    if log is None:
        raise HTTPException(404, "Extraction run not found or has no call log")
    return {"run_id": run_id, "call_log": log}


@router.get("/extract/runs/{run_id}/raw/{category}")
async def get_raw_category_data(
    run_id: str,
    category: str,
    current_user: dict = Depends(require_permission("config_apis", "view")),
):
    """Get raw extracted data for an entire category."""
    storage = ConfigStorageService()
    data = await storage.get_raw_api_data(run_id, category)
    if data is None:
        raise HTTPException(404, "No data found for this category")
    return {"run_id": run_id, "category": category, "data": data}


@router.get("/extract/runs/{run_id}/raw/{category}/{api_name}")
async def get_raw_api_response(
    run_id: str,
    category: str,
    api_name: str,
    current_user: dict = Depends(require_permission("config_apis", "view")),
):
    """Get raw JSON response for one specific API call from an extraction run.

    For inspecting exactly what came back from a single API.
    """
    storage = ConfigStorageService()
    data = await storage.get_raw_api_data(run_id, category, api_name=api_name)
    if data is None:
        raise HTTPException(404, f"No data found for {category}/{api_name}")
    return {"run_id": run_id, "category": category, "api_name": api_name, "data": data}


# ══════════════════════════════════════════════════════════════════════
# ANALYSIS ENDPOINTS
# ══════════════════════════════════════════════════════════════════════

@router.post("/analysis/start")
async def start_analysis(
    req: StartAnalysisRequest,
    current_user: dict = Depends(require_permission("config_apis", "analyze")),
):
    """Start config data analysis (background task)."""
    storage = ConfigStorageService()

    # Verify extraction exists
    extraction = await storage.get_extraction_run(req.run_id)
    if not extraction:
        raise HTTPException(404, "Extraction run not found")
    if extraction["status"] != "completed":
        raise HTTPException(400, f"Extraction is {extraction['status']}, not completed")

    analysis_id = str(uuid.uuid4())
    user_id = current_user["user_id"]
    org_id = extraction["org_id"]
    progress_cb = _ws_progress_callback(user_id, "config_analysis")

    async def _run():
        try:
            # Import here to avoid circular imports
            from app.services.config_apis.analysis_engine import run_analysis

            result = await run_analysis(
                analysis_id=analysis_id,
                run_id=req.run_id,
                user_id=user_id,
                org_id=org_id,
                on_progress=progress_cb,
            )
            await ws_manager.send_to_user(user_id, {
                "type": "config_analysis_complete",
                "run_id": req.run_id,
                "analysis_id": analysis_id,
                "result": result,
            })
        except asyncio.CancelledError:
            logger.info(f"Config analysis {analysis_id} cancelled")
            await ws_manager.send_to_user(user_id, {
                "type": "config_analysis_cancelled",
                "analysis_id": analysis_id,
            })
        except Exception as e:
            logger.exception(f"Config analysis {analysis_id} failed")
            await storage.fail_analysis_run(analysis_id, str(e))
            await ws_manager.send_to_user(user_id, {
                "type": "config_analysis_failed",
                "analysis_id": analysis_id,
                "error": str(e),
            })

    task_registry.create_task(
        _run(), name=f"config-analysis-{analysis_id}", user_id=user_id
    )
    return {"analysis_id": analysis_id, "run_id": req.run_id, "status": "started"}


@router.post("/analysis/cancel/{analysis_id}")
async def cancel_analysis(
    analysis_id: str,
    current_user: dict = Depends(require_permission("config_apis", "analyze")),
):
    """Cancel a running analysis task."""
    cancelled = task_registry.cancel_task(f"config-analysis-{analysis_id}")
    if not cancelled:
        raise HTTPException(404, "No active analysis task found")
    return {"cancelled": True, "analysis_id": analysis_id}


@router.get("/analysis/history/{run_id}")
async def get_analysis_history(
    run_id: str,
    current_user: dict = Depends(require_permission("config_apis", "view")),
):
    """Get analysis runs for a specific extraction run."""
    storage = ConfigStorageService()
    runs = await storage.get_analysis_history(run_id)
    return {"runs": runs}


@router.delete("/analysis/{analysis_id}")
async def delete_analysis(
    analysis_id: str,
    current_user: dict = Depends(require_permission("config_apis", "analyze")),
):
    """Delete an analysis run and all associated data."""
    storage = ConfigStorageService()
    await storage.delete_analysis_run(analysis_id)
    return {"status": "deleted", "analysis_id": analysis_id}


# ══════════════════════════════════════════════════════════════════════
# REVIEW & SELECT ENDPOINTS
# ══════════════════════════════════════════════════════════════════════

@router.get("/review/fingerprints/{analysis_id}")
async def get_fingerprints(
    analysis_id: str,
    entity_type: Optional[str] = Query(default=None, description="Filter by entity type"),
    limit: int = Query(default=500, ge=1, le=5000),
    current_user: dict = Depends(require_permission("config_apis", "view")),
):
    """Get config fingerprints from an analysis run."""
    from app.database import async_session
    from app.models.config_pipeline import ConfigAnalysisRun
    from sqlalchemy import select

    async with async_session() as db:
        result = await db.execute(
            select(ConfigAnalysisRun).where(
                ConfigAnalysisRun.id == uuid.UUID(analysis_id)
            )
        )
        row = result.scalar_one_or_none()
        if not row or not row.analysis_data:
            raise HTTPException(404, "Analysis run not found or has no data")

    fingerprints = row.analysis_data.get("fingerprints", [])
    entity_type_counts = row.analysis_data.get("entity_type_counts", {})

    if entity_type:
        fingerprints = [
            fp for fp in fingerprints if fp.get("entity_type") == entity_type
        ]

    return {
        "fingerprints": fingerprints[:limit],
        "total": len(fingerprints),
        "entity_type_counts": entity_type_counts,
    }


@router.get("/review/counters/{analysis_id}")
async def get_counters(
    analysis_id: str,
    current_user: dict = Depends(require_permission("config_apis", "view")),
):
    """Get frequency counters from an analysis run."""
    from app.database import async_session
    from app.models.config_pipeline import ConfigAnalysisRun
    from sqlalchemy import select

    async with async_session() as db:
        result = await db.execute(
            select(ConfigAnalysisRun).where(
                ConfigAnalysisRun.id == uuid.UUID(analysis_id)
            )
        )
        row = result.scalar_one_or_none()
        if not row or not row.analysis_data:
            raise HTTPException(404, "Analysis run not found or has no data")

    return {
        "counters": row.analysis_data.get("counters", {}),
        "total_count": row.analysis_data.get("total_count", 0),
        "entity_type_counts": row.analysis_data.get("entity_type_counts", {}),
    }


@router.get("/review/clusters/{analysis_id}")
async def get_clusters(
    analysis_id: str,
    current_user: dict = Depends(require_permission("config_apis", "view")),
):
    """Get clusters with top-5 templates from an analysis run."""
    from app.database import async_session
    from app.models.config_pipeline import ConfigAnalysisRun
    from sqlalchemy import select

    async with async_session() as db:
        result = await db.execute(
            select(ConfigAnalysisRun).where(
                ConfigAnalysisRun.id == uuid.UUID(analysis_id)
            )
        )
        row = result.scalar_one_or_none()
        if not row or not row.analysis_data:
            raise HTTPException(404, "Analysis run not found or has no data")

    return {
        "clusters": row.analysis_data.get("clusters", []),
        "entity_type_counts": row.analysis_data.get("entity_type_counts", {}),
    }


@router.post("/review/preview-payload")
async def preview_payload(
    req: PayloadPreviewRequest,
    current_user: dict = Depends(require_permission("config_apis", "analyze")),
):
    """Build payload preview with optional inclusions.

    Use include_stats=True for the UI display (shows counts/percentages).
    Use include_stats=False to preview what the LLM will actually receive.
    """
    from app.database import async_session
    from app.models.config_pipeline import ConfigAnalysisRun
    from sqlalchemy import select
    from app.services.config_apis.payload_builder import build_payloads_from_clusters

    async with async_session() as db:
        result = await db.execute(
            select(ConfigAnalysisRun).where(
                ConfigAnalysisRun.id == uuid.UUID(req.analysis_id)
            )
        )
        row = result.scalar_one_or_none()
        if not row or not row.analysis_data:
            raise HTTPException(404, "Analysis run not found or has no data")

    payloads = build_payloads_from_clusters(
        analysis_data=row.analysis_data,
        inclusions=req.inclusions,
        include_stats=req.include_stats,
    )

    # Return payload metadata for all doc types
    preview = {}
    for doc_key, data in payloads.items():
        preview[doc_key] = {
            "doc_name": data["doc_name"],
            "focus": data["focus"],
            "payload": data["payload"],
            "chars": data.get("chars", len(data.get("payload", ""))),
            "est_tokens": data.get("est_tokens", len(data.get("payload", "")) // 4),
        }

    return {"payloads": preview}


@router.get("/review/default-prompts")
async def get_default_prompts(
    current_user: dict = Depends(require_permission("config_apis", "view")),
):
    """Return default system prompts, token budgets, and doc metadata."""
    from app.services.config_apis.doc_author import (
        SYSTEM_PROMPTS, TOKEN_BUDGETS, DOC_NAMES,
    )

    return {
        "prompts": SYSTEM_PROMPTS,
        "budgets": TOKEN_BUDGETS,
        "doc_names": DOC_NAMES,
    }


# ══════════════════════════════════════════════════════════════════════
# GENERATION ENDPOINTS
# ══════════════════════════════════════════════════════════════════════

@router.post("/llm/generate")
async def start_generation(
    req: GenerateDocsRequest,
    current_user: dict = Depends(require_permission("config_apis", "generate")),
):
    """Start LLM-based document generation from analysis data (background task)."""
    storage = ConfigStorageService()

    # Verify analysis exists
    analysis = await storage.get_analysis_run(req.analysis_id)
    if not analysis:
        raise HTTPException(404, "Analysis run not found")
    if analysis["status"] != "completed":
        raise HTTPException(400, f"Analysis is {analysis['status']}, not completed")

    user_id = current_user["user_id"]
    org_id = analysis["org_id"]
    progress_cb = _ws_progress_callback(user_id, "config_generation")

    async def _run():
        try:
            from app.services.config_apis.doc_orchestrator import run_generation

            result = await run_generation(
                analysis_id=req.analysis_id,
                user_id=user_id,
                org_id=org_id,
                provider=req.provider,
                model=req.model,
                inclusions=req.inclusions,
                system_prompts=req.system_prompts,
                on_progress=progress_cb,
            )
            await ws_manager.send_to_user(user_id, {
                "type": "config_generation_complete",
                "analysis_id": req.analysis_id,
                "result": result,
            })
        except asyncio.CancelledError:
            logger.info(f"Config generation for {req.analysis_id} cancelled")
            await ws_manager.send_to_user(user_id, {
                "type": "config_generation_cancelled",
                "analysis_id": req.analysis_id,
            })
        except Exception as e:
            logger.exception(f"Config generation for {req.analysis_id} failed")
            await ws_manager.send_to_user(user_id, {
                "type": "config_generation_failed",
                "analysis_id": req.analysis_id,
                "error": str(e),
            })

    task_registry.create_task(
        _run(),
        name=f"config-generation-{req.analysis_id}",
        user_id=user_id,
    )
    return {"analysis_id": req.analysis_id, "status": "started"}


@router.post("/llm/cancel/{analysis_id}")
async def cancel_generation(
    analysis_id: str,
    current_user: dict = Depends(require_permission("config_apis", "generate")),
):
    """Cancel a running generation task."""
    cancelled = task_registry.cancel_task(f"config-generation-{analysis_id}")
    if not cancelled:
        raise HTTPException(404, "No active generation task found")
    return {"cancelled": True, "analysis_id": analysis_id}


@router.get("/llm/docs/{analysis_id}")
async def get_generated_docs(
    analysis_id: str,
    current_user: dict = Depends(require_permission("config_apis", "view")),
):
    """List generated context docs for an analysis run."""
    storage = ConfigStorageService()
    docs = await storage.get_context_docs(analysis_id)
    return {"docs": docs}


@router.get("/llm/doc/{doc_id}")
async def get_generated_doc(
    doc_id: int,
    current_user: dict = Depends(require_permission("config_apis", "view")),
):
    """Get a single generated context document."""
    storage = ConfigStorageService()
    doc = await storage.get_context_doc(doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    return doc


@router.delete("/llm/doc/{doc_id}")
async def delete_generated_doc(
    doc_id: int,
    current_user: dict = Depends(require_permission("config_apis", "extract")),
):
    """Delete a generated context document."""
    storage = ConfigStorageService()
    doc = await storage.get_context_doc(doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    await storage.delete_context_doc(doc_id)
    return {"status": "deleted", "doc_id": doc_id}


@router.get("/llm/docs")
async def list_all_docs(
    org_id: int = Query(...),
    current_user: dict = Depends(require_permission("config_apis", "view")),
):
    """List all active generated docs for an org (independent of analysis runs)."""
    storage = ConfigStorageService()
    docs = await storage.get_all_context_docs(str(org_id))
    return {"docs": docs}
