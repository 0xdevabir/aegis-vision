"""
Output Stage — evidence saving and automated multi-channel alert dispatch.
"""

import logging
import threading

from core.pipeline.base import PipelineStage, FrameContext
from utils.data import save_evidence_db
from utils.alerts import NotificationHub
from core.analysis.weapon_confirm import UNASSIGNED, WeaponConfirmer, associate

logger = logging.getLogger("HumanAnalysis")


class OutputStage(PipelineStage):
    """Saves evidence and auto-dispatches alerts to all defense channels."""

    def __init__(self, camera_location: str = "",
                 evidence_throttle_seconds: float = 10.0,
                 alarm_interval_seconds: float = 5.0,
                 alarm_callback=None, enabled: bool = True):
        super().__init__(name="output", enabled=enabled)
        self.camera_location = camera_location
        self.evidence_throttle = evidence_throttle_seconds
        self.notifications = NotificationHub(
            alarm_callback=alarm_callback,
            alarm_interval=alarm_interval_seconds,
        )
        self._last_saved: dict = {}
        self.weapon_confirmer = WeaponConfirmer(window=5, min_hits=3)
        # Fire/smoke flickers more than weapons do: demand a longer persistence.
        self.fire_confirmer = WeaponConfirmer(window=8, min_hits=5)

    def process(self, ctx: FrameContext) -> FrameContext:
        now = ctx.timestamp
        location = ctx.camera_location or self.camera_location
        camera_id = ctx.camera_id
        fh, fw = ctx.frame.shape[:2]

        # Weapon evidence must be attached to a person track and persist over frames.
        assigned = associate(ctx.weapon_detections, ctx.tracks)
        confirmed_keys = self.weapon_confirmer.update(assigned)
        ctx.confirmed_weapons = {k: assigned[k] for k in confirmed_keys}

        best_fire = max(ctx.fire_detections, key=lambda d: d["score"], default=None)
        fire_keys = self.fire_confirmer.update({"fire": best_fire} if best_fire else {})
        if "fire" in fire_keys:
            ctx.confirmed_fire = {"fire": best_fire}
            self.notifications.fire_smoke_detected(
                camera_location=location, camera_id=camera_id, now=now,
                kind=best_fire.get("class_name", "fire"), confidence=best_fire["score"],
                camera_lat=ctx.camera_lat, camera_lng=ctx.camera_lng,
            )

        for tid in ctx.fall_tracks:
            self.notifications.fall_suspected(
                camera_location=location, camera_id=camera_id, track_id=tid, now=now,
                camera_lat=ctx.camera_lat, camera_lng=ctx.camera_lng,
            )

        if UNASSIGNED in ctx.confirmed_weapons:
            self.notifications.weapon_detected(
                camera_location=location, camera_id=camera_id,
                track_id=UNASSIGNED, now=now,
                camera_lat=ctx.camera_lat, camera_lng=ctx.camera_lng,
                confidence=ctx.confirmed_weapons[UNASSIGNED]["score"],
            )

        for track in ctx.tracks:
            if not track.is_confirmed():
                continue

            track_id = track.track_id
            x1, y1, x2, y2 = map(int, track.to_ltrb())
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(fw, x2), min(fh, y2)

            roi = ctx.frame[y1:y2, x1:x2]
            if roi.size == 0:
                continue

            name = ctx.identities.get(track_id, "Unknown")
            is_criminal = track_id in ctx.criminal_ids
            is_suspicious = track_id in ctx.suspicious_tracks
            reasons = ctx.suspicious_tracks.get(track_id, [])
            has_weapon = track_id in ctx.confirmed_weapons
            alert = is_criminal or has_weapon or is_suspicious

            if is_criminal:
                self.notifications.criminal_detected(
                    criminal_name=name,
                    camera_location=location,
                    camera_id=camera_id,
                    track_id=track_id,
                    now=now,
                    camera_name=ctx.camera_name,
                    camera_lat=ctx.camera_lat,
                    camera_lng=ctx.camera_lng,
                    confidence=ctx.identity_conf.get(track_id),
                )

            if has_weapon:
                self.notifications.weapon_detected(
                    camera_location=location,
                    camera_id=camera_id,
                    track_id=track_id,
                    now=now,
                    camera_lat=ctx.camera_lat,
                    camera_lng=ctx.camera_lng,
                    confidence=ctx.confirmed_weapons[track_id]["score"],
                )

            if is_suspicious:
                self.notifications.suspicious_behavior(
                    name=name,
                    reasons=reasons,
                    camera_location=location,
                    camera_id=camera_id,
                    track_id=track_id,
                    now=now,
                    camera_lat=ctx.camera_lat,
                    camera_lng=ctx.camera_lng,
                )

            if alert and (now - self._last_saved.get(track_id, 0) >= self.evidence_throttle):
                try:
                    threading.Thread(
                        target=save_evidence_db,
                        args=(
                            location, track_id, name,
                            is_criminal, has_weapon, is_suspicious,
                            reasons, ctx.frame.copy(), roi.copy(),
                        ),
                        daemon=True,
                    ).start()
                    self._last_saved[track_id] = now
                except Exception as e:
                    logger.warning(f"Evidence save failed: {e}")

        for plate in ctx.watchlisted_plates:
            vehicle_type = "unknown"
            for v in ctx.vehicle_detections:
                if v.get("bbox") == plate.get("vehicle_bbox"):
                    vehicle_type = v.get("class_name", "vehicle")
                    break
            self.notifications.watchlisted_vehicle(
                plate_number=plate["plate_number"],
                vehicle_type=vehicle_type,
                camera_location=location,
                camera_id=camera_id,
                now=now,
                camera_lat=ctx.camera_lat,
                camera_lng=ctx.camera_lng,
            )

        for anomaly in ctx.anomalies:
            if anomaly.get("type") == "line_cross":
                continue   # counting event: analytics only, not an alert
            self.notifications.anomaly_detected(
                anomaly_message=anomaly.get("message", "Anomaly detected"),
                camera_location=location,
                camera_id=camera_id,
                now=now,
                camera_lat=ctx.camera_lat,
                camera_lng=ctx.camera_lng,
                zone=anomaly.get("zone"),
                track_id=anomaly.get("track_id"),
                anomaly_type="INTRUSION" if anomaly.get("type") == "intrusion" else "ANOMALY_DETECTED",
            )

        ctx.threat_score = min(
            100,
            len(ctx.tracks) * 5
            + (50 if ctx.confirmed_weapons else 0)
            + len(ctx.active_criminals) * 50
            + len(ctx.anomalies) * 10,
        )

        return ctx
