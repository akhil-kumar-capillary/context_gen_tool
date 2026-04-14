from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey

from app.database import Base
from app.utils import utcnow


class PlatformSettings(Base):
    __tablename__ = "platform_settings"

    id = Column(Integer, primary_key=True, default=1)
    theme_preset = Column(String(50), default="slate_blue")
    primary_hsl_light = Column(String(50), default="215 70% 55%")
    primary_hsl_dark = Column(String(50), default="215 70% 65%")
    dark_mode_default = Column(Boolean, default=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
