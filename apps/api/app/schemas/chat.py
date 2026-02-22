"""Pydantic schemas for the chat feature."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class ChatMessageRequest(BaseModel):
    content: str
    conversation_id: Optional[str] = None
    provider: str = "anthropic"
    model: str = "claude-sonnet-4-20250514"


class ToolCallInfo(BaseModel):
    name: str
    id: str
    input: dict
    result: Optional[str] = None
    elapsed_seconds: Optional[float] = None


class ChatMessageResponse(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: Optional[str] = None
    tool_calls: Optional[list[ToolCallInfo]] = None
    token_usage: Optional[dict] = None
    created_at: datetime


class ConversationResponse(BaseModel):
    id: str
    title: str
    provider: str
    model: str
    created_at: datetime
    updated_at: datetime
    message_count: Optional[int] = None


class ConversationDetailResponse(BaseModel):
    id: str
    title: str
    provider: str
    model: str
    created_at: datetime
    updated_at: datetime
    messages: list[ChatMessageResponse]
