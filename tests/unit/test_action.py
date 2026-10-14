from types import SimpleNamespace

import numpy as np
import pytest

from core.analysis.action import (
    ACTION_MODEL, ALERT_ACTIONS, CLIP_LEN, NTU60_LABELS, ActionRecognizer, _to_array,
)
from core.analysis.pose import KEYPOINT_NAMES
from core.pipeline.base import FrameContext
from core.pipeline.stages.behavior import BehaviorStage

FRAME = (480, 640, 3)


def person(cx, cy=240.0, h=200.0):
    """All 17 joints spread over a box of height h centred at (cx, cy)."""
    return {"kpts": {name: (cx + (i % 3 - 1) * 10, cy - h / 2 + i * h / 16, 0.9)
                     for i, name in enumerate(KEYPOINT_NAMES)}}


def test_labels_are_ntu60():
    assert len(NTU60_LABELS) == 60
    assert NTU60_LABELS[42] == "falling" and NTU60_LABELS[49].startswith("punching")


def test_missing_joints_sit_on_body_centre_with_zero_score():
    kpts = {n: (100.0, 200.0, 0.9) for n in KEYPOINT_NAMES[5:]}      # face joints dropped
    a = _to_array(kpts)
    assert a.shape == (17, 3)
    assert np.allclose(a[0], (100, 200, 0)) and a[5, 2] == pytest.approx(0.9)
    assert _to_array({"nose": (1, 1, 0.9)}) is None                  # too few joints


def _recognizer_with_history(poses_by_time):
    r = ActionRecognizer(model_path="/nonexistent.onnx")
    for t, poses in poses_by_time:
        r._history.append((t, {tid: _to_array(p["kpts"]) for tid, p in poses.items()}))
    return r


def test_clip_is_normalized_looped_and_pads_an_absent_partner():
    r = _recognizer_with_history([(t * 0.1, {1: person(320)}) for t in range(20)])   # 1.9 s alone
    clip = r._clip(1, FRAME)
    assert clip.shape == (1, 2, CLIP_LEN, 17, 3)
    assert np.abs(clip[0, 0, :, :, :2]).max() <= 1.0                  # PreNormalize2D range
    assert not clip[0, 1].any()                                       # no partner → zeros
    n = round(1.9 * 30)
    assert np.allclose(clip[0, 0, 0], clip[0, 0, n])                  # short clip loops (test mode)


def test_clip_includes_nearest_person_but_not_a_distant_one():
    near = _recognizer_with_history([(t * 0.1, {1: person(300), 2: person(360)}) for t in range(20)])
    assert near._clip(1, FRAME)[0, 1].any()
    far = _recognizer_with_history([(t * 0.1, {1: person(100, h=100), 2: person(600, h=100)})
                                    for t in range(20)])
    assert not far._clip(1, FRAME)[0, 1].any()


def test_fight_classes_raise_nothing():
    # Measured useless on real fight footage; see the comment on ALERT_ACTIONS.
    assert not {49, 50, 51} & set(ALERT_ACTIONS)


def test_too_short_history_is_not_classified():
    r = _recognizer_with_history([(t * 0.1, {1: person(320)}) for t in range(5)])
    assert r._clip(1, FRAME) is None


def test_people_who_leave_are_forgotten():
    r = ActionRecognizer(model_path="/nonexistent.onnx")
    r.net = object()                                                  # pretend enabled; no clip is due yet
    r._last_run = {1: 0.0, 2: 0.0}
    r._results = {2: ("fighting", NTU60_LABELS[49], 0.9)}
    assert r.update(0.5, FRAME, {1: person(320)}) == {}
    assert set(r._last_run) == {1}


def test_missing_model_disables_quietly():
    r = ActionRecognizer(model_path="/nonexistent.onnx")
    assert not r.enabled and r.update(0.0, FRAME, {1: person(320)}) == {}


# Standing COCO-17 skeleton in body units (y down)
SKELETON = np.array([
    [0, -0.80], [-0.05, -0.85], [0.05, -0.85], [-0.10, -0.82], [0.10, -0.82],
    [-0.20, -0.60], [0.20, -0.60], [-0.25, -0.30], [0.25, -0.30], [-0.27, -0.02], [0.27, -0.02],
    [-0.12, 0.00], [0.12, 0.00], [-0.13, 0.42], [0.13, 0.42], [-0.14, 0.85], [0.14, 0.85],
])


def body(tilt_deg=0.0, drop=0.0, rng=np.random.default_rng(0)):
    a = np.radians(tilt_deg)
    rot = np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]])
    pts = SKELETON @ rot.T * 150 + (320, 240 + drop) + rng.normal(0, 1.5, SKELETON.shape)
    return {"kpts": {n: (float(x), float(y), 0.9) for n, (x, y) in zip(KEYPOINT_NAMES, pts)}}


def _final_result(seq, fps=15):
    r = ActionRecognizer(every_seconds=0)
    assert r.enabled
    for i, p in enumerate(seq):
        r.update(i / fps, FRAME, {1: p})
        if r._pending is not None:
            r._pending.result()                                       # tests: wait for the worker
    return r.update(len(seq) / fps, FRAME, {1: seq[-1]})


@pytest.mark.skipif(not ACTION_MODEL.is_file(), reason="run scripts/export_action_model.py")
def test_model_does_not_alert_on_a_standing_person():
    assert _final_result([body() for _ in range(45)]) == {}


@pytest.mark.skipif(not ACTION_MODEL.is_file(), reason="run scripts/export_action_model.py")
def test_model_recognizes_a_fall():
    seq = [body() for _ in range(15)]                                 # 1 s upright
    seq += [body(9 * k, 10 * k) for k in range(1, 11)]               # topples over ~0.7 s
    seq += [body(90, 100) for _ in range(20)]                         # lies there
    reason, label, prob = _final_result(seq)[1]
    assert (reason, label) == ("falling", "falling") and prob > 0.9


class _FakeRecognizer:
    def __init__(self, result):
        self.result = result

    def update(self, now, frame_shape, poses):
        return self.result


class _FakePose:
    enabled = True

    def detect(self, frame):
        return [{"bbox": (100, 100, 200, 400), **person(150, 250, 280)}]


def _behavior_ctx():
    track = SimpleNamespace(track_id=7, is_confirmed=lambda: True, to_ltrb=lambda: (100, 100, 200, 400))
    ctx = FrameContext(frame=np.zeros(FRAME, dtype=np.uint8))
    ctx.tracks, ctx.timestamp = [track], 1.0
    return ctx


def test_behavior_stage_reports_learned_action_as_a_reason():
    stage = BehaviorStage(pose_analyzer=_FakePose(), pose_every_n=1,
                          action_recognizer=_FakeRecognizer({7: ("fighting", NTU60_LABELS[49], 0.9)}))
    ctx = stage.process(_behavior_ctx())
    assert ctx.suspicious_tracks[7] == ["fighting"]


def test_behavior_stage_routes_learned_fall_to_fall_alert():
    stage = BehaviorStage(pose_analyzer=_FakePose(), pose_every_n=1,
                          action_recognizer=_FakeRecognizer({7: ("falling", NTU60_LABELS[42], 0.8)}))
    ctx = stage.process(_behavior_ctx())
    assert 7 in ctx.fall_tracks and 7 not in ctx.suspicious_tracks
