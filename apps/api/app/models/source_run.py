import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY, TEXT

from app.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class ConfluenceExtraction(Base):
    __tablename__ = "confluence_extractions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Integer, ForeignKey("users.id"))
    org_id = Column(Integer)
    space_key = Column(String(50))
    space_name = Column(String(255))
    page_ids = Column(ARRAY(TEXT))
    extracted_content = Column(JSONB)  # [{page_id, title, content_md}]
    status = Column(String(50), default="running")
    created_at = Column(DateTime(timezone=True), default=utcnow)
    completed_at = Column(DateTime(timezone=True))


class ConfigApiExtraction(Base):
    __tablename__ = "config_api_extractions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Integer, ForeignKey("users.id"))
    org_id = Column(Integer, nullable=False)
    api_type = Column(String(100), nullable=False)  # 'campaigns', 'promotions', etc.
    extracted_data = Column(JSONB)
    processed_summary = Column(String)
    status = Column(String(50), default="running")
    created_at = Column(DateTime(timezone=True), default=utcnow)
    completed_at = Column(DateTime(timezone=True))
