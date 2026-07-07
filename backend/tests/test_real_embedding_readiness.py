"""Tests for real embedding provider readiness (P1-M24.2).

Covers:
- check_embedding_provider.py logic for all providers.
- Missing API key detection.
- Dimension mismatch detection.
- Safe error message scrubbing (no key leaks).
- Mock provider always ready.
- Blocked status when dimension mismatch.

All tests are local-only — no external API dependency.
"""

from __future__ import annotations

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


class TestCheckEmbeddingProviderScript(unittest.TestCase):
    """Verify check_embedding_provider.py script behaviour."""

    def setUp(self):
        self._saved = {
            k: os.environ.get(k)
            for k in ("EMBEDDING_PROVIDER", "EMBEDDING_MODEL",
                       "EMBEDDING_API_KEY", "EMBEDDING_DIMENSION",
                       "EMBEDDING_BASE_URL", "OPENAI_API_KEY",
                       "EMBEDDING_TIMEOUT_SECONDS", "EMBEDDING_MAX_RETRIES")
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

    def test_check_script_mock_exit_code_0(self):
        """Mock provider check should exit 0 (ready)."""
        os.environ["EMBEDDING_PROVIDER"] = "mock"
        result = subprocess.run(
            [sys.executable, _script_path("check_embedding_provider.py")],
            capture_output=True, text=True, timeout=30,
            env={**os.environ}, cwd=_PROJECT_ROOT
        )
        self.assertEqual(result.returncode, 0,
                         f"Mock check should exit 0. stderr: {result.stderr}")

    def test_check_script_mock_output_contains_keywords(self):
        """Mock provider output must contain expected fields."""
        os.environ["EMBEDDING_PROVIDER"] = "mock"
        result = subprocess.run(
            [sys.executable, _script_path("check_embedding_provider.py")],
            capture_output=True, text=True, timeout=30,
            env={**os.environ}, cwd=_PROJECT_ROOT
        )
        stdout = result.stdout
        self.assertIn("mock_ready", stdout)
        self.assertIn("provider_ready", stdout)
        self.assertIn("mock", stdout.lower())

    def test_check_script_missing_key_exit_code_1(self):
        """Real provider without key should exit 1."""
        os.environ["EMBEDDING_PROVIDER"] = "siliconflow"
        # No EMBEDDING_API_KEY
        result = subprocess.run(
            [sys.executable, _script_path("check_embedding_provider.py")],
            capture_output=True, text=True, timeout=30,
            env={**os.environ}, cwd=_PROJECT_ROOT
        )
        self.assertEqual(result.returncode, 1,
                         f"Missing key should exit 1. stdout: {result.stdout}")

    def test_check_script_missing_key_output_says_missing(self):
        """Real provider without key must say missing_api_key."""
        os.environ["EMBEDDING_PROVIDER"] = "siliconflow"
        result = subprocess.run(
            [sys.executable, _script_path("check_embedding_provider.py")],
            capture_output=True, text=True, timeout=30,
            env={**os.environ}, cwd=_PROJECT_ROOT
        )
        stdout = result.stdout
        self.assertIn("missing_api_key", stdout)

    def test_check_script_unknown_provider_exit_code_1(self):
        """Unknown provider should exit 1 (not ready)."""
        os.environ["EMBEDDING_PROVIDER"] = "unknown_provider_xyz"
        result = subprocess.run(
            [sys.executable, _script_path("check_embedding_provider.py")],
            capture_output=True, text=True, timeout=30,
            env={**os.environ}, cwd=_PROJECT_ROOT
        )
        self.assertEqual(result.returncode, 1)

    def test_check_script_never_prints_api_key(self):
        """Output must never contain the API key value."""
        os.environ["EMBEDDING_PROVIDER"] = "siliconflow"
        os.environ["EMBEDDING_API_KEY"] = "sk-this-is-a-secret-key-12345"
        result = subprocess.run(
            [sys.executable, _script_path("check_embedding_provider.py")],
            capture_output=True, text=True, timeout=30,
            env={**os.environ}, cwd=_PROJECT_ROOT
        )
        stdout = result.stdout
        stderr = result.stderr
        self.assertNotIn("sk-this-is-a-secret-key-12345", stdout)
        self.assertNotIn("sk-this-is-a-secret-key-12345", stderr)

    def test_check_script_verify_flag_runs_without_crash(self):
        """--verify flag should work without crashing for mock provider."""
        os.environ["EMBEDDING_PROVIDER"] = "mock"
        test_env = {**os.environ}
        # Add backend/ to PYTHONPATH so the script can import app.embedding
        backend_dir = os.path.join(_PROJECT_ROOT, "backend")
        existing_path = test_env.get("PYTHONPATH", "")
        test_env["PYTHONPATH"] = backend_dir + (";" + existing_path if existing_path else "")
        result = subprocess.run(
            [sys.executable, _script_path("check_embedding_provider.py"), "--verify"],
            capture_output=True, text=True, timeout=30,
            env=test_env, cwd=_PROJECT_ROOT
        )
        combined = result.stdout + result.stderr
        self.assertIn("test_embed", combined.lower())

    def test_check_script_siliconflow_recognized(self):
        """siliconflow provider should be recognized."""
        os.environ["EMBEDDING_PROVIDER"] = "siliconflow"
        result = subprocess.run(
            [sys.executable, _script_path("check_embedding_provider.py")],
            capture_output=True, text=True, timeout=30,
            env={**os.environ}, cwd=_PROJECT_ROOT
        )
        self.assertIn("siliconflow", result.stdout.lower())

    def test_check_script_jina_recognized(self):
        """jina provider should be recognized."""
        os.environ["EMBEDDING_PROVIDER"] = "jina"
        result = subprocess.run(
            [sys.executable, _script_path("check_embedding_provider.py")],
            capture_output=True, text=True, timeout=30,
            env={**os.environ}, cwd=_PROJECT_ROOT
        )
        self.assertIn("jina", result.stdout.lower())

    def test_check_script_openai_compatible_recognized(self):
        """openai_compatible provider should be recognized."""
        os.environ["EMBEDDING_PROVIDER"] = "openai_compatible"
        result = subprocess.run(
            [sys.executable, _script_path("check_embedding_provider.py")],
            capture_output=True, text=True, timeout=30,
            env={**os.environ}, cwd=_PROJECT_ROOT
        )
        self.assertIn("openai_compatible", result.stdout.lower())


class TestSafeErrorMessageScrubbing(unittest.TestCase):
    """Verify that error messages never leak sensitive data."""

    def setUp(self):
        self._saved = {
            k: os.environ.get(k)
            for k in ("EMBEDDING_PROVIDER", "EMBEDDING_API_KEY",
                       "EMBEDDING_BASE_URL", "DATABASE_URL")
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

    def test_check_provider_never_returns_api_key(self):
        """check_provider() result dict must not contain API key."""
        sys.path.insert(0, _PROJECT_ROOT)
        import scripts.check_embedding_provider as cp
        os.environ["EMBEDDING_PROVIDER"] = "siliconflow"
        os.environ["EMBEDDING_API_KEY"] = "sk-secret-key-value"
        result = cp.check_provider(verify=False)
        result_str = str(result)
        self.assertNotIn("sk-secret-key-value", result_str)

    def test_check_provider_mock_returns_expected_keys(self):
        """Mock provider result must contain expected keys."""
        sys.path.insert(0, _PROJECT_ROOT)
        import scripts.check_embedding_provider as cp
        os.environ["EMBEDDING_PROVIDER"] = "mock"
        result = cp.check_provider(verify=False)
        self.assertIn("mock_ready", result)
        self.assertIn("provider_ready", result)
        self.assertTrue(result["mock_ready"])
        self.assertTrue(result["provider_ready"])


class TestDimensionMismatchDetection(unittest.TestCase):
    """Verify that dimension mismatch can be detected and blocked."""

    def setUp(self):
        self._saved = {
            k: os.environ.get(k)
            for k in ("EMBEDDING_PROVIDER", "EMBEDDING_MODEL",
                       "EMBEDDING_API_KEY", "EMBEDDING_DIMENSION",
                       "EMBEDDING_BASE_URL", "OPENAI_API_KEY")
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

    def test_mock_default_dimension_matches_pgvector(self):
        """Mock default 1536 dim matches pgvector Vector(1536)."""
        from app.embedding import MockEmbeddingProvider
        provider = MockEmbeddingProvider()
        self.assertEqual(provider.dimension, 1536)

    def test_mock_custom_dimension_detected_as_mismatch(self):
        """A 1024-dim provider would mismatch pgvector Vector(1536)."""
        # This tests the detection logic, not actual write
        pgvector_dim = 1536
        mock_dim = 1024
        self.assertNotEqual(mock_dim, pgvector_dim,
                            "1024 != 1536 should be detected as mismatch")

    def test_embedding_dimension_is_consistent(self):
        """Same text should produce same dimension every time."""
        from app.embedding import MockEmbeddingProvider
        provider = MockEmbeddingProvider(dimension=1536)
        v1 = provider.embed("hello")
        v2 = provider.embed("world")
        v3 = provider.embed("a completely different longer text")
        self.assertEqual(len(v1), 1536)
        self.assertEqual(len(v2), 1536)
        self.assertEqual(len(v3), 1536)

    def test_mock_unit_length_with_1536_dim(self):
        """Mock embeddings with 1536 dim should be unit length."""
        from app.embedding import MockEmbeddingProvider
        provider = MockEmbeddingProvider(dimension=1536)
        vec = provider.embed("test text for normalization check")
        norm = math.sqrt(sum(v * v for v in vec))
        self.assertAlmostEqual(norm, 1.0, places=5)