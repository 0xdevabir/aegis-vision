#!/usr/bin/env bash
# One-command Docker bring-up for Aegis (Postgres + Redis + API + pipeline + dashboard).
# Usage: ./scripts/docker-up.sh      (macOS, Linux, Git Bash/WSL; PowerShell: scripts\docker-up.ps1)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: Docker is not installed. Install Docker Desktop (or Docker Engine on Linux), then retry."
  exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
  echo "ERROR: docker compose plugin missing."
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  echo "ERROR: cannot reach the Docker daemon. Start Docker Desktop (Linux: sudo systemctl start docker,"
  echo "       and add yourself to the docker group), wait until it is ready, then retry."
  exit 1
fi

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example — set real secrets before production use."
fi

# Compose interpolates these from .env — they must be present (placeholders OK for local demos).
need() {
  local key="$1"
  local val
  val="$(grep -E "^${key}=" .env | head -1 | cut -d= -f2- | tr -d '\r' || true)"
  if [ -z "$val" ]; then
    echo "ERROR: set ${key} in .env, then re-run."
    exit 1
  fi
}
need POSTGRES_PASSWORD
need SECRET_KEY
need ENCRYPTION_KEY
need ENCRYPTION_SALT
need INTERNAL_API_KEY

# Create the mounted folders as this user: a missing one would be created by Docker as root on Linux.
mkdir -p models data/watchlist data/demo/clips logs

# Host webcam bridge so Docker cameras with source: 0 / "0" can see the laptop cam.
start_bridge() {
  local py host=127.0.0.1
  py=".venv/bin/python"
  [ -x "$py" ] || py=".venv/Scripts/python.exe"          # Git Bash on Windows
  [ -x "$py" ] || py="$(command -v python3 || command -v python || true)"
  if [ -z "$py" ] || ! "$py" -c 'import cv2' >/dev/null 2>&1; then
    echo "Webcam bridge skipped: needs Python with OpenCV on the host (./scripts/setup.sh). RTSP/HTTP cameras are unaffected."
    return 0
  fi
  # Docker Engine on Linux: host.docker.internal is the docker bridge gateway, not loopback,
  # so the bridge must listen there. Docker Desktop forwards to the host's loopback.
  if [ "$(uname -s)" = Linux ] && ! docker info -f '{{.OperatingSystem}}' | grep -q 'Docker Desktop'; then
    host="$(docker network inspect bridge -f '{{(index .IPAM.Config 0).Gateway}}' 2>/dev/null || true)"
    host="${host:-172.17.0.1}"
  fi
  if (exec 3<>"/dev/tcp/${host}/8090") 2>/dev/null; then
    echo "webcam bridge already running"
    return 0
  fi
  nohup "$py" scripts/webcam_bridge.py --host "$host" > logs/webcam_bridge.log 2>&1 &
  echo $! > logs/webcam_bridge.pid
  echo "webcam bridge started on ${host}:8090 (logs/webcam_bridge.log)"
}
start_bridge

echo "Building and starting Aegis stack (first build can take 10–20+ minutes)…"
docker compose up -d --build

HTTP_PORT="$(grep -E '^HTTP_PORT=' .env | head -1 | cut -d= -f2- | tr -d '\r' || true)"
HTTP_PORT="${HTTP_PORT:-8080}"
echo ""
echo "============================================"
echo "  Aegis is starting"
echo "  Dashboard  → http://localhost:${HTTP_PORT}"
echo "  API / docs → http://localhost:${HTTP_PORT}/docs"
echo "  Logs       → docker compose logs -f"
echo "  Admin pwd  → docker compose logs backend 2>&1 | grep bootstrap"
echo "  Stop       → docker compose down   (or: make docker-down)"
echo "============================================"
