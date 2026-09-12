# M2-22.5｜Chunk质量与标题/Locator修复记录

> 以下第26至39节从原M2-22总记录按连续区间原样迁入；第26和29节是当时与本能力相邻确认的跨层顺序决定，因此一并保留。

## 26. 2026-09-08｜RAG后意图识别与执行分流顺序调整

### 26.1 用户确认与当前缺口

用户明确确认：暂不扩展时间约束、来源权威性评分或复杂对比；完成RAG分层评估后，紧接着先实施意图识别与执行分流，再进入M2-22.9多Agent轨迹评估。

当前公开消息POST已在M2-21.10迁移到唯一Agent Gateway，但还没有在Supervisor前实施独立的意图/复杂度分流。现有真实Business Worker集成基线已记录：单一商品或库存请求也会产生6次模型调用，规格加库存为7次。因此，若在改造前就生成M2-22.9最终轨迹报告，报告只代表即将被替换的旧执行路径。

### 26.2 冻结的顺序与最小范围

后续顺序冻结为：

```text
M2-22.5～M2-22.8 RAG分层评估与用户复核
→ M2-22.8R 意图识别与执行分流
→ M2-22.9 改造后的最终多Agent轨迹评估
→ M2-22.10 正式集、Bad Case和阶段收口
→ M2-23 前端
→ M2-24 最终演示与M2收口
```

M2-22.8R的最小目标不是只给用户消息贴上意图标签，而是让标签真正决定执行路径：

```text
简单单一查询 → 快速路径，绕过Supervisor
固定复合查询 → 受控Pipeline
确需规划的复杂任务 → Supervisor/Worker
信息不足 → 安全追问
当前不支持 → 明确unsupported
```

分流不能被实现为“所有请求先固定调一次LLM分类”。候选策略是两层：程序只对能够稳定验证的高置信明确请求直接分流；无法确定时，再用一次严格结构化模型输出同时给出意图、路径和可校验的业务参数。模型输出低置信、参数不全或Schema非法时安全追问或返回unsupported，不把不确定请求默认升级为高成本Supervisor路径。

这些数字只是后续实施方案要校准的调用目标，不是已实现结果：

| 路径 | 待校准模型调用目标 | 理由 |
|---|---:|---|
| L0直接回答 | 通常1次 | 分类与回答不再拆成两次 |
| 高置信明确Business查询 | 0次 | 程序分流、Tool执行、确定性格式化 |
| 不确定Business查询 | 最多1次 | 一次同时完成意图、路径和参数提取，Tool后不固定再调模型 |
| Knowledge问答 | 通常1至2次 | 高置信程序路由后只需RAG回答；路由不确定时才增加一次结构化判断 |
| 固定复合Pipeline | 通常不超过2次 | 一次理解/参数提取和最多一次有必要的跨源综合，独立Tool并行 |
| L3 Supervisor/Worker | 按树形预算有界计数 | 只有复杂任务支付规划、Handoff和恢复成本 |

本步只使用M2已有Business/Knowledge能力，不新增Worker、Tool、Web研究、时间约束、权威性评分、动态通用DAG或M4能力。详细路由合同、实现文件、模型/规则边界、降级策略和门禁阈值，必须等M2-22.8的实际RAG结果已知后再提交完整方案，本次文档更新不自动授权代码开发。

### 26.3 调用链位置、验证和边界

本次实际只修改总进度看板、M2入口和本过程记录，位于方案/进度层；未经过前端、API、Schema、Agent/LangGraph、Harness、Tool、Service、Repository/Model、PostgreSQL/pgvector、Storage或外部Provider。

后续M2-22.8R必须验证路由准确率、路径选择、任务完成、Tool/Evidence一致性、模型调用数、Token、成本与p50/p95；至少要有单Business、单Knowledge、Business+Knowledge固定复合、复杂Supervisor、需要追问和unsupported用例。M2-22.9只能在该改造完成后评估最终轨迹。

文档验证已完成：对三份文档运行`git diff --check`无错误，仅有Git对现有LF/CRLF工作区转换的提示；`rg`复核确认总看板、M2入口、M2-22步骤、调用链和完成标准均使用“M2-22.8 → M2-22.8R → M2-22.9”顺序，旧版步骤数量和RAG后直接进入.9的表述均已清除；三份文档的Markdown代码栅栏数量均为偶数。

本次能证明用户确认的顺序、最小范围、后续验证方法和停止点已进入正式记录；不能证明意图识别、快速路径或固定Pipeline已实现，也不能证明现有6/7次模型调用已降低。该文档调整完成当时的下一动作是等待用户单独授权M2-22.5；后续授权和结果见第27节。

## 27. M2-22.5实施记录：Chunk质量矩阵（2026-09-08）

### 27.1 用户授权、当前缺口和本步输入输出

用户正式确认并授权只实施`M2-22.5 Chunk质量矩阵`，明确禁止提前实现M2-22.6或后续步骤，禁止安装/运行Ragas，也禁止运行Embedding、pgvector、检索、Reranker、Context、Agent、Qwen和前端功能。

本步开始前缺少的不是另一个Chunk算法，而是一把统一的“尺子”：R04已经证明18份文档的Canonical Parser Artifact恢复34/34事实，但还不知道现有Chunk流程是否会把完整答案、标题、段落、表格、页眉、图片OCR文字和前后文切坏，也不知道当前`600/700/100`与其他完整配置相比表现如何。

输入固定为：18份经过公开上传与建文档API、正式Parser Service和R04质量门禁的Canonical Parser Artifact；34条已有Golden Evidence；四组冻结完整Chunk配置。输出为：首轮4配置矩阵、按冻结规则选出的候选、只改变overlap 80/100/120的第二轮矩阵、逐文档/逐Golden归因、公开安全JSON报告，以及清理后的正式数据库/Storage基线。本步没有用后续检索分数倒推Chunk参数。

### 27.2 实现与指标规则

1. 首轮固定比较`target/max/overlap=400/500/100`、`500/600/100`、`600/700/100`、`700/850/100`，其余`heading_context_max_tokens=120`、`table_row_overlap=1`、`repeated_edge_min_pages=2`、表头重复、隐藏Sheet、归一化器、Chunker和Token Counter身份全部相同；
2. 候选选择只看首轮结构质量，优先Golden完整包含与Locator、证据范围覆盖、边界破坏和标题/表格保留，再看空块、近重复和Chunk数量；没有检索与存储收益证据时不把“大块更少”直接解释为生产最优；
3. 第二轮只对首轮候选`chunk-large`改变`text_overlap_tokens=80/100/120`，其他字段保持不变；
4. Golden先检查证据原文是否存在于Parser Artifact，再检查是否完整落在至少一个Chunk，最后检查该Chunk的真实页码/source span、DOCX来源或表格坐标能否覆盖Golden Locator；失败分别归因`parser_artifact`、`chunk_rule`、`locator`；
5. 结构检查覆盖段落、Parser标题提示、表格行、DOCX页眉/页脚、图片OCR、图片前后文链接、重复页眉/页脚排除和段落/句子边界；基础检查覆盖Token min/p50/p95/max、显式重叠率、空块、近重复、Chunk来源顺序、全量Locator完整性和同输入同配置的字节级重复构建；
6. Evidence跨Canonical换行或多个连续文本来源块时，Locator允许多个真实source span共同覆盖中间仅为空白的间隔；DOCX表格使用Canonical表格坐标。评估器不伪造连续范围或DOCX物理页码。

### 27.3 修改文件与职责

- `app/evals/chunk_metrics.py`：新增纯确定性Chunk质量计算、三层失败归因、结构审计、Token/重叠/重复/顺序/Locator/确定性聚合和首轮候选选择；不修改生产Chunker；
- `app/evals/rag_runner.py`：在既有Parser Runner旁新增显式`--stage chunk`入口；为18份文档建立隔离评估租户，经现有API、Parser Service与`DocumentChunkService`运行矩阵，读取正式发布Chunk Artifact、内存重建比对，最终精确清理租户数据库行和Storage对象；默认Parser入口保持不变；
- `app/schemas/evaluation.py`：让评估配置完整冻结既有`repeated_edge_min_pages=2`，避免报告身份漏掉实际参与Chunk的配置字段；没有改生产默认值；
- `tests/unit/test_rag_chunk_metrics.py`：覆盖DOCX页眉/页脚/图片OCR与前后文、Parser/Chunk/Locator三层归因、候选并列规则和跨换行多source span Locator；
- `tests/unit/test_rag_evaluation_contracts.py`：补充完整Chunk配置身份断言；
- `tests/integration/test_m2_rag_chunk_runner.py`：以4份真实类型子集验证公开摄取、正式Parser/Chunk Service、4组首轮和候选重叠扫描、Golden Locator、确定性、公开安全报告及数据库/Storage恢复；
- 本过程记录、M2阶段入口和项目总看板：同步实际矩阵、失败事实、验证边界与停止点。

### 27.4 完整调用链位置

```text
前端：不经过、不修改
→ API：仅复用 POST /files 与 POST /documents 登记18份评估文档
→ Schema：公开请求/响应不改；内部评估Schema冻结完整Chunk配置与报告
→ Agent / LangGraph / Harness / Tool：不经过
→ File / Document Service → Storage uploads
→ Parser Router / R04质量门禁
→ Canonical Parser Artifact / Parsed Storage
→ 现有 DocumentChunkService
→ StructureAwareDocumentChunker + UnicodeMixedTokenCounter
→ Canonical Chunk Artifact
→ DocumentChunkSet / PostgreSQL + Chunk Storage
→ 项目确定性Chunk评估器
→ 精确清理评估租户、ChunkSet和Storage对象
→ Embedding / pgvector / Retrieval / Reranker / Context / Agent / Qwen / Ragas / 前端：全部停止，未运行
```

### 27.5 正式18文档、34 Golden矩阵结果

正式命令为`.venv\Scripts\python.exe -m app.evals.rag_runner --stage chunk --enable-docling`。最终Run为`m2-22.5-20260908t091241-0ada274d`，`run_status=completed`、18份文档、34条Golden全部完成，但`quality_gate_passed=False`。`completed`只代表矩阵和清理完整，不代表质量通过。

| 配置 | Chunk数 | Token min/p50/p95/max | 显式重叠率 | Golden内容/Locator | 段落保留 | 边界断裂 | 标题 | 表格行 | 门禁 |
|---|---:|---|---:|---|---|---|---|---|---|
| compact 400/500/100 | 800 | 2/387/400/496 | 24.41% | 34/34；34/34 | 9683/9687 | 4/9750 | 109/152 | 45/45 | False |
| medium 500/600/100 | 611 | 2/486/500/598 | 19.19% | 33/34；33/34 | 9686/9687 | 1/9750 | 109/152 | 45/45 | False |
| current 600/700/100 | 506 | 2/586/599/695 | 15.90% | 33/34；33/34 | 9687/9687 | 0/9750 | 109/152 | 45/45 | False |
| large 700/850/100 | 429 | 2/684/699/848 | 13.28% | 34/34；34/34 | 9685/9687 | 2/9750 | 109/152 | 45/45 | False |
| large 700/850/80 | 419 | 2/682/699/847 | 10.62% | 33/34；33/34 | 9686/9687 | 1/9750 | 109/152 | 45/45 | False |
| large 700/850/100 | 429 | 2/684/699/848 | 13.28% | 34/34；34/34 | 9685/9687 | 2/9750 | 109/152 | 45/45 | False |
| large 700/850/120 | 441 | 2/684/699/805 | 16.00% | 34/34；34/34 | 9687/9687 | 0/9750 | 109/152 | 45/45 | False |

所有7组均为18/18文档来源顺序正确、18/18全量Locator完整、18/18重复构建字节一致、0空Chunk；近重复分别为1/1/1/2/1/2/1。合成与真实跨境、digital与OCR分别单列，没有混成一个看不出问题的总分。

首轮候选是`chunk-large`；在它的重叠扫描中，120是本轮结构指标最完整的组合：34/34 Golden与Locator、9687/9687段落、0边界断裂、45/45表格，Token最大805没有超过850，显式重叠16.00%。这只是本步候选证据，不是生产默认参数变更，也不能在检索尚未运行时宣布最终最优。

真实通过项包括：表格行45/45；图文DOCX的页眉1/1、页脚1/1、图片OCR 1/1、图片前后文1/1；OCR组4/4 Golden；所有正确包含的Golden都有真实Locator，最终0个`locator`失败。最初发现的跨换行与DOCX表格误报属于评估器Locator判定缺陷，修正并补反例后重新完整运行，最终报告没有保留错误分数。

真实失败项归因如下：

- 全部配置的标题都是109/152。`m2-complex-v1-two-column-market-brief`为2/6，因为Parser Artifact在一个物理文本行内保存左右栏两个标题，现有Chunker只做整行标题精确匹配；`eu-vat-oss-guidelines-2026-en`为32/64、`eu-gpsr-factsheet-2023-en`为6/11、`eu-safety-gate-alert-10001641-en`为2/4，均是Parser标题提示存在但没有作为对应Chunk正文中的独立标题保留，归因`chunk_rule`；
- `smoke-ext-025-ioss-coverage`在medium/current只由单Chunk覆盖96.59%，在large-overlap-80只覆盖75%，所以三组均为33/34并归因`chunk_rule`；compact、large-overlap-100和120能完整包含它；
- compact/medium/large/large-overlap-80/100分别有4/1/2/1/2个段落或句子边界断裂；current和large-overlap-120为0。没有通过降低R04阈值、放宽Golden或修改生产默认值掩盖这些差异。

### 27.6 测试与工程验证

1. 指标模块首轮RED在导入缺失模块时失败；实现后新增4个专项单测全部通过。最终专项集合`tests/unit/test_rag_chunk_metrics.py + test_rag_evaluation_contracts.py + tests/integration/test_m2_rag_chunk_runner.py`为`84 passed in 36.77s`；
2. 相邻Parser/Artifact/Chunk单元为`173 passed, 2 skipped in 25.10s`；
3. 相邻上传/Parser/Chunk集成组合为`21 passed, 3 skipped, 6 errors in 69.44s`。6个error全部来自旧`tests/integration/test_file_api.py`的module夹具在正式10份文档版本仍引用文件时执行无条件`DELETE FROM files`，PostgreSQL复合外键在setup阶段拒绝；尚未进入本步Runner、指标或Chunk代码。该范围外测试隔离问题没有被删除、改断言或清空正式基线来制造通过；
4. 在明确禁止下游功能的边界内，完整允许范围单元回归为`442 passed, 2 skipped in 31.48s`，完整允许范围数据库/服务集成为`60 passed, 3 skipped in 100.62s`；没有运行全仓原样pytest，因为其中会实际执行用户明令禁止的Embedding、pgvector、检索、Reranker、Context、Agent和Qwen功能；
5. `ruff check app tests scripts migrations`通过；`mypy app`为156个源码通过；`compileall -q app`、`pip check`、`git diff --check`通过；Alembic current/heads均为`20260905_0011 (head)`，`alembic check`为`No new upgrade operations detected`。本步无迁移；
6. 本步3个需要格式化的文件已修正并通过定向格式检查；全范围格式检查为336个文件正确，只剩未修改的既有`tests/integration/test_document_chunk_set_migration.py`一处CRLF差异。

### 27.7 报告、清理和正式基线

Git忽略的正式报告位于`data/evals/runtime/reports/m2_cross_border_chunk_report_v1.json`，大小498,013字节，SHA-256为`37bf809c654af1eb92cfb777165aba274fdf6307e7e8befc220cbcf44c69f3e7`；报告只保存公开Source ID、配置、Hash、计数、比例和失败层，不保存Chunk正文、绝对路径、Storage Key、tenant/user UUID、口令或数据库URL。

Runner退出前的清理结果以及回归后的独立复核均为：评估数据库行0、评估ChunkSet 0、评估Storage对象0；正式files/documents/versions各10、ACL 9、pending版本10、upload对象10、正式ChunkSet 0、M1德国仓可售库存125，`baseline_restored=True`。一次性能诊断期间人工停止的中间运行曾留下1个隔离评估租户和90个ChunkSet，已按精确租户/对象键清理并验证正式基线后才重新运行；该中间结果没有被当作正式报告。

### 27.8 能证明、不能证明与排查方向

能证明：18份当前固定文档在同一R04合格Artifact上真实经过现有Chunk Service；四组完整配置和候选重叠扫描可重复；Golden内容、证据范围与真实Locator可以分层判断；表格、DOCX页眉/页脚/图片OCR及前后文在所有配置均保留；至少`700/850/120`能同时达到34/34、完整段落、0边界断裂、Token上限、顺序、Locator和字节确定性；当前标题保留不足是可复现的Chunk规则问题，不是Parser原文缺失或Locator评估误报；评估数据已经清理且正式基线未被污染。

不能证明：`700/850/120`在真实检索、Reranker、Context或回答中一定最优；109/152标题可以被忽略；近重复率已经达到未来生产目标；18份/34条覆盖所有语言、PDF版面、表格或OCR噪声；DOCX具备物理页码；生产默认配置已经改变；M2-22.6或任何后续RAG/Ragas质量已经验证。M2-22.5的执行工作完成不等于质量门禁通过。

若Golden不完整，先看它在Parser Artifact是否逐字存在；存在但没有单Chunk完整覆盖时查Chunk窗口、段落/句子边界和overlap；内容完整但Locator失败时查页码/source span、DOCX来源或表格坐标。若标题缺失，优先对照`heading_hints`与Artifact原始行，再查Chunker的整行精确匹配和两栏/组合标题拆分，不要降低R04阈值。若表格断裂，查行分组、重复表头与source row；若DOCX图片失去前后文，按段落/Run/图片序号检查Block顺序；若重复构建不同，先查配置Hash、输入Artifact Hash、排序键和非确定性字段。若清理失败，只按隔离评估tenant和已登记对象键排查，禁止全表删除或清空正式Storage。

当前停止。M2-22.5质量矩阵已经完成实际运行，但质量门禁为False；下一动作是等待用户理解本节并决定是否单独授权Chunk规则修复。未经新授权不得修改生产Chunker或默认参数，不得进入M2-22.6，不得安装/运行Ragas，也不得运行Embedding、pgvector、检索、Reranker、Context、Agent、Qwen或前端。

## 28. M2-22.5R确认方案：标题元数据注入与Chunk复验（2026-09-08）

### 28.1 用户确认与当前缺口

用户确认采用标题元数据注入方案，并授权先固化本节文档、随后开始M2-22.5R下一步。核心决定是：不再依赖文本窗口把标题和正文“碰巧切在一起”，而是在切正文前建立可信标题层级，把标题作为正文Chunk的附属属性。

现有实现已经有正确骨架：`DocumentChunk.body_text`保存正文、`heading_path`保存最多9级标题元数据、`retrieval_text`供后续索引使用，数据库`document_chunks.heading_path`也是独立JSONB。当前缺口发生在PDF标题绑定：Chunker把`heading_hints`按规范化文字建表，再用整行`hints.get(line.text)`精确相等判断；一行含编号、标点或多个栏目的标题时，Parser提示虽存在，却不能进入`heading_path`，最终正式矩阵只有109/152。

### 28.2 本修复目标与明确不做

目标：

1. `body_text`只由可定位正文构成，纯标题不作为正文窗口的一部分；
2. `heading_path`保存由Parser Artifact可信提示推导的父子标题层级，并绑定给该标题下至少一个正文Chunk；
3. `retrieval_text`只作为确定性派生视图，由受Token预算约束的标题元数据加正文生成；后续一个章节被拆成多个Chunk时，每个正文Chunk都携带相同标题上下文，不依赖overlap复制标题；
4. 标题元数据必须能回到同一Artifact的提示、页和确定位置；纯标题空壳Chunk、正文短语误报标题、重复页眉/页脚冒充标题、并列标题冒充父子层级均不得算通过；
5. 使用原18份文档、34条Golden和7组矩阵重新验证，并恢复正式数据库/Storage基线。

明确不做：不放宽Golden，不修改R04质量阈值，不用模糊或语义匹配猜标题，不先调整生产Chunk默认参数，不运行Embedding、pgvector、检索、Reranker、Context、Agent、Qwen、Ragas或前端，不进入M2-22.6。Canonical Parser Artifact继续保存原始标题和正文，本修复的“抽离”只发生在Chunk表示中，不删除上游原文。

### 28.3 前置条件与关键语义

- R04正式基线仍为18/18文档、34/34原文、4/4 OCR；
- M2-22.5失败基线固定为标题109/152，当前配置`600/700/100`为33/34 Golden，候选`700/850/120`为34/34、0边界断裂但标题仍109/152；
- 标题、正文和检索视图职责固定如下：

```text
Canonical Parser Artifact：保留原始标题、正文、顺序和Locator
→ 标题绑定器：把可信标题提示转换为当前heading_path
→ body_text：只保存正文及真实source spans
→ heading_path：保存标题层级元数据
→ retrieval_text：在Token预算内渲染 heading_path + body_text
→ Chunk Artifact：同时对正文、标题元数据、来源和Hash负责
```

- `heading_path`中的顺序表示父标题到子标题，不表示左右两栏的并列关系；若现有页级提示不能唯一判断双栏标题对应正文，必须停止并提交Parser Artifact字符范围/坐标补充方案，不能在Chunk层猜测。

### 28.4 按顺序实施的小步骤

#### M2-22.5R-01｜元数据合同、真实模式与RED测试

- 目标：冻结`body_text/heading_path/retrieval_text`职责，新增编号标题、标题与正文同行、多级标题、正文短语误报、纯标题空壳和歧义多标题反例；结合4份真实失败文档确认哪些提示能由现有Artifact唯一绑定；
- 预计文件：`tests/unit/test_document_text_chunker.py`、`tests/unit/test_rag_chunk_metrics.py`，必要时只增加测试辅助代码；
- 验证：新增测试必须在旧实现上以预期断言失败，同时既有精确标题、DOCX、表格、重复页眉/页脚和确定性测试保持通过；
- 停止条件：若真实双栏案例缺少唯一绑定所需位置事实，只记录证据并停止，不进入Parser修改。

#### M2-22.5R-02｜确定性标题绑定实现

- 目标：在Token窗口前处理标题；只把同页、精确文本范围、字符边界明确且无冲突的提示更新到标题栈，按level删除同级及更深旧标题；纯标题不进入正文窗口，同行剩余正文保持原字符映射；
- 预计文件：`app/services/documents/chunking/chunker.py`、`tests/unit/test_document_text_chunker.py`；
- 验证：R-01的RED转绿；标题下正文Chunk携带正确`heading_path`，标题不因Chunk窗口或overlap丢失，正文source spans、Token硬上限和字节确定性不回归；
- 边界：若需要新增Parser字符范围/坐标，先停止并提交本节增补与用户确认，不自动修改`pdf.py`、`native.py`或Artifact合同。

#### M2-22.5R-03｜质量门禁防伪与报告语义

- 目标：标题通过必须同时满足“来自真实提示、位于Chunk元数据、绑定至少一个正文Chunk、层级正确”，不能靠复制字符串或标题空壳制造152/152；
- 预计文件：`app/evals/chunk_metrics.py`、`app/evals/rag_runner.py`、`tests/unit/test_rag_chunk_metrics.py`及Runner集成测试；
- 验证：伪造heading_path、标题仅在`body_text`、只有标题无正文、并列标题伪装层级均失败；每组配置继续独立保存门禁结果。矩阵总完成状态与候选质量状态分离：故意用于比较的失败配置继续保留，只有至少一个按冻结规则选出的候选满足全部质量条件时才能声明候选门禁通过，不用“所有实验配置必须同时通过”制造不可解释结论，也不删除失败配置。

#### M2-22.5R-04｜正式矩阵复验与清理

- 目标：复用原18份文档、34条Golden、4组首轮与候选overlap 80/100/120，重跑正式Parser→Chunk矩阵；
- 预计文件：不预设生产代码；生成Git忽略报告并更新本记录、M2入口和总看板；
- 验证：18/18 R04、34/34内容与Locator、标题152/152且每个标题绑定正文、段落与表格完整、DOCX视觉上下文、Token范围、重叠、顺序、Locator、确定性及精准清理；
- 停止点：无论通过或失败都先向用户解释；不得自动更新生产默认配置或进入M2-22.6。

### 28.5 完整调用链位置

```text
前端：不经过
→ API：仅正式复验时复用上传/建文档入口
→ Schema：公开请求/响应不改；复用Chunk的heading_path元数据
→ Agent / LangGraph / Harness / Tool：不经过
→ Parser/R04 → Canonical Parser Artifact
→ Chunk标题绑定器 → heading_path
→ 正文分组与Token窗口 → body_text
→ 标题元数据 + 正文 → retrieval_text
→ Canonical Chunk Artifact → Chunk Storage / DocumentChunkSet
→ Chunk质量评估与精准清理
→ Embedding / pgvector / Retrieval / Reranker / Context / Agent / Qwen / Ragas / 前端：不运行
```

基础方案复用现有`heading_path`和数据库JSONB，不需要迁移；只有证据证明现有Artifact缺少双栏唯一定位时，才另行讨论Parser元数据扩展。

### 28.6 阶段完成标准

M2-22.5R只有同时满足以下条件才可完成：

- 元数据合同和反例测试已冻结，旧实现RED、修复后GREEN；
- 真实标题不能只靠字符串出现或标题空壳通过；
- 至少一个冻结候选达到34/34 Golden与Locator、152/152标题且全部绑定正文、0可避免边界断裂、45/45表格、DOCX页眉/页脚/图片OCR/前后文完整、18/18顺序/Locator/确定性、0空Chunk并满足Token硬上限；
- 其他失败实验配置和Bad Case仍完整保留；
- 专项、相邻和明确排除下游功能的完整允许范围回归已实际运行；
- 评估租户数据库行、ChunkSet和Storage对象归零，正式10份文档、0正式ChunkSet与M1库存125恢复；
- 三份进度记录同步实际通过或失败，用户理解后再决定生产参数或M2-22.6。

### 28.7 主要风险与排查方向

- 标题误报：先查提示是否在同页唯一精确出现及字符边界，不允许模糊匹配正文短语；
- 标题层级错误：按level维护父子栈，同级标题必须替换旧同级，不把并列栏目标记成父子；
- 标题空壳：要求标题元数据绑定至少一个非标题正文单元，评估器不计只含标题的Chunk；
- 双栏歧义：若页级文字顺序不足，停在Artifact定位层，不凭标题出现顺序猜正文归属；
- Token回归：`retrieval_text`中的标题仍计入`max_tokens`，长标题路径按现有有界策略渲染，完整`heading_path`元数据不因渲染截断而丢失；
- Locator与Hash：正文字符映射保持真实，标题元数据、配置和输入Artifact都参与确定性Chunk Hash；
- 参数混淆：先只改标题绑定，复验后再比较原7组参数，不把算法与生产默认值同时改动。

### 28.8 本次文档固化结果与下一动作

本节已记录用户确认、输入输出、完整链路、四个小步骤、每步文件与验证、完成标准、风险和禁止范围。当前授权允许随后开始R-01元数据合同与RED测试；在R-01完成并记录前不进入R-02，实现期间若发现双栏需要Parser定位扩展则必须停止等待确认。

## 29. 2026-09-08｜意图分流模型调用原则补充

### 29.1 用户确认与本次目标

用户指出：如果先单独调用一次大模型做意图识别，再调用一次大模型生成答案，那么即使增加了L0至L3分流，简单请求仍然至少需要两次模型调用，成本和延迟问题并没有真正解决。用户确认先更新相应文档，本次不授权M2-22.8R代码开发。

因此补充冻结以下设计原则：**意图识别是一层路由能力，但不等于所有请求都固定新增一次LLM调用。** 候选方案采用两级分流：能够被程序高置信识别的明确请求直接进入对应路径；只有表达含糊、信息不足或可能跨路径的请求，才调用一次输出严格结构化结果的模型，并尽量在这一次结果中同时完成意图、执行级别、工具路由和业务参数提取。

暂定模型调用目标如下：

- L0普通问答不把“分类”和“回答”拆成两次独立调用，通常共用一次回答模型调用；
- 明确且高置信的Business查询允许0次模型调用，由程序解析受限参数、调用Tool并用确定性模板返回；无法可靠解析时，最多用1次模型同时完成意图判断和参数提取；
- Knowledge问答只保留必要的检索后有依据回答，通常为1至2次模型调用，是否需要模型路由取决于程序分流置信度；
- 固定复合查询使用受控Pipeline，并行执行相互独立的Tool，典型目标不超过2次模型调用；
- 只有真正需要拆解、追问、冲突处理或多轮研究的L3请求才进入Supervisor与Worker，并受轮次、Token、成本和超时预算约束。

以上数字是M2-22.8R方案阶段需要用轨迹和成本实验验证的**候选目标**，不是当前已经实现或已经达标的能力。具体的高置信规则、置信度阈值、结构化Schema、失败回退和澄清策略，应在M2-22.8完成后提交M2-22.8R完整实施方案时再确认；不得仅用不断扩张的关键词表冒充通用自然语言理解。

### 29.2 本次修改文件与职责

1. `docs/PROJECT_PROGRESS.md`：在总进度看板冻结“不固定新增一次LLM”的项目级决策，并写入近期记录；
2. `docs/progress/M2/M2_KNOWLEDGE_RAG.md`：在M2阶段入口补充执行分流原则、成本风险和后续验证指标；
3. `docs/progress/M2/records/M2_22_CROSS_BORDER_RAG_EVALUATION_PLAN.md`：细化M2-22.8R的范围、暂定模型调用目标、验证维度和本次用户确认记录。

### 29.3 调用链位置

本次只更新设计和进度文档，没有经过或修改“前端 → API → Schema → Agent/LangGraph → Harness → Tool → Service → Repository/Model → PostgreSQL/pgvector/Storage/外部Provider”中的任何运行时代码。未来M2-22.8R实施时，主要位于API之后、Agent/LangGraph和Tool之前的执行分流层，并通过Harness轨迹记录真实调用次数、Token、成本和延迟。

### 29.4 验证、边界与排查方向

验证方法：检查三份文档中的核心原则、层级目标和阶段顺序是否一致；检查Markdown代码围栏、冲突标记和行尾空白；检查本次范围是否只涉及文档。

实际结果：三份文档均检索到“不固定新增一次LLM”“程序高置信分流”“低置信结构化模型”和候选调用目标；Markdown代码围栏数量均为偶数，行尾空白和冲突标记均为0；范围内`git diff --check`无错误，仅提示Git未来可能把现有LF转换为CRLF。

能证明：设计口径已经明确区分“存在意图路由能力”和“固定增加一次模型调用”，并给出了后续可以测量的调用次数目标。

不能证明：意图路由已经实现、程序规则能够覆盖真实用户表达、模型调用次数已经下降，或准确率、Token、成本、p50/p95延迟已经达标。这些必须等M2-22.8R代码实现和真实轨迹实验后才能确认。

未来若实际调用次数超过目标，优先检查：是否把分类和回答机械拆成两次模型调用；明确Tool请求是否被错误送入Supervisor；工具结果是否在不需要推理时又交给模型润色；低置信请求是否缺少结构化路由和澄清回退。

本次文档补充不改变当前开发停点：M2-22.5R标题元数据注入修复方案已经获得授权，下一动作仍是R-01元数据合同、真实失败模式和RED测试；不得因本次文档调整提前开始M2-22.8R代码开发。

## 30. M2-22.5R-01实施记录：合同反例与真实提示审计（2026-09-08）

### 30.1 本步目标、输入输出与调用链

本步只执行已确认方案中的R-01，不修改生产切块策略。输入是现有`ArtifactHeadingHint`、Canonical Parser Artifact中的页级最终文本、现有Chunk输出，以及4份标题指标失败文档；输出是可执行反例、真实提示分类证据和是否具备进入R-02的判断。

调用链位置如下：

```text
R04通过的Canonical Parser Artifact
→ 只读审计heading_hints与最终页文本的关系
→ 现有DocumentTextChunker合同反例
→ Chunk标题质量指标防伪反例
```

本步不经过前端、公开API、Agent/LangGraph、Harness、Tool、Embedding、pgvector、检索、Reranker、Context、Qwen或Ragas，也不写PostgreSQL与Storage。

### 30.2 修改文件与职责

1. `tests/unit/test_document_text_chunker.py`：新增3个合同反例，分别冻结“编号/同行标题进入元数据且不进入正文”“父子标题路径绑定正文且不产生标题空壳”“正文中的标题短语不得被提升为元数据”；
2. `tests/unit/test_rag_chunk_metrics.py`：新增质量门禁反例，要求仅把标题写入`heading_path`、但Chunk没有正文时不得计为标题保留；
3. `docs/PROJECT_PROGRESS.md`：同步R-01真实结论、停止点和验证基线；
4. `docs/progress/M2/M2_KNOWLEDGE_RAG.md`：同步M2阶段当前状态、阻塞和下一动作；
5. 本过程记录：保存完整诊断证据，并明确修订前置条件。

没有修改`app/services/documents/chunking/chunker.py`、Parser、Artifact Schema、R04阈值、生产Chunk默认参数、数据库迁移或任何下游RAG实现。

### 30.3 RED测试实际结果

执行：

```text
.venv\Scripts\python.exe -m pytest tests/unit/test_document_text_chunker.py tests/unit/test_rag_chunk_metrics.py -q
```

实际结果为`3 failed, 14 passed in 8.45s`。3个失败均为R-01预期RED：

- 编号标题`2. IOSS适用范围`没有进入`heading_path`；
- 多级案例只保留父标题，没有把编号子标题绑定给正文；
- 现有标题指标把只有标题、没有正文的空壳Chunk错误计为通过。

正文短语不误提升的反例和原有14个相关测试保持通过。`ruff format --check`显示测试文件无需改格式，`ruff check`定向检查通过。这组RED不是产品回归通过结论，而是用可重复失败冻结待修复合同；生产代码尚未修改，所以本步没有伪称已经完成专项、相邻或完整GREEN回归。完整回归仍属于R-04正式复验的强制完成条件。

### 30.4 真实文档提示审计

使用现有本地评估源和原生PDF解析器，只读比较每条提示与同页规范化最终文本，没有上传、建文档、写数据库或运行Chunk之后的任何功能。分类规则是：整行精确出现、在单一物理行内唯一出现、出现位置歧义、最终页文本中缺失。

| 文档 | 提示总数 | 整行精确 | 同行唯一子串 | 歧义 | 最终页文本缺失 |
|---|---:|---:|---:|---:|---:|
| 双栏市场简报 | 6 | 2 | 4 | 0 | 0 |
| 欧盟VAT OSS指南 | 64 | 24 | 8 | 1 | 31 |
| 欧盟GPSR事实表 | 11 | 2 | 6 | 0 | 3 |
| Safety Gate通报 | 4 | 1 | 3 | 0 | 0 |
| 合计 | 85 | 29 | 21 | 1 | 34 |

代表性事实：双栏文档的“左栏｜销量观察”和“右栏｜动作建议”被压在同一物理文本行内；OSS的若干一级提示实际是正文项目符号句；GPSR的`EUR 11.5 billion per year`是数据而非标题；Safety Gate的`Alert number`和具体编号是字段名/字段值组合。代码合同也把`ArtifactHeadingHint`定义为“保留的来源标题线索，不能提升为保证为真的事实”。

### 30.5 结论与问题重新归因

标题元数据注入这个架构方向仍然成立：可信标题应该进入`heading_path`，正文留在`body_text`，`retrieval_text`由两者确定性派生。但R-01推翻了原验收分母：152条`heading_hints`不是152条可信标题，109/152只能表示现有Chunker消费了多少启发式提示，不能直接解释为“43个真实标题被切坏”。

如果继续要求152/152，最容易出现的假通过就是把项目符号、金额、字段值和缺失提示全部硬塞进Chunk元数据。这既违背“不得放宽或伪造Golden”，也会污染后续检索。因此第28.6节中的`152/152`完成标准自本次证据起暂停使用；它是已确认方案形成时的历史假设，不能在用户确认增补前静默改成另一个数字。

问题现在分成三层：

- `Parser Artifact`层：`heading_hints`是候选线索，且通常只有页码、文本和层级，没有统一字符范围、栏位或正文归属；
- `Chunk规则`层：当前整行精确匹配确实漏掉编号标题和可唯一定位的同行标题，但这种保守行为同时避免了一部分误提升；
- `Locator/评估`层：把所有提示当正式标题Golden是指标合同错误，需要独立的可信结构标题真值集。

### 30.6 建议增补与停止条件

建议在不修改原34条内容Golden的前提下，单独增加人工复核并版本化冻结的“结构标题Golden”。每条至少记录来源文档、页、标题原文、层级、与正文的预期关系以及可验证Locator。152条原始提示继续完整保留，用于衡量Parser候选覆盖率和噪声，不再直接作为Chunk标题质量分母。

确认后再依次执行：

1. 先冻结4份失败文档的可信结构标题Golden和明确反例；
2. Chunk层只消费能够在同页、字符边界和顺序上确定性确认的标题；项目符号、字段值、歧义项不提升；
3. 对双栏标题如果现有Artifact仍无法唯一建立“标题属于哪段正文”，停止并提交Parser字符范围/坐标增补，不用左右出现顺序猜父子关系；
4. 修改防伪指标，只接受“可信标题元数据绑定至少一个正文Chunk”；随后才进入正式矩阵和完整清理回归。

能证明：当前152分母不可信；编号/同行标题和标题空壳分别存在生产合同及评估器缺口；直接注入全部提示会制造错误元数据；本步没有污染正式数据库或Storage。

不能证明：可信结构标题的最终数量、现有Artifact足以绑定全部真实标题、生产Chunk策略已经修复、候选参数已经通过、或M2-22.6任何能力已经验证。

根据第28.4节已经确认的停止条件，R-02未开始。下一动作是等待用户理解并确认：是否把正式标题验收从“全部152条启发式提示”修订为“人工冻结的可信结构标题Golden”，同时保留152条提示作为Parser诊断数据。未经确认不得实现生产标题绑定，也不得进入M2-22.6。

用户随后明确确认该口径并授权开始，实际实施见第31节；本段保留为当时停止点，不再代表当前状态。

## 31. M2-22.5R-01A实施记录：可信结构标题Golden冻结（2026-09-08）

### 31.1 用户确认与本步范围

用户确认把正式标题验收从“全部152条启发式提示”修订为“人工冻结的可信结构标题Golden”，同时保留原提示作为Parser诊断数据，并授权开始实施。本步只冻结4份原标题指标失败文档的真值合同和数据，不修改Parser、R04、生产Chunker、Chunk默认参数、34条内容Golden、数据库或Storage。

输入是4份问题文档的原始PDF视觉版面、Native Parser最终页文本和85条`heading_hints`；输出是版本化候选分类、组合标题、禁止提升反例和“标题路径→正文锚点”关系。调用链只到评估合同：

```text
原始PDF视觉版面 + Native Parser heading_hints/最终页文本
→ 人工逐项分类
→ 可信独立标题 / 组合标题片段 / 非标题
→ 可信heading_path与正文锚点Golden
```

没有经过API、Agent/LangGraph、Harness、Tool、Repository/Model、PostgreSQL、Storage、Embedding、pgvector、检索、Reranker、Context、Qwen、Ragas或前端。

### 31.2 真值数据与合同

新增`m2-chunk-heading-golden-v1`数据，SHA-256为`93428d44fe539ed4eafbed6b80169818fc273c6c675a807de887fa20c3aa9c17`。85条原始提示无遗漏、无重复归属地被分为：

| 来源 | 提示总数 | 可独立作为标题 | 组合标题片段 | 明确不是标题 |
|---|---:|---:|---:|---:|
| 双栏市场简报 | 6 | 6 | 0 | 0 |
| 欧盟VAT OSS指南 | 64 | 28 | 0 | 36 |
| 欧盟GPSR事实表 | 11 | 4 | 2 | 5 |
| Safety Gate通报 | 4 | 0 | 2 | 2 |
| 合计 | 85 | 38 | 4 | 43 |

2个组合标题是`THE NEW GENERAL PRODUCT`+`SAFETY REGULATION`和`Safety Gate`+`Alerts`；它们必须作为一个视觉标题使用，不能把片段伪装成父子章节。43个非标题包括OSS正文项目符号、GPSR栏目眉和金额图表标注、Safety Gate字段名及告警编号。

另冻结26条可信正文绑定案例：双栏4条、OSS 16条、GPSR 5条、Safety Gate 1条。每条都记录来源、文档、物理页、完整`heading_path`、标题原文、非标题正文锚点及`following_flow/same_column`关系。它们是针对已知结构风险的正式Golden，不冒充枚举63页OSS指南中的每一个视觉小标题。

### 31.3 修改文件与职责

1. `app/schemas/evaluation.py`：新增严格、框架无关的标题审计与Golden合同；强制85条提示分区计数一致、每个提示Occurrence只能归类一次、组合标题文本由有序片段构成、正文锚点不得等于标题、同栏关系必须同页、正文与标题必须属于同一文档；
2. `data/evals/m2_cross_border_chunk_headings_v1.json`：保存4份问题文档的38条独立标题、2个组合标题、43条非标题反例和26条可信正文绑定；
3. `tests/unit/test_m2_chunk_heading_golden.py`：冻结版本、数量和文件Hash，重跑Native PDF Parser核对85条提示完整分区，核对26组标题/正文确实存在于声明页，并覆盖分区篡改和跨文档绑定拒绝；
4. 三层进度文档：同步确认、实际结果、停止点和下一方案。

### 31.4 TDD与实际验证

1. 新测试在合同尚不存在时先得到预期RED：收集阶段因无法导入`ChunkHeadingGoldenDataset`而停止；
2. 合同与数据实现后，专项为`5 passed in 14.41s`；
3. 标题Golden、既有评估合同和40条Smoke数据相邻回归为`89 passed in 16.00s`；
4. 全范围Ruff通过，`mypy app`为156个源码文件通过，`compileall -q app`通过；
5. PDF视觉审计临时页图位于受控`tmp/pdfs/m2-heading-audit`，复核后按已验证绝对路径删除，`removed=True`；没有产生数据库/Storage评估数据，因此不需要数据库清理；
6. R-01中故意冻结的3个生产Chunk/指标RED仍等待后续修复，本步没有把它们删除或改成宽松断言。生产代码没有修改，因此完整Chunk矩阵和完整GREEN回归不在本小步伪报为完成。

### 31.5 能证明与不能证明

能证明：4份问题文档的85条Parser提示已经逐项分类；旧152分母中的已知噪声不会再被强行写成标题；26条标题与正文关系有独立、可复查的真值；组合标题、同栏关系和非标题反例已有严格合同；Golden自身防重复、防跨文档和防篡改。

不能证明：生产Chunker已经注入标题；26条案例代表全部文档的所有视觉小标题；双栏标题已经可以由现有Artifact唯一绑定；候选Chunk参数已经通过；18文档正式矩阵、M2-22.6或任何下游能力已经验证。

### 31.6 新发现的确定性阻塞

双栏市场简报视觉上有清晰的左右栏标题和各自正文，但当前Native PDF Artifact把同一高度的左右文字压进同一个页级文本行。例如标题成为“左栏｜销量观察　右栏｜动作建议”，下一行又同时包含左右栏正文。`PdfHeadingHint`只有文字、字体、页码和层级；Native Adapter也没有给提示写入已有的`bounding_box`，正文更没有逐行字符范围与坐标。

因此，Chunk层仅凭当前Artifact无法证明“广告预算属于右栏动作建议”而不是左栏销量观察。按第28节的防猜测停止条件，R-02生产标题绑定没有开始；必须先确认最小Parser Locator增补。

## 32. M2-22.5R-01B已确认方案：PDF行级Locator增补

### 32.1 目标与明确不做

目标是在不改变PDF最终原文、不修改R04阈值的前提下，为Native PDF页增加确定性的行级事实：物理行号、精确文字、在页文本中的真实字符范围、页面坐标，以及标题提示所引用的行。Chunk层随后才能按真实栏位绑定标题与正文。

明确不做：不在Parser里直接生成最终`heading_path`，不使用模糊/语义模型猜标题，不调整Chunk参数，不改34条内容Golden，不运行Embedding、pgvector、检索、Reranker、Context、Agent、Qwen、Ragas、前端，也不进入M2-22.6。

### 32.2 拟按顺序实施

1. **Locator合同与RED**：为PDF Native结果和Canonical Artifact设计有界行级结构；旧Artifact缺省字段仍能读取，新Artifact必须校验页码、行序、字符范围、坐标、提示引用和无重叠关系。先用双栏标题、左右正文、组合标题和映射失败反例冻结测试；
2. **Native提取**：从PyMuPDF现有`dict`行数据保留top-left坐标，并把每个可验证物理行映射回当前页文本的真实字符范围；无法精确映射的行显式省略或拒绝，不伪造offset；
3. **Artifact适配**：Native Adapter确定性写入行级Locator和标题提示坐标/行引用，更新Parser/Adapter身份与Hash；旧v1 Artifact保持向后兼容，新解析的几何字段参与内容Hash；
4. **真实复验并停止**：先验证双栏4组标题正文关系可唯一定位，再验证4份问题PDF及18份R04文档的原文、页数、Golden和质量门禁不回归。通过后仍先向用户解释，才回到既有R-02标题元数据注入。

预计修改`app/services/documents/parsers/pdf.py`、`app/services/documents/artifacts.py`、`app/services/documents/parsers/native.py`及对应Parser/Artifact/路由/真实评估测试；不预设数据库迁移，因为定位事实保存在版本化Artifact中。

### 32.3 完成标准与风险

- 双栏左右标题和正文各自拥有可验证、互不混淆的坐标与真实字符范围；同一视觉行的左右片段不能被合并成一个假标题；
- 标题提示必须引用真实行，正文行不能因字体最大值被提升；组合标题仍由Golden明确判断，不由Parser擅自合并；
- 旧Artifact可读，新Artifact Hash稳定，重复解析字节确定；18份文档R04与34条内容Golden不回归；
- 专项、相邻和禁止下游边界内的完整允许范围回归实际运行；临时数据精准清理并恢复正式基线；
- 如字符范围无法无损映射当前页文本，优先调整Canonical PDF文字组织合同并再次请求确认，不能伪造offset。

主要风险是PyMuPDF的“展示行”与`get_text("text", sort=True)`最终字符串不总是一一对应，尤其是双栏、连字符、旋转文字和图表。排查顺序固定为原始span/line坐标→页文本字符映射→Native Adapter→Artifact校验→Chunk绑定；不能在Chunk层用空格数量或标题出现顺序补猜。

用户随后明确表示“开始下一步”，据此只实施本节R-01B；实际结果见第33节。

## 33. M2-22.5R-01B实施记录：PDF行级Locator增补与验收阻塞（2026-09-08）

### 33.1 本步输入、输出与调用链

本步缺少的不是重新识别152个标题，而是Parser已经看见物理行，却没有把行号、字符位置和坐标交给Artifact。输入是通过既有PDF安全限制的字节流、PyMuPDF `get_text("text", sort=True)`页文本与`get_text("dict", sort=True)`物理行/span；输出是每页有界的`layout_lines`：一基行号、原行文字、可证明时的页文本字符起止、top-left坐标和显式页尺寸，以及每个`heading_hint`引用的物理行与同一坐标。

调用链为：

```text
PDF字节流
→ Native PdfParser（页文本 + 物理行/坐标 + 可证明字符范围）
→ Native Adapter
→ Canonical Parsed Artifact（pdf_layout_lines + heading hint行引用）
→ R04质量门禁
→ 停止
```

专项没有经过Chunker，也没有经过Embedding、pgvector、检索、Reranker、Context、Agent/LangGraph、Harness、Tool、Qwen、Ragas或前端。只有正式R04回归按原有API→Service→Repository/Model→PostgreSQL/Storage链临时摄取18份文档，并在`finally`中精准清理。

### 33.2 实现与防伪规则

1. `app/services/documents/parsers/pdf.py`：Parser身份升为`m2-pdf-v2`；新增严格`PdfBoundingBox`和`PdfLayoutLine`，保留PyMuPDF物理行顺序、页面尺寸和坐标，并用只跨行内空白的逐字匹配回填真实字符范围；找不到不重叠证据时保存`None/None`，不伪造offset；标题提示必须引用同页真实物理行；
2. `app/services/documents/artifacts.py`：新增`ArtifactPdfLayoutLine`和`ArtifactTextBlock.pdf_layout_lines`，校验一基连续行号、页码一致、坐标在页内、字符范围成对/不越界/不重叠、范围原文一致，以及标题引用存在且文字/坐标相同；新字段为空时不参与旧v1载荷序列化，保证旧Artifact Hash可复验，新几何非空时进入内容Hash；
3. `app/services/documents/parsers/native.py`：只把PDF Adapter身份升为`m2-native-pdf-adapter-v2`，DOCX/XLSX/CSV继续使用`m2-native-adapter-v1`；逐项转换行坐标和标题引用；
4. `app/services/documents/parsers/__init__.py`：公开新的PDF行与坐标合同；
5. `tests/fixtures/pdf_factory.py`、`tests/unit/test_pdf_parser.py`、`tests/unit/test_parsed_artifacts.py`：新增同高左右栏合成PDF、真实range/坐标、标题行引用、旧载荷兼容、假range拒绝和几何改变Hash反例；
6. `tests/unit/test_m2_pdf_layout_locator.py`：真实加载4份合成PDF和8份官方PDF，重复解析并核对12/12确定性；检查4份标题问题PDF的38条独立标题和4个组合片段都有真实行/range，并验证双栏4组标题正文位于同一物理半栏。

这里没有把组合标题交给Parser擅自合并，也没有把不能唯一映射的重复表格文字硬塞进某个字符位置。物理行仍保留真实坐标，字符范围明确为空，后续可以区分“有几何事实”和“字符Occurrence不唯一”。

### 33.3 TDD、专项与相邻回归

1. RED：新增测试首次收集因`ArtifactPdfLayoutLine`不存在而报ImportError，证明测试先于实现；
2. Parser/Artifact基础GREEN为`20 passed`；标题Golden与相邻集合随后为`25 passed`；12份PDF真实Locator专项最终通过，4/4双栏同栏关系通过；
3. 禁止下游边界内的完整允许单元范围为`369 passed, 2 skipped, 3 failed in 104.30s`。3个失败与R-01冻结结果相同：编号标题没有进入`heading_path`、父子路径缺少编号子标题、质量指标仍会误收标题空壳；它们等待R-02，不能在本步删除；
4. Parser/Chunk Service、Parser/Chunk Runner和两组合成Seed数据库相邻集成为`21 passed in 86.99s`；
5. `ruff check app tests scripts migrations`通过，`mypy app`为156个源码文件通过，`compileall -q app`与`git diff --check`通过。额外执行的仓库根目录`ruff check .`显示旧`api/`、`config/`、`tools/`、`utils/`等非当前维护目录共98个既有问题，本步没有越界改写这些文件，也不把该命令伪报为通过。

### 33.4 18文档、34条Golden与清理实测

正式Parser/R04命令实际摄取18份文档，结果不是全绿：

| 指标 | 实际结果 |
|---|---:|
| 上传成功 | 18/18 |
| 解析完成 | 17/18 |
| 全部Golden恢复 | 32/34 |
| 8份官方PDF Golden | 14/14 |
| OCR Golden | 2/4 |
| 已完成文档R04 | 17/17 `accepted` |
| 路由 | Native 16、Hybrid 1、Docling 0；扫描件失败 |

唯一失败是`m2-complex-v1-scanned-receiving-ticket`。Docling/RapidOCR Worker已经返回结果，但没有在既有2秒收尾窗口退出，第一次正式运行记录`shutdown_timeout`，总耗时约93.48秒、峰值约1.98GB；随后单件Router/OCR Smoke再次记录同类失败，总耗时约99.29秒、峰值约1.96GB。连续两次相同失败说明不能当作一次偶发噪声；失败位于既有`LocalDoclingProvider`进程生命周期层，不在本次Native PDF Locator、Artifact适配或R04阈值层。本步没有放宽超时、改R04或跳过扫描件。

正式Runner仍完成精准清理：评估数据库行0、评估Storage对象0；正式基线恢复为10个File、10个Document、10个Version、9条ACL、10个Pending Version、10个上传对象，M1守护库存仍为125。临时JSON报告已在读取结果后按确定路径删除；两个失败Worker PID均不存在；未留下本步评估数据。

### 33.5 能证明、不能证明与停止点

能证明：Native PDF不再只有整页字符串；双栏左右标题和正文各自有独立坐标与真实字符范围；42个可信标题/组合片段可回到真实物理行；新坐标参与Hash且重复构建稳定；旧Artifact可读；12份正式PDF的Parser/Adapter结构没有回归；17份完成文档仍通过R04，8份官方PDF仍为14/14；评估清理恢复正式数据库与Storage基线。

不能证明：当前完整18份文档仍能达到18/18、34/34和OCR 4/4；Docling Worker退出问题已经解决；生产Chunker已经消费行级Locator；标题已经按元数据注入正文Chunk；R-02的3个RED已经修复；原7组Chunk矩阵已经用新Artifact重跑；M2-22.6或任何下游能力已经验证。

当前状态为“R-01B实现完成、验收受阻”。排查优先级已经定位为Docling子进程发送Snapshot后的退出/线程句柄收束，而不是Parser Artifact文字、Chunk规则或Locator。按单步协作边界停止，等待用户理解并决定是否单独授权处理或复验该阻塞；不得自动进入R-02或M2-22.6。

## 34. M2-22.5R-01B补充实施记录：Docling一次性Worker确定性退出（2026-09-08）

### 34.1 授权、缺口、输入输出与边界

用户在理解“路由正确，失败发生在OCR结果返回后的Worker收尾”后明确表示开始下一步。本小步只修复第33节暴露的Docling进程生命周期阻塞，不修改Parser选路、R04阈值、Canonical文字内容、Chunk规则或标题Golden。

大白话说，旧流程像是工人已经把OCR结果交到窗口，但身后的工具线程还没有收好，父进程因此按安全规则拒收。输入仍是已经受大小限制、确实被Router判定需要增强解析的扫描PDF字节；输出仍是原来的严格`DoclingParseSnapshot`。本步只保证一次性Worker在同步发送完整结果并关闭单向Pipe后立即结束，让父进程继续执行“结果到达、Worker已退出、退出码正常、Snapshot复验”四道条件；没有把2秒收尾窗口调大，也没有允许仍存活的Worker蒙混通过。

调用链位置为：

```text
公开上传/文档登记
→ Parser Service
→ Router（既有健康度与复杂度规则，本步未改）
→ LocalDoclingProvider父进程边界
→ spawn一次性Worker
→ 本地CPU Docling + RapidOCR
→ 严格Snapshot同步写入Pipe并关闭
→ Worker确定性退出（本步）
→ 父进程确认退出码并复验Snapshot
→ Docling Adapter → Canonical Artifact → R04
→ 停止
```

专项和正式R04复验均未运行Chunker、Embedding、pgvector、检索、Reranker、Context、Agent/LangGraph、Harness、Tool、Qwen、Ragas或前端。相邻回归只运行既有Parser/Chunk的确定性测试与数据库Service合同，没有启动上述下游功能；R-02标题注入仍保持RED。

### 34.2 最小实现与防放宽规则

1. `app/services/documents/parsers/docling.py`：新增只允许一次性子进程调用的`_exit_docling_worker`。Worker成功或固定失败消息已经由`Connection.send_bytes`同步写完后，先关闭连接，再用进程级退出绕过Docling/ONNXRuntime可能残留的非守护线程；最终消息未发送成功时保留非零退出码。父进程的总时限、RSS/Snapshot上限、2秒收尾窗口、活进程拒收、退出码和Snapshot复验全部不变；
2. `tests/fixtures/docling_process_worker.py`：把`lingering.pdf`改成更接近真实故障的“后台非守护线程滞留”，并增加复用正式退出助手的`hard-exit-lingering.pdf`；
3. `tests/unit/test_docling_process_isolation.py`：新增“结果完整发送后即使存在滞留线程也能成功、PID消失”的回归；旧滞留Worker仍必须得到`shutdown_timeout`，证明不是放宽父进程门禁；
4. 本记录、M2入口与项目总看板：同步实际验证、基线、边界和下一停止点。

### 34.3 TDD、真实扫描件与正式18文档结果

1. RED：测试先引入尚不存在的退出助手，首次收集得到预期ImportError；实现后Docling进程隔离专项为`6 passed in 19.88s`，其中故意滞留、不调用正式退出助手的Worker仍被拒绝；
2. 单件正式Router/RapidOCR Smoke为`1 passed in 109.47s`。扫描PDF保持`unusable → docling`并恢复2/2事实；日志为`status=success`、Worker PID 39876、`spawn_ms=5798`、`ready_ms=5820`、`total_ms=101853`、`peak_rss_bytes=1959198720`，随后确认PID不存在；
3. 第一次18文档复跑已经达到18/18解析、34/34 Golden和OCR 4/4，但Runner如实标为`failed`：运行前数据库中的正式M2 Seed为0条，而Storage已有10个上传对象，因此不是干净基线。该次评估租户行与对象仍清理为0；随后只用既有两个M2 Seed入口恢复正式基线，并在运行前确认`10 files / 10 documents / 10 versions / 9 ACL / 10 pending / 10 uploads / M1 125 / clean=True`；
4. 干净基线上的第二次正式Parser/R04运行最终为`run_status=completed`：18/18上传、18/18解析、34/34 Golden、外部14/14、OCR 4/4，Parser事实恢复率和OCR字段准确率均为1.0；路由Native 16、Docling 1、Hybrid 1，18/18 R04决定均为`accepted`。p50/p95/max解析耗时为237/65,040/65,040 ms；
5. 正式Runner清理结果为评估数据库行0、评估Storage对象0；正式基线恢复10个File、10个Document、10个Version、9条ACL、10个Pending Version、10个上传对象，M1守护库存125，`baseline_restored=true`；
6. 随后的21项相邻数据库测试会重置正式M2表，测试后审计实际发现数据库正式记录为0、Storage仍为10。最终再次只运行既有两个M2 Seed入口并复核为`10/10/10/9/10/10/M1 125/clean=True`；临时Parser报告已按确定路径删除，没有留下本步评估数据或Docling Worker。

### 34.4 专项、相邻、完整允许回归与工程门禁

- Docling进程隔离专项在最终格式化后复跑为`6 passed in 14.40s`；禁止下游边界内的完整允许单元范围为`370 passed, 2 skipped, 3 failed in 75.23s`。新增生命周期用例进入通过数；3个失败与R-01时完全相同，分别是编号标题未进入`heading_path`、父子路径缺少编号子标题、标题空壳被指标误收，继续作为R-02的正式RED；
- Parser/Chunk Service、Parser/Chunk Runner和两组合成Seed相邻数据库集成为`21 passed in 59.79s`；
- `ruff check app tests scripts migrations`通过；本步3个代码/测试文件格式检查通过；`mypy app`为156个源码文件通过；`compileall -q app`和`git diff --check`通过。diff检查仅提示若干既有工作区文件未来会按Git配置把LF转换为CRLF，没有空白错误。

### 34.5 能证明、不能证明、风险与停止点

能证明：本次失败不是Router把扫描件送错路径；正式Docling Worker能在完整Snapshot发回后确定性退出；父进程没有通过增加等待时间或接受活进程来制造成功；故意不执行退出协议的滞留Worker仍被拒绝并清理；同一代码状态下已重新得到18/18 Parser、34/34 Golden、OCR 4/4和18/18 R04接受；评估数据已经清零且正式数据库/Storage/M1基线恢复。

不能证明：任意第三方库子进程都应该使用这种退出方式；多个Docling任务并发时已有全局队列或背压；直接DOCX OCR已经获得同样的进程隔离；生产Chunker已经消费新PDF行级Locator；标题元数据已经注入正文Chunk；3个R-02 RED已经修复；7组Chunk矩阵已在新标题规则下重跑；M2-22.6或任何检索/生成能力已经验证。

后续若再次出现`shutdown_timeout`，先看最终消息是否发送、Pipe是否关闭、Worker退出码和是否走了正式`_docling_worker_entry`；若在结果发送前卡住，仍按既有总时限/RSS门禁处理，不能把进程级退出当成推理超时修复。若出现`worker_crash`，先区分消息发送失败与本地模型/ONNX异常。`os._exit`只位于一次性Worker末端，不能搬到主服务或可复用进程。

本小步完成后停止。R-01B的正式验收阻塞已经解除，但M2-22.5标题质量门禁仍未通过；下一动作只能是在用户理解并单独授权后开始既有R-02确定性标题元数据绑定。不得自动进入R-02、M2-22.6或任何后续步骤。

## 35. M2-22.5R-02实施记录：确定性标题绑定与语义层级阻塞（2026-09-08）

### 35.1 本步目标、输入输出和调用链

用户明确授权开始下一步。本步只实施第28.4节R-02，不修改R-03质量评估器，不重跑R-04正式7组矩阵，也不进入M2-22.6。

大白话说，旧Chunker会把标题当普通正文一起塞进切割窗口，而且只认“整行和提示一模一样”；新流程先看Parser已经保存的真实物理行、字符范围和坐标，确认标题后把它从正文里拿出来，放进后续正文Chunk的`heading_path`。正文仍保留自己的真实source span，`retrieval_text`再按现有Token预算把标题上下文和正文拼成检索视图。

```text
R04通过的Canonical Parser Artifact
→ PDF物理行/字符范围/坐标
→ 本步确定性标题候选过滤、合并、层级栈和双栏绑定
→ body_text + heading_path
→ 现有Token窗口与overlap
→ retrieval_text + Canonical Chunk Artifact
→ 停止
```

没有经过前端、Agent/LangGraph、Harness、Tool、Embedding、pgvector、检索、Reranker、Context、Qwen或Ragas。相邻集成只验证Parser/Chunk Service与版本化Artifact落库；没有创建索引或运行下游功能。

### 35.2 实现与防伪边界

1. `app/services/documents/chunking/chunker.py`：PDF先把`pdf_layout_lines`的真实source range映射为独立切片；标题必须引用同页真实物理行，或在旧Artifact中满足独立整行/编号前缀的唯一边界。纯标题不进入正文窗口，同行标题后的正文从标题真实结束位置开始；
2. 同页并列栏标题根据bbox位于页面左/右半栏建立互斥标题栈，正文只继承本栏标题，不能按页级字符串顺序猜；连续同栏、同字号、水平对齐且行距处于真实换行范围的标题确定性合并；
3. 项目符号、纯货币数值、引用编号以及与数据值同排的字段标签不提升；较短全大写栏目眉紧邻更完整的多行主标题时，不绑定正文，由完整主标题替代；`Part/Annex/Chapter/Section + 编号`以通用结构标记开启新根章节，不写死Golden标题全文；
4. `app/services/documents/chunking/contracts.py`：行为身份升级为`m2-structure-aware-chunker-v2`，同时保留旧v1合同可读；Chunk Artifact Schema和数据库没有迁移；
5. `app/schemas/evaluation.py`：新评估配置的默认Chunker身份同步为v2，同时保留历史v1报告可读取；没有修改指标计算或门禁阈值；
6. `tests/unit/test_document_text_chunker.py`：冻结标题抽离、编号/同行正文范围、父子栈、正文短语不误报、双栏同栏归属和重复构建确定性；
7. `tests/unit/test_document_chunk_contracts.py`、`tests/unit/test_rag_evaluation_contracts.py`：冻结v2默认身份及v1兼容；
8. `tests/unit/test_m2_chunk_heading_golden.py`：新增真实4份问题PDF→Native Parser→Artifact→Chunker直接验收，逐条比较26个可信正文路径并确认43个非标题没有进入元数据。该测试保留聚合RED，不把真实失败拆掉或改宽松。

### 35.3 TDD与实际结果

编码前标题相关定向RED为`5 failed, 3 passed, 6 deselected`：旧实现仍把精确标题留在正文，编号/同行与父子绑定失败，双栏正文取不到本栏标题。主体实现后相同Chunk测试为`8 passed, 6 deselected`，最终完整文本Chunk文件为`14 passed`；格式化后的文本Chunk、Chunk合同和评估合同定向集合为`102 passed`。

R-01冻结的3个缺口现在是`2 passed, 1 failed`：编号标题和父子标题的生产绑定已通过；唯一失败仍是`test_heading_quality_rejects_metadata_attached_only_to_a_title_shell`，它属于尚未实施的R-03评估器防伪，本步按边界没有修改`app/evals/chunk_metrics.py`。

新增真实直接验收第一次显示只有4/26路径正确且已知非标题被提升；加入确定性多行合并、根章节、数据/字段过滤后，最终达到：

| 项目 | 实际结果 |
|---|---:|
| 可信标题正文路径 | 21/26 |
| 已知非标题未进入`heading_path` | 43/43 |
| 双栏4组同栏关系 | 4/4 |
| 剩余失败 | 5/26 |

剩余5条为：OSS的`Deregistration`、`Exclusion`、`Date on which...`、`Quarantine period`人工Golden要求放在`Specific details`之下；但PDF原生Outline把它们与`Specific details`列为同一二级，Artifact的字体级别也相同。GPSR的`Consumer detriment`人工Golden要求放在`Better enforcement`之下，但该PDF没有Outline，两者字体级别相同，当前Artifact没有共同容器或显式父节点。仅凭页面先后顺序不能唯一证明父子关系。

因此完整允许单元回归如实为`366 passed, 2 skipped, 2 failed in 93.96s`。两个失败分别是上述5条真实路径的聚合RED，以及R-03标题空壳防伪RED；没有新的Parser、Locator、Chunk Token、表格、DOCX或确定性失败。相邻Parser/Chunk Service与两个Seed集成为`19 passed in 29.76s`。

工程门禁为：`ruff check app tests scripts migrations`通过；`mypy app`为156个源码文件通过；`compileall -q app`、`pip check`和`git diff --check`通过，diff只提示既有LF未来可能转换CRLF，没有空白错误。

### 35.4 数据清理与正式基线

本步没有运行正式评估Runner、没有摄取18份评估文档，也没有创建评估租户或评估Storage对象。数据库相邻测试结束后，按既有流程重新运行`seed_m2_files`和`seed_m2_complex_files`，最终只读审计为10个File、10个Document、10个Version、9条ACL、10个pending版本、10个upload对象、0个正式ChunkSet、M1德国仓可售库存125，`clean=True`。

没有删除或覆盖正式文件；没有生成需要额外清理的临时报告。本步没有重跑原18文档、34内容Golden或7组矩阵，因为R-02真实层级RED尚未通过，提前运行R-04既浪费一次Docling成本，也不能得到可声明通过的标题门禁。

### 35.5 能证明、不能证明与停止点

能证明：标题和正文现在是两个职责；纯标题不会占正文窗口；编号/同行正文保留真实范围；双栏使用物理坐标而非字符串顺序；连续多行标题可合并；43条已知噪声没有污染元数据；Chunker行为有新版本身份且旧v1可读；21条真实标题路径已经绑定到正确正文；Token/表格/DOCX/确定性相邻范围没有新回归；正式数据库和Storage基线干净。

不能证明：26/26语义层级已经正确；R-03标题空壳防伪已经修复；至少一个7组候选通过完整门禁；原18份文档/34条内容Golden在Chunker v2下已经正式复跑；生产默认参数应该改变；M2-22.6或任何下游能力已经验证。

当前R-02状态是“主体实现、真实语义层级验收受阻”，不能标记完成。下一步必须先让用户理解并单独确认5条层级真值的处理原则：若以PDF原生Outline为权威，需要有证据地修订与其冲突的OSS Golden；若坚持人工语义父子关系，就必须为无大纲/同字号版面设计新的可审计结构来源，不能把`Specific details`、`Better enforcement`等Golden词语硬编码进生产Chunker，也不能按页面出现顺序猜。未经确认不得进入R-03、R-04、M2-22.6或任何后续功能。

上述阻塞随后由用户逐页视觉裁决解除：两组标题确为同级，问题在人工Golden而不在Parser或Chunker；最终收口见第36节。

## 36. M2-22.5R-02用户视觉裁决、人工Golden纠正与收口（2026-09-08）

### 36.1 裁决与问题归因

用户查看原PDF对应页面后明确确认：

1. OSS中`Specific details`与`Deregistration`、`Exclusion`、`Date on which deregistration/exclusion becomes effective`、`Quarantine period`是同级标题，不是父子关系；
2. GPSR中`Better enforcement`与`Consumer detriment`也是同级标题；
3. Parser提取的字体层级没有问题。

这5条父子关系来自助手在R-01A人工制作Golden时的错误判断。Parser Artifact、OSS的PDF原生Outline和当前Chunker对这两处的同级输出是一致的，因此本次不能修改Parser或生产Chunk规则去迎合错误答案，也不能放宽R04阈值。

### 36.2 实际修改

1. `data/evals/m2_cross_border_chunk_headings_v2.json`：由v1升级为`m2-chunk-heading-golden-v2`。OSS 4条叶标题的`semantic_level`由3纠正为2，路径移除错误父级`Specific details`；GPSR的`Consumer detriment`由3纠正为2，路径移除错误父级`Better enforcement`。标题原文、页码、正文锚点、绑定方向、26条正文关系总数与43条非标题反例均不变；新文件SHA-256为`c4c4b78313118bc9a9e646cd1e3479f7ba71e9a76eb15e982fee1060d12aa4a6`；
2. `app/schemas/evaluation.py`：正式标题Golden合同接受当前v2身份，同时保留历史v1身份可读；未修改指标阈值；
3. `tests/unit/test_m2_chunk_heading_golden.py`：切换到v2数据并冻结新版本与Hash；
4. `tests/unit/test_m2_pdf_layout_locator.py`：Locator真实文档测试切换到v2数据；
5. `docs/PROJECT_PROGRESS.md`、`docs/progress/M2/M2_KNOWLEDGE_RAG.md`与本文：同步R-02完成状态、证据、边界和下一动作。

本次没有为5条标题修改`chunker.py`，因为生产结果本来就是正确的同级关系。完整调用链只到：

```text
原PDF视觉事实
→ 已有Parser Artifact / PDF行级Locator
→ 已有Chunker v2标题元数据绑定
→ v2人工Golden直接比对
→ 停止
```

没有经过Embedding、pgvector、检索、Reranker、Context、Agent/LangGraph、Harness、Tool、Qwen、Ragas或前端，也没有运行R-04的18文档7组正式矩阵。

### 36.3 实际验证结果

1. R-02专项：`tests/unit/test_m2_chunk_heading_golden.py`、`test_m2_pdf_layout_locator.py`和`test_document_text_chunker.py`为`22 passed in 64.29s`，包含26/26真实标题正文关系、43/43已知非标题拒绝、双栏Locator和文本Chunk合同；
2. 相邻Chunk/Evaluation合同：5个相关文件为`110 passed in 66.84s`；
3. 相邻数据库集成：Parser Service、Chunk Service和两个Seed集成为`19 passed in 32.17s`；
4. 禁止下游边界内完整允许单元回归为`367 passed, 2 skipped, 1 failed in 91.70s`。唯一失败是`test_heading_quality_rejects_metadata_attached_only_to_a_title_shell`，属于尚未实施R-03的评估防伪；R-02真实路径聚合RED已经通过；
5. 数据库集成后重新运行两个正式M2 Seed入口；最终只读审计为10个File、10个Document、10个Version、9条ACL、10个pending版本、10个upload对象、0个ChunkSet、M1德国仓可售库存125，Parser和Chunk基线均`clean=True`；
6. 格式化后再次复跑两个真实Golden/Locator测试文件为`8 passed in 76.63s`；`ruff check app tests scripts migrations`、8个R-02相关Python文件的格式检查、`mypy app`（156个源码文件）、`compileall -q app`、`pip check`和`git diff --check`均通过；
7. 用户复核用的5张临时PNG已经从`tmp/pdfs/m2-heading-dispute`删除，原始PDF未修改。

### 36.4 能证明、不能证明与停止点

能证明：这5条争议的正确关系是同级；此前失败由人工Golden误判造成，不是Parser路由、Parser字体层级、Locator或Chunker错误；纠正后R-02达到26/26真实标题正文路径并保持43/43非标题拒绝；相关合同与相邻数据库流程没有回归；正式数据库和Storage已恢复干净基线。

不能证明：R-03标题空壳评估漏洞已经修复；原18份文档、34条内容Golden和7组Chunk配置已在当前v2状态下正式重跑；至少一组配置已通过完整Chunk质量门禁；生产默认Chunk参数应该改变；M2-22.6或任何下游RAG能力已验证。

R-02至此完成并停止。下一动作只能是在用户理解并单独授权后实施R-03评估器防伪；R-03通过后才可由R-04运行正式18文档、34条内容Golden和7组矩阵。不得自动进入R-03、R-04、M2-22.6或任何后续功能。

## 37. M2-22.5R-03实施记录：标题质量门禁防伪与报告语义（2026-09-08）

### 37.1 本步目标、输入输出与调用链

用户在理解R-02已完成后明确授权开始下一步。本步只实施第28.4节R-03：修复“Chunk只带标题字符串或标题元数据也可能被计为标题保留”的评估漏洞，并纠正报告总门禁必须让所有实验配置同时通过的错误语义。不修改Parser、R04质量阈值、生产Chunk规则或默认Chunk参数，不运行R-04正式矩阵，也不进入M2-22.6。

输入是R04通过的Canonical Parser Artifact、Chunker v2产物、`m2-chunk-heading-golden-v2`的26条可信标题正文关系和现有34条内容Golden；输出是每文档/配置的严格标题保留计数、独立质量门禁及带标题数据身份的v2报告合同。调用链为：

```text
已有Parser Artifact
→ 已有Chunker v2：body_text + heading_path + source_spans
→ 本步严格标题质量评估
→ 每组配置独立门禁
→ 冻结候选总门禁语义
→ 报告v2
→ 停止
```

没有经过Embedding、pgvector、检索、Reranker、Context、Agent/LangGraph、Harness、Tool、Qwen、Ragas或前端。数据库集成只验证Parser/Chunk Service、Runner报告和精准清理。

### 37.2 实现与防伪规则

1. `app/evals/chunk_metrics.py`：`evaluate_chunk_document`接收版本化可信标题正文案例；对有人工Golden的文档，每条标题只有在同一个文本Chunk同时满足以下条件才计为保留：完整规范化`heading_path`精确相等、`body_text`包含Golden非标题正文、`retrieval_text`包含完整标题上下文、Parser Artifact声明页存在对应标题提示或Canonical结构标题、Chunk页码与source span确实覆盖正文原文、正文source slice不是标题本身且真实出现在`body_text`；
2. 原始`heading_hints`继续是Parser候选诊断，不再直接进入正式标题成功分母。没有人工标题Golden的文档只检查Canonical `block.heading_path`，并同样要求绑定真实、可定位的非标题正文；
3. `app/evals/rag_runner.py`：Runner固定加载标题Golden v2并传给每份文档/每组配置；报告升级为`m2-chunk-quality-report-v2`，新增标题数据版本、原始文件SHA-256和本次命中的可信案例数；
4. 每组首轮与重叠配置继续独立保留`quality_gate_passed`。报告总门禁不再要求所有比较实验同时通过，而是要求按冻结质量排序选出的候选中，至少一个重叠配置满足全部质量条件；失败配置和Bad Case不会被删除；
5. `tests/unit/test_rag_chunk_metrics.py`：新增正常绑定，以及标题空壳、只有文本没有元数据、伪造父子路径、错误正文source span、Parser标题来源缺失反例；
6. `tests/unit/test_m2_chunk_heading_golden.py`：既有4份真实问题PDF、26条关系除直接比较Chunker输出外，再逐条进入R-03严格评估函数；
7. `tests/unit/test_m2_rag_parser_runner.py`与`tests/integration/test_m2_rag_chunk_runner.py`：冻结“至少一个选定候选通过”的报告语义、v2数据身份，并在5文档真实Service Runner中让双栏文档的4条标题关系逐组通过。

本步没有改`app/services/documents/chunking/chunker.py`，因为R-02生产输出已经正确；也没有修改标题Golden、34条内容Golden或R04阈值。

### 37.3 TDD、专项、相邻和完整回归

1. 编码前先加入6个R-03用例，旧评估器得到`6 failed, 4 passed in 9.78s`，失败原因是旧函数不接受可信标题案例，也没有正文/Locator联合核验；
2. 实现后`tests/unit/test_rag_chunk_metrics.py`为`10 passed in 7.22s`；定向评估、报告、Golden与合同集合为`101 passed in 29.82s`；
3. 4份真实问题PDF测试为`6 passed in 26.67s`，其中26/26可信标题正文关系逐条通过R-03严格函数；
4. 禁止下游边界内完整允许单元回归为`371 passed, 2 skipped in 121.83s`，此前标题空壳失败已经转绿，没有新增Parser、Chunk、表格、OCR、Locator或确定性失败；
5. 真实Runner专项最终为`1 passed in 53.49s`：5份文档实际经过上传、Parser/R04、Chunk Service、4组首轮配置和候选重叠扫描；双栏标题Golden共4条，在每组配置均为4/4；
6. 相邻Parser Service、Chunk Service、两个Seed和Runner集成为`20 passed in 79.94s`；
7. 工程门禁全部通过：`ruff check app tests scripts migrations`、6个R-03相关文件格式检查、`mypy app`（156个源码文件）、`compileall -q app`、`pip check`和`git diff --check`。diff只有仓库现有LF/CRLF提示，没有空白错误。

### 37.4 数据清理与正式基线

Runner使用隔离评估身份和Storage范围，测试结束后评估数据库行、ChunkSet和Storage对象归零。全部数据库回归完成后再次运行`seed_m2_files`与`seed_m2_complex_files`，最终只读审计为10个File、10个Document、10个Version、9条ACL、10个pending版本、10个upload对象、0个正式ChunkSet、M1德国仓可售库存125，Parser和Chunk基线均`clean=True`。

本步没有生成或保留正式18文档报告；没有运行Ragas、Embedding或任何禁止下游。

### 37.5 能证明、不能证明与停止点

能证明：标题字符串、`heading_path`或Parser提示任意单项都不能制造通过；受审标题必须绑定同一Chunk中的真实非标题正文和正确Locator；伪造父子层级、缺失Parser来源及错误正文source span都会被拒绝；4份真实问题PDF的26条关系通过严格指标；Runner实际消费标题Golden v2并可审计其Hash；失败实验配置与候选总门禁语义已经分离；相关代码、相邻Service和正式基线没有回归。

不能证明：当前18份文档在7组正式配置下全部通过；34条内容Golden与Locator仍为34/34；正式标题总数和每组结果是什么；至少一个冻结候选已经通过完整门禁；最佳生产Chunk参数应该改变；M2-22.6或任何检索、重排、Context、回答与Agent能力已经验证。

R-03至此完成并停止。下一动作只能是在用户理解并单独授权后实施R-04：使用当前Parser/R04、Chunker v2、标题Golden v2和报告v2正式重跑18文档、34条内容Golden及7组矩阵，随后精准清理并如实报告。不得自动进入R-04、M2-22.6或任何后续功能。

## 38. M2-22.5R-04正式矩阵运行、质量受阻与清理（2026-09-09）

### 38.1 本步授权、输入输出与边界

用户明确授权进入M2-22.5R-04。本步没有新增生产能力，输入是已经通过R04的18份正式评估文档、34条内容Golden、Chunker v2、`m2-chunk-heading-golden-v2`的26条人工标题正文关系和`m2-chunk-quality-report-v2`评估器；输出是当前代码状态下的正式Chunk矩阵结果、失败归因、回归证据和清理后的正式基线。

实际调用链为：

```text
受控原文件
→ 公开上传/建文档API
→ DocumentParserService / Router / Native或Docling
→ Canonical Parser Artifact
→ R04质量门禁
→ DocumentChunkService / Chunker v2
→ Canonical Chunk Artifact（body_text + heading_path + retrieval_text + source_spans）
→ 项目确定性Chunk质量矩阵
→ 精准清理与正式基线复核
→ 停止
```

没有运行Embedding、pgvector、检索、Reranker、Context、Agent/LangGraph、Harness Tool、Qwen、Ragas或前端；没有修改生产默认Chunk参数、Parser、R04阈值、34条内容Golden或标题Golden，也没有进入M2-22.6。

### 38.2 正式运行与配置矩阵

运行前只读基线为10个File、10个Document、10个Version、9条ACL、10个pending版本、10个upload对象、0个ChunkSet、M1德国仓可售库存125，`clean=True`。Docker最初未启动导致数据库连接超时；启动仓库既有`deep-search-postgres`容器后重新检查，基线干净，再执行：

```powershell
.venv\Scripts\python.exe -m app.evals.rag_runner --stage chunk --enable-docling --output data\evals\runtime\reports\m2_cross_border_chunk_report_v2.json
```

Run ID为`m2-22.5-20260909t005309-682e5c2b`，UTC运行时间为`2026-09-09T00:53:09.678527Z`至`2026-09-09T01:06:14.664902Z`。运行状态为`completed`，18/18文档完成Parser并通过R04，34条内容Golden全部进入评估。`completed`只说明执行和清理成功，不等于质量门禁通过。

4组首轮实际结果：

| 配置 | 内容Golden | 标题 | 边界断裂 | 表格 | Chunk数 | Token min/p50/p95/max | 重叠冗余 |
|---|---:|---:|---:|---:|---:|---:|---:|
| `400/500/100` | 34/34 | 55/56 | 91/9750 | 45/45 | 779 | 6/388/399/482 | 24.54% |
| `500/600/100` | 34/34 | 55/56 | 90/9750 | 45/45 | 588 | 6/486/499/598 | 19.24% |
| `600/700/100` | 33/34 | 55/56 | 90/9750 | 45/45 | 482 | 6/586/598/667 | 15.90% |
| `700/850/100` | 34/34 | 55/56 | 90/9750 | 45/45 | 406 | 6/685/698/793 | 13.30% |

冻结候选选择策略在结构质量并列时同时保留`chunk-large`与`chunk-medium`，因此本次不是旧记录中的“4+3=7组”，而是4组首轮加2个候选各3个overlap，共10组完整配置；这是R-03已经冻结并由测试验证的候选语义，不是运行中临时改规则。6组overlap扫描中，除`chunk-large-overlap-080`为33/34外，其余5组均为34/34内容和Locator；所有6组均为55/56标题、90/9750边界、45/45表格、18/18顺序/Locator完整性/确定性和0空Chunk，因此全部总门禁False。

代表性`chunk-large-overlap-120`结果为：417个Chunk，Token min/p50/p95/max=`6/685/699/803`，重叠冗余率15.99%，1个近重复Chunk；34/34内容Golden和Locator、证据source span覆盖100%、45/45表格、18/18来源顺序、18/18 Locator完整性、18/18字节确定性、0空Chunk全部通过。DOCX页眉3/3、页脚3/3、图片OCR 1/1、图片前后文关系1/1也全部通过。近重复计数不是当前门禁失败项；实际门禁失败条件是标题未全保留和边界断裂不为0。

### 38.3 失败事实与定位

人工冻结的26条标题正文关系全部通过：双栏4/4、OSS 16/16、GPSR 5/5、Safety Gate 1/1。总体标题55/56中的唯一失败来自没有人工标题Golden的`m2-complex-v1-scanned-receiving-ticket`，其Canonical fallback为4/5。它不是此前用户裁决的同级标题争议，也不能据此改Golden。

总体段落为9598/9687，即89个单位被记为“不在正文”；边界再包含1个未通过的结构标题单位，共90/9750。11份失败PDF分别为：蘑菇灯手册6、扫描入库单1、双栏简报10、合并表头成本表1、VAT解释说明11、OSS指南27、低价值包裹19、退运5、GPSR 6、Safety Gate新闻稿2、Safety Gate通报2。

代码核对得到一个确定的评估合同冲突：

1. Chunker v2识别纯标题后会更新`heading_path`，并按已确认设计跳过纯标题，不让它进入`body_text`；
2. `_audit_structure`仍把Canonical PDF Block中的每一个非空行放入边界分母，并且只在Chunk的`body_text`里查找；
3. `ExcludedChunkSpan`目前只支持空白、重复页眉、重复页脚和噪声，没有“已提升为标题元数据”原因，也没有精确字符起止范围；纯标题以及多行合并标题被跳过时，Chunk Artifact没有保存这段来源审计；
4. 无人工Golden的Canonical fallback还按`source_block_ids`查正文绑定；纯标题独立成块并被抽离后，后续正文Chunk不会自然携带该标题Block ID，因此扫描入库单的1个标题无法由现有合同证明。

因此，当前结果**不能解释为89段正文真的被切坏**。它证明的是：标题抽离策略已经执行，但Chunk Artifact与边界评估没有同步表达“哪一段源文字被合法抽到元数据、绑定给了哪个正文Chunk”。失败位于Chunk Artifact/评估审计合同交界，不是Parser原文恢复、正文Locator、表格、overlap、顺序或确定性；也没有证据要求修改R04阈值。

建议的最小后续修复是M2-22.5R-04A：让Chunker对每个实际提升的标题输出可审计的精确源范围（至少Block、字符起止、页/坐标、标题层级以及所绑定正文Chunk），并纳入Chunk Hash/版本；边界评估只能排除这些真实、可定位、已绑定的标题范围，不能按字符串或所有`heading_hints`宽松忽略；同时用该绑定复核扫描入库单的1个Canonical fallback。该修复必须先写RED反例，再重跑同一正式矩阵。当前未获该代码修改授权，所以本步没有实施。

### 38.4 专项、相邻、完整回归与清理

1. R-04正式Runner：`run_status=completed documents=18 golden=34 quality_gate_passed=False`；这是本步必须保留的真实质量失败；
2. 专项评估/标题/报告合同：`101 passed in 22.85s`；
3. 相邻Parser Service、Chunk Service、两个Seed与5文档Runner集成：`20 passed in 63.69s`；
4. 禁止下游边界内完整Parser/Artifact/Router/Chunk/Evaluation单元回归：`367 passed, 2 skipped in 89.24s`；
5. 首次用文件路径直跑`seed_m2_files.py`因模块搜索路径报`ModuleNotFoundError: app`，在导入阶段退出、没有数据库写入；改用正式模块入口后，`python -m scripts.seed_m2_files`与`python -m scripts.seed_m2_complex_files`均成功；
6. 最终独立只读审计再次得到10 files / 10 documents / 10 versions / 9 ACL / 10 pending / 10 uploads / 0 ChunkSet / M1库存125 / `clean=True`；Runner报告内也记录评估数据库行0、评估ChunkSet 0、评估Storage对象0与`baseline_restored=True`；
7. 临时报告大小713,628字节，SHA-256为`ecf16a31fe77ad1dfc39413b7a9bc3bd8ea2a37644be50dd879c1da1fc425fbd`。必要汇总进入本记录后按用户要求删除；原始18份输入文件和正式10份Seed对象未删除或覆盖。

本步只修改三份进度文档：本文保存完整命令、结果、归因与停止点；`docs/progress/M2/M2_KNOWLEDGE_RAG.md`保存M2当前状态、风险和验证基线；`docs/PROJECT_PROGRESS.md`保存项目级状态与下一动作。没有生产代码、测试、Schema、迁移、Golden或配置变更。

### 38.5 能证明、不能证明与停止点

能证明：当前Parser/R04可处理18/18文档；至少多个候选达到34/34内容Golden与真实Locator；人工标题关系26/26；表格、DOCX视觉文字及前后文、Token硬上限、顺序、Locator完整性和重复构建确定性没有回归；评估器没有因为内容成功而掩盖标题/边界失败；失败已定位到标题元数据来源审计和边界分母合同；专项、相邻和完整允许回归通过；评估数据库与Storage已清理，正式基线恢复。

不能证明：当前Chunk总质量门禁通过；90个边界失败已经逐条由新版来源记录证明为合法标题排除；扫描入库单第5个Canonical标题已绑定；`700/850/120`应成为生产默认值；近重复Chunk在更大语料上没有影响；Embedding、pgvector、检索、Reranker、Context、回答、Agent、Qwen、Ragas、前端或M2-22.6已经验证。

R-04运行与清理已经完成，但质量验收受阻，M2-22.5R不能标记完成。当前停止并等待用户理解及单独授权R-04A最小修复；不得自动修改Chunk Artifact/Chunker/评估器，不得更新生产默认参数，不得进入M2-22.6或任何后续步骤。

## 39. M2-22.5R-04A实施记录：标题来源审计、版面边界校准与正式收口（2026-09-09）

### 39.1 用户授权、缺口、输入输出与边界

用户在确认“标题已经按要求从`body_text`抽到元数据，而旧评价仍要求标题出现在正文”后，明确授权先修改并进入R-04A。本步只修复M2-22.5的Chunk Artifact、Chunker与质量评价合同，不修改34条内容Golden、标题Golden、R04解析质量阈值或生产默认Chunk参数，也不实现M2-22.6。

本步输入是18份已经通过R04的Canonical Parser Artifact、其中PDF的真实Block/字符范围/页码/`pdf_layout_lines`/bbox、DOCX结构来源、34条内容Golden和标题Golden v2；输出是`m2-structure-aware-chunker-v3` Chunk Artifact、标题精确来源审计、与真实版面一致的边界统计，以及重跑后的正式质量矩阵。

实际调用链为：

```text
受控原文件
→ 公开上传/建文档API
→ DocumentParserService / Router / Native或Docling
→ Canonical Parser Artifact
→ R04解析质量门禁
→ DocumentChunkService / Chunker v3
→ Canonical Chunk Artifact
   ├─ body_text：只放正文
   ├─ heading_path：用于检索的标题路径
   ├─ heading_sources：标题的Block/字符起止/页码/bbox来源
   └─ excluded_spans：标题、重复页眉页脚或噪声的精确审计
→ 项目确定性Chunk质量矩阵
→ 精准清理与正式基线复核
→ 停止
```

没有运行Ragas、Embedding、pgvector、检索、Reranker、Context、Agent/LangGraph、Qwen或前端；相邻回归没有启动这些下游能力。本步没有新增迁移或数据库字段。

### 39.2 实现、严格评价规则与防伪边界

1. Chunker版本升为`m2-structure-aware-chunker-v3`。每个真实提升到`heading_path`的标题可带`ChunkHeadingSource`，记录路径下标、规范化标题、真实源文字，以及Block、字符起止、页码、bbox；来源进入Chunk内容Hash。空列表在序列化时省略，历史v1/v2 Artifact继续可读；
2. 标题原文不回填`body_text`。Chunker另外写入`reason=heading_metadata`的精确`ExcludedChunkSpan`；重复页眉/页脚、噪声和被主标题吸收的masthead也保存真实字符范围。表格Chunk重编号保留标题来源；
3. 标题质量和正文边界继续分开：56个结构标题要通过标题门禁，仍必须有真实Parser声明、正确路径、真实非标题正文、检索视图、Locator和精确来源；仅写一个标题字符串或伪造路径仍不能通过；
4. 正文边界不再要求标题重复出现在`body_text`。只有`heading_metadata`的Block、字符范围、Locator、源切片与Parser标题声明全部一致时，该范围才从正文分母排除。封面连续标题或图示标签即使没有可绑定正文，也必须以精确Chunk Artifact元数据证明后才可排除，不能仅凭字符串或所有`heading_hints`宽松忽略；
5. PDF正文审计不再把文本层横向拼接的整行当作唯一段落单位。若Parser提供行级Locator，评价按与Chunker一致的“有真实offset的物理layout line + 行内未覆盖残段”逐项检查；没有layout信息的旧Artifact仍回退到原行审计。这样双栏左右正文和复杂表格单元可以进入不同Chunk，但每个真实来源片段仍必须被找到；
6. 修复一个真实Chunk审计遗漏：全大写masthead被后续多行主标题吸收时，旧判断把它留在`consumed`集合却因仍遍历自身匹配而没有写`noise`。现在只用未消费的保留标题判断覆盖，真实masthead会得到精确噪声记录；组合标题的第二行不会被重复排除；
7. 编号标题审计使用与Chunker相同的确定性编号前缀剥离规则，例如Parser提示`2. IOSS适用范围`仍可证明规范化标题`IOSS适用范围`，没有把业务词或Golden硬编码进规则。

这不是把门禁调松。标题路径质量仍要求标题与正文绑定；正文边界只是不再要求标题同时存在于正文。双栏/表格改用Parser已有的真实物理行和坐标，未删除任何正文检查，也没有修改`boundary_breaks == 0`的正式门禁。

### 39.3 TDD、首轮正式失败与逐条归因

编码前的4个RED分别在“Chunk没有`heading_sources`”“正确抽离标题仍被算作正文缺失”“删除标题来源绑定后标题质量仍通过”等预期位置失败。加入v3合同和首轮评价实现后，定向4项转绿；标题来源还增加了路径下标唯一、正文Chunk限定、精确字符范围、源切片、Locator、排除记录和Hash篡改反例。

首轮R-04A正式运行Run ID为`m2-22.5-20260909t021722-f63212c3`，执行和清理成功，但质量门禁仍为False。它已经把标题从55/56修到56/56，并把边界误报从90降到41；34条内容Golden的候选表现保持不变，正式基线也恢复。因为41不等于0，本步没有在此冒充通过。

随后对41条逐一打印原Block、页码、字符范围、Parser提示、layout line、标题来源、Chunk正文和排除记录，得到三类确定事实：

- 22条来自双栏或复杂表格。PDF文本层把不同横坐标内容拼成一行，而Chunker按真实bbox拆到多个Chunk，所有物理文字行实际都存在；
- 18条是封面连续标题或图示标签，均已有Parser声明和精确`heading_metadata`范围，但没有独立正文可绑定；它们不应进入`body_text`分母；
- 1条`CONSUMER PROTECTION`是masthead的真实审计漏记，既没有正文也没有排除元数据，定位并修复于Chunk规则。

修正后只重跑上述6份Native PDF做离线逐条复核，六份均为`MISSING 0`；临时诊断脚本随后删除，没有成为交付物或留下评估数据。

### 39.4 最终18文档、34 Golden与13组正式矩阵

最终在干净正式基线上执行：

```powershell
.venv\Scripts\python.exe -m app.evals.rag_runner --stage chunk --enable-docling --output data\evals\runtime\reports\m2_cross_border_chunk_report_v2.json
```

Run ID为`m2-22.5-20260909t032311-651ab937`，UTC运行时间为`2026-09-09T03:23:11.474046Z`至`2026-09-09T03:45:39.461101Z`。18/18文档完成真实上传、Parser与R04，路由为Native 16、Docling 1、Hybrid 1；34条内容Golden全部进入评估，最终`run_status=completed`且`quality_gate_passed=True`。

四组首轮结果为：

| 配置 | 内容Golden/Locator | 标题 | 边界断裂 | 表格 | Chunk数 | Token min/p50/p95/max | 重叠冗余 |
|---|---:|---:|---:|---:|---:|---:|---:|
| `400/500/100` | 34/34 | 56/56 | 0/11809 | 45/45 | 779 | 6/388/399/482 | 24.54% |
| `500/600/100` | 34/34 | 56/56 | 0/11809 | 45/45 | 588 | 6/486/499/598 | 19.24% |
| `600/700/100` | 33/34 | 56/56 | 0/11809 | 45/45 | 482 | 6/586/598/667 | 15.90% |
| `700/850/100` | 34/34 | 56/56 | 0/11809 | 45/45 | 406 | 6/685/698/793 | 13.30% |

物理layout line与残段成为正确审计单位后，边界分母由旧文本层拼接行口径的9750变为11809；不能把它描述成简单删除90项。新分母逐项覆盖了拆开的双栏和表格来源，结果为0个断裂。

首轮结构质量并列，冻结选择策略得到`chunk-compact/chunk-large/chunk-medium`三个候选，因此最终是4组首轮加3个候选各3组overlap，共13组，不是运行中临时增加。9组overlap结果为：

| 配置 | 内容Golden/Locator | Chunk数 | 重叠冗余 |
|---|---:|---:|---:|
| compact / 80 | 34/34 | 733 | 19.58% |
| compact / 100 | 34/34 | 779 | 24.54% |
| compact / 120 | 34/34 | 832 | 29.51% |
| large / 80 | 33/34 | 397 | 10.66% |
| large / 100 | 34/34 | 406 | 13.30% |
| large / 120 | 34/34 | 417 | 15.99% |
| medium / 80 | 34/34 | 563 | 15.35% |
| medium / 100 | 34/34 | 588 | 19.24% |
| medium / 120 | 34/34 | 617 | 23.19% |

9组均为56/56标题、0/11809边界断裂、45/45表格、18/18顺序、18/18 Locator完整性、18/18重复构建确定性和0空Chunk。代表性`large/120`另为证据source span覆盖100%、DOCX页眉3/3、页脚3/3、图片OCR 1/1、图片前后文1/1、Token `6/685/699/803`，有1个近重复Chunk。数字只用于矩阵比较；本步没有选择或修改生产默认参数。

### 39.5 专项、相邻、完整回归、工程门禁与清理

1. R-04A关键定向4项为`4 passed`；最终Chunk合同、文本Chunk、指标、报告合同和真实标题Golden专项为`123 passed in 24.29s`；
2. Parser Service、Chunk Service、5文档Runner与两个Seed相邻PostgreSQL集成为`20 passed in 70.96s`；
3. 禁止下游边界内的完整Parser/Artifact/Router/Chunk/Evaluation/Storage单元范围收集387项，结果为`385 passed, 2 skipped in 83.64s`，没有失败；
4. `ruff check app tests scripts migrations`通过；11个本步代码/测试文件格式正确；`mypy app`为156个源码文件通过；`compileall -q app`、`pip check`和`git diff --check`通过。diff只有现有Git换行提示，没有空白错误；
5. 正式报告内记录评估数据库行0、评估ChunkSet 0、评估Storage对象0、`baseline_restored=True`。相邻数据库测试会重置M2表，因此测试后再次运行两个既有Seed入口；最终独立只读审计为10 files / 10 documents / 10 versions / 9 ACL / 10 pending / 10 uploads / 0 ChunkSet / M1库存125 / `clean=True`；
6. 临时正式报告为940,807字节，SHA-256 `857040c692640d286b364589f0963b0eaea7e1b21affaac2ef24cfd28259dd1a`。必要结果进入本记录后按用户要求删除；18份原始评估文档与正式10份Seed对象未删除或覆盖。

### 39.6 能证明、不能证明、风险与停止点

能证明：当前18份固定文档能通过R04并进入真实Chunk Service；Chunker v3在正文不重复标题的前提下可审计标题原文、路径、Block、精确字符范围、页码和bbox；标题56/56、34条内容与Locator在多个候选中34/34、边界0/11809、表格45/45、DOCX视觉来源与前后文、顺序、Locator和确定性均通过；伪造标题字符串、错误路径、错误源切片或缺失排除记录仍不能制造标题质量通过；正式评估数据已清理并恢复基线。

不能证明：`600/700/100`当前生产默认值是最佳选择；近重复Chunk在更大语料没有影响；任意未来PDF的复杂版面、标题或OCR都一定正确；Embedding、pgvector、检索、Reranker、Context、回答、权限、Citation、Agent、Qwen、Ragas、前端或M2-22.6已经验证。本步尤其不能用Chunk Golden包含率替代后续真实检索指标。

M2-22.5及其R-04A至此完成。当前停止并等待用户理解及单独授权M2-22.6；不得自动安装或运行Ragas，也不得自动进入Embedding、pgvector、检索、Reranker、Context、Agent、Qwen、前端或任何后续步骤。

