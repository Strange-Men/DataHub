"""Tests for P1-M20 RAG / Agent / Bad Case DB Persistence.

Verifies:
- approved candidate builds rag_chunks table.
- pending_review candidate does NOT enter rag_chunks.
- rejected candidate does NOT enter rag_chunks.
- Duplicate RAG build is idempotent (no infinitely growing chunks).
- RAG chunks can be read from DB.
- Agent retrieval reads DB rag_chunks.
- Agent retrieval writes retrieval_logs table.
- Retrieval detail can be read from DB.
- Bad Case submission writes bad_cases table.
- Bad Case generates knowledge_candidates draft (pending_review).
- created_candidate_id links to the candidate.
- Bad Case candidate can be read via candidate list.
- DB-first, JSON fallback does not break old chains.
- No real PostgreSQL required.

All tests use a temporary SQLite database.
"""

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


class RagAgentBadCaseDbPersistenceTest(unittest.TestCase):
    """Test RAG, Agent retrieval, and Bad Case DB persistence using temporary SQLite."""

    @classmethod
    def setUpClass(cls) -> None:
        # Create a temporary SQLite database file
        cls._tmpfile = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        cls._tmpfile.close()
        cls._db_path = cls._tmpfile.name
        os.environ["DATABASE_URL"] = f"sqlite:///{cls._db_path}"

        # Force re-import so the app uses the temp DB
        import importlib
        import app.database as db_module
        import app.db_models as _models_module
        import app.db_repositories as _repo_module
        import app.storage as _storage_module
        import app.main as _main_module

        importlib.reload(db_module)
        db_module.init_database_tables()
        importlib.reload(_models_module)
        importlib.reload(_repo_module)
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

    def _import_clean_extract_approve(self, suffix: str = "") -> str:
        """Full pipeline: import → clean → extract → approve one candidate.

        Returns the approved candidate_id.
        """
        unique = suffix or self._unique
        payload = {
            "source_name": f"p1_m19_test_{unique}",
            "conversations": [
                {
                    "conversation_id": f"conv_{unique}_0",
                    "messages": [
                        {
                            "message_id": f"msg_{unique}_q",
                            "role": "customer",
                            "content": f"How fast is shipping to Germany for ORD-{unique}?",
                            "timestamp": "2026-07-05T10:00:00",
                        },
                        {
                            "message_id": f"msg_{unique}_a",
                            "role": "agent",
                            "content": f"Shipping to Germany takes 5-7 business days for ORD-{unique}.",
                            "timestamp": "2026-07-05T10:01:00",
                        },
                    ],
                }
            ],
        }
        # Import
        resp = self.client.post("/api/sources/import-json", json=payload)
        self.assertEqual(resp.status_code, 200)
        batch_id = resp.json()["data"]["batch_id"]

        # Clean
        resp = self.client.post(f"/api/cleaning/run/{batch_id}")
        self.assertEqual(resp.status_code, 200)

        # Extract
        resp = self.client.post(f"/api/extraction/run/{batch_id}")
        self.assertEqual(resp.status_code, 200)

        # Get candidates
        resp = self.client.get("/api/knowledge/candidates")
        self.assertEqual(resp.status_code, 200)
        candidates = resp.json()["data"]["candidates"]
        self.assertGreaterEqual(len(candidates), 1)
        candidate_id = candidates[0]["candidate_id"]

        # Approve one candidate
        resp = self.client.post(
            f"/api/review/{candidate_id}/approve",
            json={"reviewer": "test_reviewer", "review_note": "Approved for RAG test."},
        )
        self.assertEqual(resp.status_code, 200)

        return candidate_id

    def _get_db_session(self):
        """Create a fresh DB session for direct table queries."""
        return self.db.SessionLocal()

    # ── 1. Approved candidate builds rag_chunks ─────────────────────

    def test_01_approved_candidate_builds_rag_chunks(self):
        """Approved candidate enters rag_chunks table after Build RAG."""
        self._import_clean_extract_approve()

        resp = self.client.post("/api/rag/build")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertGreaterEqual(data["built_count"], 1)
        self.assertEqual(data["status"], "completed")

        # Check rag_chunks table has data
        db = self._get_db_session()
        try:
            import app.db_models as models
            count = db.query(models.RagChunk).count()
            self.assertGreaterEqual(count, 1)
        finally:
            db.close()

    # ── 2. pending_review candidate does NOT enter rag_chunks ───────

    def test_02_pending_review_not_in_rag_chunks(self):
        """Candidates with status pending_review are excluded from RAG."""
        unique = self._unique
        payload = {
            "source_name": f"p1_m19_pending_{unique}",
            "conversations": [
                {
                    "conversation_id": f"conv_pending_{unique}",
                    "messages": [
                        {
                            "message_id": f"msg_pending_q",
                            "role": "customer",
                            "content": "What is your return policy?",
                            "timestamp": "2026-07-05T10:00:00",
                        },
                        {
                            "message_id": f"msg_pending_a",
                            "role": "agent",
                            "content": "You can return items within 30 days of purchase.",
                            "timestamp": "2026-07-05T10:01:00",
                        },
                    ],
                }
            ],
        }
        resp = self.client.post("/api/sources/import-json", json=payload)
        batch_id = resp.json()["data"]["batch_id"]
        self.client.post(f"/api/cleaning/run/{batch_id}")
        self.client.post(f"/api/extraction/run/{batch_id}")

        # Do NOT approve — leave as pending_review
        resp = self.client.post("/api/rag/build")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        # All candidates are pending_review → 0 built
        self.assertEqual(data["built_count"], 0)
        self.assertIn("review_status_pending_review", data.get("skipped_reasons", {}))

        # Check rag_chunks table: should only contain chunks from approved candidates
        db = self._get_db_session()
        try:
            import app.db_models as models
            chunks = db.query(models.RagChunk).all()
            # Each chunk should have a valid candidate_id from approved candidates
            for chunk in chunks:
                candidate = db.query(models.KnowledgeCandidate).filter(
                    models.KnowledgeCandidate.id == chunk.candidate_id
                ).first()
                if candidate:
                    self.assertEqual(candidate.status, "approved")
        finally:
            db.close()

    # ── 3. rejected candidate does NOT enter rag_chunks ─────────────

    def test_03_rejected_not_in_rag_chunks(self):
        """Candidates with status rejected are excluded from RAG."""
        unique = f"{self._unique}_rej"
        payload = {
            "source_name": f"p1_m19_rejected_{unique}",
            "conversations": [
                {
                    "conversation_id": f"conv_rej_{unique}",
                    "messages": [
                        {
                            "message_id": "msg_rej_q",
                            "role": "customer",
                            "content": "How do I cancel my order?",
                            "timestamp": "2026-07-05T10:00:00",
                        },
                        {
                            "message_id": "msg_rej_a",
                            "role": "agent",
                            "content": "You can cancel your order from the Orders page.",
                            "timestamp": "2026-07-05T10:01:00",
                        },
                    ],
                }
            ],
        }
        resp = self.client.post("/api/sources/import-json", json=payload)
        batch_id = resp.json()["data"]["batch_id"]
        self.client.post(f"/api/cleaning/run/{batch_id}")
        self.client.post(f"/api/extraction/run/{batch_id}")
        resp = self.client.get("/api/knowledge/candidates")
        candidates = resp.json()["data"]["candidates"]
        candidate_id = candidates[0]["candidate_id"]

        # Reject this candidate
        self.client.post(
            f"/api/review/{candidate_id}/reject",
            json={"reviewer": "test_reviewer", "review_note": "Rejected."},
        )

        resp = self.client.post("/api/rag/build")
        data = resp.json()["data"]
        self.assertIn("review_status_rejected", data.get("skipped_reasons", {}))

    # ── 4. Duplicate RAG build is idempotent ───────────────────────

    def test_04_duplicate_rag_build_idempotent(self):
        """Repeated RAG builds do not infinitely append duplicate chunks."""
        self._import_clean_extract_approve()

        # First build
        resp = self.client.post("/api/rag/build")
        data1 = resp.json()["data"]
        count1 = data1["chunk_count"]

        # Second build — same approved candidates
        resp = self.client.post("/api/rag/build")
        data2 = resp.json()["data"]
        count2 = data2["chunk_count"]

        # Chunk count should be stable (not doubled)
        self.assertEqual(count1, count2)

        # DB should have exactly count2 rows
        db = self._get_db_session()
        try:
            import app.db_models as models
            db_count = db.query(models.RagChunk).count()
            self.assertEqual(db_count, count2)
            self.assertGreaterEqual(db_count, 1)
        finally:
            db.close()

    # ── 5. RAG chunks can be read from DB ──────────────────────────

    def test_05_rag_chunks_readable_from_db(self):
        """RAG chunk list API returns data from DB."""
        approved_id = self._import_clean_extract_approve()
        self.client.post("/api/rag/build")

        # List chunks
        resp = self.client.get("/api/rag/chunks")
        self.assertEqual(resp.status_code, 200)
        chunks = resp.json()["data"]["chunks"]
        self.assertGreaterEqual(len(chunks), 1)

        # Verify at least one chunk matches the approved candidate
        matching = [c for c in chunks if c["candidate_id"] == approved_id]
        self.assertEqual(len(matching), 1)

        # Get chunk detail
        chunk_id = matching[0]["chunk_id"]
        resp = self.client.get(f"/api/rag/chunks/{chunk_id}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["candidate_id"], approved_id)

    # ── 6. Agent retrieval reads DB rag_chunks ─────────────────────

    def test_06_agent_retrieval_reads_db_rag_chunks(self):
        """CustomerOpsAgent retrieval uses DB rag_chunks."""
        self._import_clean_extract_approve()
        self.client.post("/api/rag/build")

        resp = self.client.post(
            "/api/customer-ops-agent/retrieve",
            json={"query": "shipping Germany", "top_k": 3},
            headers={"X-DataHub-Client": "CustomerOpsAgent"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertIn("retrieval_id", data)
        self.assertGreaterEqual(len(data["results"]), 1)

    # ── 7. Agent retrieval writes retrieval_logs ───────────────────

    def test_07_retrieval_logs_written(self):
        """After retrieval, retrieval_logs table has data."""
        self._import_clean_extract_approve()
        self.client.post("/api/rag/build")

        resp = self.client.post(
            "/api/customer-ops-agent/retrieve",
            json={"query": "shipping Germany", "top_k": 3},
            headers={"X-DataHub-Client": "CustomerOpsAgent"},
        )
        retrieval_id = resp.json()["data"]["retrieval_id"]

        db = self._get_db_session()
        try:
            import app.db_models as models
            log = db.query(models.RetrievalLog).filter(
                models.RetrievalLog.id == retrieval_id
            ).first()
            self.assertIsNotNone(log)
            self.assertEqual(log.query, "shipping Germany")
        finally:
            db.close()

    # ── 8. Retrieval detail readable from DB ───────────────────────

    def test_08_retrieval_detail_readable_from_db(self):
        """GET retrieval detail returns data from DB."""
        self._import_clean_extract_approve()
        self.client.post("/api/rag/build")

        resp = self.client.post(
            "/api/customer-ops-agent/retrieve",
            json={"query": "shipping Germany", "top_k": 3},
            headers={"X-DataHub-Client": "CustomerOpsAgent"},
        )
        retrieval_id = resp.json()["data"]["retrieval_id"]

        resp = self.client.get(
            f"/api/customer-ops-agent/retrievals/{retrieval_id}",
            headers={"X-DataHub-Client": "CustomerOpsAgent"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["retrieval_id"], retrieval_id)

    # ── 9. Bad Case submission writes bad_cases ────────────────────

    def test_09_bad_case_writes_db(self):
        """Bad Case submission writes to bad_cases table."""
        self._import_clean_extract_approve()
        self.client.post("/api/rag/build")

        resp = self.client.post(
            "/api/customer-ops-agent/retrieve",
            json={"query": "shipping Germany", "top_k": 3},
            headers={"X-DataHub-Client": "CustomerOpsAgent"},
        )
        retrieval_id = resp.json()["data"]["retrieval_id"]

        resp = self.client.post(
            "/api/customer-ops-agent/bad-cases",
            json={
                "retrieval_id": retrieval_id,
                "user_query": "Where is my order?",
                "agent_answer": "Your package should arrive soon.",
                "issue_type": "wrong_answer",
                "severity": "high",
            },
            headers={"X-DataHub-Client": "CustomerOpsAgent"},
        )
        self.assertEqual(resp.status_code, 200)
        bc_data = resp.json()["data"]
        bad_case_id = bc_data["bad_case_id"]
        self.assertEqual(bc_data["status"], "open")

        db = self._get_db_session()
        try:
            import app.db_models as models
            bc = db.query(models.BadCase).filter(
                models.BadCase.id == bad_case_id
            ).first()
            self.assertIsNotNone(bc)
            self.assertEqual(bc.user_question, "Where is my order?")
            self.assertEqual(bc.status, "open")
        finally:
            db.close()

    # ── 10. Bad Case generates knowledge_candidates draft ───────────

    def test_10_bad_case_creates_knowledge_candidate_draft(self):
        """Bad Case → create-draft generates a knowledge_candidates record."""
        self._import_clean_extract_approve()
        self.client.post("/api/rag/build")

        resp = self.client.post(
            "/api/customer-ops-agent/retrieve",
            json={"query": "shipping Germany", "top_k": 3},
            headers={"X-DataHub-Client": "CustomerOpsAgent"},
        )
        retrieval_id = resp.json()["data"]["retrieval_id"]

        resp = self.client.post(
            "/api/customer-ops-agent/bad-cases",
            json={
                "retrieval_id": retrieval_id,
                "user_query": "How do I track my package?",
                "agent_answer": "It's on the way.",
                "issue_type": "missing_knowledge",
                "severity": "medium",
            },
            headers={"X-DataHub-Client": "CustomerOpsAgent"},
        )
        bad_case_id = resp.json()["data"]["bad_case_id"]

        resp = self.client.post(
            f"/api/bad-cases/{bad_case_id}/create-draft",
            json={
                "question": "How do I track my package?",
                "answer": "You can track your package using the tracking number in your confirmation email. If you don't have it, please provide your order number.",
                "intent": "order_status",
                "tags": ["tracking", "order"],
                "risk_level": "low",
                "quality_score": 0.85,
                "knowledge_type": "faq",
            },
        )
        self.assertEqual(resp.status_code, 200)
        candidate_data = resp.json()["data"]
        candidate_id = candidate_data["candidate_id"]
        self.assertTrue(candidate_id.startswith("kc_badcase_"))

        db = self._get_db_session()
        try:
            import app.db_models as models
            kc = db.query(models.KnowledgeCandidate).filter(
                models.KnowledgeCandidate.id == candidate_id
            ).first()
            self.assertIsNotNone(kc)
            self.assertEqual(kc.status, "pending_review")
            self.assertEqual(kc.source_type, "bad_case")
        finally:
            db.close()

    # ── 11. Bad Case candidate status is pending_review ─────────────

    def test_11_bad_case_candidate_pending_review(self):
        """Bad Case generated candidate has review_status=pending_review."""
        self._import_clean_extract_approve()
        self.client.post("/api/rag/build")

        resp = self.client.post(
            "/api/customer-ops-agent/retrieve",
            json={"query": "shipping Germany", "top_k": 3},
            headers={"X-DataHub-Client": "CustomerOpsAgent"},
        )
        retrieval_id = resp.json()["data"]["retrieval_id"]

        resp = self.client.post(
            "/api/customer-ops-agent/bad-cases",
            json={
                "retrieval_id": retrieval_id,
                "user_query": "Can I get a refund?",
                "agent_answer": "Please check our refund policy.",
                "issue_type": "wrong_answer",
                "severity": "medium",
            },
            headers={"X-DataHub-Client": "CustomerOpsAgent"},
        )
        bad_case_id = resp.json()["data"]["bad_case_id"]

        resp = self.client.post(
            f"/api/bad-cases/{bad_case_id}/create-draft",
            json={
                "question": "Can I get a refund?",
                "answer": "Yes, you can request a refund within 30 days. Please provide your order number.",
                "intent": "refund",
                "tags": ["refund", "policy"],
                "risk_level": "medium",
                "quality_score": 0.8,
                "knowledge_type": "faq",
            },
        )
        candidate_data = resp.json()["data"]
        self.assertEqual(candidate_data["review_status"], "pending_review")

        db = self._get_db_session()
        try:
            import app.db_models as models
            kc = db.query(models.KnowledgeCandidate).filter(
                models.KnowledgeCandidate.id == candidate_data["candidate_id"]
            ).first()
            self.assertIsNotNone(kc)
            self.assertEqual(kc.status, "pending_review")
        finally:
            db.close()

    # ── 12. created_candidate_id links to candidate ─────────────────

    def test_12_created_candidate_id_links(self):
        """Bad Case's linked_candidate_id points to the generated candidate."""
        self._import_clean_extract_approve()
        self.client.post("/api/rag/build")

        resp = self.client.post(
            "/api/customer-ops-agent/retrieve",
            json={"query": "shipping Germany", "top_k": 3},
            headers={"X-DataHub-Client": "CustomerOpsAgent"},
        )
        retrieval_id = resp.json()["data"]["retrieval_id"]

        resp = self.client.post(
            "/api/customer-ops-agent/bad-cases",
            json={
                "retrieval_id": retrieval_id,
                "user_query": "What are your business hours?",
                "agent_answer": "We are open 24/7.",
                "issue_type": "wrong_answer",
                "severity": "low",
            },
            headers={"X-DataHub-Client": "CustomerOpsAgent"},
        )
        bad_case_id = resp.json()["data"]["bad_case_id"]

        resp = self.client.post(
            f"/api/bad-cases/{bad_case_id}/create-draft",
            json={
                "question": "What are your business hours?",
                "answer": "Our customer service is available Monday-Friday 9am-6pm EST and Saturday 10am-4pm EST.",
                "intent": "general",
                "tags": ["hours", "support"],
                "risk_level": "low",
                "quality_score": 0.9,
                "knowledge_type": "faq",
            },
        )
        candidate_id = resp.json()["data"]["candidate_id"]

        # Check bad case has linked_candidate_id
        resp = self.client.get(f"/api/bad-cases/{bad_case_id}")
        self.assertEqual(resp.json()["data"]["linked_candidate_id"], candidate_id)

        db = self._get_db_session()
        try:
            import app.db_models as models
            bc = db.query(models.BadCase).filter(
                models.BadCase.id == bad_case_id
            ).first()
            self.assertIsNotNone(bc)
            self.assertEqual(bc.created_candidate_id, candidate_id)
        finally:
            db.close()

    # ── 13. Bad Case candidate readable via candidate list ─────────

    def test_13_bad_case_candidate_in_candidate_list(self):
        """Bad Case candidate appears in the knowledge candidate list."""
        self._import_clean_extract_approve()
        self.client.post("/api/rag/build")

        resp = self.client.post(
            "/api/customer-ops-agent/retrieve",
            json={"query": "shipping Germany", "top_k": 3},
            headers={"X-DataHub-Client": "CustomerOpsAgent"},
        )
        retrieval_id = resp.json()["data"]["retrieval_id"]

        resp = self.client.post(
            "/api/customer-ops-agent/bad-cases",
            json={
                "retrieval_id": retrieval_id,
                "user_query": "How do I change my shipping address?",
                "agent_answer": "You can change it in settings.",
                "issue_type": "retrieval_miss",
                "severity": "medium",
            },
            headers={"X-DataHub-Client": "CustomerOpsAgent"},
        )
        bad_case_id = resp.json()["data"]["bad_case_id"]

        resp = self.client.post(
            f"/api/bad-cases/{bad_case_id}/create-draft",
            json={
                "question": "How do I change my shipping address?",
                "answer": "You can update your shipping address from your account settings before the order ships.",
                "intent": "shipping",
                "tags": ["shipping", "address"],
                "risk_level": "medium",
                "quality_score": 0.8,
                "knowledge_type": "faq",
            },
        )
        candidate_id = resp.json()["data"]["candidate_id"]

        # Check candidate appears in list
        resp = self.client.get("/api/knowledge/candidates")
        candidates = resp.json()["data"]["candidates"]
        matching = [c for c in candidates if c["candidate_id"] == candidate_id]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]["source_type"], "bad_case")

    # ── 14. DB first, JSON fallback preserves old chains ───────────

    def test_14_db_first_json_fallback(self):
        """After DB is populated, API still returns correct data (DB-first)."""
        # Run full pipeline
        approved_id = self._import_clean_extract_approve()
        self.client.post("/api/rag/build")

        resp = self.client.post(
            "/api/customer-ops-agent/retrieve",
            json={"query": "shipping Germany", "top_k": 3},
            headers={"X-DataHub-Client": "CustomerOpsAgent"},
        )
        retrieval_id = resp.json()["data"]["retrieval_id"]

        # RAG chunk list reads from DB
        resp = self.client.get("/api/rag/chunks")
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(len(resp.json()["data"]["chunks"]), 1)

        # Retrieval trace reads from DB
        resp = self.client.get(
            f"/api/customer-ops-agent/retrievals/{retrieval_id}",
            headers={"X-DataHub-Client": "CustomerOpsAgent"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["retrieval_id"], retrieval_id)

    # ── 15. Health check reports P1-M20 ──────────────────────────────

    def test_15_health_reports_p1_m19(self):
        """Health check should report P1-M20."""
        resp = self.client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        health = resp.json()
        self.assertEqual(health["phase"], "P1-M21")
        self.assertIn("database_status", health)

    # ── 16. No real PostgreSQL required ────────────────────────────

    def test_16_no_real_postgresql_required(self):
        """Database backend should be SQLite in test environment."""
        resp = self.client.get("/api/health")
        db_status = resp.json()["database_status"]
        self.assertEqual(db_status["backend"], "sqlite")


if __name__ == "__main__":
    unittest.main()
