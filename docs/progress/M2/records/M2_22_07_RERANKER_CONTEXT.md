# M2-22.7｜Reranker、Context与漏召回诊断记录

> 以下第43至49节从原M2-22总记录按连续区间原样迁入，保留方案、真实资源数据、质量门禁和Bad Case。

## 43. M2-22.7详细实施方案与文档同步（2026-09-10）

### 43.1 用户意图、当前现状与缺少的能力

用户先明确要求开始M2-22.7，随后补充必须先同步正式文档并查看M2-22.7的小步骤。因此本节先完成方案和状态同步，不把“开始下一步”扩大解释为已经授权运行全部五个小步；用户确认本节后才实施M2-22.7.1，每个小步完成、验证和讲解后继续停止等待。

M2-22.6已经在18份文档、40条Debug问题上筛出`compact 400/500 + overlap 100 + candidate depth 10 + RRF 60`。34条可回答题的Hybrid Recall@8为`.9118`，其中真实跨境14题为`.8571`；三条最终漏题在所选depth 10的Dense和Lexical上游都没有正确Evidence。真实组把每路候选深度扩大到20/30时，完整融合候选的miss仍为2，因此Reranker不能凭空补回这些不存在于输入候选池的证据。

现有`RerankerRetrievalService`、固定本地`BAAI/bge-reranker-v2-m3@953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e`和`ContextBuilderService`已经实现并在旧10文档小集合上通过工程验证；但旧M2-17的18条可检索Golden、Fake Embedding和最多30条候选不能代替当前18文档/40题真实BGE-M3检索集。当前缺少的是：同一批M2-22.6获权Hybrid候选经过真实BGE-Reranker后是否升排、Top5/Top8如何取舍、邻块0/1和Context 2000/3000/4000预算如何影响Golden覆盖、冗余、Token与CPU资源，以及这些结论能否在清理和权限门禁下复现。

### 43.2 本步目标与明确不做

M2-22.7只完成四件事：

1. 在完全相同且已经获权的Hybrid候选上比较RRF与Reranker，保留上游候选缺失、升排、降排和不变四类结果；
2. 顺序筛选Reranker Top5/Top8，再只对筛出的TopK比较邻块0/1与Context Token上限2000/3000/4000，不做无界笛卡尔积；
3. 用项目确定性Evaluator计算排名、Golden Evidence覆盖、Context冗余、Token和安全结果，记录本地BGE模型身份、缓存身份、p50/p95/max延迟和峰值RSS；
4. 形成Debug集候选建议与Bad Case，恢复正式Seed和Storage基线；不因指标不达标而删除难题、改变分母或直接修改生产默认。

本步不生成最终回答，不运行Ragas生成指标、Qwen、Knowledge Tool、Harness、Agent/LangGraph、公开聊天API、Citation或前端；不新增Worker/Tool，不部署GPU/独立推理服务，不修改BGE-Reranker、Context Builder、生产Chunk/TopK/RRF/Context默认值、数据库结构或正式Golden。若评估暴露生产实现缺陷，必须停止并单独提交最小修复方案。

### 43.3 前置条件与固定口径

- 数据、来源、Golden、Parser、Chunker v3、固定BGE-M3和M2-22.6所选检索配置继续使用第42节身份，不重新海选10组Chunk或RRF常数；
- 固定本地Reranker snapshot必须按既有manifest和文件Hash强制离线加载；外部Qwen欠费不阻塞本步；
- 34条可回答题全部进入排名和Context质量分母，6条无答案/ACL/版本题进入零容忍安全分栏；候选缺失必须记为上游失败，不能从Reranker分母移除；
- RRF与Reranker必须比较同一批候选身份和正文Hash；Reranker只能重排，不能新增、替换或越权读取候选；
- 每题对最大候选并集只做一次真实Reranker评分，评估缓存只在当前Run内复用。缓存身份至少绑定query Hash、候选有序身份及正文Hash、模型ID/revision、最大长度、精度和评分实现版本；缓存不进入生产链、不跨Run冒充可复现结果；
- Context必须通过现有Repository按当前用户、ACL、软删除和active代次重新取回锚点与邻块，不信任评估Runner携带的正文；Token使用项目`m2-unicode-token-counter-v1`，不能冒充Qwen真实Token；
- 当前真实跨境完整候选最多命中12/14，所以仅靠Reranker无法达到第10节建议的`.90` Recall@8门禁。M2-22.7的“评估完成”和“质量门禁通过”必须分开；若正式结果仍未达标，照实收口评估并在进入M2-22.8前单独讨论召回修复。

### 43.4 五个小步骤

#### M2-22.7.1｜评估配置、结果合同与确定性指标

- 输入：冻结的RRF候选身份、Reranker有序评分、Golden Evidence映射和Context片段元数据；
- 输出：严格的TopK/Context顺序实验计划、逐题Reranker对比、逐题Context质量和分组聚合合同；精确定义候选缺失、升排/降排、Golden覆盖、冗余、Token利用率和失败状态；
- 预计文件：`app/schemas/evaluation.py`、新增`app/evals/reranker_context_metrics.py`、新增`tests/unit/test_rag_reranker_context_metrics.py`，以及本记录/阶段入口/总看板；
- 验证：先用缺少合同或实现的RED证明缺口，再做最小GREEN；覆盖Top5/Top8、缺失候选不出分母、重复候选拒绝、邻块不能伪装Anchor、Token超限拒绝、空Context与失败非数值；运行聚焦单元、相邻评估合同、Ruff、Mypy、编译和diff检查；
- 停止点：不创建Runner、不访问数据库、不加载BGE，完成后等待用户确认M2-22.7.2。

#### M2-22.7.2｜Fake Runner、报告和Run内评分缓存

- 输入：M2-22.6所选配置、冻结数据集、确定性Fake Reranker和Fake Context读取器；
- 输出：只运行“Top5/Top8 → 选定TopK下的邻块/Token”顺序筛选的Runner、公开安全报告、逐题Trace Hash和Run内评分缓存；
- 预计文件：新增`app/evals/reranker_context_runner.py`与`app/evals/reranker_context_report.py`、新增`scripts/run_m2_reranker_context_evaluation.py`、对应Runner/报告/CLI单元测试及进度文档；
- 验证：最大候选每题只评分一次、不同query/候选Hash/模型身份不得误命中缓存、失败不缓存、报告不保存正文/路径/Storage Key、顺序计划不是`2×2×3`无界重复推理、重复运行结果确定；
- 停止点：只用Fake和内存夹具，不访问真实PostgreSQL/Storage、不加载真实BGE，完成后等待用户确认M2-22.7.3。

#### M2-22.7.3｜真实PostgreSQL/pgvector、权限重取与清理闭环

- 输入：18份冻结文档、公开摄取身份、所选Chunk/检索配置、Fake Reranker和真实Context Builder/Repository；其中上传、解析和切块是固定语料的首次准备阶段，不是每次查询实验都重跑；
- 输出：幂等固定语料准备器、持久ChunkSet/IndexSet、真实Hybrid、Reranker边界、Context重取及权限/active版本门禁。成功语料继续保留；只有首次创建中途失败或测试隔离数据才精确回滚；
- 预计文件：`app/evals/reranker_context_runner.py`、真实运行装配接缝、`tests/integration/test_m2_rag_reranker_context_runner.py`及直接相邻夹具/进度文档；
- 验证：候选集合严格不扩大，ACL撤销、软删除、active切代、跨tenant和坏Context来源均安全失败；Context来自数据库当前快照；同配置二次调用的Document/ChunkSet/IndexSet/Chunk身份完全不变，修改Embedding/FTS身份时只建新IndexSet、不得重切Chunk；
- 停止点：不加载真实BGE、不跑40题正式质量矩阵，完成后等待用户确认M2-22.7.4。

> 用户确认的方案修订：M2-22.5/.6早期评估Runner为了恢复基线曾在结束时删除评估Chunk；用户明确要求从本步开始把18份固定文档作为可复用语料保留。因此后续普通查询、Dense/Lexical depth、RRF、TopK、Reranker和查询侧关键词逻辑实验都复用同一ChunkSet；Embedding或文档FTS构造身份变化只重建IndexSet。只有原文、Parser产物或Chunk配置变化才重新解析/切块。该修订替代本节旧版“每次真实摄取后finally清零”的成功路径，不改变失败时精确回滚要求。

#### M2-22.7.4｜固定本地BGE-Reranker小样本资源探针

- 输入：固定模型snapshot和少量预先指定的中英德、表格、候选缺失及无答案代表题；
- 输出：离线加载身份、单次最大候选评分、缓存复用、截断、CPU延迟与峰值RSS探针；候选缺失题必须保持缺失；
- 预计文件：真实Provider装配/CLI开关、Smoke测试或专用探针测试、报告合同和进度文档；
- 验证：local-only、manifest/Hash、模型ID/revision、一次评分复用、异常脱敏、有限值、进程退出和内存记录；结果只证明资源与链路可运行，不冒充40题质量结论；
- 停止点：不运行完整矩阵，完成后等待用户确认M2-22.7.5。

#### M2-22.7.5｜18文档/40题正式矩阵、回归与收口

- 输入：通过前四步的Runner、固定18文档/40题、所选检索配置和固定本地BGE-Reranker；
- 输出：RRF与Reranker逐题/分组排名差异、Top5/Top8选择、所选TopK下6个Context配置的覆盖/冗余/Token、Bad Case、资源、缓存、清理和候选建议；
- 预计文件：Runner/报告的必要收口、正式运行脚本测试、M2-22记录、M2入口和总看板；不预设必须修改生产文件；
- 验证：34条可回答题与6条安全题全部出现，合成/真实/诊断分组独立；项目指标可从逐题结果复算；安全泄漏0；报告先记录大小/Hash和摘要再精确删除；运行聚焦、相邻、允许单元/集成、显式本地BGE Smoke、Ruff、Mypy、编译、依赖和diff门禁；三套Seed重跑并独立核对数据库/Storage基线；
- 停止点：无论质量是否达标都先向用户讲清升降排、Context取舍、资源和首错层。未获新授权不得修改生产配置、修复召回、进入M2-22.8或运行Qwen。

### 43.5 完整调用链位置

```text
前端：不经过
→ API：M2-22.7.3固定语料首次缺失时复用公开文件入口；之后.7.3/.5查询实验直接复用数据库中的Document/ChunkSet/IndexSet，纯指标与层级复算不经过公开聊天API
→ Schema：Evaluation、Retrieval、Reranker、Context合同
→ Agent/LangGraph：不经过
→ Harness：不经过
→ Tool：不经过
→ Service：Parser → Chunk → Index → Dense/Lexical/RRF → Reranker → Context Builder
→ Repository/Model：当前权限候选、active代次、Chunk与Context重取
→ PostgreSQL/pgvector/Storage：真实集成和正式矩阵经过
→ 外部Provider：不经过；BGE-M3与BGE-Reranker均从本地固定snapshot离线运行，Qwen不运行
```

### 43.6 阶段完成标准

- 五个小步骤各自完成RED/GREEN、相邻回归、完整记录和停止复核；
- RRF与Reranker使用同一候选集，34条可回答题分母不变，三条上游候选缺失不被归咎或隐藏；
- Top5/Top8及邻块0/1、Token 2000/3000/4000按顺序筛选，真实评分不因Context组合重复执行；
- 排名、Context覆盖/冗余/Token、CPU/RSS、模型/缓存身份、三类数据分组与Bad Case可复算；
- ACL、tenant、软删除和active版本泄漏为0，Context重新获权和预算门禁全部通过；
- 临时报告、失败的半成品语料、测试隔离数据和模型进程清理完成；成功的18文档固定语料及其ChunkSet/IndexSet保留，正式Seed与M1库存不被修改；
- “评估运行完成”与“质量达到建议门禁”分开报告；未达标时不得自动进入回答评估或修改生产参数。

### 43.7 主要风险与优先排查方向

- Reranker无法修复候选缺失：先看Dense/Lexical完整候选是否包含Golden，再看重排；不得用扩大分母、删题或邻块碰巧带回正文伪装召回成功；
- CPU与内存：旧M2-17在约15候选时Reranker p50约6.7秒、查询阶段RSS增量约1.29 GiB；先查是否每题只评分一次、batch和文本截断，再判断是否需要缩小本步运行批次，不直接引入GPU服务；
- 缓存串用：先核对query、候选有序身份/正文Hash、模型revision和评分参数是否全部进入缓存键；
- Context覆盖低：按“Reranker Anchor是否正确 → Repository当前授权重取 → 邻块关系 → overlap去重 → Token裁剪”顺序排查，不先放宽预算；
- 跨重建排序变化：M2-22.6已知UUID同分兜底风险继续单列；RRF与Reranker必须在同一Run、同一候选快照内比较，不能把不同重建的名次差归因于模型；
- 报告泄露或过大：Trace只保存公开身份、Locator、分数、正文Hash和Evidence映射，不保存正文、内部路径、Storage Key、向量、密钥或原始异常；
- 数据生命周期错误：若普通查询后ChunkSet/Chunk身份变化，先停止并核对是否误调用Parser/Chunk/Index准备路径；失败半成品或测试隔离数据清理失败时，再核对tenant、外键、Storage派生对象和Worker/模型进程。成功固定语料不得作为临时数据自动删除。

### 43.8 当前停止点

本节只同步方案与状态，未修改`app/`、`scripts/`、`tests/`、依赖、数据库、Storage或生产配置，未运行Reranker、Context、BGE或测试。下一动作是用户确认上述五步；确认后只实施M2-22.7.1，并在验证和记录后停止。

### 43.9 本次文档同步实施记录

- 日期、阶段与步骤：2026-09-10，M2-22.7方案同步；
- 目标与实际修改：`docs/PROJECT_PROGRESS.md`把项目停止点改为M2-22.7方案待确认；`docs/progress/M2/M2_KNOWLEDGE_RAG.md`修正“仍未接通M2-22.6”和“M2-22受阻”两处过时摘要；本文把M2-22.6状态改为已完成，并新增第43节完整五步方案、边界、调用链、完成标准和风险；
- 调用链位置：只修改进度与方案文档，前端、API、Schema运行代码、Agent/LangGraph、Harness、Tool、Service、Repository/Model、PostgreSQL/pgvector/Storage和外部Provider均未经过；
- 验证方法与实际结果：`rg`复核三份文档的当前停止点、下一动作、M2-22状态、M2-22.6/.7状态和五个子步骤；活动摘要中不再存在“仍未接通M2-22.6”“M2-22.7尚未授权”或“Ragas仍待补”的旧表述。三份文档Markdown代码栅栏数分别为0、22、78，均为偶数；Tracked文档`git diff --check`通过，未跟踪的本文用`git diff --no-index --check`通过，仅有Windows LF/CRLF提示；固定Reranker revision另与`app/core/config.py`和M2-17记录交叉核对一致；
- 能证明：总看板、M2入口和M2-22过程记录现在对当前停止点、五步顺序、禁止范围和下一动作表达一致；
- 不能证明：任何M2-22.7合同、指标、Runner、缓存、真实数据库链、BGE资源或40题质量已经实现或运行；本次没有运行应用测试，也没有重新验证M2-22.6历史指标；
- 风险与排查：当前M2-22代码和记录仍位于有大量未提交变更的工作区，后续只允许在明确目标文件上做最小补丁并持续检查diff，不能覆盖或混入无关文件；
- 下一步：等待用户确认第43节方案；确认后只实施M2-22.7.1，完成验证与记录后停止。

## 44. M2-22.7.1实施记录：评估配置、结果合同与确定性指标（2026-09-10）

### 44.1 本步解决的问题与输入输出

- 当前缺口：M2-22.6已经选出`compact 400/500 + overlap 100 + candidate depth 10 + RRF 60`，但此前没有一份可执行合同保证Top5/Top8按顺序筛选、34条可回答题始终留在分母、上游候选缺失不会被删题或误算成Reranker失败，也没有统一冻结Context覆盖、冗余、Token利用率和失败状态；
- 输入：冻结数据集中的40条题、同一题同一次Run内最多20条的RRF候选快照、未来Reranker对同一候选池给出的顺序，以及未来Context Builder输出的Anchor/Neighbor、Evidence和Token元数据；这里的20来自Dense与Lexical各取深度10后的去重并集上限，不代表把候选深度改成20；
- 输出：冻结配置、8个有顺序的实验点、34+6固定队列、逐题RRF/Reranker比较、逐题Context质量、分组聚合和安全分栏合同，以及不依赖模型和数据库的纯确定性计算函数；
- 为什么需要：如果先写Runner，遗漏题目、换候选池或把失败填成0都可能让报告看似更好。先冻结合同，后续Fake Runner、真实数据库链和真实BGE只能按同一把尺子填数据；
- 明确不做：本步未创建Runner、报告CLI、缓存、数据库接线或模型加载，未修改生产Reranker、Context Builder、配置、迁移或依赖。

### 44.2 冻结的计算口径

1. 顺序筛选配置：先只比较Reranker Top5和Top8；选定其中一个TopK后，才比较邻块窗口`0/1`与Token预算`2000/3000/4000`，因此计划固定为`2 + 2 × 3 = 8`个实验点，不把真实Reranker重复扩成`2 × 2 × 3`次；
2. 候选池一致性：RRF前后必须具有完全相同的候选ID、Evidence集合和公开来源身份，且不得重复；Reranker只能改顺序，不能加、删或替换候选；
3. 候选缺失：若完整RRF候选池没有任何Golden Evidence，则状态为`candidate_missing`，RRF与Reranker首个正确名次均为`None`，Top5/Top8命中均为`False`；该题仍是成功计算的逐题记录并留在34题分母中，不能归咎于Reranker；
4. 升排、降排与排名不变：分别比较同一候选池中首个含Golden Evidence候选的RRF名次和Reranker名次；新名次更小为`promoted`、更大为`demoted`、相等为`unchanged`；Top5/Top8命中另按该名次独立计算；
5. Context Golden Evidence覆盖率：最终Context全部Anchor和Neighbor片段覆盖的不同Golden Evidence数 ÷ 该题Golden Evidence总数；Anchor覆盖率只看真正位于所选TopK中的Anchor，Neighbor即使补回Evidence也不能伪装成Anchor命中；
6. Context冗余率：按最终Context顺序，某片段没有新增尚未覆盖的Golden Evidence即记为冗余；冗余片段数 ÷ Context片段总数。它衡量的是相对Golden Evidence的确定性冗余，不等价于通用语义重复度；
7. Token利用率：Context片段Token总数 ÷ 配置预算`2000/3000/4000`；总数超过预算直接拒绝。Token口径沿用`m2-unicode-token-counter-v1`身份；
8. 空Context与计算失败：合法的空Context确实得到覆盖率、冗余率和Token利用率`0.0`；`failed/skipped`的计算值必须全部为`None`并附失败原因，不能伪装成0分；只要分组内有失败，聚合数值也保持`None`；
9. 固定分栏：34条可回答题必须与声明ID逐条完全对应；6条安全题继续独立保留为ACL 2条、版本2条、无证据1条、未知1条，不能并入质量分母。只有确定性的受保护来源题计算零泄漏断言，未知/无证据题不伪造安全分数。

### 44.3 修改文件与职责

- `app/schemas/evaluation.py`：新增固定评估计划、顺序实验点、34+6队列、逐题与分组Reranker/Context结果、安全结果合同，并通过交叉字段校验阻止候选池漂移、失败填0和分母缩水；
- `app/evals/reranker_context_metrics.py`：新增不访问外部系统的纯计算函数，负责生成8点计划、冻结40题队列、比较排名、计算Context指标、聚合结果和检查安全分栏；
- `tests/unit/test_rag_reranker_context_metrics.py`：新增13个单元测试，覆盖固定模型身份、真实34+6队列、最大20候选、Top5/Top8、候选缺失、同池约束、Anchor/Neighbor边界、假Anchor、重复片段、Token超限、空Context、失败非数值和安全分栏；
- `docs/PROJECT_PROGRESS.md`、`docs/progress/M2/M2_KNOWLEDGE_RAG.md`与本文：同步当前状态、决策、验证基线、风险和下一动作。

### 44.4 RED、GREEN与实际验证

- RED：先创建只引用目标模块和合同的测试，运行`.venv\Scripts\python.exe -m pytest tests/unit/test_rag_reranker_context_metrics.py -q`，测试收集阶段以`ModuleNotFoundError: No module named 'app.evals.reranker_context_metrics'`失败；这准确证明缺少本步模块，而不是用人为失败断言制造RED；
- GREEN：完成最小Schema与纯指标模块后，聚焦测试为`13 passed in 1.55s`；
- 相邻评估合同：聚焦测试加`test_rag_evaluation_contracts.py`、`test_rag_retrieval_metrics.py`、`test_ragas_retrieval_adapter.py`和`test_m2_cross_border_eval_smoke_dataset.py`共`111 passed in 12.64s`；
- 静态与编译门禁：`ruff check app tests scripts migrations`通过；三个目标Python文件`ruff format --check`通过；`mypy app`通过，覆盖161个源文件；`compileall -q app`通过；`git diff --check`通过，仅出现Windows工作区既有的LF/CRLF转换提示；
- 验证环境没有访问PostgreSQL、pgvector、Storage，也没有加载或运行BGE、Qwen、Ragas。

### 44.5 完整调用链位置

```text
冻结JSONL / RRF候选快照 / 未来Reranker顺序 / 未来Context元数据
→ Evaluation Schema
→ 纯确定性指标函数
→ 未来M2-22.7.2 Runner与报告（本步未实现）
```

- 前端、API、Agent/LangGraph、Harness、Tool均不经过；
- Service中的生产Retrieval、Reranker和Context Builder不经过也未修改；
- Repository/Model、PostgreSQL/pgvector/Storage、外部Provider均不经过；
- 本步位于正式评估Runner的“尺子”层，只定义后续各层必须提交什么数据以及怎样计算结果。

### 44.6 能证明与不能证明

- 能证明：合同可以拒绝分母缩水、Reranker候选池变化、Neighbor伪装Anchor、重复身份、Token超限和失败填0；同一批逐题结果可确定性复算排名变化、TopK命中、Context覆盖、冗余和Token利用率；
- 不能证明：尚未证明真实BGE-Reranker能加载、资源可接受或能提升Top5/Top8，也未证明真实Context数据库重取、安全链、报告、缓存和清理闭环；
- 质量结论：本步只是“评估尺子完成”，不等于“质量门禁通过”。真实跨境完整候选池理论上限仍为`12/14 = 85.71%`，低于建议的90%门禁，本步没有改写该事实。

### 44.7 风险、问题与优先排查

- 排名结果异常：先核对RRF前后候选ID、Evidence和来源身份是否完全相同，再检查首个Golden名次和TopK阈值，不先怀疑模型；
- Context覆盖异常：按“Reranker Anchor是否正确 → 未来真实Repository是否重新鉴权 → Neighbor关联是否指向真实Anchor → Token预算”顺序排查；
- 失败看成0：先看`status`及失败原因，再看Schema的失败分支是否仍收到任何数值字段；不要对`None`做默认补零；
- 当前仓库仍有大量用户保留的M2-22未提交改动，本步只修改声明的目标文件，没有整理、覆盖或回退无关文件。

### 44.8 当前停止点与下一动作

M2-22.7.1已完成实现、验证和记录，现在停止。下一动作只能在用户单独授权后实施M2-22.7.2：用Fake与内存夹具建立Runner、公开安全报告和Run内评分缓存；在此之前不创建Runner，不运行真实BGE，不访问数据库或Storage。

## 45. M2-22.7.2实施记录：Fake Runner、公开报告与Run内评分缓存（2026-09-10）

### 45.1 本步解决的问题与输入输出

- 当前缺口：M2-22.7.1已经有评估配置和指标函数，但它们仍是分散的“尺子”，没有一个Runner能保证同一道题的Top5、Top8和6个Context点共享同一次评分，也没有可验证的公开报告、逐题Trace Hash或命令入口；
- 输入：冻结40题JSONL；由Golden正文和确定性干扰文本构造的Fake RRF候选；明确标记为`deterministic_fake`的Hash评分器；只在内存中把选定候选转为Anchor的Fake Context读取器；
- 输出：固定8点Runner、34条可回答结果、6条安全结果、Top5/Top8与6个Context全分母聚合、40个逐题Trace Hash及总Hash、Run内评分缓存统计、公开安全JSON报告和只允许选择TopK/输出位置的CLI；
- 为什么需要：本步先证明“评估过程本身不会重复推理、漏题、泄露正文或把Fake冒充真实质量”。如果直接接数据库和BGE，编排错误、权限错误与模型质量会混在一起，初学者也难以判断第一处故障在哪一层；
- 明确不做：Fake候选不是M2-22.6真实RRF候选；Hash分数不是BGE分数；内存Anchor不是Repository重新鉴权的Context。本步不访问PostgreSQL/pgvector/Storage，不加载BGE/Qwen/Ragas，不修改生产配置、Reranker、Context Builder、迁移或依赖。

### 45.2 Runner、缓存和报告怎样工作

```text
冻结40题JSONL
→ 为每题构造Fake候选（问题/正文只留在Runner内存）
→ RunScoringCache按完整身份取分
→ 确定性Fake Reranker（缓存未命中时才调用）
→ Top5 / Top8比较
→ 只在选定TopK运行6个Fake Context点
→ M2-22.7.1确定性指标
→ 脱敏逐题Trace + SHA-256
→ 公开安全报告 / CLI
```

1. 顺序仍为2个Reranker点加6个Context点；34条可回答题产生`34×8=272`次逻辑取分，6条安全题各取1次，总计278次；
2. 缓存键绑定query SHA-256、候选有序ID与正文SHA-256、Fake model ID/revision、max length、precision和scorer version。相同题的8点只在第一次未命中，因此34题产生238次命中；6条安全题单独取分，底层Provider总调用40次；
3. query变化、候选顺序变化、正文及其Hash变化或模型身份变化都会形成新键；Provider抛错或返回非法分数时不会写缓存，再次请求仍会调用Provider；缓存对象只存在于单次Runner调用中，不跨Run保存；
4. 可回答题的Fake Context Reader按选定TopK分别运行邻块`0/1`与预算`2000/3000/4000`六点；本步只生成Anchor，不伪造数据库Neighbor。6条安全题用允许范围最宽的`neighbor=1/token=4000`单独探测，共210次Context读取；
5. 逐题Trace保存query Hash、候选公开身份、可证明的公开Locator、RRF/Reranker名次与分数、正文Hash、Evidence映射和指标结果；不保存问题、正文、内部路径、Storage Key、tenant、owner、SQL或原始异常；
6. 每条Trace有独立SHA-256，40条有序Hash再形成总Hash。Schema重算并拒绝被篡改的逐题Hash或总Hash；相同输入、Fake身份与选定TopK会得到字节一致报告；
7. 报告固定`execution_mode=deterministic_fake`和`quality_gate_passed=None`。`run_status=completed`只表示Fake Runner执行完整，绝不表示真实BGE或真实跨境90%质量门禁通过。

### 45.3 修改文件与职责

- `app/evals/reranker_context_runner.py`：新增私有题目/候选输入、Fake评分与Context接缝、确定性Fake实现、Run内缓存、冻结数据转假候选、8点编排、34+6聚合和Trace生成；
- `app/evals/reranker_context_report.py`：新增Fake身份、公开候选Trace、可回答/安全逐题Trace、缓存统计和总报告合同，以及确定性序列化、逐题/总Trace Hash、公开报告写入；
- `scripts/run_m2_reranker_context_evaluation.py`：新增Fake-only CLI，固定读取冻结JSONL，只暴露输出位置和`selected-top-k=5/8`，不提供数据库、真实模型或范围扩展开关；
- `tests/unit/test_m2_reranker_context_runner.py`：验证40题、8点、每题最多一次Provider评分、278/238/40缓存事实、输入维度隔离、失败不缓存、候选缺失保留和重复运行确定性；
- `tests/unit/test_m2_reranker_context_report.py`：验证正文/问题/私有字段不会进入报告、Artifact Hash可复核、逐题Trace Hash篡改会被拒绝、Fake完成与质量门禁分开；
- `tests/unit/test_m2_reranker_context_cli.py`：真实运行冻结40题Fake CLI并重新解析报告，验证命令范围只有输出与选定TopK；
- `docs/PROJECT_PROGRESS.md`、`docs/progress/M2/M2_KNOWLEDGE_RAG.md`与本文：同步状态、验证基线、风险和下一动作。

### 45.4 RED、GREEN与实际验证

- RED：先新增Runner、报告和CLI测试，运行三个测试文件；收集阶段出现3个`ModuleNotFoundError: No module named 'app.evals.reranker_context_report'`，准确证明本步报告/Runner模块尚不存在；
- GREEN：完成最小实现后，三个聚焦测试文件为`8 passed in 13.40s`，格式/类型最小修正后复跑仍为`8 passed in 10.57s`；
- 相邻回归：本步8项加M2-22.7.1指标、通用评估合同、冻结数据合同和既有Retrieval Runner合同共`116 passed in 17.79s`；
- 静态与编译门禁：`ruff check app tests scripts migrations`通过；本步及直接上游8个Python文件`ruff format --check`通过；`mypy app`通过，覆盖163个源码文件；`compileall -q app scripts/run_m2_reranker_context_evaluation.py`通过；最终`git diff --check`通过，仅有Windows LF/CRLF转换提示；
- CLI测试的报告只写入pytest临时目录，本步没有在仓库保留运行报告、缓存或其他临时数据。

### 45.5 完整调用链位置

```text
前端：不经过
→ API：不经过
→ Schema：复用M2-22.7.1评估合同，新增公开报告合同
→ Agent/LangGraph：不经过
→ Harness：不经过
→ Tool：不经过
→ Service：只复用确定性Unicode Token Counter；不经过生产Retrieval/Reranker/Context Builder
→ Repository/Model：不经过
→ PostgreSQL/pgvector/Storage：不经过
→ 外部Provider：不经过；只有进程内Fake评分器和Fake Context读取器
```

本步在完整业务链旁边搭建的是“离线评估编排层”，用于先验证Runner、缓存和报告；它没有改变用户在线查询的任何生产路径。

### 45.6 能证明与不能证明

- 能证明：40题分母和8点顺序由Runner保持；同题多配置不会重复底层评分；缓存身份变化不会串用且失败不缓存；逐题Trace和报告可校验、可复现并且不序列化问题/正文/私有路径；CLI只能运行明确的Fake边界；
- 不能证明：M2-22.6真实RRF候选已经接入；当前用户、ACL、软删除和active版本会在Context阶段重新验证；真实BGE模型可加载、资源可接受或排名更好；真实Neighbor/Token裁剪与数据库清理正确；
- 质量结论：Fake报告的安全门禁True只说明空安全候选没有泄漏，不能外推到真实权限链。真实跨境理论上限仍是`12/14=85.71%`，本步没有运行或改变该指标。

### 45.7 风险、问题与优先排查

- Provider调用超过每题一次：先核对所有阶段是否共享同一个`RunScoringCache`，再检查query Hash、候选顺序/正文Hash或Fake模型身份是否在中途变化；
- 错误命中缓存：依次改变query、候选顺序、正文Hash和模型revision复现；缓存键缺任一维度都属于本层错误，不能靠清空全局缓存掩盖；
- 报告出现正文或私有信息：先检查Runner是否把私有输入对象直接塞入Pydantic报告，再检查递归字段门禁；报告只接受显式Public Trace类型；
- Trace Hash不一致：先按排序键固定的JSON重新序列化单题Trace，再核对40条Trace顺序是否与冻结Cohort一致；
- Fake结果看起来过好或过差：不要调Fake分数或把它写入质量结论；本步分数只用于验证编排分支，真实质量必须等待后续真实候选与BGE步骤。

### 45.8 当前停止点与下一动作

M2-22.7.2已完成实现、验证和记录，现在停止。下一动作只能在用户单独授权后实施M2-22.7.3：使用Fake Reranker接入真实PostgreSQL/pgvector候选、Context Repository当前权限重取和finally清理闭环；在此之前不访问真实数据库/Storage，不加载真实BGE，不运行40题正式质量矩阵。

## 46. M2-22.7.3实施记录：固定语料、真实数据库候选与Context权限重取（2026-09-10）

### 46.1 用户确认、当前缺口与本步输入输出

用户在实施前连续确认了数据生命周期：18份文档的解析和所选`compact 400/500 + overlap 100`分块一旦完成，就应作为固定语料保留；后续调整Dense/Lexical候选深度、RRF、Reranker TopK或查询侧关键词逻辑不应重新解析、切块。Embedding或文档FTS构造方式变化需要重建索引，但仍应复用原ChunkSet。只有原文、Parser输出或Chunk配置变化才需要重新切块。

本步开始时独立只读检查实际数据库为`0 ChunkSet / 0 IndexSet / 0 Chunk`，证明M2-22.6的物理评估数据已经按当时的清理方案删除，不能虚称旧Chunk仍在。因此本步输入是既有18份冻结原文、40题数据合同、所选Chunk/检索配置、Fake Embedding、Fake Reranker及现有生产Service/Repository；输出分为两部分：

1. 一个幂等固定语料准备器：语料不存在时才执行真实上传、Parser/Docling、Chunk和Index，成功后不删除；已存在时校验并复用；
2. 一个真实数据库探针：从同一数据库快照执行Dense Top10、Lexical Top10、RRF 60、生产Reranker Service + Fake Provider，再由生产Context Builder/Repository按当前权限重取。

本步没有加载真实BGE-M3或BGE-Reranker，没有运行Qwen、Ragas或40题质量矩阵，也没有修改生产Parser、Chunker、Index、Retrieval、Reranker、Context、配置、迁移或依赖。

### 46.2 固定语料与索引为什么分两层

固定语料身份`corpus_sha256`只绑定数据集版本、来源清单Hash、18份原文内容Hash及所选Chunk配置；Embedding和FTS不进入该身份。索引身份`index_sha256`另行绑定Embedding完整身份和FTS Builder版本。这样三类变化会得到不同处理：

- 只改查询深度、RRF、Reranker TopK或查询侧关键词匹配：直接查询现有IndexSet，Document、Parser Artifact、ChunkSet和IndexSet都不重建；
- 改Embedding身份或文档侧FTS Builder：DocumentIndexService在同一DocumentVersion和同一ChunkSet上新增IndexSet，旧ChunkSet不变；
- 改原文、Parser产物或Chunk配置：语料身份/ChunkSet身份变化，才允许重新解析或切块。

需要特别区分两个名字：`DocumentChunkSet`是已经切好的、保存在Storage中的Canonical Chunk Artifact；数据库`DocumentChunk`是某一IndexSet下可被pgvector/FTS查询的索引行。换Embedding会新增一代IndexSet和对应索引行，但不会重新切正文，也不会改变原ChunkSet。普通Top10/RRF/Reranker实验两者都不变。

### 46.3 修改文件与代码职责

- `app/evals/reranker_context_corpus.py`：新增幂等固定语料准备器、语料/索引/快照三层Hash、现有语料兼容性校验、同ChunkSet索引代次复用及仅限首次创建失败的精确回滚；
- `app/evals/reranker_context_runner.py`：新增真实数据库探针装配；冻结Hybrid输入必须为Dense/Lexical各depth不超过10、RRF 60和最多20条去重候选；只允许Fake Reranker进入本步，随后把结果交给真实Context Builder；
- `tests/integration/test_m2_rag_reranker_context_runner.py`：新增真实PostgreSQL/pgvector、Reranker边界、Context当前权限重取、坏来源拒绝、固定语料二次复用和“换索引不重切”集成测试；
- `docs/PROJECT_PROGRESS.md`、`docs/progress/M2/M2_KNOWLEDGE_RAG.md`与本文：同步用户确认后的数据生命周期、调用链、验证、风险和下一动作。

没有新增Runner报告CLI、数据库字段、迁移或依赖；`docs/AImianshiti.md`及其他无关工作区改动未触碰。

### 46.4 真实调用链

首次准备固定语料时：

```text
18份冻结原文
→ 公开文件上传/登记API
→ DocumentParserService（需要时走本地Docling/RapidOCR）
→ ACL夹具
→ DocumentChunkService（compact 400/500 + overlap 100）
→ DocumentIndexService + Fake Embedding
→ Storage保存原文/Parser/Chunk Artifact
→ PostgreSQL保存Document/Version/ACL/ChunkSet/IndexSet/Chunk
→ 成功后保留，不执行评估finally删除
```

同一语料的查询探针：

```text
RetrievalRequest + 当前CurrentUser
→ DenseRetrievalService（pgvector Top10）
→ LexicalRetrievalService（PostgreSQL FTS Top10）
→ HybridRetrievalService（RRF 60，去重并集最多20）
→ RerankerRetrievalService + FakeRerankerProvider（Top5/Top8边界）
→ ContextBuilderService
→ RetrievalRepository按当前tenant/ACL/软删除/active版本/active IndexSet重新取Anchor与Neighbor
→ Context Metric Segment
```

前端、公开聊天API、Agent/LangGraph、Harness和Tool不经过；首次语料摄取经过文件API，查询探针直接从评估装配层进入Service。Repository/Model、PostgreSQL/pgvector和Storage真实经过；外部Provider不经过，本地真实BGE模型也未加载。

### 46.5 RED、GREEN与实际运行证据

- 第一组RED：数据库集成测试先引用目标装配函数，收集阶段出现`ImportError: cannot import name 'build_m2_database_probe_context'`，准确证明Fake Runner尚未接通生产Reranker/Context；
- 第二组RED：固定语料测试先引用目标模块，收集阶段出现`ModuleNotFoundError: No module named 'app.evals.reranker_context_corpus'`，准确证明缺少“只建一次、后续复用”的语料边界；
- GREEN过程中测试又捕获了首次上传后DocumentVersion尚未active时无法定位来源的真实装配错误；修正为按该隔离语料的唯一DocumentVersion装配索引后，单项复跑`1 passed`；
- 最终聚焦文件为`9 passed`；它证明同配置第二次调用的Document、ChunkSet、IndexSet和Chunk UUID完全相同，另一个Embedding revision只把IndexSet总数从1增到2，Document与ChunkSet仍完全相同；
- 真实权限、检索和Context相邻集成三个文件合计`24 passed in 43.90s`；覆盖ACL撤销、软删除、active版本、active IndexSet、跨tenant、篡改正文和非Fake身份拒绝；
- Reranker/Context指标、Runner、报告、CLI及生产合同相邻单元为`72 passed in 7.50s`；既有M2检索Runner集成为`1 passed in 21.32s`；
- 工程门禁：`ruff check app tests scripts migrations`通过，3个本步目标文件格式正确，`mypy app`通过164个源码文件，`compileall -q app scripts/run_m2_reranker_context_evaluation.py`通过；tracked与本步新增文件的diff检查均无空白错误，只有Git for Windows的LF/CRLF提示。

正式固定语料首次准备结果：

- `created=True`；18 sources / 18 documents / 18 ChunkSets / 18 Fake IndexSets / 779 active Chunk rows；
- tenant ID `3288f8db-e815-442c-860a-dbb8077a1954`；
- corpus SHA-256 `70750ee64c959795e7360a80f59df9248275ecfe5ddfbfb740e290bf5cde27a3`；
- Fake索引 SHA-256 `723d41409ce14629f25c21cf8892f2136fd02030798db071269fe4b3a1a212ea`；
- 当前物理快照 SHA-256 `a165e1dbd36f2db24e943deb1066fbf64ac8035e6588f7677e086fcee89cb42c`。

紧接着第二次以相同输入调用得到`created=False`，上述tenant与三项Hash、18/18/18/779计数全部不变。再在该快照上运行`mushroom lamp voltage`小样本，得到11个Hybrid去重候选、5个Fake Reranker输出、12个Context片段、3266个项目Token和`context_supported=True`；探针前后该tenant的Chunk行均为779。

### 46.6 能证明、不能证明与风险

能证明：普通查询实验不会再次上传、解析或切块；同配置幂等复用保留完整物理身份；索引身份变化可在同一ChunkSet上新增索引代次；生产Reranker Service不会扩大Hybrid候选集；生产Context Builder不信任Reranker正文，而会重新按当前数据库权限和active代次读取；成功后的18文档固定语料实际仍存在。

不能证明：Fake Embedding的Dense质量或Fake Reranker排名代表真实BGE；固定`BAAI/bge-reranker-v2-m3`能成功加载、资源可接受或提升Top5/Top8；34条可回答题和6条安全题正式质量已经运行；真实跨境建议90%门禁已经通过。当前真实跨境候选理论上限仍是12/14=`85.71%`，本步只完成工程链，不改变该质量事实。

主要风险与排查：

- 固定语料位于当前开发评估数据库，历史集成测试中有会重建schema的测试；这类测试确实会物理删除数据，不能在固定语料创建后运行。后续先跑此类测试，再用幂等准备器检查；如果语料仍在只复用，如果已被外部schema重置才需要恢复；
- 若普通TopK/RRF实验后ChunkSet或快照Hash变化，先检查调用链是否误进`ensure_m2_reranker_context_corpus`的新建分支或生产Parser/Chunk入口，不先归因于检索参数；
- 若未来换真实BGE-M3索引，预期只新增IndexSet并复用18个ChunkSet。应先比对corpus Hash和ChunkSet ID，再检查Embedding/FTS索引身份；不得因为索引质量变化重新切块；
- 当前准备器复用了既有评估摄取私有函数；如果上游评估模块改名或数据合同升级，优先检查语料Hash、来源映射和失败回滚，不静默接受不兼容旧语料。

### 46.7 当前停止点与下一动作

M2-22.7.3已经完成实现、真实数据库验证、固定语料持久化和文档同步。现在停止，不自动进入M2-22.7.4。下一动作只能在用户单独授权后运行固定本地`BAAI/bge-reranker-v2-m3@953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e`的小样本资源探针；该步仍不运行40题正式质量矩阵、Qwen、Ragas、Agent/LangGraph、Tool、Harness或前端。

## 47. M2-22.7.4实施记录：固定本地BGE-Reranker小样本资源探针（2026-09-10）

### 47.1 本步输入、输出和为什么需要

- 输入：固定模型身份`BAAI/bge-reranker-v2-m3@953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e`、float32/CPU/batch 2/max length 8192，以及预先冻结的中文、英文、德文、表格、候选缺失、无答案6类合成样本；每类20候选，对应Dense Top10与Lexical Top10去重并集的理论最大尺寸；
- 输出：严格区分真实BGE与Fake的探针报告合同、固定身份/离线快照状态、每类20个有限分数、当前Run缓存统计、加载时间、评分p50/p95/max、RSS起点/峰值/增量、effective batch、子进程退出和安全状态；
- 为什么需要：M2-22.7.3只证明真实数据库/Context权限链，Reranker仍为Fake。在把真实BGE放进40题矩阵前，必须先用少量代表输入确认这台机器能够离线加载模型、承受最大候选池、保持候选缺失语义并正常退出，否则正式矩阵失败时无法区分模型资源问题与40题质量问题；
- 明确不做：不读取18份文档，不访问固定779个Chunk、PostgreSQL/pgvector或Storage，不执行Parser/Chunk/Index/Dense/Lexical/RRF/Context，不运行40题、Qwen、Ragas、Agent/LangGraph、Harness、Tool、API或前端，不修改生产Reranker、Context Builder、配置、迁移或依赖。

### 47.2 大白话运行过程和关键合同

```text
6类合成问题 × 每题20个短候选
→ RunScoringCache查当前运行缓存
→ 未命中时交给既有BgeRerankerProvider
→ 固定本地snapshot离线评分
→ 校验20个分数有限、顺序/身份一一对应
→ 同一池第二次请求命中缓存
→ 只把Hash、名次、耗时、RSS和安全状态写入公开报告
```

1. 模型只显式`load()`一次；6个池各调用Provider一次，共6次。每个池紧接着重复取分一次验证缓存，所以12次逻辑请求严格等于6次miss、6次hit、6个缓存项和6次Provider调用；
2. 缓存继续复用M2-22.7.2的身份键：query Hash、候选有序ID/正文Hash和完整评分器身份共同决定是否命中，不跨Run保存；本步只把评分器身份接缝从Fake扩展为固定BGE公开身份，Fake Runner仍由原有类型门禁限制；
3. 生产Provider返回`RerankerBatch`后再次按query、正文原顺序、pair key、模型身份、effective batch、raw/sigmoid有限值校验，非法数量、错序、NaN/Infinity或身份漂移均安全失败；
4. 中文、英文、德文和表格样本各有一个预期候选，可以记录其真实名次；`candidate_missing`与`no_answer`没有预期候选，报告Schema禁止它们生成候选ID或名次，无论其他干扰候选分数多高都不能冒充召回成功；
5. max length合同固定为8192并由既有Provider传入后端；本步没有制造超长文本来声称实际发生截断。原因是所选固定Chunk上限为500项目Token，正式输入远低于8192；报告因此同时记录`max_length_contract_verified=True`和`long_input_exercised=False`；
6. 报告固定`execution_mode=pinned_local_bge_probe`和`quality_gate_passed=None`，不保存query、候选正文、本机路径、PID或原始异常。完成只表示资源探针跑完，不能冒充18文档/40题质量达标。

### 47.3 修改文件与职责

- `app/evals/reranker_resource_probe.py`：新增6类私有探针输入、20候选池、固定身份校验、生产Batch适配、Run缓存复用、有限分数/安全状态、延迟/RSS/子进程测量及脱敏错误边界；
- `app/evals/reranker_context_report.py`：新增固定BGE探针身份、逐类结果、资源测量和总报告Schema，以及公开安全序列化/写入；把共享缓存统计错误文案从Fake专用改为Provider通用，计数规则不变；
- `app/evals/reranker_context_runner.py`：仅把评分接缝身份类型扩展到Fake或固定BGE探针身份；原Fake正式Runner仍显式拒绝非Fake身份；
- `scripts/run_m2_reranker_resource_probe.py`：新增必须显式`--run-real`的离线CLI，只接受输出位置，没有`--allow-download`，固定CPU/float32/batch 2/max length 8192并复用既有生产Provider；
- `tests/unit/test_m2_reranker_resource_probe.py`：覆盖6类×20候选、只评分一次、缓存复用、缺失/无答案无名次、报告不含正文、错误脱敏、快照和身份拒绝；
- `tests/unit/test_m2_reranker_resource_probe_cli.py`：验证无显式授权不能运行且CLI不存在下载开关；
- `docs/PROJECT_PROGRESS.md`、`docs/progress/M2/M2_KNOWLEDGE_RAG.md`与本文：同步状态、证据、边界、风险和下一动作；
- 未修改`app/services/retrieval/reranker_provider.py`、生产配置、Context Builder、数据库、迁移、依赖或`docs/AImianshiti.md`。

### 47.4 RED、GREEN、模型恢复与真实结果

- RED：先写两个测试文件并运行，收集阶段分别报`ModuleNotFoundError: No module named 'app.evals.reranker_resource_probe'`和`No module named 'scripts.run_m2_reranker_resource_probe'`，共2 errors in 1.58s，准确证明缺少资源探针与显式CLI；
- 最小GREEN：新增合同、探针和CLI后为`6 passed in 6.75s`；格式/类型修正后仍为`6 passed in 6.71s`；
- 相邻回归：生产BGE Provider、旧资源Benchmark、M2-22.7 Fake Runner/报告/CLI及本步共`45 passed in 15.79s`；
- 快照恢复：第一次真实CLI用错误的直接文件启动方式在导入前失败，改为项目模块启动后安全提示快照无效。只读检查确认当前`data/model-cache`仅有`bge-m3`和`docling`，目标Reranker目录确实不存在；经用户明确授权后，既有下载脚本按固定revision、无Token、单worker恢复6个运行文件，共`2,293,242,108`字节，manifest SHA-256为`c0cd30c8cb8f001454a113390ac195b15b54a2b16de4a86c8fa6ca91202e3f8b`，随后无下载模式`verify_reranker_snapshot=True`；
- 真实离线运行：设置Hugging Face/Transformers离线变量，并把HTTP/HTTPS代理指向不可用的`127.0.0.1:1`，真实探针仍完成。模型加载`26.317746s`；6个20候选池评分p50/p95/max为`4811.968/6351.987/6396.700ms`；RSS从`316.418MiB`升到`2045.113MiB`，增量`1728.695MiB`；configured/effective batch均为2；新存活子进程0；
- 真实结果：120个分数全部有限；中文、英文、德文和表格预期候选均排第1；候选缺失/无答案仍无预期ID和名次；缓存为12请求、6 miss、6 hit、6 Provider调用、6项。报告Schema round-trip和Artifact Hash复核均为True，临时报告2,933字节，SHA-256为`8732450faeeea921e6b098c71d35382d8426d946429ede0324d8d4c32cff3d1c`；记录后精确删除，不作为正式质量资产保留；
- 真实相邻Smoke：相同离线与不可用代理条件下，既有中文、英文和SKU真实Provider用例为`3 passed in 66.64s`；
- 工程门禁：本步目标文件`ruff check`与`ruff format --check`通过，4个直接源码Mypy通过，`compileall -q app scripts tests/unit`、`pip check`和`git diff --check`通过。额外运行全仓库根目录Ruff/Mypy时发现旧`agent/api/tools`原型的既有格式债，以及`prepare_m2_cross_border_eval.py`的6个既有类型/缺stub问题；这些不在本步目标文件或当前维护范围，已如实保留且未顺手修改。

### 47.5 完整调用链位置

```text
前端：不经过
→ API：不经过
→ Schema：新增固定BGE资源探针公开报告合同
→ Agent/LangGraph：不经过
→ Harness：不经过
→ Tool：不经过
→ 评估层：6类私有样本 → RunScoringCache → 探针适配器
→ Service：既有BgeRerankerProvider
→ Repository/Model：不经过业务Repository/Model；只加载本地模型权重
→ PostgreSQL/pgvector/Storage：不经过
→ 外部Provider：推理不经过；模型快照缺失时仅在用户单独授权后由既有脚本恢复，真实探针阶段强制离线
```

因此本步不是“再走一次RAG”：没有文档解析、切块、索引或检索。它只是在正式40题接线前，对Reranker这一个零件做最大候选池的承载测试。M2-22.7.3留下的18文档/18 ChunkSet/779 Chunk既没有被读取，也没有被删除或重建；它们的物理计数仍以第46节最后一次数据库验证为准，本步按范围没有为核数而额外连接数据库。

### 47.6 能证明与不能证明

能证明：固定模型/revision/精度/max length身份和manifest Hash正确；本地CPU可离线加载并处理20候选；输出数量、顺序映射和分数有限；每池一次真实评分可被当前Run复用；错误不泄露底层路径；候选缺失与无答案不会虚构名次；峰值RSS、延迟、effective batch和进程退出可记录；既有生产Provider未被本步改坏。

不能证明：真实18文档/40题RRF候选已经交给BGE；Reranker Top5还是Top8更好；34题排名Recall/MRR/nDCG是否提升；Context邻块/Token哪组更好；真实权限安全矩阵再次通过；长于8192 Token的输入实际发生了怎样的截断；并发吞吐或GPU生产性能。四个简单样本排第1也不能当成正式质量结论，报告因此保持`quality_gate_passed=None`。

### 47.7 风险与优先排查

- 快照再次缺失或Hash失败：先运行无下载复核并检查固定revision/manifest，不静默下载；只有用户明确授权才能恢复；
- 正式矩阵太慢：按本步20候选p95约6.35秒估算40题会有明显CPU耗时，先确认每题只评分一次并共享Run缓存，再检查batch是否从2因OOM降到1，不先改Chunk或扩大模型服务范围；
- RSS过高：当前峰值约2.00 GiB、增量约1.69 GiB。先看是否存在重复模型实例或未退出子进程，再考虑运行隔离/GPU；不得把异常吞成0分；
- 正式题候选缺失：先看RRF池内是否有Golden；没有就保留`candidate_missing`并归因上游召回，不能靠Reranker、邻块或删题伪造恢复；
- 报告被当成正式结论：先检查`execution_mode`和`quality_gate_passed`；只有M2-22.7.5的34+6完整分母结果才能讨论TopK/Context质量。

### 47.8 当前停止点与下一动作

M2-22.7.4已完成实现、真实固定模型离线运行、资源测量、回归和文档同步。现在停止，不自动进入M2-22.7.5。下一动作只能在用户理解并单独授权后，把第46节持久保留的18文档/40题真实候选接入固定BGE，运行Top5/Top8与所选TopK下6个Context点的正式矩阵；无论结果是否达到建议门禁，都必须保留34+6完整分母、上游候选缺失和非数值失败，不得自动修改Chunk、检索或生产配置。

## 48. M2-22.7.5实施记录：18文档/40题正式Reranker/Context矩阵（2026-09-10）

### 48.1 授权、输入、输出与为什么需要

用户在理解并确认“固定Chunk不再删除、查询参数变化不重新切块、Reranker基于上一步Top10两路融合池精排”后，单独授权实施M2-22.7.5。本步输入不是一批新文档，而是M2-22.7.3持久保留的18个Document、18个`compact 400/500 + overlap 100` ChunkSet和779个逻辑Chunk，以及M2-22.6选定的Dense Top10、Lexical Top10、RRF 60和固定本地Reranker身份。

本步要回答四个仍未知的问题：

1. 同一批Hybrid候选经过真实BGE-Reranker后，Top5/Top8分别命中多少，哪些题升排、降排、不变或在上游就缺失；
2. Top5与Top8应按冻结规则选哪一个；
3. 选定TopK后，邻块0/1与2000/3000/4000 Token六点怎样影响Golden覆盖、Anchor覆盖、冗余和Token利用率；
4. 40题、6条安全分栏、本地资源、缓存、报告和固定语料生命周期能否一起闭环。

输出是严格公开报告、逐题Trace Hash、四组聚合、Bad Case和候选建议。无论分数如何，本步都不得重切Chunk、删除难题、修改生产检索/Reranker/Context配置，或继续生成回答。

### 48.2 实现文件与职责

- `app/evals/reranker_context_formal.py`：新增真实正式矩阵装配；每道题从当前PostgreSQL/pgvector得到同一Hybrid候选，只真实评分一次，再派生Top5/Top8和六个Context点；按34题总命中选择TopK并聚合四组结果、资源、缓存、安全与Bad Case；
- `app/evals/reranker_context_report.py`：新增固定BGE正式身份、PostgreSQL Context读取身份、固定语料公开身份、资源测量、Bad Case及34+6完整正式报告合同；冻结8个顺序实验点、8行Reranker聚合、24行Context聚合、质量门禁和公开安全序列化；
- `app/evals/reranker_context_corpus.py`：新增只读Chunk身份检查和基于保留Artifact重建Golden Evidence映射；检查不会激活或切换IndexSet。真实BGE-M3索引仍只从同一ChunkSet创建，不调用Parser/Chunk；
- `scripts/run_m2_reranker_context_formal_evaluation.py`：新增必须显式`--run-real`的正式CLI，固定离线BGE-M3/BGE-Reranker、受管报告目录、报告Hash后精确删除及安全摘要；
- `tests/unit/test_m2_reranker_context_formal.py`、`test_m2_reranker_context_formal_report.py`、`test_m2_reranker_context_formal_cli.py`：覆盖Run缓存、TopK并列规则、34+6报告完整性、质量门禁、公开字段、CLI显式授权及只读Chunk身份顺序；
- `docs/PROJECT_PROGRESS.md`、`docs/progress/M2/M2_KNOWLEDGE_RAG.md`与本文：同步实际结果、调用链、验证、边界、风险和停止点；
- 未修改生产Parser、Chunker、Dense/Lexical/RRF、Reranker Provider/Service、Context Builder、Repository SQL、配置、迁移、依赖、Golden或`docs/AImianshiti.md`。

### 48.3 真实调用链与“没有重新切块”

正式运行链是：

```text
固定40题合同（34可回答 + 6安全）
→ 只读核对18 Document / 18 ChunkSet / 779逻辑Chunk身份
→ 若真实BGE-M3索引尚不存在：DocumentIndexService读取同一Chunk Artifact并新增IndexSet
→ CurrentUser + RetrievalRequest
→ DenseRetrievalService（本地BGE-M3 QUERY + pgvector Top10）
→ LexicalRetrievalService（PostgreSQL FTS Top10）
→ HybridRetrievalService（RRF 60，获权去重并集）
→ RunCachingRerankerProvider
→ 生产RerankerRetrievalService + 固定本地BGE-Reranker
→ 同一评分派生Top5与Top8；按冻结规则选Top5
→ 生产ContextBuilderService
→ RetrievalRepository按当前tenant/ACL/软删除/active版本和IndexSet重取Anchor/Neighbor
→ 六点确定性Context指标、6条安全结果、公开Trace/报告
→ 记录Hash后删除临时报告，固定语料和索引继续保留
```

首次正式运行只在18个既有ChunkSet上新增18个真实BGE-M3 IndexSet。`DocumentChunk`是“某代索引里的可搜索行”，因此Fake与真实BGE两代索引合计1558行；`DocumentChunkSet.chunk_count`之和仍是779，这才是正文实际切出的逻辑Chunk数。第二次权威运行没有重新上传、解析、切块或重算文档Embedding，只复用已落库的真实IndexSet执行40个查询和精排。

前端、公开聊天API、Agent/LangGraph、Harness、Knowledge Tool、Qwen、Ragas、最终回答和Citation均不经过；Schema、评估层、生产检索/Reranker/Context Service、Repository/Model、PostgreSQL/pgvector和本地模型真实经过。Storage只用于核对/读取既有原文与Parser/Chunk Artifact及首次同ChunkSet建真实索引，不生成新Chunk Artifact；外部Provider和网络推理不经过。

### 48.4 RED、最小GREEN与过程中捕获的生命周期问题

- RED：先新增正式Runner测试并实际运行，收集阶段报`ModuleNotFoundError: No module named 'app.evals.reranker_context_formal'`，准确证明现有Fake Runner尚没有真实40题装配；
- 最小GREEN加入正式Runner、报告与CLI后，三个新测试文件达到`8 passed`；随后补只读Chunk身份检查，正式Runner/CLI最终相关子集为`6 passed`；
- 第一轮正式运行成功建立真实BGE-M3索引并完成40题。为了扩展CLI摘要进行复跑时，旧检查路径先调用Fake语料确保器，意外把active IndexSet切回Fake并在`retained_fake_index`阶段失败。这个失败没有重切或删除Chunk，但证明“用会激活索引的确保器做只读证明”不正确；
- 最小修正是新增`inspect_m2_reranker_context_chunks`并让CLI先只读校验Document/ChunkSet/Chunk身份，再确保真实索引。最终权威复跑成功，18个active IndexSet全部为真实BGE-M3；没有为修复扩大到生产代码或配置。

### 48.5 Reranker正式结果与TopK选择

四组逐题分类和命中如下。`candidate_missing`表示正确Evidence根本不在Dense10/Lexical10的Hybrid输入池；其Reranker名次保持空值，但题目仍留在分母。

| 分组 | RRF@5 | Reranker@5 | RRF@8 | Reranker@8 | 缺失/升排/降排/不变 |
|---|---:|---:|---:|---:|---:|
| 全部可回答 | 27/34 | 31/34 | 31/34 | 31/34 | 3 / 10 / 3 / 18 |
| 真实跨境 | 9/14 | 12/14 | 12/14 | 12/14 | 2 / 5 / 1 / 6 |
| 合成跨境 | 10/10 | 10/10 | 10/10 | 10/10 | 0 / 2 / 1 / 7 |
| 通用诊断 | 8/10 | 9/10 | 9/10 | 9/10 | 1 / 3 / 1 / 5 |

冻结规则是：34题中Reranker命中更多者优先；如果Top5与Top8命中数相同，选更小的Top5，减少后续Context噪声和成本。本次两者都是31/34，所以选择Top5。这个选择没有把生产默认`reranker_top_k=8`改为5，只形成下一步需用户确认的评估候选。

### 48.6 Context六点、计算方法与候选取舍

三个指标继续使用M2-22.7.1冻结定义：

- 总Golden覆盖率 = Context所有片段覆盖到的不同Golden Evidence数 / 该题应有Golden数；
- Anchor覆盖率 = 只看Reranker选中的锚点Chunk覆盖到的Golden数 / 应有Golden数，邻块命中不能算成精排成功；
- 冗余率 = Context最终有序片段中没有带来任何新增Golden Evidence的片段数 / 总片段数；Token利用率 = 实际项目Token / 允许预算。空Context是成功的数值0，计算失败则这些比率保持`None`，本次24个分组聚合均为`completed`。

全部34题结果：

| 邻块 | Token预算 | 总覆盖 | Anchor覆盖 | 冗余率 | Token利用率 |
|---:|---:|---:|---:|---:|---:|
| 0 | 2000 | 31/34 `.9118` | 31/34 `.9118` | `.8176` | `.5784` |
| 0 | 3000 | 31/34 `.9118` | 31/34 `.9118` | `.8176` | `.3856` |
| 0 | 4000 | 31/34 `.9118` | 31/34 `.9118` | `.8176` | `.2892` |
| 1 | 2000 | 31/34 `.9118` | 31/34 `.9118` | `.8885` | `.7378` |
| 1 | 3000 | 32/34 `.9412` | 31/34 `.9118` | `.9062` | `.6604` |
| 1 | 4000 | 32/34 `.9412` | 31/34 `.9118` | `.9135` | `.5556` |

邻块1+3000与邻块1+4000达到相同最高总覆盖32/34；3000预算更小、冗余更低且预算利用更充分，因此记录“Top5 + neighbor 1 + 3000 Token”为后续候选。它不是生产配置变更，也不是质量门禁通过：Anchor仍只有31/34，且真实跨境Reranker仍是12/14。

三个最终Bad Case均保留：

- `smoke-syn-011-scan-batch`：上游候选缺失，邻块1/4000仍没有Golden；
- `smoke-ext-029-return-invalidation`：上游候选缺失，邻块1/4000仍没有Golden；
- `smoke-ext-031-zh-responsible-person`：上游候选缺失且Reranker Anchor仍未命中，但邻块1在3000/4000预算碰巧补到Golden，所以只能算Context总覆盖增加，不能说Reranker恢复。

### 48.7 安全、缓存、资源、报告与最终基线

- 6条安全题按2条ACL、2条版本、1条无Evidence、1条unknown完整保留，6/6完成，安全泄漏0；34条可回答题也全部保留，候选映射失败0；
- 正式运行共有74次逻辑评分请求：34题各请求Top5/Top8两次，加6条安全题各一次。每个可回答题第二次请求复用同一候选池分数，所以34次hit；40个非空池各调用真实Provider一次，得到40次miss、40次Provider调用和40个Run内缓存项。六个Context点直接复用选定Top5结果，不重复运行Reranker；
- 权威运行ID为`m2-2275-bf6b85f51b24909f`。总耗时`771.9230233s`，模型加载`24.8247664s`，评分p50/p95/max为`18076.2463/28578.5696/29613.4833ms`；effective batch最小/最大均为2；RSS从`978.1367MiB`升到`3681.2734MiB`，增量`2703.1367MiB`；
- 固定语料Hash为`70750ee64c959795e7360a80f59df9248275ecfe5ddfbfb740e290bf5cde27a3`，真实BGE索引Hash为`f62217ba7a2a0e490f60e788778272fc14f12605aa5625dfbb70a391b3121dfe`，快照Hash为`556a1831d3b05befdb8006bc494eb1328926ec12e3687eb6a6b3fc7c2109acbf`；Trace Set SHA-256为`5cf23c03d3ece573652d63aa07d2d0356a89dc48239e8296bd4ac63d2de523e3`；
- 临时正式报告596,026字节，SHA-256为`b62d4c674653c32ed2541fe97bc4f2cb0a7357997c97b75f08e9becb33d09804`，记录摘要后精确删除。真实资源测量会随运行变化，所以完整报告Hash不要求跨运行相同；逐题确定性逻辑由Trace Set Hash表达；
- 三套幂等Seed入口全部重跑成功。最终只读数据库为固定语料18 files / 18 documents / 18 versions / 39 ACL / 18 ChunkSets / 36 IndexSets，ChunkSet逻辑总数779，18个active代次全部为真实BGE-M3；全库另含两组正式Seed，因此files/documents/versions各28。Storage为64个对象：28 uploads / 18 parsed / 18 chunks；M1德国仓可售库存仍为`150-20-5=125`。

### 48.8 验证、能证明、不能证明、风险与停止点

- 最终聚焦与相邻单元共`172 passed in 12.22s`；排除会另建临时Parser/Chunk语料的用例后，相邻真实PostgreSQL/pgvector/Reranker/Context权限集成为`8 passed, 1 deselected in 15.33s`，测试后固定身份仍为18/18/779且Hash不变；
- 显式开启固定本地BGE-Reranker Smoke为`3 passed in 58.73s`；默认未开开关的首次命令得到3 skipped，只表示测试保护开关生效，不是模型失败；
- `ruff check app tests scripts migrations`与19个相关文件格式检查通过；`mypy app`通过166个源码文件，10个直接源码Mypy通过；`compileall -q app tests scripts migrations`、`pip check`和最终`git diff --check`通过；
- 能证明：固定Chunk被复用且没有重切；真实BGE-M3检索、固定BGE-Reranker、生产Context权限重取和34+6报告链完整运行；Top5在同一候选池把@5从27/34升到31/34；邻块1+3000提高总Context覆盖但没有改变Anchor；安全零泄漏；缓存确实没有为六个Context点重复推理；评估完成与质量失败可以同时如实表达；
- 不能证明：真实跨境已经达到90%门禁；Reranker能修复3个上游候选缺失；邻块补到的题已经可生成正确且忠实的最终回答；建议Context候选应立即成为生产默认；CPU延迟/RSS适合并发生产；Qwen回答、Ragas生成指标、Citation、Knowledge Tool、Harness、Agent/LangGraph、API或前端已经验证；
- 主要风险：真实文本评分p95约28.58秒且峰值RSS约3.60GiB，明显高于短探针；先查真实Chunk长度、CPU和批处理，不改Chunk掩盖资源问题。固定语料仍位于开发数据库，后续会重建schema的旧测试可能物理删除它；必须先识别这类测试，确需运行后再用幂等准备器只在缺失时恢复。召回修复必须从两个真实跨境缺失和一个诊断缺失的Dense/Lexical候选入手，不能靠Reranker或邻块伪装；
- 停止点：M2-22.7五个小步至此完成，`evaluation_completed=True`、安全门禁True、`quality_gate_passed=False`。当前停止并向用户解释指标；下一动作只能由用户单独决定/授权召回修复。未经新授权不得修改生产检索/配置、重切Chunk、进入M2-22.8、运行Qwen/Ragas回答评估或继续Agent/前端。

## 49. M2-22.7漏召回只读原因诊断（2026-09-10）

### 49.1 授权、输入、输出与目的

用户在理解“Reranker只能重排已经进入候选池的Chunk”后，授权先检查三条`candidate_missing`的具体原因，不授权修复。本次输入仍是M2-22.7.5保留的18份Document、18个`compact 400/500 + overlap 100` ChunkSet、779个逻辑Chunk、真实BGE-M3 active IndexSet，以及三道失败问题和人工Golden Evidence。输出不是新索引或新参数，而是每题的以下只读证据：

1. 正确原文是否仍完整存在于既定Chunk；
2. 真实Dense与Lexical在更深观察窗口中的名次；
3. 正式depth 10之外，depth 20/30/50是否能让完整Golden进入RRF候选；
4. 排在前面的干扰内容是什么，以及失败应归因于跨语言词法、语义混淆、文档内定位还是切块。

这一步之所以需要，是为了先区分“答案在仓库中但搜索没拿到”和“答案在解析/切块时已经丢失”。二者的修法完全不同：前者应改查询或召回策略，后者才可能需要重新处理文档。本次诊断明确禁止上传、解析、重切、修改生产depth/RRF、运行Reranker/Context/回答链或生成正式报告。

### 49.2 实际只读调用链

```text
三道失败问题 + 固定Golden Evidence
→ 只读核对18 Document / 18 ChunkSet / 779逻辑Chunk及语料Hash
→ 从现有真实BGE-M3 active IndexSet读取同一批DocumentChunk
→ BGE-M3只生成三条查询向量
→ DenseRetrievalService临时观察Top100
→ LexicalRetrievalService临时观察Top100
→ 诊断代码分别按route depth 10/20/30/50/100重算RRF 60
→ 对照Golden Chunk、同文档Chunk和前列干扰Chunk
→ 再次只读核对语料身份
```

前端、API、Schema、Agent/LangGraph、Harness、Tool、生产Reranker、Context Builder、最终回答、Citation、Qwen和Ragas均不经过。Service、Repository/Model、PostgreSQL/pgvector与本地BGE-M3查询Embedding真实经过；Storage不读写。诊断为取得现有语料快照调用了既有幂等确保入口，但强制检查`created=False`，且前后计数与Hash完全相同，没有创建文档、ChunkSet或IndexSet。

### 49.3 三道题的共同结果

| 题目 | 完整Golden所在Chunk | Dense名次/相似度 | Lexical名次 | depth 20/30 | depth 50的RRF名次 |
|---|---|---:|---:|---|---:|
| `smoke-syn-011-scan-batch` | `2c889299-66ba-5696-846a-c2cdf6164049` | 33 / `.527909` | 缺失 | 均缺失 | 39 |
| `smoke-ext-029-return-invalidation` | `4291db91-fb58-5ade-bdfa-37818ce0d9e6` | 42 / `.546187` | 缺失 | 均缺失 | 50 |
| `smoke-ext-031-zh-responsible-person` | `e69ddb37-c3f8-5866-bc56-a5e1177e8020` | 39 / `.525650` | 缺失 | 均缺失 | 52 |

三条完整Golden都能在既定Chunk正文中逐字找到，Locator映射也存在，因此不是Parser漏字，也不是Chunker删掉了答案。三条问题都是中文，而完整Golden Chunk是英文；PostgreSQL FTS得到的中文查询词项与对应英文Chunk词项交集均为空，所以Lexical即使把观察深度提高到100也找不到完整Golden。它返回的是带有“批次、退货、申报、产品”等中文通用词的其他Chunk。

Dense能跨语言理解大致意思，但完整Golden分别只排33、42、39。正式每路depth 10自然拿不到；把观察深度提高到20或30仍然一条也补不进来。depth 50虽然终于包含它们，但融合后的RRF仍仅排39、50、52，离后续Top5/Top8很远，还会显著增加Reranker CPU成本与噪声。因此本次数据不支持把“直接将Top10改成Top50”当作有效修复。

### 49.4 每道题为什么被压后

1. `smoke-syn-011-scan-batch`问“扫描入库单的批次号是什么”，正确Chunk完整保存`BATCH: BATCH-SCAN-42`。但它是只有46个项目Token的英文OCR票据，中文Lexical没有桥梁；Dense前3名是另一份欧盟低价值货物文档中的交易标识、托运/运输编号和进口代码，后面还有中文批次质检片段。模型识别到“某种编号/批次”的语义，却没有足够线索把英文OCR票据排到前10。
2. `smoke-ext-029-return-invalidation`问远程销售退货导致自由流通申报失效的90日期限和退回地址。正确英文法律段落完整保存在目标文档第4页Chunk中。Dense前4名主要是另一份内容高度相似的低价值货物海关文档，目标文档其他“退货/失效”相关Chunk也排在5、25、27、29、30名；完整同时包含“90天+原供应商或指定地址”的Golden被相似法律段落压到42名。这是跨语言之外的近似法律条款竞争和单文档内精确段落定位问题。
3. `smoke-ext-031-zh-responsible-person`不是“连正确文档都没找到”。GPSR正确文档的其他Chunk已在Dense第1至3名；第3名从重叠边界的`ble person in the EU...`开始，已经含有“欧盟责任人”和“作为消费者及市场监管机构联络点”的核心答案后半段。正式Golden严格映射到包含整段原文的前一Chunk，所以该完整Chunk记为Dense第39、Anchor候选缺失；Context的邻块1正是从已选中的同文档Chunk向前补到完整Golden，解释了为何总Context覆盖由31/34变为32/34。这是文档已经召回、局部段落选择与严格Golden口径共同造成的特殊失败，不应解释成重新切块的理由。

### 49.5 修改文件与验证结果

- 生产代码、测试、Schema、配置、迁移、依赖、Golden、Chunk Artifact和数据库内容均未修改；
- 只更新`docs/PROJECT_PROGRESS.md`、`docs/progress/M2/M2_KNOWLEDGE_RAG.md`与本文，记录结论、边界和下一动作；
- 临时只读诊断脚本仅用于本次检查，完成后已从`tmp/`精确删除，没有把一次性排查代码留入仓库；
- 两次诊断运行均退出0。运行前后固定语料都是18 Document / 18 ChunkSet / 779逻辑Chunk，语料SHA-256均为`70750ee64c959795e7360a80f59df9248275ecfe5ddfbfb740e290bf5cde27a3`，快照确保结果为`created=False`；
- 本次是只读诊断，没有生产实现缺口，因此RED/GREEN不适用；验证依据是三题真实检索名次、Golden正文核对、同文档/干扰Chunk对照，以及前后语料身份不变。文档修改完成后另运行Markdown结构检查、`git diff --check`和目标文件diff复核。

### 49.6 能证明、不能证明与风险

能证明：三道题的答案没有在解析或切块时丢失；Lexical对这三组中英问题/证据缺少词法桥梁；Dense召回了相近主题但完整Evidence排序过低；depth 20/30不能解决；GPSR题已命中正确文档并由Context邻块补到完整Golden；Reranker没有拿到三条完整Golden，所以不能为这三条完整Golden负责。

不能证明：所有未来漏召回都由跨语言造成；查询翻译、同义词扩展、文档路由、父子检索或其他策略哪一种一定最好；GPSR的部分Chunk是否应在正式Golden口径中算“足以回答”；任一修复已经让真实跨境达到90%。这些都需要独立冻结实验合同后再测，不能在诊断阶段凭观察改口径或生产参数。

主要风险与排查顺序：

- 先改Chunk会破坏已经通过的34/34内容与Locator基线，而且本次证据不支持这样做；
- 只加深到50会把大量噪声和CPU成本交给Reranker，且三条完整Golden在RRF仍远离Top8；
- 查询扩展若无边界，可能加入错误翻译并降低其他31题召回；后续必须在完整34题分母上做基线/候选对照；
- GPSR题若直接放宽Golden，会把评估规则改成迎合结果；应先独立判断“部分Chunk是否事实充分”，同时继续保留完整Golden与Anchor/Neighbor分栏。

### 49.7 当前停止点与下一动作

本次只读原因诊断已经完成并停止。当前结论是“保留现有Chunk，修复方向在查询到候选的召回层”；但尚未授权任何修复。下一动作只能在用户理解并确认后，另行提出一个小范围召回实验方案，优先比较有边界的中英查询扩展/翻译和正确文档内二次定位，并用完整34+6分母验证。未经新授权不得修改生产检索、配置或Chunk，不得自动把depth改到50、重新运行Reranker正式矩阵或进入M2-22.8。

