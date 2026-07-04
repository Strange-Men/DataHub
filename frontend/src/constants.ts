import type { Intent, KnowledgeType, ReviewStatus, RiskLevel, SourceType } from "./types";

export const reviewStatusLabels: Record<ReviewStatus, string> = {
  pending_review: "待审核",
  needs_revision: "需修改",
  approved: "已通过",
  rejected: "已驳回",
};

export const sourceTypeLabels: Record<SourceType, string> = {
  sanitized_batch: "清洗批次",
  chat_logs: "客服聊天",
  public_dataset: "公开数据集",
  bad_case: "坏例回流",
  legacy_rag: "旧 RAG 迁移",
  manual: "人工录入",
  unknown: "未知来源",
};

export const riskLabels: Record<RiskLevel, string> = {
  low: "低风险",
  medium: "中风险",
  high: "高风险",
};

export const knowledgeTypeLabels: Record<string, string> = {
  faq: "FAQ",
  standard_answer: "标准回答",
  business_rule: "业务规则",
  human_handoff_rule: "转人工规则",
  escalation_rule: "转人工规则",
  forbidden_answer_rule: "禁答规则",
  forbidden_rule: "禁答规则",
};

export const intentLabels: Record<Intent, string> = {
  shipping: "物流配送",
  refund: "退款退货",
  order_status: "订单状态",
  product_info: "商品信息",
  handoff: "转人工",
  prohibited_answer: "禁答规则",
  general: "通用",
};

export const reviewStatusOptions: ReviewStatus[] = [
  "pending_review",
  "needs_revision",
  "approved",
  "rejected",
];

export const sourceTypeOptions: SourceType[] = [
  "chat_logs",
  "public_dataset",
  "bad_case",
  "legacy_rag",
  "manual",
  "unknown",
];

export const intentOptions: Intent[] = [
  "shipping",
  "refund",
  "order_status",
  "product_info",
  "handoff",
  "prohibited_answer",
  "general",
];

export const riskOptions: RiskLevel[] = ["low", "medium", "high"];

export const SAMPLE_JSON = {
  source_name: "sample_customer_chat",
  conversations: [
    {
      conversation_id: "conv_001",
      messages: [
        {
          message_id: "msg_001",
          role: "customer",
          content: "我想问一下，从中国发货到德国大概需要多长时间？",
          timestamp: "2026-07-03T10:00:00",
        },
        {
          message_id: "msg_002",
          role: "agent",
          content: "您好，从中国发货到德国通常需要 7-12 个工作日，具体时效取决于物流方式和清关速度。我们会为您选择最快的物流渠道。",
          timestamp: "2026-07-03T10:01:00",
        },
      ],
    },
    {
      conversation_id: "conv_002",
      messages: [
        {
          message_id: "msg_003",
          role: "customer",
          content: "我买的产品有质量问题，怎么退货？退款多久能到账？",
          timestamp: "2026-07-03T10:05:00",
        },
        {
          message_id: "msg_004",
          role: "agent",
          content: "很抱歉给您带来不便。我们的退货流程是：1）在订单页面提交退货申请；2）将商品寄回我们的仓库；3）仓库收到后 3-5 个工作日完成退款。如果您需要帮助，我可以帮您直接发起退货流程。",
          timestamp: "2026-07-03T10:06:00",
        },
      ],
    },
  ],
};

export function qualityLevel(score: number): "high" | "medium" | "low" {
  if (score >= 0.8) return "high";
  if (score >= 0.5) return "medium";
  return "low";
}

export function qualityLabel(level: "high" | "medium" | "low") {
  if (level === "high") return "高质量";
  if (level === "medium") return "需复核";
  return "低质量";
}

export function suggestedActionLabel(action: string) {
  const labels: Record<string, string> = {
    keep: "建议保留",
    review: "建议复核",
    drop: "建议丢弃",
    keep_edited: "修改后保留",
    needs_review: "需要复核",
  };
  return labels[action] || action;
}
