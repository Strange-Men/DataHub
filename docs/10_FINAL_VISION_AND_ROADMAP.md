# DataHub Final Vision And Roadmap

## 1. Final Positioning

DataHub is not only a customer service RAG tool. DataHub is a multi-source data governance and RAG knowledge platform for an Agent cluster.

中文定位：

```text
DataHub 不是单纯的客服 RAG 工具，而是面向 Agent 集群的多源数据治理与 RAG 知识中台。
```

Final positioning:

```text
DataHub | Multi-source data governance and RAG knowledge platform for Agent clusters
```

The long-term goal is:

```text
Multi-source business data
-> cleaning / desensitization / standardization
-> knowledge extraction / material understanding / human review
-> text + multimodal RAG knowledge base
-> data service APIs / MCP Tools
-> CustomerOpsAgent / SalesAgent / OpsAgent / MaterialAgent and other Agent consumers
```

Phase 1 serves CustomerOpsAgent first because the text customer service knowledge loop is the smallest useful closed loop. CustomerOpsAgent is the first core consumer, not the only final consumer.

## 2. Four-Phase Roadmap

中文正式路线：

```text
Phase 1：Text Customer Service Knowledge Loop
真实客服聊天记录
-> 清洗 / 去重 / 脱敏
-> FAQ / 标准回答 / 业务规则 / 转人工规则 / 禁答规则
-> 人工审核
-> 文本 RAG 知识库
-> CustomerOpsAgent 文本客服
-> Bad Case 回流

Phase 2：AI Material Center & Multimodal Knowledge
运营 Agent / AI 素材中心生成图片、视频、海报素材
-> 素材导入
-> OCR / Caption / 标签 / SKU 绑定
-> 人工审核
-> 多模态知识库
-> CustomerOpsAgent 图文 / 多模态客服

Phase 3：High-quality Dataset Export
已审核客服知识、优秀人工回复、Bad Case 修正、优质问答
-> 销售新人培训资料
-> FAQ 手册 / SOP / 话术手册 / 典型案例 / 测验题
-> SFT 数据集 / Preference 数据集
-> 用于降低 AI 客服 AI 味和提升品牌客服风格

Phase 4：MCP Tools & Agent Cluster Integration
DataHub 封装 MCP Tools
-> search_customer_knowledge
-> search_multimodal_assets
-> submit_bad_case
-> export_training_dataset
-> export_finetune_dataset
-> CustomerOpsAgent / SalesAgent / OpsAgent / MaterialAgent 统一调用
```

### Phase 1: Text Customer Service Knowledge Loop

```text
Real customer service chat records
-> cleaning / deduplication / desensitization
-> FAQ / standard answers / business rules / human-handoff rules / forbidden-answer rules
-> human review
-> text RAG knowledge base
-> CustomerOpsAgent text customer service
-> Bad Case feedback
```

Phase 1 proves the governed knowledge lifecycle:

- Raw data is separated from sanitized data.
- Sanitized data becomes knowledge candidates.
- Humans approve or reject candidates.
- Only approved knowledge can enter RAG.
- CustomerOpsAgent retrieves controlled knowledge.
- Bad Cases return to DataHub for correction.

### Phase 2: AI Material Center And Multimodal Knowledge

```text
Ops Agent / AI Material Center generated images, videos, and poster assets
-> material ingestion
-> OCR / Caption / tags / SKU binding
-> human review
-> multimodal knowledge base
-> CustomerOpsAgent image-text / multimodal customer service
```

Phase 2 extends DataHub from text knowledge governance into multimodal asset governance. The goal is not just to store images or videos, but to turn reviewed materials into retrievable business knowledge with traceable source metadata.

Expected capabilities:

- AI Material Center asset ingestion.
- Image and poster OCR.
- Caption generation or caption correction.
- Asset tags and business labels.
- SKU or product binding.
- Human review for material understanding.
- Multimodal retrieval preparation for CustomerOpsAgent.

### Phase 3: High-Quality Dataset Export

```text
Reviewed customer service knowledge, excellent human replies, Bad Case fixes, high-quality Q&A
-> new sales training materials
-> FAQ handbook / SOP / script handbook / typical cases / quiz questions
-> SFT dataset / Preference dataset
-> reduce AI flavor and improve brand voice, service style, and refusal rules
```

Phase 3 turns reviewed knowledge assets into training and improvement datasets.

Expected outputs:

- Sales onboarding FAQ handbooks.
- SOP documents.
- Customer service script handbooks.
- Typical case libraries.
- Quiz and assessment questions.
- Supervised fine-tuning dataset exports.
- Preference dataset exports.

This phase may support model improvement later, but Phase 3 does not mean DataHub itself must train models.

### Phase 4: MCP Tools And Agent Cluster Integration

```text
DataHub MCP Tools
-> search_customer_knowledge
-> search_multimodal_assets
-> submit_bad_case
-> export_training_dataset
-> export_finetune_dataset
-> CustomerOpsAgent / SalesAgent / OpsAgent / MaterialAgent unified access
```

Phase 4 packages DataHub capabilities as stable tools for the Agent cluster.

Potential tool layer:

- `search_customer_knowledge`
- `search_multimodal_assets`
- `submit_bad_case`
- `export_training_dataset`
- `export_finetune_dataset`

Expected consumers:

- CustomerOpsAgent
- SalesAgent
- OpsAgent
- MaterialAgent
- Future fine-tuning pipeline

## 3. Current Development Boundary

Current code development still only implements Phase 1.

Phase 2, Phase 3, and Phase 4 are formal product roadmap phases, but they must not be implemented early.

Current forbidden work remains:

- No full multimodal implementation.
- No image OCR, Caption, or SKU binding implementation.
- No video understanding.
- No sales training export implementation.
- No fine-tuning dataset export implementation.
- No MCP implementation.
- No SalesAgent, OpsAgent, or MaterialAgent integration.
- No enterprise big data platform expansion.

The roadmap should guide architecture decisions without breaking the small-step development discipline.

## 4. Target Architecture

```text
Data Sources
  - Customer chat logs
  - Product docs
  - Bad cases
  - AI Material Center assets
  - Human corrections

DataHub Core
  - Ingestion
  - Cleaning & Sanitization
  - Knowledge Extraction
  - Material Understanding
  - Human Review
  - Knowledge Asset Store
  - RAG Builder
  - Dataset Export
  - MCP Tool Layer

Consumers
  - CustomerOpsAgent
  - SalesAgent
  - OpsAgent
  - MaterialAgent
  - Fine-tuning pipeline
```

Current implementation covers only the early Phase 1 path:

```text
Customer chat logs
-> Ingestion
-> Cleaning & Sanitization
-> Knowledge Extraction
-> Human Review
-> Local RAG Builder
```

Future modules are real roadmap modules, not current implementation commitments.

## 5. Resume-Ready Project Positioning

中文简历表达：

```text
DataHub｜面向 Agent 集群的多源数据治理与 RAG 知识中台

设计并实现面向跨境电商 AI 应用的 DataHub 数据资产中心，支持从真实客服聊天记录中进行清洗、脱敏、知识抽取与人工审核，构建可追溯 RAG 知识库并供给 CustomerOpsAgent；项目架构预留 AI 素材中心、多模态知识库、销售培训数据导出、微调数据导出和 MCP Agent 集群调用能力，形成“数据治理—知识生产—Agent 调用—反馈回流”的 AI 数据闭环。
```

The Chinese resume wording must be used carefully: Phase 2, Phase 3, and Phase 4 are architecture reservations and later extensions, not completed features yet.

```text
DataHub | Multi-source data governance and RAG knowledge platform for Agent clusters

Designed and implemented a DataHub data asset center for cross-border e-commerce AI applications. The system supports cleaning, desensitization, knowledge extraction, and human review from real customer service chat records, builds a traceable RAG knowledge base, and provides knowledge to CustomerOpsAgent. The architecture reserves extension paths for AI Material Center integration, multimodal knowledge bases, sales training dataset export, fine-tuning dataset export, and MCP-based Agent cluster access, forming an AI data closed loop across data governance, knowledge production, Agent consumption, and feedback iteration.
```

Important wording rule:

- Current completed work should be described as Phase 1 text customer service knowledge governance.
- Phase 2, Phase 3, and Phase 4 should be described as architecture reservations or roadmap extensions unless they are actually implemented later.
