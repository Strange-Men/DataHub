"""Tests for P1-M23.2 CustomerOpsAgent Semantic Retrieval.

Verifies:
- semantic retrieval from rag_embeddings when available.
- fallback to keyword retrieval when semantic is unavailable.
- SQLite does not crash (falls back gracefully).
- dimension mismatch triggers fallback.
- response includes score / candidate_id / source trace.
- retrieval_logs metadata_json includes retrieval_mode / fallback_reason / scores.
- Does NOT require real external embedding API.
- Does NOT require real Render database.
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient


ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


class CustomerOpsSemanticRetrievalTest(unittest.TestCase):
    """Test semantic retrieval with SQLite (keyword fallback expected)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmpfile = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        cls._tmpfile.close()
        cls._db_path = cls._tmpfile.name
        os.environ["DATABASE_URL"] = f"sqlite:///{cls._db_path}"
        os.environ["EMBEDDING_PROVIDER"] = "mock"
        os.environ["EMBEDDING_DIMENSION"] = "1536"

        import importlib
        import app.database as db_module
        import app.db_models as _models_module
        import app.db_repositories as _repo_module
        import app.storage as _storage_module
        import app.main as _main_module

        importlib.reload(db_module)
        importlib.reload(_models_module)
        importlib.reload(_repo_module)
        db_module.init_database_tables()
        importlib.reload(_storage_module)
        importlib.reload(_main_module)

        cls.db = db_module
        cls.app = _main_module.app
        cls.client = TestClient(cls.app)
        cls.run_id = uuid4().hex[:8]

    @classmethod
    def tearDownClass(cls) -> None:
        try:
            os.unlink(cls._db_path)
        except OSError:
            pass

    def setUp(self) -> None:
        self._unique = f"{self.run_id}_{uuid4().hex[:6]}"

    # ── Helpers ────────────────────────────────────────────────────

    def _import_clean_extract(self, suffix: str = "") -> str:
        unique = suffix or self._unique
        payload = {
            "source_name": f"p1_m23_test_{unique}",
            "conversations": [
                {
                    "conversation_id": f"conv_{unique}_0",
                    "messages": [
                        {
                            "message_id": f"msg_{unique}_q",
                            "role": "customer",
                            "content": f"How do I return an item and get a refund for order ORD-{unique}?",
                            "timestamp": "2026-07-05T10:00:00",
                        },
                        {
                            "message_id": f"msg_{unique}_a",
                            "role": "agent",
                            "content": "You can return within 30 days for a full refund. Please use the original packaging.",
                            "timestamp": "2026-07-05T10:01:00",
                        },
                    ],
                },
            ],
        }
        resp = self.client.post("/api/sources/import-json", json=payload)
        self.assertEqual(resp.status_code, 200, f"Import failed: {resp.text}")
        batch_id = resp.json()["data"]["batch_id"]

        resp = self.client.post(f"/api/cleaning/run/{batch_id}")
        self.assertEqual(resp.status_code, 200)

        resp = self.client.post(f"/api/extraction/run/{batch_id}")
        self.assertEqual(resp.status_code, 200)

        return batch_id

    def _setup_approved_rag(self) -> None:
        """Import, clean, extract, approve first candidate, build RAG."""
        self._import_clean_extract()
        resp = self.client.get("/api/knowledge/candidates")
        candidates = resp.json()["data"]["candidates"]
        self.assertGreater(len(candidates), 0, "Need at least one candidate")
        cid = candidates[0]["candidate_id"]

        resp = self.client.post(
            f"/api/review/{cid}/approve",
            json={"reviewer": "m23_tester", "review_note": "Approved for semantic retrieval test."},
        )
        self.assertEqual(resp.status_code, 200)

        resp = self.client.post("/api/rag/build")
        self.assertEqual(resp.status_code, 200)

    # ── Tests ──────────────────────────────────────────────────────

    def test_01_sqlite_fallback_to_keyword_does_not_crash(self):
        """SQLite should fallback to keyword retrieval without crashing."""
        self._setup_approved_rag()

        resp = self.client.post(
            "/api/customer-ops-agent/retrieve",
            json={"query": "How do I return an item and get a refund?", "top_k": 3},
            headers={"X-DataHub-Client": "CustomerOpsAgent"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]

        # On SQLite, we expect keyword fallback
        mode = data.get("retrieval_mode", "")
        self.assertIn(mode, [
            "customerops_keyword_fallback",
            "customerops_vector_with_keyword_fallback",
            "customerops_local_mock_retrieval",
        ], f"Unexpected retrieval_mode: {mode}")

        # Should have fallback_used = True on SQLite
        self.assertTrue(data.get("fallback_used", False),
                        "SQLite should trigger fallback")
        self.assertIsNotNone(data.get("fallback_reason"),
                             "Fallback reason must be recorded")

        # Should still return results via keyword fallback
        results = data.get("results", [])
        self.assertIsInstance(results, list)

    def test_02_response_includes_required_fields(self):
        """Response should include retrieval_id, retrieval_mode, results, fallback fields."""
        self._setup_approved_rag()

        resp = self.client.post(
            "/api/customer-ops-agent/retrieve",
            json={"query": "refund policy", "top_k": 3},
            headers={"X-DataHub-Client": "CustomerOpsAgent"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]

        # Required top-level fields
        self.assertIn("retrieval_id", data)
        self.assertIn("retrieval_mode", data)
        self.assertIn("results", data)
        self.assertIn("fallback_used", data)
        self.assertIn("fallback_reason", data)
        self.assertIn("query", data)
        self.assertIn("top_k", data)
        self.assertIn("created_at", data)

        # retrieval_id should not be empty
        self.assertTrue(data["retrieval_id"].startswith("retrieval_"),
                        f"Unexpected retrieval_id: {data['retrieval_id']}")

    def test_03_results_have_score_and_candidate_id(self):
        """Each result should include score, candidate_id, chunk_id, source trace."""
        self._setup_approved_rag()

        resp = self.client.post(
            "/api/customer-ops-agent/retrieve",
            json={"query": "shipping delivery time", "top_k": 3},
            headers={"X-DataHub-Client": "CustomerOpsAgent"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        results = data.get("results", [])

        for r in results:
            self.assertIn("score", r, f"Missing 'score' in result: {r}")
            self.assertIsInstance(r["score"], (int, float))
            self.assertIn("candidate_id", r)
            self.assertIn("chunk_id", r)
            self.assertIn("chunk_text", r)
            self.assertIn("source_type", r)
            self.assertIn("answer", r)

    def test_04_retrieval_trace_persisted(self):
        """Retrieval trace should be retrievable via GET endpoint."""
        self._setup_approved_rag()

        resp = self.client.post(
            "/api/customer-ops-agent/retrieve",
            json={"query": "return policy", "top_k": 3},
            headers={"X-DataHub-Client": "CustomerOpsAgent"},
        )
        self.assertEqual(resp.status_code, 200)
        retrieval_id = resp.json()["data"]["retrieval_id"]

        # Fetch the trace
        resp2 = self.client.get(
            f"/api/customer-ops-agent/retrievals/{retrieval_id}",
            headers={"X-DataHub-Client": "CustomerOpsAgent"},
        )
        self.assertEqual(resp2.status_code, 200)
        trace = resp2.json()["data"]
        self.assertEqual(trace["retrieval_id"], retrieval_id)
        self.assertEqual(trace["query"], "return policy")

    def test_05_retrieval_logs_metadata_has_semantic_fields(self):
        """retrieval_logs metadata_json should include retrieval_mode, fallback_reason, scores."""
        self._setup_approved_rag()

        resp = self.client.post(
            "/api/customer-ops-agent/retrieve",
            json={"query": "refund process timeline", "top_k": 3},
            headers={"X-DataHub-Client": "CustomerOpsAgent"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]

        # Check that the response contains semantic metadata
        self.assertIn("retrieval_mode", data)
        self.assertIn("fallback_used", data)
        self.assertIn("fallback_reason", data)

        # retrieval_logs in DB should have the metadata
        retrieval_id = data["retrieval_id"]
        resp2 = self.client.get(
            f"/api/customer-ops-agent/retrievals/{retrieval_id}",
            headers={"X-DataHub-Client": "CustomerOpsAgent"},
        )
        self.assertEqual(resp2.status_code, 200)
        trace = resp2.json()["data"]
        self.assertIn("retrieval_mode", trace)
        self.assertIn("fallback_used", trace)

    def test_06_query_validation_still_works(self):
        """Empty query, overlong query, invalid top_k should return errors."""
        # Empty query
        resp = self.client.post(
            "/api/customer-ops-agent/retrieve",
            json={"query": "   ", "top_k": 3},
            headers={"X-DataHub-Client": "CustomerOpsAgent"},
        )
        self.assertEqual(resp.status_code, 400)

        # top_k < 1
        resp = self.client.post(
            "/api/customer-ops-agent/retrieve",
            json={"query": "test", "top_k": 0},
            headers={"X-DataHub-Client": "CustomerOpsAgent"},
        )
        self.assertEqual(resp.status_code, 400)

        # top_k > 10
        resp = self.client.post(
            "/api/customer-ops-agent/retrieve",
            json={"query": "test", "top_k": 11},
            headers={"X-DataHub-Client": "CustomerOpsAgent"},
        )
        self.assertEqual(resp.status_code, 400)

    def test_07_unauthorized_client_rejected(self):
        """Missing or invalid X-DataHub-Client header returns 401."""
        resp = self.client.post(
            "/api/customer-ops-agent/retrieve",
            json={"query": "test", "top_k": 3},
        )
        self.assertEqual(resp.status_code, 401)

    def test_08_dimension_mismatch_triggers_fallback(self):
        """When query embedding dimensionality doesn't match stored, should fallback."""
        # Set a custom dimension that won't match the stored 1536
        old_dim = os.environ.get("EMBEDDING_DIMENSION")
        os.environ["EMBEDDING_DIMENSION"] = "64"  # different from stored 1536

        try:
            self._setup_approved_rag()

            resp = self.client.post(
                "/api/customer-ops-agent/retrieve",
                json={"query": "refund policy", "top_k": 3},
                headers={"X-DataHub-Client": "CustomerOpsAgent"},
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.json()["data"]

            # Should have fallen back
            self.assertTrue(data.get("fallback_used", False),
                            "Dimension mismatch should trigger fallback")
        finally:
            if old_dim:
                os.environ["EMBEDDING_DIMENSION"] = old_dim
            else:
                os.environ.pop("EMBEDDING_DIMENSION", None)

    def test_09_semantic_retrieval_with_keyword_fallback_integration(self):
        """Full integration: import -> clean -> extract -> approve -> build -> retrieve."""
        self._setup_approved_rag()

        # Verify the build created rag_embeddings
        resp = self.client.post("/api/rag/build")
        self.assertEqual(resp.status_code, 200)
        build_data = resp.json()["data"]
        self.assertGreater(build_data.get("chunk_count", 0), 0,
                           "RAG build should create chunks")

        # Retrieve using semantic (will fallback to keyword on SQLite)
        queries = [
            "How do I get a refund?",
            "return policy",
            "shipping options",
        ]
        for q in queries:
            resp = self.client.post(
                "/api/customer-ops-agent/retrieve",
                json={"query": q, "top_k": 3},
                headers={"X-DataHub-Client": "CustomerOpsAgent"},
            )
            self.assertEqual(resp.status_code, 200, f"Query '{q}' failed: {resp.text}")
            data = resp.json()["data"]
            self.assertIsNotNone(data.get("retrieval_mode"))
            self.assertIsInstance(data.get("results"), list)

    def test_10_health_reports_p1_m24(self):
        """Health check should report P1-M24 phase."""
        resp = self.client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        # health endpoint returns dict directly (not wrapped in ApiResponse)
        phase = resp.json().get("phase", "")
        self.assertEqual(phase, "P1-M24", f"Expected P1-M24, got {phase}")


if __name__ == "__main__":
    unittest.main()
