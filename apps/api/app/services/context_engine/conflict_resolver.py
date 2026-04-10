"""Conflict Resolver — LLM-assisted contradiction detection between contexts.

Compares context documents pairwise (batched) to find contradicting
rules, instructions, or facts. Returns structured conflicts for user review.
"""
import asyncio
import json
import logging
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Awaitable

from app.services.llm_service import call_llm

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, str, str], Awaitable[None]]

CONFLICT_SYSTEM_PROMPT = """\
You are a knowledge consistency auditor. You will receive pairs of context \
documents and must identify CONTRADICTIONS — places where one document says \
something that directly conflicts with another.

IMPORTANT: Only report REAL contradictions — where following one document's \
instructions would violate another's. Do NOT report:
- Documents covering different topics (not a conflict)
- Different levels of detail (not a conflict)
- Complementary information (not a conflict)

For each contradiction found, return a JSON object:
{
  "conflicts": [
    {
      "doc_a_index": 0,
      "doc_b_index": 1,
      "excerpt_a": "exact quote from doc A that contradicts",
      "excerpt_b": "exact quote from doc B that contradicts",
      "description": "what specifically contradicts and why",
      "severity": "high|medium|low",
      "suggested_resolution": "which doc is likely more authoritative and why"
    }
  ]
}

If NO contradictions exist, return: {"conflicts": []}

Severity guide:
- high: Following one breaks the other (e.g., "always use X" vs "never use X")
- medium: Inconsistent defaults or thresholds
- low: Minor wording differences that could cause confusion
"""


@dataclass
class ConflictItem:
    """A detected contradiction between two context documents."""

    id: str
    doc_a_name: str
    doc_a_key: str
    doc_a_excerpt: str
    doc_b_name: str
    doc_b_key: str
    doc_b_excerpt: str
    description: str
    severity: str  # high | medium | low
    suggested_resolution: str

    def to_dict(self) -> dict:
        return asdict(self)


async def detect_conflicts(
    contexts: list[dict],
    progress_cb: ProgressCallback | None = None,
    batch_size: int = 10,
    provider: str = "anthropic",
    model: str = "claude-sonnet-4-5-20241022",
) -> list[ConflictItem]:
    """Detect contradictions between context documents.

    Batches documents and uses LLM to find pairwise contradictions.
    Returns a list of ConflictItem for user review.
    """
    if len(contexts) < 2:
        return []

    async def emit(detail: str):
        if progress_cb:
            await progress_cb("conflicts", detail, "running")

    # Build batches — each batch gets all-pairs comparison
    batches = _build_batches(contexts, batch_size)
    all_conflicts: list[ConflictItem] = []
    conflict_counter = 0

    await emit(f"Checking {len(batches)} batch(es) for contradictions...")

    for i, batch_contexts in enumerate(batches):
        await emit(f"Analyzing batch {i + 1}/{len(batches)} ({len(batch_contexts)} docs)...")

        try:
            batch_conflicts = await _check_batch(
                batch_contexts, provider, model, conflict_counter,
            )
            all_conflicts.extend(batch_conflicts)
            conflict_counter += len(batch_conflicts)
        except Exception as e:
            logger.warning("Conflict check failed for batch %d: %s", i + 1, e)

    if all_conflicts:
        await emit(f"Found {len(all_conflicts)} contradiction(s)")
    else:
        await emit("No contradictions detected")

    return all_conflicts


def _build_batches(contexts: list[dict], batch_size: int) -> list[list[dict]]:
    """Split contexts into batches for pairwise comparison."""
    if len(contexts) <= batch_size:
        return [contexts]
    return [contexts[i:i + batch_size] for i in range(0, len(contexts), batch_size)]


async def _check_batch(
    batch: list[dict],
    provider: str,
    model: str,
    id_offset: int,
) -> list[ConflictItem]:
    """Send a batch of contexts to LLM for contradiction detection."""
    # Build user message with all docs in the batch
    parts = [f"Compare these {len(batch)} documents for contradictions:\n\n"]
    for i, ctx in enumerate(batch):
        name = ctx.get("name", f"Doc {i}")
        content = ctx.get("content", "")
        # Truncate very long docs to keep within context window
        if len(content) > 3000:
            content = content[:3000] + "\n\n[... truncated for comparison ...]"
        parts.append(f"### Document {i}: {name}\n{content}\n\n---\n\n")

    user_message = "".join(parts)

    result = await call_llm(
        provider=provider,
        model=model,
        system=CONFLICT_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
        max_tokens=4096,
    )

    # Extract text from result
    text = ""
    for block in result.get("content", []):
        if block.get("type") == "text":
            text = block["text"]
            break

    if not text.strip():
        return []

    # Parse JSON response
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Try extracting JSON from response
        import re
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            try:
                data = json.loads(match.group(0))
            except json.JSONDecodeError:
                logger.warning("Could not parse conflict detection response")
                return []
        else:
            return []

    raw_conflicts = data.get("conflicts", [])
    items: list[ConflictItem] = []

    for j, c in enumerate(raw_conflicts):
        idx_a = c.get("doc_a_index", 0)
        idx_b = c.get("doc_b_index", 1)

        if idx_a >= len(batch) or idx_b >= len(batch):
            continue

        doc_a = batch[idx_a]
        doc_b = batch[idx_b]

        severity = c.get("severity", "medium")
        if severity not in ("high", "medium", "low"):
            severity = "medium"

        items.append(ConflictItem(
            id=f"conflict_{id_offset + j}",
            doc_a_name=doc_a.get("name", ""),
            doc_a_key=doc_a.get("doc_key", doc_a.get("name", "")),
            doc_a_excerpt=c.get("excerpt_a", ""),
            doc_b_name=doc_b.get("name", ""),
            doc_b_key=doc_b.get("doc_key", doc_b.get("name", "")),
            doc_b_excerpt=c.get("excerpt_b", ""),
            description=c.get("description", ""),
            severity=severity,
            suggested_resolution=c.get("suggested_resolution", ""),
        ))

    return items
