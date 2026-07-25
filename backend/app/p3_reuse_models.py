"""P3 reuse-project and governed-source SQLAlchemy models.

P3-M2.1 intentionally defines only the project and selected-source tables.
The models reference P1/P2 governance records by stable IDs and immutable
evidence; they never add foreign keys or columns to P1/P2 tables.
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
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
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
