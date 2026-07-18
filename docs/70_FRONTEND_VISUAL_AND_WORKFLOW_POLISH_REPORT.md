# P1/P2 Frontend Visual and Workflow Polish Report

## 1. Scope

This change is a presentation-only polish on top of commit `f55a16d5d154cfa0151dc964550a5ed2be7b1d60`. It changes the homepage, P2 workflow presentation and retrieval-validation interaction without changing backend business code, database schema, API routes or request contracts, Retrieval/RRF/Embedding, No-answer thresholds, Auth/RBAC, lifecycle state transitions, CustomerOpsAgent defaults or Unified opt-in.

## 2. Homepage

- Replaced five unrelated Emoji with consistent `P1`, `P2`, `P3`, `P4` and `QA` square marks.
- Reordered the capabilities as P1, P2, P3, P4, then the independent retrieval/Agent acceptance tool.
- Desktop viewports use five equal-width/equal-height cards in one row. The 1366 breakpoint uses 3+2 and mobile uses one column.
- Compressed the Hero to a title/description and one compact status bar. The large three-row status box and excess whitespace were removed.
- P1, P2 and retrieval/Agent cards use one “可使用 / 进入模块” pattern.
- P3/P4 are non-interactive “规划中” cards with one concise reason and no duplicate disabled button or warning block.

## 3. Retrieval and Agent Validation Positioning

The user-facing name is now consistently **“检索与 Agent 验证”** in navigation, homepage and page heading. Its description states that the tool validates P1, P2, combined retrieval and customer-service Agent recall, citations and safe abstention. It is not presented as a P1-P4 phase and no API path or backend module name changed.

Tabs now read:

- P1 文本检索
- P2 多模态检索
- 联合检索
- 客服 Agent

The query area is shorter, exposes a character count, keeps the submit button disabled for empty input and separates input from result presentation.

## 4. P2 Five-stage Workflow

The ten backend steps are still mapped exactly as before but are grouped into five user stages:

1. 素材上传与解析
2. 内容修订与审核
3. 知识快照与发布
4. 索引构建与开放检索
5. 检索验证与归档

The compact header derives the current stage from existing Asset, Extraction, Review/Snapshot, Knowledge Asset, Index, Embedding and lifecycle states. It displays the current stage, current Chinese status, next suggested action and a primary navigation action. It never writes a synthetic backend state.

Main-operation terminology is Chinese: 内容解析、人工审核、知识快照、知识资产、建立索引、生成向量、向量已就绪、开放检索、归档 and 来源追踪. IDs and index generation/chunk details remain available under concise trace or expandable technical detail.

Visibility wording remains explicit:

- 向量已就绪：知识向量已经生成，点击“开放检索”后才会被搜索到。
- 已开放检索：当前知识已经开放检索，可以进入“检索与 Agent 验证”。
- 已归档：该知识已停止检索，历史记录和来源链仍然保留。

Ready, serving, failed and archived mappings only change visible labels and guidance; lifecycle APIs and gates are untouched.

## 5. Unified Switch

The oversized native checkbox was replaced by a reusable accessible switch:

- visual size: 44 × 24 px;
- `role="switch"` and `aria-checked` expose the real state;
- off state: `Shadow` — “仅观察 P1/P2 联合召回，不影响最终结果。”;
- on state: `Active` — “使用联合检索结果作为本次验证结果。”.

The existing `activeUnified` state and `shadow_mode: !activeUnified` payload remain unchanged. CustomerOpsAgent uses the same compact control while keeping the existing default P1-only and explicit per-request Unified opt-in.

## 6. Responsive Browser Acceptance

The local Vite page was inspected in the in-app browser using calibrated CSS viewports. No viewport produced page-level horizontal overflow or console errors.

| Viewport | Homepage | Navigation / workflow | Result |
|---|---|---|---|
| 1920 × 1080 | 5 cards, one row, equal 314 × 226 px | Hero 210 px; title not clipped; all cards above 576 px | PASS |
| 1440 × 900 | 5 cards, one row, equal 266 × 226 px | no overflow; five-stage P2 track remains one row | PASS |
| 1366 × 768 | 3+2 cards, equal 422 × 226 px | page remains operable; no narrow cards | PASS |
| 390 × 844 | 5 single-column cards, 341 px wide | navigation wraps without its own scrollbar; P2 stages single-column; controls full-width | PASS |

The retrieval page was also checked at desktop and mobile sizes. Its four tabs become 2×2 on mobile; the switch remains 44 × 24 px and the submit action remains reachable without horizontal scrolling.

## 7. Tests and Build

- Frontend governance, P2 state mapping, Auth frontend and No-answer/Unified contracts: **11 passed**, 2 existing FastAPI deprecation warnings, 1.17 seconds.
- Production build: **PASS**, TypeScript + Vite, 56 modules, 842 ms.
- Browser console errors: 0.
- `git diff --check`: PASS.
- Temporary Vite process: stopped; `frontend/dist` remains ignored and is not committed.

## 8. Preserved Boundaries

- No backend application file changed.
- `/api/auth/me` remains the only trusted role source and five-role UX permissions remain unchanged.
- P1 remains usable and P2 actions still call the same real APIs.
- CustomerOpsAgent remains P1-only by default.
- Unified remains explicit opt-in.
- P3/P4 remain disabled and have no real entry.
- No database, runtime data, vector, Secret or build output is included.
