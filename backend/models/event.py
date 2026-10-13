from sqlalchemy import Column, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.sql import func

from backend.db.database import Base


class Event(Base):
    """Structured, searchable record of every observable event (alerts included)."""

    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    event_type = Column(String(30), nullable=False, index=True)
    severity = Column(String(10), nullable=False, default="info")
    camera_id = Column(String(50), nullable=True, index=True)
    camera_location = Column(String(100), nullable=True)
    track_id = Column(Integer, nullable=True)
    zone = Column(String(50), nullable=True)
    person_name = Column(String(100), nullable=True)
    plate_number = Column(String(20), nullable=True)
    confidence = Column(Float, nullable=True)
    alert_id = Column(Integer, nullable=True, index=True)
    evidence_id = Column(Integer, nullable=True)
    clip_id = Column(Integer, nullable=True)
    message = Column(Text, nullable=True)
    meta = Column(Text, nullable=True)          # JSON for type-specific fields

    __table_args__ = (
        Index("idx_event_cam_time", "camera_id", "timestamp"),
        Index("idx_event_type_time", "event_type", "timestamp"),
        Index("idx_event_track", "camera_id", "track_id"),
    )
