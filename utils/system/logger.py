"""
Structured Logger
=================
Upgraded from basic console-only to file rotation + structured format.
"""

import os
import logging
from logging.handlers import RotatingFileHandler

# Ensure log directory exists
_log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
os.makedirs(_log_dir, exist_ok=True)

logger = logging.getLogger("HumanAnalysis")
logger.setLevel(logging.INFO)

# --- Formatter ---
formatter = logging.Formatter(
    "%(asctime)s | %(name)s | %(levelname)-8s | %(module)s:%(lineno)d | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# --- Console Handler ---
if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

# --- File Handler (rotating: 10MB, keep 5 backups) ---
_log_file = os.path.join(_log_dir, "surveillance.log")
if not any(isinstance(h, RotatingFileHandler) for h in logger.handlers):
    file_handler = RotatingFileHandler(
        _log_file,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
