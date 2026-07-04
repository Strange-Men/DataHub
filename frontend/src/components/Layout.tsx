import { NavLink } from "react-router-dom";
import type { BackendStatus } from "../types";

const NAV_ITEMS = [
  { path: "/", label: "首页", exact: true },
  { path: "/p1-text-hub", label: "客服文本中台", exact: false },
  { path: "/p2-material-center", label: "AI 素材中心", exact: false },
  { path: "/p3-asset-reuse", label: "数据资产复用", exact: false },
  { path: "/p4-mcp-agents", label: "MCP + Agent 集群", exact: false },
  { path: "/advanced", label: "高级信息", exact: false },
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
          <span className="nav-title">DataHub</span>
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
