# 项目总进度看板

> 本文档是项目进度的统一入口，只保存当前状态、里程碑摘要、跨阶段决策、阻塞项和阶段链接。
> 详细方案、逐步日志和完整验证结果保存在 `docs/progress/` 对应阶段记录中。
> 状态枚举：待确认、待开始、进行中、受阻、已完成。
> 最近更新：2026-09-07

## 1. 当前状态

| 项目 | 当前内容 |
|---|---|
| 当前阶段 | M2：知识库垂直切片 |
| 阶段状态 | 进行中 |
| 已完成到 | M1已完成；M2-01至M2-20已收口；M2-21十二步的合同、两个真实Worker、Qwen/统一引用、持久化、唯一Gateway、跨请求恢复、独立只读并行及G0～G7矩阵已完成并验证 |
| 当前停止点 | M2-21.12及整个M2-21已完成；尚未授权开始M2-22最小RAG评估集和Runner |
| 下一动作 | 等待用户确认理解M2-21收口结果并单独授权M2-22；不得自动开始后续代码 |
| 尚未具备 | M2-22至M2-24、前端知识问答、M2最终评估/演示收口及M4/M5能力 |
| 当前阻塞 | 无本步技术硬阻塞；Reranker CPU延迟、图文DOCX定位、测试时间依赖及一项范围外文档解析集成失败属于已知风险 |

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
| 互联网搜索 | M4使用`search_public_web`与`read_public_source`两个受控Tool，经Service和可替换Provider调用Tavily；不允许模型提交任意URL/HTTP |
| V1文件存储 | 本地文件系统 + Storage抽象，不部署MinIO |
| 数据 | 明确标注的版本化合成演示数据 |
| Tool权限 | 单个Agent或Skill只获得1至5个允许Tool，模型不能直接访问数据库 |
| Harness | 统一负责上下文、权限、白名单、预算、超时重试、审计、证据和评估钩子 |
| MCP | V1不引入；连接真实外部系统或向外部客户端复用时再评估 |
| 项目最高目标 | 面向秋招AI应用岗位形成可运行、可观察、可量化、用户能独立讲透的作品；M4与M5仍是最终主线，不把顺序后移擅自解释为删除 |
| 公开聊天入口 | 复用现有消息POST；M2-21.10已迁移到唯一Agent Gateway，旧M1固定图不再位于公开主路径或充当自动兜底 |
| 秋招范围调整 | M3多模态暂缓；M4推荐版已确认：复用Business/Knowledge Worker，只新增Web Research Worker，以Tavily自定义Provider实现搜索与受控正文读取，保留三类Evidence、有界并行、PostgreSQL Checkpoint、Markdown和一个研究Skill；M5保留Agent/RAG评估、加固和作品化；详见[M4入口](progress/M4/M4_DEEP_RESEARCH.md)与[调整方案](design/05_Autumn_Recruitment_Scope_Adjustment_Plan.md) |
| 开发方式 | 教学式协作、阶段方案先确认、一次完成一个可验证小步骤 |
| 阶段文档结构 | M1及以后统一使用`docs/progress/M{编号}/`，阶段短入口与`records/`过程记录分离；新窗口按当前任务读取，不默认加载全部历史 |

M2 专属的解析、分块、索引、检索、Reranker、Context和Evidence决策不在总看板重复展开，统一以 [M2入口](progress/M2/M2_KNOWLEDGE_RAG.md) 和对应过程记录为准。

## 4. 当前验证基线

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
| 图文DOCX事实级定位不足 | 图片文字可能无法形成可核验Evidence | 继续作为解析上游边界记录，不伪造召回成功 |
| 既有跨月硬编码测试 | 默认全量测试随月份变化失败 | 后续单独修复测试时间依赖，不放宽生产规则 |
| 固定UUID数据库夹具存在顺序耦合 | 人工改变测试顺序可能产生污染 | 后续加固测试隔离和唯一数据身份 |
| Business商品规格没有Evidence | M2-21.8明确不伪造引用；只规格可作为已观察结构化结果，但没有可引用Evidence | 若后续要求规格也强制引用，先新增真实规格Evidence来源 |
| Qwen生产质量未收口 | M2-21.8代表性真实Smoke已通过；M2-21.12环境无Key而显式跳过复跑，仍未覆盖任意自然语言、真实Tool整链或负载 | M2-22/M5使用版本化评估集验证规划、行动、引用、延迟与预算 |
| 记忆与崩溃恢复边界 | 有界短期记忆、澄清同根恢复、撤权重验和一次Re-plan已完成；不是长期画像，未知执行结果的`running`根暂不自动抢占 | M5评估长对话与恢复租约，不擅自扩大记忆范围 |
| Worker并发规模边界 | 已证明两个独立只读Worker在单进程内有界重叠及预算/Session/Trace隔离；未做高并发、多进程或写操作冲突控制 | M5再做负载、背压和多进程评估；写能力必须另行设计审批与一致性边界 |
| README与旧面试指南仍含早期原型/原始完整版表述 | 直接用于投递会夸大或混淆当前实现 | M5作品化前按实际代码、评估和演示统一清理；当前不得直接照抄 |

当前没有阻止M2-22方案讨论的技术硬阻塞，但M2-21收口理解确认与M2-22单步授权是流程门禁。唯一公开Gateway、两个真实Worker顺序与独立只读并行、严格Qwen、统一引用、持久化、跨请求恢复和G0～G7矩阵已经分别验证；完整integration仍有一项范围外文档解析失败，生产Qwen质量、高负载并发和前端交互仍需后续验证。

## 6. 最近完成摘要

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
