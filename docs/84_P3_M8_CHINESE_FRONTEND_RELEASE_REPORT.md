# P3-M8 中文前端任务流发布报告

## 1. 发布结论

P3-M8 **PASS**。M8.1～M8.4 已分别实现、聚焦测试、提交、推送并创建 annotated tag；M8.5 完成真实 Docker 流程、前端权威门禁、少量后端契约回归、视觉与发布审计。P3 现在提供完整中文任务流，P4 仍为规划中。

本阶段只修改前端与发布文档，没有修改后端业务代码、API、数据库模型或 P1/P2 行为。M7.5 的 fresh clean-export 结果 `1125 passed, 21 skipped, 44 warnings, 0 failed` 继续作为后端权威基线。

## 2. 目标与产品边界

M8 将 M1～M7 已冻结的真实 P3 API 组织为清晰的中文工作区：选择治理来源、创建并激活项目、生成和修订草稿、人工审核、发布、导出、下载与撤回。

- 前端隐藏或禁用按钮只是可用性提示，**不能替代后端 RBAC**。
- `published` 只是受治理的 P3 资产状态，不等于进入 RAG、MCP 或 Agent。
- `export` 只是生成受治理 Artifact，不等于已经训练模型。
- `P3_LLM_DRAFT_ENABLED` 默认关闭；未启用时不调用 Provider、不生成 LLM 草稿。
- v1 身份审计仍以 `actor_role`、`request_id` 和时间为主，稳定个人身份继续 Deferred。
- P3 资产不能链式作为 P3 来源；P4 未开始。

## 3. 用户流程与信息架构

页面路由为 `/p3`，入口卡片从“规划中”切换为可进入；P1、P2 入口与工作流保持可用，P4 继续禁用并显示“规划中”。P3 主页面采用五阶段任务流：

1. 项目与来源：创建 Project、检查来源资格、添加治理来源、重新验证并激活。
2. 草稿生成：选择五类资产之一，执行确定性模板生成；LLM 能力默认关闭。
3. 编辑与审核：创建新修订、提交审核、执行 `needs_revision` / `approved` / `rejected` 决策。
4. 发布管理：查看 Current Published、确认发布、版本替换与归档状态。
5. 导出交付：创建 JSONL/CSV 导出、查看 Job/Artifact、下载或逻辑 revoke。

Stepper 在桌面端展示完整阶段，在移动端使用自身容器内的安全横向滚动，不造成页面级横向溢出。技术字段放在默认收起的高级信息区，主操作与治理状态优先显示。

## 4. API Client 覆盖

前端类型化 Client 覆盖 `/api/auth/me`、来源资格单项/批量查询、Project CRUD/激活/归档、Source 添加/列表/逻辑移除/重新验证、Asset 生成/列表/详情、人工修订、提交审核、Review 决策/历史、发布/归档/Current Published、Export 创建/列表/详情、Artifact Metadata/下载/revoke。

Client 统一处理 Bearer Header、安全 JSON 错误、Blob 下载和稳定错误码；请求不接受调用方伪造 approved/current/archived、Review、Snapshot、Source Trace、Hash 或发布状态。

## 5. Project 与 Source UI

- Project 列表分页、稳定选择、创建幂等键与手动重试。
- draft 项目可更新元数据、添加或逻辑移除来源；active/archived 的冻结边界有中文说明。
- 支持 `P1_KNOWLEDGE`、`P2_KNOWLEDGE_ASSET`、`APPROVED_BAD_CASE_CORRECTION`。
- 资格不足以 HTTP 200 业务结果展示稳定原因；原始 Bad Case 明确不可用。
- 前端只提交来源身份和可选预期指纹，治理证据由后端 M1 真相源读取并固化。
- 激活前展示来源数量、stale 状态与重新验证结果；stale 项目不能生成、发布或新导出。

## 6. Draft、Revision 与五类编辑器

确定性模板支持 `training_material`、`sop`、`service_script`、`qa_bank`、`sft_dataset` 五类资产。每类内容使用结构化中文编辑器，而不是直接暴露内部 JSON；修改通过 `manual_revision` 创建新版本，不覆盖父版本。

LLM 草稿入口仅在功能开关与权限允许时可用；默认关闭时显示明确说明且不会发起请求。确定性生成、版本号、内容 Hash、来源 Manifest 和引用信息均以只读摘要展示。

## 7. Review UI

- `generated` / `needs_revision` 版本可提交人工审核。
- Review 使用 `p3-review-v1` 四项 checklist；批准必须全部通过。
- `needs_revision` 与 `rejected` 必须填写意见，并在危险操作确认框中再次确认。
- Decision 后状态、评论、角色、请求标识和时间进入 Review 历史。
- `approved` 不等于 `published`；只有 admin 可进入后续显式发布。

## 8. Publication UI

发布区只允许符合 active Project、approved Review、Hash/Manifest/Grounding 与当前来源门禁的版本进入发布确认。admin 发布前必须确认影响；同一 Project/Asset Type 新版本发布后，旧 current 自动变为 `superseded`，界面只显示一个 Current Published。

`superseded`、`archived`、`source_stale` 版本禁止新发布。历史 Payload、Review、Source Snapshot 和 Hash 继续只读保留，不支持前端原地覆盖。

## 9. Export、Download 与 Revoke UI

- admin 可对 current published 且未 stale 的版本创建 JSONL/CSV 导出。
- Job 显示 pending/running/succeeded/failed/revoked 中文状态、格式、行数、SHA-256 和 Manifest 摘要。
- 五角色可读取并下载授权 Artifact；只有 admin 可创建和 revoke。
- revoke 使用二次确认，完成后下载返回 410；文件、Manifest、校验和及审计仍保留。
- 来源后续 stale 会阻止新导出，但不重写历史 Artifact；未 revoke 的历史 Artifact 仍可下载并明确显示来源状态。

## 10. 中文状态、错误与页面状态

Project、Asset Version、Review、Export Job、资格原因与常见 HTTP 错误均映射为稳定中文文案。401 说明 Token 缺失或无效，403 说明角色权限不足，409 展示业务冲突，410 表示 Artifact 已撤回，422 展示字段校验问题；响应不显示堆栈、连接串、Token、完整正文或向量。

所有工作区提供 Loading、Empty、Error 和可重试状态。空列表不伪造示例数据；失败重试复用同一幂等键，避免重复创建。

## 11. RBAC 界面行为

角色由 `/api/auth/me` 确认。admin 可执行全部 P3 操作；cleaner 负责项目、来源、生成、修订与提交；reviewer 执行 Review Decision；viewer 只读；service 只显示被授权的生成/导出后台能力，不提供人工审核或直接发布入口。

无权限动作隐藏或禁用并说明原因，但安全判断始终由后端集中式 Permission 执行。token 模式的 401/403 与 disabled 兼容模式均由后端契约测试固定。

## 12. 响应式、视觉与可访问性

浏览器验收覆盖 `1920x1080`、`1440x900`、`1366x768`、`768x1024`、`390x844`：无页面级横向溢出，Hero 高度保持克制，五阶段清晰，主操作突出，技术详情默认收起，桌面端不空旷，手机端不拥挤。首页 P1/P2/P3 可用、P4 规划中；浏览器 console 无 warning/error。

表单具有可见 Label；Switch/Checkbox 同时提供控件与文字状态；Dialog 具有标题、焦点圈定、焦点恢复和 Escape 关闭；危险操作要求明确确认；焦点样式和键盘顺序保持可见。大尺寸 Checkbox 未回归。

Docker Desktop 恢复后，浏览器工具的 reload 被 URL 安全策略拒绝；本轮没有绕过策略或改用隐蔽浏览器。恢复前已完成上述五尺寸 DOM/视觉/console 证据，恢复后用真实 Docker API 完成两条全生命周期验收。

## 13. Docker 真实流程

开发 Docker volumes 未删除或重置，backend/frontend/PostgreSQL 均恢复为 healthy。

路径一实际完成：创建并激活 Project → 确定性 v1 → 人工修订 v2 → `needs_revision` → 人工修订 v3 → `approved` → `published` → JSONL Export `succeeded` → 下载 200 → revoke → 下载 410。

路径二实际完成：创建并激活 Project → QA Bank v1 → 提交审核 → `rejected`；版本保持 rejected，未发布、未导出。

M8.4 另验证同类资产 v2 发布后 v1 为 `superseded`，Current Published 指向 v2，并完成 JSONL/CSV 双格式导出。没有通过修改 P1/P2 数据伪造 stale；stale 发布/激活/新导出与历史 Artifact 行为由现有聚焦契约测试验证。

## 14. 测试与构建结果

- M8.1 聚焦：9 passed。
- M8.2 聚焦：18 passed。
- M8.3 聚焦：36 passed。
- M8.4 聚焦：49 passed。
- M8.5 frontend 全量 unit/component/contract：5 files、49 passed。
- M8.5 少量 backend RBAC/stale/OpenAPI 契约：8 passed、2 个既有 deprecation warnings。
- TypeScript `tsc --noEmit`：PASS。
- ESLint：0 errors；1 条既有 P1 `useMemo` dependency warning，M8 未修改该代码。
- Production build：PASS，75 modules，CSS 73.64 kB，JS 336.02 kB。
- M7.5 backend 权威基线：1125 passed、21 skipped、44 warnings、0 failed。

仓库未配置独立浏览器 E2E runner。本次 E2E 证据由真实 Docker 两条完整 API 生命周期、五个 P3 页面/契约组件测试文件以及恢复前真实浏览器响应式/console 验收共同组成；没有伪造“全流程浏览器自动化”结果。

## 15. Vercel Preview 与 Fixture 边界

没有可用 Preview URL：环境无 Vercel CLI、`vercel.json`、`.vercel/project.json` 或 `VERCEL_TOKEN`，因此没有伪造部署。本轮未创建或使用 Preview Fixture，Fixture 路径保持不存在/默认关闭。

即使未来使用 Fixture，它也只能验证视觉与交互壳，不能作为来源资格、审核、发布、导出、RBAC 或持久化的功能验收证据。**本地 Docker 真实 API 是 M8 功能验收依据。**

## 16. 冻结保护与安全审计

- M8 未修改任何 backend 文件、数据库表或 API 业务语义。
- P1/P2 页面、路由和治理流程保持可用；未改 P1/P2 业务代码或数据。
- P3 仍精确为七张冻结表，未创建第八张业务表。
- 没有调用真实 Provider；LLM 默认关闭。
- 未提交 `.env`、Token、API Key、数据库、下载文件、runtime manifest、真实业务数据或 Fixture 产物。
- Preview、published、export 均没有被描述为训练、RAG、Agent 或 P4 完成。

## 17. 已知限制

- 当前没有生产稳定个人身份，只保留角色级审计。
- 未配置 Vercel Preview，线上预览不是本次 Release 证据。
- 仓库暂无独立浏览器 E2E runner；本次没有为发布收尾引入新的测试框架。
- LLM 草稿默认关闭；具体 Provider 质量不属于 M8。
- Artifact 仍采用本地受治理 Storage；云交付、训练执行、RAG/Agent 接入均不在范围内。

## 18. P4 开始条件

P4 尚未开始。只有收到单独明确指令，并冻结稳定只读 API/MCP 契约、权限、Source Trace/Export Manifest 消费边界、部署与安全门禁后，P4 才能规划或开发。P4 不得绕过 P3 published/current/non-archived 和 Artifact revoke 状态，也不得回写 P1/P2/P3 治理记录。

