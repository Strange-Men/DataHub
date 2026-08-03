"""Explicit, fail-closed Alembic status and safe upgrade CLI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.migration_adoption import (  # noqa: E402
    MigrationAdoptionError,
    adopt_or_upgrade,
)
from app.migration_status import check_migration_status  # noqa: E402


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage DataHub Alembic migrations.")
    parser.add_argument(
        "command",
        choices=("status", "upgrade", "adopt"),
        help="status is read-only; upgrade/adopt use the same safe adoption workflow.",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="Optional override; prefer DATABASE_URL to avoid shell history exposure.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "status":
            status = check_migration_status(args.database_url)
            print(json.dumps(status.to_dict(), sort_keys=True))
            return 0 if status.ready else 1
        result = adopt_or_upgrade(args.database_url)
    except MigrationAdoptionError:
        print("migration refused: MIGRATION_SCHEMA_REFUSED", file=sys.stderr)
        return 2
    except Exception:
        print("migration failed: MIGRATION_OPERATION_FAILED", file=sys.stderr)
        return 3
    print(
        json.dumps(
            {
                "action": result.action,
                "revision": result.revision,
                "schema_matches_baseline": result.schema_matches_baseline,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
