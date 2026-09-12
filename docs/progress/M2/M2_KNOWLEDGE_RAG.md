# M2：知识库垂直切片

> 本文件是M2的唯一必读入口，只保存当前状态、能力地图、有效决策、活动风险、步骤索引和下一动作。
> 完整方案、实施日志和验证证据保存在[`records/`](records/)中，开始具体任务时按需读取。
> 最近更新：2026-09-12

## 1. 当前状态

| 项目 | 当前内容 |
|---|---|
| 阶段状态 | 进行中 |
| 已完成 | M2-01至M2-21；M2-22.1至M2-22.7.5、M2-22.8.1至.8.6及M2-22.8.7-A/B/C/D/F/G/H/I/L/M/O/Q；M仅有界单题诊断完成，B/D为已由F撤销的历史实验，K旧补评已撤销 |
| 当前停止点 | T（A1）本地完成：正文允许重复引用，来源清单按首次出现顺序唯一登记；Prompt/共享校验/独立服务/本地指标已对齐，见第82节。历史S40题报告不改写 |
| 下一动作 | A1收口后停止，等待用户评判其余B/C/D/E疑点；不自动真实调用。T聚焦72/相邻213/完整单元1283 passed、2 skipped，静态门禁通过，新增模型费用0 |
| 已知质量限制 | M2-22.7.5真实跨境Reranker Top5为12/14，未过90%门禁；三条漏召回已定位，用户接受暂缓修复，但失败结论和Bad Case继续保留 |
| 技术阻塞 | 40题已覆盖但质量未全通过；38引用当前获权有效版本，不能把自动safety_information_leakage直接当旧版本泄露证据。11检索缺失、重复标签、答案完整性及评分问题保留 |
| 后续顺序 | 完成M2-22.8并复核 → M2-22.8R意图识别与执行分流 → M2-22.9最终Agent轨迹评估 → M2-23前端 → M2-24收口 |

## 2. 新窗口阅读顺序

1. 先读[`docs/PROJECT_PROGRESS.md`](../../PROJECT_PROGRESS.md)，确认全项目阶段和跨阶段问题；
2. 再读本文件，确认M2停止点、活动风险和下一动作；
3. 开始具体步骤前，按第3节只读相关能力记录及直接上游；
4. 只有排查历史回归、设计冲突或验证依据时，才继续展开其他记录；
5. 代码事实与记录冲突时，以当前代码和实际验证为准，并同步修正文档。

## 3. M2过程记录目录

### 3.1 主能力记录

| 范围 | 内容 | 何时读取 |
|---|---|---|
| [M2文档治理](records/M2_DOCUMENT_GOVERNANCE.md) | 文档拆分、迁移验证和长期维护规则 | 整理入口、过程记录或链接时 |
| [M2原始阶段方案](records/M2_00_STAGE_PLAN.md) | M2总体目标、24步原始计划、完成标准和初始风险 | 核对M2原始边界时 |
| [M2-01至06](records/M2_01_06_FOUNDATION.md) | 配置、pgvector、Storage、文件/文档模型、Repository和文件API | 修改基础设施、上传或权限时 |
| [M2-07至11](records/M2_07_11_DOCUMENT_PARSING.md) | Native/Docling解析、Canonical Artifact和解析发布 | 修改Parser、OCR或解析产物时 |
| [M2-12](records/M2_12_CHUNKING.md) | 结构感知分块、Chunk Set和Chunk Artifact | 修改分块时 |
| [M2-13至15](records/M2_13_15_INDEXING.md) | FTS/vector、BGE-M3、Index Set和原子激活 | 修改Embedding或索引时 |
| [M2-16](records/M2_16_RETRIEVAL.md) | 权限前置Dense/Lexical/Hybrid/RRF检索 | 修改召回或融合时 |
| [M2-17](records/M2_17_RERANKER.md) | Reranker合同、Provider、Service和资源基准 | 修改精排时 |
| [M2-18](records/M2_18_CONTEXT_EVIDENCE.md) | Context、Evidence、持久化和引用验证 | 修改上下文或引用链时 |
| [M2-19](records/M2_19_SEARCH_KNOWLEDGE_TOOL.md) | `search_knowledge` Tool和Harness执行链 | 修改知识检索Tool时 |
| [M2-20](records/M2_20_FILE_EVIDENCE_TOOLS.md) | 文件与Evidence受控读取Tool | 修改文件读取或Evidence详情时 |
| [M2-21](records/M2_21_ENGINEERED_MULTI_AGENT_PLAN.md) | 多Agent合同、Worker、Gateway、持久化、恢复和并发 | 修改Agent主链时 |
| [M2-22导航](records/M2_22_CROSS_BORDER_RAG_EVALUATION_PLAN.md) | M2-22方案与五组能力记录的短目录 | 实施或排查任一M2-22.x时先读 |
| [架构学习图](records/M2_ARCHITECTURE_LEARNING_MAPS.md) | 当前框架和调用链学习图 | 用图理解架构时 |

### 3.2 M2-22按能力拆分

| 范围 | 记录 |
|---|---|
| 原始阶段方案与门禁 | [M2_22_00_STAGE_PLAN.md](records/M2_22_00_STAGE_PLAN.md) |
| M2-22.1至.4 数据、Golden、Parser/OCR | [M2_22_01_04_DATA_AND_PARSER.md](records/M2_22_01_04_DATA_AND_PARSER.md) |
| M2-22.5 Chunk质量与标题/Locator修复 | [M2_22_05_CHUNK_EVALUATION.md](records/M2_22_05_CHUNK_EVALUATION.md) |
| M2-22.6 检索矩阵与Ragas | [M2_22_06_RETRIEVAL_EVALUATION.md](records/M2_22_06_RETRIEVAL_EVALUATION.md) |
| M2-22.7 Reranker、Context和漏召回诊断 | [M2_22_07_RERANKER_CONTEXT.md](records/M2_22_07_RERANKER_CONTEXT.md) |
| M2-22.8 回答、Citation、拒答和Provider | [M2_22_08_ANSWER_CITATION.md](records/M2_22_08_ANSWER_CITATION.md) |

迁移前的总看板和M2入口原文保存在[冻结快照](records/M2_DOCUMENTATION_MIGRATION_SNAPSHOT_2026-09-11.md)中；它只用于完整性追溯，不再追加日志。

## 4. M2目标与边界

M2要证明的完整闭环是：用户上传一份明确标注为合成演示数据的知识文件，系统安全保存、解析、分块和索引；用户提问时，系统在当前租户和文档权限范围内检索、重排、构造Context、保存Evidence，并让Agent输出可验证引用。

当前明确不做：

- 不使用RAGFlow，不引入MCP；
- 不接真实Amazon SP-API、ERP或生产对象存储；
- 不允许模型直接访问数据库、Storage Key或绕过Tool/Harness权限；
- 不把小型语料、有限并发和单机资源测试描述成生产规模；
- 未经当前小步骤的单独确认，不提前实现后续Provider、前端或研究能力。

## 5. 当前能力地图

### 5.1 生产知识链

```text
用户 / CurrentUser
→ 文件API与Schema
→ 文件、文档Service
→ LocalStorage + PostgreSQL
→ Parser Router（Native / Docling / Hybrid）
→ Canonical Parsed Artifact
→ 结构感知Chunk Artifact
→ BGE-M3 + FTS + pgvector Index Set
→ 权限前置Dense / Lexical → RRF
→ BGE-Reranker
→ Context Builder重新获权
→ ContextArtifact + Evidence
→ Tool Registry + Harness
→ Knowledge Worker / Agent Gateway
→ Citation Validator → 聊天响应
```

### 5.2 当前回答评估链

```text
固定40题Cohort
→ 固定18文档 / 779 Chunk
→ Dense10 + Lexical10 + RRF60
→ BGE-Reranker Top5
→ neighbor 1 + 3000 Token Context候选
→ 回答/Citation/拒答确定性指标
→ Fake Answer Runner + Run内缓存
→ 逐题Trace Hash + 公开脱敏报告
```

当前`.8.3`已把固定40题全部送入真实公开API、Gateway、Knowledge Worker、Harness、Tool、PostgreSQL/pgvector和本地BGE；生产知识查询直接从数据库Chunk取回正文，Storage只在评估准备阶段只读构建Golden映射。40/40 API、Tool和回答收口通过，Tool为1016至5703ms，6条安全题无Evidence泄露，临时运行数据清零；回答端仍是Fake，质量门禁保持非数值。

## 6. 步骤状态索引

| 步骤 | 状态 | 结果摘要 | 详细记录 |
|---|---|---|---|
| M2-01至06 | 已完成 | 基础配置、pgvector、Storage、数据模型、Repository和文件API | [基础记录](records/M2_01_06_FOUNDATION.md) |
| M2-07至11 | 已完成 | 四类Native Parser、Docling双路径、Canonical Artifact和解析发布 | [解析记录](records/M2_07_11_DOCUMENT_PARSING.md) |
| M2-12 | 已完成 | 结构感知分块、Chunk Set和版本化Artifact | [分块记录](records/M2_12_CHUNKING.md) |
| M2-13至15 | 已完成 | FTS/vector、BGE-M3、幂等索引和原子激活 | [索引记录](records/M2_13_15_INDEXING.md) |
| M2-16 | 已完成 | 权限前置Dense/Lexical/Hybrid/RRF检索闭环 | [检索记录](records/M2_16_RETRIEVAL.md) |
| M2-17 | 已完成 | BGE-Reranker Provider、Service和验收 | [重排记录](records/M2_17_RERANKER.md) |
| M2-18 | 已完成 | Context、Evidence、原子持久化和引用验证 | [Context记录](records/M2_18_CONTEXT_EVIDENCE.md) |
| M2-19 | 已完成 | `search_knowledge` Tool与Harness权限/故障矩阵 | [M2-19记录](records/M2_19_SEARCH_KNOWLEDGE_TOOL.md) |
| M2-20 | 已完成 | 两个文件/Evidence受控读取Tool | [M2-20记录](records/M2_20_FILE_EVIDENCE_TOOLS.md) |
| M2-21 | 已完成 | 多Agent、公开Gateway、持久化、恢复和最多2路只读并发 | [M2-21记录](records/M2_21_ENGINEERED_MULTI_AGENT_PLAN.md) |
| M2-22.1至.4 | 已完成 | 来源、40题Golden、真实摄取、Parser/OCR和质量门禁 | [数据与Parser记录](records/M2_22_01_04_DATA_AND_PARSER.md) |
| M2-22.5 | 已完成 | Chunk质量矩阵、标题元数据和Locator收口 | [Chunk记录](records/M2_22_05_CHUNK_EVALUATION.md) |
| M2-22.6 | 已完成 | 检索矩阵与Ragas检索语义评分 | [Retrieval记录](records/M2_22_06_RETRIEVAL_EVALUATION.md) |
| M2-22.7 | 已完成 | Reranker/Context矩阵和漏召回只读诊断；质量门禁False被保留 | [Reranker/Context记录](records/M2_22_07_RERANKER_CONTEXT.md) |
| M2-22.8.1至.8.2 | 已完成 | 回答指标合同、Fake Runner、缓存和安全报告 | [Answer/Citation记录](records/M2_22_08_ANSWER_CITATION.md) |
| M2-22.8.3 | 已完成 | 固定40题真实Gateway/Fake Answer全链40/40通过；Tool 1016至5703ms，安全题零泄露，临时数据清零；生产默认仍为4+8 | [Answer/Citation第58节](records/M2_22_08_ANSWER_CITATION.md#58-m2-2283固定40题真实gateway收口2026-09-11) |
| M2-22.8.4-A | 已完成 | 最终Qwen请求移除Evidence正文的`business_result`副本；无Evidence结果继续保留；未做语义去重 | [Answer/Citation第59节](records/M2_22_08_ANSWER_CITATION.md#59-m2-2284-a回答provider输入单份evidence投影2026-09-11) |
| M2-22.8.4-B | 已完成 | 共享四角色核心；DeepSeek Responses严格Schema、关闭thinking、无Web Tool、显式配置和安全错误映射通过模拟HTTP验证 | [Answer/Citation第60节](records/M2_22_08_ANSWER_CITATION.md#60-m2-2284-b双provider共享核心与deepseek-responses适配2026-09-11) |
| M2-22.8.5 | 已完成 | DeepSeek真实Answer小样本4/4通过；765至1356ms，总计3482 tokens | [Answer/Citation第61节](records/M2_22_08_ANSWER_CITATION.md#61-m2-2285-deepseek真实answer小样本探针2026-09-11) |
| M2-22.8.6 | 已完成 | Ragas四项生成指标与DeepSeek Judge真实好/坏校准完成；18次调用共20170 tokens | [Answer/Citation第62节](records/M2_22_08_ANSWER_CITATION.md#62-m2-2286-ragas生成指标与deepseek-judge人工校准2026-09-11) |
| M2-22.8.7 | 进行中 | S四段固定40题现场已全部采集，35题API200/5题引用422；六安全题5通过/38失败，质量问题待确认修复，不等于里程碑验收通过 | [Answer/Citation第81节](records/M2_22_08_ANSWER_CITATION.md#81-m2-2287-s-单次40题答卷与分层质量基线方案2026-09-12) |
| M2-22.8.7-A | 已完成 | 真实34+6校准：安全错误Top-1最高`.4835`，而正常Golden低至`.0054`且可在第4/5名；拒绝6/6最多只剩21/34非空Context，阈值方案不可行且未接生产 | [Answer/Citation第63节](records/M2_22_08_ANSWER_CITATION.md#63-m2-2287真实预检故障与三信号证据门控校准2026-09-11) |
| M2-22.8.7-B | 已完成 | 历史实验：曾由Knowledge Worker选择Evidence子集；因存在误删正确Chunk风险，能力已由F撤销 | [Answer/Citation第64节](records/M2_22_08_ANSWER_CITATION.md#64-m2-2287-b-evidence可回答性门控方案与用户确认2026-09-11) |
| M2-22.8.7-C | 已完成 | 七类固定诊断与未知降级贯通Provider/Worker/LangGraph/Checkpoint/评估；API仍为通用422；完整单元`1189 passed, 2 skipped` | [Answer/Citation第65节](records/M2_22_08_ANSWER_CITATION.md#65-m2-2287-c-422安全分型诊断方案与用户确认2026-09-11) |
| M2-22.8.7-D | 已完成 | 历史实验：曾接回真实Provider选择0至8条Evidence；该当前能力和独立筛选用量已由F删除 | [Answer/Citation第66节](records/M2_22_08_ANSWER_CITATION.md#66-m2-2287-d-正式评估evidence筛选适配器对齐方案与用户确认2026-09-11) |
| M2-22.8.7-E | 受阻 | 旧架构历史运行：3次筛选+1次Answer、Judge 0次；失败证据保留，但不再代表当前调用链 | [Answer/Citation第67节](records/M2_22_08_ANSWER_CITATION.md#67-m2-2287-e-真实deepseek-evidence筛选小样本诊断方案与用户授权2026-09-11) |
| M2-22.8.7-F | 已完成 | 撤销中间LLM硬筛选；Worker和Supervisor保证全部候选上交，Answer正文仍单份；删除筛选调用/指标/CLI；完整单元`1194 passed, 2 skipped` | [Answer/Citation第68节](records/M2_22_08_ANSWER_CITATION.md#68-m2-2287-f-撤销knowledge-worker语义硬筛选方案与用户确认2026-09-11) |
| M2-22.8.7-G | 已完成 | 四类Answer拒答Few-shot与四类模型输出错误的一次修复完成；第二次调用计入预算、ResourceUsage和Provider统计；完整单元`1209 passed, 2 skipped`，未调用外部模型 | [Answer/Citation第69节](records/M2_22_08_ANSWER_CITATION.md#69-m2-2287-g-answer拒答few-shot与一次输出修复方案2026-09-11) |
| M2-22.8.7-H | 已完成 | 真实DeepSeek三题依次为`answered/no_evidence/partial`，引用`1/0/1`且partial只引用支持项；3次、3927 tokens、零修复，未调用Qwen/Judge | [Answer/Citation第70节](records/M2_22_08_ANSWER_CITATION.md#70-m2-2287-h-真实deepseek三题answer小样本2026-09-12) |
| M2-22.8.7-I | 已完成 | 正式报告接受每题1至2次Answer调用并拒绝第3次；三题/40题外部调用上限33/440，系统失败按题停机；完整单元`1214 passed, 2 skipped`，本地Gateway/Fake 40/40通过，外部调用0 | [Answer/Citation第71节](records/M2_22_08_ANSWER_CITATION.md#71-m2-2287-i-正式矩阵付费安全对齐2026-09-12) |
| M2-22.8.7-L | 已完成 | Judge白名单请求/响应/解析/评分诊断进入正式报告；不改变补评/停机/预算，完整单元`1241 passed, 2 skipped`，真实模型调用0 | [Answer/Citation第74节](records/M2_22_08_ANSWER_CITATION.md#74-m2-2287-l-judge本地白名单诊断2026-09-12) |
| M2-22.8.7-O | 已完成 | 辅助评分不阻断后续Answer，服务/预算不可用则后续评分跳过；报告v4分开业务与Ragas结论，完整单元`1251 passed, 2 skipped`，真实调用0 | [Answer/Citation第77节](records/M2_22_08_ANSWER_CITATION.md#77-m2-2287-o-ragas辅助评分不阻断问答评估2026-09-12) |
| M2-22.8.7-P | 受阻 | 真实业务22完成/1失败/17未执行；三次Judge评分失败后续问答继续，第23题Answer修复后仍citation_contract；209请求、379064 Token、临时数据归零 | [Answer/Citation第78节](records/M2_22_08_ANSWER_CITATION.md#78-m2-2287-p-辅助评分策略下真实40题评估2026-09-12) |
| M2-22.8.7-Q | 已完成 | 同次资料与实际答卷本地留存、引用失败具体原因；完整单元1267/2，真实调用0，旧答案无法恢复 | [第79节](records/M2_22_08_ANSWER_CITATION.md#79-m2-2287-q-同次评估现场证据留存2026-09-12) |
| M2-22.8R | 待开始 | 意图识别与执行分流 | [M2-22原始方案](records/M2_22_00_STAGE_PLAN.md) |
| M2-22.9至.10 | 待开始 | Agent轨迹评估与M2-22收口 | [M2-22原始方案](records/M2_22_00_STAGE_PLAN.md) |
| M2-23 | 待开始 | 最小前端上传、知识问答和引用展示 | [M2原始计划](records/M2_00_STAGE_PLAN.md) |
| M2-24 | 待开始 | 故障矩阵、演示和阶段收口 | [M2原始计划](records/M2_00_STAGE_PLAN.md) |

## 7. 当前有效决策

- PostgreSQL保存元数据、状态、ACL、Chunk、向量、Context和Evidence；LocalStorage保存上传文件与解析/分块Artifact；
- Native Parser负责普通文件快速路径，Docling只处理受控复杂文件；两者统一进入版本化Canonical Artifact；
- Chunk Set与Index Set身份分离：原文、Parser或Chunk配置变化才重切；Embedding/FTS变化只新建Index Set；查询参数变化两者都不重建；
- Dense和Lexical必须在排序前应用同一租户、ACL、软删除和active版本边界；Hybrid使用固定RRF；
- Reranker只能重排已获权候选；Context Builder不信任候选正文，必须重新获权和取回同代次Chunk；
- Context、Evidence和Tool关联使用确定性身份与事务保护；Citation输出前必须重新验证当前权限和Evidence身份；
- 日常回归默认使用Fake；真实BGE、Docling、Qwen、DeepSeek和外部Judge只能显式运行，失败不能伪造成分数；
- 固定评估语料为18文档、18 ChunkSet和779逻辑Chunk；M2-22.7.5选择Reranker Top5与neighbor 1 + 3000 Token作为后续回答评估候选；
- 三条漏召回不删题、不重切Chunk、不直接把depth改到50；用户接受暂缓修复，但12/14和门禁False继续公开保留；
- M2-22.8固定34条可回答和6条安全题；确定性Citation身份/Golden映射与Ragas Faithfulness、人工语义复核必须分栏；
- O起Ragas只辅助：评分失败不阻断后续问答，失败非数值且保留完成/失败/跳过数量；Judge服务或预算不可用时停止后续评分，不扩大请求上限。业务链失败仍停机，业务规则通过不等于回答语义全正确；
- 保留Qwen并新增DeepSeek，通过配置显式切换；两个Provider共享角色合同和Citation边界，但分别处理传输协议；
- DeepSeek使用Responses API `/responses`、`text.format=json_schema`、`reasoning.effort=none`且不授予服务端Tool；Qwen继续使用原Chat Completions方言；Provider暴露厂商、模型、API方言和共享Prompt Hash供后续报告审计；
- 最终回答Provider只通过`answer_evidence`接收已有Evidence的正文；对应`business_result`副本在Provider输入投影时移除，无Evidence的文件结果仍保留；Chunk语义去重暂缓；
- Reranker相关性门控先离线比较绝对下限、Top-1相对比例和低置信Gap；最多8个Anchor只是上限，不补位、不循环召回，Neighbor不计入有效Anchor数量；校准通过前不接生产链；
- Knowledge Worker不做语义硬筛选；检索返回的全部获权候选必须完整进入WorkerResult和Answer输入，Supervisor阻止漏交。真实空检索仍以`no_evidence`跳过Answer；Answer引用继续受Schema、Evidence ID和Citation合同约束；
- Answer共享Prompt包含answered、仅引用支持项、非空无答案和partial四类短合成示例；仅`model_json/model_schema/evidence_reference_contract/citation_contract`使用原问题、原Evidence顺序和原严格Schema修复一次，第二次调用必须先通过根预算并计入ResourceUsage；
- M2-22.8完成并复核后才实施意图分流：程序先处理高置信明确请求，只有不确定时才使用一次结构化模型决定意图、路径和参数。

## 8. 当前风险与验证基线

### 8.1 活动风险

| 风险 | 当前事实与排查方向 |
|---|---|
| `.8.7-P`真实Answer失败 | 前22题业务完成，第23题检索成功但Answer修复后仍citation_contract/API422；无法从脱敏记录确定具体标签错误。P已实际绕过三次Judge失败继续业务，停止来自独立Answer边界 |
| 本地Gateway 8秒门禁波动 | `.8.7-I`第一次显式40题Fake Answer回归有至少一题Tool超时，第二次相同运行40/40通过且Tool为1204至4797ms；不因偶发抖动放宽门禁，J步预检失败仍不得进入付费40题 |
| 真实修复成功未证明 | P第23题真实调用2次，第二次仍citation_contract；首次错误阶段与完整ResourceUsage快照未留。证明有界修复执行及Provider总量，不代表修复成功或所有错误分支真实验证 |
| `.8.7`真实预检未通过 | 正常题曾完成一次Answer/Judge但Faithfulness与Factual Correctness为0，后续正常题在Provider产生Token后被本地边界以422拒绝；安全题无受限Evidence泄露，但可能引用无关获权Evidence返回`partial`。固定40题正式报告不存在，禁止继续按完成描述 |
| 旧Evidence筛选小样本受阻 | `.8.7-E`保留为旧架构历史失败；由于中间筛选已由F撤销，不再继续细分或复测这条调用链 |
| 候选不等于答案证据 | 当前全部获权候选进入Answer以避免中间召回损失；回答后的逐句支持性验证尚未实现，非空无答案场景仍是下一步风险 |
| DeepSeek真实证明范围有限 | `.8.5`已证明4个合成Answer输入真实通过，但未经过Gateway、Tool或真实检索，也不证明40题质量、长Context、持续可用性或一般化安全性 |
| DeepSeek同模型评审偏差 | `.8.6`的Answer模型与Judge均为`deepseek-v4-flash`；好坏方向已真实校准，但报告必须保留`same_model_bias=true`，不能把自评分数当作独立最终结论 |
| Chunk语义近似重复 | `.8.4-A`只消除了同一Evidence的双通道重复，没有合并身份不同但语义相似的Chunk；后续若实施，必须先验证不会误删互补证据或降低Golden覆盖 |
| Agent证据包大小 | `.8.3`真实RED证明12段长Context可能超过Agent结构化JSON的16KB边界；当前只缩短给模型看的正文副本并保留12个Evidence身份，原始Context/Evidence不改。后续真实Provider需验证截断后的回答质量 |
| 跨语言召回缺失 | 三条Golden仍在Chunk中，Dense完整Golden名次33/42/39且Lexical缺失；后续若修复，优先独立评估查询扩展和文档内定位 |
| Context补回被误算成Reranker成功 | Top5 Anchor为31/34，最终Context总覆盖32/34；后续报告必须同时展示两者 |
| BGE显存边界 | BGE-M3/Reranker单独峰值约2179/2178 MiB，总和超过4 GiB；同进程轮流卸载后可用显存恢复约3257/3295 MiB。不能把隔离探针误写成双模型共同驻留或真实Gateway已GREEN |
| Fake Answer误读 | `.8.3`已证明真实Gateway、检索Context、Citation身份和清理接线，但Fake Answer仍不能证明Qwen/DeepSeek回答质量或语义支持 |
| 外部Provider/Judge不稳定 | Key、余额、网络、超时和框架错误都保留非数值；有效均值必须同时报告完成样本数 |
| 固定语料被测试清空 | 会重置schema的集成测试先运行，之后用幂等准备器恢复；查询实验不得重新解析和切块 |
| 当前规模有限 | 小型演示语料和最多2路只读并发不代表生产吞吐；M5再做负载和更大规模验证 |

### 8.2 当前可复核基线

| 能力 | 当前结果 | 完整证据 |
|---|---|---|
| Q同次现场留存 | RED7失败；聚焦163、最终相邻280、完整单元`1267 passed, 2 skipped`，静态门禁通过；实际资料/输入/两次输出/评分本地分离留存，真实调用0 | [第79节](records/M2_22_08_ANSWER_CITATION.md#79-m2-2287-q-同次评估现场证据留存2026-09-12) |
| S引用失败单题隔离 | RED2失败/16通过；聚焦91通过；完整单元`1277 passed, 2 skipped`，Ruff/Mypy/格式/编译通过。只改评估停止判断，不放宽生产引用校验；第三段真实27/28/34失败后均继续 | [第81节](records/M2_22_08_ANSWER_CITATION.md#81-m2-2287-s-单次40题答卷与分层质量基线方案2026-09-12) |
| T正文重复引用 | RED6失败/62通过；最终聚焦72、相邻213、完整单元1283/2；正文可重复，清单首现去重，未知/拒答/清单重复保护保留；5题10草稿离线标签检查通过，真实调用0 | [第82节](records/M2_22_08_ANSWER_CITATION.md#82-m2-2287-ta1允许正文重复引用同一来源仅登记一次2026-09-12) |
| P真实辅助评分策略 | 聚焦84；业务22完成/1失败/17未执行，Judge第5/8/18题失败后继续，21题进入评分；Answer24/Judge185、379064 Token，v4读回/Token/候选/清理与Hash核对通过，无代码变更 | [第78节](records/M2_22_08_ANSWER_CITATION.md#78-m2-2287-p-辅助评分策略下真实40题评估2026-09-12) |
| O辅助评分解耦 | 行为RED`16 failed, 29 passed`，40行循环RED`5 failed`；聚焦84、相邻179、完整单元`1251 passed, 2 skipped`，静态门禁通过，真实调用0；当前v4策略替代I/K/L的Judge停机旧规则 | [第77节](records/M2_22_08_ANSWER_CITATION.md#77-m2-2287-o-ragas辅助评分不阻断问答评估2026-09-12) |
| L本地Judge诊断 | RED`10 failed, 20 passed`；聚焦74、相邻196、完整单元`1241 passed, 2 skipped`；静态门禁通过，仅新增白名单观察，模型/预算/停机参数不变、真实调用0 | [第74节](records/M2_22_08_ANSWER_CITATION.md#74-m2-2287-l-judge本地白名单诊断2026-09-12) |
| K诊断前恢复 | 补评/继续矩阵/预算扩大已撤销；完整单元`1219 passed, 2 skipped`，Ruff/Mypy/格式/编译通过；仅11个目标文件变化，Answer与J报告指纹不变，真实调用0 | [第73节](records/M2_22_08_ANSWER_CITATION.md#73-m2-2287-k-未收口改动撤销与诊断前恢复2026-09-12) |
| 真实Gateway预检与正式矩阵 | 预检3/3通过；正式前2题完成、第3题Judge失败后停止37题；Answer 6次、Judge 36次、总79239 tokens、零修复，临时数据清零；`.8.7-J`受阻 | [第72节](records/M2_22_08_ANSWER_CITATION.md#72-m2-2287-j-真实gateway三题预检与固定40题受阻运行2026-09-12) |
| 正式矩阵付费安全对齐 | 一次修复计数、Answer/Judge请求硬限额、系统失败后续停机、安全题非空候选拒答和清理合同完成；RED`1 failed`，聚焦`37 passed`，相邻`138 passed`，完整单元`1214 passed, 2 skipped`；本地Gateway/Fake 40/40通过，外部调用0 | [第71节](records/M2_22_08_ANSWER_CITATION.md#71-m2-2287-i-正式矩阵付费安全对齐2026-09-12) |
| 真实DeepSeek三题Answer | 直接回答、非空无关Context拒答、部分回答全部通过；3次调用，输入3781/输出146/总3927 tokens，均未修复；相邻单元`32 passed` | [第70节](records/M2_22_08_ANSWER_CITATION.md#70-m2-2287-h-真实deepseek三题answer小样本2026-09-12) |
| Answer拒答Few-shot与一次输出修复 | RED`11 failed, 44 passed`；聚焦`61 passed`、相邻`221 passed`、完整单元`1209 passed, 2 skipped`；四类白名单最多修复一次且第二次计入预算/用量，外部调用0 | [第69节](records/M2_22_08_ANSWER_CITATION.md#69-m2-2287-g-answer拒答few-shot与一次输出修复方案2026-09-11) |
| 真实Evidence三题预检 | 正常题选1条并Answer成功；两条安全题零入答Evidence/零Answer但为`unknown_output_contract`；3次筛选+1次Answer、Judge 0次、基线恢复，状态受阻 | [第67节](records/M2_22_08_ANSWER_CITATION.md#67-m2-2287-e-真实deepseek-evidence筛选小样本诊断方案与用户授权2026-09-11) |
| 正式评估Evidence筛选适配器 | 固定首次检索后由真实Provider做一次0至8条选择，二次Tool/超过8条安全失败，零支持跳过Answer，三类用量分栏；完整单元`1196 passed, 2 skipped`，未调用外部Provider | [第66节](records/M2_22_08_ANSWER_CITATION.md#66-m2-2287-d-正式评估evidence筛选适配器对齐方案与用户确认2026-09-11) |
| Evidence可回答性门控 | Knowledge Worker仅上交有ID/原文支持的子集；伪造支持失败，零支持跳过Answer Provider，有效兄弟Worker仍可部分回答；完整单元`1181 passed, 2 skipped`，Mypy 173文件通过 | [第64节](records/M2_22_08_ANSWER_CITATION.md#64-m2-2287-b-evidence可回答性门控方案与用户确认2026-09-11) |
| Ragas生成指标与Judge校准 | 好答案四项`1.0/.8536/1.0/.9898`均高于坏答案`0/.4098/0/.4714`；DeepSeek Judge 18次共20170 tokens，`same_model_bias=true`；全量单元`1164 passed, 2 skipped` | [第62节](records/M2_22_08_ANSWER_CITATION.md#62-m2-2286-ragas生成指标与deepseek-judge人工校准2026-09-11) |
| DeepSeek真实Answer探针 | `deepseek-v4-flash`真实`/responses` 4/4通过；三个有证据样本各合法引用1条，无证据样本零引用；765至1356ms，总计3482 tokens | [第61节](records/M2_22_08_ANSWER_CITATION.md#61-m2-2285-deepseek真实answer小样本探针2026-09-11) |
| 双Provider共享核心与DeepSeek适配 | Qwen/DeepSeek共享四角色Prompt、Schema转换、Citation校验与单份Evidence投影；DeepSeek Responses模拟HTTP及错误边界通过；全量单元`1154 passed, 2 skipped` | [第60节](records/M2_22_08_ANSWER_CITATION.md#60-m2-2284-b双provider共享核心与deepseek-responses适配2026-09-11) |
| Answer Provider输入单份Evidence投影 | Qwen请求内同一Evidence正文只出现一次；无Evidence文件正文仍出现一次；Provider与相邻Agent回归`53 passed`，Mypy检查生产代码170文件通过 | [第59节](records/M2_22_08_ANSWER_CITATION.md#59-m2-2284-a回答provider输入单份evidence投影2026-09-11) |
| Answer/Citation真实Gateway接线 | 固定40题40/40通过，Tool 1016至5703ms；创建40个Context、401条Evidence和24条AnswerEvidence后精确清零；6条安全题零泄露，Fake质量门禁为`None` | [第58节](records/M2_22_08_ANSWER_CITATION.md#58-m2-2283固定40题真实gateway收口2026-09-11) |
| CUDA/BGE解阻探针 | `torch 2.13.0+cu130`、GTX 1650 Ti 4 GiB；两个固定`float32`模型分别/轮流运行成功，预热后0.112/0.416秒；相邻BGE单元`128 passed` | [第55节](records/M2_22_08_ANSWER_CITATION.md#55-m2-2283解阻探针cuda-pytorch与bge显存2026-09-11) |
| CPU/GPU分置真实Gateway探针 | 单题两次复核：Tool成功3422ms，API全程6245/5588ms；诊断确认12条Evidence超过Worker上限8而429，临时数据归零且18/18/779不变；相邻单元`46 passed` | [第56节](records/M2_22_08_ANSWER_CITATION.md#56-m2-2283解阻探针cpugpu分置真实gateway与evidence预算2026-09-11) |
| Answer/Citation Fake编排 | 40题；.8.1/.8.2合计`21 passed`，相邻回归`135 passed`；`quality_gate_passed=None` | [第52至53节](records/M2_22_08_ANSWER_CITATION.md#52-m2-2281实施记录回答citation拒答合同与确定性指标2026-09-10) |
| Reranker/Context | Top5 31/34；Context 32/34；真实跨境12/14，门禁False | [第48节](records/M2_22_07_RERANKER_CONTEXT.md#48-m2-2275实施记录18文档40题正式rerankercontext矩阵2026-09-10) |
| Retrieval/Ragas | Hit/Recall@8 `.9118`；Ragas有效均值Precision `.8024`（21/34）、Recall `.9630`（27/34）、Relevancy `.9815`（27/34） | [第42节](records/M2_22_06_RETRIEVAL_EVALUATION.md#42-m2-226-ragas检索语义评分补跑与最终收口2026-09-10) |
| 固定语料 | 18 Document、18 ChunkSet、779逻辑Chunk；语料Hash保持不变 | [第46至49节](records/M2_22_07_RERANKER_CONTEXT.md#46-m2-2273实施记录固定语料真实数据库候选与context权限重取2026-09-10) |

这些数字证明对应历史代码状态下的验证结果；不能证明后续修改后仍自动有效，也不能证明生产规模、真实DeepSeek质量或M2已经完成。

## 9. 下一步和记录规则

S最新结果见第81.4节：用户明确确认后仅补39/40，两题正确拒答；四段累计40题全部有真实现场，不重答前题，生产引用/权限/版本规则未变。先向用户解释完整结果与质量问题，再确认下一最小修复，不自动调用模型或进入M2-22.8R。历史P/Q/R及S各段报告保留，不能把采集完成或API200当成整体质量通过。

后续文档固定遵守：

- 一个事实只在对应能力记录中保存完整版本；
- 本入口只同步步骤状态、有效决策、活动风险、验证基线和下一动作；
- 总看板只同步里程碑级状态，不复制本文件的逐步测试数字；
- 同一完整能力继续写入同一记录，不为内部模块或微步骤新建碎片文件；
- 能力完成后冻结记录；后续修订写入该能力的新章节并明确旧结论是否失效；
- 未验证的工作不得标记为完成。
