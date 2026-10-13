"""Which detector models exist on disk. 'missing' = that feature is OFF."""

import logging
import os

logger = logging.getLogger("HumanAnalysis")

KEYS = ("human_detector", "weapon_detector", "vehicle_detector", "pose_analyzer", "fire_detector")
LABELS = {
    "human_detector": "Person detection",
    "weapon_detector": "Weapon detection",
    "vehicle_detector": "Vehicle detection",
    "pose_analyzer": "Pose / fall checks",
    "fire_detector": "Fire & smoke detection",
}


def model_status() -> dict:
    from paths import ROOT
    from utils.config import load_yaml
    from utils.config.model_config import load_model_registry

    out = {}
    try:
        cfg = load_yaml(str(ROOT / "config" / "config.yaml")) or {}
        registry = load_model_registry(str(ROOT))
        for key in KEYS:
            entry = registry.get(key, {})
            rel = entry.get("path")
            if not rel:
                continue
            path = os.path.join(str(ROOT), cfg.get("model_dir", "models"), os.path.basename(rel))
            if os.path.exists(path):
                out[key] = "ok"
            else:
                out[key] = "not_installed" if entry.get("optional") else "missing"
    except Exception as e:
        logger.warning(f"Model status check failed: {e}")
    return out
