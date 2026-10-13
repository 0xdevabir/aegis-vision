"""Load model paths and settings from config/models.yaml."""

import os
from utils.config.config_loader import load_yaml


def load_model_registry(base_dir: str) -> dict:
    path = os.path.join(base_dir, "config", "models.yaml")
    if not os.path.exists(path):
        return {}
    return load_yaml(path).get("models", {})


def model_path(base_dir: str, model_dir: str, key: str, fallback: str) -> str:
    registry = load_model_registry(base_dir)
    entry = registry.get(key, {})
    rel = entry.get("path", fallback)
    if os.path.isabs(rel):
        return rel
    return os.path.join(model_dir, os.path.basename(rel))


def model_setting(base_dir: str, key: str, setting: str, default=None):
    registry = load_model_registry(base_dir)
    return registry.get(key, {}).get(setting, default)

