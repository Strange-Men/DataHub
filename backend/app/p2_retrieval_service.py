"""P2-M8.1 isolated semantic retrieval orchestration."""

from __future__ import annotations

from datetime import UTC, datetime
import os
import time
from uuid import uuid4

from sqlalchemy.orm import Session

from app import db_repositories
from app.answerability import (
    AnswerabilityConfig,
    AnswerabilityDecision,
    AnswerabilityEvidence,
    evaluate_answerability,
)
from app.embedding import EmbeddingProvider, get_embedding_provider
from app.knowledge_asset_repositories import KnowledgeSourceTraceError, get_knowledge_asset
from app.knowledge_embedding_service import (
    embedding_fingerprint,
    embedding_profile_for_provider,
)
from app.knowledge_index_repositories import KnowledgeIndexSourceTraceError, get_index_entry
from app.p2_retrieval_repositories import (
    P2PgvectorQueryError,
    P2PgvectorUnavailableError,
    P2ServingEmbeddingRow,
    list_serving_embedding_rows,
    search_serving_embeddings,
)
from app.p2_retrieval_schemas import (
    P2RetrievalRequest,
    P2RetrievalResponse,
    P2RetrievalResult,
)


class P2RetrievalFailure(RuntimeError):
    def __init__(
        self,
        *,
        reason: str,
        message: str,
        status_code: int,
        response: P2RetrievalResponse,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message
        self.status_code = status_code
        self.response = response


def _safe_trace_summary(result: P2RetrievalResult) -> dict[str, object]:
    trace = result.source_trace
    return {
        "chunk_id": result.chunk_id,
        "index_entry_id": result.index_entry_id,
        "knowledge_asset_id": result.knowledge_asset_id,
        "asset_id": result.asset_id,
        "snapshot_id": trace.snapshot_id,
        "review_id": trace.review_id,
        "extraction_id": trace.extraction_id,
    }


class P2RetrievalService:
    """Queries only governed P2 embeddings and never imports P1 RAG models."""

    def __init__(
        self,
        db: Session,
        provider: EmbeddingProvider | None = None,
    ) -> None:
        self.db = db
        self.provider = provider or get_embedding_provider()
        self.answerability_config = AnswerabilityConfig.from_environment()

    def _response(
        self,
        *,
        retrieval_id: str,
        payload: P2RetrievalRequest,
        created_at: str,
        started: float,
        results: list[P2RetrievalResult],
        fallback_reason: str | None,
        error_code: str | None = None,
        error_message: str | None = None,
        debug: dict[str, object] | None = None,
        answerability: AnswerabilityDecision | None = None,
    ) -> P2RetrievalResponse:
        return P2RetrievalResponse(
            retrieval_id=retrieval_id,
            query=payload.query.strip(),
            top_k=payload.top_k,
            matched_count=len(results),
            results=results,
            fallback_used=False,
            fallback_reason=fallback_reason,
            embedding_provider=self.provider.provider_name,
            embedding_model=self.provider.model_name,
            embedding_dimension=int(self.provider.dimension),
            embedding_profile=embedding_profile_for_provider(self.provider),
            latency_ms=round((time.perf_counter() - started) * 1000, 3),
            request_id=payload.request_id,
            evaluation_scope=payload.evaluation_scope,
            created_at=created_at,
            error_code=error_code,
            error_message=error_message,
            debug=debug if payload.debug else None,
            answerability=answerability,
        )

    def _log(self, response: P2RetrievalResponse) -> None:
        trace = {
            "retrieval_id": response.retrieval_id,
            "request_id": response.request_id,
            "evaluation_scope": response.evaluation_scope,
            "query": response.query,
            "retrieval_mode": response.retrieval_mode,
            "top_k": response.top_k,
            "result_count": response.matched_count,
            "result_chunk_ids": [item.chunk_id for item in response.results],
            "matched_knowledge_asset_ids": [
                item.knowledge_asset_id for item in response.results
            ],
            "matched_scores": [item.score for item in response.results],
            "embedding_provider": response.embedding_provider,
            "embedding_model": response.embedding_model,
            "embedding_dimension": response.embedding_dimension,
            "embedding_profile": response.embedding_profile,
            "latency_ms": response.latency_ms,
            "fallback_used": response.fallback_used,
            "fallback_reason": response.fallback_reason,
            "answerability": (
                response.answerability.model_dump(mode="json")
                if response.answerability
                else None
            ),
            "source_trace_summaries": [
                _safe_trace_summary(item) for item in response.results
            ],
            "created_at": response.created_at,
            "log_namespace": "p2_retrieval_v1",
        }
        try:
            db_repositories.save_retrieval_log_to_db(self.db, trace)
        except Exception:
            self.db.rollback()

    def _raise(
        self,
        *,
        reason: str,
        code: str,
        message: str,
        status_code: int,
        retrieval_id: str,
        payload: P2RetrievalRequest,
        created_at: str,
        started: float,
    ) -> None:
        response = self._response(
            retrieval_id=retrieval_id,
            payload=payload,
            created_at=created_at,
            started=started,
            results=[],
            fallback_reason=reason,
            error_code=code,
            error_message=message,
            answerability=evaluate_answerability(
                query=payload.query,
                evidence=[],
                scope="p2",
                config=self.answerability_config,
                retrieval_unavailable=True,
            ),
        )
        self._log(response)
        raise P2RetrievalFailure(
            reason=reason,
            message=message,
            status_code=status_code,
            response=response,
        )

    def _validate_row(
        self,
        row: P2ServingEmbeddingRow,
        *,
        profile: str,
        provider_name: str,
        model_name: str,
        dimension: int,
    ) -> object:
        try:
            entry = get_index_entry(self.db, row.index_entry_id)
        except KnowledgeIndexSourceTraceError as exc:
            raise ValueError("source_trace_invalid") from exc
        if entry is None:
            raise ValueError("source_trace_invalid")
        try:
            knowledge_asset = get_knowledge_asset(self.db, entry.knowledge_asset_id)
        except KnowledgeSourceTraceError as exc:
            raise ValueError("source_trace_invalid") from exc
        if (
            knowledge_asset is None
            or knowledge_asset.status != "active"
            or entry.status != "serving"
            or entry.sync_state != "ready"
            or entry.error_message
        ):
            raise ValueError("not_serving")
        chunk = next((item for item in entry.chunks if item.id == row.chunk_id), None)
        if chunk is None:
            raise ValueError("source_trace_invalid")
        if (
            row.embedding_profile != profile
            or row.provider != provider_name
            or row.model != model_name
        ):
            raise ValueError("embedding_profile_mismatch")
        if row.dimension != dimension:
            raise ValueError("embedding_dimension_mismatch")
        expected = embedding_fingerprint(
            chunk_id=chunk.id,
            chunk_hash=chunk.chunk_hash,
            chunk_text=chunk.chunk_text,
            generation=entry.generation,
            provider=self.provider,
            embedding_profile=profile,
        )
        metadata = row.embedding_metadata
        if (
            row.embedding_fingerprint != expected
            or metadata.get("index_fingerprint") != entry.fingerprint
            or metadata.get("chunk_hash") != chunk.chunk_hash
            or int(metadata.get("index_generation", -1)) != entry.generation
            or metadata.get("source_trace") != entry.source_trace.model_dump()
        ):
            raise ValueError("fingerprint_mismatch")
        return entry

    def search(self, payload: P2RetrievalRequest) -> P2RetrievalResponse:
        started = time.perf_counter()
        created_at = datetime.now(UTC).isoformat()
        retrieval_id = f"p2_retrieval_{uuid4().hex[:16]}"
        provider_name = self.provider.provider_name.strip()
        model_name = self.provider.model_name.strip()
        dimension = int(self.provider.dimension)
        profile = embedding_profile_for_provider(self.provider)

        serving_rows = list_serving_embedding_rows(
            self.db, evaluation_scope=payload.evaluation_scope
        )
        if not serving_rows:
            answerability = evaluate_answerability(
                query=payload.query,
                evidence=[],
                scope="p2",
                config=self.answerability_config,
            )
            response = self._response(
                retrieval_id=retrieval_id,
                payload=payload,
                created_at=created_at,
                started=started,
                results=[],
                fallback_reason="no_serving_index",
                answerability=answerability,
            )
            self._log(response)
            return response

        profile_rows = [row for row in serving_rows if row.embedding_profile == profile]
        if not profile_rows:
            same_model = [
                row
                for row in serving_rows
                if row.provider == provider_name and row.model == model_name
            ]
            reason = (
                "embedding_dimension_mismatch"
                if same_model and any(row.dimension != dimension for row in same_model)
                else "embedding_profile_mismatch"
            )
            self._raise(
                reason=reason,
                code=reason.upper(),
                message="The active P2 embedding profile is incompatible with serving data.",
                status_code=409,
                retrieval_id=retrieval_id,
                payload=payload,
                created_at=created_at,
                started=started,
            )

        for row in profile_rows:
            try:
                self._validate_row(
                    row,
                    profile=profile,
                    provider_name=provider_name,
                    model_name=model_name,
                    dimension=dimension,
                )
            except ValueError as exc:
                reason = str(exc)
                if reason == "not_serving":
                    reason = "source_trace_invalid"
                self._raise(
                    reason=reason,
                    code=reason.upper(),
                    message="P2 serving data failed governance validation.",
                    status_code=409,
                    retrieval_id=retrieval_id,
                    payload=payload,
                    created_at=created_at,
                    started=started,
                )

        try:
            query_embedding = self.provider.embed(payload.query.strip())
        except Exception:
            self._raise(
                reason="embedding_generation_failed",
                code="P2_QUERY_EMBEDDING_FAILED",
                message="P2 query embedding generation failed.",
                status_code=502,
                retrieval_id=retrieval_id,
                payload=payload,
                created_at=created_at,
                started=started,
            )
        if len(query_embedding) != dimension:
            self._raise(
                reason="embedding_dimension_mismatch",
                code="EMBEDDING_DIMENSION_MISMATCH",
                message=f"P2 query embedding dimension must be {dimension}.",
                status_code=409,
                retrieval_id=retrieval_id,
                payload=payload,
                created_at=created_at,
                started=started,
            )

        candidate_limit = min(max(payload.top_k * 4, 20), 50)
        try:
            minimum_score = float(os.getenv("P2_RETRIEVAL_MIN_SCORE", "0.45"))
        except ValueError:
            minimum_score = 0.45
        minimum_score = min(max(minimum_score, -1.0), 1.0)
        try:
            candidates = search_serving_embeddings(
                self.db,
                query_embedding=query_embedding,
                embedding_profile=profile,
                provider=provider_name,
                model=model_name,
                dimension=dimension,
                limit=candidate_limit,
                evaluation_scope=payload.evaluation_scope,
            )
        except P2PgvectorUnavailableError:
            self._raise(
                reason="pgvector_unavailable",
                code="P2_PGVECTOR_UNAVAILABLE",
                message="P2 pgvector retrieval is unavailable.",
                status_code=503,
                retrieval_id=retrieval_id,
                payload=payload,
                created_at=created_at,
                started=started,
            )
        except P2PgvectorQueryError:
            self._raise(
                reason="pgvector_query_error",
                code="P2_PGVECTOR_QUERY_ERROR",
                message="P2 vector query failed.",
                status_code=502,
                retrieval_id=retrieval_id,
                payload=payload,
                created_at=created_at,
                started=started,
            )

        results: list[P2RetrievalResult] = []
        decision_evidence: list[AnswerabilityEvidence] = []
        filtered_candidate_count = 0
        asset_counts: dict[str, int] = {}
        for candidate in candidates:
            try:
                entry = self._validate_row(
                    candidate,
                    profile=profile,
                    provider_name=provider_name,
                    model_name=model_name,
                    dimension=dimension,
                )
            except ValueError:
                filtered_candidate_count += 1
                continue
            metadata = candidate.chunk_metadata
            decision_evidence.append(
                AnswerabilityEvidence(
                    score=float(candidate.score or 0.0),
                    source="p2",
                    conflict_key=str(metadata.get("conflict_key") or "") or None,
                    claim_value=str(metadata.get("claim_value") or "") or None,
                )
            )
            if float(candidate.score or 0.0) < minimum_score:
                filtered_candidate_count += 1
                continue
            if asset_counts.get(candidate.asset_id, 0) >= 2:
                continue
            asset_counts[candidate.asset_id] = asset_counts.get(candidate.asset_id, 0) + 1
            result = P2RetrievalResult(
                rank=len(results) + 1,
                score=round(float(candidate.score or 0.0), 6),
                chunk_id=candidate.chunk_id,
                index_entry_id=candidate.index_entry_id,
                knowledge_asset_id=candidate.knowledge_asset_id,
                asset_id=candidate.asset_id,
                chunk_text=candidate.chunk_text,
                content_type=candidate.content_type,
                source_trace=entry.source_trace,
                metadata={
                    **candidate.chunk_metadata,
                    "embedding_profile": candidate.embedding_profile,
                    "embedding_fingerprint": candidate.embedding_fingerprint,
                },
            )
            results.append(result)
            if len(results) >= payload.top_k:
                break

        response = self._response(
            retrieval_id=retrieval_id,
            payload=payload,
            created_at=created_at,
            started=started,
            results=results,
            fallback_reason=None if results else "no_hits",
            answerability=evaluate_answerability(
                query=payload.query,
                evidence=decision_evidence,
                scope="p2",
                config=self.answerability_config,
                filtered_candidate_count=filtered_candidate_count,
            ),
            debug={
                "candidate_limit": candidate_limit,
                "serving_row_count": len(profile_rows),
                "asset_chunk_quota": 2,
                "minimum_score": minimum_score,
                "evaluation_scope": payload.evaluation_scope,
            },
        )
        self._log(response)
        return response
