# M2-21｜工程化多 Agent 正式方案与实施记录

> 文档性质：根据 2026-09-02 至 2026-09-03 讨论整理并由用户确认的正式实施方案。
>
> 当前状态：已完成。2026-09-07 已完成并验证 M2-21.12，M2-21 十二步全部收口；当前停止等待用户确认理解，后续 M2-22 必须单独授权。
>
> 用户确认：2026-09-03，用户回复“按照你的这个思路来”，确认本方案方向和全部推荐决策。
>
> 顺序调整确认：2026-09-03，用户回复“可以，采用调整后的顺序”，确认使用 Walking Skeleton：先验证最小闭环和第一条真实 Worker 链，再固化持久化、接入真实模型并完成整链加固。
>
> 本轮复核授权：2026-09-04，用户确认先进行 M2-21 方案复核。该确认只授权形成复核结论和同步文档，不等于确认复核稿，也不授权 M2-21.1 代码开发。
>
> 复核方案确认：2026-09-04，用户回复“我已经确认M2-21的方案了，但是在执行之前我需要你先和我把这一步的所有内容和我讲明白”，确认第 20 节的能力边界、公开主路径和新十二步顺序。
>
> M2-21.1 授权：2026-09-04 至 2026-09-05，用户明确确认并授权只完成 M2-21.1。该授权不包含 Capability Catalog/Resolver、Agent Definition、模型协议、Graph、Worker Runtime、真实 Worker、Qwen、持久化、API、记忆或任何后续步骤。
>
> M2-21.2 授权：2026-09-05，M2-21.1 完成并停止后，用户回复“可以开始下一步了”。依照已经确认的十二步顺序和当时唯一下一动作，该授权只指 M2-21.2 Capability Catalog/Resolver 与 Agent Definition，不包含 M2-21.3 Provider 协议、Graph、Runtime、真实 Worker 或后续能力。
>
> M2-21.3 授权：2026-09-05，M2-21.2 完成并停止后，用户明确回复“开始M2-21.3”，随后回复“继续”要求完成当前工作。授权只包含 Planner/Decision/Handoff/Answer Provider 协议、严格请求/响应边界和确定性 Mock，不包含 M2-21.4 Supervisor/LangGraph、Fake Worker 运行闭环或后续能力。
>
> M2-21.4 授权：2026-09-05，M2-21.3 完成后，用户明确回复“开始下一步M2-21.4”。授权只包含最小 Supervisor LangGraph、Resolver 安全投影输入、确定性 Mock Provider 与 Fake Worker 闭环，不包含 M2-21.5 Worker Runtime、树形预算、Harness 适配、真实 Worker 或任何后续能力。
>
> M2-21.5 授权：2026-09-05，M2-21.4 完成并停止后，用户回复“开始下一步”。依照已确认的十二步顺序和当时唯一下一动作，该授权只包含通用 Worker Runtime、树形预算、终止管理、Harness/Provider预算适配和内存父子 Trace 合同，不包含 M2-21.6 Business Data Worker、真实 Tool 调用、数据库父子 AgentRun、Qwen、API 或任何后续能力。
>
> M2-21.6 授权：2026-09-05，M2-21.5 完成并停止后，用户明确回复“开始下一步M2-21.6”。该授权只包含有界 Action/Observation Business Data Worker、M1 两个业务 Tool 的真实纵向调用、Agent Definition 可执行状态和对应单元/PostgreSQL集成验证，不包含 M2-21.7 Knowledge Worker、双 Worker L2、Qwen、父子 AgentRun 持久化、API、记忆、并行或任何后续能力。
>
> M2-21.7 授权：2026-09-05，M2-21.6 完成并停止后，用户明确回复“开始下一步M2-21.7”。该授权只包含有界 Knowledge Worker、三个 M2 知识 Tool 的真实调用、Knowledge Agent Definition 可执行状态、两个真实 Worker 的顺序 L2、稳定合并与部分成功验证，不包含 M2-21.8 Qwen/统一证据回答、父子 AgentRun 持久化、API、记忆、并行或任何后续能力。
>
> M2-21.8 授权：2026-09-05，M2-21.7 完成并停止后，用户明确回复“开始下一步M2-21,8”，随后回复“继续”要求完成当前步骤。该授权只包含四角色严格 Qwen Provider、统一 Answer Evidence/Citation 边界、Graph 终态引用复核、配置、单元测试和显式真实 Smoke，不包含 M2-21.9 父子 AgentRun/Checkpoint 持久化、公开 API 迁移、完整记忆/恢复、并行或任何后续能力。
>
> M2-21.9 授权：2026-09-05，用户在连续步骤上下文中回复“开始下一步M2-9”。依照已确认十二步顺序、M2-09早已完成以及当时唯一下一动作，本轮明确说明按 M2-21.9 执行且用户未纠正。授权只包含父子 AgentRun、共享任务板、Checkpoint、最终答案 Evidence 映射、Repository/Service、迁移和测试，不包含 M2-21.10 公开 Agent Gateway/API 迁移、完整记忆/恢复、Re-plan、并行或后续能力。
>
> M2-21.10 授权：2026-09-05，用户明确回复“开始下一步M2-21.10”。授权只包含唯一公开 Agent Gateway、现有聊天 API 迁移、Supervisor/两个真实 Worker/持久化主路径接线，以及 L0、Business 单 Worker、Knowledge 单 Worker、跨 Worker、部分成功和旧 M1 入口退出门禁；不包含 M2-21.11 跨请求记忆/恢复/Re-plan、M2-21.12 并行/完整矩阵或任何后续能力。

> M2-21.11 授权：2026-09-07，M2-21.10正式收尾后，用户明确回复“接着完成M2-21.11”。授权只包含有界安全对话记忆、澄清暂停/同根恢复、跨请求重新获权、最多一次Re-plan、累计预算和重复Tool保护、request_id重复提交保护及对应测试/记录；不包含M2-21.12并行调度、完整G0～G7矩阵、任何新Tool/Worker/模型协议/迁移或后续里程碑。
>
> M2-21.12 授权：2026-09-07，M2-21.11完成并收尾后，用户明确回复“开始M2-21.12”。授权只包含独立只读Worker的有界并行、并发Session/Trace/预算隔离、G0～G7及权限/故障/资源收口矩阵、显式Smoke、Seed恢复和进度同步；不包含M2-22评估Runner、M2-23前端、M2-24阶段收口、任何新Tool/Worker/模型协议/迁移或M4/M5能力。
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
                         └─ 后续经单独确认的专业 Worker
                              ↓
                    Harness → Tool / Skill / Service
                              ↓
                 PostgreSQL / pgvector / Storage / 外部服务
                              ↓
                  Observation + Evidence + Artifact
                              ↓
                    Answer Evidence Set
                              ↓
                    统一 Answer Provider
                              ↓
                      Citation Validator
                              ↓
                          最终回答
```

### 3.1 Supervisor

Supervisor 负责总目标、任务 DAG、Worker 选择、依赖、子预算、进度、失败处理、完成状态和 Answer Evidence Set。最终自然语言统一交给 Answer Provider，再由 Citation Validator 验证；Supervisor 不直接访问数据库、宿主文件系统、Storage Key、Tool 或内部 Service。

### 3.2 M2-21 首批 Worker

M2-21 实际跑通两个专业 Worker：

- `BusinessDataWorker`：直接复用 M1 的 `get_product_spec` 和 `search_inventory` Tool、Service、Repository、数据库 Evidence 与 Harness，不嵌套 M1 固定 Planner；
- `KnowledgeWorker`：使用 M2 的 `search_knowledge`、`read_uploaded_file` 和 `get_evidence_detail`，返回文档 Context/Evidence、公开文件结果和明确未知项。

M1 的原库存 Graph、Provider、API 和回归继续保留，作为已经完成的垂直切片和兼容基线。

### 3.3 后续 Worker

- M3 已退出当前秋招主线；只有重新提交并确认阶段方案后，才增加 Vision Worker 和多模态 Artifact；
- M4 推荐版正式方案已确认只增加 Web Research Worker 和一个 `cross-border-market-research` Skill；固定分析与 Markdown 组织分别由 Analysis Service、Report Service 承担，不把它们包装成独立 Worker；
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
| M4 | 复用前两类 Worker，只新增 Web Research Worker；受控搜索/正文读取、Web Evidence、长任务恢复、Markdown 和一个研究 Skill | 独立 Analysis/Report Worker、PDF、Redis/Celery、生产级全面加固 |
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

- 不一次实现 Vision、Web Research 等后续专业 Worker；M4 已确认的 Analysis/Report 仍是确定性 Service，不是 Worker；
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

以下顺序采用 Walking Skeleton：先用最小合同、Mock 和 Fake Worker 跑通一条可以从输入走到结果的细骨架，再接 Harness 和两个真实 Worker；随后尽早接入真实 Qwen 和统一证据回答，再固化数据库状态、迁移公开 API、补齐记忆恢复并完成整链矩阵。它改变的是验证先后，不减少任何企业级合同、安全、持久化、Evidence 或矩阵要求。

以下顺序已经由用户确认，但不构成代码开发授权；每一步仍必须单独得到开始确认：

1. `M2-21.1`：冻结 Agent、Task、Action、Observation、Delegation、Worker Result、终态合同，并冻结迁移验收样本；
2. `M2-21.2`：建立 Capability Catalog/Resolver 与 Agent Definition，安全投影当前真实能力；
3. `M2-21.3`：实现 Planner、Decision、Handoff、Answer Provider 协议和确定性 Mock；
4. `M2-21.4`：搭建最小 Supervisor LangGraph，以 Fake Worker 跑通 L0、L1、最小 L2、追问和不支持请求；
5. `M2-21.5`：建立可复用 Worker Runtime、树形预算、终止管理和 Harness 适配器；
6. `M2-21.6`：实现有界 Action/Observation 的 Business Data Worker，验证自主选择 M1 两个 Tool；
7. `M2-21.7`：实现 Knowledge Worker，并跑通两个真实 Worker 的顺序 L2 复合任务；
8. `M2-21.8`：接入严格 Qwen，完成真实目标理解、规划、行动选择、统一证据回答和 Citation Validator；
9. `M2-21.9`：把已验证合同固化为父子 AgentRun、共享任务板、Checkpoint 和回答 Evidence 映射；
10. `M2-21.10`：将现有公开聊天 API 切换到 Agent Gateway，覆盖 L0、单 Worker、多 Worker、部分成功，并执行 M1 主路径迁移门禁；
11. `M2-21.11`：补齐有界对话记忆、澄清暂停/恢复、跨请求重新获权、有限 Re-plan 和重复提交保护；
12. `M2-21.12`：验证独立只读 Worker 有界并行、真实权限/故障/资源矩阵并收口。

四个提前反馈点：M2-21.4 能证明控制骨架可走通，M2-21.6 能证明第一条真实 Tool 纵向链可走通，M2-21.7 能证明正常复合问题可以由两个 Worker 顺序协作，M2-21.8 能证明真实模型会在严格合同和 Evidence 边界内工作；此后才固化持久化并迁移公开入口。

### 12.1 每一步预计文件、调用链和验证重点

文件清单是编码前预期，RED 阶段可以因真实依赖小幅调整，但必须记录原因且不能越过本步边界。

| 步骤 | 预计新增/修改文件 | 本步调用链位置 | RED/GREEN验证重点 |
|---|---|---|---|
| M2-21.1 | `app/schemas/agent.py`、`app/agents/engineered_state.py`、按需导出文件、`tests/fixtures/agent_acceptance.py`、`tests/unit/test_engineered_agent_contracts.py` | API之后的Schema与Agent状态合同；不运行Provider、Graph、Tool或数据库 | 多任务依赖、循环/重复ID、互斥Action、Delegation/Result、双层状态、敏感字段禁止、有界载荷、Evidence上限、无完整CoT字段、G0-G7验收样本形状；M1合同回归 |
| M2-21.2 | `app/capabilities/contracts.py`、`catalog.py`、`resolver.py`、`app/agents/definitions.py`、必要的Registry安全投影、`tests/unit/test_capability_resolver.py` | Agent → Capability Resolver → Agent/Skill/Tool元数据；不执行能力 | 类型/版本、角色预过滤、候选上限、稳定排序、未知/伪造能力、未实现能力拒绝、敏感元数据不泄露、M1两Tool/M2五Tool精确回归 |
| M2-21.3 | `app/llm/agent_schemas.py`、`agent_provider.py`、`agent_mock.py`、`app/llm/__init__.py`、`tests/unit/test_agent_providers.py` | Agent合同 → Mock Planner/Decision/Handoff/Answer Provider；不执行Graph、真实能力或数据库 | 严格结构、能力引用、单次唯一行动、追问/结束/无法完成、Mock确定性、Prompt注入只作数据、安全错误；M1 Provider不变 |
| M2-21.4 | `app/agents/supervisor.py`、`app/agents/graphs/engineered_multi_agent.py`、状态/导出、`tests/unit/test_multi_agent_graph.py` | Schema → 最小Supervisor LangGraph → Resolver/Mock Provider/Fake Worker → AgentResult；不落数据库或真实Tool | L0直接回答、L1一次Handoff、最小顺序L2、Observation后结束、等待用户、无能力、重复/步数终止、状态不含完整CoT；同输入确定性 |
| M2-21.5 | `app/agents/runtime/` 下Worker执行、Dispatcher、Termination等模块，`app/runtime/budget.py`、`executor.py`、`trace.py`、配置、错误和单元/集成测试 | Agent Action/Delegation → Worker Runtime → Harness → 已登记能力抽象 | 通用分派、可信CurrentUser、父子预算原子扣减、委派深度/数量、重复/无进展、超时、事务/savepoint、Trace父子关联和脱敏；M1预算保持 |
| M2-21.6 | `app/agents/workers/business_data.py`、Agent Definition、Graph适配、单元和真实PostgreSQL集成测试 | Supervisor → Business Worker → Runtime/Harness → M1 Tool → Service → Repository → PostgreSQL → DB Evidence | 只库存/只规格/组合查询时自主选择最小必要Tool、商品歧义、角色/market/tenant、拒绝/超时、Observation、Evidence和预算；第一条真实L1纵向链，不嵌套M1 Planner |
| M2-21.7 | `app/agents/workers/knowledge.py`、Agent Definition、Supervisor/Graph顺序L2扩展、单元和真实PostgreSQL/Storage集成测试 | Supervisor → Business/Knowledge Worker顺序调度 → Harness → M1/M2 Tool → PostgreSQL/Storage →混合Observation | 知识搜索、文件读取、Evidence详情、无证据、ACL/软删除/旧active、复合任务依赖、稳定合并、一个Worker失败时部分成功；本步不并行 |
| M2-21.8 | `app/llm/agent_qwen.py`、Provider/配置与 `.env.example`、统一 Answer Evidence/Citation 适配、Graph、单元测试和显式 Smoke | Supervisor/Worker → Qwen API → 结构化计划/行动/Handoff/证据回答 → Citation Validator；真实执行仍经Runtime/Harness | HTTPS/密钥、关闭模型联网、严格输出、真实一跳/多跳、未知能力/多余参数拒绝、Observation不可改写、伪造引用、429/5xx/超时脱敏、日志无秘密；Mock回归不变、真实Smoke默认跳过 |
| M2-21.9 | `app/models/runtime.py`、Agent任务/Checkpoint/回答Evidence Repository与Service、`app/schemas/agent.py`、`app/schemas/evidence.py`、`migrations/versions/*_agent_runtime.py`、迁移/Service测试 | 已验证Agent状态/任务/Evidence → Model/Repository → PostgreSQL；不改变规划策略 | 父子Run、任务DAG强约束、共享任务板、版本冲突、跨tenant/user/thread恢复拒绝、敏感状态拒绝、Evidence去重/12条上限、upgrade/downgrade和Alembic单head |
| M2-21.10 | `app/services/conversation.py`、`app/api/routers/threads.py`、依赖装配、`app/schemas/chat.py`、HTTP集成测试 | API → Schema → Agent Gateway → 单Worker/Supervisor → Harness/Tool → Evidence → Answer | 同一公开入口的L0、单Worker、复合多Worker和部分成功；旧图零调用、无旧图兜底、事务提交/回滚、公开响应脱敏和M1结果回归 |
| M2-21.11 | Agent memory/answer evidence/checkpoint Service与Repository、Graph/API集成、Schema及单元/集成测试 | 有界消息/安全摘要/Checkpoint → 澄清恢复或有限Re-plan → Answer Evidence Set → Answer Provider | 最近消息＋安全摘要、指代恢复、澄清暂停/恢复、跨请求重新获权、重复提交、有限Re-plan、撤权竞态和重复Tool/Evidence防护 |
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
13. 十二步采用 Walking Skeleton 顺序：M2-21.4 先得到 Mock/Fake 最小闭环，M2-21.6 得到第一条真实业务链，M2-21.7 得到顺序双 Worker 协作，M2-21.8 尽早验证真实 Qwen 和统一证据回答，再固化持久化、迁移公开 API 并补齐记忆恢复；
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

本文件能够证明：用户已经确认“可分阶段扩展的工程化多 Agent 底座”方向、上述实施取舍、M2-21 与后续里程碑边界和十二步 Walking Skeleton 顺序；M2-21.1 已按第 22 节冻结严格合同、状态外壳和 G0～G7 样本，M2-21.2 已按第 23 节建立安全 Capability Catalog/Resolver 与两个 Agent Definition，M2-21.3 已按第 24 节建立四类 Agent Provider 协议、输出校验器和确定性 Mock，M2-21.4 已按第 25 节建立最小 Supervisor LangGraph 并以 Fake Worker 跑通 L0/L1/顺序 L2、追问、拒绝与有界停止，M2-21.5 已按第 26 节建立通用 Worker Runtime、树形预算、终止管理、Harness适配和内存父子Trace合同，M2-21.6 已按第 27 节接通真实 Business Worker L1，M2-21.7 已按第 28 节接通真实 Knowledge Worker、三个知识Tool及顺序双Worker L2，M2-21.8 已按第 29 节接入严格 Qwen Planner/Decision/Handoff/Answer和统一 Citation Validator，M2-21.9 已按第 30 节把父子Run、任务板、Checkpoint和答案Evidence映射固化为受身份边界保护的PostgreSQL模型、Repository和Service，M2-21.10 已按第 31 节把公开聊天唯一入口迁移到 Agent Gateway，并把实际 Supervisor、Worker Runtime、两个真实 Worker、Tool/Harness、父子Run、任务板、Checkpoint和最终Evidence接成一条可审计主路径，M2-21.11 已按第32节补齐有界安全记忆、澄清同根恢复、跨请求重新获权、一次Re-plan、累计预算和重复提交保护。

本文件不能证明：真实 Qwen 在任意自然语言、长对话和生产负载下的稳定质量，并行调度、完整G0～G7公开矩阵、崩溃后自动租约接管或生产多Agent质量已经实现。

当前停止在 M2-21.11 完成点；必须等待用户确认理解并单独授权 M2-21.12，不能直接开始后续代码。

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

## 19. 2026-09-03｜Walking Skeleton 历史顺序确认与整理（已被 2026-09-04 复核顺序取代）

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
- 当时的定向检查确认：M2-21.4 是 Mock/Fake 最小闭环，M2-21.6 是 Business 真实纵向链，M2-21.7 是顺序双 Worker，M2-21.8 是持久化，M2-21.9 是真实 Qwen；该历史顺序已由第 12 节当前顺序取代；
- 搜索旧映射 `M2-21.3=AgentRun`、`M2-21.5=Qwen`、`M2-21.9=Supervisor Graph`，结果为 `NONE`；
- Markdown 代码围栏数量为 `12` 且偶数配对；
- `git diff --check` 通过，仅有 Git 的 LF/CRLF 行尾转换提示。

### 19.5 能证明与不能证明

以上结果能证明唯一方案、M2入口和总看板已经采用同一个 Walking Skeleton 顺序，步骤编号及验证表没有错位。不能证明最小Graph、Fake Worker、真实Business/Knowledge Worker、持久化或Qwen已经实现；这些仍需在对应步骤取得单独授权后，以实际RED/GREEN和回归结果证明。

### 19.6 数据、风险与下一动作

本次没有运行应用或测试，没有连接PostgreSQL/Storage，也没有修改正式演示数据，因此无需恢复Seed。本节保存的是 2026-09-03 的历史确认过程；2026-09-04 用户确认复核方案后，第 12 节已经成为唯一当前顺序。后续排查编号时应先核对第 12 节，再核对当前步骤日志和 M2 入口。

## 20. 2026-09-04｜秋招目标下的 M2-21 方案复核确认记录

> 用户回复“我已经确认M2-21的方案了，但是在执行之前我需要你先和我把这一步的所有内容和我讲明白”，确认本节的能力边界、公开主路径和新十二步顺序。新顺序已经同步为第 12 节唯一当前顺序；该确认仍不授权 M2-21.1 代码开发。

### 20.1 当前现状和真正缺口

当前已经有 M1 库存查询闭环，以及 M2-01 至 M2-20 的自建 RAG、Evidence 和五个受控 Tool，但还没有：

- 统一 Agent Gateway、Supervisor、Business Data Worker 和 Knowledge Worker；
- 能理解目标并选择能力的真实 Qwen 规划/行动协议；
- Worker 的有界 Action → Observation → 下一步/结束循环；
- 父子 Run、结构化 Handoff、短期记忆、Checkpoint、有限 Re-plan 和树形预算；
- 同时使用数据库与文档 Evidence 的统一 Answer Provider；
- 通过新 Agent 主路径工作的公开聊天 API 和前端知识问答；
- 多 Agent 路由、工具、引用、安全、资源和故障的可复现评估。

所以 M2-21 不能被缩成一个固定的“库存或知识”分类器，也不能只做 Knowledge RAG 包装。它必须完成真实多 Agent 的后端核心闭环。

### 20.2 复核结论：能力不删，只调整边界与验证顺序

| 能力 | 复核结论 |
|---|---|
| Supervisor、两个真实 Worker、Capability Catalog/Resolver | 全部保留 |
| 目标理解和“意图识别” | 保留，但实现为“目标/子任务理解 → 能力发现 → 结构化行动”，不新增脆弱的固定意图枚举和 `if/else` 路由 |
| 结构化 Handoff、父子 Run、共享任务板 | 全部保留 |
| 短期/对话记忆、澄清恢复、有限 Re-plan | 全部保留；不扩张为无治理永久画像 |
| 树形预算、终止、权限、Trace、Checkpoint | 全部保留 |
| 统一 Answer Provider、Evidence、Citation Validator | 全部保留，并把真实回答验证前移 |
| 独立只读 Worker 有界并行 | 保留在收口步骤；先证明顺序正确，再证明并行隔离 |
| 真实 Qwen | 保留并由原第 9 步前移，避免长期只验证 Mock |
| M2-22 评估、M2-23 前端、M2-24 验收 | 全部保留；验收样本在 M2-21.1 提前冻结，每步增量回归，完整 Runner 仍由 M2-22 完成 |
| M4、M5 | 都是最终秋招主线，不删除；M3 继续暂缓 |

本轮只收紧没有真实需求支撑的抽象：未实现能力不注册，不为固定分析/报告创建假 Worker，不引入无界长期记忆、任意 SQL/HTTP、MCP、Redis/Celery 或通用 Browser。

### 20.3 最终公开聊天主路径和 M1 生命周期

复核建议把最终迁移目标冻结为：

```text
同一个 POST /api/v1/threads/{thread_id}/messages
→ Chat Schema / Conversation Service
→ Agent Gateway + 可信 RunContext
→ Planner + Capability Resolver
   ├─ L0：统一 Answer Provider 直接回答
   ├─ L1：选择一个专业 Worker
   └─ L2：Supervisor 委派多个 Worker
→ Worker Runtime + Harness
→ 允许的 Tool → Service → Repository/Provider
→ PostgreSQL / pgvector / Storage
→ Observation + Answer Evidence Set
→ 统一 Answer Provider
→ Citation Validator
→ 公开回答
```

这里的“意图识别”不是把句子先硬分成 `inventory_query` 或 `knowledge_query`，而是让模型在 Resolver 给出的真实能力范围内理解目标、形成子任务并提出结构化行动；程序再验证能力、参数、权限、预算和停止条件。

M1 的处理方式必须明确区分“接口兼容”和“旧实现继续当主路由”：

- 保留现有聊天 URL、请求/响应合同、数据库 Evidence、合成数据和 M1 回归样本，避免客户端无意义破坏；
- `InventoryQueryAgent` 固定 Graph 与旧 Provider 只保留为内部兼容/回归基线，便于证明迁移没有破坏库存结果；
- 公开聊天切换完成后，库存问题也必须经过 Agent Gateway → Resolver → Business Data Worker，不能直连旧 Graph，也不能在新 Gateway 失败后偷偷回退旧 Graph；
- 不新增公开 `legacy` 端点，不让客户端选择 Agent 名称或路由模式；路由责任属于系统。

### 20.4 Business Worker 的自主性和统一回答边界

`BusinessDataWorker` 不是把 M1 固定图换一个类名。它获得的只是当前获准能力摘要，并在有界循环中执行：

```text
读取子任务和可用能力
→ 选择 get_product_spec、search_inventory、先后组合或追问
→ Runtime/Harness 校验并执行
→ 读取结构化 Observation
→ 判断信息是否足够、是否需要下一动作、是否应停止
```

例如只问库存时不应机械调用规格 Tool；只问规格时不应查询库存；商品或市场歧义会影响正确结果时先追问；需要“库存是否满足某产品条件”时可以在预算内组合两个 Tool。Worker 不嵌套 M1 Planner，也不能绕过 Harness 直接调用 Service/Repository。

最终多 Agent 路径不再使用 M1 固定字符串模板作为统一回答方式。统一 Answer Provider 根据已获权 Observation 与 Answer Evidence Set 组织自然语言；确定性程序继续负责数字原值、权限、Evidence 映射和引用校验。也就是说，模型负责表达和有证据的综合，不能修改库存数值、伪造来源或把 Worker 文字自动当成事实。

### 20.5 确认后的新十二步顺序（已同步到第 12 节）

这次调整仍使用 Walking Skeleton，但把真实模型、引用回答和公开迁移的反馈提前；全部高含金量能力仍在 M2-21 内：

1. `M2-21.1`：冻结 Agent、Task、Action、Observation、Delegation、Worker Result、终态合同，并冻结迁移验收样本；
2. `M2-21.2`：建立 Capability Catalog/Resolver 与 Agent Definition，只安全投影真实能力；
3. `M2-21.3`：实现 Planner、Decision、Handoff、Answer Provider 协议和确定性 Mock；
4. `M2-21.4`：搭建最小 Supervisor LangGraph，以 Fake Worker 跑通 L0、L1、最小 L2、追问和不支持请求；
5. `M2-21.5`：建立复用 Worker Runtime、树形预算、终止管理和 Harness 适配器；
6. `M2-21.6`：实现有界 Action/Observation 的 Business Data Worker，验证自主选择 M1 两个 Tool；
7. `M2-21.7`：实现 Knowledge Worker，并跑通两个真实 Worker 的顺序 L2 复合任务；
8. `M2-21.8`：接入严格 Qwen，完成真实目标理解、规划、行动选择、统一证据回答和 Citation Validator；
9. `M2-21.9`：把已验证合同固化为父子 AgentRun、共享任务板、Checkpoint 和回答 Evidence 映射；
10. `M2-21.10`：将现有公开聊天 API 切换到 Agent Gateway，覆盖 L0、单 Worker、多 Worker、部分成功，并执行 M1 主路径迁移门禁；
11. `M2-21.11`：补齐有界对话记忆、澄清暂停/恢复、跨请求重新获权、有限 Re-plan 和重复提交保护；
12. `M2-21.12`：验证独立只读 Worker 有界并行，以及真实权限、故障、资源、Qwen/BGE 和迁移回归矩阵并收口。

与 2026-09-03 的历史顺序相比，`M2-21.1` 至 `.7` 的地基和两个真实 Worker 不删除；真实 Qwen 与统一引用回答前移到 `.8`，持久化顺延到 `.9`，公开 API 迁移前移到 `.10`，完整多轮记忆和恢复集中到 `.11`。第 12 节现已同步为本顺序，不再存在两套当前编号。

### 20.6 每步文件、调用链和验证重点

| 步骤 | 预计主要文件 | 本步调用链位置 | 最关键验证 |
|---|---|---|---|
| 21.1 | `app/schemas/agent.py`、`app/agents/engineered_state.py`、合同测试/验收夹具 | Schema/Agent 状态合同，不执行能力 | DAG/互斥 Action/终态/敏感字段/迁移样本/M1 合同 |
| 21.2 | `app/capabilities/`、`app/agents/definitions.py`、Resolver 测试 | Agent → Resolver → 安全能力摘要 | M1 Registry精确2个Tool；M2安全投影累计5个唯一Tool（2个Business＋3个Knowledge）并登记2个Worker；伪造/越权能力拒绝 |
| 21.3 | `app/llm/agent_*` 协议、Mock 与测试 | Agent 合同 → Mock Planner/Handoff/Answer | 严格结构、单次唯一行动、追问/结束/拒绝、注入文本不改变权限 |
| 21.4 | `app/agents/supervisor.py`、多 Agent Graph 与测试 | Schema → Supervisor → Resolver/Mock/Fake Worker | L0/L1/L2、追问、不支持、重复和步数终止；不落数据库 |
| 21.5 | `app/agents/runtime/`、现有 Runtime 适配与测试 | Action/Handoff → Worker Runtime → Harness | 可信身份、父子预算、深度/次数、超时、重复、Trace 和事务边界 |
| 21.6 | `app/agents/workers/business_data.py` 及数据库集成测试 | Supervisor → Business Worker → Harness → M1 Tool → Service → Repository → PostgreSQL | 只库存/只规格/组合/歧义；不嵌套旧 Planner；数据库 Evidence |
| 21.7 | `app/agents/workers/knowledge.py` 及真实 PostgreSQL/Storage 测试 | Supervisor → 两 Worker 顺序协作 → M1/M2 Tool → 数据与文档 Evidence | 单知识、跨 Worker、ACL、无证据、部分成功和稳定合并 |
| 21.8 | `app/llm/agent_qwen.py`、Answer Evidence/Citation 适配与 Smoke | Supervisor/Worker → Qwen → 结构化行动/回答 → Citation Validator | 严格输出、真实一跳/多跳、伪造引用、429/5xx/超时脱敏、Mock 回归 |
| 21.9 | Runtime Model/Repository/Service、迁移与测试 | Agent 状态/任务/Evidence → PostgreSQL | 父子 Run、DAG约束、Checkpoint版本、跨身份恢复拒绝、upgrade/downgrade |
| 21.10 | `app/services/conversation.py`、`threads.py`、聊天 Schema 和 HTTP 测试 | 公开 API → Agent Gateway → Worker/Harness/Tool → Answer | 唯一公开入口、旧图零调用、无旧图兜底、L0/L1/L2、部分成功与事务 |
| 21.11 | Memory/Checkpoint/Graph/API 集成及测试 | 有界消息/安全摘要 → 恢复/Re-plan → 回答 | 指代、澄清恢复、重新获权、重复 Tool/Evidence 防护、有限 Re-plan |
| 21.12 | 并发 Dispatcher、整链矩阵、Smoke/基准与进度记录 | 完整后端链；前端仍留给 M2-23 | Session/Trace/原子预算隔离、权限/注入/故障、性能成本、Seed 恢复 |

如果某一步 RED 证明范围仍太大，可以把该步继续拆成 `.x.a/.x.b` 的教学小步骤，但不能借拆分删除本表的完成条件，也不能未经确认提前进入后续编号。

### 20.7 必须冻结的迁移验收样本

| 编号 | 场景 | 必须观察到的结果 |
|---|---|---|
| G0 | 唯一公开入口 | 客户端继续调用同一个消息 POST，不传路由/Agent；根 Run 属于 Agent Gateway |
| G1 | 禁止旧图直连/兜底 | 将旧 `InventoryQueryAgent.run` 设为调用即失败的 Spy，公开库存请求仍由 Business Worker 成功；Gateway 故障时返回统一安全错误而不是回退旧图 |
| G2 | 业务单 Tool | 库存问题只调用 `search_inventory`，规格问题只调用 `get_product_spec`；返回数据库 Evidence |
| G3 | 知识单 Tool | 只创建 Knowledge Worker，最小必要地调用知识 Tool，回答包含当前仍获权的文档引用 |
| G4 | 跨 Worker | 同一根 Run 下形成 Business/Knowledge 子 Run，分别只有自己的能力；最终答案区分数据库事实、文档事实和跨来源推断 |
| G5 | 澄清与恢复 | 信息不足时先进入 `waiting_user` 且不伪造 Evidence；补充信息后重新获权，只执行未完成动作 |
| G6 | 不支持与预算终止 | 写库存/自动下单等请求不调用 Tool；重复行动或超步数在确定上限内终止，不生成假成功 |
| G7 | 引用校验 | 合法引用精确映射 Answer Evidence Set；伪造、越界、重复或回答前撤权的引用不能进入成功响应 |

所有成功用例还必须共同断言：一个 Gateway 根 Run、Worker 子 Run 无孤儿、ToolCall 继承当前身份/预算/Trace、回答保存前完成引用校验、公开状态不暴露 Prompt/SQL/路径/密钥/原始异常。

### 20.8 与 M2-22、M2-23、M2-24、M4、M5 的边界

- M2-21 负责后端多 Agent 核心、真实 Qwen、记忆/恢复、公开聊天 API 迁移和工程矩阵；
- M2-22 基于 M2-21.1 冻结样本实现完整 Agent/RAG Runner 与指标，不等到 M5 才第一次评估；
- M2-23 完成上传、统一聊天、多 Agent 步骤和 Evidence 的用户可见前端；
- M2-24 完成真实演示、Chromium、故障矩阵和 M2 收口；
- M4 复用 M2 的 Supervisor、Business/Knowledge Worker，只新增 Web Research Worker，并完成三来源有界深度研究；
- M5 完成跨 M2/M4 的综合评估、安全/性能/成本加固、README、架构图、演示视频、简历和面试材料。

因此，M1/M2 是必要底座但不是整个秋招项目终点；M4 和 M5 仍保留为最终目标。

### 20.9 本次复核的文档链、验证边界和下一动作

本次只经过 `AGENTS长期协作规则 → 项目总看板 → M2阶段入口 → M2-21方案 → 总体设计/秋招范围/M4边界`。没有经过 `前端 → API → Schema → Agent/LangGraph → Harness → Tool → Service → Model → PostgreSQL/Storage` 运行链，也没有连接 Qwen、BGE 或 Tavily。

文档验证完成后只能证明：复核稿覆盖了现状、目标、非目标、前置条件、十二步文件/调用链/验证、完成边界、风险与迁移验收，并且和已确认的 M4 推荐版一致。它不能证明任何 Supervisor、Worker、意图理解、记忆、Qwen、API 迁移或并行已经实现。

用户已经确认本节复核方案。当前下一动作是先向用户完整讲明整个 M2-21，而不是只解释 M2-21.1；用户确认已经理解整体方案后，仍需单独授权 M2-21.1，不能自动编码。

### 20.10 本次修改文件、实际验证、风险和结果

本次修改及同步职责：

- 根`AGENTS.md`：保存“以秋招AI应用岗位为最高目标、帮助用户讲透项目、M4/M5不因后移而删除”的项目级长期协作规则；
- 本文件：保存M2-21复核原因、非删减结论、公开主路径、旧M1生命周期、Worker自主性、新十二步和迁移样本；
- `docs/progress/M2/M2_KNOWLEDGE_RAG.md`与`docs/PROJECT_PROGRESS.md`：先同步复核稿，用户确认后再同步当前停止点为“整体讲解中、未授权M2-21.1”；
- `docs/design/02_System_Architecture_and_Agent_RAG_Design.md`：把固定意图图、Redis/Celery、旧Tool/Skill数量和M4三Worker更新为当前架构；
- `docs/design/03_Data_Evaluation_and_Implementation_Plan.md`：把原始完整版路线明确标成历史基线，并同步M2/M4/M5当前主线；
- `docs/design/05_Autumn_Recruitment_Scope_Adjustment_Plan.md`：消除M4已确认与下半部仍写待确认的冲突；
- `docs/progress/M4/`两份文件：同步复用统一Answer Provider/Citation Validator、Report Service确定性边界和实际文档验证证据。

实际验证结果：

- 相关文档相对链接解析结果为`LINK_CHECK_PASS`；
- 本节推荐步骤和对应表均精确覆盖1至12，结果为`REVIEW_STEPS=12`、`REVIEW_TABLE_ROWS=12`且顺序检查为`True`；
- Markdown围栏检查为`FENCE_CHECK_PASS`，相关文件行尾检查为`TRAILING_WHITESPACE_PASS`；
- 过期关键词定向检查只命中总看板中明确标为“历史节点、后续已取代”的旧M4状态，没有仍作为当前方案的冲突；
- `git diff --check`通过，仅有Windows的LF/CRLF转换提示；
- Git范围检查只有根协作规则和`docs/`文档，没有应用代码、测试、迁移、配置、数据库或Storage改动。

这些结果能证明复核稿完整、步骤编号一致、外围权威文档不再把后续开发引回旧架构，也能证明本次没有越权编码。不能证明任何多Agent、意图理解、Worker自主循环、记忆、Qwen、API迁移、Checkpoint或并行已经运行。

原先“第12节与第20节存在两套顺序”的风险已解除：第12节已经提升为复核后唯一当前顺序，第19节只保留历史确认过程。当前主要剩余风险是 README 与旧面试指南仍可能包含早期原型或原始完整版表述，不应直接用于投递；它们应在 M5 作品化前按实际实现统一清理。

## 21. 2026-09-04｜整个 M2-21 实施前讲解范围与授权边界

> 本节保留 M2-21.1 开工前的历史停止点；当前状态已经由第 22 节取代。

### 21.1 用户要求与当前停止点

用户确认复核后的 M2-21 总方案，同时明确要求在执行前先讲明“整个 M2-21”，而不是只讲 M2-21.1。因此当前只进行整体方案教学和文档同步，没有创建或修改 Agent、Schema、测试、迁移、配置、API、数据库或前端代码。

讲解完成后也不自动开工。用户先确认已经理解整体方案，再单独授权 M2-21.1；每个后续 M2-21.x 仍按教学式单步开发规则独立讲解、实现、验证和确认。

### 21.2 整体讲解必须覆盖的九个问题

1. 当前已经有什么、缺什么，以及为什么 M1 固定聊天图和普通 RAG 还不等于多 Agent；
2. 最终一次自然语言请求怎样从公开 API 进入 Agent Gateway，并走到 L0、L1 或 L2；
3. Qwen、Planner、Capability Resolver、Supervisor、Worker、Harness、Tool、Service 和数据库分别决定什么；
4. Agent、Task、Action、Observation、Handoff、Worker Result、Evidence、Checkpoint 和父子 Run 怎样连接；
5. Business Data Worker 怎样自主选择 M1 Tool，而旧 M1 Graph 为什么只保留为内部回归；
6. 短期记忆、对话记忆、澄清恢复、有限 Re-plan、树形预算、失败和并发怎样受控；
7. M2-21.1 至 M2-21.12 每一步的输入、输出、主要文件、调用链位置、验证目标和不做内容；
8. 整个 M2-21 的完成标准、主要风险、优先排查方向，以及每一层能证明和不能证明什么；
9. M2-21 对秋招 AI 应用岗位的价值，以及它与 M2-22、M2-23、M2-24、M4 和 M5 的关系。

### 21.3 一条完整运行链的大白话解释

```text
用户自然语言
→ 现有聊天 API 接收请求
→ Agent Gateway 建立一次可信根任务
→ Qwen 在真实可用能力摘要内理解目标并给出结构化计划/行动
→ 简单问题直接回答；单领域问题交给一个 Worker；复合问题由 Supervisor 拆分和委派
→ Worker 在有界 Action/Observation 循环中选择自己的少量 Tool
→ Harness 逐次校验身份、权限、参数、预算、超时、重复和审计
→ Tool 调用既有 Service/Repository/Provider，读取 PostgreSQL、pgvector 或 Storage
→ Worker 只返回结构化 Observation、Evidence/Artifact ID、未知项和安全错误
→ Supervisor 合并仍然有效且重新获权的 Evidence
→ 统一 Answer Provider 组织自然语言
→ Citation Validator 拦截伪造或越界引用
→ API 返回公开答案，并在需要时保存可恢复的安全 Checkpoint
```

Agent Gateway 是统一入口和运行装配者，不是靠一串固定 `if/else` 做意图分类；Qwen 负责受限的语义理解和决策，Resolver 只提供真实且当前可候选的能力，Harness 对模型提出的每个动作拥有最终执行否决权。

### 21.4 十二步的学习主线

十二步不是十二个互不相关的功能，而是四段递进证明：

- `.1` 至 `.3` 先统一语言：状态/任务/行动/结果合同、能力目录和模型协议；
- `.4` 至 `.7` 再证明骨架和真实执行：Fake 闭环、公共 Runtime、Business Worker、Knowledge Worker 和顺序 L2；
- `.8` 至 `.11` 把真实智能接入产品链：真实 Qwen、证据回答、持久化、公开 API、记忆和恢复；
- `.12` 最后证明工程边界：受控并行、权限、注入、失败、资源、真实模型组合与迁移回归。

任何一步的通过都只证明该步覆盖的能力。例如 `.4` 只能证明控制流合同，不证明真实数据库权限；`.7` 能证明两个真实 Worker 顺序协作，但不证明真实 Qwen 的语义稳定性；`.8` 能证明真实模型受合同约束，但在 `.9` 前不证明跨请求恢复；`.10` 能证明公开入口完成单轮迁移，但完整多轮记忆和恢复要到 `.11`；只有 `.12` 通过后才能说 M2-21 后端阶段收口。

### 21.5 完整调用链位置

整个 M2-21 最终经过：

```text
前端（本阶段不改）
→ API（.10 接入，.11 补多轮）
→ Schema（.1 起）
→ Agent Gateway / Supervisor / Worker / LangGraph（.3-.8）
→ Harness / Runtime（.5 起）
→ 既有 Tool（.6-.7 复用，不重写）
→ 既有 Service / Repository / Provider（复用）
→ PostgreSQL / pgvector / Storage（.6-.7 真实读取，.9 新增运行状态持久化）
→ Answer Evidence / Citation（.8 起）
→ API 响应
```

M2-21 不经过 M2-23 的新前端，也不实现 M4 的 Web Research；但它必须留下稳定的 Worker、Handoff、Evidence、Checkpoint 和预算接口，让后续阶段只增加专业能力，不重写底座。

### 21.6 整体教学后的理解标准

在开始 M2-21.1 前，用户至少应能用自己的话说明：

- 为什么“意图识别”不是库存/知识二分类，而是目标理解、能力发现和结构化行动；
- 为什么 Qwen 可以提出行动，却不能决定身份、权限、真实预算或直接访问数据库；
- 为什么 Supervisor、Worker、Harness 和 Tool 不是同一个东西；
- 为什么 Worker 结果必须携带 Evidence，而不是只返回一句模型结论；
- 为什么旧 M1 Graph 不再走公开主路径，但仍值得作为回归基线保留；
- 为什么先顺序后并行、先内存合同后持久化、先 Mock 后真实 Qwen；
- 为什么完成 M2-21 仍不等于整个秋招项目完成，M2-22 至 M2-24、M4 和 M5 还分别负责评估、前端、验收、深度研究和作品化。

如果上述任一项仍不清楚，应继续讲解，不进入代码。

## 22. 2026-09-05｜M2-21.1 严格合同、状态外壳与迁移验收样本

### 22.1 授权、目标与边界

用户正式确认并授权开始 M2-21.1，并明确要求只建立整个多 Agent 系统共同使用的严格合同、Checkpoint 安全状态外壳和 G0～G7 迁移验收样本，不得提前实现 M2-21.2 或后续能力。

本步输入是现有 `M1Schema` 严格基类、Context/Evidence 的 12 条上限、可信 `RunContext`、M1 `ExecutionBudget` 与重复调用规则、M1 `InventoryGraphState` 的既有设计及相邻单元测试。输出是版本化 Task DAG、互斥 Action、Observation、Handoff、Worker Result、执行状态/业务结果和通用安全状态合同，以及版本化 G0～G7 测试夹具。

本步没有实现 Capability Catalog/Resolver、Agent Definition、Provider、Supervisor LangGraph、Worker Runtime、Business/Knowledge Worker、Qwen、AgentRun 数据库结构、Checkpoint 持久化、记忆、API 迁移、并行调度或 M2-22 以后内容。

### 22.2 大白话运行关系与关键设计

本步只规定“团队以后必须怎样填表”，没有启动真正的 Agent：

```text
可信请求身份与真实预算（仍由现有 Runtime 掌握）
→ TaskPlan 描述有依赖的任务
→ 一次 AgentDecision 只能选择一个 Action
→ 未来 Runtime 执行后形成公开安全 Observation
→ Supervisor 用程序组装的 Handoff 把一个任务交给 Worker
→ WorkerResult 分开报告执行是否正常结束和业务回答质量
→ EngineeredAgentState 只保存恢复所需的安全结构
```

主要冻结结论：

1. `TaskPlan` 最多 24 个任务；Task ID 唯一，依赖必须存在，拒绝自依赖和任意多节点循环。目标、能力、依赖、完成条件与列表长度均有硬上限；Task 同时具有明确分配状态和执行状态。
2. `AgentAction` 是以 `type` 区分的严格联合，只允许 `execute_capability`、`delegate_task`、`ask_user`、`finish`、`cannot_complete`；`AgentDecision` 只有一个 `action` 字段，混入第二种行动会作为多余字段拒绝。
3. 模型提出的 `DelegateTaskAction` 只有任务和目标 Worker，不能填写父 Run、身份、权限或预算；`AgentHandoff.allocated_budget_ref` 只存在于未来 Runtime 组装的内部交接包。
4. 通用 JSON 最多 32 个键、每层列表最多 32 项、最多 5 层、序列化最多 16384 字节、单个字符串最多 4000 字符，只接受有限 JSON 值；递归拒绝身份、tenant、角色、权限、父 Run、真实预算、SQL、路径、Storage Key、密钥、Token、堆栈和原始异常键。
5. Observation 能表达成功、部分成功、错误、拒绝和超时，且失败 Observation 不能同时携带结构化成功结果或 Evidence/Artifact；安全错误文本额外拒绝常见堆栈、SQL、本地路径和秘密模式。
6. Evidence 与 Artifact 每组最多 12 个且必须唯一；Task、Handoff、Observation、Worker Result 和状态中的文本、列表及资源消耗都有明确上限。
7. 执行状态固定为 `waiting/running/waiting_user/completed/failed`，业务结果固定为 `answered/partial/no_evidence/unsupported/denied/timed_out/system_error`。例如权限拒绝是系统正常结束的 `completed + denied`，超时和系统错误才是执行失败；矛盾组合直接拒绝。
8. `EngineeredAgentState` 是 Pydantic 可序列化状态外壳，只包含 Run ID、目标、计划、当前安全进度、公开 Observation/Worker Result、Evidence/Artifact ID、未知项、公开摘要、停止原因和资源消耗；不包含完整思维链、Prompt、消息全文、数据库 Session、Tool 对象、可信 RunContext、身份、权限、真实预算、SQL、路径、Storage Key 或原始异常。
9. G0～G7 夹具使用 `m2-agent-acceptance-v1` 版本，冻结唯一公开入口、禁止旧 M1 Graph 直连/兜底、Business 单 Tool、Knowledge 单 Tool、跨 Worker、澄清恢复、不支持/预算终止和引用校验八类场景；共同成功断言还冻结唯一 Gateway 根 Run、无孤儿 Worker、ToolCall 继承身份/预算/Trace、引用先校验再保存、回答 Evidence 最多 12 条和公开敏感字段黑名单。

### 22.3 修改文件与职责

- 新增 `app/schemas/agent.py`：定义合同版本、边界常量、Task/TaskPlan、五类 Action、Decision、Observation、Handoff、Worker Result、双层状态枚举、资源消耗、安全错误和有界 JSON；
- 新增 `app/agents/engineered_state.py`：定义未来 Graph 可使用的 Checkpoint 安全状态外壳及终态一致性检查；
- 新增 `tests/fixtures/agent_acceptance.py`：冻结版本化 G0～G7 输入、期望和共同迁移断言；
- 新增 `tests/unit/test_engineered_agent_contracts.py`：覆盖合法序列化和全部关键拒绝路径；
- 修改本记录、M2 阶段入口和项目总看板：同步授权、实现、验证、边界、风险和下一停止点；
- 没有修改 `app/schemas/__init__.py` 或 `app/agents/__init__.py`：本步合同当前只供内部模块按明确路径导入，不提前扩大包级公共导出面。

### 22.4 完整调用链位置

本步实际经过：

```text
前端（不经过）
→ API（不修改公开行为）
→ Schema（本步核心）
→ Agent State（本步核心，仅状态外壳）
→ LangGraph（未实现）
→ Harness（只复用既有可信边界，不扩展）
→ Tool（不调用、不修改）
→ Service / Repository / Model（不经过）
→ PostgreSQL / pgvector / Storage / 外部 Provider（不经过）
```

### 22.5 TDD 与实际验证

先写测试后运行的 RED 为：`tests/unit/test_engineered_agent_contracts.py` 在收集阶段报 `ModuleNotFoundError: No module named 'app.agents.engineered_state'`，结果为 `1 error`。这证明失败来自生产合同尚不存在。

最小实现后的第一次运行有 27 个通过、1 个失败；重复 Task ID 已被拒绝，但诊断文字是 `must be unique`，没有满足测试要求的明确 `duplicate`。只修改错误文案后为 `28 passed`。完成需求对照补强后，最终聚焦合同为 `31 passed`。

最终验证结果：

- 指定新测试与四组相邻回归：`73 passed in 5.75s`；
- 完整单元测试：`731 passed, 2 skipped in 25.25s`；
- 正式代码范围 `ruff check app tests scripts`：通过；
- 四个本步新增文件 `ruff format --check`：`4 files already formatted`；
- `mypy app`：`Success: no issues found in 122 source files`；
- `compileall`：通过；`pip check`：`No broken requirements found`；
- `git diff --check`：通过，只有工作区既有 LF/CRLF 转换提示；
- 额外运行 `ruff format --check app tests scripts` 时，发现未由本步修改的 `tests/integration/test_document_chunk_set_migration.py` 有 1 处既有格式差异，结果为 `1 file would be reformatted, 256 files already formatted`。`git status --short --` 该文件为空，证明它不是本步改动；为遵守单步边界没有顺手改写。

本步没有模型、数据库、Storage、网络或迁移行为，因此没有运行 Qwen/BGE Smoke、PostgreSQL 矩阵、Alembic 或 Seed 恢复；这些也不是 M2-21.1 合同验证能证明的内容。

### 22.6 能证明与不能证明

以上结果能证明：合同拒绝多余字段和非法 DAG；一次 Decision 只有一个 Action；通用 JSON 与 ID/文本/列表均有界；模型载荷不能注入可信身份、权限、父 Run 和真实预算；Observation/Handoff/Worker Result 边界清楚；执行状态与业务结果不会出现已覆盖的矛盾组合；状态可以 JSON 往返且不能塞入已列出的运行时或敏感字段；G0～G7 样本形状已经冻结；现有 M1 合同和固定库存 Graph 单元回归没有退化。

这些结果不能证明任何 Action 已被执行，也不能证明 Capability 发现、真实 Supervisor/Worker、Harness 树形预算、LangGraph 状态转换、数据库/文档读取、Checkpoint 持久化、Qwen 规划、聊天 API 迁移、对话恢复、并行调度或 G0～G7 运行行为已经实现。G0～G7 当前只是后续步骤必须消费的版本化测试输入和期望。

### 22.7 风险、排查与下一动作

当前主要风险是后续 Provider 或 Runtime 绕过这些合同、把模型 `delegate_task` 直接当成可信 Handoff，或在持久化时另建一套无界 JSON。出现问题时优先按 `模型原始结构 → AgentAction/TaskPlan 验证 → Runtime 注入可信 Handoff/预算 → Observation/WorkerResult → EngineeredAgentState JSON` 顺序排查；Evidence 错位时从原始 Evidence ID、每层去重与 12 条上限开始检查；状态恢复异常时先检查合同版本、额外字段和 JSON 深度/大小。

M2-21.1 已完成并停止。下一动作只能是先由用户确认已经理解本步，再单独讨论并授权 M2-21.2；不得自动开始 Capability Catalog/Resolver 或任何后续实现。

## 23. 2026-09-05｜M2-21.2 Capability Catalog/Resolver 与 Agent Definition

### 23.1 授权、目标与边界

M2-21.1 完成并停止后，用户回复“可以开始下一步了”。按照已经确认的十二步顺序和当时文档中的唯一下一动作，本轮只授权 M2-21.2：在现有 Tool Registry 上方建立版本化 Capability 合同、只读 Catalog、确定性 Resolver，以及 Business Data/Knowledge 两个 Worker 的声明态 Agent Definition。

本步输入是 M1 精确两个 Tool、M2 累计五个 Tool 的既有 Registry，可信 `RunContext.roles`，M2-21.1 的 `AgentHandoff`、`WorkerResult`、Capability/Worker ID 等严格合同。输出是内部服务端能力定义、模型可见安全摘要、模型只可提交的有界能力 ID 选择、按可信角色与 Worker 白名单求交的 Resolver，以及两个尚不可执行的 Worker 角色定义。

本步没有实现 Planner/Decision/Handoff/Answer Provider 协议或 Mock、Supervisor/LangGraph、Worker Runtime、Business/Knowledge Worker 执行代码、Harness 适配、Qwen、数据库模型/迁移、Checkpoint、记忆、API 迁移、并行调度或 M2-21.3 以后能力。

### 23.2 大白话运行关系与关键设计

本步建立的是“公司能力通讯录和前台筛选规则”，不是让通讯录中的员工开始工作：

```text
现有 M1/M2 Tool Registry（真实实现事实）
→ Capability Catalog 适配成版本化内部元数据
→ 服务端 Agent Definition 限定每个 Worker 最多五个 Tool
→ Resolver 使用可信 RunContext 角色与 Worker 白名单求交
→ 模型只得到少量、稳定排序、不可执行的安全能力摘要
→ 后续 Runtime 仍必须通过 Registry/Harness 做最终权限与执行检查
```

主要冻结结论：

1. Capability 类型从合同层区分 `tool/skill/agent/runtime`；当前 Catalog 只登记五个已有 Tool 和两个 Worker 角色，不虚构 Skill 或 Runtime capability。
2. 五个 Tool 标记为 `available`；两个 Worker 只标记为 `declared`。它们有职责和合同，但没有 Runtime，因此默认委派候选为空，显式选择声明态 Worker 会被拒绝为 unavailable。
3. M1 Catalog 精确复用 `get_product_spec/search_inventory`；M2 Catalog 累计复用这两个 Tool 与 `search_knowledge/read_uploaded_file/get_evidence_detail`，没有修改原 Registry 或 PermissionGuard。
4. Business Data Definition 只能看两个 M1 Tool；Knowledge Definition 只能看三个知识 Tool；每个 Worker 都以 `AgentHandoff` 为输入、`WorkerResult` 为输出且不能继续委派。
5. 模型控制的 `CapabilitySelection` 只有最多 12 个唯一 capability ID，不能填写 Agent 身份、用户、tenant、roles、权限、父 Run 或真实预算。未知 ID、跨 Worker 选择和未知 Worker 均明确拒绝，不做猜测或兜底。
6. Resolver 输入中的角色来自可信 `RunContext`，先与 Catalog 的服务端角色规则和 Agent 白名单求交；返回按稳定 ID 排序。本层只是候选预过滤，未来真正执行仍由 Registry、PermissionGuard 和 Harness 重新否决。
7. 对模型返回的是独立 `ResolvedCapability`，不含内部角色、Worker 所有权、timeout、data scope、Schema 类、tenant、路径、SQL、Storage Key、密钥或真实预算；Tool 参数 Schema 会移除 title/description/examples 等非必要注解。
8. 参数 Schema 必须是 `additionalProperties=false` 的对象，并限制 128 个键、128 个列表项、12 层、65536 字节和有限 JSON；任何层级的属性名都拒绝可信身份、权限、运行 ID、真实预算、SQL、路径、Storage Key、秘密、Token、堆栈或原始异常。
9. Catalog 保存和取回定义时都深拷贝，外部修改嵌套参数字典不能篡改已登记能力；重复能力 ID、重复 Agent Definition、Agent 引用不存在 Tool 或与 Tool 所有权不一致均在装配时失败。

### 23.3 修改文件与职责

- 新增 `app/capabilities/contracts.py`：定义版本化 Capability 类型、实现状态、内部定义、模型选择、安全投影、稳定结果与有界参数 Schema；
- 新增 `app/capabilities/catalog.py`：把既有 M1/M2 Tool Registry 适配为不可变 Catalog，并登记两个声明态 Agent capability；
- 新增 `app/capabilities/resolver.py`：使用服务端 Agent Definition、可信角色和内部白名单确定性筛选，拒绝未知、越权或未实现能力；
- 新增 `app/capabilities/__init__.py`：只建立包边界，不提前公开导出尚未形成稳定外部 API 的类型；
- 新增 `app/agents/definitions.py`：冻结 Business Data/Knowledge 的职责、能力集合、Evidence 来源、完成标准和输入输出合同，但不创建 Worker 实例；
- 新增 `tests/unit/test_capability_resolver.py`：覆盖精确 Registry 适配、类型/版本、Agent Definition、角色预过滤、候选上限、稳定排序、伪造/越权/未实现拒绝、敏感元数据、参数边界与不可变性；
- 修改本记录、M2 阶段入口和项目总看板：同步实际授权、TDD、验证、边界、风险和下一停止点；
- 没有修改现有 Tool Registry、PermissionGuard、Harness、`app/agents/__init__.py` 或任何公开 API。

### 23.4 完整调用链位置

本步实际建立但尚未由公开请求调用的内部链是：

```text
前端 / API /公开 Schema（不经过、不修改）
→ 未来 Agent（本步只有声明态 Definition，没有实例）
→ Capability Resolver（本步核心）
→ Capability Catalog（本步核心）
→ 既有 Tool Registry 元数据（只读取和适配）
→ Harness / Tool 执行（不调用、不修改）
→ Service / Repository / Model（不经过）
→ PostgreSQL / pgvector / Storage / 外部 Provider（不经过）
```

因此本步的输入是可信运行角色、服务端选定的 Agent ID 和有界 capability ID；输出只是可序列化的安全能力说明，不是可调用函数、Tool 对象、权限授权书或执行结果。

### 23.5 TDD 与实际验证

先新增测试并实际运行。RED 在测试收集阶段报 `ModuleNotFoundError: No module named 'app.agents.definitions'`，结果为 `1 error`，证明所需生产合同尚不存在。最小实现后的第一次运行为 `11 passed, 1 failed`；失败不是生产权限缺口，而是角色预过滤测试临时定义了 `owner_worker`，却仍沿用 Catalog 中只归属 `business_data` 的 Tool。保留 Resolver 的所有权一致性检查，只修正测试夹具的服务端所有者后，聚焦测试为 `12 passed`。

最终验证结果：

- M2-21.2 聚焦测试：`12 passed in 1.55s`；
- 与 M2-21.1、Agent Tool、文件/Evidence Tool 和权限合同的相邻回归：`61 passed in 1.84s`；
- 完整单元测试：`743 passed, 2 skipped in 25.54s`；
- `ruff check app tests scripts`：`All checks passed`；
- 六个本步新增文件的 `ruff format --check`：`6 files already formatted`；
- `mypy app`：`Success: no issues found in 127 source files`；
- `compileall`：通过；`pip check`：`No broken requirements found`；
- `git diff --check`：通过，只有工作区既有 LF/CRLF 转换提示；
- 全正式范围 `ruff format --check app tests scripts` 仍只发现未由本步修改的 `tests/integration/test_document_chunk_set_migration.py` 有 1 处既有格式差异，结果为 `1 file would be reformatted, 262 files already formatted`。为保留用户工作区和单步边界，没有顺手修改。

本步没有数据库、Storage、模型、迁移、Seed 或网络行为，因此没有运行 PostgreSQL 集成矩阵、Alembic、Qwen/BGE Smoke 或 Seed 恢复；M2-20 的真实数据验证基线不受本步影响。

### 23.6 能证明与不能证明

以上结果能证明：当前五个真实 Tool 能被稳定、分角色地适配为安全能力摘要；M1 仍精确两个 Tool，M2 累计精确五个 Tool；两类 Worker 的职责和最多五个能力集合已冻结但不会冒充可执行 Agent；模型不能通过选择载荷注入可信作用域；Resolver 会拒绝未知、跨 Worker、角色不符和未实现能力；内部白名单、运行参数和敏感元数据不会进入已覆盖的模型投影；Catalog 的已覆盖嵌套结构不能被外部引用篡改；现有单元合同没有回归。

这些结果不能证明：模型已经会选择正确能力，Agent 已经能接受 Handoff 或执行 Tool，Resolver 的候选就是最终执行授权，Supervisor/Worker/Graph 已存在，Harness 已接入通用 Capability，真实用户问题能完成 L0/L1/L2，数据库/Storage 权限链已在多 Agent 路径运行，或 Qwen、Checkpoint、记忆、API 迁移和 G0～G7 运行行为已经实现。

### 23.7 风险、排查与下一动作

当前主要风险是后续 Provider 绕过 Resolver 使用任意字符串、Runtime 把安全摘要误当作执行授权、实现 Worker 后忘记把 Agent capability 从 `declared` 经过验证地升级为 `available`，或新增 Tool 时只改 Registry/Definition 一侧导致所有权不一致。出现问题时优先按 `原 Tool Registry → Catalog 内部定义 → Agent Definition 白名单 → 可信 RunContext 角色 → CapabilitySelection → Resolver 安全投影 → 后续 Harness 最终授权` 顺序排查；发现元数据泄露时先比较内部 `CapabilityDefinition` 与外部 `ResolvedCapability` 的字段和参数 Schema；发现“有能力却不可用”时先检查实现状态、Agent 所有权和角色交集。

M2-21.2 已完成并停止。下一动作只能是先由用户确认已经理解本步，再单独讨论并授权 M2-21.3；不得自动实现 Planner/Decision/Handoff/Answer Provider 协议、Mock 或任何后续能力。

## 24. 2026-09-05｜M2-21.3 Agent Provider 协议与确定性 Mock

### 24.1 授权、目标与边界

M2-21.2 完成并停止后，用户明确回复“开始M2-21.3”，随后回复“继续”要求完成当前步骤。本步只在 M2-21.1 的严格 Agent 合同与 M2-21.2 的安全 Capability 投影之间建立模型决策接口：Planner 生成 TaskPlan，Decision 一次生成一个 AgentDecision，Handoff Provider 生成不含可信运行字段的草稿，Answer Provider 生成终态 Action，并以确定性离线 Mock 为下一步 Graph 提供可重复测试替身。

本步输入是用户目标、公开有界上下文、Resolver 返回的安全 Worker/Capability 摘要、TaskPlan、公开 Observation 和 WorkerResult。输出是经过程序再次校验的 TaskPlan、AgentDecision、HandoffDraft 或 AgentAnswer。所有请求和响应均可 JSON 序列化；请求不包含 user、tenant、roles、权限、父 Run、真实预算、数据库 Session、Tool 对象、SQL、路径、Storage Key、密钥或原始异常。

本步没有实现 Supervisor/LangGraph、Fake Worker 运行闭环、Worker Runtime、树形预算分配、真实 Business/Knowledge Worker、Tool 执行、Qwen/网络 Provider、Provider 工厂切换、数据库/Checkpoint、记忆、API 迁移、并行调度或 M2-21.4 以后能力。

### 24.2 大白话运行关系与关键设计

本步相当于先统一“经理怎样向模型发四种表、模型交回后怎样验单”，但还没有经理工作流：

```text
M2-21.1 Task/Action/Observation/Result合同
+ M2-21.2 Resolver安全能力摘要
→ PlannerRequest / DecisionRequest / HandoffRequest / AnswerRequest
→ 可替换的四类Agent Provider协议
→ 确定性离线Mock按固定脚本返回结果
→ 程序校验目标、Worker、能力、任务和Evidence/Artifact引用
→ TaskPlan / AgentDecision / HandoffDraft / AgentAnswer
```

主要冻结结论：

1. Provider 合同版本为 `m2-agent-provider-contract-v1`；四类请求都继承严格 `extra=forbid`，单个序列化请求最多 65536 字节，避免把大量历史、Observation 或 Capability Schema 无界塞入模型上下文。
2. `WorkerCapabilityProfile` 把一个安全 Agent 摘要与其 Resolver 批准的 1～5 个非 Agent 能力绑定；最多向 Planner 提供 8 个唯一 Worker。这样不仅能验证“Worker 和 Tool 都存在”，还能拒绝把 Knowledge Tool 分配给 Business Worker 等交叉归属错误。
3. Planner 输出必须保持原目标不漂移；每个已分配任务的负责人必须是本轮可用 Worker，所需能力必须属于该 Worker。Task 数量、DAG、文本和 Evidence 要求继续由 M2-21.1 的 TaskPlan 合同限制。
4. Decision 请求绑定当前计划和 active task；若 CapabilityResolution 带有 `requesting_agent_id`，它必须等于当前任务负责人。输出继续复用五类互斥 AgentAction，执行能力只能来自候选中的 Tool/Skill/Runtime，委派只能指向当前任务和候选 Agent。
5. Decision 声称 `answered` 时，Evidence 数量必须达到当前任务的最低要求，而且引用只能来自输入 Observation/WorkerResult；没有证据时可以诚实返回 `no_evidence`，不能伪装成已回答。
6. 模型只能生成 `HandoffDraft`，其中没有 `handoff_id`、`allocated_budget_ref`、父 Run、可信身份或权限。草稿必须保持原 task、goal、target Worker 和完成标准，Evidence/Artifact ID 只能从输入的安全结果中选择；真实 Handoff ID 和预算引用留给后续 Runtime 注入。
7. `AgentAnswer` 只允许 `finish` 或 `cannot_complete` 两种终态，不能夹带执行、委派或追问 Action；`finish` 的 Evidence/Artifact ID 只能来自输入 WorkerResult。实际 Citation Validator 和事实忠实性仍留到 M2-21.8。
8. 四个 `Protocol` 分别是 `AgentPlannerProvider`、`AgentDecisionProvider`、`AgentHandoffProvider`、`AgentAnswerProvider`，`EngineeredAgentProvider` 组合四者；调用方依赖接口而不是 Mock/Qwen 具体类。
9. `DeterministicAgentMock` 只消费有界 `AgentMockScript`，按固定顺序返回深拷贝并复用正式输出校验器；脚本耗尽会显式失败，不按关键词猜测、不联网、不执行 Tool，也不自动回退旧 M1 Provider。
10. 现有 M1 `ModelProvider.propose_tool_call`、MockProvider、QwenProvider 和工厂行为没有修改；`app.llm` 只新增复合 Agent Provider 与 Mock 的包级导出。

### 24.3 修改文件与职责

- 新增 `app/llm/agent_schemas.py`：定义版本化 Planner/Decision/Handoff/Answer 请求、WorkerCapabilityProfile、HandoffDraft、AgentAnswer、请求总大小和引用池边界；
- 新增 `app/llm/agent_provider.py`：定义四个可替换 Provider Protocol、复合 Protocol，以及计划/行动/交接/回答的程序校验器；
- 新增 `app/llm/agent_mock.py`：定义有界脚本、显式耗尽错误和按顺序返回深拷贝的确定性离线 Mock；
- 新增 `tests/unit/test_agent_providers.py`：覆盖严格 Schema、总大小、Protocol 替换性、Worker-能力归属、目标漂移、未知能力/Worker/Task、互斥 Action、Evidence 最低要求、Handoff 可信字段隔离、终态回答、深拷贝、脚本耗尽、Prompt 注入只作数据，以及 Provider/Mock 不导入网络、数据库或执行层；
- 修改 `app/core/errors.py`：新增统一、安全且不回显模型原始内容的 `AgentProviderOutputError`；
- 修改 `app/llm/__init__.py`：保留全部 M1 导出，只新增 `EngineeredAgentProvider` 与 `DeterministicAgentMock`；
- 修改本记录、M2 阶段入口和项目总看板：同步授权、TDD、验证、边界、风险和下一停止点；
- 没有修改 Capability Catalog/Resolver、Agent Definition、Graph、Harness、Tool、Service、Repository、数据库、配置或公开 API。

### 24.4 完整调用链位置

本步建立的是未来 Agent/LangGraph 内部的模型边界：

```text
前端 / API /公开Schema（不经过、不修改）
→ Agent/LangGraph（本步只定义其未来调用的Provider接口，不实现Graph）
→ Agent Provider请求Schema（本步核心）
→ 确定性Mock（本步核心，不联网）
→ 输出校验器（本步核心）
→ M2-21.1 Task/Action/Handoff/Result合同
→ Harness / Tool / Service / Repository / Model（不经过）
→ PostgreSQL / pgvector / Storage / 外部Provider（不经过）
```

本步 Provider 输入中的 Capability 必须已经由 Resolver 安全投影；输出仍只是计划、行动建议、公开 Handoff 草稿或回答草稿。它既不是权限授权，也没有执行任何 Action。

### 24.5 TDD 与实际验证

先新增 `tests/unit/test_agent_providers.py` 再运行。第一次 RED 在收集阶段报 `ImportError: cannot import name 'AgentProviderOutputError' from 'app.core.errors'`，结果为 `1 error`，证明 Agent Provider 边界尚不存在。最小实现后聚焦测试首次 GREEN 为 `12 passed`。

实现审阅发现扁平 Capability 列表不能验证 Worker 与能力归属，于是先补测试；第二次 RED 在收集阶段报无法从 `app.llm.agent_schemas` 导入 `WorkerCapabilityProfile`，结果为 `1 error`。加入安全 Profile 和 Planner 归属校验后为 `14 passed`。随后补充“Evidence 必需任务不能零证据 answered”的测试，第三次 RED 为 `1 failed, 14 passed`；只增加当前任务 Evidence 最低数量检查，并保留合法 `no_evidence` 后为 `15 passed`。最后增加 Provider/Mock 禁止导入网络、数据库和执行层的静态边界测试，最终聚焦结果为 `16 passed in 1.30s`。

最终验证结果：

- M2-21.3 最终聚焦测试：`16 passed in 1.30s`；
- 与 M2-21.1、M2-21.2、现有 M1 Mock/Qwen Provider、库存 Graph、Agent Tool、Context 和公共 Schema 的相邻回归：`129 passed in 13.85s`；
- 完整单元测试：`759 passed, 2 skipped in 45.63s`；
- `ruff check app tests scripts`：`All checks passed`；
- 六个本步新增/修改代码测试文件的 `ruff format --check`：`6 files already formatted`；
- `mypy app`：`Success: no issues found in 130 source files`；
- `compileall`：通过；`pip check`：`No broken requirements found`；
- `git diff --check`：通过，只有工作区既有 LF/CRLF 转换提示；
- 全正式范围 `ruff format --check app tests scripts` 仍只发现未由本步修改的 `tests/integration/test_document_chunk_set_migration.py` 有 1 处既有格式差异，结果为 `1 file would be reformatted, 266 files already formatted`。该文件在 `git status` 中没有变化，本步没有越界改写。

本步没有数据库、Storage、模型网络、迁移、配置或 Seed 行为，因此没有运行 PostgreSQL 集成矩阵、Alembic、真实 Qwen/BGE Smoke 或 Seed 恢复；M2-20 的真实数据基线不受影响。

### 24.6 能证明与不能证明

以上结果能证明：四类模型职责已有可替换异步协议；请求和响应严格、有界、可序列化；Planner 不能引用未提供或不属于目标 Worker 的能力；Decision 只能产生一个合法 Action，并受当前任务、候选能力、Worker 与 Evidence 最低要求约束；Handoff 模型草稿不能携带可信预算/Run/身份字段或伪造引用；Answer 只能形成终态且不能引用 WorkerResult 之外的 ID；确定性 Mock 可离线复现固定调用序列、返回深拷贝并在脚本耗尽时停止；新 Provider/Mock 模块没有导入网络、数据库、Service、Tool 或 Runtime；现有 M1 Provider 与库存 Graph 单元行为没有回归。

这些结果不能证明：Planner 的语义拆解质量、真实模型对 Prompt 注入的抵抗、回答文字受 Evidence 忠实支持、Citation 已校验、Supervisor 能驱动状态转换、Fake/真实 Worker 能执行、Handoff 已获得真实预算、Harness/Tool 已接入、数据库/Storage 权限已在 Agent 路径运行、真实 Qwen 的结构输出/延迟/错误脱敏、Checkpoint、API 迁移或 G0～G7 场景已经跑通。

### 24.7 风险、排查与下一动作

当前主要风险是后续 Graph 绕过这些校验器直接消费 Provider 输出，真实 Qwen 适配器只做 JSON 解析却不复用目标/能力/引用校验，Runtime 把 `HandoffDraft` 当成可信 `AgentHandoff`，或把 Mock 的顺序脚本误用于并发/生产。出现问题时优先按 `Resolver安全投影 → WorkerCapabilityProfile → Provider请求大小/字段 → 严格Pydantic解析 → validate_*_response → Graph状态 → 后续Runtime可信注入` 排查；Worker 选错时先比较 Profile 归属，引用错位时先比较 Observation/WorkerResult 顶层引用池，Mock 偶发失败时先检查调用顺序和脚本是否耗尽。

M2-21.3 已完成并停止。下一动作只能是先由用户确认已经理解本步，再单独讨论并授权 M2-21.4；不得自动实现 Supervisor LangGraph、Fake Worker 最小闭环或任何后续能力。

## 25. 2026-09-05｜M2-21.4 最小 Supervisor LangGraph 与 Fake Worker 闭环

### 25.1 授权、目标与边界

M2-21.3 完成后，用户明确回复“开始下一步M2-21.4”。本步只把前三步已经冻结的 Task/Action/Observation/Result 合同、Resolver 安全投影和确定性 Mock Provider 串成一条纯内存 Supervisor 控制骨架，并通过测试内 Fake Worker 验证 L0、L1、最小顺序 L2、追问、不支持请求、重复行动与决策步数停止。

本步输入是服务端生成的 Run ID、用户目标、有界公开上下文，以及已经过 Resolver 过滤的 `WorkerCapabilityProfile`；输出是严格、可 JSON 序列化的 `EngineeredAgentState`。Supervisor 只看安全 Worker 摘要和结构化结果，不接收 `RunContext`、身份、权限、真实预算、数据库 Session、Tool 对象、SQL、路径、Storage Key、密钥或原始异常。

本步没有实现 M2-21.5 Worker Runtime、树形预算、父子 Run、Harness 适配、真实 `AgentHandoff` ID/预算注入、Business Data/Knowledge Worker、任何 Tool 调用、数据库/Storage、Checkpoint、Qwen、Citation Validator、API 迁移、恢复/Re-plan、并行调度或后续步骤。两个生产 Agent Definition 继续保持 `declared`；测试内安全 Profile 和 Fake Worker 不会把它们冒充为生产可执行 Worker。

### 25.2 大白话运行关系与关键设计

本步相当于让“经理”第一次按照表单真正走流程，但员工仍是测试替身：

```text
SupervisorRequest（目标＋公开上下文＋Resolver安全Worker摘要）
→ plan：Mock Planner生成Task DAG并再次校验负责人和能力归属
├─ L0直接任务 → compose_answer：Mock Answer Provider直接结束
└─ L1/L2任务 → decide：每次只接收一个Action
   → prepare_handoff：生成不含真实Run/预算的HandoffDraft
   → invoke_worker：测试Fake Worker返回严格WorkerResult/Observation
   → 依赖满足后选择下一个任务，全部完成后compose_answer
→ EngineeredAgentState（公开摘要、双状态、结果、Evidence及资源消耗）
```

主要实现结论：

1. Graph 只有 `plan`、`decide`、`prepare_handoff`、`invoke_worker`、`compose_answer` 五个业务节点；所有分支由严格 Action、任务状态和依赖关系决定，没有按库存/知识关键词写固定意图 `if/else`。
2. `SupervisorRequest` 只接收稳定排序且唯一的 Resolver 安全 Worker Profile；模型计划中的负责人必须存在，所需能力必须属于该 Worker，新计划只能从 `waiting` 状态开始。纯 L0 只允许一个未分配且不需要能力的直接任务。
3. Supervisor 的 Decision 只暴露 Agent 候选；若模型提出 `execute_capability`，或把任务交给与计划负责人不一致的另一个合法 Worker，程序会在 Handoff 前拒绝。Supervisor 因而不能直接调用 Tool，也不能被模型临时改写 Worker 归属。
4. Provider 只产生 `HandoffDraft`。测试 Fake Worker 的窄接口明确不接收 `handoff_id`、`allocated_budget_ref`、父 Run 或可信身份；这些字段只有 M2-21.5 Runtime 建立真实树形预算后才能注入。
5. WorkerResult 必须与 Handoff 的 task/worker 以及计划负责人一致；Observation 中的 Evidence/Artifact 必须由 WorkerResult 顶层继续携带，`answered` 结果必须满足任务最低 Evidence 数量。最终 `answered` 也必须逐任务包含所需 Evidence，实际文字忠实性和引用格式仍留给 M2-21.8。
6. 顺序 L2 按 Task DAG 依赖选择第一个可运行任务；前一 Worker 的结果和 Observation 会进入后一 Decision，全部任务完成后才进入 Answer Provider，Evidence 使用稳定顺序汇总。
7. `ask_user` 把执行状态置为 `waiting_user`、业务结果保持空，并保留当前 task ID；本步只能验证暂停形状，真正跨请求恢复属于 M2-21.11。
8. 服务器固定的 `SupervisorGuardrails` 限制最多 Decision 次数和同一 Action 无进展重复次数。它只是最小控制循环保险，不是 M2-21.5 的根/子 Run 树形预算。
9. Provider/Fake Worker 的未知异常统一变成 `system_error` 和固定公开摘要，原始异常、堆栈、SQL或路径不会进入输出状态。
10. `EngineeredAgentState` 增加有界 `public_context`，并允许在计划阶段安全失败时 `plan=None`；这使规划前失败也能形成合法脱敏结果，不需要伪造一个 TaskPlan。状态仍不保存思维链、Prompt、消息全文或运行时对象。

### 25.3 修改文件与职责

- 新增 `app/agents/supervisor.py`：定义严格 `SupervisorRequest`、服务器侧最小循环护栏、Fake Worker 窄协议和返回安全状态的 `SupervisorAgent` 门面；
- 新增 `app/agents/graphs/engineered_multi_agent.py`：定义五节点 LangGraph、Task DAG 顺序调度、行动/交接/结果校验、Observation/Evidence 汇总、双状态终止和安全异常映射；
- 修改 `app/agents/engineered_state.py`：补充有界公开上下文，并允许规划失败时没有伪造计划；保留全部敏感字段禁入和终态一致性校验；
- 修改 `app/agents/__init__.py` 与 `app/agents/graphs/__init__.py`：在不移除 M1 导出的前提下公开 Supervisor 和新 Graph 的必要入口；
- 新增 `tests/unit/test_multi_agent_graph.py`：覆盖 L0、L1、最小顺序 L2、Observation 后回答、等待用户、无能力 unsupported、计划 Worker 不可被覆盖、异常脱敏、重复/步数终止、确定性/序列化、节点与禁止导入边界；
- 修改本记录、M2 阶段入口和项目总看板：同步本步授权、TDD、验证、边界、风险和下一停止点；
- 没有修改 API、Harness、Tool、Service、Repository、Model、迁移、配置、Seed、Storage 或生产 Agent Definition 状态。

### 25.4 完整调用链位置

本步实际运行链为：

```text
前端 / API（不经过、不修改）
→ SupervisorRequest Schema（本步）
→ 最小 Supervisor LangGraph（本步核心）
→ M2-21.3 确定性 Mock Planner/Decision/Handoff/Answer Provider
→ Resolver 已过滤的安全 Profile（只作为输入，不重新执行可信授权）
→ 测试内 Fake Worker（本步测试替身）
→ WorkerResult / Observation
→ EngineeredAgentState（本步严格输出）
→ Worker Runtime / Harness / Tool / Service / Repository / Model（不经过）
→ PostgreSQL / pgvector / Storage / 外部 Provider（不经过）
```

这里的 Fake Worker 只能证明控制流和数据边界正确，不能证明真实 Worker 能选 Tool 或真实权限链已经运行。

### 25.5 TDD 与实际验证

先新增 `tests/unit/test_multi_agent_graph.py` 再运行。第一次 RED 在测试收集阶段报 `ModuleNotFoundError: No module named 'app.agents.graphs.engineered_multi_agent'`，结果为 `1 error`，证明 Supervisor Graph 尚不存在。最小实现后首轮聚焦结果为 `9 passed`。

代码审阅发现仅验证“目标 Worker 存在”还不足以阻止模型用另一个合法 Worker 覆盖计划负责人，于是先补失败测试；第二次 RED 期望 `invalid_decision`，实际得到 `invalid_handoff`，结果为 `1 failed, 9 deselected`，证明错误委派直到 Handoff 阶段才被阻止。最小修复把计划负责人和所需能力校验前移到 Decision 边界，随后测试通过。再补 Worker 原始异常脱敏用例后，最终聚焦结果为 `11 passed`。

最终验证结果：

- M2-21.4 最终聚焦测试：`11 passed`；
- 与 M2-21.1、M2-21.2、M2-21.3、Agent Tool、Context、公共 Schema 和 M1 库存 Graph 的指定相邻回归：`112 passed in 9.52s`；
- 完整单元测试：`770 passed, 2 skipped in 33.73s`；
- `ruff check app tests scripts`：`All checks passed`；
- 六个本步新增/修改代码测试文件的 `ruff format --check`：全部格式正确；
- `mypy app`：`Success: no issues found in 132 source files`；
- `compileall`：通过；`pip check`：`No broken requirements found`；
- `git diff --check`：通过，只有工作区既有 LF/CRLF 转换提示；
- 全正式范围 `ruff format --check app tests scripts` 仍只发现未由本步修改的 `tests/integration/test_document_chunk_set_migration.py` 有 1 处既有格式差异，结果为 `1 file would be reformatted, 269 files already formatted`。该文件在 `git status` 中没有变化，本步没有越界改写。
- 额外执行根目录 `ruff check . --statistics` 得到 `98 errors`，`ruff format --check .` 得到 `27 files would be reformatted`；正式 `app tests scripts` 检查已经通过，因此其余命中来自仓库既有旧原型目录，外加上述 1 个既有迁移测试格式差异。本步没有越界批量修复这些历史文件。

本步没有数据库、Storage、模型网络、迁移、配置或 Seed 行为，因此没有运行 PostgreSQL 集成矩阵、Alembic、真实 Qwen/BGE Smoke 或 Seed 恢复；M2-20 的真实数据基线不受本步影响。

### 25.6 能证明与不能证明

以上结果能证明：最小 Supervisor 已能用同一组严格合同执行 L0 直接回答、L1 一次委派和按依赖顺序的最小 L2；Worker Observation/Result 会在结束前进入 Answer Provider；等待用户和 unsupported 不会被混成系统失败；执行状态与业务结果保持分离；错误 Worker、Supervisor 直接执行能力、结果错配和 Evidence 缺失会被程序拒绝；重复行动和决策次数都有确定性停止；Mock/Fake 的同输入同脚本输出一致且可 JSON 序列化；已覆盖的异常不会泄露原始运行细节；新 Graph 未导入 API、Runtime、Harness、Tool、Service、Repository 或数据库层；M1 库存 Graph 行为没有回归。

这些结果不能证明：生产 Planner/Qwen 的语义质量、真实 Agent Definition 已可执行、真实 `AgentHandoff`/父子 Run/树形预算、Worker Runtime/Harness/权限/超时重试/Trace/事务、Business 或 Knowledge Worker 的 Tool 自主选择、真实 PostgreSQL/Storage Evidence、答案文字忠实性与 Citation Validator、Checkpoint/恢复/Re-plan、公开聊天迁移、并行或 G0～G7 整链行为已经实现。Fake Worker 返回的是预编排严格结果，不代表真实业务事实。

### 25.7 风险、排查与下一动作

当前主要风险是后续 Runtime 把 `HandoffDraft` 直接当成可信 `AgentHandoff`、真实 Worker 绕过 Harness、树形预算与当前最小 Decision 护栏产生两套相互矛盾的终止逻辑，或恢复时把 `waiting_user` 当成已完成。出现问题时优先按 `SupervisorRequest安全Profile → Planner Task/负责人/依赖 → Decision单一Action → HandoffDraft → Runtime注入父子Run和子预算 → WorkerResult/Observation绑定 → Answer Evidence集合 → EngineeredAgentState双状态` 排查；错误委派先比较 Task assignment，循环先看行动签名和 Decision 次数，信息泄露先检查公开上下文、异常捕获和最终状态 JSON。

M2-21.4 已完成并停止。下一动作只能是先由用户确认已经理解本步，再单独讨论并授权 M2-21.5；不得自动实现 Worker Runtime、树形预算、Harness 适配、真实 Worker 或任何后续能力。

## 26. 2026-09-05｜M2-21.5 Worker Runtime、树形预算、终止管理与 Harness 适配

### 26.1 授权、目标与明确边界

M2-21.4 完成并停止后，用户回复“开始下一步”。依照已经确认的十二步顺序和文档中唯一下一动作，本步只建立可供后续 Business Data/Knowledge Worker 共同复用的运行外壳：把模型可见的 `HandoffDraft` 转换成程序拥有真实 ID 和预算引用的 `AgentHandoff`，按精确 Worker ID 分发，在可信 `RunContext`、子预算、现有 Harness 和独立数据库 Session 边界内执行，并对重复、无进展、超时、异常、资源和子 Trace 做统一收口。

本步输入是 M2-21.3 已校验的 `HandoffDraft`、服务端可信 `RunContext`、已经存在的根 `RunTrace`、程序注入的根/子预算限制、Worker 注册表、Harness 依赖和 Session 工厂；输出是严格 `WorkerResult`、根预算聚合快照和有界内存 `WorkerRunRecord`。身份、租户、角色、市场范围、父 Run、Handoff ID、Worker Run ID 和真实预算都由程序提供，模型无法通过草稿覆盖。

本步没有实现 M2-21.6 Business Data Worker、M2-21.7 Knowledge Worker、任何真实 Tool/Service/Repository 调用、Agent Definition 状态切换、Qwen、PostgreSQL 父子 AgentRun/Checkpoint、API 迁移、对话记忆、Re-plan、Worker 并行调度或后续步骤。`app.models.runtime.AgentRun` 尚无父子字段，因此本步只冻结内存父子 Trace 形状；数据库持久化明确留给 M2-21.9。测试中的 Worker 是运行时替身，SQLite 只验证事务/savepoint语义，不代表真实业务链已经接通。

### 26.2 大白话运行过程与关键设计

可以把本步理解成给“员工”修好统一工位，但还没有招聘真正的库存员工和知识员工：

```text
Supervisor产生HandoffDraft（只有公开任务内容，没有可信身份和真实预算）
→ Dispatcher按完整Worker ID精确找人；找不到就失败，不走旧M1 Graph兜底
→ Termination先检查相同Handoff是否重复
→ AgentBudgetTree原子预留一个子预算，并生成不可猜职责的budget_ref
→ Runtime生成handoff_id、worker_run_id及父/根Run关联
→ 创建有界内存Worker Trace
→ 为这次Worker调用新建独立Session、外层事务和savepoint
→ 绑定服务端可信RunContext并用子预算创建既有Harness
→ 在子预算剩余时间内调用注册Worker
→ 校验返回的task_id/worker_id，记录Evidence并用实测资源覆盖Worker自报数字
→ 完成则提交；等待、失败、超时、重复或无进展则回滚
→ 关闭子预算，归还未消耗的预留容量，形成安全WorkerResult和子Trace
```

主要设计结论：

1. `AgentBudgetTree` 使用同一把重入锁原子维护根消耗、所有开放子预算的剩余预留、唯一任务数、委派数、深度、Evidence 和共享截止时间。分配前一次性校验全部容量，任一维度不够都不产生半个子预算；并发测试证明同一根槽位只会被一个调用占用。
2. 子预算同时限制模型调用、Tool调用、相同Tool参数重复、输入/输出Token、Evidence和时间。子调用的每次实际消耗都会同步计入根预算；子预算关闭只释放未使用预留，已经消耗的资源不会返还。Supervisor四类Provider可通过`BudgetedAgentProvider`在每次调用前扣根模型次数。
3. 现有M1 `ExecutionBudget`行为未改变。`HarnessExecutor`只把具体类型依赖放宽成同一最小`ExecutionBudgetProtocol`，因此既能继续接M1预算，也能接树形子预算；M1预算和Harness相邻回归全部通过。
4. `WorkerDispatcher`只接受唯一注册ID并做精确匹配，不含默认Worker、关键词路由或旧M1 Graph兜底。找不到目标时不会创建Session、Handoff、预算或Trace。
5. `WorkerExecutionContext`是运行期数据类而非Pydantic状态：它包含可信上下文、子预算、Harness、Session和Worker Run关联，明确`can_delegate=False`。这些运行时对象不会进入`EngineeredAgentState`或未来Checkpoint。
6. 每次Worker调用使用新的Session、显式外层事务和嵌套savepoint。只有执行状态为`completed`的严格结果提交；活动态、等待用户、失败、超时、无进展和异常全部回滚。这样后续Worker不能共享同一个易污染的Session。
7. `asyncio.wait_for`使用根/子两级中更短的剩余时间；原始异常、SQL和本地路径统一转换为固定`Worker执行失败。`，不会进入WorkerResult或Trace。Runtime还核对task/worker身份并用预算实测值覆盖Worker声明的`resource_usage`，模型或Worker不能伪造消耗。
8. `WorkerTerminationManager`分别按完整稳定Handoff签名阻止重复委派，并按`task_id + worker_id`累计连续无进展结果；仅改变公开上下文不能绕过无进展上限。它和M2-21.4的Supervisor决策步数护栏职责不同：前者保护真实Worker边界，后者保护Graph控制循环。
9. `WorkerRunRecord`只保存父/根/子Run、Trace、租户、预算引用、任务/Worker、深度、双状态、安全摘要/错误和资源统计，不保存Prompt、消息、思维链、Session、Harness、Tool对象、SQL、路径或原始异常。本步用内存Recorder冻结关联和脱敏合同，不能冒充M2-21.9的持久化审计。
10. 本步没有在配置中拍脑袋写生产预算默认值。测试显式注入有界限制；不同Worker的最终预算初值要在真实Business/Knowledge链和Qwen/BGE延迟有数据后再确定。

### 26.3 修改文件与职责

- 修改 `app/runtime/budget.py`：保留原M1 `BudgetLimits/ExecutionBudget`，新增Harness最小预算协议、根/子Agent预算限制、聚合/子消耗快照、原子`AgentBudgetTree`和Harness兼容的`ChildExecutionBudget`；
- 修改 `app/runtime/executor.py`：将预算构造参数从M1具体类收窄为结构化协议，未改变权限、Registry、Trace或回调执行顺序；
- 新增 `app/agents/runtime/contracts.py`：定义Worker Run父子关联、只存在于运行期的可信执行上下文，以及Worker/Harness/Invoker窄协议；
- 新增 `app/agents/runtime/dispatcher.py`：提供唯一、精确且无兜底的Worker注册与分发；
- 新增 `app/agents/runtime/termination.py`：实现重复Handoff和连续无进展终止策略；
- 新增 `app/agents/runtime/trace.py`：实现严格、可序列化的内存子运行记录，明确作为M2-21.9前的临时持久化缝；
- 新增 `app/agents/runtime/harness.py`：校验可信上下文与根审计Run的tenant/trace一致后，用子预算创建现有Harness；
- 新增 `app/agents/runtime/provider.py`：在四类Supervisor Provider调用前扣减根模型调用预算，不实现任何模型协议或Qwen；
- 新增 `app/agents/runtime/worker.py`：串联精确分发、终止检查、真实Handoff注入、子预算、内存Trace、独立Session、事务/savepoint、上下文绑定、超时、结果验真、实测资源和安全失败；
- 新增 `app/agents/runtime/__init__.py`：公开本步必要运行时入口；
- 新增 `tests/unit/test_agent_budget_tree.py`、`test_worker_runtime.py`、`test_agent_runtime_adapters.py`：覆盖根/子预算、原子并发、深度/任务/委派/重复/Token/Evidence/时间、可信注入、无兜底分发、Session提交回滚、超时、异常脱敏、无进展、Trace及Harness/Provider适配；
- 修改本记录、M2阶段入口和项目总看板：同步授权、RED/GREEN、验证、边界、风险和下一停止点；
- 没有修改API、Tool、Service、Repository、Model、迁移、配置、Agent Definition状态、Seed、Storage或任何M4文件；工作区原有用户文档/M4改动均保留。

### 26.4 完整调用链位置

本步实际执行链为：

```text
前端 / API（不经过、不修改）
→ M2-21.4 Supervisor产生HandoffDraft（合同上游；本步测试直接构造）
→ WorkerDispatcher + WorkerTerminationManager（本步）
→ AgentBudgetTree分配程序拥有的子预算（本步）
→ WorkerRuntime生成AgentHandoff和WorkerRunTrace（本步核心）
→ 独立Session + transaction/savepoint + 可信RunContext绑定（本步核心）
→ WorkerHarnessAdapter → 既有Harness权限/预算/Trace外壳（本步适配）
→ 测试Worker替身返回严格WorkerResult（只验证Runtime，不是真实Worker）
→ 结果身份/Evidence/实测资源校验 → 提交或回滚 → 内存WorkerRunRecord
→ Tool / Service / Repository / Model / PostgreSQL / pgvector / Storage / 外部Provider（不经过）
```

另有一条独立的根预算适配链：`Supervisor Graph调用四类Provider → BudgetedAgentProvider先扣根模型次数 → 既有Mock Provider`。本步只验证扣次和上限，不修改Provider协议，也没有调用真实模型。

### 26.5 TDD、GREEN与工程检查

先新增`test_agent_budget_tree.py`和`test_worker_runtime.py`再运行。第一次RED在测试收集阶段出现2个错误：`AgentBudgetLimits`无法从`app.runtime.budget`导入，以及`app.agents.runtime`模块不存在。这证明树形预算与Worker Runtime确实尚未实现，不是旧功能回归。

最小实现后的首轮聚焦得到`15 passed, 1 failed`：失败用例期望第二个不同Handoff进入Worker，实际只调用一次。排查发现生产代码正确拒绝了重复`budget_ref`，问题是测试夹具把所有后续预算引用固定成同一UUID；修正夹具为“首个ID稳定、后续ID唯一”后，16项通过。随后先为`BudgetedAgentProvider`和Harness适配新增测试，第二次RED在收集阶段报`BudgetedAgentProvider`无法导入；补最小适配器后18项通过。最后补齐独立任务上限与两个线程竞争同一根槽位的原子性测试，最终聚焦为`20 passed`。

最终实际结果：

- M2-21.5聚焦测试：`20 passed in 1.42s`；
- 与M2-21.1至.4、Agent Tool、Context、公共Schema、M1预算/库存Graph和既有Harness Trace的指定相邻回归：`145 passed in 8.88s`；
- 完整单元测试：`790 passed, 2 skipped in 22.02s`；
- `ruff check app tests scripts`：`All checks passed`；
- 13个本步新增/修改代码测试文件的`ruff format --check`：全部格式正确；
- `mypy app`：`Success: no issues found in 140 source files`；
- `compileall`通过；`pip check`为`No broken requirements found`；
- `git diff --check`通过，只有工作区既有LF/CRLF转换提示；
- 全正式范围`ruff format --check app tests scripts`仍只发现未由本步修改的`tests/integration/test_document_chunk_set_migration.py`有1处既有格式差异，结果为`1 file would be reformatted, 280 files already formatted`，本步没有越界改写。

本步没有运行真实PostgreSQL集成矩阵、Alembic、Seed恢复、真实Tool、Storage、Qwen/BGE Smoke或浏览器测试，因为公开/API/真实业务链均未修改。SQLite内存测试实际创建表并验证成功结果提交、原始异常与超时回滚，能证明Session事务控制代码工作，但不能代替后续PostgreSQL真实隔离和故障矩阵。

### 26.6 能证明与不能证明

以上结果能证明：不可信Handoff草稿不能提供或覆盖身份、父Run和真实预算；Runtime能生成唯一Handoff/Worker Run/预算引用并建立父根关联；未知Worker不会兜底或占用资源；根/子预算在已覆盖的顺序与并发竞争下原子扣减，开放子预算不会被根调用抢占，关闭只归还未用配额；深度、任务、委派、调用、重复、Token、Evidence和共享时间均有界；Worker只能收到服务端可信RunContext、不可委派的运行上下文、子预算、Harness和独立Session；成功提交，运行/失败/超时/无进展回滚；结果身份和资源声明受到程序复核；已覆盖异常不会泄露SQL、路径或原始异常；M1预算、库存Graph和Harness Trace合同没有回归。

这些结果不能证明：Business Data或Knowledge Worker已存在或会正确选择Tool；任何真实M1/M2 Tool、权限、Service、Repository、PostgreSQL、pgvector或Storage已经由多Agent链调用；SQLite能覆盖PostgreSQL全部事务/锁语义；父子AgentRun已持久化或可跨进程恢复；生产预算默认值已经调优；真实Qwen会正确规划/行动/回答；Citation Validator、API Gateway、记忆/Re-plan、并行调度或G0～G7整链已经实现。内存Trace在进程重启后会丢失，不能用于生产审计。

### 26.7 风险、排查方向与下一动作

当前主要风险是后续真实Worker绕过`execution.harness`直接调用Service/Repository、把模型自报资源当成可信事实、错误地复用Session、把内存子Trace误当作持久化完成，或在真实Provider耗时下发现测试预算初值不合适。出现问题时优先按`HandoffDraft → Dispatcher精确ID → 重复检查 → 根容量/子预留 → 程序AgentHandoff → WorkerRun父子关联 → 独立Session/savepoint → bind_run_context → Harness权限/预算/Trace → WorkerResult身份/Evidence → 实测资源 → commit/rollback → 子预算close`排查；调用次数不对先看根快照和开放预留，事务污染先看每次Session及终态分支，泄露先检查异常映射和Trace记录，未知Worker被执行则先检查Dispatcher注册表。

M2-21.5 已完成并停止。下一动作只能是先由用户确认已经理解本步，再单独讨论并授权 M2-21.6；不得自动实现 Business Data Worker、调用 M1 Tool、修改Agent Definition为可执行或进入任何后续能力。

## 27. 2026-09-05｜M2-21.6 有界 Business Data Worker 与首条真实 L1 纵向链

### 27.1 授权、目标、输入输出与明确边界

M2-21.5 完成并停止后，用户明确回复“开始下一步M2-21.6”。本步只让第一个真实专业 Worker 上岗：`BusinessDataWorker` 接收 Runtime 生成的可信 `AgentHandoff` 和 `WorkerExecutionContext`，在有界 Action/Observation 循环内让注入的 Decision Provider 每次只选一个行动，自主选择现有 `get_product_spec`、`search_inventory` 中的最小必要 Tool，并返回严格 `WorkerResult`。

本步输入来自上游 Supervisor 的公开任务草稿，以及 Runtime 程序注入的真实 Handoff ID、任务/Worker、父子 Run、可信 `RunContext`、子预算、Harness 和独立 Session；输出是包含双状态、公开摘要、结构化业务结果、Observation、Evidence ID、安全错误和实测资源的 `WorkerResult`。正常执行继续向下经过既有 M1 Tool、Service、Repository 和 PostgreSQL，库存成功还会产生数据库 Evidence。

本步没有实现 Knowledge Worker、两个真实 Worker 的 L2 协作、Qwen、真实语义理解质量、数据库父子 AgentRun/Checkpoint、共享任务板持久化、公开 Agent Gateway/API 迁移、对话记忆、Re-plan、并行、M2-22、M2-23、M4 或 M5。现有 M1 固定库存 Graph/API 继续保留为兼容和回归基线，但 Business Worker 不导入、不嵌套也不兜底调用该 Graph。

### 27.2 大白话运行过程与关键设计

可以把本步理解为让“业务数据员工”在上一部已经建好的受控工位上正式工作：

```text
Supervisor只产生公开HandoffDraft
→ WorkerRuntime注入可信身份、父子Run、真实子预算、Harness和独立Session
→ BusinessDataWorker从Resolver取得且只能看见两个业务Tool
→ 每次模型决策前由Harness扣一次子模型预算
→ Provider一次只能返回execute / ask_user / finish / cannot_complete之一
→ 程序校验Action候选、参数Schema、Handoff公开任务范围和重复签名
→ SQLAlchemy Tool Factory把这次Worker的Session/Harness绑定到既有M1 Tool
→ Tool继续经过Harness权限/市场/预算/Trace
→ Product/Inventory Service → Repository → PostgreSQL
→ ToolEnvelope转换为带capability_id和data的安全Observation
→ Worker校验完成条件、Evidence集合和双状态后返回WorkerResult
→ Runtime按终态提交或回滚，并用实测预算覆盖Worker声明
→ Supervisor汇总WorkerResult并由测试Answer Provider形成终态
```

关键设计结论：

1. Worker 的可执行候选始终来自 `CapabilityResolver.resolve_for_agent(..., "business_data", ...)`，精确限定为 `get_product_spec` 和 `search_inventory`；`search_knowledge` 等跨 Worker 能力在执行前被 Provider 输出校验拒绝。
2. 每个 Decision 仍使用 M2-21.3 的严格 `DecisionRequest/AgentDecision`。Worker 在调用 Provider 前通过 Harness 扣减真实子模型预算，再调用 `validate_decision_response`；最多 4 次决策且相同 Tool+参数不可重复。测试可注入确定性 Provider，但生产 Worker 没有写死自然语言关键词路由。
3. Tool 参数先经过 `BoundedJsonObject`，再严格解析为现有 `GetProductSpecInput` 或 `SearchInventoryInput`。商品查询、市场、仓库和直接 SKU 必须与 Handoff 的必要公开上下文一致；组合查询中库存 SKU 必须等于前一个商品 Observation 实际解析出的 SKU，模型不能换成另一个同租户商品。
4. `SqlAlchemyBusinessCapabilityExecutorFactory` 只负责把当前 Worker 的独立 Session 和 Harness 绑定到现有 M1 `GetProductSpecTool/SearchInventoryTool`、Service、Repository 与 `EvidenceService`。它同时构造两个获准入口，但只有被 Action 选择的 Tool 才会实际调用；真实 ToolCall 记录证明没有多余调用。
5. 成功 Observation 显式保存 `capability_id` 与该 Tool 的公开 `data`，避免以后仅凭字段形状猜测来源；错误 Envelope 映射为 `error/rejected/timeout` 和 `SafeAgentError`，不保存原始异常、SQL、路径或秘密。数据库或预算超时直接形成 `failed + timed_out`，不会再让模型无限尝试。
6. `finish` 只能引用当前 Observation 已产生且完整的 Evidence 集合；伪造、遗漏或额外 Artifact 会被拒绝。`answered` 至少需要一个成功 Observation 且不能混有失败 Observation；`partial` 至少保留一个成功结果；`denied` 必须有真实 `rejected` Observation，模型不能凭空声称权限拒绝。
7. 商品规格 Tool 沿用 M1 既有合同，不创建 Evidence，因此只规格任务可以在有真实结构化 Observation 但 `evidence_ids=[]` 时回答；库存任务仍必须返回数据库 Evidence，外层 Supervisor 的任务 EvidenceRequirement 会再次把关。Handoff 当前没有携带完整 EvidenceRequirement，所以 Worker 内部计划只声明可选数据库 Evidence，不能把这一点误称为统一答案引用已经完成。
8. Business Agent Definition 现在从 `declared` 变为 `available`，因此成为唯一可委派 Agent；Knowledge Definition 仍是 `declared`，不会提前进入可执行候选。现有 Supervisor 与 Worker Runtime 已经满足 Graph/Invoker 接口，无需新增一层适配或修改 Graph 生产逻辑。

### 27.3 修改文件与职责

- 新增 `app/agents/workers/business_data.py`：定义 Worker 循环、4步决策护栏、业务 Capability Executor/Factory 协议、真实 SQLAlchemy/M1 Tool 绑定、参数与任务范围校验、Observation/Result 聚合、Evidence验真和安全终止；
- 新增 `app/agents/workers/__init__.py`：只公开本步 Business Worker 及其必要构造入口；
- 修改 `app/agents/definitions.py`：只把 `business_data` 标为 `available`，保持 `knowledge` 为 `declared`；
- 修改 `app/capabilities/catalog.py`：同步当前“一可执行、一声明态”Worker 的事实说明，不改变五个 Tool 元数据；
- 新增 `tests/unit/test_business_data_worker.py`：覆盖只规格、精确SKU库存、规格加库存、歧义后追问、真实拒绝语义、超时、unsupported、非法参数、跨Worker能力、伪造Evidence、解析后SKU漂移、重复行动、决策上限及旧M1 Graph/知识栈禁止导入；
- 修改 `tests/unit/test_capability_resolver.py`：冻结只有 Business Worker 可委派、Knowledge Worker 仍不可执行的状态；
- 新增 `tests/integration/test_business_data_worker.py`：用确定性 Provider 串起真实 Supervisor、Worker Runtime、Harness、M1 Tool、Service、Repository、PostgreSQL、ToolCall与Evidence，验证三类成功路径和越权拒绝；
- 同步本记录、M2入口和项目总看板；没有修改 API、Graph、M1 Tool/Service/Repository、数据库 Model/迁移、配置、Seed、Storage、知识 Worker或任何M4文件，工作区既有用户文档与M4改动全部保留。

### 27.4 完整调用链位置

本步单元测试验证 Worker 自身边界；真实 PostgreSQL 集成测试实际跑通：

```text
前端 / 公开API（不经过、不修改）
→ SupervisorRequest + M2-21.4 Supervisor LangGraph
→ 确定性测试 Planner/Decision/Handoff Provider（不是Qwen）
→ HandoffDraft
→ M2-21.5 WorkerRuntime / Dispatcher / 子预算 / 独立Session
→ BusinessDataWorker有界Action/Observation循环（本步核心）
→ CapabilityResolver精确投影两个业务Tool
→ WorkerHarnessAdapter + 既有Harness权限/预算/Trace
→ get_product_spec 或 search_inventory（既有M1 Tool）
→ ProductSpecService / InventoryService / EvidenceService
→ ProductRepository / InventoryRepository
→ PostgreSQL商品、规格、库存、AgentRun、ToolCall、Evidence
→ WorkerObservation / WorkerResult
→ Supervisor汇总 + 确定性测试Answer Provider
→ EngineeredAgentState
→ pgvector / Storage / 外部Provider（不经过）
```

旧 M1 `InventoryQueryGraph` 没有进入上述新链，也没有在新 Worker 失败时兜底；现有 M1 Graph/API 只在独立回归测试中运行。

### 27.5 TDD、GREEN、真实集成与工程检查

先新增 `tests/unit/test_business_data_worker.py` 并修改 Capability 状态预期，再实际运行。第一次 RED 在测试收集阶段报 `ModuleNotFoundError: No module named 'app.agents.workers'`，结果为 `1 error in 2.42s`、退出码 1，证明真实 Business Worker 模块确实不存在。

最小实现后的第一次 GREEN 尝试为 `20 passed, 3 failed`：只规格、组合和拒绝三个结果没有正确收口。排查发现完整商品结果在 `business_result` 中重复套两层后超过已经冻结的 JSON 五层深度，同时 Pydantic安全错误对象不能直接哈希去重。修复没有放宽安全上限，而是让 Observation 显式保存 `capability_id + data`、业务结果只增加一层 `product/inventory`，并按错误公开字段去重。随后单元与Resolver共 `23 passed`；补充超时、失败事务Evidence引用清理和真实 PostgreSQL 矩阵后，最终聚焦为 `26 passed in 8.16s`。失败或等待用户会回滚Worker事务，因此对应结果会移除未提交Evidence引用，避免返回已经不存在的ID。

最终实际验证结果：

- Business Worker、Capability状态与真实PostgreSQL聚焦矩阵：`26 passed in 8.16s`；
- M2-21.1至.6、Agent Tool、Context、公共Schema、M1库存Graph、树形预算和Worker Runtime指定相邻单元回归：`145 passed in 6.70s`；
- 新Business链加现有M1真实Agent Tool、库存Graph和公开M1 API的PostgreSQL相邻集成：`22 passed in 20.32s`；
- 完整单元测试：`803 passed, 2 skipped in 28.10s`；
- `ruff check app tests scripts`：`All checks passed`；本步7个新增/修改代码测试文件格式正确；
- `mypy app`：`Success: no issues found in 142 source files`；额外包含两份本步测试时为144个源文件通过；
- `compileall`通过；`pip check`为`No broken requirements found`；`git diff --check`通过，仅有工作区既有LF/CRLF转换提示；
- 全正式范围 `ruff format --check app tests scripts` 仍只发现未由本步修改的 `tests/integration/test_document_chunk_set_migration.py` 有1处既有格式差异，结果为 `1 file would be reformatted, 284 files already formatted`；`git status`确认该文件未修改，本步没有越界改写。

真实矩阵逐项验证：只规格路径只有 `get_product_spec` 一个 ToolCall且0 Evidence；精确库存路径只有 `search_inventory` 一个 ToolCall且1条数据库 Evidence；组合路径按 `get_product_spec → search_inventory` 两个 ToolCall且1条Evidence；DE身份请求FR仓时 Harness记录一个 `denied` ToolCall、0 Evidence，最终业务结果为`denied`。对应根预算实测模型调用为6/6/7/6，Tool调用为1/1/2/1，子预算全部关闭且无开放预留。

本步没有修改 Model 或迁移，因此没有运行或声称 Alembic 变化；没有运行真实 Qwen/BGE/Docling Smoke、Storage、浏览器或前端测试。集成测试使用现有合成演示M1 Seed和真实PostgreSQL，结束后删除本步线程及级联运行记录。

### 27.6 能证明与不能证明

以上结果能证明：Business Worker 已经是唯一可委派真实 Worker；它在严格、有界、可预算的 Action/Observation 循环中只能选择两个M1业务Tool；规格、库存和组合任务会按测试Provider选择最小必要Tool；组合查询不能在解析SKU后偷换目标；未知/知识能力、非法参数、伪造Evidence、重复调用和超限会在下游执行前终止；真实身份、tenant、角色、市场和预算仍来自Runtime/Harness而不是模型；真实PostgreSQL链能产生正确ToolCall、库存125和数据库Evidence，FR越权会在Service前拒绝且无Evidence；执行状态与业务结果分离；新Worker不嵌套旧M1 Planner/Graph，现有M1 Tool、Graph和API回归未退化。

这些结果不能证明：真实Qwen能理解任意自然语言并稳定选择最小Tool，因为本步按计划只使用确定性测试Provider；Knowledge Worker或双Worker L2已经存在；只规格结果已有数据库Evidence或最终引用；Supervisor/Answer Provider已经用真实模型并经过Citation Validator；父子AgentRun已经持久化——当前业务ToolCall和Evidence仍按M2-21.5临时设计关联根AgentRun，子Run只在内存；公开聊天已迁移到Agent Gateway；等待用户可跨请求恢复；Checkpoint、记忆、Re-plan、并行、pgvector/Storage或G0～G7整链已经完成。真实矩阵覆盖当前小型合成数据和DE→FR市场拒绝，不等于全部角色、tenant竞态、数据库锁故障或生产性能已经收口。

### 27.7 风险、排查方向与下一动作

当前主要风险是未来真实 Planner/Handoff Provider 未把必要的 `product_query/sku/market_code/warehouse_code` 放入公开上下文，导致 Worker 为防止目标漂移而拒绝Action；商品规格沿用M1合同没有Evidence，不能用于需要强制引用的统一答案；父子运行尚未落库，业务Tool审计暂时仍挂在根AgentRun；真实Qwen的行动质量、Token、延迟和生产预算默认值还没有数据；Knowledge Worker接入后还要验证两个Worker的Evidence稳定合并与部分成功。

出现问题时优先按 `Supervisor Task/required_capabilities → Handoff公开上下文 → Runtime注入budget_ref/可信RunContext → Resolver两个候选 → Decision单一Action → 参数Schema与目标锁定 → Harness权限/子预算/Trace → M1 Tool → Service → Repository → PostgreSQL → ToolEnvelope → Observation capability_id/data → Evidence全集 → WorkerResult双状态 → Supervisor Answer` 排查。调用数不对先查Decision请求和ToolCall；组合SKU错误先查第一条Observation的解析结果；权限错误先查可信market_scopes和Harness记录；Evidence缺失先查库存ToolCall、事务终态和外层任务EvidenceRequirement；泄露或内部错误先查Envelope到SafeAgentError的转换边界。

M2-21.6 已完成并停止。下一动作只能是先由用户确认已经理解本步，再单独讨论并授权 M2-21.7；不得自动实现 Knowledge Worker、双Worker L2、Qwen、持久化、API、记忆、并行或任何后续能力。

## 28. 2026-09-05｜M2-21.7 Knowledge Worker 与顺序双 Worker L2

### 28.1 授权、目标、输入输出与明确边界

M2-21.6 完成并停止后，用户明确回复“开始下一步M2-21.7”。本步只让第二个专业 Worker 上岗，并把两个真实 Worker 接到已经存在的顺序 Supervisor 骨架：`KnowledgeWorker` 接收 Runtime 生成的可信 `AgentHandoff` 和 `WorkerExecutionContext`，在有界 Action/Observation 循环内从 `search_knowledge`、`read_uploaded_file`、`get_evidence_detail` 三个既有 M2 Tool 中选择一次一个行动；Supervisor 按 Task DAG 顺序运行 Business 和 Knowledge 子任务，稳定合并结果，并在非阻塞知识任务失败时保留已完成的业务结果。

本步输入来自上游 Supervisor 的公开任务与 Handoff 草稿，以及 Runtime 程序注入的真实 Handoff ID、任务/Worker、父子 Run、可信 `RunContext`、子预算、Harness 和 Session；输出仍是冻结的 `WorkerObservation`、`WorkerResult` 与 `EngineeredAgentState`。搜索成功可返回文档 Evidence ID，文件读取返回受控 Artifact ID，Evidence 详情只能读取 Handoff 已允许或本次搜索已经观察到的 Evidence；无获权事实时返回成功执行的 `no_evidence`，而不是伪造答案。

本步没有实现 M2-21.8 真实 Qwen、统一自然语言证据回答或 Citation Validator，也没有实现数据库父子 AgentRun、Checkpoint持久化、公开Agent Gateway/API迁移、完整记忆、恢复/Re-plan、并行、M2-22、M2-23、M4或M5。测试使用确定性 Provider；现有公开聊天行为和旧 M1 固定 Graph 均未修改。

### 28.2 大白话运行过程与关键设计

可以把本步理解为给“知识资料员工”发了一张只允许使用三件工具的工牌，再让主管按依赖顺序先问业务员工、后问知识员工：

```text
Supervisor读取Task DAG并选择当前可运行任务
→ HandoffDraft只携带公开目标、上下文和允许转交的Evidence/Artifact ID
→ Runtime注入真实身份、父子Run、子预算、Harness和Session
→ KnowledgeWorker从Resolver取得且只能看见三个知识Tool
→ 每次Decision先扣模型预算，一次只能返回一个Action
→ 程序校验Tool归属、严格参数、任务范围和重复签名
→ SQLAlchemy Knowledge Factory用同一Session/Harness构造既有M2 Tool
→ search_knowledge：Hybrid/pgvector → Reranker → Context/Evidence
   或 read_uploaded_file：文件Repository → Storage → 有界片段
   或 get_evidence_detail：Evidence Repository → 重新鉴权详情
→ ToolEnvelope转换成公开、安全、可序列化的Observation
→ Worker验真Evidence/Artifact全集和双状态后返回WorkerResult
→ Supervisor继续下一个依赖任务并按任务顺序稳定合并
→ 全成功收口answered；allows_partial的失败保留成功结果并收口partial
```

关键设计结论：

1. `KnowledgeWorker` 的候选始终来自 `CapabilityResolver.resolve_for_agent(..., "knowledge", ...)`，精确限定三个知识 Tool；业务 Tool 或任意未知能力在执行前拒绝。Knowledge Agent Definition 验证后从 `declared` 切换为 `available`，当前两个真实 Worker 均可被 Supervisor 委派。
2. Worker 最多 5 次 Decision，相同 Tool 与参数不能重复；每次仍复用严格 `DecisionRequest/AgentDecision` 和树形子预算。Knowledge Worker 不获得委派能力，不能绕过 Supervisor 自行创建下级 Agent。
3. `search_knowledge.query` 必须与 Handoff 的 `knowledge_query/query` 一致；`read_uploaded_file.file_id` 必须来自 Handoff 允许的 Artifact 或公开 `file_id/file_ids`；`get_evidence_detail.evidence_id` 必须来自 Handoff 明确转交的 Evidence 或本次 Observation。模型不能借通用JSON换租户、换文件或枚举别的Evidence。
4. `SqlAlchemyKnowledgeCapabilityExecutorFactory` 只负责用当前 Worker 的 Session、可信用户和 Harness 装配既有 Retrieval/File/Evidence Repository、Service 和 Tool。它不会直接查询数据库或Storage，也没有新增第二套知识逻辑；真正执行继续由 Harness 做白名单、权限、预算、Trace和错误映射。
5. 既有知识 Tool 的公开结果包含较深的 Context/Locator 结构，直接塞入 Agent 通用JSON会超过 M2-21.1冻结的5层边界。本步没有放宽合同，而是在 Tool→Observation 边界建立白名单投影：保留回答需要的标题、片段、引用、文档/版本/Chunk/File ID等公开字段，并对正文和Locator做长度截断；不保存Storage Key、本地路径、SQL或原始异常。
6. `finish` 必须精确引用全部且仅引用当前 Observation 已产生的唯一 Evidence/Artifact；`answered`要求全部观察成功，`partial`要求同时存在成功和失败，`no_evidence`要求Tool成功但没有可用引用，拒绝/超时/失败会清除可能因事务回滚而失效的引用。执行状态与业务结果继续分开表达。
7. Supervisor 只有在所有任务已终态、失败任务标记为`allows_partial`、且至少已有一个完成并产生`answered/partial`结果时，才会进入统一Answer阶段；`blocks_dependents`失败仍终止整链。最终Action无论业务结果为何都不能引用WorkerResult之外的Evidence/Artifact，避免部分成功分支成为伪造引用旁路。
8. 顺序L2按Task Plan原顺序保存WorkerResult，并按出现顺序去重Evidence/Artifact，因此相同输入下合并顺序稳定。本步明确不并行，不能把该验证解释为已解决并发Session或合并竞态。

### 28.3 修改文件与职责

- 新增 `app/agents/workers/knowledge.py`：定义Knowledge Worker、5步护栏、Capability Executor/Factory协议、三个真实M2 Tool装配、参数与Handoff范围校验、公开结果扁平投影、Observation/WorkerResult聚合、Evidence/Artifact验真及安全终止；
- 修改 `app/agents/workers/__init__.py`：公开Knowledge Worker及其必要构造合同；
- 修改 `app/agents/definitions.py`：将Knowledge Agent标记为`available`，并声明它可产生`document/artifact`两类上层引用；
- 修改 `app/capabilities/catalog.py`：同步五个真实Tool与两个可执行Worker的当前事实说明；
- 修改 `app/agents/graphs/engineered_multi_agent.py`：增加严格的`allows_partial`顺序L2收口条件，并让所有最终Action统一校验Evidence/Artifact只能来自WorkerResult；
- 修改 `app/agents/supervisor.py`：同步当前顺序Supervisor职责说明，不改变公开API；
- 新增 `tests/unit/test_knowledge_worker.py`：覆盖搜索/文件/详情、成功无证据、跨Worker与目标漂移、未转交Evidence、拒绝、超时、追问、重复、决策上限、严格护栏及禁止依赖旧M1 Graph；
- 修改 `tests/unit/test_capability_resolver.py`：冻结两个Worker均可委派及Knowledge只拥有三个M2 Tool；
- 修改 `tests/unit/test_multi_agent_graph.py`：冻结Knowledge失败且允许部分成功时保留Business结果、顺序和引用的终态；
- 新增 `tests/integration/test_knowledge_worker.py`：使用真实PostgreSQL/pgvector/Storage、两个真实Worker和既有Harness/Tool验证三个知识入口、ACL/软删除/旧active、无证据、顺序L2、稳定合并与部分成功；
- 同步本记录、M2入口和项目总看板。没有修改Schema合同、M1/M2 Tool、Service、Repository、Model、迁移、配置、Seed、API、前端、Qwen或任何M4文件；工作区原有用户文档和其他未提交改动均保留。

### 28.4 完整调用链位置

本步不经过前端和公开 API。Knowledge 单Worker的真实搜索链实际为：

```text
测试Supervisor/Runtime入口（确定性Provider，不是Qwen）
→ HandoffDraft
→ WorkerRuntime / Dispatcher / 子预算 / 独立Session
→ KnowledgeWorker有界Action/Observation（本步核心）
→ CapabilityResolver精确投影三个知识Tool
→ WorkerHarnessAdapter + Harness权限/预算/Trace
→ search_knowledge
→ KnowledgeSearchService
→ Dense + Lexical + Hybrid/RRF + Reranker
→ RetrievalRepository / Context Builder / Evidence Repository
→ PostgreSQL + pgvector
→ Context / 文档Evidence
→ WorkerObservation / WorkerResult
```

文件和Evidence读取分支为：

```text
KnowledgeWorker
→ Harness
→ read_uploaded_file → FileReadingService → FileRepository + LocalStorage
或 get_evidence_detail → EvidenceQueryService → EvidenceRepository → PostgreSQL
→ 再次核对tenant/user/roles/market、ACL、软删除和active代次
→ 有界公开Observation
```

顺序L2集成路径为：

```text
Supervisor Task DAG
→ BusinessDataWorker → Harness → M1库存Tool → PostgreSQL数据库Evidence
→ KnowledgeWorker → Harness → M2文件Tool → PostgreSQL/Storage → Artifact
→ ordered WorkerResult merge
→ 确定性Answer Provider
→ completed + answered
```

为保持M2文件矩阵的回滚型测试数据不提交到共享数据库，顺序L2用例通过一个仅存在于测试中的内联Invoker给两个真实Worker注入同一夹具Session；Worker、Resolver、预算、Harness、Tool、Service、Repository、PostgreSQL和Storage仍全部实际执行。Knowledge搜索另有独立用例通过生产`WorkerRuntime`和真实提交的pgvector夹具运行，验证Runtime隔离链。外部Qwen/BGE网络Provider、公开API、Checkpoint和前端均不经过。

### 28.5 TDD、GREEN、真实集成与工程检查

先新增Knowledge Worker与顺序L2失败测试再实际运行。第一次RED在收集阶段报`ModuleNotFoundError: No module named 'app.agents.workers.knowledge'`，退出码1，证明第二个真实Worker模块确实尚不存在，而不是旧实现偶然满足测试。

最小实现后的中间失败暴露了三个真实边界：第一，完整Context Tool结果直接进入`BoundedJsonObject`会超过冻结的JSON深度，因此改为白名单扁平投影而没有放宽合同；第二，测试Provider在搜索后详情阶段重复提交同一Evidence，因此按Observation稳定去重；第三，子预算申请12条Evidence会占满根容量，改为按本任务实际需要申请4条。早期曾为验证跨Session搜索临时提交两份合成文档，最终测试改用自带清理的提交夹具；收尾时又按两个精确UUID、标题前缀和独占引用逐项验证，只删除这两份临时文档及其各自独占的版本、Chunk/Index Set、Evidence、Context和File行，正式Seed与其他数据未触碰。

最终实际验证结果：

- Knowledge Worker、Capability状态、Supervisor部分成功与真实M2 Tool聚焦测试：`40 passed in 12.63s`；
- 两个真实Worker及现有M1/M2知识Tool的选定PostgreSQL/pgvector/Storage相邻集成：`48 passed in 42.30s`；
- 完整单元测试：`812 passed, 2 skipped in 24.51s`；
- `ruff check app tests scripts`：`All checks passed`；本步相关代码/测试的定向格式检查通过；
- `mypy app`：`Success: no issues found in 143 source files`；`compileall`通过；`pip check`为`No broken requirements found`；
- `git diff --check`通过，仅有工作区既有LF/CRLF转换提示；
- 全正式范围`ruff format --check app tests scripts`仍只发现未由本步修改的`tests/integration/test_document_chunk_set_migration.py`有1处既有格式差异，结果为`1 file would be reformatted, 287 files already formatted`，本步没有越界改写；
- 额外根目录`ruff check .`命中旧原型目录的99项既有问题；项目正式`app tests scripts`范围通过，本步没有批量改写或清理不属于本步的历史原型。

本步没有修改Model或迁移，因此没有声称Alembic变化；没有运行真实Qwen/BGE/Docling Smoke、浏览器或前端测试。真实Storage用例使用pytest临时目录，提交型检索夹具和测试线程均在结束时清理；收尾查询确认早期两条精确临时记录已经移除。

### 28.6 能证明与不能证明

以上结果能证明：Knowledge Worker已经成为第二个可委派真实Worker；它在严格、有界、可预算的Action/Observation循环中只能选择三个M2知识Tool；模型不能把查询换成Handoff之外的目标，不能读取未转交的File/Evidence，也不能借Knowledge Worker调用业务Tool；真实PostgreSQL/pgvector链能搜索当前获权且active的Chunk并生成文档Evidence，旧active不会混入；真实Storage文件读取和Evidence详情会重新检查ACL、软删除、来源代次和可信身份；无可用事实能区分为“执行成功但无证据”；深层Tool结果在不放宽Agent状态合同的前提下安全投影；两个真实Worker能按依赖顺序运行并稳定合并数据库Evidence与文件Artifact；允许部分成功的Knowledge失败不会抹掉Business成功，阻塞失败仍不会被错误包装成完成；M1/Business、知识Tool和完整单元合同没有回归。

这些结果不能证明：真实Qwen能理解任意自然语言、制定正确DAG、稳定选择Tool或生成忠实带引用回答，因为全部Agent Provider仍是确定性的测试实现；当前Supervisor的最终文字没有Citation Validator；L2矩阵的Runtime编排使用测试内联Invoker接缝，不能单独证明两个生产独立Session的组合事务策略；父子AgentRun/Checkpoint未持久化，子Trace仍在内存；公开聊天没有迁移到Agent Gateway；跨请求恢复、完整记忆、Re-plan、并行调度、生产延迟/负载以及G0～G7整链尚未完成。小型合成语料中的ACL/软删除/旧active通过，也不等于所有数据库竞态或大规模检索已经收口。

### 28.7 风险、排查方向与下一动作

当前主要风险是未来真实Planner/Handoff Provider遗漏`knowledge_query/file_id`或合法Evidence转交，导致Worker按安全边界拒绝行动；Tool结果投影若新增字段而白名单未同步，可能出现“底层有结果、Observation缺字段”；真实Qwen可能产生重复、目标漂移或伪造引用；Reranker在本机CPU上的延迟会叠加到多Worker总预算；父子运行尚未落库，当前Tool审计仍挂根AgentRun；并行尚未验证，不能共享当前测试Session策略。

出现问题时优先按`Task DAG/失败影响 → Handoff公开上下文及转交ID → Runtime可信RunContext/预算/Session → Resolver三个候选 → Decision单一Action → 参数Schema与查询/File/Evidence范围 → Harness权限/Trace → M2 Tool → Service → Repository/pgvector/Storage → ToolEnvelope → 扁平Observation → Evidence/Artifact全集 → WorkerResult双状态 → Supervisor有用成功/失败影响判断 → 稳定合并 → 最终引用来源校验`排查。搜索无结果先看active代次、Embedding identity、ACL和Context/Evidence原子保存；文件无结果先看公开file ID、File/Document软删除、Artifact Hash和Storage；详情隐藏先看Evidence是否已转交及当前ACL；部分成功错误先看`failure_impact`、任务终态和是否存在真正可用的成功WorkerResult；泄露先查Tool结果投影与SafeAgentError边界。

M2-21.7 已完成并停止。下一动作只能是先由用户确认已经理解本步，再单独讨论并授权 M2-21.8；不得自动实现真实Qwen、统一证据回答/Citation Validator、持久化、API、记忆、并行或任何后续能力。

## 29. 2026-09-05｜M2-21.8 严格 Qwen 与统一证据回答

### 29.1 授权、目标、输入输出与明确边界

M2-21.7 完成并停止后，用户明确回复“开始下一步M2-21,8”，随后回复“继续”。本步只把 M2-21.3 冻结的四类 Provider 协议接到一个严格 Qwen 实现，并补齐最终回答前的统一 Evidence/Citation 边界：Planner 生成 Task Plan，Supervisor/Worker Decision 一次选择一个 Action，Handoff Provider 只生成公开草稿，Answer Provider 只使用程序提供的证据编号生成终态回答；所有模型输出仍需经过服务端合同、Resolver能力归属、参数Schema和Graph终态校验。

本步输入是已经脱敏、有界的 `PlanRequest`、`DecisionRequest`、`HandoffRequest`、`AnswerRequest` 及 Resolver 生成的安全 Worker/Capability Profile；输出是现有严格 `TaskPlan`、`AgentDecision`、`HandoffDraft` 和 `AgentAnswer`。真实用户、tenant、roles、父子Run、权限、预算引用、Session、Tool对象、SQL、Storage Key、本地路径和原始异常都不交给模型生成或覆盖。

本步没有新增 Agent 角色、Capability、Tool、LangGraph节点、Worker Runtime、数据库模型或迁移，也没有实现 M2-21.9 父子 AgentRun/任务板/Checkpoint 持久化、M2-21.10公开Agent Gateway/API迁移、完整记忆与恢复、Re-plan、并行调度、M2-22、M2-23、M4或M5。现有公开聊天与旧M1固定Graph行为不变。

### 29.2 大白话运行过程与关键设计

可以把本步理解为：让千问正式参与“填工作单”，但表格、可选员工、可选工具、参数格式、证据编号以及最终盖章都由程序掌握。

```text
Supervisor / Worker准备安全请求
→ QwenAgentProvider只发送公开目标、已获准Worker/Capability和有界Observation
→ 千问按当前角色的严格JSON Schema返回一个结构化结果
→ Pydantic合同 + 服务端Validator再次校验任务、归属、参数和引用
→ execute_capability才由既有Worker Runtime/Harness走后续真实执行链
→ WorkerResult中的可信Evidence由程序投影为[E1]…[E12]
→ Answer Provider只能在文字中使用这些本地编号
→ 程序把编号映射回原始Evidence UUID并执行Citation Validator
→ Graph在写入终态前再次复核，才允许completed结果输出
```

关键设计结论：

1. `QwenAgentProvider` 通过 OpenAI-compatible `/chat/completions` 发起每次恰好一个请求，使用 HTTPS、Bearer认证、显式超时、`stream=false`、`enable_search=false`、`enable_thinking=false`、温度0和有界输出Token；没有自动重试、模型兜底或互联网搜索。超时、连接/HTTP错误和坏输出只映射为安全公开错误，不回显Key、请求体、响应体、堆栈、SQL或路径。
2. 四种角色使用各自严格 JSON Schema。Planner 的模型传输形状不是开放任务数组，而是服务端为本次最多8个Worker生成的可空 `worker_tasks` 槽位和一个可空直接任务；每个Worker最多一个任务，槽位内能力枚举只来自该Worker的Resolver白名单，任务负责人、分配状态和默认依赖由程序生成。这仍可让一个Worker在自己的有界循环中多次选择Tool，同时减少模型重复拆分和跨Worker能力错配。
3. Qwen当前接口实测会以HTTP 400拒绝Schema关键字`uniqueItems`。Provider只在发往模型的Schema副本中去掉该关键字，唯一性仍由Pydantic与服务端Validator强制；同时移除模型接口不需要的`default`、`format`、`discriminator`，把`const`收紧为单值`enum`，所有对象都要求已声明字段且`additionalProperties=false`。这不是放宽内部合同。
4. Decision Schema按当前 Worker 的每个可执行 Capability动态生成可区分分支，`execute_capability`的`arguments`直接绑定该Capability的真实参数JSON Schema。模型即使返回已知Tool名，也不能带额外参数、身份、权限或预算；解析后仍由`jsonschema`服务端复验，真正执行还必须通过Worker范围锁、Resolver和Harness。
5. Handoff模型输出不含`public_context`，程序把请求中的公开上下文原样复制到草稿，避免模型在交接时改写SKU、市场、File/Evidence范围。真实Handoff ID、父子Run和预算引用继续由Runtime生成。
6. `AnswerEvidenceSet` 按 Task/WorkerResult/Observation的稳定顺序，把最多12个唯一Evidence映射为 `[E1]` 至 `[E12]`；模型只看到公开摘要、来源类型和本地编号，不直接决定Evidence UUID。顶层WorkerResult Evidence必须与Observation实际产出的全集一致，重复、歧义、超过12条或无Observation支撑都会拒绝。
7. Citation Validator只接受ASCII形式的`[E1]`至`[E12]`，拒绝未知、重复、乱序映射、伪造UUID、全角/小写/越界标签；有可用证据且业务结果为`answered`时至少引用一条，`no_evidence`和`cannot_complete`不能伪造引用。Provider层先验一次，Graph终态前再验一次，避免自定义Provider绕过。
8. 商品规格仍沿用M1合同，本身没有Evidence；统一答案允许把它作为已观察的结构化业务结果说明，但不能为它伪造引用。只有库存数据库Evidence或知识文档Evidence等实际Observation来源可进入`[E#]`映射。

### 29.3 修改文件与职责

- 新增 `app/llm/agent_qwen.py`：实现四角色严格Qwen Provider、HTTPS配置校验、每角色动态JSON Schema、模型传输到内部合同的安全转换以及公开错误映射；
- 新增 `app/llm/agent_evidence.py`：构造最多12条的稳定Answer Evidence Set，校验WorkerResult与Observation来源，并执行本地Citation标签到真实Evidence UUID的双向一致性校验；
- 新增 `app/llm/agent_factory.py`：按配置显式创建Qwen或有界Mock Provider，保持纯协议模块不依赖HTTP客户端；
- 修改 `app/llm/agent_provider.py`：统一调用Citation Validator；对Decision中的Capability参数使用该能力的服务端JSON Schema复验；拒绝同一Worker重复任务、空能力已分配任务和直接/Worker任务混合计划；
- 修改 `app/agents/graphs/engineered_multi_agent.py`：AnswerRequest只构造一次，并在Graph终态写入前再次执行统一引用校验；
- 修改 `app/core/config.py` 与 `.env.example`：增加`QWEN_AGENT_MAX_OUTPUT_TOKENS`（默认4096、范围256至8192），并明确它只是Provider单次输出上限，不是真实运行预算；
- 修改 `requirements.txt`：把服务端参数Schema复验所用`jsonschema>=4.26,<5`声明为直接运行依赖；
- 修改 `app/llm/__init__.py`：公开严格Qwen实现和Provider工厂；
- 新增 `tests/unit/test_agent_answer_citations.py`：覆盖跨Worker稳定编号、Observation来源、13条超限、合法映射、伪造/畸形/重复标签、UUID不一致、强制引用和无证据禁引；
- 新增 `tests/unit/test_agent_qwen_provider.py`：使用`httpx.MockTransport`覆盖四角色请求、严格离线JSON Schema、动态Capability参数、Handoff上下文不可改写、Answer标签映射、坏输出、未知能力、额外参数、401/429/503/超时脱敏、工厂和HTTP地址拒绝；
- 新增 `tests/smoke/test_agent_qwen_smoke.py`：默认跳过、显式环境开关运行真实Qwen，验证单Worker规划、Supervisor委派、Handoff、Business行动选择、跨Worker规划和合成Evidence回答；Smoke只提出Action，不实际调用Tool；
- 更新既有Provider、Graph及Business/Knowledge集成测试，使Evidence回答使用统一本地Citation标签并保持旧Mock/M1合同回归；同步本记录、M2入口和项目总看板。未修改Model、Repository、Service、Tool、迁移、Seed、公开API、前端或M4文档。

### 29.4 完整调用链位置

本步不经过前端和公开API。模型决策链位于Schema/Agent之间：

```text
现有内部Supervisor或Worker
→ 严格Provider Request Schema
→ QwenAgentProvider（本步核心）
→ 阿里云OpenAI-compatible HTTPS接口
→ 角色专属JSON Schema结果
→ Pydantic + 服务端目标/能力/参数/引用Validator
→ TaskPlan / 单一Action / HandoffDraft / AgentAnswer
→ 既有Supervisor或Worker继续控制流程
```

当Action是执行能力时，本步没有改变下游链：

```text
execute_capability建议
→ Worker范围与Handoff目标校验
→ CapabilityResolver
→ Worker Runtime子预算
→ Harness权限/白名单/预算/超时/Trace
→ 既有Tool → Service → Repository → PostgreSQL/pgvector/Storage
→ Observation → WorkerResult
```

最终证据回答链为：

```text
有序WorkerResult + Observation中的真实Evidence ID
→ AnswerEvidenceSet稳定生成[E1]…[E12]
→ Qwen Answer只生成文字和本地标签
→ 服务端映射回真实Evidence UUID
→ Provider Citation Validator
→ Supervisor Graph Citation Validator
→ 现有EngineeredAgentState终态
```

外部Provider只在显式真实Smoke经过；单元测试全部使用MockTransport，无网络。数据库、pgvector和Storage没有因本步新增访问；所选相邻集成只验证现有Worker测试回答适配统一引用合同。

### 29.5 TDD、GREEN、真实 Smoke 与工程检查

先新增Answer Citation和Qwen Provider失败测试并实际运行。第一次RED在收集阶段同时报`ModuleNotFoundError: No module named 'app.llm.agent_evidence'`和`ImportError: cannot import name 'create_engineered_agent_provider'`，退出码1，证明统一证据模块和真实Provider工厂尚不存在，而不是旧Mock偶然满足。

最小实现后的真实Smoke暴露并推动了三个合同收紧：第一次模型返回的Task分配状态与Worker冲突且多规划无用回答任务，因此把负责人/分配状态改为程序所有；随后发现跨Worker能力错配，因此让每个Worker槽位只枚举Resolver批准的能力；最后阿里云接口明确以HTTP 400拒绝`uniqueItems`，于是只规范化出站Schema，内部唯一性校验不变。单靠提示词仍会偶发把一个简单库存问题拆给Knowledge Worker，最终改为“每个可用Worker一个可空槽位、每Worker最多一个任务”的有界传输形状，真实Smoke稳定通过。

最终实际验证结果：

- Evidence/Citation、Qwen Provider、既有Provider和Supervisor Graph聚焦回归：`50 passed in 6.63s`；
- 两个真实Worker的选定相邻集成：`21 passed in 23.37s`；
- 显式真实Qwen Smoke：`1 passed in 23.45s`，覆盖单Worker计划、Supervisor委派、Handoff上下文、真实Business行动选择、Business+Knowledge计划和带`[E1]`回答；
- 完整单元测试：`834 passed, 2 skipped in 38.59s`；
- `ruff check app tests scripts`：`All checks passed`；14个本步文件定向格式检查为`14 files already formatted`；
- `mypy app`：`Success: no issues found in 146 source files`；`compileall`通过；`pip check`为`No broken requirements found`；`git diff --check`退出码0，仅有工作区LF/CRLF转换提示；
- 全正式范围`ruff format --check app tests scripts`仍只发现未由本步修改的`tests/integration/test_document_chunk_set_migration.py`有1处既有格式差异，结果为`1 file would be reformatted, 293 files already formatted`，本步没有越界改写；
- 完整集成测试实际为`256 passed, 2 skipped, 1 failed in 176.02s`。唯一失败是范围外的`test_parse_failure_marks_first_index_failed_without_creating_index_set`：测试删除上传文件后预期`DocumentParsingError`，实际未抛出；隔离复跑仍为`1 failed in 7.02s`。该用例不导入本步Provider/Citation模块，本步没有越界修改文档索引Service；因此不能声称完整integration全绿，后续应单独定位其测试数据/Storage状态与解析缓存边界。

本步没有Model或迁移变化，因此未运行或声称Alembic变化；没有运行浏览器、前端、公开聊天API或负载测试。真实Qwen Smoke会消耗少量外部模型额度，测试默认保持跳过，只有显式环境变量和Key同时存在时才运行；日志与测试输出未打印Key。

### 29.6 能证明与不能证明

以上结果能证明：现有四类Agent Provider协议已有一个真实Qwen实现；输入只包含安全Profile和公开状态，输出必须满足角色专属严格Schema；Planner不能伪造负责人/分配状态或把能力跨Worker分配；Decision一次只能产生一个Action且Tool参数要同时通过模型Schema和服务端Schema；Handoff不能改写公开上下文或生成可信预算；模型不能开启搜索、写入身份/权限/父Run/真实预算或直接执行Tool；超时、HTTP错误和坏输出不会把请求、响应、Key或内部异常泄露给外部；最多12条Observation支持的Evidence会稳定映射到本地标签，最终文本、标签和真实UUID必须一致；Graph不会信任Provider已经验过而跳过Citation校验；旧Mock、Supervisor、Worker和M1合同的完整单元回归未退化；真实Qwen在本次代表性输入上能完成计划、委派草稿、Business行动选择和带引用回答。

这些结果不能证明：真实Qwen对任意自然语言、长对话、提示注入、所有G0～G7组合或生产并发都稳定；真实Smoke中的Action没有继续执行Tool，回答Evidence为合成Observation，因此它不是“真实Qwen＋真实数据库/pgvector/Storage”的端到端质量矩阵；商品规格本身仍没有Evidence；完整集成仍有一个范围外失败；Qwen响应Token使用尚未作为可信消费量落入持久化审计；父子AgentRun、共享任务板、Checkpoint、公开Agent Gateway、跨请求恢复、完整记忆、Re-plan、并行和前端引用展示都尚未实现。

### 29.7 风险、排查方向与下一动作

当前主要风险是Qwen在更复杂输入上仍可能过度规划、选择不必要Worker或生成虽然结构合法但语义不佳的参数；服务端严格Schema能阻止越权和形状错误，不能替代M5评估集。出站Schema适配依赖当前Qwen支持的JSON Schema子集，模型或网关升级后可能变化；`jsonschema`依赖需要在所有部署环境安装；统一Citation当前验证“引用来自真实Observation且编号一致”，不能自动证明文字里的每个事实都被所引Evidence充分支持；父子Run尚未持久化，模型调用、任务和引用跨请求不可恢复；完整integration的文档解析失败需要另步处理，不能在本步掩盖。

出现问题时优先按`Provider Factory配置 → HTTPS endpoint/model/key/timeout → 角色Request公开投影 → 动态JSON Schema → HTTP状态/安全错误类别 → Pydantic解析 → Plan Worker槽位与Capability归属 → Decision参数Schema → Handoff原始public_context → Worker/Harness真实执行 → Observation Evidence全集 → AnswerEvidenceSet [E#] → 文本Citation扫描 → UUID映射 → Graph终态复核`排查。模型多派任务先看Worker槽位和任务必要性；400先看Qwen支持的Schema关键字；行动被拒先比Capability参数Schema与Handoff目标锁；引用被拒先核对WorkerResult顶层ID是否精确来自Observation、标签是否ASCII且唯一、回答业务结果是否允许引用；秘密泄露先查HTTP错误映射和日志，不得打印原始payload。

M2-21.8 已完成并停止。下一动作只能是先由用户确认已经理解本步，再单独讨论并授权 M2-21.9；不得自动实现父子AgentRun/共享任务板/Checkpoint持久化、API、记忆、并行或任何后续能力。

## 30. 2026-09-05｜M2-21.9 父子Run、任务板、Checkpoint与答案Evidence持久化

### 30.1 授权、目标、输入输出与明确边界

用户在 M2-21.8 完成并讲解后的连续步骤上下文中回复“开始下一步M2-9”。由于 M2-09 已经完成、已确认十二步顺序的唯一下一动作是 M2-21.9，本轮开始前明确告知按 M2-21.9 执行并给出纠正机会，用户未提出更正。本步只把此前已经运行验证的安全合同固化到 PostgreSQL：一棵根 Supervisor/子 Worker Run 树、一份规范化共享任务板、不可变版本化 Checkpoint，以及最终回答标签到 Evidence UUID 的稳定映射。

本步输入是服务端可信 `CurrentUser`、Thread ID、程序生成的Run/预算引用、严格 `TaskPlan`、`WorkerRunTrace`、`WorkerResult`、`EngineeredAgentState`和`AnswerEvidenceMapping`；输出是数据库中的父子 `AgentRun`、任务与依赖边、Worker安全结果、带版本和哈希的Checkpoint，以及最多12条有序答案Evidence关联。模型不能提供或覆盖tenant、user、Thread、根/父Run、真实预算和权限。

本步没有修改前端、公开聊天API、现有Supervisor规划策略、Worker Action循环、Capability Catalog/Resolver、Tool、Service业务查询、Qwen调用或G0～G7运行行为；没有实现M2-21.10 Agent Gateway/API迁移、M2-21.11跨请求记忆/恢复/Re-plan、M2-21.12并行/完整矩阵，也没有进入M2-22、M2-23、M4或M5。当前内部Supervisor/Worker Runtime仍未自动调用本步持久化Service，该接线必须随公开Gateway迁移和恢复语义在后续步骤单独验证。

### 30.2 大白话运行过程与关键设计

可以把本步理解成给已经会协作的“Agent小组”增加一本不能乱改、不能串公司的正式工作台账：

```text
可信用户和Thread开始一次任务
→ 建立Supervisor根Run，并一次写入TaskPlan的全部任务和依赖边
→ Supervisor给某个Worker分配程序生成的子Run和预算引用
→ Worker提交严格WorkerResult，任务板用版本号防止旧结果覆盖新结果
→ 每个安全恢复点追加一份Checkpoint，不覆盖旧版本
→ 恢复时重新核对tenant/user/thread/root、严格状态Schema和SHA-256
→ 根Run完成后，把[E1]…[E12]稳定映射到同tenant的真实Evidence UUID
```

关键设计结论：

1. 复用现有`agent_runs`而不是另建平行运行表。`run_kind`区分`legacy/supervisor/worker`；旧M1记录由数据库默认成为`legacy`，原有Trace写法不变。根Run的`root_run_id=id`、深度0；Worker必须有不同的根/父/自身ID、Agent ID、Task ID、预算引用和1至8层深度。
2. 根Run保留Trace唯一性；同一执行树的Worker允许共享根Trace ID，通过PostgreSQL部分唯一索引只限制`legacy/supervisor`。父/根关联使用包含tenant、Thread和user的复合自外键，数据库本身拒绝跨身份串联。
3. 任务板把任务节点和依赖边分表保存。复合外键拒绝不存在的依赖，Check拒绝自依赖，PostgreSQL递归Constraint Trigger拒绝多节点循环；TaskPlan进入数据库前仍先经过Pydantic DAG校验，形成应用层与数据库层双重防线。
4. 任务的执行状态和业务结果继续分列并由Check约束相容组合。Worker开始任务时任务版本递增；提交结果必须带`expected_task_version`并锁定行，陈旧版本返回安全冲突，不能静默覆盖。
5. Worker结果只保存严格合同的公开JSON及SHA-256，不保存Prompt、完整思维链、Session、Harness、Tool对象、SQL、Storage Key、本地路径或原始异常。安全错误只落公开code/message。
6. Checkpoint是追加式历史记录，每个根Run从版本1递增；写入前重新构造`EngineeredAgentState`并使用稳定JSON编码，限制262144字节并计算SHA-256。保存以根Run行锁加预期版本防并发覆盖；读取时身份范围、Schema、状态/业务结果和哈希任一不一致都拒绝恢复。
7. 最终答案Evidence要求`[E1]`起连续排列、UUID唯一且最多12条；数据库再以ordinal范围、根内ordinal唯一、根内Evidence唯一和tenant复合外键保证不会串租户或重复。
8. 迁移降级会先检查是否存在任何新式Run、任务、Checkpoint或答案Evidence；存在时明确拒绝丢数据。旧迁移回放通过只保留`run_kind`的server default，避免当前ORM在旧表不存在该列时主动发送新字段。

### 30.3 修改文件与职责

- 修改`app/models/runtime.py`：扩展`AgentRun`父子树字段与复合约束，为`Evidence`增加tenant复合唯一键；新增`AgentTaskRecord`、`AgentTaskDependency`、`AgentCheckpoint`和`AgentAnswerEvidence`四个ORM模型；
- 修改`app/models/__init__.py`与`migrations/env.py`：注册并公开新模型，确保Alembic比较完整Metadata；
- 新增`app/repositories/agent_runtime.py`：提供固定、tenant范围内的Run、任务、Checkpoint和答案Evidence读写，不接受模型生成SQL或开放过滤器；
- 新增`app/services/agent_runtime.py`：执行可信身份检查、父子Run创建、任务版本冲突、Worker结果持久化、Checkpoint稳定序列化/保存/验真和答案Evidence保存/读取；
- 修改`app/schemas/evidence.py`：新增严格`AnswerEvidenceReference/AnswerEvidenceMapping`，冻结连续标签、唯一ID和12条上限；Checkpoint继续直接复用M2-21.1的`EngineeredAgentState`与`app/schemas/agent.py`现有双状态和敏感字段规则，没有复制第二套状态Schema；
- 修改`app/core/errors.py`：新增安全的持久化、Checkpoint版本/不存在和任务版本冲突错误，不暴露SQL、路径或异常；
- 新增`migrations/versions/20260905_0011_engineered_agent_runtime.py`：完成表、列、复合外键、Check、索引、DAG循环Trigger和可拒绝数据丢失的降级；
- 新增`tests/unit/test_agent_runtime_persistence_contracts.py`：覆盖模型形状、无敏感列、答案Evidence去重/连续/12条、Checkpoint稳定序列化和敏感状态拒绝；
- 新增`tests/integration/test_agent_runtime_persistence.py`：在真实PostgreSQL验证父子Run、共享任务板、两类Worker、任务/Checkpoint版本冲突、Checkpoint篡改、跨tenant/user/thread恢复拒绝、Evidence映射和DAG数据库约束；
- 新增`tests/integration/test_agent_runtime_migration.py`：验证0011 upgrade/downgrade、四张新表、Run列、部分唯一索引和Alembic单head；
- 修改`tests/unit/test_runtime_models.py`：把旧“所有Run的trace全局唯一”断言收紧为“legacy/supervisor根Trace唯一，Worker可共享同一执行Trace”，旧M1唯一性仍由部分唯一索引保护；同步本记录、M2入口和项目总看板。

没有修改`app/schemas/agent.py`，因为本步所需Task/Worker/状态双维度和敏感字段边界已经由M2-21.1冻结，直接复用比再造持久化副本更安全。

### 30.4 完整调用链位置

本步不经过前端和公开API，也不调用Qwen、Tool或业务Service。核心链是：

```text
服务端可信CurrentUser + Thread
→ 既有严格Agent Schema / EngineeredAgentState
→ AgentRuntimePersistenceService（身份、版本、哈希和状态一致性）
→ AgentRuntimeRepository（固定查询/写入）
→ SQLAlchemy Model
→ PostgreSQL复合外键、Check、唯一索引和DAG Trigger
```

Worker结果和最终引用分别落库为：

```text
WorkerRunTrace + WorkerResult
→ 子AgentRun + agent_tasks安全结果JSON/版本

AnswerEvidenceMapping [E1]…[E12]
→ 同tenant真实Evidence ID验真
→ agent_answer_evidences稳定ordinal映射
```

当前完整产品链仍停在内部调用边界：`前端（不经过）→ API（不修改）→ Schema（复用/补Evidence映射）→ Agent（不改策略）→ Harness/Tool/业务Service（不经过）→ 本步Persistence Service → Repository/Model → PostgreSQL`。M2-21.10才有权把公开聊天唯一入口接到这套运行与持久化底座。

### 30.5 TDD、GREEN、迁移和工程检查

先新增持久化合同单元测试并实际运行。第一次RED在测试收集阶段报`ImportError: cannot import name 'AgentAnswerEvidence' from 'app.models.runtime'`，退出码1，证明新模型、证据映射和Service尚不存在。最小合同和模型完成后，首次单元运行有1项失败，仅因测试期待中文“敏感”而现有合同使用英文`sensitive`，修正测试为复用既有错误语义后通过。

数据库实现后的第一次聚焦迁移/Service测试为`14 passed`。完整integration随后暴露本步引入的旧迁移兼容失败：数据库降至0011之前时，当前ORM主动发送尚不存在的`run_kind`列；将Python侧default去掉、只保留新数据库server default后，旧`tool_context`迁移回放与本步测试`4 passed`，最终加入任务版本冲突和Checkpoint篡改验证后的聚焦结果为`15 passed in 12.63s`。

最终实际验证结果：

- 指定合同、M1库存Graph、Context、公共Schema、Worker Runtime及本步迁移/Service相邻回归：`94 passed in 7.36s`；
- 完整单元测试：`840 passed, 2 skipped in 27.28s`；
- 完整integration原样首次运行：`258 passed, 2 skipped, 2 failed`；其中一个是本步旧迁移兼容问题并已修复，另一个仍是既有文档解析失败；修复后排除该唯一已知范围外用例的完整integration为`259 passed, 2 skipped, 1 deselected in 219.36s`；
- `ruff check app tests scripts migrations`：`All checks passed`；本步12个代码/测试/迁移文件定向格式检查全部通过；全正式范围格式检查仍只发现未由本步修改的`tests/integration/test_document_chunk_set_migration.py`有1处既有格式差异，本步没有越界改写；
- `mypy app`：`Success: no issues found in 148 source files`；`compileall -q app tests scripts migrations`通过；`pip check`为`No broken requirements found`；`git diff --check`退出码0，仅有工作区既有LF/CRLF转换提示；
- Alembic `current`和`heads`均为`20260905_0011 (head)`；`alembic check`为`No new upgrade operations detected`，证明ORM Metadata与迁移没有漂移；0011空数据`downgrade → upgrade → downgrade → upgrade`实测通过。

本步没有运行真实Qwen/BGE/Docling Smoke、浏览器或前端测试，也没有修改正式Seed。集成夹具使用随机tenant/user/thread并在结束时级联删除；数据库最终保持0011唯一head。

### 30.6 能证明与不能证明

以上结果能证明：旧M1 AgentRun可继续作为`legacy`写入且根Trace仍唯一；Supervisor根Run和Worker子Run能在同一tenant/user/thread及共享Trace下持久化，数据库拒绝非法形状和跨身份关联；任务板能保存最多24个任务的规范化依赖，应用合同与数据库共同拒绝缺失、自依赖和循环；Worker结果只保存严格公开状态，任务旧版本和Checkpoint旧版本不能覆盖新记录；Checkpoint能稳定序列化、限制大小、追加版本、校验身份/双状态/哈希，数据库JSON被篡改后恢复会失败；最终答案只能保存最多12条同tenant、唯一且连续的Evidence映射；迁移可升级、空数据降级且只有一个head；现有M1/Agent合同、Worker Runtime和完整单元回归没有退化。

这些结果不能证明：当前公开请求已经自动创建这些记录，因为Agent Gateway尚未迁移；现有Supervisor/Worker Runtime仍未注入本步Service，完整ToolCall到子Run的生产接线尚未验证；Checkpoint存在不等于跨请求记忆、澄清恢复、撤权重验或Re-plan已经实现；答案Evidence映射只证明身份和编号一致，不证明每句话的事实充分性；任务DAG和行锁在高并发生产负载下的吞吐尚未评估；真实Qwen、RAG质量、并行Worker、G0～G7公开整链、前端引用展示仍不在本步证明范围。完整integration仍有一项范围外文档解析失败，不能声称全量全绿。

### 30.7 风险、排查方向与下一动作

主要风险是后续接线时仍把ToolCall挂到根Run而不是当前Worker子Run；Gateway若在根Run、任务板和首个Checkpoint之间分多次提交，会留下不完整运行；Checkpoint虽然防篡改和串身份，但M2-21.11恢复前仍必须重新验证Capability、Evidence ACL/active代次和文件状态；DAG Trigger保证无环但会增加写入成本；`agent_runs`同时兼容legacy和engineered形状，后续查询必须显式带`run_kind`，不能把旧M1记录误当Supervisor；降级遇到新数据会故意停止，需要先做明确的数据导出/清理方案，不能强制丢弃。

出现问题时优先按`CurrentUser/Thread → root run_kind与复合身份 → parent/root自外键 → TaskPlan合同 → agent_tasks节点 → dependency外键/循环Trigger → task row_version → WorkerResult双状态/安全JSON/hash → Checkpoint expected_version → canonical JSON/SHA-256 → tenant/user/thread/root恢复范围 → Answer Evidence连续ordinal/tenant外键 → Alembic current/heads/check`排查。旧迁移回放报新列不存在时先看ORM客户端default是否被编译进旧表INSERT；恢复失败先区分“身份范围内不存在”“版本冲突”“Schema不合法”和“哈希篡改”，不得向外回显数据库异常。

M2-21.9 已完成并停止。下一动作只能是先由用户确认已经理解本步，再单独授权 M2-21.10 公开 Agent Gateway/API 迁移；不得自动接线公开聊天、实现记忆恢复、并行或任何后续能力。

## 31. 2026-09-07｜M2-21.10 唯一 Agent Gateway、公开 API 迁移与持久化主路径接线

### 31.1 授权、目标、输入输出与明确边界

用户于 2026-09-05 明确回复“开始下一步M2-21.10”，并于 2026-09-07 要求“正式收尾”。本步只把 M2-21.1 至 .9 已经分别验证的部件接成一条公开主路径：现有消息 POST 只进入一个 `AgentGateway`，由它建立可信根Run、调用 Supervisor、按需要运行 Business Data Worker 或 Knowledge Worker、让真实Tool继续经过Harness，并同步父子Run、共享任务板、Checkpoint和最终答案Evidence。旧 M1 固定库存Graph继续保留作内部兼容和回归，但不再被公开路由直接构造，也不充当Gateway失败时的兜底。

本步输入是经过认证的 `CurrentUser`、已验Thread、用户消息、程序配置的真实预算和可替换 Agent Provider；输出仍使用现有聊天响应外壳，同时公开 `execution.route=agent_gateway`、执行状态、独立业务结果、最多5个实际Tool名和最多12条重新授权后的数据库/文档Evidence摘要。模型仍不能提交tenant、user、roles、父Run、权限或真实预算。

本步没有实现跨请求加载Checkpoint、等待用户后的续跑、短期对话记忆、恢复前撤权重验、Re-plan、并行Worker或完整G0～G7公开矩阵；没有新增Capability、Agent Definition、Tool、模型角色、数据库表或迁移；没有修改前端、RAG算法、业务查询、Storage、BGE、Qwen协议、M2-22、M2-23、M4或M5。

### 31.2 大白话运行过程与关键设计

可以把M2-21.10理解成“把已经分别造好的部门接到唯一前台，并把工作流水账真正写入数据库”。以前公开聊天直接找旧库存Graph，所以知识Worker和多Worker虽然内部能运行，用户从公开入口仍用不到。现在流程变成：

```text
用户发送消息
→ API先验证登录身份和Thread归属并保存用户消息
→ AgentGateway用服务端身份创建Supervisor根Run
→ Resolver只暴露当前用户真正可用的Worker和Capability
→ Provider给出严格TaskPlan，Gateway先把任务板落库
→ Supervisor按DAG顺序决定L0直接回答或委派Worker
→ Worker Runtime创建Worker子Run并取得程序预算
→ Business/Knowledge Worker只能经Harness调用自己的真实Tool
→ ToolCall和Evidence记到当前Worker子Run
→ Gateway同步任务双状态、写入Checkpoint和最终答案Evidence映射
→ API保存助手消息并重新验证Evidence可见性后返回原聊天响应
```

根Run在首次模型调用前建立，合法TaskPlan在首个Worker启动前保存，因此审计不会从半路才开始。持久化Trace Recorder把每次Worker委派变成真实子Run，并把子Run的 `RunTrace` 交给Harness，所以ToolCall不会错误挂到Supervisor根Run。公开Evidence返回前仍按当前用户、ACL、软删除和active代次重新授权，不能因为运行时曾经看见过就永久可见。

测试可注入确定性Provider来稳定冻结L0、单Business、单Knowledge、跨Worker和部分成功形状；生产依赖按配置创建既有Engineered Agent Provider。没有“模型失败就偷偷回旧库存Graph”的路径：Provider或运行失败会形成安全终态/HTTP错误，而不是改变执行器。

### 31.3 修改文件与职责

- `app/agents/gateway.py`：新增唯一API侧编排入口，组合Resolver、Supervisor、Worker Runtime、Harness、两个真实Worker和持久化Service；负责根Run、任务板、子Run Trace、Checkpoint、答案Evidence及安全终态映射；
- `app/api/routers/threads.py`：消息POST改为只依赖 `AgentGateway`；移除旧 `InventoryQueryAgent`、`InventoryQueryInput`和M1 Registry的公开直连，保留既有用户/助手消息事务与HTTP外壳；
- `app/api/dependencies.py`、`app/main.py`：组装惰性Reranker、可注入/可配置Provider和Gateway依赖，便于生产配置与确定性集成测试使用同一入口；
- `app/schemas/chat.py`：公开执行路由加入 `agent_gateway`，把执行状态和 `business_outcome`分开，实际Tool上限扩为5，Evidence扩为最多12条并支持严格可区分的数据库/文档摘要；
- `app/services/evidence.py`：公开响应前重新授权并生成混合数据库/文档Evidence摘要；
- `app/services/agent_runtime.py`、`app/repositories/agent_runtime.py`：拆出“先建根Run、再存计划”，增加任务板终态同步和根树实际Tool名读取；旧调用保持兼容；
- `app/agents/runtime/contracts.py`、`trace.py`、`worker.py`及导出：允许持久化Trace Recorder返回真实Worker子Run审计上下文，Worker Runtime据此把Harness ToolCall绑定到子Run；内存测试合同继续兼容；
- `tests/fixtures/agent_gateway_provider.py`：提供严格确定性的Gateway计划/行动/回答脚本，不伪装真实Qwen质量；
- `tests/unit/test_agent_gateway_migration.py`：冻结公开路由不得再导入旧M1 Graph/Registry，并验证新聊天响应合同；
- `tests/integration/test_m1_api.py`：在同一真实HTTP入口验证L0、Business单Tool、Knowledge单Tool、两个真实Worker、部分成功、父子Run、子Run ToolCall、Checkpoint、答案Evidence和原M1错误边界。

本步没有创建迁移；`.1`至`.9`和用户已有设计/M4文档改动均被保留，没有reset、覆盖或清理。

### 31.4 完整调用链位置

本步第一次把此前分段能力接入公开后端整链：

```text
前端（本步不修改）
→ POST /api/v1/threads/{thread_id}/messages
→ Chat Schema / CurrentUser / Thread授权
→ AgentGateway
→ Capability Resolver
→ Supervisor LangGraph
→ Planner / Decision / Handoff / Answer Provider
→ Worker Runtime + 树形预算 + 持久化Trace
→ Business Data Worker / Knowledge Worker
→ Harness
→ M1业务Tool或M2知识Tool
→ 对应Service
→ Repository/Model
→ PostgreSQL / pgvector / LocalStorage（按实际Tool需要）
→ 父子AgentRun / ToolCall / Task / Checkpoint / Evidence持久化
→ 当前权限下Evidence摘要
→ 原聊天响应
```

真实Qwen属于可配置Provider，但本步集成门禁使用确定性Provider，避免外部网络和模型漂移影响合同测试。前端没有改动，也没有浏览器验证。

### 31.5 TDD、GREEN、回归与工程检查

先新增迁移门禁并实际运行RED：`tests/unit/test_agent_gateway_migration.py`首次为`2 failed`。失败一证明公开路由仍包含 `InventoryQueryAgent` 旧直连；失败二证明聊天Schema还不接受 `agent_gateway`、最多5个Tool和独立 `business_outcome`。最小实现后该文件为`2 passed`。

实现过程中分别运行并修正了父子Trace、计划先持久化、文档Evidence夹具与跨Worker测试接缝；最终实际结果如下：

- 本步修改的持久化/Runtime/Schema聚焦测试：`28 passed`；公开API集成文件：`14 passed in 17.22s`；关键相邻单元：`100 passed`；真实M1 API、两个Worker、持久化与迁移选定集成：`26 passed`；
- 完整单元测试：`842 passed, 2 skipped in 41.78s`；
- 完整integration：`264 passed, 2 skipped, 1 failed in 217.00s`。唯一失败仍是范围外既有 `test_parse_failure_marks_first_index_failed_without_creating_index_set`：删除上传源后预期 `DocumentParsingError`，实际未抛出。本步没有修改文档索引Service，未把该失败伪装成通过；
- 正式收尾时第一次组合门禁为`44 passed, 14 errors`，14项都在夹具Seed阶段因Docker Desktop未运行、PostgreSQL `127.0.0.1:5433`连接超时，尚未进入Gateway。恢复既有容器且状态为`Healthy`后，同一命令为`58 passed in 19.62s`，证明是环境停机而非功能回归；没有删除或重建数据卷；
- `ruff check app tests`为`All checks passed`；19个本步文件定向格式检查为`19 files already formatted`；`mypy app`为`Success: no issues found in 149 source files`；`git diff --check`退出码0，仅有工作区LF/CRLF提示；
- 全范围 `ruff format --check app tests`仍只发现未由本步修改的 `tests/integration/test_document_chunk_set_migration.py`有1处既有格式差异，本步没有越界改写。

本步没有模型/迁移变化，因此没有声称新Alembic迁移或真实Qwen API Smoke；数据库最终保持既有0011主线和健康容器。

### 31.6 能证明与不能证明

以上结果能证明：公开消息POST现在只有一个Agent Gateway执行入口，源代码门禁能阻止旧M1 Graph再次直连或成为自动兜底；同一入口可以L0直接回答、只运行Business Tool、只运行Knowledge Tool、顺序运行两个真实Worker，并在允许时保留部分成功；根Run在模型前、计划在Worker前持久化；Worker有真实子Run，Harness产生的ToolCall绑定子Run；任务双状态、Checkpoint、最终答案Evidence和公开消息能形成同一Trace下的审计链；数据库与文档Evidence返回前重新授权；旧M1登录、Thread归属、库存结果、404/409/504和事务边界没有因入口迁移丢失；运行状态与业务结果继续分离。

这些结果不能证明：公开入口上的真实Qwen对任意自然语言都能稳定规划和回答，因为集成门禁使用确定性Provider；不能证明跨请求从Checkpoint恢复、等待用户后的续跑、撤权重验、Re-plan、并行调度、高并发事务隔离或完整G0～G7公开验收；不能证明每个生成事实都被引用充分支持；不能证明前端已经展示多Worker或混合Evidence；完整integration仍有一项范围外文档解析失败，全范围格式仍有一项范围外既有差异。

### 31.7 风险、排查方向与下一动作

当前主要风险是：生产Provider配置错误会让唯一入口安全失败，系统不会再用旧库存Graph掩盖问题；等待用户的状态虽然可落Checkpoint，但M2-21.11之前不会跨请求恢复；恢复时必须重新验证身份、Capability、Evidence ACL/active代次和文件状态；当前Worker仍按DAG顺序执行，并行隔离留给M2-21.12；Qwen语义质量与完整G0～G7仍需要版本化矩阵和M5评估；测试依赖Docker/PostgreSQL，停机时API集成会在Seed阶段统一报连接错误。

出现问题时优先按`认证与Thread归属 → AgentGateway依赖/Provider配置 → 根Run是否先建立 → TaskPlan是否先落库 → Resolver可用Worker/Capability → Supervisor Task DAG → Handoff程序预算 → Worker子Run → Harness RunTrace → ToolCall所属run_id → Tool Service/Repository → 任务板双状态 → Checkpoint版本/hash → Answer Evidence标签/UUID → 当前ACL重新授权 → 助手消息事务`排查。若所有API测试同时在setup失败，先查Docker Desktop、`deep-search-postgres`健康状态和5433端口，不要先改Agent代码；若旧库存Graph重新出现在公开路由，迁移门禁应立即失败；若ToolCall挂根Run，先查持久化Trace Recorder是否把子Run `RunTrace`交给Worker Runtime。

M2-21.10 已正式完成并停止。下一动作只能是先由用户确认已经理解本步，再单独授权 M2-21.11 跨请求记忆、恢复与Re-plan；不得自动开始恢复、并行、完整矩阵、M2-22、M2-23、M4或M5。

## 32. 2026-09-07｜M2-21.11 有界记忆、澄清恢复、重新获权与重复提交保护

### 32.1 授权、目标、输入输出与明确边界

M2-21.10正式收尾后，用户明确回复“接着完成M2-21.11”。本步只让已经会写Checkpoint的公开Agent主路径真正“接着上次做”：保存最多8条安全近期消息和最多2000字符旧消息摘要；第一次缺信息时返回`waiting_user`；下一条消息在同一Thread中领取同一个Supervisor根Run，恢复未完成任务或最多重新规划一次；每次跨请求继续前重新验证当前身份、Capability、Evidence、Artifact和累计预算；同一`request_id`只产生一组确定消息ID和一份当时响应，不能重复建Run、重复写消息或换内容重用。

输入是当前重新认证得到的`CurrentUser`、Thread、客户端`request_id`、新消息、已有不可变Checkpoint和审计记录；输出是同根Run上的新版本Checkpoint、恢复后的严格状态，或者当前请求对应的精确幂等重放。安全记忆只保存脱敏摘要，不保存完整Prompt/Chain-of-Thought、SQL、路径、Storage Key、秘密、Session、Tool对象或原始异常。

本步没有新增Capability、Agent Definition、Worker、Tool、Provider模型操作、LangGraph节点、数据库表或迁移；没有实现Worker并行、完整G0～G7公开矩阵、生产负载、前端、多轮永久画像、M2-22、M2-23、M4或M5。M2-21.12仍需单独授权。

### 32.2 大白话运行过程与关键设计

可以把本步理解成给前台和工作台加上“取号续办”，而不是让Agent变得更聪明：

```text
本次消息带request_id进入唯一消息POST
→ Gateway从当前用户自己的Thread读取少量历史并脱敏
→ 若request_id已经办过：找到该请求当时的Checkpoint并精确重放
→ 若上一根Run正在等用户：锁住Thread，领取同一根Run并追加领取Checkpoint
→ 恢复前按当前登录身份重新检查Capability及所有Evidence/File Artifact
→ 恢复累计模型/Tool/Token/时长/任务/委派预算和旧Tool参数签名
→ 继续原计划；只有“尚无Worker结果的Supervisor澄清”最多允许一次Re-plan
→ 只执行未完成任务，已完成Worker结果不重跑
→ Tool结束后、最终Checkpoint前再次重新获权，防止中途撤权竞态
→ 保存新的不可变Checkpoint，再返回completed或waiting_user
```

关键设计结论：

1. `AgentConversationMemory`只允许最多8条近期消息、2000字符安全摘要和有界计数；构建时最多读取24条本Thread消息，并清理密钥赋值、SQL关键字、本地路径和Traceback。给模型的公开投影不包含turn UUID、用户身份、角色权限或预算字段；遇到多字节长文本时会先缩短摘要、再移除最旧消息，实际验证总JSON仍不超过16384字节。
2. `EngineeredAgentState`新增已处理请求ID、当前请求ID、恢复次数和重规划次数；最多保留16个请求ID、最多恢复4次、最多Re-plan 1次，当前请求ID必须属于已接受集合。它们仍经过严格Schema、Checkpoint大小和SHA-256校验。
3. 新请求开始模型调用前先保存`running`初始Checkpoint；`waiting_user`结果也单独保存；恢复领取再追加一个`running`版本，最终再追加结果版本。因此一次澄清并恢复的实际版本为1初始、2等待、3领取、4完成，旧版本不覆盖。
4. Thread行锁与活动根查询保证同一Thread同一时刻只有一个可领取根；正在运行时重试会安全返回409。请求消息ID由tenant/user/thread/request_id/role确定性生成，Conversation Service只允许完全相同的角色和内容幂等复用。
5. 每个Checkpoint记录`active_request_id`，所以同一根Run后来完成后，重试第一次澄清请求仍返回第一次的`waiting_user`，不会错误返回后来请求的最终答案。Tool名也从该Checkpoint的Observation推导，不读取根Run未来发生的Tool记录。
6. 恢复预算由已验证Checkpoint和真实ToolCall/WorkerRun审计重建；累计时长继续占用根截止时间，旧Tool名加参数签名进入新子预算，恢复后不能用相同参数重新调用来绕过重复限制。Worker开始任务返回真实行版本，完成时不再写死版本2。
7. 身份、角色和市场范围仍只来自每次请求重新认证的`CurrentUser`；Capability Resolver每次重新投影可用Worker/Tool。状态中保留的数据库/文档Evidence和File Artifact在模型恢复前与最终保存前逐项重新授权。撤权时返回安全403，追加`completed + denied`Checkpoint并清空最新状态中的Observation、WorkerResult、Evidence和Artifact，旧答案不会重放。
8. 本步的Re-plan不是无限“再想一次”：只有等待发生在任何Worker完成之前且次数仍为0时才替换尚未执行的任务板；如果已有Worker结果，则保留DAG与已完成结果，只继续未完成任务。新计划仍经过现有Planner、Resolver和Task DAG合同。

### 32.3 修改文件与职责

- `app/schemas/agent.py`、`app/agents/engineered_state.py`：新增严格安全记忆及请求/恢复/Re-plan有界状态；
- `app/services/agent_memory.py`、`app/repositories/conversation.py`、`app/services/conversation.py`：读取获权Thread的小段消息、脱敏压缩，并用确定消息ID幂等落消息；
- `app/runtime/budget.py`：从可信审计恢复累计预算、截止时间和重复Tool签名；
- `app/repositories/agent_runtime.py`、`app/services/agent_runtime.py`：按当前请求定位Checkpoint、锁定领取等待根、替换未执行计划、恢复预算审计、读取真实任务版本；
- `app/agents/graphs/engineered_multi_agent.py`、`app/agents/supervisor.py`：把已领取Checkpoint投影回现有五节点图，区分继续原计划与一次Re-plan；没有新增图节点；
- `app/agents/gateway.py`：统一编排开始/恢复/重放、两次重新获权、累计预算、Checkpoint版本和安全结果；
- `app/schemas/chat.py`、`app/api/routers/threads.py`、`app/schemas/common.py`、`app/core/errors.py`、`app/api/errors.py`：加入可选自动生成的`request_id`、成功态`waiting_user`、确定消息落库和409活动请求冲突；旧客户端不传request_id仍兼容；
- `tests/unit/test_agent_memory_resume.py`、`test_agent_budget_tree.py`及相关Schema/Gateway测试：覆盖记忆限长脱敏、状态次数、恢复预算和响应合同；
- `tests/fixtures/agent_gateway_provider.py`、`tests/integration/test_m1_api.py`、`tests/unit/test_demo_m1.py`：覆盖澄清恢复、精确重放、ID碰撞、恢复前撤权、最终保存前撤权竞态和旧HTTP演示合同；
- 同步本记录、M2入口和总看板；没有修改数据库Model/迁移、Tool/业务Service、Capability/Agent定义、Qwen协议、正式Seed、Storage内容或用户已有M4文档。

### 32.4 完整调用链位置

本步经过公开后端主链，但只扩展跨请求控制外壳：

```text
前端（未修改；可选提交request_id）
→ POST /api/v1/threads/{thread_id}/messages
→ Chat Schema + 当前CurrentUser/Thread授权
→ AgentGateway判断精确重放 / 新根 / 同根恢复
→ Conversation Memory Service → Conversation Repository → PostgreSQL消息尾部
→ Checkpoint Service/Repository → PostgreSQL不可变Checkpoint与任务板
→ 当前Resolver/Capability重新投影 + Evidence/File重新获权
→ 现有Supervisor LangGraph（继续或一次Re-plan）
→ 现有Worker Runtime/树形预算/Harness/Tool/Service/Repository
→ PostgreSQL/pgvector/Storage（只有实际Tool需要时经过）
→ 最终重新获权 → Checkpoint/答案Evidence → 幂等用户/助手消息 → HTTP响应
```

未经过的新层包括前端改造、新Worker、新Tool、新Provider协议、外部模型网络、数据库迁移和并行Dispatcher。

### 32.5 TDD、GREEN、回归与工程检查

先写失败测试并实际运行：`test_agent_memory_resume.py`和预算恢复用例首次在收集阶段产生2个错误，分别无法导入`AgentConversationMemory`和`AgentBudgetRestore`，退出码1，证明原代码确实没有安全记忆与累计预算恢复合同。最小实现后，记忆/预算聚焦先得到`4 passed`；补齐恢复次数和多字节文本总字节边界后，记忆文件最终`5 passed`。

实现接线后的实际验证：

- 记忆、预算、Gateway、Graph、持久化、Agent Tool、Context、M1库存Graph和公共Schema相邻单元：`79 passed in 7.96s`；
- 当前公开API文件：`20 passed in 18.80s`，实际覆盖同一根Run澄清恢复、一次Re-plan、版本`[1,2,3,4]`、第一次响应后续精确重放、重复请求不新增Run/消息、不同内容复用ID返回409、恢复前撤权和Tool后/最终保存前撤权竞态；
- M1 API、持久化及两个真实Worker的选定PostgreSQL相邻集成：`31 passed in 33.24s`；
- 完整单元：`848 passed, 2 skipped in 36.69s`；
- 完整integration：`270 passed, 2 skipped, 1 failed in 214.34s`。唯一失败仍是已连续记录的范围外`test_parse_failure_marks_first_index_failed_without_creating_index_set`：删除上传源后预期`DocumentParsingError`，实际未抛出；本步没有修改文档索引/解析Service，未把它伪装成通过；
- `ruff check app tests scripts migrations`通过；本步文件定向格式全部通过；全范围格式为`315 files already formatted`，仅未修改的既有`test_document_chunk_set_migration.py`仍有1处差异；
- `mypy app`为`Success: no issues found in 150 source files`；`compileall`通过；`pip check`为`No broken requirements found`；`git diff --check`通过，仅有工作区既有LF/CRLF提示；
- Alembic `current`和`heads`均为`20260905_0011 (head)`，`alembic check`为`No new upgrade operations detected`。本步无需新迁移。

测试使用确定性Agent Provider，没有调用真实Qwen/BGE网络；PostgreSQL、真实Business/Knowledge Tool和LocalStorage只在对应集成用例实际经过。测试创建的Thread按既有前缀清理，撤权用例在`finally`恢复文件状态；没有改动正式Seed或清理用户文件。

### 32.6 能证明与不能证明

以上结果能证明：公开入口能把澄清保存为可恢复Checkpoint，并在下一请求用同一根Run恢复；近期消息和旧摘要有界且经过已覆盖的敏感模式脱敏；恢复前会重新认证身份、重新投影Capability并重新授权保留引用；撤权发生在请求之间或Tool后/最终落库前都不会返回旧内容；Supervisor澄清最多Re-plan一次，已有Worker结果不会被Re-plan清掉或重跑；模型、Tool、Token、时间、任务、委派和重复Tool签名跨请求累计；请求重试幂等且请求ID碰撞安全拒绝；Checkpoint追加版本、任务行版本和M1既有合同没有回归。

这些结果不能证明：真实Qwen能稳定理解任意指代或长对话；基于规则的安全摘要能识别所有敏感表达；系统已有长期用户画像或完整对话记忆；高并发下没有任何吞吐瓶颈；独立只读Worker已经并行；完整G0～G7、真实模型整链、负载/性能成本和前端恢复交互已经收口。完整integration仍有一项范围外文档解析失败。

### 32.7 风险、排查方向与下一动作

主要风险是：记忆脱敏是保守规则而非通用DLP，复杂秘密表达仍需M5评估；最多8条近期消息可能丢失很早的指代，安全摘要也不是事实数据库；同步API中途进程崩溃会留下`running`初始Checkpoint，当前同request_id返回409而不是自动接管未知执行，生产级超时租约需后续专门设计；撤权后数据库历史审计记录仍保留旧Evidence/Artifact ID用于审计，但最新可恢复状态和公开响应已清空，任何未来运行查询API仍必须重新授权；恢复预算依赖ToolCall/WorkerRun审计完整性，若数量不一致应安全失败而不是重置预算。

出现问题时优先按`request_id与确定消息ID → owned Thread消息尾部/脱敏 → active_request_id对应Checkpoint → Thread锁与根状态 → Checkpoint版本/hash → 当前CurrentUser/Resolver → Evidence/File ACL → 累计预算与旧Tool签名 → continue/replan模式 → 任务行版本 → Worker/Harness/Tool → 最终再次获权 → 幂等消息`排查。409先查同Thread是否有`running`根或同ID换了内容；恢复错根先查`active_request_id`和tenant/user/thread范围；重复Tool先比数据库`arguments_summary`与预算签名；403先查Evidence active/市场和File/Document软删除/ACL。

M2-21.11已完成并停止。下一动作只能是先由用户确认已经理解本步，再单独授权M2-21.12并行调度与完整G0～G7收口矩阵；不得自动开始并行、矩阵、M2-22、M2-23、M4或M5。

## 33. 2026-09-07｜M2-21.12 独立只读 Worker 有界并行与 G0～G7 收口矩阵

### 33.1 本步目标、输入输出与边界

本步只补上 M2-21 最后一块运行边界和验收证据：输入仍是已验证的 Task DAG、可信 `RunContext`、两个真实 Worker、父子预算和冻结的 G0～G7 样本；输出是“依赖已经满足、属于不同 Worker、且所需能力均为只读”的任务最多同时执行两个，并把完整后端能力映射到可重复运行的验收矩阵。没有新增 Agent、Tool、Provider 协议、数据库表、迁移、前端、M2-22 评估 Runner 或 M4/M5 能力。

大白话运行规则如下：

```text
Supervisor按计划顺序找当前可运行任务
→ 先检查依赖都完成、Worker不同、底层能力只读、并发数不超过2
→ 每个任务仍分别向模型取得一个Action和一份Handoff，不存在“一次吐出多个Action”
→ Worker Runtime并发接收最多两份Handoff
→ 每个Worker分别申请服务端预算、建立子Run和独立Session/事务
→ 各自只经Harness调用自己的Tool
→ 等这一小批都返回后，按原TaskPlan顺序稳定合并Result/Evidence/Artifact
→ 继续DAG、部分成功或统一回答
```

有依赖的任务、`max_parallel_workers=1`或未来非只读能力仍保持顺序执行。并行只改变“可以同时等待两个独立读取任务”，不改变权限、Tool白名单、Evidence上限、失败语义或最终答案校验。

### 33.2 RED、最小实现与过程中发现的问题

先在 `test_multi_agent_graph.py` 增加会合测试：第一个 Fake Worker 必须在 200ms 内等到第二个独立 Worker，否则失败。旧图实际结果为 `1 failed in 10.69s`，只有 `inventory` 进入 Worker，`both_started` 为假，准确证明旧实现仍按单任务串行执行。

最小实现后，Supervisor仍保留原五个节点，只把单个待执行项扩成有界批次：`SupervisorGuardrails.max_parallel_workers`默认2且只能为1～4；候选按TaskPlan稳定顺序选择，必须依赖已完成、Worker不同且全部所需Capability为`none/read`，同时受剩余Decision次数约束。Decision和Handoff仍逐任务取得并逐份验证；只有 `worker.invoke` 使用 `asyncio.gather` 并发，结果按输入顺序合并，因此模型合同仍是“一次Decision一个Action”，不会出现模型控制并发数或预算。

第一次真实Gateway并发测试得到`2 failed`，进一步暴露旧串行配置的真实资源问题：Business与Knowledge子预算各预留最多8条Evidence，同时打开会预留16条，超过根上限12，第二个Worker因此在开始子Run前被安全拒绝。修复没有放宽根预算，而是把服务端角色配额固定为Business最多4条、Knowledge最多8条，并在`AgentGatewayLimits`构造时验证两者模型调用、Tool、Token、Evidence和超时预留能装进同一个根预算。`WorkerRuntime`按精确Worker ID读取不可变预算映射，模型无法提交或覆盖该映射。修复后同一公开成功/部分成功用例为`2 passed in 8.88s`。

最后复核又先增加“同一批一个Worker抛异常时，另一个Worker必须在图返回前完成”的失败测试。第一次为`1 failed in 8.94s`，证明默认`asyncio.gather`会在首个异常出现后立即向上返回，可能留下仍在执行的同批任务。最小修复改为等待整批结果并统一检查异常：所有Worker均已收束后，图才返回脱敏失败；不泄露原始异常，也不把孤儿协程留在响应之后继续运行。

### 33.3 修改文件与职责

- `app/agents/supervisor.py`：增加服务端并发上限，默认最多两个Worker；
- `app/agents/graphs/engineered_multi_agent.py`：在原五节点图内选择独立只读任务批次、并发调用Worker并按计划顺序稳定合并；依赖任务和并发上限1仍顺序执行；
- `app/agents/runtime/worker.py`：支持按Worker ID取得服务端子预算，保持每次调用独立Session、事务、子Run和预算引用；
- `app/agents/gateway.py`：固定Business 4条、Knowledge 8条Evidence子配额并验证全部并行预留不超过根预算12；
- `tests/fixtures/agent_gateway_provider.py`：把公开G4确定性计划改成两个互不依赖的只读任务，并增加只用于测试的双Worker会合Provider；
- `tests/unit/test_multi_agent_graph.py`：冻结真实重叠、稳定结果顺序和`max_parallel_workers=1`退回串行；
- `tests/unit/test_agent_gateway_migration.py`：冻结两个角色子预算之和不能超过根预算；
- `tests/integration/test_multi_agent_matrix.py`：把G0～G7逐项绑定到真实可执行测试，并在公开Gateway/PostgreSQL链验证两个Worker确实重叠、共享根Run/Trace但拥有不同预算引用与ToolCall归属，同时覆盖三种已登记读取角色；
- 同步本记录、M2入口和总看板。没有修改Tool、业务Service、Repository/Model、迁移、Qwen协议、正式Seed内容、前端或用户已有M4文档。

### 33.4 完整调用链位置

```text
前端（未修改）
→ POST /api/v1/threads/{thread_id}/messages
→ Chat Schema + CurrentUser/Thread授权
→ 唯一AgentGateway（无旧M1 Graph兜底）
→ Capability Resolver + Supervisor五节点LangGraph
→ 独立只读Task批次（最多2；有依赖/非只读仍顺序）
→ 每Task一个Decision + 一个HandoffDraft
→ WorkerRuntime并发边界
   ├─ Business子Run + 预算引用 + 独立Session → Harness → M1 Tool → Service → Repository → PostgreSQL
   └─ Knowledge子Run + 预算引用 + 独立Session → Harness → M2 Tool → Service → Repository → PostgreSQL/Storage
→ 按TaskPlan稳定合并WorkerResult/Evidence/Artifact
→ Answer Provider + Citation Validator
→ 任务板/Checkpoint/答案Evidence/消息持久化
→ 当前权限重新授权后的聊天响应
```

真实BGE Smoke另经过本地BGE-M3、pgvector和临时索引/检索链；真实Qwen Smoke因本机没有密钥被显式跳过。前端、浏览器、M2-22评估Runner、M2-23、M2-24、M4和M5均未经过。

### 33.5 验证方法与实际结果

- RED：独立Fake Worker会合用例为`1 failed in 10.69s`，只启动第一个Worker；
- 第二个RED：同批一个Worker抛错时，旧实现没有等另一个Worker完成即返回，结果为`1 failed in 8.94s`；修复后批次会完整收束再给出安全失败；
- GREEN：Supervisor图最终`15 passed in 7.47s`；公开跨Worker成功/部分成功为`2 passed in 8.88s`；并发、Runtime、Gateway预算和公开矩阵聚焦回归为`32 passed in 13.12s`；
- G0～G7、三角色/ACL、Prompt注入、循环/超时、Provider/数据库/Storage/Reranker故障、Evidence及相邻链的选定矩阵为`150 passed in 35.94s`；
- 完整单元测试：`852 passed, 2 skipped in 39.38s`；
- 完整integration：`275 passed, 2 skipped, 1 failed in 218.96s`。唯一失败仍是已连续记录的范围外 `test_parse_failure_marks_first_index_failed_without_creating_index_set`：它删除固定`uploads/2026/08/...`，当前月份Seed文件未被删除，所以预期`DocumentParsingError`未抛出；本步没有修改索引/解析Service，也没有把它伪装为通过；
- 显式真实BGE-M3离线检索Smoke：`1 passed in 42.14s`，报告同时断言`baseline_restored=true`；显式Agent Qwen Smoke：`1 skipped in 1.81s`，原因是当前环境没有`QWEN_API_KEY`且未设置付费调用开关。M2-21.8已保留此前真实Qwen代表性Smoke通过证据，但本步不声称重新调用成功；
- `ruff check app tests scripts migrations`通过；本步8个代码/测试文件格式通过；全范围格式为`316 files already formatted`，仍只有未由本步修改的`test_document_chunk_set_migration.py`一处既有格式差异；
- `mypy app`为`Success: no issues found in 150 source files`；`compileall`通过；`pip check`为`No broken requirements found`；`git diff --check`未发现空白错误，仅报告既有LF/CRLF提示；
- Alembic current/heads均为`20260905_0011 (head)`，`alembic check`为`No new upgrade operations detected`，本步无需迁移；
- 全量测试后重新运行既有幂等`seed_m1 → seed_m2_files → seed_m2_complex_files`。只读复核为10 files、10 documents、10 versions、9 ACL、10个parse/index pending，ChunkSet/IndexSet/Chunk/Context/Evidence/ToolContextLink/AgentRun/ToolCall/AgentTask/Checkpoint/AnswerEvidence均为0；Storage精确10个uploads；`LR-TL-MUSH-OR01 / DE-FRA`可售125。

### 33.6 能证明与不能证明

这些结果能证明：当前两个真实Worker只有在任务独立、Worker不同且能力只读时才进入最多2路并发；并发发生在真实公开Gateway和Worker循环，不只是计时假设；每个Worker拥有不同子Run和预算引用，ToolCall正确归属各自子Run，Session/事务由Runtime逐调用独立创建；根Evidence预算没有因并行放宽；结果与Evidence按计划顺序稳定；同批异常会等待全部Worker收束后再安全返回，一个允许部分成功的Worker失败不会抹掉另一个成功结果；G0～G7均有冻结样本到可执行测试的追踪关系；三种业务读取角色、ACL、注入、循环/超时、主要Provider/数据库/Storage/Reranker故障和引用边界有实际回归结果；M1公开主路径没有退化。

这些结果不能证明：系统支持任意数量Worker或写操作并发；同步Tool/数据库代码在Python事件循环内能获得CPU级并行；高并发、多进程、跨机器或长任务吞吐已经达到生产指标；真实Qwen在本步环境下重新通过；真实Qwen与两个真实Tool的任意自然语言整链质量；M2-22评估Runner、前端引用交互、长期记忆或崩溃租约已经实现。完整integration仍有一项范围外时间依赖测试失败。

### 33.7 风险、排查方向与停止点

并发问题优先按`Task依赖/状态 → required Capability side_effect → Worker是否不同 → max_parallel_workers/剩余Decision → 根预算可用容量 → 角色子预算映射 → 子Run start与任务行版本 → 独立Session/事务 → Harness ToolCall归属 → gather结果顺序 → partial规则`排查。只启动一个Worker时先看任务是否仍有依赖或并发上限是否为1；第二个Worker直接失败先看根预算预留而不是只看实际消耗；数据库冲突先看两个任务是否误用同一task_id/行版本；结果顺序漂移先看是否绕过按draft顺序合并。性能方面，本步只证明“允许重叠”和资源上界，不把本机短样本耗时包装成生产吞吐结论。

M2-21.12及整个M2-21十二步现已完成并停止。下一动作只能是在用户理解并确认本次收口后，单独授权M2-22最小RAG评估集和Runner；不得自动开始M2-22、M2-23、M2-24、M4或M5。
