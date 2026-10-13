"""Chain-of-custody + evidence integrity verification."""


from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from backend.db.database import get_db
from backend.models.user import User
from backend.models.evidence import Evidence
from backend.auth.auth import operator_or_admin
from backend.services.custody import append_custody, custody_chain, verify_evidence_integrity

router = APIRouter(prefix="/custody", tags=["custody"])


@router.get("/evidence/{evidence_id}")
def get_chain(
    evidence_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(operator_or_admin),
):
    ev = db.query(Evidence).filter(Evidence.id == evidence_id).first()
    if not ev:
        raise HTTPException(404, "Evidence not found")
    return {
        "evidence_id": evidence_id,
        "content_sha256": ev.content_sha256,
        "chain": custody_chain(db, evidence_id),
        "integrity": verify_evidence_integrity(db, evidence_id),
    }


@router.post("/evidence/{evidence_id}/verify")
def verify(
    evidence_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(operator_or_admin),
):
    result = verify_evidence_integrity(db, evidence_id)
    if "error" in result:
        raise HTTPException(404, result["error"])
    append_custody(
        db,
        evidence_id=evidence_id,
        action="VERIFIED",
        actor=user.username,
        actor_id=user.id,
        details=f"integrity_ok={result['ok']}",
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    result["verified_by"] = user.username
    return result


@router.post("/evidence/{evidence_id}/access")
def log_access(
    evidence_id: int,
    request: Request,
    action: str = "ACCESSED",
    db: Session = Depends(get_db),
    user: User = Depends(operator_or_admin),
):
    if action not in ("ACCESSED", "DOWNLOADED", "EXPORTED", "TRANSFERRED"):
        raise HTTPException(400, "Invalid action")
    ev = db.query(Evidence).filter(Evidence.id == evidence_id).first()
    if not ev:
        raise HTTPException(404, "Evidence not found")
    row = append_custody(
        db,
        evidence_id=evidence_id,
        action=action,
        actor=user.username,
        actor_id=user.id,
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    return {"status": "logged", "id": row.id, "record_hash": row.record_hash}
