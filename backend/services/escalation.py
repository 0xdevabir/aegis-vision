"""Escalate critical alerts nobody acknowledged: page the backup officers, once."""
import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from backend.db.database import SessionLocal
from backend.models.alert import Alert
from backend.services import officer_dispatch
from backend.services.audit import log_audit
from backend.utils.websocket import manager

logger = logging.getLogger(__name__)


async def escalate_unacknowledged(db: Session, after_seconds: int, now: Optional[datetime] = None) -> int:
    """Returns how many alerts were escalated. Each alert escalates at most once."""
    now = now or datetime.utcnow()
    cutoff = now - timedelta(seconds=after_seconds)
    pending = db.query(Alert).filter(
        Alert.alert_type.in_(list(officer_dispatch.OFFICER_ALERT_TYPES)),
        Alert.acknowledged == False, Alert.dismissed == False,  # noqa: E712
        Alert.review_status != "rejected",
        Alert.escalated_at.is_(None), Alert.timestamp <= cutoff).all()
    for alert in pending:
        officers = officer_dispatch.officers_for_camera(db, alert.camera_id)
        backups = officers[1:]
        sent = []
        if backups:
            text = "ESCALATION (no acknowledgement) | " + officer_dispatch.sms_text(
                alert.alert_type, alert.person_name, None, alert.camera_location, None, None, None)
            sent = await officer_dispatch.sms_officers(backups, text, {"alert_id": alert.id, "camera_id": alert.camera_id})
        alert.escalated_at = now
        log_audit(db, None, "ALERT_ESCALATED", "alert", alert.id,
                  f"backups={[u.username for u in backups]} sms_sent={sent}")
        db.commit()
        await manager.broadcast({"event_type": "ALERT_ESCALATED", "alert_type": "ALERT_ESCALATED", "severity": "high",
                                 "alert_id": alert.id, "camera_id": alert.camera_id,
                                 "message": f"Alert #{alert.id} not acknowledged after {after_seconds}s: escalated"}, "alerts")
    return len(pending)


async def escalation_loop() -> None:
    after = int(os.getenv("ESCALATE_AFTER_SECONDS", "120"))
    if after <= 0:
        return
    while True:
        await asyncio.sleep(15)
        db = SessionLocal()
        try:
            await escalate_unacknowledged(db, after)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Escalation sweep failed: {e}")
            db.rollback()
        finally:
            db.close()
