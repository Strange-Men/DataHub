"""Machine-generated immutable schema snapshot for the initial Alembic baseline.

Do not import application ORM models here. Future schema changes belong in new
revision files; changing this snapshot would invalidate safe adoption checks.
"""

from __future__ import annotations

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


BASELINE_REVISION = "20260803_0001"
BASELINE_SCHEMA_SHA256 = '99111b9840ab5e6444bc0b985ff61b42b97d020d564c82e8e9d414517119492f'
P3_TABLE_NAMES = frozenset({
    'export_artifacts',
    'export_jobs',
    'reuse_asset_version_sources',
    'reuse_asset_versions',
    'reuse_projects',
    'reuse_reviews',
    'reuse_source_items',
})
BASELINE_TABLE_NAMES = frozenset({
    'asset_extractions',
    'asset_review_snapshots',
    'assets',
    'bad_cases',
    'export_artifacts',
    'export_jobs',
    'extraction_jobs',
    'extraction_reviews',
    'knowledge_assets',
    'knowledge_candidates',
    'manual_cleaning_records',
    'p2_knowledge_chunks',
    'p2_knowledge_embeddings',
    'p2_knowledge_index_entries',
    'rag_chunks',
    'rag_embeddings',
    'raw_batches',
    'raw_messages',
    'retrieval_logs',
    'reuse_asset_version_sources',
    'reuse_asset_versions',
    'reuse_projects',
    'reuse_reviews',
    'reuse_source_items',
    'review_records',
    'sanitized_batches',
    'sanitized_messages',
})


def _vector_type(dialect_name: str, dimensions: int | None) -> sa.types.TypeEngine:
    if dialect_name == "postgresql":
        return Vector(dimensions) if dimensions is not None else Vector()
    return sa.Text()


def build_baseline_metadata(dialect_name: str) -> sa.MetaData:
    """Build metadata solely from this frozen snapshot."""

    metadata = sa.MetaData()
    tables: dict[str, sa.Table] = {}
    tables['asset_extractions'] = sa.Table(
        'asset_extractions',
        metadata,
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('asset_id', sa.String(), nullable=False),
        sa.Column('job_id', sa.String(), nullable=False),
        sa.Column('extract_type', sa.String(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=False), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('asset_id', 'extract_type', 'version', name='uq_asset_extraction_version'),
    )

    tables['asset_review_snapshots'] = sa.Table(
        'asset_review_snapshots',
        metadata,
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('asset_id', sa.String(), nullable=False),
        sa.Column('extraction_id', sa.String(), nullable=False),
        sa.Column('review_id', sa.String(), nullable=False),
        sa.Column('extract_type', sa.String(), nullable=False),
        sa.Column('original_content', sa.Text(), nullable=False),
        sa.Column('approved_content', sa.Text(), nullable=False),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=False), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('extraction_id', 'version', name='uq_asset_review_snapshot_version'),
    )

    tables['assets'] = sa.Table(
        'assets',
        metadata,
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('asset_type', sa.String(), nullable=False),
        sa.Column('file_name', sa.String(), nullable=False),
        sa.Column('mime_type', sa.String(), nullable=False),
        sa.Column('size', sa.BigInteger(), nullable=False),
        sa.Column('storage_uri', sa.Text(), nullable=False),
        sa.Column('hash', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=False), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=False), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    tables['bad_cases'] = sa.Table(
        'bad_cases',
        metadata,
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('retrieval_id', sa.String(), nullable=True),
        sa.Column('user_question', sa.Text(), nullable=False),
        sa.Column('bad_answer', sa.Text(), nullable=True),
        sa.Column('expected_answer', sa.Text(), nullable=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('created_candidate_id', sa.String(), nullable=True),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=False), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=False), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    tables['extraction_jobs'] = sa.Table(
        'extraction_jobs',
        metadata,
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('asset_id', sa.String(), nullable=False),
        sa.Column('extract_type', sa.String(), nullable=False),
        sa.Column('provider', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('retry_count', sa.Integer(), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=False), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=False), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=False), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=False), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    tables['extraction_reviews'] = sa.Table(
        'extraction_reviews',
        metadata,
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('asset_id', sa.String(), nullable=False),
        sa.Column('extraction_id', sa.String(), nullable=False),
        sa.Column('review_status', sa.String(), nullable=False),
        sa.Column('reviewer', sa.String(), nullable=True),
        sa.Column('review_comment', sa.Text(), nullable=True),
        sa.Column('original_content', sa.Text(), nullable=False),
        sa.Column('revised_content', sa.Text(), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=False), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=False), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('extraction_id', 'version', name='uq_extraction_review_version'),
    )

    tables['knowledge_assets'] = sa.Table(
        'knowledge_assets',
        metadata,
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('source_snapshot_id', sa.String(), nullable=False),
        sa.Column('asset_id', sa.String(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('content_type', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=False), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=False), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('asset_id', 'content_type', 'version', name='uq_knowledge_asset_version'),
    )

    tables['knowledge_candidates'] = sa.Table(
        'knowledge_candidates',
        metadata,
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('source_type', sa.String(), nullable=False),
        sa.Column('source_id', sa.String(), nullable=True),
        sa.Column('question', sa.Text(), nullable=False),
        sa.Column('answer', sa.Text(), nullable=False),
        sa.Column('intent', sa.String(), nullable=True),
        sa.Column('tags', sa.JSON(), nullable=True),
        sa.Column('risk_level', sa.String(), nullable=False),
        sa.Column('quality_score', sa.Float(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=False), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=False), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    tables['manual_cleaning_records'] = sa.Table(
        'manual_cleaning_records',
        metadata,
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('sanitized_message_id', sa.String(), nullable=False),
        sa.Column('cleaner', sa.String(), nullable=False),
        sa.Column('action', sa.String(), nullable=False),
        sa.Column('original_content', sa.Text(), nullable=False),
        sa.Column('cleaned_content', sa.Text(), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=False), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    tables['p2_knowledge_chunks'] = sa.Table(
        'p2_knowledge_chunks',
        metadata,
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('index_entry_id', sa.String(), nullable=False),
        sa.Column('knowledge_asset_id', sa.String(), nullable=False),
        sa.Column('chunk_text', sa.Text(), nullable=False),
        sa.Column('chunk_hash', sa.String(), nullable=False),
        sa.Column('chunk_order', sa.Integer(), nullable=False),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=False), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('index_entry_id', 'chunk_order', name='uq_p2_knowledge_chunk_order'),
    )

    tables['p2_knowledge_embeddings'] = sa.Table(
        'p2_knowledge_embeddings',
        metadata,
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('index_entry_id', sa.String(), nullable=False),
        sa.Column('chunk_id', sa.String(), nullable=False),
        sa.Column('knowledge_asset_id', sa.String(), nullable=False),
        sa.Column('chunk_text', sa.Text(), nullable=False),
        sa.Column('embedding', _vector_type(dialect_name, None), nullable=False),
        sa.Column('provider', sa.String(), nullable=False),
        sa.Column('model', sa.String(), nullable=False),
        sa.Column('dimension', sa.Integer(), nullable=False),
        sa.Column('embedding_profile', sa.String(), nullable=False),
        sa.Column('fingerprint', sa.String(), nullable=False),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=False), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('chunk_id', 'embedding_profile', 'fingerprint', name='uq_p2_knowledge_embedding_build'),
    )

    tables['p2_knowledge_index_entries'] = sa.Table(
        'p2_knowledge_index_entries',
        metadata,
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('knowledge_asset_id', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('generation', sa.Integer(), nullable=False),
        sa.Column('fingerprint', sa.String(), nullable=False),
        sa.Column('sync_state', sa.String(), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=False), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=False), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    tables['rag_chunks'] = sa.Table(
        'rag_chunks',
        metadata,
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('candidate_id', sa.String(), nullable=False),
        sa.Column('chunk_text', sa.Text(), nullable=False),
        sa.Column('intent', sa.String(), nullable=True),
        sa.Column('tags', sa.JSON(), nullable=True),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=False), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    tables['rag_embeddings'] = sa.Table(
        'rag_embeddings',
        metadata,
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('chunk_id', sa.String(), nullable=True),
        sa.Column('candidate_id', sa.String(), nullable=False),
        sa.Column('source_type', sa.String(), nullable=False),
        sa.Column('source_batch_id', sa.String(), nullable=True),
        sa.Column('source_message_id', sa.String(), nullable=True),
        sa.Column('modality', sa.String(), nullable=False),
        sa.Column('chunk_text', sa.Text(), nullable=False),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('embedding', _vector_type(dialect_name, 1536), nullable=True),
        sa.Column('embedding_provider', sa.String(), nullable=True),
        sa.Column('embedding_model', sa.String(), nullable=True),
        sa.Column('embedding_dimension', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=False), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=False), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    tables['raw_batches'] = sa.Table(
        'raw_batches',
        metadata,
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('source_name', sa.String(), nullable=False),
        sa.Column('source_type', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('message_count', sa.Integer(), nullable=False),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=False), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=False), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    tables['raw_messages'] = sa.Table(
        'raw_messages',
        metadata,
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('batch_id', sa.String(), nullable=False),
        sa.Column('role', sa.String(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('timestamp', sa.String(), nullable=True),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=False), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    tables['retrieval_logs'] = sa.Table(
        'retrieval_logs',
        metadata,
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('query', sa.Text(), nullable=False),
        sa.Column('matched_chunk_ids', sa.JSON(), nullable=True),
        sa.Column('response_preview', sa.Text(), nullable=True),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=False), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    tables['reuse_projects'] = sa.Table(
        'reuse_projects',
        metadata,
        sa.Column('id', sa.String(200), nullable=False),
        sa.Column('name', sa.String(300), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', sa.Enum('draft', 'active', 'archived', name='reuse_project_status', native_enum=False, create_constraint=True), nullable=False),
        sa.Column('created_by_role', sa.String(50), nullable=False),
        sa.Column('request_id', sa.String(200), nullable=False),
        sa.Column('idempotency_key', sa.String(200), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=False), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=False), nullable=False),
        sa.Column('archived_at', sa.DateTime(timezone=False), nullable=True),
        sa.CheckConstraint('length(trim(name)) > 0', name='ck_reuse_projects_name_not_blank'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('idempotency_key', name='uq_reuse_projects_idempotency_key'),
    )

    tables['review_records'] = sa.Table(
        'review_records',
        metadata,
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('candidate_id', sa.String(), nullable=False),
        sa.Column('reviewer', sa.String(), nullable=False),
        sa.Column('action', sa.String(), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('snapshot_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=False), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    tables['sanitized_batches'] = sa.Table(
        'sanitized_batches',
        metadata,
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('raw_batch_id', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('message_count', sa.Integer(), nullable=False),
        sa.Column('high_quality_count', sa.Integer(), nullable=False),
        sa.Column('review_recommended_count', sa.Integer(), nullable=False),
        sa.Column('drop_recommended_count', sa.Integer(), nullable=False),
        sa.Column('average_quality_score', sa.Float(), nullable=True),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=False), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=False), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    tables['sanitized_messages'] = sa.Table(
        'sanitized_messages',
        metadata,
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('batch_id', sa.String(), nullable=False),
        sa.Column('raw_message_id', sa.String(), nullable=True),
        sa.Column('role', sa.String(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('sanitized_content', sa.Text(), nullable=False),
        sa.Column('quality_score', sa.Float(), nullable=False),
        sa.Column('quality_level', sa.String(), nullable=False),
        sa.Column('suggested_action', sa.String(), nullable=False),
        sa.Column('cleaning_issues', sa.JSON(), nullable=True),
        sa.Column('risk_flags', sa.JSON(), nullable=True),
        sa.Column('pii_entities', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=False), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=False), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    tables['reuse_asset_versions'] = sa.Table(
        'reuse_asset_versions',
        metadata,
        sa.Column('id', sa.String(200), nullable=False),
        sa.Column('project_id', sa.String(200), nullable=False),
        sa.Column('asset_type', sa.Enum('training_material', 'sop', 'service_script', 'qa_bank', 'sft_dataset', name='reuse_asset_type', native_enum=False, create_constraint=True), nullable=False),
        sa.Column('version_number', sa.Integer(), nullable=False),
        sa.Column('status', sa.Enum('generating', 'generated', 'pending_review', 'needs_revision', 'approved', 'published', 'rejected', 'failed', 'superseded', 'archived', name='reuse_asset_version_status', native_enum=False, create_constraint=True), nullable=False),
        sa.Column('generation_mode', sa.Enum('deterministic_template', 'llm_draft', 'manual_revision', name='reuse_generation_mode', native_enum=False, create_constraint=True), nullable=False),
        sa.Column('template_key', sa.String(200), nullable=False),
        sa.Column('template_version', sa.String(100), nullable=False),
        sa.Column('content_payload', sa.JSON(), nullable=False),
        sa.Column('content_hash', sa.String(128), nullable=False),
        sa.Column('source_manifest_hash', sa.String(128), nullable=False),
        sa.Column('idempotency_key', sa.String(200), nullable=False),
        sa.Column('created_by_role', sa.String(50), nullable=False),
        sa.Column('request_id', sa.String(200), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=False), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=False), nullable=False),
        sa.Column('approved_at', sa.DateTime(timezone=False), nullable=True),
        sa.Column('published_at', sa.DateTime(timezone=False), nullable=True),
        sa.Column('superseded_at', sa.DateTime(timezone=False), nullable=True),
        sa.Column('archived_at', sa.DateTime(timezone=False), nullable=True),
        sa.Column('published_by_role', sa.String(50), nullable=True),
        sa.Column('publish_request_id', sa.String(200), nullable=True),
        sa.Column('publish_idempotency_key', sa.String(200), nullable=True),
        sa.Column('superseded_by_asset_version_id', sa.String(200), nullable=True),
        sa.Column('archived_by_role', sa.String(50), nullable=True),
        sa.Column('archive_request_id', sa.String(200), nullable=True),
        sa.Column('archive_idempotency_key', sa.String(200), nullable=True),
        sa.Column('failure_code', sa.String(100), nullable=True),
        sa.Column('failure_message', sa.Text(), nullable=True),
        sa.Column('parent_asset_version_id', sa.String(200), nullable=True),
        sa.CheckConstraint('length(trim(content_hash)) > 0', name='ck_reuse_asset_versions_content_hash_not_blank'),
        sa.CheckConstraint("generation_mode != 'manual_revision' OR parent_asset_version_id IS NOT NULL", name='ck_reuse_asset_versions_manual_parent_required'),
        sa.CheckConstraint('parent_asset_version_id IS NULL OR parent_asset_version_id != id', name='ck_reuse_asset_versions_parent_not_self'),
        sa.CheckConstraint('length(trim(source_manifest_hash)) > 0', name='ck_reuse_asset_versions_source_manifest_hash_not_blank'),
        sa.CheckConstraint('length(trim(template_key)) > 0', name='ck_reuse_asset_versions_template_key_not_blank'),
        sa.CheckConstraint('length(trim(template_version)) > 0', name='ck_reuse_asset_versions_template_version_not_blank'),
        sa.CheckConstraint('version_number >= 1', name='ck_reuse_asset_versions_version_positive'),
        sa.ForeignKeyConstraint(['project_id'], ['reuse_projects.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['parent_asset_version_id'], ['reuse_asset_versions.id'], name='fk_reuse_asset_versions_parent', ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['superseded_by_asset_version_id'], ['reuse_asset_versions.id'], name='fk_reuse_asset_versions_superseded_by', ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('archive_idempotency_key', name='uq_reuse_asset_versions_archive_idempotency_key'),
        sa.UniqueConstraint('idempotency_key', name='uq_reuse_asset_versions_idempotency_key'),
        sa.UniqueConstraint('project_id', 'asset_type', 'version_number', name='uq_reuse_asset_versions_project_type_version'),
        sa.UniqueConstraint('publish_idempotency_key', name='uq_reuse_asset_versions_publish_idempotency_key'),
    )

    tables['reuse_source_items'] = sa.Table(
        'reuse_source_items',
        metadata,
        sa.Column('id', sa.String(200), nullable=False),
        sa.Column('project_id', sa.String(200), nullable=False),
        sa.Column('source_type', sa.Enum('P1_KNOWLEDGE', 'P2_KNOWLEDGE_ASSET', 'APPROVED_BAD_CASE_CORRECTION', name='p3_source_type', native_enum=False, create_constraint=True), nullable=False),
        sa.Column('source_id', sa.String(200), nullable=False),
        sa.Column('source_version', sa.Integer(), nullable=True),
        sa.Column('source_version_key', sa.Integer(), sa.Computed('COALESCE(source_version, 0)', persisted=True), nullable=True),
        sa.Column('source_fingerprint', sa.String(128), nullable=False),
        sa.Column('eligibility_policy_version', sa.String(100), nullable=False),
        sa.Column('approved_review_id', sa.String(200), nullable=True),
        sa.Column('snapshot_id', sa.String(200), nullable=True),
        sa.Column('knowledge_asset_id', sa.String(200), nullable=True),
        sa.Column('lineage_manifest_hash', sa.String(128), nullable=True),
        sa.Column('source_trace', sa.JSON(), nullable=False),
        sa.Column('selected_by_role', sa.String(50), nullable=False),
        sa.Column('request_id', sa.String(200), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=False), nullable=False),
        sa.Column('removed_at', sa.DateTime(timezone=False), nullable=True),
        sa.Column('source_stale', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.CheckConstraint('length(trim(source_fingerprint)) > 0', name='ck_reuse_source_items_fingerprint_not_blank'),
        sa.CheckConstraint('length(trim(eligibility_policy_version)) > 0', name='ck_reuse_source_items_policy_not_blank'),
        sa.CheckConstraint('length(trim(source_id)) > 0', name='ck_reuse_source_items_source_id_not_blank'),
        sa.CheckConstraint('source_version IS NULL OR source_version >= 1', name='ck_reuse_source_items_source_version_positive'),
        sa.ForeignKeyConstraint(['project_id'], ['reuse_projects.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('project_id', 'source_type', 'source_id', 'source_version_key', name='uq_reuse_source_items_project_source_version'),
    )

    tables['export_jobs'] = sa.Table(
        'export_jobs',
        metadata,
        sa.Column('id', sa.String(200), nullable=False),
        sa.Column('project_id', sa.String(200), nullable=False),
        sa.Column('asset_version_id', sa.String(200), nullable=False),
        sa.Column('export_format', sa.Enum('jsonl', 'csv', name='p3_export_format', native_enum=False, create_constraint=True), nullable=False),
        sa.Column('status', sa.Enum('pending', 'running', 'succeeded', 'failed', 'revoked', name='p3_export_job_status', native_enum=False, create_constraint=True), nullable=False),
        sa.Column('export_policy_version', sa.String(100), nullable=False),
        sa.Column('requested_by_role', sa.String(50), nullable=False),
        sa.Column('request_id', sa.String(200), nullable=False),
        sa.Column('idempotency_key', sa.String(200), nullable=False),
        sa.Column('request_fingerprint', sa.String(128), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=False), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=False), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=False), nullable=True),
        sa.Column('failed_at', sa.DateTime(timezone=False), nullable=True),
        sa.Column('revoked_at', sa.DateTime(timezone=False), nullable=True),
        sa.Column('revoked_by_role', sa.String(50), nullable=True),
        sa.Column('revoke_request_id', sa.String(200), nullable=True),
        sa.Column('revoke_idempotency_key', sa.String(200), nullable=True),
        sa.Column('failure_code', sa.String(100), nullable=True),
        sa.Column('failure_message', sa.Text(), nullable=True),
        sa.CheckConstraint('length(trim(request_fingerprint)) > 0', name='ck_export_jobs_fingerprint_not_blank'),
        sa.CheckConstraint('length(trim(export_policy_version)) > 0', name='ck_export_jobs_policy_not_blank'),
        sa.ForeignKeyConstraint(['asset_version_id'], ['reuse_asset_versions.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['project_id'], ['reuse_projects.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('idempotency_key', name='uq_export_jobs_idempotency_key'),
        sa.UniqueConstraint('revoke_idempotency_key', name='uq_export_jobs_revoke_idempotency_key'),
    )

    tables['reuse_asset_version_sources'] = sa.Table(
        'reuse_asset_version_sources',
        metadata,
        sa.Column('id', sa.String(200), nullable=False),
        sa.Column('asset_version_id', sa.String(200), nullable=False),
        sa.Column('source_item_id', sa.String(200), nullable=False),
        sa.Column('source_type', sa.Enum('P1_KNOWLEDGE', 'P2_KNOWLEDGE_ASSET', 'APPROVED_BAD_CASE_CORRECTION', name='p3_asset_version_source_type', native_enum=False, create_constraint=True), nullable=False),
        sa.Column('source_id', sa.String(200), nullable=False),
        sa.Column('source_version', sa.Integer(), nullable=True),
        sa.Column('source_fingerprint', sa.String(128), nullable=False),
        sa.Column('approved_review_id', sa.String(200), nullable=True),
        sa.Column('snapshot_id', sa.String(200), nullable=True),
        sa.Column('knowledge_asset_id', sa.String(200), nullable=True),
        sa.Column('lineage_manifest_hash', sa.String(128), nullable=False),
        sa.Column('source_trace_snapshot', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=False), nullable=False),
        sa.CheckConstraint('length(trim(source_fingerprint)) > 0', name='ck_reuse_asset_version_sources_fingerprint_not_blank'),
        sa.CheckConstraint('length(trim(lineage_manifest_hash)) > 0', name='ck_reuse_asset_version_sources_lineage_hash_not_blank'),
        sa.CheckConstraint('length(trim(source_id)) > 0', name='ck_reuse_asset_version_sources_source_id_not_blank'),
        sa.CheckConstraint('source_version IS NULL OR source_version >= 1', name='ck_reuse_asset_version_sources_version_positive'),
        sa.ForeignKeyConstraint(['asset_version_id'], ['reuse_asset_versions.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['source_item_id'], ['reuse_source_items.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('asset_version_id', 'source_item_id', name='uq_reuse_asset_version_sources_version_source'),
    )

    tables['reuse_reviews'] = sa.Table(
        'reuse_reviews',
        metadata,
        sa.Column('id', sa.String(200), nullable=False),
        sa.Column('asset_version_id', sa.String(200), nullable=False),
        sa.Column('decision', sa.Enum('approved', 'needs_revision', 'rejected', name='reuse_review_decision', native_enum=False, create_constraint=True), nullable=False),
        sa.Column('comments', sa.Text(), nullable=True),
        sa.Column('checklist_payload', sa.JSON(), nullable=False),
        sa.Column('review_policy_version', sa.String(100), nullable=False),
        sa.Column('reviewed_content_hash', sa.String(128), nullable=False),
        sa.Column('reviewed_source_manifest_hash', sa.String(128), nullable=False),
        sa.Column('reviewer_role', sa.String(50), nullable=False),
        sa.Column('request_id', sa.String(200), nullable=False),
        sa.Column('idempotency_key', sa.String(200), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=False), nullable=False),
        sa.CheckConstraint("decision = 'approved' OR length(trim(comments)) > 0", name='ck_reuse_reviews_comments_for_nonapproval'),
        sa.CheckConstraint('length(trim(reviewed_content_hash)) > 0', name='ck_reuse_reviews_content_hash_not_blank'),
        sa.CheckConstraint('length(trim(reviewed_source_manifest_hash)) > 0', name='ck_reuse_reviews_manifest_hash_not_blank'),
        sa.CheckConstraint('length(trim(review_policy_version)) > 0', name='ck_reuse_reviews_policy_not_blank'),
        sa.ForeignKeyConstraint(['asset_version_id'], ['reuse_asset_versions.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('asset_version_id', name='uq_reuse_reviews_asset_version'),
        sa.UniqueConstraint('idempotency_key', name='uq_reuse_reviews_idempotency_key'),
    )

    tables['export_artifacts'] = sa.Table(
        'export_artifacts',
        metadata,
        sa.Column('id', sa.String(200), nullable=False),
        sa.Column('export_job_id', sa.String(200), nullable=False),
        sa.Column('asset_version_id', sa.String(200), nullable=False),
        sa.Column('export_format', sa.Enum('jsonl', 'csv', name='p3_export_artifact_format', native_enum=False, create_constraint=True), nullable=False),
        sa.Column('storage_backend', sa.String(50), nullable=False),
        sa.Column('storage_key', sa.String(500), nullable=False),
        sa.Column('safe_file_name', sa.String(255), nullable=False),
        sa.Column('content_type', sa.String(100), nullable=False),
        sa.Column('encoding', sa.String(50), nullable=False),
        sa.Column('byte_size', sa.Integer(), nullable=False),
        sa.Column('row_count', sa.Integer(), nullable=False),
        sa.Column('artifact_sha256', sa.String(128), nullable=False),
        sa.Column('export_manifest_hash', sa.String(128), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=False), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=False), nullable=True),
        sa.Column('revoked_by_role', sa.String(50), nullable=True),
        sa.Column('revoke_request_id', sa.String(200), nullable=True),
        sa.CheckConstraint('length(trim(storage_backend)) > 0', name='ck_export_artifacts_backend_not_blank'),
        sa.CheckConstraint('byte_size >= 0', name='ck_export_artifacts_byte_size_nonnegative'),
        sa.CheckConstraint('length(trim(content_type)) > 0', name='ck_export_artifacts_content_type_not_blank'),
        sa.CheckConstraint('length(trim(encoding)) > 0', name='ck_export_artifacts_encoding_not_blank'),
        sa.CheckConstraint('length(trim(safe_file_name)) > 0', name='ck_export_artifacts_file_name_not_blank'),
        sa.CheckConstraint('length(trim(export_manifest_hash)) > 0', name='ck_export_artifacts_manifest_not_blank'),
        sa.CheckConstraint('row_count >= 0', name='ck_export_artifacts_row_count_nonnegative'),
        sa.CheckConstraint('length(trim(artifact_sha256)) > 0', name='ck_export_artifacts_sha_not_blank'),
        sa.CheckConstraint('length(trim(storage_key)) > 0', name='ck_export_artifacts_storage_key_not_blank'),
        sa.ForeignKeyConstraint(['asset_version_id'], ['reuse_asset_versions.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['export_job_id'], ['export_jobs.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('export_job_id', name='uq_export_artifacts_export_job_id'),
        sa.UniqueConstraint('storage_key', name='uq_export_artifacts_storage_key'),
    )

    sa.Index('ix_asset_extractions_asset_id', tables['asset_extractions'].c['asset_id'], unique=False)
    sa.Index('ix_asset_extractions_extract_type', tables['asset_extractions'].c['extract_type'], unique=False)
    sa.Index('ix_asset_extractions_job_id', tables['asset_extractions'].c['job_id'], unique=True)
    sa.Index('ix_asset_review_snapshots_asset_id', tables['asset_review_snapshots'].c['asset_id'], unique=False)
    sa.Index('ix_asset_review_snapshots_extract_type', tables['asset_review_snapshots'].c['extract_type'], unique=False)
    sa.Index('ix_asset_review_snapshots_extraction_id', tables['asset_review_snapshots'].c['extraction_id'], unique=False)
    sa.Index('ix_asset_review_snapshots_review_id', tables['asset_review_snapshots'].c['review_id'], unique=True)
    sa.Index('ix_assets_asset_type', tables['assets'].c['asset_type'], unique=False)
    sa.Index('ix_assets_hash', tables['assets'].c['hash'], unique=True)
    sa.Index('ix_assets_status', tables['assets'].c['status'], unique=False)
    sa.Index('ix_extraction_jobs_asset_id', tables['extraction_jobs'].c['asset_id'], unique=False)
    sa.Index('ix_extraction_jobs_extract_type', tables['extraction_jobs'].c['extract_type'], unique=False)
    sa.Index('ix_extraction_jobs_status', tables['extraction_jobs'].c['status'], unique=False)
    sa.Index('ix_extraction_reviews_asset_id', tables['extraction_reviews'].c['asset_id'], unique=False)
    sa.Index('ix_extraction_reviews_extraction_id', tables['extraction_reviews'].c['extraction_id'], unique=False)
    sa.Index('ix_extraction_reviews_review_status', tables['extraction_reviews'].c['review_status'], unique=False)
    sa.Index('ix_knowledge_assets_asset_id', tables['knowledge_assets'].c['asset_id'], unique=False)
    sa.Index('ix_knowledge_assets_content_type', tables['knowledge_assets'].c['content_type'], unique=False)
    sa.Index('ix_knowledge_assets_source_snapshot_id', tables['knowledge_assets'].c['source_snapshot_id'], unique=True)
    sa.Index('ix_knowledge_assets_status', tables['knowledge_assets'].c['status'], unique=False)
    sa.Index('ix_manual_cleaning_records_sanitized_message_id', tables['manual_cleaning_records'].c['sanitized_message_id'], unique=False)
    sa.Index('ix_p2_knowledge_chunks_chunk_hash', tables['p2_knowledge_chunks'].c['chunk_hash'], unique=False)
    sa.Index('ix_p2_knowledge_chunks_index_entry_id', tables['p2_knowledge_chunks'].c['index_entry_id'], unique=False)
    sa.Index('ix_p2_knowledge_chunks_knowledge_asset_id', tables['p2_knowledge_chunks'].c['knowledge_asset_id'], unique=False)
    sa.Index('ix_p2_knowledge_embeddings_chunk_id', tables['p2_knowledge_embeddings'].c['chunk_id'], unique=False)
    sa.Index('ix_p2_knowledge_embeddings_embedding_profile', tables['p2_knowledge_embeddings'].c['embedding_profile'], unique=False)
    sa.Index('ix_p2_knowledge_embeddings_fingerprint', tables['p2_knowledge_embeddings'].c['fingerprint'], unique=True)
    sa.Index('ix_p2_knowledge_embeddings_index_entry_id', tables['p2_knowledge_embeddings'].c['index_entry_id'], unique=False)
    sa.Index('ix_p2_knowledge_embeddings_knowledge_asset_id', tables['p2_knowledge_embeddings'].c['knowledge_asset_id'], unique=False)
    sa.Index('ix_p2_knowledge_embeddings_provider', tables['p2_knowledge_embeddings'].c['provider'], unique=False)
    sa.Index('ix_p2_knowledge_index_entries_fingerprint', tables['p2_knowledge_index_entries'].c['fingerprint'], unique=True)
    sa.Index('ix_p2_knowledge_index_entries_knowledge_asset_id', tables['p2_knowledge_index_entries'].c['knowledge_asset_id'], unique=True)
    sa.Index('ix_p2_knowledge_index_entries_status', tables['p2_knowledge_index_entries'].c['status'], unique=False)
    sa.Index('ix_p2_knowledge_index_entries_sync_state', tables['p2_knowledge_index_entries'].c['sync_state'], unique=False)
    sa.Index('ix_rag_chunks_candidate_id', tables['rag_chunks'].c['candidate_id'], unique=False)
    sa.Index('ix_rag_embeddings_candidate_id', tables['rag_embeddings'].c['candidate_id'], unique=False)
    sa.Index('ix_rag_embeddings_chunk_id', tables['rag_embeddings'].c['chunk_id'], unique=False)
    sa.Index('ix_raw_messages_batch_id', tables['raw_messages'].c['batch_id'], unique=False)
    sa.Index('ix_reuse_projects_status', tables['reuse_projects'].c['status'], unique=False)
    sa.Index('ix_review_records_candidate_id', tables['review_records'].c['candidate_id'], unique=False)
    sa.Index('ix_sanitized_batches_raw_batch_id', tables['sanitized_batches'].c['raw_batch_id'], unique=False)
    sa.Index('ix_sanitized_messages_batch_id', tables['sanitized_messages'].c['batch_id'], unique=False)
    sa.Index('ix_reuse_asset_versions_asset_type', tables['reuse_asset_versions'].c['asset_type'], unique=False)
    sa.Index('ix_reuse_asset_versions_parent_asset_version_id', tables['reuse_asset_versions'].c['parent_asset_version_id'], unique=False)
    sa.Index('ix_reuse_asset_versions_project_id', tables['reuse_asset_versions'].c['project_id'], unique=False)
    sa.Index('ix_reuse_asset_versions_status', tables['reuse_asset_versions'].c['status'], unique=False)
    sa.Index('ix_reuse_asset_versions_superseded_by_asset_version_id', tables['reuse_asset_versions'].c['superseded_by_asset_version_id'], unique=False)
    sa.Index('uq_reuse_asset_versions_current_published', tables['reuse_asset_versions'].c['project_id'], tables['reuse_asset_versions'].c['asset_type'], unique=True, sqlite_where=sa.text("status = 'published'"), postgresql_where=sa.text("status = 'published'"))
    sa.Index('ix_reuse_source_items_project_id', tables['reuse_source_items'].c['project_id'], unique=False)
    sa.Index('ix_reuse_source_items_source_type', tables['reuse_source_items'].c['source_type'], unique=False)
    sa.Index('ix_export_jobs_asset_version_id', tables['export_jobs'].c['asset_version_id'], unique=False)
    sa.Index('ix_export_jobs_export_format', tables['export_jobs'].c['export_format'], unique=False)
    sa.Index('ix_export_jobs_project_id', tables['export_jobs'].c['project_id'], unique=False)
    sa.Index('ix_export_jobs_status', tables['export_jobs'].c['status'], unique=False)
    sa.Index('ix_reuse_asset_version_sources_asset_version_id', tables['reuse_asset_version_sources'].c['asset_version_id'], unique=False)
    sa.Index('ix_reuse_asset_version_sources_source_item_id', tables['reuse_asset_version_sources'].c['source_item_id'], unique=False)
    sa.Index('ix_reuse_reviews_asset_version_id', tables['reuse_reviews'].c['asset_version_id'], unique=False)
    sa.Index('ix_reuse_reviews_decision', tables['reuse_reviews'].c['decision'], unique=False)
    sa.Index('ix_export_artifacts_asset_version_id', tables['export_artifacts'].c['asset_version_id'], unique=False)
    sa.Index('ix_export_artifacts_export_format', tables['export_artifacts'].c['export_format'], unique=False)
    sa.Index('ix_export_artifacts_export_job_id', tables['export_artifacts'].c['export_job_id'], unique=False)

    return metadata


__all__ = [
    "BASELINE_REVISION",
    "BASELINE_SCHEMA_SHA256",
    "BASELINE_TABLE_NAMES",
    "P3_TABLE_NAMES",
    "build_baseline_metadata",
]
