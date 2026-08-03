# 25 — Vercel Deployment Guide（P1-M15.7）

## Vercel 部署配置

### 基础设置

| 配置项 | 值 |
|--------|-----|
| Root Directory | `frontend` |
| Framework | Vite |
| Build Command | `npm run build` |
| Output Directory | `dist` |
| Install Command | `npm ci` |

### 环境变量

| 变量名 | 值 |
|--------|-----|
| `VITE_API_BASE_URL` | `https://<backend-host>` |

> **重要**：`VITE_API_BASE_URL` 必须以 `VITE_` 开头才能在 Vite 构建时通过 `import.meta.env` 读取。
> 它会进入公开的浏览器构建产物，只能配置公开 API 地址，禁止放入 Token、数据库 URL 或 Provider Secret。

### 部署步骤

1. 在 Vercel 中导入 GitHub 仓库。
2. 设置 Root Directory 为 `frontend`。
3. 在 Environment Variables 中添加 `VITE_API_BASE_URL`。
4. 部署。
5. 等待构建完成后，访问 Vercel 分配的域名（或自定义域名）。

### 部署后检查（配置验证，不等于生产验收）

- [ ] 打开 Vercel 分配的预览或正式域名
- [ ] 顶部导航栏正常显示，可点击切换页面
- [ ] 首页根据 `/api/capabilities` 显示 P1/P2/P3 的真实能力状态，失败时显示“状态未知”
- [ ] 点击"重新检测"可重新检测后端连接
- [ ] P1/P2/P3 入口路由存在，P4 始终显示“规划中”且无虚假操作
- [ ] 浏览器请求未携带构建时 Secret；后端 RBAC 仍是权限边界

Vercel 静态前端构建成功不能证明 Render/backend、Migration、数据库、Storage 或业务链路已完成生产验收。

### 后端健康检查

```bash
curl --fail https://<backend-host>/health/live
curl --fail https://<backend-host>/health/ready
curl --fail https://<backend-host>/api/capabilities
```

`/health/live` 只检查进程；`/health/ready` 以纯读方式检查 Migration、数据库、pgvector、Storage 与 Auth，未就绪时返回 503。`/health` 和 `/api/health` 仅为兼容端点。

### 常见问题

#### 前端显示"后端暂未连接"

先直接检查 backend 的 `/health/live` 与 `/health/ready`，再点击“重新检测”。不得把 readiness 503 当作前端连接问题掩盖。

#### CORS 错误

检查部署环境的 `CORS_ALLOWED_ORIGINS` 是否包含当前 Vercel HTTPS Origin；不要通过通配符或修改前端绕过后端安全配置。

#### 前端构建失败

确保：
- `frontend/` 目录下存在 `package.json` 和 `vite.config.ts`
- `npm run build` 在本地可正常执行
- 所有 TypeScript 类型检查通过

### 本地开发

```bash
cd frontend
npm ci
npm run dev
# 访问 http://127.0.0.1:5173
# 前端自动连接 http://127.0.0.1:8000（本地后端）
```

### GitHub Website 设置（可选人工操作）

在 GitHub repo 页面：

About 右侧齿轮 → Website → 填写：

```
https://<your-vercel-domain>/
```

注意：此步骤需要手动在 GitHub UI 操作，无法通过代码自动完成。
