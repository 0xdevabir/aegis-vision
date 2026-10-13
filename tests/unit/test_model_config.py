"""Tests for model config loader."""

import os
from utils.config import load_model_registry, model_path, model_setting


class TestModelConfig:
    def test_load_registry(self):
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        project = os.path.dirname(base)
        registry = load_model_registry(project)
        assert "human_detector" in registry
        assert registry["human_detector"]["type"] == "yolo"

    def test_model_path(self):
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        project = os.path.dirname(base)
        path = model_path(project, os.path.join(project, "models"), "human_detector", "yolov8s.pt")
        assert path.endswith("yolov8x.pt") or path.endswith("yolov8s.pt")

    def test_model_setting_fallback(self):
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        project = os.path.dirname(base)
        tol = model_setting(project, "face_recognizer", "tolerance", 0.5)
        assert isinstance(tol, (int, float))
