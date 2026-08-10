# P1-P3-R1 Contract and Infrastructure Hardening Release Report

状态：**PASS（含已批准验收例外）**

发布日期：2026-08-10

基线提交：`5d7e86f50a254515180a234b01baff665527fb44`

适用范围：P1-P3-R1.1～R1.4 与 Release Closure；不包含 P1 数据层重构、P2 真实多模态、P3-M9 或 P4。

## Release Decision

P1-P3-R1 Contract and Infrastructure Hardening 完成。R1 冻结了产品与数据所有权契约，提供真实 Runtime Capabilities，建立 Alembic/Health/Auth/Docker 安全边界，并将四项统一质量门禁落到 GitHub Actions。

Stage E 验收中曾误把一次 P2 Retrieval smoke 当作纯读取探针。该请求使用现有 SiliconFlow Embedding 配置生成 query embedding，产生一次真实 Provider 调用，并按既有审计契约新增一条 `retrieval_logs`。2026-08-10，用户明确接受该单次验收例外，要求保留审计记录并继续发布。本报告不删除记录、不改写 preflight，也不把例外描述为“零调用”或“数据完全不变”。

## 1. R1 目标

R1 只加固跨 P1/P2/P3 的合同和基础设施：统一真实产品定位、运行时能力真相、Migration 所有权、Health/Auth 边界、可复现 Docker 基础与 CI 门禁。R1 不新增产品业务功能，不提前进入后续 Goal。

## 2. P1/P2/P3 真实定位

- P1 是客服文本知识治理中心，覆盖导入、清洗、审核、RAG、检索和 Bad Case 回流；CustomerOpsAgent 默认 P1-only。
- P2 是素材文本投影治理中心，覆盖 JPEG/PNG/WebP 素材治理、人工修订、Snapshot、发布、独立索引与检索；正式 Extraction 仍是 deterministic mock。
- P3 是已治理知识复用资产生产和交付中心，生产五类资产并支持修订、审核、发布和 JSONL/CSV 导出；`approved != published`、`published != RAG/Agent/training`、`export != training`。
- P4 仍是 `planned`，尚未开始。

## 3. 开发偏移修正

R1.1 通过 `docs/85_P1_P3_R1_CONTRACT_FREEZE_AND_PLATFORM_ADR.md` 消除了中英文 README、当前状态文档和历史表述之间的产品定位偏移。R1.2 将首页从静态可用性推断改为运行时能力映射。R1.3 移除正常 startup 的 Schema 所有权并建立 Migration/Health/Auth fail-closed 契约。R1.4 将本地约束转成四项远端自动门禁。

R1.4 首次远端运行暴露 Job 级 `runner.temp` 上下文错误；后续运行又暴露 SQLite/PostgreSQL 测试隔离和进程级数据库上下文恢复问题。所有纠正均使用透明 follow-up commit，未 rewrite 或 force push；最终质量标签指向纠正后的绿色提交。

## 4. Runtime Capabilities

`GET /api/capabilities` 是部署能力真相来源。最终本地 Docker 验收返回：

| 维度 | 状态 |
| --- | --- |
| authority | `local_docker` |
| database / pgvector | `available` / `available` |
| asset / export storage | `local_only` / `local_only` |
| P1 | `available` |
| P2 / P3 | `local_only` / `local_only` |
| P4 | `planned` |
| P3 LLM draft | `false` |
| Unified Retrieval | `false` |
| CustomerOpsAgent default | `p1` |

探针为只读、无 DDL、无业务写入，不回显 Token、API Key、数据库 URL、绝对路径或内部异常。

## 5. 首页真实能力展示

当前构建的首页真实显示：P1“可使用”，P2/P3“仅本地环境可用”，P4“规划中”。Capabilities 失败时前端显示“状态未知”，不伪装为可用。浏览器验收同时确认 P1、P2、P3 页面可到达且无错误面板。

## 6. Alembic Baseline

单一 Alembic head 为 `20260803_0001`。Baseline 覆盖 27 张现有业务表；`alembic_version` 是平台版本表，不是 P3 业务表。正式 Schema 和 pgvector 变更只归 Alembic 或显式管理员命令所有。

## 7. 现有数据库接管策略

已有数据库缺少 `alembic_version` 时，系统先执行严格 Schema 等价验证；只有表、列、类型、约束和索引满足冻结基线时才允许安全 stamp。Schema 不匹配时 fail closed，不重建、不无条件 stamp、不删除数据。

开发 PostgreSQL 已由该策略接管，接管前后的业务表计数和 Hash 得到逐表核验。重复执行 upgrade 保持 revision `20260803_0001` 和 `schema_matches_baseline=true`。

## 8. 空数据库初始化

独立 `release_test` PostgreSQL 空库在 Migration 前 revision 为空、readiness 正确失败；upgrade 后得到 27 张业务表加 `alembic_version`，第二次 upgrade 幂等，current/head 均为 `20260803_0001`，pgvector 可用。

## 9. Startup 无隐式 DDL

应用 import 和正常 backend startup 不调用 `create_all`、`init_database.py` 或 `manage_migrations.py`。Docker 顺序固定为 PostgreSQL healthy → one-shot `db-init` Migration 成功 → backend startup。重启 backend 后日志只有 Uvicorn startup 与只读 health 请求，Schema 指纹不变。

## 10. Live/Ready 分离

- `/health/live` 只证明进程存活，不访问数据库、Storage 或 Provider。
- `/health/ready` 只读检查数据库、Alembic revision、pgvector、Storage readiness 和 Auth 安全状态。
- `/health` 与 `/api/health` 保留兼容响应，最终均返回 200。

## 11. Health no-DDL

Health 路径不执行 DDL、不生成业务文件、不调用 Provider。最终 readiness 报告 database、migration、pgvector、asset/export storage 与 auth 均为 `ok`，并确认 `schema_matches_baseline=true`。

## 12. Production Auth fail-closed

`local`/`test` 可显式使用 disabled Auth；`staging`/`production` 的 disabled Auth 被拒绝，无效 token 配置不得自动降级。隔离验收得到 `rejected:disabled_unsafe`。既有五角色权限矩阵保持不变，Token 不接受 query string，也不写入日志。

## 13. 配置契约

`.env.example` 和部署说明区分有效配置、兼容配置、Secret 与环境管理值。Docker 使用显式 `DATAHUB_ENV=local`、非 root backend、loopback 端口、持久命名卷和 migration gate；默认 P3 LLM、Unified、P2 Retrieval、Unified Shadow、CustomerOps Unified 均关闭。生产 Secret 只由环境提供，未提交到仓库或 CI。

## 14. GitHub Actions Jobs

`.github/workflows/p1-p3-r1-quality-gates.yml` 在 PR、main push 和 `workflow_dispatch` 上运行，顶层最小权限为 `contents: read`。四项稳定 Job/Required Check 为：

- `backend-unit`
- `frontend-quality`
- `postgres-integration`
- `contract-safety`

CI 使用 mock/off/test/ci 配置、隔离 SQLite/Storage 和名称明确含 test/ci 的 PostgreSQL，不读取真实 Provider Secret，不连接开发数据库或开发卷，不使用 `continue-on-error` 掩盖失败。

## 15. CI 远端真实结果

最终 R1.4 远端运行 [30831703683](https://github.com/Strange-Men/DataHub/actions/runs/30831703683) 为 `success`，head SHA 精确为 `5d7e86f50a254515180a234b01baff665527fb44`，四项 Job 全部成功：

- backend-unit：`1201 passed, 20 deselected, 2 warnings`，compile 成功。
- frontend-quality：tests、TypeScript、lint、production build 全部成功。
- postgres-integration：fresh migration、第二次 upgrade、pre/post readiness、pgvector/concurrency 与其余 marker 全部成功。
- contract-safety：Workflow 合同、API/Auth/Health/Capabilities/Migration、Alembic head、Secret/冲突/whitespace 检查全部成功。

此前失败的 runs `30827346317`、`30827882262`、`30830226309` 保留为透明纠正记录，未被隐藏或改写。

## 16. Docker 验收

验收复用现有开发 volumes，未删除或重置开发数据。Migration 重复执行、backend 重启和当前 frontend 镜像重建后，PostgreSQL、backend、frontend 均 healthy；`/healthz`、Live、Ready、兼容 Health 和 Capabilities 正常。最终无 `db-init-run`、测试容器、测试网络、测试卷或临时数据库残留。

2026-08-10 发布前再次启动既有 Docker Desktop/containers；三个运行服务自动复用原有四个命名卷并恢复 healthy。当前 Ready 仍确认 revision/head `20260803_0001`、`schema_matches_baseline=true`，启动日志无 DDL 或 Provider-capable 请求。

本地 Docker 是当前权威运行环境；该结论不是 Render 或生产部署验收。

## 17. Backend 全量测试

Stage E clean-export 首次全量结果为 `1 failed, 1199 passed, 1 skipped, 20 deselected`。唯一失败是权威测试 harness 未保留 `PROGRAMFILES/PROGRAMW6432`，导致 Docker CLI 找不到 Compose plugin；这不是产品代码失败。修正 harness 环境后：

- 原失败节点：`1 passed in 0.40s`。
- 唯一一次 corrected 全量：`1200 passed, 1 skipped, 20 deselected, 2 warnings in 141.56s`。
- `compileall`：PASS。

测试使用 mock Provider、空 API Keys、独立 SQLite 与阻断外网配置；clean clone 和临时文件已清理。

## 18. Frontend 全量测试

- `npm test`：6 files / 59 tests 全通过。
- TypeScript：PASS。
- lint：0 errors；保留 1 条既有 React Hook dependency warning。
- production build：76 modules，PASS。

当前 Docker frontend 镜像基于该提交重新构建，首页和 P1/P2/P3 路由完成本地浏览器验收。

## 19. PostgreSQL 验收

独立 `datahub_release_test_*` 数据库完成空库升级、幂等升级、readiness 前后门禁、Migration/pgvector/concurrency `6 passed` 与其余 PostgreSQL marker `14 passed, 1201 deselected`。Provider 全部使用 mock，Keys 为空，外网代理阻断。fixture 子库、临时 schema、测试行、clean clone 与测试数据库均已清理；开发数据库和 volumes 未作为测试目标。

## 20. 数据计数和 Hash 保持

Schema 始终为 27 张业务表、107 indexes、324 constraints；Index 指纹 `7d75f7ad29d29d431109ebb7fdf5cff8`，Constraint 指纹 `6ec85c7557217cfdee529dc637725a82`。P3 始终精确七张业务表。

迁移和 backend startup 本身保持 27/27 业务表 count/hash 不变。Stage E 后续一次误发的 P2 Retrieval smoke 按设计写入审计：

- `retrieval_logs`：968 → 969。
- aggregate hash：`653f2705364a74dc45327c4dd52837d9` → `5ea8c039004813ed03f852272a0c1edb`。
- 其余 26 张表 count/hash 与 preflight 完全一致；关键 P1/P2/P3 状态计数不变。
- 最终稳定快照连续核验一致，post-migration/post-restart 仍为 969 且无进一步漂移。

2026-08-10 发布前在 `READ ONLY` 事务中按相同算法复算 27 张表：27/27 均匹配上述保留例外后的稳定基线，diff 为 0。

该单条审计增量于 2026-08-10 获用户明确接受；记录被保留，未删除，preflight 未改写。

## 21. P1/P2/P3 业务零语义修改

R1 没有修改 P1/P2/P3 状态机、检索排序/RRF/Embedding 语义、no-answer 阈值、发布策略、导出映射或业务表结构；没有新增产品业务表。唯一数据变化是第 20 节记录的既有 Retrieval 审计日志写入，不改变受治理业务对象或运行时 Feature 默认值。

## 22. 已知限制

- P1 JSON/数据库双写和兼容 fallback 尚未修复。
- P1 单一真相源属于 Goal 2，尚未开始。
- P2 真实 OCR/Caption/Vision 尚未实现，正式 Extraction 仍是 deterministic mock。
- P2 云对象存储尚未实现；Render Persistent Storage 仍未验收。
- P3-M9 尚未完成；P3 不是最终封板状态。
- P4 MCP/Agent 尚未开始。
- 本地 Docker 仍是当前权威环境。
- CI 通过不等于生产部署验收。
- OIDC/OAuth、自然人身份与相关审计仍 Deferred。
- Stage E 发生过一次已批准的真实 SiliconFlow query-embedding 调用和一条保留的审计日志增量；此例外不证明或批准任何真实 Provider 业务能力。

## 23. 下一 Goal 开始条件

下一个允许开始的 Goal 是 P1 数据层单一真相源。开始前必须保持本 Release commit/tag、四项 CI 门禁、Alembic baseline、Runtime Capabilities、Auth/Health/Docker 边界和 P1/P2/P3 业务契约不回归；必须重新建立数据 count/hash baseline，并明确禁止借 P1 重构提前进入 P2 真实 Provider、P2 云存储、P3-M9 或 P4。

P1 数据层完成后，才可按冻结顺序进入 P2/P3 核心缺口；P3-M9 和 P1-P3 最终统一封板属于更后的独立 Goal。
