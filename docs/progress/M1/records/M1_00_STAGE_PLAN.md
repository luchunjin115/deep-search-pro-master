# M1 原始阶段方案与总体设计

> 本文件保存从迁移前单文件中拆出的完整历史方案、实施日志与验证证据。
> 当前状态和阅读入口见 [M1入口](../M1_INVENTORY_QUERY.md)。

## 1. 本文档目的

本文档把已确认的总体设计收缩成一个可逐步开发、逐步验证的M1实施合同。M1只证明一件事：Amazon运营人员登录后，用自然语言查询德国仓蘑菇灯库存，系统在权限和预算约束下查询PostgreSQL，并返回答案、数据时间、数据库证据和审计轨迹。

本文档保存M1方案、确认记录、逐步实施日志和验证结果；运行代码保存在对应的项目目录中。

## 2. 术语的大白话解释

| 术语 | 大白话 | M1中的例子 |
|---|---|---|
| FastAPI | 接收网页请求、调用后端逻辑、把结果送回去的“服务门口” | 接收登录和聊天请求 |
| Schema | 数据格式合同，规定什么字段能进来、什么字段必须返回 | 库存结果必须包含SKU、可售量和数据时间 |
| ORM | 用Python类代表数据库表和数据行 | SQLAlchemy的`InventorySnapshot`类对应库存快照表 |
| Model | 固定调用链里的数据库模型，不是千问大模型 | `InventorySnapshot`负责把库存对象映射到PostgreSQL表 |
| SQLAlchemy | M1采用的ORM和数据库连接工具 | 管理PostgreSQL连接、事务和受控查询 |
| Alembic | 数据库结构的版本记录器 | 按版本创建用户、产品和库存表 |
| Repository | 专门负责查数据库的数据访问层 | 按租户、SKU和仓库查询最新库存 |
| Service | 执行业务规则的一层 | 计算可售库存并组织Evidence |
| LangGraph | 把Agent步骤写成明确节点和分支的流程图 | 意图解析→商品解析→库存查询→回答 |
| RBAC | 按角色控制权限 | 运营、选品人员、负责人拥有不同角色权限 |
| Harness | 包在Agent外面的程序护栏 | 工具调用前检查身份、市场范围、次数和超时 |
| Mock | 不调用真实外部API的“假实现” | 无千问Key时固定解析“德国仓蘑菇灯” |
| Evidence | 支撑答案的可追溯证据对象 | 指向某条合成库存快照并记录数据时间 |
| trace_id | 一次执行的追踪编号 | 用同一个编号关联路由、工具、耗时和错误 |
| SSE | 服务器持续向网页单向推送事件的连接 | M1不使用，长任务阶段再引入 |

## 3. 当前现状与缺少的能力

### 3.1 旧项目已有能力

- `api/server.py`已有FastAPI入口、任务接口、上传/下载和WebSocket原型；
- `agent/main_agent.py`使用`create_deep_agent`组织主Agent和三个子Agent，并用`InMemorySaver`保存内存状态；
- `api/context.py`展示了使用`ContextVar`隔离会话上下文的正确方向；
- `api/monitor.py`能向WebSocket上报工具和最终结果；
- `tools/`已有MySQL、RAGFlow、Tavily、文件读取、Markdown和PDF原型；
- `requirements.txt`包含FastAPI、LangGraph、SQLAlchemy、Pydantic等部分可复用依赖；
- 当前`frontend/`是空目录，没有`package.json`和可运行页面；
- 当前仓库没有Docker Compose、Alembic配置、PostgreSQL模型或自动测试目录。

### 3.2 旧项目不能直接承担M1的原因

- 旧数据库是MySQL，目标数据库是PostgreSQL；
- 旧数据库Agent可把模型生成的任意SQL直接交给数据库，没有表/字段白名单、租户过滤和可靠只读边界；
- 导入旧主Agent时会初始化模型、RAGFlow和Tavily等外部能力，无法在没有Key时做稳定测试；
- 旧上下文只有会话目录和线程ID，没有用户、租户、角色和数据范围；
- 旧WebSocket事件在内存中，断线后不能补取，也没有数据库审计；
- 没有登录、RBAC、库存模型、Evidence、工具契约、预算或测试；
- 旧README、`.env.example`和依赖仍描述MySQL、RAGFlow及通用多Agent原型，与M1目标不一致。

### 3.3 M1缺少的能力

- 一个与旧原型隔离的新`app/`后端入口；
- 可由Docker Compose启动的PostgreSQL；
- SQLAlchemy连接、ORM模型和Alembic迁移；
- 可重复生成的租户、用户、角色、产品、仓库和库存合成数据；
- 固定Repository查询和明确的输入、输出、错误Schema；
- 登录、JWT身份、市场数据范围和最小RBAC；
- `get_product_spec`、`search_inventory`两个只读Tool；
- RunContext、ToolRegistry、PermissionGuard、ExecutionBudget和基础Trace；
- Mock/Qwen Provider和最小LangGraph库存流程；
- 同步聊天、Evidence API及最小Next.js桌面页面；
- 单元、PostgreSQL集成和浏览器端到端验证。

## 4. 阶段目标与演示效果

### 4.1 阶段目标

Amazon运营人员登录后输入：

> 德国仓蘑菇灯还有多少可售库存？

系统应完成：

1. 从登录身份建立包含用户、租户、角色、市场范围、会话和`trace_id`的RunContext；
2. Mock或千问把自然语言解析为库存意图、商品关键词和德国市场参数；
3. Harness允许且只允许本次所需Tool；
4. `get_product_spec`把“蘑菇灯”解析为受控SKU；
5. `search_inventory`用固定Repository查询PostgreSQL；
6. 返回期末、预留、不可售、可售、在途、安全库存和数据时间；
7. 返回数据库Evidence并醒目标注“合成演示数据”；
8. 保存路由、工具、参数摘要、耗时、状态和错误轨迹；
9. 最小桌面聊天页面显示登录、执行中、成功/失败、回答和证据。

### 4.2 用户最终能看到的效果

- 一个演示登录页和一个桌面聊天页；
- 输入自然语言后先看到“正在查询库存”；
- 成功后看到明确数字、SKU、仓库和数据时间；
- 右侧证据卡显示数据库来源、记录定位、查询条件摘要和“合成演示数据”；
- 权限不足、非法参数或无记录时看到具体原因，不显示“未知错误”；
- 开发调试响应中可用`trace_id`定位本次执行轨迹。

## 5. 明确不做的内容

M1不实现或不启动：

- Skill运行时和5个业务Skill；
- 自建RAG、BGE-M3、Reranker和pgvector知识检索；
- 图片理解和文件上传链路；
- Tavily互联网搜索；
- Supervisor、多Worker和深度研究；
- Celery、Redis、后台长任务、Checkpoint恢复和SSE；
- Markdown/PDF报告；
- MinIO、MCP、Amazon SP-API和真实公司数据；
- 模型生成SQL、通用SQL工具或任何数据写入类Agent Tool；
- 完整企业数据后台、任务中心、知识库和报告中心；
- 移动端适配和生产级商业SaaS能力。

## 6. 前置条件

### 6.1 必须满足

- 用户确认本实施方案；
- Git工作区在每一步开始前可识别已有用户修改，禁止覆盖无关变更；
- Docker Desktop与Docker Compose可用，PostgreSQL端口可配置；
- Python 3.11建议版本可用；
- Node.js 20 LTS及npm可用；
- 当前本机端口使用PostgreSQL `5433`、API `8000`、前端`3000`；PostgreSQL原计划的`5432`被另一工作区占用，因此本项目只绑定`127.0.0.1:5433`；
- 真实密钥只写本地`.env`，不进入Git。

### 6.2 不阻塞开工

- 千问API Key不阻塞M1-01至Mock端到端验证，默认`LLM_PROVIDER=mock`；
- 没有Redis不阻塞M1，因为本阶段没有队列、长任务或跨进程缓存；
- 没有Tavily、RAGFlow、BGE模型不阻塞M1，这些能力不进入本阶段。

## 7. 总体技术方案

### 7.1 新旧代码迁移

| 分类 | 处理 | 原因 |
|---|---|---|
| `api/context.py`的`ContextVar`思想 | 保留思想，在`app/runtime/context.py`重写为强类型RunContext | 旧结构缺少用户、租户、角色和trace |
| `api/monitor.py`的事件记录思想 | 保留思想，改为结构化Trace并持久化 | 旧实现只有内存WebSocket事件 |
| FastAPI异步接口思路 | 保留 | 适合后续扩展，但M1聊天采用同步HTTP响应 |
| `tools/tavily_tool.py`、文件和PDF能力 | 暂时隔离 | 属于M2/M4，不进入M1导入链 |
| `agent/`、`api/`、`tools/`旧目录 | M1不删除、不搬迁、不导入 | 保留学习和迁移依据，避免一次性重写风险 |
| `tools/db_tools.py` | 新链路完全替换 | MySQL、字符串表名和任意SQL不满足安全要求 |
| `create_deep_agent`隐式编排 | 新链路完全替换为显式LangGraph | 只保留M1可观察的固定节点 |
| `InMemorySaver` | M1不使用 | 同步短流程无恢复需求，轨迹改存PostgreSQL |
| `requirements.txt` | 收缩为M1主链依赖；旧依赖另存兼容清单 | 避免安装RAGFlow、MySQL、PDF等未使用依赖 |
| `.env.example`、README | 更新为M1主入口和合成数据说明 | 旧说明会把用户引向错误启动方式 |

新代码统一从`app/main.py`启动。通过启动命令、导入测试和README明确“旧原型不属于M1运行链”，不靠删除旧代码实现隔离。

### 7.2 建议的M1后端目录

```text
app/
├── main.py
├── api/
│   ├── dependencies.py
│   └── routers/
│       ├── auth.py
│       ├── threads.py
│       └── evidence.py
├── core/
│   ├── config.py
│   ├── errors.py
│   ├── logging.py
│   └── security.py
├── db/
│   ├── base.py
│   └── session.py
├── models/
│   ├── identity.py
│   ├── catalog.py
│   ├── inventory.py
│   └── runtime.py
├── schemas/
│   ├── common.py
│   ├── auth.py
│   ├── chat.py
│   ├── product.py
│   ├── inventory.py
│   └── evidence.py
├── repositories/
│   ├── product.py
│   ├── inventory.py
│   └── runtime.py
├── services/
│   ├── auth.py
│   ├── product.py
│   ├── inventory.py
│   └── evidence.py
├── llm/
│   ├── provider.py
│   ├── mock.py
│   ├── qwen.py
│   └── schemas.py
├── tools/
│   ├── contracts.py
│   ├── registry.py
│   ├── get_product_spec.py
│   └── search_inventory.py
├── agents/
│   ├── state.py
│   └── graphs/inventory_query.py
└── runtime/
    ├── context.py
    ├── permissions.py
    ├── budget.py
    ├── trace.py
    └── executor.py

migrations/
scripts/
tests/
frontend/
```

不为只有一个文件的概念预先建立空目录；上面是目标边界，具体文件只在对应步骤创建。

### 7.3 M1是否建立Next.js页面

需要。现有`frontend/`只是空目录，无法演示“登录→提问→证据”。M1将在该目录建立最小Next.js App Router + TypeScript页面，只实现：

- 登录表单；
- 单会话聊天输入和消息区；
- 请求中的执行状态；
- 回答卡和Evidence侧栏；
- 合成演示数据标识；
- 权限、无数据和系统错误状态。

不实现完整导航、任务中心、文件上传、图表或复杂状态管理。前端只展示后端事实，不在浏览器重新计算库存。

### 7.4 PostgreSQL第一批最小表

M1建议14张表，按三个小批次迁移：

| 数据域 | 表 | M1职责 |
|---|---|---|
| 身份 | `tenants` | 演示公司和`is_demo`标记 |
| 身份 | `users` | 邮箱、显示名、密码哈希、状态和租户 |
| 身份 | `roles` | `company_owner`、`product_scout`、`amazon_operator` |
| 身份 | `user_roles` | 用户角色及`market_scopes`数据范围 |
| 商品 | `products` | SPU、中文/英文名、别名、演示标记 |
| 商品 | `product_variants` | 唯一SKU、颜色、状态 |
| 商品 | `product_specs` | 规格值、单位、来源和核验状态 |
| 库存 | `warehouses` | `DE-FRA`、`FR-CDG`等仓库与市场 |
| 库存 | `inventory_snapshots` | 期末、预留、不可售、在途、安全库存和时间 |
| 会话 | `threads` | 用户聊天会话 |
| 会话 | `messages` | 用户问题和系统回答摘要 |
| 运行 | `agent_runs` | trace、路由、预算计数、状态、耗时和错误 |
| 运行 | `tool_calls` | Tool版本、参数摘要、权限结果、耗时和错误 |
| 证据 | `evidences` | 数据库来源、定位、结构化数据、数据时间和访问范围 |

M1不建立`permissions`、`role_permissions`、`tasks`、`task_steps`、`skill_runs`、`checkpoints`、RAG或评估表。Tool允许角色先由版本化ToolRegistry声明，`user_roles.market_scopes`约束市场；进入更复杂权限阶段后再无损迁移到完整权限表。

关键约束：

- `users(tenant_id, email)`唯一；
- `product_variants(tenant_id, sku)`唯一；
- `warehouses(tenant_id, code)`唯一；
- `inventory_snapshots(tenant_id, variant_id, warehouse_id, snapshot_at)`唯一；
- 所有业务和运行记录必须直接带`tenant_id`或通过外键唯一追溯；
- 数量字段非负；`available = on_hand - reserved - unsellable`由Service统一计算并校验；
- 时间使用带时区时间戳。

### 7.5 Redis决定

M1不启动Redis。理由：

- 聊天请求在一次同步HTTP内完成；
- 没有Celery Worker、后台长任务、SSE事件中继、跨进程预算或缓存；
- Trace和Evidence直接写PostgreSQL；
- 单机进程内预算即可完成确定性验证。

Redis预计在M4长任务和Celery出现时引入。若M1提前启动，只能证明容器能运行，不能增加库存闭环的有效能力，反而增加端口、配置和排错面。这一决定是对总体设计中“M1启动Redis”候选顺序的明确收缩。

### 7.6 SQLAlchemy与Alembic分工

- SQLAlchemy负责程序运行时：建立连接池、开启事务、把Python ORM对象映射到表，并让Repository执行参数化查询；
- Alembic负责数据库结构演进：记录“第1版有哪些表、第2版增加什么约束”，支持升级和回退；
- Seed生成器只负责插入演示数据，不能代替Alembic建表；
- 前端、模型和Tool都不直接使用数据库连接。

### 7.7 合成数据与可重复性

- 生成器版本固定为`m1-v1`，随机种子固定；关键演示对象使用确定性UUID；
- 蘑菇灯沿用`LR-TL-MUSH-OR01`，明确标记候选新品和合成演示数据；“尚未产生真实销售”不等于没有演示备货，M1允许它存在海外仓预备库存；
- 德国仓示例数量满足统一公式，例如期末150、预留20、不可售5、可售125，实际数值在Seed清单中唯一声明；
- Seed重复执行使用确定性upsert或先验证后跳过，不制造重复SKU；
- 生成后输出`data/seed/m1_manifest.json`，记录版本、种子、表行数、关键答案和内容哈希；
- 自动校验行数、唯一约束、外键、非负数量、可售公式、权限样本和关键演示答案；
- 页面、API和Evidence均返回`synthetic_data=true`。

### 7.8 M1用户和权限样本

三类产品角色全部进入M1，但只建立库存/规格所需的最小权限样本，不实现完整V1权限矩阵：

- 1个公司负责人：允许查询DE和FR库存/规格；
- 1个选品人员：允许查询DE和FR库存/规格；
- 1个德国运营：只允许DE；
- 1个法国运营：只允许FR，用来验证查询德国仓会被拒绝。

因此是“三类角色、四个演示账号”。密码只保存Argon2哈希；演示初始密码来自本地环境或非敏感Seed默认值，并在README标注仅限本地演示。

RBAC不是只检查角色名。PermissionGuard同时检查：

```text
Tool允许角色 ∩ 当前用户角色 ∩ 当前租户 ∩ 用户市场范围 ∩ 系统只读策略
```

### 7.9 库存查询安全策略

M1采用固定Repository查询和受控参数，禁止模型生成SQL：

```text
自然语言
 → 模型输出InventoryIntent Schema
 → Pydantic校验SKU/商品词/DE或FR
 → PermissionGuard检查租户与市场
 → Repository使用预写SQLAlchemy条件
 → PostgreSQL参数化SELECT + statement_timeout
```

Repository强制带`tenant_id`、SKU、仓库/市场和“最新快照”条件。模型看不到连接串、Session、ORM对象或SQL执行方法。总体设计中面向未来的“受控只读SQL计划 + AST校验”不进入M1，因为两个固定查询不需要通用SQL能力。

### 7.10 两个Tool的Schema

#### `get_product_spec`

输入：

```json
{
  "product_query": "蘑菇灯"
}
```

约束：去除首尾空格，长度1至100；可接收合法SKU、中文名、英文名或受控别名；`tenant_id`不允许由模型传入，只从RunContext取得。

成功数据：

```json
{
  "product_id": "uuid",
  "variant_id": "uuid",
  "sku": "LR-TL-MUSH-OR01",
  "name_zh": "橙色复古蘑菇台灯",
  "name_en": "LUMORIVA Orange Mushroom Table Lamp",
  "status": "candidate",
  "specs": [
    {
      "name": "height",
      "value": "30",
      "unit": "cm",
      "verification_status": "demo_declared"
    }
  ],
  "synthetic_data": true
}
```

#### `search_inventory`

输入：

```json
{
  "sku": "LR-TL-MUSH-OR01",
  "market_code": "DE",
  "warehouse_code": null
}
```

约束：SKU格式白名单；`market_code`只允许`DE|FR`；可选仓库必须属于该市场；`tenant_id`和允许市场只从RunContext取得。

成功数据：

```json
{
  "sku": "LR-TL-MUSH-OR01",
  "product_name": "橙色复古蘑菇台灯",
  "market_code": "DE",
  "warehouse_code": "DE-FRA",
  "warehouse_name": "德国法兰克福海外仓",
  "on_hand": 150,
  "reserved": 20,
  "unsellable": 5,
  "available": 125,
  "inbound": 80,
  "safety_stock": 60,
  "snapshot_at": "2026-08-28T08:00:00+02:00",
  "synthetic_data": true
}
```

#### 统一Tool外壳与错误

```json
{
  "status": "success|error",
  "data": {},
  "evidence_ids": ["uuid"],
  "error": {
    "code": "FORBIDDEN",
    "message": "当前账号无权查询德国市场库存",
    "retryable": false,
    "field": "market_code"
  },
  "meta": {
    "tool": "search_inventory",
    "version": "1.0.0",
    "duration_ms": 83,
    "source_time": "2026-08-28T08:00:00+02:00",
    "trace_id": "uuid",
    "synthetic_data": true
  }
}
```

M1错误码至少包含：`VALIDATION_ERROR`、`UNAUTHENTICATED`、`FORBIDDEN`、`PRODUCT_NOT_FOUND`、`AMBIGUOUS_PRODUCT`、`INVENTORY_NOT_FOUND`、`DATABASE_TIMEOUT`、`BUDGET_EXCEEDED`、`PROVIDER_ERROR`、`INTERNAL_ERROR`。错误不能返回堆栈、密钥、连接串或原始SQL。

### 7.11 Mock与千问Provider

- 定义`ModelProvider`接口，只暴露“根据问题和当前白名单提出一个Tool调用建议”所需方法；
- `ToolRegistry`只投影名称、描述和参数JSON Schema给模型，不提供Tool实例、角色策略、tenant或超时配置；
- `MockProvider`使用固定规则和测试用例，稳定提出演示调用建议，不联网、不收费；
- 默认环境使用Mock，所有确定性单元、集成和端到端测试均不依赖千问；
- `QwenProvider`通过OpenAI兼容Function Calling调用百炼，返回的Tool名称和参数必须经过当前白名单与对应Pydantic输入Schema复检；
- 千问不可用、超时或输出非法时返回`PROVIDER_ERROR`，不得绕过Schema直接查询数据库；
- Qwen冒烟测试单独标记，需要Key时才运行，不作为本地核心回归的前置条件。

证明千问只负责Tool选择建议和参数的方法：

1. `app/llm/`不导入`app/db/`、Repository或SQLAlchemy Session；
2. Provider构造函数不接收数据库连接；
3. 请求测试确认Provider只收到问题、当前允许的Tool说明及后端已确认SKU，不收到Tool实例、身份、权限或数据库配置；
4. Trace顺序必须是`model_proposal → graph_validation → permission_check → tool_call → repository_query`；
5. 数据库访问日志只能由Repository产生；
6. 即使模型建议未登记Tool或输出`DROP TABLE`字段，也会因白名单或Tool输入Schema不接收而被拒绝。

这能证明“本项目没有把数据库能力交给千问”，但不能证明第三方模型服务自身的内部实现。

### 7.12 LangGraph最小图

```text
START
  ↓
propose_next_tool（Provider只看当前白名单）
  ├─ 无适用Tool → unsupported_answer → END
  ↓
validate_proposal（检查图状态、Tool名称和强类型参数）
  ├─ 非法或不符合当前状态 → error_answer → END
  ↓
execute_tool（经Harness检查权限/预算/Trace后执行）
  ├─ 错误 → error_answer → END
  ├─ get_product_spec成功 → 保存可信SKU → 回到propose_next_tool，当前只开放search_inventory
  └─ search_inventory成功
  ↓
compose_answer（确定性模板，不重新查询）
  ↓
END
```

身份认证和RunContext构建发生在进入图之前；PermissionGuard、预算和Trace包在模型建议和每次Tool执行边界，不伪装成Agent节点。图最多允许2次模型建议和2次Tool执行，这个“回到决策节点”只是完成商品解析后的一次受限分支，不是开放式自主循环。M1没有Supervisor、Worker、自由规划、Skill、Checkpoint或人工确认节点。

### 7.13 Evidence生成

M1由确定性的`EvidenceService`把Repository结果变成数据库Evidence，不让模型自行编写证据：

- `source_type=database`；
- `source_name=synthetic_inventory`或`synthetic_product_catalog`；
- `source_locator`保存表名和记录UUID，不暴露连接串；
- `query_summary`保存规范化的SKU、市场、仓库和租户范围，不保存用户密码或完整Token；
- `structured_data`保存回答实际使用的字段；
- `observed_at`为业务数据时间，`created_at`为查询时间；
- `access_scope`保存tenant和市场；
- `synthetic_data=true`；
- Evidence先持久化，再将ID和安全摘要返回给回答。

回答中的库存数字必须直接来自Evidence结构化数据；模型推断不能伪装成数据库证据。

### 7.14 API与前端数据流

M1最小接口：

```text
POST /api/v1/auth/login
GET  /api/v1/me
POST /api/v1/threads
POST /api/v1/threads/{thread_id}/messages
GET  /api/v1/evidence/{evidence_id}
```

登录返回短期JWT Bearer Token。JWT可以理解成“后端签名的临时身份证”；后续请求携带它，后端仍需从数据库读取用户状态、角色和范围。

聊天POST同步返回：`status`、`thread_id`、`message_id`、`answer`、Evidence摘要数组，以及包含`trace_id`、路由、Tool名称、耗时和状态的`execution`对象。前端在等待HTTP时显示`running`，收到后显示`completed`或具体错误；需要详情时按Evidence ID读取。

### 7.15 同步HTTP还是SSE

M1选择同步HTTP：

- 目标是一到两个只读Tool和最多两次模型建议，属于数秒级快速查询；
- 没有后台Worker，HTTP断开后也没有可恢复长任务；
- 同步响应最容易确定性测试错误码、Evidence和审计是否一致；
- 前端仍能显示“正在查询”，不等于必须使用流式协议。

若实际基线P95超过8秒，先定位模型或数据库耗时，不以SSE掩盖性能问题。SSE留给后续需要流式文本或长任务状态的阶段。

## 8. 完整调用链

```text
前端 Next.js
  登录、输入问题、显示running/completed/error、答案和Evidence
  ↓ HTTP
API FastAPI
  校验JWT、创建thread/trace、调用LangGraph、映射HTTP错误
  ↓
Schema Pydantic
  校验登录、聊天、意图、Tool、Evidence和错误结构
  ↓
Service + LangGraph + Harness
  组织步骤，检查权限/预算，调用Tool，计算可售量，生成证据和轨迹
  ├─→ LLM Provider（Mock或千问）
  │     只看当前白名单Tool说明并输出一个受控调用建议，不持有执行或数据库能力
  ↓
Repository
  使用固定参数化条件和tenant/market过滤查询
  ↓
Model（SQLAlchemy ORM）
  把Python业务对象映射到数据库表；这里不是千问大模型
  ↓
PostgreSQL
  保存合成业务数据、用户、会话、Evidence和Trace
```

响应沿相反方向返回。要求中的固定主链是“前端→API→Schema→Service→Model（ORM）→PostgreSQL”；Repository只是把Service和ORM查询职责分开。千问属于Service/LangGraph调用的LLM Provider旁路，不是固定主链里的Model。安全边界不变：千问永远不能跳过Service/Harness直连Repository、ORM或PostgreSQL。

## 9. 实施顺序与依赖评审

候选顺序需要调整的地方：

- Alembic迁移依赖ORM模型，不能在模型定义前完成实际建表，所以先建立SQLAlchemy连接，再按数据域定义模型和迁移；
- Schema是跨层合同，应在Repository和Service正式实现前冻结；
- 身份服务和RunContext要先于PermissionGuard和Tool执行；
- Tool必须在Repository、Service、Schema和Harness都存在后注册；
- Mock Provider先于Qwen真实接入，确保外部Key不阻塞主链；
- Redis、SSE不进入M1；
- 自动测试不是最后才开始，每一步都有局部测试，最后一步只补全故障矩阵和端到端回归。

M1计划按21个小步骤实施。一个步骤只解决一个主要问题；每步完成代码、实际验证和进度记录后暂停汇报，不自动进入下一步。

## 10. 21个单步实施计划

### M1-01｜建立新目录、配置和依赖基线

- 输入：当前旧原型、已确认技术边界；输出：可导入但不含业务实现的`app/`入口、分层配置和M1/旧原型依赖边界。
- 上游：M0设计；下游：所有后端步骤。
- 预计文件：`app/__init__.py`、`app/main.py`、`app/core/config.py`、`requirements.txt`、`requirements-dev.txt`、`requirements-legacy.txt`、`.env.example`、`.gitignore`。
- 调用链位置：API基础和项目配置；尚未经过前端、Schema、Service、Model、PostgreSQL。
- 验证：配置缺失/默认值测试、`app.main`导入测试、依赖清单检查、确认新入口不导入旧`agent/api/tools`。
- 能证明：新旧运行入口已隔离、配置可解析。不能证明：数据库、登录或库存可用。

### M1-02｜只启动PostgreSQL容器

- 输入：数据库环境变量；输出：健康的PostgreSQL服务和持久卷。
- 上游：M1-01；下游：数据库连接与迁移。
- 预计文件：`docker-compose.yml`、`.env.example`、`README.md`。
- 调用链位置：PostgreSQL基础设施；未经过前端、API、Schema、Service、Model。
- 验证：`docker compose config`、容器healthcheck、`pg_isready`、重启后连接验证。
- 能证明：数据库服务可连接、配置有效。不能证明：表和业务数据存在。

### M1-03｜建立SQLAlchemy连接和事务边界

- 输入：`DATABASE_URL`；输出：Engine、Session、Base、请求级事务和数据库健康检查。
- 上游：M1-02；下游：ORM模型、Repository。
- 预计文件：`app/db/base.py`、`app/db/session.py`、`app/api/dependencies.py`、`tests/integration/test_database_connection.py`。
- 调用链位置：API依赖→PostgreSQL连接；未经过业务Schema、Service、Model。
- 验证：连接/回滚/Session关闭、连接失败信息脱敏、`SELECT 1`。
- 能证明：程序能安全建立和释放数据库事务。不能证明：业务表正确。

### M1-04｜建立身份和角色模型及迁移

- 输入：单租户、三角色、市场范围设计；输出：`tenants/users/roles/user_roles`表。
- 上游：M1-03；下游：Seed、登录、RunContext。
- 预计文件：`app/models/identity.py`、`migrations/env.py`、`migrations/versions/*_identity.py`、`alembic.ini`、模型测试。
- 调用链位置：Model→PostgreSQL；未经过前端、API、业务Service或LLM。
- 验证：Alembic升级/降级/再升级、唯一约束、外键和市场范围格式。
- 能证明：身份数据结构可版本化。不能证明：登录和权限拦截有效。

### M1-05｜建立商品和库存模型及迁移

- 输入：商品、SKU、规格、仓库和库存字段；输出：5张业务表及约束。
- 上游：M1-03、M1-04；下游：Seed、Repository。
- 预计文件：`app/models/catalog.py`、`app/models/inventory.py`、`migrations/versions/*_inventory_domain.py`、模型测试。
- 调用链位置：Model→PostgreSQL。
- 验证：非负Check约束、租户内SKU唯一、仓库唯一、快照唯一、外键、迁移回退。
- 能证明：数据库能拒绝重复SKU和非法数量。不能证明：自然语言能查到库存。

### M1-06｜建立会话、运行、Tool审计和Evidence模型

- 输入：trace和Evidence字段合同；输出：`threads/messages/agent_runs/tool_calls/evidences`表。
- 上游：M1-04；下游：Trace、聊天API和Evidence API。
- 预计文件：`app/models/runtime.py`、`migrations/versions/*_runtime_evidence.py`、模型测试。
- 调用链位置：Model(ORM)→PostgreSQL；这里的Model不是大模型。
- 验证：trace唯一、外键、JSON字段、Evidence访问范围和状态枚举。
- 能证明：运行事实有持久化位置。不能证明：真实执行已写入轨迹。

### M1-07｜生成可重复的合成演示数据

- 输入：固定种子、版本和演示业务规则；输出：四个账号、蘑菇灯、仓库、库存和manifest。
- 上游：M1-04至M1-06；下游：所有查询和测试。
- 预计文件：`scripts/seed_m1.py`、`data/seed/m1_seed.json`、`data/seed/m1_manifest.json`、`tests/integration/test_seed_m1.py`。
- 调用链位置：Model→PostgreSQL，属于开发数据入口；不经过前端、API、LLM。
- 验证：空库生成、重复执行、行数/哈希一致、关键答案、可售公式、演示标记、密码非明文。
- 能证明：测试数据可重复且业务关系一致。不能证明：线上真实数据质量。

### M1-08｜冻结Pydantic输入、输出和错误合同

- 输入：第7.10节Tool/API字段；输出：可复用的认证、聊天、商品、库存、Evidence、ToolEnvelope和ErrorDetail Schema。
- 上游：业务目标和数据字段；下游：Service、Tool、Provider、API、前端类型。
- 预计文件：`app/schemas/common.py`、`auth.py`、`chat.py`、`product.py`、`inventory.py`、`evidence.py`、Schema单元测试。
- 调用链位置：Schema层；尚未执行Service、Model或PostgreSQL。
- 验证：合法样例、非法SKU、非法市场、缺字段、多余SQL字段、错误序列化。
- 能证明：边界数据可被严格检查。不能证明：数据库结果正确。

### M1-09｜实现受控商品和库存Repository

- 输入：已验证查询条件与Session；输出：租户范围内的商品解析和最新库存记录。
- 上游：M1-03、M1-05、M1-08；下游：两个业务Service。
- 预计文件：`app/repositories/product.py`、`inventory.py`、Repository集成测试。
- 调用链位置：Service下游→Model(ORM)→PostgreSQL。
- 验证：SKU精确查、别名查、宽泛名称歧义、DE/FR过滤、跨租户无结果、参数化查询、statement timeout。
- 能证明：固定查询和数据范围正确。不能证明：Tool权限和聊天路由正确。

### M1-10｜实现商品规格Service

- 输入：`product_query`和RunContext租户；输出：唯一产品规格或明确的未找到/歧义错误。
- 上游：Schema、ProductRepository；下游：`get_product_spec` Tool和LangGraph。
- 预计文件：`app/services/product.py`、`app/services/evidence.py`相关商品证据部分、单元/集成测试。
- 调用链位置：Schema→Service→Model→PostgreSQL；不经过LLM。
- 验证：SKU、中文别名、英文名、未找到、歧义和跨租户。
- 能证明：商品词能安全解析成SKU。不能证明：库存查询已完成。

### M1-11｜实现库存查询与数据库Evidence Service

- 输入：合法SKU、市场/仓库和RunContext；输出：统一库存结果及持久化Evidence。
- 上游：InventoryRepository、Schema、runtime表；下游：`search_inventory` Tool和回答。
- 预计文件：`app/services/inventory.py`、`app/services/evidence.py`、Service测试。
- 调用链位置：Schema→Service→Model→PostgreSQL。
- 验证：可售公式、最新快照、零库存、无记录、仓库市场不匹配、数据库超时映射、Evidence字段一致。
- 能证明：数据库事实能变成答案数据和证据。不能证明：Agent会选择正确Tool。

### M1-12｜实现登录、JWT和RunContext

- 输入：邮箱密码、thread和trace；输出：签名Token、当前用户信息和强类型RunContext。
- 上游：身份表和Seed；下游：PermissionGuard、API、LangGraph。
- 预计文件：`app/core/security.py`、`app/services/auth.py`、`app/runtime/context.py`、认证测试。
- 调用链位置：API依赖→Service→Model→PostgreSQL；尚未调用大模型。
- 验证：正确/错误密码、禁用用户、过期/伪造Token、四个账号角色和市场范围、Context并发隔离。
- 能证明：执行身份来自后端可信数据。不能证明：Tool权限已执行。

### M1-13｜实现ToolRegistry和PermissionGuard

- 输入：RunContext、Tool元数据和请求市场；输出：允许或结构化拒绝。
- 上游：M1-08、M1-12；下游：Tool执行器。
- 预计文件：`app/tools/registry.py`、`app/runtime/permissions.py`、策略测试。
- 调用链位置：Service/Harness层；不直接访问前端或LLM，必要时读取身份范围。
- 验证：未注册Tool、角色不允许、DE运营查DE成功、FR运营查DE拒绝、tenant不匹配、只读副作用等级。
- 能证明：服务端权限不依赖Prompt。不能证明：预算和审计已生效。

### M1-14｜实现ExecutionBudget和基础Trace

- 输入：模型/Tool次数上限、总时限、调用摘要；输出：预算判定及`agent_runs/tool_calls`轨迹。
- 上游：runtime表、RunContext；下游：统一Tool执行器和LangGraph。
- 预计文件：`app/runtime/budget.py`、`trace.py`、`executor.py`、Harness测试。
- 调用链位置：Service/Harness→Model(ORM)→PostgreSQL。
- 验证：模型次数超限、Tool次数超限、总时限、重复调用、敏感参数摘要脱敏、成功/失败均落轨迹。
- 能证明：M1最小预算和Trace有效。不能证明：后续跨进程预算或重试恢复。

### M1-15｜实现并注册两个Agent Tool

- 输入：严格Tool Schema、RunContext和业务Service；输出：统一ToolEnvelope。
- 上游：M1-10至M1-14；下游：LangGraph。
- 预计文件：`app/tools/contracts.py`、`get_product_spec.py`、`search_inventory.py`、Tool测试。
- 调用链位置：Schema→Service/Harness→Model(ORM)→PostgreSQL。
- 验证：Registry元数据、版本、超时、权限、成功、业务错误、异常脱敏；注册表中严格只有两个Agent Tool。
- 能证明：两个Tool可被受控调用。不能证明：自然语言路由正确。

### M1-16｜建立Mock和Qwen Provider边界

- 输入：自然语言问题、当前允许的Tool安全说明和可选的后端已确认SKU；输出：严格`ToolCallProposal`，只提出调用，不执行Tool或SQL。
- 上游：M1-13 ToolRegistry；下游：LangGraph决策与审核节点。
- 预计文件：`app/llm/provider.py`、`mock.py`、`qwen.py`、`schemas.py`、Provider测试。
- 调用链位置：Service/LangGraph→Model（这里指千问或Mock）；不经过Repository/PostgreSQL。
- 验证：两轮Mock建议、当前Tool白名单、非法/未授权Tool拒绝、参数Schema、Provider超时、SQL注入字段拒绝、静态导入边界；有Key时单独Qwen冒烟。
- 能证明：Provider只能返回当前白名单内的受控Tool建议。不能证明：Tool已经执行或真实千问对所有自然语言都准确。

### M1-17｜实现LangGraph库存最小流程

- 输入：RunContext和问题；输出：确定性回答、Evidence ID、执行状态和trace。
- 上游：Provider受控建议合同、两个Tool、Harness；下游：聊天API。
- 预计文件：`app/agents/state.py`、`app/agents/graphs/inventory_query.py`、图轨迹测试。
- 调用链位置：Schema→Service/LangGraph→Model→Tool/Harness→Service→Model(ORM)→PostgreSQL。
- 验证：标准问题节点顺序、非目标意图、商品未找到、权限拒绝、预算停止、Provider错误、禁止Tool从未出现。
- 能证明：M1流程显式、可观察、可终止。不能证明：HTTP和网页已接通。

### M1-18｜实现FastAPI登录、会话、聊天和Evidence接口

- 输入：HTTP请求、JWT和LangGraph结果；输出：版本化JSON响应和正确HTTP状态。
- 上游：M1-12、M1-17；下游：Next.js。
- 预计文件：`app/main.py`、`app/api/dependencies.py`、`app/api/routers/auth.py`、`threads.py`、`evidence.py`、API集成测试。
- 调用链位置：API→Schema→Service/LangGraph→Model→PostgreSQL，首次接通完整后端链。
- 验证：OpenAPI、登录、me、建会话、聊天、Evidence详情、401/403/404/422/504映射、CORS白名单。
- 能证明：HTTP客户端能完成完整后端查询。不能证明：浏览器界面可用。

### M1-19｜实现最小Next.js登录和证据聊天页

- 输入：M1 API合同；输出：桌面端登录、聊天、状态、回答和Evidence侧栏。
- 上游：M1-18；下游：浏览器端到端测试和演示。
- 预计文件：`frontend/package.json`、`next.config.*`、`tsconfig.json`、`app/layout.tsx`、`app/page.tsx`、`app/globals.css`、`components/*`、`lib/api.ts`。
- 调用链位置：前端→API→Schema→Service→Model→PostgreSQL，完整用户链路。
- 验证：TypeScript检查、lint、production build、键盘发送、loading/error/empty状态、Evidence定位、合成数据标识。
- 能证明：页面构建成功且能正确消费API类型。不能证明：真实浏览器与后端联合运行无误。

### M1-20｜完成故障矩阵、集成和浏览器端到端回归

- 输入：完整M1系统；输出：可重复测试报告和Bad Case记录。
- 上游：M1-01至M1-19；下游：演示验收。
- 预计文件：`tests/unit/*`、`tests/integration/*`、`frontend/e2e/*`、Playwright配置、测试说明。
- 调用链位置：覆盖前端→API→Schema→Service→Model→PostgreSQL整链，也分别绕过上游做组件测试。
- 验证：见第11节完整矩阵；Mock为默认，真实PostgreSQL为集成环境。
- 能证明：已覆盖的正常、越权和故障场景可重复通过。不能证明：未覆盖环境、真实流量和千问长期稳定性。

### M1-21｜完成演示脚本、README和阶段结果记录

- 输入：所有测试和实际启动结果；输出：初学者可照做的启动/演示说明、实际结果和已知限制。
- 上游：M1-20；下游：用户M1验收和M2方案讨论。
- 预计文件：`README.md`、`docs/progress/M1/M1_INVENTORY_QUERY.md`、`docs/PROJECT_PROGRESS.md`、必要的测试结果摘要。
- 调用链位置：项目交付层；演示脚本实际覆盖完整链路，文档本身不进入运行链。
- 验证：从干净数据库按README启动、Seed、登录、查询、越权演示、停止并重启；检查命令和链接。
- 能证明：M1可按说明复现和讲解。不能证明：M2及后续能力已实现。

## 11. 测试与异常验证矩阵

### 11.1 单元测试

- Schema：合法/非法SKU、市场、空问题、额外SQL字段、错误外壳；
- Service：可售公式、商品歧义、零库存、Evidence映射；
- Harness：角色、tenant、市场权限交集，次数/时限/重复调用，Trace脱敏；
- Provider：Mock确定性、非法结构、超时和SQL注入文本；
- LangGraph：节点顺序、终止分支和禁止Tool；
- 安全：密码哈希/JWT、错误不泄露连接串或堆栈。

### 11.2 PostgreSQL集成测试

- 所有Alembic迁移升级、降级和重建；
- Seed首次运行和重复运行结果/哈希一致；
- 唯一约束、外键、非负Check和重复SKU；
- tenant、role和market范围过滤；
- 商品别名、最新库存快照、零库存和无记录；
- `statement_timeout`在测试查询中实际触发；
- Tool、Evidence、agent_run和tool_call在同一trace下可追溯；
- API使用真实PostgreSQL和Mock Provider完成登录到回答。

### 11.3 浏览器端到端测试

- 德国运营登录并查询德国仓蘑菇灯，页面显示可售量、时间、Evidence和演示标记；
- 法国运营查询德国仓，页面显示权限不足且不出现库存数字；
- 非法/过期Token回到登录状态；
- 无库存和数据库错误显示具体可行动错误；
- 键盘发送、重复点击保护、loading状态和Evidence侧栏可用。

### 11.4 指定异常如何验证

| 异常 | 注入/准备方式 | 期望结果 | 主要证明 |
|---|---|---|---|
| 越权 | FR运营查询DE-FRA | `FORBIDDEN`，无Evidence、无数据泄露，Trace记录拒绝 | PermissionGuard在Tool前执行 |
| 非法SKU | 直接API/Tool传`SKU@@@` | 422或`VALIDATION_ERROR`，Repository零调用 | Schema先于数据库 |
| 零库存 | Seed一条合法且`available=0`快照 | 成功返回0，不误报“未找到” | 零是有效业务事实 |
| 无库存记录 | 合法SKU在指定仓无快照 | `INVENTORY_NOT_FOUND` | 区分零库存和无记录 |
| 重复SKU | 集成测试插入同租户同SKU两次 | PostgreSQL唯一约束拒绝；Seed重跑不重复 | 数据库最终约束生效 |
| 数据库超时 | 测试事务设置极短`statement_timeout`并运行`pg_sleep`；Repository模拟相同异常 | API映射504/`DATABASE_TIMEOUT`且可重试，Trace记错 | DB超时设置与错误映射有效 |
| 模型超时 | Mock Provider抛超时 | `PROVIDER_ERROR`，无Tool/DB调用 | 模型失败不会绕过流程 |
| Tool次数超限 | 测试预算设为0或构造重复请求 | `BUDGET_EXCEEDED`，后续Tool不执行 | 程序预算有效 |
| 商品歧义 | 宽泛名称匹配多个灯具 | `AMBIGUOUS_PRODUCT`并要求更精确SKU | 系统不随便选商品 |
| 跨租户 | 另一tenant记录使用相同SKU | 当前tenant查不到对方记录 | tenant过滤有效 |

数据库超时的两部分验证分别证明PostgreSQL超时参数会生效、应用会正确映射超时；它不能完全模拟所有真实网络抖动。网络级故障在后续可靠性阶段扩展。

## 12. 范围控制护栏

- ToolRegistry测试断言注册表严格只有`get_product_spec`和`search_inventory`；
- `app/`导入测试禁止引用RAGFlow、Tavily、BGE、pgvector、Celery、Redis、MinIO和旧MySQL工具；
- M1没有`skills/`运行时代码、Supervisor或Worker目录；
- 不接受SQL字符串作为任何公开Schema字段；
- Docker Compose只定义PostgreSQL；
- 前端没有上传、任务中心、知识库、报告、图表和管理后台；
- 发现后续需求只记录到“遗留问题”，不顺手实现；
- 每步只有经验证并更新本文件后才可汇报完成。

## 13. 阶段完成标准

必须同时满足以下条件，M1才能从“进行中”改为“已完成”：

1. 用户确认后的21个步骤均完成并有实际验证记录；
2. PostgreSQL可由Docker Compose启动，迁移和Seed可从空库重复执行；
3. 四个演示账号和三类角色存在，DE/FR范围验证通过；
4. 标准库存问题通过Mock Provider走指定LangGraph节点和两个受控Tool；
5. 前端显示正确库存、数据时间、Evidence、执行状态和合成数据标记；
6. ToolRegistry中只有两个M1 Tool，模型不能提交或执行SQL；
7. 越权、非法SKU、零库存、无记录、重复SKU、超时、歧义和跨租户测试通过；
8. 路由、参数摘要、权限、Tool、耗时、错误和Evidence可由同一`trace_id`关联；
9. 单元、PostgreSQL集成、API和浏览器端到端测试通过；
10. README能从干净环境复现演示；
11. `docs/PROJECT_PROGRESS.md`和本文件记录实际结果、能证明和不能证明的范围；
12. 未提前实现第5节列出的后续能力。

## 14. 主要风险与优先排查方向

| 风险/现象 | 优先排查方向 |
|---|---|
| 新入口启动时仍要求RAGFlow/Tavily/MySQL Key | 检查`app/`是否误导入旧`agent/api/tools` |
| Docker无法启动 | 先看Docker Desktop、端口、Compose配置和PostgreSQL healthcheck |
| Alembic显示最新但缺表 | 检查`migrations/env.py`的metadata导入和实际`DATABASE_URL` |
| Seed结果每次不同 | 检查固定种子、确定性UUID、时钟字段和upsert键 |
| 用户登录成功但角色为空 | 检查`user_roles` Seed、JWT解析后的数据库刷新和禁用状态 |
| 越权查询返回数据 | 第一优先检查PermissionGuard和Repository的tenant/market条件，不只改Prompt |
| 可售数不一致 | 检查统一公式、快照字段和是否误取旧快照，前端不得重算 |
| 商品词匹配错SKU | 检查别名优先级、SKU精确匹配和歧义分支 |
| Trace有工具但无Evidence | 检查Tool事务顺序和Evidence落库失败时是否错误提交 |
| Qwen输出不符合Schema | 检查结构化输出、模型名、Prompt和一次有限修复；禁止宽松解析SQL文本 |
| 同步聊天超过8秒 | 分开测Provider、PermissionGuard、Repository和序列化耗时，再决定优化 |
| 前端CORS或401 | 检查API地址、允许源、Token保存/过期和浏览器网络面板 |
| 测试通过但演示失败 | 对比测试数据库与演示数据库URL、Seed版本和前端环境变量 |

## 15. 需要用户确认的技术决定

以下均给出推荐结论，用户确认整个M1方案即表示接受；如不同意可逐项调整：

1. **新旧隔离**：推荐新后端统一放`app/`，旧`agent/api/tools`保留但M1不导入、不删除。
2. **Redis**：推荐M1不启动，只用PostgreSQL；Redis延后到需要Celery长任务的M4。
3. **前端**：推荐在现有空`frontend/`内建立最小Next.js + TypeScript页面。
4. **用户样本**：推荐三类角色全部建模，使用四个账号（负责人、选品人员、DE运营、FR运营）验证最小权限。
5. **数据库查询**：推荐只用固定Repository和受控条件，M1完全禁止模型生成SQL。
6. **模型策略**：推荐Mock为默认可重复测试路径，Qwen为可选冒烟路径；无Key不阻塞M1。
7. **流程**：推荐最小LangGraph固定图，不启用Supervisor、Worker、Skill或循环Tool Agent。
8. **通信**：推荐同步HTTP；SSE延后到确有流式或长任务需求时。
9. **演示数据解释**：推荐允许候选新品`LR-TL-MUSH-OR01`存在合成的海外仓预备库存，同时继续明确“无真实销售”。
10. **步骤数**：推荐按21个小步骤逐个说明、实现、验证和更新进度，不批量授权后续步骤。

除了Docker/Node/Python可用性和本地端口需要开工后实际检查，当前没有必须先提供的外部凭据。千问Key可以到M1-16再决定是否配置。

## 16. 本次方案编写记录

### 2026-08-28｜M1-PLAN-01｜编写并评审M1详细实施方案

**状态：已完成**

**目标**

基于总体设计和真实旧代码，明确M1边界、迁移策略、数据表、Tool/Harness/Provider/LangGraph/API/前端设计、21个单步顺序、验证方法和完成标准。

**本次修改文件**

- `docs/progress/M1/M1_INVENTORY_QUERY.md`：创建M1详细实施方案和本记录；
- `docs/PROJECT_PROGRESS.md`：同步当前步骤、M1链接和方案摘要。

**调用链位置**

本次属于设计与项目治理层，没有修改“前端→API→Schema→Service→Model→PostgreSQL”任何运行代码。文档规划覆盖了整条未来链路，但不代表链路已经实现。

**验证方法与实际结果**

- 文件存在性检查通过：本文件已创建，总进度看板已更新；
- 12项必需内容关键词检查全部为`True`，包括阶段状态、现状、目标、不做内容、前置条件、调用链、实施步骤、完成标准、风险、确认问题和禁止开发声明；
- 使用正则`^### M1-[0-9]{2}｜`实际识别到21个步骤，编号从M1-01连续到M1-21；
- 两份本次修改文档共识别到22个代码围栏标记，为偶数，未发现未闭合围栏；
- 逐文件检查Markdown标题层级，未发现跨级标题；未发现非Markdown硬换行用途的行尾空白；
- 逐个解析两份文档中的本地Markdown链接，5次引用的目标均存在；
- 未发现`<<<<<<<`、`=======`、`>>>>>>>`合并冲突标记；
- `git diff --check`未报告空白错误，只提示Windows工作区未来可能把`PROJECT_PROGRESS.md`从LF转换为CRLF；
- `git status --short`只显示`docs/PROJECT_PROGRESS.md`被修改、`docs/progress/M1/M1_INVENTORY_QUERY.md`为新文件，没有M1运行代码变更；
- `git diff --stat`只统计已跟踪的总看板，不会包含尚未跟踪的新M1文件，因此不把该统计当作文档总变更量证明。

**能够证明**

- 方案文件具备要求的结构、21个小步骤、验证矩阵、风险和确认停止点；
- 总看板与阶段文件的状态均为“待确认”，链接有效；
- 本次工作范围只包含两份Markdown文档，没有开始M1运行代码；
- 被检查的本地链接、代码围栏、冲突标记和Git空白规则没有发现结构性问题。

**不能证明**

- 任何M1运行代码已经实现；
- PostgreSQL、千问、FastAPI、Next.js或端到端链路能够运行；
- 方案中的暂定性能和安全目标已经达到。

**风险或问题**

- 总体设计的候选顺序曾包含M1启动Redis，本方案基于实际范围建议延后，需要用户随整体方案确认；
- 21个步骤仍需用户确认后才能开始第1步。

**下一步**

用户已于2026-08-28明确要求“开始进入M1-01”；方案确认停止点已经解除，后续按单步规则推进。
