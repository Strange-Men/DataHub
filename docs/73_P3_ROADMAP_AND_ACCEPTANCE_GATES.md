# P3 路线与验收门禁

> 状态：P3-M0.1 规划审核通过并冻结；P3-M1 尚未开始。
> 本文冻结路线和阶段门禁，不表示任何 P3 业务能力已经实现。

## 1. 路线目标

P3 按“来源资格 -> 项目与来源 -> 确定性草稿 -> 可选 LLM -> 审核版本 -> 资料发布 -> 数据集导出 -> 中文前端 -> Release Closure”逐步交付。每个阶段只有一个核心能力，完成后停止，等待下一条明确指令。

```text
P3-M0 规划
-> M1 来源资格
-> M2 项目与来源冻结
-> M3 确定性草稿
-> M4 可选 LLM Provider
-> M5 编辑/审核/版本
-> M6 资料资产发布
-> M7 JSONL/CSV 导出
-> M8 中文任务流
-> M9 质量、Docker、Release Closure
```

## 2. 全阶段执行规则

1. P1/P2 业务代码冻结；P3 通过新增模块和只读适配器接入。
2. 每个开发 Prompt 只实现一个能力，默认最多修改 1～2 个核心实现文件。
3. schema/repository、service/API、frontend、tests、docs/Git 收尾尽量拆成不同 Prompt。
4. 一个 Prompt 结束时先跑其聚焦测试；一个阶段结束时再跑相关回归。
5. 每个 commit 必须功能完整、业务可用，Commit Message 使用中文。
6. 每阶段最后一个 commit 推送后创建独立 annotated tag；不得移动历史 tag。
7. 不自动连续进入下一阶段；阶段完成、commit、tag、push 后立即停止。
8. 未通过硬门禁不得通过修改期望值、跳过测试或放宽来源规则“修复”。
9. 测试只使用合成数据和独立测试环境，不接触保留开发卷。
10. P3-M0.1 仅完成文档固化、commit/tag/push；收尾后必须停止，不自动进入 M1。

## 3. 复杂度口径

| 级别 | 含义 | 典型范围 |
|---|---|---|
| S | 单模块、低迁移风险 | 1～2 个独立开发日 |
| M | 跨 repository/service/API 或一组状态迁移 | 3～5 个独立开发日 |
| L | 跨后端、前端、事务和 Docker 验收 | 6～10 个独立开发日 |
| XL | 多阶段组合，仅用于总量观察 | 10 个以上独立开发日 |

这是相对复杂度，不是交付承诺；真实数据规模、身份方案和 Provider 决策会改变工期。

## 4. 路线总览

| 阶段 | 核心能力 | 复杂度 | 强制入口 | 强制停止点 |
|---|---|---:|---|---|
| P3-M0 | 规划、边界和契约草案/固化 | S | P1/P2 冻结基线 | 文档待审或固化后停止 |
| P3-M1 | 来源只读查询与资格判定 | M | M0 已人工固化 | 合法/非法来源门禁通过 |
| P3-M2 | Reuse Project 与来源选择冻结 | L | M1 tag 已推送 | 项目和不可变来源快照可用 |
| P3-M3 | 模板与确定性草稿生成 | M | M2 tag 已推送 | 相同输入产生相同 generated 版本 |
| P3-M4 | 可选 LLM 草稿 Provider | M | Provider/数据边界已批准 | 默认关闭、失败安全后停止；可延期 |
| P3-M5 | 人工编辑、审核和版本 | L | M3，或已明确跳过 M4 | approved/published 尚未混同 |
| P3-M6 | 培训/SOP/话术/题库发布 | M | M5 tag 已推送 | 资料类 current published 可用 |
| P3-M7 | SFT 数据集与 JSONL/CSV 导出 | L | M6 tag 已推送 | Artifact/Manifest 可复现 |
| P3-M8 | 中文前端完整任务流 | XL | M7 后端契约冻结 | 所有启用操作调用真实 API |
| P3-M9 | 质量评测、Docker 验收、Release Closure | L | M8 tag 已推送 | 本地 Docker release tag 后停止 |

## 5. P3-M0：规划、边界和契约固化

### 5.1 阶段契约

| 项目 | 内容 |
|---|---|
| 目标 | 形成 PRD、架构/数据契约和分阶段路线，供人工审核 |
| 输入 | HEAD `3a969c3d...`；P1/P2 冻结状态；现有 schema、RBAC 和前端导航 |
| 输出 | `docs/71_*`、`docs/72_*`、`docs/73_*`、`docs/74_*` 和 P3 状态记录 |
| 允许修改 | 当前草案轮仅三份新增规划文档；固化轮仅文档修订、状态登记和 Git 收尾 |
| 禁止范围 | 业务代码、数据库、API、前端、测试运行、Docker、P3-M1 |
| 数据对象 | 只设计，不创建 |
| API | 只写草案，不实现 |
| 前端 | 只写页面草案，不修改现有 P3 disabled shell |
| 测试 | 当前轮不运行；只做文档完整性和 Git 状态检查 |
| 验收指标 | 状态机、七表、来源、权限、Migration、Artifact 和阶段路线全部冻结；无阻断 M1 的未决项 |
| 回滚点 | 回退 P3 规划/状态文档 commit，不触碰 P1/P2 |
| 下一阶段入口 | `p3-m0-planning-freeze` 已推送、工作树 clean，并收到独立 P3-M1 指令 |

### 5.2 Git 建议

- 固化 Commit：`[P3-M0] docs: freeze data asset reuse plan`
- Annotated Tag：`p3-m0-planning-freeze`
- commit/tag 正常推送后立即停止。

## 6. P3-M1：复用来源只读查询与资格判定

### 6.1 核心目标

建立 P1/P2 统一只读来源 DTO、资格策略和分页查询，能够稳定区分 approved/current/non-archived 与所有拒绝原因。M1 不保存项目，不生成草稿。

### 6.2 开发 Prompt 切分

1. **M1-A：资格判定核心**
   新增 source schema/policy 与 P1/P2 只读 adapter；不新增路由。
2. **M1-B：来源查询 API**
   新增分页查询/evaluate 路由，复用 M1-A；不新增持久化。
3. **M1-C：测试与文档/Git 收尾**
   只补测试、契约文档和阶段报告；不改判定逻辑，除非测试确认缺陷后另开修复 Prompt。

每个 Prompt 完成一个可测试能力并独立 commit；M1-C 推送后打阶段 tag。

### 6.3 阶段契约

| 项目 | 内容 |
|---|---|
| 输入 | 固化的 source eligibility v1；P1/P2 只读表 |
| 输出 | 统一 source ref、eligibility result、reason code 和分页 eligible source API |
| 允许修改 | 新 P3 source schema/service/route；路由注册；聚焦测试；M1 文档 |
| 禁止范围 | P1/P2 表和 service 写路径、P3 表、草稿、LLM、前端、导出 |
| 数据对象 | 非持久化 `ReuseSourceRef`、`SourceEligibilityResult` |
| API | `GET /api/reuse/sources/eligible`；`POST /api/reuse/sources/evaluate` |
| 前端 | 无 |
| 测试 | P1 approved/漂移；P2 active/current/archived/old；ready-not-serving；Bad Case 修正；Trace 完整；分页/RBAC |
| 验收指标 | invalid source 进入 eligible 列表为 0；archived/old leakage 为 0；合法 Trace coverage 100% |
| 停止条件 | 聚焦和 P1/P2 相关回归通过；API 契约冻结；无数据库变更 |
| 回滚点 | 回退新增 P3 source 模块和路由注册；P1/P2 零数据变化 |
| 下一阶段入口 | M1 commit/tag/push 完成并人工授权 M2 |

### 6.4 Git 建议

- Commit：`[P3-M1] 功能：新增复用来源资格判定与只读查询`
- Tag：`p3-m1-source-eligibility`

## 7. P3-M2：Reuse Project 和来源选择基础

### 7.1 核心目标

持久化复用项目和不可变来源快照，使后续生成使用固定来源集合。M2 不生成任何内容。

### 7.2 开发 Prompt 切分

1. **M2-A：Project/Source 数据模型与 repository**
   只新增 `reuse_projects`、`reuse_source_items` 和 repository/additive `create_all` 注册。
2. **M2-B：Project API**
   只实现项目 CRUD 和状态规则。
3. **M2-C：来源选择与重检 API**
   只实现 source attach/remove/revalidate，调用 M1。
4. **M2-D：事务、幂等测试和阶段收尾**。

### 7.3 阶段契约

| 项目 | 内容 |
|---|---|
| 输入 | M1 合格 source ref 和 eligibility policy version |
| 输出 | ReuseProject、唯一 source binding、受控来源快照、重检状态 |
| 允许修改 | P3 ORM/repository/service/routes；additive `create_all` 表注册；聚焦测试和 M2 文档 |
| 禁止范围 | 修改 P1/P2 schema；资产版本、生成、审核、发布、导出、前端 |
| 数据对象 | `ReuseProject`、`ReuseSourceItem` |
| API | project CRUD；source attach/remove/revalidate |
| 前端 | 无 |
| 测试 | 唯一 canonical source；并发 attach；幂等重放；来源捕获最小化；stale；回滚；RBAC |
| 验收指标 | duplicate source rate 0；SourceItem capture completeness 100%；失败无孤儿项目/来源 |
| 停止条件 | 只读源未被写入；项目来源集合可稳定重放；所有 P3 表仅含合成测试数据 |
| 回滚点 | 回退 P3 migration/模块；无跨 P1/P2 外键级联删除 |
| 下一阶段入口 | M2 commit/tag/push 后人工授权 M3 |

### 7.4 Git 建议

- Commit：`[P3-M2] 功能：建立复用项目与来源快照`
- Tag：`p3-m2-reuse-project-source-selection`

## 8. P3-M3：模板与确定性草稿生成基础

### 8.1 核心目标

以版本化只读模板把固定来源集合转换为可编辑 `generated` 版本；相同输入得到相同内容。M3 不接真实 LLM，不审核、不发布。

### 8.2 开发 Prompt 切分

1. **M3-A：模板 registry 和类型化输出 schema**。
2. **M3-B：确定性 generator**。
3. **M3-C：generated 版本持久化最小模型与 generate API**。
4. **M3-D：确定性、失败回滚和阶段收尾**。

若 M2 尚未引入 `reuse_asset_versions`，M3-C 只新增该表及 `reuse_asset_version_sources`；不提前新增 Review/Export 表。

### 8.3 阶段契约

| 项目 | 内容 |
|---|---|
| 输入 | active 项目、合格 SourceItems、固定模板版本 |
| 输出 | `ReuseAssetVersion.status=generated`、内容 hash、source manifest hash |
| 允许修改 | template registry、generator、资产版本最小 persistence/API、聚焦测试 |
| 禁止范围 | 真实 LLM、审核、批准、发布、导出、前端模板编辑器 |
| 数据对象 | `ReuseAssetVersion` generating/generated/failed；`reuse_asset_version_sources` |
| API | create asset version；deterministic generate；读取版本 |
| 前端 | 无 |
| 测试 | 五种 asset_kind schema；排序；必填字段；引用覆盖；相同输入 hash；失败 rollback |
| 验收指标 | required field completeness 100%；citation coverage 100%；同输入内容/checksum 100% 一致 |
| 停止条件 | 生成结果只能是 generated/failed；数据库不存在 approved/published 结果 |
| 回滚点 | 回退模板/generator 和 P3 资产版本表；项目/来源仍可保留或按 migration 回退 |
| 下一阶段入口 | M3 tag 推送；人工选择 M4 或明确延期并进入 M5 |

### 8.4 Git 建议

- Commit：`[P3-M3] 功能：新增模板化确定性草稿生成`
- Tag：`p3-m3-deterministic-draft-generation`

## 9. P3-M4：可选 LLM 草稿生成 Provider

### 9.1 核心目标

在默认关闭、最小数据、失败安全的条件下，为 generated 草稿增加可替换 LLM Provider。该阶段可延期，不是 M5 的必需前置。

### 9.2 入口硬门禁

以下 M4 实施选择必须在该阶段入口明确：

- 允许的 Provider/模型。
- 数据是否可发送到外部服务。
- Secret 注入方式。
- Prompt 审批和最大内容限制。

未关闭时，M4 状态为 **DEFERRED**，不得接真实 Provider；人工可明确跳过后授权 M5。

### 9.3 开发 Prompt 切分

1. **M4-A：Provider protocol、offline fake 和默认关闭配置**。
2. **M4-B：一个已批准 Provider adapter**；不同时接多个 Provider。
3. **M4-C：生成校验、故障注入、Secret 审计和阶段收尾**。

### 9.4 阶段契约

| 项目 | 内容 |
|---|---|
| 输入 | M3 template/schema；明确批准的 Provider 决策 |
| 输出 | 可选 LLM generated 草稿、provider/model/prompt/request/response hash |
| 允许修改 | P3 generation provider 模块、配置模板、聚焦测试和文档 |
| 禁止范围 | 自动批准/发布；发送 raw 数据；训练/微调；多 Provider 编排；P1/P2 修改 |
| 数据对象 | 沿用 ReuseAssetVersion；不新增正式资产状态 |
| API | generate 增加显式 `generation_mode=llm`；默认 deterministic |
| 前端 | 无；不提前放 Provider 选择 UI |
| 测试 | 默认关闭；schema/citation/PII；timeout/rate limit/invalid JSON；rollback；日志/响应无 Secret |
| 验收指标 | 失败产生正式资产数量 0；PII/Secret leakage 0；引用覆盖 100% |
| 停止条件 | deterministic 路径无回归；Provider 不可用时安全失败；仍只产出 generated/failed |
| 回滚点 | 关闭 Provider 配置并回退 adapter；M3 deterministic 保持可用 |
| 下一阶段入口 | M4 tag 推送，或 M4 延期决定记录后，人工授权 M5 |

### 9.5 Git 建议

- Commit：`[P3-M4] 功能：增加可选草稿生成提供方`
- Tag：`p3-m4-optional-llm-draft-provider`

## 10. P3-M5：人工编辑、审核和版本 Snapshot

### 10.1 核心目标

完成 generated/needs_revision 编辑、并发控制、提交冻结、人工审核和版本历史。M5 只建立 approved，不发布资料。

### 10.2 开发 Prompt 切分

1. **M5-A：generated/needs_revision 编辑与乐观锁**。
2. **M5-B：submit-review 内容冻结与来源重检**。
3. **M5-C：ReuseReview 决策和退修新版本**。
4. **M5-D：并发/事务/RBAC 测试和阶段收尾**。

### 10.3 阶段契约

| 项目 | 内容 |
|---|---|
| 输入 | M3/M4 generated 版本；固定来源集合 |
| 输出 | 冻结版本、ReuseReview、approved/needs_revision/rejected 历史 |
| 允许修改 | P3 asset version/review repository/service/routes；审核测试和文档 |
| 禁止范围 | 发布、归档、导出、前端、P1/P2 审核替代 |
| 数据对象 | `ReuseAssetVersion` 完整审核状态；`ReuseReview` |
| API | PATCH generated/needs_revision；submit-review；review decision；new-version；version list |
| 前端 | 无 |
| 测试 | lock conflict；内容冻结；source_stale；非法迁移；双审核；退修编辑重提；RBAC；rollback |
| 验收指标 | 未审核进入 approved 为 0；reviewed content hash coverage 100%；并发覆盖丢失为 0 |
| 停止条件 | approved 仍不可作为 published API 结果或导出；每个决定有只追加记录 |
| 回滚点 | 回退 review 模块/additive schema；保留 M3 generated 版本可读，禁止手工改状态 |
| 下一阶段入口 | M5 commit/tag/push 后人工授权 M6 |

### 10.4 Git 建议

- Commit：`[P3-M5] 功能：建立复用草稿审核与版本管理`
- Tag：`p3-m5-review-version-snapshot`

## 11. P3-M6：培训资料、SOP、话术和题库资产发布

### 11.1 核心目标

把 approved 资料类版本显式发布为 current P3 资产，并支持 supersede/archive。M6 不做数据集文件导出。

### 11.2 开发 Prompt 切分

1. **M6-A：publish/supersede 事务和 current published 查询**。
2. **M6-B：archive/source-stale 门禁和资料类 projection**。
3. **M6-C：并发发布、归档、P1/P2 回归和阶段收尾**。

### 11.3 阶段契约

| 项目 | 内容 |
|---|---|
| 输入 | approved 资料类 ReuseAssetVersion |
| 输出 | current published 资料资产、旧版本 superseded、显式 archived |
| 允许修改 | P3 publish/archive service/routes；资料 projection；聚焦测试和文档 |
| 禁止范围 | JSONL/CSV Artifact、模型训练、P4、前端、P1/P2 状态变化 |
| 数据对象 | `ReuseAssetVersion` published/superseded/archived |
| API | publish；archive；published detail；versions |
| 前端 | 无 |
| 测试 | approved != published；来源重检；双发布；supersede；archive；Trace；RBAC |
| 验收指标 | 单 asset_key current published <= 1；archived/old source leakage 0；Trace coverage 100% |
| 停止条件 | training/sop/service_script/qa_bank 四类均可发布；sft 导出尚不可用 |
| 回滚点 | 回退 publish 路由/事务；已产生 P3 测试数据只逻辑归档，不触碰来源 |
| 下一阶段入口 | M6 commit/tag/push 后人工授权 M7 |

### 11.4 Git 建议

- Commit：`[P3-M6] 功能：支持复用资料资产发布与归档`
- Tag：`p3-m6-reuse-asset-publication`

## 12. P3-M7：JSONL/CSV 指令数据集导出

### 12.1 核心目标

把 published/current `sft_dataset` 规范化、去重、校验并导出为可复现 JSONL/CSV Artifact 和 Manifest。M7 不执行训练。

### 12.2 开发 Prompt 切分

1. **M7-A：SFT sample schema、规范化和 fingerprint 去重**。
2. **M7-B：ExportJob/Artifact persistence 与存储 adapter**。
3. **M7-C：JSONL exporter + Manifest**。
4. **M7-D：CSV exporter 复用同一规范样本**。
5. **M7-E：download/revoke、故障注入、质量测试和阶段收尾**。

### 12.3 阶段契约

| 项目 | 内容 |
|---|---|
| 输入 | published/current/non-archived sft_dataset version |
| 输出 | JSONL/CSV data Artifact、Manifest、checksum、撤回记录 |
| 允许修改 | P3 export schema/service/repository/routes/storage；独立测试卷配置；文档 |
| 禁止范围 | 模型训练、外部训练平台上传、P1/P2 写入、普通资料伪装成 SFT、前端 |
| 数据对象 | `ExportJob`、`ExportArtifact` |
| API | create/get ExportJob；download/revoke Artifact |
| 前端 | 无 |
| 测试 | JSONL/CSV 编码和 schema；精确去重；PII；失败 rollback；并发幂等；字节复现；撤回 |
| 验收指标 | invalid JSONL 0；duplicate sample 0；instruction/output 完整 100%；PII/forbidden 0；source coverage 100% |
| 停止条件 | 同一固定输入 checksum 相同；失败无半文件/成功状态；下载只允许 available 且未 revoked Artifact |
| 回滚点 | 禁用 export route；逻辑撤回 Artifact；只清理 Job 明确拥有的测试文件 |
| 下一阶段入口 | M7 commit/tag/push 后人工授权 M8 |

### 12.4 Git 建议

- Commit：`[P3-M7] 功能：新增指令数据集规范导出`
- Tag：`p3-m7-dataset-export`

## 13. P3-M8：中文前端完整任务流

### 13.1 核心目标

把已冻结的 M1-M7 API 组织成全中文、按角色可理解的真实任务流。不得在 M8 修改后端业务契约以迁就前端。

### 13.2 开发 Prompt 切分

1. **M8-A：导航、项目列表和来源选择**，最多修改页面/API client 两个核心文件。
2. **M8-B：草稿编辑、引用面板和版本冲突**。
3. **M8-C：审核工作台和版本 diff**。
4. **M8-D：发布、归档和导出中心**。
5. **M8-E：角色 UX、响应式、frontend contract/build 和阶段收尾**。

每个 Prompt 必须保持页面可构建、已接入控件可真实执行；不留半连接按钮。

### 13.3 阶段契约

| 项目 | 内容 |
|---|---|
| 输入 | M1-M7 冻结 API 和权限矩阵 |
| 输出 | P3 中文项目、来源、草稿、审核、发布、导出工作流 |
| 允许修改 | P3 页面、共享 API/types、导航和必要样式；frontend tests/docs |
| 禁止范围 | 后端业务逻辑、P1/P2 页面重构、P4、虚假成功、浏览器持久化角色 |
| 数据对象 | 仅消费后端 DTO |
| API | 不新增；若契约缺口阻断则停止并回到单独后端修订阶段 |
| 前端 | `/p3-asset-reuse` 从 disabled shell 转为真实入口；主导航加入 P3 |
| 测试 | 角色按钮；中文 401/403；状态映射；mutation refresh；Source Trace；移动端；build；浏览器 smoke |
| 验收指标 | fake action 0；控制台错误 0；中文覆盖 100%；所有 enabled mutation 对应真实 API |
| 停止条件 | admin/cleaner/reviewer/viewer 流程清晰；service 无治理入口；P4 仍 disabled |
| 回滚点 | 回退 P3 页面/导航，恢复 disabled shell；后端 P3 不受影响 |
| 下一阶段入口 | M8 commit/tag/push 后人工授权 M9 |

### 13.4 Git 建议

- Commit：`[P3-M8] 前端：完成数据资产复用中文任务流`
- Tag：`p3-m8-chinese-reuse-workflow`

## 14. P3-M9：质量评测、Docker 验收与 Release Closure

### 14.1 核心目标

在独立测试环境中证明来源、生成、审核、发布、导出、安全和 P1/P2 回归门禁，形成仅限本地 Docker 的 release closure。

### 14.2 开发 Prompt 切分

1. **M9-A：质量 Eval fixture/runner**
   只添加合成挑战集、run-scoped manifest 和指标计算。
2. **M9-B：独立 PostgreSQL/Docker E2E**
   只补事务、并发、存储故障和端到端验收。
3. **M9-C：全量回归与安全审计**
   不新增功能，只修复独立确认的缺陷；修复需单独 Prompt/commit。
4. **M9-D：Release Closure 文档与 Git 收尾**
   只更新 README、08/09、阶段账本和 closure report。

### 14.3 阶段契约

| 项目 | 内容 |
|---|---|
| 输入 | M1-M8 已推送 tag；独立测试环境；合成挑战集 |
| 输出 | 指标报告、Docker 验收证据、Release Closure、本地 release tag |
| 允许修改 | eval/test/compose-test/closure docs；确认缺陷的最小修复另开 Prompt |
| 禁止范围 | 新产品能力、阈值迎合测试、真实业务数据、Render P3 上线声明、P4 |
| 数据对象 | test-run scoped P3 数据和 Artifact |
| API | 不新增 |
| 前端 | 不新增功能；只验证 production build/browser |
| 测试 | 第 15 节全门禁；全 backend；frontend build/contracts；P1 Harness；P2 Acceptance；Auth；Docker persistence |
| 验收指标 | 第 16 节硬指标全部通过；0 未解释失败；Secret leakage 0 |
| 停止条件 | 本地 Docker closure 文档、commit、push、annotated tag 完成；Render 状态真实记录 |
| 回滚点 | 部署上一阶段 tag；不删除数据库/Artifact 保留卷；关闭 P3 导航或 Provider 配置 |
| 下一阶段入口 | P3 维护或 P4 只能在新的人工指令下开始 |

### 14.4 Git 建议

- Commit：`[P3-M9] 发布：完成数据资产复用本地验收`
- Tag：`p3-m9-local-docker-release`
- Render P2/P3 持久化若未完成，closure 必须继续标为 BLOCKED。

## 15. 强制测试矩阵

| 编号 | 测试主题 | 最迟落地阶段 | 关键断言 |
|---:|---|---|---|
| 1 | Source eligibility | M1 | 合法源入选，原因码稳定 |
| 2 | archived/旧版本禁止 | M1/M9 | leakage 0 |
| 3 | 未审核禁止 | M1 | P1/P2/Bad Case 均阻断 |
| 4 | Source Trace | M1/M3 | 发布/样本 coverage 100% |
| 5 | 草稿/正式隔离 | M3 | generator 不能产 approved/published |
| 6 | 人工审核状态机 | M5 | 非法迁移 409，内容冻结 |
| 7 | 发布与归档 | M6 | approved != published，archive 禁导出 |
| 8 | 版本切换 | M5/M6 | vN+1 发布后 vN superseded |
| 9 | JSONL/CSV | M7 | 解析/编码/列/Manifest 100% 合法 |
| 10 | 重复样本 | M7 | Artifact 精确重复 0 |
| 11 | 敏感信息 | M3/M4/M7 | PII/Secret/forbidden 0 |
| 12 | 生成失败回滚 | M3/M4 | 无半状态、无正式记录 |
| 13 | 并发发布与幂等 | M2/M5/M6/M7 | 单一资源、重放一致 |
| 14 | Auth/RBAC | 每阶段 | 五角色矩阵与 401/403 |
| 15 | Docker 隔离 | M9 | 开发卷/计数不变 |
| 16 | P1/P2 回归保护 | 每阶段收尾/M9 | 冻结契约和默认行为不变 |

## 16. P3-M9 质量门禁

### 16.1 数据资格硬门禁

- invalid source rate = 0
- archived source leakage = 0
- old-version leakage = 0
- source trace coverage = 100%
- duplicate source rate = 0

### 16.2 生成质量

- M1～M8 不冻结经验数值阈值，执行“无法由来源证明即阻断”的结构性事实门禁
- M9 使用独立挑战集先测量 factual consistency，再冻结 release 数值阈值；不得对挑战集逐条调参
- required field completeness = 100%
- citation coverage = 100%
- reviewer approval rate 和 revision rate 必须按 template/provider 输出真实值，不设置鼓励放松审核的通过阈值

### 16.3 数据集质量硬门禁

- final duplicate sample rate = 0
- invalid JSONL rate = 0
- instruction/answer completeness = 100%
- forbidden content rate = 0
- PII leakage rate = 0
- source coverage = 100%

### 16.4 工程质量硬门禁

- 全部测试失败数 = 0；skip 有清晰理由
- transaction rollback 故障场景通过率 = 100%
- idempotency 重放场景通过率 = 100%
- 相同固定输入的 export checksum 一致率 = 100%
- cleanup 误删开发/业务数据 = 0
- Git、日志、响应、Artifact、Manifest Secret leakage = 0
- P1 Harness 保持 10/10
- P2 Acceptance 保持 Ready/Serve/Archive/old-version 门禁
- CustomerOpsAgent 默认 P1-only
- Unified 继续显式 opt-in

## 17. 每阶段 Git 与停止纪律

| 阶段 | Commit Message 建议 | Tag |
|---|---|---|
| M0 | `[P3-M0] docs: freeze data asset reuse plan` | `p3-m0-planning-freeze` |
| M1 | `[P3-M1] 功能：新增复用来源资格判定与只读查询` | `p3-m1-source-eligibility` |
| M2 | `[P3-M2] 功能：建立复用项目与来源快照` | `p3-m2-reuse-project-source-selection` |
| M3 | `[P3-M3] 功能：新增模板化确定性草稿生成` | `p3-m3-deterministic-draft-generation` |
| M4 | `[P3-M4] 功能：增加可选草稿生成提供方` | `p3-m4-optional-llm-draft-provider` |
| M5 | `[P3-M5] 功能：建立复用草稿审核与版本管理` | `p3-m5-review-version-snapshot` |
| M6 | `[P3-M6] 功能：支持复用资料资产发布与归档` | `p3-m6-reuse-asset-publication` |
| M7 | `[P3-M7] 功能：新增指令数据集规范导出` | `p3-m7-dataset-export` |
| M8 | `[P3-M8] 前端：完成数据资产复用中文任务流` | `p3-m8-chinese-reuse-workflow` |
| M9 | `[P3-M9] 发布：完成数据资产复用本地验收` | `p3-m9-local-docker-release` |

阶段标准收尾顺序：

1. 聚焦测试。
2. 相关 P1/P2 回归。
3. diff/security/Secret audit。
4. 更新本阶段报告和 08/09。
5. 精确 staging。
6. 中文 commit。
7. 正常 push。
8. annotated tag 并 push tag。
9. 汇报结果并停止，等待下一阶段指令。

P3-M0.1 完成 docs/71～74 和状态记录后执行精确暂存、commit/tag/push，随后停止。

## 18. 主要风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| P1 approved 内容后续漂移 | 未复审内容进入 P3 | approved Review snapshot 指纹一致性 |
| P2 serving 与 published 混淆 | 错误拒绝合法源或扩大资格 | 资格按 active/current/approved，serving 仅观察 |
| Bad Case resolved 被当作 approved | 未审核修正泄漏 | 必须引用 approved Candidate |
| LLM 改写事实 | 培训/数据集错误 | 默认 deterministic、来源约束、引用和人工复审 |
| Source Trace 过大或含隐私 | 导出泄漏 | 最小 Trace、内外部 projection 分离 |
| 多状态塞入一个大表 | 高耦合和竞态 | 推荐六对象/七表、状态归属明确 |
| 双发布/双导出 | 多 current 版本或重复文件 | 锁、唯一约束、Idempotency-Key |
| 源归档后历史文件继续传播 | 合规风险 | 阻断新发布/新导出、保留 Manifest、由 admin 逻辑 revoke；明确外部副本限制 |
| Artifact 清理误伤 | 数据丢失 | Job/run 精确前缀和独立卷 |
| 前端假状态 | 用户误判已发布 | 后端状态为唯一真相，mutation 后刷新 |
| P3 牵动 P1/P2 | 冻结基线回归 | 新模块、只读 adapter、阶段回归门禁 |
| Render 持久化未就绪 | 错误线上声明 | 本地 Docker 为权威，Render 保持 BLOCKED |

## 19. 冻结决策与阶段性 Deferred

| 决策 | 冻结结论 | 后续处理 |
|---|---|---|
| 质量阈值 | M1～M8 结构门禁，M9 校准 release 数值 | M9 独立挑战集 |
| Migration | 沿用 additive `create_all(checkfirst)`，应用回退保留表 | M2 实施；migration 工具升级需另立 ADR |
| 角色 | v1 复用五角色，admin 发布/导出/revoke | 稳定个人身份和独立角色生产化 Deferred |
| LLM | M3 不依赖；M4 可选且只生成草稿 | Provider/模型/数据出境在 M4 入口明确 |
| Artifact | 无自动 TTL/物理删除，admin 逻辑 revoke | 外部存储和企业保留期 Deferred |
| 来源失效 | 标记 source_stale，阻断新批准/发布/导出 | 历史 Artifact 不自动 revoke |
| 链式复用 | P3 v1 禁止 | 不设开放阶段 |
| 独立索引 | P3 v1 不建立 | 只有经测量需求后另行规划 |

## 20. P3-M0.1 停止条件

本轮在以下事实成立后立即停止：

- docs/71～74 已冻结并记录状态。
- README、docs/08、docs/09 只追加 P3-M0.1 状态，不改 P1/P2 历史结论。
- 没有业务代码、数据库、API 或前端修改。
- 没有运行测试或 Docker。
- 精确暂存、commit、push 和 `p3-m0-planning-freeze` annotated tag push 完成。
- working tree clean。
- P3-M1 尚未开始，等待独立人工指令。
