# 24 — Frontend Product UX Redesign（P1-M15.7 / P1-M15.8）

## 0. P1-M15.8 更新：首页入口简化

P1-M15.8 在 P1-M15.7 的多页面架构基础上做了以下调整：

- **Hero 区简化**：删除三个重复操作按钮（开始体验、上传客服数据、使用示例数据），Hero 仅负责介绍 DataHub 的价值主张。
- **统一入口**：四个能力模块卡片作为首页唯一主入口，用户自然知道要体验就点击"客服文本中台"。
- **移除高级信息导航**：顶部导航栏不再显示"高级信息"，`/advanced` 路由已删除。
- **隐藏开发者技术细节**：公开前端不再展示 API Base URL、local JSON storage、mock retrieval、no vector DB、no embedding、no MCP 等开发者信息。后端服务状态仅显示用户级文案（服务正常 / 连接中 / 服务暂不可用，可能正在冷启动）。
- **P1 工作台不变**：P1 所有功能（导入、清洗、审核、RAG、Bad Case）保持完整可用。
- **P2/P3/P4 产品壳不变**：三个未来页面完整保留，所有操作按钮禁用并标注后续接入。

## 1. 原前端问题

P1-M15.6 之前的前端存在以下问题：

- **单页堆砌**：所有功能（导入、清洗、审核、RAG、Bad Case）堆在同一页面，无导航结构。
- **面向开发者**：页面标题是"DataHub 管理台"，字段标签是 `source_name`、`batch_id`、`candidate_id`，用户需要理解技术术语。
- **要求复制粘贴 JSON**：用户必须手动编写或复制 JSON 到 textarea 才能导入数据。
- **P2/P3/P4 仅占位卡片**：没有完整的产品页面设计，只放了 4 张卡片。
- **后端连接写死 localhost**：`API_BASE = ""` 依赖 Vite proxy，部署到 Vercel 后无法连接 Render 后端。
- **不区分普通用户和开发者**：技术状态面板和操作界面混在一起。

## 2. 新的多页面信息架构

改为 React Router v6 多页面结构，顶部导航栏：

```
首页 (/)
├── 客服文本中台 (/p1-text-hub)       ← P1，已接入真实后端
├── AI 素材中心 (/p2-material-center)  ← P2，产品壳
├── 数据资产复用 (/p3-asset-reuse)     ← P3，产品壳
└── MCP + Agent 集群 (/p4-mcp-agents)  ← P4，产品壳
```

## 3. P1-P4 每个页面职责

### P1：客服文本中台（已接入）
- 5 步工作流：导入数据 → 机器清洗 → 人工清洗 → 知识审核 → RAG & Agent
- 支持文件选择、拖拽上传、示例数据、高级粘贴模式
- 人工清洗卡片默认只显示用户能理解的信息（角色、内容、质量标签、机器建议）
- 技术字段默认折叠到"技术字段"details 中
- source trace 折叠到"查看来源"details 中
- 所有按钮和标签使用中文

### P2：AI 素材中心（未接入）
- 展示 6 步未来流程：素材导入 → OCR/Caption → 标签/SKU 绑定 → 多模态审核 → 多模态知识库 → 多模态 Agent
- 所有按钮禁用，标注"P2 后接入"
- 页面有完整的产品设计，不是一张 Roadmap 卡片

### P3：数据资产复用（未接入）
- 展示 6 个未来模块：培训资料、SOP/话术、FAQ 手册、微调导出、数据筛选、导出记录
- 所有按钮禁用，标注"P3 后接入"
- 不接真实导出功能

### P4：MCP + Agent 集群（未接入）
- 展示 MCP 工具列表（6 个工具）和 Agent 集群（4 个 Agent）
- 展示调用日志和工具权限模块
- 所有按钮禁用，标注"P4 后接入"
- 不做真实 MCP，不做假调用

## 4. 为什么隐藏开发者信息

- 目标用户是数据清洗员、知识审核员、运营人员，不是程序员
- 高级信息页面独立放置，顶部导航可进入
- 普通用户流程中不出现技术字段（除非手动展开"技术字段"折叠区）

## 5. 文件上传和示例数据设计

三种导入方式：

1. **选择 JSON 文件**：`<input type="file" accept=".json">` + FileReader
2. **拖拽上传**：drop zone 支持 drag & drop
3. **使用示例数据**：一键加载内置的中文客服聊天样例
4. **高级模式**：粘贴 JSON（默认折叠，不干扰普通用户）

## 6. Vercel + Render API 连接方案

### 前端 api.ts

```typescript
const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ||
  (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1"
    ? "http://127.0.0.1:8000"
    : "https://datahub-jr8x.onrender.com");
```

- 本地开发（localhost）：连接 `http://127.0.0.1:8000`
- Vercel 部署：读取环境变量 `VITE_API_BASE_URL=https://datahub-jr8x.onrender.com`
- 所有 API 请求通过 `apiPath()` 函数统一拼接 URL

### 后端未连接提示

不再显示红色错误和 FastAPI 启动命令。改为友好提示：

> "后端暂未连接，可能是 Render 免费实例冷启动。请稍等或点击重新检测。"

## 7. CORS 配置

后端 `main.py` 添加 CORSMiddleware：

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://data-hub-flame.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## 8. 当前限制

- 本地 JSON 文件存储（不持久化到数据库）
- 关键词匹配检索（非向量检索）
- 规则引擎（非真实 LLM）
- P2/P3/P4 仅为产品壳
- Render 免费实例可能冷启动
