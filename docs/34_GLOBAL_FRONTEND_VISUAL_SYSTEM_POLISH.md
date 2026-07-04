# P1-M20.6 Global Frontend Visual System Polish

## 目标

本轮目标不是只修 P1 页面，而是把 DataHub **全部前端页面**统一成同一套克制、专业、暗黑风的产品视觉系统。

## 覆盖范围

### 审计了全部前端文件

- `frontend/src/styles.css` — 全局样式系统
- `frontend/src/App.tsx` — 路由入口
- `frontend/src/components/Layout.tsx` — 顶部导航栏
- `frontend/src/components/Shared.tsx` — 共享组件
- `frontend/src/pages/HomePage.tsx` — 首页
- `frontend/src/pages/P1TextHub.tsx` — 客服文本中台 (P1)
- `frontend/src/pages/P2MaterialCenter.tsx` — AI 素材中心 (P2)
- `frontend/src/pages/P3AssetReuse.tsx` — 数据资产复用 (P3)
- `frontend/src/pages/P4McpAgents.tsx` — MCP + Agent 集群 (P4)
- `frontend/src/pages/AdvancedPage.tsx` — 高级信息

### 覆盖的页面

1. 首页 — Hero、能力卡片、连接状态
2. 客服文本中台 — 4步主流程、子标签、操作面板
3. AI 素材中心 — Roadmap banner、流程卡片、信息面板
4. 数据资产复用 — Roadmap banner、模块卡片、信息面板
5. MCP + Agent 集群 — Roadmap banner、工具卡片、Agent 卡片
6. 顶部导航栏 — 品牌、链接、状态指示器
7. 全局服务状态 — 连接指示器、badge
8. 空状态、禁用态、Roadmap 卡片

## 统一的设计 Token

在 `:root` 中新增并整理了完整的 CSS 设计 token：

### 页面与表面 (Background & Surface)
- `--bg-page`, `--bg-appbar`, `--bg-surface`, `--bg-surface-raised`, `--bg-surface-soft`, `--bg-surface-muted`
- `--bg-input`, `--bg-input-focus`

### 边框 (Border)
- `--border-subtle`, `--border-strong`, `--border-accent`

### 文本 (Text)
- `--text-primary`, `--text-secondary`, `--text-muted`, `--text-faint`

### 强调色 (Accent)
- `--accent: #22d3ee` — 克制暗青色
- `--accent-hover`, `--accent-soft`, `--accent-blue`
- 不再使用高饱和亮蓝 `#1f9df0` 大面积涂按钮

### 语义色 (Semantic)
- `--success`, `--success-soft`
- `--warning`, `--warning-soft`
- `--error`, `--error-soft`
- `--purple`, `--purple-soft`

### 间距 (Spacing)
- `--space-page: 28px`, `--space-section: 28px`, `--space-card: 24px`, `--space-element: 16px`, `--space-tight: 10px`

### 圆角 (Radius)
- `--radius-card: 10px`, `--radius-button: 8px`, `--radius-sm: 6px`, `--radius-pill: 999px`

### 按钮 (Button)
- `--btn-height: 40px`, `--btn-height-lg: 48px`, `--btn-height-sm: 32px`
- `--btn-padding-x: 20px`, `--btn-padding-x-lg: 28px`, `--btn-padding-x-sm: 12px`

### 向后兼容别名
保留了 `--canvas`, `--surface`, `--line`, `--text`, `--text-strong`, `--muted`, `--faint`, `--accent-green`, `--accent-purple`, `--danger` 等旧别名，确保不破坏已有代码。

## 统一的按钮规范

### 按钮层级

| Class | 用途 | 背景 | 边框 |
|-------|------|------|------|
| `button` (default) | 通用基础按钮 | `--bg-surface` | `--border-subtle` |
| `.btn-primary` | 主要操作 | 暗青-深蓝渐变 | 青色半透明边框 |
| `.btn-secondary` | 次要操作 | 暗表面 | 青色微边框 |
| `.btn-outline` | 轮廓按钮 | 透明 | 微弱边框 |
| `.btn-danger` | 危险操作 | 暗红色 | 红色边框 |
| `.btn-disabled` | 禁用/未接入 | 极暗灰 | 极弱边框 |
| `.btn-next` | **下一步（统一）** | 暗青渐变 | 青色边框 |
| `.btn-small` | 小工具按钮 | 透明 | 暗色边框 |

### 关键修复

1. **默认按钮不再使用刺眼亮蓝渐变** (`#1f9df0 → #1478ca`)。
2. **主按钮改为暗青-深蓝渐变** (`#0e5a6b → #0d4a58`)，专业、克制。
3. **新增 `.btn-next`** 统一所有"下一步 →"按钮，高度、颜色、圆角、hover 完全一致。
4. **禁用按钮** 使用独立样式而非简单 `opacity: 0.5`。
5. **P2/P3/P4 "暂未接入"按钮** 统一使用 `.btn-disabled`。

## 统一的卡片与模块

### 卡片类型统一

| 类型 | Padding | Radius | Background | Border |
|------|---------|--------|------------|--------|
| 能力卡片 (Home) | 24px | 10px | `--bg-surface` | `--border-subtle` |
| 流程卡片 (P2/P3) | 22px | 10px | `--bg-surface` | `--border-subtle` |
| 工作步骤 (P1) | 24px | 10px | `--bg-surface` | `--border-subtle` |
| 子区域 (P1) | 20px | 8px | `--bg-surface-soft` | `--border-subtle` |
| 信息卡片 (P2/P3/P4) | 20px | 8px | `--bg-surface` | `--border-subtle` |
| 工具/Agent 卡片 (P4) | 16-18px | 8-10px | `--bg-surface` | `--border-subtle` |

所有卡片背景色、边框色、圆角统一，不同页面看起来像同一产品。

### 统一的其他元素

- **空状态 (empty-state)**：统一虚线边框 `rgba(90,110,138,0.22)`，统一内边距 `40px 24px`。
- **Badge 系统**：统一 `padding: 3px 10px`、`border-radius: 999px`、`font-size: 0.76rem`。
- **状态统计**：统一 `border-radius: 999px` 药丸样式。
- **进度条**：改为暗青渐变 `#0e7490 → #22d3ee`（不再使用亮蓝 `#1f9df0`）。
- **导航 Logo**：改为暗青渐变 `#0e7490 → #155e75`（不再使用亮蓝 `#1f9df0 → #1478ca`）。
- **标签激活态**：保持暗青色 `--accent`，不过亮。
- **内容预览文字**：从 `#dbeafe`（太亮）改为 `#c4d5e8`（柔和）。

## 修改的文件

1. `frontend/src/styles.css` — 全面重构，新增 token 体系，统一按钮/卡片/间距/颜色
2. `frontend/src/pages/P1TextHub.tsx` — 5 个"下一步"按钮统一为 `btn-next`

P2/P3/P4 页面（MaterialCenter、AssetReuse、McpAgents）和 HomePage、Layout、Shared 组件无需修改——它们已通过统一的 CSS class 自动获得一致的视觉风格。

## 未改动的事项

- 未改变 P1 四个主流程结构（导入 → 清洗 → 审核生成 → Agent 测试）
- 未改变数据库逻辑
- 未改变 API 逻辑
- 未进入 P2/P3/P4 后端开发
- 未恢复 7 个 Step
- 未恢复高级信息页面路由
- 未提交 `.env` / `datahub.db` / `backend/storage/` / API Key
- 未打 tag
