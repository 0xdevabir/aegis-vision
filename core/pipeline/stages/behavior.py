"""
Behavior Analysis Stage
=======================
Runs pose-based behavior analysis, anomaly detection, and ANPR.
"""

import logging
from collections import defaultdict
from core.pipeline.base import PipelineStage, FrameContext
from core.analysis.behavior import is_suspicious_behavior
from core.analysis.anpr import PlateVoter
from core.analysis.fall import FallDetector
from core.analysis.pose import assign_poses
from core.analysis.weapon_confirm import overlap_ratio

logger = logging.getLogger("HumanAnalysis")


class BehaviorStage(PipelineStage):
    """Analyzes tracked persons for suspicious behavior and anomalies."""

    def __init__(self, pose_analyzer=None, anomaly_detector=None,
                 anpr=None, plate_db=None, fall_detector=None, action_recognizer=None,
                 pose_every_n: int = 2, anpr_every_n: int = 3, enabled: bool = True):
        super().__init__(name="behavior", enabled=enabled)
        self.pose_analyzer = pose_analyzer
        self.anomaly_detector = anomaly_detector
        self.anpr = anpr
        self.plate_db = plate_db
        self.fall_detector = fall_detector if fall_detector is not None else FallDetector()
        self.action_recognizer = action_recognizer
        self._actions = {}                   # track id → (reason, NTU label, probability)
        self.pose_every_n = max(1, pose_every_n)   # pose is the costliest per-frame step
        self._frames = 0
        self._last_poses = {}
        self.anpr_every_n = max(1, anpr_every_n)
        self.plate_voter = PlateVoter()
        self._plates = {}                    # vehicle track id → confirmed plate
        self._plates_logged = set()

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
                if self.action_recognizer is not None:     # fed once per fresh pose pass
                    self._actions = self.action_recognizer.update(now, ctx.frame.shape, self._last_poses)
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
            self._track_history[track_id].append((now, cx, cy, y2 - y1))
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

            # Learned actions (ST-GCN): a fall joins the rule-based fall alert, the rest are reasons
            action = self._actions.get(track_id)
            if action and action[0] == "falling":
                ctx.fall_tracks[track_id] = {"bbox": (x1, y1, x2, y2)}
            elif action and action[0] not in reasons:
                reasons.append(action[0])
                is_suspicious = True

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

        if self.anpr is not None:
            self._run_anpr(ctx)

        return ctx


    def _run_anpr(self, ctx: FrameContext) -> None:
        """Read plates per vehicle track and publish them only once confirmed by voting.

        OCR is the slowest step in the pipeline, so a vehicle is read every
        `anpr_every_n` frames and not at all once its plate is confirmed.
        """
        boxes = {t.track_id: tuple(map(int, t.to_ltrb()))
                 for t in ctx.vehicle_tracks if t.is_confirmed()}
        self.plate_voter.prune(boxes)
        for tid in [k for k in self._plates if k not in boxes]:
            del self._plates[tid]

        for v in ctx.vehicle_detections:
            vx1, vy1, vx2, vy2 = v["bbox"]
            tid = max(boxes, key=lambda k: overlap_ratio(v["bbox"], boxes[k]), default=None)
            if tid is None or overlap_ratio(v["bbox"], boxes[tid]) < 0.5:
                continue                     # no stable track yet: nothing to vote on
            if tid not in self._plates and self._frames % self.anpr_every_n == 0:
                vehicle_roi = ctx.frame[vy1:vy2, vx1:vx2]
                if vehicle_roi.size == 0:
                    continue
                try:
                    reads = self.anpr.detect_plates(vehicle_roi)
                except Exception as e:
                    logger.warning(f"ANPR error: {e}")
                    continue
                best = max(reads, key=lambda r: r["confidence"], default=None)
                self.plate_voter.add(tid, best["plate_number"] if best else None)
                number = self.plate_voter.confirmed(tid)
                if number and best and best["plate_number"] == number:
                    w, h = max(1, vx2 - vx1), max(1, vy2 - vy1)
                    px1, py1, px2, py2 = best["bbox"]
                    self._plates[tid] = {
                        "plate_number": number, "confidence": best["confidence"],
                        "rel": (px1 / w, py1 / h, px2 / w, py2 / h),   # follows the vehicle as it moves
                    }
            plate = self._plates.get(tid)
            if plate is None:
                continue
            w, h = vx2 - vx1, vy2 - vy1
            r = plate["rel"]
            out = {
                "plate_number": plate["plate_number"], "confidence": plate["confidence"],
                "bbox": (int(vx1 + r[0] * w), int(vy1 + r[1] * h), int(vx1 + r[2] * w), int(vy1 + r[3] * h)),
                "vehicle_bbox": v["bbox"], "track_id": tid,
            }
            ctx.plate_detections.append(out)
            if self.plate_db and self.plate_db.is_watchlisted(out["plate_number"]):
                ctx.watchlisted_plates.append(out)
                if tid not in self._plates_logged:
                    self._plates_logged.add(tid)
                    logger.warning(f"WATCHLISTED PLATE: {out['plate_number']}")
        self._plates_logged &= set(boxes)
