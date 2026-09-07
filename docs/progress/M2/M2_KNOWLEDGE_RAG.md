# M2：知识库垂直切片

> 本文件是 M2 的唯一必读入口，只保存当前状态、关键决策、步骤索引、风险和下一动作。
> 完整方案、实施日志和验证证据保存在 [`records/`](records/) 中，开始具体任务时按需读取。
> 最近更新：2026-09-07

## 1. 当前状态

| 项目 | 当前内容 |
|---|---|
| 阶段状态 | 进行中 |
| 已完成 | M2-01 至 M2-20；M2-21十二步已全部完成，包含严格合同、两个真实Worker、Qwen/统一引用、持久化、公开Gateway、跨请求恢复、独立只读Worker有界并行和G0～G7收口矩阵 |
| 当前停止点 | M2-21.12及整个M2-21已完成；尚未授权开始M2-22最小RAG评估集和Runner |
| 下一动作 | 等待用户确认理解M2-21收口结果并单独授权M2-22；不得自动实现评估Runner、前端或后续能力 |
| 尚未开始 | M2-22至M2-24、前端知识问答和M2阶段最终评估/演示收口 |
| 技术阻塞 | 无硬阻塞；存在性能和上游质量边界，见第 7 节 |

M2-20.1至M2-20.6已经全部完成并验证。M2-21十二步于2026-09-07全部完成：在共同合同、能力目录、Provider/Mock、五节点Supervisor、通用Worker Runtime、两个真实Worker、严格Qwen、统一引用、PostgreSQL持久化、唯一公开Gateway和跨请求恢复之上，独立只读且属于不同Worker的任务现在最多2路并发；真实公开G4验证了两个子Run重叠、独立预算/Session/Trace/ToolCall归属和稳定合并，G0～G7均已映射到可执行测试。当前停止等待M2-22单独授权。

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

仍未接通的是M2-22评估Runner、M2-23前端引用展示和M2-24最终演示/阶段收口。

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

### 7.2 当前风险与边界

| 风险或边界 | 当前事实 | 优先排查方向 |
|---|---|---|
| Reranker CPU 延迟 | 约 15 个候选的本机 p50/p95 约 6.70/7.24 秒 | 候选裁剪、GPU、批处理或有证据支持的路由策略 |
| 图文 DOCX | 图片文字事实级定位仍只有 2/20 | Docling/Office视觉文字融合和Canonical定位 |
| 事实级 Locator | 当前正式复杂语料约 16/20 | Parser Adapter、表格/图片定位和Golden边界 |
| 既有跨月测试 | 默认全量唯一失败来自上传 Key 写死 `2026/08` | 修复测试时间依赖，不放宽生产Storage规则 |
| 数据库夹具顺序耦合 | 人工改变部分固定UUID测试顺序可触发污染 | 强化测试隔离和唯一数据身份 |
| 规模与并发 | 当前只证明小型合成语料闭环 | M5再做负载、并发和更大规模评估 |
| Business商品规格无Evidence | M2-21.8明确不伪造引用；只规格可作为已观察结构化结果，但没有可引用Evidence | 后续若产品要求规格也强制引用，需先新增真实规格Evidence来源 |
| Qwen生产质量未收口 | M2-21.8代表性真实Smoke已通过；M2-21.12环境无Key而显式跳过复跑，仍未覆盖任意自然语言、真实Tool整链和负载 | M2-22/M5以版本化评估集验证规划、行动、参数、引用、延迟和预算 |
| 记忆与崩溃恢复边界 | 已完成有界脱敏短期记忆、澄清同根恢复、一次Re-plan和撤权重验；不是长期画像，未知状态进程崩溃后的`running`根当前返回409，不自动抢占 | M5评估长对话和恢复租约需求，不擅自扩成永久记忆 |
| 并发规模边界 | 当前只证明两个独立只读Worker在单进程事件循环内有界重叠、预算/Session/Trace隔离；同步Tool片段和高负载吞吐未做生产基准 | M5再做负载、多进程、背压和更大规模评估；写操作必须另行设计审批与冲突控制 |

## 8. 最近验证基线

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

M2-20已经完成、验证并收口；M2-21十二步也已全部完成，包含共同合同、能力目录、Provider/Mock、Supervisor、通用Worker Runtime、两个真实Worker、严格Qwen/统一引用、父子Run/任务板/Checkpoint、唯一公开Gateway、有界跨请求恢复，以及独立只读Worker最多2路并发和G0～G7收口矩阵。当前停止等待用户确认理解M2-21整体结果并单独授权M2-22最小RAG评估集和Runner；不得自动进入M2-22、M2-23、M2-24、M4或M5。

后续记录方式：

- 本入口只更新当前状态、步骤索引、有效关键决策、风险和下一动作；
- 详细方案、修改文件、TDD过程、验证数字、能证明/不能证明和排查记录写入对应 `records/` 文件；
- 同一能力继续追加到已有记录；进入新的能力步骤时再创建新记录文件；
- 不把逐次测试流水账重复粘贴到 `docs/PROJECT_PROGRESS.md`；总看板只保留里程碑摘要和链接；
- 未验证的工作不得标记为已完成，代码变化导致旧验证失效时必须在对应记录中注明。
