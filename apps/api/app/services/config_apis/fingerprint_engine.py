"""
Fingerprint engine — extracts ConfigFingerprint from every config object.

Iterates over raw extracted API data and decomposes each config object into
a typed structural fingerprint for frequency analysis and template selection.

Analog of Databricks' fingerprint_engine.py but for Config API objects.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

from app.services.config_apis.config_fingerprint import (
    ConfigFingerprint,
    _CATEGORICAL_FIELDS,
    _CONDITION_KEYWORDS,
    _ID_FIELDS,
    _NAME_FIELDS,
    _RULE_KEYWORDS,
    _TYPE_FIELDS,
    _WORKFLOW_KEYWORDS,
)

logger = logging.getLogger(__name__)

# Max string length to store in raw_object
_MAX_STR_LEN = 2000


# ═══════════════════════════════════════════════════════════════════════
# Entity type mapping: category → {api_key: entity_type}
# ═══════════════════════════════════════════════════════════════════════

ENTITY_MAP: Dict[str, Dict[str, str]] = {
    "loyalty": {
        "programs": "program",
        "tiers": "tier",
        "earning_strategies": "strategy",
        "expiry_strategies": "strategy",
        "alternate_currencies": "alternate_currency",
        "partner_programs": "partner_program",
        "event_types": "event_type",
        "custom_fields": "loyalty_custom_field",
    },
    "campaigns": {
        "campaigns": "campaign",
        "campaign_details": "campaign_config",
        "campaign_messages": "message",
        "sms_templates": "sms_template",
        "email_templates": "email_template",
    },
    "promotions": {
        "loyalty_promotions": "loyalty_promotion",
        "cart_promotions": "cart_promotion",
        "custom_fields": "promotion_custom_field",
        "rewards_groups": "rewards_group",
    },
    "audiences": {
        "audiences": "audience",
        "target_groups": "target_group",
        "behavioral_events": "behavioral_event",
        "audience_filters": "audience_filter",
        "dim_attr_availability": "audience_filter",
    },
    "coupons": {
        "coupon_series": "coupon_series",
        "product_categories": "product_category",
        "product_brands": "product_brand",
        "product_attributes": "product_attribute",
    },
    "extended_fields": {
        "customer_extended_fields": "customer_ef",
        "transaction_extended_fields": "txn_ef",
        "lineitem_extended_fields": "line_item_ef",
    },
    "org_settings": {
        "behavioral_events": "org_behavioral_event",
        "customer_labels": "customer_label",
        "org_hierarchy": "org_hierarchy_node",
        "target_groups": "target_group",
    },
}


# ═══════════════════════════════════════════════════════════════════════
# Extract items from Capillary response shapes (reused from analysis_engine)
# ═══════════════════════════════════════════════════════════════════════

def _extract_items(data: Any) -> list:
    """Extract list of items from various Capillary API response shapes."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if "_error" in data:
            return []
        for key in (
            "data", "entity", "entities", "programs", "tiers",
            "strategies", "promotions", "campaigns", "audiences",
            "results", "items", "records", "config",
        ):
            val = data.get(key)
            if isinstance(val, list):
                return val
            if isinstance(val, dict) and "data" in val and isinstance(val["data"], list):
                return val["data"]
    return []


# ═══════════════════════════════════════════════════════════════════════
# Core helpers
# ═══════════════════════════════════════════════════════════════════════

def _infer_type(val: Any) -> str:
    """Infer a simple type label for a value."""
    if val is None:
        return "null"
    if isinstance(val, bool):
        return "boolean"
    if isinstance(val, int):
        return "integer"
    if isinstance(val, float):
        return "number"
    if isinstance(val, str):
        return "string"
    if isinstance(val, list):
        return "array"
    if isinstance(val, dict):
        return "object"
    return "unknown"


def _compute_depth(obj: Any, current: int = 0) -> int:
    """Compute maximum nesting depth of a dict/list structure."""
    if isinstance(obj, dict):
        if not obj:
            return current
        return max(
            _compute_depth(v, current + 1) for v in obj.values()
        )
    if isinstance(obj, list):
        if not obj:
            return current
        return max(
            _compute_depth(v, current + 1) for v in obj[:20]  # cap for perf
        )
    return current


def _count_fields(obj: Any) -> int:
    """Count total number of fields recursively (keys in dicts)."""
    if isinstance(obj, dict):
        total = len(obj)
        for v in obj.values():
            total += _count_fields(v)
        return total
    if isinstance(obj, list):
        return sum(_count_fields(v) for v in obj[:20])
    return 0


def _cap_strings(obj: Any, max_len: int = _MAX_STR_LEN) -> Any:
    """Recursively cap long strings in a dict/list structure."""
    if isinstance(obj, str):
        return obj[:max_len] + "…" if len(obj) > max_len else obj
    if isinstance(obj, dict):
        return {k: _cap_strings(v, max_len) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_cap_strings(v, max_len) for v in obj]
    return obj


def _detect_keywords(obj: Any, keywords: frozenset, visited: int = 0) -> bool:
    """Check if any key in a nested dict matches the keyword set."""
    if visited > 8:
        return False
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in keywords:
                return True
            if isinstance(v, (dict, list)):
                if _detect_keywords(v, keywords, visited + 1):
                    return True
    if isinstance(obj, list):
        for item in obj[:10]:
            if _detect_keywords(item, keywords, visited + 1):
                return True
    return False


def _extract_first(obj: dict, field_names: tuple) -> Any:
    """Return the first non-None value for a set of field names."""
    for f in field_names:
        val = obj.get(f)
        if val is not None:
            return val
    return None


# ═══════════════════════════════════════════════════════════════════════
# Single fingerprint extraction
# ═══════════════════════════════════════════════════════════════════════

def extract_fingerprint(
    fp_id: str,
    category: str,
    entity_type: str,
    obj: dict,
) -> ConfigFingerprint:
    """Parse one config object into a ConfigFingerprint."""
    if not isinstance(obj, dict):
        return ConfigFingerprint(
            id=fp_id,
            category=category,
            entity_type=entity_type,
            raw_object={"_value": str(obj)[:500]},
        )

    # Top-level field names and types
    field_names = list(obj.keys())
    field_types = {k: _infer_type(v) for k, v in obj.items()}
    nested_objects = [k for k, v in obj.items() if isinstance(v, (dict, list))]

    # Categorical / enum-like field values
    field_values: Dict[str, Any] = {}
    for k, v in obj.items():
        if k in _CATEGORICAL_FIELDS and v is not None:
            field_values[k] = v

    # Identity extraction
    entity_name = str(_extract_first(obj, _NAME_FIELDS) or "")
    entity_id = _extract_first(obj, _ID_FIELDS)
    entity_subtype = str(_extract_first(obj, _TYPE_FIELDS) or "")

    # Complexity metrics
    depth = _compute_depth(obj)
    total_fields = _count_fields(obj)

    # Structural flags
    has_rules = _detect_keywords(obj, _RULE_KEYWORDS)
    has_conditions = _detect_keywords(obj, _CONDITION_KEYWORDS)
    has_workflow = _detect_keywords(obj, _WORKFLOW_KEYWORDS)

    return ConfigFingerprint(
        id=fp_id,
        category=category,
        entity_type=entity_type,
        entity_subtype=entity_subtype,
        entity_name=entity_name[:200],
        entity_id=entity_id,
        field_names=field_names,
        nested_objects=nested_objects,
        field_types=field_types,
        field_values=field_values,
        depth=depth,
        total_fields=total_fields,
        has_rules=has_rules,
        has_conditions=has_conditions,
        has_workflow=has_workflow,
        raw_object=_cap_strings(obj),
    )


# ═══════════════════════════════════════════════════════════════════════
# Batch extraction from all categories
# ═══════════════════════════════════════════════════════════════════════

def extract_all_fingerprints(
    raw_data: Dict[str, Any],
) -> Tuple[List[ConfigFingerprint], Dict[str, int]]:
    """Extract fingerprints from ALL extraction categories.

    Args:
        raw_data: The extracted_data dict from ConfigExtractionRun,
                  keyed by category (loyalty, campaigns, etc.)

    Returns:
        (fingerprints, entity_type_counts)
        where entity_type_counts = {"program": 3, "campaign": 50, ...}
    """
    fingerprints: List[ConfigFingerprint] = []
    entity_type_counts: Dict[str, int] = {}

    for category, api_data in raw_data.items():
        if not isinstance(api_data, dict):
            continue

        entity_map = ENTITY_MAP.get(category, {})

        for api_key, response_data in api_data.items():
            entity_type = entity_map.get(api_key)
            if not entity_type:
                # Fallback: use api_key as entity_type
                entity_type = api_key.rstrip("s") if api_key.endswith("s") else api_key

            items = _extract_items(response_data)
            if not items:
                # If response_data itself is a dict (single object, not list)
                if isinstance(response_data, dict) and "_error" not in response_data:
                    fp_id = f"{category}__{api_key}__0"
                    fp = extract_fingerprint(fp_id, category, entity_type, response_data)
                    fingerprints.append(fp)
                    entity_type_counts[entity_type] = entity_type_counts.get(entity_type, 0) + 1
                continue

            for idx, item in enumerate(items):
                fp_id = f"{category}__{api_key}__{idx}"
                fp = extract_fingerprint(fp_id, category, entity_type, item)
                fingerprints.append(fp)

            entity_type_counts[entity_type] = (
                entity_type_counts.get(entity_type, 0) + len(items)
            )

    logger.info(
        "Extracted %d fingerprints across %d entity types",
        len(fingerprints),
        len(entity_type_counts),
    )
    return fingerprints, entity_type_counts
