# M2-16：权限前置的混合检索

> 本文件保存从迁移前单文件中拆出的完整历史方案、实施日志与验证证据。
> 当前状态和阅读入口见 [M2入口](../M2_KNOWLEDGE_RAG.md)。

### 2026-08-31｜M2-16-PLAN｜权限前置的混合检索闭环

**状态：已完成；M2-16.1至M2-16.7均已完成并验证。2026-08-31范围修订把原路线图中分散在M2-16至M2-18的Dense、Lexical和RRF合并为当前M2-16内部小步骤；第7节已同步为同一套有效编号。用户对M2-16的确认不授权新M2-17 Reranker、RAG或任何后续阶段。**

### 1. 当前现状和真正缺少的能力

M2-15已经能把文档解析、分块、生成Embedding并写入`document_chunks`。数据库也已经有`search_vector`的GIN索引和`embedding vector(1024)`的HNSW余弦索引。但是系统现在只会“把书放上书架”，还不会根据用户问题“从书架找出有权限阅读的几页”。现有应用没有search、lexical、dense、hybrid、RRF、rerank或RAG路由；`app/services/retrieval/`只有Embedding Provider。

当前`fts_text`直接保存原始`retrieval_text`，版本为`m2-fts-raw-retrieval-v1`。英文可依靠空格分词，连续中文用PostgreSQL `simple`配置时可能无法按“亮度”等子词命中。因此，中文关键词检索必须在文档入库和用户查询两边使用同一套、固定版本的jieba分词规则。只给查询分词不能修复已经按整段中文建立的旧词条。

当前访问规则为：同租户内文档owner、`company_owner`，或命中user/role/market ACL的用户可读；`access_level`目前不额外赋予tenant全员读取权。检索继续复用这一规则，不在M2-16偷偷改变业务权限。

### 2. M2-16目标

1. Lexical Retrieval（关键词检索）：用版本化中文分词和PostgreSQL FTS找出字面命中的Chunk；
2. Dense Retrieval（语义检索）：把用户问题按`QUERY`用途生成BGE-M3或Fake向量，再用pgvector余弦距离找出意思接近的Chunk；
3. Hybrid Retrieval（混合检索）：同时取得两路候选，不让单一检索方式决定全部结果；
4. RRF（按两个候选榜单名次稳定融合）：按`1 / (k + rank)`合并名次，默认`k=60`，不直接相加量纲不同的FTS分数和余弦分数；
5. 在SQL候选集合中固定tenant、Document ACL、市场、active Document Version、active ready Index Set、未软删除和完整Embedding身份过滤；
6. 返回可以解释和复算的来源定位、两路原始排名/分数、RRF分数、模型revision和FTS builder版本。

### 3. 本阶段明确不做

- 不实现BGE Reranker；
- 不调用Qwen生成答案，不实现RAG答案、引用或Evidence持久化；
- 不接入聊天、LangGraph、Agent Tool或Harness；
- 不新增前端检索页面；
- 默认不新增临时HTTP搜索路由，先以内部Service和真实PostgreSQL集成测试证明稳定合同；
- 不实现后台队列、Worker、租约、分布式任务、MCP、真实Amazon SP-API；
- 不自动开始M2-17或后续工作。

### 4. 前置条件与已确认决策

- Git保持`main`和基线提交`5c20cf2`；保留现有3个未提交修改，不提交、不回退；
- PostgreSQL 17.11、pgvector 0.8.6保持healthy，Alembic为`20260831_0007 (head)`；
- 固定真实模型为`BAAI/bge-m3@5617a9f61b028005a4858fdac845db406aefb181`，日常测试默认使用Fake；
- 2026-08-31已幂等恢复正式Seed，实际计数为10 files、10 documents、10 document_versions、9 document_acl，0 Chunk Set、0 Index Set、0 Chunk、0 active指针；这证明后续可以从正式干净基线启动索引，不证明检索已经可用；
- Dense查询Embedding失败时返回安全、可重试的检索失败，不悄悄降级成关键词结果；否则调用者会误把“不完整混合检索”当成完整成功；
- M2-16的“可审计”是响应中保留可复算的身份、排名、分数和来源，不新增Retrieval Run/Evidence数据库表；持久化审计留给后续Context/Evidence阶段。

### 5. 数据流

```text
可信RunContext中的tenant/user/role/market
                    + 用户query
                           |
             先建立同一份获权active候选边界
                           |
        +------------------+------------------+
        |                                     |
        v                                     v
jieba同版分词 -> PostgreSQL FTS       QUERY用途 -> EmbeddingProvider
        |                                     |
 Lexical top-30                      pgvector cosine top-30
        |                                     |
        +------------------+------------------+
                           v
                 按chunk_id去重并执行RRF
                           v
       返回final rank、两路分数分解和Source Locator
```

文档侧在索引时使用`DOCUMENT`用途生成并保存Embedding；查询侧使用`QUERY`用途临时生成查询向量。Fake Provider只证明调用、维度和确定性，不证明语义好坏；固定向量集成测试证明pgvector排序；显式本地BGE Smoke才证明真实语义模型能接入查询链。

### 6. 权限与数据隔离策略

Repository的Dense和Lexical查询必须复用同一个基础获权条件，且在排序和`LIMIT`之前应用：

1. `tenant_id`等于可信RunContext，不接受请求体传入tenant；
2. Document和StoredFile都未软删除，文件状态可用；
3. `documents.active_version_id`等于当前Chunk的version；
4. Version处于可检索状态，`active_index_set_id`指向当前ready Index Set；
5. Chunk必须属于这个active Index Set；
6. 用户为owner、company_owner，或命中user/role/market ACL之一；
7. Dense还要求Chunk的provider/model/revision/dimension/normalize等身份与本次Query Provider完全一致。

调用者不能传role、market、ACL、version_id、index_set_id、向量、SQL或模型本地路径。跨tenant、旧版本、失败索引、未激活索引、软删除文档和无权文档统一不会进入候选集。

### 7. 输入、输出和错误合同

- 输入：严格Schema，核心只有`query`，长度建议1至2000字符；候选数量使用服务端配置，最多只允许安全上限，不允许客户端扩大权限或任意控制SQL；
- 输出：候选Chunk的document/version/index/chunk公开ID、标题、类型、语言、市场、正文、页码/标题路径/Sheet/单元格或行范围等Source Locator、final rank；同时返回dense rank/余弦距离或相似度、lexical rank/FTS score、RRF score、Embedding身份和FTS builder版本；
- 不输出：tenant内部字段、ACL明细、Storage Key、真实磁盘路径、1024维向量、SQL、数据库异常或本地模型路径；
- 错误：空白/超长输入为安全校验错误；Provider不可用、向量身份不匹配、数据库超时/不可用为类型化安全错误；合法但没有命中返回空候选，不把无结果当系统故障；任何一路内部失败不返回伪装成完整Hybrid的200结果。

### 8. 按顺序执行的单一职责小步骤

##### M2-16.1｜冻结检索合同、配置和错误

- 目标：只定义“可以问什么、返回什么、怎样安全失败”，不写SQL；
- 预计文件：新增`app/schemas/retrieval.py`、`app/services/retrieval/errors.py`、`tests/unit/test_retrieval_contracts.py`；按实际需要小改`app/core/config.py`和`tests/unit/test_config.py`；
- 调用链位置：未来API/Tool → **Schema（本步）** → 未来Service；前端、API、Repository、Model、PostgreSQL均不经过；
- 验证：严格字段、空白/超长query、候选上限、公开结果字段、分数有限值、来源定位和错误脱敏的单元测试；Ruff、Mypy、编译和基线哨兵；
- 能证明：边界合同稳定；不能证明数据库能检索或权限正确。

##### M2-16.2｜建立版本化中文FTS构建器和迁移0008

- 目标：让文档侧和查询侧都使用固定jieba规则，并允许旧、新FTS builder版本共存；
- 预计文件：新增`app/services/retrieval/lexical_text.py`、`migrations/versions/20260831_0008_*.py`、`tests/unit/test_lexical_text.py`、`tests/integration/test_document_chunk_fts_migration.py`；修改`app/schemas/document_chunks.py`、`app/services/documents/indexing.py`或其Mapper合同、`app/models/documents.py`及相关测试；
- 调用链位置：Index Service/未来Lexical Service → FTS Builder → Mapper/Model → PostgreSQL generated search_vector + GIN；不经过前端或HTTP API；
- 验证：中文、英文、SKU、型号、条款号两边同规则；jieba版本和配置固定；`0007→0008→0007→0008`往返；旧Index Set仍合法，新Index Set使用新版；新成品ready前active不切换；
- 能证明：中文词条可被一致构建；不能证明Hybrid排序质量。

##### M2-16.3｜建立共享获权active候选Repository

- 目标：Dense和Lexical只能从同一套获权、active、ready数据集合取候选，避免两路权限写法漂移；
- 预计文件：新增`app/repositories/retrieval.py`、`tests/integration/test_retrieval_repository_scope.py`；按需要从`app/repositories/documents.py`提取并复用只读访问条件；
- 调用链位置：未来Retrieval Service → **Repository（本步）** → Document/Version/ACL/Index Set/Chunk Model → PostgreSQL；
- 验证：owner、company_owner、user/role/market ACL允许；跨tenant、无ACL、市场不交集、旧version、非active/failed Index Set、软删除Document/File全部为零候选；
- 能证明：数据库候选边界正确；不能证明查询向量或RRF。

##### M2-16.4｜实现Dense检索

- 目标：使用`QUERY`用途生成查询向量，在获权候选中按pgvector余弦距离取前N名；
- 预计文件：新增`app/services/retrieval/dense.py`、`tests/unit/test_dense_retrieval.py`、`tests/integration/test_dense_retrieval.py`；修改`app/repositories/retrieval.py`和`app/services/retrieval/__init__.py`；
- 调用链位置：内部调用者 → Schema → Dense Service → EmbeddingProvider(QUERY) → Retrieval Repository → Model → PostgreSQL/pgvector；不经过前端和HTTP API；
- 验证：Fake用于调用和错误边界；固定1024维归一化向量在真实PostgreSQL证明排序、top-N、稳定tie-break和身份过滤；Provider/DB故障安全失败；
- 能证明：pgvector真实排序和权限同时生效；Fake不能证明真实语义质量，小数据不能证明大规模HNSW召回。

##### M2-16.5｜实现Lexical检索

- 目标：把query按与索引相同的版本分词，在获权候选中使用PostgreSQL FTS排序；
- 预计文件：新增`app/services/retrieval/lexical.py`、`tests/unit/test_lexical_retrieval.py`、`tests/integration/test_lexical_retrieval.py`；修改`app/repositories/retrieval.py`；
- 调用链位置：内部调用者 → Schema → Lexical Service → jieba/Repository → Model → PostgreSQL FTS/GIN；不经过Embedding、前端和HTTP API；
- 验证：中文“亮度”、英文、SKU、型号、数字和无结果；所有权限/active过滤与Dense一致；`EXPLAIN`只确认GIN索引可用，不强求小表一定选择索引；
- 能证明：真实PostgreSQL关键词命中；不能证明Dense或最终融合质量。

##### M2-16.6｜实现Hybrid和RRF

- 目标：并列运行两路检索，按chunk_id去重，用固定`rrf_k=60`合并名次并保留分数分解；
- 预计文件：新增`app/services/retrieval/hybrid.py`、`tests/unit/test_rrf.py`、`tests/integration/test_hybrid_retrieval.py`；修改检索Schema导出；
- 调用链位置：内部调用者 → Schema → Hybrid Service → Dense + Lexical → RRF → 安全结果；底层两路继续进入Embedding/Repository/Model/PostgreSQL；
- 验证：只在单路命中、两路命中、重复Chunk、同分tie-break、空结果和一路故障时均有确定行为；结果权限集合不得超过两路获权候选并集；
- 能证明：融合公式、顺序和分数可复算；不能证明Reranker或回答质量。

##### M2-16.7｜真实闭环验收和阶段收口

- 目标：用正式合成文档建立临时索引，验证检索后精确恢复干净Seed；
- 预计文件：新增`scripts/verify_m2_retrieval.py`、`tests/unit/test_m2_retrieval_verification.py`、`tests/smoke/test_m2_retrieval_bge_smoke.py`；修改`tests/unit/test_m2_baseline.py`及两份进度文档；
- 调用链位置：验证脚本 → Retrieval Schema/Hybrid Service → Query Embedding + Retrieval Repository → Model → PostgreSQL FTS/pgvector；仍不经过前端、HTTP API、Reranker、Qwen、Evidence或Agent；
- 验证：Fake 10文档日常闭环、固定向量数据库排序、显式离线BGE小型语义Smoke、跨权限/版本/删除故障矩阵、`EXPLAIN`索引可用性、全量后端质量门；最后只清理本次生成物并恢复10/10/10/9和0索引行；
- 能证明：当前规模真实数据库闭环和确定性；不能承诺百万Chunk、并发负载、生产延迟、HNSW全量召回率或最终RAG答案质量。

### 9. 阶段完成标准

1. 中文关键词、Dense语义和RRF混合检索全部通过真实PostgreSQL验证；
2. tenant、owner/company_owner、user/role/market ACL、active Version、active ready Index Set、软删除和Embedding身份在排序前生效；
3. 旧版、失败、未激活、跨tenant和无权限Chunk不会进入任何候选榜单；
4. 结果包含安全来源定位、两路名次/分数和RRF分解，不泄露内部字段；
5. 日常测试默认Fake，固定向量负责数据库顺序，真实BGE只由显式Smoke加载且强制离线；
6. 迁移、Ruff、Mypy、编译、依赖、聚焦测试和后端全量通过，正式Seed精确恢复；
7. 没有实现Reranker、Qwen回答、Evidence、Tool、Agent、前端或HTTP检索路由。

### 10. 主要风险和优先排查

- 中文搜不到：先比较文档侧与查询侧的builder版本、jieba版本、HMM配置和最终分词文本，再查GIN/tsquery；
- Dense结果异常：先查`DOCUMENT/QUERY`用途、1024维、归一化、model/revision和cache key，再查余弦操作符与排序方向；
- 权限泄露：先比较Dense/Lexical是否共用同一access clause，以及过滤是否发生在`ORDER BY/LIMIT`之前；
- 旧数据被搜到：先查Document active Version和Version active Index Set两级连接，不只看Chunk自身ready字段；
- 小表不走HNSW/GIN：先用`EXPLAIN`确认索引可用，再区分优化器合理选择顺序扫描和索引定义错误；不能为了让测试好看而关闭正常优化器行为；
- Fake语义看似错误：Fake只保证确定性，不保证近义句排名；语义判断必须看显式BGE Smoke；
- Provider故障：返回类型化可重试错误，不把Lexical单路伪装成完整Hybrid成功。

### 11. 确认记录、当前结果与明确停止点

用户在完整方案和通俗解释后两次回复“继续”，视为确认上述M2-16范围与默认决策。确认后的第一个动作原计划是恢复正式Seed；用户中断命令后只读核对确认事务实际已经完成，当前为10 files、10 documents、10 versions、9 ACL，0 Chunk Set、0 Index Set、0 Chunk、0 active指针。随后用户指出应先更新文档，因此当前只补齐确认与方案记录，不开始生产代码。

M2-16.1至M2-16.7已经按下方步骤日志完成。用户另行确认暂不增加lexical/dense/hybrid模式路由；M2-16.7在35 Chunk合成样本上测得同步Hybrid p95约43.29 ms，规模不足以证明路由收益，因此继续默认Hybrid并把路由评估后置。这不改变tenant、ACL和服务端上限必须由确定性代码控制的边界。**M2-16已经收口，当前必须停止；只有用户确认M2-17方案后才可开始Reranker，当前不授权RAG、前端、Agent、HTTP检索API或任何后续阶段。**

### 2026-08-31｜M2-16.1｜冻结检索合同、配置和安全错误

**状态：已完成；已验证；明确停止在M2-16.1。**

1. 本步解决的问题：M2-15只有“文档如何被索引”的内部事实，没有规定未来Dense、Lexical和Hybrid“允许接收什么、必须返回什么、怎样安全失败”。本步先冻结共同边界，避免后续三路各自发明字段、用非法数字伪装未命中，或把SQL、路径和数据库原始异常带到公开响应；
2. 大白话运行过程：未来调用者只交一段`query`；tenant、用户、角色、市场、ACL、版本、Index Set、向量、SQL和候选数量都不能从请求体伪造。未来Service会按本步集中配置取候选，并把每个Chunk的公开身份、文档信息、正文、来源位置和真实命中分数装入同一份响应。本步只定义这只“安全标准箱子”和固定错误说明，还没有去数据库找任何Chunk；
3. 输入合同：`RetrievalRequest`继承项目现有严格Schema，先去除首尾空白，再要求1至2000字符且拒绝任何额外字段。2000是代码级硬上限；运行配置新增`retrieval_query_max_characters=2000`，未来Service可以在硬上限内进一步收紧。请求不接受候选数量，Dense、Lexical和Hybrid最终候选默认均为30、合法上限100；`hybrid_candidate_count`不得大于两路候选之和，Reranker top-k不得大于任一路或Hybrid候选数，`rrf_k`保持60；
4. 输出合同：公开候选只含document/version/index_set/chunk UUID，文档标题、类型、语言、市场和Chunk正文。PDF、DOCX、XLSX、CSV分别使用有辨别字段的类型化Source Locator，能表达页码/多页、标题路径、块/段落/表格、Sheet、单元格范围和行范围，且拒绝Storage Key等额外字段；
5. 分数决定：`dense`与`lexical`为可选分解，至少一路真实命中；未进入某一路榜单明确使用`None`，不用0、负排名或无穷大冒充。所有公开浮点数使用有限值合同，拒绝NaN和正负Infinity；所有榜单名次和最终名次从1开始。Dense按当前pgvector余弦定义限制distance为0至2、similarity为-1至1，两者同时出现时必须满足`similarity = 1 - distance`；Lexical的具体FTS归一化公式要到M2-16.5才冻结，因此本步只限制为有限值，不凭空设置上限；RRF分数必须为正有限值，Hybrid要求两种索引身份、`rrf_k`和每项RRF分数，最终名次必须连续；
6. 错误边界：新增检索输入错误、Embedding Provider不可用、Embedding身份不匹配、数据库不可用、数据库超时和检索内部失败六个专用异常类。构造器不接收原始异常文本，只生成固定公开中文消息；新增通用`DATABASE_UNAVAILABLE`公开错误码并映射未来HTTP 503，其余复用既有422/503/504/500语义。未来代码可以用异常链保留内部原因供日志排查，但`to_detail()`不会输出SQL、Storage Key、磁盘/模型缓存路径、环境变量或数据库连接信息；
7. 实际修改文件与职责：
   - `app/schemas/retrieval.py`：新增请求、候选/文档身份、四类来源定位、Dense/Lexical分解、Embedding/FTS身份、结果和按模式校验的统一响应；
   - `app/services/retrieval/errors.py`：新增六类固定消息的类型化检索错误；
   - `app/core/config.py`与`.env.example`：新增query硬上限、Hybrid最终候选数及候选组合校验；业务模块没有自行读取环境变量；
   - `app/schemas/common.py`与`app/api/errors.py`：登记`DATABASE_UNAVAILABLE`并冻结其503映射；
   - `app/schemas/__init__.py`与`app/services/retrieval/__init__.py`：从项目公共包入口导出新合同和错误；
   - `tests/unit/test_retrieval_contracts.py`：覆盖严格输入、四类定位、分数/排名、三种模式、敏感字段和错误脱敏；
   - `tests/unit/test_m2_baseline.py`：补充集中配置合法/非法组合并把阶段哨兵推进到“只有合同、没有检索执行”；
   - `docs/progress/M2/M2_KNOWLEDGE_RAG.md`与`docs/PROJECT_PROGRESS.md`：记录本步决定、验证、Seed恢复、风险和停止点；
8. 完整调用链位置：未来链路是`前端或Agent Tool → 未来API/Tool → Retrieval Schema（本步） → 未来Retrieval Service → 未来Embedding/Repository → 现有Model → PostgreSQL`。本步实际只经过Schema、集中配置和错误边界；没有经过前端、HTTP API、检索Service编排、查询Embedding调用、Repository、Model或PostgreSQL查询；
9. TDD证据：先新增合同测试，首次运行在收集阶段按预期因`ModuleNotFoundError: app.schemas.retrieval`失败，证明RED来自目标能力缺失。最小实现后第一次GREEN只剩1项配置样例失败：样例同时违反Reranker和Hybrid两个关系，校验器先报告前者；只把该测试的Reranker值改为合法5，让它单独验证Hybrid关系，没有放宽生产配置。最终聚焦合同与基线测试为`83 passed in 4.01s`，加入静态类型表达修正和余弦一致性断言后复跑仍为`83 passed`；
10. 最终验证：后端全量`.venv\Scripts\python.exe -m pytest -q`为`554 passed, 8 skipped in 90.06s`，8项仍是既有显式Smoke/环境条件跳过；`.venv\Scripts\ruff.exe check app tests scripts migrations`全仓通过，本步9个代码/测试文件`ruff format --check`通过；全仓format check只报告用户原先保留的`tests/integration/test_document_chunk_set_migration.py`换行/格式差异，本步没有机械改写该文件。Mypy检查`app`及本步两份测试共105个源码文件通过；`compileall -q app tests scripts migrations`无错误；`pip check`为`No broken requirements found`；`git diff --check`通过；Alembic current/heads均为`20260831_0007 (head)`且`alembic check`无新操作，因此本步不需要迁移；
11. Seed与基础设施恢复：全量测试按既有集成测试设计把共享演示Seed清理为0行，复核发现后只运行项目既有幂等模块入口`seed_m1 → seed_m2_files → seed_m2_complex_files`恢复，没有删除卷、清空数据库或Storage。最终只读结果为PostgreSQL 17.11 + pgvector 0.8.6容器healthy，10 files、10 documents、10 versions、9 ACL、10 parse pending、10 index pending、0 active Version、0 active Index Set、0 Chunk Set、0 Index Set、0 Chunk；Storage为10 uploads、0 parsed JSON、0 chunks JSON；M1 `LR-TL-MUSH-OR01 / DE-FRA`可售库存125；固定BGE快照8个必需文件与manifest均在本地，日常配置仍为Fake和`model_local_files_only=True`，本步从未加载真实模型；
12. 能证明与不能证明：测试能证明公开合同拒绝伪造字段、空白/超长问题、非法排名、非有限分数、矛盾余弦值、错误模式组合和敏感内部字段，并能表达四类文档定位及单路未命中；能证明集中配置拒绝越界与非法组合，现有后端没有被公共导出和错误码修改破坏。它不能证明中文分词、FTS/GIN命中、pgvector查询排序、tenant/ACL/active过滤、两路RRF真实融合、性能或真实BGE语义质量，因为这些分别属于M2-16.2至M2-16.7；
13. 风险与优先排查：未来请求422先看是否有多余tenant/limit等字段或query去空白后为空/超过配置；响应校验失败先看检索模式与Dense/Lexical/RRF字段是否一致、名次是否从1连续；Dense分数失败先核对是否误把inner product当余弦distance/similarity；中文分数范围不能在本步猜测，等M2-16.5按实际SQL冻结；错误泄露优先检查是否绕过专用错误、直接把`str(database_error)`写入响应；配置启动失败先比较Hybrid、两路候选和Reranker top-k关系；
14. 下一步与停止点：M2-16.1已经完成并验证，当前明确停止。不得自动开始M2-16.2，不新增jieba分词器、0008迁移、Repository、SQL、Dense/Lexical/Hybrid Service、RRF实现或真实BGE加载；等待用户理解和明确确认后再继续。

### 2026-08-31｜M2-16.2｜版本化中文分词和FTS Builder迁移

**状态：已完成；已验证；明确停止在M2-16.2。**

1. 本步解决的问题：原索引把整段`retrieval_text`原样交给PostgreSQL `simple`配置。英文和SKU可以按空白、标点拆开，但连续中文通常会被视作大词，未来查询“亮度”未必能命中文档里的“蘑菇灯亮度调节说明”。本步增加文档侧与未来查询侧共用的版本化中文词条构建器，并让数据库同时接受旧raw与新版索引代次；
2. 大白话运行过程：文档入库前先经过同一台“固定切词机”，例如“蘑菇灯亮度调节说明”稳定变成`蘑菇 灯 亮度 调节 说明`，再保存到`fts_text`。PostgreSQL继续自动把`fts_text`生成`search_vector`并使用既有GIN索引。未来用户查询也必须走同一台切词机，这样两边使用相同词条；本步只准备这台机器及数据库版本边界，还没有编写正式关键词检索Service；
3. Builder身份与确定性：新增`m2-fts-jieba-search-v1`，固定jieba `0.42.1`、随包词典SHA-256 `7197c3211ddd98962b036cdf40324d1ea2bfaa12bd028e68faa70111a88e12a8`、search模式、`HMM=False`、NFKC + casefold规范化和Unicode字母数字过滤。Builder使用独立Tokenizer，不接受运行期自定义词，不依赖jieba全局词典状态；词典文件、包版本或输入边界不符合合同都会安全失败；
4. 文档与查询一致性：`FtsTextPurpose.DOCUMENT`和`QUERY`用于审计用途，但当前明确使用同一套规则。词条保持原顺序和词频，不去重；英文被统一为小写，全角字符被规范化，SKU、型号、数字和条款组成部分继续可搜索。输入必须是非空字符串，输入与输出均受2,000,000字符存储边界保护；
5. 索引写入变化：`map_index_rows()`不再令`fts_text = retrieval_text`，而是调用共享Builder；`DocumentChunkWriteFacts`也用同一Builder复算并拒绝伪造词条。`retrieval_text`仍完整保留给展示、Embedding和后续RAG，只有独立的`fts_text`变成分词产物。Index Set确定性身份原本就包含`fts_builder_version`，因此新旧规则自然生成不同索引代次，不会把旧成品误当新版复用；
6. 迁移决定：新增Alembic `20260831_0008`，只调整`document_index_sets`身份约束，允许`m2-fts-raw-retrieval-v1`和`m2-fts-jieba-search-v1`共存；没有新增列，也没有原地改写旧Chunk。旧ready索引可继续保持active，新版索引只有ready后才能通过既有复合外键切换active。降级前如果发现新版Index Set会明确拒绝，避免为了回到0007而静默删除或误解释新数据；
7. 实际修改文件与职责：
   - `app/services/retrieval/lexical_text.py`：实现固定身份、输入边界、独立jieba Tokenizer、锁、缓存和文档/查询共享入口；
   - `app/services/retrieval/__init__.py`：从稳定公共入口导出FTS Builder合同；
   - `app/services/documents/indexing/contracts.py`：将当前Index Set身份推进到新版Builder，并复算校验每行`fts_text`；
   - `app/services/documents/indexing/mapping.py`：在索引Mapper中真正生成新版词条；
   - `app/models/knowledge.py`：ORM约束同时描述旧raw与新版FTS身份；
   - `migrations/versions/20260831_0008_versioned_jieba_fts.py`：升级新旧共存，降级遇到新版数据时安全拒绝；
   - `requirements.txt`：将jieba从兼容范围固定为精确`0.42.1`；
   - `scripts/verify_m2_index_pipeline.py`：索引验收改为按版本化Builder复核数据库`fts_text`；
   - `tests/unit/test_lexical_text.py`：覆盖身份、依赖固定、中文/英文/SKU/型号/条款、规范化、顺序、词频、确定性和非法输入；
   - `tests/unit/test_document_index_mapping.py`：验证Mapper使用新版身份与共享词条结果；
   - `tests/integration/test_document_chunk_fts_migration.py`：验证迁移往返、旧新共存、active切换、数据库约束、真实FTS命中和安全降级；
   - `tests/integration/test_document_index_service.py`：从真实索引Service落库结果断言新版身份与每个Chunk词条；
   - `tests/unit/test_m2_baseline.py`：把阶段哨兵推进到“Builder和0008已存在，但候选Repository与检索执行仍不存在”；
   - `docs/progress/M2/M2_KNOWLEDGE_RAG.md`与`docs/PROJECT_PROGRESS.md`：同步本步决定、验证、Seed和停止点；
8. 完整调用链位置：索引侧实际经过`DocumentIndexService（已有） → FTS Builder（本步） → Index Mapper/合同（本步修改） → DocumentChunk Model（已有，约束同步） → PostgreSQL generated search_vector + GIN（已有）`；迁移直接作用于Model到PostgreSQL的Index Set身份边界。查询侧目前只证明`QUERY → FTS Builder`能生成相同词条，尚未经过Retrieval Service、Repository或生产SQL。前端、HTTP检索API、Agent Tool、Dense、Hybrid/RRF、Reranker、Qwen和真实BGE都未经过；
9. TDD RED证据：先写Builder与Mapper测试，首次收集按预期因`ModuleNotFoundError: app.services.retrieval.lexical_text`失败；最小实现后只剩Mapper样例少算一次标题中的“安全要求”，根据“保持词频”合同修正测试期望而未改生产逻辑，随后`16 passed`。再先写迁移和阶段边界测试，首次为`3 failed, 48 passed`，失败分别来自0008不存在、数据库拒绝新版身份和阶段哨兵找不到迁移，均准确指向待实现能力；
10. 迁移调试记录：第一次创建约束时因Alembic命名约定对原始名称再次加前缀，实际要删除的约束没有找到；改用`op.f(...)`指明已格式化名称后转绿。新增安全降级测试时，测试清理顺序先删Tenant触发Version外键，只调整测试按依赖顺序删Version再删Tenant；该次失败留下的唯一测试tenant经只读UUID精确核对后定向删除并复核为0，没有清空数据库或Storage；
11. 最终验证：Builder/Mapper首轮GREEN为`16 passed`；迁移与阶段边界为`51 passed`，安全降级单测为`3 passed`；包含合同、Model、迁移、Repository、索引Service与API的扩大聚焦集为`151 passed in 19.37s`，格式化后关键集复跑`79 passed in 12.54s`。后端全量`.venv\Scripts\python.exe -m pytest -q`为`568 passed, 8 skipped in 92.41s`，8项仍是显式Smoke或环境条件跳过；
12. 工程质量与迁移验证：`.venv\Scripts\python.exe -m ruff check app migrations scripts tests`全仓通过，本步12个文件`ruff format --check`通过；Mypy检查`app`、验收脚本和相关测试共110个源文件为`Success: no issues found`；`compileall -q app migrations scripts tests`无错误；`pip check`为`No broken requirements found`，运行环境jieba确认为`0.42.1`；`git diff --check`通过。Alembic current与heads均为`20260831_0008 (head)`，`alembic check`为`No new upgrade operations detected`；PostgreSQL容器保持healthy；
13. Seed与基础设施恢复：全量测试后只运行既有幂等入口`seed_m1 → seed_m2_files → seed_m2_complex_files`。最终只读事务显示`transaction_read_only=on`，PostgreSQL 17.11、pgvector 0.8.6，10 files、10 documents、10 versions、9 ACL，10 parse pending、10 index pending、0 active Version、0 active Index Set、0 Chunk Set、0 Index Set、0 Chunk、0非空Embedding；Storage为10 uploads、0 parsed JSON、0 chunks JSON、0其他对象；M1 `LR-TL-MUSH-OR01 / DE-FRA`可售库存125。本步没有加载BGE-M3，日常测试仍使用Fake Provider；
14. 能证明与不能证明：测试能证明相同输入在文档与查询用途产生同版确定性词条，新索引Service真实保存新版词条，PostgreSQL约束允许旧新代次共存且阻止未知版本，新成品ready前不能切active，新版词条通过参数化FTS表达式能命中中文“亮度”，迁移可以安全往返且不会静默丢新版数据。它不能证明生产Lexical Repository的tenant/ACL/active候选边界、Top K排序、GIN在大数据下的执行计划、Dense/Hybrid/RRF效果、真实BGE语义、并发或生产延迟，因为这些属于M2-16.3至M2-16.7；
15. 风险与优先排查：中文搜不到时先比较文档和query的`fts_builder_version`、最终`fts_text`、jieba版本与词典Hash，再看`search_vector`和tsquery；启动时报Builder错误先检查虚拟环境是否确切安装jieba 0.42.1及官方词典是否被改动；旧active索引中文效果不变是预期，必须重建新版Index Set并在ready后切换，不能原地伪装升级；迁移降级被拒绝时先找新版Index Set并走显式重建/清理方案，不能绕过保护；内存或延迟异常先看是否把超大正文绕过既有Chunk边界直接交给Builder；
16. 下一步与停止点：M2-16.2已经完成并验证，当前明确停止。不得自动开始M2-16.3，不新增共享获权候选Repository、tenant/ACL/active过滤、Dense/Lexical生产查询、Hybrid/RRF、HTTP API或真实模型加载；等待用户理解和明确确认后再继续。

### 2026-09-01｜M2-16.3｜共享获权active候选Repository

**状态：已完成；已验证；明确停止在M2-16.3。**

1. 本步目标与输入输出：M2-16.2已经能稳定生成中文FTS词条，但Dense和Lexical还没有共同的数据库安全入口。用户本轮明确授权只建立候选边界。输入是认证链从数据库刷新后的可信`CurrentUser`，包含`tenant_id`、`user_id`、角色和市场范围；输出是一条可继续组合的SQLAlchemy `Select`，返回获权的`DocumentChunk`及关联Document、Version、Index Set和StoredFile。请求体不能传tenant、ACL、version或index set；本步也不返回已排序的检索结果；
2. 大白话运行过程：未来两条检索路线都要先走同一扇门。门先按可信用户锁定租户，再确认文档和源文件没有软删除，文档指向当前active Version，Version又指向当前active且ready的Index Set，Chunk确实属于这一代Index Set；最后复用现有Document权限规则检查owner、company_owner、user ACL、role ACL或与用户市场相交的market ACL。只有通过全部条件的Chunk才留给后续Dense或Lexical排序；
3. 共享边界实现：新增`RetrievalRepository.authorized_active_chunks_statement(current_user)`作为唯一公共候选入口。方法不接受额外tenant参数，并在运行时拒绝非`CurrentUser`对象；所有DocumentChunk到Index Set、Version、Document和StoredFile的连接都同时核对tenant及复合归属字段，避免只按单个UUID连接造成错挂；权限部分直接复用M2-05以来的`document_access_clause()`，没有复制第二套ACL SQL；
4. active与状态条件：Document必须`deleted_at IS NULL`且`active_version_id`等于当前Version；Version的parse/index状态都必须为ready，且`active_index_set_id`等于当前Index Set；Index Set状态必须ready；Chunk必须通过完整tenant/document/version/chunk set/index set连接属于该active代次；StoredFile必须与Version同tenant、状态不是soft_deleted且`deleted_at IS NULL`。因此旧Version、旧Index Set、pending/failed Index Set、软删除Document/File不会进入候选；
5. 排序前边界：本方法只构造基础`SELECT ... JOIN ... WHERE ...`，测试直接编译SQL并断言不存在`ORDER BY`和`LIMIT`。未来Dense和Lexical必须从这条语句继续组合自己的评分、排序和Top K，权限过滤天然先于排序及截断，不能各自重写权限条件；
6. statement timeout与异常边界：Repository继续调用既有`apply_statement_timeout()`，集成测试确认事务内`statement_timeout=2s`。本步不新增数据库异常映射；按照现有项目分层，未来Retrieval Service负责把数据库超时/不可用映射为M2-16.1已经冻结的安全错误，Repository不把原始SQL或数据库异常包装进公开响应；
7. 实际修改文件与职责：
   - `app/repositories/retrieval.py`：新增共享授权active Chunk候选语句与可信`CurrentUser`运行时门禁；
   - `app/repositories/__init__.py`：从Repository公共入口导出`RetrievalRepository`；
   - `tests/integration/test_retrieval_repository_scope.py`：用真实PostgreSQL建立owner/company_owner/user/role/market ACL以及所有拒绝场景，验证同一候选边界、跨tenant隔离、无排序/limit和statement timeout；测试Chunk向量全部是固定合成值，未加载Provider；
   - `tests/unit/test_m2_baseline.py`：把阶段哨兵推进到M2-16.3，要求共享Repository已经存在，同时继续禁止`dense.py`、`keyword.py`、`hybrid.py`等后续执行模块；
   - `docs/progress/M2/M2_KNOWLEDGE_RAG.md`与`docs/PROJECT_PROGRESS.md`：记录方案、TDD、验证、Seed、风险和停止点；
8. 完整调用链位置：未来链路是`Retrieval Service（未实现） → Retrieval Repository（本步） → Document/Version/ACL/Index Set/Chunk/StoredFile Model（已有） → PostgreSQL（本步真实验证）`。本步实际经过Repository、ORM Model和PostgreSQL；没有经过前端、HTTP检索API、Retrieval Service编排、查询Embedding、pgvector距离、Lexical tsquery/排名、Hybrid、RRF、Reranker、Agent Tool、Qwen回答或Evidence；
9. TDD RED证据：先新增候选范围集成测试和阶段哨兵，在生产Repository文件不存在时运行`.venv\Scripts\python.exe -m pytest -q tests/integration/test_retrieval_repository_scope.py tests/unit/test_m2_baseline.py`，测试收集阶段按预期因`ModuleNotFoundError: No module named 'app.repositories.retrieval'`失败，证明RED来自目标Repository能力缺失，而不是断言拼错或数据库环境故障；
10. TDD GREEN与测试夹具校正：最小Repository实现后，第一次执行范围测试的3个error来自旧Index Set夹具把Chunk事后改挂到另一组复合外键，PostgreSQL正确以`fk_document_chunks_tenant_index_set_chunk_set_version_document`拒绝。只把测试数据改为“同一个Version/Chunk Set下并存新旧两个Index Set”，未修改生产查询；最终候选范围加阶段哨兵为`52 passed in 2.79s`。这也证明测试场景遵守真实数据库复合归属，而非绕过约束伪造旧代次；
11. 权限与拒绝矩阵结果：同租户reader能看到自己owner文档、直接user ACL、角色ACL及DE market ACL，看不到无ACL和FR market不交集；同租户company_owner能看到无ACL文档；另一租户company_owner只看到自己租户的cross-tenant样本，看不到当前租户样本。active Version与active Index Set样本可见，而旧Version、旧Index Set、pending/failed Index Set、软删除Document/File均为零候选；伪造`{"tenant_id": ...}`字典不能代替`CurrentUser`；
12. 最终测试结果：聚焦测试为`52 passed`；包含M2-15索引Repository/Service、Knowledge Service、M2-16.1合同和M2-16.2 Builder的相邻回归除既有日期问题外为`164 passed, 1 failed`。后端全量为`572 passed, 6 skipped, 1 failed in 47.63s`，唯一失败是既有`test_parse_failure_marks_first_index_failed_without_creating_index_set`把待删除上传Key硬编码为`2026/08`，而`FileService`按当前日期生成`2026/09` Key，实际文件未被删除，所以没有抛解析错误；该用例单独运行同样失败且与新Repository没有调用关系。本轮范围不授权修改M2-15.4测试；排除这个已定位用例后全量其余为`572 passed, 6 skipped, 1 deselected in 46.81s`；
13. 工程质量与迁移检查：全仓`.venv\Scripts\python.exe -m ruff check app tests scripts migrations`通过，203个文件`ruff format --check`通过；`mypy app`检查105个源文件无问题，新增Repository与集成测试的单独Mypy也通过；`compileall -q app tests scripts migrations`无错误，`pip check`为`No broken requirements found`，`git diff --check`通过；Alembic current/heads均为`20260831_0008 (head)`，`alembic check`为`No new upgrade operations detected`，因此本步不需要且没有新增迁移；
14. 正式Seed与基础设施最终状态：全量测试按既有设计把共享正式Seed清为0，随后只运行仓库已有幂等入口`seed_m1 → seed_m2_files → seed_m2_complex_files`恢复。最终PostgreSQL为10 files、10 documents、10 document_versions、9 document_acl、10 parse pending、10 index pending、0 active Document Version、0 active Index Set、0 document_chunk_sets、0 document_index_sets、0 document_chunks、0非空Embedding；Storage为10 uploads、0 parsed、0 chunks、0其他对象；M1 `LR-TL-MUSH-OR01 / DE-FRA`可售库存125。`deep-search-postgres`容器healthy，镜像与实际查询分别确认PostgreSQL 17.11、pgvector 0.8.6；
15. 模型边界：固定真实模型常量与本地快照仍为`BAAI/bge-m3@5617a9f61b028005a4858fdac845db406aefb181`；日常测试配置为`embedding_backend=fake`且`model_local_files_only=True`。本步测试使用固定1024维合成向量只满足现有表约束，没有创建Provider，也没有加载、下载或联网调用真实BGE；
16. 能证明与不能证明：本步能证明真实PostgreSQL候选集合在排序前统一执行可信tenant、现有五类访问路径、active Version、active ready Index Set、Chunk代次归属及Document/File软删除过滤，并证明未来两路已有单一可复用入口。它不能证明查询Embedding、pgvector余弦排序、Dense Top K、正式tsquery/FTS排名、GIN/HNSW执行计划、Hybrid/RRF、Reranker、性能、并发或回答质量，因为这些都没有实现；
17. 风险与优先排查：若未来出现权限泄漏，先确认Dense/Lexical是否都从`authorized_active_chunks_statement()`继续组合，而不是另写FROM/WHERE；再核对调用者传入的是否为认证依赖从数据库刷新后的CurrentUser。若旧数据出现，依次查Document active Version、Version active Index Set、Index Set ready及Chunk五字段复合归属；若已授权数据消失，先查Document/File软删除状态、Version parse/index状态、ACL subject与CurrentUser角色/市场是否一致；若超时，先确认事务内statement timeout和查询计划，再查后续排序是否错误地绕过基础语句；
18. 下一步与停止点：M2-16.3已经完成并验证，当前明确停止。没有开始M2-16.4，不新增查询Embedding、pgvector距离、Dense Top K、正式Lexical tsquery/排名、Hybrid、RRF、HTTP API、Agent Tool、前端、Qwen或真实模型加载。只有用户理解并再次明确确认后，才可进入M2-16.4 Dense检索。

### 2026-09-01｜M2-16.4｜权限前置的Dense检索

**状态：已完成；已验证；明确停止在M2-16.4。**

1. 本步目标与范围：用户明确回复“开始下一步”，授权执行既有M2-16.4方案。本步输入是可信`CurrentUser`和严格`RetrievalRequest.query`，输出是`RetrievalResponse(mode="dense")`；只实现QUERY用途Embedding、完整身份检查、共享候选范围内的pgvector余弦距离、服务端Top K、稳定tie-break和安全响应，不实现Lexical、Hybrid、RRF、Reranker、API、Agent、前端或Qwen；
2. 大白话运行过程：Service先用登录用户经过M2-16.3的安全门查看当前可读active索引使用哪套Embedding身份；没有可读Chunk就直接返回空结果，不加载模型。只有当前Provider身份与至少一个可读active Index Set完全一致时，才把问题按`QUERY`用途生成一个1024维归一化向量；Repository从同一扇安全门追加身份条件，PostgreSQL计算余弦距离，按距离从小到大取服务端限定数量；
3. Repository实现：`list_authorized_embedding_identities()`从共享候选语句只投影active Index Set身份，供Service在模型调用前判断兼容性；`dense_candidates_statement()`再次从`authorized_active_chunks_statement()`继续组合完整`embedding_identity_json`、Index Set/Chunk model与revision、非空向量、`embedding <=> query_vector`、`ORDER BY distance ASC, chunk UUID ASC`及`LIMIT`；`search_dense()`只返回安全`DenseCandidateRecord`，不带tenant、ACL、向量、Storage Key或磁盘路径；
4. 身份与失败策略：若可读范围完全没有当前Provider身份，返回`RetrievalEmbeddingIdentityMismatchError`，不把不兼容索引当无结果；可读范围同时存在兼容和其他身份时，只检索兼容代次。Provider必须返回一个QUERY用途、身份一致、有限且归一化的1024维向量；Provider失败映射为可重试安全错误，数据库SQLSTATE 57014映射超时，其余SQLAlchemy错误映射数据库不可用，公开消息不含SQL、连接串或表名；
5. 排名与公开结果：数据库余弦distance要求0至2，Service同时给出`similarity = 1 - distance`，Dense rank和final rank从1连续排列；距离同分使用Chunk行UUID升序稳定打破平局。PDF、DOCX、XLSX、CSV均从现有Chunk定位事实映射到M2-16.1类型化公开Locator；响应不包含Embedding数组、tenant、ACL或Storage实现细节；
6. 实际修改文件与职责：
   - `app/repositories/retrieval.py`：在M2-16.3共享候选边界上新增身份读取、Dense SQL、pgvector排序和安全Record；
   - `app/repositories/__init__.py`：导出`DenseCandidateRecord`及既有Repository；
   - `app/services/retrieval/dense.py`：新增Dense Service、QUERY Provider调用、批次验真、错误映射、分数与四类来源定位组装；
   - `app/services/retrieval/__init__.py`：从稳定公共入口导出`DenseRetrievalService`；
   - `tests/unit/test_dense_retrieval.py`：覆盖QUERY用途、运行时query上限、空范围不加载Provider、身份不匹配、Provider/数据库故障、四类定位、分数和敏感字段；
   - `tests/integration/test_dense_retrieval.py`：用固定归一化向量在真实PostgreSQL验证距离、Top K、同分UUID顺序、权限排除、身份过滤及SQL子句顺序；
   - `tests/unit/test_m2_baseline.py`：阶段哨兵推进到Dense已存在，但Lexical、Hybrid、Reranker与检索API仍不存在；
   - 两份进度文档：记录TDD、验证、Seed、风险和停止点；
7. 完整调用链位置：本步实际经过`内部调用者/测试 → Retrieval Schema → DenseRetrievalService → EmbeddingProvider(QUERY) → RetrievalRepository共享安全门 + Dense扩展 → Document/Version/ACL/Index Set/Chunk/StoredFile Model → PostgreSQL/pgvector`。没有经过前端、HTTP API、Lexical Builder查询、GIN/tsquery、Hybrid、RRF、Reranker、Agent Tool、Harness、Evidence或Qwen；
8. TDD RED证据：先新增单元和真实pgvector集成测试，再运行两文件。收集阶段分别因`ImportError: cannot import name 'DenseCandidateRecord'`和`ModuleNotFoundError: No module named 'app.services.retrieval.dense'`失败，准确证明RED来自M2-16.4 Record、Repository Dense能力和Service尚不存在；
9. TDD GREEN证据：最小实现后首次Dense两文件即为`9 passed in 2.49s`；推进阶段哨兵并完成格式/类型修正后，包含M2-16.1合同、M2-16.3安全门和M2-16.4的聚焦集为`95 passed`；补齐运行时query限制、DOCX/XLSX/CSV定位和第二次数据库查询故障后最终聚焦集为`100 passed in 3.46s`；
10. 真实数据库排序证据：查询向量为单位向量`e1`，数据库固定候选依次为同向distance 0、`(0.8, 0.6)` distance 0.2、两个正交向量distance 1；服务端Top 3返回0、0.2、1，并在两个distance 1候选中选择UUID较小者。无ACL的distance 0候选被M2-16.3边界排除，不兼容revision的distance 0候选被身份条件排除；编译SQL确认`WHERE < ORDER BY < LIMIT`且包含ACL、身份和`<=>`；
11. 最终测试：Embedding、索引身份、M2-16.3和Dense扩大回归为`170 passed, 1 failed`；后端全量为`586 passed, 6 skipped, 1 failed in 47.82s`，唯一失败仍是既有`test_parse_failure_marks_first_index_failed_without_creating_index_set`硬编码删除`2026/08` Key，而当前FileService生成`2026/09` Key。该测试与Dense无调用关系且本轮未授权修改；排除已定位用例后全量其余为`586 passed, 6 skipped, 1 deselected in 46.72s`；
12. 工程质量与迁移：全仓Ruff lint通过，206个文件format check通过；`mypy app`检查106个源文件无问题，新增Repository/Service/测试的聚焦Mypy也通过；`compileall -q app tests scripts migrations`、`pip check`和`git diff --check`通过；两个公共包可从全新Python进程独立导入。Alembic current/heads均为`20260831_0008 (head)`且check无新操作，因此本步没有新增迁移；
13. 正式Seed与基础设施：两轮全量测试把共享正式Seed清为0后，只运行既有幂等入口`seed_m1 → seed_m2_files → seed_m2_complex_files`恢复。最终为10 files、10 documents、10 versions、9 ACL、10 parse pending、10 index pending、0 active Version、0 active Index Set、0 Chunk Set、0 Index Set、0 Chunk、0 Embedding；Storage为10 uploads、0 parsed、0 chunks、0其他；M1蘑菇灯DE-FRA可售125。PostgreSQL 17.11、pgvector 0.8.6和容器healthy；
14. 模型边界、能证明与不能证明：固定模型仍为`BAAI/bge-m3@5617a9f61b028005a4858fdac845db406aefb181`，日常配置为Fake且local-only。本步没有加载、下载或联网调用真实BGE。测试能证明QUERY用途调用、当前规模真实pgvector精确距离、身份/权限先于排序、Top K和稳定tie-break；Fake/固定向量不能证明真实语义质量，当前小表也不能证明HNSW在百万Chunk下的召回、性能或一定被优化器选择，更不能证明Lexical/Hybrid/RRF；
15. 风险与排查：Dense结果为空时先区分没有获权active Chunk、active身份不兼容和合法Top K无行；身份错误先逐字段比较Provider与Index Set的contract/provider/model/revision/pooling/max_length/normalize/precision/dimensions，再核对Chunk model/revision；排序错误先检查QUERY用途、向量归一化、`<=>`方向及distance/similarity换算；权限异常先确认Dense SQL确实从共享语句继续组合；超时先看statement timeout和执行计划。身份预检与排序目前是同一Session中的两次只读语句，在极端并发active切换下依赖PostgreSQL事务可见性，未来并发加固时应评估单语句快照或更高隔离级别；
16. 下一步与停止点：M2-16.4已经完成并验证，当前明确停止。没有开始M2-16.5，不新增正式Lexical tsquery/排名、GIN计划验证、Hybrid、RRF、HTTP API、Agent Tool、前端、Qwen或真实模型加载。只有用户理解并再次明确确认后，才可进入M2-16.5 Lexical检索。

### 2026-09-01｜M2-16.5｜版本化Lexical检索、FTS排名与Top K

**状态：已完成；已验证；明确停止在M2-16.5。**

1. 本步解决的问题：M2-16.2只有“文档和问题怎样用同一套规则切词”，M2-16.3只有共享权限安全门，还缺少正式把查询词条送入PostgreSQL FTS、按真实关键词相关度排序并在数据库端限制候选数量的能力。本步补齐Lexical单路，但不做Hybrid、RRF或检索模式路由；
2. 大白话运行过程：用户的问题先进入与索引相同的固定jieba Builder；词条有序去重后用OR连接，例如问题中的任一有效词都可以召回，避免“如何”等泛词把整条查询按AND卡死。Repository先执行M2-16.3的tenant、ACL、active Version、active ready Index Set安全门，再要求Index Set的FTS Builder版本一致、`search_vector @@ tsquery`命中，最后才按`ts_rank_cd(..., 32)`从高到低排序、UUID从小到大打破同分并执行服务端`LIMIT`。Service把结果装入M2-16.1安全响应，不返回tenant、ACL、Storage Key、生成列或SQL；
3. SQL与安全决定：tsquery文本只由受控Builder输出的Unicode字母数字词条构成，Service和Repository各自校验，整串仍由SQLAlchemy参数绑定交给`to_tsquery('simple', ...)`，不拼接为原始SQL。`fts_builder_version`必须与active Index Set一致，旧raw索引不会混入新版排名。Lexical语句从`authorized_active_chunks_statement(CurrentUser)`继续组合，所以权限/active过滤明确位于`ORDER BY`和`LIMIT`之前；本路不查询Embedding列，也不创建或调用Embedding Provider；
4. 排名决定：使用PostgreSQL `ts_rank_cd(search_vector, tsquery, 32)`；Normalization 32把排名变换为`rank/(rank+1)`，保留词频和覆盖密度差异并得到有限、便于展示的值，但Hybrid不会直接把它与余弦分数相加，后续M2-16.6仍按榜单名次执行RRF。相同Lexical分数按Chunk UUID升序，保证重复执行顺序稳定；
5. 实际修改文件与职责：
   - `app/repositories/retrieval.py`：新增`LexicalCandidateRecord`、Lexical参数防御、共享候选上的FTS身份/命中/排名/Top K语句和安全记录映射；
   - `app/services/retrieval/lexical.py`：新增查询Builder调用、OR tsquery构造、数据库错误映射、Lexical响应与排名组装；
   - `app/services/retrieval/result_mapping.py`：从Dense提取四类来源定位的共用映射，避免两条检索路线复制并漂移PDF/DOCX/XLSX/CSV公开定位逻辑；
   - `app/services/retrieval/dense.py`：只改为调用共用来源定位映射，Dense向量、身份和排序行为不变；
   - `app/repositories/__init__.py`与`app/services/retrieval/__init__.py`：导出新增正式能力；
   - `tests/unit/test_lexical_retrieval.py`：覆盖Builder/OR查询、公开响应、空结果、运行时query上限和数据库错误脱敏；
   - `tests/integration/test_lexical_retrieval.py`：真实PostgreSQL覆盖词频排名、稳定同分、Top K、无权限与旧Builder排除、中英文/SKU/型号/数字/条款、无结果、SQL顺序和GIN可用性；
   - `tests/unit/test_m2_baseline.py`：把边界哨兵推进到Lexical已存在、Hybrid/Reranker/API仍不存在；
   - `docs/progress/M2/M2_KNOWLEDGE_RAG.md`与`docs/PROJECT_PROGRESS.md`：记录本步证据、路由后置决定、风险、Seed和停止点；
6. 完整调用链位置：当前实际链路为`内部调用者 → RetrievalRequest Schema（M2-16.1） → LexicalRetrievalService（本步） → FTS Builder（M2-16.2） → RetrievalRepository共享安全门 + Lexical扩展（M2-16.3/本步） → Document/Version/Index Set/Chunk Model → PostgreSQL FTS generated search_vector/GIN`。本步经过Schema、Service、Builder、Repository、Model和PostgreSQL；不经过前端、HTTP API、Agent Tool、Qwen、Embedding Provider、pgvector距离、Hybrid、RRF、Reranker或Evidence；
7. TDD RED证据：先新增单元和集成测试，首次运行在收集阶段分别因`ImportError: cannot import name 'LexicalCandidateRecord'`和`ModuleNotFoundError: app.services.retrieval.lexical`失败，准确证明缺少的是本步Repository记录和Lexical Service，而不是数据库、测试数据或断言错误；
8. TDD GREEN证据：最小实现后，Lexical + Dense回归首次为`29 passed in 4.34s`；最终Lexical单步测试为`15 passed in 3.41s`；包含M2-16合同、Builder、迁移、共享候选、Dense、Lexical和基线哨兵的相关回归为`129 passed in 5.84s`；
9. 真实数据库证据：测试构造有权、无权和旧Builder active文档；“亮度”按词频得到高、中、同分低UUID的前三名，无权高词频Chunk和旧Builder Chunk均未出现。中文“蘑菇灯”、英文`brightness`、SKU `LR-TL-MUSH-OR01`、型号`X200`、`220V`和条款`5.2`均命中，不存在词返回空列表。编译SQL明确满足`WHERE < ORDER BY < LIMIT`并包含ACL、Builder版本、`@@`和`TS_RANK_CD`；测试只在本事务用`enable_seqscan=off`运行`EXPLAIN`确认`ix_document_chunks_search_vector_gin`与查询结构兼容，不声称小表默认计划一定选择GIN；
10. 后端全量：`.venv\Scripts\python.exe -m pytest tests/unit tests/integration -q`实际为`601 passed, 2 skipped, 1 failed in 49.47s`。唯一失败仍是既有`test_parse_failure_marks_first_index_failed_without_creating_index_set`固定删除`uploads/2026/08/...`，而9月FileService真实写入`uploads/2026/09/...`，导致未触发预期解析错误；本步未越权修改。明确排除该已知用例后为`601 passed, 2 skipped, 1 deselected in 49.35s`；
11. 工程质量：正式M1/M2范围`ruff check app tests scripts migrations`通过，`ruff format --check app tests scripts migrations`为`210 files already formatted`；无范围`ruff check .`仍会报告仓库旧版`agent/api/tools/rawflow`的既有问题，本步未改这些旧文件。Mypy为`Success: no issues found in 108 source files`；`compileall -q app tests scripts`无错误；`pip check`为`No broken requirements found`；`git diff --check`通过；Alembic current/heads均为`20260831_0008 (head)`，`alembic check`为`No new upgrade operations detected`，因此本步不需要且没有新增迁移；
12. 能证明的内容：能证明版本化查询词条、参数化OR tsquery、真实PostgreSQL FTS命中与词频排序、稳定tie-break、数据库端Top K、Builder身份过滤、共享权限安全门先于排名、四类公开定位复用、空结果和数据库错误脱敏；Dense回归证明来源定位抽取没有改变已有Dense行为；
13. 不能证明的内容：当前合成小表不能证明生产数据规模的GIN执行计划、吞吐或延迟；词频排序不能证明语义相近但无共同词的问题能命中，也不能证明Hybrid/RRF或最终RAG答案质量；未运行正式10文档检索验收，未加载真实BGE，未验证百万Chunk、并发active切换或端到端API延迟；
14. 风险与优先排查：中文或SKU搜不到，先比较文档和查询的`fts_builder_version`与实际Builder词条，再查OR tsquery及`search_vector`；排序异常先查`ts_rank_cd`参数、文档词频和UUID tie-break；权限泄露先确认Lexical仍从`authorized_active_chunks_statement`组合且`WHERE`位于排序/限制之前；数据库报tsquery语法错先查Builder是否输出非字母数字词条和Service/Repository双重校验；性能问题先用正式规模`EXPLAIN (ANALYZE, BUFFERS)`看候选选择率和GIN计划，不能根据当前小表推断；
15. 正式Seed与基础设施最终状态：全量测试后只运行既有幂等入口`seed_m1 → seed_m2_files → seed_m2_complex_files`恢复。只读事务复核为10 files、10 documents、10 document_versions、9 document_acl、10 parse pending、10 index pending、0 active Document Version、0 active Index Set、0 document_chunk_sets、0 document_index_sets、0 document_chunks、0 Embedding；Storage为10 uploads、0 parsed、0 chunks、0其他对象；`LR-TL-MUSH-OR01 / DE-FRA`可售125；PostgreSQL 17.11、pgvector 0.8.6且容器healthy；固定真实模型常量仍为`BAAI/bge-m3@5617a9f61b028005a4858fdac845db406aefb181`，日常配置为Fake且local-only，本步没有加载、下载或联网调用真实BGE；
16. 路由决定与停止点：用户确认暂不做“问题应该走Lexical、Dense还是Hybrid”的自动路由，先在M2-16.6完成默认Hybrid，在M2-16.7测出真实延迟和质量后再评估；本步没有创建路由合同或让大模型决定模式。M2-16.5现已完成并验证，明确没有开始M2-16.6；未实现Hybrid、RRF、HTTP检索API、Agent Tool、前端、Qwen、Reranker或后续步骤，等待用户理解并单独确认。

### 2026-09-01｜M2-16.6｜Hybrid编排、RRF去重融合与稳定Top K

**状态：已完成；已验证；明确停止在M2-16.6。**

1. 本步解决的问题：M2-16.4和M2-16.5已经各自生成安全Dense榜单和Lexical榜单，但系统还不能把同一Chunk的两次命中合并，也没有共同最终名次。直接相加余弦距离和FTS分数会混合不同量纲，本步因此只按两路名次执行可复算RRF；
2. 大白话运行过程：Hybrid Service把同一个可信用户和同一个问题分别交给现有Dense与Lexical Service；两路各自经过M2-16.3共享安全门和数据库Top K。拿回两张完整榜单后，以`chunk_id`作为同一页内容的身份证去重：同时命中的Chunk获得两项贡献，只在一路命中的Chunk保留另一项为`None`。全部候选按RRF总分降序、Chunk UUID升序稳定排序，最后才截取Hybrid最终Top K；
3. RRF公式与稳定性：固定`rrf_k=60`，单路贡献为`1 / (60 + rank)`，双路贡献相加；不直接使用余弦距离或`ts_rank_cd`数值参与融合。RRF同分时按Chunk UUID升序，因此相同两张输入榜单会得到相同输出。最终`final_rank`从1连续编号，响应同时携带Embedding完整公开身份、FTS Builder版本和每个Chunk的Dense/Lexical原始排名与分数；
4. 完整失败决定：Hybrid只有在两路都成功返回完整合同后才构造响应；Dense或Lexical任一路抛出输入、Provider、身份、数据库或内部错误时原样向上失败，不把另一条单路结果伪装成Hybrid成功。空榜单不是故障：两路都为空时仍返回包含两种可复现身份的合法空Hybrid结果；
5. 跨语句一致性防御：重复`chunk_id`在两路的document/version/index_set身份、公开文档信息、正文或Source Locator必须完全一致，否则安全内部失败；同一Document若在两路观察到不同Version或Index Set，也拒绝融合，避免极端active切换窗口把两个代次混入一个Hybrid响应；单路自身重复Chunk或不连续原始rank同样拒绝；
6. 执行方式决定：当前两个下游Service是同步接口并共享同一个SQLAlchemy Session，Session不能安全地在线程间并发使用，因此本步按Dense后Lexical顺序执行，而不是为了表面“并行”引入线程风险。它们在业务上仍是两条独立榜单分支；是否需要独立Session并发、异步化或检索模式路由，必须在M2-16.7得到正式延迟数据后再评估；
7. 实际修改文件与职责：
   - `app/services/retrieval/hybrid.py`：新增下游检索协议、双路完整执行、合同防御、`chunk_id`去重、跨代次检查、RRF计算、稳定排序和最终Top K；
   - `app/services/retrieval/__init__.py`：从稳定包入口导出`HybridRetrievalService`；
   - `tests/unit/test_rrf.py`：覆盖双路重复、单路命中、RRF精确公式、UUID同分、融合后Top K、空结果、事实冲突、一路故障和配置边界；
   - `tests/integration/test_hybrid_retrieval.py`：复用真实PostgreSQL Dense/Lexical测试图，证明两路实际运行、无权Chunk不进入并集、重复合并、单路候选保留和最终Top K；
   - `tests/unit/test_m2_baseline.py`：将阶段哨兵推进到Hybrid存在但Reranker与检索API不存在；
   - `docs/progress/M2/M2_KNOWLEDGE_RAG.md`与`docs/PROJECT_PROGRESS.md`：记录公式、顺序执行决定、验证、Seed、路由后置和停止点；
8. 完整调用链位置：`内部调用者 → RetrievalRequest Schema → HybridRetrievalService（本步） → DenseRetrievalService + LexicalRetrievalService → EmbeddingProvider(QUERY) + FTS Builder → RetrievalRepository共享安全门 → Document/Version/Index Set/Chunk Model → PostgreSQL pgvector/FTS → RRF（本步） → RetrievalResponse`。本步经过内部Schema、三层检索Service、已有Provider/Builder、Repository、Model和PostgreSQL；不经过前端、HTTP API、Agent Tool、Qwen、Reranker、Evidence或模式路由；
9. TDD RED证据：先新增单元与真实PostgreSQL集成测试，首次收集均因`ModuleNotFoundError: No module named 'app.services.retrieval.hybrid'`失败，准确证明缺少的是Hybrid/RRF生产模块，不是Fixture、数据库或断言问题；
10. TDD GREEN证据：最小实现首次为`11 passed in 2.48s`；修正静态类型变量名和测试Fixture导入结构后复跑仍为`11 passed`。包含检索Schema、版本化Builder、0008迁移、共享候选、Dense、Lexical、Hybrid/RRF及阶段哨兵的扩大回归为`140 passed in 7.29s`；
11. 真实数据库证据：集成测试使用同一个真实`RetrievalRepository`和PostgreSQL Fixture分别执行pgvector Dense与FTS Lexical；最终集合精确等于两条获权榜单并集，无ACL的高匹配Chunk未出现；双路共同命中的Chunk只返回一次且同时保留两种分数，Lexical未命中但Dense命中的合法Chunk仍以Dense-only形式保留；最终候选限制在跨路去重和RRF排序后生效；
12. 后端全量：`.venv\Scripts\python.exe -m pytest tests/unit tests/integration -q`实际为`612 passed, 2 skipped, 1 failed in 55.94s`。唯一失败仍是既有`test_parse_failure_marks_first_index_failed_without_creating_index_set`固定删除`uploads/2026/08/...`，而9月FileService真实写入`uploads/2026/09/...`，未触发预期解析错误；本步未越权修改。明确排除该已知用例后为`612 passed, 2 skipped, 1 deselected in 49.24s`；
13. 工程质量：`ruff check app tests scripts migrations`通过；`ruff format --check app tests scripts migrations`为`213 files already formatted`；Mypy为`Success: no issues found in 109 source files`；`compileall -q app tests scripts`无错误；`pip check`为`No broken requirements found`；`git diff --check`通过；Alembic current/heads均为`20260831_0008 (head)`，`alembic check`无新操作，因此本步不需要且没有新增迁移；
14. 能证明与不能证明：能证明RRF公式、按Chunk去重、双路/单路分数保留、稳定tie-break、融合后Top K、空结果、一路失败不伪成功、同Chunk事实与同Document代次冲突安全失败，以及真实PostgreSQL两路结果不会突破获权并集。不能证明正式10文档Recall、真实BGE语义质量、最终RAG答案质量、生产延迟、并发吞吐、百万Chunk性能或顺序执行是否已成为瓶颈；这些属于M2-16.7及后续评估；
15. 风险与优先排查：RRF顺序异常先核对两路原始rank是否从1连续、公式是否误写为`rank+k`之外的形式以及最终排序方向；重复Chunk未合并先查公开`chunk_id`是否一致；同Document代次冲突先查Hybrid两次数据库读取期间是否发生active切换；一路结果消失先查对应下游Service是否为空而不是把`None`当0分；延迟高先分别记录Dense身份预检/Embedding/pgvector、Lexical Builder/FTS和RRF纯内存耗时，再决定独立Session并发或路由，不能先让大模型绕过安全链；
16. 正式Seed与基础设施最终状态：两轮全量测试后只运行既有幂等入口`seed_m1 → seed_m2_files → seed_m2_complex_files`恢复。只读事务复核为10 files、10 documents、10 document_versions、9 document_acl、10 parse pending、10 index pending、0 active Document Version、0 active Index Set、0 document_chunk_sets、0 document_index_sets、0 document_chunks、0 Embedding；Storage为10 uploads、0 parsed、0 chunks、0其他对象；`LR-TL-MUSH-OR01 / DE-FRA`可售125；PostgreSQL 17.11、pgvector 0.8.6且容器healthy；固定真实模型仍为`BAAI/bge-m3@5617a9f61b028005a4858fdac845db406aefb181`，日常配置为Fake且local-only，本步没有加载、下载或联网调用真实BGE；
17. 路由决定与停止点：本步完成的是进入知识库检索后的默认Hybrid编排，不是“哪些问题进入知识库”或“进入后选择哪种模式”的路由。用户此前决定先不实现自动或大模型路由，等M2-16.7实际测量延迟和质量后再评估。M2-16.6现已完成并验证，明确没有开始M2-16.7；未实现正式10文档验收脚本、真实BGE检索Smoke、检索API、Reranker、RAG、前端、Agent或后续步骤，等待用户理解并单独确认。

### 2026-09-01｜M2-16.7｜正式检索闭环验收和阶段收口

**状态：已完成；已验证；M2-16阶段已收口，明确没有开始M2-17。**

1. 本步解决的问题：M2-16.3至M2-16.6分别证明了安全候选、Dense、Lexical和Hybrid/RRF，但此前仍没有用正式10份合成文档、20条Golden问题把这些能力串成可重复验收，也没有真实BGE检索Smoke、延迟记录、索引执行计划证据和验收后精确Seed恢复。本步只补齐验证闭环，不新增生产检索算法；
2. 大白话运行过程：验收脚本先确认正式Seed干净，再临时解析、切块并用Fake为10份文档建立35个可检索Chunk。20个问题各自完整运行Dense、Lexical和Hybrid，再重复一次Hybrid比较结果顺序；随后临时改变版本、Index Set和软删除状态，确认安全门立刻把文档挡在候选外，并检查市场与角色ACL。最后用`EXPLAIN`确认GIN/HNSW定义可被相应查询采用，删除本轮20个parsed/chunk发布对象及全部临时索引行，把数据库和Storage恢复到pending Seed；
3. 本步输入与输出：输入是可信`CurrentUser`、10份版本化合成Seed、20条Golden问题/答案/定位、固定Fake身份以及显式离线BGE-M3本地快照；输出是版本化JSON验收报告、Dense/Lexical/Hybrid命中与排名、公开来源、权限故障矩阵、执行计划、分路延迟、清理状态和最终布尔判定。请求仍只有`query`，tenant、ACL、Top K、模型身份和索引代次不能由问题伪造；
4. 实际修改文件与职责：
   - `scripts/verify_m2_retrieval.py`：新增正式Fake 10文档验收、20问三路检索、确定性比较、安全故障注入、GIN/HNSW `EXPLAIN`、延迟统计、显式离线BGE单文档检索及`finally`清理；
   - `tests/unit/test_m2_retrieval_verification.py`：冻结Fake与BGE验收报告的通过条件，逐项突变质量、安全、索引、延迟和清理字段，防止报告缺项仍误判成功；
   - `tests/smoke/test_m2_retrieval_bge_smoke.py`：默认跳过，只有`RUN_BGE_M3_RETRIEVAL_SMOKE=1`才加载固定本地BGE-M3，验证真实Dense/Hybrid证据和清理；
   - `tests/unit/test_m2_baseline.py`：把阶段哨兵推进到M2-16.7验收文件存在，同时继续断言Reranker和HTTP检索API不存在；
   - `docs/progress/M2/M2_KNOWLEDGE_RAG.md`与`docs/PROJECT_PROGRESS.md`：记录M2-16.7证据、限制、Seed、路由决定与M2-16收口；
5. 完整调用链位置：`验收脚本 → RetrievalRequest Schema → HybridRetrievalService → DenseRetrievalService + LexicalRetrievalService → QUERY Embedding Provider + FTS Builder → RetrievalRepository共享安全门 → Document/Version/Index Set/Chunk Model → PostgreSQL pgvector/FTS → RRF → RetrievalResponse → 验收报告/清理`。为准备正式数据，上游还实际经过`DocumentIndexService → Parser/Chunk Service → Storage/PostgreSQL`。本步不经过前端、HTTP检索API、Qwen、Reranker、Context Builder、Evidence、Agent Tool或模式路由；
6. TDD RED证据：先新增验收判定、BGE Smoke和阶段哨兵测试，再运行`.venv\Scripts\python.exe -m pytest tests/unit/test_m2_retrieval_verification.py tests/unit/test_m2_baseline.py -q`，实际为`3 failed, 48 passed`；两项因`ModuleNotFoundError: scripts.verify_m2_retrieval`，一项因验收脚本文件不存在，准确证明缺少的是M2-16.7验收能力；
7. TDD GREEN证据：最小验收实现与静态问题修正后，同一命令为`51 passed in 2.09s`；默认包含BGE Smoke时为`51 passed, 1 skipped in 2.13s`，证明日常测试不会误加载真实模型。检索合同、Builder、迁移、共享Repository、Dense、Lexical、Hybrid及本步验收的相关回归为`142 passed in 6.39s`；
8. 正式Fake检索结果：10/10文档索引ready，共35 Chunk和35 Embedding。20问中Dense正确文档20/20、Lexical正确文档18/20、Hybrid正确文档20/20；Hybrid包含Golden事实所需探针的正确证据18/20，18条证据均带Schema验真的安全公开来源，重复Hybrid顺序20/20一致。2条未检索证据都是既有`visual_quality_notice`图文DOCX图片/页眉事实，未伪装成成功；
9. 来源定位审计：安全来源门禁是18/20，与可检索证据一致；另保留更严格的“公开Chunk首锚点是否精确等于Golden事实位置”观察值16/20。两个差异来自DOCX同一Chunk后部段落，而当前公开Locator返回Chunk首个来源锚点；它不泄露Storage Key、tenant、原始Span或表格JSON，但后续Context/引用阶段若要求事实级精确段落，应扩展范围或证据局部Locator，不能把16/20误写成20/20；
10. 权限与故障矩阵：正式10文档运行证明owner读取全部、DE market ACL允许、FR市场不匹配拒绝、role ACL允许和角色不匹配拒绝；把Document active Version置空、Version active Index Set置空、Document软删除或StoredFile软删除后，目标文档均立即变成0候选，恢复后重新可见。M2-16.3相关真实PostgreSQL回归继续覆盖company_owner、user ACL、跨tenant、无ACL、旧Version/Index Set及pending/failed代次，Dense/Lexical仍复用同一排序前安全边界；
11. 数据库索引证据：验收只在事务内设置`enable_seqscan=off`后运行`EXPLAIN`，Lexical计划出现`ix_document_chunks_search_vector_gin`，向量计划出现`ix_document_chunks_embedding_hnsw_cosine`。这证明索引定义与查询表达式兼容，不声称35行小表在正常优化器成本下必须选索引，也不证明百万Chunk性能或HNSW全量召回率；
12. 延迟与路由决定：同一台本机、35 Chunk、Fake Query Embedding、20问的Dense p50/p95/max约`22.603/27.586/35.782 ms`，Lexical约`12.577/20.757/22.283 ms`，同步Hybrid约`36.189/43.290/43.951 ms`。样本过小、Fake向量过快且没有网络/API/Reranker，不能据此证明生产延迟高；因此不增加lexical/dense/hybrid自动或大模型路由，V1继续默认Hybrid，未来只有在更大规模端到端评估显示收益时再讨论路由；
13. 真实BGE证据：`RUN_BGE_M3_RETRIEVAL_SMOKE=1`、`MODEL_LOCAL_FILES_ONLY=true`及Transformers/Hugging Face离线变量下，固定`BAAI/bge-m3@5617a9f61b028005a4858fdac845db406aefb181`对蘑菇灯手册建立真实向量，并以“这款台灯需要多少伏特供电？”通过Dense/Hybrid找到含`220 V`证据，两路分数均存在且清理成功；实际为`1 passed in 17.88s`，没有下载或联网；
14. 后端全量与工程质量：原样运行`.venv\Scripts\python.exe -m pytest tests/unit tests/integration -q`为`614 passed, 2 skipped, 1 failed in 49.99s`。唯一失败仍是既有索引Service用例硬编码删除`uploads/2026/08/...`，9月真实文件位于`2026/09`而未触发预期解析失败；本步未越权修改。排除该用例后为`614 passed, 2 skipped, 1 deselected in 51.38s`。`ruff check app tests scripts migrations`通过，格式为`216 files already formatted`；Mypy为`Success: no issues found in 110 source files`；`compileall -q app tests scripts`无错误；`pip check`无损坏依赖；`git diff --check`通过；Alembic current/heads均为`20260831_0008 (head)`且`alembic check`无新操作，本步没有迁移；
15. 能证明与不能证明：能证明当前电脑、正式合成语料与真实PostgreSQL上的索引建立、共享权限前置、三路检索、RRF、公开来源、稳定顺序、Fake日常运行、固定本地BGE单文档检索、索引表达式兼容和精确清理闭环。不能证明图文DOCX两条图片事实、事实级Locator 20/20、真实BGE在全部20问的召回率、Reranker提升、最终RAG回答/引用质量、HTTP端到端延迟、并发负载、百万Chunk性能或生产HNSW召回率；
16. 风险与优先排查：检索漏事实先区分上游Parser/Chunk是否已有文字，再看Lexical词条与Dense身份；图文DOCX应先补Office图片OCR/页眉策略，不能靠调RRF掩盖。来源不精确先核对Chunk多Span与当前首锚点映射，再决定事实级范围合同。权限异常先查共享`authorized_active_chunks_statement`及active双指针，不分别修改Dense/Lexical。延迟上升先拆分Query Embedding、Dense SQL、Lexical SQL和RRF耗时，再评估独立Session并发或模式路由；
17. 正式Seed与停止点：所有验证后只运行既有幂等入口`seed_m1 → seed_m2_files → seed_m2_complex_files`恢复。只读复核为10 files、10 documents、10 document_versions、9 document_acl、10 parse pending、10 index pending、0 active Document Version、0 active Index Set、0 document_chunk_sets、0 document_index_sets、0 document_chunks、0 Embedding；Storage为10 uploads、0 parsed、0 chunks、0其他对象；`LR-TL-MUSH-OR01 / DE-FRA`可售125；PostgreSQL 17.11 + pgvector 0.8.6容器healthy；默认Fake、local-only，固定BGE revision未变。M2-16.7与整个M2-16现已完成，明确没有开始M2-17、Reranker、RAG、API、Agent、前端或模式路由，等待用户确认下一阶段方案。
