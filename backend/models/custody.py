"""Tamper-evident chain-of-custody records (append-only)."""

from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Index
from sqlalchemy.sql import func
from backend.db.database import Base


class CustodyRecord(Base):
    """
    Append-only custody log. Never UPDATE or DELETE rows in application code.
    Each entry seals evidence_id + sha256_hash + action + actor.
    """
    __tablename__ = "custody_records"

    id = Column(Integer, primary_key=True, index=True)
    evidence_id = Column(Integer, ForeignKey("evidence.id"), nullable=False, index=True)
    action = Column(String(40), nullable=False, index=True)  # CAPTURED|ACCESSED|DOWNLOADED|VERIFIED|TRANSFERRED|EXPORTED
    actor = Column(String(80), nullable=False, default="SYSTEM")
    actor_id = Column(Integer, nullable=True)
    sha256_hash = Column(String(64), nullable=False)
    prev_hash = Column(String(64), nullable=True)  # hash-chain link to previous custody row
    record_hash = Column(String(64), nullable=False)  # hash of this row's sealed payload
    details = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    __table_args__ = (
        Index("idx_custody_evidence_time", "evidence_id", "created_at"),
    )
