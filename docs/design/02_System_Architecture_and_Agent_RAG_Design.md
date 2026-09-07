# 跨境电商多 Agent 智能分析平台——系统架构与 Agent/RAG 技术设计

> 文档状态：已确认
> 版本：V1.2
> 约束：本地开发部署、合成业务数据、千问负责推理与多模态、自建 RAG、V1 使用本地文件存储
>
> 2026-09-04范围同步：当前秋招主线为 M2 多 Agent/RAG 闭环 → M4 通用有界深度研究 → M5 评估作品化，M3 多模态暂缓。M4 已确认只新增 Web Research Worker，固定分析与 Markdown 格式化由 Service 完成，V1 不引入 Redis/Celery。M2-21 最新实施顺序已经用户确认，当前处于整体实施前讲解、尚未授权 M2-21.1；分别以[秋招范围方案](05_Autumn_Recruitment_Scope_Adjustment_Plan.md)、[M2-21唯一记录](../progress/M2/records/M2_21_ENGINEERED_MULTI_AGENT_PLAN.md)和[M4正式方案](../progress/M4/records/M4_00_STAGE_PLAN.md)为准。

## 1. 架构目标

系统需要同时满足两类看似冲突的要求：

- 普通库存或规格查询必须快速，不能每次启动复杂多 Agent；
- 选品和市场报告必须能自主分解任务、调用多类数据源并保留证据。

因此采用“确定性工作流控制边界，Agent 在局部做动态决策”的混合架构，不采用完全自由循环，也不为展示多 Agent 而拆分过多角色。

## 2. 核心架构决策

| 编号 | 决策 | 结论 |
|---|---|---|
| ADR-001 | 主模型与视觉模型 | 统一使用阿里云百炼 `qwen3.8-max` |
| ADR-002 | 模型职责 | 只负责意图理解、图片理解、规划、工具选择、推理与生成 |
| ADR-003 | Agent编排 | 显式 LangGraph 状态图，替代不可观察的自由循环 |
| ADR-004 | RAG | 自建索引与查询管线，不依赖 RAGFlow |
| ADR-005 | 向量存储 | PostgreSQL + pgvector |
| ADR-006 | Embedding | BGE-M3，本地运行或后续适配远程服务 |
| ADR-007 | Reranker | bge-reranker-v2-m3 |
| ADR-008 | 业务数据库 | PostgreSQL，与向量和元数据统一管理 |
| ADR-009 | 网络搜索 | Tavily，通过自定义 Provider 接口调用 |
| ADR-010 | 文件存储 | V1本地目录 + Storage抽象，不部署MinIO |
| ADR-011 | 长任务 | V1使用应用内有界执行器＋PostgreSQL任务/租约/Checkpoint；不引入Redis/Celery |
| ADR-012 | 前后端 | Next.js + FastAPI；聊天先同步HTTP，M4任务状态先轮询，SSE按真实体验需求后续评估 |
| ADR-013 | 数据操作 | V1 Agent只允许只读业务查询 |
| ADR-014 | 评估 | 自建分层评估集，指标与回归测试进入代码仓库 |
| ADR-015 | Skill边界 | 当前秋招主线只确认M4一个`cross-border-market-research` Skill；简单原子操作不封装为Skill |
| ADR-016 | Tool边界 | 不以数量为目标，只实现闭环需要的单一职责Tool；单个Agent按任务只获得1至5个 |
| ADR-017 | Harness | 作为运行时护栏逐阶段建设，不设计成新的Agent角色 |
| ADR-018 | MCP | V1不引入；内部能力先使用直接Python接口，外部连接器后续评估 |

## 3. 总体架构

```text
┌────────────────────────────────────────────────────────────────────┐
│ Next.js Web：统一聊天 │ 知识库 │ M4任务进度/结果 │ Evidence        │
└───────────────────────────────┬────────────────────────────────────┘
                                │ HTTPS；M4首版状态轮询
┌───────────────────────────────▼────────────────────────────────────┐
│ FastAPI：Auth/RBAC │ 同一聊天入口 │ 文件/索引 │ 任务状态          │
└───────────────────────────────┬────────────────────────────────────┘
                                ▼
┌────────────────────────────────────────────────────────────────────┐
│ Agent Gateway + Planner + Capability Resolver                      │
│ L0直接回答 │ L1单Worker │ L2 Supervisor多Worker │ M4持久研究任务    │
└───────────────────────────────┬────────────────────────────────────┘
                                ▼
┌────────────────────────────────────────────────────────────────────┐
│ 统一Agent/Worker Runtime + Harness                                  │
│ 身份 │ 权限 │ 白名单 │ 树形预算/终止 │ Trace │ Checkpoint │ Evidence│
└───────────────────────────────┬────────────────────────────────────┘
                                ▼
┌────────────────────────────────────────────────────────────────────┐
│ Business/Knowledge/Web Worker → Tool → 确定性Service/Repository    │
│ M4长任务：应用内有界执行器领取PostgreSQL任务租约                    │
└───────────────┬──────────────────┬───────────────────┬─────────────┘
                ▼                  ▼                   ▼
┌──────────────────────┐ ┌──────────────────┐ ┌──────────────────────┐
│ PostgreSQL + pgvector│ │ Local Storage    │ │ 外部Provider         │
│ 业务/文档/任务/证据/ │ │ 上传/解析产物/   │ │ Qwen / Tavily        │
│ Run/Trace/Checkpoint │ │ Markdown结果     │ │                      │
└──────────────────────┘ └──────────────────┘ └──────────────────────┘
```

## 4. 代码模块边界

建议逐步重构为：

```text
app/
├── api/                 # FastAPI路由、DTO、认证依赖
├── core/                # 配置、异常、日志、安全、枚举
├── models/              # SQLAlchemy ORM
├── schemas/             # Pydantic输入输出Schema
├── repositories/        # 数据访问层
├── services/
│   ├── storage/         # LocalStorage/S3Storage接口
│   ├── documents/       # 文件解析、清洗、分块
│   ├── retrieval/       # 混合检索、重排、Context
│   ├── evidence/        # 证据规范化与引用
│   ├── analysis/        # 首版仅放确定性计算，不包装成Worker
│   └── reports/         # Markdown确定性格式化
├── llm/
│   ├── provider.py      # LLM/Vision统一接口
│   ├── qwen.py
│   └── schemas.py       # 结构化输出
├── tools/               # Agent可调用工具及注册表
├── skills/              # 业务Skill定义、参考资料和模板
├── agents/
│   ├── state.py
│   ├── router.py
│   ├── supervisor.py
│   ├── workers/
│   ├── graphs/
│   └── runtime/         # Harness：上下文、策略、预算、追踪和Skill加载
├── workers/             # M4应用内有界任务执行器（非Celery）
└── evals/               # 数据集、Runner、指标、报告

frontend/
├── app/
├── components/
├── features/chat/
├── features/evidence/
├── features/tasks/
├── features/knowledge/
└── lib/api/

data/
├── source-files/
├── parsed-files/
├── generated-reports/
└── temp/
```

## 5. Agent设计

### 5.1 统一入口不等于每次都启动多个 Agent

最终公开聊天统一经过轻量 Agent Gateway 和 Capability Resolver，但按任务复杂度选择成本不同的路径：L0直接回答，L1只启动一个专业Worker，L2才由Supervisor协调多个Worker。这样库存问题也完成目标理解和能力选择，却不会为了展示多Agent而启动无关角色。

“蘑菇灯库存是多少”通常只需要Business Data Worker调用一次库存Tool；“库存是否满足内部补货规则”才可能需要Business与Knowledge两个Worker。公开入口统一、运行时统一，但实际Worker数量和Tool调用次数按目标自适应。

### 5.2 角色划分

#### Supervisor

职责：

- 判断任务复杂度；
- 生成和调整计划；
- 选择Worker；
- 控制并行与依赖；
- 检查证据是否足够；
- 判断完成/部分成功/追问/失败状态，并形成Answer Evidence Set。

Supervisor不直接访问数据库、文件系统、Tool或内部Service，只能通过结构化Handoff委派Worker并读取规范化结果。最终自然语言交给统一Answer Provider，引用验证通过后才能公开返回。

#### Business Data Worker

- 只看到当前获准的`get_product_spec`和`search_inventory`能力摘要；
- 在有界Action/Observation循环中按子任务选择一个、按需组合或先追问；
- 所有执行都经过Runtime/Harness，不直接访问Service、Repository或数据库；
- 返回结构化Observation、数据库Evidence、未知项和资源消耗，不自行伪造最终事实。

#### Knowledge Worker

- 改写或分解知识查询；
- 应用用户、角色、文档类型和版本过滤；
- 执行混合检索与Rerank；
- 返回引用片段，不直接编造最终结论。

#### Web Research Worker

- 将研究问题拆成可搜索查询；
- 只通过`search_public_web`发现候选，再通过`read_public_source`读取本Run已登记来源；
- Tool经Web Service与Provider调用Fake或Tavily，Worker不直接调用SDK或任意URL；
- 保存标题、URL、发布时间、访问时间、正文片段和Web Evidence；
- 区分官方来源、媒体、零售页面和低可信来源。

#### Analysis Service

- 只承担阶段明确需要、可复现的固定计算；
- 首版M4不实现供应商报价、任意经营指标、Pandas复杂分析或图表；
- Service没有独立目标、上下文、Tool权限或任务生命周期，因此不是Agent。

#### 统一 Answer Provider 与 Report Service

- 统一Answer Provider只根据重新获权的Observation和Answer Evidence Set合成内容；
- Citation Validator阻止伪造、越界或已撤权引用进入成功回答；
- Report Service只做确定性Markdown章节和格式组织，不自行搜索或推理；
- M4首版不生成PDF，也不创建Report Worker。

### 5.3 LangGraph状态

```python
class AgentState(TypedDict):
    task_id: str
    thread_id: str
    user_id: str
    tenant_id: str
    role: str
    original_query: str
    attachments: list[str]
    route: str
    active_skill: str | None
    skill_version: str | None
    allowed_tools: list[str]
    plan: list[dict]
    current_step: int
    tool_budget: int
    evidence_ids: list[str]
    intermediate_results: list[dict]
    assumptions: list[str]
    unknowns: list[str]
    errors: list[dict]
    status: str
    final_answer: str | None
    report_file_id: str | None
```

Agent状态不保存无限增长的原始工具结果。大结果写入PostgreSQL或本地文件，State只保留ID和摘要。

### 5.4 主路由图

```text
公开消息POST
→ authenticate_and_scope
→ Agent Gateway / RunContext
→ Planner + Capability Resolver
   ├─ L0：无需外部事实 → Answer Provider
   ├─ L1：一个专业Worker
   │      → 有界Action/Observation → Harness → Tool
   ├─ L2：Supervisor
   │      → Task DAG → 多个Worker顺序或有界并行
   └─ L3（M4）：创建可恢复研究任务
          → 应用内有界执行器 + PostgreSQL租约/Checkpoint
→ collect_and_reauthorize_evidence
→ sufficient?
   ├─ no：有限replan / ask_user / partial / cannot_complete
   └─ yes
→ Answer Evidence Set
→ 统一Answer Provider
→ Citation Validator
→ 回答或task_id
```

这里不维护`inventory_query/knowledge_query`固定意图枚举。模型只在Resolver返回的真实能力范围内提出目标、子任务和结构化行动，Harness仍由程序执行身份、权限、参数、预算和终止规则。M2-21已确认在公开入口迁移完成后，让旧M1固定库存图退出公开主路径，仅保留内部兼容/回归，且不作为Agent Gateway失败时的自动兜底。

### 5.5 终止条件

每个任务同时受以下条件限制：

- 最大图节点数；
- 最大模型调用数；
- 最大工具调用数；
- 最大累计Token；
- 最大执行时间；
- 连续相同工具与参数不得重复；
- 关键证据已满足且结果已生成；
- 用户取消；
- 不可恢复错误。

阈值从配置读取，不写死在Prompt中。达到上限时返回已完成部分、缺失信息和停止原因。

### 5.6 Human-in-the-Loop

V1业务工具均为只读，仍在以下情况暂停：

- 用户问题存在会明显改变结果的歧义；
- 缺少关键成本、市场或时间范围；
- 用户要求使用未提供的数据；
- 报告包含未经确认的关键假设；
- 用户要求执行超出V1范围的写操作。

## 6. 模型与多模态设计

### 6.1 Provider抽象

```python
class ModelProvider(Protocol):
    async def chat(...): ...
    async def chat_with_tools(...): ...
    async def structured_output(...): ...
    async def analyze_image(...): ...
```

M2-21在通用模型接口上进一步区分严格的Planner、Decision、Handoff和Answer协议，每次只接受经过Schema验证的结构化输出；日常回归使用确定性Mock，显式Smoke使用Qwen实现。环境变量配置Base URL、API Key和模型名称，业务代码不得直接实例化OpenAI客户端。`analyze_image`属于已暂缓的M3能力，不是当前主线完成条件。

### 6.2 千问职责

- 文本与图片意图理解；
- 路由和计划结构化输出；
- Function Calling参数生成；
- 商品视觉属性提取；
- 多证据综合推理；
- 报告语言组织。

### 6.3 千问不负责

- 直接连接数据库；
- 执行SQL；
- 自行读取本地文件路径；
- 直接访问pgvector；
- 决定最终权限；
- 执行文件删除；
- 计算需要精确复现的经营指标。

### 6.4 图片处理

```text
UploadFile
  → MIME/大小/哈希验证
  → LocalStorage保存
  → 图片预处理（方向、尺寸、必要压缩）
  → 读取字节并转Base64 Data URL
  → qwen3.8-max + 严格JSON Schema
  → Pydantic校验/必要时修复一次
  → visual_observation + evidence入库
```

视觉结构至少包含：

- category；
- visible_attributes；
- ocr_text；
- visible_components；
- style_tags；
- usage_scenes；
- quality_findings；
- observations；
- inferences；
- unknowns；
- confidence。

## 7. 工具系统

### 7.1 工具契约

所有工具遵守单一职责，并统一返回：

```json
{
  "status": "success|error|partial",
  "data": {},
  "evidence_ids": [],
  "error": null,
  "meta": {
    "tool": "search_inventory",
    "duration_ms": 83,
    "source_time": "2026-08-27T10:00:00+08:00"
  }
}
```

错误结果也返回给Agent，但必须去除堆栈、密钥、数据库连接串等敏感信息。

### 7.2 当前秋招主线Tool清单

Tool数量不是完成目标。当前只保留已经实现或由正式阶段方案确认、且对核心闭环必要的单一职责能力。

M1业务查询：

- `get_product_spec`
- `search_inventory`

M2知识与文件：

- `search_knowledge`
- `get_evidence_detail`
- `read_uploaded_file`

M3多模态（暂缓，未实现）：

- `analyze_product_images`
- `search_similar_products`

M4公开研究（已确认方案，未实现）：

- `search_public_web`
- `read_public_source`

每个Agent或Skill一次只获得1至5个允许工具，避免把全部工具同时放入模型上下文。固定计算、Markdown组织和文件落盘等确定性步骤由Service直接执行，不包装成让模型自由决定是否调用的Tool。供应商报价、任意经营指标、Pandas图表和PDF不在当前秋招主线。

### 7.3 数据库工具安全

当前V1不提供任意SQL Tool，也不让Business Worker生成SQL。安全链路是：

```text
自然语言问题
 → Capability Resolver只投影获准的业务Tool
 → Business Worker选择get_product_spec或search_inventory
 → Harness校验可信身份、白名单、参数、预算和超时
 → Tool调用固定Service/Repository查询
 → Repository执行tenant/role/market受控SQL
 → 结果与查询范围生成数据库Evidence
```

当前规则：

- 模型不能提交SQL、表名、字段名、连接串或数据库身份；
- V1所有业务Tool只读，写库存、下单、改价等请求返回不支持；
- tenant、角色和market范围来自可信RunContext，不接受模型覆盖；
- Repository使用结构化条件、结果上限和事务边界；
- 敏感字段不进入模型上下文；
- Tool、用户、规范化参数摘要、耗时、结果状态和Evidence写审计。

未来若真实需求要求通用只读查询，必须另行提交SQL AST、白名单、超时和行列级权限方案，不能从当前两个业务Tool暗中扩张。

### 7.4 Tool、Skill、Agent与LangGraph的分工

这四个概念不能混在一起：

| 概念 | 大白话 | 本项目例子 |
|---|---|---|
| Tool | 一次具体动作，相当于“手” | `search_inventory`只查询库存 |
| Skill | 一套可复用的业务操作手册 | 库存风险分析需要查库存、计算周转并给出补货建议 |
| Agent | 承担某类工作的角色 | Business Data Worker负责企业经营数据 |
| LangGraph | 决定先后顺序和分支的流程图 | 先取数据，证据不足时再补查，最后汇总 |
| Harness | 包在运行过程外层的护栏 | 阻止越权工具、限制次数、记录轨迹和恢复任务 |

简单库存或规格查询只需要Tool，不为它创建Skill。只有“步骤相对固定、会组合多个工具、会被反复使用、需要明确质量检查”的复杂业务能力才封装为Skill。Skill不是新的Agent，也不绕过LangGraph；它向现有Agent提供可复用的步骤、输入输出约定和检查清单。

### 7.5 当前秋招主线业务Skill

| Skill | 首次实现 | 主要职责 | 允许申请的工具 |
|---|---|---|---|
| `cross-border-market-research` | M4 | 目标澄清、三来源取证、冲突处理、停止条件和输出检查；不写死商品/国家 | 可申请Business、Knowledge、Web能力，最终Tool仍取Worker/父Agent/用户/系统/ACL交集 |

M3的`product-visual-analysis`及原先报价、库存风险、报告写作等候选Skill保留为历史设计，不在当前秋招主线实施。若未来恢复，必须由真实需求重新确认，不能为了凑数量创建。

Skill目录遵循易读、可版本化的文件结构：

```text
app/skills/
└── cross-border-market-research/
│   ├── SKILL.md
│   ├── references/
│   └── assets/

app/agents/runtime/
├── skill_catalog.py      # 只加载名称、描述和版本
├── skill_loader.py       # 被选中后再读取完整SKILL.md
├── skill_router.py       # 根据任务推荐Skill
└── skill_policy.py       # 校验Skill申请的工具范围
```

采用渐进式加载：启动时只读取Skill名称、描述和版本；路由命中后才加载完整`SKILL.md`；确有需要时再读取`references/`或`assets/`。这样可以减少模型上下文长度，并让Skill独立版本化和评估。

Skill中保存稳定的方法，而不保存动态事实。应包含步骤、输入输出、事实/推断/未知规则、失败处理、模板和评估样例；不应包含实时库存、价格、汇率、API Key、数据库密码或会变化的法规原文。动态事实必须通过Tool、RAG或数据库获得。

### 7.6 Harness工程设计

Harness不是某一个第三方框架，也不是额外增加一个会推理的Agent。这里用它表示“让Agent可靠运行的一组工程控制”：模型可以建议做什么，但是否允许执行、最多执行几次、失败如何恢复，最终由程序决定。

V1 Harness由以下能力逐步组成：

| 组件 | 职责 |
|---|---|
| `RunContext` / `ContextBuilder` | 统一注入用户、租户、角色、会话、附件和追踪ID |
| `ToolRegistry` | 注册工具Schema、版本、超时和副作用等级 |
| `PermissionGuard` | 在调用前执行RBAC、tenant范围和字段权限检查 |
| `ExecutionBudget` | 限制模型、工具、Token、时间和重复调用次数 |
| Retry / Timeout | 区分可重试错误与永久错误，并设置退避和超时 |
| Checkpoint | 保存长任务节点状态，使中断后可以恢复 |
| Evidence Recorder | 把数据库、RAG、网页和文件结果统一登记为Evidence |
| Trace / Audit | 记录路由、Skill版本、工具参数摘要、耗时、拒绝和错误 |
| Human-in-the-Loop | 在关键歧义、重要假设或未来写操作前暂停确认 |
| Eval Hooks | 把实际轨迹交给评估Runner计算路由、Skill和工具指标 |

工具最终允许范围必须取以下条件的交集，而不能只相信Prompt或`SKILL.md`中的声明：

```text
最终允许工具
 = Skill申请工具
 ∩ Worker允许工具
 ∩ 当前用户角色权限
 ∩ 系统安全策略
```

M1已实现最小Harness骨架；M2-01至M2-20增加检索上下文和Evidence，M2-21负责Capability Resolver、Worker Runtime、父子预算、短期记忆和PostgreSQL Checkpoint；M4在此基础上增加长任务租约、Web Evidence、一个研究Skill和受控恢复；M5建立综合故障注入与回归评估。M3不再是Skill运行时或Checkpoint的前置阶段。

### 7.7 MCP边界

MCP（Model Context Protocol，模型上下文协议）是一种让AI客户端用统一格式连接外部工具和数据源的协议，它不是向量数据库，也不是实现多Agent的必要条件。

V1不部署MCP Server或引入通用数据库、文件系统MCP。当前前后端、Agent和工具都在同一项目内，直接Python接口更简单，也更容易落实用户权限、类型检查和测试。Tavily同样先走自定义Provider，不因存在官方MCP就增加一层协议。

以下情况出现时再评估MCP：

- 接入真实Amazon SP-API、ERP、仓储或其他独立系统；
- 同一个连接器需要被多个AI客户端复用；
- 希望把本项目的只读检索能力对外开放；
- 团队需要独立部署、授权和版本管理连接器。

即使未来使用MCP，外部工具仍必须经过Harness的权限、预算、超时、审计和证据规范化，MCP本身不替代这些控制。

## 8. 自建RAG设计

### 8.1 离线索引管线

```text
原文件
 → 校验与保存
 → 格式解析
 → 文本清洗和结构提取
 → 元数据提取
 → 结构感知分块
 → BGE-M3向量化
 → PostgreSQL chunks + pgvector
 → 构建全文检索字段
 → 索引状态ready
```

### 8.2 首期解析器

| 文件 | 首期解析器 | 说明 |
|---|---|---|
| PDF | PyMuPDF | 文本型PDF、页码保留 |
| DOCX | python-docx | 标题、段落、表格 |
| XLSX | openpyxl + Pandas | Sheet、表头、单元格范围 |
| CSV | Pandas | 编码和分隔符检测 |
| TXT/MD | Python标准库 | 标题和段落 |
| 图片 | qwen3.8-max | OCR和视觉属性 |

扫描PDF、复杂版面和通用OCR放入增强版。

### 8.3 分块策略

使用结构感知递归分块，不使用全文件固定字符硬切：

- Markdown/Word按标题层级；
- PDF保留页码，在段落边界切分；
- 表格按表头 + 行窗口；
- 说明书优先保留规格表和步骤完整性；
- 合规文件保留条款编号；
- 目标块大小初始设置约400至700 tokens；
- overlap初始设置约80至120 tokens；
- 参数通过评估调整。

每个chunk保存：文档ID、版本、页码/Sheet、标题路径、语言、产品、市场、权限、时间和内容哈希。

### 8.4 在线查询管线

```text
用户问题
 → 权限与租户范围
 → 必要时查询改写/分解
 → 元数据过滤
 → dense top-30（pgvector）
 → lexical top-30（PostgreSQL FTS）
 → RRF融合
 → bge-reranker-v2-m3精排
 → top-5至top-8
 → Context去重、邻块补全、Token预算
 → qwen生成
 → 引用验证
```

检索先过滤权限再计算相似度，禁止先跨租户检索再在应用层删除结果。

### 8.5 为什么使用pgvector

- 项目本来需要PostgreSQL；
- 向量、文档元数据、权限和业务实体可以事务关联；
- 本地Docker少一个独立数据库服务；
- 支持HNSW和余弦距离；
- 便于实现dense + PostgreSQL全文检索混合方案。

第一版数据规模有限，不引入ChromaDB、Milvus或Elasticsearch。

### 8.6 索引更新

- 新增：解析、分块、向量化后追加；
- 修改：新建文档版本，旧版本标记inactive；
- 删除：先软删除，再异步删除chunk和文件；
- Embedding升级：新建 `embedding_version`，后台重建，不覆盖旧索引；
- 查询默认只检索最新有效版本。

## 9. 证据层

不同工具输出先标准化为Evidence，模型不直接拼接任意原始结果。

```python
class Evidence(BaseModel):
    id: str
    source_type: Literal["database", "knowledge", "user_file", "web", "image"]
    source_name: str
    source_locator: str
    title: str
    excerpt: str
    structured_data: dict | None
    observed_at: datetime
    published_at: datetime | None
    confidence: float | None
    trust_level: str
    tenant_id: str
    access_scope: dict
```

证据规则：

- 数据库证据记录查询时间和业务数据时间；
- 文档证据记录版本、页码或Sheet；
- 网络证据保留原始URL、标题和访问时间；
- 图片证据保存文件ID和模型版本；
- 报告中的重要结论必须关联一个或多个Evidence ID；
- 模型推断不得伪装成证据。

## 10. 文件存储

### 10.1 Storage接口

```python
class StorageBackend(Protocol):
    def put(self, key: str, stream, content_type: str) -> StoredObject: ...
    def open(self, key: str): ...
    def exists(self, key: str) -> bool: ...
    def delete(self, key: str) -> None: ...
```

V1实现 `LocalStorageBackend`。Key格式：

```text
{tenant_id}/{category}/{yyyy}/{mm}/{file_uuid}.{ext}
```

所有路径通过 `Path.resolve()` 校验必须位于配置的数据根目录内。接口只接受对象Key，不接受用户提供的绝对路径。

### 10.2 文件元数据与物理文件

- PostgreSQL存file_id、原名、key、MIME、大小、哈希、状态和权限；
- 本地目录存二进制文件；
- API下载参数只使用file_id；
- 报告与用户上传文件使用不同category；
- 临时文件设置生命周期清理任务。

## 11. API设计概要

```text
POST   /api/v1/auth/login
GET    /api/v1/me

POST   /api/v1/threads
GET    /api/v1/threads
GET    /api/v1/threads/{thread_id}/messages
POST   /api/v1/threads/{thread_id}/messages
GET    /api/v1/threads/{thread_id}/events       # SSE

POST   /api/v1/files
GET    /api/v1/files/{file_id}
GET    /api/v1/files/{file_id}/status
DELETE /api/v1/files/{file_id}

GET    /api/v1/tasks
GET    /api/v1/tasks/{task_id}
POST   /api/v1/tasks/{task_id}/cancel
POST   /api/v1/tasks/{task_id}/retry
POST   /api/v1/tasks/{task_id}/resume

GET    /api/v1/evidence/{evidence_id}
GET    /api/v1/reports
GET    /api/v1/reports/{report_id}
POST   /api/v1/feedback
```

消息POST返回 `message_id` 和可选 `task_id`。M2继续使用同步HTTP；M4长任务通过状态API轮询，SSE只有在真实体验验证需要时再增加，不能作为任务持久化机制。

## 12. 持久化、队列与恢复

### 12.1 状态分工

- PostgreSQL：业务真相、会话、父子Run、任务、租约、Agent Checkpoint、证据、文件和审计；
- 本地文件：上传文件、解析产物和报告。

V1不引入Redis/Celery。M4应用内有界执行器从PostgreSQL领取任务租约，每个安全节点完成后提交状态和Checkpoint。该方案用于本地作品规模的可恢复证明，不宣称具有分布式队列吞吐；只有真实压测证明不足时才另行评估队列。

### 12.2 恢复策略

- 每个关键LangGraph节点结束后写Checkpoint；
- 工具调用使用幂等 `tool_call_id`；
- Worker重启后从最后成功节点恢复；
- 外部API超时只重试有限次数并指数退避；
- 不可重试错误进入failed并保留已有证据；
- 用户可从失败节点重试，不必重新运行全部研究。

## 13. 缓存策略

第一版只缓存明确安全的内容：

- Embedding：按文本哈希 + 模型版本缓存；
- Rerank：按query哈希、候选哈希和模型版本缓存；
- 网络搜索：按规范化query和时间窗口缓存；
- 产品Schema：短期缓存；
- 不跨租户缓存带权限的最终回答。

缓存Key必须包含tenant、权限范围、版本和语言等影响结果的维度。

## 14. 安全设计

### 14.1 四层防护

输入：

- 长度、文件类型、大小、MIME校验；
- 用户文本与系统指令分离；
- 网络和文档内容标记为不可信数据；
- 限流和上传配额。

处理：

- RBAC与tenant过滤；
- Agent按角色动态加载工具；
- SQL只读、白名单和超时；
- 文件访问限制在Storage接口；
- 外部内容不能覆盖系统指令。

输出：

- 过滤密钥、连接串和系统Prompt；
- 引用验证；
- 合成数据标识；
- 对合规和销量等不确定结论添加限定。

审计：

- 记录登录、查询、文件、工具、报告和权限拒绝；
- 日志中对API Key和敏感字段脱敏；
- 每次Agent任务关联trace_id。

### 14.2 Prompt注入

网页或文件中出现“忽略之前指令”等文本时，只能作为引用材料，不得被当作系统指令。工具结果进入模型前增加来源边界和数据标签。外部内容不能触发新的高权限工具调用。

## 15. 可观测性

每个请求生成 `trace_id`，记录：

- 用户、会话、任务和路由；
- LangGraph节点开始/结束/状态；
- 模型名称、延迟、输入输出Token；
- 工具名称、规范化参数、结果状态和耗时；
- 检索候选、Rerank分数和最终引用；
- 错误类型、重试次数和恢复节点；
- 用户反馈。

V1先实现结构化JSON日志和PostgreSQL追踪表；LangSmith/Langfuse、Prometheus/Grafana作为增强项，不作为完成核心链路的前置条件。

## 16. 本地部署

### 16.1 Docker Compose服务

```text
frontend   Next.js
api        FastAPI
postgres   PostgreSQL + pgvector
```

M4长任务由API应用中的有界执行器领取PostgreSQL任务租约；源文件通过Storage抽象访问本地目录。Embedding/Reranker初期可在应用进程按需加载；实测后决定常驻或独立推理服务。

### 16.2 本地运行配置

```env
APP_ENV=development
DATABASE_URL=postgresql+psycopg://...

LLM_PROVIDER=qwen
LLM_MODEL=qwen3.8-max
DASHSCOPE_API_KEY=...
DASHSCOPE_BASE_URL=...

TAVILY_API_KEY=...

STORAGE_BACKEND=local
LOCAL_STORAGE_ROOT=/data

EMBEDDING_MODEL=BAAI/bge-m3
RERANKER_MODEL=BAAI/bge-reranker-v2-m3
```

`.env.example`只放占位符，任何真实密钥都不能提交Git。

## 17. 现有代码迁移策略

### 17.1 保留

- 当前FastAPI认证、会话消息URL、文件API和请求/响应合同；
- M1两个业务Tool、数据库Evidence、Seed和回归基线；
- M2自建RAG、Storage、知识Tool和文档Evidence；
- LangGraph、Harness和Provider抽象；
- LangGraph相关依赖。

### 17.2 替换

| 当前实现 | V1目标 |
|---|---|
| `create_deep_agent`隐式编排 | 显式LangGraph状态图 |
| `InMemorySaver` | PostgreSQL Checkpoint |
| RAGFlow聊天助手工具 | 自建RAG Service |
| MySQL直接查询 | PostgreSQL + 安全只读SQL层 |
| 任意SQL执行 | AST校验、白名单、超时、LIMIT |
| 会话目录直接复制文件 | Storage接口 + files元数据 |
| 进程内不可恢复后台任务 | 应用内有界执行器＋PostgreSQL任务租约/Checkpoint |
| 绝对路径下载参数 | `file_id`下载 |
| 全开放CORS | 本地前端域名白名单 |

### 17.3 不建议一次性重写

迁移按垂直切片进行：M1固定库存图已证明第一个闭环；M2-21在保留聊天HTTP合同的前提下建设Agent Gateway和Business/Knowledge Worker，再把公开消息入口切换到新主路径；旧M1固定图仅作为内部兼容/回归基线，不成为失败时的隐式兜底。M2-22至M2-24完成评估和前端后，再接M4深度研究。每完成一个切片都保留自动化测试，避免大爆炸式重写。

## 18. 测试策略概要

- 单元测试：工具参数、SQL规则、路径安全、分块、证据规范化；
- 集成测试：PostgreSQL/pgvector、文件上传、父子Run/Checkpoint、Tavily Fake；
- Agent轨迹测试：给定问题必须选择指定工具或禁止工具；
- Skill轨迹测试：触发正确、简单任务不误触发、版本可追踪、规定步骤完成；
- Harness策略测试：权限交集、预算、超时、重复调用、重试和审计生效；
- RAG评估：Recall、MRR、引用和忠实性；
- 多模态评估仅在未来恢复M3后重新立项；
- 端到端：统一聊天中的库存/知识/Evidence，以及M4任务进度和Markdown结果；
- 故障注入：模型超时、Tavily失败、执行器恢复、租约到期和文件损坏。

## 19. 第一版技术完成定义

满足以下条件才视为技术完成：

- 所有公开聊天使用同一Agent Gateway，按L0/L1/L2/L3选择直接回答、单Worker、多Worker或持久任务；
- 简单库存查询不强制启用Skill，复杂业务流程可加载匹配版本的Skill；
- Tool调用必须通过Harness计算出的服务端权限交集；
- Agent状态和会话重启后仍存在；
- 数据库工具无法执行写操作或越权查询；
- RAG包含混合检索、Reranker和引用；
- 数据库、文档和网页的重要结论都可定位到Evidence；
- 外部服务失败可重试或部分降级；
- 本地文件不能通过路径参数越权访问；
- 关键指标能够通过评估Runner复现；
- Docker Compose可在目标电脑启动前端、API和PostgreSQL/pgvector核心服务。
