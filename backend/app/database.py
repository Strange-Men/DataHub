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

    Also attempts to enable pgvector extension when on PostgreSQL (P1-M21.1).
    Failure is silent — the extension may not be available on all deployments.
    """
    # Import models so they register on Base.metadata
    import app.db_models as _models  # noqa: F401
    Base.metadata.create_all(bind=engine)

    # Try to enable pgvector — safe no-op on SQLite, graceful failure on
    # PostgreSQL without the extension available (P1-M21.1).
    try:
        ensure_pgvector_extension()
    except Exception:
        pass


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


# ── pgvector helpers (P1-M21) ────────────────────────────────────────────────


def check_pgvector_available() -> dict[str, object]:
    """Check whether the pgvector extension is available on the connected database.

    Safe for all backends:
    - SQLite: returns available=false gracefully (no error).
    - PostgreSQL without pgvector: returns available=false.
    - PostgreSQL with pgvector: returns available=true.

    Never leaks the DATABASE_URL, username, password, or host.
    Never raises — errors are captured and returned in the dict.
    """
    result: dict[str, object] = {
        "pgvector_available": False,
        "backend": _backend_label(),
    }

    if _backend_label() != "postgresql":
        result["pgvector_available"] = False
        result["reason"] = "pgvector is only relevant for PostgreSQL."
        return result

    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT * FROM pg_available_extensions WHERE name = 'vector';")
            ).fetchall()
            available = len(rows) > 0
            result["pgvector_available"] = available
            if available and rows:
                row = rows[0]
                version = row._mapping.get("default_version", "unknown")
                result["default_version"] = str(version)
    except Exception as exc:
        result["pgvector_available"] = False
        result["error"] = str(exc)[:200]

    return result


def ensure_pgvector_extension() -> dict[str, object]:
    """Try to enable the pgvector extension on the connected database.

    Safe for all backends:
    - SQLite: skip gracefully.
    - PostgreSQL: execute CREATE EXTENSION IF NOT EXISTS vector.
    - Errors are captured and returned — never raised to the caller.

    Returns a dict with:
    - extension_create_ok: bool
    - backend: str
    - error: str (only on failure)

    Never leaks the DATABASE_URL, username, password, or host.
    """
    result: dict[str, object] = {
        "extension_create_ok": False,
        "backend": _backend_label(),
    }

    if _backend_label() != "postgresql":
        result["extension_create_ok"] = False
        result["reason"] = "pgvector extension is only relevant for PostgreSQL."
        return result

    try:
        with engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
            conn.commit()
        result["extension_create_ok"] = True
    except Exception as exc:
        result["extension_create_ok"] = False
        result["error"] = str(exc)[:200]

    return result
