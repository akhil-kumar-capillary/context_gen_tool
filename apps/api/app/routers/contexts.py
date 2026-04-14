"""Context CRUD — proxies requests to Capillary's context API.

Each mutation (create/update/archive/restore) also writes a version record
to the local content_versions table so users can browse history and restore.
"""
import base64
import logging
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from app.core.rbac import require_permission
from app.database import async_session
from app.schemas.context import ContextCreateRequest, ContextUpdateRequest, BulkUploadRequest
from app.services.versioning import create_version, get_version_detail
from app.utils import md_to_html

logger = logging.getLogger(__name__)

router = APIRouter()


def _headers(user: dict, org_id: int) -> dict:
    return {
        "Authorization": f"Bearer {user['capillary_token']}",
        "x-cap-api-auth-org-id": str(org_id),
    }


@router.get("/list")
async def list_contexts(
    org_id: int = Query(...),
    is_active: bool | None = Query(None),
    current_user: dict = Depends(require_permission("context_management", "view")),
):
    params: dict[str, str] = {}
    if is_active is not None:
        params["is_active"] = str(is_active).lower()
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{current_user['base_url']}/ask-aira/context/list",
            params=params,
            headers=_headers(current_user, org_id),
        )
        if not resp.is_success:
            raise HTTPException(resp.status_code, "Failed to fetch contexts")
        return resp.json()


@router.post("/upload")
async def upload_context(
    req: ContextCreateRequest,
    org_id: int = Query(...),
    current_user: dict = Depends(require_permission("context_management", "create")),
):
    html_content = md_to_html(req.content)
    encoded = base64.b64encode(html_content.encode("utf-8")).decode("utf-8")
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{current_user['base_url']}/ask-aira/context/upload_context",
            headers={
                **_headers(current_user, org_id),
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={"name": req.name, "context": encoded, "scope": req.scope},
        )
        if not resp.is_success:
            logger.warning("Context upload failed (HTTP %d): %s", resp.status_code, resp.text[:200])
            raise HTTPException(resp.status_code, "Failed to upload context")

        capillary_resp = resp.json()

    # Create version 1 (initial snapshot) — store HTML to stay consistent
    # with what Capillary returns on subsequent list calls.
    context_id = str(
        capillary_resp.get("id")
        or capillary_resp.get("context_id")
        or capillary_resp.get("data", {}).get("id", "")
    )
    if context_id:
        snapshot = {"name": req.name, "content": html_content, "scope": req.scope}
        try:
            async with async_session() as db:
                await create_version(
                    db,
                    entity_type="aira_context",
                    entity_id=context_id,
                    org_id=org_id,
                    snapshot=snapshot,
                    previous_snapshot=None,
                    change_type="create",
                    change_summary=f"Created context '{req.name}'",
                    changed_fields=["name", "content", "scope"],
                    user_id=current_user.get("user_id"),
                )
                await db.commit()
        except Exception:
            logger.warning("Failed to create version for new context %s", context_id, exc_info=True)

    return capillary_resp


@router.put("/update")
async def update_context(
    req: ContextUpdateRequest,
    org_id: int = Query(...),
    current_user: dict = Depends(require_permission("context_management", "edit")),
):
    logger.info("update_context called: context_id=%s, org_id=%s", req.context_id, org_id)
    # Look up the previous version's snapshot (if any) before the Capillary call
    previous_snapshot = None
    try:
        async with async_session() as db:
            from sqlalchemy import select, func
            from app.models.content_version import ContentVersion

            result = await db.execute(
                select(ContentVersion.snapshot)
                .where(
                    ContentVersion.entity_type == "aira_context",
                    ContentVersion.entity_id == str(req.context_id),
                    ContentVersion.org_id == org_id,
                )
                .order_by(ContentVersion.version_number.desc())
                .limit(1)
            )
            previous_snapshot = result.scalar_one_or_none()
    except Exception:
        logger.debug("Could not fetch previous version for context %s", req.context_id, exc_info=True)

    html_content = md_to_html(req.content)
    encoded = base64.b64encode(html_content.encode("utf-8")).decode("utf-8")
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.put(
            f"{current_user['base_url']}/ask-aira/context/update_context",
            params={"context_id": req.context_id},
            headers={
                **_headers(current_user, org_id),
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={"name": req.name, "context": encoded, "scope": req.scope},
        )
        if not resp.is_success:
            raise HTTPException(resp.status_code, "Failed to update context")

        capillary_resp = resp.json()

    # Create a version record for the update (always store HTML for consistency)
    new_snapshot = {"name": req.name, "content": html_content, "scope": req.scope}
    changed_fields = []
    if previous_snapshot:
        for field in ("name", "content", "scope"):
            if previous_snapshot.get(field) != new_snapshot.get(field):
                changed_fields.append(field)
    else:
        changed_fields = ["name", "content", "scope"]

    try:
        async with async_session() as db:
            ver = await create_version(
                db,
                entity_type="aira_context",
                entity_id=str(req.context_id),
                org_id=org_id,
                snapshot=new_snapshot,
                previous_snapshot=previous_snapshot,
                change_type="update",
                change_summary=f"Updated context '{req.name}'" + (
                    f": {', '.join(changed_fields)}" if changed_fields else ""
                ),
                changed_fields=changed_fields or None,
                user_id=current_user.get("user_id"),
            )
            await db.commit()
            logger.info("Created version v%d for context %s", ver.version_number, req.context_id)
    except Exception:
        logger.exception("Failed to create version for context update %s", req.context_id)

    return capillary_resp


@router.put("/archive")
async def archive_context(
    context_id: str = Query(...),
    org_id: int = Query(...),
    current_user: dict = Depends(require_permission("context_management", "edit")),
):
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.put(
            f"{current_user['base_url']}/ask-aira/context/archive_context",
            params={"context_id": context_id},
            headers=_headers(current_user, org_id),
        )
        if not resp.is_success:
            raise HTTPException(resp.status_code, "Failed to archive context")

        capillary_resp = resp.json()

    # Record archive event in version history
    try:
        async with async_session() as db:
            from sqlalchemy import select
            from app.models.content_version import ContentVersion

            result = await db.execute(
                select(ContentVersion.snapshot)
                .where(
                    ContentVersion.entity_type == "aira_context",
                    ContentVersion.entity_id == str(context_id),
                    ContentVersion.org_id == org_id,
                )
                .order_by(ContentVersion.version_number.desc())
                .limit(1)
            )
            latest_snapshot = result.scalar_one_or_none() or {}

            await create_version(
                db,
                entity_type="aira_context",
                entity_id=str(context_id),
                org_id=org_id,
                snapshot={**latest_snapshot, "_archived": True},
                previous_snapshot=latest_snapshot or None,
                change_type="archive",
                change_summary="Archived context",
                user_id=current_user.get("user_id"),
            )
            await db.commit()
    except Exception:
        logger.warning("Failed to create version for context archive %s", context_id, exc_info=True)

    return capillary_resp


@router.put("/restore")
async def restore_context(
    context_id: str = Query(...),
    org_id: int = Query(...),
    current_user: dict = Depends(require_permission("context_management", "edit")),
):
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.put(
            f"{current_user['base_url']}/ask-aira/context/restore_context",
            params={"context_id": context_id},
            headers=_headers(current_user, org_id),
        )
        if not resp.is_success:
            raise HTTPException(resp.status_code, "Failed to restore context")

        capillary_resp = resp.json()

    # Record restore event in version history
    try:
        async with async_session() as db:
            from sqlalchemy import select
            from app.models.content_version import ContentVersion

            result = await db.execute(
                select(ContentVersion.snapshot)
                .where(
                    ContentVersion.entity_type == "aira_context",
                    ContentVersion.entity_id == str(context_id),
                    ContentVersion.org_id == org_id,
                )
                .order_by(ContentVersion.version_number.desc())
                .limit(1)
            )
            latest_snapshot = result.scalar_one_or_none() or {}
            restored_snapshot = {k: v for k, v in latest_snapshot.items() if k != "_archived"}

            await create_version(
                db,
                entity_type="aira_context",
                entity_id=str(context_id),
                org_id=org_id,
                snapshot=restored_snapshot,
                previous_snapshot=latest_snapshot or None,
                change_type="restore",
                change_summary="Restored context from archive",
                user_id=current_user.get("user_id"),
            )
            await db.commit()
    except Exception:
        logger.warning("Failed to create version for context restore %s", context_id, exc_info=True)

    return capillary_resp


@router.post("/bulk-upload")
async def bulk_upload(
    req: BulkUploadRequest,
    org_id: int = Query(...),
    current_user: dict = Depends(require_permission("context_management", "create")),
):
    results = []
    for item in req.contexts:
        try:
            existing_id = req.existing_name_map.get(item.name)
            if existing_id:
                resp = await update_context(
                    ContextUpdateRequest(
                        context_id=existing_id,
                        name=item.name,
                        content=item.content,
                        scope=item.scope,
                    ),
                    org_id=org_id,
                    current_user=current_user,
                )
                results.append({"name": item.name, "status": "updated", "data": resp})
            else:
                resp = await upload_context(
                    ContextCreateRequest(
                        name=item.name,
                        content=item.content,
                        scope=item.scope,
                    ),
                    org_id=org_id,
                    current_user=current_user,
                )
                results.append({"name": item.name, "status": "created", "data": resp})
        except Exception as e:
            results.append({"name": item.name, "status": "error", "error": str(e)})
    return {"results": results}
