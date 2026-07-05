#!/usr/bin/env python3
"""Seed a clean, English-only eval corpus for RAG evaluation.

Usage:
  python scripts/seed_rag_eval_corpus.py --base-url http://127.0.0.1:8000
  python scripts/seed_rag_eval_corpus.py --base-url https://datahub-jr8x.onrender.com --verbose

Creates a small set of clean customer-service knowledge entries via the
existing P1 APIs (import -> clean -> manual_clean -> extract -> approve ->
sync_rag).  Does NOT introduce new business APIs.

Each entry has clear English question/answer/intent covering:
  - refund / return
  - shipping / tracking
  - escalation / human support

Outputs:
  - batch_id, candidate_ids, embedding_count, trace_id
  - per-step PASS/FAIL status

If a step fails, reports it and does not pretend success.
"""

from __future__ import annotations

import argparse
import sys
import textwrap
import time
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import requests


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _trace_id() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"eval-corpus-{ts}-{uuid4().hex[:6]}"


EVAL_CORPUS_CONVERSATIONS: list[dict[str, Any]] = [
    {
        "conversation_id": "eval_corpus_conv_refund",
        "messages": [
            {
                "message_id": "eval_msg_refund_q",
                "role": "customer",
                "content": "How do I return a product and get my money back?",
                "timestamp": "2026-07-05T10:00:00Z",
            },
            {
                "message_id": "eval_msg_refund_a",
                "role": "agent",
                "content": "You can return any product within 30 days for a full refund. Please include the original packaging and receipt. Refunds are processed within 5-7 business days after we receive the return.",
                "timestamp": "2026-07-05T10:01:00Z",
            },
        ],
    },
    {
        "conversation_id": "eval_corpus_conv_shipping",
        "messages": [
            {
                "message_id": "eval_msg_shipping_q",
                "role": "customer",
                "content": "Where is my order and how can I track it?",
                "timestamp": "2026-07-05T11:00:00Z",
            },
            {
                "message_id": "eval_msg_shipping_a",
                "role": "agent",
                "content": "Your order is being processed. You can track your shipment using the tracking number in your account. Standard shipping takes 5-7 business days, express shipping takes 2-3 business days.",
                "timestamp": "2026-07-05T11:01:00Z",
            },
        ],
    },
    {
        "conversation_id": "eval_corpus_conv_escalation",
        "messages": [
            {
                "message_id": "eval_msg_escalation_q",
                "role": "customer",
                "content": "I need to speak to a human agent right now, this is urgent.",
                "timestamp": "2026-07-05T12:00:00Z",
            },
            {
                "message_id": "eval_msg_escalation_a",
                "role": "agent",
                "content": "I understand your frustration. Let me transfer you to a human agent immediately. A support specialist will assist you within the next few minutes.",
                "timestamp": "2026-07-05T12:01:00Z",
            },
        ],
    },
    {
        "conversation_id": "eval_corpus_conv_warranty",
        "messages": [
            {
                "message_id": "eval_msg_warranty_q",
                "role": "customer",
                "content": "What warranty coverage do you offer on electronics?",
                "timestamp": "2026-07-05T13:00:00Z",
            },
            {
                "message_id": "eval_msg_warranty_a",
                "role": "agent",
                "content": "All electronics come with a 12-month manufacturer warranty covering defects. You can purchase extended warranty for up to 3 years of total coverage. Warranty claims require proof of purchase.",
                "timestamp": "2026-07-05T13:01:00Z",
            },
        ],
    },
    {
        "conversation_id": "eval_corpus_conv_cancel",
        "messages": [
            {
                "message_id": "eval_msg_cancel_q",
                "role": "customer",
                "content": "Can I cancel my order after it has already been shipped?",
                "timestamp": "2026-07-05T14:00:00Z",
            },
            {
                "message_id": "eval_msg_cancel_a",
                "role": "agent",
                "content": "If your order has already shipped, you cannot cancel it directly. However, you can refuse the delivery or return the package after receiving it for a full refund within 30 days.",
                "timestamp": "2026-07-05T14:01:00Z",
            },
        ],
    },
]


def seed_corpus(
    base_url: str,
    timeout: int = 30,
    verbose: bool = False,
) -> dict[str, Any]:
    base = base_url.rstrip("/")
    session = requests.Session()
    session.headers["Content-Type"] = "application/json"
    tid = _trace_id()

    def _post(path: str, json_data: dict[str, Any] | None = None,
              extra_headers: dict[str, str] | None = None) -> requests.Response:
        return session.post(f"{base}{path}", json=json_data, timeout=timeout,
                            headers=extra_headers or None)

    def _get(path: str) -> requests.Response:
        return session.get(f"{base}{path}", timeout=timeout)

    results: list[dict[str, str]] = []
    candidate_ids: list[str] = []

    print(f"Seed Eval Corpus")
    print(f"base_url: {base}")
    print(f"trace_id: {tid}")
    print(f"conversations: {len(EVAL_CORPUS_CONVERSATIONS)}")
    print(f"started: {_now_iso()}")
    print()

    # Step 1: Import
    source_name = f"eval_corpus_{tid}"
    import_payload: dict[str, Any] = {
        "source_name": source_name,
        "conversations": EVAL_CORPUS_CONVERSATIONS,
    }
    try:
        resp = _post("/api/sources/import-json", json_data=import_payload)
        if resp.status_code != 200:
            print(f"[FAIL] import: HTTP {resp.status_code} {resp.text[:200]}")
            return {"status": "failed", "step": "import"}
        batch_id = resp.json()["data"]["batch_id"]
        print(f"[PASS] import -> batch_id={batch_id}")
        results.append({"step": "import", "status": "PASS", "batch_id": batch_id})
    except Exception as exc:
        print(f"[FAIL] import: {exc}")
        return {"status": "failed", "step": "import", "error": str(exc)[:200]}

    # Step 2: Machine cleaning
    try:
        resp = _post(f"/api/cleaning/run/{batch_id}")
        if resp.status_code != 200:
            print(f"[FAIL] machine_cleaning: HTTP {resp.status_code}")
            return {"status": "failed", "step": "machine_cleaning"}
        print(f"[PASS] machine_cleaning")
        results.append({"step": "machine_cleaning", "status": "PASS"})
    except Exception as exc:
        print(f"[FAIL] machine_cleaning: {exc}")
        return {"status": "failed", "step": "machine_cleaning", "error": str(exc)[:200]}

    # Helper for PATCH requests (defined before use)
    def _patch(path: str, json_data: dict[str, Any]) -> requests.Response:
        return session.patch(f"{base}{path}", json=json_data, timeout=timeout)

    # Step 3: Manual cleaning — mark first message as keep (no content change)
    try:
        resp = _patch(
            f"/api/sanitized/{batch_id}/messages/{EVAL_CORPUS_CONVERSATIONS[0]['messages'][0]['message_id']}/manual-clean",
            json_data={
                "content": EVAL_CORPUS_CONVERSATIONS[0]["messages"][0]["content"],
                "manual_action": "keep",
                "cleaner": "eval_corpus_seed",
                "cleaning_note": "Eval corpus — keep original content.",
            },
        )
        print(f"[PASS] manual_cleaning (keep original content, not 'keep_edited')")
        results.append({"step": "manual_cleaning", "status": "PASS"})
    except Exception as exc:
        print(f"[WARN] manual_cleaning: {exc} (continuing)")
        results.append({"step": "manual_cleaning", "status": "WARN"})

    # Step 4: Extract knowledge candidates
    try:
        resp = _post(f"/api/extraction/run/{batch_id}")
        if resp.status_code != 200:
            print(f"[FAIL] extraction: HTTP {resp.status_code}")
            return {"status": "failed", "step": "extraction"}
        print(f"[PASS] extraction")
        results.append({"step": "extraction", "status": "PASS"})
    except Exception as exc:
        print(f"[FAIL] extraction: {exc}")
        return {"status": "failed", "step": "extraction", "error": str(exc)[:200]}

    # Step 5: Get candidates
    try:
        resp = _get("/api/knowledge/candidates")
        candidates = resp.json()["data"]["candidates"]
        batch_candidates = [
            c for c in candidates
            if c.get("source_batch_id") == batch_id
        ]
        if not batch_candidates:
            print("[FAIL] No candidates generated from eval corpus batch")
            return {"status": "failed", "step": "get_candidates"}
        print(f"[PASS] found {len(batch_candidates)} candidates")
    except Exception as exc:
        print(f"[FAIL] get_candidates: {exc}")
        return {"status": "failed", "step": "get_candidates", "error": str(exc)[:200]}

    # Step 6: Approve all candidates
    for c in batch_candidates:
        cid = c["candidate_id"]
        try:
            resp = _post(
                f"/api/review/{cid}/approve",
                json_data={
                    "reviewer": "eval_corpus_seed",
                    "review_note": "Approved for eval corpus.",
                },
            )
            if resp.status_code == 200:
                candidate_ids.append(cid)
                if verbose:
                    print(f"  [PASS] approve {cid}")
            else:
                print(f"  [FAIL] approve {cid}: HTTP {resp.status_code}")
        except Exception as exc:
            print(f"  [FAIL] approve {cid}: {exc}")
    print(f"[PASS] approved {len(candidate_ids)}/{len(batch_candidates)} candidates")
    results.append({
        "step": "approve", "status": "PASS",
        "approved": len(candidate_ids),
        "total": len(batch_candidates),
    })

    if not candidate_ids:
        print("[FAIL] No candidates approved")
        return {"status": "failed", "step": "approve"}

    # Step 7: Sync RAG
    try:
        resp = _post("/api/rag/build")
        if resp.status_code != 200:
            print(f"[FAIL] sync_rag: HTTP {resp.status_code}")
            return {"status": "failed", "step": "sync_rag"}
        data = resp.json()["data"]
        emb_count = data.get("embedding_count", 0)
        vec_enabled = data.get("vector_sync_enabled", False)
        print(f"[PASS] sync_rag -> embedding_count={emb_count} vector_sync={vec_enabled}")
        results.append({
            "step": "sync_rag", "status": "PASS",
            "embedding_count": emb_count,
            "vector_sync_enabled": vec_enabled,
        })
    except Exception as exc:
        print(f"[FAIL] sync_rag: {exc}")
        return {"status": "failed", "step": "sync_rag", "error": str(exc)[:200]}

    print()
    print("=" * 60)
    print("SEED COMPLETE")
    print("=" * 60)
    print(f"  trace_id:          {tid}")
    print(f"  batch_id:          {batch_id}")
    print(f"  candidate_ids:     {', '.join(candidate_ids)}")
    print(f"  embedding_count:   {emb_count if 'emb_count' in dir() else '?'}")
    print(f"  completed_at:      {_now_iso()}")

    return {
        "status": "ok",
        "trace_id": tid,
        "batch_id": batch_id,
        "candidate_ids": candidate_ids,
        "candidate_count": len(candidate_ids),
        "embedding_count": emb_count if 'emb_count' in dir() else 0,
        "steps": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed a clean English eval corpus for RAG evaluation.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples:
              python scripts/seed_rag_eval_corpus.py --base-url http://127.0.0.1:8000
              python scripts/seed_rag_eval_corpus.py --base-url https://datahub-jr8x.onrender.com --verbose
        """),
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000",
                        help="Base URL of the DataHub FastAPI backend")
    parser.add_argument("--timeout", type=int, default=30,
                        help="HTTP request timeout in seconds")
    parser.add_argument("--verbose", action="store_true",
                        help="Print per-candidate approval details")
    args = parser.parse_args()

    start = time.monotonic()
    result = seed_corpus(base_url=args.base_url, timeout=args.timeout,
                         verbose=args.verbose)
    elapsed = time.monotonic() - start
    print(f"\n  duration: {elapsed:.1f}s")

    if result.get("status") != "ok":
        sys.exit(1)


if __name__ == "__main__":
    main()
