"""Confluence LLM tools — real implementations using ConfluenceClient.

These tools are callable by the LLM during chat sessions.
"""
from __future__ import annotations

from app.services.tools.registry import registry
from app.services.tools.tool_context import ToolContext


@registry.tool(
    name="confluence_test_connection",
    description=(
        "Test the connection to the configured Confluence instance. "
        "Call this when the user wants to verify their Confluence connection."
    ),
    module="confluence",
    requires_permission=("confluence", "connect"),
    annotations={"display": "Testing Confluence connection..."},
)
async def confluence_test_connection(ctx: ToolContext) -> str:
    from app.services.sources.confluence.client import ConfluenceClient

    try:
        client = ConfluenceClient()
        ok = await client.test_connection()
        if ok:
            return f"Successfully connected to Confluence at {client.url}"
        return "Connection test failed — could not reach Confluence."
    except ValueError as e:
        return f"Confluence not configured: {e}"
    except Exception as e:
        return f"Connection error: {e}"


@registry.tool(
    name="confluence_list_spaces",
    description=(
        "List all available Confluence spaces. Call this when the user wants "
        "to see what Confluence spaces exist."
    ),
    module="confluence",
    requires_permission=("confluence", "view"),
    annotations={"display": "Listing Confluence spaces..."},
)
async def confluence_list_spaces(ctx: ToolContext) -> str:
    from app.services.sources.confluence.client import ConfluenceClient

    try:
        client = ConfluenceClient()
        spaces = await client.list_spaces(limit=50)
        if not spaces:
            return "No Confluence spaces found."
        lines = [f"Found {len(spaces)} Confluence spaces:\n"]
        for s in spaces:
            lines.append(f"- **{s['name']}** (key: `{s['key']}`, type: {s['type']})")
        return "\n".join(lines)
    except Exception as e:
        return f"Error listing spaces: {e}"


@registry.tool(
    name="confluence_search_pages",
    description=(
        "Search for Confluence pages by keyword. Call this when the user wants "
        "to find specific pages in Confluence."
    ),
    module="confluence",
    requires_permission=("confluence", "view"),
    annotations={"display": "Searching Confluence pages..."},
)
async def confluence_search_pages(
    ctx: ToolContext, query: str = "", space_key: str = ""
) -> str:
    """Search Confluence pages.

    query: The search query text
    space_key: Optional space key to filter results (e.g. 'PROJ')
    """
    from app.services.sources.confluence.client import ConfluenceClient

    if not query:
        return "Please provide a search query."
    try:
        client = ConfluenceClient()
        results = await client.search_pages(
            query=query, space_key=space_key or None, limit=10
        )
        if not results:
            return f"No pages found for query: '{query}'"
        lines = [f"Found {len(results)} pages matching '{query}':\n"]
        for r in results:
            excerpt = r["excerpt"][:100] + "..." if len(r["excerpt"]) > 100 else r["excerpt"]
            lines.append(
                f"- **{r['title']}** (ID: {r['id']}, space: {r['space_key']})\n  {excerpt}"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"Search error: {e}"


@registry.tool(
    name="confluence_get_page",
    description=(
        "Fetch the full content of a specific Confluence page by its ID. "
        "Call this when the user wants to read a page's content."
    ),
    module="confluence",
    requires_permission=("confluence", "view"),
    annotations={"display": "Fetching Confluence page..."},
)
async def confluence_get_page(ctx: ToolContext, page_id: str = "") -> str:
    """Fetch a Confluence page.

    page_id: The numeric Confluence page ID
    """
    from app.services.sources.confluence.client import ConfluenceClient

    if not page_id:
        return "Please provide a page ID."
    try:
        client = ConfluenceClient()
        page = await client.get_page(page_id)
        content = page["content"]
        # Truncate if very long
        if len(content) > 15000:
            content = content[:15000] + "\n\n[Content truncated — page is very long]"
        return (
            f"## {page['title']}\n"
            f"Space: {page['space_name']} ({page['space_key']})\n"
            f"URL: {page['url']}\n\n"
            f"{content}"
        )
    except Exception as e:
        return f"Error fetching page {page_id}: {e}"


@registry.tool(
    name="confluence_extract_pages",
    description=(
        "Extract multiple pages from a Confluence space and save them. "
        "Call this when the user wants to pull content from a Confluence space "
        "for context generation."
    ),
    module="confluence",
    requires_permission=("confluence", "extract"),
    annotations={"display": "Extracting Confluence pages..."},
)
async def confluence_extract_pages(
    ctx: ToolContext, space_key: str = "", max_pages: int = 20
) -> str:
    """Extract pages from a Confluence space.

    space_key: The Confluence space key to extract from (e.g. 'PROJ')
    max_pages: Maximum number of pages to extract (default 20)
    """
    import uuid
    from datetime import datetime, timezone
    from app.services.sources.confluence.client import ConfluenceClient
    from app.models.source_run import ConfluenceExtraction

    if not space_key:
        return "Please provide a space_key (e.g. 'PROJ')."

    try:
        client = ConfluenceClient()

        # Get space pages
        pages = await client.get_space_pages(space_key, limit=max_pages)
        if not pages:
            return f"No pages found in space '{space_key}'."

        # Fetch each page content
        extracted = []
        for p in pages[:max_pages]:
            try:
                page = await client.get_page(p["id"])
                extracted.append(
                    {
                        "page_id": page["id"],
                        "title": page["title"],
                        "content_md": page["content"],
                        "url": page["url"],
                        "space_key": page["space_key"],
                    }
                )
            except Exception as e:
                extracted.append(
                    {"page_id": p["id"], "title": p["title"], "content_md": f"Error: {e}", "url": ""}
                )

        # Save to DB
        run_id = uuid.uuid4()
        async with ctx.get_db() as db:
            run = ConfluenceExtraction(
                id=run_id,
                user_id=ctx.user_id,
                org_id=ctx.org_id,
                space_key=space_key,
                space_name=extracted[0].get("space_key", space_key) if extracted else space_key,
                page_ids=[e["page_id"] for e in extracted],
                extracted_content=extracted,
                status="complete",
                completed_at=datetime.now(timezone.utc),
            )
            db.add(run)
            await db.commit()

        lines = [f"Successfully extracted {len(extracted)} pages from space '{space_key}':\n"]
        for e in extracted:
            preview = e["content_md"][:80] + "..." if len(e["content_md"]) > 80 else e["content_md"]
            lines.append(f"- **{e['title']}** ({len(e['content_md'])} chars)")
        lines.append(f"\nExtraction saved (run ID: {run_id})")
        return "\n".join(lines)
    except Exception as e:
        return f"Extraction error: {e}"
