"""
Automated notification hub for the CV pipeline.
One criminal detection on any camera triggers ALL channels automatically.
"""

import logging
import threading
from typing import Optional, Callable

from utils.alerts.event_publisher import dispatch_alert
from utils.config.camera_registry import maps_url

logger = logging.getLogger("HumanAnalysis")


class NotificationHub:
    """Central hub — throttles and dispatches alerts across every defense channel."""

    def __init__(
        self,
        alarm_callback: Optional[Callable] = None,
        alarm_interval: float = 5.0,
    ):
        self.alarm_callback = alarm_callback
        self.alarm_interval = alarm_interval
        self._last_alarm: dict = {}

    def _should_fire(self, key: str, now: float) -> bool:
        if now - self._last_alarm.get(key, 0) < self.alarm_interval:
            return False
        self._last_alarm[key] = now
        return True

    def _sound_alarm(self) -> None:
        if self.alarm_callback:
            threading.Thread(target=self.alarm_callback, daemon=True).start()

    def _geo_message(self, base: str, camera_location: str, camera_id: str,
                     camera_lat: Optional[float], camera_lng: Optional[float]) -> str:
        msg = f"{base} at {camera_location} (Camera: {camera_id})"
        if camera_lat is not None and camera_lng is not None:
            msg += f" — GPS: {camera_lat:.5f}, {camera_lng:.5f}"
            url = maps_url(camera_lat, camera_lng)
            if url:
                msg += f" | Map: {url}"
        return msg

    def criminal_detected(
        self,
        criminal_name: str,
        camera_location: str,
        camera_id: str,
        track_id: int,
        now: float,
        camera_name: str = "",
        camera_lat: Optional[float] = None,
        camera_lng: Optional[float] = None,
        confidence: Optional[float] = None,
    ) -> None:
        key = f"criminal_{camera_id}_{track_id}"
        if not self._should_fire(key, now):
            return

        self._sound_alarm()
        message = self._geo_message(
            f"WATCHLIST MATCH (unverified): {criminal_name}",
            camera_location, camera_id, camera_lat, camera_lng,
        )
        logger.critical(message)

        dispatch_alert(
            alert_type="CRIMINAL_DETECTED",
            severity="critical",
            camera_location=camera_location,
            camera_id=camera_id,
            track_id=track_id,
            person_name=criminal_name,
            camera_name=camera_name or camera_location,
            camera_lat=camera_lat,
            camera_lng=camera_lng,
            message=message,
            confidence=confidence,
        )

    def weapon_detected(
        self,
        camera_location: str,
        camera_id: str,
        track_id: int,
        now: float,
        camera_lat: Optional[float] = None,
        camera_lng: Optional[float] = None,
        confidence: Optional[float] = None,
    ) -> None:
        key = f"weapon_{camera_id}"
        if not self._should_fire(key, now):
            return

        self._sound_alarm()
        dispatch_alert(
            alert_type="WEAPON_DETECTED",
            severity="critical",
            camera_location=camera_location,
            camera_id=camera_id,
            track_id=track_id,
            confidence=confidence,
            camera_lat=camera_lat,
            camera_lng=camera_lng,
            message=self._geo_message(
                "WEAPON DETECTED", camera_location, camera_id, camera_lat, camera_lng,
            ),
        )

    def fire_smoke_detected(
        self,
        camera_location: str,
        camera_id: str,
        now: float,
        kind: str = "fire",
        confidence: Optional[float] = None,
        camera_lat: Optional[float] = None,
        camera_lng: Optional[float] = None,
    ) -> None:
        if not self._should_fire(f"fire_{camera_id}", now):
            return
        self._sound_alarm()
        dispatch_alert(
            alert_type="FIRE_SMOKE_DETECTED",
            severity="critical",
            camera_location=camera_location,
            camera_id=camera_id,
            confidence=confidence,
            camera_lat=camera_lat,
            camera_lng=camera_lng,
            message=self._geo_message(
                f"{kind.upper()} DETECTED (confirmed over several frames)",
                camera_location, camera_id, camera_lat, camera_lng,
            ),
        )

    def fall_suspected(
        self,
        camera_location: str,
        camera_id: str,
        track_id: int,
        now: float,
        camera_lat: Optional[float] = None,
        camera_lng: Optional[float] = None,
    ) -> None:
        if not self._should_fire(f"fall_{camera_id}_{track_id}", now):
            return
        dispatch_alert(
            alert_type="FALL_SUSPECTED",
            severity="high",
            camera_location=camera_location,
            camera_id=camera_id,
            track_id=track_id,
            camera_lat=camera_lat,
            camera_lng=camera_lng,
            message=self._geo_message(
                "Possible fall — person down, please check on camera",
                camera_location, camera_id, camera_lat, camera_lng,
            ),
        )

    def suspicious_behavior(
        self,
        name: str,
        reasons: list,
        camera_location: str,
        camera_id: str,
        track_id: int,
        now: float,
        camera_lat: Optional[float] = None,
        camera_lng: Optional[float] = None,
    ) -> None:
        key = f"suspicious_{camera_id}_{track_id}"
        if not self._should_fire(key, now):
            return

        dispatch_alert(
            alert_type="SUSPICIOUS_BEHAVIOR",
            severity="high",
            camera_location=camera_location,
            camera_id=camera_id,
            track_id=track_id,
            person_name=name,
            camera_lat=camera_lat,
            camera_lng=camera_lng,
            message=f"Suspicious: {', '.join(reasons)} at {camera_location}",
        )

    def watchlisted_vehicle(
        self,
        plate_number: str,
        vehicle_type: str,
        camera_location: str,
        camera_id: str,
        now: float,
        camera_lat: Optional[float] = None,
        camera_lng: Optional[float] = None,
    ) -> None:
        key = f"plate_{camera_id}_{plate_number}"
        if not self._should_fire(key, now):
            return

        dispatch_alert(
            alert_type="SUSPICIOUS_VEHICLE",
            severity="high",
            camera_location=camera_location,
            camera_id=camera_id,
            plate_number=plate_number,
            camera_lat=camera_lat,
            camera_lng=camera_lng,
            message=f"Watchlisted plate {plate_number} ({vehicle_type}) at {camera_location}",
        )

    def anomaly_detected(
        self,
        anomaly_message: str,
        camera_location: str,
        camera_id: str,
        now: float,
        camera_lat: Optional[float] = None,
        camera_lng: Optional[float] = None,
        zone: Optional[str] = None,
        track_id: Optional[int] = None,
        anomaly_type: str = "ANOMALY_DETECTED",
    ) -> None:
        key = f"anomaly_{camera_id}_{anomaly_type}_{zone}_{track_id}"
        if not self._should_fire(key, now):
            return

        dispatch_alert(
            alert_type=anomaly_type,
            severity="high" if anomaly_type == "INTRUSION" else "medium",
            zone=zone,
            track_id=track_id,
            camera_location=camera_location,
            camera_id=camera_id,
            camera_lat=camera_lat,
            camera_lng=camera_lng,
            message=anomaly_message,
        )

