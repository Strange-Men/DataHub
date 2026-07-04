import json
import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.main import app  # noqa: E402


class PublicDatasetEvalFlowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        self.sample_path = ROOT_DIR / "samples" / "public_dataset_eval_sample.json"
        self.sample = json.loads(self.sample_path.read_text(encoding="utf-8"))

    def _headers(self) -> dict[str, str]:
        return {"X-DataHub-Client": "CustomerOpsAgent"}

    def test_public_dataset_sample_runs_through_p1_loop(self) -> None:
        self.assertEqual(
            self.sample["source_name"],
            "public_dataset_eval_bitext_sample",
        )
        self.assertEqual(len(self.sample["conversations"]), 50)

        imported = self.client.post("/api/sources/import-json", json=self.sample)
        self.assertEqual(imported.status_code, 200, imported.text)
        batch = imported.json()["data"]
        batch_id = batch["batch_id"]
        self.assertEqual(batch["conversation_count"], 50)
        self.assertEqual(batch["message_count"], 100)

        cleaned = self.client.post(f"/api/cleaning/run/{batch_id}")
        self.assertEqual(cleaned.status_code, 200, cleaned.text)
        cleaning = cleaned.json()["data"]
        self.assertEqual(cleaning["sanitized_message_count"], 100)
        self.assertEqual(cleaning["dropped_message_count"], 0)

        extracted = self.client.post(f"/api/extraction/run/{batch_id}")
        self.assertEqual(extracted.status_code, 200, extracted.text)
        extraction = extracted.json()["data"]
        self.assertEqual(extraction["candidate_count"], 50)

        candidates = self.client.get("/api/knowledge/candidates")
        self.assertEqual(candidates.status_code, 200, candidates.text)
        batch_candidates = [
            candidate
            for candidate in candidates.json()["data"]["candidates"]
            if candidate["source_batch_id"] == batch_id
        ]
        self.assertEqual(len(batch_candidates), 50)

        approved_ids: list[str] = []
        rejected_id = batch_candidates[10]["candidate_id"]
        revision_id = batch_candidates[11]["candidate_id"]
        for candidate in batch_candidates[:10]:
            response = self.client.post(
                f"/api/review/{candidate['candidate_id']}/approve",
                json={
                    "reviewer": "public_dataset_eval_test",
                    "review_note": "Controlled approval for public dataset evaluation.",
                },
            )
            self.assertEqual(response.status_code, 200, response.text)
            approved_ids.append(candidate["candidate_id"])

        rejected = self.client.post(
            f"/api/review/{rejected_id}/reject",
            json={
                "reviewer": "public_dataset_eval_test",
                "review_note": "Rejected to verify RAG exclusion.",
            },
        )
        self.assertEqual(rejected.status_code, 200, rejected.text)

        needs_revision = self.client.post(
            f"/api/review/{revision_id}/needs-revision",
            json={
                "reviewer": "public_dataset_eval_test",
                "review_note": "Needs revision to verify RAG exclusion.",
            },
        )
        self.assertEqual(needs_revision.status_code, 200, needs_revision.text)

        built = self.client.post("/api/rag/build")
        self.assertEqual(built.status_code, 200, built.text)
        self.assertEqual(built.json()["data"]["status"], "completed")

        chunks = self.client.get("/api/rag/chunks")
        self.assertEqual(chunks.status_code, 200, chunks.text)
        chunk_candidate_ids = {
            chunk["candidate_id"]
            for chunk in chunks.json()["data"]["chunks"]
        }
        for candidate_id in approved_ids:
            self.assertIn(candidate_id, chunk_candidate_ids)
        self.assertNotIn(rejected_id, chunk_candidate_ids)
        self.assertNotIn(revision_id, chunk_candidate_ids)

        retrieved = self.client.post(
            "/api/customer-ops-agent/retrieve",
            headers=self._headers(),
            json={"query": "cancel order", "top_k": 5},
        )
        self.assertEqual(retrieved.status_code, 200, retrieved.text)
        retrieval = retrieved.json()["data"]
        self.assertTrue(retrieval["retrieval_id"].startswith("retrieval_"))
        self.assertEqual(retrieval["retrieval_mode"], "customerops_local_mock_retrieval")
        self.assertGreaterEqual(len(retrieval["results"]), 1)
        self.assertTrue(
            all(result["review_status"] == "approved" for result in retrieval["results"])
        )

        bad_case = self.client.post(
            "/api/customer-ops-agent/bad-cases",
            headers=self._headers(),
            json={
                "retrieval_id": retrieval["retrieval_id"],
                "user_query": "cancel order",
                "agent_answer": "The current answer missed the exact cancellation step.",
                "issue_type": "retrieval_miss",
                "expected_answer": (
                    "The answer should explain how to cancel an order and "
                    "when to escalate."
                ),
                "severity": "medium",
                "conversation_id": "public_eval_bad_case",
                "agent_session_id": "public_eval_session",
                "metadata": {"dataset": "bitext_customer_support"},
            },
        )
        self.assertEqual(bad_case.status_code, 200, bad_case.text)
        bad_case_data = bad_case.json()["data"]
        self.assertEqual(bad_case_data["status"], "open")
        self.assertGreaterEqual(bad_case_data["retrieval_result_count"], 1)

        chunks_before_draft = {
            chunk["chunk_id"]: chunk["chunk_text"]
            for chunk in self.client.get("/api/rag/chunks").json()["data"]["chunks"]
        }
        draft = self.client.post(
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
                "reviewer": "public_dataset_eval_test",
                "review_note": "Created from public dataset Bad Case evaluation.",
            },
        )
        self.assertEqual(draft.status_code, 200, draft.text)
        draft_data = draft.json()["data"]
        self.assertEqual(draft_data["review_status"], "pending_review")
        self.assertEqual(draft_data["source_type"], "bad_case")
        self.assertEqual(draft_data["source_bad_case_id"], bad_case_data["bad_case_id"])
        self.assertEqual(draft_data["source_retrieval_id"], retrieval["retrieval_id"])
        self.assertEqual(draft_data["extraction_method"], "bad_case_resolution")

        chunks_after_draft = {
            chunk["chunk_id"]: chunk["chunk_text"]
            for chunk in self.client.get("/api/rag/chunks").json()["data"]["chunks"]
        }
        self.assertEqual(chunks_after_draft, chunks_before_draft)
        self.assertNotIn(f"chunk_{draft_data['candidate_id']}", chunks_after_draft)


if __name__ == "__main__":
    unittest.main()
