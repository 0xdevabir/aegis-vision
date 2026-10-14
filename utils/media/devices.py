"""Local camera devices (built-in and USB webcams) as the operating system lists them.

A camera bound to `device:<unique id>` keeps pointing at the same physical camera. A bare
index does not: OpenCV numbers cameras in unique-ID order, so plugging in another camera
(or an iPhone showing up as a Continuity Camera) can renumber the ones already in use.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger("HumanAnalysis")

DEVICE_PREFIX = "device:"

# What this process saw before it first opened a camera (see snapshot_local_cameras).
_startup: list[dict] | None = None


class CameraListStale(RuntimeError):
    """The device is connected, but was plugged in after this process listed its cameras."""


def _mac_cameras() -> list[dict]:
    out = subprocess.run(["/usr/sbin/system_profiler", "SPCameraDataType", "-json"],
                         capture_output=True, timeout=10, check=True).stdout
    items = json.loads(out).get("SPCameraDataType", [])
    # Same order as OpenCV's AVFoundation backend, so the position is the OpenCV index.
    items.sort(key=lambda d: str(d.get("spcamera_unique-id") or ""))
    return [{"name": d.get("_name") or "Camera", "uid": str(d.get("spcamera_unique-id") or "")} for d in items]


def _linux_cameras() -> list[dict]:
    found = []
    for node in Path("/sys/class/video4linux").glob("video*"):
        number = node.name[5:]
        try:
            # A webcam also exposes a metadata node (index 1): only index 0 delivers video.
            if not number.isdigit() or (node / "index").read_text().strip() != "0":
                continue
            found.append({"index": int(number), "name": (node / "name").read_text().strip(), "uid": ""})
        except OSError:
            continue
    return sorted(found, key=lambda d: d["index"])


def list_local_cameras() -> list[dict]:
    """[{index, name, uid, source}] for every camera connected to this machine right now.

    `source` is what to store as the camera's video source. Empty when the platform cannot
    list cameras (Windows, or a container that does not see the host's devices).
    """
    try:
        if sys.platform == "darwin":
            cameras = _mac_cameras()
        elif sys.platform.startswith("linux"):
            cameras = _linux_cameras()
        else:
            return []
    except Exception as e:  # noqa: BLE001  listing is best-effort, never fatal
        logger.debug(f"Could not list local cameras: {e}")
        return []
    for position, cam in enumerate(cameras):
        cam.setdefault("index", position)
        cam["source"] = f"{DEVICE_PREFIX}{cam['uid']}" if cam["uid"] else str(cam["index"])
    return cameras


def bridge_url(source: str) -> str:
    """Video URL on the host webcam bridge for a local camera source ("0" or "device:<uid>")."""
    from urllib.parse import quote
    return f"{os.environ['LOCAL_CAMERA_URL']}?source={quote(str(source), safe=':')}"


def list_host_cameras() -> list[dict]:
    """The cameras of the machine the user sits at.

    Inside Docker that is not this machine: ask scripts/webcam_bridge.py on the host instead.
    Empty when the bridge is not running, so nothing is reported as unplugged by mistake.
    """
    bridge = os.getenv("LOCAL_CAMERA_URL", "")
    if not bridge:
        return list_local_cameras()
    from urllib.parse import urlsplit
    import urllib.request
    parts = urlsplit(bridge)
    try:
        with urllib.request.urlopen(f"{parts.scheme}://{parts.netloc}/devices", timeout=3) as r:
            return json.loads(r.read()).get("devices", [])
    except Exception as e:  # noqa: BLE001  an old bridge or none at all: nothing to list
        logger.debug(f"Could not list host cameras through the bridge: {e}")
        return []


def snapshot_local_cameras() -> list[dict]:
    """Remember the cameras present now. Call once, before the process opens any camera.

    macOS keeps giving a process the camera list from its first use of the camera API, so the
    indexes that are valid in this process are the ones from this snapshot, not from a later listing.
    """
    global _startup
    _startup = list_local_cameras()
    return _startup


def device_connected(uid: str) -> bool:
    return any(d["uid"] == uid for d in list_local_cameras())


def device_index(uid: str) -> int:
    """OpenCV index of the camera with this unique ID, valid in this process."""
    known = _startup if _startup is not None else list_local_cameras()
    for d in known:
        if d["uid"] == uid:
            return d["index"]
    if _startup is not None and device_connected(uid):
        raise CameraListStale(f"Camera device {uid} was connected after start")
    raise RuntimeError(f"Camera device {uid} is not connected")
