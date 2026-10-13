from types import SimpleNamespace as NS
from unittest.mock import MagicMock

import pytest

from core.analysis.anomaly_detector import AnomalyDetector
from core.analysis.zones import validate_geometry
from core.runtime.runtime_config import apply_geometry

SQUARE = [[0.1, 0.1], [0.5, 0.1], [0.5, 0.5], [0.1, 0.5]]


def zone(**kw):
    return {"name": "door", "type": "restricted", "polygon": SQUARE, **kw}


def test_valid_geometry_is_cleaned():
    out = validate_geometry([zone()], [{"name": "gate", "p1": [0, 0], "p2": [1, 1]}])
    assert out["zones"][0]["polygon"][0] == [0.1, 0.1]
    assert out["lines"][0]["name"] == "gate"


@pytest.mark.parametrize("bad,msg", [
    ([zone(name="")], "name"),
    ([zone(), zone()], "Duplicate"),
    ([zone(type="danger")], "type"),
    ([zone(polygon=SQUARE[:2])], "3-"),
    ([zone(polygon=[[0.1, 0.1], [0.5, 0.5], [0.9, 0.9]])], "straight line"),
    ([zone(polygon=[[0.1, 0.1], [1.5, 0.1], [0.5, 0.5]])], "between 0 and 1"),
    ([zone(polygon=[[0.1, 0.1], ["x", 0.1], [0.5, 0.5]])], "numbers"),
])
def test_invalid_zones_rejected(bad, msg):
    with pytest.raises(ValueError, match=msg):
        validate_geometry(bad, [])


def test_line_and_name_clash_rules():
    with pytest.raises(ValueError, match="same point"):
        validate_geometry([], [{"name": "l", "p1": [0.2, 0.2], "p2": [0.2, 0.2]}])
    with pytest.raises(ValueError, match="Duplicate"):
        validate_geometry([zone(name="x")], [{"name": "X", "p1": [0, 0], "p2": [1, 1]}])
    with pytest.raises(ValueError, match="At most"):
        validate_geometry([zone(name=f"z{i}") for i in range(21)], [])


def _track(tid, cx, foot_y):
    t = MagicMock()
    t.track_id = tid
    t.is_confirmed.return_value = True
    t.to_ltrb.return_value = (cx - 20, foot_y - 80, cx + 20, foot_y)
    return t


def test_set_geometry_resets_state_and_applies_new_zone():
    d = AnomalyDetector(dwell_seconds=10)
    t = _track(1, 100, 100)
    d.update([t], (480, 640, 3), now=0)
    d.update([t], (480, 640, 3), now=11)           # dwell fired in a quadrant
    d.set_geometry([zone()], [])                   # now a restricted zone around (200, 150)
    inside = _track(1, 160, 150)                   # foot at (0.25, 0.31)
    ev = d.update([inside], (480, 640, 3), now=12)
    assert [a["type"] for a in ev] == ["intrusion"]


def test_apply_geometry_only_on_change_and_ignores_unconfigured():
    det = AnomalyDetector()
    pipe = NS(stages=[NS(name="behavior", anomaly_detector=det)])
    assert apply_geometry(pipe, None) is False     # never configured → keep defaults
    g = {"zones": [zone()], "lines": []}
    assert apply_geometry(pipe, g) is True
    assert [z.name for z in det.zones] == ["door"]
    assert apply_geometry(pipe, g) is False        # unchanged → no state reset
