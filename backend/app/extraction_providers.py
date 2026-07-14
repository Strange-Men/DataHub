"""Provider boundary for P2 extraction work.

P2-M2 intentionally ships only a deterministic mock. Real OCR, Caption,
Vision LLM, or metadata engines require later milestone approval.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.asset_schemas import AssetRecord


@dataclass(frozen=True)
class ExtractionContext:
    job_id: str
    extract_type: str
    asset: AssetRecord


@dataclass(frozen=True)
class ExtractionOutput:
    content: str
    metadata: dict[str, object] = field(default_factory=dict)


class ExtractionProviderError(RuntimeError):
    """A provider failure whose message is safe to persist and return."""


class ExtractionProvider(ABC):
    """Stable interface implemented by current and future extraction engines."""

    provider_name: str

    @abstractmethod
    def extract(self, context: ExtractionContext) -> ExtractionOutput:
        """Return normalized extraction output or raise ExtractionProviderError."""


class MockExtractionProvider(ExtractionProvider):
    """Deterministic pipeline fixture; it performs no AI or media analysis."""

    provider_name = "mock"

    def extract(self, context: ExtractionContext) -> ExtractionOutput:
        return ExtractionOutput(
            content=(
                f"[mock:{context.extract_type}] "
                f"foundation result for {context.asset.file_name}"
            ),
            metadata={
                "synthetic": True,
                "foundation_only": True,
                "source_asset_hash": context.asset.hash,
                "source_mime_type": context.asset.mime_type,
            },
        )


def get_extraction_provider(provider_name: str) -> ExtractionProvider:
    normalized = provider_name.strip().lower()
    if normalized == "mock":
        return MockExtractionProvider()
    raise ValueError("P2-M2 supports only the mock extraction provider.")
