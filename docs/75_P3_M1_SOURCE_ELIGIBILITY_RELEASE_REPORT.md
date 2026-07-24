# P3-M1 Source Eligibility Release Report

> 阶段：P3-M1 Source Eligibility
>
> 验收轮次：P3-M1.3 Source Eligibility Stage Acceptance and Release Closure
>
> 决策：PASS
>
> 边界：P3-M2 尚未开始；未创建 P3 表、ReuseProject 或前端流程。

## 1. P3-M1 目标

P3-M1 为后续数据资产复用建立唯一、确定、只读的来源资格真相层。该阶段只回答一个问题：一个明确的 P1、P2 或 Bad Case 修正知识引用，当前是否满足 P3 复用资格。

阶段交付包括：

- M1.1：来源引用、稳定原因码、单项/批量资格判定内核。
- M1.2：只读单项/批量 API、批量边界和集中式 RBAC。
- M1.3：代码检查、功能矩阵、Docker Smoke、全量回归与发布固化。

P3-M1 不创建 P3 数据表，不选择或保存来源，不创建 Project、草稿、Artifact 或索引，不修改 P1/P2 状态。

## 2. M1.1 内核设计

`backend/app/p3_source_eligibility.py` 是唯一资格真相来源：

- 直接读取现有 SQLAlchemy 治理记录。
- 不接受调用方传入 approved、archived、current 等可信状态。
- 不执行 `add`、`delete`、`update`、`commit` 或状态迁移。
- 不调用 LLM、Provider、Embedding、Retrieval、Agent 或网络。
- 单项函数为 `check_source_eligibility`。
- 批量函数为 `check_sources_eligibility`，按输入顺序复用单项判断。
- 相同数据库状态、来源引用和 policy version 得到相同结果。

Route 仅负责请求校验、RBAC、数据库 Session 和安全错误映射，不复制资格规则。数据库异常只捕获 `SQLAlchemyError` 并返回稳定 503，不向响应暴露连接信息或堆栈。

## 3. 来源类型

合法治理来源类型冻结为：

1. `P1_KNOWLEDGE`
2. `P2_KNOWLEDGE_ASSET`
3. `APPROVED_BAD_CASE_CORRECTION`

`RAW_BAD_CASE` 仅是用于明确拒绝原始 Bad Case 的 API 输入哨兵，不是合法 P3 来源类型。

## 4. 判定结果字段

`P3SourceEligibilityDecision` 包含：

- `source_type`
- `source_id`
- `eligible`
- `reason_code`
- `source_status`
- `source_version`
- `content_fingerprint`
- `approved_review_id`
- `snapshot_id`
- `knowledge_asset_id`
- `lineage_complete`
- `checked_conditions`
- `policy_version`

响应不包含完整正文、原始聊天、向量、Token、Secret、内部存储 URI 或数据库连接信息。

当前策略版本为：

`p3-source-eligibility-v1`

## 5. 稳定原因码

P3-M1 集中定义 12 个原因码：

1. `ELIGIBLE`
2. `SOURCE_NOT_FOUND`
3. `SOURCE_TYPE_UNSUPPORTED`
4. `SOURCE_NOT_APPROVED`
5. `SOURCE_ARCHIVED`
6. `SOURCE_SUPERSEDED`
7. `SOURCE_NOT_CURRENT`
8. `SOURCE_FINGERPRINT_MISMATCH`
9. `SOURCE_TRACE_INCOMPLETE`
10. `RAW_BAD_CASE_NOT_ALLOWED`
11. `BAD_CASE_CORRECTION_NOT_APPROVED`
12. `SOURCE_STATE_INVALID`

来源不合格是业务判定而非 HTTP 错误，因此合法请求返回 HTTP 200 和对应原因码。请求格式错误返回 422。

## 6. P1 资格规则

P1 Candidate 只有同时满足以下条件才 eligible：

1. Candidate 存在。
2. 当前状态为 `approved`。
3. 最新有效 ReviewRecord 为 `approved`。
4. ReviewRecord 具有不可变 `snapshot_json`。
5. Snapshot 包含 Candidate ID、来源类型、上游来源 ID 和审核业务字段。
6. 当前 question、answer、intent、tags、risk level、knowledge type 的规范化 SHA-256 指纹与审核快照一致。
7. question/answer 非空，来源类型有效。
8. Source Trace 完整。
9. Bad Case 来源 Candidate 还必须通过 Bad Case 修正链路检查。

未审核、rejected、archived、superseded、指纹漂移、Trace 缺失和不存在来源均被稳定拒绝。P1 没有实体版本号；调用方不能伪造审核状态。

## 7. P2 资格规则

P2 Knowledge Asset 只有同时满足以下条件才 eligible：

1. Knowledge Asset 存在且状态为 `active`。
2. 它是相同 `asset_id + content_type` 的最高当前版本。
3. 未 archived、未 superseded。
4. 绑定 AssetReviewSnapshot。
5. Snapshot 对应的 ExtractionReview 为 `approved`。
6. Knowledge Asset、Snapshot、Review、Extraction 和 Asset 关系一致。
7. Snapshot 内容指纹与当前 Knowledge Asset 内容指纹一致。
8. Source Trace 必填 ID、版本、Asset hash 和 extraction job ID 完整。

archived、superseded、旧版本、未审核、Snapshot 缺失或 lineage 不完整均不可复用。

## 8. ready 未 serving 的设计理由

P3 读取的是审核并发布后的治理资产，不是线上 Retrieval 可见性。因此：

- `ready` 未 `serving`：`ELIGIBLE`
- `serving`：`ELIGIBLE`
- index status：只作为 `checked_conditions` 中的观察元数据

当前开发 Docker volume 中没有 ready 行；13 条 active Knowledge Asset 的 index 均为 serving。为保护 P1/P2 冻结状态，本轮没有临时修改 index 状态制造 live 数据。`test_p2_ready_not_serving_is_eligible` 使用真实 SQLAlchemy 模型和临时数据库完成 ready-not-serving 验收并通过。

## 9. Bad Case 规则

- 原始 Bad Case 永远不能直接成为 P3 来源，返回 `RAW_BAD_CASE_NOT_ALLOWED`。
- 修正结果必须形成 `source_type=bad_case` 的 P1 Candidate。
- Candidate 和最新 Review 必须 approved。
- 审核快照与当前修正内容指纹必须一致。
- Source Trace 必须包含原 Bad Case ID。
- 原 Bad Case 必须为 `resolved`，且 `created_candidate_id` 必须指向该修正 Candidate。
- 普通 `P1_KNOWLEDGE` 引用也不能绕过上述 Bad Case 修正链路检查。

## 10. 单项和批量 API

### 单项

`POST /api/p3/source-eligibility/check`

请求字段：

- `source_type`
- `source_id`
- `source_version`（可选）
- `expected_fingerprint`（可选）

### 批量

`POST /api/p3/source-eligibility/check-batch`

请求字段：

- `sources`

两类响应均使用统一成功 envelope，返回 `policy_version` 和 decision。批量响应保持输入顺序，每个输入对应一个结果，单条不合格不会终止其他结果。

## 11. 批量限制

- 最小数量：1
- 最大数量：100
- 空数组：HTTP 422，`too_short`
- 101 条：HTTP 422，`too_long`
- 不允许无限批量

## 12. RBAC

集中式 Permission：

`p3.source.read`

允许的既有角色：

- admin
- cleaner
- reviewer
- viewer
- service

没有新增认证角色。Route 使用 `require_permission(Permission.P3_SOURCE_READ)`，不散落角色字符串。

Auth 行为：

- disabled：保持既有兼容模式。
- token 模式无 Token：401 `AUTHENTICATION_REQUIRED`。
- token 模式错误 Token：401 `AUTHENTICATION_INVALID`。
- 缺少 Permission：403 `AUTHORIZATION_DENIED`。
- 五个既有角色具有 `p3.source.read`，访问 P3 资格接口均为 200。
- Health 保持公开；`/api/auth/me` 行为不变。

## 13. Docker Smoke

使用现有开发 compose 项目和 volumes；未删除、重置或替换 postgres/asset/backend storage volumes。仅重建 backend 镜像以加载当前代码。

### 13.1 disabled 模式

| 场景 | HTTP | 结果 |
|---|---:|---|
| P1 approved + 指纹一致 | 200 | `ELIGIBLE` |
| P1 pending_review | 200 | `SOURCE_NOT_APPROVED` |
| P2 active + serving | 200 | `ELIGIBLE` |
| P2 archived | 200 | `SOURCE_ARCHIVED` |
| 原始 Bad Case | 200 | `RAW_BAD_CASE_NOT_ALLOWED` |
| P1/P2/Bad Case 混合批量 | 200 | 顺序保持；各条独立返回 |
| 空批次 | 422 | `too_short` |
| 101 条批次 | 422 | `too_long` |

混合批量原因码顺序为：

`ELIGIBLE -> SOURCE_NOT_APPROVED -> ELIGIBLE -> SOURCE_ARCHIVED -> RAW_BAD_CASE_NOT_ALLOWED`

### 13.2 token 模式

| 场景 | HTTP | 结果 |
|---|---:|---|
| 无 Token | 401 | `AUTHENTICATION_REQUIRED` |
| 错误 Token | 401 | `AUTHENTICATION_INVALID` |
| admin | 200 | `ELIGIBLE` |
| cleaner | 200 | `ELIGIBLE` |
| reviewer | 200 | `ELIGIBLE` |
| viewer | 200 | `ELIGIBLE` |
| service | 200 | `ELIGIBLE` |
| 代表性无权限操作 | 403 | `AUTHORIZATION_DENIED` |

五个生产角色均有 `p3.source.read`，因此 live P3 Route 不存在可配置的“已认证但缺少该 Permission”角色；该 403 分支由聚焦 Route 测试临时移除 viewer Permission 后验证。Docker 使用 cleaner 调用 P2 archive 验证集中式 403 契约。

Smoke 后 backend 已按 compose 默认配置重建并恢复：

- `DATAHUB_AUTH_MODE=disabled`
- `/api/auth/me`：200、`auth_mode=disabled`、`authenticated=false`
- backend/frontend/postgres：healthy

## 14. 测试结果

| 门禁 | 结果 |
|---|---|
| M1.1 来源资格聚焦测试 | 26 passed |
| M1.2 API/RBAC 聚焦测试 | 30 passed，2 个既有 FastAPI warnings |
| Auth/RBAC 回归 | 24 passed，2 个既有 FastAPI warnings |
| P1 Review/持久化相关回归 | 2 passed，4 个既有 warnings |
| P2 Snapshot/Knowledge Asset 相关回归 | 6 passed，10 个既有 warnings |
| OpenAPI/Route 契约 | 包含于 M1.2 30 passed；live OpenAPI 再验证 PASS |
| clean-export 全量 backend | 520 passed、5 个显式 PostgreSQL skips、44 warnings |
| compileall | PASS |
| Secret / conflict marker scan | PASS |
| `git diff --check` | PASS |

全量套件耗时 2006.68 秒。warnings 为既有 FastAPI `on_event` 弃用提示和两项 mock Provider fallback 提示；没有测试失败。

## 15. 零写入证明

1. 内核没有数据库写入调用。
2. Route 只取得 Session 并调用内核。
3. `test_decision_process_performs_zero_writes` 监听 SQL 执行并确认无写语句。
4. `test_request_does_not_change_business_record_counts` 确认 API 前后 Candidate/Review 数量不变。
5. Docker Smoke 仅调用资格 API、Auth/Health/OpenAPI 和只读 SELECT。
6. token 模式代表性 403 在业务处理前被 RBAC 拒绝。
7. 没有新增或修改数据库模型；没有 P3 表。

## 16. P1/P2 冻结保护

- 未修改 P1/P2 repository、service、route 或数据库模型。
- 未改变 P1/P2 状态机。
- 未触发 Retrieval、Embedding、Agent、No-answer 或 Provider。
- 未修改现有治理数据来制造 ready Smoke。
- P3 只读取 P1/P2，绝不回写。
- 未移动任何 P1/P2/P3 历史 tag。

## 17. 已知限制

- 当前 API 只评估明确来源引用，不提供来源列表、分页筛选或 Project 选择。
- P3-M1 不保存资格结果；每次按当前数据库状态重新判断。
- 当前开发 Docker 数据没有 ready-not-serving 行，live Smoke 只能覆盖 serving；ready 语义由聚焦数据库测试覆盖。
- Auth v1 仍是角色 Token，稳定个人身份 Deferred。
- 批量函数按输入逐项执行有界查询；M1 不做大规模来源浏览性能优化。
- PII/禁用内容的正式资产门禁属于后续 Project/生成/审核阶段，不扩大本阶段资格 API 响应。

## 18. P3-M2 入口条件

P3-M2 只有在以下条件全部满足后才能由独立指令开始：

1. 本报告、汇总 commit 和 `p3-m1-source-eligibility-release` annotated tag 已推送。
2. `main` 与 `origin/main` 同步且 working tree clean。
3. P1/P2 继续冻结。
4. M1.1 内核继续作为唯一资格真相来源。
5. M2 只实现 Reuse Project、SourceItem 和来源选择，不进入生成、审核、发布、导出或前端。
6. 不自动连续进入 M2。

P3-M1 发布结论：**PASS；阶段完成。**
