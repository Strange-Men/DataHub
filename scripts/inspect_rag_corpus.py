#!/usr/bin/env python3
"""Inspect the RAG embeddings corpus for quality diagnosis.

Usage:
  python scripts/inspect_rag_corpus.py
  python scripts/inspect_rag_corpus.py --verbose

Reads DATABASE_URL from the environment.  If the variable is not set,
reports SKIP and exits cleanly — no local DB means no direct inspection.

Reports:
  - total rag_embeddings rows
  - distribution by source_type, modality
  - duplicate / near-duplicate chunk_text patterns
  - suspected pollution entries (harness artifacts, placeholder text)
  - Chinese-content detection
  - embedding_provider / model / dimension distribution

Never prints DATABASE_URL, API keys, or full sensitive content.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from typing import Any


def _is_chinese(text: str) -> bool:
    """Return True if text contains a significant amount of CJK characters."""
    cjk = sum(1 for ch in text if '一' <= ch <= '鿿' or '㐀' <= ch <= '䶿')
    return cjk > 3


def _pollution_score(chunk_text: str, metadata: dict[str, Any]) -> tuple[bool, str]:
    """Check if a chunk looks like test/pollution data.

    Returns (is_polluted, reason).
    """
    text_lower = chunk_text.lower()

    if "manually verified content" in text_lower:
        return True, "harness_manual_cleaning_placeholder"
    if "harness automated" in text_lower:
        return True, "harness_automated_cleaning"
    if _is_chinese(chunk_text) and not _is_chinese(
        metadata.get("question", metadata.get("chunk_text", ""))
    ):
        return True, "chinese_content_in_english_corpus"

    return False, ""


def inspect_corpus(verbose: bool = False) -> dict[str, Any]:
    """Inspect rag_embeddings via direct DB connection."""
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        print("SKIP: DATABASE_URL is not set.")
        print("backend: unknown")
        print("reason: cannot connect to database for direct inspection.")
        print()
        print("next_action:")
        print("  Set DATABASE_URL to inspect the RAG corpus directly,")
        print("  or use online eval to assess corpus quality indirectly:")
        print("    python scripts/run_rag_eval.py --base-url https://datahub-jr8x.onrender.com --top-k 5")
        return {"status": "skipped", "reason": "no DATABASE_URL"}

    backend = "postgresql" if database_url.startswith("postgres") else "sqlite"
    print(f"backend: {backend}")
    print()

    try:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session
        from app.db_models import RagEmbedding
    except ImportError as exc:
        print(f"FAIL: cannot import SQLAlchemy or db_models: {exc}")
        return {"status": "failed", "reason": str(exc)[:200]}

    engine = None
    try:
        connect_args = {"connect_timeout": 10} if backend == "postgresql" else {}
        engine = create_engine(database_url, echo=False, connect_args=connect_args)
        session = Session(engine)
        rows = session.query(RagEmbedding).all()
        total = len(rows)
        print(f"total rag_embeddings rows: {total}")

        if total == 0:
            print("No rows in rag_embeddings — corpus is empty.")
            session.close()
            engine.dispose()
            return {"status": "ok", "total": 0}

        # Distribution by source_type
        source_types = Counter(
            (r.source_type or "unknown") for r in rows
        )
        print()
        print("source_type distribution:")
        for st, cnt in source_types.most_common():
            print(f"  {st}: {cnt}")

        # Distribution by modality
        modalities = Counter(
            (r.modality or "unknown") for r in rows
        )
        print()
        print("modality distribution:")
        for mod, cnt in modalities.most_common():
            print(f"  {mod}: {cnt}")

        # Embedding provider distribution
        providers = Counter(
            (r.embedding_provider or "unknown") for r in rows
        )
        print()
        print("embedding_provider distribution:")
        for p, cnt in providers.most_common():
            print(f"  {p}: {cnt}")

        # Embedding dimension distribution
        dims = Counter(
            (r.embedding_dimension or 0) for r in rows
        )
        print()
        print("embedding_dimension distribution:")
        for d, cnt in dims.most_common():
            print(f"  {d}: {cnt}")

        # Chunk text analysis
        chunk_texts = [r.chunk_text or "" for r in rows]
        duplicate_texts = Counter(chunk_texts)
        repeated = {t: c for t, c in duplicate_texts.items() if c > 1 and t}
        print()
        print(f"unique chunk_text values: {len(set(chunk_texts))}")
        print(f"duplicated chunk_text values: {len(repeated)}")

        if repeated and verbose:
            print()
            print("top duplicated chunk_text (first 80 chars):")
            for text, cnt in sorted(repeated.items(), key=lambda x: -x[1])[:5]:
                preview = text[:80].replace("\n", " | ")
                print(f"  [{cnt}x] {preview}...")

        # Pollution detection
        polluted: list[tuple[str, str, str]] = []
        chinese_count = 0
        for r in rows:
            ct = r.chunk_text or ""
            meta = dict(r.metadata_json) if isinstance(r.metadata_json, dict) else {}
            is_p, reason = _pollution_score(ct, meta)
            if is_p:
                polluted.append((r.id or "?", reason, ct[:80].replace("\n", " | ")))
            if _is_chinese(ct):
                chinese_count += 1

        print()
        print(f"chinese-content entries: {chinese_count}")
        print(f"suspected pollution entries: {len(polluted)}")

        if polluted:
            print()
            print("pollution breakdown:")
            reasons = Counter(r for _, r, _ in polluted)
            for reason, cnt in reasons.most_common():
                print(f"  {reason}: {cnt}")
            if verbose and len(polluted) <= 20:
                print()
                print("pollution details:")
                for rid, reason, preview in polluted:
                    print(f"  [{reason}] id={rid}")
                    print(f"    text={preview}...")

        # Candidate ID overview
        cids = Counter(
            (r.candidate_id or "?") for r in rows
        )
        print()
        print(f"unique candidate_ids: {len(cids)}")

        session.close()
        engine.dispose()

        return {
            "status": "ok",
            "total": total,
            "source_types": dict(source_types),
            "modalities": dict(modalities),
            "providers": dict(providers),
            "dimensions": dict(dims),
            "unique_chunk_texts": len(set(chunk_texts)),
            "duplicate_texts": len(repeated),
            "chinese_content": chinese_count,
            "pollution_count": len(polluted),
            "pollution_breakdown": dict(Counter(r for _, r, _ in polluted)),
        }

    except Exception as exc:
        print(f"FAIL: {exc}")
        if engine:
            engine.dispose()
        return {"status": "failed", "reason": str(exc)[:300]}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inspect the RAG embeddings corpus for quality diagnosis."
    )
    parser.add_argument("--verbose", action="store_true",
                        help="Show detailed pollution and duplicate entries")
    args = parser.parse_args()
    inspect_corpus(verbose=args.verbose)


if __name__ == "__main__":
    main()
