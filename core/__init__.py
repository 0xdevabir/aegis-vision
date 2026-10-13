import importlib

__all__ = [
    "HumanDetector", "WeaponDetector", "HumanTracker",
    "PoseAnalyzer", "FaceRecognizerDB",
    "is_suspicious_behavior",
    "LicensePlateRecognizer", "LicensePlateDatabase",
    "VehicleDetector", "VehicleTracker", "FireSmokeDetector",
    "AnomalyDetector", "Analytics",
]

_modules = {
    "HumanDetector": "core.detectors",
    "WeaponDetector": "core.detectors",
    "VehicleDetector": "core.detectors",
    "VehicleTracker": "core.detectors",
    "FireSmokeDetector": "core.detectors",
    "HumanTracker": "core.tracking",
    "FaceRecognizerDB": "core.recognition",
    "is_suspicious_behavior": "core.analysis",
    "PoseAnalyzer": "core.analysis",
    "LicensePlateRecognizer": "core.analysis",
    "LicensePlateDatabase": "core.analysis",
    "AnomalyDetector": "core.analysis",
    "Analytics": "core.analysis",
}


def __getattr__(name):
    if name in _modules:
        return getattr(importlib.import_module(_modules[name]), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
