import { useCallback, useEffect, useState } from "react";
import type { AuthRole } from "../../api";
import { p3Client, P3ApiError, type P3Client } from "../client";
import {
  toWorkspaceError,
  type P3WorkspaceError,
} from "../components/WorkspaceFeedback";
import type {
  JsonObject,
  P3AssetSourceSnapshot,
  P3AssetStatus,
  P3AssetType,
  P3AssetVersion,
  P3Project,
  P3Review,
  P3ReviewChecklist,
  P3ReviewDecision,
} from "../types";

const ASSET_PAGE_SIZE = 12;

export type AssetFilters = {
  assetType?: P3AssetType;
  status?: P3AssetStatus;
};

export function useAssetReviewWorkspace(
  project: P3Project | null,
  role: AuthRole | null,
  client: P3Client = p3Client,
) {
  const [assets, setAssets] = useState<P3AssetVersion[]>([]);
  const [assetTotal, setAssetTotal] = useState(0);
  const [assetOffset, setAssetOffset] = useState(0);
  const [assetFilters, setAssetFilters] = useState<AssetFilters>({});
  const [selectedAsset, setSelectedAsset] = useState<P3AssetVersion | null>(null);
  const [assetSources, setAssetSources] = useState<P3AssetSourceSnapshot[]>([]);
  const [review, setReview] = useState<P3Review | null>(null);
  const [reviewHistory, setReviewHistory] = useState<P3Review[]>([]);
  const [loadingAssets, setLoadingAssets] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [mutatingAsset, setMutatingAsset] = useState(false);
  const [error, setError] = useState<P3WorkspaceError | null>(null);
  const [notice, setNotice] = useState("");

  const loadAssets = useCallback(async (
    currentProject: P3Project,
    offset = 0,
    filters: AssetFilters = {},
    signal?: AbortSignal,
  ) => {
    setLoadingAssets(true);
    setError(null);
    try {
      const response = await client.listAssets(
        currentProject.id,
        {
          limit: ASSET_PAGE_SIZE,
          offset,
          asset_type: filters.assetType,
          status: filters.status,
        },
        { signal },
      );
      setAssets(response.data.items);
      setAssetTotal(response.data.total);
      setAssetOffset(response.data.offset);
    } catch (caught) {
      if (caught instanceof DOMException && caught.name === "AbortError") return;
      setError(toWorkspaceError(caught));
    } finally {
      setLoadingAssets(false);
    }
  }, [client]);

  const loadReviewHistory = useCallback(async (
    currentProject: P3Project,
    signal?: AbortSignal,
  ) => {
    try {
      const response = await client.listReviews(
        currentProject.id,
        { limit: 100, offset: 0 },
        { signal },
      );
      setReviewHistory(response.data.items);
    } catch (caught) {
      if (caught instanceof DOMException && caught.name === "AbortError") return;
      setError(toWorkspaceError(caught));
    }
  }, [client]);

  useEffect(() => {
    setSelectedAsset(null);
    setAssetSources([]);
    setReview(null);
    setNotice("");
    if (!project || project.status === "draft") {
      setAssets([]);
      setAssetTotal(0);
      return;
    }
    const controller = new AbortController();
    void Promise.all([
      loadAssets(project, 0, {}, controller.signal),
      loadReviewHistory(project, controller.signal),
    ]);
    return () => controller.abort();
  }, [loadAssets, loadReviewHistory, project]);

  const loadSelectedAsset = useCallback(async (
    currentProject: P3Project,
    assetVersionId: string,
  ) => {
    setLoadingDetail(true);
    setError(null);
    try {
      const [assetResponse, sourceResponse] = await Promise.all([
        client.getAsset(currentProject.id, assetVersionId),
        client.listAssetSources(currentProject.id, assetVersionId, {
          limit: 100,
          offset: 0,
        }),
      ]);
      setSelectedAsset(assetResponse.data);
      setAssetSources(sourceResponse.data.items);
      try {
        const reviewResponse = await client.getReview(currentProject.id, assetVersionId);
        setReview(reviewResponse.data);
      } catch (caught) {
        if (caught instanceof P3ApiError && caught.status === 404) {
          setReview(null);
        } else {
          throw caught;
        }
      }
      return assetResponse.data;
    } catch (caught) {
      setError(toWorkspaceError(caught));
      return null;
    } finally {
      setLoadingDetail(false);
    }
  }, [client]);

  const refreshCurrentProject = useCallback(async (
    preferredAssetId?: string,
  ) => {
    if (!project) return;
    await Promise.all([
      loadAssets(project, assetOffset, assetFilters),
      loadReviewHistory(project),
    ]);
    if (preferredAssetId) await loadSelectedAsset(project, preferredAssetId);
  }, [
    assetFilters,
    assetOffset,
    loadAssets,
    loadReviewHistory,
    loadSelectedAsset,
    project,
  ]);

  const generateDeterministic = useCallback(async (
    assetType: P3AssetType,
    idempotencyKey: string,
  ) => {
    if (!project) return null;
    setMutatingAsset(true);
    setError(null);
    try {
      const response = await client.generateDeterministicDraft(project.id, {
        asset_type: assetType,
        idempotency_key: idempotencyKey,
      });
      setNotice("确定性草稿已生成，可以查看结构化内容并创建人工修订。");
      await refreshCurrentProject(response.data.id);
      return response.data;
    } catch (caught) {
      setError(toWorkspaceError(caught));
      return null;
    } finally {
      setMutatingAsset(false);
    }
  }, [client, project, refreshCurrentProject]);

  const generateLlm = useCallback(async (
    assetType: P3AssetType,
    idempotencyKey: string,
  ) => {
    if (!project) return null;
    setMutatingAsset(true);
    setError(null);
    try {
      const response = await client.generateLlmDraft(project.id, {
        asset_type: assetType,
        idempotency_key: idempotencyKey,
      });
      setNotice("LLM 草稿已生成；它仍是未审核草稿，不能自动发布。");
      await refreshCurrentProject(response.data.id);
      return response.data;
    } catch (caught) {
      setError(toWorkspaceError(caught));
      return null;
    } finally {
      setMutatingAsset(false);
    }
  }, [client, project, refreshCurrentProject]);

  const createRevision = useCallback(async (
    contentPayload: JsonObject,
    idempotencyKey: string,
  ) => {
    if (!project || !selectedAsset) return null;
    setMutatingAsset(true);
    setError(null);
    try {
      const response = await client.createRevision(
        project.id,
        selectedAsset.id,
        contentPayload,
        idempotencyKey,
      );
      setNotice(`已创建版本 v${response.data.version_number}，旧版本内容没有被覆盖。`);
      await refreshCurrentProject(response.data.id);
      return response.data;
    } catch (caught) {
      setError(toWorkspaceError(caught));
      return null;
    } finally {
      setMutatingAsset(false);
    }
  }, [client, project, refreshCurrentProject, selectedAsset]);

  const submitReview = useCallback(async (idempotencyKey: string) => {
    if (!project || !selectedAsset) return null;
    setMutatingAsset(true);
    setError(null);
    try {
      const response = await client.submitReview(
        project.id,
        selectedAsset.id,
        idempotencyKey,
      );
      setNotice("草稿已提交审核，当前版本暂时不能编辑。");
      await refreshCurrentProject(response.data.id);
      return response.data;
    } catch (caught) {
      setError(toWorkspaceError(caught));
      return null;
    } finally {
      setMutatingAsset(false);
    }
  }, [client, project, refreshCurrentProject, selectedAsset]);

  const decideReview = useCallback(async (input: {
    decision: P3ReviewDecision;
    comments?: string | null;
    checklist: P3ReviewChecklist;
    idempotencyKey: string;
  }) => {
    if (!project || !selectedAsset || !role) return null;
    setMutatingAsset(true);
    setError(null);
    try {
      const response = await client.decideReview(
        project.id,
        selectedAsset.id,
        {
          decision: input.decision,
          comments: input.comments,
          checklist: input.checklist,
          idempotency_key: input.idempotencyKey,
        },
      );
      setReview(response.data);
      setNotice(
        input.decision === "approved"
          ? "内容已批准，但尚未发布。"
          : input.decision === "needs_revision"
            ? "内容已退回修改，可以基于当前版本创建新修订。"
            : "内容已拒绝，当前版本不会进入发布流程。",
      );
      await refreshCurrentProject(selectedAsset.id);
      return response.data;
    } catch (caught) {
      setError(toWorkspaceError(caught));
      return null;
    } finally {
      setMutatingAsset(false);
    }
  }, [client, project, refreshCurrentProject, role, selectedAsset]);

  const changeFilters = useCallback(async (filters: AssetFilters) => {
    setAssetFilters(filters);
    setAssetOffset(0);
    if (project) await loadAssets(project, 0, filters);
  }, [loadAssets, project]);

  return {
    assets,
    assetTotal,
    assetOffset,
    assetPageSize: ASSET_PAGE_SIZE,
    assetFilters,
    selectedAsset,
    assetSources,
    review,
    reviewHistory,
    loadingAssets,
    loadingDetail,
    mutatingAsset,
    error,
    notice,
    loadAssets,
    loadSelectedAsset: (assetVersionId: string) => (
      project ? loadSelectedAsset(project, assetVersionId) : Promise.resolve(null)
    ),
    generateDeterministic,
    generateLlm,
    createRevision,
    submitReview,
    decideReview,
    changeFilters,
    clearError: () => setError(null),
  };
}
