# P1/P2-M9.3 Frontend Governance Usability Report

## 1. 结论

M9.3 已把现有 P1/P2 后端治理能力整理为中文、任务流优先且只调用真实 API 的前端工作台。改动仅涉及前端、前端契约测试和文档；未修改数据库、后端业务路由、检索、Embedding、RRF、CustomerOpsAgent 默认行为或 Unified opt-in 规则。

## 2. 原前端问题

- 认证控件和业务页面各自管理状态，角色虽已由后端确认，但缺少统一权限 UX。
- P1/P2 页面更接近能力演示，用户不容易判断当前步骤和下一步。
- P2 缺少 Extraction、Embed、Serve 等真实入口，`ready` 与 `serving` 的差异不够明确。
- 检索、Agent、系统状态没有独立验证入口；P3/P4 页面包含较多预览式假按钮。
- 异步操作、危险操作、稳定错误码和 Source Trace 的展示缺少统一规则。

## 3. 信息架构

顶部统一展示 DataHub、当前环境、后端确认的当前角色和访问令牌清除操作。主导航收敛为：

1. P1 文本知识治理
2. P2 多模态知识治理
3. 检索验证
4. 系统状态

首页只提供真实导航；P3/P4 保留“尚未开放”状态、禁用入口和原因，不进入空页面。

## 4. P1 中文治理流程

P1 页面按真实 API 组织为：数据导入 → 机器清洗 → 手工修订 → 候选知识生成 → 人工审核 → RAG 同步 → CustomerOpsAgent 验证 → Bad Case 提交与查看。每个写操作都有角色门禁、执行锁、成功刷新和中文错误反馈；Reject、RAG sync 等可见性操作使用说明影响的中文二次确认。

## 5. P2 中文治理流程

P2 页面按真实生命周期组织为：上传 Asset → Extraction → 修订/Review → Snapshot → 发布 Knowledge Asset → 创建 Index → Embed → Ready → 显式 Serve → Retrieval → Archive → Source Trace。

- Extraction 调用真实 `/api/assets/{asset_id}/extract`。
- Embed 调用真实 `/api/knowledge-index/{index_entry_id}/embed`。
- Serve 调用真实 `/api/knowledge-index/{index_entry_id}/serve`。
- 页面不绕过 Review、Snapshot 或 Serving Gate，也不展示完整向量。

## 6. Ready / Serving 与 Archive

- `ready · 向量已生成，尚未开放检索` 明确表示内容尚不可检索。
- `serving · 已开放检索` 明确表示已经通过显式 Serve 开放。
- Archive、Serve、Reject、RAG sync 和发布新版本均有具体影响说明，不使用模糊的“确定吗”。
- 终态操作被禁用；Archive 成功后重新读取后端状态。归档不会删除历史记录。

## 7. Source Trace

页面用可读链路展示 `Knowledge Asset → Snapshot → Review → Extraction → Asset`，同时保留对象 ID、版本和关键来源信息。完整向量、Secret、数据库连接和 Debug 堆栈不会出现在 UI。

## 8. 可信角色与权限 UX

角色唯一来源是 `GET /api/auth/me`。前端仅在 `sessionStorage` 保存 Token，不保存或接受用户填写的角色。页面加载、Token 应用和刷新均重新向后端解析并 allow-list 角色；Token 清除或 401 会清除本地认证状态。

| 角色 | 前端可见操作 |
|---|---|
| admin | 全部 P1/P2 治理、审核、发布、Embed、Serve、Archive 和服务验证 |
| cleaner | 导入、清洗、修订、上传、Extraction；审核/发布/Serve/Archive 显示无权限 |
| reviewer | 查看待审核项并审核；不可导入、Embed、Serve、Archive |
| service | Retrieval、CustomerOpsAgent、Bad Case；不显示人工治理写操作 |
| viewer | 列表、详情、状态、Source Trace 和允许的只读检索；写操作禁用 |

按钮权限只改善 UX，后端 RBAC 仍是最终安全边界。无权限控件附带“当前角色没有执行此操作的权限。”说明。

## 9. 状态与错误

集中映射 loading、empty、success、warning、error、unauthorized 和 forbidden。稳定 HTTP/业务错误统一转换为中文：401 身份验证失败、403 权限不足、404 对象不存在、409 状态冲突、422 输入不合法、503 依赖服务暂不可用。异步操作期间按钮锁定，结束后按真实后端状态刷新；英文堆栈不会直接展示。

## 10. 检索验证

独立页面提供 P1 Retrieval、P2 Retrieval、Unified Retrieval 和 CustomerOpsAgent 的真实调用，展示 query、retrieval mode、rank/score、evidence、source trace、fallback used/reason。CustomerOpsAgent 默认 P1-only；Unified 和 Agent Unified 分支都必须由用户显式 opt-in，Shadow 与 Active 文案分离。

## 11. 假按钮清理

P3/P4 原有 18 个预览式按钮已删除。未开放能力只保留禁用入口和原因；新增的业务按钮均调用真实 API、跳转真实模块，或因权限/生命周期/未开放原因明确禁用。

## 12. 自动化测试

- M9.3 前端静态契约、M9.2 Auth/RBAC、CustomerOpsAgent/Unified 兼容及相关 P2 route contract：`99 passed, 26 warnings`，9.74 秒。
- 前端 production build：PASS，Vite 5.4.21，54 modules transformed。
- 未修改后端业务代码或 route/schema，因此按阶段边界未重复运行 411 项全量 backend pytest；M9.2 的 411 passed 仍是稳定基线。

覆盖点包括 `/api/auth/me` 可信角色、五角色权限矩阵、Token 清除/Header、401/403 中文映射、P2 真实 API、ready/serving、Archive 确认、Source Trace、Unified opt-in、P3/P4 disabled、无向量/Token URL/console 暴露。

## 13. Docker 浏览器验收

在保留现有 volumes 的本地 Compose 环境完成真实浏览器验收：

- token 模式无 Token 显示未认证和中文 401；清除 Token 后角色与权限立即清空。
- 页面刷新后通过 `/api/auth/me` 恢复后端确认的 admin 角色。
- cleaner 可进入 Extraction，Archive 等高风险操作显示无权限。
- reviewer 显示审核职责和对应权限边界。
- service 完成一次真实 P1 Retrieval 请求，并显示 CustomerOpsAgent 默认 P1-only、Unified 未勾选。
- viewer 的上传操作禁用并显示明确权限原因。
- admin 可见完整 P2 治理能力；保留数据中实际展示 `serving · 已开放检索`、`archived` 和完整 Source Trace，未显示向量。
- 首页 P3/P4 两个入口均 disabled 并显示未开放原因；浏览器控制台无应用错误。

验收没有执行破坏性 Archive/发布操作，没有删除 volume。结束后 backend 已恢复 `DATAHUB_AUTH_MODE=disabled`、配置角色 Token 数量 0，backend/frontend/PostgreSQL 均 healthy。

## 14. 兼容性与安全

- CustomerOpsAgent 默认仍为 P1-only。
- Unified 仍需显式 opt-in。
- 未修改检索、索引或归档实现；M9.2/M9.1 的 archived leakage = 0 基线保持，未重复运行三轮 Eval。
- Token 不进入 URL、源码、日志或 Git；前端只使用当前标签页的 `sessionStorage`。
- P1/P2 后端 response contract 未改变。

## 15. 已知限制

- 当前后端没有独立的 Extraction 内容修订保存接口；cleaner 可以创建修订/复核任务，但前端不会伪造内容保存或绕过 reviewer 权限。
- 项目没有现成浏览器 E2E 测试框架，本阶段未引入 Playwright 工程；角色流程使用静态契约测试和本地 Docker 手工浏览器验收。
- 保留数据提供了 serving/archived 实例；为避免改变 retained corpus，浏览器验收未现场创建 ready → serve → archive 新对象。状态文案、按钮门禁和确认由自动化契约测试覆盖。
- Render 线上 Auth/P2 浏览器验收未执行，不能用本地 Docker 证据替代。

## 16. M9.4 入口建议

M9.4 尚未开始。下一阶段仅在单独授权后进入 PostgreSQL/pgvector 故障、事务与并发测试，以及有数据集和测量依据、默认关闭的 No-answer Gate；不得借前端工作流修改 RRF、Agent 默认模式或 Unified opt-in。
