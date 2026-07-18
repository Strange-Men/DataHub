# P1/P2-M9.4A Engineering Reliability and Test Environment Isolation Report

## 1. 结论

M9.4A 已完成工程可靠性与测试环境隔离。开发 Docker 栈保持运行时，rebuild CLI、离线测试、独立 PostgreSQL/pgvector 集成测试和 Docker test profile 均可执行；测试结束后不残留测试进程、端口、容器或 volumes。没有修改数据库 schema、检索排序、RRF、CustomerOpsAgent 默认行为或 Unified opt-in，也没有实现 No-answer Gate。

## 2. 已知干扰与根因

复现时开发 backend 持续 healthy。`test_rebuild_script_with_base_url_shows_usage` 把固定的 `http://127.0.0.1:8000` 当作参数语法检查目标：backend 运行时，该测试真实调用 `/api/health` 和 `/api/rag/build`，耗时 14.69 秒；backend 停止时则快速连接失败。同一文件的本地模式还复制整个宿主环境并允许使用项目默认数据库/兼容 Storage，单项曾耗时 41.75 秒。

根因是测试未定义自己的服务发现、Provider、数据库和 Storage 边界，而不是业务超时或 pytest 失败。扩大 timeout、sleep 或要求人工停止开发容器都不能解决该问题。

## 3. 修复方案

- 固定开发端口改为绑定 `127.0.0.1:0` 的随机端口 HTTP Stub，Stub 返回受控 health/build 契约并在 `finally` 中 shutdown、close、join。
- 子进程使用白名单环境，不再复制完整 `os.environ`；明确注入 mock Provider、临时 test SQLite、临时 Asset root、disabled Auth 和短超时。
- 真实 Provider 的 timeout、401、403、429、5xx 使用故障对象注入，不发送网络请求；输出统一脱敏。
- 本地 CLI 行为通过函数级受控 build 结果验证；参数测试在 Provider 检查阶段 fail closed，不读取开发 Storage。
- clean-export 脚本测试显式加入导出目录自身的 `scripts` 路径，消除对收集顺序或原工作区 `sys.path` 的依赖。

最终 rebuild/隔离聚焦集合为 27 passed，最慢的随机 Stub CLI 用例 0.69 秒；没有扩大 timeout 或加入 sleep。

## 4. 三层测试环境

### A. Unit / Offline

- `DATAHUB_TEST_MODE=offline`
- `EMBEDDING_PROVIDER=mock`、`LLM_PROVIDER=mock`
- test SQLite 文件名必须包含 `test`
- Provider Key 不进入子进程
- HTTP/HTTPS proxy 指向本地拒绝端口；localhost 仅供受控 Stub
- 临时目录随测试清理

### B. PostgreSQL/pgvector Integration

- 数据库固定名 `datahub_test`，宿主端口默认 55432。
- `DATAHUB_TEST_DATABASE_URL` 缺失时文件安全 skip；URL database name 不含 `test` 或等于声明的开发 URL 时直接拒绝。
- 使用真实 PostgreSQL 16 + pgvector 0.8.5，应用表由正常 db-init 创建。
- 每项测试仅创建 `m94a_` scope，前后清理；最终 test DB Assets、Knowledge Assets、M9.4A Embeddings 均为 0。

### C. Docker E2E

- `compose.test.yaml` + profile `test` + 独立 project name。
- backend 18000、PostgreSQL 55432，不占用开发 8000/5433/5173。
- 网络、PostgreSQL、Asset、backend Storage、runtime manifest volumes 全部独立。
- test backend 强制 mock Provider、disabled Auth、所有 Unified/Agent opt-in flag false。

## 5. 数据库和 Compose 安全门禁

`scripts/test_environment.py` 在测试启动前拒绝：非 test 数据库、test/dev 相同 URL、真实 Provider Key、非 mock offline Provider、缺少 `test` 的 Docker project name，以及与开发端口重叠的 test ports。错误均为明确的 fail-closed 原因，不会静默降级。

测试密码只在运行进程中注入，未写入 `.env`、Compose、源码、日志或 Git。`compose.test.yaml` 要求调用者提供 ephemeral test-only password，不生成或复用开发密码。

## 6. PostgreSQL/pgvector 结果

独立 test stack 的真实集成套件 5 passed（3.85 秒）：

- vector extension 可用，vector(3) 正确写入。
- 错误维度写入触发 PostgreSQL 失败并完整 rollback。
- cosine 排序为 near → far。
- `status=serving` 和当前 fingerprint 双门禁排除了 archived 与 stale rows，archived leakage 为 0。
- 临时数据库连接失败返回安全 backend/status，不含密码或 URL；原 test DB 随后 `SELECT 1` 恢复成功。

## 7. 事务与回滚

- Review approved + Snapshot：注入 Snapshot 唯一冲突后，Review 最终仍为 pending，Snapshot 仍只有原记录。
- Index Entry + Chunk Projection：Chunk 主键冲突后 entry 保持 building，未留下 target chunk。
- Embedding 保存：主键冲突后 entry 保持 ready、不进入 serving，目标 fingerprint 行数为 0。
- Serve/Archive：两者争用同一 PostgreSQL row lock，最终状态始终 archived、sync_state archived；物理向量保留。
- Storage：对象写入失败不创建 metadata；metadata commit 失败只删除刚写入的 test object。
- Retrieval log：写入异常触发 rollback，但健康 Unified 检索结果仍返回。

## 8. 并发与幂等

- 四路相同 Snapshot publish 只创建一个 Knowledge Asset。
- 两路不同 Snapshot publish 由 Asset row lock 串行分配唯一版本，最终仅一个 active。
- 四路相同 Knowledge Asset index 只创建一个 Index Entry。
- Serve/Archive 并发不产生非法 serving；Archive 重放保持 archived。
- 既有相关回归继续覆盖重复 publish/index/embed/serve/archive、fingerprint idempotency、Unified branch timeout/both-failure、Agent opt-in fallback 和 Bad Case draft idempotency。

## 9. 故障注入

- Provider：timeout、401、403、429、5xx、错误维度、空/不完整 batch 均使用 Mock/Fake，不访问 SiliconFlow；错误不含 sentinel Secret。
- Storage：写入失败、metadata 失败后的对象补偿删除、路径和配置安全由聚焦测试覆盖。
- Database：连接失败、事务唯一冲突、pgvector 错误维度和恢复连接均在 test DB/子进程中验证。
- Retrieval：P1/P2 单分支失败、双分支失败、branch timeout、post-filter/fusion 边界和 log failure 保留既有安全降级；P1 默认 Agent 不依赖 P2。

相关 M9.1/M9.2/P2/Unified/Agent/Archive 聚焦回归为 155 passed、30 warnings（114.62 秒）。

## 10. 开发栈与测试栈并行证据

开发项目 `datahub` 与测试项目 `datahub-m94a-test` 同时运行并 healthy：

- dev backend/PostgreSQL：8000/5433，数据库 `datahub`。
- test backend/PostgreSQL：18000/55432，数据库 `datahub_test`。
- dev API 返回 69 Assets；test API 返回 0 Assets，证明请求和数据分流。
- dev 数据库在测试前后均为 69 Assets / 80 Knowledge Assets。
- test cleanup 后 test DB 为 0 Assets / 0 Knowledge Assets / 0 `m94a_` Embeddings。
- 只对 `datahub-m94a-test` 执行 `down -v`；最终 test containers=0、test volumes=0，开发三服务仍 healthy。

## 11. 性能观察

- 固定开发 backend 的 CLI 用例由 14.69 秒真实调用改为 0.69 秒受控 Stub；本地 rebuild 耦合用例由 41.75 秒降为约 0.17 秒 fail-closed 参数/环境验证。
- 既有 Unified timeout 测试继续证明两分支并行且慢分支受统一 budget 约束；没有修改线程池或 RRF。
- P2 query embedding 在一次 search 中只构建一次；Retrieval log failure 不阻塞主结果。
- Source Trace 当前仍按候选重新验证，存在小 corpus 下可接受但尚未量化的 N+1 风险；没有 EXPLAIN/规模阈值证据，因此本阶段不做查询重构或 ANN 索引变更。

## 12. 全量门禁

- clean-export backend：430 passed、5 skipped、44 warnings，91.19 秒。
- 5 个 skip 是显式要求 `DATAHUB_TEST_DATABASE_URL` 的 PostgreSQL 文件；同一文件已在独立栈单独 5 passed。
- frontend production build：PASS，Vite 54 modules。
- Docker dev/test parallel：PASS。
- Secret、ignored artifact、process/container cleanup 和 `git diff --check` 在 Git 收尾执行。

## 13. 兼容性

- archived leakage 保持 0。
- CustomerOpsAgent 默认保持 P1-only。
- Unified 仍需显式 opt-in，默认 flag 全部 false。
- Auth/RBAC 聚焦回归包含在 155 项与全量 430 项中。
- 开发数据库、开发 Asset/manifest volumes、sealed tags 均未修改或移动。

## 14. 已知限制

- 本阶段是轻量确定性并发门禁，不是压力测试或容量认证。
- Provider HTTP 状态使用故障注入，不宣称真实 SiliconFlow 故障演练。
- 没有引入数据库迁移或新约束；依赖当前 row locks 与唯一约束验证。
- Render/Persistent Disk 仍未验收，本地 test profile 不能替代线上证据。
- No-answer 数据集、阈值、Shadow/Active Gate 均未实现。

## 15. M9.4B 入口建议

M9.4B No-answer Gate 尚未开始。下一阶段必须先建立标注数据集并测量各检索模式的分布，默认关闭、先 Shadow、显式启用；不得凭感觉修改阈值、RRF 或 Agent 默认行为。
