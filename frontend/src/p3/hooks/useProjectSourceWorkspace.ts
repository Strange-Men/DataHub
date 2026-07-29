import { useCallback, useEffect, useState } from "react";
import { p3Client, type P3Client } from "../client";
import {
  toWorkspaceError,
  type P3WorkspaceError,
} from "../components/WorkspaceFeedback";
import type {
  P3Project,
  P3ProjectStatus,
  P3SourceEligibilityDecision,
  P3SourceEligibilityInput,
  P3SourceItem,
  P3SourceType,
} from "../types";

const PROJECT_PAGE_SIZE = 8;
const SOURCE_PAGE_SIZE = 12;

export type SourceFilters = {
  sourceType?: P3SourceType;
  onlyStale: boolean;
  includeRemoved: boolean;
};

export function useProjectSourceWorkspace(client: P3Client = p3Client) {
  const [projects, setProjects] = useState<P3Project[]>([]);
  const [projectTotal, setProjectTotal] = useState(0);
  const [projectOffset, setProjectOffset] = useState(0);
  const [selectedProject, setSelectedProject] = useState<P3Project | null>(null);
  const [sources, setSources] = useState<P3SourceItem[]>([]);
  const [sourceTotal, setSourceTotal] = useState(0);
  const [sourceOffset, setSourceOffset] = useState(0);
  const [sourceFilters, setSourceFilters] = useState<SourceFilters>({
    onlyStale: false,
    includeRemoved: false,
  });
  const [eligibility, setEligibility] = useState<P3SourceEligibilityDecision | null>(null);
  const [activationSummary, setActivationSummary] = useState({
    sourceCount: 0,
    staleCount: 0,
  });
  const [loadingProjects, setLoadingProjects] = useState(true);
  const [loadingSources, setLoadingSources] = useState(false);
  const [checkingEligibility, setCheckingEligibility] = useState(false);
  const [mutating, setMutating] = useState(false);
  const [error, setError] = useState<P3WorkspaceError | null>(null);
  const [notice, setNotice] = useState("");

  const loadProjects = useCallback(async (
    offset = 0,
    status?: P3ProjectStatus,
    signal?: AbortSignal,
  ) => {
    setLoadingProjects(true);
    setError(null);
    try {
      const response = await client.listProjects(
        { limit: PROJECT_PAGE_SIZE, offset, status },
        { signal },
      );
      setProjects(response.data.items);
      setProjectTotal(response.data.total);
      setProjectOffset(response.data.offset);
    } catch (caught) {
      if (caught instanceof DOMException && caught.name === "AbortError") return;
      setError(toWorkspaceError(caught));
    } finally {
      setLoadingProjects(false);
    }
  }, [client]);

  const loadSources = useCallback(async (
    project: P3Project,
    offset = 0,
    filters = sourceFilters,
    signal?: AbortSignal,
  ) => {
    setLoadingSources(true);
    setError(null);
    try {
      const response = await client.listSources(
        project.id,
        {
          limit: SOURCE_PAGE_SIZE,
          offset,
          include_removed: filters.includeRemoved,
          source_type: filters.sourceType,
          source_stale: filters.onlyStale ? true : undefined,
        },
        { signal },
      );
      setSources(response.data.items);
      setSourceTotal(response.data.total);
      setSourceOffset(response.data.offset);
    } catch (caught) {
      if (caught instanceof DOMException && caught.name === "AbortError") return;
      setError(toWorkspaceError(caught));
    } finally {
      setLoadingSources(false);
    }
  }, [client, sourceFilters]);

  const loadActivationSummary = useCallback(async (project: P3Project) => {
    try {
      const [allSources, staleSources] = await Promise.all([
        client.listSources(project.id, {
          limit: 1,
          offset: 0,
          include_removed: false,
        }),
        client.listSources(project.id, {
          limit: 1,
          offset: 0,
          include_removed: false,
          source_stale: true,
        }),
      ]);
      setActivationSummary({
        sourceCount: allSources.data.total,
        staleCount: staleSources.data.total,
      });
    } catch (caught) {
      setError(toWorkspaceError(caught));
    }
  }, [client]);

  useEffect(() => {
    const controller = new AbortController();
    void loadProjects(0, undefined, controller.signal);
    return () => controller.abort();
  }, [loadProjects]);

  const selectProject = useCallback(async (project: P3Project) => {
    setSelectedProject(project);
    setEligibility(null);
    setNotice("");
    setSourceOffset(0);
    await Promise.all([
      loadSources(project, 0, sourceFilters),
      loadActivationSummary(project),
    ]);
  }, [loadActivationSummary, loadSources, sourceFilters]);

  const createProject = useCallback(async (input: {
    name: string;
    description?: string | null;
    idempotencyKey: string;
  }) => {
    setMutating(true);
    setError(null);
    try {
      const response = await client.createProject({
        name: input.name,
        description: input.description || null,
        idempotency_key: input.idempotencyKey,
      });
      const project = response.data;
      setSelectedProject(project);
      setSources([]);
      setSourceTotal(0);
      setSourceOffset(0);
      setActivationSummary({ sourceCount: 0, staleCount: 0 });
      setNotice("复用项目已创建，可以开始检查并添加治理来源。");
      await loadProjects(0);
      return project;
    } catch (caught) {
      setError(toWorkspaceError(caught));
      return null;
    } finally {
      setMutating(false);
    }
  }, [client, loadProjects]);

  const updateProjectMetadata = useCallback(async (input: {
    name?: string;
    description?: string | null;
  }) => {
    if (!selectedProject) return null;
    setMutating(true);
    setError(null);
    try {
      const response = await client.updateProject(selectedProject.id, input);
      setSelectedProject(response.data);
      setNotice("项目信息已更新。");
      await loadProjects(projectOffset);
      return response.data;
    } catch (caught) {
      setError(toWorkspaceError(caught));
      return null;
    } finally {
      setMutating(false);
    }
  }, [client, loadProjects, projectOffset, selectedProject]);

  const checkEligibility = useCallback(async (input: P3SourceEligibilityInput) => {
    setCheckingEligibility(true);
    setEligibility(null);
    setError(null);
    try {
      const response = await client.checkSourceEligibility(input);
      setEligibility(response.data.decision);
      return response.data.decision;
    } catch (caught) {
      setError(toWorkspaceError(caught));
      return null;
    } finally {
      setCheckingEligibility(false);
    }
  }, [client]);

  const addCheckedSource = useCallback(async () => {
    if (!selectedProject || !eligibility?.eligible) return null;
    setMutating(true);
    setError(null);
    try {
      const response = await client.addSource(selectedProject.id, {
        source_type: eligibility.source_type as P3SourceType,
        source_id: eligibility.source_id,
        source_version: eligibility.source_version ?? undefined,
        expected_fingerprint: eligibility.content_fingerprint ?? undefined,
      });
      setNotice("治理来源已加入项目，审核证据由后端资格内核固化。");
      setEligibility(null);
      await Promise.all([
        loadSources(selectedProject, 0, sourceFilters),
        loadActivationSummary(selectedProject),
      ]);
      return response.data;
    } catch (caught) {
      setError(toWorkspaceError(caught));
      return null;
    } finally {
      setMutating(false);
    }
  }, [client, eligibility, loadActivationSummary, loadSources, selectedProject, sourceFilters]);

  const removeSource = useCallback(async (sourceItemId: string) => {
    if (!selectedProject) return;
    setMutating(true);
    setError(null);
    try {
      await client.removeSource(selectedProject.id, sourceItemId);
      setNotice("来源已从当前选择中逻辑移除，历史记录仍会保留。");
      await Promise.all([
        loadSources(selectedProject, 0, sourceFilters),
        loadActivationSummary(selectedProject),
      ]);
    } catch (caught) {
      setError(toWorkspaceError(caught));
    } finally {
      setMutating(false);
    }
  }, [client, loadActivationSummary, loadSources, selectedProject, sourceFilters]);

  const revalidateSource = useCallback(async (sourceItemId: string) => {
    if (!selectedProject) return;
    setMutating(true);
    setError(null);
    try {
      const response = await client.revalidateSource(selectedProject.id, sourceItemId);
      setNotice(
        response.data.source_stale
          ? "来源已发生变化，当前项目不能激活或用于新的正式流转。"
          : "来源重新验证通过，审核证据仍然有效。",
      );
      await Promise.all([
        loadSources(selectedProject, sourceOffset, sourceFilters),
        loadActivationSummary(selectedProject),
      ]);
    } catch (caught) {
      setError(toWorkspaceError(caught));
    } finally {
      setMutating(false);
    }
  }, [client, loadActivationSummary, loadSources, selectedProject, sourceFilters, sourceOffset]);

  const revalidateAllSources = useCallback(async () => {
    if (!selectedProject) return;
    setMutating(true);
    setError(null);
    try {
      const response = await client.revalidateProjectSources(selectedProject.id, 100);
      const staleCount = response.data.results.filter((item) => item.source_stale).length;
      setNotice(
        staleCount
          ? `重新验证完成，发现 ${staleCount} 个已变化来源。`
          : `重新验证完成，${response.data.total} 个来源仍然有效。`,
      );
      await Promise.all([
        loadSources(selectedProject, sourceOffset, sourceFilters),
        loadActivationSummary(selectedProject),
      ]);
    } catch (caught) {
      setError(toWorkspaceError(caught));
    } finally {
      setMutating(false);
    }
  }, [client, loadActivationSummary, loadSources, selectedProject, sourceFilters, sourceOffset]);

  const activateProject = useCallback(async () => {
    if (!selectedProject) return null;
    setMutating(true);
    setError(null);
    try {
      const response = await client.activateProject(selectedProject.id);
      setSelectedProject(response.data);
      setNotice("项目已激活，来源选择已冻结，可以进入草稿生成阶段。");
      await loadProjects(projectOffset);
      await loadSources(response.data, 0, sourceFilters);
      return response.data;
    } catch (caught) {
      setError(toWorkspaceError(caught));
      return null;
    } finally {
      setMutating(false);
    }
  }, [client, loadProjects, loadSources, projectOffset, selectedProject, sourceFilters]);

  const archiveProject = useCallback(async () => {
    if (!selectedProject) return null;
    setMutating(true);
    setError(null);
    try {
      const response = await client.archiveProject(selectedProject.id);
      setSelectedProject(response.data);
      setNotice("项目已归档，历史记录继续保留并以只读方式展示。");
      await loadProjects(projectOffset);
      return response.data;
    } catch (caught) {
      setError(toWorkspaceError(caught));
      return null;
    } finally {
      setMutating(false);
    }
  }, [client, loadProjects, projectOffset, selectedProject]);

  const changeSourceFilters = useCallback(async (filters: SourceFilters) => {
    setSourceFilters(filters);
    setSourceOffset(0);
    if (selectedProject) await loadSources(selectedProject, 0, filters);
  }, [loadSources, selectedProject]);

  return {
    projects,
    projectTotal,
    projectOffset,
    projectPageSize: PROJECT_PAGE_SIZE,
    selectedProject,
    sources,
    sourceTotal,
    sourceOffset,
    sourcePageSize: SOURCE_PAGE_SIZE,
    sourceFilters,
    eligibility,
    activationSummary,
    loadingProjects,
    loadingSources,
    checkingEligibility,
    mutating,
    error,
    notice,
    loadProjects,
    loadSources,
    selectProject,
    createProject,
    updateProjectMetadata,
    checkEligibility,
    addCheckedSource,
    removeSource,
    revalidateSource,
    revalidateAllSources,
    activateProject,
    archiveProject,
    changeSourceFilters,
    clearError: () => setError(null),
    clearNotice: () => setNotice(""),
  };
}
