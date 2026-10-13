import os
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.db.database import init_db
from backend.api import alert_routes, audit_routes, events_routes, map_routes, vehicle_routes
from backend.api.auth_routes import router as auth_router
from backend.api.face_routes import router as face_router
from backend.api.evidence_routes import router as evidence_router
from backend.api.camera_routes import router as camera_router
from backend.api.analytics_routes import router as analytics_router
from backend.api.ws_routes import router as ws_router
from backend.api.system_routes import router as system_router
from backend.api.report_routes import router as report_router
from backend.api.stream_routes import router as stream_router
from backend.api.incident_routes import router as incident_router
from backend.api.custody_routes import router as custody_router
from backend.api.recording_routes import router as recording_router
from backend.api.reid_routes import router as reid_router
from backend.api.integration_routes import router as integration_router
from backend.api.calibration_routes import router as calibration_router
from backend.api.vms_routes import router as vms_router
from backend.api.config_routes import router as config_router
from backend.api.metrics_routes import router as metrics_router
from backend.middleware.rate_limiter import RateLimitMiddleware

logger = logging.getLogger("HumanAnalysis")

# ---------------------------------------------------------------------------
# Security: Validate critical secrets on startup
# ---------------------------------------------------------------------------
_INSECURE_DEFAULTS = {
    "change-me-in-production",
    "CHANGE_THIS_SECRET_KEY_IN_PRODUCTION_64_CHARS_MIN",
    "CHANGE_THIS_SECRET_KEY_IN_PRODUCTION_32_CHARS_MIN",
    "CHANGE_THIS_ENCRYPTION_KEY_32_CHARS",
    "",
}


def _is_insecure(value, extra=None):
    if not value:
        return True
    if value in _INSECURE_DEFAULTS or (extra and value in extra):
        return True
    return value.startswith("CHANGE_THIS")


def _validate_secrets():
    """Refuse to start with missing/default secrets (all environments)."""
    from backend.auth.guards import internal_key_is_secure

    secret_key = os.getenv("SECRET_KEY", "")
    encryption_key = os.getenv("ENCRYPTION_KEY", "")
    salt = os.getenv("ENCRYPTION_SALT", "")

    problems = []
    if _is_insecure(secret_key) or len(secret_key) < 32:
        problems.append("SECRET_KEY missing, default, or shorter than 32 chars")
    if _is_insecure(encryption_key, {"default-key-change-in-prod"}):
        problems.append("ENCRYPTION_KEY missing or default")
    if _is_insecure(salt, {"default-salt"}):
        problems.append("ENCRYPTION_SALT missing or default")
    if not internal_key_is_secure():
        problems.append("INTERNAL_API_KEY missing or default")

    if problems:
        raise RuntimeError(
            "SECURITY ERROR: " + "; ".join(problems)
            + ". Run scripts/ensure_local_env.py or set strong values in .env."
        )


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Aegis — AI Smart Surveillance API",
    description="Intelligent surveillance platform with face recognition, ANPR, "
                "anomaly detection, cross-camera tracking, and analytics.",
    version="5.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
_cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(RateLimitMiddleware)

# ---------------------------------------------------------------------------
# Routes (prefixed under /api/v1 for versioning)
# ---------------------------------------------------------------------------
API_V1 = "/api/v1"

app.include_router(auth_router, prefix=API_V1)
app.include_router(face_router, prefix=API_V1)
app.include_router(evidence_router, prefix=API_V1)
app.include_router(audit_routes.router, prefix=API_V1)
app.include_router(camera_router, prefix=API_V1)
app.include_router(vehicle_routes.router, prefix=API_V1)
app.include_router(analytics_router, prefix=API_V1)
app.include_router(alert_routes.router, prefix=API_V1)
app.include_router(events_routes.router, prefix=API_V1)
app.include_router(map_routes.router, prefix=API_V1)
app.include_router(ws_router, prefix=API_V1)
app.include_router(system_router, prefix=API_V1)
app.include_router(report_router, prefix=API_V1)
app.include_router(stream_router, prefix=API_V1)
app.include_router(incident_router, prefix=API_V1)
app.include_router(custody_router, prefix=API_V1)
app.include_router(recording_router, prefix=API_V1)
app.include_router(reid_router, prefix=API_V1)
app.include_router(integration_router, prefix=API_V1)
app.include_router(calibration_router, prefix=API_V1)
app.include_router(vms_router, prefix=API_V1)
app.include_router(config_router, prefix=API_V1)
app.include_router(metrics_router, prefix=API_V1)


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def startup_event():
    _validate_secrets()
    init_db()
    import asyncio
    from backend.services.escalation import escalation_loop
    app.state.escalation_task = asyncio.create_task(escalation_loop())
    from scripts.seed_cameras import seed_cameras
    seed_cameras()
    try:
        from utils.config import load_yaml, expand_env
        from utils.alerts.event_publisher import set_auto_alerts_enabled
        cfg_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "config.yaml")
        if os.path.exists(cfg_path):
            cfg = expand_env(load_yaml(cfg_path))
            if "auto_alerts_enabled" in cfg:
                set_auto_alerts_enabled(bool(cfg.get("auto_alerts_enabled", True)))
    except Exception as e:
        logger.warning(f"Config auto_alerts load skipped: {e}")
    logger.info("✅ AI-SSS Backend started successfully")


@app.get("/health")
def health_check():
    checks = {"database": "unknown", "redis": "unknown", "pipeline": "unknown"}
    status = "healthy"
    try:
        from backend.db.database import SessionLocal
        db = SessionLocal()
        db.execute(__import__("sqlalchemy").text("SELECT 1"))
        db.close()
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = str(e)
        status = "degraded"
    try:
        from backend.services.ha import redis_health
        rh = redis_health()
        checks["redis"] = rh.get("status", "unknown")
    except Exception as e:
        checks["redis"] = str(e)
    try:
        from backend.api.system_routes import _pipeline_status
        checks["pipeline"] = "online" if _pipeline_status.get("online") else "standby"
        if _pipeline_status.get("last_heartbeat"):
            checks["last_heartbeat"] = _pipeline_status["last_heartbeat"]
    except Exception:
        checks["pipeline"] = "unknown"
    from backend.services.model_health import model_status
    models = model_status()
    checks["models"] = models
    if any(v == "missing" for v in models.values()):
        status = "degraded"
    return {"status": status, "version": "5.0.0", "checks": checks}







