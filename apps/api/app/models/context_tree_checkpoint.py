import uuid
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.database import Base
from app.utils import utcnow


class ContextTreeCheckpoint(Base):
    __tablename__ = "context_tree_checkpoints"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("context_tree_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    org_id = Column(Integer, nullable=False, index=True)

    label = Column(String(255), default="")
    tree_data = Column(JSONB, nullable=False)

    # Summary metadata
    change_summary = Column(Text)
    node_count = Column(Integer)
    leaf_count = Column(Integer)
    health_score = Column(Integer)

    created_at = Column(DateTime(timezone=True), default=utcnow)
