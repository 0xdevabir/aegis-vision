"""ANPR: plate normalisation, plausibility filter, per-vehicle voting, stage wiring."""
from types import SimpleNamespace

import numpy as np

from core.analysis.anpr import (
    LicensePlateDatabase, LicensePlateRecognizer, PlateVoter, normalize_plate, plausible_plate,
)
from core.pipeline.base import FrameContext
from core.pipeline.stages.behavior import BehaviorStage


def test_normalize_strips_noise_and_maps_bengali_digits():
    assert normalize_plate(" dha-ka 12.3456 ") == "DHAKA123456"
    assert normalize_plate("ঢাকা মেট্রো-গ ১২-৩৪৫৬") == normalize_plate("ঢাকামেট্রোগ123456")
    assert normalize_plate(None) == ""


def test_plausible_plate_rejects_signage():
    assert plausible_plate("ABC1234")
    assert not plausible_plate("TOYOTA")            # no digit
    assert not plausible_plate("A1")                # too short
    assert not plausible_plate("A" * 12 + "1")      # too long


def test_recognizer_filters_low_confidence_and_implausible_reads():
    r = LicensePlateRecognizer()
    box = [(0, 0), (10, 0), (10, 5), (0, 5)]
    r._reader = SimpleNamespace(readtext=lambda roi: [
        (box, "abc-1234", 0.9), (box, "TOYOTA", 0.95), (box, "XYZ9999", 0.1)])
    assert [p["plate_number"] for p in r.detect_plates(None)] == ["ABC1234"]


def test_voter_needs_agreement_and_prunes():
    v = PlateVoter(window=5, min_votes=2)
    v.add("t1", "ABC1234")
    assert v.confirmed("t1") is None                # one read is not enough
    v.add("t1", "A8C1234")                          # OCR slip
    v.add("t1", None)                               # nothing read
    assert v.confirmed("t1") is None
    v.add("t1", "ABC1234")
    assert v.confirmed("t1") == "ABC1234"
    v.prune(set())
    assert v.confirmed("t1") is None


def test_watchlist_matches_regardless_of_formatting():
    db = LicensePlateDatabase(loader=lambda: {"abc 1234"})
    assert db.is_watchlisted("ABC-1234")
    assert not db.is_watchlisted("ABC1235")


class _FakeAnpr:
    def __init__(self, reads):
        self.reads, self.calls = list(reads), 0

    def detect_plates(self, roi):
        self.calls += 1
        text = self.reads.pop(0) if self.reads else None
        return [{"bbox": (10, 20, 60, 40), "plate_number": text, "confidence": 0.8}] if text else []


def _ctx(bbox=(100, 100, 300, 200), tid="7"):
    ctx = FrameContext(frame=np.zeros((480, 640, 3), dtype=np.uint8))
    ctx.vehicle_detections = [{"bbox": bbox, "score": 0.9, "class_id": 2, "class_name": "car"}]
    ctx.vehicle_tracks = [SimpleNamespace(track_id=tid, is_confirmed=lambda: True, to_ltrb=lambda: bbox)]
    return ctx


def _stage(anpr, watch=()):
    return BehaviorStage(anpr=anpr, plate_db=LicensePlateDatabase(loader=lambda: set(watch)), anpr_every_n=1)


def test_stage_publishes_plate_only_after_two_matching_reads_then_stops_ocr():
    anpr = _FakeAnpr(["ABC1234", "ABC1234"])
    stage = _stage(anpr, watch={"ABC1234"})
    first = stage.process(_ctx())
    assert first.plate_detections == [] and first.watchlisted_plates == []
    second = stage.process(_ctx())
    assert [p["plate_number"] for p in second.plate_detections] == ["ABC1234"]
    assert second.plate_detections[0]["bbox"] == (110, 120, 160, 140)
    assert len(second.watchlisted_plates) == 1
    moved = stage.process(_ctx(bbox=(200, 100, 400, 200)))                 # confirmed: no more OCR
    assert anpr.calls == 2
    assert moved.plate_detections[0]["bbox"] == (210, 120, 260, 140)       # box follows the vehicle


def test_stage_ignores_untracked_vehicles_and_forgets_departed_tracks():
    anpr = _FakeAnpr(["ABC1234"] * 4)
    stage = _stage(anpr)
    ctx = _ctx()
    ctx.vehicle_tracks = []
    assert stage.process(ctx).plate_detections == [] and anpr.calls == 0
    stage.process(_ctx())
    stage.process(_ctx())
    assert "7" in stage._plates
    stage.process(ctx)
    assert stage._plates == {}
