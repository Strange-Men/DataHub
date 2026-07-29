import type {
  P3AssetStatus,
  P3AssetType,
  P3EligibilityReason,
  P3ExportStatus,
  P3ProjectStatus,
  P3SourceDisplayStatus,
  P3SourceType,
} from "./types";

export const P3_PROJECT_STATUS_LABELS: Readonly<Record<P3ProjectStatus, string>> = {
  draft: "草稿项目",
  active: "已激活",
  archived: "已归档",
};

export const P3_ASSET_STATUS_LABELS: Readonly<Record<P3AssetStatus, string>> = {
  generating: "生成中",
  generated: "草稿已生成",
  pending_review: "待审核",
  needs_revision: "需要修改",
  approved: "已批准",
  published: "已发布",
  rejected: "已拒绝",
  failed: "生成失败",
  superseded: "已被新版本替代",
  archived: "已归档",
};

export const P3_EXPORT_STATUS_LABELS: Readonly<Record<P3ExportStatus, string>> = {
  pending: "等待导出",
  running: "正在导出",
  succeeded: "导出成功",
  failed: "导出失败",
  revoked: "已撤回",
};

export const P3_SOURCE_STATUS_LABELS: Readonly<Record<P3SourceDisplayStatus, string>> = {
  eligible: "可使用",
  stale: "来源已变化",
  removed: "已移除",
};

export const P3_SOURCE_TYPE_LABELS: Readonly<Record<P3SourceType, string>> = {
  P1_KNOWLEDGE: "P1 已审核知识",
  P2_KNOWLEDGE_ASSET: "P2 已发布知识资产",
  APPROVED_BAD_CASE_CORRECTION: "已审核 Bad Case 修正",
};

export const P3_ASSET_TYPE_LABELS: Readonly<Record<P3AssetType, string>> = {
  training_material: "培训材料",
  sop: "SOP",
  service_script: "客服话术",
  qa_bank: "问答题库",
  sft_dataset: "SFT 数据集",
};

export const P3_ELIGIBILITY_REASON_LABELS: Readonly<Record<P3EligibilityReason, string>> = {
  ELIGIBLE: "来源可以使用",
  SOURCE_NOT_FOUND: "没有找到这个来源",
  SOURCE_TYPE_UNSUPPORTED: "当前不支持此来源类型",
  SOURCE_NOT_APPROVED: "来源尚未审核",
  SOURCE_ARCHIVED: "来源已归档",
  SOURCE_SUPERSEDED: "来源已被新版本替代",
  SOURCE_NOT_CURRENT: "这不是当前有效版本",
  SOURCE_FINGERPRINT_MISMATCH: "来源内容已经变化，请重新选择",
  SOURCE_TRACE_INCOMPLETE: "来源追踪信息不完整",
  RAW_BAD_CASE_NOT_ALLOWED: "原始 Bad Case 不能直接使用",
  BAD_CASE_CORRECTION_NOT_APPROVED: "Bad Case 修正尚未审核",
  SOURCE_STATE_INVALID: "来源当前状态不允许复用",
};

const P3_ERROR_LABELS: Readonly<Record<string, string>> = {
  P3_PROJECT_STATE_INVALID: "项目当前状态不允许执行此操作。",
  P3_PROJECT_ACTIVE_SOURCE_FROZEN: "项目激活后不能再修改来源。",
  P3_SOURCE_INELIGIBLE: "来源不符合复用条件，请检查审核和版本状态。",
  P3_SOURCE_STALE: "来源内容已经变化，请重新选择。",
  P3_ASSET_PROJECT_NOT_ACTIVE: "请先激活项目，再生成草稿。",
  P3_ASSET_SOURCE_STALE: "项目来源已变化，暂时不能生成草稿。",
  P3_REVIEW_ASSET_STATE_INVALID: "当前草稿还未提交审核，或状态不允许审核。",
  P3_REVIEW_CHECKLIST_INVALID: "批准前需要完成全部审核检查项。",
  P3_REVIEW_COMMENTS_REQUIRED: "退回修改或拒绝时必须填写审核意见。",
  P3_PUBLICATION_ASSET_NOT_APPROVED: "只有已批准版本才能发布；批准不等于发布。",
  P3_EXPORT_ASSET_NOT_PUBLISHED: "当前版本不是可导出的正式版本。",
  P3_EXPORT_ARTIFACT_REVOKED: "导出文件已撤回。",
  P3_LLM_DRAFT_DISABLED: "LLM 草稿功能当前未启用。",
  AUTHENTICATION_REQUIRED: "身份验证失败，请检查访问令牌。",
  AUTHENTICATION_INVALID: "身份验证失败，请检查访问令牌。",
  AUTHORIZATION_DENIED: "当前角色没有执行此操作的权限。",
};

export function p3ErrorLabel(code: string | null | undefined, status: number): string {
  if (status === 401) return "身份验证失败，请检查访问令牌。";
  if (status === 403) return "当前角色没有执行此操作的权限。";
  if (code && P3_ERROR_LABELS[code]) return P3_ERROR_LABELS[code];
  if (status === 404) return "对象不存在或已不可用。";
  if (status === 409) return "当前状态不允许执行此操作，请刷新后重试。";
  if (status === 422) return "输入内容不符合要求，请检查后重试。";
  if (status >= 500) return "服务暂时不可用，请稍后重试。";
  return "操作没有完成，请检查输入后重试。";
}

export function shortHash(value: string | null | undefined): string {
  if (!value) return "—";
  return value.length <= 12 ? value : `${value.slice(0, 8)}…${value.slice(-4)}`;
}
