"""Databricks LLM tools — callable by the AI chat assistant.

These tools allow the AI to interact with the Databricks pipeline:
list runs, view analysis results, check connection status, etc.
"""

import json
from typing import Optional

from app.services.tools.registry import registry
from app.services.tools.tool_context import ToolContext
from app.services.databricks.storage import StorageService


@registry.tool(
    name="databricks_list_extraction_runs",
    description=(
        "List all Databricks extraction runs. Call this when the user "
        "asks about their Databricks extraction history or wants to see "
        "which notebooks have been extracted."
    ),
    module="databricks",
    requires_permission=("databricks", "view"),
    annotations={"display": "Listing Databricks extraction runs..."},
)
async def databricks_list_extraction_runs(ctx: ToolContext) -> str:
    """List all extraction runs with status and counts."""
    storage = StorageService()
    runs = await storage.get_extraction_runs()

    if not runs:
        return "No Databricks extraction runs found. You can start one from the Databricks source page."

    lines = ["**Databricks Extraction Runs**\n"]
    for run in runs[:10]:
        status = run.get("status", "?")
        total_nb = run.get("total_notebooks", 0)
        valid_sq = run.get("valid_sqls", 0)
        started = run.get("started_at", "?")
        instance = run.get("databricks_instance", "?")
        run_id = run["id"]
        lines.append(
            f"- **{run_id[:8]}...** | {status} | {instance}\n"
            f"  Notebooks: {total_nb}, Valid SQLs: {valid_sq} | Started: {started}"
        )

    if len(runs) > 10:
        lines.append(f"\n*...and {len(runs) - 10} more runs*")

    return "\n".join(lines)


@registry.tool(
    name="databricks_list_analysis_runs",
    description=(
        "List all Databricks analysis runs. Call this when the user "
        "asks about their analysis history, fingerprints, or SQL patterns."
    ),
    module="databricks",
    requires_permission=("databricks", "view"),
    annotations={"display": "Listing Databricks analysis runs..."},
)
async def databricks_list_analysis_runs(ctx: ToolContext) -> str:
    """List all analysis runs with summary metadata."""
    storage = StorageService()
    runs = await storage.get_analysis_history()

    if not runs:
        return "No Databricks analysis runs found. Run an analysis after extracting notebooks."

    lines = ["**Databricks Analysis Runs**\n"]
    for run in runs[:10]:
        analysis_id = str(run.get("id", "?"))
        org_id = run.get("org_id", "?")
        version = run.get("version", 1)
        fp_count = run.get("fingerprint_count", 0)
        nb_count = run.get("notebook_count", 0)
        created = run.get("created_at", "?")
        instance = run.get("databricks_instance", "?")
        lines.append(
            f"- **{analysis_id[:8]}...** | org={org_id} | v{version}\n"
            f"  Fingerprints: {fp_count}, Notebooks: {nb_count} | {created}"
        )

    if len(runs) > 10:
        lines.append(f"\n*...and {len(runs) - 10} more runs*")

    return "\n".join(lines)


@registry.tool(
    name="databricks_get_analysis_detail",
    description=(
        "Get detailed analysis results including counters, clusters, and filters. "
        "Call this when the user asks about SQL patterns, table usage, or analysis "
        "details for a specific analysis run."
    ),
    module="databricks",
    requires_permission=("databricks", "view"),
    annotations={"display": "Fetching analysis details..."},
)
async def databricks_get_analysis_detail(
    ctx: ToolContext, analysis_id: str,
) -> str:
    """Get analysis details.
    analysis_id: UUID of the analysis run to inspect.
    """
    storage = StorageService()
    analysis = await storage.get_analysis_run(analysis_id)

    if not analysis:
        return f"Analysis run {analysis_id} not found."

    # Summary
    counters = analysis.get("counters", {})
    clusters = analysis.get("clusters", [])
    filters = analysis.get("classified_filters", {})
    total_w = analysis.get("total_weight", 0)

    # Top tables
    table_items = counters.get("table", [])
    top_tables = table_items[:15] if isinstance(table_items, list) else []

    # Top functions
    func_items = counters.get("function", [])
    top_funcs = func_items[:10] if isinstance(func_items, list) else []

    lines = [
        f"**Analysis: {analysis_id[:8]}...**",
        f"- Org: {analysis.get('org_id')}",
        f"- Total Weight: {total_w}",
        f"- Clusters: {len(clusters)}",
        f"- Classified Filters: {len(filters) if isinstance(filters, list) else 'N/A'}",
        "",
        "**Top Tables:**",
    ]
    for item in top_tables:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            lines.append(f"  - `{item[0]}` ({item[1]} uses)")

    lines.append("\n**Top Functions:**")
    for item in top_funcs:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            lines.append(f"  - `{item[0]}` ({item[1]} uses)")

    return "\n".join(lines)


@registry.tool(
    name="databricks_list_context_docs",
    description=(
        "List generated context documents for a Databricks analysis. "
        "Call this when the user asks about their generated context docs, "
        "or wants to see what documents exist."
    ),
    module="databricks",
    requires_permission=("databricks", "view"),
    annotations={"display": "Listing context documents..."},
)
async def databricks_list_context_docs(
    ctx: ToolContext, analysis_id: str,
) -> str:
    """List context docs for an analysis.
    analysis_id: UUID of the analysis run whose docs to list.
    """
    storage = StorageService()
    docs = await storage.get_context_docs(analysis_id)

    if not docs:
        return f"No context documents found for analysis {analysis_id}. Generate docs first."

    lines = [f"**Context Documents for {analysis_id[:8]}...**\n"]
    for doc in docs:
        key = doc.get("doc_key", "?")
        name = doc.get("doc_name", "?")
        tokens = doc.get("token_count", 0)
        model = doc.get("model_used", "?")
        created = doc.get("created_at", "?")
        lines.append(
            f"- **{key}** — {name}\n"
            f"  Tokens: ~{tokens} | Model: {model} | {created}"
        )

    return "\n".join(lines)


@registry.tool(
    name="databricks_get_context_doc",
    description=(
        "Get the full content of a specific context document. "
        "Call this when the user wants to read or review a generated context document."
    ),
    module="databricks",
    requires_permission=("databricks", "view"),
    annotations={"display": "Fetching context document..."},
)
async def databricks_get_context_doc(
    ctx: ToolContext, doc_id: int,
) -> str:
    """Get a context document by ID.
    doc_id: Integer ID of the context document.
    """
    storage = StorageService()
    doc = await storage.get_context_doc(doc_id)

    if not doc:
        return f"Context document {doc_id} not found."

    content = doc.get("doc_content", "")
    key = doc.get("doc_key", "?")
    name = doc.get("doc_name", "?")

    # Truncate if very long (keep first 3000 chars for chat context)
    if len(content) > 3000:
        content = content[:3000] + "\n\n... (truncated — view full document in the UI)"

    return f"**{key} — {name}**\n\n{content}"


@registry.tool(
    name="databricks_storage_stats",
    description=(
        "Show storage statistics for the Databricks pipeline — row counts "
        "for extraction runs, extracted SQLs, analysis runs, fingerprints, "
        "and context documents."
    ),
    module="databricks",
    requires_permission=("databricks", "view"),
    annotations={"display": "Checking Databricks storage stats..."},
)
async def databricks_storage_stats(ctx: ToolContext) -> str:
    """Get row counts for all Databricks pipeline tables."""
    storage = StorageService()
    stats = await storage.get_storage_stats()

    lines = ["**Databricks Pipeline Storage**\n"]
    for table, count in stats.items():
        lines.append(f"- {table}: {count:,} rows")

    return "\n".join(lines)
