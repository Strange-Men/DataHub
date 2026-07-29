import { useState } from "react";
import type { AuthRole } from "../../api";
import { can, permissionHint } from "../../governance";
import { P3_PROJECT_STATUS_LABELS } from "../presentation";
import type { P3Project } from "../types";
import { ConfirmDialog } from "./ConfirmDialog";

export function ProjectActivationPanel({
  role,
  project,
  sourceCount,
  staleCount,
  mutating,
  onActivate,
  onArchive,
}: {
  role: AuthRole | null;
  project: P3Project;
  sourceCount: number;
  staleCount: number;
  mutating: boolean;
  onActivate: () => void;
  onArchive: () => void;
}) {
  const [confirmAction, setConfirmAction] = useState<"activate" | "archive" | null>(null);
  const canActivate = can(role, "p3.project.activate");
  const canArchive = can(role, "p3.project.archive");
  const activationReady = sourceCount > 0 && staleCount === 0;

  return (
    <section className="p3-activation-panel" aria-labelledby="p3-activation-title">
      <div className="p3-section-heading">
        <div>
          <h2 id="p3-activation-title">项目流转</h2>
          <p>激活前会由后端再次验证全部来源；前端检查只用于提前提示。</p>
        </div>
        <span className={`p3-status-chip ${project.status}`}>
          {P3_PROJECT_STATUS_LABELS[project.status]}
        </span>
      </div>

      {project.status === "draft" && (
        <>
          <ul className="p3-activation-checks">
            <li className={sourceCount > 0 ? "passed" : "blocked"}>
              <span aria-hidden="true">{sourceCount > 0 ? "✓" : "!"}</span>
              至少选择一个未移除来源
              <small>{sourceCount} 个当前来源</small>
            </li>
            <li className={staleCount === 0 ? "passed" : "blocked"}>
              <span aria-hidden="true">{staleCount === 0 ? "✓" : "!"}</span>
              没有已变化来源
              <small>{staleCount ? `${staleCount} 个来源需要处理` : "当前未发现异常"}</small>
            </li>
            <li className="passed">
              <span aria-hidden="true">✓</span>
              激活时重新验证审核证据
              <small>后端资格内核是最终判断依据</small>
            </li>
          </ul>
          <div className="p3-primary-action-row">
            <div>
              <strong>{activationReady ? "项目可以激活" : "尚未满足激活条件"}</strong>
              <p>激活后来源选择会冻结，随后才能生成正式草稿。</p>
            </div>
            <button
              type="button"
              className="btn-primary"
              disabled={!activationReady || !canActivate || mutating}
              title={permissionHint(role, "p3.project.activate")}
              onClick={() => setConfirmAction("activate")}
            >
              激活项目
            </button>
          </div>
        </>
      )}

      {project.status === "active" && (
        <div className="p3-feedback success" role="status">
          <strong>项目已激活，来源选择已冻结。</strong>
          <span>现在可以进入“生成与修订”阶段。</span>
        </div>
      )}

      {project.status === "archived" && (
        <div className="p3-feedback neutral" role="status">
          <strong>项目已归档。</strong>
          <span>历史来源、草稿、审核和导出记录继续保留，只读展示。</span>
        </div>
      )}

      {project.status !== "archived" && canArchive && (
        <div className="p3-secondary-danger-zone">
          <div>
            <strong>结束这个项目</strong>
            <p>归档后不能重新激活，历史记录仍会保留。</p>
          </div>
          <button
            type="button"
            className="btn-small danger-text"
            disabled={mutating}
            onClick={() => setConfirmAction("archive")}
          >
            归档项目
          </button>
        </div>
      )}

      <ConfirmDialog
        open={confirmAction === "activate"}
        title="激活这个复用项目？"
        description="系统会再次验证全部来源。激活成功后来源选择会冻结，但项目内容仍可继续进入草稿与审核流程。"
        confirmLabel="确认激活"
        busy={mutating}
        onCancel={() => setConfirmAction(null)}
        onConfirm={() => {
          onActivate();
          setConfirmAction(null);
        }}
      />
      <ConfirmDialog
        open={confirmAction === "archive"}
        title="归档这个复用项目？"
        description="归档后不能恢复或重新激活；来源、草稿、审核和导出历史不会被删除。"
        confirmLabel="确认归档"
        danger
        busy={mutating}
        onCancel={() => setConfirmAction(null)}
        onConfirm={() => {
          onArchive();
          setConfirmAction(null);
        }}
      />
    </section>
  );
}
