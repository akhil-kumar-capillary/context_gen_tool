"""Health Scorer — post-processes the LLM-generated tree to compute/validate health scores.

Scoring factors:
  - Content quality (30%): length, presence of meaningful text
  - Redundancy (25%): LLM-detected overlap score
  - Conflicts (25%): count and severity of contradictions
  - Completeness (20%): required fields present
"""
import logging

logger = logging.getLogger(__name__)

# Scoring weights
W_CONTENT = 0.30
W_REDUNDANCY = 0.25
W_CONFLICTS = 0.25
W_COMPLETENESS = 0.20

# Conflict severity penalties
CONFLICT_PENALTY = {"high": 15, "medium": 8, "low": 3}


def _score_content(node: dict) -> int:
    """Score content quality (0-100)."""
    desc = node.get("desc", "")
    if not desc:
        return 30  # No content at all

    length = len(desc.strip())
    if length > 500:
        return 100
    if length > 200:
        return 85
    if length > 100:
        return 70
    if length > 30:
        return 50
    return 30


def _score_redundancy(node: dict) -> int:
    """Score based on redundancy analysis (0-100, higher = less redundant)."""
    analysis = node.get("analysis", {})
    redundancy = analysis.get("redundancy", {})
    score = redundancy.get("score", 0)

    if score == 0:
        return 100  # No redundancy detected
    return max(0, 100 - score)


def _score_conflicts(node: dict) -> int:
    """Score based on conflict count and severity (0-100, higher = fewer conflicts)."""
    analysis = node.get("analysis", {})
    conflicts = analysis.get("conflicts", [])

    if not conflicts:
        return 100

    penalty = 0
    for c in conflicts:
        severity = c.get("severity", "low")
        penalty += CONFLICT_PENALTY.get(severity, 3)

    return max(0, 100 - penalty)


def _score_completeness(node: dict) -> int:
    """Score field completeness (0-100)."""
    score = 0
    total = 5  # 5 checkable fields

    if node.get("name"):
        score += 1
    if node.get("id"):
        score += 1
    if node.get("type") in ("root", "cat", "leaf"):
        score += 1
    if node.get("visibility") in ("public", "private"):
        score += 1
    if node.get("desc") or node.get("children"):
        score += 1

    return round((score / total) * 100)


def _score_leaf(node: dict) -> int:
    """Compute health score for a leaf node."""
    content_score = _score_content(node)
    redundancy_score = _score_redundancy(node)
    conflict_score = _score_conflicts(node)
    completeness_score = _score_completeness(node)

    weighted = (
        content_score * W_CONTENT
        + redundancy_score * W_REDUNDANCY
        + conflict_score * W_CONFLICTS
        + completeness_score * W_COMPLETENESS
    )
    return round(weighted)


def _score_category(node: dict) -> int:
    """Compute health for a category — weighted average of children."""
    children = node.get("children", [])
    if not children:
        return _score_completeness(node)

    total = 0
    count = 0
    for child in children:
        total += child.get("health", 70)
        count += 1

    return round(total / max(count, 1))


def score_tree_health(tree: dict) -> dict:
    """Walk tree and compute health scores.

    Modifies the tree in-place, updating each node's `health` field.
    Returns the modified tree.
    """
    _score_node(tree)
    return tree


def _score_node(node: dict, depth: int = 0):
    """Recursively score a node and all its children (bottom-up)."""
    children = node.get("children", [])

    # First, score all children
    for child in children:
        _score_node(child, depth + 1)

    # Then score this node
    if node.get("type") == "leaf":
        node["health"] = _score_leaf(node)
    elif children:
        node["health"] = _score_category(node)
    else:
        node["health"] = _score_completeness(node)
