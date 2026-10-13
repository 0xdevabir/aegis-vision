.PHONY: webcam-bridge webcam-bridge-bg webcam-bridge-stop setup demo test backend pipeline frontend ingest run all stop docker-build docker-up docker-down docker-logs docker-admin

setup:
	./scripts/setup.sh

demo: run

run all:
	./run.sh $(ARGS)

stop:
	@for port in 8000 5173; do \
	  lsof -tiTCP:$$port -sTCP:LISTEN 2>/dev/null | xargs kill -9 2>/dev/null || true; \
	done
	@echo "Stopped processes on :8000 and :5173"

test:
	pytest tests/unit/ -v

backend:
	uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

pipeline:
	python main.py --video data/demo/clips/sample.mp4

frontend:
	cd frontend && npm run dev

ingest:
	python scripts/ingest_watchlist.py

# ---- Docker (full stack: Postgres, Redis, API, AI pipeline, dashboard) ----
docker-build:
	docker compose build

docker-up:
	./scripts/docker-up.sh

docker-down: webcam-bridge-stop
	docker compose down

docker-logs:
	docker compose logs -f --tail=100

# Lost the admin password? Reset it inside the running container:
docker-admin:
	docker compose exec backend docker/entrypoint.sh python scripts/seed_demo.py --reset-password

# Stream the host webcam over HTTP so the Docker pipeline can read it (source: 0).
# The bridge needs OpenCV: use the project venv when there is one.
BRIDGE_PY := $(shell [ -x .venv/bin/python ] && echo .venv/bin/python || echo python3)

webcam-bridge:
	$(BRIDGE_PY) scripts/webcam_bridge.py

# Background bridge for Docker: starts once, no-op if already serving on :8090.
webcam-bridge-bg:
	@if lsof -tiTCP:8090 -sTCP:LISTEN >/dev/null 2>&1; then echo "webcam bridge already running"; \
	else mkdir -p logs && nohup $(BRIDGE_PY) scripts/webcam_bridge.py > logs/webcam_bridge.log 2>&1 & \
	echo "webcam bridge started (logs/webcam_bridge.log)"; fi

webcam-bridge-stop:
	@lsof -tiTCP:8090 -sTCP:LISTEN 2>/dev/null | xargs kill 2>/dev/null || true
	@[ ! -f logs/webcam_bridge.pid ] || { kill $$(cat logs/webcam_bridge.pid) 2>/dev/null; rm -f logs/webcam_bridge.pid; }

