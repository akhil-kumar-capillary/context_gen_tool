"""Config API LLM tools — comprehensive wrappers around CapillaryAPIClient.

These tools are callable by the LLM during chat sessions. They use the user's
Capillary auth token (from ToolContext) to call Intouch API endpoints via the
full CapillaryAPIClient (13 services, 89 methods).
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import urlparse

from app.services.config_apis.client import CapillaryAPIClient, APIError
from app.services.tools.registry import registry
from app.services.tools.tool_context import ToolContext

logger = logging.getLogger(__name__)

_MAX_ITEMS = 25  # max items to show in a list before truncation


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_client(ctx: ToolContext) -> CapillaryAPIClient:
    """Create a CapillaryAPIClient from ToolContext."""
    base_url = ctx.base_url
    if not base_url:
        raise ValueError("No Capillary base URL available for this user session.")
    parsed = urlparse(base_url)
    host = parsed.netloc or base_url.replace("https://", "").replace("http://", "").rstrip("/")
    return CapillaryAPIClient(host=host, token=ctx.capillary_token, org_id=ctx.org_id)


def _extract_list(data: Any, keys: Sequence[str] = (
    "data", "entity", "entities", "programs", "tiers", "strategies",
    "promotions", "campaigns", "audiences", "results", "items", "records",
    "config", "rewards", "brands",
)) -> list:
    """Pull a list from various Capillary response shapes."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in keys:
            val = data.get(key)
            if isinstance(val, list):
                return val
            if isinstance(val, dict) and "data" in val and isinstance(val["data"], list):
                return val["data"]
    return []


def _fmt_error(e: APIError, action: str) -> str:
    """Format an API error for LLM consumption."""
    if e.status_code == 401:
        return f"Authentication failed while {action}. Your session may have expired — try refreshing."
    if e.status_code == 403:
        return f"Permission denied while {action}. Your account may not have access to this data."
    if e.status_code == 404:
        return f"Not found: {action}. The requested resource may not exist."
    return f"Failed to {action}: {e.message}"


def _truncated(items: list, label: str) -> str:
    """Footer note if list was truncated."""
    if len(items) > _MAX_ITEMS:
        return f"\n*...and {len(items) - _MAX_ITEMS} more {label}. Showing first {_MAX_ITEMS}.*"
    return ""


def _safe_name(obj: dict, *keys: str) -> str:
    """Get first non-empty name from obj."""
    for k in keys:
        val = obj.get(k)
        if val:
            return str(val)
    return str(obj.get("id", "?"))


def _json_snippet(obj: Any, max_chars: int = 1500) -> str:
    """Compact JSON snippet, truncated if too long."""
    try:
        s = json.dumps(obj, indent=2, default=str)
    except Exception:
        s = str(obj)
    if len(s) > max_chars:
        return s[:max_chars] + "\n... (truncated)"
    return s


# ---------------------------------------------------------------------------
# Tool 1: Discovery
# ---------------------------------------------------------------------------

@registry.tool(
    name="config_api_discover",
    description=(
        "List all available Capillary Configuration API tools and what data they can retrieve. "
        "Call this when the user asks what configuration data is available or what APIs exist."
    ),
    module="config_apis",
    requires_permission=("config_apis", "view"),
    annotations={"display": "Listing available config APIs..."},
)
async def config_api_discover(ctx: ToolContext) -> str:
    """List all available config API tools."""
    return """**Available Capillary Configuration API Tools**

**Loyalty Programs:**
- `config_get_loyalty_programs` — List all loyalty programs
- `config_get_loyalty_program_details` — Full program detail (tiers, strategies, partners, currencies)
- `config_get_loyalty_promotions` — List/detail loyalty promotions
- `config_get_extended_fields` — Customer, transaction & line-item extended fields

**Campaigns & Messaging:**
- `config_list_campaigns` — Search/list campaigns
- `config_get_campaign_details` — Campaign by ID with messages
- `config_get_messaging_channels` — Email, SMS, WhatsApp, Push accounts & templates

**Coupons & Rewards:**
- `config_get_coupon_series` — List coupon/voucher series
- `config_get_coupon_series_details` — Detail for one coupon series
- `config_get_cart_promotions` — Cart/gift voucher promotions
- `config_get_rewards` — Brands & reward catalog

**Audience & Segments:**
- `config_get_audiences` — Search/list audience groups
- `config_get_audience_filters` — Audience filter definitions
- `config_get_target_groups` — Milestones & streaks target groups

**Organization:**
- `config_get_org_hierarchy` — Zones, concepts, stores hierarchy
- `config_get_org_entities` — Stores, zones, concepts, or tills
- `config_get_behavioral_events` — Behavioral events & customer labels

Use any of these tools to fetch real configuration data for this organization."""


# ---------------------------------------------------------------------------
# Tool 2: Loyalty Programs — List
# ---------------------------------------------------------------------------

@registry.tool(
    name="config_get_loyalty_programs",
    description=(
        "List all loyalty programs configured for this organization. "
        "Returns program names, IDs, types, and status. Call this when the user "
        "asks about loyalty programs, point programs, or membership programs."
    ),
    module="config_apis",
    requires_permission=("config_apis", "fetch"),
    annotations={"display": "Fetching loyalty programs..."},
)
async def config_get_loyalty_programs(ctx: ToolContext) -> str:
    """List all loyalty programs for the org."""
    try:
        async with _make_client(ctx) as client:
            data = await client.loyalty.get_loyalty_programs()
    except APIError as e:
        return _fmt_error(e, "fetching loyalty programs")

    programs = _extract_list(data)
    if not programs:
        return "No loyalty programs found for this organization."

    lines = [f"Found **{len(programs)}** loyalty program(s):\n"]
    for p in programs[:_MAX_ITEMS]:
        name = _safe_name(p, "name", "programName")
        pid = p.get("programId") or p.get("id") or "?"
        ptype = p.get("programType") or p.get("type") or ""
        status = p.get("status") or ""
        extra = []
        if ptype:
            extra.append(ptype)
        if status:
            extra.append(status)
        suffix = f" — {', '.join(extra)}" if extra else ""
        lines.append(f"- **{name}** (ID: {pid}){suffix}")

    lines.append(_truncated(programs, "programs"))
    lines.append("\n*Use `config_get_loyalty_program_details` with a program ID for full details.*")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 3: Loyalty Program Details
# ---------------------------------------------------------------------------

@registry.tool(
    name="config_get_loyalty_program_details",
    description=(
        "Get detailed info for a specific loyalty program including tiers, "
        "earning/expiry strategies, partner programs, and alternate currencies. "
        "Requires a program_id — use config_get_loyalty_programs first to find IDs."
    ),
    module="config_apis",
    requires_permission=("config_apis", "fetch"),
    annotations={"display": "Fetching program details..."},
)
async def config_get_loyalty_program_details(
    ctx: ToolContext, program_id: int,
) -> str:
    """Get full details for a loyalty program.
    program_id: The ID of the loyalty program to fetch details for.
    """
    try:
        async with _make_client(ctx) as client:
            # Fetch all related data in sequence (APIs depend on same session)
            program = await client.loyalty.get_loyalty_program_by_id(program_id)
            tiers_data = await client.loyalty.get_all_tiers_by_lp_id(program_id)
            strategies_data = await client.loyalty.get_strategies(program_id)
            partners_data = await client.loyalty.get_all_partner_programs_by_lp_id(program_id)
            currencies_data = await client.loyalty.get_alternate_currencies(program_id)
    except APIError as e:
        return _fmt_error(e, f"fetching details for program {program_id}")

    lines = [f"## Loyalty Program {program_id}\n"]

    # Program basics
    prog = program if isinstance(program, dict) else {}
    prog_inner = prog.get("entity", prog) if isinstance(prog.get("entity"), dict) else prog
    name = _safe_name(prog_inner, "name", "programName")
    lines.append(f"**Name:** {name}")
    for field in ("programType", "type", "status", "description"):
        val = prog_inner.get(field)
        if val:
            lines.append(f"**{field.replace('_', ' ').title()}:** {val}")

    # Tiers
    tiers = _extract_list(tiers_data, ("tiers", "data", "entity"))
    if tiers:
        lines.append(f"\n### Tiers ({len(tiers)})")
        for t in tiers:
            tname = _safe_name(t, "name", "tierName")
            tnumber = t.get("tierNumber") or t.get("rank") or ""
            lines.append(f"- **{tname}** (rank: {tnumber})")

    # Strategies
    strategies = _extract_list(strategies_data, ("strategies", "data", "entity"))
    if strategies:
        lines.append(f"\n### Point Strategies ({len(strategies)})")
        for s in strategies[:10]:
            sname = _safe_name(s, "name", "strategyName")
            stype = s.get("strategyType") or s.get("type") or ""
            lines.append(f"- **{sname}** — {stype}" if stype else f"- **{sname}**")

    # Partner programs
    partners = _extract_list(partners_data, ("partnerPrograms", "data", "entity"))
    if partners:
        lines.append(f"\n### Partner Programs ({len(partners)})")
        for pp in partners[:10]:
            ppname = _safe_name(pp, "name", "partnerProgramName")
            lines.append(f"- {ppname}")

    # Alternate currencies
    currencies = _extract_list(currencies_data, ("data", "entity", "alternateCurrencies"))
    if currencies:
        lines.append(f"\n### Alternate Currencies ({len(currencies)})")
        for c in currencies[:10]:
            cname = _safe_name(c, "name", "currencyName")
            ratio = c.get("conversionRatio") or c.get("ratio") or ""
            lines.append(f"- **{cname}**" + (f" (ratio: {ratio})" if ratio else ""))

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 4: Loyalty Promotions
# ---------------------------------------------------------------------------

@registry.tool(
    name="config_get_loyalty_promotions",
    description=(
        "List loyalty promotions (point-based promotions). Optionally get details "
        "for a specific promotion by ID. Call when the user asks about loyalty "
        "promotions, bonus points, or earning rules."
    ),
    module="config_apis",
    requires_permission=("config_apis", "fetch"),
    annotations={"display": "Fetching loyalty promotions..."},
)
async def config_get_loyalty_promotions(
    ctx: ToolContext,
    promotion_id: int = 0,
    program_id: int = 0,
    limit: int = 50,
) -> str:
    """List or get loyalty promotions.
    promotion_id: Specific promotion ID to fetch details (0 = list all).
    program_id: Program ID (required when fetching a specific promotion).
    limit: Max promotions to list (default 50).
    """
    try:
        async with _make_client(ctx) as client:
            if promotion_id and program_id:
                data = await client.loyalty.get_promotion(promotion_id, program_id)
                promo = data if isinstance(data, dict) else {}
                inner = promo.get("entity", promo)
                name = _safe_name(inner, "name", "promotionName")
                lines = [f"## Loyalty Promotion: {name} (ID: {promotion_id})\n"]
                lines.append(f"```json\n{_json_snippet(inner)}\n```")
                return "\n".join(lines)

            data = await client.loyalty.list_promotions(limit=limit)
    except APIError as e:
        return _fmt_error(e, "fetching loyalty promotions")

    promos = _extract_list(data, ("promotions", "data", "entity"))
    if not promos:
        return "No loyalty promotions found."

    lines = [f"Found **{len(promos)}** loyalty promotion(s):\n"]
    for p in promos[:_MAX_ITEMS]:
        name = _safe_name(p, "name", "promotionName")
        pid = p.get("id") or p.get("promotionId") or "?"
        status = p.get("status") or p.get("isActive", "")
        ptype = p.get("type") or p.get("promotionType") or ""
        extra = []
        if ptype:
            extra.append(ptype)
        if status:
            extra.append(str(status))
        suffix = f" — {', '.join(extra)}" if extra else ""
        lines.append(f"- **{name}** (ID: {pid}){suffix}")

    lines.append(_truncated(promos, "promotions"))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 5: Extended Fields
# ---------------------------------------------------------------------------

@registry.tool(
    name="config_get_extended_fields",
    description=(
        "Get extended fields (custom attributes) for customers, transactions, "
        "and line items. Also includes loyalty custom fields. Requires a program_id."
    ),
    module="config_apis",
    requires_permission=("config_apis", "fetch"),
    annotations={"display": "Fetching extended fields..."},
)
async def config_get_extended_fields(
    ctx: ToolContext, program_id: int = 0,
) -> str:
    """Get extended fields for a loyalty program.
    program_id: Loyalty program ID. If 0, will try to auto-detect from first program.
    """
    try:
        async with _make_client(ctx) as client:
            # Auto-resolve program_id
            if not program_id:
                progs_data = await client.loyalty.get_loyalty_programs()
                progs = _extract_list(progs_data)
                if progs:
                    program_id = progs[0].get("programId") or progs[0].get("id") or 0
                if not program_id:
                    return "No loyalty programs found — cannot fetch extended fields without a program ID."

            custom_fields = await client.loyalty.get_custom_fields()
            customer_ef = await client.loyalty.get_customer_extended_fields(program_id)
            txn_ef = await client.loyalty.get_txn_extended_fields(program_id)
            lineitem_ef = await client.loyalty.get_line_item_extended_fields(program_id)
    except APIError as e:
        return _fmt_error(e, "fetching extended fields")

    lines = [f"## Extended Fields (Program ID: {program_id})\n"]

    # Custom fields
    cf_list = _extract_list(custom_fields, ("data", "entity", "customFields"))
    if cf_list:
        lines.append(f"### Loyalty Custom Fields ({len(cf_list)})")
        for f in cf_list[:_MAX_ITEMS]:
            fname = _safe_name(f, "name", "fieldName")
            ftype = f.get("type") or f.get("dataType") or ""
            lines.append(f"- `{fname}` ({ftype})" if ftype else f"- `{fname}`")
        lines.append(_truncated(cf_list, "custom fields"))

    # Customer extended fields
    cef = _extract_list(customer_ef, ("data", "entity"))
    if cef:
        lines.append(f"\n### Customer Extended Fields ({len(cef)})")
        for f in cef[:_MAX_ITEMS]:
            fname = _safe_name(f, "name", "fieldName")
            ftype = f.get("type") or f.get("dataType") or ""
            lines.append(f"- `{fname}` ({ftype})" if ftype else f"- `{fname}`")
        lines.append(_truncated(cef, "customer fields"))

    # Txn extended fields
    tef = _extract_list(txn_ef, ("data", "entity"))
    if tef:
        lines.append(f"\n### Transaction Extended Fields ({len(tef)})")
        for f in tef[:_MAX_ITEMS]:
            fname = _safe_name(f, "name", "fieldName")
            ftype = f.get("type") or f.get("dataType") or ""
            lines.append(f"- `{fname}` ({ftype})" if ftype else f"- `{fname}`")
        lines.append(_truncated(tef, "transaction fields"))

    # Lineitem extended fields
    lef = _extract_list(lineitem_ef, ("data", "entity"))
    if lef:
        lines.append(f"\n### Line-Item Extended Fields ({len(lef)})")
        for f in lef[:_MAX_ITEMS]:
            fname = _safe_name(f, "name", "fieldName")
            ftype = f.get("type") or f.get("dataType") or ""
            lines.append(f"- `{fname}` ({ftype})" if ftype else f"- `{fname}`")
        lines.append(_truncated(lef, "line-item fields"))

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 6: List Campaigns
# ---------------------------------------------------------------------------

@registry.tool(
    name="config_list_campaigns",
    description=(
        "Search and list marketing campaigns. Optionally filter by campaign name. "
        "Call when the user asks about campaigns, marketing messages, or campaign history."
    ),
    module="config_apis",
    requires_permission=("config_apis", "fetch"),
    annotations={"display": "Listing campaigns..."},
)
async def config_list_campaigns(
    ctx: ToolContext, search: str = "", limit: int = 20,
) -> str:
    """Search and list campaigns.
    search: Filter campaigns by name (empty = all).
    limit: Max results (default 20).
    """
    try:
        async with _make_client(ctx) as client:
            data = await client.campaigns.list_campaigns(campaign_name=search, limit=limit)
    except APIError as e:
        return _fmt_error(e, "listing campaigns")

    campaigns = _extract_list(data, ("campaigns", "data", "entity", "results"))
    if not campaigns:
        return f"No campaigns found{' matching: ' + search if search else ''}."

    lines = [f"Found **{len(campaigns)}** campaign(s){' matching: ' + search if search else ''}:\n"]
    for c in campaigns[:_MAX_ITEMS]:
        name = _safe_name(c, "name", "campaignName")
        cid = c.get("id") or c.get("campaignId") or "?"
        status = c.get("status") or c.get("state") or ""
        ctype = c.get("type") or c.get("campaignType") or ""
        extra = []
        if ctype:
            extra.append(ctype)
        if status:
            extra.append(status)
        suffix = f" — {', '.join(extra)}" if extra else ""
        lines.append(f"- **{name}** (ID: {cid}){suffix}")

    lines.append(_truncated(campaigns, "campaigns"))
    lines.append("\n*Use `config_get_campaign_details` with a campaign ID for full details.*")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 7: Campaign Details
# ---------------------------------------------------------------------------

@registry.tool(
    name="config_get_campaign_details",
    description=(
        "Get detailed info for a specific campaign including its messages. "
        "Requires a campaign_id — use config_list_campaigns first to find IDs."
    ),
    module="config_apis",
    requires_permission=("config_apis", "fetch"),
    annotations={"display": "Fetching campaign details..."},
)
async def config_get_campaign_details(
    ctx: ToolContext, campaign_id: int,
) -> str:
    """Get campaign details with messages.
    campaign_id: The ID of the campaign to fetch.
    """
    try:
        async with _make_client(ctx) as client:
            campaign_data = await client.campaigns.get_campaign_by_id(campaign_id)
            messages_data = await client.campaigns.list_campaign_messages(
                campaign_id, limit=20, offset=0
            )
    except APIError as e:
        return _fmt_error(e, f"fetching campaign {campaign_id}")

    camp = campaign_data if isinstance(campaign_data, dict) else {}
    inner = camp.get("entity", camp) if isinstance(camp.get("entity"), dict) else camp

    name = _safe_name(inner, "name", "campaignName")
    lines = [f"## Campaign: {name} (ID: {campaign_id})\n"]

    for field in ("status", "state", "type", "campaignType", "startDate", "endDate", "description"):
        val = inner.get(field)
        if val:
            lines.append(f"**{field.replace('_', ' ').title()}:** {val}")

    # Messages
    msgs = _extract_list(messages_data, ("messages", "data", "entity", "results"))
    if msgs:
        lines.append(f"\n### Messages ({len(msgs)})")
        for m in msgs[:15]:
            mname = _safe_name(m, "name", "messageName")
            channel = m.get("channel") or m.get("type") or ""
            mstatus = m.get("status") or ""
            mid = m.get("id") or m.get("messageId") or "?"
            extra = []
            if channel:
                extra.append(channel)
            if mstatus:
                extra.append(mstatus)
            suffix = f" — {', '.join(extra)}" if extra else ""
            lines.append(f"- **{mname}** (ID: {mid}){suffix}")
    else:
        lines.append("\n*No messages found for this campaign.*")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 8: Messaging Channels
# ---------------------------------------------------------------------------

@registry.tool(
    name="config_get_messaging_channels",
    description=(
        "Get messaging channel configuration: email templates, SMS templates, "
        "WhatsApp accounts, and push notification accounts. Call when the user "
        "asks about messaging channels, templates, or communication setup."
    ),
    module="config_apis",
    requires_permission=("config_apis", "fetch"),
    annotations={"display": "Fetching messaging channels..."},
)
async def config_get_messaging_channels(ctx: ToolContext) -> str:
    """Get email, SMS, WhatsApp, and push notification setup."""
    lines = ["## Messaging Channels Configuration\n"]
    errors: List[str] = []

    try:
        async with _make_client(ctx) as client:
            # Email templates
            try:
                email_data = await client.campaigns.get_email_templates()
                emails = _extract_list(email_data, ("data", "entity", "templates", "results"))
                lines.append(f"### Email Templates ({len(emails)})")
                for t in emails[:10]:
                    tname = _safe_name(t, "name", "templateName")
                    tid = t.get("id") or t.get("templateId") or "?"
                    lines.append(f"- **{tname}** (ID: {tid})")
                if len(emails) > 10:
                    lines.append(f"  *...and {len(emails) - 10} more*")
                lines.append("")
            except APIError as e:
                errors.append(f"Email templates: {e.message}")

            # SMS templates
            try:
                sms_data = await client.campaigns.get_sms_templates()
                sms = _extract_list(sms_data, ("data", "entity", "templates", "results"))
                lines.append(f"### SMS Templates ({len(sms)})")
                for t in sms[:10]:
                    tname = _safe_name(t, "name", "templateName")
                    tid = t.get("id") or t.get("templateId") or "?"
                    lines.append(f"- **{tname}** (ID: {tid})")
                if len(sms) > 10:
                    lines.append(f"  *...and {len(sms) - 10} more*")
                lines.append("")
            except APIError as e:
                errors.append(f"SMS templates: {e.message}")

            # WhatsApp accounts
            try:
                wa_data = await client.campaigns.get_whatsapp_accounts()
                wa_accounts = _extract_list(wa_data, ("data", "entity", "accounts", "results"))
                lines.append(f"### WhatsApp Accounts ({len(wa_accounts)})")
                for a in wa_accounts[:10]:
                    aname = _safe_name(a, "name", "accountName", "displayName")
                    aid = a.get("id") or a.get("accountId") or "?"
                    lines.append(f"- **{aname}** (ID: {aid})")
                lines.append("")
            except APIError as e:
                errors.append(f"WhatsApp accounts: {e.message}")

            # Push notification accounts
            try:
                push_data = await client.campaigns.get_push_notification_accounts()
                push_accounts = _extract_list(push_data, ("data", "entity", "accounts", "results"))
                lines.append(f"### Push Notification Accounts ({len(push_accounts)})")
                for a in push_accounts[:10]:
                    aname = _safe_name(a, "name", "accountName", "displayName")
                    aid = a.get("id") or a.get("accountId") or "?"
                    lines.append(f"- **{aname}** (ID: {aid})")
                lines.append("")
            except APIError as e:
                errors.append(f"Push notification: {e.message}")

    except APIError as e:
        return _fmt_error(e, "fetching messaging channels")

    if errors:
        lines.append("### Errors")
        for err in errors:
            lines.append(f"- {err}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 9: Coupon Series — List
# ---------------------------------------------------------------------------

@registry.tool(
    name="config_get_coupon_series",
    description=(
        "List coupon/voucher series configured for this organization. "
        "Call when the user asks about coupons, vouchers, or discount series."
    ),
    module="config_apis",
    requires_permission=("config_apis", "fetch"),
    annotations={"display": "Fetching coupon series..."},
)
async def config_get_coupon_series(
    ctx: ToolContext, program_id: int = 0, owned_by: str = "",
) -> str:
    """List coupon/voucher series.
    program_id: Filter by loyalty program ID (0 = all).
    owned_by: Filter by ownership ('LOYALTY' or empty for all).
    """
    try:
        async with _make_client(ctx) as client:
            data = await client.coupon.list_coupon_series(
                program_id=program_id or None,
                owned_by="LOYALTY" if owned_by == "LOYALTY" else None,
            )
    except APIError as e:
        return _fmt_error(e, "fetching coupon series")

    series = _extract_list(data, ("data", "entity", "config", "results", "items"))
    if not series:
        return "No coupon series found."

    lines = [f"Found **{len(series)}** coupon series:\n"]
    for s in series[:_MAX_ITEMS]:
        name = _safe_name(s, "seriesName", "name")
        sid = s.get("id") or s.get("seriesId") or "?"
        discount_type = s.get("discountType") or s.get("type") or ""
        status = s.get("status") or ""
        extra = []
        if discount_type:
            extra.append(discount_type)
        if status:
            extra.append(status)
        suffix = f" — {', '.join(extra)}" if extra else ""
        lines.append(f"- **{name}** (ID: {sid}){suffix}")

    lines.append(_truncated(series, "series"))
    lines.append("\n*Use `config_get_coupon_series_details` with a series ID for full details.*")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 10: Coupon Series — Detail
# ---------------------------------------------------------------------------

@registry.tool(
    name="config_get_coupon_series_details",
    description=(
        "Get detailed configuration for a specific coupon/voucher series by ID. "
        "Requires a series_id — use config_get_coupon_series first to find IDs."
    ),
    module="config_apis",
    requires_permission=("config_apis", "fetch"),
    annotations={"display": "Fetching coupon series details..."},
)
async def config_get_coupon_series_details(
    ctx: ToolContext, series_id: int,
) -> str:
    """Get details for a specific coupon series.
    series_id: The ID of the coupon series to fetch.
    """
    try:
        async with _make_client(ctx) as client:
            data = await client.coupon.get_coupon_series_by_id(series_id)
    except APIError as e:
        return _fmt_error(e, f"fetching coupon series {series_id}")

    inner = data.get("entity", data) if isinstance(data, dict) else data
    if isinstance(inner, dict):
        name = _safe_name(inner, "seriesName", "name")
        lines = [f"## Coupon Series: {name} (ID: {series_id})\n"]
        lines.append(f"```json\n{_json_snippet(inner)}\n```")
        return "\n".join(lines)

    return f"Coupon series {series_id}:\n```json\n{_json_snippet(data)}\n```"


# ---------------------------------------------------------------------------
# Tool 11: Cart Promotions
# ---------------------------------------------------------------------------

@registry.tool(
    name="config_get_cart_promotions",
    description=(
        "List cart promotions and gift vouchers. Optionally filter by name, type, "
        "or active status. Call when the user asks about cart-level promotions, "
        "discount rules, or gift vouchers."
    ),
    module="config_apis",
    requires_permission=("config_apis", "fetch"),
    annotations={"display": "Fetching cart promotions..."},
)
async def config_get_cart_promotions(
    ctx: ToolContext, name: str = "", active_only: bool = False,
) -> str:
    """List cart promotions / gift vouchers.
    name: Filter by promotion name (empty = all).
    active_only: Only show active promotions.
    """
    try:
        async with _make_client(ctx) as client:
            data = await client.promotion.get_cart_promo_or_gift_voucher_by_name(
                name=name or None,
                active=True if active_only else None,
            )
    except APIError as e:
        return _fmt_error(e, "fetching cart promotions")

    promos = _extract_list(data, ("data", "entity", "promotions", "results"))
    if not promos:
        return f"No cart promotions found{' matching: ' + name if name else ''}."

    lines = [f"Found **{len(promos)}** cart promotion(s):\n"]
    for p in promos[:_MAX_ITEMS]:
        pname = _safe_name(p, "name", "promotionName")
        pid = p.get("id") or p.get("promotionId") or "?"
        ptype = p.get("type") or p.get("promotionType") or ""
        status = "ACTIVE" if p.get("active") else p.get("status", "")
        extra = []
        if ptype:
            extra.append(ptype)
        if status:
            extra.append(status)
        suffix = f" — {', '.join(extra)}" if extra else ""
        lines.append(f"- **{pname}** (ID: {pid}){suffix}")

    lines.append(_truncated(promos, "promotions"))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 12: Rewards
# ---------------------------------------------------------------------------

@registry.tool(
    name="config_get_rewards",
    description=(
        "Get brands and their reward catalogs. Lists brands first, then rewards "
        "for the first brand (or a specified brand_id). Call when the user asks "
        "about rewards, reward catalog, or fulfillment."
    ),
    module="config_apis",
    requires_permission=("config_apis", "fetch"),
    annotations={"display": "Fetching rewards..."},
)
async def config_get_rewards(
    ctx: ToolContext, brand_id: int = 0,
) -> str:
    """Get brands and reward catalog.
    brand_id: Specific brand ID to get rewards for (0 = auto-detect first brand).
    """
    try:
        async with _make_client(ctx) as client:
            brands_data = await client.reward.get_brands()
            brands = _extract_list(brands_data, ("data", "entity", "brands", "results"))

            if not brand_id and brands:
                brand_id = brands[0].get("id") or brands[0].get("brandId") or 0

            rewards = []
            if brand_id:
                try:
                    rewards_data = await client.reward.list_catalog_rewards(brand_id)
                    rewards = _extract_list(rewards_data, ("data", "entity", "rewards", "results"))
                except APIError:
                    pass  # Some orgs may not have reward catalog access
    except APIError as e:
        return _fmt_error(e, "fetching rewards")

    lines = ["## Rewards Configuration\n"]

    if brands:
        lines.append(f"### Brands ({len(brands)})")
        for b in brands[:10]:
            bname = _safe_name(b, "name", "brandName")
            bid = b.get("id") or b.get("brandId") or "?"
            lines.append(f"- **{bname}** (ID: {bid})")
        lines.append("")

    if rewards:
        lines.append(f"### Reward Catalog (Brand ID: {brand_id}) — {len(rewards)} rewards")
        for r in rewards[:_MAX_ITEMS]:
            rname = _safe_name(r, "name", "rewardName")
            rid = r.get("id") or r.get("rewardId") or "?"
            rtype = r.get("type") or r.get("rewardType") or ""
            status = r.get("status") or ""
            extra = []
            if rtype:
                extra.append(rtype)
            if status:
                extra.append(status)
            suffix = f" — {', '.join(extra)}" if extra else ""
            lines.append(f"- **{rname}** (ID: {rid}){suffix}")
        lines.append(_truncated(rewards, "rewards"))
    elif brand_id:
        lines.append(f"*No rewards found for brand {brand_id}.*")
    else:
        lines.append("*No brands found — cannot fetch rewards.*")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 13: Audiences
# ---------------------------------------------------------------------------

@registry.tool(
    name="config_get_audiences",
    description=(
        "Search and list audience groups. Call when the user asks about audiences, "
        "segments, customer groups, or targeting."
    ),
    module="config_apis",
    requires_permission=("config_apis", "fetch"),
    annotations={"display": "Fetching audiences..."},
)
async def config_get_audiences(
    ctx: ToolContext, search: str = "",
) -> str:
    """Search and list audience groups.
    search: Filter audiences by name (empty = all).
    """
    try:
        async with _make_client(ctx) as client:
            data = await client.campaigns.get_audiences(search=search)
    except APIError as e:
        return _fmt_error(e, "fetching audiences")

    audiences = _extract_list(data, ("data", "entity", "audiences", "results"))
    if not audiences:
        return f"No audiences found{' matching: ' + search if search else ''}."

    lines = [f"Found **{len(audiences)}** audience(s):\n"]
    for a in audiences[:_MAX_ITEMS]:
        aname = _safe_name(a, "name", "audienceName", "groupName")
        aid = a.get("id") or a.get("audienceId") or "?"
        atype = a.get("type") or a.get("audienceType") or ""
        count = a.get("customerCount") or a.get("size") or ""
        extra = []
        if atype:
            extra.append(atype)
        if count:
            extra.append(f"{count} customers")
        suffix = f" — {', '.join(extra)}" if extra else ""
        lines.append(f"- **{aname}** (ID: {aid}){suffix}")

    lines.append(_truncated(audiences, "audiences"))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 14: Audience Filters
# ---------------------------------------------------------------------------

@registry.tool(
    name="config_get_audience_filters",
    description=(
        "Get audience filter definitions and dimension/attribute availability. "
        "Call when the user asks about audience filtering criteria, available "
        "dimensions, or how to build audience queries."
    ),
    module="config_apis",
    requires_permission=("config_apis", "fetch"),
    annotations={"display": "Fetching audience filters..."},
)
async def config_get_audience_filters(ctx: ToolContext) -> str:
    """Get audience filter definitions and dimension availability."""
    try:
        async with _make_client(ctx) as client:
            filters_data = await client.audience.get_audience_filters()
            avail_data = await client.audience.get_dim_attr_value_availability()
    except APIError as e:
        return _fmt_error(e, "fetching audience filters")

    lines = ["## Audience Filter Configuration\n"]

    # Filters
    filters = _extract_list(filters_data, ("data", "entity", "filters", "results"))
    if filters:
        lines.append(f"### Available Filters ({len(filters)})")
        for f in filters[:_MAX_ITEMS]:
            fname = _safe_name(f, "name", "filterName", "label")
            ftype = f.get("type") or f.get("filterType") or ""
            lines.append(f"- **{fname}** ({ftype})" if ftype else f"- **{fname}**")
        lines.append(_truncated(filters, "filters"))
        lines.append("")

    # Dimension availability
    if isinstance(avail_data, dict):
        dims = avail_data.get("data") or avail_data.get("dimensions") or avail_data
        if isinstance(dims, dict):
            lines.append("### Dimension/Attribute Availability")
            for dim, attrs in list(dims.items())[:15]:
                if isinstance(attrs, (list, dict)):
                    count = len(attrs)
                    lines.append(f"- **{dim}**: {count} attributes")
                else:
                    lines.append(f"- **{dim}**: {attrs}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 15: Target Groups
# ---------------------------------------------------------------------------

@registry.tool(
    name="config_get_target_groups",
    description=(
        "List target groups (milestones, streaks, unified targets). "
        "Call when the user asks about milestones, streaks, target groups, or goals."
    ),
    module="config_apis",
    requires_permission=("config_apis", "fetch"),
    annotations={"display": "Fetching target groups..."},
)
async def config_get_target_groups(
    ctx: ToolContext, name: str = "",
) -> str:
    """List target groups.
    name: Filter by target group name (empty = all).
    """
    try:
        async with _make_client(ctx) as client:
            data = await client.org_settings.get_all_target_groups(name=name or None)
    except APIError as e:
        return _fmt_error(e, "fetching target groups")

    targets = _extract_list(data, ("data", "entity", "targets", "targetGroups", "results"))
    if not targets:
        return f"No target groups found{' matching: ' + name if name else ''}."

    lines = [f"Found **{len(targets)}** target group(s):\n"]
    for t in targets[:_MAX_ITEMS]:
        tname = _safe_name(t, "name", "targetGroupName")
        tid = t.get("id") or t.get("targetGroupId") or "?"
        ttype = t.get("type") or t.get("targetType") or ""
        status = t.get("status") or t.get("active", "")
        extra = []
        if ttype:
            extra.append(ttype)
        if status:
            extra.append(str(status))
        suffix = f" — {', '.join(extra)}" if extra else ""
        lines.append(f"- **{tname}** (ID: {tid}){suffix}")

    lines.append(_truncated(targets, "target groups"))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 16: Org Hierarchy
# ---------------------------------------------------------------------------

@registry.tool(
    name="config_get_org_hierarchy",
    description=(
        "Get the organization hierarchy — zones, concepts, and stores. "
        "Call when the user asks about org structure, store locations, "
        "zones, or organizational hierarchy."
    ),
    module="config_apis",
    requires_permission=("config_apis", "fetch"),
    annotations={"display": "Fetching org hierarchy..."},
)
async def config_get_org_hierarchy(ctx: ToolContext) -> str:
    """Get organization hierarchy (zones, concepts, stores)."""
    try:
        async with _make_client(ctx) as client:
            data = await client.intouch.get_organization_hierarchy()
    except APIError as e:
        return _fmt_error(e, "fetching org hierarchy")

    # Try to extract meaningful structure
    if isinstance(data, dict):
        inner = data.get("entity", data) if isinstance(data.get("entity"), dict) else data
        org_name = _safe_name(inner, "name", "orgName")
        lines = [f"## Organization Hierarchy: {org_name}\n"]

        # Count entities
        zones = inner.get("zones") or inner.get("zone") or []
        if isinstance(zones, list):
            lines.append(f"**Zones:** {len(zones)}")
            for z in zones[:15]:
                zname = _safe_name(z, "name", "zoneName")
                concepts = z.get("concepts") or z.get("concept") or []
                concept_count = len(concepts) if isinstance(concepts, list) else 0
                lines.append(f"- **{zname}** ({concept_count} concepts)")
                if isinstance(concepts, list):
                    for c in concepts[:5]:
                        cname = _safe_name(c, "name", "conceptName")
                        stores = c.get("stores") or c.get("store") or []
                        store_count = len(stores) if isinstance(stores, list) else 0
                        lines.append(f"  - {cname} ({store_count} stores)")
            if len(zones) > 15:
                lines.append(f"  *...and {len(zones) - 15} more zones*")
        else:
            lines.append(f"```json\n{_json_snippet(inner, 2000)}\n```")

        return "\n".join(lines)

    return f"Organization hierarchy:\n```json\n{_json_snippet(data, 2000)}\n```"


# ---------------------------------------------------------------------------
# Tool 17: Org Entities
# ---------------------------------------------------------------------------

@registry.tool(
    name="config_get_org_entities",
    description=(
        "Get organization entities of a specific type: STORE, ZONE, CONCEPT, or TILL. "
        "Call when the user asks for a list of stores, zones, concepts, or tills."
    ),
    module="config_apis",
    requires_permission=("config_apis", "fetch"),
    annotations={"display": "Fetching org entities..."},
)
async def config_get_org_entities(
    ctx: ToolContext, entity_type: str = "STORE",
) -> str:
    """Get org entities by type.
    entity_type: Type of entity to fetch — STORE, ZONE, CONCEPT, or TILL.
    """
    valid = {"STORE", "ZONE", "CONCEPT", "TILL"}
    entity_type = entity_type.upper()
    if entity_type not in valid:
        return f"Invalid entity_type: '{entity_type}'. Valid types: {', '.join(sorted(valid))}"

    try:
        async with _make_client(ctx) as client:
            data = await client.arya.get_entities(entity_type)  # type: ignore[arg-type]
    except APIError as e:
        return _fmt_error(e, f"fetching {entity_type} entities")

    entities = _extract_list(data, ("data", "entity", "entities", "results"))
    if not entities:
        return f"No {entity_type} entities found."

    lines = [f"Found **{len(entities)}** {entity_type.lower()}(s):\n"]
    for ent in entities[:_MAX_ITEMS]:
        ename = _safe_name(ent, "name", "code", "entityName")
        eid = ent.get("id") or ent.get("entityId") or "?"
        ecode = ent.get("code") or ent.get("entityCode") or ""
        extra = f" (code: {ecode})" if ecode and ecode != ename else ""
        lines.append(f"- **{ename}** (ID: {eid}){extra}")

    lines.append(_truncated(entities, entity_type.lower() + "s"))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 18: Behavioral Events & Customer Labels
# ---------------------------------------------------------------------------

@registry.tool(
    name="config_get_behavioral_events",
    description=(
        "Get behavioral events and customer status labels configured for this org. "
        "Call when the user asks about events, customer lifecycle stages, or labels."
    ),
    module="config_apis",
    requires_permission=("config_apis", "fetch"),
    annotations={"display": "Fetching behavioral events..."},
)
async def config_get_behavioral_events(ctx: ToolContext) -> str:
    """Get behavioral events and customer labels."""
    lines = ["## Behavioral Events & Customer Labels\n"]
    errors: List[str] = []

    try:
        async with _make_client(ctx) as client:
            try:
                events_data = await client.org_settings.get_behavioral_events()
                events = _extract_list(events_data, ("data", "entity", "events", "results"))
                lines.append(f"### Behavioral Events ({len(events)})")
                for e in events[:_MAX_ITEMS]:
                    ename = _safe_name(e, "name", "eventName")
                    etype = e.get("type") or e.get("eventType") or ""
                    lines.append(f"- **{ename}** ({etype})" if etype else f"- **{ename}**")
                lines.append(_truncated(events, "events"))
                lines.append("")
            except APIError as e:
                errors.append(f"Behavioral events: {e.message}")

            try:
                labels_data = await client.org_settings.get_customer_labels()
                labels = _extract_list(labels_data, ("data", "entity", "labels", "results"))
                lines.append(f"### Customer Status Labels ({len(labels)})")
                for lbl in labels[:_MAX_ITEMS]:
                    lname = _safe_name(lbl, "name", "label", "labelName")
                    ldesc = lbl.get("description") or ""
                    lines.append(f"- **{lname}**" + (f" — {ldesc}" if ldesc else ""))
                lines.append(_truncated(labels, "labels"))
            except APIError as e:
                errors.append(f"Customer labels: {e.message}")

    except APIError as e:
        return _fmt_error(e, "fetching behavioral events")

    if errors:
        lines.append("\n### Errors")
        for err in errors:
            lines.append(f"- {err}")

    return "\n".join(lines)
