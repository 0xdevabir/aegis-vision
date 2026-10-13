"""Heatmap must survive a resolution change instead of crashing the camera worker."""
from types import SimpleNamespace

from core.analysis.analytics import Analytics


def _track(x, y):
    return SimpleNamespace(is_confirmed=lambda: True, to_ltrb=lambda: (x - 5, y - 5, x + 5, y + 5))


def test_heatmap_resizes_when_frame_size_changes():
    a = Analytics()
    a.update_heatmap([_track(100, 100)], (480, 640, 3))
    assert a.heatmap.shape == (480, 640)
    a.update_heatmap([_track(1000, 695)], (720, 1280, 3))      # used to raise IndexError
    assert a.heatmap.shape == (720, 1280)
    assert a.heatmap[695, 1000] == 1.0


def test_heatmap_accumulates_at_stable_size():
    a = Analytics()
    for _ in range(3):
        a.update_heatmap([_track(50, 60)], (480, 640, 3))
    assert a.heatmap[60, 50] == 3.0
