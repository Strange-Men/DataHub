import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.schemas import ImportJsonRequest, SourceBatchMetadata


BASE_DIR = Path(__file__).resolve().parent.parent
RAW_BATCH_DIR = BASE_DIR / "storage" / "raw_batches"
INDEX_FILE = RAW_BATCH_DIR / "index.json"


def _ensure_storage() -> None:
    RAW_BATCH_DIR.mkdir(parents=True, exist_ok=True)
    if not INDEX_FILE.exists():
        INDEX_FILE.write_text("[]", encoding="utf-8")


def _read_index() -> list[dict[str, object]]:
    _ensure_storage()
    try:
        data = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return data


def _write_index(items: list[dict[str, object]]) -> None:
    _ensure_storage()
    INDEX_FILE.write_text(
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

    items = _read_index()
    items.append(metadata.model_dump())
    _write_index(items)
    return metadata


def list_raw_batches() -> list[SourceBatchMetadata]:
    return [SourceBatchMetadata(**item) for item in _read_index()]


def get_raw_batch_metadata(batch_id: str) -> SourceBatchMetadata | None:
    for item in _read_index():
        if item.get("batch_id") == batch_id:
            return SourceBatchMetadata(**item)
    return None

