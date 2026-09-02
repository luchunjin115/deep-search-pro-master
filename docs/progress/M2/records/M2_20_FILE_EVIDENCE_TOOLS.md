# M2-20：文件与 Evidence 受控读取 Tool

> 本文件保存 M2-20 的正式方案、用户确认、逐步实施日志和完整验证证据。
> 当前状态和阅读入口见 [M2入口](../M2_KNOWLEDGE_RAG.md)。

## 1. 2026-09-02｜M2-20完整方案与用户确认

**状态：M2-20.1至M2-20.6全部完成并验证；M2-20已收口。**

### 1.1 当前现状和缺少的能力

M2-19已经把`search_knowledge`接入隔离M2 Registry与Harness，并能在当前tenant、用户和文档ACL范围内生成可持久化的Context与Evidence。现有代码还不能把M2文档Evidence详情作为Agent Tool安全展开，也不能让Agent只凭公开`file_id`和受控定位条件读取已发布解析产物中的有限内容。

现有可复用基础包括：

- `FileRepository`与`document_access_clause`已经统一实现owner、company owner、user/role/market ACL、tenant和软删除过滤；
- `RoutedParseResult → selected_artifact → CanonicalParsedArtifact`已经形成项目自有解析事实合同；
- M1数据库Evidence已有安全详情读取，M2文档Evidence已有持久化、当前ACL/active代次复核和引用白名单能力；
- M2 Registry、Harness、可信`RunContext/CurrentUser`、预算、超时和Trace已经可复用。

### 1.2 本阶段目标

1. 新增`read_uploaded_file`严格合同和只读Tool：只接受公开`file_id`与可选受控locator，服务端自行获权并读取解析产物，返回有界文本或表格预览；
2. 新增`get_evidence_detail`严格合同和只读Tool：只接受`evidence_id`，统一安全返回M1数据库Evidence或M2文档Evidence详情；
3. M1 Registry继续精确两个Tool，隔离M2 Registry累计精确五个Tool；
4. 两个新Tool都经过Harness可信身份、角色、预算、超时、Trace和脱敏Envelope边界；
5. 用真实PostgreSQL、LocalStorage与Fake/确定性数据完成owner/ACL、跨tenant、软删除、旧代次、范围、故障和泄露矩阵。

### 1.3 明确不做

- 不新增文件或Evidence HTTP API；
- 不接入知识Agent、LangGraph、Qwen或前端；
- 不修改M1库存图或把五个M2 Tool自动投影给现有库存Provider；
- 不允许模型传路径、Storage Key、tenant、用户、角色、市场、SQL或服务端读取预算；
- 不直接读取整份原始二进制文件，不重新运行Parser，不把解析产物无界塞给模型；
- `read_uploaded_file`初版不创建新的Document Evidence，不让它成为M2-21最终回答的无引用事实旁路；
- 不修改全局Tool次数预算，也不处理真实CPU Reranker与8秒Harness预算冲突；
- 不实施M2-21及后续能力。

### 1.4 已确认的推荐决策

1. `read_uploaded_file`模型输入只允许`file_id`和可选的严格分类型locator；读取长度、页数、行数和单元格数量由服务端限制；
2. PDF一次最多3页，XLSX/CSV一次最多50行，成功结果总正文最多8000字符；DOCX只允许明确block、paragraph或table定位，省略locator时只返回服务端有界预览；
3. 只读取已经发布并重新通过`RoutedParseResult`合同验证的`selected_artifact`，不相信原始路径或未校验JSON；
4. 具体`file_id`可以读取获权、未删除且`parse_status=ready`的关联版本；不强制版本已经active，但输出必须明确版本和`is_active_version`，搜索仍只使用active ready索引；
5. `get_evidence_detail`输入只允许`evidence_id`，同时支持既有M1 database Evidence与M2 knowledge/user_file Evidence；
6. M2文档Evidence详情读取必须同时复核Context请求者、当前ACL、Document/File软删除、active Version/Index Set和完整Chunk身份；不可见、跨tenant、跨用户、撤权或过期统一为`EVIDENCE_NOT_FOUND`；
7. Tool专用M2文档详情补充公开`file_id`，用于Evidence详情到文件读取的下一跳；不暴露tenant、owner、ACL、Storage Key、路径、SQL或数据库连接；
8. `get_evidence_detail`成功Envelope携带请求的Evidence ID；`read_uploaded_file`不伪造Evidence，成功Envelope的`evidence_ids`为空；
9. 三个现有业务角色都可调用两个新Tool，实际可见资源继续由当前用户和文档ACL决定；两个Tool均为`side_effect=read`、`data_scope=tenant`；
10. M1 Registry继续精确两个Tool；M2 Registry累计精确五个Tool：`get_product_spec`、`search_inventory`、`search_knowledge`、`read_uploaded_file`、`get_evidence_detail`；
11. M2-20日常测试不加载或下载真实BGE/Qwen；
12. 当前一次运行最多两个Tool调用，`search → detail → read`三跳策略和全局预算是否调整留到M2-21统一决定，本阶段不越权修改。

### 1.5 实施步骤

#### M2-20.1｜冻结合同和五Tool Registry

- 新增四类安全locator输入、`ReadUploadedFileInput/Result`、`GetEvidenceDetailInput/Result`和Tool专用文档详情；
- `ToolName`加入两个新名称；
- M1 Registry保持两个Tool，M2 Registry精确累计五个Tool；
- 只登记元数据和公共导出，不创建执行Tool、Service或Repository读取入口；
- 预计文件：`app/schemas/common.py`、`files.py`、`evidence.py`、`__init__.py`、`app/tools/registry.py`及合同测试。

#### M2-20.2｜实现安全解析产物读取Service

- 新增一次性获权读取查询，服务端取得私有`parsed_storage_key`；
- 有界加载并验证`RoutedParseResult`，从`selected_artifact`按locator生成确定性有界结果；
- 预计文件：`app/services/file_reading.py`、Repository、配置、错误和Service测试。

#### M2-20.3｜实现`ReadUploadedFileTool`并接入Harness

- 绑定可信`CurrentUser`与`ToolExecutionContext`，通过M2 Registry、权限、预算、超时和Trace执行Service；
- 返回安全`ToolEnvelope`且不伪造Evidence ID；
- 预计文件：`app/tools/read_uploaded_file.py`、公共导出及Tool/Harness测试。

#### M2-20.4｜扩展统一Evidence详情Service

- 保持M1 database Evidence行为，新增M2文档Evidence当前请求者、ACL、软删除、active代次和完整来源身份复核；
- 构造不含内部字段的严格详情；
- 预计文件：`app/repositories/evidence.py`、`app/services/evidence.py`及单元/真实PostgreSQL测试。

#### M2-20.5｜实现`GetEvidenceDetailTool`并接入Harness

- 只接受Evidence UUID，绑定可信身份并通过Harness返回详情；
- 成功Envelope只携带该Evidence ID，失败统一脱敏；
- 预计文件：`app/tools/get_evidence_detail.py`、公共导出及Tool/Harness测试。

#### M2-20.6｜完成权限/范围/故障矩阵与收口

- 覆盖三角色、owner/company owner、user/role/market ACL、跨tenant/用户、撤权、软删除、旧代次、未解析/失败状态、locator越界、范围过大、Storage/产物/数据库故障、预算/超时/Trace和敏感字段泄露；
- 运行相邻回归、全量门禁和工程质量，恢复正式Seed并只读复核；
- M2-20完成后明确停止，等待用户单独确认M2-21。

### 1.6 完整调用链位置

M2-20最终将形成两条内部链路：

```text
Schema → M2 Registry → Harness → ReadUploadedFileTool
→ File Reading Service → File/Document Repository → PostgreSQL + Storage
```

```text
Schema → M2 Registry → Harness → GetEvidenceDetailTool
→ Evidence Service/Repository → PostgreSQL
```

M2-20不经过前端、HTTP知识API、知识Agent/LangGraph、Qwen或最终回答生成。M2-20.1只到`Schema → Tool Registry元数据`。

### 1.7 各步验证方式与完成标准

- 每步先写失败测试并记录RED，再做最小GREEN；
- 合同测试证明额外字段、路径、身份、SQL、读取预算和超范围locator被拒绝；
- Registry测试证明M1精确两个、M2精确五个，版本、角色、scope、side effect、timeout和模型描述正确；
- Service测试使用Fake与真实Storage/PostgreSQL证明重新获权、产物验证、定位、裁剪和错误脱敏；
- Tool测试证明可信身份绑定、Harness权限/预算/超时/Trace和Envelope；
- 相邻回归覆盖M1 Registry/Harness/库存图及M2搜索/Context/Evidence；
- 按风险运行全量、Ruff、格式、Mypy、compileall、pip check、diff check和Alembic门禁；
- 全量若仍只有既有跨月上传Key测试失败，必须明确区分且不越权修改；
- 测试修改正式演示数据后，按既有Seed入口恢复并只读复核；
- 只有代码、真实验证和完整日志均完成后才能把对应步骤标记为已完成。

### 1.8 主要风险与排查顺序

1. 读取无结果：先查`CurrentUser/tenant → File/Document软删除 → owner/ACL → Version parse状态 → parsed_storage_key`；
2. locator失败：查文件类型与locator discriminator、范围硬上限、Canonical block/table/page/sheet事实，不先放宽Schema；
3. 产物失败：查Storage对象存在性/读取上限、`RoutedParseResult`验证、source hash和selected artifact，不返回私有Key或原始异常；
4. Evidence失败：查source type/schema version、Context请求者、当前ACL/active代次、完整Chunk身份，再查数据库；
5. Tool失败：查M1/M2 Registry隔离、RunContext身份绑定、预算发生点、timeout和Trace状态；
6. 当前解析JSON仍需有界加载后定位，能证明小型合成语料，不证明超大文件流式随机访问；
7. DOCX视觉页码仍受既有解析质量边界限制，不伪造不存在的页码；
8. `read_uploaded_file`初版没有新Evidence，因此M2-21不得把其内容作为无引用最终事实。

## 2. 2026-09-02｜M2-20.1｜冻结合同和五Tool Registry

**状态：已完成；已验证；明确停止在M2-20.1。**

本步输入是模型未来可提供的公开`file_id/evidence_id`与可选安全locator；输出是严格Pydantic合同和只读Registry元数据。上游Agent/API尚不存在，下游Service/Repository/Storage/Evidence读取尚未实现。本步明确不创建`ReadUploadedFileTool`、`GetEvidenceDetailTool`或任何执行Service。

1. 本步解决的问题：M2-19完成后，公共`ToolName`和隔离M2 Registry仍只有`search_knowledge`，项目没有“按公开file ID有限翻页”或“按Evidence ID安全展开”的模型输入/输出合同；如果不先冻结，后续Service容易接受路径、身份、SQL或调用者自定预算，也无法证明M1两Tool没有被M2扩展污染；
2. 大白话运行过程：本步只制作两张严格申请表和更新M2门禁名册。模型未来可以填写“哪个公开文件、看哪一小段”或“展开哪张Evidence卡”，但不能填写路径、Storage Key、tenant、用户、角色、市场、SQL或扩大读取预算。系统现在只认识这两种申请表，还没有真正打开Storage或数据库；
3. 文件输入合同：`ReadUploadedFileInput`只包含`file_id`和可选discriminated locator；discriminator是“按`source_type`选择PDF/DOCX/XLSX/CSV不同规则”的严格类型开关。PDF最多连续3页；DOCX必须且只能指定block/paragraph/table之一；XLSX只能二选一指定A1单元格矩形或完整行窗口，最多50行、1000单元格且拒绝超过XFD/1048576边界；CSV最多50行；额外字段统一拒绝；
4. 文件输出合同：`ReadUploadedFileResult`只包含公开File/Document/Version身份、原文件基名、来源类型、是否active、1至12个带公开locator的section、精确字符总数、截断标志和合成数据标志；单section与总结果正文硬上限均为8000字符，字符总数、来源类型和截断状态必须自洽；不包含tenant、owner、ACL、Storage Key、路径或SQL；
5. Evidence合同：`GetEvidenceDetailInput`只包含`evidence_id`；`GetEvidenceDetailResult.detail`是按`source_type`区分的既有M1 `EvidenceDetail`或新增`ToolDocumentEvidenceDetail`。后者继承M2安全文档详情并只补公开`file_id`下一跳；`evidence_id`属性从已验证detail派生，不重复相信调用者；
6. Registry合同：公共`ToolName`新增`read_uploaded_file/get_evidence_detail`；M1 Registry继续精确`get_product_spec/search_inventory`两个，M2 Registry按稳定排序精确五个。两个新定义均为`1.0.0`、3000ms、三业务角色、`data_scope=tenant`、`side_effect=read`，描述明确用途、返回、有界限制、合成数据和禁止字段；没有把它们接入M1 Provider或库存Agent；
7. 模块边界修正：文件输入locator保存在既有`app/schemas/files.py`；文件输出单独放到`app/schemas/file_reading.py`。原因是既有`retrieval.py`已经依赖`files.Sha256`，而输出section又需要`RetrievalSourceLocator`；独立输出模块避免`files ↔ retrieval`循环导入，同时没有创建Service或执行层；
8. 实际修改文件与职责：
   - `app/schemas/common.py`：公共Tool名称累计为五个，既有12条Envelope Evidence上限不变；
   - `app/schemas/files.py`：新增四格式严格输入locator、范围验真和`ReadUploadedFileInput`；
   - `app/schemas/file_reading.py`：新增公开有界section和`ReadUploadedFileResult`自洽校验；
   - `app/schemas/evidence.py`：新增Evidence Tool输入、统一结果和带公开file ID的文档详情；
   - `app/schemas/__init__.py`：导出新公共合同；
   - `app/tools/registry.py`：保持M1两Tool，隔离M2 Registry累计并精确登记五Tool；
   - `tests/unit/test_file_evidence_tool_contracts.py`：新增7项合同/Registry/停止边界测试；
   - `tests/unit/test_search_knowledge_contracts.py`：把M2 Registry期望推进为五Tool，同时继续禁止执行Service/Tool、Agent和API；
   - 本记录、M2入口和总看板：记录方案确认、TDD、验证、风险、Seed与下一停止点；
9. 完整调用链位置：本步实际只到`ReadUploadedFileInput/GetEvidenceDetailInput Schema → M2 Tool Registry元数据 → 对应输出Schema`。不经过前端、HTTP API、Harness执行、Tool执行、Service、Repository、Model、PostgreSQL业务读取、Storage、Agent/LangGraph、Qwen、Citation Validator实际调用或前端；
10. TDD RED证据：先新增合同测试并推进既有Registry断言，运行`.venv\Scripts\python.exe -m pytest -q tests\unit\test_file_evidence_tool_contracts.py tests\unit\test_search_knowledge_contracts.py`；收集阶段因`ImportError: cannot import name 'CsvFileReadLocator' from app.schemas`失败，退出码1，准确证明公共文件/Evidence Tool合同尚不存在；生产实现是在该RED之后才补充；
11. 最小GREEN：只实现合同、公共导出和Registry元数据后，同一聚焦集合为`28 passed in 0.82s`。首次质量检查Mypy已通过，但发现`app.schemas.__all__`排序及4个文件格式不符合Ruff；只做机械排序/格式化，不改变合同行为；
12. 相邻回归：新合同、M2-19知识合同、M1 Agent Tool合同、权限、Provider、Context和M2基线为`129 passed in 6.15s`；进一步加入M1库存图/Harness/权限与M2搜索Tool、KnowledgeSearchService、Evidence、Citation和0010关联后为`238 passed in 31.25s`；
13. 全量结果：排除显式`tests/smoke`真实模型测试和既有跨月用例后，`tests/unit + tests/integration`为`863 passed, 2 skipped, 1 deselected in 93.24s`；原样默认全量为`863 passed, 10 skipped, 1 failed in 91.55s`。唯一失败仍是`test_parse_failure_marks_first_index_failed_without_creating_index_set`固定删除`uploads/2026/08`，当前9月真实夹具Key未被删除，因而没有抛出预期解析错误；它与本步Schema/Registry没有调用关系，未越权修改；
14. 工程质量与迁移：正式新运行链范围`ruff check app tests scripts`通过，240个文件格式正确；Mypy为117个`app`源文件无问题；compileall、pip check和`git diff --check`通过。Alembic current/heads均为`20260902_0010 (head)`且`alembic check`无新升级操作，本步没有Model或迁移。额外对仓库根目录`.`运行Ruff会纳入保留的旧原型`agent/api/tools/utils`并暴露既有格式/旧规则问题；这些不由本步产生，也未越权批量改写；
15. 能证明的内容：能证明四格式调用者locator有固定小窗口、文件和Evidence输入不能夹带身份/路径/SQL/预算，文件输出有8000字符硬边界与自洽公开字段，Evidence详情联合合同只补安全file ID，M1 Registry仍精确两个且M2 Registry精确五个，新Tool元数据不会自动进入库存Agent；
16. 不能证明的内容：本步没有Repository、Service或执行Tool，不能证明真实owner/ACL/跨tenant/软删除/parse状态、Storage读取、Canonical Artifact定位、Evidence当前授权、Harness身份/预算/超时/Trace、Envelope运行结果、API、Agent、Qwen或前端；这些必须从M2-20.2开始逐步实现和验证；
17. 风险与排查顺序：合同导入失败先查`files输入模块 → file_reading输出模块 → retrieval依赖方向 → schemas公共导出`；locator误拒绝先查source type、二选一字段、页/行/单元格硬边界，不先放宽规则；Registry异常先查`ToolName → schema import → M1定义复用 → M2五定义`；模型看不到新Tool属于预期，因为本步没有修改Agent/Provider投影；
18. 正式数据与停止点：全量测试会修改共享测试/演示数据库，随后依次运行既有`python -m scripts.seed_m1 → seed_m2_files → seed_m2_complex_files`恢复。只读复核为10 files、10 documents、10 versions、9 ACL、10个parse/index pending、0 active Version、0 ChunkSet/IndexSet/Chunk、0 ContextArtifact/Evidence/ToolContextLink/AgentRun/ToolCall；Storage精确10个uploads、0 parsed、0 chunks，德国仓可售库存125。M2-20.1已完成，明确没有创建`app/services/file_reading.py`、`app/tools/read_uploaded_file.py`或`get_evidence_detail.py`，没有开始M2-20.2、API、Agent、Qwen或前端，必须等待用户单独确认。

## 3. 2026-09-02｜M2-20.2｜实现安全解析产物读取Service

**状态：已完成；已验证；明确停止在M2-20.2。**

本步输入是Harness未来提供的可信`CurrentUser`与M2-20.1已经冻结的`ReadUploadedFileInput`；输出是严格`ReadUploadedFileResult`。上游执行Tool/Harness接线尚未实现，下游是一次性获权Repository查询、PostgreSQL元数据和LocalStorage中的版本化解析JSON。本步不创建`ReadUploadedFileTool`，不生成Evidence，不经过API、Agent、Qwen或前端。

1. 本步解决的问题：M2-20.1只有“申请表”和Registry名册，系统还不能拿公开`file_id`重新检查当前用户权限，也不能安全打开私有解析产物、按四种格式定位并把内容裁成公开小窗口；如果直接让未来Tool接触Storage Key或整份JSON，会绕过Repository权限和输出上限；
2. 大白话运行过程：Service先拿当前登录人的可信身份去数据库问“这个文件现在还能不能看”，数据库在同一条查询里同时核对tenant、文件/文档软删除和owner/ACL。获权后，Service内部取得不对外公开的解析产物Key，确认它确实属于当前tenant的`parsed`目录和这个版本，再从LocalStorage最多读取100 MiB。JSON重新通过`RoutedParseResult`自校验，并核对格式、文件SHA和版本content hash；最后只取指定页、段、表、Sheet/单元格或行，最多返回12段和8000字符；
3. Repository与授权：新增不可变内部记录`ReadableParsedFile`和`find_readable_parsed_file`。查询从`StoredFile`一次join`DocumentVersion/Document`，复用`document_access_clause`，同时限制file ID、tenant、File/Document未软删除及owner/company owner/user/role/market ACL；返回版本号、格式、File SHA、Version content hash、parse状态、私有Key和是否active。无结果统一由Service映射为`FILE_NOT_FOUND`；
4. 状态与私有Key：只允许已获权且`parse_status=ready`、`parsed_storage_key`非空的具体关联版本；不要求该版本active，输出如实携带`is_active_version`。Key先通过既有`validate_storage_key`，再强制匹配当前tenant、`parsed`类别和`{version_id}.json`文件名，任何不一致只返回统一安全读取错误；
5. Artifact校验：Storage只读取`file_read_max_artifact_bytes + 1`字节，超限即拒绝；JSON必须重新形成合法`RoutedParseResult`，只使用`selected_artifact`，并要求Artifact `source_type`与文件扩展一致，`source_sha256`同时等于`StoredFile.sha256`和`DocumentVersion.content_hash`，不相信数据库Key、格式或任一单独hash；
6. 四格式确定性读取：PDF按1至3页筛选且保留真实页码；DOCX按一个明确block/paragraph/table定位；XLSX按Sheet加A1矩形或行窗口读取，行窗口也由Service按实际列数裁到最多1000单元格；CSV按最多50个物理行读取；省略locator时使用服务端预览策略，PDF最多3页、总体最多12段；表格转为带物理行号的确定性安全Markdown视图；
7. 输出与故障：所有section合计最多8000字符，超长时精确裁剪并设置section/result `truncated=true`；不存在的定位返回固定`VALIDATION_ERROR/locator`，未ready返回`FILE_STATE_CONFLICT`，数据库、Storage、超限、非法JSON、Artifact/Key/Hash不一致统一为不含路径、Key、SQL或底层异常的`FileReadError`；
8. 实际修改文件与职责：
   - `.env.example`、`app/core/config.py`：新增仅由服务端控制的100 MiB解析JSON读取硬上限；
   - `app/core/errors.py`：新增安全定位错误与统一解析产物读取错误；
   - `app/repositories/files.py`：新增内部获权记录和一次性File/Version/Document查询；
   - `app/repositories/__init__.py`：导出Repository内部公共记录；
   - `app/services/file_reading.py`：实现获权、Key/JSON/Hash复核、四格式选择、表格渲染和全局裁剪；
   - `app/services/__init__.py`：导出`FileReadingService/ParsedFileReader`，没有导出执行Tool；
   - `tests/unit/test_file_reading_service.py`：Fake Repository/Storage覆盖四格式、可信身份参数、非active、预览/裁剪、状态、Key/JSON/Hash/数据库/Storage故障与脱敏；
   - `tests/integration/test_file_reading_service.py`：真实PostgreSQL与临时LocalStorage覆盖owner、user ACL、跨tenant、撤权、Document软删除、pending状态和非active ready版本；
   - `tests/unit/test_file_evidence_tool_contracts.py`、`test_m2_baseline.py`：把停止线推进到Service存在/执行Tool不存在，并锁定服务端配置；
9. 完整调用链位置：`CurrentUser + ReadUploadedFileInput Schema → FileReadingService → FileRepository → StoredFile/DocumentVersion/Document Model → PostgreSQL → private parsed_storage_key → Storage.open → RoutedParseResult → selected CanonicalParsedArtifact → ReadUploadedFileResult Schema`。本步不经过前端、HTTP API、M2 Registry实际执行、Harness、Tool执行类、Evidence/Citation Validator、Agent/LangGraph、Qwen或最终回答；
10. TDD RED证据：生产实现前新增`tests/unit/test_file_reading_service.py`并运行；收集阶段因`ImportError: cannot import name 'FileReadError' from app.core.errors`失败，退出码1，准确证明安全错误、Repository内部记录和File Reading Service均不存在；生产代码在该RED后才加入；
11. 最小GREEN与中间修正：首次实现后同一测试为`13 passed`；补充双重hash、私有Key形状、精确8000字符裁剪和数据库故障脱敏后，最终单元Service为`16 passed`。真实集成业务断言首次全部通过，但teardown先删tenant触发DocumentVersion/File外键错误；仅按`ACL → Version → Document → File → User → Tenant`修正测试清理顺序，并精确清除该次遗留的3个测试tenant，随后真实集成为`3 passed`；
12. 聚焦与相邻回归：最终Service/真实Repository+Storage/合同/配置聚焦为`75 passed in 2.70s`；文件/Storage/Artifact/知识Schema/权限/Parser Service与M2-19 SearchKnowledge相邻集合为`226 passed in 15.09s`；
13. 独立旧File API夹具现象：人为只组合部分相邻测试时得到`224 passed, 6 errors`，6项都发生在`test_file_api.py`模块setup直接`DELETE FROM files`，正式Seed的DocumentVersion外键阻止删除；没有本步业务断言失败。相同File API在正式全量顺序中通过，说明这是既有测试顺序/清理前置耦合，不修改生产规则，也未越权重写旧夹具；
14. 全量结果：正斜杠节点正确排除既有跨月用例后为`882 passed, 2 skipped, 1 deselected in 69.25s`；原样默认全量为`882 passed, 10 skipped, 1 failed in 81.08s`。唯一失败仍是`test_parse_failure_marks_first_index_failed_without_creating_index_set`固定删除`uploads/2026/08`，当前9月夹具真实Key没有被删，因而未抛预期解析错误；它与本步读取Service无调用关系，未越权修改；
15. 工程质量与迁移：`ruff check app tests scripts`通过，243个文件格式正确；Mypy为118个`app`源文件无问题；compileall、pip check和`git diff --check`通过；Alembic current/heads均为`20260902_0010 (head)`且`alembic check`无新升级操作，本步没有Model或迁移；
16. 能证明的内容：可信身份被转换为固定Repository参数；真实owner/user ACL、跨tenant、撤权、Document软删除和未ready边界生效；获权非active ready版本可以安全读取并明确标记；四格式locator、默认预览、100 MiB加载上限、8000字符输出、Key/Routed/Canonical/双重hash验证和常见故障脱敏可重复；私有tenant/Key/路径/SQL不进入公开结果；
17. 不能证明的内容：本步没有执行Tool，不能证明M2 Registry投影、Harness角色/预算/超时/Trace或Envelope；完整company owner/role/market ACL、File自身软删除、更多locator越界和故障矩阵留到M2-20.6；当前仍是有界加载整份JSON后定位，不证明超大文件流式随机访问或高并发性能；没有创建Evidence，因此M2-21不能把文件读取正文当成无引用最终事实；也没有证明Evidence详情、API、Agent、Qwen或前端；
18. 风险与排查顺序：404先查`CurrentUser/tenant → File/Document软删除 → owner/ACL`；状态冲突查具体Version `parse_status/parsed_storage_key`；定位错误查文件类型、页/段/表/Sheet/行列及Canonical真实坐标，不先放宽Schema；统一读取错误依次查100 MiB上限、Key tenant/category/version、Storage对象、Routed合同、source type和File/Version双hash；表格被裁剪先查50行/1000单元格/8000字符边界；
19. 正式数据与停止点：全量后再次执行既有三个Seed入口恢复。最终只读复核为10 files、10 documents、10 versions、9 ACL、10个parse/index pending、0 active Version、0 ChunkSet/IndexSet/Chunk、0 ContextArtifact/Evidence/ToolContextLink/AgentRun/ToolCall、0个M2-20.2测试tenant；Storage精确10个uploads、0 parsed、0 chunks，德国仓关键SKU可售125，Alembic仍为0010 head。M2-20.2已完成，明确没有创建`app/tools/read_uploaded_file.py`或`get_evidence_detail.py`，没有接入Harness、API、Agent、Qwen或前端，也没有开始M2-20.3；必须等待用户单独确认。

## 4. 2026-09-02｜M2-20.3｜实现`ReadUploadedFileTool`并接入Harness

**状态：已完成；已验证；明确停止在M2-20.3。**

本步输入是模型按M2-20.1合同构造的公开`ReadUploadedFileInput`，以及应用绑定的可信`CurrentUser`和Harness生成的`ToolExecutionContext`；输出是`ToolEnvelope[ReadUploadedFileResult]`，成功时`evidence_ids`固定为空。上游是隔离M2 Registry、Harness权限/预算/超时/Trace，下游复用M2-20.2 `FileReadingService`。本步不实现Evidence详情Service/Tool，不修改API、Agent、Qwen或前端。

1. 本步解决的问题：M2-20.2虽然能安全读取文件，但还只能由Python代码直接调用Service；模型未来发起的文件读取尚未经过M2 Registry白名单、可信运行身份、角色权限、次数预算、3秒Tool超时和持久化Trace，也没有统一安全Envelope；
2. 大白话运行过程：Agent以后只提交“公开文件ID和想看的一小段”。Harness先检查这个Tool是否在M2名册、当前角色是否允许、调用次数是否超限，并先写一条审计记录；Tool再逐项比对“应用登录人”和“Harness运行人”是不是同一个用户、tenant、角色和市场，完全一致才把原申请交给File Reading Service。Service重新查数据库权限并安全读取解析产物；结果返回时Tool还会核对Service给回来的确实是严格结果且`file_id`没有串线，然后包成统一Envelope。任何已知业务错误按公开错误返回，未知异常由Harness脱敏；
3. 执行适配器：新增`ReadUploadedFileTool`，构造时从实际Harness取得`read_uploaded_file`定义，并用`validate_tool_binding`精确校验名称、输入Schema和输出Schema，避免执行代码与Registry元数据漂移；`invoke`只通过`HarnessExecutor.execute_tool`调用下游，目标tenant固定取自Harness，不接受模型传tenant；
4. 身份与结果防线：Tool执行回调逐项核对`CurrentUser.user_id/tenant_id/roles/market_scopes`和`ToolExecutionContext`；不一致时在Service前失败。Service结果必须是`ReadUploadedFileResult`且返回`file_id`等于请求的公开`file_id`，否则视为不可信内部结果并由Harness统一转为不泄露细节的`INTERNAL_ERROR`；
5. Envelope与Evidence边界：成功结果保留Registry版本、Trace ID、耗时和合成数据标志，直接包装有界文件结果；没有创建或伪造Evidence，`evidence_ids`始终为空。已知`ApplicationError`保留公开code/field/retryable，未知错误、私有Storage Key和SQL细节不进入Envelope；
6. Trace与预算：真实Harness测试证明公开`file_id/locator`进入有界`arguments_summary`，tenant和Storage信息不进入参数审计；无角色调用在Service前以denied记录；相同参数第二次调用受既有重复预算阻断；回调超过Registry的3000ms后返回`BUDGET_EXCEEDED`并把ToolCall记为timeout；locator业务错误记为error；本步没有修改任何全局预算；
7. 公共导出：`app/tools/__init__.py`继续使用惰性导出以避免运行时循环导入，新增`ReadUploadedFileTool`公共入口；M1 Registry仍精确两个、隔离M2 Registry仍精确五个，未创建`GetEvidenceDetailTool`；
8. 测试边界推进：新增Tool单元与真实PostgreSQL Trace集成测试；原M2-20.2停止哨兵推进为“只允许文件执行Tool存在”，同时继续断言`app/tools/get_evidence_detail.py`、知识Agent/API不存在，库存图不包含两个M2读取Tool；M2-19停止哨兵同步到当前真实边界；
9. 实际修改文件与职责：
   - `app/tools/read_uploaded_file.py`：可信身份绑定、精确Registry合同校验、Harness执行、Service结果验真和安全Envelope；
   - `app/tools/__init__.py`：惰性公开导出`ReadUploadedFileTool`；
   - `tests/unit/test_read_uploaded_file_tool.py`：覆盖Registry漂移、成功Envelope/空Evidence、四类身份错配、已知/未知错误、错误结果类型和file ID串线；
   - `tests/integration/test_read_uploaded_file_tool.py`：使用真实PostgreSQL Trace与Harness覆盖成功审计、角色拒绝、身份错配、重复预算、3000ms超时和业务错误状态；
   - `tests/unit/test_file_evidence_tool_contracts.py`、`tests/unit/test_search_knowledge_contracts.py`：推进停止边界，继续阻止Evidence执行Tool、Agent和API提前出现；
   - 本记录、M2入口与总看板：同步完成状态、验证基线、有效决策和下一动作；
10. 完整调用链位置：本步接通`ReadUploadedFileInput Schema → M2 Registry → Harness权限/预算/超时/Trace → ReadUploadedFileTool → FileReadingService → File/Document Repository → PostgreSQL + LocalStorage → ReadUploadedFileResult → ToolEnvelope`。不经过前端、HTTP知识API、知识Agent/LangGraph、Qwen、Citation Validator调用或最终回答生成；
11. TDD RED证据：生产实现前新增两类Tool测试并推进停止哨兵，实际运行聚焦集合；收集阶段同时得到`ImportError: cannot import name 'ReadUploadedFileTool' from 'app.tools'`与`ModuleNotFoundError: No module named 'app.tools.read_uploaded_file'`，共2个收集错误、退出码1，准确证明执行模块和公共入口均不存在；生产代码在该RED之后才加入；
12. 最小GREEN与测试夹具校正：首次实现后为`42 passed, 1 failed`，失败是超时测试让请求与Fake结果使用不同file ID，新的防串线校验先正确返回`INTERNAL_ERROR`；统一测试file ID后超时断言通过，但同一测试又复用了唯一Trace ID，数据库按设计拒绝第二个AgentRun。只把两个审计行为拆成独立测试，没有放宽生产规则；最终聚焦为`44 passed in 3.62s`，格式化后复跑仍为`44 passed`；
13. 相邻回归：文件Tool、M2-20.2 Service/真实Repository+Storage、M2-19 SearchKnowledgeTool、M1 Tool合同/真实Tool、权限、Provider、Context与Harness Trace共`208 passed in 18.44s`；说明新增惰性导出和M2执行Tool没有污染M1两Tool与既有知识搜索链；
14. 全量结果：只运行`tests/unit + tests/integration`并精确排除既有跨月用例后为`898 passed, 2 skipped, 1 deselected in 69.11s`；原样默认全量为`898 passed, 10 skipped, 1 failed in 71.87s`。唯一失败仍是`test_parse_failure_marks_first_index_failed_without_creating_index_set`把删除Key固定为`uploads/2026/08`，当前9月夹具使用`2026/09`，因而没有抛预期解析错误；它与本步Tool/Harness链无调用关系，未越权修改；
15. 工程质量与迁移：`ruff check app tests scripts`通过，246个文件格式正确；Mypy为119个`app`源文件无问题；compileall、pip check和`git diff --check`通过。Alembic current/heads均为`20260902_0010 (head)`，`alembic check`无新升级操作；本步没有Model或迁移；
16. 能证明的内容：能证明执行类只能绑定M2 Registry的精确合同，模型参数经过Harness且目标tenant来自可信上下文，绑定身份不一致时Service不会运行，角色、重复预算、3000ms超时和ToolCall状态可持久化，公开成功结果与请求file ID一致且不伪造Evidence，已知/未知故障使用安全Envelope；结合M2-20.2相邻回归，还能证明下游真实获权Repository和LocalStorage读取没有被本步破坏；
17. 不能证明的内容：本步没有实施M2-20.6完整三角色、owner/company owner、role/market ACL、File软删除、全部locator与故障矩阵；Tool/Harness集成使用确定性Fake Service，而真实PostgreSQL/LocalStorage Service由独立相邻集成测试证明，尚未形成同一测试中的全链真实调用；也不能证明Evidence详情重取、`search → detail → read`三跳预算、HTTP、Agent/LangGraph、Qwen、Citation Validator实际调用、最终回答引用或前端；文件读取仍不创建Evidence，因此不能作为无引用最终事实旁路；
18. 风险与排查顺序：构造失败先查是否注入M2 Registry以及名称/输入/输出Schema是否一致；调用被拒先查RunContext角色与预算，再查绑定CurrentUser四项身份；`INTERNAL_ERROR`先查Service返回类型和file ID是否串线，再按M2-20.2顺序查Repository、Storage Key、Routed/Canonical Artifact与Hash；timeout先查3000ms Registry预算和Service读取耗时，不修改全局Tool次数；Trace写入失败查唯一trace ID、Thread/User/Tenant复合身份和数据库连接；
19. 正式数据与停止点：两种全量测试会修改共享测试/演示数据库，随后已依次运行`python -m scripts.seed_m1`、`seed_m2_files`、`seed_m2_complex_files`恢复。只读复核为10 files、10 documents、10 versions、9 ACL、10个parse/index pending、0 ChunkSet/IndexSet/Chunk、0 ContextArtifact/Evidence/ToolContextLink/AgentRun/ToolCall、0个M2-20测试tenant；Storage为10 uploads、0 parsed、0 chunks，德国仓关键SKU可售125。M2-20.3已完成，明确没有创建Evidence详情Service或`GetEvidenceDetailTool`，没有修改API、Agent、Qwen或前端，也没有开始M2-20.4；必须等待用户单独确认。

## 5. 2026-09-02｜M2-20.4｜扩展统一Evidence详情Service

**状态：已完成；已验证；明确停止在M2-20.4。**

本步输入是可信`CurrentUser`与只含`evidence_id`的`GetEvidenceDetailInput`；输出是`GetEvidenceDetailResult`，其中detail可以是既有M1数据库Evidence或新增带公开`file_id`的M2文档Evidence。上游未来是`GetEvidenceDetailTool`，本步尚未创建；下游是Evidence Repository、共享active Chunk获权边界和PostgreSQL。本步不接Harness、API、Agent、Qwen或前端。

1. 本步解决的问题：M2文档Evidence虽然已经持久化并可被Citation Validator按Context整体验证，但现有`EvidenceQueryService.get_detail()`只会构造M1库存数据库Evidence，无法凭单个Evidence ID重新核对Context请求者、当前ACL、软删除和active代次，也无法返回M2-20.1冻结的统一Tool详情；
2. 大白话运行过程：系统先按当前tenant找到Evidence卡，确认它属于数据库证据还是文档证据。数据库卡继续走原来的M1市场权限检查；文档卡则不能只看“当时保存时合法”，必须重新去数据库验票：这张卡是不是当前登录人请求的Context、文档和文件现在是否还活着、当前用户现在是否仍有ACL、Version和Index Set是否仍为active ready、卡上记录的Chunk整组身份和正文Hash是否仍与当前成品一致。全部通过才组装公开详情，任何不可见或过期状态统一返回`EVIDENCE_NOT_FOUND`；
3. M1兼容边界：保留`EvidenceQueryService.get_detail(user, evidence_id) -> EvidenceDetail`作为既有M1 HTTP专用入口，并明确只接受`source_type=database`；`get_summaries`继续复用该入口。即使调用者猜到M2文档Evidence ID，现有`/api/v1/evidence/{id}`也只得到404，不会被本步悄悄扩展为联合HTTP API；
4. 新统一Service入口：新增`get_tool_detail(user, GetEvidenceDetailInput) -> GetEvidenceDetailResult`供M2-20.5未来Tool调用。数据库分支复用同一M1构造和tenant/market检查；knowledge/user_file分支调用新的当前授权Repository查询，再构造`ToolDocumentEvidenceDetail`；本步没有让模型或API直接调用这个方法；
5. 当前请求者边界：文档Evidence必须连接真实`ContextArtifact`，且`requested_by_user_id`精确等于当前登录用户；即使同tenant的company owner现在能读取底层文档，也不能展开另一位用户请求产生的Context Evidence。跨tenant、跨用户、记录不存在和当前不可见统一为同一个`EvidenceNotFoundError`；
6. 当前ACL与代次边界：Repository复用`RetrievalRepository.authorized_active_chunks_statement(CurrentUser)`，因此owner/company owner/user/role/market ACL、Document/File软删除、active Version、`parse_status/index_status=ready`、active ready Index Set在读取详情时重新生效；不是只相信Evidence行的历史快照；
7. 完整来源身份：Evidence必须同时匹配当前Chunk的tenant、Document、Version、Chunk Set、Index Set和Chunk UUID，`file_id`必须匹配当前Version；schema version、source type/name、trust level和Context合同版本必须正确，citation ordinal不能超过Context片段数，`source_content_sha256`必须等于当前Chunk正文Hash，Evidence标题也必须仍与Document标题一致；任一错位都隐藏为未找到；
8. 公开详情构造：Repository只返回不含tenant、owner、ACL、Storage Key、路径或SQL的不可变`AuthorizedDocumentEvidence`；Service从已验证事实构造公开file ID、Context ID、`[E#]`、四重检索身份、文档公开元数据、四格式locator、两个Hash和snapshot信任标记，再由严格Pydantic合同进行最后校验；坏locator或不完整公开事实统一转为不泄露底层内容的`EvidenceReadError`；
9. 故障边界：初次tenant查询或文档获权查询发生SQLAlchemy异常时，统一返回固定`INTERNAL_ERROR/证据数据读取失败`；底层密码、SQL和表名不进入公开错误。不存在、跨tenant/用户、撤权、软删除和过期代次使用`EVIDENCE_NOT_FOUND`，避免通过错误差异探测资源是否存在；
10. 实际修改文件与职责：
   - `app/repositories/evidence.py`：新增公开安全内部记录和单个文档Evidence当前获权/active/完整来源查询；
   - `app/repositories/__init__.py`：从Repository受控入口导出新记录；
   - `app/services/evidence.py`：保留M1详情行为，新增统一Tool专用详情入口、两分支构造、权限隐藏和错误脱敏；
   - `tests/unit/test_evidence_detail_service.py`：Fake Repository覆盖M1兼容、数据库/文档联合结果、M1 HTTP隐藏文档Evidence、无结果/未授权、坏公开事实和数据库错误脱敏；
   - `tests/integration/test_evidence_detail_service.py`：真实PostgreSQL覆盖成功详情、跨请求者/tenant、ACL撤销、Document/File软删除、inactive Version/Index Set和来源Hash错位；
   - `tests/unit/test_file_evidence_tool_contracts.py`：把停止哨兵推进到Evidence Service存在但`GetEvidenceDetailTool`、Agent和API仍不存在；
   - 本记录、M2入口和总看板：同步步骤状态、有效决策、验证基线与下一动作；
11. 完整调用链位置：本步接通`CurrentUser + GetEvidenceDetailInput Schema → EvidenceQueryService.get_tool_detail → EvidenceRepository → ContextArtifact/Evidence + 当前Document/File/Version/IndexSet/Chunk → PostgreSQL → ToolDocumentEvidenceDetail/EvidenceDetail → GetEvidenceDetailResult`。不经过前端、HTTP知识API、M2 Registry实际执行、Harness、`GetEvidenceDetailTool`、Agent/LangGraph、Qwen、Storage读取、Citation Validator调用或最终回答；
12. TDD RED证据：生产实现前新增单元/真实PostgreSQL测试并推进停止哨兵，实际运行聚焦集合；测试收集阶段因`ImportError: cannot import name 'AuthorizedDocumentEvidence' from app.repositories.evidence`失败、退出码1，准确证明当前获权文档Evidence读取记录和统一Service入口不存在；生产代码在该RED之后才加入；
13. 最小GREEN与补强：首个最小实现后聚焦为`23 passed in 4.38s`；Ruff只发现一个SQL连接实体的Python解包变量未使用，Mypy只发现联合detail局部变量被推断为M1单类型，只补下划线变量与显式联合注解，不改变业务。随后补充真实ACL撤销测试，最终聚焦为`24 passed in 4.50s`；
14. 相邻回归：Evidence详情、M1 Schema/API、Context、Knowledge Evidence持久化、Citation Validator、KnowledgeSearchService/SearchKnowledgeTool、File Reading Service/Tool及M1 Agent Tool共`156 passed in 24.46s`；说明M1数据库Evidence详情与HTTP行为、M2 Context/Evidence写入和引用校验均未被联合Service破坏；
15. 全量结果：只运行`tests/unit + tests/integration`并精确排除既有跨月用例后为`915 passed, 2 skipped, 1 deselected in 98.01s`；原样默认全量为`915 passed, 10 skipped, 1 failed in 99.02s`。唯一失败仍是`test_parse_failure_marks_first_index_failed_without_creating_index_set`固定删除`uploads/2026/08`，当前9月夹具使用另一Key，因而没有抛预期解析错误；它与本步Evidence详情查询无调用关系，未越权修改；
16. 工程质量与迁移：`ruff check app tests scripts`通过，248个文件格式正确；Mypy为119个`app`源文件无问题；compileall、pip check和`git diff --check`通过。Alembic current/heads均为`20260902_0010 (head)`且`alembic check`无新升级操作；本步复用现有表和约束，没有Model或迁移；
17. 能证明的内容：能证明M1详情/API继续只返回数据库Evidence，新的统一Service可以安全返回M1或M2严格详情；M2详情要求原Context请求者、当前tenant/ACL、Document/File存活、active ready Version/Index Set和完整Chunk来源/Hash同时成立；ACL撤销或代次切换后旧Evidence不可见；返回不包含tenant、owner、ACL、Storage Key、路径或SQL；数据库和合同异常被脱敏；
18. 不能证明的内容：本步没有`GetEvidenceDetailTool`，不能证明M2 Registry绑定、Harness角色/预算/超时/Trace、ToolEnvelope携带请求Evidence ID或模型实际调用；完整owner/company owner/role/market ACL和更多字段篡改矩阵留到M2-20.6；`context_text_sha256`因数据库未持久化完整Context正文只能通过合同格式和既有持久化链信任，当前无法在详情读取时重新计算；也不能证明HTTP知识API、Agent/LangGraph、Qwen回答、Citation Validator与Tool联动或前端；
19. 风险与排查顺序：统一404先查`tenant Evidence行 → source_type → Context requested_by_user_id → 当前owner/ACL → Document/File软删除 → active Version → active Index Set → 完整Chunk/Hash`，不能把具体失败原因返回调用者；`INTERNAL_ERROR`先查数据库异常，再查locator、citation ordinal和公开Schema构造；M1详情异常先确认是否误把文档Evidence送入旧HTTP入口以及access_scope市场是否仍在用户范围；查询性能先确认复用了单条active Chunk获权SQL，没有循环查ACL；
20. 正式数据与停止点：两种全量测试会修改共享测试/演示数据库，随后已依次运行`python -m scripts.seed_m1`、`seed_m2_files`、`seed_m2_complex_files`恢复。只读复核为10 files、10 documents、10 versions、9 ACL、10个parse/index pending、0 ChunkSet/IndexSet/Chunk、0 ContextArtifact/Evidence/ToolContextLink/AgentRun/ToolCall、0个M2-20/retrieval测试tenant；Storage为10 uploads、0 parsed、0 chunks，德国仓关键SKU可售125。M2-20.4已完成，明确没有创建`app/tools/get_evidence_detail.py`，没有接入Harness、API、Agent、Qwen或前端，也没有开始M2-20.5；必须等待用户单独确认。

## 6. 2026-09-02｜M2-20.5｜实现`GetEvidenceDetailTool`并接入Harness

**状态：已完成；已验证；明确停止在M2-20.5。**

本步输入是模型只能填写的`GetEvidenceDetailInput(evidence_id)`与运行时绑定的可信`CurrentUser`；输出是`ToolEnvelope[GetEvidenceDetailResult]`，成功时只携带Service已经重新验证的同一个Evidence ID。上游当前只有M2 Registry与Harness，知识Agent/API尚不存在；下游复用M2-20.4的`EvidenceQueryService → EvidenceRepository → PostgreSQL`。本步不实施M2-20.6矩阵，不修改API、Agent、LangGraph、Qwen或前端。

1. 本步解决的问题：M2-20.4已经能按当前身份安全读取数据库或文档Evidence，但尚无正式Agent Tool适配器，模型调用还不能经过M2 Registry白名单、Harness角色/预算/超时/Trace，也没有统一的安全Envelope；
2. 大白话运行过程：模型只交一张写着Evidence UUID的小票。Harness先检查这个Tool是否在M2名册、当前角色是否允许、次数和3000ms时间是否超限，并保存调用轨迹；Tool再核对构造时绑定的用户、tenant、角色和市场与Harness可信上下文完全一致，随后把同一用户和小票交给Evidence Service重新验权。Service返回的详情类型和Evidence ID必须与小票一致，才能把该ID放入成功Envelope；任何已知或未知失败都只返回安全错误，不带Evidence ID；
3. 精确Registry绑定：`GetEvidenceDetailTool`构造时从注入的Harness读取`get_evidence_detail@1.0.0`定义，并用`validate_tool_binding`核对名称、`GetEvidenceDetailInput`和`GetEvidenceDetailResult`；误接M1 Registry或Schema漂移会在执行前失败，不会静默调用错误Service；
4. 可信身份边界：Tool逐项核对`CurrentUser.user_id/tenant_id/roles/market_scopes`与`ToolExecutionContext`，目标tenant只取Harness可信tenant，不接受模型或绑定对象自行改写；任一错位都在Service前返回安全`FORBIDDEN`；
5. 结果与Evidence边界：Tool只调用`EvidenceQueryService.get_tool_detail`，并要求返回严格`GetEvidenceDetailResult`且`result.evidence_id == request.evidence_id`；成功Envelope的`evidence_ids`精确为这一项，避免Service串线或Tool伪造另一张证据；错误Envelope始终为空列表；
6. Harness运行边界：继续复用现有M2 Registry的三业务角色、`data_scope=tenant`、`side_effect=read`和3000ms单Tool超时；重复相同调用会命中现有每运行重复预算，角色拒绝发生在Service之前，允许、拒绝、错误和超时状态均持久化到真实PostgreSQL Trace；本步没有修改全局最多两个Tool调用的预算；
7. 故障脱敏：`EvidenceNotFoundError`保留公开`EVIDENCE_NOT_FOUND/evidence_id`合同；身份错误、预算和超时走既有安全错误；Service返回错误类型、错Evidence ID或抛含路径/SQL的未知异常会被Harness转换为`INTERNAL_ERROR`，私有内容不进入Envelope；
8. 实际修改文件与职责：
   - `app/tools/get_evidence_detail.py`：新增精确绑定、可信身份核对、Harness执行、Service结果验真和安全Envelope的正式Tool适配器；
   - `app/tools/__init__.py`：惰性导出`GetEvidenceDetailTool`，保持运行时循环导入边界；
   - `tests/unit/test_get_evidence_detail_tool.py`：使用Fake Harness/Service覆盖合同绑定、成功Evidence ID、已知错误、四类身份错位、坏结果、ID串线和未知故障脱敏；
   - `tests/integration/test_get_evidence_detail_tool.py`：使用真实Harness与PostgreSQL Trace、确定性Fake Service覆盖成功审计、角色拒绝、身份错位、重复预算、3000ms超时和已知Evidence错误；
   - `tests/unit/test_file_evidence_tool_contracts.py`、`tests/unit/test_search_knowledge_contracts.py`：把停止哨兵推进为两个M2读取执行Tool均存在，同时继续禁止知识Agent和API；
   - 本记录、M2入口和总看板：同步步骤状态、验证基线、风险和下一停止点；
9. 完整调用链位置：本步接通`GetEvidenceDetailInput Schema → M2 Registry → Harness权限/预算/超时/Trace → GetEvidenceDetailTool可信身份与结果验真 → EvidenceQueryService → EvidenceRepository → PostgreSQL → GetEvidenceDetailResult → ToolEnvelope`。不经过前端、HTTP知识API、知识Agent/LangGraph、Qwen、Storage、文件读取Tool、Citation Validator实际调用或最终回答；
10. TDD RED证据：生产实现前先新增Tool单元/集成测试并推进两个停止哨兵，实际运行聚焦集合；测试收集阶段分别因`ImportError: cannot import name 'GetEvidenceDetailTool' from 'app.tools'`与`ModuleNotFoundError: No module named 'app.tools.get_evidence_detail'`失败，退出码1，准确证明公共执行入口和Tool模块尚不存在；生产代码在该RED后才加入；
11. 最小GREEN：只新增一个薄Tool适配器和惰性公共导出后，原聚焦集合为`44 passed in 3.68s`；其中新增16个单元/真实Harness行为用例，既有合同与Registry停止边界同时通过；
12. 相邻回归：新Tool、M2-20合同、统一Evidence Service、文件读取Service/Tool、KnowledgeSearchService/SearchKnowledgeTool、Knowledge Evidence、Citation Validator、Context、M1 Agent Tool/Harness与库存Evidence共`212 passed in 33.80s`；说明M1数据库Evidence、M2当前授权详情、文件读取和知识检索链没有被新适配器破坏；
13. 全量结果：精确排除既有跨月用例后，`tests/unit + tests/integration`为`931 passed, 2 skipped, 1 deselected in 92.99s`；原样默认全量为`931 passed, 10 skipped, 1 failed in 76.98s`。唯一失败仍是`test_parse_failure_marks_first_index_failed_without_creating_index_set`写死删除`uploads/2026/08`，而当前9月夹具使用不同Key，因而没有抛出预期解析错误；它与本步Tool/Harness/Evidence调用链无关，未越权修改；
14. 工程质量与迁移：`ruff check app tests scripts`通过，251个文件格式正确；Mypy为120个`app`源文件无问题；compileall、pip check和`git diff --check`通过，后者仅输出既有LF/CRLF提示。Alembic current/heads均为`20260902_0010 (head)`，`alembic check`无新升级操作；本步没有Model或迁移；
15. 能证明的内容：能证明Tool只能绑定M2精确合同，模型只能提交Evidence ID，Harness在Service前执行角色/重复预算并记录Trace，绑定身份四项必须精确一致，3000ms超时被安全记录，成功结果与请求ID一致且Envelope只带该证据，已知/未知错误不泄露私有路径或SQL；结合M2-20.4相邻回归，还能证明Service会重新检查数据库市场权限或文档当前请求者、ACL、软删除、active代次和完整来源；
16. 不能证明的内容：本步真实Harness集成测试使用确定性Fake Evidence Service，真实PostgreSQL Evidence重新获权由M2-20.4独立集成测试证明，尚未在同一测试中形成`Tool → Harness → 真实Service/Repository`完整权限矩阵；三角色、owner/company owner、user/role/market ACL、撤权、软删除、旧代次与数据库故障的整链组合留到M2-20.6；也不能证明三跳预算、HTTP、Agent/LangGraph、Qwen回答、Citation Validator与Tool联动或前端；
17. 风险与排查顺序：Tool构造失败先查是否注入M2 Registry以及名称/输入/输出Schema；调用被拒先查RunContext角色和重复/总预算，再查绑定CurrentUser四项身份；`EVIDENCE_NOT_FOUND`按M2-20.4顺序查tenant Evidence行、source type、Context请求者、当前ACL/软删除/active代次和Chunk来源，不向调用者暴露具体原因；`INTERNAL_ERROR`先查Service返回类型与Evidence ID是否串线，再查数据库或公开Schema；timeout先查3000ms定义与查询耗时，不修改全局预算；
18. 正式数据与停止点：两种全量测试修改了共享测试/演示数据库，随后已依次运行`python -m scripts.seed_m1`、`seed_m2_files`、`seed_m2_complex_files`恢复。只读复核为1个正式tenant、10 files、10 documents、10 versions、9 ACL、10个parse/index pending、0 active Version、0 ChunkSet/IndexSet/Chunk、0 ContextArtifact/Evidence/ToolContextLink/AgentRun/ToolCall；Storage精确10 uploads、0 parsed、0 chunks，德国仓关键SKU可售125。M2-20.5已完成，明确没有开始M2-20.6，没有修改API、Agent、LangGraph、Qwen或前端；必须等待用户单独确认。

## 7. 2026-09-02｜M2-20.6｜权限、范围、故障矩阵与M2-20收口

**状态：已完成；已验证；M2-20整体已完成。**

本步输入仍是两个已冻结的公开申请：`ReadUploadedFileInput(file_id, locator?)`和`GetEvidenceDetailInput(evidence_id)`；输出仍是各自严格结果的安全`ToolEnvelope`。本步把真实M2 Registry、Harness、PostgreSQL Trace、两个正式Tool、真实Service/Repository、临时LocalStorage和合成文档/Evidence放进同一条验收链，不新增业务功能。M2-21知识路由、LangGraph、Qwen、API和前端均不在本步范围。

1. 本步解决的问题：M2-20.1至M2-20.5分别证明了合同、Service和Tool单点行为，但真实Tool/Harness测试仍使用Fake Service，真实Service测试又没有经过Harness；因此此前不能证明“同一次真实运行中，两种读取都穿过权限、预算、Trace并落到真实Repository/Storage/PostgreSQL”这一整链组合；
2. 大白话运行过程：测试先生成一份明确标注为合成数据的PDF、已发布解析产物、active索引Chunk、Context和Evidence，再用真实登录用户与Harness发起“读文件”和“展开证据”。每组测试只改变一张门票或一个资源状态，例如换角色、改ACL、撤权、软删除、切走active代次、破坏Storage或让数据库抛错，然后同时检查公开Envelope和数据库Trace是否都给出预期且不泄密；
3. 三角色与五种授权路径：同一真实双Tool调用分别验证`product_scout`作为文档owner、`company_owner`无ACL读取、`amazon_operator` user ACL、`amazon_operator` role ACL和`product_scout` market ACL；两次Tool调用在同一个AgentRun中均为`allowed/success`，文件Envelope保持空Evidence，详情Envelope只携带已验证Evidence ID；
4. 撤权与当前状态：Evidence创建后删除user ACL，文件读取统一为`FILE_NOT_FOUND`、Evidence详情统一为`EVIDENCE_NOT_FOUND`；Document或File软删除时两条链均隐藏；active Version或active Index Set切走时，指定公开file ID的已解析版本仍按既定决策允许读取并明确非active，而依赖当前active来源的旧Evidence立即隐藏；
5. 请求者、tenant和来源边界：同tenant内把Context请求者改成另一用户后，即使当前用户是company owner也不能展开旧Evidence；结合既有真实Service相邻测试，跨tenant资源、跨Context请求者、来源Hash错位、旧Version/Index、当前ACL撤销均继续统一隐藏，不能用错误差异探测资源；
6. 解析与locator范围：`parse_status=pending/failed`通过真实Tool返回`FILE_STATE_CONFLICT`且不生成Evidence；请求不存在的PDF第999页返回`VALIDATION_ERROR/locator`且不暴露Storage Key。M2-20.1合同测试继续锁定PDF最多3页、表格最多50行/1000单元格，M2-20.2 Service测试继续锁定最多8000字符和裁剪标志；
7. Storage、Artifact与数据库故障：删除解析对象或写入包含私有路径/SQL字样的损坏JSON，真实Service/Tool/Harness统一返回`INTERNAL_ERROR`，Envelope与Trace均不含Key、路径或SQL；File与Evidence Repository分别注入`SQLAlchemyError`时，仍由真实Service、Tool和Trace三层脱敏为固定内部错误；
8. Harness累计边界：本步同一次运行真实调用两个不同Tool，证明当前`max_tool_calls=2`足够支撑`detail + read`；M2-20.3/M2-20.5既有相邻测试继续证明三业务角色元数据、角色拒绝、相同参数重复预算、3000ms单Tool超时、身份四项错位和Trace状态。`search → detail → read`三跳仍超过当前预算，继续留给M2-21方案决定，本步没有修改全局预算；
9. 实际修改文件与职责：
   - `tests/integration/m2_20_matrix_support.py`：新增只用于测试的真实整链夹具，生成回滚式合成文档/索引/Context/Evidence和临时Storage，复用正式Registry、Harness、Tool、Service与Repository；
   - `tests/integration/test_file_evidence_tool_matrix.py`：新增18项角色/ACL、撤权、状态、范围、Storage/Artifact、数据库和请求者整链验收；
   - 没有修改任何`app/`生产文件、Schema、Registry、预算、Model或迁移，说明前五步的生产实现已满足已确认合同；
   - 本记录、M2入口和总看板：同步M2-20完成状态、验证基线、遗留边界和下一动作；
10. 完整调用链位置：本步实际验证`严格Schema → M2 Registry → Harness权限/预算/超时/Trace → ReadUploadedFileTool/GetEvidenceDetailTool → FileReadingService/EvidenceQueryService → File/Evidence/Retrieval Repository → PostgreSQL + LocalStorage → 严格Result → ToolEnvelope`。不经过HTTP知识API、知识Agent/LangGraph、Qwen、Citation Validator实际回答调用、前端或互联网；
11. TDD RED证据：先新增整链矩阵测试入口并实际运行；收集阶段因`ModuleNotFoundError: No module named 'tests.integration.m2_20_matrix_support'`失败、退出码1，准确证明仓库尚无可复用的真实M2-20整链验收夹具；之后才补测试支持和行为矩阵，没有先改生产代码；
12. 最小GREEN：首轮三角色/五授权、撤权、状态、范围、Storage和请求者矩阵为`16 passed in 14.06s`；补入File/Evidence数据库故障经Service/Tool/Trace三层脱敏后，最终矩阵为`18 passed in 10.50s`。所有用例直接通过，未暴露生产缺陷，因此没有为了制造变更而修改`app/`；同步记录后最终复跑仍为`18 passed in 10.27s`；
13. M2-20聚焦回归：合同、两个Service、两个Tool、真实Repository/Storage和新矩阵共`93 passed in 17.66s`；能够从六个步骤整体证明公开输入、授权重取、有界读取、详情重取、Harness和故障脱敏没有互相冲突；
14. M1/M2相邻回归：进一步加入Retrieval ACL、KnowledgeSearchService/SearchKnowledgeTool、Knowledge Evidence、Context、Citation Validator、M1 Agent Tool/Harness和库存Evidence，共`233 passed in 35.30s`；说明M2五Tool隔离没有污染M1两Tool，M2-19检索/证据链未被M2-20矩阵破坏；
15. 全量结果：精确排除既有跨月用例后，`tests/unit + tests/integration`为`949 passed, 2 skipped, 1 deselected in 86.30s`；原样默认全量为`949 passed, 10 skipped, 1 failed in 83.68s`。唯一失败仍是`test_parse_failure_marks_first_index_failed_without_creating_index_set`写死删除`uploads/2026/08`，当前9月夹具使用不同Key，因而没有抛预期解析错误；它与本步两个读取Tool的调用链无关，未越权修改；
16. 工程质量与迁移：`ruff check app tests scripts`通过，253个文件格式正确；Mypy为120个`app`源文件无问题；compileall、pip check和`git diff --check`通过，diff只输出既有LF/CRLF提示。Alembic current/heads均为`20260902_0010 (head)`，`alembic check`无新升级操作；本步没有生产迁移；
17. 能证明的内容：能证明两个M2读取Tool在三业务角色、owner/company owner/user/role/market ACL下可通过同一真实Harness运行；撤权、软删除、Context请求者变化和旧active来源会在读取时重新生效；指定file ID与Evidence active语义保持刻意差异；解析/locator/Storage/Artifact/数据库故障均形成安全Envelope与Trace；输入和输出不暴露tenant、ACL、私有路径、Storage Key或SQL；
18. 不能证明的内容：矩阵使用小型合成PDF、Fake索引向量和确定性Context，不加载真实BGE/Qwen，不能证明真实模型延迟、三跳Agent策略、超大文件流式随机访问、高并发或灾难恢复；`read_uploaded_file`仍不创建Evidence，因此未来回答不能把它作为无引用事实旁路；也没有证明HTTP知识API、LangGraph回答、Citation Validator与Tool联动或前端展示；
19. 风险与排查顺序：读取失败先查Harness角色/预算与绑定身份，再查owner/ACL、软删除和parse状态；Evidence 404按`tenant Evidence → Context请求者 → 当前ACL → active Version/Index → Chunk/Hash`排查且不向调用者透露具体原因；文件内部错误依次查私有Key形状、Storage对象、Routed/Canonical合同和双Hash；三跳被预算拒绝属于当前已知边界，应在M2-21方案中决定调用策略或预算，不在M2-20回改；
20. 正式数据与停止点：两种全量测试修改了共享测试/演示数据库，随后已依次运行`python -m scripts.seed_m1`、`seed_m2_files`、`seed_m2_complex_files`恢复。只读复核为1个正式tenant、0个M2-20.6测试tenant、10 files、10 documents、10 versions、9 ACL、10个parse/index pending、0 active Version、0 ChunkSet/IndexSet/Chunk、0 ContextArtifact/Evidence/ToolContextLink/AgentRun/ToolCall；Storage精确10 uploads、0 parsed、0 chunks，德国仓关键SKU可售125。记录后最终矩阵复跑再次只读确认tenant/files/documents/versions/ACL仍为`1/10/10/10/9`且Context/Evidence/Link/AgentRun/ToolCall仍全为0。M2-20整体已完成，明确没有开始M2-21、API、Agent、Qwen或前端；下一步应先讨论并确认M2-21方案。
