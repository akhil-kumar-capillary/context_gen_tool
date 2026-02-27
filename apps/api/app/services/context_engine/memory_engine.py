"""Memory Suggestion Engine — analyzes chat history for recurring patterns.

Detects patterns that appear across multiple chat sessions and suggests
they should become permanent context rules in the tree.
"""
import json
import logging
from typing import Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import ChatMessage, ChatConversation
from app.services.llm_service import call_llm

logger = logging.getLogger(__name__)


async def _load_recent_user_messages(
    db: AsyncSession,
    org_id: int,
    user_id: int,
    min_sessions: int = 3,
    limit: int = 200,
) -> list[dict]:
    """Load recent user messages across multiple sessions."""
    # Get conversations for this org
    conv_stmt = (
        select(ChatConversation.id)
        .where(
            ChatConversation.org_id == org_id,
            ChatConversation.user_id == user_id,
        )
        .order_by(ChatConversation.updated_at.desc())
        .limit(50)  # Last 50 conversations
    )
    conv_result = await db.execute(conv_stmt)
    conv_ids = [row[0] for row in conv_result.all()]

    if len(conv_ids) < min_sessions:
        return []

    # Load user messages from those conversations
    msg_stmt = (
        select(ChatMessage)
        .where(
            ChatMessage.conversation_id.in_(conv_ids),
            ChatMessage.role == "user",
        )
        .order_by(ChatMessage.created_at.desc())
        .limit(limit)
    )
    msg_result = await db.execute(msg_stmt)
    messages = msg_result.scalars().all()

    return [
        {
            "text": msg.content[:500] if msg.content else "",
            "conversation_id": str(msg.conversation_id),
            "created_at": msg.created_at.isoformat() if msg.created_at else "",
        }
        for msg in messages
        if msg.content and len(msg.content.strip()) > 10
    ]


async def detect_memory_patterns(
    db: AsyncSession,
    org_id: int,
    user_id: int,
    min_sessions: int = 3,
    min_confidence: int = 70,
    provider: str = "anthropic",
    model: str = "claude-sonnet-4-20250514",
) -> list[dict]:
    """Analyze chat history for recurring patterns.

    Queries ChatMessage table for recurring user requests across sessions.
    Uses LLM to identify patterns that should become permanent context.

    Args:
        db: Database session.
        org_id: Organization ID.
        user_id: User ID.
        min_sessions: Minimum number of sessions a pattern must appear in.
        min_confidence: Minimum confidence score (0-100) to include.
        provider: LLM provider.
        model: LLM model.

    Returns: list of pattern dicts:
        [{
            "pattern": "Always exclude test users from analytics queries",
            "evidence": [{"text": "...", "session_date": "..."}],
            "confidence": 89,
            "sessions": 11,
            "mentions": 17,
            "suggested_node": "Analytics & SQL > SQL Generation Rules",
            "preview": "Exclude users where email LIKE '%@capillarytech.com'...",
        }]
    """
    messages = await _load_recent_user_messages(
        db, org_id, user_id, min_sessions
    )

    if len(messages) < 10:
        return []  # Not enough data

    # Group messages by conversation
    by_conv: dict[str, list[str]] = {}
    for msg in messages:
        conv = msg["conversation_id"]
        if conv not in by_conv:
            by_conv[conv] = []
        by_conv[conv].append(msg["text"])

    if len(by_conv) < min_sessions:
        return []

    # Build prompt for LLM
    system = (
        "You are a pattern detection expert. Analyze user messages from multiple "
        "chat sessions and identify recurring patterns or rules that the user "
        "repeatedly mentions or asks for.\n\n"
        "For each pattern found, output a JSON object:\n"
        "{\n"
        '  "pattern": "brief description of the recurring rule/preference",\n'
        '  "evidence": ["exact quote 1", "exact quote 2", "exact quote 3"],\n'
        '  "confidence": 0-100,\n'
        '  "sessions": number of sessions where this appeared,\n'
        '  "suggested_node": "Category > Leaf Name where this should live",\n'
        '  "preview": "The context rule text that should be added"\n'
        "}\n\n"
        "Output one JSON object per line. If no patterns found, output: NONE\n"
        "Only include patterns with confidence >= " + str(min_confidence) + "."
    )

    # Build user message with session summaries
    session_parts = []
    for conv_id, msgs in list(by_conv.items())[:20]:
        session_parts.append(
            f"--- Session {conv_id[:8]} ---\n" +
            "\n".join(f"User: {m}" for m in msgs[:10])
        )

    user_msg = (
        f"Analyze these {len(by_conv)} chat sessions ({len(messages)} messages) "
        f"for recurring patterns:\n\n" +
        "\n\n".join(session_parts)
    )

    try:
        result = await call_llm(
            provider=provider,
            model=model,
            system=system,
            messages=[{"role": "user", "content": user_msg}],
            max_tokens=2000,
        )

        response_text = ""
        for block in result.get("content", []):
            if block.get("type") == "text":
                response_text += block["text"]

        patterns = []
        for line in response_text.strip().split("\n"):
            line = line.strip()
            if not line or line.upper() == "NONE":
                continue
            try:
                pattern = json.loads(line)
                if pattern.get("confidence", 0) >= min_confidence:
                    # Ensure required fields
                    pattern.setdefault("sessions", 0)
                    pattern.setdefault("mentions", pattern.get("sessions", 0))
                    pattern.setdefault("evidence", [])
                    # Convert evidence strings to dicts if needed
                    evidence = []
                    for e in pattern.get("evidence", []):
                        if isinstance(e, str):
                            evidence.append({"text": e, "session_date": ""})
                        elif isinstance(e, dict):
                            evidence.append(e)
                    pattern["evidence"] = evidence[:5]  # Cap at 5
                    patterns.append(pattern)
            except json.JSONDecodeError:
                continue

        return patterns

    except Exception as e:
        logger.warning(f"Memory pattern detection failed (non-fatal): {e}")
        return []
