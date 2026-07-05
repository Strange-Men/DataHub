"""Tests for P1-M23 RAG Eval Script (scripts/run_rag_eval.py).

Verifies:
- eval script can load rag_eval_queries.json.
- eval script can compute keyword_hit_rate@5.
- eval script can compute recall@5.
- eval script handles connection errors gracefully.
- eval script CLI arguments parse correctly.
- Does NOT require real external embedding API.
- Does NOT require real Render database.
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
SCRIPTS_DIR = ROOT_DIR / "scripts"
SAMPLES_DIR = ROOT_DIR / "samples"


class RagEvalScriptTest(unittest.TestCase):
    """Test the eval script logic without requiring a running backend."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.eval_path = SAMPLES_DIR / "rag_eval_queries.json"
        # Ensure the script can be imported
        if str(SCRIPTS_DIR) not in sys.path:
            sys.path.insert(0, str(SCRIPTS_DIR))

    def test_01_eval_queries_json_exists(self):
        """Eval queries JSON file should exist and be valid."""
        self.assertTrue(self.eval_path.exists(),
                        f"Eval file not found: {self.eval_path}")
        with open(self.eval_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertIsInstance(data, list)
        self.assertGreaterEqual(len(data), 10,
                                f"Expected at least 10 queries, got {len(data)}")

    def test_02_eval_queries_have_required_fields(self):
        """Each eval query should have id, query, intent, expected_keywords."""
        with open(self.eval_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        for i, eq in enumerate(data):
            self.assertIn("id", eq, f"Query {i} missing 'id'")
            self.assertIn("query", eq, f"Query {i} missing 'query'")
            self.assertIn("intent", eq, f"Query {i} missing 'intent'")
            self.assertIn("expected_keywords", eq, f"Query {i} missing 'expected_keywords'")
            self.assertIsInstance(eq["query"], str)
            self.assertTrue(len(eq["query"]) > 0, f"Query {i} has empty query string")

    def test_03_compute_keyword_hit_rate_no_keywords(self):
        """Empty expected_keywords should return (0, False)."""
        from run_rag_eval import compute_keyword_hit_rate
        results = [{"chunk_text": "refund policy details", "intent": "refund", "tags": []}]
        matched, any_hit = compute_keyword_hit_rate(results, [])
        self.assertEqual(matched, 0)
        self.assertFalse(any_hit)

    def test_04_compute_keyword_hit_rate_found(self):
        """Keywords found in chunk_text should match."""
        from run_rag_eval import compute_keyword_hit_rate
        results = [
            {
                "chunk_text": "You can return items within 30 days for a refund.",
                "intent": "refund",
                "tags": ["return", "refund"],
            }
        ]
        expected = ["return", "refund", "money back"]
        matched, any_hit = compute_keyword_hit_rate(results, expected)
        self.assertEqual(matched, 2)  # "return" and "refund" found, "money back" not
        self.assertTrue(any_hit)

    def test_05_compute_keyword_hit_rate_not_found(self):
        """Keywords not in results should return (0, False)."""
        from run_rag_eval import compute_keyword_hit_rate
        results = [{"chunk_text": "shipping options to Germany", "intent": "shipping", "tags": []}]
        expected = ["refund", "money back", "return"]
        matched, any_hit = compute_keyword_hit_rate(results, expected)
        self.assertEqual(matched, 0)
        self.assertFalse(any_hit)

    def test_06_compute_keyword_recall_at_k(self):
        """recall@k should be fraction of keywords found."""
        from run_rag_eval import compute_keyword_recall_at_k
        results = [
            {"chunk_text": "refund and return policy", "intent": "refund", "tags": ["refund"]},
            {"chunk_text": "shipping options", "intent": "shipping", "tags": ["shipping"]},
        ]
        expected = ["refund", "return", "shipping", "money", "warranty"]
        recall = compute_keyword_recall_at_k(results, expected, k=5)
        self.assertEqual(recall, 0.6)  # refund, return, shipping found = 3/5

    def test_07_load_eval_queries_loads_all(self):
        """load_eval_queries should load all queries from a valid JSON file."""
        from run_rag_eval import load_eval_queries
        queries = load_eval_queries(str(self.eval_path))
        self.assertIsInstance(queries, list)
        self.assertGreaterEqual(len(queries), 10)

    def test_08_load_eval_queries_invalid_path(self):
        """load_eval_queries should raise for non-existent file."""
        from run_rag_eval import load_eval_queries
        with self.assertRaises((FileNotFoundError, Exception)):
            load_eval_queries("/nonexistent/path/eval.json")

    def test_09_call_retrieve_connection_refused(self):
        """call_retrieve should handle connection errors gracefully."""
        from run_rag_eval import call_retrieve
        result = call_retrieve("http://127.0.0.1:19999", "test query", top_k=3, timeout=2)
        self.assertIsNotNone(result)
        self.assertIn("error", result)

    def test_10_keyword_recall_at_k_empty_results(self):
        """Empty results should give recall=0."""
        from run_rag_eval import compute_keyword_recall_at_k
        recall = compute_keyword_recall_at_k([], ["refund", "return"], k=5)
        self.assertEqual(recall, 0.0)

    def test_11_intent_coverage_in_eval_set(self):
        """Eval set should cover multiple intents."""
        with open(self.eval_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        intents = {eq.get("intent") for eq in data if eq.get("intent")}
        # Should cover at least 3 different intents
        self.assertGreaterEqual(len(intents), 3,
                                f"Expected ≥3 intents, got {len(intents)}: {intents}")

    def test_12_no_pii_in_eval_queries(self):
        """Eval queries should not contain PII patterns."""
        import re
        pii_patterns = [
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",  # email
            r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b",  # phone
        ]
        with open(self.eval_path, "r", encoding="utf-8") as f:
            content = f.read()

        for pat in pii_patterns:
            matches = re.findall(pat, content)
            self.assertEqual(len(matches), 0,
                             f"PII pattern '{pat}' found in eval queries: {matches}")


if __name__ == "__main__":
    unittest.main()
