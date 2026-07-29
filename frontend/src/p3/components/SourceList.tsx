import { useState } from "react";
import type { AuthRole } from "../../api";
import { can, permissionHint } from "../../governance";
import {
  P3_SOURCE_STATUS_LABELS,
  P3_SOURCE_TYPE_LABELS,
  shortHash,
} from "../presentation";
import type { SourceFilters } from "../hooks/useProjectSourceWorkspace";
import type { P3Project, P3SourceItem, P3SourceType } from "../types";
import { ConfirmDialog } from "./ConfirmDialog";

export function SourceList({
  role,
  project,
  sources,
  total,
  offset,
  pageSize,
  filters,
  loading,
  mutating,
  onFilters,
  onPage,
  onRevalidate,
  onRevalidateAll,
  onRemove,
}: {
  role: AuthRole | null;
  project: P3Project;
  sources: P3SourceItem[];
  total: number;
  offset: number;
  pageSize: number;
  filters: SourceFilters;
  loading: boolean;
  mutating: boolean;
  onFilters: (filters: SourceFilters) => void;
  onPage: (offset: number) => void;
  onRevalidate: (sourceItemId: string) => void;
  onRevalidateAll: () => void;
  onRemove: (sourceItemId: string) => void;
}) {
  const [removeTarget, setRemoveTarget] = useState<P3SourceItem | null>(null);
  const readOnly = project.status === "archived";
  const canManage = can(role, "p3.source.manage") && !readOnly;
  const canRemove = canManage && project.status === "draft";

  function updateFilters(patch: Partial<SourceFilters>) {
    onFilters({ ...filters, ...patch });
  }

  return (
    <section className="p3-source-list-section" aria-labelledby="p3-source-list-title">
      <div className="p3-section-heading">
        <div>
          <h2 id="p3-source-list-title">项目来源</h2>
          <p>仅展示安全摘要；完整正文、向量和 Source Trace 不在此页面展开。</p>
        </div>
        <button
          type="button"
          className="btn-secondary"
          disabled={!canManage || mutating || sources.length === 0}
          title={permissionHint(role, "p3.source.manage")}
          onClick={onRevalidateAll}
        >
          {mutating ? "正在处理…" : "重新验证全部"}
        </button>
      </div>

      <div className="p3-source-filters" aria-label="来源筛选">
        <label>
          <span>来源类型</span>
          <select
            value={filters.sourceType ?? ""}
            onChange={(event) => updateFilters({
              sourceType: event.target.value
                ? event.target.value as P3SourceType
                : undefined,
            })}
          >
            <option value="">全部类型</option>
            {Object.entries(P3_SOURCE_TYPE_LABELS).map(([code, label]) => (
              <option key={code} value={code}>{label}</option>
            ))}
          </select>
        </label>
        <div className="p3-filter-switch">
          <span>
            <strong>只看异常来源</strong>
            <small>仅显示已经发生变化的来源</small>
          </span>
          <button
            type="button"
            role="switch"
            aria-checked={filters.onlyStale}
            aria-label="只看异常来源"
            className="compact-switch"
            onClick={() => updateFilters({ onlyStale: !filters.onlyStale })}
          >
            <span />
          </button>
        </div>
        <div className="p3-filter-switch">
          <span>
            <strong>包含已移除</strong>
            <small>显示历史逻辑移除记录</small>
          </span>
          <button
            type="button"
            role="switch"
            aria-checked={filters.includeRemoved}
            aria-label="包含已移除来源"
            className="compact-switch"
            onClick={() => updateFilters({ includeRemoved: !filters.includeRemoved })}
          >
            <span />
          </button>
        </div>
      </div>

      {loading ? (
        <div className="p3-loading" role="status">正在加载项目来源…</div>
      ) : sources.length === 0 ? (
        <div className="p3-empty-state">
          <strong>{filters.onlyStale ? "没有异常来源" : "当前项目还没有来源"}</strong>
          <p>
            {project.status === "draft"
              ? "先检查来源是否可用，再添加到项目。"
              : "此项目当前没有可展示的来源记录。"}
          </p>
        </div>
      ) : (
        <div className="p3-source-cards">
          {sources.map((source) => {
            const status = source.removed_at
              ? "removed"
              : source.source_stale ? "stale" : "eligible";
            return (
              <article className={`p3-source-card ${status}`} key={source.id}>
                <div className="p3-source-card-head">
                  <div>
                    <span className="p3-source-type">
                      {P3_SOURCE_TYPE_LABELS[source.source_type]}
                    </span>
                    <h3 title={source.source_id}>
                      来源 {source.source_id.length > 36
                        ? `${source.source_id.slice(0, 34)}…`
                        : source.source_id}
                    </h3>
                  </div>
                  <span className={`p3-status-chip ${status}`}>
                    {P3_SOURCE_STATUS_LABELS[status]}
                  </span>
                </div>
                <dl className="p3-source-summary">
                  <div><dt>版本</dt><dd>{source.source_version ?? "当前版本"}</dd></div>
                  <div><dt>审核</dt><dd>{source.approved_review_id ? "审核已通过" : "治理证据已确认"}</dd></div>
                  <div><dt>内容指纹</dt><dd>{shortHash(source.source_fingerprint)}</dd></div>
                  <div><dt>加入时间</dt><dd>{new Date(source.created_at).toLocaleString("zh-CN")}</dd></div>
                </dl>
                {!readOnly && (
                  <div className="p3-source-actions">
                    <button
                      type="button"
                      className="btn-small"
                      disabled={!canManage || mutating || Boolean(source.removed_at)}
                      onClick={() => onRevalidate(source.id)}
                    >
                      重新验证
                    </button>
                    {project.status === "draft" && (
                      <button
                        type="button"
                        className="btn-small danger-text"
                        disabled={!canRemove || mutating || Boolean(source.removed_at)}
                        onClick={() => setRemoveTarget(source)}
                      >
                        从项目移除
                      </button>
                    )}
                  </div>
                )}
                <details className="p3-inline-technical">
                  <summary>技术详情</summary>
                  <dl>
                    <div><dt>source_type</dt><dd>{source.source_type}</dd></div>
                    <div><dt>policy_version</dt><dd>{source.eligibility_policy_version}</dd></div>
                    <div><dt>source_item_id</dt><dd>{source.id}</dd></div>
                  </dl>
                </details>
              </article>
            );
          })}
        </div>
      )}

      {total > pageSize && (
        <div className="p3-pagination" aria-label="来源分页">
          <span>共 {total} 个来源</span>
          <div>
            <button
              type="button"
              className="btn-small"
              disabled={offset === 0 || loading}
              onClick={() => onPage(Math.max(0, offset - pageSize))}
            >
              上一页
            </button>
            <button
              type="button"
              className="btn-small"
              disabled={offset + pageSize >= total || loading}
              onClick={() => onPage(offset + pageSize)}
            >
              下一页
            </button>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={removeTarget !== null}
        title="从项目中移除这个来源？"
        description="此操作只会逻辑移除当前选择，历史审核证据仍会保留，不会修改 P1/P2 原始知识。"
        confirmLabel="确认移除"
        danger
        busy={mutating}
        onCancel={() => setRemoveTarget(null)}
        onConfirm={() => {
          if (removeTarget) onRemove(removeTarget.id);
          setRemoveTarget(null);
        }}
      />
    </section>
  );
}
