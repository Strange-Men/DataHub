"""Embedding provider abstraction for DataHub P1-M21 Vector RAG Foundation.

Supports:
- deterministic mock embedding (for local tests, no external API needed)
- real embedding provider interface (reserved for online use)

Configuration (environment variables):
- EMBEDDING_PROVIDER  — default "mock"
- EMBEDDING_MODEL     — default "mock-deterministic"
- EMBEDDING_API_KEY   — optional, for real providers
- EMBEDDING_DIMENSION — optional, default 1536

Never logs or exposes API keys.
"""

from __future__ import annotations

import hashlib
import os
import re
import struct
from abc import ABC, abstractmethod
from typing import Any


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

    P1-M23.1: Uses a bag-of-words token-based approach.
    Each alphanumeric token is independently hashed to a deterministic
    vector; the text's embedding is the sum of all token vectors,
    L2-normalized.  This gives:
      - same text → same vector (deterministic, testable)
      - texts sharing words → non-zero cosine similarity (keyword-aware)
      - texts with no shared words → near-zero cosine similarity

    This is NOT a semantic embedding — it only captures lexical overlap.
    Real semantic retrieval requires a real embedding provider (OpenAI, etc.).
    """

    def __init__(self, dimension: int = 1536) -> None:
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

    def _token_vector(self, token: str) -> list[float]:
        """Generate a deterministic unit vector for a single token."""
        hash_bytes = hashlib.sha256(token.encode("utf-8")).digest()
        values = []
        for i in range(self._dimension):
            byte_idx = (i * 4) % len(hash_bytes)
            chunk = hash_bytes[byte_idx:byte_idx + 4]
            if len(chunk) < 4:
                chunk = chunk + hash_bytes[:4 - len(chunk)]
            raw = struct.unpack(">i", chunk)[0]
            values.append(raw / 2147483648.0)
        # L2 normalize token vector
        norm_sq = sum(v * v for v in values)
        if norm_sq > 0:
            norm = norm_sq ** 0.5
            values = [v / norm for v in values]
        return values

    def embed(self, text: str) -> list[float]:
        """Return a deterministic, keyword-aware mock embedding.

        Algorithm (P1-M23.1):
        1. Tokenize text into lowercase alphanumeric words.
        2. Generate a deterministic unit vector for each unique token.
        3. Sum all token vectors (bag-of-words).
        4. L2-normalize the sum to unit length.

        Same text → same vector.
        Texts sharing words → non-zero cosine similarity.
        """
        if not text:
            return [0.0] * self._dimension

        # Tokenize: extract alphanumeric word tokens, lowercase, deduplicate
        tokens = list(set(re.findall(r"[a-zA-Z0-9]+", text.lower())))
        if not tokens:
            return [0.0] * self._dimension

        # Sum token vectors
        values = [0.0] * self._dimension
        for token in tokens:
            tv = self._token_vector(token)
            for i in range(self._dimension):
                values[i] += tv[i]

        # L2 normalize the summed vector
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
        base_url: str | None = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        provider_name: str = "openai",
    ) -> None:
        self._model = model
        self._api_key = api_key or os.getenv("EMBEDDING_API_KEY") or os.getenv("OPENAI_API_KEY", "")
        self._dimension = dimension or 1536
        self._base_url = base_url or os.getenv("EMBEDDING_BASE_URL") or os.getenv("OPENAI_BASE_URL", "")
        self._timeout = timeout
        self._max_retries = max_retries
        self._provider_name = provider_name

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def provider_name(self) -> str:
        return self._provider_name

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

        client_kwargs: dict[str, Any] = {"api_key": self._api_key, "timeout": self._timeout}
        if self._base_url:
            client_kwargs["base_url"] = self._base_url
        client = OpenAI(**client_kwargs)
        last_exc: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                response = client.embeddings.create(
                    model=self._model,
                    input=text,
                    dimensions=self._dimension,
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

        client_kwargs: dict[str, Any] = {"api_key": self._api_key, "timeout": self._timeout}
        if self._base_url:
            client_kwargs["base_url"] = self._base_url
        client = OpenAI(**client_kwargs)
        last_exc: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                response = client.embeddings.create(
                    model=self._model,
                    input=texts,
                    dimensions=self._dimension,
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

    Default: MockEmbeddingProvider(dimension=1536).
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
        dim = dimension or 1536
        return MockEmbeddingProvider(dimension=dim)

    if provider in ("openai", "openai_compatible", "siliconflow", "jina"):
        # All these providers use OpenAI-compatible API.
        # SiliconFlow base URL: https://api.siliconflow.com/v1
        # Jina base URL: https://api.jina.ai/v1
        # DeepSeek is NOT an embedding provider — only for LLM answer generation.
        model = model or "text-embedding-3-small"
        dim = dimension or 1536
        base_url = os.getenv("EMBEDDING_BASE_URL", "").strip() or os.getenv("OPENAI_BASE_URL", "").strip() or None
        timeout = float(os.getenv("EMBEDDING_TIMEOUT_SECONDS", "30").strip())
        max_retries = int(os.getenv("EMBEDDING_MAX_RETRIES", "3").strip())
        return OpenAIEmbeddingProvider(
            model=model,
            api_key=api_key,
            dimension=dim,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            provider_name=provider,
        )

    # Unknown provider — fall back to mock with a warning
    import warnings
    warnings.warn(
        f"Unknown embedding provider '{provider}'. Falling back to mock. "
        f"Set EMBEDDING_PROVIDER to 'mock', 'openai', 'openai_compatible', 'siliconflow', or 'jina'."
    )
    return MockEmbeddingProvider(dimension=dimension or 1536)
