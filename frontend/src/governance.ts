import type { AuthRole } from "./api";

export type FrontendPermission =
  | "p1.import"
  | "p1.clean"
  | "p1.revise"
  | "p1.review"
  | "p1.rag_sync"
  | "p1.read"
  | "p2.asset_upload"
  | "p2.extract"
  | "p2.revise"
  | "p2.review"
  | "p2.publish"
  | "p2.index"
  | "p2.embed"
  | "p2.serve"
  | "p2.archive"
  | "p2.read"
  | "retrieval.p1"
  | "retrieval.p2"
  | "retrieval.unified"
  | "agent.customerops"
  | "badcase.submit";

const ALL_PERMISSIONS: readonly FrontendPermission[] = [
  "p1.import", "p1.clean", "p1.revise", "p1.review", "p1.rag_sync", "p1.read",
  "p2.asset_upload", "p2.extract", "p2.revise", "p2.review", "p2.publish",
  "p2.index", "p2.embed", "p2.serve", "p2.archive", "p2.read",
  "retrieval.p1", "retrieval.p2", "retrieval.unified", "agent.customerops", "badcase.submit",
];

export const ROLE_LABELS: Record<AuthRole, string> = {
  admin: "管理员",
  cleaner: "清洗员",
  reviewer: "审核员",
  service: "服务账号",
  viewer: "只读访客",
};

export const ROLE_PERMISSIONS: Record<AuthRole, ReadonlySet<FrontendPermission>> = {
  admin: new Set(ALL_PERMISSIONS),
  cleaner: new Set([
    "p1.import", "p1.clean", "p1.revise", "p1.read",
    "p2.asset_upload", "p2.extract", "p2.revise", "p2.read",
  ]),
  reviewer: new Set(["p1.read", "p1.review", "p2.read", "p2.review"]),
  service: new Set([
    "retrieval.p1", "retrieval.p2", "retrieval.unified", "agent.customerops", "badcase.submit",
  ]),
  viewer: new Set(["p1.read", "p2.read", "retrieval.p1", "retrieval.p2"]),
};

export const FORBIDDEN_MESSAGE = "当前角色没有执行此操作的权限。";

export function can(role: AuthRole | null, permission: FrontendPermission): boolean {
  return role !== null && ROLE_PERMISSIONS[role].has(permission);
}

const ERROR_CODE_MESSAGES: Record<string, string> = {
  AUTHENTICATION_REQUIRED: "身份验证失败，请检查访问令牌。",
  AUTHENTICATION_INVALID: "身份验证失败，请检查访问令牌。",
  AUTHORIZATION_DENIED: FORBIDDEN_MESSAGE,
  ASSET_NOT_FOUND: "素材不存在或已不可用。",
  KNOWLEDGE_ASSET_NOT_FOUND: "知识资产不存在或已不可用。",
  KNOWLEDGE_INDEX_NOT_FOUND: "知识索引不存在或已不可用。",
  KNOWLEDGE_INDEX_NOT_READY: "知识索引尚未准备好，请先完成前置步骤。",
  KNOWLEDGE_INDEX_NOT_READY_FOR_SERVING: "向量尚未准备好，暂不能开放检索。",
  KNOWLEDGE_EMBEDDING_MISSING: "尚未生成向量，请先执行生成向量。",
  PENDING_REVIEW_EXISTS: "该内容已有待处理审核任务。",
  ASSET_DUPLICATE: "该素材已存在，无需重复上传。",
};

export function apiErrorMessage(body: any, status: number, fallback: string): string {
  if (status === 401) return "身份验证失败，请检查访问令牌。";
  if (status === 403) return FORBIDDEN_MESSAGE;
  const code = body?.detail?.code || body?.error?.code;
  if (typeof code === "string" && ERROR_CODE_MESSAGES[code]) return ERROR_CODE_MESSAGES[code];
  if (status === 404) return "对象不存在或已不可用。";
  if (status === 409) return "当前状态不允许此操作，请刷新后重试。";
  if (status === 422) return "输入内容不合法，请检查后重试。";
  if (status === 503) return "存储、Provider 或数据库暂不可用，请稍后重试。";
  return fallback;
}

export function permissionHint(role: AuthRole | null, permission: FrontendPermission): string | undefined {
  return can(role, permission) ? undefined : FORBIDDEN_MESSAGE;
}
