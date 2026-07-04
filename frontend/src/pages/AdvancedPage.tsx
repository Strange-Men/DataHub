import type { BackendStatus } from "../types";

export function AdvancedPage({
  backendStatus,
  onCheckBackend,
}: {
  backendStatus: BackendStatus;
  onCheckBackend: () => void;
}) {
  return (
    <div className="advanced-page">
      <div className="page-hero">
        <h1>高级信息</h1>
        <p>开发者信息和技术状态，普通用户无需关注此页面。</p>
      </div>

      <section className="info-section">
        <h2>后端连接</h2>
        <div className="info-grid">
          <div className="info-card">
            <strong>健康状态</strong>
            <span className={`conn-indicator ${backendStatus.state}`} />
            <span>
              {backendStatus.state === "connected"
                ? "已连接"
                : backendStatus.state === "checking"
                  ? "检测中..."
                  : "未连接"}
            </span>
            {backendStatus.service ? <span>服务：{backendStatus.service}</span> : null}
            {backendStatus.phase ? <span>阶段：{backendStatus.phase}</span> : null}
            <button type="button" className="btn-secondary btn-sm" onClick={onCheckBackend}>
              重新检测
            </button>
          </div>
          <div className="info-card">
            <strong>API Base URL</strong>
            <code>https://datahub-jr8x.onrender.com</code>
            <span>本地开发：http://127.0.0.1:8000</span>
          </div>
        </div>
      </section>

      <section className="info-section">
        <h2>当前技术边界</h2>
        <div className="info-grid">
          <div className="info-card">
            <strong>local JSON storage</strong>
            <p>当前所有数据存储在 backend/storage/ 目录的 JSON 文件中。不使用数据库，不持久化到云端。每次部署或重启后，storage 目录重置。</p>
          </div>
          <div className="info-card">
            <strong>mock retrieval</strong>
            <p>当前检索基于关键词匹配（token overlap），不使用向量检索。没有真实的语义搜索能力。检索方法标记为 local_json_mock_retrieval。</p>
          </div>
          <div className="info-card">
            <strong>no vector DB / no embedding</strong>
            <p>当前不接入向量数据库（如 Pinecone、Weaviate、Milvus），不调用 embedding 模型。所有检索通过规则匹配完成。</p>
          </div>
          <div className="info-card">
            <strong>no real LLM / no DB / no MCP</strong>
            <p>当前不使用真实的大语言模型。知识抽取、质量评估均为规则引擎。不使用数据库、ORM。MCP 协议未实现。</p>
          </div>
        </div>
      </section>

      <section className="info-section">
        <h2>source trace 说明</h2>
        <p>每条知识候选都包含完整的来源追溯字段，确保数据治理可审计：</p>
        <ul>
          <li><strong>source_batch_id</strong>：原始导入批次 ID</li>
          <li><strong>source_conversation_id</strong>：原始会话 ID</li>
          <li><strong>source_message_ids</strong>：原始消息 ID 列表</li>
          <li><strong>source_bad_case_id</strong>：关联的 Bad Case ID</li>
          <li><strong>source_retrieval_id</strong>：关联的检索记录 ID</li>
          <li><strong>source_legacy_id</strong>：旧 RAG 系统迁移 ID</li>
          <li><strong>source_import_id</strong>：批量导入 ID</li>
        </ul>
      </section>

      <section className="info-section">
        <h2>调试信息</h2>
        <div className="info-card">
          <strong>前端</strong>
          <ul>
            <li>Framework：React 18 + Vite + TypeScript</li>
            <li>路由：React Router v6</li>
            <li>部署：Vercel（https://data-hub-flame.vercel.app/）</li>
            <li>API 连接：通过 VITE_API_BASE_URL 环境变量配置</li>
          </ul>
        </div>
        <div className="info-card">
          <strong>后端</strong>
          <ul>
            <li>Framework：FastAPI（Python）</li>
            <li>部署：Render（https://datahub-jr8x.onrender.com）</li>
            <li>健康检查：GET /api/health</li>
            <li>CORS：允许 localhost:5173 和 Vercel 域名</li>
            <li>存储：本地 JSON 文件（backend/storage/）</li>
          </ul>
        </div>
      </section>
    </div>
  );
}
