import {
  P3_ASSET_STATUS_LABELS,
  P3_ASSET_TYPE_LABELS,
  P3_GENERATION_MODE_LABELS,
  P3_SOURCE_TYPE_LABELS,
  shortHash,
} from "../presentation";
import type {
  JsonObject,
  JsonValue,
  P3AssetSourceSnapshot,
  P3AssetVersion,
} from "../types";

function record(value: JsonValue | undefined): JsonObject | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value
    : null;
}

function text(payload: JsonObject, key: string): string {
  return typeof payload[key] === "string" ? payload[key] : "";
}

function textList(payload: JsonObject, key: string): string[] {
  const value = payload[key];
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

function objectList(payload: JsonObject, key: string): JsonObject[] {
  const value = payload[key];
  return Array.isArray(value)
    ? value.map(record).filter((item): item is JsonObject => item !== null)
    : [];
}

function SourceReferenceCount({ payload }: { payload: JsonObject }) {
  const refs = Array.isArray(payload.source_refs) ? payload.source_refs.length : 0;
  return <span className="p3-source-ref-count">{refs} 个来源引用</span>;
}

function StringList({ title, items }: { title: string; items: string[] }) {
  if (!items.length) return null;
  return (
    <section className="p3-content-block">
      <h4>{title}</h4>
      <ul>{items.map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}</ul>
    </section>
  );
}

function TrainingView({ payload }: { payload: JsonObject }) {
  const sections = objectList(payload, "sections");
  return (
    <>
      <h3>{text(payload, "title") || "未命名培训材料"}</h3>
      <StringList title="学习目标" items={textList(payload, "learning_objectives")} />
      <div className="p3-content-sections">
        {sections.map((section, index) => (
          <section className="p3-content-block" key={index}>
            <div className="p3-content-block-title">
              <h4>{text(section, "heading") || `章节 ${index + 1}`}</h4>
              <SourceReferenceCount payload={section} />
            </div>
            <p>{text(section, "content") || "未填写章节内容"}</p>
          </section>
        ))}
      </div>
      <StringList title="核心要点" items={textList(payload, "key_points")} />
    </>
  );
}

function SopView({ payload }: { payload: JsonObject }) {
  const steps = objectList(payload, "steps");
  return (
    <>
      <h3>{text(payload, "title") || "未命名 SOP"}</h3>
      <div className="p3-content-summary-grid">
        <section><span>目的</span><p>{text(payload, "purpose") || "—"}</p></section>
        <section><span>适用范围</span><p>{text(payload, "scope") || "—"}</p></section>
      </div>
      <StringList title="前置条件" items={textList(payload, "prerequisites")} />
      <section className="p3-content-block">
        <h4>操作步骤</h4>
        <ol className="p3-procedure-steps">
          {steps.map((step, index) => (
            <li key={index}>
              <span>{typeof step.order === "number" ? step.order : index + 1}</span>
              <p>{text(step, "instruction") || "未填写步骤"}</p>
              <SourceReferenceCount payload={step} />
            </li>
          ))}
        </ol>
      </section>
      <StringList title="注意事项" items={textList(payload, "cautions")} />
      <StringList title="升级规则" items={textList(payload, "escalation_rules")} />
    </>
  );
}

function ServiceScriptView({ payload }: { payload: JsonObject }) {
  const steps = objectList(payload, "response_steps");
  return (
    <>
      <h3>{text(payload, "title") || "未命名客服话术"}</h3>
      <div className="p3-content-summary-grid">
        <section><span>适用场景</span><p>{text(payload, "scenario") || "—"}</p></section>
        <section><span>开场</span><p>{text(payload, "opening") || "—"}</p></section>
      </div>
      <section className="p3-content-block">
        <h4>回复步骤</h4>
        <ol className="p3-procedure-steps">
          {steps.map((step, index) => (
            <li key={index}>
              <span>{typeof step.order === "number" ? step.order : index + 1}</span>
              <p>{text(step, "response") || "未填写回复"}</p>
              <SourceReferenceCount payload={step} />
            </li>
          ))}
        </ol>
      </section>
      <StringList title="禁止承诺" items={textList(payload, "prohibited_claims")} />
      <StringList title="升级处理" items={textList(payload, "escalation")} />
    </>
  );
}

function QaBankView({ payload }: { payload: JsonObject }) {
  const items = objectList(payload, "items");
  return (
    <>
      <h3>{text(payload, "title") || "未命名问答题库"}</h3>
      <div className="p3-qa-cards">
        {items.map((item, index) => (
          <article key={index}>
            <span>问题 {index + 1}</span>
            <h4>{text(item, "question") || "未填写问题"}</h4>
            <p>{text(item, "answer") || "未填写答案"}</p>
            <SourceReferenceCount payload={item} />
          </article>
        ))}
      </div>
    </>
  );
}

function SftView({ payload }: { payload: JsonObject }) {
  const records = objectList(payload, "records");
  return (
    <>
      <h3>SFT 数据集草稿</h3>
      <div className="p3-sft-records">
        {records.map((item, index) => (
          <article key={index}>
            <span>样本 {index + 1}</span>
            <dl>
              <div><dt>instruction</dt><dd>{text(item, "instruction") || "—"}</dd></div>
              <div><dt>input</dt><dd>{text(item, "input") || "—"}</dd></div>
              <div><dt>output</dt><dd>{text(item, "output") || "—"}</dd></div>
            </dl>
            <SourceReferenceCount payload={item} />
          </article>
        ))}
      </div>
    </>
  );
}

export function StructuredAssetViewer({
  asset,
  sources,
  loading,
}: {
  asset: P3AssetVersion;
  sources: P3AssetSourceSnapshot[];
  loading: boolean;
}) {
  return (
    <section className="p3-asset-detail" aria-labelledby="p3-asset-detail-title">
      <div className="p3-section-heading">
        <div>
          <span className="p3-stage-label">版本 v{asset.version_number}</span>
          <h2 id="p3-asset-detail-title">{P3_ASSET_TYPE_LABELS[asset.asset_type]}内容</h2>
          <p>
            {P3_GENERATION_MODE_LABELS[asset.generation_mode]} ·
            {asset.parent_asset_version_id ? " 由上一版本创建的新修订" : " 初始草稿"}
          </p>
        </div>
        <span className={`p3-status-chip ${asset.status}`}>
          {P3_ASSET_STATUS_LABELS[asset.status]}
        </span>
      </div>

      <div className="p3-structured-content">
        {asset.asset_type === "training_material" && <TrainingView payload={asset.content_payload} />}
        {asset.asset_type === "sop" && <SopView payload={asset.content_payload} />}
        {asset.asset_type === "service_script" && <ServiceScriptView payload={asset.content_payload} />}
        {asset.asset_type === "qa_bank" && <QaBankView payload={asset.content_payload} />}
        {asset.asset_type === "sft_dataset" && <SftView payload={asset.content_payload} />}
      </div>

      <section className="p3-asset-source-snapshots" aria-labelledby="p3-snapshot-title">
        <div>
          <h3 id="p3-snapshot-title">来源快照摘要</h3>
          <span>{sources.length} 个不可变来源快照</span>
        </div>
        {loading ? (
          <p role="status">正在加载来源快照…</p>
        ) : (
          <div>
            {sources.map((source) => (
              <article key={source.id}>
                <strong>{P3_SOURCE_TYPE_LABELS[source.source_type]}</strong>
                <span>版本 {source.source_version ?? "当前"}</span>
                <span>指纹 {shortHash(source.source_fingerprint)}</span>
              </article>
            ))}
          </div>
        )}
      </section>

      <details className="p3-inline-technical">
        <summary>技术详情与只读 JSON</summary>
        <dl>
          <div><dt>asset_version_id</dt><dd>{asset.id}</dd></div>
          <div><dt>content_hash</dt><dd>{asset.content_hash}</dd></div>
          <div><dt>manifest_hash</dt><dd>{asset.source_manifest_hash}</dd></div>
          <div><dt>parent_version_id</dt><dd>{asset.parent_asset_version_id ?? "无"}</dd></div>
        </dl>
        <pre>{JSON.stringify(asset.content_payload, null, 2)}</pre>
      </details>
    </section>
  );
}
