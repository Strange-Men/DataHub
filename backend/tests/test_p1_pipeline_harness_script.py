"""Lightweight tests for P1 pipeline harness internal logic.

These tests verify the harness script's internal functions (trace_id format,
response excerpt truncation, step result data structures, pgvector check graceful
SKIP behaviour) WITHOUT connecting to any external service.

No network, no database, no running FastAPI required.
"""

import json
import os
import re
import sys
import unittest


# ---------------------------------------------------------------------------
# Helpers — direct copies or imports from the harness script
# ---------------------------------------------------------------------------

# Add scripts/ to path so we can import from the harness module
_scripts_dir = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)


class TestTraceIdFormat(unittest.TestCase):
    """Verify trace_id generation format."""

    def test_trace_id_format(self):
        from run_p1_pipeline_harness import _trace_id

        tid = _trace_id()
        # Expected format: p1-harness-YYYYMMDD-HHMMSS-xxxxxx (6 hex chars)
        pattern = r"^p1-harness-\d{8}-\d{6}-[0-9a-f]{6}$"
        self.assertRegex(tid, pattern, f"trace_id '{tid}' does not match expected format")

    def test_trace_ids_are_unique(self):
        from run_p1_pipeline_harness import _trace_id

        ids = {_trace_id() for _ in range(20)}
        self.assertEqual(len(ids), 20, "trace_ids should be unique")


class TestTruncate(unittest.TestCase):
    """Verify response excerpt truncation."""

    def test_truncate_short_text(self):
        from run_p1_pipeline_harness import _truncate

        short = "hello"
        self.assertEqual(_truncate(short, 100), "hello")

    def test_truncate_long_text(self):
        from run_p1_pipeline_harness import _truncate

        long_text = "x" * 500
        result = _truncate(long_text, 300)
        self.assertLess(len(result), len(long_text))
        self.assertTrue(result.endswith("...(truncated)"))

    def test_truncate_default_max_len(self):
        from run_p1_pipeline_harness import _truncate

        long_text = "x" * 500
        result = _truncate(long_text)
        self.assertLessEqual(len(result), 350)  # 300 + "...(truncated)" ≈ 316


class TestStepResult(unittest.TestCase):
    """Verify StepResult data structure."""

    def test_pass_result(self):
        from run_p1_pipeline_harness import StepResult

        r = StepResult("health_check", "PASS", 200, key_ids={"phase": "P1-M21"})
        self.assertTrue(r.is_pass())
        self.assertEqual(r.status, "PASS")
        self.assertEqual(r.http_status, 200)
        self.assertEqual(r.key_ids["phase"], "P1-M21")

    def test_fail_result(self):
        from run_p1_pipeline_harness import StepResult

        r = StepResult("import", "FAIL", 500, message="Internal server error")
        self.assertFalse(r.is_pass())
        self.assertEqual(r.status, "FAIL")
        self.assertIn("Internal server error", r.message)

    def test_skip_result(self):
        from run_p1_pipeline_harness import StepResult

        r = StepResult("manual_cleaning", "SKIP", message="No batch_id")
        self.assertFalse(r.is_pass())
        self.assertEqual(r.status, "SKIP")


class TestSafeJsonDump(unittest.TestCase):
    """Verify safe JSON dump helper."""

    def test_dumps_dict(self):
        from run_p1_pipeline_harness import _safe_json_dump

        result = _safe_json_dump({"a": 1, "b": 2})
        self.assertIn("a", result)
        self.assertIn("1", result)

    def test_dumps_truncation(self):
        from run_p1_pipeline_harness import _safe_json_dump

        large = {"key": "x" * 1000}
        result = _safe_json_dump(large, max_len=100)
        self.assertLess(len(result), 200)


class TestSampleData(unittest.TestCase):
    """Verify inline sample data matches API schema expectations."""

    def test_import_payload_has_source_name(self):
        from run_p1_pipeline_harness import IMPORT_PAYLOAD

        self.assertIn("source_name", IMPORT_PAYLOAD)
        self.assertIsInstance(IMPORT_PAYLOAD["source_name"], str)
        self.assertTrue(len(IMPORT_PAYLOAD["source_name"]) > 0)

    def test_import_payload_has_conversations(self):
        from run_p1_pipeline_harness import IMPORT_PAYLOAD

        self.assertIn("conversations", IMPORT_PAYLOAD)
        self.assertIsInstance(IMPORT_PAYLOAD["conversations"], list)
        self.assertGreater(len(IMPORT_PAYLOAD["conversations"]), 0)

    def test_each_conversation_has_required_fields(self):
        from run_p1_pipeline_harness import IMPORT_PAYLOAD

        for conv in IMPORT_PAYLOAD["conversations"]:
            self.assertIn("conversation_id", conv)
            self.assertIn("messages", conv)
            self.assertIsInstance(conv["messages"], list)
            self.assertGreater(len(conv["messages"]), 0)

    def test_each_message_has_required_fields(self):
        from run_p1_pipeline_harness import IMPORT_PAYLOAD

        for conv in IMPORT_PAYLOAD["conversations"]:
            for msg in conv["messages"]:
                self.assertIn("message_id", msg)
                self.assertIn("role", msg)
                self.assertIn("content", msg)
                self.assertIn("timestamp", msg)
                self.assertIn(msg["role"], ("customer", "agent", "system", "unknown"))

    def test_covers_refund_intent(self):
        from run_p1_pipeline_harness import IMPORT_PAYLOAD

        all_text = json.dumps(IMPORT_PAYLOAD).lower()
        self.assertTrue(
            any(term in all_text for term in ["refund", "return"]),
            "Sample data should cover refund/return scenarios",
        )

    def test_covers_shipping_intent(self):
        from run_p1_pipeline_harness import IMPORT_PAYLOAD

        all_text = json.dumps(IMPORT_PAYLOAD).lower()
        self.assertTrue(
            any(term in all_text for term in ["shipping", "tracking", "order"]),
            "Sample data should cover shipping/tracking scenarios",
        )

    def test_covers_escalation_intent(self):
        from run_p1_pipeline_harness import IMPORT_PAYLOAD

        all_text = json.dumps(IMPORT_PAYLOAD).lower()
        self.assertTrue(
            any(term in all_text for term in ["human", "agent", "transfer"]),
            "Sample data should cover human escalation scenarios",
        )

    def test_has_low_quality_sample(self):
        from run_p1_pipeline_harness import IMPORT_PAYLOAD

        # conv_harness_004 should contain low-quality noise: "lol haha asdf" + "ok"
        all_text = json.dumps(IMPORT_PAYLOAD).lower()
        self.assertTrue(
            any(term in all_text for term in ["lol", "haha", "asdf"]),
            "Sample data should include at least one low-quality / noise message",
        )


class TestNowIso(unittest.TestCase):
    """Verify _now_iso returns valid ISO 8601."""

    def test_now_iso_format(self):
        from run_p1_pipeline_harness import _now_iso

        ts = _now_iso()
        # Should end with Z or +00:00
        self.assertTrue(ts.endswith("+00:00") or ts.endswith("Z") or "+" in ts)
        # Should be parseable
        self.assertIsInstance(ts, str)
        self.assertGreater(len(ts), 10)


class TestPgvectorCheckNoDbUrl(unittest.TestCase):
    """Verify pgvector check behaviour when DATABASE_URL is not set."""

    def setUp(self):
        self._saved = os.getenv("DATABASE_URL")
        if "DATABASE_URL" in os.environ:
            del os.environ["DATABASE_URL"]

    def tearDown(self):
        if self._saved:
            os.environ["DATABASE_URL"] = self._saved
        elif "DATABASE_URL" in os.environ:
            del os.environ["DATABASE_URL"]

    def test_check_skips_when_no_database_url(self):
        """When DATABASE_URL is unset, the check script should exit gracefully (code 0)."""
        # We run the script in a subprocess to test exit code
        import subprocess

        env = os.environ.copy()
        env.pop("DATABASE_URL", None)
        result = subprocess.run(
            [sys.executable, os.path.join(_scripts_dir, "check_pgvector_support.py")],
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertEqual(result.returncode, 0, f"Expected exit 0, got {result.returncode}\nstdout:\n{result.stdout}")
        self.assertIn("SKIP", result.stdout)
        self.assertIn("DATABASE_URL is not set", result.stdout)


class TestPipelineHarnessInit(unittest.TestCase):
    """Verify PipelineHarness initialization."""

    def test_default_base_url(self):
        from run_p1_pipeline_harness import PipelineHarness

        h = PipelineHarness("http://127.0.0.1:8000")
        self.assertEqual(h.base_url, "http://127.0.0.1:8000")
        self.assertEqual(h.timeout, 30)
        self.assertFalse(h.verbose)
        self.assertFalse(h.stop_on_fail)
        self.assertIsInstance(h.trace_id, str)
        self.assertTrue(h.trace_id.startswith("p1-harness-"))

    def test_custom_options(self):
        from run_p1_pipeline_harness import PipelineHarness

        h = PipelineHarness(
            "https://example.com:9000",
            timeout=10,
            verbose=True,
            stop_on_fail=True,
            trace_id="custom-123",
        )
        self.assertEqual(h.base_url, "https://example.com:9000")
        self.assertEqual(h.timeout, 10)
        self.assertTrue(h.verbose)
        self.assertTrue(h.stop_on_fail)
        self.assertEqual(h.trace_id, "custom-123")

    def test_url_trailing_slash(self):
        from run_p1_pipeline_harness import PipelineHarness

        h = PipelineHarness("http://127.0.0.1:8000/")
        self.assertEqual(h.base_url, "http://127.0.0.1:8000")


class TestSkipResult(unittest.TestCase):
    """Verify that SKIP cannot masquerade as PASS."""

    def test_skip_is_not_pass(self):
        from run_p1_pipeline_harness import StepResult

        skip = StepResult("step", "SKIP", message="reason")
        self.assertFalse(skip.is_pass())
        self.assertNotEqual(skip.status, "PASS")
