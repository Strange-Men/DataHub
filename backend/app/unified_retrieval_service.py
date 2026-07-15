"""P2-M8.2 logical dual-index retrieval and non-impacting shadow fusion."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import UTC, datetime
import os
import re
import threading
import time
from typing import Callable, Iterable
from uuid import uuid4

from sqlalchemy.orm import Session

from app import db_repositories
from app.database import SessionLocal
from app.knowledge_asset_repositories import (
    KnowledgeSourceTraceError,
    get_knowledge_asset,
)
from app.knowledge_index_repositories import (
    KnowledgeIndexSourceTraceError,
    get_index_entry,
)
from app.p2_retrieval_repositories import list_serving_embedding_rows
from app.unified_retrieval_adapters import (
    BranchResult,
    NormalizedCandidate,
    P1RetrievalAdapter,
    P2RetrievalAdapter,
)
from app.unified_retrieval_schemas import (
    UnifiedRetrievalLatency,
    UnifiedRetrievalRequest,
    UnifiedRetrievalResponse,
    UnifiedRetrievalResult,
    UnifiedRetrievalShadowComparison,
    UnifiedRetrievalSourceMode,
)


_TRUE_VALUES = {"1", "true", "yes", "on"}
_BRANCH_EXECUTOR = ThreadPoolExecutor(
    max_workers=8, thread_name_prefix="unified-retrieval"
)
_BRANCH_SLOTS = threading.BoundedSemaphore(16)


def _env_enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in _TRUE_VALUES


def _bounded_float(name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return min(max(value, minimum), maximum)


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return min(max(value, minimum), maximum)


@dataclass(frozen=True)
class UnifiedRetrievalFlags:
    unified_enabled: bool = False
    p2_enabled: bool = False
    shadow_enabled: bool = False
    branch_timeout_seconds: float = 8.0
    rrf_rank_constant: int = 60
    p2_asset_chunk_quota: int = 2

    @classmethod
    def from_environment(cls) -> "UnifiedRetrievalFlags":
        return cls(
            unified_enabled=_env_enabled("UNIFIED_RETRIEVAL_ENABLED"),
            p2_enabled=_env_enabled("P2_RETRIEVAL_ENABLED"),
            shadow_enabled=_env_enabled("UNIFIED_RETRIEVAL_SHADOW_MODE"),
            branch_timeout_seconds=_bounded_float(
                "UNIFIED_RETRIEVAL_BRANCH_TIMEOUT_SECONDS", 8.0, 0.05, 60.0
            ),
            rrf_rank_constant=_bounded_int(
                "UNIFIED_RETRIEVAL_RRF_K", 60, 1, 1000
            ),
            p2_asset_chunk_quota=_bounded_int(
                "UNIFIED_RETRIEVAL_P2_ASSET_CHUNK_QUOTA", 2, 1, 10
            ),
        )


class UnifiedRetrievalFailure(RuntimeError):
    def __init__(
        self,
        *,
        retrieval_id: str,
        request_id: str | None,
        reason: str,
        status_code: int = 503,
    ) -> None:
        super().__init__(reason)
        self.retrieval_id = retrieval_id
        self.request_id = request_id
        self.reason = reason
        self.status_code = status_code


def _safe_reason(value: str | None, default: str) -> str:
    normalized = re.sub(r"[^a-z0-9_:-]", "", (value or "").lower())[:120]
    return normalized or default


def _timeout_result(source: str, timeout_seconds: float) -> BranchResult:
    return BranchResult(
        source_index=source,  # type: ignore[arg-type]
        mode=f"{source}_branch_timeout",
        status="timeout",
        candidates=(),
        latency_ms=round(timeout_seconds * 1000, 3),
        fallback_reason=f"{source}_timeout",
        error_code=f"{source.upper()}_BRANCH_TIMEOUT",
        error_type="Timeout",
    )


def _skipped_result(source: str, reason: str) -> BranchResult:
    return BranchResult(
        source_index=source,  # type: ignore[arg-type]
        mode=f"{source}_branch_skipped",
        status="skipped",
        candidates=(),
        latency_ms=0.0,
        fallback_reason=reason,
        error_code=reason.upper(),
        error_type="FeatureDisabled",
    )


def _source_identity_key(candidate: NormalizedCandidate) -> str:
    """Deduplicate only within a physical index and governed identity."""

    return f"{candidate.source_index}:{candidate.evidence_id}"


def _stable_candidate_id(candidate: NormalizedCandidate) -> str:
    return (
        candidate.knowledge_asset_id
        or candidate.candidate_id
        or candidate.chunk_id
    )


def _candidate_to_result(
    candidate: NormalizedCandidate,
    *,
    rank: int,
    fused_score: float | None,
    contributions: list[dict[str, object]] | None = None,
) -> UnifiedRetrievalResult:
    metadata = dict(candidate.metadata)
    if contributions:
        metadata["rrf_contributions"] = contributions
    return UnifiedRetrievalResult(
        source_index=candidate.source_index,
        source_type=candidate.source_type,
        rank=rank,
        fused_score=round(fused_score, 8) if fused_score is not None else None,
        original_rank=candidate.original_rank,
        original_score=candidate.original_score,
        candidate_id=candidate.candidate_id,
        knowledge_asset_id=candidate.knowledge_asset_id,
        chunk_id=candidate.chunk_id,
        asset_id=candidate.asset_id,
        evidence_text=candidate.evidence_text,
        content_type=candidate.content_type,
        source_trace=dict(candidate.source_trace),
        metadata=metadata,
    )


def route_order_results(
    candidates: Iterable[NormalizedCandidate],
    *,
    top_k: int,
    p2_asset_chunk_quota: int = 2,
) -> list[UnifiedRetrievalResult]:
    """Deduplicate one route without using route-local score as a cross-route key."""

    seen: set[tuple[str, str]] = set()
    asset_counts: dict[str, int] = {}
    results: list[UnifiedRetrievalResult] = []
    for candidate in candidates:
        identity = (candidate.source_index, candidate.evidence_id)
        if identity in seen:
            continue
        if (
            candidate.source_index == "p2"
            and candidate.asset_id
            and asset_counts.get(candidate.asset_id, 0) >= p2_asset_chunk_quota
        ):
            continue
        seen.add(identity)
        if candidate.source_index == "p2" and candidate.asset_id:
            asset_counts[candidate.asset_id] = asset_counts.get(candidate.asset_id, 0) + 1
        results.append(
            _candidate_to_result(candidate, rank=len(results) + 1, fused_score=None)
        )
        if len(results) >= top_k:
            break
    return results


def reciprocal_rank_fusion(
    branches: Iterable[BranchResult],
    *,
    top_k: int,
    rank_constant: int = 60,
    p2_asset_chunk_quota: int = 2,
) -> list[UnifiedRetrievalResult]:
    """Fuse ranks only; route-local cosine scores never affect ordering."""

    grouped: dict[str, dict[str, object]] = {}
    for branch in branches:
        if branch.status != "ok":
            continue
        for candidate in branch.candidates:
            key = _source_identity_key(candidate)
            contribution = 1.0 / (rank_constant + candidate.original_rank)
            if key not in grouped:
                grouped[key] = {
                    "candidate": candidate,
                    "score": contribution,
                    "best_rank": candidate.original_rank,
                    "contributions": [
                        {
                            "source_index": candidate.source_index,
                            "original_rank": candidate.original_rank,
                            "chunk_id": candidate.chunk_id,
                            "rrf_score": round(contribution, 8),
                        }
                    ],
                }
                continue
            state = grouped[key]
            representative = state["candidate"]
            if not isinstance(representative, NormalizedCandidate):
                continue
            if (
                candidate.original_rank,
                0 if candidate.source_index == "p1" else 1,
                _stable_candidate_id(candidate),
            ) < (
                representative.original_rank,
                0 if representative.source_index == "p1" else 1,
                _stable_candidate_id(representative),
            ):
                state["candidate"] = candidate
                state["score"] = contribution
                state["best_rank"] = candidate.original_rank
                state["contributions"] = [
                    {
                        "source_index": candidate.source_index,
                        "original_rank": candidate.original_rank,
                        "chunk_id": candidate.chunk_id,
                        "rrf_score": round(contribution, 8),
                    }
                ]

    ranked = sorted(
        grouped.values(),
        key=lambda state: (
            -float(state["score"]),
            int(state["best_rank"]),
            0
            if isinstance(state["candidate"], NormalizedCandidate)
            and state["candidate"].source_index == "p1"
            else 1,
            _stable_candidate_id(state["candidate"]),  # type: ignore[arg-type]
        ),
    )
    results: list[UnifiedRetrievalResult] = []
    p2_asset_counts: dict[str, int] = {}
    for state in ranked:
        candidate = state["candidate"]
        if not isinstance(candidate, NormalizedCandidate):
            continue
        if (
            candidate.source_index == "p2"
            and candidate.asset_id
            and p2_asset_counts.get(candidate.asset_id, 0) >= p2_asset_chunk_quota
        ):
            continue
        if candidate.source_index == "p2" and candidate.asset_id:
            p2_asset_counts[candidate.asset_id] = (
                p2_asset_counts.get(candidate.asset_id, 0) + 1
            )
        results.append(
            _candidate_to_result(
                candidate,
                rank=len(results) + 1,
                fused_score=float(state["score"]),
                contributions=list(state["contributions"]),  # type: ignore[arg-type]
            )
        )
        if len(results) >= top_k:
            break
    return results


def _fresh_p2_filter(candidates: tuple[NormalizedCandidate, ...]) -> tuple[NormalizedCandidate, ...]:
    """Close the archive/supersede race after P2 vector recall."""

    if not candidates:
        return ()
    db = SessionLocal()
    accepted: list[NormalizedCandidate] = []
    try:
        serving_rows = {
            (row.index_entry_id, row.chunk_id, row.knowledge_asset_id): row
            for row in list_serving_embedding_rows(db)
        }
        for candidate in candidates:
            entry_id = str(candidate.metadata.get("index_entry_id", ""))
            if not entry_id or not candidate.knowledge_asset_id or not candidate.asset_id:
                continue
            try:
                entry = get_index_entry(db, entry_id)
                asset = get_knowledge_asset(db, candidate.knowledge_asset_id)
            except (KnowledgeIndexSourceTraceError, KnowledgeSourceTraceError):
                continue
            embedding_row = serving_rows.get(
                (entry_id, candidate.chunk_id, candidate.knowledge_asset_id)
            )
            if (
                entry is None
                or asset is None
                or embedding_row is None
                or entry.knowledge_asset_id != candidate.knowledge_asset_id
                or asset.asset_id != candidate.asset_id
                or asset.status != "active"
                or entry.status != "serving"
                or entry.sync_state != "ready"
                or entry.error_message
                or entry.source_trace.model_dump() != candidate.source_trace
                or embedding_row.embedding_fingerprint
                != candidate.metadata.get("embedding_fingerprint")
                or embedding_row.embedding_profile
                != candidate.metadata.get("embedding_profile")
                or embedding_row.provider
                != candidate.metadata.get("embedding_provider")
                or embedding_row.model != candidate.metadata.get("embedding_model")
                or embedding_row.dimension
                != candidate.metadata.get("embedding_dimension")
                or embedding_row.embedding_metadata.get("index_fingerprint")
                != entry.fingerprint
                or embedding_row.embedding_metadata.get("chunk_hash")
                != embedding_row.chunk_hash
                or embedding_row.embedding_metadata.get("source_trace")
                != candidate.source_trace
                or int(
                    embedding_row.embedding_metadata.get("index_generation", -1)
                )
                != entry.generation
            ):
                continue
            accepted.append(candidate)
    finally:
        db.close()
    return tuple(accepted)


def _source_mode(branch: BranchResult) -> UnifiedRetrievalSourceMode:
    return UnifiedRetrievalSourceMode(
        source_index=branch.source_index,
        mode=branch.mode,
        status=branch.status,
        result_count=branch.result_count,
        latency_ms=max(branch.latency_ms, 0.0),
        fallback_used=branch.fallback_used,
        fallback_reason=branch.fallback_reason,
        error_code=branch.error_code,
        error_type=branch.error_type,
        embedding_provider=branch.embedding_provider,
        embedding_model=branch.embedding_model,
        embedding_dimension=branch.embedding_dimension,
        embedding_profile=branch.embedding_profile,
        native_retrieval_id=branch.native_retrieval_id,
    )


def _result_id(result: UnifiedRetrievalResult) -> str:
    return f"{result.source_index}:{result.chunk_id}"


def _shadow_comparison(
    control: list[UnifiedRetrievalResult],
    candidate: list[UnifiedRetrievalResult],
    *,
    control_mode: str,
    candidate_mode: str,
) -> UnifiedRetrievalShadowComparison:
    control_ids = [_result_id(item) for item in control]
    candidate_ids = [_result_id(item) for item in candidate]
    control_set = set(control_ids)
    candidate_set = set(candidate_ids)
    control_ranks = {item_id: rank for rank, item_id in enumerate(control_ids, start=1)}
    candidate_ranks = {item_id: rank for rank, item_id in enumerate(candidate_ids, start=1)}
    overlap = control_set & candidate_set
    return UnifiedRetrievalShadowComparison(
        control_mode=control_mode,
        candidate_mode=candidate_mode,
        control_count=len(control),
        candidate_count=len(candidate),
        overlap_count=len(overlap),
        control_only_count=len(control_set - candidate_set),
        candidate_only_count=len(candidate_set - control_set),
        rank_changed_count=sum(
            1 for item_id in overlap if control_ranks[item_id] != candidate_ranks[item_id]
        ),
        control_result_ids=control_ids,
        candidate_result_ids=candidate_ids,
        summary={
            "p2_candidate_count": sum(
                1 for item in candidate if item.source_index == "p2"
            ),
            "raw_scores_compared": False,
        },
    )


class UnifiedRetrievalService:
    def __init__(
        self,
        db: Session,
        *,
        p1_adapter: P1RetrievalAdapter | None = None,
        p2_adapter: P2RetrievalAdapter | None = None,
        flags: UnifiedRetrievalFlags | None = None,
        p2_post_filter: Callable[
            [tuple[NormalizedCandidate, ...]], tuple[NormalizedCandidate, ...]
        ] = _fresh_p2_filter,
    ) -> None:
        self.db = db
        self.p1_adapter = p1_adapter or P1RetrievalAdapter()
        self.p2_adapter = p2_adapter or P2RetrievalAdapter()
        self.flags = flags or UnifiedRetrievalFlags.from_environment()
        self.p2_post_filter = p2_post_filter

    def _run_one_branch(
        self,
        source: str,
        adapter: object,
        payload: UnifiedRetrievalRequest,
        candidate_k: int,
    ) -> BranchResult:
        result = adapter.search(  # type: ignore[attr-defined]
            query=payload.query,
            top_k=candidate_k,
            request_id=payload.request_id,
        )
        if source != "p2" or result.status != "ok" or not result.candidates:
            return result
        try:
            filtered = self.p2_post_filter(result.candidates)
        except Exception as exc:
            return BranchResult(
                source_index="p2",
                mode="p2_post_filter_error",
                status="error",
                candidates=(),
                latency_ms=result.latency_ms,
                fallback_reason="p2_post_filter_error",
                error_code="P2_POST_FILTER_ERROR",
                error_type=type(exc).__name__[:80],
                embedding_provider=result.embedding_provider,
                embedding_model=result.embedding_model,
                embedding_dimension=result.embedding_dimension,
                embedding_profile=result.embedding_profile,
                native_retrieval_id=result.native_retrieval_id,
            )
        if len(filtered) == len(result.candidates):
            return result
        return BranchResult(
            **{
                **result.__dict__,
                "candidates": filtered,
                "fallback_reason": (
                    result.fallback_reason or "p2_post_filter_rejected_candidates"
                ),
            }
        )

    def _run_one_branch_with_slot(
        self,
        source: str,
        adapter: object,
        payload: UnifiedRetrievalRequest,
        candidate_k: int,
    ) -> BranchResult:
        try:
            return self._run_one_branch(source, adapter, payload, candidate_k)
        finally:
            _BRANCH_SLOTS.release()

    def _run_branches(
        self,
        payload: UnifiedRetrievalRequest,
        candidate_k: int,
        *,
        include_p1_control: bool,
    ) -> dict[str, BranchResult]:
        results: dict[str, BranchResult] = {}
        adapters: dict[str, object] = {}
        branch_sources = list(payload.sources)
        if include_p1_control and "p1" not in branch_sources:
            branch_sources.insert(0, "p1")
        for source in branch_sources:
            if source == "p2" and not self.flags.p2_enabled:
                results[source] = _skipped_result(source, "p2_retrieval_disabled")
            else:
                adapters[source] = (
                    self.p1_adapter if source == "p1" else self.p2_adapter
                )
        if not adapters:
            return results

        futures: dict[str, Future[BranchResult]] = {}
        for source, adapter in adapters.items():
            if not _BRANCH_SLOTS.acquire(blocking=False):
                results[source] = BranchResult(
                    source_index=source,  # type: ignore[arg-type]
                    mode=f"{source}_branch_saturated",
                    status="error",
                    candidates=(),
                    latency_ms=0.0,
                    fallback_reason=f"{source}_branch_saturated",
                    error_code=f"{source.upper()}_BRANCH_SATURATED",
                    error_type="CapacityExceeded",
                )
                continue
            try:
                futures[source] = _BRANCH_EXECUTOR.submit(
                    self._run_one_branch_with_slot,
                    source,
                    adapter,
                    payload,
                    candidate_k,
                )
            except Exception:
                _BRANCH_SLOTS.release()
                results[source] = BranchResult(
                    source_index=source,  # type: ignore[arg-type]
                    mode=f"{source}_branch_executor_unavailable",
                    status="error",
                    candidates=(),
                    latency_ms=0.0,
                    fallback_reason=f"{source}_branch_executor_unavailable",
                    error_code=f"{source.upper()}_BRANCH_EXECUTOR_UNAVAILABLE",
                    error_type="ExecutorUnavailable",
                )
        if not futures:
            return results
        done, _ = wait(
            futures.values(), timeout=self.flags.branch_timeout_seconds
        )
        for source, future in futures.items():
            if future not in done:
                results[source] = _timeout_result(
                    source, self.flags.branch_timeout_seconds
                )
                continue
            try:
                results[source] = future.result()
            except Exception as exc:
                results[source] = BranchResult(
                    source_index=source,  # type: ignore[arg-type]
                    mode=f"{source}_branch_error",
                    status="error",
                    candidates=(),
                    latency_ms=0.0,
                    fallback_reason=f"{source}_branch_error",
                    error_code=f"{source.upper()}_BRANCH_ERROR",
                    error_type=type(exc).__name__[:80],
                )
        return results

    def _log_failure(
        self,
        *,
        retrieval_id: str,
        payload: UnifiedRetrievalRequest,
        reason: str,
        branches: dict[str, BranchResult] | None = None,
    ) -> None:
        branch_payload = {
            source: {
                "mode": branch.mode,
                "status": branch.status,
                "latency_ms": branch.latency_ms,
                "fallback_reason": branch.fallback_reason,
                "error_code": branch.error_code,
                "native_retrieval_id": branch.native_retrieval_id,
            }
            for source, branch in (branches or {}).items()
        }
        unified = {
            "namespace": "unified_retrieval_v1",
            "shadow_mode": self.flags.shadow_enabled,
            "status": "error",
            "reason": reason,
            "source_modes": branch_payload,
            "raw_scores_compared": False,
        }
        try:
            db_repositories.save_retrieval_log_to_db(
                self.db,
                {
                    "retrieval_id": retrieval_id,
                    "request_id": payload.request_id,
                    "query": payload.query,
                    "result_chunk_ids": [],
                    "result_count": 0,
                    "retrieval_mode": "unified_retrieval_error",
                    "fallback_used": False,
                    "fallback_reason": reason,
                    "metadata": {"unified_retrieval": unified},
                    "unified_retrieval": unified,
                },
            )
        except Exception:
            self.db.rollback()

    def _log(self, response: UnifiedRetrievalResponse) -> None:
        unified = {
            "namespace": "unified_retrieval_v1",
            "shadow_mode": response.retrieval_mode == "shadow_control",
            "control_mode": response.control_mode,
            "candidate_mode": response.candidate_mode,
            "source_modes": {
                source: mode.model_dump() for source, mode in response.source_modes.items()
            },
            "candidate_result_ids": [
                _result_id(item) for item in response.candidate_results
            ],
            "source_distribution": response.source_distribution,
            "latency_ms": response.latency_ms.model_dump(),
            "fallback_used": response.fallback_used,
            "fallback_reason": response.fallback_reason,
            "request_id": response.request_id,
            "native_retrieval_ids": {
                source: mode.native_retrieval_id
                for source, mode in response.source_modes.items()
            },
            "shadow_comparison": (
                response.shadow_comparison.model_dump()
                if response.shadow_comparison
                else None
            ),
            "rrf_rank_constant": self.flags.rrf_rank_constant,
            "raw_scores_compared": False,
        }
        trace = {
            "retrieval_id": response.retrieval_id,
            "request_id": response.request_id,
            "query": response.query,
            "result_chunk_ids": [item.chunk_id for item in response.results],
            "result_count": len(response.results),
            "retrieval_mode": response.retrieval_mode,
            "fallback_used": response.fallback_used,
            "fallback_reason": response.fallback_reason,
            "metadata": {"unified_retrieval": unified},
            "unified_retrieval": unified,
        }
        try:
            db_repositories.save_retrieval_log_to_db(self.db, trace)
        except Exception:
            self.db.rollback()

    def search(self, payload: UnifiedRetrievalRequest) -> UnifiedRetrievalResponse:
        started = time.perf_counter()
        created_at = datetime.now(UTC).isoformat()
        retrieval_id = f"unified_retrieval_{uuid4().hex[:16]}"
        if not self.flags.unified_enabled:
            self._log_failure(
                retrieval_id=retrieval_id,
                payload=payload,
                reason="unified_retrieval_disabled",
            )
            raise UnifiedRetrievalFailure(
                retrieval_id=retrieval_id,
                request_id=payload.request_id,
                reason="unified_retrieval_disabled",
            )
        if payload.shadow_mode and not self.flags.shadow_enabled:
            self._log_failure(
                retrieval_id=retrieval_id,
                payload=payload,
                reason="unified_shadow_disabled",
            )
            raise UnifiedRetrievalFailure(
                retrieval_id=retrieval_id,
                request_id=payload.request_id,
                reason="unified_shadow_disabled",
            )
        effective_shadow = self.flags.shadow_enabled

        candidate_k = min(max(payload.top_k * 4, 20), 20)
        branches = self._run_branches(
            payload, candidate_k, include_p1_control=effective_shadow
        )
        healthy = [
            branch for branch in branches.values() if branch.status == "ok"
        ]
        if not healthy:
            reasons = [
                _safe_reason(branch.fallback_reason, f"{source}_unavailable")
                for source, branch in sorted(branches.items())
            ]
            reason = "branches_unavailable:" + ",".join(reasons)
            self._log_failure(
                retrieval_id=retrieval_id,
                payload=payload,
                reason=reason,
                branches=branches,
            )
            raise UnifiedRetrievalFailure(
                retrieval_id=retrieval_id,
                request_id=payload.request_id,
                reason=reason,
            )

        p1 = branches.get("p1")
        p2 = branches.get("p2")
        control_branch = p1 if p1 and p1.status == "ok" else None
        control_results = route_order_results(
            control_branch.candidates if control_branch else (),
            top_k=payload.top_k,
            p2_asset_chunk_quota=self.flags.p2_asset_chunk_quota,
        )
        control_mode = control_branch.mode if control_branch else "control_unavailable"

        fusion_started = time.perf_counter()
        requested_healthy = [
            branches[source]
            for source in payload.sources
            if source in branches and branches[source].status == "ok"
        ]
        healthy_sources = {branch.source_index for branch in requested_healthy}
        if payload.fusion_enabled and healthy_sources == {"p1", "p2"}:
            candidate_results = reciprocal_rank_fusion(
                requested_healthy,
                top_k=payload.top_k,
                rank_constant=self.flags.rrf_rank_constant,
                p2_asset_chunk_quota=self.flags.p2_asset_chunk_quota,
            )
            candidate_mode = "unified_rrf"
        else:
            preferred = requested_healthy[0] if requested_healthy else None
            candidate_results = route_order_results(
                preferred.candidates if preferred else (),
                top_k=payload.top_k,
                p2_asset_chunk_quota=self.flags.p2_asset_chunk_quota,
            )
            if healthy_sources == {"p1"}:
                candidate_mode = "partial_p1" if "p2" in payload.sources else "p1_only"
            elif healthy_sources == {"p2"}:
                candidate_mode = "partial_p2" if "p1" in payload.sources else "p2_only"
            elif healthy_sources == {"p1", "p2"} and not payload.fusion_enabled:
                candidate_mode = "p1_only"
            else:
                candidate_mode = "candidate_unavailable"
        fusion_ms = round((time.perf_counter() - fusion_started) * 1000, 3)

        unavailable = [
            (source, branch)
            for source, branch in branches.items()
            if branch.status != "ok"
        ]
        branch_fallbacks = [
            (source, branch)
            for source, branch in branches.items()
            if branch.status == "ok" and branch.fallback_used
        ]
        fallback_used = bool(unavailable or branch_fallbacks)
        fallback_reason = None
        if fallback_used:
            fallback_reason = ";".join(
                f"{source}:{_safe_reason(branch.fallback_reason, branch.status)}"
                for source, branch in unavailable + branch_fallbacks
            )

        source_distribution = {
            source: sum(
                1 for item in candidate_results if item.source_index == source
            )
            for source in ("p1", "p2")
        }
        comparison = _shadow_comparison(
            control_results,
            candidate_results,
            control_mode=control_mode,
            candidate_mode=candidate_mode,
        )
        retrieval_mode = "shadow_control" if effective_shadow else candidate_mode
        visible_results = control_results if effective_shadow else candidate_results
        response = UnifiedRetrievalResponse(
            retrieval_id=retrieval_id,
            request_id=payload.request_id,
            query=payload.query,
            top_k=payload.top_k,
            sources=payload.sources,
            retrieval_mode=retrieval_mode,  # type: ignore[arg-type]
            control_mode=control_mode,
            candidate_mode=candidate_mode,
            source_modes={
                source: _source_mode(branch) for source, branch in branches.items()
            },
            results=visible_results,
            control_results=control_results,
            candidate_results=candidate_results,
            p1_result_count=p1.result_count if p1 else 0,
            p2_result_count=p2.result_count if p2 else 0,
            fused_result_count=len(candidate_results),
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
            partial=bool(unavailable),
            source_distribution=source_distribution,
            latency_ms=UnifiedRetrievalLatency(
                total=round((time.perf_counter() - started) * 1000, 3),
                p1=p1.latency_ms if p1 else None,
                p2=p2.latency_ms if p2 else None,
                fusion=fusion_ms,
            ),
            shadow_comparison=comparison,
            created_at=created_at,
            debug=(
                {
                    "candidate_k": candidate_k,
                    "rrf_rank_constant": self.flags.rrf_rank_constant,
                    "raw_scores_compared": False,
                    "p2_post_filter": True,
                    "server_forced_shadow": effective_shadow,
                }
                if payload.debug
                else None
            ),
        )
        self._log(response)
        return response
