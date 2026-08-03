import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import type { CapabilitiesResponse } from "../../capabilities/types";
import { setAuthSession } from "../../api";
import { HomePage } from "../HomePage";

const backendStatus = {
  state: "connected" as const,
  service: "datahub",
  phase: "p3",
};

function capabilityResponse(
  moduleOverrides: Partial<CapabilitiesResponse["modules"]> = {},
): CapabilitiesResponse {
  return {
    environment: "local",
    authority: "local_docker",
    auth: { mode: "disabled", safe_for_environment: true },
    infrastructure: {
      database: "available",
      pgvector: "available",
      asset_storage: "local_only",
      export_storage: "local_only",
    },
    modules: {
      p1: { status: "available", reason_codes: [] },
      p2: { status: "local_only", reason_codes: ["ASSET_STORAGE_LOCAL_ONLY"] },
      p3: { status: "local_only", reason_codes: ["EXPORT_STORAGE_LOCAL_ONLY"] },
      p4: { status: "planned", reason_codes: ["NOT_IMPLEMENTED"] },
      ...moduleOverrides,
    },
    features: {
      p3_llm_draft: false,
      unified_retrieval: false,
      customerops_default_mode: "p1",
    },
  };
}

function jsonResponse(data: unknown): Response {
  return new Response(JSON.stringify(data), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

function renderHome() {
  return render(
    <MemoryRouter>
      <HomePage backendStatus={backendStatus} onCheckBackend={vi.fn()} />
    </MemoryRouter>,
  );
}

function capabilityCard(title: string): HTMLElement {
  const card = screen.getByRole("heading", { name: title }).closest("article");
  if (!card) throw new Error(`Capability card not found: ${title}`);
  return card;
}

describe("Home capability truth", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it.each([
    ["available", "可使用"],
    ["local_only", "仅本地环境可用"],
    ["degraded", "能力受限"],
    ["unavailable", "当前环境不可用"],
  ] as const)("maps API status %s to %s", async (status, label) => {
    vi.spyOn(window, "fetch").mockResolvedValue(jsonResponse(capabilityResponse({
      p1: { status, reason_codes: [] },
    })));

    renderHome();

    expect(await within(capabilityCard("P1 文本知识治理")).findByText(label)).toBeVisible();
  });

  it("keeps reason codes folded in technical details and sends no auth header", async () => {
    setAuthSession("local-test-token");
    const fetchMock = vi.spyOn(window, "fetch").mockResolvedValue(jsonResponse(capabilityResponse({
      p1: { status: "degraded", reason_codes: ["AUTH_CONFIGURATION_INVALID"] },
    })));
    const user = userEvent.setup();

    renderHome();

    const p1 = capabilityCard("P1 文本知识治理");
    expect(await within(p1).findByText("能力受限")).toBeVisible();
    const authSummary = within(p1).getByText("技术详情");
    expect(within(p1).getByText("鉴权配置无效")).not.toBeVisible();
    await user.click(authSummary);
    expect(within(p1).getByText("鉴权配置无效")).toBeVisible();

    const p2 = capabilityCard("P2 素材文本投影治理");
    expect(await within(p2).findByText("仅本地环境可用")).toBeVisible();
    const summary = within(p2).getByText("技术详情");
    const details = summary.closest("details");
    expect(details).not.toHaveAttribute("open");
    expect(within(p2).getByText("ASSET_STORAGE_LOCAL_ONLY")).not.toBeVisible();
    await user.click(summary);
    expect(details).toHaveAttribute("open");
    expect(within(p2).getByText("ASSET_STORAGE_LOCAL_ONLY")).toBeVisible();

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(new Headers(init.headers).has("Authorization")).toBe(false);
  });

  it("falls back to unknown for P1-P3 while keeping P4 planned", async () => {
    vi.spyOn(window, "fetch").mockRejectedValue(new Error("capability service unavailable"));

    renderHome();

    for (const title of ["P1 文本知识治理", "P2 素材文本投影治理", "数据资产复用"]) {
      expect(await within(capabilityCard(title)).findByText("状态未知")).toBeVisible();
      expect(within(capabilityCard(title)).getByRole("button", { name: "进入模块" })).toBeEnabled();
    }
    const p4 = capabilityCard("P4 MCP + Agent 集群");
    expect(within(p4).getByText("规划中")).toBeVisible();
    expect(within(p4).queryByRole("button")).not.toBeInTheDocument();
    expect(p4).toHaveClass("disabled");
  });

  it.each([
    ["P1 文本知识治理", "/p1-text-hub", "P1 route"],
    ["P2 素材文本投影治理", "/p2-material-center", "P2 route"],
    ["数据资产复用", "/p3", "P3 route"],
    ["检索与 Agent 验证", "/retrieval-validation", "QA route"],
  ])("preserves the %s entry", async (title, path, target) => {
    vi.spyOn(window, "fetch").mockResolvedValue(jsonResponse(capabilityResponse()));
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route
            path="/"
            element={<HomePage backendStatus={backendStatus} onCheckBackend={vi.fn()} />}
          />
          <Route path={path} element={<div>{target}</div>} />
        </Routes>
      </MemoryRouter>,
    );

    const card = capabilityCard(title);
    await user.click(within(card).getByRole("button", { name: "进入模块" }));
    expect(await screen.findByText(target)).toBeVisible();
  });
});
