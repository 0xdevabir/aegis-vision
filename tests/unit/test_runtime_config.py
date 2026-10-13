from types import SimpleNamespace as NS

from core.analysis import behavior
from core.runtime.runtime_config import apply_runtime_config


def make_pipeline():
    det = NS(name="detection", human_detector=NS(conf_threshold=0.5),
             vehicle_detector=NS(conf_threshold=0.5), weapon_detector=NS(conf_threshold=0.4))
    rec = NS(name="recognition", face_recognizer=NS(tolerance=0.45))
    beh = NS(name="behavior", anomaly_detector=NS(crowd_threshold=5))
    return NS(stages=[det, rec, beh])


def test_values_are_applied_to_stages():
    p = make_pipeline()
    applied = apply_runtime_config(p, {
        "confidence_threshold": 0.6, "weapon_conf_threshold": 0.7,
        "face_tolerance": 0.40, "crowd_threshold": 8, "loiter_seconds": 30})
    assert len(applied) == 5
    assert p.stages[0].human_detector.conf_threshold == 0.6
    assert p.stages[0].weapon_detector.conf_threshold == 0.7
    assert p.stages[1].face_recognizer.tolerance == 0.40
    assert p.stages[2].anomaly_detector.crowd_threshold == 8
    assert behavior.SUSPICIOUS_LOITER_SECONDS == 30
    behavior.configure_behavior({"loiter_seconds": 15})


def test_out_of_range_and_unknown_values_are_ignored():
    p = make_pipeline()
    applied = apply_runtime_config(p, {"face_tolerance": 0.99, "weapon_conf_threshold": 0.01,
                                       "rm_rf": 1})
    assert applied == {}
    assert p.stages[1].face_recognizer.tolerance == 0.45
    assert p.stages[0].weapon_detector.conf_threshold == 0.4
