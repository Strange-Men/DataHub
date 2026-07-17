import { FormEvent, useMemo, useState } from "react";
import { apiFetch, apiPath } from "../api";
import { useAuth } from "../auth/AuthContext";
import { apiErrorMessage, can, FORBIDDEN_MESSAGE, type FrontendPermission } from "../governance";

type RetrievalKind = "p1" | "p2" | "unified" | "agent";

const KIND_CONFIG: Record<RetrievalKind, { label: string; permission: FrontendPermission; description: string }> = {
  p1: { label: "P1 Retrieval", permission: "retrieval.p1", description: "只检索已审核并同步的 P1 文本知识。" },
  p2: { label: "P2 Retrieval", permission: "retrieval.p2", description: "只检索 serving 状态的 P2 向量知识。" },
  unified: { label: "Unified Retrieval", permission: "retrieval.unified", description: "显式调用 P1/P2 统一检索；默认保持 Shadow。" },
  agent: { label: "CustomerOpsAgent", permission: "agent.customerops", description: "默认 P1-only；Unified 必须在下方显式选择。" },
};

function resultItems(body: any): any[] {
  if (Array.isArray(body?.results)) return body.results;
  if (Array.isArray(body?.data?.results)) return body.data.results;
  return [];
}

function sourceTrace(item: any): string {
  const trace = item?.source_trace;
  if (!trace || typeof trace !== "object") return "暂无来源链";
  const ordered = [
    ["Knowledge Asset", trace.knowledge_asset_id],
    ["Snapshot", trace.snapshot_id],
    ["Review", trace.review_id],
    ["Extraction", trace.extraction_id],
    ["Asset", trace.asset_id],
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
        <h1>检索验证</h1>
        <p>使用真实服务验证 P1、P2、Unified 与 CustomerOpsAgent；页面不会显示完整向量或内部连接信息。</p>
      </div>

      <div className="workflow-tabs" role="tablist" aria-label="检索类型">
        {(Object.keys(KIND_CONFIG) as RetrievalKind[]).map((item) => (
          <button
            key={item}
            type="button"
            className={kind === item ? "btn-primary" : "btn-secondary"}
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
          <label>
            检索问题
            <textarea value={query} onChange={(event) => setQuery(event.target.value)} rows={3} maxLength={500} placeholder="请输入要验证的问题" />
          </label>
          {kind === "unified" && (
            <label className="option-row">
              <input type="checkbox" checked={activeUnified} onChange={(event) => setActiveUnified(event.target.checked)} />
              主动使用 Unified 结果（未勾选时保持 Shadow）
            </label>
          )}
          {kind === "agent" && (
            <label className="option-row">
              <input type="checkbox" checked={agentUnified} onChange={(event) => setAgentUnified(event.target.checked)} />
              显式 opt-in Unified（默认 CustomerOpsAgent 为 P1-only）
            </label>
          )}
          <button className="btn-primary" type="submit" disabled={busy || !allowed || !query.trim()} title={!allowed ? FORBIDDEN_MESSAGE : undefined}>
            {busy ? "检索中，请勿重复提交..." : "开始验证"}
          </button>
        </form>
      </section>

      {error && <div className="feedback error" role="alert">{error}</div>}
      {response && (
        <section className="material-panel retrieval-results">
          <div className="result-summary">
            <span>模式：<strong>{response.retrieval_mode || response.data?.retrieval_mode || "unknown"}</strong></span>
            <span>结果：<strong>{results.length}</strong></span>
            <span>Fallback：<strong>{String(response.fallback_used ?? response.data?.fallback_used ?? false)}</strong></span>
            {(response.fallback_reason || response.data?.fallback_reason) && <span>原因：{response.fallback_reason || response.data?.fallback_reason}</span>}
          </div>
          {results.length === 0 ? (
            <div className="empty-state"><p className="empty-title">未检索到已治理且可见的知识</p><p className="empty-desc">请确认内容已审核、同步或进入 serving 状态。</p></div>
          ) : results.map((item, index) => (
            <article className="retrieval-result-card" key={item.chunk_id || item.candidate_id || index}>
              <div className="review-card-meta">
                <span>#{item.rank || index + 1} · {item.source_index || item.source_type || "p1"}</span>
                <span>score {Number(item.fused_score ?? item.score ?? item.original_score ?? 0).toFixed(4)}</span>
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
