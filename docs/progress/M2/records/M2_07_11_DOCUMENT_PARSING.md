# M2-07 至 M2-11：文档解析与版本化解析产物

> 本文件保存从迁移前单文件中拆出的完整历史方案、实施日志与验证证据。
> 当前状态和阅读入口见 [M2入口](../M2_KNOWLEDGE_RAG.md)。

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
- `docs/progress/M2/M2_KNOWLEDGE_RAG.md`、`docs/PROJECT_PROGRESS.md`：记录实际结果和新的停止点；本步没有把进度写入README。

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

## 25. M2-22真实评估后的Parser设计修正指引（2026-09-08）

本文件前述M2-11.1至M2-11.5记录是当时基于5份小型复杂合成文件得到的历史实施事实，不回写或伪装为已经具备的新能力。M2-22.4让18份文档进入真实摄取/解析链后，严格事实恢复只有22/34；随后只读诊断证明10条外部缺失在Native正确页逐字存在，却因`detected_document_table/two_column`触发整文档Docling选择而丢失。连续长PDF探针还复现120秒超时、OCR线程未退出和后续失效页面句柄，说明M2-11.4“小文件通过”的结论不能外推为真实长文档稳定。

图文DOCX原记录的0/2也已进一步拆分：`QC-VISUAL-17`是页眉普通文字未提取，`QUARANTINE 12 PCS`才是正文inline shape图片未OCR。在R-03实施前，`DocxParser`只遍历顶层正文段落/表格，旧Docling标准DOCX后端也没有补回这两类内容；R-03完成后的现状见本节末尾更新。

用户已确认新的修复原则：`quality.py`负责确定性Native文本健康度，`routing.py`只执行路由；健康Native不能被结构复杂度标签整文档覆盖；Docling只作受控候选并在独立进程内运行；DOCX分别提取页眉/页脚和按Run原位置插入图片OCR；解析后使用70%全文突降、逐页退化和OCR空结果规则决定阻断或告警。完整步骤、文件范围、验收标准和授权边界统一见[M2-22数据与Parser记录第21节](M2_22_01_04_DATA_AND_PARSER.md#21-m2-224r-parser质量修复确认方案2026-09-08)，本文件不复制后续实施流水账。

M2-22.4R-01已随后完成：Native文本现按版本化有效字符、最低文字、内容页覆盖和低文字/扫描信号分为`healthy/suspect/unusable`，健康PDF不再因表格/双栏标签被整文档Docling覆盖；8份官方PDF已验证14/14恢复，扫描PDF仍经Docling恢复2/2。这只修复路由部分，不代表整个Parser已收口；完整代码与验证见[M2-22数据与Parser记录第22节](M2_22_01_04_DATA_AND_PARSER.md#22-m2-224r-01实施记录native文本健康度与pdf无损路由2026-09-08)。

M2-22.4R-02也已随后完成：主进程不再缓存Docling Converter，每份增强文档固定进入一次性Windows `spawn`子进程，并受父进程总时限、进程树采样RSS和Snapshot字节上限约束；超时、崩溃或超限会清理进程并返回固定失败，下一任务获得干净进程。真实扫描PDF在隔离后仍恢复2/2，单次实测总耗时约77.72秒、峰值约1.83 GiB。完整代码、RED/GREEN、资源和限制见[M2-22数据与Parser记录第23节](M2_22_01_04_DATA_AND_PARSER.md#23-m2-224r-02实施记录docling故障进程隔离2026-09-08)。

M2-22.4R-03现已完成：`DocxParser` v2单独提取Section页眉/页脚，并在正文段落Run内部按`wp:inline`锚点生成原位图片OCR Segment；Canonical用可选且显式版本化的`m2-docx-source-v1`区分`docx_header/docx_footer/docx_image_ocr`，记录图片序号、Hash、尺寸、Provider/版本与置信度，普通Artifact v1 Block继续保持旧序列化/Hash形状。真实图文DOCX经正式Router保持Native，`QC-VISUAL-17`与`QUARANTINE 12 PCS`均找回；DOCX视觉标签不再触发无收益的标准Docling。Word物理页码仍不可由`python-docx`可靠取得，因此保留Section/段落/Run来源而不伪造页码。完整代码、安全边界、真实OCR和视觉检查见[M2-22数据与Parser记录第24节](M2_22_01_04_DATA_AND_PARSER.md#24-m2-224r-03实施记录docx页眉页脚与原位图片ocr2026-09-08)。当前下一动作等待R-04单独授权，不得提前进入R-04或M2-22.5。
