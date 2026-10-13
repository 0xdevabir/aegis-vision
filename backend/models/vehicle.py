from sqlalchemy import Column, Integer, String, DateTime, Boolean, Index
from sqlalchemy.sql import func
from backend.db.database import Base


class LicensePlate(Base):
    __tablename__ = "license_plates"

    id = Column(Integer, primary_key=True, index=True)
    plate_number = Column(String(20), unique=True, nullable=False, index=True)
    watchlisted = Column(Boolean, default=False)
    reason = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        Index("idx_plate_number", "plate_number"),
    )


class VehicleDetection(Base):
    __tablename__ = "vehicle_detections"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    camera_location = Column(String(50), nullable=False, index=True)
    track_id = Column(Integer, nullable=False)
    vehicle_type = Column(String(20), nullable=False)
    license_plate = Column(String(20), nullable=True)
    plate_confidence = Column(String(10), nullable=True)
    is_suspicious = Column(Boolean, default=False)
    evidence_id = Column(Integer, nullable=True)

    __table_args__ = (
        Index("idx_vehicle_timestamp", "timestamp", "camera_location"),
    )
