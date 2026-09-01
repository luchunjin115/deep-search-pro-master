# M2-17：BGE-Reranker 二次精排

> 本文件保存从迁移前单文件中拆出的完整历史方案、实施日志与验证证据。
> 当前状态和阅读入口见 [M2入口](../M2_KNOWLEDGE_RAG.md)。

### 2026-09-01｜M2-17-PLAN｜获权Hybrid候选的BGE二次精排

**状态：已完成；M2-17.1至M2-17.5均已完成并验证，等待M2-18方案确认。**

### 1. 当前现状和缺少的能力

M2-16已经能从同一权限安全门产生最多30条Hybrid候选，并保存Dense、Lexical和RRF原始分数，但最终顺序只反映两张检索榜单的名次，不会把“问题和每一段正文”放在一起逐段复审。当前`Settings`虽预留`reranker_backend=fake`、`BAAI/bge-reranker-v2-m3`、batch size 2和top 8，却没有Reranker输入/输出合同、Provider、Service、固定真实revision、缓存manifest、类型化错误、质量基准或显式Smoke；本地`data/model-cache`也只有BGE-M3和Docling，没有Reranker权重。

大白话说，Hybrid像初筛员，已经从有权限的资料中挑出30段；M2-17要增加一名复审员，把“用户问题+每一段候选正文”成对阅读，再把最相关的8段排到前面。复审员没有数据库钥匙，只能重排或丢弃初筛结果，不能自己补入一段新资料。

### 2. 本阶段目标

1. 冻结Reranker请求、模型身份、有限分数、原始Hybrid名次/分数保留和最终连续排名合同；
2. 建立硬件无关Provider协议与确定性Fake，日常单元/集成测试不加载、不下载、不联网；
3. 实现Reranker Service，只接收服务端构造的`RetrievalResponse(mode="hybrid")`，输出最多8条严格子集；
4. 固定真实模型为`BAAI/bge-reranker-v2-m3@953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e`，建立本地snapshot manifest、文件Hash、强制离线加载、设备与资源基准；
5. 在正式合成候选上比较RRF与Reranker的Recall@8、MRR、延迟和内存，保留逐问题前后排名，不用主观印象宣称提升；
6. 验收后精确恢复正式Seed，并记录M2-17能证明和不能证明的边界。

### 3. 明确不做

- 不修改M2-16 tenant、ACL、active Version/Index Set或软删除安全门；
- 不让Reranker接收HTTP请求传入的任意Chunk、tenant、Top K、模型名或revision；
- 不重新查询PostgreSQL、不生成Embedding、不修改Index Set/Chunk或新增数据库迁移；若实现中发现必须迁移，立即停止说明；
- 不实现Context Builder、邻块补全、Evidence、引用验证、Qwen回答、`search_knowledge` Tool、Agent、前端或HTTP检索API；
- 不实现检索模式路由，也不把模型选择权交给大模型；
- 不承诺线程内模型推理的硬中断超时。若未来必须强杀卡死推理，需要独立进程/推理服务，不能用一个无法终止的线程伪装；
- 不在M2-17.1至M2-17.3自动下载约2.29 GB真实权重；下载和真实运行只在M2-17.4单独确认后进行。

### 4. 前置条件与固定决定

1. 保留当前`main`及HEAD/origin `9c805e683a422477c675e828b2eedbb775f9cf1d`，保护M2-16.3至M2-16.7累计未提交工作，不reset、不覆盖；
2. 正式Seed继续保持10/10/10/9、10 parse/index pending、0 active/Chunk Set/Index Set/Chunk/Embedding，日常测试默认Fake和local-only；
3. Reranker输入最多是服务端`hybrid_candidate_count=30`，输出默认`reranker_top_k=8`；调用者不能改这两个值；
4. 相同Reranker分数按原Hybrid rank、再按Chunk UUID稳定打破平局；输出保留原Dense/Lexical/RRF分解，新增Reranker身份、有限原始分数、0至1 sigmoid归一化分数和Reranker rank。归一化分数不是业务概率，不据此编造置信度；
5. 空Hybrid候选直接返回合法空结果且不加载Provider；Provider失败整体返回类型化安全错误，不把未精排Hybrid伪装成Reranker成功；
6. 真实模型只从固定本地snapshot加载，`trust_remote_code=False`，离线变量强制开启；模型卡说明其输入是query/passage并输出相关性分数，项目继续使用已确认的多语言`bge-reranker-v2-m3`。

### 5. 按顺序实施的小步骤

##### M2-17.1｜冻结合同、配置和安全错误

- 输入：现有`RetrievalRequest`和`RetrievalResponse(mode="hybrid")`；
- 输出：Reranker身份、分数分解、最终结果/响应、Provider不可用与内部失败的固定安全错误；
- 预计文件：修改`app/schemas/retrieval.py`、`app/core/config.py`、`.env.example`、`app/services/retrieval/errors.py`、公共导出和`tests/unit/test_reranker_contracts.py`、`tests/unit/test_m2_baseline.py`；
- TDD：先证明合同/错误不存在而RED，再覆盖额外字段、NaN/Infinity、非法rank/top-k、浮动真实revision、敏感路径/原始异常和Hybrid事实保留；
- 停止点：只定义边界，不实现Provider或模型加载。

##### M2-17.2｜Provider协议与确定性Fake

- 输入：一个有界query和按原顺序排列的候选正文；
- 输出：数量、顺序和身份可核对的有限Reranker分数批次；
- 预计文件：新增`app/services/retrieval/reranker_provider.py`、`tests/unit/test_reranker_provider.py`，修改包导出；
- TDD：覆盖空白/超长query、空/超量候选、数量或顺序错位、非有限分数、稳定Fake、并发首次加载边界和安全错误；
- 停止点：日常能力仍为Fake，不下载真实模型。

##### M2-17.3｜只重排获权Hybrid子集的Service

- 输入：可信用户、原始query和服务端Hybrid响应；
- 输出：最多8条Reranked结果；
- 预计文件：新增`app/services/retrieval/reranker.py`、`tests/unit/test_reranker.py`、`tests/integration/test_reranked_retrieval.py`，修改公共导出和阶段哨兵；
- TDD：覆盖重排、稳定同分、top 8、空候选不调用Provider、Provider失败、重复/错身份/篡改事实拒绝，以及输出Chunk集合必须是Hybrid输入严格子集；真实PostgreSQL集成链继续证明无权候选无法被重新引入；
- 停止点：完成Fake生产编排，不下载真实模型、不做RAG。

##### M2-17.4｜固定离线BGE-Reranker与资源基准

- 前置：用户单独确认约2.29 GB下载、当前磁盘和网络；若连接失败先探测本机实际VPN代理端口，不照抄旧电脑端口；
- 预计文件：扩展Provider真实后端，新增`scripts/download_m2_reranker.py`、`scripts/benchmark_m2_reranker.py`、`tests/smoke/test_bge_reranker_smoke.py`及snapshot manifest；
- 验证：固定revision与逐文件SHA-256、local-only离线复跑、中英文/SKU正负对排序、CPU/GPU能力探测、加载时间、单批/p50/p95、峰值RSS、batch 2遇OOM降为1、第三方异常脱敏；
- 停止点：只证明模型Provider与小型语义Smoke，不自动跑正式10文档验收。

##### M2-17.5｜正式质量对比、全量门禁和阶段收口

- 预计文件：新增`scripts/verify_m2_reranker.py`、`tests/unit/test_m2_reranker_verification.py`，按需新增显式Smoke并更新两份进度文档；
- 验证：正式18条当前可检索Golden证据逐题保存RRF rank与Reranker rank，计算Recall@8和MRR前后变化；记录两条上游不可检索图文DOCX事实而不归咎于Reranker。Fake负责日常确定性闭环，真实BGE只显式离线运行；完成聚焦/相关/后端全量、Ruff、Mypy、compileall、pip check、Alembic check和`git diff --check`；
- 清理：只用既有幂等Seed入口恢复并逐项复核10/10/10/9、0索引数据、Storage 10 uploads、M1可售125；
- 停止点：M2-17完成后等待M2-18 Context/Evidence方案确认，不自动继续。

### 6. 完整调用链位置

M2-17实际链路为：`内部调用者 → RetrievalRequest Schema → HybridRetrievalService → Dense + Lexical → M2-16共享Repository安全门 → PostgreSQL → RRF Hybrid候选 → RerankerService → Fake或本地BGE-Reranker Provider → RerankedResponse`。

本阶段经过内部Schema、现有检索Service、Reranker Service和本地模型Provider；安全候选的产生仍经过Repository、Model和PostgreSQL。Reranker自身不访问数据库。整个阶段不经过前端、HTTP API、Context Builder、Evidence、Qwen、Tool、Agent或模式路由。

### 7. 阶段完成标准

1. Reranker输出严格是获权Hybrid候选的子集，身份、正文、来源和原始三路分数不可篡改；
2. Fake日常测试稳定且不加载/下载/联网，真实模型固定revision、manifest和本地离线边界；
3. top 8、有限分数、稳定tie-break、空输入、批量降级和失败脱敏均有自动测试；
4. 正式可检索Golden记录RRF与Reranker的Recall@8、MRR、逐题排名和实际资源/延迟，指标如实报告；
5. 相关与后端全量没有新增失败，工程质量门通过，正式Seed精确恢复；
6. 没有新增迁移，也没有实现M2-18及以后能力。

### 8. 主要风险和优先排查

- Reranker排错：先核对输入是否真是同一query与完整候选正文、输出数量/顺序映射和sigmoid方向，再查模型，不先调RRF；
- 权限泄露：先检查Service是否只接受内部Hybrid响应以及结果是否做身份/事实子集核对；Reranker不得自行查库或接收客户端候选；
- 真实模型下载/缓存：先核对固定revision、manifest、约2.29 GB空间、实际代理端口和local-only，禁止运行时偷偷联网；
- CPU慢或内存高：先记录加载与推理解耦指标、batch 2/1和候选长度；未做进程隔离时不能声称能硬中断卡死模型；
- 指标下降：保存逐问题前后rank，区分上游候选缺失、表格正文序列化、截断和真实相关性判断，不通过删除难例美化平均值；
- 两条图文DOCX仍缺失：Reranker只能重排已有候选，无法恢复Parser从未提取的图片文字，这是明确上游边界。

### 9. 确认与当前停止点

用户回复“开始下一步”后，按仓库规则先完成只读检查并提交本方案；随后明确回复“确认M2-17方案，开始M2-17.1”。该确认只授权按小步骤实施M2-17，不能视为自动授权后续RAG。M2-17.1与M2-17.2分别完成后，用户均再次回复“开始下一步”，因此M2-17.3获单步授权；M2-17.3完成并提前披露约2.29 GB下载成本后，用户再次回复“开始下一步”，因此M2-17.4获单步授权；随后用户明确要求清理失败缓存并“清理完后开始下一步”，因此M2-17.5正式质量对比与收口也获授权。**M2-17现已完成并验证，当前停止；M2-18仍需提交并确认独立阶段方案。**

### 2026-09-01｜M2-17.1｜Reranker合同、固定配置与安全错误

**状态：已完成；已验证；明确停止在M2-17.1。**

1. 本步解决的问题：M2-16的公开合同只能表达Dense、Lexical和Hybrid/RRF结果，无法表达“哪一个Reranker、用什么revision和精度、给每条Hybrid候选多少原始/归一化分数、原Hybrid名次是什么、最终名次是什么”。配置虽有浮动`main`和模型名占位，但真实后端只拒绝`main`，不能拒绝换成其他模型或关闭local-only；本步冻结这些边界，防止后续Provider和Service各自发明字段或使用浮动模型；
2. 大白话运行过程：Hybrid初筛结果仍保留原文、来源、Dense/Lexical分数和RRF分数；新合同只在外面加“原来排第几、复审原始分、sigmoid归一化分、复审后第几”。响应最多8条，名次必须从1连续；相同分数未来按原Hybrid名次和Chunk UUID稳定排序。合同明确归一化分数只是便于比较的0至1数值，不是业务概率；
3. 输入与输出：本步的上游输入概念是服务端构造的`RetrievalResponse(mode="hybrid")`，但尚未实现实际调用；输出合同是`RerankedRetrievalResponse`，包含Embedding/FTS/RRF身份、Reranker身份、输入候选数、服务端top-k和最多8条`RerankedRetrievalResult`。请求体没有新增candidate、tenant、Top K、模型、revision或路径字段；
4. 合同决定：`RetrievalRerankerIdentity`保存contract version、provider、model/revision、max length、precision及固定`sigmoid`变换；`RetrievalRerankerScore`拒绝NaN/Infinity、非正rank、0至1范围外值及与原始分不一致的sigmoid值；响应拒绝不连续final rank、score rank错位、重复/越界Hybrid rank、超过top-k、丢失RRF分数及违反分数降序/稳定tie-break的结果；
5. 配置决定：新增常量`BAAI/bge-reranker-v2-m3@953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e`，默认仍是Fake，但模型和revision也固定为同一逻辑目标；新增严格8192 max length和float32默认精度。未来`reranker_backend=bge`时，模型/revision任一不匹配或`MODEL_LOCAL_FILES_ONLY=false`均在启动配置阶段拒绝；本步没有检查/创建缓存，也没有下载权重；
6. 安全错误：新增`RetrievalRerankerProviderUnavailableError`，公开固定`PROVIDER_ERROR`、可重试且不含原始异常。后续Provider可用异常链保留内部诊断，但公开Detail不会带query/passage、CUDA错误、token、缓存路径或密钥；未知合同/编排问题继续使用既有`RetrievalInternalError`；
7. 实际修改文件与职责：
   - `app/core/config.py`：固定Reranker模型/revision，新增max length/precision并收紧真实后端身份与local-only校验；
   - `.env.example`：同步固定revision、8192长度和float32示例，默认仍为Fake；
   - `app/schemas/retrieval.py`：新增Reranker身份、分数、Reranked结果/响应及跨字段排序/数量门禁；
   - `app/services/retrieval/errors.py`与`app/services/retrieval/__init__.py`：新增并导出脱敏Reranker Provider错误；
   - `tests/unit/test_reranker_contracts.py`：覆盖合法形状、分数、sigmoid、名次、稳定顺序、top 8、Hybrid事实保留、敏感额外字段、固定配置和错误脱敏；
   - `tests/unit/test_m2_baseline.py`：加入新环境键和固定默认值，并推进阶段哨兵，继续断言Provider、Service和HTTP API不存在；
   - 两份进度文档：记录确认、TDD、验证、风险、Seed与停止点；
8. 完整调用链位置：当前只到`已有Hybrid RetrievalResponse → M2-17.1 Reranker Schema/配置/安全错误`。经过内部Schema与集中Settings，不经过Reranker Provider/Service、Repository、Model、PostgreSQL、Storage、真实模型、前端、HTTP API、Context、Evidence、Qwen、Tool或Agent；
9. TDD RED证据：先新增合同测试和阶段哨兵，再运行`.venv\Scripts\python.exe -m pytest tests/unit/test_reranker_contracts.py tests/unit/test_m2_baseline.py -q`；测试收集立即因`ImportError: cannot import name 'BGE_RERANKER_MODEL_ID' from app.core.config`失败，准确证明缺失的是本步固定配置/合同，而不是数据库或模型；
10. TDD GREEN证据：最小实现后首次为`2 failed, 58 passed`，两项都只是测试正则大小写及字段级Pydantic错误先于自定义错误，非法数据实际已被拒绝；修正测试对文案的过度绑定后为`60 passed in 1.92s`。连同M2-16原检索合同为`94 passed`，包含Dense/Lexical/Hybrid/共享权限/FTS的相关回归为`153 passed in 6.41s`；
11. 后端全量：原样运行为`625 passed, 2 skipped, 1 failed in 49.32s`。唯一失败仍是既有`test_parse_failure_marks_first_index_failed_without_creating_index_set`固定删除`uploads/2026/08/...`，而当前9月夹具写入`2026/09`，未触发预期解析失败；本步未越权修改。排除该已知用例后为`625 passed, 2 skipped, 1 deselected in 48.88s`；
12. 工程质量：`ruff check app tests scripts migrations`通过；`ruff format --check app tests scripts migrations`为`217 files already formatted`；Mypy为`Success: no issues found in 109 source files`；`compileall -q app tests scripts`无错误；`pip check`无损坏依赖；`git diff --check`通过；Alembic current/heads均为`20260831_0008 (head)`且`alembic check`无新操作，因此本步没有迁移；
13. 能证明与不能证明：能证明Reranker公开身份/分数/排名可以严格表达，非法浮点、错误sigmoid、错误排名/数量/顺序、敏感额外字段、浮动或错误真实模型身份和在线模式会被拒绝，且M2-16已有合同/检索没有回归。不能证明Provider产生真实分数、Fake确定性、模型加载、OOM batch降级、Hybrid子集安全重排、真实BGE语义提升、延迟或内存；这些属于M2-17.2至M2-17.5；
14. 风险与优先排查：合同校验失败先区分单项分数字段与响应跨字段门禁；sigmoid不一致先核对是否误把归一化值当raw logit或重复sigmoid；真实配置启动失败先核对完整revision、固定model、8192/precision和local-only。未来Service必须逐字段复制Hybrid事实并验证子集，不能只凭Chunk ID重新查库；
15. 正式Seed与停止点：全量测试后只运行既有`seed_m1 → seed_m2_files → seed_m2_complex_files`恢复。只读复核为10 files、10 documents、10 versions、9 ACL、10 parse pending、10 index pending、0 active Version/Index Set、0 Chunk Set/Index Set/Chunk/Embedding；Storage为10 uploads、0 parsed、0 chunks、0其他；M1可售125；PostgreSQL 17.11 + pgvector 0.8.6 healthy。M2-17.1现已完成，明确没有Provider、Service、模型缓存/下载或M2-17.2及后续能力，等待用户确认。

### 2026-09-01｜M2-17.2｜Provider协议与确定性Fake

**状态：已完成；已验证；明确停止在M2-17.2。**

1. 本步解决的问题：M2-17.1只有公开响应合同，还没有一个可替换、可测试的“问题+候选正文→相关性分数”能力；若后续Service直接依赖某个模型库，就无法用Fake做日常测试，也难以发现模型少返回一项、调换顺序、返回NaN/Infinity或身份漂移。本步建立唯一Provider边界，让Fake与未来本地BGE必须交付同一种可核对批次；
2. 大白话运行过程：调用方交给Provider一个问题和一排正文。Fake不理解语义，也不会访问网络，而是对每个“问题+正文”做固定SHA-256运算，生成稳定raw分数并做一次sigmoid。每项还带一个只含Hash的`pair_key`，它同时绑定问题、正文、模型身份和原位置；校验器重新计算这些键，因此少一项、多一项、交换两项或把分数贴错正文都会整体失败；
3. 输入与输出：输入query必须是1至2000字符的非空字符串，passages必须是1至100项的非空字符串序列，每项最多100000字符；输出是不可变`RerankerBatch`，包含同数量、同顺序的`RerankerPairScore`、固定`RerankerIdentity`和有效batch大小。调用者不能通过这里传tenant、ACL、Top K、模型、revision或Chunk身份；
4. Provider合同：`RerankerProvider`只暴露`identity`与`score(query, passages)`；`validate_reranker_batch`核对精确身份、数量、逐项顺序键、batch范围、raw/normalized均为有限实数、normalized处于0至1且严格等于raw的sigmoid。批次、身份和单项分数均为冻结dataclass，避免返回后被原地篡改；
5. Fake决定：身份固定为`m2-reranker-provider-v1 / fake / fake/m2-reranker-deterministic / m2-fake-reranker-v1 / 8192 / float32 / sigmoid`；测试冻结一组中文/SKU Golden Hash和raw分数，跨实例、重复调用及32次并发首次使用结果一致。Fake无加载阶段，因此本步能证明并发首次使用无共享可变状态；未来真实模型“只构造一次”的并发懒加载仍属于M2-17.4；
6. 安全错误：新增内部`RerankerInputError`，只暴露固定校验消息及`query`或`passages`字段；新增内部`RerankerProviderError`，只暴露固定`PROVIDER_ERROR`消息与retryable标记，不回显问题、正文、模型路径、CUDA或第三方原始异常。M2-17.3再负责把内部Provider错误映射到M2-17.1公开检索错误；
7. 实际修改文件与职责：
   - `app/services/retrieval/reranker_provider.py`：定义Provider协议、身份/分数/批次、pair key、输入与输出校验及确定性Fake；
   - `app/core/errors.py`：新增Provider层输入错误和脱敏执行错误；
   - `app/services/retrieval/__init__.py`：统一导出新Provider公共能力，供后续Service依赖注入；
   - `tests/unit/test_reranker_provider.py`：覆盖确定性/Golden、身份、顺序绑定、边界输入、数量/顺序/身份错位、NaN/Infinity/错误sigmoid、不可变、并发首次使用、错误脱敏及无模型/网络依赖；
   - `tests/unit/test_m2_baseline.py`：阶段哨兵推进到Provider存在，同时继续断言Reranker Service和HTTP检索API不存在；
   - 两份进度文档：同步本步结果、验证、Seed、风险和停止点；
8. 完整调用链位置：当前只到`未来Reranker Service → RerankerProvider协议 → FakeRerankerProvider`。本步经过Service层内部Provider模块和M2-17.1 Schema身份兼容检查；不调用现有Hybrid Service，不经过Repository、Model、PostgreSQL、Storage、前端、HTTP API、Context/Evidence、Qwen、Tool、Agent或真实模型；
9. TDD RED证据：先新增`tests/unit/test_reranker_provider.py`并推进基线哨兵，再运行`.venv\Scripts\python.exe -m pytest tests/unit/test_reranker_provider.py tests/unit/test_m2_baseline.py -q`；收集阶段立即因`ImportError: cannot import name 'RerankerInputError' from app.core.errors`失败，准确证明缺失的是本步Provider/错误能力，不是数据库、Seed或模型；
10. TDD GREEN证据：最小实现后同一命令为`81 passed in 1.91s`；补充固定Golden后，Provider+M2-17.1合同+阶段哨兵为`93 passed`。包含Embedding、Dense、Lexical、Hybrid/RRF、共享Repository权限和检索验收的相关回归为`205 passed`；
11. 后端全量：原样`.venv\Scripts\python.exe -m pytest -q`为`658 passed, 7 skipped, 1 failed`；唯一失败仍是既有`test_parse_failure_marks_first_index_failed_without_creating_index_set`硬编码删除`uploads/2026/08/...`，当前9月文件实际在`2026/09`，未触发预期解析失败，本步未越权修改。跳过显式真实模型Smoke并排除该已知用例后为`658 passed, 2 skipped, 1 deselected`；
12. 工程质量：`ruff check app tests scripts migrations`通过；`ruff format --check app tests scripts migrations`为`219 files already formatted`；`mypy app`为`Success: no issues found in 110 source files`，本步3份测试单独Mypy通过；`compileall -q app tests scripts migrations`无错误；`pip check`无损坏依赖；`git diff --check`通过。Alembic current/heads均为`20260831_0008 (head)`且`alembic check`无新操作，因此本步没有迁移；
13. 能证明与不能证明：能证明有界问题/正文可以稳定产生数量和顺序一一对应的有限Fake分数，身份/原位置/正文错配、非法浮点、错误sigmoid、可变返回对象及日常测试引入真实模型/联网依赖会被测试发现；也能证明M2-16检索链无新增回归。不能证明Fake分数有语义质量，不能证明Reranker Service只重排获权Hybrid子集，也不能证明真实BGE加载、截断、OOM batch降级、质量、延迟或内存；分别留给M2-17.3至M2-17.5；
14. 风险与优先排查：未来Service若报批次错位，先比较输入候选数量与逐位置`pair_key`，再查Provider，不要先改排序；若公开Schema身份不兼容，先核对contract/provider/model/revision/max length/precision/sigmoid；Fake顺序变化先检查Golden是否因合同算法被误改。`pair_key`只能证明输入映射完整，不能替代M2-17.3对Chunk身份、正文、来源和原Hybrid分数的严格子集核对；
15. 正式Seed与停止点：全量后仅运行既有`seed_m1 → seed_m2_files → seed_m2_complex_files`恢复。只读复核为10 files、10 documents、10 versions、9 ACL、10 parse pending、10 index pending、0 active Version/Index Set、0 Chunk Set/Index Set/Chunk/Embedding；Storage为10 uploads、0 parsed、0 chunks、0其他；M1 `LR-TL-MUSH-OR01`在`DE-FRA`可售125；PostgreSQL 17.11 + pgvector 0.8.6容器healthy。M2-17.2已完成，明确没有创建`reranker.py`、没有Reranker Service、真实BGE后端、模型缓存/加载/下载、HTTP API或M2-17.3，等待用户确认。

### 2026-09-01｜M2-17.3｜只重排获权Hybrid子集的Service

**状态：已完成；已验证；明确停止在M2-17.3。**

1. 本步解决的问题：M2-17.2的Provider只能对query和正文打分，还没有安全入口取得候选、把分数贴回正确Chunk、稳定截取top 8或保留Hybrid证据。如果让调用者直接提交候选，或者只按数组位置盲贴分数，无ACL内容、旧正文或错位分数就可能混入结果。本步把候选来源固定为服务端Hybrid Service，并在重排前后重复核对边界；
2. 大白话运行过程：Reranker Service先拿可信`CurrentUser`和问题调用现有Hybrid，得到已经过tenant/ACL/active-ready安全门的候选；随后只把问题和这些候选的有序正文交给Provider。Provider返回分数后，Service重新验收每张“分数回执”，按分数从高到低排列，同分保留原Hybrid先后，再取最多8条。新结果逐字段复制原Chunk，Provider没有字段可以新增或改写文档；
3. 输入与输出：公开方法输入仍是可信`CurrentUser`与严格`RetrievalRequest`，候选不属于调用者输入；依赖是内部`HybridRetrievalRoute`和`RerankerProvider`。输出为`RerankedRetrievalResponse`，记录原候选数、服务端top-k、Embedding/FTS/RRF/Reranker身份、原Hybrid rank、新rank及完整原始事实；
4. 安全子集边界：Service拒绝非Hybrid模式、缺失身份/RRF、非连续rank、重复Chunk、同Document混合Version/Index Set以及通过`model_copy`绕过Schema的非法正文；再次调用`validate_reranker_batch`核对Provider身份、数量、顺序、pair key、有限raw和sigmoid。输出只能遍历`zip(hybrid.results, batch.scores, strict=True)`构造，因此没有从请求、Provider或数据库外部补入Chunk的路径；
5. 排序与top-k：全部Hybrid候选先评分，再按`normalized_score`降序、原Hybrid rank升序、Chunk UUID升序稳定排序，最后应用固定5至8范围内的服务端top-k，默认8；调用者请求中没有top-k字段。空Hybrid结果直接返回合法空响应但仍保留全部检索/Provider身份，且不调用Provider；
6. 错误边界：内部Provider输入不一致视为编排错误并映射`RetrievalInternalError`；`RerankerProviderError`或批次校验失败映射M2-17.1固定`RetrievalRerankerProviderUnavailableError`，不回显query、正文、CUDA或路径。Hybrid自身的权限、数据库、Embedding等类型化错误继续原样向上，不伪装成精排成功；
7. 实际修改文件与职责：
   - `app/services/retrieval/reranker.py`：新增可信Hybrid依赖协议、Service编排、Hybrid重验、空响应、稳定排序、top 8和安全错误映射；
   - `app/services/retrieval/__init__.py`：统一导出`RerankerRetrievalService`；
   - `tests/unit/test_reranker.py`：覆盖真实调用次序、全事实保留、重排/同分/top 8、空候选、Provider失败、数量/顺序/身份/正文绑定篡改、非法Hybrid及服务端top-k；
   - `tests/integration/test_reranked_retrieval.py`：复用真实PostgreSQL Dense+Lexical+Hybrid链，确认无ACL Chunk不会被Reranker重新引入；
   - `tests/unit/test_m2_baseline.py`：阶段哨兵推进到Service存在，继续断言HTTP API不存在；
   - 两份进度文档：同步验证、风险、Seed和M2-17.4需单独授权的停止点；
8. 完整调用链位置：`CurrentUser + RetrievalRequest → RerankerRetrievalService → HybridRetrievalService → Dense + Lexical → M2-16共享Repository安全门 → Model/PostgreSQL → 获权RRF候选 → RerankerProvider(Fake) → RerankedRetrievalResponse`。Service本身不直接访问Repository、Model、PostgreSQL或Storage；整个步骤不经过前端、HTTP API、Context/Evidence、Qwen、Tool、Agent或模式路由；
9. TDD RED证据：先新增单元/集成测试并推进阶段哨兵，再运行`.venv\Scripts\python.exe -m pytest tests/unit/test_reranker.py tests/integration/test_reranked_retrieval.py tests/unit/test_m2_baseline.py -q`；两份测试均在收集阶段因`ModuleNotFoundError: No module named 'app.services.retrieval.reranker'`失败，准确证明缺失的是本步Service，而不是数据库或模型；
10. TDD GREEN证据：最小实现后同一命令为`64 passed in 2.67s`；加入M2-17.1合同和M2-17.2 Provider回归后为`108 passed`；包含Embedding、Dense、Lexical、Hybrid/RRF、共享Repository权限及验收的相关回归为`220 passed in 8.73s`；
11. 后端全量：原样`.venv\Scripts\python.exe -m pytest -q`为`673 passed, 7 skipped, 1 failed in 52.76s`；唯一失败仍是既有跨月硬编码用例删除`uploads/2026/08/...`而当前真实夹具写入`2026/09`，本步未越权修改。跳过显式真实模型Smoke并排除该用例后为`673 passed, 2 skipped, 1 deselected in 52.01s`；
12. 工程质量：`ruff check app tests scripts migrations`通过；`ruff format --check app tests scripts migrations`为`222 files already formatted`；`mypy app`为`Success: no issues found in 111 source files`，本步3文件单独Mypy通过；`compileall -q app tests scripts migrations`、`pip check`和`git diff --check`通过。Alembic current/heads均为`20260831_0008 (head)`且`alembic check`无新操作，因此本步没有迁移；
13. 能证明与不能证明：能证明生产形状的Fake编排只从同一可信用户的Hybrid结果取候选，先完整评分再top 8，输出Chunk集合不会超出输入集合，身份/正文/来源/Dense/Lexical/RRF不会被Provider改写，错位或恶意分数批次失败；真实PostgreSQL证明无ACL Chunk在整链仍不可见。不能证明Fake具有语义质量，也不能证明真实BGE的snapshot、加载、截断、OOM降级、延迟、内存或质量提升；这些属于M2-17.4/17.5；
14. 风险与优先排查：若结果事实变化，先比较输出`hybrid_rank`对应的原Hybrid对象，禁止重新查库拼装；若Provider不可用，先核对候选数量、逐位置pair key和身份，再查真实模型；若无权限内容出现，优先排查M2-16共享候选边界和Hybrid输入，Reranker没有数据库读取或候选注入接口。Python线程无法硬中断卡死模型的边界仍未改变，真实推理隔离需在后续按实测决定；
15. 正式Seed与停止点：全量后仅运行既有`seed_m1 → seed_m2_files → seed_m2_complex_files`恢复。只读复核为10 files、10 documents、10 versions、9 ACL、10 parse pending、10 index pending、0 active Version/Index Set、0 Chunk Set/Index Set/Chunk/Embedding；Storage为10 uploads、0 parsed、0 chunks、0其他；M1 `LR-TL-MUSH-OR01`在`DE-FRA`可售125；PostgreSQL 17.11 + pgvector 0.8.6容器healthy。M2-17.3已完成，明确没有真实BGE后端、模型缓存/加载/下载、HTTP API、RAG或M2-17.4；后者涉及约2.29 GB下载，等待用户单独确认。

### 2026-09-01｜M2-17.4｜固定离线BGE-Reranker与资源基准

**状态：已完成；已验证；明确停止在M2-17.4。**

1. 本步解决的问题：M2-17.3只有确定性Fake，无法证明固定真实模型能从本地安全加载、逐对输出可用分数、在当前机器承受多少时间和内存，也没有可审计的模型文件Hash。用户回复“开始下一步”后，已按此前披露的约2.29 GB成本实施M2-17.4；
2. 大白话运行过程：下载器先把固定revision的六个运行文件放进专用本地货架，再给每个文件登记大小和SHA-256“指纹”。真实Provider每次启动先逐文件验指纹，第一次打分时才在锁内加载一次模型；它把问题和正文成对交给BGE，按原顺序取回raw分数并转成sigmoid分数。若batch 2发生内存不足，只缩到batch 1重试；普通错误不会触发盲目重试，也不会把正文、路径或第三方异常泄露出去；
3. 输入与输出：输入继续是M2-17.2冻结的有界`query + passages`，不含tenant、ACL、Chunk、Top K、模型或路径；输出仍是同一`RerankerBatch`与固定身份，因此M2-17.3 Service可在Fake和真实Provider之间切换，不需要复制权限或重排逻辑；
4. 固定快照：模型为`BAAI/bge-reranker-v2-m3@953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e`，运行文件总计`2,293,242,108`字节。manifest登记`config.json`、`model.safetensors`、`sentencepiece.bpe.model`、`special_tokens_map.json`、`tokenizer.json`、`tokenizer_config.json`的大小与SHA-256；其中`model.safetensors`为`2,271,071,852`字节，SHA-256为`d9e3e081faff1eefb84019509b2f5558fd74c1a05a2c7db22f74174fcedb5286`；
5. 下载现场：首次官方客户端直连停滞；只读监听检查确认当前电脑`fcclientCore`实际监听`127.0.0.1:7892`，直连15秒超时而该现场端口约6.13秒返回HTTP 200，之后只在下载进程内使用此代理，没有写入项目或永久环境。重试留下两个不在manifest内的`.incomplete`分片和一个空lock，共约1.89 GiB；M2-17.5开始前已处理Windows长路径限制，精确删除2,034,237,440字节分片及空lock，最终临时文件为0且正式snapshot复验通过；
6. Provider边界：`BgeRerankerProvider`只允许固定model/revision、`max_length=8192`、batch 1至16和cpu/cuda/auto；CPU强制float32，CUDA按配置支持float16/bfloat16。模型懒加载受锁保护，`HF_HUB_OFFLINE=1`与`TRANSFORMERS_OFFLINE=1`在加载前设置，使用本地路径、`trust_remote_code=False`且不让第三方做额外normalize；分数数量、顺序、有限性和pair key仍由公共合同复核；
7. 实际修改文件与职责：
   - `app/services/retrieval/reranker_provider.py`：新增真实Provider、snapshot校验、设备/精度选择、并发懒加载、OOM batch降级、数组兼容和脱敏错误；
   - `app/services/retrieval/__init__.py`：导出真实Provider及工厂/快照校验入口；
   - `scripts/download_m2_reranker.py`：只在显式`--allow-download`时联网下载固定运行文件，原子生成manifest；已有完整快照时只做离线Hash复核；
   - `scripts/benchmark_m2_reranker.py`：使用固定合成中英/SKU语料记录匿名机器标签、环境、加载时间、p50/p95、RSS/GPU和实际排序分数；报告写入被Git忽略的`output/m2_reranker_benchmarks/`；
   - `tests/unit/test_bge_reranker_provider.py`：覆盖懒加载并发、设备/精度、snapshot篡改、批次、OOM 2→1、非OOM不重试、身份、数组返回及错误脱敏；
   - `tests/unit/test_m2_reranker_benchmark.py`：覆盖显式下载授权、manifest、损坏恢复、匿名标签、报告结构与写入；
   - `tests/smoke/test_bge_reranker_smoke.py`：显式开关下真实验证中文、英文和SKU正段分数高于负段；
   - `tests/unit/test_m2_baseline.py`：阶段哨兵推进到M2-17.4文件存在；既有M2-17.2无真实模型日常导入测试改为AST检查“没有顶层急加载”，允许真实实现只在调用时延迟导入；
   - 两份进度文档：同步真实资源、验证、风险、Seed和停止点；
8. 完整调用链位置：本步直接链路是`RerankerRetrievalService（既有） → RerankerProvider协议 → BgeRerankerProvider → 固定本地snapshot → RerankerBatch → RerankerRetrievalService`。完整生产链仍是`CurrentUser + RetrievalRequest → Hybrid → Dense + Lexical → 共享Repository安全门 → Model/PostgreSQL → RRF获权候选 → Reranker Service → 本地BGE Provider → RerankedResponse`。本步自身不访问Repository、Model、PostgreSQL或Storage，也不经过前端、HTTP API、Context/Evidence、Qwen、Tool、Agent或模式路由；
9. TDD RED证据：先新增真实Provider、基准和Smoke测试并推进阶段哨兵，运行`.venv\Scripts\python.exe -m pytest tests/unit/test_bge_reranker_provider.py tests/unit/test_m2_reranker_benchmark.py tests/smoke/test_bge_reranker_smoke.py tests/unit/test_m2_baseline.py -q`；收集阶段因`ImportError: cannot import name 'BGE_RERANKER_REQUIRED_FILES'`及缺少`BgeRerankerProvider`失败，准确证明缺失的是M2-17.4真实Provider/快照能力；
10. TDD GREEN证据：最小实现、批次修正和懒导入哨兵更新后，本步Fake/注入测试为`113 passed, 3 skipped`；最终包含Reranker合同、Fake、Service、真实Provider、基准、集成和阶段哨兵的聚焦集合为`139 passed, 3 skipped in 5.15s`。三个跳过项只由显式真实Smoke开关控制；
11. 真实Smoke与离线证明：设置`RUN_BGE_RERANKER_SMOKE=1`、Hugging Face/Transformers离线变量，并把HTTP/HTTPS代理临时指向不可用的`127.0.0.1:1`后，`tests/smoke/test_bge_reranker_smoke.py`仍为`3 passed in 14.56s`；中文、英文和SKU三组均为相关正文raw分数高于无关正文，证明这次推理只用本地快照；
12. 实际资源基准：匿名标签`local-a`、Windows、Python 3.11.9、16物理/24逻辑CPU、约31.84 GiB RAM、CPU版Torch 2.13.0，无CUDA；batch 2、6个pair、5轮。模型加载`7.037724 s`，整组p50/p95为`0.545183/0.670579 s`，RSS从326.9 MiB升至峰值2055.1 MiB，增量1728.2 MiB。中文raw为`1.989568 > -11.037552`、英文`4.742977 > -11.041710`、SKU`5.168136 > -10.021044`，三组排序均通过；
13. 后端全量：原样`.venv\Scripts\python.exe -m pytest -q`为`704 passed, 10 skipped, 1 failed in 51.18s`；唯一失败仍是既有`test_parse_failure_marks_first_index_failed_without_creating_index_set`，测试把待删除上传Key硬编码为`2026/08`，而当前9月夹具写入另一Key，因此没有触发预期解析失败；它与本步无关且未越权修改。排除显式Smoke和该已知用例后为`704 passed, 2 skipped, 1 deselected in 50.26s`；
14. 工程质量：`ruff check app tests scripts migrations`通过；修正下载器唯一格式差异后，`ruff format --check`覆盖227文件；`mypy app`加本步脚本/测试为`Success: no issues found in 116 source files`；`compileall -q app scripts tests migrations`、`pip check`、`git diff --check`通过。Alembic current/heads均为`20260831_0008 (head)`且`alembic check`无新操作，因此本步没有迁移；
15. 能证明与不能证明：能证明当前机器上的固定文件未被篡改、真实模型可强制离线加载，中英/SKU小样本方向正确，加载/单组推理/RSS已如实记录，并发只构造一次、OOM batch缩小、普通错误不重试和异常脱敏由注入测试覆盖；日常默认仍为Fake，不会加载/下载/联网。不能证明正式18条Golden的Recall@8/MRR提升、百万Chunk或并发吞吐、GPU精度/显存、超长文本语义质量、操作系统级硬超时，也不能把三个小样本排序当作RAG最终质量；
16. 风险与优先排查：快照不可用先运行无下载模式校验并核对manifest/文件Hash，不先重下；模型加载失败先核对固定revision、local-only、Torch设备和精度；内存不足先看实际effective batch是否从2降到1，再决定是否需要进程隔离，不能把非OOM吞成降级成功；排序方向异常先核对query/passage顺序、raw分数和sigmoid，不先修改RRF。CPU基准单批约0.55至0.67秒且峰值RSS约2.01 GiB，后续端到端延迟需要M2-17.5按正式候选数量实测；
17. 正式Seed与停止点：全量后只运行既有`seed_m1 → seed_m2_files → seed_m2_complex_files`恢复。只读事务复核为10 files、10 documents、10 document_versions、9 document_acl、10 parse pending、10 index pending、0 active Document Version、0 active Index Set、0 document_chunk_sets、0 document_index_sets、0 document_chunks、0 Embedding；Storage精确为10 uploads、0 parsed、0 chunks、0其他对象；`LR-TL-MUSH-OR01 / DE-FRA`可售125；PostgreSQL 17.11、pgvector 0.8.6且容器healthy；Alembic current/heads均为`20260831_0008 (head)`。M2-17.4已完成，明确没有运行正式10文档质量对比，也没有开始M2-17.5、RAG、API、Agent、前端或模式路由，等待用户确认。

### 2026-09-01｜M2-17.5｜正式质量对比、全量门禁和阶段收口

**状态：已完成；已验证；M2-17已收口，明确没有开始M2-18。**

1. 本步解决的问题：M2-17.4只能证明真实模型能加载和区分三组小样本，不能回答“在项目正式10文档、20个问题上，Reranker是否真的把正确证据拉进top 8”。本步新增可重复验收器，固定比较同一批获权Hybrid/RRF候选与真实BGE重排结果，不通过临时删难题或换分母美化指标；
2. 大白话运行过程：先用现有正式入口解析、切块并以Fake Embedding建立10文档/35 Chunk索引；每个问题先经过完整Hybrid安全链得到RRF榜单，再把这张已经获权的榜单冻结后交给现有Reranker Service和固定本地BGE。验收器在同一证据探针上分别找RRF和精排后的第一名次，最后恢复全部临时索引和Storage对象；
3. 固定计分边界：20题全部保存在报告中；固定`visual_quality_notice:1/2`两条图文DOCX图片文字为`upstream_image_text_not_extracted`，只记录、不计分，且两条在本轮RRF和Reranker中都确实没有证据。其余18题必须全部在原Hybrid最多30条候选中存在证据，否则完成门禁失败；Recall@8与MRR@8使用完全相同18题分母，rank大于8或缺失均按0计；
4. 质量结果：RRF为14/18命中，Recall@8=`0.777778`、MRR@8=`0.318056`；BGE-Reranker为18/18，Recall@8=`1.0`、MRR@8=`0.898148`，分别提升`0.222222`和`0.580092`。RRF top8漏掉的`quality_inspection_sop:1`（原20→1）、`supplier_quotes:1`（9→2）、`scanned_receiving_ticket:1`（10→1）和`:2`（22→2）全部被拉回；18题中16题证据排第1、1题排第2、1题排第6；
5. 延迟与资源结果：20题每题约15个获权候选、CPU batch 2。Hybrid p50/p95为`40.842/48.503 ms`；真实Reranker p50/p95为`6701.876/7242.196 ms`，端到端为`6745.311/7283.693 ms`，首题冷精排`7242.196 ms`。进程RSS在正式查询前已含索引/Docling状态，为1498.3 MiB，峰值2793.2 MiB，查询阶段增量1294.9 MiB；
6. 延迟结论：本轮能证明真实精排质量显著提升，也同样证明当前CPU同步逐题精排约6.7至7.2秒，不能描述为低延迟可用。报告中的`recommended_retrieval_order=reranker`只表示质量排序优于RRF，不代表生产部署决策；后续优先评估减少送入Reranker的候选数、GPU/独立推理服务、缓存和是否需要确定性路由。本步按用户此前决定不实现模式路由；
7. 缓存清理：开始前确认没有Reranker/Hugging Face下载进程，只针对固定snapshot的`.cache/huggingface/download`处理失败残留。第一次普通API删除只移除了空lock；两个分片因Windows传统260字符路径限制未删除。随后在同一PowerShell内验证目标仍位于精确目录，并用Windows长路径前缀删除2个分片共`2,034,237,440`字节；最终`.incomplete/.lock=0`，无下载模式再次逐文件SHA-256验证正式snapshot通过；
8. 实际修改文件与职责：
   - `scripts/verify_m2_reranker.py`：新增显式`--run-real`正式验收、固定排除清单、同候选RRF/Reranker逐题排名、Recall@8/MRR@8复算门禁、CPU延迟/RSS记录、安全CLI错误和finally恢复；
   - `tests/unit/test_m2_reranker_verification.py`：覆盖固定18题分母、top8指标、模型身份、固定排除项、逐题数量、诚实指标复算、延迟有限性和Seed恢复门禁；
   - `tests/unit/test_m2_baseline.py`：阶段哨兵推进到M2-17.5验收脚本/测试存在，同时继续断言HTTP检索API不存在；
   - `output/m2_reranker_verification.json`：Git忽略的本机真实报告，保存20题逐项排名、质量、延迟、资源、清理和阶段判定；
   - 两份进度文档：同步缓存清理、质量/延迟、TDD、全量、Seed、边界和M2-17收口；
9. 完整调用链位置：`显式验收CLI → 正式Seed/DocumentIndexService → Parser/Chunk/Storage + Fake Embedding → Document/Version/Index Set/Chunk Model → PostgreSQL → RetrievalRequest → HybridRetrievalService → Dense + Lexical → M2-16共享Repository安全门 → RRF候选 → 冻结同一获权响应 → RerankerRetrievalService → 固定本地BGE-Reranker → RerankedResponse → 质量/资源报告 → 精确清理`。不经过前端、HTTP API、Context Builder、Evidence、引用验证、Qwen、Tool、Agent或模式路由；
10. TDD RED证据：先新增验收判定/指标测试并推进阶段哨兵，再运行`.venv\Scripts\python.exe -m pytest tests/unit/test_m2_reranker_verification.py tests/unit/test_m2_baseline.py -q`；结果为`4 failed, 48 passed`，四个失败都因`ModuleNotFoundError: No module named 'scripts.verify_m2_reranker'`或目标文件不存在，准确证明缺失的是M2-17.5验收能力；
11. TDD GREEN证据：实现最小验收器并修正完整报告夹具后，同一聚焦命令为`52 passed in 1.96s`；包含Reranker合同、Fake/真实Provider、Service、基准、正式验证、真实PostgreSQL权限集成和阶段哨兵的M2-17集合为`142 passed, 3 skipped in 5.51s`，3个跳过仍仅是默认关闭的真实Smoke；
12. 真实强制离线证据：正式命令同时设置`HF_HUB_OFFLINE=1`、`TRANSFORMERS_OFFLINE=1`，并把HTTP/HTTPS代理指向不可用`127.0.0.1:1`；仍成功完成Docling本地解析、Fake索引、固定本地BGE-Reranker 20题推理、报告和清理，`decision.m2_17_complete=true`。日常默认复核仍为`reranker_backend=fake`和`model_local_files_only=True`；
13. 后端全量：原样`.venv\Scripts\python.exe -m pytest -q`为`707 passed, 10 skipped, 1 failed in 51.15s`；唯一失败仍是既有`test_parse_failure_marks_first_index_failed_without_creating_index_set`硬编码删除`2026/08`上传Key，而9月夹具使用另一Key，与本步无关且未越权修改。排除显式Smoke和该已知用例后为`707 passed, 2 skipped, 1 deselected in 51.53s`；
14. 工程质量：全仓`ruff check app tests scripts migrations`通过，`ruff format --check`为229文件已格式化；`mypy app`加本步脚本/测试/阶段哨兵为`Success: no issues found in 114 source files`；`compileall -q app scripts tests migrations`、`pip check`和`git diff --check`通过。Alembic current/heads均为`20260831_0008 (head)`，`alembic check`无新操作，因此本步没有迁移；
15. 能证明与不能证明：能证明固定真实BGE在当前正式合成语料的18条可检索事实上，将top8证据覆盖从14提升到18并显著提高MRR；逐题排名、固定难例、同候选输入、强制离线、资源和清理可审计，且Reranker仍只能重排获权Hybrid子集。不能证明自然用户问题、生产文档、并发/GPU、百万Chunk、端到端HTTP、Context/Evidence、最终回答/引用或生产SLA；20题小集合也不能消除过拟合与语料偏差；
16. 风险与优先排查：质量回归先比较逐题`rrf_first_evidence_rank`与`reranker_first_evidence_rank`，再核对query/passage和模型revision；延迟优先看候选数与长度、CPU/GPU和batch，不先牺牲权限门或偷偷删难题；无权内容出现先查M2-16共享Repository和Hybrid输入，Reranker没有数据库补候选接口；图片两题需在后续多模态/解析增强解决，不能归因于Reranker；Python线程仍不能硬终止卡死推理，生产隔离需独立设计；
17. 正式Seed与停止点：全量后只运行既有`seed_m1 → seed_m2_files → seed_m2_complex_files`恢复。只读事务最终为10 files、10 documents、10 document_versions、9 document_acl、10 parse pending、10 index pending、0 active Document Version、0 active Index Set、0 document_chunk_sets、0 document_index_sets、0 document_chunks、0 Embedding；Storage精确10 uploads、0 parsed、0 chunks、0其他对象；`LR-TL-MUSH-OR01 / DE-FRA`可售125；PostgreSQL 17.11、pgvector 0.8.6且容器healthy；Reranker临时下载文件为0且snapshot复验通过。M2-17已完成并收口，明确没有开始M2-18、Context/Evidence、RAG回答、API、Agent、前端或模式路由，等待用户确认下一阶段方案。
