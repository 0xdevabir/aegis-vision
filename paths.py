"""
Project path constants — single source of truth for directories.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent

CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
WATCHLIST_DIR = DATA_DIR / "watchlist"
DEMO_CLIPS_DIR = DATA_DIR / "demo" / "clips"
RECORDINGS_DIR = DATA_DIR / "recordings"
RESULTS_DIR = DATA_DIR / "results"
EVIDENCE_DIR = ROOT / "evidence"
MODELS_DIR = ROOT / "models"
LOGS_DIR = ROOT / "logs"

CONFIG_YAML = CONFIG_DIR / "config.yaml"
CAMERAS_YAML = CONFIG_DIR / "cameras.yaml"
MODELS_YAML = CONFIG_DIR / "models.yaml"
WATCHLIST_MANIFEST = WATCHLIST_DIR / "manifest.json"

