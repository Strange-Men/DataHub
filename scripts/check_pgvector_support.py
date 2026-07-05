#!/usr/bin/env python3
"""Check pgvector extension availability on the configured PostgreSQL database.

Usage:
  python scripts/check_pgvector_support.py

This script reads DATABASE_URL from the environment and checks whether the
pgvector extension is available and can be enabled.

Safe for:
  - Local development (no DATABASE_URL set → graceful SKIP)
  - SQLite backends (graceful SKIP)
  - Render PostgreSQL (performs the actual check)

Never prints the DATABASE_URL value.
"""

from __future__ import annotations

import os
import sys
import textwrap


def _backend_label(database_url: str) -> str:
    """Return a safe backend label (never the connection string)."""
    if database_url.startswith("postgresql") or database_url.startswith("postgres"):
        return "postgresql"
    if database_url.startswith("sqlite"):
        return "sqlite"
    return "unknown"


def main() -> None:
    database_url = os.getenv("DATABASE_URL", "").strip()

    print("pgvector Availability Check")
    print("===========================")
    print()

    if not database_url:
        print("SKIP: DATABASE_URL is not set.")
        print("backend: unknown")
        print("pgvector_available: unknown (no DATABASE_URL)")
        print("extension_create_ok: unknown")
        print()
        print("next_action:")
        print("  Set DATABASE_URL to a Render PostgreSQL connection string")
        print("  or run this check from the Render shell / deployment environment.")
        print("  Example manual SQL:")
        print("    SELECT * FROM pg_available_extensions WHERE name = 'vector';")
        print("    CREATE EXTENSION IF NOT EXISTS vector;")
        sys.exit(0)

    backend = _backend_label(database_url)
    print(f"backend: {backend}")

    if backend != "postgresql":
        print("SKIP: pgvector is only relevant for PostgreSQL.")
        print(f"Current backend is '{backend}', not 'postgresql'.")
        print()
        print("next_action:")
        print("  Deploy to Render with a PostgreSQL DATABASE_URL to check pgvector support.")
        sys.exit(0)

    # PostgreSQL path
    try:
        from sqlalchemy import create_engine, text
    except ImportError:
        print("FAIL: SQLAlchemy is not installed.")
        print("  Install: pip install sqlalchemy")
        sys.exit(1)

    engine = None
    try:
        engine = create_engine(database_url, echo=False, connect_args={"connect_timeout": 10})
        with engine.connect() as conn:
            # Step 1: check availability
            result = conn.execute(
                text("SELECT * FROM pg_available_extensions WHERE name = 'vector';")
            )
            rows = result.fetchall()
            pgvector_available = len(rows) > 0

            if pgvector_available:
                row = rows[0]
                version = row._mapping.get("default_version", "unknown")
                print(f"pgvector_available: true  (default_version: {version})")
            else:
                print("pgvector_available: false")
                print("extension_create_ok: false")
                print()
                print("next_action:")
                print("  pgvector is NOT available on this Render PostgreSQL instance.")
                print("  P1-M21 (Vector RAG Foundation) is BLOCKED.")
                print("  Options:")
                print("    1. Upgrade Render PostgreSQL plan.")
                print("    2. Use an external vector store (ChromaDB, Pinecone free tier).")
                print("    3. Re-evaluate whether vector RAG can be deferred to P2.")
                sys.exit(0 if pgvector_available else 2)

            # Step 2: try to create extension
            try:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
                conn.commit()
                print("extension_create_ok: true")
                print()
                print("next_action:")
                print("  pgvector is available and enabled.")
                print("  Proceed with P1-M21 (Vector RAG Foundation).")
                sys.exit(0)
            except Exception as exc:
                print(f"extension_create_ok: false")
                print(f"  error: {exc}")
                print()
                print("next_action:")
                print("  pgvector is available but CREATE EXTENSION failed.")
                print("  Check database user permissions (superuser or createextenion privilege).")
                print("  Contact Render support or upgrade database plan if needed.")
                sys.exit(3)

    except Exception as exc:
        print(f"FAIL: Could not connect or run pgvector check.")
        print(f"  error: {exc}")
        print(f"  Note: DATABASE_URL value is NOT printed (security).")
        print()
        print("next_action:")
        print("  Verify DATABASE_URL is correct and the database is reachable.")
        print("  Run the following SQL manually on Render PostgreSQL:")
        print("    SELECT * FROM pg_available_extensions WHERE name = 'vector';")
        print("    CREATE EXTENSION IF NOT EXISTS vector;")
        sys.exit(4)
    finally:
        if engine:
            engine.dispose()


if __name__ == "__main__":
    main()
