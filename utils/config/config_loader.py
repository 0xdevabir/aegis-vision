"""Load and merge YAML configuration with environment variable expansion."""

import os


def load_yaml(path: str) -> dict:
    import yaml

    with open(path, "r") as f:
        return yaml.safe_load(f) or {}


def expand_env(value):
    if isinstance(value, str):
        if value.startswith("${") and value.endswith("}"):
            return os.getenv(value[2:-1], "")
        if value.startswith("env:"):
            return os.getenv(value[4:], "")
        return os.path.expandvars(value)
    if isinstance(value, dict):
        return {k: expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [expand_env(v) for v in value]
    return value


def load_cameras_config(base_dir: str) -> list[dict]:
    path = os.path.join(base_dir, "config", "cameras.yaml")
    if not os.path.exists(path):
        return []
    data = expand_env(load_yaml(path))
    cameras = data.get("cameras", [])
    return [c for c in cameras if c.get("enabled", True)]
