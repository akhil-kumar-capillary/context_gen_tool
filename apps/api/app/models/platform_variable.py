from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey

from app.database import Base
from app.utils import utcnow


class PlatformVariable(Base):
    __tablename__ = "platform_variables"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(255), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=True)
    value_type = Column(String(20), nullable=False, default="string")
    group_name = Column(String(100), nullable=True, index=True)
    description = Column(String(500), nullable=True)
    default_value = Column(Text, nullable=True)
    is_required = Column(Boolean, default=False)
    validation_rule = Column(String(500), nullable=True)
    sort_order = Column(Integer, default=0)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
