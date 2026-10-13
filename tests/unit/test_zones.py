from unittest.mock import MagicMock

from core.analysis.anomaly_detector import AnomalyDetector
from core.analysis.zones import crossed, point_in_polygon

SHAPE = (480, 640, 3)


def track(tid, cx, foot_y):
    t = MagicMock()
    t.track_id = tid
    t.is_confirmed.return_value = True
    t.to_ltrb.return_value = (cx - 20, foot_y - 80, cx + 20, foot_y)
    return t


def test_point_in_polygon():
    sq = [(0.2, 0.2), (0.6, 0.2), (0.6, 0.6), (0.2, 0.6)]
    assert point_in_polygon(0.4, 0.4, sq)
    assert not point_in_polygon(0.8, 0.4, sq)


def test_line_cross_direction_and_segment_bounds():
    a, b = (0.5, 0.0), (0.5, 1.0)
    assert crossed((0.4, 0.5), (0.6, 0.5), a, b) == -crossed((0.6, 0.5), (0.4, 0.5), a, b) != 0
    assert crossed((0.4, 0.5), (0.45, 0.5), a, b) == 0
    assert crossed((0.4, 1.5), (0.6, 1.5), a, b) == 0     # beyond the finite segment


def test_restricted_zone_intrusion_reported_once_per_entry():
    zones = [{"name": "door", "type": "restricted",
              "polygon": [[0.1, 0.1], [0.5, 0.1], [0.5, 0.9], [0.1, 0.9]]}]
    d = AnomalyDetector(zones=zones)
    inside = track(1, 200, 300)
    first = d.update([inside], SHAPE, now=0)
    assert [a["type"] for a in first] == ["intrusion"]
    assert d.update([inside], SHAPE, now=1) == []
    d.update([], SHAPE, now=2)                           # leaves → state reset
    assert [a["type"] for a in d.update([inside], SHAPE, now=3)] == ["intrusion"]


def test_dwell_fires_once_and_resets_after_leaving():
    d = AnomalyDetector(dwell_seconds=10)
    t = track(1, 100, 100)
    assert d.update([t], SHAPE, now=0) == []
    assert [a["type"] for a in d.update([t], SHAPE, now=11)] == ["dwell"]
    assert d.update([t], SHAPE, now=12) == []             # no per-frame repeats
    d.update([], SHAPE, now=13)
    assert d.update([t], SHAPE, now=14) == []             # timer restarted


def test_line_crossing_event():
    d = AnomalyDetector(lines=[{"name": "gate", "p1": [0.5, 0], "p2": [0.5, 1]}])
    d.update([track(1, 280, 200)], SHAPE, now=0)
    ev = d.update([track(1, 360, 200)], SHAPE, now=1)
    assert [a["type"] for a in ev] == ["line_cross"]
