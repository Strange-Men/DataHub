# P1-P3-R1 契约冻结与平台架构决策

状态：已接受

日期：2026-08-03

适用版本：P1-P3-R1 及其后续四个顺序 Goal

## 1. 背景与目的

DataHub 已连续完成 P1、P2 与 P3-M8，但产品说明、运行时状态和部署基础设施之间仍存在偏差。本 ADR 冻结当前真实产品契约、数据所有权、检索隔离及后续实施顺序。它不改变 P1/P2/P3 业务状态机、检索排序、发布策略或数据结构，也不把尚未完成的能力描述为可用。

## 2. 产品定位与当前边界

### P1：客服文本知识治理中心

P1 接收聊天数据，完成规则清洗、PII 脱敏、人工清洗、知识候选抽取和人工审核，并只让已批准知识进入 P1 RAG。CustomerOpsAgent 默认只检索 P1，Bad Case 可回流到治理流程。

P1 当前仍保留 JSON/数据库兼容双写和 fallback。数据库单一真相源切换属于后续独立 Goal，本轮不得提前切换或大规模拆分 `storage.py`。

### P2：素材文本投影治理中心

P2 接收 JPEG、PNG 和 WebP 素材，管理素材、文本投影、人工修订、Snapshot、Knowledge Asset、发布和独立检索。当前正式 Extraction Provider 仍是 deterministic mock；因此 P2 的已交付价值是素材文本投影治理，而不是真实 OCR、Caption 或完整多模态理解。

本地 Docker 是当前 P2 权威运行与验收环境。未配置持久存储的非持久部署只能报告 `local_only`、`degraded` 或 `unavailable`，不得宣称 P2 在线完整可用。真实 OCR/Caption/Vision Provider 与云对象存储均属于后续 Goal。

### P3：已治理知识复用资产生产和交付中心

P3 只消费合格 P1、P2 或已批准 Bad Case 修正知识，生产 `training_material`、`sop`、`service_script`、`qa_bank`、`sft_dataset` 五类资产。它支持确定性草稿、显式开关控制的可选 LLM 草稿、人工修订、审核、发布以及 JSONL/CSV 导出。

P3 契约明确：`approved != published`，`published != RAG/Agent/training`，`export != training`。P3-M8 已完成中文前端工作流，但 P3-M9 最终质量封板尚未完成。

### P4：规划中

P4 MCP/Agent 尚未开始。未来 P4 只能消费当时的 current published P3 资产，不得绕过 P3 发布边界，也不得把历史或仅 approved 的资产视为当前交付物。

## 3. 输入、输出与数据所有权

| 阶段 | 输入 | 输出 | 数据所有者 | 允许写入范围 |
| --- | --- | --- | --- | --- |
| P1 | 原始客服聊天、人工治理动作、Bad Case 反馈 | 清洗文本、候选知识、approved P1 知识、P1 检索索引 | P1 | 仅 P1 数据、P1 索引及 P1 治理记录 |
| P2 | JPEG/PNG/WebP 素材及人工修订 | 文本投影、Snapshot、Knowledge Asset、P2 独立检索索引 | P2 | 仅 P2 数据、P2 文件引用及 P2 索引 |
| P3 | 合格 P1/P2/Bad Case 修正知识的只读引用 | 五类资产、版本、审核、发布记录、JSONL/CSV 导出 | P3 | 仅冻结的七张 P3 业务表及导出存储 |
| P4 | 未来的 current published P3 资产 | 尚未定义 | P4（未来） | 当前无写入权限，尚未实现 |

跨阶段引用不转移源数据所有权。P3 不回写 P1/P2，也不得改变源知识的审核、服务或检索状态。P3 的 published 资产不会自动进入 P1/P2 Retrieval、CustomerOpsAgent、训练或任何未来 Agent。

## 4. Retrieval 与协调层决策

1. P1 Retrieval 与 P2 Retrieval 保持物理隔离，分别维护索引、过滤条件和生命周期。
2. Unified Retrieval 只是一层显式 opt-in 的逻辑协调层，不是第三套物理索引，也不改变 P1/P2 排名、RRF、no-answer 阈值或 Embedding 语义。
3. CustomerOpsAgent 默认模式保持 P1-only；只有显式配置才能启用 Unified。
4. P3 不拥有或回写 P1/P2 Retrieval；P3 published 也不自动进入 Retrieval。

## 5. Runtime Capabilities 决策

`GET /api/capabilities` 是部署能力真相来源。前端不得再根据路由存在、构建成功或静态文案推断模块可用。

能力状态必须综合当前环境、数据库、已安装 pgvector、存储后端及其 readiness、Auth 安全配置、Feature Flag 与模块实现状态。探针必须只读、无业务写入、无 DDL、无真实 Provider 调用，并只返回稳定状态与安全 reason code；不得泄露 Token、API Key、数据库 URL、绝对路径、用户数据、Provider Secret 或完整内部异常。

P4 在当前所有环境始终报告 `planned`。P3 LLM Draft 默认关闭，Unified Retrieval 默认关闭，CustomerOpsAgent 默认 P1-only。

## 6. 本地与生产安全边界

- `local`/`test` 可显式使用 Auth disabled，以保持现有开发和测试兼容性。
- `staging`/`production` 必须 fail closed：Auth disabled 或 token 配置无效时，拒绝启动或让 readiness 失败；不得自动降级为 disabled。
- Token 只通过受支持的认证头传递，不接受 query string，不打印或回显 Secret。
- 本地 Docker 验收证明本地权威环境可用，不等于生产部署验收。
- CI 通过证明提交的质量门禁通过，不等于生产环境、持久存储或真实 Provider 已验收。

## 7. Schema、Migration 与启动所有权

应用 import、正常 startup 和 Health 不拥有 DDL。正式 Schema、pgvector extension 与兼容变更必须由 Alembic Migration 或显式管理员命令管理。已有数据库只有在 Schema 等价验证完全通过后才允许安全 stamp；不匹配时 fail closed，不得无条件接管或重建。

P3 保持精确七张冻结业务表；`alembic_version` 是平台版本表，不属于 P3 业务表。任何后续 Migration 不得隐式新增第八张 P3 业务表。

## 8. 后续工作冻结顺序

后续工作严格按以下四个 Goal 顺序推进：

1. 契约与基础设施加固（本 P1-P3-R1）。
2. P1 数据层单一真相源，移除 JSON/数据库双写与 fallback 技术债。
3. P2/P3 核心缺口修复，包括真实 Provider、持久存储及明确批准的能力缺口。
4. P1-P3 最终统一封板，包括 P3-M9 质量封板。

不得在 Goal 1 中提前进入 Goal 2～4，也不得开始 P4。

## 9. 结果与已知限制

本决策统一了文档和后续平台实现的事实来源，但不代表未交付能力已完成。当前明确保留的限制包括：P1 JSON/数据库双写和 fallback、P2 deterministic mock、P2 云对象存储缺失、P3-M9 未完成、P4 未开始、OIDC/OAuth 与自然人身份审计未实现。

历史 Release 报告记录的是各里程碑当时的真实结论，保持原文，不以本 ADR 回写或重新解释历史验收结果。
