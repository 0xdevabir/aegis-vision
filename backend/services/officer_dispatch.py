"""Find the police officers assigned to a camera and alert them automatically."""
import logging
import os
from typing import List, Optional

import httpx
from sqlalchemy.orm import Session

from backend.models.camera_officer import CameraOfficer
from backend.models.user import User
from backend.utils.http_retry import post_with_retry

logger = logging.getLogger(__name__)

# Alert types that page the assigned officer automatically.
OFFICER_ALERT_TYPES = {"CRIMINAL_DETECTED", "WEAPON_DETECTED"}


def officers_for_camera(db: Session, camera_id: Optional[str]) -> List[User]:
    """Active police users assigned to `camera_id`, primary first."""
    if not camera_id:
        return []
    rows = (db.query(CameraOfficer, User)
            .join(User, User.id == CameraOfficer.user_id)
            .filter(CameraOfficer.camera_id == camera_id, User.is_active == True, User.role == "police")  # noqa: E712
            .order_by(CameraOfficer.priority, CameraOfficer.id).all())
    return [u for _, u in rows]


def officer_summary(officers: List[User]) -> List[dict]:
    """Safe to broadcast: no phone numbers."""
    return [{"id": u.id, "name": u.username} for u in officers]


def sms_text(alert_type: str, person_name: Optional[str], camera_name: Optional[str], camera_location: Optional[str],
             lat: Optional[float], lng: Optional[float], ticket: Optional[str]) -> str:
    what = "WATCHLIST MATCH (unverified)" if alert_type == "CRIMINAL_DETECTED" else alert_type.replace("_", " ")
    parts = [f"AEGIS {what}"]
    if person_name:
        parts.append(f"Person: {person_name}")
    parts.append(f"Camera: {camera_name or camera_location or 'unknown'}")
    if lat is not None and lng is not None:
        parts.append(f"GPS: {lat:.5f},{lng:.5f} https://www.google.com/maps?q={lat},{lng}")
    if ticket:
        parts.append(f"Ticket: {ticket}")
    return " | ".join(parts)


async def sms_officers(officers: List[User], text: str, payload: dict) -> List[str]:
    """POST one SMS-webhook call per officer with a phone. Returns usernames notified."""
    url = os.getenv("SMS_WEBHOOK", "")
    if not url or os.getenv("ALERTS_ENABLED", "false").lower() != "true":
        return []
    sent = []
    async with httpx.AsyncClient() as client:
        for u in officers:
            if not u.phone:
                logger.warning(f"Officer {u.username} has no phone number; SMS skipped")
                continue
            if await post_with_retry(client, url, {"to": u.phone, "officer": u.username, "message": text, **payload}):
                sent.append(u.username)
            else:
                logger.error(f"SMS to officer {u.username} failed after retries")
    return sent
