"""Tests for P1-M23.2 RAG Corpus Tools.

Verifies:
- inspect_rag_corpus.py gracefully SKIPs when DATABASE_URL unset.
- cleanup_rag_test_data.py defaults to dry-run.
- cleanup_rag_test_data.py does not delete without --apply.
- seed_rag_eval_corpus.py sample data is structurally valid.
- check_embedding_provider.py does not leak API keys.
- mock provider readiness is reported correctly.
- Does NOT require real external API.
- Does NOT require real Render database.
"""

import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT_DIR = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT_DIR / "scripts"


class RagCorpusToolsTest(unittest.TestCase):
    """Test corpus tools without requiring a real database."""

    @classmethod
    def setUpClass(cls) -> None:
        if str(SCRIPTS_DIR) not in sys.path:
            sys.path.insert(0, str(SCRIPTS_DIR))

    def setUp(self) -> None:
        # Ensure DATABASE_URL is not set for safe testing
        self._saved_db_url = os.environ.pop("DATABASE_URL", None)

    def tearDown(self) -> None:
        if self._saved_db_url:
            os.environ["DATABASE_URL"] = self._saved_db_url

    def test_01_inspect_skips_without_database_url(self):
        """inspect_rag_corpus should SKIP when DATABASE_URL is not set."""
        from inspect_rag_corpus import inspect_corpus
        result = inspect_corpus(verbose=False)
        self.assertEqual(result["status"], "skipped")
        self.assertIn("no DATABASE_URL", result["reason"])

    def test_02_cleanup_skips_without_database_url(self):
        """cleanup_rag_test_data should SKIP when DATABASE_URL is not set."""
        from cleanup_rag_test_data import run_cleanup
        result = run_cleanup(apply_changes=False, verbose=False)
        self.assertEqual(result["status"], "skipped")

    def test_03_cleanup_default_dry_run(self):
        """cleanup should default to dry-run; apply_changes=False means no deletes."""
        from cleanup_rag_test_data import run_cleanup
        result = run_cleanup(apply_changes=False, verbose=False)
        # Should be skipped (no DB) or dry_run, but never "applied"
        self.assertNotEqual(result.get("status"), "applied")

    def test_04_pollution_rules_detect_harness_content(self):
        """Pollution rules should detect harness manual cleaning placeholders."""
        from cleanup_rag_test_data import (
            _match_harness_manual_cleaning,
            _match_harness_automated,
        )
        text = "Question: Manually verified content - harness automated cleaning."
        self.assertTrue(_match_harness_manual_cleaning(text, {}))
        self.assertTrue(_match_harness_automated(text, {}))

        clean_text = "Question: How do I return shoes and get a refund?"
        self.assertFalse(_match_harness_manual_cleaning(clean_text, {}))
        self.assertFalse(_match_harness_automated(clean_text, {}))

    def test_05_seed_conversations_are_valid(self):
        """Seed script conversations should have required fields and be English."""
        from seed_rag_eval_corpus import EVAL_CORPUS_CONVERSATIONS

        self.assertIsInstance(EVAL_CORPUS_CONVERSATIONS, list)
        self.assertGreaterEqual(len(EVAL_CORPUS_CONVERSATIONS), 3,
                               "Need at least 3 conversations")

        for conv in EVAL_CORPUS_CONVERSATIONS:
            self.assertIn("conversation_id", conv)
            self.assertIn("messages", conv)
            self.assertGreaterEqual(len(conv["messages"]), 2,
                                    f"Need at least 2 messages in {conv['conversation_id']}")
            for msg in conv["messages"]:
                self.assertIn("message_id", msg)
                self.assertIn("role", msg)
                self.assertIn("content", msg)
                self.assertIn("timestamp", msg)
                # Content should be non-empty English
                self.assertTrue(len(msg["content"]) > 10,
                               f"Content too short: {msg['content'][:30]}")
                # Should not contain obvious placeholder text
                self.assertNotIn("Manually verified", msg["content"])
                self.assertNotIn("harness automated", msg["content"])

    def test_06_seed_covers_required_intents(self):
        """Seed corpus should cover refund/shipping/escalation intents."""
        from seed_rag_eval_corpus import EVAL_CORPUS_CONVERSATIONS

        all_text = " ".join(
            msg["content"].lower()
            for conv in EVAL_CORPUS_CONVERSATIONS
            for msg in conv["messages"]
        )

        # Should cover refund/return
        self.assertTrue(
            any(kw in all_text for kw in ["refund", "return", "money back"]),
            "Missing refund/return content")

        # Should cover shipping/tracking
        self.assertTrue(
            any(kw in all_text for kw in ["shipping", "tracking", "order"]),
            "Missing shipping/tracking content")

        # Should cover escalation
        self.assertTrue(
            any(kw in all_text for kw in ["human agent", "transfer", "speak to"]),
            "Missing escalation content")

    def test_07_embedding_check_mock_ready(self):
        """check_embedding_provider should report mock_ready=true without API key."""
        from check_embedding_provider import check_provider
        result = check_provider(verify=False)
        self.assertTrue(result.get("mock_ready"))
        # Without API key, should be mock or report provider_ready
        self.assertIn(
            result.get("provider"),
            ["mock", "openai", "openai_compatible", "siliconflow", "jina"],
        )

    def test_08_embedding_check_no_key_leak(self):
        """check_embedding_provider output must never contain API key text."""
        import io
        import sys as _sys
        from check_embedding_provider import check_provider

        # Set a fake key to test that it doesn't leak
        os.environ["EMBEDDING_API_KEY"] = "sk-test-secret-key-12345"
        try:
            old_stdout = _sys.stdout
            _sys.stdout = captured = io.StringIO()
            try:
                check_provider(verify=False)
            finally:
                _sys.stdout = old_stdout
            output = captured.getvalue()
            self.assertNotIn("sk-test-secret-key-12345", output,
                             "API key must not appear in output")
        finally:
            os.environ.pop("EMBEDDING_API_KEY", None)

    def test_09_chinese_detection(self):
        """_is_chinese should detect CJK characters."""
        from inspect_rag_corpus import _is_chinese
        self.assertTrue(_is_chinese("我买的产品有质量问题，怎么退货？"))
        self.assertTrue(_is_chinese("从中国发货到德国大概需要多长时间？"))
        self.assertFalse(_is_chinese("How do I return shoes and get a refund?"))
        self.assertFalse(_is_chinese("short"))

    def test_10_pollution_score(self):
        """_pollution_score should detect harness pollution, skip clean text."""
        from inspect_rag_corpus import _pollution_score
        is_p, reason = _pollution_score(
            "Question: Manually verified content - harness automated cleaning.",
            {},
        )
        self.assertTrue(is_p)
        self.assertEqual(reason, "harness_manual_cleaning_placeholder")

        is_p2, reason2 = _pollution_score(
            "Question: How do I return shoes and get a refund? Answer: You can return within 30 days.",
            {"question": "How do I return shoes?"},
        )
        self.assertFalse(is_p2)


if __name__ == "__main__":
    unittest.main()
