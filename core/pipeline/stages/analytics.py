"""
Analytics Stage
===============
Updates the occupancy heatmap, zone dwell and line-crossing flow.
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
        self.analytics.update_heatmap(ctx.tracks, ctx.frame.shape)

        for anomaly in ctx.anomalies or []:
            kind = anomaly.get("type")
            if kind == "dwell":
                self.analytics.record_dwell(
                    anomaly.get("track_id", 0),
                    anomaly.get("zone", "unknown"),
                    float(anomaly.get("duration_seconds", 0)),
                )
            elif kind == "line_cross":
                self.analytics.record_crossing(anomaly.get("zone", "unknown"), anomaly.get("direction", 1))

        ctx.traffic_flow = self.analytics.get_traffic_flow()
        ctx.dwell_stats = self.analytics.get_dwell_stats()
        return ctx

    def get_analytics(self) -> Analytics:
        """Direct access to the Analytics instance for API queries."""
        return self.analytics
