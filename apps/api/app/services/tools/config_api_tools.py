"""Config API LLM tools — real implementations that fetch Capillary config data.

These tools are callable by the LLM during chat sessions. They use the user's
Capillary auth token (from ToolContext) to call Intouch API endpoints.
"""
from __future__ import annotations

import httpx

from app.services.tools.registry import registry
from app.services.tools.tool_context import ToolContext


# Mirror the available types from the router
_API_TYPES = {
    "campaigns": {"label": "Campaigns", "path": "/v2/campaigns"},
    "promotions": {"label": "Promotions", "path": "/v2/promotions"},
    "audience": {"label": "Audience Groups", "path": "/v2/audience/groups"},
    "voucher_series": {"label": "Voucher Series", "path": "/v1.1/coupon/series"},
    "loyalty_programs": {"label": "Loyalty Programs", "path": "/v2/loyalty/programs"},
    "points": {"label": "Points Configuration", "path": "/v2/points"},
}


@registry.tool(
    name="config_api_list_available",
    description=(
        "List available Capillary Configuration API types that can be fetched. "
        "Call this when the user wants to see what configuration data sources exist."
    ),
    module="config_apis",
    requires_permission=("config_apis", "view"),
    annotations={"display": "Listing available config APIs..."},
)
async def config_api_list_available(ctx: ToolContext) -> str:
    lines = ["Available Capillary Configuration APIs:\n"]
    for key, info in _API_TYPES.items():
        lines.append(f"- **{info['label']}** (`{key}`)")
    lines.append(
        "\nUse the `config_api_fetch` tool with an `api_type` to fetch data."
    )
    return "\n".join(lines)


@registry.tool(
    name="config_api_fetch",
    description=(
        "Fetch configuration data from a Capillary API endpoint. Call this when "
        "the user wants to pull configuration data (campaigns, promotions, "
        "audience groups, voucher series, loyalty programs, or points config)."
    ),
    module="config_apis",
    requires_permission=("config_apis", "fetch"),
    annotations={"display": "Fetching configuration data..."},
)
async def config_api_fetch(
    ctx: ToolContext, api_type: str = "", limit: int = 50
) -> str:
    """Fetch from a Capillary Configuration API.

    api_type: The type of API to fetch (campaigns, promotions, audience, voucher_series, loyalty_programs, points)
    limit: Maximum number of records to fetch (default 50)
    """
    if not api_type or api_type not in _API_TYPES:
        avail = ", ".join(f"`{k}`" for k in _API_TYPES)
        return f"Unknown api_type: '{api_type}'. Available types: {avail}"

    api_def = _API_TYPES[api_type]
    base_url = ctx.base_url
    if not base_url:
        return "No Capillary base URL available for this user session."

    url = f"{base_url}{api_def['path']}"
    headers = {
        "Authorization": f"Bearer {ctx.capillary_token}",
        "x-cap-api-auth-org-id": str(ctx.org_id),
        "Accept": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, headers=headers, params={"limit": limit})

        if resp.status_code != 200:
            return f"Capillary API returned {resp.status_code}: {resp.text[:300]}"

        data = resp.json()
    except httpx.HTTPError as e:
        return f"Failed to reach Capillary API: {e}"
    except Exception as e:
        return f"Error: {e}"

    # Extract records
    records = data if isinstance(data, list) else None
    for key in ("data", "entity", "entities", "records", "results", "items"):
        if isinstance(data, dict) and key in data and isinstance(data[key], list):
            records = data[key]
            break

    count = len(records) if isinstance(records, list) else 1

    lines = [f"Fetched {count} {api_def['label'].lower()} record(s):\n"]

    if records and isinstance(records, list):
        for r in records[:15]:
            if isinstance(r, dict):
                name = (
                    r.get("name")
                    or r.get("title")
                    or r.get("seriesName")
                    or r.get("programName")
                    or str(r.get("id", "?"))
                )
                status = r.get("status") or r.get("state") or ""
                extra = f" (status: {status})" if status else ""
                lines.append(f"- **{name}**{extra}")
        if count > 15:
            lines.append(f"\n... and {count - 15} more records.")
    else:
        lines.append("(Could not parse records list from response)")

    # Persist to DB
    try:
        import uuid
        from datetime import datetime, timezone
        from app.models.source_run import ConfigApiExtraction

        run_id = uuid.uuid4()
        async with ctx.get_db() as db:
            extraction = ConfigApiExtraction(
                id=run_id,
                user_id=ctx.user_id,
                org_id=ctx.org_id,
                api_type=api_type,
                extracted_data=data,
                processed_summary="\n".join(lines),
                status="complete",
                completed_at=datetime.now(timezone.utc),
            )
            db.add(extraction)
            await db.commit()
        lines.append(f"\nExtraction saved (run ID: {run_id})")
    except Exception:
        pass  # Non-critical — data still returned even if DB save fails

    return "\n".join(lines)
