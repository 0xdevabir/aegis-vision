# Aegis — AI Smart Surveillance System


## Running the system

```bash
./run.sh                      # one command: backend + pipeline + frontend
# or: make run

./run.sh path/to/video.mp4    # custom video
./run.sh --no-pipeline        # API + dashboard only
make stop                     # kill :8000 and :5173

# First-time setup (once):
./scripts/setup.sh

# Manual:
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
python main.py --video data/demo/clips/sample.mp4
cd frontend && npm run dev
```

## Architecture facts

- **Entrypoint**: `main.py` → `core/app/factory.py` → `SurveillancePipeline` (6 stages)
- **Pipeline stages**: Detection → Tracking → Recognition → Behavior → Analytics → Output
- **Auto alerts**: `utils/alerts/notification_hub.py` → `POST /api/v1/alerts/dispatch` → DB + audit + WebSocket + GPS
- **Config**: `config/config.yaml`, `config/cameras.yaml`, `config/models.yaml` (via `utils/config/`)
- **Paths**: `paths.py` — single source for `data/watchlist`, `data/demo/clips`, etc.
- **Face recognition**: `core/recognition/face_recognizer_db.py` + encodings stored in the DB (PostgreSQL or SQLite)
- **Dashboard**: `frontend/src/` — components, hooks, services
- **Reports API**: `GET /api/v1/reports/incident`
- **Tests**: `pytest tests/unit/`
- **Docs**: `docs/ARCHITECTURE.md`, `docs/DEFENSE.md`

## Directory conventions

- `data/watchlist/` — watchlist face images (JPG/PNG; `scripts/convert_heic.py` for HEIC)
- `data/demo/clips/` — demo video files
- `core/pipeline/stages/` — modular CV stages
- `backend/services/alert_dispatcher.py` — central alert dispatch
- `scripts/` — setup, seed, evaluate, defense demo, deploy

## Quirks

- `INTERNAL_API_KEY` in `.env` must match between backend and pipeline
- Camera GPS in `config/cameras.yaml` or `config/config.yaml`
- Local webcams: prefer `source: device:<unique id>` over an index (`utils/media/devices.py`). OpenCV numbers cameras in unique-ID order, so plugging one in renumbers the others. The Cameras page lists connected devices (`GET /api/v1/cameras/devices`); a new one stays unused until an admin clicks "Use this camera". Pause/Resume is the `enabled` flag in `cameras.yaml`
- Press `S` for pipeline stats, `T` for thermal, `Q` to quit
- Face work runs in worker subprocesses (`core/recognition/face_worker.py`, `FACE_WORKERS`, default 1): dlib next to PyTorch/MPS in one process segfaults. Detector is YuNet (`models/face_detection_yunet_2023mar.onnx`, fetched by `ensure_local_env.py`; dlib is the fallback)
- Read model results (`read_boxes`) inside the model lock: MPS tensor reads outside it crash the process
- Dashboard stream: `STREAM_HUD=clean|full`, `STREAM_FPS`, `STREAM_WIDTH`, `STREAM_QUALITY` (clean = people boxes only; full = local-window HUD)
- Cross-camera tracking: red-alert subjects (watchlist match, armed) are remembered by whole-body appearance in `core/tracking/cross_camera.py` (one tracker shared by all camera threads of `main.py --multi`; model `models/person_reid_youtu_2021nov.onnx`). A lookalike on any camera becomes `ctx.tracked` → `PERSON_TRACKED` alert + captures + "TRACKING" box. `ctx.live_flags` rides the heartbeat (`flags`) to the Live page tile. Tune with `XCAM_MATCH_THRESHOLD`
- Capture basket: while a critical subject is in view the pipeline uploads a zoomed still every `CAPTURE_INTERVAL_SECONDS` (`utils/alerts/capture.py` → `POST /api/v1/captures/ingest` → `ALERT_CAPTURE` on the alerts WebSocket → `frontend/src/components/CaptureBasket.jsx`). A still is only kept if a critical alert for that camera exists in the last 15 min. Gender/age come from the optional `models/genderage.onnx` (`utils/face_attributes.py`) and are estimates
- Dev machine is an 8 GB MacBook: on battery / Low Power Mode or with Chrome+Cursor open it swaps and video stutters. Measure smoothness on AC power
