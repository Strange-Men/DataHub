"""Read-only adapter for historical P1 JSON storage.

Normal P1 runtime code must not import this module.  It exists only for
reconciliation, explicit legacy migration, and isolated tests.  The adapter
never creates directories or index files and never writes legacy storage.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from app.p1_reconciliation_models import (
    InvalidRecord,
    Inventory,
    Record,
    aggregate_hash,
)


_DIRECT_SPECS: dict[str, tuple[str, str]] = {
    "cleaning_jobs": ("cleaning_job", "job_id"),
    "extraction_jobs": ("extraction_job", "job_id"),
    "knowledge_candidates": ("knowledge_candidate", "candidate_id"),
    "review_records": ("review_record", "review_id"),
    "rag_chunks": ("rag_chunk", "chunk_id"),
    "retrieval_logs": ("retrieval_log", "retrieval_id"),
    "bad_cases": ("bad_case", "bad_case_id"),
    "legacy_rag_imports": ("legacy_rag_import", "import_id"),
    "manual_cleaning_records": ("manual_cleaning_record", "record_id"),
}


def _load_json(path: Path) -> object:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _as_dict(value: object) -> dict[str, Any] | None:
    return dict(value) if isinstance(value, Mapping) else None


def _text(value: object) -> str:
    return str(value) if value is not None else ""


def _records_from_index(path: Path) -> tuple[list[dict[str, Any]], InvalidRecord | None]:
    if not path.exists():
        return [], None
    try:
        value = _load_json(path)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return [], InvalidRecord("legacy_index", str(path), "UNREADABLE_OR_INVALID_JSON")
    if not isinstance(value, list) or not all(isinstance(item, Mapping) for item in value):
        return [], InvalidRecord("legacy_index", str(path), "INDEX_MUST_BE_OBJECT_LIST")
    return [dict(item) for item in value], None


def _references(entity: str, payload: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    if entity == "raw_message":
        return (("raw_batch", _text(payload.get("batch_id"))),)
    if entity == "sanitized_batch":
        return (("raw_batch", _text(payload.get("source_batch_id"))),)
    if entity == "sanitized_message":
        return (("sanitized_batch", _text(payload.get("batch_id"))),)
    if entity == "manual_cleaning_record":
        message_id = "__".join(
            (
                _text(payload.get("batch_id")),
                _text(payload.get("conversation_id")),
                _text(payload.get("message_id")),
            )
        )
        return (("sanitized_message", message_id),)
    if entity == "knowledge_candidate":
        source_type = _text(payload.get("source_type"))
        if source_type in {"sanitized_batch", "chat_logs", "public_dataset"}:
            source_id = _text(payload.get("source_batch_id"))
            return (("sanitized_batch", source_id),) if source_id else ()
        if source_type == "bad_case":
            source_id = _text(payload.get("source_bad_case_id"))
            return (("bad_case", source_id),) if source_id else ()
        if source_type == "legacy_rag":
            source_id = _text(payload.get("source_import_id"))
            return (("legacy_rag_import", source_id),) if source_id else ()
    if entity in {"review_record", "rag_chunk"}:
        return (("knowledge_candidate", _text(payload.get("candidate_id"))),)
    if entity == "bad_case":
        retrieval_id = _text(payload.get("retrieval_id"))
        return (("retrieval_log", retrieval_id),) if retrieval_id else ()
    return ()


def _add_record(
    inventory: Inventory,
    entity: str,
    business_id: str,
    payload: Mapping[str, Any],
    source: Path,
) -> None:
    if not business_id:
        inventory.invalid.append(InvalidRecord(entity, str(source), "MISSING_BUSINESS_ID"))
        return
    existing = inventory.records.get(entity, {}).get(business_id)
    record = Record(
        entity=entity,
        business_id=business_id,
        payload=dict(payload),
        source=str(source),
        references=_references(entity, payload),
    )
    if existing is not None and dict(existing.payload) != dict(record.payload):
        inventory.invalid.append(InvalidRecord(entity, str(source), "DUPLICATE_ID_DIFFERENT_PAYLOAD"))
        return
    inventory.add(record)


def _raw_batch_payload(document: Mapping[str, Any]) -> dict[str, Any] | None:
    metadata = _as_dict(document.get("metadata"))
    raw_payload = _as_dict(document.get("raw_payload"))
    if metadata is None or raw_payload is None:
        return None
    conversations = raw_payload.get("conversations")
    if not isinstance(conversations, list):
        return None
    return {
        "batch_id": metadata.get("batch_id"),
        "source_name": metadata.get("source_name", raw_payload.get("source_name")),
        "message_count": metadata.get("message_count"),
        "conversation_count": metadata.get("conversation_count"),
        "created_at": metadata.get("created_at"),
        "status": metadata.get("status", "raw_imported"),
        "conversations": conversations,
    }


def _load_raw_batches(root: Path, inventory: Inventory) -> None:
    directory = root / "raw_batches"
    detail_ids: set[str] = set()
    for path in sorted(directory.glob("*.json")):
        if path.name == "index.json":
            continue
        try:
            value = _load_json(path)
        except (OSError, UnicodeError, json.JSONDecodeError):
            inventory.invalid.append(InvalidRecord("raw_batch", str(path), "UNREADABLE_OR_INVALID_JSON"))
            continue
        document = _as_dict(value)
        payload = _raw_batch_payload(document or {})
        if payload is None:
            inventory.invalid.append(InvalidRecord("raw_batch", str(path), "INVALID_RAW_BATCH_DOCUMENT"))
            continue
        batch_id = _text(payload.get("batch_id"))
        _add_record(inventory, "raw_batch", batch_id, payload, path)
        detail_ids.add(batch_id)
        conversations = payload.get("conversations", [])
        for conversation in conversations if isinstance(conversations, list) else []:
            conversation_dict = _as_dict(conversation)
            if conversation_dict is None:
                inventory.invalid.append(InvalidRecord("raw_message", str(path), "INVALID_CONVERSATION"))
                continue
            conversation_id = _text(conversation_dict.get("conversation_id"))
            messages = conversation_dict.get("messages", [])
            if not isinstance(messages, list):
                inventory.invalid.append(InvalidRecord("raw_message", str(path), "INVALID_MESSAGE_LIST"))
                continue
            for message in messages:
                message_dict = _as_dict(message)
                if message_dict is None:
                    inventory.invalid.append(InvalidRecord("raw_message", str(path), "INVALID_MESSAGE"))
                    continue
                message_id = _text(message_dict.get("message_id"))
                record_id = f"{batch_id}|{conversation_id}|{message_id}"
                message_payload = {
                    "id": record_id,
                    "batch_id": batch_id,
                    "conversation_id": conversation_id,
                    "message_id": message_id,
                    "role": message_dict.get("role"),
                    "content": message_dict.get("content"),
                    "timestamp": message_dict.get("timestamp"),
                    "created_at": payload.get("created_at"),
                }
                _add_record(inventory, "raw_message", record_id, message_payload, path)

    index, invalid = _records_from_index(directory / "index.json")
    if invalid:
        inventory.invalid.append(invalid)
    for item in index:
        batch_id = _text(item.get("batch_id"))
        if batch_id not in detail_ids:
            inventory.invalid.append(InvalidRecord("raw_batch", f"index:{batch_id}", "MISSING_DETAIL_FILE"))


def _sanitized_batch_payload(document: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in document.items()
        if key != "messages"
    }


def _load_sanitized_batches(root: Path, inventory: Inventory) -> None:
    directory = root / "sanitized_batches"
    detail_ids: set[str] = set()
    for path in sorted(directory.glob("*.json")):
        if path.name == "index.json":
            continue
        try:
            value = _load_json(path)
        except (OSError, UnicodeError, json.JSONDecodeError):
            inventory.invalid.append(InvalidRecord("sanitized_batch", str(path), "UNREADABLE_OR_INVALID_JSON"))
            continue
        document = _as_dict(value)
        if document is None or not isinstance(document.get("messages"), list):
            inventory.invalid.append(InvalidRecord("sanitized_batch", str(path), "INVALID_SANITIZED_BATCH_DOCUMENT"))
            continue
        batch_id = _text(document.get("batch_id"))
        _add_record(inventory, "sanitized_batch", batch_id, _sanitized_batch_payload(document), path)
        detail_ids.add(batch_id)
        for message in document["messages"]:
            message_dict = _as_dict(message)
            if message_dict is None:
                inventory.invalid.append(InvalidRecord("sanitized_message", str(path), "INVALID_MESSAGE"))
                continue
            conversation_id = _text(message_dict.get("conversation_id"))
            message_id = _text(message_dict.get("message_id"))
            record_id = f"{batch_id}__{conversation_id}__{message_id}"
            message_payload = {"id": record_id, "batch_id": batch_id, **message_dict}
            message_payload["created_at"] = document.get("created_at")
            _add_record(inventory, "sanitized_message", record_id, message_payload, path)

    index, invalid = _records_from_index(directory / "index.json")
    if invalid:
        inventory.invalid.append(invalid)
    for item in index:
        batch_id = _text(item.get("batch_id"))
        if batch_id not in detail_ids:
            inventory.invalid.append(InvalidRecord("sanitized_batch", f"index:{batch_id}", "MISSING_DETAIL_FILE"))


def _load_direct_directory(
    root: Path,
    directory_name: str,
    entity: str,
    id_field: str,
    inventory: Inventory,
) -> None:
    directory = root / directory_name
    file_ids: set[str] = set()
    for path in sorted(directory.glob("*.json")):
        if path.name == "index.json":
            continue
        try:
            value = _load_json(path)
        except (OSError, UnicodeError, json.JSONDecodeError):
            inventory.invalid.append(InvalidRecord(entity, str(path), "UNREADABLE_OR_INVALID_JSON"))
            continue
        payload = _as_dict(value)
        if payload is None:
            inventory.invalid.append(InvalidRecord(entity, str(path), "JSON_OBJECT_REQUIRED"))
            continue
        business_id = _text(payload.get(id_field))
        _add_record(inventory, entity, business_id, payload, path)
        file_ids.add(business_id)

    index, invalid = _records_from_index(directory / "index.json")
    if invalid:
        inventory.invalid.append(invalid)
    for item in index:
        business_id = _text(item.get(id_field))
        if business_id not in file_ids:
            _add_record(inventory, entity, business_id, item, directory / "index.json")


def load_legacy_inventory(storage_root: Path) -> Inventory:
    """Load historical storage without printing or mutating business content."""
    root = storage_root.resolve()
    inventory = Inventory()
    hash_entries: list[tuple[str, str]] = []
    for path in sorted(root.rglob("*.json")):
        try:
            raw = path.read_bytes()
        except OSError:
            inventory.invalid.append(InvalidRecord("legacy_file", str(path), "UNREADABLE_FILE"))
            continue
        inventory.file_count += 1
        inventory.byte_count += len(raw)
        hash_entries.append((path.relative_to(root).as_posix(), hashlib.sha256(raw).hexdigest()))
    inventory.aggregate_hash = aggregate_hash(hash_entries)

    _load_raw_batches(root, inventory)
    _load_sanitized_batches(root, inventory)
    for directory_name, (entity, id_field) in _DIRECT_SPECS.items():
        _load_direct_directory(root, directory_name, entity, id_field, inventory)
    return inventory


def assert_read_only_adapter() -> None:
    """Marker used by static gates and tests; this module exposes no write API."""


__all__ = ["assert_read_only_adapter", "load_legacy_inventory"]
