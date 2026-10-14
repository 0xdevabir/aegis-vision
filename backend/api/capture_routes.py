"""Capture basket: zoomed subject stills the pipeline takes every few seconds during a red alert."""

import hashlib
import json
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session, defer

from backend.auth.auth import operator_or_admin
from backend.auth.guards import verify_internal_key, viewer_user
from backend.db.database import SessionLocal, get_db
from backend.models.alert import Alert
from backend.models.audit_log import AuditLog
from backend.models.capture import AlertCapture
from backend.models.config_entry import ConfigEntry
from backend.models.known_person import KnownPerson
from backend.models.user import User
from backend.utils.websocket import manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/captures", tags=["captures"])

MAX_BYTES = 4 * 1024 * 1024
MAX_PER_ALERT = int(os.getenv("CAPTURE_MAX_PER_ALERT", "120"))        # 10 minutes at one per 5 s
RETENTION_DAYS = int(os.getenv("CAPTURE_RETENTION_DAYS", "7"))
ALERT_WINDOW_MINUTES = 15
NON_PERSON_TYPES = {"FIRE_SMOKE_DETECTED"}

# What goes in the basket: "red" = red alerts only (watchlist match, armed, tracked, fire);
# "suspicious" = also people flagged for suspicious behaviour (a high, not critical, alert).
SCOPE_KEY = "capture.scope"
SCOPES = ("red", "suspicious")
SUSPICIOUS_TYPE = "SUSPICIOUS_BEHAVIOR"


def capture_scope(db: Session) -> str:
    row = db.query(ConfigEntry).filter(ConfigEntry.key == SCOPE_KEY).first()
    return row.value if row and row.value in SCOPES else "red"


def _serialize(c: AlertCapture, seq: Optional[int] = None, subject: Optional[dict] = None) -> dict:
    attrs = json.loads(c.attributes) if c.attributes else {}
    has_gps = c.camera_lat is not None and c.camera_lng is not None
    return {
        "id": c.id,
        "timestamp": c.timestamp.isoformat() if c.timestamp else None,
        "alert_id": c.alert_id,
        "alert_type": c.alert_type,
        "camera_id": c.camera_id,
        "camera_location": c.camera_location,
        "camera_name": c.camera_name,
        "camera_lat": c.camera_lat,
        "camera_lng": c.camera_lng,
        "maps_url": f"https://www.google.com/maps?q={c.camera_lat},{c.camera_lng}" if has_gps else None,
        "track_id": c.track_id,
        "person_name": c.person_name,
        "confidence": c.confidence,
        "width": c.width,
        "height": c.height,
        "source_width": c.source_width,
        "source_height": c.source_height,
        "bbox": [float(v) for v in c.bbox.split(",")] if c.bbox else None,
        "attributes": attrs,
        "subject": subject if subject is not None else attrs.get("subject"),
        "content_sha256": c.content_sha256,
        "seq": seq,
    }


def _find_alert(db: Session, alert_type: str, camera_id: str, track_id: Optional[int]) -> Optional[Alert]:
    cutoff = datetime.utcnow() - timedelta(minutes=ALERT_WINDOW_MINUTES)
    severity = "high" if alert_type == SUSPICIOUS_TYPE else "critical"
    q = db.query(Alert).filter(
        Alert.alert_type == alert_type, Alert.camera_id == camera_id,
        Alert.severity == severity, Alert.timestamp >= cutoff,
    ).order_by(Alert.id.desc())
    alert = q.filter(Alert.track_id == track_id).first() if track_id is not None else None
    return alert or q.first()


def _store(image: bytes, fields: dict) -> dict:
    """Blocking part of ingest (DB + image analysis); runs in the thread pool."""
    import cv2
    import numpy as np
    from utils.face_attributes import describe

    bgr = cv2.imdecode(np.frombuffer(image, np.uint8), cv2.IMREAD_COLOR)
    if bgr is None:
        raise HTTPException(status_code=400, detail="Not a readable image")

    db = SessionLocal()
    try:
        if fields["alert_type"] == SUSPICIOUS_TYPE and capture_scope(db) != "suspicious":
            return {"status": "off"}               # basket is set to red alerts only
        alert = _find_alert(db, fields["alert_type"], fields["camera_id"], fields["track_id"])
        if alert is None:
            # The alert and its first capture leave the pipeline together; let the alert land first.
            time.sleep(1.0)
            db.rollback()
            alert = _find_alert(db, fields["alert_type"], fields["camera_id"], fields["track_id"])
        if alert is None:
            return {"status": "no_alert"}          # e.g. the dispatcher rejected the identity

        taken = db.query(AlertCapture).filter(AlertCapture.alert_id == alert.id).count()
        if taken >= MAX_PER_ALERT:
            return {"status": "capped", "alert_id": alert.id}

        attrs = describe(bgr) if fields["alert_type"] not in NON_PERSON_TYPES else {}
        if fields["person_name"]:
            known = db.query(KnownPerson).filter(KnownPerson.person_id == fields["person_name"]).first()
            if known:
                attrs["subject"] = {
                    "name": known.name, "category": known.category,
                    "criminal_status": known.criminal_status, "threat_level": known.threat_level,
                }

        capture = AlertCapture(
            alert_id=alert.id,
            image_data=image,
            content_sha256=hashlib.sha256(image).hexdigest(),
            width=bgr.shape[1],
            height=bgr.shape[0],
            attributes=json.dumps(attrs) if attrs else None,
            **fields,
        )
        db.add(capture)
        if RETENTION_DAYS > 0:
            db.query(AlertCapture).filter(
                AlertCapture.timestamp < datetime.utcnow() - timedelta(days=RETENTION_DAYS),
            ).delete(synchronize_session=False)
        db.commit()
        db.refresh(capture)
        return {"status": "stored", "capture": _serialize(capture, seq=taken + 1)}
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@router.post("/ingest")
async def ingest_capture(
    file: UploadFile = File(...),
    camera_id: str = Form(...),
    alert_type: str = Form(...),
    camera_location: Optional[str] = Form(default=None),
    camera_name: Optional[str] = Form(default=None),
    camera_lat: Optional[float] = Form(default=None),
    camera_lng: Optional[float] = Form(default=None),
    track_id: Optional[int] = Form(default=None),
    person_name: Optional[str] = Form(default=None),
    confidence: Optional[float] = Form(default=None),
    bbox: Optional[str] = Form(default=None, pattern=r"^[0-9.]+(,[0-9.]+){3}$"),
    source_width: Optional[int] = Form(default=None),
    source_height: Optional[int] = Form(default=None),
    x_internal_key: Optional[str] = Header(default=None, alias="X-Internal-Key"),
):
    """Pipeline uploads one zoomed still of a red-alert subject; dashboards are told at once."""
    verify_internal_key(x_internal_key)
    image = await file.read(MAX_BYTES + 1)
    if not image or len(image) > MAX_BYTES:
        raise HTTPException(status_code=400, detail="Capture is empty or too large")

    result = await run_in_threadpool(_store, image, {
        "camera_id": camera_id, "alert_type": alert_type, "camera_location": camera_location,
        "camera_name": camera_name, "camera_lat": camera_lat, "camera_lng": camera_lng,
        "track_id": track_id, "person_name": person_name, "confidence": confidence,
        "bbox": bbox, "source_width": source_width, "source_height": source_height,
    })
    if result["status"] == "stored":
        await manager.broadcast({
            "alert_type": "ALERT_CAPTURE",
            "severity": "info",
            "camera_id": camera_id,
            "capture": result["capture"],
        }, "alerts")
        return {"status": "stored", "id": result["capture"]["id"], "alert_id": result["capture"]["alert_id"]}
    return result


@router.get("/")
def list_captures(
    limit: int = Query(default=60, ge=1, le=300),
    alert_id: Optional[int] = None,
    camera_id: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(operator_or_admin),
):
    """Newest first. Image bytes are served separately by /captures/{id}/image."""
    query = db.query(AlertCapture).options(defer(AlertCapture.image_data))
    if capture_scope(db) != "suspicious":
        query = query.filter(AlertCapture.alert_type != SUSPICIOUS_TYPE)
    if alert_id is not None:
        query = query.filter(AlertCapture.alert_id == alert_id)
    if camera_id:
        query = query.filter(AlertCapture.camera_id == camera_id)
    return [_serialize(c) for c in query.order_by(AlertCapture.id.desc()).limit(limit).all()]


class ScopeIn(BaseModel):
    scope: str


@router.get("/scope")
def get_scope(db: Session = Depends(get_db), user: User = Depends(operator_or_admin)):
    return {"scope": capture_scope(db)}


@router.put("/scope")
def set_scope(body: ScopeIn, db: Session = Depends(get_db), user: User = Depends(operator_or_admin)):
    """Red alerts only, or suspicious people too. The pipeline picks it up on its next config poll."""
    if body.scope not in SCOPES:
        raise HTTPException(status_code=400, detail=f"scope must be one of: {', '.join(SCOPES)}")
    entry = db.query(ConfigEntry).filter(ConfigEntry.key == SCOPE_KEY).first()
    old = entry.value if entry else None
    if old != body.scope:
        db.add(AuditLog(
            user_id=user.id, username=user.username, action="CONFIG_CHANGE",
            resource="config", resource_id=SCOPE_KEY, details=f"{old!r} -> {body.scope!r}",
        ))
        if entry:
            entry.value, entry.updated_by = body.scope, user.id
        else:
            db.add(ConfigEntry(key=SCOPE_KEY, value=body.scope, updated_by=user.id,
                               description="Capture basket: red alerts only, or suspicious people too"))
        db.commit()
    return {"scope": body.scope}


@router.get("/{capture_id}/image")
def get_capture_image(
    capture_id: int,
    token: Optional[str] = Query(default=None),
    w: Optional[int] = Query(default=None, ge=32, le=1024, description="Thumbnail width"),
    db: Session = Depends(get_db),
):
    viewer_user(token, db)
    capture = db.query(AlertCapture).filter(AlertCapture.id == capture_id).first()
    if not capture:
        raise HTTPException(status_code=404, detail="Capture not found")
    content = capture.image_data
    if w and capture.width and w < capture.width:
        import cv2
        import numpy as np

        bgr = cv2.imdecode(np.frombuffer(content, np.uint8), cv2.IMREAD_COLOR)
        if bgr is not None:
            small = cv2.resize(bgr, (w, max(1, round(bgr.shape[0] * w / bgr.shape[1]))), interpolation=cv2.INTER_AREA)
            ok, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 82])
            if ok:
                content = buf.tobytes()
    return Response(content=content, media_type="image/jpeg",
                    headers={"Cache-Control": "private, max-age=86400"})
