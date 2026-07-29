import {
  P3_ASSET_STATUS_LABELS,
  P3_ASSET_TYPE_LABELS,
  P3_GENERATION_MODE_LABELS,
} from "../presentation";
import type { AssetFilters } from "../hooks/useAssetReviewWorkspace";
import type { P3AssetStatus, P3AssetType, P3AssetVersion } from "../types";

const FILTERABLE_STATUSES: P3AssetStatus[] = [
  "generated",
  "pending_review",
  "needs_revision",
  "approved",
  "published",
  "rejected",
  "failed",
  "superseded",
  "archived",
];

export function AssetVersionList({
  assets,
  total,
  offset,
  pageSize,
  filters,
  selectedAsset,
  loading,
  onFilters,
  onPage,
  onSelect,
}: {
  assets: P3AssetVersion[];
  total: number;
  offset: number;
  pageSize: number;
  filters: AssetFilters;
  selectedAsset: P3AssetVersion | null;
  loading: boolean;
  onFilters: (filters: AssetFilters) => void;
  onPage: (offset: number) => void;
  onSelect: (assetVersionId: string) => void;
}) {
  return (
    <section className="p3-asset-list-section" aria-labelledby="p3-asset-list-title">
      <div className="p3-section-heading">
        <div>
          <h2 id="p3-asset-list-title">草稿与版本</h2>
          <p>每次人工修订都会创建新版本，不会覆盖旧内容。</p>
        </div>
        <span className="p3-status-chip neutral">共 {total} 个版本</span>
      </div>

      <div className="p3-asset-filters" aria-label="版本筛选">
        <label>
          <span>资产类型</span>
          <select
            value={filters.assetType ?? ""}
            onChange={(event) => onFilters({
              ...filters,
              assetType: event.target.value
                ? event.target.value as P3AssetType
                : undefined,
            })}
          >
            <option value="">全部类型</option>
            {Object.entries(P3_ASSET_TYPE_LABELS).map(([code, label]) => (
              <option value={code} key={code}>{label}</option>
            ))}
          </select>
        </label>
        <label>
          <span>当前状态</span>
          <select
            value={filters.status ?? ""}
            onChange={(event) => onFilters({
              ...filters,
              status: event.target.value
                ? event.target.value as P3AssetStatus
                : undefined,
            })}
          >
            <option value="">全部状态</option>
            {FILTERABLE_STATUSES.map((status) => (
              <option value={status} key={status}>{P3_ASSET_STATUS_LABELS[status]}</option>
            ))}
          </select>
        </label>
      </div>

      {loading ? (
        <div className="p3-loading" role="status">正在加载资产版本…</div>
      ) : assets.length === 0 ? (
        <div className="p3-empty-state">
          <strong>还没有草稿版本</strong>
          <p>选择资产类型并使用确定性模板生成第一版草稿。</p>
        </div>
      ) : (
        <div className="p3-asset-version-list">
          {assets.map((asset) => (
            <button
              type="button"
              className={`p3-asset-version-card ${selectedAsset?.id === asset.id ? "selected" : ""}`}
              aria-pressed={selectedAsset?.id === asset.id}
              key={asset.id}
              onClick={() => onSelect(asset.id)}
            >
              <span className="p3-version-number">v{asset.version_number}</span>
              <span className="p3-version-main">
                <strong>{P3_ASSET_TYPE_LABELS[asset.asset_type]}</strong>
                <small>
                  {P3_GENERATION_MODE_LABELS[asset.generation_mode]}
                  {asset.parent_asset_version_id ? " · 基于上一版本修订" : ""}
                </small>
              </span>
              <span className={`p3-status-chip ${asset.status}`}>
                {P3_ASSET_STATUS_LABELS[asset.status]}
              </span>
              <time dateTime={asset.created_at}>
                {new Date(asset.created_at).toLocaleString("zh-CN")}
              </time>
            </button>
          ))}
        </div>
      )}

      {total > pageSize && (
        <div className="p3-pagination" aria-label="资产版本分页">
          <span>第 {Math.floor(offset / pageSize) + 1} 页</span>
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
    </section>
  );
}
