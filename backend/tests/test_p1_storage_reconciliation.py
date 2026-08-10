from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.database import Base  # noqa: E402
from app import db_models  # noqa: E402
from app.p1_database_inventory import load_database_inventory  # noqa: E402
from app.p1_database_migration import (  # noqa: E402
    MigrationBlocked,
    apply_migration_plan,
    build_migration_plan,
)
from app.p1_legacy_storage import load_legacy_inventory  # noqa: E402
from app.p1_reconciliation_models import (  # noqa: E402
    Classification,
    InvalidRecord,
    Inventory,
    Record,
    canonical_hash,
    reconcile,
)


@pytest.fixture()
def sqlite_session(tmp_path: Path) -> Session:
    engine = create_engine(f"sqlite:///{tmp_path / 'p1-r2-test.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        yield session
    engine.dispose()


def _record(
    entity: str,
    business_id: str,
    payload: dict[str, object],
    *,
    references: tuple[tuple[str, str], ...] = (),
) -> Record:
    return Record(entity, business_id, payload, "fixture", references)


def _raw_fixture() -> Inventory:
    created_at = "2026-08-10T01:02:03Z"
    batch_payload = {
        "batch_id": "batch_1",
        "source_name": "fixture",
        "message_count": 1,
        "conversation_count": 1,
        "created_at": created_at,
        "status": "raw_imported",
        "conversations": [
            {
                "conversation_id": "conv_1",
                "messages": [
                    {
                        "message_id": "msg_1",
                        "role": "customer",
                        "content": "fixture business text",
                        "timestamp": "2026-08-10T01:00:00Z",
                    }
                ],
            }
        ],
    }
    message_payload = {
        "id": "batch_1|conv_1|msg_1",
        "batch_id": "batch_1",
        "conversation_id": "conv_1",
        "message_id": "msg_1",
        "role": "customer",
        "content": "fixture business text",
        "timestamp": "2026-08-10T01:00:00Z",
        "created_at": created_at,
    }
    inventory = Inventory()
    inventory.add(_record("raw_batch", "batch_1", batch_payload))
    inventory.add(
        _record(
            "raw_message",
            "batch_1|conv_1|msg_1",
            message_payload,
            references=(("raw_batch", "batch_1"),),
        )
    )
    return inventory


def test_canonicalization_normalizes_timestamps_unordered_lists_and_none_defaults() -> None:
    left = {
        "created_at": "2026-08-10T09:00:00+08:00",
        "tags": ["b", "a"],
        "risk_flags": None,
    }
    right = {
        "created_at": "2026-08-10T01:00:00Z",
        "tags": ["a", "b"],
        "risk_flags": [],
    }
    assert canonical_hash(left) == canonical_hash(right)


def test_reconciliation_classifies_every_required_state_without_content() -> None:
    legacy = Inventory()
    database = Inventory()
    legacy.add(_record("knowledge_candidate", "exact", {"value": 1}))
    database.add(_record("knowledge_candidate", "exact", {"value": 1}))
    legacy.add(_record("knowledge_candidate", "json", {"value": 2}))
    database.add(_record("knowledge_candidate", "db", {"value": 3}))
    legacy.add(_record("knowledge_candidate", "conflict", {"value": 4}))
    database.add(_record("knowledge_candidate", "conflict", {"value": 5}))
    legacy.add(
        _record(
            "review_record",
            "orphan",
            {"candidate_id": "missing"},
            references=(("knowledge_candidate", "missing"),),
        )
    )
    legacy.add(_record("cleaning_job", "legacy-audit", {"job_id": "legacy-audit"}))
    database.add(_record("rag_embedding", "embedding", {"id": "embedding"}))
    legacy.invalid.append(InvalidRecord("raw_batch", "invalid.json", "INVALID_JSON"))

    result = reconcile(legacy, database)
    counts = result.counts
    assert counts[Classification.EXACT_MATCH.value] == 1
    assert counts[Classification.JSON_ONLY.value] == 1
    assert counts[Classification.DB_ONLY.value] == 1
    assert counts[Classification.CONFLICT.value] == 1
    assert counts[Classification.ORPHAN.value] == 1
    assert counts[Classification.INVALID.value] == 1
    assert counts[Classification.DB_ONLY_BY_DESIGN.value] == 1
    assert counts[Classification.LEGACY_ONLY_BY_DESIGN.value] == 1
    encoded = json.dumps(result.safe_report())
    assert "invalid.json" not in encoded
    assert "legacy-audit" not in encoded


def test_legacy_loader_is_read_only_accepts_windows_paths_and_never_reports_content(
    tmp_path: Path,
) -> None:
    root = tmp_path / "legacy storage"
    raw_dir = root / "raw_batches"
    raw_dir.mkdir(parents=True)
    document = {
        "metadata": {
            "batch_id": "batch_sensitive",
            "source_name": "fixture",
            "message_count": 1,
            "conversation_count": 1,
            "created_at": "2026-08-10T01:02:03Z",
            "status": "raw_imported",
        },
        "raw_payload": {
            "source_name": "fixture",
            "conversations": [
                {
                    "conversation_id": "conv_1",
                    "messages": [
                        {
                            "message_id": "msg_1",
                            "role": "customer",
                            "content": "never print this sensitive fixture",
                            "timestamp": "2026-08-10T01:00:00Z",
                        }
                    ],
                }
            ],
        },
    }
    detail = raw_dir / "batch_sensitive.json"
    detail.write_text(json.dumps(document), encoding="utf-8")
    (raw_dir / "index.json").write_text(
        json.dumps([document["metadata"]]), encoding="utf-8"
    )
    before = hashlib.sha256(detail.read_bytes()).hexdigest()

    inventory = load_legacy_inventory(Path(str(root)))
    result = reconcile(inventory, Inventory())

    assert inventory.file_count == 2
    assert hashlib.sha256(detail.read_bytes()).hexdigest() == before
    assert "batch_sensitive" in inventory.records["raw_batch"]
    assert "never print this sensitive fixture" not in json.dumps(result.safe_report())


def test_plan_is_no_write_and_apply_is_insert_only_and_idempotent(
    sqlite_session: Session,
) -> None:
    legacy = _raw_fixture()
    empty = load_database_inventory(sqlite_session)
    plan = build_migration_plan(legacy, reconcile(legacy, empty))
    assert len(plan.inserts) == 2
    assert sqlite_session.query(db_models.RawBatch).count() == 0
    sqlite_session.rollback()

    assert apply_migration_plan(sqlite_session, plan) == 2
    database = load_database_inventory(sqlite_session)
    result = reconcile(legacy, database)
    assert result.counts[Classification.EXACT_MATCH.value] == 2
    assert result.counts[Classification.JSON_ONLY.value] == 0
    replay = build_migration_plan(legacy, result)
    assert replay.inserts == ()
    sqlite_session.rollback()
    assert apply_migration_plan(sqlite_session, replay) == 0
    assert sqlite_session.query(db_models.RawBatch).count() == 1


def test_conflict_blocks_plan_and_never_overwrites_database(sqlite_session: Session) -> None:
    legacy = _raw_fixture()
    sqlite_session.add(
        db_models.RawBatch(
            id="batch_1",
            source_name="database-value",
            source_type="chat_logs",
            status="raw_imported",
            message_count=0,
            metadata_json={},
        )
    )
    sqlite_session.commit()
    result = reconcile(legacy, load_database_inventory(sqlite_session))
    with pytest.raises(MigrationBlocked):
        build_migration_plan(legacy, result)
    assert sqlite_session.get(db_models.RawBatch, "batch_1").source_name == "database-value"


def test_apply_failure_rolls_back_whole_transaction(sqlite_session: Session) -> None:
    legacy = _raw_fixture()
    plan = build_migration_plan(
        legacy,
        reconcile(legacy, load_database_inventory(sqlite_session)),
    )
    sqlite_session.rollback()

    def fail_on_message(item: object) -> None:
        if getattr(item, "entity") == "raw_message":
            raise RuntimeError("injected failure")

    with pytest.raises(RuntimeError, match="injected failure"):
        apply_migration_plan(sqlite_session, plan, before_insert=fail_on_message)
    assert sqlite_session.query(db_models.RawBatch).count() == 0
    assert sqlite_session.query(db_models.RawMessage).count() == 0


@pytest.mark.postgres_integration
def test_postgres_fixture_requires_explicit_test_database() -> None:
    url = os.getenv("P1_R2_TEST_DATABASE_URL")
    if not url:
        pytest.skip("P1_R2_TEST_DATABASE_URL is not configured")
    assert "test" in url.lower() or "ci" in url.lower()
    engine = create_engine(url)
    factory = sessionmaker(bind=engine)
    with factory() as session:
        legacy = _raw_fixture()
        plan = build_migration_plan(legacy, reconcile(legacy, load_database_inventory(session)))
        session.rollback()
        apply_migration_plan(session, plan)
        assert reconcile(legacy, load_database_inventory(session)).counts[
            Classification.JSON_ONLY.value
        ] == 0
        session.query(db_models.RawMessage).filter(
            db_models.RawMessage.batch_id == "batch_1"
        ).delete()
        session.query(db_models.RawBatch).filter(db_models.RawBatch.id == "batch_1").delete()
        session.commit()
    engine.dispose()
