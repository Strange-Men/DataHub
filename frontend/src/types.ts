export type SourceBatch = {
  batch_id: string;
  source_name: string;
  message_count: number;
  conversation_count: number;
  created_at: string;
  status: "raw_imported";
};

export type BackendStatus = {
  state: "checking" | "connected" | "disconnected";
  service?: string;
  phase?: string;
  detail?: string;
};

export type Asset = {
  id: string;
  asset_type: "image" | "video" | "pdf" | string;
  file_name: string;
  mime_type: string;
  size: number;
  storage_uri: string;
  hash: string;
  status: "uploaded" | string;
  metadata_json: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type AssetPagination = {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
};

export type AssetExtraction = {
  id: string;
  asset_id: string;
  job_id: string;
  extract_type: "ocr" | "caption" | "metadata" | string;
  content: string;
  metadata_json: Record<string, unknown>;
  version: number;
  created_at: string;
};

export type ExtractionReviewStatus =
  | "pending"
  | "approved"
  | "rejected"
  | "needs_revision";

export type ExtractionReview = {
  id: string;
  asset_id: string;
  extraction_id: string;
  review_status: ExtractionReviewStatus;
  reviewer: string | null;
  review_comment: string | null;
  original_content: string;
  revised_content: string | null;
  version: number;
  created_at: string;
  updated_at: string;
};

export type AssetReviewSnapshot = {
  id: string;
  asset_id: string;
  extraction_id: string;
  review_id: string;
  extract_type: string;
  original_content: string;
  approved_content: string;
  metadata_json: Record<string, unknown>;
  version: number;
  created_at: string;
};

export type CleaningJob = {
  raw_message_count: number;
  sanitized_message_count: number;
  dropped_message_count: number;
  pii_detected_count: number;
  exact_duplicate_count?: number;
  near_duplicate_count?: number;
  low_quality_count?: number;
  noise_count?: number;
  drop_recommended_count?: number;
  average_quality_score?: number;
  status: "completed";
};

export type ManualAction = "keep" | "keep_edited" | "drop" | "needs_review";
export type ReviewStatus = "pending_review" | "needs_revision" | "approved" | "rejected";
export type SourceType =
  | "sanitized_batch"
  | "chat_logs"
  | "public_dataset"
  | "bad_case"
  | "legacy_rag"
  | "manual"
  | "unknown";
export type Intent =
  | "shipping"
  | "refund"
  | "order_status"
  | "product_info"
  | "handoff"
  | "prohibited_answer"
  | "general";
export type RiskLevel = "low" | "medium" | "high";
export type KnowledgeType =
  | "faq"
  | "standard_answer"
  | "business_rule"
  | "human_handoff_rule"
  | "forbidden_answer_rule"
  | "escalation_rule"
  | "forbidden_rule";

export type SanitizedMessage = {
  conversation_id: string;
  message_id: string;
  source_message_id: string;
  role: "customer" | "agent" | "system";
  content: string;
  pii_detected: boolean;
  pii_types: string[];
  cleaning_issues: string[];
  risk_flags: string[];
  quality_score: number;
  quality_level: "high" | "medium" | "low";
  suggested_action: "keep" | "review" | "drop";
  manual_cleaning_status?: "not_cleaned" | "cleaned";
  manual_cleaned_content?: string | null;
  manual_action?: ManualAction | null;
  cleaner?: string | null;
  cleaning_note?: string | null;
};

export type SanitizedBatch = {
  batch_id: string;
  sanitized_message_count: number;
  low_quality_count?: number;
  noise_count?: number;
  average_quality_score?: number;
  messages: SanitizedMessage[];
};

export type KnowledgeCandidate = {
  candidate_id: string;
  source_type?: SourceType;
  source_batch_id?: string | null;
  source_conversation_id?: string | null;
  source_message_ids: string[];
  source_bad_case_id?: string | null;
  source_retrieval_id?: string | null;
  source_chunk_ids?: string[];
  source_legacy_id?: string | null;
  source_import_id?: string | null;
  knowledge_type: KnowledgeType;
  question: string;
  answer: string;
  intent: Intent;
  tags: string[];
  risk_level: RiskLevel;
  review_status: ReviewStatus;
  quality_score: number;
  cleaning_issues?: string[];
  risk_flags?: string[];
  reviewer?: string | null;
  review_note?: string | null;
  reviewed_at?: string | null;
  created_at: string;
  updated_at?: string | null;
};

export type ManualEditState = {
  content: string;
  manual_action: ManualAction;
  cleaner: string;
  cleaning_note: string;
};

export type CandidateEditState = {
  question: string;
  answer: string;
  intent: Intent;
  tagsText: string;
  risk_level: RiskLevel;
  quality_score: string;
};

export type ReviewFilterState = {
  status: "all" | ReviewStatus;
  source_type: "all" | SourceType;
  quality_level: "all" | "high" | "medium" | "low";
  intent: "all" | Intent;
  keyword: string;
};

export type ReviewDecisionState = {
  reviewer: string;
  review_note: string;
};

export type RagSearchResult = {
  score: number;
  matched_terms: string[];
  chunk_id: string;
  candidate_id: string;
  knowledge_type: string;
  intent: string;
  tags: string[];
  risk_level: string;
  quality_score: number;
  chunk_text: string;
  answer?: string;
};
