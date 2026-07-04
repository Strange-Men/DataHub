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


class BadCaseFeedbackTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        self.sample = json.loads(
            (ROOT_DIR / "samples" / "customer_chat_sample.json").read_text(
                encoding="utf-8"
            )
        )

    def _customerops_headers(self) -> dict[str, str]:
        return {"X-DataHub-Client": "CustomerOpsAgent"}

    def _assert_customerops_error(
        self,
        response,
        status_code: int,
        code: str,
    ) -> None:
        self.assertEqual(response.status_code, status_code, response.text)
        body = response.json()
        self.assertFalse(body["success"])
        self.assertEqual(body["error"]["code"], code)
        self.assertIn("message", body["error"])
        self.assertTrue(body["requestId"].startswith("req_"))

    def _assert_api_error(
        self,
        response,
        status_code: int,
        code: str,
    ) -> None:
        self.assertEqual(response.status_code, status_code, response.text)
        self.assertEqual(response.json()["detail"]["code"], code)

    def _create_retrieval(self) -> tuple[str, list[str]]:
        payload = dict(self.sample)
        payload["source_name"] = "bad_case_feedback_test"

        imported = self.client.post("/api/sources/import-json", json=payload)
        self.assertEqual(imported.status_code, 200, imported.text)
        batch_id = imported.json()["data"]["batch_id"]

        cleaned = self.client.post(f"/api/cleaning/run/{batch_id}")
        self.assertEqual(cleaned.status_code, 200, cleaned.text)

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
        candidate_id = batch_candidates[0]["candidate_id"]
        unique_term = f"m8badcase{candidate_id[-6:]}"

        updated = self.client.patch(
            f"/api/knowledge/candidates/{candidate_id}",
            json={
                "question": f"How should we answer {unique_term}?",
                "answer": f"{unique_term} approved answer with tracking guidance.",
                "intent": "order_status",
                "tags": ["order", "tracking", unique_term],
                "risk_level": "low",
                "quality_score": 0.9,
            },
        )
        self.assertEqual(updated.status_code, 200, updated.text)

        approved = self.client.post(
            f"/api/review/{candidate_id}/approve",
            json={
                "reviewer": "bad_case_test",
                "review_note": "Approved for M8 retrieval binding.",
            },
        )
        self.assertEqual(approved.status_code, 200, approved.text)

        built = self.client.post("/api/rag/build")
        self.assertEqual(built.status_code, 200, built.text)

        retrieved = self.client.post(
            "/api/customer-ops-agent/retrieve",
            headers=self._customerops_headers(),
            json={
                "query": unique_term,
                "top_k": 5,
                "conversation_id": "conv_bad_case_test",
                "agent_session_id": "session_bad_case_test",
            },
        )
        self.assertEqual(retrieved.status_code, 200, retrieved.text)
        retrieval_data = retrieved.json()["data"]
        self.assertGreaterEqual(len(retrieval_data["results"]), 1)
        return (
            retrieval_data["retrieval_id"],
            [result["chunk_id"] for result in retrieval_data["results"]],
        )

    def _valid_bad_case_payload(self, retrieval_id: str) -> dict[str, object]:
        return {
            "retrieval_id": retrieval_id,
            "user_query": "Where is my order?",
            "agent_answer": "Your package should arrive soon.",
            "issue_type": "wrong_answer",
            "expected_answer": "The answer should mention tracking status or escalation.",
            "severity": "medium",
            "conversation_id": "conv_bad_case_test",
            "agent_session_id": "session_bad_case_test",
            "metadata": {
                "channel": "web_chat",
                "language": "en",
            },
        }

    def test_bad_case_feedback_queue_does_not_mutate_knowledge_or_rag(self) -> None:
        health = self.client.get("/health")
        self.assertEqual(health.status_code, 200, health.text)
        self.assertEqual(health.json()["phase"], "P1-M19")

        retrieval_id, linked_chunk_ids = self._create_retrieval()
        payload = self._valid_bad_case_payload(retrieval_id)

        missing_header = self.client.post(
            "/api/customer-ops-agent/bad-cases",
            json=payload,
        )
        self._assert_customerops_error(
            missing_header,
            401,
            "UNAUTHORIZED_CLIENT",
        )

        wrong_header = self.client.post(
            "/api/customer-ops-agent/bad-cases",
            headers={"X-DataHub-Client": "OtherAgent"},
            json=payload,
        )
        self._assert_customerops_error(
            wrong_header,
            401,
            "UNAUTHORIZED_CLIENT",
        )

        invalid_retrieval = self.client.post(
            "/api/customer-ops-agent/bad-cases",
            headers=self._customerops_headers(),
            json={**payload, "retrieval_id": "retrieval_missing"},
        )
        self._assert_customerops_error(
            invalid_retrieval,
            404,
            "INVALID_RETRIEVAL_REFERENCE",
        )

        empty_query = self.client.post(
            "/api/customer-ops-agent/bad-cases",
            headers=self._customerops_headers(),
            json={**payload, "user_query": "   "},
        )
        self._assert_customerops_error(empty_query, 400, "INVALID_USER_QUERY")

        long_query = self.client.post(
            "/api/customer-ops-agent/bad-cases",
            headers=self._customerops_headers(),
            json={**payload, "user_query": "x" * 501},
        )
        self._assert_customerops_error(long_query, 400, "USER_QUERY_TOO_LONG")

        empty_answer = self.client.post(
            "/api/customer-ops-agent/bad-cases",
            headers=self._customerops_headers(),
            json={**payload, "agent_answer": "   "},
        )
        self._assert_customerops_error(empty_answer, 400, "INVALID_AGENT_ANSWER")

        long_answer = self.client.post(
            "/api/customer-ops-agent/bad-cases",
            headers=self._customerops_headers(),
            json={**payload, "agent_answer": "x" * 2001},
        )
        self._assert_customerops_error(long_answer, 400, "AGENT_ANSWER_TOO_LONG")

        bad_issue = self.client.post(
            "/api/customer-ops-agent/bad-cases",
            headers=self._customerops_headers(),
            json={**payload, "issue_type": "unsupported_issue"},
        )
        self._assert_customerops_error(bad_issue, 400, "INVALID_ISSUE_TYPE")

        bad_severity = self.client.post(
            "/api/customer-ops-agent/bad-cases",
            headers=self._customerops_headers(),
            json={**payload, "severity": "critical"},
        )
        self._assert_customerops_error(bad_severity, 400, "INVALID_SEVERITY")

        candidates_before = self.client.get("/api/knowledge/candidates").json()[
            "data"
        ]["candidates"]
        chunks_before = self.client.get("/api/rag/chunks").json()["data"]["chunks"]

        created = self.client.post(
            "/api/customer-ops-agent/bad-cases",
            headers=self._customerops_headers(),
            json=payload,
        )
        self.assertEqual(created.status_code, 200, created.text)
        bad_case = created.json()["data"]
        self.assertTrue(bad_case["bad_case_id"].startswith("badcase_"))
        self.assertEqual(bad_case["status"], "open")
        self.assertEqual(bad_case["retrieval_id"], retrieval_id)
        self.assertEqual(bad_case["linked_chunk_ids"], linked_chunk_ids)
        self.assertEqual(bad_case["retrieval_result_count"], len(linked_chunk_ids))

        listed = self.client.get("/api/bad-cases")
        self.assertEqual(listed.status_code, 200, listed.text)
        listed_ids = {
            item["bad_case_id"]
            for item in listed.json()["data"]["bad_cases"]
        }
        self.assertIn(bad_case["bad_case_id"], listed_ids)

        detail = self.client.get(f"/api/bad-cases/{bad_case['bad_case_id']}")
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertEqual(detail.json()["data"]["bad_case_id"], bad_case["bad_case_id"])

        patched = self.client.patch(
            f"/api/bad-cases/{bad_case['bad_case_id']}",
            json={
                "status": "triaged",
                "review_note": "Confirmed retrieval miss.",
                "resolution_type": "retrieval_tuning",
                "linked_candidate_id": "kc_manual_reference_only",
            },
        )
        self.assertEqual(patched.status_code, 200, patched.text)
        patched_data = patched.json()["data"]
        self.assertEqual(patched_data["status"], "triaged")
        self.assertEqual(patched_data["review_note"], "Confirmed retrieval miss.")
        self.assertEqual(patched_data["resolution_type"], "retrieval_tuning")
        self.assertEqual(patched_data["linked_candidate_id"], "kc_manual_reference_only")

        candidates_after = self.client.get("/api/knowledge/candidates").json()[
            "data"
        ]["candidates"]
        chunks_after = self.client.get("/api/rag/chunks").json()["data"]["chunks"]
        self.assertEqual(len(candidates_after), len(candidates_before))
        self.assertEqual(
            {candidate["candidate_id"] for candidate in candidates_after},
            {candidate["candidate_id"] for candidate in candidates_before},
        )
        self.assertEqual(
            {chunk["chunk_id"] for chunk in chunks_after},
            {chunk["chunk_id"] for chunk in chunks_before},
        )

        routes = {route.path for route in app.routes}
        self.assertTrue("/api/customer-ops-agent/bad-cases" in routes)
        self.assertTrue("/api/bad-cases" in routes)
        self.assertFalse(any("/embeddings" in path for path in routes))
        self.assertFalse(any("/vector" in path for path in routes))

    def test_bad_case_can_create_pending_review_draft_only(self) -> None:
        retrieval_id, linked_chunk_ids = self._create_retrieval()
        payload = self._valid_bad_case_payload(retrieval_id)

        missing_bad_case = self.client.post(
            "/api/bad-cases/badcase_missing/create-draft",
            json={
                "question": "Where is my order?",
                "answer": "Please provide your order number.",
            },
        )
        self._assert_api_error(missing_bad_case, 404, "BAD_CASE_NOT_FOUND")

        created = self.client.post(
            "/api/customer-ops-agent/bad-cases",
            headers=self._customerops_headers(),
            json=payload,
        )
        self.assertEqual(created.status_code, 200, created.text)
        bad_case = created.json()["data"]
        bad_case_id = bad_case["bad_case_id"]

        empty_question = self.client.post(
            f"/api/bad-cases/{bad_case_id}/create-draft",
            json={
                "question": "   ",
                "answer": "Please provide your order number.",
            },
        )
        self._assert_api_error(empty_question, 400, "INVALID_DRAFT_PAYLOAD")

        empty_answer = self.client.post(
            f"/api/bad-cases/{bad_case_id}/create-draft",
            json={
                "question": "Where is my order?",
                "answer": "   ",
            },
        )
        self._assert_api_error(empty_answer, 400, "INVALID_DRAFT_PAYLOAD")

        bad_score = self.client.post(
            f"/api/bad-cases/{bad_case_id}/create-draft",
            json={
                "question": "Where is my order?",
                "answer": "Please provide your order number.",
                "quality_score": 1.2,
            },
        )
        self._assert_api_error(bad_score, 400, "INVALID_DRAFT_PAYLOAD")

        ignored_created = self.client.post(
            "/api/customer-ops-agent/bad-cases",
            headers=self._customerops_headers(),
            json={**payload, "user_query": "Ignored Bad Case test"},
        )
        self.assertEqual(ignored_created.status_code, 200, ignored_created.text)
        ignored_id = ignored_created.json()["data"]["bad_case_id"]
        ignored_patch = self.client.patch(
            f"/api/bad-cases/{ignored_id}",
            json={
                "status": "ignored",
                "review_note": "Not actionable.",
                "resolution_type": "ignore",
            },
        )
        self.assertEqual(ignored_patch.status_code, 200, ignored_patch.text)
        ignored_draft = self.client.post(
            f"/api/bad-cases/{ignored_id}/create-draft",
            json={
                "question": "Should not create?",
                "answer": "Ignored Bad Cases cannot create drafts.",
            },
        )
        self._assert_api_error(ignored_draft, 400, "BAD_CASE_IGNORED")

        candidates_before = self.client.get("/api/knowledge/candidates").json()[
            "data"
        ]["candidates"]
        chunks_before = self.client.get("/api/rag/chunks").json()["data"]["chunks"]
        existing_candidate_ids = {
            candidate["candidate_id"] for candidate in candidates_before
        }
        chunk_snapshot = {
            chunk["chunk_id"]: chunk["chunk_text"]
            for chunk in chunks_before
        }

        draft = self.client.post(
            f"/api/bad-cases/{bad_case_id}/create-draft",
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
                "reviewer": "local_reviewer",
                "review_note": "Created from Bad Case after human correction.",
            },
        )
        self.assertEqual(draft.status_code, 200, draft.text)
        candidate = draft.json()["data"]
        self.assertTrue(candidate["candidate_id"].startswith("kc_badcase_"))
        self.assertEqual(candidate["review_status"], "pending_review")
        self.assertEqual(candidate["source_type"], "bad_case")
        self.assertEqual(candidate["source_bad_case_id"], bad_case_id)
        self.assertEqual(candidate["source_retrieval_id"], retrieval_id)
        self.assertEqual(candidate["source_chunk_ids"], linked_chunk_ids)
        self.assertEqual(candidate["extraction_method"], "bad_case_resolution")

        candidate_detail = self.client.get(
            f"/api/knowledge/candidates/{candidate['candidate_id']}"
        )
        self.assertEqual(candidate_detail.status_code, 200, candidate_detail.text)
        self.assertEqual(
            candidate_detail.json()["data"]["review_status"],
            "pending_review",
        )

        updated_bad_case = self.client.get(f"/api/bad-cases/{bad_case_id}")
        self.assertEqual(updated_bad_case.status_code, 200, updated_bad_case.text)
        updated_bad_case_data = updated_bad_case.json()["data"]
        self.assertEqual(
            updated_bad_case_data["linked_candidate_id"],
            candidate["candidate_id"],
        )
        self.assertEqual(updated_bad_case_data["status"], "resolved")

        candidates_after = self.client.get("/api/knowledge/candidates").json()[
            "data"
        ]["candidates"]
        self.assertEqual(len(candidates_after), len(candidates_before) + 1)
        for existing in candidates_after:
            if existing["candidate_id"] in existing_candidate_ids:
                before = next(
                    item
                    for item in candidates_before
                    if item["candidate_id"] == existing["candidate_id"]
                )
                self.assertEqual(existing["review_status"], before["review_status"])

        chunks_after = self.client.get("/api/rag/chunks").json()["data"]["chunks"]
        self.assertEqual(
            {chunk["chunk_id"]: chunk["chunk_text"] for chunk in chunks_after},
            chunk_snapshot,
        )
        self.assertNotIn(
            f"chunk_{candidate['candidate_id']}",
            {chunk["chunk_id"] for chunk in chunks_after},
        )

        manual_build = self.client.post("/api/rag/build")
        self.assertEqual(manual_build.status_code, 200, manual_build.text)
        rebuilt_chunks = self.client.get("/api/rag/chunks").json()["data"]["chunks"]
        self.assertNotIn(
            f"chunk_{candidate['candidate_id']}",
            {chunk["chunk_id"] for chunk in rebuilt_chunks},
        )


if __name__ == "__main__":
    unittest.main()
