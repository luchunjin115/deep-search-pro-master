# M2-18：Context、Evidence 与引用验证

> 本文件保存从迁移前单文件中拆出的完整历史方案、实施日志与验证证据。
> 当前状态和阅读入口见 [M2入口](../M2_KNOWLEDGE_RAG.md)。

### 2026-09-01｜M2-18.1｜Context、文档Evidence、预算与错误契约

**状态：已完成；已验证；明确停止在M2-18.1。**

1. 本步解决的问题：M2-17只能给出排好顺序的获权Chunk，项目此前没有统一方式表达“一次有界上下文、其中每段对应哪个`[E#]`、没有证据时怎样返回、未来文档Evidence可以公开哪些字段”，也没有Context专用服务端预算和脱敏错误；
2. 大白话运行过程：本步只先制作“资料包表格”和“安全规则”，没有真正开始整理资料。未来Builder必须把最终获权片段填入`ContextBundle`，每段有局部`[E#]`、Evidence/Chunk身份、公开文档信息、四格式定位、文本Hash和Token数；没有合法片段时明确返回`supported=false`和空列表，不把无证据伪装成系统错误；
3. 输入与输出：输入边界沿用现有Reranker公开身份、文档元数据和PDF/DOCX/XLSX/CSV定位合同；输出冻结为`m2-context-bundle-v1`、`m2-document-evidence-v1`与成功的`CitationValidationResult`。调用者不能在请求中覆盖Token、片段数或邻居窗口；
4. 固定配置：`CONTEXT_MAX_TOKENS=4000`，硬上限16000且不得小于单Chunk上限；`CONTEXT_MAX_SEGMENTS=12`，硬上限12且不得小于Reranker top k；`CONTEXT_NEIGHBOR_WINDOW=1`，硬上限1。Token身份固定为`m2-unicode-token-counter-v1`，这只是项目确定性预算单位，不能证明等同于千问真实Token；
5. 契约约束：有证据Bundle必须包含至少一段和正Token总量，片段Token之和不得超过总量，总量不得超过预算；标签必须按最终顺序连续为`[E1]`至`[E12]`，Evidence ID与Chunk UUID不得重复；anchor不能错误绑定邻居，前/后邻居必须指出其anchor Chunk；空证据必须是零Token和空片段；
6. 隐私边界：新的`DocumentEvidenceSummary/Detail`只允许`knowledge`或`user_file`，包含公开文档身份、四格式locator、来源/上下文Hash和`document_snapshot`信任标记；不包含tenant、owner、ACL、access scope、Storage Key、本地路径、SQL或原始异常。M1既有`EvidenceSummary/Detail`保持原类和行为，没有在本步破坏库存API合同；
7. 固定错误：新增Context输入错误、存储事实不符合合同、未知构建失败、知识Evidence保存失败和非法引用五类固定中文消息；Cause中的SQL、tenant、Storage Key或路径不会进入公开`ErrorDetail`；
8. 实际修改文件与职责：
   - `.env.example`、`app/core/config.py`：登记三项服务端Context预算及相互关系；
   - `app/schemas/context.py`：新增Context Bundle、片段、引用标签与成功引用映射合同；
   - `app/schemas/evidence.py`：在不替换M1数据库Evidence类的前提下新增文档Evidence摘要和详情；
   - `app/core/errors.py`、`app/services/retrieval/errors.py`：新增固定、脱敏的Evidence/引用/Context错误；
   - `app/schemas/__init__.py`、`app/services/retrieval/__init__.py`：导出本步公共契约和错误；
   - `tests/unit/test_context_contracts.py`：覆盖默认/越界配置、有证据/无证据、自相矛盾Bundle、标签/身份唯一性、邻居关系、敏感字段、两类文档Evidence、成功引用映射及错误脱敏；
   - 两份进度文档：记录确认、实现、验证、边界和停止点；
9. 完整调用链位置：本步只定义`RerankedRetrievalResponse → Context Schema → Document Evidence Schema`之间的接口。完整项目链中经过Schema和集中配置/错误，未经过前端、API、Context Service、Repository、Model、PostgreSQL、Storage、Tool、Harness、Agent、LangGraph或Qwen；
10. TDD RED证据：先新增`tests/unit/test_context_contracts.py`，运行`.venv\Scripts\python.exe -m pytest -q tests/unit/test_context_contracts.py`；收集阶段因`ImportError: cannot import name 'CitationValidationError' from 'app.core.errors'`失败，准确证明本步所需合同与错误不存在；
11. TDD GREEN证据：最小实现后新增测试为`13 passed in 2.04s`；Context、Retrieval、Reranker、M1 Schema和配置相邻回归为`82 passed in 2.59s`；全部单元测试为`573 passed in 13.32s`；
12. 工程质量：本步文件`ruff check`通过，格式检查为8文件已格式化；`mypy app`为`Success: no issues found in 112 source files`；`compileall -q app tests/unit`和`pip check`通过。Alembic current/heads均为`20260831_0008 (head)`，`alembic check`为`No new upgrade operations detected`，证明本步没有迁移；
13. 能证明与不能证明：能证明Context/Evidence的公开形状、预算上下限、空证据状态、局部标签范围、基础一致性、敏感字段拒绝和错误脱敏已冻结，且现有单元链未回归。不能证明Hash由真实正文计算、Chunk已重新获权、邻居必要性、去重/overlap/最终渲染预算、Evidence数据库约束或持久化、ACL撤销后读取、伪引用解析及回答语义支持；这些属于M2-18.2至M2-18.6；
14. 风险与优先排查：配置启动失败先核对Context预算是否小于Chunk上限、片段数是否小于Reranker top k；Bundle校验失败先核对`supported/segments/total_tokens`是否自洽，再检查标签和Evidence/Chunk是否重复。当前Schema只校验Hash格式，未来必须由可信Builder计算并由Evidence Service复核，不能接受调用者提供的Hash；
15. 数据、边界与停止点：本步没有访问或修改业务表、Storage或正式模型，因此没有需要恢复的临时数据，也没有重复运行Seed。没有新增Model、Alembic迁移、`context.py` Service、Repository、Evidence写入/读取实现、引用解析器、API、Tool、Harness、Agent、Qwen、前端或模式路由。M2-18.1已完成，必须停止；只有用户理解并明确确认后，才进入M2-18.2的ContextArtifact与Evidence兼容迁移。

### 2026-09-01｜M2-18.2｜ContextArtifact、三分支Evidence与0009迁移

**状态：已完成；已验证；明确停止在M2-18.2。**

1. 本步解决的问题：原`evidences`表在PostgreSQL层只允许`source_type='database'`、库存专用来源名、非空AgentRun/ToolCall和三个库存JSON对象，无法合法保存知识库或用户文件证据，也没有“一次Context”的持久化身份和`[E#]`唯一范围；
2. 大白话运行过程：新增`context_artifacts`作为一次“资料包封面”，保存是谁请求、检索结果和配置的Hash、预算与最终内容Hash；每个文档Evidence像封面下的一张证据卡，记录局部序号和完整文档来源。数据库不是分别检查几个孤立UUID，而是用两条复合外键把Version与File、Chunk与IndexSet/ChunkSet/Version/Document整组绑定，任何串租户或错代次组合都无法写入；
3. 输入与输出：输入是M2-18.1冻结的`m2-context-bundle-v1`、`m2-document-evidence-v1`、4000/12/1预算和文档来源身份；输出是`ContextArtifact` ORM、扩展后的`Evidence` ORM与`20260901_0009`数据库结构。本步没有Service调用入口；
4. `ContextArtifact`结构：保存tenant、请求用户、合同/Token Counter版本、query/retrieval snapshot/config/context/identity五类SHA-256、两个JSON快照、max/total Token、segment count和创建时间；同tenant、同用户、同identity Hash唯一，支持0片段/0 Token的无证据Artifact；预算仍硬限制700至16000 Token和最多12片段；
5. Evidence兼容分支：database分支默认回填/写入`m1-database-evidence-v1`，继续要求完整AgentRun/ToolCall、旧字符串locator、query/structured/access JSON和`internal_demo`；knowledge/user_file分支要求`m2-document-evidence-v1`、`document_chunk`来源名、结构化locator、Context、`[E#]`序号、完整文档来源、两个内容Hash和`document_snapshot`，旧库存专用JSON必须为空；
6. 外键与唯一性：新增Context复合外键；新增Version+Document+File四列来源外键；新增Chunk+IndexSet+ChunkSet+Version+Document六列来源外键。每个Context内`citation_ordinal`唯一，同一个Chunk也只能出现一次；文档来源使用RESTRICT，避免证据存在时物理删除来源，实际业务仍使用既有软删除状态；
7. 运行时边界：`agent_run_id`和`tool_call_id`改为可空但必须同时有值或同时为空；database分支仍强制两者存在，文档分支可在M2-18独立持久化，M2-19接入Tool后也可以同时关联完整运行对。没有提前增加Message关系；
8. 降级安全：0009 downgrade在执行破坏性DDL前检查ContextArtifact或knowledge/user_file Evidence；存在任一行就抛出明确RuntimeError，不静默删除审计资料。没有新文档资料时可完整回到0008，并把旧Evidence列、非空性、CHECK和ToolCall外键恢复为M1形状；
9. 实际修改文件与职责：
   - `app/models/runtime.py`：新增ContextArtifact，扩展Evidence字段、分支CHECK、复合外键、索引、唯一性和只读Context导航；可选JSONB使用`none_as_null=True`确保Python `None`真正写为SQL NULL；
   - `app/models/knowledge.py`：为DocumentVersion+File与DocumentChunk完整代次增加可被复合外键引用的唯一键；
   - `app/models/__init__.py`：导出ContextArtifact；
   - `migrations/versions/20260901_0009_context_and_document_evidence.py`：实现兼容升级、无资料往返降级和有资料拒绝降级；
   - `tests/integration/test_context_evidence_migration.py`：真实PostgreSQL覆盖0008↔0009、M1旧写入、合法文档Evidence、缺字段、跨tenant、伪Chunk、半运行绑定、非法JSON、重复citation/Chunk、降级保护和Metadata一致性；
   - 两份进度文档：同步完成事实、验证、Seed和停止点；
10. 完整调用链位置：本步位于`Evidence Service（尚未实现） → ContextArtifact/Evidence Model → PostgreSQL`。完整项目链中经过Model与PostgreSQL迁移，不经过前端、API、Context Repository/Builder、Evidence Service、Storage读写、Tool、Harness、Agent、LangGraph、Qwen或引用解析；
11. TDD RED证据：先新增真实迁移测试，运行`.venv\Scripts\python.exe -m pytest -q tests/integration/test_context_evidence_migration.py`；收集阶段因`ImportError: cannot import name 'ContextArtifact' from 'app.models.runtime'`失败，准确证明模型和迁移缺失；
12. GREEN修正记录：第一次迁移因CHECK名称被命名规则重复加前缀而整体事务回滚；改用`op.f()`标记实际名称。随后测试发现JSONB的Python `None`会成为JSON null，修正为`none_as_null=True`；又发现`MATCH FULL`会把非空tenant与空运行ID视为部分NULL，改由普通复合外键加独立成对CHECK保证。最后修正原生Connection读取方式和只读关系配置；所有问题均由原测试暴露，没有绕开约束；
13. 验证结果：0009迁移聚焦`4 passed in 3.94s`；包含runtime迁移、M1库存Evidence、Chunk/IndexSet迁移、Model与M2-18.1契约的相邻回归为`50 passed in 5.82s`；排除显式真实模型Smoke和既有跨月硬编码用例后的后端完整Fake门禁为`724 passed, 2 skipped, 1 deselected in 53.53s`；
14. 工程质量：全仓`ruff check app tests scripts migrations`通过，`ruff format --check`为233文件已格式化；`mypy app`为`Success: no issues found in 112 source files`；`compileall -q app tests scripts migrations`、`pip check`和`git diff --check`通过。Alembic current/heads均为`20260901_0009 (head)`，`alembic check`无新操作；
15. 能证明与不能证明：能证明旧M1 Evidence数据库形状升级后仍可写读，三类来源由分支CHECK隔离，合法文档证据可写，跨tenant/错Chunk/缺来源/重复citation/非法JSON/半运行绑定被真实PostgreSQL拒绝，迁移可安全往返且不会静默丢新资料。不能证明CurrentUser/ACL/active Version/active ready Index Set/软删除的读取安全，也不能证明Hash由真实正文计算、幂等Service、Context算法、Evidence详情读取或引用语义；这些属于M2-18.3至M2-18.6；
16. 正式Seed与停止点：完整测试后按`seed_m1 → seed_m2_files → seed_m2_complex_files`恢复。只读复核为10 files、10 documents、10 versions、9 ACL、10 parse pending、10 index pending、0 active Version、0 Chunk Set/Index Set/Chunk、0 ContextArtifact、0 Evidence；Storage为10 uploads、0 parsed、0 chunks；M1 `LR-TL-MUSH-OR01 / DE-FRA`可售125；Alembic为0009 head。没有实现M2-18.3 Repository、安全重取/邻居、Context Builder、Evidence Service、引用解析、API、Tool、Agent、Qwen或前端。M2-18.2已完成，必须停止并等待用户单独确认M2-18.3。

### 2026-09-01｜M2-18.3｜安全重取Reranker锚点与同代次邻居

**状态：已完成；已验证；明确停止在M2-18.3。**

1. 本步解决的问题：Reranker响应是上一时刻生成的精简公开结果，只有公开身份、正文和少量元数据；如果Context直接相信它，就无法发现ACL撤销、active Version/IndexSet切换、文件软删除或响应字段被篡改，也拿不到ChunkSet、顺序、正文Hash、Token和overlap等可信事实；
2. 大白话运行过程：Reranker只交一张“候选名单”，Repository拿当前登录用户重新去数据库验票。先一次查齐所有锚点，确认每张票仍属于当前用户可读的活动成品；再只用数据库刚确认的ChunkSet、IndexSet和序号，一次查齐锚点前后各一段。第二次查询也重新经过整套权限门，并以第二次结果作为最终快照，避免把第一次查询后的旧对象直接交给后续Builder；
3. 输入与输出：输入是可信`CurrentUser`、严格`RerankedRetrievalResponse`和服务端邻居窗口0或1；输出是按Reranker顺序排列的`ContextChunkWindowRecord`，每项包含一个`ContextChunkRecord`锚点及可选previous/next。记录只含后续Context所需的文档代次、File ID、公开元数据、正文、Token、Hash和完整定位/overlap JSON，不含tenant、owner、ACL、Storage Key、向量、FTS或SQL；
4. 安全身份核对：每个锚点必须同时匹配Document ID、Version ID、IndexSet ID和数据库Chunk UUID；正文、标题、文档类型、语言和市场也必须与数据库事实一致。UUID重复、身份伪造、正文/元数据篡改、无ACL、跨tenant、旧Version、旧IndexSet、软删除Document/File都返回同一个不暴露存在性的Repository异常；
5. 邻居边界：邻居不是按“同文档、序号接近”宽松查询，而是同时固定Document、Version、ChunkSet、IndexSet，并继续经过当前active/ready/ACL/软删除安全门；只取`chunk_index - 1`和`chunk_index + 1`，不存在就返回`None`，旧索引代次中相同序号的Chunk不会混入；
6. 查询数量：第一次SQL批量重取最多8个锚点，第二次SQL批量重取锚点和窗口；候选从1增加到8时仍固定两次Chunk查询，不会出现“每个锚点再查一次邻居”的N+1问题。第二次查询重新包含锚点，若权限或active状态在两次语句间失效则整体拒绝；
7. 实际修改文件与职责：
   - `app/repositories/retrieval.py`：新增可信Chunk/窗口不可变记录、统一脱敏的重取异常、锚点事实核对及两次批量获权查询；Dense/Lexical既有查询继续复用原实现；
   - `app/repositories/__init__.py`：从Repository受控入口导出三类M2-18.3记录/异常；
   - `tests/integration/test_context_retrieval_repository.py`：使用真实PostgreSQL覆盖前后邻居、同活动代次、固定两次SQL、ACL/tenant/旧代次/软删除、身份/正文/文档元数据篡改、重复锚点、类型/窗口边界和空结果；
   - 两份进度文档：同步确认记录、验证事实、调用链、边界和停止点；
8. 完整调用链位置：`RerankedRetrievalResponse → RetrievalRepository → Document/Version/IndexSet/Chunk/File Model → PostgreSQL`。安全条件实际复用`DocumentAcl`查询。完整项目链中已经过上游Reranker，当前本步经过Repository、Model和PostgreSQL；未经过前端、HTTP API、Context Builder算法、ContextArtifact/Evidence写入、Storage读写、Tool、Harness、Agent、LangGraph、Qwen或引用解析；
9. TDD RED证据：先新增`tests/integration/test_context_retrieval_repository.py`，运行`.venv\Scripts\python.exe -m pytest -q tests/integration/test_context_retrieval_repository.py`；收集阶段因`ImportError: cannot import name 'ContextChunkRehydrationError'`失败，准确证明安全重取接口与记录不存在；
10. GREEN与相邻回归：最小实现后真实PostgreSQL聚焦为`11 passed in 4.43s`；包含共享安全门、Dense、Lexical、Hybrid、Reranker及Context合同的相邻集合为`126 passed in 7.89s`；测试同时监听SQL执行，确认成功路径的Chunk SELECT精确为2次；
11. 完整Fake门禁：原样全量为`735 passed, 10 skipped, 1 failed in 54.14s`；唯一失败仍是既有`test_parse_failure_marks_first_index_failed_without_creating_index_set`硬编码删除`2026/08`上传Key，而当前9月夹具使用另一Key。按既有边界排除显式Smoke和该用例后为`735 passed, 2 skipped, 1 deselected in 53.78s`，本步未越权修改旧问题；
12. 工程质量：全仓`ruff check app tests scripts migrations`通过，`ruff format --check`为234文件已格式化；`mypy app`为`Success: no issues found in 112 source files`；`compileall -q app tests scripts migrations`、`pip check`和`git diff --check`通过。Alembic current/heads均为`20260901_0009 (head)`，`alembic check`无新操作，因此本步没有迁移；
13. 能证明的内容：能证明Reranker输出进入Context前会按当前用户和当前数据库状态重新获权，四重身份及正文/文档元数据篡改会被拒绝，邻居不会跨Document/Version/ChunkSet/IndexSet，查询数有界且空结果无需访问业务行；也能证明现有检索、Reranker和M2-18.1合同未回归；
14. 不能证明的内容：本步只提供可信原料，尚不能证明邻居一定值得保留、重复锚点/邻居如何合并、overlap如何裁剪、Token与12段预算如何执行、最终Hash/Locator如何生成、ContextArtifact/Evidence如何幂等保存、ACL撤销后的Evidence详情读取或引用是否合法；这些属于M2-18.4至M2-18.6；
15. 风险与优先排查：出现统一重取异常时，服务内部先按“输入是否为真实Reranker响应 → 四重身份是否一致 → ACL/owner/company_owner/role/user/market → active Version → active ready IndexSet → Document/File软删除”的顺序排查，不能把具体缺失项直接返回调用者。邻居缺失先核对Chunk序号是否连续及是否同一ChunkSet/IndexSet；查询数增长先检查是否把批量条件误改为循环查库；
16. 正式Seed与停止点：完整测试后只运行既有`seed_m1 → seed_m2_files → seed_m2_complex_files`恢复。只读复核为PostgreSQL 17.11、pgvector 0.8.6、容器healthy，10 files、10 documents、10 versions、9 ACL、10 parse pending、10 index pending、0 active Version/IndexSet、0 ChunkSet/IndexSet/Chunk、0 ContextArtifact、0 Evidence；Storage精确10 uploads、0 parsed/chunks/其他对象；M1 `LR-TL-MUSH-OR01 / DE-FRA`可售125。M2-18.3已完成，必须停止；没有实现M2-18.4 Context Builder算法、Evidence Service、引用解析、API、Tool、Agent、Qwen或前端，等待用户单独确认下一步。

### 2026-09-01｜M2-18.4｜确定性Context Builder算法

**状态：已完成；已验证；明确停止在M2-18.4。**

1. 本步解决的问题：M2-18.3只交付了获权且可信的锚点/邻居原料，还没有决定哪些片段进入模型上下文、重复内容如何处理、overlap如何裁剪、预算不足时保谁、最终引用顺序和Hash如何稳定。本步只把这些原料构建成内存`ContextBundle`，不写数据库；
2. 大白话运行过程：系统先把Reranker排在前面的锚点当“主证据”，预算还有空间时再补邻居；同一Chunk或正文完全相同的副本只保留优先级更高的一份。确实选中了前一段时，才按Chunk中记录且再次核验过的overlap剪掉重复开头；最后把已选片段恢复为“前一段→锚点→后一段”的阅读顺序，编号为`[E1]`至`[E12]`；
3. 输入与输出及上下游：输入是可信`CurrentUser`、原始`RetrievalRequest`和严格`RerankedRetrievalResponse`；Builder内部只通过`ContextWindowReader.rehydrate_context_windows`取得M2-18.3安全窗口。输出是不可变`BuiltContext`，包括公开`ContextBundle`、与片段对齐的可信私有来源记录、检索快照、配置及各层SHA-256；输出仅在内存中交给下一步持久化Service；
4. 选择优先级：先按Reranker最终名次尝试全部锚点，再按相同窗口顺序尝试previous/next邻居；每次候选加入都重新渲染并核算完整预算。预算冲突时锚点天然优先于邻居；相邻锚点若已经作为主证据出现，不会再以另一个锚点的邻居身份重复出现；
5. 去重边界：第一层按Chunk UUID去重；第二层按NFC规范化、去首尾空白后的正文SHA-256去重，完全相同正文只保留先到的高优先级来源。裁剪后的正文还会再次检查Hash重复和空片段；这不会做模糊语义去重，也不会擅自合并内容相似但不完全相同的证据；
6. overlap规则：文本只在记录声明立即前驱、该前驱确实同时入选、声明Token数不越界且当前前缀精确匹配前驱后缀时裁剪；否则声明不一致会安全失败。表格同时验证结构化行数与正文行数，只移除明确标记`repeated_as_context=true`且Token数与声明一致的重复行；没有选中前驱时不裁剪，避免凭单边声明误删事实；
7. 预算和顺序：服务端构造参数严格限制Token为700至16000、片段为5至12、邻居窗口为0至1，并要求固定`m2-unicode-token-counter-v1`。默认使用4000 Token、12片段和前后各1段；每次加入后的实际渲染Token总和不得超过上限。选择优先级与展示顺序分离，最终按Reranker窗口内previous/anchor/next的自然顺序稳定输出；
8. 数据验真与公开边界：Builder再次核对窗口数量、锚点与Reranker四重身份/正文/文档元数据、Canonical Chunk ID、Chunk类型、访问级别、扩展名、正文Hash格式、Token下界、表格结构、Locator及同代次邻居关系。公开来源把`private`映射为`user_file`，把`tenant/restricted`映射为`knowledge`；响应不包含tenant、owner、ACL、Storage Key、路径、向量、FTS或SQL；
9. 稳定身份：查询、检索快照、Builder配置、上下文内容和幂等身份分别计算规范JSON SHA-256；Context UUID由tenant、user和幂等Hash通过固定namespace UUID5生成，Evidence UUID由Context、片段序号、Chunk UUID和裁剪后正文Hash确定性生成。相同输入与可信数据库快照得到相同ID、顺序和Hash；本步只是预生成身份，未持久化；
10. 实际修改文件与职责：
   - `app/services/retrieval/context.py`：新增Reader协议、`BuiltContext`、参数护栏、窗口验真、优先级选择、双重去重、文本/表格overlap、预算、自然顺序、公开映射及确定性Hash/UUID；
   - `app/services/retrieval/__init__.py`：从Retrieval Service受控入口导出Builder、版本和结果类型；
   - `tests/unit/test_context_builder.py`：覆盖确定性、自然顺序、来源映射、敏感字段缺失、相邻锚点、正文去重、选中/未选前驱、文本/表格overlap、锚点预算优先、精确Token/片段边界、空结果及错误映射；
   - `tests/integration/test_context_retrieval_repository.py`：在真实PostgreSQL安全重取后直接构建Context，验证公开Locator与内部File来源仍对齐；
   - 本文件和`docs/PROJECT_PROGRESS.md`：同步确认、验证、边界和下一停止点；
11. 完整调用链位置：`RetrievalRequest + RerankedRetrievalResponse → ContextBuilderService → RetrievalRepository → Document/Version/ChunkSet/IndexSet/Chunk/File Model → PostgreSQL → 内存ContextBundle`。本步经过Schema、Service、Repository、Model和PostgreSQL读取；未经过前端、HTTP API、ContextArtifact/Evidence写入、Storage读写、Tool、Harness、Agent、LangGraph、Qwen或引用解析；
12. TDD RED证据：先新增`tests/unit/test_context_builder.py`并运行聚焦测试；收集阶段因`ModuleNotFoundError: No module named 'app.services.retrieval.context'`失败，准确证明Builder模块尚不存在。最小实现后Builder单元测试为`13 passed in 1.57s`；
13. GREEN、集成与相邻回归：Builder单元加真实PostgreSQL安全重取集成为`25 passed in 4.76s`；包含Chunk合同/持久化、Context合同、Repository、Dense/Lexical/Hybrid和Reranker的相邻集合为`159 passed in 8.96s`。这证明算法边界及Repository到Builder的真实数据库读取路径可用，但没有证明数据库写入或模型回答；
14. 完整门禁与工程质量：原样全量为`749 passed, 10 skipped, 1 failed in 55.80s`，唯一失败仍是既有`test_parse_failure_marks_first_index_failed_without_creating_index_set`把上传Key写死为`2026/08`而当前日期为9月，本步未越权修改。排除显式Smoke和该既有用例后为`749 passed, 2 skipped, 1 deselected in 55.40s`；全仓Ruff通过、236文件已格式化，Mypy为113个app源文件无问题，compileall、pip check通过；Alembic current/heads均为`20260901_0009 (head)`且check无新操作；
15. 能证明、不能证明与排查方向：能证明获权窗口会按确定性优先级、严格overlap和预算产生无敏感字段的稳定内存Context，空结果稳定返回`supported=false`，异常被映射为Context类型化安全错误。不能证明ContextArtifact/Evidence已经幂等写入、事务失败可补偿、ACL撤销后Evidence详情读取安全、模型引用`[E#]`真实存在或回答忠于证据；这些属于M2-18.5与M2-18.6。构建失败优先依次核对M2-18.3窗口完整性、Chunk Token/Hash/Locator、overlap前驱与正文、表格重复行、预算配置，不能先放宽约束；
16. 正式Seed与停止点：完整测试后只运行既有`seed_m1 → seed_m2_files → seed_m2_complex_files`恢复。只读复核为PostgreSQL 17.11、pgvector 0.8.6、10 files、10 documents、10 versions、9 ACL、10 parse pending、10 index pending、0 active Version、0 ChunkSet/IndexSet/Chunk、0 ContextArtifact、0 Evidence；Storage精确10 uploads；M1 `LR-TL-MUSH-OR01 / DE-FRA`可售125。M2-18.4已完成，必须停止；没有实现M2-18.5 Evidence持久化Service、引用解析、API、Tool、Agent、Qwen或前端，等待用户单独确认下一步。

### 2026-09-01｜M2-18.5｜Context与文档Evidence原子幂等持久化

**状态：已完成；已验证；明确停止在M2-18.5。**

1. 本步解决的问题：M2-18.4只能返回内存`BuiltContext`；进程结束后没有“一次资料包封面”和每张`[E#]`证据卡的数据库记录，也不能证明重复重试不会复制数据、保存一半失败不会残留半成品，或Builder完成后撤权/切代的数据不会继续落库；
2. 大白话运行过程：保存前先检查“资料包防伪码”，再拿当前登录用户去数据库重新验一次每张最终证据的权限和代次；随后尝试登记Context封面和全部Evidence卡片。相同ID已经存在时不盲目报错或覆盖，而是把数据库现有内容逐字段核对；完全一致就复用，任何冲突、缺行或多行都整包失败并回滚；
3. 输入、输出与事务所有权：输入是可信`CurrentUser`、M2-18.4的`BuiltContext`，并预留可选的既有`EvidenceWriteContext`运行对；输出是不可变`PersistedDocumentContext`，含原`ContextBundle`、按`[E#]`对齐的`DocumentEvidenceDetail`及`reused`事实。Service使用嵌套保存点并flush，但不commit外层Session，继续由请求/Harness事务决定最终提交或回滚；
4. Builder产物验真：保存前重新计算检索快照Hash、配置Hash、每段正文Hash/Token、Context内容Hash、幂等身份Hash、Context UUID5和每个Evidence UUID5，同时核对片段与私有来源的Chunk/Document/Locator/来源类型对齐。手工构造或篡改的`BuiltContext`不能只凭类型进入数据库；
5. 写前重新获权：`RetrievalRepository.reauthorize_context_sources`复用tenant、owner/company_owner、user/role/market ACL、active Version、active ready IndexSet、Document/File软删除安全门，并用`FOR UPDATE`锁定查询到的当前来源行；返回的完整`ContextChunkRecord`必须与Builder私有来源逐项相同。空证据不查询业务Chunk，但仍可保存零片段审计Artifact；
6. 幂等与冲突策略：Context和Evidence沿用M2-18.4确定性UUID及M2-18.2唯一约束，PostgreSQL使用`ON CONFLICT DO NOTHING`应对重复/并发重试，随后按tenant、user、identity或Context重新读取并逐字段验真；已有相同资料完整复用并返回`reused=true`，ID碰撞、身份Hash冲突、部分Evidence或错运行绑定统一安全失败，不覆盖旧审计事实；
7. 原子性：Context插入、所有Evidence批量插入、现有行复核和公开详情构造都位于同一嵌套保存点；任一步出现SQL、Schema、来源撤权或冲突错误，保存点整体回滚。测试注入Evidence写入异常后确认ContextArtifact与Evidence计数都仍为0；
8. Evidence映射：每段写`m2-document-evidence-v1`、`document_chunk`、knowledge/user_file、局部序号、公开结构化Locator、标题和最多1000字符excerpt；同时保存File/Document/Version/ChunkSet/IndexSet/Chunk完整来源、源Chunk内容Hash和Context裁剪后正文Hash，`trust_level=document_snapshot`且明确为合成数据。独立M2-18调用允许AgentRun/ToolCall同时为空；可选运行对必须tenant一致并继续受数据库复合外键保护；
9. 实际修改文件与职责：
   - `app/repositories/retrieval.py`：新增最终来源写前重新获权、逐项核对和行锁；
   - `app/repositories/evidence.py`：新增`KnowledgeEvidenceRepository`，负责Context/Evidence冲突安全插入、按幂等身份读取和稳定序号读取；既有M1 Evidence读取保持不变；
   - `app/services/retrieval/context.py`：新增`validate_built_context`，集中复算Builder输出的Hash、Token和UUID身份；
   - `app/services/evidence.py`：扩展现有`EvidenceService`，新增`PersistedDocumentContext`、文档Context原子持久化、字段映射、冲突核对和公开详情构造；库存Evidence方法未改；
   - `app/repositories/__init__.py`、`app/services/__init__.py`、`app/services/retrieval/__init__.py`：导出新的受控接口；
   - `tests/integration/test_knowledge_evidence_service.py`：真实PostgreSQL覆盖成功、幂等、空证据、撤权、私有来源篡改、故障注入与整包回滚；
   - 本文件和`docs/PROJECT_PROGRESS.md`：同步确认、验证、风险、Seed和下一停止点；
10. 完整调用链位置：`CurrentUser + BuiltContext → EvidenceService → validate_built_context → KnowledgeEvidenceRepository → RetrievalRepository共享安全门 → Document/File/Version/IndexSet/Chunk + ContextArtifact/Evidence Model → PostgreSQL → PersistedDocumentContext`。本步经过Schema、Service、Repository、Model和PostgreSQL读写；未经过前端、HTTP API、Storage读写、Tool执行、Harness、Agent、LangGraph、Qwen、最终回答或引用解析；
11. TDD RED证据：先新增真实集成测试并运行`.venv\Scripts\python.exe -m pytest -q tests\integration\test_knowledge_evidence_service.py`；收集阶段因`ImportError: cannot import name 'KnowledgeEvidenceRepository' from 'app.repositories.evidence'`失败，准确证明缺失的是M2-18.5持久化入口；
12. GREEN与相邻回归：最小实现后真实PostgreSQL聚焦为`6 passed in 3.70s`；M2文档持久化、M1库存Evidence、Context Builder与合同相邻集合为`35 passed in 3.82s`。第一次撤权测试使用系统当前时间，因夹具`created_at`固定在稍后的09:00 UTC而被数据库“删除时间不得早于创建时间”约束正确拒绝；测试改用`created_at + 1秒`表达合法软删除，没有放宽生产约束；
13. 完整门禁：原样默认全量为`755 passed, 10 skipped, 1 failed in 57.83s`，唯一失败仍是既有`test_parse_failure_marks_first_index_failed_without_creating_index_set`把上传Key写死为`2026/08`而当前日期为9月，本步未越权修改。排除显式真实模型Smoke和该既有用例后为`755 passed, 2 skipped, 1 deselected in 60.04s`；
14. 工程质量与额外调查：全仓Ruff通过，237文件已格式化；Mypy为113个app源文件无问题；compileall、pip check和git diff check通过。Alembic current/heads均为`20260901_0009 (head)`且check无新操作，因此本步无需迁移。人工把固定UUID数据库集成文件改成非默认执行顺序时可复现3个Dense/Hybrid/Reranker夹具互相污染失败；三个目标单跑通过，默认全量只剩既有跨月失败，确认不是本步生产回归，但这是后续测试隔离加固项；
15. 能证明、不能证明与排查方向：能证明当前获权、未变更的Builder产物可原子幂等持久化；重复调用不增行，空证据有审计封面，撤权/篡改/冲突/数据库故障不会返回伪成功，M1 database Evidence仍兼容。不能证明ACL撤销后Evidence详情读取、模型回答中的标签解析、`[E99]`/重复/错位引用拒绝、答案语义是否受证据支持或ToolCall多次调用策略；这些属于M2-18.6和M2-19以后。失败优先按“Builder身份Hash → 当前ACL/active/软删除 → 来源代次 → Context冲突 → Evidence序号/Chunk冲突 → 外层事务状态”排查，不返回原始SQL异常；
16. 正式Seed与停止点：完整测试后只运行既有`seed_m1 → seed_m2_files → seed_m2_complex_files`恢复。只读复核为PostgreSQL 17.11、pgvector 0.8.6、10 files、10 documents、10 versions、9 ACL、10 parse pending、10 index pending、0 active Version、0 ChunkSet/IndexSet/Chunk、0 ContextArtifact、0 Evidence；Storage精确10 uploads；M1 `LR-TL-MUSH-OR01 / DE-FRA`可售125。M2-18.5已完成，必须停止；没有实现M2-18.6引用验证、API、Tool、Agent、Qwen或前端，等待用户单独确认下一步。

### 2026-09-01｜M2-18.6｜严格引用解析与当前授权白名单验证

**状态：已完成；已验证；M2-18已收口；明确停止在M2-19之前。**

1. 本步解决的问题：M2-18.5已经把Context和每张`[E#]`证据卡安全保存到PostgreSQL，但模型回答仍只是一段普通字符串；如果不再验票，模型可以漏写引用、编造`[E99]`、重复贴同一标签，或在保存后权限撤销、文档删除、active代次切换时继续引用旧Evidence。本步只建立最终答案字符串到当前获权Evidence白名单的验证边界；
2. 大白话运行过程：系统先检查回答里的“票号”是不是严格的半角大写`[E1]`至`[E12]`，再拿登录用户和Context ID去数据库取当前仍可看的证据名单。答案可以只引用其中一部分，也可以按叙述需要改变出现顺序，例如`[E3]`后接`[E1]`；但同一票号重复、票号写错、资料包属于别人、文档后来撤权/删除/换代，都会统一拒绝。最终返回的Evidence UUID由数据库按局部序号映射，不相信回答自报；
3. 输入、输出与边界：`CitationValidatorService.validate_answer`输入可信`CurrentUser`、持久化`context_id`和非空且不超过100000字符的回答字符串，输出既有严格`CitationValidationResult`，其中`ContextCitation`按答案出现顺序保存`citation_label`与数据库Evidence ID。Repository只返回最小不可变`AuthorizedCitationContext`，不把正文、ACL、Storage Key、路径或SQL交给解析器；
4. 严格语法：只认可ASCII半角括号、大写`E`和无空格十进制序号`[E1]`至`[E12]`；`[E0]`、`[E13]`、`[E99]`、`[e1]`、`[E 1]`、`［E1］`、缺右括号及重复标签均安全失败。支持型Context至少需要一个合法引用；空Context只允许零引用，仍不在本步判断回答是否采用了正确拒答措辞；
5. 当前Context归属：Repository按Context ID、当前用户tenant和`requested_by_user_id`同时读取；即使同租户其他用户或company owner也不能拿另一个请求者的Context验票，避免把一次用户私有检索快照当成租户共享资料包；不存在、跨租户或跨用户统一表现为安全的引用验证失败；
6. 当前ACL与代次复核：非空Context复用`RetrievalRepository.authorized_active_chunks_statement(CurrentUser)`，并把每条Evidence的Chunk、Document、Version、ChunkSet、IndexSet完整身份连接到共享安全门；只有Document/File未软删除、Version仍active、Index Set仍active ready且owner/company_owner/user/role/market ACL当前允许时，整份有序Evidence白名单才返回。任意一张卡过期或未获权都拒绝整个Context，不降级为残缺白名单；
7. 持久化结构验真：Repository还核对Context合同版本、Token计数器版本、`segment_count`、Evidence数量与从1开始的连续局部序号，以及`m2-document-evidence-v1`、`document_chunk`和knowledge/user_file分支。空Context必须确实是零Evidence；结构缺行、多行、错序号或错类型时不返回可用快照；
8. 安全错误：类型错误、空白/超长回答、无效标签、不可见/过期Context统一抛出既有`CitationValidationError`；SQLAlchemy数据库故障转换为既有`EvidenceReadError`，不向上暴露原始SQL、表名、tenant或权限细节。解析成功只表示标签存在且当前可读，不表示答案内容在语义上真的被该Evidence支持；
9. 实际修改文件与职责：
   - `app/services/citations.py`：新增Reader协议、严格/可疑标签解析、答案边界、支持/空Context规则及答案顺序到Evidence ID的映射；
   - `app/repositories/evidence.py`：新增`AuthorizedCitationContext`和当前用户/当前ACL/当前代次下的完整Evidence白名单读取；既有M1库存Evidence读取和M2-18.5写入保持不变；
   - `app/repositories/__init__.py`、`app/services/__init__.py`：导出新的受控接口；
   - `tests/unit/test_citation_validator.py`：用Fake覆盖子集/顺序、无引用、重复、越界、大小写/空格/全角/缺括号、空Context、安全错误和输入上限；
   - `tests/integration/test_citation_validator.py`：先经M2-18.5真实持久化，再用真实PostgreSQL验证成功、跨用户/tenant、软删除撤权和空Context；
   - 本文件和`docs/PROJECT_PROGRESS.md`：同步确认、验证、边界、风险、Seed和M2-18收口状态；
10. 完整调用链位置：`模型答案字符串（本步测试直接提供） + CurrentUser + context_id → CitationValidatorService → KnowledgeEvidenceRepository → RetrievalRepository共享安全门 → ContextArtifact/Evidence + Document/File/Version/ChunkSet/IndexSet/Chunk Model → PostgreSQL → CitationValidationResult`。本步经过Schema、Service、Repository、Model和PostgreSQL读取；未经过前端、HTTP API、Storage、Tool、Harness、Agent、LangGraph、Qwen调用或数据库写入，也没有新增迁移；
11. TDD RED证据：先新增引用单元/真实数据库测试并运行聚焦集合；收集阶段分别因`AuthorizedCitationContext`无法导入和`app.services.citations`不存在失败，准确证明缺少的是引用白名单记录、Repository入口和Validator模块，而不是现有Context Builder或Evidence持久化故障；
12. GREEN与相邻回归：最小实现及格式修正后，单元`15 passed in 1.42s`、真实PostgreSQL集成`3 passed in 2.70s`，合计`18 passed in 2.76s`；包含Context合同/Builder/Repository、Evidence迁移/持久化及M1库存Evidence的相邻集合为`69 passed in 7.79s`。这证明字符串规则与数据库当前授权映射可以连通，也证明既有Evidence相邻能力未回归；
13. 完整门禁：原样默认全量为`773 passed, 10 skipped, 1 failed in 62.77s`；唯一失败仍是既有`test_parse_failure_marks_first_index_failed_without_creating_index_set`把删除Key写死为`2026/08`，当前9月实际上传对象未被删除，因此没有抛预期解析异常，本步未越权修改。排除显式真实模型Smoke和该既有用例后为`773 passed, 2 skipped, 1 deselected in 62.38s`；
14. 工程质量与迁移：全仓Ruff lint通过，240文件已格式化；Mypy为114个app源文件无问题；compileall、pip check和git diff check通过。Alembic current/heads均为`20260901_0009 (head)`，`alembic check`确认无新升级操作，因此M2-18.6不需要Schema或数据库迁移；
15. 能证明、不能证明与排查方向：能证明合法标签只能映射到该请求者当前完整获权Context内的Evidence，伪造/重复/畸形/越界/跨用户/撤权/软删除/旧代次不会通过，空Context不能伪造引用。不能证明回答事实正确、每句话都受所引证据支持、引用位置贴近对应陈述、无答案时拒答措辞合格、Prompt注入已隔离或Qwen真实输出质量；这些属于M2-21回答链和M2-22评估。失败优先按“回答字符/标签语法 → Context请求者归属 → Context/Evidence数量与序号 → 当前ACL/软删除 → active Version/Index Set → Evidence完整来源身份 → 数据库可用性”排查，不应先放宽校验；
16. 正式Seed、启动问题与停止点：全量测试后依次用模块方式运行既有`seed_m1 → seed_m2_files → seed_m2_complex_files`恢复；首次直接执行`python scripts/seed_m1.py`因仓库根目录未进入模块搜索路径而在导入`app`时失败，未触碰数据库，改用`python -m scripts.seed_m1`后成功，无需修改业务代码。最终只读复核为PostgreSQL 17.11、pgvector 0.8.6、容器healthy，10 files、10 documents、10 versions、9 ACL、10 parse pending、10 index pending、0 active Version/IndexSet、0 ChunkSet/IndexSet/Chunk、0 ContextArtifact、0 Evidence；Storage精确10 uploads、0 parsed/chunks/其他对象；M1 `LR-TL-MUSH-OR01 / DE-FRA`可售125。M2-18.6及整个M2-18现已完成，明确没有开始M2-19、Tool、API、Agent、Qwen或前端，等待用户确认进入下一阶段方案。
