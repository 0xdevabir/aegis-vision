"""Persist observable events for structured search."""

import json
import logging
from typing import Optional

from sqlalchemy.orm import Session

from backend.models.event import Event

logger = logging.getLogger("HumanAnalysis")


def record_event(db: Session, event_type: str, severity: str = "info", *,
                 camera_id: Optional[str] = None, camera_location: Optional[str] = None,
                 track_id: Optional[int] = None, zone: Optional[str] = None,
                 person_name: Optional[str] = None, plate_number: Optional[str] = None,
                 confidence: Optional[float] = None, alert_id: Optional[int] = None,
                 message: Optional[str] = None, meta: Optional[dict] = None,
                 commit: bool = True) -> Optional[Event]:
    try:
        ev = Event(
            event_type=event_type, severity=severity, camera_id=camera_id,
            camera_location=camera_location, track_id=track_id, zone=zone,
            person_name=person_name, plate_number=plate_number, confidence=confidence,
            alert_id=alert_id, message=message, meta=json.dumps(meta) if meta else None,
        )
        db.add(ev)
        if commit:
            db.commit()
            db.refresh(ev)
        return ev
    except Exception as e:      # never let event logging break alerting
        logger.warning(f"Event record failed: {e}")
        db.rollback()
        return None
