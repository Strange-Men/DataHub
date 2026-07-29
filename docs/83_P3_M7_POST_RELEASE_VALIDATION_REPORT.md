# P3-M7.5 Post-release Validation and Test Contract Closure

## 1. 为什么执行 M7.5

P3-M7 Release Closure 的第一次 clean-export 全量测试为：

`1118 passed, 21 skipped, 7 failed, 44 warnings`

7 个失败均被判断为旧阶段仍禁止后来合法 `export_jobs`、`export_artifacts` 的过期测试契约。Release Closure 修订后，7 个失败节点已通过，但没有在修订后的最终测试代码上重新获得一次全量 0 failed 结果。

M7.5 只闭合该证据缺口，不新增产品功能、不改变 M7 业务语义、不进入 M8。

## 2. 七个首次失败测试

1. `test_generation_does_not_modify_p1_p2_or_write_export_tables`
2. `test_create_all_adds_only_registered_frozen_p3_tables`
3. `test_service_does_not_write_export_tables_or_call_sql_directly`
4. `test_fresh_schema_has_publication_fields_and_empty_export_tables`
5. `test_additive_upgrade_and_repeated_create_all_preserve_p1_p2_data`
6. `test_application_init_registers_current_p3_tables_idempotently`
7. `test_create_all_is_idempotent_with_review_and_export_tables`

## 3. 真实失败原因分类

| 测试 | 原保护目标 | 过期断言 | M7 后正确契约 |
| --- | --- | --- | --- |
| Deterministic generation | P1/P2 不变且不越界写 Export | Export 表绝对不存在 | P1/P2 精确不变；若表已注册则 Export 行数为 0 |
| Draft Asset Models | 当前模块只注册冻结范围内的表 | 实际表必须等于早期表集合 | 早期必需表存在，且不得超出五张 pre-M7 表加两张冻结 Export 表 |
| LLM Draft Service | 不直接 SQL、不进入 Export | Export 表绝对不存在 | 保留 SQL 源码边界；已注册 Export 表行数为 0 |
| Publication Repository | Publication 字段/约束正确且不写 Export | Export 表绝对不存在 | 保留字段、唯一索引、自引用 FK；已注册 Export 表行数为 0 |
| Additive upgrade | P1/P2 表和数据不被升级破坏 | 后续 P3 表绝对不存在 | 精确保留 P1 answer、P2 hash；已注册 Export 表行数为 0 |
| Application init | 初始化幂等并注册当前完整 Schema | 只列出五张 pre-M7 表 | 精确列出七张冻结 P3 表 |
| Review Schema | Review 表/约束幂等且不写 Export | Export 表绝对不存在 | 保留 Review 字段/约束；已注册 Export 表行数为 0 |

失败属于阶段时间边界过期，不属于 M7 产品代码缺陷。

## 4. 测试契约修订原则

- 历史测试继续验证其阶段真正拥有的字段、约束、Hash、数据保持和零越界写入。
- 历史测试不再把“最新数据库不能包含合法后续表”当作兼容条件。
- 测试模块独立运行时可只注册自身模型；全量收集共享 metadata 时允许已注册的冻结后续表，但必须证明旧阶段没有写入这些表。
- 当前完整 Schema 使用独立权威测试精确验证七张表，而不是依赖历史模块 import 顺序。
- 未删除测试，未增加 skip/xfail，未把精确约束改为 truthy 判断。

## 5. 是否存在被弱化的断言

审查发现一处需要收紧：

`test_empty_database_creates_exactly_seven_p3_tables` 名称声明 “exactly seven”，原实现却只验证七表为实际表集合的子集，并仅排除三个候选表。其他命名的第八张 `reuse_*` 或 `export_*` 业务表可能漏检。

M7.5 将其修订为：

- 实际 `reuse_*` / `export_*` 表集合必须与七张冻结表完全相等。
- P1 `knowledge_candidates` 与 P2 `assets` 必须仍存在。
- 重复 `create_all` 前后 P1/P2 列集合和数据不变。
- approved Review、published Asset、Content Hash、Source Manifest Hash、Review Hash 和 checklist 不变。
- 新增 Export 表保持零行。
- PostgreSQL 条件测试同样执行精确七表集合断言。

其他 7 个历史失败修订均保留原保护目标，没有发现删除或实质弱化。

## 6. 当前七张 P3 表权威断言

当前冻结集合精确为：

1. `reuse_projects`
2. `reuse_source_items`
3. `reuse_asset_versions`
4. `reuse_asset_version_sources`
5. `reuse_reviews`
6. `export_jobs`
7. `export_artifacts`

SQLite 与 PostgreSQL 均以集合相等断言验证，不依赖数据库系统表总数。不存在第八张 `reuse_*` / `export_*` P3 业务表。

## 7. SQLite / PostgreSQL 兼容结果

- 7 个历史失败节点：**7 passed in 2.64s**。
- SQLite Schema/compatibility：**128 passed, 1 skipped, 5 deselected in 6.33s**。
- 独立 PostgreSQL Schema/compatibility：**5 passed, 129 deselected in 2.48s**。
- PostgreSQL 隔离数据库每次均精确创建并在 `finally` 删除，未触碰开发数据库或 volume。

前两次 PostgreSQL 命令分别误选 SQLite URL、误选未安装的 `psycopg` 驱动，属于测试运行环境错误；改用项目已安装的 `psycopg2` 后 5/5 通过，没有因此修改产品或测试语义。错误 SQLite URL 产生的一个未跟踪临时数据库已按精确路径移入回收站。

## 8. 修订后最终全量 pytest

权威目录：

`.local-data/p3-m7.5-clean-export-current`

该目录由 `git archive HEAD` 加本轮唯一测试契约修订组成，未复制 `.env`、旧数据库、`.local-data` 或历史 clean-export。

最终命令：

```text
python -m pytest backend/tests -q
```

最终结果：

**1125 passed, 21 skipped, 44 warnings in 144.93s，0 failed。**

21 个 skip 均为已有环境/条件 skip；本轮未新增 skip 或 xfail。44 个 warning 为既有 FastAPI lifespan deprecation 与 mock embedding fallback，本轮不升级依赖。

compileall、Ruff changed-test check、Secret diff scan、conflict marker scan 和 `git diff --check` 通过。

## 9. P1/P2 冻结保护

- P1/P2 表、列和已有测试数据在兼容升级前后精确保持。
- P1 answer、P2 hash、published Asset、Review、Content Hash、Manifest Hash 均有回归断言。
- 本轮未修改 P1/P2 业务代码、Schema 或数据。
- 未运行 P1 Harness、P2 Acceptance 或 Eval，因为本轮只闭合测试契约。

## 10. M7 业务语义

M7 Export Model、Repository、Service、API、RBAC、Storage、序列化、Manifest、Revoke 与 Source stale 语义均未修改。本轮业务代码修改数为 0，也没有新增表、API 或前端。

真实 Provider 调用为 0；默认 `DATAHUB_AUTH_MODE=disabled`、`P3_LLM_DRAFT_ENABLED=false`。

## 11. 历史 clean-export 隔离状态

- 18 个历史 clean-export 入口全部位于 `.local-data`、被 Git 忽略且 Git 跟踪数为 0。
- tar/zip 归档只包含 `.env.example` 模板，没有 SQLite 数据库。
- 13 个历史目录包含 `datahub.db`，其中 11 个存在非空记录；无法证明全部为纯合成数据，因此按潜在敏感历史归档处理。
- 敏感模式命中只位于 `.env.example`、测试或文档样例；没有发现 runtime `.env`、私钥或证书文件。
- 当前 pytest、脚本和配置不引用这些历史路径；M7.5 使用全新独立目录，不会把旧结果当作当前证据。
- 按指令未删除、改写或提交用户已有归档。建议后续由数据所有者单独决定加密、保留或安全销毁策略。

## 12. P3-M8 开始条件

M7.5 报告、测试契约修订、commit、main push 和 `p3-m7.5-post-release-validation` annotated tag 全部固化后，M7 测试证据缺口即闭合。

P3-M8 仍必须等待新的明确指令；本轮没有开发或启动前端。
