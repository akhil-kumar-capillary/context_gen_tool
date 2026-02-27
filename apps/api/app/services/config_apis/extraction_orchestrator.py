"""
Config APIs extraction orchestrator.

User selects which API categories to fetch, provides per-category params.
Each category is a phase with WebSocket progress.
Failed individual APIs are skipped with warnings (never crash the whole extraction).

Every API call is individually tracked with status, timing, item count,
and error details — stored in ``api_call_log`` for full visibility.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any, Callable, Awaitable, Dict, List, Optional, Tuple, TypedDict

from app.services.config_apis.client import CapillaryAPIClient, APIError
from app.services.config_apis.storage import ConfigStorageService

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, int, int, str], Awaitable[None]]


# ---------------------------------------------------------------------------
# Per-API-call result tracking
# ---------------------------------------------------------------------------

class APICallResult(TypedDict, total=False):
    """Structured metadata for one API call — stored in api_call_log."""
    api_name: str        # e.g. "programs", "sms_templates"
    status: str          # "success" | "error"
    http_status: int     # HTTP status code (if available)
    item_count: int      # number of items extracted
    error_message: str   # error details if failed
    duration_ms: int     # milliseconds
    response_bytes: int  # approx size of JSON response


def _count_response_items(data: Any) -> int:
    """Count items in a Capillary API response (various shapes)."""
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        if "_error" in data:
            return 0
        for key in ("data", "entity", "entities", "programs", "tiers",
                     "strategies", "promotions", "campaigns", "audiences",
                     "results", "items", "records", "config"):
            val = data.get(key)
            if isinstance(val, list):
                return len(val)
            if isinstance(val, dict) and "data" in val and isinstance(val["data"], list):
                return len(val["data"])
    return 0


def _extract_items_local(data: Any) -> list:
    """Extract list of items from a Capillary API response."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if "_error" in data:
            return []
        for key in ("data", "entity", "entities", "programs", "tiers",
                     "strategies", "promotions", "campaigns", "audiences",
                     "results", "items", "records", "config"):
            val = data.get(key)
            if isinstance(val, list):
                return val
            if isinstance(val, dict) and "data" in val and isinstance(val["data"], list):
                return val["data"]
    return []


async def _tracked_call(fn, name: str) -> Tuple[Any, APICallResult]:
    """Call fn() and return (data, call_result) with full tracking."""
    t0 = time.monotonic()
    result: APICallResult = {"api_name": name, "status": "success"}

    try:
        data = await fn()
        elapsed = int((time.monotonic() - t0) * 1000)
        result["duration_ms"] = elapsed

        # Check if it's an error response
        if isinstance(data, dict) and "_error" in data:
            result["status"] = "error"
            result["error_message"] = data.get("_error", "Unknown error")
            result["http_status"] = data.get("_status_code", 0)
            result["item_count"] = 0
        else:
            result["item_count"] = _count_response_items(data)
            try:
                result["response_bytes"] = len(json.dumps(data, default=str))
            except Exception:
                result["response_bytes"] = 0

        return data, result

    except APIError as e:
        elapsed = int((time.monotonic() - t0) * 1000)
        logger.warning(f"API call {name} failed: {e.message}")
        result["status"] = "error"
        result["duration_ms"] = elapsed
        result["http_status"] = e.status_code
        result["error_message"] = e.message
        result["item_count"] = 0
        return {"_error": e.message, "_status_code": e.status_code}, result

    except Exception as e:
        elapsed = int((time.monotonic() - t0) * 1000)
        logger.warning(f"API call {name} failed: {e}")
        result["status"] = "error"
        result["duration_ms"] = elapsed
        result["error_message"] = str(e)
        result["item_count"] = 0
        return {"_error": str(e)}, result


# ---------------------------------------------------------------------------
# Category registry — each category defines the API calls to make
# ---------------------------------------------------------------------------

CATEGORIES: Dict[str, Dict[str, Any]] = {
    "loyalty": {
        "label": "Loyalty Programs",
        "description": "Programs, tiers, strategies, currencies, partners, event types",
        "params_schema": [
            {"key": "program_id", "label": "Program ID", "type": "number", "required": False,
             "help": "Specific program ID (leave empty to auto-detect)"},
        ],
    },
    "extended_fields": {
        "label": "Extended Fields",
        "description": "Customer, transaction, line-item extended fields",
        "params_schema": [
            {"key": "program_id", "label": "Program ID", "type": "number", "required": False,
             "help": "Leave empty to auto-detect from first loyalty program"},
        ],
    },
    "campaigns": {
        "label": "Campaigns",
        "description": "List campaigns, campaign details, messages, templates",
        "params_schema": [
            {"key": "limit", "label": "Max campaigns", "type": "number", "required": False,
             "default": 50, "help": "Maximum number of campaigns to fetch"},
            {"key": "search", "label": "Search filter", "type": "text", "required": False,
             "help": "Filter campaigns by name"},
        ],
    },
    "promotions": {
        "label": "Promotions",
        "description": "Loyalty promotions, cart promotions",
        "params_schema": [
            {"key": "limit", "label": "Max promotions", "type": "number", "required": False,
             "default": 50, "help": "Maximum number of promotions to fetch"},
            {"key": "active_only", "label": "Active only", "type": "boolean", "required": False,
             "default": False, "help": "Only fetch active promotions"},
        ],
    },
    "coupons": {
        "label": "Coupons & Rewards",
        "description": "Coupon series, product brands/categories/attributes, reward custom fields",
        "params_schema": [
            {"key": "owned_by", "label": "Owned by", "type": "select", "required": False,
             "options": ["NONE", "LOYALTY"], "default": "NONE",
             "help": "Filter by ownership"},
        ],
    },
    "audiences": {
        "label": "Audiences & Segments",
        "description": "Audiences, target groups, segments, filters",
        "params_schema": [
            {"key": "search", "label": "Search", "type": "text", "required": False,
             "help": "Filter audiences by name"},
        ],
    },
    "org_settings": {
        "label": "Org Settings",
        "description": "Behavioral events, customer labels, org hierarchy, target groups",
        "params_schema": [
            {"key": "channels", "label": "Channels", "type": "multi_select", "required": False,
             "options": ["SMS", "EMAIL", "WHATSAPP", "MOBILEPUSH"],
             "default": ["SMS", "EMAIL"], "help": "Channels to fetch domain properties for"},
        ],
    },
}


def get_available_categories() -> List[Dict[str, Any]]:
    """Return category metadata for the frontend category picker."""
    result = []
    for cat_id, cat in CATEGORIES.items():
        result.append({
            "id": cat_id,
            "label": cat["label"],
            "description": cat["description"],
            "params_schema": cat["params_schema"],
        })
    return result


# ---------------------------------------------------------------------------
# Helper: run a list of (name, coroutine_factory) calls with tracking
# ---------------------------------------------------------------------------

async def _run_apis(
    apis: list,
    phase: str,
    emit: ProgressCallback,
) -> Tuple[Dict[str, Any], List[APICallResult]]:
    """Run a list of (name, async_fn) API calls sequentially with full tracking."""
    data: Dict[str, Any] = {}
    call_results: List[APICallResult] = []
    total = len(apis)

    for i, (name, fn) in enumerate(apis):
        await emit(phase, i, total, f"Fetching {name}...")
        result_data, call_result = await _tracked_call(fn, name)
        data[name] = result_data
        call_results.append(call_result)

        # Emit per-call result
        if call_result["status"] == "success":
            count = call_result.get("item_count", 0)
            ms = call_result.get("duration_ms", 0)
            await emit(phase, i + 1, total, f"  \u2713 {name}: {count} items ({ms}ms)")
        else:
            err = call_result.get("error_message", "unknown error")[:100]
            http = call_result.get("http_status", "")
            ms = call_result.get("duration_ms", 0)
            status_str = f" HTTP {http}" if http else ""
            await emit(phase, i + 1, total, f"  \u2717 {name}:{status_str} {err} ({ms}ms)")

    await emit(phase, total, total, f"{phase}: {total} API calls completed")
    return data, call_results


# ---------------------------------------------------------------------------
# Helper: resolve program_id from programs list
# ---------------------------------------------------------------------------

async def _resolve_program_id(
    client: CapillaryAPIClient,
    emit: ProgressCallback,
    phase: str,
) -> Tuple[Optional[int], Any, APICallResult]:
    """Fetch programs list and return (program_id, raw_data, call_result).

    Returns the first program's ID, or None if no programs found.
    """
    programs_data, call_result = await _tracked_call(
        lambda: client.loyalty.get_loyalty_programs(),
        "programs",
    )

    programs = _extract_items_local(programs_data)
    if programs:
        # Try common ID field names
        pid = None
        for p in programs:
            if isinstance(p, dict):
                pid = p.get("programId") or p.get("id") or p.get("program_id")
                if pid:
                    break
        if pid:
            await emit(phase, 0, 1,
                       f"Auto-resolved program_id={pid} from {len(programs)} programs")
            return int(pid), programs_data, call_result

    await emit(phase, 0, 1, f"No programs found — cannot resolve program_id")
    return None, programs_data, call_result


# ---------------------------------------------------------------------------
# Per-category extraction functions
# ---------------------------------------------------------------------------

async def _extract_loyalty(
    client: CapillaryAPIClient,
    params: Dict[str, Any],
    emit: ProgressCallback,
) -> Tuple[Dict[str, Any], List[APICallResult]]:
    """Fetch loyalty program configurations with auto-resolution."""
    data: Dict[str, Any] = {}
    all_calls: List[APICallResult] = []
    program_id = params.get("program_id")

    # Phase 1: Base APIs (always fetched)
    base_apis = [
        ("programs", lambda: client.loyalty.get_loyalty_programs()),
        ("custom_fields", lambda: client.loyalty.get_custom_fields()),
        ("liability_owners", lambda: client.loyalty.get_liability_owners()),
        ("org_labels", lambda: client.loyalty.get_org_labels()),
    ]
    base_data, base_calls = await _run_apis(base_apis, "loyalty", emit)
    data.update(base_data)
    all_calls.extend(base_calls)

    # Phase 2: Auto-resolve program_id if not provided
    if not program_id:
        programs = _extract_items_local(base_data.get("programs"))
        if programs:
            for p in programs:
                if isinstance(p, dict):
                    pid = p.get("programId") or p.get("id") or p.get("program_id")
                    if pid:
                        program_id = int(pid)
                        await emit("loyalty", len(base_apis), len(base_apis),
                                   f"Auto-resolved program_id={program_id} from {len(programs)} programs")
                        break

    # Phase 3: Program-specific APIs
    if program_id:
        pid = int(program_id)
        program_apis = [
            ("program_detail", lambda: client.loyalty.get_loyalty_program_by_id(pid)),
            ("tiers", lambda: client.loyalty.get_all_tiers_by_lp_id(pid)),
            ("strategies", lambda: client.loyalty.get_strategies(pid)),
            ("partner_programs", lambda: client.loyalty.get_all_partner_programs_by_lp_id(pid)),
            ("alternate_currencies", lambda: client.loyalty.get_alternate_currencies(pid)),
            ("event_types", lambda: client.loyalty.get_event_types(pid)),
            ("subscription_partner", lambda: client.loyalty.get_subscription_partner_programs(pid)),
        ]
        prog_data, prog_calls = await _run_apis(program_apis, "loyalty_programs", emit)
        data.update(prog_data)
        all_calls.extend(prog_calls)
    else:
        await emit("loyalty", len(base_apis), len(base_apis),
                    "No programs found — skipping program-specific APIs")

    return data, all_calls


async def _extract_extended_fields(
    client: CapillaryAPIClient,
    params: Dict[str, Any],
    emit: ProgressCallback,
) -> Tuple[Dict[str, Any], List[APICallResult]]:
    """Fetch extended field configurations with auto-resolution."""
    all_calls: List[APICallResult] = []
    program_id = params.get("program_id")

    # Auto-resolve if not provided
    if not program_id:
        pid, programs_data, programs_call = await _resolve_program_id(
            client, emit, "extended_fields"
        )
        all_calls.append(programs_call)
        program_id = pid

    if not program_id:
        await emit("extended_fields", 0, 0,
                    "Skipped — no program_id available (no loyalty programs found)")
        return {"_skipped": "no program_id available"}, all_calls

    pid = int(program_id)
    apis = [
        ("customer_extended_fields", lambda: client.loyalty.get_customer_extended_fields(pid)),
        ("txn_extended_fields", lambda: client.loyalty.get_txn_extended_fields(pid)),
        ("line_item_extended_fields", lambda: client.loyalty.get_line_item_extended_fields(pid)),
    ]
    ef_data, ef_calls = await _run_apis(apis, "extended_fields", emit)
    all_calls.extend(ef_calls)
    return ef_data, all_calls


async def _extract_campaigns(
    client: CapillaryAPIClient,
    params: Dict[str, Any],
    emit: ProgressCallback,
) -> Tuple[Dict[str, Any], List[APICallResult]]:
    """Fetch campaign configurations."""
    limit = int(params.get("limit", 50))
    search = params.get("search", "")

    data: Dict[str, Any] = {}
    all_calls: List[APICallResult] = []

    # Phase 1: List campaigns
    await emit("campaigns", 0, 3, "Listing campaigns...")
    campaigns_list, list_call = await _tracked_call(
        lambda: client.campaigns.list_campaigns(campaign_name=search, limit=limit),
        "campaigns_list",
    )
    data["campaigns_list"] = campaigns_list
    all_calls.append(list_call)

    if list_call["status"] == "success":
        count = list_call.get("item_count", 0)
        await emit("campaigns", 0, 3, f"  \u2713 campaigns_list: {count} items ({list_call.get('duration_ms', 0)}ms)")
    else:
        await emit("campaigns", 0, 3, f"  \u2717 campaigns_list: {list_call.get('error_message', '')[:80]}")

    # Phase 2: Fetch details + messages for top campaigns
    campaigns = []
    if isinstance(campaigns_list, dict):
        campaigns = campaigns_list.get("data", campaigns_list.get("campaigns", []))
        if isinstance(campaigns, dict):
            campaigns = campaigns.get("data", [])
    if not isinstance(campaigns, list):
        campaigns = []

    await emit("campaigns", 1, 3, f"Fetching details for {len(campaigns[:limit])} campaigns...")
    details = []
    for i, camp in enumerate(campaigns[:limit]):
        camp_id = camp.get("id")
        if not camp_id:
            continue
        detail, detail_call = await _tracked_call(
            lambda cid=camp_id: client.campaigns.get_campaign_by_id(cid),
            f"campaign_{camp_id}",
        )
        all_calls.append(detail_call)

        messages, msg_call = await _tracked_call(
            lambda cid=camp_id: client.campaigns.list_campaign_messages(cid, limit=20),
            f"campaign_{camp_id}_messages",
        )
        all_calls.append(msg_call)

        details.append({
            "campaign_id": camp_id,
            "detail": detail,
            "messages": messages,
        })
    data["campaign_details"] = details

    # Phase 3: Templates and settings
    await emit("campaigns", 2, 3, "Fetching templates and settings...")
    templates_apis = [
        ("sms_templates", lambda: client.campaigns.get_sms_templates()),
        ("email_templates", lambda: client.campaigns.get_email_templates()),
        ("default_attribution", lambda: client.campaigns.get_default_attribution()),
        ("program_configurations", lambda: client.campaigns.get_program_configurations()),
        ("whatsapp_accounts", lambda: client.campaigns.get_whatsapp_accounts()),
        ("push_notification_accounts", lambda: client.campaigns.get_push_notification_accounts()),
    ]
    template_data, template_calls = await _run_apis(templates_apis, "campaigns_templates", emit)
    data.update(template_data)
    all_calls.extend(template_calls)

    await emit("campaigns", 3, 3, f"Done — {len(details)} campaigns fetched")
    return data, all_calls


async def _extract_promotions(
    client: CapillaryAPIClient,
    params: Dict[str, Any],
    emit: ProgressCallback,
) -> Tuple[Dict[str, Any], List[APICallResult]]:
    """Fetch promotion configurations."""
    limit = int(params.get("limit", 50))
    active_only = params.get("active_only", False)

    apis = [
        ("loyalty_promotions", lambda: client.loyalty.list_promotions(limit=limit, offset=0)),
        ("cart_promotions", lambda: client.promotion.get_cart_promo_or_gift_voucher_by_name(
            active=active_only if active_only else None
        )),
        ("cart_promotion_custom_fields", lambda: client.cart_promotion.get_custom_fields_for_cart_promotion()),
        ("rewards_custom_fields", lambda: client.promotion.get_custom_fields_list()),
        ("rewards_groups", lambda: client.promotion.get_groups_list()),
        ("rewards_languages", lambda: client.promotion.get_languages_list()),
        ("segments", lambda: client.promotion.get_segments_list()),
    ]
    return await _run_apis(apis, "promotions", emit)


async def _extract_coupons(
    client: CapillaryAPIClient,
    params: Dict[str, Any],
    emit: ProgressCallback,
) -> Tuple[Dict[str, Any], List[APICallResult]]:
    """Fetch coupon and reward configurations."""
    owned_by = params.get("owned_by", "NONE")
    owned_by_val = owned_by if owned_by == "LOYALTY" else None

    apis = [
        ("coupon_series", lambda: client.coupon.list_coupon_series(owned_by=owned_by_val)),
        ("coupon_custom_property", lambda: client.coupon.get_custom_property()),
        ("coupon_org_settings", lambda: client.coupon.get_org_settings()),
        ("product_categories", lambda: client.coupon.get_product_categories()),
        ("product_brands", lambda: client.coupon.get_product_brands()),
        ("product_attributes", lambda: client.coupon.get_product_attributes()),
        ("reward_custom_fields", lambda: client.reward.get_custom_fields()),
    ]
    return await _run_apis(apis, "coupons", emit)


async def _extract_audiences(
    client: CapillaryAPIClient,
    params: Dict[str, Any],
    emit: ProgressCallback,
) -> Tuple[Dict[str, Any], List[APICallResult]]:
    """Fetch audience and segment configurations."""
    search = params.get("search", "")

    apis = [
        ("audiences", lambda: client.campaigns.get_audiences(search=search)),
        ("target_groups", lambda: client.org_settings.get_all_target_groups()),
        ("audience_filters", lambda: client.audience.get_audience_filters()),
        ("dim_attr_availability", lambda: client.audience.get_dim_attr_value_availability()),
        ("customer_test_control", lambda: client.audience.get_customer_test_control()),
        ("behavioral_events", lambda: client.org_settings.get_behavioral_events()),
    ]
    return await _run_apis(apis, "audiences", emit)


async def _extract_org_settings(
    client: CapillaryAPIClient,
    params: Dict[str, Any],
    emit: ProgressCallback,
) -> Tuple[Dict[str, Any], List[APICallResult]]:
    """Fetch organization settings."""
    channels = params.get("channels", ["SMS", "EMAIL"])
    if isinstance(channels, str):
        channels = [c.strip() for c in channels.split(",")]

    apis = [
        ("behavioral_events", lambda: client.org_settings.get_behavioral_events()),
        ("customer_labels", lambda: client.org_settings.get_customer_labels()),
        ("organization_hierarchy", lambda: client.intouch.get_organization_hierarchy()),
        ("target_groups", lambda: client.org_settings.get_all_target_groups()),
    ]

    for ch in channels:
        apis.append((
            f"domain_properties_{ch.lower()}",
            lambda channel=ch: client.campaigns.get_domain_properties(channel),
        ))

    return await _run_apis(apis, "org_settings", emit)


# Category → extraction function map
_CATEGORY_EXTRACTORS = {
    "loyalty": _extract_loyalty,
    "extended_fields": _extract_extended_fields,
    "campaigns": _extract_campaigns,
    "promotions": _extract_promotions,
    "coupons": _extract_coupons,
    "audiences": _extract_audiences,
    "org_settings": _extract_org_settings,
}


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

async def run_extraction(
    *,
    run_id: Optional[str] = None,
    host: str,
    token: str,
    org_id: int,
    user_id: int,
    categories: List[str],
    category_params: Optional[Dict[str, Dict[str, Any]]] = None,
    on_progress: Optional[ProgressCallback] = None,
) -> Dict[str, Any]:
    """
    Run the full config API extraction pipeline.

    Args:
        run_id: Pre-generated UUID (auto-generated if missing).
        host: Capillary platform host (e.g., "eu.intouch.capillarytech.com").
        token: Bearer auth token.
        org_id: Organization ID.
        user_id: User running the extraction.
        categories: List of category IDs to extract.
        category_params: Per-category params dict.
        on_progress: async callback(phase, completed, total, detail).

    Returns:
        dict with run_id, stats, api_call_log
    """
    run_id = run_id or str(uuid.uuid4())
    category_params = category_params or {}
    storage = ConfigStorageService()

    async def emit(phase: str, completed: int, total: int, detail: str):
        if on_progress:
            await on_progress(phase, completed, total, detail)

    # Create DB record
    await storage.create_extraction_run(
        run_id=run_id,
        user_id=user_id,
        org_id=org_id,
        host=host,
        categories=categories,
        category_params=category_params,
    )

    await emit("init", 0, len(categories), f"Starting extraction for {len(categories)} categories")

    extracted_data: Dict[str, Any] = {}
    stats: Dict[str, Any] = {}
    api_call_log: Dict[str, List[dict]] = {}

    async with CapillaryAPIClient(host=host, token=token, org_id=org_id) as client:
        for cat_idx, cat_id in enumerate(categories):
            if cat_id not in _CATEGORY_EXTRACTORS:
                logger.warning(f"Unknown category: {cat_id}, skipping")
                continue

            params = category_params.get(cat_id, {})
            extractor = _CATEGORY_EXTRACTORS[cat_id]
            label = CATEGORIES.get(cat_id, {}).get("label", cat_id)

            await emit("category", cat_idx, len(categories), f"Extracting: {label}")
            t0 = time.monotonic()

            try:
                result, call_results = await extractor(client, params, emit)
                duration = round(time.monotonic() - t0, 2)

                # Count successes vs errors from call results
                success_count = sum(1 for c in call_results if c.get("status") == "success")
                error_count = sum(1 for c in call_results if c.get("status") == "error")

                extracted_data[cat_id] = result
                api_call_log[cat_id] = [dict(c) for c in call_results]  # serialize TypedDicts
                stats[cat_id] = {
                    "apis": len(call_results),
                    "success": success_count,
                    "failed": error_count,
                    "duration_s": duration,
                }

                await emit(
                    "category_done", cat_idx + 1, len(categories),
                    f"{label}: {success_count} OK, {error_count} failed ({duration}s)"
                )
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.exception(f"Category {cat_id} extraction failed entirely")
                extracted_data[cat_id] = {"_error": str(e)}
                api_call_log[cat_id] = [{
                    "api_name": f"{cat_id}_entire_category",
                    "status": "error",
                    "error_message": str(e),
                    "duration_ms": int((time.monotonic() - t0) * 1000),
                    "item_count": 0,
                }]
                stats[cat_id] = {"apis": 0, "success": 0, "failed": 1, "duration_s": 0}
                await emit("category_error", cat_idx + 1, len(categories), f"{label}: FAILED — {e}")

    # Save to DB
    await storage.complete_extraction_run(
        run_id=run_id,
        extracted_data=extracted_data,
        stats=stats,
        api_call_log=api_call_log,
    )

    total_apis = sum(s.get("apis", 0) for s in stats.values())
    total_success = sum(s.get("success", 0) for s in stats.values())
    total_failed = sum(s.get("failed", 0) for s in stats.values())

    await emit(
        "complete", len(categories), len(categories),
        f"Extraction complete: {total_apis} APIs ({total_success} OK, {total_failed} failed)"
    )

    return {
        "run_id": run_id,
        "categories_extracted": len(categories),
        "total_apis": total_apis,
        "total_success": total_success,
        "total_failed": total_failed,
        "stats": stats,
        "api_call_log": api_call_log,
    }
