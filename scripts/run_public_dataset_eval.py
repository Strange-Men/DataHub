"""Run a lightweight DataHub P1 evaluation against a converted public sample."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient


ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.main import app  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the DataHub P1 public dataset evaluation flow.",
    )
    parser.add_argument(
        "--sample",
        default=str(ROOT_DIR / "samples" / "public_dataset_eval_sample.json"),
        help="Path to a DataHub import JSON sample.",
    )
    parser.add_argument(
        "--approve-count",
        type=int,
        default=10,
        help="Number of extracted candidates to approve for local RAG evaluation.",
    )
    parser.add_argument(
        "--query",
        default="cancel order",
        help="Retrieval query used for the CustomerOpsAgent test.",
    )
    return parser.parse_args()


def _load_sample(path: Path) -> dict[str, object]:
    if not path.exists():
        raise FileNotFoundError(f"Sample JSON not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _headers() -> dict[str, str]:
    return {"X-DataHub-Client": "CustomerOpsAgent"}


def run_eval(sample_path: Path, approve_count: int, query: str) -> dict[str, object]:
    client = TestClient(app)
    sample = _load_sample(sample_path)
    conversations = sample.get("conversations", [])
    if not isinstance(conversations, list) or not conversations:
        raise ValueError("Sample JSON must contain non-empty conversations.")

    imported = client.post("/api/sources/import-json", json=sample)
    imported.raise_for_status()
    batch = imported.json()["data"]
    batch_id = batch["batch_id"]

    cleaned = client.post(f"/api/cleaning/run/{batch_id}")
    cleaned.raise_for_status()
    cleaning = cleaned.json()["data"]

    extracted = client.post(f"/api/extraction/run/{batch_id}")
    extracted.raise_for_status()
    extraction = extracted.json()["data"]

    candidates = client.get("/api/knowledge/candidates")
    candidates.raise_for_status()
    batch_candidates = [
        candidate
        for candidate in candidates.json()["data"]["candidates"]
        if candidate["source_batch_id"] == batch_id
    ]
    if not batch_candidates:
        raise AssertionError("No candidates were extracted from the public sample.")

    approved_ids: list[str] = []
    for candidate in batch_candidates[:approve_count]:
        candidate_id = candidate["candidate_id"]
        approved = client.post(
            f"/api/review/{candidate_id}/approve",
            json={
                "reviewer": "public_dataset_eval",
                "review_note": "Controlled approval for P1-M9.5 evaluation.",
            },
        )
        approved.raise_for_status()
        approved_ids.append(candidate_id)

    built = client.post("/api/rag/build")
    built.raise_for_status()
    build = built.json()["data"]

    chunks = client.get("/api/rag/chunks")
    chunks.raise_for_status()
    sample_chunks = [
        chunk
        for chunk in chunks.json()["data"]["chunks"]
        if chunk["candidate_id"] in approved_ids
    ]

    retrieved = client.post(
        "/api/customer-ops-agent/retrieve",
        headers=_headers(),
        json={"query": query, "top_k": 5},
    )
    retrieved.raise_for_status()
    retrieval = retrieved.json()["data"]

    bad_case = client.post(
        "/api/customer-ops-agent/bad-cases",
        headers=_headers(),
        json={
            "retrieval_id": retrieval["retrieval_id"],
            "user_query": query,
            "agent_answer": "The current answer missed the exact cancellation step.",
            "issue_type": "retrieval_miss",
            "expected_answer": "The answer should explain how to cancel an order and when to escalate.",
            "severity": "medium",
            "conversation_id": "public_eval_bad_case",
            "agent_session_id": "public_eval_session",
            "metadata": {"dataset": "bitext_customer_support"},
        },
    )
    bad_case.raise_for_status()
    bad_case_data = bad_case.json()["data"]

    draft = client.post(
        f"/api/bad-cases/{bad_case_data['bad_case_id']}/create-draft",
        json={
            "question": "How can a customer cancel an order?",
            "answer": (
                "Ask for the order number, verify whether the order is still "
                "eligible for cancellation, and escalate to a human agent if "
                "the order has already shipped."
            ),
            "intent": "order_status",
            "tags": ["order", "cancel", "handoff"],
            "risk_level": "medium",
            "quality_score": 0.7,
            "knowledge_type": "faq",
            "reviewer": "public_dataset_eval",
            "review_note": "Created from public dataset Bad Case evaluation.",
        },
    )
    draft.raise_for_status()
    draft_data = draft.json()["data"]

    return {
        "dataset_name": "Bitext customer support dataset",
        "sample_path": str(sample_path),
        "source_name": sample.get("source_name"),
        "raw_conversation_count": batch["conversation_count"],
        "raw_message_count": batch["message_count"],
        "sanitized_message_count": cleaning["sanitized_message_count"],
        "dropped_message_count": cleaning["dropped_message_count"],
        "candidate_count": extraction["candidate_count"],
        "approved_count": len(approved_ids),
        "rag_chunk_count": len(sample_chunks),
        "retrieval_test_count": 1,
        "retrieval_hit_count": len(retrieval["results"]),
        "bad_case_count": 1,
        "bad_case_to_draft_count": 1,
        "retrieval_id": retrieval["retrieval_id"],
        "bad_case_id": bad_case_data["bad_case_id"],
        "draft_candidate_id": draft_data["candidate_id"],
        "draft_review_status": draft_data["review_status"],
        "build_status": build["status"],
        "retrieval_mode": retrieval["retrieval_mode"],
    }


def main() -> int:
    args = _parse_args()
    metrics = run_eval(
        sample_path=Path(args.sample),
        approve_count=args.approve_count,
        query=args.query,
    )
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
