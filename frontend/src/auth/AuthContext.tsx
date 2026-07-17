import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import {
  apiFetch,
  apiPath,
  authErrorMessage,
  clearAuthSession,
  getAccessToken,
  isAuthRole,
  setAuthSession,
  type AuthRole,
} from "../api";

type AuthMode = "disabled" | "token" | "unknown";

type AuthContextValue = {
  role: AuthRole | null;
  authMode: AuthMode;
  authenticated: boolean;
  loading: boolean;
  message: string;
  applyToken: (token: string) => Promise<boolean>;
  clearToken: () => Promise<void>;
  refreshPrincipal: (quiet?: boolean) => Promise<void>;
  setMessage: (message: string) => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [role, setRole] = useState<AuthRole | null>(null);
  const [authMode, setAuthMode] = useState<AuthMode>("unknown");
  const [authenticated, setAuthenticated] = useState(false);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");

  const refreshPrincipal = useCallback(async (quiet = false) => {
    setLoading(true);
    try {
      const response = await apiFetch(apiPath("/api/auth/me"), {}, { suppressAuthEvent: quiet });
      const body = await response.json();
      const resolvedRole = body?.data?.role;
      const resolvedMode = body?.data?.auth_mode;
      if (!response.ok || !body.success || !isAuthRole(resolvedRole)) {
        if (response.status === 401) clearAuthSession();
        setRole(null);
        setAuthenticated(false);
        if (response.status === 401) setAuthMode("token");
        if (!quiet) setMessage(authErrorMessage(response.status) || "无法确认当前访问角色。");
        return;
      }
      setRole(resolvedRole);
      setAuthMode(resolvedMode === "disabled" ? "disabled" : "token");
      setAuthenticated(Boolean(body.data.authenticated));
    } catch {
      setRole(null);
      setAuthenticated(false);
      if (!quiet) setMessage("无法连接后端验证访问令牌。");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshPrincipal(true);
  }, [refreshPrincipal]);

  const applyToken = useCallback(async (token: string) => {
    const normalized = token.trim();
    if (!normalized) {
      setMessage("请输入访问令牌。");
      return false;
    }
    setAuthSession(normalized);
    setLoading(true);
    try {
      const response = await apiFetch(apiPath("/api/auth/me"));
      const body = await response.json();
      const resolvedRole = body?.data?.role;
      if (!response.ok || !body.success || !isAuthRole(resolvedRole)) {
        clearAuthSession();
        setRole(null);
        setAuthenticated(false);
        setAuthMode("token");
        setMessage(authErrorMessage(response.status) || "访问令牌验证失败。");
        return false;
      }
      setRole(resolvedRole);
      setAuthMode(body.data.auth_mode === "disabled" ? "disabled" : "token");
      setAuthenticated(Boolean(body.data.authenticated));
      setMessage("访问令牌已应用，角色已由后端确认。");
      return true;
    } catch {
      clearAuthSession();
      setRole(null);
      setAuthenticated(false);
      setMessage("无法连接后端验证访问令牌。");
      return false;
    } finally {
      setLoading(false);
    }
  }, []);

  const clearToken = useCallback(async () => {
    clearAuthSession();
    setRole(null);
    setAuthenticated(false);
    setMessage("访问令牌已清除。");
    await refreshPrincipal(true);
  }, [refreshPrincipal]);

  const value = useMemo<AuthContextValue>(() => ({
    role,
    authMode,
    authenticated,
    loading,
    message,
    applyToken,
    clearToken,
    refreshPrincipal,
    setMessage,
  }), [role, authMode, authenticated, loading, message, applyToken, clearToken, refreshPrincipal]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}

export function hasStoredAccessToken(): boolean {
  return Boolean(getAccessToken());
}
