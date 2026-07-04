"""Database connection and session management.

Uses SQLAlchemy to support:
- SQLite (local default, no DATABASE_URL set)
- PostgreSQL (production, via DATABASE_URL environment variable)

Security:
- Never prints or exposes the full DATABASE_URL.
- check_database_connection() returns only safe status info.
"""

import os
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.engine import Engine


def _build_database_url() -> str:
    """Return the database URL, defaulting to local SQLite when DATABASE_URL is not set."""
    url = os.getenv("DATABASE_URL", "").strip()
    if url:
        return url
    # Default SQLite for local development
    db_path = os.path.join(os.path.dirname(__file__), "..", "..", "datahub.db")
    db_path = os.path.abspath(db_path)
    return f"sqlite:///{db_path}"


DATABASE_URL = _build_database_url()

# ── Engine ──────────────────────────────────────────────────────────────────
# SQLite needs connect_args for thread safety; PostgreSQL does not.
_connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    _connect_args["check_same_thread"] = False

engine: Engine = create_engine(
    DATABASE_URL,
    connect_args=_connect_args,
    echo=False,
    # pool_pre_ping helps detect stale connections for PostgreSQL
    pool_pre_ping=True if DATABASE_URL.startswith("postgresql") else False,
)

# ── Session ─────────────────────────────────────────────────────────────────
SessionLocal: sessionmaker[Session] = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

# ── Base ────────────────────────────────────────────────────────────────────
from sqlalchemy.orm import DeclarativeBase  # noqa: E402


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""
    pass


# ── Dependency ──────────────────────────────────────────────────────────────


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a database session and closes it after use."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Health helper ───────────────────────────────────────────────────────────


def _backend_label() -> str:
    """Return a safe backend label (never the connection string)."""
    if DATABASE_URL.startswith("postgresql") or DATABASE_URL.startswith("postgres"):
        return "postgresql"
    if DATABASE_URL.startswith("sqlite"):
        return "sqlite"
    return "unknown"


def init_database_tables() -> None:
    """Idempotent: create all tables if they don't exist.

    Safe to call multiple times — uses create_all(checkfirst equivalent).
    Does NOT drop existing data.
    Does NOT print DATABASE_URL.
    """
    # Import models so they register on Base.metadata
    import app.db_models as _models  # noqa: F401
    Base.metadata.create_all(bind=engine)


def check_database_connection() -> dict[str, object]:
    """Test that the database is reachable.

    Returns a safe dict suitable for inclusion in the /health response.
    Never leaks the DATABASE_URL, username, password, or host.
    """
    result: dict[str, object] = {
        "enabled": True,
        "backend": _backend_label(),
    }
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        result["status"] = "ok"
    except Exception:
        result["status"] = "error"
    return result
