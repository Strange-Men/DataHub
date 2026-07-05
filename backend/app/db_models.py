"""SQLAlchemy ORM models for DataHub core data tables.

These models define the database schema for P1-M16 Database Foundation.
They are compatible with both SQLite and PostgreSQL.

P1-M21 adds rag_embeddings table for vector RAG foundation.

Round note:
- JSON fields use sa.JSON which works with both SQLite (stored as text) and PostgreSQL (json/jsonb).
- created_at / updated_at use server defaults so they work without application-level timestamps.
- String IDs with indexes (not foreign keys) keep the schema simple and avoid complex migration.
- The embedding column uses Vector type when pgvector is available (PostgreSQL),
  and falls back to Text (JSON-encoded) for SQLite.
"""

import datetime
import os

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.engine import Engine

from app.database import Base, engine

# ── Conditional pgvector Vector type ─────────────────────────────────────────
# When pgvector is installed AND the backend is PostgreSQL, use the native
# Vector type.  Otherwise fall back to Text (JSON-encoded embedding) so
# SQLite and non-pgvector PostgreSQL still work.

_HAS_PGVECTOR = False
try:
    from pgvector.sqlalchemy import Vector  # noqa: F811

    _HAS_PGVECTOR = True
except ImportError:
    Vector = None  # type: ignore[assignment]


def _is_postgresql(eng: Engine | None = None) -> bool:
    """Return True if the connected database is PostgreSQL."""
    target = eng or engine
    try:
        url_str = str(target.url)
        return url_str.startswith("postgresql") or url_str.startswith("postgres")
    except Exception:
        return False


def _embedding_column():
    """Return the appropriate column type for the embedding vector.

    PostgreSQL + pgvector installed → Vector(1536)
    SQLite or pgvector not installed → Text (JSON-encoded list of floats)
    """
    if _HAS_PGVECTOR and _is_postgresql():
        return Column("embedding", Vector(1536), nullable=True)
    else:
        return Column("embedding", Text, nullable=True)


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


class RawBatch(Base):
    __tablename__ = "raw_batches"

    id = Column(String, primary_key=True)
    source_name = Column(String, nullable=False)
    source_type = Column(String, nullable=False, default="chat_logs")
    status = Column(String, nullable=False, default="raw_imported")
    message_count = Column(Integer, nullable=False, default=0)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)


class RawMessage(Base):
    __tablename__ = "raw_messages"

    id = Column(String, primary_key=True)
    batch_id = Column(String, nullable=False, index=True)
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    timestamp = Column(String, nullable=True)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)


class SanitizedBatch(Base):
    __tablename__ = "sanitized_batches"

    id = Column(String, primary_key=True)
    raw_batch_id = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="sanitized")
    message_count = Column(Integer, nullable=False, default=0)
    high_quality_count = Column(Integer, nullable=False, default=0)
    review_recommended_count = Column(Integer, nullable=False, default=0)
    drop_recommended_count = Column(Integer, nullable=False, default=0)
    average_quality_score = Column(Float, nullable=True)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)


class SanitizedMessage(Base):
    __tablename__ = "sanitized_messages"

    id = Column(String, primary_key=True)
    batch_id = Column(String, nullable=False, index=True)
    raw_message_id = Column(String, nullable=True)
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    sanitized_content = Column(Text, nullable=False)
    quality_score = Column(Float, nullable=False, default=1.0)
    quality_level = Column(String, nullable=False, default="high")
    suggested_action = Column(String, nullable=False, default="keep")
    cleaning_issues = Column(JSON, nullable=True)
    risk_flags = Column(JSON, nullable=True)
    pii_entities = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)


class ManualCleaningRecord(Base):
    __tablename__ = "manual_cleaning_records"

    id = Column(String, primary_key=True)
    sanitized_message_id = Column(String, nullable=False, index=True)
    cleaner = Column(String, nullable=False)
    action = Column(String, nullable=False)
    original_content = Column(Text, nullable=False)
    cleaned_content = Column(Text, nullable=True)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)


class KnowledgeCandidate(Base):
    __tablename__ = "knowledge_candidates"

    id = Column(String, primary_key=True)
    source_type = Column(String, nullable=False, default="sanitized_batch")
    source_id = Column(String, nullable=True)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    intent = Column(String, nullable=True)
    tags = Column(JSON, nullable=True)
    risk_level = Column(String, nullable=False, default="medium")
    quality_score = Column(Float, nullable=False, default=0.5)
    status = Column(String, nullable=False, default="pending_review")
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)


class ReviewRecord(Base):
    __tablename__ = "review_records"

    id = Column(String, primary_key=True)
    candidate_id = Column(String, nullable=False, index=True)
    reviewer = Column(String, nullable=False)
    action = Column(String, nullable=False)
    note = Column(Text, nullable=True)
    snapshot_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)


class RagChunk(Base):
    __tablename__ = "rag_chunks"

    id = Column(String, primary_key=True)
    candidate_id = Column(String, nullable=False, index=True)
    chunk_text = Column(Text, nullable=False)
    intent = Column(String, nullable=True)
    tags = Column(JSON, nullable=True)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)


class RetrievalLog(Base):
    __tablename__ = "retrieval_logs"

    id = Column(String, primary_key=True)
    query = Column(Text, nullable=False)
    matched_chunk_ids = Column(JSON, nullable=True)
    response_preview = Column(Text, nullable=True)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)


class BadCase(Base):
    __tablename__ = "bad_cases"

    id = Column(String, primary_key=True)
    retrieval_id = Column(String, nullable=True)
    user_question = Column(Text, nullable=False)
    bad_answer = Column(Text, nullable=True)
    expected_answer = Column(Text, nullable=True)
    status = Column(String, nullable=False, default="open")
    created_candidate_id = Column(String, nullable=True)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)


# ── P1-M21: Vector RAG Foundation ────────────────────────────────────────────


class RagEmbedding(Base):
    """Minimum viable vector knowledge table for semantic RAG.

    - candidate_id must be traceable to knowledge_candidates.
    - source trace must not be lost.
    - modality is reserved (default 'text') for P2 multimodal.
    - The embedding column type is chosen dynamically:
        PostgreSQL + pgvector → Vector(1536)
        SQLite / no pgvector → Text (JSON-encoded)
    """

    __tablename__ = "rag_embeddings"

    id = Column(String, primary_key=True)
    chunk_id = Column(String, nullable=True, index=True)
    candidate_id = Column(String, nullable=False, index=True)
    source_type = Column(String, nullable=False, default="sanitized_batch")
    source_batch_id = Column(String, nullable=True)
    source_message_id = Column(String, nullable=True)
    modality = Column(String, nullable=False, default="text")
    chunk_text = Column(Text, nullable=False)
    metadata_json = Column(JSON, nullable=True)
    # embedding column — dynamically chosen at module load time
    embedding = _embedding_column()
    embedding_provider = Column(String, nullable=True)
    embedding_model = Column(String, nullable=True)
    embedding_dimension = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)
