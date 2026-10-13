"""Shared live-event payload builder and WebSocket broadcaster."""

from datetime import datetime
from typing import Optional

from backend.utils.websocket import manager


def _maps_url(lat: Optional[float], lng: Optional[float]) -> Optional[str]:
    if lat is None or lng is None:
        return None
    return f"https://www.google.com/maps?q={lat},{lng}"


def build_event_payload(
    event_type: str,
    severity: str = "info",
    camera_location: Optional[str] = None,
    camera_id: Optional[str] = None,
    track_id: Optional[int] = None,
    person_name: Optional[str] = None,
    message: Optional[str] = None,
    camera_name: Optional[str] = None,
    camera_lat: Optional[float] = None,
    camera_lng: Optional[float] = None,
) -> dict:
    maps = _maps_url(camera_lat, camera_lng)
    return {
        "alert_type": event_type,
        "severity": severity,
        "camera_location": camera_location,
        "camera_id": camera_id,
        "camera_name": camera_name,
        "camera_lat": camera_lat,
        "camera_lng": camera_lng,
        "maps_url": maps,
        "track_id": track_id,
        "person_name": person_name,
        "message": message,
        "timestamp": datetime.utcnow().isoformat(),
        "data": {
            "camera_location": camera_location,
            "camera_id": camera_id,
            "camera_name": camera_name,
            "camera_lat": camera_lat,
            "camera_lng": camera_lng,
            "maps_url": maps,
            "criminal_name": person_name,
            "track_id": track_id,
            "message": message,
        },
    }


async def broadcast_live_event(
    event_type: str,
    severity: str = "info",
    camera_location: Optional[str] = None,
    camera_id: Optional[str] = None,
    track_id: Optional[int] = None,
    person_name: Optional[str] = None,
    message: Optional[str] = None,
    camera_name: Optional[str] = None,
    camera_lat: Optional[float] = None,
    camera_lng: Optional[float] = None,
    extra: Optional[dict] = None,
) -> dict:
    payload = build_event_payload(
        event_type=event_type,
        severity=severity,
        camera_location=camera_location,
        camera_id=camera_id,
        track_id=track_id,
        person_name=person_name,
        message=message,
        camera_name=camera_name,
        camera_lat=camera_lat,
        camera_lng=camera_lng,
    )
    if extra:
        payload.update(extra)
    await manager.broadcast(payload, "alerts")
    return payload
