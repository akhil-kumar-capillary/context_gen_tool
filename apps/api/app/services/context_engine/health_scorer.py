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
    """Score content quality (0-100) based on length AND structure."""
    desc = node.get("desc", "")
    if not desc:
        return 30  # No content at all

    text = desc.strip()
    length = len(text)

    # Base score from length
    if length > 500:
        base = 80
    elif length > 200:
        base = 65
    elif length > 100:
        base = 50
    elif length > 30:
        base = 40
    else:
        return 30

    # Bonus for structured content (up to +20)
    bonus = 0
    if "#" in text:          # Has headings
        bonus += 7
    if "|" in text:          # Has tables
        bonus += 5
    if "```" in text:        # Has code blocks
        bonus += 3
    if "- " in text or "* " in text:  # Has lists
        bonus += 5

    return min(100, base + bonus)


def _score_redundancy(node: dict) -> tuple[int, bool]:
    """Score based on redundancy analysis (0-100, higher = less redundant).

    Returns (score, is_uncertain) — uncertain if analysis data is missing.
    """
    analysis = node.get("analysis")
    if not analysis or not isinstance(analysis, dict):
        return 70, True  # Uncertain — cap at moderate score

    redundancy = analysis.get("redundancy")
    if not redundancy or not isinstance(redundancy, dict):
        return 70, True

    score = redundancy.get("score", 0)
    if score == 0:
        return 100, False
    return max(0, 100 - score), False


def _score_conflicts(node: dict) -> tuple[int, bool]:
    """Score based on conflict count and severity (0-100, higher = fewer conflicts).

    Returns (score, is_uncertain) — uncertain if analysis data is missing.
    """
    analysis = node.get("analysis")
    if not analysis or not isinstance(analysis, dict):
        return 70, True

    conflicts = analysis.get("conflicts")
    if conflicts is None:
        return 70, True

    if not conflicts:
        return 100, False

    penalty = 0
    for c in conflicts:
        severity = c.get("severity", "low")
        penalty += CONFLICT_PENALTY.get(severity, 3)

    return max(0, 100 - penalty), False


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
    """Compute health score for a leaf node.

    If analysis data is missing (enricher failed), the score is capped
    at 70 to indicate uncertainty rather than falsely reporting 100.
    """
    content_score = _score_content(node)
    redundancy_score, r_uncertain = _score_redundancy(node)
    conflict_score, c_uncertain = _score_conflicts(node)
    completeness_score = _score_completeness(node)

    weighted = (
        content_score * W_CONTENT
        + redundancy_score * W_REDUNDANCY
        + conflict_score * W_CONFLICTS
        + completeness_score * W_COMPLETENESS
    )
    score = round(weighted)

    # Cap at 70 if analysis data is missing — indicates uncertainty
    if (r_uncertain or c_uncertain) and score > 70:
        score = 70

    return score


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
