"""Public-API smoke gate for the M8.3 CustomerOpsAgent opt-in contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
from typing import Any
from urllib import error, request
from uuid import uuid4


def _post(base_url: str, path: str, payload: dict[str, object], timeout: float) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    http_request = request.Request(
        f"{base_url.rstrip('/')}{path}",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-DataHub-Client": "CustomerOpsAgent",
        },
    )
    try:
        with request.urlopen(http_request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8"))
        except Exception:
            detail = {"status": exc.code}
        raise RuntimeError(f"http_{exc.code}:{_safe_error(detail)}") from None
    except Exception as exc:
        raise RuntimeError(f"request_failed:{type(exc).__name__}") from None


def _safe_error(value: object) -> str:
    if isinstance(value, dict):
        error_data = value.get("error")
        if isinstance(error_data, dict):
            code = str(error_data.get("code", "request_error"))
            return "".join(ch for ch in code if ch.isalnum() or ch in "_-:")[:120]
    return "request_error"


def _load_cases(manifest_path: Path, sample_path: Path) -> tuple[dict[str, object], dict[str, object]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    sample = json.loads(sample_path.read_text(encoding="utf-8"))
    queries = {str(item["id"]): item for item in sample.get("queries", [])}
    active: dict[str, object] | None = None
    archived: dict[str, object] | None = None
    for entry in manifest.get("queries", []):
        query_id = str(entry.get("query_id", ""))
        sample_entry = queries.get(query_id, {})
        runtime_query = entry.get("runtime_query") or sample_entry.get("query")
        merged = {**entry, "query": runtime_query, "query_id": query_id}
        if entry.get("should_be_archived") and runtime_query:
            archived = merged
        elif (
            active is None
            and entry.get("should_return_results")
            and entry.get("expected_knowledge_asset_ids")
            and runtime_query
        ):
            active = merged
    if active is None or archived is None:
        raise RuntimeError("manifest_missing_active_or_archived_case")
    return active, archived


def _data(response: dict[str, Any]) -> dict[str, Any]:
    data = response.get("data")
    if not response.get("success") or not isinstance(data, dict):
        raise RuntimeError("invalid_api_envelope")
    return data


def _walk_keys(value: object) -> list[str]:
    keys: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            keys.append(str(key).lower())
            keys.extend(_walk_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.extend(_walk_keys(child))
    return keys


def _ids(results: list[dict[str, Any]], field: str) -> set[str]:
    return {str(item[field]) for item in results if item.get(field)}


def run(args: argparse.Namespace) -> dict[str, object]:
    active, archived = _load_cases(args.expected_manifest, args.sample_file)
    trace = f"agent-opt-in-smoke-{time.strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:6]}"
    query = str(active["query"])
    common = {"query": query, "top_k": args.top_k, "request_id": trace}

    legacy = _data(
        _post(
            args.base_url,
            "/api/customer-ops-agent/retrieve",
            {"query": query, "top_k": args.top_k},
            args.timeout,
        )
    )
    default_v2 = _data(
        _post(
            args.base_url,
            "/api/v2/customer-ops-agent/retrieve",
            common,
            args.timeout,
        )
    )
    opt_in = _data(
        _post(
            args.base_url,
            "/api/v2/customer-ops-agent/retrieve",
            {**common, "retrieval_strategy": "unified"},
            args.timeout,
        )
    )

    failures: list[str] = []
    if not str(legacy.get("retrieval_mode", "")).startswith("customerops_"):
        failures.append("legacy_mode_invalid")
    if "unified" in str(legacy.get("retrieval_mode", "")):
        failures.append("legacy_endpoint_switched")
    if default_v2.get("actual_retrieval_strategy") != "p1":
        failures.append("v2_default_not_p1")
    if "unified" in str(default_v2.get("retrieval_mode", "")):
        failures.append("v2_default_mode_changed")

    opt_results = [item for item in opt_in.get("results", []) if isinstance(item, dict)]
    source_indexes = sorted({str(item.get("source_index")) for item in opt_results})
    if args.expect_opt_in_active:
        if opt_in.get("actual_retrieval_strategy") != "unified":
            failures.append("explicit_opt_in_not_active")
        if opt_in.get("retrieval_mode") != "customerops_unified_retrieval":
            failures.append("active_mode_invalid")
        if opt_in.get("fallback_used"):
            failures.append("active_unified_unexpected_fallback")
        if source_indexes != ["p1", "p2"]:
            failures.append("active_unified_missing_source")
        if any(not item.get("source_trace") for item in opt_results):
            failures.append("source_trace_incomplete")
    else:
        if opt_in.get("actual_retrieval_strategy") != "p1":
            failures.append("disabled_opt_in_not_p1")
        if not opt_in.get("fallback_used"):
            failures.append("disabled_opt_in_missing_fallback")
        if opt_in.get("fallback_reason") != "customerops_unified_retrieval_disabled":
            failures.append("disabled_opt_in_reason_invalid")

    archived_leakage = 0
    archived_mode: str | None = None
    if args.expect_opt_in_active:
        archived_data = _data(
            _post(
                args.base_url,
                "/api/v2/customer-ops-agent/retrieve",
                {
                    "query": str(archived["query"]),
                    "top_k": args.top_k,
                    "retrieval_strategy": "unified",
                    "request_id": f"{trace}-archive",
                },
                args.timeout,
            )
        )
        archived_mode = str(archived_data.get("retrieval_mode"))
        archived_results = [
            item for item in archived_data.get("results", []) if isinstance(item, dict)
        ]
        forbidden_knowledge = set(
            map(str, archived.get("expected_knowledge_asset_ids", []))
        ) | set(map(str, archived.get("forbidden_knowledge_asset_ids", [])))
        forbidden_assets = set(map(str, archived.get("expected_asset_ids", []))) | set(
            map(str, archived.get("forbidden_asset_ids", []))
        )
        forbidden_chunks = set(map(str, archived.get("expected_chunk_ids", []))) | set(
            map(str, archived.get("forbidden_chunk_ids", []))
        )
        archived_leakage = len(
            forbidden_knowledge & _ids(archived_results, "knowledge_asset_id")
        ) + len(forbidden_assets & _ids(archived_results, "asset_id")) + len(
            forbidden_chunks & _ids(archived_results, "chunk_id")
        )
        if archived_leakage:
            failures.append("archived_content_leaked")

    response_keys = set(_walk_keys({"legacy": legacy, "default": default_v2, "opt_in": opt_in}))
    if {"embedding", "vector", "api_key", "database_url"} & response_keys:
        failures.append("sensitive_or_vector_field_exposed")

    summary: dict[str, object] = {
        "trace_id": trace,
        "expected_opt_in_active": args.expect_opt_in_active,
        "legacy_retrieval_mode": legacy.get("retrieval_mode"),
        "default_actual_strategy": default_v2.get("actual_retrieval_strategy"),
        "default_retrieval_mode": default_v2.get("retrieval_mode"),
        "opt_in_actual_strategy": opt_in.get("actual_retrieval_strategy"),
        "opt_in_retrieval_mode": opt_in.get("retrieval_mode"),
        "opt_in_fallback_used": opt_in.get("fallback_used"),
        "opt_in_fallback_reason": opt_in.get("fallback_reason"),
        "opt_in_source_indexes": source_indexes,
        "opt_in_result_count": len(opt_results),
        "archived_query_mode": archived_mode,
        "archived_leakage_count": archived_leakage,
        "failures": failures,
        "passed": not failures,
    }
    if args.verbose:
        summary["selected_ids"] = {
            "knowledge_asset_ids": sorted(_ids(opt_results, "knowledge_asset_id")),
            "asset_ids": sorted(_ids(opt_results, "asset_id")),
            "chunk_ids": sorted(_ids(opt_results, "chunk_id")),
        }
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--expected-manifest", type=Path, required=True)
    parser.add_argument(
        "--sample-file",
        type=Path,
        default=Path("samples/p2_rag_eval_queries.json"),
    )
    parser.add_argument("--expect-opt-in-active", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def main() -> int:
    try:
        summary = run(parse_args())
    except Exception as exc:
        summary = {
            "passed": False,
            "failures": [f"smoke_error:{type(exc).__name__}"],
        }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary.get("passed") else 1


if __name__ == "__main__":
    sys.exit(main())
