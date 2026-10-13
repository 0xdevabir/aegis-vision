from sqlalchemy import Column, Integer, String, Text, DateTime, Index
from sqlalchemy.sql import func
from backend.db.database import Base


class ConfigEntry(Base):
    __tablename__ = "config_entries"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=True)
    description = Column(String(255), nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    updated_by = Column(Integer, nullable=True)

    __table_args__ = (
        Index("idx_config_key", "key"),
    )
