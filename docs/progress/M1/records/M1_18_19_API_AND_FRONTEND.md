# M1-18 至 M1-19：FastAPI 与 Next.js

> 本文件保存从迁移前单文件中拆出的完整历史方案、实施日志与验证证据。
> 当前状态和阅读入口见 [M1入口](../M1_INVENTORY_QUERY.md)。

### 2026-08-28｜M1-18｜实现FastAPI登录、会话、聊天和Evidence接口

**状态：已完成**

**本步解决的问题**

M1-17只能由Python测试代码直接调用，浏览器或普通HTTP客户端还没有正式入口。本步把认证、会话、LangGraph和Evidence接到版本化FastAPI接口，并用一个请求级事务保证：成功时用户消息、助手回答和Evidence一起提交，失败时业务数据一起回滚；独立Trace仍保留失败原因。

FastAPI可以理解为“后端服务门口”。JWT Bearer是登录后每次请求出示的短期数字通行证；它只指出用户和租户，后端每次仍重新查询PostgreSQL获得最新账号状态、角色和市场范围。同步HTTP表示客户端发送一个问题后等待完整答案一次返回；M1没有实现SSE逐字流式输出。

**输入、输出和上下游**

- 输入：登录邮箱/密码，Bearer Token，可选会话标题，自然语言问题，URL中的会话ID或Evidence ID；
- 输出：严格JSON登录结果、当前用户、会话、完整聊天回答、Evidence摘要/详情，或者统一`ApiErrorResponse`；
- 上游：M1-12认证与RunContext、M1-17 LangGraph；
- 下游：M1-19 Next.js将只消费这些HTTP合同，不直接访问数据库或Agent内部对象；
- 成功聊天响应包含`trace_id`、实际Tool名称、耗时、回答和Evidence；模型仍只建议Tool，后端才执行Harness、Repository和PostgreSQL查询。

**公开接口**

| 方法与路径 | 用途 | 主要保护 |
|---|---|---|
| `POST /api/v1/auth/login` | 演示账号登录并取得JWT | Argon2密码校验、统一401 |
| `GET /api/v1/me` | 查看Token对应的最新身份 | 每次重新读取账号状态、角色和市场范围 |
| `POST /api/v1/threads` | 创建当前用户自己的聊天会话 | JWT、tenant和user自动取自可信身份 |
| `POST /api/v1/threads/{thread_id}/messages` | 同步执行一次库存Agent查询 | 会话归属、预算、权限、Trace、请求事务 |
| `GET /api/v1/evidence/{evidence_id}` | 查看数据库Evidence详情 | tenant过滤和市场范围复核，越权与不存在统一404 |

**关键技术决定与边界**

- 所有公开业务接口使用`/api/v1`前缀并进入OpenAPI；CORS仅允许配置中的前端来源，当前为`http://localhost:3000`；
- 登录之外的接口使用HTTP Bearer Token；Token伪造、过期、账号禁用或缺失均返回401并带`WWW-Authenticate: Bearer`；
- 创建RunContext前必须用固定Repository查询确认Thread属于当前tenant、当前user且仍为active；不能信任URL里的UUID；
- Evidence先按tenant固定查询，再检查记录中的市场范围是当前用户市场范围的子集；跨租户、跨市场和不存在都返回同样404，避免泄露记录是否存在；
- 对话和Evidence Repository只接受受控字段，使用SQLAlchemy固定条件及事务内`statement_timeout`，不接受模型或前端提供SQL；
- 同步SQLAlchemy Session由异步请求依赖创建、使用和关闭在同一事件循环线程，避免M1-17指出的跨线程共享；M1查询很短，尚未改造成异步数据库驱动；
- 请求依赖在成功响应发送前`commit`，路由或提交失败则`rollback`并关闭Session；LangGraph失败也先回滚业务事务，Trace使用独立短事务保留；
- Provider按请求创建；Qwen Provider自己创建的HTTP客户端会在请求后关闭，Mock不联网；
- Agent结果增加`duration_ms`，API只返回安全执行摘要，不暴露节点内部状态、原始SQL、密码、Token或异常堆栈；
- M1继续使用一次返回完整结果的同步HTTP。库存查询最多两次模型和两次Tool、默认总预算8秒，暂时没有足够长的任务需要SSE；SSE属于后续体验优化，不在本步扩范围。

**修改文件与职责**

- `app/main.py`：注册版本化路由、统一错误处理和现有CORS；
- `app/api/dependencies.py`：请求级数据库事务、Bearer身份刷新、Provider生命周期，以及会话/Evidence Service装配；
- `app/api/errors.py`：把业务错误、请求格式错误和未知错误映射为安全JSON及401/403/404/409/422/429/500/503/504；
- `app/api/routers/auth.py`：登录和`/me`；
- `app/api/routers/threads.py`：创建会话、核验归属、保存消息、构造LangGraph并返回同步回答；
- `app/api/routers/evidence.py`：Evidence详情入口；
- `app/repositories/conversation.py`：固定创建/读取Thread和写入Message；
- `app/repositories/evidence.py`：按tenant固定读取Evidence；
- `app/services/conversation.py`：Thread所有权和消息保存规则；
- `app/services/evidence.py`：在既有Evidence写入之外增加读取、Schema还原和市场范围检查；
- `app/core/errors.py`、`app/schemas/common.py`：增加Thread/Evidence不存在、请求提交和图终态等安全错误合同；
- `app/agents/state.py`、`app/agents/graphs/inventory_query.py`：在公开Agent结果中提供真实预算耗时，并把Provider超时标为`timed_out`；
- `tests/integration/test_m1_api.py`：真实PostgreSQL HTTP闭环、越权、超时、OpenAPI和CORS测试；
- `tests/integration/test_database_connection.py`：使请求事务探针与M1异步路由采用同一线程模型；
- `README.md`、本阶段记录和总进度：同步M1-18可运行范围和停止点。

**调用链位置**

```text
前端（尚未实现；当前可用HTTP客户端或OpenAPI代替）
→ FastAPI API（本步）
→ Pydantic Schema
→ 会话Service / LangGraph
→ ModelProvider提出受控Tool建议
→ Harness审核并执行Agent Tool
→ 商品/库存/Evidence Service
→ 固定Repository
→ SQLAlchemy Model（ORM）
→ PostgreSQL合成演示数据
→ Evidence与回答按JSON返回
```

**验证方法与实际结果**

1. OpenAPI实际包含5个M1接口，允许来源`http://localhost:3000`的CORS预检成功；
2. DE运营真实登录并调用`/me`，返回最新DE市场范围；缺Token和错误密码返回安全401，非法空标题返回统一422；
3. 登录后创建Thread并发送“德国仓蘑菇灯还有多少可售库存？”，HTTP 200返回可售125、合成数据说明、两个Tool名称、trace和一个Evidence摘要；
4. 使用返回的Evidence ID调用详情接口，真实返回`available=125`、DE访问范围和`synthetic_data=true`；
5. FR运营使用DE运营的Thread ID返回`THREAD_NOT_FOUND/404`；FR运营读取DE Evidence也返回`EVIDENCE_NOT_FOUND/404`；
6. DE运营询问法国库存时返回`FORBIDDEN/403`并携带trace，不返回库存或Evidence；
7. 注入确定性Provider超时后返回`PROVIDER_ERROR/504`并携带trace；
8. 请求事务提交、回滚、提交失败和连接释放原有专项测试继续通过，路由与Session保持同一异步请求线程；
9. M1 API专项5项通过；全量`pytest -q`共168项通过、1项真实Qwen付费冒烟按设计跳过；
10. Ruff通过，95个Python文件格式正确，Mypy检查63个`app/scripts`源文件无问题，Python编译和依赖检查通过；PostgreSQL 17.11容器健康，Alembic保持`20260828_0003 (head)`且无迁移差异；
11. 最终重新执行确定性Seed，数据库恢复为用户4条、Thread/AgentRun/ToolCall/Evidence各0条，关键答案仍为125；README、总进度和M1阶段文档的代码围栏及相对链接通过检查，`git diff --check`通过且只提示Windows未来可能转换LF/CRLF，未提交或推送Git。

**能够证明**

- 普通HTTP客户端已经能完成“登录→创建会话→自然语言库存查询→125回答→Evidence详情”的完整后端闭环；
- JWT身份会在每次请求刷新，会话和Evidence不能仅凭猜中UUID越权访问；
- 成功回答、数据时间、数据库证据、Tool摘要和trace已经通过稳定JSON合同交给未来前端；
- 模型没有获得数据库连接或自由SQL入口，仍只返回受控Tool建议；
- 已覆盖的401、403、404、422、503/504和请求事务行为有可重复测试。

**不能证明**

- 浏览器页面已经可用；Next.js登录和聊天页属于M1-19；
- 真实Qwen账号和网络可用；付费冒烟仍按设计跳过；
- SSE流式输出、长任务并发和高负载性能可用；M1采用短查询同步HTTP；
- 所有坏情况已覆盖；非法SKU、重复SKU、无库存和数据库故障的完整HTTP故障矩阵属于M1-20；
- 真实Amazon或公司数据已经接入；当前仍全部是合成演示数据。

**常见问题与优先排查方向**

- 401：先检查`Authorization: Bearer <token>`格式、Token是否过期，再检查Seed账号是否active；
- 404 Thread：检查Thread是否由当前登录用户创建且状态为active，不要绕过归属检查；
- 403市场越权：检查`/me`返回的最新`market_scopes`和问题解析出的市场；
- 404 Evidence：先检查Evidence所属tenant和`access_scope.market_codes`，不要把404改成能泄露跨用户记录的错误；
- 504：区分模型Tool建议超时和PostgreSQL statement timeout，用返回错误码和AgentRun/ToolCall Trace定位；
- 返回成功但刷新后消息或Evidence消失：检查请求依赖是否在响应发送前commit，以及是否发生提交期约束错误；
- API返回500：先查服务端日志和Trace安全错误，不要把原始数据库异常直接加入响应。

**下一步**

停止开发并等待用户理解和确认M1-18。只有用户明确回复“确认M1-18，可以进入M1-19”后，才实现最小Next.js登录和证据聊天页。

### 2026-08-28｜M1-19｜实现最小Next.js登录和证据聊天页

**状态**

已完成并验证；等待用户确认后才能进入M1-20。

**本步开始前缺少什么**

M1-18已经把“登录→创建会话→自然语言查询→返回125及Evidence”的后端接口跑通，但普通用户只能使用OpenAPI或命令行，尚没有真正的桌面聊天页面。本步只补展示和交互层，不改库存计算、权限、Agent流程或数据库结构。

**输入、输出和上下游**

- 输入：M1-18的登录、当前身份、创建会话、同步聊天和Evidence详情JSON合同；
- 输出：一个可在桌面浏览器中操作的登录页和三栏工作台；
- 上游：用户输入账号、密码和自然语言问题；
- 下游：前端API客户端调用FastAPI，后端继续经过Schema、Service、LangGraph、Harness、Model和PostgreSQL；
- 页面不保存或计算库存数字，只展示后端返回的答案与Evidence。

**用大白话解释运行过程**

用户先在网页选择演示账号并输入密码。登录成功后，页面向后端确认“我是谁、能看哪个市场”，再建立一条聊天会话。用户输入“德国仓蘑菇灯还有多少可售库存？”并按Enter，页面进入查询中状态，等待同步HTTP请求返回；后端完成既有Agent流程后，页面把回答显示在中间，把Evidence编号、SKU、仓库、数据时间、125及来源定位显示在右侧。Shift+Enter只换行，不发送；请求未结束时不能重复点击发送。

**设计与范围决定**

- 使用Next.js 16的App Router；`app/page.tsx`保持服务端页面，只有需要状态和事件的工作台组件使用客户端模式；
- 采用“证据工坊”视觉方向：墨黑、纸白、橙色提示、蓝色数据库证据，并用带虚线装订感的Evidence票据作为辨识点；
- 桌面端采用“身份/会话→聊天→Evidence”三栏，窄屏自动改为单栏；
- 登录Token只保存在当前React内存中，不写入`localStorage`，刷新页面需要重新登录；
- M1继续使用同步HTTP，不提前实现SSE、流式消息、文件上传、复杂导航或全局状态框架；
- 所有页面明确显示“合成演示数据”，避免被误认为真实Amazon数据。

**新增或修改文件与职责**

- `frontend/package.json`、`frontend/package-lock.json`：固定Next.js、React、TypeScript、ESLint、Vitest和组件测试依赖及命令；
- `frontend/next.config.ts`、`frontend/tsconfig.json`、`frontend/eslint.config.mjs`、`frontend/vitest.config.ts`：生产构建、类型、代码规范和测试配置；
- `frontend/.env.example`：声明可公开给浏览器的后端API基础地址，不保存秘密；
- `frontend/app/layout.tsx`、`frontend/app/page.tsx`：最小页面壳和入口；
- `frontend/app/globals.css`：三栏布局、Evidence票据、响应式、键盘焦点和减少动画规则；
- `frontend/components/inventory-workbench.tsx`：登录、会话、问题发送、状态、错误、回答和Evidence交互；
- `frontend/lib/api.ts`：对M1-18接口的强类型调用和安全错误解析；
- `frontend/tests/setup.ts`、`frontend/tests/inventory-workbench.test.tsx`：组件清理和四条关键交互测试；
- `frontend/AGENTS.md`、`frontend/CLAUDE.md`：Next.js生成的本目录协作和版本注意事项；
- `.gitignore`：忽略前端依赖、构建产物、本地环境文件、TypeScript缓存和自动生成的`next-env.d.ts`；
- `README.md`、本阶段记录和总进度：增加前端启动方法、能力边界和M1-19验证结论。

**调用链位置**

```text
Next.js前端（本步：收集输入、发HTTP、展示回答与Evidence）
→ FastAPI API（M1-18）
→ Pydantic Schema（M1-08）
→ 会话Service / LangGraph / Harness / Agent Tool（M1-10至M1-17）
→ SQLAlchemy Model与受控Repository（M1-03至M1-11）
→ PostgreSQL合成演示数据（M1-02至M1-07）
→ JSON回答与Evidence返回前端
```

这里前端没有绕过任何一层，也没有直接连接PostgreSQL。

**验证方法与实际结果**

1. `npm test`：1个测试文件、4项组件交互测试全部通过；覆盖登录与身份展示、空状态、Enter发送、Shift+Enter换行、查询中禁用重复发送、125回答、Evidence自动加载和权限错误安全展示；
2. `npm run typecheck`：通过，API合同与组件使用未发现TypeScript类型错误；
3. `npm run lint`：通过，ESLint未发现问题；
4. `npm run build`：Next.js 16.3.3生产构建成功，`/`和`/_not-found`静态页面生成完成；
5. `npm ls --depth=0`：顶层依赖树完整；`npm audit --audit-level=high`：0个已知漏洞；
6. 前后端实际启动后，后端`/health`返回`database=connected`，前端根页面HTTP 200并包含“每个库存数字”和“合成演示数据”文案，前后端日志没有启动错误；
7. 当前执行环境没有可用的受控浏览器实例，因此没有把HTTP 200或组件测试冒充成真实浏览器点击与视觉截图；该验证明确安排在M1-20；
8. 全量后端`pytest -q`共168项通过、1项真实Qwen付费冒烟按设计跳过；Ruff、95个Python文件格式、63个`app/scripts`源文件Mypy、Python编译和依赖检查全部通过；
9. PostgreSQL 17.11容器健康，Alembic保持`20260828_0003 (head)`；重新执行确定性Seed后，数据库为用户4条、Thread/AgentRun/ToolCall/Evidence各0条，DE-FRA的`LR-TL-MUSH-OR01`可售数量仍为125；
10. 从`http://localhost:3000`实际请求前端返回HTTP 200，后端健康检查返回`database=connected`，浏览器来源对应的CORS预检返回允许`http://localhost:3000`；
11. README、总进度和M1阶段文档的代码围栏及相对链接通过检查，`git diff --check`通过且仅有Windows未来可能转换LF/CRLF的提示；未提交或推送Git。

**能够证明**

- 前端可以按强类型合同调用M1登录、身份、会话、聊天和Evidence接口；
- 关键交互状态和成功/权限错误展示具有可重复组件测试；
- 前端生产包能通过类型检查、代码规范和正式构建；
- 页面不会自己计算125，也不会把登录Token长期写入浏览器存储；
- 页面结构、样式和响应式规则已经实现，并明确标注合成演示数据。

**不能证明**

- 当前还不能证明真实浏览器中每个按钮、键盘焦点和三栏视觉效果都正确，因为本次没有可用的受控浏览器实例；
- 组件测试使用Mock API，不能单独证明真实前后端连起来后所有故障分支都正确；
- 不能证明真实Qwen可用，付费冒烟仍需API Key并显式开启；
- 不能证明高并发、SSE流式输出或移动端完整产品体验；这些不属于M1-19。

**常见问题与优先排查方向**

- 页面能打开但登录失败：先确认后端在`127.0.0.1:8000`运行、已执行Seed、密码等于根目录`.env`中的`M1_DEMO_PASSWORD`；
- 浏览器提示跨域：请从`http://localhost:3000`打开页面，不要把前端地址换成未加入后端CORS白名单的域名；
- 页面显示网络错误：检查`frontend/.env.local`中的`NEXT_PUBLIC_API_BASE_URL`，修改后要重启Next.js开发服务；
- 登录后刷新又回到登录页：这是M1有意采用内存Token的结果，不是数据库丢失；
- 右侧没有Evidence：先看聊天区是否返回安全错误，再用trace定位Provider、权限、Tool或数据库层；失败回答不会伪造Evidence；
- 构建失败：先确认Node.js至少20.9，再删除可重新生成的`.next`缓存并检查`npm install`是否成功，不要修改后端业务逻辑来规避前端依赖问题。

**下一步**

停止开发并等待用户理解和确认M1-19。只有用户明确回复“确认M1-19，可以进入M1-20”后，才补齐故障矩阵、真实前后端集成和浏览器端到端回归。
