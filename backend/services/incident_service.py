"""Incident ticket helpers — create from alerts, timeline events."""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from backend.models.incident import Incident, IncidentEvent
from backend.models.alert import Alert


def _next_ticket_id(db: Session) -> str:
    last = db.query(Incident).order_by(Incident.id.desc()).first()
    n = (last.id + 1) if last else 1
    return f"INC-{1000 + n}"


def add_event(
    db: Session,
    incident: Incident,
    event_type: str,
    message: str,
    actor: Optional[str] = None,
) -> IncidentEvent:
    ev = IncidentEvent(
        incident_id=incident.id,
        event_type=event_type,
        message=message,
        actor=actor or "SYSTEM",
    )
    db.add(ev)
    return ev


def create_incident_from_alert(
    db: Session,
    alert: Alert,
    *,
    created_by: Optional[int] = None,
    created_by_name: str = "SYSTEM",
) -> Incident:
    """Idempotent: one open incident per alert_id."""
    existing = db.query(Incident).filter(Incident.alert_id == alert.id).first()
    if existing:
        return existing

    lat = lng = None
    if alert.details:
        try:
            import json
            geo = json.loads(alert.details)
            lat, lng = geo.get("lat"), geo.get("lng")
        except Exception:
            pass

    priority = alert.severity if alert.severity in ("critical", "high", "medium", "low", "info") else "high"
    if priority == "info":
        priority = "low"

    inc = Incident(
        ticket_id=_next_ticket_id(db),
        title=alert.message or alert.alert_type.replace("_", " "),
        description=alert.message,
        incident_type=alert.alert_type,
        priority=priority if priority != "info" else "medium",
        status="open",
        camera_id=alert.camera_id,
        camera_location=alert.camera_location,
        lat=lat,
        lng=lng,
        alert_id=alert.id,
        evidence_id=alert.evidence_id,
        person_name=alert.person_name,
        plate_number=alert.plate_number,
        created_by=created_by,
        created_by_name=created_by_name,
    )
    db.add(inc)
    db.flush()
    add_event(db, inc, "CREATED", f"Incident opened from alert #{alert.id}", created_by_name)
    add_event(db, inc, "ALERT", f"{alert.alert_type}: {alert.message}", "SYSTEM")
    return inc


def ensure_incident_for_dispatch(db: Session, alert_id: int, **kwargs) -> Optional[Incident]:
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        return None
    return create_incident_from_alert(db, alert, **kwargs)
