"""Tree Modifier — intelligent context tree modification with zero information loss.

Three-phase workflow:
  1. analyze_and_plan() — LLM checks conflicts, duplicates, decides placement
  2. apply_modification() — deterministic code applies the plan
  3. validate_no_info_loss() — verifies no content was lost
"""
import copy
import json
import logging
import re
import uuid
from dataclasses import dataclass, field

from app.config import settings
from app.services.llm_service import call_llm

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class ModificationPlan:
    """LLM's decision on how to integrate new content into the tree."""

    action: str  # add_to_existing | create_leaf | create_category | modify_existing | remove
    target_node_id: str | None = None
    target_parent_id: str | None = None
    new_content: str = ""
    new_name: str | None = None
    rationale: str = ""
    conflicts: list[dict] = field(default_factory=list)
    duplicates: list[dict] = field(default_factory=list)
    cross_references: list[dict] = field(default_factory=list)
    needs_user_confirmation: bool = False
    position_after: str | None = None  # node_id to insert after (for ordering)


@dataclass
class ValidationReport:
    """Post-modification validation results."""

    passed: bool
    before_leaf_count: int
    after_leaf_count: int
    before_total_chars: int
    after_total_chars: int
    missing_sentences: list[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class ModificationResult:
    """Result of applying a modification."""

    success: bool
    action_taken: str
    node_id: str  # created / modified node
    updated_tree: dict
    validation: ValidationReport
    summary: str


# ---------------------------------------------------------------------------
# System prompt for the planning LLM call
# ---------------------------------------------------------------------------

PLAN_SYSTEM_PROMPT = """\
You are a context tree modification expert. You receive a compact view of a \
hierarchical context tree and a user's request to add, modify, or remove context.

## Tree Structure
The tree has three node types:
- **root**: Top-level container
- **cat** (category): Grouping node with children
- **leaf**: Content node with `desc` containing the full context text

## Your Job
1. ANALYZE the user's request — what content do they want to add/modify/remove?
2. CHECK CONFLICTS: Does the new content contradict ANY existing node's rules or information? \
If so, list each conflict with the conflicting node ID, description, and severity (low/medium/high).
3. CHECK DUPLICATES: Is similar content already covered? If so, list each duplicate with \
the node ID and overlap detail.
4. DECIDE PLACEMENT: Should this go into an existing node (append) or a new node? \
Choose the most semantically appropriate location.
5. FORMAT CONTENT: Match the existing tree's tone (instructional, reference-style). \
Use markdown formatting consistent with existing nodes.
6. CROSS-REFERENCE: Note relationships to other nodes where relevant.

## Critical Rules
- ZERO information loss: NEVER suggest removing or overwriting existing content \
unless the user EXPLICITLY asks to replace something.
- When adding to an existing node: APPEND to its content (don't replace).
- When creating a new node: choose the best category. Create a new category only \
if no existing one fits.
- If content conflicts with existing rules, set needs_user_confirmation=true.
- If content is a near-duplicate, set needs_user_confirmation=true.
- Match the naming conventions of existing nodes.

## Output
Return a single JSON object (no markdown fences, no extra text):
{
  "action": "add_to_existing" | "create_leaf" | "create_category" | "modify_existing" | "remove",
  "target_node_id": "...",
  "target_parent_id": "...",
  "new_content": "the formatted content to add/set",
  "new_name": "name for new node (if creating)",
  "rationale": "why this placement was chosen",
  "conflicts": [{"with_node": "node_id", "description": "...", "severity": "low|medium|high"}],
  "duplicates": [{"node_id": "node_id", "overlap_detail": "..."}],
  "cross_references": [{"from_node": "node_id", "to_node": "node_id", "relationship": "..."}],
  "needs_user_confirmation": false,
  "position_after": null
}
"""


# ---------------------------------------------------------------------------
# Tree utility functions
# ---------------------------------------------------------------------------


def compact_tree_for_llm(tree: dict, max_chars: int | None = None) -> str:
    """Serialize tree as compact text for LLM context.

    Shows: node ID, name, type, first ~200 chars of desc, children count.
    """
    max_chars = max_chars or getattr(settings, "tree_modify_max_compact_chars", 50000)
    lines: list[str] = []

    def _walk(node: dict, depth: int = 0):
        indent = "  " * depth
        ntype = node.get("type", "leaf")
        nid = node.get("id", "?")
        name = node.get("name", "?")
        health = node.get("health", "?")
        vis = node.get("visibility", "public")

        desc = node.get("desc", "")
        desc_preview = desc[:200].replace("\n", " ") + ("..." if len(desc) > 200 else "")

        children = node.get("children", [])
        child_info = f", {len(children)} children" if children else ""

        line = f"{indent}[{ntype}] {nid} | {name} | health={health} | vis={vis}{child_info}"
        if desc_preview and ntype == "leaf":
            line += f"\n{indent}  desc: {desc_preview}"

        lines.append(line)
        for child in children:
            _walk(child, depth + 1)

    _walk(tree)
    result = "\n".join(lines)

    # Truncate if too long
    if len(result) > max_chars:
        result = result[:max_chars] + "\n... (truncated)"

    return result


def collect_all_content(tree: dict) -> dict[str, str]:
    """Collect {node_id: full_desc} for every leaf node."""
    content_map: dict[str, str] = {}

    def _walk(node: dict):
        if node.get("type") == "leaf" and node.get("desc"):
            content_map[node["id"]] = node["desc"]
        for child in node.get("children", []):
            _walk(child)

    _walk(tree)
    return content_map


def count_leaves(tree: dict) -> int:
    """Count total leaf nodes."""
    if tree.get("type") == "leaf":
        return 1
    return sum(count_leaves(c) for c in tree.get("children", []))


def total_content_chars(tree: dict) -> int:
    """Sum of all leaf desc lengths."""
    return sum(len(v) for v in collect_all_content(tree).values())


def find_node(tree: dict, node_id: str) -> dict | None:
    """Find a node by ID."""
    if tree.get("id") == node_id:
        return tree
    for child in tree.get("children", []):
        found = find_node(child, node_id)
        if found:
            return found
    return None


def find_parent(tree: dict, node_id: str) -> dict | None:
    """Find the parent of a node."""
    for child in tree.get("children", []):
        if child.get("id") == node_id:
            return tree
        found = find_parent(child, node_id)
        if found:
            return found
    return None


def remove_node(tree: dict, node_id: str) -> bool:
    """Remove a node by ID. Returns True if found and removed."""
    children = tree.get("children", [])
    for i, child in enumerate(children):
        if child.get("id") == node_id:
            children.pop(i)
            return True
        if remove_node(child, node_id):
            return True
    return False


# ---------------------------------------------------------------------------
# Phase 1: Analyze & Plan
# ---------------------------------------------------------------------------


async def analyze_and_plan(
    tree: dict,
    user_request: str,
    content: str = "",
    provider: str = "anthropic",
    model: str = "claude-sonnet-4-6",
) -> ModificationPlan:
    """Ask LLM to analyze the tree and produce a modification plan.

    Returns a ModificationPlan with placement decision, conflicts, duplicates, etc.
    """
    compact = compact_tree_for_llm(tree)
    max_tokens = getattr(settings, "tree_modify_max_output_tokens", 8192)

    user_msg = f"""## Current Context Tree
{compact}

## User Request
{user_request}

## Content to Integrate
{content if content else "(no specific content provided — infer from request)"}

Analyze the tree and return your modification plan as a JSON object."""

    result = await call_llm(
        provider=provider,
        model=model,
        system=PLAN_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
        max_tokens=max_tokens,
    )

    # Extract text from response
    raw_text = ""
    for block in result.get("content", []):
        if block.get("type") == "text":
            raw_text += block["text"]

    # Parse JSON from response
    plan_data = _parse_plan_json(raw_text)

    return ModificationPlan(
        action=plan_data.get("action", "create_leaf"),
        target_node_id=plan_data.get("target_node_id"),
        target_parent_id=plan_data.get("target_parent_id"),
        new_content=plan_data.get("new_content", content),
        new_name=plan_data.get("new_name"),
        rationale=plan_data.get("rationale", ""),
        conflicts=plan_data.get("conflicts", []),
        duplicates=plan_data.get("duplicates", []),
        cross_references=plan_data.get("cross_references", []),
        needs_user_confirmation=plan_data.get("needs_user_confirmation", False),
        position_after=plan_data.get("position_after"),
    )


def _parse_plan_json(raw: str) -> dict:
    """Parse JSON from LLM response, handling markdown fences and extra text."""
    # Try direct parse first
    try:
        return json.loads(raw.strip())
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown code fence
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Try finding JSON object in the text
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    logger.error(f"Failed to parse modification plan JSON: {raw[:500]}")
    raise ValueError("Could not parse LLM's modification plan as JSON")


# ---------------------------------------------------------------------------
# Phase 2: Apply Modification
# ---------------------------------------------------------------------------


def apply_modification(tree: dict, plan: ModificationPlan) -> dict:
    """Apply a ModificationPlan to the tree. Returns the modified tree.

    This is deterministic code — no LLM calls. The tree is modified in place.
    """
    action = plan.action

    if action == "add_to_existing":
        return _apply_add_to_existing(tree, plan)
    elif action == "create_leaf":
        return _apply_create_leaf(tree, plan)
    elif action == "create_category":
        return _apply_create_category(tree, plan)
    elif action == "modify_existing":
        return _apply_modify_existing(tree, plan)
    elif action == "remove":
        return _apply_remove(tree, plan)
    else:
        raise ValueError(f"Unknown action: {action}")


def _apply_add_to_existing(tree: dict, plan: ModificationPlan) -> dict:
    """Append content to an existing node's desc. Never overwrites."""
    if not plan.target_node_id:
        raise ValueError("add_to_existing requires target_node_id")

    node = find_node(tree, plan.target_node_id)
    if not node:
        raise ValueError(f"Target node '{plan.target_node_id}' not found")

    existing = node.get("desc", "")
    separator = "\n\n" if existing else ""
    node["desc"] = existing + separator + plan.new_content

    # Add cross-references as a comment at the end
    if plan.cross_references:
        refs = ", ".join(
            f"{r.get('to_node', '?')} ({r.get('relationship', '')})"
            for r in plan.cross_references
        )
        node["desc"] += f"\n\n> **See also:** {refs}"

    return tree


def _apply_create_leaf(tree: dict, plan: ModificationPlan) -> dict:
    """Create a new leaf node under the target parent."""
    parent_id = plan.target_parent_id or "root"
    parent = find_node(tree, parent_id)
    if not parent:
        # Fallback to root
        parent = tree

    if "children" not in parent:
        parent["children"] = []

    node_id = f"leaf_{uuid.uuid4().hex[:8]}"
    new_node: dict = {
        "id": node_id,
        "name": plan.new_name or plan.new_content[:60].strip(),
        "type": "leaf",
        "health": 80,
        "visibility": "public",
        "desc": plan.new_content,
        "source": "manual",
    }

    # Add cross-references
    if plan.cross_references:
        refs = ", ".join(
            f"{r.get('to_node', '?')} ({r.get('relationship', '')})"
            for r in plan.cross_references
        )
        new_node["desc"] += f"\n\n> **See also:** {refs}"

    # Position after a specific node if specified
    if plan.position_after:
        children = parent["children"]
        insert_idx = len(children)
        for i, child in enumerate(children):
            if child.get("id") == plan.position_after:
                insert_idx = i + 1
                break
        children.insert(insert_idx, new_node)
    else:
        parent["children"].append(new_node)

    plan.target_node_id = node_id  # store for result
    return tree


def _apply_create_category(tree: dict, plan: ModificationPlan) -> dict:
    """Create a new category with an initial leaf node."""
    parent_id = plan.target_parent_id or "root"
    parent = find_node(tree, parent_id)
    if not parent:
        parent = tree

    if "children" not in parent:
        parent["children"] = []

    cat_id = f"cat_{uuid.uuid4().hex[:8]}"
    leaf_id = f"leaf_{uuid.uuid4().hex[:8]}"

    new_cat: dict = {
        "id": cat_id,
        "name": plan.new_name or "New Category",
        "type": "cat",
        "health": 80,
        "visibility": "public",
        "children": [
            {
                "id": leaf_id,
                "name": plan.new_name or plan.new_content[:60].strip(),
                "type": "leaf",
                "health": 80,
                "visibility": "public",
                "desc": plan.new_content,
                "source": "manual",
            }
        ],
    }

    parent["children"].append(new_cat)
    plan.target_node_id = leaf_id
    return tree


def _apply_modify_existing(tree: dict, plan: ModificationPlan) -> dict:
    """Replace a node's content. The plan must provide FULL replacement content."""
    if not plan.target_node_id:
        raise ValueError("modify_existing requires target_node_id")

    node = find_node(tree, plan.target_node_id)
    if not node:
        raise ValueError(f"Target node '{plan.target_node_id}' not found")

    node["desc"] = plan.new_content
    if plan.new_name:
        node["name"] = plan.new_name

    return tree


def _apply_remove(tree: dict, plan: ModificationPlan) -> dict:
    """Remove a node from the tree."""
    if not plan.target_node_id:
        raise ValueError("remove requires target_node_id")

    if plan.target_node_id == "root":
        raise ValueError("Cannot remove the root node")

    if not remove_node(tree, plan.target_node_id):
        raise ValueError(f"Node '{plan.target_node_id}' not found")

    return tree


# ---------------------------------------------------------------------------
# Phase 3: Validate — Zero Information Loss
# ---------------------------------------------------------------------------


def validate_no_info_loss(
    before_tree: dict,
    after_tree: dict,
    action: str,
) -> ValidationReport:
    """Compare before/after trees to verify no information was lost.

    For additions: after must have >= leaves and >= content chars.
    For modifications: sentence-level check on the modified node.
    For removals: explicitly allowed (user confirmed), skip sentence check.
    """
    before_leaves = count_leaves(before_tree)
    after_leaves = count_leaves(after_tree)
    before_chars = total_content_chars(before_tree)
    after_chars = total_content_chars(after_tree)

    missing: list[str] = []
    notes = ""

    if action == "remove":
        # Removal is explicitly user-confirmed, so leaf/char decrease is expected
        return ValidationReport(
            passed=True,
            before_leaf_count=before_leaves,
            after_leaf_count=after_leaves,
            before_total_chars=before_chars,
            after_total_chars=after_chars,
            notes="Node removed as requested by user.",
        )

    # For non-remove actions: check no content disappeared
    if action in ("add_to_existing", "create_leaf", "create_category"):
        # Leaf count should not decrease
        if after_leaves < before_leaves:
            missing.append(
                f"Leaf count decreased: {before_leaves} → {after_leaves}"
            )

        # Content chars should not decrease
        if after_chars < before_chars:
            missing.append(
                f"Total content decreased: {before_chars} → {after_chars} chars"
            )

    if action == "modify_existing":
        # For modifications, check that all original sentences still exist
        before_content = collect_all_content(before_tree)
        after_content = collect_all_content(after_tree)

        # Check each original leaf's sentences exist somewhere in the after tree
        after_corpus = " ".join(after_content.values()).lower()
        for node_id, content in before_content.items():
            sentences = _split_sentences(content)
            for sentence in sentences:
                # Skip very short sentences (headers, labels)
                if len(sentence.strip()) < 15:
                    continue
                if sentence.strip().lower() not in after_corpus:
                    missing.append(
                        f"Missing from node {node_id}: '{sentence[:80]}...'"
                    )
                    # Cap at 5 missing sentences to avoid noise
                    if len(missing) >= 5:
                        break
            if len(missing) >= 5:
                break

    passed = len(missing) == 0
    if not passed:
        notes = "VALIDATION FAILED — information loss detected. Tree will be rolled back."

    return ValidationReport(
        passed=passed,
        before_leaf_count=before_leaves,
        after_leaf_count=after_leaves,
        before_total_chars=before_chars,
        after_total_chars=after_chars,
        missing_sentences=missing,
        notes=notes,
    )


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences for validation."""
    # Simple sentence splitting — handles common patterns
    sentences = re.split(r"(?<=[.!?])\s+|\n\n+|\n(?=[-*#])", text)
    return [s.strip() for s in sentences if s.strip()]


# ---------------------------------------------------------------------------
# Orchestrator: full modify workflow
# ---------------------------------------------------------------------------


async def modify_tree(
    tree: dict,
    user_request: str,
    content: str = "",
    provider: str = "anthropic",
    model: str = "claude-sonnet-4-6",
) -> ModificationResult:
    """Full modification workflow: analyze → apply → validate.

    Returns ModificationResult with the updated tree or rollback on failure.
    """
    # Deep copy for before snapshot
    before_tree = copy.deepcopy(tree)
    working_tree = copy.deepcopy(tree)

    # Phase 1: Analyze & Plan
    plan = await analyze_and_plan(
        working_tree, user_request, content, provider, model
    )

    # If conflicts/duplicates require user confirmation, return early
    if plan.needs_user_confirmation:
        issues = []
        for c in plan.conflicts:
            issues.append(
                f"CONFLICT ({c.get('severity', '?')}): {c.get('description', '?')} "
                f"[node: {c.get('with_node', '?')}]"
            )
        for d in plan.duplicates:
            issues.append(
                f"DUPLICATE: {d.get('overlap_detail', '?')} "
                f"[node: {d.get('node_id', '?')}]"
            )

        return ModificationResult(
            success=False,
            action_taken="needs_confirmation",
            node_id="",
            updated_tree=before_tree,  # unchanged
            validation=ValidationReport(
                passed=True,
                before_leaf_count=count_leaves(before_tree),
                after_leaf_count=count_leaves(before_tree),
                before_total_chars=total_content_chars(before_tree),
                after_total_chars=total_content_chars(before_tree),
            ),
            summary=(
                f"Found issues that need your confirmation:\n"
                + "\n".join(f"- {i}" for i in issues)
                + f"\n\nPlacement rationale: {plan.rationale}"
                + f"\n\nPlease confirm to proceed, or provide clarification."
            ),
        )

    # Phase 2: Apply
    try:
        modified_tree = apply_modification(working_tree, plan)
    except ValueError as e:
        return ModificationResult(
            success=False,
            action_taken="error",
            node_id="",
            updated_tree=before_tree,
            validation=ValidationReport(
                passed=False,
                before_leaf_count=count_leaves(before_tree),
                after_leaf_count=count_leaves(before_tree),
                before_total_chars=total_content_chars(before_tree),
                after_total_chars=total_content_chars(before_tree),
                notes=str(e),
            ),
            summary=f"Failed to apply modification: {e}",
        )

    # Phase 3: Validate
    validation = validate_no_info_loss(before_tree, modified_tree, plan.action)

    if not validation.passed:
        logger.warning(
            f"Tree modification validation FAILED: {validation.missing_sentences}"
        )
        return ModificationResult(
            success=False,
            action_taken="rollback",
            node_id="",
            updated_tree=before_tree,  # rollback
            validation=validation,
            summary=(
                f"Modification rolled back — information loss detected:\n"
                + "\n".join(f"- {s}" for s in validation.missing_sentences[:5])
            ),
        )

    # Build summary
    node_id = plan.target_node_id or ""
    action_desc = {
        "add_to_existing": f"Appended content to '{find_node(modified_tree, node_id).get('name', node_id) if find_node(modified_tree, node_id) else node_id}'",
        "create_leaf": f"Created new leaf node '{plan.new_name or 'unnamed'}'",
        "create_category": f"Created new category '{plan.new_name or 'unnamed'}'",
        "modify_existing": f"Modified node '{find_node(modified_tree, node_id).get('name', node_id) if find_node(modified_tree, node_id) else node_id}'",
        "remove": f"Removed node '{node_id}'",
    }

    summary_parts = [action_desc.get(plan.action, plan.action)]
    summary_parts.append(f"Rationale: {plan.rationale}")

    if plan.cross_references:
        refs = ", ".join(
            f"{r.get('from_node', '?')} → {r.get('to_node', '?')}"
            for r in plan.cross_references
        )
        summary_parts.append(f"Cross-references added: {refs}")

    summary_parts.append(
        f"Validation: {validation.after_leaf_count} leaves, "
        f"{validation.after_total_chars} chars "
        f"(was {validation.before_leaf_count} leaves, {validation.before_total_chars} chars)"
    )

    return ModificationResult(
        success=True,
        action_taken=plan.action,
        node_id=node_id,
        updated_tree=modified_tree,
        validation=validation,
        summary="\n".join(summary_parts),
    )
