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


class ManualCleaningTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        self.run_id = uuid4().hex[:8]

    def _import_manual_cleaning_sample(self) -> str:
        unique = self.run_id
        payload = {
            "source_name": f"manual_cleaning_{unique}",
            "conversations": [
                {
                    "conversation_id": f"manual_cleaning_conv_{unique}",
                    "messages": [
                        {
                            "message_id": "msg_drop_q",
                            "role": "customer",
                            "content": f"Should manualdrop{unique} become knowledge?",
                            "timestamp": "2026-07-03T10:00:00",
                        },
                        {
                            "message_id": "msg_drop_a",
                            "role": "agent",
                            "content": f"manualdrop{unique} should not become a candidate.",
                            "timestamp": "2026-07-03T10:01:00",
                        },
                        {
                            "message_id": "msg_edit_q",
                            "role": "customer",
                            "content": f"Original manualedit{unique} shipping question?",
                            "timestamp": "2026-07-03T10:02:00",
                        },
                        {
                            "message_id": "msg_edit_a",
                            "role": "agent",
                            "content": f"Original manualedit{unique} answer.",
                            "timestamp": "2026-07-03T10:03:00",
                        },
                        {
                            "message_id": "msg_review_q",
                            "role": "customer",
                            "content": f"Should manualreview{unique} be checked?",
                            "timestamp": "2026-07-03T10:04:00",
                        },
                        {
                            "message_id": "msg_review_a",
                            "role": "agent",
                            "content": f"manualreview{unique} needs a reviewer.",
                            "timestamp": "2026-07-03T10:05:00",
                        },
                        {
                            "message_id": "msg_old_q",
                            "role": "customer",
                            "content": f"How long does manualold{unique} shipping take to Spain?",
                            "timestamp": "2026-07-03T10:06:00",
                        },
                        {
                            "message_id": "msg_old_a",
                            "role": "agent",
                            "content": f"manualold{unique} shipping to Spain takes 7-12 business days.",
                            "timestamp": "2026-07-03T10:07:00",
                        },
                    ],
                }
            ],
        }
        imported = self.client.post("/api/sources/import-json", json=payload)
        self.assertEqual(imported.status_code, 200, imported.text)
        return imported.json()["data"]["batch_id"]

    def _raw_batch_text(self, batch_id: str) -> str:
        raw_path = ROOT_DIR / "backend" / "storage" / "raw_batches" / f"{batch_id}.json"
        return raw_path.read_text(encoding="utf-8")

    def _manual_clean(self, batch_id: str, message_id: str, **overrides: object) -> dict:
        payload = {
            "content": f"Manually cleaned content {self.run_id}.",
            "manual_action": "keep",
            "cleaner": "local_cleaner",
            "cleaning_note": "Verified by manual cleaning test.",
        }
        payload.update(overrides)
        response = self.client.patch(
            f"/api/sanitized/{batch_id}/messages/{message_id}/manual-clean",
            json=payload,
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["data"]

    def test_manual_cleaning_updates_sanitized_only_and_guides_extraction(self) -> None:
        batch_id = self._import_manual_cleaning_sample()
        raw_before = self._raw_batch_text(batch_id)

        cleaned = self.client.post(f"/api/cleaning/run/{batch_id}")
        self.assertEqual(cleaned.status_code, 200, cleaned.text)

        drop_record = self._manual_clean(
            batch_id,
            "msg_drop_q",
            content=f"manualdrop{self.run_id} should be removed.",
            manual_action="drop",
            cleaning_note="No business value after review.",
        )
        edit_record = self._manual_clean(
            batch_id,
            "msg_edit_q",
            content=f"How fast is manualcleanedited{self.run_id} delivery?",
            manual_action="keep_edited",
            cleaning_note="Normalized customer question.",
        )
        self._manual_clean(
            batch_id,
            "msg_edit_a",
            content=f"manualcleanedited{self.run_id} delivery takes 5 business days.",
            manual_action="keep_edited",
            cleaning_note="Normalized agent answer.",
        )
        self._manual_clean(
            batch_id,
            "msg_review_q",
            content=f"manualreview{self.run_id} needs review.",
            manual_action="needs_review",
            cleaning_note="Needs senior cleaner review.",
        )

        self.assertEqual(self._raw_batch_text(batch_id), raw_before)
        self.assertEqual(drop_record["manual_action"], "drop")
        self.assertEqual(edit_record["manual_action"], "keep_edited")

        record_path = (
            ROOT_DIR
            / "backend"
            / "storage"
            / "manual_cleaning_records"
            / f"{edit_record['record_id']}.json"
        )
        self.assertTrue(record_path.exists())

        sanitized = self.client.get(f"/api/sanitized/{batch_id}")
        self.assertEqual(sanitized.status_code, 200, sanitized.text)
        messages = sanitized.json()["data"]["messages"]
        by_source_id = {message["source_message_id"]: message for message in messages}

        edited_message = by_source_id["msg_edit_q"]
        self.assertEqual(edited_message["manual_cleaning_status"], "cleaned")
        self.assertEqual(edited_message["manual_action"], "keep_edited")
        self.assertEqual(edited_message["cleaner"], "local_cleaner")
        self.assertEqual(edited_message["cleaning_note"], "Normalized customer question.")
        self.assertIn(f"manualcleanedited{self.run_id}", edited_message["manual_cleaned_content"])

        old_message = by_source_id["msg_old_q"]
        self.assertEqual(old_message["manual_cleaning_status"], "not_cleaned")
        self.assertIsNone(old_message["manual_action"])

        extracted = self.client.post(f"/api/extraction/run/{batch_id}")
        self.assertEqual(extracted.status_code, 200, extracted.text)

        candidates = self.client.get("/api/knowledge/candidates")
        self.assertEqual(candidates.status_code, 200, candidates.text)
        batch_candidates = [
            candidate
            for candidate in candidates.json()["data"]["candidates"]
            if candidate["source_batch_id"] == batch_id
        ]
        questions = " ".join(candidate["question"] for candidate in batch_candidates)
        answers = " ".join(candidate["answer"] for candidate in batch_candidates)
        combined = f"{questions} {answers}"

        self.assertIn(f"manualcleanedited{self.run_id}", combined)
        self.assertIn(f"manualold{self.run_id}", combined)
        self.assertNotIn(f"manualdrop{self.run_id}", combined)
        self.assertNotIn(f"manualreview{self.run_id}", combined)

        edited_candidate = next(
            candidate
            for candidate in batch_candidates
            if f"manualcleanedited{self.run_id}" in candidate["question"]
        )
        self.assertEqual(edited_candidate["review_status"], "pending_review")
        self.assertEqual(edited_candidate["manual_cleaning_status"], "cleaned")
        self.assertIn("keep_edited", edited_candidate["manual_action"])


if __name__ == "__main__":
    unittest.main()
