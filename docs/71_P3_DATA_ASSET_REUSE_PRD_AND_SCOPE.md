# P3 数据资产复用 PRD 与范围

> 状态：P3-M0.1 规划审核通过并冻结；P3-M1 尚未开始。
> 基线：`3a969c3d63b195caccd7c987fe108c3e809c7066`。
> 约束：本文只定义产品范围，不代表 API、数据库、前端或运行能力已经实现。

## 1. 背景与业务问题

P1 已形成审核通过的文本知识，P2 已形成带 Review、Snapshot、Knowledge Asset 和完整来源链的多模态文本投影知识。现阶段这些高质量知识主要服务于检索和 Agent，培训资料、SOP、客服话术和指令数据集仍依赖人工复制、二次整理和离线文件，存在以下问题：

- 同一知识被多次复制后失去版本关系，无法判断是否仍为当前有效版本。
- 培训资料和数据集常缺少来源、审核人、审核时间和内容指纹。
- Bad Case 修正结果可能在尚未通过知识审核时被误当作正式答案。
- 生成式改写可能改变事实、遗漏限制条件或带入个人信息。
- JSONL/CSV 导出缺少统一 schema、去重、可复现和撤回机制。
- 已归档或已被新版本替代的知识可能继续进入新资产。

P3 的任务是把已经治理完成的知识转化为新的、独立审核和版本化的复用资产，而不是绕过或替代 P1/P2 治理。

## 2. 产品定位

P3 名称为“数据资产复用”，定位为 P1/P2 下游的受治理再生产层：

```text
P1/P2 已审核知识
-> P3 来源资格判定与不可变来源快照
-> 复用项目与模板
-> 草稿生成/人工编辑
-> P3 独立人工审核
-> 发布复用资产
-> 可复现导出与撤回记录
```

P3 的核心价值不是“自动生成更多内容”，而是“在不污染源知识的前提下，可追溯、可审核、可版本化地复用高质量知识”。

## 3. P1、P2、P3、P4 边界

| 阶段 | 负责 | 不负责 | P3 关系 |
|---|---|---|---|
| P1 文本知识治理 | 文本清洗、候选知识、人工审核、RAG、Bad Case 回流 | 培训资料和数据集资产发布 | P3 只读已审核知识和审核证据 |
| P2 多模态知识治理 | Asset、Extraction、Review、Snapshot、Knowledge Asset、索引与 Serving | 培训资料和模型训练 | P3 只读已审核且已发布的当前 Knowledge Asset |
| P3 数据资产复用 | 复用任务、草稿、编辑、复审、发布、JSONL/CSV 导出 | 模型训练、P1/P2 治理、Agent 集群 | 本阶段范围 |
| P4 MCP 与 Agent 集群 | 工具契约、Agent 调用和编排 | 替代 P3 审核或直接修改 P1/P2 | 未来只能读取 P3 已发布资产和可用导出 |

强制边界：

- P3 不更新 P1/P2 业务表的状态、内容、版本、索引或 Serving 状态。
- P3 不把生成内容写回 P1/P2，不自动创建或批准 P1/P2 知识。
- P3 不使用 raw、sanitized、pending、rejected、archived、superseded 或来源链不完整的数据生成正式资产。
- P3 不改变 CustomerOpsAgent 的 P1-only 默认，不改变 Unified 显式 opt-in。
- Render P2 持久化仍为 BLOCKED；P3 权威开发和验收环境仍为本地 Docker。

## 4. 目标用户

| 用户 | 主要任务 | v1 权限映射建议 |
|---|---|---|
| 数据管理员 | 配置模板、管理项目、处理撤回和归档 | `admin` |
| 清洗人员 | 选择来源、生成和编辑草稿 | `cleaner` |
| 审核人员 | 审核复用草稿、要求修订、批准 | `reviewer` |
| 培训资料负责人 | 维护培训资料、SOP、标准话术 | v1 复用 `cleaner`；正式发布由 `admin` |
| 数据集导出负责人 | 选择已发布数据集版本并执行导出/撤回 | v1 由 `admin` 承担 |
| 只读观察者 | 查看项目、资产、版本和来源追踪 | `viewer` |

P3 v1 不新增认证角色：发布、导出和 Artifact revoke 由 `admin` 承担；稳定个人身份和独立 `publisher`/`exporter` 角色作为生产化 Deferred。

## 5. 产品原则

1. 只有通过来源资格判定的知识才能加入复用项目。
2. 每次提交审核、发布和导出前都重新判定来源资格，不能只依赖创建项目时的结果。
3. 生成结果永远先是草稿，不能自动成为批准或发布资产。
4. P3 的批准不等于发布；发布必须是独立、显式、可审计操作。
5. P3 的内容、审核、版本和导出记录独立于 P1/P2。
6. 每个已发布版本和每个导出样本必须具有完整 Source Trace。
7. 已归档来源和旧版本不能进入新发布或新导出。
8. LLM 只能做受约束改写和编排，不得无来源补充事实。
9. 正式资产和导出不得包含未经批准的真实聊天、个人信息、Secret 或内部敏感字段。
10. 所有失败均保持可回滚，不产生半发布资产、半成品导出或 P1/P2 状态变化。

## 6. 核心用户场景

### 6.1 新人培训资料

培训负责人选择一组已审核 FAQ、业务规则和标准话术，使用“新人培训”模板生成章节草稿，人工调整顺序和表达，经审核后发布为版本化培训资产。

### 6.2 SOP 操作手册

清洗人员选择同一业务流程下的当前规则，按步骤、前置条件、异常分支和升级路径组织为 SOP。任何缺失的步骤必须标为“待补充”，不能由模型猜测。

### 6.3 客服标准话术

从已批准标准答案、禁答规则和人工转接规则中生成场景话术。正式发布前审核品牌语气、事实、风险提示和禁用表达。

### 6.4 场景化问答题库

从已确认优质问答构造题目、参考答案、考点和来源引用。题目可以改写，答案事实不得脱离来源。

### 6.5 指令微调数据集

把已发布的 P3 数据集资产规范化为 instruction/input/output 样本，经字段校验、去重、敏感信息扫描和人工审核后导出 JSONL 或 CSV。P3 不执行模型训练。

### 6.6 Bad Case 修正复用

Bad Case 本身不能直接成为来源。只有由 Bad Case 生成的 P1 Knowledge Candidate 完成 P1 人工审核并处于 `approved` 后，才能以该 Candidate 为正式来源，并在 Source Trace 中保留 Bad Case、Retrieval 和原 Chunk 的引用关系。

## 7. P3 输入来源与资格

### 7.1 合法来源

| 来源 | 合法对象 | 必须满足 |
|---|---|---|
| P1 已审核知识 | `KnowledgeCandidate` | 当前状态 `approved`；存在 approved Review 证据；当前业务字段与批准快照指纹一致；来源链完整 |
| P2 知识资产 | `KnowledgeAsset` | `status=active`；是同一 `asset_id + content_type` 的当前最高有效版本；上游 Review 为 `approved`；Source Trace 完整 |
| Bad Case 修正 | 来源类型为 `bad_case` 的 P1 `KnowledgeCandidate` | Candidate 已 approved；`source_bad_case_id` 有效；Bad Case 为 `resolved` 且关联 Candidate 一致 |
| 优质问答 | P1 approved FAQ/standard answer，或符合相同治理条件的 P2 当前 Knowledge Asset | 问题/答案完整；来源合格；结构性质量规则和敏感信息检查通过 |
| 业务规则/FAQ/标准话术 | P1 approved 对象或 P2 active 当前 Knowledge Asset | 类型匹配；来源合格；不含归档或旧版本 |

### 7.2 明确不合法的来源

- P1 `pending_review`、`needs_revision`、`rejected` Candidate。
- 只有 `BadCase.status=resolved`、但其修正 Candidate 尚未 approved 的记录。
- P2 draft/archived Knowledge Asset。
- 已被新 Knowledge Asset 版本替代的旧 active/archived 版本。
- P2 只有 Extraction 或 Snapshot、但尚未发布为 active Knowledge Asset 的内容。
- raw chat、sanitized message、Retrieval Log、模型回答和未确认“优质”的问答。
- 任意 P3 资产；P3 v1 禁止把 P3 输出再次作为 P3 来源，避免循环 lineage。
- 来源追踪缺失、内容指纹不一致、敏感信息检查未通过的内容。

### 7.3 P2 ready 但未 serving

**结论：可以被 P3 使用，但必须满足 P2 Knowledge Asset 已审核、已发布、current、non-archived。**

理由：`ready/serving` 是 P2 检索开放门禁，`active` Knowledge Asset 和 approved Review 是治理发布门禁。P3 复用的是已治理内容，不依赖其是否已开放向量检索。P3 按 approved + published/current/non-archived 判断，不按 serving 判断。`serving` 仅可作为 Source Trace 中的观察字段，不能扩大或缩小 P3 资格。

### 7.4 P1 current 判定补偿

当前 P1 没有独立版本/归档模型，且 Candidate 是可更新行。P3 不修改 P1，而是在适配器中使用更严格的只读规则：

- 读取 `KnowledgeCandidate.status=approved`。
- 读取该 Candidate 最新的 approved `ReviewRecord` 及其 `snapshot_json`。
- 对 question、answer、intent、tags、risk_level、knowledge_type 等批准字段计算规范化指纹。
- 当前 Candidate 指纹必须与 approved Review 快照指纹一致；不一致时返回 `SOURCE_APPROVAL_DRIFT`，要求先回到 P1 重新审核。
- P3 捕获不可变来源快照和指纹；后续正式操作仍须再次检查源行没有失效或漂移。

这是一项 P3 读取侧保护，不改变 P1 冻结状态。

## 8. 输出资产

| `asset_kind` | 中文名称 | 规范内容 |
|---|---|---|
| `training_material` | 新人培训资料 | 章节、学习目标、正文、案例、检查题、引用 |
| `sop` | SOP 操作手册 | 适用范围、前置条件、步骤、异常分支、升级规则、引用 |
| `service_script` | 客服标准话术 | 场景、标准表达、禁用表达、转人工条件、引用 |
| `qa_bank` | 场景化问答题库 | 题目、参考答案、考点、难度、引用 |
| `sft_dataset` | 指令微调数据集 | instruction/input/output/system/metadata/source_refs |

共同规则：

- 上述类型共用版本、审核、发布、归档和 Source Trace 框架。
- `sft_dataset` 使用独立的类型化内容 schema、样本去重和导出验证，不能把普通 Markdown 资料直接改名为数据集。
- v1 正式内容以结构化 JSON 和可读 Markdown 投影保存；PDF/DOCX/PPTX 生成延期。

## 9. 完整用户流程

```text
浏览合格来源
-> 创建复用项目
-> 选择并冻结来源快照
-> 选择输出类型与模板版本
-> 确定性生成或显式选择 LLM Provider，形成 generated 版本
-> 人工编辑
-> 提交 P3 审核
-> 审核退修或批准
-> 管理员显式发布
-> 对已发布当前版本执行导出
-> 校验、生成 Artifact 和 Manifest
-> 下载、追踪、必要时撤回/归档
```

关键交互：

- 来源加入时显示“合格/不合格”和具体原因。
- generated/needs_revision 页面始终显示“非正式资产”。
- 审核页展示当前内容、上一版本 diff、全部引用和资格重检结果。
- 发布按钮只对 approved 当前版本可用。
- 导出按钮只对 published、non-archived、来源仍合格的版本可用。
- 所有 P3 页面和错误提示使用中文；技术 ID 放在可展开的来源追踪区。

### 9.1 冻结状态模型

三类状态分别归属不同对象，禁止混用：

- `ReuseProject`：`draft -> active -> archived`。
- `ReuseAssetVersion`：`generating -> generated -> pending_review -> approved -> published`，并具有 `needs_revision`、`rejected`、`failed` 分支；新版本发布时旧 published 版本进入 `superseded`，当前版本可被显式 `archived`。
- `ExportJob`：`pending -> running -> succeeded | failed`，成功导出可由 admin 逻辑转为 `revoked`。

冻结语义：

- `generated` 只是模板或机器生成结果，可编辑但不是已审核资产。
- `approved` 不等于 `published`，二者必须由不同显式操作产生。
- `published` 内容不可直接覆盖；修改必须创建同一 Project/asset kind 的下一版本。
- 同一 Project 和 `asset_kind` 最多一个 current published 版本。
- `superseded`、`archived`、`source_stale` 版本禁止新发布和新导出。

## 10. In Scope

- P1/P2 合法来源的只读查询和统一资格判定。
- 复用项目、来源选择和不可变来源快照。
- 培训资料、SOP、话术、问答题库和 SFT 数据集模板。
- 确定性草稿生成。
- 可选、显式配置的 LLM 草稿生成 Provider。
- 草稿编辑、并发保护、人工审核、版本和发布。
- Source Trace、来源指纹、审核记录和发布记录。
- JSONL/CSV 导出、格式校验、去重、Artifact/Manifest、逻辑撤回。
- PII/敏感信息/禁用内容检测门禁。
- 中文 P3 任务流。
- 本地 Docker 独立测试和 P1/P2 回归保护。

## 11. Out of Scope

- 模型训练、微调任务执行、训练集上传到外部平台。
- 新增 OCR、Caption、Vision LLM 或原生多模态 Embedding。
- 修改 P1/P2 原始内容、审核、状态、索引或检索逻辑。
- 默认切换 CustomerOpsAgent 或 Unified。
- P4 MCP Server、工具注册、Agent 集群和自动调用。
- 自动批准、自动发布、自动导出正式资产。
- 未审核或已归档知识的“临时例外”。
- 真实聊天、隐私数据、Secret 或企业业务数据随代码提交。
- Render P2/P3 持久化上线声明。
- PDF/DOCX/PPTX、偏好数据集/DPO、自动合成负样本和跨语言批量生成。

## 12. 权限和角色

能力权限继续集中定义，不在路由中散落角色判断：

| 角色 | P3 v1 权限 |
|---|---|
| `cleaner` | 创建/维护 Project、选择合法来源、生成和编辑 generated/needs_revision 内容、提交审核 |
| `reviewer` | 只读项目和来源、对 pending_review 执行 needs_revision/approved/rejected |
| `admin` | 全部 P3 权限，包括发布、supersede、archive、导出和 revoke Artifact |
| `viewer` | 只读项目、版本、审核结果、Source Trace 和导出状态 |
| `service` | 仅执行被明确授权的生成或导出后台任务；不能人工审核、直接发布、archive 或 revoke |

约束：

- P3 v1 不新增认证角色；发布/导出职责固定由 admin 承担。
- 当前认证系统没有真实用户账户，无法可靠强制“提交者与审核者不是同一自然人”；该能力明确 Deferred。
- service 只允许调用专用后台任务能力，不继承 reviewer/admin 的人工治理权限。
- Auth disabled 仍仅用于受信本地兼容；Docker 正式验收使用 token 模式。

## 13. 数据安全

- P3 只捕获复用所需的治理后内容和最小来源元数据，不复制 raw chat、完整 Retrieval Log、Token、数据库 URL 或二进制素材。
- v1 审计字段只记录 `actor_role`、`request_id` 和 UTC 时间，不存储 Token、Token Hash、真实姓名或伪造的个人 ID。
- 生成前、审核前、发布前和导出前运行 PII/Secret/禁用内容检测。
- 检测到 PII 时硬阻断正式发布和导出；只能返回字段位置和规则 ID，不在日志重复原文。
- LLM Provider 请求使用最小内容集，不发送 raw 来源；Provider、模型、Prompt 模板版本和响应哈希必须记录，密钥只来自运行时 Secret。
- 下载 Artifact 使用授权接口，不能暴露本地绝对路径或对象存储内部 URI。
- 日志只记录 ID、状态、计数、哈希前缀和安全错误码。
- 测试、示例和文档只能使用合成数据。

## 14. 成功指标与门禁

### 14.1 数据资格

| 指标 | 定义 | P3-M9 硬门禁 |
|---|---|---:|
| invalid source rate | 进入正式审核的来源中不满足资格的比例 | 0 |
| archived source leakage | 新发布/新导出中来自已归档源的数量 | 0 |
| old-version leakage | 新发布/新导出中来自非当前源版本的数量 | 0 |
| source trace coverage | 已发布版本和样本具备完整 Trace 的比例 | 100% |
| duplicate source rate | 同一项目内重复 canonical source 的比例 | 0 |

### 14.2 生成质量

| 指标 | 定义 | 冻结策略 |
|---|---|---:|
| factual consistency | 审核样本中可由来源直接支持的事实比例 | M1～M8 执行“无法由来源证明即阻断”的结构性门禁；数值阈值在 M9 用独立挑战集校准 |
| required field completeness | 模板必填字段完整比例 | 100% |
| citation coverage | 可验证陈述具有来源引用的比例 | 100% |
| reviewer approval rate | 首次提交被批准的比例 | 记录基线；不以提高批准率替代质量 |
| revision rate | 被要求修订的提交比例 | 记录基线并按模板/Provider 分层 |

### 14.3 数据集质量

| 指标 | 定义 | P3-M9 硬门禁 |
|---|---|---:|
| duplicate sample rate | 最终 Artifact 内规范化重复样本比例 | 0 |
| invalid JSONL rate | 不能按 schema 解析的行比例 | 0 |
| instruction/answer completeness | instruction 与 output 非空比例 | 100% |
| forbidden content rate | 命中禁用内容的导出样本比例 | 0 |
| PII leakage rate | 导出中未脱敏个人信息比例 | 0 |
| source coverage | 样本至少有一个完整来源引用的比例 | 100% |

### 14.4 工程质量

| 指标 | 门禁 |
|---|---|
| full test count | Release Closure 记录实际 collected/passed/skipped；失败数为 0，skip 必须逐项说明 |
| transaction rollback | 故障注入场景 100% 无半状态、无 P1/P2 写入 |
| idempotency | 同一 key 重放 100% 返回同一资源，不重复生成 |
| export reproducibility | 相同发布快照、模板/导出配置产生字节一致 Artifact 和相同 checksum |
| cleanup safety | 只清理带当前 test run scope 的 P3 测试数据；误删业务数据为 0 |
| Secret leakage | Git、日志、响应、Artifact、Manifest 中为 0 |

## 15. 已知限制

- 当前 P1 缺少独立版本/归档模型，P3 只能通过批准快照指纹一致性补偿，不能把 P1 直接描述为完整版本系统。
- 现有 Token RBAC 只有角色，没有稳定用户 ID；“提交者不得自审”需要身份能力后才能完全强制。
- LLM 事实一致性不能仅靠自动指标证明，正式资产仍依赖人工审核。
- 已下载到外部系统的导出文件无法物理召回；P3 v1 不自动删除历史 Artifact，由 admin 逻辑 revoke 后阻断后续系统内下载并保留撤回记录。
- Render P2 持久化未完成，P3 的发布声明仅覆盖本地 Docker。
- v1 不建设 P3 向量索引，大规模项目的来源浏览性能需在真实数据量下复评。

## 16. Deferred 能力

- 独立 publisher/exporter 角色、OIDC、用户身份生命周期和审批分离。
- PDF、DOCX、PPTX、SCORM 等培训交付格式。
- DPO/偏好数据、多轮对话数据、自动负样本和跨语言生成。
- 外部对象存储、签名下载、长期归档和企业 DLP 集成。
- P3 独立全文/向量检索索引和大规模异步队列。
- 来源失效的主动订阅/事件总线；v1 在审核批准、发布和新导出时重检。
- P4 MCP published-only 工具实现。

## 17. 明确验收条件

P3 最终验收必须同时满足：

1. 只能列出并选择合法来源，不合格来源返回稳定原因码。
2. P1 approved 快照漂移、P2 archived/旧版本、未审核 Bad Case 修正均被阻断。
3. P2 active/current/approved 但 ready-not-serving 的 Knowledge Asset 可以使用。
4. 每个草稿明确为非正式内容；生成不能越过人工编辑和审核。
5. approved 和 published 是两个独立状态与操作。
6. 每个发布版本都保存不可变内容、版本号、审核记录和完整 Source Trace。
7. 每次审核批准、发布和新导出前重新验证来源；失效后标记 `source_stale`，不能新发布或产生新 Artifact。
8. 普通资料与 SFT 数据集共用治理框架，但使用不同内容 schema 和校验器。
9. JSONL/CSV 可重复生成、格式合法、去重后无重复样本，Manifest 和 checksum 完整。
10. PII、禁用内容和 Secret 泄漏均为 0。
11. 并发审核/发布/导出满足幂等和事务回滚要求。
12. 中文前端完成来源、项目、草稿、审核、发布和导出任务流，不展示假按钮。
13. P1/P2 全量回归门禁通过，CustomerOpsAgent 默认和 Unified opt-in 不变。
14. 本地 Docker 独立测试通过且不接触保留开发卷。
15. P4 不得读取 generated/approved 未发布版本，不得调用 P3 内部治理写接口。

## 18. 关键设计结论

1. **P3 需要新增数据库表**，因为项目、来源快照、P3 版本、审核、发布和导出审计不能安全塞入 P1/P2 表或无版本文件。
2. 合法来源只有 P1 approved Candidate（含 approved Bad Case 修正）和 P2 approved + active/current Knowledge Asset；P3 v1 禁止 P3 资产再次作为 P3 来源。
3. approved/current/non-archived 由统一资格策略、不可变来源快照和正式操作前重检共同保证。
4. P2 ready 但未 serving 可以使用；P3 不按 serving 判断治理资格。
5. Bad Case 不能直接使用，必须通过其修正 Candidate 的 P1 审核。
6. 优质问答至少要求 approved、内容完整、来源合格、敏感检查通过；M1～M8 使用结构性门禁，最终数值质量阈值在 M9 独立校准。
7. 所有生成资料必须再次经过 P3 人工审核。
8. SOP、培训资料、话术和问答题库共用治理/版本模型，通过 `asset_kind` 和类型化内容 schema 区分。
9. 指令数据集使用独立 `sft_dataset` schema、样本级 Source Trace、去重和导出验证。
10. LLM 不允许无来源改写事实；不能确认的内容必须保留原文或标记待人工补充。

## 19. 已冻结决策与生产化 Deferred

P3 v1 已冻结：

1. M1～M8 使用结构性质量门禁，M9 才用独立挑战集校准最终数值阈值。
2. 不新增认证角色；admin 负责发布、导出和 revoke。
3. 数据库升级沿用现有 SQLAlchemy additive `create_all(checkfirst)` 方式；不修改 P1/P2 表，不提供生产自动 destructive down migration。
4. M3 仅使用确定性模板；具体 LLM Provider/模型到 M4 决定，且只能生成草稿。
5. Artifact 不设置自动 TTL、不自动物理删除；只允许 admin 逻辑 revoke。
6. 来源失效只阻断新的审核批准、发布和导出，不改写历史资产或自动删除历史 Artifact。
7. P3 v1 禁止链式复用，不建立独立检索索引，不执行模型训练。

生产化 Deferred：

- 稳定个人身份、禁止同一自然人自审、OIDC 和身份生命周期。
- 独立 publisher/exporter 角色。
- 真实 LLM Provider、模型和数据出境审批；必须在 M4 入口明确。
- 外部 Artifact 对象存储、企业保留年限和 DLP。
- PDF/DOCX/PPTX 等资料交付格式。

冻结规划中不再保留阻断 P3-M1 的未决项。
