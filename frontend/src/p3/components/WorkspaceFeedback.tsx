import type { P3ApiError } from "../client";

export type P3WorkspaceError = Pick<P3ApiError, "message" | "code" | "requestId" | "status">;

export function WorkspaceError({
  error,
  onDismiss,
}: {
  error: P3WorkspaceError | null;
  onDismiss?: () => void;
}) {
  if (!error) return null;
  return (
    <div className="p3-feedback error" role="alert">
      <div>
        <strong>{error.message}</strong>
        <p>请检查当前项目状态和输入内容，必要时刷新后重试。</p>
      </div>
      {onDismiss && (
        <button type="button" className="btn-small" onClick={onDismiss}>关闭</button>
      )}
      <details className="p3-inline-technical">
        <summary>技术详情</summary>
        <dl>
          <div><dt>HTTP 状态</dt><dd>{error.status}</dd></div>
          <div><dt>error_code</dt><dd>{error.code ?? "未提供"}</dd></div>
          <div><dt>request_id</dt><dd>{error.requestId ?? "未提供"}</dd></div>
        </dl>
      </details>
    </div>
  );
}

export function WorkspaceNotice({
  message,
}: {
  message: string;
}) {
  if (!message) return null;
  return <div className="p3-feedback success" role="status">{message}</div>;
}
