"""HOG first, CNN only as a fallback; boxes come back in the original image's coordinates."""
import types

import numpy as np

from utils import face_detect


class FakeFR:
    def __init__(self, hog=(), cnn=()):
        self.hog, self.cnn, self.calls = list(hog), list(cnn), []

    def face_locations(self, img, model="hog", number_of_times_to_upsample=1):
        self.calls.append((model, img.shape[:2]))
        return self.hog if model == "hog" else self.cnn


def _img(h=720, w=1280):
    return np.zeros((h, w, 3), np.uint8)


def test_hog_hit_skips_cnn():
    fr = FakeFR(hog=[(10, 60, 70, 20)])
    assert face_detect.locate_faces(_img(), fr) == [(10, 60, 70, 20)]
    assert [c[0] for c in fr.calls] == ["hog"]


def test_cnn_fallback_runs_on_downscaled_copy_and_maps_back():
    fr = FakeFR(cnn=[(50, 150, 150, 50)])             # found at 640x360 (scale 0.5)
    boxes = face_detect.locate_faces(_img(720, 1280), fr, cnn_max_dim=640)
    assert boxes == [(100, 300, 300, 100)]            # mapped to the 1280x720 frame
    assert fr.calls[1] == ("cnn", (360, 640))


def test_cnn_fallback_can_be_disabled_per_call_and_globally(monkeypatch):
    fr = FakeFR(cnn=[(1, 2, 3, 4)])
    assert face_detect.locate_faces(_img(), fr, cnn_fallback=False) == []
    assert [c[0] for c in fr.calls] == ["hog"]
    monkeypatch.setattr(face_detect, "CNN_ENABLED", False)
    assert face_detect.locate_faces(_img(), FakeFR(cnn=[(1, 2, 3, 4)])) == []


def test_recognizer_limits_cnn_fallback_with_cooldown(monkeypatch):
    from core.recognition import face_recognizer_db as mod
    monkeypatch.setattr(face_detect, "_yunet", False)    # dlib-only path
    fr = FakeFR()                                      # never finds a face
    monkeypatch.setattr(mod, "face_recognition", types.SimpleNamespace(face_locations=fr.face_locations),
                        raising=False)
    rec = mod.FaceRecognizerDB(cnn_cooldown=60)
    roi = np.zeros((200, 200, 3), np.uint8)
    for _ in range(4):
        rec.recognize_detail(roi)
    models = [c[0] for c in fr.calls]
    assert models.count("cnn") == 1 and models.count("hog") == 4   # CNN only once per cooldown


def test_cnn_cooldown_is_per_camera(monkeypatch):
    """A camera burning its CNN budget must not lock another camera out of the CNN fallback."""
    from core.recognition import face_recognizer_db as mod
    fr = FakeFR()                                      # never finds a face
    monkeypatch.setattr(mod, "face_recognition", types.SimpleNamespace(face_locations=fr.face_locations),
                        raising=False)
    monkeypatch.setattr(face_detect, "_yunet", False)
    rec = mod.FaceRecognizerDB(cnn_cooldown=60)
    roi = np.zeros((200, 200, 3), np.uint8)
    rec.recognize_detail(roi, source="cam_a")
    rec.recognize_detail(roi, source="cam_a")
    rec.recognize_detail(roi, source="cam_b")
    models = [c[0] for c in fr.calls]
    assert models.count("cnn") == 2                    # once for cam_a, once for cam_b


def test_yunet_unavailable_returns_none_so_dlib_is_used(monkeypatch):
    monkeypatch.setattr(face_detect, "_yunet", False)
    assert face_detect.yunet_boxes(np.zeros((80, 80, 3), np.uint8)) is None


def test_yunet_hit_skips_dlib_entirely(monkeypatch):
    fr = FakeFR(hog=[(1, 2, 3, 4)], cnn=[(1, 2, 3, 4)])
    monkeypatch.setattr(face_detect, "yunet_boxes", lambda rgb: [(5, 70, 70, 10)])
    monkeypatch.setattr(fr, "face_encodings", lambda rgb, boxes: [boxes[0]], raising=False)
    enc, missed = face_detect.detect_and_encode(_img(100, 100), 1, True, 20, 0.0, face_recognition=fr)
    assert enc == (5, 70, 70, 10) and missed is False
    assert fr.calls == []                                # neither HOG nor CNN ran


def test_yunet_miss_falls_back_to_cnn_only_when_allowed(monkeypatch):
    monkeypatch.setattr(face_detect, "yunet_boxes", lambda rgb: [])
    fr = FakeFR()
    assert face_detect.detect_and_encode(_img(100, 100), 1, False, 20, 0.0, face_recognition=fr) == (None, False)
    assert fr.calls == []                                # cooldown active: no slow detector
    enc, missed = face_detect.detect_and_encode(_img(100, 100), 1, True, 20, 0.0, face_recognition=fr)
    assert enc is None and missed is True
    assert [c[0] for c in fr.calls] == ["cnn"]           # CNN, never the slow multi-upsample HOG
