"""Initialize the DataHub database.

Creates all tables defined in db_models.py via Base.metadata.create_all.
Works with both SQLite (local default) and PostgreSQL (production).

Usage:
    python scripts/init_database.py

Environment:
    DATABASE_URL — optional; defaults to SQLite at ../datahub.db
"""

import sys
import os

# Ensure the backend package is importable
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(ROOT_DIR, "backend")
sys.path.insert(0, BACKEND_DIR)

from app.database import engine, Base, check_database_connection, _backend_label  # noqa: E402
from app import db_models  # noqa: E402, F401 — registers all models on Base.metadata


def main() -> None:
    label = _backend_label()
    print(f"Database backend: {label}")

    # Safety: never print the full connection string
    print("Creating tables ...")
    Base.metadata.create_all(bind=engine)

    table_names = sorted(Base.metadata.tables.keys())
    print(f"Tables created: {len(table_names)}")
    for name in table_names:
        print(f"  - {name}")

    print("Checking database connection ...")
    status = check_database_connection()
    print(f"  enabled : {status['enabled']}")
    print(f"  backend : {status['backend']}")
    print(f"  status  : {status['status']}")

    if status["status"] == "ok":
        print("Database initialization complete.")
    else:
        print("Database initialization completed, but connection check returned an error.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
