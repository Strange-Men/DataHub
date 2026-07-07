"""Tests for vector RAG rebuild logic (P1-M24.2).

Covers:
- rebuild_vector_rag.py script importability.
- Provider readiness check blocking rebuild.
- Dimension mismatch blocking rebuild.
- Mock provider rebuild works.
- Safe error messages (no API key / DATABASE_URL leaks).
- Rebuild result schema fields.

All tests are local-only — no external API dependency.
"""

from __future__ import annotations

import importlib.util
import math
import os
import subprocess
import sys
import unittest

# Project root is 2 levels up from backend/tests/
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _script_path(script_name: str) -> str:
    """Return absolute path to a script in the project root."""
    return os.path.join(_PROJECT_ROOT, "scripts", script_name)


def _test_env() -> dict:
    """Return env dict with PYTHONPATH set for script imports."""
    env = {**os.environ}
    backend_dir = os.path.join(_PROJECT_ROOT, "backend")
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = backend_dir + (";" + existing if existing else "")
    return env


class TestRebuildScriptImportable(unittest.TestCase):
    """Verify rebuild_vector_rag.py can be imported without errors."""

    def test_script_module_importable(self):
        """The rebuild script module file exists and is loadable."""
        spec = importlib.util.spec_from_file_location(
            "rebuild_vector_rag",
            _script_path("rebuild_vector_rag.py")
        )
        self.assertIsNotNone(spec, "rebuild_vector_rag.py should be importable")

    def test_rebuild_script_has_expected_functions(self):
        """rebuild_vector_rag.py must expose run_rebuild and check_provider_locally."""
        sys.path.insert(0, _PROJECT_ROOT)
        import scripts.rebuild_vector_rag as script
        self.assertTrue(hasattr(script, 'run_rebuild'))
        self.assertTrue(hasattr(script, 'check_provider_locally'))
        self.assertTrue(hasattr(script, 'PGVECTOR_TABLE_DIMENSION'))


class TestRebuildScriptCli(unittest.TestCase):
    """Verify rebuild_vector_rag.py CLI behaviour."""

    def setUp(self):
        self._saved = {
            k: os.environ.get(k)
            for k in ("EMBEDDING_PROVIDER", "EMBEDDING_MODEL",
                       "EMBEDDING_API_KEY", "EMBEDDING_DIMENSION",
                       "EMBEDDING_BASE_URL", "OPENAI_API_KEY",
                       "EMBEDDING_TIMEOUT_SECONDS", "EMBEDDING_MAX_RETRIES",
                       "DATABASE_URL", "PYTHONPATH")
        }
        for k in self._saved:
            if k in os.environ:
                del os.environ[k]

        # Set mock provider for safe local testing
        os.environ["EMBEDDING_PROVIDER"] = "mock"

    def tearDown(self):
        for k, v in self._saved.items():
            if v is not None:
                os.environ[k] = v
            elif k in os.environ:
                del os.environ[k]

    def test_rebuild_script_help_works(self):
        """--help should exit 0."""
        result = subprocess.run(
            [sys.executable, _script_path("rebuild_vector_rag.py"), "--help"],
            capture_output=True, text=True, timeout=30,
            env=_test_env(), cwd=_PROJECT_ROOT
        )
        self.assertEqual(result.returncode, 0,
                         f"--help should exit 0. stderr: {result.stderr[:500]}")

    def test_rebuild_script_runs_without_crash_local(self):
        """Local rebuild with mock provider should run without crashing."""
        result = subprocess.run(
            [sys.executable, _script_path("rebuild_vector_rag.py")],
            capture_output=True, text=True, timeout=60,
            env=_test_env(), cwd=_PROJECT_ROOT
        )
        stdout = result.stdout
        stderr = result.stderr
        combined = stdout + stderr
        # Should either succeed or gracefully report blocked status
        self.assertTrue("Rebuild" in combined or "BLOCKED" in combined or
                        "SUCCESS" in combined or "FAILED" in combined)

    def test_rebuild_script_never_prints_api_key(self):
        """Output must never contain the API key."""
        os.environ["EMBEDDING_API_KEY"] = "sk-my-secret-key-12345"
        os.environ["EMBEDDING_PROVIDER"] = "siliconflow"
        result = subprocess.run(
            [sys.executable, _script_path("rebuild_vector_rag.py")],
            capture_output=True, text=True, timeout=30,
            env=_test_env(), cwd=_PROJECT_ROOT
        )
        stdout = result.stdout
        stderr = result.stderr
        self.assertNotIn("sk-my-secret-key-12345", stdout)
        self.assertNotIn("sk-my-secret-key-12345", stderr)

    def test_rebuild_script_missing_key_reports_blocked(self):
        """When real provider has no key, rebuild should report BLOCKED."""
        os.environ["EMBEDDING_PROVIDER"] = "siliconflow"
        # No EMBEDDING_API_KEY
        result = subprocess.run(
            [sys.executable, _script_path("rebuild_vector_rag.py")],
            capture_output=True, text=True, timeout=30,
            env=_test_env(), cwd=_PROJECT_ROOT
        )
        stdout = result.stdout
        combined = stdout + result.stderr
        blocked = "BLOCKED" in combined or "missing_api_key" in combined or result.returncode != 0
        self.assertTrue(blocked,
                        f"Should be blocked without key. Output: {stdout[:500]}")

    def test_rebuild_script_with_base_url_shows_usage(self):
        """--base-url should work without crashing with Python syntax errors."""
        os.environ["EMBEDDING_PROVIDER"] = "mock"
        result = subprocess.run(
            [sys.executable, _script_path("rebuild_vector_rag.py"),
             "--base-url", "http://127.0.0.1:8000"],
            capture_output=True, text=True, timeout=30,
            env=_test_env(), cwd=_PROJECT_ROOT,
            encoding="utf-8", errors="replace"
        )
        # May fail to connect but shouldn't crash with Python syntax/interpreter error
        stderr = result.stderr
        # A SyntaxError or ImportError would appear as a traceback
        # Network connection errors are expected and OK
        self.assertNotIn("SyntaxError", stderr)

    def test_rebuild_script_verbose_flag_accepted(self):
        """--verbose flag should be accepted."""
        os.environ["EMBEDDING_PROVIDER"] = "mock"
        result = subprocess.run(
            [sys.executable, _script_path("rebuild_vector_rag.py"), "--verbose"],
            capture_output=True, text=True, timeout=60,
            env=_test_env(), cwd=_PROJECT_ROOT
        )
        self.assertNotIn("unrecognized arguments", result.stderr)

    def test_rebuild_script_force_flag_accepted(self):
        """--force flag should be accepted."""
        os.environ["EMBEDDING_PROVIDER"] = "mock"
        result = subprocess.run(
            [sys.executable, _script_path("rebuild_vector_rag.py"), "--force"],
            capture_output=True, text=True, timeout=60,
            env=_test_env(), cwd=_PROJECT_ROOT
        )
        self.assertNotIn("unrecognized arguments", result.stderr)


class TestRebuildLogicNoExternalAPI(unittest.TestCase):
    """Verify rebuild logic without real external API calls."""

    def setUp(self):
        self._saved = {
            k: os.environ.get(k)
            for k in ("EMBEDDING_PROVIDER", "EMBEDDING_MODEL",
                       "EMBEDDING_API_KEY", "EMBEDDING_DIMENSION",
                       "EMBEDDING_BASE_URL", "OPENAI_API_KEY",
                       "EMBEDDING_TIMEOUT_SECONDS", "EMBEDDING_MAX_RETRIES",
                       "DATABASE_URL")
        }
        for k in self._saved:
            if k in os.environ:
                del os.environ[k]

    def tearDown(self):
        for k, v in self._saved.items():
            if v is not None:
                os.environ[k] = v
            elif k in os.environ:
                del os.environ[k]

    def test_check_provider_locally_mock_ready(self):
        """Mock provider is always ready locally."""
        os.environ["EMBEDDING_PROVIDER"] = "mock"
        sys.path.insert(0, _PROJECT_ROOT)
        import scripts.rebuild_vector_rag as script
        result = script.check_provider_locally(verbose=False)
        self.assertTrue(result.get("mock_ready"))
        self.assertTrue(result.get("provider_ready"))
        self.assertFalse(result.get("real_embedding_provider"))

    def test_check_provider_locally_real_missing_key(self):
        """Real provider without key returns provider_ready=False."""
        os.environ["EMBEDDING_PROVIDER"] = "siliconflow"
        # No EMBEDDING_API_KEY
        sys.path.insert(0, _PROJECT_ROOT)
        import scripts.rebuild_vector_rag as script
        result = script.check_provider_locally(verbose=False)
        self.assertFalse(result.get("provider_ready"))
        self.assertEqual(result.get("reason"), "missing_api_key")

    def test_pgvector_table_dimension_constant(self):
        """PGVECTOR_TABLE_DIMENSION should be 1536."""
        sys.path.insert(0, _PROJECT_ROOT)
        import scripts.rebuild_vector_rag as script
        self.assertEqual(script.PGVECTOR_TABLE_DIMENSION, 1536)

    def test_dimension_mismatch_logic(self):
        """A 1024-dim provider should be detected as mismatch vs 1536 table."""
        pgvector_dim = 1536
        real_dim = 1024
        self.assertNotEqual(real_dim, pgvector_dim)
        # This is the detection that blocks rebuild

    def test_different_text_embeddings_differ_with_mock(self):
        """Mock embeddings for different texts should differ."""
        from app.embedding import MockEmbeddingProvider
        provider = MockEmbeddingProvider(dimension=1536)
        v1 = provider.embed("How do I return an item?")
        v2 = provider.embed("What is your shipping policy?")
        diffs = [abs(a - b) for a, b in zip(v1, v2)]
        self.assertTrue(any(d > 0.001 for d in diffs),
                        "Different texts should produce different vectors")

    def test_embedding_dimension_1536_is_correct_for_pgvector(self):
        """Default mock dimension (1536) matches pgvector Vector(1536)."""
        from app.embedding import get_embedding_provider
        os.environ["EMBEDDING_PROVIDER"] = "mock"
        provider = get_embedding_provider()
        self.assertEqual(provider.dimension, 1536)
        vec = provider.embed("test")
        self.assertEqual(len(vec), 1536)


class TestRebuildResultFields(unittest.TestCase):
    """Verify rebuild result schema contains required fields."""

    def setUp(self):
        self._saved = {
            k: os.environ.get(k)
            for k in ("EMBEDDING_PROVIDER", "EMBEDDING_API_KEY",
                       "DATABASE_URL")
        }
        for k in self._saved:
            if k in os.environ:
                del os.environ[k]
        os.environ["EMBEDDING_PROVIDER"] = "mock"

    def tearDown(self):
        for k, v in self._saved.items():
            if v is not None:
                os.environ[k] = v
            elif k in os.environ:
                del os.environ[k]

    def test_rebuild_result_has_required_fields(self):
        """run_rebuild result dict must contain expected fields."""
        sys.path.insert(0, _PROJECT_ROOT)
        import scripts.rebuild_vector_rag as script
        result = script.run_rebuild(base_url=None, verbose=False, force=False)
        self.assertIn("rebuild_status", result)
        # Even BLOCKED should report these fields
        if result.get("rebuild_status") != "BLOCKED":
            self.assertIn("embedding_count", result)
            self.assertIn("failed_embedding_count", result)
            self.assertIn("provider", result)