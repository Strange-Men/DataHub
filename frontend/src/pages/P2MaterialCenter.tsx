import { FormEvent, useEffect, useRef, useState } from "react";
import { apiPath } from "../api";
import type {
  Asset,
  AssetExtraction,
  AssetPagination,
  AssetReviewSnapshot,
  ExtractionReview,
  ExtractionReviewStatus,
  KnowledgeAsset,
} from "../types";

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
  const [extractions, setExtractions] = useState<AssetExtraction[]>([]);
  const [snapshots, setSnapshots] = useState<AssetReviewSnapshot[]>([]);
  const [knowledgeAssets, setKnowledgeAssets] = useState<KnowledgeAsset[]>([]);
  const [activeReview, setActiveReview] = useState<ExtractionReview | null>(null);
  const [reviewer, setReviewer] = useState("");
  const [reviewComment, setReviewComment] = useState("");
  const [revisedContent, setRevisedContent] = useState("");
  const [isReviewLoading, setIsReviewLoading] = useState(false);
  const [isReviewSubmitting, setIsReviewSubmitting] = useState(false);
  const [isKnowledgeSubmitting, setIsKnowledgeSubmitting] = useState(false);
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
      setExtractions([]);
      setSnapshots([]);
      setKnowledgeAssets([]);
      setActiveReview(null);
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
      await loadReviewWorkspace(assetId);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "素材详情加载失败。");
    }
  }

  async function loadReviewWorkspace(assetId: string) {
    setIsReviewLoading(true);
    try {
      const [extractionResponse, snapshotResponse, knowledgeResponse] = await Promise.all([
        fetch(apiPath(`/api/assets/${assetId}/extractions`)),
        fetch(apiPath(`/api/assets/${assetId}/snapshots`)),
        fetch(apiPath(`/api/knowledge-assets?page=1&page_size=100&asset_id=${assetId}`)),
      ]);
      const [extractionBody, snapshotBody, knowledgeBody] = await Promise.all([
        extractionResponse.json(),
        snapshotResponse.json(),
        knowledgeResponse.json(),
      ]);
      if (!extractionResponse.ok || !extractionBody.success) {
        throw new Error(apiError(extractionBody, "Extraction 结果加载失败。"));
      }
      if (!snapshotResponse.ok || !snapshotBody.success) {
        throw new Error(apiError(snapshotBody, "审核快照加载失败。"));
      }
      if (!knowledgeResponse.ok || !knowledgeBody.success) {
        throw new Error(apiError(knowledgeBody, "Knowledge Asset 加载失败。"));
      }
      setExtractions(extractionBody.data.extractions);
      setSnapshots(snapshotBody.data.snapshots);
      setKnowledgeAssets(knowledgeBody.data.knowledge_assets);
      setActiveReview(null);
      setReviewer("");
      setReviewComment("");
      setRevisedContent("");
    } finally {
      setIsReviewLoading(false);
    }
  }

  async function loadReview(reviewId: string) {
    const response = await fetch(apiPath(`/api/reviews/${reviewId}`));
    const body = await response.json();
    if (!response.ok || !body.success) {
      throw new Error(apiError(body, "审核任务加载失败。"));
    }
    const review = body.data as ExtractionReview;
    setActiveReview(review);
    setReviewer(review.reviewer || "");
    setReviewComment(review.review_comment || "");
    setRevisedContent(review.revised_content ?? review.original_content);
  }

  async function startReview(extraction: AssetExtraction) {
    if (!selectedAsset) return;
    setIsReviewSubmitting(true);
    setError("");
    setMessage("");
    try {
      const response = await fetch(apiPath(`/api/assets/${selectedAsset.id}/reviews`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ extraction_id: extraction.id }),
      });
      const body = await response.json();
      if (!response.ok || !body.success) {
        if (body?.detail?.code === "PENDING_REVIEW_EXISTS") {
          const existingId = body.detail.details?.existing_review_id;
          if (existingId) {
            await loadReview(existingId);
            setMessage("已恢复该 Extraction 的待审核任务。");
            return;
          }
        }
        throw new Error(apiError(body, "审核任务创建失败。"));
      }
      const review = body.data as ExtractionReview;
      setActiveReview(review);
      setReviewer(review.reviewer || "");
      setReviewComment("");
      setRevisedContent(review.original_content);
      setMessage("审核任务已创建；原始 Extraction 保持只读。");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "审核任务创建失败。");
    } finally {
      setIsReviewSubmitting(false);
    }
  }

  async function submitReview(decision: Exclude<ExtractionReviewStatus, "pending">) {
    if (!selectedAsset || !activeReview) return;
    if (!reviewer.trim()) {
      setError("请填写审核人。");
      return;
    }
    setIsReviewSubmitting(true);
    setError("");
    setMessage("");
    try {
      const response = await fetch(apiPath(`/api/reviews/${activeReview.id}`), {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          review_status: decision,
          reviewer: reviewer.trim(),
          review_comment: reviewComment.trim() || null,
          revised_content: revisedContent,
        }),
      });
      const body = await response.json();
      if (!response.ok || !body.success) {
        throw new Error(apiError(body, "审核提交失败。"));
      }
      setActiveReview(body.data.review);
      const snapshotResponse = await fetch(apiPath(`/api/assets/${selectedAsset.id}/snapshots`));
      const snapshotBody = await snapshotResponse.json();
      if (snapshotResponse.ok && snapshotBody.success) {
        setSnapshots(snapshotBody.data.snapshots);
      }
      const labels = {
        approved: "审核已通过，并生成不可变快照。",
        rejected: "审核已拒绝，不生成快照。",
        needs_revision: "已标记需要修改，不生成快照。",
      };
      setMessage(labels[decision]);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "审核提交失败。");
    } finally {
      setIsReviewSubmitting(false);
    }
  }

  async function publishSnapshot(snapshotId: string) {
    if (!selectedAsset) return;
    setIsKnowledgeSubmitting(true);
    setError("");
    setMessage("");
    try {
      const response = await fetch(apiPath(`/api/snapshots/${snapshotId}/publish`), {
        method: "POST",
      });
      const body = await response.json();
      if (!response.ok || !body.success) {
        throw new Error(apiError(body, "Knowledge Asset 发布失败。"));
      }
      await loadReviewWorkspace(selectedAsset.id);
      setMessage(
        body.data.created
          ? "Approved Snapshot 已发布为 Knowledge Asset；未进入 RAG。"
          : "该 Snapshot 已发布，返回已有 Knowledge Asset。",
      );
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Knowledge Asset 发布失败。");
    } finally {
      setIsKnowledgeSubmitting(false);
    }
  }

  async function archiveKnowledgeAsset(knowledgeAssetId: string) {
    if (!selectedAsset) return;
    setIsKnowledgeSubmitting(true);
    setError("");
    setMessage("");
    try {
      const response = await fetch(apiPath(`/api/knowledge-assets/${knowledgeAssetId}/archive`), {
        method: "POST",
      });
      const body = await response.json();
      if (!response.ok || !body.success) {
        throw new Error(apiError(body, "Knowledge Asset 归档失败。"));
      }
      await loadReviewWorkspace(selectedAsset.id);
      setMessage("Knowledge Asset 已归档，历史内容和来源链保持不变。");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Knowledge Asset 归档失败。");
    } finally {
      setIsKnowledgeSubmitting(false);
    }
  }

  return (
    <div className="p2-page">
      <div className="page-hero">
        <h1>AI 素材中心</h1>
        <p>接入素材、查看 Extraction，并用人工决策形成可信且不可变的审核快照。</p>
      </div>

      <div className="roadmap-banner material-boundary-banner">
        <span className="roadmap-icon">P2</span>
        <div>
          <strong>Knowledge Asset Foundation</strong>
          <p>P2-M4 只将 approved snapshot 治理为独立 Knowledge Asset。Embedding、RAG 同步和 Agent 调用均未接入。</p>
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

      <section className="material-panel review-foundation-panel">
        <div className="material-panel-header">
          <div>
            <h2>Extraction 人工审核</h2>
            <p>原始 Extraction 只读；只有 approved 会生成不可变快照。</p>
          </div>
          {selectedAsset && (
            <button
              className="btn-secondary btn-sm"
              type="button"
              disabled={isReviewLoading || isReviewSubmitting}
              onClick={() => void loadReviewWorkspace(selectedAsset.id)}
            >
              {isReviewLoading ? "加载中..." : "刷新审核区"}
            </button>
          )}
        </div>

        {!selectedAsset ? (
          <div className="empty-state">
            <p className="empty-title">请先选择素材</p>
            <p className="empty-desc">选择素材后可查看其 Extraction 和审核快照。</p>
          </div>
        ) : isReviewLoading ? (
          <div className="empty-state"><p className="empty-title">正在加载审核数据...</p></div>
        ) : (
          <div className="review-workspace">
            <div className="review-extraction-column">
              <h3>Extraction 结果</h3>
              {extractions.length === 0 ? (
                <div className="review-empty-note">
                  当前素材还没有 Extraction 结果。P2-M3 不会自动调用 OCR 或 Caption。
                </div>
              ) : (
                <div className="review-extraction-list">
                  {extractions.map((extraction) => (
                    <article className="review-extraction-card" key={extraction.id}>
                      <div className="review-card-meta">
                        <span>{extraction.extract_type}</span>
                        <span>v{extraction.version}</span>
                      </div>
                      <pre>{extraction.content}</pre>
                      <button
                        className="btn-secondary btn-sm"
                        type="button"
                        disabled={isReviewSubmitting}
                        onClick={() => void startReview(extraction)}
                      >
                        创建 / 恢复审核
                      </button>
                    </article>
                  ))}
                </div>
              )}
            </div>

            <div className="review-editor-column">
              <h3>审核决策</h3>
              {!activeReview ? (
                <div className="review-empty-note">从左侧选择一条 Extraction 开始审核。</div>
              ) : (
                <div className="review-editor">
                  <div className="review-card-meta">
                    <span>Review v{activeReview.version}</span>
                    <span className={`review-status-badge status-${activeReview.review_status}`}>
                      {activeReview.review_status}
                    </span>
                  </div>
                  <label>
                    原始 Extraction（只读）
                    <textarea value={activeReview.original_content} rows={5} readOnly />
                  </label>
                  <label>
                    人工修订内容
                    <textarea
                      value={revisedContent}
                      rows={7}
                      disabled={activeReview.review_status !== "pending" || isReviewSubmitting}
                      onChange={(event) => setRevisedContent(event.target.value)}
                    />
                  </label>
                  <div className="review-form-grid">
                    <label>
                      审核人
                      <input
                        value={reviewer}
                        disabled={activeReview.review_status !== "pending" || isReviewSubmitting}
                        onChange={(event) => setReviewer(event.target.value)}
                        placeholder="reviewer"
                      />
                    </label>
                    <label>
                      审核说明
                      <input
                        value={reviewComment}
                        disabled={activeReview.review_status !== "pending" || isReviewSubmitting}
                        onChange={(event) => setReviewComment(event.target.value)}
                        placeholder="可选"
                      />
                    </label>
                  </div>
                  {activeReview.review_status === "pending" ? (
                    <div className="review-decision-actions">
                      <button className="btn-primary" type="button" disabled={isReviewSubmitting} onClick={() => void submitReview("approved")}>通过</button>
                      <button className="btn-secondary" type="button" disabled={isReviewSubmitting} onClick={() => void submitReview("needs_revision")}>需要修改</button>
                      <button className="btn-danger" type="button" disabled={isReviewSubmitting} onClick={() => void submitReview("rejected")}>拒绝</button>
                    </div>
                  ) : (
                    <p className="review-terminal-note">终态审核不可再次修改；需要新决策时请创建下一版 Review。</p>
                  )}
                </div>
              )}
            </div>

            <div className="review-snapshot-column">
              <h3>Approved Snapshots</h3>
              {snapshots.length === 0 ? (
                <div className="review-empty-note">暂无 approved snapshot。</div>
              ) : (
                <div className="review-snapshot-list">
                  {snapshots.map((snapshot) => (
                    <article className="review-snapshot-card" key={snapshot.id}>
                      <div className="review-card-meta">
                        <span>{snapshot.extract_type} · v{snapshot.version}</span>
                        <span>immutable</span>
                      </div>
                      <p>{snapshot.approved_content}</p>
                      <small>{snapshot.id}</small>
                      {knowledgeAssets.some((item) => item.source_snapshot_id === snapshot.id) ? (
                        <span className="knowledge-published-note">已发布 Knowledge Asset</span>
                      ) : (
                        <button
                          className="btn-primary btn-sm"
                          type="button"
                          disabled={isKnowledgeSubmitting}
                          onClick={() => void publishSnapshot(snapshot.id)}
                        >
                          发布为 Knowledge Asset
                        </button>
                      )}
                    </article>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </section>

      <section className="material-panel knowledge-foundation-panel">
        <div className="material-panel-header">
          <div>
            <h2>Knowledge Assets</h2>
            <p>展示可信内容、状态、版本及完整来源；本区不提供 RAG 或 Embedding 操作。</p>
          </div>
        </div>
        {!selectedAsset ? (
          <div className="empty-state">
            <p className="empty-title">请先选择素材</p>
            <p className="empty-desc">选择素材后可查看其治理后的 Knowledge Asset。</p>
          </div>
        ) : knowledgeAssets.length === 0 ? (
          <div className="review-empty-note">暂无 Knowledge Asset。请先发布 approved snapshot。</div>
        ) : (
          <div className="knowledge-asset-list">
            {knowledgeAssets.map((knowledge) => (
              <article className="knowledge-asset-card" key={knowledge.id}>
                <div className="review-card-meta">
                  <span>{knowledge.content_type} · v{knowledge.version}</span>
                  <span className={`knowledge-status status-${knowledge.status}`}>{knowledge.status}</span>
                </div>
                <p>{knowledge.content}</p>
                <dl className="knowledge-trace-grid">
                  <div><dt>Knowledge Asset</dt><dd>{knowledge.id}</dd></div>
                  <div><dt>Snapshot</dt><dd>{knowledge.source_trace.snapshot_id}</dd></div>
                  <div><dt>Review</dt><dd>{knowledge.source_trace.review_id}</dd></div>
                  <div><dt>Extraction</dt><dd>{knowledge.source_trace.extraction_id}</dd></div>
                  <div><dt>Asset</dt><dd>{knowledge.source_trace.asset_id}</dd></div>
                </dl>
                {knowledge.status === "active" && (
                  <button
                    className="btn-secondary btn-sm"
                    type="button"
                    disabled={isKnowledgeSubmitting}
                    onClick={() => void archiveKnowledgeAsset(knowledge.id)}
                  >
                    归档
                  </button>
                )}
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
