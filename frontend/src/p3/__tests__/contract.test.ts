import { setAuthSession } from "../../api";
import { p3Client } from "../client";
import { createP3IdempotencyKey } from "../idempotency";
import {
  P3_ASSET_STATUS_LABELS,
  P3_ELIGIBILITY_REASON_LABELS,
  P3_EXPORT_STATUS_LABELS,
  P3_PROJECT_STATUS_LABELS,
  P3_SOURCE_STATUS_LABELS,
  p3ErrorLabel,
} from "../presentation";

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("P3 frontend contract", () => {
  it("uses centralized Chinese lifecycle labels", () => {
    expect(P3_PROJECT_STATUS_LABELS).toEqual({
      draft: "草稿项目",
      active: "已激活",
      archived: "已归档",
    });
    expect(P3_ASSET_STATUS_LABELS.approved).toBe("已批准");
    expect(P3_ASSET_STATUS_LABELS.published).toBe("已发布");
    expect(P3_EXPORT_STATUS_LABELS.revoked).toBe("已撤回");
    expect(P3_SOURCE_STATUS_LABELS.stale).toBe("来源已变化");
  });

  it("maps governed source and workflow errors to user-facing Chinese", () => {
    expect(P3_ELIGIBILITY_REASON_LABELS.SOURCE_NOT_APPROVED).toBe("来源尚未审核");
    expect(P3_ELIGIBILITY_REASON_LABELS.RAW_BAD_CASE_NOT_ALLOWED).toBe(
      "原始 Bad Case 不能直接使用",
    );
    expect(p3ErrorLabel("P3_LLM_DRAFT_DISABLED", 503)).toBe(
      "LLM 草稿功能当前未启用。",
    );
    expect(p3ErrorLabel("P3_EXPORT_ARTIFACT_REVOKED", 409)).toBe(
      "导出文件已撤回。",
    );
  });

  it("creates bounded client-owned idempotency keys", () => {
    const key = createP3IdempotencyKey("create project");
    expect(key).toMatch(/^p3-ui-create-project-[0-9a-f-]+$/);
    expect(createP3IdempotencyKey("create project")).not.toBe(key);
    expect(key.length).toBeLessThanOrEqual(200);
  });

  it("uses the source eligibility path and exact request fields", async () => {
    const fetchMock = vi.spyOn(window, "fetch").mockResolvedValue(jsonResponse({
      success: true,
      data: {
        policy_version: "p3-source-eligibility-v1",
        decision: {
          source_type: "P1_KNOWLEDGE",
          source_id: "candidate-1",
          eligible: true,
          reason_code: "ELIGIBLE",
          source_status: "approved",
          source_version: 1,
          content_fingerprint: "abc",
          approved_review_id: "review-1",
          snapshot_id: null,
          knowledge_asset_id: null,
          lineage_complete: true,
          checked_conditions: [],
          policy_version: "p3-source-eligibility-v1",
        },
      },
      requestId: "req_1",
    }));

    await p3Client.checkSourceEligibility({
      source_type: "P1_KNOWLEDGE",
      source_id: "candidate-1",
      expected_fingerprint: "abc",
    });

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url).endsWith("/api/p3/source-eligibility/check")).toBe(true);
    expect(JSON.parse(String(init?.body))).toEqual({
      source_type: "P1_KNOWLEDGE",
      source_id: "candidate-1",
      expected_fingerprint: "abc",
    });
  });

  it("uses governed M1-M7 paths and keeps tokens out of URLs", async () => {
    setAuthSession("secret-test-token");
    const fetchMock = vi.spyOn(window, "fetch").mockResolvedValue(jsonResponse({
      success: true,
      data: {
        items: [],
        total: 0,
        limit: 20,
        offset: 0,
      },
      requestId: "req_2",
    }));

    const controller = new AbortController();
    await p3Client.listAssets(
      "project-1",
      { limit: 20, status: "pending_review" },
      { signal: controller.signal },
    );

    const [url, init] = fetchMock.mock.calls[0];
    const requestUrl = String(url);
    expect(requestUrl).toContain(
      "/api/p3/reuse-projects/project-1/assets?limit=20&status=pending_review",
    );
    expect(requestUrl).not.toContain("secret-test-token");
    expect(new Headers(init?.headers).get("Authorization")).toBe(
      "Bearer secret-test-token",
    );
    expect(init?.signal).toBe(controller.signal);
  });

  it("sends required idempotency keys for write operations", async () => {
    const fetchMock = vi.spyOn(window, "fetch").mockResolvedValue(jsonResponse({
      success: true,
      data: {
        id: "project-1",
        name: "新员工培训",
        description: null,
        status: "draft",
        created_by_role: "cleaner",
        request_id: "req_3",
        created_at: "2026-07-29T00:00:00Z",
        updated_at: "2026-07-29T00:00:00Z",
        archived_at: null,
      },
      requestId: "req_3",
    }, 201));

    await p3Client.createProject({
      name: "新员工培训",
      idempotency_key: "p3-ui-create-project-123",
    });

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url).endsWith("/api/p3/reuse-projects")).toBe(true);
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body)).idempotency_key).toBe(
      "p3-ui-create-project-123",
    );
  });

  it("preserves stable error code, request id and HTTP status", async () => {
    vi.spyOn(window, "fetch").mockResolvedValue(jsonResponse({
      detail: { code: "P3_LLM_DRAFT_DISABLED", message: "disabled" },
      requestId: "req_disabled",
    }, 503));

    await expect(p3Client.generateLlmDraft("project-1", {
      asset_type: "sop",
      idempotency_key: "p3-ui-llm-1",
    })).rejects.toMatchObject({
      name: "P3ApiError",
      status: 503,
      code: "P3_LLM_DRAFT_DISABLED",
      requestId: "req_disabled",
      message: "LLM 草稿功能当前未启用。",
    });
  });
});
