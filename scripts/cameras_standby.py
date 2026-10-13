#!/usr/bin/env python3
"""Put every camera in config/cameras.yaml on standby, so none opens until it is started from
the dashboard's Live page. run.sh calls this once per launch unless CAMERA_AUTOSTART=true."""
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    path = ROOT / "config" / "cameras.yaml"
    if not path.is_file():
        return 0
    data = yaml.safe_load(path.read_text()) or {}
    for cam in data.get("cameras") or []:
        cam["started"] = False
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
