"""Read-only P1 legacy JSON versus database reconciliation command."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Read-only reconciliation (default).")
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=ROOT / ".local-data" / "p1-r2" / "reports",
    )
    parser.add_argument("--database-url-env", default="DATABASE_URL")
    parser.add_argument(
        "--legacy-storage-root",
        type=Path,
        default=ROOT / "backend" / "storage",
    )
    return parser


def _configure_database(variable_name: str) -> None:
    value = os.environ.get(variable_name)
    if not value:
        raise RuntimeError("DATABASE_URL_ENV_MISSING")
    os.environ["DATABASE_URL"] = value


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        _configure_database(args.database_url_env)
        from app.database import SessionLocal
        from app.p1_database_inventory import load_database_inventory
        from app.p1_legacy_storage import load_legacy_inventory
        from app.p1_reconciliation_models import reconcile

        legacy = load_legacy_inventory(args.legacy_storage_root)
        with SessionLocal() as db:
            database = load_database_inventory(db)
        result = reconcile(legacy, database)
        report = result.safe_report()
        report["mode"] = "check"
        report["generated_at"] = datetime.now(UTC).isoformat()
        report["legacy_manifest"] = {
            "file_count": legacy.file_count,
            "byte_count": legacy.byte_count,
            "aggregate_hash": legacy.aggregate_hash,
        }
        report["database_manifest"] = {"aggregate_hash": database.aggregate_hash}
        args.report_dir.mkdir(parents=True, exist_ok=True)
        output = args.report_dir / "p1-reconciliation.json"
        output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps({"counts": result.counts, "report": str(output)}, sort_keys=True))
        return 2 if any(result.blockers.values()) else 0
    except Exception as exc:
        code = str(exc) if str(exc).isupper() else "RECONCILIATION_FAILED"
        print(json.dumps({"error": code}, sort_keys=True), file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
