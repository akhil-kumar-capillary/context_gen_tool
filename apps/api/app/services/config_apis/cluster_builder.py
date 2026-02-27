"""
Cluster builder — groups configs by entity type and selects top-N templates.

Analog of Databricks' cluster_builder.py. Groups config fingerprints by
(entity_type, entity_subtype), then selects diverse representative templates
for LLM context generation.

Default: top 5 templates per cluster (user requirement).
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from typing import Any, Dict, List

from app.services.config_apis.config_fingerprint import ConfigFingerprint

logger = logging.getLogger(__name__)


def build_clusters(
    fps: List[ConfigFingerprint],
    max_templates_per_type: int = 5,
) -> List[Dict[str, Any]]:
    """Group fingerprints by (entity_type, entity_subtype) and select templates.

    For each cluster:
    1. Collect all fingerprints in that group
    2. Sort by structural complexity (depth * total_fields)
    3. Select diverse templates: simplest, most complex, + mid-range
    4. Record cluster stats (counts, common fields, naming patterns, etc.)

    Returns list of cluster dicts.
    """
    # Group fingerprints by (entity_type, entity_subtype)
    groups: Dict[tuple, List[ConfigFingerprint]] = defaultdict(list)
    for fp in fps:
        key = (fp.entity_type, fp.entity_subtype)
        groups[key].append(fp)

    clusters: List[Dict[str, Any]] = []

    for (entity_type, entity_subtype), group_fps in groups.items():
        cluster = _build_one_cluster(
            entity_type=entity_type,
            entity_subtype=entity_subtype,
            group_fps=group_fps,
            max_templates=max_templates_per_type,
        )
        clusters.append(cluster)

    # Sort clusters by count descending
    clusters.sort(key=lambda c: c["count"], reverse=True)

    logger.info(
        "Built %d clusters from %d fingerprints (max %d templates each)",
        len(clusters),
        len(fps),
        max_templates_per_type,
    )
    return clusters


def _build_one_cluster(
    entity_type: str,
    entity_subtype: str,
    group_fps: List[ConfigFingerprint],
    max_templates: int,
) -> Dict[str, Any]:
    """Build a single cluster from a group of fingerprints."""
    count = len(group_fps)

    # ── Select diverse templates ──
    selected = _select_diverse_templates(group_fps, max_templates)
    template_ids = [fp.id for fp in selected]
    templates = [fp.raw_object for fp in selected]

    # ── Common fields (present in >70% of cluster) ──
    field_counter: Counter = Counter()
    for fp in group_fps:
        for fname in fp.field_names:
            field_counter[fname] += 1
    threshold = max(1, int(count * 0.7))
    common_fields = [f for f, c in field_counter.most_common() if c >= threshold]

    # ── Field value distribution (for categorical fields) ──
    field_value_dist: Dict[str, Dict[str, int]] = defaultdict(lambda: Counter())
    for fp in group_fps:
        for fname, fval in fp.field_values.items():
            val_str = str(fval)[:100]
            field_value_dist[fname][val_str] += 1
    # Convert to serializable
    field_value_dist_ser = {
        fname: dict(counter.most_common(20))
        for fname, counter in field_value_dist.items()
    }

    # ── Naming pattern ──
    naming_pattern = _detect_naming_pattern(group_fps)

    # ── Complexity stats ──
    depths = [fp.depth for fp in group_fps]
    fields = [fp.total_fields for fp in group_fps]
    avg_depth = round(sum(depths) / max(count, 1), 1)
    avg_fields = round(sum(fields) / max(count, 1), 1)

    # ── Structural feature counts ──
    rules_count = sum(1 for fp in group_fps if fp.has_rules)
    conditions_count = sum(1 for fp in group_fps if fp.has_conditions)
    workflow_count = sum(1 for fp in group_fps if fp.has_workflow)

    return {
        "entity_type": entity_type,
        "entity_subtype": entity_subtype,
        "count": count,
        "template_ids": template_ids,
        "templates": templates,
        "common_fields": common_fields,
        "field_value_dist": field_value_dist_ser,
        "naming_pattern": naming_pattern,
        "avg_depth": avg_depth,
        "avg_fields": avg_fields,
        "structural_features": {
            "has_rules": rules_count,
            "has_conditions": conditions_count,
            "has_workflow": workflow_count,
        },
    }


def _select_diverse_templates(
    fps: List[ConfigFingerprint],
    n: int,
) -> List[ConfigFingerprint]:
    """Select N diverse templates from a list of fingerprints.

    Strategy:
    1. Sort by complexity (depth * total_fields)
    2. Always include simplest and most complex
    3. Fill remaining slots with evenly-spaced picks from the middle
    """
    if len(fps) <= n:
        return fps

    # Sort by complexity score
    scored = sorted(fps, key=lambda fp: fp.depth * max(fp.total_fields, 1))

    selected: List[ConfigFingerprint] = []

    # Always include simplest
    selected.append(scored[0])

    # Always include most complex
    selected.append(scored[-1])

    # Fill remaining from middle, evenly spaced
    remaining = n - 2
    if remaining > 0:
        middle = scored[1:-1]
        if len(middle) <= remaining:
            selected.extend(middle)
        else:
            step = len(middle) / remaining
            for i in range(remaining):
                idx = min(int(i * step), len(middle) - 1)
                candidate = middle[idx]
                if candidate not in selected:
                    selected.append(candidate)
                else:
                    # Find next unused
                    for alt in middle:
                        if alt not in selected:
                            selected.append(alt)
                            break

    return selected[:n]


def _detect_naming_pattern(fps: List[ConfigFingerprint]) -> str:
    """Detect common naming pattern from fingerprint names."""
    names = [fp.entity_name for fp in fps if fp.entity_name]
    if not names:
        return ""

    # Check for common prefix
    prefixes: Counter = Counter()
    for name in names:
        parts = None
        if "_" in name:
            parts = name.split("_")
        elif "-" in name:
            parts = name.split("-")
        elif " " in name:
            parts = name.split(" ")
        if parts and parts[0]:
            prefixes[parts[0]] += 1

    if prefixes:
        top_prefix, top_count = prefixes.most_common(1)[0]
        if top_count >= max(2, len(names) * 0.3):
            sep = "_" if "_" in names[0] else "-" if "-" in names[0] else " "
            return f"{top_prefix}{sep}*"

    return ""
