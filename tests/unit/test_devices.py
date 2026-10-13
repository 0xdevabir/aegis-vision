"""Local camera devices: listing, and binding a camera to a device instead of an index."""

import json
import types

import pytest

from utils.media import devices

PROFILER = {"SPCameraDataType": [
    {"_name": "USB Webcam", "spcamera_unique-id": "0x1100000046d0825"},
    {"_name": "FaceTime HD Camera", "spcamera_unique-id": "0x0000000005ac8514"},
]}


@pytest.fixture
def mac(monkeypatch):
    """A Mac whose connected cameras are whatever `state["out"]` holds."""
    state = {"out": PROFILER}
    monkeypatch.setattr(devices.sys, "platform", "darwin")
    monkeypatch.setattr(devices.subprocess, "run",
                        lambda *a, **k: types.SimpleNamespace(stdout=json.dumps(state["out"])))
    monkeypatch.setattr(devices, "_startup", None)
    return state


def test_index_follows_unique_id_order_like_opencv(mac):
    cams = devices.list_local_cameras()
    assert [(c["index"], c["name"]) for c in cams] == [(0, "FaceTime HD Camera"), (1, "USB Webcam")]
    assert cams[1]["source"] == "device:0x1100000046d0825"


def test_listing_failure_is_an_empty_list(monkeypatch):
    monkeypatch.setattr(devices.sys, "platform", "darwin")

    def boom(*a, **k):
        raise OSError("no system_profiler")
    monkeypatch.setattr(devices.subprocess, "run", boom)
    assert devices.list_local_cameras() == []


def test_camera_plugged_in_later_does_not_move_a_bound_camera(mac):
    devices.snapshot_local_cameras()
    assert devices.device_index("0x1100000046d0825") == 1
    # A new camera sorts first, which shifts every OpenCV index in a *fresh* process.
    mac["out"] = {"SPCameraDataType": [{"_name": "iPhone", "spcamera_unique-id": "0x00"}, *PROFILER["SPCameraDataType"]]}
    assert devices.device_index("0x1100000046d0825") == 1
    with pytest.raises(devices.CameraListStale):
        devices.device_index("0x00")


def test_unplugged_device_raises(mac):
    devices.snapshot_local_cameras()
    with pytest.raises(RuntimeError, match="not connected"):
        devices.device_index("0xdead")


def test_open_capture_resolves_a_bound_device_to_its_index(mac, monkeypatch):
    cv2 = pytest.importorskip("cv2")
    from utils.media import video_source
    opened = []

    class Cap:
        def __init__(self, src, *a):
            opened.append(src)

        def isOpened(self):
            return True

        def read(self):
            return False, None

        def release(self):
            pass

    monkeypatch.setattr(cv2, "VideoCapture", Cap)
    video_source.open_capture("device:0x1100000046d0825").release()
    assert opened == [1]
