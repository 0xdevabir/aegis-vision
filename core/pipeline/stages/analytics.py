"""
Analytics Stage
===============
Updates heatmap, dwell time, and traffic flow analytics.
Previously existed as Analytics class but was NEVER integrated.
"""

import logging
from core.pipeline.base import PipelineStage, FrameContext
from core.analysis.analytics import Analytics

logger = logging.getLogger("HumanAnalysis")


class AnalyticsStage(PipelineStage):
    """Updates spatial analytics: heatmap, dwell time, traffic flow."""

    def __init__(self, enabled: bool = True):
        super().__init__(name="analytics", enabled=enabled)
        self.analytics = Analytics()

    def process(self, ctx: FrameContext) -> FrameContext:
        # Update heatmap with current track positions
        self.analytics.update_heatmap(ctx.tracks, ctx.frame.shape)

        # Record movement paths for each confirmed track
        for track in ctx.tracks:
            if not track.is_confirmed():
                continue
            x1, y1, x2, y2 = map(int, track.to_ltrb())
            cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
            self.analytics.record_movement(track.track_id, cx, cy)

        # Make analytics data available to downstream stages
        ctx.heatmap = self.analytics.get_heatmap_normalized()
        ctx.dwell_stats = self.analytics.get_dwell_stats()
        for anomaly in ctx.anomalies or []:
            if anomaly.get("type") == "dwell":
                self.analytics.record_dwell(
                    anomaly.get("track_id", 0),
                    anomaly.get("zone", "unknown"),
                    float(anomaly.get("duration_seconds", 0)),
                )

        ctx.traffic_flow = self.analytics.get_traffic_flow()
        ctx.dwell_stats = self.analytics.get_dwell_stats()

        return ctx

    def get_analytics(self) -> Analytics:
        """Direct access to the Analytics instance for API queries."""
        return self.analytics

