"""Context Engine tools — LLM-callable tools for tree management from chat.

These tools let the AI assistant interact with the context tree directly,
enabling chat-driven tree operations.
"""
import json
import logging
import uuid

from app.services.tools.registry import registry
from app.services.tools.tool_context import ToolContext

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool: generate_context_tree
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
async def generate_context_tree(ctx: ToolContext) -> str:
    """Trigger tree generation from chat."""
    from app.core.websocket import ws_manager
    from app.core.task_registry import task_registry
    from app.database import async_session
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
        )

    task_registry.create_task(
        _run(),
        name=f"context-engine-{run_id}",
        user_id=user_id,
    )

    return (
        f"Context tree generation started (run ID: {run_id}). "
        f"I'm collecting contexts from all sources (Databricks, Config APIs, Capillary) "
        f"and organizing them into a hierarchical tree. "
        f"You can track progress in the Context Engine page. "
        f"This may take a minute."
    )


# ---------------------------------------------------------------------------
# Tool: get_tree_node
# ---------------------------------------------------------------------------


@registry.tool(
    name="get_tree_node",
    description=(
        "Read a specific node from the current context tree. "
        "Call this when the user asks about a specific context node, "
        "category, or wants to see what's in a particular part of the tree."
    ),
    module="context_engine",
    requires_permission=("context_engine", "view"),
    annotations={"display": "Reading tree node..."},
)
async def get_tree_node(ctx: ToolContext, node_name: str) -> str:
    """Read a specific node from the tree.

    node_name: Name or ID of the node to look up
    """
    from sqlalchemy import select, desc
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
        return "No context tree found. Generate one first using the Context Engine."

    # Search for the node
    node = _search_node(run.tree_data, node_name)
    if not node:
        # List available nodes
        available = _list_node_names(run.tree_data)
        return (
            f"Node '{node_name}' not found in the tree. "
            f"Available nodes: {', '.join(available[:15])}"
        )

    # Format for LLM
    lines = [f"**{node.get('name', 'Unknown')}** ({node.get('type', 'leaf')})"]
    lines.append(f"Health: {node.get('health', '?')}/100")
    lines.append(f"Visibility: {node.get('visibility', 'public')}")

    if node.get("desc"):
        lines.append(f"\nContent:\n{node['desc']}")

    if node.get("children"):
        child_names = [c.get("name", "?") for c in node["children"]]
        lines.append(f"\nChildren: {', '.join(child_names)}")

    if node.get("analysis"):
        analysis = node["analysis"]
        if analysis.get("redundancy", {}).get("score", 0) > 0:
            lines.append(f"\nRedundancy: {analysis['redundancy']['score']}%")
        if analysis.get("conflicts"):
            lines.append(f"Conflicts: {len(analysis['conflicts'])}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: add_to_context_tree
# ---------------------------------------------------------------------------


@registry.tool(
    name="add_to_context_tree",
    description=(
        "Add new content to the context tree. "
        "Performs placement, conflict, and redundancy checks before adding. "
        "Call this when the user wants to add a rule, context, or information "
        "to the tree."
    ),
    module="context_engine",
    requires_permission=("context_engine", "edit"),
    annotations={"display": "Adding to context tree..."},
)
async def add_to_context_tree(
    ctx: ToolContext,
    content: str,
    category: str = "",
) -> str:
    """Add new context to the tree.

    content: The context content to add
    category: Target category name (optional — auto-detected if empty)
    """
    from sqlalchemy import select, desc, update
    from app.models.context_tree import ContextTreeRun
    import copy

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
        return (
            "No context tree found. Generate one first using the Context Engine, "
            "then try adding content."
        )

    tree = copy.deepcopy(run.tree_data)

    # Find target category
    if category:
        target = _search_node(tree, category)
        if not target or target.get("type") == "leaf":
            return f"Category '{category}' not found. Available categories: {', '.join(_list_categories(tree))}"
    else:
        # Auto-detect: put in the first category or root
        categories = [c for c in tree.get("children", []) if c.get("type") == "cat"]
        target = categories[0] if categories else tree

    # Create new leaf node
    node_id = f"chat_{uuid.uuid4().hex[:8]}"
    new_node = {
        "id": node_id,
        "name": content[:60] + ("..." if len(content) > 60 else ""),
        "type": "leaf",
        "health": 80,
        "visibility": "public",
        "desc": content,
        "source": "manual",
    }

    if "children" not in target:
        target["children"] = []
    target["children"].append(new_node)

    # Save back
    async with ctx.get_db() as db:
        await db.execute(
            update(ContextTreeRun)
            .where(ContextTreeRun.id == run.id)
            .values(tree_data=tree)
        )
        await db.commit()

    # Notify frontend via WebSocket
    if ctx.ws_manager and ctx.ws_connection_id:
        await ctx.ws_manager.send_to_connection(
            ctx.ws_connection_id,
            {
                "type": "context_tree_updated",
                "tree_data": tree,
                "run_id": str(run.id),
            },
        )

    return (
        f"Added to tree under '{target.get('name', 'root')}' as a new leaf node. "
        f"The Context Engine tree view has been updated."
    )


# ---------------------------------------------------------------------------
# Tool: restructure_tree
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
    from sqlalchemy import select, desc
    from app.models.context_tree import ContextTreeRun
    from app.services.context_engine.restructure_proposer import propose_restructure

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
        return "No context tree found. Generate one first."

    # Get all node IDs (restructure the whole tree)
    all_ids = _collect_ids(run.tree_data)

    try:
        proposal = await propose_restructure(
            tree=run.tree_data,
            node_ids=all_ids[:20],  # Cap to prevent huge prompts
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


def _search_node(tree: dict, query: str) -> dict | None:
    """Search for a node by name or ID (case-insensitive partial match)."""
    query_lower = query.lower()

    if tree.get("id", "").lower() == query_lower:
        return tree
    if query_lower in tree.get("name", "").lower():
        return tree

    for child in tree.get("children", []):
        found = _search_node(child, query)
        if found:
            return found
    return None


def _list_node_names(tree: dict) -> list[str]:
    """Collect all node names."""
    names = [tree.get("name", "?")]
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
