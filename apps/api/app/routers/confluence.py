"""Confluence source module — browse spaces, search pages, extract content."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from pydantic import BaseModel

from app.core.auth import get_current_user
from app.core.rbac import require_permission
from app.services.sources.confluence.client import ConfluenceClient
from app.database import async_session
from app.models.source_run import ConfluenceExtraction

router = APIRouter()


# ── helpers ───────────────────────────────────────────────────────────

def _get_client() -> ConfluenceClient:
    """Instantiate a Confluence client from global settings."""
    try:
        return ConfluenceClient()
    except ValueError as e:
        raise HTTPException(400, str(e))


# ── schemas ───────────────────────────────────────────────────────────

class TestConnectionRequest(BaseModel):
    url: Optional[str] = None
    email: Optional[str] = None
    api_token: Optional[str] = None


class ExtractRequest(BaseModel):
    space_key: str
    page_ids: list[str] = []           # if empty, extract all pages in space
    max_pages: int = 50


class SearchRequest(BaseModel):
    query: str
    space_key: Optional[str] = None
    limit: int = 10


# ── endpoints ─────────────────────────────────────────────────────────

@router.post("/test-connection")
async def test_connection(
    req: TestConnectionRequest = Body(TestConnectionRequest()),
    current_user: dict = Depends(require_permission("confluence", "view")),
):
    """Test Confluence Cloud connectivity."""
    try:
        client = ConfluenceClient(
            url=req.url or None,
            email=req.email or None,
            api_token=req.api_token or None,
        )
        ok = await client.test_connection()
        return {"connected": ok, "url": client.url}
    except ValueError as e:
        return {"connected": False, "error": str(e)}
    except Exception as e:
        return {"connected": False, "error": str(e)}


@router.get("/spaces")
async def list_spaces(
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(require_permission("confluence", "view")),
):
    """List available Confluence spaces."""
    client = _get_client()
    spaces = await client.list_spaces(limit=limit)
    return {"spaces": spaces}


@router.post("/search")
async def search_pages(
    req: SearchRequest,
    current_user: dict = Depends(require_permission("confluence", "view")),
):
    """CQL full-text search across Confluence pages."""
    client = _get_client()
    results = await client.search_pages(
        query=req.query, space_key=req.space_key, limit=req.limit
    )
    return {"results": results}


@router.get("/spaces/{space_key}/pages")
async def get_space_pages(
    space_key: str,
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(require_permission("confluence", "view")),
):
    """Get root-level pages of a space."""
    client = _get_client()
    pages = await client.get_space_pages(space_key, limit=limit)
    return {"pages": pages}


@router.get("/pages/{page_id}")
async def get_page(
    page_id: str,
    current_user: dict = Depends(require_permission("confluence", "view")),
):
    """Fetch a single page with Markdown content."""
    client = _get_client()
    try:
        page = await client.get_page(page_id)
        return page
    except Exception as e:
        raise HTTPException(404, f"Page not found: {e}")


@router.get("/pages/{page_id}/children")
async def get_child_pages(
    page_id: str,
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(require_permission("confluence", "view")),
):
    """Get child pages of a page."""
    client = _get_client()
    children = await client.get_child_pages(page_id, limit=limit)
    return {"children": children}


@router.post("/extract")
async def extract_pages(
    req: ExtractRequest,
    org_id: int = Query(...),
    current_user: dict = Depends(require_permission("confluence", "extract")),
):
    """Extract pages from a space and store as a ConfluenceExtraction run.

    If page_ids is empty, fetches all root-level pages of the space.
    Returns the extraction run with extracted content.
    """
    client = _get_client()

    # Determine which pages to extract
    if req.page_ids:
        page_ids = req.page_ids
    else:
        space_pages = await client.get_space_pages(req.space_key, limit=req.max_pages)
        page_ids = [p["id"] for p in space_pages]

    # Fetch each page
    extracted_content = []
    for pid in page_ids[:req.max_pages]:
        try:
            page = await client.get_page(pid)
            extracted_content.append(
                {
                    "page_id": page["id"],
                    "title": page["title"],
                    "content_md": page["content"],
                    "url": page["url"],
                    "space_key": page["space_key"],
                }
            )
        except Exception as e:
            extracted_content.append(
                {"page_id": pid, "title": "Error", "content_md": f"Failed: {e}", "url": ""}
            )

    # Get space name from first page or fallback
    space_name = ""
    if extracted_content and extracted_content[0].get("space_key"):
        spaces = await client.list_spaces(limit=200)
        for s in spaces:
            if s["key"] == req.space_key:
                space_name = s["name"]
                break

    # Save to database
    run_id = uuid.uuid4()
    async with async_session() as db:
        run = ConfluenceExtraction(
            id=run_id,
            user_id=current_user["user_id"],
            org_id=org_id,
            space_key=req.space_key,
            space_name=space_name,
            page_ids=[p["page_id"] for p in extracted_content],
            extracted_content=extracted_content,
            status="complete",
            completed_at=datetime.now(timezone.utc),
        )
        db.add(run)
        await db.commit()

    return {
        "run_id": str(run_id),
        "space_key": req.space_key,
        "space_name": space_name,
        "pages_extracted": len(extracted_content),
        "content": extracted_content,
    }


@router.get("/extractions")
async def list_extractions(
    org_id: int = Query(...),
    current_user: dict = Depends(require_permission("confluence", "view")),
):
    """List past Confluence extraction runs."""
    from sqlalchemy import select

    async with async_session() as db:
        stmt = (
            select(ConfluenceExtraction)
            .where(ConfluenceExtraction.org_id == org_id)
            .order_by(ConfluenceExtraction.created_at.desc())
            .limit(20)
        )
        result = await db.execute(stmt)
        runs = result.scalars().all()

    return {
        "extractions": [
            {
                "id": str(r.id),
                "space_key": r.space_key,
                "space_name": r.space_name,
                "page_count": len(r.page_ids) if r.page_ids else 0,
                "status": r.status,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in runs
        ]
    }
