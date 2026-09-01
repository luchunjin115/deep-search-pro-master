# M2：知识库垂直切片

> 本文件是 M2 的唯一必读入口，只保存当前状态、关键决策、步骤索引、风险和下一动作。
> 完整方案、实施日志和验证证据保存在 [`records/`](records/) 中，开始具体任务时按需读取。
> 最近更新：2026-09-01

## 1. 当前状态

| 项目 | 当前内容 |
|---|---|
| 阶段状态 | 进行中 |
| 已完成 | M2-01 至 M2-18 |
| 当前停止点 | M2-18 已完成并收口 |
| 下一动作 | 等待用户确认进入 M2-19 方案讨论 |
| 尚未开始 | `search_knowledge` Tool、知识问答 HTTP API、知识 Agent/LangGraph、Qwen 基于证据回答、前端知识问答 |
| 技术阻塞 | 无硬阻塞；存在性能和上游质量边界，见第 7 节 |

用户尚未确认 M2-19 方案，因此不得自动开始 M2-19 代码。确认 M2-19 也不自动授权后续步骤。

## 2. 新窗口阅读顺序

新 Agent 不需要全文读取全部 M2 历史，按下面顺序读取：

1. 必读 `docs/PROJECT_PROGRESS.md`，确认全项目当前阶段和跨阶段问题；
2. 必读本文件，确认 M2 当前停止点、有效决策和下一动作；
3. 开始具体步骤前，只读取第 3 节中与该步骤直接相关的过程记录；
4. 只有排查历史回归、设计冲突或验证依据时，才读取其他过程记录；
5. 代码事实与记录冲突时，以当前代码、迁移和实际验证为准，并同步修正文档。

例如讨论 M2-19 时，优先读取本文件、`M2_18_CONTEXT_EVIDENCE.md`，再按 Tool 与 Harness 的真实代码调用链做只读检查；无需默认读取 M2-01 至 M2-17 全部日志。

## 3. M2 过程记录目录

| 范围 | 内容 | 何时读取 |
|---|---|---|
| [M2_DOCUMENT_GOVERNANCE.md](records/M2_DOCUMENT_GOVERNANCE.md) | M2文档拆分方案、修改范围、完整性验证和维护规则 | 排查进度文档结构或链接时 |
| [M2_00_STAGE_PLAN.md](records/M2_00_STAGE_PLAN.md) | M2 原始阶段方案、目标、总体链路、24步计划、完成标准和初始风险 | 核对阶段原始边界或总体设计时 |
| [M2_01_06_FOUNDATION.md](records/M2_01_06_FOUNDATION.md) | 配置、pgvector、Storage、文件/文档模型、Schema、Repository、状态 Service 和文件 API | 修改上传、Storage、文件权限或文档状态时 |
| [M2_07_11_DOCUMENT_PARSING.md](records/M2_07_11_DOCUMENT_PARSING.md) | PDF/DOCX/XLSX/CSV Native Parser、合成语料、Docling 双路径、Canonical Artifact 和解析发布 | 修改解析器、路由、OCR、解析产物或文件安全时 |
| [M2_12_CHUNKING.md](records/M2_12_CHUNKING.md) | 结构感知分块、Token Counter、表格切块、Chunk Set 和 Artifact 发布 | 修改分块、表格结构或 Chunk Artifact 时 |
| [M2_13_15_INDEXING.md](records/M2_13_15_INDEXING.md) | `document_chunks`、FTS/vector、BGE-M3、Index Set、幂等索引和同步索引 API | 修改Embedding、索引代次、Chunk入库或索引事务时 |
| [M2_16_RETRIEVAL.md](records/M2_16_RETRIEVAL.md) | 权限前置候选、Dense、Lexical、Hybrid、RRF、质量与延迟验收 | 修改召回、ACL过滤、排序或检索参数时 |
| [M2_17_RERANKER.md](records/M2_17_RERANKER.md) | Reranker合同、Fake、BGE Provider、Service、质量和资源基准 | 修改精排模型、候选裁剪或精排策略时 |
| [M2_18_CONTEXT_EVIDENCE.md](records/M2_18_CONTEXT_EVIDENCE.md) | Context合同、持久化、安全重取、Builder、Evidence和引用验证 | 讨论或实现 M2-19 Tool，以及修改引用链时 |

这些文件是正式阶段记录，不是可删除的临时归档。入口只做导航和当前状态摘要，完整完成证据仍以对应过程记录为准。

## 4. M2 目标与边界

M2 要证明的垂直链路是：用户上传一份明确标注为合成演示数据的知识文件，系统安全保存、解析、分块和索引；用户提问时，系统在当前租户和文档权限范围内检索、重排、构造上下文、保存 Evidence，并验证回答引用。

M2 继续复用 M1 的登录、`CurrentUser`、事务、Harness、Trace、聊天和数据库 Evidence 基础，不重新实现另一套认证或运行框架。

当前明确不做：

- 不使用 RAGFlow；
- 不引入 MCP；
- 不接真实 Amazon SP-API、ERP 或生产对象存储；
- V1 文件仍使用本地文件系统和 `Storage` 抽象，不部署 MinIO；
- 不允许模型直接访问数据库或绕过 Tool/Harness 权限；
- 不把扫描件、复杂供应商文件、百万 Chunk、高并发或灾难恢复描述为已解决；
- 在 M2-19 方案确认前，不注册 Tool 或扩展 Agent。

## 5. 当前已实现调用链

```text
用户与 CurrentUser
→ 文件 API / Schema
→ 文件与文档 Service
→ LocalStorage + PostgreSQL
→ Parser Router（Native / Docling / Hybrid）
→ Canonical Parsed Artifact
→ 结构感知 Chunk Artifact
→ BGE-M3 Embedding + FTS + pgvector
→ active ready Index Set
→ 权限前置 Dense / Lexical
→ Hybrid + RRF
→ BGE-Reranker
→ Context Builder
→ ContextArtifact + Document Evidence
→ Citation Validator
```

尚未接通的后半段：

```text
Citation Validator 之前的既有能力
→ search_knowledge Tool（M2-19，未开始）
→ 知识路由与 LangGraph（M2-21，未开始）
→ Qwen 基于 Evidence 的回答（未开始）
→ HTTP 聊天链和前端引用展示（未开始）
```

## 6. 步骤状态索引

| 步骤 | 状态 | 结果摘要 | 详细记录 |
|---|---|---|---|
| M2-01 | 已完成 | 配置、依赖和新旧导入边界 | [基础记录](records/M2_01_06_FOUNDATION.md) |
| M2-02 | 已完成 | PostgreSQL 17 + pgvector 基础设施 | [基础记录](records/M2_01_06_FOUNDATION.md) |
| M2-03 | 已完成 | `Storage` 接口与 `LocalStorage` | [基础记录](records/M2_01_06_FOUNDATION.md) |
| M2-04 | 已完成 | File、Document、Version、ACL 模型与迁移 | [基础记录](records/M2_01_06_FOUNDATION.md) |
| M2-05 | 已完成 | 文件/文档 Schema、Repository 和状态 Service | [基础记录](records/M2_01_06_FOUNDATION.md) |
| M2-06 | 已完成 | 上传、列表、状态、下载和软删除 API | [基础记录](records/M2_01_06_FOUNDATION.md) |
| M2-07 | 已完成 | 文本型 PDF Native Parser | [解析记录](records/M2_07_11_DOCUMENT_PARSING.md) |
| M2-08 | 已完成 | DOCX Native Parser | [解析记录](records/M2_07_11_DOCUMENT_PARSING.md) |
| M2-09 | 已完成 | XLSX/CSV Native Parser | [解析记录](records/M2_07_11_DOCUMENT_PARSING.md) |
| M2-10 | 已完成 | `m2-v1` 合成知识文件和 manifest | [解析记录](records/M2_07_11_DOCUMENT_PARSING.md) |
| M2-11 | 已完成 | Docling 双路径、Canonical Artifact、解析调度和版本化发布 | [解析记录](records/M2_07_11_DOCUMENT_PARSING.md) |
| M2-12 | 已完成 | 结构感知分块、Chunk Set 和版本化 Chunk Artifact | [分块记录](records/M2_12_CHUNKING.md) |
| M2-13 | 已完成 | `document_chunks`、PostgreSQL FTS 和 `vector(1024)` | [索引记录](records/M2_13_15_INDEXING.md) |
| M2-14 | 已完成 | BGE-M3 Provider、固定快照、真实 Smoke 和资源基准 | [索引记录](records/M2_13_15_INDEXING.md) |
| M2-15 | 已完成 | 幂等索引、失败重试、Index Set 和版本原子激活 | [索引记录](records/M2_13_15_INDEXING.md) |
| M2-16 | 已完成 | 权限前置 Dense/Lexical/Hybrid/RRF 检索闭环 | [检索记录](records/M2_16_RETRIEVAL.md) |
| M2-17 | 已完成 | BGE-Reranker Provider、Service 和质量验收 | [重排记录](records/M2_17_RERANKER.md) |
| M2-18 | 已完成 | Context、Evidence、原子持久化与严格引用验证 | [Context记录](records/M2_18_CONTEXT_EVIDENCE.md) |
| M2-19 | 待确认 | 设计并注册 `search_knowledge` Tool | 尚未创建方案记录 |
| M2-20 | 待开始 | `read_uploaded_file` 与 `get_evidence_detail` Tool | [原始计划](records/M2_00_STAGE_PLAN.md) |
| M2-21 | 待开始 | 有界知识路由、LangGraph 和基于 Evidence 的回答 | [原始计划](records/M2_00_STAGE_PLAN.md) |
| M2-22 | 待开始 | 最小 RAG 评估集和 Runner | [原始计划](records/M2_00_STAGE_PLAN.md) |
| M2-23 | 待开始 | 最小前端上传、知识问答和引用展示 | [原始计划](records/M2_00_STAGE_PLAN.md) |
| M2-24 | 待开始 | 故障矩阵、真实演示、Chromium 回归和阶段收口 | [原始计划](records/M2_00_STAGE_PLAN.md) |

## 7. 仍然有效的关键决策与风险

### 7.1 关键决策

- PostgreSQL 保存业务元数据、状态、ACL、Chunk、向量、Context 和 Evidence；本地 Storage 保存上传文件及解析/分块 Artifact；
- Native Parser 负责普通文件快速路径；Docling 只处理经过安全检查的复杂文件；Office 结构事实继续以 Native 结果为底稿；
- Native 与 Docling 汇合到项目自有、版本化的 Canonical Parsed Artifact，Markdown 不是唯一事实底稿；
- Chunk 和 Index Set 使用确定性身份；新版本或新索引只有完整 ready 后才能原子切换 active；
- Dense 与 Lexical 共用同一套当前用户、tenant、ACL、软删除和 active 代次候选边界；权限过滤发生在排序前；
- Hybrid 使用固定 RRF 融合，当前不增加自动检索模式路由；
- Reranker 只能重排已经获权的 Hybrid 候选，不能扩大召回或绕过 ACL；
- Context Builder 不信任 Reranker 返回的正文，必须重新获权并从数据库取得同代次锚点和邻居；
- Context/Evidence 使用确定性身份和事务内原子幂等保存；引用验证必须重新检查当前用户、ACL、软删除和 active 代次；
- 所有日常回归默认使用 Fake；真实 BGE/Docling/Qwen 只通过显式 Smoke 或质量验收运行。

### 7.2 当前风险与边界

| 风险或边界 | 当前事实 | 优先排查方向 |
|---|---|---|
| Reranker CPU 延迟 | 约 15 个候选的本机 p50/p95 约 6.70/7.24 秒 | 候选裁剪、GPU、批处理或有证据支持的路由策略 |
| 图文 DOCX | 图片文字事实级定位仍只有 2/20 | Docling/Office视觉文字融合和Canonical定位 |
| 事实级 Locator | 当前正式复杂语料约 16/20 | Parser Adapter、表格/图片定位和Golden边界 |
| 既有跨月测试 | 默认全量唯一失败来自上传 Key 写死 `2026/08` | 修复测试时间依赖，不放宽生产Storage规则 |
| 数据库夹具顺序耦合 | 人工改变部分固定UUID测试顺序可触发污染 | 强化测试隔离和唯一数据身份 |
| 规模与并发 | 当前只证明小型合成语料闭环 | M5再做负载、并发和更大规模评估 |

## 8. 最近验证基线

M2-18.6 收口时的实际结果：

- 引用验证单元和真实 PostgreSQL 聚焦：`18 passed`；
- Context/Evidence 相邻回归：`69 passed`；
- 排除显式真实模型 Smoke 和既有跨月用例后：`773 passed, 2 skipped, 1 deselected`；
- 原样默认全量：`773 passed, 10 skipped, 1 failed`，唯一失败是既有跨月测试；
- Ruff、240 文件格式检查、114 个 `app` 模块 Mypy、编译、依赖和 Alembic 门禁通过；
- Alembic 为 `20260901_0009 (head)` 且无漂移；
- 正式 Seed 已恢复为 10 files / 10 documents / 10 versions / 9 ACL，索引、Context 和 Evidence 均为 0；
- Storage 只有 10 个 uploads，M1 德国仓可售库存仍为 125。

这些结果能证明 M2-01 至 M2-18 的确定性测试、当前 PostgreSQL 集成和既有 M1 基线在记录时可重复；不能证明生产规模、长期模型稳定性、真实供应商复杂文档覆盖率、低延迟 Reranker 或尚未实现的 Tool/Agent/前端链路。

## 9. 下一步和记录规则

下一步只能先提交 M2-19 实施方案，至少说明现状、目标、不做内容、输入输出、Tool 权限、Harness关系、修改文件、调用链、验证、完成标准和风险。用户明确确认后，才开始 M2-19 的第一个小步骤。

后续记录方式：

- 本入口只更新当前状态、步骤索引、有效关键决策、风险和下一动作；
- 详细方案、修改文件、TDD过程、验证数字、能证明/不能证明和排查记录写入对应 `records/` 文件；
- 同一能力继续追加到已有记录；进入新的能力步骤时再创建新记录文件；
- 不把逐次测试流水账重复粘贴到 `docs/PROJECT_PROGRESS.md`；总看板只保留里程碑摘要和链接；
- 未验证的工作不得标记为已完成，代码变化导致旧验证失效时必须在对应记录中注明。
