# M2-22.6｜检索矩阵与Ragas记录

> 以下第40至42节从原M2-22总记录按连续区间原样迁入，保留正式指标、失败样本和外部Judge边界。

## 40. M2-22.6实施记录：检索评估器完成、真实矩阵受DOCX公开Locator阻塞（2026-09-09）

### 40.1 授权、缺口与本步边界

用户正式授权只实施M2-22.6。M2-22.5已经证明18份文档经过Parser/R04后，冻结候选中的正确原文能够进入Chunk并保留来源；它没有证明查询向量、PostgreSQL FTS或RRF能把正确Chunk排进TopK，也没有验证相似产品、无答案题、ACL/软删除/active版本或排名稳定性。

本步输入固定为既有18份文档、40条Debug Smoke、其中34条可回答Golden Evidence、M2-22.5筛出的9组`compact/medium/large × overlap 80/100/120`和当前生产`600/700/100`基线；候选深度固定10/20/30，先在RRF=60下筛候选深度，再只对所选深度比较RRF 20/60/100，不做无界笛卡尔积。目标输出是Dense、Lexical、Hybrid完整有序候选及其排名/分数/Locator，确定性指标、Ragas检索语义指标、分组延迟/过滤/稳定性和Bad Case报告。

允许调用链为：

```text
18份冻结文档
→ 上传/登记API
→ Parser / R04
→ Chunker v3（只用评估配置覆盖）
→ Index Service
→ 本地BGE-M3 DOCUMENT/QUERY Embedding
→ PostgreSQL FTS + pgvector（排序前共用tenant/ACL/软删除/active代次过滤）
→ Dense / Lexical
→ RRF Hybrid
→ 项目确定性排名指标 + Ragas检索语义指标
→ 分层安全报告
→ 精确清理、正式Seed与M1基线复核
```

没有实现或运行BGE-Reranker、Context/Evidence、Knowledge Tool、Harness、Agent/LangGraph、Supervisor/Worker、项目Qwen回答、Citation、自动路由或前端；没有修改生产SQL、数据库结构、Golden、生产Chunk参数或生产TopK/RRF默认值，也没有进入M2-22.7。

### 40.2 已实现的M2-22.6能力

1. `app/evals/retrieval_metrics.py`实现项目确定性指标：Precision/Recall/Hit Rate `@1/@3/@5/@8/@10/@20`、MRR@10、nDCG@5/@10、首个正确Evidence排名、Evidence单位去重Recall、相似产品串答和无答案误召回；
2. `app/evals/retrieval_report.py`冻结安全报告合同。每条路由保存完整有序候选的Chunk/Document/Version/Index Set ID、排名、Dense/Lexical/RRF分数、逻辑来源、Locator、正文Hash和匹配Evidence ID，不保存正文、向量、tenant、密钥或Judge思维链；确定性结果与Ragas结果分栏；
3. `app/evals/ragas_retrieval.py`固定`ragas==0.4.3`，按该版本真实API适配`ContextPrecisionWithReference`、`ContextRecall`、`ContextRelevance`和`NoiseSensitivity`。只有前三项能在纯检索输入中运行；`NoiseSensitivity`在该版本要求`response`，M2-22.6禁止生成回答，所以必须记录`skipped/input_invalid`而不是伪造0分。异常、网络、超时和Judge失败均无数值；
4. Judge身份固定记录Provider、模型、API别名版本、温度、top-p、最大输出、seed、30秒超时、2次尝试、Prompt实现包Hash和状态，不保存思维链。最小真实探针得到Context Precision约1.0、Context Recall 1.0、Context Relevance 1.0；Noise Sensitivity按上述合同显式跳过。该探针只调用Ragas Judge，没有启动项目最终回答链；
5. `app/evals/retrieval_runner.py`实现18文档真实摄取、冻结Chunk矩阵、BGE精确文本内存缓存、预编码以区分Embedding失败与Index持久化失败、Dense/Lexical真实Service、RRF融合、四类报告分组、顺序筛选、完整Trace、过滤审计、稳定复跑和失败时精确清理；
6. `scripts/run_m2_retrieval_evaluation.py`提供正式模块入口。BGE固定本地revision与离线模型；批量大小16和数据库语句超时30秒只作用于评估Settings副本，并同时记录生产默认批量4、SQL超时2秒和已观测超时，未修改生产默认值；`--config-id/--case-id/--no-ragas`只用于有界诊断；
7. 新增确定性指标、Ragas适配、Runner合同和真实PostgreSQL/pgvector集成测试。集成测试使用Fake Embedding隔离模型质量，但真实执行FTS、vector距离、RRF、ACL/软删除、active代次、稳定复跑及清理；正式Runner另使用真实BGE。

依赖管理沿用`requirements-dev.txt`的开发评估边界，固定新增`ragas==0.4.3`及其当前导入所需的`langchain-community==0.4.1`；没有安装DeepEval。安装前核对了现有venv、依赖文件、模型缓存和磁盘，包安装后`pip show`与`pip check`确认确切版本且无破损依赖。Ragas 0.4.3实际指标模块组成的Prompt实现包SHA-256为`fc347923599df1a73f285372856a462e4ebbdf5a3e7bffdc40fc5a7332323845`。

### 40.3 RED/GREEN与评估器验证

初始RED分别证明项目不存在检索排名指标、Ragas检索适配和M2-22.6 Runner；加入最小实现后，确定性指标和Ragas适配单元逐步达到11项通过，Runner合同达到3项通过。真实集成首先证明PostgreSQL FTS、pgvector、RRF和清理闭环；随后加入无答案软删除样本与Dense安全错误诊断。

正式失败暴露后又增加一条RED：评估器必须保留首个无法映射的Chunk ID和原始校验原因，不能只记录生产安全错误`检索暂时无法完成`。RED在缺少诊断类型/函数处导入失败；GREEN后Runner单元4项通过。稳定性复跑分支第一次漏传新增的`case_id`，同组专项表现为`12 passed, 1 failed`；只补传参数后复跑为`13 passed in 25.44s`。

当前静态工程门禁结果：9个M2-22.6代码/测试文件Ruff format通过；Ruff lint通过；4个评估源码Mypy通过；`compileall`通过；`pip check`无破损依赖；`git diff --check`通过。完整相邻和截至Retrieval层的允许回归尚未运行，因为正式矩阵在第一组第一题已命中必须另行授权的生产数据合同缺口；不得把专项通过冒充本步完整验收。

### 40.4 真实运行、逐层诊断与确定阻塞

真实运行过程中已分开验证以下故障：

1. 首次从标准输入启动模块触发Windows多进程`<stdin>`入口失败，属于Runner启动方式；改用`python -m scripts.run_m2_retrieval_evaluation`后解除；
2. BGE批量32在本机长文档运行不稳定；只把评估吞吐批量降为16，生产默认仍为4；
3. 第一版Evidence映射把无答案题当成可回答题，定位为评估器Golden/Evidence映射并修正；没有改Golden；
4. `eu-vat-explanatory-notes-2026-en`在`compact/80`下产生292个Chunk。BGE已成功返回向量，但Index持久化在生产默认2秒SQL超时下失败；同一数据、同一Chunk与Fake向量在评估30秒超时下成功，索引阶段约43.2秒。因此这是Index/PostgreSQL持久化边界，不是BGE失败，也不构成修改生产超时或选择compact为生产默认的证据；
5. 纠正以上评估器问题后，完整正式运行真实解析18/18文档、预编码40/40查询，并在第一组`chunk-compact-overlap-080`完成18份文档的Chunk、BGE和Index。首题`smoke-syn-001-voltage`执行Dense@10时，pgvector已经返回有序候选，但第4名Chunk `179ca26a-1e5b-5ed5-a1c5-08e6efd02c30`无法构造公开`DocxRetrievalSourceLocator`：页码、段落号、表格号和标题路径全部为空；生产Dense Service因此在结果映射层转换为安全`RetrievalInternalError`；
6. 单题、同候选、全18文档的干净复现得到相同故障形状和具体Chunk，排除旧数据残留。结合当前代码可定位最早缺口：`m2-complex-v1-visual-quality-notice`是本批唯一包含R-03 DOCX页眉/页脚来源的文档；`_adapt_docx_region`把Section/region信息存入`docx_source`，但其通用`SourceLocator`为空；Chunker v3按设计原样保存该Parser来源，M2-22.5的Locator完整性只验证“Chunk与Parser一致”，没有验证“所有Chunk都能形成公开Retrieval Locator”；Dense结果映射又没有读取`docx_source`或`source_block_ids`。因此首个错误层归为**Parser Artifact的DOCX region公开坐标缺口，暴露于Dense结果映射**，不是pgvector Dense召回质量、FTS、ACL、RRF、Ragas或Judge。

这个错误不能通过删除第4名、只评Top3、扩大TopK或从候选中排除页眉/页脚掩盖。继续正式矩阵需要修改生产来源映射或上游Parser/Chunk坐标，超出本次仅允许评估器改动的边界，故按用户要求立即停止。没有生成任何候选质量分数，也没有运行Ragas正式40题评分；所有10组Chunk、三档深度和三档RRF指标均为**未完成/不可报告**，不是0分。

### 40.5 建议的最小修复方案（未实施，等待单独授权）

推荐单独授权`M2-22.6R-01 DOCX region Retrieval Locator修复`，只解决这一阻塞，不进入M2-22.7：

1. 先为DOCX页眉/页脚Chunk分别写Dense与Lexical RED，证明当前公开结果映射失败；再加伪造/非法Block ID反例；
2. 不改数据库结构、排序SQL、过滤条件、TopK/RRF、Golden或Chunk边界。让Dense/Lexical候选记录带上数据库中已经存在的`source_block_ids`，当DOCX `start_locator`没有任何公开坐标时，只允许把第一个格式合法且属于该Chunk的Canonical `bNNNNNN`转换为公开`block_number`；原有段落号、表格号、页码和标题路径优先级不变；
3. 预计只修改`app/repositories/retrieval.py`与`app/services/retrieval/result_mapping.py`，并补Dense/Lexical/Hybrid和权限前置集成测试。因为共享Mapper也被Context读取，修复验证必须确保只改变Locator坐标，不运行或构造Context；
4. 修复后先复跑单题真实BGE阻塞样本；通过后再从干净基线完整重跑本M2-22.6矩阵、Ragas检索指标、专项/相邻/完整允许回归和最终清理。评分仍不得自动改生产默认值。

若用户不接受Canonical Block作为公开DOCX坐标，则备选方案是给Parser Artifact的DOCX region Locator增加稳定Section/region坐标并升级Artifact/适配版本，但这会扩大到Parser重验，成本和影响明显更大，不是推荐的最小修复。

### 40.6 清理、能证明与停止点

失败Runner的`finally`已清除隔离租户、用户、文档、版本、ACL、ChunkSet、IndexSet、Chunk行、向量、Storage上传与Parser/Chunk对象，并清空进程内Embedding缓存。随后重新运行既有`seed_m2_files`与`seed_m2_complex_files`；独立只读审计为10 files、10 documents、10 versions、9 ACL、10 pending版本、10 upload对象、0 ChunkSet、0 IndexSet、0 Chunk、M1德国仓可售库存125、`clean=True`，残留M2-22.6评估租户为0。三个早期诊断报告目录和`dependency-audit`临时目录已按核对后的绝对路径删除；18份受控原文、既有正式Parser/Chunk报告和模型缓存保留。

能证明：M2-22.6评估器合同、确定性算法、Ragas 0.4.3适配、真实FTS/pgvector/RRF集成与清理路径已经实现；Ragas前三个纯检索指标能用固定Judge运行，Noise Sensitivity在禁止回答的边界内必须显式跳过；真实BGE与Index已到达第一组全18文档；生产2秒索引边界和DOCX region公开Locator缺口均已分层定位。

不能证明：任何候选配置、候选深度或RRF常数的完整质量优劣；40题Ragas语义表现；四类分组的Precision/Recall/Hit/MRR/nDCG/延迟；全部ACL/版本过滤和排名稳定性在18文档正式集上通过；生产默认值应当修改；M2-22.6已完成；以及Reranker、Context、Evidence、回答、Citation、Agent或M2-22.7任何能力。

第40节当时的M2-22.6状态为`受阻`而非`已完成`；该Locator修复随后已获用户确认并按第41节完成。历史失败证据保留，但当前停止点以第41节为准。

## 41. M2-22.6R-01与确定性检索矩阵（2026-09-09）

### 41.1 用户决定、RED与最小修复

用户确认采用第40.5节首选方案，并补充要求：缺精确坐标时降级展示；若Canonical Block也损坏，单个候选不能拖垮整个请求，但必须显式记录映射失败并让质量门禁失败，不能静默删除后把后续候选名次前移。该授权只解除M2-22.6的Locator阻塞，不授权Reranker、Context/Evidence、回答、Citation、Agent或M2-22.7。

先写RED并得到预期失败：Repository候选没有`source_block_ids`；公开响应不能表达单候选映射失败和原始排名空洞；Dense/Lexical仍会因一个无Locator候选全局报错。GREEN实现遵守以下顺序：

1. 既有页码、页集合、段落号、表格号、标题路径和原有Block坐标继续优先；
2. 只有DOCX候选的上述公开坐标全部为空时，才检查第一个`source_block_ids`；它必须精确匹配`b[0-9]{6}`、数值大于0，并与首个source span的`block_id`相同，随后才转换为公开`block_number`；
3. 若该校验失败，只捕获专门的Locator映射异常，记录`source_mode + 原始rank + chunk_id + source_locator_mapping + invalid_source_locator`。其他类型/校验错误仍走全局安全错误，避免把任意程序缺陷吞成“降级”；
4. Dense/Lexical结果允许由`results + candidate_failures`共同组成连续原始排名。例如第2名失败时公开结果排名为`1,3`，不会把第3名改成第2名；RRF继续使用route score内的原始排名，因此不会因坏候选获得虚假加分；
5. 每个实验的`candidate_mapping_quality_gate_passed`要求所有路由零映射失败；总`integrity_quality_gate_passed`还要求ACL、软删除、inactive Index Set、tenant和稳定性审计全部通过。Trace同时保存安全失败记录，指标计算为失败名次插入不相关占位，不会静默改善Precision、Recall、MRR或nDCG。

没有按“页眉/页脚”过滤候选。当前公开Retrieval Locator的`source_type`是`docx`而不是`header/footer`，region事实位于Parser的`docx_source`；更重要的是冻结题`smoke-syn-015-visual-control`确实询问页眉控制码`QC-VISUAL-17`，过滤会直接删除正确Evidence并改变真实排序问题。

修改文件与职责：

- `app/repositories/retrieval.py`：只把已有Chunk `source_block_ids`带入Dense/Lexical候选记录；排序SQL和过滤SQL未改；
- `app/services/retrieval/result_mapping.py`：实现精确坐标优先、Canonical Block兜底以及专用Locator映射异常；
- `app/services/retrieval/dense.py`、`lexical.py`：逐候选映射，只隔离专用Locator失败并保留原始排名；
- `app/services/retrieval/hybrid.py`：接受有明确失败记录的route排名空洞，按原始Dense/Lexical rank计算RRF并向报告传递失败；
- `app/schemas/retrieval.py`：新增公开安全的候选失败合同，并验证结果与失败必须覆盖完整原始route排名；
- `app/evals/retrieval_report.py`、`retrieval_runner.py`：Trace、指标占位、实验/总质量门禁和Bad Case接通映射失败；Hybrid只有在至少一个上游route已经把正确Evidence送入Top8、融合后却丢失时才归因RRF，两路都漏召回时不再重复误报为RRF；
- `tests/unit/test_dense_retrieval.py`、`test_lexical_retrieval.py`、`test_retrieval_contracts.py`、`test_rrf.py`、`test_m2_retrieval_runner.py`及相邻集成夹具：覆盖真实Block降级、坏Block隔离、排名不前移、RRF原始rank和质量门禁。

### 41.2 真实阻塞样本与正式运行

最小真实复现Run `m2-22.6-20260909t093211-34c9503d`使用全18文档、`chunk-compact-overlap-080`和单题`smoke-syn-001-voltage`，真实经过上传/登记、Parser/R04、Chunker v3、Index Service、本地BGE-M3、PostgreSQL FTS/pgvector、Dense/Lexical与RRF。733个Chunk和5个有界实验点全部完成；原先导致全局报错的Dense第4名仍是同一Chunk、相似度`0.5581355`、最终rank 4，公开Locator降级为`Docx block_number=1`，没有页码，也没有被过滤或重排。全部Trace映射失败0、完整性门禁True，清理与基线恢复True。临时摘要133,226字节，SHA-256 `a63964c9e775ce38b8b826015f1e966a03ddeaaa5c280030ed6eefef011caaed`。

正式Run `m2-22.6-20260909t095558-22ee87ce`从干净基线完成18份文档、40条查询、10组冻结Chunk配置、10/20/30三档候选深度以及每组所选深度上的RRF 20/60/100；实际只运行30个深度点加20个额外RRF点，不是10×3×3无界笛卡尔积。总计180个Index Set、50份JSONL Trace、2,000个case-experiment、6,000条Dense/Lexical/Hybrid有序列表、106,518个候选，候选映射失败0。运行约2小时59分；摘要7,693,041字节、SHA-256 `446d0a12d4c5f21d1c573ac91c58c0e88a6085f74b01b95fc72c3885d292a112`，50份Trace共81,199,038字节，每份Hash另由摘要记录。Trace保存全部候选的Chunk/Document/Version/Index Set ID、原始排名、Dense/Lexical/RRF分数、逻辑来源、公开Locator、正文Hash和匹配Evidence ID，不只保存最终TopK，也不保存正文、向量、tenant、密钥或Judge思维链。

固定身份：来源`m2-cross-border-sources-v1` / `f0b6c492603a91a9b9eb220ec96a060150b1396a79274f0e5357cacd6680b6c7`；数据集`m2-cross-border-rag-smoke-v1` / `1d22afa22c5752463189827dba86502f8bc1d06ab7d70403cb0af463c5c4c46b`；Embedding `BAAI/bge-m3@5617a9f61b028005a4858fdac845db406aefb181`、评估批量16。查询Embedding 40次的p50/p95/max为`335/406/23149 ms`。生产SQL超时仍为2,000 ms，评估副本为30,000 ms；已观测`compact/80`长VAT文档在生产边界超时，未修改生产设置。

### 41.3 候选深度筛选真实结果

下表使用不能被合成题稀释的`real_cross_border` 14条可回答题、Hybrid route；每格依次为深度10/20/30，RRF固定60。参数为`target/max/overlap`。`miss`是该深度完整候选列表内完全没有正确Evidence的题数，不是`1-Hit@8`。

| Chunk配置 | 参数 | Chunk数 | Index ms | Hit/Recall@8 | MRR@10 | nDCG@10 | miss |
|---|---:|---:|---:|---|---|---|---|
| compact/080 | 400/500/80 | 733 | 1,138,944 | .7857/.7857/.7143 | .3935/.3897/.3775 | .4879/.4986/.4727 | 3/1/1 |
| compact/100 | 400/500/100 | 779 | 1,011,817 | .8571/.7143/.7143 | .4817/.4628/.4513 | .5692/.5528/.5276 | 2/2/2 |
| compact/120 | 400/500/120 | 832 | 1,105,898 | .7143/.5714/.5714 | .4477/.4347/.4340 | .5097/.4977/.4824 | 4/1/1 |
| medium/080 | 500/600/80 | 563 | 942,184 | .7143/.6429/.5714 | .4101/.3852/.3673 | .4831/.4465/.4157 | 3/3/2 |
| medium/100 | 500/600/100 | 588 | 921,936 | .7143/.6429/.5714 | .3757/.3690/.3579 | .4571/.4508/.4263 | 3/2/1 |
| medium/120 | 500/600/120 | 617 | 983,571 | .5714/.5714/.5000 | .3774/.3257/.3234 | .4249/.3854/.3830 | 5/2/1 |
| large/080 | 700/850/80 | 397 | 961,757 | .7143/.7143/.6429 | .4294/.4223/.4333 | .5138/.5070/.5162 | 3/2/1 |
| large/100 | 700/850/100 | 406 | 929,847 | .6429/.6429/.5714 | .4060/.3966/.4008 | .4791/.4705/.4594 | 4/2/0 |
| large/120 | 700/850/120 | 417 | 1,063,132 | .5714/.5714/.5714 | .3571/.3452/.3494 | .4116/.4160/.4190 | 3/2/0 |
| current | 600/700/100 | 482 | 1,053,554 | .6429/.5000/.5714 | .4018/.3889/.3899 | .4595/.4331/.4341 | 5/3/3 |

每组都按冻结选择器选深度10。原因不是“更大TopK一定更差”，而是Hybrid输出由两条更深候选列表重新融合，额外候选会改变前8排序；本步不得扩大TopK掩盖上游失败。`compact/100 depth 10`在真实组Hit/Recall@8、MRR@10和nDCG@10均为本轮最高，因此成为后续RRF筛选与全局候选。生产基线的真实配置是`current depth 30/RRF 60`：真实组Hybrid Hit@8 `.5714`、MRR@10 `.3899`、nDCG@10 `.4341`；它保留作为对照，没有被修改。

### 41.4 RRF常数与所选候选的完整指标

每个Chunk配置只在其已选深度10比较RRF 20/60/100。十组配置的三种RRF常数均产生完全相同的Hybrid候选顺序和所有确定性排名指标；只有RRF数值本身和亚毫秒级融合计时不同。因此没有质量证据证明20或100优于当前60，最终候选保持RRF 60。各配置的`real_cross_border`三常数共同结果如下：

| Chunk配置 | RRF 20/60/100 Hit/Recall@8 | MRR@10 | nDCG@10 |
|---|---:|---:|---:|
| compact/080 | .7857/.7857/.7857 | .3935/.3935/.3935 | .4879/.4879/.4879 |
| compact/100 | .8571/.8571/.8571 | .4817/.4817/.4817 | .5692/.5692/.5692 |
| compact/120 | .7143/.7143/.7143 | .4477/.4477/.4477 | .5097/.5097/.5097 |
| medium/080 | .7143/.7143/.7143 | .4101/.4101/.4101 | .4831/.4831/.4831 |
| medium/100 | .7143/.7143/.7143 | .3757/.3757/.3757 | .4571/.4571/.4571 |
| medium/120 | .5714/.5714/.5714 | .3774/.3774/.3774 | .4249/.4249/.4249 |
| large/080 | .7143/.7143/.7143 | .4294/.4294/.4294 | .5138/.5138/.5138 |
| large/100 | .6429/.6429/.6429 | .4060/.4060/.4060 | .4791/.4791/.4791 |
| large/120 | .5714/.5714/.5714 | .3571/.3571/.3571 | .4116/.4116/.4116 |
| current | .6429/.6429/.6429 | .4018/.4018/.4018 | .4595/.4595/.4595 |

最终只形成候选建议`compact/100 + depth 10 + RRF 60`，没有修改生产默认。下表为该候选全部冻结cutoff；顺序均为`@1/@3/@5/@8/@10/@20`，安全组没有可回答题，其0值只表示确定性排名指标不适用，安全结果看最后一列的误召回。

| 分组 | route | Precision | Recall = Hit Rate | MRR@10 | nDCG@5/@10 | 首个正确均值 | miss | SKU串答 | 无答案误召回 | 候选min/p50/p95/max | 延迟p50/p95/max ms |
|---|---|---|---|---:|---|---:|---:|---:|---:|---|---|
| 全部可回答 | Dense | .5588/.2745/.1882/.1213/.0971/.0485 | .5588/.7941/.9118/.9118/.9118/.9118 | .7010 | .7541/.7541 | 1.6774 | 3 | .1111 | 0 | 10/10/10/10 | 99/108/111 |
| 全部可回答 | Lexical | .3824/.1961/.1294/.0882/.0706/.0353 | .3824/.5882/.6176/.6765/.6765/.6765 | .4821 | .5095/.5298 | 2.0870 | 11 | .2222 | 0 | 4/10/10/10 | 61/364/517 |
| 全部可回答 | Hybrid | .5294/.2647/.1647/.1213/.0971/.0485 | .5294/.7647/.7647/.9118/.9118/.9118 | .6584 | .6702/.7193 | 2.2903 | 3 | .1111 | 0 | 11/17/20/20 | 0/1/1 |
| 真实跨境 | Dense | .5000/.2619/.1857/.1250/.1000/.0500 | .5000/.7143/.8571/.8571/.8571/.8571 | .6429 | .6967/.6967 | 1.7500 | 2 | .5000 | 0 | 10/10/10/10 | 101/108/108 |
| 真实跨境 | Lexical | .0000/.0952/.0714/.0536/.0429/.0214 | .0000/.2857/.2857/.3571/.3571/.3571 | .1310 | .1616/.1870 | 3.2000 | 9 | 1.0000 | 0 | 8/10/10/10 | 114/517/517 |
| 真实跨境 | Hybrid | .3571/.2143/.1429/.1250/.1000/.0500 | .3571/.5714/.5714/.8571/.8571/.8571 | .4817 | .4736/.5692 | 3.4167 | 2 | .5000 | 0 | 13/18/20/20 | 0/1/1 |
| 合成跨境 | Dense | .6000/.3333/.2000/.1250/.1000/.0500 | .6000/1/1/1/1/1 | .7833 | .8393/.8393 | 1.5000 | 0 | 0 | 0 | 10/10/10/10 | 98/107/107 |
| 合成跨境 | Lexical | .6000/.2667/.1800/.1250/.1000/.0500 | .6000/.8000/.9000/1/1/1 | .7226 | .7562/.7895 | 2.2000 | 0 | 0 | 0 | 4/10/10/10 | 61/372/372 |
| 合成跨境 | Hybrid | .7000/.3333/.2000/.1250/.1000/.0500 | .7000/1/1/1/1/1 | .8500 | .8893/.8893 | 1.3000 | 0 | 0 | 0 | 11/17/19/19 | 0/1/1 |
| 通用诊断 | Dense | .6000/.2333/.1800/.1125/.0900/.0450 | .6000/.7000/.9000/.9000/.9000/.9000 | .7000 | .7492/.7492 | 1.7778 | 1 | 0 | 0 | 10/10/10/10 | 95/110/110 |
| 通用诊断 | Lexical | .7000/.2667/.1600/.1000/.0800/.0400 | .7000/.8000/.8000/.8000/.8000/.8000 | .7333 | .7500/.7500 | 1.2500 | 2 | 0 | 0 | 9/10/10/10 | 56/87/87 |
| 通用诊断 | Hybrid | .6000/.2667/.1600/.1125/.0900/.0450 | .6000/.8000/.8000/.9000/.9000/.9000 | .7143 | .7262/.7595 | 1.8889 | 1 | 0 | 0 | 11/15/18/18 | 0/1/1 |
| 安全/ACL/版本 | Dense | 0/0/0/0/0/0 | 0/0/0/0/0/0 | 0 | 0/0 | - | 0 | - | 0 | 10/10/10/10 | 95/111/111 |
| 安全/ACL/版本 | Lexical | 0/0/0/0/0/0 | 0/0/0/0/0/0 | 0 | 0/0 | - | 0 | - | 0 | 6/10/10/10 | 61/172/172 |
| 安全/ACL/版本 | Hybrid | 0/0/0/0/0/0 | 0/0/0/0/0/0 | 0 | 0/0 | - | 0 | - | 0 | 12/14/17/17 | 0/0/0 |

全部34条可回答题之外另有6条无答案题，其中4条ACL/版本/拒绝来源可做确定性泄漏判断，误召回为0；另外2条属于语义未知/无证据，不伪装成确定性0分。过滤审计为ACL 4条、软删除2条route、inactive Index Set 2条route、tenant 80条route，泄漏全部0；所选配置重复120条route，排名变化0。排序前过滤仍由既有Repository SQL完成，本步没有在结果出来后再删禁用候选。

### 41.5 Bad Case与首错层

最终候选在真实跨境、合成跨境和通用诊断中分别保持独立结果。10个唯一问题存在Top8失败；不是笼统的“模型不好”：

- `smoke-syn-011-scan-batch`：Dense和Lexical完整depth 10均无正确Evidence，首错分别位于pgvector Dense召回和PostgreSQL FTS；Hybrid缺失来自两条上游输入，不归咎RRF；
- `smoke-syn-012-scan-sample`：Dense命中，Lexical在depth 10漏召回，首错为PostgreSQL FTS；
- `smoke-ext-024-record-retention`、`025-ioss-coverage`、`027-fixed-duty`、`028-handling-fee-vat`、`030-h7-conditions`、`032-en-ioss-optional`、`034-de-return-window`：Dense/Hybrid可命中，Lexical漏召回，首错为PostgreSQL FTS；
- `smoke-ext-029-return-invalidation`与`031-zh-responsible-person`：Dense和Lexical均漏召回，Hybrid没有可融合的正确输入，首错分别记录在pgvector Dense召回与PostgreSQL FTS，而不是RRF；
- 其余成功题中相似SKU/产品串答为：Dense 1/9、Lexical 2/9、Hybrid 1/9；真实跨境子组分别为1/2、2/2、1/2，说明真实相似产品仍是明确风险；
- Parser Artifact、Chunk范围和Golden/Evidence映射已由上游34/34内容+Locator及本轮Index映射证明通过；本轮没有Locator映射、ACL/active版本或真实RRF融合首错。生产2秒索引超时单独归为Index/PostgreSQL持久化边界。

### 41.6 Ragas正式状态与外部授权阻塞

固定`ragas==0.4.3`、`langchain-community==0.4.1`，Judge身份为`qwen-openai-compatible / qwen3.8-max / api-alias-20260909`，temperature 0、top-p 1、max output 2048、seed 20260909、单次30秒、最多2次，Prompt实现包SHA-256 `fc347923599df1a73f285372856a462e4ebbdf5a3e7bffdc40fc5a7332323845`。只对所选候选的34条可回答Hybrid结果运行，没有启动项目Qwen最终回答链。

正式结果分栏且全部保持非数值：Context Precision 34个`judge_failed/judge_provider_error`；Context Recall 34个同类失败；Context Relevancy 34个`framework_failed/framework_error`，原因是Ragas在底层连接失败后返回无效结果；Noise Sensitivity 34个`skipped/input_invalid`，因为0.4.3要求`response`而本步禁止构造回答。随后只补跑所选候选的外部网络申请被安全审查拒绝：评估问题、Golden摘要和候选原文会发送到外部Qwen API，而现有授权未被视为对这次数据发送的明确同意。没有绕过限制，也没有把失败写成0分或通过。

因此M2-22.6本地确定性部分完成，正式Ragas语义评分仍为`受阻`。只有用户在知情后明确允许上述数据发送，才可只补跑`compact/100 + depth 10 + RRF 60`；不得重新扩成全矩阵，更不得进入M2-22.7。

### 41.7 测试、工程门禁、清理与结论

实际验证结果：

- Locator/指标/报告/真实pgvector专项：`177 passed`；
- Index/Embedding/Retrieval相邻普通测试：`136 passed, 4 skipped`；4个跳过均为默认未开启的真实BGE Smoke，随后显式开启三个本地离线开关补跑为`4 passed`；
- 截至Retrieval的允许单元回归：`625 passed, 2 skipped`；两个跳过均为Windows无法创建测试symlink（errno 22）；
- 截至Retrieval的允许数据库/服务集成：`130 passed, 3 skipped, 1 failed`；3个跳过是默认关闭的重量级Docling/OCR Smoke。唯一失败`test_seed_m1::test_seed_is_repeatable_and_matches_business_contract`发生在测试清场：它先删除仍被正式M2 `document_versions`外键引用的M1 tenant，PostgreSQL正确拒绝；不是本次Locator、FTS、pgvector、RRF、ACL或active版本回归。未为凑绿修改数据库结构或正式数据；
- Ruff format覆盖348文件通过，Ruff lint通过，11个本步/直接相邻源码Mypy通过，`compileall app scripts tests`、`pip check`和`git diff --check`通过；没有安装DeepEval；
- 单题复现与正式矩阵两个目录在记录大小、Hash和汇总后，先核对绝对路径均位于`data/evals/runtime/reports/`，再精确递归删除；本步不再有检索summary/trace临时报告。8份冻结外部原文的raw/processed副本、三个既有Parser/Chunk诊断报告和本地模型缓存属于上游正式资产，未删除；
- 随后实际依次运行`seed_m1`、`seed_m2_files`、`seed_m2_complex_files`。独立使用容器内`psql`直接只读核对：files/documents/versions=`10/10/10`、ACL 9、pending版本10、Chunk Set/Index Set/Chunk=`0/0/0`、名称匹配M2-22.6的评估tenant 0、M1 `LR-TL-MUSH-OR01 @ DE-FRA`可售125；独立文件系统核对Storage仅10个`uploads`对象，无parsed/chunks/index评估对象。Runner的进程内BGE memo cache在`finally`清空，没有持久化查询缓存。最终正式基线恢复；

能证明：正确内容进入Chunk之后，当前BGE/FTS/RRF在这40题上的真实排名能力、四类分组差异、相似产品风险、权限与版本过滤、稳定性、延迟和候选来源均已量化；无坐标DOCX region不会再拖垮请求，坏Block也不能静默改善指标；`compact/100 + depth 10 + RRF 60`是本轮值得保留的候选。

不能证明：该候选应成为生产默认；外部Judge语义质量已经通过；Noise Sensitivity可以在不生成回答时计算；生产2秒SQL超时应该直接调大；困难真实题已解决；以及Reranker、Context/Evidence、回答、Citation、Agent或任何M2-22.7能力。生产默认Chunk、TopK、RRF、SQL和数据库结构均保持不变。

## 42. M2-22.6 Ragas检索语义评分补跑与最终收口（2026-09-10）

### 42.1 目标、输入、边界与调用链

用户明确授权后，本步只补齐M2-22.6缺少的Ragas检索语义判断，不重新海选Chunk或检索参数。输入仍是冻结的18份文档、40条Debug问题，其中只有34条可回答题进入外部Judge；配置严格固定为`compact 400/500 + overlap 100 + candidate depth 10 + RRF 60`。评估Runner新增`--ragas-selected-only`硬边界，并拒绝与baseline、单配置、单题、跳过Ragas等参数组合，避免误跑完整10组/50点矩阵。

真实调用链为：

```text
18份冻结文档
→ 上传/登记 API
→ Parser / R04
→ Chunker v3 compact/100
→ Index Service
→ 本地固定BGE-M3
→ PostgreSQL FTS / pgvector
→ Dense / Lexical
→ RRF 60 Hybrid（最多20个合并候选）
→ Ragas 0.4.3检索语义适配层
→ 外部Qwen仅作为Judge
```

本步没有经过Reranker、Context Builder、Evidence、Harness、Tool、Agent/LangGraph、项目Qwen最终回答或Citation，也没有安装DeepEval。发送范围只包含34条冻结问题、对应Golden摘要和当前Hybrid候选必要原文；没有发送密钥、数据库密码、无关tenant/生产数据、评估范围外内容或Judge思维链。Trace只保存正文SHA-256，不保存正文。

### 42.2 修改文件与职责

- `scripts/run_m2_retrieval_evaluation.py`：增加并冻结`--ragas-selected-only`运行入口，只允许单一Chunk配置、depth 10和RRF 60；
- `app/evals/retrieval_runner.py`：逐题记录不含正文的Ragas进度；可回答Hybrid结果若没有候选则硬失败，不能静默漏评；
- `app/evals/ragas_retrieval.py`：冻结并启动时复核Prompt实现Hash；把最终网络、超时、限流、Provider和框架失败分开，失败不产生数值；
- `app/schemas/evaluation.py`：补充`network_error`失败类别；
- `tests/unit/test_m2_retrieval_runner.py`：验证单配置CLI范围和冲突参数；
- `tests/unit/test_ragas_retrieval_adapter.py`：验证Prompt Hash、失败分类和安全摘要不泄露底层错误正文。

生产Chunk、TopK、RRF、SQL、数据库结构和最终回答链均未修改。

### 42.3 正式运行与确定性复核

正式Run为`m2-22.6-20260909t165858-4a56843a`，UTC时间`2026-09-09T16:58:58Z`至`18:59:33Z`，约2小时。它从干净基线真实完成18份文档解析、40条查询Embedding、18个Index Set、779个Chunk和唯一一个`compact/100 + depth 10 + RRF 60`实验；Trace覆盖40题、120条Dense/Lexical/Hybrid route list和1,430个候选，候选映射失败0，完整性门禁通过，生产默认未变。

本轮Hybrid确定性结果没有覆盖旧矩阵，而是并列保留：

| 分组 | 旧矩阵Hit/Recall@8 | 本轮Hit/Recall@8 | 旧→新 MRR@10 | 旧→新 nDCG@10 | miss |
|---|---:|---:|---:|---:|---:|
| 全部34条可回答 | .9118 | .9118 | .6584 → .6929 | .7193 → .7450 | 3 → 3 |
| 真实跨境14条 | .8571 | .8571 | .4817 → .4940 | .5692 → .5789 | 2 → 2 |
| 合成跨境10条 | 1.0000 | 1.0000 | .8500 → 1.0000 | .8893 → 1.0000 | 0 → 0 |
| 通用诊断10条 | .9000 | .9000 | .7143 → .6643 | .7595 → .7226 | 1 → 1 |

关键结论是召回门槛、安全结果和漏题数复现，但前部名次没有跨清理重建完全复现。本轮全部34题Hybrid Hit@1由`.5294`变为`.5882`，真实组不变、合成组`.7000→1.0000`、通用组`.6000→.5000`。代码只读定位显示Dense与Lexical同分时按`DocumentChunk.id`排序，RRF同分也按运行期`chunk_id`排序；清理重建会产生新数据库UUID，因此同分候选可能换位。当前Run内部120条稳定性复跑仍为0变化，但这只能证明同一批Index内稳定，不能证明跨重建稳定。修复该问题会改变生产排序合同，超出本次授权，故只登记风险，不改代码或参数。

过滤审计复现为ACL 4题泄漏0、软删除2条route泄漏0、inactive Index Set泄漏0、跨tenant 80条route泄漏0；相似产品Hybrid串答仍为1/9。没有重新运行其他9组Chunk配置或其余49个矩阵点。

### 42.4 Judge身份、Ragas汇总与计分口径

依赖保持`ragas==0.4.3`、`langchain-community==0.4.1`，未升级、降级或替换。Judge身份为`qwen-openai-compatible / qwen3.8-max / api-alias-20260909`；temperature 0、top-p 1、max output 2048、seed 20260909、单次超时30秒、最多2次；Prompt身份`ragas-0.4.3-collections-source-v1`，实现包SHA-256为`fc347923599df1a73f285372856a462e4ebbdf5a3e7bffdc40fc5a7332323845`。

下表的均值只对`completed`样本做算术平均；失败和跳过没有数值，也没有按0分混入均值。因此“4/14，均值.7917”表示真实组只有4题Precision得到有效结果，不能解释为14题整体分数。

| 分组 | Context Precision | Context Recall | Context Relevancy | Noise Sensitivity |
|---|---|---|---|---|
| 全部34条 | .8024（21完成/13失败） | .9630（27完成/7失败） | .9815（27完成/7失败） | 34跳过/`input_invalid` |
| 真实跨境14条 | .7917（4完成/10失败） | 1.0000（8完成/6失败） | 1.0000（7完成/7失败） | 14跳过/`input_invalid` |
| 合成跨境10条 | .9571（7完成/3失败） | 1.0000（10完成） | 1.0000（10完成） | 10跳过/`input_invalid` |
| 通用诊断10条 | .6984（10完成） | .8889（9完成/1失败） | .9500（10完成） | 10跳过/`input_invalid` |

最终状态总计：Context Precision为21完成、6个`judge_timeout`、7个`judge_provider_error`；Context Recall为27完成、1个`judge_timeout`、6个`judge_provider_error`；Context Relevancy为27完成、7个`framework_error`；Noise Sensitivity因0.4.3要求`response`而34个全部`skipped/input_invalid`。没有构造项目回答来凑该指标。

### 42.5 34题逐项Ragas结果

表中`T`为`judge_timeout`，`P`为`judge_provider_error`，`F`为`framework_error`，`S`为`skipped/input_invalid`；所有失败/跳过格都没有数值。

| case | 分组 | Precision | Recall | Relevancy | Noise |
|---|---|---:|---:|---:|---|
| smoke-syn-001-voltage | 合成跨境 | 1.000000 | 1.000000 | 1.000000 | S |
| smoke-syn-002-cleaning | 合成跨境 | .700000 | 1.000000 | 1.000000 | S |
| smoke-syn-003-sample-size | 合成跨境 | 1.000000 | 1.000000 | 1.000000 | S |
| smoke-syn-004-exposed-wire | 合成跨境 | 1.000000 | 1.000000 | 1.000000 | S |
| smoke-syn-005-disclaimer | 合成跨境 | T | 1.000000 | 1.000000 | S |
| smoke-syn-006-weee-status | 合成跨境 | T | 1.000000 | 1.000000 | S |
| smoke-syn-007-supplier-price | 合成跨境 | 1.000000 | 1.000000 | 1.000000 | S |
| smoke-syn-008-landed-formula | 合成跨境 | 1.000000 | 1.000000 | 1.000000 | S |
| smoke-syn-009-de-june-sales | 合成跨境 | 1.000000 | 1.000000 | 1.000000 | S |
| smoke-syn-010-fr-row-range | 合成跨境 | T | 1.000000 | 1.000000 | S |
| smoke-syn-011-scan-batch | 通用诊断 | .000000 | .000000 | .500000 | S |
| smoke-syn-012-scan-sample | 通用诊断 | .642857 | 1.000000 | 1.000000 | S |
| smoke-syn-013-ad-budget | 通用诊断 | 1.000000 | 1.000000 | 1.000000 | S |
| smoke-syn-014-reorder-line | 通用诊断 | 1.000000 | 1.000000 | 1.000000 | S |
| smoke-syn-015-visual-control | 通用诊断 | .500000 | 1.000000 | 1.000000 | S |
| smoke-syn-016-visual-quarantine | 通用诊断 | 1.000000 | 1.000000 | 1.000000 | S |
| smoke-syn-017-cost-c | 通用诊断 | 1.000000 | 1.000000 | 1.000000 | S |
| smoke-syn-018-lowest-logistics | 通用诊断 | .500000 | T | 1.000000 | S |
| smoke-syn-019-replenish | 通用诊断 | .340909 | 1.000000 | 1.000000 | S |
| smoke-syn-020-lead-formula | 通用诊断 | 1.000000 | 1.000000 | 1.000000 | S |
| smoke-ext-021-gpsr-date | 真实跨境 | 1.000000 | 1.000000 | 1.000000 | S |
| smoke-ext-022-alert-count | 真实跨境 | 1.000000 | 1.000000 | 1.000000 | S |
| smoke-ext-023-alert-model-risk | 真实跨境 | 1.000000 | 1.000000 | 1.000000 | S |
| smoke-ext-024-record-retention | 真实跨境 | .166667 | 1.000000 | 1.000000 | S |
| smoke-ext-025-ioss-coverage | 真实跨境 | T | 1.000000 | 1.000000 | S |
| smoke-ext-026-oss-return-cycle | 真实跨境 | T | 1.000000 | 1.000000 | S |
| smoke-ext-027-fixed-duty | 真实跨境 | T | 1.000000 | 1.000000 | S |
| smoke-ext-028-handling-fee-vat | 真实跨境 | P | P | F | S |
| smoke-ext-029-return-invalidation | 真实跨境 | P | P | F | S |
| smoke-ext-030-h7-conditions | 真实跨境 | P | 1.000000 | F | S |
| smoke-ext-031-zh-responsible-person | 真实跨境 | P | P | F | S |
| smoke-ext-032-en-ioss-optional | 真实跨境 | P | P | F | S |
| smoke-ext-033-de-risk-categories | 真实跨境 | P | P | F | S |
| smoke-ext-034-de-return-window | 真实跨境 | P | P | F | S |

### 42.6 Judge、网络和框架Bad Case

- 超时：`smoke-syn-005/006/010`与`smoke-ext-025/026/027`的Precision，以及`smoke-syn-018`的Recall，在有界重试后仍超时；最终状态是7个`judge_timeout`，无数值；
- Provider：从`smoke-ext-028`附近起，外部Qwen明确返回HTTP 400 `Arrearage`（账户欠费/账户状态拒绝）。最终安全报告不保存Provider原始错误、请求ID或密钥，只留下13个`judge_provider_error`；涉及028—034的Precision及除030外的Recall；
- 网络：运行中观察到多次瞬时`Connection error`，部分随后成功，正式最终状态中`network_error=0`。当前报告没有持久化“恢复成功的瞬时重试次数”，因此不伪造精确数量；
- 框架：028—034的Context Relevancy在底层Provider失败后由Ragas返回无效语义结果，最终7个`framework_error`；失败没有被写成0分；
- 语义低分：在有效结果中，`smoke-syn-011-scan-batch`的Precision/Recall为0、Relevancy为.5；这与确定性检索完全漏召回一致。`smoke-ext-024-record-retention`Precision仅.166667，说明候选虽命中Golden，但噪声较多。

Provider欠费使7道后段真实题的三项语义指标不完整，因此本轮不是“34题Ragas全量成功”，也不能据此宣称真实跨境语义质量已经整体通过。已完成样本的均值仍可作为局部观察值，失败样本必须保留为缺失状态。

### 42.7 报告、验证、清理与完成标准

正式摘要`summary.json`为232,280字节，SHA-256 `24511d80c2d1b200e05a93e5b71b9a7388fa1616a350bc3b8c41040c791b3d24`；唯一Trace为1,094,678字节，SHA-256 `0d7e00192dc8664dfcaed3946ece51312a0d618c7d4329d34eee2ce6f7eeda7d`。Runner在`finally`中已清空进程内Embedding memo cache，并把评估数据库行和Storage对象清零；本节先记录摘要、逐题结果与Hash，再核对绝对路径确在`data/evals/runtime/reports/`内并精确删除唯一Run目录，最终剩余报告目录0。

实际验证结果：

- Ragas专项：`9 passed`；
- Evaluation Runner、指标与报告合同：`96 passed`；
- Index/Embedding/Retrieval相邻单元与真实数据库集成：`153 passed`；
- 截至Retrieval且排除Reranker/Context/Tool/Harness/Agent的允许单元回归：`680 passed, 2 skipped`，两个跳过为Windows symlink能力限制；
- 截至Retrieval允许数据库/服务集成：`140 passed, 2 skipped, 1 failed`；两个跳过是默认未开启的重量级Docling Smoke，唯一失败仍是历史`test_seed_m1`清场先删被正式M2外键引用的tenant，PostgreSQL正确拒绝，不是本次检索或Ragas回归；
- 显式加载固定本地BGE-M3的Embedding/Index/Retrieval Smoke：`4 passed`；
- Ruff format覆盖348文件、Ruff lint、Mypy 163源码、`compileall app scripts tests`、`pip check`和`git diff --check`全部通过；diff检查只有既有Windows LF/CRLF提示；
- Docker中的`deep-search-postgres`为healthy，pgvector扩展版本`0.8.6`；固定BGE-M3 revision `5617a9f61b028005a4858fdac845db406aefb181`本地32个文件约2.138 GiB，D盘最终清理前可用约148.74 GiB。

删除报告并完成全部测试后，最终再次依次运行`seed_m1`、`seed_m2_files`和`seed_m2_complex_files`。容器内`psql`独立只读核对：files/documents/versions=`10/10/10`，parse/index pending=`10/10`，ACL 9，Chunk Set/Index Set/Chunk=`0/0/0`，名称匹配M2-22.6的评估tenant 0，pgvector `0.8.6`；M1目标库存为on-hand 150、reserved 20、unsellable 5、available 125。文件系统独立核对Storage仅10个正式upload对象、派生或评估对象0，本次检索Run目录0；三个上游Parser/Chunk诊断报告和8份冻结外部原文的raw/processed副本按正式资产保留。最终D盘可用约148.74 GiB。

能证明：这18文档/34条可回答题在所选真实检索链上的部分语义质量得到了外部Judge有效分数；失败状态、权限过滤、候选映射、清理和依赖身份可审计；`smoke-syn-011`和`smoke-ext-024`是明确语义Bad Case；单一配置运行没有修改生产参数。

不能证明：34题三项Ragas已经全量成功；真实跨境组的局部完成均值代表完整14题；Noise Sensitivity可在无回答时计算；候选应该直接成为生产默认；跨重建排序完全稳定；以及Reranker、Context/Evidence、回答、Citation、Agent或M2-22.7任何能力。M2-22.6以“有效分数与失败均真实记录”的标准收口，而不是把外部Provider失败伪装成质量通过。

