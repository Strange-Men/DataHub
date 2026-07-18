"""M8.2 unit gates for parallel branches, rank-only RRF, and safe shadowing."""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path
import sys
import time
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient


ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.unified_retrieval_adapters import BranchResult, NormalizedCandidate  # noqa: E402
from app.unified_retrieval_schemas import UnifiedRetrievalRequest  # noqa: E402
from app.unified_retrieval_service import (  # noqa: E402
    UnifiedRetrievalFailure,
    UnifiedRetrievalFlags,
    UnifiedRetrievalService,
    reciprocal_rank_fusion,
    route_order_results,
)


def candidate(
    source: str,
    rank: int,
    *,
    score: float = 0.5,
    suffix: str | None = None,
    text: str | None = None,
    asset_id: str | None = None,
) -> NormalizedCandidate:
    suffix = suffix or f"{source}-{rank}"
    return NormalizedCandidate(
        source_index=source,  # type: ignore[arg-type]
        source_type="p1_text" if source == "p1" else "p2_knowledge_asset",
        original_rank=rank,
        original_score=score,
        candidate_id=f"candidate-{suffix}" if source == "p1" else None,
        knowledge_asset_id=f"knowledge-{suffix}" if source == "p2" else None,
        chunk_id=f"chunk-{suffix}",
        asset_id=asset_id if source == "p2" else None,
        evidence_text=text or f"evidence {suffix}",
        content_type="faq" if source == "p1" else "ocr",
        source_trace={"trace": suffix},
        metadata={"index_entry_id": f"index-{suffix}"} if source == "p2" else {},
    )


def branch(
    source: str,
    candidates: tuple[NormalizedCandidate, ...] = (),
    *,
    status: str = "ok",
    fallback_reason: str | None = None,
) -> BranchResult:
    return BranchResult(
        source_index=source,  # type: ignore[arg-type]
        mode=(
            "customerops_vector_retrieval"
            if source == "p1"
            else "p2_vector_retrieval"
        ),
        status=status,  # type: ignore[arg-type]
        candidates=candidates,
        latency_ms=2.0,
        fallback_reason=fallback_reason,
        error_code=(f"{source.upper()}_ERROR" if status == "error" else None),
    )


class FakeAdapter:
    def __init__(self, result: BranchResult, *, delay: float = 0.0) -> None:
        self.result = result
        self.delay = delay
        self.calls: list[dict[str, object]] = []

    def search(self, **kwargs: object) -> BranchResult:
        self.calls.append(kwargs)
        if self.delay:
            time.sleep(self.delay)
        return self.result


def flags(**overrides: object) -> UnifiedRetrievalFlags:
    values: dict[str, object] = {
        "unified_enabled": True,
        "p2_enabled": True,
        "shadow_enabled": True,
        "branch_timeout_seconds": 0.2,
        "rrf_rank_constant": 60,
        "p2_asset_chunk_quota": 2,
    }
    values.update(overrides)
    return UnifiedRetrievalFlags(**values)  # type: ignore[arg-type]


def service(
    p1: BranchResult,
    p2: BranchResult,
    *,
    feature_flags: UnifiedRetrievalFlags | None = None,
    p2_filter=None,
) -> UnifiedRetrievalService:
    return UnifiedRetrievalService(
        Mock(),
        p1_adapter=FakeAdapter(p1),  # type: ignore[arg-type]
        p2_adapter=FakeAdapter(p2),  # type: ignore[arg-type]
        flags=feature_flags or flags(),
        p2_post_filter=p2_filter or (lambda items: items),
    )


def test_feature_flags_fail_closed_and_invalid_values_stay_disabled() -> None:
    names = {
        "UNIFIED_RETRIEVAL_ENABLED": "not-a-bool",
        "P2_RETRIEVAL_ENABLED": "",
        "UNIFIED_RETRIEVAL_SHADOW_MODE": "0",
    }
    with patch.dict(os.environ, names, clear=False):
        configured = UnifiedRetrievalFlags.from_environment()
    assert configured.unified_enabled is False
    assert configured.p2_enabled is False
    assert configured.shadow_enabled is False
    assert configured.rrf_rank_constant == 60


def test_rrf_uses_rank_only_with_k60_and_is_stable_when_raw_scores_swap() -> None:
    first = branch(
        "p1",
        (candidate("p1", 1, score=-100), candidate("p1", 2, score=999)),
    )
    second = branch(
        "p2",
        (candidate("p2", 1, score=999), candidate("p2", 2, score=-100)),
    )
    fused = reciprocal_rank_fusion((first, second), top_k=4, rank_constant=60)
    assert [item.source_index for item in fused] == ["p1", "p2", "p1", "p2"]
    assert fused[0].fused_score == round(1 / 61, 8)
    assert fused[2].fused_score == round(1 / 62, 8)

    swapped = reciprocal_rank_fusion(
        (
            branch("p1", tuple(reversed(first.candidates))),
            branch("p2", tuple(reversed(second.candidates))),
        ),
        top_k=4,
        rank_constant=60,
    )
    assert [item.chunk_id for item in swapped] == [item.chunk_id for item in fused]


def test_cross_index_exact_text_remains_distinct_and_preserves_both_traces() -> None:
    shared_p1 = candidate("p1", 1, text="Same governed answer")
    shared_p2 = candidate("p2", 2, text="  same   governed ANSWER ")
    unique = candidate("p2", 1, text="Different answer")
    fused = reciprocal_rank_fusion(
        (branch("p1", (shared_p1,)), branch("p2", (unique, shared_p2))),
        top_k=5,
    )
    assert len(fused) == 3
    shared = [item for item in fused if "governed" in item.evidence_text.lower()]
    assert {item.source_index for item in shared} == {"p1", "p2"}
    assert all(len(item.metadata["rrf_contributions"]) == 1 for item in shared)
    assert {str(item.source_trace["trace"]) for item in shared} == {"p1-1", "p2-2"}


def test_route_dedup_and_p2_asset_quota_are_deterministic() -> None:
    items = (
        candidate("p2", 1, suffix="a", asset_id="asset-one"),
        candidate("p2", 2, suffix="a", asset_id="asset-one"),
        candidate("p2", 3, suffix="b", asset_id="asset-one"),
        candidate("p2", 4, suffix="c", asset_id="asset-one"),
    )
    results = route_order_results(items, top_k=5, p2_asset_chunk_quota=2)
    assert [item.knowledge_asset_id for item in results] == ["knowledge-a", "knowledge-b"]


def test_same_route_identity_contributes_to_rrf_only_once() -> None:
    first = candidate("p2", 1, suffix="same-ka", asset_id="asset-one")
    duplicate_chunk = replace(
        first,
        original_rank=2,
        original_score=0.99,
        chunk_id="chunk-same-ka-second",
        evidence_text="a second chunk for the same governed asset",
    )
    fused = reciprocal_rank_fusion(
        (branch("p2", (first, duplicate_chunk)),), top_k=5, rank_constant=60
    )
    assert len(fused) == 1
    assert fused[0].fused_score == round(1 / 61, 8)
    assert len(fused[0].metadata["rrf_contributions"]) == 1


def test_shadow_returns_p1_control_while_candidate_contains_rrf_results() -> None:
    p1 = branch("p1", (candidate("p1", 1), candidate("p1", 2)))
    p2 = branch("p2", (candidate("p2", 1),))
    with patch("app.unified_retrieval_service.db_repositories.save_retrieval_log_to_db"):
        response = service(p1, p2).search(
            UnifiedRetrievalRequest(query="warranty", top_k=3, shadow_mode=True)
        )
    assert response.retrieval_mode == "shadow_control"
    assert [item.chunk_id for item in response.results] == [
        item.chunk_id for item in response.control_results
    ]
    assert {item.source_index for item in response.candidate_results} == {"p1", "p2"}
    assert response.candidate_mode == "unified_rrf"
    assert response.shadow_comparison is not None
    assert response.shadow_comparison.summary["raw_scores_compared"] is False


def test_non_shadow_versioned_api_returns_fused_candidate() -> None:
    p1 = branch("p1", (candidate("p1", 1),))
    p2 = branch("p2", (candidate("p2", 1),))
    with patch("app.unified_retrieval_service.db_repositories.save_retrieval_log_to_db"):
        response = service(p1, p2, feature_flags=flags(shadow_enabled=False)).search(
            UnifiedRetrievalRequest(query="mixed", shadow_mode=False)
        )
    assert response.retrieval_mode == "unified_rrf"
    assert response.results == response.candidate_results
    assert response.fallback_used is False


def test_server_shadow_flag_cannot_be_bypassed_by_request() -> None:
    p1 = branch("p1", (candidate("p1", 1),))
    p2 = branch("p2", (candidate("p2", 1),))
    with patch("app.unified_retrieval_service.db_repositories.save_retrieval_log_to_db"):
        response = service(p1, p2).search(
            UnifiedRetrievalRequest(query="forced shadow", shadow_mode=False)
        )
    assert response.retrieval_mode == "shadow_control"
    assert response.results == response.control_results


def test_p2_only_shadow_still_uses_injected_p1_control_but_candidate_is_p2() -> None:
    p1_adapter = FakeAdapter(branch("p1", (candidate("p1", 1),)))
    p2_adapter = FakeAdapter(branch("p2", (candidate("p2", 1),)))
    retrieval = UnifiedRetrievalService(
        Mock(),
        p1_adapter=p1_adapter,  # type: ignore[arg-type]
        p2_adapter=p2_adapter,  # type: ignore[arg-type]
        flags=flags(),
        p2_post_filter=lambda items: items,
    )
    with patch("app.unified_retrieval_service.db_repositories.save_retrieval_log_to_db"):
        response = retrieval.search(
            UnifiedRetrievalRequest(query="p2 only", sources="p2", fusion_enabled=False)
        )
    assert [item.source_index for item in response.results] == ["p1"]
    assert [item.source_index for item in response.candidate_results] == ["p2"]
    assert response.candidate_mode == "p2_only"
    assert set(response.source_modes) == {"p1", "p2"}


def test_dual_route_without_fusion_keeps_p1_as_deterministic_candidate() -> None:
    p1 = branch("p1", (candidate("p1", 1),))
    p2 = branch("p2", (candidate("p2", 1),))
    with patch("app.unified_retrieval_service.db_repositories.save_retrieval_log_to_db"):
        response = service(p1, p2).search(
            UnifiedRetrievalRequest(query="no fusion", fusion_enabled=False)
        )
    assert response.candidate_mode == "p1_only"
    assert [item.source_index for item in response.candidate_results] == ["p1"]
    assert response.results == response.control_results


def test_p2_flag_disabled_keeps_p1_control_and_never_calls_p2_adapter() -> None:
    p1_adapter = FakeAdapter(branch("p1", (candidate("p1", 1),)))
    p2_adapter = FakeAdapter(branch("p2", (candidate("p2", 1),)))
    retrieval = UnifiedRetrievalService(
        Mock(),
        p1_adapter=p1_adapter,  # type: ignore[arg-type]
        p2_adapter=p2_adapter,  # type: ignore[arg-type]
        flags=flags(p2_enabled=False),
        p2_post_filter=lambda items: items,
    )
    with patch("app.unified_retrieval_service.db_repositories.save_retrieval_log_to_db"):
        response = retrieval.search(UnifiedRetrievalRequest(query="p2 disabled"))
    assert p2_adapter.calls == []
    assert response.source_modes["p2"].status == "skipped"
    assert response.candidate_mode == "partial_p1"
    assert response.results == response.control_results


def test_parallel_timeout_does_not_wait_for_slow_branch_and_degrades_to_p1() -> None:
    p1_adapter = FakeAdapter(branch("p1", (candidate("p1", 1),)))
    p2_adapter = FakeAdapter(branch("p2", (candidate("p2", 1),)), delay=0.35)
    retrieval = UnifiedRetrievalService(
        Mock(),
        p1_adapter=p1_adapter,  # type: ignore[arg-type]
        p2_adapter=p2_adapter,  # type: ignore[arg-type]
        flags=flags(branch_timeout_seconds=0.05),
        p2_post_filter=lambda items: items,
    )
    started = time.perf_counter()
    with patch("app.unified_retrieval_service.db_repositories.save_retrieval_log_to_db"):
        response = retrieval.search(UnifiedRetrievalRequest(query="timeout"))
    elapsed = time.perf_counter() - started
    assert elapsed < 0.2
    assert response.candidate_mode == "partial_p1"
    assert response.source_modes["p2"].status == "timeout"
    assert response.fallback_used is True
    assert "p2:p2_timeout" in str(response.fallback_reason)


def test_post_filter_failure_isolated_and_returns_healthy_p1_control() -> None:
    p1 = branch("p1", (candidate("p1", 1),))
    p2 = branch("p2", (candidate("p2", 1),))

    def fail(_items):
        raise RuntimeError("DATABASE_URL=must-not-leak")

    with patch("app.unified_retrieval_service.db_repositories.save_retrieval_log_to_db"):
        response = service(p1, p2, p2_filter=fail).search(
            UnifiedRetrievalRequest(query="post gate failure")
        )
    assert response.results == response.control_results
    assert response.candidate_mode == "partial_p1"
    assert response.source_modes["p2"].error_code == "P2_POST_FILTER_ERROR"
    assert "DATABASE_URL" not in str(response.model_dump())


def test_p2_freshness_filter_is_inside_branch_timeout_budget() -> None:
    p1_adapter = FakeAdapter(branch("p1", (candidate("p1", 1),)))
    p2_adapter = FakeAdapter(branch("p2", (candidate("p2", 1),)))

    def slow_filter(items):
        time.sleep(0.3)
        return items

    retrieval = UnifiedRetrievalService(
        Mock(),
        p1_adapter=p1_adapter,  # type: ignore[arg-type]
        p2_adapter=p2_adapter,  # type: ignore[arg-type]
        flags=flags(branch_timeout_seconds=0.05),
        p2_post_filter=slow_filter,
    )
    started = time.perf_counter()
    with patch("app.unified_retrieval_service.db_repositories.save_retrieval_log_to_db"):
        response = retrieval.search(UnifiedRetrievalRequest(query="slow freshness"))
    assert time.perf_counter() - started < 0.2
    assert response.source_modes["p2"].status == "timeout"
    assert response.candidate_mode == "partial_p1"


def test_executor_submit_failure_releases_every_acquired_capacity_slot() -> None:
    class CountingSlots:
        def __init__(self) -> None:
            self.acquired = 0
            self.released = 0

        def acquire(self, blocking=False):
            del blocking
            self.acquired += 1
            return True

        def release(self):
            self.released += 1

    slots = CountingSlots()
    retrieval = service(
        branch("p1", (candidate("p1", 1),)),
        branch("p2", (candidate("p2", 1),)),
    )
    with patch("app.unified_retrieval_service._BRANCH_SLOTS", slots), patch(
        "app.unified_retrieval_service._BRANCH_EXECUTOR.submit",
        side_effect=RuntimeError("executor unavailable"),
    ), patch("app.unified_retrieval_service.db_repositories.save_retrieval_log_to_db"):
        with pytest.raises(UnifiedRetrievalFailure):
            retrieval.search(UnifiedRetrievalRequest(query="executor failure"))
    assert slots.acquired == 2
    assert slots.released == slots.acquired


def test_each_branch_failure_isolated_and_both_failure_is_safe() -> None:
    p1_ok = branch("p1", (candidate("p1", 1),))
    p2_ok = branch("p2", (candidate("p2", 1),))
    p1_error = branch("p1", status="error", fallback_reason="p1_query_error")
    p2_error = branch("p2", status="error", fallback_reason="p2_query_error")
    with patch("app.unified_retrieval_service.db_repositories.save_retrieval_log_to_db"):
        p1_response = service(p1_ok, p2_error).search(
            UnifiedRetrievalRequest(query="p1 survives")
        )
        p2_response = service(
            p1_error, p2_ok, feature_flags=flags(shadow_enabled=False)
        ).search(
            UnifiedRetrievalRequest(query="p2 survives", shadow_mode=False)
        )
    assert p1_response.candidate_mode == "partial_p1"
    assert p2_response.candidate_mode == "partial_p2"
    assert all(item.source_index == "p2" for item in p2_response.results)

    with pytest.raises(UnifiedRetrievalFailure) as caught:
        service(p1_error, p2_error).search(UnifiedRetrievalRequest(query="both fail"))
    assert caught.value.retrieval_id.startswith("unified_retrieval_")
    assert "query_error" in caught.value.reason
    assert "DATABASE_URL" not in caught.value.reason


def test_post_recall_gate_can_remove_archived_race_candidate_before_fusion() -> None:
    p1 = branch("p1", (candidate("p1", 1),))
    p2 = branch("p2", (candidate("p2", 1),))
    with patch("app.unified_retrieval_service.db_repositories.save_retrieval_log_to_db"):
        response = service(
            p1,
            p2,
            p2_filter=lambda _items: (),
            feature_flags=flags(shadow_enabled=False),
        ).search(
            UnifiedRetrievalRequest(query="archived race", shadow_mode=False)
        )
    assert all(item.source_index != "p2" for item in response.candidate_results)
    assert response.source_modes["p2"].result_count == 0
    assert response.source_modes["p2"].fallback_reason == "p2_post_filter_rejected_candidates"


def test_unified_log_is_namespaced_and_contains_no_vectors() -> None:
    captured: list[dict[str, object]] = []

    def capture(_db: object, trace: dict[str, object]) -> None:
        captured.append(trace)

    with patch(
        "app.unified_retrieval_service.db_repositories.save_retrieval_log_to_db",
        side_effect=capture,
    ):
        service(
            branch("p1", (candidate("p1", 1),)),
            branch("p2", (candidate("p2", 1),)),
        ).search(UnifiedRetrievalRequest(query="logging"))
    serialized = str(captured[0])
    unified = captured[0]["unified_retrieval"]
    assert unified["namespace"] == "unified_retrieval_v1"
    assert unified["raw_scores_compared"] is False
    assert "embedding_vector" not in serialized
    assert "API_KEY" not in serialized
    assert "DATABASE_URL" not in serialized


def test_retrieval_log_failure_does_not_break_healthy_unified_result() -> None:
    database = Mock()
    retrieval = UnifiedRetrievalService(
        database,
        p1_adapter=FakeAdapter(branch("p1", (candidate("p1", 1),))),
        p2_adapter=FakeAdapter(branch("p2", (candidate("p2", 1),))),
        flags=flags(shadow_enabled=False),
        p2_post_filter=lambda items: items,
    )
    with patch(
        "app.unified_retrieval_service.db_repositories.save_retrieval_log_to_db",
        side_effect=RuntimeError("safe test log failure"),
    ):
        response = retrieval.search(
            UnifiedRetrievalRequest(query="log failure", shadow_mode=False)
        )
    assert response.candidate_mode == "unified_rrf"
    assert len(response.candidate_results) == 2
    database.rollback.assert_called_once()


def test_api_is_disabled_by_default_and_preserves_correlation_ids(monkeypatch) -> None:
    monkeypatch.setenv("UNIFIED_RETRIEVAL_ENABLED", "false")
    monkeypatch.setenv("P2_RETRIEVAL_ENABLED", "false")
    monkeypatch.setenv("UNIFIED_RETRIEVAL_SHADOW_MODE", "false")
    from app.main import app

    response = TestClient(app).post(
        "/api/v2/retrieval/search",
        json={"query": "safe default", "request_id": "client-request"},
    )
    assert response.status_code == 503
    data = response.json()["data"]
    assert data["retrieval_id"].startswith("unified_retrieval_")
    assert data["request_id"] == "client-request"
    assert data["fallback_used"] is False
    assert data["results"] == []


def test_m82_does_not_modify_sealed_p1_retrieval_files() -> None:
    status = os.popen(
        "git diff --name-only -- backend/app/storage.py backend/app/schemas.py "
        "backend/app/db_models.py backend/app/db_repositories.py"
    ).read()
    assert status.strip() == ""
