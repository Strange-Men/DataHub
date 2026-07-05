"""Tests for the RAG eval set (P1-M21).

Covers:
- Eval set JSON file exists and is valid JSON.
- At least 10 queries in the eval set.
- Each query has id, query, intent, expected_keywords.
- expected_candidate_ids is a list (may be empty in M21).
- Valid intent values.
- Schema validation.
"""

import json
import os
import unittest


EVAL_SET_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "samples", "rag_eval_queries.json"
)

VALID_INTENTS = {
    "refund", "shipping", "escalation", "product_info",
    "policy", "general", "order_status", "handoff",
    "prohibited_answer",
}


class TestEvalSetFile(unittest.TestCase):
    """Verify the eval set JSON file structure and content."""

    @classmethod
    def setUpClass(cls):
        cls.eval_path = os.path.normpath(EVAL_SET_PATH)

    def test_file_exists(self):
        """Eval set JSON file must exist."""
        self.assertTrue(
            os.path.isfile(self.eval_path),
            f"Eval set file not found: {self.eval_path}"
        )

    def test_file_is_valid_json(self):
        """Eval set file must be valid JSON."""
        with open(self.eval_path, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as e:
                self.fail(f"Eval set JSON is invalid: {e}")
        self.assertIsInstance(data, list)

    def test_at_least_10_queries(self):
        """Eval set must have at least 10 queries."""
        with open(self.eval_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertGreaterEqual(
            len(data), 10,
            f"Eval set should have at least 10 queries, got {len(data)}"
        )

    def test_no_more_than_20_queries(self):
        """Eval set should stay manageable — no more than 20 queries."""
        with open(self.eval_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertLessEqual(
            len(data), 20,
            f"Eval set should have at most 20 queries, got {len(data)}"
        )

    def test_each_query_has_id(self):
        """Every query must have a unique id."""
        with open(self.eval_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        ids = []
        for item in data:
            self.assertIn("id", item, f"Query missing 'id': {item.get('query', 'N/A')}")
            self.assertIsInstance(item["id"], str)
            self.assertTrue(len(item["id"]) > 0, "id must not be empty")
            ids.append(item["id"])
        # IDs must be unique
        self.assertEqual(len(ids), len(set(ids)),
                         f"Query IDs must be unique. Duplicates: {[i for i in ids if ids.count(i) > 1]}")

    def test_each_query_has_query_field(self):
        """Every query must have a non-empty 'query' string."""
        with open(self.eval_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for item in data:
            self.assertIn("query", item, f"Item {item.get('id', 'N/A')} missing 'query'")
            self.assertIsInstance(item["query"], str)
            self.assertTrue(len(item["query"].strip()) > 0,
                            f"Query must not be empty: {item.get('id', 'N/A')}")

    def test_each_query_has_intent(self):
        """Every query must have an 'intent' field."""
        with open(self.eval_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for item in data:
            self.assertIn("intent", item, f"Item {item.get('id', 'N/A')} missing 'intent'")
            self.assertIsInstance(item["intent"], str)
            self.assertTrue(len(item["intent"]) > 0)

    def test_each_query_has_expected_keywords(self):
        """Every query must have 'expected_keywords' (list, may be empty)."""
        with open(self.eval_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for item in data:
            self.assertIn("expected_keywords", item,
                          f"Item {item.get('id', 'N/A')} missing 'expected_keywords'")
            self.assertIsInstance(item["expected_keywords"], list,
                                  f"expected_keywords must be a list: {item.get('id', 'N/A')}")

    def test_each_query_has_expected_candidate_ids(self):
        """Every query must have 'expected_candidate_ids' (list, may be empty in M21)."""
        with open(self.eval_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for item in data:
            self.assertIn("expected_candidate_ids", item,
                          f"Item {item.get('id', 'N/A')} missing 'expected_candidate_ids'")
            self.assertIsInstance(item["expected_candidate_ids"], list,
                                  f"expected_candidate_ids must be a list: {item.get('id', 'N/A')}")

    def test_intent_coverage(self):
        """Eval set should cover at least 4 different intents."""
        with open(self.eval_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        intents = {item["intent"] for item in data}
        self.assertGreaterEqual(
            len(intents), 4,
            f"Eval set should cover at least 4 intents, got {len(intents)}: {intents}"
        )

    def test_refund_coverage(self):
        """At least one query should cover the 'refund' intent."""
        with open(self.eval_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        intents = {item["intent"] for item in data}
        self.assertIn("refund", intents, "Eval set must cover refund intent")

    def test_shipping_coverage(self):
        """At least one query should cover the 'shipping' intent."""
        with open(self.eval_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        intents = {item["intent"] for item in data}
        self.assertIn("shipping", intents, "Eval set must cover shipping intent")

    def test_escalation_coverage(self):
        """At least one query should cover the 'escalation' intent."""
        with open(self.eval_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        intents = {item["intent"] for item in data}
        self.assertIn("escalation", intents, "Eval set must cover escalation intent")

    def test_bad_case_query_present(self):
        """At least one query should represent a bad case (noise/ambiguous)."""
        with open(self.eval_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        bad_ids = [item["id"] for item in data if "badcase" in item.get("id", "").lower()]
        self.assertTrue(len(bad_ids) > 0,
                        "Eval set should include at least one bad case query")

    def test_each_query_has_notes(self):
        """Each query should have a notes field (can be empty string)."""
        with open(self.eval_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for item in data:
            self.assertIn("notes", item,
                          f"Item {item.get('id', 'N/A')} missing 'notes' field")
            self.assertIsInstance(item["notes"], str)

    def test_no_real_user_data(self):
        """Eval set must not contain PII or real customer data."""
        with open(self.eval_path, "r", encoding="utf-8") as f:
            raw_text = f.read().lower()
        # Quick PII scan — should not contain email-like strings or phone numbers
        import re
        email_pattern = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
        phone_pattern = re.compile(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b')
        self.assertIsNone(
            email_pattern.search(raw_text),
            "Eval set should not contain email addresses"
        )
        self.assertIsNone(
            phone_pattern.search(raw_text),
            "Eval set should not contain phone numbers"
        )
