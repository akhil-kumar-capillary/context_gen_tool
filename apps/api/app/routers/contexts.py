"""Context CRUD — proxies requests to Capillary's context API."""
import base64
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from app.core.rbac import require_permission
from app.schemas.context import ContextCreateRequest, ContextUpdateRequest, BulkUploadRequest

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
    encoded = base64.b64encode(req.content.encode("utf-8")).decode("utf-8")
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
            detail = resp.text[:500] if resp.text else "Failed to upload context"
            raise HTTPException(resp.status_code, detail)
        return resp.json()


@router.put("/update")
async def update_context(
    req: ContextUpdateRequest,
    org_id: int = Query(...),
    current_user: dict = Depends(require_permission("context_management", "edit")),
):
    encoded = base64.b64encode(req.content.encode("utf-8")).decode("utf-8")
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
        return resp.json()


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
        return resp.json()


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
        return resp.json()


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
