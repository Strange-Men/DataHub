export function P3AssetReuse() {
  const modules = [
    {
      icon: "📚",
      title: "销售新人培训资料",
      description: "将已审核的高质量客服问答自动整理为培训手册，帮助新销售快速掌握产品知识和话术。",
    },
    {
      icon: "📋",
      title: "SOP / 话术手册",
      description: "从知识库中提取标准操作流程和客服话术，生成可打印或可导出的标准化文档。",
    },
    {
      icon: "❓",
      title: "FAQ 手册",
      description: "自动从已审核知识中聚合高频问答，按意图和分类组织为 FAQ 手册。",
    },
    {
      icon: "🤖",
      title: "微调数据集导出",
      description: "将已审核的问答对导出为 JSONL 格式，用于大语言模型的微调训练。",
    },
    {
      icon: "🔍",
      title: "数据资产筛选",
      description: "按意图、风险等级、质量分、来源等维度筛选数据资产，满足不同场景的数据需求。",
    },
    {
      icon: "📤",
      title: "导出记录",
      description: "查看历史导出记录，追踪数据资产的使用和分发情况。",
    },
  ];

  return (
    <div className="p3-page">
      <div className="page-hero">
        <h1>高质量数据资产复用</h1>
        <p>
          将已审核客服知识、Bad Case 修正、优质问答复用为销售培训资料、SOP、FAQ
          手册和微调数据集。
        </p>
      </div>

      <div className="roadmap-banner">
        <span className="roadmap-icon">🚧</span>
        <div>
          <strong>P3 阶段功能</strong>
          <p>本页面展示数据资产复用的未来产品形态，所有功能将在 P3 阶段接入真实后端能力。</p>
        </div>
      </div>

      <section className="flow-grid">
        {modules.map((mod, idx) => (
          <article className="flow-card" key={idx}>
            <span className="module-icon">{mod.icon}</span>
            <h3>{mod.title}</h3>
            <p>{mod.description}</p>
            <button type="button" className="btn-disabled" disabled>
              P3 后接入
            </button>
          </article>
        ))}
      </section>

      <section className="info-panel">
        <h3>当前状态</h3>
        <ul>
          <li>页面模块已设计完毕，展示 P3 阶段的完整产品形态。</li>
          <li>所有操作按钮当前为禁用状态，不连接后端。</li>
          <li>数据资产复用能力将在 P3 迭代中实现，依赖 P1 知识库中的已审核数据。</li>
          <li>导出功能不提供真实文件下载，当前仅为产品预览。</li>
        </ul>
      </section>
    </div>
  );
}
