"""Non-invasive P1/P2 adapters for M8.2 branch orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
import time
from typing import Callable, Literal

from app.database import SessionLocal
from app.p2_retrieval_schemas import P2RetrievalRequest
from app.p2_retrieval_service import P2RetrievalFailure, P2RetrievalService
from app.schemas import CustomerOpsRetrievalRequest
from app.storage import run_customerops_retrieval


BranchSource = Literal["p1", "p2"]
BranchStatus = Literal["ok", "error", "timeout", "skipped"]


@dataclass(frozen=True)
class NormalizedCandidate:
    """Route-neutral evidence without comparing route-local scores."""

    source_index: BranchSource
    source_type: str
    original_rank: int
    original_score: float
    chunk_id: str
    evidence_text: str
    content_type: str
    candidate_id: str | None = None
    knowledge_asset_id: str | None = None
    asset_id: str | None = None
    source_trace: dict[str, object] = field(default_factory=dict)
    metadata: dict[str, object] = field(default_factory=dict)

    @property
    def evidence_id(self) -> str:
        if self.source_index == "p1":
            return self.candidate_id or self.chunk_id
        return self.knowledge_asset_id or self.chunk_id


@dataclass(frozen=True)
class BranchResult:
    source_index: BranchSource
    mode: str
    status: BranchStatus
    candidates: tuple[NormalizedCandidate, ...]
    latency_ms: float
    fallback_used: bool = False
    fallback_reason: str | None = None
    error_code: str | None = None
    error_type: str | None = None
    embedding_provider: str | None = None
    embedding_model: str | None = None
    embedding_dimension: int | None = None
    embedding_profile: str | None = None
    native_retrieval_id: str | None = None

    @property
    def result_count(self) -> int:
        return len(self.candidates)


def _safe_exception_type(exc: Exception) -> str:
    """Expose only a bounded class label, never an exception message."""

    label = re.sub(r"[^A-Za-z0-9_]", "", type(exc).__name__)[:80]
    return label or "RetrievalError"


class P1RetrievalAdapter:
    """Wrap the sealed CustomerOps retrieval function without changing it."""

    source_index: Literal["p1"] = "p1"

    def __init__(
        self,
        request_factory: Callable[[str, int], CustomerOpsRetrievalRequest]
        | None = None,
    ) -> None:
        # M8.2 uses the default factory. M8.3 may inject the versioned Agent
        # payload so conversation/session context is retained without changing
        # the sealed P1 request type or retrieval implementation.
        self.request_factory = request_factory

    def search(
        self,
        *,
        query: str,
        top_k: int,
        request_id: str | None = None,
    ) -> BranchResult:
        del request_id  # The sealed P1 request has no correlation-id field.
        started = time.perf_counter()
        try:
            payload = (
                self.request_factory(query, top_k)
                if self.request_factory is not None
                else CustomerOpsRetrievalRequest(query=query, top_k=top_k)
            )
            response = run_customerops_retrieval(payload, query, top_k)
            candidates = tuple(
                NormalizedCandidate(
                    source_index="p1",
                    source_type=item.source_type,
                    original_rank=rank,
                    original_score=float(item.score),
                    candidate_id=item.candidate_id,
                    chunk_id=item.chunk_id,
                    evidence_text=item.chunk_text,
                    content_type=item.knowledge_type,
                    source_trace={
                        "candidate_id": item.candidate_id,
                        "chunk_id": item.chunk_id,
                        "source_type": item.source_type,
                        "source_batch_id": item.source_batch_id,
                        "source_conversation_id": item.source_conversation_id,
                        "source_message_ids": item.source_message_ids,
                        "source_bad_case_id": item.source_bad_case_id,
                        "source_retrieval_id": item.source_retrieval_id,
                        "source_chunk_ids": item.source_chunk_ids,
                        "source_legacy_id": item.source_legacy_id,
                        "source_import_id": item.source_import_id,
                        "migration_mode": item.migration_mode,
                        "review_status": item.review_status,
                    },
                    metadata={
                        "intent": item.intent,
                        "tags": item.tags,
                        "risk_level": item.risk_level,
                        "quality_score": item.quality_score,
                        "build_method": item.build_method,
                        "matched_terms": item.matched_terms,
                        "answer": item.answer,
                        "provider_metadata_status": "not_exposed_by_sealed_p1_response",
                    },
                )
                for rank, item in enumerate(response.results, start=1)
            )
            return BranchResult(
                source_index="p1",
                mode=response.retrieval_mode,
                status="ok",
                candidates=candidates,
                latency_ms=round((time.perf_counter() - started) * 1000, 3),
                fallback_used=response.fallback_used,
                fallback_reason=response.fallback_reason,
                native_retrieval_id=response.retrieval_id,
            )
        except Exception as exc:
            return BranchResult(
                source_index="p1",
                mode="p1_branch_error",
                status="error",
                candidates=(),
                latency_ms=round((time.perf_counter() - started) * 1000, 3),
                fallback_used=False,
                fallback_reason="p1_branch_error",
                error_code="P1_BRANCH_ERROR",
                error_type=_safe_exception_type(exc),
            )


class P2RetrievalAdapter:
    """Own a short-lived P2 DB session and delegate to its governed service."""

    source_index: Literal["p2"] = "p2"

    def search(
        self,
        *,
        query: str,
        top_k: int,
        request_id: str | None = None,
    ) -> BranchResult:
        started = time.perf_counter()
        db = None
        try:
            db = SessionLocal()
            response = P2RetrievalService(db).search(
                P2RetrievalRequest(
                    query=query,
                    top_k=top_k,
                    debug=False,
                    request_id=request_id,
                )
            )
            candidates = tuple(
                NormalizedCandidate(
                    source_index="p2",
                    source_type="p2_knowledge_asset",
                    original_rank=item.rank,
                    original_score=float(item.score),
                    knowledge_asset_id=item.knowledge_asset_id,
                    chunk_id=item.chunk_id,
                    asset_id=item.asset_id,
                    evidence_text=item.chunk_text,
                    content_type=item.content_type,
                    source_trace=item.source_trace.model_dump(),
                    metadata={
                        **item.metadata,
                        "index_entry_id": item.index_entry_id,
                        "embedding_provider": response.embedding_provider,
                        "embedding_model": response.embedding_model,
                        "embedding_dimension": response.embedding_dimension,
                        "embedding_profile": response.embedding_profile,
                    },
                )
                for item in response.results
            )
            return BranchResult(
                source_index="p2",
                mode=response.retrieval_mode,
                status="ok",
                candidates=candidates,
                latency_ms=response.latency_ms,
                fallback_used=response.fallback_used,
                fallback_reason=response.fallback_reason,
                embedding_provider=response.embedding_provider,
                embedding_model=response.embedding_model,
                embedding_dimension=response.embedding_dimension,
                embedding_profile=response.embedding_profile,
                native_retrieval_id=response.retrieval_id,
            )
        except P2RetrievalFailure as exc:
            response = exc.response
            return BranchResult(
                source_index="p2",
                mode=response.retrieval_mode,
                status="error",
                candidates=(),
                latency_ms=response.latency_ms,
                fallback_used=False,
                fallback_reason=exc.reason,
                error_code=response.error_code or "P2_BRANCH_ERROR",
                error_type=_safe_exception_type(exc),
                embedding_provider=response.embedding_provider,
                embedding_model=response.embedding_model,
                embedding_dimension=response.embedding_dimension,
                embedding_profile=response.embedding_profile,
                native_retrieval_id=response.retrieval_id,
            )
        except Exception as exc:
            return BranchResult(
                source_index="p2",
                mode="p2_branch_error",
                status="error",
                candidates=(),
                latency_ms=round((time.perf_counter() - started) * 1000, 3),
                fallback_used=False,
                fallback_reason="p2_branch_error",
                error_code="P2_BRANCH_ERROR",
                error_type=_safe_exception_type(exc),
            )
        finally:
            if db is not None:
                db.close()
