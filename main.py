"""
AI Smart Surveillance System (Aegis) v5.0
============================================
Production Architecture — Pipeline-based Entrypoint

Usage:
    python main.py                       # Single camera (config.yaml)
    python main.py --video path/to.mp4   # Video file
    python main.py --multi               # All enabled cameras (cameras.yaml)
    python main.py --multi --no-display  # Headless multi-camera
"""

import argparse
import logging
import os
import sys
import threading
import time

import cv2

from core.app.factory import build_pipeline
from core.runtime import run_camera_loop
from paths import CONFIG_YAML, EVIDENCE_DIR, ROOT
from utils.config import load_cameras_config, load_yaml, expand_env, get_camera_geo
from utils.media import fresh_process_sees_webcam, resolve_source
from utils.system import logger

cv2.setNumThreads(0)

# Exit code asking run.sh's supervisor to restart the pipeline (it restarts on any non-zero exit).
RESTART_EXIT_CODE = 75
_restart_requested = threading.Event()
_HOTPLUG_MARK = ROOT / "logs" / ".webcam_hotplug_restart"


def _hotplug_restart_allowed(min_gap: float = 600.0) -> bool:
    """At most one hotplug restart per `min_gap` seconds, so a webcam that opens in a fresh
    process but still fails here cannot put the whole pipeline into a restart loop."""
    try:
        if time.time() - _HOTPLUG_MARK.stat().st_mtime < min_gap:
            return False
    except OSError:
        pass
    try:
        _HOTPLUG_MARK.parent.mkdir(parents=True, exist_ok=True)
        _HOTPLUG_MARK.touch()
    except OSError:
        return False
    return True


def _resolve_camera_index(cfg):
    env_index = os.getenv("CAMERA_INDEX")
    if env_index:
        try:
            return int(env_index)
        except ValueError:
            return env_index
    return expand_env(cfg.get("camera_index", 0))


def _start_camera_thread(cam_cfg, cfg, base_dir, show_window):
    cam_id = cam_cfg["id"]
    cam_loc = cam_cfg.get("location", cam_id)
    cam_name = cam_cfg.get("name", cam_id)
    cam_lat = cam_cfg.get("lat")
    cam_lng = cam_cfg.get("lng")
    source = resolve_source(cam_cfg.get("source", 0))
    fps = cam_cfg.get("fps_limit", cfg.get("target_fps", 30))

    # Wire ONVIF PTZ if configured for this camera
    if cam_cfg.get("onvif_host"):
        try:
            from backend.services.ptz import configure_onvif
            configure_onvif(
                cam_id,
                host=str(cam_cfg["onvif_host"]),
                username=str(cam_cfg.get("onvif_user") or "admin"),
                password=str(cam_cfg.get("onvif_pass") or ""),
                profile_token=cam_cfg.get("onvif_profile") or "Profile_1",
            )
            logger.info(f"ONVIF PTZ configured for {cam_id}")
        except Exception as e:
            logger.warning(f"ONVIF setup skipped for {cam_id}: {e}")

    pipeline, criminal_names, _ = build_pipeline(
        cfg, base_dir, camera_location=cam_loc,
        zones=cam_cfg.get("zones"), lines=cam_cfg.get("lines"),
    )

    stop_event = threading.Event()

    def worker():
        # A camera that is unreachable (phone app closed, Wi-Fi down) or whose stream
        # drops must keep retrying; otherwise its thread dies and it stays off for good.
        delay = 10.0
        while not stop_event.is_set():
            started = time.time()
            try:
                run_camera_loop(
                    pipeline=pipeline,
                    criminal_names=criminal_names,
                    source=source,
                    camera_id=cam_id,
                    camera_location=cam_loc,
                    camera_name=cam_name,
                    camera_lat=cam_lat,
                    camera_lng=cam_lng,
                    target_fps=fps,
                    show_window=show_window,
                    window_title=f"AI-SSS — {cam_name}",
                    stop_event=stop_event,
                )
            except Exception as e:
                logger.error(f"[{cam_id}] camera unavailable: {e}")
                if (sys.platform == "darwin" and isinstance(source, int)
                        and fresh_process_sees_webcam(source) and _hotplug_restart_allowed()):
                    # macOS never refreshes this process's camera list: a webcam plugged in after
                    # start stays invisible here until the pipeline restarts.
                    logger.warning(f"[{cam_id}] webcam {source} was plugged in after start — restarting pipeline")
                    _restart_requested.set()
                    break
            if stop_event.is_set():
                break
            if time.time() - started > 60:      # it was healthy for a while: retry soon
                delay = 10.0
            logger.warning(f"[{cam_id}] offline — retrying in {int(delay)}s")
            if stop_event.wait(delay):
                break
            delay = min(delay * 2, float(os.getenv("CAMERA_RETRY_MAX", "30")))

    t = threading.Thread(target=worker, name=f"camera-{cam_id}", daemon=True)
    t.start()
    return t, stop_event


def main():
    parser = argparse.ArgumentParser(description="AI Smart Surveillance System v5.0")
    parser.add_argument("--video", type=str, default="", help="Path to video file.")
    parser.add_argument("--multi", action="store_true", help="Run all enabled cameras from cameras.yaml.")
    parser.add_argument("--no-display", action="store_true", help="Headless mode (no OpenCV windows).")
    args = parser.parse_args()
    base_dir = str(ROOT)

    cfg = load_yaml(str(CONFIG_YAML))

    for d in ["criminals", "weapons", "suspicious"]:
        os.makedirs(EVIDENCE_DIR / d, exist_ok=True)

    show_window = not args.no_display and os.getenv("HEADLESS", "false").lower() != "true"
    target_fps = cfg.get("target_fps", 30)

    if args.multi:
        cameras = load_cameras_config(base_dir)
        if not cameras:
            # Keep running: the hot-reload loop below starts cameras as soon as one is enabled
            # (e.g. from the dashboard). Exiting here left nothing running to pick that up.
            logger.warning("No enabled cameras in config/cameras.yaml — waiting for one to be enabled")
        local = {}
        for c in cameras:
            if isinstance(c.get("source", 0), int):
                local.setdefault(c["source"], []).append(c["id"])
        for src, ids in local.items():
            if len(ids) > 1:
                logger.warning(
                    f"Cameras {', '.join(ids)} all use local webcam {src}: they share one device and "
                    f"each runs a full pipeline on it. Disable all but one in config/cameras.yaml."
                )
        logger.info(f"Starting multi-camera mode: {len(cameras)} camera(s)")
        threads_and_events = {c["id"]: _start_camera_thread(c, cfg, base_dir, show_window) for c in cameras}
        try:
            while True:
                time.sleep(2.0)
                if _restart_requested.is_set():
                    logging.shutdown()
                    os._exit(RESTART_EXIT_CODE)     # skip joining camera threads stuck in OpenCV
                current_cameras = load_cameras_config(base_dir)
                active_cids = {c.get("id") for c in current_cameras if c.get("id")}
                
                # 1. Stop cameras that are no longer enabled
                for cid in list(threads_and_events.keys()):
                    if cid not in active_cids:
                        logger.info(f"Camera disabled or removed: {cid}. Stopping stream.")
                        _, stop_event = threads_and_events[cid]
                        stop_event.set()
                        del threads_and_events[cid]

                # 2. Start newly enabled cameras
                for c in current_cameras:
                    cid = c.get("id")
                    if cid and cid not in threads_and_events:
                        logger.info(f"User enabled camera: {cid}. Starting stream.")
                        try:
                            threads_and_events[cid] = _start_camera_thread(c, cfg, base_dir, show_window)
                        except Exception as e:  # noqa: BLE001  one bad camera must not kill hot-reload
                            logger.error(f"Could not start camera {cid}: {e}")
                            time.sleep(5.0)
        except KeyboardInterrupt:
            pass
        cv2.destroyAllWindows()
        return

    if args.video:
        source = args.video
        camera_id = "video_0"
        geo = get_camera_geo(base_dir, camera_id)
    else:
        source = _resolve_camera_index(cfg)
        camera_id = "cam_0"
        geo = get_camera_geo(base_dir, camera_id)

    camera_location = geo.get("location", cfg.get("camera_location", "Camera_1"))
    camera_name = geo.get("name", camera_location)
    camera_lat = geo.get("lat")
    camera_lng = geo.get("lng")

    pipeline, criminal_names, camera_location = build_pipeline(
        cfg, base_dir, camera_location=camera_location,
    )
    logger.info("System started — press Q to quit, T for thermal, S for stats")
    if camera_lat and camera_lng:
        logger.info(f"Camera GPS: {camera_lat}, {camera_lng}")

    run_camera_loop(
        pipeline=pipeline,
        criminal_names=criminal_names,
        source=source,
        camera_id=camera_id,
        camera_location=camera_location,
        camera_name=camera_name,
        camera_lat=camera_lat,
        camera_lng=camera_lng,
        target_fps=target_fps,
        show_window=show_window,
    )

    stats = pipeline.get_stats()
    logger.info(f"Final pipeline stats: {stats}")
    logger.info("System stopped")


if __name__ == "__main__":
    main()

