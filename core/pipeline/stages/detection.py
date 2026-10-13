"""
Detection Stage
===============
Runs human, vehicle, and weapon detection on each frame.
"""

import logging
from core.pipeline.base import PipelineStage, FrameContext

logger = logging.getLogger("HumanAnalysis")


class DetectionStage(PipelineStage):
    """Runs YOLO-based detection for humans, vehicles, and weapons."""

    def __init__(self, human_detector, vehicle_detector=None,
                 weapon_detector=None, fire_detector=None, enabled: bool = True):
        super().__init__(name="detection", enabled=enabled)
        self.human_detector = human_detector
        self.vehicle_detector = vehicle_detector
        self.weapon_detector = weapon_detector
        self.fire_detector = fire_detector

    def process(self, ctx: FrameContext) -> FrameContext:
        # Human detection (always enabled)
        ctx.human_detections = self.human_detector.detect(ctx.frame)

        # Vehicle detection
        if self.vehicle_detector is not None:
            try:
                ctx.vehicle_detections = self.vehicle_detector.detect(ctx.frame)
            except Exception as e:
                logger.warning(f"Vehicle detection error: {e}")

        # Weapon detection
        if self.weapon_detector is not None:
            try:
                ctx.weapon_detections = self.weapon_detector.detect(ctx.frame)
                ctx.weapon_present = len(ctx.weapon_detections) > 0
            except Exception as e:
                logger.warning(f"Weapon detection error: {e}")

        if self.fire_detector is not None:
            try:
                ctx.fire_detections = self.fire_detector.detect(ctx.frame)
            except Exception as e:
                logger.warning(f"Fire/smoke detection error: {e}")

        return ctx
