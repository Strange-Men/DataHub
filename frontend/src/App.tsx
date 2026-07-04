import { FormEvent, useEffect, useMemo, useState } from "react";

type SourceBatch = {
  batch_id: string;
  source_name: string;
  message_count: number;
  conversation_count: number;
  created_at: string;
  status: "raw_imported";
};

type CleaningJob = {
  job_id: string;
  sanitized_batch_id: string;
  raw_message_count: number;
  sanitized_message_count: number;
  dropped_message_count: number;
  pii_detected_count: number;
  exact_duplicate_count?: number;
  near_duplicate_count?: number;
  low_quality_count?: number;
  noise_count?: number;
  review_recommended_count?: number;
  drop_recommended_count?: number;
  average_quality_score?: number;
  status: "completed";
};

type ManualAction = "keep" | "keep_edited" | "drop" | "needs_review";

type SanitizedMessage = {
  conversation_id: string;
  message_id: string;
  source_message_id: string;
  role: "customer" | "agent" | "system";
  content: string;
  pii_detected: boolean;
  pii_types: string[];
  cleaning_notes: string[];
  cleaning_issues: string[];
  risk_flags: string[];
  quality_score: number;
  quality_level: "high" | "medium" | "low";
  suggested_action: "keep" | "review" | "drop";
  manual_cleaning_status?: "not_cleaned" | "cleaned";
  manual_cleaned_content?: string | null;
  manual_action?: ManualAction | null;
  cleaner?: string | null;
  cleaning_note?: string | null;
  manual_cleaned_at?: string | null;
};

type SanitizedBatch = {
  batch_id: string;
  source_batch_id: string;
  status: "sanitized";
  raw_message_count: number;
  sanitized_message_count: number;
  dropped_message_count: number;
  pii_detected_count: number;
  exact_duplicate_count?: number;
  near_duplicate_count?: number;
  low_quality_count?: number;
  noise_count?: number;
  review_recommended_count?: number;
  drop_recommended_count?: number;
  average_quality_score?: number;
  messages: SanitizedMessage[];
};

type ManualEditState = {
  content: string;
  manual_action: ManualAction;
  cleaner: string;
  cleaning_note: string;
};

type PhaseCard = {
  title: string;
  status: "已接入" | "开发中" | "Roadmap" | "未接入";
  description: string;
  items: string[];
};

const phaseCards: PhaseCard[] = [
  {
    title: "P1 客服文本知识中台",
    status: "开发中",
    description: "围绕客服聊天记录完成导入、清洗、审核、RAG、检索和 Bad Case 回流。",
    items: [
      "数据导入",
      "机器清洗",
      "人工清洗",
      "知识抽取",
      "人工审核",
      "RAG 知识库",
      "CustomerOpsAgent 检索",
      "Bad Case 回流"
    ]
  },
  {
    title: "P2 AI 素材中心接入",
    status: "Roadmap",
    description: "面向图片、视频、海报等素材治理，当前仅预留产品入口。",
    items: ["素材导入", "OCR / Caption", "标签 / SKU 绑定", "多模态审核", "多模态知识库"]
  },
  {
    title: "P3 高质量数据资产复用",
    status: "Roadmap",
    description: "将已审核知识复用为销售培训、SOP、FAQ 和模型改进数据。",
    items: ["销售培训资料", "SOP / 话术手册", "FAQ 手册", "微调数据集导出"]
  },
  {
    title: "P4 MCP + Agent 集群",
    status: "Roadmap",
    description: "封装统一工具层，面向 CustomerOpsAgent、SalesAgent、OpsAgent 等 Agent 集群。",
    items: ["MCP Tools", "CustomerOpsAgent", "SalesAgent", "OpsAgent", "MaterialAgent"]
  }
];

const defaultImportJson = `{
  "source_name": "sample_customer_chat",
  "conversations": [
    {
      "conversation_id": "conv_001",
      "messages": [
        {
          "message_id": "msg_001",
          "role": "customer",
          "content": "How long does shipping take to Germany?",
          "timestamp": "2026-07-03T10:00:00"
        },
        {
          "message_id": "msg_002",
          "role": "agent",
          "content": "Shipping to Germany usually takes 7-12 business days after dispatch.",
          "timestamp": "2026-07-03T10:01:00"
        }
      ]
    }
  ]
}`;

function statusLabel(status: PhaseCard["status"]) {
  return `状态：${status}`;
}

function qualityLabel(level: SanitizedMessage["quality_level"]) {
  if (level === "high") return "高质量";
  if (level === "medium") return "需复核";
  return "建议丢弃";
}

function actionLabel(action: SanitizedMessage["suggested_action"] | ManualAction) {
  const map: Record<string, string> = {
    keep: "建议保留",
    review: "建议复核",
    drop: "建议丢弃",
    keep_edited: "修改后保留",
    needs_review: "需要复核"
  };
  return map[action] || action;
}

export function App() {
  const [sourceName, setSourceName] = useState("sample_customer_chat");
  const [jsonText, setJsonText] = useState(defaultImportJson);
  const [sources, setSources] = useState<SourceBatch[]>([]);
  const [selectedBatchId, setSelectedBatchId] = useState("");
  const [cleaningJob, setCleaningJob] = useState<CleaningJob | null>(null);
  const [sanitizedBatch, setSanitizedBatch] = useState<SanitizedBatch | null>(null);
  const [manualEdits, setManualEdits] = useState<Record<string, ManualEditState>>({});
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [isBusy, setIsBusy] = useState(false);

  useEffect(() => {
    void loadSources();
  }, []);

  const currentBatchOptions = useMemo(
    () => sources.map((source) => ({ id: source.batch_id, label: `${source.source_name} / ${source.batch_id}` })),
    [sources]
  );

  async function loadSources() {
    try {
      const response = await fetch("/api/sources");
      const body = await response.json();
      if (response.ok && body.success) {
        setSources(body.data.sources);
        if (!selectedBatchId && body.data.sources.length > 0) {
          setSelectedBatchId(body.data.sources[0].batch_id);
        }
      }
    } catch {
      setError("无法加载批次列表，请确认 FastAPI 后端正在运行。");
    }
  }

  async function importJson(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setMessage("");
    let parsed: unknown;
    try {
      parsed = JSON.parse(jsonText);
    } catch {
      setError("JSON 格式不正确，请检查后再导入。");
      return;
    }
    if (!sourceName.trim()) {
      setError("请输入 source name。");
      return;
    }
    const payload =
      parsed && typeof parsed === "object"
        ? { ...parsed, source_name: sourceName.trim() }
        : parsed;

    setIsBusy(true);
    try {
      const response = await fetch("/api/sources/import-json", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const body = await response.json();
      if (!response.ok || !body.success) {
        setError("导入失败，请确认 JSON 字段符合 DataHub 格式。");
        return;
      }
      setSelectedBatchId(body.data.batch_id);
      setMessage(`导入成功：${body.data.batch_id}`);
      await loadSources();
    } catch {
      setError("导入请求失败，请确认后端服务可用。");
    } finally {
      setIsBusy(false);
    }
  }

  async function runCleaning(batchId = selectedBatchId) {
    if (!batchId.trim()) {
      setError("请先选择或输入 batch_id。");
      return;
    }
    setError("");
    setMessage("");
    setIsBusy(true);
    try {
      const response = await fetch(`/api/cleaning/run/${batchId}`, { method: "POST" });
      const body = await response.json();
      if (!response.ok || !body.success) {
        setError("机器清洗失败，请确认 raw batch 存在。");
        return;
      }
      setCleaningJob(body.data);
      setMessage("机器清洗完成，已生成 sanitized batch。");
      await loadSanitized(batchId);
    } catch {
      setError("机器清洗请求失败。");
    } finally {
      setIsBusy(false);
    }
  }

  async function loadSanitized(batchId = selectedBatchId) {
    if (!batchId.trim()) {
      setError("请先选择或输入 batch_id。");
      return;
    }
    setError("");
    setIsBusy(true);
    try {
      const response = await fetch(`/api/sanitized/${batchId}`);
      const body = await response.json();
      if (!response.ok || !body.success) {
        setError("未找到 sanitized batch，请先执行机器清洗。");
        return;
      }
      setSanitizedBatch(body.data);
      const editState: Record<string, ManualEditState> = {};
      body.data.messages.forEach((item: SanitizedMessage) => {
        editState[item.message_id] = {
          content: item.manual_cleaned_content || item.content,
          manual_action: item.manual_action || "keep",
          cleaner: item.cleaner || "local_cleaner",
          cleaning_note: item.cleaning_note || ""
        };
      });
      setManualEdits(editState);
    } catch {
      setError("读取 sanitized batch 失败。");
    } finally {
      setIsBusy(false);
    }
  }

  function updateManualEdit(messageId: string, patch: Partial<ManualEditState>) {
    setManualEdits((current) => ({
      ...current,
      [messageId]: {
        ...current[messageId],
        ...patch
      }
    }));
  }

  async function saveManualClean(item: SanitizedMessage) {
    if (!sanitizedBatch) return;
    const edit = manualEdits[item.message_id];
    if (!edit?.content.trim()) {
      setError("人工清洗内容不能为空。");
      return;
    }
    setError("");
    setMessage("");
    setIsBusy(true);
    try {
      const response = await fetch(
        `/api/sanitized/${sanitizedBatch.batch_id}/messages/${item.message_id}/manual-clean`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(edit)
        }
      );
      const body = await response.json();
      if (!response.ok || !body.success) {
        setError("保存人工清洗结果失败。");
        return;
      }
      setMessage(`人工清洗已保存：${body.data.record_id}`);
      await loadSanitized(sanitizedBatch.batch_id);
    } catch {
      setError("保存人工清洗请求失败。");
    } finally {
      setIsBusy(false);
    }
  }

  async function runExtraction() {
    if (!sanitizedBatch) {
      setError("请先读取 sanitized batch。");
      return;
    }
    setError("");
    setMessage("");
    setIsBusy(true);
    try {
      const response = await fetch(`/api/extraction/run/${sanitizedBatch.batch_id}`, {
        method: "POST"
      });
      const body = await response.json();
      if (!response.ok || !body.success) {
        setError("知识抽取失败。");
        return;
      }
      setMessage(`知识抽取完成，生成候选知识 ${body.data.candidate_count} 条。`);
    } catch {
      setError("知识抽取请求失败。");
    } finally {
      setIsBusy(false);
    }
  }

  return (
    <main className="app-shell">
      <section className="hero-band">
        <div>
          <p className="eyebrow">DataHub 管理台</p>
          <h1>DataHub 数据治理与 RAG 知识中台</h1>
          <p className="summary">
            面向 Agent 集群的多源数据治理、知识生产与统一检索平台。当前聚焦 P1
            文本客服知识中台补强，P2/P3/P4 为 Roadmap，尚未接入后端。
          </p>
        </div>
        <div className="hero-status">
          <span>当前状态</span>
          <strong>P1 文本客服知识中台补强中</strong>
          <p>P2/P3/P4 入口仅用于产品结构预留。</p>
        </div>
      </section>

      {error ? <div className="message error">{error}</div> : null}
      {message ? <div className="message success">{message}</div> : null}

      <section className="phase-grid" aria-label="DataHub phase modules">
        {phaseCards.map((card) => (
          <article className={`phase-card ${card.status === "Roadmap" ? "muted-card" : ""}`} key={card.title}>
            <div className="card-title-row">
              <h2>{card.title}</h2>
              <span className={`status-badge status-${card.status}`}>{statusLabel(card.status)}</span>
            </div>
            <p>{card.description}</p>
            <div className="module-list">
              {card.items.map((item) => (
                <span key={item}>{item}</span>
              ))}
            </div>
            <button type="button" disabled={card.status === "Roadmap" || card.status === "未接入"}>
              {card.status === "Roadmap" ? "未接入" : "进入模块"}
            </button>
          </article>
        ))}
      </section>

      <section className="workbench-grid">
        <article className="panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow compact">数据导入</p>
              <h2>导入客服聊天 JSON</h2>
            </div>
            <button type="button" className="secondary" onClick={loadSources}>
              刷新批次
            </button>
          </div>
          <form className="stacked-form" onSubmit={importJson}>
            <label>
              <span>source name</span>
              <input value={sourceName} onChange={(event) => setSourceName(event.target.value)} />
            </label>
            <label>
              <span>JSON 内容</span>
              <textarea value={jsonText} onChange={(event) => setJsonText(event.target.value)} />
            </label>
            <button type="submit" disabled={isBusy}>
              导入 raw batch
            </button>
          </form>
        </article>

        <article className="panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow compact">机器清洗</p>
              <h2>选择批次并生成 sanitized 数据</h2>
            </div>
          </div>
          <label>
            <span>选择 batch_id</span>
            <select
              value={selectedBatchId}
              onChange={(event) => setSelectedBatchId(event.target.value)}
            >
              <option value="">手动输入或选择批次</option>
              {currentBatchOptions.map((option) => (
                <option value={option.id} key={option.id}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>batch_id</span>
            <input value={selectedBatchId} onChange={(event) => setSelectedBatchId(event.target.value)} />
          </label>
          <div className="button-row">
            <button type="button" onClick={() => runCleaning()} disabled={isBusy}>
              执行机器清洗
            </button>
            <button type="button" className="secondary" onClick={() => loadSanitized()} disabled={isBusy}>
              读取 sanitized batch
            </button>
            <button type="button" className="secondary" onClick={runExtraction} disabled={isBusy || !sanitizedBatch}>
              执行知识抽取
            </button>
          </div>
          {cleaningJob ? (
            <div className="metric-grid">
              <Metric label="raw" value={cleaningJob.raw_message_count} />
              <Metric label="sanitized" value={cleaningJob.sanitized_message_count} />
              <Metric label="PII" value={cleaningJob.pii_detected_count} />
              <Metric label="重复" value={cleaningJob.exact_duplicate_count || 0} />
              <Metric label="近重复" value={cleaningJob.near_duplicate_count || 0} />
              <Metric label="建议丢弃" value={cleaningJob.drop_recommended_count || 0} />
            </div>
          ) : null}
        </article>
      </section>

      <section className="panel manual-workbench">
        <div className="panel-heading">
          <div>
            <p className="eyebrow compact">人工清洗工作台</p>
            <h2>校验、修正并记录 sanitized message</h2>
          </div>
          <span className="status-badge status-开发中">开发中</span>
        </div>
        <div className="rule-box">
          <strong>清洗规则提示</strong>
          <ul>
            <li>隐私必须脱敏，不能恢复真实个人信息。</li>
            <li>无意义内容、广告、噪声建议丢弃。</li>
            <li>有业务价值的客服问答优先保留。</li>
            <li>不确定内容标记为需要复核。</li>
            <li>不要改写原始业务含义，只修正清洗文本。</li>
          </ul>
        </div>
        {!sanitizedBatch ? (
          <p className="empty-state">请选择 batch 并读取 sanitized 数据。</p>
        ) : (
          <>
            <div className="metric-grid">
              <Metric label="消息数" value={sanitizedBatch.sanitized_message_count} />
              <Metric label="低质量" value={sanitizedBatch.low_quality_count || 0} />
              <Metric label="噪声" value={sanitizedBatch.noise_count || 0} />
              <Metric label="平均分" value={sanitizedBatch.average_quality_score ?? 0} />
            </div>
            <div className="message-list">
              {sanitizedBatch.messages.map((item) => (
                <article className="message-card" key={item.message_id}>
                  <div className="message-meta">
                    <span>{item.conversation_id}</span>
                    <span>{item.message_id}</span>
                    <span>{item.role}</span>
                    <span className={`quality quality-${item.quality_level}`}>
                      {qualityLabel(item.quality_level)} / {item.quality_score}
                    </span>
                    <span>{actionLabel(item.suggested_action)}</span>
                  </div>
                  <p className="content-preview">{item.content}</p>
                  <div className="pill-row">
                    {item.pii_detected ? <span className="pill danger">PII</span> : null}
                    {item.pii_types.map((type) => (
                      <span className="pill" key={`${item.message_id}-pii-${type}`}>
                        {type}
                      </span>
                    ))}
                    {item.cleaning_issues.map((issue) => (
                      <span className="pill muted" key={`${item.message_id}-issue-${issue}`}>
                        {issue}
                      </span>
                    ))}
                    {item.risk_flags.map((flag) => (
                      <span className="pill warning" key={`${item.message_id}-risk-${flag}`}>
                        {flag}
                      </span>
                    ))}
                  </div>
                  {item.manual_cleaning_status === "cleaned" ? (
                    <div className="manual-status">
                      已人工清洗：{item.manual_action ? actionLabel(item.manual_action) : "已处理"} /{" "}
                      {item.cleaner || "未记录清洗员"}
                    </div>
                  ) : null}
                  <div className="manual-grid">
                    <label>
                      <span>人工修正后的清洗文本</span>
                      <textarea
                        className="compact-textarea"
                        value={manualEdits[item.message_id]?.content || item.content}
                        onChange={(event) =>
                          updateManualEdit(item.message_id, { content: event.target.value })
                        }
                      />
                    </label>
                    <div className="manual-controls">
                      <label>
                        <span>人工处理动作</span>
                        <select
                          value={manualEdits[item.message_id]?.manual_action || "keep"}
                          onChange={(event) =>
                            updateManualEdit(item.message_id, {
                              manual_action: event.target.value as ManualAction
                            })
                          }
                        >
                          <option value="keep">保留</option>
                          <option value="keep_edited">修改后保留</option>
                          <option value="drop">丢弃</option>
                          <option value="needs_review">需要复核</option>
                        </select>
                      </label>
                      <label>
                        <span>清洗员</span>
                        <input
                          value={manualEdits[item.message_id]?.cleaner || "local_cleaner"}
                          onChange={(event) =>
                            updateManualEdit(item.message_id, { cleaner: event.target.value })
                          }
                        />
                      </label>
                      <label>
                        <span>人工清洗备注</span>
                        <textarea
                          className="note-textarea"
                          value={manualEdits[item.message_id]?.cleaning_note || ""}
                          onChange={(event) =>
                            updateManualEdit(item.message_id, {
                              cleaning_note: event.target.value
                            })
                          }
                        />
                      </label>
                      <button type="button" onClick={() => saveManualClean(item)} disabled={isBusy}>
                        保存人工清洗结果
                      </button>
                    </div>
                  </div>
                </article>
              ))}
            </div>
          </>
        )}
      </section>
    </main>
  );
}

function Metric({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
