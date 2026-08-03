# DataHub 统一质量门

`.github/workflows/` 中的工作流用于对后端、前端、PostgreSQL 迁移和契约安全进行统一验证。它们在 Pull Request、推送到 `main` 以及人工 `workflow_dispatch` 时运行。

## 建议的 required checks

建议仓库管理员在 GitHub Branch Protection 中将以下稳定 Job 名称配置为 `main` 的 required checks：

- `backend-unit`
- `frontend-quality`
- `postgres-integration`
- `contract-safety`

这些只是建议配置名称。仓库内文件无法证明 GitHub Branch Protection 已启用，本文档也不声称它已启用。应以 GitHub 仓库设置中的实际规则为准。

## 安全边界

- 后端与前端离线检查不注入真实密钥，不读取本地 `.env`，不调用真实 Embedding、LLM 或其他 Provider。
- PostgreSQL 集成检查使用 CI 专属的 pgvector Service Container 和名称显式包含 `test` 的独立测试库，不指向开发或业务数据库。
- 质量门不上传 Secret、数据库导出、业务数据或本地运行产物。

## 查看真实 Actions 状态

只有 GitHub 上某次 Actions Run 的实际 conclusion 才是远程 CI 证据：

1. 在 Pull Request 的 **Checks** 页查看四个 Job 的实际状态和日志。
2. 在仓库 **Actions** 页选择对应 Commit 或 `main` 分支的 Run。
3. 也可使用 `gh run list --branch main` 查看近期 Run，使用 `gh run view <run-id> --log-failed` 查看失败日志。

本地测试结果、本文档或工作流定义本身，都不能代替远程 Actions 的实际成功结论。
