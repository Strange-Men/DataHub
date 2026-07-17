import { NavLink } from "react-router-dom";
import type { BackendStatus } from "../types";
import { AuthControls } from "./AuthControls";

const NAV_ITEMS = [
  { path: "/", label: "首页", exact: true },
  { path: "/p1-text-hub", label: "P1 文本知识治理", exact: false },
  { path: "/p2-material-center", label: "P2 多模态知识治理", exact: false },
  { path: "/retrieval-validation", label: "检索验证", exact: false },
  { path: "/system-status", label: "系统状态", exact: false },
];

export function Layout({
  children,
  backendStatus,
  onCheckBackend,
}: {
  children: React.ReactNode;
  backendStatus: BackendStatus;
  onCheckBackend: () => void;
}) {
  return (
    <div className="app-layout">
      <nav className="top-nav">
        <div className="nav-brand">
          <span className="nav-logo">DH</span>
          <span className="nav-title">DataHub <small>{(import.meta as any).env?.MODE || "runtime"}</small></span>
        </div>
        <div className="nav-links">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.exact}
              className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
            >
              {item.label}
            </NavLink>
          ))}
        </div>
        <div className="nav-status">
          <AuthControls onApplied={onCheckBackend} />
          <span
            className={`status-dot ${backendStatus.state}`}
            title={
              backendStatus.state === "connected"
                ? "后端已连接"
                : backendStatus.state === "checking"
                  ? "检测中..."
                  : "后端未连接"
            }
          />
          <button
            type="button"
            className="nav-status-btn"
            onClick={onCheckBackend}
            title="重新检测后端连接"
          >
            {backendStatus.state === "connected" ? "已连接" : backendStatus.state === "checking" ? "检测中" : "未连接"}
          </button>
        </div>
      </nav>
      <main className="page-content">{children}</main>
    </div>
  );
}
