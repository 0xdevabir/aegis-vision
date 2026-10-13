"""
Database engine — PostgreSQL (prod/Render) or SQLite (local zero-setup).

If DATABASE_URL points at unreachable local Postgres, falls back to
data/ai_sss.db so `./run.sh` works without Docker/psql installed.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base

load_dotenv()

logger = logging.getLogger("HumanAnalysis")
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SQLITE = "sqlite:///" + (ROOT / "data" / "ai_sss.db").as_posix()


def _normalize_database_url(url: str) -> str:
    """Render and other cloud Postgres providers require SSL."""
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    if url.startswith("sqlite:"):
        return url

    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))

    host = (parsed.hostname or "").lower()
    needs_ssl = host.endswith(".render.com") or os.getenv("DATABASE_SSL", "").lower() in {"1", "true", "yes"}
    if needs_ssl and "sslmode" not in query:
        query["sslmode"] = "require"

    if query:
        url = urlunparse(parsed._replace(query=urlencode(query)))
    elif needs_ssl:
        url = f"{url}?sslmode=require"

    return url


def _is_local_postgres(url: str) -> bool:
    if not url.startswith("postgresql"):
        return False
    host = (urlparse(url).hostname or "").lower()
    return host in {"localhost", "127.0.0.1", ""}


def _can_connect(url: str) -> bool:
    try:
        args = {}
        kwargs = {}
        if url.startswith("sqlite"):
            args["check_same_thread"] = False
        else:
            if "sslmode=require" in url:
                args["sslmode"] = "require"
            kwargs["pool_pre_ping"] = True
        eng = create_engine(url, connect_args=args, **kwargs)
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        eng.dispose()
        return True
    except Exception:
        return False


def _resolve_database_url() -> str:
    force_sqlite = os.getenv("USE_SQLITE", "").lower() in {"1", "true", "yes"}
    raw = os.getenv("DATABASE_URL", "").strip()

    if force_sqlite or not raw:
        (ROOT / "data").mkdir(parents=True, exist_ok=True)
        return DEFAULT_SQLITE

    url = _normalize_database_url(raw)

    if url.startswith("sqlite"):
        (ROOT / "data").mkdir(parents=True, exist_ok=True)
        return url

    if _can_connect(url):
        return url

    # Local Postgres missing (role/db not created, Docker down) → SQLite
    if _is_local_postgres(url) or os.getenv("ALLOW_SQLITE_FALLBACK", "true").lower() in {"1", "true", "yes"}:
        (ROOT / "data").mkdir(parents=True, exist_ok=True)
        logger.warning(
            "Database unreachable (%s) — falling back to SQLite at data/ai_sss.db",
            urlparse(url).hostname or url[:40],
        )
        return DEFAULT_SQLITE

    return url


DATABASE_URL = _resolve_database_url()

_connect_args = {}
_engine_kwargs = {"pool_pre_ping": True}

if DATABASE_URL.startswith("sqlite"):
    _connect_args["check_same_thread"] = False
    # SQLite does not support pool_size / max_overflow the same way
    engine = create_engine(
        DATABASE_URL,
        connect_args=_connect_args,
        pool_pre_ping=True,
    )
else:
    if "sslmode=require" in DATABASE_URL:
        _connect_args["sslmode"] = "require"
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_recycle=280,
        pool_size=5,
        max_overflow=2,
        connect_args=_connect_args,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def init_db():
    from backend.models import (
        user, face_encoding, evidence, audit_log, known_person, person_image,
        camera, alert, vehicle, config_entry, incident, custody, recording, calibration, event,
    )
    Base.metadata.create_all(bind=engine)
    _ensure_columns()


# (table, column, DDL type) — additive changes until Alembic baselines exist.
_ADDITIVE_COLUMNS = [
    ("alerts", "review_status", "VARCHAR(12) NOT NULL DEFAULT 'pending'"),
    ("alerts", "reviewed_by", "INTEGER"),
    ("alerts", "reviewed_at", "TIMESTAMP"),
    ("alerts", "review_note", "TEXT"),
    ("cameras", "geometry", "TEXT"),
    ("cameras", "geometry_updated_at", "TIMESTAMP"),
    ("face_encodings", "image_id", "INTEGER"),
    ("users", "phone", "VARCHAR(30)"),
    ("users", "failed_attempts", "INTEGER NOT NULL DEFAULT 0"),
    ("users", "locked_until", "TIMESTAMP"),
    ("alerts", "escalated_at", "TIMESTAMP"),
    ("cameras", "heading", "FLOAT"),
    ("cameras", "fov", "FLOAT"),
    ("cameras", "range_m", "FLOAT"),
]


def _ensure_columns():
    from sqlalchemy import inspect
    insp = inspect(engine)
    for table, col, ddl in _ADDITIVE_COLUMNS:
        if table not in insp.get_table_names():
            continue
        if col in {c["name"] for c in insp.get_columns(table)}:
            continue
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}"))
        logger.info("Added column %s.%s", table, col)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
