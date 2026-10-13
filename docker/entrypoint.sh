#!/usr/bin/env bash
# Usage: entrypoint.sh api | pipeline | <any command>
set -euo pipefail
role="${1:-api}"

wait_for_db() {
  echo "[entrypoint] waiting for the database…"
  for _ in $(seq 1 45); do
    if python - <<'PY' 2>/dev/null
from backend.db.database import engine
with engine.connect():
    pass
PY
    then echo "[entrypoint] database ready"; return 0; fi
    sleep 2
  done
  echo "[entrypoint] ERROR: database not reachable" >&2; return 1
}

case "$role" in
  api)
    wait_for_db
    python scripts/db_upgrade.py          # create/upgrade schema (Alembic-aware)
    python scripts/bootstrap_admin.py     # first start only: creates the admin account
    exec uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 1
    ;;
  pipeline)
    wait_for_db
    echo "[entrypoint] waiting for the API…"
    until curl -sf "${BACKEND_URL:-http://backend:8000}/health" >/dev/null; do sleep 3; done
    exec python main.py --multi --no-display
    ;;
  *)
    exec "$@"
    ;;
esac
