from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, Index, Float
from sqlalchemy.sql import func
from backend.db.database import Base


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    alert_type = Column(String(30), nullable=False, index=True)
    severity = Column(String(10), nullable=False, default="medium")
    camera_location = Column(String(50), nullable=True)
    camera_id = Column(String(50), nullable=True)
    track_id = Column(Integer, nullable=True)
    person_name = Column(String(100), nullable=True)
    plate_number = Column(String(20), nullable=True)
    evidence_id = Column(Integer, nullable=True)

    message = Column(Text, nullable=True)
    details = Column(Text, nullable=True)

    acknowledged = Column(Boolean, default=False)
    acknowledged_by = Column(Integer, nullable=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    dismissed = Column(Boolean, default=False)
    escalated_at = Column(DateTime(timezone=True), nullable=True)   # backup officers paged after no acknowledgement

    channels_sent = Column(String(100), nullable=True)

    # Human review: identification-type alerts stay "pending" until an operator
    # confirms or rejects; external webhooks are held until "confirmed".
    review_status = Column(String(12), nullable=False, default="pending", server_default="pending")
    reviewed_by = Column(Integer, nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    review_note = Column(Text, nullable=True)

    __table_args__ = (
        Index("idx_alert_timestamp", "timestamp", "alert_type"),
        Index("idx_alert_unacknowledged", "acknowledged", "dismissed"),
    )
