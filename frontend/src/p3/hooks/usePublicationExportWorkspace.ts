import { useCallback, useEffect, useRef, useState } from "react";
import { p3Client, P3ApiError, type P3Client } from "../client";
import {
  toWorkspaceError,
  type P3WorkspaceError,
} from "../components/WorkspaceFeedback";
import { createP3IdempotencyKey } from "../idempotency";
import type {
  P3AssetVersion,
  P3ExportArtifact,
  P3ExportFormat,
  P3ExportJob,
  P3Project,
  P3PublishedAsset,
} from "../types";

const EXPORT_PAGE_SIZE = 20;
type AssetRefresh = (assetVersionId?: string) => Promise<void>;

function safeDownloadName(value: string): string {
  const sanitized = value.replace(/[\\/\0\r\n"]/g, "_").trim();
  return sanitized || "p3-export";
}

export function usePublicationExportWorkspace(
  project: P3Project | null,
  selectedAsset: P3AssetVersion | null,
  refreshAssets: AssetRefresh,
  client: P3Client = p3Client,
) {
  const [publishedAssets, setPublishedAssets] = useState<P3PublishedAsset[]>([]);
  const [exportJobs, setExportJobs] = useState<P3ExportJob[]>([]);
  const [artifacts, setArtifacts] = useState<Record<string, P3ExportArtifact>>({});
  const [loading, setLoading] = useState(false);
  const [mutating, setMutating] = useState(false);
  const [error, setError] = useState<P3WorkspaceError | null>(null);
  const [notice, setNotice] = useState("");
  const operationKeys = useRef(new Map<string, string>());

  const keyFor = useCallback((scope: string) => {
    const existing = operationKeys.current.get(scope);
    if (existing) return existing;
    const key = createP3IdempotencyKey(scope);
    operationKeys.current.set(scope, key);
    return key;
  }, []);

  const clearKey = useCallback((scope: string) => {
    operationKeys.current.delete(scope);
  }, []);

  const loadArtifacts = useCallback(async (
    jobs: P3ExportJob[],
    signal?: AbortSignal,
  ) => {
    const artifactJobs = jobs.filter((job) => (
      job.status === "succeeded" || job.status === "revoked"
    ));
    const entries = await Promise.all(artifactJobs.map(async (job) => {
      try {
        const response = await client.getExportArtifact(job.id, { signal });
        return [job.id, response.data] as const;
      } catch (caught) {
        if (caught instanceof DOMException && caught.name === "AbortError") return null;
        if (caught instanceof P3ApiError && caught.status === 404) return null;
        throw caught;
      }
    }));
    setArtifacts(Object.fromEntries(entries.filter((entry) => entry !== null)));
  }, [client]);

  const loadWorkspace = useCallback(async (
    currentProject: P3Project,
    signal?: AbortSignal,
  ) => {
    setLoading(true);
    setError(null);
    try {
      const [publishedResponse, exportResponse] = await Promise.all([
        client.listPublishedAssets(
          currentProject.id,
          { limit: 100, offset: 0 },
          { signal },
        ),
        client.listExports(
          currentProject.id,
          { limit: EXPORT_PAGE_SIZE, offset: 0 },
          { signal },
        ),
      ]);
      setPublishedAssets(publishedResponse.data.items);
      setExportJobs(exportResponse.data.items);
      await loadArtifacts(exportResponse.data.items, signal);
    } catch (caught) {
      if (caught instanceof DOMException && caught.name === "AbortError") return;
      setError(toWorkspaceError(caught));
    } finally {
      setLoading(false);
    }
  }, [client, loadArtifacts]);

  useEffect(() => {
    setPublishedAssets([]);
    setExportJobs([]);
    setArtifacts({});
    setNotice("");
    if (!project || project.status === "draft") return;
    const controller = new AbortController();
    void loadWorkspace(project, controller.signal);
    return () => controller.abort();
  }, [loadWorkspace, project]);

  const publishSelected = useCallback(async () => {
    if (!project || !selectedAsset) return null;
    const scope = `publish-${project.id}-${selectedAsset.id}`;
    setMutating(true);
    setError(null);
    try {
      const response = await client.publishAsset(
        project.id,
        selectedAsset.id,
        keyFor(scope),
      );
      clearKey(scope);
      setNotice(
        response.data.superseded_asset_version_id
          ? "新版本已发布，旧的当前正式版本已被替代。"
          : "版本已发布为当前正式 P3 数据资产。",
      );
      await Promise.all([
        refreshAssets(selectedAsset.id),
        loadWorkspace(project),
      ]);
      return response.data;
    } catch (caught) {
      setError(toWorkspaceError(caught));
      return null;
    } finally {
      setMutating(false);
    }
  }, [
    clearKey,
    client,
    keyFor,
    loadWorkspace,
    project,
    refreshAssets,
    selectedAsset,
  ]);

  const archiveAsset = useCallback(async (assetVersionId: string) => {
    if (!project) return null;
    const scope = `archive-${project.id}-${assetVersionId}`;
    setMutating(true);
    setError(null);
    try {
      const response = await client.archiveAsset(
        project.id,
        assetVersionId,
        keyFor(scope),
      );
      clearKey(scope);
      setNotice("版本已逻辑归档；历史审核与来源快照继续保留。");
      await Promise.all([
        refreshAssets(assetVersionId),
        loadWorkspace(project),
      ]);
      return response.data;
    } catch (caught) {
      setError(toWorkspaceError(caught));
      return null;
    } finally {
      setMutating(false);
    }
  }, [clearKey, client, keyFor, loadWorkspace, project, refreshAssets]);

  const createExport = useCallback(async (
    assetVersionId: string,
    exportFormat: P3ExportFormat,
  ) => {
    if (!project) return null;
    const scope = `export-${project.id}-${assetVersionId}-${exportFormat}`;
    setMutating(true);
    setError(null);
    try {
      const response = await client.createExport(
        project.id,
        assetVersionId,
        exportFormat,
        keyFor(scope),
      );
      clearKey(scope);
      setNotice(`${exportFormat.toUpperCase()} 导出已完成，可以下载。`);
      await loadWorkspace(project);
      return response.data;
    } catch (caught) {
      setError(toWorkspaceError(caught));
      return null;
    } finally {
      setMutating(false);
    }
  }, [clearKey, client, keyFor, loadWorkspace, project]);

  const downloadArtifact = useCallback(async (artifact: P3ExportArtifact) => {
    if (artifact.revoked_at) return false;
    setMutating(true);
    setError(null);
    try {
      const result = await client.downloadArtifact(artifact.id);
      const objectUrl = URL.createObjectURL(result.blob);
      const anchor = document.createElement("a");
      anchor.href = objectUrl;
      anchor.download = safeDownloadName(artifact.safe_file_name);
      anchor.rel = "noopener";
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(objectUrl);
      setNotice(`已开始下载 ${safeDownloadName(artifact.safe_file_name)}。`);
      return true;
    } catch (caught) {
      setError(toWorkspaceError(caught));
      return false;
    } finally {
      setMutating(false);
    }
  }, [client]);

  const revokeExport = useCallback(async (exportJobId: string) => {
    if (!project) return null;
    const scope = `revoke-${exportJobId}`;
    setMutating(true);
    setError(null);
    try {
      const response = await client.revokeExport(exportJobId, keyFor(scope));
      clearKey(scope);
      setNotice("导出文件已逻辑撤回，下载已禁用；历史审计继续保留。");
      await loadWorkspace(project);
      return response.data;
    } catch (caught) {
      setError(toWorkspaceError(caught));
      return null;
    } finally {
      setMutating(false);
    }
  }, [clearKey, client, keyFor, loadWorkspace, project]);

  return {
    publishedAssets,
    exportJobs,
    artifacts,
    loading,
    mutating,
    error,
    notice,
    publishSelected,
    archiveAsset,
    createExport,
    downloadArtifact,
    revokeExport,
    refresh: () => (project ? loadWorkspace(project) : Promise.resolve()),
    clearError: () => setError(null),
  };
}
