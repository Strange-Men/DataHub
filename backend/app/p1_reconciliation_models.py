"""Safe, content-free models for P1 legacy/database reconciliation.

This module deliberately contains no filesystem or database access.  It is
shared by the read-only reconciliation command and the explicit migration
planner so both paths use exactly the same classification rules.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Iterable, Mapping


class Classification(StrEnum):
    EXACT_MATCH = "EXACT_MATCH"
    JSON_ONLY = "JSON_ONLY"
    DB_ONLY = "DB_ONLY"
    CONFLICT = "CONFLICT"
    ORPHAN = "ORPHAN"
    INVALID = "INVALID"
    DB_ONLY_BY_DESIGN = "DB_ONLY_BY_DESIGN"
    # These immutable historical workflow receipts have no lossless P1 table
    # representation.  They remain inventoried legacy input, not runtime truth.
    LEGACY_ONLY_BY_DESIGN = "LEGACY_ONLY_BY_DESIGN"


MIGRATABLE_ENTITIES = frozenset(
    {
        "raw_batch",
        "raw_message",
        "sanitized_batch",
        "sanitized_message",
        "manual_cleaning_record",
        "knowledge_candidate",
        "review_record",
        "rag_chunk",
        "retrieval_log",
        "bad_case",
    }
)

LEGACY_AUDIT_ENTITIES = frozenset(
    {"cleaning_job", "extraction_job", "legacy_rag_import"}
)

DB_ONLY_ENTITIES = frozenset({"rag_embedding"})


PERSISTENCE_MAP: tuple[dict[str, object], ...] = (
    {"entity": "raw_batch", "legacy": "raw_batches", "database": "raw_batches", "mode": "reconciled"},
    {"entity": "raw_message", "legacy": "raw_batches/*.json", "database": "raw_messages", "mode": "reconciled"},
    {"entity": "sanitized_batch", "legacy": "sanitized_batches", "database": "sanitized_batches", "mode": "reconciled"},
    {"entity": "sanitized_message", "legacy": "sanitized_batches/*.json", "database": "sanitized_messages", "mode": "reconciled"},
    {"entity": "cleaning_job", "legacy": "cleaning_jobs", "database": None, "mode": "legacy_audit_only"},
    {"entity": "extraction_job", "legacy": "extraction_jobs", "database": None, "mode": "legacy_audit_only"},
    {"entity": "manual_cleaning_record", "legacy": "manual_cleaning_records", "database": "manual_cleaning_records", "mode": "reconciled"},
    {"entity": "knowledge_candidate", "legacy": "knowledge_candidates", "database": "knowledge_candidates", "mode": "reconciled"},
    {"entity": "review_record", "legacy": "review_records", "database": "review_records", "mode": "reconciled"},
    {"entity": "rag_chunk", "legacy": "rag_chunks", "database": "rag_chunks", "mode": "reconciled"},
    {"entity": "rag_embedding", "legacy": None, "database": "rag_embeddings", "mode": "db_only_by_design"},
    {"entity": "retrieval_log", "legacy": "retrieval_logs", "database": "retrieval_logs", "mode": "reconciled_best_effort_audit"},
    {"entity": "bad_case", "legacy": "bad_cases", "database": "bad_cases", "mode": "reconciled"},
    {"entity": "legacy_rag_import", "legacy": "legacy_rag_imports", "database": None, "mode": "legacy_import_receipt"},
)


@dataclass(frozen=True)
class Record:
    entity: str
    business_id: str
    payload: Mapping[str, Any]
    source: str
    references: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class InvalidRecord:
    entity: str
    source: str
    reason_code: str


@dataclass(frozen=True)
class ReconciliationItem:
    entity: str
    business_id: str
    classification: Classification
    json_hash: str | None = None
    database_hash: str | None = None
    differing_fields: tuple[str, ...] = ()
    reason_code: str | None = None

    def safe_dict(self) -> dict[str, object]:
        return {
            "entity": self.entity,
            "id_hash": short_id_hash(self.business_id),
            "classification": self.classification.value,
            "differing_fields": list(self.differing_fields),
            "json_hash": self.json_hash,
            "database_hash": self.database_hash,
            "reason_code": self.reason_code,
        }


@dataclass
class Inventory:
    records: dict[str, dict[str, Record]] = field(default_factory=dict)
    invalid: list[InvalidRecord] = field(default_factory=list)
    file_count: int = 0
    byte_count: int = 0
    aggregate_hash: str = ""

    def add(self, record: Record) -> None:
        self.records.setdefault(record.entity, {})[record.business_id] = record


@dataclass(frozen=True)
class ReconciliationResult:
    items: tuple[ReconciliationItem, ...]
    persistence_map: tuple[dict[str, object], ...] = PERSISTENCE_MAP

    @property
    def counts(self) -> dict[str, int]:
        counts = {classification.value: 0 for classification in Classification}
        for item in self.items:
            counts[item.classification.value] += 1
        return counts

    @property
    def blockers(self) -> dict[str, int]:
        counts = self.counts
        return {
            key: counts[key]
            for key in ("CONFLICT", "ORPHAN", "INVALID")
        }

    def safe_report(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "persistence_map": list(self.persistence_map),
            "counts": self.counts,
            "blockers": self.blockers,
            "items": [item.safe_dict() for item in self.items],
        }


_UNORDERED_LIST_FIELDS = frozenset(
    {
        "candidate_ids",
        "cleaning_issues",
        "linked_chunk_ids",
        "matched_terms",
        "pii_types",
        "result_chunk_ids",
        "risk_flags",
        "source_chunk_ids",
        "source_message_ids",
        "tags",
    }
)

_NONE_DEFAULTS: dict[str, object] = {
    "candidate_ids": [],
    "cleaning_issues": [],
    "linked_chunk_ids": [],
    "metadata": {},
    "pii_types": [],
    "result_chunk_ids": [],
    "risk_flags": [],
    "source_chunk_ids": [],
    "source_message_ids": [],
    "tags": [],
}


def short_id_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def normalize_timestamp(value: object) -> object:
    if not isinstance(value, str) or not value.strip():
        return value
    candidate = value.strip()
    try:
        parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    except ValueError:
        return candidate
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def canonicalize(value: object, *, field_name: str = "") -> object:
    """Return deterministic JSON-compatible data without discarding business fields."""
    if value is None and field_name in _NONE_DEFAULTS:
        return _NONE_DEFAULTS[field_name]
    if isinstance(value, datetime):
        parsed = value if value.tzinfo else value.replace(tzinfo=UTC)
        return parsed.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
    if isinstance(value, Mapping):
        return {
            str(key): canonicalize(item, field_name=str(key))
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        normalized = [canonicalize(item) for item in value]
        if field_name in _UNORDERED_LIST_FIELDS:
            return sorted(normalized, key=canonical_json)
        return normalized
    if field_name.endswith("_at") or field_name in {"timestamp", "exported_at"}:
        return normalize_timestamp(value)
    if isinstance(value, float):
        return round(value, 12)
    return value


def canonical_json(value: object) -> str:
    return json.dumps(
        canonicalize(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def canonical_hash(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def differing_fields(left: Mapping[str, Any], right: Mapping[str, Any]) -> tuple[str, ...]:
    left_canonical = canonicalize(left)
    right_canonical = canonicalize(right)
    assert isinstance(left_canonical, dict)
    assert isinstance(right_canonical, dict)
    return tuple(
        key
        for key in sorted(set(left_canonical) | set(right_canonical))
        if left_canonical.get(key) != right_canonical.get(key)
    )


def reconcile(
    legacy: Inventory,
    database: Inventory,
) -> ReconciliationResult:
    items: list[ReconciliationItem] = []
    all_legacy_ids = {
        (entity, business_id)
        for entity, records in legacy.records.items()
        for business_id in records
    }

    for invalid in (*legacy.invalid, *database.invalid):
        items.append(
            ReconciliationItem(
                entity=invalid.entity,
                business_id=invalid.source,
                classification=Classification.INVALID,
                reason_code=invalid.reason_code,
            )
        )

    entities = sorted(set(legacy.records) | set(database.records))
    for entity in entities:
        legacy_records = legacy.records.get(entity, {})
        database_records = database.records.get(entity, {})
        for business_id in sorted(set(legacy_records) | set(database_records)):
            json_record = legacy_records.get(business_id)
            db_record = database_records.get(business_id)
            if json_record is not None:
                missing_reference = next(
                    (
                        reference
                        for reference in json_record.references
                        if reference not in all_legacy_ids
                        and reference[0] not in DB_ONLY_ENTITIES
                    ),
                    None,
                )
                if missing_reference is not None:
                    items.append(
                        ReconciliationItem(
                            entity=entity,
                            business_id=business_id,
                            classification=Classification.ORPHAN,
                            json_hash=canonical_hash(json_record.payload),
                            reason_code=f"MISSING_{missing_reference[0].upper()}_REFERENCE",
                        )
                    )
                    continue

            if entity in LEGACY_AUDIT_ENTITIES:
                items.append(
                    ReconciliationItem(
                        entity=entity,
                        business_id=business_id,
                        classification=Classification.LEGACY_ONLY_BY_DESIGN,
                        json_hash=(canonical_hash(json_record.payload) if json_record else None),
                        reason_code="NO_LOSSLESS_P1_TABLE_REPRESENTATION",
                    )
                )
                continue
            if entity in DB_ONLY_ENTITIES:
                items.append(
                    ReconciliationItem(
                        entity=entity,
                        business_id=business_id,
                        classification=Classification.DB_ONLY_BY_DESIGN,
                        database_hash=(canonical_hash(db_record.payload) if db_record else None),
                        reason_code="DATABASE_NATIVE_RUNTIME_ENTITY",
                    )
                )
                continue
            if json_record is None and db_record is not None:
                items.append(
                    ReconciliationItem(
                        entity=entity,
                        business_id=business_id,
                        classification=Classification.DB_ONLY,
                        database_hash=canonical_hash(db_record.payload),
                        reason_code="DATABASE_CREATED_AFTER_LEGACY_SNAPSHOT",
                    )
                )
                continue
            if db_record is None and json_record is not None:
                items.append(
                    ReconciliationItem(
                        entity=entity,
                        business_id=business_id,
                        classification=Classification.JSON_ONLY,
                        json_hash=canonical_hash(json_record.payload),
                    )
                )
                continue
            assert json_record is not None and db_record is not None
            json_hash = canonical_hash(json_record.payload)
            database_hash = canonical_hash(db_record.payload)
            classification = (
                Classification.EXACT_MATCH
                if json_hash == database_hash
                else Classification.CONFLICT
            )
            items.append(
                ReconciliationItem(
                    entity=entity,
                    business_id=business_id,
                    classification=classification,
                    json_hash=json_hash,
                    database_hash=database_hash,
                    differing_fields=(
                        ()
                        if classification is Classification.EXACT_MATCH
                        else differing_fields(json_record.payload, db_record.payload)
                    ),
                )
            )
    return ReconciliationResult(items=tuple(items))


def aggregate_hash(entries: Iterable[tuple[str, str]]) -> str:
    digest = hashlib.sha256()
    for name, item_hash in sorted(entries):
        digest.update(name.replace("\\", "/").encode("utf-8"))
        digest.update(b"\0")
        digest.update(item_hash.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


__all__ = [
    "Classification",
    "DB_ONLY_ENTITIES",
    "InvalidRecord",
    "Inventory",
    "LEGACY_AUDIT_ENTITIES",
    "MIGRATABLE_ENTITIES",
    "PERSISTENCE_MAP",
    "Record",
    "ReconciliationItem",
    "ReconciliationResult",
    "aggregate_hash",
    "canonical_hash",
    "canonical_json",
    "canonicalize",
    "differing_fields",
    "normalize_timestamp",
    "reconcile",
    "short_id_hash",
]
