"""Shared parsing utilities for LLM refactoring/sanitization output.

Handles code fences, truncation recovery, and name sanitization.
Used by both the context_tools refactor tool and the context engine sanitizer.
"""
import json
import logging
import re

logger = logging.getLogger(__name__)

_NAME_REGEX = re.compile(r"^[a-zA-Z0-9 _:#()\-,]+$")


def parse_refactor_output(
    text: str,
    expected_count: int | None = None,
) -> list[dict]:
    """Parse LLM refactoring output — handles code fences, truncation, name sanitization.

    Ported from the desktop app's parse-llm-response.ts for consistency.

    Args:
        text: Raw LLM output (JSON array of docs).
        expected_count: If provided, logs a warning when fewer docs are
            recovered than expected (indicates truncation data loss).

    Returns a list of dicts, each with keys: name, content, scope.
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

    if expected_count is not None and len(result) < expected_count:
        logger.warning(
            "Parsed %d docs out of %d expected "
            "(lost %d from truncated output)",
            len(result),
            expected_count,
            expected_count - len(result),
        )

    return result
