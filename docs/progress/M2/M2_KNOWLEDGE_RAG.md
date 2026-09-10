# M2：知识库垂直切片

> 本文件是 M2 的唯一必读入口，只保存当前状态、关键决策、步骤索引、风险和下一动作。
> 完整方案、实施日志和验证证据保存在 [`records/`](records/) 中，开始具体任务时按需读取。
> 最近更新：2026-09-10

## 1. 当前状态

| 项目 | 当前内容 |
|---|---|
| 阶段状态 | 进行中 |
| 已完成 | M2-01 至 M2-21；M2-22.1至M2-22.6已完成。M2-22.6包含Locator降级、10组Chunk/50点确定性检索矩阵，以及只对筛出配置补跑的Ragas检索语义评分、失败分类、清理与回归 |
| 当前停止点 | M2-22.6已收口。用户已要求进入M2-22.7，但先同步文档并查看步骤；M2-22.7五步详细方案已写入过程记录，运行代码与真实评估尚未开始 |
| 下一动作 | 等待用户确认M2-22.7详细方案；确认后只实施M2-22.7.1评估配置、结果合同与确定性指标，并在验证、记录后停止 |
| 已确认后续顺序 | M2-22.5至.8完成RAG分层评估与用户复核后，先插入M2-22.8R意图识别与执行分流改造，再实施M2-22.9最终多Agent轨迹评估，然后才进入M2-23前端与M2-24收口 |
| 尚未开始 | M2-22.7运行代码与真实评估、M2-22.8、M2-22.8R、M2-22.9至M2-24、前端知识问答和M2阶段最终评估/演示收口 |
| 技术阻塞 | M2-22.7无已知本地阻塞；外部Judge欠费使M2-22.6的7条后段真实题语义指标不完整，但M2-22.7只使用固定本地BGE-Reranker和项目确定性Context指标，不依赖Qwen。Noise Sensitivity继续留到允许生成回答的M2-22.8 |

M2-20.1至M2-20.6已经全部完成并验证。M2-21十二步于2026-09-07全部完成：在共同合同、能力目录、Provider/Mock、五节点Supervisor、通用Worker Runtime、两个真实Worker、严格Qwen、统一引用、PostgreSQL持久化、唯一公开Gateway和跨请求恢复之上，独立只读且属于不同Worker的任务现在最多2路并发；真实公开G4验证了两个子Run重叠、独立预算/Session/Trace/ToolCall归属和稳定合并，G0～G7均已映射到可执行测试。M2-22.1至M2-22.6已经完成；M2-22.6的Ragas补跑只使用筛出的单一配置，部分Judge失败按真实状态保留，未进入Reranker或任何后续层。

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
| [M2_21_ENGINEERED_MULTI_AGENT_PLAN.md](records/M2_21_ENGINEERED_MULTI_AGENT_PLAN.md) | M2-21唯一记录；包含已确认方案、十二步顺序、角色/能力/Handoff/记忆/跨阶段边界及逐步实施日志；当前状态以文件顶部和最新步骤记录为准 | 开始任一M2-21.x前必读，并在每步完成后继续追加记录 |
| [M2_22_CROSS_BORDER_RAG_EVALUATION_PLAN.md](records/M2_22_CROSS_BORDER_RAG_EVALUATION_PLAN.md) | M2-22已修订方案；包含跨境电商语料、磁盘门禁、完整结构感知切块配置、确定性检索指标、Ragas检索/生成语义指标、人工复核、RAG后意图分流改造与最终多Agent轨迹评估门禁 | 实施任一M2-22.x前必读 |
| [M2_ARCHITECTURE_LEARNING_MAPS.md](records/M2_ARCHITECTURE_LEARNING_MAPS.md) | 当前项目框架总览图的范围、调用链、交付文件、验证证据和阅读边界 | 用图理解当前框架，或后续更新架构/流转图时 |

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
- M2-21复核方案虽已确认，但当前小步骤未经单独开发授权时，不新增执行Tool或扩展Agent。

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

M2-21.5当时先接通、且尚未进入公开API或真实业务Worker的运行外壳是：

```text
HandoffDraft
→ 精确Worker Dispatcher + 重复/无进展终止
→ 根/子AgentBudgetTree
→ 程序生成AgentHandoff和WorkerRun父子关联
→ 可信RunContext + 独立Session/savepoint + 现有Harness适配
→ 测试Worker Result → 实测资源/提交回滚 → 内存子Trace
```

M2-21.6 已在内部接通第一条真实 Business L1 纵向链：

```text
Supervisor + 确定性测试Provider
→ WorkerRuntime生成可信AgentHandoff、子预算和独立Session
→ BusinessDataWorker有界Action/Observation
→ CapabilityResolver精确限定get_product_spec / search_inventory
→ Harness权限/预算/Trace
→ M1 Tool → Service → Repository → PostgreSQL
→ ToolCall + 库存数据库Evidence
→ WorkerResult → Supervisor终态
```

M2-21.7 已把第二个真实 Worker 和顺序 L2 接到同一内部骨架：

```text
Supervisor按Task DAG先后准备HandoffDraft
→ WorkerRuntime/测试事务接缝注入可信Handoff、子预算、RunContext和Harness
→ BusinessDataWorker → M1 Tool → PostgreSQL数据库Evidence
→ KnowledgeWorker → M2知识Tool → PostgreSQL/pgvector/Storage → 文档Evidence或文件Artifact
→ 两个WorkerResult按任务顺序稳定合并
→ 全部成功为completed + answered
→ allows_partial的Knowledge失败时保留Business结果并收口为completed + partial
```

M2-21.8 已接通内部严格 Qwen 与统一证据回答边界：

```text
Supervisor / Worker安全Request
→ QwenAgentProvider HTTPS严格JSON Schema（搜索关闭、确定性参数）
→ TaskPlan / 单一Action / HandoffDraft / Answer本地Citation标签
→ Pydantic + Resolver归属 + Capability参数Schema服务端复验
→ 已有Worker Runtime / Harness / Tool执行链（仅执行Action时）
→ Observation支持的Answer Evidence Set [E1]…[E12]
→ Provider Citation Validator + Graph终态Citation Validator
→ 内部EngineeredAgentState终态
```

M2-21.9 建立了持久化边界：

```text
可信CurrentUser + Thread + 严格TaskPlan/WorkerResult/EngineeredAgentState
→ AgentRuntimePersistenceService身份、版本、状态与哈希校验
→ AgentRuntimeRepository固定tenant范围读写
→ PostgreSQL父子AgentRun + agent_tasks/dependencies共享任务板
→ 不可变agent_checkpoints + agent_answer_evidences
→ 复合外键、Check、唯一索引与DAG循环Trigger
```

M2-21.10 已把公开入口、真实运行和持久化接成主路径：

```text
消息POST + CurrentUser/Thread授权
→ 唯一AgentGateway（无旧M1 Graph兜底）
→ 先建Supervisor根Run、再保存TaskPlan
→ Capability驱动Supervisor + Worker Runtime
→ Business/Knowledge Worker → Harness → 真实Tool
→ Worker子Run上的ToolCall/Evidence
→ 同步任务双状态 + Checkpoint + Answer Evidence映射
→ 当前权限重新授权后的聊天响应
```

M2-21.11 已把跨请求恢复接到同一公开主路径：

```text
request_id + 当前CurrentUser/Thread + 有界脱敏消息记忆
→ 精确重放 / 新根Run / 领取waiting_user同根Run
→ 恢复前重新投影Capability并授权Evidence/File
→ 恢复累计预算、旧Tool签名和任务行版本
→ 继续原DAG或最多一次Re-plan
→ 最终Checkpoint前再次获权
→ 幂等保存用户/助手消息并返回waiting_user或completed
```

M2-21.12 已在同一公开主路径加入有界并行：

```text
依赖已满足的不同只读Worker（最多2）
→ 分别取得单一Action/Handoff
→ 独立子预算、子Run、Session和Harness并发执行
→ 按TaskPlan顺序稳定合并
→ G0～G7可执行测试矩阵
```

M2-22.6完整检索矩阵已经接通并收口。仍未接通的是M2-22.7 Reranker/Context正式评估、M2-22.8回答/Citation评估、M2-23前端引用展示和M2-24最终演示/阶段收口。

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
| M2-21 | 已完成 | 十二步全部完成；独立只读Worker最多2路并发，公开G4隔离和G0～G7权限/故障/资源矩阵已验证 | [M2-21唯一方案、确认记录与过程记录](records/M2_21_ENGINEERED_MULTI_AGENT_PLAN.md) |
| M2-22 | 进行中 | M2-22.1至M2-22.6已完成；M2-22.7五步详细方案已提交，等待用户确认后从M2-22.7.1开始，尚未运行Reranker或Context正式评估 | [M2-22方案与过程记录](records/M2_22_CROSS_BORDER_RAG_EVALUATION_PLAN.md) |
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
- M2-21采用Supervisor＋Business Data/Knowledge两个首批Worker的工程化多Agent底座；L0直接回答、L1单Worker、L2多Worker按任务复杂度自适应，不使用库存/知识固定意图if/else。
- Capability Catalog合同从第一版区分Tool、Skill、Agent和未来Runtime capability；当前五个真实Tool及Business/Knowledge两个Worker均为`available`，未实现Skill/Runtime capability不注册。
- M2-21第一版只有Supervisor可以Handoff；共享任务板、局部工作记忆、PostgreSQL Checkpoint、父子Run、树形预算和统一Answer Provider/Evidence交接进入阶段范围。
- M2-21先验证顺序执行，并在收口前验证独立只读Worker有界并行；长期偏好/经验记忆、Code Interpreter、Browser和后续专业Worker按真实需求分配到后续里程碑。
- M2-21采用Walking Skeleton实施顺序：先冻结最小合同和能力目录，M2-21.4跑通Mock/Fake最小闭环，M2-21.6跑通Business真实纵向链，M2-21.7验证顺序双Worker，M2-21.8接入真实Qwen和统一引用，再固化持久化、迁移API并完成记忆/并行/矩阵。
- 2026-09-04复核方案已由用户确认：不删除上述能力；最终公开聊天统一经过Agent Gateway，旧M1固定Graph只保留内部兼容/回归；Business Worker在有界Action/Observation循环中按任务自主选择两个M1 Tool；真实Qwen与统一引用回答前移到M2-21.8，持久化为.9、公开API迁移为.10、完整记忆/恢复为.11。
- M2-21.1已冻结`m2-agent-contract-v1`：TaskPlan最多24个任务且必须为合法DAG；Action一次只能五选一；通用JSON限制32键/32列表项/5层/16384字节；Evidence/Artifact每组最多12个且唯一；模型Action不能携带可信身份、权限、父Run或真实预算；通用状态只保存可序列化安全信息。G0～G7夹具另以`m2-agent-acceptance-v1`版本冻结，本步不执行这些场景。
- M2-21.2已冻结`m2-capability-contract-v1`：M1精确两个Tool、M2累计五个Tool通过适配层进入不可变Catalog；Business Data/Knowledge分别只拥有2/3个Tool，二者在该步当时都处于`declared`；模型只提交最多12个唯一能力ID，Resolver按可信`RunContext.roles`、Worker白名单和实现状态筛选并返回稳定安全摘要，原Registry/PermissionGuard仍负责后续最终执行边界。M2-21.6验证Business后将其切为`available`，M2-21.7验证Knowledge后将两个Worker均切为`available`。
- M2-21.3已冻结`m2-agent-provider-contract-v1`：Planner通过最多8个`WorkerCapabilityProfile`了解每个Worker获准的1～5个能力；四类Provider请求总大小最多65536字节；计划、行动、Handoff草稿和终态回答都要经过目标/归属/任务/Evidence引用校验。Handoff草稿不含真实Run或预算，确定性Mock只按有界脚本离线返回并在耗尽时显式停止。
- M2-21.4已建立五节点最小Supervisor LangGraph：L0直接进入Answer Provider，L1/L2按Task DAG顺序产生Decision和HandoffDraft、调用测试Fake Worker并汇总Observation/WorkerResult；错误Worker在Handoff前拒绝，同一Action无进展重复和Decision次数有确定性停止。
- M2-21.5已建立通用Worker Runtime：Dispatcher只按精确Worker ID分发且无旧图兜底；Runtime用程序生成的Handoff/Worker Run/预算引用注入可信`RunContext`、现有Harness和每次调用独立Session；树形预算原子预留根/子模型、Tool、Token、Evidence、任务、委派、深度和共享时间容量，关闭子预算后只归还未用配额；重复Handoff、连续无进展、超时和原始异常都会形成安全WorkerResult。子运行关联当前只记录在有界内存Trace中，数据库父子AgentRun明确留到M2-21.9。
- M2-21.6已实现有界Business Data Worker：每次Decision只能提出一个Action，最多4次且禁止相同Tool参数重复；参数必须通过M1严格Schema并与Handoff公开商品/市场/仓库及已解析SKU一致；真实执行只能经Harness调用`get_product_spec/search_inventory`。Observation显式记录能力ID和公开Tool数据，Evidence必须来自当前Observation全集。
- M2-21.7已实现有界Knowledge Worker：最多5次Decision，只能通过Harness调用`search_knowledge/read_uploaded_file/get_evidence_detail`；查询、File ID和Evidence ID必须来自Handoff允许范围或本次Observation，Tool深层结果先扁平化和截断再进入冻结的有界JSON状态。两个真实Worker现均可委派；Supervisor按DAG顺序运行L2并稳定合并Evidence/Artifact，只有标记`allows_partial`且已有可用成功结果时才允许失败Worker收口为`completed + partial`。
- M2-21.8已实现严格`QwenAgentProvider`：Planner使用按可信Worker动态生成的可空任务槽，Decision参数绑定Resolver批准Capability的真实JSON Schema，Handoff公开上下文由程序原样保留，Answer只能使用程序生成的`[E1]`至`[E12]`；Pydantic、服务端参数校验和Graph终态Citation Validator形成多层防线。真实Qwen Smoke只验证代表性计划、行动建议和合成Evidence回答，不等于生产质量矩阵或真实Tool端到端。
- M2-21.9已把运行合同固化到PostgreSQL：旧M1 Run保持`legacy`兼容；Supervisor/Worker使用同tenant/user/thread复合父子关联和共享Trace；任务节点、依赖边、执行/业务双状态与安全WorkerResult进入共享任务板，外键、自依赖Check及递归Trigger共同拒绝非法DAG；任务与Checkpoint均使用预期版本防覆盖，Checkpoint还会稳定序列化、限长并校验SHA-256；最终答案Evidence保持连续`[E1]`至`[E12]`、同tenant和唯一。实际Graph/API接线已由M2-21.10完成，恢复语义已由M2-21.11完成。
- M2-21.10已建立唯一公开Agent Gateway：消息POST不再导入或构造旧M1库存Graph；Gateway用可信身份和真实预算先创建根Run、再保存计划，经Resolver/Supervisor/Worker Runtime调用两个真实Worker和Harness Tool，并把ToolCall绑定到Worker子Run，最后同步任务板、Checkpoint、答案Evidence和助手消息。公开响应分离执行状态与业务结果，Evidence在返回前重新授权；集成门禁使用确定性Provider，不冒充真实Qwen生产质量。
- M2-21.11已建立有界跨请求恢复：Checkpoint只保留最多8条脱敏近期消息和2000字符摘要；消息POST接受可选`request_id`并以确定消息ID防重复；`waiting_user`下一请求在Thread锁下领取同一根Run，已有Worker结果继续原DAG，无Worker结果最多Re-plan一次。恢复前和最终保存前重新验证当前身份、Capability、Evidence/File；累计预算、截止时间及旧Tool签名不会重置。重复请求精确重放当时Checkpoint，换内容复用ID或活动根冲突返回409。
- M2-21.12已完成有界并行：Supervisor只并发依赖已满足、分属不同Worker且全部所需Capability为`none/read`的任务，默认最多2路；模型仍逐任务给出一个Action和Handoff。Business/Knowledge分别使用服务端4/8条Evidence子配额，总预留不超过根上限12；公开Gateway验证两个真实Worker重叠、不同预算引用和ToolCall子Run归属，结果按TaskPlan顺序合并。G0～G7均绑定到实际测试目标。
- M2-22评估采用“项目确定性评估 + Ragas语义评估 + 人工复核”：真实文件必须经过现有摄取、Parser/OCR、结构感知Chunk、BGE/pgvector、混合检索、Reranker、Context/Evidence和公开问答链；项目代码计算解析/切块、Precision/Recall/Hit Rate/MRR/nDCG、权限、Citation与资源，Ragas在M2-22.6/.8分别评检索和生成语义，固定Test与争议Bad Case人工复核。M2-22.1只冻结框架无关合同和Evaluator身份，不安装Ragas；DeepEval不进入RAG主评估，多Agent阶段若Ragas指标不足必须另行评审。
- 2026-09-08用户确认：M2-22.5至.8仍先完成RAG分层评估；RAG复核后不直接运行M2-22.9，而是先插入M2-22.8R意图识别与执行分流。意图识别不能只贴标签后继续全部进入Supervisor；它必须让简单单一查询走快速路径、固定复合查询走受控Pipeline、确需规划的任务才进入Supervisor/Worker。分流不得固定额外消耗一次LLM：高置信明确请求先由程序判断，只有不确定请求才用一次结构化模型输出同时完成意图、路径和参数提取；L0分类与直接回答不拆成两次、结构化Business结果优先由程序格式化。本步不新增Worker、Tool、Web研究、时间约束或权威性比较；细化方案必须在M2-22.8复核后另行提交并获得授权。
- M2-22.1已把来源、许可和`planned/downloaded/verified/rejected`状态互斥规则落为严格Schema；Golden只能引用可信Fixture ID，不能携带身份、ACL或真实预算；完整Chunk/检索配置与数据、代码、模型、Evaluator/Judge/Prompt身份进入可复现运行合同。项目确定性结果与Ragas结果使用不同Schema，框架/Judge失败没有数值，不能冒充0分。
- M2-22.2以Manifest作为唯一URL白名单：只有许可已核查、版本固定、显式获准的小文件可以下载；HTTP重定向必须先把最终URL写回Manifest，声明大小和实际流式字节均受来源预算约束，原件只读，普通PDF使用`identity_copy@m2-eval-transform-v1`，合规小图片可使用固定`image_to_pdf`；验证后的Hash也支持Git忽略文件在新环境中安全重建。首批8份欧盟官方核心PDF已验证，3个CORD/DocILE/Kleister全量候选仍不下载。
- M2-22.4 Runner只负责摄取/Parser层：公开API登记后直接调用已有`DocumentParserService`，不调用会继续索引的端点；严格恢复只认Frozen Evidence原文。`completed`只代表运行和清理成功，不代表质量达标。实际18/18解析完成，但22/34事实恢复、真实组4/14、OCR 2/4，必须作为后续切块与检索的上游基线保留。
- M2-22.4只读诊断已证明低分主要不是Native抽不出官方PDF文字：10条外部缺失Golden在Native全局及声明页均为逐字命中，基线却因`detected_document_table/two_column`把整份PDF切到Docling并丢失；图文DOCX的2条图片文字在Native和Docling中均0 Token。诊断只读原文件和三路Artifact，不连接API/数据库/Storage，也不改变生产路由。
- M2-22.4R-01把Native健康判断固定为版本化有效字符、最低文字和内容页覆盖；R-02把Docling `DocumentConverter`、模型、OCR线程和文档句柄全部移入每文档一次性的Windows `spawn`进程。父进程只发送非秘密受控配置，以50 ms采样整棵进程树RSS，并限制总时间和Snapshot字节；任何失败都不接收部分Artifact，只返回固定错误并清理进程树。首版默认总时限150秒、RSS 4 GiB、Snapshot 64 MiB；这属于单任务隔离，不是全局并发队列或OS cgroup硬内存配额。
- M2-22.4R-03把DOCX Parser升级为v2：Section页眉/页脚是独立来源，正文`wp:inline`图片按Run原位OCR；Canonical仍读取旧v1产物，并用可选、显式版本化的`m2-docx-source-v1`扩展记录来源、图片序号/Hash/尺寸和OCR身份/置信度。已由Native处理的DOCX视觉标签只保留审计理由，不再触发标准Docling。
- M2-22.4R-04新增严格`m2-post-parse-quality-v1`：仅健康Native参与70%全文保留率比较；PDF按真实页定位检查最终少于10字符时的Native文字突降或扫描未恢复；DOCX大于5 KiB空OCR先产生结构化告警，图片独占段落或正文近空时升级拒绝。门禁在Router完成选路后、Parsed Artifact发布前执行；新解析必须携带接受决定，拒绝结果不进入`ready`、不写Parsed Storage且不能创建Index Set。旧v1 Routed Artifact仍可读取，不需要数据库迁移。
- M2-22.5冻结首轮`400/500/100`、`500/600/100`、`600/700/100`、`700/850/100`四组完整配置，只从首轮结构质量选择候选，再只改变overlap 80/100/120。评估器分别检查Golden整条包含与来源定位、段落/标题/表格/DOCX视觉上下文、Token范围、显式重叠、空块/近重复、来源顺序、Locator完整性和重复构建字节确定性；失败固定归因`parser_artifact/chunk_rule/locator`。矩阵只产生候选，不改变生产默认Chunk参数。
- M2-22.5R坚持正文与标题元数据分离；用户已确认`heading_hints`只作Parser候选诊断，R-01A为4份问题文档冻结85条完整分类和26条标题正文关系，R-01B补齐真实行级Locator。R-02 Chunker v2已抽离标题、绑定同栏正文、合并连续多行标题并拒绝43/43已知噪声。用户逐页确认OSS 4条与GPSR 1条均为同级，纠正人工Golden v1后，v2下真实路径为26/26；这5条无需修改Parser或Chunk规则。
- M2-22.5R-03把`heading_hints`与正式质量分母彻底分开：有可信Golden时，每条标题必须在同一正文Chunk中通过完整路径、正文锚点、Parser标题来源、页码/source span和检索视图检查；无人工Golden时只保留Canonical结构标题检查，不把启发式提示直接算成功。报告升级为`m2-chunk-quality-report-v2`并记录标题数据身份；总门禁只要求冻结候选中至少一组完整通过，不要求所有对比实验同时通过。
- M2-22.5R-04正式运行后保持严格门禁：`completed`只表示18文档矩阵与清理执行成功，不等于质量通过。26条人工标题关系全部通过；55/56总标题中的单个失败属于无人工Golden文档的Canonical fallback。边界统计必须区分正文丢失与“标题已按设计提升为元数据”，但这种排除必须由Chunk Artifact中的精确源范围证明，不能仅凭标题字符串或Parser hint跳过。
- M2-22.5R-04A把上述证明落实为Chunker v3：`heading_sources`和`heading_metadata`保存真实Block、字符起止、页码/bbox并进入Hash；标题质量仍要求Parser来源、路径、正文、检索视图和Locator联合通过，正文边界只排除精确且由Parser声明的标题范围。PDF有行级Locator时按物理layout line及真实残段审计，避免把双栏/表格的横向文本层拼接误报为一个断裂段落。最终18文档13组矩阵总门禁True，但不据此修改生产默认参数。
- M2-22.6只允许顺序筛选：9组冻结Chunk候选加当前生产基线；先在RRF=60下比较候选深度10/20/30，再只对每组所选深度比较RRF 20/60/100。确定性排名指标与Ragas 0.4.3语义指标分栏，Judge/框架/网络失败无数值；Noise Sensitivity因固定版本需要回答而在本步显式跳过。正式矩阵已按该顺序完成；无坐标DOCX候选使用Canonical Block降级，不能用Repository直出、删除候选或扩大TopK绕过Service失败。
- M2-22.6最终补跑严格使用`compact/100 + depth 10 + RRF 60`，没有重跑完整矩阵。Ragas有效均值只按完成样本计算：全部34题Precision `.8024`（21完成）、Recall `.9630`（27完成）、Relevancy `.9815`（27完成）；其余为7个超时、13个Provider失败、7个框架失败，Noise 34条因无回答全部跳过。外部欠费和跨重建UUID同分排序差异均作为风险保留，不修改生产参数。

### 7.2 当前风险与边界

| 风险或边界 | 当前事实 | 优先排查方向 |
|---|---|---|
| Reranker CPU 延迟 | 约 15 个候选的本机 p50/p95 约 6.70/7.24 秒 | 候选裁剪、GPU、批处理或有证据支持的路由策略 |
| 图文 DOCX | R-03已找回页眉与正文图片文字；M2-22.5全部7组配置的页眉、页脚、图片OCR和前后文均1/1，且4条OCR Golden均找到内容和Locator。Word渲染页码仍不可由`python-docx`可靠获得 | 继续使用Section/段落/Run/图片序号等真实定位，不把Section号伪装成物理页码；进程隔离留待负载加固 |
| 事实级 Locator | M2-22.5已允许证据跨Canonical换行/连续来源块，并识别DOCX表格坐标；最佳配置34/34 Golden均有内容与真实Locator，18/18文档Locator完整性通过，0个Locator归因失败 | 后续保持相同真实页码、source span、表格坐标或DOCX来源字段；不得用伪造页码制造通过 |
| Chunk标题与边界 | R-04A已用Chunker v3记录标题Block、字符范围、页码/bbox和精确排除原因；PDF按物理layout line及真实残段审计。正式矩阵达到56/56标题、0/11809边界断裂，多个候选34/34内容与Locator，总门禁True | 保持Golden、Parser、R04阈值和生产默认参数不变；未来新语料若失败，先按Parser Artifact、Chunk规则、Locator三层归因，不把Chunk通过外推为检索/回答通过 |
| DOCX region公开Locator | 已用现有`source_block_ids`实现受校验Canonical `block_number`降级；原第4名页眉Chunk仍保留第4名。非法Block只隔离该名次并使质量门禁失败，不能静默删候选；正式106,518候选映射失败0 | 保持精确坐标优先、Block仅兜底；不按页眉/页脚类型过滤，因为冻结题确实包含页眉控制码。新失败先查Parser/Chunk来源一致性，再查结果映射 |
| Ragas正式Judge完整性 | 用户已授权且单配置补跑完成；Precision/Recall/Relevancy分别有21/27/27条有效分数。7个超时、13个HTTP 400欠费Provider失败和7个Ragas无效结果均无数值；Noise 34条按无回答边界跳过 | 后续不得把完成样本均值外推为34题全量结论；先处理外部账户状态并设计独立授权的缺失样本补评方案，本步不自动重跑或启动回答链 |
| 既有跨月测试 | R-04收口已让夹具使用真实上传返回的Storage Key，跨月独立用例与完整后端均通过 | 保持生产Storage规则不变；未来测试继续从实际上传结果取Key |
| 数据库测试夹具会重置正式M2 Seed | 本次相邻集成后实测数据库正式记录归零但Storage仍有10个对象；若只看测试通过会留下不一致基线 | 所有数据库测试结束后重新运行既有两个M2 Seed入口并检查`clean=True`；后续单独强化测试隔离和唯一数据身份 |
| 规模与并发 | 当前只证明小型合成语料闭环 | M5再做负载、并发和更大规模评估 |
| Parser路由选择与Docling稳定性 | 扫描PDF结果返回后的`shutdown_timeout`已通过一次性Worker末端确定性退出修复；父进程的2秒收尾、超时/RSS/Snapshot限制和活进程拒收均未放宽。正式复验恢复18/18、34/34、OCR 4/4和18/18 R04接受 | 继续保留故意滞留Worker拒收回归；全局并发/背压及直接DOCX OCR进程隔离仍留给后续负载加固，不把本次单Worker结果扩大为吞吐证明 |
| Business商品规格无Evidence | M2-21.8明确不伪造引用；只规格可作为已观察结构化结果，但没有可引用Evidence | 后续若产品要求规格也强制引用，需先新增真实规格Evidence来源 |
| Qwen生产质量未收口 | M2-21.8代表性真实Smoke已通过；M2-21.12环境无Key而显式跳过复跑，仍未覆盖任意自然语言、真实Tool整链和负载 | M2-22/M5以版本化评估集验证规划、行动、参数、引用、延迟和预算 |
| Ragas Judge偏差与依赖边界 | 固定`ragas==0.4.3`与`langchain-community==0.4.1`，Judge身份、参数和Prompt Hash均复核。已完成样本分数可审计，但超时与欠费使真实跨境仅4/14条Precision、8/14条Recall、7/14条Relevancy有效 | 均值必须连同完成数报告；外部账户恢复后若需补缺，必须另行授权并保持相同Judge身份，不得用换框架、换模型或生成回答掩盖缺失 |
| 检索跨重建稳定性 | 同一Index内120条route复跑0变化；清理后重建时Hit/Recall@8与miss复现，但MRR/nDCG变化。Dense、Lexical和RRF同分兜底依赖运行期Chunk UUID，新建UUID会改变同分顺序 | 当前不改生产检索合同；后续若单独授权修复，优先评估以稳定Canonical Chunk身份作为同分键，并增加跨清理重建回归 |
| 记忆与崩溃恢复边界 | 已完成有界脱敏短期记忆、澄清同根恢复、一次Re-plan和撤权重验；不是长期画像，未知状态进程崩溃后的`running`根当前返回409，不自动抢占 | M5评估长对话和恢复租约需求，不擅自扩成永久记忆 |
| 并发规模边界 | 当前只证明两个独立只读Worker在单进程事件循环内有界重叠、预算/Session/Trace隔离；同步Tool片段和高负载吞吐未做生产基准 | M5再做负载、多进程、背压和更大规模评估；写操作必须另行设计审批与冲突控制 |
| 简单请求统一进入Supervisor | 当前公开Gateway还没有独立的意图/复杂度分流，已有集成基线显示单一Business查询也会产生6次模型调用；若再固定增加一次LLM分类，只会给所有请求叠加新成本 | 不提前修改当前RAG评估链；M2-22.8复核后单独设计M2-22.8R，采用“程序高置信分流 → 低置信才调一次结构化模型”的候选策略，用路由准确率、模型调用数、Token、成本和p50/p95对比证明改造价值 |

## 8. 最近验证基线

M2-22.6正式收口时：

- Run `m2-22.6-20260909t165858-4a56843a`只重建并运行`compact/100 + depth 10 + RRF 60`：18份文档、40题、18个Index Set、779个Chunk、120条route list、1,430候选，映射失败0；未重跑10组/50点矩阵，生产默认未变；
- 全部34条可回答Hybrid的Hit/Recall@8仍为`.9118`，真实/合成/通用分别为`.8571/1.0000/.9000`，miss仍为`2/0/1`。跨重建MRR@10由`.6584`变为`.6929`、nDCG@10由`.7193`变为`.7450`；原因定位为同分兜底依赖新建Chunk UUID，同一Index内120条稳定性仍为0变化；
- Ragas完成样本均值为Precision `.8024`（21/34）、Recall `.9630`（27/34）、Relevancy `.9815`（27/34）；7个超时、13个HTTP 400欠费Provider失败、7个框架无效结果全部无数值，Noise 34条按`input_invalid`跳过。真实组有效数只有4/14、8/14、7/14，不能宣称全量通过；
- Ragas专项9、Runner/指标96、Index/Embedding/Retrieval相邻153、允许单元680和固定本地BGE Smoke 4全部通过；允许集成为`140 passed, 2 skipped, 1 failed`，唯一失败仍是历史M1 Seed清场顺序与正式M2外键冲突。Ruff 348文件、lint、Mypy 163源码、编译、依赖和diff门禁通过；
- 摘要/Trace Hash记录在[M2-22过程记录第42节](records/M2_22_CROSS_BORDER_RAG_EVALUATION_PLAN.md#42-m2-226-ragas检索语义评分补跑与最终收口2026-09-10)后精确删除。最终三套Seed重跑；独立基线为10 files/documents/versions、10 parse/index pending、9 ACL、0 ChunkSet/IndexSet/Chunk、评估tenant 0、Storage 10 uploads/0派生对象、M1 `150-20-5=125`；
- 未运行Reranker、Context/Evidence、Tool、Harness、Agent/LangGraph、最终Qwen回答、Citation或M2-22.7。M2-22.6完成后停止，等待用户理解和另行授权。

M2-22.6R-01与确定性矩阵完成、Ragas外发受阻时（历史基线）：

- 无精确坐标DOCX候选降级到受校验Canonical Block；坏Block只隔离单个候选、保持原始名次并使完整性门禁失败。真实阻塞样本从全局报错变为Dense第4名`block_number=1`，没有删除页眉/页脚；
- 正式矩阵完成10组Chunk、深度10/20/30后RRF 20/60/100的顺序筛选；50份Trace覆盖6,000条Dense/Lexical/Hybrid路由列表、106,518候选且映射失败0。所选`compact/100 + depth 10 + RRF 60`在真实跨境Hybrid Hit/Recall@8为0.8571、MRR@10为0.4817、nDCG@10为0.5692；
- ACL/软删除/inactive Index Set/tenant泄漏0，120条排名稳定性复跑0变化；生产默认和数据库结构未改。专项177、相邻136加真实BGE Smoke 4、允许单元625均通过；允许集成130通过、3跳过、1个旧M1 Seed清场夹具失败；
- Ragas 34条正式样本未得到分数：Context Precision/Recall为Judge失败，Context Relevancy为框架失败，Noise Sensitivity按纯检索边界跳过；等待用户明确授权把评估内容发送给外部Qwen API。详细证据见[M2-22记录第41节](records/M2_22_CROSS_BORDER_RAG_EVALUATION_PLAN.md#41-m2-226r-01与确定性检索矩阵2026-09-09)。
- 两个本步检索报告目录记录Hash后已精确删除；M1和两个M2正式Seed均实际重跑。独立核对为10 files/documents/versions、9 ACL、10 pending/uploads、0 ChunkSet/IndexSet/Chunk、评估tenant 0、M1库存125；冻结原文、既有上游报告和模型缓存未删。
- Ragas固定0.4.3，只适配Context Precision/Recall/Relevance与Noise Sensitivity；Judge身份/参数/Prompt实现Hash/重试/失败状态可追溯，不保存思维链。前三项最小真实探针通过，Noise因本步禁止回答而显式`skipped/input_invalid`；
- 专项单元与真实PostgreSQL FTS/pgvector/RRF集成为`13 passed`；9个新代码/测试文件Ruff格式和lint通过，4个评估源码Mypy通过，编译、`pip check`和diff检查通过；完整允许回归未运行；
- 正式运行已真实解析18/18文档、预编码40/40问题并完成首个`compact/80`全量BGE/Index；首题Dense@10第4名DOCX region Chunk无法形成公开Locator。最早缺口为Parser Artifact中region通用Locator为空，暴露于Dense结果映射；矩阵无正式分数，不能记0或通过；
- `compact/80`的292-Chunk VAT索引还在生产2秒SQL超时下真实失败、评估30秒覆盖下成功；生产超时、Chunk、TopK/RRF均未修改。失败数据和临时报告已清理，两个Seed重放后的独立审计为10 files/documents/versions、9 ACL、10 pending/uploads、0 ChunkSet/IndexSet/Chunk、M1库存125、评估租户0、`clean=True`；详见[M2-22记录第40节](records/M2_22_CROSS_BORDER_RAG_EVALUATION_PLAN.md#40-m2-226实施记录检索评估器完成真实矩阵受docx公开locator阻塞2026-09-09)。

M2-22.5R-04A完成时：

- Chunker升为`m2-structure-aware-chunker-v3`，标题保持在`heading_path/retrieval_text`而不回填`body_text`；新增精确`heading_sources`与`heading_metadata`排除记录，并修复被主标题吸收的masthead漏记；
- 首轮正式运行先把标题修到56/56、边界从90降到41但门禁仍False；逐条复核确认22条是双栏/表格横向拼接误报、18条是有精确记录但无正文可绑定的封面/图示标题、1条是真实masthead审计漏记。修正后六份问题Native PDF均为`MISSING 0`；
- 最终Run `m2-22.5-20260909t032311-651ab937`为18/18文档、34条内容Golden、4组首轮与9组overlap，`quality_gate_passed=True`。代表性large/120为34/34内容与Locator、56/56标题、0/11809边界、45/45表格、18/18顺序/Locator/确定性，DOCX页眉3/3、页脚3/3、图片OCR和前后文各1/1；
- 专项`123 passed`、相邻PostgreSQL/Service`20 passed`、完整允许单元`385 passed, 2 skipped`；Ruff、格式、156源码Mypy、编译、依赖和diff检查通过；
- Runner内清理与最终独立审计均确认评估数据为0，正式基线为10 files/documents/versions、9 ACL、10 pending/uploads、0 ChunkSet和M1库存125。报告Hash固定后删除；没有修改Golden、R04阈值或生产默认参数，没有运行任何禁止下游。完整证据见[M2-22记录第39节](records/M2_22_CROSS_BORDER_RAG_EVALUATION_PLAN.md#39-m2-225r-04a实施记录标题来源审计版面边界校准与正式收口2026-09-09)。

M2-22.5R-04正式矩阵运行并受阻时：

- 正式命令使用当前Parser/R04、Chunker v2、标题Golden v2和报告v2，18/18文档解析并通过R04；4组首轮后按冻结策略选择`chunk-large`与`chunk-medium`，分别扫描overlap 80/100/120，共运行10组完整配置；
- `chunk-large-overlap-120`产生417个Chunk，Token min/p50/p95/max=`6/685/699/803`、重叠冗余率15.99%；34/34内容Golden和Locator、证据范围覆盖100%、45/45表格、18/18顺序/Locator/确定性、0空Chunk、DOCX页眉/页脚/图片OCR与前后文均通过；
- 人工标题Golden 26/26通过；总标题55/56，唯一失败定位到`m2-complex-v1-scanned-receiving-ticket`的Canonical fallback。段落9598/9687、边界断裂90/9750；11份PDF出现的89个段落缺口与纯标题从`body_text`抽离一致，另1个失败是上述结构标题单元。当前代码的边界审计没有读取任何“标题已提升为元数据”的精确来源记录，因此不能把这90项当成真实正文被切坏，也不能直接忽略它们制造通过；
- 质量报告运行状态`completed`但总门禁`False`；报告SHA-256为`ecf16a31fe77ad1dfc39413b7a9bc3bd8ea2a37644be50dd879c1da1fc425fbd`，记录汇总后已删除。专项`101 passed`、相邻Parser/Chunk/Seed/Runner集成`20 passed`、完整允许单元`367 passed, 2 skipped`；
- 评估数据库行、评估ChunkSet和Storage对象均为0；集成测试后重建两组正式Seed，最终为10 files / 10 documents / 10 versions / 9 ACL / 10 pending / 10 uploads / 0 ChunkSet / M1库存125 / `clean=True`。本步未修改生产代码、默认Chunk参数、Golden或R04阈值，也未运行任何禁止下游。完整证据见[M2-22记录第38节](records/M2_22_CROSS_BORDER_RAG_EVALUATION_PLAN.md#38-m2-225r-04正式矩阵运行质量受阻与清理2026-09-09)。

M2-22.5R-03质量门禁防伪与报告语义完成时：

- 评估器对可信标题案例必须在同一个文本Chunk中核对完整`heading_path`、Golden正文锚点、Parser真实提示/结构来源、正文页码与source span覆盖及`retrieval_text`标题上下文；仅有标题字符串或元数据不能通过；
- 人工标题Golden v2成为受审文档的正式标题分母，未经人工确认的`heading_hints`只作诊断；4份真实问题PDF的26/26关系通过严格新指标；
- Chunk报告升级为v2，新增标题数据版本、Hash和本次案例数；每组配置保留独立门禁，报告总门禁表示“冻结候选的重叠扫描中至少一组完整通过”，失败实验不删除；
- TDD RED为`6 failed, 4 passed`；定向专项`101 passed`、真实标题文件`6 passed`、完整允许单元`371 passed, 2 skipped`；5文档真实Runner集成通过并在7组配置中逐组验证双栏4/4，相邻数据库集成`20 passed`；
- 未运行R-04正式18文档、34条内容Golden与7组矩阵，也未运行任何禁止下游。当前停止等待R-04单独授权。完整证据见[M2-22记录第37节](records/M2_22_CROSS_BORDER_RAG_EVALUATION_PLAN.md#37-m2-225r-03实施记录标题质量门禁防伪与报告语义2026-09-08)。

M2-22.5R-02人工Golden纠正并完成时：

- 用户逐页复核确认OSS的`Specific details`与后续4个标题同级，GPSR的`Better enforcement`与`Consumer detriment`同级；此前由助手人工冻结的父子关系有误，Parser字体层级、PDF Outline（OSS）和Chunker输出没有错；
- 标题数据升级为`m2-chunk-heading-golden-v2`，SHA-256为`c4c4b78313118bc9a9e646cd1e3479f7ba71e9a76eb15e982fee1060d12aa4a6`。只纠正5条`semantic_level/heading_path`，标题原文、页码、正文锚点、26条总数、43条非标题和所有门禁阈值均未放宽；
- 专项为`22 passed`，包含26/26真实标题正文关系与43/43非标题拒绝；相邻Chunk/Evaluation合同`110 passed`，相邻Parser/Chunk/Seed数据库集成`19 passed`；完整允许单元`367 passed, 2 skipped, 1 failed`，唯一失败仍是未实施R-03的标题空壳防伪；
- 数据库与Storage恢复10 files / 10 documents / 10 versions / 9 ACL / 10 pending / 10 uploads / 0 ChunkSet / M1库存125 / `clean=True`；5张临时PDF预览已删除，原始PDF未修改；
- 本次纠正未运行18文档7组正式矩阵、Ragas、Embedding、pgvector、检索、Reranker、Context、Agent、Qwen或前端。R-02标记完成并停止，下一步必须单独授权R-03。完整证据见[M2-22记录第36节](records/M2_22_CROSS_BORDER_RAG_EVALUATION_PLAN.md#36-m2-225r-02用户视觉裁决人工golden纠正与收口2026-09-08)。

M2-22.5R-02确定性标题绑定主体实现、真实层级验收受阻时：

- Chunker v2在正文窗口前处理标题；纯标题不进入`body_text`，编号/同行剩余正文保持原字符范围，`heading_path`独立保存标题，`retrieval_text`继续由标题元数据和正文按Token预算派生；双栏正文只继承本栏标题；
- 连续同栏、同字号且行距可证明为换行的标题会合并；项目符号、纯金额、引用编号及同排字段标签/值不会提升。真实4份问题PDF达到21/26可信正文路径，43/43已知非标题未提升；剩余5条聚合RED保留；
- 合成Chunk合同14/14通过；格式化后的定向合同102/102通过；完整允许单元`366 passed, 2 skipped, 2 failed`，两个失败分别是5条语义父子关系聚合RED和未实施R-03的标题空壳防伪；相邻数据库集成19/19通过；
- Ruff全维护范围、156源码Mypy、编译、依赖和diff检查通过；数据库回归后正式基线恢复为10 files / 10 documents / 10 versions / 9 ACL / 10 pending / 10 uploads / 0 ChunkSet / M1库存125 / `clean=True`；本步没有正式评估租户或Storage评估对象；
- 本步未运行原18文档7组矩阵、Ragas、Embedding、pgvector、检索、Reranker、Context、Agent、Qwen或前端。R-02未标完成，不进入R-03/R-04/M2-22.6。完整证据见[M2-22记录第35节](records/M2_22_CROSS_BORDER_RAG_EVALUATION_PLAN.md#35-m2-225r-02实施记录确定性标题绑定与语义层级阻塞2026-09-08)。

M2-22.5R-01B Docling一次性Worker收尾阻塞解除时：

- 一次性Worker现在只在完整结果或固定失败消息同步发出并关闭Pipe后执行确定性进程退出；父进程原有2秒收尾窗口、活进程拒收、退出码与Snapshot复验没有放宽，故意滞留的假Worker仍得到`shutdown_timeout`；
- 单件真实Router/RapidOCR Smoke为`1 passed`，扫描PDF恢复2/2事实，Worker日志为`status=success`、总耗时101,853 ms、峰值约1.96 GB，PID完成后不存在；
- 干净基线上的18文档正式Parser/R04为`run_status=completed`：18/18上传与解析、34/34 Golden、外部14/14、OCR 4/4、18/18质量接受，路由Native 16 / Docling 1 / Hybrid 1；评估行/对象为0，正式10份数据库/Storage基线与M1库存125恢复；
- Docling专项`6 passed`，完整允许单元为`370 passed, 2 skipped, 3 failed`，3个失败仍只对应未实施的R-02标题绑定RED；相邻数据库集成`21 passed`。Ruff、156文件Mypy、格式、编译与diff检查通过；
- 本步没有改Router、R04、Chunker或标题Golden，没有运行Embedding、pgvector、检索、Reranker、Context、Agent、Qwen、Ragas或前端。完整证据见[M2-22记录第34节](records/M2_22_CROSS_BORDER_RAG_EVALUATION_PLAN.md#34-m2-225r-01b补充实施记录docling一次性worker确定性退出2026-09-08)。

M2-22.5R-01B PDF行级Locator实现完成、验收受阻时：

- 12份正式PDF重复解析确定，4组双栏标题正文可按左右坐标唯一定位；4份问题PDF中38条独立标题和4个组合片段均引用真实物理行及字符范围；旧Artifact可读，新几何进入内容Hash；
- 允许范围单元回归`369 passed, 2 skipped, 3 failed`，3个失败是仍等待R-02的编号标题/父子标题与标题空壳RED；数据库相邻集成`21 passed`；维护范围Ruff、156文件Mypy、编译与diff检查通过；
- 18文档正式Parser/R04实跑为17/18、32/34、官方14/14、OCR 2/4。扫描PDF Worker连续两次`shutdown_timeout`；评估数据库行和Storage对象清零，正式10文档基线及M1库存125恢复，临时报告删除且Worker PID不存在；
- 因全量门禁没有重现，R-01B不能标记完整通过，R-02、生产Chunker和M2-22.6均未开始。完整证据见[M2-22记录第33节](records/M2_22_CROSS_BORDER_RAG_EVALUATION_PLAN.md#33-m2-225r-01b实施记录pdf行级locator增补与验收阻塞2026-09-08)。

M2-22.5R-01A可信结构标题Golden完成时：

- `m2-chunk-heading-golden-v1`对4份问题PDF的85条Parser提示完成无遗漏分区：38条独立标题、4条组合标题片段、43条非标题；数据SHA-256为`93428d44fe539ed4eafbed6b80169818fc273c6c675a807de887fa20c3aa9c17`；
- 26条可信正文关系包含双栏4、OSS 16、GPSR 5、Safety Gate 1，并明确完整标题路径、物理页、非标题正文锚点和`following_flow/same_column`；
- 新专项`5 passed`，与既有评估合同和40条Smoke数据相邻回归`89 passed`；Ruff、156个源码Mypy和编译通过；视觉复核临时页图已精准删除；
- 生产Parser/Chunker、R04、34条内容Golden、数据库/Storage均未修改，也未运行任何禁止下游。双栏行级Locator阻塞和待确认方案见[M2-22记录第31至32节](records/M2_22_CROSS_BORDER_RAG_EVALUATION_PLAN.md#31-m2-225r-01a实施记录可信结构标题golden冻结2026-09-08)。

M2-22.5R-01完成、R-02暂停时：

- `tests/unit/test_document_text_chunker.py`新增编号/同行标题、多级标题路径和正文短语误报反例；`tests/unit/test_rag_chunk_metrics.py`新增标题空壳防伪反例；
- 旧实现定向运行实际为`3 failed, 14 passed in 8.45s`：3个失败分别冻结编号/同行标题未进入元数据、多级子标题未绑定正文、标题空壳被指标误收；其余相关合同保持通过，Ruff定向检查通过；
- 只读真实审计4份失败文档85条提示：整行精确29、同行唯一21、歧义1、最终页文本缺失34，并确认若干提示本身不是标题。因此第28节原`152/152`假设暂停，等待确认人工冻结的可信结构标题Golden；
- 本步没有修改生产Chunker、Parser、R04、数据库或Storage，也没有运行任何被禁止的下游能力。完整证据见[M2-22记录第30节](records/M2_22_CROSS_BORDER_RAG_EVALUATION_PLAN.md#30-m2-225r-01实施记录合同反例与真实提示审计2026-09-08)。

M2-22.5完成实际矩阵、但质量门禁未通过时：

- 18份R04合格文档通过公开上传/建文档API、正式Parser Service和现有`DocumentChunkService`进入隔离评估租户；首轮compact/medium/current/large和`chunk-large`的overlap 80/100/120共7组完成，生产默认配置未变；
- 首轮四组分别为800/611/506/429个Chunk，Golden包含与Locator为34/34、33/34、33/34、34/34；候选选择为`chunk-large`。overlap 120得到441个Chunk、Token min/p50/p95/max `2/684/699/805`、显式重叠率16.00%、34/34 Golden与Locator、9687/9687段落、0/9750边界断裂、45/45表格、18/18顺序/Locator完整性/重复构建确定性、0空块及1个近重复；
- DOCX页眉/页脚/图片OCR/前后文均1/1，OCR组4/4；所有配置标题只保留109/152，因此7组质量门禁均False。medium/current/overlap80还把`smoke-ext-025-ioss-coverage`切到多个Chunk，分别只覆盖96.59%/96.59%/75%，归因为`chunk_rule`；Parser Artifact和Locator归因均为0；
- 正式报告为Git忽略的`data/evals/runtime/reports/m2_cross_border_chunk_report_v1.json`，498,013字节，SHA-256 `37bf809c654af1eb92cfb777165aba274fdf6307e7e8befc220cbcf44c69f3e7`。清理后评估数据库行、ChunkSet与Storage对象均为0；正式基线为10 files/documents/versions、9 ACL、10 pending、10 uploads、0正式ChunkSet，M1德国仓可售125；
- 专项`84 passed`；相邻单元`173 passed, 2 skipped`；相邻集成`21 passed, 3 skipped, 6 errors`，6个setup error来自旧`test_file_api.py`无条件删除仍被正式文档外键引用的`files`，未进入本步代码；完整允许范围单元`442 passed, 2 skipped`、集成`60 passed, 3 skipped`。Ruff、156个源码Mypy、编译、依赖、diff和Alembic门禁通过；全范围格式只剩未修改的既有迁移测试一处差异。详见[M2-22记录第27节](records/M2_22_CROSS_BORDER_RAG_EVALUATION_PLAN.md#27-m2-225实施记录chunk质量矩阵2026-09-08)。

M2-22.4R-04完成时：

- `m2-post-parse-quality-v1`完整记录状态、拒绝/告警代码、Native与最终字符数及保留率、所有阈值、逐页判断和DOCX图片判断；严格反序列化会重新计算决定，不能只把`rejected`改成`accepted`绕过门禁；
- Router对Native和增强结果统一执行质量判断，Parser Service在序列化和Storage发布前再次要求非空且已接受的决定。拒绝集成实际得到Parse/File/Index失败、无Parsed Storage Key、0个Index Set；接受/告警决定写入向后兼容的Routed Artifact，新解析不允许省略决定；
- 18份原件经公开API、隔离PostgreSQL/Storage和正式Parser主链为18/18完成、34/34 Golden、4/4 OCR；路由Native 16 / Docling 1 / Hybrid 1，18个决定全部接受且0告警，282个PDF页与1个DOCX图片判断均接受。报告SHA-256为`f97757f24713d76becb4a9815cee2450a21844e31f45e02965b45fdee8d8d915`，运行后评估行/对象为0并恢复正式10文档与M1库存125；
- 定向质量/路由`25 passed`、Parser Service集成`6 passed`、相邻集成`31 passed`、完整单元`1008 passed, 2 skipped`、完整后端`1287 passed, 14 skipped`；Ruff、155个源码Mypy、编译、依赖和Alembic门禁通过。跨月Key夹具与Alembic日志污染已最小修复；详见[M2-22记录第25节](records/M2_22_CROSS_BORDER_RAG_EVALUATION_PLAN.md#25-m2-224r-04实施记录解析质量门禁与拒绝索引2026-09-08)。

M2-22.4R-03完成时：

- 真实图文DOCX经正式Router保持`native`，Artifact共12个Block、254个非空白字符；`QC-VISUAL-17`和`QUARANTINE 12 PCS`均找回，图片OCR平均置信度约0.993，Markdown顺序为页眉→正文→`[图片内容]`→图注→页脚；
- 图片安全覆盖外链拒绝、数量/单图/总字节/像素上限、损坏图片、重复图片Hash缓存及空OCR不伪造；普通Artifact v1 Block继续省略新字段并保持旧Hash计算形状，严格新元数据拒绝不完整来源；
- 专项与相邻Parser/Artifact/Router/诊断/Chunk/配置/复杂夹具`116 passed`；完整单元`990 passed, 2 skipped`；显式真实RapidOCR Router Smoke `1 passed`；Ruff、155个`app`源码Mypy、编译和依赖通过。Word只读渲染的1页PNG已逐页检查，页眉/图片/页脚无裁切、重叠或缺字；
- 全量后端`1259 passed, 14 skipped, 6 failed`；其中5个R-02日志捕获断言单文件复跑`5 passed`，剩余既有跨月索引用例独立失败，原因仍是上传Key写死`2026/08`。这些均不在R-03代码路径，未越界修复；详见[M2-22记录第24节](records/M2_22_CROSS_BORDER_RAG_EVALUATION_PLAN.md#24-m2-224r-03实施记录docx页眉页脚与原位图片ocr2026-09-08)。

M2-22.4R-02完成时：

- `LocalDoclingProvider`已移除主进程共享Converter；每个调用固定用`spawn`子进程重新构造离线CPU Docling/RapidOCR，父进程只接收`R`就绪、`S + 严格JSON Snapshot`成功或`F`失败三类有界消息，成功后还会按请求格式重新验证Snapshot；
- 超时任务后PID消失，下一任务PID不同且模块计数重新为1；崩溃、1 MiB RSS限制、1 KiB结果限制和发送成功快照后仍不退出都返回固定`复杂文档增强解析失败`。聚焦隔离/Settings/Router为`73 passed`，完整单元`974 passed, 2 skipped`，相邻Parser Service/File Reading/复杂Seed/Runner为`12 passed`；
- 显式真实扫描Smoke为`unusable → docling`，2/2 Golden恢复；`spawn/ready/total=4,958/4,975/77,721 ms`，采样峰值RSS为`1,961,213,952`字节（约1.83 GiB），完成后PID 31916不存在。Git忽略报告Hash为`87e1c6c1f242e19a77fa8938e93a629357e6bdf67c4bf0f7c6a22bc0cc007d89`；
- 全范围Ruff lint、154个`app`源文件Mypy、编译、依赖、diff和Alembic门禁通过；329个文件格式正确，唯一差异仍是本步未修改的既有迁移测试。不能据此声称DOCX视觉文字、R-04发布门禁、34/34、全局Docling并发或OS硬内存配额已完成；详见[M2-22记录第23节](records/M2_22_CROSS_BORDER_RAG_EVALUATION_PLAN.md#23-m2-224r-02实施记录docling故障进程隔离2026-09-08)。

M2-22.4缺失证据诊断完成时：

- Git忽略的实际诊断报告`m2_parser_diagnostic_report_v1.json`绑定基线Run `m2-22.4-20260908t031430-a20e3f41`；8份问题文档、12条缺失均完成归因，结果为10条`route_selection_loss`、2条`ocr_extraction_loss`，0条评估归一化误差、0条模糊的部分/完全漏失；
- 10条外部缺失证据在Native全文与Golden声明页均`exact=true、token_recall=1.0`；基线Docling长文档字符数相对Native分别出现`71,011/225,544`、`31,959/117,373`、`34,221/139,843`等明显截断。若只做“保留原22条并取回这10条”的反事实组合可达32/34、外部14/14，但这不是生产修复后的重跑成绩；
- 图文DOCX两条Office视觉证据在Native和Docling中均`exact=false、relaxed=false、token_recall=0`，两路均147字符；源定义继续确认其中1条在页眉、1条在正文图片，因此既缺页眉提取也缺原位图片OCR；
- 初版连续Docling诊断在第三次超时后人工停止：复现120.063/120.031/120.016秒超时、OCR线程15秒不退出及后续`pypdfium2`失效页面句柄。最终诊断改为Native优先，只对Native不能归因的图文DOCX运行Docling，26.13秒完成且无持久化副作用；
- 新诊断专项与相邻Router/Runner共`16 passed`，完整单元`957 passed, 2 skipped`；全范围Ruff、格式、154个`app`源码Mypy、编译、依赖和diff检查通过。实际报告16,626字节且不含原文、Storage Key、tenant、口令、数据库URL或绝对路径。完整证据见[M2-22记录第20节](records/M2_22_CROSS_BORDER_RAG_EVALUATION_PLAN.md#20-m2-224-缺失证据诊断2026-09-08)。

M2-22.4完成时：

- 18份选定原件全部经公开上传/建文档API、隔离PostgreSQL/Storage、现有Parser Router和Canonical Artifact完成解析；路由为Native 5、Docling 11、Hybrid 2，畸形PDF由上传边界422拒绝；
- 严格Golden原文恢复为22/34（64.71%），合成组18/20、真实跨境组4/14、OCR字段2/4；解析延迟p50/p95/max为6,464/136,479/136,479 ms，进程峰值RSS约2.53 GiB。这是上游真实失败基线，不代表RAG质量完成；
- Runner专项`6 passed`；完整后端`1229 passed, 4 skipped, 1 failed`，唯一失败仍是既有上传Key写死2026/08的跨月测试；Ruff、153个`app`源码Mypy、编译、依赖、格式、Alembic和diff检查通过；
- 评估租户和对象清理为0，正式基线恢复为10 files/documents/versions、9 ACL、10个pending版本与10个upload对象，M1可售125。实际安全报告保存在Git忽略的本地reports目录；完整证据见[M2-22记录第19节](records/M2_22_CROSS_BORDER_RAG_EVALUATION_PLAN.md#19-m2-224-实施记录真实摄取parserocr和基线恢复2026-09-08)。

M2-22.2完成时：

- 8份欧盟官方核心PDF完成真实下载：VAT/OSS 3份、低价值包裹/退运2份、GPSR 1份、Safety Gate年报发布材料与单条风险通报2份；raw和processed各8份、各`5,152,421`字节，逐份SHA-256一致；文件复核为275页、未加密且都有可提取文本；
- Manifest把上述8份记为`verified + allowed_no_redistribution`并记录版本、大小、Hash、安全相对路径和`identity_copy@m2-eval-transform-v1`；3个全量诊断候选继续`planned + pending_review + download_allowed=false`，总下载预算收紧至59 MiB；本地原件/派生文件位于Git忽略目录；
- 新下载合同和既有评估合同合并`91 passed`；完整单元`943 passed, 2 skipped`；Ruff lint、3个本步Python文件格式、151个`app`源文件Mypy、编译、依赖和`git diff --check`通过；全范围格式仍只报告未修改迁移测试的一处既有差异；
- 本步没有创建Smoke/Golden、连接数据库或Storage、运行Parser/Chunk/检索/Reranker/Agent/Ragas，因此没有质量分数。详细RED/GREEN、来源与文件Hash见[M2-22记录第17节](records/M2_22_CROSS_BORDER_RAG_EVALUATION_PLAN.md#17-2026-09-07m2-222-受控下载hash校验和确定性转换)。

M2-22.1完成时：

- 评估合同聚焦测试`79 passed`，指定Schema/Context/结构感知Chunk相邻回归`57 passed`，合并`136 passed`；完整单元`931 passed, 2 skipped`；
- `ruff check app tests scripts migrations`、本步格式、151个`app`源文件Mypy、编译与`git diff --check`通过；全范围格式检查仍只报告未修改的既有迁移测试一处换行差异；
- 11个来源均为`planned + pending_review + download_allowed=false`，实际大小、Hash、路径和转换字段为空，外部原始预算累计180 MiB；
- 本步没有下载、数据库/Storage访问、RAG/Ragas运行或生产参数变更，因此没有任何M2-22质量分数。完整RED/GREEN和边界见[M2-22记录第16节](records/M2_22_CROSS_BORDER_RAG_EVALUATION_PLAN.md#16-2026-09-07m2-221-评估合同来源-manifest-和磁盘门禁)。

M2-21.12及整个M2-21完成时：

- Supervisor在不增加图节点的前提下，只对依赖已满足、Worker不同且能力只读的任务最多2路并发；模型仍逐任务产生一个Action/Handoff。公开G4实际让Business/Knowledge两个真实Worker在Provider会合点重叠，并验证共享根Run/Trace、不同预算引用、独立ToolCall子Run归属和按计划稳定合并；并发上限1会退回顺序；
- G0～G7均映射到真实可执行测试；包含三种读取角色、ACL、Prompt注入、循环/超时、Provider/数据库/Storage/Reranker故障、Evidence和资源边界的选定矩阵`150 passed`，最终聚焦回归`32 passed`；
- 完整单元`852 passed, 2 skipped`；完整integration为`275 passed, 2 skipped, 1 failed`，唯一失败仍是范围外既有跨月文档解析用例；显式真实BGE-M3离线检索Smoke `1 passed`且基线恢复，真实Agent Qwen Smoke因本机无Key为`1 skipped`，不冒充通过；
- Ruff lint、本步8个代码/测试文件格式、150个`app`源文件Mypy、编译、依赖、`git diff --check`和Alembic current/heads/check通过；全范围格式仍只命中未修改迁移测试1处既有差异。Alembic保持`20260905_0011 (head)`且无漂移；
- 全量后运行既有三个幂等Seed入口，恢复10 files/documents/versions、9 ACL、10个parse/index pending、零运行/检索发布数据、Storage 10 uploads和德国仓可售125。完整证据见[M2-21记录第33节](records/M2_21_ENGINEERED_MULTI_AGENT_PLAN.md#33-2026-09-07m2-2112-独立只读-worker-有界并行与-g0g7-收口矩阵)。

M2-21.11 完成时：

- 最多8条近期消息、2000字符安全摘要、16个请求ID、4次恢复和1次Re-plan均为严格Checkpoint状态；密钥赋值、SQL、路径和Traceback按已覆盖规则脱敏，模型公开投影不含身份、权限、预算或消息UUID；
- 公开API实际验证`waiting_user`后同一根Run恢复，Checkpoint版本为初始/等待/领取/完成`[1,2,3,4]`；第一次澄清请求在后续完成后仍精确重放第一次响应；重复ID不新增Run/消息，换内容复用返回409；恢复前撤权、重复重放撤权及Tool后最终保存前撤权均返回403且最新状态清空引用；
- 相邻单元`79 passed`，公开API`20 passed`，M1 API/持久化/两个Worker选定集成`31 passed`，完整单元`848 passed, 2 skipped`；完整integration为`270 passed, 2 skipped, 1 failed`，唯一失败仍是范围外既有文档解析用例；
- Ruff lint、本步文件格式、150个`app`源文件Mypy、编译、依赖、`git diff --check`和Alembic current/heads/check通过；全范围格式仍只命中未修改的既有迁移测试1处差异。没有新Model或迁移，也未运行真实Qwen/BGE、并行、浏览器或完整G0～G7矩阵。完整证据见[M2-21记录第32节](records/M2_21_ENGINEERED_MULTI_AGENT_PLAN.md#32-2026-09-07m2-2111-有界记忆澄清恢复重新获权与重复提交保护)。

M2-21.10 完成时：

- 公开消息POST只依赖`AgentGateway`，静态门禁确认路由不再包含`InventoryQueryAgent`、`InventoryQueryInput`或旧M1 Registry构造；同一真实HTTP入口已覆盖L0、Business单Tool、Knowledge单Tool、两个真实Worker和允许的部分成功，并验证根/子Run、子Run ToolCall、任务板、Checkpoint和答案Evidence；
- 本步聚焦28项、公开API文件14项、关键相邻单元100项、选定真实集成26项通过；完整单元为`842 passed, 2 skipped`；完整integration为`264 passed, 2 skipped, 1 failed`，唯一失败仍是范围外既有文档解析用例，未越界修复或掩盖；
- 正式收尾时Docker Desktop停机导致14个API用例在Seed阶段连接5433超时；恢复既有PostgreSQL容器为healthy后，同一收口矩阵为`58 passed in 19.62s`，没有删除或重建数据卷；
- `ruff check app tests`、19个本步文件格式、149个`app`源文件Mypy和`git diff --check`通过；全范围格式检查仍只命中未修改的既有迁移测试1处差异。能证明唯一公开执行入口和实际持久化主路径，不证明跨请求恢复、Re-plan、并行、完整G0～G7、前端展示或真实Qwen生产质量。完整证据见[M2-21记录第31节](records/M2_21_ENGINEERED_MULTI_AGENT_PLAN.md#31-2026-09-07m2-2110-唯一-agent-gateway公开-api-迁移与持久化主路径接线)。

M2-21.9 完成时：

- 父子`AgentRun`、共享`agent_tasks/dependencies`任务板、不可变`agent_checkpoints`和`agent_answer_evidences`已通过真实PostgreSQL Service/迁移测试；任务缺失依赖、自依赖和循环、任务/Checkpoint陈旧版本、Checkpoint篡改及跨tenant/user/thread恢复均被拒绝；
- 指定合同、M1库存Graph、Context、公共Schema、Worker Runtime及本步迁移/Service相邻回归`94 passed`；完整单元测试`840 passed, 2 skipped`；
- 完整integration首次暴露并修复本步旧迁移兼容问题；修复后排除唯一既有范围外文档解析失败的结果为`259 passed, 2 skipped, 1 deselected`，对应旧迁移回放与本步聚焦最终`15 passed`；
- `ruff check app tests scripts migrations`通过，本步文件格式正确，148个`app`源文件Mypy、编译、依赖、`git diff --check`和Alembic检查通过；全正式范围格式检查仍只命中未修改的既有迁移测试1处差异；
- Alembic current/heads均为`20260905_0011 (head)`且无Metadata漂移，空数据upgrade/downgrade实测通过。能证明持久化层合同和数据库约束，不证明公开API或现有Graph/Worker已完成接线、跨请求恢复或并行。完整证据见[M2-21记录第30节](records/M2_21_ENGINEERED_MULTI_AGENT_PLAN.md#30-2026-09-05m2-219-父子run任务板checkpoint与答案evidence持久化)。

M2-21.8 完成时：

- Evidence/Citation、Qwen Provider、既有Provider和Supervisor Graph聚焦回归`50 passed`；两个真实Worker的选定相邻集成`21 passed`；完整单元测试`834 passed, 2 skipped`；
- 显式真实Qwen Smoke为`1 passed`，覆盖单Worker计划、Supervisor委派、Handoff公开上下文、Business行动选择、Business+Knowledge计划和合成Evidence带`[E1]`回答；Smoke只提出Action且回答使用合成Observation，未执行真实Tool整链；
- `ruff check app tests scripts`通过，14个本步文件格式正确，146个`app`源文件Mypy、编译、依赖和`git diff --check`通过；全正式范围格式检查仍只命中未由本步修改的既有迁移测试1处格式差异；
- 完整集成为`256 passed, 2 skipped, 1 failed`，唯一范围外失败是文档解析测试删除上传后预期`DocumentParsingError`但未抛出，隔离复跑仍失败。本步没有修改对应索引Service，不能声称完整integration全绿；
- 能证明严格Qwen结构边界、Worker/Capability归属、参数复验、Handoff不可改写、错误脱敏及Observation支持的稳定Citation映射；不能证明生产模型质量、真实Qwen+Tool端到端、事实充分性、持久化、API、记忆或并行。完整证据见[M2-21记录第29节](records/M2_21_ENGINEERED_MULTI_AGENT_PLAN.md#29-2026-09-05m2-218-严格-qwen-与统一证据回答)。

M2-21.7 完成时：

- Knowledge Worker、Capability状态、Supervisor部分成功与真实M2 Tool聚焦测试`40 passed`；两个真实Worker及M1/M2知识Tool的选定PostgreSQL/pgvector/Storage相邻集成`48 passed`；
- 完整单元测试`812 passed, 2 skipped`；
- `ruff check app tests scripts`通过，143个`app`源文件Mypy、编译、依赖和`git diff --check`通过；全正式范围格式检查仍只发现未由本步修改的`tests/integration/test_document_chunk_set_migration.py`有1处既有格式差异，本步没有越界改写；
- 真实矩阵能证明三个知识Tool、无证据、ACL/软删除/旧active、顺序`Business → Knowledge`、稳定Evidence/Artifact合并和`allows_partial`失败收口；测试仍使用确定性Provider，L2回滚型夹具使用内联Invoker接缝，Knowledge搜索另行通过真实Worker Runtime验证。不能证明真实Qwen、统一Citation忠实性、父子Run持久化、API、记忆或并行。完整证据见[M2-21记录第28节](records/M2_21_ENGINEERED_MULTI_AGENT_PLAN.md#28-2026-09-05m2-217-knowledge-worker-与顺序双-worker-l2)。

M2-21.6 完成时：

- Business Worker、Capability状态与真实PostgreSQL聚焦矩阵`26 passed`；M2-21.1至.6、Agent Tool、Context、公共Schema、M1库存Graph、树形预算和Worker Runtime指定相邻单元回归`145 passed`；
- 新Business链加现有M1真实Agent Tool、库存Graph和公开M1 API的PostgreSQL相邻集成`22 passed`；只规格/精确库存/组合/FR越权的ToolCall数量分别为1/1/2/1，Evidence为0/1/1/0；
- 完整单元测试`803 passed, 2 skipped`；
- `ruff check app tests scripts`通过，本步7个代码测试文件格式正确，142个`app`源文件Mypy、编译、依赖和`git diff --check`通过；
- 全正式范围格式检查仍只发现未由本步修改的`tests/integration/test_document_chunk_set_migration.py`有1处既有格式差异，本步没有越界改写；
- 本步使用确定性测试Provider和真实PostgreSQL/M1合成Seed，能证明第一条Business L1执行链与权限/Evidence/预算，不能证明真实Qwen语义质量、Knowledge Worker、统一引用、父子Run持久化或公开API迁移。完整证据见[M2-21记录第27节](records/M2_21_ENGINEERED_MULTI_AGENT_PLAN.md#27-2026-09-05m2-216-有界-business-data-worker-与首条真实-l1-纵向链)。

M2-21.5 完成时：

- Worker Runtime/树形预算/Harness适配聚焦测试`20 passed`，与M2-21.1至.4、现有Agent Tool、Context、公共Schema、M1预算/库存Graph及Harness Trace的指定相邻回归合计`145 passed`；
- 完整单元测试`790 passed, 2 skipped`；
- `ruff check app tests scripts`通过，13个本步新增/修改代码测试文件格式正确，140个`app`源文件Mypy、编译、依赖和`git diff --check`通过；
- 全正式范围格式检查仍只发现未由本步修改的`tests/integration/test_document_chunk_set_migration.py`有1处既有格式差异，本步没有越界改写；
- 本步用SQLite内存库验证每次Worker独立Session、显式事务/savepoint提交与回滚；没有运行真实PostgreSQL、Tool、Storage、模型网络、迁移、配置或Seed，M2-20真实数据基线不变。完整证据见[M2-21记录第26节](records/M2_21_ENGINEERED_MULTI_AGENT_PLAN.md#26-2026-09-05m2-215-worker-runtime树形预算终止管理与-harness-适配)。

M2-21.4 完成时：

- 最小Supervisor聚焦测试`11 passed`，与M2-21.1至.3、Agent Tool、Context、公共Schema和M1库存Graph的相邻回归合计`112 passed`；
- 完整单元测试`770 passed, 2 skipped`；
- `ruff check app tests scripts`通过，六个本步新增/修改代码测试文件格式正确，132个`app`源文件Mypy、编译和依赖检查通过；
- 全正式范围格式检查仍只发现未由本步修改的`tests/integration/test_document_chunk_set_migration.py`有1处既有格式差异，本步没有越界改写；
- 额外根目录Ruff检查仍命中旧原型目录的既有质量欠债：`ruff check . --statistics`为98项、根格式检查为27个文件；本步正式范围通过且没有越界批量修复；
- 本步没有数据库、Storage、模型网络、迁移、配置或Seed行为；完整证据见[M2-21记录第25节](records/M2_21_ENGINEERED_MULTI_AGENT_PLAN.md#25-2026-09-05m2-214-最小-supervisor-langgraph-与-fake-worker-闭环)。

M2-21.3 完成时：

- Agent Provider聚焦测试`16 passed`，与M2-21.1/.2、现有M1 Mock/Qwen Provider、库存Graph、Agent Tool、Context和公共Schema相邻回归合计`129 passed`；
- 完整单元测试`759 passed, 2 skipped`；
- `ruff check app tests scripts`通过，六个本步新增/修改代码测试文件格式正确，130个`app`源文件Mypy、编译和依赖检查通过；
- 全正式范围格式检查仍只发现未由本步修改的`tests/integration/test_document_chunk_set_migration.py`有1处既有格式差异，本步没有越界改写；
- 本步没有数据库、Storage、模型网络、迁移、配置或Seed行为；完整证据见[M2-21记录第24节](records/M2_21_ENGINEERED_MULTI_AGENT_PLAN.md#24-2026-09-05m2-213-agent-provider-协议与确定性-mock)。

M2-21.2 完成时：

- Capability聚焦测试`12 passed`，与M2-21.1、Agent Tool、文件/Evidence Tool及权限合同相邻回归合计`61 passed`；
- 完整单元测试`743 passed, 2 skipped`；
- `ruff check app tests scripts`通过，六个本步新增文件格式正确，127个`app`源文件Mypy、编译和依赖检查通过；
- 全正式范围格式检查仍只发现未由本步修改的`tests/integration/test_document_chunk_set_migration.py`有1处既有格式差异，本步没有越界改写；
- 本步没有数据库、Storage、模型、迁移或Seed行为；完整证据见[M2-21记录第23节](records/M2_21_ENGINEERED_MULTI_AGENT_PLAN.md#23-2026-09-05m2-212-capability-catalogresolver-与-agent-definition)。

M2-21.1 完成时：

- 新合同聚焦测试`31 passed`，与M1 Tool、Context、库存Graph和公共Schema相邻回归合计`73 passed`；
- 完整单元测试`731 passed, 2 skipped`；
- `ruff check app tests scripts`通过，四个本步新增文件格式正确，122个`app`源文件Mypy、编译和依赖检查通过；
- 全正式范围格式检查另发现未由本步修改的`tests/integration/test_document_chunk_set_migration.py`有1处既有格式差异，本步没有越界改写；
- 本步没有数据库、Storage、模型、迁移或Seed行为；完整证据见[M2-21记录第22节](records/M2_21_ENGINEERED_MULTI_AGENT_PLAN.md#22-2026-09-05m2-211-严格合同状态外壳与迁移验收样本)。

M2-20.6 收口时的实际结果：

- M2-20聚焦合同、Service、Tool与真实矩阵：`93 passed`；M1/M2相邻回归：`233 passed`；
- 排除既有跨月用例后：`949 passed, 2 skipped, 1 deselected`；
- 原样默认全量：`949 passed, 10 skipped, 1 failed`，唯一失败仍是既有跨月测试；
- Ruff、253文件格式、120个`app`源文件Mypy、编译、依赖和Alembic门禁通过；
- Alembic继续为`20260902_0010 (head)`且无漂移，本步没有新增迁移；
- 正式Seed已恢复为10 files / 10 documents / 10 versions / 9 ACL，索引、Context、Evidence、ToolContextLink、AgentRun和ToolCall均为0；
- Storage只有10个uploads，M1德国仓可售库存仍为125。

这些结果能证明两个读取Tool在三业务角色、owner/company owner/user/role/market ACL下通过同一真实Harness落到真实Service/Repository，撤权、软删除、旧active来源、解析/locator、Storage/Artifact和数据库故障均被安全处理并记录Trace；不能证明M2-21多Agent策略、真实Qwen/BGE延迟、公开聊天Agent Gateway迁移或前端。

## 9. 下一步和记录规则

M2-20已经完成、验证并收口；M2-21十二步和M2-22.1至M2-22.6也已完成。M2-22.6已经补齐筛出配置的Ragas语义评分、失败分类、跨重建差异、清理和回归；外部欠费导致的缺失值保持可见，不影响本步按真实结果收口，也不能表述成34题全量质量通过。用户已要求进入M2-22.7并先同步文档；五步详细方案已经写入M2-22过程记录，当前等待用户确认，确认后只实施M2-22.7.1。已确认的远期顺序仍是RAG分层评估完成并复核后 → M2-22.8R意图识别与执行分流 → M2-22.9最终Agent轨迹评估 → M2-22.10收口。

后续记录方式：

- 本入口只更新当前状态、步骤索引、有效关键决策、风险和下一动作；
- 详细方案、修改文件、TDD过程、验证数字、能证明/不能证明和排查记录写入对应 `records/` 文件；
- 同一能力继续追加到已有记录；进入新的能力步骤时再创建新记录文件；
- 不把逐次测试流水账重复粘贴到 `docs/PROJECT_PROGRESS.md`；总看板只保留里程碑摘要和链接；
- 未验证的工作不得标记为已完成，代码变化导致旧验证失效时必须在对应记录中注明。
