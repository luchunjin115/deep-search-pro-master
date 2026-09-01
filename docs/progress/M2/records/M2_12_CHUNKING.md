# M2-12：结构感知分块

> 本文件保存从迁移前单文件中拆出的完整历史方案、实施日志与验证证据。
> 当前状态和阅读入口见 [M2入口](../M2_KNOWLEDGE_RAG.md)。

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
