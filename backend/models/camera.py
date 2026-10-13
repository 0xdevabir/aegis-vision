from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text
from sqlalchemy.sql import func
from backend.db.database import Base


class Camera(Base):
    __tablename__ = "cameras"

    id = Column(Integer, primary_key=True, index=True)
    camera_id = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    location = Column(String(100), nullable=True)
    lat = Column(Float, nullable=True)
    lng = Column(Float, nullable=True)
    rtsp_url = Column(String(255), nullable=True)
    heading = Column(Float, nullable=True)     # degrees clockwise from north the camera faces (map field-of-view cone)
    fov = Column(Float, nullable=True)         # horizontal field of view, degrees
    range_m = Column(Float, nullable=True)     # how far it sees, metres
    active = Column(Boolean, default=True)
    # JSON {zones: [...], lines: [...]} in normalized 0-1 coordinates (see core/analysis/zones.py)
    geometry = Column(Text, nullable=True)
    geometry_updated_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
