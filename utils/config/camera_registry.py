"""Camera geo registry — resolves GPS coordinates per camera_id."""

import os
from typing import Optional

from utils.config.config_loader import load_yaml, load_cameras_config, expand_env


def _default_geo(cfg: dict) -> dict:
    return {
        "camera_id": "cam_0",
        "name": cfg.get("camera_name", "Default Camera"),
        "location": cfg.get("camera_location", "Camera_1"),
        "lat": cfg.get("camera_lat"),
        "lng": cfg.get("camera_lng"),
    }


def build_camera_registry(base_dir: str) -> dict:
    """Build camera_id → {name, location, lat, lng} from cameras.yaml + config.yaml."""
    registry = {}
    config_path = os.path.join(base_dir, "config", "config.yaml")
    cfg = expand_env(load_yaml(config_path)) if os.path.exists(config_path) else {}

    for cam in load_cameras_config(base_dir):
        registry[cam["id"]] = {
            "camera_id": cam["id"],
            "name": cam.get("name", cam["id"]),
            "location": cam.get("location", cam["id"]),
            "lat": cam.get("lat"),
            "lng": cam.get("lng"),
            "rtsp_url": str(cam.get("source", "")),
        }

    if "cam_0" not in registry:
        registry["cam_0"] = _default_geo(cfg)
    if "video_0" not in registry:
        registry["video_0"] = {
            "camera_id": "video_0",
            "name": cfg.get("camera_name", "Demo Video"),
            "location": cfg.get("camera_location", "Demo_Video"),
            "lat": cfg.get("camera_lat"),
            "lng": cfg.get("camera_lng"),
        }

    return registry


def get_camera_geo(base_dir: str, camera_id: str) -> dict:
    registry = build_camera_registry(base_dir)
    return registry.get(camera_id, registry.get("cam_0", {}))


def maps_url(lat: Optional[float], lng: Optional[float]) -> Optional[str]:
    if lat is None or lng is None:
        return None
    return f"https://www.google.com/maps?q={lat},{lng}"

