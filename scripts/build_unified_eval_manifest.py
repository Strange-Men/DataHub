#!/usr/bin/env python3
"""Translate governed P2 acceptance IDs into M8.2 Unified Eval labels."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path

try:
    from eval_run_scope import collect_p2_scope_ids, load_run_scope
except ModuleNotFoundError:  # imported as scripts.build_unified_eval_manifest in tests
    from scripts.eval_run_scope import collect_p2_scope_ids, load_run_scope


QUERY_MAP = {
    "unified_p2_only_001": "p2_product_001",
    "unified_mixed_001": "p2_product_001",
    "unified_archived_001": "p2_archive_001",
    "unified_replaced_001": "p2_version_001",
    "unified_conflict_001": "p2_version_001",
    "unified_p1_failure_001": "p2_caption_001",
    "unified_duplicate_001": "p2_product_001",
    "unified_latency_001": "p2_warranty_001",
}


def _strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def build_manifest(source: dict[str, object]) -> dict[str, object]:
    raw_queries = source.get("queries")
    if not isinstance(raw_queries, list):
        raise ValueError("P2 manifest must contain a queries list.")
    by_id = {
        str(item.get("query_id")): item
        for item in raw_queries
        if isinstance(item, dict) and item.get("query_id")
    }
    missing = sorted(set(QUERY_MAP.values()) - set(by_id))
    if missing:
        raise ValueError("P2 manifest is missing required query labels: " + ", ".join(missing))

    entries: list[dict[str, object]] = []
    for unified_id, p2_id in QUERY_MAP.items():
        source_item = by_id[p2_id]
        entry: dict[str, object] = {"query_id": unified_id}
        if unified_id == "unified_archived_001":
            entry.update(
                {
                    "forbidden_p2_knowledge_asset_ids": _strings(
                        source_item.get("expected_knowledge_asset_ids")
                    ),
                    "forbidden_p2_chunk_ids": _strings(
                        source_item.get("expected_chunk_ids")
                    ),
                    "forbidden_p2_asset_ids": _strings(
                        source_item.get("expected_asset_ids")
                    ),
                }
            )
            runtime_query = str(source_item.get("runtime_query", "")).strip()
            if runtime_query:
                entry["runtime_query"] = runtime_query
        else:
            entry.update(
                {
                    "expected_p2_knowledge_asset_ids": _strings(
                        source_item.get("expected_knowledge_asset_ids")
                    ),
                    "expected_p2_chunk_ids": _strings(
                        source_item.get("expected_chunk_ids")
                    ),
                    "expected_p2_asset_ids": _strings(
                        source_item.get("expected_asset_ids")
                    ),
                }
            )
        if p2_id == "p2_version_001":
            entry.update(
                {
                    "forbidden_p2_knowledge_asset_ids": _strings(
                        source_item.get("forbidden_knowledge_asset_ids")
                    ),
                    "forbidden_p2_chunk_ids": _strings(
                        source_item.get("forbidden_chunk_ids")
                    ),
                    "forbidden_p2_asset_ids": _strings(
                        source_item.get("forbidden_asset_ids")
                    ),
                }
            )
        entries.append(entry)

    output: dict[str, object] = {
        "version": "p1-p2-m9.1-unified-runtime-v2",
        "source_trace_id": source.get("trace_id"),
        "generated_at": datetime.now(UTC).isoformat(),
        "queries": entries,
    }
    run_scope = load_run_scope(source)
    if run_scope is not None:
        output["run_scope"] = run_scope
        output["p2_scope_ids"] = sorted(collect_p2_scope_ids(entries))
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="Build ignored Unified Eval runtime labels.")
    parser.add_argument("--p2-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        source = json.loads(args.p2_manifest.read_text(encoding="utf-8"))
        if not isinstance(source, dict):
            raise ValueError("P2 manifest root must be an object.")
        output = build_manifest(source)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(
        json.dumps(
            {
                "success": True,
                "query_count": len(output["queries"]),
                "output": str(args.output),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
