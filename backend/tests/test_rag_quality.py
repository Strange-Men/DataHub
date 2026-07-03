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


class RagQualityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        self.sample = json.loads(
            (ROOT_DIR / "samples" / "customer_chat_sample.json").read_text(
                encoding="utf-8"
            )
        )

    def _create_candidates(self, suffix: str) -> list[dict[str, object]]:
        payload = dict(self.sample)
        payload["source_name"] = f"rag_quality_{suffix}"

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

    def test_rag_build_is_approved_only_and_idempotent(self) -> None:
        health = self.client.get("/health")
        self.assertEqual(health.status_code, 200, health.text)
        self.assertEqual(health.json()["phase"], "M7")

        candidates = [
            *self._create_candidates("a"),
            *self._create_candidates("b"),
        ]
        self.assertGreaterEqual(len(candidates), 4)

        approve_id = candidates[0]["candidate_id"]
        reject_id = candidates[1]["candidate_id"]
        revision_id = candidates[2]["candidate_id"]
        pending_id = candidates[3]["candidate_id"]

        approved = self.client.post(
            f"/api/review/{approve_id}/approve",
            json={
                "reviewer": "rag_quality_test",
                "review_note": "Approved for local RAG quality test.",
            },
        )
        self.assertEqual(approved.status_code, 200, approved.text)

        rejected = self.client.post(
            f"/api/review/{reject_id}/reject",
            json={
                "reviewer": "rag_quality_test",
                "review_note": "Rejected for exclusion test.",
            },
        )
        self.assertEqual(rejected.status_code, 200, rejected.text)

        revision = self.client.post(
            f"/api/review/{revision_id}/needs-revision",
            json={
                "reviewer": "rag_quality_test",
                "review_note": "Needs revision for exclusion test.",
            },
        )
        self.assertEqual(revision.status_code, 200, revision.text)

        first_build = self.client.post("/api/rag/build")
        self.assertEqual(first_build.status_code, 200, first_build.text)
        first_data = first_build.json()["data"]
        self.assertGreaterEqual(first_data["built_count"], 1)

        chunks = self.client.get("/api/rag/chunks")
        self.assertEqual(chunks.status_code, 200, chunks.text)
        chunk_list = chunks.json()["data"]["chunks"]
        chunk_ids = [chunk["chunk_id"] for chunk in chunk_list]
        self.assertEqual(len(chunk_ids), len(set(chunk_ids)))

        candidate_status = {
            candidate["candidate_id"]: candidate["review_status"]
            for candidate in self.client.get("/api/knowledge/candidates")
            .json()["data"]["candidates"]
        }
        chunk_candidate_ids = {chunk["candidate_id"] for chunk in chunk_list}
        self.assertTrue(
            all(
                candidate_status[chunk["candidate_id"]] == "approved"
                for chunk in chunk_list
            )
        )
        self.assertIn(approve_id, chunk_candidate_ids)
        self.assertNotIn(reject_id, chunk_candidate_ids)
        self.assertNotIn(revision_id, chunk_candidate_ids)
        self.assertNotIn(pending_id, chunk_candidate_ids)

        second_build = self.client.post("/api/rag/build")
        self.assertEqual(second_build.status_code, 200, second_build.text)
        second_chunks = self.client.get("/api/rag/chunks").json()["data"]["chunks"]
        second_chunk_ids = [chunk["chunk_id"] for chunk in second_chunks]
        self.assertEqual(len(second_chunk_ids), len(set(second_chunk_ids)))
        self.assertEqual(len(second_chunk_ids), len(chunk_ids))

        search = self.client.post(
            "/api/rag/search",
            json={"query": "shipping Germany", "top_k": 5},
        )
        self.assertEqual(search.status_code, 200, search.text)
        results = search.json()["data"]["results"]
        self.assertGreaterEqual(len(results), 1)
        self.assertIn("matched_terms", results[0])
        self.assertIn("source_batch_id", results[0])
        self.assertIn("source_conversation_id", results[0])
        self.assertIn("source_message_ids", results[0])

        empty_query = self.client.post(
            "/api/rag/search",
            json={"query": "   ", "top_k": 5},
        )
        self.assertEqual(empty_query.status_code, 400)
        self.assertEqual(empty_query.json()["detail"]["code"], "INVALID_QUERY")

        long_query = self.client.post(
            "/api/rag/search",
            json={"query": "x" * 501, "top_k": 5},
        )
        self.assertEqual(long_query.status_code, 400)
        self.assertEqual(long_query.json()["detail"]["code"], "QUERY_TOO_LONG")

        bad_top_k = self.client.post(
            "/api/rag/search",
            json={"query": "shipping", "top_k": 11},
        )
        self.assertEqual(bad_top_k.status_code, 400)
        self.assertEqual(bad_top_k.json()["detail"]["code"], "INVALID_TOP_K")

        routes = {route.path for route in app.routes}
        self.assertFalse(any("/bad-cases" in path for path in routes))


if __name__ == "__main__":
    unittest.main()
