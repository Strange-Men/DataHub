#!/usr/bin/env python3
"""Safely clean up test/pollution data from the RAG embeddings corpus.

Usage:
  python scripts/cleanup_rag_test_data.py              # dry-run (no changes)
  python scripts/cleanup_rag_test_data.py --apply      # actually delete
  python scripts/cleanup_rag_test_data.py --verbose

PURPOSE:
  Remove clearly identifiable test/harness artifacts from rag_embeddings
  so that eval metrics reflect real knowledge, not placeholder content.

SAFETY:
  - Default DRY-RUN: no rows are deleted unless --apply is passed.
  - Only matches entries with EXPLICIT pollution markers:
      * chunk_text containing "Manually verified content"
      * chunk_text containing "harness automated cleaning"
  - Does NOT delete rows based on candidate_id, batch_id, or source_type alone.
  - No full-table truncation. No unconditional DELETE.

Requires DATABASE_URL in environment (postgresql or sqlite).
If DATABASE_URL is not set, reports SKIP.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from typing import Any


# ── Pollution match rules ────────────────────────────────────────────────
# Each rule is a (name, matcher_fn) pair.
# The matcher receives (chunk_text: str, metadata_json: dict) and returns
# True if the row should be considered for cleanup.


def _match_harness_manual_cleaning(chunk_text: str, _meta: dict) -> bool:
    return "manually verified content" in chunk_text.lower()


def _match_harness_automated(chunk_text: str, _meta: dict) -> bool:
    return "harness automated" in chunk_text.lower()


POLLUTION_RULES: list[tuple[str, Any]] = [
    ("harness_manual_cleaning_placeholder", _match_harness_manual_cleaning),
    ("harness_automated_cleaning_note", _match_harness_automated),
]


def run_cleanup(apply_changes: bool = False, verbose: bool = False) -> dict[str, Any]:
    """Scan rag_embeddings and optionally remove pollution rows."""
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        print("SKIP: DATABASE_URL is not set.")
        print("Cannot connect to database for cleanup.")
        return {"status": "skipped", "reason": "no DATABASE_URL"}

    backend = "postgresql" if database_url.startswith("postgres") else "sqlite"
    mode = "APPLY" if apply_changes else "DRY-RUN"
    print(f"backend: {backend}")
    print(f"mode: {mode}")
    print()

    try:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session
        from app.db_models import RagEmbedding
    except ImportError as exc:
        print(f"FAIL: cannot import: {exc}")
        return {"status": "failed", "reason": str(exc)[:200]}

    engine = None
    try:
        engine = create_engine(database_url, echo=False, connect_args={"connect_timeout": 10})
        session = Session(engine)
        all_rows = session.query(RagEmbedding).all()
        total_before = len(all_rows)

        # Find matches
        matched: list[tuple[Any, str]] = []  # (row, rule_name)
        for row in all_rows:
            ct = row.chunk_text or ""
            meta = dict(row.metadata_json) if isinstance(row.metadata_json, dict) else {}
            for rule_name, rule_fn in POLLUTION_RULES:
                if rule_fn(ct, meta):
                    matched.append((row, rule_name))
                    break  # first match wins

        match_count = len(matched)
        print(f"total rag_embeddings rows: {total_before}")
        print(f"matched for cleanup:      {match_count}")

        # Breakdown by rule
        rule_counts = Counter(name for _, name in matched)
        if rule_counts:
            print()
            print("match breakdown:")
            for name, cnt in rule_counts.most_common():
                print(f"  {name}: {cnt}")

        if match_count == 0:
            print()
            print("No pollution entries found. Nothing to do.")
            session.close()
            engine.dispose()
            return {"status": "ok", "total_before": total_before, "deleted": 0,
                    "breakdown": {}}

        # Show what would be deleted
        if verbose and match_count <= 50:
            print()
            print("matched entries (preview):")
            for row, rule in matched[:20]:
                preview = (row.chunk_text or "")[:80].replace("\n", " | ")
                print(f"  [{rule}] id={row.id}")
                print(f"    text={preview}...")

        if not apply_changes:
            print()
            print("DRY-RUN complete. No rows deleted.")
            print("Pass --apply to actually delete these rows.")
            session.close()
            engine.dispose()
            return {
                "status": "dry_run",
                "total_before": total_before,
                "would_delete": match_count,
                "breakdown": dict(rule_counts),
            }

        # ── APPLY: delete matched rows ──────────────────────────────────
        deleted = 0
        for row, _rule in matched:
            session.delete(row)
            deleted += 1
        session.commit()

        total_after = session.query(RagEmbedding).count()
        session.close()
        engine.dispose()

        print()
        print(f"DELETED: {deleted} rows")
        print(f"remaining: {total_after}")
        print()

        return {
            "status": "applied",
            "total_before": total_before,
            "total_after": total_after,
            "deleted": deleted,
            "breakdown": dict(rule_counts),
        }

    except Exception as exc:
        print(f"FAIL: {exc}")
        if engine:
            engine.dispose()
        return {"status": "failed", "reason": str(exc)[:300]}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Safely clean up test/pollution data from rag_embeddings."
    )
    parser.add_argument("--apply", action="store_true",
                        help="Actually delete matched rows (default: dry-run only)")
    parser.add_argument("--verbose", action="store_true",
                        help="Show matched entry previews")
    args = parser.parse_args()
    run_cleanup(apply_changes=args.apply, verbose=args.verbose)


if __name__ == "__main__":
    main()
