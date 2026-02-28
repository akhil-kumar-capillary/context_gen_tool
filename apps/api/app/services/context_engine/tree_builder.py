"""Tree Builder — LLM-powered context tree structuring.

Sends collected contexts to LLM and asks it to organize them into a
hierarchical tree with health scores, analysis, and secret detection.

The LLM returns a *lightweight* tree (summaries only in desc fields).
After parsing, we attach the original full content back to each leaf
by matching on source_doc_key / name.  This keeps the LLM output small
and avoids truncation.
"""
import asyncio
import json
import logging
import re
from typing import Any, Callable, Awaitable

from app.services.llm_service import stream_llm

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, str, str], Awaitable[None]]

# ---------------------------------------------------------------------------
# System prompt — instructs LLM to build the tree
# ---------------------------------------------------------------------------

TREE_SYSTEM_PROMPT = """\
You are a context organization expert. You will receive ALL context documents \
for an organization. Your job is to analyze them and organize them into a \
hierarchical tree structure.

## Tree Structure Rules:
- Root node: "Organization Context" (type: "root", id: "root")
- Categories: Logical groupings (type: "cat") — e.g. "Analytics & SQL", \
"Loyalty & Rewards", "Campaigns & Messaging"
- Leaf nodes: Individual context items (type: "leaf")

## For each node you must provide:
- id: unique snake_case identifier (e.g. "analytics_sql", "loyalty_master_rules")
- name: human-readable display name
- type: "root" | "cat" | "leaf"
- health: 0-100 score based on content quality, freshness, redundancy
- visibility: "public" (general use) | "private" (contains sensitive data \
like API keys, test data)
- children: array of child nodes (for root and cat types)

## For leaf nodes additionally provide:
- desc: A concise summary of the context content (2-3 sentences describing \
what this context covers and its key rules). Do NOT copy the full original \
text — the system will attach full content automatically after parsing.
- source: which pipeline generated it ("databricks", "config_apis", \
"capillary", "manual") — MUST match the Source from the input exactly
- source_doc_key: original doc key if from a pipeline — MUST match the \
Key from the input exactly. If no Key was provided, use the Name instead.

## For category nodes additionally provide:
- secrets: array of detected secrets [{key, scope, type}] if any child \
contains credential references (e.g. API keys, Bearer tokens, passwords)

## Health Scoring Guidelines:
- 90-100: Fresh, well-written, no redundancy, actively useful
- 70-89: Good but may have minor overlap or slightly stale
- 50-69: Significant redundancy, partial overlap with other nodes, or outdated
- Below 50: Conflicting with other nodes, very stale, or mostly redundant

## Analysis Checks:
For EACH leaf node, also include an "analysis" field:
{
    "redundancy": {"score": 0-100, "overlaps_with": ["node_id_1"], "detail": "..."},
    "conflicts": [{"with_node": "node_id", "description": "...", "severity": "low|medium|high"}],
    "suggestions": ["potential improvement or restructure suggestion"]
}

## Secret Detection:
If any leaf content contains credentials (Bearer tokens, API keys, passwords, \
auth headers), detect them and:
1. List them in the parent category's "secrets" array as: \
{"key": "{{KEY_NAME}}", "scope": "category_name", "type": "Basic Auth|API Key|Token|Password"}
2. Add a "secretRefs" array to the leaf node referencing the key names: ["{{KEY_NAME}}"]
3. Set the leaf's visibility to "private"

## Output Format:
Return ONLY valid JSON — the tree object. No markdown code fences, no \
explanation, no text before or after the JSON. Start with { and end with }.
"""


def _build_user_message(contexts: list[dict], org_id: int) -> str:
    """Build the user message from collected contexts."""
    parts = [
        f"Here are {len(contexts)} context documents for organization {org_id}.\n"
        "Organize them into a tree structure following the system prompt instructions.\n\n"
    ]

    for i, ctx in enumerate(contexts, 1):
        source = ctx.get("source", "unknown")
        name = ctx.get("name", f"Context {i}")
        doc_key = ctx.get("doc_key", "")
        content = ctx.get("content", "")

        parts.append("---\n")
        parts.append(f"Source: {source} | Name: {name}")
        if doc_key:
            parts.append(f" | Key: {doc_key}")
        parts.append(f"\n{content}\n\n")

    return "".join(parts)


# ---------------------------------------------------------------------------
# Post-LLM: attach full original content to leaf nodes
# ---------------------------------------------------------------------------


def _attach_full_content(tree: dict, contexts: list[dict]):
    """Replace LLM summaries with original full content in leaf nodes.

    The LLM only writes short summaries in desc — we match each leaf back
    to the original context by source_doc_key or name and inject the full
    content.
    """
    # Build lookup maps keyed by lowercase name and doc_key
    content_map: dict[str, str] = {}
    for ctx in contexts:
        content = ctx.get("content", "")
        if not content:
            continue
        # Map by doc_key
        doc_key = ctx.get("doc_key", "")
        if doc_key:
            content_map[doc_key.lower().strip()] = content
        # Map by name
        name = ctx.get("name", "")
        if name:
            content_map[name.lower().strip()] = content

    attached = _walk_and_attach(tree, content_map)
    logger.info(f"Attached full content to {attached} leaf nodes")


def _walk_and_attach(node: dict, content_map: dict[str, str]) -> int:
    """Recursively walk tree and replace desc with full content."""
    count = 0
    if node.get("type") == "leaf":
        # Try matching by source_doc_key first, then name
        key = (node.get("source_doc_key") or "").lower().strip()
        name = (node.get("name") or "").lower().strip()
        full = content_map.get(key) or content_map.get(name)
        if full:
            node["desc"] = full
            count += 1

    for child in node.get("children", []):
        if isinstance(child, dict):
            count += _walk_and_attach(child, content_map)
    return count


# ---------------------------------------------------------------------------
# JSON parsing — robust extraction with truncation recovery
# ---------------------------------------------------------------------------


def _parse_tree_output(text: str) -> dict:
    """Parse LLM tree output — handles code fences, truncation, etc.

    Reuses the robust parsing strategy from context_tools._parse_refactor_output
    but adapted for a single JSON object (tree) instead of an array.
    """
    text = text.strip()

    # Strip code fences (```json ... ```)
    if text.startswith("```"):
        lines = text.split("\n")
        start = 1
        end = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
        text = "\n".join(lines[start:end]).strip()

    # Also strip trailing ``` if present
    if text.endswith("```"):
        text = text[:-3].strip()

    parsed = None

    # Try 1: Direct JSON parse
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try 2: Extract JSON object from surrounding text
    if parsed is None:
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            try:
                parsed = json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

    # Try 3: Truncation recovery — progressively trim and close brackets
    if parsed is None:
        obj_start = text.find("{")
        if obj_start != -1:
            partial = text[obj_start:]

            # Strategy: find the last point where we can cleanly truncate,
            # then close all open brackets.
            # Walk backward from the end to find a safe truncation point:
            # after a complete value (number, string, true/false/null, ] or })
            parsed = _recover_truncated_json(partial)

    if not isinstance(parsed, dict):
        raise ValueError(
            f"Could not parse LLM response as JSON object. "
            f"Response starts with: {text[:200]}"
        )

    return parsed


def _recover_truncated_json(partial: str) -> dict | None:
    """Attempt to recover valid JSON from a truncated string.

    Strategy:
    1. Walk backward from the end to find the last "safe" truncation point
       (after a closing } or ], after a string value, after a number, etc.)
    2. Remove any trailing comma
    3. Close all remaining open brackets/braces
    4. Try to parse
    """
    # Try multiple truncation points going backward
    # Look for the last occurrence of these safe endings: }, ], "string", number, true, false, null
    safe_endings = [
        ('"', 'string'),
        ('}', 'object_close'),
        (']', 'array_close'),
    ]

    # First, try the naive bracket-completion approach
    result = _try_bracket_completion(partial)
    if result is not None:
        return result

    # If that failed, try progressively shorter substrings
    # Find all positions of closing braces/brackets as candidate truncation points
    candidates = []
    for i in range(len(partial) - 1, 0, -1):
        ch = partial[i]
        if ch in ('}', ']', '"') or partial[i:i+4] in ('true', 'null') or partial[i:i+5] == 'false':
            candidates.append(i + 1)
        if len(candidates) > 50:
            break  # don't search too far back

    for end_pos in candidates:
        truncated = partial[:end_pos]
        result = _try_bracket_completion(truncated)
        if result is not None:
            logger.warning(
                f"Tree output truncated — recovered by trimming "
                f"{len(partial) - end_pos} chars from end"
            )
            return result

    return None


def _try_bracket_completion(text: str) -> dict | None:
    """Try to complete truncated JSON by closing open brackets and braces."""
    # Remove trailing incomplete tokens (partial strings, trailing commas, colons)
    cleaned = text.rstrip()

    # Remove trailing comma if present
    if cleaned.endswith(","):
        cleaned = cleaned[:-1]

    # Remove trailing colon (incomplete key-value)
    if cleaned.endswith(":"):
        # Remove the incomplete key:value — go back to before the key
        # Find the last comma or opening bracket before this
        last_safe = max(cleaned.rfind(","), cleaned.rfind("{"), cleaned.rfind("["))
        if last_safe > 0:
            cleaned = cleaned[:last_safe + 1]
            # If we ended at a comma, it's fine. If at { or [, also fine.

    # Count unmatched brackets
    open_braces = 0
    open_brackets = 0
    in_string = False
    escape = False

    for ch in cleaned:
        if escape:
            escape = False
            continue
        if ch == '\\' and in_string:
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == '{':
            open_braces += 1
        elif ch == '}':
            open_braces -= 1
        elif ch == '[':
            open_brackets += 1
        elif ch == ']':
            open_brackets -= 1

    # If we're inside an unclosed string, close it
    if in_string:
        cleaned += '"'

    # Remove trailing comma after closing the string
    if cleaned.endswith('",'):
        pass  # comma is fine if followed by more content
    elif cleaned.endswith(','):
        cleaned = cleaned[:-1]

    # Close any open brackets/braces
    closes = "]" * max(open_brackets, 0) + "}" * max(open_braces, 0)
    fixed = cleaned + closes

    try:
        result = json.loads(fixed)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

    return None


def _validate_tree(tree: dict) -> dict:
    """Basic validation and normalization of the tree structure."""
    # Ensure required fields on root
    tree.setdefault("id", "root")
    tree.setdefault("name", "Organization Context")
    tree.setdefault("type", "root")
    tree.setdefault("health", 0)
    tree.setdefault("visibility", "public")
    tree.setdefault("children", [])

    # Recursively validate children
    _validate_node(tree)

    # Compute aggregate health if root health is 0
    if tree["health"] == 0 and tree["children"]:
        tree["health"] = _compute_aggregate_health(tree)

    return tree


def _validate_node(node: dict, depth: int = 0):
    """Recursively validate and normalize tree nodes."""
    node.setdefault("id", f"node_{depth}_{id(node)}")
    node.setdefault("name", "Unnamed")
    node.setdefault("type", "leaf" if depth > 1 else "cat")
    node.setdefault("health", 70)
    node.setdefault("visibility", "public")

    children = node.get("children", [])
    if isinstance(children, list):
        for child in children:
            if isinstance(child, dict):
                _validate_node(child, depth + 1)


def _compute_aggregate_health(node: dict) -> int:
    """Compute weighted average health from children."""
    children = node.get("children", [])
    if not children:
        return node.get("health", 70)

    total = 0
    count = 0
    for child in children:
        if isinstance(child, dict):
            if child.get("children"):
                h = _compute_aggregate_health(child)
            else:
                h = child.get("health", 70)
            total += h
            count += 1

    return round(total / max(count, 1))


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------


async def build_tree(
    contexts: list[dict],
    org_id: int,
    progress_cb: ProgressCallback | None = None,
    cancel_event: asyncio.Event | None = None,
    provider: str = "anthropic",
    model: str = "claude-opus-4-6",
    max_tokens: int = 16000,
    skip_content_attach: bool = False,
) -> dict[str, Any]:
    """Ask LLM to organize contexts into a hierarchical tree.

    The LLM returns a lightweight tree with concise summaries in leaf desc
    fields.  After parsing, we attach the original full context content
    back to each leaf by matching on source_doc_key / name.

    Args:
        contexts: List of context dicts from the collector.
        org_id: Organization ID.
        progress_cb: Async callback(phase, detail, status) for progress updates.
        cancel_event: Event to cancel the stream.
        provider: LLM provider.
        model: LLM model.
        max_tokens: Max output tokens.
        skip_content_attach: If True, skip attaching original content to leaves.
            Used when the sanitizer will handle content attachment instead.

    Returns:
        {
            "tree_data": {...},     # the parsed tree
            "model_used": "...",
            "provider_used": "...",
            "token_usage": {"input_tokens": N, "output_tokens": N},
            "system_prompt_used": "...",
        }
    """
    async def emit(phase: str, detail: str, status: str = "running"):
        if progress_cb:
            await progress_cb(phase, detail, status)

    await emit("analyzing", f"Sending {len(contexts)} contexts to LLM...", "running")

    user_message = _build_user_message(contexts, org_id)
    messages = [{"role": "user", "content": user_message}]

    # Stream LLM response (collect full output) — with retry on transient errors
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
                system=TREE_SYSTEM_PROMPT,
                messages=messages,
                max_tokens=max_tokens,
                cancel_event=cancel_event,
            ):
                if event["type"] == "chunk":
                    full_output += event["text"]
                    # Emit periodic progress
                    if len(full_output) % 2000 < len(event["text"]):
                        await emit(
                            "analyzing",
                            f"Building tree structure... ({len(full_output)} chars)",
                            "running",
                        )
                elif event["type"] == "end":
                    token_usage = event.get("usage", token_usage)
                    if event.get("stop_reason") == "cancelled":
                        raise asyncio.CancelledError("Tree generation cancelled")
                    if event.get("stop_reason") in ("max_tokens", "length"):
                        was_truncated = True
                        logger.warning(
                            f"Tree generation truncated at max_tokens={max_tokens} "
                            f"({len(full_output)} chars collected)"
                        )
                        await emit(
                            "analyzing",
                            "Response was truncated — attempting recovery...",
                            "running",
                        )
            # Stream completed successfully — break out of retry loop
            break

        except asyncio.CancelledError:
            raise
        except Exception as e:
            is_server_error = "500" in str(e) or "Internal server error" in str(e) or "api_error" in str(e)
            if is_server_error and attempt < max_retries:
                wait = 3 * (attempt + 1)
                logger.warning(f"LLM API error (attempt {attempt + 1}/{max_retries + 1}), retrying in {wait}s: {e}")
                await emit(
                    "analyzing",
                    f"API error — retrying in {wait}s (attempt {attempt + 2}/{max_retries + 1})...",
                    "running",
                )
                await asyncio.sleep(wait)
                continue
            logger.exception("LLM tree generation failed")
            raise ValueError(f"LLM tree generation failed: {e}") from e

    if not full_output.strip():
        raise ValueError("LLM returned empty response for tree generation")

    # Parse the tree output
    await emit("validating", "Parsing tree structure...", "running")

    try:
        tree_data = _parse_tree_output(full_output)
    except ValueError:
        logger.error("Failed to parse tree output: %s", full_output[:500])
        raise

    # Validate and normalize
    tree_data = _validate_tree(tree_data)

    if was_truncated:
        await emit("validating", "Tree recovered from truncated response (some nodes may be missing)", "done")
    else:
        await emit("validating", "Tree structure validated", "done")

    # Attach full original content to leaf nodes (unless sanitizer will handle it)
    if not skip_content_attach:
        await emit("validating", "Attaching full context content to leaves...", "running")
        _attach_full_content(tree_data, contexts)
        await emit("validating", "Full content attached", "done")
    else:
        await emit("validating", "Skipping content attach (sanitization will handle it)", "done")

    return {
        "tree_data": tree_data,
        "model_used": model,
        "provider_used": provider,
        "token_usage": token_usage,
        "system_prompt_used": TREE_SYSTEM_PROMPT,
    }
