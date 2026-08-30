# M2：知识库垂直切片详细实施方案

> 阶段状态：进行中
> 方案日期：2026-08-29
> 方案确认：2026-08-29，用户明确回复“确认M2方案，可以开始M2-01”
> 方案修订确认：2026-08-30，用户确认引入 Docling 作为复杂文档本地解析后端，保留现有 Parser 快速路径，并要求先更新文档再逐步实施
> M2-12方案确认：2026-08-30，用户明确回复“好的开始这一步”；M2-12.1与M2-12.2均已按单步规则完成
> 当前步骤：M2-12.2“PDF/DOCX文本结构单元与切块”已完成；停止并等待用户确认是否开始M2-12.3
> M1 代码基线：`main` / `94ad0eec837dfa618bb2e0c07e6a21769d690ebb`
> 数据性质：M2 文档、标准答案和评估数据必须是明确标注的版本化合成演示数据

> **当前停止点：M2-12.2已完成并验证；用户明确授权M2-12.3前，禁止实现表格切块、Chunk发布Service、数据库迁移、Embedding、索引、检索或RAG问答。**

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

## 7. 26 个正式步骤（M2-11细分为5个受控子步骤）

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

### M2-16｜实现权限前置的 Dense 检索

- 目标：查询向量后在 SQL 中先应用 tenant、ACL、active version、ready、deleted 过滤，再按余弦取 top-k。
- 预计文件：`app/repositories/retrieval.py`、`app/services/retrieval/dense.py`、集成测试。
- 调用链：Retrieval Service → Repository → pgvector。
- 验证：相关块排序、跨tenant/owner/market零泄露、旧版本/失败/删除块不出现、top-k和超时生效。

### M2-17｜实现中文友好的 Lexical 检索

- 目标：构建应用层中文分词后的 PostgreSQL FTS 查询，同时保留型号、条款号和数字精确能力。
- 预计文件：`app/services/retrieval/lexical.py`、Repository FTS 方法、分词配置和测试。
- 调用链：Query → Lexical Service → Repository → PostgreSQL FTS。
- 验证：中文短语、德法/英文、SKU/型号/条款号、权限过滤、停用词、无结果和 statement timeout。

### M2-18｜实现 RRF 混合检索

- 目标：合并 Dense/Lexical 名次、去重并保留两路排名和分数摘要。
- 预计文件：`app/services/retrieval/hybrid.py`、Schema、单元/集成测试。
- 调用链：Retrieval Service → Dense + Lexical → RRF。
- 验证：单路和双路命中、稳定排序、重复块、一路失败的安全策略、权限集合不扩大、参数可配置。

### M2-19｜实现 BGE-Reranker 与真实基准

- 目标：对获权混合候选做二次精排，输出 top 5～8；本步才显式下载 Reranker。
- 预计文件：`app/services/retrieval/reranker.py`、Fake/真实 Smoke、基准脚本和测试。
- 调用链：Hybrid Candidates → Reranker → Final Candidates。
- 验证：Fake稳定、真实中英文相关性、模型/revision/设备记录、内存、超时、空候选、批量降级；不得重新引入未授权块。

### M2-20｜实现 Context Builder、知识 Evidence 和引用验证

- 目标：去重/邻块补全/Token预算，把最终 Chunk 转成 knowledge/user_file Evidence，并验证 `[E#]`。
- 预计文件：Evidence迁移、`app/schemas/evidence.py`、`app/services/evidence.py`、`app/services/retrieval/context.py`、测试。
- 调用链：Reranked Chunks → Context/Evidence Service → Model → PostgreSQL → Evidence。
- 验证：PDF页码、DOCX段/表、Sheet/单元格/行范围、Evidence外键、ACL读取、错位/编造引用拒绝、M1 database Evidence仍可读。

### M2-21｜实现并注册 `search_knowledge` Tool

- 目标：通过 Harness 调用混合检索、Reranker、Context 和 Evidence，返回严格 ToolEnvelope。
- 预计文件：`app/schemas/knowledge.py`、`app/tools/search_knowledge.py`、Registry/Permission扩展、Tool测试。
- 调用链：Schema → Harness → Tool → Retrieval/Evidence Service → PostgreSQL/pgvector。
- 验证：成功、无答案、越权、预算、超时、错误脱敏、ToolCall与Evidence关联；Registry累计5个V1已实现Tool中的3个M2工具逐步加入。

### M2-22｜实现 `read_uploaded_file` 与 `get_evidence_detail` Tool

- 目标：按 file_id/locator 有界读取解析产物，并把现有 Evidence 详情能力纳入 Agent Tool 白名单。
- 预计文件：`app/tools/read_uploaded_file.py`、`get_evidence_detail.py`、对应Schema、Registry、Service和测试。
- 调用链：Schema → Harness → Tool → File/Evidence Service → Storage/PostgreSQL。
- 验证：owner/ACL、路径参数拒绝、长度上限、页/Sheet范围、删除后不可读、跨tenant/market统一安全错误、无原路径/Storage key泄露。

### M2-23｜新增有界知识路由、LangGraph 和基于 Evidence 的回答

- 目标：保留 M1 库存图，增加 knowledge_query 分支；Mock免费回归，Qwen只依据获权 Evidence 组织带引用回答。
- 预计文件：`app/agents/router.py`、`app/agents/graphs/knowledge_query.py`、`app/llm/provider.py`及Schema、聊天API扩展、测试。
- 调用链：API → Router/LangGraph → Provider建议 → Harness/Tool → Retrieval/Evidence → Mock/Qwen → 引用验证 → 回答。
- 验证：库存问题仍走M1、知识问题只开放知识Tool、无答案拒答、Prompt注入文档只当数据、引用合法、模型/Tool预算、Qwen付费 Smoke默认跳过。

### M2-24｜建立最小 RAG 评估集和 Runner

- 目标：复用 `m2-v1` 普通语料与 `m2-complex-v1` 复杂语料建立约20条最小样本，分别记录 Parser路由、Dense、Lexical、RRF、Reranker 和最终引用结果。
- 预计文件：`app/evals/rag_runner.py`、`data/evals/m2_rag_v1.jsonl`、期望定位、结果模板和测试。
- 调用链：Eval Runner → Retrieval各阶段 → Evidence/答案；不经过前端。
- 验证：普通/复杂文档分组的解析事实召回、路由准确性、Recall@5/@10、MRR、Citation Accuracy、无答案拒答、ACL阻断、多语言和版本过滤；保存代码、数据、Parser、Docling模型和检索参数版本。

### M2-25｜实现最小前端上传、状态、知识问答和引用展示

- 目标：在现有工作台增加附件、文件状态、知识回答和按来源类型展示的 Evidence 票据。
- 预计文件：`frontend/lib/api.ts`、`components/inventory-workbench.tsx`的受控拆分或扩展、knowledge/upload组件、CSS和组件测试。
- 调用链：前端 → Files/Chat/Evidence API → M2后端全链。
- 验证：选择/上传、状态、失败重试、知识问题、页码/Sheet引用、键盘/焦点、无权限和合成资料标识；TypeScript、ESLint、Build。

### M2-26｜完成故障矩阵、真实 BGE 演示、Chromium 回归和阶段收口

- 目标：从干净 M2 数据状态复现普通Native解析、复杂Docling解析、上传、索引、问答、引用、版本和越权，更新 README 与进度记录。
- 预计文件：后端集成测试、`frontend/e2e/*`、演示脚本、README、本文件和总看板。
- 调用链：Chromium/演示脚本 → 前端/API → Schema → Service → Parser/Embedding/Retrieval → Model → PostgreSQL/pgvector → Evidence。
- 验证：四格式、真实Docling、真实BGE、Mock/Qwen边界、普通/复杂路由、权限、损坏文件、重复索引、旧版本、软删除、模型/DB故障、M1全回归、无秘密和无残留服务。

## 8. M2 最终完成标准

M2 只有同时满足以下条件才能标记为“已完成”：

1. M2-01至M2-26均经用户逐步授权、完成并记录实际验证；
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

## 11. M2-PLAN-01 方案记录

**状态：已完成（阶段仍为待确认）**

**日期**

2026-08-29

**目标**

完整阅读项目规则、设计、M1记录和相关代码；只读核对 Git、环境、数据库、依赖和旧原型；恢复并验证 M1 基线；提交 M2 范围、架构、26个小步骤、验证、完成标准和风险。

**本次修改文件**

- `docs/progress/M2_KNOWLEDGE_RAG.md`：新建本阶段待确认方案与检查记录；
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
- `docs/progress/M2_KNOWLEDGE_RAG.md`、`docs/PROJECT_PROGRESS.md`：记录用户确认、本步事实、验证和新停止点。

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
- `main`是可用于真实模型运行的固定revision；配置只允许Fake默认使用它，真实BGE后端必须在M2-14/M2-19填写固定revision；
- 前端、API、Model、pgvector和Evidence链路已经增加M2能力。

**常见问题与优先排查方向**

- `.env`新增字段拼写错误或JSON数组格式错误：先用`Settings()`或定向测试检查，不要到上传API阶段才排查；
- 本地`.env`暂时没有M2键：当前安全默认值足以导入和运行M1；进入需要真实目录或真实BGE的步骤时只补对应键，不覆盖现有密码与API Key；
- 真实BGE配置被拒绝：必须提供固定模型revision，不能继续使用会漂移的`main`；
- 依赖安装很慢或磁盘增长：优先确认FlagEmbedding带来的PyTorch/Transformers/数据集传递依赖，按M2-14/M2-19分别安装与基准，不要把模型权重提交Git；
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
- `docs/progress/M2_KNOWLEDGE_RAG.md`、`docs/PROJECT_PROGRESS.md`：记录实施事实、验证、风险和新停止点。

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

## 18. M2-07 实施记录

### 2026-08-29｜M2-07｜实现文本型 PDF 解析器

**状态：已完成**

**本步解决的问题**

M2-06只能确认上传对象“看起来是PDF”并保存原始字节，还不能取得可供后续分块和引用的页文字。本步新增独立、确定性、资源有界的PyMuPDF解析器：从Storage提供的二进制流读取PDF，按物理页提取嵌入文字，保留从1开始的页码，提供基于字体大小的基础标题线索，并对空页、低文字页和疑似扫描图片页产生结构化警告。它明确不执行OCR，也不把底层库异常、路径或Storage Key带到输出。

**输入、输出和上下游**

- 输入：由受控Storage打开的二进制PDF流，以及集中Settings中的源大小、最大页数、最大提取字符数和低文字阈值；
- 输出：parser名称/版本、页数、每页文字、页码、字符数、图片数、标题线索和安全警告，或固定的损坏/加密/超限异常；
- 上游：M2-05/06获权文件边界和M2-03 `StorageBackend.open()`；测试实际使用LocalStorage流验证；
- 下游：M2-11解析调度与版本化JSON产物、M2-12结构感知分块；本步不接API、不写数据库状态。

**用大白话解释运行过程**

解析器像逐页翻书的录入员。它先确认整本书没有超过允许字节数和页数，再一页一页读取PDF里原本就存在的文字层。每页输出自己的页码和文字，不把第三页的内容算到第二页；字体明显大于正文的短行只标成“可能是标题”，不假装百分之百理解版面。如果某页是空白，会标记空页；文字很少会标记低文字；如果同时主要是一张图片，就提示“疑似扫描页，M2不做OCR”。

损坏、加密或超限时，解析器不会返回已经处理到一半的页面，也不会把PyMuPDF错误或本机路径抛给上层，只给固定安全错误。后续M2-11才负责把这些结果保存为版本化JSON并更新数据库状态。

**解析合同与边界**

- `PdfParseResult`严格包含`parser_name=pymupdf`、包含引擎版本的parser版本、`source_type=pdf`、完整连续页序列和警告；
- `PdfPageText`保存1开始的`page_number`、规范化文本、非空白字符数、图片数、低文字标记和该页标题线索；字符数必须与实际文本一致；
- `PdfHeadingHint`使用全篇主要正文字号作为基线，字号至少大20%且短于200字符的文本行才作为线索；不同字号映射为1至6级。这只是线索，不是复杂版面语义承诺；
- 空白页返回`empty_page`；少量嵌入文字返回`low_text_page`；低文字且含图片返回`scanned_page_suspected`，消息明确不执行OCR；
- `DocumentParseError`、`DocumentEncryptedError`和`DocumentLimitError`只包含固定中文安全消息；
- 默认最大源字节复用25MiB上传上限、最多500页、最多500万提取字符、低文字阈值20个非空白字符；集中配置可以在安全范围内调整；
- 读取按1MiB分块并在超过源上限后立即终止；页数在提取前检查，总字符在逐页处理时检查，超限不返回部分结果；
- 不做图片内容识别、OCR、表格重建、公式/手写体识别、页眉页脚消歧或复杂多栏阅读顺序恢复。

**PDF技能与夹具验证**

- 按PDF技能使用ReportLab生成可重复的两页文本层级加一页空白夹具，并生成一页图片型扫描夹具；测试夹具代码只含明确标记的合成内容；
- 当前环境没有Poppler的`pdftoppm/pdfinfo`，也未在Codex随附运行时找到。为避免擅自安装系统级软件，使用本步固定版本PyMuPDF将夹具逐页渲染为PNG并实际目视检查；
- 视觉检查确认第一页20pt主标题和正文、第二页16pt章节标题和正文、第三页完全空白，扫描夹具的文字只存在于图片中；没有裁切、重叠、黑块或不可读内容；
- 按技能要求，检查完成后已删除`tmp/pdfs/`中的6个临时PDF/PNG，仓库只保留可重复生成夹具的测试代码。

**修改文件与职责**

- `app/services/documents/parsers/base.py`：通用Parser协议、页定位、结构化警告和安全解析异常；
- `app/services/documents/parsers/pdf.py`：PyMuPDF有界读取、逐页文字、图片计数、标题线索、扫描警告和Settings构造入口；
- `app/services/documents/parsers/__init__.py`：冻结M2-07公共Parser导入边界；
- `app/core/config.py`、`.env.example`：新增PDF最大页数、最大提取字符数和低文字阈值；源字节上限复用上传配置；
- `tests/fixtures/pdf_factory.py`：用ReportLab/Pillow生成文本、空白、低文字、图片扫描和加密合成PDF；
- `tests/unit/test_pdf_parser.py`：验证页码、文字、标题、警告、损坏/加密、三类超限、异常脱敏、确定性和LocalStorage流；
- `tests/unit/test_m2_baseline.py`：验证新增配置、ReportLab开发依赖和M2-07停止线，继续禁止DOCX/XLSX/CSV Parser与Retrieval；
- `requirements-dev.txt`：声明仅用于可重复测试夹具生成的ReportLab；PyMuPDF已在M2-01运行依赖中声明，本步首次安装；
- `README.md`、本文件和`docs/PROJECT_PROGRESS.md`：同步当前能力、验证事实和下一停止点。

**调用链位置**

```text
前端（未经过）
→ API（未新增解析/索引入口）
→ Schema（Parser内部严格输出合同）
→ File Service授权边界（复用，未新增调度）
→ Storage.open（复用并在测试中实际接线）
→ PDF Parser（本步）
→ 逐页文字 / 页码 / 标题线索 / 警告（本步输出）
→ Model / PostgreSQL / pgvector / Evidence（均未经过）
```

**验证方法与实际结果**

1. `tests/unit/test_pdf_parser.py`共11项通过：两页文本加空页的页序列、文字、20pt/16pt标题层级、空页定位、低文字警告和图片扫描警告符合合同；扫描页图片中的文字没有被伪装成OCR结果；
2. 损坏PDF和读取流异常统一为`文档解析失败`，加密PDF为明确安全错误，测试中的私有路径、API Key标记和测试密码均未进入异常；
3. 源字节、页数和总提取字符三类上限分别触发`DocumentLimitError`且不返回部分页面；非法Parser构造参数和非法Settings值被拒绝；
4. 同一PDF重复解析结果完全一致；输出不含Storage Key、路径、tenant或SQL；真实LocalStorage `put → open → PdfParser`链路成功提取3页；
5. 解析器、M2配置和LocalStorage聚焦回归60项通过、2项Windows真实符号链接权限测试按设计跳过；
6. 后端全量确定性回归281项通过、3项按设计跳过，其中包括1项真实Qwen付费冒烟和2项Windows真实符号链接测试；未调用真实Qwen；
7. Ruff通过；Mypy严格检查5个解析器/配置/夹具源文件通过，对PyMuPDF和ReportLab不完整类型声明使用精确错误码忽略；PDF模块编译与公共导入通过；
8. PyMuPDF 1.28.2、ReportLab 4.5.1和Pillow 12.3.0安装成功，`pip check`通过；没有安装FlagEmbedding、下载BGE模型或调用互联网模型；
9. Alembic仍为`20260829_0004 (head)`，PostgreSQL保持healthy，M2四张表最终0行，M1 DE-FRA可售库存仍为125；
10. 高可信秘密扫描和`git diff --check`通过；未新增API、迁移、Document调度、解析产物、Chunk、Embedding、Retrieval、Evidence或前端，未提交或推送Git。

**能够证明**

- 文本型PDF的嵌入文字能够按物理页稳定提取，并给后续引用提供正确的1开始页码；
- 基础字号层级可以产生可解释、可复现的标题线索，同时没有把它描述成完整语义版面理解；
- 空白、低文字和图片型扫描页能够被区分并给出明确警告，扫描图片内容不会偷偷进入文本结果；
- 损坏、加密、源大小、页数、字符数和底层流异常都有安全、有界且不泄露的失败行为；
- Parser只需要受控二进制流，不需要也不会接触本地绝对路径、Storage Key、tenant、数据库或模型；
- 本步不需要数据库迁移，并且没有破坏现有M1/M2后端回归和库存答案125。

**不能证明**

- 所有PDF都能正确恢复阅读顺序；复杂多栏、浮动文本、特殊字体编码、公式和跨页表格仍可能需要增强；
- 扫描页中的图片文字已经被识别；M2-07明确不做OCR，图片理解仍属于M3；
- 标题线索一定等于作者真实标题层级；当前只是字号启发式，后续分块必须允许没有标题或修正层级；
- 上传后会自动运行解析器、更新`parse_status`或保存解析JSON；这些是M2-11解析调度职责；
- DOCX、XLSX和CSV已经能解析；它们分别属于M2-08和M2-09；
- Poppler渲染与PyMuPDF渲染在所有复杂PDF上完全一致；当前视觉检查使用PyMuPDF回退，因为本机没有Poppler；
- 恶意PDF解析具有进程级CPU/内存硬隔离或超时终止；当前提供输入/页/文字上限，生产级沙箱或独立Worker仍是后续增强。

**常见问题与优先排查方向**

- 返回“文档解析失败”：先确认对象确实是完整PDF且Storage读取正常；不要把PyMuPDF原始异常直接返回客户端；
- 返回“文档已加密”：需要用户上传未加密副本，M2不保存或猜测PDF密码；
- 返回“超过解析安全限制”：检查源字节、页数和提取字符配置，先判断文档是否合理，不要无条件把上限调到极大；
- 页面文字为空：检查是否为真实空页、扫描图片、字体编码或只有矢量图；有图片且低文字时应保留扫描警告，不要自动OCR；
- 页码错一页：确认后续始终使用Parser输出的1开始`page_number`，不要直接暴露PyMuPDF内部0开始索引；
- 标题识别过多或过少：优先检查正文字号样本、字号差异和文本长度；标题线索是启发式，不能作为唯一结构依据；
- PyMuPDF导入失败：确认项目虚拟环境安装了`requirements.txt`中的PyMuPDF，而不是旧的同名`fitz`包；
- 测试夹具无法生成：检查`requirements-dev.txt`中的ReportLab及其Pillow依赖，不要把二进制测试PDF手工改进Git。

**下一步**

停止并等待用户理解和确认。下一步应当是M2-08“实现DOCX解析器”；本次对M2-07的授权不包含M2-08。

## 19. M2-08实施记录（已完成）

**日期**：2026-08-29
**阶段**：M2知识库垂直切片
**步骤**：M2-08
**状态**：已完成
**目标**：实现独立、有界、确定性的DOCX解析器，保留标题层级、正文顺序、表格内容和稳定定位编号；不提前接入解析调度、数据库或检索。

**本步开始前缺少的能力**

- M2-06只能识别并保存DOCX，M2-07只解析PDF；Storage中的Word文件还不能变成结构化文字；
- 共用`SourceLocator`只有PDF页码，不能表达Word中的第几个正文块、段落、表格、行和列；
- 虽然`requirements.txt`已声明`python-docx`，当前虚拟环境尚未安装，也没有DOCX ZIP展开保护和合成测试夹具；
- 后续分块与Evidence需要标题路径和稳定原文位置，但本步开始前没有可复用合同。

**输入、输出和上下游**

- 输入：`StorageBackend.open()`返回的只读二进制流；Parser不接收本地路径、Storage Key、tenant或数据库连接；
- 输出：严格`DocxParseResult`，包含parser版本、正文块序列、段落/表格/单元格数量、非空白字符数、标题路径、定位器和安全警告；
- 上游：M2-03 Storage与M2-06文件格式门禁；本步只复用其流接口，不改上传API；
- 下游：M2-11解析调度和版本化JSON产物、M2-12结构感知分块；本步不调用它们。

**用大白话解释运行过程**

解析器像沿着Word正文从上往下抄录的录入员。它先看压缩包的“目录清单”，确认里面没有太多文件、没有异常大的展开体积、没有离谱压缩比，也没有`..`这类危险名字；整个过程不把文件解压到磁盘。通过门禁后，它才让`python-docx`打开文档。

正文中的标题、普通段落和表格按出现顺序统一编号。标题会维护一条层级路径，例如“产品指南 → 安全 → 清洁”；标题后的普通段落和表格都继承当时的路径。每张表、每一行、每个单元格再获得从1开始的编号。空段落也保留在正文顺序中，避免后续位置悄悄前移；整份文档没有任何可提取文字时返回明确警告。

任何损坏、危险、加密或超限输入都不会返回半份结果，也不会暴露ZIP、XML、本机路径或第三方库异常。图片仍保存在原始DOCX中，但解析器不读取图片文字或理解图片。

**解析合同与安全边界**

- `DocxParseResult.blocks`是带`kind`区分的段落/表格联合类型，`block_number`必须形成完整的1开始序列；段落号和表格号也必须各自连续；
- `DocxParagraphBlock`保存文字、Word样式名、1至9级标题层级、当前标题路径和段落定位；包括有意保留的空段落；
- `DocxTableBlock`保留正文中的位置、表格编号、标题路径、行和单元格；每个单元格包含表/行/列定位；
- Pydantic交叉校验保证声明数量、实际列表、字符数、块/段/表/行/列序列以及Locator互相一致，未知字段仍被拒绝；
- 默认限制为25MiB源文件、5000个ZIP成员、100MiB总展开量、200倍最大压缩比、50000个正文块、200000个表格单元格和500万非空白字符；Settings只允许在固定安全范围内调整；
- ZIP门禁在`python-docx`加载前检查必要OOXML成员、重复/绝对/反斜杠/穿越成员名、加密标记、负数或零压缩异常、总展开量和压缩比；不调用`extract`；
- 损坏DOCX或底层流错误统一为`文档解析失败`，加密为`文档已加密，无法解析`，资源超限为`文档超过解析安全限制`；
- 只读取正文顶层段落和表格；不执行宏、不联网、不解析图片、不OCR，也不承诺文本框、页眉页脚、脚注、批注、修订记录或嵌入对象的完整语义。

**修改文件与职责**

- `app/services/documents/parsers/docx.py`：DOCX ZIP门禁、标题识别、正文顺序、段落/表格模型、稳定定位、资源上限和安全异常映射；
- `app/services/documents/parsers/base.py`：扩展通用Locator的块、段、表、行、列和标题路径，并新增空文档警告；PDF页定位保持兼容；
- `app/services/documents/parsers/__init__.py`：导出M2-08公共DOCX Parser和结果类型；
- `app/core/config.py`、`.env.example`：新增DOCX成员数、展开量、压缩比、正文块、单元格和提取字符上限；
- `tests/fixtures/docx_factory.py`：使用明确`compact_reference_guide`版式生成标题、正文、两张表格、空段落、空文档、压缩负载和危险成员合成DOCX；不提交二进制夹具；
- `tests/unit/test_docx_parser.py`：验证标题路径、正文顺序、多表格、空文档、损坏/危险ZIP、七类资源上限、压缩炸弹、异常脱敏、配置、确定性、Locator和LocalStorage流；同时审计DOCX页面与表格OOXML几何；
- `tests/unit/test_pdf_parser.py`：因通用Locator新增`heading_path`字段，将“无内部路径”断言收窄为真实的本地/文件系统路径字段，PDF行为未改变；
- `tests/unit/test_m2_baseline.py`：验证新增配置，将停止线推进到M2-08，继续禁止XLSX/CSV Parser和Retrieval；
- `README.md`：记录稳定的本地运行、配置和Parser使用方法，不承担里程碑进度看板职责；
- 本文件和`docs/PROJECT_PROGRESS.md`：记录当前步骤、验证事实和下一停止点。

**调用链位置**

```text
前端（未经过）
→ API（未新增解析/索引入口）
→ Schema（Parser内部严格结果合同）
→ File Service授权边界（复用，未新增调度）
→ Storage.open（复用并在测试中实际接线）
→ DOCX ZIP安全门禁（本步）
→ python-docx Parser（本步）
→ 标题路径 / 段落 / 表格 / 稳定定位（本步输出）
→ Chunk / Embedding / Retrieval / Model / PostgreSQL / pgvector / Evidence（均未经过）
```

**验证方法与实际结果**

1. `tests/unit/test_docx_parser.py`共18项通过：标题1至3级路径、普通/空段落、两张表格、10个单元格和块/段/表/行/列1开始编号符合合同；
2. 空DOCX返回`empty_document`而不是伪造正文；损坏ZIP、危险成员和流错误统一脱敏，测试私有路径/API Key标记未进入异常；
3. 源字节、ZIP成员数、总展开量、压缩比、正文块、表格单元格和总字符七类上限均触发安全`DocumentLimitError`且不返回部分结果；1MiB高压缩负载在`python-docx`加载前被拒绝；
4. 同一DOCX重复解析结果完全一致，输出不含Storage Key、本地路径、tenant或SQL；真实LocalStorage `put → open → DocxParser`成功；
5. `compact_reference_guide`合成夹具的Letter页面、1英寸边距、字体/行距、9360 DXA表宽、120 DXA表缩进、2700/6660 DXA列宽和单元格宽度通过可重复结构审计；
6. 按`documents`技能调用官方`render_docx.py`时，当前虚拟环境缺少其`pdf2image`运行依赖；进一步确认本机也没有LibreOffice/`soffice`和Poppler。因此按技能明确降级规则没有声称视觉渲染通过，只保留第5项结构审计事实；临时37250字节DOCX已安全删除；
7. 后端全量确定性回归305项通过、3项按设计跳过，其中包括1项真实Qwen付费冒烟和2项Windows真实符号链接测试；未调用真实Qwen；
8. 当前M1/M2代码范围`app + migrations + scripts + tests`的Ruff通过；Mypy严格检查4个解析器/配置核心文件通过；编译、公共导入和`pip check`通过；
9. 额外仓库全目录Ruff发现旧版根目录`agent/api/tools/utils`的98项既有问题；这些文件不属于当前新架构和M2-08范围，本步按“不顺手重构M1/遗留原型”约束未修改；
10. PostgreSQL保持healthy，Alembic仍为`20260829_0004 (head)`，M2四张表最终0行；全量测试后重新运行M1 Seed并用SQL确认DE-FRA可售库存仍为125；
11. 已安装运行声明中已有的`python-docx 1.2.0`及其`lxml 6.1.2`依赖，未安装FlagEmbedding、下载BGE模型、创建迁移、调用互联网模型、提交或推送Git。

**能够证明**

- 合成DOCX中的标题、正文、空段落和多张表格能够按正文顺序稳定提取，标题路径与1开始定位可供后续分块引用；
- ZIP成员、展开量、压缩比和解析结果大小都有实际执行的资源门禁，常见损坏、穿越和压缩炸弹样本不会进入无界解析；
- Parser只依赖受控二进制流，不接触磁盘路径、Storage Key、tenant、数据库、模型或网络；
- 共用Locator扩展没有破坏PDF解析回归，M2-08不需要数据库迁移，也没有破坏M1库存答案125；
- 合成DOCX的结构与明确版式参数一致。

**不能证明**

- DOCX在Word或LibreOffice中的最终视觉版式已经通过PNG目视门禁；当前机器缺少所需渲染器，只有结构审计通过；
- 所有真实世界Word文件都能完美恢复阅读顺序；文本框、浮动形状、SmartArt、页眉页脚、脚注、批注、修订、嵌入对象和复杂合并单元格仍可能需要增强；
- 图片中的文字已经提取或图片内容已经理解；这些不属于M2文本边界，图片理解属于M3；
- 上传后会自动解析、更新数据库状态、保存JSON、分块、Embedding、检索或生成Evidence；这些分别属于M2-11及后续步骤；
- XLSX和CSV已经能解析；它们属于M2-09；
- 当前进程内资源限制等同于生产级CPU/内存沙箱；真正不可信文档仍可在后续部署中增加独立Worker、超时和系统级隔离；
- 整个历史仓库的旧原型代码已经通过Ruff；本步只证明当前M1/M2新代码范围通过。

**常见问题与优先排查方向**

- 返回“文档解析失败”：先确认文件确实是完整DOCX ZIP、包含必要OOXML成员且Storage流可从开头读取；不要把XML/ZIP底层异常直接返回用户；
- 返回“文档已加密”：让用户上传未加密副本；M2不保存、猜测或破解密码；
- 返回“超过解析安全限制”：依次检查源大小、ZIP成员数、总展开量、最大压缩比、正文块、单元格和字符配置，不要直接把全部上限调大；
- 标题路径不正确：检查Word段落是否真正使用Heading 1至Heading 9或带outline level的样式，而不是只把普通正文加粗放大；
- 表格单元格重复：优先检查源文件是否有合并单元格；`python-docx`按表格网格访问时可能为合并区域返回重复文本，后续分块需显式决定去重策略；
- 正文缺少文字：检查内容是否实际位于文本框、页眉页脚、批注、修订删除区或图片中；M2-08只读取正文顶层段落和表格；
- `python-docx`导入失败：在项目虚拟环境安装`requirements.txt`声明的1.2系列，不要安装同名无关包；
- 需要视觉渲染：安装受控版本LibreOffice/soffice、Poppler和官方渲染脚本依赖后重新执行PNG逐页检查；在完成前不得把结构审计表述成视觉通过。

**用户评审后的文档职责修正**

- 用户指出README不应重复维护M2步骤进度。已将README顶部改回项目名称，移除M2-01至M2-08完成范围、步骤编号、“本步”和“下一步”等进度性表述；
- README保留仍然有用的配置、启动、API和独立Parser使用方法；正式总进度只维护在`docs/PROJECT_PROGRESS.md`，M2详细记录只维护在本文件；
- 本次只是文档职责修正，没有改变M2-08代码或验证结论，也没有开始M2-09。

**下一步**

停止并等待用户理解和确认。下一步应当是M2-09“实现XLSX/CSV解析器”；本次对M2-08的授权不包含M2-09。

## 20. M2-09实施记录（已完成）

**日期**：2026-08-29
**阶段**：M2知识库垂直切片
**步骤**：M2-09
**状态**：已完成
**目标**：实现独立、有界、确定性的XLSX和CSV解析器，保留Sheet、表头、物理行、单元格或行范围、编码和分隔符信息；不写商品、仓库或库存业务表，不提前接入解析调度或RAG链路。

**本步开始前缺少的能力**

- M2-06只能识别、保存和下载XLSX/CSV；Storage中的表格文件还不能变成后续分块可使用的结构化文字；
- 共用`SourceLocator`不能表达Sheet名、单元格范围或连续行范围，后续Evidence无法稳定指出“哪张表、哪一行、哪个单元格”；
- XLSX公式的边界尚未冻结：系统必须保存公式文本，只能读取文件已有缓存值，绝不能在服务端执行公式或编造计算结果；
- CSV还没有明确编码和分隔符策略，也没有大表、异常ZIP、空行与底层异常的资源和脱敏边界；
- `requirements.txt`虽已按M2-01正式方案声明openpyxl与Pandas，但本步开始时当前虚拟环境尚未安装这两项运行依赖。

**输入、输出和上下游**

- 输入：`StorageBackend.open()`返回的只读XLSX/CSV二进制流，以及集中Settings中的源文件、ZIP展开、Sheet、行、列、单元格和字符上限；
- XLSX输出：parser及引擎版本、按工作簿顺序排列的Sheet、可见状态、首个非空表头行、完整物理行、单元格类型/坐标/值、公式文本、文件已有缓存值、字符统计和空Sheet警告；
- CSV输出：parser及引擎版本、实际识别编码和分隔符、首个非空表头行、包含空行的逻辑行、行范围、字符统计和空CSV警告；
- 上游：M2-03 Storage与M2-06上传格式门禁；本步在测试中实际接通LocalStorage二进制流；
- 下游：M2-11解析调度和版本化JSON产物、M2-12结构感知分块；本步只定义和验证Parser输出，不调用下游。

**用大白话解释运行过程**

XLSX解析器像一个只读表格抄录员。它先检查Excel压缩包目录，确认里面没有危险路径、重复文件、异常大的展开体积或离谱压缩比，然后用openpyxl以只读模式打开两次：一次看原始公式，一次只看文件自己保存的计算缓存。比如`E2`写着`=C2*D2`，解析器会保留这段公式；如果上传文件没有缓存结果，就明确返回空值，不会偷偷算出一个数字。随后它按原顺序记录每张Sheet、每个物理行和每个单元格，空行也不会被挤掉。

CSV解析器先按固定顺序尝试UTF-8 BOM、严格UTF-8和GB18030，再只从逗号、分号、Tab和竖线中识别分隔符。Pandas负责遵守引号和逻辑行规则，例如引号里的分号不会被误拆成新列。第一条非空行只作为“表头线索”保留，原始行本身仍留在结果中；它不会把CSV当成库存导入文件写进业务表。

两种解析器遇到损坏、危险或超限文件都不会返回半份结果，也不会把本机路径、Storage Key或第三方库错误暴露给调用方。

**解析合同与安全边界**

- `XlsxParseResult`、`XlsxSheet`、`XlsxRow`和`XlsxCell`通过Pydantic交叉校验Sheet/行/列的1开始连续编号、行列形状、计数、表头、公式统计、字符统计与Locator一致性；
- XLSX保留Sheet顺序和`visible/hidden/veryHidden`状态；首个非空物理行提供表头线索，行Locator保存`sheet_name + A行:末列行 + row_start/row_end`，单元格Locator保存Sheet名和精确坐标；
- XLSX公式只保留以`=`开始的公式文本，并通过`data_only=True`读取上传文件已有缓存；解析器不执行公式、不启用外部链接，也不把无缓存公式伪装成计算结果；
- XLSX默认限制为25MiB源文件、5000个ZIP成员、100MiB总展开量、200倍压缩比、100张Sheet、每Sheet 100000行、500列、总计500000个单元格和500万非空白字符；
- XLSX在openpyxl加载前检查必要OOXML成员、重复/绝对/反斜杠/穿越成员名、加密标记、异常压缩大小、总展开量和压缩比；不把ZIP展开到磁盘；
- `CsvParseResult`和`CsvRow`交叉校验完整的1开始逻辑行、列宽、非空行数、首个非空表头、字符数和`row_start/row_end`定位；
- CSV编码策略固定为UTF-8 BOM优先、严格UTF-8其次、严格GB18030最后；分隔符只允许逗号、分号、Tab和竖线，并有确定性的回退顺序；
- CSV默认限制为25MiB源文件、200000行、500列、总计500000个单元格和500万非空白字符；NUL字节、无法解码和结构错误统一安全失败；
- 所有Settings只能在代码规定的上限内调整；流读取按1MiB分块，超限立即停止；损坏或底层异常统一为`文档解析失败`，资源超限统一为`文档超过解析安全限制`；
- 两种格式都只做确定性文字/表格结构提取，不执行宏、外部链接或公式，不理解图片，不OCR，也不写商品、仓库、库存或其他业务表。

**修改文件与职责**

- `app/services/documents/parsers/xlsx.py`：XLSX ZIP门禁、双只读工作簿、Sheet/行/单元格结构、公式与缓存值边界、稳定定位、资源上限和安全异常；
- `app/services/documents/parsers/csv.py`：CSV编码与分隔符识别、Pandas逻辑行读取、空行/表头/行范围、资源上限和安全异常；
- `app/services/documents/parsers/base.py`：扩展通用Locator的Sheet名、单元格范围与行范围，并新增空Sheet和空CSV警告；PDF/DOCX定位保持兼容；
- `app/services/documents/parsers/__init__.py`：导出M2-09公共Parser和结果模型；
- `app/core/config.py`、`.env.example`：新增XLSX和CSV集中资源限制；不加入任何秘密值；
- `tests/fixtures/spreadsheet_factory.py`：内存生成多Sheet、公式、空行、日期、危险/压缩/超大维度XLSX，以及UTF-8-SIG、GB18030、逗号/分号/Tab CSV；只含明确合成内容，不提交二进制夹具；
- `tests/unit/test_xlsx_parser.py`：验证XLSX结构、公式边界、空Sheet、危险ZIP、九类上限、确定性、脱敏和LocalStorage流；
- `tests/unit/test_csv_parser.py`：验证编码、分隔符、引号、空行/空CSV、损坏输入、五类上限、确定性、脱敏和LocalStorage流；
- `tests/unit/test_m2_baseline.py`：验证新增配置与依赖声明，把停止线推进到M2-09并继续禁止Retrieval；
- `tests/unit/test_docx_parser.py`：同步共用Locator校验消息，DOCX行为未改变；
- 本文件和`docs/PROJECT_PROGRESS.md`：记录当前步骤、验证事实与下一停止点；README不再承担步骤进度记录职责，本步未修改README。

`requirements.txt`中的openpyxl 3.1系列和Pandas 3系列声明来自已确认的M2-01依赖边界，本步没有重复改写声明；本步只在现有`.venv`安装其锁定范围内版本以实际运行解析验证，没有下载任何模型。

**调用链位置**

```text
前端（未经过）
→ API（未新增解析或索引入口）
→ Schema（Parser内部严格结果合同，本步扩展Locator）
→ File Service授权边界（复用，未新增解析调度）
→ Storage.open（复用，并在测试中实际接线）
→ XLSX：ZIP门禁 → openpyxl只读解析（本步）
→ CSV：编码/分隔符门禁 → Pandas只读解析（本步）
→ Sheet / 表头 / 行 / 单元格或行范围（本步输出）
→ Parser调度 / Chunk / Embedding / Retrieval / Model / PostgreSQL / pgvector / Evidence（均未经过）
```

**验证方法与实际结果**

1. `tests/unit/test_xlsx_parser.py`共16项通过：三张Sheet顺序和隐藏状态、首个非空表头、空物理行、日期、精确单元格/行范围、空Sheet警告和LocalStorage流符合合同；
2. 两个合成公式均保留公式文本，因夹具没有缓存值而明确统计为2个无缓存公式，值保持`None`；测试证明解析器没有执行或编造公式结果；
3. XLSX损坏ZIP、危险成员、源字节、成员数、总展开量、压缩比、Sheet数、行、列、总单元格和字符限制均安全失败；压缩负载和伪造大维度在受控阶段被拒绝；
4. `tests/unit/test_csv_parser.py`共12项通过：UTF-8-SIG分号、严格UTF-8 Tab、GB18030逗号、带引号分隔符、空行、空CSV和行范围符合合同；
5. CSV结构错误、非法/不完整字节和NUL输入统一脱敏失败；源字节、行、列、总单元格与字符五类上限均触发安全错误；
6. 两种格式重复解析结果完全一致，输出不含Storage Key、本地路径、tenant或SQL；真实LocalStorage `put → open → Parser`链路分别通过；
7. 与PDF、DOCX、配置和停止线一起的聚焦回归94项通过；后端第二次全量回归345项通过、3项按既有条件跳过，未调用真实Qwen；
8. 第一次全量回归出现2项M1 Agent Tool集成断言失败，分别观察到测试开始前已有1条Evidence和3条AgentRun；全量结束后数据库运行表已为0，单独重跑该集成模块6项全部通过，再从干净状态重跑全量得到第7项结果，因此没有通过修改M1测试或代码掩盖问题；
9. M2-09相关文件Ruff通过；Mypy严格检查4个Parser/配置源文件通过；Parser与夹具编译通过，`pip check`报告无损坏依赖；
10. 当前`.venv`安装并实际使用openpyxl 3.1.5、Pandas 3.0.5及其必要小型依赖；未安装FlagEmbedding、下载BGE-M3/BGE-Reranker或调用互联网模型；
11. PostgreSQL保持healthy，Alembic为`20260829_0004 (head)`，M2四张文件/文档元数据表最终均为0行；全量测试后重新运行M1 Seed并用SQL确认DE-FRA关键可售库存仍为125；
12. `spreadsheets`技能要求的`load_workspace_dependencies/@oai/artifact-tool`在当前工具环境中不可用，因此没有声称完成该工具的工作簿渲染/视觉门禁。本步交付的是后端Parser而非用户工作簿；测试夹具按项目正式方案使用openpyxl在内存生成，并通过结构、内容和解析结果检查。

**能够证明**

- 合成XLSX中的多Sheet、隐藏状态、表头、空物理行、日期、公式文本和精确单元格/行范围能够稳定提取；
- 没有缓存值的公式不会被执行或伪造结果，公式与缓存值的来源边界明确；
- UTF-8-SIG、UTF-8和GB18030合成CSV，以及逗号、分号和Tab分隔符、引号字段和空行能够稳定提取；
- 两种解析器都有实际执行的输入、结构、解压和结果大小限制，常见损坏、危险ZIP、压缩负载、大维度和异常编码能够安全失败；
- Parser只依赖受控二进制流，不接触Storage Key、tenant、数据库、模型或网络；
- 共用Locator扩展没有破坏PDF/DOCX和M1/M2后端回归，M2-09不需要数据库迁移，也没有改变M1库存答案125。

**不能证明**

- 所有真实世界XLSX/CSV都能完美恢复业务语义；合并单元格、数据透视表、图表、批注、命名区域、外部链接、宏、超复杂日期/数字格式和损坏的缓存值仍可能需要增强；
- Excel公式已得到正确计算；本步故意不执行公式，只读取文件已有缓存值；
- XLSX中的图片、图表或扫描文字已经理解；M2只提取可读单元格文字，图片理解属于M3；
- CSV的第一条非空行一定是业务上的真实表头；当前只提供确定性表头线索，后续解析调度或分块必须允许修正；
- 上传后会自动选择解析器、保存版本化JSON、更新`parse_status`、分块、Embedding、检索或生成Evidence；这些属于M2-11及后续步骤；
- XLSX/CSV会写入商品、仓库或库存业务表；M2明确禁止这种写入；
- 已完成artifact-tool工作簿渲染或视觉检查；当前工具环境缺少该技能运行时，本步没有交付需要视觉验收的工作簿文件；
- 当前进程内上限等同于生产级CPU/内存沙箱；真正不可信大文件仍可在后续部署中增加独立Worker、超时和系统级隔离。

**常见问题与优先排查方向**

- XLSX返回“文档解析失败”：先检查上传对象是否为完整OOXML工作簿、必要ZIP成员是否存在、Storage流是否从开头读取，以及是否含危险成员；不要直接返回openpyxl/ZIP原始异常；
- XLSX返回“超过解析安全限制”：依次检查源大小、成员数、展开量、压缩比、Sheet、行、列、总单元格和字符配置，不要无条件放大所有上限；
- 公式有文本但值为空：优先检查原文件是否由Excel等程序保存了缓存计算结果；这是正常安全边界，不应在后端调用`eval`或自行计算；
- 行号或引用位置偏移：确认后续使用Parser输出的1开始物理行和单元格坐标，不要删除空物理行后重新编号；
- CSV中文乱码或解析失败：确认源文件是UTF-8/UTF-8-SIG/GB18030之一；其他编码当前应明确拒绝，而不是猜测后静默产生错误文本；
- CSV列数异常：检查引号是否闭合、文件实际分隔符是否属于支持集合，以及字段内部的分隔符是否正确加引号；
- CSV被误当库存导入：检查调用方是否绕过Parser边界直接写业务Repository；M2表格上传只用于知识解析和文件分析；
- `openpyxl`或`pandas`导入失败：确认使用项目`.venv`并安装`requirements.txt`，再运行`python -m pip check`；不要为此安装BGE模型依赖。

**下一步**

停止并等待用户理解和确认。下一步应当是M2-10“建立`m2-v1`合成知识文件和manifest”；本次对M2-09的授权不包含M2-10。

## 21. M2-10实施记录（已完成）

**日期：2026-08-29**
**状态：已完成**

**本步目标与解决的问题**

M2-07至M2-09已经分别能读PDF、DOCX、XLSX和CSV，但项目此前没有一套固定版本、可重复生成、带标准答案与标准定位的知识文件。这样一来，后续解析调度、分块、检索和Evidence即使运行成功，也缺少一份不会随手工编辑漂移的“统一考卷”。本步建立`m2-v1`合成知识语料、manifest和可重复Seed入口，把5份文件保存到LocalStorage，并只建立文件、文档、版本和ACL元数据基线。

**输入、输出和大白话运行过程**

- 输入：可审查的`m2_seed.json`定义、M1固定租户/用户/角色/SKU基线，以及M2-03至M2-05已经存在的Storage和文件/文档模型；
- 处理：脚本先保证M1 Seed存在，再按固定内容和固定元数据生成1份PDF、2份DOCX、1份XLSX和1份CSV，计算SHA-256和稳定UUID；随后把二进制写入LocalStorage，并用同一批稳定ID建立数据库记录；
- 输出：`m2_manifest.json`记录版本、分类声明、文件hash、页数/Sheet/行数、标准问题、标准答案和页码/段落/表格/单元格/行范围定位；PostgreSQL得到5个文件、5个文档、5个待解析版本和5条ACL；
- 幂等边界：再次运行会核对已有Storage对象和数据库字段，内容一致则复用，内容冲突则拒绝，不覆盖现有对象；新写Storage而后续失败时会补偿删除本次新对象；
- 状态边界：文件保持`uploaded`，版本保持`parse_status=pending`、`index_status=pending`，文档`active_version_id`为空。本步不伪装已经解析或索引。

**合成语料内容**

1. `m2-v1_蘑菇灯产品说明书.pdf`：2页，覆盖产品规格、220 V、电源安全和清洁要求；
2. `m2-v1_蘑菇灯质检SOP.docx`：标题结构、抽样规则和缺陷处置表；
3. `m2-v1_德国灯具合规演示清单.docx`：CE/RoHS/WEEE等演示检查项，并明确“不构成法律或认证意见”；
4. `m2-v1_蘑菇灯供应商报价.xlsx`：`供应商报价`和`报价说明`两个Sheet，包含3个保留但不执行的公式；
5. `m2-v1_蘑菇灯月度运营数据.csv`：DE/FR两市场12个月度数据行及明确合成声明，不写商品、仓库或库存业务表。

全部文件均标记为合成演示资料；合规内容明确不构成法律或认证意见。XLSX生成按用户在本步的明确确认，例外使用项目已声明的`openpyxl`；该例外只适用于这份合成Seed工作簿。

**修改文件与职责**

- `data/seed/m2_seed.json`：人类可审查的`m2-v1`内容、ACL、结构预期、标准问答和定位源定义；
- `scripts/m2_seed_content.py`：确定性生成PDF/DOCX/XLSX/CSV；固定文档元数据和OOXML时间，设置DOCX页面/表格几何与XLSX可读样式；
- `scripts/seed_m2_files.py`：校验定义、生成稳定ID/hash/Storage Key、保证M1前置、幂等写Storage和PostgreSQL、失败补偿并生成manifest；
- `data/seed/m2_manifest.json`：实际生成结果的版本化清单、hash、结构统计和黄金定位；不包含Storage Key、本地路径、密码、Token或API Key；
- `tests/integration/test_seed_m2_files.py`：验证确定性、真实Parser定位、文档/表格结构、空基线Seed、重复运行、状态、ACL、Storage冲突和M1守卫；
- `tests/unit/test_m2_baseline.py`：把阶段停止线推进到M2-10，明确M2-11解析调度与检索模块仍不存在；
- `docs/progress/M2_KNOWLEDGE_RAG.md`、`docs/PROJECT_PROGRESS.md`：记录实际结果和新的停止点；本步没有把进度写入README。

**完整调用链位置**

```text
开发数据入口：m2_seed.json
→ 合成文件生成器（本步）
→ M2 Seed Service脚本（本步）
→ LocalStorage + File/Document/Version/ACL Model（复用M2-03至M2-05）
→ PostgreSQL（本步写入元数据）

前端 → API → 对外Schema → Parser调度 → Chunk → Embedding → Retrieval
→ Model → pgvector检索 → Evidence
以上业务问答链均未经过；现有独立Parser只用于测试黄金定位，没有接入生产调度。
```

**验证方法与实际结果**

1. 跨2秒连续生成两轮，5份文件的字节和SHA-256全部一致；修复了`openpyxl`自动刷新XLSX内部修改时间导致hash漂移的问题，只规范化OOXML元数据，不改变业务内容；
2. PDF实际生成2页并用PyMuPDF渲染为两张页面图逐页检查，中文、标题、页码、正文和免责声明可见且无截断；PDF Parser确认220 V在第1页、清洁前拔插头在第2页；
3. 两份DOCX通过Parser与技能结构审计：标题计数分别为4和3，均为单节8.5×11英寸、四边1英寸；表格`tblW`、缩进、列网格和所有单元格宽度完全匹配，段落及表格黄金定位稳定；
4. 标准DOCX渲染器已实际调用，但当前机器缺少`pdf2image`，同时无LibreOffice/soffice，无法完成DOCX页面图视觉门禁；本步没有把结构审计描述成视觉验收；
5. XLSX通过Parser和`openpyxl`结构检查：两个非空Sheet、冻结首行、隐藏网格、固定列宽、3个公式文本、4/5行结构及黄金单元格定位稳定；当前环境缺少spreadsheets技能的artifact runtime，因此没有完成artifact-tool视觉门禁；
6. CSV确认UTF-8-SIG、逗号分隔、15个逻辑行、DE第7行与FR第8至13行定位稳定；
7. M2-10聚焦回归与停止线共40项通过；后端全量确定性回归348项通过、3项按既有条件跳过，未调用真实Qwen；
8. Seed在测试提供的空M2基线中能自动恢复M1前置并成功写入；重复运行manifest字节相同、行数不增加；冲突Storage对象会安全拒绝且不落文档记录；
9. 实际开发库连续Seed两次，manifest SHA-256保持一致；最终数据库为5个文件、5个文档、5个版本和5条ACL，状态为`uploaded/pending/pending`、active版本0个，5个Storage对象均与manifest hash一致；
10. M1守卫确认`LR-TL-MUSH-OR01`在`DE-FRA`可售库存仍为125；PostgreSQL容器healthy，Alembic为`20260829_0004 (head)`且`alembic check`无待生成迁移；
11. Ruff通过；Mypy严格检查3个M2-10源/测试文件通过；Python编译和`pip check`通过；
12. Git与敏感信息审计确认本步未写入秘密值、未提交或推送，且没有新增迁移、API、解析调度、分块、Embedding、检索、前端或M1重构。

**能够证明**

- 5份`m2-v1`合成知识文件可以从可审查定义稳定重建，跨运行hash、大小、页数、Sheet、行数和黄金定位不会因时间戳漂移；
- 从M2数据为空的环境可以补齐M1前置并建立Storage与知识元数据基线，重复执行不会重复追加或静默覆盖冲突文件；
- 现有四类独立Parser能够从这套固定语料提取预定事实和定位，为M2-11及后续检索评测提供统一“考卷”；
- Seed没有把表格内容写入M1商品、仓库或库存业务表，M1关键答案125保持；
- 文档被明确标记为合成演示资料，合规清单不会被包装成法律或认证意见。

**不能证明**

- 上传后已经自动解析、保存解析产物、更新状态或切换active版本；M2-11尚未实现；
- 已经分块、生成BGE-M3向量、写入pgvector、混合检索、重排、调用模型或生成Evidence；这些均是后续步骤；
- 5份小型合成文件代表所有真实供应商文档、复杂工作簿、扫描PDF或异常格式；
- DOCX已通过真实Office/LibreOffice页面渲染视觉验收，或XLSX已通过artifact-tool视觉验收；当前环境缺少相应运行时；
- 当前同步本地Seed等于生产级对象存储、备份、跨进程事务或灾难恢复方案。

**常见问题与优先排查方向**

- 重跑报告Storage对象冲突：先核对`m2_seed.json`版本、manifest hash和本地对象是否被手工修改；不要直接覆盖，若要换语料应发布新版本；
- manifest hash漂移：优先检查生成器是否引入当前时间、随机ID、未固定PDF元数据或OOXML内部时间；不要只固定ZIP外层时间戳；
- 数据库字段冲突：先检查同一稳定ID是否已有不同tenant、owner、标题、hash、ACL或状态；这通常说明基线被手工修改或版本策略错误；
- 黄金定位偏移：检查源定义中标题、空段、表格行列或CSV空行是否变化；定位变化必须同步发布新语料版本，不能只改预期答案；
- 中文字体或页面布局异常：PDF先检查ReportLab CID字体与A4固定布局；DOCX需在具备LibreOffice/Office的环境补做真实页面渲染；
- XLSX公式值为空：本步故意只保存公式文本，不执行公式；后续Parser不能自行`eval`；
- Seed后状态仍为pending：这是M2-10的正确停止线，解析和状态更新应由M2-11完成，不能在Seed脚本中伪造ready。

**下一步**

停止并等待用户理解和确认。下一步应当是M2-11“实现解析调度与版本化解析产物”；本次对M2-10的授权不包含M2-11。

## 22. 强制确认声明

**M2阶段状态为“进行中”，当前已完成M2-01至M2-10，并已记录M2-11修订方案。用户明确确认前，禁止开始M2-11.1；确认M2-11.1不自动授权M2-11.2至M2-11.5或任何后续正式步骤。**

## 23. M2-PLAN-02 Docling双路径解析修订方案记录

**状态：已完成（方案记录；运行代码待开始）**

**日期**

2026-08-30

**确认记录**

- 用户决定引入 Docling，Marker 与 LlamaParse 暂不考虑；
- 用户确认解析阶段采用双路径：普通文件优先使用现有 Native Parser，复杂安全文件使用 Docling；
- 用户明确复杂文件必须进入正式评估，而不是只做临时示例；
- 用户要求先更新进度文档，再按逐步确认规则实施；本次授权只覆盖文档修订，不等于已经授权生成语料、安装依赖或开发 M2-11.1。

**现状与缺少的能力**

- M2-07至M2-09已经实现 PyMuPDF、python-docx、openpyxl/Pandas 四类独立、有界、确定性 Parser；
- M2-10已经建立不可变的`m2-v1`普通合成语料：1份PDF、2份DOCX、1份XLSX和1份CSV，共10条黄金事实及定位；
- 当前Parser单元测试和`m2-v1`能证明普通合成文件、定位、安全限制和结果稳定性，但不能证明扫描件、多栏、复杂表格、图片文字或复杂Office布局；
- 当前虚拟环境为Python 3.11.9，尚未安装Docling或PyTorch；15.9GB内存和GTX 1650 Ti 4GB是否能稳定运行Docling尚未实际验证；
- 当前没有Canonical Parsed Artifact、解析质量门禁、Parser Router、Docling Adapter、解析调度、版本化解析产物或自动状态闭环。

**本次修订的目标**

只在解析摄取层建立可替换双路径：

```text
获权文件版本
→ 既有文件类型/大小/签名/压缩安全检查
→ Native Parser
→ Parse Quality Gate
   ├─ 普通且质量合格：保留Native结果
   └─ 复杂且安全：Docling本地增强解析
→ Canonical Parsed Artifact JSON
→ LocalStorage原子发布
→ document_versions.parse状态
```

Native与Docling只在解析阶段分支；分块、Embedding、Dense/Lexical/RRF、Reranker、Evidence和Agent仍由项目统一实现，不能形成两套RAG系统。Markdown可以作为Canonical Artifact派生视图，但不能替代包含页码、标题路径、Sheet、单元格、公式、警告和Parser版本的结构化底稿。

**明确不做**

- 不删除或重写现有四类Parser；
- 不修改`m2-v1`定义、已有生成文件、manifest、hash或黄金定位；
- 不允许加密、损坏、类型不符、ZIP Bomb或超限文件借Docling绕过安全门禁；
- 不引入Marker、LlamaParse、云解析API、MCP或真实业务文档；
- M2-11不实现Chunk、Embedding、pgvector业务表、检索、Reranker、Evidence、Agent、Prompt或前端；
- 不在普通单元测试或应用导入时隐式联网下载Docling模型。

**前置条件**

1. `m2-v1`继续作为Native普通文件回归基线；
2. 所有新增文档继续使用明确标注、可重复生成的合成演示内容；
3. Docling包、模型、OCR选项、设备和缓存目录必须在真实基准后固定；
4. 模型缓存只能进入被Git忽略的`data/model-cache`，不能写入源码或Storage原文件目录；
5. M2-11.5数据库集成验证前需要Docker Desktop/PostgreSQL可用；M2-11.1至M2-11.4不以数据库持续运行作为唯一前提；
6. 当前工作区仍包含M2-01至M2-10的未提交变更；如需Git检查点，必须由用户另行授权提交或推送。

### M2-11.1｜建立`m2-complex-v1`复杂文档正式评估集

**本步只解决的问题**

建立不会覆盖`m2-v1`的正式“复杂考卷”，为Docling可行性、路由、分块、检索和引用提供贯穿式黄金数据。

**输入与输出**

- 输入：M2合成产品/运营业务定义、现有文件生成器模式和SourceLocator合同；
- 输出：版本化复杂PDF/DOCX/XLSX、黄金问题/答案/定位、期望路由/OCR标记、manifest及幂等Seed；
- 上游：M2-03 Storage、M2-04/05知识元数据、M2-10可重复Seed模式；
- 下游：M2-11.2真实Docling基准、M2-11.4路由、M2-12分块和M2-24 RAG评估。

**计划语料**

1. 扫描PDF：文字只存在于页面图片，黄金事实固定到页码；
2. 双栏PDF：固定左右栏阅读顺序，包含重复页眉页脚；
3. 复杂表格PDF：包含合并表头或无边框业务表格；
4. 复杂DOCX：包含正文外视觉内容、图片文字、页眉页脚或文本框中的至少两类；
5. 复杂XLSX：包含多层合并表头、多个数据区域和公式；openpyxl仍保留单元格事实底稿，Docling只接受语义视图评估。

**预计文件**

- 新增：`data/seed/m2_complex_seed.json`、`data/seed/m2_complex_manifest.json`；
- 新增：复杂语料生成/Seed脚本，优先复用现有生成逻辑但保持`m2-v1`默认入口和输出不变；
- 新增或扩展：`tests/fixtures/pdf_factory.py`、`docx_factory.py`、`spreadsheet_factory.py`及复杂Seed集成测试；
- 修改：本文件和`docs/PROJECT_PROGRESS.md`记录实际结果。

**调用链位置**

```text
开发数据定义
→ 文件生成
→ LocalStorage
→ File/Document Model
→ PostgreSQL
```

不经过Parser Router、Docling、Chunk、Embedding、检索、Model或Agent。

**验证方式**

- 空目录两次生成的字节、SHA-256、页数、Sheet、行数和manifest一致；
- 每条黄金事实的答案确实存在于源定义，定位满足SourceLocator合同；
- 期望路由、OCR要求、复杂性标签和合成声明齐全；
- 重复Seed不增加行数，冲突对象拒绝，不覆盖现有对象；
- `m2-v1`现有5份文件、manifest字节和10条黄金事实保持不变；
- M1 Seed、库存125及既有Parser回归不退化。

**实际实施记录（2026-08-30，已完成）**

1. 本步解决了什么：新增独立且版本化的`m2-complex-v1`正式复杂文档评估集，没有修改或覆盖`m2-v1`；
2. 大白话运行过程：JSON先规定5份“复杂考卷”和10道标准题，生成器把它们稳定地做成PDF、DOCX和XLSX，Seed再把同一批二进制写入LocalStorage，并把文件、文档、版本和ACL写入PostgreSQL；重复执行只核对既有内容，不追加重复行；
3. 实际语料：2页图片扫描PDF、2页双栏/重复页眉页脚PDF、1页合并表头/无边框表格PDF、含页眉/页脚/图片文字的DOCX、含两层合并表头/两个数据区域/6个公式的XLSX；每份固定2条Golden，并记录`expected_route=docling`、`requires_ocr`和复杂性标签；
4. 新增文件与职责：
   - `data/seed/m2_complex_seed.json`：可人工审阅的合成业务事实、Golden、定位与路由预期；
   - `scripts/m2_complex_seed_content.py`：确定性生成3份PDF、1份DOCX和1份XLSX；
   - `scripts/seed_m2_complex_files.py`：校验定义、生成稳定UUID/哈希/Storage Key、构建manifest并幂等写入Storage/PostgreSQL；
   - `data/seed/m2_complex_manifest.json`：冻结5份源文件的SHA-256、结构、Golden、路由和OCR预期；
   - `tests/integration/test_seed_m2_complex_files.py`：验证确定性、复杂结构、Native能力差异、旧集不可变、冲突拒绝和数据库幂等；
5. 调用链位置：`开发数据定义 → 文件生成 → LocalStorage → StoredFile/Document/DocumentVersion/DocumentAcl Model → PostgreSQL`；本步没有经过前端、API、Schema、Parser Router、Docling、Chunk、Embedding、检索、模型或Agent；测试只旁路调用现有Native Parser，确认考题确实能暴露其能力边界；
6. 实际验证结果：
   - 复杂Seed聚焦集成测试`3 passed`，覆盖两次字节/SHA一致、10个Locator合同、Storage冲突拒绝及PostgreSQL重复Seed不增行；
   - 默认Seed连续执行两次后保持`5 files / 5 documents / 5 versions / 4 ACL`，M1德国仓可售库存仍为125；
   - 后端全量回归`351 passed, 3 skipped`；Ruff通过，两个新增脚本Mypy通过，`pip check`无破损依赖；
   - 3份PDF共5页通过逐页视觉检查；DOCX通过真实Microsoft Word导出的一页视觉检查；XLSX通过真实Microsoft Excel导出的两个工作表视觉检查，均无乱码、裁切或重叠；临时预览被移入已忽略的`output/m2_complex_qa/`，可按需复核；
   - 扫描PDF由PyMuPDF得到2个空文字页、每页1张图片和`scanned_page_suspected`；DOCX Native正文结果看不到页眉`QC-VISUAL-17`及图片`IMG-D17`；XLSX Native仍保留2个Sheet、14行、6个公式和精确单元格事实，证明三类目标难点成立；
   - 原`m2-v1`四个基线文件SHA-256保持不变：定义`D4D9E...F474`、manifest`3B522...5ECB`、生成器`5075A...97A2`、Seed脚本`3A4FB...AE14`；旧5份文件和10条Golden继续由回归测试约束；
7. 能证明：复杂评估集可重复生成、可追溯、可幂等入库，Golden与定位合同有效，并且样本真实触发扫描、阅读顺序、表格语义、正文外视觉内容和复杂表格结构；
8. 不能证明：Docling尚未安装或执行，因此不能证明OCR召回、Docling阅读顺序/表格质量、资源占用、最终路由和RAG答案质量；这些只属于M2-11.2及后续步骤；
9. 工具边界：技能自带`render_docx.py`因当前虚拟环境缺`pdf2image`且机器无Poppler未能运行；本机存在Microsoft Word，因此使用只读打开并导出PDF完成了等价的真实Word排版检查。电子表格`artifact-tool`运行时在当前会话不可用，因此没有声称通过该工具门禁；改用现有项目openpyxl结构/公式断言和真实Excel只读导出进行双重验证；
10. 常见问题与排查：若将来哈希漂移，先查固定ZIP时间、Office元数据和生成依赖版本；若Golden答不出，先区分“源文件生成错误”与“Docling未识别”；若重复Seed失败，先核对同一Storage Key的字节和数据库固定UUID行，不要覆盖冲突对象。

### M2-11.2｜固定Docling依赖并完成真实资源/质量基准

**本步只解决的问题**

在不接主链路的前提下，证明Docling在当前机器上能否稳定、可重复、资源可接受地改善指定复杂文件。

**预计文件**

- `requirements.txt`、`.env.example`、`app/core/config.py`；
- Docling真实基准脚本与默认跳过的Smoke测试；
- 本文件记录包/模型版本、缓存、CPU/GPU、OCR、耗时、峰值内存/显存和实际结果。

**调用链位置**

```text
Benchmark/Smoke
→ Docling本地Provider
→ m2-complex-v1
→ 基准结果
```

不经过API、数据库状态、索引或Agent。

**验证和决策门槛**

- 安装解析和`pip check`通过，现有应用可导入；
- 模型只写入固定缓存，日常测试保持无网络；
- Native、Docling在同一复杂文件上记录关键事实召回、阅读顺序、表格结构、页码/边界框和资源；
- GPU OOM但CPU可用时，Docling只能采用CPU或离线索引策略；
- 小型演示文档超过冻结超时或无明显质量提升时，不得强行接入在线回退，应记录结果并暂停M2-11.3；
- 基准通过后固定Docling包、模型、OCR配置和Parser版本，禁止使用漂移的`latest`作为可复现结论。

**实际实施记录（2026-08-30，已完成）**

1. 本步解决了什么：在不接主解析链路的前提下，完成Docling本地CPU环境、最小模型缓存、离线Native/Docling对照基准和显式真实Smoke；结果证明Docling明显改善扫描PDF，但不能替代Office Native事实底稿；
2. 大白话运行过程：脚本先校验本地模型文件哈希，再从`m2-complex-v1`确定性生成同一批5份复杂文件；每份分别交给现有Native Parser和Docling，检查10条Golden、双栏顺序和表格数量，同时采样耗时与进程内存，最后生成被Git忽略的JSON报告；日常测试不设置开关时不会加载模型或联网；
3. 固定运行配置：Python 3.11.9；`docling==2.123.1`、`rapidocr==3.9.2`、`onnxruntime==1.23.2`、`torch==2.13.0`、`psutil==7.2.2`；CPU、4线程、单文档120秒、RapidOCR英文ONNX、PyPdfium2 PDF后端、Heron ONNX版面模型、TableFormer accurate、远程服务和外部插件关闭；
4. 固定模型：缓存位于被Git忽略的`data/model-cache/docling/`，正式目录约699MiB；Heron Transformers提交`8f39ad3c...`、Heron ONNX提交`40bde044...`、TableFormer `v2.3.0@fc0f2d45...`，RapidOCR为PP-OCRv6 ONNX英文组合；基准在推理前校验5个关键权重SHA-256，禁止缺文件或内容漂移；首次下载因Windows长路径失败，使用`D:\dcm`短路径完成后复制并验证，失败残留和中转副本均已删除；
5. 修改文件与职责：
   - `requirements.txt`：固定Docling、RapidOCR和ONNX Runtime直接依赖；
   - `requirements-dev.txt`：声明基准资源采样所需psutil；
   - `.env.example`、`app/core/config.py`：新增默认关闭的Docling开关、固定缓存、CPU/线程/超时/OCR及禁止远程服务/插件配置，并限制缓存必须位于统一模型目录；
   - `scripts/benchmark_m2_docling.py`：模型哈希门禁、Native/Docling双路执行、Golden/阅读顺序/结构/资源评估和JSON报告；
   - `tests/unit/test_m2_docling_benchmark.py`：验证Golden归一化、组合表格事实和阅读顺序算法；
   - `tests/integration/test_m2_docling_smoke.py`：默认跳过、仅在`RUN_REAL_DOCLING_SMOKE=1`时加载真实模型验证两页扫描PDF；
   - `tests/unit/test_m2_baseline.py`：约束新增配置默认值、非法配置、缓存边界和依赖声明；
6. 调用链位置：`Benchmark/Smoke → m2-complex-v1内存源文件 → Native Parser或本地Docling → output基准JSON`；没有经过前端、API、Schema、Storage发布、Document Model、PostgreSQL状态、Chunk、Embedding、pgvector、检索、Prompt或Agent；
7. 正式质量与资源结果：
   - 总计：Native `6/10`，Docling `7/10`；两路均`5/5`转换成功；Native最慢0.181秒、最大额外RSS 14.8MiB，Docling最慢36.990秒、最大额外RSS 1439.3MiB；
   - 扫描PDF：Native `0/2`，Docling `2/2`，36.990秒、额外RSS 1439.3MiB；默认ThreadedDoclingParse后端曾导致第2页失败，固定PyPdfium2后两页均成功；
   - 双栏PDF：两路均`2/2`，Docling 3.661秒、258.7MiB，阅读顺序检查通过；
   - 复杂表格PDF：两路均`2/2`，Docling 4.964秒、208.8MiB，并输出1张结构化表；
   - 图文DOCX：两路均`0/2`；Docling标准DOCX后端没有恢复页眉控制码或嵌入图片文字，不能把“支持DOCX”误写成“会OCR所有Word视觉内容”；
   - 多区域XLSX：Native `2/2`，Docling `1/2`；Docling读出补货数值但未保留`=B10+C10`原始公式，openpyxl必须继续作为公式与单元格事实底稿；
8. CPU/GPU结论：当前安装的PyTorch为CPU构建，`torch.cuda.is_available()`为False、CUDA版本为空，`nvidia-smi`也无法取得NVML信息，因此没有伪造GPU耗时或显存数据；当前可复现结论只覆盖CPU，不能证明GTX 1650 Ti GPU路径可用或会OOM；
9. 验证结果：真实模型聚焦集`44 passed`并出现2条Docling内部弃用警告；默认后端全量`357 passed, 4 skipped`，其中真实Docling和真实Qwen等按显式条件跳过；本步文件Ruff、核心Mypy、`pip check`和应用导入通过。扩展到整个遗留仓库的静态检查仍有本步外的99个Ruff与57个Mypy存量问题，未在本步越界修改；
10. 能证明：固定模型的本地CPU链路可离线复现；扫描PDF、双栏顺序和复杂PDF表格达到本评估集门槛；在当前小文件上时间和内存低于120秒/4GiB门槛；Docling总事实得分不低于Native，因此可以进入M2-11.3统一Artifact设计；
11. 不能证明：真实供应商大文件、中文扫描OCR、手写体、公式、加密/损坏文件、并发吞吐、GPU、同步API延迟和最终Router/RAG效果；尤其不能证明Docling单独覆盖DOCX视觉文字或XLSX公式；
12. 后续约束与排查：M2-11.3必须无损保留Native的页码、标题、Office公式和单元格事实；M2-11.4不能把“复杂文件=只用Docling”当作实现，应允许Native事实底稿叠加Docling增强。扫描页失败先查PDF backend与页级错误，OCR缺字再查语言/分辨率，模型报缺失先跑哈希门禁，内存过高先限制并发而不是切到在线远程服务。

**停止点**

M2-11.2已经完成。M2-11.3具备前置条件，但仍需用户单独确认；本次授权不包含Canonical Artifact或后续Router实现。

### M2-11.3｜建立Canonical Parsed Artifact及Native无损适配

**本步只解决的问题**

让四类既有Native结果先汇合为项目自有统一JSON合同，避免Docling第三方类型扩散到下游。

**预计文件**

- `app/services/documents/artifacts.py`；
- `app/services/documents/parsers/base.py`、`__init__.py`及Native Adapter；
- `tests/unit/test_parsed_artifacts.py`和四类Parser兼容回归。

**调用链位置**

```text
Native ParseResult
→ Native Adapter
→ Canonical Parsed Artifact
```

不经过Docling、Storage发布、Model或PostgreSQL。

**验证方式**

- PDF页码/标题线索、DOCX标题路径/段/表、XLSX公式/缓存值/单元格、CSV行范围不丢失；
- 可选边界框具有统一坐标和页尺寸语义；
- JSON包含schema、parser和内容hash版本，输出稳定且无绝对路径/Storage Key/秘密；
- Markdown只由Artifact确定性生成，删除Markdown后仍可从结构化内容重建；
- 现有四类Parser合同保持向后兼容。

**实际实施记录（2026-08-30，已完成）**

1. 本步解决了什么：建立项目自有、严格校验、可版本化的统一解析JSON合同，并把现有PyMuPDF、python-docx、openpyxl和Pandas四类Native结果无损转换进同一结构；后续分块和检索不再需要理解四套Parser类型，也不会直接依赖Docling第三方对象；
2. 大白话运行过程：Parser仍按原方式读取文件，Adapter只接收已经安全解析成功的结果和源文件SHA-256；它把PDF页、DOCX段落/表格、XLSX Sheet/行/单元格、CSV行统一整理为有序Block，计算统计值与内容SHA-256；Markdown需要展示时再从Block确定性生成，不保存为事实底稿；
3. 冻结合同：`schema_version=m2-canonical-parsed-artifact-v1`、`content_hash_version=m2-canonical-content-v1`、Native Adapter为`m2-native-adapter-v1`；顶层保存源格式、源SHA-256、Provider/Parser/Adapter版本、有序Block、统一警告、统计和Artifact内容SHA-256；Block ID固定为`b000001`起的连续编号；未知字段继续由Pydantic严格拒绝；
4. 结构保留：
   - PDF每页一个Text Block，保留1开始页码、字符数、图片数、低文字标记、标题线索、字号和原警告；
   - DOCX段落与表格保持原正文顺序，保留块/段/表/行/列定位、标题层级、标题路径、样式和单元格文字；
   - XLSX每个Sheet一个Table Block，保留Sheet顺序/名称/可见状态、物理空行、表头、坐标、值、数据类型、原始公式、缓存值和精确单元格定位；
   - CSV保留编码、分隔符、表头、逻辑空行、字段值和行范围；
   - 定义可选`top_left`页面坐标框，强制正面积且不越过页宽页高；当前Native结果没有伪造不存在的边界框，字段保持`null`；
5. 修改文件与职责：
   - `app/services/documents/artifacts.py`：Canonical Schema、Parser无关警告、统计/哈希自校验、可选边界框和确定性Markdown派生；
   - `app/services/documents/parsers/native.py`：四类Native ParseResult分发与无损Adapter；
   - `app/services/documents/__init__.py`：公开Artifact、Adapter和Markdown入口；
   - `app/services/documents/parsers/__init__.py`：保持既有Parser公共导出稳定；
   - `tests/unit/test_parsed_artifacts.py`：四格式无损、哈希防篡改、Markdown重建、边界框和两套正式语料验证；
   - `tests/unit/test_m2_baseline.py`：停止线推进到M2-11.3，明确Docling Adapter、Router和Parser Service仍不存在；
6. 调用链位置：`Native ParseResult → Native Adapter → Canonical Parsed Artifact → 可选Markdown视图`；没有经过前端、API、Storage发布、Document Model、PostgreSQL写入、Docling执行、质量门禁、Router、Chunk、Embedding、pgvector、检索、Prompt或Agent；
7. 验证结果：Artifact与四类Parser聚焦回归`103 passed`；默认后端全量`363 passed, 4 skipped`；Ruff和4个新增/导出核心源文件Mypy通过，`pip check`无破损依赖，应用与公共Artifact入口可正常导入；全量首次运行因Docker Desktop未启动而卡在PostgreSQL连接，恢复现有Docker引擎和healthy容器后重新执行通过，没有重建命名卷或修改Schema；
8. 正式语料验证：不可变`m2-v1`和`m2-complex-v1`共10份文件全部生成Canonical Artifact；Artifact记录的源SHA-256与真实字节一致，序列化后重新校验结果相同，10个内容SHA-256均不同；两套XLSX中的9个原始公式全部保留；原Parser测试和全量回归继续约束旧合同与M1可售125；
9. 静态检查边界：本步核心源文件Mypy通过；若把新测试文件一并交给Mypy，它会递归发现既有`tests/fixtures/docx_factory.py`和`spreadsheet_factory.py`的11个第三方类型存量问题，本步没有越界修改夹具类型声明，也没有把它们误报为已解决；
10. 能证明：四种Native结果可稳定汇合；源哈希、Parser版本、内容哈希和定位可审计；JSON篡改会被内容哈希拒绝；删除Markdown后可由结构化Artifact重新生成；现有Parser调用者无需修改；Schema已经允许后续Docling Provider，但本步没有伪造Docling结果；
11. 不能证明：Docling到Canonical的映射、Native/Docling合并与冲突处理、自动路由、安全回退、Artifact原子保存、数据库状态、分块、检索或最终问答；边界框合同已经定义，但当前Native Parser没有提供真实坐标；Markdown是检视视图，不保证还原Office视觉排版；
12. 风险与排查：统计或内容哈希失败先查Adapter是否漏映射/重复计数；XLSX答错先检查`formula/cached_value/value`三者而不是只看Markdown；定位缺失先对比原ParseResult和Block locator；序列化漂移先核对schema、adapter和依赖版本，禁止手工绕过哈希校验。

**停止点**

M2-11.3已经完成。下一步M2-11.4将实现Docling Adapter、质量门禁和Parser Router，但仍需用户单独确认；本次授权不包含M2-11.4或后续解析状态闭环。

### M2-11.4｜实现Docling Adapter、质量门禁与Parser Router

**本步只解决的问题**

根据安全文件的格式特征和Native结果质量，在Native与Docling之间作确定性选择，并统一返回Canonical Artifact。

**预计文件**

- `app/services/documents/parsers/docling.py`；
- `app/services/documents/quality.py`、`routing.py`；
- Fake Docling单元测试、真实Docling Smoke和Router对照测试。

**调用链位置**

```text
Storage二进制流
→ Native Parser
→ Quality Gate
→ 可选Docling Adapter
→ Canonical Parsed Artifact
```

不更新数据库状态，不开始分块或索引。

**验证方式**

- `m2-v1`普通PDF/DOCX/XLSX/CSV保持Native路径；
- 扫描、低文字、复杂阅读顺序或复杂表格的指定安全样本进入Docling；
- XLSX由openpyxl保留公式/单元格事实，Docling不得覆盖缺失值或编造公式；
- 加密、损坏、类型不符、ZIP Bomb和超限文件直接安全失败，不进入Docling；
- 保存Native、Docling与Router的路由原因、警告、版本和对照结果；
- Docling不可用、超时或OOM映射为固定安全错误，不泄露第三方异常或路径。

**实际完成记录（2026-08-30）**

1. 本步解决的问题：把M2-11.2验证过的Docling真正接入项目自有解析链，同时保留现有Native Parser的安全边界和Office事实；普通文件不承担模型开销，复杂PDF使用Docling结果，复杂DOCX/XLSX同时保存两路结果但最终仍选择Native事实底稿；
2. 大白话运行过程：Router先根据文件名确认格式并复核文件签名，再调用原Native Parser执行加密、损坏、ZIP展开量、压缩比、页数、字符数和文件大小等检查；只有Native成功后，质量门禁才检查Native低文字警告和源文件的双栏、PDF表格、DOCX内嵌媒体、XLSX合并单元格等确定性特征，并结合可选受控提示决定`native/docling/hybrid`；需要增强时，Local Docling Provider以离线CPU模型解析并先转成项目自有Snapshot，再生成Canonical Artifact；Router返回被选结果、两路Artifact、路由原因与结构对照；
3. 路由合同：
   - 普通PDF/DOCX/XLSX及所有CSV为`native`，不实例化或调用Docling模型；
   - 扫描、低文字、双栏阅读顺序、合并表头或无边框表格PDF为`docling`，最终选择Docling Artifact；
   - 包含页眉页脚、图片文字的DOCX，以及合并多层表头、多区域、公式的XLSX为`hybrid`，实际调用Docling形成对照，但最终选择Native Artifact以避免丢失Office公式、坐标和正文事实；
   - 自动特征检查是正式上传的默认判断方式；可选复杂度提示只能触发更重的增强路径，不能强制降级或跳过Native安全检查；CSV永不进入Docling；普通DOCX的常规页眉不会单独触发重模型，只有内嵌媒体等更强信号才进入Hybrid；
4. Canonical扩展：Docling Adapter版本固定为`m2-docling-adapter-v1`；第三方Docling对象只存在于`parsers/docling.py`内部，向外返回项目自有Text/Table Snapshot；Canonical表格新增`document_table`来源、合并单元格行列跨度、行/列表头标记和真实页面边界框；PDF页数改按物理页保存，因此同一页可包含多个Docling Block；
5. 修改文件与职责：
   - `app/services/documents/artifacts.py`：扩展Docling Adapter版本、复杂表格单元格语义、多块同页统计和Provider可配置构建；
   - `app/services/documents/parsers/base.py`、`parsers/__init__.py`：新增固定中文`DocumentEnhancementError`并公开，第三方路径、异常或密钥不外泄；
   - `app/services/documents/parsers/docling.py`：隔离Docling类型、懒加载本地CPU Converter、Docling→Snapshot→Canonical映射、标题路径、表格跨度、页码和坐标转换；
   - `app/services/documents/quality.py`：实现PDF双栏/表格、DOCX页眉与媒体、XLSX合并单元格等自动特征检查，以及可审计的确定性质量门禁和路由原因；
   - `app/services/documents/routing.py`、`documents/__init__.py`：实现文件签名复核、Native-first编排、Docling/Hybrid选择、Office事实保护和Native/Docling结构对照；
   - `tests/unit/test_document_routing.py`：覆盖Snapshot映射、普通集、复杂集、公式保护、安全前置拒绝和Docling失败脱敏；
   - `tests/integration/test_m2_docling_smoke.py`：增加真实扫描PDF Router Smoke；
   - `scripts/verify_m2_parser_router.py`：运行5份正式复杂语料并生成`output/m2_parser_router_report.json`对照报告；
   - `tests/unit/test_m2_baseline.py`：把阶段停止线推进到M2-11.4，继续禁止提前出现M2-11.5的`parser_service.py`；
6. 完整调用链位置：本步验证的是`内存源文件字节 → 文件签名复核 → Native Parser安全检查 → Native Adapter → Quality Gate → 可选Local Docling Provider → Docling Snapshot/Adapter → RoutedParseResult/Canonical Artifact`；没有经过前端、API、LocalStorage读取或发布、Document Service/Repository、Model、PostgreSQL状态更新、Chunk、Embedding、pgvector、检索、Prompt或Agent；
7. Fake与安全验证：普通`m2-v1`正式集全部为Native且Docling调用0次；5份`m2-complex-v1`不传manifest复杂度标签，仅靠自动特征检查即使用Fake Provider得到固定`3 docling + 2 hybrid`且调用5次；加密PDF、损坏PDF、DOCX伪装PDF、高压缩DOCX和超限PDF均在Docling前失败，Provider调用保持0；Docling disabled、RuntimeError、TimeoutError和MemoryError均只返回`复杂文档增强解析失败`，不包含路径或第三方细节；
8. 真实验证：扫描PDF真实Router Smoke为`1 passed`，耗时64.02秒，选中Docling Canonical且两条Golden为2/2；5份复杂正式语料未传manifest复杂度标签，在固定本地CPU/4线程/离线模型上全部完成，Docling进入率5/5，路由为`docling=3、hybrid=2、native=0`，最终8/10；对照结果如下：

| 复杂文件 | 路由 | 最终Provider | Native | Docling | 最终 |
|---|---|---|---:|---:|---:|
| 扫描入库单PDF | docling | docling | 0/2 | 2/2 | 2/2 |
| 双栏市场简报PDF | docling | docling | 2/2 | 2/2 | 2/2 |
| 合并表头成本表PDF | docling | docling | 2/2 | 2/2 | 2/2 |
| 图文质检通知DOCX | hybrid | native | 0/2 | 0/2 | 0/2 |
| 多区域补货XLSX | hybrid | native | 2/2 | 1/2 | 2/2 |

9. Office事实验证：复杂XLSX的Native Artifact保存6个原始公式，Docling Artifact为0个公式；Hybrid最终选择Native，因此两条Golden保持2/2，未用Docling缺失值覆盖或编造公式；图文DOCX的0/2被如实保留，没有用路由成功掩盖质量失败；
10. 回归结果：Parser/Artifact/Router聚焦`70 passed`；默认后端全量`370 passed, 5 skipped`；Ruff检查`app/scripts/tests`通过，5个解析核心文件Mypy通过，`pip check`无破损依赖，应用与公开Router入口导入通过；真实Docling测试继续由`RUN_REAL_DOCLING_SMOKE=1`显式启用，普通测试不加载模型；
11. 能证明：普通文件不会误入昂贵模型；当前五类正式复杂特征无需人工标签即可自动路由；复杂文件只有在Native安全检查后才会进入Docling；三类复杂PDF的真实最终结果为6/6；扫描PDF获得实际OCR收益；Office Hybrid不会丢失XLSX公式；两路Parser/Adapter版本、警告、路由原因、内容Hash和结构对照可审计；第三方Docling对象没有渗透到下游合同；
12. 不能证明：图文DOCX页眉/图片文字已经解决、任意未知复杂格式都能自动识别、Canonical JSON已写入Storage、数据库`pending → parsing → ready/failed`状态已闭环、失败发布可补偿、分块/Embedding/检索/问答效果；当前DOCX需要在最终RAG真实验收时再判断是否增加专用视觉/OCR增强；
13. 风险与排查：普通文件误路由先检查传入复杂度标签和Native警告；类型伪装先查文件签名门禁；扫描PDF空结果先查本地模型缓存、RapidOCR和页级定位；表格错位先查Docling原Cell span到Canonical网格的映射；XLSX答案错误优先检查Hybrid是否错误选择了Docling以及Native公式/坐标是否仍在；第三方失败泄漏先检查是否绕过`DocumentEnhancementError`；模型内存过高优先限制解析并发，不启用远程回退。

**停止点**

M2-11.4已经完成。下一步M2-11.5将把Router接入LocalStorage、DocumentVersion状态和Canonical JSON原子发布，但仍需用户单独确认；本次授权不包含M2-11.5、M2-12分块或任何后续能力。

### M2-11.5｜实现解析调度、版本化发布与状态闭环

**本步只解决的问题**

把已验证的Router接入DocumentVersion状态和LocalStorage，形成可重试、可审计且不覆盖旧版本的解析闭环。

**预计文件**

- `app/services/documents/parser_service.py`；
- `app/services/documents/service.py`、`app/repositories/documents.py`、`app/schemas/knowledge.py`的最小扩展；
- Parser Service单元/集成测试、本文件和总看板；
- 现有`document_versions.parser_name/parser_version/parsed_storage_key/parse_status`足够承载V1主产物，默认不新增数据库迁移。

**调用链位置**

```text
后续索引入口
→ Parser Service
→ Storage/Native/Quality/Docling
→ Canonical JSON原子发布
→ Document Service/Repository
→ DocumentVersion Model
→ PostgreSQL
```

不经过Chunk、Embedding、pgvector业务表、检索、Agent或前端。

**验证方式**

- `pending → parsing → ready/failed`合法转换；
- Canonical主产物使用`{tenant}/parsed/{year}/{month}/{version_id}.json`，公共响应不暴露Key；
- Storage发布或数据库提交失败时清理本次半成品，审计和安全错误保留；
- 重试不覆盖旧版本产物，不让失败新版本替换旧active；
- parser/模型版本、路由原因、警告和内容hash可从Artifact审计；
- tenant/owner/ACL、M1库存125、迁移头和全量回归保持。

**实际完成记录（2026-08-30）**

1. 本步解决的问题：把M2-11.4只返回内存结果的Router接入真实LocalStorage和DocumentVersion状态，使每个版本可以被单个任务领取、生成不可覆盖的版本化解析JSON，并在成功、失败和重试后留下相互一致的数据库状态；
2. 大白话运行过程：Parser Service先用一个很短的数据库事务确认用户是文档所有者或公司Owner，并原子地把版本从`pending/failed`领取为`parsing`；随后关闭事务，从Storage读取原文件，复核字节数和SHA-256，在数据库事务外运行Native/Quality/Docling Router；解析成功后把完整Routed Artifact写成JSON，再用第二个短事务把Parser元数据和内部Key写入`ready`；任何中间失败都会删除本次JSON半成品，并用独立事务把版本和文件记为`failed`；
3. 状态与并发合同：
   - DocumentVersion只允许本服务原子执行`pending/failed → parsing → ready/failed`；`claim_parse`的条件UPDATE保证同一版本只有一个任务能领取，第二次领取得到状态冲突；
   - 文件在领取时执行`uploaded/failed → validating → parsing`；解析成功后保持`parsing`等待后续索引步骤，解析失败则记录固定`文档解析失败`；
   - 慢速解析不持有数据库事务或行锁；Parser Service自己拥有领取、完成和失败三个短事务，不依赖未来API请求是否存在；
   - Parser Service从不修改`documents.active_version_id`，因此失败新版本不会替换已验证的旧active版本；
4. 发布合同：主产物Schema为`m2-routed-parsed-document-v1`，内部保存route/reasons/quality、selected/native/docling Artifact、结构对照、两路Parser与Adapter版本、警告、源/内容Hash；路径固定为`{tenant}/parsed/{year}/{month}/{version_id}.json`，LocalStorage原子且不可覆盖；数据库只保存选中Parser名称/版本和内部Key，`ParsedDocumentPublication`与原有公共Document响应都不返回Key或原文件名；
5. 修改文件与职责：
   - `app/services/documents/parser_service.py`：任务领取、Storage读取与Hash复核、Router执行、JSON发布、完成事务、失败补偿和安全重试；
   - `app/repositories/documents.py`：增加带状态前置条件的原子`claim_parse/complete_parse/fail_parse`；
   - `app/services/documents/routing.py`：给持久化主产物增加固定`m2-routed-parsed-document-v1`版本；
   - `app/schemas/knowledge.py`：增加不暴露Storage Key的`ParsedDocumentPublication`；
   - `app/core/errors.py`：增加固定、可重试且不泄露内部异常的`DocumentParsingError`；
   - `app/services/documents/__init__.py`：公开`DocumentParserService`；
   - `tests/integration/test_document_parser_service.py`：真实PostgreSQL与LocalStorage成功、失败、重试、补偿、权限和旧active版本测试；
   - `tests/unit/test_m2_baseline.py`：停止线推进到M2-11.5，确认Parser Service已存在而分块/检索模块仍不存在；
6. 完整调用链位置：`内部解析入口 → DocumentParserService → Document/File Repository → DocumentVersion/StoredFile Model → PostgreSQL短事务 → LocalStorage原文件 → Native/Quality/可选Docling Router → Routed Canonical JSON → LocalStorage原子发布 → PostgreSQL ready/failed`；本步没有经过前端、HTTP API、Chunk、Embedding、pgvector业务向量表、检索、Prompt、Agent或最终回答；
7. 成功验证：真实上传的普通PDF从`pending/uploaded`开始，完成后DocumentVersion为`ready`、文件为等待索引的`parsing`、数据库Parser名称为`pymupdf`，JSON Key严格包含tenant和version UUID；从Storage重新读取的JSON可被`RoutedParseResult`完整校验，源Hash、Artifact内容Hash和发布字节Hash一致，公开结果和JSON均不包含私有Storage源Key或原文件名；
8. 失败与重试验证：删除源对象后解析只返回固定`文档解析未能完成，请稍后重试`，版本/文件进入failed且无解析JSON；恢复同一不可变源对象后，同一version ID可从failed重新领取并成功发布；ready版本再次解析被状态冲突拒绝，已有Artifact不被覆盖；
9. 补偿验证：在JSON已经原子发布后，模拟PostgreSQL完成更新失败，Parser Service删除本次JSON、回滚完成事务、记录failed且不泄露模拟数据库路径；数据库恢复后同一版本可以成功重试；
10. 权限与旧版本验证：同租户非所有者无法领取私有文档，版本保持pending、文件保持uploaded且没有Artifact；第一版本完成解析/索引并设为active后，第二版本解析失败，`active_version_id`仍指向第一版本，第一版本Artifact仍存在；
11. 验证结果：Parser Service真实集成`5 passed`；Storage、四类Parser、Artifact、Router、知识迁移/服务和阶段守卫聚焦`152 passed, 2 skipped`；默认后端全量`375 passed, 5 skipped`；Ruff检查`app/scripts/tests`通过，7个解析/Repository/Schema核心文件Mypy通过，`pip check`无破损依赖，应用与公开Parser Service入口导入通过；
12. 数据与迁移复核：没有新增数据库迁移，Alembic仍为`20260829_0004 (head)`；全量测试结束后发现共享演示库Seed为空，已通过既有幂等`seed_m2_files`与`seed_m2_complex_files`恢复，不是手工改业务数据；最终M1 `DE-FRA`可售库存为125，M2为10 files、10 documents、10 versions且全部保持pending，未把测试解析状态带入正式Seed；
13. 能证明：Parser Router已经进入真实Storage与PostgreSQL闭环；状态领取具备单任务前置条件；慢解析不占用长事务；发布字节、Artifact内容和源文件均可Hash审计；数据库完成失败会补偿Storage半成品；失败可重试且不覆盖ready Artifact或旧active版本；内部Key不会进入公共结果；
14. 不能证明：进程在OS强制终止、机器断电或Storage删除本身持续失败时绝对不会留下孤儿对象；后续可增加`parsing`超时回收/孤儿巡检，但不在本步扩展；本步也没有证明分块、Embedding、向量索引、权限过滤检索或RAG答案效果；复杂DOCX视觉文字0/2仍是已知质量短板；
15. 风险与排查：版本一直`parsing`先查工作进程是否在领取后被强杀；数据库ready但对象缺失先查是否绕过Parser Service手工改状态；Storage存在但版本failed先查完成事务失败和补偿删除日志；重试提示对象已存在说明上次孤儿清理失败，禁止覆盖，应先按tenant/version精确核验；源Hash不符先查Storage对象与DocumentVersion content_hash；旧active异常变化先查是否有代码越过索引完成条件直接调用`activate_version`。

**M2-11整体结论**

M2-11.1至M2-11.5均已完成：复杂评估集、真实Docling基准、Canonical合同、自动Router和版本化解析状态闭环全部具备实际验证依据。M2-11没有解决分块、索引或最终RAG问答，这些仍按M2-12之后的独立步骤推进。

**停止点**

M2-11已经完成。下一步M2-12是“实现结构感知分块”，但仍需用户单独确认；本次授权不包含M2-12、Embedding、索引、检索或后续能力。

**M2-11整体完成标准**

1. `m2-v1`普通语料保持不可变，`m2-complex-v1`可重复生成并具有黄金答案、定位、路由和OCR标记；
2. Docling真实包/模型/配置固定，在当前机器有可复现质量与资源基准；
3. 普通文件保持Native，指定复杂安全文件进入Docling，危险文件直接拒绝；
4. Native与Docling汇合为同一Canonical Artifact，Markdown只是派生视图；
5. 版本化JSON原子发布，失败/重试/旧版本/权限边界安全；
6. 普通测试不隐式下载模型，真实Docling Smoke与离线回归分离；
7. 每个子步骤均完成代码、实际验证、阶段日志和总看板同步，并得到用户下一步授权。

**主要风险与排查方向**

- Docling/PyTorch依赖冲突：先检查解析依赖树、当前Pydantic/Transformers兼容和`pip check`，不批量升级无关依赖；
- 模型下载或缓存漂移：固定模型/revision和缓存根目录，检查`.gitignore`，不得提交权重；
- 4GB显存OOM：先真实测CPU/GPU，小batch/CPU/离线索引优先，不反复触发系统卡死；
- 中文OCR或表格效果不佳：核对黄金事实、阅读顺序和定位，不能只凭Markdown观感判断；
- Router过度或漏判：普通集约束Native，复杂集约束Docling，保存每次路由原因；
- 第三方结构变化：只允许Docling Adapter依赖其类型，Canonical Schema独立版本化；
- XLSX语义增强丢公式：openpyxl事实底稿优先，Docling输出不得覆盖坐标、公式或缓存值；
- 原`m2-v1`被意外改写：在复杂语料生成和全回归中固定检查旧manifest字节/hash/定位。

**下一步**

停止并等待用户审阅M2-11整体结果。只有用户明确确认后，才开始M2-12结构感知分块；该授权不包含Embedding、索引、检索、RAG问答或后续正式步骤。

## 24. M2-12结构感知分块方案与实施记录

### M2-12正式方案确认

**确认日期：2026-08-30**

用户在审阅结构感知分块方案、并进一步确认“不是固定字数一刀切，而是结构优先、长度兜底”后，明确回复“好的开始这一步”。该授权覆盖M2-12总方向，实际开发仍按项目单步规则拆分，当前只实施M2-12.1。

M2-12确认采用：

- 只消费`m2-routed-parsed-document-v1`中的`selected_artifact`，切块算法只依赖`m2-canonical-parsed-artifact-v1`，不依赖PyMuPDF、Docling、python-docx或openpyxl类型；
- 初始目标600 Token、硬上限700 Token、同一语义范围内重叠100 Token；标题、段落、表格、Sheet和来源定位优先于长度；
- 文本Chunk与结构化表格Chunk共用一个版本化合同，同时保存`body_text`、后续检索用`retrieval_text`、标题路径、页码、字符偏移、Sheet/单元格/行范围、公式、跨度和可选边界框；
- 相同文档版本、Canonical内容Hash、Chunker/Token Counter版本和配置必须得到字节级相同的输出；
- M2-12后续将新增`document_chunk_sets`元数据表承载重切版本、状态和Hash；真正`document_chunks`、FTS和`vector(1024)`仍保留到M2-13；
- 图文DOCX页眉/图片文字0/2、Native不具备显式列表语义和部分Native PDF无真实坐标是上游已知边界，M2-12不编造或顺手修复。

实施拆分为：M2-12.1合同/计数/配置；M2-12.2 PDF/DOCX文本结构单元；M2-12.3四类表格切块；M2-12.4 Chunk Set模型与迁移；M2-12.5 Storage/PostgreSQL发布闭环；M2-12.6 Golden Set、真实数据库与收口。

### 2026-08-30｜M2-12.1｜Chunk合同、确定性Token Counter与配置基线

**状态：已完成**

1. 本步解决的问题：M2-11只有Canonical Parsed Artifact，还没有统一规定“切出的小卡片必须长什么样、怎样计数、怎样证明重复生成没有漂移”；本步先冻结严格Chunk合同、可置换Token Counter边界、无模型的确定性中英文计数器和集中配置，不实现真正切块算法；
2. 大白话运行过程：后续Chunker必须把每张“小卡片”写成同一张严格表格：正文和检索文本分开、标明来源Block/页/标题/单元格，表格继续保留行列和公式；计数器对中文字符、英数分段和标点按固定规则计数，不加载BGE；配置、单Chunk和整套Artifact分别计算Hash，任何文本、定位、公式或配置被改动都会被拒绝；
3. 冻结版本：`m2-canonical-chunk-artifact-v1`、`m2-chunk-content-v1`、`m2-structure-aware-chunker-v1`、`m2-chunk-normalization-v1`和`m2-unicode-token-counter-v1`；`chunk_set_id`由document version、Canonical内容Hash、Chunker/Counter版本和配置Hash通过固定UUIDv5命名空间推导，不含随机数、时间、路径或秘密；
4. 数据合同：顶层记录文档/版本ID、Routed/Canonical Schema、源/发布/Canonical内容Hash、Chunker/Counter、完整配置与Hash、有序Chunk、排除Span、统计和输出Hash；文本/表格Chunk共同保存`body_text/retrieval_text/token_count/heading_path/source_spans/page_numbers/bounding_boxes/overlap`，表格额外保存Sheet状态、编码/分隔符、行范围、单元格、公式、表头和重复上下文标记；
5. 修改文件与职责：
   - `app/services/documents/chunking/contracts.py`：Chunk/Chunk Artifact严格Pydantic合同、交叉约束、Canonical JSON Hash、确定性Chunk Set ID与构建入口；
   - `app/services/documents/chunking/token_counting.py`：`TokenCounter` Protocol、NFC规范化后的Token Span及`UnicodeMixedTokenCounter`；
   - `app/services/documents/chunking/__init__.py`：冻结M2-12.1稳定公共导入；
   - `app/core/config.py`、`.env.example`：新增700硬上限、120标题预算、1行表格重叠、至少2页重复边缘判定与配置组合校验；
   - `tests/unit/test_document_chunk_contracts.py`：验证计数、配置、字节稳定、配置换ID、两层篡改拒绝、XLSX公式/单元格语义、顺序/上限/重叠/额外字段拒绝；
   - `tests/unit/test_m2_baseline.py`：将阶段守卫推进到M2-12.1，明确允许合同和计数器，但`normalization.py/chunker.py/service.py`仍不得出现；
6. 完整调用链位置：`Canonical Parsed Artifact（只作为后续输入类型） → Chunk内部Schema/Hash/Token Counter（本步）`；未经过前端、API、真正Chunker算法、Storage发布、Repository、SQLAlchemy Model、PostgreSQL业务写入、Embedding、pgvector、检索、Qwen、Evidence或Agent；
7. 聚焦验证：Chunk合同/配置与阶段守卫`52 passed`；相同输入和配置的Artifact对象、JSON字节、Chunk Set ID和Hash完全相同；配置改动会生成不同ID/Hash；篡改Chunk正文或顶层输入Hash均被严格拒绝；结构化表格测试保留Sheet、A1:B2、重复表头标记、`=C2+D2`公式和B2精确定位；
8. 全量与质量验证：Ruff对`app/tests/scripts/migrations`通过；5个本步源/测试文件Mypy通过；编译和`pip check`通过；有效全量回归`387 passed, 5 skipped`，比M2-11增加12个本步合同/配置用例；首次全量运行因Docker Desktop未运行而在数据库模块超时，确认Linux Engine不存在后中断，只恢复原有Docker Desktop/容器/命名卷，PostgreSQL healthy后从头重跑得到上述有效结果；
9. 数据与迁移复核：本步没有新增模型或迁移，Alembic仍为`20260829_0004 (head)`，`alembic check`无待生成操作；全量测试清空Seed后只运行既有幂等M1/`m2-v1`/`m2-complex-v1` Seed恢复，最终为10 files、10 documents、10 versions、9 ACL，10个版本的parse/index均为pending，M1 `DE-FRA`可售库存仍为125；
10. 能证明：后续算法已有一份不丢标题、来源Span、表格行列、公式和单元格的严格输出合同；中英文长度单位可重复；配置、单Chunk和整套输出可Hash审计；相同身份可推导相同Chunk Set ID；本步导入不加载或下载BGE/Docling模型；
11. 不能证明：任何PDF/DOCX/XLSX/CSV已经实际切成Chunk、600/700/100策略在真实文档上达标、页眉页脚/长段/表格行窗口算法正确、Chunk JSON已写入Storage、Chunk Set已写PostgreSQL，或Embedding/检索可用；`UnicodeMixedTokenCounter`是明确版本化的切块长度单位，不是BGE-M3真实tokenizer；
12. 风险与排查：合同Hash漂移先查Canonical JSON键顺序、Unicode NFC和是否误加时间字段；Chunk Set ID变化先对比document version、Canonical内容Hash、Chunker/Counter版本和配置Hash；公式/定位丢失先查后续Chunker是否绕过`ChunkTableData/ChunkSourceSpan`；Token数与后续BGE差异必须在M2-14记录并使用新Counter/Chunk Set，不覆盖当前版本。

**停止点**

M2-12.1已完成。下一步M2-12.2才会实现PDF/DOCX的确定性清洗、标题/段落/显式列表结构单元、跨页和长段文本切块；仍需用户单独确认。本次授权不包含M2-12.2、表格切块、Chunk Set迁移、Storage发布、Embedding、索引或检索。

### 2026-08-30｜M2-12.2｜PDF/DOCX文本结构单元与切块

**状态：已完成**

1. 本步解决的问题：M2-12.1只有Chunk合同和计数规则，还不能把真实Canonical PDF/DOCX内容切成Chunk；本步实现只依赖`CanonicalParsedArtifact`的文本算法，生成符合既有合同的Text Chunk，同时把空内容、重复页眉页脚和暂缓处理的表格显式列出；
2. 大白话运行过程：先把Canonical里的文字做固定清洗，但为每个清洗后字符保留“它来自哪个Block的哪一段”；再按标题把内容放进不同抽屉，同一标题下的短段合并，太长时优先在段落、句号、分号/逗号、空白处断开，实在没有自然边界才按Token硬切；后一块只在同一个标题抽屉里复制最多100 Token的上一块末尾，表格会关上当前抽屉并把表格ID交给M2-12.3；
3. 确定性规范化：`m2-chunk-normalization-v1`执行CRLF/CR统一为LF、NBSP统一为空格、Unicode NFC、行尾空白去除、连续空行上限和首尾空白去除；`NormalizedSourceText`为每个输出字符保留Canonical原文半开区间，Unicode组合字符也可回指原始偏移；算法不读取文件路径、时间、随机数、Parser对象或模型；
4. PDF策略：按物理页和Canonical顺序读取文本行；只对完全相同的标题提示升级标题路径；相同首行/末行在至少配置页数重复时分别记录为`repeated_header/repeated_footer`排除Span；同一标题路径且中间没有表格时允许跨页合并，Chunk保存全部有序页码和来源Span；
5. DOCX策略：直接信任Canonical的`heading_level/heading_path`，按标题范围隔离段落；正文中已有的`-/*/•/▪/◦/数字或字母编号`标记原样保留并作为列表结构单元参与合并；若Word自动编号没有进入Canonical文本，本步不猜造编号；标题切换和表格都形成硬边界；
6. 长度与重叠：检索文本由完整`heading_path`元数据和最多120 Token的标题上下文加正文构成；默认以600 Token为软目标、700为硬上限，边界优先级为段落→句子→分句→空白→Token；重叠只发生在同一标题组的连续Chunk之间，保存前一Chunk ID、实际Token数和重复来源Span，不跨标题或表格；
7. 输出边界：`TextChunkingResult`只包含有序Text Chunk、`ExcludedChunkSpan`和`deferred_table_block_ids`；每个Chunk已由M2-12.1的`build_document_chunk`计算内容Hash并保存`body_text/retrieval_text/heading_path/source_block_ids/source_spans/page_numbers/bounding_boxes/overlap`；完整Chunk Artifact要等M2-12.3加入表格Chunk后统一构建，不用文本半成品冒充完整文档；
8. 修改文件与职责：
   - `app/services/documents/chunking/normalization.py`：确定性Unicode/换行/空白规范化和Canonical字符偏移映射；
   - `app/services/documents/chunking/chunker.py`：PDF/DOCX结构单元、重复边缘识别、标题分组、跨页、递归边界窗口、重叠、来源Span和文本结果；
   - `app/services/documents/chunking/__init__.py`：公开文本Chunker、结果、错误和规范化入口；
   - `tests/unit/test_document_text_chunker.py`：覆盖规范化偏移、DOCX标题/列表/表格边界、PDF重复边缘/标题提示/跨页、超长段/重叠、标题隔离、空段审计、确定性、非法类型和Native真实解析链路；
   - `tests/unit/test_m2_baseline.py`：停止线推进到M2-12.2，允许文本算法但继续禁止`tables.py/service.py`和检索模块；
   - 本文件和`docs/PROJECT_PROGRESS.md`：记录实际实现、验证、边界和下一停止点；
9. 完整调用链位置：`Native/Docling Parser（已存在上游） → Canonical Parsed Artifact → normalization/StructureAwareTextChunker（本步） → M2-12.1 DocumentChunk合同与单Chunk Hash`；本步不经过前端、HTTP API、Chunk发布Service、Repository、SQLAlchemy Model、PostgreSQL业务写入、Storage输出、Embedding、pgvector、检索、Reranker、Qwen、Evidence或Agent；
10. 聚焦验证：新增文本算法与合同/Parser/Artifact/Router/阶段守卫合计`103 passed`；实际`make_text_pdf → PdfParser → Native Adapter → Canonical Artifact → Chunker`和`make_structured_docx → DocxParser → Native Adapter → Canonical Artifact → Chunker`均生成带来源Span且不超过700 Token的确定性结果；同一输入两次JSON完全相同；
11. 全量与质量验证：默认后端全量`396 passed, 5 skipped`；Ruff检查`app/tests/scripts/migrations`通过；5个Chunk核心文件Mypy通过；`compileall`、`pip check`和公共导入通过；真实PostgreSQL容器保持healthy；
12. 数据与迁移复核：本步未新增Model、Repository或迁移，Alembic仍为`20260829_0004 (head)`且`alembic check`无待生成操作；全量测试将共享Seed清空后，仅运行既有幂等M1、`m2-v1`和`m2-complex-v1` Seed恢复，最终10 files、10 documents、10 versions、9 ACL，10个版本parse/index均为pending，M1 `DE-FRA`可售库存仍为125；
13. 能证明：PDF/DOCX已经能从真实Canonical输入稳定生成文本Chunk；标题不同不会混块；同标题可跨页；重复页眉页脚不会进入检索正文且有排除审计；表格不会被静默忽略；长段不突破硬上限且重叠可回溯；正文、标题、页码和字符区间可供未来回答引用；算法没有依赖PyMuPDF、Docling或python-docx运行时类型；
14. 不能证明：DOCX/XLSX/PDF表格和XLSX/CSV行窗口已经切好、完整Chunk Artifact已经发布、数据库已有Chunk Set、失败重试/旧结果清理已闭环，或Embedding/混合检索/RAG回答有效；Native PDF没有Bounding Box时本步不会编造坐标；上游图文DOCX图片文字0/2和未被解析器暴露的Word自动编号仍不会凭空出现；
15. 风险与排查：标题混块先查Canonical `heading_path`或PDF标题提示是否精确匹配；页眉页脚误删先查页面首末行、重复阈值和排除Span；引用偏移异常先查规范化字符映射与`source_spans`；Chunk超限先查标题预算、边界选择和Token Counter版本；列表编号缺失先确认编号是否存在于Canonical文本；表格前后文字意外合并先查`deferred_table_block_ids`和表格硬边界；结果Hash漂移先对比Canonical内容Hash、配置、Counter和规范化版本。

**停止点**

M2-12.2已完成。下一步M2-12.3才会实现DOCX/PDF文档表格、XLSX工作表和CSV的结构化行窗口切块，包括表头重复、Sheet/单元格/公式/行范围与表格行重叠；仍需用户单独确认。本次授权不包含M2-12.3、Chunk Set迁移、Storage/PostgreSQL发布、Embedding、索引或检索。
