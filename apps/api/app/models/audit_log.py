from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB

from app.database import Base
from app.utils import utcnow


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    user_email = Column(String(255))
    action = Column(String(100), nullable=False, index=True)
    module = Column(String(100))
    resource_type = Column(String(100))
    resource_id = Column(String(100))
    details = Column(JSONB)
    ip_address = Column(String(45))
    created_at = Column(DateTime(timezone=True), default=utcnow, index=True)
