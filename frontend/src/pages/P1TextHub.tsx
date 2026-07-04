import { FormEvent, useMemo, useRef, useState } from "react";
import { apiPath } from "../api";
import {
  intentOptions,
  qualityLabel,
  qualityLevel,
  reviewStatusLabels,
  riskLabels,
  riskOptions,
  SAMPLE_JSON,
  sourceTypeLabels,
  suggestedActionLabel,
} from "../constants";
import type {
  BackendStatus,
  CandidateEditState,
  CleaningJob,
  KnowledgeCandidate,
  ManualAction,
  ManualEditState,
  RagSearchResult,
  ReviewDecisionState,
  ReviewFilterState,
  ReviewStatus,
  SanitizedBatch,
  SanitizedMessage,
  SourceBatch,
  SourceType,
} from "../types";
import { Metric, RuleBox, SectionHeader, StepIndicator } from "../components/Shared";

const P1_STEPS = [
  { number: 1, label: "导入数据" },
  { number: 2, label: "机器清洗" },
  { number: 3, label: "人工清洗" },
  { number: 4, label: "知识审核" },
  { number: 5, label: "RAG & Agent" },
];

function toCandidateEdit(candidate: KnowledgeCandidate): CandidateEditState {
  return {
    question: candidate.question,
    answer: candidate.answer,
    intent: candidate.intent,
    tagsText: candidate.tags.join(", "),
    risk_level: candidate.risk_level,
    quality_score: String(candidate.quality_score),
  };
}

export function P1TextHub({
  backendStatus,
  onCheckBackend,
}: {
  backendStatus: BackendStatus;
  onCheckBackend: () => void;
}) {
  // Step tracking
  const [currentStep, setCurrentStep] = useState(1);

  // Step 1: Import
  const [sourceName, setSourceName] = useState("sample_customer_chat");
  const [jsonText, setJsonText] = useState("");
  const [showPasteArea, setShowPasteArea] = useState(false);
  const [sources, setSources] = useState<SourceBatch[]>([]);
  const [selectedBatchId, setSelectedBatchId] = useState("");
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const dropRef = useRef<HTMLDivElement | null>(null);
  const [dragOver, setDragOver] = useState(false);

  // Step 2: Cleaning
  const [cleaningJob, setCleaningJob] = useState<CleaningJob | null>(null);

  // Step 3: Manual Clean
  const [sanitizedBatch, setSanitizedBatch] = useState<SanitizedBatch | null>(null);
  const [manualEdits, setManualEdits] = useState<Record<string, ManualEditState>>({});

  // Step 4: Review
  const [candidates, setCandidates] = useState<KnowledgeCandidate[]>([]);
  const [candidateEdits, setCandidateEdits] = useState<Record<string, CandidateEditState>>({});
  const [reviewDecisions, setReviewDecisions] = useState<Record<string, ReviewDecisionState>>({});
  const [reviewFilters, setReviewFilters] = useState<ReviewFilterState>({
    status: "pending_review",
    source_type: "all",
    quality_level: "all",
    intent: "all",
    keyword: "",
  });

  // Step 5: RAG & Agent
  const [ragBuilt, setRagBuilt] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<RagSearchResult[]>([]);
  const [retrievalId, setRetrievalId] = useState("");
  const [badCaseForm, setBadCaseForm] = useState({
    user_query: "",
    agent_answer: "",
    issue_type: "wrong_answer",
    severity: "medium",
    expected_answer: "",
  });

  // Shared
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [isBusy, setIsBusy] = useState(false);

  // ------- Step 1 helpers -------
  const currentBatchOptions = useMemo(
    () =>
      sources.map((s) => ({
        id: s.batch_id,
        label: `${s.source_name} / ${s.batch_id}`,
      })),
    [sources],
  );

  function handleFileSelect(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (e) => {
      const text = e.target?.result as string;
      setJsonText(text);
      try {
        const parsed = JSON.parse(text);
        if (parsed.source_name) setSourceName(parsed.source_name);
      } catch { /* ignore */ }
    };
    reader.readAsText(file);
    event.target.value = "";
  }

  function handleDrop(event: React.DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragOver(false);
    const file = event.dataTransfer.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (e) => {
      const text = e.target?.result as string;
      setJsonText(text);
      try {
        const parsed = JSON.parse(text);
        if (parsed.source_name) setSourceName(parsed.source_name);
      } catch { /* ignore */ }
    };
    reader.readAsText(file);
  }

  function loadSampleData() {
    setJsonText(JSON.stringify(SAMPLE_JSON, null, 2));
    setSourceName(SAMPLE_JSON.source_name);
  }

  async function loadSources(showError = true) {
    try {
      const response = await fetch(apiPath("/api/sources"));
      const body = await response.json();
      if (response.ok && body.success) {
        setSources(body.data.sources);
        if (!selectedBatchId && body.data.sources.length > 0) {
          setSelectedBatchId(body.data.sources[0].batch_id);
        }
      }
    } catch {
      if (showError) setError("无法加载批次列表，请确认后端连接。");
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
      setError("JSON 格式不正确，请检查后重新导入。");
      return;
    }
    if (!sourceName.trim()) {
      setError("请输入数据名称。");
      return;
    }
    const payload =
      parsed && typeof parsed === "object"
        ? { ...parsed, source_name: sourceName.trim() }
        : parsed;

    setIsBusy(true);
    try {
      const response = await fetch(apiPath("/api/sources/import-json"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const body = await response.json();
      if (!response.ok || !body.success) {
        setError("导入失败，请确认 JSON 格式正确。");
        return;
      }
      setSelectedBatchId(body.data.batch_id);
      setMessage(`✅ 导入成功！批次 ID：${body.data.batch_id}`);
      await loadSources();
      setCurrentStep(2);
    } catch {
      setError("导入请求失败，请确认后端服务可用。");
    } finally {
      setIsBusy(false);
    }
  }

  // ------- Step 2 helpers -------
  async function runCleaning(batchId = selectedBatchId) {
    if (!batchId.trim()) {
      setError("请先选择或导入数据批次。");
      return;
    }
    setError("");
    setMessage("");
    setIsBusy(true);
    try {
      const response = await fetch(apiPath(`/api/cleaning/run/${batchId}`), { method: "POST" });
      const body = await response.json();
      if (!response.ok || !body.success) {
        setError("机器清洗失败，请确认批次存在。");
        return;
      }
      setCleaningJob(body.data);
      setMessage("✅ 机器清洗完成！");
      await loadSanitized(batchId);
      setCurrentStep(3);
    } catch {
      setError("机器清洗请求失败。");
    } finally {
      setIsBusy(false);
    }
  }

  async function loadSanitized(batchId = selectedBatchId) {
    if (!batchId.trim()) return;
    setError("");
    setIsBusy(true);
    try {
      const response = await fetch(apiPath(`/api/sanitized/${batchId}`));
      const body = await response.json();
      if (!response.ok || !body.success) {
        setError("未找到清洗后的数据，请先执行机器清洗。");
        return;
      }
      setSanitizedBatch(body.data);
      const editState: Record<string, ManualEditState> = {};
      body.data.messages.forEach((item: SanitizedMessage) => {
        editState[item.message_id] = {
          content: item.manual_cleaned_content || item.content,
          manual_action: item.manual_action || "keep",
          cleaner: item.cleaner || "cleaner_01",
          cleaning_note: item.cleaning_note || "",
        };
      });
      setManualEdits(editState);
    } catch {
      setError("读取清洗数据失败。");
    } finally {
      setIsBusy(false);
    }
  }

  // ------- Step 3 helpers -------
  function updateManualEdit(messageId: string, patch: Partial<ManualEditState>) {
    setManualEdits((current) => ({
      ...current,
      [messageId]: { ...current[messageId], ...patch },
    }));
  }

  async function saveManualClean(item: SanitizedMessage) {
    if (!sanitizedBatch) return;
    const edit = manualEdits[item.message_id];
    if (!edit?.content.trim()) {
      setError("清洗内容不能为空。");
      return;
    }
    setError("");
    setMessage("");
    setIsBusy(true);
    try {
      const response = await fetch(
        apiPath(`/api/sanitized/${sanitizedBatch.batch_id}/messages/${item.message_id}/manual-clean`),
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(edit),
        },
      );
      const body = await response.json();
      if (!response.ok || !body.success) {
        setError("保存失败。");
        return;
      }
      setMessage(`✅ 已保存：${body.data.record_id}`);
      await loadSanitized(sanitizedBatch.batch_id);
    } catch {
      setError("保存请求失败。");
    } finally {
      setIsBusy(false);
    }
  }

  async function runExtraction() {
    if (!sanitizedBatch) {
      setError("请先完成机器清洗。");
      return;
    }
    setError("");
    setMessage("");
    setIsBusy(true);
    try {
      const response = await fetch(apiPath(`/api/extraction/run/${sanitizedBatch.batch_id}`), {
        method: "POST",
      });
      const body = await response.json();
      if (!response.ok || !body.success) {
        setError("知识抽取失败。");
        return;
      }
      setMessage(`✅ 知识抽取完成，生成 ${body.data.candidate_count} 条候选知识。`);
      await loadCandidates();
      setCurrentStep(4);
    } catch {
      setError("知识抽取请求失败。");
    } finally {
      setIsBusy(false);
    }
  }

  // ------- Step 4 helpers -------
  async function loadCandidates(showError = true) {
    setError("");
    try {
      const response = await fetch(apiPath("/api/knowledge/candidates"));
      const body = await response.json();
      if (!response.ok || !body.success) {
        if (showError) setError("无法读取候选知识列表。");
        return;
      }
      const loaded: KnowledgeCandidate[] = body.data.candidates;
      setCandidates(loaded);
      const edits: Record<string, CandidateEditState> = {};
      const decisions: Record<string, ReviewDecisionState> = {};
      loaded.forEach((c) => {
        edits[c.candidate_id] = toCandidateEdit(c);
        decisions[c.candidate_id] = {
          reviewer: c.reviewer || "reviewer_01",
          review_note: c.review_note || "",
        };
      });
      setCandidateEdits(edits);
      setReviewDecisions(decisions);
    } catch {
      if (showError) setError("读取候选知识失败。");
    }
  }

  const filteredCandidates = useMemo(() => {
    const kw = reviewFilters.keyword.trim().toLowerCase();
    return candidates.filter((c) => {
      const st = c.source_type || "unknown";
      const lvl = qualityLevel(c.quality_score);
      if (reviewFilters.status !== "all" && c.review_status !== reviewFilters.status) return false;
      if (reviewFilters.source_type !== "all" && st !== reviewFilters.source_type) return false;
      if (reviewFilters.quality_level !== "all" && lvl !== reviewFilters.quality_level) return false;
      if (reviewFilters.intent !== "all" && c.intent !== reviewFilters.intent) return false;
      if (!kw) return true;
      return [c.candidate_id, c.question, c.answer, c.intent, c.tags.join(" ")]
        .join(" ")
        .toLowerCase()
        .includes(kw);
    });
  }, [candidates, reviewFilters]);

  function updateCandidateEdit(candidateId: string, patch: Partial<CandidateEditState>) {
    setCandidateEdits((cur) => ({
      ...cur,
      [candidateId]: { ...cur[candidateId], ...patch },
    }));
  }

  function updateReviewDecision(candidateId: string, patch: Partial<ReviewDecisionState>) {
    setReviewDecisions((cur) => ({
      ...cur,
      [candidateId]: { ...cur[candidateId], ...patch },
    }));
  }

  async function saveCandidate(candidate: KnowledgeCandidate) {
    const edit = candidateEdits[candidate.candidate_id];
    if (!edit) return;
    const qs = Number(edit.quality_score);
    if (!edit.question.trim() || !edit.answer.trim()) {
      setError("问题和答案不能为空。");
      return;
    }
    if (Number.isNaN(qs) || qs < 0 || qs > 1) {
      setError("质量分必须在 0 到 1 之间。");
      return;
    }
    setError("");
    setMessage("");
    setIsBusy(true);
    try {
      const response = await fetch(apiPath(`/api/knowledge/candidates/${candidate.candidate_id}`), {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: edit.question.trim(),
          answer: edit.answer.trim(),
          intent: edit.intent,
          tags: edit.tagsText.split(",").map((t) => t.trim()).filter(Boolean),
          risk_level: edit.risk_level,
          quality_score: qs,
        }),
      });
      const body = await response.json();
      if (!response.ok || !body.success) {
        setError("保存失败。");
        return;
      }
      setMessage(`✅ 已保存：${candidate.candidate_id}`);
      await loadCandidates();
    } catch {
      setError("保存请求失败。");
    } finally {
      setIsBusy(false);
    }
  }

  async function reviewCandidate(candidate: KnowledgeCandidate, action: "approve" | "reject" | "needs-revision") {
    const decision = reviewDecisions[candidate.candidate_id] || { reviewer: "reviewer_01", review_note: "" };
    if (!decision.reviewer.trim()) {
      setError("请填写审核人。");
      return;
    }
    setError("");
    setMessage("");
    setIsBusy(true);
    try {
      const response = await fetch(apiPath(`/api/review/${candidate.candidate_id}/${action}`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          reviewer: decision.reviewer.trim(),
          review_note: decision.review_note,
        }),
      });
      const body = await response.json();
      if (!response.ok || !body.success) {
        setError("审核操作失败。");
        return;
      }
      const label = action === "approve" ? "审核通过" : action === "reject" ? "已驳回" : "已打回修改";
      setMessage(`✅ ${label}：${candidate.candidate_id}`);
      await loadCandidates();
    } catch {
      setError("审核请求失败。");
    } finally {
      setIsBusy(false);
    }
  }

  // ------- Step 5 helpers -------
  async function buildRag() {
    setError("");
    setMessage("");
    setIsBusy(true);
    try {
      const response = await fetch(apiPath("/api/rag/build"), { method: "POST" });
      const body = await response.json();
      if (!response.ok || !body.success) {
        setError("RAG 构建失败。");
        return;
      }
      setRagBuilt(true);
      setMessage(`✅ RAG 构建完成！共 ${body.data.chunk_count} 个知识块。`);
      setCurrentStep(5);
    } catch {
      setError("RAG 构建请求失败。");
    } finally {
      setIsBusy(false);
    }
  }

  async function searchRag() {
    if (!searchQuery.trim()) {
      setError("请输入测试问题。");
      return;
    }
    setError("");
    setIsBusy(true);
    try {
      const response = await fetch(apiPath("/api/rag/search"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: searchQuery.trim(), top_k: 5 }),
      });
      const body = await response.json();
      if (!response.ok || !body.success) {
        setError("检索失败。");
        return;
      }
      setSearchResults(body.data.results || []);
    } catch {
      setError("检索请求失败。");
    } finally {
      setIsBusy(false);
    }
  }

  async function agentRetrieve() {
    if (!searchQuery.trim()) {
      setError("请输入测试问题。");
      return;
    }
    setError("");
    setIsBusy(true);
    try {
      const response = await fetch(apiPath("/api/customer-ops-agent/retrieve"), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-DataHub-Client": "CustomerOpsAgent",
        },
        body: JSON.stringify({ query: searchQuery.trim(), top_k: 5 }),
      });
      const body = await response.json();
      if (!response.ok || !body.success) {
        setError("Agent 检索失败。");
        return;
      }
      setSearchResults(body.data.results || []);
      setRetrievalId(body.data.retrieval_id);
    } catch {
      setError("Agent 检索请求失败。");
    } finally {
      setIsBusy(false);
    }
  }

  async function submitBadCase() {
    if (!retrievalId) {
      setError("请先执行 Agent 检索获取 retrieval_id。");
      return;
    }
    if (!badCaseForm.user_query.trim()) {
      setError("请填写用户问题。");
      return;
    }
    setError("");
    setMessage("");
    setIsBusy(true);
    try {
      const response = await fetch(apiPath("/api/customer-ops-agent/bad-cases"), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-DataHub-Client": "CustomerOpsAgent",
        },
        body: JSON.stringify({
          retrieval_id: retrievalId,
          user_query: badCaseForm.user_query.trim(),
          agent_answer: badCaseForm.agent_answer.trim(),
          issue_type: badCaseForm.issue_type,
          severity: badCaseForm.severity,
          expected_answer: badCaseForm.expected_answer.trim() || undefined,
        }),
      });
      const body = await response.json();
      if (!response.ok || !body.success) {
        setError("Bad Case 提交失败。");
        return;
      }
      setMessage(`✅ Bad Case 已提交：${body.data.bad_case_id}`);
    } catch {
      setError("Bad Case 提交请求失败。");
    } finally {
      setIsBusy(false);
    }
  }

  return (
    <div className="p1-page">
      <div className="page-hero">
        <h1>客服文本中台</h1>
        <p>将客服聊天数据导入、清洗、审核，最终沉淀为可供 Agent 使用的高质量 RAG 知识库。</p>
      </div>

      <StepIndicator steps={P1_STEPS} currentStep={currentStep} />

      {error ? <div className="message error">{error}</div> : null}
      {message ? <div className="message success">{message}</div> : null}

      {/* ======== Step 1: Import ======== */}
      <section className="work-step" id="step-1">
        <SectionHeader eyebrow="Step 1" title="导入客服数据" />
        <p className="step-desc">选择本地 JSON 文件、拖拽上传，或使用我们提供的示例数据开始体验。</p>

        <div
          ref={dropRef}
          className={`drop-zone ${dragOver ? "drag-over" : ""}`}
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
        >
          <span className="drop-icon">📂</span>
          <p>拖拽 JSON 文件到此处，或点击下方按钮选择文件</p>
          <div className="drop-actions">
            <input
              ref={fileInputRef}
              type="file"
              accept=".json"
              style={{ display: "none" }}
              onChange={handleFileSelect}
            />
            <button type="button" className="btn-primary" onClick={() => fileInputRef.current?.click()}>
              选择文件
            </button>
            <button
              type="button"
              className="btn-secondary"
              data-sample-btn
              onClick={loadSampleData}
            >
              使用示例数据
            </button>
            <button
              type="button"
              className="btn-outline"
              onClick={() => setShowPasteArea(!showPasteArea)}
            >
              {showPasteArea ? "隐藏" : "高级模式：粘贴 JSON"}
            </button>
          </div>
        </div>

        {showPasteArea ? (
          <form className="import-form" onSubmit={importJson}>
            <label>
              <span>数据名称</span>
              <input value={sourceName} onChange={(e) => setSourceName(e.target.value)} />
            </label>
            <label>
              <span>JSON 内容</span>
              <textarea
                rows={8}
                value={jsonText}
                onChange={(e) => setJsonText(e.target.value)}
                placeholder="在此粘贴 JSON 数据..."
              />
            </label>
            <button type="submit" className="btn-primary" disabled={isBusy}>
              {isBusy ? "导入中..." : "导入数据"}
            </button>
          </form>
        ) : jsonText ? (
          <form className="import-form" onSubmit={importJson}>
            <div className="json-preview">
              <strong>已加载数据预览：</strong>
              <pre>{jsonText.length > 500 ? jsonText.slice(0, 500) + "..." : jsonText}</pre>
            </div>
            <button type="submit" className="btn-primary" disabled={isBusy}>
              {isBusy ? "导入中..." : "确认导入"}
            </button>
          </form>
        ) : null}

        <div className="batch-selector">
          <label>
            <span>已有数据批次</span>
            <select value={selectedBatchId} onChange={(e) => setSelectedBatchId(e.target.value)}>
              <option value="">选择批次...</option>
              {currentBatchOptions.map((o) => (
                <option key={o.id} value={o.id}>{o.label}</option>
              ))}
            </select>
          </label>
          <button type="button" className="btn-secondary" onClick={() => loadSources()}>
            刷新批次列表
          </button>
        </div>
      </section>

      {/* ======== Step 2: Machine Clean ======== */}
      <section className="work-step" id="step-2">
        <SectionHeader
          eyebrow="Step 2"
          title="机器清洗"
          actions={
            <button
              type="button"
              className="btn-primary"
              disabled={isBusy || !selectedBatchId}
              onClick={() => runCleaning()}
            >
              执行机器清洗
            </button>
          }
        />
        <p className="step-desc">选择数据批次，一键执行机器清洗，自动完成 PII 脱敏、去重、质量评估和建议动作。</p>

        {!cleaningJob ? (
          <div className="empty-state">
            <p className="empty-title">尚未执行机器清洗</p>
            <p className="empty-desc">请先在 Step 1 导入数据，然后点击"执行机器清洗"。</p>
          </div>
        ) : (
          <div className="metric-grid">
            <Metric label="原始消息数" value={cleaningJob.raw_message_count} />
            <Metric label="清洗后消息数" value={cleaningJob.sanitized_message_count} />
            <Metric label="高质量" value={cleaningJob.sanitized_message_count - (cleaningJob.drop_recommended_count || 0) - (cleaningJob.low_quality_count || 0)} />
            <Metric label="需复核" value={(cleaningJob as any).review_recommended_count || 0} />
            <Metric label="建议丢弃" value={cleaningJob.drop_recommended_count || 0} />
            <Metric label="隐私脱敏" value={cleaningJob.pii_detected_count} />
            <Metric label="重复/近重复" value={(cleaningJob.exact_duplicate_count || 0) + (cleaningJob.near_duplicate_count || 0)} />
            <Metric label="平均质量分" value={cleaningJob.average_quality_score ?? 0} />
            <Metric label="丢弃消息数" value={cleaningJob.dropped_message_count} />
          </div>
        )}

        <div className="step-next-actions">
          <button type="button" className="btn-secondary" disabled={isBusy || !cleaningJob} onClick={() => loadSanitized()}>
            查看清洗结果
          </button>
          <button type="button" className="btn-primary" disabled={isBusy || !cleaningJob} onClick={runExtraction}>
            执行知识抽取 → Step 4
          </button>
        </div>
      </section>

      {/* ======== Step 3: Manual Clean ======== */}
      <section className="work-step" id="step-3">
        <SectionHeader eyebrow="Step 3" title="人工清洗" />
        <p className="step-desc">逐条审核机器清洗结果，修正内容、确认保留或丢弃。</p>

        <RuleBox
          title="清洗规则提示"
          rules={[
            "隐私必须脱敏，不能恢复真实个人信息。",
            "无意义内容、广告、噪声建议丢弃。",
            "有业务价值的客服问答优先保留。",
            "不确定内容标记为需要复核。",
            "不要改写原始业务含义，只修正清洗文本。",
          ]}
        />

        {!sanitizedBatch ? (
          <div className="empty-state">
            <p className="empty-title">尚未加载清洗数据</p>
            <p className="empty-desc">请先在 Step 2 执行机器清洗，然后点击"查看清洗结果"。</p>
          </div>
        ) : (
          <div className="message-list">
            {sanitizedBatch.messages.map((item) => (
              <article className="message-card" key={item.message_id}>
                <div className="message-header">
                  <span className={`role-badge ${item.role}`}>
                    {item.role === "customer" ? "客户" : item.role === "agent" ? "客服" : "系统"}
                  </span>
                  <span className={`quality-badge ${item.quality_level}`}>
                    {qualityLabel(item.quality_level)} / {item.quality_score}
                  </span>
                  <span className="suggest-badge">{suggestedActionLabel(item.suggested_action)}</span>
                </div>
                <p className="content-preview">{item.content}</p>
                <details className="tech-details">
                  <summary>技术字段</summary>
                  <div className="tech-fields">
                    <span>conversation_id: {item.conversation_id}</span>
                    <span>message_id: {item.message_id}</span>
                    {item.pii_detected ? <span className="pii-flag">PII: {item.pii_types.join(", ")}</span> : null}
                    {item.cleaning_issues.length > 0 ? <span>清洗问题: {item.cleaning_issues.join(", ")}</span> : null}
                    {item.risk_flags.length > 0 ? <span>风险标记: {item.risk_flags.join(", ")}</span> : null}
                  </div>
                </details>
                <div className="manual-grid">
                  <label>
                    <span>修正后的内容</span>
                    <textarea
                      value={manualEdits[item.message_id]?.content || item.content}
                      onChange={(e) => updateManualEdit(item.message_id, { content: e.target.value })}
                      rows={3}
                    />
                  </label>
                  <div className="manual-controls">
                    <label>
                      <span>操作</span>
                      <select
                        value={manualEdits[item.message_id]?.manual_action || "keep"}
                        onChange={(e) =>
                          updateManualEdit(item.message_id, { manual_action: e.target.value as ManualAction })
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
                        value={manualEdits[item.message_id]?.cleaner || "cleaner_01"}
                        onChange={(e) => updateManualEdit(item.message_id, { cleaner: e.target.value })}
                      />
                    </label>
                    <label>
                      <span>备注</span>
                      <textarea
                        rows={2}
                        value={manualEdits[item.message_id]?.cleaning_note || ""}
                        onChange={(e) => updateManualEdit(item.message_id, { cleaning_note: e.target.value })}
                      />
                    </label>
                    <button type="button" className="btn-primary btn-sm" onClick={() => saveManualClean(item)} disabled={isBusy}>
                      保存
                    </button>
                  </div>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>

      {/* ======== Step 4: Knowledge Review ======== */}
      <section className="work-step" id="step-4">
        <SectionHeader
          eyebrow="Step 4"
          title="知识审核"
          actions={
            <>
              <button type="button" className="btn-secondary" onClick={() => loadCandidates()} disabled={isBusy}>
                刷新候选知识
              </button>
              <button type="button" className="btn-primary" onClick={buildRag} disabled={isBusy}>
                构建 RAG 知识库
              </button>
            </>
          }
        />
        <p className="step-desc">审核机器抽取的候选知识，编辑内容，通过或驳回。</p>

        <RuleBox
          title="审核规则提示"
          rules={[
            "回答必须准确、可执行、无隐私。",
            "高风险规则必须谨慎，不能轻易承诺退款、赔偿、法律或支付结论。",
            "禁答内容不能作为普通 FAQ 进入 RAG，应保留为规则边界。",
            "转人工规则要保留，尤其是支付风险、物流异常、政策不确定场景。",
            "不确定内容打回修改；只有已通过才能进入 RAG。",
          ]}
        />

        <div className="filter-grid">
          <label>
            <span>审核状态</span>
            <select
              value={reviewFilters.status}
              onChange={(e) => setReviewFilters((c) => ({ ...c, status: e.target.value as any }))}
            >
              <option value="all">全部</option>
              <option value="pending_review">待审核</option>
              <option value="needs_revision">需修改</option>
              <option value="approved">已通过</option>
              <option value="rejected">已驳回</option>
            </select>
          </label>
          <label>
            <span>质量等级</span>
            <select
              value={reviewFilters.quality_level}
              onChange={(e) => setReviewFilters((c) => ({ ...c, quality_level: e.target.value as any }))}
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
              onChange={(e) => setReviewFilters((c) => ({ ...c, intent: e.target.value as any }))}
            >
              <option value="all">全部</option>
              {intentOptions.map((i) => (
                <option key={i} value={i}>{i}</option>
              ))}
            </select>
          </label>
          <label>
            <span>关键词搜索</span>
            <input
              value={reviewFilters.keyword}
              onChange={(e) => setReviewFilters((c) => ({ ...c, keyword: e.target.value }))}
              placeholder="搜索问题、答案、标签..."
            />
          </label>
        </div>

        <div className="review-summary">
          当前显示 {filteredCandidates.length} 条 / 全部 {candidates.length} 条。只有「已通过」候选知识可以进入 RAG。
        </div>

        <div className="candidate-list">
          {filteredCandidates.length === 0 ? (
            <div className="empty-state">
              <p className="empty-title">没有符合筛选条件的候选知识</p>
              <p className="empty-desc">请先执行 Step 2 的知识抽取，或在筛选条件中调整状态。</p>
            </div>
          ) : (
            filteredCandidates.map((candidate) => {
              const edit = candidateEdits[candidate.candidate_id] || toCandidateEdit(candidate);
              const decision = reviewDecisions[candidate.candidate_id] || { reviewer: "reviewer_01", review_note: "" };
              const lvl = qualityLevel(candidate.quality_score);
              const st = candidate.source_type || "unknown";

              return (
                <article className="candidate-card" key={candidate.candidate_id}>
                  <div className="candidate-header">
                    <div className="candidate-meta">
                      <span className={`review-badge ${candidate.review_status}`}>
                        {reviewStatusLabels[candidate.review_status]}
                      </span>
                      <span>{sourceTypeLabels[st]}</span>
                      <span>{riskLabels[candidate.risk_level]}</span>
                      <span className={`quality-badge ${lvl}`}>{qualityLabel(lvl)} / {candidate.quality_score}</span>
                    </div>
                  </div>

                  <div className="candidate-edit-grid">
                    <label>
                      <span>问题</span>
                      <textarea
                        rows={2}
                        value={edit.question}
                        onChange={(e) => updateCandidateEdit(candidate.candidate_id, { question: e.target.value })}
                      />
                    </label>
                    <label>
                      <span>答案</span>
                      <textarea
                        rows={2}
                        value={edit.answer}
                        onChange={(e) => updateCandidateEdit(candidate.candidate_id, { answer: e.target.value })}
                      />
                    </label>
                    <label>
                      <span>意图</span>
                      <select
                        value={edit.intent}
                        onChange={(e) => updateCandidateEdit(candidate.candidate_id, { intent: e.target.value as any })}
                      >
                        {intentOptions.map((i) => (
                          <option key={i} value={i}>{i}</option>
                        ))}
                      </select>
                    </label>
                    <label>
                      <span>风险等级</span>
                      <select
                        value={edit.risk_level}
                        onChange={(e) => updateCandidateEdit(candidate.candidate_id, { risk_level: e.target.value as any })}
                      >
                        {riskOptions.map((r) => (
                          <option key={r} value={r}>{riskLabels[r]}</option>
                        ))}
                      </select>
                    </label>
                    <label>
                      <span>质量分</span>
                      <input
                        value={edit.quality_score}
                        onChange={(e) => updateCandidateEdit(candidate.candidate_id, { quality_score: e.target.value })}
                      />
                    </label>
                    <label>
                      <span>标签（逗号分隔）</span>
                      <input
                        value={edit.tagsText}
                        onChange={(e) => updateCandidateEdit(candidate.candidate_id, { tagsText: e.target.value })}
                      />
                    </label>
                  </div>

                  <details className="tech-details">
                    <summary>查看来源</summary>
                    <div className="tech-fields">
                      <span>candidate_id: {candidate.candidate_id}</span>
                      {candidate.source_batch_id ? <span>batch: {candidate.source_batch_id}</span> : null}
                      {candidate.source_conversation_id ? <span>conversation: {candidate.source_conversation_id}</span> : null}
                      <span>created: {candidate.created_at}</span>
                      {candidate.updated_at ? <span>updated: {candidate.updated_at}</span> : null}
                    </div>
                  </details>

                  <div className="review-action-grid">
                    <label>
                      <span>审核人</span>
                      <input
                        value={decision.reviewer}
                        onChange={(e) => updateReviewDecision(candidate.candidate_id, { reviewer: e.target.value })}
                      />
                    </label>
                    <label>
                      <span>审核备注</span>
                      <textarea
                        rows={2}
                        value={decision.review_note}
                        onChange={(e) => updateReviewDecision(candidate.candidate_id, { review_note: e.target.value })}
                      />
                    </label>
                  </div>

                  <div className="candidate-actions">
                    <button type="button" className="btn-secondary btn-sm" onClick={() => saveCandidate(candidate)} disabled={isBusy}>
                      保存修改
                    </button>
                    <button type="button" className="btn-primary btn-sm" onClick={() => reviewCandidate(candidate, "approve")} disabled={isBusy}>
                      审核通过
                    </button>
                    <button type="button" className="btn-danger btn-sm" onClick={() => reviewCandidate(candidate, "reject")} disabled={isBusy}>
                      驳回
                    </button>
                    <button type="button" className="btn-outline btn-sm" onClick={() => reviewCandidate(candidate, "needs-revision")} disabled={isBusy}>
                      打回修改
                    </button>
                  </div>
                </article>
              );
            })
          )}
        </div>
      </section>

      {/* ======== Step 5: RAG & Agent ======== */}
      <section className="work-step" id="step-5">
        <SectionHeader eyebrow="Step 5" title="生成 RAG 并供给 Agent" />
        <p className="step-desc">构建 RAG 知识库，测试检索效果，提交 Bad Case 回流改进知识质量。</p>

        {!ragBuilt ? (
          <div className="empty-state">
            <p className="empty-title">尚未构建 RAG 知识库</p>
            <p className="empty-desc">请先在 Step 4 审核通过候选知识，然后点击"构建 RAG 知识库"。</p>
            <button type="button" className="btn-primary" onClick={buildRag} disabled={isBusy}>
              构建 RAG
            </button>
          </div>
        ) : (
          <>
            <div className="search-box">
              <label>
                <span>输入测试问题</span>
                <div className="search-row">
                  <input
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="例如：发货到德国需要多长时间？"
                  />
                  <button type="button" className="btn-primary" onClick={searchRag} disabled={isBusy}>
                    测试检索
                  </button>
                  <button type="button" className="btn-secondary" onClick={agentRetrieve} disabled={isBusy}>
                    Agent 检索
                  </button>
                </div>
              </label>
            </div>

            {retrievalId ? (
              <div className="retrieval-info">
                <span>Retrieval ID: <code>{retrievalId}</code></span>
              </div>
            ) : null}

            {searchResults.length > 0 ? (
              <div className="search-results">
                <h3>检索结果（{searchResults.length} 条）</h3>
                {searchResults.map((r, idx) => (
                  <div className="search-result-card" key={idx}>
                    <div className="result-header">
                      <span className="result-score">相关度：{(r.score * 100).toFixed(0)}%</span>
                      <span className="result-type">{r.knowledge_type}</span>
                      <span>意图：{r.intent}</span>
                    </div>
                    <pre className="result-text">{r.chunk_text}</pre>
                    {(r as any).answer ? (
                      <p className="result-answer"><strong>答案：</strong>{(r as any).answer}</p>
                    ) : null}
                  </div>
                ))}
              </div>
            ) : null}

            {retrievalId ? (
              <div className="bad-case-form">
                <h3>提交 Bad Case</h3>
                <p>如果 Agent 返回的结果不理想，请提交 Bad Case 帮助改进知识质量。提交后将生成待审核草稿。</p>
                <div className="bad-case-grid">
                  <label>
                    <span>用户问题</span>
                    <textarea
                      rows={2}
                      value={badCaseForm.user_query}
                      onChange={(e) => setBadCaseForm((f) => ({ ...f, user_query: e.target.value }))}
                    />
                  </label>
                  <label>
                    <span>Agent 回答</span>
                    <textarea
                      rows={2}
                      value={badCaseForm.agent_answer}
                      onChange={(e) => setBadCaseForm((f) => ({ ...f, agent_answer: e.target.value }))}
                    />
                  </label>
                  <label>
                    <span>期望答案（可选）</span>
                    <textarea
                      rows={2}
                      value={badCaseForm.expected_answer}
                      onChange={(e) => setBadCaseForm((f) => ({ ...f, expected_answer: e.target.value }))}
                    />
                  </label>
                  <label>
                    <span>问题类型</span>
                    <select
                      value={badCaseForm.issue_type}
                      onChange={(e) => setBadCaseForm((f) => ({ ...f, issue_type: e.target.value }))}
                    >
                      <option value="wrong_answer">答案错误</option>
                      <option value="missing_knowledge">知识缺失</option>
                      <option value="unsafe_answer">不安全答案</option>
                      <option value="bad_tone">语气不当</option>
                      <option value="retrieval_miss">检索遗漏</option>
                      <option value="other">其他</option>
                    </select>
                  </label>
                  <label>
                    <span>严重程度</span>
                    <select
                      value={badCaseForm.severity}
                      onChange={(e) => setBadCaseForm((f) => ({ ...f, severity: e.target.value }))}
                    >
                      <option value="low">低</option>
                      <option value="medium">中</option>
                      <option value="high">高</option>
                    </select>
                  </label>
                </div>
                <button type="button" className="btn-primary" onClick={submitBadCase} disabled={isBusy}>
                  提交 Bad Case
                </button>
              </div>
            ) : null}
          </>
        )}
      </section>
    </div>
  );
}
