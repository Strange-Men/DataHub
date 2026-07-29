import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AssetGenerationPanel } from "../../p3/components/AssetGenerationPanel";
import { AssetVersionList } from "../../p3/components/AssetVersionList";
import { ReviewWorkspace } from "../../p3/components/ReviewWorkspace";
import { StructuredAssetViewer } from "../../p3/components/StructuredAssetViewer";
import { StructuredRevisionEditor } from "../../p3/components/StructuredRevisionEditor";
import type {
  JsonObject,
  P3AssetSourceSnapshot,
  P3AssetType,
  P3AssetVersion,
  P3Project,
  P3Review,
} from "../../p3/types";

const sourceRef: JsonObject = {
  source_item_id: "source-item-1",
  source_type: "P1_KNOWLEDGE",
  source_id: "knowledge-1",
  source_version: 1,
  approved_review_id: "review-source-1",
  snapshot_id: null,
  knowledge_asset_id: null,
  content_fingerprint: "fingerprint-123",
  lineage_manifest_hash: "lineage-123",
};

const sourceSnapshot: P3AssetSourceSnapshot = {
  id: "asset-source-1",
  asset_version_id: "asset-1",
  source_item_id: "source-item-1",
  source_type: "P1_KNOWLEDGE",
  source_id: "knowledge-1",
  source_version: 1,
  source_fingerprint: "fingerprint-123",
  approved_review_id: "review-source-1",
  snapshot_id: null,
  knowledge_asset_id: null,
  lineage_manifest_hash: "lineage-123",
  source_trace_snapshot: { schema_version: "p3-source-trace-v1" },
  created_at: "2026-07-30T01:00:00Z",
};

const payloads: Record<P3AssetType, JsonObject> = {
  training_material: {
    title: "新人培训",
    learning_objectives: ["理解退款规则"],
    sections: [{ heading: "退款流程", content: "先核验订单。", source_refs: [sourceRef] }],
    key_points: ["不得无依据承诺"],
    source_refs: [sourceRef],
  },
  sop: {
    title: "退款 SOP",
    purpose: "规范退款处理",
    scope: "客服团队",
    prerequisites: ["订单信息完整"],
    steps: [{ order: 1, instruction: "核验订单", source_refs: [sourceRef] }],
    cautions: ["保护隐私"],
    escalation_rules: ["异常订单升级"],
    source_refs: [sourceRef],
  },
  service_script: {
    title: "退款话术",
    scenario: "用户申请退款",
    opening: "您好，我来协助处理。",
    response_steps: [{ order: 1, response: "请提供订单号。", source_refs: [sourceRef] }],
    prohibited_claims: ["不得承诺即时到账"],
    escalation: ["异常情况转人工"],
    source_refs: [sourceRef],
  },
  qa_bank: {
    title: "退款问答",
    items: [{ question: "多久退款？", answer: "以审核结果为准。", source_refs: [sourceRef] }],
    source_refs: [sourceRef],
  },
  sft_dataset: {
    records: [{
      instruction: "回答退款时效",
      input: "用户询问多久到账",
      output: "以审核结果为准。",
      metadata: { intent: "refund" },
      source_refs: [sourceRef],
    }],
  },
};

function asset(
  assetType: P3AssetType = "training_material",
  overrides: Partial<P3AssetVersion> = {},
): P3AssetVersion {
  return {
    id: "asset-1",
    project_id: "project-1",
    asset_type: assetType,
    version_number: 1,
    status: "generated",
    generation_mode: "deterministic_template",
    template_key: `${assetType}_v1`,
    template_version: "v1",
    content_payload: payloads[assetType],
    content_hash: "content-hash-123456",
    source_manifest_hash: "manifest-hash-123456",
    parent_asset_version_id: null,
    created_by_role: "cleaner",
    request_id: "req_asset",
    created_at: "2026-07-30T01:00:00Z",
    updated_at: "2026-07-30T01:00:00Z",
    approved_at: null,
    published_at: null,
    failure_code: null,
    failure_message: null,
    ...overrides,
  };
}

function project(): P3Project {
  return {
    id: "project-1",
    name: "客服培训",
    description: null,
    status: "active",
    created_by_role: "cleaner",
    request_id: "req_project",
    created_at: "2026-07-30T00:00:00Z",
    updated_at: "2026-07-30T00:00:00Z",
    archived_at: null,
  };
}

function review(decision: "approved" | "needs_revision" | "rejected" = "approved"): P3Review {
  return {
    id: "review-1",
    asset_version_id: "asset-1",
    decision,
    comments: decision === "approved" ? "结构与引用有效" : "请修订内容",
    checklist_payload: {
      structure_complete: true,
      source_refs_valid: true,
      no_unsupported_claims_confirmed: true,
      safe_for_reuse: true,
    },
    review_policy_version: "p3-review-v1",
    reviewed_content_hash: "content-hash-123456",
    reviewed_source_manifest_hash: "manifest-hash-123456",
    reviewer_role: "reviewer",
    request_id: "req_review",
    created_at: "2026-07-30T02:00:00Z",
  };
}

describe("P3 draft, revision and review workspace", () => {
  it("offers all five deterministic asset types and keeps disabled LLM from sending requests", async () => {
    const user = userEvent.setup();
    const onGenerate = vi.fn().mockResolvedValue(asset());
    const onGenerateLlm = vi.fn();
    render(
      <AssetGenerationPanel
        role="cleaner"
        project={project()}
        busy={false}
        onGenerate={onGenerate}
        onGenerateLlm={onGenerateLlm}
      />,
    );

    for (const label of ["培训材料", "SOP", "客服话术", "问答题库", "SFT 数据集"]) {
      expect(screen.getByRole("radio", { name: new RegExp(label) })).toBeEnabled();
    }
    await user.click(screen.getByRole("radio", { name: /SOP/ }));
    await user.click(screen.getByRole("button", { name: "生成SOP草稿" }));
    expect(onGenerate).toHaveBeenCalledWith("sop", expect.stringMatching(/^p3-ui-generate-draft-/));
    expect(screen.getByRole("button", { name: "当前环境未启用" })).toBeDisabled();
    expect(screen.getByText("当前环境未启用，不会发送 Provider 请求。")).toBeVisible();
    expect(onGenerateLlm).not.toHaveBeenCalled();
  });

  it("renders paged version summaries without raw payloads in the list", () => {
    const onSelect = vi.fn();
    render(
      <AssetVersionList
        assets={[
          asset("sop"),
          asset("qa_bank", {
            id: "asset-2",
            version_number: 2,
            generation_mode: "manual_revision",
            parent_asset_version_id: "asset-1",
            status: "pending_review",
          }),
        ]}
        total={2}
        offset={0}
        pageSize={12}
        filters={{}}
        selectedAsset={null}
        loading={false}
        onFilters={vi.fn()}
        onPage={vi.fn()}
        onSelect={onSelect}
      />,
    );
    expect(screen.getByText("确定性模板")).toBeVisible();
    expect(screen.getByText(/人工修订 · 基于上一版本修订/)).toBeVisible();
    expect(screen.queryByText("content_payload")).not.toBeInTheDocument();
  });

  it.each([
    ["training_material", "新人培训", "学习目标"],
    ["sop", "退款 SOP", "操作步骤"],
    ["service_script", "退款话术", "回复步骤"],
    ["qa_bank", "退款问答", "多久退款？"],
    ["sft_dataset", "SFT 数据集草稿", "回答退款时效"],
  ] as const)("shows structured %s content with folded technical JSON", (assetType, title, detail) => {
    render(
      <StructuredAssetViewer
        asset={asset(assetType)}
        sources={[sourceSnapshot]}
        loading={false}
      />,
    );
    expect(screen.getByText(title)).toBeVisible();
    expect(screen.getByText(detail)).toBeVisible();
    const technical = screen.getByText("技术详情与只读 JSON");
    expect(technical.closest("details")).not.toHaveAttribute("open");
    expect(screen.queryByText("p3-source-trace-v1")).not.toBeInTheDocument();
  });

  it.each([
    ["training_material", "标题", "新人培训（修订）"],
    ["sop", "目的", "规范退款与升级"],
    ["service_script", "场景", "用户催促退款"],
    ["qa_bank", "问题", "退款需要哪些材料？"],
    ["sft_dataset", "instruction", "解释退款材料"],
  ] as const)("edits %s through structured fields and creates a child version", async (
    assetType,
    fieldLabel,
    value,
  ) => {
    const user = userEvent.setup();
    const onSave = vi.fn().mockResolvedValue(asset(assetType, {
      id: "asset-2",
      version_number: 2,
      generation_mode: "manual_revision",
      parent_asset_version_id: "asset-1",
    }));
    render(
      <StructuredRevisionEditor
        role="cleaner"
        asset={asset(assetType)}
        sources={[sourceSnapshot]}
        busy={false}
        onSave={onSave}
      />,
    );
    const editor = screen.getByRole("heading", { name: "创建人工修订" }).closest("section");
    if (!editor) throw new Error("Revision editor missing.");
    const field = within(editor).getByLabelText(fieldLabel);
    await user.clear(field);
    await user.type(field, value);
    await user.click(within(editor).getByRole("button", { name: "保存为新版本" }));
    expect(onSave).toHaveBeenCalledWith(
      expect.objectContaining(assetType === "sft_dataset" ? { records: expect.any(Array) } : {}),
      expect.stringMatching(/^p3-ui-manual-revision-/),
    );
    expect(within(editor).queryByLabelText(/Source ID/i)).not.toBeInTheDocument();
    expect(within(editor).queryByLabelText(/Asset Type/i)).not.toBeInTheDocument();
  });

  it("supports adding, deleting and reordering repeated training sections", async () => {
    const user = userEvent.setup();
    render(
      <StructuredRevisionEditor
        role="cleaner"
        asset={asset("training_material")}
        sources={[sourceSnapshot]}
        busy={false}
        onSave={vi.fn()}
      />,
    );
    await user.click(screen.getByRole("button", { name: "添加章节" }));
    expect(screen.getAllByLabelText("章节标题", { selector: "input" })).toHaveLength(2);
    expect(screen.getAllByText(/章节 \d/).length).toBeGreaterThanOrEqual(2);
    const upButtons = screen.getAllByRole("button", { name: "上移" });
    await user.click(upButtons[upButtons.length - 1]);
    const deleteButtons = screen.getAllByRole("button", { name: "删除" });
    await user.click(deleteButtons[deleteButtons.length - 1]);
  });

  it("submits generated content and locks pending-review editing", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn().mockResolvedValue(asset("sop", { status: "pending_review" }));
    const { rerender } = render(
      <ReviewWorkspace
        role="cleaner"
        asset={asset("sop")}
        sources={[sourceSnapshot]}
        review={null}
        history={[]}
        busy={false}
        onSubmit={onSubmit}
        onDecide={vi.fn()}
      />,
    );
    await user.click(screen.getByRole("button", { name: "提交审核" }));
    expect(onSubmit).toHaveBeenCalledWith(expect.stringMatching(/^p3-ui-submit-review-/));

    rerender(
      <StructuredRevisionEditor
        role="cleaner"
        asset={asset("sop", { status: "pending_review" })}
        sources={[sourceSnapshot]}
        busy={false}
        onSave={vi.fn()}
      />,
    );
    expect(screen.getByText("版本正在等待审核，内容已锁定。")).toBeVisible();
    expect(screen.queryByRole("button", { name: "保存为新版本" })).not.toBeInTheDocument();
  });

  it("enforces approval checklist and comment gates before a confirmed decision", async () => {
    const user = userEvent.setup();
    const onDecide = vi.fn().mockResolvedValue(review());
    render(
      <ReviewWorkspace
        role="reviewer"
        asset={asset("sop", { status: "pending_review" })}
        sources={[sourceSnapshot]}
        review={null}
        history={[]}
        busy={false}
        onSubmit={vi.fn()}
        onDecide={onDecide}
      />,
    );
    await user.click(screen.getByRole("button", { name: "提交审核决定" }));
    expect(screen.getByText("批准前必须完成全部四项审核检查。")).toBeVisible();
    for (const label of [
      "内容结构完整",
      "来源引用有效",
      "未发现无依据承诺",
      "适合后续复用",
    ]) {
      await user.click(screen.getByRole("switch", { name: label }));
    }
    await user.click(screen.getByRole("button", { name: "提交审核决定" }));
    const dialog = screen.getByRole("dialog", { name: "确认批准这个版本？" });
    await user.click(within(dialog).getByRole("button", { name: "确认批准" }));
    expect(onDecide).toHaveBeenCalledWith(expect.objectContaining({
      decision: "approved",
      checklist: {
        structure_complete: true,
        source_refs_valid: true,
        no_unsupported_claims_confirmed: true,
        safe_for_reuse: true,
      },
    }));
  });

  it.each([
    ["needs_revision", "退回修改"],
    ["rejected", "拒绝"],
  ] as const)("requires comments for %s and records confirmed decision", async (decision, label) => {
    const user = userEvent.setup();
    const onDecide = vi.fn().mockResolvedValue(review(decision));
    render(
      <ReviewWorkspace
        role="reviewer"
        asset={asset("sop", { status: "pending_review" })}
        sources={[sourceSnapshot]}
        review={null}
        history={[]}
        busy={false}
        onSubmit={vi.fn()}
        onDecide={onDecide}
      />,
    );
    await user.click(screen.getByRole("radio", { name: label }));
    await user.click(screen.getByRole("button", { name: "提交审核决定" }));
    expect(screen.getByText("退回修改或拒绝时必须填写审核意见。")).toBeVisible();
    await user.type(screen.getByLabelText(/审核意见/), "缺少明确来源说明");
    await user.click(screen.getByRole("button", { name: "提交审核决定" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: `确认${label}` }));
    expect(onDecide).toHaveBeenCalledWith(expect.objectContaining({
      decision,
      comments: "缺少明确来源说明",
    }));
  });

  it("keeps cleaner decision controls hidden and states approved is not published", () => {
    const { rerender } = render(
      <ReviewWorkspace
        role="cleaner"
        asset={asset("sop", { status: "pending_review" })}
        sources={[sourceSnapshot]}
        review={null}
        history={[]}
        busy={false}
        onSubmit={vi.fn()}
        onDecide={vi.fn()}
      />,
    );
    expect(screen.queryByRole("button", { name: "提交审核决定" })).not.toBeInTheDocument();
    rerender(
      <ReviewWorkspace
        role="viewer"
        asset={asset("sop", { status: "approved" })}
        sources={[sourceSnapshot]}
        review={review()}
        history={[review()]}
        busy={false}
        onSubmit={vi.fn()}
        onDecide={vi.fn()}
      />,
    );
    expect(screen.getByText("内容已批准，但尚未发布。")).toBeVisible();
    expect(screen.getByText(/不能证明审核人与提交人是不同自然人/)).toBeVisible();
    expect(screen.getByText("审核员")).toBeVisible();
    expect(screen.getByText("p3-review-v1")).toBeVisible();
  });
});
