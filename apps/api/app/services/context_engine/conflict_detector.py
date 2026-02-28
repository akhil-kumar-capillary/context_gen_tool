"""Conflict Detector — post-LLM pass that identifies contradicting rules between leaf nodes.

Uses a fast LLM call (haiku-equivalent) to compare leaf node pairs within
the same or related categories.
"""
import asyncio
import logging
from typing import Any

from app.services.llm_service import call_llm

logger = logging.getLogger(__name__)


def _collect_leaves(node: dict, category: str = "") -> list[dict]:
    """Collect all leaf nodes with their parent category."""
    leaves = []
    cat_name = node.get("name", category) if node.get("type") == "cat" else category

    if node.get("type") == "leaf":
        leaves.append({
            "id": node.get("id", ""),
            "name": node.get("name", ""),
            "desc": node.get("desc", ""),
            "category": cat_name,
        })

    for child in node.get("children", []):
        leaves.extend(_collect_leaves(child, cat_name))

    return leaves


def _build_comparison_pairs(leaves: list[dict], max_pairs: int = 20) -> list[tuple[dict, dict]]:
    """Build pairs of leaves to compare.

    Strategy: compare within same category + cross-category for rule-like content.
    Caps at max_pairs to control LLM costs.
    """
    pairs = []

    # Group by category
    by_cat: dict[str, list[dict]] = {}
    for leaf in leaves:
        cat = leaf.get("category", "")
        if cat not in by_cat:
            by_cat[cat] = []
        by_cat[cat].append(leaf)

    # Within-category pairs
    for cat_leaves in by_cat.values():
        for i in range(len(cat_leaves)):
            for j in range(i + 1, len(cat_leaves)):
                if len(pairs) >= max_pairs:
                    return pairs
                pairs.append((cat_leaves[i], cat_leaves[j]))

    # Cross-category pairs (only for rule-like nodes)
    rule_keywords = {"rule", "rules", "default", "always", "never", "must", "should"}
    rule_leaves = [
        l for l in leaves
        if any(kw in l.get("name", "").lower() or kw in l.get("desc", "")[:200].lower()
               for kw in rule_keywords)
    ]
    for i in range(len(rule_leaves)):
        for j in range(i + 1, len(rule_leaves)):
            if rule_leaves[i]["category"] != rule_leaves[j]["category"]:
                if len(pairs) >= max_pairs:
                    return pairs
                pair = (rule_leaves[i], rule_leaves[j])
                if pair not in pairs:
                    pairs.append(pair)

    return pairs


async def detect_conflicts(
    tree: dict,
    provider: str = "anthropic",
    model: str = "claude-opus-4-6",
) -> int:
    """Detect contradictions between leaf nodes.

    Sends pairs to LLM for comparison. Updates the tree's analysis.conflicts
    in-place.

    Returns the number of conflicts found.
    """
    leaves = _collect_leaves(tree)

    if len(leaves) < 2:
        return 0

    pairs = _build_comparison_pairs(leaves)
    if not pairs:
        return 0

    conflict_count = 0

    # Build a single batch prompt for efficiency
    pair_descriptions = []
    for i, (a, b) in enumerate(pairs):
        pair_descriptions.append(
            f"PAIR {i + 1}:\n"
            f"  Node A: [{a['id']}] {a['name']} — {a['desc'][:300]}\n"
            f"  Node B: [{b['id']}] {b['name']} — {b['desc'][:300]}"
        )

    system = (
        "You are a conflict detection expert. Analyze each pair of context "
        "nodes and identify if they contain contradicting rules or instructions.\n\n"
        "For each pair, respond with ONLY:\n"
        "- 'NONE' if no conflict\n"
        "- A JSON object if conflict found: "
        '{"pair": N, "severity": "low|medium|high", "description": "what contradicts"}\n\n'
        "One response per pair, separated by newlines."
    )

    user_msg = "Check these pairs for conflicts:\n\n" + "\n\n".join(pair_descriptions)

    try:
        result = await call_llm(
            provider=provider,
            model=model,
            system=system,
            messages=[{"role": "user", "content": user_msg}],
            max_tokens=2000,
        )

        # Parse response
        response_text = ""
        for block in result.get("content", []):
            if block.get("type") == "text":
                response_text += block["text"]

        # Process each line
        import json
        for line in response_text.strip().split("\n"):
            line = line.strip()
            if not line or line.upper() == "NONE":
                continue
            try:
                conflict = json.loads(line)
                pair_idx = conflict.get("pair", 0) - 1
                if 0 <= pair_idx < len(pairs):
                    a, b = pairs[pair_idx]
                    _add_conflict(tree, a["id"], b["id"],
                                  conflict.get("description", ""),
                                  conflict.get("severity", "low"))
                    conflict_count += 1
            except (json.JSONDecodeError, KeyError):
                continue

    except Exception as e:
        logger.warning(f"Conflict detection failed (non-fatal): {e}")

    return conflict_count


def _add_conflict(tree: dict, node_a_id: str, node_b_id: str,
                  description: str, severity: str):
    """Add conflict entries to both nodes in the tree."""
    node_a = _find_node(tree, node_a_id)
    node_b = _find_node(tree, node_b_id)

    if node_a:
        if "analysis" not in node_a:
            node_a["analysis"] = {"redundancy": {"score": 0, "overlaps_with": [], "detail": ""}, "conflicts": [], "suggestions": []}
        node_a["analysis"]["conflicts"].append({
            "with_node": node_b_id,
            "description": description,
            "severity": severity,
        })

    if node_b:
        if "analysis" not in node_b:
            node_b["analysis"] = {"redundancy": {"score": 0, "overlaps_with": [], "detail": ""}, "conflicts": [], "suggestions": []}
        node_b["analysis"]["conflicts"].append({
            "with_node": node_a_id,
            "description": description,
            "severity": severity,
        })


def _find_node(tree: dict, node_id: str) -> dict | None:
    if tree.get("id") == node_id:
        return tree
    for child in tree.get("children", []):
        found = _find_node(child, node_id)
        if found:
            return found
    return None
