import { useEffect, useState } from "react";
import {
  AUTH_ERROR_EVENT,
  apiFetch,
  apiPath,
  authErrorMessage,
  clearAuthSession,
  getAccessToken,
  isAuthRole,
  setAuthSession,
  type AuthRole,
} from "../api";


const ROLE_LABELS: Record<AuthRole, string> = {
  admin: "管理员",
  cleaner: "清洗员",
  reviewer: "审核员",
  service: "服务账号",
  viewer: "只读访客",
};


export function AuthControls({ onApplied }: { onApplied: () => void }) {
  const [tokenInput, setTokenInput] = useState("");
  const [role, setRole] = useState<AuthRole | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const showAuthError = (event: Event) => {
      setMessage((event as CustomEvent<string>).detail);
    };
    window.addEventListener(AUTH_ERROR_EVENT, showAuthError);
    return () => window.removeEventListener(AUTH_ERROR_EVENT, showAuthError);
  }, []);

  useEffect(() => {
    const token = getAccessToken();
    if (!token) return;

    let cancelled = false;
    async function restoreVerifiedRole() {
      try {
        const response = await apiFetch(apiPath("/api/auth/me"));
        const body = await response.json();
        const resolvedRole = body?.data?.role;
        if (!response.ok || !body.success || !isAuthRole(resolvedRole)) {
          clearAuthSession();
          if (!cancelled) setRole(null);
          return;
        }
        if (!cancelled) setRole(resolvedRole);
      } catch {
        clearAuthSession();
        if (!cancelled) {
          setRole(null);
          setMessage("无法连接后端验证访问令牌。");
        }
      }
    }

    void restoreVerifiedRole();
    return () => {
      cancelled = true;
    };
  }, []);

  async function applyToken() {
    const token = tokenInput.trim();
    if (!token) {
      setMessage("请输入访问令牌。");
      return;
    }
    setBusy(true);
    setMessage("");
    setAuthSession(token);
    try {
      const response = await apiFetch(apiPath("/api/auth/me"));
      const body = await response.json();
      const resolvedRole = body?.data?.role;
      if (!response.ok || !body.success || !isAuthRole(resolvedRole)) {
        clearAuthSession();
        setRole(null);
        setMessage(authErrorMessage(response.status) || "访问令牌验证失败。");
        return;
      }
      setRole(resolvedRole);
      setTokenInput("");
      setMessage(`令牌已应用，当前角色：${ROLE_LABELS[resolvedRole] || resolvedRole}`);
      onApplied();
    } catch {
      clearAuthSession();
      setRole(null);
      setMessage("无法连接后端验证访问令牌。");
    } finally {
      setBusy(false);
    }
  }

  function clearToken() {
    clearAuthSession();
    setTokenInput("");
    setRole(null);
    setMessage("访问令牌已清除。");
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
          placeholder="Bearer Token"
          autoComplete="off"
          aria-label="访问令牌"
        />
      </label>
      <button type="button" className="btn-small" onClick={applyToken} disabled={busy}>
        {busy ? "验证中" : "应用令牌"}
      </button>
      <button type="button" className="btn-small" onClick={clearToken}>
        清除
      </button>
      <span className="auth-role">角色：{role ? ROLE_LABELS[role] : "未认证"}</span>
      {message && <span className="auth-message" role="status">{message}</span>}
    </div>
  );
}
