"""Context management tools — LLM-callable tools for CRUD operations on context documents.

These wrap the Capillary context API proxying logic (same as routers/contexts.py)
but return formatted strings suitable for LLM consumption.
"""

import base64
import logging
import re
from pathlib import Path

import aiofiles
import aiofiles.os
import httpx

from app.config import settings
from app.services.context_engine.parsing import (
    parse_refactor_output as _parse_refactor_output,
)
from app.services.llm_service import call_llm, stream_llm
from app.services.tools.registry import registry
from app.services.tools.tool_context import ToolContext
from app.utils import md_to_html

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BLUEPRINT_PATH = Path(__file__).parent.parent.parent / "resources" / "blueprint.md"

# Regex to strip existing summaries (old HTML-comment and new blockquote formats)
_SUMMARY_RE = re.compile(
    r"^(?:<!-- SUMMARY:.*?-->\n*|> \*\*Summary:\*\*.*?\n\n)",
    re.DOTALL,
)

SUMMARY_SYSTEM_PROMPT = (
    "You are a technical writer. Generate a concise, factual description of the "
    "given context document in UNDER 250 characters (this is a HARD LIMIT). "
    "The description must convey the document's purpose and key topics so an AI "
    "system can decide whether to load the full document.\n\n"
    "Rules:\n"
    "- Return ONLY the description text, nothing else.\n"
    "- HARD LIMIT: 250 characters maximum. Aim for 150-200 characters.\n"
    "- Write in third person, declarative tone (e.g. 'Defines the schema for...').\n"
    "- NEVER use first person ('I'), questions, or conversational language.\n"
    "- NEVER ask for clarification or say the content is insufficient.\n"
    "- If the content is too short to summarize meaningfully, return ONLY the word: SKIP\n\n"
    "Before returning, validate against this checklist:\n"
    "1. Is the output UNDER 250 characters? If not, shorten it.\n"
    "2. Does it start with a verb or noun phrase (not 'I', 'This', or a question)?\n"
    "3. Does it describe WHAT the document covers, not HOW it is structured?\n"
    "4. Is it a single factual statement, not a conversation?\n"
    "Only return the final description after all checks pass."
)

_MIN_CONTENT_LENGTH = 50  # Skip summary for trivially short docs
_MAX_SUMMARY = 280  # Hard cap; "> **Summary:** {text}\n\n" adds ~18 chars → stays under 300


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


async def _fetch_active_contexts(ctx: ToolContext) -> list[dict]:
    """Fetch active contexts from the Capillary API.

    Returns the normalised list of context dicts.
    Raises ``RuntimeError`` on HTTP failure so callers can catch and return
    an error string.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{ctx.base_url}/ask-aira/context/list",
            params={"is_active": "true"},
            headers=ctx.capillary_headers(),
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"Failed to fetch contexts (HTTP {resp.status_code})"
            )
        try:
            data = resp.json()
        except ValueError as exc:
            raise RuntimeError(
                f"Invalid JSON response from context API: {exc}"
            ) from exc

    return (
        data
        if isinstance(data, list)
        else data.get("data", data.get("contexts", []))
    )


def _find_context_by_name(
    contexts: list[dict],
    name: str,
    *,
    exact: bool = False,
) -> dict | None:
    """Find a context by name (case-insensitive).

    * ``exact=False`` (default) — prefers an exact match; falls back to the
      first substring match.  Used by ``get_context_content`` and
      ``update_context`` for user convenience.
    * ``exact=True`` — exact match only.  Used by ``delete_context`` for
      safety (no accidental partial-match deletion).
    """
    name_lower = name.lower()
    partial_match: dict | None = None

    for c in contexts:
        cname = c.get("name", "").lower()
        if cname == name_lower:
            return c
        if not exact and name_lower in cname and partial_match is None:
            partial_match = c

    return partial_match


def _maybe_decode_base64(content: str) -> str:
    """Decode base64 if the string is valid base64, otherwise return as-is."""
    try:
        return base64.b64decode(content).decode("utf-8")
    except Exception:
        return content


async def _send_ws(ctx: ToolContext, payload: dict) -> None:
    """Send a WebSocket message if a connection is active, otherwise no-op."""
    if ctx.ws_manager and ctx.ws_connection_id:
        await ctx.ws_manager.send_to_connection(ctx.ws_connection_id, payload)


async def _generate_summary(content: str) -> str:
    """Generate a <300 char summary for a context document using Haiku.

    Returns empty string if content is too short, LLM fails, or output is
    unusable.
    """
    if len(content.strip()) < _MIN_CONTENT_LENGTH:
        return ""

    try:
        result = await call_llm(
            provider="anthropic",
            model="claude-haiku-4-5-20251001",
            system=SUMMARY_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}],
            max_tokens=150,
        )
        for block in result.get("content", []):
            if block.get("type") == "text":
                summary_text = block["text"].strip()
                break
        else:
            return ""
    except Exception as e:
        logger.warning("Failed to generate summary: %s", e)
        return ""

    # Discard SKIP or conversational filler
    if summary_text.upper() == "SKIP" or summary_text.lower().startswith("i "):
        return ""

    # Hard cap — LLMs can't count, so this is the real enforcement.
    if len(summary_text) > _MAX_SUMMARY:
        truncated = summary_text[:_MAX_SUMMARY]
        last_period = max(truncated.rfind(". "), truncated.rfind(".\n"))
        if last_period > 100:
            summary_text = truncated[: last_period + 1]
        else:
            last_space = truncated.rfind(" ", 0, _MAX_SUMMARY - 3)
            summary_text = (
                truncated[:last_space] + "..."
                if last_space > 100
                else truncated[: _MAX_SUMMARY - 3] + "..."
            )

    return summary_text


def _prepend_summary(summary_text: str, content: str) -> str:
    """Prepend a blockquote summary to *content*, or return it unchanged."""
    if summary_text:
        return f"> **Summary:** {summary_text}\n\n{content}"
    return content


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
    try:
        contexts = await _fetch_active_contexts(ctx)
    except RuntimeError as e:
        return f"Error: {e}"

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
    try:
        contexts = await _fetch_active_contexts(ctx)
    except RuntimeError as e:
        return f"Error: {e}"

    target = _find_context_by_name(contexts, context_name)
    if not target:
        available = ", ".join(c.get("name", "?") for c in contexts[:10])
        return f"Context '{context_name}' not found. Available contexts: {available}"

    content = target.get("content", target.get("context", ""))
    if content:
        content = _maybe_decode_base64(content)
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
    await _send_ws(ctx, {
        "type": "ai_context_staged",
        "context": {"name": name, "content": content, "scope": scope},
    })

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
    await _send_ws(ctx, {"type": "trigger_bulk_upload"})

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
    try:
        contexts = await _fetch_active_contexts(ctx)
    except RuntimeError as e:
        return f"Error: {e}"

    target = _find_context_by_name(contexts, context_name)
    if not target:
        return f"Error: Context '{context_name}' not found."

    context_id = target.get("id", target.get("contextId"))
    if not context_id:
        return f"Error: Could not determine ID for context '{context_name}'."

    # Convert markdown → HTML for Capillary
    html_content = md_to_html(new_content)
    encoded = base64.b64encode(html_content.encode("utf-8")).decode("utf-8")

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
    try:
        contexts = await _fetch_active_contexts(ctx)
    except RuntimeError as e:
        return f"Error: {e}"

    # exact=True: no partial-match deletion for safety
    target = _find_context_by_name(contexts, context_name, exact=True)
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
        "blueprint. This fetches all contexts, sends them to an LLM for "
        "restructuring, then generates a concise summary for each and prepends it. "
        "Results are staged in the 'AI Generated' tab for review. "
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
    generates summaries, and stages results in the AI Generated tab.
    """
    # 1. Fetch all active contexts
    try:
        contexts = await _fetch_active_contexts(ctx)
    except RuntimeError as e:
        return f"Error: {e}"

    if not contexts:
        return "No context documents found to refactor."

    # 2. Load blueprint (async I/O to avoid blocking event loop)
    blueprint = ""
    if await aiofiles.os.path.exists(BLUEPRINT_PATH):
        async with aiofiles.open(BLUEPRINT_PATH, encoding="utf-8") as f:
            blueprint = await f.read()

    if not blueprint:
        return "Error: Blueprint file not found. Cannot refactor without restructuring guidelines."

    # 3. Build user message — NO artificial token budget or payload cap
    user_parts: list[str] = [
        "Below are ALL the context documents for this organization. "
        "Please restructure them according to the blueprint instructions.\n\n"
        f"There are {len(contexts)} context document(s). "
        "Restructure and compress without losing critical information.\n\n"
        "Return your response as a JSON array where each element has:\n"
        '- "name": the context document name (max 100 chars, only alphanumeric, spaces, _:#()-,)\n'
        '- "content": the restructured context content in markdown\n\n'
        "Respond ONLY with the JSON array, no additional text before or after it.\n\n"
        "---\n\n",
    ]

    for i, c in enumerate(contexts):
        name = c.get("name", f"Context {i + 1}")
        raw_content = _maybe_decode_base64(
            c.get("content", c.get("context", ""))
        )
        scope = c.get("scope", "org")
        user_parts.append(f"### Context Document {i + 1}: {name}\n")
        user_parts.append(f"Scope: {scope}\n")
        user_parts.append(f"Content:\n{raw_content}\n\n---\n\n")

    user_content = "".join(user_parts)
    messages = [{"role": "user", "content": user_content}]

    # 4. Stream LLM response (collect full output)
    full_output = ""
    try:
        async for event in stream_llm(
            provider=settings.refactor_provider,
            model=settings.refactor_model,
            system=blueprint,
            messages=messages,
            max_tokens=settings.sanitize_max_output_tokens,
        ):
            if event["type"] == "chunk":
                full_output += event["text"]
                await _send_ws(ctx, {
                    "type": "tool_progress",
                    "tool": "refactor_all_contexts",
                    "text": ".",
                })
    except Exception as e:
        return f"Error during LLM refactoring: {e!s}"

    # 5. Parse output (robust: handles code fences, truncation, name sanitisation)
    try:
        new_docs = _parse_refactor_output(full_output)
    except ValueError as e:
        return f"Error: {e!s}"

    if not new_docs:
        return "Error: LLM returned empty results. The response may have been truncated."

    # 6. Generate summaries + stage restructured documents
    staged_names: list[str] = []
    total_docs = len(new_docs)

    for idx, doc in enumerate(new_docs):
        doc_name = doc.get("name", "Unnamed")
        doc_content = doc.get("content", "")
        doc_scope = doc.get("scope", "org")

        # Generate and prepend summary for each refactored doc
        summary_text = await _generate_summary(doc_content)
        doc_content = _prepend_summary(summary_text, doc_content)

        await _send_ws(ctx, {
            "type": "ai_context_staged",
            "context": {
                "name": doc_name,
                "content": doc_content,
                "scope": doc_scope,
            },
        })
        await _send_ws(ctx, {
            "type": "tool_progress",
            "tool": "refactor_all_contexts",
            "text": f"Summarized {idx + 1}/{total_docs}: {doc_name}",
        })
        staged_names.append(f"- **{doc_name}**")

    return (
        f"Refactoring complete! Restructured {len(contexts)} documents into "
        f"{len(new_docs)} clean documents (with summaries prepended). They have been "
        f"staged in the 'AI Generated' tab for review:\n\n"
        + "\n".join(staged_names)
        + "\n\nThe user can review, edit, and upload them from the 'AI Generated' tab, "
        "or ask you to upload all staged contexts."
    )


# ---------------------------------------------------------------------------
# Tool: add_summary_to_contexts
# ---------------------------------------------------------------------------


@registry.tool(
    name="add_summary_to_contexts",
    description=(
        "Generate a concise summary (under 300 characters) for each context document "
        "and prepend it to the top of the content. Summaries help aiRA quickly decide "
        "which contexts to load. Results are staged in the 'AI Generated' tab. "
        "Call this when the user asks to add summaries to contexts."
    ),
    module="context_management",
    requires_permission=("context_management", "edit"),
    annotations={"display": "Generating context summaries..."},
)
async def add_summary_to_contexts(ctx: ToolContext) -> str:
    """Generate a short summary for each context and prepend it to the content.

    Processes contexts one at a time, stages results in the AI Generated tab.
    """
    # 1. Fetch all active contexts
    try:
        contexts = await _fetch_active_contexts(ctx)
    except RuntimeError as e:
        return f"Error: {e}"

    if not contexts:
        return "No context documents found to summarize."

    total = len(contexts)
    staged_names: list[str] = []

    # 2. Process each context sequentially
    for i, c in enumerate(contexts):
        name = c.get("name", f"Context {i + 1}")
        raw_content = _maybe_decode_base64(
            c.get("content", c.get("context", ""))
        )
        scope = c.get("scope", "org")

        # Strip existing summary if present (allows safe re-running)
        clean_content = _SUMMARY_RE.sub("", raw_content)

        # Generate summary via shared helper
        summary_text = await _generate_summary(clean_content)
        new_content = _prepend_summary(summary_text, clean_content)

        # Stage in AI Generated tab
        status_label = (
            f"Skipped {i + 1}/{total}: {name} (too short)"
            if not summary_text
            else f"Summarized {i + 1}/{total}: {name}"
        )
        await _send_ws(ctx, {
            "type": "ai_context_staged",
            "context": {"name": name, "content": new_content, "scope": scope},
        })
        await _send_ws(ctx, {
            "type": "tool_progress",
            "tool": "add_summary_to_contexts",
            "text": status_label,
        })

        suffix = " (skipped — too short)" if not summary_text else ""
        staged_names.append(f"- **{name}**{suffix}")

    return (
        f"Generated summaries for {total} context documents and staged them in the "
        f"'AI Generated' tab for review:\n\n"
        + "\n".join(staged_names)
        + "\n\nEach context now has a `> **Summary:** ...` blockquote within the first "
        "300 characters. Review and upload from the 'AI Generated' tab."
    )
