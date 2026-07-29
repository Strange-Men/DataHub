import { useMemo } from "react";
import { useAuth } from "../auth/AuthContext";
import { ROLE_LABELS } from "../governance";
import { ProjectActivationPanel } from "../p3/components/ProjectActivationPanel";
import { ProjectPicker } from "../p3/components/ProjectPicker";
import { AssetGenerationPanel } from "../p3/components/AssetGenerationPanel";
import { AssetVersionList } from "../p3/components/AssetVersionList";
import { ReviewWorkspace } from "../p3/components/ReviewWorkspace";
import { SourceEligibilityForm } from "../p3/components/SourceEligibilityForm";
import { SourceList } from "../p3/components/SourceList";
import { StructuredAssetViewer } from "../p3/components/StructuredAssetViewer";
import { StructuredRevisionEditor } from "../p3/components/StructuredRevisionEditor";
import { WorkspaceError, WorkspaceNotice } from "../p3/components/WorkspaceFeedback";
import { useAssetReviewWorkspace } from "../p3/hooks/useAssetReviewWorkspace";
import { useProjectSourceWorkspace } from "../p3/hooks/useProjectSourceWorkspace";
import { P3_PROJECT_STATUS_LABELS } from "../p3/presentation";

const WORKFLOW_STEPS = [
  { number: 1, title: "创建项目", description: "定义本次复用目标" },
  { number: 2, title: "选择来源", description: "只选择已治理知识" },
  { number: 3, title: "生成与修订", description: "形成可审核草稿" },
  { number: 4, title: "提交与审核", description: "由人工作出决定" },
  { number: 5, title: "发布与导出", description: "形成正式复用资产" },
] as const;

export function P3AssetReuse() {
  const { role, authMode } = useAuth();
  const workspace = useProjectSourceWorkspace();
  const assetWorkspace = useAssetReviewWorkspace(workspace.selectedProject, role);
  const currentStep = useMemo(() => {
    if (!workspace.selectedProject) return 1;
    if (workspace.selectedProject.status === "draft") return 2;
    if (workspace.selectedProject.status === "active") {
      if (!assetWorkspace.selectedAsset) return 3;
      if (["generated", "needs_revision"].includes(assetWorkspace.selectedAsset.status)) return 3;
      return 4;
    }
    return 5;
  }, [assetWorkspace.selectedAsset, workspace.selectedProject]);

  return (
    <div className="p3-workspace">
      <header className="p3-workspace-hero">
        <div>
          <span className="p3-eyebrow">P3 · GOVERNED REUSE</span>
          <h1>数据资产复用</h1>
          <p>
            将已经审核的知识整理为培训资料、SOP、客服话术、问答题库或数据集，
            每一步都保留来源和人工审核记录。
          </p>
        </div>
        <div className="p3-role-pill" aria-label="当前访问角色">
          <span>当前角色</span>
          <strong>{role ? ROLE_LABELS[role] : "正在确认"}</strong>
        </div>
      </header>

      <nav className="p3-stepper" aria-label="数据资产复用五阶段">
        {WORKFLOW_STEPS.map((step) => {
          const isCurrent = step.number === currentStep;
          const isComplete = step.number < currentStep;
          return (
            <div
              className={`p3-step ${isCurrent ? "current" : ""} ${isComplete ? "complete" : ""}`}
              aria-current={isCurrent ? "step" : undefined}
              key={step.number}
            >
              <span className="p3-step-number">{isComplete ? "✓" : step.number}</span>
              <span>
                <strong>{step.title}</strong>
                <small>{step.description}</small>
              </span>
            </div>
          );
        })}
      </nav>

      <WorkspaceError error={workspace.error} onDismiss={workspace.clearError} />
      <WorkspaceNotice message={workspace.notice} />
      <WorkspaceError error={assetWorkspace.error} onDismiss={assetWorkspace.clearError} />
      <WorkspaceNotice message={assetWorkspace.notice} />

      <ProjectPicker
        role={role}
        projects={workspace.projects}
        total={workspace.projectTotal}
        offset={workspace.projectOffset}
        pageSize={workspace.projectPageSize}
        selectedProject={workspace.selectedProject}
        loading={workspace.loadingProjects}
        mutating={workspace.mutating}
        onPage={(offset) => void workspace.loadProjects(offset)}
        onSelect={(project) => void workspace.selectProject(project)}
        onCreate={workspace.createProject}
      />

      {workspace.selectedProject ? (
        <div className="p3-project-workspace">
          <section className="p3-selected-project" aria-labelledby="p3-selected-project-title">
            <div>
              <span className="p3-stage-label">当前项目</span>
              <h2 id="p3-selected-project-title">{workspace.selectedProject.name}</h2>
              <p>{workspace.selectedProject.description || "未填写项目说明"}</p>
            </div>
            <span className={`p3-status-chip ${workspace.selectedProject.status}`}>
              {P3_PROJECT_STATUS_LABELS[workspace.selectedProject.status]}
            </span>
          </section>

          <SourceEligibilityForm
            role={role}
            project={workspace.selectedProject}
            decision={workspace.eligibility}
            checking={workspace.checkingEligibility}
            mutating={workspace.mutating}
            onCheck={workspace.checkEligibility}
            onAdd={workspace.addCheckedSource}
          />

          <SourceList
            role={role}
            project={workspace.selectedProject}
            sources={workspace.sources}
            total={workspace.sourceTotal}
            offset={workspace.sourceOffset}
            pageSize={workspace.sourcePageSize}
            filters={workspace.sourceFilters}
            loading={workspace.loadingSources}
            mutating={workspace.mutating}
            onFilters={(filters) => void workspace.changeSourceFilters(filters)}
            onPage={(offset) => {
              if (workspace.selectedProject) {
                void workspace.loadSources(
                  workspace.selectedProject,
                  offset,
                  workspace.sourceFilters,
                );
              }
            }}
            onRevalidate={(id) => void workspace.revalidateSource(id)}
            onRevalidateAll={() => void workspace.revalidateAllSources()}
            onRemove={(id) => void workspace.removeSource(id)}
          />

          <ProjectActivationPanel
            role={role}
            project={workspace.selectedProject}
            sourceCount={workspace.activationSummary.sourceCount}
            staleCount={workspace.activationSummary.staleCount}
            mutating={workspace.mutating}
            onActivate={() => void workspace.activateProject()}
            onArchive={() => void workspace.archiveProject()}
          />

          {workspace.selectedProject.status !== "draft" && (
            <>
              {workspace.selectedProject.status === "active" && (
                <AssetGenerationPanel
                  role={role}
                  project={workspace.selectedProject}
                  busy={assetWorkspace.mutatingAsset}
                  onGenerate={assetWorkspace.generateDeterministic}
                  onGenerateLlm={assetWorkspace.generateLlm}
                />
              )}

              <AssetVersionList
                assets={assetWorkspace.assets}
                total={assetWorkspace.assetTotal}
                offset={assetWorkspace.assetOffset}
                pageSize={assetWorkspace.assetPageSize}
                filters={assetWorkspace.assetFilters}
                selectedAsset={assetWorkspace.selectedAsset}
                loading={assetWorkspace.loadingAssets}
                onFilters={(filters) => void assetWorkspace.changeFilters(filters)}
                onPage={(offset) => {
                  if (workspace.selectedProject) {
                    void assetWorkspace.loadAssets(
                      workspace.selectedProject,
                      offset,
                      assetWorkspace.assetFilters,
                    );
                  }
                }}
                onSelect={(id) => void assetWorkspace.loadSelectedAsset(id)}
              />

              {assetWorkspace.selectedAsset && (
                <>
                  <StructuredAssetViewer
                    asset={assetWorkspace.selectedAsset}
                    sources={assetWorkspace.assetSources}
                    loading={assetWorkspace.loadingDetail}
                  />
                  {workspace.selectedProject.status === "active" && (
                    <>
                      <StructuredRevisionEditor
                        role={role}
                        asset={assetWorkspace.selectedAsset}
                        sources={assetWorkspace.assetSources}
                        busy={assetWorkspace.mutatingAsset}
                        onSave={assetWorkspace.createRevision}
                      />
                      <ReviewWorkspace
                        role={role}
                        asset={assetWorkspace.selectedAsset}
                        sources={assetWorkspace.assetSources}
                        review={assetWorkspace.review}
                        history={assetWorkspace.reviewHistory}
                        busy={assetWorkspace.mutatingAsset}
                        onSubmit={assetWorkspace.submitReview}
                        onDecide={assetWorkspace.decideReview}
                      />
                    </>
                  )}
                </>
              )}
            </>
          )}
        </div>
      ) : (
        <section className="p3-workspace-panel">
          <div className="p3-empty-state" role="status">
            <strong>选择或创建一个项目后开始</strong>
            <p>工作台不会一次性加载全部历史项目，也不会展示未经审核的原始知识。</p>
          </div>
        </section>
      )}

      <details className="p3-technical-details">
        <summary>技术详情</summary>
        <dl>
          <div><dt>工作区路由</dt><dd>/p3</dd></div>
          <div><dt>认证模式</dt><dd>{authMode}</dd></div>
          <div><dt>当前项目 ID</dt><dd>{workspace.selectedProject?.id ?? "未选择"}</dd></div>
        </dl>
      </details>
    </div>
  );
}
