from sqlalchemy import Column, Integer, String, DateTime, Text, Index
from sqlalchemy.sql import func
from backend.db.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    user_id = Column(Integer, nullable=True, index=True)
    username = Column(String(50), nullable=True)
    action = Column(String(50), nullable=False, index=True)
    resource = Column(String(50), nullable=True)
    resource_id = Column(String(50), nullable=True)
    details = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=True)

    __table_args__ = (
        Index("idx_audit_timestamp", "timestamp"),
        Index("idx_audit_action", "action"),
    )
