"""Chat router — WebSocket endpoint for streaming chat + REST for conversation CRUD."""
import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.core.auth import get_current_user, decode_session_token
from app.core.websocket import ws_manager
from app.database import get_db
from app.models.chat import ChatConversation, ChatMessage
from app.services.chat_orchestrator import ChatOrchestrator
from app.services.tools.tool_context import ToolContext

# Import tool modules to trigger registration
import app.services.tools.context_tools  # noqa: F401
import app.services.tools.databricks_tools  # noqa: F401
import app.services.tools.confluence_tools  # noqa: F401
import app.services.tools.config_api_tools  # noqa: F401
import app.services.tools.context_engine_tools  # noqa: F401

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# WebSocket — streaming chat
# ---------------------------------------------------------------------------


@router.websocket("/ws/chat")
async def chat_websocket(websocket: WebSocket):
    """WebSocket endpoint for streaming AI chat with tool calling.

    Protocol:
      Client → Server:
        {type: "chat_message", content: "...", conversation_id: "...", provider: "...", model: "...", org_id: ...}

      Server → Client:
        {type: "chat_chunk", text: "..."}
        {type: "tool_preparing", tool: "...", tool_id: "...", display: "..."}
        {type: "tool_start", tool: "...", tool_id: "...", display: "..."}
        {type: "tool_end", tool: "...", tool_id: "...", summary: "..."}
        {type: "chat_end", conversation_id: "...", usage: {...}, tool_calls: [...]}
        {type: "error", message: "..."}
    """
    # Authenticate via query parameter
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(4001, "Missing token")
        return

    try:
        user = decode_session_token(token)
    except Exception:
        await websocket.close(4001, "Invalid token")
        return

    connection_id = str(uuid.uuid4())
    user_id = user.get("user_id")

    await ws_manager.connect(websocket, connection_id, user_id)

    # Per-connection cancel event — set when client sends {"type": "cancel"}
    cancel_event = asyncio.Event()

    # Track the currently-running chat task so the receive loop stays free
    # to process cancel / ping messages while the LLM streams.
    active_chat_task: asyncio.Task | None = None

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await ws_manager.send_to_connection(
                    connection_id, {"type": "error", "message": "Invalid JSON"}
                )
                continue

            msg_type = msg.get("type")

            if msg_type == "ping":
                await ws_manager.send_to_connection(connection_id, {"type": "pong"})
                continue

            if msg_type == "cancel":
                logger.info(f"Chat cancel requested (connection={connection_id})")
                cancel_event.set()
                continue

            if msg_type == "chat_message":
                # If a previous chat is still running, cancel it first
                if active_chat_task and not active_chat_task.done():
                    cancel_event.set()
                    try:
                        await asyncio.wait_for(active_chat_task, timeout=2.0)
                    except (asyncio.TimeoutError, Exception):
                        active_chat_task.cancel()

                # Reset cancel event for new message
                cancel_event.clear()

                # Run as a background task so the receive loop stays free
                # to read cancel messages while LLM streams
                active_chat_task = asyncio.create_task(
                    _handle_chat_message(
                        msg=msg,
                        user=user,
                        connection_id=connection_id,
                        cancel_event=cancel_event,
                    )
                )
            else:
                await ws_manager.send_to_connection(
                    connection_id,
                    {"type": "error", "message": f"Unknown message type: {msg_type}"},
                )

    except WebSocketDisconnect:
        cancel_event.set()  # Cancel any in-flight processing
        if active_chat_task and not active_chat_task.done():
            active_chat_task.cancel()
        await ws_manager.disconnect(connection_id, user_id)
    except RuntimeError:
        # Starlette raises RuntimeError when WS is already closed
        logger.info(f"Chat WebSocket closed (connection={connection_id})")
        cancel_event.set()
        if active_chat_task and not active_chat_task.done():
            active_chat_task.cancel()
        await ws_manager.disconnect(connection_id, user_id)
    except Exception as e:
        logger.exception("Chat WebSocket error")
        cancel_event.set()
        if active_chat_task and not active_chat_task.done():
            active_chat_task.cancel()
        await ws_manager.disconnect(connection_id, user_id)


async def _handle_chat_message(
    msg: dict,
    user: dict,
    connection_id: str,
    cancel_event: asyncio.Event | None = None,
):
    """Process an incoming chat message.

    Uses 3 short-lived DB sessions to avoid holding a connection during
    the (potentially long) LLM streaming phase:
      1. Load/create conversation + save user message  (quick DB)
      2. Run LLM orchestrator with tool calls           (no DB held — tools open their own)
      3. Persist assistant response                      (quick DB)
    """
    from app.database import async_session

    content = msg.get("content", "").strip()
    if not content:
        await ws_manager.send_to_connection(
            connection_id, {"type": "error", "message": "Empty message"}
        )
        return

    conversation_id = msg.get("conversation_id")
    provider = msg.get("provider", "anthropic")
    model = msg.get("model", "claude-sonnet-4-20250514")
    org_id = msg.get("org_id")

    if not org_id:
        await ws_manager.send_to_connection(
            connection_id, {"type": "error", "message": "org_id is required"}
        )
        return

    try:
        # ── Phase 1: Load conversation + save user message (short DB session) ──
        conv_id = None
        llm_messages: list[dict] = []
        is_first_message = False

        async with async_session() as db:
            conversation = None
            if conversation_id:
                result = await db.execute(
                    select(ChatConversation)
                    .options(selectinload(ChatConversation.messages))
                    .where(ChatConversation.id == conversation_id)
                )
                conversation = result.scalar_one_or_none()

            if not conversation:
                conversation = ChatConversation(
                    user_id=user["user_id"],
                    org_id=org_id,
                    title=content[:100],
                    provider=provider,
                    model=model,
                )
                db.add(conversation)
                await db.flush()
                is_first_message = True

            conv_id = conversation.id

            # Save user message
            user_msg = ChatMessage(
                conversation_id=conv_id,
                role="user",
                content=content,
            )
            db.add(user_msg)

            # Build LLM message history before closing session.
            # For new conversations, skip history (messages relationship is empty
            # and lazy-loading fails in async context — greenlet_spawn error).
            if is_first_message:
                llm_messages = [{"role": "user", "content": content}]
            else:
                llm_messages = _build_llm_messages(conversation, content)

            await db.commit()
        # ── Session released — DB connection returned to pool ──

        # ── Phase 2: Run LLM orchestrator (no DB connection held) ──
        # Tools that need DB will open their own short-lived sessions.
        # We pass a session factory instead of a live session.
        tool_ctx = ToolContext(
            user=user,
            org_id=org_id,
            db=None,  # Tools open their own sessions via async_session()
            ws_manager=ws_manager,
            ws_connection_id=connection_id,
        )

        orchestrator = ChatOrchestrator(
            provider=provider,
            model=model,
            tool_context=tool_ctx,
        )

        async def _on_text_chunk(text):
            await ws_manager.send_to_connection(
                connection_id, {"type": "chat_chunk", "text": text}
            )

        async def _on_tool_detected(tool, tool_id, display):
            await ws_manager.send_to_connection(
                connection_id,
                {"type": "tool_preparing", "tool": tool, "tool_id": tool_id, "display": display},
            )

        async def _on_tool_start(tool, tool_id, display):
            await ws_manager.send_to_connection(
                connection_id,
                {"type": "tool_start", "tool": tool, "tool_id": tool_id, "display": display},
            )

        async def _on_tool_end(tool, tool_id, summary):
            await ws_manager.send_to_connection(
                connection_id,
                {"type": "tool_end", "tool": tool, "tool_id": tool_id, "summary": summary},
            )

        async def _on_end(usage):
            pass  # We send chat_end after persisting

        result = await orchestrator.run(
            messages=llm_messages,
            on_text_chunk=_on_text_chunk,
            on_tool_detected=_on_tool_detected,
            on_tool_start=_on_tool_start,
            on_tool_end=_on_tool_end,
            on_end=_on_end,
            cancel_event=cancel_event,
        )

        was_cancelled = result.get("cancelled", False)

        # On cancel, send chat_end immediately so the frontend gets instant
        # feedback — before the DB persist.
        if was_cancelled:
            await ws_manager.send_to_connection(
                connection_id,
                {
                    "type": "chat_end",
                    "conversation_id": str(conv_id),
                    "usage": result["usage"],
                    "tool_calls": [],
                },
            )

        # ── Phase 3: Persist assistant response (short DB session) ──
        async with async_session() as db:
            assistant_msg = ChatMessage(
                conversation_id=conv_id,
                role="assistant",
                content=result["assistant_text"],
                tool_calls=result["tool_calls"] if result["tool_calls"] else None,
                token_usage=result["usage"],
            )
            db.add(assistant_msg)

            # Update conversation title on first non-cancelled exchange
            if is_first_message and not was_cancelled:
                conv = await db.get(ChatConversation, conv_id)
                if conv:
                    conv.title = content[:100]

            await db.commit()

        # For normal (non-cancelled) completion, send chat_end after persisting
        if not was_cancelled:
            await ws_manager.send_to_connection(
                connection_id,
                {
                    "type": "chat_end",
                    "conversation_id": str(conv_id),
                    "usage": result["usage"],
                    "tool_calls": [
                        {"name": tc["name"], "id": tc["id"]}
                        for tc in result.get("tool_calls", [])
                    ],
                },
            )

    except Exception as e:
        logger.exception("Chat message processing failed")
        await ws_manager.send_to_connection(
            connection_id,
            {"type": "error", "message": f"Failed to process message: {str(e)}"},
        )


def _build_llm_messages(
    conversation: ChatConversation,
    current_content: str,
) -> list[dict]:
    """Build LLM message history from persisted messages.

    Applies sliding window from settings.chat_history_window.
    """
    messages: list[dict] = []

    # Get recent messages (excluding the one we just added)
    existing = sorted(
        [m for m in conversation.messages if m.content != current_content or m.role != "user"],
        key=lambda m: m.created_at,
    )

    # Sliding window
    window = existing[-(settings.chat_history_window):]

    for msg in window:
        if msg.role == "user":
            messages.append({"role": "user", "content": msg.content or ""})
        elif msg.role == "assistant":
            messages.append({"role": "assistant", "content": msg.content or ""})

    # Add current user message
    messages.append({"role": "user", "content": current_content})

    return messages


# ---------------------------------------------------------------------------
# REST — Conversation CRUD
# ---------------------------------------------------------------------------


@router.get("/conversations")
async def list_conversations(
    org_id: int = Query(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all conversations for the current user in the given org."""
    result = await db.execute(
        select(ChatConversation)
        .where(
            ChatConversation.user_id == current_user["user_id"],
            ChatConversation.org_id == org_id,
        )
        .order_by(desc(ChatConversation.updated_at))
    )
    conversations = result.scalars().all()

    # Get message counts
    response = []
    for conv in conversations:
        count_result = await db.execute(
            select(func.count(ChatMessage.id)).where(
                ChatMessage.conversation_id == conv.id
            )
        )
        msg_count = count_result.scalar()
        response.append({
            "id": str(conv.id),
            "title": conv.title,
            "provider": conv.provider,
            "model": conv.model,
            "created_at": conv.created_at.isoformat(),
            "updated_at": conv.updated_at.isoformat(),
            "message_count": msg_count,
        })

    return response


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a conversation with all its messages."""
    result = await db.execute(
        select(ChatConversation)
        .options(selectinload(ChatConversation.messages))
        .where(
            ChatConversation.id == conversation_id,
            ChatConversation.user_id == current_user["user_id"],
        )
    )
    conversation = result.scalar_one_or_none()
    if not conversation:
        raise HTTPException(404, "Conversation not found")

    return {
        "id": str(conversation.id),
        "title": conversation.title,
        "provider": conversation.provider,
        "model": conversation.model,
        "created_at": conversation.created_at.isoformat(),
        "updated_at": conversation.updated_at.isoformat(),
        "messages": [
            {
                "id": str(m.id),
                "conversation_id": str(m.conversation_id),
                "role": m.role,
                "content": m.content,
                "tool_calls": m.tool_calls,
                "token_usage": m.token_usage,
                "created_at": m.created_at.isoformat(),
            }
            for m in sorted(conversation.messages, key=lambda m: m.created_at)
        ],
    }


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a conversation and all its messages."""
    result = await db.execute(
        select(ChatConversation).where(
            ChatConversation.id == conversation_id,
            ChatConversation.user_id == current_user["user_id"],
        )
    )
    conversation = result.scalar_one_or_none()
    if not conversation:
        raise HTTPException(404, "Conversation not found")

    await db.delete(conversation)
    await db.commit()
    return {"success": True}
