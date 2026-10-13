"""
Unit Tests — Pipeline Framework
================================
Tests for the pipeline base classes: FrameContext, PipelineStage, SurveillancePipeline.
These tests require NO external dependencies (no DB, no models).
"""

import numpy as np
from core.pipeline.base import FrameContext, PipelineStage, SurveillancePipeline


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class DummyStage(PipelineStage):
    """A no-op stage for testing."""

    def __init__(self, name="dummy", enabled=True, side_effect=None):
        super().__init__(name=name, enabled=enabled)
        self.side_effect = side_effect
        self.call_count = 0

    def process(self, ctx: FrameContext) -> FrameContext:
        self.call_count += 1
        if self.side_effect:
            self.side_effect(ctx)
        return ctx


def _make_frame(h=480, w=640):
    """Create a dummy BGR frame."""
    return np.zeros((h, w, 3), dtype=np.uint8)


# ---------------------------------------------------------------------------
# Tests: FrameContext
# ---------------------------------------------------------------------------

class TestFrameContext:
    def test_default_values(self):
        frame = _make_frame()
        ctx = FrameContext(frame=frame)
        assert ctx.frame_number == 0
        assert ctx.human_detections == []
        assert ctx.weapon_present is False
        assert ctx.threat_score == 0
        assert ctx.criminal_ids == set()

    def test_stores_frame(self):
        frame = _make_frame(100, 200)
        ctx = FrameContext(frame=frame)
        assert ctx.frame.shape == (100, 200, 3)

    def test_mutable_fields(self):
        ctx = FrameContext(frame=_make_frame())
        ctx.identities[1] = "John"
        ctx.criminal_ids.add(1)
        assert ctx.identities[1] == "John"
        assert 1 in ctx.criminal_ids


# ---------------------------------------------------------------------------
# Tests: PipelineStage
# ---------------------------------------------------------------------------

class TestPipelineStage:
    def test_enabled_stage_runs(self):
        stage = DummyStage(name="test", enabled=True)
        ctx = FrameContext(frame=_make_frame())
        result = stage(ctx)
        assert stage.call_count == 1
        assert result is ctx

    def test_disabled_stage_skipped(self):
        stage = DummyStage(name="test", enabled=False)
        ctx = FrameContext(frame=_make_frame())
        result = stage(ctx)
        assert stage.call_count == 0
        assert result is ctx

    def test_timing_stats(self):
        stage = DummyStage(name="timed")
        ctx = FrameContext(frame=_make_frame())
        stage(ctx)
        stage(ctx)
        stats = stage.get_stats()
        assert stats["name"] == "timed"
        assert stats["calls"] == 2
        assert stats["avg_ms"] >= 0
        assert stats["total_ms"] >= 0


# ---------------------------------------------------------------------------
# Tests: SurveillancePipeline
# ---------------------------------------------------------------------------

class TestSurveillancePipeline:
    def test_empty_pipeline(self):
        pipeline = SurveillancePipeline()
        frame = _make_frame()
        ctx = pipeline.run(frame, camera_id="test")
        assert ctx.camera_id == "test"
        assert ctx.frame_number == 1
        assert ctx.timestamp > 0

    def test_stages_execute_in_order(self):
        order = []

        def mark(n):
            def fn(ctx):
                order.append(n)
            return fn

        pipeline = SurveillancePipeline()
        pipeline.add_stage(DummyStage("first", side_effect=mark(1)))
        pipeline.add_stage(DummyStage("second", side_effect=mark(2)))
        pipeline.add_stage(DummyStage("third", side_effect=mark(3)))

        pipeline.run(_make_frame())
        assert order == [1, 2, 3]

    def test_disabled_stages_skipped_in_pipeline(self):
        order = []

        def mark(n):
            def fn(ctx):
                order.append(n)
            return fn

        pipeline = SurveillancePipeline()
        pipeline.add_stage(DummyStage("first", side_effect=mark(1)))
        pipeline.add_stage(DummyStage("disabled", enabled=False, side_effect=mark(2)))
        pipeline.add_stage(DummyStage("third", side_effect=mark(3)))

        pipeline.run(_make_frame())
        assert order == [1, 3]

    def test_frame_count_increments(self):
        pipeline = SurveillancePipeline()
        pipeline.add_stage(DummyStage("test"))

        ctx1 = pipeline.run(_make_frame())
        ctx2 = pipeline.run(_make_frame())
        assert ctx1.frame_number == 1
        assert ctx2.frame_number == 2

    def test_get_stats(self):
        pipeline = SurveillancePipeline()
        pipeline.add_stage(DummyStage("a"))
        pipeline.add_stage(DummyStage("b"))
        pipeline.run(_make_frame())

        stats = pipeline.get_stats()
        assert stats["frame_count"] == 1
        assert len(stats["stages"]) == 2
        assert stats["stages"][0]["name"] == "a"
        assert stats["stages"][1]["name"] == "b"

    def test_camera_info_passed(self):
        pipeline = SurveillancePipeline()
        ctx = pipeline.run(_make_frame(), camera_id="cam_01", camera_location="Gate_1")
        assert ctx.camera_id == "cam_01"
        assert ctx.camera_location == "Gate_1"
