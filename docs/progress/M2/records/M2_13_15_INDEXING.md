# M2-13 至 M2-15：检索存储、Embedding 与索引管线

> 本文件保存从迁移前单文件中拆出的完整历史方案、实施日志与验证证据。
> 当前状态和阅读入口见 [M2入口](../M2_KNOWLEDGE_RAG.md)。

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

- 本方案已写入`docs/progress/M2/M2_KNOWLEDGE_RAG.md`，保存现状、取舍、实施步骤、验证、风险和停止点；
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
   - `docs/progress/M2/M2_KNOWLEDGE_RAG.md`与`docs/PROJECT_PROGRESS.md`：记录本步证据、阶段完成状态、遗留边界与停止点；
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
3. 修改文件与职责：`tests/integration/test_document_chunk_set_migration.py`在测试插入值中显式加入既有`created_at`，消除UTC 10:01之后运行必失败的时间依赖，继续验证`started_at >= created_at`约束；`docs/progress/M2/M2_KNOWLEDGE_RAG.md`与`docs/PROJECT_PROGRESS.md`记录本机恢复、修复和验证证据。BGE快照位于Git忽略的`data/model-cache`，匿名报告位于Git忽略的`output/m2_embedding_benchmarks/local.json`；
4. 完整调用链位置：环境门禁覆盖`前端 → API → Pydantic Schema → Service/LangGraph/Harness或DocumentIndexService → EmbeddingProvider/Repository → Model → PostgreSQL/pgvector`。测试夹具修复只作用于Model/PostgreSQL迁移约束测试，不修改生产调用链、迁移或业务数据合同；
5. 基础设施与迁移验证：Docker Desktop恢复后`deep-search-postgres`为healthy，`pg_isready`接受连接，数据库`vector`扩展为0.8.6；Alembic实际从`20260829_0004`依次升级`0005/0006/0007`，最终`current=20260831_0007 (head)`且`alembic check`为`No new upgrade operations detected`；
6. BGE验证：显式下载并校验固定`BAAI/bge-m3@5617a9f61b028005a4858fdac845db406aefb181`快照，重组后约2.30 GB。真实基准中文相关/无关相似度为`0.840595 > 0.348997`，跨语言为`0.731607 > 0.308162`；强制离线Embedding Smoke为`2 passed in 50.71s`，真实`DocumentIndexService → PostgreSQL/pgvector`单文档索引、幂等复用与清理Smoke为`1 passed in 32.06s`；
7. 后端验证：首次全量为`1 failed, 515 passed, 8 skipped`，失败精确落在Chunk Set迁移测试的固定时间夹具；最小修复后该文件`2 passed`、Ruff通过，最终全量为`516 passed, 8 skipped in 110.52s`。8项跳过分别来自2项默认关闭的BGE Embedding、1项默认关闭的BGE索引、1项付费Qwen、2项显式Docling和2项当前Windows符号链接权限；BGE三项已在本步显式单独通过；
8. 前端与端到端验证：Vitest组件`4 passed`，TypeScript `tsc --noEmit`、ESLint和Next.js 16.3.3生产构建通过；清理组合脚本遗留的精确Uvicorn进程后，Chromium `4 passed`，覆盖德国库存/Evidence成功、法国账号跨市场403、无效Token 401，以及PostgreSQL中断时安全500与自动恢复；
9. 能证明与不能证明：能证明当前电脑的依赖、PostgreSQL/pgvector、最新迁移、固定BGE本地权重、真实向量生成、真实单文档索引、默认后端回归、前端构建和M1浏览器闭环可运行；不能证明付费Qwen真实调用、当前Windows符号链接能力、M2复杂Docling显式Smoke、GPU性能、10文档真实BGE语义质量或任何尚未实现的关键词/Dense/混合/RRF/Reranker/RAG质量；
10. 风险与排查：迁移导入失败先查虚拟环境`pgvector`；数据库不可用先查Docker Desktop、容器health和5433；BGE失败先查固定manifest/revision、约2.30 GB快照、离线变量和内存；Chunk Set时间约束失败先比较测试显式`created_at/started_at`，不得放宽生产约束；Playwright启动失败先查8000/3000占用并只终止命令行明确属于本项目的遗留进程；
11. 下一步与停止点：本机已经具备继续讨论下一阶段的运行基线，但当前授权仍不包含M2-16代码。M2-16必须先提交实施方案并由用户明确确认，不能因环境恢复而自动开始。
