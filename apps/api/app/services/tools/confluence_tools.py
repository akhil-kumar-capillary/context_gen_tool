"""Confluence tool stubs — registered so the LLM knows they exist.

These will be fully implemented in Phase 4.
"""
from app.services.tools.registry import registry
from app.services.tools.tool_context import ToolContext


@registry.tool(
    name="confluence_test_connection",
    description=(
        "Test the connection to a Confluence instance. Call this when the user "
        "wants to verify their Confluence connection."
    ),
    module="confluence",
    requires_permission=("confluence", "connect"),
    annotations={"display": "Testing Confluence connection..."},
)
async def confluence_test_connection(ctx: ToolContext) -> str:
    return (
        "The Confluence integration is currently being set up and will be available soon. "
        "It will allow you to extract documentation from Confluence spaces and convert "
        "them into context documents."
    )


@registry.tool(
    name="confluence_extract_pages",
    description=(
        "Extract pages from a Confluence space. Call this when the user wants to "
        "pull content from Confluence for context generation."
    ),
    module="confluence",
    requires_permission=("confluence", "extract"),
    annotations={"display": "Extracting Confluence pages..."},
)
async def confluence_extract_pages(ctx: ToolContext, space_key: str = "") -> str:
    """Extract pages from Confluence.

    space_key: The Confluence space key to extract from
    """
    return (
        "Confluence page extraction is not yet available. This feature will allow you to "
        "extract and convert Confluence documentation into context documents."
    )
