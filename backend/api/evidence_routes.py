
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy import desc
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from backend.db.database import get_db
from backend.models.evidence import Evidence
from backend.models.user import User
from backend.auth.auth import operator_or_admin, admin_only
from backend.auth.guards import viewer_user
from backend.services.audit import log_audit

router = APIRouter(prefix="/evidence", tags=["evidence"])


class EvidenceResponse(BaseModel):
    id: int
    timestamp: datetime
    camera_location: str
    track_id: int
    person_name: Optional[str]
    is_criminal: bool
    weapon_present: bool
    is_suspicious: bool
    category: str
    reasons: Optional[str]
    has_image: bool = False
    content_sha256: Optional[str] = None

    class Config:
        from_attributes = True


@router.get("/", response_model=List[EvidenceResponse])
def list_evidence(
    skip: int = 0, limit: int = 50,
    category: Optional[str] = None,
    camera_location: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(operator_or_admin),
):
    query = db.query(Evidence)
    if category:
        query = query.filter(Evidence.category == category)
    if camera_location:
        query = query.filter(Evidence.camera_location == camera_location)
    return query.order_by(desc(Evidence.timestamp)).offset(skip).limit(limit).all()


@router.get("/{evidence_id}/image")
def get_evidence_image(
    evidence_id: int,
    kind: str = Query(default="frame", pattern="^(frame|roi)$"),
    token: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    """Serve the stored JPEG snapshot (full frame or subject crop)."""
    viewer = viewer_user(token, db)
    ev = db.query(Evidence).filter(Evidence.id == evidence_id).first()
    if not ev:
        raise HTTPException(status_code=404, detail="Evidence not found")
    data = ev.frame_data if kind == "frame" else ev.roi_data
    if not data:
        raise HTTPException(status_code=404, detail="No image stored for this record")
    if ev.encrypted:
        from backend.utils.encryption import EncryptionManager
        data = EncryptionManager().decrypt(data)
    # Log access in custody chain (best-effort)
    try:
        from backend.services.custody import append_custody
        append_custody(db, evidence_id=evidence_id, action="ACCESSED", actor=viewer.username,
                       actor_id=viewer.id, details=f"kind={kind}")
        db.commit()
    except Exception:
        db.rollback()
    return Response(content=data, media_type="image/jpeg",
                    headers={"Cache-Control": "private, no-store"})


@router.get("/{evidence_id}")
def get_evidence(evidence_id: int, db: Session = Depends(get_db),
                 user: User = Depends(operator_or_admin)):
    ev = db.query(Evidence).filter(Evidence.id == evidence_id).first()
    if not ev:
        raise HTTPException(status_code=404, detail="Evidence not found")
    return ev


@router.delete("/{evidence_id}")
def delete_evidence(evidence_id: int, request: Request, db: Session = Depends(get_db),
                    admin: User = Depends(admin_only)):
    ev = db.query(Evidence).filter(Evidence.id == evidence_id).first()
    if not ev:
        raise HTTPException(status_code=404, detail="Evidence not found")
    log_audit(db, admin, "EVIDENCE_DELETE", "evidence", evidence_id,
              f"category={ev.category} camera={ev.camera_location} person={ev.person_name}", request)
    db.delete(ev)
    db.commit()
    return {"status": "deleted"}


