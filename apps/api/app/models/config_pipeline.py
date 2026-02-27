"""
DB models for the Config APIs extraction → analysis pipeline.

ConfigExtractionRun  – stores raw fetched API data (JSONB)
ConfigAnalysisRun    – stores computed analysis of extraction data (JSONB)
"""

import uuid
from sqlalchemy import (
    Column, Integer, String, DateTime, Text, ForeignKey,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.database import Base
from app.utils import utcnow


class ConfigExtractionRun(Base):
    """One extraction run — aggregated raw JSON from selected API categories."""

    __tablename__ = "config_extraction_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Integer, ForeignKey("users.id"))
    org_id = Column(Integer, nullable=False)
    host = Column(String(500), nullable=False)

    # Which categories were selected (list of category IDs)
    categories = Column(JSONB)  # ["loyalty", "campaigns", ...]
    # Per-category user params (JSONB dict)
    category_params = Column(JSONB)  # {"campaigns": {"limit": 50}, ...}

    # Aggregated raw data — keyed by category
    extracted_data = Column(JSONB)  # {"loyalty": {...}, "campaigns": {...}, ...}

    # Extraction stats — counts, warnings, timing
    stats = Column(JSONB)  # {"loyalty": {"apis": 5, "success": 4, "failed": 1, "duration_s": 12.3}, ...}

    # Per-API-call results — structured log for full visibility
    api_call_log = Column(JSONB)  # {"loyalty": [{"api_name": "programs", "status": "success", "http_status": 200, "item_count": 3, "duration_ms": 245}, ...], ...}

    status = Column(String(50), default="running")  # running | completed | failed | cancelled
    error_message = Column(Text)

    started_at = Column(DateTime(timezone=True), default=utcnow)
    completed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=utcnow)


class ConfigAnalysisRun(Base):
    """One analysis run — computed patterns/counts from an extraction run."""

    __tablename__ = "config_analysis_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("config_extraction_runs.id", ondelete="CASCADE"),
        index=True,
    )
    user_id = Column(Integer, ForeignKey("users.id"))
    org_id = Column(Integer, nullable=False)

    # Full analysis output — keyed by analysis phase
    analysis_data = Column(JSONB)

    version = Column(Integer, default=1)
    status = Column(String(50), default="running")  # running | completed | failed | cancelled
    error_message = Column(Text)

    created_at = Column(DateTime(timezone=True), default=utcnow)
    completed_at = Column(DateTime(timezone=True))
