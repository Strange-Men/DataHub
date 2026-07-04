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


class PhaseOneFlowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        self.sample = json.loads(
            (ROOT_DIR / "samples" / "customer_chat_sample.json").read_text(
                encoding="utf-8"
            )
        )

    def _headers(self) -> dict[str, str]:
        return {"X-DataHub-Client": "CustomerOpsAgent"}

    def _create_batch_candidates(self, source_name: str) -> list[dict[str, object]]:
        payload = dict(self.sample)
        payload["source_name"] = source_name

        imported = self.client.post("/api/sources/import-json", json=payload)
        self.assertEqual(imported.status_code, 200, imported.text)
        batch_id = imported.json()["data"]["batch_id"]

        cleaned = self.client.post(f"/api/cleaning/run/{batch_id}")
        self.assertEqual(cleaned.status_code, 200, cleaned.text)
        self.assertEqual(cleaned.json()["data"]["status"], "completed")

        sanitized = self.client.get(f"/api/sanitized/{batch_id}")
        self.assertEqual(sanitized.status_code, 200, sanitized.text)
        self.assertEqual(sanitized.json()["data"]["status"], "sanitized")

        extracted = self.client.post(f"/api/extraction/run/{batch_id}")
        self.assertEqual(extracted.status_code, 200, extracted.text)

        candidates = self.client.get("/api/knowledge/candidates")
        self.assertEqual(candidates.status_code, 200, candidates.text)
        batch_candidates = [
            candidate
            for candidate in candidates.json()["data"]["candidates"]
            if candidate["source_batch_id"] == batch_id
        ]
        self.assertGreaterEqual(len(batch_candidates), 1)
        return batch_candidates

    def _prepare_candidate(
        self,
        candidate: dict[str, object],
        unique_term: str,
        status: str,
    ) -> str:
        candidate_id = str(candidate["candidate_id"])
        updated = self.client.patch(
            f"/api/knowledge/candidates/{candidate_id}",
            json={
                "question": f"How should DataHub answer {unique_term}?",
                "answer": f"{unique_term} controlled customer support answer.",
                "intent": "order_status",
                "tags": ["order", "tracking", unique_term],
                "risk_level": "medium",
                "quality_score": 0.82,
            },
        )
        self.assertEqual(updated.status_code, 200, updated.text)

        if status == "approved":
            reviewed = self.client.post(
                f"/api/review/{candidate_id}/approve",
                json={
                    "reviewer": "p1_m9_flow",
                    "review_note": "Approved for P1-M9 flow verification.",
                },
            )
        elif status == "rejected":
            reviewed = self.client.post(
                f"/api/review/{candidate_id}/reject",
                json={
                    "reviewer": "p1_m9_flow",
                    "review_note": "Rejected for P1-M9 exclusion verification.",
                },
            )
        else:
            reviewed = self.client.post(
                f"/api/review/{candidate_id}/needs-revision",
                json={
                    "reviewer": "p1_m9_flow",
                    "review_note": "Needs revision for P1-M9 exclusion verification.",
                },
            )
        self.assertEqual(reviewed.status_code, 200, reviewed.text)
        return candidate_id

    def test_phase_one_core_loop_freeze(self) -> None:
        health = self.client.get("/health")
        self.assertEqual(health.status_code, 200, health.text)
        self.assertEqual(health.json()["phase"], "P1-M15")

        approved_candidate = self._create_batch_candidates("p1_m9_approved")[0]
        rejected_candidate = self._create_batch_candidates("p1_m9_rejected")[0]
        revision_candidate = self._create_batch_candidates("p1_m9_revision")[0]

        approved_term = f"p1m9approved{approved_candidate['candidate_id'][-6:]}"
        rejected_term = f"p1m9rejected{rejected_candidate['candidate_id'][-6:]}"
        revision_term = f"p1m9revision{revision_candidate['candidate_id'][-6:]}"

        approved_id = self._prepare_candidate(
            approved_candidate,
            approved_term,
            "approved",
        )
        rejected_id = self._prepare_candidate(
            rejected_candidate,
            rejected_term,
            "rejected",
        )
        revision_id = self._prepare_candidate(
            revision_candidate,
            revision_term,
            "needs_revision",
        )

        built = self.client.post("/api/rag/build")
        self.assertEqual(built.status_code, 200, built.text)

        chunks = self.client.get("/api/rag/chunks")
        self.assertEqual(chunks.status_code, 200, chunks.text)
        chunk_list = chunks.json()["data"]["chunks"]
        chunk_ids = {chunk["chunk_id"] for chunk in chunk_list}
        chunk_candidate_ids = {chunk["candidate_id"] for chunk in chunk_list}
        self.assertIn(approved_id, chunk_candidate_ids)
        self.assertNotIn(rejected_id, chunk_candidate_ids)
        self.assertNotIn(revision_id, chunk_candidate_ids)

        retrieved = self.client.post(
            "/api/customer-ops-agent/retrieve",
            headers=self._headers(),
            json={"query": approved_term, "top_k": 5},
        )
        self.assertEqual(retrieved.status_code, 200, retrieved.text)
        retrieval_data = retrieved.json()["data"]
        self.assertTrue(retrieval_data["retrieval_id"].startswith("retrieval_"))
        self.assertGreaterEqual(len(retrieval_data["results"]), 1)
        self.assertTrue(
            all(result["review_status"] == "approved" for result in retrieval_data["results"])
        )
        self.assertIn(
            approved_id,
            {result["candidate_id"] for result in retrieval_data["results"]},
        )

        rejected_retrieval = self.client.post(
            "/api/customer-ops-agent/retrieve",
            headers=self._headers(),
            json={"query": rejected_term, "top_k": 5},
        )
        self.assertEqual(rejected_retrieval.status_code, 200, rejected_retrieval.text)
        self.assertNotIn(
            rejected_id,
            {
                result["candidate_id"]
                for result in rejected_retrieval.json()["data"]["results"]
            },
        )

        revision_retrieval = self.client.post(
            "/api/customer-ops-agent/retrieve",
            headers=self._headers(),
            json={"query": revision_term, "top_k": 5},
        )
        self.assertEqual(revision_retrieval.status_code, 200, revision_retrieval.text)
        self.assertNotIn(
            revision_id,
            {
                result["candidate_id"]
                for result in revision_retrieval.json()["data"]["results"]
            },
        )

        bad_case = self.client.post(
            "/api/customer-ops-agent/bad-cases",
            headers=self._headers(),
            json={
                "retrieval_id": retrieval_data["retrieval_id"],
                "user_query": "Where is my order?",
                "agent_answer": "Your package should arrive soon.",
                "issue_type": "wrong_answer",
                "expected_answer": (
                    "Please provide your order number or tracking number. "
                    "If tracking is unavailable, we will escalate this to a human agent."
                ),
                "severity": "medium",
            },
        )
        self.assertEqual(bad_case.status_code, 200, bad_case.text)
        bad_case_data = bad_case.json()["data"]
        self.assertEqual(bad_case_data["status"], "open")

        chunks_before_draft = {
            chunk["chunk_id"]: chunk["chunk_text"]
            for chunk in self.client.get("/api/rag/chunks").json()["data"]["chunks"]
        }

        draft = self.client.post(
            f"/api/bad-cases/{bad_case_data['bad_case_id']}/create-draft",
            json={
                "question": "Where is my order?",
                "answer": (
                    "Please provide your order number or tracking number. "
                    "If tracking is unavailable, we will escalate this to a human agent."
                ),
                "intent": "order_status",
                "tags": ["order", "tracking", "handoff"],
                "risk_level": "medium",
                "quality_score": 0.7,
                "knowledge_type": "faq",
                "reviewer": "p1_m9_flow",
                "review_note": "Created from Bad Case during P1-M9 release verification.",
            },
        )
        self.assertEqual(draft.status_code, 200, draft.text)
        draft_candidate = draft.json()["data"]
        self.assertEqual(draft_candidate["review_status"], "pending_review")
        self.assertEqual(draft_candidate["source_type"], "bad_case")
        self.assertEqual(
            draft_candidate["source_bad_case_id"],
            bad_case_data["bad_case_id"],
        )
        self.assertEqual(
            draft_candidate["source_retrieval_id"],
            retrieval_data["retrieval_id"],
        )
        self.assertEqual(draft_candidate["extraction_method"], "bad_case_resolution")

        updated_bad_case = self.client.get(
            f"/api/bad-cases/{bad_case_data['bad_case_id']}"
        )
        self.assertEqual(updated_bad_case.status_code, 200, updated_bad_case.text)
        self.assertEqual(
            updated_bad_case.json()["data"]["linked_candidate_id"],
            draft_candidate["candidate_id"],
        )

        chunks_after_draft = {
            chunk["chunk_id"]: chunk["chunk_text"]
            for chunk in self.client.get("/api/rag/chunks").json()["data"]["chunks"]
        }
        self.assertEqual(chunks_after_draft, chunks_before_draft)
        self.assertEqual(set(chunks_after_draft), chunk_ids)
        self.assertNotIn(f"chunk_{draft_candidate['candidate_id']}", chunks_after_draft)


if __name__ == "__main__":
    unittest.main()
