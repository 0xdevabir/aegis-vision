"""
Tracking Stage
==============
Runs DeepSORT tracking on detections to assign persistent track IDs.
"""

import logging
from core.pipeline.base import PipelineStage, FrameContext

logger = logging.getLogger("HumanAnalysis")


class TrackingStage(PipelineStage):
    """Updates DeepSORT trackers with current frame detections."""

    def __init__(self, human_tracker, vehicle_tracker=None, enabled: bool = True):
        super().__init__(name="tracking", enabled=enabled)
        self.human_tracker = human_tracker
        self.vehicle_tracker = vehicle_tracker

    def process(self, ctx: FrameContext) -> FrameContext:
        # Track humans
        ctx.tracks = self.human_tracker.track(ctx.human_detections, ctx.frame)

        # Track vehicles
        if self.vehicle_tracker is not None and ctx.vehicle_detections:
            try:
                ctx.vehicle_tracks = self.vehicle_tracker.track(
                    ctx.vehicle_detections, ctx.frame
                )
            except Exception as e:
                logger.warning(f"Vehicle tracking error: {e}")

        return ctx
