export type JsonPrimitive = string | number | boolean | null;
export type JsonValue = JsonPrimitive | JsonValue[] | { [key: string]: JsonValue };
export type JsonObject = { [key: string]: JsonValue };

export type P3ProjectStatus = "draft" | "active" | "archived";
export type P3AssetStatus =
  | "generating"
  | "generated"
  | "pending_review"
  | "needs_revision"
  | "approved"
  | "published"
  | "rejected"
  | "failed"
  | "superseded"
  | "archived";
export type P3ExportStatus = "pending" | "running" | "succeeded" | "failed" | "revoked";
export type P3SourceDisplayStatus = "eligible" | "stale" | "removed";
export type P3SourceType =
  | "P1_KNOWLEDGE"
  | "P2_KNOWLEDGE_ASSET"
  | "APPROVED_BAD_CASE_CORRECTION";
export type P3EligibilitySourceType = P3SourceType | "RAW_BAD_CASE";
export type P3AssetType =
  | "training_material"
  | "sop"
  | "service_script"
  | "qa_bank"
  | "sft_dataset";
export type P3GenerationMode =
  | "deterministic_template"
  | "llm_draft"
  | "manual_revision";
export type P3ReviewDecision = "approved" | "needs_revision" | "rejected";
export type P3ExportFormat = "jsonl" | "csv";
export type P3EligibilityReason =
  | "ELIGIBLE"
  | "SOURCE_NOT_FOUND"
  | "SOURCE_TYPE_UNSUPPORTED"
  | "SOURCE_NOT_APPROVED"
  | "SOURCE_ARCHIVED"
  | "SOURCE_SUPERSEDED"
  | "SOURCE_NOT_CURRENT"
  | "SOURCE_FINGERPRINT_MISMATCH"
  | "SOURCE_TRACE_INCOMPLETE"
  | "RAW_BAD_CASE_NOT_ALLOWED"
  | "BAD_CASE_CORRECTION_NOT_APPROVED"
  | "SOURCE_STATE_INVALID";

export interface P3Pagination<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface P3ApiEnvelope<T> {
  success: true;
  data: T;
  requestId: string;
}

export interface P3ApiErrorDetail {
  code: string;
  message?: string;
  details?: Record<string, string>;
}

export interface P3ApiErrorBody {
  detail?: P3ApiErrorDetail;
  error?: P3ApiErrorDetail;
  requestId?: string;
}

export interface P3Project {
  id: string;
  name: string;
  description: string | null;
  status: P3ProjectStatus;
  created_by_role: string;
  request_id: string;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
}

export interface P3ProjectCreateInput {
  name: string;
  description?: string | null;
  idempotency_key: string;
}

export interface P3ProjectUpdateInput {
  name?: string;
  description?: string | null;
}

export interface P3SourceEligibilityInput {
  source_type: P3EligibilitySourceType;
  source_id: string;
  source_version?: number;
  expected_fingerprint?: string;
}

export interface P3SourceEligibilityDecision {
  source_type: string;
  source_id: string;
  eligible: boolean;
  reason_code: P3EligibilityReason;
  source_status: string | null;
  source_version: number | null;
  content_fingerprint: string | null;
  approved_review_id: string | null;
  snapshot_id: string | null;
  knowledge_asset_id: string | null;
  lineage_complete: boolean;
  checked_conditions: string[];
  policy_version: string;
}

export interface P3SourceEligibilityData {
  policy_version: string;
  decision: P3SourceEligibilityDecision;
}

export interface P3SourceEligibilityBatchData {
  policy_version: string;
  decisions: P3SourceEligibilityDecision[];
}

export interface P3SourceItem {
  id: string;
  project_id: string;
  source_type: P3SourceType;
  source_id: string;
  source_version: number | null;
  source_fingerprint: string;
  eligibility_policy_version: string;
  approved_review_id: string | null;
  snapshot_id: string | null;
  knowledge_asset_id: string | null;
  lineage_manifest_hash: string | null;
  source_trace: JsonObject;
  selected_by_role: string;
  request_id: string;
  created_at: string;
  removed_at: string | null;
  source_stale: boolean;
}

export interface P3SourceAddInput {
  source_type: P3EligibilitySourceType;
  source_id: string;
  source_version?: number;
  expected_fingerprint?: string;
}

export interface P3SourceRevalidation {
  source_item_id: string;
  project_id: string;
  status: "valid" | "stale" | "skipped_removed";
  eligible: boolean;
  reason_code: P3EligibilityReason;
  source_stale: boolean;
}

export interface P3ProjectRevalidation {
  project_id: string;
  results: P3SourceRevalidation[];
  total: number;
  limit: number;
}

export interface P3GenerationSourceRef {
  source_item_id: string;
  source_type: P3SourceType;
  source_id: string;
  source_version: number | null;
  approved_review_id: string | null;
  snapshot_id: string | null;
  knowledge_asset_id: string | null;
  content_fingerprint: string;
  lineage_manifest_hash: string;
}

export interface P3AssetVersion {
  id: string;
  project_id: string;
  asset_type: P3AssetType;
  version_number: number;
  status: P3AssetStatus;
  generation_mode: P3GenerationMode;
  template_key: string;
  template_version: string;
  content_payload: JsonObject;
  content_hash: string;
  source_manifest_hash: string;
  parent_asset_version_id: string | null;
  created_by_role: string;
  request_id: string;
  created_at: string;
  updated_at: string;
  approved_at: string | null;
  published_at: string | null;
  failure_code: string | null;
  failure_message: string | null;
}

export interface P3AssetSourceSnapshot {
  id: string;
  asset_version_id: string;
  source_item_id: string;
  source_type: P3SourceType;
  source_id: string;
  source_version: number | null;
  source_fingerprint: string;
  approved_review_id: string | null;
  snapshot_id: string | null;
  knowledge_asset_id: string | null;
  lineage_manifest_hash: string;
  source_trace_snapshot: JsonObject;
  created_at: string;
}

export interface P3AssetGenerateInput {
  asset_type: P3AssetType;
  template_key?: string;
  idempotency_key: string;
}

export interface P3LlmAssetGenerateInput {
  asset_type: P3AssetType;
  prompt_key?: string;
  provider_profile?: string;
  idempotency_key: string;
}

export interface P3ReviewChecklist {
  structure_complete: boolean;
  source_refs_valid: boolean;
  no_unsupported_claims_confirmed: boolean;
  safe_for_reuse: boolean;
}

export interface P3Review {
  id: string;
  asset_version_id: string;
  decision: P3ReviewDecision;
  comments: string | null;
  checklist_payload: P3ReviewChecklist;
  review_policy_version: string;
  reviewed_content_hash: string;
  reviewed_source_manifest_hash: string;
  reviewer_role: string;
  request_id: string;
  created_at: string;
}

export interface P3PublishedAsset {
  asset_version_id: string;
  project_id: string;
  asset_type: P3AssetType;
  version_number: number;
  status: P3AssetStatus;
  generation_mode: P3GenerationMode;
  published_at: string | null;
  published_by_role: string | null;
  content_hash: string;
  source_manifest_hash: string;
  superseded_by_asset_version_id: string | null;
  archived_at: string | null;
  source_stale: boolean;
  current_reuse_eligible: boolean;
}

export interface P3PublicationOutcome {
  asset: P3PublishedAsset;
  superseded_asset_version_id: string | null;
  replayed: boolean;
}

export interface P3ExportJob {
  id: string;
  project_id: string;
  asset_version_id: string;
  export_format: P3ExportFormat;
  status: P3ExportStatus;
  export_policy_version: string;
  requested_by_role: string;
  request_id: string;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  failed_at: string | null;
  revoked_at: string | null;
  failure_code: string | null;
  failure_message: string | null;
}

export interface P3ExportArtifact {
  id: string;
  export_job_id: string;
  asset_version_id: string;
  export_format: P3ExportFormat;
  safe_file_name: string;
  content_type: string;
  encoding: string;
  byte_size: number;
  row_count: number;
  artifact_sha256: string;
  export_manifest_hash: string;
  created_at: string;
  revoked_at: string | null;
  source_stale: boolean;
  current_reuse_eligible: boolean;
}

export interface P3ExportOutcome {
  job: P3ExportJob;
  artifact: P3ExportArtifact | null;
  replayed: boolean;
}

export interface P3ExportRevokeOutcome {
  job: P3ExportJob;
  artifact: P3ExportArtifact;
  replayed: boolean;
}
