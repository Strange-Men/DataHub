"""Deterministic, configurable no-answer decisions for P1/P2 retrieval."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import os
from typing import Iterable, Literal

from pydantic import BaseModel, Field


class AnswerabilityConfigurationError(ValueError):
    """Raised when no-answer configuration is unsafe or malformed."""


class AnswerabilityMode(StrEnum):
    DISABLED = "disabled"
    SHADOW = "shadow"
    ENFORCED = "enforced"


class AnswerabilityReason(StrEnum):
    ANSWERABLE = "ANSWERABLE"
    NO_EVIDENCE = "NO_EVIDENCE"
    LOW_RELEVANCE = "LOW_RELEVANCE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"
    ALL_CANDIDATES_FILTERED = "ALL_CANDIDATES_FILTERED"
    QUERY_TOO_AMBIGUOUS = "QUERY_TOO_AMBIGUOUS"
    RETRIEVAL_UNAVAILABLE = "RETRIEVAL_UNAVAILABLE"


class AnswerabilityDecision(BaseModel):
    answerable: bool
    no_answer_reason: AnswerabilityReason
    decision_score: float | None = None
    decision_threshold: float | None = None
    valid_evidence_count: int = Field(ge=0)
    mode: AnswerabilityMode
    abstention_enforced: bool
    decision_signals: dict[str, object] = Field(default_factory=dict)

    @property
    def should_abstain(self) -> bool:
        return self.abstention_enforced and not self.answerable


@dataclass(frozen=True)
class AnswerabilityEvidence:
    score: float
    source: Literal["p1", "p2"]
    valid: bool = True
    conflict_key: str | None = None
    claim_value: str | None = None


@dataclass(frozen=True)
class AnswerabilityConfig:
    mode: AnswerabilityMode = AnswerabilityMode.DISABLED
    p1_min_score: float = 0.45
    p2_min_score: float = 0.55
    unified_min_score: float = 1.0
    min_evidence: int = 1
    ambiguous_query_min_length: int = 4

    @classmethod
    def from_environment(cls) -> "AnswerabilityConfig":
        raw_mode = os.getenv("DATAHUB_NO_ANSWER_MODE", "disabled").strip().lower()
        try:
            mode = AnswerabilityMode(raw_mode)
        except ValueError as exc:
            raise AnswerabilityConfigurationError(
                "DATAHUB_NO_ANSWER_MODE must be disabled, shadow, or enforced."
            ) from exc

        return cls(
            mode=mode,
            p1_min_score=_score("P1_NO_ANSWER_MIN_SCORE", 0.45),
            p2_min_score=_score("P2_NO_ANSWER_MIN_SCORE", 0.55),
            unified_min_score=_score("UNIFIED_NO_ANSWER_MIN_SCORE", 1.0),
            min_evidence=_integer("NO_ANSWER_MIN_EVIDENCE", 1, minimum=1, maximum=20),
            ambiguous_query_min_length=_integer(
                "NO_ANSWER_AMBIGUOUS_QUERY_MIN_LENGTH", 4, minimum=1, maximum=100
            ),
        )

    def threshold_for(self, scope: Literal["p1", "p2", "unified"]) -> float:
        if scope == "p1":
            return self.p1_min_score
        if scope == "p2":
            return self.p2_min_score
        return self.unified_min_score

    def normalize_unified_score(self, source: Literal["p1", "p2"], score: float) -> float:
        """Normalize against a source-local threshold; never compare raw route scores."""

        local_threshold = self.p1_min_score if source == "p1" else self.p2_min_score
        if local_threshold == 0:
            return 1.0 if score >= 0 else 0.0
        return round(max(0.0, min(float(score) / local_threshold, 1.0)), 6)


def _score(name: str, default: float) -> float:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = float(raw)
    except ValueError as exc:
        raise AnswerabilityConfigurationError(f"{name} must be a number from 0 to 1.") from exc
    if not 0 <= value <= 1:
        raise AnswerabilityConfigurationError(f"{name} must be between 0 and 1.")
    return value


def _integer(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise AnswerabilityConfigurationError(f"{name} must be an integer.") from exc
    if not minimum <= value <= maximum:
        raise AnswerabilityConfigurationError(
            f"{name} must be between {minimum} and {maximum}."
        )
    return value


def _has_conflict(evidence: Iterable[AnswerabilityEvidence]) -> bool:
    claims: dict[str, str] = {}
    for item in evidence:
        key = (item.conflict_key or "").strip()
        value = (item.claim_value or "").strip().casefold()
        if not key or not value:
            continue
        previous = claims.setdefault(key, value)
        if previous != value:
            return True
    return False


def evaluate_answerability(
    *,
    query: str,
    evidence: Iterable[AnswerabilityEvidence],
    scope: Literal["p1", "p2", "unified"],
    config: AnswerabilityConfig | None = None,
    filtered_candidate_count: int = 0,
    retrieval_unavailable: bool = False,
) -> AnswerabilityDecision:
    """Evaluate deterministic signals without mutating retrieval candidates."""

    resolved = config or AnswerabilityConfig.from_environment()
    threshold = resolved.threshold_for(scope)
    candidates = list(evidence)
    valid = [item for item in candidates if item.valid]
    ranked = sorted(valid, key=lambda item: float(item.score), reverse=True)
    top_score = float(ranked[0].score) if ranked else None
    second_score = float(ranked[1].score) if len(ranked) > 1 else None
    reliable = [item for item in ranked if float(item.score) >= threshold]
    compact_query = "".join(query.split())

    reason = AnswerabilityReason.ANSWERABLE
    answerable = True
    if len(compact_query) < resolved.ambiguous_query_min_length:
        answerable = False
        reason = AnswerabilityReason.QUERY_TOO_AMBIGUOUS
    elif not candidates:
        answerable = False
        reason = (
            AnswerabilityReason.ALL_CANDIDATES_FILTERED
            if filtered_candidate_count
            else AnswerabilityReason.NO_EVIDENCE
        )
    elif not valid:
        answerable = False
        reason = AnswerabilityReason.ALL_CANDIDATES_FILTERED
    elif top_score is None or top_score < threshold:
        answerable = False
        reason = AnswerabilityReason.LOW_RELEVANCE
    elif len(reliable) < resolved.min_evidence:
        answerable = False
        reason = AnswerabilityReason.INSUFFICIENT_EVIDENCE
    elif _has_conflict(reliable):
        answerable = False
        reason = AnswerabilityReason.CONFLICTING_EVIDENCE

    # A degraded/failed retrieval is operationally distinct from a genuine miss.
    # A healthy branch with sufficient evidence may still answer safely.
    if retrieval_unavailable and not answerable:
        reason = AnswerabilityReason.RETRIEVAL_UNAVAILABLE

    return AnswerabilityDecision(
        answerable=answerable,
        no_answer_reason=reason,
        decision_score=round(top_score, 6) if top_score is not None else None,
        decision_threshold=threshold,
        valid_evidence_count=len(reliable),
        mode=resolved.mode,
        abstention_enforced=resolved.mode == AnswerabilityMode.ENFORCED,
        decision_signals={
            "candidate_count": len(candidates),
            "filtered_candidate_count": filtered_candidate_count,
            "top1_top2_margin": (
                round(top_score - second_score, 6)
                if top_score is not None and second_score is not None
                else None
            ),
            "retrieval_unavailable": retrieval_unavailable,
            "score_semantics": (
                "source_local_threshold_ratio" if scope == "unified" else f"{scope}_native_score"
            ),
        },
    )


SAFE_ABSTENTION_MESSAGE = (
    "当前知识库中没有找到足够可靠的信息，暂时无法准确回答该问题。"
)
