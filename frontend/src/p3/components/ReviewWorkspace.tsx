import { useEffect, useRef, useState } from "react";
import type { AuthRole } from "../../api";
import { can, permissionHint, ROLE_LABELS } from "../../governance";
import { createP3IdempotencyKey } from "../idempotency";
import {
  P3_ASSET_STATUS_LABELS,
  P3_REVIEW_DECISION_LABELS,
  shortHash,
} from "../presentation";
import type {
  P3AssetSourceSnapshot,
  P3AssetVersion,
  P3Review,
  P3ReviewChecklist,
  P3ReviewDecision,
} from "../types";
import { ConfirmDialog } from "./ConfirmDialog";

const CHECKLIST_ITEMS: Array<{
  key: keyof P3ReviewChecklist;
  label: string;
  help: string;
}> = [
  { key: "structure_complete", label: "内容结构完整", help: "必填章节和字段已经完成" },
  { key: "source_refs_valid", label: "来源引用有效", help: "引用均来自当前不可变 Snapshot" },
  {
    key: "no_unsupported_claims_confirmed",
    label: "未发现无依据承诺",
    help: "事实与承诺能够由来源证明",
  },
  { key: "safe_for_reuse", label: "适合后续复用", help: "内容适合发布为企业复用资产" },
];

const EMPTY_CHECKLIST: P3ReviewChecklist = {
  structure_complete: false,
  source_refs_valid: false,
  no_unsupported_claims_confirmed: false,
  safe_for_reuse: false,
};

export function ReviewWorkspace({
  role,
  asset,
  sources,
  review,
  history,
  busy,
  onSubmit,
  onDecide,
}: {
  role: AuthRole | null;
  asset: P3AssetVersion;
  sources: P3AssetSourceSnapshot[];
  review: P3Review | null;
  history: P3Review[];
  busy: boolean;
  onSubmit: (idempotencyKey: string) => Promise<P3AssetVersion | null>;
  onDecide: (input: {
    decision: P3ReviewDecision;
    comments?: string | null;
    checklist: P3ReviewChecklist;
    idempotencyKey: string;
  }) => Promise<P3Review | null>;
}) {
  const [checklist, setChecklist] = useState<P3ReviewChecklist>(EMPTY_CHECKLIST);
  const [decision, setDecision] = useState<P3ReviewDecision>("approved");
  const [comments, setComments] = useState("");
  const [validation, setValidation] = useState("");
  const [confirmDecision, setConfirmDecision] = useState(false);
  const submitKey = useRef(createP3IdempotencyKey("submit-review"));
  const decisionKey = useRef(createP3IdempotencyKey("review-decision"));
  const canSubmit = can(role, "p3.asset.submit_review");
  const canDecide = can(role, "p3.review.decide");
  const allChecked = Object.values(checklist).every(Boolean);

  useEffect(() => {
    setChecklist(EMPTY_CHECKLIST);
    setDecision("approved");
    setComments("");
    setValidation("");
    setConfirmDecision(false);
    submitKey.current = createP3IdempotencyKey("submit-review");
    decisionKey.current = createP3IdempotencyKey("review-decision");
  }, [asset.id]);

  async function submit() {
    const completed = await onSubmit(submitKey.current);
    if (completed) submitKey.current = createP3IdempotencyKey("submit-review");
  }

  function prepareDecision() {
    if (decision === "approved" && !allChecked) {
      setValidation("批准前必须完成全部四项审核检查。");
      return;
    }
    if (decision !== "approved" && !comments.trim()) {
      setValidation("退回修改或拒绝时必须填写审核意见。");
      return;
    }
    setValidation("");
    setConfirmDecision(true);
  }

  async function decide() {
    const completed = await onDecide({
      decision,
      comments: comments.trim() || null,
      checklist,
      idempotencyKey: decisionKey.current,
    });
    if (completed) decisionKey.current = createP3IdempotencyKey("review-decision");
    setConfirmDecision(false);
  }

  const selectedHistory = history.filter((item) => item.asset_version_id === asset.id);
  if (review && !selectedHistory.some((item) => item.id === review.id)) {
    selectedHistory.unshift(review);
  }

  return (
    <section className="p3-review-workspace" aria-labelledby="p3-review-title">
      <div className="p3-section-heading">
        <div>
          <span className="p3-stage-label">第 4 阶段</span>
          <h2 id="p3-review-title">提交与人工审核</h2>
          <p>批准是发布的前置条件，但批准本身不会让内容成为正式资产。</p>
        </div>
        <span className={`p3-status-chip ${asset.status}`}>
          {P3_ASSET_STATUS_LABELS[asset.status]}
        </span>
      </div>

      {asset.status === "generated" && (
        <div className="p3-submit-review-panel">
          <ul className="p3-activation-checks">
            <li className="passed"><span aria-hidden="true">✓</span>内容结构已生成
              <small>提交时由后端再次校验 Schema</small></li>
            <li className={sources.length ? "passed" : "blocked"}>
              <span aria-hidden="true">{sources.length ? "✓" : "!"}</span>来源引用已固化
              <small>{sources.length} 个来源快照</small></li>
            <li className="passed"><span aria-hidden="true">✓</span>来源状态重新确认
              <small>后端提交门禁是最终判断依据</small></li>
          </ul>
          <div className="p3-primary-action-row">
            <div>
              <strong>提交后当前版本将锁定</strong>
              <p>如需修改，审核员退回后会基于此版本创建新修订。</p>
            </div>
            <button
              type="button"
              className="btn-primary"
              disabled={!canSubmit || busy || sources.length === 0}
              title={permissionHint(role, "p3.asset.submit_review")}
              onClick={() => void submit()}
            >
              {busy ? "正在提交…" : "提交审核"}
            </button>
          </div>
        </div>
      )}

      {asset.status === "pending_review" && (
        <>
          <div className="p3-feedback neutral" role="status">
            <strong>当前版本正在等待人工审核，编辑已禁用。</strong>
            <span>{canDecide ? "请完成审核检查并作出决定。" : "你可以查看内容和后续审核结果。"}</span>
          </div>
          {canDecide && (
            <div className="p3-review-decision-panel">
              <fieldset className="p3-review-checklist">
                <legend>审核检查</legend>
                {CHECKLIST_ITEMS.map((item) => (
                  <div className="p3-filter-switch" key={item.key}>
                    <span><strong>{item.label}</strong><small>{item.help}</small></span>
                    <button
                      type="button"
                      role="switch"
                      className="compact-switch"
                      aria-checked={checklist[item.key]}
                      aria-label={item.label}
                      onClick={() => {
                        setChecklist((current) => ({
                          ...current,
                          [item.key]: !current[item.key],
                        }));
                        setValidation("");
                        decisionKey.current = createP3IdempotencyKey("review-decision");
                      }}
                    ><span /></button>
                  </div>
                ))}
              </fieldset>

              <fieldset className="p3-review-decisions">
                <legend>审核决定</legend>
                {(["approved", "needs_revision", "rejected"] as const).map((value) => (
                  <label className={decision === value ? "selected" : ""} key={value}>
                    <input
                      type="radio"
                      name="p3-review-decision"
                      value={value}
                      checked={decision === value}
                      onChange={() => {
                        setDecision(value);
                        setValidation("");
                        decisionKey.current = createP3IdempotencyKey("review-decision");
                      }}
                    />
                    <span>{P3_REVIEW_DECISION_LABELS[value]}</span>
                  </label>
                ))}
              </fieldset>

              <label className="p3-review-comments">
                <span>审核意见{decision === "approved" ? "（可选）" : "（必填）"}</span>
                <textarea
                  rows={4}
                  value={comments}
                  maxLength={10_000}
                  aria-invalid={Boolean(validation)}
                  aria-describedby={validation ? "p3-review-validation" : undefined}
                  onChange={(event) => {
                    setComments(event.target.value);
                    setValidation("");
                    decisionKey.current = createP3IdempotencyKey("review-decision");
                  }}
                  placeholder={
                    decision === "approved"
                      ? "可记录批准说明"
                      : "说明需要修改或拒绝的具体原因"
                  }
                />
              </label>
              {validation && <p id="p3-review-validation" className="p3-field-error" role="alert">{validation}</p>}
              <div className="p3-form-actions">
                <span>系统只记录审核角色和请求审计，不虚构自然人身份。</span>
                <button type="button" className="btn-primary" disabled={busy} onClick={prepareDecision}>
                  提交审核决定
                </button>
              </div>
            </div>
          )}
        </>
      )}

      {asset.status === "approved" && (
        <div className="p3-feedback success" role="status">
          <strong>内容已批准，但尚未发布。</strong>
          <span>只有管理员完成发布后，它才会成为正式 P3 数据资产。</span>
        </div>
      )}

      {asset.status === "needs_revision" && (
        <div className="p3-feedback error" role="status">
          <strong>审核要求修改。</strong>
          <span>请查看审核意见，并基于当前版本创建新的人工修订。</span>
        </div>
      )}

      {asset.status === "rejected" && (
        <div className="p3-feedback error" role="status">
          <strong>当前版本已被拒绝。</strong>
          <span>该版本不会进入发布流程，审核记录会继续保留。</span>
        </div>
      )}

      <ReviewHistory history={selectedHistory} />

      <ConfirmDialog
        open={confirmDecision}
        title={`确认${P3_REVIEW_DECISION_LABELS[decision]}这个版本？`}
        description={
          decision === "approved"
            ? "批准后内容仍未发布，管理员需要另行执行发布。"
            : "决定将被记录在当前不可变版本上，后续不会原地覆盖。"
        }
        confirmLabel={`确认${P3_REVIEW_DECISION_LABELS[decision]}`}
        danger={decision === "rejected"}
        busy={busy}
        onCancel={() => setConfirmDecision(false)}
        onConfirm={() => void decide()}
      />
    </section>
  );
}

function ReviewHistory({ history }: { history: P3Review[] }) {
  return (
    <section className="p3-review-history" aria-labelledby="p3-review-history-title">
      <div>
        <h3 id="p3-review-history-title">审核记录</h3>
        <p>当前系统记录角色和请求审计，不能证明审核人与提交人是不同自然人。</p>
      </div>
      {history.length === 0 ? (
        <div className="p3-empty-state">
          <strong>尚无最终审核决定</strong>
          <p>提交审核后，批准、退回修改或拒绝会记录在这里。</p>
        </div>
      ) : (
        <div className="p3-review-history-list">
          {history.map((item) => {
            const checklist = item.checklist_payload;
            return (
              <article key={item.id}>
                <div>
                  <span className={`p3-status-chip ${item.decision}`}>
                    {P3_REVIEW_DECISION_LABELS[item.decision]}
                  </span>
                  <time dateTime={item.created_at}>
                    {new Date(item.created_at).toLocaleString("zh-CN")}
                  </time>
                </div>
                <p>{item.comments || "未填写审核意见"}</p>
                <ul>
                  {CHECKLIST_ITEMS.map((check) => (
                    <li key={check.key}>
                      {checklist[check.key] ? "✓" : "—"} {check.label}
                    </li>
                  ))}
                </ul>
                <dl>
                  <div><dt>审核角色</dt><dd>{ROLE_LABELS[item.reviewer_role as AuthRole] ?? item.reviewer_role}</dd></div>
                  <div><dt>Review Policy</dt><dd>{item.review_policy_version}</dd></div>
                  <div><dt>Content Hash</dt><dd>{shortHash(item.reviewed_content_hash)}</dd></div>
                  <div><dt>Manifest Hash</dt><dd>{shortHash(item.reviewed_source_manifest_hash)}</dd></div>
                </dl>
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}
