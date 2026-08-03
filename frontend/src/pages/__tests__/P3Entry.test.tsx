import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { App } from "../../App";
import { HomePage } from "../HomePage";

const backendStatus = {
  state: "connected" as const,
  service: "datahub",
  phase: "p3",
};

function jsonResponse(data: unknown): Response {
  return new Response(JSON.stringify(data), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

describe("P3 entry and route", () => {
  it("enables P3 while preserving P1/P2 and keeping P4 disabled", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <HomePage backendStatus={backendStatus} onCheckBackend={vi.fn()} />
      </MemoryRouter>,
    );

    const p1 = screen.getByRole("heading", { name: "P1 文本知识治理" }).closest("article");
    const p2 = screen.getByRole("heading", { name: "P2 素材文本投影治理" }).closest("article");
    const p3 = screen.getByRole("heading", { name: "数据资产复用" }).closest("article");
    const p4 = screen.getByRole("heading", { name: "P4 MCP + Agent 集群" }).closest("article");

    expect(p1).not.toBeNull();
    expect(p2).not.toBeNull();
    expect(p3).not.toBeNull();
    expect(p4).not.toBeNull();
    expect(within(p1!).getByRole("button", { name: "进入模块" })).toBeEnabled();
    expect(within(p2!).getByRole("button", { name: "进入模块" })).toBeEnabled();
    expect(within(p3!).getByRole("button", { name: "进入模块" })).toBeEnabled();
    expect(within(p4!).queryByRole("button")).not.toBeInTheDocument();
    expect(p4).toHaveClass("disabled");

    await user.click(within(p3!).getByRole("button", { name: "进入模块" }));
    expect(window.location.pathname).not.toContain("p4");
  });

  it("registers /p3 and renders the five-stage Chinese workspace", async () => {
    vi.spyOn(window, "fetch").mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/health")) {
        return jsonResponse({ status: "ok", service: "datahub", phase: "p3" });
      }
      if (url.includes("/api/p3/reuse-projects")) {
        return jsonResponse({
          success: true,
          data: { items: [], total: 0, limit: 8, offset: 0 },
          requestId: "req_projects",
        });
      }
      return jsonResponse({
        success: true,
        data: { role: "admin", auth_mode: "disabled", authenticated: true },
        requestId: "req_auth",
      });
    });
    window.history.pushState({}, "", "/p3");

    render(<App />);

    expect(await screen.findByRole("heading", { name: "数据资产复用", level: 1 })).toBeVisible();
    expect(screen.getByRole("navigation", { name: "数据资产复用五阶段" })).toBeVisible();
    for (const label of ["创建项目", "选择来源", "生成与修订", "提交与审核", "发布与导出"]) {
      expect(screen.getByText(label)).toBeVisible();
    }
    expect(screen.getByText("选择或创建一个项目后开始")).toBeVisible();
    await waitFor(() => expect(screen.getByText("管理员")).toBeVisible());
    expect(screen.getByText("技术详情")).toBeVisible();
  });
});
