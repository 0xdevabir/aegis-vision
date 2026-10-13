from sqlalchemy import Column, Integer, String, DateTime, Text, LargeBinary, ForeignKey, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from backend.db.database import Base


class FaceEncoding(Base):
    __tablename__ = "face_encodings"

    id = Column(Integer, primary_key=True, index=True)
    person_id = Column(Integer, ForeignKey("known_persons.id"), nullable=False, index=True)
    encoding = Column(LargeBinary, nullable=False)
    image_id = Column(Integer, ForeignKey("person_images.id", ondelete="SET NULL"), nullable=True, index=True)
    image_path = Column(String(255), nullable=True)
    encoding_version = Column(String(20), default="1.0")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    person = relationship("KnownPerson", back_populates="face_encodings")

    __table_args__ = (
        Index("idx_face_person_id", "person_id"),
    )

    @staticmethod
    def serialize_encoding(encoding) -> bytes:
        import numpy as np
        if encoding is None:
            return b""
        if isinstance(encoding, bytes):
            return encoding
        if not isinstance(encoding, np.ndarray):
            encoding = np.array(encoding, dtype=np.float64)
        return encoding.tobytes()

    @staticmethod
    def deserialize_encoding(data: bytes):
        import numpy as np
        return np.frombuffer(data, dtype=np.float64)
