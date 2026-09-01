# M2 原始阶段方案与总体设计

> 本文件保存从迁移前单文件中拆出的完整历史方案、实施日志与验证证据。
> 当前状态和阅读入口见 [M2入口](../M2_KNOWLEDGE_RAG.md)。

## 1. 本文档目的

本文档把已经确认的三份总体设计收缩成可逐步开发、逐步验证的 M2 实施合同。M2 只证明一条新的垂直链路：用户上传一份合成产品说明书，系统安全保存、解析、分块和索引；用户随后用自然语言提问，系统在租户与文档权限范围内完成关键词和向量混合检索、BGE 重排、回答生成，并把答案定位到文档页码、工作表或单元格范围。

M2 不重写 M1 登录、库存、Harness、Trace、聊天或 Evidence 基础，而是在这些已验证边界上增加知识与文件能力。

## 2. 开始前只读检查结果

### 2.1 Git 与工作区

- 当前分支为 `main`；
- `HEAD`、本地 `main`、本地缓存的 `origin/main` 和通过远端只读查询得到的 `origin/main` 均为 `94ad0eec837dfa618bb2e0c07e6a21769d690ebb`；
- 本地与远端 ahead/behind 为 `0/0`；
- 检查开始和 M1 回归结束后工作区均干净；
- 本轮没有提交或推送 Git。

### 2.2 本机与运行环境

| 项目 | 实际结果 | M2 含义 |
|---|---|---|
| 系统 Python | 3.9.13 | 不满足项目建议版本，不能直接使用 |
| 项目虚拟环境 Python | 3.11.9 | 后续必须使用 `.venv\Scripts\python.exe` |
| Node.js | 24.15.0 | 满足当前 Next.js 要求 |
| npm | 11.12.1 | `npm.ps1` 被 PowerShell 策略拦截，`npm.cmd` 正常 |
| Docker / Compose | 29.6.1 / 5.3.0 | 正常 |
| CPU / 内存 | 6 核 12 线程 / 15.9GB | 可做小规模本地推理，但需控制模型常驻和批量 |
| GPU | GTX 1650 Ti 4GB | 显存不足以默认同时常驻两个大模型 |
| D 盘可用空间 | 约 49.9GB | 可下载模型和保存演示文件，但必须配置缓存目录并忽略 Git |

`.env` 存在，并覆盖当前 `.env.example` 的全部 27 个键；Qwen、数据库和 JWT 必需键均已配置，本次只检查是否存在，未读取或输出秘密值。M2 尚缺 Storage、上传限制、Embedding、Reranker 和模型缓存等配置键，模板中也还没有这些键。

### 2.3 PostgreSQL、迁移与 Seed

- PostgreSQL 17.11 容器为 `healthy`；
- Alembic 为 `20260828_0003 (head)`；
- 当前镜像中 `vector` 扩展既不可用也未安装，M2 不能只执行 `CREATE EXTENSION`；
- Seed 为 1 个租户、4 个用户、3 个角色、1 个商品、1 个 SKU、4 条规格、2 个仓库和 2 条库存快照；
- `LR-TL-MUSH-OR01` 在 `DE-FRA` 的可售库存仍为 125；
- Thread、Message、AgentRun、ToolCall 和 Evidence 均为 0。

### 2.4 M1 回归基线

| 验证 | 实际结果 | 能证明 | 不能证明 |
|---|---|---|---|
| 后端全量测试 | 175 passed，1 个真实 Qwen 付费冒烟 skipped | M1 确定性后端和 PostgreSQL 集成基线未退化 | 真实 Qwen 长期稳定 |
| 前端组件 | 4 passed | M1 登录、发送、状态和 Evidence 交互合同未退化 | 真实浏览器整链 |
| TypeScript / ESLint / Build | 全部通过 | 当前前端可类型检查并生产构建 | M2 上传界面已存在 |
| Playwright Chromium | 4 passed | 成功查询、403、401、数据库停机与恢复整链可重复 | 其他浏览器、并发和 M2 文件链路 |
| 回归后数据 | 运行表 0，库存 125，容器 healthy | 测试清理和 M1 初始基线恢复成功 | M2 数据结构或模型可用 |

真实 Qwen 冒烟没有重复执行，因此本轮没有产生模型费用。

## 3. 现有能力与旧代码边界

### 3.1 新 `app/` 运行链中可直接扩展的基础

| 已有能力 | M2 的使用方式 |
|---|---|
| `Settings` 集中配置 | 增加 Storage、文件限制、模型和检索参数，不允许业务模块各自读环境变量 |
| 请求级 SQLAlchemy 事务和 Alembic | 新增文件、文档、版本、ACL、Chunk 和向量迁移 |
| JWT、RunContext、角色和市场范围 | 上传、读取、检索和 Evidence 详情都从可信身份取得 tenant/user/scope |
| ToolRegistry、PermissionGuard、Budget、Trace | 把 M2 三个 Tool 纳入同一服务端白名单与审计，不靠 Prompt 控权 |
| 严格 Pydantic Schema | 文件、解析、Chunk、检索、引用和错误继续默认拒绝额外字段 |
| LangGraph 显式流程 | 保留库存图，新增有界知识问答路径，不做自由循环 |
| Evidence 表、Service、API 与前端轨道 | 通过迁移扩展为 knowledge/user_file 来源，继续按 ID 授权读取 |
| Mock/Qwen Provider 边界 | Mock 负责免费回归；Qwen 只做受控 Tool 建议和基于 Evidence 的回答组织 |

### 3.2 已盘点但当前不存在的 M2 能力

- pgvector 镜像、扩展、Python 类型和向量索引；
- BGE-M3、BGE-Reranker、PyTorch/Transformers/FlagEmbedding；
- PyMuPDF、python-docx、openpyxl、Pandas 和 multipart 上传依赖；
- Storage 接口、本地数据根目录、原文件和解析产物目录；
- 文件元数据、文档、版本、ACL、Chunk 和索引状态表；
- 上传、状态、下载、软删除、重试和新版本 API；
- PDF/DOCX/XLSX/CSV 解析、结构感知分块和定位信息；
- Dense、Lexical、RRF、Reranker、Context Builder 和引用验证；
- M2 三个 Agent Tool、知识问答图、RAG 评估集和最小前端。

### 3.3 旧原型只可参考的内容

| 旧代码 | 可以参考 | 不能直接导入的原因 |
|---|---|---|
| `api/server.py` 上传原型 | FastAPI `UploadFile` 和流式复制思路 | 信任原文件名、直接拼会话目录、无大小/MIME/哈希/tenant/元数据/事务，且全开放 CORS |
| `tools/upload_file_read_tool.py` | 不同扩展名需要不同解析器 | 接受文件名/路径、允许会话外绝对路径、整份文件直接转字符串、异常原文外泄、无定位/权限/预算 |
| `utils/path_utils.py` | `Path.resolve()` 和路径归一化意识 | 实现重复定义，明确允许会话外绝对路径和特殊 `updated/` 逃逸，不满足 Storage key 边界 |
| `tools/ragflow_tools.py`、`rawflow/` | 知识检索需要独立边界的概念 | 依赖 RAGFlow、导入即初始化外部客户端、无自建索引、无 ACL、无引用验证且返回原始异常 |
| `agent/subagents/knowledge_base_agent.py` | Knowledge Worker 的职责名称 | 导入旧 RAGFlow Tool，不经过新 Registry/Harness/RunContext |
| `requirements-legacy.txt` | 解析库候选和旧版本线索 | 只供旧教学原型，不是新链依赖合同，不能整体安装回主环境 |

旧 `agent/`、`api/`、`tools/`、`rawflow/` 和 `utils/` 继续保留为迁移参考，但 M2 新运行链不得导入它们。旧代码出现的 RAGFlow、绝对路径、MySQL、任意 SQL、内存事件和原始异常处理全部禁止带入 `app/`。

## 4. 用大白话解释 M1、M2 和 RAG

### 4.1 M1 已完成什么，为什么是 M2 的地基

M1 已经把“谁在问、能看什么、模型最多做几次、真正是谁查数据库、答案证据存在哪里”解决了。M2 不需要再造登录、权限、聊天和审计，而是给这套安全管道增加一种新数据源：内部文件。

没有 M1，M2 很容易退化成“任何人上传文件，模型随便读磁盘，再把整篇内容丢给大模型”。有了 M1，M2 可以保证：用户只用 `file_id/document_id/evidence_id`，真实路径只在服务端；检索先做 tenant 和 ACL 过滤；模型只看到最终允许的片段；每条引用能反查原文位置；失败仍有状态和 Trace。

### 4.2 一份 PDF 从上传到回答会经历什么

```text
用户选择 PDF
→ FastAPI 校验登录、大小、扩展名、声明 MIME 和文件签名
→ LocalStorage 用 UUID key 保存原文件，PostgreSQL 保存文件元数据
→ PyMuPDF 按页提取文本和页码，保存版本化解析产物
→ 分块器按标题/段落切成约 400～700 token 的小块
→ BGE-M3 把每个块变成 1024 维向量
→ PostgreSQL 保存块文本、页码、全文检索字段和 pgvector 向量
→ 用户提问时，SQL 先按 tenant、ACL、有效版本和软删除状态过滤
→ 向量检索和关键词检索各取候选，RRF 融合
→ BGE-Reranker 对候选重新排序
→ Context Builder 去重、补邻块并控制 Token
→ Qwen 只依据这些 Evidence 片段组织回答
→ 引用验证后返回答案和 [E1]、[E2]
→ 右侧 Evidence 可定位到文档名、版本、页码/Sheet/单元格范围
```

### 4.3 专业词第一次出现时的大白话解释

| 术语 | 大白话 | 本项目例子 |
|---|---|---|
| Storage | 管理文件保存和读取的统一“仓库接口” | API 只给它对象 key，不给 Windows 绝对路径 |
| 文档解析 | 把二进制文件变成带结构的文字 | PDF 保留页码，XLSX 保留 Sheet 和单元格范围 |
| 分块 | 把长文档切成适合检索的小段 | 一条合规条款尽量保持在同一个块中 |
| Embedding | 把文字转换成能比较语义距离的一串数字 | “三档调光”和“三级亮度”即使字不同也可能靠近 |
| pgvector | PostgreSQL 保存和检索向量的扩展 | `document_chunks.embedding vector(1024)` |
| 关键词检索 | 按实际出现的词找文本 | 型号、条款号、尺寸和 SKU 更适合关键词命中 |
| 混合检索 | 同时用语义和关键词，再合并排名 | Dense top-30 + Lexical top-30 + RRF |
| RRF | 不强行比较两种不同分数，而按各自名次融合 | 同时在两路靠前的块获得更高综合排名 |
| Reranker | 让专门模型拿“问题+候选段落”做第二次精排 | 从融合候选中挑出最相关的 5～8 个块 |
| 引用 | 答案与原文证据的可点击关系 | `[E2]` 对应说明书第 3 页“开关操作” |
| ACL | 文档访问名单 | FR 运营不能检索只授权 DE 的内部文档 |
| 软删除 | 先标记不可见，不马上删物理文件 | 检索立即排除，物理清理以后单独执行 |

### 4.4 与“把整份文档发给大模型”的区别

整份发送会浪费 Token、容易超过上下文、每次重复付费、难以定位原句，也很难在发送前对每个文档做权限过滤。M2 的 RAG 先在本地找出少量最相关片段，只把获权 Evidence 交给 Qwen。这样更便宜、更快、更容易引用和评估；但检索可能漏掉关键段落，所以必须有 Recall、无答案拒答和引用准确率评估，不能把 RAG 当成绝对正确。

## 5. M2 目标、范围与明确不做

### 5.1 本阶段目标

- 本地 Storage 接口与安全文件 key；
- PDF、DOCX、XLSX、CSV 上传、解析和状态；
- 文件、逻辑文档、版本、ACL、Chunk 和索引元数据；
- 结构感知分块、BGE-M3、pgvector 和 PostgreSQL 全文检索；
- Dense + Lexical + RRF + BGE-Reranker；
- 文档名、版本、页码、标题、Sheet、单元格或行范围引用；
- `search_knowledge`、`read_uploaded_file`、`get_evidence_detail` 三个只读 Agent Tool；
- 有界知识问答路径、Mock 基线和可选真实 Qwen 回答；
- 最小版本化合成文档与 RAG 评估集；
- 最小上传、处理状态、知识问答和 Evidence 展示前端。

### 5.2 M2 明确不做

- 商品、仓库、库存管理后台；
- 把 XLSX/CSV 直接导入商品、仓库、库存或经营业务表；
- 真实 Amazon SP-API、ERP、供应商系统同步；
- 图片理解、OCR 产品化和相似 SKU，属于 M3；
- Tavily、Supervisor、多 Worker、深度报告和完整 Skill 运行时，属于 M4；
- Celery、Redis、持久后台队列和跨进程恢复；M2 使用显式同步索引端点和可重试状态；
- MinIO/S3、云部署和完整商业多租户计费；
- 扫描 PDF 的完整 OCR、复杂版面、手写体和公式识别；
- Elasticsearch、Milvus、ChromaDB、RAGFlow 或 MCP；
- 物理文件自动垃圾回收；M2 只完成软删除和可测试的清理接口边界；
- 提前开发 M3、M4 或 M5。

## 6. M2 总体技术方案

### 6.1 完整调用链

```text
Next.js 前端
  上传、状态、问题、回答、引用定位
→ FastAPI API
  JWT、multipart、file/document/evidence ID、HTTP 错误
→ Pydantic Schema
  文件合同、状态、解析结果、Tool、检索、引用和错误
→ Service
  Storage、文件状态、解析调度、分块、索引、检索、Context、Evidence
→ Parser / Embedding / Retrieval
  PyMuPDF / python-docx / openpyxl+Pandas / BGE-M3 / RRF / Reranker
→ Repository + SQLAlchemy Model
  tenant、ACL、有效版本、软删除、向量和全文检索固定查询
→ PostgreSQL / pgvector
  元数据、Chunk、向量、FTS、Trace 和 Evidence
→ Qwen 或 Mock
  只看获权 Context，组织答案，不读取路径或数据库
→ Evidence
  文档、版本、页码/Sheet/范围和片段返回前端
```

### 6.2 PostgreSQL 保存什么，本地目录保存什么

| 保存位置 | 内容 | 原因 |
|---|---|---|
| PostgreSQL | file_id、原名、Storage key、MIME、大小、SHA-256、owner、状态、错误摘要、deleted_at | 可查询、可授权、可审计 |
| PostgreSQL | 逻辑文档、版本、active_version、parser/embedding 版本、ACL | 版本和权限必须参与 SQL 过滤 |
| PostgreSQL / pgvector | Chunk 原文、定位元数据、token 数、FTS 字段、1024 维向量 | 混合检索需要文本、权限和向量一起过滤 |
| PostgreSQL | ToolCall、Knowledge/User-file Evidence、检索分数摘要 | 回答和证据可追踪 |
| 本地 Storage | 原始 PDF/DOCX/XLSX/CSV 二进制 | 不把大二进制塞进业务数据库 |
| 本地 Storage | 版本化解析 JSON 产物 | `read_uploaded_file` 可按页/段/Sheet 有界读取，也便于重新分块 |
| 本地模型缓存 | BGE-M3、Reranker 权重和 tokenizer | 模型文件体积大，必须忽略 Git |

前端、模型和 Tool 永远只接触 ID、标题和安全定位，不接触 `D:\...` 绝对路径或 Storage key。

### 6.3 建议的数据模型

| 表 | 核心职责 |
|---|---|
| `files` | 每次上传的物理对象元数据、owner、hash、状态、错误、软删除 |
| `documents` | 稳定的逻辑文档、标题、类型、语言、市场、access_level、active_version_id |
| `document_versions` | 某次内容版本关联的 file_id、parser/embedding 版本、parse/index 状态和解析产物 key |
| `document_acl` | role/user/market 授权；检索 SQL 必须先关联过滤 |
| `document_chunks` | 版本内 chunk、页码/Sheet/单元格/行范围、原文、token、hash、FTS 和 `vector(1024)` |

与总体设计相比，本方案建议让 `document_versions.file_id` 关联每个版本的物理文件，而 `documents` 只保存稳定逻辑身份和 `active_version_id`。否则新版本上传后无法准确知道每个版本对应哪份原文件。该细化随整个 M2 方案一起等待用户确认。

### 6.4 文件状态与同步索引边界

```text
uploaded → validating → parsing → indexing → ready
     └─────────────── 任一阶段失败 ─────────→ failed
ready/failed → soft_deleted
```

M2 不提前引入 Redis/Celery。上传 API 只负责安全落盘和元数据；显式 `POST /files/{file_id}/index` 同步执行本地演示规模的索引，并在失败时持久化安全状态，用户可重试。它能证明管线正确和幂等，但不能证明进程崩溃后的后台任务自动恢复；持久 Worker 属于 M4。

### 6.5 更新、重新索引、软删除、版本和重复文件

- 新上传：创建 file、document 和 version 1；索引成功后才把该版本设为 active；
- 内容更新：为同一 document 创建新 file 和新 version，旧版本继续可查，直到新版本完整 ready 后在一个短事务中原子切换 active；
- 解析或索引失败：保留旧 active 版本，新版本标记 failed，不让半成品进入检索；
- 重新索引：同一版本使用新的 `embedding_version/chunking_version` 建新索引结果，成功后切换，不覆盖已验证旧结果；
- 软删除：立即写 `deleted_at` 并从文件读取、检索和 Evidence 新访问中过滤；物理删除由以后独立清理任务完成；
- SHA-256 重复：在同一 tenant 和同一逻辑文档内阻止重复版本；跨 owner 不返回别人的 file_id，也不做可能泄露存在性的全局去重；
- Chunk 幂等：`version_id + chunk_index + content_hash + embedding_version` 建唯一边界，重试先核对或安全替换当前未激活索引，不重复追加。

### 6.6 权限规则

- 三类角色都可上传；默认新文档为 owner 私有；
- 公司负责人可查看当前租户有效文档；普通用户只看自己上传或 ACL 明确授权的文档；
- market ACL 与用户数据库当前 `market_scopes` 求交；
- ACL 必须进入 Dense 和 Lexical 两条 SQL 的 `WHERE/JOIN`，禁止先跨租户搜索再在 Python 删除；
- `read_uploaded_file` 和 `get_evidence_detail` 也必须复用同一资源授权规则；
- Prompt、模型建议和前端传入的 tenant/owner/role 一律不可信。

### 6.7 三个 M2 Tool

| Tool | 输入 | 输出 | 不做什么 |
|---|---|---|---|
| `search_knowledge` | 查询文本、可选安全过滤条件 | 重排后的片段、定位、分数摘要和 Evidence ID | 不读未授权版本，不生成最终自由答案，不接收 SQL/tenant |
| `read_uploaded_file` | file_id、可选页/Sheet/范围和最大长度 | 已解析产物中的有界文本或表格预览 | 不接收路径，不把整份大文件无界塞给模型，不写业务表 |
| `get_evidence_detail` | evidence_id | 当前身份获权的严格 Evidence 详情 | 不绕过 tenant/ACL，不返回 Storage key、路径或数据库连接 |

上传、解析、索引、Markdown/PDF 转换等确定性动作继续是 API/Service，不包装成让模型自由决定的 Agent Tool。

### 6.8 检索和引用初始参数

- Chunk 目标 400～700 tokens，overlap 80～120 tokens；按页、标题、段落、表头和行窗口调整；
- Dense 初取 30，Lexical 初取 30；
- RRF 初始常数 `k=60`；
- Reranker 输出 5～8 个块；
- Context 去重、必要时补相邻块，并使用独立 Token 预算；
- 中文关键词初版使用应用层分词后的 PostgreSQL `simple` FTS 字段，原文另存；不在 M2 增加 Elasticsearch 或新的 PostgreSQL 分词扩展；
- 所有参数进入配置和评估 run，不写死在 Prompt；最终值以 M2 评估结果为准。

引用定位：PDF 为页码；DOCX 为标题路径、段落或表格编号；XLSX 为 Sheet + 单元格范围；CSV 为行范围。回答中的 `[E1]` 只能引用本次返回且当前用户获权的 Evidence ID；缺失、错位或模型编造的引用必须在返回前拒绝或修复。

### 6.9 模型运行策略

- 单元、API、权限和大部分检索回归使用确定性 Fake Embedding/Fake Reranker，不下载模型也不依赖 GPU；
- pgvector 集成测试使用固定小向量，证明数据库距离和权限过滤；
- BGE-M3 和 Reranker 分别在自己的步骤显式下载、缓存、跑真实 CPU/GPU 基准，未经说明不联网；
- 模型懒加载、批量大小和设备可配置；在 15.9GB 内存/4GB 显存机器上默认避免两个模型同时常驻；
- 真实模型 Smoke 与完整离线回归分开，不能让日常 `pytest` 隐式下载数 GB 模型；
- 记录模型 ID、revision、维度、归一化、batch、设备、耗时和峰值内存，Embedding 变更必须生成新版本。

## 7. 24 个正式步骤（M2-11与M2-16各自包含受控子步骤）

每个步骤只解决一个清晰问题。完成代码、实际验证和阶段日志后暂停，不自动进入下一步。

### M2-01｜建立 M2 配置、依赖和新旧导入边界

- 目标：新增 Storage、上传、模型缓存、Embedding/Reranker 和检索参数合同，冻结 M2 直接依赖，不实现业务。
- 预计文件：`app/core/config.py`、`.env.example`、`.gitignore`、`requirements.txt`、`requirements-dev.txt`、`tests/unit/test_m2_baseline.py`、README。
- 调用链：配置/依赖层；不经过前端、API、Service、Model 或 PostgreSQL。
- 验证：配置合法/非法值、秘密不输出、主依赖可解析、新 `app/` 不导入旧 RAGFlow/上传工具；安装后 `pip check`、M1 全回归。

### M2-02｜为 PostgreSQL 17 增加 pgvector 基础设施

- 目标：选定并固定兼容镜像或可复现构建，安全验证现有命名卷、`CREATE EXTENSION vector` 和回退路径。
- 预计文件：`docker-compose.yml`、必要的 `docker/postgres/Dockerfile`、README、基础设施测试；本步不建业务向量表。
- 调用链：PostgreSQL 基础设施；未经过业务 API/Service。
- 验证：Compose 配置、容器 healthy、旧 M1 表与125不丢失、扩展版本可查询、普通重启持久化、M1 全回归。

### M2-03｜实现 Storage 接口和 LocalStorage

- 目标：只用对象 key 安全、原子地 put/open/exists/delete，所有路径强制位于数据根目录。
- 预计文件：`app/services/storage/base.py`、`local.py`、`contracts.py`、`tests/unit/test_local_storage.py`。
- 调用链：Service/Storage → 本地文件系统；不经过 API、Model、PostgreSQL。
- 验证：正常写读、UUID key、路径穿越/绝对路径/符号链接拒绝、临时文件清理、重复 key 策略和异常脱敏。

### M2-04｜建立文件、文档、版本和 ACL 模型及迁移

- 目标：新增 `files/documents/document_versions/document_acl` 及状态、tenant、owner、版本和软删除约束。
- 预计文件：`app/models/knowledge.py`、`app/models/__init__.py`、`migrations/versions/*_knowledge_metadata.py`、模型/迁移测试。
- 调用链：Model → PostgreSQL；未经过上传 API、Parser 或检索。
- 验证：升级/回退/再升级、跨租户外键、版本唯一、ACL 格式、active version 边界、软删除字段和 Alembic check。

### M2-05｜冻结文件与文档 Schema、Repository 和状态 Service

- 目标：统一文件元数据、状态机、owner/ACL 检查、错误码和对外响应。
- 预计文件：`app/schemas/files.py`、`knowledge.py`、`app/repositories/files.py`、`documents.py`、`app/services/files.py`、`documents.py`、测试。
- 调用链：Schema → Service → Repository → Model → PostgreSQL。
- 验证：合法/非法状态转换、tenant/owner/role/market、重复 hash、删除后不可读、额外 path/tenant/sql 字段拒绝。

### M2-06｜实现上传、列表、状态、下载和软删除 API

- 目标：安全接收 PDF/DOCX/XLSX/CSV，只保存文件和元数据，不在本步解析索引。
- 预计文件：`app/api/routers/files.py`、`app/api/dependencies.py`、`app/main.py`、API 集成测试。
- 调用链：前端未实现 → API → Schema → File Service → Storage + Model → PostgreSQL。
- 验证：multipart、大小/扩展名/MIME/签名、SHA-256、原名与 UUID key 分离、file_id 下载、越权404、软删除、损坏文件和部分写入清理。

### M2-07｜实现文本型 PDF 解析器

- 目标：用 PyMuPDF 提取页文本、页码和基础标题线索；识别低文本扫描页但不做 OCR。
- 预计文件：`app/services/documents/parsers/base.py`、`pdf.py`、PDF 合成测试夹具与测试。
- 调用链：File Service → Storage → PDF Parser；不经过 Embedding/pgvector。
- 验证：多页、空页、损坏/加密PDF、页码定位、超限保护、扫描件警告和异常脱敏。

### M2-08｜实现 DOCX 解析器

- 目标：保留标题层级、段落顺序、表格和定位编号。
- 预计文件：`app/services/documents/parsers/docx.py`、DOCX 合成夹具与测试。
- 调用链：Storage → DOCX Parser；不经过 Chunk/Embedding。
- 验证：标题、普通段落、多表格、空文档、损坏 ZIP、超大解压保护和定位稳定性。

### M2-09｜实现 XLSX/CSV 解析器

- 目标：提取 Sheet、表头、行、单元格/行范围和编码信息，不写商品库存业务表。
- 预计文件：`app/services/documents/parsers/xlsx.py`、`csv.py`、表格合成夹具与测试。
- 调用链：Storage → openpyxl/Pandas Parser；不经过业务商品/库存 Model。
- 验证：多 Sheet、公式值边界、空行、UTF-8-SIG/GB18030、分隔符、恶意 ZIP/超大表和行范围定位。

### M2-10｜建立 `m2-v1` 合成知识文件和 manifest

- 目标：生成说明书、质检 SOP、合规清单和报价/运营表格的最小版本化样本及标准定位。
- 预计文件：`scripts/seed_m2_files.py`、`data/seed/m2_seed.json`、`m2_manifest.json`、`tests/integration/test_seed_m2_files.py`、合成源文件生成逻辑。
- 调用链：开发数据入口 → Storage + File/Document Model → PostgreSQL；不经过 Agent。
- 验证：空环境生成、重复运行、hash/行数/页码/Sheet稳定、合成与非法律意见标记、无秘密、M1 Seed不变。

### M2-11｜实现解析调度与版本化解析产物

- 目标：保留 PyMuPDF/python-docx/openpyxl/Pandas 作为普通文件快速路径，引入 Docling 作为扫描件、复杂布局和复杂表格的本地增强后端；两条解析路径必须汇合为统一 Canonical Parsed Artifact JSON，再原子保存到 parsed Storage 并更新 parse 状态。Docling 不替代后续自建清洗、分块、Embedding、检索、重排和 Evidence。
- 子步骤：
  1. `M2-11.1`：建立不可覆盖 `m2-v1` 的 `m2-complex-v1` 正式合成复杂文档、黄金答案、黄金定位、路由预期、manifest 和 Seed；
  2. `M2-11.2`：安装并固定 Docling/模型依赖，在当前 Python 3.11、15.9GB 内存和 GTX 1650 Ti 4GB 环境完成 CPU/GPU、OCR、耗时、内存和显存真实基准；
  3. `M2-11.3`：建立统一 Canonical Parsed Artifact、可选页面边界框及四类 Native Parser 无损适配；
  4. `M2-11.4`：实现 Docling Adapter、解析质量门禁和 Parser Router；普通文件走 Native，复杂文件在安全检查后进入 Docling，危险/加密/损坏/超限文件直接拒绝；
  5. `M2-11.5`：实现 Parser Service、版本化 JSON 原子发布、parse 状态、失败补偿和重试闭环。
- 预计文件：`data/seed/m2_complex_seed.json`、`m2_complex_manifest.json`、复杂文件生成/Seed脚本、`requirements.txt`、`.env.example`、`app/core/config.py`、`app/services/documents/artifacts.py`、`parsers/docling.py`、`quality.py`、`routing.py`、`parser_service.py`、Document Service/Repository小幅扩展及单元/Smoke/集成测试。
- 调用链：开发评估数据或后续索引入口 → Parser Service → Storage → Native Parser → Quality Gate → 可选 Docling → Canonical Artifact → Storage → Document Model → PostgreSQL；不经过 Agent、Prompt、Embedding、pgvector 或前端。
- 验证：`m2-v1`字节/hash/定位不变；普通语料保持 Native；指定复杂语料进入 Docling；Native/Docling/Router 三路对照；危险文件不回退；统一 JSON、parser/模型版本、路由原因和定位可审计；真实模型不进入日常测试隐式下载；失败状态、补偿和重试安全；旧版本产物不被覆盖。
- 授权边界：五个子步骤逐一确认；确认 M2-11 总方案不自动授权 M2-11.2 至 M2-11.5。

### M2-12｜实现结构感知分块

- 目标：只消费统一 Canonical Parsed Artifact，先做确定性清洗，再按 PDF 页/段、DOCX 标题/表格、XLSX/CSV 表头+行窗口切块；Native与Docling产物共用同一套Chunk合同，并保留页码、标题、Sheet、单元格、行范围及可选边界框。
- 预计文件：`app/services/documents/chunking.py`、token 计数适配器、单元测试。
- 调用链：Parsed Artifact → Chunking Service；未写 PostgreSQL 向量。
- 验证：重复页眉页脚、OCR空白/噪声和重复块的确定性处理；400～700 token 目标、overlap、长段递归切分、条款/表头完整、表格Markdown视图、块顺序、内容 hash 和定位不漂移。

### M2-13｜建立 document_chunks、FTS 和 vector(1024) 模型及迁移

- 目标：保存 Chunk、定位、版本、FTS、Embedding 元数据和向量，建立必要索引。
- 预计文件：`app/models/knowledge.py`、`migrations/versions/*_knowledge_chunks_vector.py`、模型/pgvector集成测试。
- 调用链：Model → PostgreSQL/pgvector。
- 验证：迁移往返、维度拒绝、HNSW/FTS索引存在、active/tenant/ACL关联、唯一幂等约束、固定向量余弦排序。

### M2-14｜实现 BGE-M3 Embedding Provider 与真实基准

- 目标：建立可替换 Provider、批量编码、归一化、缓存 key 和 1024 维严格输出；本步才显式下载真实模型。
- 预计文件：`app/services/retrieval/embedding.py`、模型配置、Fake/真实 Smoke、基准脚本与记录。
- 调用链：Index Service → Embedding Provider；尚未完成全量索引。
- 验证：Fake确定性、真实中英文维度/有限值/相似性、revision记录、CPU/GPU耗时、峰值内存、batch降级和无网络回归。

### M2-15｜实现幂等索引、重试和版本原子激活管线

- 目标：串起 validate → parse → chunk → embed → save → ready，并支持新版本、重新索引和失败恢复。
- 预计文件：`app/services/documents/indexing.py`、`app/api/routers/files.py`索引/版本端点、Repositories、集成测试。
- 调用链：API → Schema → Index Service → Storage/Parser/Chunk/Embedding → Model → PostgreSQL/pgvector。
- 验证：首次索引、重复请求不增块、失败状态、旧 active 保留、新版 ready 后原子切换、删除文档不检索、进程中断限制有明确记录。

### M2-16｜实现权限前置的 Lexical、Dense、Hybrid 与 RRF 检索闭环

- 目标：一次完成“只能从获权的当前正式索引中找资料”的检索核心，但继续拆成七个单一职责小步骤逐项验证：
  1. `M2-16.1`：冻结检索输入、输出、分数和安全错误合同；
  2. `M2-16.2`：建立文档侧与查询侧一致的版本化中文分词，并增加兼容旧/新FTS builder的`0008`迁移；
  3. `M2-16.3`：建立Dense与Lexical共用的tenant、owner/company_owner、user/role/market ACL、active Version、active ready Index Set和软删除候选边界；
  4. `M2-16.4`：使用`QUERY`用途Embedding和pgvector余弦距离实现Dense top-N；这是原路线图M2-16的核心；
  5. `M2-16.5`：使用同版jieba和PostgreSQL FTS实现中文、英文、SKU、型号及条款号Lexical top-N；这是原路线图M2-17的核心；
  6. `M2-16.6`：按chunk去重并用固定`rrf_k=60`融合两路名次，保留原始排名和分数；这是原路线图M2-18的核心；
  7. `M2-16.7`：完成Fake日常闭环、固定向量真实PostgreSQL排序、显式离线BGE Smoke、故障矩阵和正式Seed恢复。
- 预计文件：`app/schemas/retrieval.py`、`app/services/retrieval/{errors,lexical_text,dense,lexical,hybrid}.py`、`app/repositories/retrieval.py`、`migrations/versions/*_document_chunk_fts_builder.py`、验证脚本及单元/集成/Smoke测试。
- 调用链：内部调用者 → Retrieval Schema → Hybrid Service → Dense + Lexical → EmbeddingProvider/Repository → Model → PostgreSQL FTS/pgvector → RRF安全结果；本阶段不经过前端、HTTP检索API、Reranker、Qwen、Evidence或Agent。
- 验证：两路检索在排序和`LIMIT`前使用同一获权active集合；中文/英文/SKU、固定向量余弦顺序、稳定RRF、来源定位和分数分解通过；跨tenant/owner/market、旧版本、失败索引和软删除零泄露；Fake不冒充语义质量，真实BGE只由显式离线Smoke加载。
- 授权边界：M2-16方案已确认，但仍按M2-16.1至M2-16.7逐步开发、验证、记录和汇报；M2-16不包含下方M2-17 Reranker或更后步骤。

### M2-17｜实现 BGE-Reranker 与真实基准

- 状态：进行中；方案已确认，M2-17.1至M2-17.3已完成，等待M2-17.4模型下载与真实离线后端单独授权；已有Provider/Fake与安全Service，尚未实现真实后端或下载模型。
- 目标：对获权混合候选做二次精排，默认输出top 8；本阶段后部才允许在单独确认后显式下载Reranker。
- 预计文件：`app/services/retrieval/reranker.py`、`reranker_provider.py`、严格Schema/错误、Fake/真实Smoke、基准脚本和测试。
- 调用链：Hybrid Candidates → Reranker Service → Fake或本地BGE-Reranker → Final Candidates。
- 验证：Fake稳定、真实中英文相关性、模型/revision/设备记录、内存、受控失败、空候选、批量降级；输出必须是输入获权候选的严格子集，不得重新引入或篡改任何Chunk。

### M2-18｜实现 Context Builder、知识 Evidence 和引用验证

- 状态：已完成；阶段方案已确认，M2-18.1至M2-18.6均已逐步完成并验证。
- 目标：去重/邻块补全/Token预算，把最终 Chunk 转成 knowledge/user_file Evidence，并验证 `[E#]`。
- 预计文件：Evidence迁移、`app/schemas/evidence.py`、`app/services/evidence.py`、`app/services/retrieval/context.py`、测试。
- 调用链：Reranked Chunks → Context/Evidence Service → Model → PostgreSQL → Evidence。
- 验证：PDF页码、DOCX段/表、Sheet/单元格/行范围、Evidence外键、ACL读取、错位/编造引用拒绝、M1 database Evidence仍可读。

### M2-19｜实现并注册 `search_knowledge` Tool

- 目标：通过 Harness 调用混合检索、Reranker、Context 和 Evidence，返回严格 ToolEnvelope。
- 预计文件：`app/schemas/knowledge.py`、`app/tools/search_knowledge.py`、Registry/Permission扩展、Tool测试。
- 调用链：Schema → Harness → Tool → Retrieval/Evidence Service → PostgreSQL/pgvector。
- 验证：成功、无答案、越权、预算、超时、错误脱敏、ToolCall与Evidence关联；Registry累计5个V1已实现Tool中的3个M2工具逐步加入。

### M2-20｜实现 `read_uploaded_file` 与 `get_evidence_detail` Tool

- 目标：按 file_id/locator 有界读取解析产物，并把现有 Evidence 详情能力纳入 Agent Tool 白名单。
- 预计文件：`app/tools/read_uploaded_file.py`、`get_evidence_detail.py`、对应Schema、Registry、Service和测试。
- 调用链：Schema → Harness → Tool → File/Evidence Service → Storage/PostgreSQL。
- 验证：owner/ACL、路径参数拒绝、长度上限、页/Sheet范围、删除后不可读、跨tenant/market统一安全错误、无原路径/Storage key泄露。

### M2-21｜新增有界知识路由、LangGraph 和基于 Evidence 的回答

- 目标：保留 M1 库存图，增加 knowledge_query 分支；Mock免费回归，Qwen只依据获权 Evidence 组织带引用回答。
- 预计文件：`app/agents/router.py`、`app/agents/graphs/knowledge_query.py`、`app/llm/provider.py`及Schema、聊天API扩展、测试。
- 调用链：API → Router/LangGraph → Provider建议 → Harness/Tool → Retrieval/Evidence → Mock/Qwen → 引用验证 → 回答。
- 验证：库存问题仍走M1、知识问题只开放知识Tool、无答案拒答、Prompt注入文档只当数据、引用合法、模型/Tool预算、Qwen付费 Smoke默认跳过。

### M2-22｜建立最小 RAG 评估集和 Runner

- 目标：复用 `m2-v1` 普通语料与 `m2-complex-v1` 复杂语料建立约20条最小样本，分别记录 Parser路由、Dense、Lexical、RRF、Reranker 和最终引用结果。
- 预计文件：`app/evals/rag_runner.py`、`data/evals/m2_rag_v1.jsonl`、期望定位、结果模板和测试。
- 调用链：Eval Runner → Retrieval各阶段 → Evidence/答案；不经过前端。
- 验证：普通/复杂文档分组的解析事实召回、路由准确性、Recall@5/@10、MRR、Citation Accuracy、无答案拒答、ACL阻断、多语言和版本过滤；保存代码、数据、Parser、Docling模型和检索参数版本。

### M2-23｜实现最小前端上传、状态、知识问答和引用展示

- 目标：在现有工作台增加附件、文件状态、知识回答和按来源类型展示的 Evidence 票据。
- 预计文件：`frontend/lib/api.ts`、`components/inventory-workbench.tsx`的受控拆分或扩展、knowledge/upload组件、CSS和组件测试。
- 调用链：前端 → Files/Chat/Evidence API → M2后端全链。
- 验证：选择/上传、状态、失败重试、知识问题、页码/Sheet引用、键盘/焦点、无权限和合成资料标识；TypeScript、ESLint、Build。

### M2-24｜完成故障矩阵、真实 BGE 演示、Chromium 回归和阶段收口

- 目标：从干净 M2 数据状态复现普通Native解析、复杂Docling解析、上传、索引、问答、引用、版本和越权，更新 README 与进度记录。
- 预计文件：后端集成测试、`frontend/e2e/*`、演示脚本、README、本文件和总看板。
- 调用链：Chromium/演示脚本 → 前端/API → Schema → Service → Parser/Embedding/Retrieval → Model → PostgreSQL/pgvector → Evidence。
- 验证：四格式、真实Docling、真实BGE、Mock/Qwen边界、普通/复杂路由、权限、损坏文件、重复索引、旧版本、软删除、模型/DB故障、M1全回归、无秘密和无残留服务。

## 8. M2 最终完成标准

M2 只有同时满足以下条件才能标记为“已完成”：

1. M2-01至M2-24均经用户逐步授权、完成并记录实际验证；
2. PostgreSQL 17 + pgvector 可重复启动，M1结构和125基线未丢失；
3. PDF、DOCX、XLSX、CSV 可以安全上传、解析、失败重试和软删除；
4. `m2-v1`普通语料与`m2-complex-v1`复杂语料均可重复生成；普通文件保持Native快速路径，指定复杂文件经安全检查后进入固定版本Docling，两路汇合为统一Canonical Artifact；
5. 前端和模型只使用 file/document/evidence ID，不接触绝对路径或 Storage key；
6. 文件、文档、版本、ACL、Chunk、FTS、向量和状态可由迁移从干净环境重建；
7. BGE-M3 真实生成1024维向量，模型版本与基准有记录；
8. Dense、Lexical、RRF、Reranker 四阶段结果可单独观察和评估；
9. 检索在 SQL 相似度计算前完成 tenant、ACL、active、ready 和 deleted 过滤；
10. 新版本失败不会替换旧 active，成功后原子切换；重新索引不产生重复 Chunk；
11. 三个 M2 Tool 均通过 Registry、PermissionGuard、Budget、Trace 和严格 Schema；
12. 知识问答无证据时拒答，有证据时引用能定位页码/标题/Sheet/范围；
13. M1 database Evidence 与 M2 knowledge/user_file Evidence 均能安全读取；
14. 最小评估集可复现，并分组报告普通/复杂解析、路由、Recall/MRR/Citation/ACL/拒答指标，不提前伪造目标值；
15. 最小前端能上传、看状态、提问、查看引用和错误；
16. 后端、前端组件、TypeScript、ESLint、Build 和 Chromium 端到端全部通过；
17. M1 175+1 skipped、4组件、4 E2E 基线不退化；
18. 真实 Docling、Qwen、BGE 模型文件、密码、Token、API Key、绝对路径和连接串没有进入 Git、日志或响应；
19. 没有提前实现 M3/M4/M5 或第5.2节非目标。

## 9. M2 能证明与不能证明什么

### 9.1 能证明

- 能自行实现一条不依赖 RAGFlow 的文档摄取、索引、混合检索、重排和引用链；
- 能把 PostgreSQL 业务数据库、pgvector、文档权限、版本和 Evidence 放在一致的事务与审计边界内；
- 能处理四种常见业务文件并保留适合用户核对的定位；
- 能区分文件二进制、本地解析产物、PostgreSQL元数据和向量的职责；
- 能通过自动评估比较 Dense、关键词、RRF 和 Reranker，而不是只凭主观感觉调参；
- 能证明跨租户、跨 owner、跨市场、旧版本、删除文档不会进入已覆盖的检索结果；
- 能在现有 M1 工作台中展示知识答案与 Evidence，而不破坏库存路径。

### 9.2 不能证明

- 不能证明解析所有扫描件、复杂排版、公式、图片、手写体和任意损坏办公文件；
- 不能证明合规内容构成真实法律、认证或经营建议；所有资料仍是合成演示；
- 不能证明大规模企业知识库、百万 Chunk、高并发、多机部署或云对象存储性能；
- 不能证明进程崩溃后索引任务自动恢复；M2没有持久 Worker；
- 不能证明真实 Qwen 对所有问法都忠实，严格 Schema 和引用验证只能降低风险；
- 不能证明 M3 图片、多模态相似SKU、M4联网研究/多Agent报告或M5完整作品化已经完成。

## 10. 主要风险与优先排查方向

| 风险/现象 | 影响 | 优先排查方向 |
|---|---|---|
| pgvector 镜像切换后数据库起不来 | M1/M2均阻塞 | 先核对 PostgreSQL major、数据目录权限、扩展镜像和命名卷；不删除卷 |
| 模型下载慢或失败 | 无法跑真实Embedding/Reranker | 核对模型ID/revision、缓存目录、代理和磁盘；Fake回归不受阻 |
| 16GB内存/4GB显存不足 | OOM或系统卡顿 | 减小batch、CPU运行、懒加载、顺序卸载；不要同时常驻两模型 |
| Docling/PyTorch安装或依赖冲突 | 复杂解析不可用或破坏现有模型边界 | 先做独立导入、`pip check`与真实基准；固定包/模型版本，不让单元测试隐式下载模型 |
| Docling在4GB显存OOM或单文件过慢 | 无法作为在线回退 | 先测CPU/GPU；GPU失败则CPU或离线索引，超过基准门槛不得接入同步请求 |
| PDF解析为空 | 无可索引文本 | 检查是否扫描PDF、加密或字体编码；安全文件可经质量门禁进入Docling OCR，危险文件仍直接拒绝 |
| Parser路由过度或漏判 | 普通文件变慢或复杂内容丢失 | 用`m2-v1`约束Native路径，用`m2-complex-v1`约束Docling路径，保存路由原因和三路对照结果 |
| Docling升级或输出结构漂移 | Artifact、Chunk和Evidence失稳 | 固定Docling/模型版本，只在Adapter内处理第三方结构，Canonical Schema独立版本化 |
| DOCX/XLSX解压异常 | ZIP bomb或内存激增 | 先检查压缩条目、总解压大小、行列上限和read-only模式 |
| CSV乱码或错列 | 引用和分析错误 | 检查BOM、UTF-8/GB18030、分隔符、引号和行范围 |
| 中文关键词召回差 | 型号/条款漏检 | 检查分词字段、数字/连字符归一化、Dense补偿和评估Bad Case |
| Dense相关但关键词不相关 | 融合排序不稳 | 分别查看两路rank、RRF参数和query改写，禁止只看最终答案 |
| 引用页码/Sheet错位 | 用户无法核验 | 检查解析定位→Chunk→Evidence的稳定ID链和邻块补全 |
| 权限越权 | 严重数据泄露 | 第一优先检查两路Repository SQL的tenant/ACL/active/deleted条件，不只改Prompt |
| 重复索引 | 数据膨胀、排名重复 | 检查内容hash、版本、embedding_version和唯一约束/事务 |
| 新版本失败导致旧文档消失 | 线上知识不可用 | 只在新版ready后原子切active，失败保留旧active |
| 软删除后仍可读 | 数据泄露 | 检查文件API、两路检索、Evidence读取和缓存都过滤deleted_at |
| Prompt注入文档影响Tool | 越权或错误执行 | 文档内容标记为不可信数据；知识图只开放当前1～3个只读Tool |
| Reranker让指标下降 | 精排模型或输入格式错误 | 保存重排前后排名，核对query/passages格式、长度截断和多语言样本 |
| 测试不稳定 | 难以回归 | 默认Fake模型、固定向量、固定合成文件、真实模型Smoke单独运行 |
| M1回归失败 | 范围扩展破坏既有能力 | 先定位ToolName/Evidence Schema/迁移兼容，不修改125业务公式掩盖问题 |
