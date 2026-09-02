# M2：知识库垂直切片

> 本文件是 M2 的唯一必读入口，只保存当前状态、关键决策、步骤索引、风险和下一动作。
> 完整方案、实施日志和验证证据保存在 [`records/`](records/) 中，开始具体任务时按需读取。
> 最近更新：2026-09-02

## 1. 当前状态

| 项目 | 当前内容 |
|---|---|
| 阶段状态 | 进行中 |
| 已完成 | M2-01 至 M2-20；文件与Evidence受控读取两条Tool链已完成整链矩阵并收口 |
| 当前停止点 | M2-20整体已完成；M2-21需求讨论与待确认实施方案已记录，最终正式方案尚未确认 |
| 下一动作 | 复核M2-21待确认实施方案的十项关键取舍；最终确认前不编码，确认后也只开始M2-21.1 |
| 尚未开始 | M2-21至M2-24、知识问答 HTTP API、知识 Agent/LangGraph、Qwen 基于证据回答、前端知识问答 |
| 技术阻塞 | 无硬阻塞；存在性能和上游质量边界，见第 7 节 |

M2-20.1至M2-20.6已经全部完成并验证。M2-21已有需求讨论和待确认实施方案，但尚未得到最终确认，不得自动开始代码开发。

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
| [M2_19_SEARCH_KNOWLEDGE_TOOL.md](records/M2_19_SEARCH_KNOWLEDGE_TOOL.md) | `search_knowledge` Tool完整方案、合同、审计关联、五步实施顺序、验证矩阵和风险 | 确认或实施M2-19时 |
| [M2_20_FILE_EVIDENCE_TOOLS.md](records/M2_20_FILE_EVIDENCE_TOOLS.md) | `read_uploaded_file/get_evidence_detail`完整方案、用户确认、严格合同、实施日志和验证矩阵 | 确认或实施M2-20时 |
| [M2_21_ENGINEERED_AGENT.md](records/M2_21_ENGINEERED_AGENT.md) | 工程化Agent需求讨论、方向性共识、候选运行模型、未决问题和非正式步骤草案 | 继续讨论或形成M2-21最终正式方案时 |
| [M2_21_ENGINEERED_AGENT_IMPLEMENTATION_PLAN.md](records/M2_21_ENGINEERED_AGENT_IMPLEMENTATION_PLAN.md) | 基于当前方向形成的待确认实施方案、十步顺序、文件、验证、完成标准和风险 | 复核、修改或最终确认M2-21实施方案时 |

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
- M2-21及后续步骤未经用户完成方案确认，不新增执行Tool或扩展Agent。

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
→ KnowledgeSearchService固定应用编排
→ M2 Tool Registry + Harness权限/预算/Trace
→ SearchKnowledgeTool可信身份绑定
→ 权限前置 Dense / Lexical
→ Hybrid + RRF
→ BGE-Reranker
→ Context Builder
→ ContextArtifact + Document Evidence + ToolContextLink审计关联
→ Citation Validator
```

M2-20.3已把安全文件读取接入正式Tool执行链：

```text
ReadUploadedFileInput + CurrentUser
→ M2 Registry → Harness权限/预算/超时/Trace
→ ReadUploadedFileTool可信身份与file ID验真
→ FileReadingService
→ 一次性File/Version/Document获权查询 → PostgreSQL
→ 私有parsed_storage_key → LocalStorage
→ RoutedParseResult重新校验 → selected Canonical Artifact
→ 四格式locator选择与8000字符裁剪
→ ReadUploadedFileResult → ToolEnvelope（空evidence_ids）
```

M2-20.5已把统一Evidence详情接入正式Tool执行链：

```text
GetEvidenceDetailInput + CurrentUser
→ M2 Registry → Harness权限/预算/超时/Trace
→ GetEvidenceDetailTool可信身份与Evidence ID验真
→ EvidenceQueryService → EvidenceRepository → PostgreSQL
→ GetEvidenceDetailResult → ToolEnvelope（单个已验证evidence_id）
```

M2-20以后尚未接通的后半段：

```text
知识路由与 LangGraph（M2-21，未开始）
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
| M2-19 | 已完成 | 严格合同、隔离Registry、审计关联、应用Service、正式Tool/Harness及权限/故障矩阵完成 | [M2-19记录](records/M2_19_SEARCH_KNOWLEDGE_TOOL.md) |
| M2-20 | 已完成 | 两个受控读取Tool的合同、Service、Harness接入及真实权限/范围/故障矩阵完成 | [M2-20记录](records/M2_20_FILE_EVIDENCE_TOOLS.md) |
| M2-21 | 待开始 | 工程化Agent需求讨论与待确认实施方案已记录；尚未授权开发 | [待确认方案](records/M2_21_ENGINEERED_AGENT_IMPLEMENTATION_PLAN.md) / [讨论草案](records/M2_21_ENGINEERED_AGENT.md) / [原始计划](records/M2_00_STAGE_PLAN.md) |
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
- Document Evidence保持可复用且不永久占有ToolCall；`tool_context_links`保证一ToolCall最多一个Context、同一Context可被多ToolCall审计复用，M1 database Evidence继续直接绑定ToolCall；
- `KnowledgeSearchService`固定执行Reranker（内部Hybrid）→ Context Builder → Evidence持久化，并在返回前逐项核对Context/Evidence；不拥有模型参数、预算、ACL或事务提交；
- 所有日常回归默认使用 Fake；真实 BGE/Docling/Qwen 只通过显式 Smoke 或质量验收运行。
- `search_knowledge`输入只允许1至2000字符query，输出只包装公开`ContextBundle`；ToolEnvelope最多12个Evidence；
- M1 Registry继续精确两个Tool，M2隔离Registry累计五个Tool；新增读取Tool元数据不会自动进入现有库存Agent或Provider投影。
- `SearchKnowledgeTool`通过Harness执行并逐项核对RunContext与绑定CurrentUser；ToolCall读取使用`FOR KEY SHARE`避免与Harness状态回写互锁，同时继续由复合外键和唯一约束验真。
- `read_uploaded_file`输入只允许公开file ID与可选四格式有界locator；PDF最多3页、表格最多50行/1000单元格、输出最多8000字符，调用者不能传路径、Storage Key、身份、SQL或读取预算。
- 文件读取Service只接受可信`CurrentUser`与严格输入；Repository在同一SQL中限制tenant、File/Document软删除及owner/ACL，Service只读`parse_status=ready`版本，私有Key必须匹配tenant/`parsed`/version，Routed Artifact、格式及File/Version双重源Hash必须一致；具体获权版本可非active但结果必须如实标记。
- `ReadUploadedFileTool`精确绑定M2 Registry，通过Harness执行并核对绑定`CurrentUser`与运行上下文的用户、tenant、角色和市场；Service结果类型与公开file ID必须和请求一致，成功Envelope不创建或伪造Evidence。
- M1 `EvidenceQueryService.get_detail`继续只服务数据库Evidence与既有HTTP合同；M2统一`get_tool_detail`可返回数据库或文档详情，文档分支必须重新核对Context请求者、当前ACL/软删除/active代次和完整Chunk来源，失败统一隐藏为`EVIDENCE_NOT_FOUND`。
- `get_evidence_detail`输入只允许Evidence ID，统一输出M1数据库或M2文档Evidence安全详情；正式Tool精确绑定可信身份并经过Harness，Service结果ID必须与请求一致，成功Envelope只携带该Evidence ID。

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

M2-20.6 收口时的实际结果：

- M2-20聚焦合同、Service、Tool与真实矩阵：`93 passed`；M1/M2相邻回归：`233 passed`；
- 排除既有跨月用例后：`949 passed, 2 skipped, 1 deselected`；
- 原样默认全量：`949 passed, 10 skipped, 1 failed`，唯一失败仍是既有跨月测试；
- Ruff、253文件格式、120个`app`源文件Mypy、编译、依赖和Alembic门禁通过；
- Alembic继续为`20260902_0010 (head)`且无漂移，本步没有新增迁移；
- 正式Seed已恢复为10 files / 10 documents / 10 versions / 9 ACL，索引、Context、Evidence、ToolContextLink、AgentRun和ToolCall均为0；
- Storage只有10个uploads，M1德国仓可售库存仍为125。

这些结果能证明两个读取Tool在三业务角色、owner/company owner/user/role/market ACL下通过同一真实Harness落到真实Service/Repository，撤权、软删除、旧active来源、解析/locator、Storage/Artifact和数据库故障均被安全处理并记录Trace；不能证明M2-21三跳Agent策略、真实Qwen/BGE延迟、HTTP知识API或前端。

## 9. 下一步和记录规则

M2-20已经完成、验证并收口。M2-21工程化Agent需求讨论与待确认实施方案已经建立，但不是最终正式方案。下一步应复核方案中的M1复用粒度、顺序执行、PostgreSQL Checkpoint、回答Evidence Set、直接回答边界、独立预算、聊天API、Capability Resolver和十步拆分；只有最终方案明确确认后才能开始M2-21.1，不得自动修改现有Agent/API或进入M2-21.2及后续步骤。

后续记录方式：

- 本入口只更新当前状态、步骤索引、有效关键决策、风险和下一动作；
- 详细方案、修改文件、TDD过程、验证数字、能证明/不能证明和排查记录写入对应 `records/` 文件；
- 同一能力继续追加到已有记录；进入新的能力步骤时再创建新记录文件；
- 不把逐次测试流水账重复粘贴到 `docs/PROJECT_PROGRESS.md`；总看板只保留里程碑摘要和链接；
- 未验证的工作不得标记为已完成，代码变化导致旧验证失效时必须在对应记录中注明。
