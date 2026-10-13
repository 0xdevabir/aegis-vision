"""Which police officers are responsible for which camera (location)."""
from sqlalchemy import Column, Integer, String, ForeignKey, UniqueConstraint
from backend.db.database import Base


class CameraOfficer(Base):
    __tablename__ = "camera_officers"

    id = Column(Integer, primary_key=True, index=True)
    camera_id = Column(String(50), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    priority = Column(Integer, nullable=False, default=0)   # 0 = primary, 1+ = backup

    __table_args__ = (UniqueConstraint("camera_id", "user_id", name="uq_camera_officer"),)
