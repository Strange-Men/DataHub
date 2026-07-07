"""Tests for the embedding provider abstraction (P1-M21, extended M24.2).

Covers:
- MockEmbeddingProvider determinism and dimension correctness.
- Default provider factory returns mock.
- Mock embedding stability across calls.
- Mock batch embedding correctness.
- No external API dependency.
- SiliconFlow / Jina / OpenAI-compatible provider factory routing.
- Missing API key safety.
- Dimension mismatch detection readiness.
"""

import math
import os
import unittest

from app.embedding import (
    EmbeddingProvider,
    MockEmbeddingProvider,
    OpenAIEmbeddingProvider,
    get_embedding_provider,
)


class TestMockEmbeddingProvider(unittest.TestCase):
    """Verify deterministic mock embedding behaviour."""

    def setUp(self):
        self.provider = MockEmbeddingProvider(dimension=64)

    def test_default_dimension_is_1536(self):
        p = MockEmbeddingProvider()
        self.assertEqual(p.dimension, 1536)

    def test_custom_dimension(self):
        p = MockEmbeddingProvider(dimension=32)
        self.assertEqual(p.dimension, 32)

    def test_embed_returns_correct_dimension(self):
        result = self.provider.embed("hello world")
        self.assertEqual(len(result), 64)

    def test_embed_is_deterministic(self):
        """Same text must produce the same embedding every time."""
        text = "How do I return an item?"
        result1 = self.provider.embed(text)
        result2 = self.provider.embed(text)
        for a, b in zip(result1, result2):
            self.assertAlmostEqual(a, b, places=10)

    def test_different_texts_produce_different_embeddings(self):
        """Different texts should produce different vectors."""
        emb1 = self.provider.embed("shipping to Germany")
        emb2 = self.provider.embed("refund policy for electronics")
        # At least one dimension should differ significantly
        diffs = [abs(a - b) for a, b in zip(emb1, emb2)]
        self.assertTrue(any(d > 0.001 for d in diffs),
                        "Different texts should produce different embeddings")

    def test_empty_text_returns_zero_vector(self):
        result = self.provider.embed("")
        self.assertEqual(len(result), 64)
        self.assertTrue(all(v == 0.0 for v in result))

    def test_embedding_is_unit_length(self):
        """Mock embeddings should be L2 normalized (approximately)."""
        texts = ["hello", "shipping", "refund request", "a longer piece of text with more words"]
        for text in texts:
            vec = self.provider.embed(text)
            norm = math.sqrt(sum(v * v for v in vec))
            self.assertAlmostEqual(norm, 1.0, places=5,
                                   msg=f"Embedding for '{text[:30]}' should be unit length, got {norm}")

    def test_embed_batch_returns_correct_count(self):
        texts = ["text one", "text two", "text three"]
        results = self.provider.embed_batch(texts)
        self.assertEqual(len(results), 3)
        for vec in results:
            self.assertEqual(len(vec), 64)

    def test_embed_batch_empty_list(self):
        results = self.provider.embed_batch([])
        self.assertEqual(len(results), 0)

    def test_provider_name_and_model(self):
        self.assertEqual(self.provider.provider_name, "mock")
        self.assertEqual(self.provider.model_name, "mock-deterministic")

    def test_dimension_32(self):
        p = MockEmbeddingProvider(dimension=32)
        vec = p.embed("test")
        self.assertEqual(len(vec), 32)
        self.assertTrue(all(isinstance(v, float) for v in vec))

    def test_dimension_128(self):
        p = MockEmbeddingProvider(dimension=128)
        vec = p.embed("test")
        self.assertEqual(len(vec), 128)


class TestEmbeddingProviderFactory(unittest.TestCase):
    """Verify get_embedding_provider factory behaviour."""

    def setUp(self):
        self._saved = {
            k: os.environ.get(k)
            for k in ("EMBEDDING_PROVIDER", "EMBEDDING_MODEL",
                       "EMBEDDING_API_KEY", "EMBEDDING_DIMENSION")
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

    def test_default_provider_is_mock(self):
        provider = get_embedding_provider()
        self.assertIsInstance(provider, MockEmbeddingProvider)
        self.assertEqual(provider.provider_name, "mock")

    def test_explicit_mock_provider(self):
        provider = get_embedding_provider(provider="mock")
        self.assertIsInstance(provider, MockEmbeddingProvider)

    def test_default_mock_dimension_is_1536(self):
        provider = get_embedding_provider(provider="mock")
        self.assertEqual(provider.dimension, 1536)

    def test_mock_with_custom_dimension(self):
        provider = get_embedding_provider(provider="mock", dimension=128)
        self.assertEqual(provider.dimension, 128)

    def test_env_var_provider_mock(self):
        os.environ["EMBEDDING_PROVIDER"] = "mock"
        provider = get_embedding_provider()
        self.assertIsInstance(provider, MockEmbeddingProvider)

    def test_env_var_dimension(self):
        os.environ["EMBEDDING_DIMENSION"] = "128"
        provider = get_embedding_provider(provider="mock")
        self.assertEqual(provider.dimension, 128)

    def test_unknown_provider_falls_back_to_mock(self):
        provider = get_embedding_provider(provider="unknown_provider_xyz")
        self.assertIsInstance(provider, MockEmbeddingProvider)

    def test_provider_returns_abstract_interface(self):
        provider = get_embedding_provider()
        self.assertIsInstance(provider, EmbeddingProvider)

    def test_factory_does_not_depend_on_api_key(self):
        """Factory must work without any API key set."""
        provider = get_embedding_provider()
        result = provider.embed("test query")
        self.assertEqual(len(result), provider.dimension)


class TestEmbeddingProviderInterface(unittest.TestCase):
    """Verify the abstract interface contract."""

    def test_mock_provider_satisfies_interface(self):
        p = MockEmbeddingProvider(dimension=32)
        self.assertIsInstance(p, EmbeddingProvider)
        self.assertEqual(p.dimension, 32)
        self.assertIsInstance(p.provider_name, str)
        self.assertIsInstance(p.model_name, str)
        vec = p.embed("test")
        self.assertIsInstance(vec, list)
        self.assertIsInstance(vec[0], float)
        batch = p.embed_batch(["a", "b"])
        self.assertEqual(len(batch), 2)


class TestRealEmbeddingProviderFactory(unittest.TestCase):
    """Verify factory behaviour for real (non-mock) providers."""

    def setUp(self):
        self._saved = {
            k: os.environ.get(k)
            for k in ("EMBEDDING_PROVIDER", "EMBEDDING_MODEL",
                       "EMBEDDING_API_KEY", "EMBEDDING_DIMENSION",
                       "EMBEDDING_BASE_URL", "EMBEDDING_TIMEOUT_SECONDS",
                       "EMBEDDING_MAX_RETRIES", "OPENAI_API_KEY",
                       "OPENAI_BASE_URL")
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

    def test_siliconflow_provider_recognized(self):
        """siliconflow maps to OpenAIEmbeddingProvider."""
        os.environ["EMBEDDING_PROVIDER"] = "siliconflow"
        os.environ["EMBEDDING_API_KEY"] = "test-key"
        os.environ["EMBEDDING_BASE_URL"] = "https://api.siliconflow.com/v1"
        provider = get_embedding_provider()
        self.assertIsInstance(provider, OpenAIEmbeddingProvider)
        self.assertEqual(provider.provider_name, "openai")

    def test_jina_provider_recognized(self):
        """jina maps to OpenAIEmbeddingProvider."""
        os.environ["EMBEDDING_PROVIDER"] = "jina"
        os.environ["EMBEDDING_API_KEY"] = "test-key"
        os.environ["EMBEDDING_BASE_URL"] = "https://api.jina.ai/v1"
        provider = get_embedding_provider()
        self.assertIsInstance(provider, OpenAIEmbeddingProvider)
        self.assertEqual(provider.provider_name, "openai")

    def test_openai_compatible_provider_recognized(self):
        """openai_compatible maps to OpenAIEmbeddingProvider."""
        os.environ["EMBEDDING_PROVIDER"] = "openai_compatible"
        os.environ["EMBEDDING_API_KEY"] = "test-key"
        os.environ["EMBEDDING_BASE_URL"] = "https://custom.api.com/v1"
        provider = get_embedding_provider()
        self.assertIsInstance(provider, OpenAIEmbeddingProvider)

    def test_openai_provider_recognized(self):
        """openai maps to OpenAIEmbeddingProvider."""
        os.environ["EMBEDDING_PROVIDER"] = "openai"
        os.environ["EMBEDDING_API_KEY"] = "test-key"
        provider = get_embedding_provider()
        self.assertIsInstance(provider, OpenAIEmbeddingProvider)

    def test_real_provider_missing_key_does_not_crash_factory(self):
        """Factory must return a provider even if API key is missing."""
        for prov in ("openai", "siliconflow", "jina", "openai_compatible"):
            os.environ["EMBEDDING_PROVIDER"] = prov
            # No API key set
            provider = get_embedding_provider()
            self.assertIsInstance(provider, EmbeddingProvider,
                                  f"Provider {prov} should be created without key")
            self.assertTrue(provider.provider_name in ("openai", "mock"),
                            f"Provider {prov} has name: {provider.provider_name}")

    def test_real_provider_missing_key_embed_raises(self):
        """Embedding with real provider without API key should raise ValueError."""
        os.environ["EMBEDDING_PROVIDER"] = "siliconflow"
        # No API key
        provider = get_embedding_provider()
        if provider.provider_name == "openai":
            with self.assertRaises(ValueError):
                provider.embed("test text")

    def test_env_base_url_passed_to_provider(self):
        """EMBEDDING_BASE_URL should be passed through."""
        os.environ["EMBEDDING_PROVIDER"] = "siliconflow"
        os.environ["EMBEDDING_API_KEY"] = "test-key"
        os.environ["EMBEDDING_BASE_URL"] = "https://api.siliconflow.com/v1"
        provider = get_embedding_provider()
        self.assertEqual(provider._base_url, "https://api.siliconflow.com/v1")

    def test_env_timeout_and_retries_read(self):
        """EMBEDDING_TIMEOUT_SECONDS and EMBEDDING_MAX_RETRIES should be read."""
        os.environ["EMBEDDING_PROVIDER"] = "siliconflow"
        os.environ["EMBEDDING_API_KEY"] = "test-key"
        os.environ["EMBEDDING_TIMEOUT_SECONDS"] = "45"
        os.environ["EMBEDDING_MAX_RETRIES"] = "5"
        provider = get_embedding_provider()
        self.assertEqual(provider._timeout, 45.0)
        self.assertEqual(provider._max_retries, 5)

    def test_provider_name_never_exposes_key(self):
        """Provider_name and model_name must not contain API keys."""
        os.environ["EMBEDDING_PROVIDER"] = "siliconflow"
        os.environ["EMBEDDING_API_KEY"] = "sk-secret-key-12345"
        provider = get_embedding_provider()
        self.assertNotIn("sk-secret", provider.provider_name)
        self.assertNotIn("sk-secret", provider.model_name)

    def test_mock_provider_still_works_with_all_env_set(self):
        """Mock provider must work even when env has real provider config."""
        os.environ["EMBEDDING_PROVIDER"] = "mock"
        os.environ["EMBEDDING_API_KEY"] = "some-key"
        os.environ["EMBEDDING_BASE_URL"] = "https://example.com"
        provider = get_embedding_provider()
        self.assertIsInstance(provider, MockEmbeddingProvider)
        vec = provider.embed("test")
        self.assertEqual(len(vec), 1536)

    def test_mock_fallback_on_unknown_provider(self):
        """Unknown provider should fallback to mock without crash."""
        os.environ["EMBEDDING_PROVIDER"] = "deepseek"
        provider = get_embedding_provider()
        # DeepSeek is LLM only, not embedding — should fallback to mock
        self.assertIsInstance(provider, MockEmbeddingProvider)


class TestRealEmbeddingReadinessNoExternalAPI(unittest.TestCase):
    """Verify readiness checks without real external API calls."""

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

    def test_mock_is_always_ready(self):
        """Mock provider is always ready, no API key needed."""
        os.environ["EMBEDDING_PROVIDER"] = "mock"
        provider = get_embedding_provider()
        vec = provider.embed("test")
        self.assertEqual(len(vec), 1536)
        self.assertEqual(provider.provider_name, "mock")

    def test_missing_key_detected(self):
        """When real provider set but no key, this should be detectable."""
        os.environ["EMBEDDING_PROVIDER"] = "siliconflow"
        # No EMBEDDING_API_KEY set
        api_key = os.getenv("EMBEDDING_API_KEY", "").strip()
        self.assertEqual(api_key, "")
        # Factory should still work but provider.embed() will raise ValueError
        provider = get_embedding_provider()
        if provider.provider_name == "openai":
            with self.assertRaises(ValueError):
                provider.embed("test")

    def test_dimension_mismatch_can_be_detected(self):
        """We can compare provider dimension vs expected table dimension."""
        expected_table_dim = 1536
        # Mock provider with 1024 dim would mismatch
        provider = MockEmbeddingProvider(dimension=1024)
        vec = provider.embed("test")
        actual_dim = len(vec)
        self.assertEqual(actual_dim, 1024)
        self.assertNotEqual(actual_dim, expected_table_dim)
        # This mismatch should be flagged in rebuild scripts

    def test_default_mock_dimension_matches_table(self):
        """Default mock 1536 dim should match pgvector Vector(1536)."""
        provider = MockEmbeddingProvider()  # default 1536
        self.assertEqual(provider.dimension, 1536)
        vec = provider.embed("test")
        self.assertEqual(len(vec), 1536)

    def test_openai_provider_default_dimension(self):
        """OpenAIEmbeddingProvider default dimension is 1536."""
        os.environ["EMBEDDING_API_KEY"] = "test-key"
        provider = OpenAIEmbeddingProvider(api_key="test-key")
        self.assertEqual(provider.dimension, 1536)
