"""Deterministic JSONL and CSV serializers for governed P3 payloads."""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from typing import Any, Iterable

from pydantic import ValidationError

from app.p3_asset_schemas import ASSET_PAYLOAD_SCHEMAS
from app.p3_export_models import P3ExportFormat
from app.p3_reuse_models import ReuseAssetType


class P3ExportSerializationError(RuntimeError):
    """Payload or serialization failure with no sensitive content."""


@dataclass(frozen=True)
class P3SerializedExport:
    content: bytes
    row_count: int
    content_type: str
    encoding: str
    extension: str


_CSV_COLUMNS: dict[ReuseAssetType, tuple[str, ...]] = {
    ReuseAssetType.TRAINING_MATERIAL: (
        "title",
        "heading",
        "content",
        "learning_objectives",
        "key_points",
        "source_refs",
    ),
    ReuseAssetType.SOP: (
        "title",
        "purpose",
        "scope",
        "prerequisites",
        "step_order",
        "instruction",
        "cautions",
        "escalation_rules",
        "source_refs",
    ),
    ReuseAssetType.SERVICE_SCRIPT: (
        "title",
        "scenario",
        "opening",
        "step_order",
        "response",
        "prohibited_claims",
        "escalation",
        "source_refs",
    ),
    ReuseAssetType.QA_BANK: (
        "question",
        "answer",
        "source_refs",
    ),
    ReuseAssetType.SFT_DATASET: (
        "instruction",
        "input",
        "output",
        "metadata",
        "source_refs",
    ),
}


def canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise P3ExportSerializationError(
            "Export value is not canonical JSON."
        ) from exc


def _refs(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise P3ExportSerializationError("Export source references are invalid.")
    return [dict(item) for item in value if isinstance(item, dict)]


def _records(
    asset_type: ReuseAssetType,
    payload: dict[str, Any],
) -> list[dict[str, Any]]:
    if asset_type is ReuseAssetType.TRAINING_MATERIAL:
        return [
            {
                "title": payload["title"],
                "heading": section["heading"],
                "content": section["content"],
                "learning_objectives": payload["learning_objectives"],
                "key_points": payload["key_points"],
                "source_refs": _refs(section["source_refs"]),
            }
            for section in payload["sections"]
        ]
    if asset_type is ReuseAssetType.SOP:
        return [
            {
                "title": payload["title"],
                "purpose": payload["purpose"],
                "scope": payload["scope"],
                "prerequisites": payload["prerequisites"],
                "step_order": step["order"],
                "instruction": step["instruction"],
                "cautions": payload["cautions"],
                "escalation_rules": payload["escalation_rules"],
                "source_refs": _refs(step["source_refs"]),
            }
            for step in payload["steps"]
        ]
    if asset_type is ReuseAssetType.SERVICE_SCRIPT:
        return [
            {
                "title": payload["title"],
                "scenario": payload["scenario"],
                "opening": payload["opening"],
                "step_order": step["order"],
                "response": step["response"],
                "prohibited_claims": payload["prohibited_claims"],
                "escalation": payload["escalation"],
                "source_refs": _refs(step["source_refs"]),
            }
            for step in payload["response_steps"]
        ]
    if asset_type is ReuseAssetType.QA_BANK:
        return [
            {
                "question": item["question"],
                "answer": item["answer"],
                "source_refs": _refs(item["source_refs"]),
            }
            for item in payload["items"]
        ]
    if asset_type is ReuseAssetType.SFT_DATASET:
        return [
            {
                "instruction": record["instruction"],
                "input": record["input"],
                "output": record["output"],
                "metadata": record["metadata"],
                "source_refs": _refs(record["source_refs"]),
            }
            for record in payload["records"]
        ]
    raise P3ExportSerializationError("Asset type is not exportable.")


def _validated_records(
    asset_type: ReuseAssetType,
    content_payload: object,
) -> list[dict[str, Any]]:
    schema = ASSET_PAYLOAD_SCHEMAS.get(asset_type)
    if schema is None:
        raise P3ExportSerializationError("Asset type is not exportable.")
    try:
        parsed = schema.model_validate(content_payload)
    except ValidationError as exc:
        raise P3ExportSerializationError(
            "Asset payload is invalid for export."
        ) from exc
    payload = parsed.model_dump(mode="json")
    records = _records(asset_type, payload)
    if not records:
        raise P3ExportSerializationError(
            "Asset payload has no exportable records."
        )
    return records


def _csv_value(value: object) -> object:
    if isinstance(value, (dict, list)):
        return canonical_json(value)
    return value


def _serialize_jsonl(records: Iterable[dict[str, Any]]) -> bytes:
    return (
        "".join(f"{canonical_json(record)}\n" for record in records)
    ).encode("utf-8")


def _serialize_csv(
    asset_type: ReuseAssetType,
    records: Iterable[dict[str, Any]],
) -> bytes:
    columns = _CSV_COLUMNS[asset_type]
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream,
        fieldnames=list(columns),
        extrasaction="raise",
        lineterminator="\r\n",
    )
    writer.writeheader()
    for record in records:
        writer.writerow({column: _csv_value(record[column]) for column in columns})
    return ("\ufeff" + stream.getvalue()).encode("utf-8")


def serialize_asset_payload(
    *,
    asset_type: ReuseAssetType,
    content_payload: object,
    export_format: P3ExportFormat,
) -> P3SerializedExport:
    if not isinstance(asset_type, ReuseAssetType):
        raise P3ExportSerializationError("Asset type is not exportable.")
    if not isinstance(export_format, P3ExportFormat):
        raise P3ExportSerializationError("Export format is unsupported.")
    records = _validated_records(asset_type, content_payload)
    try:
        if export_format is P3ExportFormat.JSONL:
            content = _serialize_jsonl(records)
            return P3SerializedExport(
                content=content,
                row_count=len(records),
                content_type="application/x-ndjson",
                encoding="utf-8",
                extension="jsonl",
            )
        content = _serialize_csv(asset_type, records)
        return P3SerializedExport(
            content=content,
            row_count=len(records),
            content_type="text/csv; charset=utf-8",
            encoding="utf-8-sig",
            extension="csv",
        )
    except (csv.Error, KeyError, TypeError, ValueError) as exc:
        raise P3ExportSerializationError(
            "Asset serialization failed."
        ) from exc


__all__ = [
    "P3ExportSerializationError",
    "P3SerializedExport",
    "canonical_json",
    "serialize_asset_payload",
]
