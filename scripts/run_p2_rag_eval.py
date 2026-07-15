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
) -> dict[str, int]:
    expected = set(expected_knowledge_asset_ids) | set(expected_asset_ids)
    ranks: dict[str, int] = {}
    for rank, item in enumerate(results[:top_k], start=1):
        for candidate in (
            str(item.get("knowledge_asset_id", "")),
            str(item.get("asset_id", "")),
        ):
            if candidate in expected and candidate not in ranks:
                ranks[candidate] = rank
    return ranks


def candidate_recall_at_k(
    results: list[dict[str, Any]],
    expected_knowledge_asset_ids: list[str],
    expected_asset_ids: list[str],
    top_k: int,
) -> float | None:
    expected = set(expected_knowledge_asset_ids) | set(expected_asset_ids)
    if not expected:
        return None
    ranks = expected_identifier_ranks(
        results, expected_knowledge_asset_ids, expected_asset_ids, top_k
    )
    return len(ranks) / len(expected)


def reciprocal_rank_at_k(
    results: list[dict[str, Any]],
    expected_knowledge_asset_ids: list[str],
    expected_asset_ids: list[str],
    top_k: int,
) -> float | None:
    expected = set(expected_knowledge_asset_ids) | set(expected_asset_ids)
    if not expected:
        return None
    ranks = expected_identifier_ranks(
        results, expected_knowledge_asset_ids, expected_asset_ids, top_k
    )
    return 1.0 / min(ranks.values()) if ranks else 0.0


def archived_leakage(
    results: list[dict[str, Any]],
    forbidden_knowledge_asset_ids: list[str],
    forbidden_asset_ids: list[str],
) -> list[str]:
    forbidden = set(forbidden_knowledge_asset_ids) | set(forbidden_asset_ids)
    leaked: list[str] = []
    for item in results:
        for candidate in (
            str(item.get("knowledge_asset_id", "")),
            str(item.get("asset_id", "")),
        ):
            if candidate in forbidden:
                leaked.append(candidate)
    return sorted(set(leaked))


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
) -> dict[str, Any]:
    payload = json.loads(eval_file.read_text(encoding="utf-8"))
    queries = list(payload.get("queries", []))
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

        expected_knowledge = list(item.get("expected_knowledge_asset_ids", []))
        expected_assets = list(item.get("expected_asset_ids", []))
        expected_terms = list(item.get("expected_terms", []))
        term_rate, matched_terms = keyword_evidence_rate(results, expected_terms)
        if term_rate is not None:
            keyword_rates.append(term_rate)
            query_keyword_hits.append(term_rate > 0)
        recall = candidate_recall_at_k(
            results, expected_knowledge, expected_assets, top_k
        )
        if recall is not None:
            candidate_recalls.append(recall)
        reciprocal_rank = reciprocal_rank_at_k(
            results, expected_knowledge, expected_assets, top_k
        )
        if reciprocal_rank is not None:
            reciprocal_ranks.append(reciprocal_rank)
        leaked = archived_leakage(
            results,
            list(item.get("forbidden_knowledge_asset_ids", [])),
            list(item.get("forbidden_asset_ids", [])),
        )
        archived_leakage_count += len(leaked)
        if bool(item.get("expect_no_hit", False)) and results:
            failed_queries.append(
                {
                    "query_id": query_id,
                    "reason": "unexpected_no_answer_hit",
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
            "exact expected Knowledge Asset/Asset identifiers only"
            if candidate_recalls
            else "n/a: no exact expected identifiers; keyword proxy is not recall"
        ),
        "MRR": round(statistics.fmean(reciprocal_ranks), 4)
        if reciprocal_ranks
        else None,
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
    args = parser.parse_args()
    if args.top_k < 1 or args.top_k > 20:
        parser.error("--top-k must be between 1 and 20")
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    summary = run_eval(
        base_url=args.base_url,
        top_k=args.top_k,
        verbose=args.verbose,
        timeout=args.timeout,
    )
    return 1 if summary["failed_queries"] or summary["archived_leakage_count"] else 0


if __name__ == "__main__":
    sys.exit(main())
