import { useEffect, useMemo, useRef, useState } from "react";
import type { AuthRole } from "../../api";
import { can, permissionHint } from "../../governance";
import { createP3IdempotencyKey } from "../idempotency";
import { P3_ASSET_TYPE_LABELS, P3_SOURCE_TYPE_LABELS } from "../presentation";
import type {
  JsonObject,
  JsonValue,
  P3AssetSourceSnapshot,
  P3AssetVersion,
} from "../types";

function clonePayload(payload: JsonObject): JsonObject {
  return JSON.parse(JSON.stringify(payload)) as JsonObject;
}

function objectValue(value: JsonValue | undefined): JsonObject | null {
  return value && typeof value === "object" && !Array.isArray(value) ? value : null;
}

function stringValue(payload: JsonObject, key: string): string {
  return typeof payload[key] === "string" ? payload[key] : "";
}

function stringArray(payload: JsonObject, key: string): string[] {
  const value = payload[key];
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

function objectArray(payload: JsonObject, key: string): JsonObject[] {
  const value = payload[key];
  return Array.isArray(value)
    ? value.map(objectValue).filter((item): item is JsonObject => item !== null)
    : [];
}

function snapshotReference(source: P3AssetSourceSnapshot): JsonObject {
  return {
    source_item_id: source.source_item_id,
    source_type: source.source_type,
    source_id: source.source_id,
    source_version: source.source_version,
    approved_review_id: source.approved_review_id,
    snapshot_id: source.snapshot_id,
    knowledge_asset_id: source.knowledge_asset_id,
    content_fingerprint: source.source_fingerprint,
    lineage_manifest_hash: source.lineage_manifest_hash,
  };
}

function referenceId(value: JsonValue): string | null {
  const item = objectValue(value);
  return item && typeof item.source_item_id === "string" ? item.source_item_id : null;
}

function moveItem<T>(items: T[], index: number, direction: -1 | 1): T[] {
  const target = index + direction;
  if (target < 0 || target >= items.length) return items;
  const next = [...items];
  [next[index], next[target]] = [next[target], next[index]];
  return next;
}

function StringListEditor({
  label,
  items,
  onChange,
}: {
  label: string;
  items: string[];
  onChange: (items: string[]) => void;
}) {
  return (
    <fieldset className="p3-repeat-editor">
      <legend>{label}</legend>
      {items.map((item, index) => (
        <div className="p3-repeat-row" key={index}>
          <input
            value={item}
            aria-label={`${label} ${index + 1}`}
            onChange={(event) => {
              const next = [...items];
              next[index] = event.target.value;
              onChange(next);
            }}
          />
          <div className="p3-order-actions">
            <button
              type="button"
              aria-label={`上移${label} ${index + 1}`}
              disabled={index === 0}
              onClick={() => onChange(moveItem(items, index, -1))}
            >↑</button>
            <button
              type="button"
              aria-label={`下移${label} ${index + 1}`}
              disabled={index === items.length - 1}
              onClick={() => onChange(moveItem(items, index, 1))}
            >↓</button>
            <button
              type="button"
              aria-label={`删除${label} ${index + 1}`}
              onClick={() => onChange(items.filter((_, itemIndex) => itemIndex !== index))}
            >删除</button>
          </div>
        </div>
      ))}
      <button type="button" className="btn-small" onClick={() => onChange([...items, ""])}>
        添加{label}
      </button>
    </fieldset>
  );
}

function SourceRefsPicker({
  label,
  value,
  sources,
  onChange,
}: {
  label: string;
  value: JsonValue[];
  sources: P3AssetSourceSnapshot[];
  onChange: (refs: JsonValue[]) => void;
}) {
  const selectedIds = new Set(value.map(referenceId).filter((id): id is string => id !== null));
  return (
    <fieldset className="p3-source-ref-picker">
      <legend>{label}</legend>
      {sources.map((source) => {
        const checked = selectedIds.has(source.source_item_id);
        return (
          <label key={source.id}>
            <input
              type="checkbox"
              checked={checked}
              onChange={() => {
                if (checked) {
                  onChange(value.filter((item) => referenceId(item) !== source.source_item_id));
                } else {
                  onChange([...value, snapshotReference(source)]);
                }
              }}
            />
            <span>
              <strong>{P3_SOURCE_TYPE_LABELS[source.source_type]}</strong>
              <small>{source.source_id}</small>
            </span>
          </label>
        );
      })}
    </fieldset>
  );
}

function ObjectListActions({
  label,
  index,
  length,
  onMove,
  onDelete,
}: {
  label: string;
  index: number;
  length: number;
  onMove: (direction: -1 | 1) => void;
  onDelete: () => void;
}) {
  return (
    <div className="p3-object-actions">
      <span>{label} {index + 1}</span>
      <div>
        <button type="button" disabled={index === 0} onClick={() => onMove(-1)}>上移</button>
        <button type="button" disabled={index === length - 1} onClick={() => onMove(1)}>下移</button>
        <button type="button" className="danger-text" onClick={onDelete}>删除</button>
      </div>
    </div>
  );
}

export function StructuredRevisionEditor({
  role,
  asset,
  sources,
  busy,
  onSave,
}: {
  role: AuthRole | null;
  asset: P3AssetVersion;
  sources: P3AssetSourceSnapshot[];
  busy: boolean;
  onSave: (payload: JsonObject, idempotencyKey: string) => Promise<P3AssetVersion | null>;
}) {
  const [draft, setDraft] = useState(() => clonePayload(asset.content_payload));
  const [validationMessage, setValidationMessage] = useState("");
  const operationKey = useRef(createP3IdempotencyKey("manual-revision"));
  const editable = ["generated", "needs_revision"].includes(asset.status)
    && can(role, "p3.asset.edit");
  const allRefs = useMemo(() => sources.map(snapshotReference), [sources]);

  useEffect(() => {
    setDraft(clonePayload(asset.content_payload));
    setValidationMessage("");
    operationKey.current = createP3IdempotencyKey("manual-revision");
  }, [asset]);

  function change(next: JsonObject) {
    setDraft(next);
    setValidationMessage("");
    operationKey.current = createP3IdempotencyKey("manual-revision");
  }

  function setField(key: string, value: JsonValue) {
    change({ ...draft, [key]: value });
  }

  function updateObjectList(key: string, next: JsonObject[]) {
    setField(key, next);
  }

  function updateObjectField(
    listKey: string,
    index: number,
    field: string,
    value: JsonValue,
  ) {
    const items = objectArray(draft, listKey);
    items[index] = { ...items[index], [field]: value };
    updateObjectList(listKey, items);
  }

  function normalizedPayload(): JsonObject {
    const normalized = clonePayload(draft);
    if (asset.asset_type !== "sft_dataset") {
      normalized.source_refs = allRefs;
    }
    if (asset.asset_type === "sop") {
      normalized.steps = objectArray(normalized, "steps").map((item, index) => ({
        ...item,
        order: index + 1,
      }));
    }
    if (asset.asset_type === "service_script") {
      normalized.response_steps = objectArray(normalized, "response_steps").map((item, index) => ({
        ...item,
        order: index + 1,
      }));
    }
    return normalized;
  }

  async function save() {
    const payload = normalizedPayload();
    if (sources.length === 0) {
      setValidationMessage("当前版本没有可用来源快照，不能创建修订。");
      return;
    }
    const created = await onSave(payload, operationKey.current);
    if (created) operationKey.current = createP3IdempotencyKey("manual-revision");
  }

  if (!editable) {
    return (
      <div className="p3-feedback neutral" role="status">
        <strong>当前版本不可编辑。</strong>
        <span>
          {asset.status === "pending_review"
            ? "版本正在等待审核，内容已锁定。"
            : "只有草稿已生成或需要修改的版本可以创建新修订。"}
        </span>
      </div>
    );
  }

  return (
    <section className="p3-revision-editor" aria-labelledby="p3-revision-title">
      <div className="p3-section-heading">
        <div>
          <h2 id="p3-revision-title">创建人工修订</h2>
          <p>
            结构化编辑 {P3_ASSET_TYPE_LABELS[asset.asset_type]}；保存会创建新版本，
            资产类型、来源集合和 Hash 不可直接修改。
          </p>
        </div>
        <span className="p3-status-chip neutral">基于 v{asset.version_number}</span>
      </div>

      <div className="p3-structured-editor-fields">
        {asset.asset_type !== "sft_dataset" && (
          <label className="p3-wide-field">
            <span>标题</span>
            <input
              value={stringValue(draft, "title")}
              onChange={(event) => setField("title", event.target.value)}
            />
          </label>
        )}

        {asset.asset_type === "training_material" && (
          <>
            <StringListEditor
              label="学习目标"
              items={stringArray(draft, "learning_objectives")}
              onChange={(items) => setField("learning_objectives", items)}
            />
            <div className="p3-object-list-editor">
              <h3>章节</h3>
              {objectArray(draft, "sections").map((section, index, sections) => (
                <article key={index}>
                  <ObjectListActions
                    label="章节"
                    index={index}
                    length={sections.length}
                    onMove={(direction) => updateObjectList(
                      "sections",
                      moveItem(sections, index, direction),
                    )}
                    onDelete={() => updateObjectList(
                      "sections",
                      sections.filter((_, itemIndex) => itemIndex !== index),
                    )}
                  />
                  <label><span>章节标题</span><input
                    value={stringValue(section, "heading")}
                    onChange={(event) => updateObjectField("sections", index, "heading", event.target.value)}
                  /></label>
                  <label><span>章节内容</span><textarea
                    rows={5}
                    value={stringValue(section, "content")}
                    onChange={(event) => updateObjectField("sections", index, "content", event.target.value)}
                  /></label>
                  <SourceRefsPicker
                    label="章节来源引用"
                    value={Array.isArray(section.source_refs) ? section.source_refs : []}
                    sources={sources}
                    onChange={(refs) => updateObjectField("sections", index, "source_refs", refs)}
                  />
                </article>
              ))}
              <button type="button" className="btn-small" onClick={() => updateObjectList(
                "sections",
                [...objectArray(draft, "sections"), {
                  heading: "",
                  content: "",
                  source_refs: allRefs,
                }],
              )}>添加章节</button>
            </div>
            <StringListEditor
              label="核心要点"
              items={stringArray(draft, "key_points")}
              onChange={(items) => setField("key_points", items)}
            />
          </>
        )}

        {asset.asset_type === "sop" && (
          <>
            <label><span>目的</span><textarea rows={3} value={stringValue(draft, "purpose")}
              onChange={(event) => setField("purpose", event.target.value)} /></label>
            <label><span>适用范围</span><textarea rows={3} value={stringValue(draft, "scope")}
              onChange={(event) => setField("scope", event.target.value)} /></label>
            <StringListEditor label="前置条件" items={stringArray(draft, "prerequisites")}
              onChange={(items) => setField("prerequisites", items)} />
            <StepEditor
              listKey="steps"
              label="操作步骤"
              textField="instruction"
              textLabel="步骤说明"
              draft={draft}
              sources={sources}
              allRefs={allRefs}
              onList={updateObjectList}
              onField={updateObjectField}
            />
            <StringListEditor label="注意事项" items={stringArray(draft, "cautions")}
              onChange={(items) => setField("cautions", items)} />
            <StringListEditor label="升级规则" items={stringArray(draft, "escalation_rules")}
              onChange={(items) => setField("escalation_rules", items)} />
          </>
        )}

        {asset.asset_type === "service_script" && (
          <>
            <label><span>场景</span><textarea rows={3} value={stringValue(draft, "scenario")}
              onChange={(event) => setField("scenario", event.target.value)} /></label>
            <label><span>开场</span><textarea rows={3} value={stringValue(draft, "opening")}
              onChange={(event) => setField("opening", event.target.value)} /></label>
            <StepEditor
              listKey="response_steps"
              label="回复步骤"
              textField="response"
              textLabel="回复内容"
              draft={draft}
              sources={sources}
              allRefs={allRefs}
              onList={updateObjectList}
              onField={updateObjectField}
            />
            <StringListEditor label="禁止承诺" items={stringArray(draft, "prohibited_claims")}
              onChange={(items) => setField("prohibited_claims", items)} />
            <StringListEditor label="升级处理" items={stringArray(draft, "escalation")}
              onChange={(items) => setField("escalation", items)} />
          </>
        )}

        {asset.asset_type === "qa_bank" && (
          <RecordEditor
            listKey="items"
            label="问答"
            fields={[
              { key: "question", label: "问题" },
              { key: "answer", label: "答案", multiline: true },
            ]}
            draft={draft}
            sources={sources}
            allRefs={allRefs}
            onList={updateObjectList}
            onField={updateObjectField}
          />
        )}

        {asset.asset_type === "sft_dataset" && (
          <RecordEditor
            listKey="records"
            label="训练样本"
            fields={[
              { key: "instruction", label: "instruction", multiline: true },
              { key: "input", label: "input", multiline: true },
              { key: "output", label: "output", multiline: true },
            ]}
            includeMetadata
            draft={draft}
            sources={sources}
            allRefs={allRefs}
            onList={updateObjectList}
            onField={updateObjectField}
          />
        )}
      </div>

      {validationMessage && <p className="p3-field-error" role="alert">{validationMessage}</p>}
      <div className="p3-form-actions">
        <span>来源引用只能从当前版本的不可变 Snapshot 中选择。</span>
        <button
          type="button"
          className="btn-primary"
          disabled={busy || !can(role, "p3.asset.edit")}
          title={permissionHint(role, "p3.asset.edit")}
          onClick={() => void save()}
        >
          {busy ? "正在保存…" : "保存为新版本"}
        </button>
      </div>
    </section>
  );
}

function StepEditor({
  listKey,
  label,
  textField,
  textLabel,
  draft,
  sources,
  allRefs,
  onList,
  onField,
}: {
  listKey: string;
  label: string;
  textField: string;
  textLabel: string;
  draft: JsonObject;
  sources: P3AssetSourceSnapshot[];
  allRefs: JsonObject[];
  onList: (key: string, items: JsonObject[]) => void;
  onField: (key: string, index: number, field: string, value: JsonValue) => void;
}) {
  const items = objectArray(draft, listKey);
  return (
    <div className="p3-object-list-editor">
      <h3>{label}</h3>
      {items.map((item, index) => (
        <article key={index}>
          <ObjectListActions label={label} index={index} length={items.length}
            onMove={(direction) => onList(listKey, moveItem(items, index, direction))}
            onDelete={() => onList(listKey, items.filter((_, itemIndex) => itemIndex !== index))} />
          <label><span>{textLabel}</span><textarea rows={3}
            value={stringValue(item, textField)}
            onChange={(event) => onField(listKey, index, textField, event.target.value)} /></label>
          <SourceRefsPicker label={`${label}来源引用`}
            value={Array.isArray(item.source_refs) ? item.source_refs : []}
            sources={sources}
            onChange={(refs) => onField(listKey, index, "source_refs", refs)} />
        </article>
      ))}
      <button type="button" className="btn-small" onClick={() => onList(listKey, [
        ...items,
        { order: items.length + 1, [textField]: "", source_refs: allRefs },
      ])}>添加{label}</button>
    </div>
  );
}

function RecordEditor({
  listKey,
  label,
  fields,
  includeMetadata = false,
  draft,
  sources,
  allRefs,
  onList,
  onField,
}: {
  listKey: string;
  label: string;
  fields: Array<{ key: string; label: string; multiline?: boolean }>;
  includeMetadata?: boolean;
  draft: JsonObject;
  sources: P3AssetSourceSnapshot[];
  allRefs: JsonObject[];
  onList: (key: string, items: JsonObject[]) => void;
  onField: (key: string, index: number, field: string, value: JsonValue) => void;
}) {
  const items = objectArray(draft, listKey);
  return (
    <div className="p3-object-list-editor p3-wide-field">
      <h3>{label}</h3>
      {items.map((item, index) => {
        const metadata = objectValue(item.metadata) ?? {};
        return (
          <article key={index}>
            <ObjectListActions label={label} index={index} length={items.length}
              onMove={(direction) => onList(listKey, moveItem(items, index, direction))}
              onDelete={() => onList(listKey, items.filter((_, itemIndex) => itemIndex !== index))} />
            {fields.map((field) => (
              <label key={field.key}>
                <span>{field.label}</span>
                {field.multiline ? (
                  <textarea rows={3} value={stringValue(item, field.key)}
                    onChange={(event) => onField(listKey, index, field.key, event.target.value)} />
                ) : (
                  <input value={stringValue(item, field.key)}
                    onChange={(event) => onField(listKey, index, field.key, event.target.value)} />
                )}
              </label>
            ))}
            {includeMetadata && (
              <label>
                <span>metadata 备注</span>
                <input
                  value={typeof metadata.note === "string" ? metadata.note : ""}
                  onChange={(event) => onField(listKey, index, "metadata", {
                    ...metadata,
                    note: event.target.value,
                  })}
                />
              </label>
            )}
            <SourceRefsPicker label={`${label}来源引用`}
              value={Array.isArray(item.source_refs) ? item.source_refs : []}
              sources={sources}
              onChange={(refs) => onField(listKey, index, "source_refs", refs)} />
          </article>
        );
      })}
      <button type="button" className="btn-small" onClick={() => onList(listKey, [
        ...items,
        {
          ...Object.fromEntries(fields.map((field) => [field.key, ""])),
          ...(includeMetadata ? { metadata: {} } : {}),
          source_refs: allRefs,
        },
      ])}>添加{label}</button>
    </div>
  );
}
