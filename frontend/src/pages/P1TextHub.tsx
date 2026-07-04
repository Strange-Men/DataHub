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
  { number: 2, label: "清洗数据" },
  { number: 3, label: "生成并审核知识" },
  { number: 4, label: "更新知识库并测试 Agent" },
];

const MANUAL_PAGE_SIZE = 10;
const REVIEW_PAGE_SIZE = 10;

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
  // ---- current main step ----
  const [currentStep, setCurrentStep] = useState(1);

  // ======== Step 1: Import ========
  const [sourceName, setSourceName] = useState("sample_customer_chat");
  const [jsonText, setJsonText] = useState("");
  const [showPasteArea, setShowPasteArea] = useState(false);
  const [sources, setSources] = useState<SourceBatch[]>([]);
  const [selectedBatchId, setSelectedBatchId] = useState("");
  const [importResult, setImportResult] = useState<{ batch_id: string; message_count: number } | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const dropRef = useRef<HTMLDivElement | null>(null);
  const [dragOver, setDragOver] = useState(false);

  // ======== Step 2: Cleaning ========
  const [cleaningJob, setCleaningJob] = useState<CleaningJob | null>(null);
  const [sanitizedBatch, setSanitizedBatch] = useState<SanitizedBatch | null>(null);
  const [manualEdits, setManualEdits] = useState<Record<string, ManualEditState>>({});
  const [cleaningSubTab, setCleaningSubTab] = useState<"machine" | "manual">("machine");
  // Manual cleaning pagination & search
  const [manualPage, setManualPage] = useState(1);
  const [manualSearch, setManualSearch] = useState("");
  const [manualQualityFilter, setManualQualityFilter] = useState<"all" | "high" | "medium" | "low">("all");
  const [manualActionFilter, setManualActionFilter] = useState<"all" | ManualAction>("all");
  const [expandedMessages, setExpandedMessages] = useState<Set<string>>(new Set());

  // ======== Step 3: Knowledge ========
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
  const [knowledgeSubTab, setKnowledgeSubTab] = useState<"generate" | "review">("generate");
  const [extractionResult, setExtractionResult] = useState<{ candidate_count: number; skipped_count?: number } | null>(null);
  const [reviewPage, setReviewPage] = useState(1);

  // ======== Step 4: Sync & Agent ========
  const [ragBuilt, setRagBuilt] = useState(false);
  const [ragChunkCount, setRagChunkCount] = useState(0);
  const [searchQuery, setSearchQuery] = useState("");
  const [agentResults, setAgentResults] = useState<RagSearchResult[]>([]);
  const [agentAnswer, setAgentAnswer] = useState("");
  const [retrievalId, setRetrievalId] = useState("");
  const [agentSearched, setAgentSearched] = useState(false);
  const [badCaseForm, setBadCaseForm] = useState({
    user_query: "",
    agent_answer: "",
    issue_type: "wrong_answer",
    severity: "medium",
    expected_answer: "",
  });
  const [badCaseSubmitted, setBadCaseSubmitted] = useState(false);

  // ---- shared ----
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [isBusy, setIsBusy] = useState(false);

  // ================================================================
  // Step 1 helpers
  // ================================================================
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
      const msgCount = body.data.message_count ?? 0;
      setImportResult({ batch_id: body.data.batch_id, message_count: msgCount });
      setMessage(`✅ 导入成功！批次：${body.data.batch_id}，包含 ${msgCount} 条消息。`);
      await loadSources(false);
    } catch {
      setError("导入请求失败，请确认后端服务可用。");
    } finally {
      setIsBusy(false);
    }
  }

  // ================================================================
  // Step 2 helpers
  // ================================================================
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
      setMessage("✅ 机器清洗完成！正在加载清洗数据...");
      await loadSanitized(batchId);
      setCleaningSubTab("manual");
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
      setManualPage(1);
      setExpandedMessages(new Set());
    } catch {
      setError("读取清洗数据失败。");
    } finally {
      setIsBusy(false);
    }
  }

  // ---- manual cleaning filtering & pagination ----
  const filteredManualMessages = useMemo(() => {
    if (!sanitizedBatch) return [];
    let msgs = sanitizedBatch.messages;
    const kw = manualSearch.trim().toLowerCase();
    if (kw) {
      msgs = msgs.filter((m) => {
        const edit = manualEdits[m.message_id];
        const searchText = [m.content, m.role, m.message_id, edit?.content || "", edit?.cleaning_note || ""]
          .join(" ")
          .toLowerCase();
        return searchText.includes(kw);
      });
    }
    if (manualQualityFilter !== "all") {
      msgs = msgs.filter((m) => m.quality_level === manualQualityFilter);
    }
    if (manualActionFilter !== "all") {
      msgs = msgs.filter((m) => {
        const edit = manualEdits[m.message_id];
        return (edit?.manual_action || m.suggested_action) === manualActionFilter;
      });
    }
    return msgs;
  }, [sanitizedBatch, manualSearch, manualQualityFilter, manualActionFilter, manualEdits]);

  const manualTotalPages = Math.max(1, Math.ceil(filteredManualMessages.length / MANUAL_PAGE_SIZE));
  const manualPageMessages = useMemo(() => {
    const start = (manualPage - 1) * MANUAL_PAGE_SIZE;
    return filteredManualMessages.slice(start, start + MANUAL_PAGE_SIZE);
  }, [filteredManualMessages, manualPage]);

  const manualProgress = useMemo(() => {
    if (!sanitizedBatch) return { total: 0, cleaned: 0 };
    const total = sanitizedBatch.messages.length;
    const cleaned = sanitizedBatch.messages.filter((m) => m.manual_cleaning_status === "cleaned").length;
    return { total, cleaned };
  }, [sanitizedBatch]);

  function toggleExpand(messageId: string) {
    setExpandedMessages((prev) => {
      const next = new Set(prev);
      if (next.has(messageId)) next.delete(messageId);
      else next.add(messageId);
      return next;
    });
  }

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
      const actionLabel = suggestedActionLabel(edit.manual_action);
      setMessage(`✅ 已保存 — 处理方式：${actionLabel}。可继续清洗下一条，或前往 Step 3 生成知识。`);
      await loadSanitized(sanitizedBatch.batch_id);
    } catch {
      setError("保存请求失败。");
    } finally {
      setIsBusy(false);
    }
  }

  // ================================================================
  // Step 3 helpers
  // ================================================================
  async function runExtraction() {
    if (!sanitizedBatch) {
      setError("请先在 Step 2 完成机器清洗。");
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
        setError("生成待审核知识失败。");
        return;
      }
      const count = body.data.candidate_count ?? 0;
      setExtractionResult({ candidate_count: count });
      setMessage(`✅ 已生成 ${count} 条待审核知识。下一步：进入「知识审核」进行审核。`);
      await loadCandidates(false);
      setKnowledgeSubTab("review");
    } catch {
      setError("生成待审核知识请求失败。");
    } finally {
      setIsBusy(false);
    }
  }

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

  const reviewStatusCounts = useMemo(() => {
    const counts: Record<string, number> = { pending_review: 0, approved: 0, rejected: 0, needs_revision: 0 };
    candidates.forEach((c) => {
      counts[c.review_status] = (counts[c.review_status] || 0) + 1;
    });
    return counts;
  }, [candidates]);

  const reviewTotalPages = Math.max(1, Math.ceil(filteredCandidates.length / REVIEW_PAGE_SIZE));
  const reviewPageCandidates = useMemo(() => {
    const start = (reviewPage - 1) * REVIEW_PAGE_SIZE;
    return filteredCandidates.slice(start, start + REVIEW_PAGE_SIZE);
  }, [filteredCandidates, reviewPage]);

  // Reset review page when filters change
  useMemo(() => { setReviewPage(1); }, [reviewFilters]);

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
      await loadCandidates(false);
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
      if (action === "approve") {
        setMessage(`✅ 审核通过：${candidate.candidate_id}。该知识可同步到 RAG 知识库，前往 Step 4 操作。`);
      } else if (action === "reject") {
        setMessage(`✅ 已驳回：${candidate.candidate_id}`);
      } else {
        setMessage(`✅ 已打回修改：${candidate.candidate_id}`);
      }
      await loadCandidates(false);
    } catch {
      setError("审核请求失败。");
    } finally {
      setIsBusy(false);
    }
  }

  // ================================================================
  // Step 4 helpers
  // ================================================================
  async function syncRag() {
    setError("");
    setMessage("");
    setIsBusy(true);
    try {
      const response = await fetch(apiPath("/api/rag/build"), { method: "POST" });
      const body = await response.json();
      if (!response.ok || !body.success) {
        setError("同步失败，请确认已有审核通过的知识。");
        return;
      }
      setRagBuilt(true);
      setRagChunkCount(body.data.chunk_count ?? 0);
      setMessage(`✅ 已同步 ${body.data.chunk_count} 个知识块到 RAG 知识库。现在可以测试 Agent 回答。`);
      setCurrentStep(4);
    } catch {
      setError("同步请求失败。");
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
    setMessage("");
    setAgentSearched(false);
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
      const results = body.data.results || [];
      setAgentResults(results);
      setRetrievalId(body.data.retrieval_id || "");
      // Collect agent answer from results
      const answers = results.filter((r: any) => r.answer).map((r: any) => r.answer);
      setAgentAnswer(answers.length > 0 ? answers[0] : "");
      setAgentSearched(true);
      setBadCaseSubmitted(false);
      // Pre-fill bad case form
      setBadCaseForm((f) => ({
        ...f,
        user_query: searchQuery.trim(),
        agent_answer: answers.length > 0 ? answers[0] : "",
      }));
      if (results.length === 0) {
        setMessage("未命中任何知识。请先确认已有审核通过的知识，并已同步到 RAG 知识库。");
      }
    } catch {
      setError("Agent 检索请求失败。");
    } finally {
      setIsBusy(false);
    }
  }

  async function submitBadCase() {
    if (!retrievalId) {
      setError("请先执行 Agent 测试获取 retrieval_id。");
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
      setBadCaseSubmitted(true);
      setMessage(`✅ 已提交 Bad Case：${body.data.bad_case_id}，并生成待审核知识草稿，可回到 Step 3 审核。`);
    } catch {
      setError("Bad Case 提交请求失败。");
    } finally {
      setIsBusy(false);
    }
  }

  // ================================================================
  // RENDER
  // ================================================================
  return (
    <div className="p1-page">
      <div className="page-hero">
        <h1>客服文本中台</h1>
        <p>导入数据 → 清洗数据 → 生成并审核知识 → 更新知识库并测试 Agent。四个主流程，简单高效。</p>
      </div>

      <StepIndicator steps={P1_STEPS} currentStep={currentStep} />

      {error ? <div className="message error">{error}</div> : null}
      {message ? <div className="message success">{message}</div> : null}

      {/* ================================================================ */}
      {/* Step 1: 导入数据                                                    */}
      {/* ================================================================ */}
      <section className="work-step" id="step-1">
        <SectionHeader eyebrow="Step 1" title="导入数据" />
        <p className="step-desc">上传 JSON 文件、拖拽上传、使用示例数据，或粘贴 JSON 内容。导入后即可进入清洗流程。</p>

        <div
          ref={dropRef}
          className={`drop-zone ${dragOver ? "drag-over" : ""}`}
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
        >
          <span className="drop-icon">📂</span>
          <p>拖拽 JSON 文件到此处，或点击下方按钮</p>
          <div className="drop-actions">
            <input
              ref={fileInputRef}
              type="file"
              accept=".json"
              style={{ display: "none" }}
              onChange={handleFileSelect}
            />
            <button type="button" className="btn-primary" onClick={() => fileInputRef.current?.click()}>
              上传 JSON
            </button>
            <button type="button" className="btn-secondary" onClick={loadSampleData}>
              使用示例数据
            </button>
            <button type="button" className="btn-outline" onClick={() => setShowPasteArea(!showPasteArea)}>
              {showPasteArea ? "收起" : "高级粘贴 JSON"}
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

        {importResult ? (
          <div className="metric-grid" style={{ marginTop: 16 }}>
            <Metric label="批次 ID" value={importResult.batch_id} />
            <Metric label="消息数量" value={importResult.message_count} />
          </div>
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

        <div className="step-next-actions">
          <button
            type="button"
            className="btn-primary btn-lg"
            disabled={!selectedBatchId}
            onClick={() => { setCurrentStep(2); setCleaningSubTab("machine"); }}
          >
            下一步：去清洗数据 →
          </button>
        </div>
      </section>

      {/* ================================================================ */}
      {/* Step 2: 清洗数据                                                    */}
      {/* ================================================================ */}
      <section className="work-step" id="step-2">
        <SectionHeader eyebrow="Step 2" title="清洗数据" />
        <p className="step-desc">
          先执行机器清洗自动处理 PII 脱敏、去重和质量评估，然后在人工清洗工作台中逐条审核和修正。
        </p>

        {/* ---- Sub-tabs ---- */}
        <div className="sub-tabs">
          <button
            type="button"
            className={`sub-tab ${cleaningSubTab === "machine" ? "active" : ""}`}
            onClick={() => setCleaningSubTab("machine")}
          >
            A. 机器清洗
          </button>
          <button
            type="button"
            className={`sub-tab ${cleaningSubTab === "manual" ? "active" : ""}`}
            onClick={() => setCleaningSubTab("manual")}
          >
            B. 人工清洗工作台
            {sanitizedBatch ? (
              <span className="sub-tab-badge">{manualProgress.cleaned}/{manualProgress.total}</span>
            ) : null}
          </button>
        </div>

        {/* ---- A. 机器清洗 ---- */}
        {cleaningSubTab === "machine" ? (
          <div className="sub-panel">
            <RuleBox
              title="机器清洗自动完成以下操作"
              rules={[
                "PII 隐私信息自动脱敏（姓名、手机、邮箱、身份证号等）。",
                "完全重复和近重复消息自动标记。",
                "根据内容质量自动打分并给出保留/复核/丢弃建议。",
                "无意义内容、广告、噪声自动标记为建议丢弃。",
              ]}
            />

            <div style={{ margin: "16px 0" }}>
              <button
                type="button"
                className="btn-primary btn-lg"
                disabled={isBusy || !selectedBatchId}
                onClick={() => runCleaning()}
              >
                {isBusy ? "清洗中..." : "执行机器清洗"}
              </button>
            </div>

            {!cleaningJob ? (
              <div className="empty-state">
                <p className="empty-title">尚未执行机器清洗</p>
                <p className="empty-desc">请先在 Step 1 导入数据，选择批次后点击"执行机器清洗"。</p>
              </div>
            ) : (
              <>
                <div className="metric-grid">
                  <Metric label="原始消息数" value={cleaningJob.raw_message_count} />
                  <Metric label="清洗后消息数" value={cleaningJob.sanitized_message_count} />
                  <Metric label="丢弃消息数" value={cleaningJob.dropped_message_count} />
                  <Metric label="隐私脱敏命中" value={cleaningJob.pii_detected_count} />
                  <Metric label="完全重复" value={(cleaningJob as any).exact_duplicate_count || 0} />
                  <Metric label="近重复" value={(cleaningJob as any).near_duplicate_count || 0} />
                  <Metric label="低质量标记" value={(cleaningJob as any).low_quality_count || 0} />
                  <Metric label="建议复核" value={(cleaningJob as any).review_recommended_count || 0} />
                  <Metric label="建议丢弃" value={(cleaningJob as any).drop_recommended_count || 0} />
                  <Metric label="平均质量分" value={(cleaningJob as any).average_quality_score ?? 0} />
                  <Metric label="噪声标记" value={(cleaningJob as any).noise_count || 0} />
                  <Metric label="状态" value="✅ 已完成" />
                </div>

                <div className="step-next-actions">
                  <button
                    type="button"
                    className="btn-primary"
                    onClick={() => setCleaningSubTab("manual")}
                  >
                    进入人工清洗工作台 →
                  </button>
                </div>
              </>
            )}
          </div>
        ) : null}

        {/* ---- B. 人工清洗工作台 ---- */}
        {cleaningSubTab === "manual" ? (
          <div className="sub-panel">
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
                <p className="empty-desc">请先在「机器清洗」中执行清洗，数据将自动加载到此处。</p>
                <button type="button" className="btn-primary" onClick={() => setCleaningSubTab("machine")}>
                  去执行机器清洗
                </button>
              </div>
            ) : (
              <>
                {/* Progress bar */}
                <div className="progress-bar-wrap">
                  <div className="progress-bar-label">
                    处理进度：{manualProgress.cleaned} / {manualProgress.total} 条
                  </div>
                  <div className="progress-bar">
                    <div
                      className="progress-bar-fill"
                      style={{ width: `${manualProgress.total > 0 ? Math.round((manualProgress.cleaned / manualProgress.total) * 100) : 0}%` }}
                    />
                  </div>
                </div>

                {/* Search & filter bar */}
                <div className="filter-bar">
                  <input
                    className="filter-search"
                    placeholder="搜索消息内容..."
                    value={manualSearch}
                    onChange={(e) => { setManualSearch(e.target.value); setManualPage(1); }}
                  />
                  <select
                    value={manualQualityFilter}
                    onChange={(e) => { setManualQualityFilter(e.target.value as any); setManualPage(1); }}
                  >
                    <option value="all">全部质量</option>
                    <option value="high">高质量</option>
                    <option value="medium">需复核</option>
                    <option value="low">低质量</option>
                  </select>
                  <select
                    value={manualActionFilter}
                    onChange={(e) => { setManualActionFilter(e.target.value as any); setManualPage(1); }}
                  >
                    <option value="all">全部处理方式</option>
                    <option value="keep">保留</option>
                    <option value="keep_edited">修改后保留</option>
                    <option value="drop">丢弃</option>
                    <option value="needs_review">需要复核</option>
                  </select>
                </div>

                {/* Message list */}
                {manualPageMessages.length === 0 ? (
                  <div className="empty-state">
                    <p className="empty-title">没有匹配的消息</p>
                    <p className="empty-desc">请调整筛选条件或搜索关键词。</p>
                  </div>
                ) : (
                  <div className="message-list">
                    {manualPageMessages.map((item) => {
                      const edit = manualEdits[item.message_id];
                      const isExpanded = expandedMessages.has(item.message_id);
                      const isCleaned = item.manual_cleaning_status === "cleaned";

                      return (
                        <article className={`message-card ${isCleaned ? "cleaned" : ""}`} key={item.message_id}>
                          {/* Summary row — always visible */}
                          <div className="message-summary" onClick={() => toggleExpand(item.message_id)}>
                            <div className="message-summary-left">
                              <span className={`role-badge ${item.role}`}>
                                {item.role === "customer" ? "客户" : item.role === "agent" ? "客服" : "系统"}
                              </span>
                              <span className={`quality-badge ${item.quality_level}`}>
                                {qualityLabel(item.quality_level)}
                              </span>
                              <span className="suggest-badge">{suggestedActionLabel(item.suggested_action)}</span>
                              {item.pii_detected ? <span className="badge-pii">含隐私</span> : null}
                              {isCleaned ? <span className="badge-cleaned">已处理</span> : null}
                            </div>
                            <div className="message-summary-right">
                              <span className="summary-text">
                                {item.content.length > 80 ? item.content.slice(0, 80) + "..." : item.content}
                              </span>
                              <span className="expand-toggle">{isExpanded ? "▲ 收起" : "▼ 展开"}</span>
                            </div>
                          </div>

                          {/* Expanded detail — only when clicked */}
                          {isExpanded ? (
                            <div className="message-detail">
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
                                    value={edit?.content || item.content}
                                    onChange={(e) => updateManualEdit(item.message_id, { content: e.target.value })}
                                    rows={3}
                                  />
                                </label>
                                <div className="manual-controls">
                                  <label>
                                    <span>操作</span>
                                    <select
                                      value={edit?.manual_action || "keep"}
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
                                      value={edit?.cleaner || "cleaner_01"}
                                      onChange={(e) => updateManualEdit(item.message_id, { cleaner: e.target.value })}
                                    />
                                  </label>
                                  <label>
                                    <span>备注</span>
                                    <textarea
                                      rows={2}
                                      value={edit?.cleaning_note || ""}
                                      onChange={(e) => updateManualEdit(item.message_id, { cleaning_note: e.target.value })}
                                    />
                                  </label>
                                  <button type="button" className="btn-primary btn-sm" onClick={() => saveManualClean(item)} disabled={isBusy}>
                                    保存
                                  </button>
                                </div>
                              </div>
                            </div>
                          ) : null}
                        </article>
                      );
                    })}
                  </div>
                )}

                {/* Pagination */}
                {filteredManualMessages.length > MANUAL_PAGE_SIZE ? (
                  <div className="pagination">
                    <span className="pagination-info">
                      共 {filteredManualMessages.length} 条，第 {manualPage} / {manualTotalPages} 页
                    </span>
                    <div className="pagination-btns">
                      <button type="button" className="btn-small" disabled={manualPage <= 1} onClick={() => setManualPage((p) => p - 1)}>
                        上一页
                      </button>
                      {Array.from({ length: manualTotalPages }, (_, i) => i + 1)
                        .filter((p) => p === 1 || p === manualTotalPages || Math.abs(p - manualPage) <= 2)
                        .map((p, idx, arr) => (
                          <span key={p}>
                            {idx > 0 && arr[idx - 1] !== p - 1 ? <span className="pagination-ellipsis">…</span> : null}
                            <button
                              type="button"
                              className={`btn-small ${p === manualPage ? "active" : ""}`}
                              onClick={() => setManualPage(p)}
                            >
                              {p}
                            </button>
                          </span>
                        ))}
                      <button type="button" className="btn-small" disabled={manualPage >= manualTotalPages} onClick={() => setManualPage((p) => p + 1)}>
                        下一页
                      </button>
                    </div>
                  </div>
                ) : null}

                <div className="step-next-actions">
                  <button
                    type="button"
                    className="btn-primary"
                    onClick={() => { setCurrentStep(3); setKnowledgeSubTab("generate"); }}
                  >
                    下一步：生成并审核知识 →
                  </button>
                </div>
              </>
            )}
          </div>
        ) : null}
      </section>

      {/* ================================================================ */}
      {/* Step 3: 生成并审核知识                                               */}
      {/* ================================================================ */}
      <section className="work-step" id="step-3">
        <SectionHeader eyebrow="Step 3" title="生成并审核知识" />
        <p className="step-desc">
          从已清洗的数据中自动生成待审核知识，然后逐条审核：通过、驳回或打回修改。只有审核通过的知识才能进入 RAG 知识库。
        </p>

        {/* ---- Sub-tabs ---- */}
        <div className="sub-tabs">
          <button
            type="button"
            className={`sub-tab ${knowledgeSubTab === "generate" ? "active" : ""}`}
            onClick={() => setKnowledgeSubTab("generate")}
          >
            A. 生成待审核知识
          </button>
          <button
            type="button"
            className={`sub-tab ${knowledgeSubTab === "review" ? "active" : ""}`}
            onClick={() => { setKnowledgeSubTab("review"); loadCandidates(false); }}
          >
            B. 知识审核
            {candidates.length > 0 ? (
              <span className="sub-tab-badge">{reviewStatusCounts.approved}/{candidates.length}</span>
            ) : null}
          </button>
        </div>

        {/* ---- A. 生成待审核知识 ---- */}
        {knowledgeSubTab === "generate" ? (
          <div className="sub-panel">
            <RuleBox
              title="自动生成说明"
              rules={[
                "基于机器清洗后的消息自动提取 FAQ 问答对。",
                "自动识别意图分类（物流、退款、订单、商品等）。",
                "自动评估质量分和风险等级。",
                "生成的知识进入「知识审核」等待人工审核。",
              ]}
            />

            <div style={{ margin: "16px 0" }}>
              <button
                type="button"
                className="btn-primary btn-lg"
                disabled={isBusy || !sanitizedBatch}
                onClick={runExtraction}
              >
                {isBusy ? "生成中..." : "生成待审核知识"}
              </button>
              {!sanitizedBatch ? (
                <p className="hint-text">请先在 Step 2 完成机器清洗。</p>
              ) : null}
            </div>

            {extractionResult ? (
              <div className="metric-grid">
                <Metric label="生成数量" value={extractionResult.candidate_count} />
                <Metric label="状态" value="✅ 已完成" />
              </div>
            ) : (
              <div className="empty-state">
                <p className="empty-title">尚未生成待审核知识</p>
                <p className="empty-desc">点击上方按钮从已清洗数据中自动生成知识候选。</p>
              </div>
            )}

            <div className="step-next-actions">
              <button
                type="button"
                className="btn-primary"
                disabled={!extractionResult}
                onClick={() => { setKnowledgeSubTab("review"); loadCandidates(false); }}
              >
                进入知识审核 →
              </button>
            </div>
          </div>
        ) : null}

        {/* ---- B. 知识审核 ---- */}
        {knowledgeSubTab === "review" ? (
          <div className="sub-panel">
            <RuleBox
              title="审核规则提示"
              rules={[
                "回答必须准确、可执行、无隐私。",
                "高风险规则谨慎处理，不能轻易承诺退款、赔偿、法律或支付结论。",
                "禁答内容不能作为普通 FAQ 进入 RAG。",
                "转人工规则要保留，尤其是支付风险、物流异常、政策不确定场景。",
                "不确定内容打回修改；只有已通过才能进入 RAG。",
              ]}
            />

            {/* Status statistics */}
            {candidates.length > 0 ? (
              <div className="status-stats">
                <span className="stat-item stat-pending">待审核：{reviewStatusCounts.pending_review}</span>
                <span className="stat-item stat-approved">已通过：{reviewStatusCounts.approved}</span>
                <span className="stat-item stat-rejected">已驳回：{reviewStatusCounts.rejected}</span>
                <span className="stat-item stat-revision">打回修改：{reviewStatusCounts.needs_revision}</span>
                <span className="stat-item stat-total">总计：{candidates.length}</span>
              </div>
            ) : null}

            {/* Filter */}
            <div className="filter-grid">
              <label>
                <span>审核状态</span>
                <select
                  value={reviewFilters.status}
                  onChange={(e) => setReviewFilters((c) => ({ ...c, status: e.target.value as any }))}
                >
                  <option value="all">全部</option>
                  <option value="pending_review">待审核</option>
                  <option value="approved">已通过</option>
                  <option value="rejected">已驳回</option>
                  <option value="needs_revision">打回修改</option>
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
              当前显示 {filteredCandidates.length} 条 / 全部 {candidates.length} 条
            </div>

            {reviewPageCandidates.length === 0 ? (
              <div className="empty-state">
                <p className="empty-title">没有符合筛选条件的候选知识</p>
                <p className="empty-desc">请先在「生成待审核知识」中生成知识，或调整筛选条件。</p>
                <button type="button" className="btn-primary" onClick={() => setKnowledgeSubTab("generate")}>
                  去生成待审核知识
                </button>
              </div>
            ) : (
              <div className="candidate-list">
                {reviewPageCandidates.map((candidate) => {
                  const edit = candidateEdits[candidate.candidate_id] || toCandidateEdit(candidate);
                  const decision = reviewDecisions[candidate.candidate_id] || { reviewer: "reviewer_01", review_note: "" };
                  const lvl = qualityLevel(candidate.quality_score);
                  const st = candidate.source_type || "unknown";

                  return (
                    <article className="candidate-card" key={candidate.candidate_id}>
                      <div className="candidate-meta">
                        <span className={`review-badge ${candidate.review_status}`}>
                          {reviewStatusLabels[candidate.review_status]}
                        </span>
                        <span>{sourceTypeLabels[st]}</span>
                        <span>{riskLabels[candidate.risk_level]}</span>
                        <span className={`quality-badge ${lvl}`}>{qualityLabel(lvl)} / {candidate.quality_score}</span>
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
                })}
              </div>
            )}

            {/* Pagination */}
            {filteredCandidates.length > REVIEW_PAGE_SIZE ? (
              <div className="pagination">
                <span className="pagination-info">
                  共 {filteredCandidates.length} 条，第 {reviewPage} / {reviewTotalPages} 页
                </span>
                <div className="pagination-btns">
                  <button type="button" className="btn-small" disabled={reviewPage <= 1} onClick={() => setReviewPage((p) => p - 1)}>
                    上一页
                  </button>
                  {Array.from({ length: reviewTotalPages }, (_, i) => i + 1)
                    .filter((p) => p === 1 || p === reviewTotalPages || Math.abs(p - reviewPage) <= 2)
                    .map((p, idx, arr) => (
                      <span key={p}>
                        {idx > 0 && arr[idx - 1] !== p - 1 ? <span className="pagination-ellipsis">…</span> : null}
                        <button
                          type="button"
                          className={`btn-small ${p === reviewPage ? "active" : ""}`}
                          onClick={() => setReviewPage(p)}
                        >
                          {p}
                        </button>
                      </span>
                    ))}
                  <button type="button" className="btn-small" disabled={reviewPage >= reviewTotalPages} onClick={() => setReviewPage((p) => p + 1)}>
                    下一页
                  </button>
                </div>
              </div>
            ) : null}

            <div className="step-next-actions">
              <button
                type="button"
                className="btn-primary"
                disabled={reviewStatusCounts.approved === 0}
                onClick={() => setCurrentStep(4)}
              >
                下一步：更新知识库并测试 Agent →
              </button>
              {reviewStatusCounts.approved === 0 ? (
                <span className="hint-text" style={{ alignSelf: "center" }}>请先审核通过至少一条知识。</span>
              ) : null}
            </div>
          </div>
        ) : null}
      </section>

      {/* ================================================================ */}
      {/* Step 4: 更新知识库并测试 Agent                                        */}
      {/* ================================================================ */}
      <section className="work-step" id="step-4">
        <SectionHeader eyebrow="Step 4" title="更新知识库并测试 Agent" />
        <p className="step-desc">
          将已审核通过的知识同步到 RAG 知识库，然后测试 Agent 回答效果。如发现回答不理想，可提交 Bad Case 回流改进。
        </p>

        {/* ---- A. 同步已审核知识到 RAG 知识库 ---- */}
        <div className="sub-section">
          <h3 className="sub-section-title">A. 同步已审核知识到 RAG 知识库</h3>
          <p className="sub-section-desc">
            将 Step 3 中所有「已通过」的知识同步到同一个 RAG 知识库中。这不是新建知识库，而是增量更新已有知识库。
          </p>

          {!ragBuilt ? (
            <div style={{ margin: "12px 0" }}>
              <button
                type="button"
                className="btn-primary btn-lg"
                disabled={isBusy || reviewStatusCounts.approved === 0}
                onClick={syncRag}
              >
                {isBusy ? "同步中..." : "同步已审核知识到 RAG 知识库"}
              </button>
              {reviewStatusCounts.approved === 0 ? (
                <p className="hint-text">暂无可同步的知识，请先在 Step 3 审核通过知识。</p>
              ) : (
                <p className="hint-text">当前有 {reviewStatusCounts.approved} 条已审核通过的知识可供同步。</p>
              )}
            </div>
          ) : (
            <div className="metric-grid">
              <Metric label="已同步知识块" value={ragChunkCount} />
              <Metric label="状态" value="✅ 已同步" />
            </div>
          )}
        </div>

        {/* ---- B. 测试 Agent 回答 ---- */}
        <div className="sub-section">
          <h3 className="sub-section-title">B. 测试 Agent 回答</h3>
          <p className="sub-section-desc">
            输入客户问题，测试 Agent 是否能从 RAG 知识库中检索到正确的知识并生成回答。
          </p>

          <div className="search-box">
            <div className="search-row">
              <input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="例如：发货到德国需要多长时间？"
                onKeyDown={(e) => { if (e.key === "Enter") agentRetrieve(); }}
              />
              <button type="button" className="btn-primary" onClick={agentRetrieve} disabled={isBusy}>
                {isBusy ? "检索中..." : "测试 Agent 回答"}
              </button>
            </div>
          </div>

          {/* Agent test result panel */}
          {agentSearched ? (
            agentResults.length === 0 ? (
              <div className="empty-state">
                <p className="empty-title">未命中任何知识</p>
                <p className="empty-desc">
                  请先确认已有审核通过的知识，并已同步到 RAG 知识库。如果已同步但仍未命中，可能是问题与知识库内容不匹配。
                </p>
              </div>
            ) : (
              <div className="agent-result-panel">
                <div className="agent-result-header">
                  <span className="agent-result-badge">
                    命中 {agentResults.length} 条知识
                  </span>
                  {retrievalId ? (
                    <span className="agent-result-id">
                      Retrieval ID: <code>{retrievalId}</code>
                    </span>
                  ) : null}
                </div>

                {agentAnswer ? (
                  <div className="agent-answer-box">
                    <strong>Agent 回答：</strong>
                    <p>{agentAnswer}</p>
                  </div>
                ) : null}

                <div className="search-results">
                  <h3>引用来源（{agentResults.length} 条）</h3>
                  {agentResults.map((r, idx) => (
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
              </div>
            )
          ) : null}

          {/* ---- C. 提交 Bad Case ---- */}
          {retrievalId ? (
            <div className="sub-section">
              <h3 className="sub-section-title">C. 提交 Bad Case</h3>
              <p className="sub-section-desc">
                如果 Agent 返回的结果不理想，请提交 Bad Case。提交后将自动生成待审核知识草稿，可回到 Step 3 审核。
              </p>

              {badCaseSubmitted ? (
                <div className="message success">
                  ✅ Bad Case 已提交，并生成待审核知识草稿。
                  <button
                    type="button"
                    className="btn-primary btn-sm"
                    style={{ marginLeft: 12 }}
                    onClick={() => { setCurrentStep(3); setKnowledgeSubTab("review"); loadCandidates(false); }}
                  >
                    回到 Step 3 审核
                  </button>
                </div>
              ) : (
                <div className="bad-case-form">
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
              )}
            </div>
          ) : null}
        </div>
      </section>
    </div>
  );
}
