# 25 — Vercel Deployment Guide（P1-M15.7）

## Vercel 部署配置

### 基础设置

| 配置项 | 值 |
|--------|-----|
| Root Directory | `frontend` |
| Framework | Vite |
| Build Command | `npm run build` |
| Output Directory | `dist` |
| Install Command | `npm install` |

### 环境变量

| 变量名 | 值 |
|--------|-----|
| `VITE_API_BASE_URL` | `https://datahub-jr8x.onrender.com` |

> **重要**：`VITE_API_BASE_URL` 必须以 `VITE_` 开头才能在 Vite 构建时通过 `import.meta.env` 读取。

### 部署步骤

1. 在 Vercel 中导入 GitHub 仓库。
2. 设置 Root Directory 为 `frontend`。
3. 在 Environment Variables 中添加 `VITE_API_BASE_URL`。
4. 部署。
5. 等待构建完成后，访问 Vercel 分配的域名（或自定义域名）。

### 部署后检查

- [ ] 打开 https://data-hub-flame.vercel.app/
- [ ] 顶部导航栏正常显示，可点击切换页面
- [ ] 首页显示"后端已连接"或"后端暂未连接"（友好提示）
- [ ] 点击"重新检测"可重新检测后端连接
- [ ] P1 页面可正常导入数据、执行清洗、审核知识
- [ ] P2/P3/P4 页面显示完整产品设计，按钮禁用并标注"未接入"
- [ ] 高级信息页面显示技术状态

### 后端健康检查

```bash
curl https://datahub-jr8x.onrender.com/api/health
# {"status":"ok","service":"datahub-api","phase":"P1-M15"}
```

### 常见问题

#### 前端显示"后端暂未连接"

Render 免费实例在 15 分钟无请求后会休眠，首次访问需要 30-60 秒冷启动。点击"重新检测"即可。

#### CORS 错误

检查 `backend/app/main.py` 中 `CORSMiddleware` 的 `allow_origins` 是否包含 `https://data-hub-flame.vercel.app`。

#### 前端构建失败

确保：
- `frontend/` 目录下存在 `package.json` 和 `vite.config.ts`
- `npm run build` 在本地可正常执行
- 所有 TypeScript 类型检查通过

### 本地开发

```bash
cd frontend
npm install
npm run dev
# 访问 http://127.0.0.1:5173
# 前端自动连接 http://127.0.0.1:8000（本地后端）
```

### GitHub Website 设置

在 GitHub repo 页面：

About 右侧齿轮 → Website → 填写：

```
https://data-hub-flame.vercel.app/
```

注意：此步骤需要手动在 GitHub UI 操作，无法通过代码自动完成。
