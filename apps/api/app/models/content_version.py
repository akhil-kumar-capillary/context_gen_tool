import uuid
from sqlalchemy import (
    Column, Integer, String, DateTime, Text, ForeignKey,
    UniqueConstraint, Index,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.database import Base
from app.utils import utcnow


class ContentVersion(Base):
    __tablename__ = "content_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Polymorphic entity reference
    entity_type = Column(String(50), nullable=False)    # "context_tree" | "aira_context"
    entity_id = Column(String(255), nullable=False)     # run UUID or Capillary context_id

    # Version tracking
    version_number = Column(Integer, nullable=False)

    # Snapshot data
    snapshot = Column(JSONB, nullable=False)             # full state at this version
    previous_snapshot = Column(JSONB)                    # state before change (for fast diff)

    # Change metadata
    change_type = Column(String(50), nullable=False)     # create|update|archive|restore|add_node|update_node|delete_node|restructure|version_restore
    change_summary = Column(Text)                        # auto-generated human-readable
    changed_fields = Column(JSONB)                       # e.g. ["name","content"] or ["tree_data"]

    # Authorship
    changed_by_user_id = Column(Integer, ForeignKey("users.id"))
    org_id = Column(Integer, nullable=False)

    created_at = Column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        UniqueConstraint(
            "entity_type", "entity_id", "version_number",
            name="uq_entity_version",
        ),
        Index("ix_cv_entity_lookup", "entity_type", "entity_id", "version_number"),
        Index("ix_cv_org", "org_id"),
    )
