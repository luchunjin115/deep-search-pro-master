# M2-21｜工程化多 Agent 正式方案与实施记录

> 文档性质：根据 2026-09-02 至 2026-09-03 讨论整理并由用户确认的正式实施方案。
>
> 当前状态：待开始。
>
> 用户确认：2026-09-03，用户回复“按照你的这个思路来”，确认本方案方向和全部推荐决策。
>
> 顺序调整确认：2026-09-03，用户回复“可以，采用调整后的顺序”，确认使用 Walking Skeleton：先验证最小闭环和第一条真实 Worker 链，再固化持久化、接入真实模型并完成整链加固。
>
> 授权边界：方案确认不等于代码开发授权；当前未授权编写 M2-21 应用代码、测试、迁移、配置、API 或前端。用户单独确认开始 M2-21.1 后才能实施；M2-21.2 及以后仍需逐步确认。
>
> 唯一记录：本文件已经合并 M2-21 的需求讨论、旧版单 Agent 候选稿和正式多 Agent 实施方案，是 M2-21 唯一有效的方案与过程记录。后续 M2-21.1 至 M2-21.12 的授权、RED/GREEN、验证、风险和结论统一追加到本文件，不再创建平行的 M2-21 方案或步骤日志。

## 1. 大白话定位

M1、M2、M3 和 M4 逐步给系统增加库存、知识、文件、图片、互联网研究、数据分析和报告等专业能力。M2-21 不负责一次性实现所有这些能力，而是建设一套以后增加能力时不需要推翻重写的“团队工作制度”：

```text
用户只说自然语言目标
→ 系统判断可以直接回答、交给一个专业 Agent，还是需要多个 Agent 协作
→ Planner 把复杂目标整理为有依赖关系的任务
→ Capability Resolver 寻找当前真实存在、当前用户可用的 Agent、Skill 或 Tool
→ Supervisor 有界地委派任务
→ Worker 使用自己的少量能力完成专业子任务
→ Harness 在每一层执行权限、预算、超时、重复、审计和 Evidence 规则
→ Supervisor 根据 Observation 决定继续、重规划、追问、部分完成或结束
→ 最终回答只使用当前仍然获权的 Evidence
```

M2-21 是多 Agent 运行底座和第一条真实协作闭环，不是“把最终所有 Worker 和通用执行环境都塞进同一步”。

## 2. 本轮形成的设计原则

### 2.1 从固定意图路由升级为能力驱动

不再采用：

```text
用户句子 → inventory_query / knowledge_query → 固定 if/else → 固定 Graph
```

改为：

```text
用户目标
→ 信息需求和子任务
→ 能力发现
→ 结构化行动
→ 执行与 Observation
→ 有限重规划
```

程序不穷举所有自然语言表达，模型也不能凭空执行未登记能力。

### 2.2 工程化多 Agent 不等于每次都启动全部 Agent

系统按任务复杂度自适应执行：

| 等级 | 典型请求 | 推荐执行方式 |
|---|---|---|
| L0 | 通用概念解释、改写、总结用户提供内容 | 直接回答，零 Tool |
| L1 | 单一库存、规格或知识查询 | 单个专业 Worker 快速完成 |
| L2 | 库存＋规格＋政策等复合问题 | Supervisor 协调两个或多个 Worker |
| L3 | 选品、市场研究、经营报告 | 后续里程碑中的长任务、多 Worker、Skill 和后台恢复 |

不为简单问题支付不必要的多 Agent 成本，也不强迫用户把正常复合问题拆成多条消息。

### 2.3 专业 Agent 是配置化角色，不复制多套运行时

所有专业 Agent 复用同一套 Agent Runtime、Harness、记忆、预算、Trace、Checkpoint 和 Evidence 协议。不同 Worker 主要通过 Agent 名称/版本、职责、可申请能力、输入输出、完成条件、默认模型/预算、委派权限和 Evidence 要求形成差异。

不能为每个 Worker 复制一套互不兼容的循环、权限和日志代码。

### 2.4 能力设计不以枚举场景为中心

能力应该同时包含：

- 取得权威业务事实的专业入口；
- 能被多个任务组合的信息获取能力；
- 在受控环境中处理数据和产物的通用执行能力；
- 追问、暂停、委派、完成等协作控制能力；
- 可复用、版本化的业务 Skill。

Code Interpreter、文件工作区、浏览器和 Handoff 是“能力原语”思路的例子，不代表本方案现在就确认这些具体 Tool 名称或要求全部在 M2-21 实现。

判断一个能力是否值得抽象时，至少检查：复用范围、可组合性、权限能否由程序约束、输出能否验证、故障影响能否控制。Tool 数量不是目标；“约 13 个 Tool”继续只是 V1 范围估计。

### 2.5 自主性与护栏分工

模型可以决定用户目标、子任务、依赖、是否需要外部能力，以及下一步应执行、委派、追问、调整还是结束。程序和 Harness 必须决定可信身份、能力是否存在、参数合同、资源 ACL、父子预算、超时、重复、委派深度、并发、Evidence、Trace 和错误脱敏。

## 3. 目标多 Agent 结构

```text
聊天 API
   ↓
Agent Gateway / RunContext
   ↓
Planner + Capability Resolver
   ↓
简单任务 ─────────────→ 单个 Worker
复杂任务 ─────────────→ Supervisor
                         ├─ Business Data Worker
                         ├─ Knowledge Worker
                         ├─ Vision Worker（M3）
                         ├─ Web Research Worker（M4）
                         ├─ Analysis Worker（M4）
                         └─ Report Worker（M4）
                              ↓
                    Harness → Tool / Skill / Service
                              ↓
                 PostgreSQL / pgvector / Storage / 外部服务
                              ↓
                  Observation + Evidence + Artifact
                              ↓
                Answer Evidence Set + Citation Validator
                              ↓
                          最终回答
```

### 3.1 Supervisor

Supervisor 负责总目标、任务 DAG、Worker 选择、依赖、子预算、进度、失败处理和最终合成。它不直接访问数据库、宿主文件系统、Storage Key 或内部 Service。

### 3.2 M2-21 首批 Worker

M2-21 实际跑通两个专业 Worker：

- `BusinessDataWorker`：直接复用 M1 的 `get_product_spec` 和 `search_inventory` Tool、Service、Repository、数据库 Evidence 与 Harness，不嵌套 M1 固定 Planner；
- `KnowledgeWorker`：使用 M2 的 `search_knowledge`、`read_uploaded_file` 和 `get_evidence_detail`，返回文档 Context/Evidence、公开文件结果和明确未知项。

M1 的原库存 Graph、Provider、API 和回归继续保留，作为已经完成的垂直切片和兼容基线。

### 3.3 后续 Worker

- M3 增加 Vision Worker 和多模态 Artifact；
- M4 增加 Web Research、Analysis、Report Worker 及对应 Skill；
- 只有专业职责、独立上下文、独立能力集合和独立完成判断都足够明确时，才新增 Worker；
- 简单确定性动作继续是 Tool 或 Service，不为了数量包装成 Agent。

## 4. Capability Catalog

M2-21 应把现有 Tool Registry 上层扩展为可替换的 Capability Catalog/Resolver。内部至少区分：

| 能力种类 | 含义 | 示例 |
|---|---|---|
| Tool | 一次受控原子动作 | 查询库存、搜索知识 |
| Skill | 可复用、版本化的业务操作手册 | 库存风险分析 |
| Agent | 能独立承担子目标的专业角色 | Knowledge Worker |
| Runtime capability | 受隔离环境支持的通用执行能力 | 后续沙箱计算或受控网页读取 |

Capability 内部元数据候选包括稳定 ID、类型/版本、安全描述、输入输出 Schema、前置条件、side effect、data scope、Evidence 能力、风险/审批级别、成本/延迟/并发/幂等特征和实现状态。

模型只看到当前任务相关的少量安全摘要，不看到角色白名单、tenant、执行对象、路径、SQL、密钥或真实预算上限。未实现能力不能伪装为已注册可执行能力。

## 5. 计划、委派和通信合同

### 5.1 Task DAG

复杂问题形成有向无环任务图，记录任务 ID、目标、依赖、所需能力、负责人、状态、预期输出、Evidence 要求和失败影响。程序拒绝重复 ID、循环依赖和越界任务数。

### 5.2 通用行动

行动候选至少包括：

```text
execute_capability
delegate_task
ask_user
finish
cannot_complete
```

`delegate_task` 是模型可提出的控制行动，但由 Agent Runtime 执行，不等同于普通业务 Tool。它只能选择 Resolver 本轮返回的 Agent，并由程序注入父 Run、可信身份和子预算。

### 5.3 Handoff

父 Agent 交给子 Agent 的结构化交接包包含子任务目标、公开上下文、允许传递的 Evidence/Artifact ID、约束、期望输出、完成条件和程序分配的预算引用。子 Agent 返回统一 Worker Result：状态、公开摘要、Observation、Evidence/Artifact ID、未知项、安全错误码和资源消耗。

子 Agent 的文字结论不能脱离 Evidence 自动变成业务事实。

### 5.4 通信模式

M2-21 第一版采用 Supervisor 中转＋数据库共享任务板，暂不引入消息队列。Worker 拥有局部工作记忆，只向共享任务板写入结构化结果，不共享完整 Prompt、原始 Tool 对象或隐藏思维过程。

## 6. 记忆设计

- **短期工作记忆**：当前目标、计划版本、任务状态、公开 Observation、Evidence/Artifact ID、信息缺口、预算计数和停止原因；
- **对话记忆**：最近有界消息＋更早安全摘要＋仍有效实体/约束，不把全部历史无限塞进模型；
- **Checkpoint**：追问或中断时提交安全状态，下一请求重新验证 tenant、user、Thread、Capability 和 Evidence 后恢复；
- **长期记忆边界**：不自动建立永久用户画像，不把每次对话或回答写入向量记忆；企业知识走文档索引，用户偏好需明确授权，Agent 经验先进入评估和受控发布。

工作状态有严格版本和大小上限，不保存完整 Chain-of-Thought，也不跨 HTTP 请求持有数据库事务。

## 7. 权限、预算、失败和并发

### 7.1 权限只会收紧

```text
当前用户权限
∩ 父 Agent 委派范围
∩ Worker 能力范围
∩ Tool/Skill 策略
∩ 当前资源 ACL
```

委派不能产生新权限。

### 7.2 树形预算与终止

根 Run 拥有总模型、Tool、Token、时间、任务数和 Evidence 上限；Supervisor 给子 Run 分配子预算，所有子消耗计入根预算。需要同时限制委派深度、Worker 数、Re-plan、同签名调用和无进展循环。预算初值必须通过 Fake 基线和显式真实 Qwen/BGE 基准后再冻结。

### 7.3 失败结果

运行状态与业务结果分开。至少能表达运行中、等待用户、完成、拒绝、超时和系统失败，以及 answered、partial、no_evidence、unsupported 等业务结果。一个 Worker 失败时，其他已经成功且仍获权的结果可以形成部分回答。

### 7.4 并发

先用顺序调度验证合同和事务边界；M2-21 后期至少验证独立只读 Worker 的有界并行。并行分支必须使用独立数据库 Session、独立子 Trace 和原子预算扣减，结果稳定合并，不得共享同一个 SQLAlchemy Session。

## 8. Evidence、Artifact 和安全回答

- Worker Observation 只包含公开安全摘要和引用，大结果存外部并由 ID 引用；
- 数据库、文档、网页、图片和分析产物保留来源类型与血缘；
- 多个 Worker 的 Evidence 在回答前重新获权、去重并映射为一次回答专属 `[E1]...[E12]`；
- 直接回答不能伪造 Evidence，业务事实必须来自对应外部能力；
- Artifact 使用公开 ID 交接，不暴露路径和 Storage Key；
- Tool、网页和文件内容都是不可信数据，不能通过 Prompt 注入改变系统、权限或委派规则；
- Trace 保存结构化行动、理由码、耗时、状态和脱敏摘要，不保存完整隐藏思维。

## 9. 跨里程碑能力分配

| 阶段 | 主要职责 | 不要求在该阶段一次做完的内容 |
|---|---|---|
| M2-21 | 多 Agent 核心合同、Catalog/Resolver、Supervisor、首批两个 Worker、Handoff、父子 Run、共享任务板、Checkpoint、树形预算、Evidence 交接、聊天 API 首条闭环 | 最终全部 Worker、任意通用执行环境 |
| M2-22 | Agent/RAG 轨迹评估集、任务完成、委派、Tool、Evidence、安全、效率和成本评估；Bad Case 闭环 | 前端体验 |
| M2-23 | 多 Agent 业务步骤、追问、部分成功、Evidence/Artifact 和调试 Trace 展示 | 新专业能力 |
| M3 | Vision Worker、多模态输入和图片 Evidence/Artifact | 深度互联网研究 |
| M4 | Web Research、Analysis、Report Worker；按真实需求评估沙箱计算、网页读取和长任务；业务 Skill | 生产级全面加固 |
| M5 | 综合评估、对抗、安全、性能、成本、作品化和发布门禁；再评估长期偏好/经验记忆 | 无治理自动学习 |

Code Interpreter、文件工作区、Browser 等当前只作为“通用能力原语”的参考方向。是否采用、具体合同和首次实现阶段，必须在对应真实需求出现时单独提交方案并确认。

## 10. 前置条件与明确不做

### 10.1 前置条件

- M1 固定库存 Graph、两个业务 Tool、Harness、数据库 Evidence、聊天 API 和回归基线保持可用；
- M2-01 至 M2-20 的文档、检索、Reranker、Context、Evidence、五 Tool 和真实权限/故障矩阵保持可用；
- M1 Registry 继续精确保留两个 Tool，M2 Registry 继续精确保留五个已实现 Tool；
- 日常验证继续使用 Mock/Fake Provider，真实 Qwen/BGE 只通过显式 Smoke 运行；
- 当前已知跨月上传 Key 测试时间依赖继续作为既有问题单独区分，不在 M2-21 越权顺手修复。

### 10.2 M2-21 明确不做

- 不一次实现 Vision、Web Research、Analysis、Report 等最终全部 Worker；
- 不提前实现尚未确认的 Code Interpreter、Browser 或任意宿主文件系统能力；
- 不允许任意 SQL、任意 HTTP、任意本地路径、无沙箱代码执行或模型直接访问 Service/Repository；
- 不实现写数据库、改价格、发邮件、发布内容等业务写 Tool 和完整审批矩阵；
- 不允许 Worker 继续递归委派，第一版只有 Supervisor 可以 Handoff；
- 不引入 Agent 间消息队列、Celery 长任务或跨服务分布式调度；
- 不建立无治理长期用户画像，不自动把聊天或模型回答写入向量记忆；
- 不修改 Reranker、Hybrid、Context Builder、解析器和索引算法；
- 不实现 M2-22 的完整语义评估平台、M2-23 前端、M3 多模态或 M4 深度研究；
- 不保存或展示完整 Chain-of-Thought；
- 不引入 MCP、MinIO、真实 Amazon SP-API 或 ERP。

## 11. M2-21 完成标准

1. 一个 Supervisor 与 Business Data、Knowledge 两个真实 Worker 使用统一 Runtime；
2. L0 直接回答、L1 单 Worker、L2 多 Worker 复合问题均可表达并验证；
3. 正常复合问题不要求用户人工拆分；
4. Planner/Resolver 不依赖库存/知识固定意图 if/else；
5. Agent、Skill、Tool 和未来 Runtime capability 能通过可替换接口发现，但未实现能力不注册；
6. Supervisor 能执行结构化 Handoff，父子 Run、任务、预算和 Trace 可关联；
7. Worker 拥有局部工作记忆，并通过共享任务板提交结构化结果；
8. 追问可以 Checkpoint，并在同一 Thread 的新请求中重新获权恢复；
9. 所有真实 Tool 继续经过 Registry、Permission、Budget、Timeout 和 Trace；
10. 数据库与文档 Evidence 能在同一回答中稳定映射和验证；
11. 顺序执行必须通过，并至少验证独立只读 Worker 的有界并行边界；
12. M1 固定库存 Graph/Provider/API 和既有数据基线不退化；
13. Mock 日常回归、真实 PostgreSQL 矩阵和显式 Qwen/BGE Smoke 有分层结果；
14. M3/M4 新增 Worker 或通用能力时不需要修改 M2-21 的核心 Handoff、Observation 和 Harness 合同。

## 12. 正式实施顺序

以下顺序采用 Walking Skeleton：先用最小合同、Mock 和 Fake Worker 跑通一条可以从输入走到结果的细骨架，再接 Harness 和第一个真实 Worker；双 Worker 协作验证后才固化数据库状态并替换为真实 Qwen。它改变的是验证先后，不减少任何企业级合同、安全、持久化、Evidence 或矩阵要求。

以下顺序已经由用户确认，但不构成代码开发授权；每一步仍必须单独得到开始确认：

1. `M2-21.1`：冻结 Agent、Task、Action、Observation、Delegation、Worker Result 和终态合同；
2. `M2-21.2`：建立 Capability Catalog/Resolver 与 Agent Definition，安全投影当前真实能力；
3. `M2-21.3`：实现 Planner、Decision、Handoff、Answer Provider 协议和确定性 Mock；
4. `M2-21.4`：搭建最小 Supervisor LangGraph，以 Fake Worker 跑通 L0/L1 的第一条无数据库闭环；
5. `M2-21.5`：建立可复用 Worker Runtime、树形预算、终止管理和 Harness 适配器；
6. `M2-21.6`：实现 Business Data Worker，复用 M1 两个 Tool，跑通第一条真实业务纵向链；
7. `M2-21.7`：实现 Knowledge Worker，复用 M2 三个 Tool，并扩展顺序双 Worker 复合任务；
8. `M2-21.8`：把已验证合同固化为父子 AgentRun、任务共享板、Checkpoint 和回答 Evidence 映射；
9. `M2-21.9`：实现严格 Qwen Provider，替换 Mock 完成真实目标理解、规划、行动选择和回答；
10. `M2-21.10`：补齐短期/对话记忆、追问恢复、有限 Re-plan、统一 Evidence 和 Citation Validator；
11. `M2-21.11`：接入现有聊天 API，覆盖直接回答、单 Worker、多 Worker、部分成功和恢复；
12. `M2-21.12`：验证独立只读 Worker 有界并行、真实权限/故障/资源矩阵并收口。

三个提前反馈点：M2-21.4 能证明控制骨架可走通，M2-21.6 能证明第一条真实 Tool 纵向链可走通，M2-21.7 能证明正常复合问题可以由两个 Worker 顺序协作；此后才承担持久化迁移和真实模型的不确定性。

### 12.1 每一步预计文件、调用链和验证重点

文件清单是编码前预期，RED 阶段可以因真实依赖小幅调整，但必须记录原因且不能越过本步边界。

| 步骤 | 预计新增/修改文件 | 本步调用链位置 | RED/GREEN验证重点 |
|---|---|---|---|
| M2-21.1 | `app/schemas/agent.py`、`app/agents/engineered_state.py`、对应 `__init__.py`、`tests/unit/test_engineered_agent_contracts.py` | API之后的Schema与Agent状态合同；不运行Provider、Graph、Tool或数据库 | 多任务依赖、循环/重复ID、互斥Action、Delegation/Result、敏感字段禁止、Evidence上限、无完整CoT字段；M1合同回归 |
| M2-21.2 | `app/capabilities/contracts.py`、`catalog.py`、`resolver.py`、`app/agents/definitions.py`、必要的Registry安全投影、`tests/unit/test_capability_resolver.py` | Agent → Capability Resolver → Agent/Skill/Tool元数据；不执行能力 | 类型/版本、角色预过滤、候选上限、稳定排序、未知/伪造能力、未实现能力拒绝、敏感元数据不泄露、M1两Tool/M2五Tool精确回归 |
| M2-21.3 | `app/llm/agent_schemas.py`、`agent_provider.py`、`agent_mock.py`、`app/llm/__init__.py`、`tests/unit/test_agent_providers.py` | Agent合同 → Mock Planner/Decision/Handoff/Answer Provider；不执行Graph、真实能力或数据库 | 严格结构、能力引用、单次唯一行动、追问/结束/无法完成、Mock确定性、Prompt注入只作数据、安全错误；M1 Provider不变 |
| M2-21.4 | `app/agents/supervisor.py`、`app/agents/graphs/engineered_multi_agent.py`、状态/导出、`tests/unit/test_multi_agent_graph.py` | Schema → 最小Supervisor LangGraph → Resolver/Mock Provider/Fake Worker → AgentResult；不落数据库或真实Tool | L0直接回答、L1一次Handoff、Observation后结束、等待用户、无能力、重复/步数终止、状态不含完整CoT；同输入确定性 |
| M2-21.5 | `app/agents/runtime/` 下Worker执行、Dispatcher、Termination等模块，`app/runtime/budget.py`、`executor.py`、`trace.py`、配置、错误和单元/集成测试 | Agent Action/Delegation → Worker Runtime → Harness → 已登记能力抽象 | 通用分派、可信CurrentUser、父子预算原子扣减、委派深度/数量、重复/无进展、超时、事务/savepoint、Trace父子关联和脱敏；M1预算保持 |
| M2-21.6 | `app/agents/workers/business_data.py`、Agent Definition、Graph适配、单元和真实PostgreSQL集成测试 | Supervisor → Business Worker → Runtime/Harness → M1 Tool → Service → Repository → PostgreSQL → DB Evidence | 规格/库存、商品歧义、角色/market/tenant、拒绝/超时、Observation、Evidence和预算；第一条真实L1纵向链，不嵌套M1 Planner |
| M2-21.7 | `app/agents/workers/knowledge.py`、Agent Definition、Supervisor/Graph顺序L2扩展、单元和真实PostgreSQL/Storage集成测试 | Supervisor → Business/Knowledge Worker顺序调度 → Harness → M1/M2 Tool → PostgreSQL/Storage →混合Observation | 知识搜索、文件读取、Evidence详情、无证据、ACL/软删除/旧active、复合任务依赖、稳定合并、一个Worker失败时部分成功；本步不并行 |
| M2-21.8 | `app/models/runtime.py`、Agent任务/Checkpoint/回答Evidence Repository与Service、`app/schemas/agent.py`、`app/schemas/evidence.py`、`migrations/versions/*_agent_runtime.py`、迁移/Service测试 | 已验证Agent状态/任务/Evidence → Model/Repository → PostgreSQL；不改变规划策略 | 父子Run、任务DAG强约束、共享任务板、版本冲突、跨tenant/user/thread恢复拒绝、敏感状态拒绝、Evidence去重/12条上限、upgrade/downgrade和Alembic单head |
| M2-21.9 | `app/llm/agent_qwen.py`、Provider、配置与 `.env.example`、Graph适配、单元测试和显式Smoke | Supervisor/Worker → Qwen API → 结构化计划/行动/Handoff/回答；真实执行仍经Runtime/Harness | HTTPS/密钥、关闭模型联网、严格输出、未知能力/多余参数拒绝、Observation不可改写、429/5xx/超时脱敏、日志无秘密；Mock回归不变、真实Smoke默认跳过 |
| M2-21.10 | Agent memory/answer evidence/citation Service与Repository、Graph集成、Schema及单元/集成测试 | Checkpoint/对话摘要/Worker Observation → 有限Re-plan → Answer Evidence Set → Answer Provider → Citation Validator | 最近消息＋安全摘要、指代恢复、澄清暂停/恢复、跨请求重获权、有限Re-plan、数据库/文档Evidence稳定映射、伪造/越界引用、撤权竞态、direct answer不伪造Evidence |
| M2-21.11 | `app/services/conversation.py`、`app/api/routers/threads.py`、依赖装配、`app/schemas/chat.py`、HTTP集成测试 | API → Schema → Agent Gateway → 单Worker/Supervisor → Harness/Tool → Evidence → Answer | 同一入口的直接回答、单Worker、复合多Worker、追问恢复、部分成功、重复提交、事务提交/回滚、公开响应脱敏和M1 API回归 |
| M2-21.12 | 并发Dispatcher必要修改、`tests/integration/test_multi_agent_matrix.py`、Qwen/BGE Smoke、资源基准脚本（仅按需）、本记录/M2入口/总看板 | 完整后端链与显式真实模型Smoke；不经过M2-23前端 | 独立只读Worker并行Session/Trace/预算隔离、三角色和ACL、Prompt注入、循环/超时、Provider/数据库/Storage/Reranker故障、Evidence、性能成本、工程门禁、Seed恢复和阶段收口 |

如果 RED 阶段证明某一步仍过大，应继续拆小，而不是为了维持编号把多个风险强行一次完成。

## 13. 每一步开发规则

每个 M2-21.x 都必须先讲清输入输出和边界，先写失败测试并记录 RED，只写最小实现，再运行 GREEN、相邻回归和按风险选择的全量门禁；区分新失败、既有跨月测试失败和环境问题，恢复测试修改的正式 Seed/Storage，记录完整证据并明确停止等待下一步授权。

## 14. 参考资料的采用与修正

本方案参考：

- `cankao.mdwendang/Agent_System_Complete_Guide.md` 的 Plan/Act/Observe/Re-plan、Orchestrator-Worker、记忆、HITL、终止和评估思想；
- `cankao.mdwendang/Function_Calling_Tool_Use_Complete_Guide.md` 的动态能力加载、多工具编排、权限和结果合同；
- `cankao.mdwendang/Advanced_Tech_Architecture_Complete_Guide.md` 的复杂度分层、混合架构和最少必要 Agent 原则；
- `cankao.mdwendang/Evaluation_System_Complete_Guide.md` 的任务完成率、步骤效率、Tool 准确率、输出质量和安全评估。

不会直接照搬以下 Demo 做法：保存完整 Chain-of-Thought、向模型返回原始异常/路径/SQL/密钥、把每次聊天自动写入长期向量记忆、让模型自行决定权限/预算、永久平铺全部 Tool、把模型自我反思当作事实验证，或使用未经本项目基准验证的经验数字作为生产标准。

## 15. 已确认的实施取舍

1. M2-21 定位为“多 Agent 核心底座＋首批两个真实 Worker”，不是最终所有能力集合；
2. 简单任务使用单 Worker，复合任务使用 Supervisor，入口仍通过统一 Planner/Resolver 而非固定业务意图路由；
3. Supervisor 不直接访问底层数据库、宿主文件或内部 Service，只通过 Worker 和受控能力取得结果；
4. 第一版只有 Supervisor 可以委派，Worker 不继续递归委派；
5. Capability Catalog 从第一版区分 Tool、Skill、Agent 和未来 Runtime capability，只登记真实已实现能力；
6. 顺序执行先落地，独立只读 Worker 的有界并行进入 M2-21 后期验收；
7. Worker 返回结构化 Observation/Evidence，由统一 Answer Provider 生成答案并通过 Citation Validator；
8. 业务事实强制来自外部能力和 Evidence，通用解释、用户提供内容和非实时推理允许直接回答；
9. PostgreSQL Checkpoint、同一 Thread 追问恢复和共享任务板进入 M2-21；
10. 继续使用现有聊天 API，前端展示留给 M2-23；
11. 长期用户偏好、经验记忆和未确认的通用执行环境不强塞进 M2-21；
12. 树形预算结构现在冻结，具体数值在 Fake 和真实 Qwen/BGE 基准后确定；
13. 十二步采用 Walking Skeleton 顺序：M2-21.4 先得到 Mock/Fake 最小闭环，M2-21.6 得到第一条真实业务链，M2-21.7 得到顺序双 Worker 协作，再固化持久化和接入真实 Qwen；
14. 每一步仍需逐步授权，RED 阶段允许继续拆小但不得提前合并后续能力。

## 16. 主要风险与排查顺序

| 风险 | 可能表现 | 优先排查顺序 |
|---|---|---|
| Planner过度或错误拆分 | 简单问题产生大量任务，复合问题遗漏子目标 | 原始目标 → Task DAG → Provider结构输出 → 评估用例 |
| Resolver/Worker选择错误 | 有能力却返回unsupported，或交给错误Worker | Capability安全投影 → 角色预过滤 → 候选摘要 → Decision输出 |
| 委派循环或目标漂移 | Agent互相转交、重复任务或扩大用户目标 | 最大深度 → Task ID/签名 → 父子Run → 无进展终止 |
| 父子预算失真 | 子任务总消耗超过根预算 | 预算预留/扣减原子性 → 失败归还规则 → 并发竞态 → Trace汇总 |
| 并发事务污染 | 两个Worker共享Session、回滚互相影响 | Session工厂 → 子Run事务 → savepoint边界 → 并发故障测试 |
| Checkpoint越权或陈旧 | 其他用户恢复任务，或旧Evidence继续使用 | tenant/user/thread复合约束 → 版本冲突 → 恢复前重获权 → Evidence active/ACL |
| Evidence跨Worker错位 | `[E1]`指向错误来源或Worker文字被当成事实 | 原始Evidence ID → Answer Evidence Set → 稳定排序/去重 → Citation Validator |
| Prompt注入跨Agent传播 | 文件或Tool结果诱导委派、泄密或越权 | 不可信数据标记 → Observation白名单 → Action校验 → Harness/输出过滤 |
| Qwen＋Reranker延迟过高 | 复合问题超过同步总预算 | 单Provider/Tool耗时 → 模型轮数 → 候选裁剪 → 顺序/并行基准 → 后续异步边界 |
| M1回归 | 旧库存Graph、API、Registry或125基线变化 | 保留旧协议 → 隔离新入口 → M1测试先跑 → 新适配层定位 |
| 阶段范围膨胀 | M2-21被Code Interpreter、Browser或最终所有Worker拖住 | 对照明确不做 → Capability Gap记录 → 分配到后续里程碑 → 单独方案确认 |

## 17. 当前记录状态

本文件能够证明：用户已经确认“可分阶段扩展的工程化多 Agent 底座”方向、上述实施取舍、M2-21 与后续里程碑边界，以及先最小闭环、再真实Worker、后持久化与真实模型的十二步 Walking Skeleton 实施顺序。

本文件不能证明：M2-21.1 已获准开发、预算数值已经通过运行基准，或任何 Supervisor、Handoff、Checkpoint、Qwen、多 Agent Graph 已经实现。

当前停止在 M2-21.1 开始授权前。

后续维护规则：每个 M2-21.x 完成后，在本文件继续追加对应步骤的日期、目标、输入输出、修改文件、调用链、RED/GREEN、回归结果、能证明与不能证明、数据恢复、风险和下一动作；只有阶段状态摘要同步到 M2 入口和项目总进度看板。

## 18. 2026-09-03｜M2-21 文档归一记录

### 18.1 目标与结果

把此前分散的需求讨论、旧版单 Agent 候选稿和正式多 Agent 方案整理为一个执行入口。整理后，`M2_21_ENGINEERED_MULTI_AGENT_PLAN.md` 是唯一 M2-21 文档；后续十二个步骤的过程日志也统一写在本文件。

### 18.2 修改文件与职责

- 修改本文件：补充唯一记录和后续维护规则，保留已确认方案、十二步顺序、边界、风险与当前授权状态；
- 修改 `docs/progress/M2/M2_KNOWLEDGE_RAG.md`：过程目录和 M2-21 步骤索引只链接本文件；
- 移除 `M2_21_ENGINEERED_AGENT.md`：其中仍有效的讨论结论已经进入本文件；
- 移除 `M2_21_ENGINEERED_AGENT_IMPLEMENTATION_PLAN.md`：旧版单 Agent 和十步候选方案已经失效，不再作为开发依据；
- `docs/PROJECT_PROGRESS.md` 的阶段状态没有变化，继续保持“方案已确认、等待 M2-21.1 单独授权”。

### 18.3 调用链位置

本次只经过 `项目进度看板 → M2阶段入口 → M2-21唯一方案与过程记录` 的文档治理链。没有经过 `前端 → API → Schema → Agent/LangGraph → Harness → Tool → Service → Model → PostgreSQL/Storage` 运行链。

### 18.4 实际验证

- `M2_21*.md` 文件枚举结果为 `COUNT=1`，唯一文件为本文件；
- M2 入口及全部 `docs/` 不再存在指向两份旧文件的 Markdown 链接；旧文件名只在本节的删除记录中保留，用于说明整理范围；
- 本文件 Markdown 代码围栏数量为 `12`，偶数配对；
- 三份入口文档未发现冲突标记和行尾空白；
- 三份入口文档的相对 Markdown 链接全部存在；
- `git diff --check` 通过，仅提示 Git 将来可能执行 LF/CRLF 行尾转换，没有内容错误；
- `git status --short` 显示本轮影响范围只有 `docs/` 文档，没有应用代码、测试、迁移、配置、Seed 或 Storage 文件。

### 18.5 能证明与不能证明

以上结果能证明 M2-21 已经只有一个权威文档、入口没有继续引用旧稿、方案和逐步记录有统一落点。不能证明任何 M2-21 运行能力已经实现，也不能证明 Supervisor、Worker、Capability Resolver、Checkpoint 或真实 Qwen 调用有效；这些必须在对应 M2-21.x 中先 RED、再最小实现和 GREEN 验证。

### 18.6 数据、风险与下一动作

本次没有运行应用测试或连接 PostgreSQL/Storage，没有修改正式演示数据，因此不需要恢复 Seed。主要文档风险是后续又创建平行 M2-21 记录；排查时先看 M2 入口是否仍只指向本文件，再检查本文件的步骤日志是否连续。当前继续停止在 M2-21.1 开始授权前。

## 19. 2026-09-03｜Walking Skeleton 实施顺序确认与整理

### 19.1 目标、确认和原因

用户明确回复“可以，采用调整后的顺序”。本次不改变已确认的 Supervisor、两个首批 Worker、Capability Catalog、Handoff、Checkpoint、树形预算、Evidence 和 LangGraph 架构，只把实施方式从“先横向铺完多层基础设施、后看到闭环”调整为“先最小纵向骨架、再真实 Worker、后持久化和真实模型”。这样 M2-21.4、M2-21.6、M2-21.7 分别提前提供控制骨架、第一条真实业务链和双 Worker 协作反馈，降低未经运行验证就固化数据库与模型接口的返工风险。

### 19.2 修改文件与职责

- 修改本文件：更新顶部用户确认、正式十二步顺序、每步预计文件、调用链、RED/GREEN重点、实施取舍和当前证明范围；
- 修改 `docs/progress/M2/M2_KNOWLEDGE_RAG.md`：同步 Walking Skeleton 为当前有效实施决策和下一阶段摘要；
- 修改 `docs/PROJECT_PROGRESS.md`：在最近完成摘要中同步实施顺序已经确认调整；
- 没有修改应用代码、测试、迁移、配置、API、Seed、Storage 或数据库。

### 19.3 调用链位置

本次只经过 `项目总进度 → M2阶段入口 → M2-21唯一方案与实施记录`。没有经过 `前端 → API → Schema → Agent/LangGraph → Harness → Tool → Service → Model → PostgreSQL/Storage`。

### 19.4 实际验证

- 正式顺序中的 `M2-21.1` 至 `M2-21.12` 编号统计为 `12`；
- 文件、调用链和验证重点表中的步骤行统计为 `12`，与正式顺序一一对应；
- 定向检查确认：M2-21.4 是 Mock/Fake 最小闭环，M2-21.6 是 Business 真实纵向链，M2-21.7 是顺序双 Worker，M2-21.8 是持久化，M2-21.9 是真实 Qwen；
- 搜索旧映射 `M2-21.3=AgentRun`、`M2-21.5=Qwen`、`M2-21.9=Supervisor Graph`，结果为 `NONE`；
- Markdown 代码围栏数量为 `12` 且偶数配对；
- `git diff --check` 通过，仅有 Git 的 LF/CRLF 行尾转换提示。

### 19.5 能证明与不能证明

以上结果能证明唯一方案、M2入口和总看板已经采用同一个 Walking Skeleton 顺序，步骤编号及验证表没有错位。不能证明最小Graph、Fake Worker、真实Business/Knowledge Worker、持久化或Qwen已经实现；这些仍需在对应步骤取得单独授权后，以实际RED/GREEN和回归结果证明。

### 19.6 数据、风险与下一动作

本次没有运行应用或测试，没有连接PostgreSQL/Storage，也没有修改正式演示数据，因此无需恢复Seed。主要风险是后续开发仍按旧编号理解职责；排查时先核对本文件第12节，再核对当前步骤日志和M2入口。当前继续等待用户单独确认开始M2-21.1，不自动进入任何代码实现。
