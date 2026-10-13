from fastapi import APIRouter, Depends, HTTPException, Header, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from backend.db.database import get_db
from backend.auth.auth import operator_or_admin
from backend.models.user import User
from backend.models.alert import Alert
from backend.models.audit_log import AuditLog
from backend.services.alert_dispatcher import (
    REVIEW_REQUIRED_TYPES, dispatch_alert, redispatch_alert, release_held_webhooks,
)
from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List

from backend.auth.guards import verify_internal_key

router = APIRouter(prefix="/alerts", tags=["alerts"])


class AlertResponse(BaseModel):
    id: int
    timestamp: datetime
    alert_type: str
    severity: str
    camera_location: Optional[str]
    person_name: Optional[str]
    plate_number: Optional[str]
    message: Optional[str]
    acknowledged: bool
    dismissed: bool
    channels_sent: Optional[str]
    review_status: Optional[str] = None
    review_note: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    camera_id: Optional[str] = None
    track_id: Optional[int] = None
    evidence_id: Optional[int] = None

    class Config:
        from_attributes = True


class AcknowledgeRequest(BaseModel):
    acknowledged: bool = True
    dismissed: bool = False
    note: Optional[str] = None


class DispatchAlertRequest(BaseModel):
    alert_type: str
    severity: str = "critical"
    camera_location: Optional[str] = None
    camera_id: Optional[str] = None
    track_id: Optional[int] = None
    person_name: Optional[str] = None
    plate_number: Optional[str] = None
    message: Optional[str] = None
    camera_name: Optional[str] = None
    camera_lat: Optional[float] = None
    camera_lng: Optional[float] = None
    zone: Optional[str] = None
    confidence: Optional[float] = None


@router.post("/dispatch")
async def auto_dispatch_alert(
    body: DispatchAlertRequest,
    x_internal_key: Optional[str] = Header(default=None, alias="X-Internal-Key"),
):
    """
    Fully automated alert dispatch from pipeline (any camera).
    Saves DB + audit log + WebSocket + webhooks in one call.
    """
    verify_internal_key(x_internal_key)
    result = await dispatch_alert(
        alert_type=body.alert_type,
        severity=body.severity,
        camera_location=body.camera_location,
        camera_id=body.camera_id,
        track_id=body.track_id,
        person_name=body.person_name,
        plate_number=body.plate_number,
        message=body.message,
        camera_name=body.camera_name,
        camera_lat=body.camera_lat,
        camera_lng=body.camera_lng,
        zone=body.zone,
        confidence=body.confidence,
    )
    return result


@router.get("/", response_model=List[AlertResponse])
def list_alerts(
    skip: int = 0,
    limit: int = 50,
    alert_type: Optional[str] = None,
    severity: Optional[str] = None,
    acknowledged: Optional[bool] = None,
    dismissed: Optional[bool] = None,
    review_status: Optional[str] = Query(default=None, pattern="^(pending|confirmed|rejected|not_required)$"),
    camera_id: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(operator_or_admin),
):
    query = db.query(Alert)
    if review_status:
        query = query.filter(Alert.review_status == review_status)
    if camera_id:
        query = query.filter(Alert.camera_id == camera_id)
    if alert_type:
        query = query.filter(Alert.alert_type == alert_type.upper())
    if severity:
        query = query.filter(Alert.severity == severity)
    if acknowledged is not None:
        query = query.filter(Alert.acknowledged == acknowledged)
    if dismissed is not None:
        query = query.filter(Alert.dismissed == dismissed)
    return query.order_by(desc(Alert.timestamp)).offset(skip).limit(limit).all()


@router.get("/unacknowledged", response_model=List[AlertResponse])
def unacknowledged_alerts(
    db: Session = Depends(get_db),
    user: User = Depends(operator_or_admin),
):
    return (
        db.query(Alert)
        .filter(Alert.acknowledged == False, Alert.dismissed == False)
        .order_by(desc(Alert.timestamp))
        .limit(100)
        .all()
    )


@router.get("/stats")
def alert_stats(
    hours: int = 24,
    db: Session = Depends(get_db),
    user: User = Depends(operator_or_admin),
):
    from datetime import timedelta
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    total = db.query(Alert).filter(Alert.timestamp >= cutoff).count()
    unack = db.query(Alert).filter(Alert.timestamp >= cutoff, Alert.acknowledged == False).count()
    by_type = (
        db.query(Alert.alert_type, Alert.severity)
        .filter(Alert.timestamp >= cutoff)
        .all()
    )
    type_counts = {}
    for t, s in by_type:
        type_counts[t] = type_counts.get(t, 0) + 1
    return {
        "period_hours": hours,
        "total": total,
        "unacknowledged": unack,
        "by_type": type_counts,
    }


@router.get("/review-queue-count")
def review_queue_count(db: Session = Depends(get_db), user: User = Depends(operator_or_admin)):
    pending = db.query(Alert).filter(Alert.review_status == "pending", Alert.dismissed == False).count()  # noqa: E712
    return {"pending": pending}


@router.get("/{alert_id}/context")
def alert_context(alert_id: int, db: Session = Depends(get_db),
                  user: User = Depends(operator_or_admin)):
    """Everything an operator needs to judge one alert without leaving the screen."""
    from datetime import timedelta
    from backend.models.evidence import Evidence
    from backend.models.event import Event

    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    ev_q = db.query(Evidence).filter(
        Evidence.timestamp >= alert.timestamp - timedelta(seconds=60),
        Evidence.timestamp <= alert.timestamp + timedelta(seconds=60),
    )
    if alert.camera_location:
        ev_q = ev_q.filter(Evidence.camera_location == alert.camera_location)
    if alert.track_id is not None and alert.track_id >= 0:
        ev_q = ev_q.filter(Evidence.track_id == alert.track_id)
    evidence = sorted(
        ev_q.limit(20).all(),
        key=lambda e: abs((e.timestamp - alert.timestamp).total_seconds()),
    )[:3]

    own = db.query(Event).filter(Event.alert_id == alert_id).first()
    related = []
    if alert.camera_id:
        related = (
            db.query(Event)
            .filter(Event.camera_id == alert.camera_id, Event.alert_id != alert_id)
            .order_by(desc(Event.timestamp)).limit(5).all()
        )
    return {
        "alert_id": alert_id,
        "evidence": [
            {"id": e.id, "category": e.category, "has_image": bool(e.frame_data),
             "timestamp": e.timestamp.isoformat() if e.timestamp else None}
            for e in evidence
        ],
        "confidence": own.confidence if own else None,
        "zone": own.zone if own else None,
        "related_events": [
            {"id": r.id, "type": r.event_type, "severity": r.severity,
             "timestamp": r.timestamp.isoformat() if r.timestamp else None,
             "message": r.message}
            for r in related
        ],
        "holds_external_notification": (
            alert.review_status == "pending"
            and alert.alert_type in REVIEW_REQUIRED_TYPES
        ),
    }


@router.put("/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: int,
    body: AcknowledgeRequest,
    db: Session = Depends(get_db),
    user: User = Depends(operator_or_admin),
):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.acknowledged = body.acknowledged
    alert.dismissed = body.dismissed
    if body.acknowledged:
        alert.acknowledged_by = user.id
        alert.acknowledged_at = datetime.utcnow()

    released = ""
    needs_review = alert.review_status == "pending"
    if body.dismissed:
        decision = "rejected"
    elif body.acknowledged:
        decision = "confirmed"
    else:
        decision = None
    if decision and (needs_review or alert.review_status in ("confirmed", "rejected")):
        was_pending = alert.review_status == "pending"
        alert.review_status = decision
        alert.reviewed_by = user.id
        alert.reviewed_at = datetime.utcnow()
        alert.review_note = body.note
        db.add(AuditLog(
            user_id=user.id, username=user.username,
            action=f"ALERT_{decision.upper()}", resource="alert",
            resource_id=str(alert_id), details=body.note,
        ))
        if decision == "confirmed" and was_pending:
            released = await release_held_webhooks(alert)
            if released:
                alert.channels_sent = ",".join(filter(None, [alert.channels_sent, released]))
    db.commit()
    return {"status": "updated", "id": alert_id, "review_status": alert.review_status,
            "webhooks_released": released}


@router.post("/{alert_id}/dispatch")
async def dispatch_police(
    alert_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(operator_or_admin),
):
    """Operator-triggered police dispatch — reuses webhook channels + audit trail."""
    from backend.models.audit_log import AuditLog

    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    result = await redispatch_alert(
        alert,
        message=f"[MANUAL DISPATCH by {user.username}] {alert.message or alert.alert_type}",
        db=db,
    )
    alert.acknowledged = True
    alert.acknowledged_by = user.id
    alert.acknowledged_at = datetime.utcnow()
    if alert.review_status == "pending":
        alert.review_status = "confirmed"
        alert.reviewed_by = user.id
        alert.reviewed_at = datetime.utcnow()
    db.add(AuditLog(
        user_id=user.id,
        username=user.username,
        action="MANUAL_DISPATCH",
        resource="alert",
        resource_id=str(alert_id),
        details=f"Police dispatched for alert {alert_id}",
    ))
    db.commit()
    return {"status": "dispatched", "alert_id": alert_id, "redispatch": result}


