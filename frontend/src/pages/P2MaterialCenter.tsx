export function P2MaterialCenter() {
  const steps = [
    {
      number: 1,
      title: "素材导入",
      description: "上传图片、视频、海报等运营素材，支持批量导入和自动格式识别。",
    },
    {
      number: 2,
      title: "OCR / Caption",
      description: "自动识别图片中的文字（OCR），为视频和图片生成描述文本（Caption）。",
    },
    {
      number: 3,
      title: "标签 / SKU 绑定",
      description: "自动提取商品标签，将素材与 SKU、商品 ID 进行关联绑定。",
    },
    {
      number: 4,
      title: "多模态人工审核",
      description: "审核 OCR 结果、Caption 质量和标签正确性，确保多模态数据准确。",
    },
    {
      number: 5,
      title: "多模态知识库",
      description: "将审核后的素材、OCR、Caption 和标签沉淀为多模态 RAG 知识块。",
    },
    {
      number: 6,
      title: "多模态 CustomerOpsAgent",
      description: "Agent 可检索图片、视频描述等多媒体知识，提升客服体验。",
    },
  ];

  return (
    <div className="p2-page">
      <div className="page-hero">
        <h1>AI 素材中心</h1>
        <p>
          用于接入运营 Agent 生成的图片、视频、海报素材，后续通过 OCR、Caption、标签和 SKU
          绑定沉淀为多模态知识资产。
        </p>
      </div>

      <div className="roadmap-banner">
        <span className="roadmap-icon">🚧</span>
        <div>
          <strong>P2 阶段功能</strong>
          <p>本页面展示 AI 素材中心的未来产品流程，所有功能将在 P2 阶段接入真实后端能力。</p>
        </div>
      </div>

      <section className="flow-grid">
        {steps.map((step) => (
          <article className="flow-card" key={step.number}>
            <div className="flow-number">{step.number}</div>
            <h3>{step.title}</h3>
            <p>{step.description}</p>
            <button type="button" className="btn-disabled" disabled>
              P2 后接入
            </button>
          </article>
        ))}
      </section>

      <section className="info-panel">
        <h3>当前状态</h3>
        <ul>
          <li>页面流程已设计完毕，展示 P2 阶段的完整产品形态。</li>
          <li>所有操作按钮当前为禁用状态，不连接后端。</li>
          <li>图片、视频、海报等素材治理能力将在 P2 迭代中实现。</li>
          <li>多模态能力（OCR、Caption、视觉嵌入）依赖外部 AI 模型，P2 阶段将逐步接入。</li>
        </ul>
      </section>
    </div>
  );
}
