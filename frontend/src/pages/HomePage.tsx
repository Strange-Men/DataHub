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
      title: "客服文本中台",
      icon: "💬",
      description: "导入客服聊天数据，经过机器清洗、人工审核，沉淀为高质量 RAG 知识库。",
      status: "已接入",
      path: "/p1-text-hub",
      disabled: false,
    },
    {
      title: "AI 素材中心",
      icon: "🎨",
      description: "图片、视频、海报素材治理，OCR、Caption、标签和 SKU 绑定。",
      status: "未接入",
      path: "/p2-material-center",
      disabled: true,
    },
    {
      title: "数据资产复用",
      icon: "📦",
      description: "将已审核知识复用为销售培训、SOP、FAQ 手册和微调数据集。",
      status: "未接入",
      path: "/p3-asset-reuse",
      disabled: true,
    },
    {
      title: "MCP + Agent 集群",
      icon: "🤖",
      description: "封装统一工具层，供 CustomerOpsAgent、SalesAgent 等 Agent 调用。",
      status: "未接入",
      path: "/p4-mcp-agents",
      disabled: true,
    },
  ];

  return (
    <div className="home-page">
      <section className="hero-section">
        <h1 className="hero-title">DataHub 数据治理与 RAG 知识中台</h1>
        <p className="hero-desc">
          将客服文本数据经过机器清洗、人工清洗和知识审核，沉淀为可供客服 Agent
          使用的高质量 RAG 知识库。
        </p>
        <div className="hero-status">
          <div className="hero-status-row">
            <span className="hero-status-label">当前已接入</span>
            <span className="hero-status-value hero-status-active">客服文本中台</span>
          </div>
          <div className="hero-status-row">
            <span className="hero-status-label">后续预留</span>
            <span className="hero-status-value">AI 素材中心 / 数据资产复用 / MCP + Agent 集群</span>
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
                  {card.disabled ? "暂未接入" : "进入工作台"}
                </button>
              </div>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
