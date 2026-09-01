# M1-07 至 M1-11：合成数据、业务合同与库存核心

> 本文件保存从迁移前单文件中拆出的完整历史方案、实施日志与验证证据。
> 当前状态和阅读入口见 [M1入口](../M1_INVENTORY_QUERY.md)。

### 2026-08-28｜M1-07｜生成可重复的合成演示数据

**状态：已完成**

**本步解决的问题**

M1-06结束时14张业务表已经存在，但全部为空。没有固定账号、商品和库存，后续Repository、权限和Agent Tool既无法开发，也无法得到每次一致的测试结果。本步建立`m1-v1`合成数据合同、可重复Seed脚本和manifest，并把演示数据实际写入本地PostgreSQL。

**输入、输出和上下游**

- 输入：固定版本`m1-v1`、固定随机种子`20260828`、版本化JSON业务事实和本地`M1_DEMO_PASSWORD`；
- 输出：1个演示租户、3个角色、4个账号与角色范围、1个蘑菇灯商品和SKU、4条规格、2个仓库、2条库存快照及稳定manifest；
- 上游：M1-04身份表、M1-05商品库存表、M1-06运行表和M1-03数据库Session；
- 下游：M1-08 Schema、M1-09 Repository、登录与权限测试、两个Agent Tool和最终演示。

**用大白话解释运行过程**

Seed可以理解为“给空数据库装一套标准样板”。`m1_seed.json`是装箱清单，写明要装哪些人、商品、仓库和库存；`seed_m1.py`是装箱工人；`m1_manifest.json`是装完后的验收单。

脚本先把`版本 + 数据类型 + 业务唯一键`转换成固定UUID，再逐条检查数据库：没有就新增，有且一致就保留，有但内容被改过就报错并整体回滚。这样重复执行不会增加第二个蘑菇灯或第二条相同库存。密码不在Seed JSON中，数据库只保存根据本地演示密码生成的Argon2不可逆哈希。manifest只对固定业务JSON计算内容哈希，不把带随机盐的密码哈希算进去，因此业务输入不变时结果文件保持一致。

```text
固定JSON业务事实
→ Seed脚本校验版本和“合成演示数据”标记
→ SQLAlchemy Session开启事务
→ Model按依赖顺序写入或核对
→ PostgreSQL约束最终把关
→ 成功提交后生成稳定manifest
```

**固定演示样本**

- 三类角色、四个账号：负责人和选品人员可看DE/FR；德国运营只看DE；法国运营只看FR；
- 蘑菇灯SKU：`LR-TL-MUSH-OR01`，商品状态为`candidate`，所有商品/仓库/库存均标记为演示数据；
- 德国仓`DE-FRA`：期末150、预留20、不可售5、在途80、安全库存60，可售`150 - 20 - 5 = 125`；
- 法国仓`FR-CDG`：期末70、预留10、不可售0、在途30、安全库存40，可售60；
- 快照时间统一为`2026-08-28T06:00:00Z`，对应德国和法国夏令时`08:00`；
- 运行域五张表不伪造Agent记录，继续保持0行，等待后续真实执行链写入。

**技术决定与边界**

- 采用“确定性UUID + 已有数据核对”，不使用会悄悄覆盖手工变化的通用upsert；
- Seed只负责开发演示数据，不创建或修改表结构，建表仍由Alembic负责；
- `available`只写入manifest作为验收答案，不写入库存表；数据库仍只保存原始数量，后续Service负责正式计算；
- JSON中不保存密码；四个账号的本地初始密码来自集中配置`Settings.m1_demo_password`；
- Argon2每次从空库生成的哈希可能因随机盐不同，但同一次数据库重复Seed会验证密码而不改写哈希；稳定性由业务JSON的SHA-256内容哈希证明；
- 本步没有实现Repository、Pydantic业务Schema、登录、PermissionGuard、Trace写入、Agent Tool、LangGraph、API或前端；
- 未启动Redis，未修改或导入旧`agent/api/tools`运行代码。

**修改文件与职责**

- `data/seed/m1_seed.json`：唯一声明M1固定合成业务事实，不包含密码；
- `scripts/seed_m1.py`：生成确定性UUID，写入或核对现有记录，计算关键答案并输出manifest；
- `scripts/__init__.py`：允许通过`python -m scripts.seed_m1`从项目根目录安全运行脚本；
- `data/seed/m1_manifest.json`：记录版本、固定种子、业务内容哈希、各表Seed行数和德国仓关键答案；
- `app/core/config.py`：集中提供受`SecretStr`保护的本地演示密码配置；
- `.env.example`：说明`M1_DEMO_PASSWORD`仅限本地演示；
- `tests/integration/test_seed_m1.py`：使用真实PostgreSQL验证首次生成、重复执行、行数、关键答案、权限样本、演示标记和密码哈希；
- `README.md`：补充Seed命令、四个账号、密码边界和固定演示答案；
- `docs/progress/M1/M1_INVENTORY_QUERY.md`、`docs/PROJECT_PROGRESS.md`：记录本步事实、验证结论和新停止点。

**调用链位置**

```text
前端（未经过）
→ API（未经过）
→ Schema（未经过；M1-08才建立业务数据合同）
→ Service（未经过；本步是独立开发数据入口）
→ Model（本步：通过现有ORM对象写入并核对）
→ PostgreSQL（本步：实际保存固定合成演示数据）
```

**验证方法与实际结果**

1. 集成测试先清理仅属于`m1-v1`的固定租户和角色，从空业务表运行Seed成功；随后再次运行，manifest对象和文件字节完全一致，各表没有重复行；
2. manifest内容哈希固定为`sha256:6c18f37c52fc8c5c98df0e6b3f58307b0c8752f04aecdf2190a92477cd4a70f5`；实际连续执行两次默认Seed命令，manifest文件SHA-256保持相同；
3. 真实PostgreSQL最终行数为：租户1、角色3、用户4、用户角色4、商品1、SKU 1、规格4、仓库2、库存快照2；五张运行域表均为0；
4. 数据库查询确认`LR-TL-MUSH-OR01`在`DE-FRA`为150/20/5，按公式得到125，在`FR-CDG`为70/10/0，按公式得到60，两条快照均为`is_demo=true`；
5. 四个用户分别绑定预期角色和`{DE,FR}`、`{DE}`或`{FR}`市场范围；四条密码值均以`$argon2id$`开头，不等于明文，并能用本地演示密码验证；
6. 第一次测试运行暴露了测试使用底层Connection读取ORM时只得到UUID的问题；只把该段读取改为ORM Session后重新验证通过，Seed生产逻辑无需修改；
7. 全量`pytest -q`共36项通过；Ruff检查通过且32个Python文件格式正确；Mypy检查16个`app/scripts`文件无类型问题；编译和`pip check`通过；
8. PostgreSQL 17.11容器保持`healthy`，最终迁移版本仍为`20260828_0003 (head)`；全量迁移测试结束后已重新执行Seed恢复演示数据；
9. 未执行登录、Repository查询、Agent、Tool、Trace、Evidence生成、聊天API或前端测试；未提交或推送Git。

**能够证明**

- 从空业务表可以得到固定且内部关系一致的M1合成演示数据；
- 同一版本Seed可以安全重复执行，不制造重复账号、SKU、仓库或库存；
- 德国仓关键答案和原始库存公式固定为125，后续层可以据此做确定性测试；
- 三类角色、四个用户和DE/FR权限范围样本已经真实存在于PostgreSQL；
- 数据和manifest明确标记为合成演示数据，密码没有以明文写入JSON或数据库；
- Seed输入内容是否变化可以由稳定SHA-256哈希发现。

**不能证明**

- 后续Repository能正确选择最新库存，或能阻止跨租户、跨市场查询；
- Service已经正式计算`available=125`并生成数据库Evidence；
- 用户现在能够登录，密码哈希存在不等于认证Service已经实现；
- 模型能够识别“德国仓蘑菇灯”，或Agent能够选择正确Tool；
- Trace、ToolCall和Evidence会在真实请求中写入；
- 前端、API或完整库存查询闭环已经可用；
- 这些合成数据能代表真实Amazon或公司数据质量。

**常见问题与优先排查方向**

- Seed提示表不存在：先执行`alembic upgrade head`并确认当前版本为`0003`；
- Seed连接失败：确认Docker容器为`healthy`、`.env`的`DATABASE_URL`使用`127.0.0.1:5433`；
- 重跑提示现有数据不一致：先核对报错对象是否被手工修改，不要直接绕过核验或删除整库；
- 密码不匹配：确认`.env`中的`M1_DEMO_PASSWORD`是否在首次Seed后被修改；当前策略不会静默重置已有密码；
- manifest哈希变化：优先比较`m1_seed.json`业务字段、数组顺序和版本，不要把密码哈希或当前时间加入manifest；
- 行数重复：检查是否绕开Seed脚本直接插入相同自然键，或改动了确定性ID规则；
- 时间看起来是`06:00`而不是`08:00`：数据库保存UTC，同一时刻在德国/法国夏令时显示为`08:00`；
- 表里没有`available`列：这是设计边界，后续Service统一计算，不能为了演示数字提前增加冗余字段。

**下一步**

停止开发并等待用户理解和确认本步结果；用户明确回复“确认M1-07，可以进入M1-08”后，才进入M1-08“冻结Pydantic输入、输出和错误合同”。

### 2026-08-28｜M1-08｜冻结Pydantic输入、输出和错误合同

**状态：已完成**

**本步解决的问题**

M1-07已经提供固定账号、商品和库存，但前端、模型、Tool、Service和API还没有共享的数据格式。如果各层自行决定字段，后续很容易出现“模型传入tenant_id”“库存结果少数据时间”“错误响应夹带SQL”或“前端按另一套字段解析”等问题。本步建立严格Pydantic合同，先固定什么数据可以进、什么数据必须出、什么情况必须拒绝。

**输入、输出和上下游**

- 输入：M1方案第7.10至7.14节确定的Tool、错误、认证、聊天和Evidence字段，以及M1-07的SKU、市场、仓库、库存和合成标记；
- 输出：认证、聊天、商品、库存、Evidence、`ToolEnvelope`、`ToolMeta`、`ErrorDetail`和`ApiErrorResponse`等可复用Schema；
- 上游：产品目标、数据库字段合同和M1-07固定样例；
- 下游：M1-09 Repository、M1-10/M1-11 Service、登录、Harness、Provider、Agent Tool、FastAPI和Next.js；
- 本步没有使用数据库Session，不读取或修改PostgreSQL业务数据。

**用大白话解释运行过程**

Schema像整条链路统一使用的“快递箱规格和安检表”。例如模型想表达库存意图时，只能装入商品词、DE/FR市场和可选仓库；没有名为`sql`、`tenant_id`或数据库连接的格子。后续代码收到数据时先过Pydantic校验，合格后才允许交给Service或Repository。

```text
未来的前端/模型/Tool输入
→ Pydantic检查字段、类型、格式和字段之间的关系
├─ 不合格：生成结构化校验错误，不进入后续层
└─ 合格：形成有类型的Python对象，供后续Service使用
```

Schema还检查结果本身是否自相矛盾。例如Tool状态为`success`时必须有`data`且不能同时有`error`；状态为`error`时必须有标准错误，不能夹带业务数据和Evidence ID。库存结果必须满足`available = on_hand - reserved - unsellable`，但正式计算仍由M1-11 Service承担。

**技术决定与边界**

- 所有M1公开Schema继承`M1Schema`，统一使用`extra=forbid`；未知字段不是被悄悄忽略，而是立即报错；
- SKU只允许3至64位大写字母、数字和连字符；仓库使用`DE-FRA`格式；市场只允许`DE|FR`；
- `warehouse_code`存在时必须以当前市场开头，例如DE请求不能携带`FR-CDG`；
- `InventoryIntent`只表示`inventory_query`及其受控参数，不存在SQL、tenant、Session或数据库连接字段；
- `tenant_id`只出现在后端可信的当前用户和Evidence访问范围响应中，不进入模型控制的Tool输入；
- 时间字段使用Pydantic的`AwareDatetime`，必须带UTC或明确时区，避免`06:00`究竟属于哪个地区的歧义；
- `synthetic_data`使用`Literal[True]`，M1结果不能被调用方伪装成真实公司数据；
- Error只允许10类既定错误码，公开字段只有`code/message/retryable/field`；额外的`sql/stack/connection_string/api_key`会被拒绝；
- Schema只能限制错误对象有哪些字段，不能判断未来Service写入`message`的每段自然语言是否泄密；真正的异常脱敏仍由后续错误映射实现；
- 登录输入用`SecretStr`避免调试序列化直接暴露密码，登录响应不包含密码或密码哈希；访问Token必须作为真实字符串返回给客户端，因此不能使用会掩码输出的`SecretStr`；
- Evidence详情使用严格的商品/库存查询摘要和结构化结果联合类型，不接受任意JSON SQL字段；来源只允许M1数据库合成目录；
- 本步没有创建API路由、Repository、Service、RunContext、权限、Tool实现、Provider、LangGraph或前端，也没有修改数据库迁移。

**修改文件与职责**

- `app/schemas/common.py`：统一严格基类、SKU/市场/角色/Tool等公共类型、10类错误码、Tool元数据和成功/失败外壳；
- `app/schemas/auth.py`：登录输入、当前用户和登录响应合同，规范化邮箱并隔离密码哈希；
- `app/schemas/chat.py`：建会话、聊天问题、执行摘要和同步聊天成功响应；
- `app/schemas/product.py`：`get_product_spec`输入、规格条目和商品结果；
- `app/schemas/inventory.py`：模型库存意图、`search_inventory`输入和库存结果及公式校验；
- `app/schemas/evidence.py`：Evidence摘要、详情、安全查询摘要、结构化数据和访问范围；
- `app/schemas/__init__.py`：集中导出M1 Schema，给后续层提供稳定导入入口；
- `tests/unit/test_schemas.py`：17项Schema边界测试；
- `README.md`：说明Schema作用、安全边界以及“合同存在不等于链路已运行”；
- `docs/progress/M1/M1_INVENTORY_QUERY.md`、`docs/PROJECT_PROGRESS.md`：记录实际实现、验证和M1-09前停止点。

**调用链位置**

```text
前端（未经过；未来消费这些字段）
→ API（未经过；尚未建立业务路由）
→ Schema（本步：严格校验输入、输出和错误）
→ Service（未经过）
→ Model（未经过；本步没有使用ORM）
→ PostgreSQL（未经过；本步没有查询或写入）
```

**验证方法与实际结果**

1. `product_query`能够去除首尾空格并接收“蘑菇灯”，额外`tenant_id`被拒绝；
2. 合法SKU `LR-TL-MUSH-OR01`通过，`sku@@@`、小写、过短和带空格SKU均被拒绝；
3. 市场只接受DE/FR，DE与`FR-CDG`的错误组合被跨字段校验拒绝；
4. `InventoryIntent`可以表达“蘑菇灯+DE”，额外`sql`和`tenant_id`字段均被拒绝；
5. 150/20/5/125库存结果通过；available改为126、负库存或无时区时间均被拒绝；
6. 商品结果缺少规格或把`synthetic_data`设为false时被拒绝；
7. 登录邮箱被规范化为小写；密码不会以明文出现在Schema JSON中；输入夹带`password_hash`被拒绝，登录响应不存在密码字段；
8. Tool成功外壳缺少data、成功同时带error、错误夹带Evidence ID等矛盾结构均被拒绝；
9. 未知错误码以及额外`sql/stack/connection_string/api_key`字段被拒绝；合法API错误只序列化`status/error/trace_id`；
10. Evidence只接受database和两个M1合成来源；查询摘要夹带SQL或`synthetic_data=false`被拒绝；
11. 空聊天问题和聊天请求额外SQL字段被拒绝；合法聊天响应包含thread、message、answer、Evidence摘要和execution trace；
12. 逐一检查公开Schema生成的JSON Schema，`additionalProperties=false`全部成立；通用泛型`ToolEnvelope[InventoryResult]`也能成功生成JSON Schema；
13. Schema专项测试17项通过，全量`pytest -q`共53项通过；Ruff检查通过且40个Python文件格式正确；Mypy检查23个`app/scripts`文件无类型问题；编译和`pip check`通过；
14. PostgreSQL容器保持`healthy`；全量迁移测试结束后已重新运行M1-07 Seed恢复演示数据；
15. 未执行Repository、Service、Tool、Agent、API或前端测试；未提交或推送Git。

**能够证明**

- 后续各层已经有统一、可序列化且默认拒绝未知字段的M1数据合同；
- 模型控制的意图和Tool输入没有SQL、tenant、Session或数据库连接入口；
- 非法SKU、非法市场、市场与仓库不一致、缺字段和额外字段能在进入业务层前被拒绝；
- 成功/失败Tool外壳、库存公式、时区和合成数据标记具有程序化约束；
- 认证和Evidence对外结构没有密码哈希、连接串、原始SQL或堆栈字段；
- 后续可以从同一Pydantic定义生成OpenAPI和前端类型，而不需要重新猜字段。

**不能证明**

- Repository已经按tenant、SKU、市场和最新时间安全查询PostgreSQL；
- Schema通过的数据一定在数据库中存在；
- 125已经由业务Service从数据库事实正式计算；
- PermissionGuard会阻止FR运营查询德国仓；
- 后续Service构造的错误消息一定完成语义脱敏；
- 千问一定输出合法意图，或Provider不会尝试绕过Schema；
- FastAPI状态码、JWT、Agent Tool、LangGraph、Evidence持久化和前端已经实现。

**常见问题与优先排查方向**

- 请求多传字段却报错：先对照对应Schema；M1故意不静默忽略未知字段；
- SKU看起来正常但被拒绝：检查是否包含小写、下划线、空格或非ASCII符号；
- 仓库被拒绝：同时核对两位市场和仓库前缀，例如`DE + DE-FRA`；
- 时间被拒绝：确保字符串包含`Z`或`+02:00`等时区；
- ToolEnvelope报自相矛盾：根据status检查data、error和evidence_ids组合；
- Evidence联合类型报错很多：先检查`query_summary`和`structured_data`是否属于同一种商品或库存形状；
- 前端字段未来发生变化：先修改并评审Pydantic合同和测试，再同步API与前端类型，不能由某一层私自改名；
- 错误结构没有敏感字段但message仍可能泄密：问题应在后续异常映射和脱敏层修复，不能误以为`extra=forbid`能理解所有文本语义。

**下一步**

停止开发并等待用户理解和确认本步结果；用户明确回复“确认M1-08，可以进入M1-09”后，才进入M1-09“实现受控商品和库存Repository”。

### 2026-08-28｜M1-09｜实现受控商品和库存Repository

**状态：已完成**

**本步解决的问题**

M1-08只能判断查询参数格式是否合法，还没有代码真正读取PostgreSQL。旧项目把模型生成的SQL直接交给数据库，不具备租户、市场、固定字段和超时边界。本步建立新的商品和库存Repository，只执行开发者预先写好的SQLAlchemy SELECT，并在每次查询中强制带租户等受控条件。

**输入、输出和上下游**

- 输入：M1-08已验证的商品词、SKU、DE/FR市场、可选仓库，后端RunContext未来提供的`tenant_id`，以及请求级SQLAlchemy Session；
- 输出：冻结的`ProductCandidate`、`ProductSpecRecord`和`InventoryRecord`只读记录列表；
- 上游：M1-03 Session、M1-05 ORM模型、M1-08 Schema；
- 下游：M1-10商品规格Service和M1-11库存/Evidence Service；
- Repository不接收自然语言Prompt、模型对象、SQL字符串、用户密码或Token。

**用大白话解释运行过程**

Repository是数据库的“固定取货窗口”。前面的Schema把申请单格式检查好，Repository再把后端可信租户和申请条件放入提前写好的查询模板。数据库驱动负责把参数与SQL结构分开传输，所以商品词和SKU不会变成SQL代码。

```text
已校验的商品词/SKU/市场 + 后端tenant_id
→ 设置本事务的数据库查询超时
→ 执行固定SQLAlchemy SELECT
→ PostgreSQL按tenant/SKU/market/warehouse/time过滤
→ 转成冻结只读记录
→ 交给后续Service判断未找到、歧义和业务结果
```

商品解析先尝试租户内精确SKU；精确命中后立即返回，避免某个SKU文本同时被当成别名。没有精确SKU时，再匹配中文全名、大小写不敏感的英文全名和受控别名。命中多个候选时完整返回，下一步Service负责生成`AMBIGUOUS_PRODUCT`，Repository不擅自选择。

库存查询按租户、SKU、市场和可选仓库过滤。数据库子查询先找出每个SKU/仓库的最大`snapshot_at`，主查询只取与最大时间相同的快照，因此不会误把旧库存当成当前库存。

**技术决定与边界**

- 禁止通用SQL入口；Repository公开方法不存在`sql`参数，只能调用预写SELECT；
- 所有业务查询同时过滤`InventorySnapshot`、SKU、商品和仓库的`tenant_id`，不是只依赖一个外键条件；
- 商品查询在精确SKU和名称/别名两个分支中都带租户条件；规格查询同时带租户和variant；
- 库存查询只读取`active`仓库，每个匹配仓库返回最新一条快照；市场内多个仓库会返回多条最新记录，后续Service必须明确处理，不能随便相加或挑选；
- SQLAlchemy使用绑定参数；集成测试监听实际发送给驱动的SQL，确认SKU和tenant UUID不出现在SQL文本中而存在于参数对象；
- 使用PostgreSQL`set_config('statement_timeout', ..., true)`设置事务级超时，参数同样绑定；事务提交或回滚后自动恢复，不污染连接池中的下一次请求；
- 应用默认超时为2000毫秒，集中配置允许50至30000毫秒；Repository底层测试允许1至30000毫秒以便快速注入超时；
- Repository返回dataclass只读快照，不返回ORM实体，避免上层无意触发懒加载或修改数据库对象；
- `InventoryRecord`只包含`on_hand/reserved/unsellable/inbound/safety_stock`原始事实，没有`available`；M1-11 Service负责正式计算；
- 本步不映射`OperationalError`为`DATABASE_TIMEOUT`，只验证PostgreSQL会真实取消超时SQL；公开错误映射留给Service/API；
- 当前M1演示数据规模很小，现有租户/SKU/仓库/快照唯一索引和仓库市场索引足够；本步没有为名称/别名额外建立GIN或全文索引，也没有新增Alembic迁移；
- 本步没有实现业务Service、Evidence、登录、PermissionGuard、Tool、Trace、LangGraph、API或前端。

**修改文件与职责**

- `app/repositories/common.py`：通过参数化`set_config`设置事务级statement timeout并限制配置范围；
- `app/repositories/product.py`：固定的租户内SKU/名称/别名候选查询和规格查询，返回冻结只读记录；
- `app/repositories/inventory.py`：固定的租户/SKU/市场/仓库过滤和每仓最新库存查询；
- `app/repositories/__init__.py`：集中暴露Repository及记录类型；
- `app/core/config.py`：新增`database_statement_timeout_ms`集中配置，默认2000毫秒；
- `.env.example`：增加`DATABASE_STATEMENT_TIMEOUT_MS=2000`示例；
- `tests/unit/test_app_baseline.py`：隔离并验证新增环境变量默认值；
- `tests/integration/test_repositories.py`：在真实PostgreSQL事务中验证商品、库存、隔离、参数绑定和超时，测试结束全部回滚；
- `README.md`：说明Repository职责、固定查询、双重权限边界和暂未计算available；
- `docs/progress/M1/M1_INVENTORY_QUERY.md`、`docs/PROJECT_PROGRESS.md`：记录本步实际结果和M1-10前停止点。

**调用链位置**

```text
前端（未经过）
→ API（未经过）
→ Schema（沿用M1-08合同；本步测试直接提供合法参数）
→ Service（未经过；M1-10/M1-11才实现）
→ Repository（本步：固定参数化只读查询）
→ Model（本步：使用Product/Variant/Spec/Warehouse/InventorySnapshot ORM字段）
→ PostgreSQL（本步：真实SELECT、最新时间聚合和statement timeout）
```

**验证方法与实际结果**

1. 同一租户内精确`LR-TL-MUSH-OR01`只返回对应SKU，不进入宽泛别名结果；
2. 中文全名和不同大小写的英文全名都返回正确SKU；受控别名“蘑菇灯”命中两个测试商品时按SKU稳定返回两个候选，证明Repository不隐藏歧义；
3. 两个租户拥有相同SKU时，各自查询只返回自己租户的商品；不存在SKU返回空列表；
4. 当前租户可读取自己variant的30cm规格，用另一个租户查询该variant返回空列表；
5. DE市场有DE-BER与DE-FRA两个仓库，DE-FRA存在旧/新两条快照；无仓库过滤时只返回DE-BER 40和DE-FRA最新150，不返回DE-FRA旧100；
6. 指定DE-FRA只返回150；FR只返回FR-CDG 70；把DE-FRA与FR市场组合或查询不存在SKU均返回空列表；
7. 另一个租户同样拥有`LR-TL-MUSH-OR01 + DE-FRA`且库存999，当前租户仍得到150，另一个租户得到999，证明同键跨租户隔离；
8. 监听实际数据库驱动调用，两个业务SELECT的SQL文本均不包含`LR-TL-MUSH-OR01`或tenant UUID，参数对象非空，证明不是字符串插值SQL；
9. 在独立真实事务中设置10毫秒statement timeout，`current_setting`返回`10ms`；执行50毫秒`pg_sleep`被PostgreSQL以`OperationalError`取消，回滚后不残留事务状态；
10. 0和30001毫秒配置被Repository公共护栏拒绝；
11. Repository专项集成测试8项通过；全量`pytest -q`共61项通过；Ruff检查通过且45个Python文件格式正确；Mypy检查27个`app/scripts`文件无类型问题；编译和`pip check`通过；
12. 全量测试后重新运行M1-07 Seed，使用真实Seed执行新Repository：“蘑菇灯”得到1个`LR-TL-MUSH-OR01`候选，`DE + DE-FRA`得到1条150/20/5快照；`InventoryRecord`确认没有`available`字段；
13. PostgreSQL 17.11容器保持`healthy`，数据库迁移仍为`20260828_0003 (head)`，本步没有结构变更；
14. 测试数据均在事务中回滚；最终数据库保持4个演示用户、1个SKU、2条Seed库存快照和0条Agent运行；
15. 未执行Service、PermissionGuard、Tool、Evidence、Agent、API或前端测试；未提交或推送Git。

**能够证明**

- 商品和库存数据库访问使用固定、参数化且带超时的SQLAlchemy SELECT，不接受模型SQL；
- 精确SKU、中文/英文名、受控别名、歧义候选和规格查询具有确定行为；
- 商品、规格和库存查询在相同SKU/仓库键跨租户时仍保持数据隔离；
- 市场和仓库过滤有效，每个仓库只返回时间最新的库存快照；
- PostgreSQL statement timeout在真实数据库中有效且属于当前事务；
- Repository只返回原始数据库事实，没有提前计算available或生成Evidence。

**不能证明**

- 商品未找到或歧义会被映射为正确的`PRODUCT_NOT_FOUND/AMBIGUOUS_PRODUCT`，这是M1-10职责；
- 150/20/5会被Service正式计算成125并通过Schema返回；
- 数据库超时会被映射为安全的`DATABASE_TIMEOUT`和HTTP 504；
- FR运营查询DE会被拒绝；Repository只接受tenant/market条件，不知道当前用户角色；
- 多个德国仓库的结果应该合并、报歧义还是要求指定仓库，业务规则仍由Service明确；
- Evidence、Trace、Tool审计会被创建；
- 模型会提供正确商品词和市场，或Agent会选择正确Tool；
- API和前端已经连接Repository。

**常见问题与优先排查方向**

- 商品查不到：先确认tenant是否正确，再按“精确SKU→全名→受控别名”顺序检查；
- “蘑菇灯”返回多个候选：这是预期的歧义保护，下一步Service应要求更精确SKU，不要在Repository里取第一条；
- 库存拿到旧数据：检查最大`snapshot_at`子查询是否同时按tenant、variant、warehouse分组；
- 查到其他租户：逐项检查主查询和子查询的tenant条件，不能只依靠SKU唯一；
- DE查不到DE-FRA：同时核对warehouse状态是否为active、market_code是否为DE、tenant是否一致；
- 查询突然超时：区分连接超时和statement timeout，先记录具体Repository方法、参数摘要和数据库慢查询计划；
- 超时后Session继续报错：PostgreSQL取消语句后当前事务必须回滚，再归还连接；
- 参数化测试失败：检查是否新增了f-string、字符串拼接或`text()`业务查询；固定`set_config`和测试用`pg_sleep`不属于业务数据查询；
- 数据量增大后别名查询变慢：先通过查询计划确认瓶颈，再在未来迁移中评估规范化别名表或GIN索引，不在M1小数据阶段预建复杂索引；
- 上层找不到available：这是有意边界，M1-11 Service才计算，不能把业务公式塞进Repository。

**下一步**

停止开发并等待用户理解和确认本步结果；用户明确回复“确认M1-09，可以进入M1-10”后，才进入M1-10“实现商品规格Service”。

### 2026-08-28｜M1-10｜实现商品规格Service

**状态：已完成**

**本步解决的问题**

M1-09的ProductRepository能返回0个、1个或多个商品候选，但不会判断这些情况在业务上代表什么，也不会把规格组装成M1-08的公开Schema。本步建立`ProductSpecService`，把Repository事实转换成唯一商品规格结果或明确、安全的业务错误。

**输入、输出和上下游**

- 输入：后端未来从RunContext取得的可信`tenant_id`，以及已通过M1-08校验的`GetProductSpecInput.product_query`；
- 输出：唯一的`ProductSpecResult`，或者`PRODUCT_NOT_FOUND`、`AMBIGUOUS_PRODUCT`、`INTERNAL_ERROR`等`ApplicationError`；
- 上游：M1-08商品Schema和M1-09 ProductRepository；
- 下游：M1-15 `get_product_spec` Agent Tool和M1-17 LangGraph商品解析节点；
- 本步不接收模型对象、Prompt、SQL、数据库Session、用户角色或市场权限。

**用大白话解释运行过程**

Repository像数据库取货员，Service像业务主管。取货员只说“找到了几件候选商品”，主管再按规则处理：

```text
GetProductSpecInput + tenant_id
→ ProductRepository查候选
├─ 0个：PRODUCT_NOT_FOUND
├─ 多个：AMBIGUOUS_PRODUCT，要求更精确的名称或SKU
└─ 1个：继续读取该tenant下的variant规格
   ├─ 无规格：PRODUCT_NOT_FOUND，明确说明规格不可用
   ├─ 非M1演示数据或内部字段非法：INTERNAL_ERROR
   └─ 合法：组装并再次通过ProductSpecResult校验
```

Service不取“第一条”掩盖歧义，也不在缺少规格时编造内容。所有成功结果最终再次经过Pydantic输出Schema；Repository或数据库出现不符合合同的状态/核验值时，Pydantic异常会被转换为安全的`INTERNAL_ERROR`，不会把内部堆栈直接交给未来API。

**技术决定与边界**

- `ProductReader` Protocol只允许Service调用`find_candidates`和`list_specs`两个只读方法，便于单元测试使用Fake，也限制Service依赖面；
- Service接收`GetProductSpecInput`对象而不是任意字典，正式链路必须先完成Pydantic检查；
- tenant仍是单独的后端参数，模型和前端控制的商品输入没有tenant字段；
- 0候选使用`PRODUCT_NOT_FOUND`；多候选使用`AMBIGUOUS_PRODUCT`；候选SKU只保存在异常内部供Trace/调试，公共`ErrorDetail`不扩展任意详情字段；
- 商品存在但规格为空时沿用M1既定错误码`PRODUCT_NOT_FOUND`，但使用“已找到商品，但没有可用的商品规格”区分原因；M1不为单个场景扩展`SPEC_NOT_FOUND`错误码；
- 输出状态采用SKU variant状态，因为本次解析结果面向具体可售SKU；M1 Seed中product和variant均为`candidate`；
- M1强制合成演示边界，Repository候选若不是demo数据则返回安全`INTERNAL_ERROR`，不把它伪装成M1结果；
- Repository返回非法状态、核验值、超出Schema规格数量等情况时，Service捕获输出校验错误并转换为`InternalDataContractError`；
- `ApplicationError.to_detail()`统一转换为M1-08的严格`ErrorDetail`，为未来Tool/API适配保留单一错误出口；
- 本步没有捕获或映射数据库超时；M1-11统一处理库存和Evidence相关数据库错误，未来可抽取共用映射；
- 原计划预计在M1-10建立`app/services/evidence.py`商品部分，实际复核后延后：Evidence表必须绑定真实`agent_run_id + tool_call_id`，这些ID要等Harness/Tool执行步骤产生；现在持久化会制造假的审计关系；
- 本步不创建Evidence、不修改Repository、ORM或迁移，也不实现库存计算、登录、PermissionGuard、Tool、Trace、LangGraph、API或前端。

**修改文件与职责**

- `app/core/errors.py`：定义可安全公开的`ApplicationError`及商品未找到、歧义、内部数据合同错误，并转换为`ErrorDetail`；
- `app/services/product.py`：定义最小`ProductReader`接口和商品唯一解析、规格组装、错误映射规则；
- `app/services/__init__.py`：集中导出商品Service接口；
- `tests/unit/test_product_service.py`：使用Fake Repository验证0/1/多候选、无规格、非演示数据和非法内部字段；
- `tests/integration/test_product_service.py`：使用真实PostgreSQL和ProductRepository验证SKU、中文别名、英文名、未找到、歧义及跨租户；
- `README.md`：解释Service业务职责、实际Seed结果和Evidence延后原因；
- `docs/progress/M1/M1_INVENTORY_QUERY.md`、`docs/PROJECT_PROGRESS.md`：记录本步实际结果、计划调整和M1-11前停止点。

**调用链位置**

```text
前端（未经过）
→ API（未经过）
→ Schema（本步输入GetProductSpecInput、输出ProductSpecResult/ErrorDetail）
→ Service（本步：唯一解析、规格组装和业务错误）
→ Repository（沿用M1-09固定查询）
→ Model（沿用现有ORM）
→ PostgreSQL（真实只读商品/规格SELECT）
```

本步不经过LLM。未来模型只能先产生受Schema约束的商品词，再经Tool调用本Service。

**验证方法与实际结果**

1. 单元测试Fake Repository返回一个候选和一条30cm规格，Service生成严格SKU、candidate状态、规格和`synthetic_data=true`结果，并按相同tenant依次调用候选/规格查询；
2. 0候选转换为`PRODUCT_NOT_FOUND`，公共错误包含固定安全消息、`retryable=false`和`field=product_query`；
3. 两个候选转换为`AMBIGUOUS_PRODUCT`，内部候选SKU按稳定顺序保存，且确认发生歧义后不再调用规格查询；
4. 唯一商品没有规格时返回`PRODUCT_NOT_FOUND`和“规格不可用”消息，不返回空成功结果；
5. 非合成候选被M1边界拒绝为`INTERNAL_ERROR`；Repository返回非法核验状态时，Pydantic内部错误被转换为安全`INTERNAL_ERROR`；
6. 真实PostgreSQL集成测试中，精确SKU、中文别名“橙色蘑菇灯”和不同大小写英文全名均解析到`LR-TL-MUSH-OR01`及30cm规格；
7. 真实数据库中不存在商品返回未找到；宽泛别名“台灯”同时命中两个SKU时返回歧义且候选稳定；
8. 另一个租户专属SKU从当前tenant查询返回未找到，从所属tenant查询成功，证明Service没有绕过Repository租户隔离；
9. 本步专项测试7项通过；全量`pytest -q`共68项通过；Ruff检查通过且50个Python文件格式正确；Mypy检查30个`app/scripts`文件无类型问题；编译和`pip check`通过；
10. 全量迁移测试后重新执行M1-07 Seed，使用真实Seed运行`Schema→Service→Repository→ORM→PostgreSQL`：输入“蘑菇灯”得到`LR-TL-MUSH-OR01`、candidate和color/diameter/height/voltage四条规格，合成标记为true；
11. PostgreSQL 17.11容器保持`healthy`，数据库迁移仍为`20260828_0003 (head)`；最终保留4个演示用户、1个SKU、2条库存快照和0条Agent运行；
12. 未创建Evidence/ToolCall/AgentRun，未执行库存、权限、Agent、API或前端测试；未提交或推送Git。

**能够证明**

- 合法商品词可以在可信tenant范围内安全解析为唯一SKU和严格规格结果；
- SKU精确匹配、中文别名、英文全名、未找到、歧义和跨租户具有明确且可重复的业务行为；
- Service不会在多候选时擅自选第一条，也不会在规格缺失时伪造成功；
- Repository内部数据必须再次通过公开输出Schema，非法数据不会直接进入Tool/API；
- 商品业务错误可以统一转换为M1公开`ErrorDetail`；
- 当前真实Seed的“蘑菇灯”商品规格后端链已经接通到PostgreSQL。

**不能证明**

- “德国仓蘑菇灯还有多少库存”已经完成；本步只解析商品规格，不查询库存；
- 150/20/5已经由库存Service计算成125；
- Evidence已经生成并与真实ToolCall/AgentRun关联；
- 数据库超时已经映射为`DATABASE_TIMEOUT`；
- 当前用户角色和市场权限已经检查；
- AI能够稳定输出“蘑菇灯”，或Agent Tool会调用本Service；
- FastAPI和前端已经能访问商品Service。

**常见问题与优先排查方向**

- 商品一直未找到：依次检查GetProductSpecInput是否通过、tenant是否正确、Repository精确SKU/全名/别名是否有记录；
- 明明有商品却提示歧义：查看内部候选SKU，确认别名是否过宽；不要通过取第一条绕过；
- 商品存在但规格不可用：检查`product_specs`是否使用相同tenant和variant_id，以及是否确实有至少一条规格；
- 返回INTERNAL_ERROR：优先检查product/variant状态、`is_demo`、规格核验状态、字段长度和规格条数是否符合M1 Schema；
- 跨租户商品被找到：检查Service是否传入RunContext中的tenant，以及是否绕开ProductRepository；
- 单元测试通过但数据库失败：Fake只证明业务分支，继续检查真实Repository、迁移版本和PostgreSQL；
- 想立刻创建Evidence：必须先具备真实AgentRun和ToolCall上下文，不能伪造外键让审计链看似完整；
- 想让AI调用Service：要等ToolRegistry、PermissionGuard、Tool和LangGraph步骤，当前直接暴露会绕过运行时护栏。

**下一步**

停止开发并等待用户理解和确认本步结果；用户明确回复“确认M1-10，可以进入M1-11”后，才进入M1-11“实现库存查询与数据库Evidence Service”。

### 2026-08-28｜M1-11｜实现库存查询与数据库Evidence Service

**状态：已完成**

**本步解决的问题**

M1-09的`InventoryRepository`只能返回最新库存原始事实，还不会把150件期末库存、20件预留和5件不可售正式计算成125件可售，也不会生成支撑回答的数据库Evidence。本步建立`InventoryService`和`EvidenceService`，让一条合法库存查询得到严格业务结果，并确保Evidence写入数据库事务后才允许返回成功。

**输入、输出和上下游**

- 输入：后端可信的`tenant_id`、`agent_run_id`、`tool_call_id`，以及已经通过M1-08校验的`SearchInventoryInput`；
- 输出：包含`InventoryResult`与`EvidenceDetail`的`InventoryServiceResult`，或者安全的`ApplicationError`；
- 上游：M1-08库存/Evidence Schema、M1-09 `InventoryRepository`、M1-06运行与Evidence外键结构；
- 下游：M1-15 `search_inventory` Agent Tool、M1-17 LangGraph和最终聊天回答；
- 本步不接收自然语言Prompt、模型对象、SQL、Token、用户角色或可自行修改的tenant。

**用大白话解释运行过程**

Repository像“按固定取货单去仓库拿数据的人”，库存Service像“负责算账和判断异常的业务主管”，Evidence Service像“把本次答案依据装订进档案的人”：

```text
可信运行标识 + 已校验库存条件
→ InventoryRepository读取该tenant、SKU、市场和仓库的最新快照
├─ 0条：INVENTORY_NOT_FOUND，不写Evidence
├─ 多条：要求补充warehouse_code，不猜仓库、不相加
└─ 1条：计算available = on_hand - reserved - unsellable
   → InventoryResult再次检查非负数、公式、时间和合成数据标记
   → EvidenceService关联AgentRun与ToolCall并flush Evidence
   ├─ Evidence失败：整次结果失败，交给请求事务回滚
   └─ Evidence成功：才把库存结果和Evidence返回上层
```

这里的`flush`是“把本次写入先送到PostgreSQL执行并检查外键”，不是单独永久保存。未来API请求最外层事务负责最终`commit`（提交，即永久保存）；任何后续步骤失败则`rollback`（回滚，即撤销整次请求产生的数据），避免出现“回答成功但证据没保存”或“证据存在但回答失败”的半成品。

**技术决定与边界**

- `InventoryReader`与`InventoryEvidenceWriter` Protocol只暴露本Service需要的两个操作，便于Fake单元测试，也防止业务层拿到任意数据库能力；
- `available`不写回库存表，只在Service中由最新快照的三个原始字段统一计算；结果还必须再次通过`InventoryResult`校验；
- 查询无记录返回`INVENTORY_NOT_FOUND`；库存数量为0是合法事实，仍返回成功和Evidence，不能误报“没找到”；
- 不指定仓库且同一市场命中多个仓时返回`VALIDATION_ERROR`并要求`warehouse_code`，M1不擅自求和或选第一条；
- Repository返回非合成数据、负库存、可售计算为负、非法市场/仓库或无时区时间时，统一转换为安全`INTERNAL_ERROR`，不把不可信内部数据交给上层；
- PostgreSQL语句取消的SQLSTATE `57014`映射为可重试的`DATABASE_TIMEOUT`；其他SQLAlchemy/驱动错误映射为安全`INTERNAL_ERROR`，公开错误中不包含SQL、密码、驱动消息或堆栈；
- Evidence确定性地来自已校验库存结果，不让模型编写。记录包含库存快照ID、查询摘要、库存结构、数据时间、可信度、实际访问的tenant和市场，以及`synthetic_data=true`；
- Evidence必须通过数据库复合外键关联同tenant的AgentRun和ToolCall。标识不匹配时返回安全的证据保存错误；外层调用者必须回滚已失败事务；
- 本步只实现库存Evidence。商品规格Evidence继续等待真实`get_product_spec` Tool上下文，不伪造商品审计记录；
- 本步没有实现登录/JWT、正式RunContext、PermissionGuard、ExecutionBudget、Trace写入器、ToolRegistry、Agent Tool、千问/Mock Provider、LangGraph、聊天API或前端；因此当前Service只能由可信后端测试代码调用，不能直接开放给用户。

**修改文件与职责**

- `app/core/errors.py`：新增库存未找到、多仓需明确、数据库超时/失败、库存合同错误和Evidence保存错误的安全异常；
- `app/services/inventory.py`：读取最新库存、处理0/1/多记录、计算可售、校验结果、映射数据库异常，并编排Evidence先写后返回；
- `app/services/evidence.py`：构造库存数据库Evidence、绑定运行/Tool外键并执行`flush`；
- `app/services/__init__.py`：集中导出库存与Evidence Service接口；
- `tests/unit/test_inventory_service.py`：使用Fake验证公式、零库存、无记录、多仓、非法数据、超时与错误脱敏；
- `tests/integration/test_inventory_evidence_service.py`：使用真实PostgreSQL事务验证最新快照、Evidence字段和外键、缺失库存不写证据及错误外键安全失败；
- `README.md`：同步M1-11可运行范围、库存Service流程、事务和未实现边界；
- `docs/progress/M1/M1_INVENTORY_QUERY.md`、`docs/PROJECT_PROGRESS.md`：记录实际实现、验证结果和M1-12前停止点。

**调用链位置**

```text
前端（未经过）
→ API（未经过）
→ Schema（沿用M1-08 SearchInventoryInput / InventoryResult / EvidenceDetail）
→ Service（本步：业务判断、可售计算、错误映射、Evidence编排）
→ Repository（沿用M1-09固定参数化查询）
→ Model（沿用库存、AgentRun、ToolCall、Evidence ORM）
→ PostgreSQL（真实读取最新快照并在事务内写入Evidence）
```

本步不经过LLM。未来千问只能提供受Schema约束的意图和参数，再由Agent Tool调用本Service；千问不会得到Repository、Session、ORM、SQL或数据库连接。

**验证方法与实际结果**

1. Fake Repository返回150/20/5，Service正式得到`available=125`；只有Evidence Writer成功返回后才产生`InventoryServiceResult`；
2. 0/0/0返回合法`available=0`并生成Evidence，证明“零库存”没有被误判为“无记录”；
3. 0条记录返回`INVENTORY_NOT_FOUND`且Evidence零调用；同一市场两仓返回要求指定`warehouse_code`的安全校验错误且不写Evidence；
4. `on_hand=10/reserved=9/unsellable=2`造成负可售，以及`synthetic_data=false`，均转换为安全库存合同错误且不写Evidence；
5. 模拟SQLSTATE `57014`得到`DATABASE_TIMEOUT/retryable=true`；其他数据库异常返回安全错误，断言公开JSON不包含SQL文本、密码或驱动详情；
6. 真实PostgreSQL集成测试创建事务内AgentRun和ToolCall，旧/新两条快照中只采用最新150/20/5，得到125，并实际读取到已经`flush`的Evidence；
7. Evidence实际绑定正确`agent_run_id`和`tool_call_id`，定位到最新`inventory_snapshots/{id}`，查询摘要为SKU/DE/DE-FRA，结构化库存为125，访问范围只记录该tenant与实际DE市场；
8. 真实PostgreSQL查询FR缺失库存不新增Evidence；故意错配AgentRun外键时数据库拒绝并被转换为安全`EvidencePersistenceError`；集成测试使用外层事务或savepoint回滚，没有留下测试数据；
9. 本步专项10项测试通过；全量`pytest -q`共78项通过；Ruff检查通过且54个Python文件格式正确；Mypy检查32个`app/scripts`文件无类型问题；编译、`pip check`均通过；
10. PostgreSQL 17.11容器为`healthy`；Alembic处于`20260828_0003 (head)`，`alembic check`确认ORM与迁移没有待生成差异；
11. 全量测试后重新执行确定性Seed，manifest仍给出`LR-TL-MUSH-OR01 + DE-FRA = 125`；使用真实Seed、临时AgentRun/ToolCall运行完整后端链，得到`available=125`、`evidence_flushed=true`和`source=synthetic_inventory`；随后事务整体回滚；
12. 最终数据库保留4个用户、1个商品、2条库存快照，且threads、agent_runs、tool_calls、evidences均为0，证明临时验证没有伪造永久运行审计；
13. 辅助验证中曾使用错误的`psql`用户名和错误的说明性租户名，均在进入业务断言前失败且没有写入；改为读取项目配置和真实Seed标识后验证通过。该过程不改变上述通过结论；
14. 未执行登录、角色权限、Agent Tool、LangGraph、聊天API或前端测试；未提交或推送Git。

**能够证明**

- 当前后端能从真实PostgreSQL最新库存快照稳定计算出德国仓可售125，并返回严格库存结果；
- 无记录、零库存、多仓、非法内部数据、数据库语句超时和普通数据库错误具有明确且安全的业务行为；
- 库存成功结果必带一条已经通过PostgreSQL外键检查的数据库Evidence，Evidence能够定位到具体库存快照并带数据时间、访问范围和合成数据标记；
- Evidence失败时Service不会返回库存成功结果，测试事务能够完整回滚；
- 模型无需也不能生成SQL，本步所有数据库读取仍经过固定Repository。

**不能证明**

- 用户已经可以登录，或`tenant_id/agent_run_id/tool_call_id`已经由正式RunContext自动产生；本步验证使用事务内可信测试上下文；
- FR运营查询DE会被PermissionGuard拒绝；当前Repository只执行传入的tenant/market过滤，不知道用户角色；
- Agent能够选择并调用`search_inventory` Tool，ExecutionBudget和Trace已经生效；
- 千问能够把“德国仓蘑菇灯还有多少可售库存”稳定解析为SKU、市场和仓库；
- FastAPI和Next.js已经能取得库存回答、Evidence和执行状态；
- M1库存查询用户闭环已经完成，或运行时代码已经达到生产可用水平。

**常见问题与优先排查方向**

- 返回`INVENTORY_NOT_FOUND`：依次检查输入SKU、tenant、market、warehouse、仓库`active`状态及是否存在快照；不要把0库存当作无记录；
- 提示需要仓库代码：说明当前市场命中多个活动仓，补充明确`warehouse_code`，不要在Service里临时选第一条；
- 返回库存合同错误：检查原始数量是否非负、三项计算是否得到非负可售、时间是否带时区、市场/仓库格式和三张源表的demo标记；
- 返回`DATABASE_TIMEOUT`：检查`DATABASE_STATEMENT_TIMEOUT_MS`、慢查询计划、索引和连接状态；超时后先回滚当前事务再继续使用Session；
- 返回Evidence保存失败：首先核对tenant、AgentRun、ToolCall三者复合外键是否属于同一次运行，再检查事务是否已因更早的数据库错误失效；
- Evidence存在但回答失败：未来API必须让运行、Tool、Evidence和回答共享同一外层事务，禁止中间单独commit；
- Evidence访问范围错误：应记录Repository实际读取的市场，而不是模型最初猜测或用户无关的全部权限范围；
- 单元测试通过但真实数据库失败：Fake只证明业务分支，继续检查容器健康、迁移head、Seed、外键和真实集成测试。

**下一步**

停止开发并等待用户理解和确认本步结果；用户明确回复“确认M1-11，可以进入M1-12”后，才进入M1-12“实现登录、JWT和RunContext”。
