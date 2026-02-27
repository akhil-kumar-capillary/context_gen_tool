"""
Frequency counters — aggregate patterns across all config fingerprints.

Analog of Databricks' frequency_counters.py but for Config API objects.
Produces Counter dicts that power the analysis dashboard visualizations
and inform the cluster builder.
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any, Dict, List, Tuple

from app.services.config_apis.config_fingerprint import ConfigFingerprint

logger = logging.getLogger(__name__)


def build_counters(
    fps: List[ConfigFingerprint],
) -> Tuple[Dict[str, Counter], int]:
    """Build frequency counters from config fingerprints.

    Returns:
        (counters_dict, total_count)

    Counter keys:
        entity_type      — {"campaign": 50, "program": 3, ...}
        entity_subtype   — {"TRANSACTIONAL": 20, "MARKETING": 15, ...}
        field_usage      — {("campaign", "name"): 48, ...}
        field_type       — {("name", "string"): 120, ...}
        field_value      — {("status", "ACTIVE"): 35, ...}
        nested_structure — {"rules": 15, "conditions": 22, ...}
        structural       — {"has_rules": 30, "has_conditions": 45, ...}
        naming_prefix    — {"TXN_": 12, "LP_": 5, ...}
        naming_separator — {"underscore": 30, "kebab": 5, "space": 10, ...}
        complexity       — {"shallow(0-2)": 50, "medium(3-5)": 30, ...}
    """
    C: Dict[str, Counter] = {
        "entity_type": Counter(),
        "entity_subtype": Counter(),
        "field_usage": Counter(),
        "field_type": Counter(),
        "field_value": Counter(),
        "nested_structure": Counter(),
        "structural": Counter(),
        "naming_prefix": Counter(),
        "naming_separator": Counter(),
        "complexity": Counter(),
    }

    total = len(fps)

    for fp in fps:
        # Entity type / subtype
        C["entity_type"][fp.entity_type] += 1
        if fp.entity_subtype:
            C["entity_subtype"][f"{fp.entity_type}:{fp.entity_subtype}"] += 1

        # Field usage (per entity_type)
        for fname in fp.field_names:
            C["field_usage"][(fp.entity_type, fname)] += 1

        # Field types
        for fname, ftype in fp.field_types.items():
            C["field_type"][(fname, ftype)] += 1

        # Field values (categorical)
        for fname, fval in fp.field_values.items():
            val_str = str(fval)[:100]  # cap value strings
            C["field_value"][(fname, val_str)] += 1

        # Nested structures
        for nkey in fp.nested_objects:
            C["nested_structure"][nkey] += 1

        # Structural flags
        if fp.has_rules:
            C["structural"]["has_rules"] += 1
        if fp.has_conditions:
            C["structural"]["has_conditions"] += 1
        if fp.has_workflow:
            C["structural"]["has_workflow"] += 1

        # Naming prefix (first word / segment before separator)
        if fp.entity_name:
            _name = fp.entity_name.strip()
            if "_" in _name:
                prefix = _name.split("_")[0]
                C["naming_prefix"][prefix] += 1
                C["naming_separator"]["underscore"] += 1
            elif "-" in _name:
                prefix = _name.split("-")[0]
                C["naming_prefix"][prefix] += 1
                C["naming_separator"]["kebab"] += 1
            elif " " in _name:
                prefix = _name.split(" ")[0]
                C["naming_prefix"][prefix] += 1
                C["naming_separator"]["space"] += 1
            else:
                C["naming_separator"]["none"] += 1

        # Complexity bracket
        if fp.depth <= 2:
            C["complexity"]["shallow(0-2)"] += 1
        elif fp.depth <= 5:
            C["complexity"]["medium(3-5)"] += 1
        else:
            C["complexity"]["deep(6+)"] += 1

    return C, total


def counters_to_serializable(
    C: Dict[str, Counter],
    top_n: int = 200,
) -> Dict[str, Any]:
    """Convert Counter objects to JSON-serializable sorted lists.

    Output format for each counter:
        [[key, count], [key, count], ...] sorted by count DESC.

    For tuple keys like ("campaign", "name"), they are joined as "campaign.name".
    """
    result: Dict[str, Any] = {}

    for counter_name, counter in C.items():
        entries = counter.most_common(top_n)
        serialized = []
        for key, count in entries:
            if isinstance(key, tuple):
                key_str = ".".join(str(k) for k in key)
            else:
                key_str = str(key)
            serialized.append([key_str, count])
        result[counter_name] = serialized

    return result
