"""Live video streaming — pipeline pushes annotated JPEG frames, dashboard pulls MJPEG.

The CV pipeline POSTs frames (internal key auth). Browsers consume them as an
MJPEG stream or single snapshot. Since <img> tags cannot send Authorization
headers, viewer endpoints accept the JWT as a query parameter.
"""

import asyncio
import threading
import time
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse

from backend.auth.guards import verify_internal_key, verify_viewer_token

router = APIRouter(prefix="/stream", tags=["stream"])

FRAME_STALE_SECONDS = 15.0
_frames: dict = {}  # camera_id -> (jpeg_bytes, monotonic_ts)
_lock = threading.Lock()
_waiters: dict = {}  # camera_id -> [asyncio.Event]: viewers woken the moment a new frame arrives


@router.post("/frame/{camera_id}")
async def push_frame(
    camera_id: str,
    request: Request,
    x_internal_key: Optional[str] = Header(default=None, alias="X-Internal-Key"),
):
    """Pipeline pushes the latest annotated JPEG frame for a camera."""
    verify_internal_key(x_internal_key)
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="Empty frame")
    with _lock:
        _frames[camera_id] = (body, time.monotonic())
    for ev in _waiters.get(camera_id, ()):
        ev.set()
    return {"status": "ok", "camera_id": camera_id, "bytes": len(body)}


@router.get("/cameras")
def streaming_cameras(token: Optional[str] = Query(default=None)):
    """Camera ids that pushed a frame recently (i.e. have live video)."""
    verify_viewer_token(token)
    now = time.monotonic()
    with _lock:
        return {
            "cameras": [
                cam for cam, (_, ts) in _frames.items()
                if now - ts < FRAME_STALE_SECONDS
            ]
        }


def _frame_with_digital_ptz(camera_id: str, jpeg_bytes: bytes) -> bytes:
    """Apply digital PTZ crop/zoom to a JPEG buffer when zoom/pan active."""
    try:
        from backend.services.ptz import get_state, apply_digital_crop
        st = get_state(camera_id)
        if st.mode != "digital" or (st.zoom <= 1.01 and abs(st.pan) < 0.01 and abs(st.tilt) < 0.01):
            return jpeg_bytes
        import cv2
        import numpy as np
        arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            return jpeg_bytes
        out = apply_digital_crop(img, camera_id)
        ok, buf = cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, 75])
        return buf.tobytes() if ok else jpeg_bytes
    except Exception:
        return jpeg_bytes


@router.get("/{camera_id}/snapshot")
def snapshot(camera_id: str, token: Optional[str] = Query(default=None)):
    verify_viewer_token(token)
    with _lock:
        entry = _frames.get(camera_id)
    if not entry or time.monotonic() - entry[1] > FRAME_STALE_SECONDS:
        raise HTTPException(status_code=404, detail="No live frame for this camera")
    data = _frame_with_digital_ptz(camera_id, entry[0])
    return Response(content=data, media_type="image/jpeg",
                    headers={"Cache-Control": "no-store"})


@router.get("/{camera_id}/live")
async def live_mjpeg(camera_id: str, token: Optional[str] = Query(default=None)):
    """MJPEG stream (multipart/x-mixed-replace) of the latest pipeline frames."""
    verify_viewer_token(token)

    async def generate():
        # Woken by push_frame instead of polling: a new frame goes out at once (no 0-100 ms wait
        # for the next poll), and a slow viewer simply skips to the newest frame.
        ev = asyncio.Event()
        _waiters.setdefault(camera_id, []).append(ev)
        last_ts = 0.0
        idle = 0
        try:
            while True:
                ev.clear()          # before the check: a frame landing after it sets the event again
                with _lock:
                    entry = _frames.get(camera_id)
                if entry and entry[1] != last_ts:
                    raw, last_ts = entry
                    frame = _frame_with_digital_ptz(camera_id, raw)
                    idle = 0
                    yield (
                        b"--frame\r\nContent-Type: image/jpeg\r\n"
                        + f"Content-Length: {len(frame)}\r\n\r\n".encode()
                        + frame + b"\r\n"
                    )
                    continue
                try:
                    await asyncio.wait_for(ev.wait(), timeout=2.0)
                except asyncio.TimeoutError:
                    idle += 1
                    if idle > 15:  # ~30s without a new frame → end stream
                        break
        finally:
            _waiters.get(camera_id, []).remove(ev)

    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-store"},
    )

