import type { BackendStatus } from "../types";
import { useAuth } from "../auth/AuthContext";
import { ROLE_LABELS } from "../governance";

export function SystemStatus({ backendStatus, onCheckBackend }: { backendStatus: BackendStatus; onCheckBackend: () => void }) {
  const { role, authMode, authenticated, loading, refreshPrincipal } = useAuth();
  return (
    <div className="system-page">
      <div className="page-hero"><h1>系统状态</h1><p>仅展示操作所需的健康状态和可信认证结果，不暴露密钥、数据库连接或调试堆栈。</p></div>
      <section className="material-panel system-status-grid">
        <article><span>后端服务</span><strong>{backendStatus.state === "connected" ? "正常" : backendStatus.state === "checking" ? "检测中" : "暂不可用"}</strong><small>{backendStatus.detail}</small></article>
        <article><span>认证模式</span><strong>{authMode === "disabled" ? "兼容模式（disabled）" : authMode === "token" ? "令牌模式" : "确认中"}</strong><small>{authenticated ? "令牌已由后端验证" : "未使用令牌身份"}</small></article>
        <article><span>当前角色</span><strong>{loading ? "确认中" : role ? ROLE_LABELS[role] : "未认证"}</strong><small>角色唯一来源：GET /api/auth/me</small></article>
        <article><span>Agent 默认策略</span><strong>P1-only</strong><small>Unified 仍需显式 opt-in</small></article>
      </section>
      <div className="system-actions">
        <button className="btn-secondary" type="button" onClick={onCheckBackend}>重新检查健康状态</button>
        <button className="btn-secondary" type="button" onClick={() => void refreshPrincipal()}>重新确认角色</button>
      </div>
    </div>
  );
}
