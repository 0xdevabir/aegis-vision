"""Incident report API routes."""

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session
from backend.db.database import get_db
from backend.services.audit import log_audit
from backend.auth.auth import operator_or_admin
from backend.models.user import User
from utils.data import ReportGenerator

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/incident")
def incident_report(
    request: Request,
    hours: int = Query(default=24, ge=1, le=168),
    user: User = Depends(operator_or_admin),
    db: Session = Depends(get_db),
):
    log_audit(db, user, "REPORT_GENERATE", "report", "incident", f"hours={hours}", request)
    db.commit()
    gen = ReportGenerator()
    try:
        return gen.generate_incident_report(hours=hours)
    finally:
        gen.close()


@router.get("/evidence-bundle")
def evidence_bundle(
    request: Request,
    ids: str = Query(..., description="Comma-separated evidence IDs"),
    user: User = Depends(operator_or_admin),
    db: Session = Depends(get_db),
):
    evidence_ids = [int(x.strip()) for x in ids.split(",") if x.strip().isdigit()]
    log_audit(db, user, "EVIDENCE_BUNDLE", "report", "bundle", f"ids={evidence_ids}", request)
    db.commit()
    gen = ReportGenerator()
    try:
        return gen.generate_evidence_bundle(evidence_ids)
    finally:
        gen.close()
