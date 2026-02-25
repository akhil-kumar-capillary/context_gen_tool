from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.database import Base
from app.utils import utcnow


class ContextDoc(Base):
    __tablename__ = "context_docs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_type = Column(String(50), nullable=False)  # 'databricks', 'confluence', etc.
    source_run_id = Column(UUID(as_uuid=True))
    user_id = Column(Integer, ForeignKey("users.id"))
    org_id = Column(String(50))
    doc_key = Column(String(100), nullable=False)  # '01_MASTER', '02_SCHEMA', etc.
    doc_name = Column(String(255))
    doc_content = Column(Text)
    model_used = Column(String(100))
    provider_used = Column(String(50))
    system_prompt_used = Column(Text)
    payload_sent = Column(JSONB)
    inclusions_used = Column(JSONB)
    token_count = Column(Integer)
    status = Column(String(50), default="active")  # active, superseded, deleted
    created_at = Column(DateTime(timezone=True), default=utcnow)
