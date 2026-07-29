import { useRef, useState } from "react";
import type { AuthRole } from "../../api";
import { can, permissionHint } from "../../governance";
import { createP3IdempotencyKey } from "../idempotency";
import { P3_PROJECT_STATUS_LABELS } from "../presentation";
import type { P3Project } from "../types";

export function ProjectPicker({
  role,
  projects,
  total,
  offset,
  pageSize,
  selectedProject,
  loading,
  mutating,
  onPage,
  onSelect,
  onCreate,
}: {
  role: AuthRole | null;
  projects: P3Project[];
  total: number;
  offset: number;
  pageSize: number;
  selectedProject: P3Project | null;
  loading: boolean;
  mutating: boolean;
  onPage: (offset: number) => void;
  onSelect: (project: P3Project) => void;
  onCreate: (input: {
    name: string;
    description?: string | null;
    idempotencyKey: string;
  }) => Promise<P3Project | null>;
}) {
  const [showCreate, setShowCreate] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [fieldError, setFieldError] = useState("");
  const createKey = useRef(createP3IdempotencyKey("create-project"));
  const canCreate = can(role, "p3.project.write");

  function resetOperationKey() {
    createKey.current = createP3IdempotencyKey("create-project");
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const normalizedName = name.trim();
    if (!normalizedName) {
      setFieldError("请填写项目名称。");
      return;
    }
    const created = await onCreate({
      name: normalizedName,
      description: description.trim() || null,
      idempotencyKey: createKey.current,
    });
    if (created) {
      setName("");
      setDescription("");
      setFieldError("");
      setShowCreate(false);
      resetOperationKey();
    }
  }

  return (
    <section className="p3-project-picker" aria-labelledby="p3-project-picker-title">
      <div className="p3-section-heading">
        <div>
          <span className="p3-stage-label">第 1 阶段</span>
          <h2 id="p3-project-picker-title">选择复用项目</h2>
          <p>每个项目独立保存来源、草稿、审核和导出记录。</p>
        </div>
        <button
          type="button"
          className="btn-primary"
          disabled={!canCreate || mutating}
          title={permissionHint(role, "p3.project.write")}
          onClick={() => setShowCreate((current) => !current)}
        >
          {showCreate ? "收起创建表单" : "新建项目"}
        </button>
      </div>

      {showCreate && (
        <form className="p3-create-project-form" onSubmit={submit}>
          <label>
            <span>项目名称</span>
            <input
              value={name}
              maxLength={300}
              required
              aria-invalid={Boolean(fieldError)}
              aria-describedby={fieldError ? "p3-project-name-error" : undefined}
              onChange={(event) => {
                setName(event.target.value);
                setFieldError("");
                resetOperationKey();
              }}
              placeholder="例如：客服新人培训资料"
            />
          </label>
          <label>
            <span>项目说明（可选）</span>
            <textarea
              value={description}
              maxLength={10_000}
              rows={3}
              onChange={(event) => {
                setDescription(event.target.value);
                resetOperationKey();
              }}
              placeholder="简要说明目标人群和使用场景"
            />
          </label>
          {fieldError && <p id="p3-project-name-error" className="p3-field-error">{fieldError}</p>}
          <div className="p3-form-actions">
            <button
              type="button"
              className="btn-secondary"
              disabled={mutating}
              onClick={() => setShowCreate(false)}
            >
              取消
            </button>
            <button type="submit" className="btn-primary" disabled={mutating}>
              {mutating ? "正在创建…" : "创建并进入项目"}
            </button>
          </div>
        </form>
      )}

      {loading ? (
        <div className="p3-loading" role="status">正在加载项目…</div>
      ) : projects.length === 0 ? (
        <div className="p3-empty-state">
          <strong>还没有复用项目</strong>
          <p>创建第一个项目后，即可选择已审核的治理知识。</p>
        </div>
      ) : (
        <>
          <div className="p3-project-list" aria-label="复用项目列表">
            {projects.map((project) => (
              <button
                type="button"
                className={`p3-project-card ${selectedProject?.id === project.id ? "selected" : ""}`}
                aria-pressed={selectedProject?.id === project.id}
                key={project.id}
                onClick={() => onSelect(project)}
              >
                <span>
                  <strong>{project.name}</strong>
                  <small>{project.description || "未填写项目说明"}</small>
                </span>
                <span className={`p3-status-chip ${project.status}`}>
                  {P3_PROJECT_STATUS_LABELS[project.status]}
                </span>
                <time dateTime={project.updated_at}>
                  更新于 {new Date(project.updated_at).toLocaleString("zh-CN")}
                </time>
              </button>
            ))}
          </div>
          <div className="p3-pagination" aria-label="项目分页">
            <span>共 {total} 个项目</span>
            <div>
              <button
                type="button"
                className="btn-small"
                disabled={offset === 0 || loading}
                onClick={() => onPage(Math.max(0, offset - pageSize))}
              >
                上一页
              </button>
              <button
                type="button"
                className="btn-small"
                disabled={offset + pageSize >= total || loading}
                onClick={() => onPage(offset + pageSize)}
              >
                下一页
              </button>
            </div>
          </div>
        </>
      )}
    </section>
  );
}
