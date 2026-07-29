"""P3 reuse-project, governed-source, and draft-asset SQLAlchemy models.

P3 models reference P1/P2 governance records only by stable IDs and immutable
evidence. They never add foreign keys or columns to P1/P2 tables.
"""

from __future__ import annotations

import datetime
from enum import Enum

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    Computed,
    DateTime,
    Enum as SqlEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
    text,
)

from app.database import Base
from app.p3_source_eligibility_schemas import P3SourceType


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _enum_values(enum_type: type[Enum]) -> list[str]:
    """Persist string enum values rather than Python member names."""

    return [str(member.value) for member in enum_type]


class ReuseProjectStatus(str, Enum):
    """Stable P3 project lifecycle states."""

    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class ReuseAssetType(str, Enum):
    """Frozen P3 v1 output asset types."""

    TRAINING_MATERIAL = "training_material"
    SOP = "sop"
    SERVICE_SCRIPT = "service_script"
    QA_BANK = "qa_bank"
    SFT_DATASET = "sft_dataset"


class ReuseAssetVersionStatus(str, Enum):
    """Frozen lifecycle states for one immutable asset version."""

    GENERATING = "generating"
    GENERATED = "generated"
    PENDING_REVIEW = "pending_review"
    NEEDS_REVISION = "needs_revision"
    APPROVED = "approved"
    PUBLISHED = "published"
    REJECTED = "rejected"
    FAILED = "failed"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"


class ReuseGenerationMode(str, Enum):
    """Stable generation modes supported by governed draft assets."""

    DETERMINISTIC_TEMPLATE = "deterministic_template"
    LLM_DRAFT = "llm_draft"
    MANUAL_REVISION = "manual_revision"


class ReuseReviewDecision(str, Enum):
    """Final human decisions recorded for one asset version."""

    APPROVED = "approved"
    NEEDS_REVISION = "needs_revision"
    REJECTED = "rejected"


class ReuseProject(Base):
    """Governance container for one P3 data-asset reuse effort."""

    __tablename__ = "reuse_projects"
    __table_args__ = (
        CheckConstraint(
            "length(trim(name)) > 0",
            name="ck_reuse_projects_name_not_blank",
        ),
        UniqueConstraint(
            "idempotency_key",
            name="uq_reuse_projects_idempotency_key",
        ),
    )

    id = Column(String(200), primary_key=True)
    name = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(
        SqlEnum(
            ReuseProjectStatus,
            name="reuse_project_status",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=_enum_values,
        ),
        nullable=False,
        default=ReuseProjectStatus.DRAFT.value,
        index=True,
    )
    created_by_role = Column(String(50), nullable=False)
    request_id = Column(String(200), nullable=False)
    idempotency_key = Column(String(200), nullable=False)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)
    archived_at = Column(DateTime, nullable=True)


class ReuseSourceItem(Base):
    """Immutable evidence for one governed source selected into a project."""

    __tablename__ = "reuse_source_items"
    __table_args__ = (
        CheckConstraint(
            "length(trim(source_id)) > 0",
            name="ck_reuse_source_items_source_id_not_blank",
        ),
        CheckConstraint(
            "source_version IS NULL OR source_version >= 1",
            name="ck_reuse_source_items_source_version_positive",
        ),
        CheckConstraint(
            "length(trim(source_fingerprint)) > 0",
            name="ck_reuse_source_items_fingerprint_not_blank",
        ),
        CheckConstraint(
            "length(trim(eligibility_policy_version)) > 0",
            name="ck_reuse_source_items_policy_not_blank",
        ),
        UniqueConstraint(
            "project_id",
            "source_type",
            "source_id",
            "source_version_key",
            name="uq_reuse_source_items_project_source_version",
        ),
    )

    id = Column(String(200), primary_key=True)
    project_id = Column(
        String(200),
        ForeignKey("reuse_projects.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    source_type = Column(
        SqlEnum(
            P3SourceType,
            name="p3_source_type",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=_enum_values,
        ),
        nullable=False,
        index=True,
    )
    source_id = Column(String(200), nullable=False)
    source_version = Column(Integer, nullable=True)
    # SQL UNIQUE treats NULL values differently across engines.  A generated
    # zero sentinel makes an unversioned source deterministic without asking
    # callers or a future repository to maintain a duplicate key column.
    source_version_key = Column(
        Integer,
        Computed("COALESCE(source_version, 0)", persisted=True),
    )
    source_fingerprint = Column(String(128), nullable=False)
    eligibility_policy_version = Column(String(100), nullable=False)
    approved_review_id = Column(String(200), nullable=True)
    snapshot_id = Column(String(200), nullable=True)
    knowledge_asset_id = Column(String(200), nullable=True)
    lineage_manifest_hash = Column(String(128), nullable=True)
    source_trace = Column(JSON, nullable=False)
    selected_by_role = Column(String(50), nullable=False)
    request_id = Column(String(200), nullable=False)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    removed_at = Column(DateTime, nullable=True)
    source_stale = Column(
        Boolean,
        nullable=False,
        default=False,
        server_default=false(),
    )


class ReuseAssetVersion(Base):
    """Versioned P3 asset payload created from a frozen source manifest."""

    __tablename__ = "reuse_asset_versions"
    __table_args__ = (
        CheckConstraint(
            "version_number >= 1",
            name="ck_reuse_asset_versions_version_positive",
        ),
        CheckConstraint(
            "length(trim(template_key)) > 0",
            name="ck_reuse_asset_versions_template_key_not_blank",
        ),
        CheckConstraint(
            "length(trim(template_version)) > 0",
            name="ck_reuse_asset_versions_template_version_not_blank",
        ),
        CheckConstraint(
            "length(trim(content_hash)) > 0",
            name="ck_reuse_asset_versions_content_hash_not_blank",
        ),
        CheckConstraint(
            "length(trim(source_manifest_hash)) > 0",
            name="ck_reuse_asset_versions_source_manifest_hash_not_blank",
        ),
        CheckConstraint(
            "generation_mode != 'manual_revision' "
            "OR parent_asset_version_id IS NOT NULL",
            name="ck_reuse_asset_versions_manual_parent_required",
        ),
        CheckConstraint(
            "parent_asset_version_id IS NULL OR parent_asset_version_id != id",
            name="ck_reuse_asset_versions_parent_not_self",
        ),
        UniqueConstraint(
            "project_id",
            "asset_type",
            "version_number",
            name="uq_reuse_asset_versions_project_type_version",
        ),
        UniqueConstraint(
            "idempotency_key",
            name="uq_reuse_asset_versions_idempotency_key",
        ),
        UniqueConstraint(
            "publish_idempotency_key",
            name="uq_reuse_asset_versions_publish_idempotency_key",
        ),
        UniqueConstraint(
            "archive_idempotency_key",
            name="uq_reuse_asset_versions_archive_idempotency_key",
        ),
        Index(
            "uq_reuse_asset_versions_current_published",
            "project_id",
            "asset_type",
            unique=True,
            sqlite_where=text("status = 'published'"),
            postgresql_where=text("status = 'published'"),
        ),
    )

    id = Column(String(200), primary_key=True)
    project_id = Column(
        String(200),
        ForeignKey("reuse_projects.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    asset_type = Column(
        SqlEnum(
            ReuseAssetType,
            name="reuse_asset_type",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=_enum_values,
        ),
        nullable=False,
        index=True,
    )
    version_number = Column(Integer, nullable=False)
    status = Column(
        SqlEnum(
            ReuseAssetVersionStatus,
            name="reuse_asset_version_status",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=_enum_values,
        ),
        nullable=False,
        default=ReuseAssetVersionStatus.GENERATING.value,
        index=True,
    )
    generation_mode = Column(
        SqlEnum(
            ReuseGenerationMode,
            name="reuse_generation_mode",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=_enum_values,
        ),
        nullable=False,
        default=ReuseGenerationMode.DETERMINISTIC_TEMPLATE.value,
    )
    template_key = Column(String(200), nullable=False)
    template_version = Column(String(100), nullable=False)
    content_payload = Column(JSON, nullable=False)
    content_hash = Column(String(128), nullable=False)
    source_manifest_hash = Column(String(128), nullable=False)
    idempotency_key = Column(String(200), nullable=False)
    created_by_role = Column(String(50), nullable=False)
    request_id = Column(String(200), nullable=False)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)
    approved_at = Column(DateTime, nullable=True)
    published_at = Column(DateTime, nullable=True)
    superseded_at = Column(DateTime, nullable=True)
    archived_at = Column(DateTime, nullable=True)
    published_by_role = Column(String(50), nullable=True)
    publish_request_id = Column(String(200), nullable=True)
    publish_idempotency_key = Column(String(200), nullable=True)
    superseded_by_asset_version_id = Column(
        String(200),
        ForeignKey(
            "reuse_asset_versions.id",
            ondelete="RESTRICT",
            name="fk_reuse_asset_versions_superseded_by",
        ),
        nullable=True,
        index=True,
    )
    archived_by_role = Column(String(50), nullable=True)
    archive_request_id = Column(String(200), nullable=True)
    archive_idempotency_key = Column(String(200), nullable=True)
    failure_code = Column(String(100), nullable=True)
    failure_message = Column(Text, nullable=True)
    parent_asset_version_id = Column(
        String(200),
        ForeignKey(
            "reuse_asset_versions.id",
            ondelete="RESTRICT",
            name="fk_reuse_asset_versions_parent",
        ),
        nullable=True,
        index=True,
    )


class ReuseAssetVersionSource(Base):
    """Immutable source-evidence snapshot bound to one asset version."""

    __tablename__ = "reuse_asset_version_sources"
    __table_args__ = (
        CheckConstraint(
            "length(trim(source_id)) > 0",
            name="ck_reuse_asset_version_sources_source_id_not_blank",
        ),
        CheckConstraint(
            "source_version IS NULL OR source_version >= 1",
            name="ck_reuse_asset_version_sources_version_positive",
        ),
        CheckConstraint(
            "length(trim(source_fingerprint)) > 0",
            name="ck_reuse_asset_version_sources_fingerprint_not_blank",
        ),
        CheckConstraint(
            "length(trim(lineage_manifest_hash)) > 0",
            name="ck_reuse_asset_version_sources_lineage_hash_not_blank",
        ),
        UniqueConstraint(
            "asset_version_id",
            "source_item_id",
            name="uq_reuse_asset_version_sources_version_source",
        ),
    )

    id = Column(String(200), primary_key=True)
    asset_version_id = Column(
        String(200),
        ForeignKey("reuse_asset_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    source_item_id = Column(
        String(200),
        ForeignKey("reuse_source_items.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    source_type = Column(
        SqlEnum(
            P3SourceType,
            name="p3_asset_version_source_type",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=_enum_values,
        ),
        nullable=False,
    )
    source_id = Column(String(200), nullable=False)
    source_version = Column(Integer, nullable=True)
    source_fingerprint = Column(String(128), nullable=False)
    approved_review_id = Column(String(200), nullable=True)
    snapshot_id = Column(String(200), nullable=True)
    knowledge_asset_id = Column(String(200), nullable=True)
    lineage_manifest_hash = Column(String(128), nullable=False)
    source_trace_snapshot = Column(JSON, nullable=False)
    created_at = Column(DateTime, nullable=False, default=_utcnow)


class ReuseReview(Base):
    """Immutable final human-review decision for one asset version."""

    __tablename__ = "reuse_reviews"
    __table_args__ = (
        CheckConstraint(
            "length(trim(reviewed_content_hash)) > 0",
            name="ck_reuse_reviews_content_hash_not_blank",
        ),
        CheckConstraint(
            "length(trim(reviewed_source_manifest_hash)) > 0",
            name="ck_reuse_reviews_manifest_hash_not_blank",
        ),
        CheckConstraint(
            "length(trim(review_policy_version)) > 0",
            name="ck_reuse_reviews_policy_not_blank",
        ),
        CheckConstraint(
            "decision = 'approved' OR length(trim(comments)) > 0",
            name="ck_reuse_reviews_comments_for_nonapproval",
        ),
        UniqueConstraint(
            "asset_version_id",
            name="uq_reuse_reviews_asset_version",
        ),
        UniqueConstraint(
            "idempotency_key",
            name="uq_reuse_reviews_idempotency_key",
        ),
    )

    id = Column(String(200), primary_key=True)
    asset_version_id = Column(
        String(200),
        ForeignKey("reuse_asset_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    decision = Column(
        SqlEnum(
            ReuseReviewDecision,
            name="reuse_review_decision",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=_enum_values,
        ),
        nullable=False,
        index=True,
    )
    comments = Column(Text, nullable=True)
    checklist_payload = Column(JSON, nullable=False)
    review_policy_version = Column(String(100), nullable=False)
    reviewed_content_hash = Column(String(128), nullable=False)
    reviewed_source_manifest_hash = Column(String(128), nullable=False)
    reviewer_role = Column(String(50), nullable=False)
    request_id = Column(String(200), nullable=False)
    idempotency_key = Column(String(200), nullable=False)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
