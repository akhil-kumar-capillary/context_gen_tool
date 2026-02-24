"""Context management tools — LLM-callable tools for CRUD operations on context documents.

These wrap the Capillary context API proxying logic (same as routers/contexts.py)
but return formatted strings suitable for LLM consumption.
"""
import base64
import json
import logging
import re
from pathlib import Path

import aiofiles
import aiofiles.os
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
        "Draft a new context document and stage it for the user's review in the "
        "'AI Generated' tab. The user can then review, edit, and upload it manually. "
        "Call this when the user asks you to create a context document. "
        "The content should be well-formatted markdown. "
        "This does NOT upload directly — it stages for review first."
    ),
    module="context_management",
    requires_permission=("context_management", "create"),
    annotations={"display": "Drafting context document..."},
)
async def create_context(
    ctx: ToolContext,
    name: str,
    content: str,
    scope: str = "org",
) -> str:
    """Draft a new context document and stage it for review in the AI Generated tab.

    name: Name for the new context document (max 100 chars, alphanumeric + _:#()-,)
    content: The context content in markdown format
    scope: Scope of the context — 'org' (default) or 'personal'
    """
    # Stage in the "AI Generated" tab via WebSocket event
    if ctx.ws_manager and ctx.ws_connection_id:
        await ctx.ws_manager.send_to_connection(
            ctx.ws_connection_id,
            {
                "type": "ai_context_staged",
                "context": {"name": name, "content": content, "scope": scope},
            },
        )

    return (
        f"Context document '{name}' has been drafted and staged in the 'AI Generated' tab "
        f"with scope '{scope}'. The user can review, edit, and upload it from there, "
        f"or ask you to upload all staged contexts."
    )


# ---------------------------------------------------------------------------
# Tool: upload_staged_contexts
# ---------------------------------------------------------------------------


@registry.tool(
    name="upload_staged_contexts",
    description=(
        "Upload all staged AI-generated context documents to the organization. "
        "Call this ONLY when the user explicitly asks to upload, save, or push the "
        "staged contexts from the 'AI Generated' tab."
    ),
    module="context_management",
    requires_permission=("context_management", "create"),
    annotations={"display": "Uploading staged contexts..."},
)
async def upload_staged_contexts(ctx: ToolContext) -> str:
    """Trigger bulk upload of all staged AI-generated contexts."""
    if ctx.ws_manager and ctx.ws_connection_id:
        await ctx.ws_manager.send_to_connection(
            ctx.ws_connection_id,
            {"type": "trigger_bulk_upload"},
        )

    return (
        "Upload has been triggered. The staged contexts in the 'AI Generated' tab "
        "are being uploaded. Check the tab for individual upload status."
    )


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
# Helpers: JSON parsing for refactoring output
# ---------------------------------------------------------------------------

_NAME_REGEX = re.compile(r"^[a-zA-Z0-9 _:#()\-,]+$")


def _parse_refactor_output(text: str) -> list[dict]:
    """Parse LLM refactoring output — handles code fences, truncation, name sanitization.

    Ported from the desktop app's parse-llm-response.ts for consistency.
    """
    text = text.strip()

    # Strip code fences (```json ... ```)
    if text.startswith("```"):
        lines = text.split("\n")
        start = 1
        end = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
        text = "\n".join(lines[start:end])

    parsed = None

    # Try 1: Direct JSON parse
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        # Try 2: Regex extraction of JSON array
        match = re.search(r"\[[\s\S]*\]", text)
        if match:
            try:
                parsed = json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        # Try 3: Truncation recovery — salvage complete objects from a cut-off response
        if parsed is None:
            arr_start = text.find("[")
            if arr_start != -1:
                partial = text[arr_start:]
                last_brace = partial.rfind("}")
                if last_brace != -1:
                    try:
                        parsed = json.loads(partial[: last_brace + 1] + "]")
                        logger.warning(
                            "Refactor output was truncated — recovered %d partial documents",
                            len(parsed) if isinstance(parsed, list) else 0,
                        )
                    except json.JSONDecodeError:
                        pass

    if not isinstance(parsed, list):
        raise ValueError(
            f"Could not parse LLM response as JSON array. Response starts with: {text[:200]}"
        )

    # Validate and sanitize each document
    result: list[dict] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        content = str(item.get("content", "")).strip()
        if not name or not content:
            continue
        # Enforce name constraints
        if len(name) > 100:
            name = name[:100]
        if not _NAME_REGEX.match(name):
            name = re.sub(r"[^a-zA-Z0-9 _:#()\-,]", "", name)
        result.append({
            "name": name,
            "content": content,
            "scope": item.get("scope", "org"),
        })

    return result


# ---------------------------------------------------------------------------
# Tool: refactor_all_contexts
# ---------------------------------------------------------------------------


@registry.tool(
    name="refactor_all_contexts",
    description=(
        "Restructure and clean up all context documents using the refactoring "
        "blueprint. This fetches all contexts, sends them to an LLM for "
        "restructuring, and stages the results in the 'AI Generated' tab for review. "
        "Nothing is overwritten — the user reviews and uploads manually. "
        "Call this when the user asks to restructure, optimize, deduplicate, or clean up their contexts."
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

    # 2. Load blueprint (async file I/O to avoid blocking event loop)
    # The blueprint IS the system prompt — matching the desktop app's approach
    blueprint = ""
    if await aiofiles.os.path.exists(BLUEPRINT_PATH):
        async with aiofiles.open(BLUEPRINT_PATH, encoding="utf-8") as f:
            blueprint = await f.read()

    if not blueprint:
        return "Error: Blueprint file not found. Cannot refactor without restructuring guidelines."

    system_prompt = blueprint

    # 3. Build user message with token budget + structured context formatting
    # (matching desktop app's formatContextsForLLM)
    max_output_tokens = settings.sanitize_max_output_tokens
    budget_per_file = max_output_tokens // max(len(contexts), 1)

    user_parts: list[str] = [
        "Below are ALL the context documents for this organization. "
        "Please restructure them according to the blueprint instructions.\n\n"
        f"IMPORTANT: You have a total output budget of ~{max_output_tokens} tokens. "
        f"There are {len(contexts)} context document(s), so aim for ~{budget_per_file} tokens "
        "per document. Be concise — compress and restructure without losing critical information.\n\n"
        "Return your response as a JSON array where each element has:\n"
        '- "name": the context document name (max 100 chars, only alphanumeric, spaces, _:#()-,)\n'
        '- "content": the restructured context content in markdown\n\n'
        "Respond ONLY with the JSON array, no additional text before or after it.\n\n"
        "---\n\n",
    ]

    name_to_id: dict[str, str] = {}
    for i, c in enumerate(contexts):
        name = c.get("name", f"Context {i + 1}")
        cid = c.get("id", c.get("contextId", ""))
        raw_content = c.get("content", c.get("context", ""))
        scope = c.get("scope", "org")
        # Try base64 decode
        try:
            raw_content = base64.b64decode(raw_content).decode("utf-8")
        except Exception:
            pass
        user_parts.append(f"### Context Document {i + 1}: {name}\n")
        user_parts.append(f"Scope: {scope}\n")
        user_parts.append(f"Content:\n{raw_content}\n\n---\n\n")
        name_to_id[name] = cid

    user_content = "".join(user_parts)

    # Cap the payload
    if len(user_content) > settings.max_payload_chars:
        user_content = user_content[: settings.max_payload_chars]

    messages = [{"role": "user", "content": user_content}]

    # 4. Stream LLM response (collect full output)
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

    # 5. Parse output (robust: handles code fences, truncation, name sanitization)
    try:
        new_docs = _parse_refactor_output(full_output)
    except ValueError as e:
        return f"Error: {str(e)}"

    if not new_docs:
        return "Error: LLM returned empty results. The response may have been truncated."

    # 6. Stage restructured documents in the AI Generated tab (not direct upload)
    staged_names = []
    for doc in new_docs:
        doc_name = doc.get("name", "Unnamed")
        doc_content = doc.get("content", "")
        doc_scope = doc.get("scope", "org")

        if ctx.ws_manager and ctx.ws_connection_id:
            await ctx.ws_manager.send_to_connection(
                ctx.ws_connection_id,
                {
                    "type": "ai_context_staged",
                    "context": {
                        "name": doc_name,
                        "content": doc_content,
                        "scope": doc_scope,
                    },
                },
            )
        staged_names.append(f"- **{doc_name}**")

    summary = (
        f"Refactoring complete! Restructured {len(contexts)} documents into "
        f"{len(new_docs)} clean documents. They have been staged in the "
        f"'AI Generated' tab for review:\n\n"
        + "\n".join(staged_names)
        + "\n\nThe user can review, edit, and upload them from the 'AI Generated' tab, "
        "or ask you to upload all staged contexts."
    )
    return summary
