from sqlalchemy import Column, Integer, String, DateTime, Float, Text, LargeBinary, Index
from sqlalchemy.sql import func
from backend.db.database import Base


class AlertCapture(Base):
    """A zoomed still of the subject, taken every few seconds while a red alert is live."""

    __tablename__ = "alert_captures"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    alert_id = Column(Integer, nullable=True, index=True)
    alert_type = Column(String(30), nullable=False)

    camera_id = Column(String(50), nullable=True)
    camera_location = Column(String(50), nullable=True)
    camera_name = Column(String(100), nullable=True)
    camera_lat = Column(Float, nullable=True)
    camera_lng = Column(Float, nullable=True)

    track_id = Column(Integer, nullable=True)
    person_name = Column(String(100), nullable=True)
    confidence = Column(Float, nullable=True)

    # Stored image size, and the subject's size in the camera frame before enlarging
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    source_width = Column(Integer, nullable=True)
    source_height = Column(Integer, nullable=True)
    bbox = Column(String(60), nullable=True)          # "x,y,w,h" as fractions of the frame
    attributes = Column(Text, nullable=True)          # JSON: estimated gender, clothing colours, …

    image_data = Column(LargeBinary, nullable=False)
    content_sha256 = Column(String(64), nullable=True)

    __table_args__ = (
        Index("idx_capture_alert_time", "alert_id", "timestamp"),
    )
