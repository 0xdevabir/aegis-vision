from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, LargeBinary
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from backend.db.database import Base


class PersonImage(Base):
    __tablename__ = "person_images"

    id = Column(Integer, primary_key=True, index=True)
    person_id = Column(Integer, ForeignKey("known_persons.id"), nullable=False, index=True)
    image_data = Column(LargeBinary, nullable=False)
    image_type = Column(String(20), default="face")
    filename = Column(String(255), nullable=True)
    image_path = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=True, server_default=func.now())

    person = relationship("KnownPerson", back_populates="images")
