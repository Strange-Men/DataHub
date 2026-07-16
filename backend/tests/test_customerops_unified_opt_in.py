"""P2-M8.3 gates for the default-off CustomerOpsAgent Unified opt-in."""

from __future__ import annotations

from pathlib import Path
import inspect
import sys
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient


ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.customerops_unified_schemas import CustomerOpsUnifiedRetrievalRequest  # noqa: E402
from app.customerops_unified_service import CustomerOpsUnifiedRetrievalService  # noqa: E402
from app.main import app, retrieve_for_customerops_agent  # noqa: E402
from app.schemas import (  # noqa: E402
    CustomerOpsRetrievalFilters,
    CustomerOpsRetrievalResponse,
    CustomerOpsRetrievalResult,
)
from app.unified_retrieval_adapters import P1RetrievalAdapter  # noqa: E402
from app.unified_retrieval_schemas import (  # noqa: E402
    UnifiedRetrievalLatency,
    UnifiedRetrievalResponse,
    UnifiedRetrievalResult,
    UnifiedRetrievalSourceMode,
)
from app.unified_retrieval_service import UnifiedRetrievalFailure  # noqa: E402


def _p1_result() -> CustomerOpsRetrievalResult:
    return CustomerOpsRetrievalResult(
        score=0.91,
        matched_terms=["warranty"],
        chunk_id="p1-chunk-1",
        candidate_id="p1-candidate-1",
        source_type="knowledge_candidate",
        source_batch_id="batch-1",
        source_conversation_id="conversation-source",
        source_message_ids=["message-1"],
        source_chunk_ids=["p1-chunk-1"],
        knowledge_type="faq",
        intent="product_info",
        tags=["warranty"],
        risk_level="low",
        quality_score=0.97,
        review_status="approved",
        chunk_text="The product warranty lasts two years.",
        build_method="approved_candidate",
        answer="The product warranty lasts two years.",
    )


def _p1_response(
    *, query: str = "How long is the warranty?", top_k: int = 5
) -> CustomerOpsRetrievalResponse:
    return CustomerOpsRetrievalResponse(
        retrieval_id="retrieval_p1_control",
        query=query,
        top_k=top_k,
        retrieval_mode="customerops_vector_retrieval",
        results=[_p1_result()],
        fallback_used=False,
        fallback_reason=None,
        created_at="2026-07-16T00:00:00+00:00",
    )


def _source_mode(source: str) -> UnifiedRetrievalSourceMode:
    return UnifiedRetrievalSourceMode(
        source_index=source,  # type: ignore[arg-type]
        mode=(
            "customerops_vector_retrieval"
            if source == "p1"
            else "p2_vector_retrieval"
        ),
        status="ok",
        result_count=1,
        latency_ms=4.0,
        native_retrieval_id=f"{source}_native_retrieval",
    )


def _unified_response(
    *, candidate_mode: str = "unified_rrf"
) -> UnifiedRetrievalResponse:
    p1 = UnifiedRetrievalResult(
        source_index="p1",
        source_type="knowledge_candidate",
        rank=1,
        fused_score=0.01639344,
        original_rank=1,
        original_score=0.91,
        candidate_id="p1-candidate-1",
        chunk_id="p1-chunk-1",
        evidence_text="The product warranty lasts two years.",
        content_type="faq",
        source_trace={"candidate_id": "p1-candidate-1", "chunk_id": "p1-chunk-1"},
        metadata={"intent": "product_info", "risk_level": "low"},
    )
    p2 = UnifiedRetrievalResult(
        source_index="p2",
        source_type="p2_knowledge_asset",
        rank=2,
        fused_score=0.01612903,
        original_rank=1,
        original_score=0.88,
        knowledge_asset_id="knowledge-active-2",
        chunk_id="p2-chunk-2",
        asset_id="asset-image-2",
        evidence_text="Caption-reviewed warranty label: two years.",
        content_type="caption",
        source_trace={
            "knowledge_asset_id": "knowledge-active-2",
            "snapshot_id": "snapshot-2",
            "review_id": "review-2",
            "extraction_id": "extraction-2",
            "asset_id": "asset-image-2",
        },
        metadata={"index_entry_id": "index-serving-2"},
    )
    candidates = [p1, p2] if candidate_mode == "unified_rrf" else [p1]
    return UnifiedRetrievalResponse(
        retrieval_id="unified_retrieval_active",
        request_id="request-agent-v2",
        query="How long is the warranty?",
        top_k=5,
        sources=["p1", "p2"],
        retrieval_mode=(
            "unified_rrf" if candidate_mode == "unified_rrf" else "partial_p1"
        ),
        control_mode="customerops_vector_retrieval",
        candidate_mode=candidate_mode,
        source_modes={"p1": _source_mode("p1"), "p2": _source_mode("p2")},
        results=candidates,
        control_results=[p1],
        candidate_results=candidates,
        p1_result_count=1,
        p2_result_count=1 if candidate_mode == "unified_rrf" else 0,
        fused_result_count=len(candidates),
        fallback_used=False,
        fallback_reason=None,
        partial=candidate_mode != "unified_rrf",
        source_distribution={"p1": 1, "p2": len(candidates) - 1},
        latency_ms=UnifiedRetrievalLatency(total=9.0, p1=4.0, p2=4.0, fusion=1.0),
        created_at="2026-07-16T00:00:00+00:00",
    )


def _request(strategy: str = "p1", **kwargs: object) -> CustomerOpsUnifiedRetrievalRequest:
    return CustomerOpsUnifiedRetrievalRequest(
        query="How long is the warranty?",
        retrieval_strategy=strategy,  # type: ignore[arg-type]
        request_id="request-agent-v2",
        **kwargs,
    )


def _enable_active_unified(monkeypatch) -> None:
    monkeypatch.setenv("CUSTOMEROPS_UNIFIED_RETRIEVAL_ENABLED", "true")
    monkeypatch.setenv("UNIFIED_RETRIEVAL_ENABLED", "true")
    monkeypatch.setenv("P2_RETRIEVAL_ENABLED", "true")
    monkeypatch.setenv("UNIFIED_RETRIEVAL_SHADOW_MODE", "false")


def test_default_request_stays_on_sealed_p1_mode(monkeypatch) -> None:
    monkeypatch.delenv("CUSTOMEROPS_UNIFIED_RETRIEVAL_ENABLED", raising=False)
    with patch(
        "app.customerops_unified_service.run_customerops_retrieval",
        return_value=_p1_response(),
    ) as legacy, patch(
        "app.customerops_unified_service.UnifiedRetrievalService.search"
    ) as unified:
        response = CustomerOpsUnifiedRetrievalService(Mock()).retrieve(_request())

    legacy.assert_called_once()
    unified.assert_not_called()
    assert response.requested_retrieval_strategy == "p1"
    assert response.actual_retrieval_strategy == "p1"
    assert response.retrieval_mode == "customerops_vector_retrieval"
    assert response.fallback_used is False


def test_flag_off_explicit_opt_in_falls_back_to_p1_with_reason(monkeypatch) -> None:
    monkeypatch.setenv("CUSTOMEROPS_UNIFIED_RETRIEVAL_ENABLED", "false")
    monkeypatch.setenv("UNIFIED_RETRIEVAL_ENABLED", "true")
    monkeypatch.setenv("P2_RETRIEVAL_ENABLED", "true")
    with patch(
        "app.customerops_unified_service.run_customerops_retrieval",
        return_value=_p1_response(),
    ), patch("app.customerops_unified_service.UnifiedRetrievalService.search") as unified:
        response = CustomerOpsUnifiedRetrievalService(Mock()).retrieve(
            _request("unified")
        )

    unified.assert_not_called()
    assert response.actual_retrieval_strategy == "p1"
    assert response.fallback_used is True
    assert response.fallback_reason == "customerops_unified_retrieval_disabled"


def test_flag_on_without_explicit_opt_in_stays_p1(monkeypatch) -> None:
    _enable_active_unified(monkeypatch)
    with patch(
        "app.customerops_unified_service.run_customerops_retrieval",
        return_value=_p1_response(),
    ), patch("app.customerops_unified_service.UnifiedRetrievalService.search") as unified:
        response = CustomerOpsUnifiedRetrievalService(Mock()).retrieve(_request())
    unified.assert_not_called()
    assert response.actual_retrieval_strategy == "p1"
    assert response.retrieval_mode == "customerops_vector_retrieval"


def test_active_flags_plus_explicit_opt_in_returns_fused_evidence(monkeypatch) -> None:
    _enable_active_unified(monkeypatch)
    with patch(
        "app.customerops_unified_service.UnifiedRetrievalService.search",
        return_value=_unified_response(),
    ) as unified, patch(
        "app.customerops_unified_service.run_customerops_retrieval"
    ) as legacy:
        response = CustomerOpsUnifiedRetrievalService(Mock()).retrieve(
            _request("unified")
        )

    unified.assert_called_once()
    legacy.assert_not_called()
    assert response.actual_retrieval_strategy == "unified"
    assert response.retrieval_mode == "customerops_unified_retrieval"
    assert {item.source_index for item in response.results} == {"p1", "p2"}
    p2 = next(item for item in response.results if item.source_index == "p2")
    assert p2.source_trace["asset_id"] == "asset-image-2"
    assert p2.knowledge_asset_id == "knowledge-active-2"
    serialized = response.model_dump_json().lower()
    assert '"embedding":' not in serialized
    assert '"vector":' not in serialized


def test_shadow_flag_cannot_be_mistaken_for_active_opt_in(monkeypatch) -> None:
    _enable_active_unified(monkeypatch)
    monkeypatch.setenv("UNIFIED_RETRIEVAL_SHADOW_MODE", "true")
    with patch(
        "app.customerops_unified_service.run_customerops_retrieval",
        return_value=_p1_response(),
    ), patch("app.customerops_unified_service.UnifiedRetrievalService.search") as unified:
        response = CustomerOpsUnifiedRetrievalService(Mock()).retrieve(
            _request("unified")
        )
    unified.assert_not_called()
    assert response.actual_retrieval_strategy == "p1"
    assert response.fallback_reason == "unified_shadow_mode_active"


def test_unified_failure_safely_falls_back_to_p1(monkeypatch) -> None:
    _enable_active_unified(monkeypatch)
    failure = UnifiedRetrievalFailure(
        retrieval_id="unified_retrieval_failed",
        request_id="request-agent-v2",
        reason="branches_unavailable:p2_branch_error",
    )
    with patch(
        "app.customerops_unified_service.UnifiedRetrievalService.search",
        side_effect=failure,
    ), patch(
        "app.customerops_unified_service.run_customerops_retrieval",
        return_value=_p1_response(),
    ):
        response = CustomerOpsUnifiedRetrievalService(Mock()).retrieve(
            _request("unified")
        )
    assert response.actual_retrieval_strategy == "p1"
    assert response.unified_attempted is True
    assert response.unified_retrieval_id == "unified_retrieval_failed"
    assert response.fallback_used is True
    assert response.fallback_reason == (
        "unified_retrieval_failed:branches_unavailable:p2_branch_error"
    )
    serialized = response.model_dump_json()
    assert "DATABASE_URL" not in serialized
    assert "API_KEY" not in serialized


def test_degraded_single_branch_is_not_used_as_active_agent_unified(monkeypatch) -> None:
    _enable_active_unified(monkeypatch)
    with patch(
        "app.customerops_unified_service.UnifiedRetrievalService.search",
        return_value=_unified_response(candidate_mode="partial_p1"),
    ), patch(
        "app.customerops_unified_service.run_customerops_retrieval",
        return_value=_p1_response(),
    ):
        response = CustomerOpsUnifiedRetrievalService(Mock()).retrieve(
            _request("unified")
        )
    assert response.actual_retrieval_strategy == "p1"
    assert response.fallback_reason == "unified_retrieval_degraded:partial_p1"


def test_p1_only_filters_fail_safe_instead_of_being_silently_dropped(monkeypatch) -> None:
    _enable_active_unified(monkeypatch)
    payload = _request(
        "unified",
        filters=CustomerOpsRetrievalFilters(intent="product_info"),
    )
    with patch(
        "app.customerops_unified_service.run_customerops_retrieval",
        return_value=_p1_response(),
    ) as legacy, patch(
        "app.customerops_unified_service.UnifiedRetrievalService.search"
    ) as unified:
        response = CustomerOpsUnifiedRetrievalService(Mock()).retrieve(payload)
    unified.assert_not_called()
    sent_payload = legacy.call_args.args[0]
    assert sent_payload.filters.intent == "product_info"
    assert response.fallback_reason == "unified_filters_not_supported"


def test_payload_aware_p1_adapter_retains_agent_context() -> None:
    template = _request(
        "unified",
        conversation_id="conversation-agent",
        agent_session_id="session-agent",
    )
    legacy_template = template.model_dump(
        include={"query", "top_k", "filters", "conversation_id", "agent_session_id"}
    )
    from app.schemas import CustomerOpsRetrievalRequest

    adapter = P1RetrievalAdapter(
        request_factory=lambda query, top_k: CustomerOpsRetrievalRequest(
            **{**legacy_template, "query": query, "top_k": top_k}
        )
    )
    with patch(
        "app.unified_retrieval_adapters.run_customerops_retrieval",
        return_value=_p1_response(top_k=20),
    ) as legacy:
        result = adapter.search(query=template.query, top_k=20)
    sent = legacy.call_args.args[0]
    assert sent.conversation_id == "conversation-agent"
    assert sent.agent_session_id == "session-agent"
    assert result.status == "ok"


def test_old_endpoint_and_contract_never_branch_to_unified() -> None:
    source = inspect.getsource(retrieve_for_customerops_agent)
    assert "retrieval_strategy" not in source
    assert "UnifiedRetrieval" not in source

    client = TestClient(app)
    with patch("app.main.run_customerops_retrieval", return_value=_p1_response()) as legacy, patch(
        "app.customerops_unified_service.UnifiedRetrievalService.search"
    ) as unified:
        response = client.post(
            "/api/customer-ops-agent/retrieve",
            headers={"X-DataHub-Client": "CustomerOpsAgent"},
            json={
                "query": "How long is the warranty?",
                "top_k": 5,
                "retrieval_strategy": "unified",
            },
        )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["retrieval_mode"] == "customerops_vector_retrieval"
    assert "requested_retrieval_strategy" not in data
    legacy.assert_called_once()
    unified.assert_not_called()


def test_versioned_route_requires_customerops_header_and_defaults_to_p1() -> None:
    client = TestClient(app)
    denied = client.post(
        "/api/v2/customer-ops-agent/retrieve",
        json={"query": "How long is the warranty?"},
    )
    assert denied.status_code == 401
    assert denied.json()["error"]["code"] == "UNAUTHORIZED_CLIENT"

    with patch(
        "app.customerops_unified_service.run_customerops_retrieval",
        return_value=_p1_response(),
    ):
        allowed = client.post(
            "/api/v2/customer-ops-agent/retrieve",
            headers={"X-DataHub-Client": "CustomerOpsAgent"},
            json={"query": "How long is the warranty?"},
        )
    assert allowed.status_code == 200
    data = allowed.json()["data"]
    assert data["actual_retrieval_strategy"] == "p1"
    assert data["retrieval_mode"] == "customerops_vector_retrieval"


def test_phase_and_default_flag_are_fail_closed() -> None:
    client = TestClient(app)
    assert client.get("/health").json()["p2_phase"] == "P2-M8.3"
    assert "CUSTOMEROPS_UNIFIED_RETRIEVAL_ENABLED=false" in (
        ROOT_DIR / ".env.example"
    ).read_text(encoding="utf-8")
    assert "CUSTOMEROPS_UNIFIED_RETRIEVAL_ENABLED" in (
        ROOT_DIR / "compose.yaml"
    ).read_text(encoding="utf-8")
