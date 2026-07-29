import { apiFetch, apiPath } from "../api";
import { p3ErrorLabel } from "./presentation";
import type {
  JsonObject,
  P3ApiEnvelope,
  P3ApiErrorBody,
  P3AssetGenerateInput,
  P3AssetSourceSnapshot,
  P3AssetStatus,
  P3AssetType,
  P3AssetVersion,
  P3ExportArtifact,
  P3ExportFormat,
  P3ExportJob,
  P3ExportOutcome,
  P3ExportRevokeOutcome,
  P3ExportStatus,
  P3LlmAssetGenerateInput,
  P3Pagination,
  P3Project,
  P3ProjectCreateInput,
  P3ProjectRevalidation,
  P3ProjectStatus,
  P3ProjectUpdateInput,
  P3PublicationOutcome,
  P3PublishedAsset,
  P3Review,
  P3ReviewChecklist,
  P3ReviewDecision,
  P3SourceAddInput,
  P3SourceEligibilityBatchData,
  P3SourceEligibilityData,
  P3SourceEligibilityInput,
  P3SourceItem,
  P3SourceRevalidation,
  P3SourceType,
} from "./types";

type QueryValue = string | number | boolean | null | undefined;
type RequestOptions = {
  signal?: AbortSignal;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isApiEnvelope(value: unknown): value is P3ApiEnvelope<unknown> {
  return (
    isRecord(value)
    && value.success === true
    && "data" in value
    && typeof value.requestId === "string"
  );
}

function errorDetail(value: unknown): { code?: string; message?: string; requestId?: string } {
  if (!isRecord(value)) return {};
  const body = value as P3ApiErrorBody;
  const detail = body.detail ?? body.error;
  return {
    code: typeof detail?.code === "string" ? detail.code : undefined,
    message: typeof detail?.message === "string" ? detail.message : undefined,
    requestId: typeof body.requestId === "string" ? body.requestId : undefined,
  };
}

async function responseBody(response: Response): Promise<unknown> {
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("json")) return null;
  try {
    return await response.json() as unknown;
  } catch {
    return null;
  }
}

export class P3ApiError extends Error {
  readonly code?: string;
  readonly requestId?: string;
  readonly status: number;

  constructor(status: number, code?: string, requestId?: string) {
    super(p3ErrorLabel(code, status));
    this.name = "P3ApiError";
    this.status = status;
    this.code = code;
    this.requestId = requestId;
  }
}

function queryString(values: Record<string, QueryValue>): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) {
    if (value !== undefined && value !== null && value !== "") {
      params.set(key, String(value));
    }
  }
  const encoded = params.toString();
  return encoded ? `?${encoded}` : "";
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  options: RequestOptions = {},
): Promise<P3ApiEnvelope<T>> {
  const headers = new Headers(init.headers);
  if (init.body !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await apiFetch(apiPath(path), {
    ...init,
    headers,
    signal: options.signal,
  });
  const body = await responseBody(response);
  if (!response.ok) {
    const detail = errorDetail(body);
    throw new P3ApiError(response.status, detail.code, detail.requestId);
  }
  if (!isApiEnvelope(body)) {
    throw new P3ApiError(502, "P3_FRONTEND_RESPONSE_INVALID");
  }
  return body as P3ApiEnvelope<T>;
}

function jsonBody(value: object): string {
  return JSON.stringify(value);
}

export const p3Client = {
  checkSourceEligibility(input: P3SourceEligibilityInput, options: RequestOptions = {}) {
    return request<P3SourceEligibilityData>(
      "/api/p3/source-eligibility/check",
      { method: "POST", body: jsonBody(input) },
      options,
    );
  },

  checkSourceEligibilityBatch(sources: P3SourceEligibilityInput[], options: RequestOptions = {}) {
    return request<P3SourceEligibilityBatchData>(
      "/api/p3/source-eligibility/check-batch",
      { method: "POST", body: jsonBody({ sources }) },
      options,
    );
  },

  createProject(input: P3ProjectCreateInput, options: RequestOptions = {}) {
    return request<P3Project>(
      "/api/p3/reuse-projects",
      { method: "POST", body: jsonBody(input) },
      options,
    );
  },

  listProjects(
    filters: { limit?: number; offset?: number; status?: P3ProjectStatus } = {},
    options: RequestOptions = {},
  ) {
    return request<P3Pagination<P3Project>>(
      `/api/p3/reuse-projects${queryString(filters)}`,
      {},
      options,
    );
  },

  getProject(projectId: string, options: RequestOptions = {}) {
    return request<P3Project>(`/api/p3/reuse-projects/${projectId}`, {}, options);
  },

  updateProject(projectId: string, input: P3ProjectUpdateInput, options: RequestOptions = {}) {
    return request<P3Project>(
      `/api/p3/reuse-projects/${projectId}`,
      { method: "PATCH", body: jsonBody(input) },
      options,
    );
  },

  activateProject(projectId: string, options: RequestOptions = {}) {
    return request<P3Project>(
      `/api/p3/reuse-projects/${projectId}/activate`,
      { method: "POST" },
      options,
    );
  },

  archiveProject(projectId: string, options: RequestOptions = {}) {
    return request<P3Project>(
      `/api/p3/reuse-projects/${projectId}/archive`,
      { method: "POST" },
      options,
    );
  },

  addSource(projectId: string, input: P3SourceAddInput, options: RequestOptions = {}) {
    return request<P3SourceItem>(
      `/api/p3/reuse-projects/${projectId}/sources`,
      { method: "POST", body: jsonBody(input) },
      options,
    );
  },

  listSources(
    projectId: string,
    filters: {
      limit?: number;
      offset?: number;
      include_removed?: boolean;
      source_type?: P3SourceType;
      source_stale?: boolean;
    } = {},
    options: RequestOptions = {},
  ) {
    return request<P3Pagination<P3SourceItem>>(
      `/api/p3/reuse-projects/${projectId}/sources${queryString(filters)}`,
      {},
      options,
    );
  },

  getSource(projectId: string, sourceItemId: string, options: RequestOptions = {}) {
    return request<P3SourceItem>(
      `/api/p3/reuse-projects/${projectId}/sources/${sourceItemId}`,
      {},
      options,
    );
  },

  removeSource(projectId: string, sourceItemId: string, options: RequestOptions = {}) {
    return request<P3SourceItem>(
      `/api/p3/reuse-projects/${projectId}/sources/${sourceItemId}`,
      { method: "DELETE" },
      options,
    );
  },

  revalidateSource(projectId: string, sourceItemId: string, options: RequestOptions = {}) {
    return request<P3SourceRevalidation>(
      `/api/p3/reuse-projects/${projectId}/sources/${sourceItemId}/revalidate`,
      { method: "POST" },
      options,
    );
  },

  revalidateProjectSources(projectId: string, limit = 100, options: RequestOptions = {}) {
    return request<P3ProjectRevalidation>(
      `/api/p3/reuse-projects/${projectId}/sources/revalidate`,
      { method: "POST", body: jsonBody({ limit }) },
      options,
    );
  },

  generateDeterministicDraft(projectId: string, input: P3AssetGenerateInput, options: RequestOptions = {}) {
    return request<P3AssetVersion>(
      `/api/p3/reuse-projects/${projectId}/assets/generate`,
      { method: "POST", body: jsonBody(input) },
      options,
    );
  },

  generateLlmDraft(projectId: string, input: P3LlmAssetGenerateInput, options: RequestOptions = {}) {
    return request<P3AssetVersion>(
      `/api/p3/reuse-projects/${projectId}/assets/generate-llm-draft`,
      { method: "POST", body: jsonBody(input) },
      options,
    );
  },

  listAssets(
    projectId: string,
    filters: { limit?: number; offset?: number; asset_type?: P3AssetType; status?: P3AssetStatus } = {},
    options: RequestOptions = {},
  ) {
    return request<P3Pagination<P3AssetVersion>>(
      `/api/p3/reuse-projects/${projectId}/assets${queryString(filters)}`,
      {},
      options,
    );
  },

  getAsset(projectId: string, assetVersionId: string, options: RequestOptions = {}) {
    return request<P3AssetVersion>(
      `/api/p3/reuse-projects/${projectId}/assets/${assetVersionId}`,
      {},
      options,
    );
  },

  listAssetSources(
    projectId: string,
    assetVersionId: string,
    filters: { limit?: number; offset?: number } = {},
    options: RequestOptions = {},
  ) {
    return request<P3Pagination<P3AssetSourceSnapshot>>(
      `/api/p3/reuse-projects/${projectId}/assets/${assetVersionId}/sources${queryString(filters)}`,
      {},
      options,
    );
  },

  createRevision(
    projectId: string,
    assetVersionId: string,
    contentPayload: JsonObject,
    idempotencyKey: string,
    options: RequestOptions = {},
  ) {
    return request<P3AssetVersion>(
      `/api/p3/reuse-projects/${projectId}/assets/${assetVersionId}/revisions`,
      {
        method: "POST",
        body: jsonBody({ content_payload: contentPayload, idempotency_key: idempotencyKey }),
      },
      options,
    );
  },

  submitReview(projectId: string, assetVersionId: string, idempotencyKey: string, options: RequestOptions = {}) {
    return request<P3AssetVersion>(
      `/api/p3/reuse-projects/${projectId}/assets/${assetVersionId}/submit-review`,
      { method: "POST", body: jsonBody({ idempotency_key: idempotencyKey }) },
      options,
    );
  },

  decideReview(
    projectId: string,
    assetVersionId: string,
    input: {
      decision: P3ReviewDecision;
      comments?: string | null;
      checklist: P3ReviewChecklist;
      idempotency_key: string;
    },
    options: RequestOptions = {},
  ) {
    return request<P3Review>(
      `/api/p3/reuse-projects/${projectId}/assets/${assetVersionId}/review`,
      { method: "POST", body: jsonBody(input) },
      options,
    );
  },

  getReview(projectId: string, assetVersionId: string, options: RequestOptions = {}) {
    return request<P3Review>(
      `/api/p3/reuse-projects/${projectId}/assets/${assetVersionId}/reviews`,
      {},
      options,
    );
  },

  listReviews(
    projectId: string,
    filters: {
      decision?: P3ReviewDecision;
      asset_type?: P3AssetType;
      limit?: number;
      offset?: number;
    } = {},
    options: RequestOptions = {},
  ) {
    return request<P3Pagination<P3Review>>(
      `/api/p3/reuse-projects/${projectId}/reviews${queryString(filters)}`,
      {},
      options,
    );
  },

  publishAsset(projectId: string, assetVersionId: string, idempotencyKey: string, options: RequestOptions = {}) {
    return request<P3PublicationOutcome>(
      `/api/p3/reuse-projects/${projectId}/assets/${assetVersionId}/publish`,
      { method: "POST", body: jsonBody({ idempotency_key: idempotencyKey }) },
      options,
    );
  },

  archiveAsset(projectId: string, assetVersionId: string, idempotencyKey: string, options: RequestOptions = {}) {
    return request<P3PublicationOutcome>(
      `/api/p3/reuse-projects/${projectId}/assets/${assetVersionId}/archive`,
      { method: "POST", body: jsonBody({ idempotency_key: idempotencyKey }) },
      options,
    );
  },

  listPublishedAssets(
    projectId: string,
    filters: { asset_type?: P3AssetType; limit?: number; offset?: number } = {},
    options: RequestOptions = {},
  ) {
    return request<P3Pagination<P3PublishedAsset>>(
      `/api/p3/reuse-projects/${projectId}/published-assets${queryString(filters)}`,
      {},
      options,
    );
  },

  getPublishedAsset(projectId: string, assetType: P3AssetType, options: RequestOptions = {}) {
    return request<P3PublishedAsset>(
      `/api/p3/reuse-projects/${projectId}/published-assets/${assetType}`,
      {},
      options,
    );
  },

  createExport(
    projectId: string,
    assetVersionId: string,
    exportFormat: P3ExportFormat,
    idempotencyKey: string,
    options: RequestOptions = {},
  ) {
    return request<P3ExportOutcome>(
      `/api/p3/reuse-projects/${projectId}/assets/${assetVersionId}/exports`,
      {
        method: "POST",
        body: jsonBody({ export_format: exportFormat, idempotency_key: idempotencyKey }),
      },
      options,
    );
  },

  listExports(
    projectId: string,
    filters: { export_format?: P3ExportFormat; status?: P3ExportStatus; limit?: number; offset?: number } = {},
    options: RequestOptions = {},
  ) {
    return request<P3Pagination<P3ExportJob>>(
      `/api/p3/reuse-projects/${projectId}/exports${queryString(filters)}`,
      {},
      options,
    );
  },

  getExportJob(exportJobId: string, options: RequestOptions = {}) {
    return request<P3ExportJob>(`/api/p3/exports/${exportJobId}`, {}, options);
  },

  getExportArtifact(exportJobId: string, options: RequestOptions = {}) {
    return request<P3ExportArtifact>(
      `/api/p3/exports/${exportJobId}/artifact`,
      {},
      options,
    );
  },

  async downloadArtifact(artifactId: string, options: RequestOptions = {}) {
    const response = await apiFetch(
      apiPath(`/api/p3/export-artifacts/${artifactId}/download`),
      { signal: options.signal },
    );
    if (!response.ok) {
      const body = await responseBody(response);
      const detail = errorDetail(body);
      throw new P3ApiError(response.status, detail.code, detail.requestId);
    }
    return {
      blob: await response.blob(),
      contentDisposition: response.headers.get("content-disposition"),
    };
  },

  revokeExport(exportJobId: string, idempotencyKey: string, options: RequestOptions = {}) {
    return request<P3ExportRevokeOutcome>(
      `/api/p3/exports/${exportJobId}/revoke`,
      { method: "POST", body: jsonBody({ idempotency_key: idempotencyKey }) },
      options,
    );
  },
};
