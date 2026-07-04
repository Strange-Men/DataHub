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
        <div className="hero-content">
          <h1 className="hero-title">DataHub 数据治理与 RAG 知识中台</h1>
          <p className="hero-desc">
            将客服文本数据经过机器清洗、人工清洗和知识审核，沉淀为可供客服 Agent
            使用的高质量 RAG 知识库。
          </p>
          <div className="hero-buttons">
            <button
              type="button"
              className="btn-primary btn-lg"
              onClick={() => navigate("/p1-text-hub")}
            >
              开始体验
            </button>
            <button
              type="button"
              className="btn-secondary btn-lg"
              onClick={() => navigate("/p1-text-hub")}
            >
              上传客服数据
            </button>
            <button
              type="button"
              className="btn-outline btn-lg"
              onClick={() => {
                navigate("/p1-text-hub");
                setTimeout(() => {
                  const sampleBtn = document.querySelector("[data-sample-btn]") as HTMLButtonElement;
                  sampleBtn?.click();
                }, 300);
              }}
            >
              使用示例数据
            </button>
          </div>
        </div>
      </section>

      <section className="connection-bar">
        <div className="connection-info">
          <span className={`conn-indicator ${backendStatus.state}`} />
          <span className="conn-text">
            {backendStatus.state === "connected"
              ? "后端已连接"
              : backendStatus.state === "checking"
                ? "正在检测后端连接..."
                : "后端暂未连接，可能是 Render 免费实例冷启动。请稍等或点击重新检测。"}
          </span>
        </div>
        <button type="button" className="btn-small" onClick={onCheckBackend}>
          重新检测
        </button>
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
