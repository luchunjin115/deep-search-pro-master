# M1-12 至 M1-15：身份、权限、Harness 与 Agent Tool

> 本文件保存从迁移前单文件中拆出的完整历史方案、实施日志与验证证据。
> 当前状态和阅读入口见 [M1入口](../M1_INVENTORY_QUERY.md)。

### 2026-08-28｜M1-12｜实现登录、JWT和RunContext

**状态：已完成**

**本步解决的问题**

M1-07已经在PostgreSQL保存四个演示账号、Argon2密码哈希、角色和市场范围，但此前没有代码能够验证登录，也没有可信方法把用户身份传给后续PermissionGuard和Agent执行。本步建立固定身份查询、认证Service、短期签名JWT和强类型RunContext，让后端能够回答“当前是谁、属于哪个租户、拥有哪些当前角色和市场范围、这次会话和执行编号是什么”。

**输入、输出和上下游**

- 输入：M1-08 `LoginRequest`中的规范化邮箱和密码；后续解析输入为JWT；建立运行上下文时再输入可信`thread_id`和可选`trace_id`；
- 输出：`LoginResponse`、数据库刷新后的`CurrentUser`，以及不可变`RunContext`；
- 上游：M1-04身份表、M1-07 Seed账号、M1-08认证Schema和M1-03请求级数据库事务；
- 下游：M1-13 PermissionGuard、M1-14 Trace/预算、M1-17 LangGraph和M1-18认证/聊天API；
- 本步不接收模型输出、Prompt、SQL、Tool名称或待查询业务市场，不执行具体Tool权限判断。

**用大白话解释运行过程**

认证Service像“后端门卫”，JWT像“有后端防伪签名且会过期的临时身份证”，RunContext像“本次任务随身携带的工作证袋”：

```text
邮箱和密码
→ Schema清理邮箱大小写和空格，并保护密码不被普通序列化
→ IdentityRepository按固定SELECT读取唯一账号、租户、角色和市场范围
→ SecurityService用Argon2核对密码哈希
→ AuthService组装CurrentUser并签发60分钟JWT

后续请求携带JWT
→ 核对HS256签名、签发方、接收方、用途、签发时间和过期时间
→ 使用JWT中的user_id + tenant_id重新查询PostgreSQL
→ 检查账号仍为active，并取得最新角色和市场范围
→ 加入thread_id与trace_id，建立不可变RunContext
```

JWT故意不保存角色和市场范围。这样管理员在数据库中禁用用户或改变范围后，不需要等旧Token过期：下一次解析Token时重新查库，就会立即采用新状态。`thread_id`代表本项目的聊天会话；`trace_id`代表这一轮具体执行，未来用于关联AgentRun、ToolCall和Evidence。

**技术决定与边界**

- 密码继续使用Seed已采用的Argon2哈希验证，数据库和响应都不返回明文密码或哈希；数据库哈希格式损坏时转换为安全内部数据错误；
- 找不到邮箱、密码错误或同一邮箱意外匹配多个租户身份，都使用安全登录失败，不猜租户；不存在唯一用户时仍执行一次虚拟密码校验，减少通过响应时间判断邮箱是否存在的差异；虚拟Argon2哈希只在进程加载时生成一次，避免每个请求重复执行无意义的哈希生成；
- 禁用用户在密码登录和Token刷新两条路径都会得到`UNAUTHENTICATED`，不能仅依赖Token过期；
- JWT只包含`sub(user_id)`、`tenant_id`、唯一`jti`、`token_type=access`、签发方、接收方、签发时间和过期时间；不包含密码、角色、市场权限、数据库连接或业务数据；
- 解码时固定算法白名单为配置中的`HS256`，并强制校验全部必需声明、签名、过期时间、签发方和接收方；伪造、过期、用途错误、字段缺失或用户已删除均安全拒绝；
- `IdentityRepository`使用固定SQLAlchemy SELECT和statement timeout读取身份，不接受SQL字符串；Token中的tenant必须与数据库用户所属tenant同时匹配；
- `RunContext`使用冻结dataclass，角色和范围转换为tuple，建立后不能被业务代码原地修改；
- `ContextVar`只在当前请求/异步任务中绑定RunContext，并在上下文结束时恢复旧值，避免并发用户共享全局身份；
- `app/api/dependencies.py`只增加请求级`AuthService`组装能力。公开`POST /api/v1/auth/login`、`GET /api/v1/me`、Bearer HTTP解析和错误状态码映射仍属于M1-18，本步没有提前创建路由；
- 本步没有验证Thread属于当前用户；RunContext只接受未来会话Service/API已经核验过的可信`thread_id`。Thread创建和所有权校验留在M1-18；
- 本步没有实现ToolRegistry、PermissionGuard、ExecutionBudget、Trace写入器、Agent Tool、Provider、LangGraph、聊天API或前端。

**修改文件与职责**

- `app/core/security.py`：Argon2密码验证、虚拟密码校验、JWT签发和严格解析；
- `app/core/errors.py`：新增登录失败、无效Token、禁用账号、身份数据合同和身份数据库安全错误；
- `app/repositories/identity.py`：固定查询邮箱或Token subject，并聚合数据库当前角色与市场范围；
- `app/repositories/__init__.py`：导出身份Repository及只读记录；
- `app/services/auth.py`：编排登录、Token身份刷新、账号状态和严格`CurrentUser`转换；
- `app/services/__init__.py`：导出认证Service接口；
- `app/runtime/context.py`、`app/runtime/__init__.py`：建立不可变RunContext及任务隔离的绑定/读取接口；
- `app/api/dependencies.py`：在现有请求级Session上组装可供未来路由注入的AuthService；
- `tests/unit/test_auth_service.py`：验证登录分支、JWT安全、数据库刷新、错误脱敏、RunContext不可变及并发隔离；
- `tests/integration/test_auth_service.py`：使用真实Seed和PostgreSQL验证四账号、错误密码、禁用用户及Token后的范围刷新；
- `README.md`：说明认证内核、JWT最小载荷、数据库刷新、RunContext和未开放HTTP路由的边界；
- `docs/progress/M1/M1_INVENTORY_QUERY.md`、`docs/PROJECT_PROGRESS.md`：记录实际实现、验证结论和M1-13前停止点。

**调用链位置**

```text
前端（未经过；尚无登录页面）
→ API（只准备AuthService依赖，尚无公开登录/me路由）
→ Schema（LoginRequest / LoginResponse / CurrentUser）
→ Service（本步：密码验证、JWT签发/解析、数据库身份刷新）
→ Repository（本步：固定身份SELECT）
→ Model（Tenant / User / UserRole / Role ORM）
→ PostgreSQL（真实读取密码哈希、状态、角色和市场范围）

数据库刷新后的CurrentUser
→ RunContext（本步：user/tenant/roles/scopes/thread/trace）
→ PermissionGuard（未经过；M1-13）
```

本步不经过千问或任何LLM。模型不会看到密码、Token、密码哈希，也不能提供tenant、角色或市场范围来覆盖数据库身份。

**验证方法与实际结果**

1. 正确邮箱密码生成`LoginResponse`，有效期为3600秒，返回用户不包含密码；解码后的JWT user/tenant正确，且声明中没有roles或market_scopes；
2. 错误密码、不存在邮箱和相同邮箱多身份均返回`InvalidCredentialsError`，不选择第一条用户；
3. 禁用账号即使密码正确也被拒绝；损坏的密码哈希转换为安全身份数据合同错误；
4. 过期Token、用另一密钥签名的伪造Token和数据库中已不存在的subject均返回`InvalidAccessTokenError`；
5. Token签发后修改Fake数据库角色/市场范围，解析原Token得到新范围；随后禁用用户，同一Token立即被拒绝；
6. 模拟身份数据库`OperationalError`，公开错误JSON不含测试SQL或驱动详情；
7. RunContext字段与数据库刷新用户一致，显式修改冻结字段被拒绝；离开绑定区间后上下文被清除；
8. 两个异步任务同时绑定不同用户，主动让出执行权后仍各自读取原用户，证明ContextVar并发隔离；
9. 真实PostgreSQL中owner、scout、DE运营和FR运营四个Seed账号全部使用Argon2密码登录成功，分别返回`company_owner/DE+FR`、`product_scout/DE+FR`、`amazon_operator/DE`和`amazon_operator/FR`；
10. 真实数据库事务内把DE运营范围改为FR后，旧Token解析出FR；再禁用用户后旧Token被拒绝；事务回滚后不污染Seed；
11. 专项单元与集成测试共11项通过；全量`pytest -q`共89项通过；Ruff检查通过且61个Python文件格式正确；Mypy检查37个`app/scripts`文件无类型问题；编译和`pip check`通过；
12. PostgreSQL 17.11容器为`healthy`；Alembic仍是`20260828_0003 (head)`，`alembic check`确认没有模型/迁移差异；本步无需新迁移；
13. 全量测试后重新执行确定性Seed，真实执行`Schema→AuthService→IdentityRepository→PostgreSQL→JWT解析→RunContext`：大写且带空格的德国运营邮箱规范化成功，得到`amazon_operator + DE`，Token有效期3600秒，Context用户和租户均与数据库一致；
14. 最终数据库仍为4个用户、4条角色分配，agent_runs、tool_calls、evidences均为0；登录和Context演示没有写入假运行记录；
15. 第一轮专项测试曾因测试辅助函数重复使用`password_hash`参数名而在进入业务代码前失败，修正测试夹具命名后同组11项全部通过；该失败不是认证行为失败；
16. Markdown结构、围栏、内部链接和Git差异将在本步最终文档检查中验证；未提交或推送Git。

**能够证明**

- 后端能够使用真实Seed密码哈希验证四个演示账号，并签发、解析有签名和过期时间的短期JWT；
- JWT只充当数据库身份指针，不把可变角色和范围固化在Token中；账号禁用、角色或市场范围变化会在后续请求立即生效；
- 伪造、过期、字段非法或数据库subject不存在的Token不能建立可信身份；
- RunContext由数据库刷新后的CurrentUser建立，字段不可变，并且不同并发任务不会互相覆盖身份；
- 身份查询和认证错误不会把密码、哈希、SQL或驱动详情暴露给未来API。

**不能证明**

- 用户现在能通过浏览器或HTTP接口登录；公开login/me路由留在M1-18；
- RunContext中的thread已经经过所有权校验；Thread API和归属检查尚未实现；
- DE运营查询DE一定允许、FR运营查询DE一定拒绝；角色和范围已装入Context，但M1-13 PermissionGuard尚未执行规则；
- Agent Tool、预算、Trace、LangGraph、千问/Mock、聊天API或前端已经接入身份；
- JWT撤销列表、Refresh Token、单点登录、跨租户同邮箱选择器或生产密钥轮换已经实现；这些均不属于M1最小范围；
- M1库存查询用户闭环已经完成。

**常见问题与优先排查方向**

- 正确密码仍提示失败：先检查邮箱规范化、Seed是否执行、`.env`中的`M1_DEMO_PASSWORD`是否与已有哈希一致，再检查账号是否唯一；
- Token刚签发就无效：检查`JWT_SECRET_KEY`、算法、系统时间、issuer/audience和运行进程是否使用同一配置；
- Token有效但用户被拒绝：查询users.status是否为active，并检查JWT中的user/tenant是否仍对应数据库同一行；
- 角色或市场为空：检查`user_roles`与`roles`外键、Seed分配以及CurrentUser严格Schema；不要把角色临时塞进JWT绕过数据库问题；
- 两个请求身份串线：检查是否使用模块级可变变量保存用户；正式执行必须通过`bind_run_context`并在`finally`语义下恢复ContextVar；
- Context缺少thread：M1-18应先创建或核验Thread所有权，再建立Context，不能直接信任URL中的thread_id；
- 身份数据库超时：检查statement timeout和连接状态，失败事务必须回滚后再使用Session；
- 想立即用HTTP测试登录：当前路由尚未实现，不要把`/health`当作认证接口；等M1-18统一实现OpenAPI、Bearer解析和401响应。

**下一步**

停止开发并等待用户理解和确认本步结果；用户明确回复“确认M1-12，可以进入M1-13”后，才进入M1-13“实现ToolRegistry和PermissionGuard”。

### 2026-08-28｜M1-13｜实现ToolRegistry和PermissionGuard

**状态：已完成**

**本步解决的问题**

M1-12已经把数据库当前用户、租户、角色和市场范围放入可信RunContext，但此前没有程序判断某个Tool是否正式登记、是否只读、当前用户角色能否使用、目标tenant是否一致以及请求市场是否越界。本步建立不可运行任意名称的ToolRegistry和确定性PermissionGuard，让权限判断由服务端代码执行，而不是依赖Prompt或模型自觉。

**输入、输出和上下游**

- 输入：M1-12可信`RunContext`、请求的Tool名称、后端绑定的`target_tenant_id`和可选`market_code`；
- 输出：不可变`PermissionGrant`，或者安全的`FORBIDDEN` `ApplicationError`；
- 上游：M1-08两个Tool Schema、M1-12数据库刷新身份和RunContext；
- 下游：M1-14统一执行预算/Trace和M1-15两个Agent Tool；
- 模型和前端不能提交allowed_roles、side_effect、version、timeout或tenant来修改Registry策略。

**用大白话解释运行过程**

ToolRegistry像“公司批准的工具白名单和说明书”，PermissionGuard像“工具间门口的门禁”：

```text
RunContext + Tool名称 + 后端目标tenant + 请求市场
→ Registry查Tool说明书
├─ 未登记：FORBIDDEN
→ 检查系统只读策略
├─ write：FORBIDDEN
→ 检查目标tenant是否等于登录tenant
├─ 不一致：FORBIDDEN
→ 检查用户角色是否与Tool允许角色有交集
├─ 无交集：FORBIDDEN
→ market范围Tool必须提供市场，并检查是否在RunContext.market_scopes
├─ 不在范围：FORBIDDEN
└─ 全部通过：返回PermissionGrant，未来执行器才可继续业务Service
```

德国运营的RunContext范围为DE，所以查询DE得到允许；法国运营范围为FR，所以查询FR允许、查询DE在进入库存Service前拒绝。权限判断不生成SQL，也不访问库存表。

**技术决定与边界**

- M1默认Registry严格只有`get_product_spec`和`search_inventory`，旧根目录`agent/`、`api/`、`tools/`不被导入；`execute_sql`等任意名称不存在回退入口；
- 每个Tool登记名称、描述、输入/输出Pydantic Schema、`1.0.0`版本、3000毫秒总超时、允许角色、数据范围和副作用等级；Registry构建后只读，重复名称、非法版本、非法超时、空角色集合或非Pydantic Schema被拒绝；
- 两个Tool均允许`company_owner`、`product_scout`和`amazon_operator`，最终可访问市场仍取RunContext中的数据库当前范围；
- `get_product_spec`读取租户公共商品目录，输入没有市场字段，因此使用`tenant`范围：检查登记、只读、tenant和角色；
- `search_inventory`使用`market`范围：除上述检查外，必须提供`market_code`且在用户范围内；
- `target_tenant_id`不是模型或Tool Schema字段，必须由未来服务端执行器绑定。即使它被错误传成另一个租户，Guard也会拒绝；真正Repository仍继续保留tenant查询条件，形成权限门禁和数据查询双重防线；
- M1系统级策略只允许`read`。测试构造的`write`元数据即使进入自定义Registry，PermissionGuard仍拒绝；默认Registry不存在写入Tool；
- 权限拒绝统一使用`FORBIDDEN/retryable=false`，分别标记`tool`、`tenant_id`或`market_code`字段，不返回允许角色清单、其他tenant信息、数据库数据或堆栈；
- 权限检查顺序先于业务Service是未来统一执行器必须遵守的合同。本步通过Fake下游调用验证拒绝后调用计数为0，但生产Tool执行器尚未在M1-15实现；
- 本步不建立`permissions`或`role_permissions`数据库表；M1最小策略随版本化Registry放在代码中，市场数据范围继续来自`user_roles.market_scopes`；
- 本步没有实现ExecutionBudget、Trace写入器、Tool执行器、两个Agent Tool函数、Provider、LangGraph、API或前端。

**M1默认Registry**

| Tool | 输入Schema | 输出Schema | 版本 | 超时 | 允许角色 | 范围 | 副作用 |
|---|---|---|---|---:|---|---|---|
| `get_product_spec` | `GetProductSpecInput` | `ProductSpecResult` | 1.0.0 | 3000ms | 三类角色 | tenant | read |
| `search_inventory` | `SearchInventoryInput` | `InventoryResult` | 1.0.0 | 3000ms | 三类角色 | market | read |

**修改文件与职责**

- `app/tools/registry.py`、`app/tools/__init__.py`：定义版本化Tool元数据、只读Registry和严格两个Tool的默认工厂；
- `app/runtime/permissions.py`：按Tool、只读、tenant、角色和市场顺序返回PermissionGrant或拒绝；
- `app/runtime/__init__.py`：导出PermissionGuard与PermissionGrant；
- `app/core/errors.py`：新增未注册Tool、角色、tenant、市场和系统只读策略的安全拒绝错误；
- `tests/unit/test_permissions.py`：验证Registry合同、非法元数据、各种拒绝、允许结果及拒绝先于Fake下游调用；
- `tests/integration/test_permissions.py`：从真实PostgreSQL登录四个Seed账号并验证当前角色/市场策略；
- `README.md`：说明双Tool白名单、权限交集、角色样本及尚未接入正式Tool执行器的边界；
- `docs/progress/M1/M1_INVENTORY_QUERY.md`、`docs/PROJECT_PROGRESS.md`：记录实际实现、验证结果和M1-14前停止点。

**调用链位置**

```text
前端（未经过）
→ API（未经过）
→ Schema（沿用两个Tool输入/输出合同）
→ RunContext（沿用M1-12可信身份）
→ ToolRegistry（本步：固定白名单和元数据）
→ PermissionGuard（本步：只读、tenant、角色和市场检查）
→ Service（未经过；只有允许后未来执行器才会调用）
→ Model/PostgreSQL业务数据（未经过）
```

真实身份集成测试会为JWT刷新读取PostgreSQL身份表，但PermissionGuard自身是纯内存确定性逻辑，不查询业务数据库、不调用模型，也不生成SQL。

**验证方法与实际结果**

1. 默认Registry名称稳定且严格等于`get_product_spec/search_inventory`，两项输入/输出Schema、版本、3000毫秒超时、三类角色、范围和`read`副作用与M1合同一致；
2. 重复Tool名称、`latest`非法版本、30001毫秒超时和空允许角色集合在Registry构建阶段被拒绝；
3. DE运营调用`search_inventory + DE + 同tenant`得到明确PermissionGrant，包含Tool、版本、tenant和市场；
4. 未注册`execute_sql`返回`FORBIDDEN`，测试中放在Guard之后的Fake数据库调用计数保持0；
5. 自定义owner-only Tool拒绝amazon_operator，跨tenant拒绝，DE运营请求FR拒绝，market范围Tool缺少市场也拒绝；
6. FR范围用户调用tenant范围`get_product_spec`无需伪造市场即可通过；自定义`write`副作用元数据被系统只读策略拒绝；
7. 真实PostgreSQL与Seed身份中，负责人和选品人员查询DE/FR均允许，DE运营查DE允许但查FR拒绝，FR运营查FR允许但查DE拒绝；四个账号均可调用同tenant商品规格Tool；
8. 真实DE运营传入另一个tenant ID被拒绝，证明Guard不只检查角色名；
9. 本步专项单元与集成测试共9项通过；全量`pytest -q`共98项通过；Ruff检查通过且66个Python文件格式正确；Mypy检查40个`app/scripts`文件无类型问题；编译与`pip check`通过；
10. PostgreSQL 17.11容器为`healthy`；Alembic仍是`20260828_0003 (head)`，`alembic check`无模型/迁移差异；本步只增加内存策略，无需数据库迁移；
11. 全量测试后重新执行确定性Seed，真实运行`PostgreSQL身份→登录/JWT→RunContext→PermissionGuard`：Registry只含两个Tool，DE运营查DE为true，FR运营查FR为true，FR运营查DE为`FORBIDDEN`；
12. 最终数据库仍为4个用户，agent_runs、tool_calls、evidences均为0，权限演示没有执行库存查询或制造假审计记录；
13. 专项首次规范检查只发现一个测试文件未使用导入，自动清理后Ruff与同组9项测试全部通过；权限行为没有失败；
14. Markdown结构、围栏、内部链接和Git差异将在最终文档检查中验证；未提交或推送Git。

**能够证明**

- 服务端默认可见的Agent Tool白名单严格只有两个，不存在任意SQL或写入Tool入口；
- 权限判断不依赖Prompt，能够使用数据库刷新后的角色、tenant和市场范围确定性允许或拒绝；
- 当前三类角色和四账号最小样本符合设计，尤其FR运营查询DE会得到安全`FORBIDDEN`；
- 跨tenant、市场越界、角色无交集、未注册Tool、缺失市场和非只读操作均有明确拒绝行为；
- 拒绝规则可以放在业务Service前执行，测试下游在拒绝后保持零调用。

**不能证明**

- 真实Agent Tool执行已经强制经过PermissionGuard；两个Tool函数和统一执行器要到M1-15实现；
- 拒绝已经写入`agent_runs/tool_calls`审计表；M1-14才实现基础Trace；
- ExecutionBudget、总时限、Tool次数或重复调用限制已经生效；
- 用户已经可以通过HTTP登录和发送聊天问题；
- 模型会选择正确Tool，或LangGraph会把市场参数传给Guard；
- 数据库Repository双重tenant/market过滤与Guard已经在一次完整Agent请求中联合验证；
- M1完整权限闭环或库存聊天闭环已经完成。

**常见问题与优先排查方向**

- 正常Tool提示未注册：检查调用名称是否与Registry完全一致，以及是否错误导入旧根目录`tools/`；不要增加任意名称回退；
- DE运营查询DE被拒绝：依次检查JWT数据库刷新、RunContext.market_scopes、请求`market_code`和`target_tenant_id`；
- FR运营可以查询DE：优先确认统一执行器是否在Service前调用Guard，其次检查market是否漏传、Registry的data_scope是否错误改为tenant；
- 角色正确仍被拒绝：检查Registry.allowed_roles与RunContext.roles是否有交集，以及角色是否来自数据库当前值；
- tenant不一致：检查目标tenant是否由服务端Context绑定，禁止从模型参数或前端JSON读取；
- 写入型Tool意外注册：默认Registry必须只从`create_m1_tool_registry`创建；即使自定义Registry存在write元数据，Guard仍应拒绝；
- Guard通过但Repository越权：继续检查Repository是否始终使用`context.tenant_id`和已授权market；Guard与查询过滤是双重防线，不能互相替代；
- 权限拒绝没有Trace：这是当前预期限制，M1-14才把允许/拒绝结果写入统一审计轨迹。

**下一步**

停止开发并等待用户理解和确认本步结果；用户明确回复“确认M1-13，可以进入M1-14”后，才进入M1-14“实现ExecutionBudget和基础Trace”。

### 2026-08-28｜M1-14｜实现ExecutionBudget和基础Trace

**状态：已完成**

**本步解决的问题**

M1-13只能判定某次Tool请求是否有权限，还不能阻止模型或Tool反复调用、限制整次运行时间，也不能把成功、拒绝、超时和错误稳定写入`agent_runs/tool_calls`。本步实现每次运行独立的ExecutionBudget、基础TraceRecorder和同步HarnessExecutor，让后续Provider/Tool必须先经过预算与权限，再执行受控回调，并保留脱敏审计。

**输入、输出和上下游**

- 输入：M1-12 RunContext、M1-13 Registry/PermissionGuard、预算配置、严格Tool输入或受控参数映射，以及确定性测试回调；
- 输出：允许执行时的`ToolExecutionResult + ToolExecutionContext`，或者安全`ApplicationError`；同时持久化AgentRun和ToolCall；
- 上游：RunContext、Tool元数据、权限策略、M1-06运行表；
- 下游：M1-15两个正式Agent Tool、M1-16 Provider调用计数和M1-17 LangGraph；
- 本步回调只用于验证Harness，不是正式`get_product_spec/search_inventory` Agent Tool实现。

**用大白话解释运行过程**

ExecutionBudget像“本次任务的次数和时间额度”，TraceRecorder像“独立保存的任务审计单”，HarnessExecutor像“把预算、门禁、记录和业务调用按固定顺序串起来的执行通道”：

```text
创建并提交running AgentRun
→ 模型调用前预留次数并更新model_call_count
→ Tool请求从自身严格参数提取market_code
→ 检查总时间、Tool次数和重复签名
→ PermissionGuard检查Tool/只读/tenant/角色/市场
├─ 预算或权限拒绝：提交denied/timeout ToolCall，不执行回调
└─ 允许：提交allowed + running ToolCall
   → 把已提交agent_run_id/tool_call_id交给业务回调
   → 成功、业务错误、数据库超时、Tool超时或未知异常分别安全收尾
→ AgentRun最终变为completed/failed/denied/timed_out
```

Trace使用独立短事务。即使业务Session后来回滚，已经记录的失败审计仍存在；成功库存Tool未来可以使用执行上下文中的真实ToolCall ID写Evidence。

**M1默认预算**

| 配置 | 默认值 | 作用 |
|---|---:|---|
| `EXECUTION_MAX_MODEL_CALLS` | 2 | 最多预留2次Provider调用 |
| `EXECUTION_MAX_TOOL_CALLS` | 2 | 库存链最多两个Tool尝试 |
| `EXECUTION_MAX_REPEAT_TOOL_CALLS` | 1 | 相同Tool+相同脱敏参数只能执行一次 |
| `EXECUTION_TOTAL_TIMEOUT_MS` | 8000 | 整次同步运行总时间预算 |
| Registry `timeout_ms` | 每Tool 3000 | 单个Tool回调上限 |

根据用户评审后的M1-16合同，商品名称路径预计使用2次受控模型建议、1次商品规格Tool和1次库存Tool；明确SKU路径可只用1次模型建议和1次库存Tool。两次上限只覆盖这条固定分支，不允许开放式循环规划。

**技术决定与边界**

- `ExecutionBudget`是每个AgentRun新建的内存对象，不使用全局计数；使用`time.monotonic`单调时钟，系统时间调整不会产生负耗时；测试可注入手动时钟而不真实等待8秒；
- 模型调用和Tool调用必须在真正下游动作前`reserve`；达到次数上限、总时间到期或相同签名重复时抛`BUDGET_EXCEEDED`；被拦截的重复/超限尝试不会执行回调，但仍记录一条拒绝ToolCall；
- 重复签名使用Tool名称和排序后的脱敏参数摘要生成SHA-256，只在内存中比较；Trace不存签名或原始敏感值；
- Executor只从Tool自身参数摘要提取`market_code`，不接受第二份独立市场参数，避免“Guard检查DE、业务参数查询FR”的双输入越权；`target_tenant_id`仍必须由服务端RunContext绑定；
- AgentRun和ToolCall通过专用`sessionmaker`的独立短事务提交，不与可能失败的业务Session共享失败状态；Thread必须在开始Run前已经提交；M1同步串行执行，不支持同一Run并行创建ToolCall，序号由已提交`tool_call_count + 1`产生；
- Trace参数最多20个顶层字段，嵌套最多2层、列表最多10项、字符串最多200字符；敏感字段名包含password/token/secret/api_key/authorization/connection/database_url/sql时统一写`[REDACTED]`；
- 未知回调异常由Harness边界转换成安全`INTERNAL_ERROR/Tool执行失败`，Trace不保存原始异常、堆栈、密码或SQL；已知ApplicationError只保存固定错误码和安全消息；
- `ToolExecutionContext`只暴露tenant、AgentRun ID、ToolCall ID和trace ID，未来库存Tool可据此建立Evidence外键；
- 同步Python无法在不破坏共享Session的情况下安全强杀正在运行的普通回调。本步在调用前和返回后检查总时间/单Tool时间，超时结果不返回并要求业务事务回滚；数据库查询仍由真实PostgreSQL `statement_timeout`中断，Provider未来使用HTTP客户端超时；
- `run_scope`保证只要AgentRun成功开始，就会在正常结果、已知业务错误或未知异常后写入终态；若Trace本身保存失败则返回安全`TracePersistenceError`，不继续假装审计成功；
- 本步没有实现两个正式Agent Tool、Provider、LangGraph、API、前端、跨进程预算、分布式锁、Checkpoint、重试恢复或并行Tool调度。

**修改文件与职责**

- `app/runtime/budget.py`：预算配置快照、模型/Tool次数、重复签名、总时间和单Tool时限判断；
- `app/runtime/trace.py`：参数脱敏、AgentRun/ToolCall独立事务持久化、终态和安全错误映射；
- `app/runtime/executor.py`：把预算、市场提取、PermissionGuard、Trace和确定性回调按固定顺序编排；
- `app/runtime/__init__.py`：导出Budget、Trace和Harness执行接口；
- `app/core/errors.py`：新增预算超限、Tool超时、未知Tool执行和Trace保存安全错误；
- `app/core/config.py`、`.env.example`：集中增加四项M1运行预算默认值；
- `tests/unit/test_app_baseline.py`：清理新增环境变量，保持配置测试不受开发者Shell污染；
- `tests/unit/test_budget.py`：验证默认预算、次数、重复、时限、非法配置和参数脱敏；
- `tests/integration/test_harness_trace.py`：使用真实PostgreSQL验证成功、拒绝、重复、模型超限、Tool/总时限、未知异常、独立审计事务和业务回滚；
- `README.md`：说明预算、Trace顺序、脱敏、事务和同步超时边界；
- `docs/progress/M1/M1_INVENTORY_QUERY.md`、`docs/PROJECT_PROGRESS.md`：记录实际实现、验证结果和M1-15前停止点。

**调用链位置**

```text
前端（未经过）
→ API（未经过）
→ Schema（沿用严格Tool输入）
→ RunContext
→ TraceRecorder.start_run（本步→AgentRun ORM→PostgreSQL）
→ ExecutionBudget（本步，内存确定性护栏）
→ ToolRegistry + PermissionGuard
→ TraceRecorder.start/deny ToolCall（本步→ToolCall ORM→PostgreSQL）
→ 测试回调（本步不是正式业务Tool）
→ TraceRecorder.finish ToolCall/AgentRun（本步→PostgreSQL）
```

本步没有调用千问、商品Service、库存Service或EvidenceService。M1-15才把实际两个Service封装成Tool并接入现有HarnessExecutor。

**验证方法与实际结果**

1. 默认Settings转换为模型2次、Tool 2次、重复1次和总时间8000毫秒的不可变BudgetLimits；非法11次Tool、重复4次或0毫秒总时间被拒绝；
2. 第一次模型预留成功、第二次在测试上限1时返回`model_call_limit`；两个不同Tool签名占满额度后第三次返回`tool_call_limit`；
3. 相同Tool参数即使字典键顺序不同也产生相同稳定签名，第二次返回`repeated_tool_call`且实际Tool计数不增加；
4. 注入手动单调时钟验证单Tool 51ms超过50ms时触发ToolTimeout，总时限达到边界时触发`total_timeout`，无需真实sleep；
5. 参数摘要对password、access_token、sql和嵌套api_key全部写`[REDACTED]`，长字符串截断，序列化结果不含测试秘密或`DROP TABLE`；
6. 真实PostgreSQL成功运行记录`completed` AgentRun，模型计数1、Tool计数1、耗时25ms；ToolCall为`allowed/success`、版本和DE库存参数摘要正确，并把真实run/tool ID交给回调；
7. DE运营请求FR在回调前被拒绝，回调计数0；AgentRun为`denied/FORBIDDEN`，ToolCall为`denied/denied/FORBIDDEN`；
8. 第一次相同库存Tool执行成功，第二次重复在回调前拒绝；实际回调只有1次，AgentRun为`failed/BUDGET_EXCEEDED`，两条ToolCall依次为success和denied；
9. 模型上限测试只记录1次模型、0次Tool，AgentRun安全失败；
10. 回调推进3001ms超过Registry 3000ms后不返回结果，AgentRun为`timed_out/BUDGET_EXCEEDED`，ToolCall为timeout且耗时3001ms；
11. 调用前推进到8000ms总预算，业务回调计数0；AgentRun为timed_out，ToolCall记录permission denied/status timeout和BUDGET_EXCEEDED；
12. 回调在业务Session写临时Message后抛含密码/SQL的RuntimeError，Harness返回安全ToolExecutionError；业务事务回滚后Message为0，但独立AgentRun/ToolCall仍是failed/error，错误消息与参数摘要均不含原始秘密；
13. 专项单元与集成测试共13项通过；全量`pytest -q`共111项通过；Ruff检查通过且71个Python文件格式正确；Mypy检查43个`app/scripts`文件无类型问题；编译与`pip check`通过；
14. PostgreSQL 17.11容器为`healthy`；Alembic仍为`20260828_0003 (head)`，`alembic check`无差异；本步复用M1-06表，无需迁移；
15. 全量测试后重新Seed，真实临时演示生成两次运行：允许链为`completed/model=1/tool=1/allowed/success`，越权链为`denied/model=0/tool=1/denied/denied`；删除临时Thread后级联清理全部演示Trace；
16. 最终数据库保留4个Seed用户，threads、agent_runs、tool_calls、evidences均为0；
17. 实现过程中首次静态检查发现导出列表插入错误、未使用导入和异常边界规范问题；修正后专项与全量检查通过。首次专项行为测试12项已通过，随后补充总时限零下游调用用例达到13项；
18. 最终文档检查确认：README、总进度和M1阶段记录的代码围栏数量均成对，内部相对链接目标均存在，`git diff --check`通过；Git状态仅保留当前工作区未提交变更，未提交或推送Git。Windows提示未来可能把部分文本文件的LF换行为CRLF，这不是内容错误，也未触发差异检查失败。

**能够证明**

- 每个M1运行拥有独立、可测试的模型/Tool次数、重复调用和总时间预算；超限发生在新增下游调用前；
- Harness能够把PermissionGuard固定放在受控回调之前，并从同一份Tool参数取得市场；
- 成功、权限拒绝、预算拒绝、Tool/数据库超时和未知错误能够形成结构化AgentRun/ToolCall终态；
- 参数摘要和未知异常完成字段级脱敏，不把测试密码、Token、SQL或原始错误写入Trace；
- Trace独立事务能在业务事务回滚后保留失败审计，成功ToolCall ID可供后续Evidence关联；
- 当前M1同步串行执行外壳能够承接下一步两个正式Tool。

**不能证明**

- `get_product_spec`和`search_inventory`正式Agent Tool已经实现或调用真实Service；
- 千问/Mock Provider已经经过模型预算，LangGraph已经使用Harness；
- Python普通回调会在超时瞬间被物理中断；本步只能在同步边界拒绝结果并回滚，数据库中断由statement timeout负责；
- 多进程、多实例或并行Tool共享同一预算；当前预算只在单次进程内Run对象中有效；
- Trace在数据库完全不可用时仍能落库；只能返回安全Trace保存失败；
- API异常映射、HTTP状态码和请求级业务回滚已经完成；
- M1完整Agent、权限、审计或库存聊天闭环已经完成。

**常见问题与优先排查方向**

- 第二次相同查询立刻`BUDGET_EXCEEDED`：检查是否在同一AgentRun重复使用相同Tool+参数；正常M1图每个Tool只调用一次；
- Tool还没执行就总超时：检查预算对象是否过早创建、Provider耗时和`EXECUTION_TOTAL_TIMEOUT_MS`，不要用提高上限掩盖慢调用；
- Tool超过3000ms才报错：这是同步回调边界检查；数据库慢查询应同时检查Repository statement timeout，外部HTTP应使用Provider客户端超时；
- Trace有running没有终态：检查调用是否绕开`run_scope`或进程被强杀；普通业务异常必须经过Harness边界；
- Trace保存失败：先检查Thread是否已经提交、context中的tenant/user/thread是否满足复合外键，再检查PostgreSQL连接；
- 失败业务数据回滚但Trace也消失：检查是否错误地让TraceRecorder复用了业务Session；Trace应使用独立sessionmaker短事务；
- Trace参数出现秘密：检查敏感字段命名和summarize_arguments；正式两个Tool仍必须使用严格Schema，不能用无限制字典绕开；
- ToolCall序号冲突：M1只允许同一Run串行Tool；不要提前并行化。未来并行执行需要数据库锁或原子序号分配；
- 权限检查市场与业务市场不一致：Executor必须从Tool参数提取市场，禁止重新增加第二个可独立传入的market参数。

**下一步**

停止开发并等待用户理解和确认本步结果；用户明确回复“确认M1-14，可以进入M1-15”后，才进入M1-15“实现并注册两个Agent Tool”。

### 2026-08-28｜M1-15｜实现并注册两个Agent Tool

**状态：已完成**

**本步解决的问题**

M1-14已经有预算、权限、Trace和受控回调通道，但回调仍是测试替身，Agent还不能通过正式接口调用M1-10商品Service和M1-11库存/Evidence Service。本步实现`GetProductSpecTool`和`SearchInventoryTool`，把两条真实业务路径绑定到同一份Registry元数据和Harness，并统一返回`ToolEnvelope`。

**输入、输出和上下游**

- 输入：`GetProductSpecInput`或`SearchInventoryInput`、可信RunContext、已启动的AgentRun、现有Harness及相应业务Service；
- 输出：`ToolEnvelope[ProductSpecResult]`或`ToolEnvelope[InventoryResult]`；库存成功还包含数据时间和一个Evidence ID；
- 上游：M1-08严格Schema、M1-10/M1-11 Service、M1-12 RunContext、M1-13 Registry/Guard及M1-14 Harness；
- 下游：M1-16 Provider只负责产生受控意图和参数，M1-17 LangGraph按名称调用两个Tool并处理Envelope；
- 本步没有接收自然语言、调用模型、编排图、开放HTTP接口或创建前端页面。

**用大白话解释运行过程**

Agent Tool像“只给Agent使用的受控业务按钮”，ToolEnvelope像“格式固定的结果盒子”：

```text
严格Tool参数
→ Harness检查预算
→ PermissionGuard检查tenant、角色和市场
→ 创建ToolCall审计记录
→ Agent Tool把参数交给现有Service
→ Repository执行固定SQLAlchemy查询
→ PostgreSQL读取合成演示数据
→ 库存成功时在业务事务中写Evidence
→ 返回成功或安全错误ToolEnvelope
```

Tool不接收SQL，也不把tenant交给模型决定。两个Tool都从Harness中的可信RunContext取得tenant；库存市场既用于权限判断也用于实际Service查询，不存在第二份可以独立修改的市场参数。

**技术决定与边界**

- `get_product_spec`绑定`GetProductSpecInput → ProductSpecResult`，调用`ProductSpecService.get_product_spec`；成功Envelope不包含Evidence ID，`source_time`为空，因为M1库存闭环只要求库存数据库证据；
- `search_inventory`绑定`SearchInventoryInput → InventoryResult`，把M1-14生成并提交的tenant、AgentRun ID和ToolCall ID转换为`EvidenceWriteContext`，再调用`InventoryService.search_inventory`；成功Envelope包含库存快照时间和一个Evidence ID；
- Tool构造时检查实现名称及输入/输出Schema是否与Registry完全一致，不一致立即抛`InvalidToolBindingError`，避免“权限白名单写的是一个合同，实际代码执行另一个合同”；
- Registry仍严格只有两个名称、版本均为`1.0.0`、超时均为3000ms、均为只读。正式实现通过各自模块显式导入，不在`app.tools`包入口急切导入执行模块，避免权限模块加载Registry时出现循环导入；
- Tool只捕获Harness返回的安全`ApplicationError`并转换为失败Envelope。业务内部未知异常先由Harness转换为`INTERNAL_ERROR/Tool执行失败`，原始堆栈、密码和SQL不会进入Envelope或Trace；
- 业务Service返回值也在Harness回调内部检查类型。若未来实现错误地返回非注册Schema结果，会在Harness边界按未知异常脱敏，而不会先把ToolCall记为成功；
- `ToolEnvelope.meta`统一包含Tool名称、Registry版本、Tool层总耗时、trace ID和`synthetic_data=true`；库存还把`snapshot_at`复制到`source_time`；
- 商品和库存Service继续依赖固定Repository查询，Tool没有模型生成SQL、SQL字符串入口或任意数据库访问能力；
- 库存Service对Evidence执行`flush`，最终`commit/rollback`仍由上层业务事务拥有。专项集成测试在成功Envelope后提交事务，在错误Envelope后回滚；M1-18请求级Session必须延续这个规则，不能由Tool私自提交整个请求中的其他业务变化；
- Tool失败Envelope已经决定ToolCall的安全终态，但整次AgentRun最终应标为completed、failed、denied还是timed_out，要由M1-17图根据Envelope统一决定。本步没有提前实现该图级状态策略。

**修改文件与职责**

- `app/tools/contracts.py`：检查运行实现与Registry绑定一致，并统一构造成功/失败ToolEnvelope及ToolMeta；
- `app/tools/get_product_spec.py`：正式商品规格Tool，只通过Harness调用ProductSpecService；
- `app/tools/search_inventory.py`：正式库存Tool，把Tool执行ID转换为Evidence上下文并调用InventoryService；
- `app/runtime/executor.py`：只读暴露可信tenant、trace ID和当前Registry定义，供正式Tool绑定；
- `app/tools/__init__.py`：保持轻量合同和Registry导出，避免运行Tool与权限模块循环导入；
- `tests/unit/test_agent_tool_contracts.py`：验证严格两Tool绑定、元数据、耗时、数据时间、Evidence ID和安全错误Envelope；
- `tests/integration/test_agent_tools.py`：使用真实Seed、身份、PostgreSQL、Repository、Service、Harness和Trace验证两条正式Tool路径；
- `README.md`：增加正式Agent Tool调用链、Envelope和Evidence边界；
- `docs/progress/M1/M1_INVENTORY_QUERY.md`、`docs/PROJECT_PROGRESS.md`：更新实际实现、验证结果和M1-16前停止点。

**调用链位置**

```text
前端（未经过）
→ API（未经过）
→ Schema（GetProductSpecInput / SearchInventoryInput）
→ Harness（预算、权限、Trace）
→ Agent Tool（本步）
→ Service（ProductSpecService / InventoryService / EvidenceService）
→ Repository（固定SQLAlchemy查询）
→ Model（商品、库存及Evidence ORM）
→ PostgreSQL（合成演示数据与Evidence）
→ ToolEnvelope（本步统一返回）
```

这是第一次让正式Agent Tool穿过Schema、Harness、Service、Repository、Model到PostgreSQL；但前端、API、自然语言Provider和LangGraph仍未经过。

**验证方法与实际结果**

1. Registry名称严格为`get_product_spec/search_inventory`，两个实现分别与注册的输入/输出Schema一致；故意把商品Tool定义换成库存输入Schema时立即拒绝绑定；
2. ToolEnvelope构造测试确认版本`1.0.0`、25ms手动耗时、快照时间、trace ID、合成数据标志和Evidence ID全部进入正确字段；权限错误只返回安全`FORBIDDEN`详情；
3. 真实PostgreSQL商品Tool通过Harness、ProductSpecService和ProductRepository查询`LR-TL-MUSH-OR01`，返回合成演示商品及规格；ToolCall为`allowed/success`；
4. 真实PostgreSQL库存Tool通过Harness、InventoryService、InventoryRepository和EvidenceService查询DE-FRA，返回可售库存125、库存快照时间和一个Evidence ID；业务事务提交后Evidence的AgentRun、ToolCall、结构化库存和合成数据标志均正确；
5. DE运营请求FR-CDG在Service和Repository前被PermissionGuard拒绝，Envelope为`FORBIDDEN/market_code`，ToolCall为`denied/denied`且Evidence数量为0；
6. 合法DE范围查询不存在SKU时，权限通过但Service返回`INVENTORY_NOT_FOUND`，ToolCall为`allowed/error`且没有Evidence；
7. 注入包含测试密码和`DROP TABLE`文本的未知Service异常，Harness将其转换为`INTERNAL_ERROR/Tool执行失败`；Envelope和Trace都不含秘密或原始SQL；
8. M1-15直接Tool专项单元及集成测试共10项通过；用户评审补充涉及的Tool合同、权限和Schema测试共28项通过；全量`pytest -q`共121项通过；
9. Ruff检查通过且72个Python文件格式正确；Mypy检查46个`app/scripts`文件无类型问题；全量Python编译和`pip check`通过；
10. PostgreSQL 17.11容器为`healthy`；Alembic仍为`20260828_0003 (head)`且`alembic check`确认无新迁移差异；
11. 全量测试后使用正确模块入口`.venv\Scripts\python.exe -m scripts.seed_m1`重复执行Seed成功，关键答案仍为DE-FRA可售125；最终数据库为4个Seed用户，threads、agent_runs、tool_calls、evidences均为0；
12. 首次全量收集发现`app.tools`包入口急切导入正式Tool导致循环导入；改为从具体Tool模块显式导入后，全量120项通过。直接执行`python scripts/seed_m1.py`也曾因模块路径不含仓库根目录在进入Seed前失败；改用项目约定的`python -m scripts.seed_m1`后成功，该失败没有修改数据库；
13. 最终文档检查确认README、总进度和M1阶段记录的代码围栏均成对，内部相对链接目标均存在，`git diff --check`通过；Git状态只保留当前累计工作区变更，未提交或推送Git。Windows仅提示部分文本文件未来可能把LF转换为CRLF，不属于内容错误。

**能够证明**

- 两个正式Agent Tool已与严格Registry合同绑定，并且每次真实业务调用都经过预算、权限和Trace；
- 商品Tool能查询真实Seed商品规格，库存Tool能查询真实Seed库存并返回可售125、数据时间和数据库Evidence ID；
- tenant来自可信RunContext，库存权限市场和业务查询市场来自同一份严格参数；
- 权限拒绝发生在Service前，业务错误和未知异常不会泄露SQL、密码或堆栈；
- Agent Tool没有任意SQL能力，实际查询继续使用Repository固定条件和PostgreSQL statement timeout；
- 成功、业务错误和权限拒绝都能形成结构一致的ToolEnvelope及对应ToolCall轨迹。

**不能证明**

- 自然语言“德国仓蘑菇灯还有多少可售库存”已经能自动识别并产生正确Tool参数；这是M1-16 Provider和M1-17 LangGraph的职责；
- 千问或Mock已经调用这两个Tool；
- AgentRun会根据失败Envelope得到最终正确的completed/failed/denied/timed_out状态；图级归并留在M1-17；
- HTTP请求已经拥有完整提交/回滚、状态码和Evidence查询接口；这是M1-18；
- 浏览器聊天页面已经可用；这是M1-19；
- M1完整库存自然语言闭环已经完成。

**常见问题与优先排查方向**

- Tool构造时报绑定错误：比较具体Tool的名称、输入/输出Schema与`create_m1_tool_registry`，不要用强制类型转换掩盖合同不一致；
- 导入Tool时报循环导入：从`app.tools.get_product_spec`或`app.tools.search_inventory`显式导入正式实现，权限/Registry底层模块不要反向导入执行Tool；
- 库存成功但没有Evidence：检查是否使用Harness提供的真实AgentRun/ToolCall ID、EvidenceService是否与库存业务使用同一个Session，以及上层是否提交业务事务；
- Evidence存在但ToolCall关联错误：检查`EvidenceWriteContext`是否从当前`ToolExecutionContext`建立，禁止外部或模型传入ID；
- DE查FR仍进入Repository：检查是否绕开正式SearchInventoryTool/Harness，以及`market_code`是否仍只来自SearchInventoryInput；
- 返回错误暴露原始异常：检查异常是否在Harness的operation内部发生；Tool外部组装代码不得把原始异常字符串塞进ErrorDetail；
- ToolCall成功但业务事务后来提交失败：上层必须把提交失败转换为请求失败并回滚；M1-18实现请求事务时需要专项测试这一边界；
- 直接运行Seed提示找不到`app`：在仓库根目录使用`.venv\Scripts\python.exe -m scripts.seed_m1`，不要用脚本文件路径直接启动。

**用户评审后的补充修正**

用户指出原Registry单句描述如果未来直接提供给模型，可能不足以说明“做什么、返回什么、什么时候使用和限制条件”。复核确认该问题成立：此前Schema已经能生成字段类型、格式、枚举、必填项和`additionalProperties=false`，但输入字段没有中文`description`，Registry描述也更偏后端摘要。

本次仍属于M1-15合同质量修正，没有进入Provider开发：

- 两个Registry描述均补充使用时机、返回内容、禁止用途、合成数据和权限限制；
- `GetProductSpecInput.product_query`补充名称/别名/SKU和先解析唯一SKU的说明；
- `InventoryIntent`三个字段补充模型提取语义，并明确仓库未知时保持为空、不能猜测；
- `SearchInventoryInput`明确只接受已确认SKU、市场仅DE/FR且受权限限制、仓库可选但多仓时必须提供；
- 测试直接调用`model_json_schema()`，确认商品必填`product_query`，库存必填`sku/market_code`，仓库不在required中，同时验证中文description、DE/FR枚举、SKU正则和禁止额外字段；
- Tool描述只帮助模型理解和选择，不替代Pydantic、PermissionGuard、ExecutionBudget、RunContext或Repository安全控制；
- 补充后相关28项测试和全量121项测试通过，Ruff、72文件格式、Mypy 46文件、编译及依赖检查通过。

**下一步**

停止开发并等待用户理解和确认本步结果；用户明确回复“确认M1-15，可以进入M1-16”后，才进入M1-16“建立Mock和千问Provider边界”。
