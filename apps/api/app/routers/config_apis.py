"""Configuration APIs source — fetch Capillary config data (campaigns, promotions, etc.)

Uses the authenticated user's Capillary token to fetch org-level configuration
from various Intouch API endpoints.
"""
from __future__ import annotations

import uuid
import json
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.core.auth import get_current_user
from app.core.rbac import require_permission
from app.database import async_session
from app.models.source_run import ConfigApiExtraction

router = APIRouter()

# ── available API types ──────────────────────────────────────────────

AVAILABLE_API_TYPES = {
    "campaigns": {
        "id": "campaigns",
        "label": "Campaigns",
        "description": "Campaign configurations and rules",
        "path": "/v2/campaigns",
        "method": "GET",
    },
    "promotions": {
        "id": "promotions",
        "label": "Promotions",
        "description": "Promotion rules and templates",
        "path": "/v2/promotions",
        "method": "GET",
    },
    "audience": {
        "id": "audience",
        "label": "Audience Groups",
        "description": "Audience/filter group definitions",
        "path": "/v2/audience/groups",
        "method": "GET",
    },
    "voucher_series": {
        "id": "voucher_series",
        "label": "Voucher Series",
        "description": "Voucher series configurations",
        "path": "/v1.1/coupon/series",
        "method": "GET",
    },
    "loyalty_programs": {
        "id": "loyalty_programs",
        "label": "Loyalty Programs",
        "description": "Loyalty program and tier configurations",
        "path": "/v2/loyalty/programs",
        "method": "GET",
    },
    "points": {
        "id": "points",
        "label": "Points Configuration",
        "description": "Points and rewards configuration",
        "path": "/v2/points",
        "method": "GET",
    },
}


def _capillary_headers(user: dict, org_id: int) -> dict:
    return {
        "Authorization": f"Bearer {user['capillary_token']}",
        "x-cap-api-auth-org-id": str(org_id),
        "Accept": "application/json",
    }


# ── schemas ──────────────────────────────────────────────────────────

class FetchRequest(BaseModel):
    limit: int = 100


# ── endpoints ────────────────────────────────────────────────────────

@router.get("/available")
async def list_available_apis(
    current_user: dict = Depends(require_permission("config_apis", "view")),
):
    """List all available Config API types."""
    return {
        "api_types": [
            {"id": v["id"], "label": v["label"], "description": v["description"]}
            for v in AVAILABLE_API_TYPES.values()
        ]
    }


@router.post("/fetch/{api_type}")
async def fetch_config(
    api_type: str,
    org_id: int = Query(...),
    req: FetchRequest = FetchRequest(),
    current_user: dict = Depends(require_permission("config_apis", "fetch")),
):
    """Fetch configuration data from a Capillary API endpoint.

    Fetches the data, stores the extraction, and returns the result.
    """
    api_def = AVAILABLE_API_TYPES.get(api_type)
    if not api_def:
        raise HTTPException(
            400,
            f"Unknown API type: '{api_type}'. Available: {list(AVAILABLE_API_TYPES.keys())}",
        )

    base_url = current_user.get("base_url", "")
    if not base_url:
        raise HTTPException(400, "No base URL configured for this user's cluster.")

    url = f"{base_url}{api_def['path']}"
    headers = _capillary_headers(current_user, org_id)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.request(
                method=api_def["method"],
                url=url,
                headers=headers,
                params={"limit": req.limit} if api_def["method"] == "GET" else None,
            )

        if resp.status_code != 200:
            raise HTTPException(
                resp.status_code,
                f"Capillary API returned {resp.status_code}: {resp.text[:500]}",
            )

        data = resp.json()
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Failed to reach Capillary API: {e}")

    # Build a human-readable summary
    summary = _build_summary(api_type, data)

    # Persist extraction
    run_id = uuid.uuid4()
    async with async_session() as db:
        extraction = ConfigApiExtraction(
            id=run_id,
            user_id=current_user["user_id"],
            org_id=org_id,
            api_type=api_type,
            extracted_data=data,
            processed_summary=summary,
            status="complete",
            completed_at=datetime.now(timezone.utc),
        )
        db.add(extraction)
        await db.commit()

    return {
        "run_id": str(run_id),
        "api_type": api_type,
        "label": api_def["label"],
        "record_count": _count_records(data),
        "summary": summary,
        "data": data,
    }


@router.get("/extractions")
async def list_extractions(
    org_id: int = Query(...),
    current_user: dict = Depends(require_permission("config_apis", "view")),
):
    """List past Config API extraction runs."""
    from sqlalchemy import select

    async with async_session() as db:
        stmt = (
            select(ConfigApiExtraction)
            .where(ConfigApiExtraction.org_id == org_id)
            .order_by(ConfigApiExtraction.created_at.desc())
            .limit(20)
        )
        result = await db.execute(stmt)
        runs = result.scalars().all()

    return {
        "extractions": [
            {
                "id": str(r.id),
                "api_type": r.api_type,
                "label": AVAILABLE_API_TYPES.get(r.api_type, {}).get("label", r.api_type),
                "status": r.status,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in runs
        ]
    }


# ── helpers ──────────────────────────────────────────────────────────

def _count_records(data: dict) -> int:
    """Try to count records in a Capillary API response."""
    if isinstance(data, list):
        return len(data)
    for key in ("data", "entity", "entities", "records", "results", "items"):
        val = data.get(key)
        if isinstance(val, list):
            return len(val)
    return 1


def _build_summary(api_type: str, data: dict) -> str:
    """Build a human-readable summary of the fetched config data."""
    count = _count_records(data)
    label = AVAILABLE_API_TYPES.get(api_type, {}).get("label", api_type)

    lines = [f"Fetched {count} {label.lower()} configuration(s)."]

    # Extract names/titles if available
    records = data if isinstance(data, list) else None
    for key in ("data", "entity", "entities", "records", "results", "items"):
        if key in data and isinstance(data[key], list):
            records = data[key]
            break

    if records and isinstance(records, list):
        names = []
        for r in records[:20]:
            if isinstance(r, dict):
                name = r.get("name") or r.get("title") or r.get("seriesName") or r.get("id")
                if name:
                    names.append(str(name))
        if names:
            lines.append(f"\nItems: {', '.join(names[:15])}")
            if len(names) > 15:
                lines.append(f"  ... and {len(names) - 15} more")

    return "\n".join(lines)
