# M2-21｜工程化 Agent 待确认实施方案

> 文档性质：根据当前讨论方向形成的候选实施方案，尚未最终确认。
>
> 当前状态：待确认。
>
> 方案日期：2026-09-02。
>
> 授权边界：生成本方案不代表授权开发。用户明确确认最终方案后，也只开始 M2-21.1；M2-21.2 及以后仍等待逐步授权。

## 1. 大白话目标

M1 的 Agent 像一条已经铺好的库存查询轨道：千问只能提议商品或库存 Tool，程序按照固定节点执行，最后由程序拼出固定答案。M2-19 和 M2-20 又准备好了知识搜索、证据详情和文件读取能力，但这些能力目前还没有进入一个能够自主决策的循环。

M2-21 要把系统升级成下面这种工作方式：

```text
用户只描述目标
    ↓
Agent 判断自己是否可以直接回答
    ↓
需要外部事实时，按需发现当前可用能力
    ↓
形成计划并执行一步或一组独立步骤
    ↓
观察结果和 Evidence
    ↓
决定继续、调整计划、追问用户、部分完成或结束
```

程序不再提前穷举所有自然语言意图和固定流程；程序负责能力目录、权限、严格合同、预算、审计、Evidence 和终止边界。模型负责理解目标、拆分任务、选择下一行动以及根据 Observation 调整计划。

## 2. 当前代码事实与缺口

### 2.1 已经具备

- `InventoryQueryAgent` 和固定五节点库存 Graph；
- `ModelProvider.propose_tool_call()`、Mock Provider 和 Qwen Provider；
- M1 两 Tool Registry 与 M2 五 Tool Registry；
- `HarnessExecutor`、`PermissionGuard`、`ExecutionBudget` 和 `TraceRecorder`；
- PostgreSQL `threads/messages/agent_runs/tool_calls/evidences`；
- `search_knowledge` 返回安全 `ContextBundle`，无证据是正常成功；
- `get_evidence_detail` 和 `read_uploaded_file` 的受控执行链；
- Document Context/Evidence 与 Citation Validator；
- 现有聊天 `POST /threads/{thread_id}/messages`。

### 2.2 当前缺少

1. Provider 只会在两个 M1 Tool 中提议一次调用，不会输出计划、追问、直接回答或结束决定；
2. 当前 Graph 只服务库存查询，节点和状态都写死；
3. M2 Registry 的五个能力没有安全投影到新 Agent；
4. 当前预算默认 `2` 次模型、`2` 次 Tool、`8` 秒，无法承载多意图和多轮观察；
5. 当前 `AgentRun` 没有等待用户、工作记忆或可恢复 Checkpoint；
6. 当前聊天 API 每条消息固定创建 `InventoryQueryAgent`；
7. 当前库存回答由代码静态拼接，知识/混合回答没有统一 Answer Provider；
8. 文档 Context 内部有 `[E#]`，数据库 Evidence 没有统一的“本次最终答案引用映射”；
9. 当前 Citation Validator 只验证单个文档 Context，不能直接验证数据库与多个文档 Context 的混合答案；
10. 当前没有部分成功、缺信息追问、无能力和直接回答的统一结果合同。

## 3. 本阶段目标

M2-21 完成后，系统应能在同一个受控 Agent 中：

- 理解一段自然语言中的一个或多个子目标；
- 判断问题能否由 LLM 直接回答；
- 在需要业务事实时按需发现最多五个当前获权能力；
- 生成结构化计划，并根据 Tool Observation 有限调整；
- 顺序完成存在依赖的多个 Tool 调用，不要求用户拆分正常复合问题；
- 对缺少必要信息的问题主动追问，并在后续消息中安全恢复；
- 对不存在的能力、无权限、无证据和部分失败给出不同结果；
- 使用现有五个 M2 Tool，所有执行继续经过 Harness；
- 把数据库和文档 Evidence 组织成一次回答专属的有序引用集合；
- 由 Mock/Qwen 生成直接回答或基于 Evidence 的回答；
- 在返回前验证引用和当前权限；
- 通过现有聊天 API 返回统一回答、执行摘要和 Evidence 卡片；
- 保留 M1 Graph、M1 Registry 和既有回归，不用新架构掩盖旧行为退化。

## 4. 明确不做

M2-21 不实现：

- 多 Agent、Supervisor、Worker 或 Agent 间消息队列；
- Tavily 互联网搜索和 M4 深度研究；
- M3 多模态 Agent；
- 写数据库、改价格、发邮件、发布内容等有副作用的业务 Tool；
- 写操作审批和完整 HITL 风险矩阵；本步只有“缺信息追问”；
- 长期用户画像、跨项目经验记忆或自动把对话写入向量记忆；
- 面向一万个 Tool 的向量化能力索引生产实现；本步只冻结可替换接口并服务当前五个 Tool；
- 前端交互和引用卡片 UI，留给 M2-23；
- M2-22 的正式 RAG Eval Dataset/Runner；
- Reranker、Hybrid、Context Builder、文档解析或索引算法调整；
- 让模型访问 tenant、用户、角色、SQL、路径、Storage Key、预算或数据库连接；
- 保存或展示模型完整隐藏思维过程；
- MCP、MinIO、Celery、真实 Amazon SP-API 或 ERP。

## 5. 推荐冻结的实施决策

以下是本方案的推荐决策，只有用户确认最终方案后才转为正式合同。

### 5.1 使用一个工程化业务 Agent

M2-21 使用一个主 Agent 和一个显式 LangGraph，不引入多 Agent。当前五个能力、上下文和任务复杂度仍适合单 Agent；多 Agent 会增加上下文传递、成本、冲突和调试难度。

### 5.2 使用 Plan → Act → Observe → Re-plan 循环

- 简单问题也生成一个最小单任务计划，复杂问题生成多任务计划；
- 每次执行后把结构化 Observation 写入工作状态；
- 原计划仍适用就继续，不适用才触发有限 Re-plan；
- Re-plan 不是相同输入的盲目重试；
- 模型可以判断完成，但程序还要检查预算、任务状态、Evidence 和输出合同。

### 5.3 不再用固定业务意图连线

模型不输出“库存路线/知识路线”后让程序写死跳转。模型输出目标、任务和下一行动；Capability Resolver 从 Registry 提供当前相关、获权、公开安全的能力候选，LangGraph 根据行动类型进入通用节点。

### 5.4 当前五个能力采用可替换 Resolver

- 新增 `CapabilityResolver` 协议；
- 当前实现从 M2 Registry 读取元数据，并按当前角色预过滤；
- 当前只有五个 Tool，允许返回全部或按信息需求返回最多五个安全摘要；
- 不把 `allowed_roles`、tenant、timeout、执行对象或内部依赖暴露给模型；
- 未来能力变多时，可把实现替换为分层/关键词/语义检索，而不改 Agent Graph 和 Provider 合同；
- 市场、ACL 和具体参数权限仍在 Harness 执行时校验，发现阶段不能冒充最终授权。

### 5.5 新 Agent 直接复用 M1 Tool，不嵌套 M1 Planner

推荐保留 M1 Graph 和测试，但新 Agent 直接通过 Harness 使用 `get_product_spec` 和 `search_inventory`。如果把整个 M1 Agent 当子图调用，会出现“外层 Planner 调内层 Planner”、重复模型调用、预算重复和 Evidence/Trace 归属模糊。

复用关系是：

```text
保留：M1 Tool + Service + Repository + Evidence + Harness + 回归
不嵌套：M1 固定提议循环和静态 compose_answer
```

### 5.6 Provider 职责拆分，M1 合同不破坏

保留现有 `ModelProvider.propose_tool_call()` 供 M1 回归。新增独立协议：

- `AgentPlannerProvider`：生成/更新结构化任务计划；
- `AgentDecisionProvider`：结合计划、Observation、候选能力和剩余预算提出下一行动；
- `AgentAnswerProvider`：根据用户输入、公开 Observation 和回答 Evidence 集合生成最终答案。

Mock 实现用于日常确定性回归；Qwen 实现使用严格结构化输出或受控函数调用，真实调用默认显式 Smoke。

### 5.7 模型输出行动，不输出内部执行权

候选行动采用严格判别联合：

```text
execute_capability
ask_user
finish
cannot_complete
```

- `execute_capability` 只能引用 Resolver 当前返回的能力；
- Tool 参数必须再次通过对应 Pydantic Input Schema；
- `ask_user` 只能返回有界、面向用户的澄清问题；
- `finish` 只表示模型认为可以结束，程序仍执行完成条件和引用校验；
- `cannot_complete` 必须使用公开原因码，不能泄露内部错误；
- 计划和行动只记录结构化理由码/信息缺口，不保存完整 Chain-of-Thought。

### 5.8 支持多意图，但第一版按依赖顺序安全执行

- 一条消息允许多个子任务；
- 有依赖的任务必须顺序执行；
- 独立任务可以在计划中标为可并行；
- M2-21 第一版执行器先顺序运行，避免并发共享 SQLAlchemy Session 和事务污染；
- 顺序执行不影响复合问题能力，只影响延迟；
- 行动合同为以后增加有界并发保留空间，M2-21 不宣称已验证并行执行。

### 5.9 建立当前任务工作记忆与 PostgreSQL Checkpoint

工作记忆保存：目标、计划版本、任务状态、公开 Observation 摘要、Evidence ID、信息缺口、预算计数和停止原因。它不保存密钥、SQL、路径、完整原始 Tool 结果或隐藏思维。

当 Agent 需要追问时：

```text
当前 HTTP 请求结束并提交安全 Checkpoint
→ 返回 clarification_required
→ 用户在同一 Thread 回复
→ 新请求重新获权并加载可恢复状态
→ 继续规划和执行
```

不跨 HTTP 请求持有数据库事务。恢复前必须重新验证 tenant、user、Thread 所有权、能力权限和 Evidence 当前可见性。

### 5.10 区分运行状态与业务完成结果

推荐运行状态：

```text
running / waiting_for_user / completed / failed / denied / timed_out
```

推荐完成结果：

```text
answered / partial / no_evidence / unsupported
```

“无证据”和“当前无能力”可以是安全完成结果，不等于服务器故障；权限拒绝、预算耗尽、Provider/数据库故障仍是对应失败状态。

### 5.11 建立回答专属 Evidence Set

一个混合问题可能同时得到数据库 Evidence 和一个或多个文档 Context；它们原有的本地 `[E#]` 可能冲突。推荐新增一次回答专属的 Evidence Set：

```text
多个 Tool Observation
→ 收集当前答案允许使用的 Evidence
→ 重新获权并去重
→ 按稳定顺序分配 [E1]...[E12]
→ 把安全摘要交给 Answer Provider
→ 最终按 Evidence Set 校验引用
```

数据库和文档 Evidence 共用这一最终映射。原始 Context 不被篡改；Evidence Set 只建立本次回答的本地引用标签。

`read_uploaded_file` 本身不产生 Evidence，因此它的正文不能直接支持最终业务事实；Agent 若要据此形成可引用结论，必须取得对应 Evidence 或明确不把内容作为已验证事实输出。

### 5.12 直接回答实行来源边界

允许不调用 Tool 的候选范围：

- 通用概念解释；
- 改写、翻译或总结用户当前提供的内容；
- 仅基于用户显式输入完成的推理；
- 不依赖当前租户、实时状态或企业知识的回答。

强制使用外部能力的范围：

- 库存、产品目录等当前数据库事实；
- 企业政策、说明书和上传文档事实；
- 当前权限、文件状态、Evidence 详情；
- 任何被描述为“最新、当前、公司内部”的事实。

程序可以校验来源声明、Evidence 和工具轨迹，但无法仅靠 Schema 百分之百证明模型没有语义误判；这部分必须通过 M2-21轨迹测试和 M2-22评估持续验证。

### 5.13 独立 Agent 预算，不粗暴扩大 M1 全局预算

保留 M1 当前 `2模型/2Tool/8秒` 回归。为新 Agent 增加独立配置，推荐初始硬上限：

| 项目 | 推荐初值 | 含义 |
|---|---:|---|
| 计划任务数 | 8 | 防止一次拆出大量子任务 |
| Agent循环步数 | 12 | 包括计划、行动、观察和结束检查 |
| 模型调用 | 8 | 覆盖计划、数次决策、有限重规划和回答 |
| Tool调用 | 5 | 当前单Agent最多暴露五个Tool |
| 同Tool同参数 | 1 | 继续防止原样重复循环 |
| Re-plan | 2 | 失败或新信息下有限调整 |
| 回答Evidence | 12 | 与现有Context/ToolEnvelope硬上限一致 |
| 总运行时间 | 45秒 | 给真实Reranker与Qwen留出组合空间，后续按基准收紧 |

这些是兜底上限，不代表每次必须用满；最终数值必须经 Fake 基线和真实 Qwen/BGE 显式 Smoke 后确认。

### 5.14 继续使用同一个聊天入口

推荐扩展现有：

```text
POST /threads/{thread_id}/messages
```

不新增第二套知识聊天 API。响应扩展为统一 Agent 结果，包括回答、完成类型、追问状态、使用能力、Trace、预算摘要和数据库/文档 Evidence Summary。前端展示仍留给 M2-23。

## 6. 目标调用链

```text
前端（M2-23才改）
→ POST /threads/{thread_id}/messages
→ Chat Schema + CurrentUser
→ Conversation Service读取有界Thread上下文/待恢复Checkpoint
→ EngineeredAgent LangGraph
→ Planner Provider（Mock/Qwen）
→ Capability Resolver → M2 Registry安全投影
→ Decision Provider提出下一行动
→ Action Validator
→ Harness权限/预算/超时/Trace
→ 五个现有Tool之一
→ Service → Model/Storage/PostgreSQL
→ 公开ToolEnvelope作为Observation
→ 工作记忆/Checkpoint
→ 继续决策或结束
→ Answer Evidence Set Builder重新获权/去重/编号
→ Answer Provider（Mock/Qwen）
→ Citation Validator
→ Conversation Service保存assistant消息
→ API返回回答、执行摘要和Evidence
```

直接回答的短链：

```text
API → Agent → Planner/Decision → Answer Provider → 输出合同 → API
```

它不经过 Tool、RAG、Storage 或业务数据库查询，但仍经过身份、Trace、预算和聊天事务。

## 7. 数据与状态候选设计

### 7.1 严格公开/内部合同

候选新增：

- `AgentRequest`：当前用户消息和可信Thread上下文引用；
- `AgentTaskPlan`：目标、最多8个任务、依赖和完成标准；
- `AgentAction`：执行能力、追问、结束或无法完成；
- `AgentObservation`：ToolEnvelope的安全摘要、Evidence ID和公开错误；
- `AgentWorkingState`：LangGraph内部工作状态；
- `AgentResult`：运行状态、完成类型、回答、能力、Evidence、Trace和节点历史；
- `AnswerEvidenceSet`：一次答案的有序`[E#] → Evidence ID`映射；
- `AgentCheckpointPayload`：版本化、可持久化的安全工作状态。

全部Pydantic模型继续 `extra="forbid"`，字符串、数组、任务数、依赖数、文本和Evidence均有硬上限。

### 7.2 PostgreSQL候选变化

推荐新增迁移：

- `agent_checkpoints`：租户、用户、Thread、来源Run、状态版本、修订号、安全状态JSON、创建/更新时间；
- `answer_evidence_sets`：本次回答Evidence集合及所属AgentRun；
- `answer_evidence_links`：集合内的citation label、Evidence ID和稳定顺序；
- `agent_runs.status`允许`waiting_for_user`；
- 根据最终恢复方式评估是否增加`resumed_from_run_id`；
- 复合外键、唯一约束和tenant一致性继续在数据库层验真。

不修改原 Evidence 的事实归属，不把Document Evidence重新绑定为单一ToolCall，也不把Checkpoint存入Message正文。

## 8. 分步实施计划

每一步都必须先写失败测试、实际运行记录 RED、只写最小实现、运行 GREEN 和相邻回归，并在本文件追加实施日志。确认整个方案只授权开始 M2-21.1。

### M2-21.1｜冻结工程化 Agent 核心合同

目标：只定义计划、任务、行动、Observation、结果和内部状态能表达什么，不实现Provider、Graph或Tool调用。

预计新增/修改：

- `app/schemas/agent.py`；
- `app/agents/engineered_state.py`；
- `app/schemas/__init__.py`、`app/agents/__init__.py`；
- `tests/unit/test_engineered_agent_contracts.py`。

RED重点：

- 多任务依赖、循环依赖、重复ID和越界任务数；
- 判别行动必须互斥；
- 计划/行动禁止tenant、user、role、SQL、路径、预算和内部ID逃生字段；
- direct、tool、ask、finish、unsupported、partial状态不矛盾；
- 不允许持久化完整CoT字段；
- Evidence最多12条且去重。

调用链位置：`API之后的Schema/Agent状态合同`；不经过Provider、LangGraph执行、Harness、Tool、Service或PostgreSQL。

完成标准：合同能够表达讨论中的全部行为，且不改变M1合同语义。

### M2-21.2｜建立可扩展能力目录与发现接口

目标：从M2 Registry安全发现当前角色可见的最多五个候选能力，不用业务`if/else`把自然语言硬连到Tool。

预计新增/修改：

- `app/capabilities/__init__.py`；
- `app/capabilities/contracts.py`；
- `app/capabilities/catalog.py`；
- `app/capabilities/resolver.py`；
- `app/tools/registry.py`（仅增加安全投影接口，M1/M2精确名称不变）；
- `tests/unit/test_capability_resolver.py`；
- `tests/unit/test_permissions.py`、`test_agent_tool_contracts.py`回归。

RED重点：角色预过滤、稳定排序、候选上限、未知能力、伪造Registry、敏感元数据不泄露、M1仍精确两Tool、M2仍精确五Tool。

调用链位置：`Agent → Capability Resolver → Registry元数据`；不执行Tool。

完成标准：Agent只看到安全能力摘要，未来替换检索实现不需要修改Graph合同。

### M2-21.3｜增加工作记忆、Checkpoint与混合回答Evidence映射

目标：让任务能够暂停/恢复，并为数据库与文档Evidence建立一次回答专属的统一引用集合。

预计新增/修改：

- `app/models/runtime.py`；
- `app/repositories/agent_checkpoints.py`；
- `app/repositories/answer_evidence.py`；
- `app/services/agent_memory.py`；
- `app/services/answer_evidence.py`；
- `app/schemas/agent.py`、`app/schemas/evidence.py`；
- `migrations/versions/20260902_0011_agent_checkpoints_answer_evidence.py`；
- `tests/integration/test_m2_21_migration.py`；
- `tests/unit/test_agent_memory.py`；
- `tests/integration/test_answer_evidence_service.py`。

RED重点：跨tenant/跨user/跨Thread恢复拒绝、修订冲突、状态JSON严格版本、敏感字段拒绝、数据库/文档Evidence去重和稳定编号、超过12条拒绝、撤权后不可构建或验证、迁移upgrade/downgrade和Alembic单head。

调用链位置：`Agent工作状态/Evidence Service → Model → PostgreSQL`；不接Provider或Graph循环。

完成标准：Checkpoint和Evidence Set具备数据库强约束、重获权和安全恢复能力。

### M2-21.4｜实现Planner、Decision与Answer Provider合同及Mock

目标：让日常测试免费、确定性地覆盖直接回答、单Tool、多Tool、追问、调整和结束。

预计新增/修改：

- `app/llm/agent_schemas.py`；
- `app/llm/agent_provider.py`；
- `app/llm/agent_mock.py`；
- `app/llm/__init__.py`；
- `tests/unit/test_agent_providers.py`。

RED重点：计划严格解析、行动只引用候选能力、Tool参数二次校验、无Evidence业务答案拒绝、Prompt注入文本只当数据、空/多行动/未知行动拒绝、超时与错误脱敏、Mock重复输入稳定。

调用链位置：`Agent合同 → Mock Provider`；不执行真实Qwen、Harness或Tool。

完成标准：Mock可覆盖全部控制分支，M1 `ModelProvider`和既有Provider测试不变。

### M2-21.5｜实现Qwen工程化Agent Provider

目标：使用Qwen完成严格计划、下一行动和最终回答，模型只看到公开上下文、候选能力和Evidence映射。

预计新增/修改：

- `app/llm/agent_qwen.py`；
- `app/llm/agent_provider.py`；
- `app/core/config.py`、`.env.example`；
- `tests/unit/test_agent_qwen_provider.py`；
- `tests/smoke/test_qwen_engineered_agent_smoke.py`。

RED重点：HTTPS与密钥、关闭模型互联网搜索、严格结构、未知能力/额外参数/多余行动拒绝、不得改写可信Observation、文档注入隔离、无密钥/HTTP/429/5xx/超时安全映射、请求日志不含秘密。

调用链位置：`Agent → Qwen API → 严格计划/行动/答案`；单元测试用MockTransport，真实Smoke默认跳过。

完成标准：Qwen只提出计划/行动/回答，不直接执行Tool或访问数据库。

### M2-21.6｜建立五Tool通用受控执行适配器与Agent预算

目标：把模型提出的合法能力行动统一落到现有五个Tool和Harness，不写五条业务路线。

预计新增/修改：

- `app/agents/runtime.py`；
- `app/runtime/budget.py`；
- `app/runtime/executor.py`；
- `app/runtime/trace.py`；
- `app/core/config.py`、`.env.example`；
- `app/core/errors.py`；
- `tests/unit/test_agent_runtime.py`；
- `tests/unit/test_budget.py`；
- `tests/integration/test_agent_capability_runtime.py`。

RED重点：五Tool正确分派、未知/未发现/未授权能力拒绝、可信CurrentUser绑定、参数类型与结果类型核对、同签名重复、动态Agent预算、M1预算不变、Tool超时、Trace顺序和脱敏、失败事务/savepoint边界。

调用链位置：`Agent Action → Harness → Tool → 既有Service`。

完成标准：所有真实执行继续经过Registry、Permission、Budget和Trace，没有模型直连Service/Repository。

### M2-21.7｜实现LangGraph计划—行动—观察—重规划循环

目标：完成工程化Agent核心循环，支持单任务、多任务、直接回答、追问、无能力、部分成功和安全终止。

预计新增/修改：

- `app/agents/graphs/engineered_agent.py`；
- `app/agents/engineered_state.py`；
- `app/agents/__init__.py`、`app/agents/graphs/__init__.py`；
- `tests/unit/test_engineered_agent_graph.py`。

候选节点：

```text
load_or_initialize
→ plan
→ discover_capabilities
→ decide_next_action
→ validate_action
→ execute_action / ask_user / prepare_finish / cannot_complete
→ observe
→ evaluate_progress
→ replan或继续
→ compose_terminal_result
```

RED重点：复合问题不被迫拆分、依赖顺序、一次Observation后继续、有限Re-plan、部分成功、等待用户、无能力、安全错误、节点/步数/模型/Tool/时间终止、没有完整CoT进入状态。

调用链位置：`Schema → LangGraph → Provider/Resolver/Runtime抽象`；单元阶段使用Fake Runtime，不落真实数据库。

完成标准：同一Graph能自主选择直接回答、Tool、追问和结束，流程不依赖固定库存/知识route。

### M2-21.8｜接入回答合成、统一Evidence和Citation Validator

目标：让最终业务回答只能使用当前允许的Evidence，并支持数据库＋文档混合引用。

预计新增/修改：

- `app/services/answer_evidence.py`；
- `app/services/citations.py`；
- `app/repositories/evidence.py`、`answer_evidence.py`；
- `app/agents/graphs/engineered_agent.py`；
- `app/schemas/evidence.py`、`agent.py`；
- `tests/unit/test_agent_answer_composition.py`；
- `tests/integration/test_agent_citation_validation.py`。

RED重点：数据库与文档Evidence稳定编号、多个Context标签冲突重映射、缺引用/重复/伪造/越界引用拒绝、撤权竞态、无证据正常回答、direct answer不伪造Evidence、`read_uploaded_file`不能冒充Evidence、Prompt注入不改变回答规则。

调用链位置：`Observation → Answer Evidence Set → Answer Provider → Citation Validator → AgentResult`。

完成标准：业务事实有合法引用，直接回答与无证据回答遵循各自合同。

### M2-21.9｜实现追问恢复、对话上下文与聊天API统一接入

目标：让自然语言聊天真正进入新Agent，并支持在同一Thread回复澄清问题后安全继续。

预计新增/修改：

- `app/services/conversation.py`；
- `app/api/routers/threads.py`；
- `app/api/dependencies.py`（仅按需装配新Agent依赖）；
- `app/schemas/chat.py`；
- `app/agents/graphs/engineered_agent.py`；
- `tests/integration/test_engineered_agent_api.py`；
- `tests/unit/test_schemas.py`。

RED重点：直接回答零Tool、库存单意图、知识单意图、库存＋知识复合问题、澄清与恢复、跨Thread/tenant恢复拒绝、部分成功、统一数据库/文档Evidence摘要、事务提交/回滚、重复提交、现有M1 API安全回归。

调用链位置：完整后端链：`API → Schema → Agent/LangGraph → Harness/Tool → Service/Model/PostgreSQL → Evidence → Answer`。

完成标准：现有聊天入口能够返回新Agent结果；本步仍不修改前端。

### M2-21.10｜真实矩阵、资源基线与阶段收口

目标：证明新Agent不是只在Mock happy path中工作，并明确真实模型、权限、预算和故障边界。

预计新增/修改：

- `tests/integration/test_engineered_agent_matrix.py`；
- `tests/smoke/test_qwen_engineered_agent_smoke.py`；
- 仅在需要时增加 `scripts/` 下显式Smoke/基准入口；
- 本记录、M2入口和总进度看板。

验证矩阵至少包括：

- 直接回答、单Tool、复合多Tool、依赖执行、追问恢复和部分成功；
- 三个业务角色、tenant、market、owner/ACL、撤权、软删除和旧active；
- Prompt注入、未知能力、恶意参数、重复调用、循环、模型/Tool/总超时；
- Provider、数据库、Storage、Reranker和Evidence持久化故障；
- 引用合法、无证据、混合Evidence、撤权后验引失败；
- M1库存Graph/Provider/API全回归；
- Fake BGE/Reranker日常全量；真实BGE/Qwen显式Smoke；
- Ruff、format、Mypy、compile、依赖、Alembic和全量pytest；
- 如果全量仍只有既有跨月上传Key测试失败，明确区分既有问题，不越权修复；
- 如果测试修改正式演示数据，按既有Seed入口恢复并只读复核。

调用链位置：完整后端链和真实外部模型Smoke；不经过前端浏览器。

完成标准：M2-21全部步骤有RED/GREEN记录、完整矩阵和可重复基线，正式Seed恢复，文档收口，并明确停止等待M2-22确认。

## 9. 每一步统一开发顺序

每个M2-21.x都必须：

1. 用大白话说明本步缺少什么；
2. 说明输入、输出、上游、下游和明确不做内容；
3. 先写失败测试；
4. 实际运行并记录RED失败位置和原因；
5. 只实现让本步通过的最小代码；
6. 运行本步GREEN与相邻回归；
7. 按风险运行质量门禁和全量测试；
8. 区分新失败、既有跨月失败和环境问题；
9. 恢复被测试修改的Seed/Storage并只读核对；
10. 在本文件追加实际日期、文件、调用链、命令、结果、能证明/不能证明、风险和下一动作；
11. 只在状态变化时同步M2入口和总看板；
12. 明确停止，等待下一小步授权。

## 10. 验证分层

### 10.1 合同层

证明严格Schema、判别行动、计划依赖、Evidence上限和禁止字段；不能证明模型语义判断正确。

### 10.2 Provider层

证明Mock确定性、Qwen请求安全、输出可解析和错误脱敏；不能证明Tool、ACL或数据库链正确。

### 10.3 Graph层

证明节点、循环、分支、Re-plan和停止条件；Fake Runtime不能证明真实Harness和事务。

### 10.4 Runtime/Tool层

证明能力行动经Harness落到五Tool、权限、预算、超时和Trace有效；不能单独证明最终答案忠实。

### 10.5 Evidence/Answer层

证明允许列表、引用映射、当前ACL重新验证和格式合法；Citation Validator只能证明引用存在且获权，语义蕴含质量仍需M2-22评估。

### 10.6 HTTP整链

证明身份、Thread、消息、Checkpoint、事务、Agent、Tool和响应合同连接；不能证明前端体验，前端属于M2-23。

### 10.7 真实模型Smoke

证明当前配置和一次受控样例可以调用真实Qwen/BGE；不能证明长期可用性、生产并发、成本或所有自然语言变体。

## 11. 阶段完成标准

M2-21只有同时满足以下条件才能标记为已完成：

1. M2-21.1至M2-21.10均得到逐步授权并有实际RED/GREEN记录；
2. 同一Agent支持直接回答、能力调用、追问、继续、部分完成和无法完成；
3. 支持库存＋知识等正常复合问题，不要求用户人工拆分；
4. Provider不是固定业务if/else路由，能力来自可替换Resolver与Registry；
5. 所有真实Tool调用仍经过Harness、权限、预算、超时和Trace；
6. 工作状态可安全暂停/恢复，不跨请求持有事务；
7. 数据库与文档Evidence能在同一答案中稳定编号和重新获权；
8. 业务事实引用通过Validator，无证据时不编造；
9. M1两Tool Registry、固定库存Graph和既有125基线不退化；
10. Mock日常回归、真实PostgreSQL矩阵、显式Qwen/BGESmoke和工程门禁有实际结果；
11. 正式Seed和Storage恢复到既有基线；
12. M2入口、总看板和本记录同步，明确没有开始M2-22。

## 12. 主要风险与排查顺序

| 风险 | 可能表现 | 优先排查 |
|---|---|---|
| 模型错误判断可直接回答 | 用模型记忆回答库存/政策 | 任务来源声明 → Provider Prompt/Schema → 轨迹用例 → M2-22评估 |
| 能力发现漏召回 | 明明有Tool却说不支持 | Registry投影 → 角色预过滤 → Resolver候选 → 模型行动 |
| 计划过度拆分 | Tool/模型调用暴涨 | 计划合同 → 任务去重 → 最大任务/步数 → Re-plan原因 |
| 计划循环 | 重复调用或不结束 | 依赖DAG → Tool签名 → 节点历史 → 终止管理器 |
| Checkpoint越权 | 其他用户恢复任务 | tenant/user/thread复合约束 → Repository查询 → 恢复前重新授权 |
| 混合Evidence标签错位 | `[E1]`指向错误来源 | Evidence Set稳定排序 → 唯一约束 → Answer输入快照 → Validator |
| 部分失败事务污染 | 一个Tool失败丢失全部成功结果 | 每行动事务/savepoint → Error分类 → partial提交规则 → Trace |
| CPU Reranker加Qwen超时 | 复杂问题超过同步预算 | Tool耗时 → 模型轮数 → 总预算 → 候选裁剪/异步化后续决策 |
| Prompt注入 | 文档内容改变计划或要求泄密 | 不可信数据边界 → Prompt分区 → Action校验 → 权限/Harness |
| M1回归 | 既有库存API或Provider变化 | 保留旧协议/Registry → 旧测试先跑 → 新适配层隔离 |
| Trace泄密 | 状态或错误含SQL/路径/密钥 | 持久化Schema → summarize/redact → 故障注入测试 |
| 方案范围过大 | 单步不可理解、难回退 | 严格十步拆分 → 每步只做一个能力 → 未授权不提前实现 |

## 13. 本方案仍需用户重点确认的取舍

在正式确认前，建议重点复核：

1. 是否接受新Agent直接复用两个M1 Tool，而不是嵌套整个M1库存Agent；
2. 是否接受M2-21第一版支持多意图但顺序执行，暂不宣称并行；
3. 是否接受PostgreSQL Checkpoint与`waiting_for_user`进入M2-21；
4. 是否接受新增回答专属Evidence Set来统一数据库/文档引用；
5. 是否接受直接回答只覆盖通用知识、用户提供内容和非实时推理；
6. 是否接受独立Agent预算推荐初值，并在真实基准后收紧；
7. 是否接受同一个聊天API接入新Agent，前端仍留给M2-23；
8. 是否接受当前只实现可替换Capability Resolver，不提前建设一万个Tool的向量目录；
9. 是否接受M2-21拆为十个逐步授权的小步骤；
10. 是否有应移出M2-21、留给M2-22/M2-23/M4的能力。

## 14. 当前记录状态

本文件目前只能证明：实施方向已经被整理为可逐步讨论的候选方案，并且与当前真实代码缺口对应。

它不能证明：

- 用户已经确认全部推荐决策；
- M2-21.1已经获准开始；
- 文件清单不会在RED阶段因真实依赖发生小幅调整；
- Qwen、LangGraph循环、Checkpoint、混合Evidence或HTTP链已经实现；
- 推荐预算已经通过真实资源基准。

当前明确停止在方案确认前，不修改任何M2-21应用代码、测试、迁移、配置、Seed、Storage或数据库。
