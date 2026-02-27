"""
Payload builder for Config APIs doc generation.

Takes analysis data (with union schemas, full objects, patterns) and builds
structured LLM payloads — one per doc type.

Each payload provides the LLM with:
- org_profile: inferred patterns about how this org uses configs
- entity_catalog: full real config objects (not truncated)
- field_reference: union schemas with valid values and presence %
- config_standards: auto-inferred rules from org patterns

Enhanced with:
- build_payloads_from_clusters(): uses top-5 templates from clusters
- strip_stats(): removes n/pct/count fields before sending to LLM
- inclusions support: toggle individual items on/off
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
                # Extract full objects into entity_catalog
                objects = (
                    entity_data.get("objects")
                    or entity_data.get("examples")
                )
                if objects:
                    entity_catalog[entity_key] = objects

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
                    entity_catalog[entity_key] = entity_data
            else:
                entity_catalog[entity_key] = entity_data

    if entity_catalog:
        payload["entity_catalog"] = entity_catalog
    if field_reference:
        payload["field_reference"] = field_reference
    if config_standards:
        payload["config_standards"] = config_standards

    text = json.dumps(payload, indent=2, default=str)

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

        payload_str = json.dumps(payload_obj, indent=2, default=str)

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

    # Entity catalog: templates from clusters (top 5 per type)
    entity_catalog: Dict[str, Any] = {}
    for cluster in clusters:
        et = cluster["entity_type"]
        subtype = cluster.get("entity_subtype", "")
        key = f"{et}:{subtype}" if subtype else et

        entity_catalog[key] = {
            "count": cluster["count"],
            "templates": cluster["templates"],
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
