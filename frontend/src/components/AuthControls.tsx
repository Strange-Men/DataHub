import { useEffect, useState } from "react";
import { AUTH_ERROR_EVENT } from "../api";
import { useAuth } from "../auth/AuthContext";
import { ROLE_LABELS } from "../governance";

export function AuthControls({ onApplied }: { onApplied: () => void }) {
  const { role, authMode, loading, message, applyToken, clearToken, setMessage } = useAuth();
  const [tokenInput, setTokenInput] = useState("");

  useEffect(() => {
    const showAuthError = (event: Event) => setMessage((event as CustomEvent<string>).detail);
    window.addEventListener(AUTH_ERROR_EVENT, showAuthError);
    return () => window.removeEventListener(AUTH_ERROR_EVENT, showAuthError);
  }, [setMessage]);

  async function handleApply() {
    if (await applyToken(tokenInput)) {
      setTokenInput("");
      onApplied();
    }
  }

  async function handleClear() {
    setTokenInput("");
    await clearToken();
    onApplied();
  }

  return (
    <div className="auth-controls">
      <label className="auth-token-field">
        <span>访问令牌</span>
        <input
          type="password"
          value={tokenInput}
          onChange={(event) => setTokenInput(event.target.value)}
          placeholder={authMode === "disabled" ? "认证已关闭" : "Bearer Token"}
          autoComplete="off"
          aria-label="访问令牌"
        />
      </label>
      <button type="button" className="btn-small" onClick={() => void handleApply()} disabled={loading}>
        {loading ? "验证中" : "应用令牌"}
      </button>
      <button type="button" className="btn-small" onClick={() => void handleClear()} disabled={loading}>
        清除
      </button>
      <span className="auth-role">
        角色：{loading ? "确认中" : role ? ROLE_LABELS[role] : "未认证"}
        {authMode === "disabled" ? "（兼容模式）" : ""}
      </span>
      {message && <span className="auth-message" role="status">{message}</span>}
    </div>
  );
}
