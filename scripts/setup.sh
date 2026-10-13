#!/bin/bash
# Aegis Setup Script

set -e

echo "================================================"
echo "  AI Surveillance System — Setup"
echo "================================================"
echo ""

if ! command -v psql &> /dev/null; then
    echo "ERROR: PostgreSQL is not installed or not in PATH"
    exit 1
fi

if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 is not installed"
    exit 1
fi

echo "1. Creating PostgreSQL database..."
createdb surveillance_db 2>/dev/null || echo "   Database may already exist"

echo ""
echo "2. Creating .env file from example..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "   .env created — edit SECRET_KEY and INTERNAL_API_KEY"
else
    echo "   .env already exists, skipping"
fi

echo ""
echo "3. Creating virtualenv and installing Python dependencies..."
BOOT=""
for cand in python3.12 python3.11 python3.10 python3; do
  if command -v "$cand" >/dev/null 2>&1; then BOOT="$cand"; break; fi
done
if [ -z "$BOOT" ]; then
  echo "ERROR: Need Python 3.10–3.12"
  exit 1
fi
if [ ! -x ".venv/bin/python" ]; then
  echo "   Creating .venv with $BOOT…"
  "$BOOT" -m venv .venv
  .venv/bin/pip install -q --upgrade pip
fi
.venv/bin/pip install -r requirements.txt
PYTHON=".venv/bin/python"

echo ""
echo "4. Initializing database schema..."
$PYTHON -m backend.init_db

echo ""
echo "5. Ingesting known persons (face encodings)..."
$PYTHON -m backend.migrate 2>/dev/null || $PYTHON scripts/ingest_watchlist.py 2>/dev/null || echo "   Run: .venv/bin/python scripts/ingest_watchlist.py"

echo ""
echo "6. Creating admin user (password is printed below; save it)..."
$PYTHON scripts/seed_demo.py 2>/dev/null || true

echo ""
echo "7. Syncing camera GPS to database..."
$PYTHON scripts/seed_cameras.py 2>/dev/null || true

echo ""
echo "8. Converting HEIC face images to JPG (if any)..."
$PYTHON scripts/convert_heic.py 2>/dev/null || true

echo ""
echo "================================================"
echo "  Setup Complete!"
echo "================================================"
echo ""
echo "Next steps:"
echo "  ./run.sh"
echo "  OR manually:"
echo "    .venv/bin/uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000"
echo "    .venv/bin/python main.py --video data/demo/clips/sample.mp4"
echo "    cd frontend && npm run dev"
echo ""

