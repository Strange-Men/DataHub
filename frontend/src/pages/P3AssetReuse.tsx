import { useAuth } from "../auth/AuthContext";
import { ROLE_LABELS } from "../governance";

const WORKFLOW_STEPS = [
  { number: 1, title: "创建项目", description: "定义本次复用目标" },
  { number: 2, title: "选择来源", description: "只选择已治理知识" },
  { number: 3, title: "生成与修订", description: "形成可审核草稿" },
  { number: 4, title: "提交与审核", description: "由人工作出决定" },
  { number: 5, title: "发布与导出", description: "形成正式复用资产" },
] as const;

export function P3AssetReuse() {
  const { role, authMode } = useAuth();

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
        {WORKFLOW_STEPS.map((step, index) => (
          <div
            className={`p3-step ${index === 0 ? "current" : ""}`}
            aria-current={index === 0 ? "step" : undefined}
            key={step.number}
          >
            <span className="p3-step-number">{step.number}</span>
            <span>
              <strong>{step.title}</strong>
              <small>{step.description}</small>
            </span>
          </div>
        ))}
      </nav>

      <section className="p3-workspace-panel" aria-labelledby="p3-project-entry-title">
        <div className="p3-panel-heading">
          <div>
            <span className="p3-stage-label">第 1 阶段</span>
            <h2 id="p3-project-entry-title">先选择或创建一个复用项目</h2>
            <p>项目用于集中管理来源、草稿、审核记录以及最终导出。</p>
          </div>
          <span className="p3-status-chip neutral">尚未选择项目</span>
        </div>

        <div className="p3-entry-options">
          <article>
            <span className="p3-entry-icon" aria-hidden="true">01</span>
            <h3>选择已有项目</h3>
            <p>继续处理已经建立的复用任务，并查看当前进度。</p>
          </article>
          <article>
            <span className="p3-entry-icon" aria-hidden="true">＋</span>
            <h3>创建复用项目</h3>
            <p>填写项目名称和说明后，从选择治理来源开始。</p>
          </article>
        </div>

        <div className="p3-empty-state" role="status">
          <strong>工作台基础已就绪</strong>
          <p>项目选择和创建操作将在本流程下一步接入真实后端数据。</p>
        </div>
      </section>

      <details className="p3-technical-details">
        <summary>技术详情</summary>
        <dl>
          <div><dt>工作区路由</dt><dd>/p3</dd></div>
          <div><dt>认证模式</dt><dd>{authMode}</dd></div>
          <div><dt>当前阶段代码</dt><dd>project_setup</dd></div>
        </dl>
      </details>
    </div>
  );
}
