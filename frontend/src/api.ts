const API_BASE_URL: string =
  (import.meta as any).env?.VITE_API_BASE_URL ||
  (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1"
    ? "http://127.0.0.1:8000"
    : "https://datahub-jr8x.onrender.com");

export type AuthRole = "admin" | "cleaner" | "reviewer" | "service" | "viewer";

const AUTH_TOKEN_KEY = "datahub.auth.token";
export const AUTH_ERROR_EVENT = "datahub:auth-error";

const AUTH_ROLES: ReadonlySet<AuthRole> = new Set([
  "admin",
  "cleaner",
  "reviewer",
  "service",
  "viewer",
]);

export function apiPath(path: string): string {
  return `${API_BASE_URL}${path}`;
}

export function getAccessToken(): string | null {
  return window.sessionStorage.getItem(AUTH_TOKEN_KEY);
}

export function isAuthRole(value: unknown): value is AuthRole {
  return typeof value === "string" && AUTH_ROLES.has(value as AuthRole);
}

export function setAuthSession(token: string): void {
  window.sessionStorage.setItem(AUTH_TOKEN_KEY, token);
}

export function clearAuthSession(): void {
  window.sessionStorage.removeItem(AUTH_TOKEN_KEY);
}

export function authErrorMessage(status: number): string | null {
  if (status === 401) return "身份验证失败，请检查访问令牌。";
  if (status === 403) return "当前角色没有执行此操作的权限。";
  return null;
}

export async function apiFetch(
  input: RequestInfo | URL,
  init: RequestInit = {},
): Promise<Response> {
  const headers = new Headers(init.headers);
  const token = getAccessToken();
  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  const response = await window.fetch(input, { ...init, headers });
  const message = authErrorMessage(response.status);
  if (message) {
    window.dispatchEvent(new CustomEvent(AUTH_ERROR_EVENT, { detail: message }));
  }
  return response;
}

export { API_BASE_URL };
