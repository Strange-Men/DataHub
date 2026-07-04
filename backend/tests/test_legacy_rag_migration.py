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


class LegacyRagMigrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        self.sample = json.loads(
            (ROOT_DIR / "samples" / "legacy_rag_export_sample.json").read_text(
                encoding="utf-8"
            )
        )
        self.unique_term = f"legacytest{uuid4().hex[:8]}"
        self.sample["source_name"] = f"customerops_legacy_rag_test_{self.unique_term}"
        self.sample["items"][0]["question"] = (
            f"How long does shipping take to Germany for {self.unique_term}?"
        )
        self.sample["items"][0]["answer"] = (
            f"{self.unique_term} shipping to Germany usually takes 7-12 business days."
        )
        self.sample["items"][0]["tags"] = [
            *self.sample["items"][0]["tags"],
            self.unique_term,
        ]

    def _headers(self) -> dict[str, str]:
        return {"X-DataHub-Client": "CustomerOpsAgent"}

    def test_legacy_rag_import_is_idempotent_and_retrievable(self) -> None:
        health = self.client.get("/health")
        self.assertEqual(health.status_code, 200, health.text)
        self.assertEqual(health.json()["phase"], "P1-M10")

        imported = self.client.post("/api/legacy-rag/import", json=self.sample)
        self.assertEqual(imported.status_code, 200, imported.text)
        import_data = imported.json()["data"]
        self.assertTrue(import_data["import_id"].startswith("legacy_import_"))
        self.assertEqual(import_data["source_type"], "legacy_rag")
        self.assertTrue(import_data["trusted_import"])
        self.assertEqual(import_data["migration_mode"], "trusted_import")
        self.assertEqual(import_data["item_count"], 3)
        self.assertEqual(import_data["created_candidate_count"], 3)
        self.assertEqual(import_data["approved_count"], 3)
        self.assertEqual(import_data["pending_review_count"], 0)
        self.assertEqual(import_data["skipped_count"], 0)

        listed = self.client.get("/api/legacy-rag/imports")
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertIn(
            import_data["import_id"],
            {item["import_id"] for item in listed.json()["data"]["imports"]},
        )

        detail = self.client.get(f"/api/legacy-rag/imports/{import_data['import_id']}")
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertEqual(detail.json()["data"]["candidate_ids"], import_data["candidate_ids"])

        duplicate = self.client.post("/api/legacy-rag/import", json=self.sample)
        self.assertEqual(duplicate.status_code, 200, duplicate.text)
        duplicate_data = duplicate.json()["data"]
        self.assertEqual(duplicate_data["created_candidate_count"], 0)
        self.assertEqual(duplicate_data["updated_count"], 0)
        self.assertEqual(duplicate_data["skipped_count"], 3)
        self.assertEqual(duplicate_data["skipped_reasons"], {"unchanged": 3})

        candidates = self.client.get("/api/knowledge/candidates")
        self.assertEqual(candidates.status_code, 200, candidates.text)
        candidate_map = {
            candidate["candidate_id"]: candidate
            for candidate in candidates.json()["data"]["candidates"]
        }
        for candidate_id in import_data["candidate_ids"]:
            candidate = candidate_map[candidate_id]
            self.assertEqual(candidate["source_type"], "legacy_rag")
            self.assertTrue(candidate["source_legacy_id"].startswith("legacy_"))
            self.assertEqual(candidate["source_import_id"], import_data["import_id"])
            self.assertEqual(candidate["review_status"], "approved")
            self.assertEqual(candidate["extraction_method"], "legacy_rag_migration")
            self.assertEqual(candidate["migration_mode"], "trusted_import")
            self.assertIn("legacy_rag", candidate["tags"])

        review_required_payload = {
            **self.sample,
            "source_name": f"customerops_legacy_rag_review_required_{uuid4().hex[:8]}",
            "trusted_import": False,
            "items": [
                {
                    **self.sample["items"][0],
                    "legacy_id": "legacy_review_required_001",
                    "question": "What should happen when order tracking is missing?",
                    "answer": "Ask for the order number and escalate if tracking cannot be found.",
                    "tags": ["order", "tracking"],
                }
            ],
        }
        review_required = self.client.post(
            "/api/legacy-rag/import",
            json=review_required_payload,
        )
        self.assertEqual(review_required.status_code, 200, review_required.text)
        review_data = review_required.json()["data"]
        self.assertFalse(review_data["trusted_import"])
        self.assertEqual(review_data["migration_mode"], "review_required")
        self.assertEqual(review_data["pending_review_count"], 1)
        pending_id = review_data["candidate_ids"][0]

        built = self.client.post("/api/rag/build")
        self.assertEqual(built.status_code, 200, built.text)

        chunks = self.client.get("/api/rag/chunks")
        self.assertEqual(chunks.status_code, 200, chunks.text)
        chunks_by_candidate = {
            chunk["candidate_id"]: chunk
            for chunk in chunks.json()["data"]["chunks"]
        }
        for candidate_id in import_data["candidate_ids"]:
            self.assertIn(candidate_id, chunks_by_candidate)
            chunk = chunks_by_candidate[candidate_id]
            self.assertEqual(chunk["source_type"], "legacy_rag")
            self.assertTrue(chunk["source_legacy_id"].startswith("legacy_"))
            self.assertEqual(chunk["source_import_id"], import_data["import_id"])
        self.assertNotIn(pending_id, chunks_by_candidate)

        retrieved = self.client.post(
            "/api/customer-ops-agent/retrieve",
            headers=self._headers(),
            json={"query": self.unique_term, "top_k": 5},
        )
        self.assertEqual(retrieved.status_code, 200, retrieved.text)
        results = retrieved.json()["data"]["results"]
        legacy_results = [
            result for result in results if result.get("source_type") == "legacy_rag"
        ]
        self.assertGreaterEqual(len(legacy_results), 1)
        first = legacy_results[0]
        self.assertIn("score", first)
        self.assertIn("matched_terms", first)
        self.assertTrue(first["chunk_id"].startswith("chunk_kc_legacy_"))
        self.assertTrue(first["candidate_id"].startswith("kc_legacy_"))
        self.assertTrue(first["source_legacy_id"].startswith("legacy_"))
        self.assertEqual(first["migration_mode"], "trusted_import")
        self.assertEqual(first["review_status"], "approved")

        routes = {route.path for route in app.routes}
        self.assertIn("/api/legacy-rag/import", routes)
        self.assertIn("/api/legacy-rag/imports", routes)
        self.assertFalse(any("/embeddings" in path for path in routes))
        self.assertFalse(any("/vector" in path for path in routes))


if __name__ == "__main__":
    unittest.main()
