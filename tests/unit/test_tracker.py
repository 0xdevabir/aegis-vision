import numpy as np

from core.tracking.tracker import HumanTracker, hist_embed


def _frame():
    f = np.zeros((720, 1280, 3), np.uint8)
    f[100:400, 300:420] = (30, 160, 220)        # a coloured "person"
    return f


def test_track_box_matches_detection_box():
    """Regression: corner boxes were fed to DeepSORT as (l, t, w, h), inflating every track."""
    t = HumanTracker()
    tracks = []
    for _ in range(3):
        tracks = t.track([([300, 100, 420, 400], 0.9, 0)], _frame())
    box = [round(v) for v in tracks[0].to_ltrb()]
    assert all(abs(a - b) <= 6 for a, b in zip(box, [300, 100, 420, 400])), box


def test_hist_embed_is_normalised_and_distinguishes_colours():
    f = _frame()
    a = hist_embed(f, 300, 100, 420, 400)
    b = hist_embed(f, 800, 100, 920, 400)        # empty background
    assert abs(np.linalg.norm(a) - 1) < 1e-4
    assert float(a @ b) < 0.9
    assert hist_embed(f, 5000, 5000, 5100, 5100).shape == (128,)   # off-frame box is safe


def test_track_ids_persist_for_a_moving_person():
    t = HumanTracker()
    ids = set()
    for i in range(6):
        f = np.zeros((720, 1280, 3), np.uint8)
        f[100:400, 300 + 8 * i:420 + 8 * i] = (30, 160, 220)
        for tr in t.track([([300 + 8 * i, 100, 420 + 8 * i, 400], 0.9, 0)], f):
            if tr.is_confirmed():
                ids.add(tr.track_id)
    assert len(ids) == 1


def _walk(tracker, boxes_per_frame):
    """Feed frames of [(x1, y1, x2, y2, conf)] and return the ids seen per frame."""
    seen = []
    for boxes in boxes_per_frame:
        dets = [([x1, y1, x2, y2], c, 0) for x1, y1, x2, y2, c in boxes]
        seen.append([t.track_id for t in tracker.track(dets, _frame()) if t.is_confirmed()])
    return seen


def test_bytetrack_exposes_the_deepsort_track_surface():
    t = HumanTracker(algorithm="bytetrack")
    tracks = []
    for _ in range(3):
        tracks = t.track([([300, 100, 420, 400], 0.9, 0)], _frame())
    assert len(tracks) == 1 and tracks[0].is_confirmed() and isinstance(tracks[0].track_id, str)
    box = [round(v) for v in tracks[0].to_ltrb()]
    assert all(abs(a - b) <= 6 for a, b in zip(box, [300, 100, 420, 400])), box


def test_bytetrack_keeps_id_through_a_low_confidence_dip():
    """ByteTrack's point: a half-hidden person scores low but still matches their own track."""
    t = HumanTracker(algorithm="bytetrack")
    frames = [[(300 + 6 * i, 100, 420 + 6 * i, 400, 0.9 if i not in (4, 5) else 0.3)] for i in range(10)]
    ids = {i for frame in _walk(t, frames) for i in frame}
    assert len(ids) == 1


def test_bytetrack_ids_survive_a_second_tracker_being_created():
    """One tracker per camera: creating camera 2's tracker must not recycle camera 1's ids."""
    a = HumanTracker(algorithm="bytetrack")
    first = _walk(a, [[(100, 100, 200, 400, 0.9)]] * 3)[-1]
    HumanTracker(algorithm="bytetrack")
    both = _walk(a, [[(100, 100, 200, 400, 0.9), (800, 100, 900, 400, 0.9)]] * 3)[-1]
    assert first[0] in both and len(set(both)) == 2


def test_bytetrack_handles_empty_frames_and_vehicles():
    from core.detectors.vehicle_detector import VehicleTracker
    assert HumanTracker(algorithm="bytetrack").track([], _frame()) == []
    v = VehicleTracker(algorithm="bytetrack")
    out = []
    for _ in range(3):
        out = v.track([{"bbox": (100, 100, 400, 300), "score": 0.8, "class_id": 2}], _frame())
    assert len(out) == 1 and out[0].det_class == 2


def test_unknown_algorithm_is_rejected():
    import pytest
    with pytest.raises(ValueError):
        HumanTracker(algorithm="sort")
