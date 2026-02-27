"""Redundancy Detector — detects semantic overlap between leaf nodes.

Sends batches of node descriptions to LLM and asks for pairwise
similarity scores. Updates the tree's analysis.redundancy in-place.
"""
import json
import logging
from typing import Any

from app.services.llm_service import call_llm

logger = logging.getLogger(__name__)


def _collect_leaves(node: dict) -> list[dict]:
    """Collect all leaf nodes from the tree."""
    leaves = []
    if node.get("type") == "leaf":
        leaves.append({
            "id": node.get("id", ""),
            "name": node.get("name", ""),
            "desc": (node.get("desc", "") or "")[:500],  # Truncate for efficiency
        })
    for child in node.get("children", []):
        leaves.extend(_collect_leaves(child))
    return leaves


async def detect_redundancy(
    tree: dict,
    provider: str = "anthropic",
    model: str = "claude-sonnet-4-20250514",
    threshold: int = 40,
) -> int:
    """Detect semantic overlap between leaf nodes.

    Sends groups of node descriptions to LLM and asks for pairwise
    similarity scores. Updates analysis.redundancy for each node.

    Args:
        tree: The tree dict to analyze.
        provider: LLM provider.
        model: LLM model.
        threshold: Minimum overlap score (0-100) to report.

    Returns the number of redundant overlaps found.
    """
    leaves = _collect_leaves(tree)
    if len(leaves) < 2:
        return 0

    # Process in batches of 10 for manageable LLM calls
    batch_size = 10
    all_overlaps: list[dict] = []

    for i in range(0, len(leaves), batch_size):
        batch = leaves[i:i + batch_size]
        if len(batch) < 2:
            continue

        overlaps = await _check_batch(batch, provider, model)
        all_overlaps.extend(overlaps)

    # Apply overlap results to the tree
    count = 0
    for overlap in all_overlaps:
        if overlap["score"] >= threshold:
            _add_redundancy(
                tree,
                overlap["node_a"],
                overlap["node_b"],
                overlap["score"],
                overlap.get("detail", ""),
            )
            count += 1

    return count


async def _check_batch(
    batch: list[dict],
    provider: str,
    model: str,
) -> list[dict]:
    """Check a batch of nodes for pairwise similarity."""
    node_descriptions = []
    for i, node in enumerate(batch):
        node_descriptions.append(
            f"NODE {i + 1} [{node['id']}]: {node['name']}\n{node['desc']}"
        )

    system = (
        "You are a semantic similarity expert. Compare the following context "
        "nodes and rate their pairwise overlap.\n\n"
        "For EACH pair with > 30% semantic overlap, output a JSON line:\n"
        '{"a": "node_id_1", "b": "node_id_2", "score": 0-100, "detail": "brief explanation"}\n\n'
        "Output ONLY the JSON lines (one per pair with overlap), nothing else. "
        "If no pairs have significant overlap, output: NONE"
    )

    user_msg = "Compare these nodes for semantic overlap:\n\n" + "\n\n---\n\n".join(node_descriptions)

    try:
        result = await call_llm(
            provider=provider,
            model=model,
            system=system,
            messages=[{"role": "user", "content": user_msg}],
            max_tokens=1500,
        )

        response_text = ""
        for block in result.get("content", []):
            if block.get("type") == "text":
                response_text += block["text"]

        overlaps = []
        for line in response_text.strip().split("\n"):
            line = line.strip()
            if not line or line.upper() == "NONE":
                continue
            try:
                data = json.loads(line)
                overlaps.append({
                    "node_a": data.get("a", ""),
                    "node_b": data.get("b", ""),
                    "score": data.get("score", 0),
                    "detail": data.get("detail", ""),
                })
            except json.JSONDecodeError:
                continue

        return overlaps

    except Exception as e:
        logger.warning(f"Redundancy batch check failed (non-fatal): {e}")
        return []


def _add_redundancy(
    tree: dict,
    node_a_id: str,
    node_b_id: str,
    score: int,
    detail: str,
):
    """Add redundancy entries to both nodes in the tree."""
    node_a = _find_node(tree, node_a_id)
    node_b = _find_node(tree, node_b_id)

    if node_a:
        if "analysis" not in node_a:
            node_a["analysis"] = {
                "redundancy": {"score": 0, "overlaps_with": [], "detail": ""},
                "conflicts": [],
                "suggestions": [],
            }
        r = node_a["analysis"]["redundancy"]
        # Keep the highest overlap score
        if score > r.get("score", 0):
            r["score"] = score
            r["detail"] = detail
        if node_b_id not in r.get("overlaps_with", []):
            r.setdefault("overlaps_with", []).append(node_b_id)

    if node_b:
        if "analysis" not in node_b:
            node_b["analysis"] = {
                "redundancy": {"score": 0, "overlaps_with": [], "detail": ""},
                "conflicts": [],
                "suggestions": [],
            }
        r = node_b["analysis"]["redundancy"]
        if score > r.get("score", 0):
            r["score"] = score
            r["detail"] = detail
        if node_a_id not in r.get("overlaps_with", []):
            r.setdefault("overlaps_with", []).append(node_a_id)


def _find_node(tree: dict, node_id: str) -> dict | None:
    if tree.get("id") == node_id:
        return tree
    for child in tree.get("children", []):
        found = _find_node(child, node_id)
        if found:
            return found
    return None
