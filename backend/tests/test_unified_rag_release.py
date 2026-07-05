import json
import sys
import unittest
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient


ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.main import app  # noqa: E402


class UnifiedRagReleaseTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        self.chat_sample = json.loads(
            (ROOT_DIR / "samples" / "customer_chat_sample.json").read_text(
                encoding="utf-8"
            )
        )
        self.public_sample = json.loads(
            (ROOT_DIR / "samples" / "public_dataset_eval_sample.json").read_text(
                encoding="utf-8"
            )
        )
        self.legacy_sample = json.loads(
            (ROOT_DIR / "samples" / "legacy_rag_export_sample.json").read_text(
                encoding="utf-8"
            )
        )
        self.run_id = uuid4().hex[:8]

    def _headers(self) -> dict[str, str]:
        return {"X-DataHub-Client": "CustomerOpsAgent"}

    def _create_candidates_from_import(
        self,
        sample: dict[str, object],
        source_name: str,
    ) -> list[dict[str, object]]:
        payload = dict(sample)
        payload["source_name"] = source_name
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
        return batch_candidates

    def _edit_candidate(
        self,
        candidate_id: str,
        unique_term: str,
        *,
        source_label: str,
    ) -> None:
        response = self.client.patch(
            f"/api/knowledge/candidates/{candidate_id}",
            json={
                "question": f"What is the unified answer for {unique_term}?",
                "answer": f"{unique_term} answer from {source_label}.",
                "intent": "order_status",
                "tags": ["unified", source_label, unique_term],
                "risk_level": "medium",
                "quality_score": 0.86,
            },
        )
        self.assertEqual(response.status_code, 200, response.text)

    def _approve_candidate(self, candidate_id: str, note: str) -> None:
        response = self.client.post(
            f"/api/review/{candidate_id}/approve",
            json={"reviewer": "p1_m11_unified_test", "review_note": note},
        )
        self.assertEqual(response.status_code, 200, response.text)

    def _retrieve_one(self, query: str, expected_candidate_id: str) -> dict[str, object]:
        response = self.client.post(
            "/api/customer-ops-agent/retrieve",
            headers=self._headers(),
            json={"query": query, "top_k": 10},
        )
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()["data"]
        self.assertTrue(data["retrieval_id"].startswith("retrieval_"))
        matches = [
            result
            for result in data["results"]
            if result["candidate_id"] == expected_candidate_id
        ]
        self.assertEqual(len(matches), 1, response.text)
        result = matches[0]
        for key in [
            "score",
            "matched_terms",
            "chunk_id",
            "candidate_id",
            "source_type",
            "source_message_ids",
            "review_status",
        ]:
            self.assertIn(key, result)
        self.assertEqual(result["review_status"], "approved")
        return {"retrieval_id": data["retrieval_id"], "result": result}

    def test_unified_rag_release_sources_and_boundaries(self) -> None:
        health = self.client.get("/health")
        self.assertEqual(health.status_code, 200, health.text)
        self.assertEqual(health.json()["phase"], "P1-M21")

        chat_candidates = self._create_candidates_from_import(
            self.chat_sample,
            f"chat_logs_unified_{self.run_id}",
        )
        chat_id = chat_candidates[0]["candidate_id"]
        chat_term = f"unifiedchat{self.run_id}"
        self._edit_candidate(chat_id, chat_term, source_label="chat_logs")
        self._approve_candidate(chat_id, "Approved chat log source for unified RAG.")

        public_candidates = self._create_candidates_from_import(
            self.public_sample,
            f"public_dataset_eval_unified_{self.run_id}",
        )
        public_id = public_candidates[0]["candidate_id"]
        public_pending_id = public_candidates[1]["candidate_id"]
        public_rejected_id = public_candidates[2]["candidate_id"]
        public_revision_id = public_candidates[3]["candidate_id"]
        public_term = f"unifiedpublic{self.run_id}"
        self._edit_candidate(public_id, public_term, source_label="public_dataset")
        self._approve_candidate(public_id, "Approved public dataset source for unified RAG.")
        self.client.post(
            f"/api/review/{public_rejected_id}/reject",
            json={"reviewer": "p1_m11_unified_test", "review_note": "Reject boundary."},
        )
        self.client.post(
            f"/api/review/{public_revision_id}/needs-revision",
            json={
                "reviewer": "p1_m11_unified_test",
                "review_note": "Needs revision boundary.",
            },
        )

        legacy_payload = dict(self.legacy_sample)
        legacy_term = f"unifiedlegacy{self.run_id}"
        legacy_payload["source_name"] = f"customerops_legacy_unified_{self.run_id}"
        legacy_payload["items"] = [
            {
                **legacy_payload["items"][0],
                "legacy_id": f"legacy_unified_{self.run_id}",
                "question": f"What is the legacy unified policy for {legacy_term}?",
                "answer": f"{legacy_term} trusted legacy answer.",
                "tags": ["legacy_rag", "unified", legacy_term],
            }
        ]
        legacy_import = self.client.post("/api/legacy-rag/import", json=legacy_payload)
        self.assertEqual(legacy_import.status_code, 200, legacy_import.text)
        legacy_id = legacy_import.json()["data"]["candidate_ids"][0]

        built = self.client.post("/api/rag/build")
        self.assertEqual(built.status_code, 200, built.text)
        repeated_build = self.client.post("/api/rag/build")
        self.assertEqual(repeated_build.status_code, 200, repeated_build.text)
        repeated_data = repeated_build.json()["data"]
        self.assertEqual(repeated_data["built_count"], 0)
        self.assertEqual(repeated_data["updated_count"], 0)

        chunks = self.client.get("/api/rag/chunks").json()["data"]["chunks"]
        chunks_by_candidate = {chunk["candidate_id"]: chunk for chunk in chunks}
        self.assertEqual(chunks_by_candidate[chat_id]["source_type"], "chat_logs")
        self.assertEqual(chunks_by_candidate[public_id]["source_type"], "public_dataset")
        self.assertEqual(chunks_by_candidate[legacy_id]["source_type"], "legacy_rag")
        self.assertNotIn(public_pending_id, chunks_by_candidate)
        self.assertNotIn(public_rejected_id, chunks_by_candidate)
        self.assertNotIn(public_revision_id, chunks_by_candidate)

        chat_retrieval = self._retrieve_one(chat_term, chat_id)
        chat_result = chat_retrieval["result"]
        self.assertEqual(chat_result["source_type"], "chat_logs")

        public_result = self._retrieve_one(public_term, public_id)["result"]
        self.assertEqual(public_result["source_type"], "public_dataset")

        legacy_result = self._retrieve_one(legacy_term, legacy_id)["result"]
        self.assertEqual(legacy_result["source_type"], "legacy_rag")
        self.assertEqual(legacy_result["source_legacy_id"], f"legacy_unified_{self.run_id}")

        bad_case = self.client.post(
            "/api/customer-ops-agent/bad-cases",
            headers=self._headers(),
            json={
                "retrieval_id": chat_retrieval["retrieval_id"],
                "user_query": "The unified RAG answer missed an edge case.",
                "agent_answer": "The previous answer was incomplete.",
                "issue_type": "missing_knowledge",
                "expected_answer": "Create a pending review draft for the missing edge case.",
                "severity": "medium",
            },
        )
        self.assertEqual(bad_case.status_code, 200, bad_case.text)
        bad_case_id = bad_case.json()["data"]["bad_case_id"]
        bad_case_term = f"unifiedbadcase{self.run_id}"
        draft = self.client.post(
            f"/api/bad-cases/{bad_case_id}/create-draft",
            json={
                "question": f"How should DataHub answer {bad_case_term}?",
                "answer": f"{bad_case_term} answer from bad case correction.",
                "intent": "order_status",
                "tags": ["bad_case", "unified", bad_case_term],
                "risk_level": "medium",
                "quality_score": 0.7,
                "knowledge_type": "faq",
                "reviewer": "p1_m11_unified_test",
                "review_note": "Created for unified RAG release boundary.",
            },
        )
        self.assertEqual(draft.status_code, 200, draft.text)
        draft_data = draft.json()["data"]
        draft_id = draft_data["candidate_id"]
        self.assertEqual(draft_data["source_type"], "bad_case")
        self.assertEqual(draft_data["review_status"], "pending_review")

        build_after_draft = self.client.post("/api/rag/build")
        self.assertEqual(build_after_draft.status_code, 200, build_after_draft.text)
        chunks_after_draft = {
            chunk["candidate_id"]
            for chunk in self.client.get("/api/rag/chunks").json()["data"]["chunks"]
        }
        self.assertNotIn(draft_id, chunks_after_draft)

        self._approve_candidate(draft_id, "Approved Bad Case draft for unified RAG.")
        build_after_approval = self.client.post("/api/rag/build")
        self.assertEqual(build_after_approval.status_code, 200, build_after_approval.text)
        bad_case_result = self._retrieve_one(bad_case_term, draft_id)["result"]
        self.assertEqual(bad_case_result["source_type"], "bad_case")
        self.assertEqual(bad_case_result["source_bad_case_id"], bad_case_id)

        routes = {route.path for route in app.routes}
        self.assertFalse(any("/embeddings" in path for path in routes))
        self.assertFalse(any("/vector" in path for path in routes))
        self.assertFalse(any("/mcp" in path.lower() for path in routes))


if __name__ == "__main__":
    unittest.main()
