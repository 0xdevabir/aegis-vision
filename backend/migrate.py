"""
Legacy data migration + watchlist ingest.
Ingests face encodings from data/watchlist/.
"""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main():
    print("Ingesting watchlist from data/watchlist/ ...")
    script = ROOT / "scripts" / "ingest_watchlist.py"
    try:
        spec = importlib.util.spec_from_file_location("ingest_watchlist", script)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.ingest()
        print("Migration complete.")
    except Exception as e:
        print(f"Migration skipped or failed: {e}")
        print("Run manually: python3 scripts/ingest_watchlist.py")


if __name__ == "__main__":
    main()
