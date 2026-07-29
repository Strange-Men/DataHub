import { useState } from "react";
import type { AuthRole } from "../../api";
import { can, permissionHint } from "../../governance";
import {
  P3_ELIGIBILITY_REASON_LABELS,
  P3_SOURCE_TYPE_LABELS,
  shortHash,
} from "../presentation";
import type {
  P3EligibilitySourceType,
  P3Project,
  P3SourceEligibilityDecision,
  P3SourceEligibilityInput,
} from "../types";

const SOURCE_OPTIONS: Array<{ value: P3EligibilitySourceType; label: string }> = [
  { value: "P1_KNOWLEDGE", label: P3_SOURCE_TYPE_LABELS.P1_KNOWLEDGE },
  { value: "P2_KNOWLEDGE_ASSET", label: P3_SOURCE_TYPE_LABELS.P2_KNOWLEDGE_ASSET },
  {
    value: "APPROVED_BAD_CASE_CORRECTION",
    label: P3_SOURCE_TYPE_LABELS.APPROVED_BAD_CASE_CORRECTION,
  },
  { value: "RAW_BAD_CASE", label: "原始 Bad Case（仅用于确认不可复用）" },
];

export function SourceEligibilityForm({
  role,
  project,
  decision,
  checking,
  mutating,
  onCheck,
  onAdd,
}: {
  role: AuthRole | null;
  project: P3Project;
  decision: P3SourceEligibilityDecision | null;
  checking: boolean;
  mutating: boolean;
  onCheck: (input: P3SourceEligibilityInput) => Promise<P3SourceEligibilityDecision | null>;
  onAdd: () => Promise<unknown>;
}) {
  const [sourceType, setSourceType] = useState<P3EligibilitySourceType>("P1_KNOWLEDGE");
  const [sourceId, setSourceId] = useState("");
  const [sourceVersion, setSourceVersion] = useState("");
  const [fieldError, setFieldError] = useState("");
  const frozen = project.status !== "draft";
  const canManage = can(role, "p3.source.manage") && !frozen;
  const decisionMatchesInput = Boolean(
    decision
    && decision.source_type === sourceType
    && decision.source_id === sourceId.trim()
    && (!sourceVersion || decision.source_version === Number(sourceVersion)),
  );

  async function check(event: React.FormEvent) {
    event.preventDefault();
    const normalizedId = sourceId.trim();
    if (!normalizedId) {
      setFieldError("请填写来源 ID。");
      return;
    }
    await onCheck({
      source_type: sourceType,
      source_id: normalizedId,
      source_version: sourceVersion ? Number(sourceVersion) : undefined,
    });
  }

  return (
    <section className="p3-source-eligibility" aria-labelledby="p3-source-eligibility-title">
      <div className="p3-section-heading">
        <div>
          <span className="p3-stage-label">第 2 阶段</span>
          <h2 id="p3-source-eligibility-title">检查治理来源</h2>
          <p>状态由后端资格内核从真实治理记录判断，不能由前端声明。</p>
        </div>
        {frozen && (
          <span className="p3-status-chip warning">
            {project.status === "active" ? "项目已激活，来源选择已冻结" : "归档项目只读"}
          </span>
        )}
      </div>

      <form className="p3-source-check-form" onSubmit={check}>
        <label>
          <span>来源类型</span>
          <select
            value={sourceType}
            disabled={!canManage || checking}
            onChange={(event) => setSourceType(event.target.value as P3EligibilitySourceType)}
          >
            {SOURCE_OPTIONS.map((option) => (
              <option value={option.value} key={option.value}>{option.label}</option>
            ))}
          </select>
        </label>
        <label>
          <span>来源 ID</span>
          <input
            value={sourceId}
            required
            maxLength={200}
            disabled={!canManage || checking}
            aria-invalid={Boolean(fieldError)}
            aria-describedby={fieldError ? "p3-source-id-error" : undefined}
            placeholder="输入治理系统中的来源编号"
            onChange={(event) => {
              setSourceId(event.target.value);
              setFieldError("");
            }}
          />
        </label>
        <label>
          <span>来源版本（可选）</span>
          <input
            value={sourceVersion}
            type="number"
            min={1}
            step={1}
            disabled={!canManage || checking}
            placeholder="默认检查当前版本"
            onChange={(event) => setSourceVersion(event.target.value)}
          />
        </label>
        <button
          type="submit"
          className="btn-primary"
          disabled={!canManage || checking || !sourceId.trim()}
          title={permissionHint(role, "p3.source.manage")}
        >
          {checking ? "正在检查…" : "检查是否可用"}
        </button>
        {fieldError && <p id="p3-source-id-error" className="p3-field-error">{fieldError}</p>}
      </form>

      {decision && decisionMatchesInput && (
        <div className={`p3-eligibility-result ${decision.eligible ? "eligible" : "ineligible"}`} role="status">
          <div>
            <span aria-hidden="true">{decision.eligible ? "✓" : "!"}</span>
            <div>
              <strong>
                {P3_ELIGIBILITY_REASON_LABELS[decision.reason_code]}
              </strong>
              <p>
                {decision.eligible
                  ? `审核证据完整，来源指纹 ${shortHash(decision.content_fingerprint)}。`
                  : "此来源不会加入项目，已保存的项目来源不受影响。"}
              </p>
            </div>
          </div>
          {decision.eligible && (
            <button
              type="button"
              className="btn-primary"
              disabled={!canManage || mutating}
              onClick={() => void onAdd()}
            >
              {mutating ? "正在添加…" : "添加到项目"}
            </button>
          )}
          <details className="p3-inline-technical">
            <summary>技术详情</summary>
            <dl>
              <div><dt>reason_code</dt><dd>{decision.reason_code}</dd></div>
              <div><dt>policy_version</dt><dd>{decision.policy_version}</dd></div>
              <div><dt>source_version</dt><dd>{decision.source_version ?? "当前版本"}</dd></div>
              <div><dt>lineage_complete</dt><dd>{String(decision.lineage_complete)}</dd></div>
            </dl>
          </details>
        </div>
      )}
    </section>
  );
}
