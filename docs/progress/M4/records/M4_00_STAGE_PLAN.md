# M4-00：通用有界深度研究与报告正式阶段方案

> 日期：2026-09-03
> 阶段：M4
> 步骤：M4-00
> 状态：已完成（仅方案确认）
> 用户确认：`确认按推荐版 M4 方案更新文档，但暂不开始代码开发`

## 1. 本步解决的问题

此前只确认了“M4必须保留、不能写死场景”，仍存在最小版、推荐版和完整版三档候选，也没有冻结Web Worker、联网方式、长网页处理、任务恢复、输出与Skill范围。本步把用户确认的推荐版写成正式阶段方案，使后续开发有清晰边界。

本步只新增和更新文档，不创建Schema、Model、Repository、Service、Tool、Agent、API、前端或数据库迁移。

## 2. 大白话说明

M4要让系统像一个受管理的小型研究团队：项目经理Supervisor把问题分给公司数据调查员、内部资料调查员和网络调查员。网络调查员不能随便上网，只能使用两个受控按钮：先搜索候选网页，再读取本次搜索中获准的少量页面。网页原文会被清洗、切小、去重并保存成证据，模型只看到与问题相关的短片段和Evidence ID。

首版不另外招聘“数据分析员”和“报告编辑”两个Agent。固定计算交给普通程序，M2统一Answer Provider在Supervisor控制下基于三类Evidence合成内容并通过Citation Validator，Report Service只负责确定性Markdown组织。这样保留真正必要的多Agent协作，同时控制开发、测试和讲解成本。

## 3. 当前现状和缺少的能力

### 3.1 当前已有

- M1已经提供`get_product_spec`、`search_inventory`、数据库Evidence和基础Harness；
- M2-01至M2-20已经提供上传、解析、分块、BGE-M3、pgvector、混合检索、Reranker、Context、文档Evidence以及`search_knowledge`、`read_uploaded_file`、`get_evidence_detail`；
- M2-21正式方案已经为Supervisor、Worker、Handoff、父子Run、树形预算、Checkpoint和Evidence交接定义建设方向。

### 3.2 当前缺少

- M2-21至M2-24尚未完成，统一多Agent底座仍是M4前置条件；
- 没有Web搜索或网页读取Schema；
- 没有Fake/Tavily Web Provider；
- 没有`search_public_web`或`read_public_source`；
- 没有Web Evidence清洗、去重、来源分类和正文定位；
- 没有Web Research Worker；
- 没有M4研究Skill、Markdown报告Service、研究任务API或前端任务视图；
- 没有M4真实Tavily、质量、安全、成本、故障和端到端验证。

## 4. 阶段目标

证明系统能够根据用户目标动态规划，在可信身份、权限、预算、超时和停止条件内，组合企业数据库、内部RAG和公开互联网三类能力，输出有来源、可回看、可部分成功且可恢复的研究结果。

阶段成功的核心不是“搜到网页”，而是：

1. 不同Worker确有职责和权限隔离；
2. 搜索摘要与网页正文证据明确分开；
3. 长网页不会无限进入模型上下文；
4. 数据库、文档和网页结论使用统一Evidence交接；
5. 任务能够在预算内并行、暂停、失败和恢复；
6. 同一套能力可以处理不同商品、市场和任务形态。

## 5. 正式范围与非目标

### 5.1 必须实现

- 复用M2 Supervisor、Business Data Worker和Knowledge Worker；
- 新增Web Research Worker；
- `search_public_web`候选来源搜索Tool；
- `read_public_source`受控正文读取Tool；
- Fake与Tavily两种Provider实现；
- URL/内容去重、来源分类、HTML正文清洗、有界切分和相关片段选择；
- Web Evidence来源、时间、locator、内容Hash、可信类型与冲突状态；
- 单Web、Knowledge＋Web、Business＋Knowledge＋Web三类路径；
- 顺序基线和独立只读Worker有界并行；
- PostgreSQL父子Run、任务、租约、Checkpoint和恢复；
- `cross-border-market-research`可版本化Skill；
- 结构化结果与Markdown研究结果；
- 任务创建/状态API和前端进度、结果、Evidence展示；
- Fake回归、真实PostgreSQL矩阵、真实Tavily/Qwen Smoke与Chromium端到端。

### 5.2 明确不做

- M3多模态、图片、OCR和相似SKU；
- 供应商报价、任意经营指标、Pandas复杂分析和图表；
- 独立Analysis Worker与Report Worker；
- PDF；
- 任意SQL、任意HTTP、任意URL、登录绕过或通用Browser；
- MCP、Redis、Celery、MinIO；
- 真实Amazon SP-API、ERP或业务写操作；
- 法律、医疗、金融等高风险自动结论；
- 无界递归、无界并发、无界搜索和无治理长期记忆。

如后续真实需求要求增加上述能力，必须单独更新阶段范围并获得用户确认，不能在某个开发步骤中顺手加入。

## 6. Agent、Tool、Service和Provider分工

### 6.1 Agent结构

```text
Supervisor
├─ Business Data Worker
│  └─ get_product_spec / search_inventory
├─ Knowledge Worker
│  └─ search_knowledge / read_uploaded_file / get_evidence_detail
└─ Web Research Worker
   └─ search_public_web / read_public_source
```

- Supervisor负责目标、Task DAG、Worker选择、依赖、子预算、失败策略和证据覆盖，并把已获权的结构化结果交给统一Answer Provider；
- Web Research Worker负责生成少量查询、选择候选来源、判断是否需要补查、返回Web Evidence和未知项；
- Worker不能直接调用Tavily SDK、HTTP客户端、数据库Repository或宿主文件系统；
- 固定计算由Analysis Service完成；
- 内容综合与引用由M2统一Answer Provider和Citation Validator完成；Markdown模板、章节拼装和导出由Report Service确定性完成；
- 首版Analysis/Report没有独立上下文、工具权限和任务生命周期，因此不包装成Agent。

### 6.2 联网调用链

```text
Web Research Worker
→ 提议Tool调用
→ Harness校验可信身份、Worker白名单、参数、预算、超时和重复签名
→ search_public_web或read_public_source
→ Web Service
→ WebSearchProvider / PublicSourceProvider
→ Fake或Tavily实现
→ 外部HTTPS API
→ 规范化结果和Web Evidence
→ Observation＋Evidence ID返回Worker
```

Tool是Agent可见的能力边界；Provider负责隔离具体外部供应商；Tavily API才是真正执行互联网搜索的外部服务。未来若出现跨客户端复用需求，可以在Provider后增加MCP Adapter，但MCP不绕过Harness，也不改变Tool公开合同。

## 7. 搜索、正文读取与长内容处理

### 7.1 为什么分成两个Tool

`search_public_web`只负责发现候选来源，返回有上限的标题、URL、摘要、时间、来源类型和不透明的`search_result_id`。搜索摘要用于选择来源，不自动成为支持关键结论的正文Evidence。

`read_public_source`只接收当前Run中已经由搜索Tool登记并仍获准的`search_result_id`。Service从服务端记录解析真实URL，禁止模型提交任意URL，因此可以阻止内网探测、协议绕过和未审计访问。

### 7.2 候选合同方向

搜索请求至少表达：查询、市场/语言、可选域名范围、可选时间范围和有上限的结果数。读取请求至少表达：`search_result_id`、研究目标或相关问题、允许的正文片段预算。具体字段、枚举和数值上限在M4-01通过Fake样本与预算测试冻结。

Tool公开结果只返回安全字段和公开ID，不返回API Key、底层HTTP细节、内部路径、完整响应对象或无限正文。

### 7.3 长网页管线

```text
有限搜索结果
→ URL规范化和域名策略
→ 来源类型与时间元数据
→ 选择少量关键页面
→ 安全获取正文
→ 删除脚本、样式、导航、广告和重复模板
→ 按标题/段落有界切分
→ 按当前研究问题选择相关片段
→ 内容Hash和重复转载识别
→ 保存正文片段、locator和来源血缘
→ 生成Web Evidence
→ Context只携带摘要、相关片段和Evidence ID
```

完整正文可按有界保留策略作为内部来源快照或Artifact保存，但不得每轮全部发送给Qwen。若来源无法安全读取、没有相关正文或超过限制，必须返回明确状态，不用搜索摘要伪造正文证据。

### 7.4 来源和冲突

来源至少区分官方机构、品牌官方、媒体、零售页面和低可信聚合页。排名不等于可信度。多个转载同一原始消息的页面不能计作多份独立证据。

冲突处理顺序：先比较地区、时间、口径、原始来源和来源类型；可以消除时记录判断依据；不能消除时并列保存并标记`conflict`或`unknown`，由最终结果向用户说明。

### 7.5 网页Prompt Injection

网页、摘要和正文始终是不可信数据。它们不能改变系统Prompt、Tool白名单、父子权限、预算或任务目标；不能要求读取密钥、访问其他数据源或执行新动作。Worker只接收结构化Observation，Trace保存安全摘要而不是把任意网页指令当控制信息。

## 8. 任务、Checkpoint和并行

### 8.1 首版执行方式

- API创建研究任务后返回公开`task_id`；
- 应用内有界任务执行器从PostgreSQL领取任务租约；
- 每个节点完成后提交任务状态、公开Observation、Evidence/Artifact ID、预算消耗和Checkpoint；
- 前端通过状态API轮询进度；
- 执行器异常时租约到期，后续执行器重新获权并从安全Checkpoint恢复；
- 不跨HTTP请求保存数据库事务、原始Tool对象或隐藏思维过程。

聊天中发起研究仍先经过M2统一Agent Gateway；研究任务API只负责创建、查询、取消/恢复`task_id`并调用同一Supervisor应用Service，不建立第二套Planner或绕过Capability Resolver。

该设计提供当前单机作品规模所需的持久状态与恢复证明，但不宣称已经达到Celery/Redis或分布式队列的生产吞吐。若真实压测证明应用内执行器不足，再单独评估队列。

### 8.2 并发规则

先通过完整顺序基线，再只对无依赖、只读且数据范围独立的Worker开启有界并行。每个分支必须使用独立数据库Session、独立子Run与Trace；树形预算原子扣减；结果按Task ID稳定合并。失败分支不能污染已经提交的其他Evidence。

## 9. 输出和Skill

### 9.1 输出类型

首版支持：

```text
short_answer
evidence_summary
verification
comparison
research_memo
report
```

所有输出必须区分事实、推断、假设、未知项、冲突和缺失来源。Markdown是呈现形式，不反向决定底层研究流程。PDF不在首版范围。

### 9.2 `cross-border-market-research`

首版只实现一个通用研究Skill，保存稳定方法：目标澄清、市场拆分、内部/外部证据要求、来源优先级、冲突处理、停止条件、输出检查和评估样例。Skill不保存实时法规、库存、价格、API Key或数据库信息，也不写死蘑菇灯、德国或法国。

Skill申请能力仍取以下交集：

```text
Skill申请
∩ Worker允许范围
∩ 父Agent委派范围
∩ 当前用户权限
∩ 系统安全策略
∩ 当前资源ACL
```

## 10. 正式实施步骤

以下文件名依据当前仓库结构预估。M2完成后必须先核对其最终合同与目录；如路径变化，应在对应步骤方案中解释，但不能改变本阶段范围。

### M4-01：冻结合同和验收样本

- 输入：M2最终Agent、Evidence、Task、Handoff和预算合同；本方案三类任务；
- 输出：研究请求、搜索、来源读取、Web Evidence、任务状态和Markdown结果Schema；固定Fake样本与失败条件；
- 预计文件：`app/schemas/research.py`、`app/schemas/web.py`、`tests/fixtures/web_research.py`、对应单元测试；
- 调用链：Schema与测试数据层；暂不访问外网或数据库；
- 验证：边界值、非法URL替代输入、结果上限、状态枚举、序列化、向后兼容和Golden样本测试；
- 完成标准：后续Provider、Tool、Worker和前端共享同一严格合同。

### M4-02：Provider接口与Fake

- 输入：M4-01合同；
- 输出：可替换的搜索/正文Provider接口和确定性Fake；
- 预计文件：`app/services/web/providers/base.py`、`fake.py`、`app/services/web/contracts.py`及单元测试；
- 调用链：Service/Provider层；Fake不经过真实互联网；
- 验证：正常、空结果、重复、冲突、超时、限流、无额度、配置错误和恶意正文夹具；
- 完成标准：没有Tavily Key也能稳定复现全部关键分支。

### M4-03：搜索Service、Tool与Harness

- 输入：可信RunContext和结构化搜索请求；
- 输出：有界候选来源、公开`search_result_id`、Trace和预算消耗；
- 预计文件：`app/services/web/search.py`、`app/tools/search_public_web.py`、Registry/权限配置及测试；
- 调用链：Agent候选调用 → Harness → Tool → Service → Fake Provider；
- 验证：身份、白名单、角色、tenant、参数、上限、重复签名、超时、错误脱敏和Trace；
- 完成标准：模型不能提交任意HTTP请求，搜索候选可审计且不伪装正文Evidence。

### M4-04：受控正文读取与Web Evidence

- 输入：当前Run已登记的`search_result_id`和研究问题；
- 输出：清洗、切分、去重后的相关正文片段及Web Evidence；
- 预计文件：`app/services/web/reading.py`、`normalization.py`、`deduplication.py`、`app/tools/read_public_source.py`、Evidence Repository/Service扩展、必要迁移及测试；
- 调用链：Harness → Tool → Source Reading Service → Provider → Evidence Repository → PostgreSQL；
- 验证：任意URL拒绝、协议/内网限制、正文上限、locator、Hash、重复转载、注入文本、原子持久化与回滚；
- 完成标准：关键网页主张可以回到正文片段，长正文不会无限进入Context。

### M4-05：Web Research Worker

- 输入：公开事实问题和Web能力摘要；
- 输出：Web Observation、Evidence ID、未知项和明确终态；
- 预计文件：`app/agents/workers/web_research.py`、Agent定义/Resolver扩展、Mock Planner样本及测试；
- 调用链：API或测试入口 → Supervisor/单Worker路由 → Harness → 两个Web Tool → Fake Provider/PostgreSQL；
- 验证：查询改写、来源选择、补查上限、停止条件、无证据、冲突、部分失败和引用映射；
- 完成标准：单Web Worker事实查询不需要启动所有Worker。

### M4-06：跨来源顺序协作

- 输入：内部核验与三来源综合任务；
- 输出：结构化Task DAG、Handoff、三类Observation/Evidence和综合回答；
- 预计文件：Supervisor/Graph/Capability Resolver扩展、组合任务测试；
- 调用链：Supervisor → Business/Knowledge/Web Worker顺序执行 → Evidence合并/重新获权 → 统一Answer Provider → Citation Validator；
- 验证：Knowledge＋Web核验、Business＋Knowledge＋Web综合、撤权、来源冲突、一个Worker失败和Evidence重新获权；
- 完成标准：不同任务按需要选择Worker，不硬编码商品、国家或固定步骤。

### M4-07：持久任务、租约、Checkpoint与并行

- 输入：已验证的顺序Task DAG和M2父子Run合同；
- 输出：PostgreSQL任务状态、执行租约、Checkpoint、恢复和独立只读Worker有界并行；
- 预计文件：Runtime Model/Repository/迁移、`app/workers/research.py`或等价应用内执行器、并发/恢复测试；
- 调用链：任务API → PostgreSQL队列/租约 → LangGraph节点 → 子Run/Worker → Checkpoint；
- 验证：进程中断模拟、租约到期领取、重复恢复、独立Session、原子预算、稳定合并、失败分支隔离；
- 完成标准：用户离开页面后任务状态仍在，恢复不重复提交已完成Evidence。

### M4-08：研究Skill与Markdown Service

- 输入：三类Evidence、分析结果、未知项和冲突；
- 输出：版本化研究步骤与可验证Markdown；
- 预计文件：`app/skills/cross-border-market-research/SKILL.md`、Skill Catalog/Policy扩展、`app/services/reports/markdown.py`及测试；
- 调用链：Supervisor选择Skill → Worker取证 → 统一Answer Provider/Citation Validator → Report Service；
- 验证：Skill权限交集、版本Trace、跨商品/市场复用、缺失引用拒绝、事实/推断/假设/未知分区；
- 完成标准：Golden Scenario成立且换商品、换市场后合同仍可用。

### M4-09：API与前端闭环

- 输入：研究请求和用户身份；
- 输出：任务ID、状态、进度、部分失败、Markdown与Evidence界面；
- 预计文件：`app/api/routers/research.py`、`app/main.py`、API Schema/Service、`frontend/features/tasks/`、`frontend/features/evidence/`、`frontend/lib/api.ts`及测试；
- 调用链：前端 → API → Schema → Agent/Harness → Tool → Service/Provider/Repository → PostgreSQL/Tavily；
- 验证：API权限/错误合同、轮询、刷新恢复、前端组件、Chromium完整流程和无障碍基础检查；
- 完成标准：用户无需理解Worker或Tool即可创建任务、看进度、读结果和核验证据。

### M4-10：真实Tavily和阶段验收

- 输入：显式启用的Tavily Key、冻结样本与完成的Fake闭环；
- 输出：真实Provider、Smoke结果、质量/安全/性能/成本/故障报告和M4收口记录；
- 预计文件：`app/services/web/providers/tavily.py`、配置示例、Smoke/集成/端到端测试、M4过程记录；
- 调用链：完整前端到Tavily/PostgreSQL链；
- 验证：真实搜索与正文、引用准确、来源分类、重复/冲突、超时/限流/无额度、p50/p95、Token/调用成本、三类任务和Golden Scenario；
- 完成标准：入口文件第9节所有完成条件均有实际证据，未验证项不得标记完成。

## 11. 验收样本

至少冻结以下三类：

1. 单一公开事实查询：只需要Web Worker；
2. 内外部核验：比较内部说明与权威公开来源；
3. 综合研究Golden Scenario：综合德国、法国库存、内部产品资料和公开市场信息，形成蘑菇灯市场建议并展示三类Evidence。

还应增加换商品、换市场样本，证明Skill和Graph没有把Golden Scenario写死。具体样本内容、数量和评分阈值在M4-01冻结，最终综合评估在M5继续扩展。

## 12. 验证层级

| 层级 | 验证内容 | 能证明 | 不能证明 |
|---|---|---|---|
| 单元测试 | Schema、清洗、去重、分类、预算、错误映射 | 确定性规则正确 | 外部API真实可用 |
| Fake集成 | Tool、Harness、Worker、Handoff、Checkpoint | 分支稳定、可重复回归 | 真实网页质量 |
| PostgreSQL集成 | 父子Run、Evidence、租约、恢复、回滚 | 持久状态和事务边界 | 分布式队列吞吐 |
| Tavily/Qwen Smoke | 真实模型和搜索服务 | 当前配置下能真实调用 | 长期可用性和全部网页覆盖 |
| Chromium端到端 | 前端创建、轮询、结果和Evidence | 用户可见完整链路 | 大规模并发能力 |
| 质量/安全矩阵 | 引用、来源、冲突、注入、越权、预算 | 关键失败边界受控 | 所有互联网风险已消失 |

## 13. 主要风险和排查方向

| 风险 | 现象 | 优先排查 |
|---|---|---|
| Provider与Tool混在一起 | 测试必须真实联网 | 检查接口注入与Fake边界 |
| 搜索和正文混淆 | 结论只引用摘要 | 检查`search_result_id`到Web Evidence血缘 |
| 任意URL读取 | SSRF或访问未审计地址 | 检查服务端结果ID解析、协议和地址策略 |
| 上下文过长 | Token/延迟激增 | 检查搜索数、页面数、切分、相关片段和Context预算 |
| 来源重复或冲突 | 多数票看似可靠但实际同源 | 检查canonical URL、Hash、发布时间和原始来源 |
| 网页注入 | Worker偏离任务或申请越权Tool | 检查不可信内容边界、Resolver投影和Harness拒绝 |
| 并发污染 | Session错误、重复Evidence、预算超支 | 检查独立Session、幂等键、原子扣减和稳定合并 |
| 恢复重复执行 | Checkpoint后重复搜索/写证据 | 检查节点幂等、租约、版本和提交边界 |
| Tavily不可用 | 任务卡死或伪造结果 | 检查错误分类、有限重试、partial和可恢复失败 |
| 范围膨胀 | 开始加入PDF、图表、MCP和更多Worker | 回看第5.2节并暂停扩展 |

## 14. M4-00修改文件与职责

- `docs/progress/M4/M4_DEEP_RESEARCH.md`：M4短入口，只保存当前状态、有效决策、步骤索引、风险、验证基线和下一动作；
- `docs/progress/M4/records/M4_00_STAGE_PLAN.md`：保存完整正式方案、用户确认、实施顺序和验证边界；
- `docs/PROJECT_PROGRESS.md`：把M4从待确认更新为正式方案已确认、阶段待开始；
- `docs/design/05_Autumn_Recruitment_Scope_Adjustment_Plan.md`：把候选档位和待确认项更新为已确认推荐版并链接正式方案；
- `docs/design/02_System_Architecture_and_Agent_RAG_Design.md`：同步Web Tool/Provider、首版Worker、Skill、任务恢复、MCP和非目标；
- `docs/design/03_Data_Evaluation_and_Implementation_Plan.md`：标明原始M4完整版已被当前正式方案取代；
- `docs/progress/M2/records/M2_21_ENGINEERED_MULTI_AGENT_PLAN.md`：只同步其面向M4的未来扩展说明，不改变M2-21当前实施范围。

## 15. 本步调用链位置

本步只修改方案和进度文档：

```text
前端：不经过
API：不经过
Schema：不经过
Agent/LangGraph/Harness：不经过
Tool：不经过
Service/Provider：不经过
Model：不经过
PostgreSQL/Tavily：不经过
```

文档描述的是未来M4目标链路，不代表这些能力已经实现。

## 16. 本步实际验证与结论边界

2026-09-04在同步M2-21复核边界时完成了本方案的实际文档验证：

- `rg --files docs/progress/M4`精确返回阶段入口与`records/M4_00_STAGE_PLAN.md`两个文件，目录结构正确且没有空占位文件；
- 对AGENTS、总看板、三份总体设计、M2入口/M2-21记录和M4两份文档执行相对Markdown链接解析，结果为`LINK_CHECK_PASS`；
- M2-21复核稿的十二步清单与文件/调用链/验证表均精确为1至12，结果分别为`REVIEW_STEPS=12`、`REVIEW_TABLE_ROWS=12`且顺序检查为`True`；
- 上述文件的Markdown围栏偶数配对，结果为`FENCE_CHECK_PASS`；自定义行尾扫描结果为`TRAILING_WHITESPACE_PASS`；
- 定向关键词检查没有发现仍以当前结论表述的“三个M4新Worker”、M4档位待确认、Redis/Celery当前方案、约13个Tool、5个Skill或平行知识HTTP API；总看板唯一“档位待确认”命中已明确标为后续已取代的历史节点；
- `git diff --check`通过，只有Windows工作区未来可能执行LF/CRLF转换的提示，没有内容错误；
- `git status --short`显示变更范围只有根`AGENTS.md`与`docs/`文档，未修改应用代码、测试、迁移、配置、Seed、Storage、密钥或运行产物。

这些结果能证明正式方案、当前总体设计、秋招范围和M2未来扩展口径一致，并且M4-00具备标记“已完成（仅方案确认）”所需的实际文档证据。不能证明M4联网、网页正文、Web Evidence、多Agent并行、Checkpoint恢复、前端或真实Tavily/Qwen已经实现；这些必须在M4-01至M4-10分别验证。

## 17. 下一步与授权边界

项目继续完成M2-21至M2-24。M2正式收口后，必须先根据M2实际完成的合同与目录复核本方案，再单独向用户说明M4-01的输入、输出、上下游、修改文件和验证方法。

本次确认不授权M4-01，也不授权任何M4运行代码。
