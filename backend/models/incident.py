"""Server-side incident tickets for national-security command workflows."""

from sqlalchemy import (
    Column, Integer, String, DateTime, Text, Boolean, ForeignKey, Index, Float,
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from backend.db.database import Base


class Incident(Base):
    __tablename__ = "incidents"

    id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(String(20), unique=True, nullable=False, index=True)

    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    incident_type = Column(String(40), nullable=False, default="ALERT", index=True)
    priority = Column(String(10), nullable=False, default="high", index=True)
    status = Column(String(20), nullable=False, default="open", index=True)

    camera_id = Column(String(50), nullable=True, index=True)
    camera_location = Column(String(100), nullable=True)
    lat = Column(Float, nullable=True)
    lng = Column(Float, nullable=True)

    alert_id = Column(Integer, ForeignKey("alerts.id"), nullable=True)
    evidence_id = Column(Integer, ForeignKey("evidence.id"), nullable=True)
    person_name = Column(String(100), nullable=True)
    plate_number = Column(String(20), nullable=True)

    assigned_to = Column(Integer, ForeignKey("users.id"), nullable=True)
    assigned_name = Column(String(80), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_by_name = Column(String(80), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)

    notes = relationship("IncidentNote", back_populates="incident", cascade="all, delete-orphan")
    events = relationship("IncidentEvent", back_populates="incident", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_incident_status_priority", "status", "priority"),
        Index("idx_incident_camera", "camera_id", "created_at"),
    )


class IncidentNote(Base):
    __tablename__ = "incident_notes"

    id = Column(Integer, primary_key=True, index=True)
    incident_id = Column(Integer, ForeignKey("incidents.id"), nullable=False, index=True)
    author_id = Column(Integer, nullable=True)
    author_name = Column(String(80), nullable=True)
    body = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    incident = relationship("Incident", back_populates="notes")


class IncidentEvent(Base):
    """Append-only timeline entry for an incident."""
    __tablename__ = "incident_events"

    id = Column(Integer, primary_key=True, index=True)
    incident_id = Column(Integer, ForeignKey("incidents.id"), nullable=False, index=True)
    event_type = Column(String(40), nullable=False)
    message = Column(Text, nullable=False)
    actor = Column(String(80), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    incident = relationship("Incident", back_populates="events")
