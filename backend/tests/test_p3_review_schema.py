"""Focused P3-M5.1 manual-revision and human-review schema tests."""

from __future__ import annotations

import os
import re
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from sqlalchemy.schema import CreateIndex, CreateTable


ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.database import Base
from app.p3_review_schema_compatibility import (
    ensure_manual_revision_review_compatibility,
)
from app.p3_review_schemas import (
    P3_REVIEW_POLICY_VERSION,
    P3ReviewDecisionPayload,
)
from app.p3_reuse_models import (
    ReuseAssetType,
    ReuseAssetVersion,
    ReuseAssetVersionStatus,
    ReuseGenerationMode,
    ReuseProject,
    ReuseProjectStatus,
    ReuseReview,
    ReuseReviewDecision,
)
from scripts.test_environment import require_test_database_url


TEST_DATABASE_URL = os.getenv("DATAHUB_TEST_DATABASE_URL", "").strip()
FORBIDDEN_TABLES = {"export_jobs", "export_artifacts"}


def _sqlite_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


@pytest.fixture
def sqlite_session():
    engine = _sqlite_engine()
    Base.metadata.create_all(bind=engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session
    engine.dispose()


def _project(project_id: str = "m51_project") -> ReuseProject:
    return ReuseProject(
        id=project_id,
        name="M5.1 review schema",
        status=ReuseProjectStatus.ACTIVE,
        created_by_role="cleaner",
        request_id=f"request_{project_id}",
        idempotency_key=f"key_{project_id}",
    )


def _version(
    *,
    version_id: str,
    project_id: str = "m51_project",
    version_number: int = 1,
    mode: ReuseGenerationMode = ReuseGenerationMode.DETERMINISTIC_TEMPLATE,
    parent_id: str | None = None,
) -> ReuseAssetVersion:
    return ReuseAssetVersion(
        id=version_id,
        project_id=project_id,
        asset_type=ReuseAssetType.TRAINING_MATERIAL,
        version_number=version_number,
        status=ReuseAssetVersionStatus.GENERATED,
        generation_mode=mode,
        template_key="p3.review.schema.v1",
        template_version="v1",
        content_payload={"title": version_id},
        content_hash=("a" if version_number == 1 else "b") * 64,
        source_manifest_hash="c" * 64,
        idempotency_key=f"key_{version_id}",
        created_by_role="cleaner",
        request_id=f"request_{version_id}",
        parent_asset_version_id=parent_id,
    )


def _review(
    *,
    review_id: str,
    version_id: str,
    decision: ReuseReviewDecision = ReuseReviewDecision.APPROVED,
    idempotency_key: str | None = None,
    comments: str | None = None,
) -> ReuseReview:
    if comments is None and decision is not ReuseReviewDecision.APPROVED:
        comments = "Human review requires follow-up."
    return ReuseReview(
        id=review_id,
        asset_version_id=version_id,
        decision=decision,
        comments=comments,
        checklist_payload={
            "structure_complete": decision is ReuseReviewDecision.APPROVED,
            "source_refs_valid": True,
            "no_unsupported_claims_confirmed": True,
            "safe_for_reuse": True,
        },
        review_policy_version=P3_REVIEW_POLICY_VERSION,
        reviewed_content_hash="a" * 64,
        reviewed_source_manifest_hash="c" * 64,
        reviewer_role="reviewer",
        request_id=f"request_{review_id}",
        idempotency_key=idempotency_key or f"key_{review_id}",
    )


@pytest.mark.parametrize(
    "mode",
    (
        ReuseGenerationMode.DETERMINISTIC_TEMPLATE,
        ReuseGenerationMode.LLM_DRAFT,
    ),
)
def test_existing_generation_modes_remain_valid(
    sqlite_session: Session,
    mode: ReuseGenerationMode,
) -> None:
    sqlite_session.add(_project())
    sqlite_session.commit()
    sqlite_session.add(_version(version_id=f"version_{mode.value}", mode=mode))
    sqlite_session.commit()
    assert (
        sqlite_session.get(ReuseAssetVersion, f"version_{mode.value}").generation_mode
        is mode
    )


def test_manual_revision_requires_valid_nonself_parent(
    sqlite_session: Session,
) -> None:
    sqlite_session.add(_project())
    sqlite_session.commit()
    sqlite_session.add(_version(version_id="parent"))
    sqlite_session.commit()
    child = _version(
        version_id="child",
        version_number=2,
        mode=ReuseGenerationMode.MANUAL_REVISION,
        parent_id="parent",
    )
    sqlite_session.add(child)
    sqlite_session.commit()
    assert child.parent_asset_version_id == "parent"

    sqlite_session.add(
        _version(
            version_id="missing_parent",
            version_number=3,
            mode=ReuseGenerationMode.MANUAL_REVISION,
        )
    )
    with pytest.raises(IntegrityError):
        sqlite_session.commit()
    sqlite_session.rollback()

    sqlite_session.add(
        _version(
            version_id="self_parent",
            version_number=3,
            mode=ReuseGenerationMode.MANUAL_REVISION,
            parent_id="self_parent",
        )
    )
    with pytest.raises(IntegrityError):
        sqlite_session.commit()
    sqlite_session.rollback()

    sqlite_session.add(
        _version(
            version_id="unknown_parent",
            version_number=3,
            mode=ReuseGenerationMode.MANUAL_REVISION,
            parent_id="not_found",
        )
    )
    with pytest.raises(IntegrityError):
        sqlite_session.commit()
    sqlite_session.rollback()


@pytest.mark.parametrize("decision", list(ReuseReviewDecision))
def test_all_final_review_decisions_persist(
    sqlite_session: Session,
    decision: ReuseReviewDecision,
) -> None:
    project_id = f"project_{decision.value}"
    version_id = f"version_{decision.value}"
    sqlite_session.add(_project(project_id))
    sqlite_session.commit()
    sqlite_session.add(_version(version_id=version_id, project_id=project_id))
    sqlite_session.commit()
    row = _review(
        review_id=f"review_{decision.value}",
        version_id=version_id,
        decision=decision,
    )
    sqlite_session.add(row)
    sqlite_session.commit()
    assert row.decision is decision


def test_review_decision_and_required_fields_are_constrained(
    sqlite_session: Session,
) -> None:
    sqlite_session.add(_project())
    sqlite_session.commit()
    sqlite_session.add(_version(version_id="version"))
    sqlite_session.commit()
    sqlite_session.add(
        _review(
            review_id="bad_decision",
            version_id="version",
            decision="auto_approved",  # type: ignore[arg-type]
        )
    )
    with pytest.raises(StatementError):
        sqlite_session.commit()
    sqlite_session.rollback()

    for field in (
        "reviewed_content_hash",
        "reviewed_source_manifest_hash",
        "review_policy_version",
    ):
        row = _review(
            review_id=f"blank_{field}",
            version_id="version",
            idempotency_key=f"key_blank_{field}",
        )
        setattr(row, field, "")
        sqlite_session.add(row)
        with pytest.raises(IntegrityError):
            sqlite_session.commit()
        sqlite_session.rollback()


def test_review_uniqueness_and_nonapproval_comments(
    sqlite_session: Session,
) -> None:
    sqlite_session.add(_project())
    sqlite_session.commit()
    sqlite_session.add_all(
        [
            _version(version_id="version_1", version_number=1),
            _version(version_id="version_2", version_number=2),
        ]
    )
    sqlite_session.commit()
    sqlite_session.add(_review(review_id="review_1", version_id="version_1"))
    sqlite_session.commit()

    sqlite_session.add(
        _review(
            review_id="review_duplicate_version",
            version_id="version_1",
            idempotency_key="different_key",
        )
    )
    with pytest.raises(IntegrityError):
        sqlite_session.commit()
    sqlite_session.rollback()

    sqlite_session.add(
        _review(
            review_id="review_duplicate_key",
            version_id="version_2",
            idempotency_key="key_review_1",
        )
    )
    with pytest.raises(IntegrityError):
        sqlite_session.commit()
    sqlite_session.rollback()

    sqlite_session.add(
        _review(
            review_id="missing_comments",
            version_id="version_2",
            decision=ReuseReviewDecision.REJECTED,
            comments=" ",
        )
    )
    with pytest.raises(IntegrityError):
        sqlite_session.commit()
    sqlite_session.rollback()


def test_review_policy_v1_requires_human_confirmation() -> None:
    approved = P3ReviewDecisionPayload.model_validate(
        {
            "decision": "approved",
            "comments": None,
            "checklist": {
                "structure_complete": True,
                "source_refs_valid": True,
                "no_unsupported_claims_confirmed": True,
                "safe_for_reuse": True,
            },
        }
    )
    assert approved.checklist.all_confirmed
    with pytest.raises(ValidationError):
        P3ReviewDecisionPayload.model_validate(
            {
                "decision": "approved",
                "checklist": {
                    "structure_complete": False,
                    "source_refs_valid": True,
                    "no_unsupported_claims_confirmed": True,
                    "safe_for_reuse": True,
                },
            }
        )
    with pytest.raises(ValidationError):
        P3ReviewDecisionPayload.model_validate(
            {
                "decision": "needs_revision",
                "checklist": {
                    "structure_complete": False,
                    "source_refs_valid": True,
                    "no_unsupported_claims_confirmed": True,
                    "safe_for_reuse": True,
                },
            }
        )


def test_parent_and_review_foreign_keys_restrict_physical_delete(
    sqlite_session: Session,
) -> None:
    sqlite_session.add(_project())
    sqlite_session.commit()
    sqlite_session.add(_version(version_id="parent"))
    sqlite_session.commit()
    sqlite_session.add(
        _version(
            version_id="child",
            version_number=2,
            mode=ReuseGenerationMode.MANUAL_REVISION,
            parent_id="parent",
        )
    )
    sqlite_session.add(_review(review_id="review", version_id="parent"))
    sqlite_session.commit()
    sqlite_session.delete(sqlite_session.get(ReuseAssetVersion, "parent"))
    with pytest.raises(IntegrityError):
        sqlite_session.commit()
    sqlite_session.rollback()
    assert sqlite_session.get(ReuseReview, "review") is not None


def test_create_all_is_idempotent_and_only_review_table_is_new() -> None:
    engine = _sqlite_engine()
    try:
        Base.metadata.create_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        tables = set(inspect(engine).get_table_names())
        assert "reuse_reviews" in tables
        assert FORBIDDEN_TABLES.isdisjoint(tables)
        columns = {item["name"] for item in inspect(engine).get_columns("reuse_reviews")}
        assert {
            "id",
            "asset_version_id",
            "decision",
            "comments",
            "checklist_payload",
            "review_policy_version",
            "reviewed_content_hash",
            "reviewed_source_manifest_hash",
            "reviewer_role",
            "request_id",
            "idempotency_key",
            "created_at",
        } == columns
        assert not any(
            marker in column.lower()
            for column in columns
            for marker in ("token", "secret", "password", "email")
        )
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def _legacy_version_values(
    project_id: str,
    version_id: str,
    mode: str,
    version_number: int,
) -> dict[str, object]:
    now = datetime.now(UTC).replace(tzinfo=None)
    return {
        "id": version_id,
        "project_id": project_id,
        "asset_type": ReuseAssetType.TRAINING_MATERIAL.value,
        "version_number": version_number,
        "status": ReuseAssetVersionStatus.GENERATED.value,
        "generation_mode": mode,
        "template_key": "legacy-v1",
        "template_version": "v1",
        "content_payload": {"legacy": version_id},
        "content_hash": ("d" if version_number == 1 else "e") * 64,
        "source_manifest_hash": "f" * 64,
        "idempotency_key": f"key_{version_id}",
        "created_by_role": "cleaner",
        "request_id": f"request_{version_id}",
        "created_at": now,
        "updated_at": now,
        "approved_at": None,
        "published_at": None,
        "superseded_at": None,
        "archived_at": None,
        "failure_code": None,
        "failure_message": None,
    }


def _create_m4_sqlite_schema(engine) -> None:
    ReuseProject.__table__.create(bind=engine)
    ddl = str(CreateTable(ReuseAssetVersion.__table__).compile(engine))
    ddl = re.sub(
        r"^\s*parent_asset_version_id VARCHAR\(200\),\s*$",
        "",
        ddl,
        flags=re.MULTILINE,
    )
    ddl = re.sub(
        r"^\s*CONSTRAINT ck_reuse_asset_versions_manual_parent_required "
        r"CHECK \([^\n]+\),\s*$",
        "",
        ddl,
        flags=re.MULTILINE,
    )
    ddl = re.sub(
        r"^\s*CONSTRAINT ck_reuse_asset_versions_parent_not_self "
        r"CHECK \([^\n]+\),\s*$",
        "",
        ddl,
        flags=re.MULTILINE,
    )
    ddl = re.sub(
        r",\s*CONSTRAINT fk_reuse_asset_versions_parent "
        r"FOREIGN KEY\(parent_asset_version_id\) "
        r"REFERENCES reuse_asset_versions \(id\) ON DELETE RESTRICT",
        "",
        ddl,
    )
    ddl = ddl.replace(
        "generation_mode IN "
        "('deterministic_template', 'llm_draft', 'manual_revision')",
        "generation_mode IN ('deterministic_template', 'llm_draft')",
    )
    assert "parent_asset_version_id" not in ddl
    assert "manual_revision" not in ddl
    with engine.begin() as connection:
        connection.exec_driver_sql(ddl)
        for index in ReuseAssetVersion.__table__.indexes:
            if "parent_asset_version_id" not in {
                column.name for column in index.columns
            }:
                connection.exec_driver_sql(str(CreateIndex(index).compile(engine)))


def test_sqlite_m4_upgrade_preserves_old_rows_and_hashes() -> None:
    engine = _sqlite_engine()
    try:
        _create_m4_sqlite_schema(engine)
        with engine.begin() as connection:
            connection.execute(
                ReuseProject.__table__.insert(),
                {
                    "id": "legacy_project",
                    "name": "Legacy M4 project",
                    "description": None,
                    "status": ReuseProjectStatus.ACTIVE.value,
                    "created_by_role": "cleaner",
                    "request_id": "legacy_project_request",
                    "idempotency_key": "legacy_project_key",
                    "created_at": datetime.now(UTC).replace(tzinfo=None),
                    "updated_at": datetime.now(UTC).replace(tzinfo=None),
                    "archived_at": None,
                },
            )
            connection.execute(
                ReuseAssetVersion.__table__.insert(),
                [
                    _legacy_version_values(
                        "legacy_project",
                        "legacy_deterministic",
                        "deterministic_template",
                        1,
                    ),
                    _legacy_version_values(
                        "legacy_project",
                        "legacy_llm",
                        "llm_draft",
                        2,
                    ),
                ],
            )
        assert ensure_manual_revision_review_compatibility(engine) is True
        assert ensure_manual_revision_review_compatibility(engine) is False
        Base.metadata.create_all(bind=engine)
        with engine.begin() as connection:
            rows = list(
                connection.execute(
                    text(
                        "SELECT id, generation_mode, content_hash, "
                        "source_manifest_hash, parent_asset_version_id "
                        "FROM reuse_asset_versions ORDER BY id"
                    )
                ).tuples()
            )
        assert rows == [
            (
                "legacy_deterministic",
                "deterministic_template",
                "d" * 64,
                "f" * 64,
                None,
            ),
            ("legacy_llm", "llm_draft", "e" * 64, "f" * 64, None),
        ]
        assert "reuse_reviews" in inspect(engine).get_table_names()
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.mark.postgres_integration
@pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="DATAHUB_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
def test_postgresql_m4_upgrade_is_forward_idempotent() -> None:
    url = require_test_database_url(
        TEST_DATABASE_URL,
        development_url=os.getenv("DATAHUB_DEVELOPMENT_DATABASE_URL"),
    )
    admin_engine = create_engine(url, pool_pre_ping=True)
    schema = f"p3m51_{uuid.uuid4().hex[:12]}"
    with admin_engine.begin() as connection:
        connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
    engine = create_engine(
        url,
        pool_pre_ping=True,
        connect_args={"options": f"-csearch_path={schema}"},
    )
    try:
        Base.metadata.create_all(
            bind=engine,
            tables=[
                ReuseProject.__table__,
                ReuseAssetVersion.__table__,
                ReuseReview.__table__,
            ],
        )
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "DROP INDEX ix_reuse_asset_versions_parent_asset_version_id"
            )
            connection.exec_driver_sql(
                "ALTER TABLE reuse_asset_versions "
                f'DROP CONSTRAINT "fk_reuse_asset_versions_parent"'
            )
            connection.exec_driver_sql(
                "ALTER TABLE reuse_asset_versions "
                'DROP CONSTRAINT "ck_reuse_asset_versions_manual_parent_required"'
            )
            connection.exec_driver_sql(
                "ALTER TABLE reuse_asset_versions "
                'DROP CONSTRAINT "ck_reuse_asset_versions_parent_not_self"'
            )
            connection.exec_driver_sql(
                "ALTER TABLE reuse_asset_versions "
                "DROP COLUMN parent_asset_version_id"
            )
            connection.exec_driver_sql(
                "ALTER TABLE reuse_asset_versions "
                'DROP CONSTRAINT "reuse_generation_mode"'
            )
            connection.exec_driver_sql(
                "ALTER TABLE reuse_asset_versions "
                'ADD CONSTRAINT "reuse_generation_mode" '
                "CHECK (generation_mode IN "
                "('deterministic_template', 'llm_draft'))"
            )
            connection.execute(
                ReuseProject.__table__.insert(),
                {
                    "id": "pg_project",
                    "name": "PostgreSQL legacy project",
                    "description": None,
                    "status": ReuseProjectStatus.ACTIVE.value,
                    "created_by_role": "cleaner",
                    "request_id": "pg_project_request",
                    "idempotency_key": "pg_project_key",
                    "created_at": datetime.now(UTC).replace(tzinfo=None),
                    "updated_at": datetime.now(UTC).replace(tzinfo=None),
                    "archived_at": None,
                },
            )
            connection.execute(
                ReuseAssetVersion.__table__.insert(),
                [
                    _legacy_version_values(
                        "pg_project",
                        "pg_deterministic",
                        "deterministic_template",
                        1,
                    ),
                    _legacy_version_values(
                        "pg_project",
                        "pg_llm",
                        "llm_draft",
                        2,
                    ),
                ],
            )
        assert ensure_manual_revision_review_compatibility(engine) is True
        assert ensure_manual_revision_review_compatibility(engine) is False
        columns = {
            item["name"]
            for item in inspect(engine).get_columns("reuse_asset_versions")
        }
        assert "parent_asset_version_id" in columns
        with engine.begin() as connection:
            before = list(
                connection.execute(
                    text(
                        "SELECT id, generation_mode, content_hash "
                        "FROM reuse_asset_versions ORDER BY id"
                    )
                ).tuples()
            )
            connection.execute(
                ReuseAssetVersion.__table__.insert(),
                _legacy_version_values(
                    "pg_project",
                    "pg_parent",
                    "deterministic_template",
                    3,
                ),
            )
            manual_values = _legacy_version_values(
                "pg_project",
                "pg_manual",
                "manual_revision",
                4,
            )
            manual_values["parent_asset_version_id"] = "pg_parent"
            connection.execute(
                ReuseAssetVersion.__table__.insert(),
                manual_values,
            )
        assert before == [
            ("pg_deterministic", "deterministic_template", "d" * 64),
            ("pg_llm", "llm_draft", "e" * 64),
        ]
    finally:
        engine.dispose()
        with admin_engine.begin() as connection:
            connection.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
        admin_engine.dispose()
