const STAGES = [
  { title: "素材上传与解析", detail: "上传 · 内容解析" },
  { title: "内容修订与审核", detail: "修订 · 人工审核" },
  { title: "知识快照与发布", detail: "知识快照 · 知识资产" },
  { title: "索引构建与开放检索", detail: "建立索引 · 生成向量 · 开放检索" },
  { title: "检索验证与归档", detail: "检索验证 · 归档 · 来源追踪" },
];

export function P2WorkflowHeader({
  currentStage,
  status,
  nextAction,
  onNext,
}: {
  currentStage: number;
  status: string;
  nextAction: string;
  onNext: () => void;
}) {
  return (
    <section className="p2-workflow-overview" aria-label="P2 五阶段治理流程">
      <div className="p2-workflow-summary">
        <div>
          <span>当前阶段</span>
          <strong>{currentStage}. {STAGES[currentStage - 1].title}</strong>
        </div>
        <div>
          <span>当前状态</span>
          <strong>{status}</strong>
        </div>
        <div className="p2-next-guidance">
          <span>下一步建议</span>
          <strong>{nextAction}</strong>
        </div>
        <button type="button" className="btn-primary" onClick={onNext}>{nextAction}</button>
      </div>
      <ol className="p2-stage-track">
        {STAGES.map((stage, index) => {
          const stageNumber = index + 1;
          const state = stageNumber < currentStage ? "done" : stageNumber === currentStage ? "current" : "upcoming";
          return (
            <li key={stage.title} className={state} aria-current={state === "current" ? "step" : undefined}>
              <span className="p2-stage-number">{state === "done" ? "✓" : stageNumber}</span>
              <span><strong>{stage.title}</strong><small>{stage.detail}</small></span>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
