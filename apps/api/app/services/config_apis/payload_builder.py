"""
Payload builder for Config APIs doc generation.

Takes analysis data (with union schemas, full objects, patterns) and builds
structured LLM payloads — one per doc type.

Each payload provides the LLM with:
- org_profile: inferred patterns about how this org uses configs
- entity_catalog: config-relevant fields from real config objects (pruned)
- field_reference: union schemas with valid values and presence %
- config_standards: auto-inferred rules from org patterns

Enhanced with:
- build_payloads_from_clusters(): uses top-5 templates from clusters
- strip_stats(): removes n/pct/count fields before sending to LLM
- _prune_template(): strips operational noise, keeps config signal
- _enforce_token_budget(): progressive payload reduction to fit budget
- inclusions support: toggle individual items on/off

Noise field analysis derived from CSV exports of API data.
"""

from __future__ import annotations

import copy
import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════
# Stats keys to strip before sending payloads to LLM
# ═══════════════════════════════════════════════════════════════════════

_STAT_KEYS = frozenset({"n", "pct", "count", "unique", "presence_pct"})


# ═══════════════════════════════════════════════════════════════════════
# Noise field registries — strip operational data, keep config signal
#
# Derived from analysis of Capillary API CSV exports:
#   audiences.csv:      18 cols → 5 signal (72% noise)
#   audience_filters:   57 cols → 25 signal (56% noise)
#   target_groups.csv:  945 cols → 16 signal (98% noise!)
#   coupon_series.csv:  260 cols → 30 signal (88% noise)
#   campaigns.csv:      15 cols → 10 signal (33% noise)
#   emf_promotions.csv: 34 cols → 25 signal (26% noise)
#   cart_promotions.csv:31 cols → 12 signal (61% noise)
# ═══════════════════════════════════════════════════════════════════════

# Layer 1: exact field names stripped from ALL entity types
_GLOBAL_NOISE_FIELDS: frozenset = frozenset({
    # ── Audit / attribution ──
    "auditInfo", "attribution", "createdBy", "modifiedBy", "lastUpdatedBy",
    "createdOn", "modifiedOn", "lastUpdatedOn", "createdAt", "updatedAt",
    "addedBy", "addedOn", "createdDate", "modifiedDate", "lastModified",
    "__v", "updatedBy",

    # ── Version / sync ──
    "versionId", "versionNumber", "version",

    # ── Runtime counters (snapshot metrics, NOT config shape) ──
    "customerCount", "testCount", "controlCount", "memberCount",
    "totalUploadCount", "totalUploadedCount", "errorCount", "totalErrorCount",
    "totalRowCount", "numTotal", "numIssued", "numRedeemed", "numUploadedTotal",
    "totalIssuedCount", "totalRedeemed", "totalDiscount", "totalTransactions",
    "totalDiscountAppliedQuantity", "totalPromotionAppliedQuantity",
    "totalEarned", "totalMessagesCount",
    "targetedCustomerCount", "sentCount", "failedCount",
    "lastTriggeredCount", "totalTriggeredCount",
    "redemptionCount", "issuedCount",

    # ── Upload / storage / S3 ──
    "uploadStatus", "couponUploadStatus", "couponUploadInfo",
    "fileUrl", "fileName", "filePath", "s3Path", "s3Url", "s3Key",
    "errorFileUrl", "successFileUrl",
    "isUploadError",

    # ── Reachability (channel runtime stats — single biggest offender) ──
    "reachabilityStats", "reachabilityStatus",

    # ── Operational timestamps (not config date ranges) ──
    "lastRunTime", "lastSyncTime", "lastRefreshTime",
    "nextRunTime", "lastTriggeredTime",
    "latestIssualTime", "latestRedemptionTime",
    "lastUsed", "last_used", "lastRedeemed", "lastEarned",
    "lastRedeemedISO", "lastEarnedISO",

    # ── Internal IDs / org references ──
    "orgId", "orgUnitId", "orgID",

    # ── UI / rendering metadata ──
    "renderOrder", "isFavourite", "supportLink", "updatedViaNewUI",
})

# Layer 2: subtree prefixes — strip any key starting with these
_NOISE_PREFIXES: tuple = (
    "oldCouponConfig",              # 145+ legacy coupon config columns
    "targetPeriodDefaultValuesMap",  # 900+ period-specific operational defaults
    "lastActivated",                 # buffer/offset serialization artifacts
    "lastReconfiguredTime",
    "lastReconfguredByUserId",       # typo in Capillary API — must match
)

# Layer 3: per-entity-type additional noise
_ENTITY_NOISE_FIELDS: Dict[str, frozenset] = {
    "audience": frozenset({
        "reloadType", "uploadHistory", "downloadUrl",
        "segmentMigrationDetails", "bucketId",
    }),
    "campaign": frozenset({
        "attributionId", "campaignId", "campaignsAttached",
    }),
    "campaign_config": frozenset({
        "deliveryStats", "lastRunDetails",
    }),
    "coupon_series": frozenset({
        "created_by", "created",
        "dvs_expiry_date", "claimedBy", "ownerValidity",
        "syncWithInstoreClient",
        "tempAlphaNumeric", "tempRandomCodeLength",
        "orgPrefixOverride", "orgSuffixOverride",
        "notifyCouponDeficiencyLimit",
        "sendNotificationForIssualLimit",
        "addGenericCodeRandomSuffix",
        "resendMessageEnabled", "resendCoupon",
        "setCouponReminder", "audienceGroupsToBeAttached",
        "clientHandlingType", "refId", "campaignId",
        "context", "metadata", "seriesType",
    }),
    "target_group": frozenset({
        "emfRuleSetId", "emfUnrolledRulesetId", "targetGroupId",
    }),
    "loyalty_promotion": frozenset({
        "startRuleIdentifier", "identifier",
        "lastUpdateDate", "lastUpdatedBy", "programId",
    }),
    "cart_promotion": frozenset({
        "promotionId",
    }),
    "audience_filter": frozenset({
        "_id", "renderOrder", "isFavourite", "__v",
        "supportLink", "createdBy", "updatedBy",
    }),
}

# Layer 4: asset URL keywords — strip from customPropertyMap-like dicts
_ASSET_URL_KEYWORDS: tuple = (
    "image", "Image", "thumbnail", "Thumbnail",
    "Url", "url", "URL",
)
# Keys in customPropertyMap to ALWAYS keep (config-relevant metadata)
_CUSTOM_PROP_KEEP: frozenset = frozenset({
    "offerName", "filter_type", "standard_description",
    "standard_terms_and_conditions", "purpose", "milestone",
    "trackerId", "Transaction", "rank",
    "short_name", "long_name",
})


# ═══════════════════════════════════════════════════════════════════════
# Template pruning — strip noise, keep config signal
# ═══════════════════════════════════════════════════════════════════════

def _is_asset_url_key(key: str) -> bool:
    """Check if a customPropertyMap key is an asset/image URL (noise)."""
    return any(kw in key for kw in _ASSET_URL_KEYWORDS)


# API response envelope keys — stripped when unwrapping response wrappers
_RESPONSE_ENVELOPE_KEYS: frozenset = frozenset({
    "status", "success", "message", "pagination",
    "code", "isError",
})

# Max entries in a dict before truncation (parallel to list truncation)
_MAX_DICT_ENTRIES = 30


# Keys that indicate a response payload (checked in order of priority)
_RESPONSE_PAYLOAD_KEYS: tuple = ("response", "result", "data")


def _unwrap_response_envelope(obj: dict) -> Any:
    """Unwrap API response envelope → extract actual config data.

    Many entity types store entire API responses as templates:
        Pattern A: {status: {...}, message: "success", response: {...}}
        Pattern B: {status: {...}, success: true, result: [...]}
        Pattern C: {data: [...], errors: [...]}
    This extracts the payload content, discarding the wrapper.
    """
    if not isinstance(obj, dict):
        return obj

    # Find the payload key (response > result > data)
    payload_key = None
    for pk in _RESPONSE_PAYLOAD_KEYS:
        if pk in obj:
            payload_key = pk
            break

    if not payload_key:
        return obj

    # Check that remaining keys are envelope metadata (not real config fields)
    other_keys = {k for k in obj if k != payload_key}
    is_envelope = all(
        k in _RESPONSE_ENVELOPE_KEYS or k == "errors" or k == "warnings"
        for k in other_keys
    )

    if not is_envelope:
        return obj

    payload = obj[payload_key]

    # If payload is a dict with a few keys, unwrap further
    # e.g., {targets: [...], pagination: {...}, evaluationPeriod: {}}
    if isinstance(payload, dict) and len(payload) <= 6:
        unwrapped = {}
        for k, v in payload.items():
            if k in _RESPONSE_ENVELOPE_KEYS:
                continue
            # Recurse one more level: {data: {data: [...]}} → [...]
            if k in _RESPONSE_PAYLOAD_KEYS and isinstance(v, (list, dict)):
                return v  # Direct extraction
            unwrapped[k] = v
        return unwrapped if unwrapped else payload

    return payload


def _prune_template(
    obj: Any,
    entity_type: str = "",
    depth: int = 0,
    max_array_items: int = 3,
    _in_custom_prop: bool = False,
) -> Any:
    """Strip operational noise from a template object for LLM payload.

    Keeps config-relevant fields (identity, rules, restrictions, filters,
    expressions, conditions) and removes runtime/audit/operational noise.

    Handles:
    - API response envelope unwrapping ({status, response} → response content)
    - Global/entity-specific noise field removal
    - Noise prefix subtree removal (oldCouponConfig*, targetPeriodDefaultValuesMap*)
    - customPropertyMap/customFieldValues asset URL filtering
    - Array truncation (cap at max_array_items)
    - Dict truncation (cap at _MAX_DICT_ENTRIES for large dicts)
    - String capping at 500 chars

    Args:
        obj: The object to prune (dict, list, or primitive).
        entity_type: Entity type for per-entity noise lookup.
        depth: Current recursion depth (max 12).
        max_array_items: Max items to keep in arrays.
        _in_custom_prop: Internal flag for customPropertyMap context.
    """
    if depth > 12:
        return "<nested>" if isinstance(obj, (dict, list)) else obj

    # Unwrap API response envelopes at the top level
    if depth == 0 and isinstance(obj, dict):
        obj = _unwrap_response_envelope(obj)

    # Combine noise sets for this entity type
    noise = _GLOBAL_NOISE_FIELDS
    if entity_type:
        noise = noise | _ENTITY_NOISE_FIELDS.get(entity_type, frozenset())

    if isinstance(obj, dict):
        pruned = {}
        items = list(obj.items())
        for k, v in items:
            # Skip internal keys
            if k.startswith("_") and k != "_id":
                continue
            # Skip global noise
            if k in noise:
                continue
            # Skip noise prefix subtrees
            if any(k.startswith(pfx) for pfx in _NOISE_PREFIXES):
                continue

            # customPropertyMap / customFieldValues: keep config-relevant, skip asset URLs
            is_custom = _in_custom_prop or k in ("customPropertyMap", "customFieldValues")
            if is_custom and k not in ("customPropertyMap", "customFieldValues"):
                if k in _CUSTOM_PROP_KEEP:
                    pruned[k] = _prune_template(
                        v, entity_type, depth + 1, max_array_items, True,
                    )
                elif not _is_asset_url_key(k):
                    pruned[k] = _prune_template(
                        v, entity_type, depth + 1, max_array_items, True,
                    )
                continue

            pruned[k] = _prune_template(
                v, entity_type, depth + 1, max_array_items,
                _in_custom_prop=is_custom,
            )

        # Dict truncation: cap large dicts (e.g., targetGroups with 1577 entries)
        if len(pruned) > _MAX_DICT_ENTRIES:
            kept_keys = list(pruned.keys())[:_MAX_DICT_ENTRIES]
            truncated = {k: pruned[k] for k in kept_keys}
            truncated["_truncated"] = f"... (+{len(pruned) - _MAX_DICT_ENTRIES} more entries)"
            return truncated

        return pruned

    if isinstance(obj, list):
        if not obj:
            return obj
        if len(obj) > max_array_items:
            truncated = [
                _prune_template(item, entity_type, depth + 1, max_array_items)
                for item in obj[:max_array_items]
            ]
            truncated.append(f"... (+{len(obj) - max_array_items} more)")
            return truncated
        return [
            _prune_template(item, entity_type, depth + 1, max_array_items)
            for item in obj
        ]

    if isinstance(obj, str) and len(obj) > 500:
        return obj[:500] + "..."

    return obj


def _summarize_raw_dict(
    obj: Any,
    max_depth: int = 3,
    current_depth: int = 0,
) -> Any:
    """Summarize a raw dict/list entity for LLM payload.

    For raw API responses stored as-is (audience_filter_schema,
    dimension_attributes, test_control_config), produce a structural
    summary instead of dumping the full response.
    """
    if current_depth >= max_depth:
        if isinstance(obj, dict):
            keys = list(obj.keys())[:10]
            return f"<object with {len(obj)} keys: {keys}>"
        if isinstance(obj, list):
            return f"<array of {len(obj)} items>"
        return obj

    if isinstance(obj, dict):
        summarized = {}
        for k, v in list(obj.items())[:30]:
            summarized[k] = _summarize_raw_dict(v, max_depth, current_depth + 1)
        if len(obj) > 30:
            summarized["_truncated"] = f"{len(obj) - 30} more keys omitted"
        return summarized

    if isinstance(obj, list):
        if not obj:
            return []
        if len(obj) <= 3:
            return [
                _summarize_raw_dict(item, max_depth, current_depth + 1)
                for item in obj
            ]
        summary = [
            _summarize_raw_dict(item, max_depth, current_depth + 1)
            for item in obj[:2]
        ]
        summary.append(f"... (+{len(obj) - 2} more items)")
        return summary

    if isinstance(obj, str) and len(obj) > 200:
        return obj[:200] + "..."

    return obj


# ═══════════════════════════════════════════════════════════════════════
# Token budget enforcement — progressive payload reduction
# ═══════════════════════════════════════════════════════════════════════

def _est_tokens(payload: Dict[str, Any]) -> int:
    """Estimate token count from payload dict."""
    return len(json.dumps(payload, default=str)) // 4


def _enforce_token_budget(
    payload: Dict[str, Any],
    doc_key: str,
    budget_tokens: int,
) -> Dict[str, Any]:
    """Progressively reduce payload to fit within token budget.

    Reduction stages (ordered by increasing information loss):
    1. Remove cluster_summary (metadata, not essential for LLM)
    2. Remove config_standards (LLM can infer from templates)
    3. Reduce templates per entity type: 5 → 3 → 2 → 1
    4. Trim field_reference (drop sample_values, nested_keys)
    5. Aggressive re-prune with max_array_items=1
    """
    current = _est_tokens(payload)
    if current <= budget_tokens:
        return payload

    # Deep copy to avoid mutating the original
    p = copy.deepcopy(payload)

    # Stage 1: drop cluster_summary
    if "cluster_summary" in p and _est_tokens(p) > budget_tokens:
        del p["cluster_summary"]
        logger.debug(
            "Budget enforcement [%s]: dropped cluster_summary (%d → %d tokens)",
            doc_key, current, _est_tokens(p),
        )

    # Stage 2: drop config_standards
    if "config_standards" in p and _est_tokens(p) > budget_tokens:
        del p["config_standards"]
        logger.debug("Budget enforcement [%s]: dropped config_standards", doc_key)

    # Stage 3: reduce templates progressively
    entity_catalog = p.get("entity_catalog", {})
    for max_t in (3, 2, 1):
        if _est_tokens(p) <= budget_tokens:
            break
        for ek, ev in entity_catalog.items():
            if isinstance(ev, dict) and "templates" in ev:
                templates = ev["templates"]
                if len(templates) > max_t:
                    ev["templates"] = templates[:max_t]
        logger.debug(
            "Budget enforcement [%s]: reduced templates to max %d/type",
            doc_key, max_t,
        )

    # Stage 4: trim field_reference (drop sample_values, nested_keys)
    if _est_tokens(p) > budget_tokens and "field_reference" in p:
        for _fk, fv in p["field_reference"].items():
            if isinstance(fv, dict):
                for _field_name, field_info in fv.items():
                    if isinstance(field_info, dict):
                        field_info.pop("sample_values", None)
                        field_info.pop("nested_keys", None)
        logger.debug("Budget enforcement [%s]: trimmed field_reference", doc_key)

    # Stage 5: aggressive re-prune remaining templates
    if _est_tokens(p) > budget_tokens:
        for ek, ev in entity_catalog.items():
            if isinstance(ev, dict) and "templates" in ev:
                et = ek.split(":")[0]
                ev["templates"] = [
                    _prune_template(t, entity_type=et, max_array_items=1)
                    for t in ev["templates"][:1]
                ]
        logger.debug("Budget enforcement [%s]: aggressive re-prune", doc_key)

    final = _est_tokens(p)
    if final > budget_tokens:
        logger.warning(
            "Budget enforcement [%s]: still over budget after all stages "
            "(%d tokens vs %d budget)",
            doc_key, final, budget_tokens,
        )
    else:
        logger.info(
            "Budget enforcement [%s]: reduced %d → %d tokens (budget %d)",
            doc_key, current, final, budget_tokens,
        )

    return p


def strip_stats(obj: Any) -> Any:
    """Recursively strip count/pct/n fields from payload.

    Removes keys in _STAT_KEYS from all dicts. This reduces token usage
    when sending payloads to LLM (stats are for UI display only).
    """
    if isinstance(obj, dict):
        return {
            k: strip_stats(v)
            for k, v in obj.items()
            if k not in _STAT_KEYS
        }
    if isinstance(obj, list):
        return [strip_stats(item) for item in obj]
    return obj

# ═══════════════════════════════════════════════════════════════════════
# Doc types — each maps to analysis sections and entity keys it needs
# ═══════════════════════════════════════════════════════════════════════

DOC_TYPES = {
    "01_LOYALTY_MASTER": {
        "name": "Loyalty Programs Reference",
        "focus": "Programs, tiers, earning/expiry strategies, currencies, partner "
                 "programs, events — with real configs this org uses",
        "sections": ["inventory", "loyalty_structure"],
    },
    "02_CAMPAIGN_REFERENCE": {
        "name": "Campaign & Messaging Reference",
        "focus": "Campaigns by type, message templates per channel, scheduling "
                 "patterns, channel configs — real examples from this org",
        "sections": ["inventory", "campaign_patterns", "channel_config"],
    },
    "03_PROMOTION_RULES": {
        "name": "Promotion & Rewards Reference",
        "focus": "Loyalty/cart promotions with full workflow structures, coupon "
                 "series with discount rules, product catalog, reward groups "
                 "— real promotion configs from this org",
        "sections": ["inventory", "promotion_rules", "relationships"],
    },
    "04_AUDIENCE_SEGMENTS": {
        "name": "Audiences & Segmentation Reference",
        "focus": "Audience definitions, filter structures, target groups, "
                 "behavioral events, test/control configs — real examples",
        "sections": ["inventory", "audience_segmentation"],
    },
    "05_CUSTOMIZATIONS": {
        "name": "Fields, Labels & Org Settings Reference",
        "focus": "Complete catalog of ALL extended fields (customer/txn/lineitem), "
                 "custom fields, labels, behavioral events, org hierarchy, "
                 "channel domain properties",
        "sections": ["inventory", "customizations", "channel_config"],
    },
}


def build_payloads(analysis_data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Build LLM payloads for each doc type from analysis data.

    Returns:
        {doc_key: {"doc_name": str, "focus": str, "payload": str}}
    """
    payloads: Dict[str, Dict[str, Any]] = {}

    for doc_key, doc_meta in DOC_TYPES.items():
        sections: Dict[str, Any] = {}
        has_non_inventory = False
        for section_key in doc_meta["sections"]:
            if section_key in analysis_data:
                section_data = analysis_data[section_key]
                if isinstance(section_data, dict) and section_data.get("available", True):
                    # Ensure section has real entity data, not just "available" key
                    entity_keys = [k for k in section_data if k != "available"]
                    if entity_keys:
                        sections[section_key] = section_data
                        if section_key != "inventory":
                            has_non_inventory = True

        # Inventory alone is not enough — need at least one content section
        if not sections or not has_non_inventory:
            continue

        payload_text = _build_structured_payload(doc_key, doc_meta, sections)
        payloads[doc_key] = {
            "doc_name": doc_meta["name"],
            "focus": doc_meta["focus"],
            "payload": payload_text,
        }

    return payloads


# ═══════════════════════════════════════════════════════════════════════
# Structured payload construction
# ═══════════════════════════════════════════════════════════════════════

_MAX_PAYLOAD_CHARS = 200_000  # raised from 150K — real data needs space


def _build_structured_payload(
    doc_key: str,
    doc_meta: Dict[str, Any],
    sections: Dict[str, Any],
) -> str:
    """Build a structured payload with org profile, entity catalog, and patterns."""
    payload: Dict[str, Any] = {
        "doc": doc_meta["name"],
        "focus": doc_meta["focus"],
    }

    # Build org profile from patterns found across sections
    org_profile = _extract_org_profile(sections)
    if org_profile:
        payload["org_profile"] = org_profile

    # Build entity catalog and field reference from sections
    entity_catalog: Dict[str, Any] = {}
    field_reference: Dict[str, Any] = {}
    config_standards: List[str] = []

    for section_key, section_data in sections.items():
        if section_key == "inventory":
            # Only include categories with actual objects (skip zero-count)
            filtered_inv = {}
            for k, v in section_data.items():
                if k == "available":
                    continue
                if isinstance(v, dict) and v.get("total_objects", 0) > 0:
                    filtered_inv[k] = v
            if filtered_inv:
                payload["inventory"] = filtered_inv
            continue

        for entity_key, entity_data in section_data.items():
            if entity_key == "available":
                continue

            if isinstance(entity_data, dict):
                # Check for standard analysis structure (objects/examples)
                objects = (
                    entity_data.get("objects")
                    or entity_data.get("examples")
                )
                if objects:
                    # Prune each object: strip noise, keep config signal
                    if isinstance(objects, list):
                        entity_catalog[entity_key] = [
                            _prune_template(o, entity_type=entity_key)
                            if isinstance(o, dict) else o
                            for o in objects
                        ]
                    else:
                        entity_catalog[entity_key] = objects
                elif not entity_data.get("union_schema") and not entity_data.get("naming_patterns"):
                    # Raw dict entity (no standard analysis wrapper) —
                    # e.g., audience_filter_schema, dimension_attributes,
                    # test_control_config. Summarize instead of dumping.
                    entity_catalog[entity_key] = _summarize_raw_dict(entity_data)

                # Extract union schemas into field_reference
                schema = entity_data.get("union_schema")
                if schema:
                    field_reference[entity_key] = schema

                # Extract naming patterns as config standards
                naming = entity_data.get("naming_patterns")
                if naming:
                    for pattern in naming:
                        config_standards.append(f"{entity_key}: {pattern}")

                # Extract value patterns as config standards
                vp = entity_data.get("value_patterns")
                if isinstance(vp, dict):
                    for field_name, field_data in vp.items():
                        top_values = field_data.get("top_values", [])
                        if top_values:
                            dominant = top_values[0]
                            if dominant.get("pct", 0) >= 70:
                                config_standards.append(
                                    f"{entity_key}.{field_name}: dominant value "
                                    f"'{dominant['value']}' ({dominant['pct']}% of configs)"
                                )
                            else:
                                vals = [v["value"] for v in top_values[:5]]
                                config_standards.append(
                                    f"{entity_key}.{field_name}: observed values = {vals}"
                                )
            elif isinstance(entity_data, list):
                if entity_data:
                    # Prune list items
                    entity_catalog[entity_key] = [
                        _prune_template(o, entity_type=entity_key)
                        if isinstance(o, dict) else o
                        for o in entity_data
                    ]
            else:
                entity_catalog[entity_key] = entity_data

    if entity_catalog:
        payload["entity_catalog"] = entity_catalog
    if field_reference:
        payload["field_reference"] = field_reference
    if config_standards:
        payload["config_standards"] = config_standards

    # Enforce token budget — progressively reduce if over
    from app.services.config_apis.doc_author import TOKEN_BUDGETS
    budget = TOKEN_BUDGETS.get(doc_key, 12000)
    payload = _enforce_token_budget(payload, doc_key, budget)

    # Compact JSON for LLM consumption — saves ~45% tokens vs indent=2
    text = json.dumps(payload, separators=(", ", ": "), default=str)

    if len(text) > _MAX_PAYLOAD_CHARS:
        text = json.dumps(payload, separators=(",", ":"), default=str)
        if len(text) > _MAX_PAYLOAD_CHARS:
            text = text[:_MAX_PAYLOAD_CHARS] + "\n... (TRUNCATED — payload exceeded size limit)"

    return text


def _extract_org_profile(sections: Dict[str, Any]) -> Dict[str, Any]:
    """Infer org-level patterns from analysis sections."""
    profile: Dict[str, Any] = {}

    inventory = sections.get("inventory", {})
    for cat_id, cat_data in inventory.items():
        if cat_id == "available" or not isinstance(cat_data, dict):
            continue
        total = cat_data.get("total_objects", 0)
        if total > 0:
            profile.setdefault("entity_counts", {})[cat_id] = total

    all_patterns: List[str] = []
    for section_data in sections.values():
        if not isinstance(section_data, dict):
            continue
        for entity_key, entity_data in section_data.items():
            if isinstance(entity_data, dict):
                naming = entity_data.get("naming_patterns")
                if naming:
                    all_patterns.extend(naming)
    if all_patterns:
        profile["naming_conventions"] = all_patterns

    for section_data in sections.values():
        if not isinstance(section_data, dict):
            continue
        td = section_data.get("type_distribution")
        if td:
            profile["campaign_type_distribution"] = td
        cd = section_data.get("channel_distribution")
        if cd:
            profile["channel_distribution"] = cd

    return profile


# ═══════════════════════════════════════════════════════════════════════
# Doc type → entity types mapping (for cluster-based payloads)
# ═══════════════════════════════════════════════════════════════════════

DOC_ENTITY_TYPES: Dict[str, List[str]] = {
    "01_LOYALTY_MASTER": [
        "program", "tier", "strategy", "alternate_currency",
        "partner_program", "event_type", "loyalty_custom_field",
    ],
    "02_CAMPAIGN_REFERENCE": [
        "campaign", "campaign_config", "message",
        "sms_template", "email_template",
    ],
    "03_PROMOTION_RULES": [
        "loyalty_promotion", "cart_promotion", "coupon_series",
        "rewards_group", "promotion_custom_field",
    ],
    "04_AUDIENCE_SEGMENTS": [
        "audience", "target_group", "behavioral_event", "audience_filter",
    ],
    "05_CUSTOMIZATIONS": [
        "customer_ef", "txn_ef", "line_item_ef",
        "customer_label", "org_hierarchy_node", "org_behavioral_event",
    ],
}


# ═══════════════════════════════════════════════════════════════════════
# Cluster-based payload builder (new — top 5 templates per type)
# ═══════════════════════════════════════════════════════════════════════

def build_payloads_from_clusters(
    analysis_data: Dict[str, Any],
    inclusions: Optional[Dict[str, Dict[str, bool]]] = None,
    include_stats: bool = True,
) -> Dict[str, Dict[str, Any]]:
    """Build LLM payloads from fingerprint clusters (top-5 templates).

    Falls back to legacy build_payloads() if no clusters exist.

    Args:
        analysis_data: Full analysis data with clusters, counters, etc.
        inclusions: {doc_key: {entity_type: bool, entity_type.template_id: bool}}
                    Omitted keys default to True (included).
        include_stats: If False, strip n/pct/count from output.

    Returns:
        {doc_key: {"doc_name": str, "focus": str, "payload": str,
                    "chars": int, "est_tokens": int}}
    """
    clusters = analysis_data.get("clusters")
    if not clusters:
        # Fallback to legacy behavior
        legacy = build_payloads(analysis_data)
        for doc_key, data in legacy.items():
            payload_str = data.get("payload", "")
            data["chars"] = len(payload_str)
            data["est_tokens"] = len(payload_str) // 4
        return legacy

    counters = analysis_data.get("counters", {})
    entity_type_counts = analysis_data.get("entity_type_counts", {})

    payloads: Dict[str, Dict[str, Any]] = {}

    for doc_key, doc_meta in DOC_TYPES.items():
        entity_types = DOC_ENTITY_TYPES.get(doc_key, [])
        doc_inclusions = (inclusions or {}).get(doc_key, {})

        # Filter clusters relevant to this doc type
        relevant_clusters = [
            c for c in clusters
            if c["entity_type"] in entity_types
        ]

        if not relevant_clusters:
            continue

        # Apply inclusions — filter out excluded entity types and templates
        filtered_clusters = _apply_inclusions(relevant_clusters, doc_inclusions)

        if not filtered_clusters:
            continue

        # Build payload structure
        payload_obj = _build_cluster_payload(
            doc_key=doc_key,
            doc_meta=doc_meta,
            clusters=filtered_clusters,
            entity_type_counts=entity_type_counts,
            counters=counters,
        )

        if not include_stats:
            payload_obj = strip_stats(payload_obj)

        # Enforce token budget — progressively reduce if over
        from app.services.config_apis.doc_author import TOKEN_BUDGETS
        budget = TOKEN_BUDGETS.get(doc_key, 12000)
        payload_obj = _enforce_token_budget(payload_obj, doc_key, budget)

        # Compact JSON for LLM consumption — saves ~45% tokens vs indent=2.
        # The LLM doesn't need pretty printing; indentation is pure waste.
        payload_str = json.dumps(payload_obj, separators=(", ", ": "), default=str)

        if len(payload_str) > _MAX_PAYLOAD_CHARS:
            payload_str = json.dumps(payload_obj, separators=(",", ":"), default=str)
            if len(payload_str) > _MAX_PAYLOAD_CHARS:
                payload_str = (
                    payload_str[:_MAX_PAYLOAD_CHARS]
                    + "\n... (TRUNCATED)"
                )

        payloads[doc_key] = {
            "doc_name": doc_meta["name"],
            "focus": doc_meta["focus"],
            "payload": payload_str,
            "chars": len(payload_str),
            "est_tokens": len(payload_str) // 4,
        }

    return payloads


def _apply_inclusions(
    clusters: List[Dict[str, Any]],
    doc_inclusions: Dict[str, bool],
) -> List[Dict[str, Any]]:
    """Apply inclusion toggles to clusters and their templates.

    Inclusion paths:
    - "entity_type" → toggle entire entity type (e.g., "campaign": False)
    - "entity_type.template_id" → toggle specific template

    Omitted keys default to True (included).
    """
    if not doc_inclusions:
        return clusters

    filtered = []
    for cluster in clusters:
        entity_type = cluster["entity_type"]
        et_key = entity_type
        if cluster.get("entity_subtype"):
            et_key = f"{entity_type}:{cluster['entity_subtype']}"

        # Check entity-level inclusion
        if not doc_inclusions.get(et_key, doc_inclusions.get(entity_type, True)):
            continue

        # Check template-level inclusions
        template_ids = cluster.get("template_ids", [])
        templates = cluster.get("templates", [])
        filtered_template_ids = []
        filtered_templates = []

        for tid, tmpl in zip(template_ids, templates):
            tmpl_key = f"{et_key}.{tid}"
            if doc_inclusions.get(tmpl_key, True):
                filtered_template_ids.append(tid)
                filtered_templates.append(tmpl)

        if not filtered_templates:
            continue

        new_cluster = {**cluster}
        new_cluster["template_ids"] = filtered_template_ids
        new_cluster["templates"] = filtered_templates
        filtered.append(new_cluster)

    return filtered


def _build_cluster_payload(
    doc_key: str,
    doc_meta: Dict[str, Any],
    clusters: List[Dict[str, Any]],
    entity_type_counts: Dict[str, int],
    counters: Dict[str, Any],
) -> Dict[str, Any]:
    """Build a structured payload from filtered clusters."""
    payload: Dict[str, Any] = {
        "doc": doc_meta["name"],
        "focus": doc_meta["focus"],
    }

    # Org profile: entity counts for this doc's types
    entity_types = DOC_ENTITY_TYPES.get(doc_key, [])
    entity_counts = {
        et: entity_type_counts.get(et, 0)
        for et in entity_types
        if entity_type_counts.get(et, 0) > 0
    }
    if entity_counts:
        payload["org_profile"] = {
            "entity_counts": entity_counts,
            "total_configs": sum(entity_counts.values()),
        }

    # Entity catalog: templates from clusters (top 5 per type) — PRUNED
    entity_catalog: Dict[str, Any] = {}
    for cluster in clusters:
        et = cluster["entity_type"]
        subtype = cluster.get("entity_subtype", "")
        key = f"{et}:{subtype}" if subtype else et

        # Prune templates: strip operational noise, keep config signal
        pruned_templates = [
            _prune_template(tmpl, entity_type=et)
            for tmpl in cluster["templates"]
        ]

        entity_catalog[key] = {
            "count": cluster["count"],
            "templates": pruned_templates,
            "common_fields": cluster.get("common_fields", []),
            "naming_pattern": cluster.get("naming_pattern", ""),
        }

    if entity_catalog:
        payload["entity_catalog"] = entity_catalog

    # Config standards: inferred from cluster patterns
    config_standards: List[str] = []
    for cluster in clusters:
        et = cluster["entity_type"]
        naming = cluster.get("naming_pattern", "")
        if naming:
            config_standards.append(
                f"{et}: naming pattern '{naming}' (from {cluster['count']} configs)"
            )
        fvd = cluster.get("field_value_dist", {})
        for fname, dist in fvd.items():
            if dist:
                top_val = max(dist.items(), key=lambda x: x[1])
                config_standards.append(
                    f"{et}.{fname}: dominant value '{top_val[0]}' "
                    f"(n={top_val[1]}/{cluster['count']})"
                )

    if config_standards:
        payload["config_standards"] = config_standards

    # Cluster summary: overview of all clusters for this doc
    cluster_summary = []
    for cluster in clusters:
        cluster_summary.append({
            "entity_type": cluster["entity_type"],
            "entity_subtype": cluster.get("entity_subtype", ""),
            "count": cluster["count"],
            "n_templates": len(cluster.get("templates", [])),
            "avg_depth": cluster.get("avg_depth", 0),
            "avg_fields": cluster.get("avg_fields", 0),
            "structural_features": cluster.get("structural_features", {}),
        })
    if cluster_summary:
        payload["cluster_summary"] = cluster_summary

    return payload
