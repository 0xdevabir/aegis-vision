"""System status and pipeline heartbeat tracking."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel

from backend.auth.auth import operator_or_admin
from backend.models.user import User
from backend.utils.websocket import manager
from backend.utils.events import build_event_payload

from backend.auth.guards import verify_internal_key

router = APIRouter(prefix="/system", tags=["system"])

_INSECURE_KEYS = {"", "pipeline-internal-key-change-me"}
_live_analytics: dict = {}
_pipeline_status: dict = {
    "online": False,
    "last_heartbeat": None,
    "cameras": {},
    "version": "5.0.0",
}


class HeartbeatPayload(BaseModel):
    camera_id: str
    camera_location: Optional[str] = None
    fps: Optional[float] = None
    threat_score: Optional[int] = None
    frame_number: Optional[int] = None
    analytics: Optional[dict] = None


@router.get("/status")
def get_system_status(user: User = Depends(operator_or_admin)):
    from backend.services.ha import redis_health, camera_offline_sla

    cameras = {}
    offline = 0
    for cam_id, meta in _pipeline_status.get("cameras", {}).items():
        sla = camera_offline_sla(meta.get("last_seen"))
        cameras[cam_id] = {**meta, "sla": sla}
        if sla == "offline":
            offline += 1

    from backend.services.model_health import model_status

    return {
        **_pipeline_status,
        "models": model_status(),
        "cameras": cameras,
        "offline_cameras": offline,
        "redis": redis_health(),
        "websocket_connections": {
            "alerts": manager.get_connection_count("alerts"),
            "status": manager.get_connection_count("status"),
        },
    }


@router.post("/heartbeat")
async def pipeline_heartbeat(
    body: HeartbeatPayload,
    x_internal_key: Optional[str] = Header(default=None, alias="X-Internal-Key"),
):
    verify_internal_key(x_internal_key)
    now = datetime.utcnow().isoformat()
    _pipeline_status["online"] = True
    _pipeline_status["last_heartbeat"] = now
    _pipeline_status["cameras"][body.camera_id] = {
        "camera_location": body.camera_location,
        "fps": body.fps,
        "threat_score": body.threat_score,
        "frame_number": body.frame_number,
        "last_seen": now,
    }

    payload = build_event_payload(
        event_type="PIPELINE_HEARTBEAT",
        severity="info",
        camera_id=body.camera_id,
        camera_location=body.camera_location,
        message=f"FPS: {body.fps:.1f}" if body.fps else "Pipeline active",
    )
    payload["fps"] = body.fps
    payload["threat_score"] = body.threat_score
    if body.analytics:
        update_live_analytics(body.camera_id, body.analytics)
    await manager.broadcast(payload, "status")
    return {"status": "ok", "camera_id": body.camera_id}






def get_live_analytics() -> dict:
    return _live_analytics


def update_live_analytics(camera_id: str, data: dict) -> None:
    _live_analytics[camera_id] = {**data, "camera_id": camera_id, "updated_at": datetime.utcnow().isoformat()}
