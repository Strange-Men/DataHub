import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getCapabilities } from "../capabilities/client";
import type {
  CapabilityDisplayStatus,
  CapabilityModuleDisplayState,
  CapabilityModuleKey,
} from "../capabilities/types";
import type { BackendStatus } from "../types";

const STATUS_LABELS: Record<CapabilityDisplayStatus, string> = {
  available: "可使用",
  local_only: "仅本地环境可用",
  degraded: "能力受限",
  unavailable: "当前环境不可用",
  unknown: "状态未知",
  planned: "规划中",
};

const REASON_CODE_LABELS: Record<string, string> = {
  DATABASE_UNAVAILABLE: "数据库不可用",
  PGVECTOR_UNAVAILABLE: "向量检索扩展不可用",
  ASSET_STORAGE_UNAVAILABLE: "素材存储不可用",
  ASSET_STORAGE_LOCAL_ONLY: "素材存储仅限本地",
  EXPORT_STORAGE_UNAVAILABLE: "导出存储不可用",
  EXPORT_STORAGE_LOCAL_ONLY: "导出存储仅限本地",
  AUTH_CONFIGURATION_INVALID: "鉴权配置无效",
  AUTH_UNSAFE_FOR_ENVIRONMENT: "当前环境的鉴权配置不安全",
  NOT_IMPLEMENTED: "尚未实现",
};

interface CapabilityCardDefinition {
  title: string;
  badge: string;
  description: string;
  path: string;
  module: CapabilityModuleKey | null;
  entryDisabled: boolean;
}

const CAPABILITY_CARD_DEFINITIONS: CapabilityCardDefinition[] = [
  {
    title: "P1 文本知识治理",
    badge: "P1",
    description: "导入、机器清洗、人工修订、知识审核、RAG 同步、Agent 验证与 Bad Case 回流。",
    path: "/p1-text-hub",
    module: "p1",
    entryDisabled: false,
  },
  {
    title: "P2 素材文本投影治理",
    badge: "P2",
    description: "治理 JPEG、PNG、WebP 素材的文本投影、人工修订、Snapshot、发布、独立检索与归档。",
    path: "/p2-material-center",
    module: "p2",
    entryDisabled: false,
  },
  {
    title: "数据资产复用",
    badge: "P3",
    description: "把已审核知识整理为培训材料、SOP、客服话术、问答题库或数据集，并保留来源与审核记录。",
    path: "/p3",
    module: "p3",
    entryDisabled: false,
  },
  {
    title: "P4 MCP + Agent 集群",
    badge: "P4",
    description: "MCP 与多 Agent 协作能力将在后续阶段规划。",
    path: "/p4-mcp-agents",
    module: "p4",
    entryDisabled: true,
  },
  {
    title: "检索与 Agent 验证",
    badge: "QA",
    description: "验证 P1、P2、联合检索和客服 Agent 的召回、引用与安全拒答效果。",
    path: "/retrieval-validation",
    module: null,
    entryDisabled: false,
  },
];

function fallbackCapabilityState(): CapabilityModuleDisplayState {
  return {
    p1: { status: "unknown", reasonCodes: [] },
    p2: { status: "unknown", reasonCodes: [] },
    p3: { status: "unknown", reasonCodes: [] },
    p4: { status: "planned", reasonCodes: ["NOT_IMPLEMENTED"] },
  };
}

export function HomePage({
  backendStatus,
  onCheckBackend,
}: {
  backendStatus: BackendStatus;
  onCheckBackend: () => void;
}) {
  const navigate = useNavigate();
  const [capabilityState, setCapabilityState] = useState<CapabilityModuleDisplayState>(
    fallbackCapabilityState,
  );
  const [capabilityRefresh, setCapabilityRefresh] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setCapabilityState(fallbackCapabilityState());
    void getCapabilities(controller.signal)
      .then((response) => {
        setCapabilityState({
          p1: { status: response.modules.p1.status, reasonCodes: [...response.modules.p1.reason_codes] },
          p2: { status: response.modules.p2.status, reasonCodes: [...response.modules.p2.reason_codes] },
          p3: { status: response.modules.p3.status, reasonCodes: [...response.modules.p3.reason_codes] },
          p4: { status: response.modules.p4.status, reasonCodes: [...response.modules.p4.reason_codes] },
        });
      })
      .catch(() => {
        if (!controller.signal.aborted) setCapabilityState(fallbackCapabilityState());
      });
    return () => controller.abort();
  }, [capabilityRefresh]);

  const capabilityCards = CAPABILITY_CARD_DEFINITIONS.map((definition) => {
    const state = definition.module
      ? capabilityState[definition.module]
      : { status: "available" as const, reasonCodes: [] };
    return { ...definition, ...state };
  });

  function recheckPlatform() {
    onCheckBackend();
    setCapabilityRefresh((value) => value + 1);
  }

  return (
    <div className="home-page">
      <section className="hero-section">
        <div className="hero-copy">
          <span className="hero-eyebrow">P1/P2/P3 GOVERNANCE WORKSPACE</span>
          <h1 className="hero-title">DataHub 数据治理与 RAG 知识中台</h1>
          <p className="hero-desc">治理客服文本、素材文本投影与复用资产，并验证检索可见性、来源和安全拒答。</p>
        </div>
        <div className="hero-status-bar" aria-label="平台状态">
          <span><i className={`conn-indicator ${backendStatus.state}`} />{backendStatus.state === "connected" ? "服务正常" : backendStatus.state === "checking" ? "连接中" : "服务暂不可用"}</span>
          <span aria-live="polite"><strong>能力状态</strong> P1 {STATUS_LABELS[capabilityState.p1.status]} · P2 {STATUS_LABELS[capabilityState.p2.status]} · P3 {STATUS_LABELS[capabilityState.p3.status]}</span>
          <span><strong>P4</strong> {STATUS_LABELS[capabilityState.p4.status]}</span>
          <button type="button" className="btn-small" onClick={recheckPlatform}>重新检测</button>
        </div>
      </section>

      <section className="capability-grid">
        <h2 className="section-title">平台能力</h2>
        <div className="capability-cards">
          {capabilityCards.map((card) => (
            <article
              key={card.title}
              className={`capability-card ${card.entryDisabled ? "disabled" : ""}`}
              data-capability-status={card.status}
            >
              <span className="capability-mark" aria-hidden="true">{card.badge}</span>
              <h3>{card.title}</h3>
              <p>{card.description}</p>
              {card.reasonCodes.length > 0 && (
                <details className="capability-technical-details">
                  <summary>技术详情</summary>
                  <ul>
                    {card.reasonCodes.map((reasonCode) => (
                      <li key={reasonCode}>
                        <code>{reasonCode}</code>
                        <span>{REASON_CODE_LABELS[reasonCode] ?? "后端能力门禁"}</span>
                      </li>
                    ))}
                  </ul>
                </details>
              )}
              <div className="capability-footer">
                <span className={`capability-status status-${card.status}`} aria-live="polite">
                  {STATUS_LABELS[card.status]}
                </span>
                {!card.entryDisabled && (
                  <button type="button" className="btn-primary btn-sm" onClick={() => navigate(card.path)}>
                    进入模块
                  </button>
                )}
              </div>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
