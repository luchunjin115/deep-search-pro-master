# 项目总进度看板

> 本文档是项目进度的统一入口，只保存当前状态、里程碑摘要、跨阶段决策、阻塞项和阶段链接。
> 详细方案、逐步日志和完整验证结果保存在 `docs/progress/` 对应阶段记录中。
> 状态枚举：待确认、待开始、进行中、受阻、已完成。
> 最近更新：2026-09-10

## 1. 当前状态

| 项目 | 当前内容 |
|---|---|
| 当前阶段 | M2：知识库垂直切片 |
| 阶段状态 | 进行中 |
| 已完成到 | M1已完成；M2-01至M2-21已收口；M2-22.1至M2-22.6已完成。M2-22.6包括Locator降级、10组Chunk/50点确定性矩阵，以及只对筛出配置补跑的Ragas检索语义评分、失败分类、清理和回归 |
| 当前停止点 | M2-22.6已最终收口。用户已要求进入M2-22.7，但先同步正式文档并查看详细步骤；M2-22.7方案已补齐，尚未修改评估或生产代码、未运行Reranker/Context |
| 下一动作 | 先由用户确认M2-22.7五步实施方案；确认后只开始M2-22.7.1评估配置、结果合同与确定性指标，不自动进入后续小步 |
| 已确认后续顺序 | 完成M2-22.5至.8 RAG分层评估并复核后，先插入M2-22.8R意图识别与执行分流改造，再用M2-22.9评估改造后的最终Agent轨迹；不等M2整体完成后再返工 |
| 尚未具备 | M2-22.7至.8 Reranker/Context/回答/Citation正式评估、Validation/Test正式集、意图识别与执行分流、最终多Agent轨迹评估、M2-23至M2-24、前端与M4/M5能力 |
| 当前阻塞 | M2-22.7无已知本地阻塞；外部Qwen欠费只影响M2-22.6遗留语义结果和后续M2-22.8回答/Judge，不阻塞本地BGE-Reranker与Context评估。当前等待用户确认M2-22.7详细方案 |

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
| 大模型 | 千问负责主推理和多模态理解 |
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
| 秋招范围调整 | M3多模态暂缓；M4推荐版已确认：复用Business/Knowledge Worker，只新增Web Research Worker，以Tavily自定义Provider实现搜索与受控正文读取，保留三类Evidence、有界并行、PostgreSQL Checkpoint、Markdown和一个研究Skill；M5保留Agent/RAG评估、加固和作品化；详见[M4入口](progress/M4/M4_DEEP_RESEARCH.md)与[调整方案](design/05_Autumn_Recruitment_Scope_Adjustment_Plan.md) |
| 开发方式 | 教学式协作、阶段方案先确认、一次完成一个可验证小步骤 |
| 阶段文档结构 | M1及以后统一使用`docs/progress/M{编号}/`，阶段短入口与`records/`过程记录分离；新窗口按当前任务读取，不默认加载全部历史 |

M2 专属的解析、分块、索引、检索、Reranker、Context和Evidence决策不在总看板重复展开，统一以 [M2入口](progress/M2/M2_KNOWLEDGE_RAG.md) 和对应过程记录为准。

## 4. 当前验证基线

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
| Reranker本机CPU p95约7.24秒 | 不适合未经优化直接进入低延迟同步链 | 后续评估候选裁剪、GPU、批处理或检索路由 |
| DOCX物理页码与region公开Locator | `python-docx`不能给稳定渲染页码；M2-22.6R-01已让无精确坐标候选使用与source span一致的Canonical `block_number`，坏Block只隔离该名次并触发质量门禁 | 不伪造物理页码、不删除页眉/页脚候选；保持页/段落/表格/标题等精确坐标优先，Block只作可审计兜底 |
| Chunk标题真值与绑定 | R-04A已补齐标题精确来源与物理版面审计，最终56/56标题、0/11809边界且总门禁True | 保持v3来源审计；新失败按Parser Artifact、Chunk和Locator逐层定位，不把Chunk通过等同检索通过 |
| 既有跨月硬编码测试 | R-04收口已让夹具使用真实上传返回的Storage Key，跨月独立用例与完整后端均通过 | 保持生产Storage规则不变；未来测试继续从实际上传结果取Key，不拼接月份 |
| 数据库测试夹具会重置正式M2 Seed | 本次相邻集成后实测出现数据库0条、Storage仍10个对象；若不做末尾审计会留下不一致基线 | 所有数据库回归完成后重新运行既有两个M2 Seed入口，并以`10/10/10/9/10/10/M1 125/clean=True`作最终门禁；后续再单独加固测试隔离 |
| Business商品规格没有Evidence | M2-21.8明确不伪造引用；只规格可作为已观察结构化结果，但没有可引用Evidence | 若后续要求规格也强制引用，先新增真实规格Evidence来源 |
| Qwen生产质量未收口 | M2-21.8代表性真实Smoke已通过；M2-21.12环境无Key而显式跳过复跑，仍未覆盖任意自然语言、真实Tool整链或负载 | M2-22/M5使用版本化评估集验证规划、行动、引用、延迟与预算 |
| Parser路由、Office视觉提取与Docling稳定性 | 扫描件Docling结果返回后的`shutdown_timeout`已修复，未放宽父进程安全门禁；正式复验恢复18/18、34/34、OCR 4/4。单件实测仍约101.9秒、峰值约1.96 GB，直接DOCX OCR尚无同级进程隔离 | Parser不再是当前Chunk门禁失败归因；保留滞留Worker拒收回归，吞吐、全局并发/背压和直接DOCX OCR进程隔离留给后续负载加固 |
| Ragas Judge偏差与依赖边界 | 固定Ragas 0.4.3和Qwen身份后单配置补跑；Precision/Recall/Relevancy分别21/27/27条有效。7个超时、13个HTTP 400欠费Provider失败、7个框架失败均无数值，Noise因需要回答全部跳过 | 完成样本均值必须连同样本数报告，不能外推为34题全量；外部账户恢复后若补缺须另行授权，不能换Judge或启动回答链掩盖缺失 |
| 检索跨重建稳定性 | 同一Index内120条route稳定，但清理后重建的Hit/Recall@8复现、MRR/nDCG变化；Dense/Lexical/RRF同分兜底依赖新建Chunk UUID | 当前不改生产排序；后续若另行授权，评估以稳定Canonical Chunk身份作同分键，并增加跨重建回归 |
| 记忆与崩溃恢复边界 | 有界短期记忆、澄清同根恢复、撤权重验和一次Re-plan已完成；不是长期画像，未知执行结果的`running`根暂不自动抢占 | M5评估长对话与恢复租约，不擅自扩大记忆范围 |
| Worker并发规模边界 | 已证明两个独立只读Worker在单进程内有界重叠及预算/Session/Trace隔离；未做高并发、多进程或写操作冲突控制 | M5再做负载、背压和多进程评估；写能力必须另行设计审批与一致性边界 |
| README与旧面试指南仍含早期原型/原始完整版表述 | 直接用于投递会夸大或混淆当前实现 | M5作品化前按实际代码、评估和演示统一清理；当前不得直接照抄 |

M2-22.5已由R-04A正式收口并恢复基线；M2-22.6的Locator、确定性矩阵和单配置Ragas补跑均已完成。Ragas部分样本有效、失败样本按超时/Provider/框架分类保留，报告与评估数据已清理，正式Seed恢复。没有运行Reranker、Context、回答、Citation、Agent或前端；当前停止等待用户复核，不进入M2-22.7。

## 6. 最近完成摘要

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
