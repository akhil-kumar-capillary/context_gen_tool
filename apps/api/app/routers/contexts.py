"""Context CRUD — proxies requests to Capillary's context API."""
import base64
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from app.core.auth import get_current_user
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
    current_user: dict = Depends(get_current_user),
):
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{current_user['base_url']}/ask-aira/context/list",
            headers=_headers(current_user, org_id),
        )
        if resp.status_code != 200:
            raise HTTPException(resp.status_code, "Failed to fetch contexts")
        return resp.json()


@router.post("/upload")
async def upload_context(
    req: ContextCreateRequest,
    org_id: int = Query(...),
    current_user: dict = Depends(get_current_user),
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
        if resp.status_code != 200:
            raise HTTPException(resp.status_code, "Failed to upload context")
        return resp.json()


@router.put("/update")
async def update_context(
    req: ContextUpdateRequest,
    org_id: int = Query(...),
    current_user: dict = Depends(get_current_user),
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
        if resp.status_code != 200:
            raise HTTPException(resp.status_code, "Failed to update context")
        return resp.json()


@router.delete("/delete")
async def delete_context(
    context_id: str = Query(...),
    org_id: int = Query(...),
    current_user: dict = Depends(get_current_user),
):
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.delete(
            f"{current_user['base_url']}/ask-aira/context/delete_context",
            params={"context_id": context_id},
            headers=_headers(current_user, org_id),
        )
        if resp.status_code != 200:
            raise HTTPException(resp.status_code, "Failed to delete context")
        return {"success": True}


@router.post("/bulk-upload")
async def bulk_upload(
    req: BulkUploadRequest,
    org_id: int = Query(...),
    current_user: dict = Depends(get_current_user),
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
