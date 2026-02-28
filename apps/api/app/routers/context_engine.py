"""Context Engine router — REST endpoints for tree generation and management."""

import asyncio
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, update, desc, delete

from app.core.rbac import require_permission
from app.core.websocket import ws_manager
from app.core.task_registry import task_registry
from app.database import async_session
from app.models.context_tree import ContextTreeRun
from app.utils import utcnow

router = APIRouter(tags=["context-engine"])


# ── Request / Response Models ─────────────────────────────────────────


class GenerateRequest(BaseModel):
    provider: str = Field(default="anthropic", description="LLM provider")
    model: str = Field(default="claude-opus-4-6", description="LLM model")
    sanitize: bool = Field(default=False, description="Run content sanitization via blueprint")
    blueprint_text: str | None = Field(default=None, description="Custom blueprint text (optional)")


class UpdateTreeRequest(BaseModel):
    tree_data: dict = Field(..., description="Updated tree structure")


class AddNodeRequest(BaseModel):
    parent_id: str = Field(..., description="ID of the parent node")
    node: dict = Field(..., description="New node data (name, desc, visibility, type)")


class UpdateNodeRequest(BaseModel):
    name: Optional[str] = None
    desc: Optional[str] = None
    visibility: Optional[str] = None
    health: Optional[int] = None


class RestructureRequest(BaseModel):
    node_ids: list[str] = Field(..., description="IDs of nodes to restructure")
    instruction: str = Field(..., description="What to do: merge, split, reorganize, etc.")


# ── Helper: tree node operations ──────────────────────────────────────


def _find_node(tree: dict, node_id: str) -> dict | None:
    """Recursively find a node by ID in the tree."""
    if tree.get("id") == node_id:
        return tree
    for child in tree.get("children", []):
        found = _find_node(child, node_id)
        if found:
            return found
    return None


def _find_parent(tree: dict, node_id: str) -> dict | None:
    """Find the parent of a node by ID."""
    for child in tree.get("children", []):
        if child.get("id") == node_id:
            return tree
        found = _find_parent(child, node_id)
        if found:
            return found
    return None


def _remove_node(tree: dict, node_id: str) -> bool:
    """Remove a node by ID from the tree. Returns True if found and removed."""
    children = tree.get("children", [])
    for i, child in enumerate(children):
        if child.get("id") == node_id:
            children.pop(i)
            return True
        if _remove_node(child, node_id):
            return True
    return False


def _count_nodes(tree: dict) -> int:
    """Count total nodes in the tree."""
    count = 1
    for child in tree.get("children", []):
        count += _count_nodes(child)
    return count


def _serialize_run(run) -> dict:
    """Serialize a ContextTreeRun to a dict (without tree_data for list views)."""
    return {
        "id": str(run.id),
        "status": run.status,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "input_context_count": run.input_context_count,
        "input_sources": run.input_sources,
        "model_used": run.model_used,
        "provider_used": run.provider_used,
        "token_usage": run.token_usage,
        "error_message": run.error_message,
        "progress_data": run.progress_data,
    }


def _serialize_run_full(run) -> dict:
    """Serialize a ContextTreeRun including tree_data."""
    d = _serialize_run(run)
    d["tree_data"] = run.tree_data
    return d


# ── Endpoints ─────────────────────────────────────────────────────────


@router.post("/generate")
async def generate_tree(
    org_id: int = Query(...),
    req: GenerateRequest = GenerateRequest(),
    current_user: dict = Depends(require_permission("context_engine", "generate")),
):
    """Start tree generation (background task).

    Collects all contexts, sends them to LLM, and builds a tree.
    Returns immediately with a run_id; progress is pushed via WebSocket.
    """
    user_id = current_user["user_id"]

    # Create the run record
    run_id = str(uuid.uuid4())
    async with async_session() as db:
        run = ContextTreeRun(
            id=uuid.UUID(run_id),
            user_id=user_id,
            org_id=org_id,
            status="running",
        )
        db.add(run)
        await db.commit()

    # Launch background task
    cancel_event = asyncio.Event()

    async def _run():
        from app.services.context_engine.orchestrator import run_tree_generation
        await run_tree_generation(
            run_id=run_id,
            user=current_user,
            org_id=org_id,
            ws_manager=ws_manager,
            user_id=user_id,
            cancel_event=cancel_event,
            sanitize=req.sanitize,
            blueprint_text=req.blueprint_text,
        )

    task_registry.create_task(
        _run(),
        name=f"context-engine-{run_id}",
        user_id=user_id,
    )

    return {"run_id": run_id, "status": "started"}


@router.post("/generate/cancel/{run_id}")
async def cancel_generation(
    run_id: str,
    current_user: dict = Depends(require_permission("context_engine", "generate")),
):
    """Cancel a running tree generation task."""
    cancelled = task_registry.cancel_task(f"context-engine-{run_id}")
    if not cancelled:
        raise HTTPException(404, "No active tree generation task found for this run_id")
    return {"cancelled": True, "run_id": run_id}


@router.get("/runs")
async def list_runs(
    org_id: int = Query(...),
    current_user: dict = Depends(require_permission("context_engine", "view")),
):
    """List all tree runs for the organization."""
    async with async_session() as db:
        result = await db.execute(
            select(ContextTreeRun)
            .where(ContextTreeRun.org_id == org_id)
            .order_by(desc(ContextTreeRun.created_at))
        )
        runs = result.scalars().all()
    return {"runs": [_serialize_run(r) for r in runs]}


@router.get("/runs/latest")
async def get_latest_run(
    org_id: int = Query(...),
    current_user: dict = Depends(require_permission("context_engine", "view")),
):
    """Get the latest completed tree run for the organization."""
    async with async_session() as db:
        result = await db.execute(
            select(ContextTreeRun)
            .where(
                ContextTreeRun.org_id == org_id,
                ContextTreeRun.status == "completed",
            )
            .order_by(desc(ContextTreeRun.created_at))
            .limit(1)
        )
        run = result.scalar_one_or_none()

    if not run:
        return {"run": None}
    return _serialize_run_full(run)


@router.get("/runs/{run_id}")
async def get_run(
    run_id: str,
    current_user: dict = Depends(require_permission("context_engine", "view")),
):
    """Get a specific tree run with full tree_data."""
    async with async_session() as db:
        result = await db.execute(
            select(ContextTreeRun)
            .where(ContextTreeRun.id == uuid.UUID(run_id))
        )
        run = result.scalar_one_or_none()

    if not run:
        raise HTTPException(404, "Tree run not found")
    return _serialize_run_full(run)


@router.put("/runs/{run_id}/tree")
async def update_tree(
    run_id: str,
    req: UpdateTreeRequest,
    current_user: dict = Depends(require_permission("context_engine", "edit")),
):
    """Update the tree structure (after user edits in the UI)."""
    async with async_session() as db:
        result = await db.execute(
            select(ContextTreeRun)
            .where(ContextTreeRun.id == uuid.UUID(run_id))
        )
        run = result.scalar_one_or_none()
        if not run:
            raise HTTPException(404, "Tree run not found")

        await db.execute(
            update(ContextTreeRun)
            .where(ContextTreeRun.id == uuid.UUID(run_id))
            .values(tree_data=req.tree_data)
        )
        await db.commit()

    return {"success": True}


@router.delete("/runs/{run_id}")
async def delete_run(
    run_id: str,
    current_user: dict = Depends(require_permission("context_engine", "edit")),
):
    """Delete a tree run."""
    async with async_session() as db:
        result = await db.execute(
            select(ContextTreeRun)
            .where(ContextTreeRun.id == uuid.UUID(run_id))
        )
        run = result.scalar_one_or_none()
        if not run:
            raise HTTPException(404, "Tree run not found")

        await db.execute(
            delete(ContextTreeRun)
            .where(ContextTreeRun.id == uuid.UUID(run_id))
        )
        await db.commit()

    return {"success": True}


@router.post("/runs/{run_id}/node")
async def add_node(
    run_id: str,
    req: AddNodeRequest,
    current_user: dict = Depends(require_permission("context_engine", "edit")),
):
    """Add a new node to the tree."""
    async with async_session() as db:
        result = await db.execute(
            select(ContextTreeRun)
            .where(ContextTreeRun.id == uuid.UUID(run_id))
        )
        run = result.scalar_one_or_none()
        if not run or not run.tree_data:
            raise HTTPException(404, "Tree run not found or has no tree data")

        tree = run.tree_data
        parent = _find_node(tree, req.parent_id)
        if not parent:
            raise HTTPException(404, f"Parent node '{req.parent_id}' not found in tree")

        # Ensure parent has children array
        if "children" not in parent:
            parent["children"] = []

        # Build the new node
        new_node = {
            "id": req.node.get("id", f"custom_{uuid.uuid4().hex[:8]}"),
            "name": req.node.get("name", "New Node"),
            "type": req.node.get("type", "leaf"),
            "health": req.node.get("health", 80),
            "visibility": req.node.get("visibility", "public"),
            "desc": req.node.get("desc", ""),
            "source": "manual",
        }
        if req.node.get("children"):
            new_node["children"] = req.node["children"]

        parent["children"].append(new_node)

        await db.execute(
            update(ContextTreeRun)
            .where(ContextTreeRun.id == uuid.UUID(run_id))
            .values(tree_data=tree)
        )
        await db.commit()

    return {"tree_data": tree}


@router.put("/runs/{run_id}/node/{node_id}")
async def update_node(
    run_id: str,
    node_id: str,
    req: UpdateNodeRequest,
    current_user: dict = Depends(require_permission("context_engine", "edit")),
):
    """Update a specific node in the tree."""
    async with async_session() as db:
        result = await db.execute(
            select(ContextTreeRun)
            .where(ContextTreeRun.id == uuid.UUID(run_id))
        )
        run = result.scalar_one_or_none()
        if not run or not run.tree_data:
            raise HTTPException(404, "Tree run not found or has no tree data")

        tree = run.tree_data
        node = _find_node(tree, node_id)
        if not node:
            raise HTTPException(404, f"Node '{node_id}' not found in tree")

        # Apply updates
        if req.name is not None:
            node["name"] = req.name
        if req.desc is not None:
            node["desc"] = req.desc
        if req.visibility is not None:
            node["visibility"] = req.visibility
        if req.health is not None:
            node["health"] = req.health

        await db.execute(
            update(ContextTreeRun)
            .where(ContextTreeRun.id == uuid.UUID(run_id))
            .values(tree_data=tree)
        )
        await db.commit()

    return {"tree_data": tree}


@router.delete("/runs/{run_id}/node/{node_id}")
async def delete_node(
    run_id: str,
    node_id: str,
    current_user: dict = Depends(require_permission("context_engine", "edit")),
):
    """Remove a node from the tree."""
    if node_id == "root":
        raise HTTPException(400, "Cannot delete the root node")

    async with async_session() as db:
        result = await db.execute(
            select(ContextTreeRun)
            .where(ContextTreeRun.id == uuid.UUID(run_id))
        )
        run = result.scalar_one_or_none()
        if not run or not run.tree_data:
            raise HTTPException(404, "Tree run not found or has no tree data")

        tree = run.tree_data
        removed = _remove_node(tree, node_id)
        if not removed:
            raise HTTPException(404, f"Node '{node_id}' not found in tree")

        await db.execute(
            update(ContextTreeRun)
            .where(ContextTreeRun.id == uuid.UUID(run_id))
            .values(tree_data=tree)
        )
        await db.commit()

    return {"tree_data": tree}


@router.post("/runs/{run_id}/sync")
async def sync_to_capillary(
    run_id: str,
    org_id: int = Query(...),
    current_user: dict = Depends(require_permission("context_engine", "sync")),
):
    """Sync tree leaf nodes to Capillary (upload/update contexts)."""
    import base64
    import httpx

    async with async_session() as db:
        result = await db.execute(
            select(ContextTreeRun)
            .where(ContextTreeRun.id == uuid.UUID(run_id))
        )
        run = result.scalar_one_or_none()
        if not run or not run.tree_data:
            raise HTTPException(404, "Tree run not found or has no tree data")

    tree = run.tree_data
    token = current_user.get("capillary_token", "")
    base_url = current_user.get("base_url", "")
    headers = {
        "Authorization": f"Bearer {token}",
        "x-cap-api-auth-org-id": str(org_id),
    }

    # Collect all leaf nodes
    leaves = []
    _collect_leaves(tree, leaves)

    # Filter to public leaves only (private ones may contain secrets)
    public_leaves = [l for l in leaves if l.get("visibility", "public") == "public"]

    results = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        for leaf in public_leaves:
            name = leaf.get("name", "Unnamed")
            content = leaf.get("desc", "")
            if not content:
                results.append({"name": name, "status": "skipped", "reason": "empty content"})
                continue

            encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")
            try:
                resp = await client.post(
                    f"{base_url}/ask-aira/context/upload_context",
                    headers={
                        **headers,
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                    data={
                        "name": name,
                        "context": encoded,
                        "scope": "org",
                    },
                )
                if resp.status_code == 200:
                    results.append({"name": name, "status": "uploaded"})
                else:
                    results.append({
                        "name": name,
                        "status": "failed",
                        "reason": f"HTTP {resp.status_code}",
                    })
            except Exception as e:
                results.append({"name": name, "status": "failed", "reason": str(e)})

    return {
        "results": results,
        "uploaded": sum(1 for r in results if r["status"] == "uploaded"),
        "total": len(public_leaves),
    }


def _collect_leaves(node: dict, leaves: list):
    """Recursively collect all leaf nodes from the tree."""
    if node.get("type") == "leaf":
        leaves.append(node)
    for child in node.get("children", []):
        _collect_leaves(child, leaves)


@router.post("/runs/{run_id}/restructure")
async def restructure_tree(
    run_id: str,
    req: RestructureRequest,
    current_user: dict = Depends(require_permission("context_engine", "edit")),
):
    """Ask LLM to restructure part of the tree.

    Returns a proposal with before/after comparison and health impact.
    The proposal needs user approval before applying.
    """
    async with async_session() as db:
        result = await db.execute(
            select(ContextTreeRun)
            .where(ContextTreeRun.id == uuid.UUID(run_id))
        )
        run = result.scalar_one_or_none()
        if not run or not run.tree_data:
            raise HTTPException(404, "Tree run not found or has no tree data")

    from app.services.context_engine.restructure_proposer import propose_restructure

    try:
        proposal = await propose_restructure(
            tree=run.tree_data,
            node_ids=req.node_ids,
            instruction=req.instruction,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))

    return {"proposal": proposal}


@router.post("/runs/{run_id}/restructure/apply")
async def apply_restructure(
    run_id: str,
    req: UpdateTreeRequest,
    current_user: dict = Depends(require_permission("context_engine", "edit")),
):
    """Apply a previously proposed restructure by saving the new tree."""
    async with async_session() as db:
        result = await db.execute(
            select(ContextTreeRun)
            .where(ContextTreeRun.id == uuid.UUID(run_id))
        )
        run = result.scalar_one_or_none()
        if not run:
            raise HTTPException(404, "Tree run not found")

        await db.execute(
            update(ContextTreeRun)
            .where(ContextTreeRun.id == uuid.UUID(run_id))
            .values(tree_data=req.tree_data)
        )
        await db.commit()

    return {"success": True, "tree_data": req.tree_data}
