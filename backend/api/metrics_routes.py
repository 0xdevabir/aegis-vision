"""Prometheus-compatible metrics endpoint."""

import hmac
import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.auth.auth import ROLES_ADMIN, get_current_user, security
from backend.db.database import get_db
from backend.models.alert import Alert

router = APIRouter(prefix="/metrics", tags=["metrics"])


def metrics_auth(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
) -> None:
    """Scrapers send `Authorization: Bearer $METRICS_TOKEN`; an admin session also works."""
    token = os.getenv("METRICS_TOKEN", "")
    if token and credentials and hmac.compare_digest(credentials.credentials.encode(), token.encode()):
        return
    if get_current_user(request, credentials, db).role not in ROLES_ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")


def _label(value) -> str:
    return str(value or "unknown").replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


@router.get("", dependencies=[Depends(metrics_auth)])
def prometheus_metrics(db: Session = Depends(get_db)):
    from backend.utils.websocket import manager
    from backend.api.system_routes import _pipeline_status

    lines = [
        "# HELP aegis_websocket_connections Active WebSocket connections",
        "# TYPE aegis_websocket_connections gauge",
        f'aegis_websocket_connections{{channel="alerts"}} {manager.get_connection_count("alerts")}',
        f'aegis_websocket_connections{{channel="status"}} {manager.get_connection_count("status")}',
        "# HELP aegis_pipeline_online Pipeline heartbeat status (1=online)",
        "# TYPE aegis_pipeline_online gauge",
        f"aegis_pipeline_online {1 if _pipeline_status.get('online') else 0}",
    ]

    cameras = _pipeline_status.get("cameras", {})
    now = datetime.utcnow()
    for name, help_text, value in (
        ("aegis_camera_fps", "Frames per second processed, from the last heartbeat", lambda m: m.get("fps")),
        ("aegis_camera_threat_score", "Threat score from the last heartbeat", lambda m: m.get("threat_score")),
        ("aegis_camera_heartbeat_age_seconds", "Seconds since the camera last reported",
         lambda m: (now - datetime.fromisoformat(m["last_seen"])).total_seconds() if m.get("last_seen") else None),
    ):
        lines += [f"# HELP {name} {help_text}", f"# TYPE {name} gauge"]
        for cam_id, meta in cameras.items():
            v = value(meta)
            if v is not None:
                lines.append(f'{name}{{camera="{_label(cam_id)}"}} {float(v):.3f}')

    lines += ["# HELP aegis_alerts Alerts stored, by type and severity", "# TYPE aegis_alerts gauge"]
    for alert_type, severity, count in (
        db.query(Alert.alert_type, Alert.severity, func.count(Alert.id))
        .group_by(Alert.alert_type, Alert.severity).all()
    ):
        lines.append(f'aegis_alerts{{type="{_label(alert_type)}",severity="{_label(severity)}"}} {count}')

    body = "\n".join(lines) + "\n"
    return Response(body, media_type="text/plain; version=0.0.4")
