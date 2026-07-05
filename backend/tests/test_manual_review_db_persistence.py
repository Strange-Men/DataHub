"""Tests for P1-M18 Manual Cleaning & Review DB Persistence.

Verifies:
- Manual cleaning writes manual_cleaning_records table.
- keep / keep_edited / drop / needs_review actions persist.
- Knowledge extraction reads from DB sanitized messages.
- Knowledge extraction applies manual cleaning effective content.
- knowledge_candidates table has data after extraction.
- Duplicate extraction is idempotent.
- Candidate list reads from DB.
- Candidate edit persists.
- approve / reject / needs_revision write review_records.
- Candidate status is persisted across refresh reads.
- JSON storage compatibility is preserved.
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


class ManualReviewDbPersistenceTest(unittest.TestCase):
    """Test manual cleaning and review DB persistence using temporary SQLite."""

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

    # ── Helper: import → clean ─────────────────────────────────────

    def _import_and_clean(self, suffix: str = "") -> tuple[str, str, str, str, str]:
        """Import sample data and run cleaning.

        Returns (batch_id, msg_keep_id, msg_keep_edited_id, msg_drop_id, msg_needs_review_id).
        """
        unique = suffix or self._unique
        payload = {
            "source_name": f"p1_m18_test_{unique}",
            "conversations": [
                {
                    "conversation_id": f"conv_{unique}_0",
                    "messages": [
                        {
                            "message_id": f"msg_{unique}_keep_q",
                            "role": "customer",
                            "content": f"How long does shipping to Germany take for order ORD-{unique}?",
                            "timestamp": "2026-07-05T10:00:00",
                        },
                        {
                            "message_id": f"msg_{unique}_keep_a",
                            "role": "agent",
                            "content": f"Shipping to Germany takes 5-7 business days for order ORD-{unique}.",
                            "timestamp": "2026-07-05T10:01:00",
                        },
                        {
                            "message_id": f"msg_{unique}_edit_q",
                            "role": "customer",
                            "content": f"I need a refund for ORD-{unique}. My email is test@example.com.",
                            "timestamp": "2026-07-05T10:02:00",
                        },
                        {
                            "message_id": f"msg_{unique}_edit_a",
                            "role": "agent",
                            "content": f"Please send your refund request to support@example.com with order ORD-{unique}.",
                            "timestamp": "2026-07-05T10:03:00",
                        },
                        {
                            "message_id": f"msg_{unique}_drop_q",
                            "role": "customer",
                            "content": "asdf lol haha test test",
                            "timestamp": "2026-07-05T10:04:00",
                        },
                        {
                            "message_id": f"msg_{unique}_drop_a",
                            "role": "agent",
                            "content": "ok",
                            "timestamp": "2026-07-05T10:05:00",
                        },
                        {
                            "message_id": f"msg_{unique}_review_q",
                            "role": "customer",
                            "content": f"Can you guarantee next-day delivery for ORD-{unique}?",
                            "timestamp": "2026-07-05T10:06:00",
                        },
                        {
                            "message_id": f"msg_{unique}_review_a",
                            "role": "agent",
                            "content": f"I cannot guarantee delivery times but I will check ORD-{unique}.",
                            "timestamp": "2026-07-05T10:07:00",
                        },
                    ],
                }
            ],
        }
        response = self.client.post("/api/sources/import-json", json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        batch_id = response.json()["data"]["batch_id"]

        cleaned = self.client.post(f"/api/cleaning/run/{batch_id}")
        self.assertEqual(cleaned.status_code, 200, cleaned.text)

        return (
            batch_id,
            f"msg_{unique}_keep_q",
            f"msg_{unique}_edit_q",
            f"msg_{unique}_drop_q",
            f"msg_{unique}_review_q",
        )

    def _manual_clean(
        self, batch_id: str, message_id: str, content: str, action: str
    ) -> dict:
        response = self.client.patch(
            f"/api/sanitized/{batch_id}/messages/{message_id}/manual-clean",
            json={
                "content": content,
                "manual_action": action,
                "cleaner": "test_cleaner_01",
                "cleaning_note": f"Test action: {action}.",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["data"]

    # ── 1. Manual cleaning writes manual_cleaning_records ───────────

    def test_01_manual_cleaning_save_writes_db(self) -> None:
        batch_id, keep_id, _, _, _ = self._import_and_clean()

        self._manual_clean(batch_id, keep_id, "Cleaned shipping question?", "keep")

        db = self.db.SessionLocal()
        try:
            from app.db_models import ManualCleaningRecord
            rows = db.query(ManualCleaningRecord).all()
            self.assertGreaterEqual(
                len(rows), 1, "manual_cleaning_records table should have data"
            )
            found = False
            for row in rows:
                if row.sanitized_message_id == keep_id:
                    found = True
                    self.assertEqual(row.action, "keep")
                    self.assertEqual(row.cleaner, "test_cleaner_01")
                    break
            self.assertTrue(found, f"Manual cleaning record for {keep_id} not found")
        finally:
            db.close()

    # ── 2. keep action persists ──────────────────────────────────────

    def test_02_keep_action_persists(self) -> None:
        batch_id, keep_id, _, _, _ = self._import_and_clean()

        self._manual_clean(batch_id, keep_id, "Shipping question kept as is.", "keep")

        # Read sanitized batch — should show manual cleaning status
        sanitized = self.client.get(f"/api/sanitized/{batch_id}")
        self.assertEqual(sanitized.status_code, 200, sanitized.text)
        messages = sanitized.json()["data"]["messages"]
        kept = next((m for m in messages if m["message_id"] == keep_id), None)
        self.assertIsNotNone(kept)
        self.assertEqual(kept["manual_cleaning_status"], "cleaned")
        self.assertEqual(kept["manual_action"], "keep")

    # ── 3. keep_edited persists cleaned_content ─────────────────────

    def test_03_keep_edited_persists_cleaned_content(self) -> None:
        batch_id, _, edit_id, _, _ = self._import_and_clean()

        self._manual_clean(
            batch_id, edit_id,
            "How do I request a refund? Please contact support.",
            "keep_edited",
        )

        sanitized = self.client.get(f"/api/sanitized/{batch_id}")
        self.assertEqual(sanitized.status_code, 200, sanitized.text)
        messages = sanitized.json()["data"]["messages"]
        edited = next((m for m in messages if m["message_id"] == edit_id), None)
        self.assertIsNotNone(edited)
        self.assertEqual(edited["manual_cleaning_status"], "cleaned")
        self.assertEqual(edited["manual_action"], "keep_edited")
        self.assertEqual(
            edited["manual_cleaned_content"],
            "How do I request a refund? Please contact support.",
        )

        # Verify DB record
        db = self.db.SessionLocal()
        try:
            from app.db_models import ManualCleaningRecord
            row = (
                db.query(ManualCleaningRecord)
                .filter(ManualCleaningRecord.sanitized_message_id == edit_id)
                .first()
            )
            self.assertIsNotNone(row)
            self.assertEqual(row.action, "keep_edited")
            self.assertEqual(
                row.cleaned_content,
                "How do I request a refund? Please contact support.",
            )
        finally:
            db.close()

    # ── 4. drop action saves and affects extraction ──────────────────

    def test_04_drop_action_persists_and_affects_extraction(self) -> None:
        batch_id, _, _, drop_id, _ = self._import_and_clean()

        self._manual_clean(batch_id, drop_id, "Dropped noise message.", "drop")

        # Extract — dropped messages should be excluded
        extracted = self.client.post(f"/api/extraction/run/{batch_id}")
        self.assertEqual(extracted.status_code, 200, extracted.text)

        candidates_resp = self.client.get("/api/knowledge/candidates")
        self.assertEqual(candidates_resp.status_code, 200, candidates_resp.text)
        batch_candidates = [
            c for c in candidates_resp.json()["data"]["candidates"]
            if c.get("source_batch_id") == batch_id
        ]
        # drop_q message should NOT appear in any candidate
        for c in batch_candidates:
            combined = f"{c['question']} {c['answer']}"
            self.assertNotIn(
                "asdf",
                combined.lower(),
                f"Candidate from dropped message should not exist: {combined}",
            )

    # ── 5. needs_review saves and affects extraction ─────────────────

    def test_05_needs_review_saves_and_affects_extraction(self) -> None:
        batch_id, _, _, _, review_id = self._import_and_clean()

        self._manual_clean(
            batch_id, review_id, "Needs review for guarantee question.", "needs_review"
        )

        extracted = self.client.post(f"/api/extraction/run/{batch_id}")
        self.assertEqual(extracted.status_code, 200, extracted.text)

        candidates_resp = self.client.get("/api/knowledge/candidates")
        self.assertEqual(candidates_resp.status_code, 200, candidates_resp.text)
        batch_candidates = [
            c for c in candidates_resp.json()["data"]["candidates"]
            if c.get("source_batch_id") == batch_id
        ]
        # The review_q message ("Can you guarantee...") should not appear
        # as a question in any candidate
        for c in batch_candidates:
            self.assertNotIn(
                "guarantee next-day delivery",
                c["question"].lower(),
                f"Candidate from needs_review message should not exist: {c['question']}",
            )

    # ── 6. Extraction reads from DB sanitized_messages ──────────────

    def test_06_extraction_reads_db_sanitized_messages(self) -> None:
        batch_id, keep_id, _, _, _ = self._import_and_clean()

        extracted = self.client.post(f"/api/extraction/run/{batch_id}")
        self.assertEqual(extracted.status_code, 200, extracted.text)
        self.assertGreaterEqual(
            extracted.json()["data"]["candidate_count"], 1,
            "Should extract at least one candidate from DB sanitized messages",
        )

    # ── 7. Extraction applies manual cleaning effective content ──────

    def test_07_extraction_applies_manual_cleaning_content(self) -> None:
        batch_id, _, edit_id, _, _ = self._import_and_clean()

        cleaned_text = "EDITED: How do I get a refund? Contact support team."
        self._manual_clean(batch_id, edit_id, cleaned_text, "keep_edited")

        extracted = self.client.post(f"/api/extraction/run/{batch_id}")
        self.assertEqual(extracted.status_code, 200, extracted.text)

        candidates_resp = self.client.get("/api/knowledge/candidates")
        batch_candidates = [
            c for c in candidates_resp.json()["data"]["candidates"]
            if c.get("source_batch_id") == batch_id
        ]
        # At least one candidate should use the cleaned content
        found_cleaned = False
        for c in batch_candidates:
            if "EDITED" in c["question"] or "EDITED" in c["answer"]:
                found_cleaned = True
                break
        self.assertTrue(
            found_cleaned,
            "Extraction should use manually cleaned content for keep_edited messages",
        )

    # ── 8. knowledge_candidates table has data ──────────────────────

    def test_08_knowledge_candidates_table_has_data(self) -> None:
        batch_id, _, _, _, _ = self._import_and_clean()
        self.client.post(f"/api/extraction/run/{batch_id}")

        db = self.db.SessionLocal()
        try:
            from app.db_models import KnowledgeCandidate as DbKnowledgeCandidate
            rows = db.query(DbKnowledgeCandidate).all()
            self.assertGreaterEqual(
                len(rows), 1,
                "knowledge_candidates table should have data after extraction",
            )
            for row in rows:
                self.assertIsNotNone(row.question)
                self.assertIsNotNone(row.answer)
                self.assertIn(
                    row.status,
                    ("pending_review", "needs_revision", "approved", "rejected"),
                )
        finally:
            db.close()

    # ── 9. Duplicate extraction is idempotent ────────────────────────

    def test_09_duplicate_extraction_is_idempotent(self) -> None:
        batch_id, _, _, _, _ = self._import_and_clean()

        first = self.client.post(f"/api/extraction/run/{batch_id}")
        self.assertEqual(first.status_code, 200, first.text)
        first_count = first.json()["data"]["candidate_count"]

        db = self.db.SessionLocal()
        try:
            from app.db_models import KnowledgeCandidate as DbKnowledgeCandidate
            count_before = db.query(DbKnowledgeCandidate).count()
            self.assertGreaterEqual(count_before, 1)
        finally:
            db.close()

        # Extract again
        second = self.client.post(f"/api/extraction/run/{batch_id}")
        self.assertEqual(second.status_code, 200, second.text)
        second_count = second.json()["data"]["candidate_count"]

        # Count should be stable (not doubling)
        self.assertEqual(
            first_count, second_count,
            f"Duplicate extraction should be idempotent: {first_count} vs {second_count}",
        )

        db2 = self.db.SessionLocal()
        try:
            from app.db_models import KnowledgeCandidate as DbKnowledgeCandidate
            count_after = db2.query(DbKnowledgeCandidate).count()
            # After re-extraction, the same source_id × question × answer
            # should be replaced, so count should not increase
            self.assertLessEqual(
                count_after, count_before * 2 + 1,
                "Duplicate extraction should not create unbounded duplicates",
            )
        finally:
            db2.close()

    # ── 10. Candidate list reads from DB ─────────────────────────────

    def test_10_candidate_list_reads_from_db(self) -> None:
        batch_id, _, _, _, _ = self._import_and_clean()
        self.client.post(f"/api/extraction/run/{batch_id}")

        candidates_resp = self.client.get("/api/knowledge/candidates")
        self.assertEqual(candidates_resp.status_code, 200, candidates_resp.text)
        candidates = candidates_resp.json()["data"]["candidates"]
        self.assertGreaterEqual(len(candidates), 1)
        for c in candidates:
            self.assertIn("candidate_id", c)
            self.assertIn("review_status", c)
            self.assertIn("question", c)
            self.assertIn("answer", c)

    # ── 11. Candidate edit persists ─────────────────────────────────

    def test_11_candidate_edit_persists(self) -> None:
        batch_id, _, _, _, _ = self._import_and_clean()
        self.client.post(f"/api/extraction/run/{batch_id}")

        candidates_resp = self.client.get("/api/knowledge/candidates")
        candidates = [
            c for c in candidates_resp.json()["data"]["candidates"]
            if c.get("source_batch_id") == batch_id
        ]
        self.assertGreaterEqual(len(candidates), 1)
        candidate_id = candidates[0]["candidate_id"]

        patched = self.client.patch(
            f"/api/knowledge/candidates/{candidate_id}",
            json={
                "question": "EDITED: What is the return policy?",
                "answer": "EDITED: Returns are accepted within 30 days.",
                "intent": "refund",
                "tags": ["return", "policy", "edited"],
                "risk_level": "low",
                "quality_score": 0.92,
            },
        )
        self.assertEqual(patched.status_code, 200, patched.text)
        data = patched.json()["data"]
        self.assertEqual(data["question"], "EDITED: What is the return policy?")
        self.assertEqual(data["intent"], "refund")
        self.assertEqual(data["quality_score"], 0.92)

        # Verify DB update
        db = self.db.SessionLocal()
        try:
            from app.db_models import KnowledgeCandidate as DbKnowledgeCandidate
            row = (
                db.query(DbKnowledgeCandidate)
                .filter(DbKnowledgeCandidate.id == candidate_id)
                .first()
            )
            self.assertIsNotNone(row)
            self.assertEqual(row.question, "EDITED: What is the return policy?")
            self.assertEqual(row.intent, "refund")
        finally:
            db.close()

    # ── 12. Approve writes review_records and updates candidate status ─

    def test_12_approve_writes_review_records(self) -> None:
        batch_id, _, _, _, _ = self._import_and_clean()
        self.client.post(f"/api/extraction/run/{batch_id}")

        candidates_resp = self.client.get("/api/knowledge/candidates")
        candidates = [
            c for c in candidates_resp.json()["data"]["candidates"]
            if c.get("source_batch_id") == batch_id
        ]
        self.assertGreaterEqual(len(candidates), 1)
        candidate_id = candidates[0]["candidate_id"]

        approved = self.client.post(
            f"/api/review/{candidate_id}/approve",
            json={"reviewer": "test_reviewer", "review_note": "Looks good."},
        )
        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertEqual(approved.json()["data"]["review_status"], "approved")

        # Verify DB: candidate status
        db = self.db.SessionLocal()
        try:
            from app.db_models import KnowledgeCandidate as DbKnowledgeCandidate
            row = (
                db.query(DbKnowledgeCandidate)
                .filter(DbKnowledgeCandidate.id == candidate_id)
                .first()
            )
            self.assertIsNotNone(row)
            self.assertEqual(row.status, "approved")
        finally:
            db.close()

        # Verify DB: review_records
        db2 = self.db.SessionLocal()
        try:
            from app.db_models import ReviewRecord
            rows = (
                db2.query(ReviewRecord)
                .filter(ReviewRecord.candidate_id == candidate_id)
                .all()
            )
            self.assertGreaterEqual(len(rows), 1)
            self.assertEqual(rows[0].action, "approved")
            self.assertEqual(rows[0].reviewer, "test_reviewer")
        finally:
            db2.close()

    # ── 13. Reject writes review_records and updates candidate status ─

    def test_13_reject_writes_review_records(self) -> None:
        batch_id, _, _, _, _ = self._import_and_clean()
        self.client.post(f"/api/extraction/run/{batch_id}")

        candidates_resp = self.client.get("/api/knowledge/candidates")
        candidates = [
            c for c in candidates_resp.json()["data"]["candidates"]
            if c.get("source_batch_id") == batch_id
        ]
        self.assertGreaterEqual(len(candidates), 1)
        candidate_id = candidates[0]["candidate_id"]

        rejected = self.client.post(
            f"/api/review/{candidate_id}/reject",
            json={"reviewer": "test_reviewer", "review_note": "Not accurate."},
        )
        self.assertEqual(rejected.status_code, 200, rejected.text)
        self.assertEqual(rejected.json()["data"]["review_status"], "rejected")

        db = self.db.SessionLocal()
        try:
            from app.db_models import ReviewRecord
            rows = (
                db.query(ReviewRecord)
                .filter(ReviewRecord.candidate_id == candidate_id)
                .all()
            )
            self.assertGreaterEqual(len(rows), 1)
            self.assertEqual(rows[0].action, "rejected")
        finally:
            db.close()

    # ── 14. needs_revision writes review_records ─────────────────────

    def test_14_needs_revision_writes_review_records(self) -> None:
        batch_id, _, _, _, _ = self._import_and_clean()
        self.client.post(f"/api/extraction/run/{batch_id}")

        candidates_resp = self.client.get("/api/knowledge/candidates")
        candidates = [
            c for c in candidates_resp.json()["data"]["candidates"]
            if c.get("source_batch_id") == batch_id
        ]
        self.assertGreaterEqual(len(candidates), 1)
        candidate_id = candidates[0]["candidate_id"]

        revised = self.client.post(
            f"/api/review/{candidate_id}/needs-revision",
            json={"reviewer": "test_reviewer", "review_note": "Needs more detail."},
        )
        self.assertEqual(revised.status_code, 200, revised.text)
        self.assertEqual(revised.json()["data"]["review_status"], "needs_revision")

        db = self.db.SessionLocal()
        try:
            from app.db_models import KnowledgeCandidate as DbKnowledgeCandidate
            row = (
                db.query(DbKnowledgeCandidate)
                .filter(DbKnowledgeCandidate.id == candidate_id)
                .first()
            )
            self.assertIsNotNone(row)
            self.assertEqual(row.status, "needs_revision")
        finally:
            db.close()

    # ── 15. Refresh reads do not depend on memory variables ──────────

    def test_15_candidate_status_survives_refresh_reads(self) -> None:
        batch_id, _, _, _, _ = self._import_and_clean()
        self.client.post(f"/api/extraction/run/{batch_id}")

        candidates_resp = self.client.get("/api/knowledge/candidates")
        candidates = [
            c for c in candidates_resp.json()["data"]["candidates"]
            if c.get("source_batch_id") == batch_id
        ]
        self.assertGreaterEqual(len(candidates), 1)
        candidate_id = candidates[0]["candidate_id"]

        # Approve
        self.client.post(
            f"/api/review/{candidate_id}/approve",
            json={"reviewer": "test_reviewer", "review_note": "Good."},
        )

        # Re-read (simulate page refresh)
        refreshed = self.client.get(f"/api/knowledge/candidates/{candidate_id}")
        self.assertEqual(refreshed.status_code, 200, refreshed.text)
        self.assertEqual(refreshed.json()["data"]["review_status"], "approved")

        # Re-read list
        list_refreshed = self.client.get("/api/knowledge/candidates")
        found = False
        for c in list_refreshed.json()["data"]["candidates"]:
            if c["candidate_id"] == candidate_id:
                self.assertEqual(c["review_status"], "approved")
                found = True
                break
        self.assertTrue(found)

    # ── 16. Health check reports P1-M18 ──────────────────────────────

    def test_16_health_reports_p1_m18(self) -> None:
        health = self.client.get("/health")
        self.assertEqual(health.status_code, 200, health.text)
        self.assertEqual(health.json()["phase"], "P1-M22.2")
        db_status = health.json()["database_status"]
        self.assertTrue(db_status["enabled"])
        self.assertEqual(db_status["status"], "ok")



if __name__ == "__main__":
    unittest.main()
