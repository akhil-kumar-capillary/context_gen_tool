"""Context Engine tools — LLM-callable tools for tree management from chat.

These tools let the AI assistant interact with the context tree directly,
enabling chat-driven tree operations with intelligent placement and
zero information loss validation.
"""
import base64
import bisect
import copy
import json
import logging
import re
import uuid

import httpx
from sqlalchemy import select, desc, update

from app.services.tools.registry import registry
from app.services.tools.tool_context import ToolContext
from app.utils import utcnow

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helper: load the latest completed tree run
# ---------------------------------------------------------------------------


async def _load_latest_tree(ctx: ToolContext):
    """Load the latest completed ContextTreeRun for the current org.

    Returns (run, tree_data) or raises ValueError.
    """
    from app.models.context_tree import ContextTreeRun

    async with ctx.get_db() as db:
        result = await db.execute(
            select(ContextTreeRun)
            .where(
                ContextTreeRun.org_id == ctx.org_id,
                ContextTreeRun.status == "completed",
            )
            .order_by(desc(ContextTreeRun.created_at))
            .limit(1)
        )
        run = result.scalar_one_or_none()

    if not run or not run.tree_data:
        raise ValueError(
            "No context tree found. Generate one first using the Context Engine."
        )
    return run, run.tree_data


async def _save_tree(
    ctx: ToolContext,
    run_id,
    tree_data: dict,
    *,
    change_type: str = "update",
    change_summary: str = "Tree updated via chat",
):
    """Save updated tree to DB with version record and notify frontend."""
    from app.models.context_tree import ContextTreeRun
    from app.services.versioning import create_version

    async with ctx.get_db() as db:
        # Fetch previous tree for version snapshot (with org_id guard)
        result = await db.execute(
            select(ContextTreeRun.tree_data)
            .where(
                ContextTreeRun.id == run_id,
                ContextTreeRun.org_id == ctx.org_id,
            )
        )
        previous_tree = result.scalar_one_or_none()

        # Update tree (with org_id guard)
        await db.execute(
            update(ContextTreeRun)
            .where(
                ContextTreeRun.id == run_id,
                ContextTreeRun.org_id == ctx.org_id,
            )
            .values(tree_data=tree_data, updated_at=utcnow())
        )

        # Create version record (same transaction)
        await create_version(
            db,
            entity_type="context_tree",
            entity_id=str(run_id),
            org_id=ctx.org_id,
            snapshot=tree_data,
            previous_snapshot=previous_tree,
            change_type=change_type,
            change_summary=change_summary,
            changed_fields=["tree_data"],
            user_id=ctx.user_id,
        )
        await db.commit()

    # Notify frontend
    if ctx.ws_manager and ctx.ws_connection_id:
        await ctx.ws_manager.send_to_connection(
            ctx.ws_connection_id,
            {
                "type": "context_tree_updated",
                "tree_data": tree_data,
                "run_id": str(run_id),
            },
        )


# ---------------------------------------------------------------------------
# Tool: generate_context_tree (kept from original)
# ---------------------------------------------------------------------------


@registry.tool(
    name="generate_context_tree",
    description=(
        "Generate a context tree that organizes ALL context documents for "
        "the current organization into an intelligent hierarchical structure. "
        "This collects contexts from Databricks, Config APIs, and Capillary, "
        "then uses LLM to build a tree with categories, health scores, and analysis. "
        "Call this when the user asks to organize, structure, or build a context tree."
    ),
    module="context_engine",
    requires_permission=("context_engine", "generate"),
    annotations={"display": "Generating context tree..."},
)
async def generate_context_tree(ctx: ToolContext, sanitize: bool = False) -> str:
    """Trigger tree generation from chat.

    sanitize: Whether to run content sanitization via blueprint (default: False).
              When True, the tree builder skips attaching original content and instead
              sends all contexts through the blueprint LLM for cleanup first.
    """
    from app.core.websocket import ws_manager
    from app.core.task_registry import task_registry
    from app.models.context_tree import ContextTreeRun

    run_id = str(uuid.uuid4())
    user_id = ctx.user_id
    org_id = ctx.org_id

    # Create the run record
    async with ctx.get_db() as db:
        run = ContextTreeRun(
            id=uuid.UUID(run_id),
            user_id=user_id,
            org_id=org_id,
            status="running",
        )
        db.add(run)
        await db.commit()

    # Launch background task
    async def _run():
        from app.services.context_engine.orchestrator import run_tree_generation
        await run_tree_generation(
            run_id=run_id,
            user=ctx.user,
            org_id=org_id,
            ws_manager=ws_manager,
            user_id=user_id,
            sanitize=sanitize,
        )

    task_registry.create_task(
        _run(),
        name=f"context-engine-{run_id}",
        user_id=user_id,
    )

    sanitize_note = " with content sanitization enabled" if sanitize else ""
    return (
        f"Context tree generation started{sanitize_note} (run ID: {run_id}). "
        f"I'm collecting contexts from all sources (Databricks, Config APIs, Capillary) "
        f"and organizing them into a hierarchical tree. "
        f"You can track progress in the Context Engine page. "
        f"This may take a minute."
    )


# ---------------------------------------------------------------------------
# Tool: read_context_tree
# ---------------------------------------------------------------------------


@registry.tool(
    name="read_context_tree",
    description=(
        "Read the full context tree structure or a specific node. "
        "Returns a compact view with node names, types, health scores, and content previews (200 chars). "
        "Use include_content=true for full content of a SPECIFIC node (can be large). "
        "For targeted searches within content, use grep_context_tree instead. "
        "Call this to understand the tree structure BEFORE making modifications."
    ),
    module="context_engine",
    requires_permission=("context_engine", "view"),
    annotations={"display": "Reading context tree..."},
)
async def read_context_tree(
    ctx: ToolContext,
    node_id: str = "",
    include_content: bool = False,
) -> str:
    """Read the context tree or a specific node.

    node_id: ID of a specific node to read (empty = full tree overview)
    include_content: If true, include full desc content for leaf nodes
    """
    from app.services.context_engine.tree_modifier import (
        compact_tree_for_llm,
        find_node,
        count_leaves,
    )

    try:
        run, tree = await _load_latest_tree(ctx)
    except ValueError as e:
        return str(e)

    # If a specific node is requested
    if node_id:
        node = find_node(tree, node_id)
        if not node:
            # List available nodes
            names = _list_node_names(tree)
            return (
                f"Node '{node_id}' not found. "
                f"Available nodes: {', '.join(names[:20])}"
            )

        lines = [f"**{node.get('name', '?')}** ({node.get('type', 'leaf')})"]
        lines.append(f"ID: {node.get('id', '?')}")
        lines.append(f"Health: {node.get('health', '?')}/100")
        lines.append(f"Visibility: {node.get('visibility', 'public')}")

        if include_content and node.get("desc"):
            lines.append(f"\n**Content:**\n{node['desc']}")
        elif node.get("desc"):
            preview = node["desc"][:300]
            lines.append(f"\n**Preview:** {preview}{'...' if len(node['desc']) > 300 else ''}")

        if node.get("children"):
            child_info = [
                f"  - {c.get('name', '?')} ({c.get('type', '?')}, health={c.get('health', '?')})"
                for c in node["children"]
            ]
            lines.append(f"\n**Children ({len(node['children'])}):**")
            lines.extend(child_info)

        if node.get("analysis"):
            analysis = node["analysis"]
            if analysis.get("redundancy", {}).get("score", 0) > 0:
                lines.append(f"\nRedundancy: {analysis['redundancy']['score']}%")
            if analysis.get("conflicts"):
                for c in analysis["conflicts"]:
                    lines.append(
                        f"Conflict ({c.get('severity', '?')}): {c.get('description', '?')}"
                    )

        return "\n".join(lines)

    # Full tree overview
    compact = compact_tree_for_llm(tree)
    leaf_count = count_leaves(tree)
    return (
        f"**Context Tree** ({leaf_count} leaves, run: {run.id})\n\n"
        f"{compact}"
    )


# ---------------------------------------------------------------------------
# Tool: modify_context_tree (intelligent replacement for add_to_context_tree)
# ---------------------------------------------------------------------------


@registry.tool(
    name="modify_context_tree",
    description=(
        "Intelligently add, modify, or update content in the context TREE (not Capillary context documents). "
        "Analyzes the tree, checks for conflicts and duplicates, decides optimal "
        "placement, and validates zero information loss. "
        "IMPORTANT: For modify/edit/remove operations on existing nodes, ALWAYS set "
        "target_node_id to the node's ID. Use grep_context_tree or read_context_tree "
        "to find the node ID first. This gives the planner full content visibility "
        "for precise surgical edits instead of error-prone full-document rewrites. "
        "For adding new content, target_node_id is optional (the planner will choose placement)."
    ),
    module="context_engine",
    requires_permission=("context_engine", "edit"),
    annotations={"display": "Analyzing tree for modification..."},
)
async def modify_context_tree(
    ctx: ToolContext,
    user_request: str,
    content: str = "",
    target_node_id: str = "",
) -> str:
    """Intelligently modify the context tree.

    user_request: What the user wants to do (e.g. "add a rule that says always use UTC")
    content: The specific context content to add or modify (optional — LLM infers if empty)
    target_node_id: ID of the node to modify (optional — provides full content visibility
        to the planner for surgical edits). ALWAYS set this for edit/modify/remove operations.
    """
    from app.services.context_engine.tree_modifier import modify_tree

    try:
        run, tree = await _load_latest_tree(ctx)
    except ValueError as e:
        return str(e)

    # Run the full modification workflow
    result = await modify_tree(
        tree=tree,
        user_request=user_request,
        content=content,
        target_node_id_hint=target_node_id or None,
    )

    if not result.success:
        if result.action_taken == "needs_confirmation":
            # Conflicts/duplicates found — return issues for user to review
            return result.summary
        # Other errors
        return f"Modification failed: {result.summary}"

    # Save the updated tree
    await _save_tree(
        ctx, run.id, result.updated_tree,
        change_type="update",
        change_summary=f"Chat: {user_request[:100]}",
    )

    return (
        f"Tree modified successfully.\n\n{result.summary}\n\n"
        f"The Context Engine tree view has been updated."
    )


# ---------------------------------------------------------------------------
# Tool: remove_from_context_tree
# ---------------------------------------------------------------------------


@registry.tool(
    name="remove_from_context_tree",
    description=(
        "Remove a node from the context tree. Use ONLY when the user explicitly "
        "asks to delete or remove specific context. Shows what will be lost "
        "and requires confirmation before proceeding."
    ),
    module="context_engine",
    requires_permission=("context_engine", "edit"),
    annotations={"display": "Preparing removal..."},
)
async def remove_from_context_tree(
    ctx: ToolContext,
    node_id: str,
    confirmed: bool = False,
) -> str:
    """Remove a node from the tree.

    node_id: ID of the node to remove
    confirmed: Set to true after user confirms. First call shows what will be removed.
    """
    from app.services.context_engine.tree_modifier import (
        find_node,
        remove_node,
        count_leaves,
        total_content_chars,
        validate_no_info_loss,
    )

    try:
        run, tree = await _load_latest_tree(ctx)
    except ValueError as e:
        return str(e)

    node = find_node(tree, node_id)
    if not node:
        return f"Node '{node_id}' not found in the tree."

    if node_id == "root":
        return "Cannot remove the root node."

    # First call: preview what will be removed
    if not confirmed:
        child_count = count_leaves(node) if node.get("children") else 0
        desc_preview = (node.get("desc", ""))[:200]
        return (
            f"**About to remove:** {node.get('name', '?')} ({node.get('type', '?')})\n"
            f"Content preview: {desc_preview}{'...' if len(node.get('desc', '')) > 200 else ''}\n"
            f"{'Children: ' + str(child_count) + ' leaf nodes' if child_count else ''}\n\n"
            f"This action will permanently remove this content from the tree. "
            f"Call this tool again with confirmed=true to proceed."
        )

    # Confirmed: actually remove
    import copy
    before = copy.deepcopy(tree)

    if not remove_node(tree, node_id):
        return f"Failed to remove node '{node_id}'."

    validation = validate_no_info_loss(before, tree, "remove")

    await _save_tree(
        ctx, run.id, tree,
        change_type="delete_node",
        change_summary=f"Chat: removed '{node.get('name', node_id)}'",
    )

    return (
        f"Removed '{node.get('name', node_id)}' from the tree.\n"
        f"Before: {validation.before_leaf_count} leaves, {validation.before_total_chars} chars\n"
        f"After: {validation.after_leaf_count} leaves, {validation.after_total_chars} chars\n"
        f"The tree has been updated."
    )


# ---------------------------------------------------------------------------
# Tool: save_tree_checkpoint
# ---------------------------------------------------------------------------


@registry.tool(
    name="save_tree_checkpoint",
    description=(
        "Save a checkpoint (version) of the current context tree state. "
        "Creates a snapshot that can be restored later. "
        "Call this when the user asks to save, checkpoint, or version the tree."
    ),
    module="context_engine",
    requires_permission=("context_engine", "edit"),
    annotations={"display": "Saving checkpoint..."},
)
async def save_tree_checkpoint(
    ctx: ToolContext,
    label: str = "",
) -> str:
    """Save a version snapshot of the current tree state.

    label: Optional label for the snapshot (e.g. "Before adding UTC rules")
    """
    from app.services.versioning import create_version
    from app.services.context_engine.tree_modifier import count_leaves, total_content_chars

    try:
        run, tree = await _load_latest_tree(ctx)
    except ValueError as e:
        return str(e)

    leaf_count = count_leaves(tree)
    char_count = total_content_chars(tree)
    summary = label or "Manual snapshot via chat"

    async with ctx.get_db() as db:
        await create_version(
            db,
            entity_type="context_tree",
            entity_id=str(run.id),
            org_id=ctx.org_id,
            snapshot=tree,
            previous_snapshot=None,
            change_type="update",
            change_summary=summary,
            changed_fields=["tree_data"],
            user_id=ctx.user_id,
        )
        await db.commit()

    return (
        f"Version saved: **{summary}**\n"
        f"- {leaf_count} leaves, {char_count:,} chars\n"
        f"- Health: {tree.get('health', '?')}/100\n"
        f"You can restore this version from the Version History panel."
    )


# ---------------------------------------------------------------------------
# Tool: sync_tree_to_capillary
# ---------------------------------------------------------------------------


@registry.tool(
    name="sync_tree_to_capillary",
    description=(
        "Upload all public leaf nodes from the context tree to Capillary as "
        "context documents. This syncs the entire tree to the Capillary platform. "
        "Call this when the user explicitly asks to sync, push, or upload the tree."
    ),
    module="context_engine",
    requires_permission=("context_engine", "sync"),
    annotations={"display": "Syncing to Capillary..."},
)
async def sync_tree_to_capillary(ctx: ToolContext) -> str:
    """Sync all public leaf nodes to Capillary."""
    try:
        run, tree = await _load_latest_tree(ctx)
    except ValueError as e:
        return str(e)

    # Collect all public leaves
    leaves: list[dict] = []
    _collect_leaves(tree, leaves)
    public_leaves = [l for l in leaves if l.get("visibility", "public") == "public"]

    if not public_leaves:
        return "No public leaf nodes found in the tree to sync."

    headers = ctx.capillary_headers()
    headers["Content-Type"] = "application/x-www-form-urlencoded"

    results = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        for leaf in public_leaves:
            name = leaf.get("name", "Unnamed")
            content = leaf.get("desc", "")
            if not content:
                results.append({"name": name, "status": "skipped", "reason": "empty"})
                continue

            encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")
            try:
                resp = await client.post(
                    f"{ctx.base_url}/ask-aira/context/upload_context",
                    headers=headers,
                    data={"name": name, "context": encoded, "scope": "org"},
                )
                if resp.is_success:
                    results.append({"name": name, "status": "uploaded"})
                else:
                    results.append({"name": name, "status": "failed", "reason": f"HTTP {resp.status_code}"})
            except Exception as e:
                results.append({"name": name, "status": "failed", "reason": str(e)})

    uploaded = sum(1 for r in results if r["status"] == "uploaded")
    failed = sum(1 for r in results if r["status"] == "failed")
    skipped = sum(1 for r in results if r["status"] == "skipped")

    summary = f"Sync complete: {uploaded} uploaded, {failed} failed, {skipped} skipped out of {len(public_leaves)} public leaves."

    if failed > 0:
        failures = [r for r in results if r["status"] == "failed"]
        summary += "\n\nFailed:\n" + "\n".join(
            f"- {f['name']}: {f.get('reason', '?')}" for f in failures[:5]
        )

    return summary


# ---------------------------------------------------------------------------
# Tool: restructure_tree (kept from original)
# ---------------------------------------------------------------------------


@registry.tool(
    name="restructure_tree",
    description=(
        "Ask LLM to restructure part of the context tree. "
        "Use this for STRUCTURAL changes: merge, split, reorganize, or optimize tree categories. "
        "NOT for content edits — use modify_context_tree for content changes. "
        "Note: works best with trees under 20 nodes; for larger trees, specify the section."
    ),
    module="context_engine",
    requires_permission=("context_engine", "edit"),
    annotations={"display": "Restructuring tree..."},
)
async def restructure_tree(ctx: ToolContext, instruction: str) -> str:
    """Ask LLM to restructure the tree.

    instruction: What to do — e.g. "merge analytics categories", "split testing", "reorganize"
    """
    from app.services.context_engine.restructure_proposer import propose_restructure

    try:
        run, tree = await _load_latest_tree(ctx)
    except ValueError as e:
        return str(e)

    all_ids = _collect_ids(tree)

    try:
        proposal = await propose_restructure(
            tree=tree,
            node_ids=all_ids[:20],
            instruction=instruction,
        )
    except ValueError as e:
        return f"Restructure failed: {e}"

    return (
        f"**Restructure Proposal:**\n\n"
        f"Before: {proposal['before']}\n"
        f"After: {proposal['after']}\n"
        f"Health impact: {proposal['health_before']} → {proposal['health_after']} "
        f"({proposal['health_impact']})\n\n"
        f"This proposal needs your approval. Go to the Context Engine page to review and apply it."
    )


# ---------------------------------------------------------------------------
# Tool: grep_context_tree
# ---------------------------------------------------------------------------

TREE_TOOL_OUTPUT_LIMIT = 15000


def _grep_in_content(
    text: str,
    pattern: str,
    n_lines_before: int = 3,
    n_lines_after: int = 3,
) -> str:
    """Grep within a text string, returning matching lines with context.

    Uses bisect for O(log n) line lookups — same algorithm as cap-ai-readiness.
    Returns formatted output with line numbers, or empty string if no matches.
    """
    lines = text.splitlines()
    if not lines:
        return ""

    # Build index of line start positions for O(log n) line lookup
    line_starts = [0]
    for i, c in enumerate(text):
        if c == "\n":
            line_starts.append(i + 1)

    hit_lines: set[int] = set()
    try:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            line_idx = bisect.bisect_right(line_starts, m.start()) - 1
            for offset in range(-n_lines_before, n_lines_after + 1):
                idx = line_idx + offset
                if 0 <= idx < len(lines):
                    hit_lines.add(idx)
    except re.error as e:
        return f"Invalid regex pattern: {e}"

    if not hit_lines:
        return ""

    # Format with line numbers — add separators between non-contiguous blocks
    result_lines: list[str] = []
    sorted_hits = sorted(hit_lines)
    prev_idx = -2
    for idx in sorted_hits:
        if idx > prev_idx + 1 and result_lines:
            result_lines.append("  ---")
        result_lines.append(f"{idx + 1:4d} | {lines[idx]}")
        prev_idx = idx

    return "\n".join(result_lines)


@registry.tool(
    name="grep_context_tree",
    description=(
        "Search within context tree node content using a regex pattern. "
        "Returns matching lines with surrounding context (like grep -C). "
        "Use this to find specific sections, rules, or patterns within large nodes "
        "BEFORE modifying them. If node_id is empty, searches ALL leaf nodes."
    ),
    module="context_engine",
    requires_permission=("context_engine", "view"),
    annotations={"display": "Searching tree content..."},
)
async def grep_context_tree(
    ctx: ToolContext,
    pattern: str,
    node_id: str = "",
    context_lines: int = 3,
) -> str:
    """Search within tree content using regex.

    pattern: Regex pattern to search for (case-insensitive)
    node_id: Node to search in (empty = search all leaf nodes)
    context_lines: Number of context lines before/after each match (default 3)
    """
    from app.services.context_engine.tree_modifier import find_node

    try:
        _run, tree = await _load_latest_tree(ctx)
    except ValueError as e:
        return str(e)

    results: list[str] = []
    total_len = 0

    if node_id:
        # Search specific node
        node = find_node(tree, node_id)
        if not node:
            names = _list_node_names(tree)
            return (
                f"Node '{node_id}' not found. "
                f"Available nodes: {', '.join(names[:20])}"
            )
        content = node.get("desc", "")
        if not content:
            return f"Node '{node_id}' has no content."

        grep_output = _grep_in_content(content, pattern, context_lines, context_lines)
        if not grep_output:
            return f"No matches for `{pattern}` in node '{node_id}'."

        results.append(
            f"**{node.get('name', '?')}** (id: {node_id})\n{grep_output}"
        )
    else:
        # Search all leaf nodes
        leaves: list[dict] = []
        _collect_leaves(tree, leaves)

        for leaf in leaves:
            content = leaf.get("desc", "")
            if not content:
                continue

            grep_output = _grep_in_content(content, pattern, context_lines, context_lines)
            if not grep_output:
                continue

            block = (
                f"**{leaf.get('name', '?')}** (id: {leaf.get('id', '?')})\n"
                f"{grep_output}"
            )
            total_len += len(block)
            results.append(block)

            if total_len > TREE_TOOL_OUTPUT_LIMIT:
                results.append(
                    f"\n...output truncated. Searched {len(leaves)} leaves. "
                    f"Use node_id parameter to search a specific node."
                )
                break

    if not results:
        return f"No matches for `{pattern}` in any tree node."

    return "\n\n".join(results)


# ---------------------------------------------------------------------------
# Tool: read_tree_node_content
# ---------------------------------------------------------------------------


@registry.tool(
    name="read_tree_node_content",
    description=(
        "Read the content of a specific tree node with line numbers. "
        "Supports reading a specific line range (start_line to end_line). "
        "Use this after grep_context_tree to read the full context around a match. "
        "Output is capped at 15000 chars — use line ranges for large nodes."
    ),
    module="context_engine",
    requires_permission=("context_engine", "view"),
    annotations={"display": "Reading node content..."},
)
async def read_tree_node_content(
    ctx: ToolContext,
    node_id: str,
    start_line: int = 1,
    end_line: int = -1,
) -> str:
    """Read node content with line numbers.

    node_id: ID of the node to read
    start_line: First line to include (1-based, default: 1)
    end_line: Last line to include (-1 = end of content)
    """
    from app.services.context_engine.tree_modifier import find_node

    try:
        _run, tree = await _load_latest_tree(ctx)
    except ValueError as e:
        return str(e)

    node = find_node(tree, node_id)
    if not node:
        names = _list_node_names(tree)
        return (
            f"Node '{node_id}' not found. "
            f"Available nodes: {', '.join(names[:20])}"
        )

    content = node.get("desc", "")
    if not content:
        return f"Node '{node_id}' has no content."

    lines = content.splitlines()
    total_lines = len(lines)

    # Normalize range (1-based → 0-based)
    start_idx = max(0, start_line - 1)
    end_idx = total_lines if end_line == -1 else min(end_line, total_lines)

    if start_idx >= total_lines:
        return f"start_line {start_line} is beyond content ({total_lines} lines)."

    selected = lines[start_idx:end_idx]

    # Format with line numbers
    output_lines: list[str] = [
        f"**{node.get('name', '?')}** (lines {start_idx + 1}\u2013{start_idx + len(selected)} of {total_lines})"
    ]
    total_len = len(output_lines[0])

    for i, line in enumerate(selected):
        numbered = f"{start_idx + i + 1:4d} | {line}"
        total_len += len(numbered) + 1
        if total_len > TREE_TOOL_OUTPUT_LIMIT:
            output_lines.append(
                f"\n...output truncated at line {start_idx + i + 1}. "
                f"Use start_line/end_line to read specific ranges."
            )
            break
        output_lines.append(numbered)

    return "\n".join(output_lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _list_node_names(tree: dict) -> list[str]:
    """Collect all node names."""
    names = [f"{tree.get('name', '?')} ({tree.get('id', '?')})"]
    for child in tree.get("children", []):
        names.extend(_list_node_names(child))
    return names


def _list_categories(tree: dict) -> list[str]:
    """Collect category names."""
    names = []
    if tree.get("type") == "cat":
        names.append(tree.get("name", "?"))
    for child in tree.get("children", []):
        names.extend(_list_categories(child))
    return names


def _collect_ids(node: dict) -> list[str]:
    """Collect all node IDs."""
    ids = [node.get("id", "")]
    for child in node.get("children", []):
        ids.extend(_collect_ids(child))
    return [i for i in ids if i]


def _collect_leaves(node: dict, leaves: list):
    """Recursively collect all leaf nodes."""
    if node.get("type") == "leaf":
        leaves.append(node)
    for child in node.get("children", []):
        _collect_leaves(child, leaves)


def _count_categories(tree: dict) -> int:
    """Count category nodes."""
    count = 1 if tree.get("type") == "cat" else 0
    for child in tree.get("children", []):
        count += _count_categories(child)
    return count
