#!/usr/bin/env python3
"""RAG Eval Runner — runs eval queries against the retrieve API and computes metrics.

Usage:
  python scripts/run_rag_eval.py
  python scripts/run_rag_eval.py --base-url http://127.0.0.1:8000
  python scripts/run_rag_eval.py --base-url https://datahub-jr8x.onrender.com --top-k 5 --verbose

Reads eval queries from samples/rag_eval_queries.json, calls
POST /api/customer-ops-agent/retrieve for each query, and computes:

  candidate_recall@5  — fraction of expected_candidate_ids found in top-5
                         (only meaningful when expected_candidate_ids is non-empty;
                          otherwise reports "n/a (keyword proxy only)")

  keyword_hit_rate@5  — fraction of queries where >=1 expected_keyword was found
                         in the top-5 results (keyword-proxy metric)

  avg_top1_score      — average similarity score of the top-1 result
  avg_top5_score      — average similarity score across all top-5 results

  semantic_mode_count — number of queries served by semantic (vector) retrieval
  fallback_count      — number of queries that fell back to keyword retrieval

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

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
DEFAULT_EVAL_PATH = REPO_ROOT / "samples" / "rag_eval_queries.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_eval_queries(path: str) -> list[dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"Eval file {path} must contain a JSON array.")
    return data


def call_retrieve(
    base_url: str, query: str, top_k: int = 5, timeout: int = 30,
) -> dict[str, Any] | None:
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


def compute_keyword_match(
    results: list[dict[str, Any]],
    expected_keywords: list[str],
) -> tuple[int, int, list[str], list[str]]:
    """Check expected_keywords against result chunk_text.

    Returns (matched_count, total_count, matched_list, missed_list).
    """
    if not expected_keywords:
        return 0, 0, [], []

    all_text = " ".join(
        r.get("chunk_text", "") + " " +
        r.get("intent", "") + " " +
        " ".join(r.get("tags", []))
        for r in results
    ).lower()

    matched = []
    missed = []
    for kw in expected_keywords:
        if kw.lower() in all_text:
            matched.append(kw)
        else:
            missed.append(kw)

    return len(matched), len(expected_keywords), matched, missed


def compute_candidate_recall_at_k(
    results: list[dict[str, Any]],
    expected_candidate_ids: list[str],
    k: int = 5,
) -> tuple[float, int, list[str]]:
    """Compute candidate_recall@k.

    Returns (recall, hits_count, found_candidate_ids).
    """
    if not expected_candidate_ids:
        return 0.0, 0, []

    top_cids = [r.get("candidate_id", "") for r in results[:k]]
    found = [cid for cid in expected_candidate_ids if cid in top_cids]
    return len(found) / len(expected_candidate_ids), len(found), found


def _safe_text(text: str, max_len: int = 80) -> str:
    """Safely truncate text for terminal display."""
    t = str(text)[:max_len].replace("\n", " | ").replace("\r", "")
    try:
        t.encode("ascii")
        return t
    except UnicodeEncodeError:
        return t.encode("ascii", errors="replace").decode("ascii")


def run_eval(
    base_url: str,
    eval_path: str | None = None,
    top_k: int = 5,
    timeout: int = 30,
    verbose: bool = False,
) -> dict[str, Any]:
    path = eval_path or str(DEFAULT_EVAL_PATH)
    queries = load_eval_queries(path)

    total = len(queries)
    keyword_hit_rates: list[float] = []
    keyword_hits_bool: list[bool] = []
    candidate_recalls: list[float] = []
    has_candidate_ids = False
    semantic_count = 0
    fallback_count = 0
    failed = 0
    all_top1_scores: list[float] = []
    all_topk_scores: list[float] = []
    mode_counts: dict[str, int] = {}
    per_query: list[dict[str, Any]] = []
    low_score_queries: list[str] = []

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

        if expected_candidate_ids:
            has_candidate_ids = True

        print(f"[{idx + 1}/{total}] {qid}: {query_text[:80]}")

        resp = call_retrieve(base_url, query_text, top_k=top_k, timeout=timeout)
        if resp is None or "error" in resp:
            print(f"  -> ERROR: {resp.get('error', 'unknown') if resp else 'null'}")
            failed += 1
            per_query.append({
                "id": qid, "query": query_text,
                "error": resp.get("error", "null") if resp else "null",
                "keyword_hit_rate": 0.0, "candidate_recall": 0.0,
                "keyword_hit": False, "matched_count": 0,
            })
            continue

        results = resp.get("results", [])
        retrieval_mode = resp.get("retrieval_mode", "unknown")
        fallback_used = resp.get("fallback_used", False)
        fallback_reason = resp.get("fallback_reason")

        # Track mode distribution
        mode_counts[retrieval_mode] = mode_counts.get(retrieval_mode, 0) + 1
        if retrieval_mode in ("customerops_vector_retrieval",):
            semantic_count += 1
        if fallback_used:
            fallback_count += 1

        # Keyword matching
        kw_matched, kw_total, kw_matched_list, kw_missed_list = \
            compute_keyword_match(results[:top_k], expected_keywords)
        kw_hit_rate = kw_matched / kw_total if kw_total > 0 else 0.0
        keyword_hit_rates.append(kw_hit_rate)
        keyword_hits_bool.append(kw_matched > 0)

        # Candidate recall (only meaningful if expected_candidate_ids non-empty)
        cand_recall, cand_hits, cand_found = \
            compute_candidate_recall_at_k(results, expected_candidate_ids, k=top_k)
        if expected_candidate_ids:
            candidate_recalls.append(cand_recall)

        # Score tracking
        topk_scores = [r.get("score", 0.0) for r in results[:top_k]]
        if topk_scores:
            all_top1_scores.append(topk_scores[0])
            all_topk_scores.extend(topk_scores)

        # Low-score detection: avg top-5 score below 0.1
        avg_score = sum(topk_scores) / len(topk_scores) if topk_scores else 0.0
        if kw_hit_rate == 0.0 and kw_matched == 0:
            low_score_queries.append(f"{qid}: '{query_text[:60]}' "
                                     f"(missed: {', '.join(kw_missed_list[:5]) if kw_missed_list else 'no keywords'})")

        pq = {
            "id": qid,
            "query": query_text,
            "intent": eq.get("intent", ""),
            "expected_keywords": expected_keywords,
            "expected_candidate_ids": expected_candidate_ids,
            "matched_keywords": kw_matched_list,
            "missed_keywords": kw_missed_list,
            "keyword_hit_rate": round(kw_hit_rate, 4),
            "keyword_hit": kw_matched > 0,
            "candidate_recall_at_5": round(cand_recall, 4) if expected_candidate_ids else None,
            "candidate_hits": cand_hits,
            "matched_count": len(results),
            "retrieval_mode": retrieval_mode,
            "fallback_used": fallback_used,
            "fallback_reason": fallback_reason,
            "avg_top5_score": round(avg_score, 4),
            "top1_score": round(topk_scores[0], 4) if topk_scores else 0.0,
            "scores": [round(s, 4) for s in topk_scores],
            "candidate_ids": [r.get("candidate_id", "") for r in results[:top_k]],
        }
        per_query.append(pq)

        if verbose:
            print(f"  kw_hit={kw_hit_rate:.2f} ({kw_matched}/{kw_total})  "
                  f"matched=[{', '.join(kw_matched_list[:5])}]  "
                  f"missed=[{', '.join(kw_missed_list[:5])}]")
            print(f"  mode={retrieval_mode}  fb={fallback_used}  "
                  f"reason={fallback_reason or '—'}  "
                  f"results={len(results)}  avg_score={avg_score:.4f}")
            for i, r in enumerate(results[:top_k]):
                score = r.get("score", 0.0)
                txt = _safe_text(r.get("chunk_text", ""), 80)
                cid = r.get("candidate_id", "")[:20]
                print(f"    [{i + 1}] score={score:+.4f}  cid={cid}")
                print(f"         text={txt}")
            # Show missed keywords prominently
            if kw_missed_list:
                print(f"  >>> MISSED KEYWORDS: {', '.join(kw_missed_list)}")
        else:
            status = "HIT" if kw_matched > 0 else "MISS"
            kw_info = f"kw={kw_hit_rate:.2f} ({kw_matched}/{kw_total})"
            if expected_candidate_ids:
                kw_info += f"  cand_recall={cand_recall:.2f}"
            print(f"  -> {status}  {kw_info}  mode={retrieval_mode}  "
                  f"avg_score={avg_score:.4f}  fb={fallback_used}")

    # ── Summary ────────────────────────────────────────────────────
    avg_kw_hit_rate = (sum(keyword_hit_rates) / len(keyword_hit_rates)
                       if keyword_hit_rates else 0.0)
    kw_query_hit_rate = (sum(keyword_hits_bool) / len(keyword_hits_bool)
                         if keyword_hits_bool else 0.0)
    avg_cand_recall = (sum(candidate_recalls) / len(candidate_recalls)
                       if candidate_recalls else 0.0)
    avg_top1 = (sum(all_top1_scores) / len(all_top1_scores)
                if all_top1_scores else 0.0)
    avg_topk = (sum(all_topk_scores) / len(all_topk_scores)
                if all_topk_scores else 0.0)

    print()
    print("=" * 60)
    print("EVAL SUMMARY")
    print("=" * 60)
    print(f"  total_queries:             {total}")
    print(f"  failed_queries:            {failed}")
    print(f"  ---")
    print(f"  keyword_hit_rate@5:        {avg_kw_hit_rate:.4f}  (avg fraction of keywords found)")
    print(f"  keyword_query_hit_rate@5:  {kw_query_hit_rate:.4f}  (fraction of queries with >=1 keyword)")
    if has_candidate_ids and candidate_recalls:
        print(f"  candidate_recall@5:        {avg_cand_recall:.4f}  (fraction of expected_candidate_ids found)")
    else:
        print(f"  candidate_recall@5:        n/a (expected_candidate_ids empty -- keyword proxy only)")
    print(f"  ---")
    print(f"  avg_top1_score:            {avg_top1:.4f}")
    print(f"  avg_top5_score:            {avg_topk:.4f}")
    print(f"  ---")
    print(f"  retrieval_mode distribution:")
    for mode, cnt in sorted(mode_counts.items()):
        print(f"    {mode}: {cnt}")
    print(f"  semantic_mode_count:       {semantic_count}")
    print(f"  fallback_count:            {fallback_count}")
    print(f"  ---")
    if low_score_queries:
        print(f"  LOW-SCORE QUERIES (no keyword hits):")
        for ls in low_score_queries:
            print(f"    - {ls}")
    print(f"  ---")
    print(f"  completed_at:              {_now_iso()}")

    return {
        "total_queries": total,
        "failed_queries": failed,
        "keyword_hit_rate_at_5": round(avg_kw_hit_rate, 4),
        "keyword_query_hit_rate_at_5": round(kw_query_hit_rate, 4),
        "candidate_recall_at_5": round(avg_cand_recall, 4) if candidate_recalls else None,
        "candidate_recall_note": (
            None if has_candidate_ids
            else "expected_candidate_ids empty — keyword_hit_rate is a proxy metric, not formal recall"
        ),
        "avg_top1_score": round(avg_top1, 4),
        "avg_top5_score": round(avg_topk, 4),
        "semantic_mode_count": semantic_count,
        "fallback_count": fallback_count,
        "mode_counts": mode_counts,
        "low_score_queries": low_score_queries,
        "per_query": per_query,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="RAG Eval Runner — compute metrics against the CustomerOpsAgent retrieve API.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples:
              python scripts/run_rag_eval.py
              python scripts/run_rag_eval.py --base-url http://127.0.0.1:8000 --top-k 5
              python scripts/run_rag_eval.py --base-url https://datahub-jr8x.onrender.com --top-k 5 --verbose
        """),
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000",
                        help="Base URL of the DataHub FastAPI backend")
    parser.add_argument("--eval-path", default=None,
                        help="Path to eval queries JSON file")
    parser.add_argument("--top-k", type=int, default=5,
                        help="Number of results per query (default: 5)")
    parser.add_argument("--timeout", type=int, default=30,
                        help="HTTP request timeout in seconds (default: 30)")
    parser.add_argument("--verbose", action="store_true",
                        help="Print per-result details including top-K matches and missed keywords")
    parser.add_argument("--output-json", default=None,
                        help="Save full eval results to a JSON file")

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

    if summary["failed_queries"] >= summary["total_queries"]:
        print("\nAll queries failed. Check that the backend is reachable.")
        sys.exit(1)


if __name__ == "__main__":
    main()
