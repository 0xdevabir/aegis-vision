"""Apply dashboard-managed thresholds to a running pipeline (no restart)."""

import logging
import threading
import time

from core.analysis.behavior import configure_behavior

logger = logging.getLogger("HumanAnalysis")

# name → (min, max): values outside are ignored, never applied.
LIMITS = {
    "confidence_threshold": (0.30, 0.90),
    "weapon_conf_threshold": (0.20, 0.90),
    "face_tolerance": (0.35, 0.60),
    "loiter_seconds": (5, 120),
    "crowd_threshold": (2, 30),
}


def apply_geometry(pipeline, geometry) -> bool:
    """Apply dashboard-defined zones/lines. Returns True if the geometry changed."""
    if not isinstance(geometry, dict):
        return False        # never configured in the dashboard: keep cameras.yaml / defaults
    for stage in pipeline.stages:
        det = getattr(stage, "anomaly_detector", None)
        if stage.name == "behavior" and det is not None:
            zones, lines = geometry.get("zones") or [], geometry.get("lines") or []
            if (zones, lines) == (getattr(det, "_applied_zones", None), getattr(det, "_applied_lines", None)):
                return False
            det.set_geometry(zones, lines)
            det._applied_zones, det._applied_lines = zones, lines
            return True
    return False


def apply_runtime_config(pipeline, values: dict) -> dict:
    """Set thresholds on the pipeline's stages; return what was actually applied."""
    clean = {k: float(v) for k, v in values.items()
             if k in LIMITS and LIMITS[k][0] <= float(v) <= LIMITS[k][1]}
    for stage in pipeline.stages:
        name = stage.name
        if name == "detection":
            if "confidence_threshold" in clean:
                stage.human_detector.conf_threshold = clean["confidence_threshold"]
                if stage.vehicle_detector is not None:
                    stage.vehicle_detector.conf_threshold = clean["confidence_threshold"]
            if "weapon_conf_threshold" in clean and stage.weapon_detector is not None:
                stage.weapon_detector.conf_threshold = clean["weapon_conf_threshold"]
        elif name == "recognition" and "face_tolerance" in clean:
            stage.face_recognizer.tolerance = clean["face_tolerance"]
        elif name == "behavior" and "crowd_threshold" in clean and stage.anomaly_detector is not None:
            stage.anomaly_detector.crowd_threshold = int(clean["crowd_threshold"])
    if "loiter_seconds" in clean:
        configure_behavior({"loiter_seconds": clean["loiter_seconds"]})
    return clean


class RuntimeConfigSync:
    """Polls the backend every `interval` seconds on a side thread (never blocks the loop)."""

    def __init__(self, pipeline, interval: float = 30.0, camera_id: str = ""):
        self.pipeline = pipeline
        self.camera_id = camera_id
        self.interval = interval
        self._last = 0.0
        self._busy = False
        self.last_applied: dict = {}

    def maybe_sync(self, now: float = None) -> None:
        now = time.time() if now is None else now
        if self._busy or now - self._last < self.interval:
            return
        self._last = now
        self._busy = True
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        try:
            import httpx

            from utils.alerts.event_publisher import BACKEND_URL, INTERNAL_API_KEY
            r = httpx.get(f"{BACKEND_URL}/api/v1/config/runtime",
                          params={"camera_id": self.camera_id} if self.camera_id else None,
                          headers={"X-Internal-Key": INTERNAL_API_KEY}, timeout=3.0)
            if r.status_code == 200:
                data = r.json()
                if apply_geometry(self.pipeline, data.get("geometry")):
                    g = data["geometry"]
                    logger.info(f"[{self.camera_id}] zones updated: "
                                f"{len(g.get('zones', []))} zones, {len(g.get('lines', []))} lines")
                applied = apply_runtime_config(self.pipeline, data)
                if applied != self.last_applied:
                    logger.info(f"Runtime thresholds applied: {applied}")
                    self.last_applied = applied
        except Exception as e:
            logger.debug(f"Runtime config sync skipped: {e}")
        finally:
            self._busy = False
