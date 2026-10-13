# Aegis Development Guide

## Prerequisites
- **macOS / Linux**
- **Python 3.10+**
- **PostgreSQL** (with pgvector)
- **Node.js 18+** (for dashboard)

## Initial Setup

```bash
./scripts/setup.sh
python scripts/seed_demo.py    # creates admin; password printed once (or set ADMIN_PASSWORD)
```

Place `yolov8s.pt` (or configured model) in `models/`.

---

## Running the Full System (Defense Demo)

Use **three terminals**:

### 1. FastAPI Backend
```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```
- API docs: http://localhost:8000/docs
- WebSocket alerts: `ws://localhost:8000/api/v1/ws/alerts`

### 2. Surveillance Pipeline
```bash
# Recommended for defense (reliable)
python main.py --video data/demo/clips/sample.mp4

# USB webcam
python main.py

# IP/CCTV camera — set RTSP in config/config.yaml or .env
python main.py

# Multi-camera (config/cameras.yaml)
python main.py --multi
```

### 3. React Dashboard
```bash
cd frontend && npm install && npm run dev
```
Open http://localhost:5173 → login as **admin** with the password printed by `seed_demo.py`

---

## Pipeline ↔ Backend Integration

The pipeline pushes live events to the backend using `INTERNAL_API_KEY` (see `.env`):

- `POST /api/v1/events/internal` — criminal, weapon, suspicious events
- `POST /api/v1/system/heartbeat` — pipeline health + FPS

Dashboard receives events via WebSocket `/api/v1/ws/alerts`.

---

## IP / CCTV Camera Setup

1. Enable RTSP on the camera; note IP, user, password, stream path
2. Test with VLC: `rtsp://user:pass@192.168.x.x:554/stream1`
3. Add to `.env`:
   ```
   RTSP_GATE_1=rtsp://user:pass@192.168.x.x:554/stream1
   RTSP_TRANSPORT=tcp
   ```
4. In `config/cameras.yaml`: `source: "${RTSP_GATE_1}"`
5. Run `python main.py` or `python main.py --multi`

---

## Evaluation (Thesis Results)

```bash
python scripts/evaluate_pipeline.py --video data/demo/clips/sample.mp4 --frames 200 --output data/results/eval.json
```

---

## Keyboard Shortcuts (Pipeline Window)
- **`S`** — Print per-stage performance stats
- **`T`** — Toggle thermal view
- **`Q`** — Quit

---

## See Also
- [DEFENSE.md](DEFENSE.md) — graduation presentation guide
- [demo/README.md](demo/README.md) — demo video setup

