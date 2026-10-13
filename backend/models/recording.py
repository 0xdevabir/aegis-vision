"""Continuous / event-triggered recording index for timeline replay."""

from sqlalchemy import Column, Integer, String, DateTime, Float, Index, Text
from sqlalchemy.sql import func
from backend.db.database import Base


class RecordingClip(Base):
    """
    Index of saved video/image clips for VMS-style timeline replay.
    Files live under data/recordings/{camera_id}/ — DB holds metadata.
    """
    __tablename__ = "recording_clips"

    id = Column(Integer, primary_key=True, index=True)
    camera_id = Column(String(50), nullable=False, index=True)
    camera_location = Column(String(100), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=False, index=True)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    duration_seconds = Column(Float, nullable=True)
    trigger = Column(String(40), nullable=False, default="event")  # event|continuous|manual
    alert_type = Column(String(40), nullable=True)
    file_path = Column(String(400), nullable=False)
    file_sha256 = Column(String(64), nullable=True)
    frame_count = Column(Integer, nullable=True)
    thumbnail_path = Column(String(400), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_rec_camera_time", "camera_id", "started_at"),
    )
