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
      icon: "💬",
      description: "导入、机器清洗、人工修订、知识审核、RAG 同步、Agent 验证与 Bad Case 回流。",
      status: "可操作",
      path: "/p1-text-hub",
      disabled: false,
    },
    {
      title: "P2 多模态知识治理",
      icon: "🎨",
      description: "上传、Extraction、Review、Snapshot、Knowledge Asset、Index、Embed、Serve、Retrieval 与 Archive。",
      status: "可操作",
      path: "/p2-material-center",
      disabled: false,
    },
    {
      title: "检索验证",
      icon: "🔎",
      description: "验证 P1、P2、Unified Retrieval 和 CustomerOpsAgent 的真实结果与来源链。",
      status: "可操作",
      path: "/retrieval-validation",
      disabled: false,
    },
    {
      title: "P3 数据资产复用",
      icon: "📦",
      description: "尚未开放：当前阶段不提供培训、SOP 或微调数据集生成。",
      status: "尚未开放",
      path: "/p3-asset-reuse",
      disabled: true,
    },
    {
      title: "P4 MCP + Agent 集群",
      icon: "🤖",
      description: "尚未开放：当前仅提供 CustomerOpsAgent 的已发布检索接口。",
      status: "尚未开放",
      path: "/p4-mcp-agents",
      disabled: true,
    },
  ];

  return (
    <div className="home-page">
      <section className="hero-section">
        <h1 className="hero-title">DataHub 数据治理与 RAG 知识中台</h1>
        <p className="hero-desc">
          以任务流完成 P1 文本知识与 P2 多模态知识治理，并用真实检索接口验证可见性和来源。
        </p>
        <div className="hero-status">
          <div className="hero-status-row">
            <span className="hero-status-label">当前可操作</span>
            <span className="hero-status-value hero-status-active">P1 文本治理 / P2 多模态治理 / 检索验证</span>
          </div>
          <div className="hero-status-row">
            <span className="hero-status-label">尚未开放</span>
            <span className="hero-status-value">P3 数据资产复用 / P4 MCP + Agent 集群（当前阶段无真实接口）</span>
          </div>
          <div className="hero-status-row">
            <span className="hero-status-label">后端服务</span>
            <span className="hero-status-value">
              <span className={`conn-indicator ${backendStatus.state}`} />
              {backendStatus.state === "connected"
                ? "服务正常"
                : backendStatus.state === "checking"
                  ? "连接中"
                  : "服务暂不可用，可能正在冷启动"}
            </span>
            <button type="button" className="btn-small" onClick={onCheckBackend}>
              重新检测
            </button>
          </div>
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
              <span className="capability-icon">{card.icon}</span>
              <h3>{card.title}</h3>
              <p>{card.description}</p>
              <div className="capability-footer">
                <span className={`capability-status ${card.disabled ? "inactive" : "active"}`}>
                  {card.status}
                </span>
                <button
                  type="button"
                  className={card.disabled ? "btn-disabled" : "btn-primary btn-sm"}
                  disabled={card.disabled}
                  onClick={() => !card.disabled && navigate(card.path)}
                >
                  {card.disabled ? "尚未开放" : "进入任务流"}
                </button>
                {card.disabled && <small className="disabled-reason">当前阶段没有可调用的真实后端能力。</small>}
              </div>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
