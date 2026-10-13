"""
Pipeline Framework — Base Classes
=================================
Provides abstract base for building modular, configurable CV pipelines.

Each stage receives a FrameContext, processes it, and passes it forward.
The SurveillancePipeline orchestrates stages in sequence.
"""

import time
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

logger = logging.getLogger("HumanAnalysis")


@dataclass
class FrameContext:
    """
    Carries all data through the pipeline.
    Each stage reads what it needs and writes its results back.
    """

    # --- Input ---
    frame: np.ndarray                          # BGR frame from camera
    frame_number: int = 0
    timestamp: float = 0.0                     # time.time()
    camera_id: str = ""
    camera_location: str = ""
    camera_name: str = ""
    camera_lat: Optional[float] = None
    camera_lng: Optional[float] = None

    # --- Detection results ---
    human_detections: list = field(default_factory=list)    # [(bbox, conf, cls)]
    vehicle_detections: list = field(default_factory=list)  # [{"bbox", "score", ...}]
    weapon_detections: list = field(default_factory=list)   # [{"bbox", "score", ...}]

    # --- Tracking results ---
    tracks: list = field(default_factory=list)              # DeepSORT tracks
    vehicle_tracks: list = field(default_factory=list)

    # --- Recognition results ---
    identities: dict = field(default_factory=dict)          # track_id → name
    identity_conf: dict = field(default_factory=dict)        # track_id → real match confidence (0-1)
    criminal_ids: set = field(default_factory=set)           # track_ids of criminals
    active_criminals: list = field(default_factory=list)     # criminal names in frame

    # --- Behavior & Anomaly ---
    suspicious_tracks: dict = field(default_factory=dict)   # track_id → reasons
    anomalies: list = field(default_factory=list)           # anomaly dicts

    # --- Analytics ---
    heatmap: Optional[np.ndarray] = None
    dwell_stats: dict = field(default_factory=dict)
    traffic_flow: dict = field(default_factory=dict)

    # --- ANPR ---
    plate_detections: list = field(default_factory=list)    # [{"plate_number", ...}]
    watchlisted_plates: list = field(default_factory=list)

    # --- Aggregated ---
    threat_score: int = 0
    weapon_present: bool = False                            # raw, unconfirmed
    fire_detections: list = field(default_factory=list)
    confirmed_fire: dict = field(default_factory=dict)      # {'fire': detection}
    fall_tracks: dict = field(default_factory=dict)         # track_id → {'bbox'}
    confirmed_weapons: dict = field(default_factory=dict)   # track_id|-1 → detection
    alerts_to_send: list = field(default_factory=list)
    evidence_to_save: list = field(default_factory=list)

    # --- Metadata ---
    metadata: dict = field(default_factory=dict)


class PipelineStage(ABC):
    """Abstract base class for a pipeline stage."""

    def __init__(self, name: str, enabled: bool = True):
        self.name = name
        self.enabled = enabled
        self._total_time_ms: float = 0.0
        self._call_count: int = 0

    @abstractmethod
    def process(self, ctx: FrameContext) -> FrameContext:
        """Process the frame context and return the (possibly modified) context."""
        ...

    def __call__(self, ctx: FrameContext) -> FrameContext:
        if not self.enabled:
            return ctx
        start = time.perf_counter()
        result = self.process(ctx)
        elapsed_ms = (time.perf_counter() - start) * 1000
        self._total_time_ms += elapsed_ms
        self._call_count += 1
        return result

    @property
    def avg_time_ms(self) -> float:
        return self._total_time_ms / max(self._call_count, 1)

    def get_stats(self) -> dict:
        return {
            "name": self.name,
            "enabled": self.enabled,
            "calls": self._call_count,
            "avg_ms": round(self.avg_time_ms, 2),
            "total_ms": round(self._total_time_ms, 2),
        }


class SurveillancePipeline:
    """
    Orchestrates a sequence of PipelineStage instances.

    Usage:
        pipeline = SurveillancePipeline()
        pipeline.add_stage(DetectionStage(...))
        pipeline.add_stage(TrackingStage(...))
        ...
        ctx = pipeline.run(frame, camera_id="gate_1")
    """

    def __init__(self):
        self.stages: list[PipelineStage] = []
        self._frame_count = 0

    def add_stage(self, stage: PipelineStage):
        """Add a stage to the end of the pipeline."""
        self.stages.append(stage)
        logger.info(f"Pipeline: added stage '{stage.name}' (enabled={stage.enabled})")

    def run(self, frame: np.ndarray, camera_id: str = "",
            camera_location: str = "", camera_name: str = "",
            camera_lat: Optional[float] = None,
            camera_lng: Optional[float] = None) -> FrameContext:
        """Run all stages on the given frame."""
        self._frame_count += 1
        ctx = FrameContext(
            frame=frame,
            frame_number=self._frame_count,
            timestamp=time.time(),
            camera_id=camera_id,
            camera_location=camera_location,
            camera_name=camera_name,
            camera_lat=camera_lat,
            camera_lng=camera_lng,
        )
        for stage in self.stages:
            ctx = stage(ctx)
        return ctx

    def get_stats(self) -> dict:
        """Return per-stage timing statistics."""
        return {
            "frame_count": self._frame_count,
            "stages": [s.get_stats() for s in self.stages],
        }

