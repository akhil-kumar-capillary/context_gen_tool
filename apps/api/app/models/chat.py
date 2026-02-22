"""Chat models — conversation and message persistence."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class ChatConversation(Base):
    __tablename__ = "chat_conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    org_id = Column(Integer, nullable=False, index=True)
    title = Column(String(255), default="New Chat")
    provider = Column(String(50), default="anthropic")
    model = Column(String(100), default="claude-sonnet-4-20250514")
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    messages = relationship(
        "ChatMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("chat_conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role = Column(String(20), nullable=False)  # 'user', 'assistant', 'tool_result'
    content = Column(Text)
    tool_calls = Column(JSONB)  # [{name, id, input, result}] for assistant messages
    tool_results = Column(JSONB)  # [{tool_use_id, content}] for tool_result messages
    token_usage = Column(JSONB)  # {input_tokens, output_tokens}
    created_at = Column(DateTime(timezone=True), default=utcnow)

    conversation = relationship("ChatConversation", back_populates="messages")
