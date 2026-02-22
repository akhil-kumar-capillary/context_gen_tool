"""Databricks tool stubs — registered so the LLM knows they exist.

These will be fully implemented in Phase 3. For now they return informational messages.
"""
from app.services.tools.registry import registry
from app.services.tools.tool_context import ToolContext


@registry.tool(
    name="databricks_test_connection",
    description=(
        "Test the connection to a Databricks workspace. Call this when the user "
        "wants to verify their Databricks connection is working."
    ),
    module="databricks",
    requires_permission=("databricks", "connect"),
    annotations={"display": "Testing Databricks connection..."},
)
async def databricks_test_connection(ctx: ToolContext) -> str:
    return (
        "The Databricks integration is currently being set up and will be available soon. "
        "It will allow you to connect to Databricks workspaces, extract SQL queries, "
        "and auto-generate context documents from your data."
    )


@registry.tool(
    name="databricks_start_extraction",
    description=(
        "Start extracting SQL notebooks and queries from a Databricks workspace. "
        "Call this when the user wants to extract Databricks content for context generation."
    ),
    module="databricks",
    requires_permission=("databricks", "extract"),
    annotations={"display": "Starting Databricks extraction..."},
)
async def databricks_start_extraction(ctx: ToolContext) -> str:
    return (
        "Databricks extraction is not yet available. This feature will allow you to "
        "automatically extract SQL notebooks and queries from your Databricks workspace."
    )


@registry.tool(
    name="databricks_list_runs",
    description=(
        "List all Databricks extraction and analysis runs. Call this when the user "
        "wants to see the history of Databricks operations."
    ),
    module="databricks",
    requires_permission=("databricks", "view"),
    annotations={"display": "Listing Databricks runs..."},
)
async def databricks_list_runs(ctx: ToolContext) -> str:
    return "Databricks run history is not yet available. This feature is coming soon."


@registry.tool(
    name="databricks_start_analysis",
    description=(
        "Start analyzing extracted Databricks SQL to identify patterns, filters, "
        "and business logic. Call this after extraction is complete."
    ),
    module="databricks",
    requires_permission=("databricks", "analyze"),
    annotations={"display": "Starting Databricks analysis..."},
)
async def databricks_start_analysis(ctx: ToolContext) -> str:
    return (
        "Databricks analysis is not yet available. This feature will analyze "
        "your extracted SQL to identify table usage patterns, common filters, "
        "and business logic for context document generation."
    )


@registry.tool(
    name="databricks_generate_docs",
    description=(
        "Generate context documents from Databricks analysis results. "
        "Call this when the user wants to create context docs from Databricks data."
    ),
    module="databricks",
    requires_permission=("databricks", "generate"),
    annotations={"display": "Generating context docs from Databricks..."},
)
async def databricks_generate_docs(ctx: ToolContext) -> str:
    return (
        "Databricks document generation is not yet available. This feature will "
        "use LLM to generate structured context documents from the analysis results."
    )
