# 2026-09-11 文档整理迁移快照

> 本文件是在压缩项目总看板和M2入口前创建的冻结快照，只用于证明迁移前内容没有丢失。
> 后续不得在本文件继续追加实施日志；日常阅读请使用项目总看板、M2入口和对应能力记录。

<!-- SNAPSHOT:PROJECT_PROGRESS:BEGIN -->
# 项目总进度看板

> 本文档是项目进度的统一入口，只保存当前状态、里程碑摘要、跨阶段决策、阻塞项和阶段链接。
> 详细方案、逐步日志和完整验证结果保存在 `docs/progress/` 对应阶段记录中。
> 状态枚举：待确认、待开始、进行中、受阻、已完成。
> 最近更新：2026-09-11

## 1. 当前状态

| 项目 | 当前内容 |
|---|---|
| 当前阶段 | M2：知识库垂直切片 |
| 阶段状态 | 进行中 |
| 已完成到 | M1已完成；M2-01至M2-21已收口；M2-22.1至M2-22.7.5及M2-22.8.1至.8.2已完成并验证 |
| 当前停止点 | M2-22.8.2已用固定40题跑通纯内存Fake Answer Runner、Run内成功缓存、逐题Trace Hash和公开安全报告；`quality_gate_passed=None`，尚未接真实Gateway/数据库或模型 |
| 下一动作 | 先由用户理解并单独授权M2-22.8.3，再把固定语料、公开Gateway与Knowledge Evidence链接到评估Runner，最终回答仍使用Fake；DeepSeek接入仍位于.8.4 |
| 已确认后续顺序 | 完成M2-22.5至.8 RAG分层评估并复核后，先插入M2-22.8R意图识别与执行分流改造，再用M2-22.9评估改造后的最终Agent轨迹；不等M2整体完成后再返工 |
| 尚未具备 | Gateway真实回答评估链、真实Answer Provider Runner、DeepSeek Agent Provider及真实探针、召回提升及复评（用户已接受暂缓）、Ragas生成评估、40题正式回答矩阵、Validation/Test正式集、意图识别与执行分流、最终多Agent轨迹评估、M2-23至M2-24、前端与M4/M5能力 |
| 当前阻塞 | M2-22.8.3至.8.4的真实接线和DeepSeek单元接入无已知本地阻塞；.8.5以后的真实调用需要用户本地配置有效DeepSeek Key与余额，外部失败必须保持非数值 |

## 2. 里程碑总览

| 里程碑 | 内容 | 状态 | 详细记录 |
|---|---|---|---|
| M0 | 产品、技术、数据、评估与协作基线 | 已完成 | [M0详细记录](progress/M0_DESIGN.md) |
| M1 | 库存查询垂直切片 | 已完成 | [M1当前入口](progress/M1/M1_INVENTORY_QUERY.md) |
| M2 | 自建RAG垂直切片 | 进行中 | [M2当前入口](progress/M2/M2_KNOWLEDGE_RAG.md) |
| M3 | 多模态商品分析（秋招主线暂缓） | 待开始 | [秋招范围调整方案](design/05_Autumn_Recruitment_Scope_Adjustment_Plan.md) |
| M4 | 通用有界深度研究与报告 | 待开始 | [M4当前入口](progress/M4/M4_DEEP_RESEARCH.md)；推荐版正式方案已确认，等待M2收口后单独授权M4-01 |
| M5 | Agent/RAG评估、加固与作品化 | 待开始 | M4范围已确认；待M2/M4实际能力稳定后提交M5正式方案并单独确认 |

M2 的完整历史方案、步骤日志和验证证据位于 [`progress/M2/records/`](progress/M2/records/)；新窗口默认只读取 M2 当前入口，开始具体任务时再按需读取对应过程记录。

## 3. 已确认的跨项目决策

| 决策 | 结论 |
|---|---|
| 大模型 | 保留Qwen并新增DeepSeek为可配置Agent Provider；当前文本推理/回答计划切到DeepSeek，未来可显式切回Qwen。Provider之间不得静默自动兜底；多模态仍保留Qwen既有边界，DeepSeek能力须实际验证后才能描述为已实现 |
| Agent编排 | LangGraph |
| 业务数据库 | PostgreSQL |
| 向量存储 | pgvector |
| Embedding / Reranker | BGE-M3 / BGE-Reranker |
| RAG | 项目自行实现，不依赖RAGFlow |
| M2 RAG评估 | 真实数据必须经过项目现有主链；项目评估器负责Parser/OCR/Chunk、确定性排名、权限、Citation和资源，Ragas在M2-22.6/.8负责检索与生成语义指标，人工复核固定Test与Bad Case；RAG阶段不同时引入DeepEval |
| 互联网搜索 | M4使用`search_public_web`与`read_public_source`两个受控Tool，经Service和可替换Provider调用Tavily；不允许模型提交任意URL/HTTP |
| V1文件存储 | 本地文件系统 + Storage抽象，不部署MinIO |
| 数据 | 明确标注的版本化合成演示数据 |
| Tool权限 | 单个Agent或Skill只获得1至5个允许Tool，模型不能直接访问数据库 |
| Harness | 统一负责上下文、权限、白名单、预算、超时重试、审计、证据和评估钩子 |
| MCP | V1不引入；连接真实外部系统或向外部客户端复用时再评估 |
| 项目最高目标 | 面向秋招AI应用岗位形成可运行、可观察、可量化、用户能独立讲透的作品；M4与M5仍是最终主线，不把顺序后移擅自解释为删除 |
| 公开聊天入口 | 复用现有消息POST；M2-21.10已迁移到唯一Agent Gateway，旧M1固定图不再位于公开主路径或充当自动兜底 |
| M2执行分流 | RAG分层评估完成后、M2-22.9之前单独实施：意图识别必须同时决定执行路径，且不固定新增一次LLM调用；程序先处理高置信明确请求，只在不确定时让模型用一次结构化输出同时完成意图、路径和参数提取。单一简单查询绕过Supervisor，固定复合查询走受控Pipeline，只有确需规划的任务进入Supervisor/Worker；本步不新增Worker、Tool或Web研究 |
| M2-22.7召回限制处置 | 2026-09-10用户在理解三条漏召回归因后接受当前结果并决定暂不修复，允许进入M2-22.8方案确认；评估完成与质量门禁失败继续分开记录，34+6分母和Bad Case不得删除，后续简历/报告不得宣称已过90%门禁 |
| 秋招范围调整 | M3多模态暂缓；M4推荐版已确认：复用Business/Knowledge Worker，只新增Web Research Worker，以Tavily自定义Provider实现搜索与受控正文读取，保留三类Evidence、有界并行、PostgreSQL Checkpoint、Markdown和一个研究Skill；M5保留Agent/RAG评估、加固和作品化；详见[M4入口](progress/M4/M4_DEEP_RESEARCH.md)与[调整方案](design/05_Autumn_Recruitment_Scope_Adjustment_Plan.md) |
| 开发方式 | 教学式协作、阶段方案先确认；默认按垂直小能力开发并采用风险驱动测试，同一能力同一层级优先扩展现有测试文件，不再按内部模块或微步骤机械新增测试文件 |
| 阶段文档结构 | M1及以后统一使用`docs/progress/M{编号}/`，阶段短入口与`records/`过程记录分离；新窗口按当前任务读取，不默认加载全部历史 |

M2 专属的解析、分块、索引、检索、Reranker、Context和Evidence决策不在总看板重复展开，统一以 [M2入口](progress/M2/M2_KNOWLEDGE_RAG.md) 和对应过程记录为准。

## 4. 当前验证基线

M2-22.8.2完成时：

- 新增纯内存Fake Answer Runner：从固定40题JSONL构造内存Context、连续`[E1]`至`[E12]`获权绑定和确定性Golden Evidence哈希；Fake Provider只在Context覆盖全部Golden时输出Canonical要点与合法Citation，6条安全题固定拒答。标准运行恰好保留34条可回答和6条安全题并调用Fake Provider 40次；
- 新增Run内Answer缓存，键绑定Provider完整身份以及case、问题、Context、Golden、获权Evidence与要点规则等所有会影响回答的私有输入；相同请求命中缓存且不二次生成，异常或`provider_failed/skipped`不写缓存。Provider抛出的原始异常被替换为固定安全摘要，失败题仍留在报告且相关指标和分组保持`None`；
- 新增公开安全报告和CLI：逐题只保存问题、Context、规则、Provider请求和答案输出的SHA-256、非正文指标与Trace Hash；递归拒绝问题/答案/Context正文、路径、Storage Key、tenant/owner、Fixture身份、SQL、原始异常/响应等私有字段。报告会复算固定分组和Trace Set Hash，篡改即拒绝；同输入两次序列化字节完全一致，Fake报告强制`quality_gate_passed=None`；
- TDD RED为三个新测试文件因缺少`app.evals.answer_citation_report`而在收集阶段失败；GREEN为M2-22.8.2的11项测试通过，连同.8.1指标为`21 passed`，相邻M2-22.7/.8评估回归为`135 passed`。全维护范围Ruff、9个目标文件格式、Mypy 169个`app`源码、目标源码/测试Mypy、`compileall`和`git diff --check`通过；
- 本步没有访问API、Gateway、Agent、Harness、Tool、数据库、pgvector、Storage或固定18文档/779 Chunk，没有加载BGE，也没有调用Qwen、DeepSeek或Ragas。完整证据见[M2-22记录第53节](progress/M2/records/M2_22_CROSS_BORDER_RAG_EVALUATION_PLAN.md#53-m2-2282实施记录fake-answer-runner公开安全报告与run内缓存2026-09-11)。

M2-22.8.1完成时：

- 冻结`m2-answer-citation-evaluation-v1`，完整继承M2-22.7.5所选`compact 400/500 + overlap 100 + Dense/Lexical各10 + Hybrid最多20 + RRF 60 + Reranker Top5 + neighbor 1 + 3000 Token`，并固定BGE-M3/BGE-Reranker版本、34条可回答与6条安全题；真实/合成/诊断分栏为14/10/10，安全原因保持ACL 2、版本2、无Evidence 1、unknown 1；
- 新增逐题回答执行合同与纯内存指标：规范化后的Golden要点/显式白名单变体覆盖、禁用断言、回答/拒答、Citation语法、缺失必需引用、重复/越界/不存在标签、当前获权Evidence映射、Golden Evidence precision/recall及安全敏感短语泄漏；失败归因明确区分上游Context缺Golden、Context输入不可用、回答执行失败、回答漏要点、Citation身份/Golden映射失败和安全错误；
- `citation_semantic_support_evaluated=False`且语义支持分数只能为`None`，明确不能把Citation身份合法或映射到Golden Evidence冒充Ragas Faithfulness/人工语义支持；Context或Provider计算失败、跳过时逐题及受影响聚合的计算字段保持`None`，题目仍由固定Cohort保留在分母；
- TDD RED为缺少`app.evals.answer_citation_metrics`的`ModuleNotFoundError`；GREEN聚焦`10 passed`，新指标+相邻评估Schema+M2-22.7全套相关单元回归`124 passed`。全维护范围Ruff、3个目标文件格式、Mypy 167个`app`源码、目标源码/测试Mypy、`compileall`和`git diff --check`通过；
- 本步只修改评估Schema、纯内存指标和单元测试，没有创建Answer Runner、报告CLI、缓存、Gateway/数据库接线、Provider、真实探针或40题正式运行；未访问PostgreSQL/pgvector/Storage，未加载BGE，未调用Qwen、DeepSeek或Ragas，也未修改固定文档、Chunk、检索/精排/Context和生产配置。完整证据见[M2-22记录第52节](progress/M2/records/M2_22_CROSS_BORDER_RAG_EVALUATION_PLAN.md#52-m2-2281实施记录回答citation拒答合同与确定性指标2026-09-10)。

M2-22.7漏召回只读诊断完成时：

- 复用同一18文档、18 ChunkSet和779个逻辑Chunk，只加载本地BGE-M3查询模型并把Dense/Lexical诊断深度临时扩大到100观察名次；没有上传、Parser、Chunk、Reranker、Context、回答链或生产配置变更。诊断前后语料计数及SHA-256 `70750ee64c959795e7360a80f59df9248275ecfe5ddfbfb740e290bf5cde27a3`一致，既有语料确保结果为`created=False`；
- 三条完整Golden Chunk都在固定语料中，排除“解析或切块把答案删掉”：`smoke-syn-011-scan-batch`的Dense/Lexical名次为33/缺失，`smoke-ext-029-return-invalidation`为42/缺失，`smoke-ext-031-zh-responsible-person`为39/缺失；把正式每路深度从10试算到20或30仍无法让完整Golden进入融合池；
- 共同主因是中文问题与英文Golden没有词法词项交集，Lexical只召回含中文通用词的干扰块；Dense理解了大致语义，但前两题被“批次/标识符”及相似海关失效条款压到后面。第三题是特殊情况：正确GPSR文档的其他Chunk已在Dense第1至3名，其中第3名含答案后半段；完整Golden位于相邻Chunk，解释了Context邻块为何能补回；
- 深度50虽能看见三条完整Golden，但其RRF名次仅39/50/52，不能据此断言“把Top10改Top50”就是有效修复。当前证据支持优先单独评估中英查询扩展/翻译和文档内二次定位；不支持重切Chunk，也尚未证明任何修复方案能通过90%门禁。完整记录见[M2-22记录第49节](progress/M2/records/M2_22_CROSS_BORDER_RAG_EVALUATION_PLAN.md#49-m2-227漏召回只读原因诊断2026-09-10)。

M2-22.7.5完成时：

- 正式Runner只读检查并复用既有18份Document、18个`compact 400/500 + overlap 100` ChunkSet和779个逻辑Chunk；首次只在同一ChunkSet上新增18个真实BGE-M3 IndexSet，未再次上传、解析或切块。最终数据库为18个固定Document、18个ChunkSet、36个IndexSet（18 Fake历史代次+18真实BGE-M3代次），18个active代次全部为真实BGE-M3；
- 40题全部保留：34条可回答题与6条安全题。34题Reranker Top5从RRF Top5的27/34提升到31/34；Top8由RRF 31/34保持为Reranker 31/34，因此按“命中更多优先、并列选更小TopK”的冻结规则选择Top5。真实/合成/诊断组在选定Top5下分别为12/14、10/10、9/10；3条`candidate_missing`仍留在分母，未归咎于Reranker；
- 选定Top5后的Context六点中，邻块1+3000 Token达到最高总Golden覆盖32/34，与4000 Token相同，但预算更小且冗余率`.9062`低于`.9135`，因此作为后续候选；Anchor覆盖仍为31/34，明确说明多出的1题只是邻块补到，不能冒充Reranker恢复。6条安全题全部完成、泄漏0；
- 正式本地BGE运行只对40个非空候选池各评分一次：74次逻辑取分、34次Run内缓存命中、40次miss/Provider调用；总耗时`771.923s`，模型加载`24.825s`，评分p50/p95/max为`18076.246/28578.570/29613.483ms`，峰值RSS`3681.273MiB`、增量`2703.137MiB`，effective batch始终为2；
- 权威复跑的Trace Set SHA-256为`5cf23c03d3ece573652d63aa07d2d0356a89dc48239e8296bd4ac63d2de523e3`；临时报告596,026字节，SHA-256为`b62d4c674653c32ed2541fe97bc4f2cb0a7357997c97b75f08e9becb33d09804`，记录后精确删除。`evaluation_completed=True`与`quality_gate_passed=False`同时保留，失败原因是实际真实跨境12/14=`85.71%`低于`.90`，不是运行失败；
- TDD RED为正式模块尚不存在时的`ModuleNotFoundError`；最终聚焦与相邻合同`172 passed`，不触碰固定语料的相邻PostgreSQL/pgvector集成`8 passed, 1 deselected`，显式本地BGE Smoke `3 passed`。Ruff全维护范围和格式、Mypy 166个`app`源码及10个目标源码、`compileall`、`pip check`通过；三套幂等Seed重跑后M1德国仓库存仍为125，固定语料仍为18/18/779，Storage为28 uploads / 18 parsed / 18 chunks；
- 本步没有运行Qwen、Ragas、最终回答、Citation、Knowledge Tool、Harness、Agent/LangGraph、公开聊天API或前端，也没有修改生产Parser、Chunker、Retriever、Reranker、Context、配置、迁移、依赖或默认参数。完整证据见[M2-22记录第48节](progress/M2/records/M2_22_CROSS_BORDER_RAG_EVALUATION_PLAN.md#48-m2-2275实施记录18文档40题正式rerankercontext矩阵2026-09-10)。

M2-22.7.4完成时：

- 新增严格的本地BGE资源探针和显式`--run-real` CLI：固定6类中英德/表格/候选缺失/无答案样本，每类模拟M2-22.6两路depth 10融合后的最大20候选；每池只调用Provider一次、第二次逻辑请求复用当前Run缓存，报告不保存问题、正文、路径或底层异常；
- 开始真实验证时发现既有2.29 GB快照已不在当前模型缓存；程序在加载前安全失败。经用户明确授权后重新下载固定6个运行文件共`2,293,242,108`字节，manifest SHA-256为`c0cd30c8cb8f001454a113390ac195b15b54a2b16de4a86c8fa6ca91202e3f8b`，无下载模式复核为True；
- 在Hugging Face/Transformers离线且HTTP/HTTPS代理指向不可用地址时，真实`BAAI/bge-reranker-v2-m3@953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e` CPU探针完成：加载`26.317746s`，20候选评分p50/p95/max为`4811.968/6351.987/6396.700ms`，RSS从`316.418MiB`升至峰值`2045.113MiB`，增量`1728.695MiB`，effective batch始终为2，新存活子进程0；12次逻辑取分为6次Provider调用+6次缓存命中；
- 四个可回答代表样本的预期候选均排第1；`candidate_missing`和`no_answer`仍无预期候选及名次。全部6×20分数有限；公开报告Schema/Hash复核通过，Artifact SHA-256为`8732450faeeea921e6b098c71d35382d8426d946429ede0324d8d4c32cff3d1c`，`quality_gate_passed=None`；
- TDD RED为两个测试文件收集时报缺少探针模块和CLI；GREEN及相邻Provider/Runner/报告/CLI为`45 passed`，额外真实离线BGE Smoke为`3 passed`。本步目标文件Ruff/Mypy通过，编译、依赖与diff检查通过；全仓库根目录Ruff/Mypy另暴露旧`agent/api/tools`格式债和既有`prepare_m2_cross_border_eval.py`类型问题，未在本步越界修改；
- 本步不经过文档上传、Parser、Chunk、Index、Dense/Lexical/RRF、Context、Repository、PostgreSQL/pgvector/Storage、Qwen/Ragas、API、Agent/LangGraph、Harness、Tool或前端，因此没有重新切块，也不能证明40题Reranker/Context质量或建议门禁通过。

M2-22.7.3完成时：

- 用户确认把文档生命周期与查询实验拆开：18份固定文档只在语料不存在时经过公开上传、真实Parser/Docling、Chunk Service和Index Service；后续Dense/Lexical depth、RRF、TopK、Reranker或查询侧关键词逻辑变化直接复用现有ChunkSet。只有原文、Parser输出或Chunk配置变化才重切；Embedding/FTS身份变化只新增IndexSet，不重做Document/Version/ChunkSet；
- 新增幂等固定语料准备器，语料Hash只绑定数据集/来源内容和Chunk配置，索引Hash另绑定Embedding/FTS身份。集成测试证明第二次调用的Document、ChunkSet、IndexSet、Chunk UUID完全相同；切换Embedding身份只把IndexSet代数从1增到2，Document与ChunkSet仍不变；成功语料不再由评估`finally`清理，只有首次创建中途失败或测试隔离租户才精确回滚；
- 正式一次性准备得到18 documents / 18 ChunkSets / 18 Fake IndexSets / 779 active Chunk rows，tenant为`3288f8db-e815-442c-860a-dbb8077a1954`，语料Hash `70750ee64c959795e7360a80f59df9248275ecfe5ddfbfb740e290bf5cde27a3`。第二次调用为`created=False`，索引Hash和快照Hash也完全不变，证明复用而非重建；
- 真实数据库小样本链为Dense Top10 + Lexical Top10 → RRF 60（11个去重候选）→ 生产Reranker Service + Fake Provider（Top5）→ 生产Context Builder/Repository（12段、3266项目Token）。Context重新检查ACL、tenant、软删除和active版本/IndexSet；探针前后Chunk均为779；
- RED先后为缺少数据库装配函数的`ImportError`和缺少固定语料模块的`ModuleNotFoundError`；GREEN聚焦`9 passed`，真实权限/检索/Context相邻集成`24 passed`，Reranker/Context单元`72 passed`，既有检索Runner集成`1 passed`。Ruff全维护范围、目标格式、Mypy 164源码和`compileall`通过；
- 本步没有运行真实BGE-Reranker、Qwen、Ragas或40题正式质量矩阵，没有修改生产Parser、Chunker、Index、Retrieval、Reranker、Context、配置、迁移或依赖。持久语料位于开发评估数据库；会重建schema的集成测试仍可能清空它，后续此类测试必须先运行，随后用幂等准备器只在缺失时恢复。

M2-22.7.2完成时：

- 新增Fake-only Runner：40题仍严格分成34条可回答与6条安全题；每条可回答题依次消费Top5、Top8和选定TopK下6个Context点，逻辑请求共`34×8+6=278`次，但Run内缓存使底层Fake评分只有40次，34题产生238次命中；
- 缓存键绑定query Hash、候选有序身份与正文Hash、Fake模型ID/revision、最大长度、精度和评分实现版本；query、候选顺序/正文Hash或模型身份变化均不命中，评分异常不写缓存；
- 每道题生成公开Trace及SHA-256，总Trace Hash再绑定40条有序Hash。报告只含公开身份、可用Locator、RRF/Reranker名次与分数、正文Hash和Evidence映射；不含问题、正文、路径、Storage Key、tenant、SQL或原始异常；重复输入得到字节一致报告；
- CLI只暴露输出路径和选定TopK，运行身份固定为`deterministic_fake`；`run_status=completed`只说明Fake编排完成，`quality_gate_passed=None`强制表示没有评估真实质量。安全分栏6/6保留且Fake零泄漏门禁为True；
- TDD RED为三个测试文件收集时缺少`app.evals.reranker_context_report`；GREEN聚焦`8 passed`，连同上一小步指标、数据合同及既有Retrieval Runner相邻回归为`116 passed`。Ruff全维护范围、8个目标文件格式、Mypy 163个`app`源码和编译通过；本步未访问PostgreSQL/pgvector/Storage，未加载BGE/Qwen/Ragas，也未经过前端、API、Agent/LangGraph、Harness、Tool或生产Reranker/Context Builder。

M2-22.7.1完成时：

- 冻结`compact 400/500 + overlap 100 + Dense/Lexical各depth 10 + Hybrid最多20 + RRF 60`，先比较Reranker Top5/Top8，再只对筛出的TopK按邻块0/1和Context 2000/3000/4000 Token运行6点；固定Reranker仍为`BAAI/bge-reranker-v2-m3@953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e`；
- 逐题合同要求RRF与Reranker候选身份及Evidence映射完全相同，并把结果严格分为`candidate_missing/promoted/demoted/unchanged`；候选缺失是成功算出的上游失败，Reranker排名保持为空，不能删题或归咎于精排；
- Context确定性指标把全部Golden覆盖与仅Anchor覆盖分开；邻块可以如实提高整体覆盖，但不能冒充Reranker Anchor命中。冗余率定义为最终顺序中“没有新增Golden Evidence的片段数/片段总数”，Token利用率为`total_tokens/context_max_tokens`；空Context是成功的0值，计算失败则所有比率为`None`；
- 正式Debug分母冻结为34条可回答题和6条安全题，安全题保持2条ACL、2条版本、1条无Evidence、1条unknown独立分栏。聚焦`13 passed`，相邻评估合同`111 passed`；Ruff全维护范围、目标格式、Mypy 161源码、`compileall app`和`git diff --check`通过；
- 本步只修改评估Schema、纯内存指标和单元测试；未创建Runner/报告CLI/缓存，未访问PostgreSQL/pgvector/Storage，未加载或运行BGE/Qwen/Ragas，也未经过前端、API、Agent/LangGraph、Harness、Tool或生产Reranker/Context Builder。

M2-22.6正式收口时：

- 只补跑筛出的`compact 400/500 + overlap 100 + depth 10 + RRF 60`，真实经过18文档上传/解析/分块/索引、本地BGE-M3、FTS/pgvector和RRF；18个Index Set、779个Chunk、40题/120条route list、1,430候选，映射失败0，没有重跑完整矩阵；
- 全部34条可回答Hybrid Hit/Recall@8仍为`.9118`，真实/合成/通用分别`.8571/1.0000/.9000`，miss仍为`2/0/1`。跨重建MRR@10从`.6584`变为`.6929`、nDCG@10从`.7193`变为`.7450`，定位为同分排序依赖重建Chunk UUID；同一Index内120条稳定性复跑仍为0变化；
- Ragas只按有效完成样本计算：Precision `.8024`（21/34）、Recall `.9630`（27/34）、Relevancy `.9815`（27/34）。7个超时、13个HTTP 400欠费Provider失败、7个框架失败无数值，Noise 34条因无回答全部跳过；真实组只有4/14、8/14、7/14条有效，不能宣称全量通过；
- Ragas专项`9 passed`、Runner/指标`96 passed`、Index/Embedding/Retrieval相邻`153 passed`、允许单元`680 passed, 2 skipped`、固定本地BGE Smoke `4 passed`；允许集成`140 passed, 2 skipped, 1 failed`，唯一失败仍是历史M1 Seed清场顺序与正式M2外键冲突。Ruff格式348文件、lint、Mypy 163源码、编译、依赖和diff门禁通过；
- 报告Hash写入[M2-22第42节](progress/M2/records/M2_22_CROSS_BORDER_RAG_EVALUATION_PLAN.md#42-m2-226-ragas检索语义评分补跑与最终收口2026-09-10)后精确删除。最终三套Seed重跑，独立核对为10 files/documents/versions、10 parse/index pending、9 ACL、0 ChunkSet/IndexSet/Chunk、评估tenant 0、Storage 10 uploads/0派生对象、M1库存`150-20-5=125`；
- 生产Chunk、TopK、RRF、SQL和数据库结构未修改；未运行Reranker、Context/Evidence、Tool、Harness、Agent/LangGraph、最终回答、Citation或M2-22.7。

M2-22.6R-01与确定性矩阵完成、Ragas外发受阻时（历史基线）：

- DOCX无页/段落/表格/标题坐标时，只把真实且与首个source span一致的Canonical `bNNNNNN`降级为公开`block_number`；非法或不一致Block只隔离该候选，保留原名次空洞、记录安全失败并使完整性门禁失败，不再拖垮整个Dense/Lexical请求，也没有过滤页眉/页脚；
- 单题真实复现确认原Dense第4名页眉Chunk仍为第4名，Locator降级为`block_number=1`；正式Run随后完成18文档、40查询、10组Chunk、50个顺序实验点、180个Index Set、50份完整Trace、6,000条路由列表和106,518个候选，Locator映射失败0；
- 冻结选择口径得到`compact 400/500 + overlap 100 + depth 10 + RRF 60`候选；全34条可回答题Hybrid Hit/Recall@8均为0.9118，MRR@10为0.6584，nDCG@10为0.7193。真实跨境14题Hybrid Hit/Recall@8为0.8571，仍有2题完全漏召回；相似产品串答率为1/9，安全过滤误召回0；
- ACL、软删除、inactive Index Set和tenant泄漏均为0，120条同配置复跑排名全部稳定；生产默认SQL、Chunk、TopK、RRF与数据库结构均未修改。`compact/80`长VAT索引仍证明生产2秒SQL超时不足，评估只用30秒覆盖；
- 专项`177 passed`，相邻普通集成`136 passed, 4 skipped`后显式开启本地BGE Smoke为`4 passed`，截至Retrieval允许单元`625 passed, 2 skipped`，数据库/服务集成`130 passed, 3 skipped, 1 failed`；唯一失败是旧M1 Seed测试清场顺序被正式M2外键阻止，不是检索回归。Ruff格式/lint、11源码Mypy、编译、`pip check`和diff检查通过；
- 固定Ragas 0.4.3在34条所选Hybrid样本上记录Context Precision/Recall各34个`judge_failed`、Context Relevancy 34个`framework_failed`、Noise Sensitivity 34个`skipped`，全部无数值。前三项失败源于外部Judge网络/数据发送权限，Noise Sensitivity因该版本要求回答而与本步禁止回答冲突。当前等待用户明确授权外发评估内容；完整证据见[M2-22过程记录第41节](progress/M2/records/M2_22_CROSS_BORDER_RAG_EVALUATION_PLAN.md#41-m2-226r-01与确定性检索矩阵2026-09-09)。
- 两个本步检索报告目录记录Hash后已精确删除；M1、两个M2正式Seed实际重跑。独立`psql`和文件系统核对为10 files/documents/versions、9 ACL、10 pending/uploads、0 ChunkSet/IndexSet/Chunk、评估tenant 0、M1库存125；8份冻结外部raw/processed原文、既有Parser/Chunk报告和模型缓存按上游资产保留。

M2-22.5R-04A完成时：

- Chunker升为`m2-structure-aware-chunker-v3`：标题继续从正文抽离到`heading_path`，并新增参与Hash的精确`heading_sources`和`heading_metadata`排除记录；Block、字符起止、页码和bbox可审计，历史v1/v2空扩展保持可读；
- PDF边界评价在有行级Locator时按物理layout line及真实残段检查，不再把双栏/表格横向拼接文本误当成一个正文段；标题只有Parser声明、源切片、Locator和精确排除记录一致时才能从正文分母移除，标题质量仍要求真实正文绑定；
- 最终Run `m2-22.5-20260909t032311-651ab937`真实完成18文档、34条Golden、4组首轮与9组overlap：总门禁True；代表性large/120为34/34内容与Locator、56/56标题、0/11809边界断裂、45/45表格、18/18顺序/Locator/确定性，DOCX页眉3/3、页脚3/3、图片OCR与前后文各1/1；
- 专项`123 passed`，相邻PostgreSQL/Service集成`20 passed`，完整允许单元`385 passed, 2 skipped`；Ruff、11文件格式、156源码Mypy、编译、依赖和diff检查通过；
- 正式报告Hash为`857040c692640d286b364589f0963b0eaea7e1b21affaac2ef24cfd28259dd1a`，摘要写入记录后删除。报告与独立审计均确认评估行/ChunkSet/Storage对象为0，正式基线恢复10 files/documents/versions、9 ACL、10 pending/uploads、0 ChunkSet和M1库存125；
- 本步未修改Golden、R04阈值或生产默认Chunk参数，也未运行Ragas及任何禁止下游。完整证据见[M2-22过程记录第39节](progress/M2/records/M2_22_CROSS_BORDER_RAG_EVALUATION_PLAN.md#39-m2-225r-04a实施记录标题来源审计版面边界校准与正式收口2026-09-09)。

M2-22.5R-01B Docling一次性Worker收尾阻塞解除时：

- 真正的Docling一次性Worker在完整结果或固定失败消息同步写完、Pipe关闭后确定性退出；父进程的2秒收尾窗口、活进程拒收、总时限、RSS/Snapshot上限、退出码和Snapshot复验均未放宽。故意留下非守护线程且不执行正式退出协议的假Worker仍得到`shutdown_timeout`；
- 单件真实Router/RapidOCR Smoke恢复扫描PDF的2/2事实，日志为`status=success`、总耗时101,853 ms、峰值约1.96 GB，Worker PID 39876完成后不存在；
- 干净基线上的18文档正式Parser/R04为`run_status=completed`：18/18上传与解析、34/34 Golden、外部14/14、OCR 4/4、18/18质量接受；路由Native 16、Docling 1、Hybrid 1；评估数据库行/Storage对象为0，正式10 files/documents/versions、9 ACL、10 pending/uploads和M1库存125恢复；
- 专项`6 passed`，相邻数据库集成`21 passed`，禁止下游边界内完整允许单元为`370 passed, 2 skipped, 3 failed`；3个失败与此前相同，继续冻结R-02的编号标题、父子路径和标题空壳缺口。Ruff、156文件Mypy、格式、编译与diff检查通过；
- 本步没有改Router、R04、Chunker、标题Golden或生产Chunk参数，没有运行Embedding、pgvector、检索、Reranker、Context、Agent、Qwen、Ragas或前端。完整证据见[M2-22过程记录第34节](progress/M2/records/M2_22_CROSS_BORDER_RAG_EVALUATION_PLAN.md#34-m2-225r-01b补充实施记录docling一次性worker确定性退出2026-09-08)。

M2-22.5R-01B PDF行级Locator实现后、全量R04复验受阻时：

- Native PDF Parser升为`m2-pdf-v2`，PDF专用Adapter升为`m2-native-pdf-adapter-v2`；Canonical Artifact新增可选`pdf_layout_lines`，逐行保存页码、行号、原文、可证明的字符范围和top-left坐标，标题提示引用对应物理行。无法唯一映射的重复/重排文字明确保留空范围，不伪造offset；
- 12份正式PDF（4份合成、8份官方）重复解析与Artifact结果一致；4组双栏标题正文关系可按页面左右坐标唯一分开，4份问题PDF的38条独立标题与4个组合片段均能回到真实行和字符范围；旧v1 Artifact缺省新字段仍可读取，新几何参与Artifact内容Hash；
- 维护范围专项/相邻单元为`369 passed, 2 skipped, 3 failed`，3个失败均是此前为R-02冻结的编号标题/父子标题与标题空壳RED；数据库相邻集成为`21 passed`；`ruff check app tests scripts migrations`、`mypy app`（156个源码文件）、`compileall -q app`和`git diff --check`通过。仓库根目录全量Ruff另显示旧`api/config/tools/utils`目录98个既有问题，本步未越界修改；
- 18文档正式Parser/R04实跑结果为17/18解析完成、32/34 Golden、官方14/14、OCR 2/4；17份完成文档全部`accepted`。唯一失败为扫描入库单，Docling Worker拿到结果后连续两次触发`shutdown_timeout`；单件复跑仍失败，说明不是一次偶发。正式评估清理恢复为10份基线文件/文档/版本、9条ACL、10个待处理版本/上传对象、M1库存125，评估行与对象均为0；临时报告已删除，两个Worker PID均不存在；
- 因18/18与34/34没有在本次代码状态下重现，R-01B记为“实现完成、验收受阻”，不得进入R-02或M2-22.6。完整证据见[M2-22过程记录第33节](progress/M2/records/M2_22_CROSS_BORDER_RAG_EVALUATION_PLAN.md#33-m2-225r-01b实施记录pdf行级locator增补与验收阻塞2026-09-08)。

M2-22.5R-01A可信结构标题Golden完成时：

- 新增严格`m2-chunk-heading-golden-v1`，SHA-256为`93428d44fe539ed4eafbed6b80169818fc273c6c675a807de887fa20c3aa9c17`；4份问题PDF的85条Parser提示全部归类为38条独立标题、4条组合标题片段和43条非标题，没有遗漏或重复归属；
- 冻结26条“完整标题路径→非标题正文锚点”Golden：双栏4、OSS 16、GPSR 5、Safety Gate 1；组合标题、同栏关系、项目符号、金额、字段名和值均有明确正反例；
- TDD首轮因缺少新合同得到预期ImportError；完成后专项`5 passed`，与既有评估合同/40条Smoke数据相邻回归`89 passed`；全范围Ruff、156个源码Mypy和编译通过；
- PDF视觉审计临时页图已按验证后的`tmp/pdfs/m2-heading-audit`绝对路径删除。没有修改生产Parser/Chunker、R04、34条内容Golden、数据库或Storage，也没有运行任何禁止的下游能力；
- 双栏审计同时证明新阻塞：现有页级Artifact把左右栏标题及正文压进同一文本行，且没有正文行级坐标，不能在Chunk层可靠恢复栏位关系。完整证据和待确认方案见[M2-22过程记录第31至32节](progress/M2/records/M2_22_CROSS_BORDER_RAG_EVALUATION_PLAN.md#31-m2-225r-01a实施记录可信结构标题golden冻结2026-09-08)。

M2-22.5R-01完成、R-02尚未开始时：

- 新增编号标题元数据、多级标题、正文短语误报和标题空壳反例；旧实现在预期位置得到`3 failed, 14 passed`，3个失败分别证明编号/同行标题尚未进入`heading_path`，以及现有质量指标会误收只有标题、没有正文的空壳Chunk；Ruff定向检查通过；
- 只读检查4份真实失败文档的R04 Parser Artifact：85条`heading_hints`中29条是整行精确匹配、21条只在某一行内唯一出现、1条出现歧义、34条在规范化最终页文本中缺失；OSS提示还包含项目符号正文，GPSR与Safety Gate提示包含金额或字段值。Artifact合同本身也明确把它称为“线索”而非保证为真的标题；
- 因此先前“109/152标题保留”只能说明Chunk未消费全部启发式提示，不能证明其余43条都是真标题，更不能把152/152作为可防伪的正式质量目标。标题元数据注入仍是目标，但只允许注入经过结构真值确认、且能与正文确定性绑定的标题；
- 本步没有修改生产Chunker、Parser Artifact、R04阈值或数据库/Storage，没有运行M2-22.6及Embedding、pgvector、检索、Reranker、Context、Agent、Qwen、Ragas、前端。完整证据见[M2-22过程记录第30节](progress/M2/records/M2_22_CROSS_BORDER_RAG_EVALUATION_PLAN.md#30-m2-225r-01实施记录合同反例与真实提示审计2026-09-08)。

M2-22.5完成实际矩阵、但质量门禁未通过时：

- 正式Runner复用公开上传/建文档API、R04 Parser Artifact、现有`DocumentChunkService`和真实PostgreSQL/Storage，运行4组首轮配置及`chunk-large`的overlap 80/100/120扫描；没有改生产Chunk默认值，也没有运行Embedding、pgvector、检索、Reranker、Context、Agent、Qwen、Ragas或前端；
- 首轮compact/medium/current/large分别产生800/611/506/429个Chunk，Golden包含与Locator分别为34/34、33/34、33/34、34/34；所有配置均为18/18顺序、Locator完整性和重复构建确定性，45/45表格行、0空Chunk。当前生产配置`600/700/100`为0/9750边界断裂，但`smoke-ext-025-ioss-coverage`只恢复96.59%证据范围；
- 首轮候选为`chunk-large`；overlap 120结果为441个Chunk、Token min/p50/p95/max=`2/684/699/805`、显式重叠率16.00%、34/34 Golden及Locator、9687/9687段落、0/9750边界断裂、45/45表格行，DOCX页眉/页脚/图片OCR/前后文均1/1，但标题仍为109/152，所以不能标记通过；缺失集中在两栏PDF、OSS指南、GPSR和Safety Gate通报的Parser标题提示与Chunk正文精确匹配规则，归因为Chunk规则，不是Parser Artifact或Locator；
- 正式报告`m2_cross_border_chunk_report_v1.json`为498,013字节，SHA-256 `37bf809c654af1eb92cfb777165aba274fdf6307e7e8befc220cbcf44c69f3e7`；评估租户数据库行、ChunkSet和Storage对象均清零，正式基线恢复10 files/documents/versions、9 ACL、10 pending、10 uploads、0正式ChunkSet，M1库存仍为125；
- 专项`84 passed`；相邻单元`173 passed, 2 skipped`；相邻集成`21 passed, 3 skipped, 6 errors`，6个error均为旧File API夹具在正式文档外键存在时无条件删除`files`；完整允许范围单元`442 passed, 2 skipped`、数据库/服务集成`60 passed, 3 skipped`。Ruff、156个源码Mypy、编译、依赖、diff及Alembic门禁通过；全范围格式检查仅剩未修改的既有迁移测试一处差异。完整证据见[M2-22过程记录第27节](progress/M2/records/M2_22_CROSS_BORDER_RAG_EVALUATION_PLAN.md#27-m2-225实施记录chunk质量矩阵2026-09-08)。

M2-22.4R-04完成时：

- 新增版本化`m2-post-parse-quality-v1`解析后质量决定：健康Native最终文字保留率低于70%拒绝；PDF逐页最终文字少于10字符时，根据Native至少50字符或扫描/图片信号拒绝，真实空白页不误拒；DOCX图片大于5 KiB且OCR为空会告警，图片独占段落或正文近空则升级为拒绝；
- 门禁位于Router选路完成后、Parsed Artifact发布前。拒绝时Parser/File/Index状态进入失败补偿，不写解析产物、不进入`ready`，Index Service集成验证为0个Index Set；接受决定和结构化告警随Routed Artifact保存，旧v1 Artifact仍可读取，但所有新解析都必须带通过决定；
- 18份原件经公开上传/建文档API、隔离PostgreSQL/Storage与正式Parser主链全部通过质量门禁，严格事实恢复34/34、OCR 4/4；18个决定均为接受、0条质量告警，282个PDF页判断与1个DOCX图片判断均接受，运行后评估数据和对象清零并恢复正式基线；
- 定向质量/路由`25 passed`，Parser Service集成`6 passed`，相邻集成`31 passed`，完整单元`1008 passed, 2 skipped`，完整后端`1287 passed, 14 skipped`；Ruff、155个源码Mypy、编译、依赖和Alembic检查通过。跨月Key与Alembic日志污染两项测试基础设施问题已最小修复；完整证据见[M2-22过程记录第25节](progress/M2/records/M2_22_CROSS_BORDER_RAG_EVALUATION_PLAN.md#25-m2-224r-04实施记录解析质量门禁与拒绝索引2026-09-08)。

M2-22.4R-03完成时：

- `DocxParser`升级到v2：Section页眉/页脚单独保存，正文Run中的`wp:inline`图片按“前文→OCR→后文”顺序输出；图片外链被拒绝，单图/总字节/像素/数量有界，同Hash重复图片只执行一次OCR但保留每个锚点；
- Canonical Artifact以向后兼容的可选`m2-docx-source-v1`元数据区分`docx_header/docx_footer/docx_image_ocr`，普通v1 Block序列化与Hash形状不变；Markdown分别显示`[页眉]`、`[页脚]`、`[图片内容]`，诊断汇总可分别计数；
- 真实Router离线RapidOCR验证图文DOCX保持Native，页眉和图片两条均找回，图片平均置信度约0.993；专项/相邻`116 passed`，完整单元`990 passed, 2 skipped`，显式真实Smoke `1 passed`，Ruff、155个源码Mypy、编译及依赖检查通过；
- 全量后端另有`1259 passed, 14 skipped, 6 failed`：5个R-02日志捕获用例隔离复跑`5 passed`，属于测试顺序日志配置污染；剩余1个既有索引集成用例仍因上传Key写死`2026/08`在当前`2026/09`无法删除真实对象而独立失败。本步未修改该范围外问题；完整证据见[M2-22过程记录第24节](progress/M2/records/M2_22_CROSS_BORDER_RAG_EVALUATION_PLAN.md#24-m2-224r-03实施记录docx页眉页脚与原位图片ocr2026-09-08)。

M2-22.4R-02完成时：

- `LocalDoclingProvider`不再在主进程缓存`DocumentConverter`；每份增强文档都通过Windows兼容`spawn`进入一次性子进程，父进程按50 ms采样Worker及其子进程RSS，并对总时间、4 GiB默认RSS和64 MiB默认Snapshot设置边界；超时、崩溃、内存/返回包超限统一返回固定安全失败并清理进程树；
- 首份卡死、次份成功的真实`spawn`测试确认超时PID消失、后续PID不同且Worker模块计数重新从1开始；崩溃、1 MiB RSS上限、1 KiB结果上限和“已发快照但进程不退出”反例均安全失败。聚焦Router/配置/隔离为`73 passed`，完整单元为`974 passed, 2 skipped`，相邻Parser/File/Seed/Runner集成为`12 passed`；
- 显式本地Docling/RapidOCR扫描Smoke仍为`unusable → docling`并恢复2/2；子进程PID 31916在完成后不存在，本次`spawn/ready/total`为`4,958/4,975/77,721 ms`，采样峰值RSS `1,961,213,952`字节（约1.83 GiB）。报告为Git忽略的`output/m2_docling_process_isolation_smoke.json`，SHA-256为`87e1c6c1f242e19a77fa8938e93a629357e6bdf67c4bf0f7c6a22bc0cc007d89`；
- 全范围Ruff lint、154个`app`源码Mypy、编译、依赖、diff及Alembic current/heads/check通过；全范围格式检查仍只报告未修改的既有迁移测试一处差异。本步不处理DOCX视觉内容、解析后门禁、Chunk或索引；完整证据见[M2-22过程记录第23节](progress/M2/records/M2_22_CROSS_BORDER_RAG_EVALUATION_PLAN.md#23-m2-224r-02实施记录docling故障进程隔离2026-09-08)。

M2-22.4缺失证据诊断完成时：

- 只读诊断绑定既有Parser基线，8份问题文档的12条缺失全部归因：10条`route_selection_loss`，2条`ocr_extraction_loss`；10条外部Golden在Native全文和正确页均逐字命中且Token Recall 1.0，图文DOCX两条在Native/Docling均0 Token；
- 当前PDF复杂度启发式会因任一页的绘图/双栏信号把整份文档切到Docling；三个长文档的基线Docling/Native字符数分别为71,011/225,544、31,959/117,373、34,221/139,843。连续Docling探针还复现三次约120秒超时、OCR线程不退出和后续失效PDF句柄；
- 最终诊断8/8文档、12/12案例完成，耗时约26.13秒；专项与相邻测试16项、完整单元957项通过并跳过2项，全范围Ruff/格式、154个源码Mypy、编译、依赖和diff检查通过。诊断不连接API、数据库或Storage，不改生产Parser，不运行Chunk/索引/RAG；完整记录见[M2-22过程记录第20节](progress/M2/records/M2_22_CROSS_BORDER_RAG_EVALUATION_PLAN.md#20-m2-224-缺失证据诊断2026-09-08)。

M2-22.4基线完成时：

- 18份原件全部经过公开文件/文档API、隔离PostgreSQL/Storage、现有Parser Router和Canonical Artifact；18/18上传和解析完成，路由为Native 5、Docling 11、Hybrid 2，畸形PDF被422拒绝；
- 严格Parser事实恢复22/34（64.71%），其中合成18/20、真实跨境4/14、OCR字段2/4；延迟p50/p95/max为6,464/136,479/136,479 ms，进程峰值RSS约2.53 GiB，已明确暴露真实PDF增强解析的性能和完整性风险；
- Runner专项6项通过；完整后端为`1229 passed, 4 skipped, 1 failed`，唯一失败仍是既有上传Key月份写死为2026/08的范围外测试；Ruff、Mypy、编译、依赖、格式、Alembic和diff门禁通过；
- 评估租户/对象均清理为0，正式Seed恢复为10 files/documents/versions、9 ACL、10个pending版本和10个upload对象，M1可售125。完整记录见[M2-22过程记录第19节](progress/M2/records/M2_22_CROSS_BORDER_RAG_EVALUATION_PLAN.md#19-m2-224-实施记录真实摄取parserocr和基线恢复2026-09-08)。

M2-22.2完成时：

- 新增Manifest白名单驱动的受控准备脚本：只有显式授权、许可已核查、版本已固定且格式受支持的来源可以联网；拒绝重定向、错误Content-Type/文件签名、声明/流式超限、空间不足、半途失败、非白名单ID、目录越界和静默覆盖；原件只读，普通文件作确定性字节副本，少量合规图片可按固定版本封装PDF；
- 8份欧盟官方核心PDF完成真实下载与复核：raw和processed各8份、各`5,152,421`字节，逐份SHA-256一致，共275页且均为未加密、有可提取文本的PDF；Manifest记录真实大小、Hash、相对路径和转换身份。CORD/DocILE/Kleister仍为`planned + pending_review + download_allowed=false`，未下载全量数据集；总预算由180 MiB收紧到59 MiB；
- 下载合同与评估合同合并`91 passed`，完整单元`943 passed, 2 skipped`；Ruff lint、3个本步Python文件格式、151个`app`源文件Mypy、编译、依赖与`git diff --check`通过；全范围格式仍只报告未修改迁移测试的一处既有差异；
- 本步没有创建Smoke/Golden、写数据库或Storage、运行Parser/Chunk/检索/Reranker/Agent/Ragas，因此仍没有任何质量分数。完整记录见[M2-22过程记录第17节](progress/M2/records/M2_22_CROSS_BORDER_RAG_EVALUATION_PLAN.md#17-2026-09-07m2-222-受控下载hash校验和确定性转换)。

M2-22.1完成时：

- 框架无关评估合同冻结来源生命周期与许可、Golden可信Fixture引用、完整Chunk/检索配置、数据/代码/模型/Evaluator/Judge/Prompt运行身份、项目确定性与Ragas分栏结果、稳定序列化/Hash及200/300/600 MiB与3 GiB磁盘门禁；
- 11个候选来源全部保持`planned + pending_review + download_allowed=false`，实际大小、Hash、路径和转换字段为空；8个欧盟/德国候选进入未来核心组，3个CORD/Kleister/DocILE候选只属非核心诊断组；总下载预算180 MiB；
- 聚焦`79 passed`、指定相邻`57 passed`、合并`136 passed`、完整单元`931 passed, 2 skipped`；Ruff lint、本步格式、151个`app`源文件Mypy、编译和`git diff --check`通过；全范围格式仍只有未修改迁移测试的一处既有差异；
- 没有联网、下载、Ragas/RAG、数据库、Storage或生产参数行为，因此不能证明许可、真实文件、链路质量或任何分数。完整记录见[M2-22过程记录第16节](progress/M2/records/M2_22_CROSS_BORDER_RAG_EVALUATION_PLAN.md#16-2026-09-07m2-221-评估合同来源-manifest-和磁盘门禁)。

M2-21.12及整个M2-21完成时：

- Supervisor只对依赖已满足、Worker不同且能力只读的任务最多2路并发；公开G4验证两个真实Worker重叠、共享根Run/Trace、不同预算引用和ToolCall子Run归属。Business/Knowledge的Evidence子配额为4/8，总预留不超过根预算12，结果按TaskPlan顺序稳定合并；
- G0～G7均绑定实际可执行测试；权限/ACL/注入/循环/超时/Provider/数据库/Storage/Reranker/Evidence选定矩阵`150 passed`，聚焦并发回归`32 passed`；完整单元`852 passed, 2 skipped`，完整integration为`275 passed, 2 skipped, 1 failed`，唯一失败仍是范围外既有跨月文档解析用例；
- 显式真实BGE-M3离线检索Smoke `1 passed`并确认基线恢复；本步真实Agent Qwen Smoke因环境无Key为`1 skipped`，M2-21.8此前真实Qwen代表性Smoke证据仍保留但本步不声称复跑通过；
- Ruff、定向格式、150个`app`源文件Mypy、编译、依赖、`git diff --check`及Alembic current/heads/check通过；全范围格式仍只有未修改迁移测试的1处既有差异。全量后正式Seed恢复为10 files/documents/versions、9 ACL、零运行/发布数据、10 uploads及德国仓可售125。完整记录见[M2-21过程记录第33节](progress/M2/records/M2_21_ENGINEERED_MULTI_AGENT_PLAN.md#33-2026-09-07m2-2112-独立只读-worker-有界并行与-g0g7-收口矩阵)。

M2-21.11 完成时：

- 公开Gateway支持最多8条脱敏近期消息和2000字符旧消息摘要；`waiting_user`可由下一请求领取同一Supervisor根Run，继续未完成DAG或在没有Worker结果时最多Re-plan一次；恢复次数、请求ID、预算、截止时间和重复Tool签名均有界；
- `request_id`精确重放当时Checkpoint，确定消息ID避免重复Run/消息，换内容复用ID或活动根冲突返回409；恢复前和最终Checkpoint前重新验证当前身份、Capability、Evidence/File，跨请求撤权和Tool后撤权竞态均返回403并清空最新安全状态引用；
- 相邻单元`79 passed`、公开API`20 passed`、选定PostgreSQL相邻集成`31 passed`、完整单元`848 passed, 2 skipped`；完整integration为`270 passed, 2 skipped, 1 failed`，唯一失败仍是范围外既有文档解析用例；
- Ruff lint、本步格式、150个`app`源文件Mypy、编译、依赖、`git diff --check`与Alembic current/heads/check通过；全范围格式仍只有未修改迁移测试的1处既有差异。本步没有新Model/迁移，未验证并行、完整G0～G7、前端或真实Qwen长对话质量。完整记录见[M2-21过程记录第32节](progress/M2/records/M2_21_ENGINEERED_MULTI_AGENT_PLAN.md#32-2026-09-07m2-2111-有界记忆澄清恢复重新获权与重复提交保护)。

M2-21.10 完成时：

- 公开消息POST现在只依赖`AgentGateway`，静态门禁拒绝旧M1库存Graph/Registry重新直连；同一真实HTTP入口验证L0、Business单Tool、Knowledge单Tool、两个真实Worker与部分成功，ToolCall实际属于Worker子Run，并同步任务板、Checkpoint和答案Evidence；
- 本步聚焦28项、公开API文件14项、关键相邻单元100项、选定真实集成26项通过；完整单元`842 passed, 2 skipped`；完整integration为`264 passed, 2 skipped, 1 failed`，唯一失败仍是范围外既有文档解析用例；
- 正式收尾时先识别Docker Desktop停机导致14个API用例在Seed阶段连接5433超时，恢复既有PostgreSQL容器为healthy后，同一收口矩阵`58 passed`；Ruff lint、本步19个文件格式、149个`app`源文件Mypy和`git diff --check`通过；
- 当前不具备跨请求Checkpoint恢复、等待用户续跑、撤权重验、Re-plan、并行、完整G0～G7或前端展示；公开API集成使用确定性Provider，不能冒充真实Qwen生产质量。完整记录见[M2-21过程记录第31节](progress/M2/records/M2_21_ENGINEERED_MULTI_AGENT_PLAN.md#31-2026-09-07m2-2110-唯一-agent-gateway公开-api-迁移与持久化主路径接线)。

M2-21.9 完成时：

- 父子`AgentRun`、共享任务板、不可变Checkpoint和最终答案Evidence映射已经形成PostgreSQL Model/Repository/Service；复合身份外键、DAG外键/自依赖Check/循环Trigger、任务与Checkpoint版本冲突、状态哈希和12条Evidence上限均有真实数据库验证；
- 指定相邻回归`94 passed`，完整单元测试`840 passed, 2 skipped`；完整integration首次发现并修复本步旧迁移兼容问题，修复后排除唯一既有范围外文档解析失败为`259 passed, 2 skipped, 1 deselected`；
- 正式范围Ruff lint、本步文件格式、148个`app`源文件Mypy、编译、依赖和`git diff --check`通过；Alembic current/heads均为`20260905_0011 (head)`，upgrade/downgrade和Metadata无漂移通过；
- 当前只完成持久化层，尚未把公开API或现有Supervisor/Worker Runtime接入；不能证明跨请求恢复、撤权重验、并行或G0～G7公开整链。完整记录见[M2-21过程记录第30节](progress/M2/records/M2_21_ENGINEERED_MULTI_AGENT_PLAN.md#30-2026-09-05m2-219-父子run任务板checkpoint与答案evidence持久化)。

M2-21.8 完成时：

- 四角色严格`QwenAgentProvider`已接入现有Planner/Decision/Handoff/Answer协议：Planner任务槽和Capability枚举来自服务端可信Profile，Decision参数绑定真实Capability JSON Schema，Handoff不能改写公开上下文，模型不能生成身份、权限、父Run或预算；
- `AnswerEvidenceSet`把Observation支持的最多12条Evidence稳定编号为`[E1]`至`[E12]`，Provider与Supervisor Graph双层校验文本标签和真实UUID完全一致；伪造、重复、畸形、超限及无证据引用会拒绝；
- 聚焦回归`50 passed`，两个真实Worker选定相邻集成`21 passed`，完整单元测试`834 passed, 2 skipped`；显式真实Qwen Smoke `1 passed`，验证代表性规划、委派、Business行动建议、跨Worker计划与合成Evidence引用回答；
- `ruff check app tests scripts`通过，14个本步文件格式正确，146个`app`源文件Mypy、编译、依赖和`git diff --check`通过；全正式范围格式检查仍只命中未修改的既有迁移测试1处格式差异；
- 完整集成实际为`256 passed, 2 skipped, 1 failed`，唯一范围外失败是文档解析测试删除上传后预期异常未抛出，隔离复跑仍失败；本步不声称全量integration全绿，也未越界修改该Service；
- 本步未新增Tool、Worker、Graph节点、Model、迁移或API。真实Smoke只提出Action且回答使用合成Observation，不能证明真实Qwen+Tool端到端、生产模型质量、父子Run持久化、公开Agent Gateway、记忆或并行。完整记录见[M2-21过程记录第29节](progress/M2/records/M2_21_ENGINEERED_MULTI_AGENT_PLAN.md#29-2026-09-05m2-218-严格-qwen-与统一证据回答)。

M2-21.7 完成时：

- `KnowledgeWorker`已成为可委派真实Worker，只能在最多5次Decision内选择`search_knowledge`、`read_uploaded_file`、`get_evidence_detail`三个M2知识Tool；参数必须匹配Handoff公开查询及允许传递的Evidence/Artifact ID，所有执行继续经过Resolver、树形子预算和Harness；
- 真实PostgreSQL/pgvector/Storage验证覆盖知识搜索、文件读取、Evidence详情、成功无证据、ACL撤权、文件软删除和旧active版本排除；顺序L2按`Business → Knowledge`稳定执行并合并数据库Evidence和文件Artifact，允许部分成功的Knowledge任务失败时保留已完成Business结果并返回`completed + partial`；
- M2-21.7聚焦单元和集成测试`40 passed`，两个真实Worker及M1/M2知识Tool的选定相邻集成`48 passed`，完整单元测试`812 passed, 2 skipped`；
- `ruff check app tests scripts`通过，143个`app`源文件Mypy、编译、依赖和`git diff --check`通过；全正式范围格式检查仍只发现未修改的既有迁移测试有1处格式差异，本步没有越界修复；
- 测试仍使用确定性Provider而非Qwen；顺序L2的回滚型数据夹具使用内联Invoker测试接缝，但两个真实Worker、Harness、Tool、PostgreSQL和Storage均实际执行，Knowledge搜索另行通过真实Worker Runtime验证。统一Answer/Citation忠实性、父子Run持久化、公开API、记忆和并行仍未实现。完整记录见[M2-21过程记录第28节](progress/M2/records/M2_21_ENGINEERED_MULTI_AGENT_PLAN.md#28-2026-09-05m2-217-knowledge-worker-与顺序双-worker-l2)。

M2-21.6 完成时：

- 有界`BusinessDataWorker`已成为唯一可委派真实Worker；它只接收Resolver投影的两个M1业务Tool，每个Decision先扣子预算并经过严格Action、参数、公开任务范围、重复和Evidence验真；
- 真实Supervisor→Worker Runtime→Harness→M1 Tool→Service→Repository→PostgreSQL链已跑通只规格、精确库存、规格加库存和DE身份请求FR拒绝；ToolCall数分别1/1/2/1，Evidence数0/1/1/0；
- 聚焦测试`26 passed`，指定相邻单元回归`145 passed`，M1/Business真实PostgreSQL相邻集成`22 passed`，完整单元测试`803 passed, 2 skipped`；
- 正式范围Ruff通过，本步7个代码测试文件格式正确，142个`app`源文件Mypy、编译、依赖和`git diff --check`通过；
- 全正式范围格式检查仍只发现未修改的既有迁移测试有1处格式差异，本步没有越界修复；
- 本步仍使用确定性测试Provider；商品规格沿用M1合同没有Evidence，Knowledge Worker、真实Qwen、统一Citation、父子Run持久化、公开API和记忆均未实现。完整记录见[M2-21过程记录第27节](progress/M2/records/M2_21_ENGINEERED_MULTI_AGENT_PLAN.md#27-2026-09-05m2-216-有界-business-data-worker-与首条真实-l1-纵向链)。

M2-21.5 完成时：

- 通用Worker Runtime能从Handoff草稿程序注入真实Handoff/Worker Run/预算引用，按精确Worker ID分发，在可信`RunContext`、子预算、现有Harness适配和独立Session内执行；树形预算、重复/无进展、超时、回滚与安全错误均有确定性测试；
- 聚焦测试`20 passed`，指定相邻回归`145 passed`，完整单元测试`790 passed, 2 skipped`；
- 正式范围Ruff通过，13个本步新增/修改代码测试文件格式正确，140个`app`源文件Mypy、编译、依赖和`git diff --check`通过；
- 全正式范围格式检查仍只发现未修改的既有迁移测试有1处格式差异，本步没有越界修复；
- 本步只用SQLite内存库验证Worker事务/savepoint边界，没有真实Tool、PostgreSQL、Storage、外部Provider、配置或迁移；父子Run当前是内存Trace合同，持久化留到M2-21.9。完整记录见[M2-21过程记录第26节](progress/M2/records/M2_21_ENGINEERED_MULTI_AGENT_PLAN.md#26-2026-09-05m2-215-worker-runtime树形预算终止管理与-harness-适配)。

M2-21.4 完成时：

- 五节点最小Supervisor LangGraph已经通过同一严格合同跑通L0直接回答、L1一次委派、按依赖顺序的最小L2、追问、unsupported和有界停止；
- 聚焦测试`11 passed`，指定相邻回归`112 passed`，完整单元测试`770 passed, 2 skipped`；
- 正式范围Ruff通过，六个本步新增/修改代码测试文件格式正确，132个`app`源文件Mypy、编译、依赖和`git diff --check`通过；
- 全正式范围格式检查仍只发现未修改的既有迁移测试有1处格式差异，本步没有越界修复；
- 额外根目录Ruff检查命中旧原型目录既有98项检查问题和27个待格式化文件；本步正式`app tests scripts`范围通过，没有越界批量改写历史原型；
- 本步只运行确定性Mock Provider与测试Fake Worker，未经过Runtime/Harness、Tool、数据库、Storage、外部Provider、配置或迁移，不改变M2-20真实数据验证基线。完整记录见[M2-21过程记录第25节](progress/M2/records/M2_21_ENGINEERED_MULTI_AGENT_PLAN.md#25-2026-09-05m2-214-最小-supervisor-langgraph-与-fake-worker-闭环)。

M2-21.3 完成时：

- Planner/Decision/Handoff/Answer四类Provider协议、`WorkerCapabilityProfile`、程序输出校验器和确定性离线Mock已经建立；
- Agent Provider聚焦测试`16 passed`，指定相邻回归`129 passed`，完整单元测试`759 passed, 2 skipped`；
- 正式范围Ruff通过，六个新增/修改代码测试文件格式正确，130个`app`源文件Mypy、编译、依赖和`git diff --check`通过；
- 全正式范围格式检查仍只发现未修改的既有迁移测试有1处格式差异，本步没有越界修复；
- 本步未经过数据库、Storage、外部Provider、配置或迁移，不改变M2-20真实数据验证基线。完整记录见[M2-21过程记录第24节](progress/M2/records/M2_21_ENGINEERED_MULTI_AGENT_PLAN.md#24-2026-09-05m2-213-agent-provider-协议与确定性-mock)。

M2-21.2 完成时：

- M1精确两个、M2累计五个真实Tool已进入版本化不可变Catalog；Business Data/Knowledge Agent Definition分别限定2/3个Tool，但只处于`declared`且不可执行；
- Capability聚焦测试`12 passed`，指定相邻回归`61 passed`，完整单元测试`743 passed, 2 skipped`；
- 正式范围Ruff通过，六个新增文件格式正确，127个`app`源文件Mypy、编译、依赖和`git diff --check`通过；
- 全正式范围格式检查仍只发现未修改的既有迁移测试有1处格式差异，本步没有越界修复；
- 本步未经过数据库、Storage、外部Provider或迁移，不改变M2-20真实数据验证基线。完整记录见[M2-21过程记录第23节](progress/M2/records/M2_21_ENGINEERED_MULTI_AGENT_PLAN.md#23-2026-09-05m2-212-capability-catalogresolver-与-agent-definition)。

M2-21.1 完成时：

- 版本化Task DAG、五类互斥Action、Observation/Handoff/Worker Result、执行/业务双状态、安全状态外壳和G0～G7数据形状已经冻结；
- 新合同聚焦测试`31 passed`，指定相邻回归`73 passed`，完整单元测试`731 passed, 2 skipped`；
- 正式范围Ruff通过，四个新增文件格式正确，122个`app`源文件Mypy、编译、依赖和`git diff --check`通过；
- 全正式范围格式检查发现未修改的既有迁移测试有1处格式差异，本步没有越界修复；
- 本步未经过数据库、Storage、外部Provider或迁移，不改变M2-20真实数据验证基线。完整记录见[M2-21过程记录第22节](progress/M2/records/M2_21_ENGINEERED_MULTI_AGENT_PLAN.md#22-2026-09-05m2-211-严格合同状态外壳与迁移验收样本)。

M2-20.6 收口时：

- M2-20聚焦合同、Service、Tool和真实矩阵`93 passed`，M1/M2相邻回归`233 passed`；
- 排除既有跨月测试后`949 passed, 2 skipped, 1 deselected`；
- 默认全量`949 passed, 10 skipped, 1 failed`，唯一失败仍是既有上传Key写死月份的时间依赖用例；
- Ruff、253文件格式、120个`app`源文件Mypy、编译、依赖和Alembic门禁通过；
- Alembic继续为`20260902_0010 (head)`且无漂移，本步没有新增迁移；
- 正式Seed恢复为10 files、10 documents、10 versions、9 ACL，索引、Context、Evidence、ToolContextLink、AgentRun和ToolCall均为0；
- Storage只有10个uploads，M1德国仓可售库存仍为125。

完整命令、逐项结果、能证明和不能证明的边界见 [M2-20过程记录](progress/M2/records/M2_20_FILE_EVIDENCE_TOOLS.md)。

## 5. 当前风险与跨阶段问题

| 风险 | 影响 | 当前处理方向 |
|---|---|---|
| Reranker本机CPU成本 | 40题正式运行评分p95约28.58秒、峰值RSS约3.60 GiB，明显高于短文本探针 | 已确认每个候选池只评分一次、batch为2；后续先分析真实Chunk长度、CPU和批处理，再单独决定候选裁剪、GPU或独立服务，不在评估步改生产链 |
| Reranker无法恢复上游漏召回 | 正式34题仍有3题在所选Dense/Lexical候选中缺Golden；真实跨境Reranker为12/14=`85.71%` | M2-22.7已把`candidate_missing`留在原分母并区分评估完成与门禁失败；进入回答评估前单独讨论召回修复 |
| Context邻块被误当成精排恢复 | Top5 Anchor为31/34；邻块1+3000/4000把总覆盖补到32/34，其中1题只是相邻Chunk碰巧含Golden | 后续必须同时报告Anchor和总覆盖；召回/Reranker质量看Anchor，不把Neighbor命中写成精排找回 |
| DOCX物理页码与region公开Locator | `python-docx`不能给稳定渲染页码；M2-22.6R-01已让无精确坐标候选使用与source span一致的Canonical `block_number`，坏Block只隔离该名次并触发质量门禁 | 不伪造物理页码、不删除页眉/页脚候选；保持页/段落/表格/标题等精确坐标优先，Block只作可审计兜底 |
| Chunk标题真值与绑定 | R-04A已补齐标题精确来源与物理版面审计，最终56/56标题、0/11809边界且总门禁True | 保持v3来源审计；新失败按Parser Artifact、Chunk和Locator逐层定位，不把Chunk通过等同检索通过 |
| 既有跨月硬编码测试 | R-04收口已让夹具使用真实上传返回的Storage Key，跨月独立用例与完整后端均通过 | 保持生产Storage规则不变；未来测试继续从实际上传结果取Key，不拼接月份 |
| 数据库测试夹具会重置正式M2 Seed及固定Chunk | 历史集成测试会重建schema；若在固定语料创建后运行，会物理删除18文档ChunkSet | 会重置schema的测试必须先运行；随后恢复正式Seed并调用幂等语料准备器。普通查询和调depth/RRF/TopK不得进入重建路径；后续再单独加固测试数据库隔离 |
| Business商品规格没有Evidence | M2-21.8明确不伪造引用；只规格可作为已观察结构化结果，但没有可引用Evidence | 若后续要求规格也强制引用，先新增真实规格Evidence来源 |
| Qwen生产质量未收口 | M2-21.8代表性真实Smoke已通过；M2-21.12环境无Key而显式跳过复跑，仍未覆盖任意自然语言、真实Tool整链或负载 | M2-22/M5使用版本化评估集验证规划、行动、引用、延迟与预算 |
| Parser路由、Office视觉提取与Docling稳定性 | 扫描件Docling结果返回后的`shutdown_timeout`已修复，未放宽父进程安全门禁；正式复验恢复18/18、34/34、OCR 4/4。单件实测仍约101.9秒、峰值约1.96 GB，直接DOCX OCR尚无同级进程隔离 | Parser不再是当前Chunk门禁失败归因；保留滞留Worker拒收回归，吞吐、全局并发/背压和直接DOCX OCR进程隔离留给后续负载加固 |
| Ragas Judge偏差与依赖边界 | 固定Ragas 0.4.3和Qwen身份后单配置补跑；Precision/Recall/Relevancy分别21/27/27条有效。7个超时、13个HTTP 400欠费Provider失败、7个框架失败均无数值，Noise因需要回答全部跳过 | 完成样本均值必须连同样本数报告，不能外推为34题全量；外部账户恢复后若补缺须另行授权，不能换Judge或启动回答链掩盖缺失 |
| Citation确定性指标边界 | M2-22.8.1只能证明标签语法/编号、当前获权Evidence身份和Golden Evidence映射，字面要点/禁用断言也只认显式白名单 | 后续必须把身份合法、Golden映射、Ragas Faithfulness与人工语义复核分栏；近义改写未列白名单时先查规则数据，不能擅自改成模糊语义匹配制造通过 |
| Fake Answer报告被误当真实质量 | M2-22.8.2的Provider读取Golden规则并使用内存Context，只验证40题编排、缓存、Hash、失败保真和脱敏；全部Fake确定性通过也不代表Qwen/DeepSeek或真实RAG回答通过 | 报告强制`execution_mode=deterministic_fake`和`quality_gate_passed=None`；简历/README不得引用Fake分数，真实链、Provider和语义质量分别留给.8.3至.8.7 |
| 检索跨重建稳定性 | 同一Index内120条route稳定，但清理后重建的Hit/Recall@8复现、MRR/nDCG变化；Dense/Lexical/RRF同分兜底依赖新建Chunk UUID | 当前不改生产排序；后续若另行授权，评估以稳定Canonical Chunk身份作同分键，并增加跨重建回归 |
| 记忆与崩溃恢复边界 | 有界短期记忆、澄清同根恢复、撤权重验和一次Re-plan已完成；不是长期画像，未知执行结果的`running`根暂不自动抢占 | M5评估长对话与恢复租约，不擅自扩大记忆范围 |
| Worker并发规模边界 | 已证明两个独立只读Worker在单进程内有界重叠及预算/Session/Trace隔离；未做高并发、多进程或写操作冲突控制 | M5再做负载、背压和多进程评估；写能力必须另行设计审批与一致性边界 |
| README与旧面试指南仍含早期原型/原始完整版表述 | 直接用于投递会夸大或混淆当前实现 | M5作品化前按实际代码、评估和演示统一清理；当前不得直接照抄 |

M2-22.5已由R-04A正式收口；M2-22.6的Locator、确定性矩阵和单配置Ragas补跑均已完成；M2-22.7五个小步也已完成，固定18文档/18 ChunkSet/779 Chunk继续保留，正式结果选择Top5与“邻块1+3000 Token”Context候选。M2-22.8.1冻结了回答/Citation/拒答合同和确定性指标，M2-22.8.2又用Golden感知Fake跑通40题Runner、Run内缓存、逐题Hash和公开安全报告；它仍没有连接真实Gateway或模型，Fake质量门禁固定为`None`。Ragas历史缺失样本继续保留；真实跨境12/14未过90%门禁。当前停止并等待用户单独授权M2-22.8.3。

## 6. 最近完成摘要

- 2026-09-11：完成M2-22.8.2 Fake Answer Runner、公开安全报告与Run内缓存。固定40题在纯内存链中完整保留34+6，标准Fake运行每题只生成一次；同请求Run内复用，失败不缓存且原始异常被安全摘要替换。逐题报告仅保留问题/Context/规则/请求/答案的SHA-256、状态、指标和防篡改Trace Hash，递归拒绝正文、路径、Storage Key、tenant和原始错误；同输入报告字节确定，Fake质量门禁固定为`None`。RED为缺少报告模块，GREEN 11项，连同.8.1为21项、相邻评估回归135项，Ruff/Mypy/编译/diff门禁通过；未接真实Gateway、数据库、BGE或任何模型，等待M2-22.8.3单独授权。

- 2026-09-10：完成M2-22.8.1回答、Citation、拒答合同与确定性指标。固定配置完整继承M2-22.7.5的Top5与neighbor 1/3000 Token，40题继续严格保留34条可回答和6条安全题，并按真实14/合成10/诊断10/安全6聚合。逐题结果分开记录Context完整性、回答执行、要点/白名单、禁用断言、回答/拒答、Citation语法/重复/越界/不存在、获权Evidence、Golden Evidence和安全泄漏；上游缺Golden不会被归咎于Reranker或回答模型，计算失败/跳过保持非数值。Citation语义支持明确未实现。RED为缺少新模块，GREEN聚焦10项，相关单元回归124项及Ruff/Mypy/编译/diff门禁通过；本步未创建Runner/CLI/缓存、未接Gateway/数据库/Provider、未运行40题或任何模型，等待M2-22.8.2单独授权。

- 2026-09-10：用户确认模型切换采用“保留Qwen、并列新增DeepSeek、通过配置显式选择”的方案，不删除Qwen代码或历史验证，也不做失败后的静默跨Provider兜底。根据当前DeepSeek官方接口，计划默认文本模型为可配置的`deepseek-v4-flash`，通过Responses API的严格JSON Schema保持四角色结构边界并关闭thinking；M2-22.8修订为七步，在原合同/Fake/真实链之后插入双Provider接入，再做DeepSeek真实回答探针、Ragas生成评估和40题正式矩阵。当前只完成方案修订，运行时代码尚未修改。

- 2026-09-10：用户在理解M2-22.7三条漏召回的逐题原因后，接受当前真实跨境12/14=`85.71%`结果并决定暂不实施召回修复。该取舍只解除进入M2-22.8方案讨论的流程阻塞，不把`quality_gate_passed=False`改成True，也不删除34条可回答题中的失败样本。当时形成的六步回答评估草案已在用户确认保留Qwen并新增DeepSeek后修订为七步，运行时代码仍未修改。

- 2026-09-10：完成M2-22.7三条候选缺失的只读原因诊断。三条正确原文均完整存在于既定779个Chunk中，Dense排名分别33/42/39，Lexical均因中文问题与英文证据无词项交集而缺失；depth 20/30仍不能覆盖，depth 50虽能看见但RRF仅39/50/52。GPSR题的正确文档及部分答案Chunk已在Dense Top3，Context通过相邻Chunk补到完整Golden。诊断未修改生产代码、配置、Chunk或索引，前后固定语料身份一致。当前等待用户确认归因，再单独决定是否设计召回修复实验。

- 2026-09-10：完成M2-22.7.5固定18文档/40题正式BGE-Reranker与Context矩阵。没有重新上传、解析或切块；只在18个既有ChunkSet/779逻辑Chunk上新增并激活真实BGE-M3索引。34题Top5由RRF 27/34提升为Reranker 31/34，Top8保持31/34，按并列选小规则选择Top5；真实/合成/诊断分别12/14、10/10、9/10。邻块1+3000 Token把总Context覆盖提高到32/34，但Anchor仍31/34，不能冒充Reranker找回。安全6/6、泄漏0；真实跨境低于90%，因此`evaluation_completed=True`且`quality_gate_passed=False`。40次Provider评分总耗时771.923秒，p95约28.58秒，峰值RSS约3.60 GiB；临时报告Hash记录后删除。单元172项、无重切集成8项、真实BGE Smoke 3项及Ruff/Mypy/编译/依赖/diff门禁通过；三套Seed与固定语料、Storage、M1库存125最终基线复核通过。当前等待用户单独决定召回修复，不进入M2-22.8。

- 2026-09-10：完成M2-22.7.4固定本地BGE-Reranker小样本资源探针。用户授权恢复当前缓存中缺失的固定模型快照，6个文件共2,293,242,108字节并通过manifest/Hash复核；离线且不可用代理下完成6类×20候选真实CPU评分，加载26.318秒、评分p50/p95/max为4.812/6.352/6.397秒、峰值RSS 2045.113 MiB（增量1728.695 MiB）、effective batch 2、新存活子进程0。12次逻辑取分只有6次Provider调用，候选缺失/无答案不虚构名次，报告保持`quality_gate_passed=None`。聚焦及相邻45项、真实Smoke 3项、目标Ruff/Mypy、编译/依赖/diff通过；未访问或修改固定18文档/779 Chunk。随后M2-22.7.5已完成40题正式矩阵。

- 2026-09-10：完成M2-22.7.3固定语料与真实数据库权限链。用户确认上传/解析/切块只做一次，后续检索与Reranker实验复用现有ChunkSet；语料与索引身份分离，Embedding/FTS变化只新增IndexSet。正式持久语料为18 documents / 18 ChunkSets / 18 Fake IndexSets / 779 Chunk，第二次调用`created=False`且三层Hash完全不变；真实小样本经Dense/Lexical Top10、RRF 60、Fake Reranker Top5和Context Repository得到11候选/12 Context片段，前后Chunk均779。聚焦9项、相邻集成24项、单元72项、既有Runner集成1项及Ruff/Mypy/编译/diff门禁通过。没有运行真实BGE-Reranker或40题质量矩阵，等待M2-22.7.4单独授权。

- 2026-09-10：完成M2-22.7.2 Fake Runner、公开安全报告、CLI和Run内评分缓存。冻结40题运行仍保留34+6分栏，只执行Top5/Top8后在所选TopK跑6个Context点；278次逻辑取分由当前Run缓存压到40次Fake Provider调用，query、候选有序身份/正文Hash和完整模型身份参与缓存键，失败不缓存。40条逐题Trace均有Hash，报告不保存问题/正文/路径/Storage Key等私有内容，重复运行字节一致；Fake运行完成与真实质量门禁通过由`quality_gate_passed=None`强制分开。TDD RED为缺少报告模块，GREEN聚焦8项、相邻116项，Ruff、Mypy、编译和diff门禁通过。当前等待M2-22.7.3单独授权。

- 2026-09-10：完成M2-22.7.1评估配置、结果合同与确定性指标。冻结所选Chunk/检索身份、Hybrid最多20候选、Top5/Top8先筛选及所选TopK下6个Context点；34条可回答题与6条安全题均由合同锁定。逐题比较严格区分候选缺失、升排、降排和不变；Context分开计算整体/Anchor Golden覆盖，Golden相对冗余和Token预算利用率，空Context保留真实0，计算失败保持非数值。TDD RED为缺少新模块，GREEN聚焦13项；相邻评估合同111项、Ruff、Mypy、编译和diff门禁通过。本步未创建Runner、访问数据库或加载模型，等待M2-22.7.2单独授权。

- 2026-09-10：完成M2-22.6 Ragas检索语义评分补跑与最终收口。正式Run只重建`compact/100 + depth 10 + RRF 60`，完成18文档、40题、18个Index Set、779个Chunk、120条route list和1,430候选，未重跑10组/50点矩阵。34条可回答题的Ragas完成样本均值为Precision `.8024`（21条）、Recall `.9630`（27条）、Relevancy `.9815`（27条）；7个超时、13个Qwen HTTP 400欠费Provider失败、7个Ragas无效结果无数值，Noise 34条因本步无回答全部跳过。Hybrid Recall@8与miss跨重建复现，MRR/nDCG因同分兜底使用新Chunk UUID而变化，旧/新结果并列记录且未改生产排序。专项9、Runner/指标96、相邻153、允许单元680、固定本地BGE 4均通过；允许集成140通过、2跳过、1个历史M1 Seed清场失败。报告Hash记录后删除，三套Seed重跑，最终数据库/Storage/M1基线干净。未进入M2-22.7。

- 2026-09-09：完成M2-22.6R-01和正式确定性检索矩阵。无精确坐标DOCX候选以受校验Canonical Block降级，原Dense第4名页眉Chunk仍保持第4名并得到`block_number=1`；坏Block RED证明只隔离单个名次、后续不前移、RRF使用原始排名，报告完整性门禁失败。正式Run完成10组Chunk、50点、180个Index Set、6,000条路由列表、106,518候选且映射失败0；筛出`compact/100 + depth 10 + RRF 60`，真实跨境Hybrid Hit/Recall@8=`0.8571`、MRR@10=`0.4817`、nDCG@10=`0.5692`，34条可回答总体Hybrid Hit/Recall@8=`0.9118`。ACL/软删除/inactive/tenant泄漏0，120路稳定性复跑0变化；生产默认未改。Ragas 34条正式样本因外部Judge数据发送权限未获分数，状态严格分为Judge失败、框架失败与纯检索不适用跳过。专项`177 passed`、相邻`136 passed, 4 skipped`并补跑真实BGE `4 passed`、允许单元`625 passed, 2 skipped`；允许集成`130 passed, 3 skipped, 1 failed`，唯一失败为旧M1 Seed测试清场顺序与正式M2外键冲突。当前等待明确外发授权，不进入M2-22.7。

- 2026-09-09：M2-22.6评估器实现并真实运行到首组Dense，但完整矩阵受阻。固定10组Chunk、深度10/20/30和RRF 20/60/100按两阶段筛选；项目确定性指标、完整Trace、四类分组、过滤/稳定性、Ragas 0.4.3检索适配及失败非数值合同已实现。专项与真实FTS/pgvector/RRF集成为`13 passed`，静态工程门禁通过。正式运行解析18/18、查询40/40并完成`compact/80`全量BGE/Index；首题Dense@10第4名为无公开坐标的DOCX页眉/页脚Chunk，最早缺口定位为Parser Artifact的region Locator，不能绕过评分。生产默认未改；失败数据/临时报告清零，正式Seed恢复`10/10/10/9/10 uploads/0 ChunkSet/IndexSet/Chunk/M1 125/clean=True`。等待单独授权M2-22.6R-01，不进入M2-22.7。

- 2026-09-09：实际运行M2-22.5R-04正式Chunk矩阵。18/18文档通过Parser/R04，报告v2运行状态`completed`；4组首轮后按冻结策略选择`chunk-large`与`chunk-medium`，各扫描overlap 80/100/120，共评估10组完整配置。`700/850/120`为417个Chunk，Token min/p50/p95/max=`6/685/699/803`、显式重叠冗余15.99%；34/34内容Golden和Locator、证据范围覆盖100%、26/26人工标题关系、45/45表格、DOCX页眉/页脚/图片OCR/前后文、18/18顺序/Locator/确定性及0空Chunk均通过。总门禁仍为False：整体标题55/56，边界断裂90/9750，其中段落9598/9687。失败分布和代码核对定位到R-02把纯标题从正文抽到元数据后，R-03边界统计仍逐行要求其出现在`body_text`，而Chunk Artifact未记录标题精确源范围；扫描入库单另有1个Canonical标题绑定未被fallback证明。未改Parser、Chunk默认参数、Golden或R04阈值；专项`101 passed`、相邻集成`20 passed`、完整允许单元`367 passed, 2 skipped`。报告SHA-256为`ecf16a31fe77ad1dfc39413b7a9bc3bd8ea2a37644be50dd879c1da1fc425fbd`，记录证据后已删除；评估行/ChunkSet/Storage对象均为0，正式基线恢复`10/10/10/9/10 uploads/0 ChunkSet/M1 125/clean=True`。当前受阻并停止，等待单独授权最小审计合同修复，不进入M2-22.6。

- 2026-09-08：完成M2-22.5R-03标题质量门禁防伪与报告语义。标题不再因`heading_hints`或字符串出现直接计为通过；对有人工Golden的文档，必须在同一个文本Chunk中同时满足完整`heading_path`、非标题正文锚点、Parser真实标题来源、正文页码与source span覆盖以及检索视图标题上下文。标题空壳、只复制标题文本、伪造父子关系、缺失Parser提示和错误Locator反例均转绿；4份真实问题PDF的26/26关系通过严格新指标。Chunk报告升级为v2，记录标题数据版本/Hash/本次案例数，总门禁改为“冻结候选的重叠配置中至少一组完整通过”，失败实验配置仍保留。TDD RED为`6 failed, 4 passed`；专项`101 passed`，真实标题文件`6 passed`，完整允许单元`371 passed, 2 skipped`；5文档真实Runner Smoke通过并覆盖4/4双栏标题关系，相邻数据库集成随后为`20 passed`。本步未运行R-04正式18文档矩阵或任何禁止下游，当前停止等待R-04单独授权。

- 2026-09-08：用户逐页查看OSS与GPSR争议版面后确认两组标题明显同级，纠正了此前由助手人工冻结的5条错误父子关系。没有修改Parser Artifact、Locator、生产Chunk规则或R04阈值；只把标题真值升级为`m2-chunk-heading-golden-v2`（SHA-256 `c4c4b78313118bc9a9e646cd1e3479f7ba71e9a76eb15e982fee1060d12aa4a6`），使4份真实问题PDF达到26/26标题正文关系且保持43/43非标题拒绝。专项`22 passed`、相邻合同`110 passed`、数据库集成`19 passed`；完整允许单元为`367 passed, 2 skipped, 1 failed`，唯一失败是未实施R-03的标题空壳防伪。集成后已恢复`10/10/10/9/10 uploads/0 ChunkSet/M1 125/clean=True`，5张临时视觉预览已删除，原PDF未改。R-02现已完成并停止，不进入R-03、R-04或M2-22.6。

- 2026-09-08：实施M2-22.5R-02确定性标题元数据绑定主体，但真实语义层级验收受阻。Chunker v2在正文Token窗口前按真实PDF行号、字符范围和坐标识别标题，把纯标题从`body_text`抽离并注入后续正文`heading_path`；编号/同行正文保留真实source span，双栏按同栏坐标绑定，多行标题确定性合并，项目符号、金额、引用编号及字段标签/值不提升。合成Chunk合同14/14通过；4份真实问题PDF的26条正文绑定由4/26提升到21/26，43/43已知非标题未进入元数据。剩余OSS 4条与PDF原生Outline层级冲突、GPSR 1条没有Outline/容器父关系，未用词语硬编码或页面顺序猜测制造通过。完整允许单元为`366 passed, 2 skipped, 2 failed`：除这组5条聚合RED外，另一个失败仍是未实施R-03的标题空壳防伪；相邻数据库集成19/19和工程门禁通过，正式基线恢复`10/10/10/9/10 uploads/0 ChunkSet/M1 125/clean=True`。本步未跑18文档7组正式矩阵或任何禁止下游，当前停止等待层级真值方案，不进入R-03或M2-22.6。

- 2026-09-08：完成M2-22.5R-01B的Docling一次性Worker收尾修复。完整结果或固定失败消息同步写完并关闭Pipe后，正式Worker以进程级方式确定性退出；父进程的2秒收尾窗口、活进程拒收、总时限、RSS/Snapshot上限和严格复验不变。故意滞留Worker仍被拒绝。真实扫描件Smoke恢复2/2并确认PID消失；干净基线上的正式矩阵恢复18/18解析、34/34 Golden、OCR 4/4、18/18 R04接受，评估行/对象清零并恢复正式10份数据与M1库存125。完整允许单元`370 passed, 2 skipped, 3 failed`，3个失败仍只属于未实施的R-02标题RED；相邻集成21项和工程门禁通过。当前停止等待R-02单独授权，不进入M2-22.6。

- 2026-09-08：用户确认修订标题真值口径后，完成M2-22.5R-01A可信结构标题Golden冻结。4份问题PDF的85条Parser提示全部分类为38条独立标题、4条组合标题片段和43条非标题；另冻结26条带来源页、完整`heading_path`、正文锚点及同栏/顺序关系的正式案例。新数据Hash为`93428d44fe539ed4eafbed6b80169818fc273c6c675a807de887fa20c3aa9c17`；专项5项、相邻89项、Ruff、156源码Mypy及编译通过，视觉审计临时文件已删除。审计证明双栏正文缺少行级坐标，已按防猜测条件停止并提交Parser Locator增补方案；生产Parser/Chunker、R04、34条内容Golden、数据库/Storage和下游均未改动或运行。

- 2026-09-08：完成M2-22.5R-01合同反例与真实提示审计，未修改生产Chunker。旧实现定向测试为预期`3 failed, 14 passed`，冻结了编号/同行标题未进入元数据、多级子标题未绑定正文、标题空壳被指标误收三个缺口；Ruff定向检查通过。对4份失败文档85条`heading_hints`只读复核得到整行精确29、同行唯一21、歧义1、最终页文本缺失34，并确认若干提示其实是项目符号、金额或字段值。由此暂停第28节原`152/152`假设，建议保留152条提示作Parser诊断，另建人工冻结的可信结构标题Golden作为Chunk验收真值。该口径随后已获用户确认并按上一条摘要完成R-01A；没有写数据库/Storage或运行任何禁止的下游功能。

- 2026-09-08：完成M2-22.5 Chunk质量矩阵的实现和真实运行，但质量门禁如实为False。18份R04合格文档通过现有Chunk Service跑完4组首轮配置和`chunk-large`的80/100/120重叠扫描；最强`700/850/120`达到34/34 Golden及Locator、9687/9687段落、0/9750边界断裂、45/45表格、18/18顺序/Locator完整性/确定性，DOCX页眉、页脚、图片OCR及前后文均1/1，Token分布`2/684/699/805`、重叠率16.00%。标题109/152的真实缺口归因Chunk规则，未改Golden、R04阈值或生产默认值。运行后评估数据清零并恢复10份正式文档、0正式ChunkSet和M1库存125；专项84项、相邻单元173项、完整允许范围单元442项及集成60项通过。相邻集成另如实保留旧File API夹具6个setup error；完整报告见M2-22记录第27节。当前停止等待用户理解和单独授权修复，不进入M2-22.6。

- 2026-09-08：用户进一步确认M2-22.8R的调用成本原则：意图识别不得固定变成每个请求额外的一次LLM调用。高置信明确请求优先由程序直接分流；不确定请求才用一次结构化模型输出同时完成意图、路径和参数提取。L0不应再叠加独立分类调用；明确Business查询使用Tool与确定性格式化；Knowledge和固定复合请求只保留检索后回答或跨源综合确实需要的模型调用。这些是待M2-22.8R实测的设计目标，不是已实现成果。

- 2026-09-08：用户确认调整M2后续顺序：M2-22.5至.8仍先完成RAG分层评估；RAG复核后、M2-22.9之前插入M2-22.8R意图识别与执行分流。简单查询应绕过Supervisor，固定复合查询走受控Pipeline，复杂任务才进入Supervisor/Worker；M2-22.9只评估改造后最终轨迹。当前只更新文档顺序与范围，未授权实施M2-22.8R，下一动作仍是等待M2-22.5单独授权。

- 2026-09-08：完成M2-22.4R-04解析质量门禁与拒绝索引。Router在最终选路后生成严格、可审计的`m2-post-parse-quality-v1`决定；健康Native保留率低于70%、PDF逐页文字突降或扫描页未恢复、DOCX大图空OCR且缺少正文上下文会拒绝，普通大图空OCR只告警。Parser Service仅发布已接受的新产物，拒绝链路不会写Parsed Storage或进入`ready`，Index Service集成确认0个Index Set。18份正式评估文档达到34/34 Golden、4/4 OCR，18个质量决定全部接受、0告警；完整后端`1287 passed, 14 skipped`，工程门禁通过。M2-22.5及后续索引/检索/Ragas没有开始。

- 2026-09-08：完成M2-22.4R-03 DOCX页眉/页脚与原位图片OCR。`DocxParser` v2单独提取Section页眉/页脚，并沿正文Run的`wp:inline`锚点保持“前文→图片OCR→后文”；图片外链、数量、单图/总字节和像素受限，同Hash重复图片只OCR一次但保留每个出现位置。Canonical以可选`m2-docx-source-v1`扩展记录来源、图片Hash/尺寸、Provider/版本/置信度，普通v1 Block旧形状和Hash兼容；Markdown显示`[页眉]/[页脚]/[图片内容]`。真实Router保持Native并找回两条目标，OCR平均置信度约0.993；专项相邻116项、完整单元990项和显式真实Smoke通过，2项跳过。全量另有5个测试顺序日志捕获失败但隔离复跑全绿，唯一独立失败仍是既有2026/08跨月测试。本步未实现R-04、Chunk矩阵或索引。

- 2026-09-08：完成M2-22.4R-02 Docling故障进程隔离。每份Docling任务现在使用Windows `spawn`一次性子进程，父进程只传递非秘密受控配置和已受限字节，并以50 ms采样RSS、150秒默认总时限、4 GiB默认RSS及64 MiB默认Snapshot约束任务；成功结果回到父进程后由严格`DoclingParseSnapshot`重新校验，超时、崩溃、内存/结果超限或发送结果后仍不退出均统一为固定错误并终止进程树。完整单元`974 passed, 2 skipped`，相邻集成`12 passed`。真实扫描PDF仍恢复2/2，实测子进程创建4.958秒、总耗时77.721秒、峰值约1.83 GiB且PID完成后消失。Ruff、Mypy、编译、依赖、diff和Alembic门禁通过；本步未实现R-03/R-04或运行Chunk/索引/RAG。

- 2026-09-08：完成M2-22.4R-01 Native文本健康度与PDF无损路由。新的确定性`m2-native-text-health-v1`用有效Unicode字符比例、整份最低文字、内容页覆盖及扫描/低文字告警产出`healthy/suspect/unusable`，并连同阈值进入路由审计；健康PDF的表格/双栏标签只作提示，不再触发整文档Docling覆盖。TDD RED为`9 failed, 54 passed`，最终聚焦扩展`85 passed`、完整单元`966 passed, 2 skipped`、相邻真实集成`12 passed`；8份官方PDF全部`healthy/native`并恢复14/14，5份复杂合成文档真实Docling路由为Native 2 / Docling 1 / Hybrid 2，扫描OCR 2/2，整体8/10，未恢复的2条仍是R-03的DOCX页眉/图片问题。全范围Ruff、154源码Mypy、编译、依赖和diff检查通过；全仓格式检查仅保留既有未修改迁移测试的1处差异。本步未实现R-02至R-04、未运行Chunk/索引/RAG。

- 2026-09-08：用户确认M2-22.4R四步Parser修复总体方案，该次首先且只完成文档固化。R-01校准Native确定性文本健康度并阻止健康PDF被整文档Docling覆盖；R-02以独立进程隔离Docling超时/崩溃；R-03分别提取DOCX页眉/页脚并按Run位置插入带`[图片内容]`派生标签和结构化来源的inline图片OCR；R-04落实70%全文突降、逐页少于10字符、图片大于5KiB空OCR等阻断/告警规则，再以18文档34条Golden收口。源定义复核还纠正“两条都是图片OCR”的粗分类：实际为1条页眉普通文字和1条正文图片文字。该文档固化步骤当时没有修改生产代码、配置、迁移或测试；R-01后续已获单独授权并按上一条摘要完成，M2-22.5仍暂停。

- 2026-09-08：完成M2-22.4缺失证据只读诊断。诊断器绑定既有基线，只重跑8份问题文档并对Native、Docling和基线selected Artifact做无原文信号比较；12条缺失中10条在Native全文和正确页均逐字命中、Token Recall 1.0，确认是整文档路由选择Docling后的损失。自动诊断当时将DOCX的2条统一归为`ocr_extraction_loss`，后续按源定义复核为1条页眉普通文字未提取、1条正文图片未OCR。初版连续Docling探针复现三次约120秒超时、OCR线程不退出及后续失效PDF句柄后人工停止；最终改为Native优先、仅对未归因件运行增强探针，8/8文档、12/12案例在约26.13秒内完成。相邻16项、完整单元957项通过并跳过2项，全范围Ruff/格式、154源码Mypy、编译、依赖与diff检查通过；未改生产Parser、写库、运行Chunk或索引。该诊断随后已进入第21节的已确认修复方案，M2-22.5继续暂停。

- 2026-09-08：完成M2-22.4真实摄取、Parser/OCR和基线恢复。18份选定原件经公开上传/建文档API、隔离PostgreSQL/Storage和现有Parser Router全部发布Canonical Artifact；路由Native 5、Docling 11、Hybrid 2。严格Golden原文恢复22/34，合成18/20、真实跨境4/14、OCR 2/4；p95约136秒、峰值RSS约2.53 GiB，证明增强解析是当前显著上游瓶颈。畸形PDF被拒；合法Seed DOCX暴露并修复上传层20倍ZIP误拒，现与Parser的200倍及100 MiB绝对上限一致。Runner专项6项通过，完整后端1229项通过、4项跳过、唯一失败为既有跨月硬编码用例；评估数据清零且正式10文档/M1库存125恢复。该基线完成后已由随后获批的第20节诊断继续归因。

- 2026-09-08：完成M2-22.3的40条Debug Smoke与人工Golden冻结。数据包含10条普通事实、8条表格/公式、6条OCR/复杂布局、6条跨章节流程、4条中英德多语言和6条ACL/版本/无证据/未知安全拒答；34条可回答题均绑定文档、原文范围和答案要点，数据字节Hash固定。外部证据已逐条在M2-22.2本地官方PDF的声明页核对；同时纠正Safety Gate文件为告警A12/01039/20、2026-09-07 API导出版本，不再把导出元数据误作告警发布日期。专项5项、M2-22相邻96项、完整单元948项通过，2项跳过；该步尚未实现Runner、写库或运行RAG/Ragas，完成时等待M2-22.4单独授权。

- 2026-09-07：完成M2-22.2受控下载、Hash校验和确定性转换。Manifest是唯一URL白名单，许可/版本/空间/格式/大小不满足即拒绝；禁止自动重定向和静默覆盖，原件只读，普通PDF作固定版本字节副本，已固定Hash支持新环境安全重建。8份欧盟官方核心PDF真实下载并验证，raw/processed各8份和5,152,421字节，共275页；3个诊断全量候选继续planned且未下载，总预算收紧至59 MiB。下载+合同91项、完整单元943项通过；未创建Smoke/Golden、写库、运行RAG/Ragas或修改生产参数，当前等待M2-22.3单独授权。

- 2026-09-07：完成M2-22.1严格评估合同、来源Manifest和纯计算磁盘门禁。来源、许可和四态生命周期互相校验；Golden只引用可信Fixture；完整结构感知Chunk/检索配置与数据、代码、模型、Evaluator/Judge/Prompt身份可追溯；项目确定性与Ragas结果分栏，框架/Judge失败不得伪装0分。Manifest登记8个欧盟/德国核心候选及3个非核心诊断候选，全部planned、许可待核查、无实际大小/Hash/路径，总预算180 MiB。聚焦79项、完整单元931项通过；未联网、下载、安装Ragas、运行RAG、写库或修改生产参数；该步完成时等待M2-22.2单独授权。

- 2026-09-07：形成并按用户确认修订[M2-22跨境电商RAG与多Agent评估方案](progress/M2/records/M2_22_CROSS_BORDER_RAG_EVALUATION_PLAN.md)。现有10份约243.5 KiB的小文件继续作为工程回归集；计划在不超过200 MiB原始外部资料的门禁内增加真实跨境资料。当前切块基线被准确记录为结构感知`target=600/max=700/overlap=100`，实验改为完整配置和隔离变量；项目代码负责Parser/OCR/Chunk、Precision/Recall/Hit Rate/MRR/nDCG、权限/Citation/资源，Ragas在.6/.8评检索与生成语义，固定Test与Bad Case人工复核，RAG复核后再单独决定多Agent。当前仅更新文档，未安装Ragas、下载、写库、实现Runner或修改生产参数，等待M2-22.1单独授权。
- 2026-09-07：完成M2-21.12及整个M2-21十二步收口。Supervisor只对依赖已满足、不同Worker、只读能力任务最多2路并发；公开G4验证两个真实Worker重叠、独立子预算/Session/Trace/ToolCall归属和稳定合并，角色Evidence配额4+8不超过根上限12；同批异常会等待全部Worker收束后再安全返回。G0～G7均映射到实际测试，选定矩阵150项、完整单元852项和integration 275项通过；integration另有1项范围外既有跨月解析失败。真实BGE Smoke通过并恢复Seed，Qwen因本机无Key显式跳过；当前停止等待M2-22单独授权。
- 2026-09-07：完成M2-21.11有界记忆、澄清同根恢复、跨请求重新获权、一次Re-plan和重复提交保护。消息POST支持可选`request_id`，Checkpoint保存有界脱敏消息与请求/恢复计数，恢复累计预算及旧Tool签名；重复请求精确重放，换内容复用返回409；恢复前与最终保存前撤权均安全返回403并清空最新状态引用。公开API20项、完整单元848项和选定集成31项通过；完整integration为270通过、2跳过、1项范围外既有文档解析失败。当前停止等待M2-21.12并行/完整矩阵单独授权。
- 2026-09-07：正式完成M2-21.10唯一Agent Gateway、公开聊天API迁移与持久化主路径接线。消息POST不再导入或构造旧M1库存Graph，Gateway先建可信Supervisor根Run、再保存TaskPlan，经Resolver/Supervisor/Worker Runtime运行Business/Knowledge Worker和Harness真实Tool；ToolCall绑定Worker子Run，任务双状态、Checkpoint、答案Evidence与助手消息进入同一审计链，公开Evidence返回前重新授权。公开API文件14项、完整单元842项、选定真实集成26项及收口矩阵58项通过；完整integration为264通过、2跳过、1项范围外既有文档解析失败。当前停止等待M2-21.11跨请求记忆、恢复与Re-plan单独授权。
- 2026-09-05：完成M2-21.9父子Run、共享任务板、Checkpoint和答案Evidence持久化。旧M1 Run保持`legacy`兼容；Supervisor/Worker父子树以tenant/user/thread复合外键和共享Trace关联；规范化任务边由外键、自依赖Check和递归Trigger拒绝非法DAG；任务与Checkpoint使用预期版本防覆盖，Checkpoint稳定序列化、限长并校验SHA-256，最终Evidence保持同tenant、唯一、连续`[E1]`至`[E12]`。相邻94项、完整单元840项及排除唯一既有失败后的integration 259项通过；Alembic升级到唯一`20260905_0011`且无漂移。当前未迁移公开API或接线现有Graph/Worker，等待M2-21.10单独授权。
- 2026-09-05：完成M2-21.8严格Qwen与统一证据回答。四角色Provider使用HTTPS OpenAI-compatible接口、关闭模型搜索/思考扩展并要求角色专属严格JSON Schema；Planner按服务端Worker槽位和Capability枚举生成任务，Decision参数再经真实Capability Schema复验，Handoff公开上下文由程序保留。Answer Evidence Set把Observation支持的最多12条Evidence映射为`[E1]`至`[E12]`，Provider和Graph双层拒绝伪造/错配引用。聚焦50项、相邻集成21项、完整单元834项及真实Qwen Smoke 1项通过；完整集成为256通过、2跳过、1项范围外文档解析失败，未掩盖或越界修复。未新增Tool/Worker/Graph节点、持久化或API，当前等待M2-21.9单独授权。
- 2026-09-05：完成M2-21.7 Knowledge Worker与顺序双Worker L2。Knowledge Worker经Resolver只获得`search_knowledge/read_uploaded_file/get_evidence_detail`，Action参数受Handoff查询和允许传递的Evidence/Artifact ID约束，Tool公开结果先扁平化再进入有界Agent状态；真实PostgreSQL/pgvector/Storage覆盖搜索、文件、Evidence详情、无证据、ACL、软删除和旧active，顺序L2稳定执行`Business → Knowledge`并合并引用，一个允许部分成功的Knowledge任务失败时保留Business结果并返回`completed + partial`。聚焦40项、选定真实集成48项、完整单元812项通过；当前仍是确定性Provider，Qwen、统一Citation校验、持久化、API、记忆和并行未实现，等待M2-21.8单独授权。
- 2026-09-05：完成M2-21.6有界Business Data Worker与首条真实L1纵向链。Worker通过Resolver只获得`get_product_spec/search_inventory`，每次Action经过子预算、参数/任务范围、重复和Evidence验真；真实Supervisor→Runtime→Harness→M1 Tool→Service→Repository→PostgreSQL矩阵跑通只规格、精确库存、规格加库存及FR越权拒绝，ToolCall数1/1/2/1、Evidence数0/1/1/0。聚焦26项、相邻单元145项、真实集成22项、完整单元803项通过；当前仍使用确定性Provider，Knowledge Worker、真实Qwen、统一引用、父子Run持久化和API未实现，等待M2-21.7单独授权。
- 2026-09-05：完成第二张“M2知识检索真实调用时序图”。图按真实代码展示内部调用方、`search_knowledge`、Harness、固定KnowledgeSearchService、权限前置Hybrid/RRF、BGE Provider、PostgreSQL及Context/Evidence原子闭环，并明确这不是公开知识聊天入口。Archify Showcase校验9/9、0错误、0警告，四种桌面视口与明暗主题无溢出，人工视觉检查通过；本步未修改运行代码、未运行应用测试、未开始M2-21.6。完整证据见[M2架构学习图记录](progress/M2/records/M2_ARCHITECTURE_LEARNING_MAPS.md)。
- 2026-09-05：完成M2-21.5通用Worker Runtime、树形预算、终止管理与Harness适配。Runtime把模型只能生成的`HandoffDraft`转换为程序拥有ID/父Run/预算引用的`AgentHandoff`，按精确Worker ID分发，在可信上下文、独立Session和现有Harness边界内运行；根/子预算原子限制调用、Token、Evidence、任务、委派、深度和共享时间，重复、无进展、超时和原始异常安全终止，未用子配额关闭后归还。聚焦20项、相邻145项、完整单元790项通过；子Trace暂存内存且没有真实Worker/Tool、PostgreSQL父子Run、Qwen、API或后续能力，当前等待M2-21.6单独授权。
- 2026-09-05：完成M2-21.4最小Supervisor LangGraph与Fake Worker闭环。五节点控制图使用Resolver安全Profile、确定性Mock Provider和测试Fake Worker跑通L0直接回答、L1一次Handoff草稿、按DAG依赖的顺序L2、追问、unsupported、错误Worker拒绝、原始异常脱敏及重复/步数终止；Observation/WorkerResult在最终回答前进入安全状态。聚焦11项、相邻112项、完整单元770项通过；没有实现Worker Runtime、真实AgentHandoff预算、Harness/Tool、真实Worker、Qwen、持久化或API，当前等待M2-21.5单独授权。
- 2026-09-05：完成第一张“当前项目框架总览图”。交互式HTML和可编辑JSON覆盖公开M1库存主链、M2知识底座、服务端可信执行与持久化边界，并明确M2知识Tool尚未进入公开聊天、模型不能构造可信身份/真实预算、Context/Evidence上限12以及Supervisor/Worker尚未成为运行路径。Archify showcase校验9/9、0错误、0警告，27个固定修订源码引用通过，四种桌面视口与明暗主题浏览器检查通过；本步未修改运行代码、未运行应用测试、未开始M2-21.3。完整记录见[M2架构学习图记录](progress/M2/records/M2_ARCHITECTURE_LEARNING_MAPS.md)。
- 2026-09-05：完成M2-21.3 Agent Provider协议与确定性Mock。四类可替换异步协议分别负责计划、单次行动、公开Handoff草稿和终态回答；WorkerCapabilityProfile绑定Worker与1～5个获准能力，程序校验目标漂移、交叉归属、未知任务/能力/Worker、Evidence最低数量与引用来源；真实Handoff ID/预算仍由后续Runtime掌握。聚焦16项、相邻129项、完整单元759项通过；没有实现Supervisor Graph、Worker Runtime、真实Worker、Qwen、持久化或API，当前等待M2-21.4单独授权。
- 2026-09-05：完成M2-21.2 Capability Catalog/Resolver与Agent Definition。M1两个、M2累计五个真实Tool通过适配层进入版本化不可变Catalog；Business Data/Knowledge分别限定2/3个Tool，两个Worker只登记为`declared`且不会冒充可执行Agent；模型只能提交有界唯一能力ID，Resolver按可信角色、Worker白名单和实现状态稳定筛选并返回脱敏摘要。聚焦12项、相邻61项、完整单元743项通过；没有实现Provider、Graph、Runtime、真实Worker、Qwen、持久化或API，当前等待M2-21.3单独授权。
- 2026-09-05：完成M2-21.1严格合同、Checkpoint安全状态外壳和版本化G0～G7迁移验收夹具。Task DAG拒绝重复/缺失/自依赖/循环，五类Action严格互斥，Observation/Handoff/Worker Result有界且脱敏，执行状态与业务结果分离，模型载荷不能注入身份、权限、父Run或真实预算；聚焦31项、相邻73项、完整单元731项通过。没有实现Resolver、Provider、Graph、Worker、Qwen、持久化、API或后续步骤，当前等待M2-21.2单独授权。
- 2026-09-04：按秋招AI应用岗位目标完成M2-21方案复核并获用户确认；完整保留Supervisor、两个真实Worker、Capability Catalog、Handoff、父子Run、Checkpoint、短期记忆、树形预算、真实Qwen、引用、并行及M4/M5，并明确公开聊天最终只经过Agent Gateway，旧M1固定Graph仅作内部兼容/回归，Business Worker以有界Action/Observation自主选择Tool，真实Qwen＋统一引用回答前移到M2-21.8。当前先讲清整个M2-21，未授权M2-21.1或任何运行代码。
- 2026-09-03：M4推荐版正式阶段方案已确认并建立独立阶段目录。首版复用Supervisor、Business Data/Knowledge Worker，只新增Web Research Worker；冻结`search_public_web`＋`read_public_source`、Fake/Tavily Provider、长网页有界Evidence、顺序后有界并行、PostgreSQL任务/租约/Checkpoint、Markdown与`cross-border-market-research` Skill；明确不做独立Analysis/Report Worker、PDF、图表、MCP和Redis/Celery。本次只更新文档，M4状态为待开始，不授权M4-01或任何运行代码。
- 2026-09-03（历史节点，后续已由上一条取代）：形成秋招目标下的跨阶段范围调整方案。已确认先完成M2，M3多模态暂缓，M4必须保留且定位为通用有界的企业数据库＋内部RAG＋公开互联网深度研究能力，M5保留评估、加固和作品化；当时M4具体档位仍待确认，本次只有设计与进度记录。
- 2026-09-03：M2-21工程化多Agent正式方案及推荐决策已确认；阶段定位为Supervisor＋Business Data/Knowledge首批Worker的核心底座，并冻结能力目录、Handoff、记忆、Checkpoint、树形预算、Evidence交接、分层执行和跨里程碑边界。实施顺序进一步确认为Walking Skeleton：先最小闭环和真实Worker，后持久化、真实Qwen、API及完整矩阵；只完成方案文档，尚未授权开始M2-21.1。
- 2026-09-02：完成M2-20.6真实权限/范围/故障矩阵并收口M2-20；两个读取Tool在同一真实Harness下覆盖三角色、五授权路径、撤权、软删除、旧代次、解析/locator、Storage/Artifact、数据库故障和Trace脱敏。没有修改生产代码，没有开始M2-21、API、Agent、Qwen或前端。
- 2026-09-02：完成M2-20.5 `GetEvidenceDetailTool`与Harness接入；精确绑定M2 Registry和可信身份，通过角色、重复预算、3000ms超时与Trace门禁，核对Service结果Evidence ID且成功Envelope只携带该ID。没有开始M2-20.6、API、Agent、Qwen或前端。
- 2026-09-02：完成M2-20.4统一Evidence详情Service；保留M1数据库Evidence与HTTP行为，新增文档Evidence按Context请求者、当前ACL/软删除/active代次和完整Chunk来源重新验证，失败统一隐藏。没有创建`GetEvidenceDetailTool`或开始M2-20.5。
- 2026-09-02：完成M2-20.3 `ReadUploadedFileTool`与Harness接入；执行前精确绑定M2 Registry和可信身份，通过角色、重复预算、3000ms超时与Trace门禁，结果核对公开file ID且成功Envelope不伪造Evidence。没有开始Evidence详情Service/Tool或M2-20.4。
- 2026-09-02：完成M2-20.2安全解析产物读取Service；可信`CurrentUser`通过一次性SQL重新获权，Service有界加载并复核Routed/Canonical Artifact、Storage Key与双重源Hash，按四格式locator返回最多8000字符的公开结果。没有创建执行Tool、接入Harness、生成Evidence或开始M2-20.3。
- 2026-09-02：M2-20完整方案和推荐决策已确认；完成M2-20.1四格式有界文件读取合同、统一Evidence详情合同、公开导出及M1两Tool/M2五Tool隔离Registry。没有创建执行Service/Tool、API、Agent、Qwen或前端。
- 2026-09-02：完成M2-19.5真实权限/故障矩阵与阶段收口；owner/company owner/user/role/market ACL、跨tenant/旧代次/软删除排除、跨ToolCall复用、撤权竞态、预算/超时和持久化原子故障均通过。M2-19整体已完成，没有开始M2-20、API、Agent、Qwen或前端。
- 2026-09-02：完成M2-19.4 `SearchKnowledgeTool`与Harness接入，验证可信身份、权限、预算、超时、Trace、Envelope和真实Tool-Context关联；修正ToolCall读取锁与Harness状态回写互锁。
- 2026-09-02：完成M2-19.3 `KnowledgeSearchService`，固定串联Reranker/Hybrid、Context Builder和Evidence原子持久化，并用真实PostgreSQL验证撤权、active切代和回滚。
- 2026-09-02：完成M2-19.2 ToolCall-Context审计关联、0010安全迁移及Document Evidence可复用归一化；M1 database Evidence保持直连。
- 2026-09-02：M2-19完整方案和推荐决策已确认；完成M2-19.1严格query/Context合同、12条Evidence上限及M1两Tool/M2三Tool隔离Registry。
- 2026-09-01：完成M1进度文档治理；M1入口与过程记录分离，历史正文完整性、链接和步骤覆盖验证通过，必读入口体积减少约95.8%。
- 2026-09-01：完成M2进度文档治理；M2入口与过程记录分离，历史正文完整性、链接和步骤覆盖验证通过，必读入口体积减少97.6%。
- 2026-08-29：M1库存查询垂直切片完成，公开演示、API、前端和Chromium整链通过；详细日志见M1记录。
- 2026-08-29至2026-08-31：完成M2-01至M2-15，建立上传、解析、分块、Embedding和幂等索引闭环。
- 2026-09-01：完成M2-16，建立权限前置的Dense、Lexical、Hybrid和RRF检索闭环。
- 2026-09-01：完成M2-17，真实BGE-Reranker提高正式Golden Recall@8，但记录了CPU延迟和内存成本。
- 2026-09-01：完成M2-18，建立Context、文档Evidence、原子幂等持久化和当前权限下的严格引用验证。

更早的逐步完成记录不在总看板重复保存，统一进入对应阶段详细记录。
<!-- SNAPSHOT:PROJECT_PROGRESS:END -->

<!-- SNAPSHOT:M2_ENTRY:BEGIN -->
# M2：知识库垂直切片

> 本文件是 M2 的唯一必读入口，只保存当前状态、关键决策、步骤索引、风险和下一动作。
> 完整方案、实施日志和验证证据保存在 [`records/`](records/) 中，开始具体任务时按需读取。
> 最近更新：2026-09-11

## 1. 当前状态

| 项目 | 当前内容 |
|---|---|
| 阶段状态 | 进行中 |
| 已完成 | M2-01 至 M2-21；M2-22.1至M2-22.7.5及M2-22.8.1至.8.2已完成并验证 |
| 当前停止点 | M2-22.8.2纯内存Fake Answer Runner、成功结果Run内缓存、逐题Trace Hash和公开安全报告已完成；Fake质量门禁固定为`None` |
| 下一动作 | 用户理解并单独授权后，只实施M2-22.8.3固定语料、公开Gateway与Knowledge Evidence链，最终Answer仍使用Fake；DeepSeek双Provider接入留到.8.4 |
| 已确认后续顺序 | M2-22.5至.8完成RAG分层评估与用户复核后，先插入M2-22.8R意图识别与执行分流改造，再实施M2-22.9最终多Agent轨迹评估，然后才进入M2-23前端与M2-24收口 |
| 尚未开始 | Gateway真实回答评估链、真实Answer Provider Runner、DeepSeek Agent Provider、召回提升及复评（用户已接受暂缓）、M2-22.8.3至.8.7、M2-22.8R、M2-22.9至M2-24、前端知识问答和M2阶段最终评估/演示收口 |
| 技术阻塞 | M2-22.8.3至.8.4无已知本地阻塞；.8.5以后真实DeepSeek/外部Judge需要用户本地有效Key和余额，失败必须显式非数值，不能用Fake替代 |

M2-20.1至M2-20.6已经全部完成并验证。M2-21十二步于2026-09-07全部完成：在共同合同、能力目录、Provider/Mock、五节点Supervisor、通用Worker Runtime、两个真实Worker、严格Qwen、统一引用、PostgreSQL持久化、唯一公开Gateway和跨请求恢复之上，独立只读且属于不同Worker的任务现在最多2路并发；真实公开G4验证了两个子Run重叠、独立预算/Session/Trace/ToolCall归属和稳定合并，G0～G7均已映射到可执行测试。M2-22.1至M2-22.6已经完成；M2-22.7.1至.7.4依次冻结合同、跑通Fake编排、保留固定语料并验证本地BGE资源，M2-22.7.5又在同一18文档/779 Chunk上完成40题真实Reranker与Context矩阵。随后只读诊断证明3条完整Golden均仍在固定Chunk中；用户接受该已知限制并决定暂不修复，门禁仍为False。用户又确认保留Qwen、并列新增DeepSeek并显式配置切换。M2-22.8.1已经冻结回答确定性指标，M2-22.8.2又用固定40题跑通纯内存Fake Answer编排、缓存、Hash与脱敏报告；当前停止等待.8.3真实Gateway/Knowledge证据链接线的单独授权，不提前接真实Provider或Ragas。

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

M2-22.6完整检索矩阵与M2-22.7五个小步均已接通并收口；正式结果选择Reranker Top5，Context候选为邻块1+3000 Token，但真实跨境仅12/14，评估完成不等于质量门禁通过。M2-22.8.1在评估侧建立了`冻结Cohort/配置 → 逐题执行记录 → 纯内存回答/Citation/安全指标 → 四个可回答视图加一个安全视图`；M2-22.8.2已经接上`固定JSONL → 内存Context/Evidence → Fake Answer Provider → Run内缓存 → 指标 → 公开安全报告`。仍未接通的是召回修复及复评、M2-22.8.3至.8.7真实回答评估链、M2-23前端引用展示和M2-24最终演示/阶段收口。

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
| M2-22 | 进行中 | M2-22.1至M2-22.8.2已完成；固定18文档/779 Chunk继续保留，真实跨境12/14门禁仍False；Fake Answer Runner/缓存/安全报告已验证且门禁为None，等待.8.3单独授权 | [M2-22方案与过程记录](records/M2_22_CROSS_BORDER_RAG_EVALUATION_PLAN.md) |
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
- M2-22.7.1冻结`m2-reranker-context-evaluation-v1`：所选Chunk为`compact 400/500 + overlap 100`，Dense/Lexical每路depth 10、Hybrid并集最多20、RRF 60；先比较Reranker Top5/Top8，再只对筛出TopK评估邻块0/1和Context 2000/3000/4000 Token。逐题结果只允许`candidate_missing/promoted/demoted/unchanged`，候选池身份与Evidence映射必须完全相同；34条可回答题和6条安全题由Cohort合同固定，缺题不能聚合。Context整体Golden覆盖与Anchor覆盖分开，冗余率是最终顺序中未新增Golden Evidence的片段占比，Token利用率是已用/预算；空Context是成功0值，计算失败的比率必须为`None`。
- M2-22.7.2固定Fake执行身份：34条可回答题每题有8次逻辑取分，6条安全题各1次，共278次；当前Run缓存绑定query Hash、候选有序身份/正文Hash及Fake模型完整身份，只触发40次Provider评分并产生238次命中，失败评分不缓存。每题公开Trace及总Trace均有SHA-256，报告不含问题/正文/路径/Storage Key/tenant/SQL；重复输入字节一致。`run_status=completed`与`quality_gate_passed=None`并存，明确只证明Fake编排完成，不代表真实质量达标。
- M2-22.7.3按用户确认修订数据生命周期：上传/解析/切块不是每轮查询实验的组成部分。首次缺失时才构建18份固定语料；成功后保留18个`compact 400/500 + overlap 100` ChunkSet和779个Chunk。语料身份与索引身份分开，换Embedding或FTS只新建IndexSet并复用ChunkSet；Dense/Lexical depth、RRF、TopK、Reranker或查询侧关键词逻辑变化连IndexSet也不重建。只有原文、Parser产物或Chunk配置变化才重切。
- M2-22.7.3数据库探针固定为Dense Top10 + Lexical Top10 → RRF 60 → 生产Reranker Service + Fake Provider → 生产Context Builder/Repository；Context不信任Reranker携带的正文，会按当前tenant、ACL、软删除、active版本和active IndexSet重新取回。成功语料不做`finally`清理；只有首次创建中途失败和测试隔离数据精确回滚。
- M2-22.7.4固定资源探针只使用6类合成问题和每题20个短候选，不读取18文档或数据库。固定本地BGE每池只评分一次，第二次逻辑请求复用Run内缓存；报告固定`quality_gate_passed=None`。max length身份仍为8192，但本步没有伪造“长文本实际截断”结论：当前固定Chunk最大500项目Token，正式矩阵应继续记录合同而不是制造超长输入。
- M2-22.7.5复用既有18个ChunkSet和779个逻辑Chunk，只在同一ChunkSet上激活真实BGE-M3索引；没有重新上传、解析或切块。34题Top5由RRF 27/34提升为Reranker 31/34，Top8保持31/34，按冻结并列规则选Top5；真实/合成/诊断分别12/14、10/10、9/10。3条候选缺失继续留在分母，邻块补到的Evidence不算Reranker Anchor命中。
- 正式Context六点中，邻块1+3000 Token达到最高总Golden覆盖32/34，与4000相同，但预算更小且冗余更低，作为后续候选；Anchor覆盖仍为31/34。`evaluation_completed=True`、安全6/6与`quality_gate_passed=False`并存，后者只因真实跨境12/14低于`.90`；评估层没有据此修改任何生产默认值。
- M2-22.7漏召回诊断只读复用固定语料：三条完整Golden Chunk均存在，Dense名次为33/42/39，Lexical均未命中；depth 20/30仍无法纳入完整Golden，depth 50虽能看见但RRF只有39/50/52。共同原因是中文查询与英文证据没有词法词项交集，Dense又被同主题或同类标识符片段压后。GPSR题的正确文档及部分答案Chunk已在Dense Top3，完整Golden由相邻Chunk补到，因此它兼有严格Golden映射和文档内定位问题。该诊断不构成参数修改，也不支持重切Chunk。
- 2026-09-10用户确认接受M2-22.7当前结果并暂不修复召回。该产品取舍只表示“带着已知限制继续评估下一层”，不改变真实跨境12/14、`quality_gate_passed=False`或三条Bad Case；M2-22.8仍须保留全部34+6分母，并把两条最终Context缺证据的可回答题记为上游归因失败，而不是删题或奖励模型猜答。
- 2026-09-10用户确认不删除Qwen，而是新增DeepSeek并通过配置显式选择，未来可切回Qwen。共享四角色严格合同、提示词和Citation边界；Provider各自处理传输差异，Qwen继续使用既有Chat Completions适配，DeepSeek计划使用Responses API严格JSON Schema、`reasoning.effort=none`且不提供Web Tool。默认候选`deepseek-v4-flash`仍须方案确认和真实探针，当前不得描述为已经接通。
- M2-22.8.1冻结`m2-answer-citation-evaluation-v1`：配置严格继承所选`compact 400/500 + overlap 100 + Dense/Lexical 10 + Hybrid 20 + RRF 60 + Reranker Top5 + neighbor 1 + 3000 Token`及固定BGE身份；Cohort必须是34条可回答（真实14、合成10、诊断10）和6条安全（ACL 2、版本2、无Evidence 1、unknown 1）。逐题合同把Context状态、回答执行状态和计算状态分开；上游Context缺Golden、回答执行失败、漏要点、Citation身份/Golden映射、安全错误分别归因。字面要点只接受Canonical或显式白名单变体；Citation语法/编号/获权身份和Golden映射可确定计算，语义支持固定未评估。计算失败/跳过以及受影响聚合保持非数值，不缩分母。
- M2-22.8.2固定`m2-answer-citation-fake-report-v1`：标准Fake Run从同一40题JSONL只构造内存Context和确定性Evidence绑定，每题只调用一次显式`deterministic_fake` Provider；Provider只有在获权Context覆盖全部Golden时才输出Canonical要点与合法Citation，安全题固定拒答。Run内缓存键绑定Provider身份和全部回答输入，只缓存`completed`，异常被固定安全摘要替换。公开Trace只留问题/Context/规则/请求/输出Hash、指标和Trace Hash，报告复算34+6及14/10/10/6分组并拒绝篡改或私有字段；Fake结果无论多高都固定`quality_gate_passed=None`。

### 7.2 当前风险与边界

| 风险或边界 | 当前事实 | 优先排查方向 |
|---|---|---|
| Reranker CPU 延迟 | 正式40题评分p50/p95/max约18.08/28.58/29.61秒，总耗时771.92秒，峰值RSS约3.60 GiB；明显高于短文本探针 | 已确认每个非空候选池只调用Provider一次且batch为2；后续若优化，先分析真实Chunk长度、CPU与批处理，再单独决定候选裁剪/GPU/独立服务，不在评估步改生产链 |
| Reranker无法修复候选缺失 | 三条完整Golden都在固定Chunk，但中文查询与英文证据无词法交集；Dense完整Golden仅排33/42/39，真实跨境Top5为12/14=`85.71%` | 用户已接受该限制并暂缓修复；M2-22.8继续保留34+6和上游失败归因，后续需要时再单独验证查询扩展/文档内定位，不删题、不重切或把depth直接改到50 |
| Context邻块被误读为精排恢复 | Top5 Anchor命中31/34；邻块1+3000/4000把总覆盖提高到32/34，其中`smoke-ext-031-zh-responsible-person`只由邻块补到 | 报告和后续说明始终同时列Anchor覆盖与总覆盖；召回/Reranker修复看Anchor，Context完整性才看Neighbor总覆盖 |
| 固定Chunk被后续测试误删 | M2-22.7.3语料持久保存在当前开发评估数据库，而部分历史集成测试会重建schema；这类测试不是普通查询实验，确实会物理清空数据 | 后续先运行会重置schema的测试，再调用幂等准备器；同一语料存在时只校验复用，不重新解析/切块。不要把正常调depth/RRF/TopK误当成重建理由 |
| 图文 DOCX | R-03已找回页眉与正文图片文字；M2-22.5全部7组配置的页眉、页脚、图片OCR和前后文均1/1，且4条OCR Golden均找到内容和Locator。Word渲染页码仍不可由`python-docx`可靠获得 | 继续使用Section/段落/Run/图片序号等真实定位，不把Section号伪装成物理页码；进程隔离留待负载加固 |
| 事实级 Locator | M2-22.5已允许证据跨Canonical换行/连续来源块，并识别DOCX表格坐标；最佳配置34/34 Golden均有内容与真实Locator，18/18文档Locator完整性通过，0个Locator归因失败 | 后续保持相同真实页码、source span、表格坐标或DOCX来源字段；不得用伪造页码制造通过 |
| Chunk标题与边界 | R-04A已用Chunker v3记录标题Block、字符范围、页码/bbox和精确排除原因；PDF按物理layout line及真实残段审计。正式矩阵达到56/56标题、0/11809边界断裂，多个候选34/34内容与Locator，总门禁True | 保持Golden、Parser、R04阈值和生产默认参数不变；未来新语料若失败，先按Parser Artifact、Chunk规则、Locator三层归因，不把Chunk通过外推为检索/回答通过 |
| DOCX region公开Locator | 已用现有`source_block_ids`实现受校验Canonical `block_number`降级；原第4名页眉Chunk仍保留第4名。非法Block只隔离该名次并使质量门禁失败，不能静默删候选；正式106,518候选映射失败0 | 保持精确坐标优先、Block仅兜底；不按页眉/页脚类型过滤，因为冻结题确实包含页眉控制码。新失败先查Parser/Chunk来源一致性，再查结果映射 |
| Ragas正式Judge完整性 | 用户已授权且单配置补跑完成；Precision/Recall/Relevancy分别有21/27/27条有效分数。7个超时、13个HTTP 400欠费Provider失败和7个Ragas无效结果均无数值；Noise 34条按无回答边界跳过 | 后续不得把完成样本均值外推为34题全量结论；先处理外部账户状态并设计独立授权的缺失样本补评方案，本步不自动重跑或启动回答链 |
| 既有跨月测试 | R-04收口已让夹具使用真实上传返回的Storage Key，跨月独立用例与完整后端均通过 | 保持生产Storage规则不变；未来测试继续从实际上传结果取Key |
| 数据库测试夹具会重置正式M2 Seed和固定Chunk | 历史集成测试会重建schema；在M2-22.7.3固定语料创建后运行会物理删除18个ChunkSet | 会重置schema的测试先运行；随后恢复正式Seed和幂等固定语料。普通查询或调depth/RRF/TopK不得重建；后续单独强化测试数据库隔离 |
| 规模与并发 | 当前只证明小型合成语料闭环 | M5再做负载、并发和更大规模评估 |
| Parser路由选择与Docling稳定性 | 扫描PDF结果返回后的`shutdown_timeout`已通过一次性Worker末端确定性退出修复；父进程的2秒收尾、超时/RSS/Snapshot限制和活进程拒收均未放宽。正式复验恢复18/18、34/34、OCR 4/4和18/18 R04接受 | 继续保留故意滞留Worker拒收回归；全局并发/背压及直接DOCX OCR进程隔离仍留给后续负载加固，不把本次单Worker结果扩大为吞吐证明 |
| Business商品规格无Evidence | M2-21.8明确不伪造引用；只规格可作为已观察结构化结果，但没有可引用Evidence | 后续若产品要求规格也强制引用，需先新增真实规格Evidence来源 |
| Qwen生产质量未收口 | M2-21.8代表性真实Smoke已通过；M2-21.12环境无Key而显式跳过复跑，仍未覆盖任意自然语言、真实Tool整链和负载 | M2-22/M5以版本化评估集验证规划、行动、参数、引用、延迟和预算 |
| Ragas Judge偏差与依赖边界 | 固定`ragas==0.4.3`与`langchain-community==0.4.1`，Judge身份、参数和Prompt Hash均复核。已完成样本分数可审计，但超时与欠费使真实跨境仅4/14条Precision、8/14条Recall、7/14条Relevancy有效 | 均值必须连同完成数报告；外部账户恢复后若需补缺，必须另行授权并保持相同Judge身份，不得用换框架、换模型或生成回答掩盖缺失 |
| 回答确定性指标被误读为语义质量 | M2-22.8.1只做NFKC/casefold/去空白后的显式短语包含、Citation身份与Golden映射；未列入白名单的合理近义表达会漏记，引用Golden也不等于该证据支持整句回答 | 先检查规则数据与逐题Trace；后续把Ragas Faithfulness和人工复核单独分栏，不放宽为不可审计的模糊匹配，也不把确定性分数冒充语义判断 |
| Fake Answer全通过被误读为真实质量 | M2-22.8.2的Fake Provider能读取Golden规则和内存Evidence，目标只是验证Runner、缓存、失败、Hash与脱敏；它没有经过真实Gateway、检索Context或真实模型 | 始终检查`execution_mode`和`quality_gate_passed=None`；真实链在.8.3、DeepSeek在.8.4至.8.5、语义与正式矩阵在.8.6至.8.7分别验证，不把Fake数值写入简历 |
| 检索跨重建稳定性 | 同一Index内120条route复跑0变化；清理后重建时Hit/Recall@8与miss复现，但MRR/nDCG变化。Dense、Lexical和RRF同分兜底依赖运行期Chunk UUID，新建UUID会改变同分顺序 | 当前不改生产检索合同；后续若单独授权修复，优先评估以稳定Canonical Chunk身份作为同分键，并增加跨清理重建回归 |
| 记忆与崩溃恢复边界 | 已完成有界脱敏短期记忆、澄清同根恢复、一次Re-plan和撤权重验；不是长期画像，未知状态进程崩溃后的`running`根当前返回409，不自动抢占 | M5评估长对话和恢复租约需求，不擅自扩成永久记忆 |
| 并发规模边界 | 当前只证明两个独立只读Worker在单进程事件循环内有界重叠、预算/Session/Trace隔离；同步Tool片段和高负载吞吐未做生产基准 | M5再做负载、多进程、背压和更大规模评估；写操作必须另行设计审批与冲突控制 |
| 简单请求统一进入Supervisor | 当前公开Gateway还没有独立的意图/复杂度分流，已有集成基线显示单一Business查询也会产生6次模型调用；若再固定增加一次LLM分类，只会给所有请求叠加新成本 | 不提前修改当前RAG评估链；M2-22.8复核后单独设计M2-22.8R，采用“程序高置信分流 → 低置信才调一次结构化模型”的候选策略，用路由准确率、模型调用数、Token、成本和p50/p95对比证明改造价值 |

## 8. 最近验证基线

M2-22.8.2完成时：

- `app/evals/answer_citation_runner.py`从固定JSONL构造纯内存Context、连续Citation和确定性Evidence/Golden身份；显式Fake Provider按“完整获权Golden才回答，否则拒答”的固定策略产生结构化`AnswerExecutionRecord`。标准Run保留34+6并恰好生成40次；
- Run内缓存用Provider完整身份和问题、Context、Golden、获权Evidence、要点等请求内容生成SHA-256键，相同请求复用；只缓存`completed`。Provider异常或失败不缓存，原始异常统一改为固定安全摘要；失败题不删除，逐题及受影响聚合继续为非数值；
- `app/evals/answer_citation_report.py`只公开case/分组身份、五类私有输入Hash、执行与指标、逐题Trace Hash和总Trace Hash；递归拒绝问题/答案/Context正文、路径、Storage Key、tenant/owner、Fixture身份、SQL、原始错误/响应。报告重新聚合40题并核对缓存计数和Hash，篡改被Pydantic拒绝；相同输入的规范JSON字节一致，`quality_gate_passed`只能为`None`；
- CLI只有`--output`参数，不提供真实Provider、数据库或检索开关。TDD RED为三个新测试文件在收集阶段因`answer_citation_report`不存在而失败；GREEN为本步11项，连同.8.1为`21 passed`，相邻评估回归`135 passed`。Ruff全维护范围、9个目标文件格式、Mypy 169个`app`源码与6个目标源码/测试、`compileall`及`git diff --check`通过；
- 本步未连接API、Agent Gateway、LangGraph、Harness、Tool、生产Service、Repository/Model、PostgreSQL/pgvector、Storage或固定18文档/779 Chunk；没有加载BGE、调用Qwen/DeepSeek/Ragas、产生费用或修改检索配置。完整证据见[M2-22记录第53节](records/M2_22_CROSS_BORDER_RAG_EVALUATION_PLAN.md#53-m2-2282实施记录fake-answer-runner公开安全报告与run内缓存2026-09-11)。

M2-22.8.1完成时：

- `app/schemas/evaluation.py`新增冻结计划、34+6且14/10/10/6分组Cohort、要点白名单、获权Evidence/Golden映射、回答执行、逐题结果和回答/安全聚合合同；`app/evals/answer_citation_metrics.py`只在内存中完成Cohort冻结、Unicode确定性短语匹配、Citation解析与映射、分层失败归因及完整分母聚合；
- 成功计算时，白名单要点按每个规则的Canonical/显式变体做规范化包含；禁用断言和安全短语同样做确定性包含。Citation把畸形、重复、`[E0]/[E13]`越界、当前Evidence不存在、获权Evidence映射与Golden Evidence precision/recall分开；回答需要但完全没有合法标签时另记`citation_required_missing`；
- 上游Context成功但缺完整Golden时，该题仍为`completed`且保留在可回答分母，只记`upstream_context_missing_golden`，不添加回答漏要点或执行失败归因。Context输入失败、Provider失败或跳过时，逐题计算字段和受影响聚合字段全部为`None`；安全题分别计算结构化拒答、敏感短语/Citation泄漏和零容忍通过；
- `citation_semantic_support_evaluated=False`和`citation_semantic_support_score=None`由Schema锁定。本步只能证明标签身份和Golden映射，不能证明语义Faithfulness、事实正确性或回答自然度；
- TDD RED为测试收集时`ModuleNotFoundError: No module named 'app.evals.answer_citation_metrics'`；GREEN聚焦`10 passed`，新指标加相邻评估Schema与M2-22.7全套单元回归`124 passed`。`ruff check app tests scripts migrations`、3个目标文件格式、`mypy app`（167个源码）、目标源码/测试Mypy、`compileall -q app tests scripts migrations`和`git diff --check`通过；
- 本步没有创建Answer Runner、公开报告/CLI、缓存、Gateway或数据库接线，没有访问PostgreSQL/pgvector/Storage，没有加载BGE或调用Qwen/DeepSeek/Ragas，没有重新上传、解析、切块、重建ChunkSet或修改Retriever/Reranker/Context/生产配置。完整证据见[M2-22记录第52节](records/M2_22_CROSS_BORDER_RAG_EVALUATION_PLAN.md#52-m2-2281实施记录回答citation拒答合同与确定性指标2026-09-10)。

M2-22.7漏召回只读诊断完成时：

- 输入仍是固定18文档、18 ChunkSet、779个逻辑Chunk及三条Bad Case；只读运行真实Dense与Lexical到诊断深度100，并按route depth 10/20/30/50/100重算RRF观察可达性。未运行Reranker、Context、最终回答，也未经过上传、Parser或Chunk Service；
- 三条Golden原文及Locator映射都能在既有Chunk中找到。`scan-batch`为Dense 33/Lexical缺失，`return-invalidation`为42/缺失，`zh-responsible-person`为39/缺失；其查询FTS词项与各自英文Golden FTS词项交集均为空。depth 20/30不能把它们带入融合池，depth 50的RRF名次也只有39/50/52；
- `scan-batch`的Dense前列被其他交易标识符、批次质检片段占据；`return-invalidation`被相似的海关失效/退货条款，尤其另一份低价值货物文档压住；GPSR题则已在Dense前3命中正确文档和含答案后半段的相邻Chunk，完整Golden位于前一Chunk，和邻块1补回结果一致；
- 诊断前后固定语料均为18 Document / 18 ChunkSet / 779逻辑Chunk，语料SHA-256均为`70750ee64c959795e7360a80f59df9248275ecfe5ddfbfb740e290bf5cde27a3`，语料确保返回`created=False`；临时诊断脚本已删除。能证明解析/切块未丢答案且主要缺口在召回；不能证明查询扩展、文档路由或其他候选策略必然通过门禁。完整证据见[M2-22记录第49节](records/M2_22_CROSS_BORDER_RAG_EVALUATION_PLAN.md#49-m2-227漏召回只读原因诊断2026-09-10)。

M2-22.7.5完成时：

- 新增真实正式评估装配、严格报告合同和显式`--run-real` CLI；CLI先只读核对固定Chunk身份，再在同一ChunkSet上确保真实BGE-M3索引，随后执行Dense10 + Lexical10 → RRF60 → 固定BGE-Reranker Top5/Top8 → 选定Top5下6个Context点。没有再次经过上传、Parser或Chunk Service；
- 34条可回答题全部完成：Reranker Top5为31/34，较RRF Top5的27/34增加4题；Reranker Top8与RRF Top8均为31/34，按并列选小规则选择Top5。逐题分类为3个候选缺失、10个升排、3个降排、18个排名不变；真实/合成/诊断选定Top5分别12/14、10/10、9/10；
- Context全体在邻块0下各预算均为31/34覆盖；邻块1+3000/4000达到最高32/34，总覆盖`.9412`，Anchor仍31/34=`.9118`。3000相较4000预算更小、冗余`.9062 < .9135`且利用率`.6604 > .5556`，因此记录为后续候选；6条安全题6/6完成且泄漏0；
- 3个Bad Case全部保留：`smoke-syn-011-scan-batch`与`smoke-ext-029-return-invalidation`在最大Context仍缺Evidence；`smoke-ext-031-zh-responsible-person`的Anchor仍缺失，只由邻块在3000/4000预算下补到。正式质量门禁因真实跨境12/14=`85.71% < .90`为False，但`evaluation_completed=True`；
- 真实评分缓存为74次逻辑请求、34 hit、40 miss/Provider调用/缓存项；总耗时`771.923s`，加载`24.825s`，评分p50/p95/max=`18076.246/28578.570/29613.483ms`，峰值RSS`3681.273MiB`、增量`2703.137MiB`，effective batch为2。Trace Set Hash为`5cf23c03d3ece573652d63aa07d2d0356a89dc48239e8296bd4ac63d2de523e3`；596,026字节临时报告Hash为`b62d4c674653c32ed2541fe97bc4f2cb0a7357997c97b75f08e9becb33d09804`，记录后删除；
- TDD RED为缺少`app.evals.reranker_context_formal`的收集错误；最终聚焦/相邻单元`172 passed`，安全的相邻数据库集成`8 passed, 1 deselected`，显式本地BGE Smoke `3 passed`。Ruff全维护范围与19文件格式、Mypy 166个`app`源码和10个目标源码、`compileall`、`pip check`通过；三套Seed重跑后只读核对固定语料18 Document/18 ChunkSet/779逻辑Chunk、36 IndexSet且18个active全为真实BGE-M3，Storage 28 uploads/18 parsed/18 chunks，M1库存125。完整证据见[M2-22记录第48节](records/M2_22_CROSS_BORDER_RAG_EVALUATION_PLAN.md#48-m2-2275实施记录18文档40题正式rerankercontext矩阵2026-09-10)。

M2-22.7.4完成时：

- `app/evals/reranker_resource_probe.py`新增6类×20候选的私有输入和真实Provider适配，复用`RunScoringCache`；`app/evals/reranker_context_report.py`新增固定BGE身份、逐类安全结果、CPU/RSS/批次/子进程和公开报告合同；CLI必须显式`--run-real`且没有下载开关；
- 初次运行确认目标快照不存在并在模型加载前安全失败；经用户授权，固定revision的6个运行文件共`2,293,242,108`字节恢复，manifest SHA-256为`c0cd30c8cb8f001454a113390ac195b15b54a2b16de4a86c8fa6ca91202e3f8b`，离线Hash复核通过；
- 真实离线CPU探针加载`26.317746s`，每个20候选池评分p50/p95/max为`4811.968/6351.987/6396.700ms`，RSS起点/峰值/增量为`316.418/2045.113/1728.695MiB`，batch 2未降级，新存活子进程0；6类共12次逻辑取分为6次Provider调用与6次缓存命中，120个分数均有限；
- 中文、英文、德文、表格样本的预期候选均排第1；候选缺失与无答案样本保持无预期候选、无名次。报告Schema与Artifact Hash复核通过，Hash为`8732450faeeea921e6b098c71d35382d8426d946429ede0324d8d4c32cff3d1c`，质量门禁字段为`None`；
- RED为缺少探针模块和CLI的两个`ModuleNotFoundError`；GREEN及相邻Provider/Runner/报告/CLI共`45 passed`，额外真实离线Smoke为`3 passed`。目标文件Ruff/Mypy通过，compileall、依赖和diff检查通过；全仓库根目录检查另暴露旧原型格式债与既有准备脚本Mypy问题，未越界处理；
- 本步未读取PostgreSQL/pgvector/Storage或固定语料，未运行Parser/Chunk/Index/Retrieval/Context、Qwen/Ragas、API、Agent/LangGraph、Harness、Tool或前端。完整证据见[M2-22记录第47节](records/M2_22_CROSS_BORDER_RAG_EVALUATION_PLAN.md#47-m2-2274实施记录固定本地bge-reranker小样本资源探针2026-09-10)。

M2-22.7.3完成时：

- 正式固定语料首次准备为`created=True`：18 documents / 18 ChunkSets / 18 Fake IndexSets / 779 active Chunk rows；语料Hash为`70750ee64c959795e7360a80f59df9248275ecfe5ddfbfb740e290bf5cde27a3`，tenant为`3288f8db-e815-442c-860a-dbb8077a1954`。第二次为`created=False`，语料、索引、快照Hash和tenant均完全一致；
- 真实查询探针在同一固定语料上得到11个Hybrid候选、5个Reranker结果、12个Context片段和3266项目Token，`context_supported=True`，运行前后Chunk数均为779；
- 聚焦数据库测试`9 passed`；权限、检索和Context相邻集成合计`24 passed`；Reranker/Context单元`72 passed`；既有M2检索Runner集成`1 passed`。Ruff全维护范围、3个目标文件格式、Mypy 164源码、`compileall`和diff检查通过；
- 本步只真实运行Fake Embedding和Fake Reranker下的数据库装配/权限链，没有运行固定本地BGE-Reranker、Qwen、Ragas或40题质量矩阵。完整证据见[M2-22记录第46节](records/M2_22_CROSS_BORDER_RAG_EVALUATION_PLAN.md#46-m2-2273实施记录固定语料真实数据库候选与context权限重取2026-09-10)。

M2-22.7.2完成时：

- `app/evals/reranker_context_runner.py`新增Fake-only Runner、确定性Hash评分器、内存Anchor Context读取器、冻结数据转假候选和Run内评分缓存；`app/evals/reranker_context_report.py`新增公开候选/逐题Trace、40题Hash链、缓存统计和报告合同；`scripts/run_m2_reranker_context_evaluation.py`只运行冻结JSONL与Fake边界；
- 34条可回答题严格按Top5、Top8、选定TopK下邻块0/1×Token 2000/3000/4000运行；6条安全题单独用最宽`neighbor=1/token=4000`探测。共278次逻辑取分只有40次Fake Provider调用，238次Run内命中，Context Reader调用210次；
- 缓存键随query、候选顺序、正文Hash、model ID/revision、max length、precision和scorer version变化；失败评分再次请求会重新调用Provider。每题报告只有query/body Hash、公开身份/Locator、名次/分数和Evidence映射；40条Trace Hash再组成总Hash，篡改单题Hash会被Schema拒绝；
- CLI在临时目录真实运行冻结40题并生成可重新校验的公开报告；相同输入两次`model_dump_json()`字节一致。报告安全分栏6/6保留、Fake安全门禁True，但真实质量字段固定为`None`；没有在仓库保留临时报告；
- TDD RED为3个测试文件收集时报`ModuleNotFoundError: app.evals.reranker_context_report`；GREEN聚焦`8 passed`，连同M2-22.7.1指标、数据/评估合同和既有Retrieval Runner相邻共`116 passed`。Ruff全维护范围、8个目标文件格式、Mypy 163个`app`源码和`compileall`通过；未访问PostgreSQL/pgvector/Storage，未加载BGE/Qwen/Ragas，未经过前端、API、Agent/LangGraph、Harness、Tool或生产Reranker/Context Builder。完整证据见[M2-22记录第45节](records/M2_22_CROSS_BORDER_RAG_EVALUATION_PLAN.md#45-m2-2272实施记录fake-runner公开报告与run内评分缓存2026-09-10)。

M2-22.7.1完成时：

- `app/schemas/evaluation.py`新增冻结计划、34+6 Cohort、顺序实验点、逐题Reranker比较、逐题/分组Context质量、分组聚合和安全分栏合同；`app/evals/reranker_context_metrics.py`新增纯内存计划、Cohort冻结、同候选池比较、Context与安全指标及完整分母聚合；
- Top5/Top8先筛选，随后只有选定TopK进入邻块0/1×Token 2000/3000/4000六点；Dense/Lexical各10可形成最多20个Hybrid候选，合同不把“每路深度”错当“融合池上限”；
- 候选缺失保持`completed + candidate_missing + 两个rank=None + 两个hit=False`并进入聚合分母；Context邻块能提高整体Golden覆盖，但只允许真实TopK Anchor进入Anchor覆盖。Golden相对冗余率=`未新增Golden的片段数/总片段数`，Token利用率=`total_tokens/context_max_tokens`；
- 正式数据文件只读冻结出34条可回答题和6条安全题，安全分布为ACL 2、版本2、无Evidence 1、unknown 1。空Context是合法`completed`零分；`calculation_failed/skipped`所有计算字段必须为`None`并带安全失败类别/摘要；
- TDD RED为测试收集时缺少`app.evals.reranker_context_metrics`；GREEN聚焦`13 passed`，与评估合同、检索指标、Ragas适配和Smoke数据合同相邻共`111 passed`。Ruff全维护范围lint通过，目标3文件格式通过，Mypy 161个`app`源码通过，`compileall -q app`和`git diff --check`通过；
- 本步未创建Runner、报告CLI或Run内缓存，未访问PostgreSQL/pgvector/Storage，未加载BGE、Qwen或Ragas，未经过前端、API、Agent/LangGraph、Harness、Tool、生产Reranker Service或Context Builder。完整证据见[M2-22记录第44节](records/M2_22_CROSS_BORDER_RAG_EVALUATION_PLAN.md#44-m2-2271实施记录评估配置结果合同与确定性指标2026-09-10)。

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
- Alembic继续为`20260902_0010 (head)`且无漂移，M2-22.7没有新增迁移；
- 两组正式M2 Seed仍为10 files / 10 documents / 10 versions / 9 ACL；另按用户确认持久保留固定评估语料18 files / 18 documents / 18 versions / 39 ACL / 18 ChunkSets。其36个IndexSet是同一批779个逻辑Chunk的Fake与真实BGE-M3两代索引，数据库1558条索引行不表示重新切成1558块；
- Storage为28个uploads、18个parsed Artifact和18个Chunk Artifact；M1德国仓可售库存仍为125。

这些结果能证明两个读取Tool在三业务角色、owner/company owner/user/role/market ACL下通过同一真实Harness落到真实Service/Repository，撤权、软删除、旧active来源、解析/locator、Storage/Artifact和数据库故障均被安全处理并记录Trace；不能证明M2-21多Agent策略、真实Qwen/BGE延迟、公开聊天Agent Gateway迁移或前端。

## 9. 下一步和记录规则

M2-20已经完成、验证并收口；M2-21十二步、M2-22.1至M2-22.6、M2-22.7五个小步和M2-22.8.1至.8.2也已完成。M2-22.7.5真实矩阵复用了固定18文档/779 Chunk并选择Top5与“邻块1+3000 Token”Context候选，但真实跨境12/14未过90%门禁。三条漏召回只读诊断已证明答案没有被解析或切块删除；用户接受该已知限制并决定暂不修复，但门禁仍保持False。M2-22.8.1冻结回答评估合同与纯内存尺子，M2-22.8.2只用Golden感知Fake跑通40题Runner、缓存和安全报告，仍没有真实Gateway或模型质量。当前停止等待用户理解和单独授权M2-22.8.3固定语料、真实公开Gateway与Knowledge Evidence链，最终Answer仍用Fake；DeepSeek接入到.8.4才开始。已确认的远期顺序仍是RAG分层评估完成并复核后 → M2-22.8R意图识别与执行分流 → M2-22.9最终Agent轨迹评估 → M2-22.10收口。

后续记录方式：

- 本入口只更新当前状态、步骤索引、有效关键决策、风险和下一动作；
- 详细方案、修改文件、TDD过程、验证数字、能证明/不能证明和排查记录写入对应 `records/` 文件；
- 同一能力继续追加到已有记录；进入新的能力步骤时再创建新记录文件；
- 不把逐次测试流水账重复粘贴到 `docs/PROJECT_PROGRESS.md`；总看板只保留里程碑摘要和链接；
- 未验证的工作不得标记为已完成，代码变化导致旧验证失效时必须在对应记录中注明。
<!-- SNAPSHOT:M2_ENTRY:END -->
