import uuid
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.database import Base
from app.utils import utcnow


class ContextTreeRun(Base):
    __tablename__ = "context_tree_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Integer, ForeignKey("users.id"))
    org_id = Column(Integer, nullable=False, index=True)

    # Input: which contexts were used to build the tree
    input_sources = Column(JSONB)          # {databricks: [doc_ids], config_apis: [doc_ids], capillary: [ids], manual: []}
    input_context_count = Column(Integer)

    # The tree structure (prototype-compatible format)
    tree_data = Column(JSONB)              # {id, name, type, health, children: [...]}

    # LLM metadata
    model_used = Column(String(100))
    provider_used = Column(String(50))
    token_usage = Column(JSONB)            # {input_tokens, output_tokens}
    system_prompt_used = Column(Text)

    # Status tracking
    status = Column(String(50), default="running")  # running | completed | failed | cancelled
    error_message = Column(Text)
    progress_data = Column(JSONB)          # [{phase, detail, status}, ...]

    created_at = Column(DateTime(timezone=True), default=utcnow)
    completed_at = Column(DateTime(timezone=True))
