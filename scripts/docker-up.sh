#!/usr/bin/env bash
# One-command Docker bring-up for Aegis (Postgres + Redis + API + pipeline + dashboard).
# Usage: ./scripts/docker-up.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: Docker is not installed. Install Docker Desktop, then retry."
  exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
  echo "ERROR: docker compose plugin missing."
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  echo "ERROR: Docker daemon is not running. Open Docker Desktop, wait until it is ready, then retry."
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
  val="$(grep -E "^${key}=" .env | head -1 | cut -d= -f2- || true)"
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

# Host webcam bridge so Docker cameras with source: 0 / "0" can see the laptop cam.
if command -v make >/dev/null 2>&1; then
  make webcam-bridge-bg || true
fi

echo "Building and starting Aegis stack (first build can take 10–20+ minutes)…"
docker compose up -d --build

HTTP_PORT="$(grep -E '^HTTP_PORT=' .env | head -1 | cut -d= -f2- || true)"
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
