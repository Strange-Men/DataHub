import { FormEvent, useEffect, useRef, useState } from "react";
import { apiFetch as fetch, apiPath } from "../api";
import { useAuth } from "../auth/AuthContext";
import { P2WorkflowHeader } from "../components/P2WorkflowHeader";
import { apiErrorMessage, can, FORBIDDEN_MESSAGE, permissionHint, ROLE_LABELS, type FrontendPermission } from "../governance";
import type {
  Asset,
  AssetExtraction,
  AssetPagination,
  AssetReviewSnapshot,
  ExtractionReview,
  ExtractionReviewStatus,
  KnowledgeAsset,
  KnowledgeIndexEntry,
} from "../types";

const PAGE_SIZE = 10;

function formatBytes(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KiB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MiB`;
}

function extractionTypeLabel(value: string): string {
  if (value === "ocr") return "文字识别";
  if (value === "caption") return "图像描述";
  if (value === "metadata") return "元数据提取";
  return value;
}

function apiError(body: any, status: number, fallback: string): string {
  return apiErrorMessage(body, status, fallback);
}

export function P2MaterialCenter() {
  const { role } = useAuth();
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
  const [knowledgeIndexEntries, setKnowledgeIndexEntries] = useState<KnowledgeIndexEntry[]>([]);
  const [embeddedIndexIds, setEmbeddedIndexIds] = useState<Set<string>>(new Set());
  const [activeReview, setActiveReview] = useState<ExtractionReview | null>(null);
  const [reviewer, setReviewer] = useState("");
  const [reviewComment, setReviewComment] = useState("");
  const [revisedContent, setRevisedContent] = useState("");
  const [isReviewLoading, setIsReviewLoading] = useState(false);
  const [isReviewSubmitting, setIsReviewSubmitting] = useState(false);
  const [isKnowledgeSubmitting, setIsKnowledgeSubmitting] = useState(false);
  const [isIndexSubmitting, setIsIndexSubmitting] = useState(false);
  const [isExtractionSubmitting, setIsExtractionSubmitting] = useState(false);
  const [extractType, setExtractType] = useState<"ocr" | "caption" | "metadata">("ocr");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  function allowed(permission: FrontendPermission): boolean {
    return can(role, permission);
  }

  function guard(permission: FrontendPermission): boolean {
    if (allowed(permission)) return true;
    setError(FORBIDDEN_MESSAGE);
    return false;
  }

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
        throw new Error(apiError(body, response.status, "素材列表加载失败。"));
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
    if (!guard("p2.asset_upload")) return;
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
        throw new Error(apiError(body, response.status, "素材上传失败。"));
      }
      setSelectedAsset(body.data);
      setExtractions([]);
      setSnapshots([]);
      setKnowledgeAssets([]);
      setKnowledgeIndexEntries([]);
      setEmbeddedIndexIds(new Set());
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
        throw new Error(apiError(body, response.status, "素材详情加载失败。"));
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
      const [extractionResponse, snapshotResponse, knowledgeResponse, indexResponse] = await Promise.all([
        fetch(apiPath(`/api/assets/${assetId}/extractions`)),
        fetch(apiPath(`/api/assets/${assetId}/snapshots`)),
        fetch(apiPath(`/api/knowledge-assets?page=1&page_size=100&asset_id=${assetId}`)),
        fetch(apiPath(`/api/knowledge-index?page=1&page_size=100&asset_id=${assetId}`)),
      ]);
      const [extractionBody, snapshotBody, knowledgeBody, indexBody] = await Promise.all([
        extractionResponse.json(),
        snapshotResponse.json(),
        knowledgeResponse.json(),
        indexResponse.json(),
      ]);
      if (!extractionResponse.ok || !extractionBody.success) {
        throw new Error(apiError(extractionBody, extractionResponse.status, "内容解析结果加载失败。"));
      }
      if (!snapshotResponse.ok || !snapshotBody.success) {
        throw new Error(apiError(snapshotBody, snapshotResponse.status, "审核快照加载失败。"));
      }
      if (!knowledgeResponse.ok || !knowledgeBody.success) {
        throw new Error(apiError(knowledgeBody, knowledgeResponse.status, "知识资产加载失败。"));
      }
      if (!indexResponse.ok || !indexBody.success) {
        throw new Error(apiError(indexBody, indexResponse.status, "知识索引状态加载失败。"));
      }
      setExtractions(extractionBody.data.extractions);
      setSnapshots(snapshotBody.data.snapshots);
      setKnowledgeAssets(knowledgeBody.data.knowledge_assets);
      setKnowledgeIndexEntries(indexBody.data.index_entries);
      const activeIndexes = (indexBody.data.index_entries as KnowledgeIndexEntry[]).filter(
        (item) => item.status !== "archived",
      );
      const embeddingChecks = await Promise.all(activeIndexes.map(async (item) => {
        const response = await fetch(apiPath(`/api/knowledge-embeddings?page=1&page_size=1&index_entry_id=${item.id}`));
        if (!response.ok) return null;
        const body = await response.json();
        return body?.success && body?.data?.pagination?.total > 0 ? item.id : null;
      }));
      setEmbeddedIndexIds(new Set(embeddingChecks.filter((item): item is string => Boolean(item))));
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
      throw new Error(apiError(body, response.status, "审核任务加载失败。"));
    }
    const review = body.data as ExtractionReview;
    setActiveReview(review);
    setReviewer(review.reviewer || "");
    setReviewComment(review.review_comment || "");
    setRevisedContent(review.revised_content ?? review.original_content);
  }

  async function startReview(extraction: AssetExtraction) {
    if (!selectedAsset) return;
    if (!guard("p2.revise")) return;
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
            setMessage("已恢复该内容解析结果的待审核任务。");
            return;
          }
        }
        throw new Error(apiError(body, response.status, "审核任务创建失败。"));
      }
      const review = body.data as ExtractionReview;
      setActiveReview(review);
      setReviewer(review.reviewer || "");
      setReviewComment("");
      setRevisedContent(review.original_content);
      setMessage("审核任务已创建；原始解析结果保持只读。");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "审核任务创建失败。");
    } finally {
      setIsReviewSubmitting(false);
    }
  }

  async function submitReview(decision: Exclude<ExtractionReviewStatus, "pending">) {
    if (!selectedAsset || !activeReview) return;
    if (!guard("p2.review")) return;
    if (decision === "rejected" && !window.confirm("拒绝后本次审核不会生成快照，内容也不会进入发布链。是否继续？")) return;
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
        throw new Error(apiError(body, response.status, "审核提交失败。"));
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
    if (!guard("p2.publish")) return;
    if (!window.confirm("发布新知识版本可能使旧版本进入归档状态。来源链和历史记录会保留。是否继续？")) return;
    setIsKnowledgeSubmitting(true);
    setError("");
    setMessage("");
    try {
      const response = await fetch(apiPath(`/api/snapshots/${snapshotId}/publish`), {
        method: "POST",
      });
      const body = await response.json();
      if (!response.ok || !body.success) {
        throw new Error(apiError(body, response.status, "知识资产发布失败。"));
      }
      await loadReviewWorkspace(selectedAsset.id);
      setMessage(
        body.data.created
          ? "已通过审核的知识快照已发布为知识资产；尚未进入检索。"
          : "该知识快照已经发布，已返回现有知识资产。",
      );
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "知识资产发布失败。");
    } finally {
      setIsKnowledgeSubmitting(false);
    }
  }

  async function archiveKnowledgeAsset(knowledgeAssetId: string) {
    if (!selectedAsset) return;
    if (!guard("p2.archive")) return;
    if (!window.confirm("归档后该知识将立即停止被检索，历史记录仍会保留。是否继续？")) return;
    setIsKnowledgeSubmitting(true);
    setError("");
    setMessage("");
    try {
      const response = await fetch(apiPath(`/api/knowledge-assets/${knowledgeAssetId}/archive`), {
        method: "POST",
      });
      const body = await response.json();
      if (!response.ok || !body.success) {
        throw new Error(apiError(body, response.status, "知识资产归档失败。"));
      }
      await loadReviewWorkspace(selectedAsset.id);
      setMessage("知识资产已归档，历史内容和来源链保持不变。");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "知识资产归档失败。");
    } finally {
      setIsKnowledgeSubmitting(false);
    }
  }

  async function createKnowledgeIndex(knowledgeAssetId: string) {
    if (!selectedAsset) return;
    if (!guard("p2.index")) return;
    setIsIndexSubmitting(true);
    setError("");
    setMessage("");
    try {
      const response = await fetch(apiPath(`/api/knowledge-assets/${knowledgeAssetId}/index`), {
        method: "POST",
      });
      const body = await response.json();
      if (!response.ok || !body.success) {
        throw new Error(apiError(body, response.status, "知识索引创建失败。"));
      }
      await loadReviewWorkspace(selectedAsset.id);
      setMessage(
        body.data.created
          ? "文本索引已经生成，下一步请生成知识向量；当前尚未开放检索。"
          : "该知识资产已经存在索引记录，没有重复生成内容片段。",
      );
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "知识索引创建失败。");
    } finally {
      setIsIndexSubmitting(false);
    }
  }

  async function archiveKnowledgeIndex(indexEntryId: string) {
    if (!selectedAsset) return;
    if (!guard("p2.archive")) return;
    if (!window.confirm("归档后该索引将立即停止被检索，不可变 Chunk 仅保留用于审计。是否继续？")) return;
    setIsIndexSubmitting(true);
    setError("");
    setMessage("");
    try {
      const response = await fetch(apiPath(`/api/knowledge-index/${indexEntryId}/archive`), {
        method: "POST",
      });
      const body = await response.json();
      if (!response.ok || !body.success) {
        throw new Error(apiError(body, response.status, "知识索引归档失败。"));
      }
      await loadReviewWorkspace(selectedAsset.id);
      setMessage("知识索引已归档；不可变内容片段仅保留审计，不再提供检索。");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "知识索引归档失败。");
    } finally {
      setIsIndexSubmitting(false);
    }
  }

  async function startExtraction() {
    if (!selectedAsset || !guard("p2.extract")) return;
    setIsExtractionSubmitting(true);
    setError("");
    setMessage("");
    try {
      const response = await fetch(apiPath(`/api/assets/${selectedAsset.id}/extract`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ extract_type: extractType, provider: "mock" }),
      });
      const body = await response.json();
      if (!response.ok || !body.success) {
        throw new Error(apiError(body, response.status, "内容解析执行失败。"));
      }
      await loadReviewWorkspace(selectedAsset.id);
      setMessage(`${extractType.toUpperCase()} 内容解析已完成并刷新结果。`);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "内容解析执行失败。");
    } finally {
      setIsExtractionSubmitting(false);
    }
  }

  async function buildEmbedding(indexEntryId: string) {
    if (!selectedAsset || !guard("p2.embed")) return;
    setIsIndexSubmitting(true);
    setError("");
    setMessage("");
    try {
      const response = await fetch(apiPath(`/api/knowledge-index/${indexEntryId}/embed`), { method: "POST" });
      const body = await response.json();
      if (!response.ok || !body.success) {
        throw new Error(apiError(body, response.status, "向量生成失败。"));
      }
      await loadReviewWorkspace(selectedAsset.id);
      setMessage("知识向量已经生成，点击“开放检索”后才会被搜索到。");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "向量生成失败。");
    } finally {
      setIsIndexSubmitting(false);
    }
  }

  async function serveKnowledgeIndex(indexEntryId: string) {
    if (!selectedAsset || !guard("p2.serve")) return;
    if (!window.confirm("开放后该知识将立即进入检索结果。请确认内容、审核快照和来源链均正确。是否继续？")) return;
    setIsIndexSubmitting(true);
    setError("");
    setMessage("");
    try {
      const response = await fetch(apiPath(`/api/knowledge-index/${indexEntryId}/serve`), { method: "POST" });
      const body = await response.json();
      if (!response.ok || !body.success) {
        throw new Error(apiError(body, response.status, "开放检索失败。"));
      }
      await loadReviewWorkspace(selectedAsset.id);
      setMessage("当前知识已经开放检索，可以进入“检索与 Agent 验证”页面检查召回和来源链。");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "开放检索失败。");
    } finally {
      setIsIndexSubmitting(false);
    }
  }

  const activeKnowledge = knowledgeAssets.find((item) => item.status === "active");
  const currentIndex = activeKnowledge
    ? knowledgeIndexEntries.find((item) => item.knowledge_asset_id === activeKnowledge.id)
    : knowledgeIndexEntries[0];
  const hasEmbedding = Boolean(currentIndex && embeddedIndexIds.has(currentIndex.id));
  const isArchived = Boolean(
    currentIndex?.status === "archived" ||
    (selectedAsset && knowledgeAssets.length > 0 && knowledgeAssets.every((item) => item.status === "archived")),
  );
  const currentStage = currentIndex?.status === "serving" || isArchived
    ? 5
    : knowledgeAssets.length > 0
      ? 4
      : snapshots.length > 0
        ? 3
        : extractions.length > 0
          ? 2
          : 1;
  const workflowStatus = isArchived
    ? "已归档"
    : currentIndex?.status === "serving"
      ? "已开放检索"
      : currentIndex?.status === "ready" && hasEmbedding
        ? "向量已就绪"
      : currentIndex?.status === "ready"
          ? "索引已就绪，待生成向量"
          : currentIndex?.status === "failed"
            ? "索引构建失败，请检查技术详情"
          : knowledgeAssets.length > 0
            ? "知识资产已发布，待建立索引"
            : snapshots.length > 0
              ? "审核已通过，待发布知识资产"
              : extractions.length > 0
                ? "内容已解析，待修订与审核"
                : selectedAsset
                  ? "素材已上传，待内容解析"
                  : "等待上传或选择素材";
  const nextAction = isArchived
    ? "查看来源追踪"
    : currentIndex?.status === "serving"
      ? "进入检索与 Agent 验证"
      : currentIndex?.status === "ready" && hasEmbedding
        ? "开放检索"
        : currentIndex?.status === "ready"
          ? "生成向量"
          : currentIndex?.status === "failed"
            ? "查看索引状态"
          : knowledgeAssets.length > 0
            ? "建立索引"
            : snapshots.length > 0
              ? "发布知识资产"
              : extractions.length > 0
                ? "进入人工审核"
                : selectedAsset
                  ? "发起内容解析"
                  : "上传素材";

  function goToNextAction() {
    if (currentIndex?.status === "serving") {
      window.location.assign("/retrieval-validation");
      return;
    }
    const target = currentStage === 1 ? "p2-stage-upload" : currentStage <= 3 ? "p2-stage-review" : "p2-stage-index";
    document.getElementById(target)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  return (
    <div className="p2-page">
      <div className="page-hero">
        <h1>P2 多模态知识治理</h1>
        <p>按五个用户阶段完成素材治理、知识发布、开放检索和归档，系统会根据真实后端状态提示下一步。</p>
      </div>

      <P2WorkflowHeader currentStage={currentStage} status={workflowStatus} nextAction={nextAction} onNext={goToNextAction} />

      {message && <div className="feedback success">{message}</div>}
      {error && <div className="feedback error">{error}</div>}
      <div className="role-scope-banner">
        <strong>当前角色：{role ? ROLE_LABELS[role] : "未认证"}</strong>
        <span>
          {role === "admin" ? "可执行全部 P2 治理操作。" :
            role === "cleaner" ? "可上传、解析与创建修订任务；审核、发布、生成向量、开放检索和归档无权限。" :
            role === "reviewer" ? "可查看并审核；上传、生成向量、开放检索和归档无权限。" :
            role === "service" ? "仅提供检索、Agent 与问题反馈服务入口；人工治理写操作无权限。" :
            role === "viewer" ? "只读；所有写操作均无权限。" : "请应用有效访问令牌以确认权限。"}
        </span>
      </div>

      <section className="material-panel" id="p2-stage-upload">
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
            <button
              className="btn-primary"
              type="submit"
              disabled={isUploading || !selectedFile || !allowed("p2.asset_upload")}
              title={permissionHint(role, "p2.asset_upload")}
            >
              {isUploading ? "上传中..." : "上传素材"}
            </button>
          </div>
          {!allowed("p2.asset_upload") && <small className="permission-hint">{FORBIDDEN_MESSAGE}</small>}
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
          <>
            <dl className="asset-detail-grid">
              <div><dt>素材 ID</dt><dd>{selectedAsset.id}</dd></div>
              <div><dt>文件名</dt><dd>{selectedAsset.file_name}</dd></div>
              <div><dt>素材类型</dt><dd>{selectedAsset.asset_type}</dd></div>
              <div><dt>文件格式</dt><dd>{selectedAsset.mime_type}</dd></div>
              <div><dt>大小</dt><dd>{formatBytes(selectedAsset.size)}</dd></div>
              <div><dt>状态</dt><dd>{selectedAsset.status === "uploaded" ? "已上传" : selectedAsset.status}</dd></div>
              <div className="asset-detail-wide"><dt>SHA-256</dt><dd>{selectedAsset.hash}</dd></div>
              <div className="asset-detail-wide"><dt>存储位置</dt><dd>{selectedAsset.storage_uri}</dd></div>
              <div><dt>创建时间</dt><dd>{selectedAsset.created_at}</dd></div>
              <div><dt>更新时间</dt><dd>{selectedAsset.updated_at}</dd></div>
            </dl>
            <div className="inline-action-panel">
              <label>
                内容解析类型
                <select value={extractType} onChange={(event) => setExtractType(event.target.value as typeof extractType)} disabled={isExtractionSubmitting}>
                  <option value="ocr">文字识别</option>
                  <option value="caption">图像描述</option>
                  <option value="metadata">元数据提取</option>
                </select>
              </label>
              <button
                className="btn-primary"
                type="button"
                onClick={() => void startExtraction()}
                disabled={isExtractionSubmitting || !allowed("p2.extract")}
                title={permissionHint(role, "p2.extract")}
              >
                {isExtractionSubmitting ? "内容解析中..." : "发起内容解析"}
              </button>
              {!allowed("p2.extract") && <small className="permission-hint">{FORBIDDEN_MESSAGE}</small>}
            </div>
          </>
        )}
      </section>

      <section className="material-panel review-foundation-panel" id="p2-stage-review">
        <div className="material-panel-header">
          <div>
            <h2>内容修订与人工审核</h2>
            <p>原始解析内容保持只读；只有审核通过后才会生成不可变知识快照。</p>
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
            <p className="empty-desc">选择素材后可查看内容解析结果和审核快照。</p>
          </div>
        ) : isReviewLoading ? (
          <div className="empty-state"><p className="empty-title">正在加载审核数据...</p></div>
        ) : (
          <div className="review-workspace">
            <div className="review-extraction-column">
              <h3>内容解析结果</h3>
              {extractions.length === 0 ? (
                <div className="review-empty-note">
                  当前素材还没有内容解析结果。请在素材详情中选择类型并发起真实解析。
                </div>
              ) : (
                <div className="review-extraction-list">
                  {extractions.map((extraction) => (
                    <article className="review-extraction-card" key={extraction.id}>
                      <div className="review-card-meta">
                        <span>{extractionTypeLabel(extraction.extract_type)}</span>
                        <span>版本 {extraction.version}</span>
                      </div>
                      <pre>{extraction.content}</pre>
                      <button
                        className="btn-secondary btn-sm"
                        type="button"
                        disabled={isReviewSubmitting || !allowed("p2.revise")}
                        title={permissionHint(role, "p2.revise")}
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
                <div className="review-empty-note">从左侧选择一条内容解析结果开始审核。</div>
              ) : (
                <div className="review-editor">
                  <div className="review-card-meta">
                    <span>审核版本 {activeReview.version}</span>
                    <span className={`review-status-badge status-${activeReview.review_status}`}>
                      {activeReview.review_status === "pending" ? "待审核" : activeReview.review_status === "approved" ? "已通过" : activeReview.review_status === "needs_revision" ? "需修改" : "已拒绝"}
                    </span>
                  </div>
                  <label>
                    原始解析内容（只读）
                    <textarea value={activeReview.original_content} rows={5} readOnly />
                  </label>
                  <label>
                    人工修订内容
                    <textarea
                      value={revisedContent}
                      rows={7}
                      disabled={activeReview.review_status !== "pending" || isReviewSubmitting || !allowed("p2.review")}
                      onChange={(event) => setRevisedContent(event.target.value)}
                    />
                  </label>
                  <div className="review-form-grid">
                    <label>
                      审核人
                      <input
                        value={reviewer}
                        disabled={activeReview.review_status !== "pending" || isReviewSubmitting || !allowed("p2.review")}
                        onChange={(event) => setReviewer(event.target.value)}
                        placeholder="reviewer"
                      />
                    </label>
                    <label>
                      审核说明
                      <input
                        value={reviewComment}
                        disabled={activeReview.review_status !== "pending" || isReviewSubmitting || !allowed("p2.review")}
                        onChange={(event) => setReviewComment(event.target.value)}
                        placeholder="可选"
                      />
                    </label>
                  </div>
                  {activeReview.review_status === "pending" ? (
                    <div className="review-decision-actions">
                      <button className="btn-primary" type="button" disabled={isReviewSubmitting || !allowed("p2.review")} title={permissionHint(role, "p2.review")} onClick={() => void submitReview("approved")}>通过</button>
                      <button className="btn-secondary" type="button" disabled={isReviewSubmitting || !allowed("p2.review")} title={permissionHint(role, "p2.review")} onClick={() => void submitReview("needs_revision")}>需要修改</button>
                      <button className="btn-danger" type="button" disabled={isReviewSubmitting || !allowed("p2.review")} title={permissionHint(role, "p2.review")} onClick={() => void submitReview("rejected")}>拒绝</button>
                    </div>
                  ) : (
                    <p className="review-terminal-note">终态审核不可再次修改；需要新决策时请创建下一版审核记录。</p>
                  )}
                </div>
              )}
            </div>

            <div className="review-snapshot-column">
              <h3>已通过的知识快照</h3>
              {snapshots.length === 0 ? (
                <div className="review-empty-note">暂无已通过审核的知识快照。</div>
              ) : (
                <div className="review-snapshot-list">
                  {snapshots.map((snapshot) => (
                    <article className="review-snapshot-card" key={snapshot.id}>
                      <div className="review-card-meta">
                        <span>{extractionTypeLabel(snapshot.extract_type)} · 版本 {snapshot.version}</span>
                        <span>不可变</span>
                      </div>
                      <p>{snapshot.approved_content}</p>
                      <small>{snapshot.id}</small>
                      {knowledgeAssets.some((item) => item.source_snapshot_id === snapshot.id) ? (
                        <span className="knowledge-published-note">已发布知识资产</span>
                      ) : (
                        <button
                          className="btn-primary btn-sm"
                          type="button"
                          disabled={isKnowledgeSubmitting || !allowed("p2.publish")}
                          title={permissionHint(role, "p2.publish")}
                          onClick={() => void publishSnapshot(snapshot.id)}
                        >
                          发布为知识资产
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

      <section className="material-panel knowledge-foundation-panel" id="p2-stage-index">
        <div className="material-panel-header">
          <div>
            <h2>知识资产与检索状态</h2>
            <p>查看可信内容、不可变版本、来源追踪，以及建立索引、生成向量和开放检索的真实状态。</p>
          </div>
        </div>
        {!selectedAsset ? (
          <div className="empty-state">
            <p className="empty-title">请先选择素材</p>
            <p className="empty-desc">选择素材后可查看治理完成的知识资产。</p>
          </div>
        ) : knowledgeAssets.length === 0 ? (
          <div className="review-empty-note">暂无知识资产。请先发布已通过审核的知识快照。</div>
        ) : (
          <div className="knowledge-asset-list">
            {knowledgeAssets.map((knowledge) => {
              const indexEntry = knowledgeIndexEntries.find(
                (item) => item.knowledge_asset_id === knowledge.id,
              );
              return (
                <article className="knowledge-asset-card" key={knowledge.id}>
                <div className="review-card-meta">
                  <span>{extractionTypeLabel(knowledge.content_type)} · 版本 {knowledge.version}</span>
                  <span className={`knowledge-status status-${knowledge.status}`}>{knowledge.status === "active" ? "使用中" : knowledge.status === "archived" ? "已归档" : "草稿"}</span>
                </div>
                <p>{knowledge.content}</p>
                <dl className="knowledge-trace-grid">
                  <div><dt>知识资产</dt><dd>{knowledge.id}</dd></div>
                  <div><dt>知识快照</dt><dd>{knowledge.source_trace.snapshot_id}</dd></div>
                  <div><dt>人工审核</dt><dd>{knowledge.source_trace.review_id}</dd></div>
                  <div><dt>内容解析</dt><dd>{knowledge.source_trace.extraction_id}</dd></div>
                  <div><dt>原始素材</dt><dd>{knowledge.source_trace.asset_id}</dd></div>
                </dl>
                <p className="source-trace-flow" aria-label="完整来源链">
                  知识资产 → 知识快照 → 人工审核 → 内容解析 → 原始素材
                </p>
                <div className="knowledge-index-summary">
                  <div>
                    <span>检索开放状态</span>
                    <strong className={`knowledge-index-status status-${indexEntry?.status || "pending"}`}>
                      {indexEntry?.status === "serving" ? "已开放检索" :
                        indexEntry?.status === "ready" && embeddedIndexIds.has(indexEntry.id) ? "向量已就绪" :
                        indexEntry?.status === "ready" ? "索引已就绪，待生成向量" :
                        indexEntry?.status === "archived" ? "已归档" : indexEntry?.status === "failed" ? "构建失败" : "待建立索引"}
                    </strong>
                  </div>
                  {indexEntry ? (
                    <details className="technical-details"><summary>技术详情</summary><small>索引代次 {indexEntry.generation} · 内容片段 {indexEntry.chunks.length} · {indexEntry.id}</small></details>
                  ) : (
                    <small>尚未建立知识索引</small>
                  )}
                  {!indexEntry && knowledge.status === "active" && (
                    <button
                      className="btn-primary btn-sm"
                      type="button"
                      disabled={isIndexSubmitting || !allowed("p2.index")}
                      title={permissionHint(role, "p2.index")}
                      onClick={() => void createKnowledgeIndex(knowledge.id)}
                    >
                      建立索引
                    </button>
                  )}
                  {indexEntry?.status === "ready" && !embeddedIndexIds.has(indexEntry.id) && (
                    <button
                      className="btn-primary btn-sm"
                      type="button"
                      disabled={isIndexSubmitting || !allowed("p2.embed")}
                      title={permissionHint(role, "p2.embed")}
                      onClick={() => void buildEmbedding(indexEntry.id)}
                    >
                      生成向量
                    </button>
                  )}
                  {indexEntry?.status === "ready" && embeddedIndexIds.has(indexEntry.id) && (
                    <button
                      className="btn-primary btn-sm"
                      type="button"
                      disabled={isIndexSubmitting || !allowed("p2.serve")}
                      title={permissionHint(role, "p2.serve")}
                      onClick={() => void serveKnowledgeIndex(indexEntry.id)}
                    >
                      开放检索
                    </button>
                  )}
                  {indexEntry && indexEntry.status !== "archived" && (
                    <button
                      className="btn-secondary btn-sm"
                      type="button"
                      disabled={isIndexSubmitting || !allowed("p2.archive")}
                      title={permissionHint(role, "p2.archive")}
                      onClick={() => void archiveKnowledgeIndex(indexEntry.id)}
                    >
                      归档索引
                    </button>
                  )}
                </div>
                {knowledge.status === "active" && (
                  <button
                    className="btn-secondary btn-sm"
                    type="button"
                    disabled={isKnowledgeSubmitting || !allowed("p2.archive")}
                    title={permissionHint(role, "p2.archive")}
                    onClick={() => void archiveKnowledgeAsset(knowledge.id)}
                  >
                    归档
                  </button>
                )}
                {indexEntry?.status === "serving" && (
                  <a className="btn-outline btn-sm inline-link" href="/retrieval-validation">前往检索与 Agent 验证</a>
                )}
                </article>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
