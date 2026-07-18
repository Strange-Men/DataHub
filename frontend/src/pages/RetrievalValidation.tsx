import { FormEvent, useMemo, useState } from "react";
import { apiFetch, apiPath } from "../api";
import { useAuth } from "../auth/AuthContext";
import { ModeSwitch } from "../components/ModeSwitch";
import { apiErrorMessage, can, FORBIDDEN_MESSAGE, type FrontendPermission } from "../governance";

type RetrievalKind = "p1" | "p2" | "unified" | "agent";

type Answerability = {
  answerable: boolean;
  no_answer_reason: string;
  decision_score?: number | null;
  decision_threshold?: number | null;
  valid_evidence_count: number;
  mode: "disabled" | "shadow" | "enforced";
  abstention_enforced: boolean;
};

const NO_ANSWER_REASON_LABELS: Record<string, string> = {
  ANSWERABLE: "证据可靠，可以回答",
  NO_EVIDENCE: "未找到相关知识",
  LOW_RELEVANCE: "检索结果相关性不足",
  INSUFFICIENT_EVIDENCE: "有效证据不足",
  CONFLICTING_EVIDENCE: "检索证据存在冲突",
  ALL_CANDIDATES_FILTERED: "候选知识未通过治理可见性检查",
  QUERY_TOO_AMBIGUOUS: "当前问题信息不足",
  RETRIEVAL_UNAVAILABLE: "检索服务暂时不可用",
};

const KIND_CONFIG: Record<RetrievalKind, { label: string; permission: FrontendPermission; description: string }> = {
  p1: { label: "P1 文本检索", permission: "retrieval.p1", description: "验证已经审核并同步的 P1 文本知识。" },
  p2: { label: "P2 多模态检索", permission: "retrieval.p2", description: "验证已经开放检索的 P2 多模态知识。" },
  unified: { label: "联合检索", permission: "retrieval.unified", description: "同时观察 P1 与 P2 的召回和融合结果。" },
  agent: { label: "客服 Agent", permission: "agent.customerops", description: "验证客服 Agent 的证据引用、降级和安全拒答；默认保持 P1-only。" },
};

function resultItems(body: any): any[] {
  if (Array.isArray(body?.results)) return body.results;
  if (Array.isArray(body?.data?.results)) return body.data.results;
  return [];
}

function answerabilityOf(body: any): Answerability | null {
  return body?.answerability || body?.data?.answerability || null;
}

function sourceTrace(item: any): string {
  const trace = item?.source_trace;
  if (!trace || typeof trace !== "object") return "暂无来源链";
  const ordered = [
    ["知识资产", trace.knowledge_asset_id],
    ["知识快照", trace.snapshot_id],
    ["人工审核", trace.review_id],
    ["内容解析", trace.extraction_id],
    ["原始素材", trace.asset_id],
  ].filter(([, value]) => value);
  return ordered.length ? ordered.map(([label, value]) => `${label}: ${value}`).join(" → ") : "来源链已返回";
}

export function RetrievalValidation() {
  const { role } = useAuth();
  const [kind, setKind] = useState<RetrievalKind>("p1");
  const [query, setQuery] = useState("");
  const [agentUnified, setAgentUnified] = useState(false);
  const [activeUnified, setActiveUnified] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [response, setResponse] = useState<any>(null);
  const config = KIND_CONFIG[kind];
  const allowed = can(role, config.permission);
  const results = useMemo(() => resultItems(response), [response]);
  const answerability = useMemo(() => answerabilityOf(response), [response]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!allowed) {
      setError(FORBIDDEN_MESSAGE);
      return;
    }
    if (!query.trim()) {
      setError("请输入检索问题。");
      return;
    }
    setBusy(true);
    setError("");
    setResponse(null);
    try {
      let path = "/api/rag/search";
      let payload: Record<string, unknown> = { query: query.trim(), top_k: 5 };
      let headers: HeadersInit = { "Content-Type": "application/json" };
      if (kind === "p2") path = "/api/v2/retrieval/p2/search";
      if (kind === "unified") {
        path = "/api/v2/retrieval/search";
        payload = {
          ...payload,
          sources: ["p1", "p2"],
          fusion_enabled: true,
          shadow_mode: !activeUnified,
          include_archived: false,
        };
      }
      if (kind === "agent") {
        path = "/api/v2/customer-ops-agent/retrieve";
        payload = { ...payload, retrieval_strategy: agentUnified ? "unified" : "p1" };
        headers = { ...headers, "X-DataHub-Client": "frontend-governance" };
      }
      const apiResponse = await apiFetch(apiPath(path), {
        method: "POST",
        headers,
        body: JSON.stringify(payload),
      });
      const body = await apiResponse.json();
      if (!apiResponse.ok) throw new Error(apiErrorMessage(body, apiResponse.status, "检索失败，请稍后重试。"));
      setResponse(body);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "检索失败，请稍后重试。");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="retrieval-page">
      <div className="page-hero">
        <h1>检索与 Agent 验证</h1>
        <p>验证 P1、P2、联合检索和客服 Agent 的召回、引用与安全拒答效果；不会显示完整向量或内部连接信息。</p>
      </div>

      <div className="workflow-tabs retrieval-tabs" role="tablist" aria-label="验证类型">
        {(Object.keys(KIND_CONFIG) as RetrievalKind[]).map((item) => (
          <button
            key={item}
            type="button"
            className={`retrieval-tab ${kind === item ? "active" : ""}`}
            aria-selected={kind === item}
            onClick={() => { setKind(item); setResponse(null); setError(""); }}
          >
            {KIND_CONFIG[item].label}
          </button>
        ))}
      </div>

      <section className="material-panel">
        <div className="material-panel-header">
          <div><h2>{config.label}</h2><p>{config.description}</p></div>
        </div>
        {!allowed && <div className="feedback warning">{FORBIDDEN_MESSAGE}</div>}
        <form className="retrieval-form" onSubmit={submit}>
          <label className="retrieval-query-field">
            <span>验证问题</span>
            <textarea value={query} onChange={(event) => setQuery(event.target.value)} rows={2} maxLength={500} placeholder="输入希望验证的业务问题" />
            <small>{query.length}/500</small>
          </label>
          {kind === "unified" && (
            <ModeSwitch
              checked={activeUnified}
              onChange={setActiveUnified}
              title="使用联合检索结果"
              offDescription="仅观察 P1/P2 联合召回，不影响最终结果。"
              onDescription="使用联合检索结果作为本次验证结果。"
            />
          )}
          {kind === "agent" && (
            <ModeSwitch
              checked={agentUnified}
              onChange={setAgentUnified}
              title="使用联合检索策略"
              offDescription="客服 Agent 保持默认 P1-only。"
              onDescription="本次请求显式使用联合检索策略。"
              offLabel="P1-only"
              onLabel="Opt-in"
            />
          )}
          <div className="retrieval-submit-row">
            <span>{!query.trim() ? "输入问题后即可开始验证" : "将调用真实接口并返回可追踪证据"}</span>
            <button className="btn-primary" type="submit" disabled={busy || !allowed || !query.trim()} title={!allowed ? FORBIDDEN_MESSAGE : undefined}>
            {busy ? "检索中，请勿重复提交..." : "开始验证"}
            </button>
          </div>
        </form>
      </section>

      {error && <div className="feedback error" role="alert">{error}</div>}
      {response && (
        <section className="material-panel retrieval-results">
          <div className="result-summary">
            <span>模式：<strong>{response.retrieval_mode || response.data?.retrieval_mode || "unknown"}</strong></span>
            <span>结果：<strong>{results.length}</strong></span>
            <span>是否降级：<strong>{(response.fallback_used ?? response.data?.fallback_used ?? false) ? "是" : "否"}</strong></span>
            {(response.fallback_reason || response.data?.fallback_reason) && <span>原因：{response.fallback_reason || response.data?.fallback_reason}</span>}
          </div>
          {answerability && (
            <div
              className={`feedback ${answerability.answerable ? "success" : answerability.no_answer_reason === "RETRIEVAL_UNAVAILABLE" ? "error" : "warning"}`}
              role="status"
            >
              <strong>{answerability.answerable ? "可以回答" : "暂不回答"}</strong>
              <span>：{NO_ANSWER_REASON_LABELS[answerability.no_answer_reason] || "当前证据无法支持可靠回答"}</span>
              <div>
                有效证据 {answerability.valid_evidence_count} 条；判定阈值 {answerability.decision_threshold ?? "未设置"}；
                门禁模式 {answerability.mode === "enforced" ? "已启用" : answerability.mode === "shadow" ? "影子观察" : "兼容关闭"}
              </div>
              {answerability.no_answer_reason === "RETRIEVAL_UNAVAILABLE" && (
                <small>这是系统故障，不代表知识库确认没有答案，请稍后重试。</small>
              )}
            </div>
          )}
          {(response.abstention_message || response.data?.abstention_message) && (
            <div className="empty-state">
              <p className="empty-title">{response.abstention_message || response.data?.abstention_message}</p>
              <p className="empty-desc">系统未引用低相关证据，也不会编造来源。</p>
            </div>
          )}
          {results.length === 0 ? (
            <div className="empty-state"><p className="empty-title">未检索到已治理且可见的知识</p><p className="empty-desc">请确认内容已审核、同步或进入 serving 状态。</p></div>
          ) : results.map((item, index) => (
            <article className="retrieval-result-card" key={item.chunk_id || item.candidate_id || index}>
              <div className="review-card-meta">
                <span>#{item.rank || index + 1} · {item.source_index || item.source_type || "p1"}</span>
                <span>相关分 {Number(item.fused_score ?? item.score ?? item.original_score ?? 0).toFixed(4)}</span>
              </div>
              <p>{item.evidence_text || item.chunk_text || item.answer || "已返回证据"}</p>
              <small>{sourceTrace(item)}</small>
            </article>
          ))}
        </section>
      )}
    </div>
  );
}
