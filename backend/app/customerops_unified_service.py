"""Explicit, default-off CustomerOpsAgent integration with Unified Retrieval."""

from __future__ import annotations

import os
import re
from typing import Iterable

from sqlalchemy.orm import Session

from app.customerops_unified_schemas import (
    CustomerOpsUnifiedEvidence,
    CustomerOpsUnifiedRetrievalRequest,
    CustomerOpsUnifiedRetrievalResponse,
)
from app.schemas import (
    CustomerOpsRetrievalRequest,
    CustomerOpsRetrievalResponse,
    CustomerOpsRetrievalResult,
)
from app.storage import run_customerops_retrieval
from app.unified_retrieval_schemas import (
    UnifiedRetrievalRequest,
    UnifiedRetrievalResponse,
    UnifiedRetrievalResult,
)
from app.unified_retrieval_adapters import P1RetrievalAdapter
from app.unified_retrieval_service import (
    UnifiedRetrievalFailure,
    UnifiedRetrievalFlags,
    UnifiedRetrievalService,
)


_TRUE_VALUES = {"1", "true", "yes", "on"}


def _enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in _TRUE_VALUES


def _safe_reason(value: str | None, default: str) -> str:
    normalized = re.sub(r"[^a-z0-9_:-]", "", (value or "").lower())[:160]
    return normalized or default


class CustomerOpsUnifiedFailure(RuntimeError):
    def __init__(self, *, reason: str, request_id: str | None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.request_id = request_id


def _legacy_request(payload: CustomerOpsUnifiedRetrievalRequest) -> CustomerOpsRetrievalRequest:
    return CustomerOpsRetrievalRequest(
        query=payload.query,
        top_k=payload.top_k,
        filters=payload.filters,
        conversation_id=payload.conversation_id,
        agent_session_id=payload.agent_session_id,
    )


def _p1_trace(item: CustomerOpsRetrievalResult) -> dict[str, object]:
    return {
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
    }


def _p1_evidence(
    results: Iterable[CustomerOpsRetrievalResult],
) -> list[CustomerOpsUnifiedEvidence]:
    evidence: list[CustomerOpsUnifiedEvidence] = []
    for rank, item in enumerate(results, start=1):
        evidence.append(
            CustomerOpsUnifiedEvidence(
                **item.model_dump(),
                source_index="p1",
                rank=rank,
                original_score=item.score,
                content_type=item.knowledge_type,
                source_trace=_p1_trace(item),
                metadata={
                    "intent": item.intent,
                    "tags": item.tags,
                    "risk_level": item.risk_level,
                    "quality_score": item.quality_score,
                },
            )
        )
    return evidence


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _unified_evidence(
    results: Iterable[UnifiedRetrievalResult],
) -> list[CustomerOpsUnifiedEvidence]:
    evidence: list[CustomerOpsUnifiedEvidence] = []
    for item in results:
        metadata = dict(item.metadata)
        compatibility_id = item.candidate_id or item.knowledge_asset_id or item.chunk_id
        score = item.fused_score if item.fused_score is not None else item.original_score
        evidence.append(
            CustomerOpsUnifiedEvidence(
                score=float(score),
                matched_terms=[],
                chunk_id=item.chunk_id,
                candidate_id=compatibility_id,
                source_type=item.source_type,
                source_batch_id=None,
                source_conversation_id=None,
                source_message_ids=[],
                source_chunk_ids=[item.chunk_id],
                knowledge_type=item.content_type,
                intent=str(metadata.get("intent", "general") or "general"),
                tags=_string_list(metadata.get("tags")),
                risk_level=str(metadata.get("risk_level", "medium") or "medium"),
                quality_score=float(metadata.get("quality_score", 1.0) or 1.0),
                chunk_text=item.evidence_text,
                build_method="unified_rrf_rank_fusion",
                answer=item.evidence_text,
                source_index=item.source_index,
                rank=item.rank,
                fused_score=item.fused_score,
                original_score=item.original_score,
                knowledge_asset_id=item.knowledge_asset_id,
                asset_id=item.asset_id,
                content_type=item.content_type,
                source_trace=dict(item.source_trace),
                metadata=metadata,
            )
        )
    return evidence


class CustomerOpsUnifiedRetrievalService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _run_p1(
        self,
        payload: CustomerOpsUnifiedRetrievalRequest,
        *,
        fallback_reason: str | None = None,
        unified_attempted: bool = False,
        unified_retrieval_id: str | None = None,
    ) -> CustomerOpsUnifiedRetrievalResponse:
        try:
            legacy_payload = _legacy_request(payload)
            legacy = run_customerops_retrieval(
                legacy_payload, payload.query, payload.top_k
            )
        except Exception as exc:
            raise CustomerOpsUnifiedFailure(
                reason=f"p1_retrieval_failed:{_safe_reason(type(exc).__name__, 'error')}",
                request_id=payload.request_id,
            ) from None

        opt_in_fallback = fallback_reason is not None
        return CustomerOpsUnifiedRetrievalResponse(
            retrieval_id=legacy.retrieval_id,
            query=legacy.query,
            top_k=legacy.top_k,
            retrieval_mode=legacy.retrieval_mode,
            results=_p1_evidence(legacy.results),
            fallback_used=opt_in_fallback or legacy.fallback_used,
            fallback_reason=(
                fallback_reason if opt_in_fallback else legacy.fallback_reason
            ),
            created_at=legacy.created_at,
            requested_retrieval_strategy=payload.retrieval_strategy,
            actual_retrieval_strategy="p1",
            unified_attempted=unified_attempted,
            unified_retrieval_id=unified_retrieval_id,
            legacy_retrieval_id=legacy.retrieval_id,
            legacy_retrieval_mode=legacy.retrieval_mode,
            legacy_fallback_used=legacy.fallback_used,
            legacy_fallback_reason=legacy.fallback_reason,
            request_id=payload.request_id,
        )

    def _gate_reason(
        self,
        payload: CustomerOpsUnifiedRetrievalRequest,
        flags: UnifiedRetrievalFlags,
    ) -> str | None:
        if not _enabled("CUSTOMEROPS_UNIFIED_RETRIEVAL_ENABLED"):
            return "customerops_unified_retrieval_disabled"
        if not flags.unified_enabled:
            return "unified_retrieval_disabled"
        if not flags.p2_enabled:
            return "p2_retrieval_disabled"
        if flags.shadow_enabled:
            return "unified_shadow_mode_active"
        if payload.filters is not None:
            return "unified_filters_not_supported"
        return None

    def retrieve(
        self, payload: CustomerOpsUnifiedRetrievalRequest
    ) -> CustomerOpsUnifiedRetrievalResponse:
        if payload.retrieval_strategy != "unified":
            return self._run_p1(payload)

        flags = UnifiedRetrievalFlags.from_environment()
        gate_reason = self._gate_reason(payload, flags)
        if gate_reason:
            return self._run_p1(payload, fallback_reason=gate_reason)

        unified_id: str | None = None
        try:
            legacy_template = _legacy_request(payload)
            payload_aware_p1 = P1RetrievalAdapter(
                request_factory=lambda query, top_k: legacy_template.model_copy(
                    update={"query": query, "top_k": top_k}
                )
            )
            unified = UnifiedRetrievalService(
                self.db,
                flags=flags,
                p1_adapter=payload_aware_p1,
            ).search(
                UnifiedRetrievalRequest(
                    query=payload.query,
                    top_k=payload.top_k,
                    sources=["p1", "p2"],
                    fusion_enabled=True,
                    shadow_mode=False,
                    include_archived=False,
                    debug=False,
                    request_id=payload.request_id,
                )
            )
            unified_id = unified.retrieval_id
        except UnifiedRetrievalFailure as exc:
            return self._run_p1(
                payload,
                fallback_reason=f"unified_retrieval_failed:{_safe_reason(exc.reason, 'error')}",
                unified_attempted=True,
                unified_retrieval_id=exc.retrieval_id,
            )
        except Exception as exc:
            return self._run_p1(
                payload,
                fallback_reason=f"unified_retrieval_failed:{_safe_reason(type(exc).__name__, 'error')}",
                unified_attempted=True,
            )

        if unified.candidate_mode != "unified_rrf":
            return self._run_p1(
                payload,
                fallback_reason=f"unified_retrieval_degraded:{_safe_reason(unified.candidate_mode, 'unknown')}",
                unified_attempted=True,
                unified_retrieval_id=unified_id,
            )
        return self._from_unified(payload, unified)

    def _from_unified(
        self,
        payload: CustomerOpsUnifiedRetrievalRequest,
        unified: UnifiedRetrievalResponse,
    ) -> CustomerOpsUnifiedRetrievalResponse:
        return CustomerOpsUnifiedRetrievalResponse(
            retrieval_id=unified.retrieval_id,
            query=unified.query,
            top_k=unified.top_k,
            retrieval_mode="customerops_unified_retrieval",
            results=_unified_evidence(unified.candidate_results),
            fallback_used=unified.fallback_used,
            fallback_reason=unified.fallback_reason,
            created_at=unified.created_at,
            requested_retrieval_strategy=payload.retrieval_strategy,
            actual_retrieval_strategy="unified",
            unified_attempted=True,
            unified_retrieval_id=unified.retrieval_id,
            source_modes=unified.source_modes,
            request_id=payload.request_id,
        )
