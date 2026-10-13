"""VMS timeline / recording clip API."""

import hashlib
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import desc

from backend.db.database import get_db
from backend.models.user import User
from backend.models.recording import RecordingClip
from backend.auth.auth import operator_or_admin
from paths import RECORDINGS_DIR, ROOT

from backend.auth.guards import safe_media_path, verify_internal_key

router = APIRouter(prefix="/recordings", tags=["recordings"])


class ClipOut(BaseModel):
    id: int
    camera_id: str
    camera_location: Optional[str]
    started_at: datetime
    ended_at: Optional[datetime]
    duration_seconds: Optional[float]
    trigger: str
    alert_type: Optional[str]
    file_path: str
    file_sha256: Optional[str]
    frame_count: Optional[int]
    notes: Optional[str]
    created_at: Optional[datetime]

    class Config:
        from_attributes = True


@router.get("/", response_model=List[ClipOut])
def list_clips(
    camera_id: Optional[str] = None,
    hours: int = 24,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    user: User = Depends(operator_or_admin),
):
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    q = db.query(RecordingClip).filter(RecordingClip.started_at >= cutoff)
    if camera_id:
        q = q.filter(RecordingClip.camera_id == camera_id)
    return q.order_by(desc(RecordingClip.started_at)).offset(skip).limit(limit).all()


@router.get("/timeline")
def timeline(
    camera_id: Optional[str] = None,
    hours: int = 24,
    db: Session = Depends(get_db),
    user: User = Depends(operator_or_admin),
):
    """Flattened timeline for the Live Monitoring replay UI."""
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    q = db.query(RecordingClip).filter(RecordingClip.started_at >= cutoff)
    if camera_id:
        q = q.filter(RecordingClip.camera_id == camera_id)
    clips = q.order_by(RecordingClip.started_at.asc()).limit(200).all()
    return {
        "period_hours": hours,
        "camera_id": camera_id,
        "events": [
            {
                "id": c.id,
                "camera_id": c.camera_id,
                "t": c.started_at.isoformat() if c.started_at else None,
                "trigger": c.trigger,
                "alert_type": c.alert_type,
                "duration_seconds": c.duration_seconds,
                "file_sha256": c.file_sha256,
            }
            for c in clips
        ],
    }


@router.get("/{clip_id}/file")
def download_clip(clip_id: int, db: Session = Depends(get_db), user: User = Depends(operator_or_admin)):
    clip = db.query(RecordingClip).filter(RecordingClip.id == clip_id).first()
    if not clip:
        raise HTTPException(404, "Clip not found")
    path = safe_media_path(clip.file_path, RECORDINGS_DIR, ROOT)
    if not path.exists():
        raise HTTPException(404, "Clip file missing on disk")
    media = "video/mp4" if path.suffix.lower() == ".mp4" else "image/jpeg"
    return FileResponse(path, media_type=media, filename=path.name)


@router.post("/ingest", response_model=ClipOut)
async def ingest_clip(
    camera_id: str = Form(...),
    camera_location: str = Form(""),
    trigger: str = Form("event"),
    alert_type: str = Form(None),
    started_at: Optional[str] = Form(None),
    frame_count: Optional[int] = Form(None),
    file: UploadFile = File(...),
    x_internal_key: Optional[str] = Header(default=None, alias="X-Internal-Key"),
    db: Session = Depends(get_db),
):
    """Pipeline / recorder uploads an event clip (mp4 or jpg)."""
    verify_internal_key(x_internal_key)
    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty file")

    digest = hashlib.sha256(data).hexdigest()
    stamp = datetime.utcnow()
    start = datetime.fromisoformat(started_at) if started_at else stamp

    if not re.fullmatch(r"[A-Za-z0-9_-]{1,50}", camera_id):
        raise HTTPException(400, "Invalid camera_id")
    dest_dir = RECORDINGS_DIR / camera_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(file.filename or "clip.jpg").suffix.lower()
    if ext not in {".mp4", ".avi", ".jpg", ".jpeg"}:
        raise HTTPException(400, "Unsupported file type")
    fname = f"{start.strftime('%Y%m%dT%H%M%S')}_{digest[:10]}{ext}"
    dest = dest_dir / fname
    dest.write_bytes(data)

    rel = str(dest.relative_to(ROOT))
    clip = RecordingClip(
        camera_id=camera_id,
        camera_location=camera_location or None,
        started_at=start,
        ended_at=stamp,
        duration_seconds=max(0.0, (stamp - start).total_seconds()),
        trigger=trigger,
        alert_type=alert_type,
        file_path=rel,
        file_sha256=digest,
        frame_count=frame_count,
    )
    db.add(clip)
    db.commit()
    db.refresh(clip)
    return clip
