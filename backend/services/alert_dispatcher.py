"""Central alert dispatcher — one detection triggers all notification channels."""

import json
import os
import logging
from datetime import datetime, timedelta
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from backend.db.database import SessionLocal
from backend.models.alert import Alert
from backend.models.audit_log import AuditLog
from backend.models.camera import Camera
from backend.models.camera_officer import CameraOfficer  # noqa: F401  (registers the table)
from backend.models.known_person import KnownPerson
from backend.services import officer_dispatch
from backend.services.event_store import record_event
from backend.services.watchlist_store import ALERT_STATUSES
from backend.utils.events import broadcast_live_event
from backend.utils.http_retry import post_with_retry
from backend.utils.websocket import manager

logger = logging.getLogger(__name__)


def _webhook_urls() -> dict:
    return {
        "law_enforcement": os.getenv("LAW_ENFORCEMENT_WEBHOOK", ""),
        "emergency": os.getenv("EMERGENCY_WEBHOOK", ""),
        "security": os.getenv("SECURITY_TEAM_WEBHOOK", ""),
    }


def _resolve_camera_geo(
    db: Session,
    camera_id: Optional[str],
    camera_lat: Optional[float],
    camera_lng: Optional[float],
    camera_name: Optional[str],
) -> tuple:
    """Fill missing GPS from cameras database table."""
    if camera_lat is not None and camera_lng is not None:
        return camera_lat, camera_lng, camera_name

    if not camera_id:
        return camera_lat, camera_lng, camera_name

    cam = db.query(Camera).filter(Camera.camera_id == camera_id).first()
    if cam:
        return cam.lat or camera_lat, cam.lng or camera_lng, cam.name or camera_name
    return camera_lat, camera_lng, camera_name


def _geo_details(lat, lng, camera_name, camera_id) -> Optional[str]:
    if lat is None or lng is None:
        return None
    return json.dumps({
        "lat": lat,
        "lng": lng,
        "camera_name": camera_name,
        "camera_id": camera_id,
        "maps_url": f"https://www.google.com/maps?q={lat},{lng}",
    })


# Identification-type alerts: external webhooks wait for human confirmation.
REVIEW_REQUIRED_TYPES = {"CRIMINAL_DETECTED"}


async def _send_webhooks(alert_type: str, payload: dict) -> str:
    if os.getenv("ALERTS_ENABLED", "false").lower() != "true":
        return ""
    urls = _webhook_urls()
    sent = []
    if alert_type == "CRIMINAL_DETECTED":
        keys = ("law_enforcement", "security")
    elif alert_type in ("WEAPON_DETECTED", "FIRE_SMOKE_DETECTED"):
        keys = ("emergency", "security")
    elif alert_type == "SUSPICIOUS_VEHICLE":
        keys = ("law_enforcement",)
    else:
        keys = ()
    for key in keys:
        if urls[key] and await _post_webhook(urls[key], payload):
            sent.append(key)             # only channels that really accepted the message
    return ",".join(sent)


async def _post_webhook(url: str, payload: dict) -> bool:
    async with httpx.AsyncClient() as client:
        return await post_with_retry(client, url, payload)


async def dispatch_alert(
    alert_type: str,
    severity: str = "info",
    camera_location: Optional[str] = None,
    camera_id: Optional[str] = None,
    track_id: Optional[int] = None,
    person_name: Optional[str] = None,
    plate_number: Optional[str] = None,
    message: Optional[str] = None,
    camera_name: Optional[str] = None,
    camera_lat: Optional[float] = None,
    camera_lng: Optional[float] = None,
    db: Optional[Session] = None,
    zone: Optional[str] = None,
    confidence: Optional[float] = None,
) -> dict:
    """Fully automated alert dispatch with pinpoint camera GPS."""
    own_session = db is None
    if own_session:
        db = SessionLocal()

    try:
        # One open alert per (type, camera, person/plate) within the window: a person lingering in view
        # must not page the officer every few seconds. Acknowledge/dismiss re-arms it.
        window = int(os.getenv("ALERT_DEDUPE_SECONDS", "120"))
        if window > 0 and alert_type != "PIPELINE_HEARTBEAT":
            cutoff = datetime.utcnow() - timedelta(seconds=window)
            dup = db.query(Alert).filter(
                Alert.alert_type == alert_type, Alert.camera_id == camera_id,
                Alert.person_name == person_name, Alert.plate_number == plate_number,
                Alert.acknowledged == False, Alert.dismissed == False,  # noqa: E712
                Alert.timestamp >= cutoff).order_by(Alert.id.desc()).first()
            if dup:
                return {"status": "deduplicated", "alert_id": dup.id}

        display_name = None
        if alert_type == "CRIMINAL_DETECTED":
            # Defense in depth: only a currently enrolled, alert-eligible criminal may raise this.
            known = db.query(KnownPerson).filter(KnownPerson.person_id == person_name).first()
            if not (known and known.category == "criminal" and known.criminal_status in ALERT_STATUSES):
                logger.warning(f"Rejected CRIMINAL_DETECTED for non-criminal identity: {person_name}")
                return {"status": "rejected", "reason": "identity is not an alert-eligible criminal"}
            display_name = known.name

        camera_lat, camera_lng, camera_name = _resolve_camera_geo(
            db, camera_id, camera_lat, camera_lng, camera_name,
        )

        if not message:
            if alert_type == "CRIMINAL_DETECTED":
                message = f"WATCHLIST MATCH (unverified): {display_name} at {camera_location}"
            else:
                message = alert_type.replace("_", " ").title()

        if display_name and person_name in message:
            message = message.replace(person_name, f"{display_name} ({person_name})", 1)

        if camera_lat is not None and camera_lng is not None:
            message += f" | GPS: {camera_lat:.5f}, {camera_lng:.5f}"

        webhook_payload = {
            "alert_type": alert_type,
            "severity": severity,
            "criminal_name": person_name,
            "person_name": person_name,
            "camera_location": camera_location,
            "camera_id": camera_id,
            "camera_name": camera_name,
            "camera_lat": camera_lat,
            "camera_lng": camera_lng,
            "maps_url": f"https://www.google.com/maps?q={camera_lat},{camera_lng}" if camera_lat else None,
            "track_id": track_id,
            "plate_number": plate_number,
            "message": message,
            "timestamp": datetime.utcnow().isoformat(),
        }
        needs_review = alert_type in REVIEW_REQUIRED_TYPES
        # Held: operators see it on the dashboard now; outside parties only after confirm.
        channels = "" if needs_review else await _send_webhooks(alert_type, webhook_payload)

        alert = Alert(
            alert_type=alert_type,
            severity=severity,
            camera_location=camera_location,
            camera_id=camera_id,
            track_id=track_id,
            person_name=person_name,
            plate_number=plate_number,
            message=message,
            details=_geo_details(camera_lat, camera_lng, camera_name, camera_id),
            channels_sent=channels or "websocket,dashboard,map",
            review_status="pending" if needs_review else "not_required",
        )
        db.add(alert)
        db.flush()

        geo_note = ""
        if camera_lat is not None and camera_lng is not None:
            geo_note = f" @ GPS({camera_lat:.5f},{camera_lng:.5f})"

        audit = AuditLog(
            user_id=None,
            username="SYSTEM",
            action="AUTO_ALERT",
            resource="alert",
            resource_id=str(alert.id),
            details=f"{alert_type}: {message} [camera={camera_id}]{geo_note}",
        )
        db.add(audit)
        db.flush()
        record_event(
            db, alert_type, severity, camera_id=camera_id, camera_location=camera_location,
            track_id=track_id, person_name=person_name, plate_number=plate_number,
            alert_id=alert.id, message=message, zone=zone, confidence=confidence,
            commit=False,
        )
        db.commit()
        db.refresh(alert)

        # Auto-open a server-side incident ticket for critical/high threats
        incident = None
        if severity in ("critical", "high"):
            try:
                from backend.services.incident_service import create_incident_from_alert
                incident = create_incident_from_alert(db, alert, created_by_name="SYSTEM")
                db.commit()
            except Exception as ie:
                logger.warning(f"Auto-incident create failed: {ie}")
                db.rollback()

        # Camera -> assigned police officer(s): assign the ticket, then page them (SMS webhook).
        officers, sms_sent = [], []
        if alert_type in officer_dispatch.OFFICER_ALERT_TYPES:
            try:
                officers = officer_dispatch.officers_for_camera(db, camera_id)
                if officers and incident is not None:
                    from backend.services.incident_service import add_event
                    incident.assigned_to = officers[0].id
                    incident.assigned_name = officers[0].username
                    add_event(db, incident, "ASSIGNED",
                              f"Auto-assigned to {', '.join(u.username for u in officers)} (camera {camera_id})", "SYSTEM")
                    db.commit()
                if officers:
                    text = officer_dispatch.sms_text(alert_type, display_name or person_name, camera_name,
                                                     camera_location, camera_lat, camera_lng,
                                                     incident.ticket_id if incident else None)
                    sms_sent = await officer_dispatch.sms_officers(
                        officers, text, {"alert_id": alert.id, "camera_id": camera_id, "lat": camera_lat, "lng": camera_lng})
                else:
                    logger.warning(f"No police officer assigned to camera {camera_id}; alert not routed")
            except Exception as oe:  # noqa: BLE001
                logger.warning(f"Officer dispatch failed: {oe}")
                db.rollback()

        payload = await broadcast_live_event(
            event_type=alert_type,
            severity=severity,
            camera_location=camera_location,
            camera_id=camera_id,
            track_id=track_id,
            person_name=person_name,
            message=message,
            camera_name=camera_name,
            camera_lat=camera_lat,
            camera_lng=camera_lng,
            extra={"alert_id": alert.id,
                   "assigned_officers": officer_dispatch.officer_summary(officers),
                   "officers_sms_sent": sms_sent},
        )
        payload["auto_dispatched"] = True

        await manager.broadcast(payload, "status")

        logger.info(
            f"AUTO ALERT: {alert_type} @ {camera_location} ({camera_id}) "
            f"GPS=({camera_lat},{camera_lng})"
        )
        return {"status": "dispatched", "alert_id": alert.id, "payload": payload}

    except Exception as e:
        logger.error(f"Alert dispatch failed: {e}")
        if own_session:
            db.rollback()
        raise
    finally:
        if own_session:
            db.close()

async def release_held_webhooks(alert: Alert) -> str:
    """Send the external webhooks that were held pending human confirmation."""
    payload = {
        "alert_type": alert.alert_type,
        "severity": alert.severity,
        "person_name": alert.person_name,
        "camera_location": alert.camera_location,
        "camera_id": alert.camera_id,
        "track_id": alert.track_id,
        "message": alert.message,
        "alert_id": alert.id,
        "review_status": alert.review_status,
        "reviewed_by": alert.reviewed_by,
        "timestamp": datetime.utcnow().isoformat(),
    }
    return await _send_webhooks(alert.alert_type, payload)


async def redispatch_alert(
    alert: Alert,
    message: Optional[str] = None,
    db: Optional[Session] = None,
) -> dict:
    """Re-broadcast an existing alert without creating a duplicate DB row."""
    own_session = db is None
    if own_session:
        db = SessionLocal()

    try:
        camera_lat = camera_lng = camera_name = None
        if alert.details:
            try:
                geo = json.loads(alert.details)
                camera_lat = geo.get("lat")
                camera_lng = geo.get("lng")
                camera_name = geo.get("camera_name")
            except Exception:
                pass

        camera_lat, camera_lng, camera_name = _resolve_camera_geo(
            db, alert.camera_id, camera_lat, camera_lng, camera_name,
        )

        dispatch_message = message or alert.message or alert.alert_type.replace("_", " ").title()

        webhook_payload = {
            "alert_type": alert.alert_type,
            "severity": alert.severity or "critical",
            "criminal_name": alert.person_name,
            "person_name": alert.person_name,
            "camera_location": alert.camera_location,
            "camera_id": alert.camera_id,
            "camera_name": camera_name,
            "camera_lat": camera_lat,
            "camera_lng": camera_lng,
            "maps_url": f"https://www.google.com/maps?q={camera_lat},{camera_lng}" if camera_lat else None,
            "track_id": alert.track_id,
            "plate_number": alert.plate_number,
            "message": dispatch_message,
            "timestamp": datetime.utcnow().isoformat(),
            "alert_id": alert.id,
            "manual_redispatch": True,
        }
        channels = await _send_webhooks(alert.alert_type, webhook_payload)

        payload = await broadcast_live_event(
            event_type=alert.alert_type,
            severity=alert.severity or "critical",
            camera_location=alert.camera_location,
            camera_id=alert.camera_id,
            track_id=alert.track_id,
            person_name=alert.person_name,
            message=dispatch_message,
            camera_name=camera_name,
            camera_lat=camera_lat,
            camera_lng=camera_lng,
        )
        payload["alert_id"] = alert.id
        payload["manual_redispatch"] = True
        payload["channels_sent"] = channels or "websocket,dashboard"

        await manager.broadcast(payload, "alerts")
        await manager.broadcast(payload, "status")

        logger.info(f"REDISPATCH: alert {alert.id} ({alert.alert_type})")
        return {"status": "redispatched", "alert_id": alert.id, "payload": payload}

    except Exception as e:
        logger.error(f"Alert redispatch failed: {e}")
        if own_session:
            db.rollback()
        raise
    finally:
        if own_session:
            db.close()

