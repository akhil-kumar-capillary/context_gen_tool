"""Context management tools — LLM-callable tools for CRUD operations on context documents.

These wrap the Capillary context API proxying logic (same as routers/contexts.py)
but return formatted strings suitable for LLM consumption.
"""
import base64
import json
import logging
from pathlib import Path

import httpx

from app.services.tools.registry import registry
from app.services.tools.tool_context import ToolContext
from app.config import settings

logger = logging.getLogger(__name__)

BLUEPRINT_PATH = Path(__file__).parent.parent.parent / "resources" / "blueprint.md"


# ---------------------------------------------------------------------------
# Tool: list_contexts
# ---------------------------------------------------------------------------


@registry.tool(
    name="list_contexts",
    description=(
        "List all context documents for the current organization. "
        "Call this when the user wants to see, review, or check what contexts exist."
    ),
    module="context_management",
    requires_permission=("context_management", "view"),
    annotations={"display": "Fetching context documents..."},
)
async def list_contexts(ctx: ToolContext) -> str:
    """List all context documents for the org."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{ctx.base_url}/ask-aira/context/list",
            headers=ctx.capillary_headers(),
        )
        if resp.status_code != 200:
            return f"Error: Failed to fetch contexts (HTTP {resp.status_code})"

        data = resp.json()

    # Format for LLM consumption
    contexts = data if isinstance(data, list) else data.get("data", data.get("contexts", []))
    if not contexts:
        return "No context documents found for this organization."

    lines = [f"Found {len(contexts)} context document(s):\n"]
    for i, ctx_item in enumerate(contexts, 1):
        name = ctx_item.get("name", "Unnamed")
        scope = ctx_item.get("scope", "org")
        ctx_id = ctx_item.get("id", ctx_item.get("contextId", "?"))
        size = ctx_item.get("size", "")
        size_str = f" ({size} bytes)" if size else ""
        lines.append(f"{i}. **{name}** (id: {ctx_id}, scope: {scope}{size_str})")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: get_context_content
# ---------------------------------------------------------------------------


@registry.tool(
    name="get_context_content",
    description=(
        "Get the full content of a specific context document by its name. "
        "Call this when the user asks about what a specific context contains "
        "or wants to review it."
    ),
    module="context_management",
    requires_permission=("context_management", "view"),
    annotations={"display": "Reading context document..."},
)
async def get_context_content(ctx: ToolContext, context_name: str) -> str:
    """Fetch and return the content of a specific context.

    context_name: Name of the context document to retrieve
    """
    # First, list contexts to find the matching one
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{ctx.base_url}/ask-aira/context/list",
            headers=ctx.capillary_headers(),
        )
        if resp.status_code != 200:
            return f"Error: Failed to fetch context list (HTTP {resp.status_code})"

        data = resp.json()
        contexts = data if isinstance(data, list) else data.get("data", data.get("contexts", []))

    # Find the matching context (case-insensitive partial match)
    target = None
    for c in contexts:
        cname = c.get("name", "")
        if cname.lower() == context_name.lower() or context_name.lower() in cname.lower():
            target = c
            break

    if not target:
        available = ", ".join(c.get("name", "?") for c in contexts[:10])
        return (
            f"Context '{context_name}' not found. "
            f"Available contexts: {available}"
        )

    # The content may be in the list response or need a separate fetch
    content = target.get("content", target.get("context", ""))
    if content:
        # Try to decode if it's base64
        try:
            decoded = base64.b64decode(content).decode("utf-8")
            content = decoded
        except Exception:
            pass  # Already plain text

        return f"**Context: {target.get('name', context_name)}**\n\n{content}"

    return f"Context '{context_name}' exists but has no content."


# ---------------------------------------------------------------------------
# Tool: create_context
# ---------------------------------------------------------------------------


@registry.tool(
    name="create_context",
    description=(
        "Create a new context document. Call this when the user provides new "
        "context to save, or asks you to create a context document from the "
        "conversation. The content should be well-formatted markdown."
    ),
    module="context_management",
    requires_permission=("context_management", "create"),
    annotations={"display": "Creating context document..."},
)
async def create_context(
    ctx: ToolContext,
    name: str,
    content: str,
    scope: str = "org",
) -> str:
    """Create a new context document.

    name: Name for the new context document (max 100 chars, alphanumeric + _:#()-,)
    content: The context content in markdown format
    scope: Scope of the context — 'org' (default) or 'personal'
    """
    encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{ctx.base_url}/ask-aira/context/upload_context",
            headers={
                **ctx.capillary_headers(),
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={"name": name, "context": encoded, "scope": scope},
        )

    if resp.status_code != 200:
        return f"Error: Failed to create context '{name}' (HTTP {resp.status_code})"

    return f"Successfully created context document '{name}' with scope '{scope}'."


# ---------------------------------------------------------------------------
# Tool: update_context
# ---------------------------------------------------------------------------


@registry.tool(
    name="update_context",
    description=(
        "Update an existing context document's content. Call this when the user "
        "asks to modify, edit, or improve a specific context. Always confirm "
        "the changes with the user first before calling this tool."
    ),
    module="context_management",
    requires_permission=("context_management", "edit"),
    annotations={"display": "Updating context document..."},
)
async def update_context(
    ctx: ToolContext,
    context_name: str,
    new_content: str,
) -> str:
    """Update an existing context document.

    context_name: Name of the context document to update
    new_content: The new content in markdown format
    """
    # First, find the context ID by name
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{ctx.base_url}/ask-aira/context/list",
            headers=ctx.capillary_headers(),
        )
        if resp.status_code != 200:
            return f"Error: Failed to fetch context list (HTTP {resp.status_code})"

        data = resp.json()
        contexts = data if isinstance(data, list) else data.get("data", data.get("contexts", []))

    # Find matching context
    target = None
    for c in contexts:
        cname = c.get("name", "")
        if cname.lower() == context_name.lower() or context_name.lower() in cname.lower():
            target = c
            break

    if not target:
        return f"Error: Context '{context_name}' not found."

    context_id = target.get("id", target.get("contextId"))
    if not context_id:
        return f"Error: Could not determine ID for context '{context_name}'."

    # Update the context
    encoded = base64.b64encode(new_content.encode("utf-8")).decode("utf-8")
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.put(
            f"{ctx.base_url}/ask-aira/context/update_context",
            params={"context_id": context_id},
            headers={
                **ctx.capillary_headers(),
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "name": target.get("name", context_name),
                "context": encoded,
                "scope": target.get("scope", "org"),
            },
        )

    if resp.status_code != 200:
        return f"Error: Failed to update context '{context_name}' (HTTP {resp.status_code})"

    return f"Successfully updated context document '{context_name}'."


# ---------------------------------------------------------------------------
# Tool: delete_context
# ---------------------------------------------------------------------------


@registry.tool(
    name="delete_context",
    description=(
        "Delete a context document. Call this ONLY when the user explicitly "
        "asks to delete or remove a context. Always confirm before deleting."
    ),
    module="context_management",
    requires_permission=("context_management", "delete"),
    annotations={"display": "Deleting context document..."},
)
async def delete_context(ctx: ToolContext, context_name: str) -> str:
    """Delete a context document by name.

    context_name: Name of the context document to delete
    """
    # Find context ID by name
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{ctx.base_url}/ask-aira/context/list",
            headers=ctx.capillary_headers(),
        )
        if resp.status_code != 200:
            return f"Error: Failed to fetch context list (HTTP {resp.status_code})"

        data = resp.json()
        contexts = data if isinstance(data, list) else data.get("data", data.get("contexts", []))

    target = None
    for c in contexts:
        cname = c.get("name", "")
        if cname.lower() == context_name.lower():
            target = c
            break

    if not target:
        return f"Error: Context '{context_name}' not found. Deletion cancelled."

    context_id = target.get("id", target.get("contextId"))
    if not context_id:
        return f"Error: Could not determine ID for context '{context_name}'."

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.delete(
            f"{ctx.base_url}/ask-aira/context/delete_context",
            params={"context_id": context_id},
            headers=ctx.capillary_headers(),
        )

    if resp.status_code != 200:
        return f"Error: Failed to delete context '{context_name}' (HTTP {resp.status_code})"

    return f"Successfully deleted context document '{context_name}'."


# ---------------------------------------------------------------------------
# Tool: refactor_all_contexts
# ---------------------------------------------------------------------------


@registry.tool(
    name="refactor_all_contexts",
    description=(
        "Restructure and clean up all context documents using the refactoring "
        "blueprint. This will fetch all contexts, send them to an LLM for "
        "restructuring, and upload the cleaned results. Call this when the user "
        "asks to restructure, optimize, deduplicate, or clean up their contexts. "
        "This is a long-running operation."
    ),
    module="context_management",
    requires_permission=("context_management", "refactor"),
    annotations={"display": "Refactoring all contexts (this may take a minute)..."},
)
async def refactor_all_contexts(ctx: ToolContext) -> str:
    """Trigger full context refactoring via LLM.

    Fetches all contexts, sends them through the sanitize/refactor pipeline,
    and returns a summary of the restructured output.
    """
    from app.services.llm_service import stream_llm

    # 1. Fetch all contexts
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{ctx.base_url}/ask-aira/context/list",
            headers=ctx.capillary_headers(),
        )
        if resp.status_code != 200:
            return f"Error: Failed to fetch contexts (HTTP {resp.status_code})"
        data = resp.json()

    contexts = data if isinstance(data, list) else data.get("data", data.get("contexts", []))
    if not contexts:
        return "No context documents found to refactor."

    # 2. Build content payload
    content_parts = []
    name_to_id: dict[str, str] = {}
    for c in contexts:
        name = c.get("name", "Unnamed")
        cid = c.get("id", c.get("contextId", ""))
        raw_content = c.get("content", c.get("context", ""))
        # Try base64 decode
        try:
            raw_content = base64.b64decode(raw_content).decode("utf-8")
        except Exception:
            pass
        content_parts.append(f"--- Document: {name} ---\n{raw_content}")
        name_to_id[name] = cid

    combined = "\n\n".join(content_parts)

    # Cap the payload
    if len(combined) > settings.max_payload_chars:
        combined = combined[: settings.max_payload_chars]

    # 3. Load blueprint
    blueprint = ""
    if BLUEPRINT_PATH.exists():
        blueprint = BLUEPRINT_PATH.read_text(encoding="utf-8")

    # 4. Build prompt
    system_prompt = f"""You are a context document restructuring assistant.

{blueprint}

The user has {len(contexts)} context documents that need to be restructured into a clean,
well-organized set. Apply the blueprint rules above.

IMPORTANT: Return ONLY a valid JSON array. No explanation text before or after."""

    messages = [
        {
            "role": "user",
            "content": (
                f"Here are the current context documents to restructure:\n\n{combined}\n\n"
                "Please restructure these into a clean set of documents following the blueprint."
            ),
        }
    ]

    # 5. Stream LLM response (collect full output)
    full_output = ""
    provider = "anthropic"  # Default to Anthropic for refactoring
    model = "claude-sonnet-4-20250514"

    try:
        async for event in stream_llm(
            provider=provider,
            model=model,
            system=system_prompt,
            messages=messages,
            max_tokens=settings.sanitize_max_output_tokens,
        ):
            if event["type"] == "chunk":
                full_output += event["text"]
                # Send progress to frontend
                await ctx.ws_manager.send_to_connection(
                    ctx.ws_connection_id,
                    {"type": "tool_progress", "tool": "refactor_all_contexts", "text": "."},
                )
    except Exception as e:
        return f"Error during LLM refactoring: {str(e)}"

    # 6. Parse output
    try:
        # Find JSON array in output
        start = full_output.find("[")
        end = full_output.rfind("]") + 1
        if start == -1 or end == 0:
            return f"Error: LLM did not return valid JSON. Raw output starts with: {full_output[:200]}"

        new_docs = json.loads(full_output[start:end])
    except json.JSONDecodeError as e:
        return f"Error parsing LLM output as JSON: {str(e)}"

    # 7. Upload restructured documents
    upload_results = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        for doc in new_docs:
            doc_name = doc.get("name", "Unnamed")
            doc_content = doc.get("content", "")
            encoded = base64.b64encode(doc_content.encode("utf-8")).decode("utf-8")

            existing_id = name_to_id.get(doc_name)
            if existing_id:
                # Update existing
                r = await client.put(
                    f"{ctx.base_url}/ask-aira/context/update_context",
                    params={"context_id": existing_id},
                    headers={
                        **ctx.capillary_headers(),
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                    data={"name": doc_name, "context": encoded, "scope": "org"},
                )
                status = "updated" if r.status_code == 200 else f"error ({r.status_code})"
            else:
                # Create new
                r = await client.post(
                    f"{ctx.base_url}/ask-aira/context/upload_context",
                    headers={
                        **ctx.capillary_headers(),
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                    data={"name": doc_name, "context": encoded, "scope": "org"},
                )
                status = "created" if r.status_code == 200 else f"error ({r.status_code})"

            upload_results.append(f"- **{doc_name}**: {status}")

    summary = (
        f"Refactoring complete! Restructured {len(contexts)} documents into "
        f"{len(new_docs)} clean documents:\n\n"
        + "\n".join(upload_results)
    )
    return summary
