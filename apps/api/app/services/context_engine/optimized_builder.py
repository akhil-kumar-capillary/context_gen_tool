"""Optimized Tree Builder — unified LLM call that restructures AND organizes.

When "Sanitize content" is enabled, this replaces the two-stage pipeline
(build tree → sanitize content) with a single LLM call that:
  1. Applies the blueprint restructuring methodology
  2. Merges/deduplicates/optimizes contexts
  3. Builds the hierarchical tree with FULL optimized content in leaves

This gives the LLM full structural control — it can produce fewer leaves
than inputs by merging duplicates, and each leaf contains the final
restructured content (not raw input).
"""
import asyncio
import logging
from typing import Any, Callable, Awaitable

import aiofiles
import aiofiles.os

from app.config import settings
from app.services.context_engine.tree_builder import (
    build_user_message,
    parse_tree_output,
    validate_tree,
    ProgressCallback,
)
from app.services.llm_service import stream_llm

logger = logging.getLogger(__name__)

BLUEPRINT_PATH = __import__("pathlib").Path(__file__).parent.parent.parent / "resources" / "blueprint.md"

# ---------------------------------------------------------------------------
# System prompt suffix — appended after the blueprint
# ---------------------------------------------------------------------------

OPTIMIZED_TREE_INSTRUCTIONS = """\

---

# OUTPUT INSTRUCTIONS — Context Tree Generation

You have been given the restructuring blueprint above. Now apply it to the \
context documents provided below.

## Your Task
1. Execute the blueprint methodology: inventory all source documents, \
detect duplicates and conflicts, resolve contradictions, restructure and \
consolidate content.
2. Organize the OPTIMIZED output into a hierarchical tree structure.

## Critical: You Have Full Optimization Liberty
- You MUST merge duplicate or near-duplicate contexts into single optimized documents.
- You MUST resolve contradictions (keep the authoritative version).
- You MAY split large contexts into logical sub-documents if it improves organization.
- You MAY rename contexts to be clearer and more descriptive.
- You MAY remove content that is purely redundant with no unique information.
- The output leaf count does NOT need to match the input context count. \
If 10 inputs contain duplicates, produce fewer consolidated leaves.
- Each leaf's "desc" field must contain the FULL restructured content — \
not a summary. This is the final content that will be used.

## Tree Structure Rules
- Root node: "Organization Context" (type: "root", id: "root")
- Categories: Logical groupings (type: "cat") — e.g. "Analytics & SQL", \
"Loyalty & Rewards", "Campaigns & Messaging"
- Leaf nodes: Individual optimized context documents (type: "leaf")

## For each node you must provide:
- id: unique snake_case identifier (e.g. "analytics_sql", "loyalty_master_rules")
- name: human-readable display name
- type: "root" | "cat" | "leaf"
- health: 0-100 score based on content quality after optimization
- visibility: "public" (general use) | "private" (contains sensitive data)
- children: array of child nodes (for root and cat types)

## For leaf nodes additionally provide:
- desc: The FULL restructured/optimized content in markdown. This is NOT a \
summary — it is the complete final document content.
- source: "optimized" if the leaf was created by merging/restructuring \
multiple inputs, or the original source ("databricks", "config_apis", \
"capillary") if the leaf maps 1:1 to a single input context.
- source_doc_key: original doc key if the leaf maps 1:1 to a single input. \
Omit this field for merged/optimized leaves.

## Health Scoring Guidelines (post-optimization):
- 90-100: Well-structured, no redundancy, clear and actionable
- 70-89: Good quality with minor areas for improvement
- 50-69: Needs further cleanup (shouldn't happen after optimization)
- Below 50: Serious issues remain

## Analysis Checks:
For EACH leaf node, include an "analysis" field:
{
    "redundancy": {"score": 0-100, "overlaps_with": [], "detail": "..."},
    "conflicts": [],
    "suggestions": ["any remaining improvement suggestions"]
}

After optimization, redundancy scores should be very low and conflicts \
should be resolved. If any remain, note them in the analysis.

## Secret Detection:
If any leaf content contains credentials (Bearer tokens, API keys, \
passwords, auth headers):
1. List them in the parent category's "secrets" array as: \
{"key": "{{KEY_NAME}}", "scope": "category_name", "type": "Basic Auth|API Key|Token|Password"}
2. Add a "secretRefs" array to the leaf referencing the key names
3. Set the leaf's visibility to "private"

## Output Format:
Return ONLY valid JSON — the tree object. No markdown code fences, no \
explanation, no text before or after the JSON. Start with { and end with }.
"""


# ---------------------------------------------------------------------------
# Blueprint loader (same logic as sanitizer)
# ---------------------------------------------------------------------------


async def _load_blueprint(custom_text: str | None = None) -> str:
    """Load the restructuring blueprint."""
    if custom_text and custom_text.strip():
        return custom_text.strip()

    if await aiofiles.os.path.exists(BLUEPRINT_PATH):
        async with aiofiles.open(BLUEPRINT_PATH, encoding="utf-8") as f:
            return await f.read()

    raise FileNotFoundError(
        f"Blueprint file not found at {BLUEPRINT_PATH} and no custom blueprint provided."
    )


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------


async def build_optimized_tree(
    contexts: list[dict],
    org_id: int,
    progress_cb: ProgressCallback | None = None,
    cancel_event: asyncio.Event | None = None,
    blueprint_text: str | None = None,
    provider: str = "anthropic",
    model: str = "claude-opus-4-6",
    max_tokens: int = 128000,
) -> dict[str, Any]:
    """Build an optimized context tree using a unified LLM call.

    Combines the blueprint restructuring methodology with tree building
    in a single LLM call, giving the LLM full liberty to merge, deduplicate,
    and optimize contexts.

    Args:
        contexts: List of context dicts from the collector.
        org_id: Organization ID.
        progress_cb: Async callback(phase, detail, status) for progress updates.
        cancel_event: Event to cancel the stream.
        blueprint_text: Custom blueprint text, or None for default blueprint.md.
        provider: LLM provider.
        model: LLM model.
        max_tokens: Max output tokens (default: 128000, Opus 4.6 max).

    Returns:
        Same shape as build_tree():
        {
            "tree_data": {...},
            "model_used": "...",
            "provider_used": "...",
            "token_usage": {"input_tokens": N, "output_tokens": N},
            "system_prompt_used": "...",
        }
    """
    async def emit(phase: str, detail: str, status: str = "running"):
        if progress_cb:
            await progress_cb(phase, detail, status)

    # 1. Load blueprint and construct system prompt
    await emit("analyzing", "Loading optimization blueprint...", "running")

    blueprint = await _load_blueprint(blueprint_text)
    system_prompt = blueprint + "\n" + OPTIMIZED_TREE_INSTRUCTIONS

    if cancel_event and cancel_event.is_set():
        raise asyncio.CancelledError()

    # 2. Build user message (reuse tree_builder pattern)
    await emit(
        "analyzing",
        f"Sending {len(contexts)} contexts to LLM for optimization & tree building...",
        "running",
    )

    user_message = build_user_message(contexts, org_id)

    # Warn if payload is large — but never silently truncate input.
    # The LLM provider will enforce its own context-window limits with an
    # explicit error, which is far better than silently dropping contexts.
    if len(user_message) > settings.max_payload_chars:
        logger.warning(
            "User message (%d chars) exceeds max_payload_chars (%d). "
            "Sending full payload — LLM provider will enforce context window limits.",
            len(user_message),
            settings.max_payload_chars,
        )

    messages = [{"role": "user", "content": user_message}]

    # 3. Stream LLM response with retry
    full_output = ""
    token_usage = {"input_tokens": 0, "output_tokens": 0}
    was_truncated = False
    max_retries = 2

    for attempt in range(max_retries + 1):
        full_output = ""
        token_usage = {"input_tokens": 0, "output_tokens": 0}

        try:
            async for event in stream_llm(
                provider=provider,
                model=model,
                system=system_prompt,
                messages=messages,
                max_tokens=max_tokens,
                cancel_event=cancel_event,
            ):
                if event["type"] == "chunk":
                    full_output += event["text"]
                    # Emit periodic progress
                    if len(full_output) % 3000 < len(event["text"]):
                        await emit(
                            "analyzing",
                            f"Optimizing & building tree... ({len(full_output)} chars)",
                            "running",
                        )
                elif event["type"] == "end":
                    token_usage = event.get("usage", token_usage)
                    if event.get("stop_reason") == "cancelled":
                        raise asyncio.CancelledError("Tree generation cancelled")
                    if event.get("stop_reason") in ("max_tokens", "length"):
                        was_truncated = True
                        logger.warning(
                            f"Optimized tree generation truncated at max_tokens={max_tokens} "
                            f"({len(full_output)} chars collected)"
                        )
                        await emit(
                            "analyzing",
                            "Response was truncated — attempting recovery...",
                            "running",
                        )
            # Stream completed successfully
            break

        except asyncio.CancelledError:
            raise
        except Exception as e:
            is_server_error = (
                "500" in str(e)
                or "Internal server error" in str(e)
                or "api_error" in str(e)
            )
            if is_server_error and attempt < max_retries:
                wait = 3 * (attempt + 1)
                logger.warning(
                    f"LLM API error (attempt {attempt + 1}/{max_retries + 1}), "
                    f"retrying in {wait}s: {e}"
                )
                await emit(
                    "analyzing",
                    f"API error — retrying in {wait}s "
                    f"(attempt {attempt + 2}/{max_retries + 1})...",
                    "running",
                )
                await asyncio.sleep(wait)
                continue
            logger.exception("Optimized tree generation failed")
            raise ValueError(f"Optimized tree generation failed: {e}") from e

    if not full_output.strip():
        raise ValueError("LLM returned empty response for optimized tree generation")

    # 4. Parse and validate tree output (reuse tree_builder utilities)
    await emit("validating", "Parsing optimized tree structure...", "running")

    try:
        tree_data = parse_tree_output(full_output)
    except ValueError:
        logger.error("Failed to parse optimized tree output: %s", full_output[:500])
        raise

    tree_data = validate_tree(tree_data)

    # Count leaves for summary
    leaf_count = _count_leaves(tree_data)

    if was_truncated:
        if leaf_count < len(contexts) * 0.5:
            logger.warning(
                "Optimized tree may have data loss: %d leaves from %d inputs (truncated)",
                leaf_count,
                len(contexts),
            )
        await emit(
            "validating",
            f"Tree recovered from truncated response — "
            f"{leaf_count} optimized leaves (some may be missing)",
            "done",
        )
    else:
        await emit(
            "analyzing",
            f"Optimized {len(contexts)} contexts into {leaf_count} consolidated documents",
            "done",
        )
        await emit("validating", "Tree structure validated", "done")

    return {
        "tree_data": tree_data,
        "model_used": model,
        "provider_used": provider,
        "token_usage": token_usage,
        "system_prompt_used": system_prompt[:500] + "...",  # truncate for storage
    }


def _count_leaves(node: dict) -> int:
    """Count leaf nodes in the tree."""
    if node.get("type") == "leaf":
        return 1
    count = 0
    for child in node.get("children", []):
        if isinstance(child, dict):
            count += _count_leaves(child)
    return count
