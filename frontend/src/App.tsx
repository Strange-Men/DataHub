import { useEffect, useState } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { apiPath } from "./api";
import type { BackendStatus } from "./types";
import { Layout } from "./components/Layout";
import { HomePage } from "./pages/HomePage";
import { P1TextHub } from "./pages/P1TextHub";
import { P2MaterialCenter } from "./pages/P2MaterialCenter";
import { P3AssetReuse } from "./pages/P3AssetReuse";
import { P4McpAgents } from "./pages/P4McpAgents";


export function App() {
  const [backendStatus, setBackendStatus] = useState<BackendStatus>({
    state: "checking",
    detail: "正在检测后端连接...",
  });

  useEffect(() => {
    checkBackendConnection();
  }, []);

  async function checkBackendConnection() {
    setBackendStatus({
      state: "checking",
      detail: "正在检测后端连接...",
    });
    try {
      const response = await fetch(apiPath("/api/health"));
      const body = await response.json();
      if (!response.ok || body.status !== "ok") {
        setBackendStatus({
          state: "disconnected",
          detail: "后端已响应，但健康检查未返回 ok。",
        });
        return;
      }
      setBackendStatus({
        state: "connected",
        service: body.service,
        phase: body.phase,
        detail: "已连接后端 API。",
      });
    } catch {
      setBackendStatus({
        state: "disconnected",
        detail: "后端暂未连接，可能是 Render 免费实例冷启动。请稍等或点击重新检测。",
      });
    }
  }

  return (
    <BrowserRouter>
      <Layout backendStatus={backendStatus} onCheckBackend={checkBackendConnection}>
        <Routes>
          <Route
            path="/"
            element={
              <HomePage backendStatus={backendStatus} onCheckBackend={checkBackendConnection} />
            }
          />
          <Route
            path="/p1-text-hub"
            element={
              <P1TextHub backendStatus={backendStatus} onCheckBackend={checkBackendConnection} />
            }
          />
          <Route path="/p2-material-center" element={<P2MaterialCenter />} />
          <Route path="/p3-asset-reuse" element={<P3AssetReuse />} />
          <Route path="/p4-mcp-agents" element={<P4McpAgents />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  );
}
