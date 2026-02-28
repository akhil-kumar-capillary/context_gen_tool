"""Content Sanitizer — LLM-powered content cleanup for context tree leaves.

Instead of attaching raw original content to tree leaves, this module sends
all contexts through the blueprint LLM to produce clean, restructured content.
Falls back to original content for any leaf not matched by the LLM output.
"""
import asyncio
import logging
from pathlib import Path
from typing import Any, Callable, Awaitable

import aiofiles
import aiofiles.os

from app.config import settings
from app.services.context_engine.parsing import parse_refactor_output
from app.services.llm_service import stream_llm

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, str, str], Awaitable[None]]

BLUEPRINT_PATH = Path(__file__).parent.parent.parent / "resources" / "blueprint.md"


# ---------------------------------------------------------------------------
# Blueprint loader
# ---------------------------------------------------------------------------


async def _load_blueprint(custom_text: str | None = None) -> str:
    """Load the sanitization blueprint.

    Priority:
    1. Custom text provided by the user (from settings store)
    2. Default blueprint.md file
    """
    if custom_text and custom_text.strip():
        return custom_text.strip()

    if await aiofiles.os.path.exists(BLUEPRINT_PATH):
        async with aiofiles.open(BLUEPRINT_PATH, encoding="utf-8") as f:
            return await f.read()

    raise FileNotFoundError(
        f"Blueprint file not found at {BLUEPRINT_PATH} and no custom blueprint provided."
    )


# ---------------------------------------------------------------------------
# User message builder
# ---------------------------------------------------------------------------


def _build_sanitize_message(
    contexts: list[dict],
    max_output_tokens: int,
) -> str:
    """Build the user message with token budget guidance.

    Uses the same formatting pattern as refactor_all_contexts in context_tools.py.
    Contexts here come from the collector (have source, name, content, doc_key).
    """
    budget_per_file = max_output_tokens // max(len(contexts), 1)

    parts: list[str] = [
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

    for i, ctx in enumerate(contexts):
        name = ctx.get("name", f"Context {i + 1}")
        content = ctx.get("content", "")
        source = ctx.get("source", "unknown")
        scope = ctx.get("scope", "org")

        parts.append(f"### Context Document {i + 1}: {name}\n")
        parts.append(f"Source: {source} | Scope: {scope}\n")
        parts.append(f"Content:\n{content}\n\n---\n\n")

    user_content = "".join(parts)

    # Cap the payload to avoid exceeding LLM limits
    if len(user_content) > settings.max_payload_chars:
        user_content = user_content[: settings.max_payload_chars]

    return user_content


# ---------------------------------------------------------------------------
# Content attachment (sanitized → tree leaves)
# ---------------------------------------------------------------------------


def _collect_leaves(node: dict, leaves: list[dict]):
    """Recursively collect all leaf nodes from the tree."""
    if node.get("type") == "leaf":
        leaves.append(node)
    for child in node.get("children", []):
        if isinstance(child, dict):
            _collect_leaves(child, leaves)


def _attach_sanitized_content(
    tree: dict,
    sanitized_docs: list[dict],
    contexts: list[dict],
) -> dict[str, int]:
    """Walk tree and replace leaf desc with sanitized content.

    Matching strategy:
    1. Try matching leaf name to sanitized doc name (case-insensitive)
    2. If not matched, fall back to original content from contexts

    Returns: {sanitized_count, fallback_count, total_leaves}
    """
    # Build sanitized content map (name → content)
    sanitized_map: dict[str, str] = {}
    for doc in sanitized_docs:
        name = doc.get("name", "").lower().strip()
        if name:
            sanitized_map[name] = doc["content"]

    # Build original content map (same logic as tree_builder._attach_full_content)
    original_map: dict[str, str] = {}
    for ctx in contexts:
        content = ctx.get("content", "")
        if not content:
            continue
        doc_key = ctx.get("doc_key", "")
        if doc_key:
            original_map[doc_key.lower().strip()] = content
        name = ctx.get("name", "")
        if name:
            original_map[name.lower().strip()] = content

    # Walk tree and attach
    leaves: list[dict] = []
    _collect_leaves(tree, leaves)

    sanitized_count = 0
    fallback_count = 0

    for leaf in leaves:
        leaf_name = (leaf.get("name") or "").lower().strip()
        leaf_key = (leaf.get("source_doc_key") or "").lower().strip()

        # Try sanitized content first
        sanitized = sanitized_map.get(leaf_name)
        if sanitized:
            leaf["desc"] = sanitized
            sanitized_count += 1
            continue

        # Fall back to original content
        original = original_map.get(leaf_key) or original_map.get(leaf_name)
        if original:
            leaf["desc"] = original
            fallback_count += 1
        else:
            fallback_count += 1

    return {
        "sanitized_count": sanitized_count,
        "fallback_count": fallback_count,
        "total_leaves": len(leaves),
    }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def sanitize_tree_content(
    tree: dict,
    contexts: list[dict],
    progress_cb: ProgressCallback | None = None,
    cancel_event: asyncio.Event | None = None,
    blueprint_text: str | None = None,
    provider: str = "anthropic",
    model: str = "claude-opus-4-6",
) -> dict[str, Any]:
    """Sanitize leaf node content using the blueprint-based LLM pipeline.

    Instead of attaching the raw original content to tree leaves, this function:
    1. Loads the blueprint (custom or default)
    2. Sends all contexts through the blueprint LLM with token budget guidance
    3. Parses the output as a JSON array of {name, content, scope}
    4. Walks the tree and replaces leaf desc fields with sanitized content
    5. Falls back to original content for any leaf not matched

    Args:
        tree: The validated tree structure from build_tree (with summaries in desc).
        contexts: Original collected contexts (same list passed to build_tree).
        progress_cb: Async callback(phase, detail, status) for progress updates.
        cancel_event: Cancellation event.
        blueprint_text: Custom blueprint text (from settings store), or None for default.
        provider: LLM provider.
        model: LLM model.

    Returns:
        {
            "sanitized_count": int,    # number of leaves successfully sanitized
            "total_leaves": int,       # total leaf count
            "fallback_count": int,     # leaves that fell back to original content
            "token_usage": {...},      # token usage from sanitization LLM call
        }
    """
    async def emit(phase: str, detail: str, status: str = "running"):
        if progress_cb:
            await progress_cb(phase, detail, status)

    # 1. Load blueprint
    await emit("sanitizing", "Loading sanitization blueprint...", "running")
    system_prompt = await _load_blueprint(blueprint_text)

    if cancel_event and cancel_event.is_set():
        raise asyncio.CancelledError()

    # 2. Build user message
    max_output_tokens = settings.sanitize_max_output_tokens
    user_content = _build_sanitize_message(contexts, max_output_tokens)
    messages = [{"role": "user", "content": user_content}]

    await emit(
        "sanitizing",
        f"Sending {len(contexts)} contexts to LLM for sanitization...",
        "running",
    )

    # 3. Stream LLM response
    full_output = ""
    token_usage = {"input_tokens": 0, "output_tokens": 0}

    async for event in stream_llm(
        provider=provider,
        model=model,
        system=system_prompt,
        messages=messages,
        max_tokens=max_output_tokens,
        cancel_event=cancel_event,
    ):
        if event["type"] == "chunk":
            full_output += event["text"]
            # Emit periodic progress
            if len(full_output) % 3000 < len(event["text"]):
                await emit(
                    "sanitizing",
                    f"Sanitizing content... ({len(full_output)} chars)",
                    "running",
                )
        elif event["type"] == "end":
            token_usage = event.get("usage", token_usage)
            if event.get("stop_reason") in ("max_tokens", "length"):
                logger.warning(
                    "Sanitization LLM response was truncated at %d chars",
                    len(full_output),
                )
                await emit(
                    "sanitizing",
                    "Response was truncated — recovering partial results...",
                    "running",
                )

    if not full_output.strip():
        raise ValueError("LLM returned empty response for sanitization")

    if cancel_event and cancel_event.is_set():
        raise asyncio.CancelledError()

    # 4. Parse output
    await emit("sanitizing", "Parsing sanitized content...", "running")
    sanitized_docs = parse_refactor_output(full_output)

    if not sanitized_docs:
        raise ValueError("LLM returned no parseable documents for sanitization")

    logger.info("Sanitization produced %d documents", len(sanitized_docs))

    # 5. Attach sanitized content to tree leaves
    await emit(
        "sanitizing",
        f"Attaching {len(sanitized_docs)} sanitized documents to tree leaves...",
        "running",
    )
    result = _attach_sanitized_content(tree, sanitized_docs, contexts)

    return {
        "sanitized_count": result["sanitized_count"],
        "total_leaves": result["total_leaves"],
        "fallback_count": result["fallback_count"],
        "token_usage": token_usage,
    }
