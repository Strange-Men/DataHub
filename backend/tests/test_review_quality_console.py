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


class ReviewQualityConsoleTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        self.run_id = uuid4().hex[:8]

    def _create_candidate(self, label: str) -> dict:
        payload = {
            "source_name": f"review_quality_{label}_{self.run_id}",
            "conversations": [
                {
                    "conversation_id": f"review_quality_conv_{label}_{self.run_id}",
                    "messages": [
                        {
                            "message_id": f"msg_{label}_q",
                            "role": "customer",
                            "content": f"How should DataHub answer reviewquality{label}{self.run_id}?",
                            "timestamp": "2026-07-03T10:00:00",
                        },
                        {
                            "message_id": f"msg_{label}_a",
                            "role": "agent",
                            "content": f"reviewquality{label}{self.run_id} answer should be reviewed first.",
                            "timestamp": "2026-07-03T10:01:00",
                        },
                    ],
                }
            ],
        }
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
        return batch_candidates[0]

    def _patch_candidate(self, candidate: dict, term: str) -> dict:
        candidate_id = candidate["candidate_id"]
        patched = self.client.patch(
            f"/api/knowledge/candidates/{candidate_id}",
            json={
                "question": f"How should the review console handle {term}?",
                "answer": f"{term} is a governed answer that requires review before RAG.",
                "intent": "order_status",
                "tags": ["review_quality", term],
                "risk_level": "medium",
                "quality_score": 0.86,
            },
        )
        self.assertEqual(patched.status_code, 200, patched.text)
        data = patched.json()["data"]
        self.assertEqual(data["question"], f"How should the review console handle {term}?")
        self.assertEqual(data["answer"], f"{term} is a governed answer that requires review before RAG.")
        self.assertEqual(data["intent"], "order_status")
        self.assertIn(term, data["tags"])
        self.assertEqual(data["risk_level"], "medium")
        self.assertEqual(data["quality_score"], 0.86)
        self.assertIn("source_batch_id", data)
        self.assertIn("cleaning_issues", data)
        self.assertIn("risk_flags", data)
        return data

    def _review(self, candidate_id: str, action: str, note: str) -> dict:
        reviewed = self.client.post(
            f"/api/review/{candidate_id}/{action}",
            json={
                "reviewer": "review_quality_console",
                "review_note": note,
            },
        )
        self.assertEqual(reviewed.status_code, 200, reviewed.text)
        return reviewed.json()["data"]

    def test_review_console_workflow_and_rag_boundaries(self) -> None:
        health = self.client.get("/health")
        self.assertEqual(health.status_code, 200, health.text)
        self.assertEqual(health.json()["phase"], "P1-M21")

        approved = self._patch_candidate(
            self._create_candidate("approved"),
            f"rqapproved{self.run_id}",
        )
        rejected = self._patch_candidate(
            self._create_candidate("rejected"),
            f"rqrejected{self.run_id}",
        )
        revision = self._patch_candidate(
            self._create_candidate("revision"),
            f"rqrevision{self.run_id}",
        )
        pending = self._patch_candidate(
            self._create_candidate("pending"),
            f"rqpending{self.run_id}",
        )

        pending_api = self.client.get("/api/review/pending")
        self.assertEqual(pending_api.status_code, 200, pending_api.text)
        pending_ids = {
            candidate["candidate_id"]
            for candidate in pending_api.json()["data"]["candidates"]
        }
        self.assertIn(pending["candidate_id"], pending_ids)

        approved_review = self._review(
            approved["candidate_id"],
            "approve",
            "Approved by review quality console test.",
        )
        rejected_review = self._review(
            rejected["candidate_id"],
            "reject",
            "Rejected by review quality console test.",
        )
        revision_review = self._review(
            revision["candidate_id"],
            "needs-revision",
            "Needs revision by review quality console test.",
        )

        self.assertEqual(approved_review["review_status"], "approved")
        self.assertEqual(rejected_review["review_status"], "rejected")
        self.assertEqual(revision_review["review_status"], "needs_revision")
        self.assertEqual(approved_review["reviewer"], "review_quality_console")
        self.assertEqual(approved_review["review_note"], "Approved by review quality console test.")
        self.assertIsNotNone(approved_review["reviewed_at"])

        review_index = json.loads(
            (ROOT_DIR / "backend" / "storage" / "review_records" / "index.json").read_text(
                encoding="utf-8"
            )
        )
        reviewed_ids = {record["candidate_id"] for record in review_index}
        self.assertIn(approved["candidate_id"], reviewed_ids)
        self.assertIn(rejected["candidate_id"], reviewed_ids)
        self.assertIn(revision["candidate_id"], reviewed_ids)

        built = self.client.post("/api/rag/build")
        self.assertEqual(built.status_code, 200, built.text)

        chunks = self.client.get("/api/rag/chunks")
        self.assertEqual(chunks.status_code, 200, chunks.text)
        chunk_candidate_ids = {
            chunk["candidate_id"]
            for chunk in chunks.json()["data"]["chunks"]
        }
        self.assertIn(approved["candidate_id"], chunk_candidate_ids)
        self.assertNotIn(rejected["candidate_id"], chunk_candidate_ids)
        self.assertNotIn(revision["candidate_id"], chunk_candidate_ids)
        self.assertNotIn(pending["candidate_id"], chunk_candidate_ids)


if __name__ == "__main__":
    unittest.main()
