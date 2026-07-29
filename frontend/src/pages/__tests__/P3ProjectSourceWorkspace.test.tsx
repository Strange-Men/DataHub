import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { p3Client, P3ApiError } from "../../p3/client";
import type {
  P3ApiEnvelope,
  P3Project,
  P3SourceEligibilityDecision,
  P3SourceItem,
  P3SourceType,
} from "../../p3/types";
import { P3AssetReuse } from "../P3AssetReuse";

const authState = vi.hoisted(() => ({
  role: "cleaner" as "admin" | "cleaner" | "reviewer" | "service" | "viewer" | null,
  authMode: "disabled" as "disabled" | "token" | "unknown",
}));

vi.mock("../../auth/AuthContext", () => ({
  useAuth: () => ({
    ...authState,
    authenticated: authState.authMode === "token",
    loading: false,
    message: "",
    applyToken: vi.fn(),
    clearToken: vi.fn(),
    refreshPrincipal: vi.fn(),
    setMessage: vi.fn(),
  }),
}));

function envelope<T>(data: T, requestId = "req_test"): P3ApiEnvelope<T> {
  return { success: true, data, requestId };
}

function project(overrides: Partial<P3Project> = {}): P3Project {
  return {
    id: "project-1",
    name: "客服新人培训",
    description: "整理已审核客服知识",
    status: "draft",
    created_by_role: "cleaner",
    request_id: "req_project",
    created_at: "2026-07-29T01:00:00Z",
    updated_at: "2026-07-29T02:00:00Z",
    archived_at: null,
    ...overrides,
  };
}

function sourceItem(
  sourceType: P3SourceType = "P1_KNOWLEDGE",
  overrides: Partial<P3SourceItem> = {},
): P3SourceItem {
  return {
    id: `source-${sourceType}`,
    project_id: "project-1",
    source_type: sourceType,
    source_id: `${sourceType.toLowerCase()}-1`,
    source_version: 1,
    source_fingerprint: "abcdef1234567890",
    eligibility_policy_version: "p3-source-eligibility-v1",
    approved_review_id: "review-1",
    snapshot_id: sourceType === "P2_KNOWLEDGE_ASSET" ? "snapshot-1" : null,
    knowledge_asset_id: sourceType === "P2_KNOWLEDGE_ASSET" ? "asset-1" : null,
    lineage_manifest_hash: "lineage-123",
    source_trace: { safe: true, hidden_value: "do-not-render-full-trace" },
    selected_by_role: "cleaner",
    request_id: "req_source",
    created_at: "2026-07-29T02:00:00Z",
    removed_at: null,
    source_stale: false,
    ...overrides,
  };
}

function decision(
  sourceType: P3SourceType | "RAW_BAD_CASE" = "P1_KNOWLEDGE",
  overrides: Partial<P3SourceEligibilityDecision> = {},
): P3SourceEligibilityDecision {
  return {
    source_type: sourceType,
    source_id: `${sourceType.toLowerCase()}-1`,
    eligible: true,
    reason_code: "ELIGIBLE",
    source_status: "approved",
    source_version: 1,
    content_fingerprint: "abcdef1234567890",
    approved_review_id: "review-1",
    snapshot_id: sourceType === "P2_KNOWLEDGE_ASSET" ? "snapshot-1" : null,
    knowledge_asset_id: sourceType === "P2_KNOWLEDGE_ASSET" ? "asset-1" : null,
    lineage_complete: true,
    checked_conditions: ["approved"],
    policy_version: "p3-source-eligibility-v1",
    ...overrides,
  };
}

function mockWorkspace(initialProject = project(), initialSources: P3SourceItem[] = []) {
  vi.spyOn(p3Client, "listProjects").mockResolvedValue(envelope({
    items: [initialProject],
    total: 1,
    limit: 8,
    offset: 0,
  }));
  vi.spyOn(p3Client, "listSources").mockImplementation(async (_projectId, filters = {}) => {
    const visible = initialSources.filter((item) => {
      if (!filters.include_removed && item.removed_at) return false;
      if (filters.source_type && item.source_type !== filters.source_type) return false;
      if (filters.source_stale === true && !item.source_stale) return false;
      return true;
    });
    return envelope({
      items: visible.slice(filters.offset ?? 0, (filters.offset ?? 0) + (filters.limit ?? 12)),
      total: visible.length,
      limit: filters.limit ?? 12,
      offset: filters.offset ?? 0,
    });
  });
  vi.spyOn(p3Client, "createProject").mockResolvedValue(envelope(initialProject));
  vi.spyOn(p3Client, "checkSourceEligibility").mockResolvedValue(envelope({
    policy_version: "p3-source-eligibility-v1",
    decision: decision(),
  }));
  vi.spyOn(p3Client, "addSource").mockResolvedValue(envelope(sourceItem()));
  vi.spyOn(p3Client, "removeSource").mockResolvedValue(envelope(sourceItem("P1_KNOWLEDGE", {
    removed_at: "2026-07-29T03:00:00Z",
  })));
  vi.spyOn(p3Client, "revalidateSource").mockResolvedValue(envelope({
    source_item_id: "source-P1_KNOWLEDGE",
    project_id: "project-1",
    status: "valid",
    eligible: true,
    reason_code: "ELIGIBLE",
    source_stale: false,
  }));
  vi.spyOn(p3Client, "revalidateProjectSources").mockResolvedValue(envelope({
    project_id: "project-1",
    results: [],
    total: initialSources.length,
    limit: 100,
  }));
  vi.spyOn(p3Client, "activateProject").mockResolvedValue(envelope(project({ status: "active" })));
  vi.spyOn(p3Client, "archiveProject").mockResolvedValue(envelope(project({
    status: "archived",
    archived_at: "2026-07-29T04:00:00Z",
  })));
  vi.spyOn(p3Client, "listAssets").mockResolvedValue(envelope({
    items: [],
    total: 0,
    limit: 12,
    offset: 0,
  }));
  vi.spyOn(p3Client, "listReviews").mockResolvedValue(envelope({
    items: [],
    total: 0,
    limit: 100,
    offset: 0,
  }));
}

async function selectInitialProject(user: ReturnType<typeof userEvent.setup>) {
  await screen.findByRole("button", { name: /客服新人培训/ });
  await user.click(screen.getByRole("button", { name: /客服新人培训/ }));
  await screen.findByRole("heading", { name: "检查治理来源" });
}

function eligibilityForm() {
  const section = screen.getByRole("heading", { name: "检查治理来源" }).closest("section");
  if (!section) throw new Error("Eligibility section was not rendered.");
  return within(section);
}

describe("P3 project and governed source workspace", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    authState.role = "cleaner";
    authState.authMode = "disabled";
  });

  it("loads paged projects and keeps a stable idempotency key across a manual retry", async () => {
    mockWorkspace();
    const create = vi.spyOn(p3Client, "createProject")
      .mockRejectedValueOnce(new P3ApiError(503, "P3_STORAGE_UNAVAILABLE", "req_fail"))
      .mockResolvedValueOnce(envelope(project({ id: "project-new", name: "售后 SOP" })));
    const user = userEvent.setup();
    render(<P3AssetReuse />);

    expect(await screen.findByText("共 1 个项目")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "新建项目" }));
    await user.type(screen.getByLabelText("项目名称"), "售后 SOP");
    await user.click(screen.getByRole("button", { name: "创建并进入项目" }));
    expect(await screen.findByText("服务暂时不可用，请稍后重试。")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "创建并进入项目" }));

    await waitFor(() => expect(create).toHaveBeenCalledTimes(2));
    const firstKey = create.mock.calls[0][0].idempotency_key;
    const secondKey = create.mock.calls[1][0].idempotency_key;
    expect(firstKey).toMatch(/^p3-ui-create-project-/);
    expect(secondKey).toBe(firstKey);
  });

  it.each([
    "P1_KNOWLEDGE",
    "P2_KNOWLEDGE_ASSET",
    "APPROVED_BAD_CASE_CORRECTION",
  ] as const)("checks and adds eligible %s without accepting caller governance fields", async (sourceType) => {
    mockWorkspace();
    const checkedDecision = decision(sourceType);
    vi.spyOn(p3Client, "checkSourceEligibility").mockResolvedValue(envelope({
      policy_version: checkedDecision.policy_version,
      decision: checkedDecision,
    }));
    const add = vi.spyOn(p3Client, "addSource").mockResolvedValue(envelope(sourceItem(sourceType)));
    const user = userEvent.setup();
    render(<P3AssetReuse />);
    await selectInitialProject(user);

    await user.selectOptions(eligibilityForm().getByLabelText("来源类型"), sourceType);
    await user.type(eligibilityForm().getByLabelText("来源 ID"), checkedDecision.source_id);
    await user.click(eligibilityForm().getByRole("button", { name: "检查是否可用" }));
    expect(await screen.findByText("来源可以使用")).toBeVisible();
    expect(eligibilityForm().getByLabelText("来源类型")).toHaveValue(sourceType);
    await user.click(screen.getByRole("button", { name: "添加到项目" }));

    await waitFor(() => expect(add).toHaveBeenCalled());
    expect(add.mock.calls[0][1]).toEqual({
      source_type: sourceType,
      source_id: checkedDecision.source_id,
      source_version: 1,
      expected_fingerprint: "abcdef1234567890",
    });
    expect(Object.keys(add.mock.calls[0][1]).sort()).toEqual([
      "expected_fingerprint",
      "source_id",
      "source_type",
      "source_version",
    ]);
  });

  it("shows ineligible and raw Bad Case reasons as HTTP 200 business outcomes", async () => {
    mockWorkspace();
    vi.spyOn(p3Client, "checkSourceEligibility").mockResolvedValue(envelope({
      policy_version: "p3-source-eligibility-v1",
      decision: decision("RAW_BAD_CASE", {
        eligible: false,
        reason_code: "RAW_BAD_CASE_NOT_ALLOWED",
        source_status: null,
        source_version: null,
        content_fingerprint: null,
        approved_review_id: null,
        lineage_complete: false,
      }),
    }));
    const user = userEvent.setup();
    render(<P3AssetReuse />);
    await selectInitialProject(user);

    await user.selectOptions(eligibilityForm().getByLabelText("来源类型"), "RAW_BAD_CASE");
    await user.type(eligibilityForm().getByLabelText("来源 ID"), "raw_bad_case-1");
    await user.click(eligibilityForm().getByRole("button", { name: "检查是否可用" }));

    expect(await screen.findByText("原始 Bad Case 不能直接使用")).toBeVisible();
    expect(screen.queryByRole("button", { name: "添加到项目" })).not.toBeInTheDocument();
  });

  it("supports stale filtering, revalidation and logical removal without exposing Source Trace", async () => {
    const stale = sourceItem("P1_KNOWLEDGE", { source_stale: true });
    mockWorkspace(project(), [stale]);
    const user = userEvent.setup();
    render(<P3AssetReuse />);
    await selectInitialProject(user);

    expect(await screen.findByText("来源已变化")).toBeVisible();
    expect(screen.queryByText("do-not-render-full-trace")).not.toBeInTheDocument();
    await user.click(screen.getByRole("switch", { name: "只看异常来源" }));
    expect(p3Client.listSources).toHaveBeenCalledWith(
      "project-1",
      expect.objectContaining({ source_stale: true }),
      expect.anything(),
    );
    await user.click(screen.getByRole("button", { name: "重新验证" }));
    await waitFor(() => expect(p3Client.revalidateSource).toHaveBeenCalled());
    await user.click(screen.getByRole("button", { name: "从项目移除" }));
    const dialog = screen.getByRole("dialog", { name: "从项目中移除这个来源？" });
    await user.click(within(dialog).getByRole("button", { name: "确认移除" }));
    await waitFor(() => expect(p3Client.removeSource).toHaveBeenCalled());
  });

  it("enforces activation checks and freezes source controls after activation", async () => {
    mockWorkspace(project(), [sourceItem()]);
    const user = userEvent.setup();
    render(<P3AssetReuse />);
    await selectInitialProject(user);

    expect(await screen.findByText("项目可以激活")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "激活项目" }));
    const dialog = screen.getByRole("dialog", { name: "激活这个复用项目？" });
    await user.click(within(dialog).getByRole("button", { name: "确认激活" }));

    expect(await screen.findByText("项目已激活，来源选择已冻结。")).toBeVisible();
    expect(screen.getByRole("button", { name: "检查是否可用" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: "从项目移除" })).not.toBeInTheDocument();
  });

  it("keeps archived projects read-only and hides mutation controls from viewer/service roles", async () => {
    authState.role = "viewer";
    mockWorkspace(project({ status: "archived" }), [sourceItem()]);
    const user = userEvent.setup();
    render(<P3AssetReuse />);
    await selectInitialProject(user);

    expect(await screen.findByText("项目已归档。")).toBeVisible();
    expect(screen.getByRole("button", { name: "新建项目" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "检查是否可用" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: "重新验证" })).not.toBeInTheDocument();
  });

  it("shows safe 401/403 feedback and supports an empty disabled-auth workspace", async () => {
    vi.spyOn(p3Client, "listProjects").mockRejectedValue(
      new P3ApiError(403, "AUTHORIZATION_DENIED", "req_forbidden"),
    );
    const { unmount } = render(<P3AssetReuse />);
    expect(await screen.findByText("当前角色没有执行此操作的权限。")).toBeVisible();
    await userEvent.click(within(screen.getByRole("alert")).getByText("技术详情"));
    expect(screen.getByText("req_forbidden")).toBeVisible();
    unmount();

    vi.restoreAllMocks();
    authState.role = "admin";
    authState.authMode = "disabled";
    vi.spyOn(p3Client, "listProjects").mockResolvedValue(envelope({
      items: [],
      total: 0,
      limit: 8,
      offset: 0,
    }));
    render(<P3AssetReuse />);
    expect(await screen.findByText("还没有复用项目")).toBeVisible();
    expect(screen.getByText("创建第一个项目后，即可选择已审核的治理知识。")).toBeVisible();
  });
});
