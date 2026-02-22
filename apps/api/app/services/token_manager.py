"""Token budget management and text chunking for LLM operations."""
import logging

logger = logging.getLogger(__name__)


def estimate_tokens(text: str) -> int:
    """Rough token count estimate (1 token ~ 4 chars for English text)."""
    return len(text) // 4


def chunk_text(text: str, max_tokens: int, overlap_tokens: int = 200) -> list[str]:
    """Split text into chunks that fit within token limits.
    Uses a sliding window with overlap to preserve context across chunks.
    """
    max_chars = max_tokens * 4
    overlap_chars = overlap_tokens * 4
    chunks = []
    start = 0

    while start < len(text):
        end = start + max_chars
        if end >= len(text):
            chunks.append(text[start:])
            break

        # Try to break at a paragraph or sentence boundary
        boundary = text.rfind("\n\n", start + overlap_chars, end)
        if boundary == -1:
            boundary = text.rfind("\n", start + overlap_chars, end)
        if boundary == -1:
            boundary = text.rfind(". ", start + overlap_chars, end)
        if boundary == -1:
            boundary = end

        chunks.append(text[start:boundary])
        start = boundary - overlap_chars if boundary > overlap_chars else boundary

    return chunks


def format_contexts_for_llm(
    contexts: list[dict],
    max_output_tokens: int,
) -> tuple[str, int]:
    """Format context documents for the sanitize/refactoring flow.
    Returns: (formatted_text, per_doc_budget)

    Matches the pattern from context-management-desktop's formatContextsForLLM.
    """
    per_doc_budget = max_output_tokens // max(len(contexts), 1)

    parts = []
    for i, ctx in enumerate(contexts, 1):
        name = ctx.get("name", f"Context_{i}")
        content = ctx.get("content", ctx.get("context", ""))
        scope = ctx.get("scope", "org")
        parts.append(
            f"--- Context {i}: {name} (scope: {scope}) ---\n{content}\n"
        )

    formatted = "\n".join(parts)
    return formatted, per_doc_budget


def cap_payload(payload: str, max_chars: int) -> str:
    """Cap payload text to max_chars, trying to preserve structure."""
    if len(payload) <= max_chars:
        return payload

    # Truncate at the last complete paragraph before limit
    truncated = payload[:max_chars]
    last_para = truncated.rfind("\n\n")
    if last_para > max_chars * 0.5:
        truncated = truncated[:last_para]

    logger.warning(f"Payload capped: {len(payload)} → {len(truncated)} chars")
    return truncated
