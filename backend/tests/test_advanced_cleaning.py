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


class AdvancedCleaningTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        self.run_id = uuid4().hex[:8]

    def _import_dirty_sample(self) -> str:
        long_text = "This response is intentionally too long. " * 35
        payload = {
            "source_name": f"p1_m12_advanced_cleaning_{self.run_id}",
            "conversations": [
                {
                    "conversation_id": f"advanced_cleaning_conv_{self.run_id}",
                    "messages": [
                        {
                            "message_id": "msg_exact_1",
                            "role": "customer",
                            "content": "Where is my order ORDER-ABC12345?",
                            "timestamp": "2026-07-03T10:00:00",
                        },
                        {
                            "message_id": "msg_exact_2",
                            "role": "customer",
                            "content": "Where is my order ORDER-ABC12345?",
                            "timestamp": "2026-07-03T10:00:01",
                        },
                        {
                            "message_id": "msg_near_1",
                            "role": "customer",
                            "content": "How long does shipping take to Canada?",
                            "timestamp": "2026-07-03T10:00:02",
                        },
                        {
                            "message_id": "msg_near_2",
                            "role": "customer",
                            "content": "How long does shipping take to Canada??",
                            "timestamp": "2026-07-03T10:00:03",
                        },
                        {
                            "message_id": "msg_empty",
                            "role": "customer",
                            "content": "   ",
                            "timestamp": "2026-07-03T10:00:04",
                        },
                        {
                            "message_id": "msg_short",
                            "role": "customer",
                            "content": "ok",
                            "timestamp": "2026-07-03T10:00:05",
                        },
                        {
                            "message_id": "msg_long",
                            "role": "agent",
                            "content": long_text,
                            "timestamp": "2026-07-03T10:00:06",
                        },
                        {
                            "message_id": "msg_repeat",
                            "role": "customer",
                            "content": "!!!!!!",
                            "timestamp": "2026-07-03T10:00:07",
                        },
                        {
                            "message_id": "msg_symbol",
                            "role": "customer",
                            "content": "!!! ??? ###",
                            "timestamp": "2026-07-03T10:00:08",
                        },
                        {
                            "message_id": "msg_noise",
                            "role": "customer",
                            "content": "free money click here promo spam lol random text",
                            "timestamp": "2026-07-03T10:00:09",
                        },
                        {
                            "message_id": "msg_pii",
                            "role": "customer",
                            "content": (
                                "My name is Alice Example, email alice@example.test, "
                                "phone +1 202 555 0101, order number ORDER-XYZ12345, "
                                "tracking number TRK1234567890, ship to 123 Example Street, "
                                "Testville, zip code 12345, card 4111 1111 1111 1111"
                            ),
                            "timestamp": "2026-07-03T10:00:10",
                        },
                        {
                            "message_id": "msg_good_question",
                            "role": "customer",
                            "content": "How long does shipping take to Mexico?",
                            "timestamp": "2026-07-03T10:00:11",
                        },
                        {
                            "message_id": "msg_good_answer",
                            "role": "agent",
                            "content": "Shipping to Mexico usually takes 7-12 business days after dispatch.",
                            "timestamp": "2026-07-03T10:00:12",
                        },
                    ],
                }
            ],
        }
        imported = self.client.post("/api/sources/import-json", json=payload)
        self.assertEqual(imported.status_code, 200, imported.text)
        return imported.json()["data"]["batch_id"]

    def test_advanced_cleaning_flags_scores_and_extraction_boundary(self) -> None:
        health = self.client.get("/health")
        self.assertEqual(health.status_code, 200, health.text)
        self.assertEqual(health.json()["phase"], "P1-M20")

        batch_id = self._import_dirty_sample()
        cleaned = self.client.post(f"/api/cleaning/run/{batch_id}")
        self.assertEqual(cleaned.status_code, 200, cleaned.text)
        cleaning_data = cleaned.json()["data"]

        self.assertGreaterEqual(cleaning_data["exact_duplicate_count"], 1)
        self.assertGreaterEqual(cleaning_data["near_duplicate_count"], 1)
        self.assertEqual(cleaning_data["dropped_message_count"], 1)
        self.assertGreaterEqual(cleaning_data["low_quality_count"], 3)
        self.assertGreaterEqual(cleaning_data["noise_count"], 1)
        self.assertGreaterEqual(cleaning_data["pii_detected_count"], 1)
        self.assertIn("average_quality_score", cleaning_data)
        self.assertGreaterEqual(cleaning_data["drop_recommended_count"], 1)

        sanitized = self.client.get(f"/api/sanitized/{batch_id}")
        self.assertEqual(sanitized.status_code, 200, sanitized.text)
        messages = sanitized.json()["data"]["messages"]
        self.assertEqual(len(messages), cleaning_data["sanitized_message_count"])

        for message in messages:
            self.assertIn("cleaning_issues", message)
            self.assertIn("risk_flags", message)
            self.assertIn("quality_score", message)
            self.assertIn("quality_level", message)
            self.assertIn("suggested_action", message)

        messages_by_id = {message["source_message_id"]: message for message in messages}
        self.assertIn("exact_duplicate", messages_by_id["msg_exact_2"]["cleaning_issues"])
        self.assertIn("near_duplicate", messages_by_id["msg_near_2"]["cleaning_issues"])
        self.assertIn("too_short", messages_by_id["msg_short"]["cleaning_issues"])
        self.assertIn("too_long", messages_by_id["msg_long"]["cleaning_issues"])
        self.assertIn("repeated_chars", messages_by_id["msg_repeat"]["cleaning_issues"])
        self.assertIn("symbol_noise", messages_by_id["msg_symbol"]["cleaning_issues"])
        self.assertIn("possible_ad", messages_by_id["msg_noise"]["cleaning_issues"])

        pii_message = messages_by_id["msg_pii"]
        for pii_type in [
            "EMAIL",
            "PHONE",
            "ORDER_ID",
            "TRACKING_ID",
            "ADDRESS",
            "NAME",
            "ZIP_CODE",
            "PAYMENT_SENSITIVE",
        ]:
            self.assertIn(pii_type, pii_message["pii_types"])
        self.assertIn("[PAYMENT_SENSITIVE]", pii_message["content"])
        self.assertIn("contains_payment_sensitive", pii_message["risk_flags"])

        extracted = self.client.post(f"/api/extraction/run/{batch_id}")
        self.assertEqual(extracted.status_code, 200, extracted.text)
        self.assertGreaterEqual(extracted.json()["data"]["candidate_count"], 1)
        candidates = self.client.get("/api/knowledge/candidates")
        self.assertEqual(candidates.status_code, 200, candidates.text)
        batch_candidates = [
            candidate
            for candidate in candidates.json()["data"]["candidates"]
            if candidate["source_batch_id"] == batch_id
        ]
        self.assertTrue(
            all("!!!!!!" not in candidate["question"] for candidate in batch_candidates)
        )
        self.assertTrue(
            all(candidate["review_status"] == "pending_review" for candidate in batch_candidates)
        )


if __name__ == "__main__":
    unittest.main()
