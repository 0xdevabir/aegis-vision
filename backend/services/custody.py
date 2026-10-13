"""Cryptographic chain-of-custody helpers (append-only)."""

from __future__ import annotations

import hashlib
from typing import Optional

from sqlalchemy.orm import Session

from backend.models.custody import CustodyRecord
from backend.models.evidence import Evidence


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _seal_record(
    evidence_id: int,
    action: str,
    actor: str,
    sha256_hash: str,
    prev_hash: Optional[str],
    details: Optional[str],
) -> str:
    payload = f"{evidence_id}|{action}|{actor}|{sha256_hash}|{prev_hash or ''}|{details or ''}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def append_custody(
    db: Session,
    evidence_id: int,
    action: str,
    actor: str = "SYSTEM",
    actor_id: Optional[int] = None,
    sha256_hash: Optional[str] = None,
    details: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> CustodyRecord:
    """Append a sealed custody record. Never mutate prior rows."""
    if not sha256_hash:
        ev = db.query(Evidence).filter(Evidence.id == evidence_id).first()
        sha256_hash = (ev.content_sha256 if ev else None) or "unknown"

    prev = (
        db.query(CustodyRecord)
        .filter(CustodyRecord.evidence_id == evidence_id)
        .order_by(CustodyRecord.id.desc())
        .first()
    )
    prev_hash = prev.record_hash if prev else None
    record_hash = _seal_record(evidence_id, action, actor, sha256_hash, prev_hash, details)

    row = CustodyRecord(
        evidence_id=evidence_id,
        action=action,
        actor=actor,
        actor_id=actor_id,
        sha256_hash=sha256_hash,
        prev_hash=prev_hash,
        record_hash=record_hash,
        details=details,
        ip_address=ip_address,
    )
    db.add(row)
    db.flush()
    return row


def verify_evidence_integrity(db: Session, evidence_id: int) -> dict:
    """Recompute SHA-256 of stored bytes and walk the custody hash chain."""
    ev = db.query(Evidence).filter(Evidence.id == evidence_id).first()
    if not ev:
        return {"ok": False, "error": "Evidence not found"}

    actual = sha256_bytes(ev.frame_data) if ev.frame_data else None
    hash_match = bool(actual and ev.content_sha256 and actual == ev.content_sha256)

    records = (
        db.query(CustodyRecord)
        .filter(CustodyRecord.evidence_id == evidence_id)
        .order_by(CustodyRecord.id.asc())
        .all()
    )
    chain_ok = True
    prev = None
    for r in records:
        expected_prev = prev.record_hash if prev else None
        if r.prev_hash != expected_prev:
            chain_ok = False
            break
        sealed = _seal_record(r.evidence_id, r.action, r.actor, r.sha256_hash, r.prev_hash, r.details)
        if sealed != r.record_hash:
            chain_ok = False
            break
        prev = r

    return {
        "ok": hash_match and chain_ok,
        "hash_match": hash_match,
        "chain_ok": chain_ok,
        "stored_sha256": ev.content_sha256,
        "actual_sha256": actual,
        "custody_entries": len(records),
    }


def custody_chain(db: Session, evidence_id: int) -> list:
    rows = (
        db.query(CustodyRecord)
        .filter(CustodyRecord.evidence_id == evidence_id)
        .order_by(CustodyRecord.id.asc())
        .all()
    )
    return [
        {
            "id": r.id,
            "action": r.action,
            "actor": r.actor,
            "sha256_hash": r.sha256_hash,
            "prev_hash": r.prev_hash,
            "record_hash": r.record_hash,
            "details": r.details,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
