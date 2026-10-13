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
