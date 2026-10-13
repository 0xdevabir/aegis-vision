#!/usr/bin/env bash
# ============================================================
# Aegis — one-command full system run
# Usage:
#   ./run.sh
#   ./run.sh data/demo/clips/sample.mp4
#   ./run.sh --no-pipeline          # backend + dashboard only
#   make run
# ============================================================
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

NO_PIPELINE=0
VIDEO=""
for arg in "$@"; do
  case "$arg" in
    --no-pipeline) NO_PIPELINE=1 ;;
    --help|-h)
      echo "Usage: ./run.sh [video.mp4] [--no-pipeline]"
      echo "  Starts backend :8000, frontend :5173, and CV pipeline."
      exit 0
      ;;
    *) VIDEO="$arg" ;;
  esac
done

if [ -z "$VIDEO" ]; then
  VIDEO="data/demo/clips/sample.mp4"
fi

BACKEND_PID=""
PIPELINE_PID=""
FRONTEND_PID=""
PIDS=()

cleanup() {
  echo ""
  echo "Stopping Aegis…"
  for pid in "${PIDS[@]:-}"; do
    pkill -P "$pid" 2>/dev/null || true     # children (the pipeline python) first
    kill "$pid" 2>/dev/null || true
  done
  # Kill anything still bound to our ports (orphans from prior runs)
  for port in 8000 5173; do
    if command -v lsof >/dev/null 2>&1; then
      lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | xargs kill -9 2>/dev/null || true
    fi
  done
  echo "Stopped."
  exit 0
}
trap cleanup INT TERM EXIT

echo "============================================"
echo "  Aegis Command Center — Full System"
echo "============================================"

# --- Python: always use the project's own virtualenv ---
# A random system/conda python is the usual cause of "dlib model not found" or
# torch load errors, so we never fall back to it silently.
if [ ! -x ".venv/bin/python" ]; then
  BOOT=""
  for cand in python3.12 python3.11 python3.10; do
    if command -v "$cand" >/dev/null 2>&1; then BOOT="$cand"; break; fi
  done
  if [ -z "$BOOT" ]; then
    echo "✗ Need Python 3.10–3.12 (found none). Install one, e.g.: brew install python@3.12"
    exit 1
  fi
  echo "[env] Creating .venv with $BOOT and installing requirements (first run only, several minutes)…"
  "$BOOT" -m venv .venv
  .venv/bin/pip install -q --upgrade pip
  .venv/bin/pip install -r requirements.txt
fi
PYTHON=".venv/bin/python"
# shellcheck disable=SC1091
source .venv/bin/activate

CHECK_FLAGS=""
[ "$NO_PIPELINE" -eq 1 ] && CHECK_FLAGS="--backend"
if ! $PYTHON scripts/check_env.py $CHECK_FLAGS; then
  echo "✗ Fix the environment problems above, then re-run ./run.sh"
  exit 1
fi

# --- .env ---
if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example"
fi

echo "[env] Ensuring secrets + local database…"
$PYTHON scripts/ensure_local_env.py

# Load env without breaking on spaces/special chars
set -a
# shellcheck disable=SC1091
source .env 2>/dev/null || true
set +a

export BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:8000}"
export PIPELINE_STREAM_ENABLED="${PIPELINE_STREAM_ENABLED:-true}"
export DVR_ENABLED="${DVR_ENABLED:-true}"
# A video file is a demo source: loop it so the dashboard stays live.
[ -f "$VIDEO" ] && export VIDEO_LOOP="${VIDEO_LOOP:-true}"
export AUTO_ALERTS_ENABLED="${AUTO_ALERTS_ENABLED:-true}"
export USE_SQLITE="${USE_SQLITE:-true}"
export ALLOW_SQLITE_FALLBACK="${ALLOW_SQLITE_FALLBACK:-true}"

# --- Frontend deps ---
if [ ! -d frontend/node_modules ]; then
  echo "[deps] Installing frontend packages…"
  (cd frontend && npm install)
fi

# --- Seed (best-effort) ---
echo "[seed] Demo user + cameras…"
$PYTHON scripts/seed_demo.py 2>/dev/null || echo "  (seed_demo skipped)"
$PYTHON scripts/seed_cameras.py 2>/dev/null || echo "  (seed_cameras skipped)"

# Free ports if stale processes linger
for port in 8000 5173; do
  if command -v lsof >/dev/null 2>&1; then
    lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | xargs kill -9 2>/dev/null || true
  fi
done

# --- Backend ---
echo "[1/3] Backend  → http://localhost:8000"
$PYTHON -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!
PIDS+=("$BACKEND_PID")

# Wait until /health responds (max ~30s)
echo -n "      waiting for API"
for i in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:8000/health" >/dev/null 2>&1; then
    echo " ✓"
    break
  fi
  echo -n "."
  sleep 1
  if [ "$i" -eq 30 ]; then
    echo " ✗ (continuing anyway)"
  fi
done

# --- Pipeline (supervised: restarted if it ever dies) ---
mkdir -p logs
supervise_pipeline() {
  local fast=0 delay=3 t0 code
  while true; do
    t0=$(date +%s)
    # `|| code=` keeps set -e from killing this supervisor when the pipeline exits non-zero.
    code=0
    $PYTHON main.py "$@" 2>&1 | tee -a logs/pipeline.out || code=${PIPESTATUS[0]}
    [ "$code" -eq 0 ] && return 0                       # clean exit (e.g. finished a file)
    if [ $(( $(date +%s) - t0 )) -lt 20 ]; then fast=$((fast + 1)); else fast=0; delay=3; fi
    if [ "$fast" -ge 5 ]; then
      echo "✗ Pipeline keeps crashing right after start (code $code). See logs/pipeline.out"
      return 1
    fi
    echo "⚠ Pipeline exited with code $code — restarting in ${delay}s (see logs/pipeline.out)"
    sleep "$delay"; delay=$(( delay < 30 ? delay * 2 : 30 ))
  done
}

if [ "$NO_PIPELINE" -eq 0 ]; then
  if [ -f "$VIDEO" ]; then
    echo "[2/3] Pipeline → $VIDEO"
    supervise_pipeline --video "$VIDEO" &
  else
    echo "[2/3] Pipeline → webcam / config (no file at $VIDEO)"
    supervise_pipeline --multi --no-display &
  fi
  PIPELINE_PID=$!
  PIDS+=("$PIPELINE_PID")
else
  echo "[2/3] Pipeline skipped (--no-pipeline)"
fi

# --- Frontend ---
echo "[3/3] Dashboard → http://localhost:5173"
(cd frontend && npm run dev -- --host 0.0.0.0 --port 5173) &
FRONTEND_PID=$!
PIDS+=("$FRONTEND_PID")

sleep 2

echo ""
echo "============================================"
echo "  SYSTEM RUNNING"
echo "============================================"
echo "  Dashboard   http://localhost:5173"
echo "  API / docs  http://localhost:8000/docs"
echo "  Health      http://localhost:8000/health"
echo "  Login       admin / (password printed by scripts/seed_demo.py)"
echo ""
echo "  Ctrl+C stops backend + pipeline + frontend"
echo "============================================"
echo ""

# Block until any child exits (or Ctrl+C)
wait

