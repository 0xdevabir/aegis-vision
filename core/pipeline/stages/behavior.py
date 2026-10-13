"""
Behavior Analysis Stage
=======================
Runs pose-based behavior analysis, anomaly detection, and ANPR.
"""

import logging
from collections import defaultdict
from core.pipeline.base import PipelineStage, FrameContext
from core.analysis.behavior import is_suspicious_behavior
from core.analysis.fall import FallDetector
from core.analysis.pose import assign_poses

logger = logging.getLogger("HumanAnalysis")


class BehaviorStage(PipelineStage):
    """Analyzes tracked persons for suspicious behavior and anomalies."""

    def __init__(self, pose_analyzer=None, anomaly_detector=None,
                 anpr=None, plate_db=None, fall_detector=None,
                 pose_every_n: int = 2, enabled: bool = True):
        super().__init__(name="behavior", enabled=enabled)
        self.pose_analyzer = pose_analyzer
        self.anomaly_detector = anomaly_detector
        self.anpr = anpr
        self.plate_db = plate_db
        self.fall_detector = fall_detector if fall_detector is not None else FallDetector()
        self.pose_every_n = max(1, pose_every_n)   # pose is the costliest per-frame step
        self._frames = 0
        self._last_poses = {}

        # Per-track trajectory history
        self._track_history = defaultdict(list)

    def process(self, ctx: FrameContext) -> FrameContext:
        fh, fw = ctx.frame.shape[:2]
        now = ctx.timestamp

        # Drop history for tracks that are gone (prevents unbounded growth)
        live = {t.track_id for t in ctx.tracks}
        for tid in [k for k in self._track_history if k not in live]:
            del self._track_history[tid]

        # One pose pass per frame (every Nth), matched to tracks by box overlap
        self._frames += 1
        if self.pose_analyzer is not None and getattr(self.pose_analyzer, "enabled", True):
            if self._frames % self.pose_every_n == 1 or self.pose_every_n == 1:
                try:
                    self._last_poses = assign_poses(
                        self.pose_analyzer.detect(ctx.frame), ctx.tracks)
                except Exception as e:
                    logger.warning(f"Pose error: {e}")
                    self._last_poses = {}
        poses = {k: v for k, v in self._last_poses.items() if k in live}
        self.fall_detector.prune(live)

        # --- Per-person behavior analysis ---
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

            # Update trajectory history (keep last 30 seconds)
            cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
            self._track_history[track_id].append((now, cx, cy))
            self._track_history[track_id] = [
                p for p in self._track_history[track_id] if now - p[0] <= 30
            ]

            pose = poses.get(track_id)
            pose_landmarks = pose["kpts"] if pose else None
            if pose and self.fall_detector.update(track_id, pose["kpts"], (x1, y1, x2, y2), now):
                ctx.fall_tracks[track_id] = {"bbox": (x1, y1, x2, y2)}

            # Behavior classification
            is_suspicious, reasons = is_suspicious_behavior(
                self._track_history[track_id], pose_landmarks
            )

            if is_suspicious:
                ctx.suspicious_tracks[track_id] = reasons

        # --- Anomaly detection (zone-based) ---
        if self.anomaly_detector is not None:
            try:
                ctx.anomalies = self.anomaly_detector.update(
                    ctx.tracks, ctx.frame.shape
                )
            except Exception as e:
                logger.warning(f"Anomaly detection error: {e}")

        # --- ANPR on vehicle detections ---
        if self.anpr is not None:
            for v in ctx.vehicle_detections:
                vx1, vy1, vx2, vy2 = v["bbox"]
                vehicle_roi = ctx.frame[vy1:vy2, vx1:vx2]
                if vehicle_roi.size == 0:
                    continue
                try:
                    plates = self.anpr.detect_plates(vehicle_roi)
                    for plate in plates:
                        # Adjust plate coordinates to frame space
                        px1, py1, px2, py2 = plate["bbox"]
                        plate["bbox"] = (px1 + vx1, py1 + vy1, px2 + vx1, py2 + vy1)
                        plate["vehicle_bbox"] = v["bbox"]
                        ctx.plate_detections.append(plate)

                        # Check watchlist
                        if self.plate_db and self.plate_db.is_watchlisted(plate["plate_number"]):
                            ctx.watchlisted_plates.append(plate)
                            logger.warning(f"WATCHLISTED PLATE: {plate['plate_number']}")
                except Exception as e:
                    logger.warning(f"ANPR error: {e}")

        return ctx

