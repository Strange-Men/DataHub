#!/usr/bin/env python3
"""Evaluate the isolated P2-only semantic retrieval API.

Keyword metrics are explicitly proxy evidence metrics. Formal candidate recall
and MRR use exact expected Knowledge Asset/Asset identifiers only.
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
DEFAULT_EVAL_FILE = ROOT_DIR / "samples" / "p2_rag_eval_queries.json"

_ID_LIST_FIELDS = (
    "expected_knowledge_asset_ids",
    "expected_asset_ids",
    "expected_chunk_ids",
    "forbidden_knowledge_asset_ids",
    "forbidden_asset_ids",
    "forbidden_chunk_ids",
)


def _post_json(url: str, payload: dict[str, object], timeout: float) -> tuple[int, dict[str, Any]]:
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
    return "\n".join(str(item.get("chunk_text", "")) for item in results).lower()


def keyword_evidence_rate(
    results: list[dict[str, Any]], expected_terms: list[str]
) -> tuple[float | None, list[str]]:
    """Return keyword coverage proxy; None means the query has no term labels."""
    if not expected_terms:
        return None, []
    text = _result_text(results)
    matched = [term for term in expected_terms if term.lower() in text]
    return len(matched) / len(expected_terms), matched


def expected_identifier_ranks(
    results: list[dict[str, Any]],
    expected_knowledge_asset_ids: list[str],
    expected_asset_ids: list[str],
    top_k: int,
    expected_chunk_ids: list[str] | None = None,
) -> dict[str, int]:
    """Return ranks at one canonical identity grain.

    Knowledge Asset ids are version-aware and therefore take precedence.
    Chunk ids are the next-best exact identity; Asset ids are only a fallback.
    Mixing all three grains would count one candidate multiple times and could
    let a superseded version match through its shared source Asset id.
    """
    if expected_knowledge_asset_ids:
        field = "knowledge_asset_id"
        expected = set(expected_knowledge_asset_ids)
    elif expected_chunk_ids:
        field = "chunk_id"
        expected = set(expected_chunk_ids)
    else:
        field = "asset_id"
        expected = set(expected_asset_ids)
    ranks: dict[str, int] = {}
    for rank, item in enumerate(results[:top_k], start=1):
        candidate = str(item.get(field, ""))
        if candidate in expected and candidate not in ranks:
            ranks[candidate] = rank
    return ranks


def candidate_recall_at_k(
    results: list[dict[str, Any]],
    expected_knowledge_asset_ids: list[str],
    expected_asset_ids: list[str],
    top_k: int,
    expected_chunk_ids: list[str] | None = None,
) -> float | None:
    expected = (
        set(expected_knowledge_asset_ids)
        if expected_knowledge_asset_ids
        else set(expected_chunk_ids or [])
        if expected_chunk_ids
        else set(expected_asset_ids)
    )
    if not expected:
        return None
    ranks = expected_identifier_ranks(
        results,
        expected_knowledge_asset_ids,
        expected_asset_ids,
        top_k,
        expected_chunk_ids,
    )
    return len(ranks) / len(expected)


def reciprocal_rank_at_k(
    results: list[dict[str, Any]],
    expected_knowledge_asset_ids: list[str],
    expected_asset_ids: list[str],
    top_k: int,
    expected_chunk_ids: list[str] | None = None,
) -> float | None:
    expected = (
        set(expected_knowledge_asset_ids)
        if expected_knowledge_asset_ids
        else set(expected_chunk_ids or [])
        if expected_chunk_ids
        else set(expected_asset_ids)
    )
    if not expected:
        return None
    ranks = expected_identifier_ranks(
        results,
        expected_knowledge_asset_ids,
        expected_asset_ids,
        top_k,
        expected_chunk_ids,
    )
    return 1.0 / min(ranks.values()) if ranks else 0.0


def archived_leakage(
    results: list[dict[str, Any]],
    forbidden_knowledge_asset_ids: list[str],
    forbidden_asset_ids: list[str],
    forbidden_chunk_ids: list[str] | None = None,
) -> list[str]:
    forbidden = (
        set(forbidden_knowledge_asset_ids)
        | set(forbidden_asset_ids)
        | set(forbidden_chunk_ids or [])
    )
    leaked: list[str] = []
    for item in results:
        for candidate in (
            str(item.get("knowledge_asset_id", "")),
            str(item.get("asset_id", "")),
            str(item.get("chunk_id", "")),
        ):
            if candidate in forbidden:
                leaked.append(candidate)
    return sorted(set(leaked))


def _string_list(value: object, *, field: str, query_id: str) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise ValueError(
            f"Manifest query '{query_id}' field '{field}' must be a list of non-empty strings."
        )
    return list(dict.fromkeys(item.strip() for item in value))


def load_expected_manifest(path: Path) -> dict[str, dict[str, object]]:
    """Load strict runtime labels without allowing query-text replacement."""
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
        if not isinstance(raw.get("should_return_results"), bool):
            raise ValueError(
                f"Manifest query '{query_id}' requires boolean should_return_results."
            )
        if not isinstance(raw.get("should_be_archived"), bool):
            raise ValueError(
                f"Manifest query '{query_id}' requires boolean should_be_archived."
            )

        normalized: dict[str, object] = {
            "should_return_results": raw["should_return_results"],
            "should_be_archived": raw["should_be_archived"],
        }
        for field in _ID_LIST_FIELDS:
            normalized[field] = _string_list(
                raw.get(field, []), field=field, query_id=query_id
            )
        normalized["expected_terms"] = _string_list(
            raw.get("expected_keywords", raw.get("expected_terms", [])),
            field="expected_keywords",
            query_id=query_id,
        )

        if normalized["should_be_archived"] and normalized["should_return_results"]:
            raise ValueError(
                f"Manifest query '{query_id}' cannot be archived and expected to return results."
            )
        runtime_query = raw.get("runtime_query")
        if runtime_query is not None:
            if not normalized["should_be_archived"]:
                raise ValueError(
                    f"Manifest query '{query_id}' may override runtime_query only when archived."
                )
            if not isinstance(runtime_query, str):
                raise ValueError(
                    f"Manifest query '{query_id}' field 'runtime_query' must be a string."
                )
            runtime_query = runtime_query.strip()
            if not runtime_query or len(runtime_query) > 500:
                raise ValueError(
                    f"Manifest query '{query_id}' field 'runtime_query' must contain 1 to 500 characters."
                )
            normalized["runtime_query"] = runtime_query
        expected_exact = any(normalized[field] for field in _ID_LIST_FIELDS[:3])
        if normalized["should_return_results"] and not expected_exact:
            raise ValueError(
                f"Manifest query '{query_id}' requires an exact expected identifier."
            )
        if normalized["should_be_archived"] and not expected_exact:
            raise ValueError(
                f"Archived manifest query '{query_id}' requires an exact identifier."
            )
        manifest[query_id] = normalized
    return manifest


def apply_expected_manifest(
    queries: list[dict[str, Any]],
    manifest: dict[str, dict[str, object]],
) -> list[dict[str, Any]]:
    base_ids = [str(item.get("id", "")).strip() for item in queries]
    if any(not query_id for query_id in base_ids) or len(set(base_ids)) != len(base_ids):
        raise ValueError("Eval queries must have unique non-empty ids.")
    missing = sorted(set(base_ids) - set(manifest))
    unknown = sorted(set(manifest) - set(base_ids))
    if missing:
        raise ValueError(f"Expected manifest is missing query ids: {', '.join(missing)}")
    if unknown:
        raise ValueError(f"Expected manifest has unknown query ids: {', '.join(unknown)}")

    merged_queries: list[dict[str, Any]] = []
    for base in queries:
        query_id = str(base["id"])
        runtime = manifest[query_id]
        merged = dict(base)
        for field in _ID_LIST_FIELDS:
            merged[field] = list(runtime[field])  # type: ignore[arg-type]
        merged["expected_terms"] = list(runtime["expected_terms"])  # type: ignore[arg-type]
        should_return = bool(runtime["should_return_results"])
        should_be_archived = bool(runtime["should_be_archived"])
        merged["should_return_results"] = should_return
        merged["should_be_archived"] = should_be_archived
        merged["expect_no_hit"] = not should_return
        if should_be_archived and runtime.get("runtime_query") is not None:
            merged["query"] = str(runtime["runtime_query"])

        if should_be_archived:
            for expected_field, forbidden_field in (
                ("expected_knowledge_asset_ids", "forbidden_knowledge_asset_ids"),
                ("expected_asset_ids", "forbidden_asset_ids"),
                ("expected_chunk_ids", "forbidden_chunk_ids"),
            ):
                merged[forbidden_field] = list(
                    dict.fromkeys(
                        [*merged[forbidden_field], *merged[expected_field]]
                    )
                )
        merged_queries.append(merged)
    return merged_queries


def duplicate_asset_fraction(results: list[dict[str, Any]]) -> float:
    if not results:
        return 0.0
    counts: dict[str, int] = {}
    for item in results:
        asset_id = str(item.get("asset_id", ""))
        if asset_id:
            counts[asset_id] = counts.get(asset_id, 0) + 1
    duplicate_results = sum(max(0, count - 1) for count in counts.values())
    return duplicate_results / len(results)


def percentile_95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(0.95 * len(ordered)) - 1)
    return ordered[index]


def run_eval(
    *,
    base_url: str,
    top_k: int,
    verbose: bool,
    timeout: float,
    eval_file: Path = DEFAULT_EVAL_FILE,
    expected_manifest: Path | None = None,
) -> dict[str, Any]:
    payload = json.loads(eval_file.read_text(encoding="utf-8"))
    queries = list(payload.get("queries", []))
    if expected_manifest is not None:
        queries = apply_expected_manifest(
            queries,
            load_expected_manifest(expected_manifest),
        )
    keyword_rates: list[float] = []
    query_keyword_hits: list[bool] = []
    candidate_recalls: list[float] = []
    reciprocal_ranks: list[float] = []
    duplicate_rates: list[float] = []
    top1_scores: list[float] = []
    top5_scores: list[float] = []
    latencies: list[float] = []
    failed_queries: list[dict[str, object]] = []
    semantic_mode_count = 0
    no_hit_count = 0
    archived_leakage_count = 0

    endpoint = base_url.rstrip("/") + "/api/v2/retrieval/p2/search"
    for item in queries:
        query_id = str(item.get("id", ""))
        query = str(item.get("query", ""))
        try:
            status, envelope = _post_json(
                endpoint,
                {
                    "query": query,
                    "top_k": top_k,
                    "debug": verbose,
                    "request_id": f"p2-eval-{query_id}",
                },
                timeout,
            )
        except (URLError, TimeoutError, OSError) as exc:
            failed_queries.append(
                {"query_id": query_id, "reason": type(exc).__name__}
            )
            if verbose:
                print(f"[{query_id}] ERROR {type(exc).__name__}")
            continue
        data = envelope.get("data", {}) if isinstance(envelope, dict) else {}
        if status != 200 or not isinstance(data, dict):
            failed_queries.append(
                {
                    "query_id": query_id,
                    "status": status,
                    "reason": data.get("fallback_reason", "request_failed")
                    if isinstance(data, dict)
                    else "invalid_response",
                }
            )
            if verbose:
                print(f"[{query_id}] HTTP {status}: {failed_queries[-1]['reason']}")
            continue

        results = list(data.get("results", []))[:top_k]
        if data.get("retrieval_mode") == "p2_vector_retrieval":
            semantic_mode_count += 1
        if not results:
            no_hit_count += 1
        latency = float(data.get("latency_ms", 0.0) or 0.0)
        latencies.append(latency)
        scores = [float(result.get("score", 0.0) or 0.0) for result in results]
        if scores:
            top1_scores.append(scores[0])
            top5_scores.extend(scores[:5])
        duplicate_rates.append(duplicate_asset_fraction(results))

        should_return_results = bool(
            item.get("should_return_results", not item.get("expect_no_hit", False))
        )
        should_be_archived = bool(item.get("should_be_archived", False))
        expected_knowledge = list(item.get("expected_knowledge_asset_ids", []))
        expected_assets = list(item.get("expected_asset_ids", []))
        expected_chunks = list(item.get("expected_chunk_ids", []))
        expected_terms = list(item.get("expected_terms", []))
        term_rate, matched_terms = keyword_evidence_rate(results, expected_terms)
        if should_return_results and term_rate is not None:
            keyword_rates.append(term_rate)
            query_keyword_hits.append(term_rate > 0)
        recall = (
            candidate_recall_at_k(
                results,
                expected_knowledge,
                expected_assets,
                top_k,
                expected_chunks,
            )
            if should_return_results
            else None
        )
        if recall is not None:
            candidate_recalls.append(recall)
        reciprocal_rank = (
            reciprocal_rank_at_k(
                results,
                expected_knowledge,
                expected_assets,
                top_k,
                expected_chunks,
            )
            if should_return_results
            else None
        )
        if reciprocal_rank is not None:
            reciprocal_ranks.append(reciprocal_rank)
        leaked = archived_leakage(
            results,
            list(item.get("forbidden_knowledge_asset_ids", [])),
            list(item.get("forbidden_asset_ids", [])),
            list(item.get("forbidden_chunk_ids", [])),
        )
        archived_leakage_count += len(leaked)
        if not should_return_results and results:
            failed_queries.append(
                {
                    "query_id": query_id,
                    "reason": (
                        "unexpected_archived_query_hit"
                        if should_be_archived
                        else "unexpected_no_answer_hit"
                    ),
                    "returned_knowledge_asset_ids": [
                        result.get("knowledge_asset_id") for result in results
                    ],
                }
            )

        if verbose:
            hit_reason = (
                f"exact_recall={recall:.3f}" if recall is not None else "formal_recall=n/a"
            )
            print(f"[{query_id}] {query}")
            print(
                f"  expected_ids={expected_knowledge + expected_assets} "
                f"expected_chunk_ids={expected_chunks} "
                f"expected_terms={expected_terms} {hit_reason} "
                f"keyword_proxy={term_rate if term_rate is not None else 'n/a'} "
                f"matched_terms={matched_terms} leaked={leaked}"
            )
            for result in results:
                print(
                    "  "
                    f"rank={result.get('rank')} score={result.get('score')} "
                    f"knowledge_asset_id={result.get('knowledge_asset_id')} "
                    f"asset_id={result.get('asset_id')} chunk_id={result.get('chunk_id')} "
                    f"trace={json.dumps(result.get('source_trace', {}), ensure_ascii=False)}"
                )

    total_queries = len(queries)
    summary = {
        "total_queries": total_queries,
        f"hit_rate@{top_k}": round(statistics.fmean(keyword_rates), 4)
        if keyword_rates
        else None,
        "hit_rate_note": "average expected-term coverage proxy; not formal recall",
        f"query_hit_rate@{top_k}": round(
            sum(query_keyword_hits) / len(query_keyword_hits), 4
        )
        if query_keyword_hits
        else None,
        "query_hit_rate_note": "fraction of term-labeled queries with at least one expected term",
        f"candidate_recall@{top_k}": round(statistics.fmean(candidate_recalls), 4)
        if candidate_recalls
        else None,
        "candidate_recall_note": (
            "exact canonical identifiers only (Knowledge Asset > Chunk > Asset)"
            if candidate_recalls
            else "n/a: no exact expected identifiers; keyword proxy is not recall"
        ),
        "candidate_recall_query_count": len(candidate_recalls),
        "MRR": round(statistics.fmean(reciprocal_ranks), 4)
        if reciprocal_ranks
        else None,
        "mrr_query_count": len(reciprocal_ranks),
        "semantic_mode_count": semantic_mode_count,
        "no_hit_count": no_hit_count,
        "archived_leakage_count": archived_leakage_count,
        "duplicate_asset_rate": round(statistics.fmean(duplicate_rates), 4)
        if duplicate_rates
        else 0.0,
        "avg_top1_score": round(statistics.fmean(top1_scores), 4)
        if top1_scores
        else 0.0,
        "avg_top5_score": round(statistics.fmean(top5_scores), 4)
        if top5_scores
        else 0.0,
        "avg_latency_ms": round(statistics.fmean(latencies), 3) if latencies else 0.0,
        "p95_latency_ms": round(percentile_95(latencies), 3),
        "failed_queries": failed_queries,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run isolated P2 retrieval eval.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument(
        "--expected-manifest",
        type=Path,
        help="Runtime exact-id labels generated by local acceptance.",
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
            verbose=args.verbose,
            timeout=args.timeout,
            expected_manifest=args.expected_manifest,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    return 1 if summary["failed_queries"] or summary["archived_leakage_count"] else 0


if __name__ == "__main__":
    sys.exit(main())
