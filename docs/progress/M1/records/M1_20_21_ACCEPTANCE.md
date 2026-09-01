# M1-20 至 M1-21：故障矩阵、浏览器回归与阶段收口

> 本文件保存从迁移前单文件中拆出的完整历史方案、实施日志与验证证据。
> 当前状态和阅读入口见 [M1入口](../M1_INVENTORY_QUERY.md)。

### 2026-08-29｜M1-20｜完成故障矩阵、集成和浏览器端到端回归

**状态**

已完成并验证；等待用户确认后才能进入M1-21。

**本步开始前缺少什么**

M1-19已经有可运行的登录和库存证据页面，也有168项后端测试及4项前端组件测试，但还缺三类最终证据：第一，零库存、无记录、商品歧义和数据库语句超时是否能穿过真实HTTP入口得到正确结果；第二，页面是否能与真实FastAPI和PostgreSQL联合运行；第三，浏览器面对403、401和数据库停机时是否会安全失败。本步主要补验证，不修改库存计算、权限规则、Agent流程、API合同或数据库结构。

**输入、输出和上下游**

- 输入：M1-01至M1-19的完整系统、合成Seed、已有单元/集成/组件测试；
- 输出：补齐的API故障集成测试、Playwright Chromium端到端套件、可重复启动和清理规则、实际故障矩阵；
- 上游：浏览器输入、Token、Mock Provider建议及故障注入；
- 下游：Next.js调用真实FastAPI，继续经过Schema、认证/会话Service、LangGraph、Harness、Agent Tool、业务Service、Repository、Model和PostgreSQL；
- M1-20没有改变任何业务成功结果，标准答案仍是DE-FRA可售125。

**用大白话解释运行过程**

集成测试像是直接从“服务门口”递交各种正常或故障请求，确认后端各层合作后给出正确HTTP结果。浏览器端到端测试则像真人一样打开生产版网页、选择账号、输入密码、按键发送问题并查看右侧Evidence；它不把后端伪装成假接口。最后一条浏览器用例会短暂停止本项目PostgreSQL，确认页面只显示安全中文错误，然后在`finally`和全局清理中恢复数据库。测试专用Thread使用`M1-20 E2E`前缀，结束后统一删除，Windows下还会清理测试独占的3000和8000监听进程。

**故障矩阵实际覆盖**

| 场景 | 本步/既有验证位置 | 实际结果 | 说明 |
|---|---|---|---|
| 正常DE库存查询 | API集成 + Playwright | HTTP 200，页面显示125、SKU、DE-FRA、来源定位和合成标识 | 真实前端、API和PostgreSQL整链通过 |
| FR运营查询DE | 既有权限/API测试 + Playwright | HTTP 403，显示安全错误，无库存Evidence | 权限拒绝发生在业务数据返回前 |
| 非法SKU | 既有Schema/Tool测试 | 422或`VALIDATION_ERROR`，Repository不执行 | Schema先拦截非法输入 |
| 零库存 | 新增API集成测试 | HTTP 200、回答0且Evidence的`available=0` | 0是有效事实，不等于无记录 |
| 无库存记录 | 新增API集成测试 | HTTP 404、`INVENTORY_NOT_FOUND`，不保存业务消息/Evidence | 找不到与库存为0严格区分 |
| 重复SKU | 既有迁移/Seed集成测试 | PostgreSQL唯一约束拒绝，Seed重跑不重复 | 数据库最终约束继续有效 |
| 数据库语句超时 | 既有真实`pg_sleep` + 新增API集成测试 | HTTP 504、`DATABASE_TIMEOUT`、可重试且不泄露SQL | 同时覆盖数据库设置和API错误映射 |
| PostgreSQL整体停机 | 新增Playwright测试 | 身份刷新阶段HTTP 500，页面显示安全中文错误，无连接串/密码/125，随后数据库恢复 | 故障早于Thread/AgentRun创建，因此不强求trace |
| 模型建议超时 | 既有Provider/API测试 | HTTP 504、`PROVIDER_ERROR`，无业务结果 | Provider失败不能绕过流程 |
| Tool次数/重复调用超限 | 既有Budget/Harness/LangGraph测试 | `BUDGET_EXCEEDED`，后续Tool停止 | 程序预算而非Prompt负责终止 |
| 商品歧义 | 新增API集成测试 | HTTP 409、`AMBIGUOUS_PRODUCT` | 系统不会随便选择第一个SKU |
| 跨租户/会话/Evidence | 既有Repository与API测试 | 当前身份查不到其他租户或用户记录 | tenant、Thread归属和Evidence范围均生效 |
| 无效/过期Token | 既有认证测试 + Playwright无效Token | HTTP 401，浏览器清空内存会话并回登录页 | 过期由认证测试覆盖，无效Token由真实浏览器覆盖 |

**新增或修改文件与职责**

- `tests/integration/test_m1_api.py`：新增零库存成功、无库存404、商品歧义409和数据库语句超时504四个API集成场景；
- `frontend/playwright.config.ts`：规定单Chromium串行执行、生产Next.js与真实FastAPI服务、确定性Mock模式、失败截图/视频/trace和全局清理；
- `frontend/e2e/inventory-workbench.spec.ts`：四条真实浏览器路径，覆盖键盘换行/发送、loading、防重复提交、Evidence、403、401和数据库停机；
- `frontend/e2e/support/runtime.ts`：执行Alembic、Seed、测试Thread清理、PostgreSQL停机/恢复、密码安全读取和Windows测试服务清理；
- `frontend/e2e/global-setup.ts`、`global-teardown.ts`：在浏览器测试前恢复数据库，在结束或失败时恢复数据库并清理运行数据与端口；
- `frontend/package.json`、`frontend/package-lock.json`：固定Playwright 1.62.1及E2E命令；
- `frontend/vitest.config.ts`：只让Vitest收集组件测试，避免误收集Playwright文件；
- `frontend/eslint.config.mjs`、`.gitignore`：忽略Playwright报告和失败产物；
- `README.md`、本阶段记录和总进度：记录M1-20运行方法、实际验证、边界和停止点。

未修改`app/`业务代码、Pydantic Schema、SQLAlchemy Model、Alembic迁移、Seed定义或页面业务组件。

**调用链位置**

```text
Playwright Chromium（本步：真实用户操作和页面断言）
→ Next.js生产页面（M1-19）
→ FastAPI API（M1-18；本步增加HTTP故障集成测试）
→ Pydantic Schema（M1-08）
→ 认证/会话Service + LangGraph + Harness + Agent Tool（M1-10至M1-17）
→ Repository + SQLAlchemy Model（M1-03至M1-11）
→ PostgreSQL合成Seed（M1-02至M1-07）
→ 回到API、页面回答和Evidence侧栏
```

浏览器用例覆盖了整条链；新增API测试从API开始，没有经过Next.js；已有单元和组件测试会分别绕过部分上游，以便精确定位Schema、Service、Harness或UI层错误。

**验证方法与实际结果**

1. 新增API定向测试：`tests/integration/test_m1_api.py`共9项通过；第一次数据库超时注入因测试替身签名不完整误得500，修正测试替身后通过，没有修改业务代码；
2. 后端全量`pytest -q -x`：172项通过、1项真实Qwen付费冒烟按设计跳过；比M1-19新增4项；
3. Playwright Chromium：4项通过；真实响应依次包含200、403、401和数据库停机时500，快乐路径右侧Evidence显示125、`LR-TL-MUSH-OR01`、`DE-FRA`、数据库定位和合成数据标识；
4. 浏览器测试中的PostgreSQL停机用例通过，测试结束后容器恢复healthy；3000和8000均无残留监听；
5. 前端组件测试：1个文件4项通过；`npm run typecheck`、`npm run lint`和Next.js 16.3.3生产构建通过；
6. `npm ls --depth=0`命令成功，`@playwright/test@1.62.1`已安装；`npm audit --audit-level=high`报告0个漏洞；
7. Ruff检查通过，95个Python文件已按格式统一，Mypy对63个`app/scripts`源文件无问题，Python编译与`pip check`通过；
8. Alembic为`20260828_0003 (head)`；重新Seed并清理测试运行数据后，用户4条、Thread/AgentRun/ToolCall/Evidence各0条，DE-FRA的`LR-TL-MUSH-OR01`可售仍为125；
9. PostgreSQL 17.11容器最终状态healthy；`git diff --check`将在文档更新后再次执行；本步没有提交或推送Git。

**能够证明**

- 在当前Windows、Chromium、Next.js 16.3.3、FastAPI和PostgreSQL 17.11组合中，标准登录查询与Evidence整链可以重复跑通；
- 已列入矩阵的正常、越权、认证、零库存、缺失、歧义、超时和数据库停机路径具有自动化回归保护；
- 浏览器不是通过Mock API得到125，而是通过真实后端和真实PostgreSQL合成Seed得到；
- 测试故障不会把连接串、数据库密码、SQL或125错误地显示给无权/失败页面；
- M1-20主要补验证和测试运行基础设施，没有改变M1-19业务功能。

**不能证明**

- 不能证明真实Qwen长期稳定或所有自然语言表达都能正确解析；浏览器回归主动固定为Mock以保证确定性；
- 不能证明Chrome之外的所有浏览器、移动端视觉、高并发、长时间运行、生产网络分区或云数据库故障；
- 不能证明真实Amazon数据、SP-API、RAG、多模态、深度研究或M2以后能力；
- 数据库整体停机发生在身份刷新阶段时没有AgentRun trace，这条用例只证明安全失败与恢复，不证明故障前已建立业务审计；
- M1还不能标记为阶段完成，因为M1-21的干净环境演示脚本、README最终收口和用户验收尚未获得授权。

**常见问题与优先排查方向**

- E2E启动前提示3000或8000被占用：先确认是否有本项目旧FastAPI/Next.js进程，不要开启`reuseExistingServer`掩盖版本串线；
- E2E快乐路径出现模型超时：检查Playwright后端是否强制`LLM_PROVIDER=mock`，日常回归不能误用真实付费Provider；
- Chromium未安装：在`frontend/`执行`npm exec playwright install chromium`；
- 数据库停机用例后容器未恢复：先执行`docker compose up -d --wait postgres`，再检查全局teardown和Docker Desktop；
- 测试后运行数据不是0：检查测试Thread是否使用`M1-20 E2E`前缀以及外键级联清理，不要删除Seed业务表；
- 403页面出现库存数字或Evidence：第一优先检查PermissionGuard、API错误分支和前端旧状态清空，不能只改测试断言。

**下一步**

停止开发并等待用户理解和确认M1-20。只有用户明确回复“确认M1-20，可以进入M1-21”后，才能编写最终演示脚本、从干净环境按README复现并完成M1阶段验收；本次授权不包含M1-21。

### 2026-08-29｜M1-21｜完成演示脚本、干净环境复现和M1阶段收口

**状态**

已完成并验证；M1-01至M1-21全部完成，M1阶段状态更新为“已完成”。

**本步开始前缺少什么**

M1-20已经证明代码和浏览器回归可用，但还缺少一个适合初学者和面试现场的固定演示入口，也没有从完全空的PostgreSQL数据卷按README重新生成整个M1。测试通过只能说明测试环境成立；M1-21要进一步证明新电脑在具备Python、Node和Docker后，能够按照公开说明恢复迁移、Seed、后端、查询、Evidence和权限拒绝。

**输入、输出和上下游**

- 输入：M1-01至M1-20的代码、迁移、`m1-v1`合成Seed、完整测试结果和README；
- 输出：一个安全公开API演示脚本、对应单元测试、可从空卷复现的README、M1最终验证记录；
- 上游：演示者提供运行中的FastAPI地址，本地`.env`只提供演示密码；
- 下游：脚本只调用公开HTTP接口，实际经过API、Schema、Service、LangGraph、Harness、Agent Tool、Repository、Model和PostgreSQL；
- 本步没有修改库存业务、权限规则、API Schema、数据库Model、迁移、Seed或Next.js页面。

**用大白话解释运行过程**

演示脚本像一个严格按台词操作的演示者。它先问健康接口“数据库连上了吗”，再用德国运营账号登录、确认身份范围、创建会话、发送库存问题并核对125和Evidence；然后换成法国运营账号查询德国仓，必须得到`FORBIDDEN`。任何一步状态码、数据格式、SKU、仓库或库存数字不符合合同，脚本立即失败。它不会把密码、Token、连接串或SQL打印到终端。

干净环境验证先确认当前卷只含一个合成租户、四个演示用户和0条运行数据，再精确删除当前Compose项目标记的`deep-search-postgres-data`卷。新卷启动后，`alembic current`没有版本；执行README的三次迁移和Seed后恢复到head与125。公开演示实际写入审计数据，读取计数后再按专用Thread标题清理，最后停止并重启PostgreSQL验证持久化。

**新增或修改文件与职责**

- `scripts/demo_m1.py`：只通过公开HTTP接口完成健康、DE成功、Evidence和FR越权演示；使用既有Pydantic响应Schema复核合同，输出安全摘要；
- `tests/unit/test_demo_m1.py`：用HTTP Mock Transport验证请求顺序、响应Schema、125、越权和敏感信息不进入摘要，并测试后端地址与密码读取边界；
- `README.md`：将M1标记为完成，补新电脑版本检查、虚拟环境、`npm ci`、公开演示命令、预期输出、面试讲解顺序和明确警告的空卷复现方法；
- `docs/progress/M1/M1_INVENTORY_QUERY.md`：记录M1-21实际过程、结果、边界和阶段结论；
- `docs/PROJECT_PROGRESS.md`：将M1更新为已完成，下一步停在M2方案讨论前。

**调用链位置**

```text
scripts.demo_m1（本步交付层，只发公开HTTP）
→ FastAPI健康/认证/会话/聊天/Evidence API
→ Pydantic Schema
→ 认证与会话Service
→ LangGraph五节点流程
→ Harness预算、权限和Trace
→ get_product_spec / search_inventory
→ 商品与库存Service
→ 固定Repository + SQLAlchemy Model
→ PostgreSQL合成Seed
→ JSON回答/Evidence/403回到演示脚本
```

脚本没有经过Next.js，因为它用于终端和面试中的确定性API演示；M1-20的4项Playwright测试继续负责“浏览器→前端→后端→数据库”整链。本步单元测试使用Mock Transport，因此只验证演示脚本自身；本步实际启动验证才证明真实后端链路。

**实际执行与验证结果**

1. Docker Desktop在本步开始时未运行，按本地恢复流程启动后，Docker Server 29.6.1和Compose 5.3.0恢复可用；
2. 删除前核对数据卷名为`deep-search-postgres-data`，Compose标签明确属于`deep-search-pro/postgres_data`；数据库为Tenant 1、User 4，Thread/AgentRun/ToolCall/Evidence均0；
3. 精确执行`docker compose down`和`docker volume rm deep-search-postgres-data`，旧合成卷已永久删除并创建同名新卷；没有删除其他Docker卷、仓库文件或真实业务数据；
4. 新卷首次`alembic current`无版本；`alembic upgrade head`按`0001→0002→0003`执行，Seed成功恢复，最终为`20260828_0003 (head)`和DE-FRA可售125；
5. 演示脚本3项单元测试通过；首轮真实执行因Windows系统代理让`httpx`访问本机返回502，确认请求未到Uvicorn后，在本地演示客户端设置`trust_env=False`，不继承系统代理，重跑通过；该修复不影响后端或Qwen Provider；
6. 真实公开API演示依次得到健康200、DE登录200、`/me` 200、Thread 201、库存200、Evidence 200、FR登录200、Thread 201和越权403；终端显示`LR-TL-MUSH-OR01 / DE-FRA / available 125`及合成数据说明；
7. 演示后数据库为Thread 2、Message 2、AgentRun 2、ToolCall 4、Evidence 1，证明流程实际执行和记录审计；清理`M1-21 Demo%`专用Thread后五类运行数据全部为0；
8. PostgreSQL停止后Compose显示无运行服务；重新`up -d --wait`后恢复healthy，迁移仍为head、User 4、运行数据0、关键库存125，证明命名卷持久化；
9. 后端全量`pytest -q`为175项通过、1项真实Qwen付费冒烟按设计跳过；M1-20的172项基础上新增3项演示脚本测试；
10. Ruff检查通过，97个Python文件格式正确；Mypy对64个`app/scripts`源文件无问题，Python编译和`pip check`通过；
11. 前端组件测试4项通过，TypeScript、ESLint和Next.js 16.3.3生产构建通过；Playwright Chromium真实端到端4项再次通过；
12. `npm audit --audit-level=high`报告0个漏洞；测试完成后3000和8000没有残留服务，PostgreSQL恢复healthy；
13. README、总看板和本阶段记录的代码围栏均为偶数，相对链接0缺失，敏感Key模式0命中；`git diff --check`无空白错误，仅提示Windows未来可能进行LF/CRLF转换；本步未提交或推送Git。

**M1阶段完成标准核对**

- 21个步骤：M1-01至M1-21均有实现和实际验证记录；
- 数据库：PostgreSQL可从空卷启动，三次迁移、Seed、停止/重启均已验证；
- 身份权限：四账号、三角色、DE/FR范围、401/403/404和跨租户边界已验证；
- Agent主链：Mock、五节点LangGraph、两个受控Tool、Harness预算/权限/Trace和Evidence已接通；
- 用户入口：FastAPI公开API、Next.js登录聊天、Evidence侧栏和Chromium端到端均通过；
- 故障矩阵：非法输入、零库存、无记录、歧义、重复SKU、Provider/数据库超时、预算、Token、PostgreSQL停机和越权均有覆盖；
- 可复现交付：README和公开演示脚本已从全新数据卷实际执行；
- 范围控制：未实现RAG、pgvector、BGE、多模态、Tavily、MCP、Redis、Celery、SSE或M2代码。

**能够证明**

- 在当前已记录的Windows、Python 3.11、Node 24、Docker 29.6.1、Compose 5.3.0、PostgreSQL 17.11和Chromium环境中，M1可以从空数据卷完整恢复并重复演示；
- 演示脚本使用公开API和真实PostgreSQL，不直接查库、不伪造125，也不输出密码或Token；
- 成功回答、Evidence、审计轨迹和权限拒绝可以在同一个固定演示中讲清楚；
- M1的阶段目标、测试矩阵、README复现和21个实施步骤已经完成。

**不能证明**

- 不能证明真实Qwen在所有表达下长期稳定；付费冒烟仍需显式开启，M1默认演示使用确定性Mock；
- 不能证明高并发、跨区域生产部署、灾难恢复、所有浏览器和移动端商业体验；
- 不能证明数据来自真实Amazon或公司系统，全部业务数据仍是明确标注的合成演示数据；
- 不能证明RAG、pgvector、BGE、多模态、深度研究、Tavily或M2以后功能已经存在；
- 删除本地Docker卷的复现方式不可恢复旧运行记录，只能依靠迁移和Seed重建合成基线，因此README已放在可选危险操作中。

**常见问题与优先排查方向**

- 演示脚本报健康502但PowerShell健康200：检查Windows系统代理；脚本已对明确本地服务禁用环境代理，不要把这个设置复制到需要代理的外部Qwen客户端；
- 演示脚本连接失败：先确认Uvicorn在`127.0.0.1:8000`运行，再查3000/8000端口和Docker健康，不要先改库存代码；
- 登录失败：检查Seed是否执行、账号是否为演示账号、`.env`的`M1_DEMO_PASSWORD`是否与Seed时一致；
- 回答不是125：先检查Seed版本、DE-FRA最新快照和是否错误启用了真实Qwen，不要在脚本或前端硬改答案；
- 越权演示返回200：第一优先检查FR账号市场范围、PermissionGuard和库存Tool参数，不要删除403断言；
- 空卷恢复误删风险：只允许操作Compose标签属于本项目的`deep-search-postgres-data`，真实数据库和其他项目卷禁止使用该命令；
- E2E后端口残留：检查Playwright全局teardown，Windows下确认3000和8000监听进程属于本项目后再结束。

**下一步**

M1到此完成并停止。后续如继续M2，必须先读取总看板和本文件，单独提交“自建RAG垂直切片”的阶段方案并等待用户确认；M1-21授权不包含M2方案创建或代码开发。

## 17. 强制确认声明

**M1阶段状态为“已完成”。用户明确确认M2阶段方案前，禁止创建或开发M2运行代码。**
