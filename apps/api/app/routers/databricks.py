"""Databricks source module endpoints.

Extraction, analysis, and LLM-based doc generation for Databricks SQL notebooks.
Long-running ops are launched as background tasks; progress is pushed via WebSocket.
"""

import asyncio
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.auth import get_current_user
from app.core.rbac import require_permission
from app.core.websocket import ws_manager
from app.config import get_databricks_cluster, get_all_configured_clusters, normalize_cluster_key

from app.services.databricks.storage import StorageService
from app.services.databricks.client import DatabricksClient
from app.services.databricks.extraction_orchestrator import run_extraction
from app.services.databricks.analysis_orchestrator import run_analysis
from app.services.databricks.doc_orchestrator import run_generation, preview_payloads
from app.services.databricks.doc_author import DOC_NAMES, SYSTEM_PROMPTS, TOKEN_BUDGETS

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Request/Response Models ──


class StartExtractionRequest(BaseModel):
    root_path: str = Field(default="/Workspace", description="Workspace root path to scan")
    modified_since: Optional[str] = Field(default=None, description="ISO date filter")
    max_workers: int = Field(default=10, ge=1, le=50)
    skip_patterns: list[str] = Field(default_factory=lambda: [".Trash", "Trash", "Archive"])


class StartAnalysisRequest(BaseModel):
    run_id: str = Field(..., description="Extraction run UUID")
    org_id: str = Field(..., description="Organization ID to analyze")


class GenerateDocsRequest(BaseModel):
    analysis_id: str = Field(..., description="Analysis run UUID")
    provider: str = Field(default="anthropic")
    model: str = Field(default="claude-sonnet-4-5-20250929")
    model_map: Optional[dict] = Field(default=None, description="Per-doc model overrides")
    system_prompts: Optional[dict] = Field(default=None, description="Custom system prompts")
    inclusions: Optional[dict] = Field(default=None, description="Payload inclusion overrides")
    focus_domains: Optional[list[str]] = Field(default=None)
    skip_validation: bool = False
    skip_focus_docs: bool = False


class PreviewPayloadRequest(BaseModel):
    analysis_id: str
    inclusions: Optional[dict] = None


# ── Helper: WebSocket progress callback ──


def _ws_progress_callback(user_id: int, channel: str):
    """Create a progress callback that sends events to the user's WebSocket."""
    async def _callback(*args):
        # Handle both dict-based and positional callbacks
        if len(args) == 1 and isinstance(args[0], dict):
            event = args[0]
        elif len(args) == 4:
            # Positional: (phase, completed, total, detail)
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
# CLUSTER ENDPOINTS
# ══════════════════════════════════════════════════════════════════════


@router.get("/clusters")
async def list_clusters(
    current_user: dict = Depends(require_permission("databricks", "view")),
):
    """List available Databricks clusters that have tokens configured.

    Returns cluster key and instance URL.  Tokens are never exposed.
    """
    return {"clusters": get_all_configured_clusters()}


@router.get("/my-cluster")
async def my_cluster(
    current_user: dict = Depends(require_permission("databricks", "view")),
):
    """Return the Databricks cluster resolved from the current user's JWT.

    The cluster is auto-resolved from the Intouch cluster the user signed into.
    """
    auth_cluster = current_user.get("cluster", "")
    key = normalize_cluster_key(auth_cluster)
    cluster = get_databricks_cluster(auth_cluster)
    if not cluster:
        return {
            "cluster_key": key,
            "instance": None,
            "configured": False,
            "message": f"No Databricks token configured for {key} (set DATABRICKS_{key}_TOKEN)",
        }
    return {
        "cluster_key": cluster.key,
        "instance": cluster.instance,
        "configured": True,
    }


# ══════════════════════════════════════════════════════════════════════
# EXTRACTION ENDPOINTS
# ══════════════════════════════════════════════════════════════════════


@router.post("/test-connection")
async def test_connection(
    current_user: dict = Depends(require_permission("databricks", "extract")),
):
    """Test connectivity to the user's Databricks workspace.

    Cluster is auto-resolved from the JWT (Intouch login cluster).
    """
    auth_cluster = current_user.get("cluster", "")
    cluster = get_databricks_cluster(auth_cluster)
    if not cluster:
        key = normalize_cluster_key(auth_cluster)
        raise HTTPException(
            status_code=404,
            detail=f"No Databricks config for cluster {key} (set DATABRICKS_{key}_TOKEN)",
        )

    async with DatabricksClient(cluster.instance, cluster.token) as client:
        result = await client.test_connection()
    return result


@router.post("/extract/start")
async def start_extraction(
    req: StartExtractionRequest,
    current_user: dict = Depends(require_permission("databricks", "extract")),
):
    """Start a notebook extraction pipeline (background task).

    Cluster is auto-resolved from the JWT (Intouch login cluster).
    Returns immediately with a run_id; progress is pushed via WebSocket.
    """
    auth_cluster = current_user.get("cluster", "")
    cluster = get_databricks_cluster(auth_cluster)
    if not cluster:
        key = normalize_cluster_key(auth_cluster)
        raise HTTPException(
            status_code=404,
            detail=f"No Databricks config for cluster {key} (set DATABRICKS_{key}_TOKEN)",
        )

    run_id = str(uuid.uuid4())
    user_id = current_user["user_id"]

    # Build config dict for the orchestrator
    config = {
        "root_path": req.root_path,
        "modified_since": req.modified_since,
        "max_workers": req.max_workers,
        "skip_patterns": req.skip_patterns,
    }

    # Credentials resolved server-side — never from the frontend
    credentials = {
        "instance": cluster.instance,
        "token": cluster.token,
    }

    progress_cb = _ws_progress_callback(user_id, "extraction")

    async def _run():
        try:
            result = await run_extraction(
                run_id=run_id,
                credentials=credentials,
                config=config,
                user_id=user_id,
                on_progress=progress_cb,
            )
            await ws_manager.send_to_user(user_id, {
                "type": "extraction_complete", "run_id": run_id, "result": result,
            })
        except Exception as e:
            logger.exception(f"Extraction {run_id} failed")
            await ws_manager.send_to_user(user_id, {
                "type": "extraction_failed", "run_id": run_id, "error": str(e),
            })

    asyncio.create_task(_run())
    return {"run_id": run_id, "status": "started"}


@router.get("/extract/runs")
async def list_extraction_runs(
    current_user: dict = Depends(require_permission("databricks", "view")),
):
    """List all extraction runs."""
    storage = StorageService()
    runs = await storage.get_extraction_runs()
    return {"runs": runs}


@router.get("/extract/runs/{run_id}")
async def get_extraction_run(
    run_id: str,
    current_user: dict = Depends(require_permission("databricks", "view")),
):
    """Get details of a specific extraction run."""
    storage = StorageService()
    run = await storage.get_extraction_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Extraction run not found")
    return run


@router.get("/extract/runs/{run_id}/sqls")
async def get_extraction_sqls(
    run_id: str,
    org_id: Optional[str] = Query(default=None),
    valid_only: bool = Query(default=False),
    current_user: dict = Depends(require_permission("databricks", "view")),
):
    """Get extracted SQLs for an extraction run."""
    storage = StorageService()
    sqls = await storage.get_extracted_sqls(run_id, valid_only=valid_only, org_id=org_id)
    return {"sqls": sqls, "count": len(sqls)}


@router.get("/extract/runs/{run_id}/notebooks")
async def get_extraction_notebooks(
    run_id: str,
    org_id: Optional[str] = Query(default=None),
    current_user: dict = Depends(require_permission("databricks", "view")),
):
    """Get notebook metadata for an extraction run."""
    storage = StorageService()
    notebooks = await storage.get_notebook_metadata(run_id, org_id=org_id)
    return {"notebooks": notebooks, "count": len(notebooks)}


@router.delete("/extract/runs/{run_id}")
async def delete_extraction_run(
    run_id: str,
    current_user: dict = Depends(require_permission("databricks", "extract")),
):
    """Delete an extraction run and all associated data."""
    storage = StorageService()
    run = await storage.get_extraction_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Extraction run not found")
    await storage.delete_extraction_run(run_id)
    return {"status": "deleted", "run_id": run_id}


@router.get("/storage-stats")
async def storage_stats(
    current_user: dict = Depends(require_permission("databricks", "view")),
):
    """Get row counts for all pipeline tables."""
    storage = StorageService()
    stats = await storage.get_storage_stats()
    return stats


# ══════════════════════════════════════════════════════════════════════
# ANALYSIS ENDPOINTS
# ══════════════════════════════════════════════════════════════════════


@router.get("/analysis/org-ids/{run_id}")
async def get_org_ids(
    run_id: str,
    current_user: dict = Depends(require_permission("databricks", "view")),
):
    """Get distinct org IDs found in an extraction run."""
    storage = StorageService()
    orgs = await storage.get_distinct_org_ids(run_id)
    return {"org_ids": orgs}


@router.post("/analysis/start")
async def start_analysis(
    req: StartAnalysisRequest,
    current_user: dict = Depends(require_permission("databricks", "analyze")),
):
    """Start SQL analysis pipeline (background task).

    Returns immediately with an analysis_id; progress is pushed via WebSocket.
    """
    user_id = current_user["user_id"]
    progress_cb = _ws_progress_callback(user_id, "analysis")

    async def _run():
        try:
            result = await run_analysis(
                run_id=req.run_id,
                org_id=req.org_id,
                user_id=user_id,
                on_progress=progress_cb,
            )
            await ws_manager.send_to_user(user_id, {
                "type": "analysis_complete", "result": result,
            })
        except Exception as e:
            logger.exception(f"Analysis for run {req.run_id} failed")
            await ws_manager.send_to_user(user_id, {
                "type": "analysis_failed", "run_id": req.run_id, "error": str(e),
            })

    asyncio.create_task(_run())
    return {"status": "started", "run_id": req.run_id, "org_id": req.org_id}


@router.get("/analysis/history")
async def analysis_history(
    current_user: dict = Depends(require_permission("databricks", "view")),
):
    """List all analysis runs with lightweight metadata."""
    storage = StorageService()
    runs = await storage.get_analysis_history()
    return {"runs": runs}


@router.get("/analysis/history/{run_id}")
async def analysis_history_for_run(
    run_id: str,
    current_user: dict = Depends(require_permission("databricks", "view")),
):
    """List analysis runs for a specific extraction run."""
    storage = StorageService()
    runs = await storage.get_analysis_history_for_run(run_id)
    return {"runs": runs}


@router.get("/analysis/{analysis_id}")
async def get_analysis(
    analysis_id: str,
    current_user: dict = Depends(require_permission("databricks", "view")),
):
    """Get full details of a specific analysis run."""
    storage = StorageService()
    analysis = await storage.get_analysis_run(analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis run not found")
    return analysis


@router.get("/analysis/{analysis_id}/fingerprints")
async def get_fingerprints(
    analysis_id: str,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    current_user: dict = Depends(require_permission("databricks", "view")),
):
    """Get paginated fingerprints for an analysis run."""
    storage = StorageService()
    fingerprints, total = await storage.get_analysis_fingerprints(analysis_id, limit, offset)
    return {"fingerprints": fingerprints, "total": total, "limit": limit, "offset": offset}


@router.get("/analysis/{analysis_id}/notebooks")
async def get_analysis_notebooks(
    analysis_id: str,
    current_user: dict = Depends(require_permission("databricks", "view")),
):
    """Get notebooks linked to an analysis run."""
    storage = StorageService()
    notebooks = await storage.get_analysis_notebooks(analysis_id)
    return {"notebooks": notebooks, "count": len(notebooks)}


@router.delete("/analysis/{analysis_id}")
async def delete_analysis(
    analysis_id: str,
    current_user: dict = Depends(require_permission("databricks", "analyze")),
):
    """Delete an analysis run and all associated data."""
    storage = StorageService()
    analysis = await storage.get_analysis_run(analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis run not found")
    await storage.delete_analysis_run(analysis_id)
    return {"status": "deleted", "analysis_id": analysis_id}


# ══════════════════════════════════════════════════════════════════════
# LLM / DOCUMENT GENERATION ENDPOINTS
# ══════════════════════════════════════════════════════════════════════


@router.get("/llm/default-prompts")
async def default_prompts(
    current_user: dict = Depends(require_permission("databricks", "view")),
):
    """Return the default system prompts, doc names, and token budgets."""
    return {
        "system_prompts": SYSTEM_PROMPTS,
        "doc_names": DOC_NAMES,
        "token_budgets": TOKEN_BUDGETS,
    }


@router.post("/llm/preview-payload")
async def preview_payload(
    req: PreviewPayloadRequest,
    current_user: dict = Depends(require_permission("databricks", "view")),
):
    """Build and return payloads without calling LLM. For inspection/preview."""
    try:
        result = await preview_payloads(
            analysis_id=req.analysis_id,
            inclusions=req.inclusions,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/llm/generate")
async def generate_docs(
    req: GenerateDocsRequest,
    current_user: dict = Depends(require_permission("databricks", "generate")),
):
    """Start LLM document generation pipeline (background task).

    Returns immediately; progress is pushed via WebSocket.
    """
    user_id = current_user["user_id"]
    progress_cb = _ws_progress_callback(user_id, "llm")

    async def _run():
        try:
            result = await run_generation(
                analysis_id=req.analysis_id,
                user_id=user_id,
                provider=req.provider,
                model=req.model,
                model_map=req.model_map,
                system_prompts=req.system_prompts,
                inclusions=req.inclusions,
                focus_domains=req.focus_domains,
                skip_validation=req.skip_validation,
                skip_focus_docs=req.skip_focus_docs,
                on_progress=progress_cb,
            )
            await ws_manager.send_to_user(user_id, {
                "type": "generation_complete",
                "analysis_id": req.analysis_id,
                "result": result,
            })
        except Exception as e:
            logger.exception(f"Doc generation for {req.analysis_id} failed")
            await ws_manager.send_to_user(user_id, {
                "type": "generation_failed",
                "analysis_id": req.analysis_id,
                "error": str(e),
            })

    asyncio.create_task(_run())
    return {"status": "started", "analysis_id": req.analysis_id}


@router.get("/llm/docs/{analysis_id}")
async def list_docs(
    analysis_id: str,
    current_user: dict = Depends(require_permission("databricks", "view")),
):
    """List generated context documents for an analysis."""
    storage = StorageService()
    docs = await storage.get_context_docs(analysis_id)
    return {"docs": docs, "count": len(docs)}


@router.get("/llm/doc/{doc_id}")
async def get_doc(
    doc_id: int,
    current_user: dict = Depends(require_permission("databricks", "view")),
):
    """Get a single context document by ID."""
    storage = StorageService()
    doc = await storage.get_context_doc(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc
