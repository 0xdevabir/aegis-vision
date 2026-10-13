# Graduation Defense Guide — Aegis (AI Smart Surveillance System)

## Automated criminal alerts (any camera → all channels)

When a watchlisted person is detected on **any camera**, the system **automatically**:

| Channel | What happens |
|---------|----------------|
| **Pipeline alarm** | Mac sound (`afplay`) |
| **OpenCV HUD** | Red box + flashing "CRIMINAL ALERT" banner |
| **Database** | Alert saved to `alerts` table |
| **Audit log** | `AUTO_ALERT` entry in `audit_logs` |
| **WebSocket** | Instant push to dashboard |
| **Dashboard** | Sound + red banner + browser notification + auto-switch to Events |
| **Evidence** | Throttled snapshot saved to DB + `evidence/` |
| **Webhooks** | Generic webhooks (law enforcement, security, CAD, SMS gateway) if configured in `.env` |
| **GPS Map** | Pinpoint camera lat/lng on dashboard + OpenCV HUD + Google Maps link |

Set GPS per camera in `config/cameras.yaml` or `config/config.yaml`:

```yaml
camera_lat: 23.8103   # your campus gate latitude
camera_lng: 90.4125   # your campus gate longitude
```

Sync to database: `python scripts/seed_cameras.py`

### One-command demo

```bash
./run.sh
# or with video:
./run.sh data/demo/clips/sample.mp4
```

Ensure `.env` has matching `INTERNAL_API_KEY` for pipeline ↔ backend.

---

## Quick start (3 terminals)

```bash
# Terminal 1 — Database + backend
./scripts/setup.sh
python scripts/seed_demo.py
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2 — CV pipeline (use video for reliable demo)
python main.py --video data/demo/clips/sample.mp4

# Terminal 3 — Dashboard
cd frontend && npm install && npm run dev
```

Open http://localhost:5173 → login as **admin** with the password printed by `seed_demo.py`

---

## 5-minute defense demo script

| Step | Action | What to say |
|------|--------|-------------|
| 1 | Show Swagger at `/docs` | REST API with auth, evidence, cameras |
| 2 | Run pipeline on demo video | Modular CV pipeline processes each frame |
| 3 | Trigger watchlist match | Face recognition against PostgreSQL encodings |
| 4 | Show dashboard events | Real-time WebSocket alerts from pipeline |
| 5 | Show evidence folder + API | Evidence with SHA-256 chain-of-custody and audit trail |
| 6 | Press `S` in pipeline window | Per-stage performance metrics |
| 7 | Run evaluation script | Quantitative results for thesis |

```bash
python scripts/evaluate_pipeline.py --video data/demo/clips/sample.mp4 --frames 200 --output data/results/eval.json
```

---

## Camera connection options

| Type | Config | Command |
|------|--------|---------|
| Demo video | — | `python main.py --video data/demo/clips/sample.mp4` |
| USB webcam | `camera_index: 0` in config.yaml | `python main.py` |
| IP/CCTV (RTSP) | `camera_index: "rtsp://..."` or `.env` | `python main.py` |
| Multi-camera | Edit `config/cameras.yaml` | `python main.py --multi` |

**RTSP tips:** set `RTSP_TRANSPORT=tcp` in `.env`; test with VLC first.

---

## Architecture talking points

1. **Pipeline stages** — independent, timed, configurable modules
2. **Security** — JWT auth, login lockout, role-based access, audit logs, rate limiting
3. **Integration** — pipeline pushes events via internal API → WebSocket → dashboard
4. **Database** — PostgreSQL (SQLite for local runs); 128-d dlib face encodings, matched in Python
5. **Limitations (be honest)** — browser video needs media server; multi-cam is threaded prototype

---

## Backup plan

If live camera fails: always use `--video data/demo/clips/sample.mp4`  
If WebSocket fails: show `/api/v1/alerts/` in Swagger  
If DB fails: evidence still saves to `evidence/` folder

---

## Likely viva questions

- **Why pipeline architecture?** → modularity, per-stage timing, easy to extend
- **False positives?** → thresholds, throttling, operator review via API
- **Privacy?** → watchlist-only matching, human review before external alerts, audit logs, retention config (off by default)
- **Scalability?** → document Redis/queue as future work; current design is single-node

