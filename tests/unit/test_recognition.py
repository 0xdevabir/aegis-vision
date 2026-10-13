import numpy as np

from core.recognition.face_recognizer_db import FaceRecognizerDB
from core.recognition.voting import IdentityVoter


def test_voter_needs_agreement():
    v = IdentityVoter(window=5, min_votes=2)
    v.add(1, "A")
    v.add(1, "B")
    assert v.confirmed(1) is None
    v.add(1, "A")
    assert v.confirmed(1) == "A"
    for _ in range(3):                   # misses push the old votes out of the window
        v.add(1, None)
    assert v.confirmed(1) is None
    v.prune(set())
    assert v.confirmed(1) is None


def test_single_identity_needs_tighter_match():
    r = FaceRecognizerDB(tolerance=0.45, solo_slack=0.05)
    assert r.match(np.array([0.43]), ["A"]) is None                      # inside tol, but no rival to prove it
    assert r.match(np.array([0.30]), ["A"])[0] == "A"
    assert FaceRecognizerDB(tolerance=0.45).match(np.array([0.43]), ["A"])[0] == "A"   # default: tolerance only


def test_match_rejects_far_and_ambiguous():
    r = FaceRecognizerDB(tolerance=0.45, min_margin=0.04)  # explicit: independent of default
    assert r.match(np.array([0.6]), ["A"]) is None                       # beyond tolerance
    assert r.match(np.array([0.30, 0.32]), ["A", "B"]) is None           # too close to call
    name, dist, margin = r.match(np.array([0.30, 0.50, 0.31]), ["A", "B", "A"])
    assert name == "A" and margin > 0.15                                 # same person ≠ rival


def test_cache_refreshes_after_ttl(monkeypatch):
    calls = []
    r = FaceRecognizerDB(loader=lambda: calls.append(1) or ([], []), cache_ttl=60)
    r._load_encodings(); r._load_encodings()
    assert len(calls) == 1
    r._loaded_at -= 61
    r._load_encodings()
    assert len(calls) == 2


def test_dlib_calls_are_serialized_across_threads(monkeypatch):
    """Concurrent camera threads must never be inside dlib at the same time."""
    import threading
    import time
    import types

    from core.recognition import face_recognizer_db as mod

    inside, overlap = [0], [False]

    def locations(rgb, **_):
        inside[0] += 1
        overlap[0] |= inside[0] > 1
        time.sleep(0.02)
        inside[0] -= 1
        return []

    fake = types.SimpleNamespace(face_locations=locations)
    monkeypatch.setattr(mod, "face_recognition", fake, raising=False)
    rec = FaceRecognizerDB()
    roi = np.zeros((200, 200, 3), np.uint8)
    threads = [threading.Thread(target=rec.recognize_detail, args=(roi,)) for _ in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert overlap[0] is False


def test_webcam_index_string_becomes_int(monkeypatch):
    from utils.media.video_source import resolve_source
    monkeypatch.delenv("LOCAL_CAMERA_URL", raising=False)
    assert resolve_source("0") == 0 and resolve_source(1) == 1
    assert resolve_source("http://1.2.3.4/video") == "http://1.2.3.4/video"
