# syntax=docker/dockerfile:1
# Aegis application image — runs both roles: `api` (FastAPI) and `pipeline` (CV workers).

# ---- builder: compiles dlib and installs every Python dependency into a venv ----
FROM python:3.11-slim AS builder
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential cmake libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
ENV VIRTUAL_ENV=/opt/venv PATH=/opt/venv/bin:$PATH PIP_NO_CACHE_DIR=1
RUN python -m venv $VIRTUAL_ENV && pip install --upgrade pip
# CPU-only torch first: the default Linux wheel bundles CUDA (~2 GB) and there is no GPU here.
RUN pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
COPY requirements.txt .
RUN pip install -r requirements.txt

# ---- runtime ----
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*
ENV VIRTUAL_ENV=/opt/venv PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 ENVIRONMENT=production \
    USE_SQLITE=false ALLOW_SQLITE_FALLBACK=false HEADLESS=true
COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY . .
RUN chmod +x docker/entrypoint.sh \
    && useradd -m -u 1000 aegis \
    && mkdir -p data/recordings data/watchlist evidence logs models utils/logs \
    && chown -R aegis:aegis /app
USER aegis

EXPOSE 8000
ENTRYPOINT ["/app/docker/entrypoint.sh"]
# One API worker on purpose: the live-frame buffer, WebSocket hub and rate limiter are in-process.
CMD ["api"]
