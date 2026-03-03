"""Context Engine tools — LLM-callable tools for tree management from chat.

These tools let the AI assistant interact with the context tree directly,
enabling chat-driven tree operations with intelligent placement and
zero information loss validation.
"""
import base64
import copy
import json
import logging
import uuid

import httpx
from sqlalchemy import select, desc, update

from app.services.tools.registry import registry
from app.services.tools.tool_context import ToolContext

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


async def _save_tree(ctx: ToolContext, run_id, tree_data: dict):
    """Save updated tree to DB and notify frontend via WebSocket."""
    from app.models.context_tree import ContextTreeRun

    async with ctx.get_db() as db:
        await db.execute(
            update(ContextTreeRun)
            .where(ContextTreeRun.id == run_id)
            .values(tree_data=tree_data)
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
        "Returns a compact view with node names, types, health scores, and content previews. "
        "Use include_content=true for full content of a specific node. "
        "Call this to understand the tree BEFORE making modifications."
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
        "Intelligently add, modify, or update content in the context tree. "
        "Analyzes the tree, checks for conflicts and duplicates, decides optimal "
        "placement, and validates zero information loss. "
        "Call this when the user wants to add a rule, update existing context, "
        "or make any content change to the tree."
    ),
    module="context_engine",
    requires_permission=("context_engine", "edit"),
    annotations={"display": "Analyzing tree for modification..."},
)
async def modify_context_tree(
    ctx: ToolContext,
    user_request: str,
    content: str = "",
) -> str:
    """Intelligently modify the context tree.

    user_request: What the user wants to do (e.g. "add a rule that says always use UTC")
    content: The specific context content to add or modify (optional — LLM infers if empty)
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
    )

    if not result.success:
        if result.action_taken == "needs_confirmation":
            # Conflicts/duplicates found — return issues for user to review
            return result.summary
        # Other errors
        return f"Modification failed: {result.summary}"

    # Save the updated tree
    await _save_tree(ctx, run.id, result.updated_tree)

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

    await _save_tree(ctx, run.id, tree)

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
    """Save a checkpoint of the current tree state.

    label: Optional label for the checkpoint (e.g. "Before adding UTC rules")
    """
    from app.models.context_tree_checkpoint import ContextTreeCheckpoint
    from app.services.context_engine.tree_modifier import count_leaves, total_content_chars

    try:
        run, tree = await _load_latest_tree(ctx)
    except ValueError as e:
        return str(e)

    leaf_count = count_leaves(tree)
    char_count = total_content_chars(tree)

    # Auto-generate label if not provided
    if not label:
        async with ctx.get_db() as db:
            count_result = await db.execute(
                select(ContextTreeCheckpoint)
                .where(ContextTreeCheckpoint.run_id == run.id)
            )
            existing = len(count_result.scalars().all())
        label = f"Checkpoint #{existing + 1}"

    checkpoint = ContextTreeCheckpoint(
        id=uuid.uuid4(),
        run_id=run.id,
        user_id=ctx.user_id,
        org_id=ctx.org_id,
        label=label,
        tree_data=tree,
        node_count=leaf_count + _count_categories(tree),
        leaf_count=leaf_count,
        health_score=tree.get("health", 0),
    )

    async with ctx.get_db() as db:
        db.add(checkpoint)
        await db.commit()

    return (
        f"Checkpoint saved: **{label}**\n"
        f"- {leaf_count} leaves, {char_count:,} chars\n"
        f"- Health: {tree.get('health', '?')}/100\n"
        f"You can restore this checkpoint from the Version History panel."
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
        "Use this when the user wants to merge, split, reorganize, "
        "or optimize parts of the tree."
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
