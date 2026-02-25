import uuid
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY

from app.database import Base
from app.utils import utcnow


class ManagedContext(Base):
    __tablename__ = "managed_contexts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    org_id = Column(Integer, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    capillary_context_id = Column(String(100))
    name = Column(String(255), nullable=False)
    content = Column(Text)
    scope = Column(String(20), default="org")
    source = Column(String(50))  # 'manual', 'databricks', 'confluence', 'refactored'
    source_doc_id = Column(Integer, ForeignKey("context_docs.id"))
    is_uploaded = Column(Boolean, default=False)
    uploaded_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class RefactoringRun(Base):
    __tablename__ = "refactoring_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Integer, ForeignKey("users.id"))
    org_id = Column(Integer, nullable=False)
    input_context_ids = Column(ARRAY(Integer))
    blueprint_text = Column(Text)
    model_used = Column(String(100))
    provider_used = Column(String(50))
    output_raw = Column(Text)
    output_parsed = Column(JSONB)
    token_usage = Column(JSONB)
    status = Column(String(50), default="running")
    error_message = Column(Text)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    completed_at = Column(DateTime(timezone=True))
