import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PublicationExportWorkspace } from "../../p3/components/PublicationExportWorkspace";
import type {
  P3AssetVersion,
  P3ExportArtifact,
  P3ExportJob,
  P3PublishedAsset,
} from "../../p3/types";

function selectedAsset(
  status: P3AssetVersion["status"] = "approved",
  overrides: Partial<P3AssetVersion> = {},
): P3AssetVersion {
  return {
    id: "asset-current",
    project_id: "project-1",
    asset_type: "training_material",
    version_number: 2,
    status,
    generation_mode: "manual_revision",
    template_key: "training_material_v1",
    template_version: "v1",
    content_payload: { title: "客服培训" },
    content_hash: "content-hash-abcdef123456",
    source_manifest_hash: "source-manifest-abcdef123456",
    parent_asset_version_id: "asset-old",
    created_by_role: "cleaner",
    request_id: "req_asset",
    created_at: "2026-07-30T01:00:00Z",
    updated_at: "2026-07-30T02:00:00Z",
    approved_at: status === "approved" ? "2026-07-30T03:00:00Z" : null,
    published_at: status === "published" ? "2026-07-30T04:00:00Z" : null,
    failure_code: null,
    failure_message: null,
    ...overrides,
  };
}

function published(overrides: Partial<P3PublishedAsset> = {}): P3PublishedAsset {
  return {
    asset_version_id: "asset-current",
    project_id: "project-1",
    asset_type: "training_material",
    version_number: 2,
    status: "published",
    generation_mode: "manual_revision",
    published_at: "2026-07-30T04:00:00Z",
    published_by_role: "admin",
    content_hash: "content-hash-abcdef123456",
    source_manifest_hash: "source-manifest-abcdef123456",
    superseded_by_asset_version_id: null,
    archived_at: null,
    source_stale: false,
    current_reuse_eligible: true,
    ...overrides,
  };
}

function exportJob(overrides: Partial<P3ExportJob> = {}): P3ExportJob {
  return {
    id: "export-job-1",
    project_id: "project-1",
    asset_version_id: "asset-current",
    export_format: "jsonl",
    status: "succeeded",
    export_policy_version: "p3-export-v1",
    requested_by_role: "admin",
    request_id: "req_export",
    created_at: "2026-07-30T05:00:00Z",
    started_at: "2026-07-30T05:00:01Z",
    completed_at: "2026-07-30T05:00:02Z",
    failed_at: null,
    revoked_at: null,
    failure_code: null,
    failure_message: null,
    ...overrides,
  };
}

function artifact(overrides: Partial<P3ExportArtifact> = {}): P3ExportArtifact {
  return {
    id: "artifact-1",
    export_job_id: "export-job-1",
    asset_version_id: "asset-current",
    export_format: "jsonl",
    safe_file_name: "training-material-v2.jsonl",
    content_type: "application/x-ndjson",
    encoding: "utf-8",
    byte_size: 2048,
    row_count: 12,
    artifact_sha256: "abcdef1234567890abcdef1234567890",
    export_manifest_hash: "manifest1234567890manifest1234567890",
    created_at: "2026-07-30T05:00:02Z",
    revoked_at: null,
    source_stale: false,
    current_reuse_eligible: true,
    ...overrides,
  };
}

function renderWorkspace({
  role = "admin",
  asset = selectedAsset(),
  publishedAssets = [published()],
  jobs = [exportJob()],
  artifactByJob = { "export-job-1": artifact() },
  onPublish = vi.fn().mockResolvedValue({ asset: published() }),
  onArchive = vi.fn().mockResolvedValue({ asset: published({ status: "archived" }) }),
  onCreateExport = vi.fn().mockResolvedValue({ job: exportJob(), artifact: artifact() }),
  onDownload = vi.fn().mockResolvedValue(true),
  onRevoke = vi.fn().mockResolvedValue({ job: exportJob({ status: "revoked" }) }),
}: {
  role?: "admin" | "cleaner" | "reviewer" | "service" | "viewer";
  asset?: P3AssetVersion | null;
  publishedAssets?: P3PublishedAsset[];
  jobs?: P3ExportJob[];
  artifactByJob?: Record<string, P3ExportArtifact>;
  onPublish?: ReturnType<typeof vi.fn>;
  onArchive?: ReturnType<typeof vi.fn>;
  onCreateExport?: ReturnType<typeof vi.fn>;
  onDownload?: ReturnType<typeof vi.fn>;
  onRevoke?: ReturnType<typeof vi.fn>;
} = {}) {
  const view = render(
    <PublicationExportWorkspace
      role={role}
      selectedAsset={asset}
      publishedAssets={publishedAssets}
      exportJobs={jobs}
      artifacts={artifactByJob}
      loading={false}
      busy={false}
      onPublish={onPublish}
      onArchive={onArchive}
      onCreateExport={onCreateExport}
      onDownload={onDownload}
      onRevoke={onRevoke}
      onRefresh={vi.fn().mockResolvedValue(undefined)}
    />,
  );
  return {
    ...view,
    onPublish,
    onArchive,
    onCreateExport,
    onDownload,
    onRevoke,
  };
}

describe("P3 publication, export and download workspace", () => {
  it("lets admin publish an approved version only after confirmation", async () => {
    const user = userEvent.setup();
    const { onPublish } = renderWorkspace();
    expect(screen.getByText("已批准，但尚未发布")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "发布此版本" }));
    const dialog = screen.getByRole("dialog", { name: "确认发布此版本？" });
    expect(within(dialog).getByText(/已有当前版本会被标记为已替代/)).toBeVisible();
    expect(within(dialog).getByText(/不会自动进入检索或 Agent/)).toBeVisible();
    await user.click(within(dialog).getByRole("button", { name: "确认发布" }));
    expect(onPublish).toHaveBeenCalledTimes(1);
  });

  it.each(["cleaner", "reviewer", "viewer", "service"] as const)(
    "keeps publication and archive actions unavailable to %s",
    (role) => {
      renderWorkspace({ role });
      expect(screen.getByText("当前角色仅可查看，发布由管理员执行。")).toBeVisible();
      expect(screen.queryByRole("button", { name: "发布此版本" })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "归档此版本" })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "撤回导出" })).not.toBeInTheDocument();
    },
  );

  it("clearly separates approved, current published, superseded and archived states", () => {
    const { rerender } = renderWorkspace({
      asset: selectedAsset("superseded"),
      publishedAssets: [published({ asset_version_id: "asset-new", version_number: 3 })],
    });
    expect(screen.getByText("已被新版本替代")).toBeVisible();
    expect(screen.getByRole("heading", { name: "当前正式版本" })).toBeVisible();
    expect(screen.getByText("版本 v3")).toBeVisible();
    rerender(
      <PublicationExportWorkspace
        role="admin"
        selectedAsset={selectedAsset("archived")}
        publishedAssets={[]}
        exportJobs={[]}
        artifacts={{}}
        loading={false}
        busy={false}
        onPublish={vi.fn()}
        onArchive={vi.fn()}
        onCreateExport={vi.fn()}
        onDownload={vi.fn()}
        onRevoke={vi.fn()}
        onRefresh={vi.fn()}
      />,
    );
    expect(screen.getByText("版本已归档，页面只读。")).toBeVisible();
    expect(screen.getByText("当前项目还没有正式发布版本")).toBeVisible();
  });

  it("creates JSONL and CSV only from the current published version", async () => {
    const user = userEvent.setup();
    const { onCreateExport } = renderWorkspace();
    await user.click(screen.getByRole("button", { name: "导出 JSONL" }));
    await user.click(screen.getByRole("button", { name: "导出 CSV" }));
    expect(onCreateExport).toHaveBeenNthCalledWith(1, "asset-current", "jsonl");
    expect(onCreateExport).toHaveBeenNthCalledWith(2, "asset-current", "csv");
  });

  it("keeps historical stale artifacts downloadable but disables new exports", async () => {
    const user = userEvent.setup();
    const onDownload = vi.fn().mockResolvedValue(true);
    renderWorkspace({
      publishedAssets: [published({ source_stale: true, current_reuse_eligible: false })],
      artifactByJob: {
        "export-job-1": artifact({ source_stale: true, current_reuse_eligible: false }),
      },
      onDownload,
    });
    expect(screen.getByRole("button", { name: "导出 JSONL" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "导出 CSV" })).toBeDisabled();
    expect(screen.getAllByText(/历史文件仍可/).length).toBeGreaterThanOrEqual(1);
    await user.click(screen.getByRole("button", { name: "下载文件" }));
    expect(onDownload).toHaveBeenCalledWith(expect.objectContaining({ id: "artifact-1" }));
  });

  it("revokes only after a dangerous confirmation and disables later downloads", async () => {
    const user = userEvent.setup();
    const onRevoke = vi.fn().mockResolvedValue({ job: exportJob({ status: "revoked" }) });
    const { rerender } = renderWorkspace({ onRevoke });
    await user.click(screen.getByRole("button", { name: "撤回导出" }));
    const dialog = screen.getByRole("dialog", { name: "确认撤回这个导出文件？" });
    expect(within(dialog).getByText(/不代表文件已被物理删除/)).toBeVisible();
    await user.click(within(dialog).getByRole("button", { name: "确认撤回" }));
    expect(onRevoke).toHaveBeenCalledWith("export-job-1");

    rerender(
      <PublicationExportWorkspace
        role="admin"
        selectedAsset={selectedAsset("published")}
        publishedAssets={[published()]}
        exportJobs={[exportJob({ status: "revoked", revoked_at: "2026-07-30T06:00:00Z" })]}
        artifacts={{
          "export-job-1": artifact({ revoked_at: "2026-07-30T06:00:00Z" }),
        }}
        loading={false}
        busy={false}
        onPublish={vi.fn()}
        onArchive={vi.fn()}
        onCreateExport={vi.fn()}
        onDownload={vi.fn()}
        onRevoke={vi.fn()}
        onRefresh={vi.fn()}
      />,
    );
    expect(screen.getByRole("button", { name: "已撤回，无法下载" })).toBeDisabled();
    expect(screen.getByText(/历史审计仍保留/)).toBeVisible();
  });

  it("warns archive is irreversible and does not restore an old version", async () => {
    const user = userEvent.setup();
    const onArchive = vi.fn().mockResolvedValue({ asset: published({ status: "archived" }) });
    renderWorkspace({ asset: selectedAsset("published"), onArchive });
    await user.click(screen.getByRole("button", { name: "归档此版本" }));
    const dialog = screen.getByRole("dialog", { name: "确认归档版本 v2？" });
    expect(within(dialog).getByText(/不可恢复，也不会自动恢复旧版本/)).toBeVisible();
    await user.click(within(dialog).getByRole("button", { name: "确认归档" }));
    expect(onArchive).toHaveBeenCalledWith("asset-current");
  });

  it("shows safe artifact metadata without storage paths or full hashes", () => {
    renderWorkspace();
    expect(screen.getByText("training-material-v2.jsonl")).toBeVisible();
    expect(screen.getByText("2.0 KB")).toBeVisible();
    expect(screen.getByText("12")).toBeVisible();
    expect(screen.getByText("abcdef12…7890")).toBeVisible();
    expect(screen.getByText("manifest…7890")).toBeVisible();
    expect(screen.queryByText("abcdef1234567890abcdef1234567890")).not.toBeInTheDocument();
    expect(screen.queryByText(/storage|absolute|\\\\|\/var\/|[A-Z]:\\/i)).not.toBeInTheDocument();
    expect(screen.getByText(/不展示存储目录、绝对路径或完整 Manifest/)).toBeVisible();
  });

  it("traps keyboard focus in dialogs, closes on Escape and restores the trigger", async () => {
    const user = userEvent.setup();
    renderWorkspace();
    const trigger = screen.getByRole("button", { name: "发布此版本" });
    trigger.focus();
    await user.click(trigger);
    const dialog = screen.getByRole("dialog");
    const cancel = within(dialog).getByRole("button", { name: "取消" });
    const confirm = within(dialog).getByRole("button", { name: "确认发布" });
    expect(cancel).toHaveFocus();
    await user.tab({ shift: true });
    expect(confirm).toHaveFocus();
    await user.tab();
    expect(cancel).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it("uses Chinese status labels and never implies RAG, Agent or model training", () => {
    renderWorkspace();
    expect(screen.getByText("导出成功")).toBeVisible();
    expect(screen.getByText(/发布表示成为正式 P3 数据资产，不会自动进入检索或 Agent/)).toBeVisible();
    expect(screen.getByText(/导出也不表示已训练模型/)).toBeVisible();
  });
});
