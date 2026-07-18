import { useNavigate } from "react-router-dom";
import type { BackendStatus } from "../types";

export function HomePage({
  backendStatus,
  onCheckBackend,
}: {
  backendStatus: BackendStatus;
  onCheckBackend: () => void;
}) {
  const navigate = useNavigate();

  const capabilityCards = [
    {
      title: "P1 文本知识治理",
      badge: "P1",
      description: "导入、机器清洗、人工修订、知识审核、RAG 同步、Agent 验证与 Bad Case 回流。",
      status: "可使用",
      path: "/p1-text-hub",
      disabled: false,
    },
    {
      title: "P2 多模态知识治理",
      badge: "P2",
      description: "完成素材解析、内容审核、知识发布、索引构建、开放检索与归档。",
      status: "可使用",
      path: "/p2-material-center",
      disabled: false,
    },
    {
      title: "P3 数据资产复用",
      badge: "P3",
      description: "数据资产复用能力将在后续阶段规划，当前没有可操作入口。",
      status: "规划中",
      path: "/p3-asset-reuse",
      disabled: true,
    },
    {
      title: "P4 MCP + Agent 集群",
      badge: "P4",
      description: "MCP 与多 Agent 协作能力将在后续阶段规划。",
      status: "规划中",
      path: "/p4-mcp-agents",
      disabled: true,
    },
    {
      title: "检索与 Agent 验证",
      badge: "QA",
      description: "验证 P1、P2、联合检索和客服 Agent 的召回、引用与安全拒答效果。",
      status: "可使用",
      path: "/retrieval-validation",
      disabled: false,
    },
  ];

  return (
    <div className="home-page">
      <section className="hero-section">
        <div className="hero-copy">
          <span className="hero-eyebrow">P1/P2 GOVERNANCE WORKSPACE</span>
          <h1 className="hero-title">DataHub 数据治理与 RAG 知识中台</h1>
          <p className="hero-desc">以清晰任务流治理文本与多模态知识，并验证检索可见性、来源和安全拒答。</p>
        </div>
        <div className="hero-status-bar" aria-label="平台状态">
          <span><i className={`conn-indicator ${backendStatus.state}`} />{backendStatus.state === "connected" ? "服务正常" : backendStatus.state === "checking" ? "连接中" : "服务暂不可用"}</span>
          <span><strong>可使用</strong> P1 · P2 · 检索与 Agent 验证</span>
          <span><strong>规划中</strong> P3 · P4</span>
          <button type="button" className="btn-small" onClick={onCheckBackend}>重新检测</button>
        </div>
      </section>

      <section className="capability-grid">
        <h2 className="section-title">平台能力</h2>
        <div className="capability-cards">
          {capabilityCards.map((card) => (
            <article
              key={card.title}
              className={`capability-card ${card.disabled ? "disabled" : ""}`}
            >
              <span className="capability-mark" aria-hidden="true">{card.badge}</span>
              <h3>{card.title}</h3>
              <p>{card.description}</p>
              <div className="capability-footer">
                <span className={`capability-status ${card.disabled ? "inactive" : "active"}`}>
                  {card.status}
                </span>
                {!card.disabled && (
                  <button type="button" className="btn-primary btn-sm" onClick={() => navigate(card.path)}>
                    进入模块
                  </button>
                )}
              </div>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
