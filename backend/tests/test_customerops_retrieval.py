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


class CustomerOpsRetrievalTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        self.sample = json.loads(
            (ROOT_DIR / "samples" / "customer_chat_sample.json").read_text(
                encoding="utf-8"
            )
        )

    def _create_candidates(self, suffix: str) -> list[dict[str, object]]:
        payload = dict(self.sample)
        payload["source_name"] = f"customerops_retrieval_{suffix}"

        imported = self.client.post("/api/sources/import-json", json=payload)
        self.assertEqual(imported.status_code, 200, imported.text)
        batch_id = imported.json()["data"]["batch_id"]

        cleaned = self.client.post(f"/api/cleaning/run/{batch_id}")
        self.assertEqual(cleaned.status_code, 200, cleaned.text)

        extracted = self.client.post(f"/api/extraction/run/{batch_id}")
        self.assertEqual(extracted.status_code, 200, extracted.text)

        candidates = self.client.get("/api/knowledge/candidates")
        self.assertEqual(candidates.status_code, 200, candidates.text)
        return [
            candidate
            for candidate in candidates.json()["data"]["candidates"]
            if candidate["source_batch_id"] == batch_id
        ]

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
        self.assertEqual(body["error"]["details"], {})
        self.assertTrue(body["requestId"].startswith("req_"))

    def test_customerops_retrieval_is_restricted_and_traceable(self) -> None:
        health = self.client.get("/health")
        self.assertEqual(health.status_code, 200, health.text)
        self.assertEqual(health.json()["phase"], "P1-M10")

        candidates = [
            *self._create_candidates("a"),
            *self._create_candidates("b"),
            *self._create_candidates("c"),
            *self._create_candidates("d"),
        ]
        self.assertGreaterEqual(len(candidates), 4)

        approve_id = candidates[0]["candidate_id"]
        reject_id = candidates[1]["candidate_id"]
        revision_id = candidates[2]["candidate_id"]
        pending_id = candidates[3]["candidate_id"]
        unique_term = f"m7unique{approve_id[-6:]}"

        updated = self.client.patch(
            f"/api/knowledge/candidates/{approve_id}",
            json={
                "question": f"How should CustomerOps answer {unique_term}?",
                "answer": f"{unique_term} shipping support answer.",
                "intent": "shipping",
                "tags": ["shipping", unique_term],
                "risk_level": "low",
                "quality_score": 0.91,
            },
        )
        self.assertEqual(updated.status_code, 200, updated.text)

        approved = self.client.post(
            f"/api/review/{approve_id}/approve",
            json={
                "reviewer": "customerops_test",
                "review_note": "Approved for CustomerOps retrieval.",
            },
        )
        self.assertEqual(approved.status_code, 200, approved.text)

        rejected = self.client.post(
            f"/api/review/{reject_id}/reject",
            json={
                "reviewer": "customerops_test",
                "review_note": "Rejected for exclusion.",
            },
        )
        self.assertEqual(rejected.status_code, 200, rejected.text)

        revision = self.client.post(
            f"/api/review/{revision_id}/needs-revision",
            json={
                "reviewer": "customerops_test",
                "review_note": "Needs revision for exclusion.",
            },
        )
        self.assertEqual(revision.status_code, 200, revision.text)

        built = self.client.post("/api/rag/build")
        self.assertEqual(built.status_code, 200, built.text)

        missing_header = self.client.post(
            "/api/customer-ops-agent/retrieve",
            json={"query": unique_term, "top_k": 5},
        )
        self._assert_customerops_error(
            missing_header,
            401,
            "UNAUTHORIZED_CLIENT",
        )

        wrong_header = self.client.post(
            "/api/customer-ops-agent/retrieve",
            headers={"X-DataHub-Client": "OtherAgent"},
            json={"query": unique_term, "top_k": 5},
        )
        self._assert_customerops_error(
            wrong_header,
            401,
            "UNAUTHORIZED_CLIENT",
        )

        retrieved = self.client.post(
            "/api/customer-ops-agent/retrieve",
            headers=self._customerops_headers(),
            json={
                "query": unique_term,
                "top_k": 5,
                "filters": {"intent": "shipping", "tags": [unique_term]},
                "conversation_id": "conv_for_test",
                "agent_session_id": "session_for_test",
            },
        )
        self.assertEqual(retrieved.status_code, 200, retrieved.text)
        data = retrieved.json()["data"]
        self.assertTrue(data["retrieval_id"].startswith("retrieval_"))
        self.assertEqual(data["retrieval_mode"], "customerops_local_mock_retrieval")
        self.assertGreaterEqual(len(data["results"]), 1)

        result = data["results"][0]
        self.assertIn("score", result)
        self.assertIn("matched_terms", result)
        self.assertIn("chunk_id", result)
        self.assertIn("candidate_id", result)
        self.assertIn("source_batch_id", result)
        self.assertIn("source_conversation_id", result)
        self.assertIn("source_message_ids", result)
        self.assertIn("answer", result)
        self.assertEqual(result["review_status"], "approved")

        result_candidate_ids = {item["candidate_id"] for item in data["results"]}
        self.assertIn(approve_id, result_candidate_ids)
        self.assertNotIn(reject_id, result_candidate_ids)
        self.assertNotIn(revision_id, result_candidate_ids)
        self.assertNotIn(pending_id, result_candidate_ids)

        forbidden_fields = {"raw_payload", "messages", "reviewer", "review_note"}
        for item in data["results"]:
            self.assertTrue(forbidden_fields.isdisjoint(item.keys()))

        trace = self.client.get(
            f"/api/customer-ops-agent/retrievals/{data['retrieval_id']}",
            headers=self._customerops_headers(),
        )
        self.assertEqual(trace.status_code, 200, trace.text)
        trace_data = trace.json()["data"]
        self.assertEqual(trace_data["retrieval_id"], data["retrieval_id"])
        self.assertEqual(trace_data["result_count"], len(data["results"]))
        self.assertEqual(trace_data["conversation_id"], "conv_for_test")
        self.assertEqual(trace_data["agent_session_id"], "session_for_test")
        self.assertNotIn("results", trace_data)

        empty_query = self.client.post(
            "/api/customer-ops-agent/retrieve",
            headers=self._customerops_headers(),
            json={"query": "   ", "top_k": 5},
        )
        self._assert_customerops_error(empty_query, 400, "INVALID_QUERY")

        long_query = self.client.post(
            "/api/customer-ops-agent/retrieve",
            headers=self._customerops_headers(),
            json={"query": "x" * 501, "top_k": 5},
        )
        self._assert_customerops_error(long_query, 400, "QUERY_TOO_LONG")

        low_top_k = self.client.post(
            "/api/customer-ops-agent/retrieve",
            headers=self._customerops_headers(),
            json={"query": "shipping", "top_k": 0},
        )
        self._assert_customerops_error(low_top_k, 400, "INVALID_TOP_K")

        bad_top_k = self.client.post(
            "/api/customer-ops-agent/retrieve",
            headers=self._customerops_headers(),
            json={"query": "shipping", "top_k": 11},
        )
        self._assert_customerops_error(bad_top_k, 400, "INVALID_TOP_K")

        missing_trace_header = self.client.get(
            "/api/customer-ops-agent/retrievals/retrieval_missing"
        )
        self._assert_customerops_error(
            missing_trace_header,
            401,
            "UNAUTHORIZED_CLIENT",
        )

        missing_trace = self.client.get(
            "/api/customer-ops-agent/retrievals/retrieval_missing",
            headers=self._customerops_headers(),
        )
        self._assert_customerops_error(missing_trace, 404, "RETRIEVAL_NOT_FOUND")

        routes = {route.path for route in app.routes}
        self.assertTrue("/api/customer-ops-agent/retrieve" in routes)
        self.assertTrue(
            "/api/customer-ops-agent/retrievals/{retrieval_id}" in routes
        )
        self.assertFalse(any("/embeddings" in path for path in routes))
        self.assertFalse(any("/vector" in path for path in routes))


if __name__ == "__main__":
    unittest.main()
