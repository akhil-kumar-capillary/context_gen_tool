import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, DateTime, Text, ForeignKey,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(UUID(as_uuid=True), ForeignKey("extraction_runs.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    org_id = Column(String(50))
    counters = Column(JSONB)
    clusters = Column(JSONB)
    classified_filters = Column(JSONB)
    fingerprints_summary = Column(JSONB)
    literal_vals = Column(JSONB)
    alias_conv = Column(JSONB)
    total_weight = Column(Integer, default=0)
    version = Column(Integer, default=1)
    status = Column(String(50), default="running")
    created_at = Column(DateTime(timezone=True), default=utcnow)


class AnalysisFingerprint(Base):
    __tablename__ = "analysis_fingerprints"

    id = Column(Integer, primary_key=True, autoincrement=True)
    analysis_id = Column(UUID(as_uuid=True), ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True)
    qfp_id = Column(String(20), nullable=False)
    raw_sql = Column(Text)
    canonical_sql = Column(Text)
    nl_question = Column(Text)
    frequency = Column(Integer, default=1)
    tables_json = Column(JSONB)
    columns_json = Column(JSONB)
    functions_json = Column(JSONB)
    join_graph_json = Column(JSONB)
    where_json = Column(JSONB)
    group_by_json = Column(JSONB)
    having_json = Column(JSONB)
    order_by_json = Column(JSONB)
    literals_json = Column(JSONB)
    case_when_json = Column(JSONB)
    window_json = Column(JSONB)
    structural_flags = Column(JSONB)
    select_col_count = Column(Integer, default=0)
    alias_map_json = Column(JSONB)
    created_at = Column(DateTime(timezone=True), default=utcnow)


class AnalysisNotebook(Base):
    """Linkage between analysis runs and the notebooks that contributed."""
    __tablename__ = "analysis_notebooks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    analysis_id = Column(UUID(as_uuid=True), ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True)
    notebook_id = Column(Integer, ForeignKey("notebook_metadata.id", ondelete="CASCADE"), index=True)
    sql_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=utcnow)
