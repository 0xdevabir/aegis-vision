"""External integrations — police CAD / SMS / radio / security webhooks."""

import logging
import os
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.db.database import get_db
from backend.models.user import User
from backend.models.alert import Alert
from backend.models.audit_log import AuditLog
from backend.auth.auth import admin_only, operator_or_admin
from backend.services.alert_dispatcher import _send_webhooks

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/integrations", tags=["integrations"])


class TestWebhookRequest(BaseModel):
    channel: str = "security"  # law_enforcement | emergency | security | sms
    message: str = "Aegis integration test"


class DispatchRequest(BaseModel):
    alert_id: int
    channels: Optional[list[str]] = None
    note: Optional[str] = None


def _channel_urls() -> dict:
    return {
        "law_enforcement": os.getenv("LAW_ENFORCEMENT_WEBHOOK", ""),
        "emergency": os.getenv("EMERGENCY_WEBHOOK", ""),
        "security": os.getenv("SECURITY_TEAM_WEBHOOK", ""),
        "sms": os.getenv("SMS_WEBHOOK", ""),  # e.g. Twilio Function / custom SMS gateway
        "cad": os.getenv("CAD_WEBHOOK", "") or os.getenv("LAW_ENFORCEMENT_WEBHOOK", ""),
        "radio": os.getenv("RADIO_WEBHOOK", ""),
    }


@router.get("/status")
def integration_status(user: User = Depends(operator_or_admin)):
    urls = _channel_urls()
    return {
        "alerts_enabled": os.getenv("ALERTS_ENABLED", "false").lower() == "true",
        "channels": {
            name: {"configured": bool(url), "url_host": _host(url) if url else None}
            for name, url in urls.items()
        },
        "hint": "Set ALERTS_ENABLED=true and webhook URLs in .env for live CAD/SMS dispatch",
    }


def _host(url: str) -> str:
    try:
        from urllib.parse import urlparse
        return urlparse(url).netloc or url[:40]
    except Exception:
        return "configured"


@router.post("/test")
def test_webhook(body: TestWebhookRequest, user: User = Depends(admin_only)):
    urls = _channel_urls()
    url = urls.get(body.channel)
    if not url:
        raise HTTPException(400, f"Channel '{body.channel}' has no webhook URL configured")
    if os.getenv("ALERTS_ENABLED", "false").lower() != "true":
        raise HTTPException(400, "ALERTS_ENABLED is false — enable it in .env first")
    payload = {
        "source": "Aegis",
        "channel": body.channel,
        "message": body.message,
        "test": True,
        "operator": user.username,
    }
    try:
        resp = httpx.post(url, json=payload, timeout=8.0)
        return {"status": "sent", "http_status": resp.status_code, "channel": body.channel}
    except Exception as e:
        raise HTTPException(502, f"Webhook failed: {e}")


@router.post("/dispatch")
async def manual_channel_dispatch(
    body: DispatchRequest,
    db: Session = Depends(get_db),
    user: User = Depends(operator_or_admin),
):
    alert = db.query(Alert).filter(Alert.id == body.alert_id).first()
    if not alert:
        raise HTTPException(404, "Alert not found")

    payload = {
        "alert_id": alert.id,
        "alert_type": alert.alert_type,
        "severity": alert.severity,
        "message": alert.message,
        "camera_location": alert.camera_location,
        "camera_id": alert.camera_id,
        "person_name": alert.person_name,
        "plate_number": alert.plate_number,
        "operator": user.username,
        "note": body.note,
        "manual": True,
    }

    # Force send even if ALERTS_ENABLED is false when operator explicitly dispatches
    urls = _channel_urls()
    channels = body.channels or ["cad", "security", "sms"]
    sent, failed = [], []
    async with httpx.AsyncClient() as client:
        for ch in channels:
            url = urls.get(ch)
            if not url:
                continue
            try:
                resp = await client.post(url, json=payload, timeout=8.0)
                (sent if resp.status_code < 400 else failed).append(ch)
            except Exception as e:  # noqa: BLE001
                logger.error(f"Manual dispatch to {ch} failed: {e}")
                failed.append(ch)

    # Also run the standard severity-based webhook set
    auto = await _send_webhooks(alert.alert_type, payload)

    db.add(AuditLog(
        user_id=user.id,
        username=user.username,
        action="EXTERNAL_DISPATCH",
        resource="alert",
        resource_id=str(alert.id),
        details=f"channels={','.join(sent) or auto or 'none'} failed={','.join(failed) or 'none'} note={body.note or ''}",
    ))
    db.commit()
    return {"status": "dispatched" if sent or auto else "failed", "channels": sent, "failed": failed, "auto_channels": auto}
