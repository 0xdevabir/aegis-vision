"""
Known Persons Model
Stores information about known persons (criminals, persons of interest, etc.)
"""
from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, ForeignKey, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from backend.models.person_image import PersonImage
from backend.models.face_encoding import FaceEncoding
from backend.db.database import Base


class KnownPerson(Base):
    __tablename__ = "known_persons"

    id = Column(Integer, primary_key=True, index=True)
    person_id = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    category = Column(String(20), nullable=False, default="civilian")
    # Categories: criminal, person_of_interest, missing_person, civilian

    # Criminal info
    criminal_status = Column(String(20), default="unknown")
    # Statuses: wanted, convicted, suspect, cleared, unknown

    threat_level = Column(Integer, default=0)  # 0-10 scale
    notes = Column(Text, nullable=True)
    image_path = Column(String(255), nullable=True)

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Relationships
    face_encodings = relationship("FaceEncoding", back_populates="person")
    evidence = relationship("Evidence", back_populates="person")
    images = relationship("PersonImage", back_populates="person")

    __table_args__ = (
        Index("idx_known_person_id", "person_id"),
        Index("idx_known_category", "category"),
        Index("idx_known_criminal_status", "criminal_status"),
    )
