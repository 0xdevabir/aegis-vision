"""Incident Management API — server-side tickets with assign / status / notes / timeline."""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc

from backend.db.database import get_db
from backend.models.user import User
from backend.models.incident import Incident, IncidentNote
from backend.models.alert import Alert
from backend.auth.auth import operator_or_admin
from backend.services.incident_service import (
    create_incident_from_alert, add_event, _next_ticket_id,
)

router = APIRouter(prefix="/incidents", tags=["incidents"])

VALID_STATUS = {"open", "investigating", "resolved", "closed"}
VALID_PRIORITY = {"critical", "high", "medium", "low"}


class NoteOut(BaseModel):
    id: int
    author_name: Optional[str]
    body: str
    created_at: datetime

    class Config:
        from_attributes = True


class EventOut(BaseModel):
    id: int
    event_type: str
    message: str
    actor: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class IncidentOut(BaseModel):
    id: int
    ticket_id: str
    title: str
    description: Optional[str]
    incident_type: str
    priority: str
    status: str
    camera_id: Optional[str]
    camera_location: Optional[str]
    lat: Optional[float]
    lng: Optional[float]
    alert_id: Optional[int]
    evidence_id: Optional[int]
    person_name: Optional[str]
    plate_number: Optional[str]
    assigned_to: Optional[int]
    assigned_name: Optional[str]
    created_by_name: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]
    resolved_at: Optional[datetime]
    notes: List[NoteOut] = []
    events: List[EventOut] = []

    class Config:
        from_attributes = True


class IncidentCreate(BaseModel):
    title: str
    description: Optional[str] = None
    incident_type: str = "MANUAL"
    priority: str = "medium"
    camera_id: Optional[str] = None
    camera_location: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    alert_id: Optional[int] = None
    evidence_id: Optional[int] = None
    person_name: Optional[str] = None
    plate_number: Optional[str] = None


class IncidentUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    assigned_to: Optional[int] = None
    assigned_name: Optional[str] = None


class NoteCreate(BaseModel):
    body: str


@router.get("/", response_model=List[IncidentOut])
def list_incidents(
    status: Optional[str] = None,
    priority: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    user: User = Depends(operator_or_admin),
):
    q = db.query(Incident).options(
        joinedload(Incident.notes), joinedload(Incident.events),
    )
    if status:
        q = q.filter(Incident.status == status)
    if priority:
        q = q.filter(Incident.priority == priority)
    return q.order_by(desc(Incident.created_at)).offset(skip).limit(limit).all()


@router.get("/stats")
def incident_stats(db: Session = Depends(get_db), user: User = Depends(operator_or_admin)):
    rows = db.query(Incident).all()
    by_status = {}
    for r in rows:
        by_status[r.status] = by_status.get(r.status, 0) + 1
    return {"total": len(rows), "by_status": by_status}


@router.get("/{incident_id}", response_model=IncidentOut)
def get_incident(incident_id: int, db: Session = Depends(get_db), user: User = Depends(operator_or_admin)):
    inc = (
        db.query(Incident)
        .options(joinedload(Incident.notes), joinedload(Incident.events))
        .filter(Incident.id == incident_id)
        .first()
    )
    if not inc:
        raise HTTPException(404, "Incident not found")
    return inc


@router.post("/", response_model=IncidentOut)
def create_incident(body: IncidentCreate, db: Session = Depends(get_db), user: User = Depends(operator_or_admin)):
    if body.alert_id:
        alert = db.query(Alert).filter(Alert.id == body.alert_id).first()
        if alert:
            inc = create_incident_from_alert(db, alert, created_by=user.id, created_by_name=user.username)
            db.commit()
            return get_incident(inc.id, db, user)

    if body.priority not in VALID_PRIORITY:
        raise HTTPException(400, f"priority must be one of {VALID_PRIORITY}")

    inc = Incident(
        ticket_id=_next_ticket_id(db),
        title=body.title,
        description=body.description,
        incident_type=body.incident_type,
        priority=body.priority,
        status="open",
        camera_id=body.camera_id,
        camera_location=body.camera_location,
        lat=body.lat,
        lng=body.lng,
        alert_id=body.alert_id,
        evidence_id=body.evidence_id,
        person_name=body.person_name,
        plate_number=body.plate_number,
        created_by=user.id,
        created_by_name=user.username,
    )
    db.add(inc)
    db.flush()
    add_event(db, inc, "CREATED", "Manual incident created", user.username)
    db.commit()
    return get_incident(inc.id, db, user)


@router.put("/{incident_id}", response_model=IncidentOut)
def update_incident(
    incident_id: int,
    body: IncidentUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(operator_or_admin),
):
    inc = db.query(Incident).filter(Incident.id == incident_id).first()
    if not inc:
        raise HTTPException(404, "Incident not found")

    if body.status is not None:
        if body.status not in VALID_STATUS:
            raise HTTPException(400, f"status must be one of {VALID_STATUS}")
        if body.status != inc.status:
            add_event(db, inc, "STATUS", f"{inc.status} → {body.status}", user.username)
            inc.status = body.status
            if body.status == "resolved":
                inc.resolved_at = datetime.utcnow()
            if body.status == "closed":
                inc.closed_at = datetime.utcnow()

    if body.priority is not None:
        if body.priority not in VALID_PRIORITY:
            raise HTTPException(400, f"priority must be one of {VALID_PRIORITY}")
        if body.priority != inc.priority:
            add_event(db, inc, "PRIORITY", f"{inc.priority} → {body.priority}", user.username)
            inc.priority = body.priority

    if body.assigned_name is not None or body.assigned_to is not None:
        name = body.assigned_name
        if body.assigned_to and not name:
            u = db.query(User).filter(User.id == body.assigned_to).first()
            name = u.username if u else str(body.assigned_to)
        if body.assigned_to == 0:          # 0 = unassign
            name = None
        add_event(db, inc, "ASSIGNED", f"Assigned to {name}" if name else "Unassigned", user.username)
        inc.assigned_to = body.assigned_to or None
        inc.assigned_name = name

    if body.title is not None:
        inc.title = body.title
    if body.description is not None:
        inc.description = body.description

    db.commit()
    return get_incident(incident_id, db, user)


@router.post("/{incident_id}/notes", response_model=NoteOut)
def add_note(
    incident_id: int,
    body: NoteCreate,
    db: Session = Depends(get_db),
    user: User = Depends(operator_or_admin),
):
    inc = db.query(Incident).filter(Incident.id == incident_id).first()
    if not inc:
        raise HTTPException(404, "Incident not found")
    note = IncidentNote(
        incident_id=incident_id,
        author_id=user.id,
        author_name=user.username,
        body=body.body,
    )
    db.add(note)
    add_event(db, inc, "NOTE", f"Note added by {user.username}", user.username)
    db.commit()
    db.refresh(note)
    return note


@router.post("/from-alert/{alert_id}", response_model=IncidentOut)
def open_from_alert(alert_id: int, db: Session = Depends(get_db), user: User = Depends(operator_or_admin)):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(404, "Alert not found")
    inc = create_incident_from_alert(db, alert, created_by=user.id, created_by_name=user.username)
    db.commit()
    return get_incident(inc.id, db, user)
