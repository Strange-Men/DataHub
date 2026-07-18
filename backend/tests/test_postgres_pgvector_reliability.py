"""Disposable PostgreSQL/pgvector transaction and concurrency gates for M9.4A."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.test_environment import require_test_database_url


TEST_DATABASE_URL = os.getenv("DATAHUB_TEST_DATABASE_URL", "").strip()
pytestmark = [
    pytest.mark.postgres_integration,
    pytest.mark.skipif(
        not TEST_DATABASE_URL,
        reason="DATAHUB_TEST_DATABASE_URL is required for PostgreSQL integration tests",
    ),
]


@pytest.fixture(scope="module")
def pg_engine():
    url = require_test_database_url(
        TEST_DATABASE_URL,
        development_url=os.getenv("DATAHUB_DEVELOPMENT_DATABASE_URL"),
    )
    engine = create_engine(url, pool_pre_ping=True)
    with engine.begin() as connection:
        assert connection.execute(text("SELECT current_database() LIKE '%test%'" )).scalar()
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    yield engine
    engine.dispose()


@pytest.fixture(autouse=True)
def clean_m94a_rows(pg_engine):
    def clean() -> None:
        with pg_engine.begin() as connection:
            test_assets = "SELECT id FROM knowledge_assets WHERE asset_id LIKE 'm94a_%'"
            connection.execute(text(
                "DELETE FROM p2_knowledge_embeddings WHERE id LIKE 'm94a_%' "
                f"OR knowledge_asset_id IN ({test_assets})"
            ))
            connection.execute(text(
                "DELETE FROM p2_knowledge_chunks WHERE id LIKE 'm94a_%' "
                f"OR knowledge_asset_id IN ({test_assets})"
            ))
            connection.execute(text(
                "DELETE FROM p2_knowledge_index_entries WHERE id LIKE 'm94a_%' "
                f"OR knowledge_asset_id IN ({test_assets})"
            ))
            connection.execute(text("DELETE FROM knowledge_assets WHERE asset_id LIKE 'm94a_%'"))
            for table in (
                "asset_review_snapshots",
                "extraction_reviews",
                "asset_extractions",
                "extraction_jobs",
                "assets",
            ):
                connection.execute(text(f"DELETE FROM {table} WHERE id LIKE 'm94a_%'"))

    clean()
    yield
    clean()


def _add_source_trace(session, *, asset_suffix: str, snapshot_suffixes: tuple[str, ...], now) -> None:
    from app.db_models import Asset, AssetExtraction, AssetReviewSnapshot, ExtractionReview

    asset_id = f"m94a_asset_{asset_suffix}"
    extraction_id = f"m94a_extraction_{asset_suffix}"
    session.add(
        Asset(
            id=asset_id,
            asset_type="image",
            file_name=f"{asset_suffix}.png",
            mime_type="image/png",
            size=8,
            storage_uri=f"test://{asset_suffix}",
            hash=f"m94a_{asset_suffix}_{uuid4().hex}",
            status="uploaded",
            created_at=now,
            updated_at=now,
        )
    )
    session.add(
        AssetExtraction(
            id=extraction_id,
            asset_id=asset_id,
            job_id=f"m94a_job_{asset_suffix}",
            extract_type="ocr",
            content="source content",
            version=1,
            created_at=now,
        )
    )
    for version, snapshot_suffix in enumerate(snapshot_suffixes, start=1):
        review_id = f"m94a_review_{snapshot_suffix}"
        session.add(
            ExtractionReview(
                id=review_id,
                asset_id=asset_id,
                extraction_id=extraction_id,
                review_status="approved",
                reviewer="reviewer",
                original_content="source content",
                version=version,
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            AssetReviewSnapshot(
                id=f"m94a_snapshot_{snapshot_suffix}",
                asset_id=asset_id,
                extraction_id=extraction_id,
                review_id=review_id,
                extract_type="ocr",
                original_content="source content",
                approved_content=f"approved {snapshot_suffix}",
                version=version,
                created_at=now,
            )
        )


def test_pgvector_dimension_cosine_and_visibility_filters(pg_engine) -> None:
    schema = f"m94a_vector_{uuid4().hex[:10]}"
    with pg_engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        connection.execute(
            text(
                f'CREATE TABLE "{schema}".items ('
                "id text PRIMARY KEY, status text NOT NULL, fingerprint text NOT NULL, "
                "embedding vector(3) NOT NULL)"
            )
        )
        connection.execute(
            text(
                f'INSERT INTO "{schema}".items (id,status,fingerprint,embedding) VALUES '
                "('active-near','serving','current','[1,0,0]'),"
                "('active-far','serving','current','[0,1,0]'),"
                "('archived','archived','current','[1,0,0]'),"
                "('stale','serving','stale','[1,0,0]')"
            )
        )
    try:
        with pytest.raises(DBAPIError):
            with pg_engine.begin() as connection:
                connection.execute(
                    text(
                        f'INSERT INTO "{schema}".items '
                        "(id,status,fingerprint,embedding) VALUES "
                        "('wrong-dimension','serving','current','[1,0]')"
                    )
                )
        with pg_engine.begin() as connection:
            rows = connection.execute(
                text(
                    f'SELECT id FROM "{schema}".items '
                    "WHERE status='serving' AND fingerprint='current' "
                    "ORDER BY embedding <=> '[1,0,0]'::vector"
                )
            ).scalars().all()
            assert rows == ["active-near", "active-far"]
            assert "archived" not in rows
            assert "stale" not in rows
            assert connection.execute(
                text(f'SELECT count(*) FROM "{schema}".items')
            ).scalar() == 4
    finally:
        with pg_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))


def test_review_snapshot_transaction_rolls_back_final_state(pg_engine) -> None:
    from app.db_models import AssetReviewSnapshot, ExtractionReview
    from app.review_repositories import finalize_extraction_review

    Session = sessionmaker(bind=pg_engine, expire_on_commit=False)
    now = datetime.now(UTC)
    with Session() as session:
        session.add(
            ExtractionReview(
                id="m94a_review",
                asset_id="m94a_asset",
                extraction_id="m94a_extraction",
                review_status="pending",
                original_content="original",
                version=1,
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            AssetReviewSnapshot(
                id="m94a_snapshot_existing",
                asset_id="m94a_asset",
                extraction_id="m94a_extraction",
                review_id="m94a_review",
                extract_type="ocr",
                original_content="original",
                approved_content="existing",
                version=1,
                created_at=now,
            )
        )
        session.commit()
        with pytest.raises(IntegrityError):
            finalize_extraction_review(
                session,
                review_id="m94a_review",
                review_status="approved",
                reviewer="reviewer",
                review_comment=None,
                revised_content=None,
                extract_type="ocr",
                approved_content="new content",
            )
    with Session() as verification:
        review = verification.get(ExtractionReview, "m94a_review")
        assert review is not None and review.review_status == "pending"
        assert verification.query(AssetReviewSnapshot).filter(
            AssetReviewSnapshot.review_id == "m94a_review"
        ).count() == 1


def test_concurrent_publish_and_index_are_idempotent(pg_engine) -> None:
    from app.db_models import KnowledgeAsset, P2KnowledgeIndexEntry
    from app.knowledge_asset_repositories import publish_knowledge_asset
    from app.knowledge_index_repositories import create_pending_index_entry

    Session = sessionmaker(bind=pg_engine, expire_on_commit=False)
    now = datetime.now(UTC)
    with Session() as session:
        _add_source_trace(
            session,
            asset_suffix="publish",
            snapshot_suffixes=("same", "v2", "v3"),
            now=now,
        )
        session.commit()

    def publish(snapshot: str):
        with Session() as session:
            return publish_knowledge_asset(
                session,
                source_snapshot_id=snapshot,
                asset_id="m94a_asset_publish",
                content=f"content {snapshot}",
                content_type="ocr",
                metadata_json={"test_scope": "m94a"},
            )

    with ThreadPoolExecutor(max_workers=4) as executor:
        same = list(executor.map(lambda _: publish("m94a_snapshot_same"), range(4)))
    assert sum(result.created for result in same) == 1

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(publish, ("m94a_snapshot_v2", "m94a_snapshot_v3")))
    with Session() as session:
        assets = session.query(KnowledgeAsset).filter(
            KnowledgeAsset.asset_id == "m94a_asset_publish"
        ).all()
        assert len(assets) == 3
        assert len({item.version for item in assets}) == 3
        active = [item for item in assets if item.status == "active"]
        assert len(active) == 1
        active_id = active[0].id

    def create_index(_value: int):
        with Session() as session:
            return create_pending_index_entry(
                session,
                knowledge_asset_id=active_id,
                generation=1,
                fingerprint="m94a_index_fingerprint",
            )

    with ThreadPoolExecutor(max_workers=4) as executor:
        indexes = list(executor.map(create_index, range(4)))
    assert sum(result.created for result in indexes) == 1
    with Session() as session:
        assert session.query(P2KnowledgeIndexEntry).filter(
            P2KnowledgeIndexEntry.knowledge_asset_id == active_id
        ).count() == 1


def test_projection_embedding_and_serve_archive_fail_safely(pg_engine) -> None:
    from app.db_models import (
        KnowledgeAsset,
        P2KnowledgeChunk,
        P2KnowledgeEmbedding,
        P2KnowledgeIndexEntry,
    )
    from app.knowledge_embedding_repositories import (
        P2EmbeddingActivationError,
        activate_index_serving,
        save_embedding_build,
    )
    from app.knowledge_index_repositories import archive_index_entry, save_projected_chunk

    Session = sessionmaker(bind=pg_engine, expire_on_commit=False)
    now = datetime.now(UTC)
    with Session() as session:
        _add_source_trace(
            session,
            asset_suffix="target",
            snapshot_suffixes=("target",),
            now=now,
        )
        _add_source_trace(
            session,
            asset_suffix="conflict",
            snapshot_suffixes=("conflict",),
            now=now,
        )
        for suffix in ("target", "conflict"):
            session.add(
                KnowledgeAsset(
                    id=f"m94a_ka_{suffix}",
                    source_snapshot_id=f"m94a_snapshot_{suffix}",
                    asset_id=f"m94a_asset_{suffix}",
                    content="content",
                    content_type="ocr",
                    status="active",
                    version=1,
                    created_at=now,
                    updated_at=now,
                )
            )
        session.add_all(
            [
                P2KnowledgeIndexEntry(
                    id="m94a_index_target",
                    knowledge_asset_id="m94a_ka_target",
                    status="building",
                    generation=1,
                    fingerprint="m94a_fp_target",
                    sync_state="building",
                    created_at=now,
                    updated_at=now,
                ),
                P2KnowledgeIndexEntry(
                    id="m94a_index_conflict",
                    knowledge_asset_id="m94a_ka_conflict",
                    status="ready",
                    generation=1,
                    fingerprint="m94a_fp_conflict",
                    sync_state="ready",
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )
        session.add(
            P2KnowledgeChunk(
                id="m94a_chunk_conflict",
                index_entry_id="m94a_index_conflict",
                knowledge_asset_id="m94a_ka_conflict",
                chunk_text="conflict",
                chunk_hash="m94a_hash_conflict",
                chunk_order=0,
                created_at=now,
            )
        )
        session.commit()
        with pytest.raises(IntegrityError):
            save_projected_chunk(
                session,
                index_entry_id="m94a_index_target",
                knowledge_asset_id="m94a_ka_target",
                chunk_id="m94a_chunk_conflict",
                chunk_text="target",
                chunk_hash="m94a_hash_target",
                chunk_order=0,
                metadata_json={"test_scope": "m94a"},
            )
    with Session() as session:
        target = session.get(P2KnowledgeIndexEntry, "m94a_index_target")
        assert target is not None and target.status == "building"
        target.status = "ready"
        target.sync_state = "ready"
        session.add(
            P2KnowledgeChunk(
                id="m94a_chunk_target",
                index_entry_id=target.id,
                knowledge_asset_id=target.knowledge_asset_id,
                chunk_text="target",
                chunk_hash="m94a_hash_target",
                chunk_order=0,
                created_at=now,
            )
        )
        session.add(
            P2KnowledgeEmbedding(
                id="m94a_embedding_conflict",
                index_entry_id="m94a_index_conflict",
                chunk_id="m94a_chunk_conflict",
                knowledge_asset_id="m94a_ka_conflict",
                chunk_text="conflict",
                embedding=[0.0, 1.0, 0.0],
                provider="mock",
                model="mock",
                dimension=3,
                embedding_profile="m94a_profile",
                fingerprint="m94a_embedding_fp_conflict",
                created_at=now,
            )
        )
        session.commit()
        with pytest.raises(IntegrityError):
            save_embedding_build(
                session,
                index_entry_id=target.id,
                rows=[
                    {
                        "id": "m94a_embedding_conflict",
                        "chunk_id": "m94a_chunk_target",
                        "knowledge_asset_id": "m94a_ka_target",
                        "chunk_text": "target",
                        "embedding": [1.0, 0.0, 0.0],
                        "provider": "mock",
                        "model": "mock",
                        "dimension": 3,
                        "embedding_profile": "m94a_profile",
                        "fingerprint": "m94a_embedding_fp_target",
                        "metadata_json": {"test_scope": "m94a"},
                    }
                ],
            )
    with Session() as session:
        target = session.get(P2KnowledgeIndexEntry, "m94a_index_target")
        assert target is not None and target.status == "ready"
        assert session.query(P2KnowledgeEmbedding).filter(
            P2KnowledgeEmbedding.fingerprint == "m94a_embedding_fp_target"
        ).count() == 0
        session.add(
            P2KnowledgeEmbedding(
                id="m94a_embedding_target",
                index_entry_id=target.id,
                chunk_id="m94a_chunk_target",
                knowledge_asset_id="m94a_ka_target",
                chunk_text="target",
                embedding=[1.0, 0.0, 0.0],
                provider="mock",
                model="mock",
                dimension=3,
                embedding_profile="m94a_profile",
                fingerprint="m94a_embedding_fp_target",
                metadata_json={"test_scope": "m94a"},
                created_at=now,
            )
        )
        session.commit()

    barrier = threading.Barrier(2)
    errors: list[type[Exception]] = []

    def serve() -> None:
        with Session() as session:
            barrier.wait(timeout=5)
            try:
                activate_index_serving(
                    session,
                    index_entry_id="m94a_index_target",
                    embedding_profile="m94a_profile",
                    provider="mock",
                    model="mock",
                    dimension=3,
                    expected_fingerprints={"m94a_embedding_fp_target"},
                )
            except P2EmbeddingActivationError as exc:
                errors.append(type(exc))

    def archive() -> None:
        with Session() as session:
            barrier.wait(timeout=5)
            archive_index_entry(session, "m94a_index_target")

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(lambda fn: fn(), (serve, archive)))
    with Session() as session:
        archived = session.get(P2KnowledgeIndexEntry, "m94a_index_target")
        assert archived is not None and archived.status == "archived"
        assert archived.sync_state == "archived"
        assert session.query(P2KnowledgeEmbedding).filter(
            P2KnowledgeEmbedding.index_entry_id == archived.id
        ).count() == 1
        repeated = archive_index_entry(session, archived.id)
        assert repeated.status == "archived"
    assert len(errors) <= 1


def test_database_failure_is_safe_and_connection_recovers(pg_engine) -> None:
    environment = {
        key: value
        for key in ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP")
        if (value := os.environ.get(key)) is not None
    }
    sentinel = "database-password-sentinel"
    unsafe_url = (
        f"postgresql+psycopg2://datahub_test:{sentinel}"
        "@127.0.0.1:1/datahub_test?connect_timeout=1"
    )
    environment.update(
        {
            "PYTHONPATH": str(ROOT / "backend"),
            "DATABASE_URL": unsafe_url,
            "DATAHUB_TEST_DATABASE_URL": unsafe_url,
        }
    )
    code = (
        "import json; from app.database import check_database_connection; "
        "print(json.dumps(check_database_connection(), sort_keys=True))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0
    output = result.stdout + result.stderr
    assert sentinel not in output
    assert unsafe_url not in output
    assert json.loads(result.stdout.strip()) == {
        "backend": "postgresql",
        "enabled": True,
        "status": "error",
    }
    with pg_engine.begin() as connection:
        assert connection.execute(text("SELECT 1")).scalar() == 1
