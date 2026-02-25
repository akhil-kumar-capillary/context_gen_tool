import uuid
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Text, ForeignKey,
)
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base
from app.utils import utcnow


class ExtractionRun(Base):
    __tablename__ = "extraction_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Integer, ForeignKey("users.id"))
    org_id = Column(Integer)
    databricks_instance = Column(String(500))
    root_path = Column(String(500))
    modified_since = Column(DateTime)
    total_notebooks = Column(Integer, default=0)
    processed_notebooks = Column(Integer, default=0)
    skipped_notebooks = Column(Integer, default=0)
    total_sqls_extracted = Column(Integer, default=0)
    valid_sqls = Column(Integer, default=0)
    unique_hashes = Column(Integer, default=0)
    api_failures = Column(Integer, default=0)
    status = Column(String(50), default="running")
    started_at = Column(DateTime(timezone=True), default=utcnow)
    completed_at = Column(DateTime(timezone=True))


class ExtractedSQL(Base):
    __tablename__ = "extracted_sqls"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(UUID(as_uuid=True), ForeignKey("extraction_runs.id", ondelete="CASCADE"), index=True)
    org_id = Column(String(50))
    org_id_source = Column(String(100))
    notebook_path = Column(Text, nullable=False)
    notebook_name = Column(String(500))
    user_name = Column(String(255))
    object_id = Column(String(100))
    language = Column(String(50))
    created_at = Column(DateTime(timezone=True))
    modified_at = Column(DateTime(timezone=True))
    cell_number = Column(Integer)
    file_type = Column(String(50))
    cleaned_sql = Column(Text)
    sql_hash = Column(String(64), index=True)
    is_valid = Column(Boolean, default=False)
    original_snippet = Column(Text)
    extracted_at = Column(DateTime(timezone=True), default=utcnow)


class NotebookMetadata(Base):
    __tablename__ = "notebook_metadata"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(UUID(as_uuid=True), ForeignKey("extraction_runs.id", ondelete="CASCADE"), index=True)
    notebook_path = Column(Text, nullable=False)
    notebook_name = Column(String(500))
    user_name = Column(String(255))
    object_id = Column(String(100))
    language = Column(String(50))
    created_at = Column(DateTime(timezone=True))
    modified_at = Column(DateTime(timezone=True))
    has_content = Column(Boolean, default=False)
    file_type = Column(String(50))
    status = Column(String(50), default="Processed")
    is_attached_to_jobs = Column(String(10), default="No")
    job_id = Column(Text)
    job_name = Column(Text)
    cont_success_run_count = Column(Integer)
    earliest_run_date = Column(DateTime(timezone=True))
    trigger_type = Column(String(50))
    extracted_at = Column(DateTime(timezone=True), default=utcnow)
