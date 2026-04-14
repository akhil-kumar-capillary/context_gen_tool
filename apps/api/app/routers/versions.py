"""Version history endpoints — browse, compare, and restore versions."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.rbac import require_permission, require_org_member
from app.database import async_session
from app.services import versioning as ver_svc

logger = logging.getLogger(__name__)

router = APIRouter(tags=["versions"])

ENTITY_TYPES = {"aira_context", "context_tree"}

# Map entity_type -> RBAC module
_MODULE_MAP = {
    "aira_context": "context_management",
    "context_tree": "context_engine",
}


def _validate_entity_type(entity_type: str):
    if entity_type not in ENTITY_TYPES:
        raise HTTPException(400, f"Invalid entity_type: {entity_type}. Must be one of {ENTITY_TYPES}")


# ── List version history ─────────────────────────────────────────────

@router.get("/{entity_type}/{entity_id}/history")
async def list_versions(
    entity_type: str,
    entity_id: str,
    org_id: int = Depends(require_org_member),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(require_permission("context_management", "view")),
):
    """List version history for an entity (newest first)."""
    _validate_entity_type(entity_type)

    async with async_session() as db:
        versions, total = await ver_svc.get_version_history(
            db, entity_type, entity_id, org_id, limit=limit, offset=offset,
        )

    return {
        "versions": [
            {
                "id": str(v.id),
                "version_number": v.version_number,
                "change_type": v.change_type,
                "change_summary": v.change_summary,
                "changed_fields": v.changed_fields,
                "changed_by_user_id": v.changed_by_user_id,
                "created_at": v.created_at.isoformat() if v.created_at else None,
            }
            for v in versions
        ],
        "total": total,
        "has_more": offset + limit < total,
    }


# ── Diff between two versions ───────────────────────────────────────
# NOTE: This must be defined BEFORE /{version_number} so FastAPI doesn't
# try to parse "diff" as an integer.

@router.get("/{entity_type}/{entity_id}/diff")
async def diff_versions(
    entity_type: str,
    entity_id: str,
    from_version: int = Query(..., description="Start version number"),
    to_version: int = Query(..., description="End version number"),
    org_id: int = Depends(require_org_member),
    current_user: dict = Depends(require_permission("context_management", "view")),
):
    """Compare two versions and return structured diff."""
    _validate_entity_type(entity_type)

    if from_version == to_version:
        raise HTTPException(400, "from_version and to_version must be different")

    async with async_session() as db:
        result = await ver_svc.compare_versions(
            db, entity_type, entity_id, from_version, to_version, org_id,
        )

    return result


# ── Get single version detail ───────────────────────────────────────

@router.get("/{entity_type}/{entity_id}/{version_number}")
async def get_version(
    entity_type: str,
    entity_id: str,
    version_number: int,
    org_id: int = Depends(require_org_member),
    current_user: dict = Depends(require_permission("context_management", "view")),
):
    """Get a specific version with full snapshot."""
    _validate_entity_type(entity_type)

    async with async_session() as db:
        ver = await ver_svc.get_version_detail(
            db, entity_type, entity_id, version_number, org_id,
        )

    if not ver:
        raise HTTPException(404, "Version not found")

    return {
        "id": str(ver.id),
        "version_number": ver.version_number,
        "change_type": ver.change_type,
        "change_summary": ver.change_summary,
        "changed_fields": ver.changed_fields,
        "changed_by_user_id": ver.changed_by_user_id,
        "created_at": ver.created_at.isoformat() if ver.created_at else None,
        "snapshot": ver.snapshot,
        "previous_snapshot": ver.previous_snapshot,
    }


# ── Backfill initial version ──────────────────────────────────────────

class BackfillRequest(BaseModel):
    snapshot: dict = Field(..., description="Current state to store as version 1")


@router.post("/{entity_type}/{entity_id}/backfill")
async def backfill_initial_version(
    entity_type: str,
    entity_id: str,
    req: BackfillRequest,
    org_id: int = Depends(require_org_member),
    current_user: dict = Depends(require_permission("context_management", "edit")),
):
    """Create version 1 for a context that predates the versioning system.

    Only creates a version if none exist yet. Idempotent — safe to call multiple times.
    """
    _validate_entity_type(entity_type)

    async with async_session() as db:
        versions, total = await ver_svc.get_version_history(
            db, entity_type, entity_id, org_id, limit=1, offset=0,
        )
        if total > 0:
            return {"created": False, "message": "Versions already exist"}

        await ver_svc.create_version(
            db,
            entity_type=entity_type,
            entity_id=str(entity_id),
            org_id=org_id,
            snapshot=req.snapshot,
            previous_snapshot=None,
            change_type="create",
            change_summary="Initial version (backfill)",
            changed_fields=list(req.snapshot.keys()),
            user_id=current_user.get("user_id"),
        )
        await db.commit()

    return {"created": True, "message": "Version 1 created"}


# ── Restore a version ────────────────────────────────────────────────

class RestoreRequest(BaseModel):
    version: int | None = Field(None, description="Current optimistic lock version (context_tree only)")


@router.post("/{entity_type}/{entity_id}/restore/{version_number}")
async def restore_version(
    entity_type: str,
    entity_id: str,
    version_number: int,
    org_id: int = Depends(require_org_member),
    req: RestoreRequest = RestoreRequest(),
    current_user: dict = Depends(require_permission("context_management", "edit")),
):
    """Restore an entity to a previous version.

    For context_tree: uses optimistic locking via req.version.
    For capillary_context: proxies an update to Capillary.
    Creates a new version record (append-only history).
    """
    _validate_entity_type(entity_type)

    async with async_session() as db:
        snapshot = await ver_svc.get_restore_snapshot(
            db, entity_type, entity_id, version_number, org_id,
        )

    if snapshot is None:
        raise HTTPException(404, "Version not found")

    if entity_type == "context_tree":
        if req.version is None:
            raise HTTPException(400, "version field is required for context_tree restore")

        from app.routers.context_engine import _versioned_tree_update
        result = await _versioned_tree_update(
            entity_id, org_id, snapshot, req.version,
            change_type="version_restore",
            change_summary=f"Restored to version {version_number}",
            user_id=current_user.get("user_id"),
        )
        return {"success": True, "restored_version": version_number, "new_version": result["version"]}

    else:  # capillary_context
        import base64
        import httpx
        from app.utils import md_to_html

        name = snapshot.get("name", "")
        content = snapshot.get("content", "")
        scope = snapshot.get("scope", "org")

        html_content = md_to_html(content)
        encoded = base64.b64encode(html_content.encode("utf-8")).decode("utf-8")

        base_url = current_user.get("base_url", "")
        headers = {
            "Authorization": f"Bearer {current_user.get('capillary_token', '')}",
            "x-cap-api-auth-org-id": str(org_id),
            "Content-Type": "application/x-www-form-urlencoded",
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.put(
                    f"{base_url}/ask-aira/context/update_context",
                    params={"context_id": entity_id},
                    headers=headers,
                    data={"name": name, "context": encoded, "scope": scope},
                )
                if not resp.is_success:
                    raise HTTPException(resp.status_code, "Failed to restore context in Capillary")
        except httpx.RequestError as e:
            logger.error("Network error restoring context %s: %s", entity_id, e)
            raise HTTPException(502, "Failed to connect to Capillary service")

        # Create version record for the restore
        new_snapshot = {"name": name, "content": content, "scope": scope}
        version_recorded = True
        try:
            async with async_session() as db:
                await ver_svc.create_version(
                    db,
                    entity_type="aira_context",
                    entity_id=entity_id,
                    org_id=org_id,
                    snapshot=new_snapshot,
                    previous_snapshot=None,
                    change_type="version_restore",
                    change_summary=f"Restored to version {version_number}",
                    user_id=current_user.get("user_id"),
                )
                await db.commit()
        except Exception:
            logger.warning("Failed to create version for context restore %s", entity_id, exc_info=True)
            version_recorded = False

        return {"success": True, "restored_version": version_number, "version_recorded": version_recorded}
