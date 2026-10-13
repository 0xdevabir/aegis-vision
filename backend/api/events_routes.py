from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from backend.db.database import get_db
from backend.models.event import Event
from backend.services.event_store import record_event
from backend.auth.auth import operator_or_admin
from backend.models.user import User
from backend.utils.events import broadcast_live_event
from pydantic import BaseModel
from typing import Optional

from backend.auth.guards import verify_internal_key

router = APIRouter(prefix="/events", tags=["events"])


class LiveEvent(BaseModel):
    event_type: str
    severity: str = "info"
    camera_location: Optional[str] = None
    camera_id: Optional[str] = None
    track_id: Optional[int] = None
    person_name: Optional[str] = None
    message: Optional[str] = None


@router.post("/live")
async def push_live_event(
    event: LiveEvent,
    user: User = Depends(operator_or_admin),
):
    payload = await broadcast_live_event(
        event_type=event.event_type,
        severity=event.severity,
        camera_location=event.camera_location,
        camera_id=event.camera_id,
        track_id=event.track_id,
        person_name=event.person_name,
        message=event.message,
    )
    return {"status": "broadcast", "event_type": event.event_type, "payload": payload}


@router.post("/internal")
async def push_internal_event(
    event: LiveEvent,
    x_internal_key: Optional[str] = Header(default=None, alias="X-Internal-Key"),
    db: Session = Depends(get_db),
):
    """Pipeline-to-backend event push (no JWT; uses shared internal key)."""
    verify_internal_key(x_internal_key)
    record_event(
        db, event.event_type, event.severity, camera_id=event.camera_id,
        camera_location=event.camera_location, track_id=event.track_id,
        person_name=event.person_name, message=event.message,
    )
    await broadcast_live_event(
        event_type=event.event_type,
        severity=event.severity,
        camera_location=event.camera_location,
        camera_id=event.camera_id,
        track_id=event.track_id,
        person_name=event.person_name,
        message=event.message,
    )
    return {"status": "broadcast", "event_type": event.event_type}


class EventOut(BaseModel):
    id: int
    timestamp: datetime
    event_type: str
    severity: str
    camera_id: Optional[str] = None
    camera_location: Optional[str] = None
    track_id: Optional[int] = None
    zone: Optional[str] = None
    person_name: Optional[str] = None
    plate_number: Optional[str] = None
    confidence: Optional[float] = None
    alert_id: Optional[int] = None
    message: Optional[str] = None

    class Config:
        from_attributes = True


@router.get("/search", response_model=List[EventOut])
def search_events(
    event_type: Optional[str] = None,
    event_types: Optional[str] = Query(default=None, description="comma-separated"),
    camera_id: Optional[str] = None,
    track_id: Optional[int] = None,
    zone: Optional[str] = None,
    severity: Optional[str] = None,
    since: Optional[datetime] = Query(default=None, description="ISO timestamp, inclusive"),
    until: Optional[datetime] = Query(default=None, description="ISO timestamp, exclusive"),
    limit: int = Query(default=100, ge=1, le=500),
    skip: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(operator_or_admin),
):
    """Structured event search, e.g. weapon events on camera 3 between 22:00 and 02:00."""
    q = db.query(Event)
    if event_type:
        q = q.filter(Event.event_type == event_type.upper())
    if event_types:
        q = q.filter(Event.event_type.in_([t.strip().upper() for t in event_types.split(",") if t.strip()]))
    if camera_id:
        q = q.filter(Event.camera_id == camera_id)
    if track_id is not None:
        q = q.filter(Event.track_id == track_id)
    if zone:
        q = q.filter(Event.zone == zone)
    if severity:
        q = q.filter(Event.severity == severity)
    if since:
        q = q.filter(Event.timestamp >= since)
    if until:
        q = q.filter(Event.timestamp < until)
    return q.order_by(desc(Event.timestamp)).offset(skip).limit(limit).all()
