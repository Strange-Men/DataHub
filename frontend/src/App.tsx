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
  raw_message_count: number;
  sanitized_message_count: number;
  dropped_message_count: number;
  pii_detected_count: number;
  exact_duplicate_count?: number;
  near_duplicate_count?: number;
  low_quality_count?: number;
  noise_count?: number;
  drop_recommended_count?: number;
  average_quality_score?: number;
  status: "completed";
};

type ManualAction = "keep" | "keep_edited" | "drop" | "needs_review";
type ReviewStatus = "pending_review" | "needs_revision" | "approved" | "rejected";
type SourceType =
  | "sanitized_batch"
  | "chat_logs"
  | "public_dataset"
  | "bad_case"
  | "legacy_rag"
  | "manual"
  | "unknown";
type Intent =
  | "shipping"
  | "refund"
  | "order_status"
  | "product_info"
  | "handoff"
  | "prohibited_answer"
  | "general";
type RiskLevel = "low" | "medium" | "high";
type KnowledgeType =
  | "faq"
  | "standard_answer"
  | "business_rule"
  | "human_handoff_rule"
  | "forbidden_answer_rule"
  | "escalation_rule"
  | "forbidden_rule";

type SanitizedMessage = {
  conversation_id: string;
  message_id: string;
  source_message_id: string;
  role: "customer" | "agent" | "system";
  content: string;
  pii_detected: boolean;
  pii_types: string[];
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
};

type SanitizedBatch = {
  batch_id: string;
  sanitized_message_count: number;
  low_quality_count?: number;
  noise_count?: number;
  average_quality_score?: number;
  messages: SanitizedMessage[];
};

type KnowledgeCandidate = {
  candidate_id: string;
  source_type?: SourceType;
  source_batch_id?: string | null;
  source_conversation_id?: string | null;
  source_message_ids: string[];
  source_bad_case_id?: string | null;
  source_retrieval_id?: string | null;
  source_chunk_ids?: string[];
  source_legacy_id?: string | null;
  source_import_id?: string | null;
  knowledge_type: KnowledgeType;
  question: string;
  answer: string;
  intent: Intent;
  tags: string[];
  risk_level: RiskLevel;
  review_status: ReviewStatus;
  quality_score: number;
  cleaning_issues?: string[];
  risk_flags?: string[];
  reviewer?: string | null;
  review_note?: string | null;
  reviewed_at?: string | null;
  created_at: string;
  updated_at?: string | null;
};

type ManualEditState = {
  content: string;
  manual_action: ManualAction;
  cleaner: string;
  cleaning_note: string;
};

type CandidateEditState = {
  question: string;
  answer: string;
  intent: Intent;
  tagsText: string;
  risk_level: RiskLevel;
  quality_score: string;
};

type ReviewFilterState = {
  status: "all" | ReviewStatus;
  source_type: "all" | SourceType;
  quality_level: "all" | "high" | "medium" | "low";
  intent: "all" | Intent;
  keyword: string;
};

type ReviewDecisionState = {
  reviewer: string;
  review_note: string;
};

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

const phaseCards = [
  {
    title: "P1 客服文本知识中台",
    status: "开发中",
    description: "导入、清洗、人工清洗、知识抽取、人工审核、统一 RAG、检索和 Bad Case 回流。",
    items: ["数据导入", "机器清洗", "人工清洗", "知识审核", "RAG 知识库", "Bad Case 回流"],
    disabled: false
  },
  {
    title: "P2 AI 素材中心接入",
    status: "Roadmap",
    description: "图片、视频、海报素材治理，当前只保留产品入口。",
    items: ["素材导入", "OCR / Caption", "标签 / SKU 绑定", "多模态审核", "多模态知识库"],
    disabled: true
  },
  {
    title: "P3 高质量数据资产复用",
    status: "Roadmap",
    description: "将已审核知识复用为销售培训、SOP、FAQ 和模型改进数据。",
    items: ["销售培训资料", "SOP / 话术手册", "FAQ 手册", "微调数据集导出"],
    disabled: true
  },
  {
    title: "P4 MCP + Agent 集群",
    status: "Roadmap",
    description: "封装统一工具层，面向 CustomerOpsAgent、SalesAgent、OpsAgent 等 Agent 集群。",
    items: ["MCP Tools", "CustomerOpsAgent", "SalesAgent", "OpsAgent", "MaterialAgent"],
    disabled: true
  }
];

const reviewStatusOptions: ReviewStatus[] = [
  "pending_review",
  "needs_revision",
  "approved",
  "rejected"
];
const sourceTypeOptions: SourceType[] = [
  "chat_logs",
  "public_dataset",
  "bad_case",
  "legacy_rag",
  "manual",
  "unknown"
];
const intentOptions: Intent[] = [
  "shipping",
  "refund",
  "order_status",
  "product_info",
  "handoff",
  "prohibited_answer",
  "general"
];
const riskOptions: RiskLevel[] = ["low", "medium", "high"];

const reviewStatusLabels: Record<ReviewStatus, string> = {
  pending_review: "待审核",
  needs_revision: "需修改",
  approved: "已通过",
  rejected: "已驳回"
};

const sourceTypeLabels: Record<SourceType, string> = {
  sanitized_batch: "清洗批次",
  chat_logs: "客服聊天",
  public_dataset: "公开数据集",
  bad_case: "坏例回流",
  legacy_rag: "旧 RAG 迁移",
  manual: "人工录入",
  unknown: "未知来源"
};

const riskLabels: Record<RiskLevel, string> = {
  low: "低风险",
  medium: "中风险",
  high: "高风险"
};

const knowledgeTypeLabels: Record<string, string> = {
  faq: "FAQ",
  standard_answer: "标准回答",
  business_rule: "业务规则",
  human_handoff_rule: "转人工规则",
  escalation_rule: "转人工规则",
  forbidden_answer_rule: "禁答规则",
  forbidden_rule: "禁答规则"
};

function qualityLevel(score: number): "high" | "medium" | "low" {
  if (score >= 0.8) return "high";
  if (score >= 0.5) return "medium";
  return "low";
}

function qualityLabel(level: "high" | "medium" | "low") {
  if (level === "high") return "高质量";
  if (level === "medium") return "需复核";
  return "低质量";
}

function suggestedActionLabel(action: SanitizedMessage["suggested_action"] | ManualAction) {
  const labels: Record<string, string> = {
    keep: "建议保留",
    review: "建议复核",
    drop: "建议丢弃",
    keep_edited: "修改后保留",
    needs_review: "需要复核"
  };
  return labels[action] || action;
}

function toCandidateEdit(candidate: KnowledgeCandidate): CandidateEditState {
  return {
    question: candidate.question,
    answer: candidate.answer,
    intent: candidate.intent,
    tagsText: candidate.tags.join(", "),
    risk_level: candidate.risk_level,
    quality_score: String(candidate.quality_score)
  };
}

export function App() {
  const [sourceName, setSourceName] = useState("sample_customer_chat");
  const [jsonText, setJsonText] = useState(defaultImportJson);
  const [sources, setSources] = useState<SourceBatch[]>([]);
  const [selectedBatchId, setSelectedBatchId] = useState("");
  const [cleaningJob, setCleaningJob] = useState<CleaningJob | null>(null);
  const [sanitizedBatch, setSanitizedBatch] = useState<SanitizedBatch | null>(null);
  const [manualEdits, setManualEdits] = useState<Record<string, ManualEditState>>({});
  const [candidates, setCandidates] = useState<KnowledgeCandidate[]>([]);
  const [candidateEdits, setCandidateEdits] = useState<Record<string, CandidateEditState>>({});
  const [reviewDecisions, setReviewDecisions] = useState<Record<string, ReviewDecisionState>>({});
  const [reviewFilters, setReviewFilters] = useState<ReviewFilterState>({
    status: "pending_review",
    source_type: "all",
    quality_level: "all",
    intent: "all",
    keyword: ""
  });
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [isBusy, setIsBusy] = useState(false);

  useEffect(() => {
    void loadSources();
    void loadCandidates();
  }, []);

  const currentBatchOptions = useMemo(
    () => sources.map((source) => ({ id: source.batch_id, label: `${source.source_name} / ${source.batch_id}` })),
    [sources]
  );

  const filteredCandidates = useMemo(() => {
    const keyword = reviewFilters.keyword.trim().toLowerCase();
    return candidates.filter((candidate) => {
      const sourceType = candidate.source_type || "unknown";
      const level = qualityLevel(candidate.quality_score);
      if (reviewFilters.status !== "all" && candidate.review_status !== reviewFilters.status) return false;
      if (reviewFilters.source_type !== "all" && sourceType !== reviewFilters.source_type) return false;
      if (reviewFilters.quality_level !== "all" && level !== reviewFilters.quality_level) return false;
      if (reviewFilters.intent !== "all" && candidate.intent !== reviewFilters.intent) return false;
      if (!keyword) return true;
      return [
        candidate.candidate_id,
        candidate.question,
        candidate.answer,
        candidate.intent,
        candidate.tags.join(" "),
        candidate.source_conversation_id || ""
      ]
        .join(" ")
        .toLowerCase()
        .includes(keyword);
    });
  }, [candidates, reviewFilters]);

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

  async function loadCandidates() {
    setError("");
    try {
      const response = await fetch("/api/knowledge/candidates");
      const body = await response.json();
      if (!response.ok || !body.success) {
        setError("无法读取知识候选列表。");
        return;
      }
      const loaded: KnowledgeCandidate[] = body.data.candidates;
      setCandidates(loaded);
      const edits: Record<string, CandidateEditState> = {};
      const decisions: Record<string, ReviewDecisionState> = {};
      loaded.forEach((candidate) => {
        edits[candidate.candidate_id] = toCandidateEdit(candidate);
        decisions[candidate.candidate_id] = {
          reviewer: candidate.reviewer || "local_reviewer",
          review_note: candidate.review_note || ""
        };
      });
      setCandidateEdits(edits);
      setReviewDecisions(decisions);
    } catch {
      setError("读取知识候选失败，请确认后端服务可用。");
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
      await loadCandidates();
    } catch {
      setError("知识抽取请求失败。");
    } finally {
      setIsBusy(false);
    }
  }

  function updateCandidateEdit(candidateId: string, patch: Partial<CandidateEditState>) {
    setCandidateEdits((current) => ({
      ...current,
      [candidateId]: {
        ...current[candidateId],
        ...patch
      }
    }));
  }

  function updateReviewDecision(candidateId: string, patch: Partial<ReviewDecisionState>) {
    setReviewDecisions((current) => ({
      ...current,
      [candidateId]: {
        ...current[candidateId],
        ...patch
      }
    }));
  }

  async function saveCandidate(candidate: KnowledgeCandidate) {
    const edit = candidateEdits[candidate.candidate_id];
    if (!edit) return;
    const qualityScore = Number(edit.quality_score);
    if (!edit.question.trim() || !edit.answer.trim()) {
      setError("问题和答案不能为空。");
      return;
    }
    if (Number.isNaN(qualityScore) || qualityScore < 0 || qualityScore > 1) {
      setError("quality_score 必须在 0 到 1 之间。");
      return;
    }
    setError("");
    setMessage("");
    setIsBusy(true);
    try {
      const response = await fetch(`/api/knowledge/candidates/${candidate.candidate_id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: edit.question.trim(),
          answer: edit.answer.trim(),
          intent: edit.intent,
          tags: edit.tagsText
            .split(",")
            .map((tag) => tag.trim())
            .filter(Boolean),
          risk_level: edit.risk_level,
          quality_score: qualityScore
        })
      });
      const body = await response.json();
      if (!response.ok || !body.success) {
        setError("保存候选知识修改失败。");
        return;
      }
      setMessage(`候选知识已保存：${candidate.candidate_id}`);
      await loadCandidates();
    } catch {
      setError("保存候选知识请求失败。");
    } finally {
      setIsBusy(false);
    }
  }

  async function reviewCandidate(candidate: KnowledgeCandidate, action: "approve" | "reject" | "needs-revision") {
    const decision = reviewDecisions[candidate.candidate_id] || {
      reviewer: "local_reviewer",
      review_note: ""
    };
    if (!decision.reviewer.trim()) {
      setError("请填写 reviewer。");
      return;
    }
    setError("");
    setMessage("");
    setIsBusy(true);
    try {
      const response = await fetch(`/api/review/${candidate.candidate_id}/${action}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          reviewer: decision.reviewer.trim(),
          review_note: decision.review_note
        })
      });
      const body = await response.json();
      if (!response.ok || !body.success) {
        setError("审核操作失败，请确认当前状态允许该操作。");
        return;
      }
      const label =
        action === "approve" ? "审核通过" : action === "reject" ? "已驳回" : "已打回修改";
      setMessage(`${label}：${candidate.candidate_id}`);
      await loadCandidates();
    } catch {
      setError("审核请求失败。");
    } finally {
      setIsBusy(false);
    }
  }

  async function buildRag() {
    setError("");
    setMessage("");
    setIsBusy(true);
    try {
      const response = await fetch("/api/rag/build", { method: "POST" });
      const body = await response.json();
      if (!response.ok || !body.success) {
        setError("RAG build 失败。");
        return;
      }
      setMessage(
        `RAG build 完成：built ${body.data.built_count} / updated ${body.data.updated_count} / chunks ${body.data.chunk_count}`
      );
    } catch {
      setError("RAG build 请求失败。");
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
          <article className={`phase-card ${card.disabled ? "muted-card" : ""}`} key={card.title}>
            <div className="card-title-row">
              <h2>{card.title}</h2>
              <span className={`status-badge status-${card.status}`}>状态：{card.status}</span>
            </div>
            <p>{card.description}</p>
            <div className="module-list">
              {card.items.map((item) => (
                <span key={item}>{item}</span>
              ))}
            </div>
            <button type="button" disabled={card.disabled}>
              {card.disabled ? "未接入" : "进入模块"}
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
            <select value={selectedBatchId} onChange={(event) => setSelectedBatchId(event.target.value)}>
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
          <span className="status-badge status-开发中">已接入</span>
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
                    <span>{suggestedActionLabel(item.suggested_action)}</span>
                  </div>
                  <p className="content-preview">{item.content}</p>
                  <TagList values={item.pii_types} variant="danger" prefix={item.pii_detected ? "PII" : ""} />
                  <TagList values={item.cleaning_issues} variant="muted" />
                  <TagList values={item.risk_flags} variant="warning" />
                  <div className="manual-grid">
                    <label>
                      <span>人工修正后的清洗文本</span>
                      <textarea
                        className="compact-textarea"
                        value={manualEdits[item.message_id]?.content || item.content}
                        onChange={(event) => updateManualEdit(item.message_id, { content: event.target.value })}
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
                          onChange={(event) => updateManualEdit(item.message_id, { cleaner: event.target.value })}
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

      <section className="panel review-workbench">
        <div className="panel-heading">
          <div>
            <p className="eyebrow compact">知识审核工作台</p>
            <h2>处理 pending_review knowledge candidates</h2>
          </div>
          <div className="button-row">
            <button type="button" className="secondary" onClick={loadCandidates} disabled={isBusy}>
              刷新候选知识
            </button>
            <button type="button" className="secondary" onClick={buildRag} disabled={isBusy}>
              Build RAG
            </button>
          </div>
        </div>

        <div className="rule-box">
          <strong>审核规则提示</strong>
          <ul>
            <li>回答必须准确、可执行、无隐私。</li>
            <li>高风险规则必须谨慎，不能轻易承诺退款、赔偿、法律或支付结论。</li>
            <li>禁答内容不能作为普通 FAQ 进入 RAG，应保留为规则边界。</li>
            <li>转人工规则要保留，尤其是支付风险、物流异常、政策不确定场景。</li>
            <li>不确定内容打回修改；只有 approved 才能进入 RAG。</li>
          </ul>
        </div>

        <div className="filter-grid">
          <label>
            <span>审核状态</span>
            <select
              value={reviewFilters.status}
              onChange={(event) =>
                setReviewFilters((current) => ({
                  ...current,
                  status: event.target.value as ReviewFilterState["status"]
                }))
              }
            >
              <option value="all">全部</option>
              {reviewStatusOptions.map((status) => (
                <option value={status} key={status}>
                  {reviewStatusLabels[status]}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>来源</span>
            <select
              value={reviewFilters.source_type}
              onChange={(event) =>
                setReviewFilters((current) => ({
                  ...current,
                  source_type: event.target.value as ReviewFilterState["source_type"]
                }))
              }
            >
              <option value="all">全部</option>
              {sourceTypeOptions.map((sourceType) => (
                <option value={sourceType} key={sourceType}>
                  {sourceTypeLabels[sourceType]}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>质量等级</span>
            <select
              value={reviewFilters.quality_level}
              onChange={(event) =>
                setReviewFilters((current) => ({
                  ...current,
                  quality_level: event.target.value as ReviewFilterState["quality_level"]
                }))
              }
            >
              <option value="all">全部</option>
              <option value="high">高质量</option>
              <option value="medium">需复核</option>
              <option value="low">低质量</option>
            </select>
          </label>
          <label>
            <span>意图</span>
            <select
              value={reviewFilters.intent}
              onChange={(event) =>
                setReviewFilters((current) => ({
                  ...current,
                  intent: event.target.value as ReviewFilterState["intent"]
                }))
              }
            >
              <option value="all">全部</option>
              {intentOptions.map((intent) => (
                <option value={intent} key={intent}>
                  {intent}
                </option>
              ))}
            </select>
          </label>
          <label className="wide-filter">
            <span>关键词搜索</span>
            <input
              value={reviewFilters.keyword}
              onChange={(event) =>
                setReviewFilters((current) => ({
                  ...current,
                  keyword: event.target.value
                }))
              }
              placeholder="搜索 question / answer / tags / source trace"
            />
          </label>
        </div>

        <div className="review-summary">
          当前显示 {filteredCandidates.length} 条 / 全部 {candidates.length} 条。只有“已通过”候选知识可以进入 RAG。
        </div>

        <div className="candidate-list">
          {filteredCandidates.length === 0 ? (
            <p className="empty-state">没有符合筛选条件的候选知识。</p>
          ) : (
            filteredCandidates.map((candidate) => (
              <CandidateCard
                key={candidate.candidate_id}
                candidate={candidate}
                edit={candidateEdits[candidate.candidate_id] || toCandidateEdit(candidate)}
                decision={
                  reviewDecisions[candidate.candidate_id] || {
                    reviewer: "local_reviewer",
                    review_note: ""
                  }
                }
                onEdit={(patch) => updateCandidateEdit(candidate.candidate_id, patch)}
                onDecision={(patch) => updateReviewDecision(candidate.candidate_id, patch)}
                onSave={() => saveCandidate(candidate)}
                onApprove={() => reviewCandidate(candidate, "approve")}
                onReject={() => reviewCandidate(candidate, "reject")}
                onNeedsRevision={() => reviewCandidate(candidate, "needs-revision")}
                disabled={isBusy}
              />
            ))
          )}
        </div>
      </section>
    </main>
  );
}

function CandidateCard({
  candidate,
  edit,
  decision,
  onEdit,
  onDecision,
  onSave,
  onApprove,
  onReject,
  onNeedsRevision,
  disabled
}: {
  candidate: KnowledgeCandidate;
  edit: CandidateEditState;
  decision: ReviewDecisionState;
  onEdit: (patch: Partial<CandidateEditState>) => void;
  onDecision: (patch: Partial<ReviewDecisionState>) => void;
  onSave: () => void;
  onApprove: () => void;
  onReject: () => void;
  onNeedsRevision: () => void;
  disabled: boolean;
}) {
  const level = qualityLevel(candidate.quality_score);
  const sourceType = candidate.source_type || "unknown";
  const sourceTrace = [
    candidate.source_batch_id ? `batch: ${candidate.source_batch_id}` : "",
    candidate.source_conversation_id ? `conversation: ${candidate.source_conversation_id}` : "",
    candidate.source_bad_case_id ? `bad case: ${candidate.source_bad_case_id}` : "",
    candidate.source_retrieval_id ? `retrieval: ${candidate.source_retrieval_id}` : "",
    candidate.source_legacy_id ? `legacy: ${candidate.source_legacy_id}` : "",
    candidate.source_import_id ? `import: ${candidate.source_import_id}` : "",
    candidate.source_message_ids?.length ? `messages: ${candidate.source_message_ids.join(", ")}` : ""
  ].filter(Boolean);

  return (
    <article className="candidate-card">
      <div className="candidate-header">
        <div>
          <h3>{candidate.candidate_id}</h3>
          <div className="message-meta">
            <span>{reviewStatusLabels[candidate.review_status]}</span>
            <span>{sourceTypeLabels[sourceType]}</span>
            <span>{knowledgeTypeLabels[candidate.knowledge_type] || candidate.knowledge_type}</span>
            <span>{riskLabels[candidate.risk_level]}</span>
            <span className={`quality quality-${level}`}>{qualityLabel(level)} / {candidate.quality_score}</span>
          </div>
        </div>
      </div>

      <div className="review-edit-grid">
        <label>
          <span>问题 question</span>
          <textarea
            className="compact-textarea"
            value={edit.question}
            onChange={(event) => onEdit({ question: event.target.value })}
          />
        </label>
        <label>
          <span>答案 answer</span>
          <textarea
            className="compact-textarea"
            value={edit.answer}
            onChange={(event) => onEdit({ answer: event.target.value })}
          />
        </label>
        <label>
          <span>intent</span>
          <select value={edit.intent} onChange={(event) => onEdit({ intent: event.target.value as Intent })}>
            {intentOptions.map((intent) => (
              <option value={intent} key={intent}>
                {intent}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>risk_level</span>
          <select
            value={edit.risk_level}
            onChange={(event) => onEdit({ risk_level: event.target.value as RiskLevel })}
          >
            {riskOptions.map((risk) => (
              <option value={risk} key={risk}>
                {riskLabels[risk]}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>quality_score</span>
          <input value={edit.quality_score} onChange={(event) => onEdit({ quality_score: event.target.value })} />
        </label>
        <label>
          <span>tags（逗号分隔）</span>
          <input value={edit.tagsText} onChange={(event) => onEdit({ tagsText: event.target.value })} />
        </label>
      </div>

      <div className="pill-row">
        {(candidate.cleaning_issues || []).map((issue) => (
          <span className="pill muted" key={`${candidate.candidate_id}-issue-${issue}`}>{issue}</span>
        ))}
        {(candidate.risk_flags || []).map((flag) => (
          <span className="pill warning" key={`${candidate.candidate_id}-risk-${flag}`}>{flag}</span>
        ))}
      </div>

      <div className="trace-box">
        <strong>source trace</strong>
        {sourceTrace.length ? (
          <ul>
            {sourceTrace.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        ) : (
          <p>暂无来源追溯字段。</p>
        )}
        <p>created_at: {candidate.created_at}</p>
        <p>updated_at: {candidate.updated_at || "未更新"}</p>
      </div>

      <div className="review-action-grid">
        <label>
          <span>reviewer</span>
          <input value={decision.reviewer} onChange={(event) => onDecision({ reviewer: event.target.value })} />
        </label>
        <label>
          <span>review_note</span>
          <textarea
            className="note-textarea"
            value={decision.review_note}
            onChange={(event) => onDecision({ review_note: event.target.value })}
          />
        </label>
      </div>

      <div className="button-row">
        <button type="button" className="secondary" onClick={onSave} disabled={disabled}>
          保存修改
        </button>
        <button type="button" onClick={onApprove} disabled={disabled}>
          审核通过
        </button>
        <button type="button" className="danger-button" onClick={onReject} disabled={disabled}>
          驳回
        </button>
        <button type="button" className="muted-button" onClick={onNeedsRevision} disabled={disabled}>
          打回修改
        </button>
      </div>
    </article>
  );
}

function TagList({
  values,
  variant,
  prefix
}: {
  values: string[];
  variant: "danger" | "muted" | "warning";
  prefix?: string;
}) {
  if (!values.length && !prefix) return null;
  return (
    <div className="pill-row">
      {prefix ? <span className={`pill ${variant}`}>{prefix}</span> : null}
      {values.map((value) => (
        <span className={`pill ${variant}`} key={value}>
          {value}
        </span>
      ))}
    </div>
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
