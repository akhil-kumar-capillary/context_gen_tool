"""Configuration APIs source module endpoints.
Full implementation in Phase 4.
"""
from fastapi import APIRouter, Depends
from app.core.auth import get_current_user
from app.core.rbac import require_permission

router = APIRouter()

AVAILABLE_API_TYPES = [
    {"id": "campaigns", "label": "Campaigns", "description": "Campaign configurations and rules"},
    {"id": "promotions", "label": "Promotions", "description": "Promotion rules and templates"},
    {"id": "audience", "label": "Audience", "description": "Audience group definitions"},
    {"id": "voucher_series", "label": "Voucher Series", "description": "Voucher series configurations"},
]


@router.get("/available")
async def list_available_apis(
    current_user: dict = Depends(require_permission("config_apis", "view")),
):
    return {"api_types": AVAILABLE_API_TYPES}


@router.post("/fetch/{api_type}")
async def fetch_config(
    api_type: str,
    current_user: dict = Depends(require_permission("config_apis", "fetch")),
):
    return {"status": "not_implemented", "message": "Phase 4"}
