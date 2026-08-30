# 项目总进度看板

> 本文档是项目进度的统一入口，只保存摘要和阶段链接。  
> 每个阶段的方案、步骤日志和验证结果保存在 `docs/progress/`。  
> 状态枚举：待确认、待开始、进行中、受阻、已完成。  
> 最近更新：2026-08-30

## 1. 当前状态

| 项目 | 当前内容 |
|---|---|
| 当前阶段 | M2：知识库垂直切片（实施中） |
| 阶段状态 | 进行中 |
| 当前步骤 | M2-12.2“PDF/DOCX文本结构单元与切块”已完成；停止并等待是否开始M2-12.3 |
| 已完成到 | M1已完成；M2已完成M2-01至M2-11及M2-12.1至M2-12.2；PDF/DOCX已具备确定性清洗、标题范围、跨页、重复页眉页脚、长段边界与同范围重叠切块，表格Block会明确延后而非静默丢弃 |
| 下一动作 | 等待用户审阅M2-12.2结果并明确授权M2-12.3四类结构化表格切块；该授权不包含Chunk Set迁移、Storage发布、Embedding、索引或检索 |
| 当前阻塞 | 无；图文DOCX页眉和图片文字仍为0/2的已知质量短板，先保留真实评估结果，在最终RAG验收时决定是否增加专用视觉/OCR增强 |

## 2. 里程碑总览

| 里程碑 | 内容 | 状态 | 详细记录或完成依据 |
|---|---|---|---|
| M0 | 产品、技术、数据、评估与协作基线 | 已完成 | [查看M0详细记录](progress/M0_DESIGN.md) |
| M1 | 库存查询垂直切片 | 已完成 | [查看M1详细记录](progress/M1_INVENTORY_QUERY.md)；M1-01至M1-21全部完成并验证 |
| M2 | 自建RAG垂直切片 | 进行中 | [查看M2方案与实施记录](progress/M2_KNOWLEDGE_RAG.md) |
| M3 | 多模态商品分析 | 待开始 | 等待M2完成 |
| M4 | 深度研究与报告 | 待开始 | 等待M3完成 |
| M5 | 评估、加固与作品化 | 待开始 | 等待M4完成 |

## 3. 阶段记录目录

| 阶段 | 文件 | 说明 |
|---|---|---|
| M0 | [M0_DESIGN.md](progress/M0_DESIGN.md) | 总体方案、协作基线和进度结构 |
| M1 | [M1_INVENTORY_QUERY.md](progress/M1_INVENTORY_QUERY.md) | 现状、边界、21个实施步骤、验证矩阵和待确认决定 |
| M2 | [M2_KNOWLEDGE_RAG.md](progress/M2_KNOWLEDGE_RAG.md) | 只读盘点、已确认方案、26个正式步骤（M2-11细分5个子步骤）和后续验证日志 |
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
