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

docker-up: webcam-bridge-bg
	docker compose up -d --build
	@echo "Dashboard: http://localhost:$${HTTP_PORT:-8080}"

docker-down: webcam-bridge-stop
	docker compose down

docker-logs:
	docker compose logs -f --tail=100

# Lost the admin password? Reset it inside the running container:
docker-admin:
	docker compose exec backend python scripts/seed_demo.py --reset-password

# Stream the host webcam over HTTP so the Docker pipeline can read it (source: 0).
webcam-bridge:
	python3 scripts/webcam_bridge.py

# Background bridge for Docker: starts once, no-op if already serving on :8090.
webcam-bridge-bg:
	@if lsof -tiTCP:8090 -sTCP:LISTEN >/dev/null 2>&1; then echo "webcam bridge already running"; \
	else mkdir -p logs && nohup python3 scripts/webcam_bridge.py > logs/webcam_bridge.log 2>&1 & \
	echo "webcam bridge started (logs/webcam_bridge.log)"; fi

webcam-bridge-stop:
	@lsof -tiTCP:8090 -sTCP:LISTEN 2>/dev/null | xargs kill 2>/dev/null || true
