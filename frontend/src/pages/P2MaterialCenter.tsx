import { FormEvent, useEffect, useRef, useState } from "react";
import { apiPath } from "../api";
import type { Asset, AssetPagination } from "../types";

const PAGE_SIZE = 10;

function formatBytes(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KiB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MiB`;
}

function apiError(body: any, fallback: string): string {
  return body?.detail?.message || body?.error?.message || fallback;
}

export function P2MaterialCenter() {
  const [assets, setAssets] = useState<Asset[]>([]);
  const [pagination, setPagination] = useState<AssetPagination>({
    page: 1,
    page_size: PAGE_SIZE,
    total: 0,
    total_pages: 0,
  });
  const [selectedAsset, setSelectedAsset] = useState<Asset | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    void loadAssets(1);
  }, []);

  async function loadAssets(page: number) {
    setIsLoading(true);
    setError("");
    try {
      const response = await fetch(apiPath(`/api/assets?page=${page}&page_size=${PAGE_SIZE}`));
      const body = await response.json();
      if (!response.ok || !body.success) {
        throw new Error(apiError(body, "素材列表加载失败。"));
      }
      setAssets(body.data.assets);
      setPagination(body.data.pagination);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "素材列表加载失败。");
    } finally {
      setIsLoading(false);
    }
  }

  async function uploadAsset(event: FormEvent) {
    event.preventDefault();
    if (!selectedFile) {
      setError("请先选择 JPEG、PNG 或 WebP 图片。");
      return;
    }
    setIsUploading(true);
    setError("");
    setMessage("");
    const form = new FormData();
    form.append("file", selectedFile);
    form.append("asset_type", "image");
    try {
      const response = await fetch(apiPath("/api/assets/upload"), {
        method: "POST",
        body: form,
      });
      const body = await response.json();
      if (!response.ok || !body.success) {
        if (body?.detail?.code === "ASSET_DUPLICATE") {
          const existingId = body.detail.details?.existing_asset_id;
          if (existingId) {
            await loadAssetDetail(existingId);
            setSelectedFile(null);
            if (fileInputRef.current) fileInputRef.current.value = "";
            setMessage(`该文件已存在，已定位到素材：${existingId}。`);
            return;
          }
          throw new Error("该文件已存在。");
        }
        throw new Error(apiError(body, "素材上传失败。"));
      }
      setSelectedAsset(body.data);
      setSelectedFile(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
      setMessage("素材已完成校验、去重检查和持久化。");
      await loadAssets(1);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "素材上传失败。");
    } finally {
      setIsUploading(false);
    }
  }

  async function loadAssetDetail(assetId: string) {
    setError("");
    try {
      const response = await fetch(apiPath(`/api/assets/${assetId}`));
      const body = await response.json();
      if (!response.ok || !body.success) {
        throw new Error(apiError(body, "素材详情加载失败。"));
      }
      setSelectedAsset(body.data);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "素材详情加载失败。");
    }
  }

  return (
    <div className="p2-page">
      <div className="page-hero">
        <h1>AI 素材中心</h1>
        <p>接入并治理图片素材。P2-M1 仅提供安全上传、去重、列表和详情，不进行图片理解。</p>
      </div>

      <div className="roadmap-banner material-boundary-banner">
        <span className="roadmap-icon">P2</span>
        <div>
          <strong>Material Ingestion Foundation</strong>
          <p>当前支持 JPEG、PNG、WebP，单文件最大 10 MiB。OCR、Caption、Embedding、RAG 和 Agent 调用尚未接入。</p>
        </div>
      </div>

      {message && <div className="feedback success">{message}</div>}
      {error && <div className="feedback error">{error}</div>}

      <section className="material-panel">
        <div className="material-panel-header">
          <div>
            <h2>上传素材</h2>
            <p>文件将先校验真实格式和大小，再计算 SHA-256 去重。</p>
          </div>
        </div>
        <form className="material-upload-form" onSubmit={uploadAsset}>
          <label>
            选择图片
            <input
              ref={fileInputRef}
              type="file"
              accept="image/jpeg,image/png,image/webp,.jpg,.jpeg,.png,.webp"
              onChange={(event) => setSelectedFile(event.target.files?.[0] || null)}
            />
          </label>
          <div className="material-upload-actions">
            <span>{selectedFile ? `${selectedFile.name} · ${formatBytes(selectedFile.size)}` : "尚未选择文件"}</span>
            <button className="btn-primary" type="submit" disabled={isUploading || !selectedFile}>
              {isUploading ? "上传中..." : "上传素材"}
            </button>
          </div>
        </form>
      </section>

      <section className="material-panel">
        <div className="material-panel-header">
          <div>
            <h2>素材列表</h2>
            <p>共 {pagination.total} 个素材，仅展示治理元数据。</p>
          </div>
          <button className="btn-secondary btn-sm" type="button" onClick={() => void loadAssets(pagination.page)} disabled={isLoading}>
            {isLoading ? "加载中..." : "刷新"}
          </button>
        </div>

        {assets.length === 0 ? (
          <div className="empty-state">
            <span className="empty-icon">◇</span>
            <p className="empty-title">暂无素材</p>
            <p className="empty-desc">上传第一张商品图或运营海报后，这里会显示资产记录。</p>
          </div>
        ) : (
          <div className="material-list">
            {assets.map((asset) => (
              <button className="material-row" type="button" key={asset.id} onClick={() => void loadAssetDetail(asset.id)}>
                <span className="material-row-main">
                  <strong>{asset.file_name}</strong>
                  <small>{asset.id}</small>
                </span>
                <span>{asset.mime_type}</span>
                <span>{formatBytes(asset.size)}</span>
                <span className="asset-status-badge">已上传</span>
                <span>查看详情 →</span>
              </button>
            ))}
          </div>
        )}

        {pagination.total_pages > 1 && (
          <div className="material-pagination">
            <button className="btn-small" type="button" disabled={pagination.page <= 1} onClick={() => void loadAssets(pagination.page - 1)}>上一页</button>
            <span>第 {pagination.page} / {pagination.total_pages} 页</span>
            <button className="btn-small" type="button" disabled={pagination.page >= pagination.total_pages} onClick={() => void loadAssets(pagination.page + 1)}>下一页</button>
          </div>
        )}
      </section>

      <section className="material-panel">
        <div className="material-panel-header">
          <div>
            <h2>素材详情</h2>
            <p>显示可审计元数据；原始二进制不存入数据库。</p>
          </div>
        </div>
        {!selectedAsset ? (
          <div className="empty-state">
            <p className="empty-title">请选择一个素材</p>
            <p className="empty-desc">从上方列表进入详情。</p>
          </div>
        ) : (
          <dl className="asset-detail-grid">
            <div><dt>Asset ID</dt><dd>{selectedAsset.id}</dd></div>
            <div><dt>文件名</dt><dd>{selectedAsset.file_name}</dd></div>
            <div><dt>素材类型</dt><dd>{selectedAsset.asset_type}</dd></div>
            <div><dt>MIME</dt><dd>{selectedAsset.mime_type}</dd></div>
            <div><dt>大小</dt><dd>{formatBytes(selectedAsset.size)}</dd></div>
            <div><dt>状态</dt><dd>{selectedAsset.status}</dd></div>
            <div className="asset-detail-wide"><dt>SHA-256</dt><dd>{selectedAsset.hash}</dd></div>
            <div className="asset-detail-wide"><dt>Storage URI</dt><dd>{selectedAsset.storage_uri}</dd></div>
            <div><dt>创建时间</dt><dd>{selectedAsset.created_at}</dd></div>
            <div><dt>更新时间</dt><dd>{selectedAsset.updated_at}</dd></div>
          </dl>
        )}
      </section>
    </div>
  );
}
