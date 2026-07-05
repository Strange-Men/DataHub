"""Embedding provider abstraction for DataHub P1-M21 Vector RAG Foundation.

Supports:
- deterministic mock embedding (for local tests, no external API needed)
- real embedding provider interface (reserved for online use)

Configuration (environment variables):
- EMBEDDING_PROVIDER  — default "mock"
- EMBEDDING_MODEL     — default "mock-deterministic"
- EMBEDDING_API_KEY   — optional, for real providers
- EMBEDDING_DIMENSION — optional, default 64

Never logs or exposes API keys.
"""

from __future__ import annotations

import hashlib
import os
import struct
from abc import ABC, abstractmethod
from typing import Optional


# ── Abstract base ────────────────────────────────────────────────────────────


class EmbeddingProvider(ABC):
    """Abstract embedding provider.

    Subclasses must implement embed() and embed_batch().
    """

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """Return the embedding vector for a single text."""
        ...

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Return embeddings for a batch of texts."""
        ...

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Return the embedding vector dimension."""
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return a human-readable provider name."""
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the model name."""
        ...


# ── Deterministic mock embedding ─────────────────────────────────────────────


class MockEmbeddingProvider(EmbeddingProvider):
    """Deterministic mock embedding provider for local testing.

    Generates stable, fixed-dimension embeddings from text content.
    Same text always produces the same vector — useful for reproducible tests.

    Does NOT depend on any external API or network.
    Uses SHA-256 hash of the input text to seed a deterministic
    pseudo-random projection onto the unit hypersphere.
    """

    def __init__(self, dimension: int = 64) -> None:
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def model_name(self) -> str:
        return "mock-deterministic"

    def embed(self, text: str) -> list[float]:
        """Return a deterministic mock embedding for the given text.

        The algorithm:
        1. Hash the UTF-8 bytes of `text` with SHA-256.
        2. Use chunks of the hash as seeds for a simple pseudo-random sequence.
        3. Normalize the resulting vector to unit length (cosine-ready).

        Same text → same vector, every time.
        """
        if not text:
            # Empty text gets a zero vector
            return [0.0] * self._dimension

        hash_bytes = hashlib.sha256(text.encode("utf-8")).digest()

        # Generate `dimension` float values from the hash bytes
        values = []
        for i in range(self._dimension):
            # Use 4 bytes of the hash (cycling) to create a float in [-1, 1]
            byte_idx = (i * 4) % len(hash_bytes)
            chunk = hash_bytes[byte_idx:byte_idx + 4]
            if len(chunk) < 4:
                chunk = chunk + hash_bytes[:4 - len(chunk)]
            # Interpret 4 bytes as a signed 32-bit integer
            raw = struct.unpack(">i", chunk)[0]
            # Normalize to [-1, 1]
            normalized = raw / 2147483648.0  # 2^31
            values.append(normalized)

        # L2 normalize to unit vector
        norm_sq = sum(v * v for v in values)
        if norm_sq > 0:
            norm = norm_sq ** 0.5
            values = [v / norm for v in values]

        return values

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Return deterministic mock embeddings for a batch of texts."""
        return [self.embed(t) for t in texts]


# ── Real embedding provider (reserved interface) ─────────────────────────────


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """OpenAI-compatible embedding provider.

    Uses OPENAI_API_KEY or EMBEDDING_API_KEY from environment.
    Supports text-embedding-3-small, text-embedding-3-large, etc.

    Not required for M21 — kept as a reserved interface for M22+.
    When used, requires the `openai` Python package.
    """

    def __init__(
        self,
        model: str = "text-embedding-3-small",
        api_key: str | None = None,
        dimension: int | None = None,
        timeout: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        self._model = model
        self._api_key = api_key or os.getenv("EMBEDDING_API_KEY") or os.getenv("OPENAI_API_KEY", "")
        self._dimension = dimension or 1536
        self._timeout = timeout
        self._max_retries = max_retries

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def provider_name(self) -> str:
        return "openai"

    @property
    def model_name(self) -> str:
        return self._model

    def embed(self, text: str) -> list[float]:
        """Return embedding via OpenAI-compatible API.

        Raises ValueError if API key is not configured.
        Raises RuntimeError after exhausting retries.
        """
        if not self._api_key:
            raise ValueError(
                "OpenAI API key is not configured. "
                "Set EMBEDDING_API_KEY or OPENAI_API_KEY in the environment."
            )
        # Use openai package if available
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError(
                "The 'openai' package is required for OpenAIEmbeddingProvider. "
                "Install it with: pip install openai"
            )

        client = OpenAI(api_key=self._api_key, timeout=self._timeout)
        last_exc: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                response = client.embeddings.create(
                    model=self._model,
                    input=text,
                )
                return list(response.data[0].embedding)
            except Exception as exc:
                last_exc = exc
                if attempt < self._max_retries:
                    import time
                    time.sleep(min(2 ** attempt, 10))

        raise RuntimeError(
            f"OpenAI embedding failed after {self._max_retries} retries. "
            f"Last error: {last_exc}"
        )

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Return embeddings for a batch via OpenAI-compatible API."""
        if not texts:
            return []
        if not self._api_key:
            raise ValueError(
                "OpenAI API key is not configured. "
                "Set EMBEDDING_API_KEY or OPENAI_API_KEY in the environment."
            )
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError(
                "The 'openai' package is required for OpenAIEmbeddingProvider. "
                "Install it with: pip install openai"
            )

        client = OpenAI(api_key=self._api_key, timeout=self._timeout)
        last_exc: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                response = client.embeddings.create(
                    model=self._model,
                    input=texts,
                )
                return [list(d.embedding) for d in response.data]
            except Exception as exc:
                last_exc = exc
                if attempt < self._max_retries:
                    import time
                    time.sleep(min(2 ** attempt, 10))

        raise RuntimeError(
            f"OpenAI batch embedding failed after {self._max_retries} retries. "
            f"Last error: {last_exc}"
        )


# ── Provider factory ─────────────────────────────────────────────────────────


def get_embedding_provider(
    provider: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    dimension: int | None = None,
) -> EmbeddingProvider:
    """Return an embedding provider based on configuration.

    Reads from environment variables (with explicit-arg override):
    - EMBEDDING_PROVIDER  → provider
    - EMBEDDING_MODEL     → model
    - EMBEDDING_API_KEY   → api_key
    - EMBEDDING_DIMENSION → dimension

    Default: MockEmbeddingProvider(dimension=64).
    """
    provider = provider or os.getenv("EMBEDDING_PROVIDER", "mock").strip().lower()
    model = model or os.getenv("EMBEDDING_MODEL", "mock-deterministic").strip()
    api_key = api_key or os.getenv("EMBEDDING_API_KEY", "").strip() or None

    if dimension is None:
        dim_str = os.getenv("EMBEDDING_DIMENSION", "").strip()
        if dim_str:
            try:
                dimension = int(dim_str)
            except ValueError:
                dimension = None

    if provider == "mock":
        dim = dimension or 64
        return MockEmbeddingProvider(dimension=dim)

    if provider == "openai":
        model = model or "text-embedding-3-small"
        dim = dimension or 1536
        return OpenAIEmbeddingProvider(
            model=model,
            api_key=api_key,
            dimension=dim,
        )

    # Unknown provider — fall back to mock with a warning
    import warnings
    warnings.warn(
        f"Unknown embedding provider '{provider}'. Falling back to mock. "
        f"Set EMBEDDING_PROVIDER to 'mock' or 'openai'."
    )
    return MockEmbeddingProvider(dimension=dimension or 64)
