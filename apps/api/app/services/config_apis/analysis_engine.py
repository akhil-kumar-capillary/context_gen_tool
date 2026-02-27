"""
Config APIs analysis engine — deep pattern extraction.

Takes raw extracted data and produces structured reference material for LLM
context-document authoring.  The goal is to extract **real config objects,
org-specific patterns, naming conventions, relationships, and valid values**
so the LLM can write context docs that help aiRA *create* new Capillary
configurations.

Key improvements over v1:
- Union schema built from ALL items (not just first)
- Stratified sampling by type/status
- Full complex objects preserved (no more <dict N items> truncation)
- Org-specific pattern extraction (naming, field combos, relationships)
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter, defaultdict
from typing import Any, Callable, Awaitable, Dict, List, Optional, Set, Tuple

from app.services.config_apis.storage import ConfigStorageService

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, int, int, str], Awaitable[None]]

ANALYSIS_PHASES = [
    "inventory",
    "loyalty_structure",
    "campaign_patterns",
    "promotion_rules",
    "audience_segmentation",
    "customizations",
    "channel_config",
    "relationships",
    "fingerprinting",
    "counters",
    "clustering",
]


async def run_analysis(
    *,
    analysis_id: str,
    run_id: str,
    user_id: int,
    org_id: int,
    on_progress: Optional[ProgressCallback] = None,
) -> Dict[str, Any]:
    """Run analysis on config extraction data."""
    storage = ConfigStorageService()

    async def emit(phase: str, completed: int, total: int, detail: str):
        if on_progress:
            await on_progress(phase, completed, total, detail)

    # Load extraction data
    await emit("loading", 0, len(ANALYSIS_PHASES), "Loading extraction data...")
    extraction = await storage.get_extraction_run(run_id)
    if not extraction:
        raise ValueError(f"Extraction run {run_id} not found")

    from app.database import async_session
    from app.models.config_pipeline import ConfigExtractionRun
    from sqlalchemy import select
    import uuid

    async with async_session() as db:
        result = await db.execute(
            select(ConfigExtractionRun).where(
                ConfigExtractionRun.id == uuid.UUID(run_id)
            )
        )
        row = result.scalar_one_or_none()
        if not row or not row.extracted_data:
            raise ValueError("Extraction has no data")
        raw_data = row.extracted_data

    analysis_data: Dict[str, Any] = {}
    total = len(ANALYSIS_PHASES)

    # Phase 1: Inventory
    await emit("inventory", 0, total, "Computing inventory...")
    analysis_data["inventory"] = _analyze_inventory(raw_data)

    # Phase 2: Loyalty Structure
    await emit("loyalty_structure", 1, total, "Extracting loyalty configs & patterns...")
    analysis_data["loyalty_structure"] = _analyze_loyalty(raw_data)

    # Phase 3: Campaign Patterns
    await emit("campaign_patterns", 2, total, "Extracting campaign configs & patterns...")
    analysis_data["campaign_patterns"] = _analyze_campaigns(raw_data)

    # Phase 4: Promotion Rules
    await emit("promotion_rules", 3, total, "Extracting promotion configs & rules...")
    analysis_data["promotion_rules"] = _analyze_promotions(raw_data)

    # Phase 5: Audience & Segmentation
    await emit("audience_segmentation", 4, total, "Extracting audience configs...")
    analysis_data["audience_segmentation"] = _analyze_audiences(raw_data)

    # Phase 6: Customizations
    await emit("customizations", 5, total, "Extracting field definitions & custom fields...")
    analysis_data["customizations"] = _analyze_customizations(raw_data)

    # Phase 7: Channel Config
    await emit("channel_config", 6, total, "Extracting channel & template config...")
    analysis_data["channel_config"] = _analyze_channels(raw_data)

    # Phase 8: Relationships
    await emit("relationships", 7, total, "Mapping cross-references & patterns...")
    analysis_data["relationships"] = _analyze_relationships(raw_data)

    # Phase 9: Fingerprinting
    await emit("fingerprinting", 8, total, "Building config fingerprints...")
    from app.services.config_apis.fingerprint_engine import extract_all_fingerprints
    fingerprints, entity_type_counts = extract_all_fingerprints(raw_data)
    analysis_data["fingerprints"] = [fp.to_dict() for fp in fingerprints]
    analysis_data["entity_type_counts"] = entity_type_counts

    # Phase 10: Frequency Counters
    await emit("counters", 9, total, "Computing frequency counters...")
    from app.services.config_apis.frequency_counters import (
        build_counters as _build_counters,
        counters_to_serializable,
    )
    counters, total_count = _build_counters(fingerprints)
    analysis_data["counters"] = counters_to_serializable(counters)
    analysis_data["total_count"] = total_count

    # Phase 11: Clustering + Top-5 Templates
    await emit("clustering", 10, total, "Building clusters & selecting templates...")
    from app.services.config_apis.cluster_builder import build_clusters
    clusters = build_clusters(fingerprints, max_templates_per_type=5)
    analysis_data["clusters"] = clusters

    # Save to DB
    await emit("saving", total, total, "Saving analysis results...")
    await storage.save_analysis_run(
        analysis_id=analysis_id,
        run_id=run_id,
        user_id=user_id,
        org_id=org_id,
        analysis_data=analysis_data,
    )

    await emit("complete", total, total, "Analysis complete")
    return {"analysis_id": analysis_id, "phases": list(analysis_data.keys())}


# ═══════════════════════════════════════════════════════════════════════
# Core Helpers
# ═══════════════════════════════════════════════════════════════════════

def _safe_list(data: Any, *keys: str) -> list:
    current = data
    for k in keys:
        if isinstance(current, dict):
            current = current.get(k)
        else:
            return []
    return current if isinstance(current, list) else []


def _safe_dict(data: Any, *keys: str) -> dict:
    current = data
    for k in keys:
        if isinstance(current, dict):
            current = current.get(k)
        else:
            return {}
    return current if isinstance(current, dict) else {}


def _extract_items(data: Any) -> list:
    """Extract list of items from various Capillary API response shapes."""
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


def _count_items(data: Any) -> int:
    return len(_extract_items(data))


# ═══════════════════════════════════════════════════════════════════════
# Union Schema — built from ALL items
# ═══════════════════════════════════════════════════════════════════════

def _build_union_schema(
    items: List[Dict], max_values: int = 20
) -> Dict[str, Any]:
    """Build field schema from ALL items with presence %, types, and sample values.

    Returns:
        {field_name: {
            "type": str,
            "presence_pct": int (0-100),
            "required": bool (>90% presence),
            "sample_values": [...] (up to max_values distinct values),
        }}
    """
    if not items:
        return {}

    n = len(items)
    field_info: Dict[str, Dict[str, Any]] = {}

    for item in items:
        if not isinstance(item, dict):
            continue
        for k, v in item.items():
            if k.startswith("_"):
                continue
            if k not in field_info:
                field_info[k] = {
                    "types": Counter(),
                    "count": 0,
                    "values": set(),
                    "has_nested": False,
                    "nested_keys": set(),
                }
            fi = field_info[k]
            fi["count"] += 1

            if v is None:
                fi["types"]["null"] += 1
            elif isinstance(v, bool):
                fi["types"]["boolean"] += 1
                fi["values"].add(str(v))
            elif isinstance(v, int):
                fi["types"]["integer"] += 1
                if len(fi["values"]) < max_values:
                    fi["values"].add(v)
            elif isinstance(v, float):
                fi["types"]["float"] += 1
            elif isinstance(v, str):
                fi["types"]["string"] += 1
                if len(fi["values"]) < max_values and len(v) < 200:
                    fi["values"].add(v)
            elif isinstance(v, list):
                fi["types"]["array"] += 1
                if v and isinstance(v[0], dict):
                    fi["has_nested"] = True
                    for nk in v[0].keys():
                        fi["nested_keys"].add(nk)
            elif isinstance(v, dict):
                fi["types"]["object"] += 1
                fi["has_nested"] = True
                for nk in v.keys():
                    fi["nested_keys"].add(nk)

    schema: Dict[str, Any] = {}
    for k, fi in field_info.items():
        most_common_type = fi["types"].most_common(1)[0][0] if fi["types"] else "unknown"
        presence_pct = round(fi["count"] * 100 / n) if n > 0 else 0

        entry: Dict[str, Any] = {
            "type": most_common_type,
            "presence_pct": presence_pct,
            "required": presence_pct >= 90,
        }

        vals = fi["values"]
        if vals and len(vals) <= max_values:
            sorted_vals = sorted(str(x) for x in vals)
            entry["sample_values"] = sorted_vals[:max_values]

        if fi["has_nested"] and fi["nested_keys"]:
            entry["nested_keys"] = sorted(fi["nested_keys"])[:30]

        schema[k] = entry

    return schema


# ═══════════════════════════════════════════════════════════════════════
# Stratified Sampling — cover all types
# ═══════════════════════════════════════════════════════════════════════

def _stratified_sample(
    items: List[Dict],
    key_field: str,
    max_per_type: int = 2,
    max_total: int = 15,
) -> List[Dict]:
    """Pick examples covering all distinct values of key_field."""
    if not items:
        return []

    by_type: Dict[str, List[Dict]] = defaultdict(list)
    for item in items:
        if not isinstance(item, dict):
            continue
        key_val = str(item.get(key_field, "unknown"))
        by_type[key_val].append(item)

    sampled: List[Dict] = []
    for type_val, type_items in by_type.items():
        for item in type_items[:max_per_type]:
            if len(sampled) >= max_total:
                break
            sampled.append(item)
        if len(sampled) >= max_total:
            break

    return sampled


# ═══════════════════════════════════════════════════════════════════════
# Object Preservation — keep full structures
# ═══════════════════════════════════════════════════════════════════════

_STR_CAP = 2000  # preserve real content (was 300)


def _preserve_objects(items: list, max_items: int = 10) -> list:
    """Return up to max_items objects with FULL nested structures preserved.

    Keeps rule expressions, workflow steps, conditions — the actual business
    logic.  Only caps very long strings.
    """
    preserved = []
    for item in items[:max_items]:
        if isinstance(item, dict):
            preserved.append(_cap_object(item))
        else:
            preserved.append(item)
    return preserved


def _cap_object(obj: Any, depth: int = 0) -> Any:
    """Recursively cap an object — only long strings are shortened."""
    if depth > 10:
        return str(obj)[:200] + "..." if isinstance(obj, str) and len(obj) > 200 else obj

    if isinstance(obj, dict):
        return {k: _cap_object(v, depth + 1) for k, v in obj.items() if not k.startswith("_")}
    elif isinstance(obj, list):
        if len(obj) > 50:
            capped = [_cap_object(x, depth + 1) for x in obj[:30]]
            capped.append(f"... ({len(obj) - 30} more items)")
            return capped
        return [_cap_object(x, depth + 1) for x in obj]
    elif isinstance(obj, str) and len(obj) > _STR_CAP:
        return obj[:_STR_CAP] + "..."
    return obj


# ═══════════════════════════════════════════════════════════════════════
# Pattern Extraction — org-specific conventions
# ═══════════════════════════════════════════════════════════════════════

def _extract_naming_patterns(items: List[Dict], name_field: str = "name") -> List[str]:
    """Detect naming conventions from a list of config objects."""
    names = []
    for item in items:
        if isinstance(item, dict):
            n = item.get(name_field)
            if isinstance(n, str) and n.strip():
                names.append(n.strip())

    if len(names) < 2:
        return []

    patterns: List[str] = []

    # Detect common prefixes
    prefixes = Counter()
    for name in names:
        parts = re.split(r'[_\-\s]+', name)
        if len(parts) >= 2:
            prefixes[parts[0]] += 1
    for prefix, count in prefixes.most_common(5):
        if count >= 2 and count >= len(names) * 0.3:
            patterns.append(f"Common prefix: '{prefix}' (used in {count}/{len(names)} names)")

    # Detect separator style
    has_underscore = sum(1 for n in names if "_" in n)
    has_dash = sum(1 for n in names if "-" in n)
    has_space = sum(1 for n in names if " " in n)
    if has_underscore > len(names) * 0.5:
        patterns.append("Naming uses underscore_case")
    elif has_dash > len(names) * 0.5:
        patterns.append("Naming uses kebab-case")
    elif has_space > len(names) * 0.5:
        patterns.append("Naming uses spaces")

    return patterns


def _extract_field_value_patterns(
    items: List[Dict], fields: List[str]
) -> Dict[str, Any]:
    """For a set of fields, find the most common values (dominant patterns)."""
    result: Dict[str, Any] = {}
    for field in fields:
        counter: Counter = Counter()
        for item in items:
            if isinstance(item, dict):
                v = item.get(field)
                if v is not None and not isinstance(v, (dict, list)):
                    counter[str(v)] += 1
        if counter:
            total = sum(counter.values())
            top = counter.most_common(5)
            result[field] = {
                "total": total,
                "top_values": [
                    {"value": val, "count": cnt, "pct": round(cnt * 100 / total)}
                    for val, cnt in top
                ],
            }
    return result


# ═══════════════════════════════════════════════════════════════════════
# Phase 1: Inventory (lightweight summary)
# ═══════════════════════════════════════════════════════════════════════

def _analyze_inventory(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Quick object counts per category."""
    inventory: Dict[str, Any] = {"available": True}
    for cat_id, cat_data in raw.items():
        if not isinstance(cat_data, dict):
            continue
        cat_counts: Dict[str, int] = {}
        for api_name, api_data in cat_data.items():
            if isinstance(api_data, dict) and "_error" in api_data:
                continue
            cat_counts[api_name] = _count_items(api_data)
        inventory[cat_id] = {
            "total_apis": len(cat_data),
            "counts": cat_counts,
            "total_objects": sum(cat_counts.values()),
        }
    return inventory


# ═══════════════════════════════════════════════════════════════════════
# Phase 2: Loyalty — programs, tiers, strategies (full configs)
# ═══════════════════════════════════════════════════════════════════════

def _analyze_loyalty(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Extract loyalty program configs with full strategies and tier structures."""
    loyalty_data = _safe_dict(raw, "loyalty")
    if not loyalty_data:
        return {"available": False}

    programs = _extract_items(loyalty_data.get("programs"))
    tiers = _extract_items(loyalty_data.get("tiers"))
    strategies = _extract_items(loyalty_data.get("strategies"))
    currencies = _extract_items(loyalty_data.get("alternate_currencies"))
    partner_programs = _extract_items(loyalty_data.get("partner_programs"))
    event_types = _extract_items(loyalty_data.get("event_types"))
    custom_fields = _extract_items(loyalty_data.get("custom_fields"))
    org_labels = _extract_items(loyalty_data.get("org_labels"))
    liability_owners = _extract_items(loyalty_data.get("liability_owners"))

    program_detail_raw = loyalty_data.get("program_detail")
    program_detail = None
    if isinstance(program_detail_raw, dict) and "_error" not in program_detail_raw:
        program_detail = program_detail_raw

    result: Dict[str, Any] = {"available": True}

    if programs:
        result["programs"] = {
            "count": len(programs),
            "union_schema": _build_union_schema(programs),
            "objects": _preserve_objects(programs, max_items=20),
            "naming_patterns": _extract_naming_patterns(programs),
            "value_patterns": _extract_field_value_patterns(
                programs, ["programType", "status", "pointsExpiryType"]
            ),
        }

    if program_detail:
        result["program_detail"] = _cap_object(program_detail)

    if tiers:
        result["tiers"] = {
            "count": len(tiers),
            "union_schema": _build_union_schema(tiers),
            "objects": _preserve_objects(tiers, max_items=30),
            "naming_patterns": _extract_naming_patterns(tiers, "name"),
        }

    if strategies:
        result["strategies"] = {
            "count": len(strategies),
            "union_schema": _build_union_schema(strategies),
            "objects": _preserve_objects(strategies, max_items=20),
            "value_patterns": _extract_field_value_patterns(
                strategies, ["type", "allocationType", "expiryType"]
            ),
            "naming_patterns": _extract_naming_patterns(strategies),
        }

    if currencies:
        result["alternate_currencies"] = {
            "count": len(currencies),
            "objects": _preserve_objects(currencies, max_items=10),
        }

    if partner_programs:
        result["partner_programs"] = {
            "count": len(partner_programs),
            "objects": _preserve_objects(partner_programs, max_items=10),
        }

    if event_types:
        result["event_types"] = {
            "count": len(event_types),
            "objects": _preserve_objects(event_types, max_items=30),
        }

    if custom_fields:
        result["custom_fields"] = {
            "count": len(custom_fields),
            "union_schema": _build_union_schema(custom_fields),
            "objects": _preserve_objects(custom_fields, max_items=30),
        }

    if org_labels:
        result["org_labels"] = {
            "count": len(org_labels),
            "objects": _preserve_objects(org_labels, max_items=30),
        }

    if liability_owners:
        result["liability_owners"] = {
            "count": len(liability_owners),
            "objects": _preserve_objects(liability_owners, max_items=10),
        }

    return result


# ═══════════════════════════════════════════════════════════════════════
# Phase 3: Campaigns — full configs with messages and templates
# ═══════════════════════════════════════════════════════════════════════

def _analyze_campaigns(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Extract campaign configs with full message structures and templates."""
    camp_data = _safe_dict(raw, "campaigns")
    if not camp_data:
        return {"available": False}

    result: Dict[str, Any] = {"available": True}

    campaigns_list = _extract_items(camp_data.get("campaigns_list"))
    if campaigns_list:
        result["campaigns"] = {
            "count": len(campaigns_list),
            "union_schema": _build_union_schema(campaigns_list),
            "examples": _stratified_sample(campaigns_list, "type", max_per_type=3, max_total=10),
            "value_patterns": _extract_field_value_patterns(
                campaigns_list, ["type", "status", "campaignType"]
            ),
            "naming_patterns": _extract_naming_patterns(campaigns_list),
        }

    details = camp_data.get("campaign_details", [])
    if isinstance(details, list) and details:
        campaign_configs = []
        message_examples = []
        type_counter: Dict[str, int] = {}
        channel_counter: Dict[str, int] = {}

        for d in details:
            if not isinstance(d, dict):
                continue
            detail = d.get("detail", {})
            if isinstance(detail, dict) and "_error" not in detail:
                campaign_configs.append(detail)
                ctype = detail.get("type") or detail.get("campaignType") or "unknown"
                type_counter[ctype] = type_counter.get(ctype, 0) + 1

            msgs = d.get("messages")
            if isinstance(msgs, dict):
                msg_list = _extract_items(msgs)
                for m in msg_list:
                    if isinstance(m, dict):
                        ch = m.get("channel") or m.get("type") or "unknown"
                        channel_counter[ch] = channel_counter.get(ch, 0) + 1
                        message_examples.append(m)

        if campaign_configs:
            result["campaign_configs"] = {
                "count": len(campaign_configs),
                "union_schema": _build_union_schema(campaign_configs),
                "examples": _stratified_sample(campaign_configs, "type", max_per_type=2, max_total=8),
            }
        result["type_distribution"] = type_counter
        result["channel_distribution"] = channel_counter

        if message_examples:
            result["messages"] = {
                "count": len(message_examples),
                "union_schema": _build_union_schema(message_examples),
                "examples": _preserve_objects(
                    _stratified_sample(message_examples, "channel", max_per_type=2, max_total=10),
                    max_items=10,
                ),
            }

    sms_templates = _extract_items(camp_data.get("sms_templates"))
    if sms_templates:
        result["sms_templates"] = {
            "count": len(sms_templates),
            "union_schema": _build_union_schema(sms_templates),
            "examples": _preserve_objects(sms_templates, max_items=8),
            "naming_patterns": _extract_naming_patterns(sms_templates),
        }

    email_templates = _extract_items(camp_data.get("email_templates"))
    if email_templates:
        result["email_templates"] = {
            "count": len(email_templates),
            "union_schema": _build_union_schema(email_templates),
            "examples": _preserve_objects(email_templates, max_items=5),
            "naming_patterns": _extract_naming_patterns(email_templates),
        }

    attribution = camp_data.get("default_attribution")
    if isinstance(attribution, dict) and "_error" not in attribution:
        result["attribution_config"] = attribution

    program_configs = camp_data.get("program_configurations")
    if isinstance(program_configs, dict) and "_error" not in program_configs:
        result["program_configurations"] = program_configs

    wa_accounts = _extract_items(camp_data.get("whatsapp_accounts"))
    if wa_accounts:
        result["whatsapp_accounts"] = {
            "count": len(wa_accounts),
            "objects": _preserve_objects(wa_accounts, max_items=5),
        }

    push_accounts = _extract_items(camp_data.get("push_notification_accounts"))
    if push_accounts:
        result["push_accounts"] = {
            "count": len(push_accounts),
            "objects": _preserve_objects(push_accounts, max_items=5),
        }

    return result


# ═══════════════════════════════════════════════════════════════════════
# Phase 4: Promotions — full workflow structures preserved
# ═══════════════════════════════════════════════════════════════════════

def _analyze_promotions(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Extract promotion configs with FULL workflow structures preserved."""
    promo_data = _safe_dict(raw, "promotions")
    if not promo_data:
        return {"available": False}

    result: Dict[str, Any] = {"available": True}

    loyalty_promos = _extract_items(promo_data.get("loyalty_promotions"))
    if loyalty_promos:
        result["loyalty_promotions"] = {
            "count": len(loyalty_promos),
            "union_schema": _build_union_schema(loyalty_promos),
            "value_patterns": _extract_field_value_patterns(
                loyalty_promos, ["type", "status", "stackability", "applyOn", "triggerActivity"]
            ),
            "examples": _preserve_objects(
                _stratified_sample(loyalty_promos, "type", max_per_type=3, max_total=10),
                max_items=10,
            ),
            "naming_patterns": _extract_naming_patterns(loyalty_promos),
        }

    cart_promos = _extract_items(promo_data.get("cart_promotions"))
    if cart_promos:
        result["cart_promotions"] = {
            "count": len(cart_promos),
            "union_schema": _build_union_schema(cart_promos),
            "value_patterns": _extract_field_value_patterns(
                cart_promos, ["type", "status", "promotionType"]
            ),
            "examples": _preserve_objects(
                _stratified_sample(cart_promos, "type", max_per_type=3, max_total=10),
                max_items=10,
            ),
            "naming_patterns": _extract_naming_patterns(cart_promos),
        }

    cart_cf = _extract_items(promo_data.get("cart_promotion_custom_fields"))
    if cart_cf:
        result["cart_promotion_custom_fields"] = {
            "count": len(cart_cf),
            "objects": _preserve_objects(cart_cf, max_items=30),
        }

    rewards_cf = _extract_items(promo_data.get("rewards_custom_fields"))
    if rewards_cf:
        result["rewards_custom_fields"] = {
            "count": len(rewards_cf),
            "objects": _preserve_objects(rewards_cf, max_items=30),
        }

    rewards_groups = _extract_items(promo_data.get("rewards_groups"))
    if rewards_groups:
        result["rewards_groups"] = {
            "count": len(rewards_groups),
            "objects": _preserve_objects(rewards_groups, max_items=30),
        }

    rewards_langs = _extract_items(promo_data.get("rewards_languages"))
    if rewards_langs:
        result["rewards_languages"] = {
            "count": len(rewards_langs),
            "objects": _preserve_objects(rewards_langs, max_items=20),
        }

    segments = _extract_items(promo_data.get("segments"))
    if segments:
        result["available_segments"] = {
            "count": len(segments),
            "union_schema": _build_union_schema(segments),
            "objects": _preserve_objects(segments, max_items=30),
        }

    return result


# ═══════════════════════════════════════════════════════════════════════
# Phase 5: Audiences & Segmentation — full filter structures
# ═══════════════════════════════════════════════════════════════════════

def _analyze_audiences(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Extract audience definitions with full filter and query structures."""
    aud_data = _safe_dict(raw, "audiences")
    if not aud_data:
        return {"available": False}

    result: Dict[str, Any] = {"available": True}

    audiences = _extract_items(aud_data.get("audiences"))
    if audiences:
        result["audiences"] = {
            "count": len(audiences),
            "union_schema": _build_union_schema(audiences),
            "value_patterns": _extract_field_value_patterns(audiences, ["type", "status"]),
            "examples": _preserve_objects(
                _stratified_sample(audiences, "type", max_per_type=3, max_total=10),
                max_items=10,
            ),
            "naming_patterns": _extract_naming_patterns(audiences),
        }

    target_groups = _extract_items(aud_data.get("target_groups"))
    if target_groups:
        result["target_groups"] = {
            "count": len(target_groups),
            "union_schema": _build_union_schema(target_groups),
            "examples": _preserve_objects(target_groups, max_items=10),
        }

    filters = aud_data.get("audience_filters")
    if isinstance(filters, dict) and "_error" not in filters:
        result["audience_filter_schema"] = filters
    elif isinstance(filters, list):
        result["audience_filters"] = _preserve_objects(filters, max_items=30)

    dim_attr = aud_data.get("dim_attr_availability")
    if isinstance(dim_attr, dict) and "_error" not in dim_attr:
        result["dimension_attributes"] = dim_attr
    elif isinstance(dim_attr, list):
        result["dimension_attributes"] = _preserve_objects(dim_attr, max_items=30)

    test_control = aud_data.get("customer_test_control")
    if isinstance(test_control, dict) and "_error" not in test_control:
        result["test_control_config"] = test_control

    events = _extract_items(aud_data.get("behavioral_events"))
    if events:
        result["behavioral_events"] = {
            "count": len(events),
            "union_schema": _build_union_schema(events),
            "objects": _preserve_objects(events, max_items=20),
        }

    return result


# ═══════════════════════════════════════════════════════════════════════
# Phase 6: Customizations — FULL field catalog (uncapped)
# ═══════════════════════════════════════════════════════════════════════

def _analyze_customizations(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Extract ALL extended fields, custom fields, labels — complete catalogs."""
    result: Dict[str, Any] = {"available": False}

    ef_data = _safe_dict(raw, "extended_fields")
    if ef_data:
        for ef_key, ef_label in [
            ("customer_extended_fields", "customer"),
            ("txn_extended_fields", "transaction"),
            ("line_item_extended_fields", "line_item"),
        ]:
            items = _extract_items(ef_data.get(ef_key))
            if items:
                result["available"] = True
                result[f"{ef_label}_extended_fields"] = {
                    "count": len(items),
                    "union_schema": _build_union_schema(items),
                    "objects": _preserve_objects(items, max_items=500),
                }

    loyalty_cf = _extract_items(_safe_dict(raw, "loyalty").get("custom_fields"))
    if loyalty_cf:
        result["available"] = True
        result["loyalty_custom_fields"] = {
            "count": len(loyalty_cf),
            "objects": _preserve_objects(loyalty_cf, max_items=100),
        }

    coupon_cp = _extract_items(_safe_dict(raw, "coupons").get("coupon_custom_property"))
    if coupon_cp:
        result["available"] = True
        result["coupon_custom_properties"] = {
            "count": len(coupon_cp),
            "objects": _preserve_objects(coupon_cp, max_items=50),
        }

    reward_cf = _extract_items(_safe_dict(raw, "coupons").get("reward_custom_fields"))
    if reward_cf:
        result["available"] = True
        result["reward_custom_fields"] = {
            "count": len(reward_cf),
            "objects": _preserve_objects(reward_cf, max_items=50),
        }

    org_data = _safe_dict(raw, "org_settings")
    labels = _extract_items(org_data.get("customer_labels"))
    if labels:
        result["available"] = True
        result["customer_labels"] = {
            "count": len(labels),
            "union_schema": _build_union_schema(labels),
            "objects": _preserve_objects(labels, max_items=50),
        }

    events = _extract_items(org_data.get("behavioral_events"))
    if events:
        result["available"] = True
        result["behavioral_events"] = {
            "count": len(events),
            "union_schema": _build_union_schema(events),
            "objects": _preserve_objects(events, max_items=30),
        }

    org_hierarchy = org_data.get("organization_hierarchy")
    if isinstance(org_hierarchy, dict) and "_error" not in org_hierarchy:
        result["available"] = True
        result["organization_hierarchy"] = _cap_object(org_hierarchy)
    elif isinstance(org_hierarchy, list):
        result["available"] = True
        result["organization_hierarchy"] = _preserve_objects(org_hierarchy, max_items=20)

    return result


# ═══════════════════════════════════════════════════════════════════════
# Phase 7: Channel config — domain properties, template schemas
# ═══════════════════════════════════════════════════════════════════════

def _analyze_channels(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Extract per-channel domain properties and template configs."""
    result: Dict[str, Any] = {"available": False}
    channels: Dict[str, Dict[str, Any]] = {}

    org_data = _safe_dict(raw, "org_settings")
    for key, val in org_data.items():
        if key.startswith("domain_properties_") and isinstance(val, dict) and "_error" not in val:
            channel = key.replace("domain_properties_", "").upper()
            result["available"] = True
            props = _extract_items(val) if not isinstance(val, list) else val
            if isinstance(val, dict) and not props:
                channels[channel] = {"domain_properties": val}
            else:
                channels[channel] = {
                    "domain_properties_count": len(props) if isinstance(props, list) else 0,
                    "domain_properties": _preserve_objects(props, max_items=50) if isinstance(props, list) else val,
                }

    camp_data = _safe_dict(raw, "campaigns")

    sms_templates = _extract_items(camp_data.get("sms_templates"))
    if sms_templates:
        result["available"] = True
        channels.setdefault("SMS", {})["templates"] = {
            "count": len(sms_templates),
            "examples": _preserve_objects(sms_templates, max_items=8),
        }

    email_templates = _extract_items(camp_data.get("email_templates"))
    if email_templates:
        result["available"] = True
        channels.setdefault("EMAIL", {})["templates"] = {
            "count": len(email_templates),
            "examples": _preserve_objects(email_templates, max_items=5),
        }

    wa_accounts = _extract_items(camp_data.get("whatsapp_accounts"))
    if wa_accounts:
        result["available"] = True
        channels.setdefault("WHATSAPP", {})["accounts"] = {
            "count": len(wa_accounts),
            "objects": _preserve_objects(wa_accounts, max_items=5),
        }

    push_accounts = _extract_items(camp_data.get("push_notification_accounts"))
    if push_accounts:
        result["available"] = True
        channels.setdefault("MOBILEPUSH", {})["accounts"] = {
            "count": len(push_accounts),
            "objects": _preserve_objects(push_accounts, max_items=5),
        }

    result["channels"] = channels
    return result


# ═══════════════════════════════════════════════════════════════════════
# Phase 8: Relationships — full cross-entity map
# ═══════════════════════════════════════════════════════════════════════

def _analyze_relationships(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Map cross-references between config objects with full entity data."""
    relationships: List[Dict[str, Any]] = []

    camp_data = _safe_dict(raw, "campaigns")
    details = camp_data.get("campaign_details", [])
    if isinstance(details, list):
        for d in details:
            if not isinstance(d, dict):
                continue
            detail = d.get("detail", {})
            if not isinstance(detail, dict):
                continue
            camp_id = d.get("campaign_id")
            camp_name = detail.get("name") or detail.get("campaignName") or str(camp_id)

            coupon_id = detail.get("couponSeriesId") or detail.get("voucherSeriesId")
            if coupon_id:
                relationships.append({
                    "from_type": "campaign", "from_id": camp_id, "from_name": camp_name,
                    "to_type": "coupon_series", "to_id": coupon_id,
                    "relation": "uses_coupon",
                })
            program_id = detail.get("programId") or detail.get("loyaltyProgramId")
            if program_id:
                relationships.append({
                    "from_type": "campaign", "from_id": camp_id, "from_name": camp_name,
                    "to_type": "loyalty_program", "to_id": program_id,
                    "relation": "linked_to_program",
                })

    coupon_data = _safe_dict(raw, "coupons")
    coupon_series = _extract_items(coupon_data.get("coupon_series"))
    product_categories = _extract_items(coupon_data.get("product_categories"))
    product_brands = _extract_items(coupon_data.get("product_brands"))
    product_attributes = _extract_items(coupon_data.get("product_attributes"))

    org_data = _safe_dict(raw, "org_settings")
    target_groups = _extract_items(org_data.get("target_groups"))

    result: Dict[str, Any] = {}

    if relationships:
        result["cross_references"] = relationships[:200]

    if coupon_series:
        result["coupon_series"] = {
            "count": len(coupon_series),
            "union_schema": _build_union_schema(coupon_series),
            "examples": _preserve_objects(
                _stratified_sample(coupon_series, "discountType", max_per_type=3, max_total=10),
                max_items=10,
            ),
            "naming_patterns": _extract_naming_patterns(coupon_series, "seriesName"),
        }

    if product_categories:
        result["product_categories"] = _preserve_objects(product_categories, max_items=30)
    if product_brands:
        result["product_brands"] = _preserve_objects(product_brands, max_items=30)
    if product_attributes:
        result["product_attributes"] = _preserve_objects(product_attributes, max_items=30)

    coupon_org_settings_val = coupon_data.get("coupon_org_settings")
    if isinstance(coupon_org_settings_val, dict) and "_error" not in coupon_org_settings_val:
        result["coupon_org_settings"] = coupon_org_settings_val

    if target_groups:
        result["target_groups"] = _preserve_objects(target_groups, max_items=15)

    # Only mark available if we have any actual entity data
    has_data = any(k for k in result if k != "available")
    result["available"] = has_data
    return result
