"""M9.4B deterministic no-answer and abstention gate contracts."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.answerability import (
    AnswerabilityConfig,
    AnswerabilityConfigurationError,
    AnswerabilityEvidence,
    AnswerabilityMode,
    AnswerabilityReason,
    SAFE_ABSTENTION_MESSAGE,
    evaluate_answerability,
)


ROOT = Path(__file__).resolve().parents[2]


def _config(**changes: object) -> AnswerabilityConfig:
    defaults: dict[str, object] = {
        "mode": AnswerabilityMode.ENFORCED,
        "p1_min_score": 0.45,
        "p2_min_score": 0.55,
        "unified_min_score": 1.0,
        "min_evidence": 1,
        "ambiguous_query_min_length": 4,
    }
    defaults.update(changes)
    return AnswerabilityConfig(**defaults)  # type: ignore[arg-type]


def test_no_candidates_is_no_evidence() -> None:
    decision = evaluate_answerability(
        query="完全无关的问题", evidence=[], scope="p1", config=_config()
    )
    assert decision.answerable is False
    assert decision.no_answer_reason == AnswerabilityReason.NO_EVIDENCE


def test_low_relevance_candidate_is_rejected() -> None:
    decision = evaluate_answerability(
        query="查询退款政策详情",
        evidence=[AnswerabilityEvidence(score=0.44, source="p1")],
        scope="p1",
        config=_config(),
    )
    assert decision.no_answer_reason == AnswerabilityReason.LOW_RELEVANCE
    assert decision.decision_score == 0.44
    assert decision.decision_threshold == 0.45


def test_minimum_evidence_is_enforced() -> None:
    decision = evaluate_answerability(
        query="查询退款政策详情",
        evidence=[AnswerabilityEvidence(score=0.9, source="p1")],
        scope="p1",
        config=_config(min_evidence=2),
    )
    assert decision.no_answer_reason == AnswerabilityReason.INSUFFICIENT_EVIDENCE


def test_explicit_governed_claim_conflict_is_rejected() -> None:
    decision = evaluate_answerability(
        query="会员退款期限是多少天",
        evidence=[
            AnswerabilityEvidence(
                score=0.9, source="p1", conflict_key="refund_days", claim_value="7"
            ),
            AnswerabilityEvidence(
                score=0.88, source="p2", conflict_key="refund_days", claim_value="14"
            ),
        ],
        scope="unified",
        config=_config(unified_min_score=0.8),
    )
    assert decision.no_answer_reason == AnswerabilityReason.CONFLICTING_EVIDENCE


@pytest.mark.parametrize("filtered_kind", ["archived", "old_version", "ready_not_serving"])
def test_governance_filtered_only_candidates_are_rejected(filtered_kind: str) -> None:
    del filtered_kind
    decision = evaluate_answerability(
        query="查询历史政策内容",
        evidence=[],
        scope="p2",
        config=_config(),
        filtered_candidate_count=1,
    )
    assert decision.no_answer_reason == AnswerabilityReason.ALL_CANDIDATES_FILTERED
    assert decision.valid_evidence_count == 0


@pytest.mark.parametrize(
    ("scope", "score"), [("p1", 0.45), ("p2", 0.55)]
)
def test_source_local_high_quality_evidence_is_answerable(scope: str, score: float) -> None:
    decision = evaluate_answerability(
        query="如何申请订单退款",
        evidence=[AnswerabilityEvidence(score=score, source=scope)],  # type: ignore[arg-type]
        scope=scope,  # type: ignore[arg-type]
        config=_config(),
    )
    assert decision.answerable is True
    assert decision.no_answer_reason == AnswerabilityReason.ANSWERABLE


def test_unified_uses_source_local_normalization_not_rrf_score() -> None:
    config = _config()
    normalized = config.normalize_unified_score("p2", 0.55)
    decision = evaluate_answerability(
        query="如何查看素材来源",
        evidence=[AnswerabilityEvidence(score=normalized, source="p2")],
        scope="unified",
        config=config,
    )
    assert normalized == 1.0
    assert decision.answerable is True
    assert decision.decision_signals["score_semantics"] == "source_local_threshold_ratio"


def test_unified_two_weak_branches_abstain() -> None:
    config = _config()
    decision = evaluate_answerability(
        query="查询不存在的跨域规则",
        evidence=[
            AnswerabilityEvidence(
                score=config.normalize_unified_score("p1", 0.30), source="p1"
            ),
            AnswerabilityEvidence(
                score=config.normalize_unified_score("p2", 0.40), source="p2"
            ),
        ],
        scope="unified",
        config=config,
    )
    assert decision.no_answer_reason == AnswerabilityReason.LOW_RELEVANCE


def test_partial_unified_failure_can_answer_from_reliable_branch() -> None:
    decision = evaluate_answerability(
        query="查询可靠的文本政策",
        evidence=[AnswerabilityEvidence(score=1.0, source="p1")],
        scope="unified",
        config=_config(),
        retrieval_unavailable=True,
    )
    assert decision.answerable is True


def test_retrieval_failure_is_not_reported_as_knowledge_miss() -> None:
    decision = evaluate_answerability(
        query="查询订单政策",
        evidence=[],
        scope="p2",
        config=_config(),
        retrieval_unavailable=True,
    )
    assert decision.no_answer_reason == AnswerabilityReason.RETRIEVAL_UNAVAILABLE


def test_ambiguous_query_has_stable_reason() -> None:
    decision = evaluate_answerability(
        query="退款", evidence=[], scope="p1", config=_config()
    )
    assert decision.no_answer_reason == AnswerabilityReason.QUERY_TOO_AMBIGUOUS


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("DATAHUB_NO_ANSWER_MODE", "automatic"),
        ("P1_NO_ANSWER_MIN_SCORE", "secret"),
        ("P2_NO_ANSWER_MIN_SCORE", "1.1"),
        ("UNIFIED_NO_ANSWER_MIN_SCORE", "-0.1"),
        ("NO_ANSWER_MIN_EVIDENCE", "0"),
        ("NO_ANSWER_AMBIGUOUS_QUERY_MIN_LENGTH", "101"),
    ],
)
def test_invalid_configuration_fails_closed(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(AnswerabilityConfigurationError):
        AnswerabilityConfig.from_environment()


@pytest.mark.parametrize(
    ("mode", "enforced"),
    [("disabled", False), ("shadow", False), ("enforced", True)],
)
def test_compatibility_modes_are_explicit(
    monkeypatch: pytest.MonkeyPatch, mode: str, enforced: bool
) -> None:
    monkeypatch.setenv("DATAHUB_NO_ANSWER_MODE", mode)
    decision = evaluate_answerability(query="无相关证据问题", evidence=[], scope="p1")
    assert decision.answerable is False
    assert decision.abstention_enforced is enforced


def test_legacy_agent_enforced_mode_removes_evidence_and_uses_safe_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import main
    from app.schemas import CustomerOpsRetrievalRequest, CustomerOpsRetrievalResponse

    decision = evaluate_answerability(
        query="超出知识库的问题", evidence=[], scope="p1", config=_config()
    )
    response = CustomerOpsRetrievalResponse.model_construct(
        retrieval_id="retrieval_test",
        query="超出知识库的问题",
        top_k=5,
        retrieval_mode="customerops_keyword_fallback",
        results=[object()],
        fallback_used=False,
        fallback_reason=None,
        created_at="2026-01-01T00:00:00+00:00",
        answerability=decision,
        abstention_message=None,
    )
    monkeypatch.setattr(main, "run_customerops_retrieval", lambda *args: response)
    result = main.retrieve_for_customerops_agent(
        CustomerOpsRetrievalRequest(query="超出知识库的问题"),
        x_datahub_client="CustomerOpsAgent",
    )
    assert result.data["results"] == []
    assert result.data["abstention_message"] == SAFE_ABSTENTION_MESSAGE


def test_frontend_maps_reasons_and_separates_outage_from_no_answer() -> None:
    source = (ROOT / "frontend" / "src" / "pages" / "RetrievalValidation.tsx").read_text(
        encoding="utf-8"
    )
    for value in (
        "未找到相关知识",
        "检索结果相关性不足",
        "有效证据不足",
        "检索证据存在冲突",
        "当前问题信息不足",
        "检索服务暂时不可用",
        "RETRIEVAL_UNAVAILABLE",
    ):
        assert value in source


def test_raw_contracts_are_additive_and_rrf_is_untouched() -> None:
    p1 = (ROOT / "backend" / "app" / "main.py").read_text(encoding="utf-8")
    p2 = (ROOT / "backend" / "app" / "p2_retrieval_schemas.py").read_text(
        encoding="utf-8"
    )
    unified = (ROOT / "backend" / "app" / "unified_retrieval_schemas.py").read_text(
        encoding="utf-8"
    )
    assert '"answerability": answerability.model_dump' in p1
    assert "answerability: AnswerabilityDecision | None" in p2
    assert "answerability: AnswerabilityDecision | None" in unified
    assert "raw_scores_compared" in (ROOT / "backend" / "app" / "unified_retrieval_service.py").read_text(encoding="utf-8")
