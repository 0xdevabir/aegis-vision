"""
Professional VMS API — continuous DVR playback, PTZ, camera capabilities, retention.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import desc

from backend.db.database import get_db
from backend.models.user import User
from backend.models.recording import RecordingClip
from backend.models.camera import Camera
from backend.auth.auth import operator_or_admin, admin_only
from backend.services import ptz as ptz_svc
from paths import RECORDINGS_DIR, ROOT
from utils.media.dvr import purge_old_recordings

from backend.auth.guards import safe_media_path, verify_internal_key

router = APIRouter(prefix="/vms", tags=["vms"])


class SegmentIngest(BaseModel):
    camera_id: str
    camera_location: Optional[str] = None
    started_at: str
    ended_at: Optional[str] = None
    duration_seconds: Optional[float] = None
    trigger: str = "continuous"
    alert_type: Optional[str] = None
    file_path: str
    file_sha256: Optional[str] = None
    frame_count: Optional[int] = None
    thumbnail_path: Optional[str] = None


class PTZMove(BaseModel):
    pan: float = 0.0
    tilt: float = 0.0
    zoom: float = 0.0


class PTZAbsolute(BaseModel):
    pan: float = 0.0
    tilt: float = 0.0
    zoom: float = 1.0


class PTZMode(BaseModel):
    mode: str  # digital | onvif


class PTZPreset(BaseModel):
    name: str


class OnvifConfig(BaseModel):
    host: str
    username: str
    password: str
    profile_token: Optional[str] = "Profile_1"


# ---------------------------------------------------------------------------
# Capabilities / status
# ---------------------------------------------------------------------------

@router.get("/status")
def vms_status(db: Session = Depends(get_db), user: User = Depends(operator_or_admin)):
    retention = float(os.getenv("DVR_RETENTION_HOURS", "48"))
    segment = float(os.getenv("DVR_SEGMENT_SECONDS", "60"))
    continuous = (
        db.query(RecordingClip)
        .filter(RecordingClip.trigger == "continuous")
        .count()
    )
    events = (
        db.query(RecordingClip)
        .filter(RecordingClip.trigger == "event")
        .count()
    )
    cameras = db.query(Camera).all()
    return {
        "dvr_enabled": os.getenv("DVR_ENABLED", "true").lower() == "true",
        "segment_seconds": segment,
        "retention_hours": retention,
        "continuous_segments": continuous,
        "event_clips": events,
        "cameras": [
            {
                "camera_id": c.camera_id,
                "name": c.name,
                "active": c.active,
                "ptz": ptz_svc.state_dict(ptz_svc.get_state(c.camera_id)),
            }
            for c in cameras
        ],
        "features": {
            "continuous_dvr": True,
            "event_recording": True,
            "timeline_scrub": True,
            "digital_ptz": True,
            "onvif_ptz": True,
            "presets": True,
        },
    }


# ---------------------------------------------------------------------------
# Continuous segment ingest (pipeline) + retention
# ---------------------------------------------------------------------------

@router.post("/segments")
def ingest_segment(
    body: SegmentIngest,
    x_internal_key: Optional[str] = Header(default=None, alias="X-Internal-Key"),
    db: Session = Depends(get_db),
):
    verify_internal_key(x_internal_key)
    started = datetime.fromisoformat(body.started_at.replace("Z", ""))
    ended = datetime.fromisoformat(body.ended_at.replace("Z", "")) if body.ended_at else None

    # Store path relative to project root when possible
    # Reject paths outside the recordings dir; store relative to project root
    fpath = str(safe_media_path(body.file_path, RECORDINGS_DIR, ROOT).relative_to(ROOT.resolve()))
    thumb = None
    if body.thumbnail_path:
        thumb = str(safe_media_path(body.thumbnail_path, RECORDINGS_DIR, ROOT).relative_to(ROOT.resolve()))

    clip = RecordingClip(
        camera_id=body.camera_id,
        camera_location=body.camera_location,
        started_at=started,
        ended_at=ended,
        duration_seconds=body.duration_seconds,
        trigger=body.trigger or "continuous",
        alert_type=body.alert_type,
        file_path=fpath,
        file_sha256=body.file_sha256,
        frame_count=body.frame_count,
        thumbnail_path=thumb,
    )
    db.add(clip)
    db.commit()
    db.refresh(clip)

    # Opportunistic retention purge
    retention = float(os.getenv("DVR_RETENTION_HOURS", "48"))
    removed = purge_old_recordings(RECORDINGS_DIR, retention)
    if removed:
        cutoff = datetime.utcnow() - timedelta(hours=retention)
        db.query(RecordingClip).filter(RecordingClip.started_at < cutoff).delete()
        db.commit()

    return {"status": "ok", "id": clip.id, "purged_files": removed}


@router.post("/retention/purge")
def purge(db: Session = Depends(get_db), admin: User = Depends(admin_only)):
    retention = float(os.getenv("DVR_RETENTION_HOURS", "48"))
    removed = purge_old_recordings(RECORDINGS_DIR, retention)
    cutoff = datetime.utcnow() - timedelta(hours=retention)
    db_removed = db.query(RecordingClip).filter(RecordingClip.started_at < cutoff).delete()
    db.commit()
    return {"purged_files": removed, "purged_rows": db_removed, "retention_hours": retention}


# ---------------------------------------------------------------------------
# Timeline + scrub playback
# ---------------------------------------------------------------------------

@router.get("/timeline")
def timeline(
    camera_id: Optional[str] = None,
    hours: float = 24,
    trigger: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(operator_or_admin),
):
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    q = db.query(RecordingClip).filter(RecordingClip.started_at >= cutoff)
    if camera_id:
        q = q.filter(RecordingClip.camera_id == camera_id)
    if trigger:
        q = q.filter(RecordingClip.trigger == trigger)
    clips = q.order_by(RecordingClip.started_at.asc()).limit(500).all()

    coverage = []
    for c in clips:
        coverage.append({
            "id": c.id,
            "camera_id": c.camera_id,
            "start": c.started_at.isoformat() if c.started_at else None,
            "end": c.ended_at.isoformat() if c.ended_at else None,
            "duration": c.duration_seconds,
            "trigger": c.trigger,
            "alert_type": c.alert_type,
            "sha256": c.file_sha256,
            "has_thumb": bool(c.thumbnail_path),
        })

    continuous_hours = sum(
        (c.duration_seconds or 0) for c in clips if c.trigger == "continuous"
    ) / 3600.0

    return {
        "period_hours": hours,
        "camera_id": camera_id,
        "segments": coverage,
        "continuous_coverage_hours": round(continuous_hours, 2),
        "segment_count": len(coverage),
    }


@router.get("/playback")
def playback_at(
    camera_id: str,
    t: str = Query(..., description="ISO timestamp to scrub to"),
    db: Session = Depends(get_db),
    user: User = Depends(operator_or_admin),
):
    """Find the continuous/event segment covering timestamp t and stream the file."""
    try:
        ts = datetime.fromisoformat(t.replace("Z", ""))
    except ValueError:
        raise HTTPException(400, "Invalid timestamp — use ISO format")

    clip = (
        db.query(RecordingClip)
        .filter(
            RecordingClip.camera_id == camera_id,
            RecordingClip.started_at <= ts,
        )
        .order_by(desc(RecordingClip.started_at))
        .first()
    )
    if not clip:
        raise HTTPException(404, "No recording covers this time")

    # Prefer segment whose end is after t
    if clip.ended_at and clip.ended_at < ts:
        # try next overlapping
        clip2 = (
            db.query(RecordingClip)
            .filter(
                RecordingClip.camera_id == camera_id,
                RecordingClip.started_at <= ts,
                RecordingClip.ended_at >= ts,
            )
            .order_by(desc(RecordingClip.started_at))
            .first()
        )
        if clip2:
            clip = clip2

    path = safe_media_path(clip.file_path, RECORDINGS_DIR, ROOT)
    if not path.exists():
        raise HTTPException(404, "Recording file missing on disk")

    media = "video/mp4" if path.suffix.lower() == ".mp4" else (
        "video/x-msvideo" if path.suffix.lower() == ".avi" else "image/jpeg"
    )
    offset = 0.0
    if clip.started_at:
        offset = max(0.0, (ts - clip.started_at).total_seconds())

    return FileResponse(
        path,
        media_type=media,
        filename=path.name,
        headers={
            "X-Segment-Id": str(clip.id),
            "X-Segment-Start": clip.started_at.isoformat() if clip.started_at else "",
            "X-Seek-Offset-Seconds": f"{offset:.2f}",
            "Accept-Ranges": "bytes",
        },
    )


@router.get("/segments/{clip_id}/thumb")
def segment_thumb(clip_id: int, db: Session = Depends(get_db), user: User = Depends(operator_or_admin)):
    clip = db.query(RecordingClip).filter(RecordingClip.id == clip_id).first()
    if not clip or not clip.thumbnail_path:
        raise HTTPException(404, "No thumbnail")
    path = safe_media_path(clip.thumbnail_path, RECORDINGS_DIR, ROOT)
    if not path.exists():
        raise HTTPException(404, "Thumbnail missing")
    return FileResponse(path, media_type="image/jpeg")


# ---------------------------------------------------------------------------
# PTZ
# ---------------------------------------------------------------------------

@router.get("/ptz/{camera_id}")
def ptz_status(camera_id: str, user: User = Depends(operator_or_admin)):
    return ptz_svc.state_dict(ptz_svc.get_state(camera_id))


@router.post("/ptz/{camera_id}/mode")
def ptz_mode(camera_id: str, body: PTZMode, user: User = Depends(operator_or_admin)):
    try:
        st = ptz_svc.set_mode(camera_id, body.mode)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return ptz_svc.state_dict(st)


@router.post("/ptz/{camera_id}/move")
def ptz_move(camera_id: str, body: PTZMove, user: User = Depends(operator_or_admin)):
    st = ptz_svc.continuous_move(camera_id, body.pan, body.tilt, body.zoom)
    return ptz_svc.state_dict(st)


@router.post("/ptz/{camera_id}/absolute")
def ptz_absolute(camera_id: str, body: PTZAbsolute, user: User = Depends(operator_or_admin)):
    st = ptz_svc.get_state(camera_id)
    if st.mode == "digital":
        st = ptz_svc.digital_absolute(camera_id, body.pan, body.tilt, body.zoom)
    else:
        st = ptz_svc.continuous_move(camera_id, 0, 0, 0)  # ensure state
        st.onvif_pan, st.onvif_tilt, st.onvif_zoom = body.pan, body.tilt, max(0, min(1, body.zoom))
        if st.onvif_host:
            try:
                ptz_svc._onvif_absolute(st, st.onvif_pan, st.onvif_tilt, st.onvif_zoom)
            except Exception as e:
                st.last_error = str(e)
    return ptz_svc.state_dict(st)


@router.post("/ptz/{camera_id}/stop")
def ptz_stop(camera_id: str, user: User = Depends(operator_or_admin)):
    return ptz_svc.state_dict(ptz_svc.stop(camera_id))


@router.post("/ptz/{camera_id}/home")
def ptz_home(camera_id: str, user: User = Depends(operator_or_admin)):
    st = ptz_svc.get_state(camera_id)
    if st.mode == "digital":
        return ptz_svc.state_dict(ptz_svc.digital_home(camera_id))
    st.onvif_pan = st.onvif_tilt = st.onvif_zoom = 0.0
    if st.onvif_host:
        try:
            ptz_svc._onvif_absolute(st, 0, 0, 0)
        except Exception as e:
            st.last_error = str(e)
    return ptz_svc.state_dict(st)


@router.post("/ptz/{camera_id}/presets")
def ptz_save_preset(camera_id: str, body: PTZPreset, user: User = Depends(operator_or_admin)):
    return ptz_svc.state_dict(ptz_svc.save_preset(camera_id, body.name))


@router.post("/ptz/{camera_id}/presets/{name}/goto")
def ptz_goto(camera_id: str, name: str, user: User = Depends(operator_or_admin)):
    try:
        return ptz_svc.state_dict(ptz_svc.goto_preset(camera_id, name))
    except KeyError as e:
        raise HTTPException(404, str(e))


@router.post("/ptz/{camera_id}/onvif")
def configure_onvif(camera_id: str, body: OnvifConfig, user: User = Depends(admin_only)):
    st = ptz_svc.configure_onvif(camera_id, body.host, body.username, body.password, body.profile_token)
    return ptz_svc.state_dict(st)
