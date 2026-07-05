#!/usr/bin/env python3
"""RAG Eval Runner — runs eval queries against the retrieve API and computes recall@5.

Usage:
  python scripts/run_rag_eval.py
  python scripts/run_rag_eval.py --base-url http://127.0.0.1:8000
  python scripts/run_rag_eval.py --base-url https://datahub-jr8x.onrender.com --top-k 5

Reads eval queries from samples/rag_eval_queries.json, calls
POST /api/customer-ops-agent/retrieve for each query, and computes:
  - recall@5 (via expected_keywords overlap)
  - keyword_hit_rate@5
  - semantic_mode_count / fallback_count
  - per-query detail

Does NOT require real LLM, real embedding API, or real Render database.
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

# Resolve repo root relative to this script
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
DEFAULT_EVAL_PATH = REPO_ROOT / "samples" / "rag_eval_queries.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_eval_queries(path: str) -> list[dict[str, Any]]:
    """Load eval queries from a JSON file. Returns list of query dicts."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"Eval file {path} must contain a JSON array.")
    return data


def call_retrieve(
    base_url: str,
    query: str,
    top_k: int = 5,
    timeout: int = 30,
) -> dict[str, Any] | None:
    """Call POST /api/customer-ops-agent/retrieve and return the response data."""
    url = f"{base_url.rstrip('/')}/api/customer-ops-agent/retrieve"
    try:
        resp = requests.post(
            url,
            json={"query": query, "top_k": top_k},
            headers={
                "Content-Type": "application/json",
                "X-DataHub-Client": "CustomerOpsAgent",
            },
            timeout=timeout,
        )
        if resp.status_code == 200:
            body = resp.json()
            return body.get("data", body)
        else:
            return {"error": f"HTTP {resp.status_code}", "detail": resp.text[:200]}
    except requests.ConnectionError:
        return {"error": "connection_refused", "detail": f"Cannot connect to {url}"}
    except requests.Timeout:
        return {"error": "timeout", "detail": f"Request to {url} timed out"}
    except Exception as exc:
        return {"error": "exception", "detail": str(exc)[:300]}


def compute_keyword_hit_rate(
    results: list[dict[str, Any]],
    expected_keywords: list[str],
) -> tuple[int, bool]:
    """Check how many expected keywords appear in the result chunk_text fields.

    Returns (matched_keyword_count, any_match).
    """
    if not expected_keywords:
        return 0, False

    # Collect all text from all results
    all_text = " ".join(
        r.get("chunk_text", "") + " " +
        r.get("intent", "") + " " +
        " ".join(r.get("tags", []))
        for r in results
    ).lower()

    matched = 0
    for kw in expected_keywords:
        if kw.lower() in all_text:
            matched += 1

    return matched, matched > 0


def compute_keyword_recall_at_k(
    results: list[dict[str, Any]],
    expected_keywords: list[str],
    k: int = 5,
) -> float:
    """Compute recall@k as the fraction of expected keywords found in top-k results."""
    if not expected_keywords:
        return 0.0

    top_k_results = results[:k]
    matched, _ = compute_keyword_hit_rate(top_k_results, expected_keywords)
    return matched / len(expected_keywords)


def run_eval(
    base_url: str,
    eval_path: str | None = None,
    top_k: int = 5,
    timeout: int = 30,
    verbose: bool = False,
) -> dict[str, Any]:
    """Run the full eval suite and return summary dict."""
    path = eval_path or str(DEFAULT_EVAL_PATH)
    queries = load_eval_queries(path)

    total = len(queries)
    recall_scores: list[float] = []
    keyword_hits: list[bool] = []
    semantic_count = 0
    fallback_count = 0
    failed = 0
    per_query: list[dict[str, Any]] = []

    print(f"RAG Eval Runner")
    print(f"base_url: {base_url}")
    print(f"eval_path: {path}")
    print(f"top_k: {top_k}")
    print(f"total_queries: {total}")
    print(f"started: {_now_iso()}")
    print()

    for idx, eq in enumerate(queries):
        qid = eq.get("id", f"eval_{idx}")
        query_text = eq.get("query", "")
        expected_keywords = eq.get("expected_keywords", [])
        expected_candidate_ids = eq.get("expected_candidate_ids", [])

        print(f"[{idx + 1}/{total}] {qid}: {query_text[:80]}...")

        resp = call_retrieve(base_url, query_text, top_k=top_k, timeout=timeout)
        if resp is None or "error" in resp:
            print(f"  -> ERROR: {resp.get('error', 'unknown') if resp else 'null'}")
            failed += 1
            per_query.append({
                "id": qid,
                "query": query_text,
                "error": resp.get("error", "null") if resp else "null",
                "recall_at_5": 0.0,
                "keyword_hit": False,
                "matched_count": 0,
            })
            continue

        results = resp.get("results", [])
        retrieval_mode = resp.get("retrieval_mode", "unknown")
        fallback_used = resp.get("fallback_used", False)
        fallback_reason = resp.get("fallback_reason")

        if retrieval_mode in ("customerops_vector_retrieval",):
            semantic_count += 1
        if fallback_used:
            fallback_count += 1

        # Compute keyword-level recall@5
        recall5 = compute_keyword_recall_at_k(results, expected_keywords, k=top_k)
        recall_scores.append(recall5)

        # Compute keyword hit rate (at least one keyword found)
        _, any_hit = compute_keyword_hit_rate(results[:top_k], expected_keywords)
        keyword_hits.append(any_hit)

        # Check expected_candidate_ids
        candidate_ids_found = [r.get("candidate_id", "") for r in results[:top_k]]
        candidate_hits = sum(
            1 for cid in expected_candidate_ids if cid in candidate_ids_found
        )

        pq = {
            "id": qid,
            "query": query_text,
            "recall_at_5": round(recall5, 4),
            "keyword_hit": any_hit,
            "matched_count": len(results),
            "retrieval_mode": retrieval_mode,
            "fallback_used": fallback_used,
            "fallback_reason": fallback_reason,
            "candidate_hits": candidate_hits,
            "scores": [r.get("score", 0) for r in results[:top_k]],
            "candidate_ids": candidate_ids_found,
        }
        per_query.append(pq)

        if verbose:
            print(f"  recall@5={recall5:.3f}  keyword_hit={any_hit}  mode={retrieval_mode}  "
                  f"fallback={fallback_used}  reason={fallback_reason or '—'}  "
                  f"results={len(results)}")
            for r in results[:3]:
                txt = str(r.get('chunk_text', '')[:60])
                # Safely handle characters that can't be encoded in the current terminal
                try:
                    print(f"    [{r.get('score', 0):.4f}] {txt}...")
                except UnicodeEncodeError:
                    print(f"    [{r.get('score', 0):.4f}] {txt.encode('ascii', errors='replace').decode('ascii')}...")
        else:
            status = "OK" if recall5 > 0 or any_hit else "MISS"
            print(f"  -> {status}  recall@5={recall5:.3f}  mode={retrieval_mode}  "
                  f"fallback={fallback_used}")

    # ── Summary ────────────────────────────────────────────────────
    avg_recall = sum(recall_scores) / len(recall_scores) if recall_scores else 0.0
    hit_rate = sum(keyword_hits) / len(keyword_hits) if keyword_hits else 0.0

    print()
    print("=" * 60)
    print("EVAL SUMMARY")
    print("=" * 60)
    print(f"  total_queries:         {total}")
    print(f"  failed_queries:        {failed}")
    print(f"  recall@5 (avg):        {avg_recall:.4f}")
    print(f"  keyword_hit_rate@5:    {hit_rate:.4f}")
    print(f"  semantic_mode_count:   {semantic_count}")
    print(f"  fallback_count:        {fallback_count}")
    print(f"  completed_at:          {_now_iso()}")

    return {
        "total_queries": total,
        "failed_queries": failed,
        "recall_at_5_avg": round(avg_recall, 4),
        "keyword_hit_rate_at_5": round(hit_rate, 4),
        "semantic_mode_count": semantic_count,
        "fallback_count": fallback_count,
        "per_query": per_query,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="RAG Eval Runner — compute recall@5 against the CustomerOpsAgent retrieve API.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples:
              python scripts/run_rag_eval.py
              python scripts/run_rag_eval.py --base-url http://127.0.0.1:8000 --top-k 5
              python scripts/run_rag_eval.py --base-url https://datahub-jr8x.onrender.com --top-k 5 --verbose
        """),
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="Base URL of the DataHub FastAPI backend (default: http://127.0.0.1:8000)",
    )
    parser.add_argument(
        "--eval-path",
        default=None,
        help="Path to eval queries JSON file (default: samples/rag_eval_queries.json)",
    )
    parser.add_argument("--top-k", type=int, default=5, help="Number of results per query (default: 5)")
    parser.add_argument("--timeout", type=int, default=30, help="HTTP request timeout in seconds (default: 30)")
    parser.add_argument("--verbose", action="store_true", help="Print per-result details")
    parser.add_argument("--output-json", default=None, help="Save full eval results to a JSON file")

    args = parser.parse_args()

    start = time.monotonic()
    summary = run_eval(
        base_url=args.base_url,
        eval_path=args.eval_path,
        top_k=args.top_k,
        timeout=args.timeout,
        verbose=args.verbose,
    )
    elapsed = time.monotonic() - start
    print(f"\n  duration: {elapsed:.1f}s")

    if args.output_json:
        with open(args.output_json, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        print(f"  output: {args.output_json}")

    # Exit code: 0 if any queries completed, 1 if all failed
    if summary["failed_queries"] >= summary["total_queries"]:
        print("\nAll queries failed. Check that the backend is reachable and serving requests.")
        sys.exit(1)


if __name__ == "__main__":
    main()
