export function P4McpAgents() {
  const toolList = [
    { name: "search_knowledge", description: "检索 RAG 知识库，返回最匹配的问答对。" },
    { name: "get_order_info", description: "查询订单状态、物流信息和历史记录。" },
    { name: "check_refund_policy", description: "查询退款政策和退货流程。" },
    { name: "submit_bad_case", description: "提交 Bad Case，触发知识改进流程。" },
    { name: "search_material", description: "检索多媒体素材库（图片、视频、海报）。" },
    { name: "get_training_material", description: "获取销售培训资料和话术手册。" },
  ];

  const agents = [
    {
      name: "CustomerOpsAgent",
      description: "客服运营 Agent，负责自动回答客户问题、转人工判断和 Bad Case 回流。",
      tools: ["search_knowledge", "get_order_info", "submit_bad_case"],
    },
    {
      name: "SalesAgent",
      description: "销售辅助 Agent，提供产品知识、话术建议和竞品对比。",
      tools: ["search_knowledge", "get_training_material"],
    },
    {
      name: "OpsAgent",
      description: "运营 Agent，负责数据导入监控、质量报告和流程调度。",
      tools: ["search_knowledge", "check_refund_policy"],
    },
    {
      name: "MaterialAgent",
      description: "素材管理 Agent，处理多媒体素材的 OCR、Caption 和标签。",
      tools: ["search_material"],
    },
  ];

  return (
    <div className="p4-page">
      <div className="page-hero">
        <h1>MCP + Agent 集群</h1>
        <p>
          将 DataHub 封装为 MCP 工具层，供 CustomerOpsAgent、SalesAgent、OpsAgent、MaterialAgent
          统一调用。
        </p>
      </div>

      <div className="roadmap-banner">
        <span className="roadmap-icon">🚧</span>
        <div>
          <strong>P4 阶段功能</strong>
          <p>本页面展示 MCP + Agent 集群的未来产品架构，所有功能将在 P4 阶段接入真实能力。</p>
        </div>
      </div>

      <section className="mcp-section">
        <h2>MCP 工具列表</h2>
        <p className="section-desc">DataHub 对外暴露的 MCP 工具接口，供 Agent 集群统一调用。</p>
        <div className="tool-grid">
          {toolList.map((tool) => (
            <article className="tool-card" key={tool.name}>
              <h3>{tool.name}</h3>
              <p>{tool.description}</p>
              <button type="button" className="btn-disabled btn-sm" disabled>
                未接入
              </button>
            </article>
          ))}
        </div>
      </section>

      <section className="agents-section">
        <h2>Agent 集群</h2>
        <p className="section-desc">面向不同业务场景的专业 Agent，通过 MCP 工具层统一访问 DataHub 能力。</p>
        <div className="agent-grid">
          {agents.map((agent) => (
            <article className="agent-card" key={agent.name}>
              <div className="agent-header">
                <span className="agent-icon">🤖</span>
                <h3>{agent.name}</h3>
              </div>
              <p>{agent.description}</p>
              <div className="agent-tools">
                <strong>可用工具：</strong>
                <div className="tool-tags">
                  {agent.tools.map((t) => (
                    <span className="tool-tag" key={t}>{t}</span>
                  ))}
                </div>
              </div>
              <button type="button" className="btn-disabled btn-sm" disabled>
                P4 后接入
              </button>
            </article>
          ))}
        </div>
      </section>

      <section className="info-panel">
        <h3>调用日志 & 工具权限</h3>
        <div className="dual-cards">
          <article className="info-card">
            <h3>调用日志</h3>
            <p>追踪所有 Agent 的 MCP 工具调用记录，包括调用时间、参数、返回结果和耗时。</p>
            <button type="button" className="btn-disabled btn-sm" disabled>
              P4 后接入
            </button>
          </article>
          <article className="info-card">
            <h3>工具权限</h3>
            <p>管理各 Agent 的 MCP 工具访问权限，控制工具调用频率和参数范围。</p>
            <button type="button" className="btn-disabled btn-sm" disabled>
              P4 后接入
            </button>
          </article>
        </div>
      </section>

      <section className="info-panel">
        <h3>当前状态</h3>
        <ul>
          <li>MCP 工具层和 Agent 集群架构已设计完毕。</li>
          <li>所有按钮当前为禁用状态，不连接后端，不做假调用。</li>
          <li>MCP 协议实现、Agent 集成将在 P4 阶段进行。</li>
          <li>当前不修改 CustomerOpsAgent 仓库。</li>
        </ul>
      </section>
    </div>
  );
}
