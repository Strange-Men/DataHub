"""Read-only P3 eligibility decisions over governed P1/P2 source records."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from enum import Enum
from typing import Any

from pydantic import ValidationError
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db_models import (
    Asset,
    AssetExtraction,
    AssetReviewSnapshot,
    BadCase,
    ExtractionReview,
    KnowledgeAsset,
    KnowledgeCandidate,
    P2KnowledgeIndexEntry,
    ReviewRecord,
)
from app.p3_source_eligibility_schemas import (
    P3SourceEligibilityDecision,
    P3SourceEligibilityReason,
    P3SourceReference,
    P3SourceType,
)


_RAW_BAD_CASE_SOURCE_TYPES = frozenset({"BAD_CASE", "RAW_BAD_CASE"})
_P1_ALLOWED_SOURCE_TYPES = frozenset(
    {
        "sanitized_batch",
        "chat_logs",
        "public_dataset",
        "bad_case",
        "legacy_rag",
        "manual",
    }
)
_P1_FINGERPRINT_FIELDS = (
    "question",
    "answer",
    "intent",
    "tags",
    "risk_level",
    "knowledge_type",
)
_P1_SNAPSHOT_REQUIRED_FIELDS = (
    "candidate_id",
    "source_type",
    *_P1_FINGERPRINT_FIELDS,
)


def _enum_value(value: object) -> object:
    return value.value if isinstance(value, Enum) else value


def _normalized_text(value: object) -> str:
    return str(value or "").strip()


def _normalized_tags(value: object) -> list[str]:
    if not isinstance(value, (list, tuple, set)):
        return []
    return sorted({_normalized_text(item) for item in value if _normalized_text(item)})


def _sha256(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _p1_fingerprint_payload(values: Mapping[str, object]) -> dict[str, object]:
    return {
        "question": _normalized_text(values.get("question")),
        "answer": _normalized_text(values.get("answer")),
        "intent": _normalized_text(values.get("intent")),
        "tags": _normalized_tags(values.get("tags")),
        "risk_level": _normalized_text(values.get("risk_level")),
        "knowledge_type": _normalized_text(values.get("knowledge_type")),
    }


def _p1_candidate_values(row: KnowledgeCandidate) -> dict[str, object]:
    metadata = row.metadata_json if isinstance(row.metadata_json, dict) else {}
    return {
        "question": row.question,
        "answer": row.answer,
        "intent": row.intent,
        "tags": row.tags,
        "risk_level": row.risk_level,
        "knowledge_type": metadata.get("knowledge_type"),
    }


def _p2_content_fingerprint(content_type: object, content: object) -> str:
    return _sha256(
        {
            "content": _normalized_text(content),
            "content_type": _normalized_text(content_type).lower(),
        }
    )


def _decision(
    *,
    source_type: str,
    source_id: str,
    reason_code: P3SourceEligibilityReason,
    source_status: str | None = None,
    source_version: int | None = None,
    content_fingerprint: str | None = None,
    approved_review_id: str | None = None,
    snapshot_id: str | None = None,
    knowledge_asset_id: str | None = None,
    lineage_complete: bool = False,
    checked_conditions: Sequence[str] = (),
) -> P3SourceEligibilityDecision:
    return P3SourceEligibilityDecision(
        source_type=source_type,
        source_id=source_id,
        eligible=reason_code == P3SourceEligibilityReason.ELIGIBLE,
        reason_code=reason_code,
        source_status=source_status,
        source_version=source_version,
        content_fingerprint=content_fingerprint,
        approved_review_id=approved_review_id,
        snapshot_id=snapshot_id,
        knowledge_asset_id=knowledge_asset_id,
        lineage_complete=lineage_complete,
        checked_conditions=list(checked_conditions),
    )


def _raw_reference(source: object) -> tuple[str, str]:
    if isinstance(source, P3SourceReference):
        return source.source_type.value, source.source_id
    if isinstance(source, Mapping):
        return (
            _normalized_text(_enum_value(source.get("source_type"))),
            _normalized_text(source.get("source_id")),
        )
    return "", ""


def _parse_reference(
    source: P3SourceReference | Mapping[str, object],
) -> tuple[P3SourceReference | None, P3SourceEligibilityDecision | None]:
    source_type, source_id = _raw_reference(source)
    if source_type.upper() in _RAW_BAD_CASE_SOURCE_TYPES:
        return None, _decision(
            source_type=source_type,
            source_id=source_id,
            reason_code=P3SourceEligibilityReason.RAW_BAD_CASE_NOT_ALLOWED,
            checked_conditions=("RAW_BAD_CASE_REJECTED",),
        )
    try:
        reference = (
            source
            if isinstance(source, P3SourceReference)
            else P3SourceReference.model_validate(source)
        )
    except (ValidationError, TypeError, ValueError):
        reason = (
            P3SourceEligibilityReason.SOURCE_TYPE_UNSUPPORTED
            if source_type not in {item.value for item in P3SourceType}
            else P3SourceEligibilityReason.SOURCE_STATE_INVALID
        )
        return None, _decision(
            source_type=source_type,
            source_id=source_id,
            reason_code=reason,
            checked_conditions=("REFERENCE_VALIDATION_FAILED",),
        )
    return reference, None


def _latest_p1_review(db: Session, candidate_id: str) -> ReviewRecord | None:
    return (
        db.query(ReviewRecord)
        .filter(ReviewRecord.candidate_id == candidate_id)
        .order_by(ReviewRecord.created_at.desc(), ReviewRecord.id.desc())
        .first()
    )


def _p1_trace_complete(
    candidate: KnowledgeCandidate,
    snapshot: Mapping[str, object],
) -> bool:
    if any(
        field not in snapshot or snapshot.get(field) is None
        for field in _P1_SNAPSHOT_REQUIRED_FIELDS
    ):
        return False
    if snapshot.get("candidate_id") != candidate.id:
        return False
    if snapshot.get("source_type") != candidate.source_type:
        return False

    metadata = candidate.metadata_json if isinstance(candidate.metadata_json, dict) else {}
    source_type = candidate.source_type
    if source_type in {"sanitized_batch", "chat_logs"}:
        required_key = "source_batch_id"
    elif source_type == "public_dataset":
        required_key = "source_import_id"
    elif source_type == "legacy_rag":
        required_key = "source_legacy_id"
    elif source_type == "bad_case":
        required_key = "source_bad_case_id"
    else:
        return bool(candidate.source_id or snapshot.get("source_note"))

    snapshot_value = _normalized_text(snapshot.get(required_key))
    current_value = _normalized_text(metadata.get(required_key))
    return bool(snapshot_value and current_value and snapshot_value == current_value)


def _check_p1(
    db: Session,
    reference: P3SourceReference,
    *,
    bad_case_correction: bool,
) -> P3SourceEligibilityDecision:
    source_type = reference.source_type.value
    candidate = (
        db.query(KnowledgeCandidate)
        .filter(KnowledgeCandidate.id == reference.source_id)
        .first()
    )
    if candidate is None:
        return _decision(
            source_type=source_type,
            source_id=reference.source_id,
            reason_code=P3SourceEligibilityReason.SOURCE_NOT_FOUND,
            checked_conditions=("SOURCE_EXISTS",),
        )

    checked = ["SOURCE_EXISTS"]
    status = _normalized_text(candidate.status)
    metadata = candidate.metadata_json if isinstance(candidate.metadata_json, dict) else {}
    if status == "archived":
        return _decision(
            source_type=source_type,
            source_id=reference.source_id,
            reason_code=P3SourceEligibilityReason.SOURCE_ARCHIVED,
            source_status=status,
            checked_conditions=checked,
        )
    if status == "superseded":
        return _decision(
            source_type=source_type,
            source_id=reference.source_id,
            reason_code=P3SourceEligibilityReason.SOURCE_SUPERSEDED,
            source_status=status,
            checked_conditions=checked,
        )
    if candidate.source_type not in _P1_ALLOWED_SOURCE_TYPES:
        return _decision(
            source_type=source_type,
            source_id=reference.source_id,
            reason_code=P3SourceEligibilityReason.SOURCE_STATE_INVALID,
            source_status=status,
            checked_conditions=checked,
        )
    if bad_case_correction and candidate.source_type != "bad_case":
        return _decision(
            source_type=source_type,
            source_id=reference.source_id,
            reason_code=P3SourceEligibilityReason.SOURCE_STATE_INVALID,
            source_status=status,
            checked_conditions=checked,
        )

    approval_failure = (
        P3SourceEligibilityReason.BAD_CASE_CORRECTION_NOT_APPROVED
        if bad_case_correction
        else P3SourceEligibilityReason.SOURCE_NOT_APPROVED
    )
    if status != "approved":
        return _decision(
            source_type=source_type,
            source_id=reference.source_id,
            reason_code=approval_failure,
            source_status=status,
            checked_conditions=checked,
        )
    checked.append("SOURCE_STATUS_APPROVED")

    review = _latest_p1_review(db, candidate.id)
    if review is None or review.action != "approved":
        return _decision(
            source_type=source_type,
            source_id=reference.source_id,
            reason_code=approval_failure,
            source_status=status,
            approved_review_id=review.id if review is not None else None,
            checked_conditions=checked,
        )
    checked.append("APPROVED_REVIEW_EXISTS")

    snapshot = review.snapshot_json if isinstance(review.snapshot_json, dict) else None
    if snapshot is None or not _p1_trace_complete(candidate, snapshot):
        return _decision(
            source_type=source_type,
            source_id=reference.source_id,
            reason_code=P3SourceEligibilityReason.SOURCE_TRACE_INCOMPLETE,
            source_status=status,
            approved_review_id=review.id,
            checked_conditions=checked,
        )
    checked.append("SOURCE_TRACE_COMPLETE")

    if not _normalized_text(candidate.question) or not _normalized_text(candidate.answer):
        return _decision(
            source_type=source_type,
            source_id=reference.source_id,
            reason_code=P3SourceEligibilityReason.SOURCE_STATE_INVALID,
            source_status=status,
            approved_review_id=review.id,
            lineage_complete=True,
            checked_conditions=checked,
        )

    current_fingerprint = _sha256(_p1_fingerprint_payload(_p1_candidate_values(candidate)))
    reviewed_fingerprint = _sha256(_p1_fingerprint_payload(snapshot))
    if (
        current_fingerprint != reviewed_fingerprint
        or (
            reference.expected_fingerprint is not None
            and current_fingerprint != reference.expected_fingerprint.lower()
        )
    ):
        return _decision(
            source_type=source_type,
            source_id=reference.source_id,
            reason_code=P3SourceEligibilityReason.SOURCE_FINGERPRINT_MISMATCH,
            source_status=status,
            content_fingerprint=current_fingerprint,
            approved_review_id=review.id,
            lineage_complete=True,
            checked_conditions=checked,
        )
    checked.append("CONTENT_FINGERPRINT_MATCH")

    if reference.source_version is not None:
        return _decision(
            source_type=source_type,
            source_id=reference.source_id,
            reason_code=P3SourceEligibilityReason.SOURCE_NOT_CURRENT,
            source_status=status,
            content_fingerprint=current_fingerprint,
            approved_review_id=review.id,
            lineage_complete=True,
            checked_conditions=checked,
        )

    if candidate.source_type == "bad_case":
        bad_case_id = _normalized_text(metadata.get("source_bad_case_id"))
        bad_case = (
            db.query(BadCase).filter(BadCase.id == bad_case_id).first()
            if bad_case_id
            else None
        )
        if bad_case is None:
            return _decision(
                source_type=source_type,
                source_id=reference.source_id,
                reason_code=P3SourceEligibilityReason.SOURCE_TRACE_INCOMPLETE,
                source_status=status,
                content_fingerprint=current_fingerprint,
                approved_review_id=review.id,
                lineage_complete=False,
                checked_conditions=checked,
            )
        if bad_case.status != "resolved" or bad_case.created_candidate_id != candidate.id:
            return _decision(
                source_type=source_type,
                source_id=reference.source_id,
                reason_code=P3SourceEligibilityReason.BAD_CASE_CORRECTION_NOT_APPROVED,
                source_status=status,
                content_fingerprint=current_fingerprint,
                approved_review_id=review.id,
                lineage_complete=True,
                checked_conditions=checked,
            )
        checked.append("BAD_CASE_RESOLUTION_LINK_VALID")

    return _decision(
        source_type=source_type,
        source_id=reference.source_id,
        reason_code=P3SourceEligibilityReason.ELIGIBLE,
        source_status=status,
        content_fingerprint=current_fingerprint,
        approved_review_id=review.id,
        lineage_complete=True,
        checked_conditions=checked,
    )


def _p2_trace_complete(
    knowledge_asset: KnowledgeAsset,
    snapshot: AssetReviewSnapshot | None,
    review: ExtractionReview | None,
    extraction: AssetExtraction | None,
    asset: Asset | None,
) -> bool:
    if any(item is None for item in (snapshot, review, extraction, asset)):
        return False
    assert snapshot is not None
    assert review is not None
    assert extraction is not None
    assert asset is not None
    if not all(
        (
            snapshot.id,
            snapshot.review_id,
            snapshot.extraction_id,
            review.id,
            review.extraction_id,
            extraction.id,
            extraction.job_id,
            asset.id,
            asset.file_name,
            asset.hash,
        )
    ):
        return False
    return bool(
        knowledge_asset.source_snapshot_id == snapshot.id
        and knowledge_asset.asset_id == snapshot.asset_id
        and knowledge_asset.asset_id == review.asset_id
        and knowledge_asset.asset_id == extraction.asset_id
        and knowledge_asset.asset_id == asset.id
        and snapshot.review_id == review.id
        and snapshot.extraction_id == review.extraction_id == extraction.id
    )


def _check_p2(
    db: Session,
    reference: P3SourceReference,
) -> P3SourceEligibilityDecision:
    source_type = reference.source_type.value
    joined = (
        db.query(
            KnowledgeAsset,
            AssetReviewSnapshot,
            ExtractionReview,
            AssetExtraction,
            Asset,
            P2KnowledgeIndexEntry,
        )
        .outerjoin(
            AssetReviewSnapshot,
            AssetReviewSnapshot.id == KnowledgeAsset.source_snapshot_id,
        )
        .outerjoin(ExtractionReview, ExtractionReview.id == AssetReviewSnapshot.review_id)
        .outerjoin(AssetExtraction, AssetExtraction.id == AssetReviewSnapshot.extraction_id)
        .outerjoin(Asset, Asset.id == KnowledgeAsset.asset_id)
        .outerjoin(
            P2KnowledgeIndexEntry,
            P2KnowledgeIndexEntry.knowledge_asset_id == KnowledgeAsset.id,
        )
        .filter(KnowledgeAsset.id == reference.source_id)
        .first()
    )
    if joined is None:
        return _decision(
            source_type=source_type,
            source_id=reference.source_id,
            reason_code=P3SourceEligibilityReason.SOURCE_NOT_FOUND,
            checked_conditions=("SOURCE_EXISTS",),
        )

    knowledge_asset, snapshot, review, extraction, asset, index_entry = joined
    checked = ["SOURCE_EXISTS"]
    status = _normalized_text(knowledge_asset.status)
    version = int(knowledge_asset.version)
    fingerprint = _p2_content_fingerprint(
        knowledge_asset.content_type,
        knowledge_asset.content,
    )
    base = {
        "source_type": source_type,
        "source_id": reference.source_id,
        "source_status": status,
        "source_version": version,
        "content_fingerprint": fingerprint,
        "approved_review_id": review.id if review is not None else None,
        "snapshot_id": snapshot.id if snapshot is not None else None,
        "knowledge_asset_id": knowledge_asset.id,
    }

    if status == "archived":
        return _decision(
            **base,
            reason_code=P3SourceEligibilityReason.SOURCE_ARCHIVED,
            checked_conditions=checked,
        )
    if status == "superseded":
        return _decision(
            **base,
            reason_code=P3SourceEligibilityReason.SOURCE_SUPERSEDED,
            checked_conditions=checked,
        )
    if status != "active":
        return _decision(
            **base,
            reason_code=P3SourceEligibilityReason.SOURCE_STATE_INVALID,
            checked_conditions=checked,
        )
    checked.append("SOURCE_ACTIVE")

    current_version = (
        db.query(func.max(KnowledgeAsset.version))
        .filter(
            KnowledgeAsset.asset_id == knowledge_asset.asset_id,
            KnowledgeAsset.content_type == knowledge_asset.content_type,
        )
        .scalar()
    )
    if (
        current_version is None
        or version != int(current_version)
        or (
            reference.source_version is not None
            and version != reference.source_version
        )
    ):
        return _decision(
            **base,
            reason_code=P3SourceEligibilityReason.SOURCE_NOT_CURRENT,
            checked_conditions=checked,
        )
    checked.append("SOURCE_CURRENT")

    if snapshot is None:
        return _decision(
            **base,
            reason_code=P3SourceEligibilityReason.SOURCE_TRACE_INCOMPLETE,
            checked_conditions=checked,
        )

    if review is None or review.review_status != "approved":
        return _decision(
            **base,
            reason_code=P3SourceEligibilityReason.SOURCE_NOT_APPROVED,
            checked_conditions=checked,
        )
    checked.append("APPROVED_REVIEW_EXISTS")

    lineage_complete = _p2_trace_complete(
        knowledge_asset,
        snapshot,
        review,
        extraction,
        asset,
    )
    if not lineage_complete:
        return _decision(
            **base,
            reason_code=P3SourceEligibilityReason.SOURCE_TRACE_INCOMPLETE,
            checked_conditions=checked,
        )
    checked.append("SOURCE_TRACE_COMPLETE")

    assert snapshot is not None
    snapshot_fingerprint = _p2_content_fingerprint(
        knowledge_asset.content_type,
        snapshot.approved_content,
    )
    if (
        fingerprint != snapshot_fingerprint
        or (
            reference.expected_fingerprint is not None
            and fingerprint != reference.expected_fingerprint.lower()
        )
    ):
        return _decision(
            **base,
            reason_code=P3SourceEligibilityReason.SOURCE_FINGERPRINT_MISMATCH,
            lineage_complete=True,
            checked_conditions=checked,
        )
    checked.append("CONTENT_FINGERPRINT_MATCH")

    if index_entry is not None:
        checked.append(f"INDEX_STATUS_OBSERVED:{index_entry.status}")

    return _decision(
        **base,
        reason_code=P3SourceEligibilityReason.ELIGIBLE,
        lineage_complete=True,
        checked_conditions=checked,
    )


def check_source_eligibility(
    db: Session,
    source: P3SourceReference | Mapping[str, object],
) -> P3SourceEligibilityDecision:
    """Return one deterministic decision without mutating any source record."""

    reference, invalid_decision = _parse_reference(source)
    if invalid_decision is not None:
        return invalid_decision
    assert reference is not None
    if reference.source_type == P3SourceType.P1_KNOWLEDGE:
        return _check_p1(db, reference, bad_case_correction=False)
    if reference.source_type == P3SourceType.APPROVED_BAD_CASE_CORRECTION:
        return _check_p1(db, reference, bad_case_correction=True)
    if reference.source_type == P3SourceType.P2_KNOWLEDGE_ASSET:
        return _check_p2(db, reference)
    return _decision(
        source_type=reference.source_type.value,
        source_id=reference.source_id,
        reason_code=P3SourceEligibilityReason.SOURCE_TYPE_UNSUPPORTED,
        checked_conditions=("SOURCE_TYPE_DISPATCH_FAILED",),
    )


def check_sources_eligibility(
    db: Session,
    sources: Sequence[P3SourceReference | Mapping[str, object]],
) -> list[P3SourceEligibilityDecision]:
    """Evaluate a bounded input sequence once per source while preserving order."""

    return [check_source_eligibility(db, source) for source in sources]
