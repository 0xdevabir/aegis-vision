#!/usr/bin/env python3
"""Run evidence retention purge (schedule via cron). Exits non-zero on failure."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.data.retention import run_retention  # noqa: E402


def main() -> int:
    result = run_retention(dry_run="--dry-run" in sys.argv)
    print(json.dumps(result, indent=2, default=str))
    return 1 if result.get("status") == "error" else 0


if __name__ == "__main__":
    sys.exit(main())
