# P3-M4 Governed LLM-assisted Draft Generation Release Report

## 1. M4 目标与发布结论

P3-M4 在 P3-M3 确定性草稿能力旁增加可选、默认关闭的 LLM 辅助草稿路径。该路径复用 M1 来源资格、M2 来源重验证、M3 受治理正文读取、Canonical Source Manifest、Asset Version Repository 和不可变 Source Snapshot，不复制第二套治理规则。

**Release decision: PASS.**

- LLM 只产生 `generated` 草稿，不能审核、批准、发布或导出。
- 默认部署 `P3_LLM_DRAFT_ENABLED=false`，不会调用 Provider。
- 发布验收未调用真实或收费 Provider；所有启用路径使用离线 Fake Provider 和独立测试数据库。
- P1/P2 业务逻辑、表和治理数据未修改。
- 未创建 `reuse_reviews`、`export_jobs` 或 `export_artifacts`。
- P3-M5 尚未开始。

## 2. 与 M3 确定性生成的关系

两条生成路径共用同一套 Asset Version、Source Snapshot、读取和审计模型：

| 路径 | `generation_mode` | 特性 |
|---|---|---|
| M3 确定性模板 | `deterministic_template` | 同输入/模板得到可复现 Payload 与 Content Hash |
| M4 LLM 草稿 | `llm_draft` | 受控结构化生成，不承诺自然语言输出确定性 |

M4 没有改变 M3 模板语义、API 或 RBAC。Docker Smoke 再次确认确定性生成返回 201，List/Detail 返回 200。

## 3. `llm_draft` Generation Mode

`ReuseGenerationMode` 当前只包含：

- `deterministic_template`
- `llm_draft`

Repository 只接受集中 Enum，不接受任意字符串。Asset List/Detail 继续使用现有读取 API，并通过 `generation_mode` 明确区分两类版本；LLM 草稿不会伪装成确定性版本。

## 4. Schema 兼容策略

M3 的数据库 Check Constraint 实际只允许 `deterministic_template`，因此 M4.1 实现了前向、幂等兼容：

- 新数据库由 SQLAlchemy metadata 直接创建包含两个值的约束。
- SQLite 旧表使用同库 shadow table 重建；事务内复制全部行，校验 ID、generation mode、Content Hash、Manifest Hash、索引和外键后替换旧表。
- PostgreSQL 在事务内替换命名 Check Constraint，迁移前后逐行核对关键 Hash。
- 重复执行为 no-op。
- 不删除 P1/P2 表，不重置数据库，不设计 destructive down migration。
- 应用回退保留兼容后的 Schema 和已有数据。

开发 PostgreSQL 最终约束实测包含：

```text
deterministic_template, llm_draft
```

隔离测试同时证明旧确定性记录在迁移前后可读、数量和 Hash 不变。

## 5. Provider 抽象

`P3LLMDraftProvider` 定义单一入口：

```text
generate_structured_draft(request) -> result
```

Request 固定包含资产类型、Prompt key/version、Source Manifest Hash、受治理 Source Materials、Response Schema、白名单模型参数和结构化 messages。Result 只暴露：

- parsed payload
- provider profile
- model alias
- 可选安全 usage summary
- 可选 finish reason

核心 Service 不依赖厂商 SDK。仓库提供最小 OpenAI-compatible Adapter，使用现有 Python 运行时 HTTP 能力；API Key 只从环境读取，不进入数据库、日志、错误、OpenAPI 或 Hash。

## 6. 配置与 Feature Flag

Compose 和 `.env.example` 已显式接线：

- `P3_LLM_DRAFT_ENABLED=false`
- `P3_LLM_PROVIDER_PROFILE=openai_compatible`
- `P3_LLM_BASE_URL`
- `P3_LLM_MODEL`
- `P3_LLM_API_KEY`
- `P3_LLM_MAX_SOURCE_COUNT=100`
- `P3_LLM_MAX_CONTEXT_CHARS=80000`
- `P3_LLM_MAX_OUTPUT_CHARS=200000`
- `P3_LLM_MAX_OUTPUT_TOKENS=4096`
- `P3_LLM_TIMEOUT_SECONDS=120`

Flag 未启用返回 `P3_LLM_DRAFT_DISABLED`；Provider 配置不完整返回 `P3_LLM_PROVIDER_NOT_CONFIGURED`。两者都发生在创建 Asset Version 之前。

## 7. Prompt Registry

版本化 Registry 为五种 Asset Type 各注册一个 `v1` Prompt：

- `p3.llm.training_material.v1`
- `p3.llm.sop.v1`
- `p3.llm.service_script.v1`
- `p3.llm.qa_bank.v1`
- `p3.llm.sft_dataset.v1`

每项包含 prompt key/version、asset type、system instruction、严格输出 Schema 和 `build_messages`。来源正文只进入 user message 中的 `governed_sources` 数据块，不进入 system message。

## 8. 五类输出结构

M4 复用 M3 已冻结的 Pydantic Schema，全部 `extra=forbid`：

| 类型 | 主要结构 |
|---|---|
| `training_material` | title、learning objectives、sections、key points、source refs |
| `sop` | purpose、scope、prerequisites、steps、cautions、escalation rules、source refs |
| `service_script` | scenario、opening、response steps、prohibited claims、escalation、source refs |
| `qa_bank` | question/answer items、source refs |
| `sft_dataset` | instruction/input/output/metadata/source refs records |

未知字段、空内容外壳、类型错误和未知引用均拒绝。

## 9. Source Material 规则

LLM Service 只能从现有 M3 Reader 获取正文：

- P1/Bad Case 修正只读取 approved Review 的不可变 snapshot。
- P2 只读取 approved、active/current Knowledge Asset 对应 Snapshot；ready 未 serving 仍可用。
- 原始 Bad Case、未审核正文、旧版本、archived/superseded 来源、向量、Token 和 Secret 不进入 Prompt。
- 调用方不能提交 source material、snapshot、payload、hash、status 或 generation mode。

## 10. Prompt Injection 防护

实现的结构防护包括：

- system instruction 和来源数据分离；
- 来源以稳定 source ref 的 JSON 数据块封装；
- 明确声明来源内指令无控制权；
- 来源不能修改 Output Schema、模型配置或工具调用；
- Provider 不具备工具、Retrieval、Embedding、Agent 或外部写权限；
- 测试覆盖 “Ignore previous instructions”“输出数据库密码”“调用外部网站”“删除其他来源”。

这些措施降低 Prompt Injection 权限和结构风险，但不宣称对所有未来攻击形式绝对免疫。

## 11. Grounding Guard

Provider 输出依次经过：

1. JSON 解析；
2. 资产类型 Pydantic Schema；
3. 输出体积门禁；
4. source ref 与输入白名单逐字段匹配；
5. source ref 去重和规范化；
6. 每个 section/step/item/record 的 100% 引用覆盖；
7. Provider 调用后再次执行 M2 来源重验证；
8. 重新计算并比较 Source Manifest；
9. 只对规范化业务 Payload 计算 Content Hash。

Provider 输出不能覆盖 Source Item、Source Snapshot 或 P1/P2 证据。

## 12. Grounding 能力边界

结构化 Guard 能证明：

- 引用 ID 来自本次输入；
- 引用证据对象未被 Provider 篡改；
- 所有实质单元都有引用；
- 来源在 Provider 调用前后仍通过治理门禁。

它不能数学意义上证明每个自然语言事实完全无幻觉，也未实现事实级 entailment 自动验证。LLM 结果因此仍是草稿，必须在 M5 经人工编辑和审核。

## 13. Context Budget

门禁默认：

- 最多 100 个来源；
- 最多 80,000 个上下文字符；
- 最多 200,000 个输出字符；
- Provider timeout 120 秒；
- 输出 token 上限 4,096。

超限返回 `P3_LLM_CONTEXT_LIMIT_EXCEEDED` 或 `P3_LLM_OUTPUT_TOO_LARGE`。系统不静默丢来源、不截断审核正文。

## 14. 请求指纹与幂等

LLM 请求身份由以下内容组成：

- project ID
- asset type
- `generation_mode=llm_draft`
- Source Manifest Hash
- provider profile
- model alias
- prompt key/version
- 规范化模型参数 Hash
- actor role

Provider、Model、Prompt 和参数 Hash 被编码进稳定 `template_key`，Prompt version 保存于 `template_version`。

行为冻结为：

- 同 key/同请求/generated：返回原版本；
- 同 key/同请求/failed：返回原失败版本，不再调用 Provider；
- 同 key/generating：返回稳定冲突；
- 同 key/不同指纹：409；
- 新尝试必须使用新 key。

Release Closure 发现并修复了并发竞态：Repository 竞争返回已有 `generating` 行时，只有该行持久化 `request_id` 对应的 attempt owner 可以调用 Provider，其他请求返回冲突。独立 PostgreSQL 双线程测试证明只创建一行且 Provider 调用次数为 1。

## 15. `generated` / `failed` 生命周期

成功路径：

```text
validate gates
-> create generating version + source snapshots
-> call Provider once
-> parse/schema/ground/revalidate
-> generated
```

失败路径：

```text
generating -> failed
```

`failure_code` 使用稳定错误码，`failure_message` 安全裁剪。失败不会保存 Raw Response、完整 Prompt、Source Material、Authorization Header、API Key、堆栈或数据库连接串。

## 16. Provider 错误处理

稳定错误包括：

- `P3_LLM_DRAFT_DISABLED`
- `P3_LLM_PROVIDER_NOT_CONFIGURED`
- `P3_LLM_CONTEXT_LIMIT_EXCEEDED`
- `P3_LLM_PROVIDER_TIMEOUT`
- `P3_LLM_PROVIDER_UNAVAILABLE`
- `P3_LLM_OUTPUT_INVALID_JSON`
- `P3_LLM_OUTPUT_SCHEMA_INVALID`
- `P3_LLM_UNKNOWN_SOURCE_REF`
- `P3_LLM_GROUNDING_INCOMPLETE`
- `P3_LLM_OUTPUT_TOO_LARGE`
- `P3_LLM_GENERATION_FAILED`

默认零自动重试、零模型切换、零确定性 fallback，避免重复收费和隐式语义变化。

## 17. API

新增：

```text
POST /api/p3/reuse-projects/{project_id}/assets/generate-llm-draft
```

请求只允许：

- `asset_type`
- `prompt_key`（可选）
- `provider_profile`（可选）
- `idempotency_key`

Route 只校验请求、获取 Principal/request ID、调用 `P3LLMDraftService`、映射错误和序列化。现有 List/Detail API 原样读取 `llm_draft`。

## 18. RBAC

集中 Permission：

```text
p3.asset.generate_llm
```

| 角色 | 生成 LLM 草稿 | 读取 Asset |
|---|---:|---:|
| admin | 允许 | 允许 |
| cleaner | 允许 | 允许 |
| service | 允许 | 允许 |
| reviewer | 拒绝 | 允许 |
| viewer | 拒绝 | 允许 |

未新增角色。Token 模式无/错误 Token 为 401，reviewer/viewer 生成为 403。

## 19. Docker 默认禁用 Smoke

使用现有开发 volumes，未 reset 或删除数据。实测：

- `DATAHUB_AUTH_MODE=disabled`
- `P3_LLM_DRAFT_ENABLED=false`
- LLM Endpoint：503 + `P3_LLM_DRAFT_DISABLED`
- disabled 调用后 Asset Version 数量仍为 0
- Deterministic Endpoint：201 + `deterministic_template`
- Asset List/Detail：200
- token 模式无/错 Token：401
- admin/cleaner/service：通过 RBAC 后 503 disabled
- reviewer/viewer：403
- 五角色读取：200
- Health 公开、`/api/auth/me` 保持原行为

Smoke 后恢复 Auth disabled 和 Feature false；精确删除本轮四条 P3 smoke graph 记录，P3 四表计数恢复 `0|0|0|0`。三个开发服务最终 healthy。

## 20. Fake Provider 隔离验收

`FakeP3LLMDraftProvider` 只能通过测试代码显式注入，不能由生产环境 profile 选择。它不访问网络，可生成五类合法 Payload，并模拟：

- timeout/unavailable
- malformed JSON
- Schema error
- unknown source ref
- missing refs
- empty content

Fake 验收覆盖五类成功、幂等、failed 留痕、Source Snapshot、Grounding、Prompt Injection 分隔和 Context Limit。

## 21. PostgreSQL 验收

独立数据库 `datahub_p3_m4_test_20260728` 运行 5 个 integration tests，验证：

- 旧 Check Constraint 的前向兼容和重复执行安全；
- 旧 deterministic 数据与 Hash 保留；
- `generation_mode=llm_draft`；
- generating -> generated / failed；
- Source Snapshot 原子写入；
- Provider timeout 的安全失败边界；
- 幂等重放；
- 并发 idempotency 只调用 Provider 一次；
- 来源 stale 后历史确定性/LLM/failed 版本不改写；
- PostgreSQL foreign key/unique/RESTRICT 基线。

测试数据库已精确 drop，临时容器为 0；开发 PostgreSQL volume 未删除。

## 22. 测试结果

| 门禁 | 结果 |
|---|---:|
| M4.1 Contract | 21 passed，1 explicit PG skip |
| M4.2 Service 最终聚焦 | 30 passed，1 explicit PG skip |
| M4.3 API/RBAC | 43 passed |
| M4.2/Auth/既有 Asset API 回归 | 86 passed |
| P3-M1～M4/Auth/OpenAPI 矩阵 | 423 passed，7 skipped |
| Isolated PostgreSQL | 5 passed |
| 修复后权威 clean-export backend | **864 passed，13 skipped，44 warnings，105.41s** |
| compileall / Secret / conflict marker / diff check | PASS |

第一次 clean-export 得到 863 passed/12 skipped，但随后 Release Closure 发现 Compose 接线和并发 attempt-owner 缺陷，因此该次结果不作为最终发布证据。上表的 864/13 是包含最终修复的权威结果。

13 个 skip 均为环境依赖 integration gates。44 个 warnings 是既有 FastAPI lifecycle deprecation 和两个预期 mock embedding fallback warning。

## 23. P1/P2 冻结保护

M4 diff 不包含 P1/P2 repository、service、route、model、Retrieval、Embedding、Agent 或前端文件。M1 Eligibility、M2 Project lifecycle、M3 deterministic semantics 未复制或改写。Docker smoke 只创建并精确清理 P3 数据，未修改 P1/P2 来源。

## 24. 安全与 Secret 保护

- API Key 只从环境读取，Settings repr 隐藏该字段。
- Route/OpenAPI 不接受 API Key、Base URL、Raw Request、Source Material 或模型参数。
- 日志和错误不回显 Token、Authorization、连接串、Raw Response、Prompt 或 Source Content。
- M4 change-set Secret scan、conflict marker scan 和 `git diff --check` 均通过。
- 未调用真实 Provider或外部网络。

## 25. 已知限制

- 未实现人工编辑、Review、approve、publish、export 或前端。
- 未实现事实级自动验证、自然语言 entailment 或自动幻觉判定。
- 未执行真实 Provider 联调、Prompt 审批或数据出境评估。
- 不承诺 LLM 输出确定性；幂等保证的是一次 attempt 不重复收费调用。
- Provider 调用为同步请求，无后台队列或自动扫描。
- LLM 草稿不能作为 P3 来源，不允许链式复用。

真实 Provider 联调是可选独立验证，不阻塞默认关闭的安全发布。

## 26. P3-M5 开始条件

P3-M5 必须等待独立人工指令，并至少满足：

1. M4 release commit/tag 已推送且 main/origin 同步；
2. 默认 Auth disabled、Feature false、三服务 healthy；
3. P1/P2、M1、M2、M3 冻结边界保持；
4. 继续使用现有 Asset Version，不创建发布或导出捷径；
5. 人工编辑与审核必须明确区分 generated、pending_review、approved 和 published；
6. 不自动把任何 LLM 草稿视为事实或已审核知识。

本报告完成后立即停止，P3-M5 尚未开始。
