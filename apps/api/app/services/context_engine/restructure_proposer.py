"""Restructure Proposer — proposes structural tree changes when overlap or conflicts are high.

Given a set of node IDs and an instruction (merge, split, reorganize),
uses LLM to propose a new tree structure with before/after comparison.
"""
import json
import logging
from typing import Any

from app.services.llm_service import call_llm
from app.services.context_engine.health_scorer import score_tree_health

logger = logging.getLogger(__name__)


def _find_node(tree: dict, node_id: str) -> dict | None:
    if tree.get("id") == node_id:
        return tree
    for child in tree.get("children", []):
        found = _find_node(child, node_id)
        if found:
            return found
    return None


def _extract_nodes(tree: dict, node_ids: list[str]) -> list[dict]:
    """Extract nodes by IDs from the tree."""
    return [n for nid in node_ids if (n := _find_node(tree, nid)) is not None]


async def propose_restructure(
    tree: dict,
    node_ids: list[str],
    instruction: str,
    provider: str = "anthropic",
    model: str = "claude-opus-4-6",
) -> dict:
    """Propose a restructure of selected nodes.

    Args:
        tree: Current tree dict.
        node_ids: IDs of nodes to restructure.
        instruction: What to do — "merge", "split", "reorganize", or free text.

    Returns:
        {
            "before": "description of current state",
            "after": "description of proposed state",
            "new_tree": {...},   # the proposed restructured tree
            "health_before": N,
            "health_after": N,
            "health_impact": "+N" or "-N",
            "needs_approval": True,
        }
    """
    target_nodes = _extract_nodes(tree, node_ids)
    if not target_nodes:
        raise ValueError("No valid nodes found for the given IDs")

    # Compute current health
    import copy
    tree_copy = copy.deepcopy(tree)
    score_tree_health(tree_copy)
    health_before = tree_copy.get("health", 0)

    # Build LLM request
    node_descriptions = []
    for node in target_nodes:
        node_json = json.dumps(node, indent=2, default=str)
        node_descriptions.append(f"--- Node: {node.get('name', '?')} (id: {node.get('id', '?')}) ---\n{node_json}")

    system = (
        "You are a context tree restructuring expert. Given a set of tree nodes "
        "and an instruction, propose a restructured version.\n\n"
        "Rules:\n"
        "- Preserve all content (desc fields) — do NOT lose any information\n"
        "- Maintain valid tree structure (root > cat > leaf)\n"
        "- Improve health scores by reducing redundancy and conflicts\n"
        "- Keep node IDs stable where possible (rename only when merging)\n\n"
        "Return ONLY a JSON object with these fields:\n"
        '{\n'
        '  "before": "brief description of current state",\n'
        '  "after": "brief description of proposed changes",\n'
        '  "nodes": [... array of restructured nodes ...]\n'
        '}\n\n'
        "No markdown, no code fences. Just the JSON."
    )

    user_msg = (
        f"Instruction: {instruction}\n\n"
        f"Full tree structure (for context):\n{json.dumps(tree, indent=2, default=str)[:5000]}\n\n"
        f"Target nodes to restructure:\n\n"
        + "\n\n".join(node_descriptions)
    )

    try:
        result = await call_llm(
            provider=provider,
            model=model,
            system=system,
            messages=[{"role": "user", "content": user_msg}],
            max_tokens=4000,
        )

        response_text = ""
        for block in result.get("content", []):
            if block.get("type") == "text":
                response_text += block["text"]

        # Parse the response
        proposal = json.loads(response_text.strip())

        # Build the new tree by replacing the target nodes
        new_tree = copy.deepcopy(tree)
        new_nodes = proposal.get("nodes", [])

        # Remove old nodes
        for nid in node_ids:
            _remove_node(new_tree, nid)

        # Find the parent of the first target node and insert new nodes
        if new_nodes:
            # Try to find a suitable parent
            parent = _find_parent(tree, node_ids[0]) if node_ids else None
            insert_target = _find_node(new_tree, parent.get("id", "root") if parent else "root")
            if insert_target:
                if "children" not in insert_target:
                    insert_target["children"] = []
                for n in new_nodes:
                    insert_target["children"].append(n)

        # Compute new health
        score_tree_health(new_tree)
        health_after = new_tree.get("health", 0)
        delta = health_after - health_before

        return {
            "before": proposal.get("before", "Current structure"),
            "after": proposal.get("after", "Proposed structure"),
            "new_tree": new_tree,
            "health_before": health_before,
            "health_after": health_after,
            "health_impact": f"+{delta}" if delta >= 0 else str(delta),
            "needs_approval": True,
        }

    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse restructure proposal: {e}")
    except Exception as e:
        raise ValueError(f"Restructure proposal failed: {e}")


def _remove_node(tree: dict, node_id: str) -> bool:
    """Remove a node by ID from the tree."""
    children = tree.get("children", [])
    for i, child in enumerate(children):
        if child.get("id") == node_id:
            children.pop(i)
            return True
        if _remove_node(child, node_id):
            return True
    return False


def _find_parent(tree: dict, node_id: str) -> dict | None:
    """Find the parent of a node by ID."""
    for child in tree.get("children", []):
        if child.get("id") == node_id:
            return tree
        found = _find_parent(child, node_id)
        if found:
            return found
    return None
