export function P4McpAgents() {
  return (
    <div className="p4-page">
      <div className="page-hero">
        <h1>P4 MCP + Agent 集群</h1>
        <p>尚未开放。当前可用的客服 Agent 已放入“检索与 Agent 验证”，仍保持默认 P1-only 和联合检索显式启用。</p>
      </div>
      <section className="material-panel unavailable-panel">
        <strong>当前阶段没有 MCP 或多 Agent 管理接口</strong>
        <p>为避免把工具名、Agent 卡片或 Console 行为冒充真实功能，本页面只保留明确的未开放说明。</p>
        <button type="button" className="btn-disabled" disabled title="P4 尚未开放">P4 尚未开放</button>
      </section>
    </div>
  );
}
