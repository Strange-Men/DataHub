"""Tests for the embedding provider abstraction (P1-M21).

Covers:
- MockEmbeddingProvider determinism and dimension correctness.
- Default provider factory returns mock.
- Mock embedding stability across calls.
- Mock batch embedding correctness.
- No external API dependency.
"""

import math
import os
import unittest

from app.embedding import (
    EmbeddingProvider,
    MockEmbeddingProvider,
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
