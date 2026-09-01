# M1-01 至 M1-06：配置、PostgreSQL、事务与基础模型

> 本文件保存从迁移前单文件中拆出的完整历史方案、实施日志与验证证据。
> 当前状态和阅读入口见 [M1入口](../M1_INVENTORY_QUERY.md)。

### 2026-08-28｜M1-01｜建立新目录、配置和依赖基线

**状态：已完成**

**本步解决的问题**

旧项目只有会在导入时初始化MySQL、RAGFlow、Tavily和旧Agent的运行入口，依赖清单也混合了M1当前不需要的大量文档、RAG和旧数据库包。本步建立一个不依赖外部服务即可导入的M1新入口，并把运行配置、M1依赖、开发依赖和旧原型依赖分开。

**输入、输出和上下游**

- 输入：已确认的M1方案、旧`requirements.txt`、`.env.example`和旧`agent/api/tools`目录；
- 输出：`app`新入口、集中配置、M1依赖清单、旧依赖快照和基础自动化测试；
- 上游：M0设计基线和M1详细方案；
- 下游：M1-02 PostgreSQL容器，以及后续数据库连接、API、Service、Tool和LangGraph步骤。

**用大白话解释运行过程**

程序从`app.main:app`进入，先由`Settings`统一读取环境变量并检查端口、API前缀、模型模式和敏感配置规则，再创建一个最小FastAPI应用。当前只有`/health`健康接口，它明确返回`database=not_checked`，因为数据库属于M1-02，不能提前假装已经可用。默认模型模式是Mock，因此没有千问Key也能安全导入应用。

**修改文件与职责**

- `app/__init__.py`：建立M1应用包并声明当前应用版本；
- `app/core/__init__.py`：建立配置基础包；
- `app/core/config.py`：集中读取和校验应用、PostgreSQL、Mock/Qwen和未来JWT配置；
- `app/main.py`：提供`create_app`应用工厂、新FastAPI入口、CORS基础设置和不访问数据库的`/health`；
- `requirements.txt`：只声明M1运行时直接依赖和兼容主版本范围；
- `requirements-dev.txt`：声明pytest、Ruff、mypy等开发验证依赖；
- `requirements-legacy.txt`：完整保留旧`requirements.txt`依赖快照，供旧教学原型按需使用；
- `.env.example`：替换为M1环境变量模板，默认使用Mock，真实密钥仍禁止提交；
- `.gitignore`：补充Python构建和包元数据产物；
- `tests/__init__.py`、`tests/unit/__init__.py`：建立测试包；
- `tests/unit/test_app_baseline.py`：验证安全默认配置、配置拒绝规则、健康接口和新旧导入边界；
- `docs/progress/M1/M1_INVENTORY_QUERY.md`、`docs/PROJECT_PROGRESS.md`：记录本步状态和验证事实。

本地`.venv`还安装了`requirements-dev.txt`声明的依赖，但虚拟环境被`.gitignore`忽略，不属于仓库源文件。

**调用链位置**

```text
前端（未经过）
→ API（建立FastAPI外壳和/health）
→ Schema（仅Settings配置校验，尚无业务Schema）
→ Service（未经过）
→ Model（未经过）
→ PostgreSQL（未启动、未连接）
```

本步属于API基础和项目配置层。它只为后续完整链路提供统一入口，不包含登录、库存、Agent Tool或数据库业务逻辑。

**验证方法与实际结果**

1. 首次执行`.venv\\Scripts\\python.exe -m pip install -r requirements-dev.txt`时，Windows旧版pip按GBK读取UTF-8中文注释，安装在下载前失败；将三个依赖文件的注释改为ASCII英文后重新执行成功；
2. `pytest -q tests/unit/test_app_baseline.py`：7个测试全部通过，其中包含`.env.example`实际解析和开发者Shell环境变量隔离；
3. `ruff check app tests`：通过，没有代码规范错误；
4. `mypy app`：通过，4个源文件没有类型错误；
5. `compileall -q app tests`：退出码0，Python语法编译通过；
6. `pip check`：返回`No broken requirements found`；
7. 直接导入`app.main:app`成功，应用标题为`Deep Search Pro M1`，路由只有框架文档路由和`/health`；
8. 扫描`app/`未发现对旧`agent/api/tools/rawflow`或MySQL、RAGFlow、Tavily运行模块的导入；
9. `requirements-legacy.txt`去掉新增说明后与Git基线中的旧`requirements.txt`逐行一致；
10. 三个依赖文件的非ASCII字符数量均为0，避免旧Windows pip再次出现编码错误；
11. `git diff --check`没有空白错误，只报告Windows未来可能进行LF/CRLF转换的提示；
12. Git状态确认没有修改旧`agent/`、`api/`、`tools/`运行文件，也没有M1-02及后续代码。
13. 再次安装`requirements-dev.txt`全部返回`Requirement already satisfied`，证明本步依赖安装可重复执行；
14. 最终检查两份进度文档代码围栏均闭合、本地链接损坏数为0、意外行尾空白数为0，变更文件中未发现常见真实密钥或私钥特征。

**能够证明**

- M1有一个不需要数据库和外部API即可导入、创建和测试的新入口；
- 配置从统一位置读取，Mock是安全默认值，Qwen模式缺少Key会立即拒绝；
- 生产模式不能继续使用本地JWT占位密钥；
- 新入口当前没有导入旧MySQL、RAGFlow、Tavily或旧Agent运行链；
- M1直接依赖、开发依赖和旧原型依赖已经分开，声明的依赖在当前`.venv`中没有破损；
- 基础健康接口不会误报数据库已经就绪。

**不能证明**

- PostgreSQL已经启动、可连接或能够持久化数据；
- SQLAlchemy事务、Alembic迁移、登录、权限、库存Tool或LangGraph已经实现；
- 千问API可以真实调用；
- 当前兼容版本范围能像锁文件一样保证未来每次安装得到完全相同的小版本；
- 前端或端到端链路已经存在。

**常见问题与优先排查方向**

- `ModuleNotFoundError`：先确认命令使用仓库`.venv\\Scripts\\python.exe`，再执行`pip install -r requirements-dev.txt`；
- pip出现GBK/UTF-8错误：先检查依赖文件是否重新出现非ASCII注释，以及使用的pip版本；
- 应用导入时要求旧API Key：检查`app/`是否误导入旧`agent/api/tools`；
- `LLM_PROVIDER=qwen`启动失败：检查`QWEN_API_KEY`，默认本地开发应先保持`mock`；
- CORS配置失败：`CORS_ORIGINS`必须是JSON数组格式；
- `/health`显示`database=not_checked`：这是本步预期结果，数据库健康检查从M1-02/M1-03开始；
- 换电脑后得到不同依赖小版本：当前是带主版本上限的直接依赖基线，完整锁定需要在后续部署基线中补充。

**下一步**

停止开发并等待用户理解和确认本步结果；用户明确同意后才进入M1-02“只启动PostgreSQL容器”。

### 2026-08-28｜M1-02｜只启动PostgreSQL容器

**状态：已完成**

**本步解决的问题**

M1-01只有数据库连接配置，没有实际PostgreSQL服务。本步建立一份只包含PostgreSQL的Docker Compose配置，使数据库版本、端口、健康检查和数据卷能够被其他开发者按相同步骤复现，同时不提前引入Redis或业务表。

**输入、输出和上下游**

- 输入：M1-01的`.env.example`、Docker Desktop和已确认的“本阶段不启动Redis”边界；
- 输出：健康运行的PostgreSQL 17.11容器、仅本机可访问的5433端口、命名数据卷和启动/停止说明；
- 上游：M1-01应用配置和依赖基线；
- 下游：M1-03 SQLAlchemy连接、请求级事务和数据库健康检查。

**用大白话解释运行过程**

Docker Compose按照`docker-compose.yml`创建一台本项目专用的PostgreSQL。Windows程序通过`127.0.0.1:5433`访问它，容器内部仍使用标准5432。数据库文件放进`deep-search-postgres-data`命名卷，因此删除并重建容器时，数据不会随着容器外壳一起消失。Docker每5秒运行`pg_isready`，只有数据库真正接受连接时才标记为`healthy`。

**镜像和端口决定**

- 使用官方固定镜像`postgres:17.11-alpine3.24`，不使用会漂移的`latest`；PostgreSQL 17.11于2026-08-13发布，Docker官方存在对应标签：[PostgreSQL 17.11发布说明](https://www.postgresql.org/docs/17/release-17-11.html)、[Docker官方Postgres标签](https://hub.docker.com/_/postgres/tags?name=17.&page=1)；
- 最初按方案尝试宿主机5432，Docker发现该端口被另一工作区的健康PostgreSQL占用。本步没有停止或修改其他项目，而是将本项目改为`127.0.0.1:5433 → 容器5432`；
- 只绑定`127.0.0.1`，避免把使用本地演示密码的开发数据库暴露到局域网；
- `DATABASE_URL`使用明确的`127.0.0.1`而不是`localhost`，避免当前Windows优先解析IPv6 `::1`造成连接等待；
- M1不使用pgvector镜像，M2进入向量检索时再评估兼容的PostgreSQL 17 pgvector镜像。

**修改文件与职责**

- `docker-compose.yml`：定义唯一的`postgres`服务、固定镜像、环境变量、IPv4本地端口、健康检查、停止宽限期和命名卷；
- `.env.example`：把本项目宿主机PostgreSQL端口和`DATABASE_URL`统一调整为`127.0.0.1:5433`；
- `app/core/config.py`：同步默认`DATABASE_URL`，防止模板与应用默认值不一致；
- `tests/unit/test_app_baseline.py`：精确断言`.env.example`能够解析出本步骤确认的数据库地址；
- `README.md`：在旧原型说明前增加M1当前范围、数据库启动、健康检查、停止和数据保留说明；
- `docs/progress/M1/M1_INVENTORY_QUERY.md`、`docs/PROJECT_PROGRESS.md`：同步本步事实、验证结论和停止点。

Docker还创建了本地容器`deep-search-postgres`、网络`deep-search-pro_default`和命名卷`deep-search-postgres-data`。它们是本地运行状态，不是Git文件；当前容器按本步完成状态保持运行。

**调用链位置**

```text
前端（未经过）
→ API（未经过；/health仍不检查数据库）
→ Schema（未经过）
→ Service（未经过）
→ Model（未经过）
→ PostgreSQL（本步建立并验证基础服务）
```

本步只证明PostgreSQL基础设施可用，不代表Python应用已经建立数据库连接。

**验证方法与实际结果**

1. `docker version`确认客户端和服务端均为29.6.2，`docker compose version`为5.3.1；Docker Desktop最初未运行，按本步需要启动后引擎正常；
2. `docker compose config --quiet`通过，`config --services`严格只返回`postgres`，`config --images`只返回`postgres:17.11-alpine3.24`；
3. 首次启动发现宿主机5432被另一工作区容器占用；确认5433空闲后调整端口，没有停止、删除或修改对方容器；
4. `docker compose ps`显示`deep-search-postgres`为`healthy`，最终端口映射为`127.0.0.1:5433->5432/tcp`；
5. 容器内`pg_isready`返回`accepting connections`，SQL确认数据库为`deep_search_pro`、用户为`deep_search_app`、服务端版本为17.11；
6. 使用`.venv`中的psycopg从Windows宿主机连接`127.0.0.1:5433`成功，证明端口映射、密码认证和数据库身份有效；
7. 创建仅用于验证的`m1_02_persistence_probe`表，容器普通重启后成功读到`m1-02-volume-ok`标记；
8. 再次写入探针后执行不带`-v`的`docker compose down`，确认命名卷仍存在；重建新容器后成功读到`m1-02-recreate-ok`，证明数据不依赖旧容器外壳；
9. 两次持久化验证后均删除探针表，查询`public` Schema表数量为0，没有把测试表留给后续Alembic；
10. 调整数据库地址后重跑M1-01回归：pytest 7个测试通过，Ruff通过，mypy通过。
11. 最终边界检查确认Compose服务数量为1、名称为`postgres`、不包含Redis，容器持续为`healthy`；
12. README和两份进度文档代码围栏均闭合、本地链接损坏数为0、合并冲突标记为0；清理旧README的Token形状占位符后，常见真实密钥和私钥特征扫描为0；`git diff --check`仅保留Windows LF/CRLF转换提示。

**能够证明**

- Compose配置只有PostgreSQL，没有提前启动Redis或其他服务；
- PostgreSQL 17.11已经运行并达到应用可判断的健康状态；
- Windows宿主机能通过受限的`127.0.0.1:5433`和密码访问正确数据库；
- 命名卷在容器重启以及删除/重建后仍能保留数据；
- 探针数据已经清理，数据库没有M1业务表；
- 本步骤没有干扰占用5432的其他工作区。

**不能证明**

- `app`已经通过SQLAlchemy连接数据库或正确管理事务；
- Alembic迁移、身份表、库存表或合成数据已经存在；
- 数据库备份恢复、并发性能、生产高可用和云部署能力；
- pgvector已经安装或启用；
- 本地演示密码适合生产环境。

**常见问题与优先排查方向**

- Docker命令存在但无法连接引擎：先确认Docker Desktop已经启动并等待Linux Engine就绪；
- 容器启动时报`port is already allocated`：使用`docker ps --filter publish=端口`定位占用者，不要直接停止不属于本项目的容器；
- `localhost`连接等待但`127.0.0.1`成功：检查IPv4/IPv6解析和Compose实际绑定地址；
- 容器为`running`但不是`healthy`：查看`docker compose logs postgres`，再检查用户名、数据库名和健康检查；
- 修改`.env`密码后旧数据卷仍使用原密码：PostgreSQL初始化变量只在空数据目录第一次生效，需要通过SQL改密码，不能误以为改环境变量会自动修改已有账号；
- 重建后数据消失：检查是否误用了`docker compose down -v`或手工删除了`deep-search-postgres-data`；
- 应用仍连接5432：对照`.env.example`检查`DATABASE_URL`是否为`127.0.0.1:5433`。

**下一步**

停止开发并等待用户理解和确认本步结果；用户明确同意后才进入M1-03“建立SQLAlchemy连接和事务边界”。

### 2026-08-28｜M1-03｜建立SQLAlchemy连接和事务边界

**状态：已完成**

**本步解决的问题**

M1-02只有一台健康运行的PostgreSQL，还没有后端统一访问数据库的方式。本步使用SQLAlchemy建立Engine、Session工厂、模型Base和请求级事务依赖，使后端能够执行最小健康查询，并保证请求成功时提交、失败时回滚、结束时释放连接。

**输入、输出和上下游**

- 输入：`.env`或`.env.example`中的`DATABASE_URL`、连接超时和SQL日志开关；
- 输出：`DatabaseRuntime`中的Engine和Session工厂、ORM模型共同Base、FastAPI数据库依赖、真实数据库健康检查；
- 上游：M1-02 PostgreSQL容器；
- 下游：M1-04至M1-06 ORM模型和Alembic迁移，以及后续Repository。

**用大白话解释运行过程**

应用启动时先按照数据库地址准备一个“连接管理器”，但不会因为导入代码就立刻占用数据库连接。请求需要数据库时，FastAPI依赖会打开一个Session，也就是本次请求专用的数据库办事窗口。请求正常结束就提交；中途抛错就撤销本次尚未提交的操作；无论成功失败都会关闭Session，把连接归还连接池。`/health`会通过同一套连接执行`SELECT 1`：成功返回HTTP 200和`database=connected`，失败返回HTTP 503和`database=unavailable`，不会把驱动报错或密码交给调用方。

**技术决定与边界**

- M1继续使用同步SQLAlchemy和同步HTTP数据库调用，FastAPI会在线程池中执行同步健康检查；当前短查询链路不需要为了“技术数量”引入异步数据库驱动；
- API路由统一使用`DatabaseSession`依赖，它采用函数级作用域，保证提交或回滚完成后才向前端发送响应，避免“前端收到成功但随后提交失败”；
- Engine和Session工厂归属于每个FastAPI应用实例，保存在`application.state`，便于测试替换，也避免各模块各自创建连接池；
- `pool_pre_ping=True`在借出已有连接前检查其可用性；连接超时默认5秒，防止数据库不可达时无限等待；
- `Base`只为后续ORM模型提供共同父类，本步没有定义任何业务表；
- 健康接口只返回受控状态，不返回底层异常；SQL参数日志启用`hide_parameters`，降低敏感值进入日志的风险；
- M1-03没有引入Alembic。Alembic负责数据库表结构版本，必须等M1-04业务模型定义后再创建首个迁移。

**修改文件与职责**

- `app/db/__init__.py`：声明新数据库基础设施包；
- `app/db/base.py`：提供后续所有ORM模型共同继承的`Base`；
- `app/db/session.py`：创建Engine和Session工厂，并执行安全的`SELECT 1`健康检查；
- `app/api/__init__.py`：声明M1 API包；
- `app/api/dependencies.py`：提供请求级Session，统一提交、回滚和关闭；
- `app/core/config.py`、`.env.example`：新增1至30秒范围内的数据库连接超时，默认5秒；
- `app/main.py`：把数据库Runtime挂到应用实例，并让`/health`返回真实数据库状态；
- `tests/unit/test_app_baseline.py`：把原来的“数据库未检查”基线更新为M1-03行为，并用内存SQLite隔离单元测试；
- `tests/integration/test_database_connection.py`：使用真实PostgreSQL验证连接、身份、健康检查、提交、回滚、连接释放和错误脱敏；
- `tests/integration/__init__.py`：声明集成测试包；
- `README.md`：把当前可运行范围更新到M1-03，并补充后端启动和健康检查方法；
- `docs/progress/M1/M1_INVENTORY_QUERY.md`、`docs/PROJECT_PROGRESS.md`：记录本步事实、验证结论和新停止点。

**调用链位置**

```text
前端（未经过）
→ API（本步：/health和请求级数据库依赖）
→ Schema（未经过：健康响应暂未建立业务Schema）
→ Service（未经过）
→ Model（只建立共同Base，没有业务模型）
→ PostgreSQL（本步：连接、SELECT 1和事务验证）
```

**验证方法与实际结果**

1. PostgreSQL容器持续为`healthy`，映射仍为`127.0.0.1:5433->5432`；
2. SQLAlchemy通过真实连接执行`SELECT 1`，并确认数据库是`deep_search_pro`、用户是`deep_search_app`；
3. 真实`/health`返回HTTP 200和`database=connected`；
4. 测试API写入探针表后正常返回，依赖自动提交，另一连接能够读取数据；
5. 测试API在建表后主动抛错，依赖自动回滚，另一连接确认表不存在；
6. 成功和失败请求结束后连接池`checkedout()`均为0，证明连接已经归还；
7. 构造一个只有提交时才触发的延迟唯一约束错误，API返回HTTP 500而不是提前返回成功，事务回滚且探针表不存在；
8. 连接本机不可用端口时，在1秒超时边界内转换为`DatabaseConnectionError`；对外错误、HTTP 503正文均不包含测试密码或底层驱动细节；
9. 首轮测试发现FastAPI不能从“字典或JSONResponse”联合返回类型建立响应字段；将健康接口统一返回`JSONResponse`后重新全量验证通过；
10. `pytest -q`共15个测试通过；`ruff check app tests`、`mypy app`和`compileall app tests`全部通过；
11. 验证结束后查询PostgreSQL `public` Schema，表数量为0，提交探针、回滚探针和延迟约束探针均已清理；
12. `git diff --check`没有空白错误，仅报告Windows工作区已有的LF/CRLF转换提醒。

**能够证明**

- 后端能通过SQLAlchemy连接正确的PostgreSQL数据库和用户；
- 一个API请求可以获得独立Session，并按成功/失败完成提交或回滚；
- Session结束后连接能够归还连接池，不会因正常请求持续占用；
- 健康检查能区分数据库可用与不可用，并返回200或503；
- 对外数据库错误不包含密码和驱动细节；
- 本步没有留下测试表，也没有提前创建业务表。

**不能证明**

- 用户、角色、商品、仓库和库存表已经存在；
- Alembic可以升级或回退数据库结构；
- Repository库存查询、租户隔离和角色权限已经实现；
- 自然语言、千问、LangGraph、Agent Tool或前端聊天链路能够运行；
- 当前本地连接池参数适合生产并发、故障切换或云数据库部署。

**常见问题与优先排查方向**

- `/health`返回503：先运行`docker compose ps`确认容器为`healthy`，再核对`DATABASE_URL`中的主机、5433端口、数据库名和用户；
- 连接等待时间过长：检查`DATABASE_CONNECT_TIMEOUT_SECONDS`是否在1至30秒内，并确认使用`127.0.0.1`而不是可能解析到IPv6的`localhost`；
- 密码修改后认证失败：检查是否只改了`.env`而没有修改已存在数据卷内的PostgreSQL账号密码；
- 请求失败后数据仍存在：先确认路由使用的是`Depends(get_db_session)`提供的Session，且业务代码没有自行提前`commit()`；
- 连接数持续增加：检查Session是否绕开依赖手工创建，以及异常路径是否执行了`close()`；
- 测试提示表已经存在：说明上次测试被强制中断，按测试输出中的随机`m1_03_*`表名核对并只清理对应探针表。

**下一步**

停止开发并等待用户理解和确认本步结果；用户明确同意后才进入M1-04“建立身份和角色模型及迁移”。

### 2026-08-28｜M1-04｜建立身份和角色模型及迁移

**状态：已完成**

**本步解决的问题**

M1-03只能连接一座空数据库，不知道公司、用户、角色和数据范围如何保存。本步建立四张身份表及首个Alembic版本，使数据库能够保存“谁属于哪家公司、拥有什么角色、能看哪些市场”，并由PostgreSQL拒绝重复或非法身份数据。

**输入、输出和上下游**

- 输入：单演示租户、`company_owner`/`product_scout`/`amazon_operator`三角色和两位大写市场代码范围设计；
- 输出：`tenants`、`users`、`roles`、`user_roles`四张表，Alembic版本`20260828_0001`及对应约束；
- 上游：M1-03 SQLAlchemy连接、Base和事务边界；
- 下游：M1-05/M1-06其他业务模型、M1-07确定性Seed、后续登录和RunContext。

**用大白话解释运行过程**

SQLAlchemy模型是Python里的“表格设计图”，Alembic迁移是可执行、可编号的“施工单”。执行`alembic upgrade head`后，Alembic按照第一个施工版本创建四张表，并在`alembic_version`记录当前版本；执行`alembic downgrade base`会按依赖反序删除这四张表；再次升级能够原样重建。业务代码以后不会靠启动应用偷偷建表，而是显式执行迁移，因此其他开发者和部署环境可以得到相同结构。

四张表分别负责：

- `tenants`：公司边界、演示数据标记和创建时间；
- `users`：租户内登录身份、规范化小写邮箱、显示名、密码哈希和`active/disabled`状态；
- `roles`：只允许M1确定的三个角色名；
- `user_roles`：用复合主键关联用户与角色，并保存`DE`、`FR`这类市场范围数组。

**技术决定与边界**

- 主键统一使用UUID，便于未来合成数据使用确定性ID，也避免不同环境自增编号碰撞；本步不生成任何具体UUID记录；
- 时间统一使用带时区时间戳并由PostgreSQL写入当前时间；
- `users(tenant_id, email)`唯一，同时要求邮箱以小写保存，避免同一租户出现大小写不同的重复登录身份；
- 用户状态只允许`active`或`disabled`，角色名只允许M1三角色；
- `market_scopes`使用PostgreSQL字符串数组，必须包含1至20项，每项必须是两个大写字母且不能为NULL；本步验证`DE/FR`，不把数据库约束永久写死为只有德国和法国；
- 用户、角色或租户被删除时，关联关系通过外键级联清理，避免孤立记录；
- 约束采用稳定命名规则，使Alembic未来能够明确增删某个约束，不依赖数据库随机名称；
- `alembic.ini`不保存连接密码；`migrations/env.py`读取和应用相同的`Settings.database_url`；
- 本步不建立`permissions`、`role_permissions`，Tool允许角色仍按已确认计划由后续ToolRegistry声明；
- 三个角色记录和四个演示账号仍由M1-07 Seed统一生成，本步保持四张业务表为空；
- 本步没有登录API、JWT、PermissionGuard或任何库存查询逻辑。

**修改文件与职责**

- `app/db/base.py`：增加稳定的表、主键、外键、唯一约束、检查约束和索引命名规则；
- `app/models/__init__.py`：集中暴露M1新链路的ORM模型；
- `app/models/identity.py`：定义Tenant、User、Role和UserRole模型、关系及数据库约束；
- `alembic.ini`：Alembic入口和日志配置，不写数据库密码；
- `migrations/env.py`：连接应用配置与SQLAlchemy metadata，支持在线/离线迁移；
- `migrations/script.py.mako`：后续新迁移文件的统一模板；
- `migrations/README`：说明迁移目录和密钥边界；
- `migrations/versions/20260828_0001_identity_and_roles.py`：首个可升级、可回退的身份结构版本；
- `tests/unit/test_identity_models.py`：验证身份表注册、表名和UserRole复合主键；
- `tests/integration/test_identity_migration.py`：在真实PostgreSQL验证迁移往返、唯一约束、角色范围、市场格式和外键；
- `README.md`：更新当前范围并增加Alembic升级、查看版本和回退警告；
- `docs/progress/M1/M1_INVENTORY_QUERY.md`、`docs/PROJECT_PROGRESS.md`：记录本步事实、验证结论和新停止点。

**调用链位置**

```text
前端（未经过）
→ API（未经过；/health继续沿用M1-03）
→ Schema（未经过）
→ Service（未经过）
→ Model（本步：四个身份ORM模型）
→ PostgreSQL（本步：Alembic建表、约束、升级与回退）
```

**验证方法与实际结果**

1. 执行Alembic升级、回退到`base`、再次升级到`20260828_0001`，四张表按顺序消失并原样恢复；测试结束的`current`为`20260828_0001 (head)`；
2. `alembic check`返回`No new upgrade operations detected`，证明当前模型metadata与迁移后的数据库结构没有待生成差异；
3. 重复插入同租户同邮箱、含大写字母的邮箱或非法用户状态，PostgreSQL抛出`IntegrityError`；
4. 写入未批准角色名、空市场数组、小写`de`市场或不存在的用户外键，PostgreSQL均拒绝；
5. 写入合法的`amazon_operator`与`["DE", "FR"]`市场范围成功，随后整体事务回滚，未留下测试数据；
6. 首轮非法数据测试在预期异常后错误释放失败的保存点，确认失败位于测试事务控制；调整为保存点先回滚、测试断言后捕获后，专项测试通过；
7. 全量`pytest -q`共21项通过；Ruff检查通过且20个Python文件均符合格式；Mypy检查11个应用文件无类型问题；编译和`pip check`通过；
8. 最终PostgreSQL公共表为`alembic_version/roles/tenants/user_roles/users`，四张身份表行数均为0；
9. 容器保持`healthy`，没有启动Redis，没有创建商品、库存、运行、Evidence或后续阶段表。

**能够证明**

- 身份结构由可追踪的Alembic版本管理，能够升级、回退和重建；
- Python ORM模型和迁移后的PostgreSQL结构一致；
- 同租户邮箱唯一、合法角色名、市场范围格式和外键完整性由数据库强制执行；
- 四张表已真实存在，且没有提前插入任何演示或真实公司数据；
- 迁移配置复用应用数据库地址，没有把密码复制到Alembic配置。

**不能证明**

- 三种角色或四个演示账号已经存在；
- 密码哈希已经由Argon2生成或用户能够登录；
- 用户获得角色后PermissionGuard会正确允许或拒绝Tool；
- 商品、仓库、库存、会话、Trace或Evidence表已经存在；
- 租户隔离的Repository查询和自然语言库存闭环已经实现；
- 级联删除是对外开放的业务功能；M1只建立数据库完整性行为，不提供删除API。

**常见问题与优先排查方向**

- `alembic current`没有版本：先确认`DATABASE_URL`指向本项目5433端口，再执行`alembic upgrade head`；
- Alembic显示最新但缺表：检查实际连接的数据库名、`migrations/env.py`是否导入模型以及`alembic_version`内容；
- `alembic check`报告新增操作：对比ORM模型和最近迁移，不能直接忽略或盲目生成重复迁移；
- 插入邮箱被小写约束拒绝：进入后续Schema/Service时统一先做`strip().lower()`，不要删除数据库防线；
- 市场范围写入失败：检查是否为空、包含NULL或使用了`de`这类非两位大写代码；
- 测试中一次约束失败导致后续SQL全部失败：需要回滚当前事务或使用保存点隔离预期异常；
- 回退后表消失：这是`downgrade base`的预期行为；正常开发使用`upgrade head`，不要把回退命令当作日常启动命令。

**下一步**

停止开发并等待用户理解和确认本步结果；用户明确同意后才进入M1-05“建立商品和库存模型及迁移”。

### 2026-08-28｜M1-05｜建立商品和库存模型及迁移

**状态：已完成**

**本步解决的问题**

M1-04只有身份边界，数据库还不知道商品、SKU、规格、仓库和某时刻库存如何保存。本步新增五张业务表和第二个Alembic版本，使PostgreSQL能够保存库存查询所需的原始事实，并在数据库层拒绝重复SKU、跨租户关联、负库存和不可能的库存分配。

**输入、输出和上下游**

- 输入：SPU/SKU、中文英文商品名、别名、规格来源、仓库市场、库存数量和快照时间设计；
- 输出：`products`、`product_variants`、`product_specs`、`warehouses`、`inventory_snapshots`五张表和迁移版本`20260828_0002`；
- 上游：M1-03数据库运行时、M1-04租户表和首个迁移；
- 下游：M1-07确定性Seed、M1-09固定Repository、商品规格和库存Service。

**用大白话解释运行过程**

商品域回答“这是什么”：`products`保存SPU级商品，`product_variants`保存实际可查询的SKU，`product_specs`保存高度、材质等可追溯规格。库存域回答“货在哪里、某时有多少”：`warehouses`保存仓库和市场，`inventory_snapshots`保存某SKU在某仓库、某时间点的原始数量。

库存快照不保存`available`字段。后续Service统一计算：

```text
available = on_hand - reserved - unsellable
```

这样不会出现“原始数量已经修改，但数据库里旧的available忘记同步”的双重事实。数据库仍强制`reserved + unsellable <= on_hand`，保证计算结果不会为负。

**技术决定与边界**

- 五张业务表全部直接带`tenant_id`；SKU到商品、规格到SKU、库存到SKU和仓库使用包含`tenant_id`的复合外键，数据库会拒绝把A公司的SKU挂到B公司的商品或仓库；
- `products(tenant_id, spu)`、`product_variants(tenant_id, sku)`和`warehouses(tenant_id, code)`分别唯一；
- 库存唯一键为`tenant_id + variant_id + warehouse_id + snapshot_at`，同一SKU、仓库和时间只能有一个快照；
- SKU和SPU只允许大写字母、数字和连字符；仓库代码采用`DE-FRA`格式，市场代码采用两位大写字母；
- 商品和SKU状态允许`candidate/active/inactive/discontinued`，兼容M1候选新品蘑菇灯；
- 商品别名使用最多20项的PostgreSQL数组，便于后续受控解析“蘑菇灯”和英文别名；
- 规格记录包含`value/unit/source_type/source_id/verification_status`；M1合成Seed将使用`synthetic_seed + demo_declared`，同时为后续供应商文档和图片观察保留明确来源类型；
- 所有库存数量必须非负，并且预留加不可售不能超过在库；`available`不落库；
- 仓库建立`tenant_id + market_code`索引，为后续按租户和DE/FR市场查询减少扫描范围；
- 商品、仓库和库存用`is_demo`明确标记合成演示事实；SKU和规格可通过所属商品唯一追溯演示属性；
- 本步只建立结构，五张新表行数保持0，没有插入蘑菇灯、德国仓或任何库存；
- 本步没有Repository、Service、Tool、Evidence、登录、权限或前端代码。

**修改文件与职责**

- `app/models/catalog.py`：定义Product、ProductVariant和ProductSpec及租户、唯一性、格式和来源约束；
- `app/models/inventory.py`：定义Warehouse和InventorySnapshot，包含市场索引、库存唯一键和数量检查；
- `app/models/__init__.py`：集中注册并暴露M1-04/M1-05全部ORM模型；
- `migrations/env.py`：把新增五个模型注册进Alembic metadata；
- `migrations/versions/20260828_0002_catalog_and_inventory.py`：创建和回退商品库存结构；
- `tests/unit/test_catalog_inventory_models.py`：验证五张表注册并确认`available`不是存储字段；
- `tests/integration/test_catalog_inventory_migration.py`：使用真实PostgreSQL验证迁移往返、唯一键、复合外键和库存检查；
- `README.md`：更新到M1-05范围、Alembic版本、回退边界和可售库存公式；
- `docs/progress/M1/M1_INVENTORY_QUERY.md`、`docs/PROJECT_PROGRESS.md`：记录本步事实、验证结论和新停止点。

**调用链位置**

```text
前端（未经过）
→ API（未经过；/health继续沿用M1-03）
→ Schema（未经过）
→ Service（未经过；available尚未实际计算）
→ Model（本步：五个商品库存ORM模型）
→ PostgreSQL（本步：第二个迁移、表、索引和约束）
```

**验证方法与实际结果**

1. 从`20260828_0001`升级到`20260828_0002`，五张表出现；回退到`0001`时只删除五张商品库存表，四张身份表保留；再次升级能原样恢复；
2. `alembic current`最终为`20260828_0002 (head)`；`alembic check`返回`No new upgrade operations detected`，模型和迁移结构一致；
3. 在真实事务中写入合法租户、蘑菇灯商品、`LR-TL-MUSH-OR01` SKU、30cm规格、`DE-FRA`仓库和150/20/5/80/60库存快照成功；事务最终回滚，不留下Seed数据；
4. 重复SKU、重复仓库代码和同SKU/仓库/时间的重复快照均被唯一约束拒绝；
5. 把另一个租户的SKU挂到当前商品，或用另一个租户把当前SKU和仓库组成库存快照，均被复合外键拒绝；
6. 写入负数`inbound`，或让`reserved + unsellable > on_hand`，均被库存检查约束拒绝；
7. 开发中在已执行的未交付`0002`迁移里补充仓库市场索引后，本地数据库出现“版本号相同但缺索引”；先补齐同名索引恢复开发状态，再由正式回退/升级测试删除并重建完整结构；最终`alembic check`无差异，运行不依赖手工索引；
8. 全量`pytest -q`共27项通过；Ruff检查通过且25个Python文件格式正确；Mypy检查13个应用文件无类型问题；编译和`pip check`通过；
9. 最终PostgreSQL公共表为9张业务表加`alembic_version`；五张新业务表行数均为0，容器保持`healthy`；
10. 未创建M1-06运行/Evidence表，未启动Redis，也未修改旧`agent/api/tools`运行代码。

**能够证明**

- 商品、SKU、规格、仓库和库存快照结构可以独立升级、回退和重建；
- Python ORM模型与真实PostgreSQL第二版结构一致；
- 数据库能阻止重复SKU、重复仓库、重复库存快照、跨租户引用和非法库存数量；
- 原始库存字段能够支持后续按统一公式计算可售库存；
- 按租户和市场查询所需的数据列、约束和索引已经存在；
- 当前表中没有真实公司数据或合成演示记录。

**不能证明**

- 蘑菇灯、德国仓和150/20/5等演示数据已经生成；
- `available=125`已经由Service实际计算；
- Repository能够按SKU、市场和最新时间返回正确快照；
- 重复名称、歧义商品和无库存错误已经被业务层处理；
- 用户权限能够限制DE或FR市场；
- Evidence、Trace、Agent Tool、LangGraph、聊天API或前端页面已经实现。

**常见问题与优先排查方向**

- `alembic current`仍是`0001`：执行`alembic upgrade head`，再确认连接的是本项目5433数据库；
- 版本显示`0002`但`alembic check`报告缺表或索引：数据库可能执行过旧的开发期迁移文件；先对比实际结构与迁移，不要只修改`alembic_version`；
- SKU或仓库写入失败：检查是否使用大写字母/数字/连字符，以及仓库是否符合`DE-FRA`这类格式；
- 合法ID仍报外键失败：同时核对`tenant_id`，复合外键会主动拒绝跨租户拼接；
- 库存写入失败：先检查五个数量是否非负，再检查`reserved + unsellable`是否超过`on_hand`；
- “可售库存字段在哪里”：它故意不在表里，后续Service从三个原始字段计算，前端也不得自行计算；
- 最新库存查询慢：后续Repository应严格带租户、SKU、仓库/市场和时间排序条件，不能把性能问题交给模型生成SQL解决。

**下一步**

停止开发并等待用户理解和确认本步结果；用户明确同意后才进入M1-06“建立会话、运行、Tool审计和Evidence模型”。

### 2026-08-28｜M1-06｜建立会话、运行、Tool审计和Evidence模型

**状态：已完成**

**本步解决的问题**

M1-05已经能保存身份、商品和库存事实，但系统还没有位置记录“哪次聊天触发了哪次Agent运行、运行调用了什么Tool、权限结果是什么、答案依据哪条证据”。本步新增五张运行域表和第三个Alembic版本，把会话、trace、Tool审计和Evidence变成可关联、可约束的数据库事实。

**输入、输出和上下游**

- 输入：会话、消息摘要、唯一`trace_id`、路由、预算计数、Tool版本/权限/耗时、Evidence来源/定位/结构化数据/访问范围字段合同；
- 输出：`threads`、`messages`、`agent_runs`、`tool_calls`、`evidences`五张表和迁移版本`20260828_0003`；
- 上游：M1-04用户/租户模型、M1-05业务表和M1-03事务边界；
- 下游：M1-07 Seed、后续基础Trace、Tool执行、聊天API和Evidence详情API。

**用大白话解释运行过程**

这五张表是一套“运行账本”：

```text
Thread：哪段聊天
→ Message：用户问题或助手回答摘要
→ AgentRun：这次处理的trace、路由、状态和预算计数
→ ToolCall：调用了什么Tool、版本、权限结果、参数摘要和耗时
→ Evidence：答案使用了哪条数据库事实、数据时间和访问范围
```

`trace_id`像一次执行的快递单号。以后看到某个回答有问题，可以从一个编号追到运行、Tool和Evidence。Evidence不只是日志文本，而是保存来源类型、表记录定位、安全查询摘要、回答使用的结构化字段、业务数据时间以及租户/市场访问范围。

**技术决定与边界**

- `threads`通过`tenant_id + user_id`复合外键绑定用户；`agent_runs`再通过`tenant_id + thread_id + user_id`确保运行用户就是会话所有者，不能在同一租户内串到另一个人的会话；
- `trace_id`全局唯一；运行状态只允许`running/completed/failed/denied/timed_out`，模型和Tool调用计数、耗时不能为负，结束时间不能早于开始时间；
- `messages`只允许`user/assistant`，保存1至4000字符的`content_summary`，不建立原始模型输入输出字段；
- `tool_calls`记录递增序号、Tool名称、版本、JSON参数摘要、`allowed/denied`权限结果、状态、耗时和安全错误摘要；同一运行中的序号不能重复；
- `arguments_summary`必须是JSON对象，不能写入数组或任意原始载荷；未来Harness仍负责真正脱敏，数据库负责结构防线；
- Evidence必须通过`tenant_id + tool_call_id + agent_run_id`复合外键指向同一次运行的ToolCall，避免把另一次运行的证据误挂到当前答案；
- M1 Evidence只允许`source_type=database`和`synthetic_inventory/synthetic_product_catalog`两个来源名；RAG、网页、文件、图片Evidence等后续阶段再通过新迁移扩展；
- `query_summary`、`structured_data`和`access_scope`必须是JSON对象；置信度在0至1之间；M1强制`synthetic_data=true`；
- `source_locator`只预留`表名/记录UUID`这类安全定位，表结构没有连接串或原始SQL字段；
- 本步为`users(tenant_id, id)`增加唯一约束，供会话复合外键可靠引用；不修改M1-04已执行迁移，而是在`0003`中版本化增加和回退；
- 五张新表保持为空，本步没有真正执行Agent、Tool、EvidenceService或聊天请求；
- 不建立`tasks`、`task_steps`、`skill_runs`、`checkpoints`、claims、reports、RAG或评估表。

**修改文件与职责**

- `app/models/runtime.py`：定义Thread、Message、AgentRun、ToolCall和Evidence模型、关系、JSON字段和约束；
- `app/models/identity.py`：补充用户租户复合唯一键，支持会话的租户一致性外键；
- `app/models/inventory.py`：明确库存快照的SKU/仓库复合关系共享`tenant_id`，消除ORM写入关系歧义；
- `app/models/__init__.py`：集中注册并暴露14个M1业务模型；
- `migrations/env.py`：把五个运行域模型加入Alembic metadata；
- `migrations/versions/20260828_0003_runtime_and_evidence.py`：创建、索引和回退运行/Evidence结构；
- `tests/unit/test_runtime_models.py`：验证五张表、trace唯一、JSONB类型和不保存原始模型载荷；
- `tests/integration/test_runtime_migration.py`：使用真实PostgreSQL验证迁移往返、租户链、trace、状态、JSON、来源和Evidence链路；
- `README.md`：更新到M1-06、第三版迁移、14张业务表和Evidence边界；
- `docs/progress/M1/M1_INVENTORY_QUERY.md`、`docs/PROJECT_PROGRESS.md`：记录本步事实、验证结论和新停止点。

**调用链位置**

```text
前端（未经过）
→ API（未经过；尚未创建聊天和Evidence路由）
→ Schema（未经过）
→ Service（未经过；尚未生成Trace或Evidence）
→ Model（本步：五个运行/Evidence ORM模型）
→ PostgreSQL（本步：第三个迁移、表、索引、JSON和关系约束）
```

**验证方法与实际结果**

1. 从`20260828_0002`升级到`20260828_0003`，五张运行表出现；回退到`0002`只删除本步五张表和用户复合唯一约束，身份、商品和库存表保留；再次升级能够原样恢复；
2. `alembic current`最终为`20260828_0003 (head)`；`alembic check`返回`No new upgrade operations detected`，模型和数据库结构一致；
3. 真实事务中写入合法租户、用户、Thread、用户Message、完成的AgentRun、`search_inventory` ToolCall和数据库Evidence成功，最终整体回滚；
4. 用当前租户绑定另一个租户的用户创建Thread，被复合外键拒绝；
5. 写入非法`tool`消息角色、重复`trace_id`或JSON数组形式的Tool参数摘要，均被数据库拒绝；
6. 建立第二次运行和`get_product_spec` ToolCall后，尝试把它的ToolCall挂到第一次运行的Evidence，被三列复合外键拒绝；
7. 将网页来源伪装成M1 Evidence，或将`access_scope`写成JSON数组，均被数据库检查约束拒绝；
8. 在把SQLAlchemy映射警告升级为错误后，发现库存快照的SKU和仓库关系共享`tenant_id`但未显式声明；使用`overlaps`明确这是有意的复合外键共享，并新增全模型映射检查，最终所有ORM关系无警告完成配置；
9. 全量`pytest -q`共35项通过；Ruff检查通过且29个Python文件格式正确；Mypy检查14个应用文件无类型问题；编译和`pip check`通过；
10. 最终PostgreSQL公共表为14张业务表加`alembic_version`，本步五张表行数均为0，容器保持`healthy`；
11. 未启动Redis，未创建后续阶段表，未修改旧`agent/api/tools`运行代码。

**能够证明**

- 会话、运行、Tool和Evidence事实有明确的PostgreSQL持久化位置；
- 一个唯一trace能够关联到正确租户、用户和Thread；
- Tool名称、版本、权限结果、调用顺序、参数摘要、耗时和错误有受控字段；
- Evidence不能跨运行串接，M1来源、JSON对象、访问范围、合成标记和置信度能够被数据库约束；
- 第三版迁移可以独立回退，M1方案中的14张业务表已全部建立且为空。

**不能证明**

- 真实聊天请求会创建Thread、Message和AgentRun；
- Harness会正确记录每次路由、权限检查、预算和Tool调用；
- Tool参数摘要已经完成字段级脱敏；表结构只能限制类型，不能判断字符串内容是否敏感；
- EvidenceService会从Repository结果生成正确的125库存证据；
- Evidence先落库、回答后生成的事务顺序已经实现；
- 聊天API、Evidence API、LangGraph、前端或真实Agent执行已经存在。

**常见问题与优先排查方向**

- `trace_id`重复：确认每次运行在进入图前生成新UUID，不要复用Thread ID或Message ID；
- Thread创建报外键错误：同时核对用户ID和租户ID，不能只确认用户ID存在；
- AgentRun无法关联Thread：确认运行中的`tenant_id/thread_id/user_id`三项与Thread完全一致；
- Tool JSON写入失败：`arguments_summary`必须是JSON对象；数组、字符串和原始序列化日志都不符合M1合同；
- Evidence外键失败：检查`tool_call_id`是否确实属于同一个`agent_run_id`，不能只改一个ID；
- Evidence来源被拒绝：M1只允许数据库合成证据，网页/RAG/文件/图片要等后续阶段迁移扩展；
- `synthetic_data=false`被拒绝：这是M1强制边界，当前项目禁止把演示链路标成真实公司数据；
- 表已经存在但没有Trace：M1-06只建存储位置，真正写入行为要等后续Trace、Tool和聊天Service步骤。

**下一步**

停止开发并等待用户理解和确认本步结果；用户明确同意后才进入M1-07“生成可重复的合成演示数据”。
