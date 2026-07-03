import json
import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.schemas import (
    CleaningJobMetadata,
    ImportJsonRequest,
    SanitizedBatch,
    SanitizedMessage,
    SourceBatchMetadata,
)


BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = BASE_DIR / "storage"
RAW_BATCH_DIR = STORAGE_DIR / "raw_batches"
SANITIZED_BATCH_DIR = STORAGE_DIR / "sanitized_batches"
CLEANING_JOB_DIR = STORAGE_DIR / "cleaning_jobs"
INDEX_FILE = RAW_BATCH_DIR / "index.json"
SANITIZED_INDEX_FILE = SANITIZED_BATCH_DIR / "index.json"
CLEANING_JOB_INDEX_FILE = CLEANING_JOB_DIR / "index.json"

EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE_PATTERN = re.compile(
    r"(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)(?!\w)"
)
ORDER_PATTERN = re.compile(
    r"\b(?:order|order id|order number|订单号)(?:\s+is)?[:#\s-]*[A-Z0-9-]{5,}\b",
    re.IGNORECASE,
)
TRACKING_PATTERN = re.compile(
    r"\b(?:tracking|tracking id|tracking number|物流单号)[:#\s-]*[A-Z]{1,4}[0-9A-Z-]{7,}\b",
    re.IGNORECASE,
)
ADDRESS_PATTERN = re.compile(
    r"\b\d{1,6}\s+[A-Za-z0-9.' -]+(?:street|st|road|rd|avenue|ave|lane|ln|drive|dr|blvd|boulevard)\b(?:,\s*[A-Za-z .-]+){0,3}",
    re.IGNORECASE,
)


def _ensure_storage() -> None:
    RAW_BATCH_DIR.mkdir(parents=True, exist_ok=True)
    SANITIZED_BATCH_DIR.mkdir(parents=True, exist_ok=True)
    CLEANING_JOB_DIR.mkdir(parents=True, exist_ok=True)
    if not INDEX_FILE.exists():
        INDEX_FILE.write_text("[]", encoding="utf-8")
    if not SANITIZED_INDEX_FILE.exists():
        SANITIZED_INDEX_FILE.write_text("[]", encoding="utf-8")
    if not CLEANING_JOB_INDEX_FILE.exists():
        CLEANING_JOB_INDEX_FILE.write_text("[]", encoding="utf-8")


def _read_json_list(path: Path) -> list[dict[str, object]]:
    _ensure_storage()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return data


def _write_json_list(path: Path, items: list[dict[str, object]]) -> None:
    _ensure_storage()
    path.write_text(
        json.dumps(items, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def create_raw_batch(payload: ImportJsonRequest) -> SourceBatchMetadata:
    _ensure_storage()
    batch_id = f"batch_{uuid4().hex[:12]}"
    created_at = datetime.now(UTC).isoformat()
    message_count = sum(len(conversation.messages) for conversation in payload.conversations)
    metadata = SourceBatchMetadata(
        batch_id=batch_id,
        source_name=payload.source_name,
        message_count=message_count,
        conversation_count=len(payload.conversations),
        created_at=created_at,
        status="raw_imported",
    )

    batch_file = RAW_BATCH_DIR / f"{batch_id}.json"
    batch_file.write_text(
        json.dumps(
            {
                "metadata": metadata.model_dump(),
                "raw_payload": payload.model_dump(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    items = _read_json_list(INDEX_FILE)
    items.append(metadata.model_dump())
    _write_json_list(INDEX_FILE, items)
    return metadata


def list_raw_batches() -> list[SourceBatchMetadata]:
    return [SourceBatchMetadata(**item) for item in _read_json_list(INDEX_FILE)]


def get_raw_batch_metadata(batch_id: str) -> SourceBatchMetadata | None:
    for item in _read_json_list(INDEX_FILE):
        if item.get("batch_id") == batch_id:
            return SourceBatchMetadata(**item)
    return None


def get_raw_batch_document(batch_id: str) -> dict[str, object] | None:
    _ensure_storage()
    batch_file = RAW_BATCH_DIR / f"{batch_id}.json"
    if not batch_file.exists():
        return None
    try:
        data = json.loads(batch_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return data


def _standardize_role(value: object) -> tuple[str, list[str]]:
    role = str(value or "system").strip().lower()
    notes: list[str] = []
    role_map = {
        "customer": "customer",
        "user": "customer",
        "client": "customer",
        "agent": "agent",
        "assistant": "agent",
        "support": "agent",
        "system": "system",
    }
    standardized = role_map.get(role, "system")
    if standardized != role:
        notes.append("role_standardized")
    return standardized, notes


def _mask_pii(content: str) -> tuple[str, list[str]]:
    masked = content
    pii_types: list[str] = []

    replacements = [
        ("EMAIL", EMAIL_PATTERN, "[EMAIL]"),
        ("TRACKING_ID", TRACKING_PATTERN, "[TRACKING_ID]"),
        ("ORDER_ID", ORDER_PATTERN, "[ORDER_ID]"),
        ("ADDRESS", ADDRESS_PATTERN, "[ADDRESS]"),
        ("PHONE", PHONE_PATTERN, "[PHONE]"),
    ]

    for pii_type, pattern, replacement in replacements:
        masked, count = pattern.subn(replacement, masked)
        if count > 0:
            pii_types.append(pii_type)

    return masked, pii_types


def _safe_message_id(conversation_index: int, message_index: int, message: dict[str, object]) -> str:
    value = str(message.get("message_id") or "").strip()
    if value:
        return value
    return f"msg_missing_{conversation_index + 1}_{message_index + 1}"


def run_cleaning(batch_id: str) -> CleaningJobMetadata | None:
    raw_document = get_raw_batch_document(batch_id)
    if raw_document is None:
        return None

    raw_payload = raw_document.get("raw_payload")
    if not isinstance(raw_payload, dict):
        return None

    conversations = raw_payload.get("conversations")
    if not isinstance(conversations, list):
        return None

    created_at = datetime.now(UTC).isoformat()
    job_id = f"clean_job_{uuid4().hex[:12]}"
    raw_message_count = 0
    dropped_message_count = 0
    sanitized_messages: list[SanitizedMessage] = []

    for conversation_index, conversation in enumerate(conversations):
        if not isinstance(conversation, dict):
            continue
        conversation_id = str(
            conversation.get("conversation_id")
            or f"conv_missing_{conversation_index + 1}"
        ).strip()
        messages = conversation.get("messages")
        if not isinstance(messages, list):
            continue

        for message_index, message in enumerate(messages):
            if not isinstance(message, dict):
                continue
            raw_message_count += 1
            notes: list[str] = []
            raw_content = str(message.get("content") or "")
            content = raw_content.strip()
            if raw_content != content:
                notes.append("content_trimmed")
            if not content:
                dropped_message_count += 1
                continue

            role, role_notes = _standardize_role(message.get("role"))
            notes.extend(role_notes)
            message_id = _safe_message_id(conversation_index, message_index, message)
            source_message_id = str(message.get("message_id") or message_id).strip() or message_id
            masked_content, pii_types = _mask_pii(content)
            if pii_types:
                notes.append("pii_masked")

            sanitized_messages.append(
                SanitizedMessage(
                    source_batch_id=batch_id,
                    conversation_id=conversation_id,
                    message_id=message_id,
                    source_message_id=source_message_id,
                    role=role,  # type: ignore[arg-type]
                    content=masked_content,
                    pii_detected=bool(pii_types),
                    pii_types=pii_types,
                    cleaning_notes=notes,
                )
            )

    completed_at = datetime.now(UTC).isoformat()
    pii_detected_count = sum(1 for message in sanitized_messages if message.pii_detected)
    sanitized_batch = SanitizedBatch(
        batch_id=batch_id,
        source_batch_id=batch_id,
        status="sanitized",
        raw_message_count=raw_message_count,
        sanitized_message_count=len(sanitized_messages),
        dropped_message_count=dropped_message_count,
        pii_detected_count=pii_detected_count,
        created_at=completed_at,
        messages=sanitized_messages,
    )
    job = CleaningJobMetadata(
        job_id=job_id,
        source_batch_id=batch_id,
        sanitized_batch_id=batch_id,
        raw_message_count=raw_message_count,
        sanitized_message_count=len(sanitized_messages),
        dropped_message_count=dropped_message_count,
        pii_detected_count=pii_detected_count,
        status="completed",
        created_at=created_at,
        completed_at=completed_at,
    )

    _ensure_storage()
    (SANITIZED_BATCH_DIR / f"{batch_id}.json").write_text(
        json.dumps(sanitized_batch.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (CLEANING_JOB_DIR / f"{job_id}.json").write_text(
        json.dumps(job.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    sanitized_items = [
        item for item in _read_json_list(SANITIZED_INDEX_FILE)
        if item.get("batch_id") != batch_id
    ]
    sanitized_items.append(
        {
            "batch_id": sanitized_batch.batch_id,
            "source_batch_id": sanitized_batch.source_batch_id,
            "status": sanitized_batch.status,
            "raw_message_count": sanitized_batch.raw_message_count,
            "sanitized_message_count": sanitized_batch.sanitized_message_count,
            "dropped_message_count": sanitized_batch.dropped_message_count,
            "pii_detected_count": sanitized_batch.pii_detected_count,
            "created_at": sanitized_batch.created_at,
        }
    )
    _write_json_list(SANITIZED_INDEX_FILE, sanitized_items)

    job_items = _read_json_list(CLEANING_JOB_INDEX_FILE)
    job_items.append(job.model_dump())
    _write_json_list(CLEANING_JOB_INDEX_FILE, job_items)
    return job


def get_cleaning_job(job_id: str) -> CleaningJobMetadata | None:
    _ensure_storage()
    job_file = CLEANING_JOB_DIR / f"{job_id}.json"
    if not job_file.exists():
        return None
    try:
        data = json.loads(job_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return CleaningJobMetadata(**data)


def get_sanitized_batch(batch_id: str) -> SanitizedBatch | None:
    _ensure_storage()
    batch_file = SANITIZED_BATCH_DIR / f"{batch_id}.json"
    if not batch_file.exists():
        return None
    try:
        data = json.loads(batch_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return SanitizedBatch(**data)
