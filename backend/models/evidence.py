from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, Index, LargeBinary
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from backend.db.database import Base
from backend.models.user import User
from backend.models.known_person import KnownPerson


class Evidence(Base):
    __tablename__ = "evidence"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    # Camera info
    camera_location = Column(String(50), nullable=False, index=True)
    camera_id = Column(String(50), nullable=True)

    # Person info
    track_id = Column(Integer, nullable=False, index=True)
    person_id = Column(Integer, ForeignKey("known_persons.id"), nullable=True)
    person_name = Column(String(100), nullable=True)

    # Detection flags
    is_criminal = Column(Boolean, default=False)
    weapon_present = Column(Boolean, default=False)
    is_suspicious = Column(Boolean, default=False)

    # Details
    reasons = Column(Text, nullable=True)
    category = Column(String(20), nullable=False, index=True)

    # File paths (nullable — kept for legacy compatibility)
    frame_path = Column(String(255), nullable=True)
    roi_path = Column(String(255), nullable=True)
    encrypted = Column(Boolean, default=False)

    # Image bytes stored directly in DB
    frame_data = Column(LargeBinary, nullable=True)
    roi_data = Column(LargeBinary, nullable=True)

    # Tamper-evident hash of frame_data (SHA-256 hex)
    content_sha256 = Column(String(64), nullable=True, index=True)

    # Metadata
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Relationships
    person = relationship("KnownPerson", back_populates="evidence")
    creator = relationship("User", foreign_keys=[created_by])

    __table_args__ = (
        Index("idx_timestamp_location", "timestamp", "camera_location"),
        Index("idx_track_time", "track_id", "timestamp"),
        Index("idx_evidence_person_name", "person_name"),
    )

    @property
    def has_image(self) -> bool:
        return self.frame_data is not None or self.frame_path is not None

