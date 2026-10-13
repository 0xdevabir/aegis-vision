#!/usr/bin/env python3
"""Ensure .env has real secrets and a usable DATABASE_URL before ./run.sh."""

from __future__ import annotations

import re
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
EXAMPLE = ROOT / ".env.example"


def _gen(n: int = 48) -> str:
    return secrets.token_urlsafe(n)


def ensure_face_model() -> None:
    """Fetch the YuNet face detector (232 KB) if missing. Best effort: without it face recognition
    still works through dlib, only slower (~10x on the detection step)."""
    sys.path.insert(0, str(ROOT))
    from utils.face_detect import YUNET_MODEL, YUNET_URL

    if YUNET_MODEL.is_file():
        return
    try:
        import urllib.request

        YUNET_MODEL.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(YUNET_URL, timeout=20) as r:
            data = r.read()
        if len(data) < 100_000:                      # an error page, not the model
            raise ValueError(f"unexpected download size {len(data)}")
        YUNET_MODEL.write_bytes(data)
        print(f"Downloaded face detector → {YUNET_MODEL.relative_to(ROOT)}")
    except Exception as e:  # noqa: BLE001
        print(f"  face detector not downloaded ({e}); using slower dlib detection")


def main() -> int:
    ensure_face_model()
    if not ENV_PATH.exists():
        if EXAMPLE.exists():
            ENV_PATH.write_text(EXAMPLE.read_text())
            print("Created .env from .env.example")
        else:
            ENV_PATH.write_text("")
            print("Created empty .env")

    text = ENV_PATH.read_text()
    changed = False

    def upsert(key: str, value: str, only_if_placeholder: bool = True) -> None:
        nonlocal text, changed
        m = re.search(rf"^{re.escape(key)}=(.*)$", text, re.M)
        cur = m.group(1).strip().strip('"').strip("'") if m else ""
        placeholder = (
            not cur
            or cur.startswith("CHANGE_THIS")
            or cur in {
                "change-me-in-production",
                "default-key-change-in-prod",
                "pipeline-internal-key-change-me",
            }
        )
        if m and only_if_placeholder and not placeholder:
            return
        line = f"{key}={value}"
        if m:
            text = re.sub(rf"^{re.escape(key)}=.*$", line, text, count=1, flags=re.M)
        else:
            text = text.rstrip() + f"\n{line}\n"
        changed = True
        print(f"  set {key}")

    upsert("SECRET_KEY", _gen(64))
    upsert("ENCRYPTION_KEY", _gen(32))
    upsert("ENCRYPTION_SALT", _gen(16))
    upsert("INTERNAL_API_KEY", _gen(32))
    upsert("ENVIRONMENT", "development", only_if_placeholder=False)

    # Prefer SQLite for local runs when Postgres isn't available
    db_m = re.search(r"^DATABASE_URL=(.*)$", text, re.M)
    db_url = db_m.group(1).strip().strip('"').strip("'") if db_m else ""
    use_sqlite = "USE_SQLITE=true" in text or "USE_SQLITE=1" in text

    needs_local_db = use_sqlite or (not db_url) or (
        "localhost" in db_url and "surveillance" in db_url
    ) or db_url.startswith("postgresql://surveillance:")

    if needs_local_db:
        sqlite_url = f"sqlite:///{(ROOT / 'data' / 'ai_sss.db').as_posix()}"
        (ROOT / "data").mkdir(parents=True, exist_ok=True)
        upsert("USE_SQLITE", "true", only_if_placeholder=False)
        upsert("DATABASE_URL", sqlite_url, only_if_placeholder=False)
        upsert("ALLOW_SQLITE_FALLBACK", "true", only_if_placeholder=False)
        print(f"  local DB → {sqlite_url}")

    if changed:
        ENV_PATH.write_text(text)
        print("Updated .env")
    else:
        print(".env already OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
