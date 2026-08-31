# M2：知识库垂直切片详细实施方案

> 阶段状态：进行中
> 方案日期：2026-08-29
> 方案确认：2026-08-29，用户明确回复“确认M2方案，可以开始M2-01”
> 方案修订确认：2026-08-30，用户确认引入 Docling 作为复杂文档本地解析后端，保留现有 Parser 快速路径，并要求先更新文档再逐步实施
> M2-12方案确认：2026-08-30，用户明确回复“好的开始这一步”；M2-12.1至M2-12.6均已按单步规则完成
> M2-13确认：2026-08-31，用户明确授权只建立`document_chunks`、PostgreSQL FTS和`vector(1024)`模型及迁移
> M2-14方案确认：2026-08-31，用户明确确认跨机器修订方案并授权Provider开发、固定模型下载与真实验证
> M2-14方案修订：2026-08-31，用户说明会在两台配置不同的电脑上开发；方案改为跨机器统一合同、逐机能力探测和可比较报告
> M2-14完成：2026-08-31，Provider/Fake、固定revision、本机CPU真实Smoke与基准、强制离线复跑、质量工具、全量回归和正式Seed复核均已通过
> M2-15方案确认：2026-08-31，用户明确回复“已确认，开始实施”；实施仍按单一小步骤逐项验证和停下汇报
> M2-15.1完成：2026-08-31，Index Set ORM、`20260831_0007`迁移、active-ready复合约束和Chunk代次归属已完成并验证
> M2-15.2完成：2026-08-31，确定性Index Set身份、完整Embedding身份Hash和Chunk逐行Mapper已完成并验证
> M2-15.3完成：2026-08-31，Index Repository领取、失败重试、批量保存和Version/Document原子激活已完成并验证
> M2-15.4完成：2026-08-31，DocumentIndexService编排、解析/切块复用、分批Embedding、失败补偿和整链原子激活已完成并验证
> M2-15.5完成：2026-08-31，最小Documents API、严格Schema、依赖组装、管理权限、安全错误和同步重试已完成并验证
> M2-15.6完成：2026-08-31，正式10文档Fake整链、显式离线BGE Smoke、失败重试、重复幂等、全量质量门和Seed恢复已完成并验证
> M2-16方案确认：2026-08-31，用户在完整方案和通俗解释后两次明确回复“继续”；只授权有权限约束的Lexical、Dense、Hybrid与RRF检索闭环，不授权Reranker、RAG或M2-17
> M2-16.1完成：2026-08-31，严格检索输入/输出、分数、集中配置和安全错误合同已冻结并验证
> M2-16.2完成：2026-08-31，版本化中文FTS Builder、索引写入接入与`20260831_0008`迁移已完成并验证
> 当前步骤：明确停止在M2-16.2；等待用户确认后才可进入M2-16.3共享获权active候选边界
> M1 代码基线：`main` / `94ad0eec837dfa618bb2e0c07e6a21769d690ebb`
> 数据性质：M2 文档、标准答案和评估数据必须是明确标注的版本化合成演示数据

> **当前停止点：M2-16.1与M2-16.2已经完成。不得自动开始M2-16.3；每个后续小步骤仍需单独授权，不自动实施Reranker、RAG、前端、Agent或M2-17。**

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

- 目标：对获权混合候选做二次精排，输出 top 5～8；本步才显式下载 Reranker。
- 预计文件：`app/services/retrieval/reranker.py`、Fake/真实 Smoke、基准脚本和测试。
- 调用链：Hybrid Candidates → Reranker → Final Candidates。
- 验证：Fake稳定、真实中英文相关性、模型/revision/设备记录、内存、超时、空候选、批量降级；不得重新引入未授权块。

### M2-18｜实现 Context Builder、知识 Evidence 和引用验证

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
- 下游：M2-11.2真实Docling基准、M2-11.4路由、M2-12分块和M2-22 RAG评估。

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

用户在审阅结构感知分块方案、并进一步确认“不是固定字数一刀切，而是结构优先、长度兜底”后，明确回复“好的开始这一步”。该授权覆盖M2-12总方向，实际开发仍按项目单步规则拆分；M2-12.1至M2-12.6已经分别获得授权并完成。

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

### 2026-08-31｜M2-12.3｜四类结构化表格切块与Canonical顺序合并

**状态：已完成**

1. 本步解决的问题：M2-12.2只会生成PDF/DOCX文本Chunk，并把表格Block列入`deferred_table_block_ids`；DOCX表格、PDF/Docling `document_table`、XLSX工作表和CSV还不能形成保留单元格事实的结构化Table Chunk。本步只消费`m2-canonical-parsed-artifact-v1`，增加四类统一表格算法，并把文本与表格Chunk按Canonical Block顺序合并；
2. 大白话运行过程：表格先保留原始行、列、单元格、公式和位置，再用“表头+连续数据行”装入每张检索卡片；后续卡片重复表头和默认1行数据上下文，并把所有复制行标成`repeated_as_context`，因此同一物理数据行不会冒充新数据；普通行按Token预算合并，超宽或超长物理行改按不切断合并单元格跨度的列窗口拆分，连一个完整单元格都放不下时明确安全失败，绝不截断；
3. 确定性与合同细化：继续使用`m2-structure-aware-chunker-v1`、`m2-unicode-token-counter-v1`和M2-12.1 Hash入口；`ChunkTableRow.repeated_as_context`现在同时适用于重复表头和数据行重叠；文本重叠仍受100 Token配置限制，表格重叠按`table_row_overlap`行数控制并由`ChunkOverlap`保存实际Token和来源Span；相同Canonical输入、配置和Counter会得到相同Chunk JSON、顺序、单Chunk Hash和整体输出Hash；
4. 四类来源策略：DOCX表格保留标题路径、表号和原单元格；PDF/Docling `document_table`保留表格标题、页码、Bounding Box、行列头标记及`row_span/column_span`；XLSX保留Sheet名、`visible/hidden/veryHidden`状态、单元格范围、原值、显示值、数据类型、公式、缓存值与坐标；CSV保留编码、分隔符和逻辑行范围；算法不导入PyMuPDF、Docling、python-docx、openpyxl或Pandas运行时类型；
5. 边界策略：空表或全空表不生成伪Chunk，进入`skipped_tables=empty_table`；只有表头的表仍生成一张结构化Chunk；隐藏Sheet默认参与切块并保留状态，配置关闭时进入`skipped_tables=hidden_sheet`；超宽表按合并跨度闭包形成原子列组，避免在合并单元格内部切开；单个原子单元格超过700 Token时抛出固定安全错误；表格`retrieval_text`含来源、标题、标题路径、Sheet、范围及行视图，但不能替代`ChunkTableData.rows.cells`结构事实；
6. Canonical顺序合并：新增`StructureAwareDocumentChunker`复用现有文本Chunker和新表格Chunker，按Artifact原始`block_id`位置稳定合并并重新生成连续`c000001...`编号、重叠引用和内容Hash；这为M2-12.4/12.5完整Canonical Chunk Artifact和发布闭环提供算法输入，但本步不持久化；
7. 修改文件与职责：
   - `app/services/documents/chunking/tables.py`：四类表格行/列窗口、表头与数据重叠、列拆分、结构化行/单元格、定位、跳过审计和文档级顺序合并；
   - `app/services/documents/chunking/contracts.py`：允许数据重叠行使用`repeated_as_context`，并区分文本Token重叠预算与表格行重叠预算；
   - `app/services/documents/chunking/__init__.py`：公开表格/文档Chunker和结果合同；
   - `tests/unit/test_document_table_chunker.py`：覆盖DOCX、真实Native DOCX链路、PDF `document_table`、真实Native XLSX/CSV、表头、行重叠、公式缓存、范围、隐藏/空/仅表头、超宽/不可拆长单元格、合并跨度、Canonical顺序和Hash；
   - `tests/unit/test_m2_baseline.py`：停止线推进到M2-12.3，允许`tables.py`但继续禁止`service.py`与检索目录；
   - `tests/integration/test_seed_m2_complex_files.py`：修复开始前发现的跨平台文本行尾Hash守卫，哈希前统一CRLF/CR为LF，不改变`m2-v1`语料、manifest内容或业务预期；
   - 本文件与`docs/PROJECT_PROGRESS.md`：同步实际结果和新停止点；
8. 完整调用链位置：`Native/Docling Parser（既有上游） → Canonical Parsed Artifact → StructureAwareTextChunker + StructureAwareTableChunker → StructureAwareDocumentChunker → M2-12.1 DocumentChunk/Hash合同`；本步没有经过前端、HTTP API、Chunk发布Service、Repository、SQLAlchemy Model、PostgreSQL业务写入、Storage输出、Embedding、pgvector业务向量表、关键词/混合检索、Reranker、Qwen、Evidence或Agent；
9. 聚焦验证：合同、四类Parser/Adapter、Artifact、Router、文本/表格Chunker、阶段守卫和复杂Seed合计`133 passed`；其中新增表格文件10项全部通过，实际DOCX、XLSX和CSV Native Parser→Canonical→Chunk链路成功，PDF `document_table`保留第2页Bounding Box和2×2合并跨度；所有生成Chunk不超过700 Token；
10. 全量与质量验证：默认后端全量`408 passed, 3 skipped`，在原`396 passed, 5 skipped`上增加10项本步用例，并因当前Windows环境已能真实执行2项符号链接测试而少跳过2项；3项剩余跳过为显式真实Docling/Qwen等条件测试。Ruff检查`app/tests/scripts/migrations`通过；3个本步核心源文件Mypy通过；`compileall`、`pip check`、`git diff --check`、公共导入和`alembic check`通过；
11. 数据与迁移复核：本步未新增Model、Repository或迁移，Alembic保持`20260829_0004 (head)`；Docker恢复后幂等启用pgvector 0.8.6，容器保持healthy；全量测试清空共享Seed后使用既有模块入口恢复M1、`m2-v1`和`m2-complex-v1`，最终10 files、10 documents、10 versions、9 ACL，10个版本parse/index均为pending，M1 `DE-FRA`可售库存为125；
12. 能证明：四类Canonical表格可以生成结构化、可定位、可Hash的Table Chunk；表头和数据重叠有明确上下文身份；公式与缓存、Sheet/单元格/行范围、页码/Bounding Box、合并跨度和来源Block不会被文本视图替代；宽行可结构化拆列，不能安全容纳的单元格不会静默截断；文本和表格最终顺序与Canonical一致；
13. 不能证明：Chunk Set元数据已经入库、完整Chunk Artifact已经写Storage、发布失败/抢占/重试/旧结果清理已闭环，或Embedding、pgvector业务向量、关键词/混合检索、Reranker和RAG回答有效；默认Header只信任Canonical `header_row_number/column_header`，Native DOCX没有暴露的表头语义不会被猜造；图文DOCX图片文字仍为0/2；
14. 风险与排查：表头未重复先查Canonical是否存在`header_row_number/column_header`与`repeat_table_headers`；数据行重复被当新数据先查`repeated_as_context`和`ChunkOverlap.source_spans`；范围错位先查首块原始表头是否计入范围、后续上下文行是否被错误计为新范围；公式缺失先查Artifact Cell的`value/display_text/data_type/formula/cached_value`；超限先查检索元数据、原子合并跨度和单元格本身Token，禁止增加截断；顺序/Hash漂移先查Canonical Block顺序、Counter、配置和重新编号；
15. 基线异常记录：开始检查时Docker Desktop未运行，恢复后本地固定pgvector镜像因缺失而按既有Dockerfile重建；现有命名卷最初为Alembic `0003`且未启用vector，通过已有`alembic upgrade head`和幂等`CREATE EXTENSION`恢复，没有删除卷或创建新迁移。首次全量还暴露Windows自动CRLF使冻结文本Hash失败，已用行尾规范化守卫修复并验证Seed内容Git diff为零。

**停止点**

M2-12.3已完成。下一步M2-12.4才会建立`document_chunk_sets`模型和Alembic迁移；必须等待用户单独确认。本次授权不包含M2-12.4、Storage/PostgreSQL Chunk发布Service、重新切片/抢占/失败重试、Embedding、pgvector业务向量表、关键词/混合检索、Reranker、RAG回答或前端。

### 2026-08-31｜M2-12.4｜Chunk Set模型与迁移

**状态：已完成**

1. 本步解决的问题：M2-12.3已经能在内存中生成完整、有序且确定性的Chunk，但PostgreSQL还没有位置登记“这批Chunk属于哪个租户/文档版本、使用哪套算法与配置、当前处理到什么状态、成功结果的Hash/Storage Key/统计是什么”。本步新增`document_chunk_sets`元数据模型与迁移，使同一文档版本可拥有多套由确定性ID区分的重切结果；不保存单个Chunk行，也不发布Artifact；
2. 大白话运行过程：把一次切块看成一批货，`document_chunk_sets`就是这批货的登记单。登记单先保存原料Hash、机器版本、规则JSON和规则Hash；开始处理时记录次数和开始时间；只有拿到完整JSON产物、输出Hash及块数统计后才允许标为`ready`，失败则只能保存安全错误摘要。相同确定性`chunk_set_id`重复登记时可用主键冲突安全地不新增第二行；
3. 合同对齐：模型直接保存M2-12.1 `CanonicalChunkArtifact`的`artifact/content/routed/canonical`四类版本、三类输入SHA-256、Chunker/Token Counter/Normalization身份、完整`config_json`及`config_sha256`；成功后保存`output_sha256`、`chunk_storage_key`、文本/表格/总Chunk数、总Token数和排除Span数，因此后续Service无需从Hash反猜配置；
4. 租户与版本边界：复合外键`(tenant_id, document_version_id, document_id)`必须整体指向同一条`document_versions`记录，不能把A文档版本挂到B文档，也不能跨租户；删除文档版本时对应Chunk Set级联删除。`(tenant_id, id)`额外唯一约束为后续Chunk行的租户内复合引用预留安全边界，但本步没有创建`document_chunks`；
5. 状态与半成品约束：状态固定为`pending/chunking/ready/failed`；`pending`必须是第0次且无开始/结束时间，`chunking`必须至少第1次且只有开始时间，`ready/failed`必须同时有开始/结束时间。`ready`必须具备输出Hash、只允许`{tenant}/chunks/{yyyy}/{mm}/{chunk_set_id}.json`的Storage Key和一致统计；`failed`只允许错误摘要；处理中和失败记录都不能冒充已发布结果；
6. 修改文件与职责：
   - `app/models/knowledge.py`：新增`DocumentChunkSet`字段、关系、复合外键、索引及版本/Hash/状态/Storage/统计约束，并为`DocumentVersion`增加一对多`chunk_sets`关系；
   - `app/models/__init__.py`：公开`DocumentChunkSet`模型；
   - `migrations/versions/20260831_0005_document_chunk_sets.py`：从`20260829_0004`升级创建表、约束和索引，降级只删除该表；
   - `tests/unit/test_knowledge_models.py`：锁定模型字段、复合外键、状态统计边界，并继续确认未来`document_chunks`不存在；
   - `tests/integration/test_document_chunk_set_migration.py`：真实PostgreSQL迁移往返、确定性ID幂等、跨文档拒绝、ready半成品拒绝、统计不一致拒绝、合法ready结果及级联删除；
   - `tests/unit/test_m2_baseline.py`：停止线推进到M2-12.4，允许Chunk Set模型/迁移但继续禁止Chunk发布`service.py`和检索目录；
   - 本文件与`docs/PROJECT_PROGRESS.md`：同步实际结果和新停止点；
7. 完整调用链位置：`M2-12.1 Canonical Chunk Artifact合同（已有上游） → SQLAlchemy DocumentChunkSet Model（本步） → Alembic 0005（本步） → PostgreSQL document_chunk_sets（本步）`。本步没有经过前端、HTTP API、Pydantic请求/响应Schema、Chunk发布Service、Repository、单Chunk业务表、Storage实际写入、Embedding、pgvector向量列、关键词/混合检索、Reranker、Qwen、Evidence或Agent；
8. 聚焦验证：模型、迁移、Chunk合同、文本/表格Chunker和阶段守卫合计`85 passed`；其中新模型/迁移最小集合`56 passed`。真实数据库验证`0005 → 0004 → 0005`往返、相同确定性ID重复写不增行、跨文档复合外键拒绝、缺结果标ready被拒绝、2+1=3统计可成功、1+1≠3统计被拒绝、删除版本后Chunk Set级联删除；
9. 全量与质量验证：后端全量`413 passed, 3 skipped`，较本步开始的`408 passed, 3 skipped`新增5项有效用例；Ruff检查`app/tests/scripts/migrations`通过，Mypy检查整个`app`的92个源文件通过，`compileall`、`pip check`、`git diff --check`和`alembic check`通过；
10. 数据与迁移复核：Alembic现为`20260831_0005 (head)`且无待生成操作；PostgreSQL/pgvector容器保持healthy。全量测试后使用现有幂等M1、`m2-v1`和`m2-complex-v1` Seed恢复，最终10 files、10 documents、10 versions、9 ACL、10个版本parse/index均为pending，M1 `DE-FRA`可售库存为125；`document_chunk_sets`保持0行，证明本步没有伪造发布结果；
11. 能证明：数据库已经能可靠登记一套确定性Chunk Set的输入身份、完整配置、执行状态、结果Hash、内部Storage Key和统计；租户/文档版本不会错挂；ready/failed半成品形状由PostgreSQL硬约束；迁移可往返且不会创建未来Chunk/向量表；
12. 不能证明：Chunker已从解析产物自动运行、Chunk Artifact已写入Storage、Service可原子抢占/成功/失败/补偿/重试、并发重新切片安全，或单Chunk已写PostgreSQL、Embedding/pgvector/FTS/混合检索/RAG回答有效；图文DOCX图片文字仍为0/2；
13. 风险与排查：无法插入pending先查四类Schema版本、三类输入Hash、实现版本和`config_json/config_sha256`是否完整；跨文档错误先核对tenant/document/version三元组；状态更新失败先检查attempt/start/completed时间与结果字段是否匹配；ready失败先检查Storage Key是否严格使用tenant、`chunks`类别、年月、Chunk Set ID和`.json`，再检查文本块数+表格块数是否等于总块数；`alembic check`漂移先逐项比较Model与0005的列类型、默认值、约束名和索引。

**停止点**

M2-12.4已完成。下一步M2-12.5才会实现Chunk Artifact的Storage/PostgreSQL发布闭环，以及原子领取、成功/失败补偿和同一确定性ID重试；必须等待用户单独确认。本次授权不包含M2-12.5、M2-12.6 Golden收口、`document_chunks`、Embedding、pgvector业务向量、FTS/混合检索、Reranker、RAG回答或前端。

### 2026-08-31｜M2-12.5｜Chunk Artifact Storage/PostgreSQL发布闭环

**状态：已完成**

1. 本步解决的问题：M2-12.4只有Chunk Set登记表，真实业务仍不能从已发布解析JSON自动读取`selected_artifact`、生成完整Chunk Artifact、不可覆盖写入Storage并把同一批次安全落为ready。服务过程中若算法、Storage或数据库任一环节失败，也缺少清理半成品和同一确定性ID重试闭环；
2. 大白话运行过程：先确认用户能管理文档且版本解析已ready，再从Storage取回并验真解析JSON；随后算出固定的Chunk Set编号，在一个很短的数据库事务里“领任务”。领完后关掉事务，在外面做耗时切块和JSON生成；文件完整写入后再开短事务盖ready章。如果中途失败，就尽量删掉刚写的文件并把登记单标为failed，下次仍使用同一编号重试；
3. 输入验真与有界读取：只读取`DocumentVersion.parsed_storage_key`指向的`m2-routed-parsed-document-v1`，读取上限为上传文件上限的4倍，用于容纳JSON结构膨胀且阻止无界内存读取；Pydantic重新验证Routed/Canonical自校验合同，并要求`selected_artifact.source_sha256`等于版本`content_hash`。非法、超限、缺失或被篡改JSON在领取前安全失败，不产生Chunk Set记录；
4. 原子领取和重切身份：`DocumentRepository.claim_chunk_set`先以确定性主键幂等插入pending，再只对完整身份一致且处于pending/failed的记录执行条件更新为chunking，`attempt_count + 1`；身份比较覆盖租户/文档/版本、四类Schema版本、三类输入Hash、Chunker/Counter/Normalization、完整配置JSON及配置Hash。同一记录处于chunking或ready时第二个worker无法领取，配置变化则生成独立Chunk Set；
5. 完整Artifact与审计：`DocumentChunkService`调用`StructureAwareDocumentChunker`生成Canonical顺序结果，再由`build_chunk_artifact`生成自校验JSON。为了避免空表或按配置排除的隐藏Sheet在发布时丢失，本步把`SkippedTableBlock`提升到稳定合同并加入`CanonicalChunkArtifact.skipped_tables`及整体输出Hash；单Chunk、排除文本Span、跳过表格、统计和来源定位都随同发布；
6. 不可覆盖发布与孤儿恢复：Storage Key固定为`{tenant}/chunks/{yyyy}/{mm}/{chunk_set_id}.json`，普通写入沿用LocalStorage原子且不可覆盖语义；若数据库失败且补偿删除也失败，下次重试只在现有对象与新生成payload字节完全相同时复用，任何不同内容都安全失败且不覆盖；Storage返回的Key、大小、字节SHA和Content-Type也必须全部匹配；
7. 成功、失败与安全输出：成功只在记录仍为chunking时写ready、输出Hash、内部Storage Key和统计；失败清空所有结果字段，只保留固定错误摘要“文档切块失败”和结束时间。`DocumentChunkSetPublication`只返回Chunk Set/文档/版本ID、配置/输出Hash和统计，不返回Storage Key、本机路径或底层异常；文档的parse状态保持ready，index状态保持pending；
8. 修改文件与职责：
   - `app/services/documents/chunking/service.py`：授权复核、有界读取与验真、确定性身份、短事务领取、事务外切块/发布、ready/failed落库、补偿和重试；
   - `app/repositories/documents.py`：新增Chunk Set幂等插入、完整身份条件领取、成功完成和失败关闭SQL；
   - `app/services/documents/chunking/contracts.py`：把跳过表格审计加入完整Canonical Chunk Artifact和Hash构建入口；
   - `app/services/documents/chunking/tables.py`：复用稳定`SkippedTableBlock`合同，不再定义只属于算法内部的重复类型；
   - `app/schemas/knowledge.py`、`app/schemas/__init__.py`：新增不泄露Storage Key的安全发布结果；
   - `app/core/errors.py`：新增固定、可重试且不暴露内部细节的Chunk发布错误；
   - `app/services/documents/chunking/__init__.py`、`app/services/documents/__init__.py`：公开稳定Service与合同入口；
   - `tests/integration/test_document_chunk_service.py`：真实Parser→Storage→Chunker→Storage→PostgreSQL链路、失败重试、数据库失败补偿、孤儿复用、并发式二次领取拒绝、权限/状态/篡改边界和配置重切；
   - `tests/unit/test_document_chunk_contracts.py`：验证跳过表格进入Artifact并受输出Hash保护；
   - `tests/unit/test_m2_baseline.py`：停止线推进到M2-12.5，允许发布Service但继续禁止检索目录；
   - 本文件与`docs/PROJECT_PROGRESS.md`：同步实际验证与下一停止点；
9. 完整调用链位置：`已存在Parser Service → Parsed Storage JSON → Canonical selected_artifact → DocumentChunkService → StructureAwareDocumentChunker → CanonicalChunkArtifact → LocalStorage + DocumentRepository → DocumentChunkSet Model → PostgreSQL`。本步使用内部安全Schema，但没有经过前端或HTTP API；没有创建单Chunk Model/表、FTS、Embedding、pgvector业务向量、关键词/混合检索、Reranker、Qwen、Evidence或Agent；
10. 聚焦验证：Chunk合同/算法/Storage/模型/迁移/Parser/Repository/发布Service和阶段守卫扩大集合`135 passed`；新增发布Service文件单独`7 passed`，包括真实原子二次领取拒绝。成功结果可从Storage重新解析为自校验`CanonicalChunkArtifact`，公开结果与JSON均不含内部解析Storage Key或原文件名；
11. 全量与质量验证：后端全量`421 passed, 3 skipped`，较本步开始的`413 passed, 3 skipped`新增8项有效用例；Ruff检查`app/tests/scripts/migrations`通过，Mypy检查95个源/测试文件通过，`compileall`、`pip check`、`git diff --check`和公共导入通过；Alembic仍为`20260831_0005 (head)`且`alembic check`无待生成操作；
12. 数据复核：PostgreSQL/pgvector容器保持healthy。全量测试后运行既有幂等M1、`m2-v1`和`m2-complex-v1` Seed，最终10 files、10 documents、10 versions、9 ACL、10个版本parse/index均pending，M1 `DE-FRA`可售库存125；正式`document_chunk_sets`与`data/storage/**/chunks/*.json`均为0，测试产物只在pytest临时目录，未伪造M2-12.6正式发布数据；
13. 能证明：已解析且有管理权限的文档版本可以真实、确定性地产生完整Chunk Artifact并在Storage/PostgreSQL一致发布；同一身份不会并发双领，失败可用同一ID重试，配置变化可并存新批次；数据库完成失败会补偿，删除失败留下的相同孤儿可恢复，不同内容不能覆盖；空/隐藏表格的明确排除不会在最终JSON中丢失；
14. 不能证明：进程在领取后被强制杀死时会自动回收长期停留在chunking的记录；当前没有持久Worker、租约超时或后台清理。也不能证明10份正式Golden语料全部已解析/切块发布、单Chunk已写PostgreSQL、FTS/Embedding/pgvector/检索/RAG回答有效；图文DOCX图片文字仍为0/2；
15. 风险与排查：领取前失败先查版本parse状态、parsed Storage对象、4倍读取上限、Routed/Canonical自校验和源Hash；状态冲突先查同一ID是否已chunking/ready或完整身份字段是否漂移；发布失败先查Storage Key年月/ID、返回大小/Hash/Content-Type；重试遇到已有对象先逐字节比较，禁止直接覆盖；ready落库失败先查记录是否仍chunking及统计约束；长期chunking先确认是否发生进程级中断，该恢复能力不在本步范围内。

**停止点**

M2-12.5已完成。下一步M2-12.6才会对版本化Golden Set执行真实解析/切块发布、核对定位与Hash、恢复正式Seed并收口整个M2-12；必须等待用户单独确认。本次授权不包含M2-12.6、`document_chunks`/M2-13、Embedding、FTS/pgvector业务向量、检索、Reranker、RAG回答或前端。

### 2026-08-31｜M2-12.6｜Golden Set真实发布、恢复与M2-12收口

**状态：已完成**

1. 本步解决的问题：M2-12.5已证明单个真实文档能安全发布Chunk Artifact，但10份版本化正式Golden语料还没有一起经过真实Parser/Chunk Service、Storage和PostgreSQL，也没有一份可重复核对“事实是否进入Chunk、原定位是否仍在、相同输入能否逐字节重建、验收后正式Seed能否恢复干净”的收口报告；
2. 大白话运行过程：脚本先确认Docling本地模型文件与Hash没变，并要求10个正式版本都处于pending、没有旧Chunk Set；然后用正式公司负责人身份逐份调用Parser Service和Chunk Service，把解析JSON与Chunk JSON真实写入Storage、把10张登记单真实写成ready。每份产物重新读取并按严格合同验真，再用同一Canonical输入/配置/Counter重新切一次逐字节比较；20条Golden分别寻找同时含答案线索和正确页码/标题/表格行列/Sheet/单元格/行范围的Chunk。最后只按这10个版本的精确ID删除临时解析/Chunk对象和Chunk Set，并恢复文件/版本pending状态；
3. Golden验收合同：`scripts/verify_m2_chunk_pipeline.py`固定`m2-chunk-pipeline-report-v1`，Seed JSON仍是问题、答案和定位的唯一权威；脚本只为每条事实维护最小检索探针，不改写原Seed。成功必须同时满足10文档ready、普通/复杂集共18/20内容+定位命中、唯一失败文档为已知`visual_quality_notice`、10/10逐字节确定性重建、10/10 Canonical Block锚点不倒退，以及清理后正式基线完整恢复；
4. 真实结果：10份文档全部完成真实发布，共35个Chunk（27个文本、8个结构化表格），单Chunk最大394 Token，均低于700硬上限；路由为5份Native、3份Docling、2份Hybrid；`m2-v1`为10/10，`m2-complex-v1`为8/10，总计18/20内容与SourceLocator同时命中；扫描PDF、双栏PDF、Docling复杂表格、XLSX公式和CSV行范围均命中，唯一失败仍是图文DOCX页眉控制码/图片文字2条，即既有0/2质量短板，没有用假Chunk或弱化定位标准掩盖；
5. 确定性与Hash：每份已发布JSON均重新解析为自校验`CanonicalChunkArtifact`；同一已发布Routed/Canonical输入、Artifact内配置和`m2-unicode-token-counter-v1`在内存中重建，10/10得到完全相同的JSON字节、Chunk顺序、Chunk Set ID和输出Hash；10/10首个来源Block锚点保持非递减，证明文本/表格合并没有打乱Canonical顺序；报告写入被Git忽略的`output/m2_chunk_pipeline_report.json`，保存每份路由、Chunk统计、Hash、事实命中Chunk ID和定位结果；
6. 收口时发现并修复的问题：正式CSV含尾部空单元格的审计行，旧检索文本渲染会留下行尾空格；`M1Schema`完整校验会剥离外层空格，使校验前Hash与校验后内容不一致。`app/services/documents/chunking/tables.py`现在在Hash前确定性去掉每行末尾空白，但`ChunkTableData.rows/cells`仍原样保留所有空单元格、列号和值，没有静默丢弃结构化事实；
7. 修改文件与职责：
   - `scripts/verify_m2_chunk_pipeline.py`：模型Hash门禁、正式Seed前置检查、真实Parser/Chunk发布、Golden内容与定位匹配、确定性重建、Canonical顺序检查、精确清理和版本化JSON报告；
   - `tests/unit/test_m2_chunk_pipeline_verification.py`：保证10份文档都有2条受审探针、普通5份真实Native链路10/10内容+定位命中且两次结果相同，并锁定图文DOCX不伪造2条上游缺失证据；
   - `app/services/documents/chunking/tables.py`：修复CSV尾部空单元格行的检索文本/Hash规范化时机，结构化单元格保持不变；
   - `tests/unit/test_m2_baseline.py`：停止线推进到M2-12.6，允许验收脚本但继续禁止检索目录；
   - 本文件与`docs/PROJECT_PROGRESS.md`：记录真实结果、边界、恢复状态和M2-13新停止点；
8. 完整调用链位置：`版本化合成Seed/Storage源文件 → DocumentParserService → Native/Docling Router → Routed/Canonical Parsed Artifact → Parsed Storage JSON → DocumentChunkService → 结构感知文本/表格Chunker → CanonicalChunkArtifact → Chunk Storage JSON + DocumentRepository → DocumentChunkSet Model → PostgreSQL`。本步使用内部安全Schema返回发布摘要，但没有经过前端或HTTP API；没有创建`document_chunks`、FTS、Embedding、pgvector业务向量、关键词/混合检索、Reranker、Qwen、Evidence或Agent；
9. 聚焦验证：新增验收/阶段守卫/表格与发布Service集合`65 passed`；普通5份正式语料在不加载Docling的日常测试中实现10/10内容+定位、两次结果相同和Canonical顺序通过；图文DOCX Native底稿明确保持0/2，防止未来测试用错误探针把缺失内容标成成功；
10. 真实离线验证：恢复并逐项校验5个冻结Docling关键权重SHA-256后，真实脚本成功退出；10份文档先全部在PostgreSQL成为ready，报告得到18/20、定位18/20、确定性10/10、顺序10/10和5 Native/3 Docling/2 Hybrid；随后精确删除20个临时发布JSON并清除10个Chunk Set，报告`baseline_restored=true`；
11. 全量与质量验证：后端全量`424 passed, 3 skipped`，较M2-12.5新增3项有效用例；Ruff对`app/tests/scripts/migrations`全范围检查通过，本步3个代码/测试文件格式检查通过；Mypy检查整个`app`、验收脚本和新增测试共95个源文件通过；`compileall`、`pip check`、`git diff --check`和`alembic check`通过；PostgreSQL保持healthy，Alembic为`20260831_0005 (head)`；
12. 最终数据复核：全量pytest按测试设计清空共享Seed后，已只运行现有幂等`seed_m2_files`和`seed_m2_complex_files`恢复。最终M1 `LR-TL-MUSH-OR01 / DE-FRA`可售库存125；M2为10 files、10 documents、10 versions、9 ACL，10个版本parse/index均为pending；`document_chunk_sets`为0，`data/storage`下parsed/chunks JSON为0；正式演示库没有保留收口过程的ready状态或发布对象；
13. 能证明：四格式普通文件和五类复杂场景能够从正式源文件经过真实Router、Canonical、结构感知切块、不可覆盖Storage发布和PostgreSQL状态闭环；现有可见事实的内容与精确定位能进入Chunk；所有Chunk低于硬上限；同一输入完全可重复；发布后的正式数据可精确恢复；
14. 不能证明：单Chunk已经写入PostgreSQL业务表、FTS/vector(1024)索引可用、BGE-M3 Embedding/混合检索/Reranker/RAG答案有效，或强杀后长期`chunking`任务能自动租约回收；这些属于M2-13以后。图文DOCX页眉与图片文字仍为0/2，当前结论是如实保留上游短板，不是已经解决；
15. 风险与排查：Golden下降先按报告区分内容缺失还是Locator丢失，再查Router选择、Canonical Block和Chunk来源Span；Hash不一致先比较输入三类Hash、配置/Counter/Chunker版本、检索文本尾部空白和结构化单元格；顺序失败先查文本/表格合并锚点及重叠来源；恢复失败只允许按10个正式版本ID核对parsed/chunk Key和Chunk Set，禁止清空整个Storage；Docling门禁失败先检查固定缓存5个文件与SHA-256，不得联网漂移后跳过门禁。

**M2-12整体结论**

M2-12.1至M2-12.6均已完成：严格Chunk合同、结构感知文本和四类表格算法、Chunk Set迁移、Storage/PostgreSQL发布闭环及正式Golden真实收口都有代码和实际验证依据。M2-12没有创建单Chunk业务表、FTS/vector或任何检索能力。

**停止点**

M2-12已经完成。下一步M2-13才会建立`document_chunks`、FTS和`vector(1024)`模型及迁移；必须等待用户单独确认。本次授权不包含M2-13、Embedding、索引、检索、Reranker、RAG回答或前端。

## 25. M2-13｜`document_chunks`、PostgreSQL FTS和`vector(1024)`模型及迁移

### 2026-08-31｜M2-13｜单Chunk检索存储地基

**状态：已完成**

1. 本步解决的问题：M2-12能把一整批Chunk发布成Storage JSON，并用`document_chunk_sets`登记批次，但PostgreSQL仍没有“一行一个Chunk”的明细表，无法在数据库内按权限/版本过滤后做关键词或向量排序。本步只建立明细模型、数据库约束、FTS/pgvector字段和索引，不导入正式Golden Chunk，不运行BGE-M3，也不实现任何写入或检索Service；
2. 大白话运行过程：`document_chunk_sets`继续像一张“整批货物登记单”，`document_chunks`则是登记单下面的逐件明细。每行先用普通列写清租户、文档、版本和批次，再保存正文、检索文本、Token、Hash以及M2-12已有的页码、标题、来源Span、坐标、重叠、表格结构和警告。PostgreSQL自动把独立`fts_text`变成可搜索词条；向量格子固定为1024维但允许为空，只有未来真实向量存在时才能同时填写模型和版本；
3. 输入、输出和上下游：输入是`m2-canonical-chunk-artifact-v1`中单个`DocumentChunk`的字段和既有`DocumentChunkSet`身份；输出是`document_chunks`数据库行、自动生成的`search_vector`、GIN索引和余弦HNSW索引。上游M2-12合同/Chunk Set不改；下游M2-14才生成真实Embedding，M2-15才实现幂等索引管线，M2-16/17才实现Dense/Lexical查询；
4. 身份与生命周期：每行显式保存`tenant_id/document_id/document_version_id/document_chunk_set_id`；直接版本复合外键以及同时覆盖tenant/Chunk Set/version/document的四列复合外键共同阻止错挂。为此给Chunk Set增加四列唯一引用键；删除Chunk Set会级联删除其Chunk，删除DocumentVersion会经直接外键和Chunk Set生命周期清理Chunk；没有把任何身份只埋进JSON；
5. Chunk合同保存：普通列保存`chunk_id/chunk_index/kind/body_text/retrieval_text/token_count/content_sha256`；JSONB分别保存`heading_path/page_numbers/source_block_ids/source_spans/bounding_boxes/overlap_json/table_json/warnings`。数据库要求JSON类型与数组长度符合M2-12上限，`text`不得携带表格对象，`table`必须携带含`source_kind`和`rows`的对象；同一Chunk Set内`chunk_id`和`chunk_index`分别唯一，ID/Hash/Token/序号格式均有检查约束；
6. FTS设计：新增独立非空`fts_text`，与保留原语义和定位上下文的`retrieval_text`分责；`search_vector`是PostgreSQL持久生成列，表达式固定为`to_tsvector('simple', fts_text)`并建立GIN索引。M2-13只用固定英文合成词验证数据库能力；当时路线图把中文分词安排在M2-17，现已并入M2-16.2/16.5，本步不伪装完成；
7. 向量设计：`embedding`类型为可空`vector(1024)`，建立`vector_cosine_ops`余弦HNSW索引；`embedding_model/embedding_version`只能与非空向量同时存在，空向量行三者必须全部为空。这样正式演示库没有假Embedding，同时给M2-14的固定模型/revision留出审计位置；
8. 修改文件与职责：
   - `app/models/knowledge.py`：新增`DocumentChunk`、Chunk Set四列唯一引用键、双重复合外键、Chunk字段/JSONB/约束、生成FTS列、`vector(1024)`和三类索引；
   - `app/models/__init__.py`：公开`DocumentChunk`模型；
   - `migrations/env.py`：显式把`DocumentChunkSet/DocumentChunk`纳入Alembic模型注册清单；
   - `migrations/versions/20260831_0006_document_chunks_fts_vector.py`：实现`0005 → 0006`创建、索引和完整降级；
   - `tests/unit/test_knowledge_models.py`：锁定字段、1024维、生成列、复合外键、唯一边界和GIN/HNSW声明；
   - `tests/integration/test_document_chunk_migration.py`：真实迁移往返、合法文本/表格、约束拒绝、FTS、向量排序、索引存在和级联生命周期；
   - `tests/unit/test_m2_baseline.py`：停止线推进到M2-13，允许模型/迁移但继续禁止`app/services/retrieval`；
   - 本文件与`docs/PROJECT_PROGRESS.md`：同步真实验证、边界和新停止点；
9. 完整调用链位置：`M2-12 Canonical Chunk合同/DocumentChunkSet（已有上游） → SQLAlchemy DocumentChunk Model（本步） → Alembic 0006（本步） → PostgreSQL FTS/pgvector（本步）`。前端、HTTP API、Pydantic对外Schema、Repository、Chunk Artifact导入/发布Service、后台Worker、BGE-M3、关键词/向量/混合检索、RRF、Reranker、Qwen、Evidence和Agent均未经过；
10. 编码前基线：分支`main`、HEAD `960559a13281555f2b3d52d27e9e4fc7552fcc05`，完整保留M2-12.3至12.6未提交改动；`.venv` Python 3.11.9、PostgreSQL healthy、pgvector 0.8.6、Alembic `0005 head`、Storage parsed/chunks JSON各0；正式库10 files/10 documents/10 versions/9 ACL、10个版本parse/index均pending、0 Chunk Set、M1可售库存125；改动前全量`424 passed, 3 skipped`；
11. 真实PostgreSQL验证：合法文本Chunk、结构化表格Chunk、三条带固定1024维合成向量的Chunk和一条无向量Chunk均成功写入事务；重复`chunk_id`、重复`chunk_index`、跨租户、跨文档、跨版本、错Chunk Set、非法SHA、0序号、0 Token、table无结构及非1024维向量均被拒绝；固定`alphaunique`只命中目标Chunk；固定查询向量的余弦距离按`0.0 → 0.2 → 1.0`确定性排序；`pg_indexes`真实查到GIN与`vector_cosine_ops` HNSW；删除Chunk Set后只清理其三条Chunk，删除另一上游版本后对应Chunk Set/Chunk级联清理；所有测试事务最终回滚；
12. 迁移与聚焦验证：真实执行`0005 → 0006 → 0005 → 0006`，表/列/生成列/1024维类型在预期位置出现或消失；新集成文件`2 passed`，模型/阶段守卫组合`59 passed`，Chunk合同/算法/知识迁移扩大集合`91 passed`；`alembic current/heads`均为`20260831_0006 (head)`，`alembic check`报告无待生成操作；
13. 全量与质量验证：后端全量`429 passed, 3 skipped`，比开始时增加5个有效用例且没有新增跳过；Ruff对`app/tests/scripts/migrations`规则检查通过，M2-13的7个文件格式检查通过；Mypy检查整个`app`和两份M2-13测试共95个源文件通过；`compileall`、`pip check`和`git diff --check`通过。全仓库`ruff format --check`仍会列出25个M2-13之前的未格式化文件，本步没有批量改写用户未提交的M2-12代码；
14. 最终数据复核：全量pytest清空共享Seed后，只运行既有幂等`seed_m2_files`和`seed_m2_complex_files`恢复。最终容器healthy、pgvector 0.8.6、Alembic `0006 head`、M1 `LR-TL-MUSH-OR01 / DE-FRA`可售125；M2为10/10/10/9、10个版本parse/index均pending、`document_chunk_sets=0`、`document_chunks=0`，`data/storage`下parsed/chunks JSON均为0；GIN/HNSW索引各真实存在1个；
15. 能证明：数据库可以逐行保存M2-12文本/表格Chunk及引用定位；普通身份列和复合外键能阻止已覆盖的错挂；Chunk唯一性、格式、text/table结构和1024维度有数据库硬约束；FTS生成列、GIN、可空向量和余弦HNSW可真实创建和运算；迁移可往返且M1/正式Seed未退化；
16. 不能证明：正式35个Golden Chunk已经导入数据库、BGE-M3已经生成真实向量、Embedding质量/性能有效、Chunk Set统计和逐行写入已由Service原子协调、中文分词、关键词/Dense/混合检索、ACL/active/soft-delete查询过滤、RRF、Reranker、RAG回答或前端已经实现。小规模固定向量排序也不能证明大数据量HNSW召回率或性能；图文DOCX页眉/图片文字仍为0/2，未在本步修复；
17. 过程中发现并修复：可空JSONB最初把Python `None`绑定成JSON字面量`null`，改为`JSONB(none_as_null=True)`后与SQL `NULL`约束一致；PostgreSQL三值逻辑曾让`kind=table/table_json=NULL`的CHECK返回未知并漏过，现显式要求table分支`table_json IS NOT NULL`，真实拒绝测试锁定该边界；
18. 风险与排查：合法Chunk插入失败先查四个身份列和Chunk Set四列引用键，再查JSON是否使用真实数组/对象而非JSON `null`；FTS不命中中文先查现M2-16.2/16.5是否生成应用层分词`fts_text`，不要覆盖`retrieval_text`；向量写入失败先查维度是否恰为1024、模型/版本是否同时提供；余弦排序异常先查运算符类和查询向量；删除后残留先查两个FK的`ON DELETE CASCADE`及是否绕过正式迁移；索引不存在先查pgvector 0.8.6、迁移头和`pg_indexes`，不要手工补建掩盖迁移漂移。

**停止点**

M2-13已经完成。下一步M2-14才会实现BGE-M3 Embedding Provider、批量编码、1024维严格输出和真实资源/质量基准；必须等待用户单独确认。本次授权不包含M2-14、Chunk Artifact导入/发布Service、重新解析/切块、后台Worker、任何关键词/向量/混合检索、RRF、Reranker、RAG回答、API或前端。

## 26. M2-14｜BGE-M3 Embedding Provider与真实基准实施方案

### 2026-08-31｜M2-14-PLAN｜已确认方案

**状态：已完成（用户已明确确认修订方案；本机实现、真实模型验证和最终收口均已完成）**

1. 当前现状与缺少能力：M2-13已经提供可空`vector(1024)`、模型/revision审计列和HNSW索引，但项目还没有统一Embedding接口，无法把M2-12的`retrieval_text`或后续查询文本稳定转换成真实向量，也没有模型缓存定位、批量降级、严格输出校验或本机资源基准；
2. 大白话目标：先做一个“统一翻译器”。上游交给它一批文字和用途（文档或查询），Fake实现给日常测试返回可重复的假向量，BGE实现从固定本地快照加载真实模型并返回1024个归一化数字。Provider只负责生成和验真，不负责把Chunk写进数据库；
3. 本阶段输入与输出：输入是有界、非空的文档`retrieval_text`或查询文本列表，以及模型ID、固定revision、设备策略、精度、batch和归一化配置；输出是与输入顺序一一对应的1024维有限浮点向量、模型身份、用途和确定性cache key。cache key由用途、Provider合同版本、模型ID、固定revision、池化/最大长度/归一化/精度等会改变数值的推理合同及原文SHA-256组成；实际设备和batch只影响性能、不应改变逻辑身份，因此不进入cache key；
4. 明确目标：实现可替换的`EmbeddingProvider`协议、确定性Fake、懒加载本地BGE-M3、文档/查询批量编码、1024维/有限值/L2归一化/顺序与数量严格校验、显式batch减半重试、固定revision本地快照解析、Provider工厂、真实下载/Smoke/基准脚本和版本化JSON报告；
5. 明确不做：不新增迁移或修改`document_chunks`，不把正式35个Golden Chunk写入数据库，不实现M2-15索引管线、Repository/Worker、Embedding持久缓存、关键词/Dense/混合检索、RRF、Reranker、RAG回答、API或前端，不重新解析/切块，也不修复图文DOCX 0/2；
6. 前置条件与已核对事实：分支`main`、HEAD `960559a13281555f2b3d52d27e9e4fc7552fcc05`且M2-12/13未提交改动仍在；官方模型为`BAAI/bge-m3`、1024维，计划固定Hub commit `5617a9f61b028005a4858fdac845db406aefb181`。当前这台电脑的Python 3.11.9、FlagEmbedding 1.4.2、PyTorch 2.13.0+cpu、Transformers 5.16.1、Sentence Transformers 6.0.0、Hugging Face Hub 1.29.0、缓存和磁盘数据只属于本机基线，不能写成另一台电脑的前提；
7. 双机与设备边界：Provider不得写死显卡型号、CUDA可用性、CPU线程数、绝对缓存路径或batch。每次运行先独立探测`torch`构建、CPU/RAM、CUDA可用性、GPU/显存和受管缓存；`MODEL_DEVICE=auto`只在当前运行时确实支持CUDA时选择CUDA，否则稳定回退CPU，也允许显式`cpu`保证可复现。当前电脑虽能看到GT 1030 4GB，但PyTorch为CPU构建，所以本机只跑CPU真实基准并记录CUDA不可用；第二台电脑按自己的能力产生独立CPU或CUDA报告，不要求两台电脑得到相同耗时；
8. 步骤一——冻结合同与Fake：预计新增`app/services/retrieval/__init__.py`、`app/services/retrieval/embedding.py`和`tests/unit/test_embedding_provider.py`，小幅补充`app/core/errors.py`、`app/core/config.py`、`.env.example`及阶段守卫。先定义文档/查询用途、模型身份、cache key、Provider协议、确定性Fake与安全错误，再用单元测试验证空输入/超量输入、相同输入可重复、不同用途cache key隔离、1024维、有限值、归一化和批次顺序；
9. 步骤二——真实BGE与离线边界：在同一Provider模块实现懒加载BGE后端。下载动作必须由独立脚本显式传入`--allow-download`并锁定commit；运行Provider只接收本地snapshot路径，设置离线模式且`trust_remote_code=False`，绝不因普通测试或应用导入隐式联网。通过可注入后端测试错误脱敏、模型只加载一次、输出形状/NaN/Inf/范数拒绝以及内存不足时batch按`4→2→1`降级；
10. 步骤三——真实Smoke与逐机基准：预计新增`scripts/benchmark_m2_embedding.py`、`tests/smoke/test_bge_m3_embedding_smoke.py`和对应脚本单测。脚本显式下载后编码同一组固定中文、英文、德文/法文短句及接近M2上限的长文本；由用户传入不含主机名/用户名的`machine_label`，分别写入Git忽略的`output/m2_embedding_benchmarks/{machine_label}.json`。报告记录操作系统、Python和依赖版本、CPU/RAM、PyTorch构建、CUDA/GPU能力、请求/实际设备、精度、初始/有效batch、加载/编码耗时、吞吐、进程峰值RSS、可用时的显存峰值、向量维度/范数和相似度，不记录本机绝对路径或其他个人信息；
11. 步骤四——离线复跑与收口：每台电脑缓存完成后都能禁止网络复跑真实Smoke，确认同一固定revision、推理合同和文本产生满足数值容差的向量及完全相同的cache key；性能指标按机器分别解释，不互相覆盖。当前工作区先完成本机真实报告、聚焦测试、Ruff、Mypy、compileall、pip check、alembic check、全量pytest和Seed复核；同一脚本与报告Schema交付给第二台电脑复跑，第二份报告可在不修改Provider代码的情况下追加；
12. 调用链位置：`未来M2-15 Index Service（本步不实现） → Embedding Provider（本步） → Fake或本地BGE-M3（本步）`。前端、API、对外Schema、Repository、Model写入和PostgreSQL/pgvector业务数据均不经过；M2-13的向量列只作为下游合同，不在本步写入；
13. 每步验证方式：步骤一用纯单元测试证明合同和Fake与硬件无关；步骤二用注入式Fake backend覆盖CPU、CUDA可用、CUDA不可用回退、懒加载、严格校验、错误映射与batch降级，不加载权重；步骤三用显式真实Smoke证明固定BGE-M3能在当前可用设备产生1024维有限归一化向量，并检查相关中英文/跨语言样本的相似度高于无关样本；步骤四用离线复跑、跨机器报告Schema校验、质量工具、全量回归和正式Seed复核证明没有隐式联网或污染数据库；
14. 完成标准：Provider接口和Fake可供M2-15/16复用且不绑定任一电脑；真实模型固定到可审计commit并只从各机受管缓存加载；模型身份包含所有影响向量数值的推理合同，cache key不受机器、设备和batch影响；批量输出数量、顺序、维度、有限值和范数均被严格验证；设备探测和batch降级有可重复测试；当前电脑真实质量/资源报告及离线复跑成功；第二台电脑可用同一命令生成同Schema独立报告；全部代码质量与回归检查通过后同步进度并停止；
15. 主要风险与排查：两台电脑结果不一致时，先分清“性能不同”还是“向量合同不同”；耗时/内存不同是正常现象，cache key不同则优先核对模型commit、Provider版本、池化、最大长度、归一化和精度。模型下载失败查固定revision、网络、代理、缓存目录和磁盘；加载失败查snapshot完整性及依赖版本；内存不足先降batch，不改变模型revision或维度；离线仍联网查是否错误传入Hub ID；GPU不可用先查PyTorch是否为CUDA构建，再查驱动和显存，不能仅凭电脑有独显就强制CUDA，也不能为了统一两台机器而隐式替换PyTorch。

**已解除的待确认停止点**

用户已明确确认以上M2-14方案，可实施本节步骤一至四。该确认不授权M2-15或任何数据库写入、检索、Reranker、RAG、API、前端工作。

### 2026-08-31｜M2-14-01｜Embedding合同、cache key与确定性Fake

**状态：已完成**

1. 目标：建立不依赖硬件和网络的统一Embedding输入/输出边界，让日常测试能够验证真实索引链未来依赖的数量、顺序、维度、用途、身份和cache key规则；
2. 大白话运行过程：调用方交给Provider一批文字并说明是`document`还是`query`；Fake把用途和原文喂给固定SHAKE算法，生成1024个数并归一化，同时用Provider合同、模型身份、用途和原文SHA-256生成cache key，全程不加载模型也不联网；
3. 修改文件：`app/services/retrieval/embedding.py`定义协议、身份、批次结果、cache key、输入边界和Fake；`app/services/retrieval/__init__.py`导出稳定入口；`app/core/errors.py`提供脱敏输入/Provider错误；`app/core/config.py`与`.env.example`固定BGE-M3模型、commit、CLS、8192最大长度、归一化和精度合同；`tests/unit/test_embedding_provider.py`覆盖行为；`tests/unit/test_m2_baseline.py`推进阶段守卫；
4. 调用链位置：`未来M2-15 Index Service（未实现） → EmbeddingProvider协议/Fake（本步）`；前端、API、对外Schema、Repository、Model和PostgreSQL均未经过，正式库没有写入Embedding；
5. 验证方法与结果：先运行新测试观察到缺少`EmbeddingInputError`/Provider模块的预期RED，再补最小实现；`tests/unit/test_embedding_provider.py + tests/unit/test_app_baseline.py`最终`18 passed`；开发前全量基线为`429 passed, 3 skipped`，附件中的5 skipped已由`-rs`确认是过时口径，当前3项分别为2个显式Docling Smoke和1个付费Qwen Smoke；
6. 能证明：Fake对相同合同和输入确定、保持批次顺序、返回1024维有限归一化向量；空白、错误类型、超数量和超长度输入被拒绝；document/query及precision进入cache身份；默认工厂不加载真实模型；真实BGE配置只能使用`BAAI/bge-m3@5617a9f61b028005a4858fdac845db406aefb181`；
7. 不能证明：本地BGE能够加载、离线边界生效、真实输出包含`dense_vecs`且满足维度/范数、设备自动选择、OOM batch降级、语义相似度或性能资源指标；这些属于M2-14-02/03；
8. 数据复核：全量pytest清理共享Seed后，按既有顺序运行`seed_m1`、`seed_m2_files`和`seed_m2_complex_files`恢复；最终M1可售125，M2为10 files/10 documents/10 versions/9 ACL、10个parse/index pending、0 Chunk Set、0 Chunk、0 Embedding，Storage parsed/chunks JSON各0；
9. 风险与排查：Fake异常先查输入是否为空/超界、用途是否为枚举值、合同字段是否漏入cache key；跨机器cache key不同先查model/revision/pooling/max length/normalize/precision和原文是否完全一致，不查设备或batch；
10. 下一步：只进入M2-14-02，先用可注入后端测试本地BGE懒加载、离线快照、设备策略、输出校验和batch降级，不下载权重。

### 2026-08-31｜M2-14-02｜本地BGE懒加载、离线快照与严格校验

**状态：已完成**

1. 目标：在不下载权重的前提下实现真实Provider的运行边界，确保它只从固定本地快照懒加载，并对设备、精度、模型输出和内存降级作可重复验证；
2. 大白话运行过程：创建Provider时只检查“本地模型身份证”是否写着固定model id和commit，并根据当前PyTorch能力决定CPU/CUDA；第一次收到文本时才设置Hugging Face/Transformers离线标志、加载一次本地模型，再按document调用`encode_corpus`、按query调用`encode_queries`。若识别到内存不足，batch从4减到2再减到1；其他异常直接脱敏失败；
3. 修改文件：`app/services/retrieval/embedding.py`新增`BgeM3EmbeddingProvider`、本地snapshot manifest校验、设备选择、FlagEmbedding加载参数、用途路由、OOM分类/降级和`dense_vecs`严格校验；`app/services/retrieval/__init__.py`导出真实Provider；`tests/unit/test_embedding_provider.py`以注入式后端覆盖慢模型边界，不加载权重；
4. 调用链位置：`未来M2-15 Index Service（未实现） → EmbeddingProvider → 本地BgeM3EmbeddingProvider → FlagEmbedding（注入式替身验证）`；前端、API、Schema、Repository、Model、PostgreSQL/pgvector均未经过；
5. 验证方法与结果：先观察缺少BGE类型/快照合同的RED，再补最小实现；新增CPU、CUDA可用、auto回退、非法CUDA/CPU半精度、快照revision不符、缺少dense、数量不符、非1024维、NaN、未归一化、懒加载一次、document/query、4→2→1和非OOM不重试测试；另用RED确认内建`MemoryError`在batch=1时必须返回`retryable=True`脱敏错误；聚焦组合最终`72 passed`，Ruff通过，Mypy对Provider和测试通过；
6. 能证明：工厂和构造不加载模型；固定快照身份不符会在加载前拒绝且错误不含路径；`auto`只在`torch.cuda.is_available()`为真时选CUDA；CPU机器拒绝伪装成float16/bfloat16合同；离线环境、`trust_remote_code=False`和本地路径会传给加载边界；只有可识别内存不足会降batch，batch=1仍失败时安全返回；输出数量、1024维、有限值、L2范数和`dense_vecs`都被检查；
7. 不能证明：FlagEmbedding真实构造参数与当前安装版本/权重完全兼容、固定快照已下载、真实中英/跨语言相似度、长文本、实际CPU耗时/RSS或离线真实复跑；这些属于M2-14-03/04；
8. 风险与排查：构造即失败先查snapshot manifest是否存在且model/revision精确匹配；auto选择错误先查当前PyTorch构建和`torch.cuda.is_available()`，不能只看显卡；输出拒绝先查是否只请求dense以及模型是否启用normalize；只有内存错误才看batch链，格式错误不要用降batch掩盖；
9. 下一步：只进入M2-14-03，以TDD实现显式下载和版本化基准脚本，再下载固定commit并进行真实Smoke。

### 2026-08-31｜M2-14-03/04｜显式下载、真实Smoke、逐机基准与离线复跑

**状态：已完成**

1. 目标：让每台电脑用同一命令显式获取固定BGE-M3 commit，生成不含机器身份的独立版本化报告，并证明缓存完成后可完全离线复跑；
2. 大白话运行过程：脚本先检查本地快照身份证；只有出现`--allow-download`才临时允许Hub联网，并始终传`BAAI/bge-m3@5617a9f61b028005a4858fdac845db406aefb181`。下载完成写marker，随后Provider切回离线、加载模型并编码固定中/英/德/法语料和680单位长文本，测量加载/编码/RSS并比较相关与无关相似度，最后按匿名`machine_label`写报告；
3. 修改文件：`scripts/benchmark_m2_embedding.py`实现固定下载、匿名label、硬件探测、RSS/GPU峰值、质量样本和报告Schema；`tests/unit/test_m2_embedding_benchmark.py`验证无授权不下载、固定参数、报告字段与隐私边界；`tests/smoke/test_bge_m3_embedding_smoke.py`提供两个显式真实Smoke；`app/services/retrieval/embedding.py`增加基准使用的幂等显式预热；
4. 下载处理：第一次默认30文件/8并发在非认证Hub环境两次中断，且未写完成marker；固定commit文件清单表明仓库同时含本步不使用的整套ONNX和图片资产。通过RED/GREEN把合同收紧为忽略`onnx/**`/图片/`.DS_Store`并使用单worker，仍下载同一commit的完整PyTorch推理文件；第三次成功，受管缓存约2191.2 MiB且被Git忽略；
5. 调用链位置：`基准/未来M2-15 → EmbeddingProvider → 本地BGE-M3 snapshot → FlagEmbedding/PyTorch CPU`；前端、API、对外Schema、Repository、Model、PostgreSQL业务写入和pgvector检索均未经过；
6. 单元与真实验证：下载/报告单测`11 passed`；Provider/脚本/Smoke普通聚焦`39 passed, 2 skipped`，Ruff通过、Mypy 5文件通过；显式`RUN_BGE_M3_SMOKE=1`真实执行`2 passed in 18.70s`。首次真实运行成功后，再显式设置`HF_HUB_OFFLINE=1`和`TRANSFORMERS_OFFLINE=1`、不传`--allow-download`复跑成功，四个相似度与首跑完全一致；
7. 当前机器报告：`output/m2_embedding_benchmarks/machine-a.json`，Schema `m2-embedding-benchmark-v1`；PyTorch `2.13.0+cpu`、请求`auto`、实际`cpu`、初始/有效batch均4、float32；加载7.232343秒、编码6.731294秒、吞吐1.04文本/秒、进程峰值RSS 2261.5 MiB、峰值增量1373.0 MiB；CUDA不可用所以显存峰值为null；
8. 数值与质量：7个向量均为1024维，范数min/max均1.0；中文相关/无关相似度`0.840595 > 0.348997`，英文查询对德文相关/法文无关相似度`0.731607 > 0.308162`；长文本为680个`m2-unicode-token-counter-v1`单位；报告含7个稳定cache key；
9. 双机合同：Provider合同、model id、revision、CLS、8192、normalize、precision和原文SHA进入身份/cache key；设备和batch不进入，单测真实比较CPU batch1与模拟CUDA batch4得到相同身份/cache key。第二台电脑可用同一命令仅更换匿名label生成独立报告，不修改Provider代码；不同硬件允许耗时、RSS、显存和浮点值在合理容差内不同；
10. 隐私与数据：实际报告检查确认不含hostname、username或工作区绝对路径；模型缓存与`output/`均被Git忽略。脚本/Smoke没有调用Repository或数据库，正式演示库仍应在最终收口中复核0 Chunk/0 Embedding；
11. 能证明：固定PyTorch快照可下载并被当前FlagEmbedding 1.4.2真实加载；当前CPU机器能离线生成满足合同的多语言/长文本向量，相关样本排序优于无关样本；报告Schema、硬件差异字段、隐私边界和跨device/batch cache key规则可重复；
12. 不能证明：第二台电脑尚未实际生成报告；当前CPU报告不能代表GPU性能/显存或其他机器数值；7个合成样本不能证明大规模检索召回率、业务Golden Chunk质量、HNSW性能、索引入库、关键词/Dense/混合检索、Reranker或RAG答案质量；
13. 风险与排查：下载失败先查非认证限流/网络，保持固定revision与单worker断点续传，不改为浮动main；加载失败查顶层`pytorch_model.bin`和tokenizer文件及marker，不改用ONNX掩盖问题；CPU太慢先降batch或换第二台CUDA机器，不能隐式替换PyTorch；相似度顺序失败先核对固定语料、precision和revision；
14. 下一步：只做M2-14最终质量、全量pytest、Alembic和正式Seed/Storage复核，完成后更新状态并停止等待M2-15授权。

### 2026-08-31｜M2-14-FINAL｜最终收口验证

**状态：已完成**

1. 本步解决的问题：把M2-14从“当前机器真实模型可运行”收口为“接口、错误边界、并发加载、离线模型、匿名报告、全量回归和正式数据边界均有证据”，同时把停止点推进到M2-15方案确认前；
2. 大白话运行过程：日常测试默认使用Fake，不碰网络和2.1 GiB模型；真实验证必须显式下载固定commit，之后Provider只从本地快照读取。第一次真实请求由锁保护，只加载一次模型；文本按query/document分别编码，内存不足才逐级减小batch；返回值必须逐个通过数量、1024维、有限值和归一化检查，最后基准脚本只写匿名机器报告；
3. 最终修改文件与职责：`.env.example`、`app/core/config.py`冻结模型和推理配置；`app/core/errors.py`提供脱敏错误；`app/services/retrieval/__init__.py`和`embedding.py`提供协议、Fake、BGE、cache key、离线快照、并发懒加载及严格校验；`scripts/benchmark_m2_embedding.py`负责显式固定下载和逐机报告；两个单元测试文件及真实Smoke覆盖合同；本文件和`docs/PROJECT_PROGRESS.md`保存完成证据和停止点；
4. 代码复核后的补强：用8线程测试复现首次并发请求会重复加载8次，加入双重检查锁后固定为1次；快照校验要求顶层权重和Tokenizer关键文件存在、非空且`stat`失败也只返回脱敏错误；命令行顶层错误不再泄露绝对路径；匿名label除格式外还拒绝包含当前用户名或主机名；CPU `DefaultCPUAllocator`/`not enough memory`等PyTorch内存错误进入batch降级；cache key增加固定黄金值，防止序列化规则悄然漂移；
5. 真实模型与报告：本机受管缓存固定为`BAAI/bge-m3@5617a9f61b028005a4858fdac845db406aefb181`，约2191.2 MiB并被Git忽略。最终强制离线报告为`output/m2_embedding_benchmarks/machine-a.json`，Schema为`m2-embedding-benchmark-v1`；请求`auto`、实际`cpu`、float32、初始/有效batch均4；加载7.267674秒、编码6.548403秒、吞吐1.069文本/秒、RSS峰值2269.8 MiB、峰值增量1381.9 MiB，CUDA不可用所以显存峰值为null；
6. 数值和Smoke结果：最终报告7个向量均为1024维，范数min/max均1.0；中文相关/无关`0.840595 > 0.348997`，英文查询对德文相关/法文无关`0.731607 > 0.308162`，680单位长文本成功。最终显式真实Smoke为`2 passed in 19.23s`；
7. 最终自动验证：全量`pytest -q`为`476 passed, 5 skipped in 40.18s`，5项均是需要显式外部条件的Smoke（2个Docling、2个BGE、1个Qwen）；Ruff检查和格式检查通过；Mypy对100个源码文件通过；`compileall`、`pip check`、`git diff --check`通过；Alembic current/heads均为`20260831_0006 (head)`且`alembic check`没有新操作；
8. 正式数据复核：全量测试后按既有顺序恢复M1、M2普通和M2复杂Seed；PostgreSQL/pgvector健康，最终为10 files、10 documents、10 versions、9 ACL、10 parse pending、10 index pending、0 Chunk Set、0 Chunk、0非空Embedding，M1可售库存125；Storage为10 uploads、0 parsed JSON、0 chunks JSON。证明M2-14没有污染业务库或提前发布索引；
9. Git边界：全过程保留`main`和用户未提交的M2改动，HEAD仍为`960559a13281555f2b3d52d27e9e4fc7552fcc05`；没有reset、checkout、commit或push，模型缓存和基准输出均未进入Git；
10. 完整调用链位置：`未来M2-15 Index Service（未实现） → EmbeddingProvider协议 → Fake或本地BGE-M3`。前端、API、对外Schema、Repository、Model写入、PostgreSQL/pgvector业务写入、关键词/Dense/混合检索、RRF、Reranker和RAG回答均未经过；
11. 能证明和不能证明：能证明当前CPU机器在固定依赖与固定revision下可真实、离线、稳定地产生满足合同的向量，且日常测试不隐式下载；不能证明第二台电脑/GPU性能、大规模召回率、35个Golden Chunk入库、HNSW查询性能或端到端RAG质量。第二台报告是待补的跨机器证据，不是本机M2-14阻塞；
12. 风险与排查：普通测试意外下载先查Provider是否收到Hub ID而非本地snapshot；加载失败先查marker、顶层权重和Tokenizer文件；内存不足先观察有效batch是否下降，再看约2.3 GiB进程峰值；两机cache key不同先核对revision、pooling、max length、normalize、precision和原文，不比较设备/batch；相似度变化先核对固定语料和依赖；数据库出现Chunk/Embedding则优先查是否误执行了后续索引脚本；
13. 下一步停止点：M2-14至此完成。当前授权不包含M2-15；必须先提交M2-15阶段实施方案并取得用户明确确认，才能继续开发。

## 27. M2-15｜幂等索引、失败重试和版本原子激活管线实施方案

### 2026-08-31｜M2-15-PLAN｜待确认方案

**状态：待确认。本节只记录只读盘点和未来实施方案；本轮没有编写运行代码、创建迁移、下载模型或修改数据库数据。**

### 27.1 开始前现状与只读核对

1. Git真实基线与用户摘要一致：当前分支为`main`，HEAD与本地`origin/main`均为`960559a13281555f2b3d52d27e9e4fc7552fcc05`；远端完整地址为`https://github.com/luchunjin115/deep-search-pro-master.git`；M2-12、M2-13、M2-14修改和未跟踪文件全部保留，本轮没有reset、checkout、clean、commit或push；
2. M2-11已有`DocumentParserService`：短事务领取`pending/failed → parsing`，事务外读取Storage并运行Router，解析JSON不可覆盖发布，短事务写`ready`；普通异常会清理本次对象并写`failed`，ready版本重复解析会冲突；
3. M2-12已有`DocumentChunkService`：严格读取并验真解析JSON，推导确定性Chunk Set ID，短事务领取`pending/failed → chunking`，事务外切块和发布，短事务写`ready`；失败可用同一ID重试，相同孤儿字节可复用，ready或chunking批次不会被第二次领取；
4. M2-13已有`document_chunks`、独立`fts_text`、生成`search_vector`、GIN、可空`vector(1024)`、余弦HNSW、模型/revision列，以及tenant/document/version/Chunk Set复合外键；但当前没有把Chunk Artifact转换为数据库行的Repository或Service；
5. M2-14已有`EmbeddingProvider`、Fake和本地BGE-M3。Provider输入保留顺序，区分`document/query`，返回同数量向量和逐文本cache key，并严格检查1024维、有限值和L2归一化；本地BGE固定`BAAI/bge-m3@5617a9f61b028005a4858fdac845db406aefb181`且只读本地快照；
6. 现有`DocumentService`已经具备创建逻辑文档、增加版本、`index_status`状态和ready后切换`documents.active_version_id`的内部能力，但这些Document操作没有HTTP路由；现有HTTP只有文件上传、列表、状态、下载和软删除；
7. 当前没有`IndexService`、索引Repository、Chunk行导入、索引API、Dense/Lexical/Hybrid查询或Reranker；`app/services/retrieval/`实际只有Embedding Provider；
8. 只读运行基线：PostgreSQL与pgvector健康，pgvector为0.8.6，Alembic current/heads均为`20260831_0006 (head)`；GIN与HNSW索引存在；正式库为10 files、10 documents、10 versions、9 ACL、10个`parse/index=pending`、0 active version、0 Chunk Set、0 Chunk、0非空Embedding；M1可售库存125；Storage为10 uploads、0 parsed JSON、0 chunks JSON；
9. 文档差异：总看板当前状态已经写明M2-14完成，但“最近完成”列表此前停在M2-13；本轮只补齐这个文档摘要，不改变M2-14既有验证结论。

### 27.2 当前真正缺少的能力

大白话说，现有项目已经有“原文件仓库”“解析器”“切块器”“向量翻译器”和“数据库货架”，但缺少一个总管把它们按顺序串起来，并决定哪一套索引现在正式生效。具体缺少：

- 一个严格的索引输入、输出和确定性索引身份；
- 一个把`CanonicalChunkArtifact.chunks`逐行转换成`document_chunks`的Mapper。Mapper就是“字段搬运规则”，保证正文、定位、表格和向量不会错位；
- 一套短事务领取、失败关闭、完整保存和激活Repository；
- 同一请求重复执行时复用成功结果、普通失败后重试同一身份的规则；
- 新版本与同版本重新索引都能“先在旁边做好，再一次切换”的数据库表达；
- 获权的同步索引HTTP入口，以及创建初始文档和新增版本的最小上游入口；
- 对解析、切块、Embedding、保存、并发、软删除、崩溃窗口和Seed恢复的整链测试。

### 27.3 本阶段目标与明确不做

**目标**

实现一条同步、可重试、可审计的最小摄取链：

```text
validate
→ ensure parse
→ ensure chunk
→ claim index set
→ embed retrieval_text
→ save all Chunk rows
→ atomically activate index set/version
→ ready
```

其中“原子”是指一组数据库改动要么全部提交，要么全部回滚。新版本或新索引集准备完成前，旧active版本/索引集继续保持；最终只用一次短事务切换指针。

**明确不做**

- 不实现关键词、Dense、混合、RRF或任何查询接口；
- 不实现BGE Reranker、RAG答案、引用、聊天、Agent Tool或前端；
- 不修复图文DOCX 0/2；
- 不引入Redis/Celery、持久Worker、租约回收、MCP、MinIO或RAGFlow；
- 不物理清理软删除文档的Storage或索引历史；
- 不修改M2-12 Chunk算法和M2-14模型合同，不下载新模型；
- 不进行与M2-15无关的重构，不提前实现M2-16/17。

**前置条件**

1. 用户先明确确认本方案；确认前不创建`0007`、不新增索引代码或API；
2. 保留当前`main@960559a13281555f2b3d52d27e9e4fc7552fcc05`上的全部M2-12/13/14未提交改动，不reset、覆盖或清理；
3. M2-11 Parser发布、M2-12 Chunk发布、M2-13 Chunk表/GIN/HNSW和M2-14 Provider合同继续作为上游，不在M2-15改写其核心语义；
4. 开始迁移步骤时，PostgreSQL/pgvector必须健康且Alembic从`20260831_0006`单head起步；若实际状态变化，先停下报告；
5. 日常测试使用Fake Provider；显式真实Smoke只允许读取M2-14已经存在且manifest匹配的固定本地BGE快照，缺快照就跳过或报告，不联网下载；
6. 正式验收前后都以10/10/10/9、10个parse/index pending、0 Chunk Set/Chunk/Embedding、M1可售125和Storage 10 uploads/0 parsed/0 chunks为恢复基线。

### 27.4 输入、输出与上下游关系

**索引任务输入**

- 服务端可信`CurrentUser`；
- URL中的`document_id`和`version_id`；
- 服务端集中配置产生的Chunker身份、Embedding身份和FTS构建版本；
- 不接受调用方传入tenant、owner、Storage Key、模型路径、模型ID、revision、SQL或向量。

**索引任务输出**

- `index_set_id`、`document_id`、`version_id`、`chunk_set_id`；
- `status=ready`、是否复用既有结果、是否切换文档版本；
- 实际`embedding_model`和`embedding_version`；
- Chunk总数、文本/表格数和完成时间；
- 不返回Storage Key、本机路径、原始向量、数据库异常或模型缓存路径。

**完整调用链**

```text
前端（M2-15不实现）
→ FastAPI Documents API
→ Pydantic Schema
→ DocumentIndexService
→ DocumentParserService / DocumentChunkService / EmbeddingProvider / Storage
→ DocumentIndexRepository
→ DocumentIndexSet / DocumentChunk / DocumentVersion / Document Model
→ PostgreSQL / pgvector
```

M2-15经过API、Schema、Service、Repository、Model、PostgreSQL/pgvector；不经过检索查询、Reranker、Qwen、Evidence、Agent或前端。

### 27.5 首次、重复、重试、重新索引和新版本如何区分

索引身份由服务端确定性生成，不使用时间或随机数：

```text
index_set_id = UUIDv5(
  chunk_set_id
  + index_schema_version
  + embedding_identity_sha256
  + embedding_purpose=document
  + fts_builder_version
)
```

`embedding_identity_sha256`覆盖M2-14的合同版本、Provider、model id、revision、pooling、max length、normalize、precision和维度；设备和batch只影响性能，不进入身份。

- **首次索引**：目标版本还没有active index set；构建成功后第一次设置版本和文档指针；
- **重复索引请求**：当前服务端身份推导出同一`index_set_id`，且该索引集已经ready并仍与Chunk行/统计一致；直接返回`reused=true`，不重新解析、Embedding或增加Chunk；
- **失败重试**：同一`index_set_id`处于failed；`attempt_count + 1`后重新执行，成功仍使用同一身份；
- **重新索引**：同一文档版本已经有active index set，但Chunk配置、FTS构建版本或Embedding身份发生变化，因而推导出新的`index_set_id`；新结果在旁边构建，成功后只切换版本的active index set；
- **新文档版本**：使用不同`version_id`和通常不同`file_id/content_hash`；旧`documents.active_version_id`保持不变，只有新版新索引集完整ready后才一次切到新版；
- **同一身份的强制重建**：V1不提供绕过幂等身份的“强制覆盖”开关。若ready结果损坏，应作为一致性故障显式处理，不能静默覆盖审计历史。

**如何复用M2-11和M2-12**

- Index Service不会对ready版本机械再次调用`parse_version`，因为M2-11的既有合同会正确拒绝这种调用；它先核对ready记录、Storage对象和Artifact Hash，完整才直接复用，只有pending/failed才调用原Parser Service；
- Chunk阶段根据实际Parsed Artifact和当前Chunk配置推导M2-12确定性Chunk Set ID；ready且Artifact验真通过就复用，pending/failed才通过一个很薄的“ensure”入口进入既有`chunk_version`领取/发布逻辑；不会复制第二套Chunker或绕开M2-12不可覆盖Storage边界；
- parsing/chunking中的并发请求返回409，不启动第二次慢操作；发现ready记录与Artifact不一致则报一致性故障，不静默重建同一身份。

### 27.6 重要设计选择与推荐

#### 方案A：不迁移，直接删除/重写`document_chunks`

优点是文件少；缺点是`document_versions.index_status`既要表示旧索引可用，又要表示新尝试正在运行，同一个字段无法同时表达两件事。同一版本重新索引时，若改成`indexing`，未来检索会错误隐藏仍可用的旧结果；若保持`ready`，失败和并发又没有独立审计状态。也无法可靠区分同一Chunk Set的不同Embedding revision。

#### 方案B：把`document_chunk_sets`同时当作索引代次

比方案A清楚，但Chunk Set身份故意只由解析内容、Chunker、Counter和配置决定；把Embedding revision塞进Chunk Set会破坏M2-12已经冻结的确定性语义，也会为相同切块重复保存Artifact。

#### 方案C：新增确定性`document_index_sets`（推荐）

“Index Set”就是一套可独立准备、失败、重试和激活的索引成品。它引用一个ready Chunk Set，再记录Embedding完整身份、FTS构建版本、状态、尝试次数、统计和错误。`DocumentVersion`保存`active_index_set_id`，`DocumentChunk`保存`document_index_set_id`。这样旧索引集能在新索引集构建期间继续服务，成功后只切一个指针；同一Chunk Set也可以安全对应不同Embedding revision。

这是本阶段唯一推荐方案。它新增一张小表和一个迁移，但直接解决本阶段明确要求的重新索引、失败审计和原子激活，不是为未来功能预建无关架构。

### 27.7 推荐数据模型与迁移

需要新增`20260831_0007`迁移，因为现有模型不足以表达“同一版本的旧索引仍ready，同时新索引正在构建”。推荐最小变化：

1. 新增`document_index_sets`：
   - 确定性`id`；
   - `tenant_id/document_id/document_version_id/document_chunk_set_id`复合身份和外键；
   - `index_schema_version`、完整`embedding_identity_json`及其SHA-256、`embedding_model`、`embedding_version`、`fts_builder_version`；
   - `pending/indexing/ready/failed`、`attempt_count`、开始/完成时间、安全错误摘要、Chunk统计；
   - 数据库CHECK只保证Index Set自身的ready/failed字段形状完整；CHECK不能跨表统计子Chunk行数，实际行数必须由最终事务锁定后核对；
2. `document_versions`新增可空`active_index_set_id`；复合外键同时带上tenant/document/version和`document_versions.index_status → document_index_sets.status`，再用CHECK要求“指针非空时版本状态必须为ready”，从而在数据库层拒绝跨边界指针和指向非ready候选；`index_status`继续表示该版本是否有可用索引；
3. `document_chunks`新增非空`document_index_set_id`和`embedding_cache_key`；唯一边界从“Chunk Set+Chunk”改为“Index Set+Chunk”，同时保留Chunk Set复合外键，允许同一切块对应不同Embedding revision；
4. 正式表当前0行，因此迁移可以直接建立严格非空约束，不需要伪造回填向量或模型身份；
5. `embedding_model`保存实际Provider identity的`model_id`：正式环境为`BAAI/bge-m3`，Fake测试为`fake/m2-deterministic`；`embedding_version`保存实际identity的`revision`：正式环境为`5617a9f61b028005a4858fdac845db406aefb181`，Fake为`m2-fake-v1`；完整推理合同另存于Index Set identity JSON/hash，避免只靠两列丢失pooling、长度或精度审计。

### 27.8 Chunk Artifact转数据库行与顺序保证

1. 从ready Chunk Set记录取得内部`chunk_storage_key`，有界读取JSON；
2. 用`CanonicalChunkArtifact.model_validate_json`重新验真，并逐项核对tenant/document/version、Chunk Set ID、输出Hash和统计；
3. 按Artifact中已经连续的`chunk_index=1..N`构造`texts = [chunk.retrieval_text, ...]`；Embedding使用`retrieval_text`，因为它在`body_text`之外明确加入标题路径、Sheet/范围等检索上下文，M2-12就是为语义检索设计该字段；`body_text`仍原样保存供未来引用；
4. 调用`provider.embed(texts, purpose=DOCUMENT)`；Provider已校验向量数量和顺序，Mapper再用`zip(chunks, vectors, cache_keys, strict=True)`逐个配对，并重新计算每个cache key，防止调用边界错位；
5. `fts_text`在M2-15固定为`retrieval_text`的原样V1视图，并把`m2-fts-raw-retrieval-v1`写入Index Set身份；这只填充M2-13已存在的生成列，不实现关键词查询或中文分词。当时路线图称M2-17，现M2-16.2改变构建规则时将产生新的Index Set身份；
6. 行ID使用`UUIDv5(index_set_id + chunk_id)`，JSONB字段直接使用M2-12严格模型的`model_dump(mode="json")`，不手工重解释定位和表格；
7. 插入前后都验证Chunk数量、连续序号、模型/revision和Index Set身份，唯一约束作为最后一道防重复保护。

### 27.9 事务、失败恢复和原子激活

**事务外的慢操作**

- Storage读取；
- Parser Router/Docling；
- 结构感知切块和JSON发布；
- Fake或真实BGE Embedding；
- JSON/Pydantic转换。

这些操作可能耗时数秒到数十秒，不能占着数据库事务和行锁。

**短事务一：领取索引集**

- 再次校验tenant/document/version/Chunk Set、管理权限和软删除；
- 确定性插入pending，只有pending/failed可条件更新为indexing并增加attempt；
- 已ready且身份/行数一致时直接复用；已indexing时返回409，避免双worker；
- 新版本没有旧索引时可把版本高层状态设为indexing；已有active index set的重新索引保持版本ready，候选进度由Index Set记录，旧结果不消失。

**短事务二：完整保存和激活**

在同一事务内：

1. 锁定并重读目标Document、Version、File、Chunk Set和Index Set；
2. 确认资源未软删除、候选仍indexing、身份和Hash未变化；
3. 一次性插入该Index Set全部`document_chunks`，核对数据库行数等于Artifact统计；
4. 把Index Set标为ready并写统计；
5. 设置`document_versions.active_index_set_id`和`index_status=ready`；首次索引时把关联`files.index_status`也设为ready；
6. 若目标Version不是当前active，再设置`documents.active_version_id=version_id`；
7. 提交。

任一步失败都会整体回滚，因此不会出现“状态ready但只有一半Chunk”或“新版本已经active但向量没保存完”。

**失败处理**

- 解析失败：沿用M2-11，写`parse_status=failed`且无解析半成品；目标版本没有旧active索引时再把版本及关联文件的高层`index_status`记为failed，已有旧active时保持ready；
- 切块失败：沿用M2-12的Chunk Set failed；同样只在没有旧active索引时把版本及关联文件的高层索引状态记为failed，索引总管只返回脱敏可重试错误；
- Index Set只有在ready Chunk Set确定后才能推导；因此解析/切块阶段的失败分别审计在Version parse状态和Chunk Set状态中，不伪造一个身份尚未确定的Index Set；
- Embedding失败：不写Chunk行；短事务把候选Index Set标为failed；
- 最终数据库保存失败：插入、状态和指针全部回滚，再用独立短事务把候选标failed；
- 新版本失败：旧`documents.active_version_id`和旧active index set不变；
- 已有可用索引的重新索引失败：版本仍ready，旧`active_index_set_id`不变，失败只记录在候选Index Set；
- 没有旧可用索引的首次失败：版本`index_status=failed`，文件failed；重试仍使用同一确定性Index Set ID；
- 普通Python/数据库/模型异常只返回固定错误，不泄露路径、SQL或模型内部细节。

### 27.10 删除、隔离和V1崩溃边界

- 所有写入和复用都同时核对`tenant_id/document_id/version_id/chunk_set_id/index_set_id`；任何一层不一致都失败，不能只凭全局UUID挂接；
- 只有文档owner或同租户`company_owner`可创建版本或索引；ACL只读用户不可管理索引；无权与不存在保持统一404；
- 文件或文档软删除后，M2-15拒绝新索引和复用。历史Index Set/Chunk暂时物理保留用于审计；M2-16/17未来查询必须同时过滤document/file未删除、active version和active index set。硬删除时由复合外键级联清理数据库行；Storage物理垃圾回收不在本阶段；
- V1能保证：应用捕获到的普通失败会清理/回滚半成品、保留旧active、同一确定性身份可重试、重复成功请求不增行；
- V1暂时不能保证：进程被强杀、机器断电或数据库连接在领取后永久中断时自动恢复。此时可能留下`parsing/chunking/indexing`状态或Storage孤儿；没有租约、心跳、后台Worker或自动巡检。再次请求会安全冲突而不是双写，需要人工核对后恢复；这些能力不在M2-15扩展。

### 27.11 API建议

M2-15应实现最小API，否则M2-06上传后的`file_id`无法在真实调用链创建Document/Version并触发索引。根据实际代码，不再把这些动作机械塞进`files.py`，而新增职责清楚的`documents.py`路由：

- `POST /api/v1/documents`：复用`DocumentCreateInput`，把当前用户拥有且未关联的上传文件创建为初始版本，成功201；
- `POST /api/v1/documents/{document_id}/versions`：复用`DocumentVersionCreateInput`，为获权管理的Document增加新版本，成功201；
- `POST /api/v1/documents/{document_id}/versions/{version_id}/index`：无请求体，所有算法/模型身份来自服务端配置；同步成功或幂等复用均返回200 `DocumentIndexPublication`；同一候选处理中返回409；非法状态409；未登录401；无权或不存在404；安全运行失败500且标明可重试错误码；
- 返回Schema不包含tenant、owner伪造字段、Storage Key、路径、向量、SQL或模型缓存；
- 本步不增加Document列表、关键词搜索、Dense搜索、混合检索、问答或前端端点。

V1推荐同步API：请求会等到本次索引成功或失败后再返回。原因是当前没有持久任务队列、Worker和租约；只返回202却不能保证后台任务在进程退出后继续运行，会制造虚假的可靠性。代价是大文件可能碰到HTTP或反向代理超时，所以客户端可用同一URL安全重试，部署时也要给同步索引设置明确超时。异步任务化留待具备持久Job和崩溃恢复后单独设计。

### 27.12 按顺序实施的小步骤

#### M2-15.1｜冻结Index Set合同、模型和迁移

- 目标：先建立可并存、可重试、可激活的确定性Index Set及数据库硬约束；
- 预计文件：修改`app/models/knowledge.py`、`app/models/__init__.py`、`migrations/env.py`；新增`migrations/versions/20260831_0007_document_index_sets.py`、`tests/integration/test_document_index_set_migration.py`；扩展`tests/unit/test_knowledge_models.py`和阶段守卫；
- 调用链：Model → Alembic → PostgreSQL/pgvector；不经过API、Embedding或检索；
- 验证：先写失败测试；真实执行`0006 → 0007 → 0006 → 0007`；验证跨tenant/document/version/Chunk Set拒绝、状态字段形状拒绝、active索引指针归属、active指向非ready候选拒绝、同Chunk Set不同Embedding Index Set可并存、级联删除和`alembic check`。同时明确子Chunk行数一致性由Repository最终事务验证，不虚称CHECK可以跨表计数。

#### M2-15.2｜实现确定性索引身份和Chunk行Mapper

- 目标：无数据库地证明Artifact、向量、cache key和行字段一一对应；
- 预计文件：新增`app/services/documents/indexing/contracts.py`、`app/services/documents/indexing/mapping.py`、`app/services/documents/indexing/__init__.py`、`tests/unit/test_document_index_mapping.py`；
- 调用链：Canonical Chunk Artifact + EmbeddingBatch → DocumentChunk写入事实；不执行SQL；
- 验证：先写失败测试；覆盖文本/表格JSONB、`retrieval_text`输入、raw FTS视图、模型/revision、严格zip顺序、cache key复算、确定性Index Set/行UUID、数量/身份/Hash篡改拒绝；断言没有搜索查询函数。

#### M2-15.3｜实现Index Repository的领取、失败和原子完成

- 目标：把并发幂等和最终原子切换固定在SQL层；
- 预计文件：新增`app/repositories/document_indexes.py`并公开；新增`tests/integration/test_document_index_repository.py`；按需小幅扩展`app/repositories/documents.py`/`files.py`；
- 调用链：Repository → Index Set/Chunk/Version/Document/File Model → PostgreSQL；
- 验证：先写失败测试；覆盖同ID双领、failed重试attempt增加、ready复用、批量行+状态+指针同事务提交、任一行失败全回滚、旧active保持、重新索引只切active index set、新版本只在ready后切active version、软删除和跨边界拒绝。

#### M2-15.4｜实现DocumentIndexService编排

- 目标：复用M2-11/12/14串起validate→parse→chunk→embed→save→ready；
- 预计文件：新增`app/services/documents/indexing/service.py`；小幅扩展`DocumentChunkService`提供“确保当前确定性Chunk Set”的幂等入口而不改变既有`chunk_version`冲突合同；扩展`app/core/errors.py`、`app/services/documents/__init__.py`、依赖工厂和`tests/integration/test_document_index_service.py`；
- 调用链：Index Service → Parser/Chunk/Storage/Embedding → Repository → PostgreSQL；
- 验证：先写失败测试；Fake Provider覆盖首次、重复不增行、parse/chunk复用、解析/切块/Embedding/DB失败、同ID重试、并发409、顺序、旧active、新版本切换、同版本新Embedding身份切换、文件/文档软删除、跨tenant/文档/版本拒绝。测试比较调用次数，证明重复ready请求不再调用Provider。

#### M2-15.5｜接入最小Documents API

- 目标：让上传后的文件能创建初始Document/新Version并显式同步索引；
- 预计文件：新增`app/api/routers/documents.py`；修改`app/api/routers/__init__.py`、`app/api/dependencies.py`、`app/main.py`、`app/schemas/knowledge.py`、`app/schemas/__init__.py`；新增`tests/integration/test_document_index_api.py`；
- 调用链：HTTP API → Schema → Document/Index Service → 下游全链；
- 验证：201创建文档/版本、200首次/复用索引、401/404/409/422/500、OpenAPI合同、owner/company_owner、ACL读者拒绝、响应脱敏；通过路由清单和源码守卫证明没有任何search/dense/lexical/hybrid/RAG端点。

#### M2-15.6｜真实Smoke、故障矩阵、Seed恢复与收口

- 目标：证明正式Chunk能逐行入库、真实BGE身份能落库，并把正式环境恢复到原始0索引基线；
- 预计文件：新增`scripts/verify_m2_index_pipeline.py`、`tests/unit/test_m2_index_pipeline_verification.py`、可显式启用的`tests/smoke/test_document_index_bge_smoke.py`；更新本文件和总看板；
- 调用链：版本化Seed → Index Service全链 → PostgreSQL/pgvector；仍不调用查询Service、Qwen或前端；
- 验证：日常全量使用Fake且不加载模型；正式10文档验收核对35个Chunk字段/顺序/统计、重复运行行数不增、失败恢复和active指针；真实BGE Smoke只读取M2-14现有固定本地快照，至少索引一份小文档并核对`BAAI/bge-m3`和固定revision，不执行下载；随后精确删除本次parsed/chunks对象和索引行，按既有Seed入口恢复；最后运行全量pytest、Ruff、format check、Mypy、compileall、pip check、Alembic current/heads/check和`git diff --check`。

每个小步骤完成后先验证、更新阶段记录并停下汇报；M2-15方案确认后先开始M2-15.1，不自动跨到M2-16。

### 27.13 全量测试后的正式Seed与Storage恢复

1. 测试优先使用事务回滚、临时Storage和独立固定ID，避免把正式Seed当普通夹具反复清空；
2. 正式验收脚本开始前记录10个版本、预期对象Key和现有0索引计数；
3. 验收结束只按本次Index Set、Chunk Set和Version精确删除生成的数据库行及parsed/chunks对象，禁止清空整个Storage根目录或命名卷；
4. 按既有幂等顺序运行M1、`m2-v1`、`m2-complex-v1` Seed恢复入口，不手工插入业务行；
5. 最终复核：10 files、10 documents、10 versions、9 ACL、10 parse pending、10 index pending、0 active version、0 Chunk Set、0 Index Set、0 Chunk、0非空Embedding、M1可售125；Storage 10 uploads、0 parsed JSON、0 chunks JSON；PostgreSQL/pgvector healthy、Alembic `0007 head`；
6. 如果恢复或计数不一致，阶段保持进行中/受阻，不能标记完成。

### 27.14 阶段完成标准

1. M2-15.1至M2-15.6均完成代码、实际验证和步骤日志；
2. 迁移可往返，Index Set、active index pointer和Chunk归属受数据库复合约束；
3. 首次、重复、失败重试、重新索引和新版本五条路径均有真实PostgreSQL测试；
4. 同一ready请求不增加Index Set或Chunk行，也不再次调用Embedding；
5. Chunk Artifact的数量、顺序、定位、表格JSON、向量和cache key一一对应；
6. 慢操作全部位于事务外，最终保存/状态/active指针位于同一短事务；
7. 任一普通失败不留下可见半成品，旧active保持；
8. 实际模型/revision、完整Embedding身份、Chunk Set、Index Set、attempt和状态可审计；
9. owner/company_owner允许，ACL读者和跨tenant/document/version写入拒绝；
10. 软删除资源不能新建或复用索引，历史行不被误当active；
11. API只提供创建文档/版本和同步索引，不存在M2-16/17查询功能；
12. Fake全量、显式真实BGE Smoke、质量工具、迁移检查和正式Seed/Storage恢复全部通过；
13. 正式库最终保持0 Index Set/0 Chunk/0 Embedding，不提前留下检索数据。

### 27.15 本阶段能证明与不能证明

**能证明**

- 小型本地演示文档能从上传后的Version真实走完解析、切块、Embedding、逐行保存和原子激活；
- 重复请求和普通失败重试不会追加重复Chunk；
- 新版本和同版本新索引集在ready前不会替换旧active；
- 已覆盖的tenant/document/version/Chunk Set/Index Set错挂会被Service与PostgreSQL共同拒绝；
- Fake用于稳定日常回归，真实BGE用于显式离线Smoke，实际模型身份会随行审计；
- M2-15没有依赖RAGFlow，也没有提前实现检索或回答。

**不能证明**

- 关键词、Dense、混合、RRF、Reranker或RAG答案质量；
- HNSW在大数据量下的召回率、百万Chunk性能、高并发或多机吞吐；
- 进程强杀/断电后的自动租约回收、后台任务继续执行或分布式exactly-once；
- 软删除后的物理擦除、Storage垃圾回收或灾难恢复；
- 图文DOCX 0/2已经修复；
- M2-16及后续阶段已经完成。

### 27.16 主要风险与优先排查方向

| 风险或现象 | 优先排查方向 |
|---|---|
| 旧索引在重新索引期间消失 | 检查是否错误改写Version高层ready状态，候选进度必须只写Index Set |
| 重复请求增加Chunk | 检查Index Set确定性身份、ready复用分支、行UUID和唯一约束 |
| 向量与文本错位 | 检查Artifact连续顺序、Provider返回数量、strict zip和cache key复算 |
| 新版本过早active | 检查最终保存与两个active指针是否处于同一事务 |
| ready但行数不足 | 检查最终事务行数核对和Index Set ready CHECK，禁止分批提交 |
| 失败后旧active改变 | 检查失败事务是否误更新Version/Document指针 |
| 重新索引产生同一ID | 逐项比较Chunk Set、Embedding完整identity和FTS builder版本；设备/batch不应影响ID |
| BGE加载或OOM | 复用M2-14固定快照与batch降级；M2-15不得下载或更换revision |
| 同步API超时但服务端已完成 | 客户端用同一文档/版本URL重试；ready身份会直接复用，不增加Chunk |
| 跨边界FK失败 | 先核对tenant/document/version/Chunk Set/Index Set五元关系，不放宽约束 |
| 软删除后仍能索引 | 检查Document和关联File的deleted/status条件是否在领取与完成事务都复核 |
| 长期indexing | 判断是否进程强杀；V1没有租约回收，禁止直接启动第二worker覆盖 |
| 全量后Seed不干净 | 按验收脚本记录的精确ID/Key清理，再运行既有幂等Seed并逐项只读复核 |

### 27.17 需要更新的进度文档与最终停止点

- 本方案已写入`docs/progress/M2_KNOWLEDGE_RAG.md`，保存现状、取舍、实施步骤、验证、风险和停止点；
- `docs/PROJECT_PROGRESS.md`在方案提交时只同步M2-15待确认、Git/数据基线摘要、M2-14最近完成缺口和阶段链接，不重复整份方案；方案确认后的实施结果按单步日志继续同步；
- 本轮运行链位置只有“项目治理/方案文档”，没有进入前端、API、Schema、Service、Repository、Model或PostgreSQL写入；
- 本轮验证只能证明方案建立在实际代码/Git/数据库/Storage基线上，不能证明未来M2-15代码已经运行。

**本方案已于2026-08-31获得用户明确确认；原“确认前不编码”停止点已经解除，实施仍必须按M2-15.1至M2-15.6逐步验证和停下汇报。**

## 28. M2-15实施记录

### 2026-08-31｜M2-15.1｜Index Set合同、模型和迁移

**状态：已完成**

1. 本步解决的问题：现有`document_versions.index_status`无法同时表达“旧索引仍可用”和“新候选正在准备”，`document_chunks`原唯一边界也无法让同一Chunk Set安全保存不同Embedding身份。本步新增独立`document_index_sets`，让每套索引成品拥有自己的确定性ID、身份、状态、尝试次数、统计和错误审计；
2. 大白话运行过程：一个ready Chunk Set现在可以挂多套Index Set，例如旧BGE revision和新revision各一套。新候选准备期间Version仍可指向旧ready Index Set；只有指针非空时，数据库才要求Version为ready，并通过带状态的复合外键保证目标属于同一tenant/document/version且确实ready。Chunk行改为按Index Set而不是只按Chunk Set判重；
3. 方案确认与TDD：用户明确回复“已确认，开始实施”。先看到ORM元数据缺表测试失败，再补最小表；随后身份/外键/active/Chunk归属测试出现5个预期失败，再实现完整ORM；迁移测试先因head仍为0006失败，再新增0007；旧M2-13测试在0007因缺`document_index_set_id`失败后固定回0006执行；两个旧Service测试又证明最初的双向ready CHECK过强，最终按确认方案收缩为“指针非空时必须ready”；
4. 修改文件与职责：
   - `app/models/knowledge.py`新增`DocumentIndexSet`、Version的`active_index_set_id`、带status的active复合外键，以及Chunk的`document_index_set_id`/`embedding_cache_key`和新唯一边界；
   - `app/models/__init__.py`和`migrations/env.py`公开并登记新模型，保证业务导入和Alembic autogenerate看到同一元数据；
   - `migrations/versions/20260831_0007_document_index_sets.py`实现0006→0007升级及可回到0006的降级；
   - `tests/integration/test_document_index_set_migration.py`真实验证迁移往返、身份状态、active-ready、跨边界、同Chunk Set多Index Set、Chunk唯一性和级联；
   - `tests/unit/test_knowledge_models.py`冻结ORM列、复合外键、唯一约束和索引合同；
   - `tests/integration/test_document_chunk_migration.py`把M2-13行为测试固定在0006并在结束后恢复head，避免用M2-15语义篡改M2-13历史合同；
   - `tests/unit/test_m2_baseline.py`登记Index Set模型和0007迁移阶段守卫；
5. 完整调用链位置：本步只经过`Model → Alembic Migration → PostgreSQL/pgvector`。没有经过前端、API、Schema、Index Service、Storage、Parser、Chunk Service、Embedding Provider、Repository、查询、Reranker、Qwen或RAG；
6. 数据库硬约束：Index Set同时用Version和Chunk Set复合外键固定tenant/document/version归属；逻辑身份唯一约束阻止用不同ID重复登记同一索引身份；Version active指针把自己的`index_status`映射到Index Set `status`，因此不能指向pending/indexing/failed候选；Chunk新增Index Set五元复合外键，同一Chunk ID/序号只在同一Index Set内唯一；ready/failed字段形状由CHECK保证，子Chunk实际行数仍明确留给M2-15.3最终事务核对；
7. 兼容边界：CHECK只规定`active_index_set_id IS NOT NULL → index_status = ready`，暂时允许旧M2-05状态机产生`ready + null pointer`，避免在M2-15.3接管原子完成前破坏现有Service。M2-15新管线不得利用这个兼容口，Repository最终事务必须同时写ready和active指针；
8. 实际验证：聚焦ORM/迁移/旧M2-12/13回归为`70 passed`；兼容修复后的关键回归为`23 passed`；全量为`485 passed, 5 skipped in 38.77s`，5项仍是需要显式外部条件的2个Docling、2个BGE和1个Qwen Smoke；真实执行`0006 → 0007 → 0006 → 0007`通过，Alembic current/heads均为`20260831_0007 (head)`，`alembic check`显示无新操作；
9. 质量检查：全仓`ruff check app tests scripts`通过；本步涉及8个文件的Ruff格式检查通过；Mypy对100个源码文件通过；`compileall`、`pip check`和`git diff --check`通过。全未提交工作区的Ruff格式检查仍会报告26个既有M2-12/14文件存在格式/换行差异，本步为避免无关批量重写没有修改它们，因此不能声称全工作区format check通过；
10. 测试清理与正式数据恢复：编码前和最终全量pytest都会被`test_seed_m2_files`的既有`finally`清理为0行；已定位到这是测试隔离行为，不是索引迁移丢数据。每次均用模块方式按M1→M2普通→M2复杂幂等恢复。最终只读复核为10 files、10 documents、10 versions、9 ACL、10 parse pending、10 index pending、0 active version、0 active Index Set、0 Chunk Set、0 Index Set、0 Chunk、0非空Embedding、M1可售125；Storage为10 uploads、0 parsed JSON、0 chunks JSON；pgvector 0.8.6且容器健康；
11. 能证明：数据库已能并存同一Chunk Set的不同Embedding索引代次；跨tenant/document/version/Chunk Set错挂、active指向非ready、同一Index Set重复Chunk、非法状态形状会被拒绝；Version删除会级联清理Index Set和Chunk；0007可往返且ORM无漂移；
12. 不能证明：尚未生成确定性Index Set ID、没有把Artifact映射成Chunk行、没有Repository领取/重试/原子完成、没有调用Fake或BGE、没有API，也没有实现关键词/Dense/混合检索、Reranker或RAG。进程崩溃恢复和跨表Chunk计数不由本步证明；
13. 风险与优先排查：迁移失败先确认0006表是否仍为0 Chunk，再查非空列前置条件；active FK失败先核对tenant/document/version/status五元关系，不放宽约束；旧Service若写ready失败先检查是否误把单向CHECK改回双向；降级若已有同Chunk Set多代Chunk，旧0006唯一约束可能无法重建，真实产生重索引数据后不得把降级当无损回滚；
14. 下一步：本步完成后停止。只有用户确认继续，才进入M2-15.2的确定性索引身份与Chunk行Mapper；不自动实现Repository、Service、API或M2-16。

### 2026-08-31｜M2-15.2｜确定性索引身份与Chunk行Mapper

**状态：已完成**

1. 本步解决的问题：M2-15.1虽然准备了Index Set和Chunk数据库结构，但还没有一种稳定方法判断“这次是不是同一套索引”，也没有在写数据库前证明第N个Chunk、第N个向量和第N个cache key确实属于同一位置。本步新增纯内存合同和Mapper；相同Chunk Set、完整Embedding身份、document用途和FTS规则会得到相同Index Set ID，任一会改变索引内容的身份事实变化都会产生不同ID；
2. 大白话运行过程：先用“怎么切块、用哪个模型和revision、怎样池化、是否归一化、精度和维度”等事实给整套索引制作身份证。Embedding返回后再逐项验货：Chunk数量、向量数量、cache key数量必须相同；cache key必须能用该Chunk的`retrieval_text`重新算出来；然后才用严格顺序把三者拉链式配对。任何一项不一致就整批拒绝，不生成可交给Repository的行事实；
3. 输入、输出和上下游：输入是M2-12已经自校验的`CanonicalChunkArtifact`、M2-14的硬件无关`EmbeddingIdentity`与`EmbeddingBatch`，以及上游已确认的`tenant_id`；输出是一个`DocumentIndexSetIdentity`和按Chunk顺序排列的`DocumentChunkWriteFacts`元组。输出只是后续Repository的写入事实，不执行SQL、不改变状态、不激活版本；
4. 身份设计：`embedding_identity_sha256`覆盖contract version、provider、model ID、revision、pooling、max length、normalize、precision和1024 dimensions；设备、实际batch大小、时间、路径不进入身份，因为它们不应改变逻辑向量。`index_set_id`使用UUIDv5，由Chunk Set ID、索引Schema版本、Embedding身份Hash、固定`document`用途和FTS builder版本共同派生；行ID再由Index Set ID和Chunk ID派生。因此重复计算ID不变，模型revision变化则ID变化；
5. 文本和审计映射：Embedding归属通过`retrieval_text`对应的cache key复算证明，而不是使用缺少标题/表头上下文的`body_text`；`fts_text`固定等于原始`retrieval_text`，PostgreSQL后续仍自行生成`search_vector`；`embedding_model`保存实际`model_id`，`embedding_version`保存实际`revision`，完整身份JSON和Hash保存在Index Set事实中；表格、来源Span、Bounding Box、重叠、警告和定位字段均来自严格`model_dump(mode="json")`，没有把表格压扁后丢失单元格事实；
6. 防错设计：Mapper会重新验证Artifact整体Hash、每个Chunk Hash和Index身份Hash/UUID，拒绝跨document/version/Chunk Set身份；只接受`EmbeddingPurpose.DOCUMENT`；校验向量必须是1024维、有限值和近似单位归一化；使用`zip(..., strict=True)`保持顺序，并对每行重新计算cache key。需要诚实说明：若某个恶意Provider同时伪造“看似正确的cache key”和错误向量内容，Mapper无法从向量数值反推出原文；因此Provider的“向量和key同序”仍是M2-14边界合同，日常Fake和真实BGE Smoke分别验证该边界；
7. 修改文件与职责：
   - `app/services/documents/indexing/contracts.py`定义Index/FTS版本常量、完整Embedding身份事实、自校验Index Set身份、确定性ID和逐Chunk写入事实；
   - `app/services/documents/indexing/mapping.py`重新校验输入、生成Index Set身份、严格核对EmbeddingBatch并映射文本/表格Chunk行；
   - `app/services/documents/indexing/__init__.py`只公开本步稳定合同和纯函数；
   - `tests/unit/test_document_index_mapping.py`覆盖身份稳定与变化、Hash/ID篡改、文本/表格JSONB、raw FTS、模型/revision、确定性行ID、数量/顺序/用途/身份/向量/跨边界和Artifact篡改拒绝；
8. TDD过程：生产模块不存在时，新增测试先按预期在导入`app.services.documents.indexing`处失败；随后补最小实现，6项测试转绿。第一次质量检查只发现新测试导入顺序、未补返回类型和格式问题，行为回归仍为`120 passed`；扩大到111文件的Mypy又发现测试把通用JSON对象直接多层下标，补显式类型收窄后通过，没有为了通过检查改变生产逻辑；
9. 完整调用链位置：本步位于`Canonical Chunk Artifact + Embedding Identity/Batch → Indexing合同/Mapper → Repository待写事实`，属于Service内部的确定性转换边界。没有经过前端、HTTP API、请求/响应Schema、Index Repository、SQLAlchemy Model写入、PostgreSQL事务、Storage发布、Parser执行、Embedding Provider调用、关键词/Dense/混合检索、Reranker、Qwen或RAG；
10. 实际验证：新测试`6 passed`；连同Chunk、表格、Embedding、ORM和阶段守卫的聚焦回归为`120 passed`；全量为`491 passed, 5 skipped in 38.28s`，新增数量正好是6项。全仓`ruff check app tests scripts`、本步4文件格式检查、111文件Mypy、`compileall`、`pip check`和`git diff --check`通过；Alembic current/heads仍为`20260831_0007 (head)`且`alembic check`无新操作；范围扫描确认本步没有SQL、搜索、重排或下载调用。全未提交工作区format check仍保留M2-15.1已记录的26个既有M2-12/14格式/换行差异，本步没有批量改写；
11. 测试清理与正式数据恢复：全量pytest后按既有入口依次运行M1、M2普通和M2复杂Seed。最终只读事务复核为10 files、10 documents、10 versions、9 ACL、10 parse pending、10 index pending、0 active version、0 active Index Set、0 Chunk Set、0 Index Set、0 Chunk、0非空Embedding；`LR-TL-MUSH-OR01`在`DE-FRA`可售125；pgvector 0.8.6且PostgreSQL容器healthy。Storage为10 uploads、0 parsed JSON、0 chunks JSON；
12. 能证明：同一逻辑索引身份和同一Chunk会稳定产生相同Index Set/行UUID；Embedding完整身份字段不会只剩模糊模型名；`retrieval_text`、raw FTS、表格/定位JSON、向量、模型revision和cache key在纯内存写入事实中按顺序一一对应；常见数量、用途、身份、Hash、边界和向量篡改会在数据库前被拒绝；没有提前实现M2-16/17检索；
13. 不能证明：尚未真正插入任何`document_index_sets`或`document_chunks`，不能证明并发领取、失败重试、事务回滚、重复请求不增行、旧active保持或最终原子切换；本步没有调用Fake/BGE生成新正式索引，也不能证明API权限、搜索效果、Reranker或RAG答案。正式35个Chunk小于Provider单次128文本上限；若未来单文档超过128 Chunk，M2-15.4必须在事务外分批Embedding并按原顺序汇总后再映射，本步没有提前实现该编排；
14. 风险与优先排查：Index Set ID意外变化时先逐项比较Chunk Set、完整Embedding身份和FTS版本，不把设备/batch加入身份；数量错误先看Service是否漏批或重复合并；顺序错误先查Provider输入列表、批次拼接和cache key复算；表格字段丢失先查是否绕过`model_dump(mode="json")`；跨边界错误不能通过放宽Mapper或数据库复合约束解决；
15. 下一步与停止点：M2-15.2完成后立即停止。只有用户明确确认继续，才进入M2-15.3的Index Repository领取、失败记录、批量保存和原子完成事务；不自动实现Index Service、API、检索或M2-16。

### 2026-08-31｜M2-15.3｜Index Repository领取、失败与原子完成

**状态：已完成**

1. 本步解决的问题：M2-15.2只能生成稳定身份和待写行，尚不能防止两个执行者同时处理同一索引，也不能保证Chunk、ready状态和active指针一起提交。本步新增专用`DocumentIndexRepository`，把任务领取、失败记录、重试编号、批量写行、行数核对和两个active指针切换固定在真实PostgreSQL事务中；
2. 大白话运行过程：领取像仓库发号码牌。同一个Index Set第一个执行者拿到`attempt_count=1`并把候选标为indexing；第二个执行者拿不到。失败后候选标failed，再领取得到号码牌2。完成时必须出示当前号码牌，拿着旧号码牌1的过期进程不能提交第2次尝试的数据；如果同一身份已经ready，Repository直接把成品交给上游复用，不增加尝试或Chunk；
3. 输入、输出和上下游：输入是tenant、M2-15.2的`DocumentIndexSetIdentity`、最终`DocumentChunkWriteFacts`、尝试编号和带时区时间；领取输出为indexing、ready复用行或`None`，失败输出failed行或`None`，完成输出ready行或`None`。Repository不解析文件、不切块、不调用Embedding；这些慢操作应由M2-15.4在领取事务提交后执行；
4. 领取短事务：先对同一Document/Version/File/ready Chunk Set加行锁并重新核对tenant、document、version、parse ready、Chunk Set ready、Document未删除和File未软删除；拒绝比当前active更旧的Version及同Version另一套正在indexing的候选；随后用PostgreSQL`INSERT ... ON CONFLICT DO NOTHING`登记确定性身份，并只把pending/failed变为indexing、`attempt_count + 1`、清空旧错误和结果。首次索引没有active时Version进入indexing；重新索引已有旧active时Version继续ready，只改变候选Index Set；
5. 失败短事务：只允许相同tenant/身份/status=indexing/attempt编号的执行者登记失败；防御性删除该候选可能存在的Chunk，清空统计并保存不超过1000字符的安全错误。首次索引失败时Version/File标failed；重新索引失败时旧active指针不变，Version/File恢复ready。旧尝试编号不能关闭或完成新尝试；
6. 完成短事务：再次锁定并复核全部资源仍然可用，验证当前attempt、M2-15.2行合同、tenant/document/version/Chunk Set/Index Set、实际模型/revision，以及行数、文本/表格数和Token总数必须等于ready Chunk Set审计统计；先在同一事务批量插入全部Chunk并查询实际行数，再把Index Set标ready，最后把Version设ready并指向新Index Set、把Document指向该Version、把File设ready。任何一步抛错由调用者回滚整笔事务，数据库外看不到中间状态；
7. 原子激活含义：同Version重建Embedding时，领取新候选不会修改旧active；只有新候选全部Chunk成功后，Version指针才从旧Index Set切到新Index Set，旧成品仍保留ready。同Document的新Version索引时，Document继续指向旧Version；新Version成功后才一次切换。Repository还比较Version序号，防止晚回来的旧Version覆盖已经active的更新Version；
8. 修改文件与职责：
   - `app/repositories/document_indexes.py`新增`claim_index_set`、`fail_index_set`、`complete_index_set`和tenant/软删除/状态/attempt/统计/行锁辅助校验；
   - `app/repositories/__init__.py`公开`DocumentIndexRepository`，让后续Service只依赖稳定Repository入口；
   - `tests/integration/test_document_index_repository.py`使用真实PostgreSQL覆盖单领取、失败重试、过期执行者、首次原子完成、ready复用、唯一约束失败回滚、同Version重建、新Version切换、Document/File软删除及跨tenant/document拒绝；
9. TDD与调试过程：测试先因`app.repositories.document_indexes`不存在按预期失败；补最小Repository后，首次运行的8项错误全部发生在测试夹具建图阶段，真实FK显示File和Version同次flush时Version先插入。对照现有迁移夹具后将File先flush，再插Version，8项转绿；随后只处理`__all__`排序、Ruff排版及SQL条件/行锁目标的Mypy类型收窄，没有放宽数据库约束或改变事务语义；
10. 真实故障证明：测试给新候选的第二行制造重复`chunk_index`，PostgreSQL唯一约束在完成事务中抛`IntegrityError`；调用者rollback后，新候选仍是先前已提交的indexing领取状态、该候选0 Chunk、Version仍指向旧ready Index Set、旧Index Set的2个Chunk完整保留。这证明不是“先写一行再留下半成品”，而是整批写入与激活一起回滚；
11. 完整调用链位置：本步经过`Repository → DocumentIndexSet/DocumentChunk/DocumentVersion/Document/StoredFile Model → PostgreSQL/pgvector`。上游测试使用M2-15.2 Mapper预先准备事实，但Repository本身不调用Parser、Chunker或Embedding。没有经过前端、HTTP API、请求/响应Schema、Index Service、Storage读写、关键词/Dense/混合检索、Reranker、Qwen或RAG；
12. 实际验证：Repository单测集为`8 passed`，扩大到Index迁移、Mapper、模型和Chunk Service的聚焦回归为`42 passed`；全量为`499 passed, 5 skipped in 40.46s`，比M2-15.2正好多8项。全仓`ruff check app tests scripts`、本步3文件格式检查、113文件Mypy、`compileall`、`pip check`和`git diff --check`通过；Alembic current/heads仍为`20260831_0007 (head)`且`alembic check`无新操作，因此本步不需要迁移；范围扫描确认没有检索、重排或模型下载功能。全未提交工作区format check仍保留已记录的26个既有M2-12/14格式/换行差异，本步未批量改写；
13. 测试清理与正式数据恢复：全量pytest后按既有入口依次恢复M1、M2普通和M2复杂Seed。最终只读事务显示`transaction_read_only=on`，10 files、10 documents、10 versions、9 ACL、10 parse pending、10 index pending、0 active Version、0 active Index Set、0 Chunk Set、0 Index Set、0 Chunk、0非空Embedding；`LR-TL-MUSH-OR01`在`DE-FRA`可售125；pgvector 0.8.6且PostgreSQL容器healthy。Storage为10 uploads、0 parsed JSON、0 chunks JSON；
14. 能证明：同一确定性身份不能被两个正常事务同时领取；失败可用同ID增加attempt重试，旧attempt不能提交；ready请求不增Index Set、attempt或Chunk；完整批次与Index Set/Version/Document/File状态在同一事务完成；同Version和新Version在候选ready前都保留旧active；常见Document/File软删除、跨tenant/document和错误Chunk归属会被Repository或数据库拒绝；
15. 不能证明：尚未有Index Service真正串起validate→parse→chunk→embed→save→ready，不能证明Embedding失败会自动调用`fail_index_set`、重复ready请求会在Service层跳过Provider或API权限映射；没有后台队列、租约超时、进程强杀自动回收或分布式exactly-once。测试证明的是正常数据库事务并发与回滚，不代表任意绕过Repository的手工SQL都安全；也没有实现任何检索或RAG答案；
16. 风险与优先排查：长期indexing先检查进程是否在领取提交后崩溃，V1还没有租约自动回收；重试被拒绝先核对attempt和是否存在另一候选indexing；完成返回None先查Document/File软删除、parse/Chunk Set状态、Version新旧顺序和行统计；IntegrityError先查Index Set五元归属及同批Chunk ID/序号，不放宽约束；旧active意外变化先确认上游没有在慢操作期间直接修改Version；
17. 下一步与停止点：M2-15.3完成后立即停止。只有用户明确确认继续，才进入M2-15.4的DocumentIndexService编排，复用M2-11/12/14串起慢操作与本步短事务；不自动实现API、检索或M2-16。

### 2026-08-31｜M2-15.4｜DocumentIndexService整链编排

**状态：已完成**

1. 本步解决的问题：M2-15.3已经有安全的数据库“仓库管理员”，但没有总调度按顺序串起Parser、Chunk Service、Embedding和Repository。本步新增同步`DocumentIndexService`，真正跑通`validate/authorize → ensure parse → ensure chunk → claim → embed → map → save → ready`；
2. 大白话运行过程：总调度先确认用户能管理目标文档。解析或切块已经有经过Hash和统计验真的成品就直接复用；没有才调用原服务。随后先用Embedding身份和Chunk Set推导固定Index Set ID，在短事务领取attempt；如果同一成品已ready就立即返回，不再跑模型。新任务在事务外分批生成向量，最后把全部Chunk、ready状态和Version/Document指针一次性提交；
3. 慢操作与事务：Storage读取、Parser/Chunker、JSON/Pydantic验真和Embedding都在数据库事务外。数据库只在领取、失败登记和最终批量保存/激活时开启短事务，避免模型运行期间长期持有行锁；
4. 解析/切块复用：`DocumentIndexService._ensure_parsed`只对`pending/failed`调用既有Parser，ready直接继续，parsing仍返回状态冲突；`DocumentChunkService.ensure_chunk_version`按真实Parsed Artifact和当前配置推导确定性Chunk Set ID，ready时重新核对Artifact身份、配置、Hash、统计和Storage JSON，非ready才进入原`chunk_version`。原`chunk_version`重复ready仍冲突，M2-12合同没有改变；
5. Embedding与顺序：固定使用每个Chunk的`retrieval_text`和`purpose=document`。超过M2-14单次128文本上限时按原顺序分批，测试用129段证明实际调用为`128+1`；每批必须保持相同identity/purpose/数量，汇总后仍由M2-15.2 Mapper逐项复算cache key并严格配对；
6. 幂等与损坏拒绝：同一ready Index Set复用前，Repository重新统计实际Chunk总数、文本数、表格数和Token总数并与审计字段比较；完整才返回`reused=true`，缺一行就拒绝，且不会再次调用Provider。重复正常请求保持相同Chunk Set/Index Set、两者attempt均不增加、Chunk不增行；
7. 失败恢复：解析/切块失败发生在Index Set身份可确定之前，只更新目标Version/File的高层索引状态，不伪造Index Set；Embedding、Mapper或最终数据库保存失败发生在领取之后，用独立短事务调用`fail_index_set`，候选变failed且保持0 Chunk。再次请求使用同一ID、attempt从1增到2；有旧active时失败只关闭候选，不切旧指针；
8. 原子激活：整链测试证明首次索引只在ready后同时设置Version active Index Set和Document active Version；同Version更换Embedding revision会创建新Index Set并保留旧ready成品，完成后只切Version指针；新Version索引前Document仍指向旧Version，完成后才一次切到新Version，旧Version自己的ready Index Set仍保留；
9. 修改文件与职责：`app/services/documents/indexing/service.py`新增结果合同、总调度、分批Embedding和失败补偿；`app/services/documents/chunking/service.py`新增验真复用入口并抽取确定性Chunk计划；`app/repositories/documents.py`新增完整边界的Chunk Set读取；`app/repositories/document_indexes.py`新增领取ready时的实际统计复核及解析/切块前置失败登记；`app/core/errors.py`新增脱敏可重试`DocumentIndexingError`；`tests/integration/test_document_index_service.py`新增10项真实PostgreSQL/Local Storage整链测试；`tests/unit/test_document_index_service.py`新增129段分批顺序测试；
10. 实际调用链：`DocumentIndexService → DocumentParserService / DocumentChunkService / Storage / EmbeddingProvider → Mapper → DocumentIndexRepository → Model → PostgreSQL/pgvector`。本步没有经过前端、HTTP API、请求/响应Schema、关键词/Dense/混合检索、RRF、Reranker、Qwen、引用、聊天或Agent；服务暂时从具体模块导入，HTTP依赖工厂和公开API组装留给M2-15.5，避免本步制造包级循环依赖；
11. TDD与调试证据：最初测试因`DocumentIndexService`不存在在导入处失败；最小实现转绿。重复请求测试先因ready Parser冲突失败，再补ensure逻辑。新增Chunk Artifact读取第一次因漏导入运行时模型失败，沿堆栈确认`NameError`后只补导入。缺Chunk测试先错误复用，再补实际统计复核。新版本测试第一次因空白页触发未启用Docling而解析失败，改用哈希不同但仍走Native的安全PDF测试数据，没有放宽生产路由；
12. 验证结果：本步新增11项测试，Index Service单元/集成为`11 passed`；连同Parser/Chunk/Embedding/Mapper/Repository的聚焦回归为`65 passed`；全量为`510 passed, 5 skipped in 45.68s`。全仓`ruff check app tests scripts`、本步7文件格式检查、102文件Mypy、`compileall`、`pip check`和`git diff --check`通过；Alembic current/heads均为`20260831_0007 (head)`且`alembic check`无新操作，因此本步不新增迁移；
13. 正式数据恢复：全量测试后依次运行M1、M2普通和M2复杂Seed。最终只读事务为`transaction_read_only=on`，10 files、10 documents、10 versions、9 ACL、10 parse pending、10 index pending、0 active Version、0 active Index Set、0 Chunk Set、0 Index Set、0 Chunk、0非空Embedding；M1关键可售125、pgvector 0.8.6、PostgreSQL容器healthy；Storage为10 uploads、0 parsed JSON、0 chunks JSON；
14. 能证明：同步进程正常运行时，首次、重复、失败重试、同Version重新Embedding和新Version都遵守确定性身份、完整批次、失败补偿和原子指针切换；重复ready不会再次调用Provider；129段分批不会改变顺序；跨租户请求在任何解析/切块/索引写入前被隐藏；
15. 不能证明：V1仍没有后台队列、任务租约超时、进程在领取后被强杀的自动回收或分布式exactly-once；没有用真实BGE跑本步正式Seed，日常整链测试使用Fake；没有API权限状态码映射，也没有实现任何关键词、Dense、混合检索、Reranker或RAG答案；
16. 风险与排查：长期indexing先查进程是否在领取提交后崩溃；重复请求冲突先查ready实际行数/统计或另一个indexing候选；解析/切块复用失败先查Storage对象、Artifact Hash、确定性配置和数据库审计是否一致；Embedding顺序错误先查每批输入边界、identity/purpose和cache key；最终失败先查attempt是否过期、Document/File软删除、Version新旧顺序和数据库约束，不放宽tenant复合边界；
17. 下一步与停止点：M2-15.4完成后立即停止。只有用户明确确认继续，才进入M2-15.5最小Documents API与Schema/依赖组装；不自动实现检索、M2-16或任何后续功能。

### 2026-08-31｜M2-15.5｜最小Documents API与同步索引入口

**状态：已完成**

1. 本步解决的问题：M2-15.4已经能在Python内部完整索引一个文档版本，但外部客户端还没有受认证、可校验且不泄露内部字段的HTTP入口。本步只新增创建逻辑文档、追加不可变版本和显式同步索引三条Documents API，把既有Document Service与DocumentIndexService组装进FastAPI；
2. 大白话运行过程：用户先通过既有Files API上传文件，再用文件ID创建文档；要更新内容时，上传另一个文件并追加V2；最后明确点击目标版本的索引URL。这个请求会等待parse→chunk→embed→save→ready完成后返回。重复点击同一ready版本会拿到同一个Index Set并返回`reused=true`，不会重复增加Chunk；V2全部完成前Document继续指向V1，完成事务提交后才一次切换到V2；
3. 输入、输出与Schema：`POST /api/v1/documents`接收`file_id/title/document_type/language/market/product_id/access_level`并返回201的安全文档详情；`POST /api/v1/documents/{document_id}/versions`接收新`file_id`并返回201版本状态；`POST /api/v1/documents/{document_id}/versions/{version_id}/index`无请求体，返回200的`DocumentIndexResponse`，包含Index/Document/Version/Chunk Set ID、ready/reused/activated、实际Embedding模型与revision、Chunk统计和完成时间，不返回tenant、Storage Key、磁盘路径、向量或原始Embedding；未知请求字段由严格Schema拒绝；
4. 权限和状态码：三条路由都要求Bearer登录；创建和追加沿用DocumentService边界，索引沿用DocumentIndexService的owner或同租户`company_owner`管理边界。只有ACL读权限的用户以及跨tenant/document/version请求统一隐藏为404，避免泄露对象存在；状态占用/冲突为409，UUID或请求体错误为422，索引内部失败为固定且可重试的安全500；本步不新增ACL管理端点；
5. 依赖组装：`get_document_service`在现有请求事务中复用FileService与DocumentRepository；`get_embedding_provider`按应用实例延迟创建并复用配置的Provider，测试配置使用确定性Fake，真实环境配置才会创建本地BGE Provider且仍强制离线；`get_document_index_service`使用应用持有的session factory、Storage、Settings和Provider组装同步索引Service。应用启动只把Provider槽位设为`None`，不会加载或下载模型；
6. 修改文件与职责：
   - `app/api/routers/documents.py`：新增三条受认证Documents路由、公开响应模型和统一错误响应声明；
   - `app/api/dependencies.py`：新增Document Service、Embedding Provider和DocumentIndexService依赖工厂；
   - `app/api/routers/__init__.py`与`app/main.py`：公开并注册Documents router，并初始化应用级Provider槽位；
   - `app/schemas/knowledge.py`与`app/schemas/__init__.py`：新增并公开不泄露内部数据的`DocumentIndexResponse`；
   - `tests/integration/test_document_index_api.py`：使用真实FastAPI、PostgreSQL和临时LocalStorage覆盖OpenAPI、认证、创建、版本、首次/重复索引、V1→V2原子切换、权限/边界、409/422/500和失败后HTTP重试；
7. 完整调用链位置：`客户端 → API → Pydantic Schema → DocumentService或DocumentIndexService → Storage / Parser / Chunk Service / EmbeddingProvider → Repository → Model → PostgreSQL/pgvector`。创建和追加不执行索引；索引端点不经过前端页面、关键词/Dense/混合查询、RRF、Reranker、Qwen、Evidence、聊天或Agent；
8. TDD与排错证据：第一项测试先因OpenAPI没有三条路由而按预期失败，补最薄Schema/依赖/路由后转绿。真实整链测试首次只因断言误猜Fake模型名为`fake-bge-m3`而失败，检查Provider固定身份后把测试修正为实际的`fake/m2-deterministic@m2-fake-v1`，没有篡改生产审计身份；随后所有API行为测试通过；
9. 幂等、失败重试与原子切换验证：首次索引返回`reused=false/activated=true`；重复URL返回相同Index Set、`reused=true`且数据库Chunk计数不变。新V2创建后只读查询确认Document仍指向V1；由同租户company_owner索引完成V2后才指向V2。测试替换为故障Fake时返回安全500；移除故障后使用同一URL重试成功，Version的ready状态和active Index Set一致；
10. 权限、安全与未提前检索验证：ACL role=`product_scout`即使能读也无法索引并得到安全404；错误Document/Version组合为404；非法UUID和伪造`tenant_id`字段为422；`parsing`占用为409。公开结果不含tenant/Storage/path/vector。OpenAPI中的Documents路径精确只有三条，且全应用路径不含search/dense/lexical/hybrid/rerank/rag，因此没有提前实现M2-16/17查询功能；
11. 实际验证结果：新增API集成测试`5 passed`；相关Document/Embedding/Mapper/Repository/Service回归`74 passed`；全量为`515 passed, 5 skipped in 45.92s`，新增数量正好是5项。全仓`ruff check app tests scripts`通过，Mypy对101个app源码文件通过，`compileall`和`pip check`通过；Alembic current/heads均为`20260831_0007 (head)`，`alembic check`无待生成操作，因此本步不需要新迁移；
12. 正式Seed与Storage恢复：全量测试后依次运行既有M1、M2普通和M2复杂幂等Seed。最终只读事务显示`transaction_read_only=on`，10 files、10 documents、10 versions、9 ACL、10 parse pending、10 index pending、0 active Version、0 active Index Set、0 Chunk Set、0 Index Set、0 Chunk、0非空Embedding；M1关键可售125，pgvector 0.8.6，PostgreSQL容器running/healthy；Storage精确为10 uploads、0 parsed JSON、0 chunks JSON、0临时文件；
13. 能证明：受认证HTTP客户端现在能创建文档、增加新版本并显式同步索引；owner/company_owner管理权限、ACL读者拒绝、边界隐藏和安全错误能贯穿真实API；同一URL可以幂等复用及在普通Embedding失败后重试；新版本在完整ready前不会替换旧active；API返回实际Provider模型和revision审计且没有内部路径；
14. 不能证明：本步没有运行真实BGE整链Smoke，日常API测试只使用Fake；没有证明HTTP连接中断后客户端一定收到成功响应，也没有后台队列、任务租约、崩溃自动回收或分布式exactly-once；没有实现GET文档列表/详情、ACL写接口、删除接口、关键词/Dense/混合检索、RRF、Reranker、RAG答案、引用、聊天或前端；图文DOCX 0/2仍未修复；
15. 风险与优先排查：404先核对当前用户tenant、owner/company_owner和document/version归属，不放宽为泄露型403；409先查目标是否仍在parsing/chunking/indexing；重复请求若Chunk增加先查Index Set身份与ready复用分支；500先查Version/Index Set安全状态和Provider/Storage/数据库日志，API响应不能加入内部异常；同步请求超时时客户端应使用同一URL重试，不能改成没有持久Worker保障的虚假202；
16. 下一步与停止点：M2-15.5完成后立即停止。只有用户明确确认继续，才进入M2-15.6正式10文档/Fake收口、显式本地BGE Smoke、故障矩阵和最终Seed恢复；不自动运行真实模型、不下载模型、不实现检索或M2-16。

### 2026-08-31｜M2-15.6｜真实Smoke、故障矩阵、Seed恢复与收口

**状态：已完成；M2-15至此完成。**

1. 本步解决的问题：M2-15.1至15.5已经分别证明模型、Mapper、Repository、Service和API，但还缺少一份可以重复执行的正式10文档整链验收，也缺少“真实BGE确实能经过索引Service写入PostgreSQL”的小型证据。本步只做收口验证，不再增加索引业务语义；
2. 大白话运行过程：验收脚本先确认正式库是干净Seed，再临时让10份合成文档走完`parse → chunk → embed → save → ready`。第一份文档的Fake Provider被故意设置为第一次失败，数据库记下failed后用同一个请求重试；全部成功后再把10份文档各索引一次，确认直接复用原结果。最后脚本只删除自己发布的Parsed/Chunk JSON和索引行，把正式Seed恢复到尚未解析、尚未索引的状态；
3. 输入、输出与上下游：输入是`m2-v1`和`m2-complex-v1`共10份版本化合成文档、现有LocalStorage、真实Parser/Chunk Service，以及Fake或固定本地BGE Provider；输出是版本化`m2-index-pipeline-report-v1`报告、10个ready审计结果或一个BGE Smoke结果，并在验证结束后恢复0索引数据。完整调用链为`验证脚本/Smoke → DocumentIndexService → Storage / Parser / Chunk Service / EmbeddingProvider → Mapper → Repository → Model → PostgreSQL/pgvector`；没有经过前端、检索查询、Reranker、Qwen、Evidence、聊天或Agent；
4. 修改文件与职责：
   - `scripts/verify_m2_index_pipeline.py`：正式Seed前置门禁、首次Embedding故障、10文档逐行审计、重复幂等、离线BGE单文档入口、精确清理、结构化报告和成功判定；
   - `tests/unit/test_m2_index_pipeline_verification.py`：冻结35 Chunk、27文本/8表格、重试attempt=2、重复不增行、清理基线和BGE身份等报告合同；
   - `tests/smoke/test_document_index_bge_smoke.py`：仅在`RUN_BGE_M3_INDEX_SMOKE=1`时加载现有固定快照，禁止下载并真实写入一份文档后清理；
   - `tests/unit/test_m2_baseline.py`：把阶段哨兵推进到M2-15，确认Index API/Service/验收文件存在且关键词、Dense、混合、Reranker和检索路由不存在；
   - `ruff.toml`：只让格式化器跳过两个哈希冻结的Seed生成器，lint仍继续检查；另有此前26个M2文件经过机械Ruff格式化，其中两个冻结文件在哈希测试报警后恢复原排版，最终24个历史文件完成纯排版收口；
   - `docs/progress/M2_KNOWLEDGE_RAG.md`与`docs/PROJECT_PROGRESS.md`：记录本步证据、阶段完成状态、遗留边界与停止点；
5. TDD证据：先新增验收合同测试，初次运行明确因`ModuleNotFoundError: scripts.verify_m2_index_pipeline`得到3个RED失败；补最小报告常量和判定函数后转为`3 passed`，再逐步扩展真实脚本。默认BGE Smoke为`1 skipped`，证明日常测试不会误加载大模型；显式开关运行后为`1 passed in 14.99s`；
6. Fake正式整链结果：报告`decision.m2_15_complete=true`。10/10文档ready，得到35 Chunk，其中27文本、8表格；35行Embedding、35行生成FTS均非空，10/10数据库行与Canonical Chunk Artifact逐项匹配。首次故障被记录，重试成功且`attempt_count=2`；第一次完整执行前后Provider调用共11次（1次故障+10次成功），重复索引后仍为11次，10/10返回reused，Index Set保持10、Chunk保持35；
7. 幂等、故障恢复和清理：重复请求同时验证“相同Index Set ID、Provider不再调用、Chunk不增长”。正式脚本清理20个本次发布的Parsed/Chunk对象，剩余发布Key为空；清理后10 files、10 documents、10 versions、9 ACL，Chunk Set/Index Set/Chunk/Embedding全为0。既有Service/Repository/API回归继续覆盖解析、切块、Embedding和数据库保存失败、过期attempt、旧active保留、同Version重建、新Version原子切换、软删除与跨tenant/document/version拒绝；
8. 真实BGE证据：Smoke只使用本地`BAAI/bge-m3@5617a9f61b028005a4858fdac845db406aefb181`快照，`allow_download=False`且设置Hugging Face/Transformers离线变量；真实1024维document向量经过同一DocumentIndexService写入一份`mushroom_lamp_manual`文档，数据库模型/revision与Provider一致，重复请求复用同一Index Set，结束后恢复基线。这个Smoke证明真实模型能接入索引写入，不代表10文档语义检索质量；
9. 格式故障与修复证据：全仓格式化首次机械改写26个历史M2文件，第二轮全量测试的冻结哈希哨兵立即发现`m2_seed_content.py`变化并失败为`1 failed, 517 passed, 6 skipped`。排查确认两个冻结生成器格式化前哈希与HEAD及固定常量完全相同；没有更新哈希掩盖问题，而是恢复原排版并用`ruff.toml [format].exclude`保护它们。两个哈希重新精确匹配，原失败测试通过，最终全量恢复全绿；
10. 最终质量门：全量`518 passed, 6 skipped in 45.75s`；`ruff check app tests scripts migrations`通过，排除两个冻结生成器后194个文件`ruff format --check`通过；Mypy对app及本步验收/Smoke共104个源码文件通过；`compileall`、`pip check`和`git diff --check`通过。Alembic current/heads均为`20260831_0007 (head)`，`alembic check`无新操作，因此本步不新增迁移；PostgreSQL/pgvector 0.8.6容器healthy；
11. 正式Seed最终复核：全量测试后依次运行M1、M2普通、M2复杂幂等Seed。只读核对为10 files、10 documents、10 versions、9 ACL、10 file uploaded、10 parse pending、10 index pending、0 active Version、0 active Index Set、0 Chunk Set、0 Index Set、0 Chunk、0非空Embedding；Storage精确10 uploads、0 parsed JSON、0 chunks JSON、0其他对象；指定`LR-TL-MUSH-OR01 / DE-FRA`快照为150 on-hand、20 reserved、5 unsellable，即125可售；
12. 能证明：现有文件、解析、切块、Fake/真实BGE、Mapper、Repository和PostgreSQL已经能组成可重复索引闭环；同一ready版本不会重复生成向量或Chunk；普通Embedding失败可用同一身份重试；新候选只有完整ready后才原子激活；每行文本、向量、cache key、模型/revision和tenant/document/version/Chunk Set/Index Set边界都有测试与数据库约束；验证结束能够精确恢复正式数据；
13. 不能证明：V1仍没有持久队列、租约、心跳或后台巡检，进程被强杀后不会自动回收长期`parsing/chunking/indexing`，需要人工核对恢复；不能承诺分布式exactly-once或客户端断线一定收到成功响应。真实BGE只做一份小文档索引Smoke，没有执行关键词、Dense、混合、RRF、Reranker、RAG答案、引用或端到端问答，因此不能证明任何检索相关率、排序质量或回答质量；图文DOCX 0/2仍是已知短板；
14. 风险与优先排查：正式脚本前置失败先查`DOCLING_BACKEND=docling`和本地Docling manifest，不要联网下载；BGE Smoke失败先查固定snapshot/revision、离线变量、内存与M2-14 batch降级；重复请求若Chunk或Provider调用增长，先查Index Set身份、ready行统计和Artifact Hash；清理不一致先查报告中的publication keys和三个active指针，不能扩大删除范围；长期indexing先查进程崩溃与attempt，再按V1人工恢复流程处理；
15. 阶段完成标准结论：M2-15.1至15.6全部完成并实际验证；幂等索引、普通失败重试、完整成品原子激活、模型/revision/Chunk Set审计、租户/文档/版本隔离、最小API、Fake全量与真实BGE小型Smoke均有证据；没有提前实现M2-16/17；
16. 下一步与停止点：M2-15至此完成。当前授权不包含M2-16；必须先提交M2-16实施方案并取得用户明确确认，才能开始任何关键词、Dense或混合检索开发。本步完成后立即停止。

### 2026-08-31｜Git同步后本机环境恢复与全量复验

**状态：已完成；不改变M2-15已完成和M2-16待确认边界。**

1. 目标与现状：从`origin/main`快进到`5c20cf2`后，本机虚拟环境缺少`pgvector/jieba/FlagEmbedding`，Docker Desktop未启动，数据库仍在`20260829_0004`，固定BGE-M3快照不存在，因此不能直接验证最新索引代码；本步只恢复本机运行与验证基线，不开发检索功能；
2. 大白话运行过程：先把依赖补全，再启动项目数据库并补齐三次迁移；随后用项目自带脚本下载固定版本的BGE-M3，强制离线加载并生成真实向量；最后从后端到真实浏览器完整跑一遍测试。全量首次失败后没有跳过数据库约束，而是确认测试把固定`started_at`与数据库当前`created_at`混用，只补回它已经定义但漏写的固定创建时间；
3. 修改文件与职责：`tests/integration/test_document_chunk_set_migration.py`在测试插入值中显式加入既有`created_at`，消除UTC 10:01之后运行必失败的时间依赖，继续验证`started_at >= created_at`约束；`docs/progress/M2_KNOWLEDGE_RAG.md`与`docs/PROJECT_PROGRESS.md`记录本机恢复、修复和验证证据。BGE快照位于Git忽略的`data/model-cache`，匿名报告位于Git忽略的`output/m2_embedding_benchmarks/local.json`；
4. 完整调用链位置：环境门禁覆盖`前端 → API → Pydantic Schema → Service/LangGraph/Harness或DocumentIndexService → EmbeddingProvider/Repository → Model → PostgreSQL/pgvector`。测试夹具修复只作用于Model/PostgreSQL迁移约束测试，不修改生产调用链、迁移或业务数据合同；
5. 基础设施与迁移验证：Docker Desktop恢复后`deep-search-postgres`为healthy，`pg_isready`接受连接，数据库`vector`扩展为0.8.6；Alembic实际从`20260829_0004`依次升级`0005/0006/0007`，最终`current=20260831_0007 (head)`且`alembic check`为`No new upgrade operations detected`；
6. BGE验证：显式下载并校验固定`BAAI/bge-m3@5617a9f61b028005a4858fdac845db406aefb181`快照，重组后约2.30 GB。真实基准中文相关/无关相似度为`0.840595 > 0.348997`，跨语言为`0.731607 > 0.308162`；强制离线Embedding Smoke为`2 passed in 50.71s`，真实`DocumentIndexService → PostgreSQL/pgvector`单文档索引、幂等复用与清理Smoke为`1 passed in 32.06s`；
7. 后端验证：首次全量为`1 failed, 515 passed, 8 skipped`，失败精确落在Chunk Set迁移测试的固定时间夹具；最小修复后该文件`2 passed`、Ruff通过，最终全量为`516 passed, 8 skipped in 110.52s`。8项跳过分别来自2项默认关闭的BGE Embedding、1项默认关闭的BGE索引、1项付费Qwen、2项显式Docling和2项当前Windows符号链接权限；BGE三项已在本步显式单独通过；
8. 前端与端到端验证：Vitest组件`4 passed`，TypeScript `tsc --noEmit`、ESLint和Next.js 16.3.3生产构建通过；清理组合脚本遗留的精确Uvicorn进程后，Chromium `4 passed`，覆盖德国库存/Evidence成功、法国账号跨市场403、无效Token 401，以及PostgreSQL中断时安全500与自动恢复；
9. 能证明与不能证明：能证明当前电脑的依赖、PostgreSQL/pgvector、最新迁移、固定BGE本地权重、真实向量生成、真实单文档索引、默认后端回归、前端构建和M1浏览器闭环可运行；不能证明付费Qwen真实调用、当前Windows符号链接能力、M2复杂Docling显式Smoke、GPU性能、10文档真实BGE语义质量或任何尚未实现的关键词/Dense/混合/RRF/Reranker/RAG质量；
10. 风险与排查：迁移导入失败先查虚拟环境`pgvector`；数据库不可用先查Docker Desktop、容器health和5433；BGE失败先查固定manifest/revision、约2.30 GB快照、离线变量和内存；Chunk Set时间约束失败先比较测试显式`created_at/started_at`，不得放宽生产约束；Playwright启动失败先查8000/3000占用并只终止命令行明确属于本项目的遗留进程；
11. 下一步与停止点：本机已经具备继续讨论下一阶段的运行基线，但当前授权仍不包含M2-16代码。M2-16必须先提交实施方案并由用户明确确认，不能因环境恢复而自动开始。

### 2026-08-31｜M2-16-PLAN｜权限前置的混合检索闭环

**状态：进行中；M2-16.1已完成，等待用户确认M2-16.2。2026-08-31范围修订把原路线图中分散在M2-16至M2-18的Dense、Lexical和RRF合并为当前M2-16内部小步骤；第7节已同步为同一套有效编号。用户对M2-16的确认不授权新M2-17 Reranker、RAG或任何后续阶段。**

#### 1. 当前现状和真正缺少的能力

M2-15已经能把文档解析、分块、生成Embedding并写入`document_chunks`。数据库也已经有`search_vector`的GIN索引和`embedding vector(1024)`的HNSW余弦索引。但是系统现在只会“把书放上书架”，还不会根据用户问题“从书架找出有权限阅读的几页”。现有应用没有search、lexical、dense、hybrid、RRF、rerank或RAG路由；`app/services/retrieval/`只有Embedding Provider。

当前`fts_text`直接保存原始`retrieval_text`，版本为`m2-fts-raw-retrieval-v1`。英文可依靠空格分词，连续中文用PostgreSQL `simple`配置时可能无法按“亮度”等子词命中。因此，中文关键词检索必须在文档入库和用户查询两边使用同一套、固定版本的jieba分词规则。只给查询分词不能修复已经按整段中文建立的旧词条。

当前访问规则为：同租户内文档owner、`company_owner`，或命中user/role/market ACL的用户可读；`access_level`目前不额外赋予tenant全员读取权。检索继续复用这一规则，不在M2-16偷偷改变业务权限。

#### 2. M2-16目标

1. Lexical Retrieval（关键词检索）：用版本化中文分词和PostgreSQL FTS找出字面命中的Chunk；
2. Dense Retrieval（语义检索）：把用户问题按`QUERY`用途生成BGE-M3或Fake向量，再用pgvector余弦距离找出意思接近的Chunk；
3. Hybrid Retrieval（混合检索）：同时取得两路候选，不让单一检索方式决定全部结果；
4. RRF（按两个候选榜单名次稳定融合）：按`1 / (k + rank)`合并名次，默认`k=60`，不直接相加量纲不同的FTS分数和余弦分数；
5. 在SQL候选集合中固定tenant、Document ACL、市场、active Document Version、active ready Index Set、未软删除和完整Embedding身份过滤；
6. 返回可以解释和复算的来源定位、两路原始排名/分数、RRF分数、模型revision和FTS builder版本。

#### 3. 本阶段明确不做

- 不实现BGE Reranker；
- 不调用Qwen生成答案，不实现RAG答案、引用或Evidence持久化；
- 不接入聊天、LangGraph、Agent Tool或Harness；
- 不新增前端检索页面；
- 默认不新增临时HTTP搜索路由，先以内部Service和真实PostgreSQL集成测试证明稳定合同；
- 不实现后台队列、Worker、租约、分布式任务、MCP、真实Amazon SP-API；
- 不自动开始M2-17或后续工作。

#### 4. 前置条件与已确认决策

- Git保持`main`和基线提交`5c20cf2`；保留现有3个未提交修改，不提交、不回退；
- PostgreSQL 17.11、pgvector 0.8.6保持healthy，Alembic为`20260831_0007 (head)`；
- 固定真实模型为`BAAI/bge-m3@5617a9f61b028005a4858fdac845db406aefb181`，日常测试默认使用Fake；
- 2026-08-31已幂等恢复正式Seed，实际计数为10 files、10 documents、10 document_versions、9 document_acl，0 Chunk Set、0 Index Set、0 Chunk、0 active指针；这证明后续可以从正式干净基线启动索引，不证明检索已经可用；
- Dense查询Embedding失败时返回安全、可重试的检索失败，不悄悄降级成关键词结果；否则调用者会误把“不完整混合检索”当成完整成功；
- M2-16的“可审计”是响应中保留可复算的身份、排名、分数和来源，不新增Retrieval Run/Evidence数据库表；持久化审计留给后续Context/Evidence阶段。

#### 5. 数据流

```text
可信RunContext中的tenant/user/role/market
                    + 用户query
                           |
             先建立同一份获权active候选边界
                           |
        +------------------+------------------+
        |                                     |
        v                                     v
jieba同版分词 -> PostgreSQL FTS       QUERY用途 -> EmbeddingProvider
        |                                     |
 Lexical top-30                      pgvector cosine top-30
        |                                     |
        +------------------+------------------+
                           v
                 按chunk_id去重并执行RRF
                           v
       返回final rank、两路分数分解和Source Locator
```

文档侧在索引时使用`DOCUMENT`用途生成并保存Embedding；查询侧使用`QUERY`用途临时生成查询向量。Fake Provider只证明调用、维度和确定性，不证明语义好坏；固定向量集成测试证明pgvector排序；显式本地BGE Smoke才证明真实语义模型能接入查询链。

#### 6. 权限与数据隔离策略

Repository的Dense和Lexical查询必须复用同一个基础获权条件，且在排序和`LIMIT`之前应用：

1. `tenant_id`等于可信RunContext，不接受请求体传入tenant；
2. Document和StoredFile都未软删除，文件状态可用；
3. `documents.active_version_id`等于当前Chunk的version；
4. Version处于可检索状态，`active_index_set_id`指向当前ready Index Set；
5. Chunk必须属于这个active Index Set；
6. 用户为owner、company_owner，或命中user/role/market ACL之一；
7. Dense还要求Chunk的provider/model/revision/dimension/normalize等身份与本次Query Provider完全一致。

调用者不能传role、market、ACL、version_id、index_set_id、向量、SQL或模型本地路径。跨tenant、旧版本、失败索引、未激活索引、软删除文档和无权文档统一不会进入候选集。

#### 7. 输入、输出和错误合同

- 输入：严格Schema，核心只有`query`，长度建议1至2000字符；候选数量使用服务端配置，最多只允许安全上限，不允许客户端扩大权限或任意控制SQL；
- 输出：候选Chunk的document/version/index/chunk公开ID、标题、类型、语言、市场、正文、页码/标题路径/Sheet/单元格或行范围等Source Locator、final rank；同时返回dense rank/余弦距离或相似度、lexical rank/FTS score、RRF score、Embedding身份和FTS builder版本；
- 不输出：tenant内部字段、ACL明细、Storage Key、真实磁盘路径、1024维向量、SQL、数据库异常或本地模型路径；
- 错误：空白/超长输入为安全校验错误；Provider不可用、向量身份不匹配、数据库超时/不可用为类型化安全错误；合法但没有命中返回空候选，不把无结果当系统故障；任何一路内部失败不返回伪装成完整Hybrid的200结果。

#### 8. 按顺序执行的单一职责小步骤

##### M2-16.1｜冻结检索合同、配置和错误

- 目标：只定义“可以问什么、返回什么、怎样安全失败”，不写SQL；
- 预计文件：新增`app/schemas/retrieval.py`、`app/services/retrieval/errors.py`、`tests/unit/test_retrieval_contracts.py`；按实际需要小改`app/core/config.py`和`tests/unit/test_config.py`；
- 调用链位置：未来API/Tool → **Schema（本步）** → 未来Service；前端、API、Repository、Model、PostgreSQL均不经过；
- 验证：严格字段、空白/超长query、候选上限、公开结果字段、分数有限值、来源定位和错误脱敏的单元测试；Ruff、Mypy、编译和基线哨兵；
- 能证明：边界合同稳定；不能证明数据库能检索或权限正确。

##### M2-16.2｜建立版本化中文FTS构建器和迁移0008

- 目标：让文档侧和查询侧都使用固定jieba规则，并允许旧、新FTS builder版本共存；
- 预计文件：新增`app/services/retrieval/lexical_text.py`、`migrations/versions/20260831_0008_*.py`、`tests/unit/test_lexical_text.py`、`tests/integration/test_document_chunk_fts_migration.py`；修改`app/schemas/document_chunks.py`、`app/services/documents/indexing.py`或其Mapper合同、`app/models/documents.py`及相关测试；
- 调用链位置：Index Service/未来Lexical Service → FTS Builder → Mapper/Model → PostgreSQL generated search_vector + GIN；不经过前端或HTTP API；
- 验证：中文、英文、SKU、型号、条款号两边同规则；jieba版本和配置固定；`0007→0008→0007→0008`往返；旧Index Set仍合法，新Index Set使用新版；新成品ready前active不切换；
- 能证明：中文词条可被一致构建；不能证明Hybrid排序质量。

##### M2-16.3｜建立共享获权active候选Repository

- 目标：Dense和Lexical只能从同一套获权、active、ready数据集合取候选，避免两路权限写法漂移；
- 预计文件：新增`app/repositories/retrieval.py`、`tests/integration/test_retrieval_repository_scope.py`；按需要从`app/repositories/documents.py`提取并复用只读访问条件；
- 调用链位置：未来Retrieval Service → **Repository（本步）** → Document/Version/ACL/Index Set/Chunk Model → PostgreSQL；
- 验证：owner、company_owner、user/role/market ACL允许；跨tenant、无ACL、市场不交集、旧version、非active/failed Index Set、软删除Document/File全部为零候选；
- 能证明：数据库候选边界正确；不能证明查询向量或RRF。

##### M2-16.4｜实现Dense检索

- 目标：使用`QUERY`用途生成查询向量，在获权候选中按pgvector余弦距离取前N名；
- 预计文件：新增`app/services/retrieval/dense.py`、`tests/unit/test_dense_retrieval.py`、`tests/integration/test_dense_retrieval.py`；修改`app/repositories/retrieval.py`和`app/services/retrieval/__init__.py`；
- 调用链位置：内部调用者 → Schema → Dense Service → EmbeddingProvider(QUERY) → Retrieval Repository → Model → PostgreSQL/pgvector；不经过前端和HTTP API；
- 验证：Fake用于调用和错误边界；固定1024维归一化向量在真实PostgreSQL证明排序、top-N、稳定tie-break和身份过滤；Provider/DB故障安全失败；
- 能证明：pgvector真实排序和权限同时生效；Fake不能证明真实语义质量，小数据不能证明大规模HNSW召回。

##### M2-16.5｜实现Lexical检索

- 目标：把query按与索引相同的版本分词，在获权候选中使用PostgreSQL FTS排序；
- 预计文件：新增`app/services/retrieval/lexical.py`、`tests/unit/test_lexical_retrieval.py`、`tests/integration/test_lexical_retrieval.py`；修改`app/repositories/retrieval.py`；
- 调用链位置：内部调用者 → Schema → Lexical Service → jieba/Repository → Model → PostgreSQL FTS/GIN；不经过Embedding、前端和HTTP API；
- 验证：中文“亮度”、英文、SKU、型号、数字和无结果；所有权限/active过滤与Dense一致；`EXPLAIN`只确认GIN索引可用，不强求小表一定选择索引；
- 能证明：真实PostgreSQL关键词命中；不能证明Dense或最终融合质量。

##### M2-16.6｜实现Hybrid和RRF

- 目标：并列运行两路检索，按chunk_id去重，用固定`rrf_k=60`合并名次并保留分数分解；
- 预计文件：新增`app/services/retrieval/hybrid.py`、`tests/unit/test_rrf.py`、`tests/integration/test_hybrid_retrieval.py`；修改检索Schema导出；
- 调用链位置：内部调用者 → Schema → Hybrid Service → Dense + Lexical → RRF → 安全结果；底层两路继续进入Embedding/Repository/Model/PostgreSQL；
- 验证：只在单路命中、两路命中、重复Chunk、同分tie-break、空结果和一路故障时均有确定行为；结果权限集合不得超过两路获权候选并集；
- 能证明：融合公式、顺序和分数可复算；不能证明Reranker或回答质量。

##### M2-16.7｜真实闭环验收和阶段收口

- 目标：用正式合成文档建立临时索引，验证检索后精确恢复干净Seed；
- 预计文件：新增`scripts/verify_m2_retrieval.py`、`tests/unit/test_m2_retrieval_verification.py`、`tests/smoke/test_m2_retrieval_bge_smoke.py`；修改`tests/unit/test_m2_baseline.py`及两份进度文档；
- 调用链位置：验证脚本 → Retrieval Schema/Hybrid Service → Query Embedding + Retrieval Repository → Model → PostgreSQL FTS/pgvector；仍不经过前端、HTTP API、Reranker、Qwen、Evidence或Agent；
- 验证：Fake 10文档日常闭环、固定向量数据库排序、显式离线BGE小型语义Smoke、跨权限/版本/删除故障矩阵、`EXPLAIN`索引可用性、全量后端质量门；最后只清理本次生成物并恢复10/10/10/9和0索引行；
- 能证明：当前规模真实数据库闭环和确定性；不能承诺百万Chunk、并发负载、生产延迟、HNSW全量召回率或最终RAG答案质量。

#### 9. 阶段完成标准

1. 中文关键词、Dense语义和RRF混合检索全部通过真实PostgreSQL验证；
2. tenant、owner/company_owner、user/role/market ACL、active Version、active ready Index Set、软删除和Embedding身份在排序前生效；
3. 旧版、失败、未激活、跨tenant和无权限Chunk不会进入任何候选榜单；
4. 结果包含安全来源定位、两路名次/分数和RRF分解，不泄露内部字段；
5. 日常测试默认Fake，固定向量负责数据库顺序，真实BGE只由显式Smoke加载且强制离线；
6. 迁移、Ruff、Mypy、编译、依赖、聚焦测试和后端全量通过，正式Seed精确恢复；
7. 没有实现Reranker、Qwen回答、Evidence、Tool、Agent、前端或HTTP检索路由。

#### 10. 主要风险和优先排查

- 中文搜不到：先比较文档侧与查询侧的builder版本、jieba版本、HMM配置和最终分词文本，再查GIN/tsquery；
- Dense结果异常：先查`DOCUMENT/QUERY`用途、1024维、归一化、model/revision和cache key，再查余弦操作符与排序方向；
- 权限泄露：先比较Dense/Lexical是否共用同一access clause，以及过滤是否发生在`ORDER BY/LIMIT`之前；
- 旧数据被搜到：先查Document active Version和Version active Index Set两级连接，不只看Chunk自身ready字段；
- 小表不走HNSW/GIN：先用`EXPLAIN`确认索引可用，再区分优化器合理选择顺序扫描和索引定义错误；不能为了让测试好看而关闭正常优化器行为；
- Fake语义看似错误：Fake只保证确定性，不保证近义句排名；语义判断必须看显式BGE Smoke；
- Provider故障：返回类型化可重试错误，不把Lexical单路伪装成完整Hybrid成功。

#### 11. 确认记录、当前结果与明确停止点

用户在完整方案和通俗解释后两次回复“继续”，视为确认上述M2-16范围与默认决策。确认后的第一个动作原计划是恢复正式Seed；用户中断命令后只读核对确认事务实际已经完成，当前为10 files、10 documents、10 versions、9 ACL，0 Chunk Set、0 Index Set、0 Chunk、0 active指针。随后用户指出应先更新文档，因此当前只补齐确认与方案记录，不开始生产代码。

M2-16.1与M2-16.2已经按下方步骤日志完成。**当前必须停止并等待用户确认；只有再次明确授权后才可进入M2-16.3。当前确认不授权M2-16.3自动开始，更不授权Reranker、RAG、前端、Agent或M2-17。**

### 2026-08-31｜M2-16.1｜冻结检索合同、配置和安全错误

**状态：已完成；已验证；明确停止在M2-16.1。**

1. 本步解决的问题：M2-15只有“文档如何被索引”的内部事实，没有规定未来Dense、Lexical和Hybrid“允许接收什么、必须返回什么、怎样安全失败”。本步先冻结共同边界，避免后续三路各自发明字段、用非法数字伪装未命中，或把SQL、路径和数据库原始异常带到公开响应；
2. 大白话运行过程：未来调用者只交一段`query`；tenant、用户、角色、市场、ACL、版本、Index Set、向量、SQL和候选数量都不能从请求体伪造。未来Service会按本步集中配置取候选，并把每个Chunk的公开身份、文档信息、正文、来源位置和真实命中分数装入同一份响应。本步只定义这只“安全标准箱子”和固定错误说明，还没有去数据库找任何Chunk；
3. 输入合同：`RetrievalRequest`继承项目现有严格Schema，先去除首尾空白，再要求1至2000字符且拒绝任何额外字段。2000是代码级硬上限；运行配置新增`retrieval_query_max_characters=2000`，未来Service可以在硬上限内进一步收紧。请求不接受候选数量，Dense、Lexical和Hybrid最终候选默认均为30、合法上限100；`hybrid_candidate_count`不得大于两路候选之和，Reranker top-k不得大于任一路或Hybrid候选数，`rrf_k`保持60；
4. 输出合同：公开候选只含document/version/index_set/chunk UUID，文档标题、类型、语言、市场和Chunk正文。PDF、DOCX、XLSX、CSV分别使用有辨别字段的类型化Source Locator，能表达页码/多页、标题路径、块/段落/表格、Sheet、单元格范围和行范围，且拒绝Storage Key等额外字段；
5. 分数决定：`dense`与`lexical`为可选分解，至少一路真实命中；未进入某一路榜单明确使用`None`，不用0、负排名或无穷大冒充。所有公开浮点数使用有限值合同，拒绝NaN和正负Infinity；所有榜单名次和最终名次从1开始。Dense按当前pgvector余弦定义限制distance为0至2、similarity为-1至1，两者同时出现时必须满足`similarity = 1 - distance`；Lexical的具体FTS归一化公式要到M2-16.5才冻结，因此本步只限制为有限值，不凭空设置上限；RRF分数必须为正有限值，Hybrid要求两种索引身份、`rrf_k`和每项RRF分数，最终名次必须连续；
6. 错误边界：新增检索输入错误、Embedding Provider不可用、Embedding身份不匹配、数据库不可用、数据库超时和检索内部失败六个专用异常类。构造器不接收原始异常文本，只生成固定公开中文消息；新增通用`DATABASE_UNAVAILABLE`公开错误码并映射未来HTTP 503，其余复用既有422/503/504/500语义。未来代码可以用异常链保留内部原因供日志排查，但`to_detail()`不会输出SQL、Storage Key、磁盘/模型缓存路径、环境变量或数据库连接信息；
7. 实际修改文件与职责：
   - `app/schemas/retrieval.py`：新增请求、候选/文档身份、四类来源定位、Dense/Lexical分解、Embedding/FTS身份、结果和按模式校验的统一响应；
   - `app/services/retrieval/errors.py`：新增六类固定消息的类型化检索错误；
   - `app/core/config.py`与`.env.example`：新增query硬上限、Hybrid最终候选数及候选组合校验；业务模块没有自行读取环境变量；
   - `app/schemas/common.py`与`app/api/errors.py`：登记`DATABASE_UNAVAILABLE`并冻结其503映射；
   - `app/schemas/__init__.py`与`app/services/retrieval/__init__.py`：从项目公共包入口导出新合同和错误；
   - `tests/unit/test_retrieval_contracts.py`：覆盖严格输入、四类定位、分数/排名、三种模式、敏感字段和错误脱敏；
   - `tests/unit/test_m2_baseline.py`：补充集中配置合法/非法组合并把阶段哨兵推进到“只有合同、没有检索执行”；
   - `docs/progress/M2_KNOWLEDGE_RAG.md`与`docs/PROJECT_PROGRESS.md`：记录本步决定、验证、Seed恢复、风险和停止点；
8. 完整调用链位置：未来链路是`前端或Agent Tool → 未来API/Tool → Retrieval Schema（本步） → 未来Retrieval Service → 未来Embedding/Repository → 现有Model → PostgreSQL`。本步实际只经过Schema、集中配置和错误边界；没有经过前端、HTTP API、检索Service编排、查询Embedding调用、Repository、Model或PostgreSQL查询；
9. TDD证据：先新增合同测试，首次运行在收集阶段按预期因`ModuleNotFoundError: app.schemas.retrieval`失败，证明RED来自目标能力缺失。最小实现后第一次GREEN只剩1项配置样例失败：样例同时违反Reranker和Hybrid两个关系，校验器先报告前者；只把该测试的Reranker值改为合法5，让它单独验证Hybrid关系，没有放宽生产配置。最终聚焦合同与基线测试为`83 passed in 4.01s`，加入静态类型表达修正和余弦一致性断言后复跑仍为`83 passed`；
10. 最终验证：后端全量`.venv\Scripts\python.exe -m pytest -q`为`554 passed, 8 skipped in 90.06s`，8项仍是既有显式Smoke/环境条件跳过；`.venv\Scripts\ruff.exe check app tests scripts migrations`全仓通过，本步9个代码/测试文件`ruff format --check`通过；全仓format check只报告用户原先保留的`tests/integration/test_document_chunk_set_migration.py`换行/格式差异，本步没有机械改写该文件。Mypy检查`app`及本步两份测试共105个源码文件通过；`compileall -q app tests scripts migrations`无错误；`pip check`为`No broken requirements found`；`git diff --check`通过；Alembic current/heads均为`20260831_0007 (head)`且`alembic check`无新操作，因此本步不需要迁移；
11. Seed与基础设施恢复：全量测试按既有集成测试设计把共享演示Seed清理为0行，复核发现后只运行项目既有幂等模块入口`seed_m1 → seed_m2_files → seed_m2_complex_files`恢复，没有删除卷、清空数据库或Storage。最终只读结果为PostgreSQL 17.11 + pgvector 0.8.6容器healthy，10 files、10 documents、10 versions、9 ACL、10 parse pending、10 index pending、0 active Version、0 active Index Set、0 Chunk Set、0 Index Set、0 Chunk；Storage为10 uploads、0 parsed JSON、0 chunks JSON；M1 `LR-TL-MUSH-OR01 / DE-FRA`可售库存125；固定BGE快照8个必需文件与manifest均在本地，日常配置仍为Fake和`model_local_files_only=True`，本步从未加载真实模型；
12. 能证明与不能证明：测试能证明公开合同拒绝伪造字段、空白/超长问题、非法排名、非有限分数、矛盾余弦值、错误模式组合和敏感内部字段，并能表达四类文档定位及单路未命中；能证明集中配置拒绝越界与非法组合，现有后端没有被公共导出和错误码修改破坏。它不能证明中文分词、FTS/GIN命中、pgvector查询排序、tenant/ACL/active过滤、两路RRF真实融合、性能或真实BGE语义质量，因为这些分别属于M2-16.2至M2-16.7；
13. 风险与优先排查：未来请求422先看是否有多余tenant/limit等字段或query去空白后为空/超过配置；响应校验失败先看检索模式与Dense/Lexical/RRF字段是否一致、名次是否从1连续；Dense分数失败先核对是否误把inner product当余弦distance/similarity；中文分数范围不能在本步猜测，等M2-16.5按实际SQL冻结；错误泄露优先检查是否绕过专用错误、直接把`str(database_error)`写入响应；配置启动失败先比较Hybrid、两路候选和Reranker top-k关系；
14. 下一步与停止点：M2-16.1已经完成并验证，当前明确停止。不得自动开始M2-16.2，不新增jieba分词器、0008迁移、Repository、SQL、Dense/Lexical/Hybrid Service、RRF实现或真实BGE加载；等待用户理解和明确确认后再继续。

### 2026-08-31｜M2-16.2｜版本化中文分词和FTS Builder迁移

**状态：已完成；已验证；明确停止在M2-16.2。**

1. 本步解决的问题：原索引把整段`retrieval_text`原样交给PostgreSQL `simple`配置。英文和SKU可以按空白、标点拆开，但连续中文通常会被视作大词，未来查询“亮度”未必能命中文档里的“蘑菇灯亮度调节说明”。本步增加文档侧与未来查询侧共用的版本化中文词条构建器，并让数据库同时接受旧raw与新版索引代次；
2. 大白话运行过程：文档入库前先经过同一台“固定切词机”，例如“蘑菇灯亮度调节说明”稳定变成`蘑菇 灯 亮度 调节 说明`，再保存到`fts_text`。PostgreSQL继续自动把`fts_text`生成`search_vector`并使用既有GIN索引。未来用户查询也必须走同一台切词机，这样两边使用相同词条；本步只准备这台机器及数据库版本边界，还没有编写正式关键词检索Service；
3. Builder身份与确定性：新增`m2-fts-jieba-search-v1`，固定jieba `0.42.1`、随包词典SHA-256 `7197c3211ddd98962b036cdf40324d1ea2bfaa12bd028e68faa70111a88e12a8`、search模式、`HMM=False`、NFKC + casefold规范化和Unicode字母数字过滤。Builder使用独立Tokenizer，不接受运行期自定义词，不依赖jieba全局词典状态；词典文件、包版本或输入边界不符合合同都会安全失败；
4. 文档与查询一致性：`FtsTextPurpose.DOCUMENT`和`QUERY`用于审计用途，但当前明确使用同一套规则。词条保持原顺序和词频，不去重；英文被统一为小写，全角字符被规范化，SKU、型号、数字和条款组成部分继续可搜索。输入必须是非空字符串，输入与输出均受2,000,000字符存储边界保护；
5. 索引写入变化：`map_index_rows()`不再令`fts_text = retrieval_text`，而是调用共享Builder；`DocumentChunkWriteFacts`也用同一Builder复算并拒绝伪造词条。`retrieval_text`仍完整保留给展示、Embedding和后续RAG，只有独立的`fts_text`变成分词产物。Index Set确定性身份原本就包含`fts_builder_version`，因此新旧规则自然生成不同索引代次，不会把旧成品误当新版复用；
6. 迁移决定：新增Alembic `20260831_0008`，只调整`document_index_sets`身份约束，允许`m2-fts-raw-retrieval-v1`和`m2-fts-jieba-search-v1`共存；没有新增列，也没有原地改写旧Chunk。旧ready索引可继续保持active，新版索引只有ready后才能通过既有复合外键切换active。降级前如果发现新版Index Set会明确拒绝，避免为了回到0007而静默删除或误解释新数据；
7. 实际修改文件与职责：
   - `app/services/retrieval/lexical_text.py`：实现固定身份、输入边界、独立jieba Tokenizer、锁、缓存和文档/查询共享入口；
   - `app/services/retrieval/__init__.py`：从稳定公共入口导出FTS Builder合同；
   - `app/services/documents/indexing/contracts.py`：将当前Index Set身份推进到新版Builder，并复算校验每行`fts_text`；
   - `app/services/documents/indexing/mapping.py`：在索引Mapper中真正生成新版词条；
   - `app/models/knowledge.py`：ORM约束同时描述旧raw与新版FTS身份；
   - `migrations/versions/20260831_0008_versioned_jieba_fts.py`：升级新旧共存，降级遇到新版数据时安全拒绝；
   - `requirements.txt`：将jieba从兼容范围固定为精确`0.42.1`；
   - `scripts/verify_m2_index_pipeline.py`：索引验收改为按版本化Builder复核数据库`fts_text`；
   - `tests/unit/test_lexical_text.py`：覆盖身份、依赖固定、中文/英文/SKU/型号/条款、规范化、顺序、词频、确定性和非法输入；
   - `tests/unit/test_document_index_mapping.py`：验证Mapper使用新版身份与共享词条结果；
   - `tests/integration/test_document_chunk_fts_migration.py`：验证迁移往返、旧新共存、active切换、数据库约束、真实FTS命中和安全降级；
   - `tests/integration/test_document_index_service.py`：从真实索引Service落库结果断言新版身份与每个Chunk词条；
   - `tests/unit/test_m2_baseline.py`：把阶段哨兵推进到“Builder和0008已存在，但候选Repository与检索执行仍不存在”；
   - `docs/progress/M2_KNOWLEDGE_RAG.md`与`docs/PROJECT_PROGRESS.md`：同步本步决定、验证、Seed和停止点；
8. 完整调用链位置：索引侧实际经过`DocumentIndexService（已有） → FTS Builder（本步） → Index Mapper/合同（本步修改） → DocumentChunk Model（已有，约束同步） → PostgreSQL generated search_vector + GIN（已有）`；迁移直接作用于Model到PostgreSQL的Index Set身份边界。查询侧目前只证明`QUERY → FTS Builder`能生成相同词条，尚未经过Retrieval Service、Repository或生产SQL。前端、HTTP检索API、Agent Tool、Dense、Hybrid/RRF、Reranker、Qwen和真实BGE都未经过；
9. TDD RED证据：先写Builder与Mapper测试，首次收集按预期因`ModuleNotFoundError: app.services.retrieval.lexical_text`失败；最小实现后只剩Mapper样例少算一次标题中的“安全要求”，根据“保持词频”合同修正测试期望而未改生产逻辑，随后`16 passed`。再先写迁移和阶段边界测试，首次为`3 failed, 48 passed`，失败分别来自0008不存在、数据库拒绝新版身份和阶段哨兵找不到迁移，均准确指向待实现能力；
10. 迁移调试记录：第一次创建约束时因Alembic命名约定对原始名称再次加前缀，实际要删除的约束没有找到；改用`op.f(...)`指明已格式化名称后转绿。新增安全降级测试时，测试清理顺序先删Tenant触发Version外键，只调整测试按依赖顺序删Version再删Tenant；该次失败留下的唯一测试tenant经只读UUID精确核对后定向删除并复核为0，没有清空数据库或Storage；
11. 最终验证：Builder/Mapper首轮GREEN为`16 passed`；迁移与阶段边界为`51 passed`，安全降级单测为`3 passed`；包含合同、Model、迁移、Repository、索引Service与API的扩大聚焦集为`151 passed in 19.37s`，格式化后关键集复跑`79 passed in 12.54s`。后端全量`.venv\Scripts\python.exe -m pytest -q`为`568 passed, 8 skipped in 92.41s`，8项仍是显式Smoke或环境条件跳过；
12. 工程质量与迁移验证：`.venv\Scripts\python.exe -m ruff check app migrations scripts tests`全仓通过，本步12个文件`ruff format --check`通过；Mypy检查`app`、验收脚本和相关测试共110个源文件为`Success: no issues found`；`compileall -q app migrations scripts tests`无错误；`pip check`为`No broken requirements found`，运行环境jieba确认为`0.42.1`；`git diff --check`通过。Alembic current与heads均为`20260831_0008 (head)`，`alembic check`为`No new upgrade operations detected`；PostgreSQL容器保持healthy；
13. Seed与基础设施恢复：全量测试后只运行既有幂等入口`seed_m1 → seed_m2_files → seed_m2_complex_files`。最终只读事务显示`transaction_read_only=on`，PostgreSQL 17.11、pgvector 0.8.6，10 files、10 documents、10 versions、9 ACL，10 parse pending、10 index pending、0 active Version、0 active Index Set、0 Chunk Set、0 Index Set、0 Chunk、0非空Embedding；Storage为10 uploads、0 parsed JSON、0 chunks JSON、0其他对象；M1 `LR-TL-MUSH-OR01 / DE-FRA`可售库存125。本步没有加载BGE-M3，日常测试仍使用Fake Provider；
14. 能证明与不能证明：测试能证明相同输入在文档与查询用途产生同版确定性词条，新索引Service真实保存新版词条，PostgreSQL约束允许旧新代次共存且阻止未知版本，新成品ready前不能切active，新版词条通过参数化FTS表达式能命中中文“亮度”，迁移可以安全往返且不会静默丢新版数据。它不能证明生产Lexical Repository的tenant/ACL/active候选边界、Top K排序、GIN在大数据下的执行计划、Dense/Hybrid/RRF效果、真实BGE语义、并发或生产延迟，因为这些属于M2-16.3至M2-16.7；
15. 风险与优先排查：中文搜不到时先比较文档和query的`fts_builder_version`、最终`fts_text`、jieba版本与词典Hash，再看`search_vector`和tsquery；启动时报Builder错误先检查虚拟环境是否确切安装jieba 0.42.1及官方词典是否被改动；旧active索引中文效果不变是预期，必须重建新版Index Set并在ready后切换，不能原地伪装升级；迁移降级被拒绝时先找新版Index Set并走显式重建/清理方案，不能绕过保护；内存或延迟异常先看是否把超大正文绕过既有Chunk边界直接交给Builder；
16. 下一步与停止点：M2-16.2已经完成并验证，当前明确停止。不得自动开始M2-16.3，不新增共享获权候选Repository、tenant/ACL/active过滤、Dense/Lexical生产查询、Hybrid/RRF、HTTP API或真实模型加载；等待用户理解和明确确认后再继续。
