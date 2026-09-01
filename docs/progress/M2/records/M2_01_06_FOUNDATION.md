# M2-01 至 M2-06：基础设施、Storage、数据模型与文件 API

> 本文件保存从迁移前单文件中拆出的完整历史方案、实施日志与验证证据。
> 当前状态和阅读入口见 [M2入口](../M2_KNOWLEDGE_RAG.md)。

## 11. M2-PLAN-01 方案记录

**状态：已完成（阶段仍为待确认）**

**日期**

2026-08-29

**目标**

完整阅读项目规则、设计、M1记录和相关代码；只读核对 Git、环境、数据库、依赖和旧原型；恢复并验证 M1 基线；提交 M2 范围、架构、26个小步骤、验证、完成标准和风险。

**本次修改文件**

- `docs/progress/M2/M2_KNOWLEDGE_RAG.md`：新建本阶段待确认方案与检查记录；
- `docs/PROJECT_PROGRESS.md`：只同步当前阶段、状态、链接和等待确认动作。

本次没有修改 `app/`、`frontend/`、`tests/`、`scripts/`、`migrations/`、`data/`、Compose、依赖或 `.env`。

**调用链位置**

本次只属于设计与项目治理层，没有进入“前端 → API → Schema → Service → Parser/Embedding/Retrieval → Model → PostgreSQL/pgvector → Evidence”运行链。文档描述未来链路不代表能力已经实现。

**验证方法与实际结果**

- 完整读取 AGENTS、总看板、M1详细记录、三份设计、README、前端规则和 M2 相关代码/配置；
- Git 分支、HEAD、本地/远端关系和工作区检查通过；
- 版本、`.env`键存在性、主机资源、PostgreSQL、迁移、Seed 和 pgvector 可用性检查完成；
- 后端175项通过、1项付费冒烟跳过；前端组件4项、TypeScript、ESLint、Build和Chromium E2E 4项通过；
- 测试后 PostgreSQL healthy、运行表0、关键库存125、Git工作区干净；
- 未执行真实 Qwen、依赖安装、模型下载、迁移或 M2 业务开发。

**下一步**

停止并等待用户评审。只有用户明确回复“确认M2方案，可以开始M2-01”后，才开始 M2-01；该授权不自动包含 M2-02。

## 12. M2-01 实施记录

### 2026-08-29｜M2-01｜建立 M2 配置、依赖和新旧导入边界

**状态：已完成**

**本步解决的问题**

M1的集中配置还不知道M2文件、模型和检索参数，主依赖也没有声明上传、四类文档解析、pgvector Python类型、中文分词和BGE Provider所需包。旧上传/RAGFlow代码仍保留在仓库中，如果新`app/`误导入，会重新引入绝对路径、导入即连接外部服务和异常泄露风险。本步只建立统一配置、依赖声明和自动导入边界，不实现任何M2业务。

**输入、输出和上下游**

- 输入：已确认的M2方案、现有`Settings`、`.env.example`、M1/旧原型依赖和旧上传/RAGFlow代码；
- 输出：可校验的Storage/上传/模型/检索配置合同、M2直接依赖范围、运行数据忽略规则和边界测试；
- 上游：M1配置与依赖基线；
- 下游：M2-02 pgvector基础设施和M2-03 Storage实现；
- 本步没有读取上传文件、加载模型、执行检索或访问新增数据库结构。

**用大白话解释运行过程**

以后所有M2模块先从同一个`Settings`对象领取参数，不能各自在代码里读取环境变量。当前默认选择Fake Embedding/Fake Reranker、CPU和只使用本地模型缓存，因此导入应用只会检查“说明书是否合法”，不会创建目录、加载PyTorch或下载BGE权重。依赖文件则提前声明后续会直接使用哪些Python包，但本步只用`pip --dry-run`验证能否求解，不把大型机器学习栈安装进当前M1虚拟环境。

**修改文件与职责**

- `app/core/config.py`：集中增加Storage、本地目录、上传允许列表/大小/批量、BGE模型/版本/设备/批量、分块和混合检索参数；拒绝危险根目录、重复/缺失格式、非1024维、未归一化、候选数量矛盾和真实BGE使用漂移`main`版本；
- `.env.example`：公开25个M2非秘密配置键和安全默认值；现有本地`.env`没有被覆盖或输出；
- `.gitignore`：忽略`data/storage/`原文件/解析产物和`data/model-cache/`模型权重；
- `requirements.txt`：声明multipart、PyMuPDF、python-docx、openpyxl、Pandas、文件类型/编码、pgvector、jieba和FlagEmbedding兼容范围；不加入RAGFlow；
- `requirements-dev.txt`：显式声明测试直接使用的`packaging`；
- `tests/unit/test_m2_baseline.py`：验证默认/模板/非法配置、秘密掩码、依赖集合、AST导入隔离和后续模块尚不存在；
- `README.md`：说明M2-01已有能力、配置含义、安全默认值、验证命令和未实现边界；
- `docs/progress/M2/M2_KNOWLEDGE_RAG.md`、`docs/PROJECT_PROGRESS.md`：记录用户确认、本步事实、验证和新停止点。

**调用链位置**

```text
前端（未经过）
→ API（未经过）
→ Schema（只经过Settings配置校验）
→ Service（未经过）
→ Parser / Embedding / Retrieval（未经过）
→ Model（未经过）
→ PostgreSQL / pgvector（未经过）
→ Evidence（未经过）
```

**验证方法与实际结果**

1. M2配置与M1应用基线定向测试23项通过，覆盖`.env.example`实际解析、Fake/CPU/只读缓存默认、四格式允许列表、25 MiB上限、1024维归一化、分块/候选参数、秘密掩码和10类非法组合；
2. AST边界测试扫描全部新`app/*.py`，未发现对旧`agent/api/tools/rawflow/utils`或`ragflow_sdk`的顶层导入；同时断言Storage、Parser、Retrieval和文件API尚未创建；
3. `pip install --dry-run --ignore-installed -r requirements-dev.txt`成功完成Python 3.11/Windows依赖求解，选择`FlagEmbedding 1.4.2`、`pgvector 0.5.0`、`PyMuPDF 1.28.2`等兼容包；命令未安装依赖或模型权重，但pip为求解把部分wheel放入本机缓存；
4. 后端全量确定性回归191项通过、1项真实Qwen付费冒烟按设计跳过；新增M2测试使通过数从M1基线175增加到191；
5. Ruff、Mypy、Python编译和当前虚拟环境`pip check`通过；
6. 全量测试后重新执行`m1-v1` Seed，PostgreSQL恢复为`20260828_0003 (head)`、容器`healthy`，DE-FRA关键库存仍为125；
7. 只读取本地`.env`的键名、不读取或输出值，确认25个M2键尚未手工加入；当前由`Settings`安全默认值承接，正式模板已经写入`.env.example`，本步没有覆盖用户现有`.env`；
8. `data/storage/`和`data/model-cache/`均未被配置导入创建；未安装M2新增包、未切换PostgreSQL镜像、未创建迁移、未下载BGE模型、未调用真实Qwen、未修改前端、未提交或推送Git。

**能够证明**

- M2后续模块已有一份集中、可从环境变量解析且能拒绝矛盾值的配置合同；
- 默认导入路径不会联网、下载模型或触发旧RAGFlow/旧上传运行时；
- 直接依赖在当前Python 3.11/Windows环境能够完成版本求解，且主依赖没有重新引入RAGFlow；
- M1后端基线、迁移和125答案没有因配置扩展退化；
- 运行时文件、解析产物和模型缓存具有明确Git忽略边界。

**不能证明**

- 新增M2依赖已经安装或每个包可以真实导入；当前只完成隔离求解，真实安装按需要的后续步骤进行；
- 当前PostgreSQL尚未提供`vector`扩展；镜像仍是M1的`postgres:17.11-alpine3.24`，M2-02才处理；
- Storage能安全读写、文件能上传/解析/分块，或BGE能产生向量和重排；这些模块尚不存在；
- `main`是可用于真实模型运行的固定revision；配置只允许Fake默认使用它，真实BGE后端必须在M2-14/M2-17填写固定revision；
- 前端、API、Model、pgvector和Evidence链路已经增加M2能力。

**常见问题与优先排查方向**

- `.env`新增字段拼写错误或JSON数组格式错误：先用`Settings()`或定向测试检查，不要到上传API阶段才排查；
- 本地`.env`暂时没有M2键：当前安全默认值足以导入和运行M1；进入需要真实目录或真实BGE的步骤时只补对应键，不覆盖现有密码与API Key；
- 真实BGE配置被拒绝：必须提供固定模型revision，不能继续使用会漂移的`main`；
- 依赖安装很慢或磁盘增长：优先确认FlagEmbedding带来的PyTorch/Transformers/数据集传递依赖，按M2-14/M2-17分别安装与基准，不要把模型权重提交Git；
- 应用导入时要求RAGFlow Key：检查新`app/`是否误导入旧`tools/ragflow_tools.py`或`rawflow/`；
- Storage目录配置被拒绝：不要指向`.`或磁盘根目录，原文件目录和模型缓存目录也必须分开；
- M1测试失败：先检查新增Settings校验是否改变M1默认值，再检查开发Shell中的M2环境变量污染。

**下一步**

停止并等待用户理解和确认。只有用户明确确认M2-01并授权M2-02后，才为PostgreSQL 17增加pgvector基础设施；本次授权不包含M2-02。

## 13. M2-02 实施记录

### 2026-08-29｜M2-02｜为 PostgreSQL 17 增加 pgvector 基础设施

**状态：已完成**

**本步解决的问题**

M2-01只声明了Python `pgvector`依赖和1024维Embedding合同，当时运行的`postgres:17.11-alpine3.24`镜像没有`vector`扩展，PostgreSQL无法创建或计算向量类型。本步保留PostgreSQL 17.11、现有命名卷和M1数据，建立固定来源的pgvector 0.8.6运行镜像，只启用扩展，不创建M2业务表、向量列或索引。

**输入、输出和上下游**

- 输入：现有`docker-compose.yml`、`postgres:17.11-alpine3.24`基线、`deep-search-postgres-data`命名卷、Alembic `0003 head`与M1合成Seed；
- 输出：可重现构建的PostgreSQL 17.11 + pgvector 0.8.6镜像、全新卷自动启用SQL、现有库中的`vector`0.8.6扩展和基础设施回归测试；
- 上游：M1 PostgreSQL容器与M2-01配置/依赖合同；
- 下游：M2-03 LocalStorage与M2-04文档元数据模型；真正的向量表和索引仍属于后续步骤。

**用大白话解释运行过程**

PostgreSQL像一个已经存着M1货物的仓库，pgvector像一套“会保存和比较向量”的新设备。本步不搬走旧货物，而是用相同PostgreSQL小版本加装设备，再让原容器用同一个命名卷启动。全新仓库会通过镜像内的初始化SQL自动安装设备；旧仓库因为不会重跑初始化脚本，所以切换后手工执行一次幂等`CREATE EXTENSION`。扩展和M1数据都保存在命名卷中，普通重启不会丢失。

**方案差异与最小处理**

官方`pgvector/pgvector:0.8.6-pg17-bookworm`固定标签已核对，但Docker Hub镜像大层在当前网络长时间卡住，而且它会把现有Alpine基线切换为Bookworm。根据M2-02“固定兼容镜像或可复现构建”的正式边界，改用仓库内Dockerfile：固定当前PostgreSQL 17.11 Alpine linux/amd64基础镜像摘要、pgvector v0.8.6对应Git提交和Alpine `build-base`0.5-r4；关闭不必要的LLVM位码并使用`OPTFLAGS=""`避免绑定构建CPU。这没有扩大到M2-03或业务数据库设计。

**修改文件与职责**

- `.dockerignore`：白名单化Docker构建上下文，只允许pgvector Dockerfile和初始化SQL，排除本地`.env`、源码、测试与数据目录；
- `docker-compose.yml`：将PostgreSQL服务指向`deep-search-pro/postgres-pgvector:17.11-0.8.6`可重现构建，保留容器名、端口、健康检查和`deep-search-postgres-data`命名卷；
- `docker/postgres/Dockerfile`：固定PostgreSQL基础镜像摘要、pgvector提交与构建依赖，编译安装扩展后删除GCC/Make，并内置初始化SQL；
- `docker/postgres/init/001-enable-vector.sql`：全新PostgreSQL数据卷第一次初始化时只执行`CREATE EXTENSION IF NOT EXISTS vector`；
- `tests/unit/test_m2_pgvector_infrastructure.py`：锁定Compose镜像/命名卷、Dockerfile摘要/提交/构建边界和初始化SQL只启用扩展；
- `tests/integration/test_m2_pgvector_infrastructure.py`：连接真实PostgreSQL，验证主版本17、pgvector 0.8.6、向量距离和M1表保留；
- `README.md`：记录构建、新/旧数据卷启用、版本查询、回退和禁止`down -v`的操作边界；
- `docs/progress/M2/M2_KNOWLEDGE_RAG.md`、`docs/PROJECT_PROGRESS.md`：记录实施事实、验证、风险和新停止点。

**调用链位置**

```text
前端（未经过）
→ API（未经过）
→ Schema（未经过）
→ Service / Parser / Embedding / Retrieval（未经过）
→ Model（未修改）
→ PostgreSQL 17 / pgvector 0.8.6（本步）
→ Evidence（未修改）
```

**验证方法与实际结果**

1. 开始时Docker Desktop未运行，只启动Docker Desktop后恢复Server 29.6.1；旧`postgres:17.11-alpine3.24`容器为healthy，命名卷标签精确属于`deep-search-pro/postgres_data`，Alembic为`0003 head`且Seed答案为125；
2. 构建后镜像报告PostgreSQL 17.11，`vector.control`/`vector.so`存在，最终镜像没有GCC和Make；
3. 切换前生成42,372字节自定义格式逻辑备份，`pg_restore --list`通过；切换使用同一命名卷，新容器healthy，现有库成功执行`CREATE EXTENSION`；
4. 真实查询得到PostgreSQL `17.11`、pgvector `0.8.6`，`[1,2,3]`与`[1,2,4]`的L2距离为1；
5. 普通`docker compose restart postgres`之后是同一容器ID、再次healthy，扩展版本、向量运算、Alembic和125均保留；
6. 使用带专用标签的临时空卷启动新镜像，自动初始化得到pgvector 0.8.6；探针容器和卷已精确删除；
7. 在另一个临时空卷中用旧PostgreSQL 17.11镜像恢复切换前备份，实际得到`20260828_0003`和125；回退探针资源及验证后的临时备份均已删除；
8. M2-02及M2-01/App基线定向29项通过；后端全回归197项通过、1项真实Qwen付费冒烟按设计跳过；
9. Ruff、Mypy 66个源文件、Python编译和`pip check`通过；`alembic check`报告无新升级操作，本步没有创建迁移；
10. 测试后重跑M1 Seed，最终容器healthy、Alembic `20260828_0003 (head)`、pgvector 0.8.6、DE-FRA可售125，且没有临时探针容器/卷/备份残留。

**能够证明**

- 当前linux/amd64 Docker Desktop环境可从固定PostgreSQL摘要和pgvector提交重现构建运行镜像；
- 旧M1命名卷能在相同PostgreSQL主/小版本下无损切换，M1表、迁移版本和125保留；
- 现有库和全新库都能得到pgvector 0.8.6，并实际执行最小向量距离运算；
- 普通重启不会丢扩展或M1数据，切换前逻辑备份可在旧PostgreSQL 17.11镜像中恢复；
- M1后端行为和Alembic ORM模型没有因基础设施变更退化。

**不能证明**

- PostgreSQL已有M2文档、文本块、Embedding列、HNSW/IVFFlat索引或混合检索；本步明确未创建这些对象；
- Python `pgvector`/FlagEmbedding已安装并能写入1024维BGE向量；M2-01仍只完成依赖声明；
- 文件能上传、保存、解析、分块或检索；Storage要到M2-03，其他能力在更后步骤；
- 当前linux/amd64基础镜像摘要可以原样在ARM主机构建，或当前设置等于生产高可用/备份方案；
- 前端、API、Schema、Service、Model或Evidence获得了新业务能力。

**常见问题与优先排查方向**

- `docker compose build` 长时间停在GCC包：这次实测是Alpine镜像源传输慢，优先保留BuildKit任务和缓存，不要改用漂移的`latest`或未验证第三方镜像；
- 容器healthy但查不到`vector`：先判断是全新卷还是已有卷；已有卷不重跑`docker-entrypoint-initdb.d`，需执行README的幂等启用命令；
- 镜像构建报摘要或Alpine包版本不存在：不要盲目改成浮动版本，先核对Dockerfile、官方PostgreSQL镜像和pgvector上游提交，然后以独立步骤升级并重跑备份/回归；
- 切换后M1数据消失：立即检查Compose是否仍挂载精确的`deep-search-postgres-data`，不要执行`docker compose down -v`；
- 退回旧镜像后查询`vector`失败：旧镜像没有扩展运行库，只能在没有依赖对象时先移除扩展，或在旧镜像的空卷中恢复切换前备份；
- M1回归失败：先核对PostgreSQL版本、命名卷、Alembic版本和Seed 125，不要先修改M1业务代码。

**下一步**

停止并等待用户理解和确认。下一步应当是M2-03“实现Storage接口和LocalStorage”；本次对M2-02的授权不包含M2-03。

## 14. M2-03 实施记录

### 2026-08-29｜M2-03｜实现 Storage 接口和 LocalStorage

**状态：已完成**

**本步解决的问题**

M2-01只有Storage根目录配置，尚没有真正管理文件的边界。业务代码如果直接拼接或打开任意路径，容易发生越过托管目录、覆盖同名文件、留下半截文件或把本机路径写进错误信息的问题。本步新增只接受规范对象Key的Storage合同和本地实现，统一完成安全定位、分块写入、大小与SHA-256计算、原子发布、读取、存在检查和幂等物理删除。

**输入、输出和上下游**

- 输入：小写规范对象Key、二进制流和不含控制字符的`content_type`；Key格式固定为`{tenant_uuid}/{category}/{yyyy}/{mm}/{file_uuid}.{ext}`；
- 输出：只包含对象Key、字节数、SHA-256和内容类型的`StoredObject`，或不包含Key、绝对路径和底层异常细节的安全Storage异常；
- 上游：后续File Service；当前没有API调用Storage；
- 下游：本地托管文件系统；不经过Parser、Embedding、Retrieval、Model、PostgreSQL/pgvector或Evidence。

**用大白话解释运行过程**

Storage像一个只认“内部货架编号”的文件保管员。调用方不能说“把文件写到D盘某个位置”，只能给出带租户UUID、年月和文件UUID的对象Key。保管员先检查编号格式和每一级目录都安全，再把上传流分小块写进目标目录里的随机临时文件，同时数大小、算SHA-256。完整写完并刷盘后，它用文件系统的原子操作发布正式对象；同名对象已经存在时明确拒绝覆盖。读取和删除仍重新检查边界，返回值与异常都不暴露本机绝对路径。

**修改文件与职责**

- `app/services/storage/contracts.py`：定义`StoredObject`、Storage安全异常、对象Key和内容类型校验；
- `app/services/storage/base.py`：定义后续Service依赖的`StorageBackend`协议；
- `app/services/storage/local.py`：实现根目录隔离、分块写入、SHA-256、同目录临时文件、原子不覆盖发布、读取、存在检查和幂等删除；
- `app/services/storage/__init__.py`：提供稳定、集中的Storage导入入口；
- `tests/unit/test_local_storage.py`：覆盖正常与空文件、重复Key、非法路径、流失败清理、异常脱敏、目录节点和符号链接边界；
- `tests/unit/test_m2_baseline.py`：把M2-01“Storage尚不存在”的旧停止线更新为M2-03“允许Storage，但仍禁止documents、retrieval和文件API”；
- `app/core/config.py`：仅修正Storage配置注释，明确M2-03使用配置而上传API仍留在M2-06；
- `README.md`、本文件和`docs/PROJECT_PROGRESS.md`：记录使用边界、验证事实和新停止点。

**调用链位置**

```text
前端（未经过）
→ API（未经过）
→ Schema（未经过）
→ Service / Storage（本步只实现Storage边界）
→ Parser / Embedding / Retrieval（未实现）
→ Model（未修改）
→ PostgreSQL / pgvector（未修改）
→ Evidence（未修改）
```

**验证方法与实际结果**

1. Storage聚焦测试最终30项通过；当前Windows缺少创建真实符号链接的权限，因此2项真实符号链接测试按环境跳过，同时2项不依赖该权限的模拟报告测试实际覆盖并通过根目录和Key目录的拒绝分支；
2. 实际在临时目录完成普通文件和空文件写入、打开、存在检查和删除，字节数与SHA-256匹配；重复Key保留第一份内容，没有`.tmp`残留；
3. 空Key、`..`、POSIX/Windows/UNC绝对路径、反斜杠、大写UUID/分类/扩展、非法年月与多重扩展均被拒绝；损坏流不会留下正式文件或临时文件，异常不包含私有流信息、对象Key或Storage根路径；
4. 后端全量确定性回归227项通过、3项跳过：其中1项为真实Qwen付费冒烟，另外2项为上述当前Windows真实符号链接权限限制；未调用真实Qwen；
5. `ruff check app tests scripts`通过；`mypy app scripts tests/unit/test_local_storage.py`对69个源文件通过；Python编译和`pip check`通过；
6. PostgreSQL容器保持healthy，Alembic仍为`20260828_0003 (head)`，`alembic check`报告没有新升级操作；本步未创建模型或迁移；
7. 测试只使用pytest临时目录，默认`data/storage`没有因模块导入或测试而被创建；未下载模型、未修改前端、未提交或推送Git。

**能够证明**

- Service后续可以依赖统一接口而不是直接接收或拼接任意绝对路径；
- 在当前Windows/NTFS环境，合法对象能完整发布和读回，重复Key不会覆盖原对象，流失败不会留下半截正式文件；
- 常见路径穿越、绝对路径、非规范Key、目录节点和代码识别到的符号链接会在文件操作边界被拒绝；
- 返回元数据和公开异常不包含本机Storage根路径或底层私有异常信息；
- M1后端回归、PostgreSQL健康状态和Alembic模型状态没有因本步退化。

**不能证明**

- 当前机器能创建并实测真实Windows符号链接；这2项测试需要开启开发者模式、管理员权限或在支持符号链接的CI/Linux环境再次执行；
- Storage已经支持上传鉴权、MIME魔数识别、文件大小/批量限制、owner/ACL、软删除、文档版本或数据库元数据；这些属于M2-04至M2-06；
- Storage能解析PDF/DOCX/XLSX/CSV、生成文本块或Embedding，或使用pgvector检索；这些属于后续独立步骤；
- `delete`就是知识库业务删除流程；它只是后端物理删除原语，数据库软删除与清理编排尚未实现；
- 当前实现等于跨主机对象存储、备份或灾难恢复方案；V1仍是单机本地Storage。

**常见问题与优先排查方向**

- 报“Storage对象Key无效”：先检查是否严格使用小写UUID、允许的分类、小写扩展和`yyyy/mm`五段格式，不要传绝对路径；
- 报“Storage对象已存在”：调用方应为新文件生成新UUID，不要依赖覆盖已有对象；
- 报“Storage配置无效”：检查根目录不能是磁盘根、普通文件或符号链接，并确认父目录权限；
- 报“Storage对象写入失败”：优先检查磁盘空间、目录写权限、防病毒软件占用，以及目标文件系统是否支持同目录硬链接原子发布；
- 留下`.tmp`文件：通常表示进程被强制终止或系统在清理时拒绝删除；先确认没有运行中的写入，再按对象目录和随机临时命名排查，不要删除正式对象；
- 符号链接测试被跳过：这是当前Windows创建测试链接的权限限制；安全分支已有确定性单元测试，仍建议在Linux CI或启用开发者模式的Windows补跑真实链接测试；
- 若Storage根目录可能被其他不受信进程同时改写，仅靠应用层路径复核不能消除所有文件系统竞态；生产部署应限制该目录的操作系统权限。

**下一步**

停止并等待用户理解和确认。下一步应当是M2-04“建立文件、文档、版本和ACL模型及迁移”；本次对M2-03的授权不包含M2-04。

## 15. M2-04 实施记录

### 2026-08-29｜M2-04｜建立文件、文档、版本和 ACL 模型及迁移

**状态：已完成**

**本步解决的问题**

M2-03只能安全保存二进制对象，PostgreSQL当时不知道文件属于哪个租户和用户、是哪份逻辑文档的第几版、当前生效版本是谁、谁有显式读取权限以及资源是否已软删除。本步建立四张知识元数据表和Alembic `20260829_0004`迁移，把tenant、owner、Storage Key、状态、版本、active指针、ACL和软删除边界变成数据库真实约束，而不是只依赖后续业务代码自觉遵守。

**输入、输出和上下游**

- 输入：后续Service要保存的租户/owner、文件元数据、逻辑文档、版本号与内容hash、解析/索引状态和角色/用户/市场授权；
- 输出：`files`、`documents`、`document_versions`、`document_acl`四张表及对应SQLAlchemy ORM；
- 上游：M1身份/角色/商品表、M2-02 PostgreSQL/pgvector基础设施和M2-03 Storage对象Key合同；
- 下游：M2-05 Schema/Repository/状态Service；当前没有业务代码读写这些表。

**用大白话解释运行过程**

本地Storage像文件仓库，M2-04新增的是仓库管理账本。`files`记“这个箱子是谁上传的、放在哪个内部货架、大小和指纹是什么”；`documents`记“这是一份稳定的产品说明书”；`document_versions`记“说明书第1版用哪只箱子，第2版又用哪只箱子”；`active_version_id`像“当前正式版本”书签，只能夹在这份文档自己的版本里；`document_acl`则记“明确允许哪个角色、用户或市场读取”。软删除只在账本上标记删除时间，物理文件以后再由受控清理流程处理。

**设计细化与边界**

- 按已确认M2方案采用`document_versions.file_id`，每个版本准确关联自己的物理文件，不沿用总体设计早期把单个`file_id`放在`documents`上的简化写法；
- `documents`显式保存稳定owner，避免尚无active版本时必须绕到文件表推断文档所有者；
- ACL使用互斥字段表达role/user/market三类主体，并用三条部分唯一索引分别阻止重复授权；
- 数据库保证active版本属于同一tenant和同一document；“只有索引ready才能切active”的状态转换由M2-05短事务Service实现，本步没有创建跨表触发器。

**修改文件与职责**

- `app/models/knowledge.py`：定义`StoredFile`、`Document`、`DocumentVersion`和`DocumentAcl` ORM、关系、索引与约束；
- `app/models/__init__.py`：把四个M2模型加入新运行链统一导出；
- `migrations/env.py`：让Alembic加载知识模型元数据；
- `migrations/versions/20260829_0004_knowledge_metadata.py`：按可回退顺序创建四张表，并在版本表创建后追加循环中的active外键；
- `tests/unit/test_knowledge_models.py`：验证ORM注册、映射无警告、版本唯一边界、active复合外键、ACL索引及无绝对路径字段；
- `tests/integration/test_knowledge_migration.py`：在真实PostgreSQL执行升级/回退/再升级和非法行约束验证；
- `README.md`、本文件和`docs/PROJECT_PROGRESS.md`：同步当前能力、验证事实和新停止点。

**调用链位置**

```text
前端（未经过）
→ API（未经过）
→ Schema（未实现）
→ Service / Repository（未实现）
→ Model（本步）
→ PostgreSQL（本步新增四张元数据表）/ pgvector（扩展保留，未新增向量列）
→ Evidence（未修改）
```

**验证方法与实际结果**

1. 从真实`20260828_0003`执行升级到`20260829_0004`成功；聚焦测试又实际执行`0004 → 0003 → 0004 → 0003 → 0004`，每次表存在/消失范围正确，M1运行表始终保留；
2. ORM与迁移聚焦9项通过，SQLAlchemy mapper在把警告当错误时仍能配置；active循环外键使用建表后追加方式，Alembic表排序无警告；
3. 真实PostgreSQL接受合法file/document/version以及role/user/market三类ACL，并拒绝跨租户file owner、跨租户document owner、Storage Key租户不匹配、跨租户version文件、重复版本号、同文档重复内容hash、active串到其他document、ACL字段混用、跨租户user ACL、未知role和重复market ACL；
4. 数据库拒绝缺少`deleted_at`的`soft_deleted`文件以及parse未ready但index已ready的版本；合法软删除可保留安全错误摘要；
5. `alembic check`在警告视为错误时仍报告`No new upgrade operations detected`，最终迁移为`20260829_0004 (head)`；
6. 后端全量确定性回归236项通过、3项按设计跳过：1项真实Qwen付费冒烟和2项当前Windows真实符号链接权限测试；未调用真实Qwen；
7. `ruff check app tests scripts migrations`通过；Mypy对包含本步文件的73个源文件通过；Python编译与`pip check`通过；
8. 最终PostgreSQL容器healthy、pgvector仍为0.8.6；全量测试清理后重跑`m1-v1` Seed，DE-FRA可售库存恢复并实查为125；四张M2表保持0行，没有残留测试数据；
9. 未创建Chunk/向量列，未调用Storage、未实现Schema/Repository/Service/API、未修改前端、未下载模型、未提交或推送Git。

**能够证明**

- 四张M2知识元数据表能从当前M1数据库安全升级、完整回退并再次重建；
- tenant与owner复合外键能够阻止文件、文档、版本和用户ACL跨租户串联；
- 同一文档的版本号与内容hash唯一，每个物理文件只能对应一个版本；
- active版本指针不能指向其他tenant或其他document的版本；
- role/user/market ACL格式互斥且同一主体不会重复授权；
- Storage Key、SHA-256、文件状态、解析/索引状态和软删除字段具有数据库级格式与一致性约束；
- M1迁移、Seed答案125与pgvector 0.8.6没有因本步退化。

**不能证明**

- 用户已经可以上传、列表、下载或删除文件；API与Schema尚未实现；
- Repository查询已自动带tenant、owner、ACL、active和deleted过滤；这是M2-05及检索步骤的职责；
- active版本一定已经解析和索引ready；数据库只保证归属正确，ready后原子切换由M2-05状态Service验证；
- LocalStorage对象和数据库元数据已经组成跨资源原子事务；当前两层尚未由File Service接线；
- PDF/DOCX/XLSX/CSV已经解析，或已有Chunk、FTS、1024维向量、混合检索和Evidence；
- 软删除后物理文件已清除；本步只提供标记字段，后台清理不在V1当前步骤。

**常见问题与优先排查方向**

- `alembic current`仍为`0003`：先确认容器healthy和`.env`连接的是本项目数据库，再执行`alembic upgrade head`，不要手工建表；
- 文件插入被Storage Key约束拒绝：检查Key中的tenant、category、年月、文件UUID和扩展是否分别与行字段一致；
- 版本插入唯一约束失败：区分是重复`version_no`、同文档重复`content_hash`，还是同一`file_id`被重复使用；
- active更新失败：确认version属于相同tenant和document，不要只按全局UUID猜测归属；
- ACL插入失败：role只填`role_name`、user只填`user_id`、market只填两位大写`market_code`，另外两列必须为空；
- 软删除失败：`files.status='soft_deleted'`必须同时设置`deleted_at`，非soft_deleted状态不得带删除时间；
- Alembic出现模型漂移：优先比较`knowledge.py`与`0004`的列类型、约束名、索引和active外键，不要直接生成另一个迁移掩盖差异。

**下一步**

停止并等待用户理解和确认。下一步应当是M2-05“冻结文件与文档Schema、Repository和状态Service”；本次对M2-04的授权不包含M2-05。

## 16. M2-05 实施记录

### 2026-08-29｜M2-05｜冻结文件与文档 Schema、Repository 和状态 Service

**状态：已完成**

**本步解决的问题**

M2-04只有数据库表和约束，还没有统一规定“外部可以提交什么字段、谁能读或管理哪份文件、状态可以怎样变化、什么条件下版本才能生效”。本步补齐严格Schema、固定Repository查询、文件/文档状态Service和安全错误码，使租户、owner、角色、市场ACL、软删除和ready激活规则由后端统一执行，而不是交给后续API或调用方自行拼接。

**输入、输出和上下游**

- 输入：后端可信的`CurrentUser`、已经由Storage生成并校验的对象事实、文件/文档Schema请求和资源UUID；
- 输出：不含tenant、Storage Key、路径或SQL的文件/文档响应，或稳定且脱敏的404/409/422/500错误；
- 上游：后续M2-06上传API、M2-03 Storage对象合同和M1登录身份；
- 下游：M2-04 ORM与PostgreSQL四张知识元数据表；Parser、Embedding、Retrieval和Evidence仍未接入。

**用大白话解释运行过程**

Schema像前台表格，只允许填写文件名、文档标题和授权对象，tenant、owner、内部货架位置和SQL根本没有输入框。Service像业务主管，检查当前用户是不是owner或公司管理员、文件能不能从当前状态走到下一状态、版本是否已经解析和索引完成。Repository像只能使用固定取货单的库管，每条读取都把tenant、未删除和owner/ACL条件直接写进SQL；查不到和无权查看统一返回“未找到”，不会暴露别人的资源是否存在。只有版本解析ready、索引ready且对应文件ready时，Service才允许把它设为当前正式版本。

**设计细化与最小差异处理**

- 外部请求统一拒绝额外字段，尤其是`tenant_id`、`owner_user_id`、`path`、`storage_key`和`sql`；可信身份来自`CurrentUser`，Storage事实来自受控Service参数；
- 普通ACL读者可以读取文档与文件元数据，但不能看到ACL名单；只有文档owner或`company_owner`能管理和查看ACL；
- 用户ACL主体必须是同一tenant的active用户，角色ACL必须引用已登记角色，市场ACL只接受当前DE/FR边界；
- 同一文档不能用相同内容hash新增版本；软删除文件后该文件不可读，若它是active版本或未激活文档已无其他有效版本，关联文档也不再可读；
- 阶段方案把本步Service写成`app/services/documents.py`，又把M2-07解析器规划在`app/services/documents/parsers/`，两者在Python中不能长期共存。采用可回退的包结构`app/services/documents/service.py`并从包入口继续导出`DocumentService`，没有创建解析器或提前实现M2-07。

**修改文件与职责**

- `app/schemas/files.py`：文件登记、状态转换和安全响应合同；校验基础文件名、扩展名、SHA-256及错误摘要；
- `app/schemas/knowledge.py`：文档创建、新版本、ACL、解析/索引状态和安全响应合同；
- `app/repositories/files.py`：固定tenant/owner/ACL/软删除文件查询和状态持久化；
- `app/repositories/documents.py`：固定文档权限查询、版本、ACL、状态更新、ready版本激活与软删除持久化；
- `app/services/files.py`：核对可信Storage事实、文件状态机以及安全响应转换；
- `app/services/documents/__init__.py`、`service.py`：文档owner/ACL规则、版本状态机和active切换；包结构为后续解析器避免同名冲突；
- `app/core/errors.py`、`app/schemas/common.py`、`app/api/errors.py`：新增文件/文档404和状态、版本、ACL冲突409错误合同；没有新增API路由；
- `app/schemas/__init__.py`、`app/repositories/__init__.py`、`app/services/__init__.py`：冻结M2-05公共导入边界；
- `tests/unit/test_knowledge_schemas.py`：验证输入字段、ACL形状、状态命令和响应脱敏；
- `tests/integration/test_knowledge_services.py`：用真实PostgreSQL验证tenant/owner/user/role/market权限、状态机、重复hash和软删除；
- `tests/unit/test_m2_baseline.py`：把旧M2-03停止线更新到M2-05，继续禁止Parser、Retrieval和文件API；
- `README.md`、本文件和`docs/PROJECT_PROGRESS.md`：同步当前能力、验证事实和新停止点。

**调用链位置**

```text
前端（未经过）
→ API（未新增路由；只补错误映射）
→ Schema（本步）
→ Service（本步）
→ Parser / Embedding / Retrieval（未实现）
→ Repository（本步）
→ Model（复用M2-04）
→ PostgreSQL（本步真实读写验证）/ pgvector（扩展保留，未使用向量）
→ Evidence（未修改）
```

**验证方法与实际结果**

1. `tests/unit/test_knowledge_schemas.py`与更新后的M2停止线测试共37项通过；额外tenant/owner/path/storage_key/sql字段、路径型原名、扩展不一致、错误摘要控制字符、非法ACL形状和不完整ready产物均被拒绝，6类新增错误码稳定映射到404或409；
2. `tests/integration/test_knowledge_services.py`在真实PostgreSQL共4项通过：owner、company owner、用户/角色/市场ACL和跨tenant隔离生效，普通读者看不到ACL名单；
3. 文件和版本合法状态链通过，`uploaded → ready`、解析未ready直接索引、未ready直接激活等非法跳转返回安全冲突；只有解析、索引和文件均ready时active切换成功；
4. 合法新版本递增为第2版，同一文档重复内容hash被拒绝；文件软删除后该文件按404隐藏，多版本文档仍可读取其他有效版本，而唯一版本被删的文档也按404隐藏；文档自身软删除后，文档及关联文件都由访问层隐藏，但物理行和Storage对象未清除；失败文件可从`failed`回到`validating`且旧错误摘要清空；
5. Ruff对本步Schema、Repository、Service、错误与测试通过；Mypy严格检查6个本步核心源文件通过；公共`app.schemas`、`app.repositories`和`app.services`导入烟测通过；
6. 聚焦验证合计41项通过；没有调用真实Qwen、下载BGE模型、创建新迁移、写上传API、Parser、Embedding、Retrieval、Evidence或前端。

**能够证明**

- 文件和文档公共数据合同不会接受调用方伪造tenant、owner、内部路径、Storage Key或SQL；
- 固定Repository查询在SQL层同时限制tenant、软删除和owner/用户/角色/市场ACL；
- owner和公司管理员的管理权限、普通ACL读取权限及跨tenant隐藏边界符合M2方案；
- 文件、解析和索引状态不能任意跳跃，版本生效前必须满足三类ready条件；
- 重复内容版本、重复/无效ACL和已软删除资源具有稳定安全错误；
- 现有M2-04数据结构足以承载本步元数据流程，不需要新增数据库迁移。

**不能证明**

- 浏览器或HTTP客户端已经可以上传、列表、下载、删除或查看状态；M2-06 API与前端仍未实现；
- 二进制文件写入LocalStorage与数据库元数据写入已经形成完整补偿流程；本步只接收受控Storage结果，没有执行上传；
- PDF/DOCX/XLSX/CSV已经解析，或解析产物Key对应真实对象；本步只冻结后续内部状态合同；
- 已有Chunk、全文索引、1024维向量、Embedding、Reranker、混合检索或Evidence；
- 并发创建同一文档新版本时永远不会竞争；数据库唯一约束会安全拒绝冲突，后续调度/API仍需把冲突映射为合适重试体验；
- 全部M1和前端回归仍通过；本步按风险只运行41项聚焦测试，没有调用真实Qwen或重复前端测试。

**常见问题与优先排查方向**

- 返回`FILE_NOT_FOUND`或`DOCUMENT_NOT_FOUND`：先检查登录tenant、owner/ACL和软删除状态；无权与不存在故意统一404，不要通过放宽SQL绕过；
- 返回状态冲突：检查当前文件、parse和index状态，不要直接把记录改成ready；按`uploaded → validating → parsing → indexing → ready`及对应版本状态顺序推进；
- active切换失败：确认目标版本属于当前文档，parse/index均ready，并且版本关联文件也是ready且未软删除；
- ACL冲突：检查主体类型只填写对应的一列，用户属于同一tenant且active、角色已登记、市场为DE或FR，并确认没有重复授权；
- 新版本hash冲突：表示内容与该逻辑文档已有版本相同，应复用已有版本或让调用方明确选择，不要篡改hash；
- Service导入失败：统一使用`from app.services.documents import DocumentService`，不要依赖内部`service.py`路径；
- PostgreSQL异常被映射为安全500：优先查服务端日志、statement timeout和数据库约束；不要把驱动异常或SQL文本返回给客户端。

**下一步**

停止并等待用户理解和确认。下一步应当是M2-06“实现上传、列表、状态、下载和软删除API”；本次对M2-05的授权不包含M2-06。

## 17. M2-06 实施记录

### 2026-08-29｜M2-06｜实现上传、列表、状态、下载和软删除 API

**状态：已完成**

**本步解决的问题**

M2-05已经有Storage、文件元数据Service和权限查询，但浏览器或HTTP客户端没有正式入口。本步新增受JWT保护的文件API，把multipart上传、安全类型检查、LocalStorage原子写入、PostgreSQL元数据事务、owner/ACL读取、`file_id`下载和软删除接成一个最小闭环。跨Storage和数据库无法使用同一个原子事务，因此额外建立请求补偿栈：只要批量后续文件、数据库flush或最终commit失败，就反向删除本请求已经发布的Storage对象。

**输入、输出和上下游**

- 输入：Bearer Token、名为`files`的1至配置上限个multipart文件，或查询/下载/删除使用的UUID `file_id`；
- 输出：201文件元数据列表、200获权列表/状态/二进制下载、204软删除，或统一脱敏的401/404/409/422/500；
- 上游：当前没有M2前端，调用方可使用HTTP客户端；身份仍由M1 JWT每次从PostgreSQL刷新；
- 下游：M2-03 LocalStorage、M2-05 File Service/Repository和M2-04 `files`表；不创建Document，不进入Parser、Embedding、Retrieval或Evidence。

**用大白话解释运行过程**

用户把文件交到API门口后，后端先检查“几份文件、名字和扩展名是否安全、浏览器声称的类型是否匹配、里面是不是对应格式、大小有没有超限”。通过后，后端自己生成UUID货架号，把原始字节写进LocalStorage，Storage同时计算大小和SHA-256；然后数据库只记文件属于谁、内部对象Key、hash和状态。返回给用户的只有`file_id`和公开元数据。下载时用户也只能拿`file_id`来领文件，Repository先检查tenant、owner或文档ACL，真正的Storage Key始终留在服务端。

如果一批文件中第一份已经落盘、第二份却不合法，或者数据库最后提交失败，请求补偿栈会按相反顺序删除已经落盘的对象，数据库事务也回滚。软删除则不同：它只把数据库状态改成`soft_deleted`并立即隐藏访问，原始对象仍保留，等待未来受控清理策略。

**接口合同**

- `POST /api/v1/files`：批量multipart上传，整批成功或整批回滚；
- `GET /api/v1/files?limit=1..100`：列出当前身份可访问且未软删除的文件；
- `GET /api/v1/files/{file_id}/status`：返回公开元数据和状态；
- `GET /api/v1/files/{file_id}`：流式下载，使用安全`Content-Disposition`、准确长度和`nosniff`；
- `DELETE /api/v1/files/{file_id}`：仅owner或当前tenant的`company_owner`可软删除，成功返回204。

**安全与格式边界**

- 文件名先由基础Schema去除首尾空格，再拒绝路径分隔符、控制字符、扩展不一致和空名称；内部对象Key使用tenant/年月/文件UUID，不包含原始文件名；
- PDF要求`application/pdf`、PDF头和尾部EOF标记；DOCX/XLSX要求对应MIME、合法ZIP中央目录、必要Office成员、非加密且成员数/声明解压体积有界；CSV只接受受控文本MIME、拒绝NUL和已识别的其他二进制格式，并验证UTF-8-SIG或GB18030文本头；
- 单文件实际字节数必须大于0且不超过配置上限，批量数量不能超过配置；LocalStorage仍用分块读取和原子发布；
- 无权限、跨用户、跨tenant和软删除资源与不存在统一映射为`FILE_NOT_FOUND` 404；公开JSON和下载头不含Storage Key或路径；
- 下载只打开Repository已经授权行的内部Key；数据库有记录但对象丢失时返回安全500，不伪装为用户404；
- `python-multipart`和`filetype`是M2-01已声明、本步首次实际需要的小型依赖，已安装到项目虚拟环境；没有安装FlagEmbedding或下载任何BGE权重。

**修改文件与职责**

- `app/api/routers/files.py`：五类文件HTTP操作、multipart入口、安全下载响应和公开OpenAPI错误合同；
- `app/api/dependencies.py`：懒加载LocalStorage、构造File Service，并让请求补偿生命周期包住数据库commit；
- `app/main.py`、`app/api/routers/__init__.py`：注入可测试Storage并注册`/api/v1/files`路由；
- `app/services/files.py`：上传大小/MIME/格式检查、UUID Key落盘、元数据登记、失败补偿和获权下载；
- `app/schemas/files.py`、`app/schemas/__init__.py`：加强文件名边界并增加批量上传响应；
- `app/core/errors.py`：增加上传422和Storage 500的脱敏业务异常；
- `tests/integration/test_file_api.py`：真实PostgreSQL加临时LocalStorage验证完整API、安全拒绝和补偿；
- `tests/unit/test_knowledge_schemas.py`、`tests/unit/test_m2_baseline.py`：同步文件名/批量响应合同和M2-06停止线；
- `README.md`、本文件和`docs/PROJECT_PROGRESS.md`：同步当前能力、验证结果和下一停止点。

**调用链位置**

```text
前端（未实现；HTTP客户端可调用）
→ API（本步：认证、multipart、file_id和下载响应）
→ Schema（复用并扩展M2-05）
→ File Service（本步扩展：格式检查、Storage协调和补偿）
→ Parser / Embedding / Retrieval（未经过）
→ Storage（本步正式接线） + Repository（复用M2-05）
→ Model（复用M2-04）
→ PostgreSQL（真实事务验证）/ pgvector（未使用向量）
→ Evidence（未修改）
```

**验证方法与实际结果**

1. `tests/integration/test_file_api.py`共6项通过：PDF/DOCX/XLSX/CSV批量上传、列表、状态、下载、原名与UUID Key分离、SHA-256、owner隔离、软删除和OpenAPI范围均符合合同；
2. 空文件、超过1MiB测试上限、PDF伪装、MIME不匹配、损坏DOCX、路径型文件名、批量超过5份均返回安全422，数据库和Storage保持原状；
3. “第一份已落盘、第二份非法”的批量失败会回滚数据库并删除第一份对象；模拟数据库flush失败以及文件已经flush但最终request commit失败时，对象同样被补偿删除，响应不含SQL或Storage Key；
4. 同tenant其他普通用户对状态、下载和删除均得到相同404；owner软删除得到204，此后状态/下载不可读，但测试确认物理Storage对象仍存在；
5. M2-06相关Schema、Storage、M2-05 Service和M1 API组合回归86项通过、2项Windows符号链接权限测试按设计跳过；
6. 后端全量确定性回归267项通过、3项按设计跳过，其中包括1项真实Qwen付费冒烟和2项Windows真实符号链接测试；未调用真实Qwen；
7. Ruff通过；Mypy严格检查5个M2-06核心源文件通过，检查时只关闭既有M1依赖链中的`redundant-cast`和`unused-ignore`提示；Python导入与编译通过；`pip check`报告无损坏依赖；
8. Alembic仍为`20260829_0004 (head)`，PostgreSQL容器healthy，最终`files/documents/document_versions/document_acl`均为0行，M1 DE-FRA可售库存仍为125；
9. 高可信秘密扫描和`git diff --check`通过；未新增迁移、Document、Parser、Chunk、Embedding、检索、Evidence或前端，未提交或推送Git。

**能够证明**

- 四类允许文件可以通过真实multipart接口安全落盘并生成与原名分离的UUID Key、实际大小和SHA-256；
- 类型声明、文件特征、大小、数量和文件名边界在进入长期Storage/数据库前受到控制；
- API读取和下载复用M2-05的tenant/owner/ACL SQL过滤，普通用户无法通过猜测UUID读取或删除别人的文件；
- 软删除立即影响列表、状态和下载，但不会在请求事务中冒险物理删除原始对象；
- LocalStorage与PostgreSQL之间的常见部分失败，以及最终commit失败，会触发已验证的补偿清理；
- M2-06不需要新表或数据库迁移，并且没有破坏现有M1 API回归和库存答案125。

**不能证明**

- PDF、DOCX、XLSX或CSV的业务内容已经可提取或一定语义正确；当前只做上传层结构/类型门禁，真正解析分别属于M2-07至M2-09；
- 上传后已经自动创建逻辑Document、解析、分块、索引或生成Evidence；本步按方案只保存原文件和文件元数据；
- 软删除对象已经从磁盘清除；当前明确保留物理对象，未来需要受控清理与保留策略；
- 进程在Storage发布后、补偿动作登记前被操作系统强制终止时绝不会留下孤儿对象；跨数据库和文件系统没有真正的分布式原子事务，仍需未来巡检/清理；
- 单靠应用层上限足以抵挡生产互联网的大请求洪峰；ASGI multipart解析发生在业务校验之前，生产部署还应在反向代理设置总请求体、连接速率和并发限制；
- 前端聊天界面已经能上传文件；M2前端步骤尚未开始。

**常见问题与优先排查方向**

- 返回422：依次检查multipart字段必须叫`files`、批量数量、原名扩展、浏览器声明MIME、真实格式特征和单文件大小；不要通过只改扩展名绕过；
- 返回404：检查当前登录身份、tenant、owner/ACL和软删除状态；下载接口故意不区分不存在与无权限；
- 返回500且数据库有记录：优先检查对应Storage对象是否丢失、根目录权限或符号链接异常；不要把内部Key返回给客户端；
- 上传失败后出现孤儿对象：先检查异常是否发生在进程强制终止窗口、补偿删除权限和Storage日志，再按数据库中不存在的UUID Key做受控巡检，不要批量删除整个Storage目录；
- Office文件被拒绝：检查ZIP中央目录是否完整、必要的`[Content_Types].xml`、关系和`word/document.xml`或`xl/workbook.xml`是否存在，以及是否加密或声明解压体积异常；
- 大请求在到达业务代码前占用临时空间：在生产反向代理设置请求体和并发上限，并监控临时目录与Storage磁盘空间；
- 下载中文名异常：客户端应优先读取RFC 5987 `filename*`；服务端同时提供UUID加扩展名的ASCII回退名。

**下一步**

停止并等待用户理解和确认。下一步应当是M2-07“实现文本型PDF解析器”；本次对M2-06的授权不包含M2-07。
