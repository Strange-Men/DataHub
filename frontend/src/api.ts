const API_BASE_URL: string =
  (import.meta as any).env?.VITE_API_BASE_URL ||
  (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1"
    ? "http://127.0.0.1:8000"
    : "https://datahub-jr8x.onrender.com");

export function apiPath(path: string): string {
  return `${API_BASE_URL}${path}`;
}

export { API_BASE_URL };
