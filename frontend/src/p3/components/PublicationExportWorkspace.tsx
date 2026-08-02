import { useMemo, useState } from "react";
import type { AuthRole } from "../../api";
import { can, permissionHint } from "../../governance";
import {
  P3_ASSET_STATUS_LABELS,
  P3_ASSET_TYPE_LABELS,
  P3_EXPORT_STATUS_LABELS,
  P3_GENERATION_MODE_LABELS,
  shortHash,
} from "../presentation";
import type {
  P3AssetVersion,
  P3ExportArtifact,
  P3ExportFormat,
  P3ExportJob,
  P3PublishedAsset,
} from "../types";
import { ConfirmDialog } from "./ConfirmDialog";

type ConfirmAction =
  | { kind: "publish" }
  | { kind: "archive"; assetVersionId: string; versionNumber: number }
  | { kind: "revoke"; exportJobId: string; fileName: string }
  | null;

function formatDate(value: string | null): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

export function PublicationExportWorkspace({
  role,
  selectedAsset,
  publishedAssets,
  exportJobs,
  artifacts,
  loading,
  busy,
  onPublish,
  onArchive,
  onCreateExport,
  onDownload,
  onRevoke,
  onRefresh,
}: {
  role: AuthRole | null;
  selectedAsset: P3AssetVersion | null;
  publishedAssets: P3PublishedAsset[];
  exportJobs: P3ExportJob[];
  artifacts: Record<string, P3ExportArtifact>;
  loading: boolean;
  busy: boolean;
  onPublish: () => Promise<unknown>;
  onArchive: (assetVersionId: string) => Promise<unknown>;
  onCreateExport: (assetVersionId: string, format: P3ExportFormat) => Promise<unknown>;
  onDownload: (artifact: P3ExportArtifact) => Promise<unknown>;
  onRevoke: (exportJobId: string) => Promise<unknown>;
  onRefresh: () => Promise<unknown>;
}) {
  const [confirmAction, setConfirmAction] = useState<ConfirmAction>(null);
  const currentByType = useMemo(
    () => new Map(publishedAssets.map((asset) => [asset.asset_type, asset])),
    [publishedAssets],
  );
  const canPublish = can(role, "p3.asset.publish");
  const canArchive = can(role, "p3.asset.archive");
  const canExport = can(role, "p3.export.create");
  const canDownload = can(role, "p3.export.download");
  const canRevoke = can(role, "p3.export.revoke");

  const confirmCopy = useMemo(() => {
    if (!confirmAction) return null;
    if (confirmAction.kind === "publish") {
      return {
        title: "确认发布此版本？",
        description: "发布后它将成为这一资产类型的当前正式版本；已有当前版本会被标记为已替代。发布不会自动进入检索或 Agent。",
        label: "确认发布",
        danger: false,
      };
    }
    if (confirmAction.kind === "archive") {
      return {
        title: `确认归档版本 v${confirmAction.versionNumber}？`,
        description: "归档后不可恢复，也不会自动恢复旧版本；历史审核和来源快照仍会保留。",
        label: "确认归档",
        danger: true,
      };
    }
    return {
      title: "确认撤回这个导出文件？",
      description: `${confirmAction.fileName} 撤回后不能再下载，历史审计仍会保留，不代表文件已被物理删除。`,
      label: "确认撤回",
      danger: true,
    };
  }, [confirmAction]);

  const performConfirmedAction = async () => {
    if (!confirmAction) return;
    let outcome: unknown = null;
    if (confirmAction.kind === "publish") outcome = await onPublish();
    if (confirmAction.kind === "archive") {
      outcome = await onArchive(confirmAction.assetVersionId);
    }
    if (confirmAction.kind === "revoke") outcome = await onRevoke(confirmAction.exportJobId);
    if (outcome) setConfirmAction(null);
  };

  return (
    <section className="p3-publication-export" aria-labelledby="p3-publication-title">
      <div className="p3-section-heading">
        <div>
          <span className="p3-stage-label">阶段 5</span>
          <h2 id="p3-publication-title">发布与导出</h2>
          <p>只有人工批准的版本才能发布；只有当前正式版本才能创建新导出。</p>
        </div>
        <button
          type="button"
          className="btn-small"
          disabled={loading || busy}
          onClick={() => void onRefresh()}
        >
          刷新发布状态
        </button>
      </div>

      <div className="p3-publication-boundary" role="note">
        <strong>发布表示成为正式 P3 数据资产，不会自动进入检索或 Agent。</strong>
        <span>导出也不表示已训练模型；下载文件仍受权限和撤回状态约束。</span>
      </div>

      {selectedAsset ? (
        <article className="p3-selected-publication">
          <div>
            <span className="p3-stage-label">当前查看版本</span>
            <h3>{P3_ASSET_TYPE_LABELS[selectedAsset.asset_type]} · v{selectedAsset.version_number}</h3>
            <p>
              {P3_ASSET_STATUS_LABELS[selectedAsset.status]} · {P3_GENERATION_MODE_LABELS[selectedAsset.generation_mode]}
            </p>
          </div>
          <div className="p3-publication-actions">
            {selectedAsset.status === "approved" && (
              <>
                <span className="p3-approval-not-published">已批准，但尚未发布</span>
                {canPublish ? (
                  <button
                    type="button"
                    className="btn-primary"
                    disabled={busy}
                    onClick={() => setConfirmAction({ kind: "publish" })}
                  >
                    发布此版本
                  </button>
                ) : (
                  <span className="p3-permission-note">当前角色仅可查看，发布由管理员执行。</span>
                )}
              </>
            )}
            {selectedAsset.status === "published" && (
              <span className="p3-current-published-label">
                {currentByType.get(selectedAsset.asset_type)?.asset_version_id === selectedAsset.id
                  ? "当前正式版本"
                  : "已发布版本"}
              </span>
            )}
            {selectedAsset.status === "superseded" && (
              <span className="p3-status-chip superseded">已被新版本替代</span>
            )}
            {selectedAsset.status === "archived" && (
              <span className="p3-readonly-note">版本已归档，页面只读。</span>
            )}
            {canArchive && ["published", "superseded"].includes(selectedAsset.status) && (
              <button
                type="button"
                className="btn-danger"
                disabled={busy}
                onClick={() => setConfirmAction({
                  kind: "archive",
                  assetVersionId: selectedAsset.id,
                  versionNumber: selectedAsset.version_number,
                })}
              >
                归档此版本
              </button>
            )}
          </div>
        </article>
      ) : (
        <div className="p3-empty-state" role="status">
          <strong>选择一个资产版本查看发布状态</strong>
        </div>
      )}

      <section className="p3-current-published" aria-labelledby="p3-current-published-title">
        <div>
          <h3 id="p3-current-published-title">当前正式版本</h3>
          <p>按资产类型展示；“已批准”不会出现在这里，直到管理员明确发布。</p>
        </div>
        {loading ? (
          <div className="p3-loading" role="status">正在加载当前正式版本…</div>
        ) : publishedAssets.length === 0 ? (
          <div className="p3-empty-state" role="status">
            <strong>当前项目还没有正式发布版本</strong>
          </div>
        ) : (
          <div className="p3-published-grid">
            {publishedAssets.map((asset) => (
              <article key={asset.asset_version_id} className={asset.source_stale ? "stale" : ""}>
                <div className="p3-published-card-heading">
                  <div>
                    <span className="p3-stage-label">{P3_ASSET_TYPE_LABELS[asset.asset_type]}</span>
                    <h4>版本 v{asset.version_number}</h4>
                  </div>
                  <span className="p3-current-published-label">当前正式版本</span>
                </div>
                <dl>
                  <div><dt>状态</dt><dd>{P3_ASSET_STATUS_LABELS[asset.status]}</dd></div>
                  <div><dt>生成方式</dt><dd>{P3_GENERATION_MODE_LABELS[asset.generation_mode]}</dd></div>
                  <div><dt>发布时间</dt><dd>{formatDate(asset.published_at)}</dd></div>
                  <div><dt>来源状态</dt><dd>{asset.source_stale ? "来源已变化" : "来源仍有效"}</dd></div>
                </dl>
                {asset.source_stale && (
                  <div className="p3-stale-warning" role="status">
                    来源已变化：历史文件仍可按状态下载，但当前版本不再适合新复用，也不能创建新导出。
                  </div>
                )}
                {canExport ? (
                  <div className="p3-export-actions">
                    <button
                      type="button"
                      className="btn-secondary"
                      disabled={busy || asset.source_stale}
                      onClick={() => void onCreateExport(asset.asset_version_id, "jsonl")}
                    >
                      导出 JSONL
                    </button>
                    <button
                      type="button"
                      className="btn-secondary"
                      disabled={busy || asset.source_stale}
                      onClick={() => void onCreateExport(asset.asset_version_id, "csv")}
                    >
                      导出 CSV
                    </button>
                  </div>
                ) : (
                  <span className="p3-permission-note">仅管理员可以创建新导出。</span>
                )}
              </article>
            ))}
          </div>
        )}
      </section>

      <section className="p3-export-history" aria-labelledby="p3-export-history-title">
        <div>
          <h3 id="p3-export-history-title">导出文件</h3>
          <p>仅展示安全文件元数据，不展示存储目录、绝对路径或完整 Manifest。</p>
        </div>
        {loading ? (
          <div className="p3-loading" role="status">正在加载导出记录…</div>
        ) : exportJobs.length === 0 ? (
          <div className="p3-empty-state" role="status">
            <strong>还没有导出记录</strong>
          </div>
        ) : (
          <div className="p3-export-card-list">
            {exportJobs.map((job) => {
              const artifact = artifacts[job.id];
              const revoked = job.status === "revoked" || Boolean(artifact?.revoked_at);
              return (
                <article key={job.id} className={revoked ? "revoked" : ""}>
                  <div className="p3-export-card-heading">
                    <div>
                      <span className="p3-stage-label">{job.export_format.toUpperCase()}</span>
                      <h4>{artifact?.safe_file_name ?? "正在准备文件"}</h4>
                    </div>
                    <span className={`p3-status-chip ${job.status}`}>
                      {P3_EXPORT_STATUS_LABELS[job.status]}
                    </span>
                  </div>
                  {artifact ? (
                    <>
                      {artifact.source_stale && (
                        <div className="p3-stale-warning" role="status">
                          此文件的来源后来发生变化，历史文件仍可下载，但不应作为新的复用起点。
                        </div>
                      )}
                      <dl className="p3-artifact-metadata">
                        <div><dt>格式</dt><dd>{artifact.export_format.toUpperCase()}</dd></div>
                        <div><dt>文件大小</dt><dd>{formatBytes(artifact.byte_size)}</dd></div>
                        <div><dt>行数</dt><dd>{artifact.row_count}</dd></div>
                        <div><dt>创建时间</dt><dd>{formatDate(artifact.created_at)}</dd></div>
                        <div><dt>SHA</dt><dd>{shortHash(artifact.artifact_sha256)}</dd></div>
                        <div><dt>Manifest Hash</dt><dd>{shortHash(artifact.export_manifest_hash)}</dd></div>
                        <div><dt>来源状态</dt><dd>{artifact.source_stale ? "来源已变化" : "来源仍有效"}</dd></div>
                      </dl>
                      <div className="p3-artifact-actions">
                        <button
                          type="button"
                          className="btn-primary"
                          disabled={busy || revoked || !canDownload}
                          title={permissionHint(role, "p3.export.download")}
                          onClick={() => void onDownload(artifact)}
                        >
                          {revoked ? "已撤回，无法下载" : "下载文件"}
                        </button>
                        {canRevoke && !revoked && (
                          <button
                            type="button"
                            className="btn-danger"
                            disabled={busy}
                            onClick={() => setConfirmAction({
                              kind: "revoke",
                              exportJobId: job.id,
                              fileName: artifact.safe_file_name,
                            })}
                          >
                            撤回导出
                          </button>
                        )}
                      </div>
                      {revoked && (
                        <p className="p3-revoked-note">文件已逻辑撤回，历史审计仍保留；未声明已物理删除。</p>
                      )}
                    </>
                  ) : (
                    <p className="p3-permission-note">
                      {job.status === "failed"
                        ? "导出失败，请查看技术详情中的稳定错误码。"
                        : "导出任务尚未生成可下载文件。"}
                    </p>
                  )}
                </article>
              );
            })}
          </div>
        )}
      </section>

      {confirmCopy && (
        <ConfirmDialog
          open
          title={confirmCopy.title}
          description={confirmCopy.description}
          confirmLabel={confirmCopy.label}
          danger={confirmCopy.danger}
          busy={busy}
          onConfirm={() => void performConfirmedAction()}
          onCancel={() => setConfirmAction(null)}
        />
      )}
    </section>
  );
}
