# M2-19：`search_knowledge` Tool 完整实施方案

> 方案日期：2026-09-02
> 当前状态：进行中（M2-19.1至M2-19.3已完成并验证）
> 前置阶段：M2-01 至 M2-18 已完成并验证
> 授权边界：M2-19方案及推荐决策已确认；M2-19.1至M2-19.5均已完成，M2-20尚未授权

## 1. 当前现状和缺少的能力

M2-16 至 M2-18 已经分别完成了权限前置的 Hybrid 检索、BGE-Reranker、Context Builder、Context/Evidence 原子幂等持久化和引用验证。当前内部代码已经能够执行：

```text
CurrentUser + RetrievalRequest
→ Dense + Lexical
→ Hybrid + RRF
→ Reranker
→ Context Builder
→ ContextArtifact + Document Evidence
→ Citation Validator
```

当前缺少的不是新的检索算法，而是一个让未来知识 Agent 安全调用整条链路的正式入口。现有能力仍是分散的 Service：

- `ToolName` 和 Registry 只登记 M1 的 `get_product_spec`、`search_inventory`；
- 没有 `SearchKnowledgeInput` / `SearchKnowledgeResult`；
- 没有 `SearchKnowledgeTool`，Harness 无法为知识检索统一执行权限、预算、超时和 Trace；
- 没有一个应用 Service 负责按固定顺序编排 Reranker、Context Builder 和 Evidence；
- `RunContext` 有可信用户安全身份，但现有 `ToolExecutionContext` 只下发 tenant/run/tool/trace ID，知识链所需的 user/role/market 身份还没有安全传到 Tool 业务回调；
- Context/Evidence 使用确定性身份，可以跨重试复用；但一行 Evidence 最多只能直接绑定一个 ToolCall，不能正确表达“不同 ToolCall 复用同一个 Context”的审计关系；
- `ToolEnvelope.evidence_ids` 当前最多 10 个，而 Context 合同最多 12 段，两个已确认合同存在上限不一致。

### 1.1 大白话解释

现在已经有“找资料、重新排序、整理证据、保存证据”的完整生产线，但还没有带门禁、计数器和行车记录仪的启动按钮。M2-19 要做的 `search_knowledge` 就是这个按钮：模型以后只能提出“请调用这个工具”，真正的用户身份、权限检查、调用次数、超时、数据库读写和审计仍由后端控制。

## 2. 本阶段目标

M2-19 只完成一个单一职责能力：实现并注册只读 Agent Tool `search_knowledge`，通过既有 Harness 调用 M2-16 至 M2-18 的安全链，并返回严格 `ToolEnvelope`。

完成后应具备：

1. Tool 输入只能包含有界自然语言问题，不能包含 tenant、用户、角色、SQL、路径、候选数量、模型名称或Context预算；
2. Tool 使用可信 `CurrentUser`，并与 Harness 的 `RunContext` 安全身份逐项核对；
3. Tool 先经过 Registry、PermissionGuard、ExecutionBudget 和 Trace，再进入业务链；
4. 业务链固定执行 `Reranker → Context Builder → Evidence持久化`，而 Reranker 内部继续调用既有 Hybrid；
5. 有证据时返回最多12段获权Context及完全对齐的Evidence ID；无证据是合法成功结果，不伪装成异常；
6. Context/Evidence可跨相同查询幂等复用，但每个成功ToolCall都有独立、可查询的Context审计关联；
7. 失败、越权、预算、超时、Provider和数据库错误进入既有安全错误合同，不泄露SQL、tenant、ACL、Storage Key、本机路径或堆栈；
8. M1库存图继续只看到原来的两个Tool，不在M2-21之前把知识Tool开放给现有Agent。

## 3. 本阶段明确不做

M2-19 不包含：

- 不调用Qwen生成最终自然语言答案；
- 不调用Citation Validator验证模型答案，因为本步尚未产生模型答案；
- 不实现知识路由、LangGraph或修改现有库存Agent；
- 不把M2 Registry接入现有`/threads/{id}/messages` API；
- 不新增HTTP知识检索接口或修改前端；
- 不实现`read_uploaded_file`或`get_evidence_detail`，它们属于M2-20；
- 不修改Dense、Lexical、RRF、Reranker或Context排序算法；
- 不新增检索模式自动路由，不让模型选择candidate count、top k或Context预算；
- 不下载、更新或联网调用真实BGE模型；日常验证继续使用Fake，真实模型性能沿用M2-17记录；
- 不修复既有跨月测试和固定UUID夹具顺序耦合，它们继续作为独立风险记录；
- 不开始M2-20及后续阶段。

## 4. 前置条件与只读盘点结论

### 4.1 已满足的前置条件

- M2-16共享权限安全门已覆盖tenant、owner/company owner、user/role/market ACL、软删除、active Version和active ready Index Set；
- M2-17 Reranker只能重排Hybrid已经获权的候选；
- M2-18 Context Builder会重新获权锚点和邻居，Context/Evidence具有确定性ID与Hash；
- M2-18 Evidence Service可以在一个保存点中原子保存Context及所有Document Evidence；
- M1已有可复用的Registry、PermissionGuard、ExecutionBudget、HarnessExecutor、TraceRecorder和ToolEnvelope；
- PostgreSQL迁移当前为`20260901_0009 (head)`；正式Seed中Context/Evidence均为0；
- 进度文档已经整理为M2短入口和`records/`过程记录结构。

### 4.2 盘点后必须解决的合同差异

| 差异 | 如果不处理会怎样 | M2-19决定 |
|---|---|---|
| ToolEnvelope最多10个Evidence，Context最多12段 | 合法Context无法装入ToolEnvelope | 把通用上限统一为12，并回归M1单Evidence行为 |
| M1 Registry必须保持精确两Tool | 直接替换会让库存Agent提前看到知识Tool | 保留`create_m1_tool_registry()`；新增M2 Registry工厂，累计登记三个已实现Tool |
| Retrieval需要CurrentUser，Tool回调只带tenant | 可能丢失user/role/market ACL上下文 | 扩展可信`ToolExecutionContext`的安全身份字段，并核对注入的CurrentUser |
| Evidence可复用但直接ToolCall外键只能绑定一次 | 第二次相同查询会冲突，或失去本次调用审计 | 新增ToolCall与Context关联表，一份Context允许被多个ToolCall复用 |
| 默认Harness总预算8秒，真实CPU Reranker p95约7.24秒 | 真实模型同步链可能接近或超过总预算 | M2-19用Fake完成日常闭环；登记Tool硬超时但不宣称真实CPU低延迟，路由级预算留到M2-21统一决定 |

## 5. 冻结的输入、输出和运行语义

### 5.1 Tool输入

计划新增`SearchKnowledgeInput`：

```text
query: 严格字符串，去空白后1至2000字符
```

输入不得出现：

- `tenant_id`、`user_id`、role、market scopes；
- SQL、表名、Storage Key、本地路径；
- Dense/Lexical候选数、RRF参数、Reranker top k；
- Context Token、片段数或邻居窗口；
- Embedding/Reranker模型、revision、设备或精度；
- file/document/chunk/index set内部身份过滤条件。

M2原始计划中的“可选安全过滤条件”本轮不开放。当前Document ACL已包含市场和用户授权；提前让模型提供过滤字段会增加越权和“合法资料被错误过滤”的复杂度，等真实评估证明必要后再单独设计。

### 5.2 Tool输出

计划新增`SearchKnowledgeResult`，只包装一个公开安全的`ContextBundle`。Tool成功时返回：

- `ToolEnvelope.status = success`；
- `data.context`为`m2-context-bundle-v1`；
- `evidence_ids`严格等于Context片段内Evidence ID，数量、顺序和唯一性完全一致；
- `meta`继续包含Tool名称、版本、时长、trace ID和合成数据标记；
- 不返回tenant、ACL、owner、Storage Key、本地路径、向量、FTS、SQL、内部Hash快照或原始异常。

Context片段已经包含`[E#]`、正文、文档标题、公开locator、来源类型、Reranker名次和Evidence ID，因此本步不再增加第二套重复的“片段结果Schema”。Reranker原始分数和模型内部身份不进入Tool公开输出。

### 5.3 无证据语义

无获权候选不是异常：

```text
ToolEnvelope.status = success
data.context.supported = false
data.context.segments = []
evidence_ids = []
```

这只表示“当前用户在当前活动资料中没有可用证据”。如何向用户组织拒答文本属于M2-21，不在Tool里硬编码自然语言答案。

### 5.4 权限语义

- Registry层：`search_knowledge`为`read`、tenant scope，允许现有三个业务角色提出调用；
- Harness层：tenant只来自`RunContext`，模型请求不能提供；
- Tool层：传入的`CurrentUser`必须与`ToolExecutionContext`中的user、tenant、roles、market scopes一致；
- Retrieval层：继续在排序前执行完整文档ACL和active代次过滤；
- Context/Evidence层：保存前再次获权；任何时点撤权、软删除或切代都不能返回旧资料伪成功。

### 5.5 Registry隔离

- `create_m1_tool_registry()`继续精确返回`get_product_spec`和`search_inventory`，现有库存Agent、API和Provider测试不改变；
- 新增M2 Registry工厂，返回上述两个Tool加`search_knowledge`；
- M2-19只证明Registry元数据和Tool可被显式构造执行，不把M2 Registry接入库存Agent；
- M2-21创建知识路由时，只把任务所需的1至5个Tool投影给模型，不把整个Registry无差别暴露。

### 5.6 Context复用与ToolCall审计

计划新增`tool_context_links`（最终命名以实现时模型约定为准）：

- 一条记录连接可信tenant、AgentRun、ToolCall与ContextArtifact；
- 一个`search_knowledge` ToolCall最多关联一个Context；
- 同一个Context可以被多个不同ToolCall复用；
- ToolCall、AgentRun和Context必须属于同tenant，并由PostgreSQL复合外键保证；
- 关联写入和Context/Evidence持久化位于同一个业务保存点，任一失败全部回滚；
- 重复执行同一关联幂等复用，冲突Context拒绝覆盖；
- Knowledge/User-file Evidence保持可复用，不再把单一ToolCall当成自身永久所有者；
- M1 database Evidence仍直接绑定其唯一ToolCall，现有库存审计不改变；
- 0010降级若存在Tool-Context审计关联必须明确拒绝，不能静默删除调用证据。

如数据库中存在历史Document Evidence直接运行绑定，0010升级应先把可表示的绑定回填到关联表，再清空Document Evidence上的运行对；随后收紧知识Evidence分支为“运行对为空、通过关联表审计”。正式Seed当前为0行，但迁移仍应对已有合法数据安全。

### 5.7 事务与错误语义

```text
TraceRecorder独立事务创建ToolCall(running)
→ 业务Session保存或复用Context/Evidence
→ 同一业务保存点写ToolCall-Context关联
→ Harness检查Tool耗时
→ TraceRecorder独立事务结束ToolCall(success/error/timeout)
```

- 业务失败由当前请求/未来Agent所有者回滚业务Session；Tool不自行commit；
- Context、Evidence和关联表必须一起成功或一起回滚；
- ToolCall审计使用独立事务，即使业务失败也保留安全失败记录；
- 已有`ApplicationError`保持原错误码和固定消息；
- 未知异常统一转换为`ToolExecutionError`；
- 数据库timeout继续标记ToolCall为timeout；
- 错误ToolEnvelope不得返回data或Evidence ID。

## 6. 完整调用链位置

M2-19完成后的本步调用链：

```text
显式调用者/测试
→ SearchKnowledgeInput Schema
→ HarnessExecutor
   → Tool Registry
   → PermissionGuard
   → ExecutionBudget
   → TraceRecorder / AgentRun / ToolCall
→ SearchKnowledgeTool
→ KnowledgeSearchService
→ RerankerRetrievalService
→ HybridRetrievalService
→ Dense + Lexical
→ RetrievalRepository
→ PostgreSQL FTS + pgvector
→ ContextBuilderService
→ EvidenceService
→ ContextArtifact + Evidence + ToolContextLink Model
→ PostgreSQL
→ SearchKnowledgeResult
→ ToolEnvelope
```

在项目要求的完整链路中，本步经过Schema、Harness、Tool、Service、Repository、Model和PostgreSQL/pgvector；不经过前端、HTTP API、Agent/LangGraph、Qwen或Citation Validator。Storage不在查询链中直接读取，正文来自当前active Index Set的PostgreSQL Chunk。

## 7. 按顺序实施的五个小步骤

用户已经确认本方案和推荐决策。M2-19.1现已完成；后续每个小步骤仍必须分别完成、验证、记录和汇报后停止，等待下一步确认。

### M2-19.1｜冻结知识Tool合同和隔离Registry

**只解决：Tool叫什么、允许接收什么、返回什么，以及谁能看到它。**

预计修改或新增：

- `app/schemas/knowledge.py`：`SearchKnowledgeInput`、`SearchKnowledgeResult`及Context/Evidence对齐校验；
- `app/schemas/common.py`：`ToolName`加入`search_knowledge`，Evidence ID通用上限由10对齐到12；
- `app/schemas/__init__.py`：导出知识Tool Schema；
- `app/tools/registry.py`：保留M1两Tool工厂，新增隔离的M2三Tool工厂和`search_knowledge@1.0.0`定义；
- `app/tools/__init__.py`：只导出Registry工厂和后续Tool入口；
- `tests/unit/test_search_knowledge_contracts.py`、既有Tool/Provider/权限测试：验证严格Schema、敏感字段拒绝、Context/Evidence顺序、M1/M2 Registry隔离、角色、tenant scope、read side effect、描述与模型JSON Schema；
- M2入口和本记录：写入步骤日志。

验证：先写RED测试证明合同/Registry不存在；GREEN后运行新合同、`test_agent_tool_contracts.py`、`test_permissions.py`、`test_providers.py`和M2 Context合同相邻回归。

停止边界：不创建迁移、Service或Tool执行类。

### M2-19.2｜建立可复用Context的ToolCall审计关联

**只解决：相同Context如何被不同ToolCall复用，同时每次调用仍可审计。**

预计修改或新增：

- `app/models/runtime.py`、`app/models/__init__.py`：新增Tool-Context关联ORM、复合外键、唯一性和关系；收紧Document Evidence运行绑定形状，M1 database分支不变；
- `migrations/versions/20260902_0010_tool_context_links.py`：创建关联表、历史合法绑定回填、Document Evidence运行字段归一化、约束更新和安全降级；
- `app/repositories/evidence.py`：新增关联的幂等插入、当前行读取和冲突核对；
- `app/services/evidence.py`：`runtime_context`改为在同一保存点建立Tool-Context关联，不把可复用Evidence永久占给一个ToolCall；
- `tests/integration/test_tool_context_migration.py`、`test_knowledge_evidence_service.py`：覆盖迁移往返/拒绝降级、跨tenant/错run/错call、一个ToolCall两个Context拒绝、一个Context多ToolCall允许、相同关联幂等、Context/Evidence/关联整包回滚及M1 Evidence兼容；
- M2入口和本记录：写入步骤日志。

验证：真实PostgreSQL从0009升级0010、空表回退再升级；有审计关联时拒绝破坏性降级；Metadata与迁移一致；现有M1/M2 Evidence集成回归。

停止边界：不编排检索，不实现`SearchKnowledgeTool`。

### M2-19.3｜实现知识检索应用编排Service

**只解决：把既有安全零件按唯一顺序串起来，不处理Harness外壳。**

预计修改或新增：

- `app/services/knowledge.py`：新增`KnowledgeSearchService`及内部结果，输入可信CurrentUser、严格请求和可选运行审计Context；固定执行Reranker、Context Builder、Evidence持久化；
- `app/services/__init__.py`：导出Service；
- 可能只补充既有Service协议类型，不改变Dense/Lexical/RRF/Reranker/Builder算法；
- `tests/unit/test_knowledge_search_service.py`：Fake覆盖调用顺序、获权用户传递、supported/unsupported、Evidence对齐、运行Context传递、下游类型篡改和所有已知ApplicationError透传；
- `tests/integration/test_knowledge_search_service.py`：真实PostgreSQL使用固定向量/Fake Provider验证整条Service链、ACL撤销、active切代和原子回滚；
- M2入口和本记录：写入步骤日志。

验证：日常测试不加载真实BGE；使用Fake Embedding/Fake Reranker和真实PostgreSQL证明业务编排及数据边界。

停止边界：Service还不能被Agent或Harness作为Tool调用。

### M2-19.4｜实现`SearchKnowledgeTool`并接入Harness

**只解决：正式Tool适配器、可信身份绑定、权限/预算/超时/Trace和ToolEnvelope。**

预计修改或新增：

- `app/runtime/executor.py`：在`ToolExecutionContext`增加可信user/roles/market scopes，现有M1 Tool可忽略这些新增字段；
- `app/tools/search_knowledge.py`：实现绑定检查、Harness执行、Service调用、成功/错误ToolEnvelope和Evidence ID对齐；
- `app/tools/__init__.py`：导出新Tool；
- `tests/unit/test_search_knowledge_tool.py`：覆盖绑定、成功、无证据、错误Envelope、错误Evidence映射、CurrentUser不匹配和未知异常脱敏；
- `tests/integration/test_search_knowledge_tool.py`：真实Harness/Trace/PostgreSQL覆盖允许、角色/tenant拒绝、预算、重复调用、Tool超时、Provider/数据库错误、ToolCall状态及Tool-Context审计；
- 既有`test_harness_trace.py`、`test_agent_tools.py`和M1图测试：证明扩展执行Context没有破坏原两Tool；
- M2入口和本记录：写入步骤日志。

验证：检查成功ToolCall为success；ApplicationError为error；数据库/总时限为timeout；被拒绝的调用不进入Retrieval；错误Envelope没有data/Evidence ID。

停止边界：不接API、库存Agent、LangGraph或Qwen。

### M2-19.5｜完成真实权限/故障矩阵与阶段收口

**只解决：证明M2-19可重复、无越权、无审计冲突，并恢复正式演示基线。**

预计修改：

- `tests/integration/test_search_knowledge_tool.py`及必要的验收测试；
- 可能新增只使用Fake模型的可重复M2-19验收脚本，但只有存在手工演示价值时才创建，不为文件数量而创建；
- `docs/progress/M2/M2_KNOWLEDGE_RAG.md`、本记录、`docs/PROJECT_PROGRESS.md`；
- 不修改前端、API、Agent或Qwen。

验证矩阵：

- 当前用户有ACL且active成品存在：返回supported Context、1至12个Evidence及ToolCall关联；
- 无获权资料：success + unsupported + 空Evidence；
- owner、company owner、user/role/market ACL分别按既有规则生效；
- 跨tenant、撤权、Document/File软删除、旧Version、旧Index Set均不泄露；
- 相同用户/查询/快照的第二个ToolCall复用Context/Evidence但新增自己的审计关联；
- 重复同一ToolCall关联不增行，冲突Context拒绝；
- Embedding/Reranker Provider故障、PostgreSQL unavailable/timeout、Context/Evidence/关联写入故障均安全返回并无半成品；
- Tool预算、重复签名和总时间预算继续生效；
- M1两个Tool、库存图、Evidence读取和现有M2检索/Context链不回归。

完成后运行专项、相邻、默认全量、Ruff、格式、Mypy、compileall、pip check、Alembic current/heads/check和`git diff --check`；最后恢复M1/M2正式Seed并只读复核PostgreSQL、pgvector、Storage和库存125基线。

## 8. 验证策略与证据要求

### 8.1 TDD顺序

每个步骤必须先出现能准确证明缺失能力的RED，再做最小GREEN。不得先写完整实现后补形式化测试。

### 8.2 测试层级

| 层级 | 主要证明内容 | 不能代替什么 |
|---|---|---|
| Schema/Registry单元 | 输入输出、字段拒绝、Registry隔离、Tool描述和上限 | 不能证明真实ACL或数据库约束 |
| Service单元 | 调用顺序、类型边界、错误传播、无答案语义 | 不能证明SQL和事务 |
| PostgreSQL迁移/集成 | 复合外键、幂等关联、跨tenant拒绝、原子性、active/ACL | 不能证明Agent或Qwen回答 |
| Harness/Tool集成 | 权限、预算、超时、Trace状态、Envelope和Evidence关联 | 不能证明HTTP或前端 |
| 相邻/全量回归 | M1与M2既有能力未回归 | 不能证明生产规模和真实模型低延迟 |

### 8.3 真实模型边界

- 日常门禁只用Fake，不隐式加载或下载BGE-M3/BGE-Reranker；
- M2-17已经证明真实Reranker质量和本机资源成本，M2-19不重复数GB模型验收；
- 若实现过程中确需真实Smoke，必须再次单独说明资源影响并等待确认；
- 8秒默认总预算下不得把真实CPU Reranker描述成稳定低延迟能力。

## 9. 阶段完成标准

只有同时满足以下条件，M2-19才能标记为已完成：

1. `search_knowledge@1.0.0`严格Schema和Registry元数据已冻结；
2. M1 Registry仍精确两个Tool，M2 Registry精确三个已实现Tool；
3. 当前用户安全身份不能由模型或Tool参数覆盖；
4. Tool通过Harness执行权限、预算、超时和Trace，不存在绕过入口；
5. 成功链实际经过Hybrid、Reranker、Context Builder和Evidence持久化；
6. supported/unsupported两种成功结果合同稳定；
7. ToolEnvelope Evidence ID与Context逐项同序一致，最多12个；
8. 一个Context可被多个ToolCall复用，每个ToolCall有独立审计关联；
9. Context、Evidence和关联写入原子，故障不留下半成品；
10. tenant、ACL、active代次和软删除在真实PostgreSQL中继续生效；
11. M1 database Evidence、两个M1 Tool和库存Agent行为不回归；
12. 专项、相邻、全量和工程质量门禁完成并记录实际数字；
13. 正式Seed和Storage恢复并只读复核；
14. M2入口、过程记录和总看板同步；
15. 明确停止在M2-19，不自动开始M2-20。

## 10. 主要风险与优先排查方向

| 风险 | 表现 | 优先排查顺序 |
|---|---|---|
| CurrentUser与RunContext错配 | Tool有tenant但user/role/market不一致 | API/Agent注入来源 → RunContext复制 → ToolExecutionContext → Tool绑定校验 |
| Registry误开放 | 库存Agent意外看到知识Tool | `create_m1_tool_registry`精确集合 → Agent组装 → Provider `available_tools` |
| Evidence ID超过Envelope上限 | 11或12段Context校验失败 | ToolEnvelope max length → Context段数 → 映射顺序/去重 |
| 相同查询第二次持久化冲突 | Context已存在但ToolCall不同 | 确认Evidence运行字段为空 → ToolContextLink幂等键 → 冲突逐字段核对 |
| 审计关联与Evidence半成功 | 有Context/Evidence但无Tool关联 | 外层保存点范围 → Repository flush → 调用者rollback → Trace独立事务 |
| ACL撤销仍返回旧资料 | 检索后到保存间状态变化 | Retrieval共享安全门 → Context重新获权 → Evidence保存前再次获权 |
| Fake身份与活动索引不匹配 | Dense在Provider前拒绝或返回身份错误 | Seed索引Embedding身份 → Query Provider身份 → active Index Set |
| 真实Reranker超过8秒总预算 | ToolCall timeout | Fake/真实Backend配置 → Harness总预算 → Tool timeout → M2-21路由级预算策略 |
| 数据库timeout状态错误 | 应为timeout却记录error | 下游错误码 → Harness `DATABASE_TIMEOUT`分支 → Trace finish状态 |
| 未知异常泄露 | Envelope出现驱动、SQL或路径 | Service异常边界 → Harness catch-all → ToolExecutionError → arguments摘要脱敏 |

## 11. 当前停止点

M2-19完整方案与推荐决策已经由用户确认，M2-19.1合同/Registry、M2-19.2 ToolCall-Context审计关联、M2-19.3知识检索应用编排Service、M2-19.4正式Tool/Harness接入和M2-19.5权限/故障矩阵均已完成并验证。M2-19状态为`已完成`，没有接入API、Agent、Qwen或前端。

当前明确停止，等待用户理解并单独确认M2-20；不得自动开始M2-20、API、知识Agent/LangGraph、Qwen或前端。

## 12. 2026-09-02｜M2-19.1｜冻结知识Tool合同和隔离Registry

**状态：已完成；已验证；明确停止在M2-19.1。**

1. 本步解决的问题：M2此前只有内部检索、Context和Evidence能力，公共`ToolName`与Registry仍只认识M1两个Tool，也没有严格的知识Tool输入/输出合同；同时`ToolEnvelope`最多10个Evidence，与既有Context最多12段的合同不一致。本步只冻结“模型能传什么、公开结果长什么样、M1和M2分别能看见哪些Tool”，没有执行知识检索；
2. 大白话运行过程：现在先给未来的知识搜索按钮做“申请表、结果盒子和工具名册”。模型的申请表只能写一个自然语言问题；结果盒子只能装已经获准公开的Context；M1名册仍只有商品和库存两个按钮，M2名册才累计加入知识搜索。真正按按钮、查数据库、重排和保存证据仍未开始；
3. 输入、输出与上下游：输入是`SearchKnowledgeInput.query`，严格字符串去空白后1至2000字符；输出是`SearchKnowledgeResult.context`这一份`ContextBundle`。`evidence_ids`由Context片段按顺序计算为不参与序列化的只读属性，避免再保存一套重复Chunk结果。上游是未来模型Tool参数，当前下游只到Registry元数据；
4. 严格输入边界：Schema因继承`M1Schema`而拒绝额外字段，模型不能传tenant、user、role、market、SQL、路径、file/document ID、candidate count、top k、Embedding/Reranker模型参数或Context预算。生成给模型的JSON Schema只有必填`query`，并明确`additionalProperties=false`；
5. 严格输出边界：`SearchKnowledgeResult`只序列化`context`，复用M2-18已验证的公开标题、locator、片段文本、Evidence ID和Context自洽规则；额外防御校验要求`supported`与是否存在segments一致。无证据保持`supported=false + segments=[] + evidence_ids=()`，不是错误；输出没有tenant、ACL、Storage Key、本地路径、SQL、向量或Reranker原始分数；
6. 公共类型与上限：`ToolName`累计加入`search_knowledge`；`ToolEnvelope.evidence_ids`最大数量从10统一为12。既有成功Envelope仍必须有data且无error，错误Envelope仍必须有error、无data且Evidence为空，M1单Evidence行为未改变；
7. Registry隔离：`create_m1_tool_registry()`继续精确返回`get_product_spec`和`search_inventory`；新增`create_m2_tool_registry()`，精确累计上述两个Tool和`search_knowledge@1.0.0`。知识Tool登记为tenant范围、read副作用、允许`company_owner/product_scout/amazon_operator`三个现有角色；描述明确使用时机、Context/Evidence返回、无证据语义、合成数据和全部禁止参数；
8. 超时元数据：知识Tool登记硬超时为8000毫秒，与当前Harness总预算量级一致，但本步没有修改Harness全局8秒预算，也没有宣称真实CPU Reranker可稳定在该预算内。真实Reranker约7.24秒p95与整链预算冲突仍留到M2-21决策；
9. 实际修改文件与职责：
   - `app/schemas/knowledge.py`：新增`SearchKnowledgeInput`、`SearchKnowledgeResult`、supported/segments防御校验和按Context顺序派生Evidence ID；
   - `app/schemas/common.py`：扩展公共`ToolName`并把Envelope Evidence上限统一为12；
   - `app/schemas/__init__.py`：从Schema公共入口导出两个新合同；
   - `app/tools/registry.py`：抽取可复用的M1定义，保持M1精确两Tool，并新增隔离的M2三Tool工厂和知识Tool元数据；
   - `app/tools/__init__.py`：只导出`create_m2_tool_registry`，没有导出执行类；
   - `tests/unit/test_search_knowledge_contracts.py`：新增21项参数化合同测试，覆盖严格输入、敏感字段、公开输出、自相矛盾Context、12/13上限、Registry隔离、角色/范围/副作用、描述、JSON Schema和后续文件未提前创建；
   - 本记录、M2入口和总进度看板：同步步骤证据、验证基线与下一停止点；
10. 完整调用链位置：本步实际链路为`SearchKnowledgeInput Schema → SearchKnowledgeResult/ContextBundle Schema → Tool Registry元数据`。在项目完整链路中只经过Schema与Tool Registry元数据；不经过前端、HTTP API、Harness执行、Tool执行、Service、Repository、Model、PostgreSQL业务查询、Storage、Agent/LangGraph、Qwen、Citation Validator或前端；
11. TDD RED证据：先只新增`tests/unit/test_search_knowledge_contracts.py`，运行`.venv\Scripts\python.exe -m pytest -q tests/unit/test_search_knowledge_contracts.py`；收集阶段因`ImportError: cannot import name 'SearchKnowledgeInput' from 'app.schemas'`失败，退出码1，准确证明公共知识Tool合同和导出不存在；没有先写生产实现；
12. GREEN与相邻回归：最小实现后新合同为`21 passed in 0.40s`；指定的知识合同、M1 Tool合同、权限、Provider、Context合同和M2基线首次合计`122 passed in 9.73s`，补强无证据成功Envelope断言后的最终复核为`122 passed in 2.89s`。这证明M1 Registry仍精确两Tool，M2 Registry精确三Tool，Provider现有投影没有被自动扩大，Context与Envelope的12条边界及`success + unsupported + []`语义兼容；
13. 全量与工程质量：原样默认全量为`794 passed, 10 skipped, 1 failed in 63.78s`；唯一失败仍是既有`test_parse_failure_marks_first_index_failed_without_creating_index_set`把上传Key写死为`2026/08`，而当前2026年9月夹具使用另一Key。排除显式真实模型Smoke和该既有用例后为`794 passed, 2 skipped, 1 deselected in 56.60s`。全仓Ruff lint通过，241个Python文件格式正确，Mypy为114个`app`模块无问题，compileall、pip check和`git diff --check`通过；
14. 数据库与迁移门禁：初次Alembic检查因Docker Desktop未运行而等待，确认原因后中止等待进程并启动既有本地Docker环境；PostgreSQL healthy后，Alembic current/heads均为`20260901_0009 (head)`，`alembic check`为`No new upgrade operations detected`。本步没有新增Model、表或迁移；
15. 能证明与不能证明：能证明知识Tool公共输入只有有界query，输出只包装公开Context，supported/segments与Evidence顺序可确定，Envelope可承载12个Evidence且拒绝13个，M1/M2 Registry隔离和元数据稳定，既有M1 Provider/权限/Envelope未回归。不能证明Tool真的执行、CurrentUser已传入Harness回调、ACL在一次Tool调用中生效、Hybrid/Reranker/Context/Evidence已被编排、ToolCall可复用Context、事务/超时/Trace、API、Agent、Qwen回答或前端；这些分别属于M2-19.2至M2-23；
16. 风险、正式数据与停止点：Registry异常先检查调用方是否误用M2工厂替换M1工厂，再检查模型投影名单；输入异常先检查是否出现后端拥有字段；12段输出异常先检查Context片段数、Evidence顺序与Envelope上限；真实执行超时仍先检查Fake/真实Provider和M2-21预算策略。全量测试后依次运行`python -m scripts.seed_m1`、`seed_m2_files`、`seed_m2_complex_files`恢复正式数据；只读复核为PostgreSQL 17.11、pgvector 0.8.6、10 files、10 documents、10 versions、9 ACL、10 parse/index pending、0 active Version、0 Chunk Set/Index Set/Chunk、0 ContextArtifact/Evidence，Storage精确10个uploads，德国仓可售库存125。没有加载或下载真实BGE。M2-19.1已完成，明确没有开始M2-19.2，必须等待用户单独确认。

## 13. 2026-09-02｜M2-19.2｜建立可复用Context的ToolCall审计关联

**状态：已完成；已验证；明确停止在M2-19.2。**

1. 本步目标：解决确定性Context/Evidence可跨重试复用、但Document Evidence原有运行外键只能永久归属一个ToolCall的冲突。输入是可信`tenant_id + agent_run_id + tool_call_id`与已经验证的`BuiltContext`；输出是同一事务保存点内的一条可审计`ToolContextLink`。同一ToolCall最多关联一个Context，同一Context允许被多个ToolCall复用；
2. 大白话运行过程：未来每次知识搜索都像一张独立工单。资料包可以复用，不必为相同资料重复抄一份Evidence；系统另存一张“这张工单使用了哪个资料包”的关联单。重试同一工单不会重复建单，另一张工单可指向同一资料包，试图让同一工单改指另一资料包会整体拒绝；
3. 数据库合同：新增`tool_context_links`，以复合外键保证关联中的tenant、ToolCall、AgentRun和Context真实同属；`tenant_id + tool_call_id`唯一约束表达一ToolCall一Context，`tenant_id + context_artifact_id`普通索引支持反查一Context的多次调用；删除ToolCall级联清理其关联，仍被审计引用的Context禁止静默删除；
4. Evidence所有权：M2 `knowledge/user_file` Evidence现在必须保持`agent_run_id/tool_call_id`同时为空，其运行审计经关联表表达；M1 `database` Evidence仍必须直接绑定唯一AgentRun/ToolCall，原有库存Evidence语义没有改变；
5. 0010迁移：创建关联表后，先拒绝无法表示的“一个历史ToolCall关联多个Context”；把已有合法Document Evidence运行对去重回填到关联表，再清空Document Evidence运行字段并收紧`ck_evidences_source_shape`。空关联表可安全回退到0009；只要存在关联，降级明确报错，避免静默丢失审计事实；
6. Repository与Service：Repository只接受精确tenant/run/call且`tool_name=search_knowledge`、权限已允许、状态为running/success的ToolCall；关联使用`ON CONFLICT DO NOTHING`后重新锁行逐字段核对，区分合法幂等与冲突。Service把Context、Evidence、ToolContextLink放在既有同一个`begin_nested`保存点，任一写入或核对失败都整包回滚，不自行commit；
7. 实际修改文件与职责：
   - `app/models/runtime.py`、`app/models/__init__.py`：新增关联ORM、关系、复合外键、唯一约束和Document Evidence运行字段形状；
   - `migrations/versions/20260902_0010_tool_context_links.py`：实现建表、历史回填、约束切换和安全降级；
   - `app/repositories/evidence.py`：锁定可关联知识ToolCall、幂等插入及精确读取关联；
   - `app/services/evidence.py`：Document Evidence不再占有ToolCall，在原子保存点内创建/核对关联；
   - `tests/integration/test_tool_context_migration.py`：覆盖迁移往返、元数据、历史回填、降级保护、复合归属、跨tenant/错run、一对多/一对一和M1兼容；
   - `tests/integration/test_knowledge_evidence_service.py`：覆盖关联创建、Evidence运行字段为空、相同关联幂等、同Context多ToolCall、同ToolCall冲突Context及关联故障整包回滚；
   - `tests/unit/test_search_knowledge_contracts.py`：把停止边界推进到M2-19.2，继续禁止提前创建M2-19.3 Service和M2-19.4 Tool执行文件；
   - 本记录、M2入口与总看板：同步步骤证据、验证基线和下一停止点；
8. 完整调用链位置：本步新增链路为`EvidenceService → KnowledgeEvidenceRepository → ToolContextLink ORM → PostgreSQL 0010`，并复用M2-18的Context/Evidence保存点。若按阶段拆分，本步只建立`ToolCall审计元数据 ↔ ContextArtifact`的持久关联；不经过前端、HTTP API、Harness实际执行、SearchKnowledgeTool、KnowledgeSearchService、Hybrid/Reranker编排、Agent/LangGraph、Qwen、Citation Validator调用或Storage读取；
9. TDD RED证据：先新增/扩展两个真实PostgreSQL集成测试，再运行`.venv\Scripts\python.exe -m pytest -q tests/integration/test_tool_context_migration.py tests/integration/test_knowledge_evidence_service.py`；收集阶段出现2个错误，均为`ImportError: cannot import name 'ToolContextLink' from app.models.runtime`，退出码1，准确证明关联ORM和后续迁移/持久化入口尚不存在；
10. GREEN修正过程：最小实现后的首轮为`11 failed, 2 passed`。迁移合同和数据库约束测试已经通过，失败根因是新增迁移回填测试的清理函数把`Tenant.id`误当`Tenant.tenant_id`，遗留一组本轮测试数据并污染后续全库计数。只修复测试清理与按当前tenant计数，先只读确认并精确删除该组本轮测试租户数据，没有修改生产约束；最终聚焦为`13 passed in 5.20s`；
11. 相邻回归：首轮为`182 passed, 1 failed`，唯一失败是M2-19.1旧停止哨兵仍断言0010文件不得存在。将哨兵推进为“允许19.2迁移，但禁止19.3 Service和19.4 Tool执行类”后，M1库存Evidence、Harness/Trace、Agent Tool及M2 Context/Evidence、Citation、模型/合同合计`183 passed in 9.41s`；
12. 全量与工程质量：原样默认全量为`801 passed, 10 skipped, 1 failed in 58.78s`；唯一失败仍是既有跨月上传Key测试把删除目标写死为`2026/08`，当前真实Key位于`2026/09`，与本步无调用关系且没有越权修改。排除显式真实模型Smoke和该既有用例后为`801 passed, 2 skipped, 1 deselected in 58.65s`。Ruff lint通过，243个Python文件格式正确，Mypy为114个`app`模块无问题，compileall、pip check和`git diff --check`通过；
13. 迁移门禁：真实PostgreSQL已实际完成0009→0010、空表0010→0009→0010、历史绑定回填及有关联拒绝降级。最终Alembic current与heads均为`20260902_0010 (head)`，`alembic check`为`No new upgrade operations detected`，说明ORM Metadata与迁移没有新增漂移；
14. 能证明的内容：能证明数据库会拒绝跨tenant Context、错AgentRun和一ToolCall两个Context；允许一Context被多ToolCall引用；相同关联重试不增行；Document Evidence不再永久占有某次调用；M1 database Evidence仍可直接绑定；Context/Evidence/关联任一失败不会留下本步半成品；历史合法数据可迁移且审计关联不会被降级静默删除；
15. 不能证明的内容：本步没有执行`search_knowledge`，不能证明Hybrid/Reranker/Context已被应用Service编排，也不能证明Harness可信身份、权限/预算/超时、ToolEnvelope、API、Agent、Qwen答案、引用语义或前端；真实CPU Reranker与8秒预算冲突仍留到M2-21。本步没有加载或下载真实BGE；
16. 风险与排查顺序：关联失败先查`ToolCall tenant/run/id → tool_name/permission/status → Context tenant → 唯一关联的既有context_id → 外层事务状态`；迁移失败先查历史Document Evidence是否同一ToolCall跨多个Context，再查复合外键；降级失败先确认是否存在必须保留的审计关联，不应直接删表；半成品先查`begin_nested`范围、Repository flush和调用者事务所有权，不应绕过约束；
17. 正式数据与停止点：全量测试修改了共享测试/演示数据库，本轮曾精确清理一组由失败清理函数遗留的测试租户；随后依次运行仓库既有`seed_m1 → seed_m2_files → seed_m2_complex_files`恢复正式数据。只读复核为PostgreSQL 17.11、pgvector 0.8.6、10 files、10 documents、10 versions、9 ACL、10 parse/index pending、0 active Version、0 Chunk Set/Index Set/Chunk、0 ContextArtifact/Evidence/ToolContextLink；Storage精确10个uploads、0 parsed/chunks/other，德国仓可售库存125。M2-19.2已完成，明确没有开始M2-19.3，必须等待用户单独确认。

## 14. 2026-09-02｜M2-19.3｜实现知识检索应用编排Service

**状态：已完成；已验证；明确停止在M2-19.3。**

1. 本步目标：既有Hybrid/Reranker、Context Builder和Evidence持久化都是独立安全零件，但此前没有应用层入口保证唯一调用顺序。输入冻结为可信`CurrentUser`、严格`SearchKnowledgeInput`和可选`EvidenceWriteContext`；输出为`KnowledgeSearchOutcome`，其中公开`SearchKnowledgeResult`只包装Context，内部只额外保留`reused`幂等信号；
2. 大白话运行过程：Service像生产线总指挥。它把用户问题转换为只有query的服务端检索单，先让Reranker调用既有Hybrid找资料，再让Builder重新验权并整理资料包，最后让Evidence Service保存资料包、证据卡和可选ToolCall关联。任何零件报出既有安全错误都原样向未来Tool传递，不跳步、不返回半成品；
3. 固定编排顺序：`SearchKnowledgeInput → RetrievalRequest → RerankerRetrievalService → Hybrid(Dense + Lexical) → ContextBuilderService → EvidenceService → SearchKnowledgeResult`。候选数、RRF、top k、Context预算、模型身份和权限范围仍由既有服务端构造器拥有，调用者不能通过本Service覆盖；
4. 可信身份：同一个`CurrentUser`对象逐步传给Reranker、Builder和Evidence；可选运行审计对象不从query构造，只原样传给Evidence Service，由M2-19.2的tenant/run/call和数据库约束再次验真。字典伪造用户或拿`RetrievalRequest`冒充知识Tool合同会在入口被拒绝；
5. 下游边界：Reranker返回值必须是可重新校验的`RerankedRetrievalResponse`；Builder返回值必须是`BuiltContext`；Evidence返回值必须是`PersistedDocumentContext`。类型被Fake或错误适配器篡改时，分别映射为既有`RetrievalInternalError`、`ContextDataContractError`和`KnowledgeEvidencePersistenceError`，不把私有对象直接交给未来Tool；
6. Context/Evidence对齐：返回前逐段核对持久化Bundle与BuiltContext完全相等，Evidence数量、UUID、Context ID、`[E#]`、source type、Chunk身份、文档元数据、公开locator和Context正文Hash逐项对应。公开Evidence ID仍只由`SearchKnowledgeResult.context.segments`按顺序派生，不新增第二套Chunk结果；
7. 错误语义：Retrieval输入、Embedding Provider/身份、Reranker Provider、PostgreSQL unavailable/timeout、内部检索、Context输入/合同/构建和知识Evidence持久化等相关既有`ApplicationError`均保持原对象透传；未知异常继续留给M2-19.4 Tool/Harness统一转换，本步不抢先实现Tool错误Envelope；
8. 实际修改文件与职责：
   - `app/services/knowledge.py`：新增三个最小Protocol、`KnowledgeSearchOutcome`与固定顺序`KnowledgeSearchService`，完成类型、持久化结果和Evidence对齐防御；
   - `app/services/__init__.py`：从Service受控公共入口导出Outcome与Service；
   - `tests/unit/test_knowledge_search_service.py`：19项Fake测试覆盖调用顺序、同一获权用户、服务端请求、运行审计传递、有/无证据、复用信号、类型篡改、Bundle/Evidence错位和11类相关ApplicationError透传；
   - `tests/integration/test_knowledge_search_service.py`：5项真实PostgreSQL测试使用固定向量、Fake Embedding/Fake Reranker覆盖完整Service链、幂等ToolCall关联、无ACL空结果、检索后撤权、active Index Set切代及Evidence写入故障回滚；
   - `tests/unit/test_search_knowledge_contracts.py`：停止哨兵推进为“Service必须存在，但SearchKnowledgeTool执行文件仍不得存在”；
   - 本记录、M2入口和总看板：同步步骤证据、验证基线与下一停止点；
9. 完整调用链位置：`CurrentUser + SearchKnowledgeInput + optional EvidenceWriteContext → KnowledgeSearchService → Reranker → Hybrid → Dense/Lexical → RetrievalRepository → PostgreSQL FTS/pgvector → ContextBuilder → EvidenceService → ContextArtifact/Evidence/ToolContextLink → PostgreSQL → KnowledgeSearchOutcome/SearchKnowledgeResult`。本步经过Schema、Service、Repository、Model和PostgreSQL；不经过前端、HTTP API、Harness执行、SearchKnowledgeTool、Agent/LangGraph、Qwen、Citation Validator调用或Storage读取；
10. TDD RED证据：先新增`tests/unit/test_knowledge_search_service.py`并运行聚焦测试；收集阶段因`ImportError: cannot import name 'KnowledgeSearchOutcome' from app.services`失败，退出码1，准确证明应用编排Service与公共导出不存在；生产实现是在该RED之后才创建；
11. 单元GREEN过程：最小实现后的第一次收集因参数化测试误用Pytest保留名`request`而停止，尚未进入业务断言；只把测试变量改名为`search_request`，未改生产逻辑。最终19项单元测试为`19 passed in 1.47s`；
12. 真实集成过程：首轮真实链为`3 passed, 2 failed`。撤权、切代和无ACL路径已通过；两项成功链在Context合同层失败，原因是复用的Lexical夹具修改正文后仍保留检索阶段固定`token_count=10`，Builder正确拒绝。只在新集成装配中用既有Unicode Token Counter重算该测试夹具预算，没有放宽Builder；最终为`5 passed in 3.13s`；
13. 聚焦与相邻回归：本步Service单元、真实集成和知识合同合计`45 passed in 3.18s`；包含Dense、Lexical、Hybrid、Reranker、Context、Evidence、0010关联和M1库存Evidence的相邻集合为`163 passed in 11.92s`；
14. 全量与工程质量：原样默认全量为`825 passed, 10 skipped, 1 failed in 60.55s`；唯一失败仍是既有跨月上传Key测试固定删除`2026/08`，当前真实Key位于`2026/09`，与本步无调用关系且未越权修改。排除显式真实模型Smoke和该既有用例后为`825 passed, 2 skipped, 1 deselected in 62.44s`。全仓Ruff lint通过，246个Python文件格式正确，Mypy为115个`app`模块无问题，compileall、pip check和`git diff --check`通过；
15. 数据库与模型门禁：本步没有新增或修改ORM/迁移；Alembic current与heads继续为`20260902_0010 (head)`，`alembic check`无新升级操作。日常验证只使用Fake Embedding和Fake Reranker，没有加载或下载真实BGE；
16. 能证明的内容：能证明未来适配器只需调用一个Service即可按固定顺序运行权限前置检索、精排、Context重新获权和Evidence原子持久化；有证据返回1至12个对齐Evidence，无权限正常返回unsupported空Context；检索与Builder之间撤权或切代会被拒绝；相同ToolCall重试复用Context/Evidence/关联；Evidence写入故障不留下Context；
17. 不能证明的内容：本步没有SearchKnowledgeTool或Harness回调，因此不能证明Registry权限真的执行、CurrentUser与ToolExecutionContext逐项绑定、预算/超时/Trace状态、ToolEnvelope成功/错误形状、API、Agent、Qwen回答、Citation Validator语义或前端。真实CPU Reranker仍不能据此宣称满足8秒整链预算；
18. 风险与排查顺序：无结果先查`CurrentUser/ACL/active代次 → Dense/Lexical → Hybrid → Reranker`；Context失败再查`Reranker四重身份 → 当前获权窗口 → Chunk token/hash/locator → Context预算`；持久化失败查`BuiltContext验真 → 再获权 → Context/Evidence对齐 → ToolContextLink → 外层事务`；错误类型异常查具体下游是否返回公共合同，不应在编排层捕获所有Exception或泄露私有原因；
19. 正式数据与停止点：全量测试修改了共享测试/演示数据库，随后依次运行既有`seed_m1 → seed_m2_files → seed_m2_complex_files`恢复。只读复核为PostgreSQL 17.11、pgvector 0.8.6、10 files、10 documents、10 versions、9 ACL、10 parse/index pending、0 active Version、0 Chunk Set/Index Set/Chunk、0 ContextArtifact/Evidence/ToolContextLink；Storage精确10个uploads、0 parsed/chunks/other，德国仓可售库存125。M2-19.3已完成，明确没有开始M2-19.4，必须等待用户单独确认。

## 15. 2026-09-02｜M2-19.4｜实现SearchKnowledgeTool并接入Harness

**状态：已完成；已验证；明确停止在M2-19.4。**

1. 本步目标：M2-19.3已经有固定知识检索Service，但此前没有正式Tool把它放进Harness的权限、预算、超时和Trace边界。输入仍只有严格`SearchKnowledgeInput.query`，应用侧另绑定可信`CurrentUser`；输出是标准`ToolEnvelope[SearchKnowledgeResult]`。本步只接通Tool适配器与Harness，不接API、库存Agent、LangGraph、Qwen或前端；
2. 大白话运行过程：Harness先核对“这个Tool是否在M2名册、当前角色能否调用、预算是否还有余额”，并先落一张运行中的ToolCall审计单；随后Tool把应用绑定的用户与Harness可信身份逐项对照，通过后才把run/call编号交给现有Service。Service保存Context/Evidence和关联，回来后Harness把ToolCall更新为success/error/timeout，Tool只返回公开Envelope；
3. 可信身份与输入边界：`ToolExecutionContext`新增`user_id/roles/market_scopes`，全部从不可由模型覆盖的`RunContext`复制；`SearchKnowledgeTool`逐项核对绑定`CurrentUser`的user、tenant、roles和market scopes。query仍是唯一模型参数，tenant、用户、角色、市场和审计ID都不能从Tool参数进入；
4. 成功与错误语义：supported Context按段落顺序把1至12个Evidence ID写入Envelope；unsupported是`status=success + supported=false + segments=[] + evidence_ids=[]`。已知`ApplicationError`保留公共错误码；未知异常由Harness统一转为不含SQL、路径或秘密的`ToolExecutionError`；错误Envelope始终无data和Evidence ID；
5. Harness与Trace状态：Registry/角色拒绝及重复预算在业务回调前记为denied；回调成功记success；Provider等应用错误记error；Tool硬超时、总时限和`DATABASE_TIMEOUT`记timeout。知识运行路由只增加审计字面量`knowledge_query`，没有实现知识Agent或路由图；
6. ToolCall-Context锁修正：真实成功链首次执行时发现M2-19.2读取ToolCall使用`FOR UPDATE`，业务事务尚未提交时Harness又要更新同一ToolCall状态，形成互等。Repository将该锁精确降为PostgreSQL`FOR KEY SHARE`：仍防止所引用ToolCall的键被删除/更改并配合复合外键验真，同时允许Harness更新非键状态字段；没有放宽tenant/run/call/name/permission/status过滤或关联唯一约束；
7. 实际修改文件与职责：
   - `app/runtime/executor.py`：把可信用户、角色和市场范围复制到允许后的Tool回调Context；既有M1 Tool可安全忽略新增字段；
   - `app/runtime/trace.py`：为正式知识Tool审计增加`knowledge_query`运行路由字面量；
   - `app/tools/search_knowledge.py`：新增合同绑定、Harness调用、身份核对、Service适配、Evidence对齐和成功/错误Envelope；
   - `app/tools/__init__.py`：使用延迟公共导出暴露`SearchKnowledgeTool`，避免`executor → registry → app.tools`循环导入；
   - `app/repositories/evidence.py`：把可关联知识ToolCall的行锁从`FOR UPDATE`改为`FOR KEY SHARE`，解决正式Harness状态更新死锁；
   - `tests/unit/test_search_knowledge_tool.py`：10项Fake测试覆盖绑定、supported/unsupported、可信审计ID传递、已知错误、四类身份错配、Evidence错位和未知异常脱敏；
   - `tests/integration/test_search_knowledge_tool.py`：7项真实Harness/Trace/PostgreSQL测试覆盖成功Context关联、角色/tenant拒绝、重复预算、8秒Tool超时、Provider错误和数据库timeout；
   - `tests/integration/test_harness_trace.py`：补充M1 Harness回调确实收到原RunContext安全身份的回归断言；
   - `tests/unit/test_search_knowledge_contracts.py`：停止哨兵推进为Tool存在，但知识Agent/API和库存图接线仍不得出现；
8. 完整调用链位置：`RunContext/CurrentUser + SearchKnowledgeInput → M2 Tool Registry → PermissionGuard/ExecutionBudget → TraceRecorder ToolCall → ToolExecutionContext → SearchKnowledgeTool → KnowledgeSearchService → Reranker/Hybrid/Dense/Lexical → ContextBuilder → EvidenceService → ContextArtifact/Evidence/ToolContextLink → PostgreSQL → ToolEnvelope`。本步新增并实际验证的是`Schema → Registry → Harness → Tool → Service`接缝及审计回写；既有Service真实PostgreSQL下游由M2-19.3继续提供。仍不经过前端、HTTP API、Agent/LangGraph、Qwen或Citation Validator调用；
9. TDD RED证据：先新增Tool单元测试并扩展Harness身份断言，运行时在测试收集阶段因`ImportError: cannot import name 'SearchKnowledgeTool' from app.tools`失败，退出码1，准确证明正式Tool和公共导出不存在；生产实现是在该RED之后才创建；
10. 单元GREEN：最小扩展执行Context、Tool和延迟导出后，Tool单元加既有Harness/Trace为`17 passed in 11.69s`；随后单元与真实Tool专项最终为`17 passed in 4.02s`；
11. 真实集成过程：首轮为`6 passed, 1 failed`，失败公开错误为知识Evidence保存失败。进一步单测成功路径时确认不是Context合同，而是ToolCall行锁与Harness回写冲突；修正为`FOR KEY SHARE`后新集成为`7 passed in 3.96s`。期间为中止互等测试进程留下2条`running`测试AgentRun，只读核对其Thread均为本轮`M1-15 Agent Tool Test`后按精确Thread UUID清理，没有删除正式业务行；
12. 相邻回归：首轮`200 passed, 2 failed`。一项是19.3停止哨兵仍禁止Tool文件，推进到19.4边界后解决；另一项是上述中断进程遗留测试行污染全库计数，精确清理后解决。最终包含M1 Tool/Registry/库存图/Harness/权限和M2合同/Service/Context/Evidence的相邻集合为`202 passed in 16.82s`；
13. 全量验证：排除显式真实模型Smoke和既有跨月用例后为`842 passed, 2 skipped, 1 deselected in 67.41s`；原样默认全量为`842 passed, 10 skipped, 1 failed in 62.63s`。唯一失败仍是既有`test_parse_failure_marks_first_index_failed_without_creating_index_set`删除写死的`2026/08`上传Key，而当前9月夹具使用另一Key；它与本步Tool/Harness链无关，未越权修改；
14. 工程质量与迁移门禁：Ruff lint通过，249个Python文件格式正确；Mypy对116个`app`模块无问题；compileall、pip check和`git diff --check`通过。Alembic current/heads均为`20260902_0010 (head)`，`alembic check`无新升级操作；本步没有新增迁移或修改0010数据库结构；
15. 能证明的内容：能证明正式知识Tool只有query可由模型控制，绑定身份无法被CurrentUser替换；M2 Registry权限、重复预算、8秒Tool超时和Trace状态实际生效；unsupported正常成功；Provider/数据库错误安全映射；Envelope Evidence与Context同序；成功ToolCall能在真实PostgreSQL关联Context；M1 Registry仍精确两Tool且库存Tool/图未回归；
16. 不能证明的内容：本步不能证明HTTP请求、知识路由、LangGraph、Qwen基于Evidence回答、Citation Validator实际调用或前端展示；更完整的owner/company owner/user/role/market ACL、软删除、旧代次、多ToolCall复用和故障原子矩阵仍属于M2-19.5。日常验证使用Fake Provider，没有证明真实CPU Reranker满足8秒整链预算，也没有加载或下载真实BGE；
17. 风险与排查顺序：权限异常先查`M1/M2 Registry工厂 → RunContext角色/tenant → Tool绑定CurrentUser`；无结果查`ACL/active代次 → Dense/Lexical → Hybrid/Reranker`；关联失败查`ToolCall name/permission/status → FOR KEY SHARE/外层事务 → 复合外键/唯一约束`；超时查`Fake/真实Provider → Tool 8000ms → total budget`；Trace状态异常查`PermissionGuard/预算发生点 → Harness异常分支 → Trace独立事务`；
18. 正式数据恢复：全量测试后依次运行既有`seed_m1 → seed_m2_files → seed_m2_complex_files`。只读复核为PostgreSQL 17.11、pgvector 0.8.6、10 files、10 documents、10 versions、9 ACL、10 parse/index pending、0 active Version、0 Chunk Set/Index Set/Chunk、0 ContextArtifact/Evidence/ToolContextLink/AgentRun/ToolCall；Storage精确10个uploads、0 parsed/chunks/other，德国仓可售库存125；
19. 停止点：M2-19.4已完成并验证，明确没有开始M2-19.5、M2-20、API、知识Agent/LangGraph、Qwen或前端。下一步必须等待用户单独确认M2-19.5。

## 16. 2026-09-02｜M2-19.5｜完成真实权限/故障矩阵与阶段收口

**状态：已完成；已验证；M2-19整体已完成。**

1. 本步目标：M2-19.4已经证明正式知识Tool可进入Harness，但完整验收仍缺owner、company owner、user/role/market ACL、跨tenant、旧代次、软删除、多ToolCall复用、撤权竞态、总时限和持久化故障的同层证据。本步只补齐真实权限/故障矩阵并收口M2-19，不新增业务接口或生产能力；
2. 大白话运行过程：为每种权限准备真实PostgreSQL文档和active索引，用Fake Embedding/Fake Reranker避免下载大模型；每次都创建真实Thread、AgentRun和ToolCall，让问题完整经过Registry、Harness、Tool、Service、检索、Context和Evidence。测试结束后按依赖顺序删除临时数据，最终再恢复正式Seed；
3. 输入输出与上下游：输入仍是可信`CurrentUser`和只有query的`SearchKnowledgeInput`；输出仍是`ToolEnvelope[SearchKnowledgeResult]`。上游实际经过M2 Registry、PermissionGuard、ExecutionBudget和Trace；下游实际经过Fake模型、真实PostgreSQL检索、ContextBuilder、EvidenceService及ToolContextLink，没有增加任何新参数、返回字段或绕过入口；
4. 权限矩阵：正式Tool实测`product_scout`文档Owner、`amazon_operator`文档Owner、user ACL、role ACL、market ACL和`company_owner`租户内读取均成功；三个既有业务角色都能调用，但结果仍由相同tenant/ACL边界决定；
5. 排除矩阵：company owner的真实Tool结果中明确不包含跨tenant Chunk、旧Document Version、旧Index Set、pending/failed Index Set、软删除Document和软删除File；返回Evidence ID继续与Context segments逐项同序；
6. 复用矩阵：相同用户和query通过两个独立Harness运行产生两个不同ToolCall；两次返回同一个确定性Context和同一组Evidence，数据库只有1个ContextArtifact和一组Evidence，但有2条各自归属ToolCall的ToolContextLink；既有同ToolCall幂等和冲突拒绝继续由M2-19.2测试覆盖；
7. 竞态与原子性：Reranker完成后删除目标user ACL，Context重新获权使正式Tool安全失败，Envelope无data/Evidence，ToolCall记error，ContextArtifact/Evidence/ToolContextLink均为0。分别注入Evidence写入和ToolContextLink写入SQLAlchemy故障，正式Tool同样返回脱敏错误且三类业务行均为0；
8. 预算和故障状态：除19.4已有重复签名和Tool 8秒硬超时外，本步新增总运行时限在回调前拒绝，Service调用次数为0且ToolCall为`permission_result=denied/status=timeout`；Embedding Provider、Reranker Provider、数据库 unavailable/timeout均保持安全错误码，其中数据库timeout记Trace timeout，其余记error；
9. TDD RED证据：先只扩展`tests/integration/test_search_knowledge_tool.py`并运行，首轮为`12 passed, 7 failed, 10 errors in 15.91s`。7项成功链返回`RetrievalInternalError`，10项teardown因File/Version复合外键清理顺序错误；准确暴露“Repository级简化夹具不能直接冒充完整可执行索引”和“提交型验收夹具需要依赖顺序清理”，生产安全校验没有被放宽；
10. RED排查与最小修正：只在测试装配中把active Index Set补成Fake Embedding完整身份与Hash，并为Chunk补合法page/block/character locator；inactive旧Index Set保留不同身份，避免破坏唯一约束和旧代次测试。清理顺序改为`Thread/运行审计 → Link/Evidence/Context → Document及其级联版本/索引/Chunk → Tenant/File/User`。首轮teardown遗留20个名称精确为`M2-16.3 retrieval/other tenant`的临时Tenant，只读列出后按上述依赖和精确名称清理，没有删除正式租户；
11. 生产变更：本步没有修改`app/`生产代码、ORM或迁移。所有既有Embedding身份、locator、ACL、active代次、软删除、复合外键、唯一约束和Harness错误语义保持不变；只扩展验收测试与M2-19完成停止哨兵；
12. 实际修改文件与职责：
   - `tests/integration/test_search_knowledge_tool.py`：由7项扩展到21项，新增真实三角色/五类授权、排除集合、两ToolCall复用、撤权竞态、Evidence/Link故障、Reranker/数据库故障和总时限矩阵；
   - `tests/unit/test_search_knowledge_contracts.py`：停止哨兵推进为M2-19完整实现存在，但M2-20的`read_uploaded_file/get_evidence_detail`、知识图/API和库存图知识接线仍不存在；
   - 本记录、M2入口和总看板：同步M2-19已完成状态、基线、风险和下一停止点；
13. 完整调用链位置：`CurrentUser/RunContext + SearchKnowledgeInput → M2 Tool Registry → PermissionGuard/ExecutionBudget → TraceRecorder → SearchKnowledgeTool → KnowledgeSearchService → Dense/Lexical/Hybrid → Fake Embedding/Fake Reranker → RetrievalRepository/PostgreSQL → ContextBuilder → EvidenceService → ContextArtifact/Evidence/ToolContextLink → ToolEnvelope`。本步验证整条内部Tool链；仍不经过HTTP API、知识Agent/LangGraph、Qwen、Citation Validator实际调用或前端；
14. GREEN与相邻回归：完成测试装配后正式Tool矩阵为`21 passed in 9.77s`；知识合同加Tool矩阵复核为`42 passed in 9.63s`；加入M1 Tool/Registry/Harness/库存图和M2检索/Context/Evidence/Service的相邻集合为`231 passed in 26.34s`；
15. 全量结果：排除显式真实模型Smoke和既有跨月用例后为`856 passed, 2 skipped, 1 deselected in 68.45s`；原样默认全量为`856 passed, 10 skipped, 1 failed in 70.71s`。唯一失败仍是既有`test_parse_failure_marks_first_index_failed_without_creating_index_set`删除写死的`2026/08`Key，而当前9月夹具使用另一Key；与本步无调用关系，未越权修改；
16. 工程质量与迁移门禁：Ruff lint通过，249个Python文件格式正确；Mypy对116个`app`模块无问题；compileall、pip check和`git diff --check`通过。Alembic current/heads均为`20260902_0010 (head)`，`alembic check`无新升级操作；本步没有迁移；
17. 能证明的内容：能证明M2-19的严格合同、隔离Registry、可信身份、Harness权限/预算/超时/Trace、权限前置检索、Context重新获权、Evidence/关联原子性、跨ToolCall复用和公开Envelope在当前合成数据/真实PostgreSQL/Fake模型基线下可重复；也能证明M1两Tool和库存图未被M2 Registry扩大；
18. 不能证明的内容：不能证明生产规模、高并发、百万Chunk、真实BGE低延迟、HTTP、知识Agent/LangGraph、Qwen基于Evidence回答、Citation Validator实际调用或前端展示。真实CPU Reranker与8秒整链预算冲突仍留到后续知识路由阶段处理；
19. 风险与排查顺序：结果缺失先查`tenant/CurrentUser → owner/ACL → Document/File软删除 → active Version/Index → Embedding身份 → Dense/Lexical/Hybrid/Reranker`；Context错误查`Reranker身份/locator/token/hash → 再获权`；持久化错误查`ToolCall running/success → FOR KEY SHARE → Context/Evidence对齐 → Link唯一/复合外键 → 外层事务`；超时查Provider后端和Tool/总预算发生点；
20. 正式数据与停止点：全量后依次运行`seed_m1 → seed_m2_files → seed_m2_complex_files`。只读复核为PostgreSQL 17.11、pgvector 0.8.6、临时matrix tenant为0、10 files、10 documents、10 versions、9 ACL、10 parse/index pending、0 active Version、0 Chunk Set/Index Set/Chunk、0 ContextArtifact/Evidence/ToolContextLink/AgentRun/ToolCall；Storage精确10个uploads、0 parsed/chunks/other，德国仓可售库存125。M2-19整体已完成，明确没有开始M2-20、API、Agent、Qwen或前端，下一步必须等待用户单独确认。
