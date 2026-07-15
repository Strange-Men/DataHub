#!/usr/bin/env python3
"""Evaluate P1 control versus Unified Retrieval candidate in shadow mode.

Keyword metrics are explicitly proxy evidence. Formal recall and MRR are
reported only when --expected-manifest supplies exact runtime identifiers.
The runner calls only the versioned Unified Retrieval management API and never
prints vectors, credentials, or internal exception details.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import statistics
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_EVAL_FILE = ROOT_DIR / "samples" / "unified_retrieval_eval_queries.json"

_EXPECTED_ID_FIELDS = (
    "expected_p1_candidate_ids",
    "expected_p1_chunk_ids",
    "expected_p2_knowledge_asset_ids",
    "expected_p2_chunk_ids",
    "expected_p2_asset_ids",
)
_FORBIDDEN_ID_FIELDS = (
    "forbidden_p1_candidate_ids",
    "forbidden_p1_chunk_ids",
    "forbidden_p2_knowledge_asset_ids",
    "forbidden_p2_chunk_ids",
    "forbidden_p2_asset_ids",
)
_ALL_ID_FIELDS = _EXPECTED_ID_FIELDS + _FORBIDDEN_ID_FIELDS


def _post_json(
    url: str, payload: dict[str, object], timeout: float
) -> tuple[int, dict[str, Any]]:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return int(response.status), json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = {"error": "non_json_http_error"}
        return int(exc.code), parsed


def _result_text(results: list[dict[str, Any]]) -> str:
    return "\n".join(
        str(
            item.get(
                "evidence_text", item.get("chunk_text", item.get("content", ""))
            )
        )
        for item in results
    ).lower()


def keyword_evidence_rate(
    results: list[dict[str, Any]], expected_terms: list[str]
) -> tuple[float | None, list[str]]:
    """Return expected-term coverage as a proxy, never formal recall."""
    if not expected_terms:
        return None, []
    text = _result_text(results)
    matched = [term for term in expected_terms if term.lower() in text]
    return len(matched) / len(expected_terms), matched


def normalize_source(result: dict[str, Any]) -> str | None:
    raw = str(result.get("source_index") or result.get("source_type") or "").lower()
    if "p2" in raw or result.get("knowledge_asset_id"):
        return "p2"
    if "p1" in raw or "customerops" in raw or result.get("candidate_id"):
        return "p1"
    return None


def _expected_exact_ids(item: dict[str, Any]) -> set[str]:
    """Build route-aware canonical labels without mixing P2 identity grains."""
    expected: set[str] = set()
    p1_candidates = list(item.get("expected_p1_candidate_ids", []))
    p1_chunks = list(item.get("expected_p1_chunk_ids", []))
    for value in p1_candidates or p1_chunks:
        grain = "candidate" if p1_candidates else "chunk"
        expected.add(f"p1:{grain}:{value}")

    p2_knowledge = list(item.get("expected_p2_knowledge_asset_ids", []))
    p2_chunks = list(item.get("expected_p2_chunk_ids", []))
    p2_assets = list(item.get("expected_p2_asset_ids", []))
    selected = p2_knowledge or p2_chunks or p2_assets
    grain = "knowledge_asset" if p2_knowledge else "chunk" if p2_chunks else "asset"
    expected.update(f"p2:{grain}:{value}" for value in selected)
    return expected


def _result_exact_ids(result: dict[str, Any]) -> set[str]:
    source = normalize_source(result)
    identifiers: set[str] = set()
    if source == "p1":
        if result.get("candidate_id"):
            identifiers.add(f"p1:candidate:{result['candidate_id']}")
        if result.get("chunk_id"):
            identifiers.add(f"p1:chunk:{result['chunk_id']}")
    elif source == "p2":
        if result.get("knowledge_asset_id"):
            identifiers.add(f"p2:knowledge_asset:{result['knowledge_asset_id']}")
        if result.get("chunk_id"):
            identifiers.add(f"p2:chunk:{result['chunk_id']}")
        if result.get("asset_id"):
            identifiers.add(f"p2:asset:{result['asset_id']}")
    return identifiers


def exact_recall_at_k(
    results: list[dict[str, Any]], item: dict[str, Any], top_k: int
) -> float | None:
    expected = _expected_exact_ids(item)
    if not expected:
        return None
    returned: set[str] = set()
    for result in results[:top_k]:
        returned.update(_result_exact_ids(result))
    return len(expected & returned) / len(expected)


def exact_reciprocal_rank_at_k(
    results: list[dict[str, Any]], item: dict[str, Any], top_k: int
) -> float | None:
    expected = _expected_exact_ids(item)
    if not expected:
        return None
    for rank, result in enumerate(results[:top_k], start=1):
        if expected & _result_exact_ids(result):
            return 1.0 / rank
    return 0.0


def _forbidden_exact_ids(item: dict[str, Any]) -> set[str]:
    forbidden: set[str] = set()
    mappings = (
        ("forbidden_p1_candidate_ids", "p1:candidate"),
        ("forbidden_p1_chunk_ids", "p1:chunk"),
        ("forbidden_p2_knowledge_asset_ids", "p2:knowledge_asset"),
        ("forbidden_p2_chunk_ids", "p2:chunk"),
        ("forbidden_p2_asset_ids", "p2:asset"),
    )
    for field, prefix in mappings:
        forbidden.update(f"{prefix}:{value}" for value in item.get(field, []))
    return forbidden


def archived_leakage(
    results: list[dict[str, Any]], item: dict[str, Any]
) -> list[str]:
    forbidden = _forbidden_exact_ids(item)
    if not forbidden:
        return []
    leaked: set[str] = set()
    for result in results:
        leaked.update(forbidden & _result_exact_ids(result))
    return sorted(leaked)


def duplicate_asset_fraction(results: list[dict[str, Any]]) -> float:
    asset_ids = [str(item.get("asset_id")) for item in results if item.get("asset_id")]
    if not asset_ids:
        return 0.0
    counts: dict[str, int] = {}
    for asset_id in asset_ids:
        counts[asset_id] = counts.get(asset_id, 0) + 1
    return sum(max(0, count - 1) for count in counts.values()) / len(asset_ids)


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(fraction * len(ordered)) - 1)
    return ordered[index]


def _latency(data: dict[str, Any]) -> tuple[float, dict[str, float]]:
    raw = data.get("latency")
    if raw is None:
        raw = data.get("latency_ms", {})
    breakdown: dict[str, float] = {}
    if isinstance(raw, dict):
        aliases = {
            "p1": ("p1", "p1_ms", "p1_latency_ms"),
            "p2": ("p2", "p2_ms", "p2_latency_ms"),
            "fusion": ("fusion", "fusion_ms", "fusion_latency_ms"),
        }
        for name, keys in aliases.items():
            for key in keys:
                if raw.get(key) is not None:
                    breakdown[name] = float(raw[key] or 0.0)
                    break
        total = raw.get("total", raw.get("total_ms", raw.get("latency_ms", 0.0)))
    else:
        total = raw if isinstance(raw, (int, float)) else data.get("latency_ms", 0.0)
    return float(total or 0.0), breakdown


def _fallback(data: dict[str, Any]) -> tuple[bool, str | None]:
    raw = data.get("fallback")
    if isinstance(raw, dict):
        used = bool(
            raw.get("used", raw.get("fallback_used", data.get("fallback_used", False)))
        )
        reason = raw.get(
            "reason", raw.get("fallback_reason", data.get("fallback_reason"))
        )
    else:
        used = bool(data.get("fallback_used", raw if isinstance(raw, bool) else False))
        reason = data.get("fallback_reason")
    return used, str(reason) if reason else None


def _string_list(value: object, *, field: str, query_id: str) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise ValueError(
            f"Manifest query '{query_id}' field '{field}' must be a list of non-empty strings."
        )
    return list(dict.fromkeys(item.strip() for item in value))


def load_expected_manifest(path: Path) -> dict[str, dict[str, object]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries = payload.get("queries") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        raise ValueError("Expected manifest must contain a 'queries' list.")
    manifest: dict[str, dict[str, object]] = {}
    for raw in entries:
        if not isinstance(raw, dict):
            raise ValueError("Every expected-manifest query must be an object.")
        query_id = str(raw.get("query_id", "")).strip()
        if not query_id:
            raise ValueError("Every expected-manifest query requires query_id.")
        if query_id in manifest:
            raise ValueError(f"Duplicate expected-manifest query_id: {query_id}")
        normalized: dict[str, object] = {}
        for field in _ALL_ID_FIELDS:
            if field in raw:
                normalized[field] = _string_list(
                    raw[field], field=field, query_id=query_id
                )
        if "expected_keywords" in raw:
            normalized["expected_terms"] = _string_list(
                raw["expected_keywords"],
                field="expected_keywords",
                query_id=query_id,
            )
        runtime_query = str(raw.get("runtime_query", "")).strip()
        if runtime_query:
            normalized["query"] = runtime_query
        manifest[query_id] = normalized
    return manifest


def apply_expected_manifest(
    queries: list[dict[str, Any]], manifest: dict[str, dict[str, object]]
) -> list[dict[str, Any]]:
    query_ids = {str(item.get("id", "")).strip() for item in queries}
    if "" in query_ids or len(query_ids) != len(queries):
        raise ValueError("Eval queries must have unique non-empty ids.")
    unknown = sorted(set(manifest) - query_ids)
    if unknown:
        raise ValueError(f"Expected manifest has unknown query ids: {', '.join(unknown)}")
    merged: list[dict[str, Any]] = []
    for item in queries:
        copy = dict(item)
        copy.update(manifest.get(str(item["id"]), {}))
        merged.append(copy)
    return merged


def _load_queries(eval_file: Path, expected_manifest: Path | None) -> list[dict[str, Any]]:
    payload = json.loads(eval_file.read_text(encoding="utf-8"))
    queries = payload.get("queries") if isinstance(payload, dict) else None
    if not isinstance(queries, list) or not queries:
        raise ValueError("Unified eval file must contain a non-empty 'queries' list.")
    normalized = [dict(item) for item in queries if isinstance(item, dict)]
    if len(normalized) != len(queries):
        raise ValueError("Every unified eval query must be an object.")
    query_ids = [str(item.get("id", "")).strip() for item in normalized]
    if any(not query_id for query_id in query_ids) or len(set(query_ids)) != len(
        query_ids
    ):
        raise ValueError("Unified eval queries must have unique non-empty ids.")
    if expected_manifest is not None:
        normalized = apply_expected_manifest(
            normalized, load_expected_manifest(expected_manifest)
        )
    return normalized


def run_eval(
    *,
    base_url: str,
    top_k: int,
    timeout: float,
    verbose: bool,
    eval_file: Path = DEFAULT_EVAL_FILE,
    expected_manifest: Path | None = None,
) -> dict[str, Any]:
    queries = _load_queries(eval_file, expected_manifest)
    endpoint = base_url.rstrip("/") + "/api/v2/retrieval/search"

    control_keyword_rates: list[float] = []
    candidate_keyword_rates: list[float] = []
    control_keyword_hits: list[bool] = []
    candidate_keyword_hits: list[bool] = []
    keyword_not_below: list[bool] = []
    control_recalls: list[float] = []
    candidate_recalls: list[float] = []
    control_rrs: list[float] = []
    candidate_rrs: list[float] = []
    exact_not_below: list[bool] = []
    source_coverages: list[float] = []
    duplicate_rates: list[float] = []
    latencies: list[float] = []
    branch_latencies: dict[str, list[float]] = {"p1": [], "p2": [], "fusion": []}
    source_distribution: dict[str, int] = {"p1": 0, "p2": 0, "unknown": 0}
    fallback_reasons: dict[str, int] = {}
    fallback_count = 0
    archived_leakage_count = 0
    archived_labeled_query_count = 0
    no_answer_result_count = 0
    shadow_response_count = 0
    shadow_contract_violation_count = 0
    branch_status_counts: dict[str, int] = {}
    request_failure_count = 0
    failed_queries: list[dict[str, object]] = []

    for item in queries:
        query_id = str(item.get("id", "")).strip()
        query = str(item.get("query", "")).strip()
        request_payload: dict[str, object] = {
            "query": query,
            "top_k": top_k,
            "sources": item.get("sources", "all"),
            "fusion_enabled": bool(item.get("fusion_enabled", True)),
            "shadow_mode": bool(item.get("shadow_mode", True)),
            "debug": bool(item.get("debug", verbose)),
            "request_id": f"unified-eval-{query_id}",
        }
        try:
            status, envelope = _post_json(endpoint, request_payload, timeout)
        except (URLError, TimeoutError, OSError) as exc:
            request_failure_count += 1
            failed_queries.append({"query_id": query_id, "reason": type(exc).__name__})
            continue
        data = envelope.get("data", {}) if isinstance(envelope, dict) else {}
        if status != 200 or not isinstance(data, dict):
            request_failure_count += 1
            failed_queries.append(
                {"query_id": query_id, "status": status, "reason": "request_failed"}
            )
            continue
        control = data.get("results", [])
        candidate = data.get("candidate_results", control)
        if not isinstance(control, list) or not isinstance(candidate, list):
            request_failure_count += 1
            failed_queries.append(
                {"query_id": query_id, "reason": "invalid_results_contract"}
            )
            continue
        control_results = [dict(result) for result in control[:top_k] if isinstance(result, dict)]
        candidate_results = [dict(result) for result in candidate[:top_k] if isinstance(result, dict)]
        is_shadow = data.get("retrieval_mode") == "shadow_control"
        if is_shadow:
            shadow_response_count += 1
        if request_payload["shadow_mode"] and not is_shadow:
            shadow_contract_violation_count += 1
            failed_queries.append(
                {"query_id": query_id, "reason": "shadow_mode_not_enforced"}
            )
        declared_control = data.get("control_results")
        if is_shadow and (
            not isinstance(declared_control, list) or declared_control != control
        ):
            shadow_contract_violation_count += 1
            failed_queries.append(
                {"query_id": query_id, "reason": "shadow_control_mismatch"}
            )
        source_modes = data.get("source_modes")
        if not isinstance(source_modes, dict):
            shadow_contract_violation_count += 1
            failed_queries.append(
                {"query_id": query_id, "reason": "source_modes_invalid"}
            )
        else:
            for source, mode in source_modes.items():
                status_name = str(mode.get("status", "unknown")) if isinstance(mode, dict) else "invalid"
                key = f"{source}:{status_name}"
                branch_status_counts[key] = branch_status_counts.get(key, 0) + 1
        if is_shadow and not isinstance(data.get("shadow_comparison"), dict):
            shadow_contract_violation_count += 1
            failed_queries.append(
                {"query_id": query_id, "reason": "shadow_comparison_missing"}
            )

        expected_terms = list(item.get("expected_terms", []))
        control_terms = list(item.get("control_expected_terms", expected_terms))
        candidate_terms = list(item.get("candidate_expected_terms", expected_terms))
        control_rate, control_matched = keyword_evidence_rate(
            control_results, control_terms
        )
        candidate_rate, candidate_matched = keyword_evidence_rate(
            candidate_results, candidate_terms
        )
        if control_rate is not None and candidate_rate is not None:
            control_keyword_rates.append(control_rate)
            candidate_keyword_rates.append(candidate_rate)
            control_keyword_hits.append(control_rate > 0)
            candidate_keyword_hits.append(candidate_rate > 0)
            not_below = candidate_rate >= control_rate
            keyword_not_below.append(not_below)
            if not not_below:
                failed_queries.append(
                    {"query_id": query_id, "reason": "candidate_keyword_below_control"}
                )

        control_recall = exact_recall_at_k(control_results, item, top_k)
        candidate_recall = exact_recall_at_k(candidate_results, item, top_k)
        control_rr = exact_reciprocal_rank_at_k(control_results, item, top_k)
        candidate_rr = exact_reciprocal_rank_at_k(candidate_results, item, top_k)
        if control_recall is not None and candidate_recall is not None:
            control_recalls.append(control_recall)
            candidate_recalls.append(candidate_recall)
            control_rrs.append(float(control_rr or 0.0))
            candidate_rrs.append(float(candidate_rr or 0.0))
            not_below = candidate_recall >= control_recall
            exact_not_below.append(not_below)
            if not not_below:
                failed_queries.append(
                    {"query_id": query_id, "reason": "candidate_exact_recall_below_control"}
                )

        expected_sources = {str(value).lower() for value in item.get("expected_sources", [])}
        returned_sources = {
            source
            for result in candidate_results
            if (source := normalize_source(result)) is not None
        }
        for result in candidate_results:
            source = normalize_source(result) or "unknown"
            source_distribution[source] = source_distribution.get(source, 0) + 1
        if expected_sources:
            coverage = len(expected_sources & returned_sources) / len(expected_sources)
            source_coverages.append(coverage)

        forbidden = _forbidden_exact_ids(item)
        if forbidden:
            archived_labeled_query_count += 1
        leaked = archived_leakage(candidate_results, item)
        archived_leakage_count += len(leaked)
        if leaked:
            failed_queries.append(
                {"query_id": query_id, "reason": "archived_leakage", "ids": leaked}
            )

        if item.get("expect_no_hit"):
            no_answer_result_count += len(candidate_results)

        duplicate_rates.append(duplicate_asset_fraction(candidate_results))
        latency, breakdown = _latency(data)
        latencies.append(latency)
        for branch, value in breakdown.items():
            branch_latencies[branch].append(value)
        fallback_used, fallback_reason = _fallback(data)
        if fallback_used:
            fallback_count += 1
            reason = fallback_reason or "unspecified"
            fallback_reasons[reason] = fallback_reasons.get(reason, 0) + 1

        if verbose:
            print(
                f"[{query_id}] sources={request_payload['sources']} "
                f"control={len(control_results)} candidate={len(candidate_results)} "
                f"control_keyword={control_rate if control_rate is not None else 'n/a'} "
                f"candidate_keyword={candidate_rate if candidate_rate is not None else 'n/a'} "
                f"control_exact={control_recall if control_recall is not None else 'n/a'} "
                f"candidate_exact={candidate_recall if candidate_recall is not None else 'n/a'} "
                f"sources_seen={sorted(returned_sources)} fallback={fallback_used} "
                f"latency_ms={latency:.3f} leaked={leaked}"
            )
            print(
                f"  control_terms={control_matched} candidate_terms={candidate_matched} "
                f"retrieval_id={data.get('retrieval_id')} "
                f"control_mode={data.get('control_mode')} "
                f"candidate_mode={data.get('candidate_mode')}"
            )

    total = len(queries)
    completed = total - request_failure_count
    keyword_gate = all(keyword_not_below) if keyword_not_below else None
    exact_gate = all(exact_not_below) if exact_not_below else None
    candidate_not_below = (
        (keyword_gate is not False) and (exact_gate is not False)
    )
    summary: dict[str, Any] = {
        "total_queries": total,
        "completed_queries": completed,
        f"control_keyword_hit_rate@{top_k}": round(statistics.fmean(control_keyword_rates), 4)
        if control_keyword_rates
        else None,
        f"candidate_keyword_hit_rate@{top_k}": round(statistics.fmean(candidate_keyword_rates), 4)
        if candidate_keyword_rates
        else None,
        "keyword_metric_note": "expected-term coverage proxy; not formal recall",
        f"control_query_hit_rate@{top_k}": round(sum(control_keyword_hits) / len(control_keyword_hits), 4)
        if control_keyword_hits
        else None,
        f"candidate_query_hit_rate@{top_k}": round(sum(candidate_keyword_hits) / len(candidate_keyword_hits), 4)
        if candidate_keyword_hits
        else None,
        "candidate_keyword_not_below_control": keyword_gate,
        "candidate_keyword_not_below_control_rate": round(sum(keyword_not_below) / len(keyword_not_below), 4)
        if keyword_not_below
        else None,
        f"control_exact_recall@{top_k}": round(statistics.fmean(control_recalls), 4)
        if control_recalls
        else None,
        f"candidate_exact_recall@{top_k}": round(statistics.fmean(candidate_recalls), 4)
        if candidate_recalls
        else None,
        "exact_recall_note": "runtime exact route-aware IDs only"
        if candidate_recalls
        else "n/a: no runtime exact IDs; keyword proxy is not recall",
        "exact_recall_query_count": len(candidate_recalls),
        "control_MRR": round(statistics.fmean(control_rrs), 4) if control_rrs else None,
        "candidate_MRR": round(statistics.fmean(candidate_rrs), 4) if candidate_rrs else None,
        "candidate_exact_not_below_control": exact_gate,
        "candidate_not_below_control": candidate_not_below,
        "source_coverage_rate": round(statistics.fmean(source_coverages), 4)
        if source_coverages
        else None,
        "source_coverage_query_count": len(source_coverages),
        "candidate_source_distribution": source_distribution,
        "duplicate_asset_rate": round(statistics.fmean(duplicate_rates), 4)
        if duplicate_rates
        else 0.0,
        "archived_leakage_count": archived_leakage_count,
        "archived_labeled_query_count": archived_labeled_query_count,
        "archived_leakage_note": (
            "exact forbidden runtime IDs only"
            if archived_labeled_query_count
            else "n/a coverage: no forbidden runtime IDs; zero is not a measured leakage rate"
        ),
        "no_answer_result_count": no_answer_result_count,
        "fallback_count": fallback_count,
        "fallback_rate": round(fallback_count / total, 4) if total else 0.0,
        "fallback_reasons": fallback_reasons,
        "shadow_response_count": shadow_response_count,
        "shadow_contract_violation_count": shadow_contract_violation_count,
        "branch_status_counts": branch_status_counts,
        "avg_latency_ms": round(statistics.fmean(latencies), 3) if latencies else 0.0,
        "p50_latency_ms": round(percentile(latencies, 0.50), 3),
        "p95_latency_ms": round(percentile(latencies, 0.95), 3),
        "avg_p1_latency_ms": round(statistics.fmean(branch_latencies["p1"]), 3)
        if branch_latencies["p1"]
        else None,
        "avg_p2_latency_ms": round(statistics.fmean(branch_latencies["p2"]), 3)
        if branch_latencies["p2"]
        else None,
        "avg_fusion_latency_ms": round(statistics.fmean(branch_latencies["fusion"]), 3)
        if branch_latencies["fusion"]
        else None,
        "failed_queries": failed_queries,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Unified Retrieval shadow eval.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--expected-manifest",
        type=Path,
        help="Optional runtime exact P1/P2 identifier labels.",
    )
    args = parser.parse_args()
    if args.top_k < 1 or args.top_k > 20:
        parser.error("--top-k must be between 1 and 20")
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    try:
        summary = run_eval(
            base_url=args.base_url,
            top_k=args.top_k,
            timeout=args.timeout,
            verbose=args.verbose,
            expected_manifest=args.expected_manifest,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    if summary["failed_queries"] or summary["archived_leakage_count"]:
        return 1
    return 0 if summary["candidate_not_below_control"] else 1


if __name__ == "__main__":
    sys.exit(main())
