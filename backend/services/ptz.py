"""
PTZ control — digital (software crop/zoom) + ONVIF physical (when configured).

ONVIF uses standard SOAP ContinuousMove / AbsoluteMove / Stop.
If the camera is unreachable, commands are accepted into a simulator so the
UI and API remain fully exercisable for demos and defense.
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass
class PTZState:
    camera_id: str
    mode: str = "digital"  # digital | onvif
    # Digital: pan/tilt in [-1,1], zoom in [1, 8]
    pan: float = 0.0
    tilt: float = 0.0
    zoom: float = 1.0
    # ONVIF / simulator position (normalized)
    onvif_pan: float = 0.0
    onvif_tilt: float = 0.0
    onvif_zoom: float = 0.0
    moving: bool = False
    presets: dict = field(default_factory=dict)
    onvif_host: Optional[str] = None
    onvif_user: Optional[str] = None
    onvif_pass: Optional[str] = None
    onvif_profile: Optional[str] = None
    last_error: Optional[str] = None


_states: dict[str, PTZState] = {}
_lock = threading.Lock()


def get_state(camera_id: str) -> PTZState:
    with _lock:
        if camera_id not in _states:
            _states[camera_id] = PTZState(camera_id=camera_id)
        return _states[camera_id]


def configure_onvif(
    camera_id: str,
    host: str,
    username: str,
    password: str,
    profile_token: Optional[str] = None,
) -> PTZState:
    st = get_state(camera_id)
    st.onvif_host = host.rstrip("/")
    st.onvif_user = username
    st.onvif_pass = password
    st.onvif_profile = profile_token or "Profile_1"
    st.mode = "onvif"
    return st


def set_mode(camera_id: str, mode: str) -> PTZState:
    st = get_state(camera_id)
    if mode not in ("digital", "onvif"):
        raise ValueError("mode must be digital or onvif")
    st.mode = mode
    return st


def digital_move(camera_id: str, pan: float = 0, tilt: float = 0, zoom: Optional[float] = None) -> PTZState:
    st = get_state(camera_id)
    st.pan = max(-1.0, min(1.0, st.pan + pan))
    st.tilt = max(-1.0, min(1.0, st.tilt + tilt))
    if zoom is not None:
        st.zoom = max(1.0, min(8.0, zoom))
    return st


def digital_absolute(camera_id: str, pan: float, tilt: float, zoom: float) -> PTZState:
    st = get_state(camera_id)
    st.pan = max(-1.0, min(1.0, pan))
    st.tilt = max(-1.0, min(1.0, tilt))
    st.zoom = max(1.0, min(8.0, zoom))
    return st


def digital_home(camera_id: str) -> PTZState:
    return digital_absolute(camera_id, 0.0, 0.0, 1.0)


def save_preset(camera_id: str, name: str) -> PTZState:
    st = get_state(camera_id)
    st.presets[name] = {
        "pan": st.pan, "tilt": st.tilt, "zoom": st.zoom,
        "onvif_pan": st.onvif_pan, "onvif_tilt": st.onvif_tilt, "onvif_zoom": st.onvif_zoom,
    }
    return st


def goto_preset(camera_id: str, name: str) -> PTZState:
    st = get_state(camera_id)
    p = st.presets.get(name)
    if not p:
        raise KeyError(f"Preset '{name}' not found")
    st.pan, st.tilt, st.zoom = p["pan"], p["tilt"], p["zoom"]
    st.onvif_pan, st.onvif_tilt, st.onvif_zoom = p["onvif_pan"], p["onvif_tilt"], p["onvif_zoom"]
    if st.mode == "onvif" and st.onvif_host:
        try:
            _onvif_absolute(st, st.onvif_pan, st.onvif_tilt, st.onvif_zoom)
        except Exception as e:
            st.last_error = str(e)
    return st


def continuous_move(camera_id: str, pan: float = 0, tilt: float = 0, zoom: float = 0) -> PTZState:
    """Start continuous PTZ. Digital accumulates; ONVIF sends ContinuousMove."""
    st = get_state(camera_id)
    if st.mode == "digital":
        return digital_move(camera_id, pan * 0.15, tilt * 0.15, st.zoom * (1 + zoom * 0.1) if zoom else None)

    st.moving = True
    # Simulator always updates local state
    st.onvif_pan = max(-1.0, min(1.0, st.onvif_pan + pan * 0.1))
    st.onvif_tilt = max(-1.0, min(1.0, st.onvif_tilt + tilt * 0.1))
    st.onvif_zoom = max(0.0, min(1.0, st.onvif_zoom + zoom * 0.05))

    if st.onvif_host:
        try:
            _onvif_continuous(st, pan, tilt, zoom)
            st.last_error = None
        except Exception as e:
            st.last_error = str(e)
            logger.warning("ONVIF ContinuousMove failed (%s): %s — using simulator", camera_id, e)
    return st


def stop(camera_id: str) -> PTZState:
    st = get_state(camera_id)
    st.moving = False
    if st.mode == "onvif" and st.onvif_host:
        try:
            _onvif_stop(st)
            st.last_error = None
        except Exception as e:
            st.last_error = str(e)
    return st


def state_dict(st: PTZState) -> dict:
    return {
        "camera_id": st.camera_id,
        "mode": st.mode,
        "digital": {"pan": st.pan, "tilt": st.tilt, "zoom": st.zoom},
        "onvif": {
            "pan": st.onvif_pan, "tilt": st.onvif_tilt, "zoom": st.onvif_zoom,
            "configured": bool(st.onvif_host),
            "host": st.onvif_host,
        },
        "moving": st.moving,
        "presets": list(st.presets.keys()),
        "last_error": st.last_error,
    }


def apply_digital_crop(frame, camera_id: str):
    """Crop/zoom a BGR frame according to digital PTZ state."""
    st = get_state(camera_id)
    if st.zoom <= 1.01 and abs(st.pan) < 0.01 and abs(st.tilt) < 0.01:
        return frame
    h, w = frame.shape[:2]
    cw = max(32, int(w / st.zoom))
    ch = max(32, int(h / st.zoom))
    cx = int(w / 2 + st.pan * (w - cw) / 2)
    cy = int(h / 2 - st.tilt * (h - ch) / 2)  # tilt up = negative y
    x1 = max(0, min(w - cw, cx - cw // 2))
    y1 = max(0, min(h - ch, cy - ch // 2))
    crop = frame[y1:y1 + ch, x1:x1 + cw]
    import cv2
    return cv2.resize(crop, (w, h))


# ---------------------------------------------------------------------------
# ONVIF SOAP (minimal — no heavy onvif-zeep dependency required)
# ---------------------------------------------------------------------------

def _soap_envelope(body: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope" '
        'xmlns:tt="http://www.onvif.org/ver10/schema" '
        'xmlns:tptz="http://www.onvif.org/ver20/ptz/wsdl">'
        f"<s:Body>{body}</s:Body></s:Envelope>"
    )


def _ptz_url(st: PTZState) -> str:
    host = st.onvif_host or ""
    if host.startswith("http"):
        return f"{host}/onvif/PTZ"
    return f"http://{host}/onvif/PTZ"


def _post_onvif(st: PTZState, body: str) -> str:
    url = _ptz_url(st)
    auth = None
    if st.onvif_user:
        auth = (st.onvif_user, st.onvif_pass or "")
    timeout = float(os.getenv("ONVIF_TIMEOUT", "3"))
    resp = httpx.post(
        url,
        content=_soap_envelope(body),
        headers={"Content-Type": "application/soap+xml; charset=utf-8"},
        auth=auth,
        timeout=timeout,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"ONVIF HTTP {resp.status_code}: {resp.text[:200]}")
    return resp.text


def _onvif_continuous(st: PTZState, pan: float, tilt: float, zoom: float) -> None:
    profile = st.onvif_profile or "Profile_1"
    body = (
        f"<tptz:ContinuousMove>"
        f"<tptz:ProfileToken>{profile}</tptz:ProfileToken>"
        f"<tptz:Velocity>"
        f"<tt:PanTilt x=\"{pan:.3f}\" y=\"{tilt:.3f}\"/>"
        f"<tt:Zoom x=\"{zoom:.3f}\"/>"
        f"</tptz:Velocity>"
        f"</tptz:ContinuousMove>"
    )
    _post_onvif(st, body)


def _onvif_absolute(st: PTZState, pan: float, tilt: float, zoom: float) -> None:
    profile = st.onvif_profile or "Profile_1"
    body = (
        f"<tptz:AbsoluteMove>"
        f"<tptz:ProfileToken>{profile}</tptz:ProfileToken>"
        f"<tptz:Position>"
        f"<tt:PanTilt x=\"{pan:.3f}\" y=\"{tilt:.3f}\"/>"
        f"<tt:Zoom x=\"{zoom:.3f}\"/>"
        f"</tptz:Position>"
        f"</tptz:AbsoluteMove>"
    )
    _post_onvif(st, body)


def _onvif_stop(st: PTZState) -> None:
    profile = st.onvif_profile or "Profile_1"
    body = (
        f"<tptz:Stop>"
        f"<tptz:ProfileToken>{profile}</tptz:ProfileToken>"
        f"<tptz:PanTilt>true</tptz:PanTilt>"
        f"<tptz:Zoom>true</tptz:Zoom>"
        f"</tptz:Stop>"
    )
    _post_onvif(st, body)
