import subprocess
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


class P1HighQualityDataHubReleaseTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        self.run_id = uuid4().hex[:8]

    def _headers(self) -> dict[str, str]:
        return {"X-DataHub-Client": "CustomerOpsAgent"}

    def _import_high_quality_sample(self) -> str:
        unique = self.run_id
        payload = {
            "source_name": f"p1_m15_high_quality_{unique}",
            "conversations": [
                {
                    "conversation_id": f"p1_m15_conv_{unique}",
                    "messages": [
                        {
                            "message_id": "msg_edit_q",
                            "role": "customer",
                            "content": f"Original p1m15edit{unique} shipping question?",
                            "timestamp": "2026-07-03T10:00:00",
                        },
                        {
                            "message_id": "msg_edit_a",
                            "role": "agent",
                            "content": f"Original p1m15edit{unique} answer.",
                            "timestamp": "2026-07-03T10:01:00",
                        },
                        {
                            "message_id": "msg_drop_q",
                            "role": "customer",
                            "content": f"Should p1m15drop{unique} enter knowledge?",
                            "timestamp": "2026-07-03T10:02:00",
                        },
                        {
                            "message_id": "msg_drop_a",
                            "role": "agent",
                            "content": f"p1m15drop{unique} should be skipped.",
                            "timestamp": "2026-07-03T10:03:00",
                        },
                        {
                            "message_id": "msg_review_q",
                            "role": "customer",
                            "content": f"Should p1m15review{unique} wait?",
                            "timestamp": "2026-07-03T10:04:00",
                        },
                        {
                            "message_id": "msg_review_a",
                            "role": "agent",
                            "content": f"p1m15review{unique} needs cleaning review.",
                            "timestamp": "2026-07-03T10:05:00",
                        },
                        {
                            "message_id": "msg_pending_q",
                            "role": "customer",
                            "content": f"How should p1m15pending{unique} be handled?",
                            "timestamp": "2026-07-03T10:06:00",
                        },
                        {
                            "message_id": "msg_pending_a",
                            "role": "agent",
                            "content": f"p1m15pending{unique} remains pending until review.",
                            "timestamp": "2026-07-03T10:07:00",
                        },
                        {
                            "message_id": "msg_revision_q",
                            "role": "customer",
                            "content": f"How should p1m15revision{unique} be handled?",
                            "timestamp": "2026-07-03T10:08:00",
                        },
                        {
                            "message_id": "msg_revision_a",
                            "role": "agent",
                            "content": f"p1m15revision{unique} should not enter RAG after needs revision.",
                            "timestamp": "2026-07-03T10:09:00",
                        },
                        {
                            "message_id": "msg_rejected_q",
                            "role": "customer",
                            "content": f"How should p1m15rejected{unique} be handled?",
                            "timestamp": "2026-07-03T10:10:00",
                        },
                        {
                            "message_id": "msg_rejected_a",
                            "role": "agent",
                            "content": f"p1m15rejected{unique} should not enter RAG after rejection.",
                            "timestamp": "2026-07-03T10:11:00",
                        },
                    ],
                }
            ],
        }
        response = self.client.post("/api/sources/import-json", json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["data"]["batch_id"]

    def _manual_clean(
        self,
        batch_id: str,
        message_id: str,
        content: str,
        action: str,
    ) -> None:
        response = self.client.patch(
            f"/api/sanitized/{batch_id}/messages/{message_id}/manual-clean",
            json={
                "content": content,
                "manual_action": action,
                "cleaner": "p1_m15_cleaner",
                "cleaning_note": f"P1 final release manual action: {action}.",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)

    def _patch_candidate(self, candidate: dict, term: str) -> dict:
        response = self.client.patch(
            f"/api/knowledge/candidates/{candidate['candidate_id']}",
            json={
                "question": f"What should DataHub answer for {term}?",
                "answer": f"{term} is a high-quality reviewed answer for CustomerOpsAgent retrieval.",
                "intent": "order_status",
                "tags": ["p1_m15", term],
                "risk_level": "medium",
                "quality_score": 0.88,
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["data"]

    def _review(self, candidate_id: str, action: str) -> dict:
        response = self.client.post(
            f"/api/review/{candidate_id}/{action}",
            json={
                "reviewer": "p1_m15_reviewer",
                "review_note": f"P1 final release review action: {action}.",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["data"]

    def _candidate_by_term(self, candidates: list[dict], term: str) -> dict:
        for candidate in candidates:
            combined = f"{candidate['question']} {candidate['answer']}"
            if term in combined:
                return candidate
        self.fail(f"Candidate containing {term} was not found.")

    def test_p1_high_quality_datahub_release_flow(self) -> None:
        health = self.client.get("/health")
        self.assertEqual(health.status_code, 200, health.text)
        self.assertEqual(health.json()["phase"], "P1-M22")

        batch_id = self._import_high_quality_sample()
        raw_path = ROOT_DIR / "backend" / "storage" / "raw_batches" / f"{batch_id}.json"
        raw_before = raw_path.read_text(encoding="utf-8")

        cleaned = self.client.post(f"/api/cleaning/run/{batch_id}")
        self.assertEqual(cleaned.status_code, 200, cleaned.text)

        sanitized = self.client.get(f"/api/sanitized/{batch_id}")
        self.assertEqual(sanitized.status_code, 200, sanitized.text)
        sanitized_data = sanitized.json()["data"]
        self.assertGreaterEqual(sanitized_data["sanitized_message_count"], 1)
        for field in [
            "cleaning_issues",
            "risk_flags",
            "quality_score",
            "quality_level",
            "suggested_action",
        ]:
            self.assertIn(field, sanitized_data["messages"][0])

        unique = self.run_id
        self._manual_clean(
            batch_id,
            "msg_edit_q",
            f"What is the p1m15edited{unique} final release policy?",
            "keep_edited",
        )
        self._manual_clean(
            batch_id,
            "msg_edit_a",
            f"p1m15edited{unique} should be reviewed before it enters unified RAG.",
            "keep_edited",
        )
        self._manual_clean(
            batch_id,
            "msg_drop_q",
            f"p1m15drop{unique} should be dropped.",
            "drop",
        )
        self._manual_clean(
            batch_id,
            "msg_review_q",
            f"p1m15review{unique} needs manual review.",
            "needs_review",
        )
        self._manual_clean(
            batch_id,
            "msg_pending_q",
            f"How should p1m15pending{unique} be handled?",
            "keep",
        )

        self.assertEqual(raw_path.read_text(encoding="utf-8"), raw_before)

        extracted = self.client.post(f"/api/extraction/run/{batch_id}")
        self.assertEqual(extracted.status_code, 200, extracted.text)
        self.assertGreaterEqual(extracted.json()["data"]["candidate_count"], 4)

        candidates_response = self.client.get("/api/knowledge/candidates")
        self.assertEqual(candidates_response.status_code, 200, candidates_response.text)
        batch_candidates = [
            candidate
            for candidate in candidates_response.json()["data"]["candidates"]
            if candidate["source_batch_id"] == batch_id
        ]
        combined_candidates = " ".join(
            f"{candidate['question']} {candidate['answer']}"
            for candidate in batch_candidates
        )
        self.assertIn(f"p1m15edited{unique}", combined_candidates)
        self.assertNotIn(f"p1m15drop{unique}", combined_candidates)
        self.assertNotIn(f"p1m15review{unique}", combined_candidates)

        approved_candidate = self._patch_candidate(
            self._candidate_by_term(batch_candidates, f"p1m15edited{unique}"),
            f"p1m15approved{unique}",
        )
        pending_candidate = self._patch_candidate(
            self._candidate_by_term(batch_candidates, f"p1m15pending{unique}"),
            f"p1m15pending{unique}",
        )
        revision_candidate = self._patch_candidate(
            self._candidate_by_term(batch_candidates, f"p1m15revision{unique}"),
            f"p1m15revision{unique}",
        )
        rejected_candidate = self._patch_candidate(
            self._candidate_by_term(batch_candidates, f"p1m15rejected{unique}"),
            f"p1m15rejected{unique}",
        )

        approved_reviewed = self._review(approved_candidate["candidate_id"], "approve")
        revision_reviewed = self._review(revision_candidate["candidate_id"], "needs-revision")
        rejected_reviewed = self._review(rejected_candidate["candidate_id"], "reject")

        self.assertEqual(approved_reviewed["review_status"], "approved")
        self.assertEqual(revision_reviewed["review_status"], "needs_revision")
        self.assertEqual(rejected_reviewed["review_status"], "rejected")
        self.assertEqual(pending_candidate["review_status"], "pending_review")

        first_build = self.client.post("/api/rag/build")
        self.assertEqual(first_build.status_code, 200, first_build.text)
        second_build = self.client.post("/api/rag/build")
        self.assertEqual(second_build.status_code, 200, second_build.text)
        self.assertEqual(second_build.json()["data"]["built_count"], 0)
        self.assertEqual(second_build.json()["data"]["updated_count"], 0)

        chunks = self.client.get("/api/rag/chunks")
        self.assertEqual(chunks.status_code, 200, chunks.text)
        chunks_by_candidate = {
            chunk["candidate_id"]: chunk
            for chunk in chunks.json()["data"]["chunks"]
        }
        approved_chunk = chunks_by_candidate[approved_candidate["candidate_id"]]
        self.assertEqual(approved_chunk["source_type"], "chat_logs")
        self.assertEqual(approved_chunk["source_conversation_id"], f"p1_m15_conv_{unique}")
        self.assertIn("msg_edit_q", approved_chunk["source_message_ids"])
        self.assertNotIn(pending_candidate["candidate_id"], chunks_by_candidate)
        self.assertNotIn(revision_candidate["candidate_id"], chunks_by_candidate)
        self.assertNotIn(rejected_candidate["candidate_id"], chunks_by_candidate)

        retrieval = self.client.post(
            "/api/customer-ops-agent/retrieve",
            headers=self._headers(),
            json={"query": f"p1m15approved{unique}", "top_k": 5},
        )
        self.assertEqual(retrieval.status_code, 200, retrieval.text)
        retrieval_data = retrieval.json()["data"]
        self.assertEqual(retrieval_data["retrieval_mode"], "customerops_local_mock_retrieval")
        matched = [
            result
            for result in retrieval_data["results"]
            if result["candidate_id"] == approved_candidate["candidate_id"]
        ]
        self.assertEqual(len(matched), 1, retrieval.text)
        for key in [
            "score",
            "matched_terms",
            "chunk_id",
            "candidate_id",
            "source_type",
            "source_conversation_id",
            "source_message_ids",
        ]:
            self.assertIn(key, matched[0])

        bad_case = self.client.post(
            "/api/customer-ops-agent/bad-cases",
            headers=self._headers(),
            json={
                "retrieval_id": retrieval_data["retrieval_id"],
                "user_query": f"p1m15approved{unique} follow-up was incomplete.",
                "agent_answer": "The prior answer missed one operational detail.",
                "issue_type": "missing_knowledge",
                "expected_answer": "Create a pending-review draft for the missing operational detail.",
                "severity": "medium",
            },
        )
        self.assertEqual(bad_case.status_code, 200, bad_case.text)
        bad_case_id = bad_case.json()["data"]["bad_case_id"]

        draft = self.client.post(
            f"/api/bad-cases/{bad_case_id}/create-draft",
            json={
                "question": f"How should DataHub handle p1m15badcase{unique}?",
                "answer": f"p1m15badcase{unique} must remain pending_review until a reviewer approves it.",
                "intent": "order_status",
                "tags": ["bad_case", "p1_m15"],
                "risk_level": "medium",
                "quality_score": 0.7,
                "knowledge_type": "faq",
                "reviewer": "p1_m15_reviewer",
                "review_note": "Created during final release verification.",
            },
        )
        self.assertEqual(draft.status_code, 200, draft.text)
        draft_data = draft.json()["data"]
        self.assertEqual(draft_data["review_status"], "pending_review")
        self.assertEqual(draft_data["source_type"], "bad_case")
        self.assertEqual(draft_data["source_bad_case_id"], bad_case_id)
        self.assertEqual(draft_data["source_retrieval_id"], retrieval_data["retrieval_id"])
        self.assertEqual(draft_data["extraction_method"], "bad_case_resolution")

        build_after_draft = self.client.post("/api/rag/build")
        self.assertEqual(build_after_draft.status_code, 200, build_after_draft.text)
        draft_chunk_ids = {
            chunk["candidate_id"]
            for chunk in self.client.get("/api/rag/chunks").json()["data"]["chunks"]
        }
        self.assertNotIn(draft_data["candidate_id"], draft_chunk_ids)

        legacy_term = f"p1m15legacy{unique}"
        legacy_import = self.client.post(
            "/api/legacy-rag/import",
            json={
                "source_name": f"p1_m15_legacy_{unique}",
                "source_type": "legacy_rag",
                "trusted_import": True,
                "items": [
                    {
                        "legacy_id": f"legacy_{unique}",
                        "question": f"What is the legacy policy for {legacy_term}?",
                        "answer": f"{legacy_term} trusted legacy answer can enter unified RAG.",
                        "intent": "order_status",
                        "tags": ["legacy_rag", "p1_m15", legacy_term],
                        "risk_level": "medium",
                        "quality_score": 0.86,
                        "knowledge_type": "faq",
                        "source_note": "Fake legacy item for final release verification.",
                    }
                ],
            },
        )
        self.assertEqual(legacy_import.status_code, 200, legacy_import.text)
        legacy_candidate_id = legacy_import.json()["data"]["candidate_ids"][0]
        legacy_build = self.client.post("/api/rag/build")
        self.assertEqual(legacy_build.status_code, 200, legacy_build.text)
        legacy_retrieval = self.client.post(
            "/api/customer-ops-agent/retrieve",
            headers=self._headers(),
            json={"query": legacy_term, "top_k": 10},
        )
        self.assertEqual(legacy_retrieval.status_code, 200, legacy_retrieval.text)
        legacy_matches = [
            result
            for result in legacy_retrieval.json()["data"]["results"]
            if result["candidate_id"] == legacy_candidate_id
        ]
        self.assertEqual(len(legacy_matches), 1, legacy_retrieval.text)
        self.assertEqual(legacy_matches[0]["source_type"], "legacy_rag")
        self.assertEqual(legacy_matches[0]["source_legacy_id"], f"legacy_{unique}")

        ignored_check = subprocess.run(
            ["git", "check-ignore", "backend/storage"],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(ignored_check.returncode, 0, ignored_check.stderr)

        routes = {route.path.lower() for route in app.routes}
        self.assertFalse(any("embedding" in route for route in routes))
        self.assertFalse(any("vector" in route for route in routes))
        self.assertFalse(any("qdrant" in route for route in routes))
        self.assertFalse(any("pgvector" in route for route in routes))
        self.assertFalse(any("mcp" in route for route in routes))


if __name__ == "__main__":
    unittest.main()
