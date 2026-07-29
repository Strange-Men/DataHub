import { useRef, useState } from "react";
import type { AuthRole } from "../../api";
import { can, permissionHint } from "../../governance";
import { P3_LLM_DRAFT_ENABLED } from "../config";
import { createP3IdempotencyKey } from "../idempotency";
import { P3_ASSET_TYPE_LABELS } from "../presentation";
import type { P3AssetType, P3AssetVersion, P3Project } from "../types";

const ASSET_TYPE_DESCRIPTIONS: Readonly<Record<P3AssetType, string>> = {
  training_material: "按学习目标和章节组织新人培训内容。",
  sop: "整理目的、前置条件、操作步骤和升级规则。",
  service_script: "形成场景化开场、回复步骤和禁止承诺。",
  qa_bank: "生成可复核的问题、答案和来源引用。",
  sft_dataset: "整理 instruction、input、output 和来源元数据。",
};

export function AssetGenerationPanel({
  role,
  project,
  busy,
  onGenerate,
  onGenerateLlm,
}: {
  role: AuthRole | null;
  project: P3Project;
  busy: boolean;
  onGenerate: (assetType: P3AssetType, idempotencyKey: string) => Promise<P3AssetVersion | null>;
  onGenerateLlm: (assetType: P3AssetType, idempotencyKey: string) => Promise<P3AssetVersion | null>;
}) {
  const [assetType, setAssetType] = useState<P3AssetType>("training_material");
  const deterministicKey = useRef(createP3IdempotencyKey("generate-draft"));
  const llmKey = useRef(createP3IdempotencyKey("generate-llm-draft"));
  const active = project.status === "active";
  const canGenerate = active && can(role, "p3.asset.generate");
  const canGenerateLlm = active
    && P3_LLM_DRAFT_ENABLED
    && can(role, "p3.asset.generate_llm");

  function resetKeys() {
    deterministicKey.current = createP3IdempotencyKey("generate-draft");
    llmKey.current = createP3IdempotencyKey("generate-llm-draft");
  }

  async function generate() {
    const created = await onGenerate(assetType, deterministicKey.current);
    if (created) resetKeys();
  }

  async function generateLlm() {
    if (!P3_LLM_DRAFT_ENABLED) return;
    const created = await onGenerateLlm(assetType, llmKey.current);
    if (created) resetKeys();
  }

  return (
    <section className="p3-asset-generation" aria-labelledby="p3-generation-title">
      <div className="p3-section-heading">
        <div>
          <span className="p3-stage-label">第 3 阶段</span>
          <h2 id="p3-generation-title">生成可审核草稿</h2>
          <p>默认使用可复现的确定性模板；任何生成结果都只是草稿。</p>
        </div>
        {!active && <span className="p3-status-chip warning">请先激活项目</span>}
      </div>

      <fieldset className="p3-asset-type-picker" disabled={!active || busy}>
        <legend>选择资产类型</legend>
        {Object.entries(P3_ASSET_TYPE_LABELS).map(([code, label]) => {
          const type = code as P3AssetType;
          return (
            <label className={assetType === type ? "selected" : ""} key={type}>
              <input
                type="radio"
                name="p3-asset-type"
                value={type}
                checked={assetType === type}
                onChange={() => {
                  setAssetType(type);
                  resetKeys();
                }}
              />
              <span>
                <strong>{label}</strong>
                <small>{ASSET_TYPE_DESCRIPTIONS[type]}</small>
              </span>
            </label>
          );
        })}
      </fieldset>

      <div className="p3-generation-actions">
        <article className="primary">
          <div>
            <span className="p3-recommended-mark">默认方式</span>
            <h3>确定性生成</h3>
            <p>相同来源和模板得到可复现结果，便于审核与追踪。</p>
          </div>
          <button
            type="button"
            className="btn-primary"
            disabled={!canGenerate || busy}
            title={permissionHint(role, "p3.asset.generate")}
            onClick={() => void generate()}
          >
            {busy ? "正在生成…" : `生成${P3_ASSET_TYPE_LABELS[assetType]}草稿`}
          </button>
        </article>

        <article className="secondary">
          <div>
            <h3>LLM 草稿</h3>
            <p>
              {P3_LLM_DRAFT_ENABLED
                ? "仅用于生成需人工审核的草稿，不会自动发布。"
                : "当前环境未启用，不会发送 Provider 请求。"}
            </p>
          </div>
          <button
            type="button"
            className="btn-secondary"
            disabled={!canGenerateLlm || busy}
            title={
              P3_LLM_DRAFT_ENABLED
                ? permissionHint(role, "p3.asset.generate_llm")
                : "LLM 草稿功能当前未启用"
            }
            onClick={() => void generateLlm()}
          >
            {P3_LLM_DRAFT_ENABLED ? "生成 LLM 草稿" : "当前环境未启用"}
          </button>
        </article>
      </div>
    </section>
  );
}
