from sqlalchemy import Column, Integer, String, DateTime, Boolean
from sqlalchemy.sql import func
from backend.db.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(100), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="viewer")
    failed_attempts = Column(Integer, nullable=False, default=0, server_default="0")
    locked_until = Column(DateTime(timezone=True), nullable=True)
    phone = Column(String(30), nullable=True)   # officer SMS number (E.164, e.g. +8801XXXXXXXXX)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
