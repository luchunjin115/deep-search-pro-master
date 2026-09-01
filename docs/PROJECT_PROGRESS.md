# 项目总进度看板

> 本文档是项目进度的统一入口，只保存摘要和阶段链接。  
> 每个阶段的方案、步骤日志和验证结果保存在 `docs/progress/`。  
> 状态枚举：待确认、待开始、进行中、受阻、已完成。  
> 最近更新：2026-09-01

## 1. 当前状态

| 项目 | 当前内容 |
|---|---|
| 当前阶段 | M2：知识库垂直切片（M2-18已完成，等待M2-19方案确认） |
| 阶段状态 | 进行中 |
| 当前步骤 | M2-18.6已完成并收口M2-18：引用验证Service从模型回答提取严格ASCII `[E#]`，再按当前用户、当前ACL、active代次和未删除状态读取持久化Context/Evidence白名单，拒绝伪造、重复、畸形、越界、跨用户和过期引用 |
| 已完成到 | M1已完成；M2已完成M2-01至M2-18。引用验证单元/真实PostgreSQL聚焦`18 passed`、Context/Evidence相邻回归`69 passed`、排除显式Smoke和既有跨月用例后`773 passed, 2 skipped, 1 deselected`；全仓Ruff/240文件格式、114个app模块Mypy、编译、依赖和Alembic门禁通过。Alembic仍为`20260901_0009 (head)`且无漂移；正式Seed已恢复为10/10/10/9、0索引/Context/Evidence，Storage仅10 uploads，M1可售125 |
| 下一动作 | 明确停止，不自动开始M2-19代码。等待用户确认进入M2-19方案讨论；下一阶段才会设计并注册`search_knowledge` Tool。当前没有HTTP知识检索API、Tool、Agent、Qwen回答或前端知识问答 |
| 当前阻塞 | 无M2-18技术硬阻塞；真实Reranker把Recall@8提高22.22个百分点，但本机CPU对约15候选的精排p50/p95约6.70/7.24秒，不适合未经优化直接作为低延迟同步链路。既有跨月硬编码用例仍是全量唯一失败，本轮未越权修改；人工把部分固定UUID集成文件改成非默认顺序可触发既有数据库夹具顺序耦合，目标用例单跑及默认全量顺序正常。图文DOCX 2/20与事实级Locator 16/20仍是上游边界 |

## 2. 里程碑总览

| 里程碑 | 内容 | 状态 | 详细记录或完成依据 |
|---|---|---|---|
| M0 | 产品、技术、数据、评估与协作基线 | 已完成 | [查看M0详细记录](progress/M0_DESIGN.md) |
| M1 | 库存查询垂直切片 | 已完成 | [查看M1详细记录](progress/M1_INVENTORY_QUERY.md)；M1-01至M1-21全部完成并验证 |
| M2 | 自建RAG垂直切片 | 进行中 | [查看M2方案与实施记录](progress/M2_KNOWLEDGE_RAG.md)；M2-16检索闭环、M2-17 Reranker及M2-18 Context/Evidence/引用验证已完成，等待M2-19方案确认 |
| M3 | 多模态商品分析 | 待开始 | 等待M2完成 |
| M4 | 深度研究与报告 | 待开始 | 等待M3完成 |
| M5 | 评估、加固与作品化 | 待开始 | 等待M4完成 |

## 3. 阶段记录目录

| 阶段 | 文件 | 说明 |
|---|---|---|
| M0 | [M0_DESIGN.md](progress/M0_DESIGN.md) | 总体方案、协作基线和进度结构 |
| M1 | [M1_INVENTORY_QUERY.md](progress/M1_INVENTORY_QUERY.md) | 现状、边界、21个实施步骤、验证矩阵和待确认决定 |
| M2 | [M2_KNOWLEDGE_RAG.md](progress/M2_KNOWLEDGE_RAG.md) | M2-01至M2-15方案、逐步验证日志、完成证据与风险边界 |
| M3 | 尚未创建 | 进入M3方案讨论时创建 |
| M4 | 尚未创建 | 进入M4方案讨论时创建 |
| M5 | 尚未创建 | 进入M5方案讨论时创建 |

## 4. 已确认的关键决策

| 决策 | 结论 |
|---|---|
| 大模型 | 千问负责主推理和多模态理解 |
| Agent编排 | LangGraph |
| 业务数据库 | PostgreSQL |
| 向量存储 | pgvector |
| RAG | 自建，不使用RAGFlow |
| Embedding | BGE-M3 |
| Reranker | BGE-Reranker |
| 互联网搜索 | Tavily自定义工具 |
| V1文件存储 | 本地文件系统 + Storage抽象 |
| MinIO | 后置，不进入V1核心范围 |
| 数据 | 明确标注的合成演示数据 |
| 开发方式 | 教学式协作、阶段先确认、一次一个可验证小步骤 |
| 进度结构 | 总看板 + 每阶段独立详细记录 |
| V1业务Skill | 5个，按M3/M4逐步落地；简单查询不封装为Skill |
| V1 Agent Tool | 目标约13个；单个Agent或Skill一次只获得1至5个 |
| Harness | 作为服务端运行时护栏，随M1至M5逐步增强 |
| 模型与Tool | 模型只提出当前白名单内的Tool调用建议；LangGraph与Harness审核，后端执行，模型不直接调用数据库 |
| M1 LangGraph | 五个显式节点；商品名称路径最多两轮建议/两次Tool，明确SKU路径一次建议/一次Tool，不允许开放式循环 |
| MCP | V1不引入；真实外部连接器或跨客户端复用时再评估 |
| M2复杂文档解析 | 保留PyMuPDF/python-docx/openpyxl/Pandas作为普通文件Native快速路径；Docling只作为安全文件的复杂布局/OCR增强后端；Marker与LlamaParse暂不引入 |
| M2解析产物 | Native与Docling必须汇合为项目自有Canonical Parsed Artifact JSON；Markdown只作派生视图，不作为唯一事实底稿 |
| M2解析评估 | 保留不可变`m2-v1`普通语料，新增版本化`m2-complex-v1`复杂语料；必须比较Native、Docling与最终Router并记录定位、质量与资源基准 |
| M2 Docling运行基线 | 固定Docling 2.123.1、RapidOCR 3.9.2、ONNX Runtime 1.23.2，本地CPU/4线程/PyPdfium2/Heron ONNX/TableFormer accurate；远程服务与外部插件关闭 |
| M2 Office解析边界 | DOCX视觉文字和XLSX公式不能只依赖Docling；Canonical Artifact与后续Router必须无损保留Native结构事实，并按需叠加Docling增强 |
| M2统一解析合同 | `m2-canonical-parsed-artifact-v1`以结构化Block为事实底稿，保存源/内容SHA、Parser与Adapter版本、定位、公式和统一警告；Markdown只作确定性派生视图 |
| M2解析路由 | 所有文件先过扩展名/文件签名与Native安全限制；再自动检查低文字、双栏、PDF表格、DOCX媒体和XLSX合并单元格，普通文件选Native，复杂PDF选Docling，复杂DOCX/XLSX走Hybrid并继续以Native作为Office事实底稿；CSV不进入Docling |
| M2解析发布 | `DocumentParserService`使用短事务原子领取版本，在事务外解析，按`{tenant}/parsed/{year}/{month}/{version_id}.json`不可覆盖发布`m2-routed-parsed-document-v1`；成功写ready，失败删半成品并写failed，同版本可安全重试 |
| M2分块合同 | M2-12只消费选中Canonical Artifact；`m2-canonical-chunk-artifact-v1`保留文本、表格、公式、单元格和来源Span，固定`m2-unicode-token-counter-v1`和600/700/100初始预算，由版本/Artifact/Chunker/Counter/配置推导确定性Chunk Set ID并计算配置、单Chunk和输出Hash |
| M2表格分块 | DOCX表格、PDF/Docling `document_table`、XLSX Sheet和CSV统一生成结构化Table Chunk；表头与1行数据重叠显式标记上下文，超宽行按不切断合并跨度的列窗口拆分，单个不可容纳单元格安全失败；文本/表格按Canonical Block顺序合并 |
| M2 Chunk Set元数据 | `document_chunk_sets`以确定性UUID登记文档版本、Canonical输入Hash、Chunker/Counter/配置、执行状态、Artifact Hash/Storage Key与统计；复合外键防跨租户/跨文档错挂，PostgreSQL约束拒绝ready/failed半成品 |
| M2 Chunk发布 | `DocumentChunkService`有界验真解析JSON、原子领取确定性Chunk Set、事务外切块并按`{tenant}/chunks/{year}/{month}/{chunk_set_id}.json`不可覆盖发布；失败清理半成品并可用同一ID重试，只复用字节完全相同的孤儿对象 |
| M2 Chunk检索存储 | `document_chunks`一行对应一个Canonical Chunk；普通列与双重复合外键固定tenant/document/version/Chunk Set关系，JSONB保存M2-12定位和表格结构，独立`fts_text`生成`simple` FTS并使用GIN，Embedding保持可空`vector(1024)`并预建余弦HNSW，真实向量生成留到M2-14 |
| M2索引代次与active指针 | 新增确定性`document_index_sets`保存Chunk Set、完整Embedding身份、FTS版本、状态、attempt和统计；Version active指针通过tenant/document/version/status复合外键只能指向自己的ready Index Set，Chunk唯一边界按Index Set隔离 |
| M2检索公开合同 | 请求体只接受去空白后的有界`query`，候选数量只由服务端集中配置；Dense/Lexical单路未命中用`None`表达，所有公开分数拒绝NaN/Infinity，排名为正整数；PDF/DOCX/XLSX/CSV使用类型化公开定位，响应不含tenant、ACL、Storage Key、路径、向量、SQL或原始异常 |
| M2版本化中文FTS | 文档与查询统一使用`m2-fts-jieba-search-v1`：固定jieba 0.42.1及词典SHA-256、search模式、`HMM=False`、NFKC/casefold和Unicode字母数字过滤；0008允许旧raw与新版Index Set共存，存在新版数据时拒绝静默降级 |
| M2共享检索候选边界 | Dense与Lexical未来必须从`RetrievalRepository.authorized_active_chunks_statement(CurrentUser)`取得同一份排序前候选；tenant只来自可信CurrentUser，并统一限制未软删除Document/File、active Version、active ready Index Set、Chunk代次归属及owner/company_owner/user/role/market ACL |
| M2 Dense检索 | `DenseRetrievalService`只用QUERY用途生成一个有界归一化向量；Repository从共享候选边界追加完整Embedding身份、pgvector余弦距离、UUID稳定tie-break和服务端Top K；不兼容身份、Provider故障、数据库超时/不可用均返回类型化安全错误 |
| M2 Lexical检索 | `LexicalRetrievalService`复用固定Builder生成有界、去重的OR tsquery；Repository从同一共享候选边界追加FTS Builder身份、`@@`命中、`ts_rank_cd(..., 32)`、UUID稳定tie-break和服务端Top K；不查询Embedding，不暴露search_vector或SQL |
| M2 Hybrid与RRF | `HybridRetrievalService`完整执行Dense与Lexical后按`chunk_id`去重，以`1/(60+rank)`相加融合；保留单路未命中的`None`和两路原始名次/分数，RRF同分按Chunk UUID升序，最终Top K在融合后应用；任一路失败不返回伪Hybrid成功 |
| M2检索模式路由 | V1当前不新增lexical/dense/hybrid自动路由或大模型路由；先完成默认Hybrid闭环，并在M2-16.7记录真实延迟与质量，再决定是否值得增加路由复杂度；任何未来路由都不得改变tenant、ACL或服务端安全上限 |
| M2检索验收 | 正式Fake 35 Chunk/20问验证Hybrid文档20/20、证据18/20和确定性20/20；本机同步Hybrid p95约43.29 ms，样本规模不足以支持新增模式路由，继续默认Hybrid并把路由评估后置；真实BGE只做显式离线单文档Smoke |
| M2 Context公开合同 | `m2-context-bundle-v1`只公开获权文档身份、定位、正文Hash、局部`[E1]`至`[E12]`和预算事实；空证据用`supported=false`与空片段表达，服务端固定4000 Token、12片段、邻居窗口1的初始上限，公开知识Evidence不含tenant、ACL、Storage Key、路径或SQL |
| M2 Context/Evidence持久化 | `context_artifacts`保存用户、检索快照/配置/内容/幂等Hash与预算；`evidences`以分支CHECK兼容M1 database和M2 knowledge/user_file，并用复合外键绑定完整文档代次。已有Context或文档Evidence时0009降级明确拒绝，不静默丢审计证据 |
| M2 Context安全重取 | Context不能直接信任Reranker响应中的正文或元数据；Repository用可信`CurrentUser`复用tenant/ACL/active Version/active ready IndexSet/软删除安全门，同时核对Document/Version/IndexSet/Chunk四重身份，再从刚确认的同一ChunkSet与IndexSet取得最多前后各1个邻居。锚点和窗口固定两次批量SQL，不随候选数形成N+1查询 |
| M2 Context构建 | Context Builder只消费安全重取窗口；按Reranker名次先保锚点再补前后邻居，以Chunk UUID及规范正文Hash去重。文本overlap只有在真实前驱同时入选且前缀/后缀一致时裁剪；表格只移除明确标为`repeated_as_context`的重复行。最终片段按文档自然窗口顺序排列并严格受4000 Token/12片段上限约束；Context、Evidence和内容Hash均确定性生成，但M2-18.4只返回内存产物、不写数据库 |
| M2 Context/Evidence持久化服务 | Evidence Service不直接相信可构造的`BuiltContext`：先复算快照/配置/内容/身份Hash及UUID，再通过共享安全门按当前`CurrentUser`锁定并重新核对最终Chunk。ContextArtifact与全部Evidence使用确定性ID和PostgreSQL冲突忽略后逐字段验真，在同一嵌套保存点中全部成功或全部回滚；Service只flush、不commit，保留请求事务所有权 |
| M2引用验证 | 只接受严格ASCII大写`[E1]`至`[E12]`，允许按答案出现顺序引用当前Context白名单的任意子集，但拒绝重复、畸形、大小写/空格/全角变体和越界标签；验证时按当前用户重新检查tenant、Context归属、文档ACL、active Version/Index Set及软删除状态。空Context只允许零引用；支持型Context至少需要一个引用；返回的Evidence ID只来自数据库映射，不信任模型自报 |

## 5. 当前阻塞与跨阶段问题

当前无阻塞问题。

只在这里记录影响整个项目或多个阶段的问题；阶段内部问题写入对应的 `docs/progress/M*.md`。

## 6. 最近完成

- 2026-08-27：完成并确认三份总体设计文档；
- 2026-08-27：建立教学式协作规则；
- 2026-08-28：将进度记录调整为总看板与分阶段日志结构。
- 2026-08-28：确认并同步Skill、Tool、Harness和MCP的边界、清单与分阶段路线。
- 2026-08-28：建立本地与GitHub远端的Git基线，将项目方案安全推送到`origin/main`。
- 2026-08-28：完成M1库存查询垂直切片详细实施方案，阶段保持“待确认”，未开始运行代码开发。
- 2026-08-28：完成M1-01新目录、集中配置和依赖边界；7个单元测试及代码、类型、编译、依赖检查通过。
- 2026-08-28：完成M1-02 PostgreSQL 17.11容器、健康检查、本机5433安全映射和命名卷持久化验证；未启动Redis。
- 2026-08-28：完成M1-03 SQLAlchemy连接管理、请求级提交/回滚/释放、真实数据库健康检查和安全503响应；15个测试通过，数据库未残留测试表。
- 2026-08-28：完成M1-04租户、用户、角色、市场范围模型和首个Alembic迁移；升级/回退/再升级及数据库约束验证通过，四张身份表保持空表等待Seed。
- 2026-08-28：完成M1-05商品、SKU、规格、仓库、库存快照模型和第二个Alembic迁移；租户一致性、唯一性和库存数量约束通过真实PostgreSQL验证，五张新表保持为空。
- 2026-08-28：完成M1-06会话、消息摘要、Agent运行、Tool调用和Evidence模型及第三个Alembic迁移；trace、JSON、状态、来源和跨运行外键约束通过验证，M1计划的14张业务表全部就位且保持为空。
- 2026-08-28：完成M1-07 `m1-v1`可重复合成演示数据；四个账号、三类角色、DE/FR权限样本、蘑菇灯规格和两仓库存已写入PostgreSQL，德国仓关键答案固定为125，36项测试通过。
- 2026-08-28：完成M1-08严格Pydantic数据合同；认证、聊天、商品、库存、Evidence、两个Tool统一外壳和10类错误码已冻结，非法SKU/市场/额外SQL字段/库存公式等边界通过17项Schema测试，全量53项测试通过。
- 2026-08-28：完成M1-09商品与库存Repository；精确SKU/名称/别名、歧义候选、租户与DE/FR隔离、每仓最新快照、参数绑定和真实PostgreSQL statement timeout通过8项集成测试，全量61项测试通过。
- 2026-08-28：完成M1-10商品规格Service；0/1/多候选、无规格、非演示或非法内部数据映射为严格结果或安全错误，真实Seed可将“蘑菇灯”解析为SKU和4条规格，全量68项测试通过。
- 2026-08-28：完成M1-11库存查询与数据库Evidence Service；最新快照150/20/5计算为可售125，零库存、缺失、多仓、非法数据和数据库异常具有安全行为，Evidence在成功返回前与运行及Tool调用关联并通过真实PostgreSQL验证，全量78项测试通过。
- 2026-08-28：完成M1-12认证内核与RunContext；四个Seed账号可通过Argon2验证并获得短期JWT，Token只保存身份指针且每次从PostgreSQL刷新状态/角色/市场范围，伪造和过期Token、禁用用户、并发上下文隔离通过验证，全量89项测试通过。
- 2026-08-28：完成M1-13 ToolRegistry与PermissionGuard；默认白名单严格只有两个版本化只读Tool，tenant、角色和市场范围在业务调用前确定性检查，真实Seed验证DE运营查DE、FR运营查FR允许且FR运营查DE拒绝，全量98项测试通过。
- 2026-08-28：完成M1-14 ExecutionBudget、基础Trace与同步Harness执行外壳；模型/Tool次数、重复签名、总时间及单Tool时限受控，AgentRun/ToolCall独立事务记录成功、拒绝、超时和脱敏错误，业务回滚后审计仍保留，全量111项测试通过。
- 2026-08-28：完成M1-15两个正式Agent Tool及用户评审补充；商品规格和库存查询均通过统一Harness调用既有Service，库存成功结果包含数据时间及Evidence ID；Registry描述和输入JSON Schema已明确用途、返回、限制、字段说明与必填项，越权、业务错误和未知异常形成安全ToolEnvelope，全量121项测试通过。
- 2026-08-28：完成并按用户评审补充修正M1-16 Mock与Qwen Provider边界；模型现在能看到当前流程允许的安全Tool说明并返回强类型调用建议，但不能执行Tool或访问数据库；未登记/未授权Tool、额外SQL参数、非法市场、篡改后端可信SKU及多Tool建议均被拒绝，全量149项通过、付费冒烟1项默认跳过。
- 2026-08-28：完成M1-17五节点LangGraph库存最小流程；标准问题通过Mock两轮建议、Harness和两个正式Tool查询真实PostgreSQL Seed，返回可售125、数据时间及Evidence；明确SKU走一次建议/一次Tool，越权、非目标问题、模型预算、商品错误、数据库超时和未知Provider异常均安全终止，全量163项通过、付费冒烟1项默认跳过。
- 2026-08-28：完成M1-18 FastAPI后端闭环；公开登录、当前身份、会话、同步聊天和Evidence详情接口，JWT身份刷新、会话归属、租户/市场Evidence范围、统一HTTP错误、请求事务、OpenAPI和CORS通过真实PostgreSQL验证，全量168项通过、付费冒烟1项默认跳过。
- 2026-08-28：完成M1-19最小Next.js桌面端；登录、会话、自然语言提问、同步执行状态、回答和数据库Evidence侧栏已经接通M1 API合同，4项组件交互测试、TypeScript、ESLint、生产构建和依赖安全检查通过；当前运行环境没有可用的受控浏览器实例，因此真实浏览器点击与截图留到M1-20验证。
- 2026-08-29：完成M1-20故障矩阵、API集成和Playwright浏览器端到端回归；后端172项通过、1项真实Qwen付费冒烟跳过，前端4项组件测试和4项Chromium真实全链路测试通过，数据库与运行数据已恢复到合成Seed初始基线。
- 2026-08-29：完成M1-21和M1阶段收口；新增安全公开API演示脚本及3项测试，从全新`deep-search-postgres-data`卷复现三次迁移、Seed、DE成功查询/Evidence和FR越权拒绝，后端175项通过、1项付费冒烟跳过，前端组件与Chromium回归各4项通过，M1-01至M1-21全部完成。
- 2026-08-29：完成M2开始前只读盘点和M1基线复验；确认当前PostgreSQL镜像不含pgvector、M2依赖与Storage尚未建立，提交M2知识库垂直切片26步实施方案，阶段保持“待确认”，未开发M2运行代码。
- 2026-08-29：用户确认M2方案后完成M2-01；新增Storage、上传、BGE和混合检索集中配置，冻结M2直接依赖声明与新旧AST导入边界；后端191项通过、1项付费冒烟跳过，M1 Seed恢复为125；未安装大型模型依赖、切换pgvector镜像或实现后续业务。
- 2026-08-29：完成M2-02；固定PostgreSQL 17.11 Alpine linux/amd64基础镜像摘要与pgvector 0.8.6提交，保留现有命名卷并启用`vector`；全新卷初始化、普通重启、旧镜像备份恢复、M1表与125均通过，后端197项通过、1项付费冒烟跳过；未建业务向量表或开始M2-03。
- 2026-08-29：完成M2-03；新增只接受规范UUID对象Key的Storage合同和LocalStorage，支持分块写入、SHA-256、同目录临时文件原子发布、重复Key不覆盖、根目录/路径穿越/符号链接防护与安全异常；后端227项通过、3项按设计跳过，Alembic仍为`20260828_0003 (head)`，未创建上传API、文档模型或迁移。
- 2026-08-29：完成M2-04；新增`files/documents/document_versions/document_acl` ORM与`20260829_0004`迁移，数据库强制tenant/owner、Storage Key、版本号/hash、active版本归属、角色/用户/市场ACL和软删除边界；升级/回退/再升级及9项聚焦测试通过，全量236项通过、3项按设计跳过，pgvector 0.8.6与M1可售125保持。
- 2026-08-29：完成M2-05；新增严格文件/文档Schema、tenant/owner/用户/角色/市场ACL固定Repository查询及文件/解析/索引状态Service，重复hash与软删除安全边界通过真实PostgreSQL验证；41项聚焦测试、Ruff、核心Mypy和公共导入检查通过，未新增迁移、API、Parser或检索。
- 2026-08-29：完成M2-06；新增受JWT保护的PDF/DOCX/XLSX/CSV批量上传、列表、状态、`file_id`下载和软删除API，验证类型/大小/hash/权限以及Storage与数据库失败补偿；后端全量267项通过、3项按设计跳过，Alembic仍为`20260829_0004 (head)`，M1可售125保持，未实现Parser、索引或前端。
- 2026-08-29：完成M2-07；新增有界PyMuPDF文本解析器，按1开始页码输出嵌入文字、字符数、图片数和字号标题线索，并区分空页、低文字和疑似扫描页而不执行OCR；ReportLab合成夹具渲染检查通过，后端全量281项通过、3项按设计跳过，未接解析API、数据库状态或索引。
- 2026-08-29：完成M2-08；新增有界python-docx解析器，按正文顺序输出标题路径、段落、表格及1开始的块/段/表/行/列定位，并在解压前限制ZIP成员、展开量和压缩比；18项DOCX测试及后端全量305项通过、3项按设计跳过。当前机器缺少LibreOffice/soffice与Poppler，DOCX视觉渲染门禁未完成，已按documents技能执行并通过可重复OOXML结构审计；未接解析调度、数据库状态或索引。
- 2026-08-29：完成M2-09；新增有界openpyxl/Pandas解析器，稳定输出XLSX的Sheet/表头/物理行/单元格与公式边界，以及CSV的UTF-8-SIG/UTF-8/GB18030编码、受限分隔符和逻辑行范围；XLSX 16项、CSV 12项及后端全量345项通过、3项按设计跳过，M1关键可售库存仍为125，未写业务表或接入解析调度与索引。
- 2026-08-29：完成M2-10；新增可重复生成的PDF说明书、两份DOCX SOP/合规清单、XLSX报价与CSV运营表，以及`m2-v1`定义、黄金定位、manifest和幂等Seed；实际Storage与PostgreSQL保持5文件/5文档/5版本/5 ACL且解析/索引仍pending，后端全量348项通过、3项按既有条件跳过，M1可售125保持。PDF逐页视觉检查和DOCX/XLSX结构检查通过；当前环境缺DOCX标准渲染与artifact-tool运行时，未声称完成这两类视觉门禁。
- 2026-08-30：确认M2-11解析方案修订；保留现有四类Native Parser作为普通文件快速路径，引入Docling作为复杂文档本地增强后端，新增`m2-complex-v1`正式评估语料方向，并将M2-11细分为复杂语料、真实基准、Canonical Artifact、路由和状态闭环5个逐步授权子步骤；本次只更新方案文档，尚未生成语料、安装依赖或修改运行代码。
- 2026-08-30：完成M2-11.1；新增可重复的扫描PDF、双栏PDF、复杂表格PDF、图文DOCX和多区域XLSX共5份`m2-complex-v1`正式复杂评估文件，固定10条Golden、SourceLocator、Docling路由/OCR预期、manifest及幂等Storage/PostgreSQL Seed；聚焦测试3项和后端全量351项通过、3项按既有条件跳过，Ruff/Mypy/依赖检查通过，真实Word/Excel与PDF逐页视觉检查通过，旧`m2-v1`四个核心文件哈希和M1可售125保持；尚未安装或运行Docling。
- 2026-08-30：完成M2-11.2；固定Docling 2.123.1、RapidOCR 3.9.2、ONNX Runtime 1.23.2及约699MiB哈希门禁模型缓存，在Python 3.11/CPU/4线程离线运行5份复杂文件；Docling 7/10、Native 6/10，扫描PDF由0/2提升至2/2，最慢36.99秒、最大额外RSS约1439MiB；同时确认标准Docling不能替代DOCX视觉OCR和XLSX公式底稿。真实聚焦44项、默认后端全量357项通过，4项按条件跳过，本步Ruff/Mypy/依赖/应用导入通过；等待单独确认M2-11.3。
- 2026-08-30：完成M2-11.3；新增`m2-canonical-parsed-artifact-v1`、四类Native Adapter、Parser无关警告、哈希自校验、可选页面坐标和确定性Markdown派生；`m2-v1`与`m2-complex-v1`共10份文件全部无损转换，9个XLSX公式、PDF页码/标题、DOCX顺序/标题路径/表格和CSV行范围保持。聚焦103项、默认后端全量363项通过，4项按条件跳过，Ruff/核心Mypy/依赖/公共导入通过；等待单独确认M2-11.4。
- 2026-08-30：完成M2-11.4；新增隔离的Docling Snapshot/Adapter、自动格式特征与质量门禁、Native-first Parser Router、文件签名复核、Office Hybrid事实保护、安全增强错误与正式Router报告。`m2-v1`普通集全部保持Native；`m2-complex-v1`不传人工复杂度标签也能真实离线路由为3份PDF选Docling、DOCX/XLSX选Hybrid，5/5进入Docling，最终8/10 Golden，其中扫描PDF由Native 0/2提升为2/2、图文DOCX仍0/2、XLSX以Native保留6个公式并保持2/2。安全测试确认加密、损坏、类型伪装、ZIP Bomb和超限输入均在Docling前拒绝，超时/OOM/第三方异常统一为固定错误；聚焦70项、真实Router Smoke 1项和默认全量370项通过，5项按条件跳过，Ruff、核心Mypy、依赖和公共导入通过；等待单独确认M2-11.5。
- 2026-08-30：完成M2-11.5并收口M2-11；新增`DocumentParserService`、原子`claim/complete/fail`状态更新、`m2-routed-parsed-document-v1`版本化JSON发布、安全结果Schema和固定解析错误。真实PostgreSQL/LocalStorage验证成功发布、源文件失败后重试、数据库完成提交失败后的Artifact删除、非所有者拒绝和失败新版本不替换旧active版本；公开结果不含Storage Key，JSON保存两路Parser版本、路由原因、警告、对照和Hash。聚焦152项通过、2项按条件跳过，全量375项通过、5项按条件跳过，Ruff、7个核心文件Mypy、依赖和公共导入通过；迁移仍为`20260829_0004 (head)`，正式Seed已恢复为M1可售125及10文件/10文档/10个pending版本；等待单独确认M2-12。
- 2026-08-30：用户确认M2-12方案后完成M2-12.1；新增`m2-canonical-chunk-artifact-v1`严格合同、文本/表格Chunk、来源Span、表格公式/单元格语义、确定性UUIDv5 Chunk Set ID、配置/单Chunk/整体Hash和`m2-unicode-token-counter-v1`，补齐600目标/700硬上限/100重叠等集中配置。聚焦`52 passed`，有效全量`387 passed, 5 skipped`，Ruff全范围、核心Mypy、编译、依赖和Alembic check通过；迁移仍为`20260829_0004 (head)`，Seed恢复为M1可售125及M2 10文件/10文档/10个pending版本/9 ACL；本步未实现真正切块算法、迁移、Storage发布、Embedding或检索，等待单独确认M2-12.2。
- 2026-08-30：完成M2-12.2；新增Parser无关的确定性文本规范化和PDF/DOCX结构感知Chunker，保留Canonical字符偏移、标题路径、页码、跨页Span和显式列表标记，按段落/句子/分句/空白/Token硬边界递归兜底，重复页眉页脚进入排除审计，表格形成硬边界并返回待处理Block ID。聚焦`103 passed`、全量`396 passed, 5 skipped`，Ruff全范围、5个Chunk核心文件Mypy、编译、依赖、Alembic check和真实Native PDF/DOCX链路通过；迁移仍为`20260829_0004 (head)`，Seed恢复为M1可售125及M2 10文件/10文档/10个pending版本/9 ACL；等待单独确认M2-12.3表格切块。
- 2026-08-31：完成M2-12.3；新增四类Canonical结构化表格Chunker和文档级顺序合并，表头及默认1行数据重叠显式标记上下文，保留DOCX/PDF标题路径与页码/Bounding Box、XLSX Sheet/范围/公式/缓存、CSV编码/行范围和合并跨度；超宽行按完整单元格列窗口拆分，不可容纳单元格安全失败。聚焦`133 passed`、全量`408 passed, 3 skipped`，Ruff全范围、核心Mypy、编译、依赖、Alembic check通过；迁移仍为`20260829_0004 (head)`，pgvector 0.8.6与PostgreSQL healthy，Seed恢复为M1可售125及M2 10文件/10文档/10个pending版本/9 ACL；等待单独确认M2-12.4。
- 2026-08-31：完成M2-12.4；新增`document_chunk_sets` SQLAlchemy模型和`20260831_0005`迁移，以复合外键、确定性ID、完整配置/Hash、四态生命周期、受限Storage Key和一致统计登记重切元数据，PostgreSQL硬约束拒绝跨文档错挂及ready/failed半成品。聚焦`85 passed`、全量`413 passed, 3 skipped`，Ruff全范围、整个app Mypy、编译、依赖、迁移往返和Alembic check通过；Seed恢复为M1可售125及M2 10文件/10文档/10个pending版本/9 ACL，新表保持0行；等待单独确认M2-12.5。
- 2026-08-31：完成M2-12.5；新增`DocumentChunkService`、Chunk Set原子领取/完成/失败Repository SQL、安全发布Schema/错误和最终Artifact跳过表格审计，真实跑通Parser→Canonical→文本/表格Chunk→不可覆盖Storage JSON→PostgreSQL ready链路，并验证失败同ID重试、数据库失败补偿、相同孤儿复用、二次领取拒绝、权限/状态/篡改与配置重切。聚焦扩大集合`135 passed`、Service单独`7 passed`，全量`421 passed, 3 skipped`，Ruff、95文件Mypy、编译、依赖和Alembic check通过；迁移保持`0005 head`，Seed恢复为M1可售125及M2 10/10/10/9和10个pending版本，正式Chunk Set/JSON保持0；等待单独确认M2-12.6。
- 2026-08-31：完成M2-12.6并收口M2-12；新增可重复的真实Golden发布/验收/恢复脚本及3项日常测试，并修复CSV尾部空单元格文本在合同校验前后Hash不一致的问题。10份`m2-v1`/`m2-complex-v1`文件经真实Parser Service→Chunk Service→Storage/PostgreSQL发布35个Chunk（27文本/8表格，最大394 Token），18/20内容与定位同时命中，唯一失败仍是已知图文DOCX 0/2；10/10逐字节确定性重建和Canonical顺序通过。全量`424 passed, 3 skipped`，Ruff、95文件Mypy、编译、依赖和Alembic check通过；20个临时JSON已精确删除，Seed恢复为M1可售125及M2 10/10/10/9、10个pending版本、0 Chunk Set/发布JSON；停止并等待M2-13授权。
- 2026-08-31：完成M2-13；新增`document_chunks` ORM与`20260831_0006`迁移，一行保存一个文本/表格Chunk及完整定位JSONB，复合外键和唯一/格式/结构约束拒绝跨租户、跨文档、跨版本、错Chunk Set和重复/脏行；独立`fts_text`生成PostgreSQL `simple` FTS并建立GIN索引，可空`vector(1024)`建立余弦HNSW索引，Embedding模型/版本只允许与真实向量同时出现。迁移往返、固定关键词、固定向量排序和级联删除通过真实PostgreSQL；全量`429 passed, 3 skipped`，Ruff、95文件Mypy、编译、依赖和Alembic check通过；正式Seed恢复为M1可售125及M2 10/10/10/9、10个pending版本、0 Chunk Set/Chunk/发布JSON；停止并等待M2-14授权。
- 2026-08-31：完成M2-14；新增硬件无关`EmbeddingProvider`合同、确定性Fake和本地BGE-M3 Provider，冻结document/query用途、1024维有限归一化校验、cache key、并发首次加载、OOM batch降级、本地快照与强制离线边界；固定`BAAI/bge-m3@5617a9f61b028005a4858fdac845db406aefb181`，真实CPU Smoke/匿名基准和离线复跑通过。全量`476 passed, 5 skipped`，Ruff、100个源码文件Mypy、编译、依赖和Alembic检查通过；正式Seed保持0 Chunk/0 Embedding，未实现索引或检索。
- 2026-08-31：完成M2-15开始前只读盘点并提交待确认方案；核对`main`与HEAD `960559a13281555f2b3d52d27e9e4fc7552fcc05`、保留M2-12/13/14未提交改动，确认PostgreSQL/pgvector、`0006 head`、10/10/10/9、10个parse/index pending、M1可售125及Storage 10 uploads/0 parsed/0 chunks。推荐新增确定性Index Set，分6个小步骤实现幂等领取、失败重试、Chunk逐行保存和版本/索引原子激活；本轮只修改进度文档，没有编码、迁移、模型下载或数据库写入。
- 2026-08-31：用户确认M2-15方案后完成M2-15.1；新增`document_index_sets` ORM与`20260831_0007`迁移，Version active指针通过tenant/document/version/status复合外键只能指向自己的ready索引代次，Chunk新增Index Set归属和cache key并按代次判重；真实验证跨边界、状态形状、同Chunk Set多Embedding代次、active-ready、级联及`0006→0007→0006→0007`。聚焦`70 passed`、全量`485 passed, 5 skipped`，Ruff检查、100文件Mypy、编译、依赖、Alembic check和本步文件格式检查通过；正式Seed恢复为10/10/10/9、10个pending版本、0 Chunk Set/Index Set/Chunk/Embedding、M1可售125及Storage 10 uploads；停止等待M2-15.2。
- 2026-08-31：完成M2-15.2；新增确定性Index Set身份与Chunk行Mapper，完整Hash覆盖Provider/model/revision/pooling/max length/normalize/precision/1024维，使用`retrieval_text`复算cache key并以strict zip配对文本、表格JSON、向量、raw FTS和审计字段，拒绝数量/顺序/用途/身份/Hash/向量/跨边界篡改。新测试`6 passed`、聚焦`120 passed`、全量`491 passed, 5 skipped`，Ruff、本步格式、111文件Mypy、编译、依赖和Alembic检查通过；正式Seed恢复为10/10/10/9、10个pending版本、0 Chunk Set/Index Set/Chunk/Embedding、M1关键可售125及Storage 10 uploads；本步无SQL、API、模型下载或检索，停止等待M2-15.3。
- 2026-08-31：完成M2-15.3；新增`DocumentIndexRepository`，以Version/Document/File/Chunk Set行锁、确定性upsert和attempt编号实现单领取、failed重试、过期执行者拒绝、ready复用，并在同一短事务批量保存Chunk、核对统计、标记Index Set ready及切换Version/Document双active指针。真实唯一约束故障证明新候选0 Chunk且旧active/旧Chunk完整保留；同Version重建、新Version切换、Document/File软删除和跨tenant/document拒绝通过。Repository`8 passed`、聚焦`42 passed`、全量`499 passed, 5 skipped`，Ruff、本步格式、113文件Mypy、编译、依赖及Alembic检查通过；无需迁移，正式Seed恢复为0 Index Set/Chunk/Embedding和Storage 10 uploads；停止等待M2-15.4。
- 2026-08-31：完成M2-15.4；新增`DocumentIndexService`，复用M2-11/12 ready Artifact并串起claim→分批Embedding→Mapper→原子保存，解析/切块/模型/数据库失败均安全登记，同ID重试attempt递增；重复ready跳过Provider且复核实际Chunk统计，129段按128+1保持顺序，同Version新Embedding和新Version均在成品ready后才切active。新增11项测试，聚焦`65 passed`、全量`510 passed, 5 skipped`，Ruff、102文件Mypy、编译、依赖及Alembic检查通过；无需迁移，正式Seed恢复为10/10/10/9、10个pending版本、0 Chunk Set/Index Set/Chunk/Embedding及Storage 10 uploads；停止等待M2-15.5。
- 2026-08-31：完成M2-15.5；新增三条受认证Documents API，接通创建文档、追加版本和显式同步索引，严格响应不暴露tenant/Storage/path/vector；真实FastAPI/PostgreSQL验证首次与重复索引、Chunk不增行、V1在V2 ready前保持active、company_owner完成后原子切V2、ACL读者/跨边界安全404、409/422/500及Provider恢复后同URL重试。OpenAPI精确只有三条Documents写入路径且无检索功能；新增5项测试，全量`515 passed, 5 skipped`，Ruff、101文件Mypy、编译、依赖及Alembic检查通过；无需迁移，正式Seed恢复为10/10/10/9、10个pending版本、0 Chunk Set/Index Set/Chunk/Embedding及Storage 10 uploads；停止等待M2-15.6。
- 2026-08-31：完成M2-15.6并收口M2-15；新增可重复的10文档Fake索引验收脚本、验收判定测试、显式离线BGE-M3单文档Smoke和M2-15边界哨兵。正式整链得到10 ready、35 Chunk（27文本/8表格）、35 Embedding/FTS，首次故障第2次重试成功，重复10次全部复用且Provider调用和Chunk数不增长；真实BGE固定模型/revision索引与清理通过。全量`518 passed, 6 skipped`，Ruff lint/194文件格式、104文件Mypy、编译、依赖、Alembic和Docker健康检查通过；恢复后正式Seed为10/10/10/9、10个parse/index pending、0 active/Chunk Set/Index Set/Chunk/Embedding，Storage 10 uploads、0 parsed/chunks JSON，M1指定库存125。未实现任何M2-16检索功能，停止等待下一阶段方案确认。
- 2026-08-31：完成Git同步后的本机环境恢复与全量复验；补齐`pgvector/jieba/FlagEmbedding`，启动PostgreSQL 17.11 + pgvector 0.8.6并把Alembic从`0004`升级到`20260831_0007 (head)`，下载固定`BAAI/bge-m3@5617a9f61b028005a4858fdac845db406aefb181`本地快照并通过离线Embedding `2 passed`及真实索引`1 passed`。修复Chunk Set迁移测试遗漏固定`created_at`导致UTC 10:01后必失败的时间夹具，后端全量`516 passed, 8 skipped`，前端组件`4 passed`、TypeScript、ESLint、Next.js生产构建及Chromium端到端`4 passed`；未开始M2-16。
- 2026-08-31：完成M2-16只读盘点、通俗讲解和方案确认；用户两次回复“继续”，确认按“权限前置的Lexical + Dense + Hybrid + RRF检索闭环”实施，但不授权Reranker、RAG、前端、Agent或M2-17。正式Seed已幂等恢复为10文件/10文档/10版本/9 ACL、0 Chunk Set/Index Set/Chunk/Embedding；本轮只记录确认和前置基线，尚未编写检索代码。
- 2026-08-31：完成M2-16.1；新增统一检索请求、四类来源定位、公开候选/文档/Embedding/FTS身份、Dense/Lexical可选分解、RRF和最终排名合同，以及六类固定脱敏检索错误；补齐query/hybrid集中配置与组合校验。TDD先因模块不存在RED，最终聚焦`83 passed`、后端全量`554 passed, 8 skipped`，全仓Ruff lint、105文件Mypy、编译、依赖及Alembic检查通过；全量测试清空共享Seed后已用既有幂等入口恢复10/10/10/9、0索引数据和M1可售125。未实现分词、迁移、SQL、Repository、Service、API或真实模型加载，停止等待M2-16.2确认。
- 2026-08-31：完成M2-16.2；新增版本化`m2-fts-jieba-search-v1`共享Builder，固定jieba 0.42.1、词典Hash、search模式、`HMM=False`与文本规范化，索引Mapper改存稳定中文词条；0008允许旧raw和新版Index Set共存并在新版数据存在时拒绝静默降级。迁移往返、active成品切换、真实索引Service写入和参数化FTS命中通过，聚焦`151 passed`、后端全量`568 passed, 8 skipped`，Ruff、110文件Mypy、编译、依赖及Alembic检查通过；正式Seed恢复为10/10/10/9、0索引数据、Storage仅10 uploads和M1可售125。未实现候选Repository或生产检索SQL，停止等待M2-16.3确认。
- 2026-09-01：完成M2-16.3；新增共享`RetrievalRepository`排序前候选边界，复用现有Document ACL条件，并以可信`CurrentUser`统一限制tenant、未软删除Document/File、active Version、active ready Index Set和Chunk完整代次归属。TDD先因Repository模块不存在RED，最终聚焦`52 passed`；后端全量唯一失败是既有索引Service测试硬编码`2026/08`上传路径在跨月后未删除真实`2026/09`文件，排除该用例后为`572 passed, 6 skipped, 1 deselected`。全仓Ruff/格式、105文件Mypy、编译、依赖、Alembic和差异检查通过；正式Seed恢复为10/10/10/9、0索引数据、Storage仅10 uploads及M1可售125。未实现Embedding查询、Dense/Lexical排序、Top K、Hybrid、RRF、API或真实模型加载，停止等待M2-16.4确认。
- 2026-09-01：完成M2-16.4；新增`DenseRetrievalService`和Repository Dense扩展，先读取共享获权active身份，再按QUERY用途生成归一化向量，以完整Embedding身份过滤并在真实PostgreSQL用pgvector余弦距离、UUID稳定tie-break和服务端Top K排序；四类来源定位和Provider/数据库安全错误均接入M2-16.1合同。TDD先因Dense模块/Record不存在RED，最终聚焦及相邻边界`100 passed`；后端全量唯一失败仍为既有跨月路径用例，排除后`586 passed, 6 skipped, 1 deselected`。全仓Ruff/206文件格式、106文件Mypy、编译、依赖、Alembic和差异检查通过；正式Seed恢复为10/10/10/9、0索引数据、Storage仅10 uploads及M1可售125。日常测试只用Fake/固定向量，未加载真实BGE；未实现Lexical、Hybrid、RRF、API或后续模块，停止等待M2-16.5确认。
- 2026-09-01：完成M2-16.5；新增`LexicalRetrievalService`和Repository FTS扩展，query复用固定jieba Builder后生成参数化OR tsquery，只从M2-16.3共享获权active候选中筛选同版Index Set，并以`ts_rank_cd(..., 32)`、UUID稳定tie-break和服务端Top K排序；Dense与Lexical共用四类安全来源定位。TDD首次按预期因Lexical模块/Record不存在而RED，最终相关回归`129 passed`；后端全量唯一失败仍为既有跨月路径用例，排除后`601 passed, 2 skipped, 1 deselected`。Ruff正式范围/210文件格式、108文件Mypy、编译、依赖、Alembic和差异检查通过；正式Seed恢复为10/10/10/9、0索引数据、Storage仅10 uploads及M1可售125。日常测试未加载真实BGE；未实现Hybrid、RRF、检索模式路由、API或后续模块，停止等待M2-16.6确认。
- 2026-09-01：完成M2-16.6；新增`HybridRetrievalService`，顺序调用现有Dense与Lexical完整安全链，按`chunk_id`去重并以固定`rrf_k=60`融合名次，保留两路原始排名/分数、单路`None`、双路身份和可复算RRF；同分按UUID稳定排序，最终Top K在融合后应用，任何一路失败整体失败，且检测同Chunk事实冲突和同Document跨active代次混合。TDD首次因Hybrid模块不存在RED，最终本步`11 passed`、相关回归`140 passed`；后端全量唯一失败仍为既有跨月路径用例，排除后`612 passed, 2 skipped, 1 deselected`。Ruff/213文件格式、109文件Mypy、编译、依赖、Alembic和差异检查通过；正式Seed恢复为10/10/10/9、0索引数据、Storage仅10 uploads及M1可售125。未实现检索模式路由、Reranker、API或后续模块，停止等待M2-16.7确认。
- 2026-09-01：完成M2-16.7并收口M2-16；新增可重复的10文档检索验收脚本、Fake门禁判定测试和显式离线BGE检索Smoke。正式Fake链建立35 Chunk/35 Embedding，以20条Golden分别验证Dense、Lexical、Hybrid/RRF：文档命中20/20、18/20、20/20，Hybrid正确证据18/20、安全来源18/20、重复顺序20/20；唯一2条证据缺口仍是已知图文DOCX图片文字。权限/版本/软删除故障矩阵、GIN/HNSW `EXPLAIN`可用性和离线BGE单文档检索通过；本机35 Chunk同步Hybrid p95约43.29 ms，样本不足以支持新增路由，继续默认Hybrid。TDD RED为`3 failed, 48 passed`，GREEN为`51 passed`，相关回归`142 passed`；后端全量唯一失败仍为既有跨月路径用例，排除后`614 passed, 2 skipped, 1 deselected`。Ruff/216文件格式、110文件Mypy、编译、依赖、Alembic和差异检查通过；正式Seed恢复为10/10/10/9、10个parse/index pending、0 active/Chunk Set/Index Set/Chunk/Embedding，Storage仅10 uploads，M1可售125。未实现模式路由、Reranker、RAG、API、Agent或前端，停止等待M2-17方案确认。
- 2026-09-01：用户确认M2-17方案后完成M2-17.1；固定`BAAI/bge-reranker-v2-m3@953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e`、8192长度与float32默认精度，新增严格Reranker身份、raw/sigmoid分数、原Hybrid rank、连续final rank、top 8响应和脱敏Provider错误；真实后端必须固定身份且local-only。TDD先因常量不存在RED，最终聚焦`60 passed`、相关回归`153 passed`；后端全量唯一失败仍为既有跨月路径用例，排除后`625 passed, 2 skipped, 1 deselected`。Ruff/217文件格式、109文件Mypy、编译、依赖、Alembic和差异检查通过；正式Seed恢复为10/10/10/9、0索引数据、Storage仅10 uploads及M1可售125。未实现Provider/Service或下载模型，停止等待M2-17.2确认。
- 2026-09-01：完成M2-17.2；新增硬件无关`RerankerProvider`协议、不可变身份/逐对分数/批次合同、SHA-256问题—正文—原位置绑定键、数量/顺序/身份/有限raw与sigmoid一致性校验，以及完全离线的确定性Fake。TDD先因`RerankerInputError`不存在RED，最终Provider/合同聚焦`93 passed`、相关检索回归`205 passed`；后端全量唯一失败仍为既有跨月路径用例，排除显式Smoke及该用例后`658 passed, 2 skipped, 1 deselected`。Ruff/219文件格式、110文件Mypy、编译、依赖、Alembic和差异检查通过；正式Seed恢复为10/10/10/9、10个parse/index pending、0 active/Chunk Set/Index Set/Chunk/Embedding，Storage仅10 uploads及M1可售125。未实现Reranker Service、真实BGE后端、模型加载/下载或M2-17.3，停止等待确认。
- 2026-09-01：完成M2-17.3；新增`RerankerRetrievalService`，候选只能由注入的可信Hybrid Service按`CurrentUser`生成，Provider只接收query和有序正文并返回分数。Service重验Hybrid结构及单active代次、Provider身份/数量/顺序/pair key，给全部候选评分后按分数、原Hybrid rank、Chunk UUID稳定排序并截取top 8，逐字段保留Chunk身份、正文、来源及Dense/Lexical/RRF事实；空候选不调用Provider，失败映射固定安全错误。TDD先因Service模块不存在RED，本步`64 passed`、合同/Provider/Service`108 passed`、相关回归`220 passed`；真实PostgreSQL集成继续证明无ACL Chunk不会进入精排结果。后端全量唯一失败仍为既有跨月路径用例，排除显式Smoke及该用例后`673 passed, 2 skipped, 1 deselected`。Ruff/222文件格式、111文件Mypy、编译、依赖、Alembic和差异检查通过；正式Seed恢复为10/10/10/9、0索引数据、Storage仅10 uploads及M1可售125。未实现或下载真实BGE、HTTP API、RAG或M2-17.4，停止等待单独确认。
- 2026-09-01：完成M2-17.4；新增固定本地`BgeRerankerProvider`、六文件SHA-256 snapshot manifest、显式下载器、匿名可比资源基准和中英/SKU真实Smoke。用户授权后下载并验证`BAAI/bge-reranker-v2-m3@953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e`共2,293,242,108字节运行文件；真实Smoke在离线变量和不可用代理下`3 passed`。本机CPU基准加载7.038秒、6对候选五轮p50/p95为0.545/0.671秒、RSS峰值2055.1 MiB且三组正负对排序全通过。TDD先因真实Provider常量/类不存在RED，最终聚焦`139 passed, 3 skipped`；后端全量唯一失败仍为既有跨月用例，排除后`704 passed, 2 skipped, 1 deselected`。Ruff/227文件格式、116文件Mypy、编译、依赖、Alembic和差异检查通过；正式Seed恢复为10/10/10/9、0索引数据、Storage仅10 uploads及M1可售125。未运行正式10文档RRF/Reranker质量对比，明确没有开始M2-17.5、RAG、API、Agent、前端或模式路由。
- 2026-09-01：完成M2-17.5并收口M2-17；新增固定20题/18题计分的真实离线质量验收器，逐题保存RRF与Reranker证据排名并严格排除两条上游图文DOCX图片文字。正式Fake索引仍为10 ready/35 Chunk/35 Embedding；RRF Recall@8/MRR@8为`0.777778/0.318056`，真实BGE-Reranker为`1.0/0.898148`，4条RRF top8漏项全部被精排拉回。质量提升同时伴随本机CPU p50/p95约`6.70/7.24秒`和RSS峰值2793.2 MiB，后续需评估候选裁剪/GPU/路由而非直接宣称低延迟可用。TDD先因验收模块不存在为`4 failed, 48 passed`，最终M2-17聚焦`142 passed, 3 skipped`；后端全量唯一失败仍为既有跨月用例，排除后`707 passed, 2 skipped, 1 deselected`。Ruff/229文件格式、114文件Mypy、编译、依赖、Alembic和差异检查通过；2,034,237,440字节失败下载分片已清理且快照复验通过，正式Seed恢复为10/10/10/9、0索引数据、Storage仅10 uploads、M1可售125。没有开始M2-18、RAG回答、API、Agent、前端或模式路由。
- 2026-09-01：完成M2-18.1；新增版本化Context Bundle、文档Evidence和成功引用映射契约，固定空证据状态、`[E1]`至`[E12]`、去重后身份唯一性、预算一致性、服务端4000 Token/12片段/邻居窗口1及安全错误。TDD先因错误类型缺失在收集期RED，最终新增`13 passed`、相邻契约`82 passed`、全部单元`573 passed`；Ruff、格式、112个app模块Mypy、编译、依赖及Alembic检查通过，仍为`20260831_0008 (head)`且无迁移漂移。本步没有Context算法、数据库迁移、Evidence落库、引用解析、API、Tool、Agent、Qwen或前端，停止等待M2-18.2确认。
- 2026-09-01：完成M2-18.2；新增`ContextArtifact` ORM和`20260901_0009`迁移，扩展Evidence为database/knowledge/user_file三分支，复合外键锁定Context、File、Document、Version、ChunkSet、IndexSet和Chunk，唯一约束固定每次Context的`[E#]`及Chunk不重复；旧M1写入依靠默认schema version保持兼容，文档数据存在时降级明确拒绝。TDD先因`ContextArtifact`不存在RED，最终迁移聚焦`4 passed`、相邻回归`50 passed`、后端Fake门禁`724 passed, 2 skipped, 1 deselected`；Ruff/233文件格式、112模块Mypy、编译、依赖、Alembic和差异检查通过。正式Seed恢复为10/10/10/9、0索引/Context/Evidence、Storage仅10 uploads及M1可售125；没有实现M2-18.3 Repository、Context算法、Evidence Service、引用解析或后续模块。
- 2026-09-01：完成M2-18.3；扩展共享`RetrievalRepository`，以可信`CurrentUser`和既有tenant/ACL/active Version/active ready IndexSet/软删除安全门重新取得Reranker锚点，同时核对Document/Version/IndexSet/Chunk四重身份、正文与文档元数据；邻居只允许来自同一Document/Version/ChunkSet/IndexSet的`chunk_index ± 1`。先批量重取锚点，再用可信结果批量重取窗口并二次复核锚点，固定两次SQL避免N+1。TDD先因安全重取异常不存在RED，最终真实PostgreSQL聚焦`11 passed`、相邻回归`126 passed`、Fake门禁`735 passed, 2 skipped, 1 deselected`；全仓Ruff/234文件格式、112模块Mypy、编译、依赖和Alembic检查通过，仍为`20260901_0009 (head)`且无漂移。正式Seed恢复为10/10/10/9、0索引/Context/Evidence、Storage仅10 uploads及M1可售125；没有实现Context去重/overlap/Token预算、Evidence Service、引用解析或后续模块，停止等待M2-18.4确认。
- 2026-09-01：完成M2-18.4；新增确定性`ContextBuilderService`，把安全重取的锚点/邻居按“锚点优先、邻居补充”选入预算，执行Chunk与规范正文去重、文本/表格可信overlap裁剪、精确Token与片段上限、自然窗口顺序和公开来源映射，并生成稳定Context/Evidence UUID与检索/配置/内容/幂等Hash；本步只返回内存`BuiltContext`，不写数据库。TDD先因Context模块不存在RED；最终单元`13 passed`、Builder加真实PostgreSQL集成`25 passed`、相邻回归`159 passed`、Fake门禁`749 passed, 2 skipped, 1 deselected`；全仓Ruff/236文件格式、113模块Mypy、编译、依赖、Alembic和Seed复核通过。原样全量唯一失败仍是既有跨月上传Key硬编码用例，本步未越权修改；停止等待M2-18.5确认。
- 2026-09-01：完成M2-18.5；扩展`EvidenceService`和新增`KnowledgeEvidenceRepository`，保存前复算Builder产物身份并按当前用户重新获权/锁定最终Chunk，以PostgreSQL确定性冲突忽略加逐字段复核实现ContextArtifact和全部文档Evidence幂等写入；嵌套保存点保证任一Evidence失败时Context也回滚，空证据仍保存零片段审计Artifact，M1 database Evidence未改。TDD先因Repository不存在RED；最终真实PostgreSQL`6 passed`、M1/M2 Evidence与Context相邻`35 passed`、Fake门禁`755 passed, 2 skipped, 1 deselected`；全仓Ruff/237文件格式、113模块Mypy、编译、依赖、Alembic及Seed复核通过。原样全量唯一失败仍是既有跨月用例；停止等待M2-18.6确认。
- 2026-09-01：完成M2-18.6并收口M2-18；新增`CitationValidatorService`和当前授权Citation Context读取，只接受严格ASCII `[E1]`至`[E12]`并按答案出现顺序返回数据库控制的Evidence ID，拒绝无引用支持型答案、重复/畸形/越界标签、跨用户Context、ACL撤销、软删除和旧代次。TDD先因Citation模块与Repository记录不存在RED，最终单元/真实PostgreSQL`18 passed`、相邻回归`69 passed`；原样全量`773 passed, 10 skipped, 1 failed`的唯一失败仍是既有跨月用例，排除后`773 passed, 2 skipped, 1 deselected`。Ruff/240文件格式、114模块Mypy、编译、依赖、Alembic与Seed复核通过；本步没有API、Tool、Agent、Qwen、回答语义判定或前端，停止等待M2-19方案确认。
