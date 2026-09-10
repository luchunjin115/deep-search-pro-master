# M2-22｜跨境电商 RAG 与多 Agent 评估方案

> 文档状态：进行中；M2-22.1 至 M2-22.6 已完成；M2-22.7五步详细方案已提交，运行代码和真实评估尚未开始
>
> 方案形成日期：2026-09-07
>
> 当前授权边界：用户已要求进入M2-22.7，但随后明确先同步文档并查看详细步骤；当前只完成方案与状态同步。必须由用户确认本方案后才开始M2-22.7.1，且每个小步完成后停止，不自动进入下一小步；M2-22.7不得运行Knowledge Tool、Harness、Agent/LangGraph、最终回答、Citation、Qwen回答或前端
>
> 上游基线：M2-01 至 M2-21 已完成；`m2-v1` 与 `m2-complex-v1` 共 10 份合成文件、20 条 Golden、约 35 个 Chunk，只作为工程回归集
>
> 实施原则：真实数据必须经过项目现有摄取链；项目评估器负责 Parser/OCR/Chunk/精确检索/权限/引用，Ragas（RAGAS）负责检索与生成语义指标，人工复核固定 Test 与 Bad Case；先完成 RAG 并停下复核，再单独设计和授权意图识别与执行分流，改造完成后才评估最终多 Agent 轨迹；PQA 暂缓

## 1. 为什么需要修订原 M2-22

原始 M2-22 计划只准备复用 10 份合成文件和约 20 条问题。这批文件总共约 243.5 KiB，每份通常只有 1 至 2 页或几行表格，适合证明 PDF、DOCX、XLSX、CSV、OCR、ACL、定位和索引链没有坏，但不足以回答以下质量问题：

- 当前结构感知切块是否把完整规则、表头和答案留在同一个 Chunk；
- 当前结构感知切块的 `target=600`、`max=700`、`overlap=100` 是否比其他完整配置更合适；
- Dense、Lexical、RRF 和 Reranker 分别贡献了多少质量；
- Dense/Lexical/Hybrid 候选各取 30、RRF `k=60`、Reranker 保留 8 条是否合理；
- 真实长 PDF、法规、跨境流程、相似产品和 OCR 噪声下是否仍能找到正确证据；
- 最终回答是否正确、忠于证据、引用准确，并在无答案时拒答；
- 多 Agent 的规划、委派和 Tool 选择是否正确，还是只因为底层 RAG 恰好容易而看起来成功。

因此，M2-22 不能只做一个“20 题最终准确率”。它需要先把 RAG 的每一层拆开测量，再评估 Agent 使用这条 RAG 链的行为。

## 2. 用大白话说明本阶段

本阶段会建立一个小型、可重复的“跨境电商公司资料室”。资料室中既有项目自己生成、答案完全可控的产品和运营文件，也有欧盟和德国公开的真实跨境电商规则、产品安全通报和表格。

系统必须先把这些原始文件经过真实上传、解析/OCR、切块、Embedding、pgvector、混合检索和重排，再回答问题。评估器会沿途检查：

```text
原文件有没有读对
→ 正确内容有没有被切坏
→ 正确 Chunk 有没有进入候选
→ RRF/Reranker 有没有把它排到前面
→ Context 有没有保留必要信息
→ 最终答案有没有忠于 Evidence 并正确引用
```

项目自己的评估器先计算可由 Golden Evidence、来源定位和运行Trace确定判断的指标；检索产生真实 Chunk、Qwen产生真实回答后，再把问题、人工参考答案、真实检索上下文和回答映射给 Ragas。Ragas 是自动阅卷器，不拥有下载、解析、切块、入库、检索、权限或回答主链，也不能用一个语义总分替代逐层故障定位。

RAG 通过复核后，先把请求分成简单单一查询、固定复合查询和确需规划的复杂任务，并让它们分别走快速路径、受控Pipeline和Supervisor/Worker。改造完成后，才使用另一组用例检查路由、Supervisor、Worker、Tool、预算、并行和恢复。RAG质量与Agent轨迹不混在同一个总分里。

## 3. 当前输入、输出和上下游

### 3.1 输入

- 已冻结的 `m2-v1`、`m2-complex-v1` 10 份合成工程回归文件；
- 经过许可、大小、Hash 和版本核验的少量真实跨境电商公开文件；
- 人工冻结的问题、答案要点、正确 Evidence 范围和拒答预期；
- 当前生产配置和候选实验配置；
- 固定版本的 Native Parser、Docling、BGE-M3、BGE-Reranker、Qwen/Fake Provider；
- 可信 `CurrentUser`、tenant、role、market、ACL 和当前 active 版本。

### 3.2 输出

- 版本化来源 Manifest，不把第三方大文件提交 Git；
- 40 条 Smoke 和至少 120 条正式评估用例；
- Parser/OCR、Chunk、Dense、Lexical、RRF、Reranker、Context、Answer/Citation 分层报告，并明确区分项目确定性指标与 Ragas 语义指标；
- TopK、RRF 和切块参数的对比报告；
- 真实跨境电商、合成跨境电商、通用文档诊断、安全用例四组独立结果；
- 可复现的 Bad Case，能定位失败发生在哪一层；
- RAG 复核通过后，先产出意图/复杂度路由与执行分流验证，再产出独立的最终 Agent 轨迹评估报告；
- 运行结束后恢复正式 Seed，不留下外部评估数据污染日常演示库。

### 3.3 上下游关系

- 上游：M2-06 上传、M2-07 至 M2-11 解析/OCR、M2-12 切块、M2-13 至 M2-15 索引、M2-16 检索、M2-17 Reranker、M2-18 Context/Evidence、M2-19 至 M2-21 Tool/Agent 主路径；
- 本阶段：M2-22.1至.8、.9至.10只新增评估数据合同、准备脚本、Runner、报告和必要的测试接缝；新插入的M2-22.8R是独立的生产执行分流改造，必须另行提交完整实施方案和获得授权；
- 下游：M2-23 前端引用展示、M2-24 最终演示收口、M5 综合评估和作品化；
- 评估步骤不得为了提高分数顺手修改生产 Parser、Chunker、Retriever、Reranker、Agent 或数据库结构。评估发现的问题进入 Bad Case，修复必须另行说明范围并获得授权；M2-22.8R只处理已确认的意图与执行分流问题，不借机扩展其他能力。

## 4. 数据是否符合跨境电商场景

结论是“分层后符合”，不能把所有公开商业文件都算作跨境电商资料。

| 数据层 | 内容 | 场景匹配 | 在本方案中的用途 |
|---|---|---|---|
| 现有合成跨境电商回归集 | 产品说明、质检、德国合规、供应商报价、月度运营、入库、市场简报、成本和补货 | 高，但不是真实经营数据 | 保留不变，检查工程回归和可控事实 |
| 欧盟/德国真实规则与流程 | VAT/OSS/IOSS、低价值包裹、海关、GPSR、包装注册、退货/召回 | 高，属于真实跨境经营知识 | 核心真实 RAG 语料和核心业务评分 |
| Safety Gate 产品通报/Excel | 产品、型号、风险、措施、国家等真实公开记录 | 高，贴近选品与合规排查 | 表格、相似产品、跨文档和合规问答 |
| 通用合同、发票、采购单 | NDA、发票、订单、收据 | 中或低 | 只测 OCR、合同长度、表格和版面，不计入核心业务总分 |
| UN/世界银行采购资料 | 政府采购流程和模板 | 低 | 最多保留 1 至 2 份做长文档/真实 DOCX 诊断，不代表跨境电商 |
| PQA/ESCI/Amazon-M2 | 商品问答、搜索相关性、商品主数据 | 相关但属于另一类公开基准或数据扩充 | 本轮暂缓，避免掩盖原始文件摄取与切块问题 |

真实企业的库存、供应商底价、退货明细和内部 SOP 通常不会合法公开。因此这部分继续使用明确标记的合成数据；法规、海关、包装和风险通报使用真实官方资料。对外展示必须分别说明来源，不能把合成库存描述成真实卖家库存。

## 5. 计划使用的数据包

### 5.1 A 组：固定工程回归集，不修改

继续使用以下两个版本：

- `m2-v1`：5 份普通 PDF/DOCX/XLSX/CSV；
- `m2-complex-v1`：5 份扫描、双栏、复杂 PDF 表格、图文 DOCX 和复杂 XLSX；
- 总大小约 243.5 KiB；
- 共 20 条 Golden；
- 用途是防止新增真实语料后破坏既有解析、权限、定位和检索基线；
- 不把这 20 条题的成绩作为真实业务质量结论。

### 5.2 B 组：真实跨境电商核心语料

首批只选 8 至 12 份官方 PDF/XLSX，不爬取整站：

1. 欧盟 VAT 电商、OSS/IOSS 指南；
2. 欧盟低价值包裹进出口与报关指南；
3. 欧盟低价值商品退运说明；
4. 欧盟 GPSR 企业指南；
5. GPSR 在线销售与平台义务问答；
6. 德国 LUCID/包装法面向在线零售商的说明与案例；
7. 欧盟 Safety Gate 产品安全年度资料；
8. 5 至 10 份选定产品风险通报 PDF；
9. 1 至 2 份 Safety Gate 搜索结果 Excel 导出；
10. 必要时补 1 份官方国际电商出口流程 PDF。

候选官方入口：

- <https://vat-one-stop-shop.ec.europa.eu/guides_en>
- <https://taxation-customs.ec.europa.eu/customs/union-customs-code/ucc-guidance-documents_en>
- <https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX%3A52025XC06233>
- <https://www.verpackungsregister.org/en/knowledge-bases/mail-order-companies-and-online-retailers>
- <https://www.verpackungsregister.org/fileadmin/files/Erklaermaterialien/Example_online-retailer.pdf>
- <https://commission.europa.eu/topics/business-and-industry/product-safety_en>

最终名单以实施时实际下载页、许可条款、文件大小、语言、版本和 SHA-256 为准。法规内容会更新，Manifest 必须记录发布日期与访问日期，评测只能回答所冻结版本的内容，不能冒充最新法律意见。

### 5.3 C 组：真实复杂文档诊断集

该组不进入跨境电商核心业务总分：

- 5 至 10 张 CORD 公开收据图片，按版本化脚本无损封装为单页 PDF，明确标记为 `deterministic_transform`，只测 OCR；
- 最多 5 份 Kleister NDA PDF，只测长合同解析和字段定位；
- DocILE 只有在数据访问条款、选择性下载和磁盘大小明确后才加入，不能成为 M2-22 完成的硬依赖；
- DocLayNet、DocVQA、DocILE 全量均不下载。

候选入口：

- <https://github.com/clovaai/cord>
- <https://github.com/applicaai/kleister-nda>
- <https://docile.rossum.ai/>

如果外部图片不能通过当前公开文件 API，转换后的 PDF 仅作为有来源记录的评估派生文件；本步不得顺手扩大生产上传格式。

### 5.4 数据量和磁盘硬边界

- 外部原始下载累计不得超过 200 MiB；
- 加工文件和评估 Artifact 持久占用目标不超过 300 MiB；
- PostgreSQL Chunk、向量和索引新增占用目标不超过 600 MiB；
- 临时 OCR/解析缓存运行后必须清理；
- 开始下载前至少确认 3 GiB 可用空间，给解析临时文件和数据库写放大留余量；
- 不把已有模型缓存计入语料大小，也不得因本方案隐式下载新模型；
- 任一实际来源超过清单预算时先停止并回报，不自动扩大磁盘范围。

## 6. 数据治理和防止答案泄漏

外部数据根目录放在 Git 仓库之外或 Git 忽略目录内，逻辑结构建议为：

```text
public-data-root/
├── raw/             # 官方原始文件，只读
├── processed/       # 有版本的格式转换和小样本
├── manifests/       # URL、许可、Hash、大小、访问日期
└── reports/         # 本地评估报告，不默认提交大结果
```

Git 只保存：

- 数据来源和许可证 Manifest；
- 下载、校验、抽样和转换脚本；
- 小型、允许提交的测试夹具；
- Golden 问题、答案要点和公开 locator；
- 评估配置、指标实现和摘要报告。

Git 不保存：

- 未确认再分发权利的第三方原文件；
- 完整公开数据集；
- PostgreSQL 数据目录或 dump；
- `data/storage/`、模型权重、API Key、Cookie、登录 Token；
- 真实用户上传文件。

每个来源至少记录：

```text
source_id
source_title
source_url
publisher
published_at
accessed_at
license_name
license_url
redistribution_allowed
source_format
source_bytes
source_sha256
source_kind
transform_version
processed_sha256
language
business_group
```

问题、答案和知识文件物理分离。知识文件中只能保留原始业务内容，不能把 Golden 问题或标准答案附加进去。测试集在最终验收前不能用于调参。

## 7. 评估集规模和切分

### 7.1 Smoke 集

先建立 40 条 Smoke，用于验证 Runner、数据形状和完整链路，不用于最终宣传：

- 普通文字事实 10 条；
- 表格/公式 8 条；
- OCR/复杂版面 6 条；
- 跨章节或流程 6 条；
- 中英德不同问法 4 条；
- 无答案、ACL、删除/旧版本 6 条。

### 7.2 正式集

RAG 正式集至少 120 条；目标 150 条，由数据质量和人工标注能力决定。最低 120 条建议分布：

- 真实跨境规则和流程直接事实 25 条；
- 业务步骤、条件和例外 20 条；
- Excel/CSV/PDF 表格事实 15 条；
- 跨章节组合 15 条；
- 跨文档组合 10 条；
- OCR/复杂版面 10 条；
- 中文、英文、德文同义问法 10 条；
- 无答案和相似干扰 10 条；
- ACL、软删除、旧 active 版本 5 条。

按业务组和难度分层切为：

- Debug：40 条，允许开发时查看；
- Validation：40 条，只用于选择配置；
- Test：至少 40 条，最终运行前不用于调参。

扩展到 150 条时优先增加真实跨境规则、相似产品和无答案样本，不机械复制简单事实题。

### 7.3 每条用例的最小形状

```text
case_id / dataset_version / split
question / language / category / difficulty
source_group / expected_documents / expected_evidence_spans
answer_key_points / acceptable_variants / forbidden_claims
should_answer / expected_denial_or_unknown_reason
required_user_profile / required_acl_state / required_version_state
```

身份、tenant、roles、market、ACL 和 active 版本由 Runner 可信夹具注入，不能放进模型可控制字段。

## 8. 必须报告的评价指标

### 8.1 文件解析和 OCR

- 支持格式成功/安全拒绝率；
- Golden 事实文本恢复率；
- OCR 关键字段准确率；
- 表格单元格事实恢复率；
- 阅读顺序正确率；
- 页码、标题、Sheet、单元格/行范围 locator 准确率；
- Native/Docling/Hybrid 路由结果；
- 每个文件耗时、峰值内存和失败原因分类。

### 8.2 切块质量

- Answer-contained rate：完整答案是否保留在至少一个 Chunk；
- Evidence-span coverage：Golden 原文范围有多少被 Chunk 覆盖；
- Boundary break rate：规则、句子、表格行被不合理切断的比例；
- Heading retention：标题和所属正文是否留有关系；
- Table-row integrity：表头和数据行是否仍能一起解释；
- Chunk token 的最小值、中位数、p95、最大值；
- 重叠冗余率、每文档 Chunk 数和空/近重复 Chunk 数；
- 各切块配置下的后续 Precision、Recall、Hit Rate、MRR、nDCG、存储量和索引耗时。

### 8.3 检索与排序

Dense、Lexical、RRF、Reranker 四个阶段分别保存完整有序候选。项目评估器以冻结的正确 Evidence ID、文档ID和原文范围计算：

- Precision@1、@3、@5、@8、@10、@20；
- Recall@1、@3、@5、@8、@10、@20；
- Hit Rate@1、@3、@5、@8、@10、@20；
- MRR@10；
- nDCG@5、@10；
- 首个正确 Evidence 的排名；
- 相似 SKU/产品串答率；
- 无答案问题的误召回情况；
- p50/p95/max 延迟和候选数量；
- Reranker 相对 RRF 的升排、降排和无变化数量。

同一批真实候选再映射给 Ragas，报告 Context Precision、Context Recall、Context Relevancy 和 Noise Sensitivity。能够由已冻结的 Evidence ID/参考Context确定的结果优先使用非 LLM 或 ID-based 判断；需要语义判断时才调用固定版本的 Judge。两个来源的分数分栏保存，不混成一个无法解释的总分。

### 8.4 Context、回答与引用

- Context 中 Golden Evidence 覆盖率；
- Context 冗余率和 Token 使用量；
- 答案关键点正确率与完整率；
- Ragas Faithfulness：答案中的事实是否都能由检索上下文支持；
- Ragas Response Relevancy：答案是否直接回应问题而没有明显跑题或无关冗余；
- Ragas Factual Correctness：答案事实是否符合人工参考答案；
- Semantic Similarity/ROUGE-L：只作为辅助观察，不得覆盖关键点、Faithfulness或Citation结论，也不得为此隐式下载新模型；
- Citation precision：引用是否真的支持对应陈述；
- Citation recall：应该引用的关键陈述是否有引用；
- 引用身份/编号/当前授权合法率；
- 无答案拒答率和有答案误拒答率；
- 中文、英文、德文分组结果；
- Qwen 网络耗时、Token 和失败类型；确定性 Fake 与真实 Qwen 分开报告。

自动指标不能单独充当最终结论。规则可确定的字段使用项目自己的确定性比较；自然语言答案使用人工要点匹配与 Ragas，并对固定 Test 和全部低分/争议样本做人工复核。若 Qwen 同时承担生成和 Judge，必须显式标记同模型偏差风险、固定模型/参数/Prompt、重复采样并与人工评分校准，不能让模型自己给自己的回答判定唯一结论。

### 8.5 安全与版本

以下属于零容忍门禁，不计算平均分：

- 跨 tenant、无 ACL、错误 market 不得返回文档或 Evidence；
- 软删除、旧 active、失败索引不得进入结果；
- Prompt 注入文档不得改变身份、权限、预算和 Tool 白名单；
- 输出不得出现绝对路径、Storage Key、SQL、秘密或原始异常；
- Citation ID 必须属于当前获权 Context；
- 评估运行不得污染正式 Seed 或遗留 AgentRun/Context/Evidence。

### 8.6 Ragas 使用边界

- M2-22 的 RAG 阶段只选择 Ragas 作为成熟语义评估框架，不同时引入 DeepEval；
- M2-22.1 的合同必须保持框架无关，但要保存 `evaluator_backend`、Ragas版本、Judge Provider/模型/参数、评审Prompt版本或Hash、重试与失败状态；本步不安装或运行Ragas；
- M2-22.6 才接入 Ragas 检索指标，M2-22.8 才接入生成指标；Parser/OCR和Chunk不交给Ragas代替；
- Ragas只能消费项目真实链路产生的 `question/reference/reference_contexts/retrieved_contexts/response`映射，不能自行绕过公开主链生成一个看似更好的结果；
- Ragas自动生成的题只能进入Debug候选，必须经人工核对原文范围后才能使用；不得进入冻结Test或反向污染知识文件；
- M2-22.9先评估Ragas现有Agent Goal/Tool Call指标是否满足本项目；如不足，必须另行提交方案并获得授权，不能自动引入DeepEval；
- 依赖版本、Judge失败、网络/Token成本和原始评审理由都必须安全记录，原始异常、密钥、绝对路径和未脱敏文档正文不得进入报告。

参考官方能力入口：

- <https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/>
- <https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/context_precision/>
- <https://docs.ragas.io/en/stable/howtos/customizations/customize_models/>

## 9. 切块和 TopK 实验设计

### 9.1 当前生产基线

当前代码配置为：

```text
chunk_target_tokens = 600
chunk_max_tokens = 700
chunk_overlap_tokens = 100
chunk_heading_context_max_tokens = 120
chunk_table_row_overlap = 1
dense_candidate_count = 30
lexical_candidate_count = 30
hybrid_candidate_count = 30
rrf_k = 60
reranker_top_k = 8
context_max_tokens = 4000
context_neighbor_window = 1
```

这些值是工程初始值，不是已经由大规模真实评估证明的最优值。

### 9.2 切块对比

当前不是每700 Token机械切一刀，而是先按标题路径、段落、句子、列表和表格结构组织内容，尽量靠近 `target_tokens`，只把 `max_tokens` 当硬上限；文本携带有界标题上下文和相邻重叠，表格优先保留整行、重复表头并按行重叠。因此实验必须比较完整配置，不能只写一个“Chunk大小”。

第一轮只改变目标/硬上限，其余参数保持一致，避免同时改多个变量后无法解释结果：

| 配置 | target | max | 文本overlap | 标题上下文上限 | 表格行overlap | 目的 |
|---|---:|---:|---:|---:|---:|---|
| compact | 400 | 500 | 100 | 120 | 1 | 看小块是否提高精确召回但丢失完整规则 |
| medium | 500 | 600 | 100 | 120 | 1 | 检查中间折中 |
| current | 600 | 700 | 100 | 120 | 1 | 当前生产基线 |
| large | 700 | 850 | 100 | 120 | 1 | 看长规则和表格是否更完整但噪声更多 |

四组必须使用同一原文件、同一 Golden、同一模型版本。第一轮选出不劣候选后，第二轮只在候选配置上比较文本overlap `80/100/120`；标题上下文和表格行overlap只有在对应Bad Case证明需要时才单独消融。先比较解析后的 Chunk 事实和存储，再比较检索质量与延迟。不能因为某组最终答案偶然更好，就忽略它对表格、定位或索引成本的损害。

### 9.3 TopK 与 RRF 对比

在不修改生产默认值的前提下，评估配置至少覆盖：

- Dense/Lexical/Hybrid 候选深度：10、20、30；
- RRF 常数：20、60、100；
- Reranker 输出：5、8；
- Context 邻块：0、1；
- Context Token 上限：2000、3000、4000。

不做无界笛卡尔积。先用 Validation 集进行逐层筛选：候选深度 → RRF → Reranker TopK → Context；Test 集只运行冻结后的当前基线和最多两个候选配置。真实 Reranker 对最大候选并集评分一次并缓存评估结果，避免同一问题因参数组合重复进行昂贵 CPU 推理；缓存不进入生产链。

选择最终值时同时看：Precision、Recall、Hit Rate、MRR、nDCG、Ragas Context指标、Faithfulness、Response Relevancy、Citation、延迟、Token和内存。M2-22只给出证据支持的建议；如需修改生产配置或合同，必须作为独立变更再次授权。

## 10. 建议质量门禁

以下是运行前冻结的建议验收线，不是当前已经达到的结果：

| 维度 | 建议门禁 |
|---|---|
| 安全、ACL、版本、Citation身份 | 100%，不允许一次越权或伪造 |
| 已选支持文件处理 | 100%成功或以预期安全错误明确拒绝，不能静默缺失 |
| 数字 PDF/DOCX/XLSX/CSV Answer-contained rate | 不低于95% |
| OCR诊断 Answer-contained rate | 不低于80%，并独立报告 |
| 真实跨境核心 Hit Rate@8 | 不低于95% |
| 真实跨境核心 Recall@8 | 不低于90% |
| 真实跨境核心 MRR@10 | 不低于0.75 |
| Ragas Context Precision / Recall | Judge与人工校准后再冻结Test门禁；建议起点为0.80 / 0.90 |
| Citation precision | 不低于95% |
| 回答 Faithfulness | 不低于90% |
| Ragas Response Relevancy | Judge与人工校准后建议不低于0.85 |
| 无答案拒答率 | 不低于90% |
| 合成/真实/诊断分组 | 必须分别报告，不允许用容易的合成题稀释真实失败 |

性能暂不伪造统一生产 SLA。必须记录当前电脑 CPU、内存、模型设备和每层 p50/p95；配置选择不能让质量小幅提升却造成无法接受的本机等待时间。真实 Qwen 网络延迟、本地检索延迟、Ragas Judge延迟与API端到端延迟分开计算。所有Ragas门禁都是运行前建议值，必须先用人工标注校准集验证Judge方向一致，再冻结Test阈值，不能把框架默认阈值冒充业务标准。

## 11. 十一项实施步骤

每一步都先写失败测试并记录 RED，再实现最小 GREEN，运行相邻回归并同步本记录。完成一个小步骤后停止，等待用户理解和下一步授权。

### M2-22.1｜冻结评估合同、来源 Manifest 和磁盘门禁

- 目标：先规定来源、数据分组、用例、运行配置、逐层结果和报告长什么样；合同保持框架无关，同时冻结Evaluator/Ragas/Judge/Prompt身份字段；验证路径、JSON大小、键数量、Hash、许可和200 MiB下载上限；
- 预计文件：`app/schemas/evaluation.py`、`data/evals/m2_cross_border_sources_v1.json`、`tests/unit/test_rag_evaluation_contracts.py`、本记录；
- 验证：多余字段、重复ID、未知分组、答案混入语料、缺许可/Hash、越界路径、超量文件、非法状态全部拒绝；
- 不做：不安装或运行Ragas，不联网下载，不调用模型，不写数据库。

### M2-22.2｜实现受控下载、Hash校验和确定性转换

- 目标：只下载 Manifest 白名单中的已选小文件，原始文件只读；允许把明确许可的少量图片按固定版本封装为PDF；
- 预计文件：`scripts/prepare_m2_cross_border_eval.py`、下载/转换测试、`.gitignore`或配置仅在确有必要时修改；
- 验证：URL白名单、大小预检、SHA-256、重复运行、禁止静默覆盖、断点失败清理、许可记录、磁盘上限；
- 不做：不下载全量数据集、不入库、不修改生产上传格式。

### M2-22.3｜建立40条Smoke并冻结人工Golden

- 目标：用现有10份回归文件和少量真实文件建立第一批分层问题，冻结正确答案要点与原文范围；
- 预计文件：`data/evals/m2_cross_border_rag_smoke_v1.jsonl`、Golden校验测试；
- 验证：问题/答案/知识文件分离，case/source/span唯一，split与类别覆盖，身份由可信夹具提供；
- 不做：不根据模型输出反向改写标准答案。

### M2-22.4｜真实摄取、Parser/OCR和基线恢复

- 目标：让选定原文件经过现有上传、Storage、Parser Router、Canonical Artifact和状态链，记录文本、表格、locator、耗时和内存；
- 预计文件：`app/evals/rag_runner.py`的摄取/解析部分、解析集成测试、报告模板；
- 验证：四格式、真实PDF、可选OCR派生PDF、损坏文件、路由、Golden恢复率、清理与正式Seed恢复；
- 不做：不改Parser或Docling策略。

### M2-22.5｜切块质量矩阵

- 目标：在同一Canonical输入上比较compact/medium/current/large四组完整结构感知配置；第一轮隔离target/max变量，第二轮只对候选比较overlap；
- 预计文件：Runner切块阶段、指标实现、`tests/unit/test_rag_chunk_metrics.py`、真实数据库/Storage集成测试；
- 验证：答案包含率、范围覆盖、边界破坏、标题/表格完整性、重复率、Chunk数量、Token分布、确定性Hash；
- 不做：不新增切块算法、不修改生产默认值。

### M2-22.6｜Dense/Lexical/RRF和TopK评估

- 状态：已完成；Locator修复、10组Chunk/50点确定性检索矩阵、所选配置Ragas补跑、失败分类、清理和回归见第41至42节；
- 目标：逐阶段保存候选和排名，完成候选深度与RRF筛选；项目代码计算Precision/Recall/Hit Rate/MRR/nDCG，Ragas计算Context Precision/Recall/Relevancy和Noise Sensitivity；
- 预计文件：Runner检索阶段、排名指标、Ragas适配层、`tests/unit/test_rag_retrieval_metrics.py`、PostgreSQL/pgvector集成测试；依赖变更只在本步另行授权后发生；
- 验证：确定性排名指标、Ragas输入映射与Judge身份、相似产品串答、无答案噪声、ACL/active过滤、稳定排序、p50/p95及框架失败隔离；
- 不做：不实现自动检索模式路由、不改生产SQL和配置。

### M2-22.7｜Reranker和Context质量/性能评估

- 状态：五步详细方案已提交，等待用户确认；尚未修改或运行评估代码；
- 目标：比较RRF与Reranker，测试Top5/Top8、邻块和Context Token预算；
- 预计文件：Runner重排/Context阶段、缓存合同测试、真实BGE显式评估入口；
- 验证：升排/降排、Recall/MRR/nDCG、Context覆盖/冗余、Token、CPU耗时/内存、缓存身份；
- 不做：不部署GPU服务、不修改Reranker实现或生产配置。

### M2-22.8｜最终RAG回答、引用和拒答评估

- 目标：通过现有知识Tool和公开Gateway验证真实问题到Evidence、Qwen回答和Citation；由项目评估器计算要点/Citation/安全结果，由Ragas计算Faithfulness、Response Relevancy、Factual Correctness和辅助Semantic Similarity；完成RAG阶段复核点；
- 预计文件：Runner回答阶段、Ragas生成指标适配、确定性Fake回归、显式Qwen Smoke、API/集成测试、RAG摘要报告；
- 验证：答案要点、Ragas语义指标、Citation precision/recall、无答案、Prompt注入、多语言、Judge校准/失败、ACL和失败脱敏；
- 停止点：完成后必须先向用户讲清RAG指标和Bad Case，未经单独确认不得进入M2-22.8R意图识别与执行分流。

### M2-22.8R｜意图识别与执行分流改造

- 状态：已确认实施顺序和最小范围，尚未提交详细实施方案，未授权代码开发；
- 前置：M2-22.8完成，用户已理解RAG指标和Bad Case，并对本步完整方案单独确认；
- 目标：在公开消息入口先判断请求的意图和复杂度，并将它与真实执行路径绑定；分流本身不固定新增一次LLM调用，高置信明确请求优先由程序直接分流，只有不确定请求才用一次严格结构化模型输出同时完成意图、路径和业务参数提取；简单单一查询绕过Supervisor，固定复合查询走受控Pipeline，确需规划的复杂任务才进入Supervisor/Worker；
- 预计文件：详细方案中再冻结；候选范围包括意图/路由Schema、路由Service或Gateway接缝、快速路径/固定Pipeline、路由与公开API集成测试、本记录/M2入口/总看板；
- 验证：冻结带期望路径的评估用例；比较路由准确率、任务完成、Tool/Evidence一致性、模型调用数、Token、成本和p50/p95；明确证明简单Business/Knowledge请求不再无条件进入Supervisor。待方案校准的调用目标为：L0分类和直接回答不拆成两次；高置信明确Business查询目标0次模型，不确定Business查询目标最多1次意图+参数调用，结构化Tool结果优先由程序格式化；Knowledge问答只保留路由不确定时的结构化调用和RAG后确实需要的一次有证据回答；固定复合请求通常不超过2次模型调用，工具独立时并行执行；L3由树形预算约束并单独报告；
- 不做：不新增Worker、Tool、Web研究、时间约束、权威性评分、动态通用DAG或M4能力；不只产出意图标签却继续让所有请求走Supervisor；不用无界关键词规则假装理解任意自然语言，低置信时必须进入受控模型路由或安全追问；
- 停止点：改造和对照验证完成后先向用户讲清输入、路由、上下游、成本变化和失败定位；未经单独确认不得进入M2-22.9。

### M2-22.9｜多Agent轨迹评估

- 前置：M2-22.8R已完成并验证，用户已经理解改造结果并单独授权；
- 目标：在RAG质量和最终执行分流已知的前提下，同时评估路由选择、快速路径、固定Pipeline以及Planner、Supervisor、Worker、Tool、预算、并行和恢复；先验证Ragas Agent Goal/Tool Call指标是否足够，不足时另行评审而非自动引入DeepEval；
- 预计文件：`data/evals/m2_agent_v1.jsonl`、Runner Agent阶段、轨迹指标测试和报告；
- 验证：任务完成、Worker选择、委派、Tool参数、重复/无效调用、Evidence交接、澄清恢复、预算终止、G0至G7；
- 不做：不新增Agent、Tool、记忆或调度能力。

### M2-22.10｜正式集、Bad Case和阶段收口

- 目标：扩充到至少120条冻结用例，在未用于调参的Test集运行最多三个配置，输出可复现结论并恢复基线；
- 预计文件：正式JSONL、报告摘要、测试、M2入口、总看板、本记录；
- 验证：分组指标、配置/代码/数据/模型/Ragas/Judge/Prompt身份、失败样本、人工校准、运行资源、重复结果、清理后10份正式Seed和M1库存125恢复；
- 不做：不进入M2-23前端、M2-24最终演示或M5综合作品化。

## 12. 完整调用链位置

### 12.1 分层诊断链

```text
前端：不经过
→ API：真实摄取时经过文件API；纯层级复算时由Runner调用既有Service
→ Schema：文件合同 + 本步评估合同
→ Agent/LangGraph：M2-22.1至.7不经过；M2-22.8只验证现有Knowledge主路径；M2-22.8R改造公开入口的意图与执行分流；.9才评估改造后的完整路由与Agent轨迹
→ Harness：Tool/最终问答阶段经过
→ Tool：最终问答阶段经过现有三个知识Tool，不新增Tool
→ Service：Parser / Chunk / Index / Retrieval / Context / Evidence
→ Repository/Model：复用当前权限、版本、Chunk、Context、Evidence和Run结构
→ PostgreSQL/pgvector/Storage：真实经过
→ 外部Provider：Docling/BGE本地显式运行；Qwen仅显式运行并单独报告
```

### 12.2 最终公开问答链

```text
评估问题
→ POST消息公开API
→ Agent Gateway
→ Supervisor
→ Knowledge Worker
→ Harness
→ search_knowledge / 必要的受控读取Tool
→ Dense + Lexical + RRF + BGE-Reranker
→ Context + Evidence
→ Qwen/Fake Answer
→ Citation Validator
→ 项目确定性评估器与Golden比较
→ Ragas检索/生成语义评估
→ 人工复核固定Test、低分和争议Bad Case
→ 保存分栏结果，不合成不可解释的单一总分
```

## 13. 阶段完成标准

只有以下条件全部满足，M2-22 才能标记为已完成：

1. 现有10份合成文件保持不变并继续通过回归；
2. 外部数据均有来源、许可、版本、大小、Hash和访问日期；
3. 外部原始下载不超过200 MiB，运行后持久数据和临时数据符合磁盘边界；
4. 40条Smoke和至少120条正式用例可重复加载，答案没有泄漏进知识文件；
5. Parser/OCR、Chunk、Dense、Lexical、RRF、Reranker、Context、Answer/Citation均有逐层结果，项目确定性指标与Ragas语义指标分栏保存；
6. 切块四组完整配置、候选TopK、RRF、Reranker TopK和Context预算有真实对比；
7. 真实跨境、合成跨境、通用诊断和安全用例独立报告；
8. 所有安全门禁100%通过，不出现越权、旧版本、删除文档、伪造Citation或敏感信息泄露；
9. 真实BGE/Docling/Qwen与Fake结果明确分开；Ragas、Judge、Prompt及参数版本可追溯，框架或Judge失败不能被记成低分或通过；
10. Bad Case能定位到具体层，不用“模型效果不好”笼统解释；
11. M2-22.8后完成用户复核，再单独提交、确认并实施M2-22.8R；M2-22.8R通过后另行授权，才实施M2-22.9；
12. 运行结束后正式Seed、Storage和数据库基线恢复，进度记录同步；
13. 没有提前实现前端、新Agent、新Tool、长期记忆、生产调参、M2-24、M4或M5。

## 14. 主要风险和排查方向

| 风险 | 影响 | 优先排查方向 |
|---|---|---|
| 第三方许可或版本不清楚 | 无法提交、演示或复现 | 暂停该来源；核对官方页面/许可；Manifest标记不可再分发，必要时只保留URL和Hash |
| 法规随时间更新 | 旧答案被误当成最新结论 | 冻结发布日期/访问日期；回答注明资料版本；不把系统输出当法律意见 |
| 真实PDF解析失败 | 后续检索必然漏答 | 先看Parser事实恢复与路由，再看Chunk，不能先调TopK掩盖上游缺字 |
| OCR慢或临时空间增大 | 本地运行时间长、磁盘不足 | 严格小样本；逐文件记录；及时清理临时图片；不下载全量图片集 |
| 图文DOCX仍漏字 | 复杂组指标下降 | 如实归到已知Parser边界；本步不顺手扩展Office OCR |
| Golden标注错误 | 指标误导调参 | 双重人工核对source/span；Hash绑定；争议样本标记而非强行计分 |
| 合成题过易 | 总分虚高 | 真实/合成分组报告；核心结论以真实跨境组为主 |
| TopK组合过多 | CPU Reranker耗时失控 | 分阶段筛选、最大候选并集一次评分、缓存仅用于评估、Test最多三个配置 |
| Qwen非确定性 | 重复结果波动 | 固定模型/参数；保存运行身份；Fake做回归；真实运行重复采样并报告方差 |
| Ragas Judge偏差或漂移 | 同模型自评、Prompt/版本变化或多语言理解偏差会改变语义分数 | 保存Ragas/Judge/Prompt身份；先与人工校准集比对；确定性指标与语义指标分栏；争议样本人工复核 |
| Ragas网络、Token或依赖故障 | 评估变慢、中断或本地依赖膨胀 | 只在获批步骤安装；限制并发/重试/调用量；记录显式失败；不得把失败当0分或跳过当通过 |
| Runner绕过生产边界 | 指标好但真实API无效 | 层级诊断和公开Gateway端到端两条链都必须运行，结果分开解释 |
| 评估污染正式数据 | 后续演示或回归不可信 | 使用固定评估身份/ID和精确清理；运行前后核对10份Seed、Storage和M1库存125 |
| 在分流改造前先评估Agent轨迹 | 报告只代表即将被替换的旧主路径，改造后必须重跑 | 严格保持M2-22.8 RAG复核 → M2-22.8R意图/分流 → M2-22.9最终轨迹的顺序 |

## 15. 当前方案记录结果

2026-09-07，用户在确认现有10份文件内容过少后，授权生成本方案；随后确认按“项目确定性评估 + Ragas语义评估 + 人工复核”修订，并纠正把结构感知切块简写成单一最大Token的表达。本次仍只完成文档方案：

- 没有下载欧盟、德国、Safety Gate、CORD、Kleister或DocILE数据；
- 没有创建 `app/evals`、评估Schema、Runner或JSONL用例；
- 没有修改Parser、Chunk、TopK、RRF、Reranker、Context、Agent或生产配置；
- 没有写入PostgreSQL、pgvector或Storage；
- 没有运行M2-22测试，也没有产生任何质量分数；
- 没有安装或运行Ragas，也没有引入DeepEval；
- 该方案记录形成时的下一动作是用户单独授权M2-22.1；后续实际实施与当前停止点以本文最后一节为准，前一步授权不自动包含后续步骤。

## 16. 2026-09-07｜M2-22.1 评估合同、来源 Manifest 和磁盘门禁

### 16.1 用户确认与本步边界

用户正式确认并授权开始 M2-22.1，并明确只完成这一小步，不继续 grill-me 访谈、不创建访谈记录，也不得提前实现 M2-22.2 或任何后续步骤。本步因此只冻结评估数据形状、候选来源账本、稳定序列化与纯计算磁盘预检；没有实现下载脚本、Smoke/正式 JSONL、Runner、Ragas 适配、指标计算、数据库或真实 RAG 运行。

### 16.2 本步目标和大白话运行过程

本步解决“后续评估各说各话、未下载资料可能被误写成已验证、失败可能被记成零分”的问题。运行过程是：

```text
候选来源或评估配置
→ 严格 Pydantic Schema 拒绝多余字段、矛盾状态和越界值
→ 规范化 JSON 使用稳定键顺序和 UTF-8 字节
→ 得到可重复的 SHA-256
→ 后续步骤只能引用已经冻结的数据、代码、模型和配置身份
```

磁盘门禁只接收调用者提供的字节数并做确定性比较，不读取磁盘、不清理文件，也不连接数据库。已有模型缓存单独记录且明确排除在评估语料之外，合同同时禁止隐式模型下载。

### 16.3 修改文件与职责

- `app/schemas/evaluation.py`：新增框架无关的来源、Manifest、Golden 用例、完整 Chunk 配置、检索/Context 配置、组件与 Evaluator 身份、分层结果、项目确定性指标、Ragas 语义指标、运行身份、规范化序列化/Hash 和磁盘预检合同；所有结构继承现有 `M1Schema`，默认拒绝多余字段；
- `data/evals/m2_cross_border_sources_v1.json`：登记 11 个方案已选候选来源，其中 8 个欧盟/德国跨境核心候选、3 个 CORD/Kleister/DocILE 非核心诊断候选；全部保持 `planned + pending_review + download_allowed=false`，实际大小、Hash、路径、转换和版本字段为空；累计最大下载预算 180 MiB；
- `tests/unit/test_rag_evaluation_contracts.py`：新增 79 项合同正反例和已登记 Manifest 验证；
- `app/schemas/__init__.py`：未修改。评估合同当前由内部评估代码按精确模块导入，没有必要扩大现有 API 公共聚合导出；
- 本记录、M2 入口与总进度看板：同步实际完成状态、验证证据和下一停止点。

### 16.4 冻结的关键合同

1. 来源分组固定为合成工程回归、真实跨境核心、复杂文档诊断、安全/ACL/版本四组；只有真实跨境核心来源可以进入核心分数。
2. 来源生命周期固定为 `planned/downloaded/verified/rejected`：`planned` 不得带实际大小、Hash 或路径；`downloaded` 必须有实际字节、原始 Hash 和安全相对路径；`verified` 还必须有来源版本、处理后 Hash/路径及确定性转换身份；`rejected` 必须有脱敏原因且不能保留被接受的下载观测。
3. 许可固定区分待核查、允许再分发、允许下载但不可再分发和禁止使用；待核查或禁止状态不能声称允许下载，允许状态必须带已核查的许可名称和 HTTPS 地址。
4. Golden 用例只保存可信 Fixture ID，不允许直接注入 user、tenant、roles、market、ACL、Storage Key 或真实预算；可回答与拒答状态必须和 Evidence、答案要点及原因一致。
5. Chunk 合同保存 target/max、文本 overlap、标题上下文、表格行 overlap、重复表头、隐藏 Sheet、Normalization、Chunker 和 Token Counter 完整身份；冻结 compact 400/500、medium 500/600、current 600/700、large 700/850，首轮其余值保持 100/120/1。
6. 检索合同保存 Dense/Lexical/Hybrid、RRF、Reranker TopK、Context 邻块/Token、BGE-M3/BGE-Reranker 模型版本、语言、数据和配置版本，并拒绝 TopK 大于候选数量等矛盾。
7. 项目确定性结果与 Ragas 语义结果使用两个不同 Schema 分栏；正常零分使用 `completed + 0.0`，框架失败、Judge 失败和跳过都不得携带数值，也不能伪装成通过。
8. 运行身份绑定来源 Manifest/Data Hash、代码 revision/dirty 状态、Parser/OCR、完整 Chunk 与检索配置、回答模型及 Evaluator/Ragas/Judge/Prompt/重试身份；不保存 Judge 思维链、原始异常、SQL、密钥、绝对路径或文档全文。
9. 磁盘合同按字节冻结外部原始 200 MiB 硬上限、加工/Artifact 300 MiB 目标上限、PostgreSQL/向量/索引 600 MiB 目标上限和处理前 3 GiB 最低可用空间；负数、错误单位、64 位整数越界和缺失可用空间都安全失败。

### 16.5 RED 与 GREEN 证据

RED：

- 命令：`.venv\\Scripts\\python.exe -m pytest tests/unit/test_rag_evaluation_contracts.py -q`
- 结果：测试收集失败，`1 error`；明确原因是 `ModuleNotFoundError: No module named 'app.schemas.evaluation'`；
- 能证明：测试先于实现存在，并准确暴露“评估合同模块尚不存在”；不能证明任何合同已经正确。

第一次 GREEN：

- 结果：`76 passed, 1 failed`；唯一失败是 `verified` 缺处理后 Hash 时先被通用“处理字段不完整”捕获，错误类别不够贴近生命周期；
- 最小修复：只调整校验顺序，让 `verified` 状态自己报告版本、大小、路径、Hash 和转换身份不完整，没有放宽任何字段规则。

最终聚焦 GREEN：

- `tests/unit/test_rag_evaluation_contracts.py`：`79 passed in 1.72s`；
- 指定相邻五个测试文件：`57 passed in 6.86s`；
- 聚焦与相邻合并：`136 passed in 7.16s`；
- 完整单元测试：`931 passed, 2 skipped in 43.32s`。

工程检查：

- `ruff check app tests scripts migrations`：通过；
- 本步两个 Python 文件格式检查：通过，`2 files already formatted`；
- 全范围 `ruff format --check app tests scripts migrations`：318 个文件格式正确，仍只报告本步未修改的 `tests/integration/test_document_chunk_set_migration.py` 一处既有换行差异；未越界改写；
- `mypy app`：`Success: no issues found in 151 source files`；
- `compileall -q app`：通过；
- `git diff --check`：通过，仅提示两份用户原有进度文档未来可能进行 LF/CRLF 转换，没有空白错误。

### 16.6 完整调用链位置

```text
前端：不经过
→ API：不修改、不调用
→ Schema：本步核心，冻结评估合同与稳定序列化
→ Agent/LangGraph：不经过
→ Harness：不运行、不修改
→ Tool：不调用、不修改
→ Service：未新增 Runner；只有 Schema 模块内的纯计算磁盘预检
→ Repository/Model：不经过
→ PostgreSQL/pgvector：不连接、不写入
→ Storage：不读取、不写入、不清理
→ 外部 Provider：不调用
→ 互联网：不访问
→ Ragas：不安装、不导入、不运行
→ 评估数据：只新增 planned 来源 Manifest，没有 Smoke 或正式用例
```

### 16.7 能证明与不能证明

能证明：合同能拒绝已覆盖的非法枚举、多余字段、重复 ID、生命周期/许可矛盾、假或畸形 Hash、危险路径、Golden/可信上下文注入、预算超限、配置关系错误、指标来源混淆、失败伪零分、非法数值和磁盘门禁错误；同一合法输入可以稳定 JSON 序列化并得到相同 Hash；现有 M1/M2 Schema、Context 和结构感知切块单元回归未被破坏。

不能证明：候选网页仍然在线、许可最终允许下载、真实文件大小与 Hash、文件可解析、OCR/Chunk/检索/Reranker/Context/回答质量、Ragas Judge 可靠性、数据库/Storage 集成、真实 Qwen/BGE 性能或任何 M2-22 质量分数。本步没有运行 integration 测试，因为没有 Repository、数据库、Storage 或外部组件行为变化。

### 16.8 风险、排查方向与下一停止点

- 若后续来源无法进入下载，先看 `license_status/download_allowed`，再核对官方许可和实际下载页，不伪造 Hash 绕过；
- 若 Manifest 无法加载，先看来源生命周期所需字段是否完整，再看安全 URL/相对路径和累计 200 MiB 预算；
- 若后续配置无法加载，先检查 Chunk 的 target/max/overlap 关系和 Reranker TopK 与候选数量；
- 若结果无法保存，先检查 `completed/failed/skipped` 是否与数值及安全失败分类矛盾，再检查序列化大小和敏感字段；
- 300 MiB 与 600 MiB 当前按方案作为预检目标门禁冻结，真实磁盘占用和写放大仍需后续获批步骤用实际数据验证；
- M2-22.1完成时在此停止，当时的下一动作是等待用户单独授权 M2-22.2；该授权和后续实施结果现已记录在第17节。

## 17. 2026-09-07｜M2-22.2 受控下载、Hash校验和确定性转换

### 17.1 用户确认与本步边界

用户明确授权开始 M2-22.2。本步只把 M2-22.1 的来源合同变成可执行的受控准备链，并实际准备首批 8 份欧盟官方小型 PDF；没有创建 M2-22.3 的 40 条 Smoke 或人工 Golden，没有实现评估 Runner，没有写 PostgreSQL/pgvector/Storage，没有运行 Parser、Chunk、检索、Reranker、Agent 或 Ragas，也没有修改任何生产参数。

### 17.2 本步解决的问题和大白话运行过程

M2-22.1 只有“来源账本”，尚不能安全取得真实文件。本步补齐的能力是：用户只给来源 ID，脚本自己从 Manifest 找固定 URL；许可、版本、空间、格式和预算任一不满足就拒绝；下载时边读边计数和计算 Hash，先写 `.part` 临时文件，全部通过才改成正式文件；原始文件设为只读，再生成带固定转换版本的 processed 文件并把真实观测写回 Manifest。

```text
用户显式给 source_id + --allow-download
→ 严格加载 Manifest，source_id 只能命中白名单
→ 核对 license_status / download_allowed / source_version / 文件格式
→ 核对 200/300 MiB门禁和至少3 GiB可用空间
→ HTTPS GET且禁止自动重定向
→ 先验Content-Length，再按流式实际字节二次限流
→ Content-Type + 文件Magic签名
→ 临时文件流式SHA-256 + 落盘重读SHA-256
→ 原件只读
→ PDF等作确定性identity_copy；合规PNG/JPEG可固定封装PDF
→ 原子写回大小、Hash、相对路径和转换身份
```

Git 忽略 `data/evals/runtime/`。因此仓库提交的是可复核的 URL、许可、版本、预算、Hash 和脚本，不提交默认不可再分发的 PDF。全新环境缺少这些本地文件时，脚本允许显式重新下载，但必须与已固定大小和 Hash 完全一致；上游内容漂移会安全失败。

### 17.3 来源与许可核查结果

- 欧盟委员会官方 Legal Notice 说明：除非另有标注，其拥有的网站内容适用 CC BY 4.0；第三方内容、商标等权利不自动包含。核查入口：<https://commission.europa.eu/legal-notice_en>。
- VAT 官方 Guides 页明确列出 2026-07-24 修订 Explanatory Notes、OSS Guidelines 和 2026-08-24 Addendum 的发布日期、语言、格式和下载入口：<https://vat-one-stop-shop.ec.europa.eu/guides_en>。
- UCC 官方 Guidance 页明确列出低价值包裹指南和 Returns 文件，并说明这些指南为解释性、非约束材料：<https://taxation-customs.ec.europa.eu/customs/union-customs-code/ucc-guidance-documents_en>。
- Safety Gate 2024 年报正文自身带 CC BY 4.0 再使用声明，但其旧下载主机在本次真实运行中跳转到临时维护页。下载器正确拒绝重定向；本步改选同一欧盟官方发布链上的 2025 Safety Gate 年报新闻 PDF，不绕过门禁。
- 为避免误分发可能包含第三方图片或标识的内容，8 份核心文件统一保守记录为 `allowed_no_redistribution`：允许本地下载评估，但原文件不进 Git。德国 LUCID 候选没有在本次核查中得到足够明确的可复核再使用依据，因此没有强行下载或伪造许可状态。
- CORD、DocILE、Kleister 三个全量/仓库级诊断候选仍为 `planned + pending_review + download_allowed=false`，没有下载；图片转 PDF 能力只用 2×2 测试图片验证，没有借此下载真实全量图片集。

### 17.4 修改文件与职责

- `scripts/prepare_m2_cross_border_eval.py`：新增唯一准备入口；负责 Manifest 白名单、许可/版本/格式门禁、目录约束、磁盘预检、禁止重定向、流式限流、Content-Type/Magic 校验、双重 Hash、只读原件、确定性转换、原子 Manifest 更新、离线幂等复核和已固定来源重建。
- `tests/unit/test_m2_cross_border_eval_preparation.py`：新增 12 项下载/转换正反例，覆盖显式授权、非白名单、许可、空间、Content-Length、流式超限、连接中断、重定向、伪装文件、Hash、只读、重复运行、静默覆盖、重建漂移、目录边界和图片确定性。
- `data/evals/m2_cross_border_sources_v1.json`：把 8 个核心候选替换为本次实际选定的精确 PDF，记录已核查许可、固定版本、真实大小、raw/processed SHA-256、安全相对路径及`identity_copy@m2-eval-transform-v1`；3 个诊断候选继续 planned；总来源预算从 180 MiB 收紧到 59 MiB。
- `.gitignore`：忽略 `data/evals/runtime/`，避免本地原件和派生文件误提交。
- `tests/unit/test_rag_evaluation_contracts.py`：把已登记 Manifest 断言从“11 个全部 planned”同步为“8 个核心 verified + 3 个非核心诊断 planned”，继续验证许可与生命周期不矛盾。
- 本记录、M2 阶段入口和总进度看板：同步实际状态、验证证据、边界和下一停止点。

### 17.5 真实文件证据

| source_id | 大小（字节） | 页数 | 可提取字符 | SHA-256（raw = processed） |
|---|---:|---:|---:|---|
| `eu-vat-explanatory-notes-2026-en` | 1,174,116 | 105 | 275,399 | `9c4b7bbe3b83e76731117cb6a6f47d31782502f55db76a32f2b75eb182e87b6f` |
| `eu-vat-oss-guidelines-2026-en` | 567,087 | 63 | 143,562 | `3a0a000a6fd853855defa6e88e65c9e8f10f669d9fce752db17e8f184e0ce385` |
| `eu-vat-customs-duty-addendum-2026-en` | 65,281 | 2 | 3,991 | `5185da1717f45e3b9f8c9f174b0f31bdbbeb420333a451d9bdec8e20d090dc1b` |
| `eu-low-value-consignments-2022-en` | 1,839,089 | 74 | 171,197 | `74f905912878c013dcc1dffb9a2dee51d979ed67ed4aa79fd17071fd9fc0376f` |
| `eu-low-value-returns-2022-en` | 689,460 | 24 | 54,644 | `911bbbc0352492b30234641db27ee8c4799de3ca5fac2ee588bc26508dd9a320` |
| `eu-gpsr-factsheet-2023-en` | 574,020 | 3 | 5,550 | `64bae9c868ec45d92bedfdecb4c54cbd1b88b01abc404469c32425d8b0546899` |
| `eu-safety-gate-report-2025-press-release-en` | 49,052 | 2 | 6,203 | `4441fc0555f438e02e2d8f6670f94b543c4f96f55e84b2fbcfc3ecb0350e1ef5` |
| `eu-safety-gate-alert-10001641-en` | 194,316 | 2 | 1,071 | `6c9c33806b0e194dfa8080250e9d661b2f743782086f0101cb251a9a663b2cc7` |

合计：raw 8 文件、`5,152,421` 字节；processed 8 文件、`5,152,421` 字节；275 页。8 份均能由独立 PDF 库打开、未加密且存在可提取文本。目录中 `.part` 文件数量为 0；`git check-ignore`确认真实文件由`data/evals/runtime/`规则忽略；原始文件在 Windows 上均具有 ReadOnly 属性。

### 17.6 RED、GREEN和工程验证

RED：

- 首次运行 `tests/unit/test_m2_cross_border_eval_preparation.py` 时测试收集失败，明确为 `ModuleNotFoundError: No module named 'scripts.prepare_m2_cross_border_eval'`，证明测试先于实现存在。
- 最小脚本出现后，首轮为 `5 passed, 4 failed`；失败暴露 Fake 流接口适配、超限/签名错误被过度归类和成功路径问题。修正流式接缝后为`9 passed`。
- 增加“已固定 Manifest 在新环境重建”测试时得到 `10 passed, 1 failed`；失败原因是旧实现把缺失的Git忽略文件直接当冲突。最小修复后，重建必须重新匹配固定大小、raw Hash、processed Hash和转换版本。

最终 GREEN：

- 下载/转换测试：`12 passed`；
- 下载合同 + M2-22.1评估合同：`91 passed in 2.57s`；
- 完整单元：`943 passed, 2 skipped in 38.50s`。

工程与真实文件验证：

- `ruff check app tests scripts migrations`：通过；
- 本步 3 个 Python 文件 `ruff format` 后复核：通过；
- `mypy app`：`Success: no issues found in 151 source files`；
- `compileall -q app scripts tests/unit/test_m2_cross_border_eval_preparation.py`：通过；
- `pip check`：`No broken requirements found`；
- `git diff --check`：通过，仅有现存 LF/CRLF 提示；
- 全范围 `ruff format --check app tests scripts migrations`：320 个文件格式正确，仍只报告本步未修改的 `tests/integration/test_document_chunk_set_migration.py` 一处既有格式差异；
- 8 个 source ID 不带 `--allow-download` 复跑全部返回 `reused=true`，大小和两份 Hash 与 Manifest 一致，证明本地幂等路径没有再次依赖网络；
- 独立 PDF 结构复核得到上表的页数与文本字符。该检查只是确认下载物可打开和非空，不冒充项目 Parser 质量评估。

本步没有 Repository、数据库、Storage、迁移或生产服务变化，因此没有运行 integration 套件；真实外部行为已由 8 次受控 HTTPS 下载、一次预期的重定向拒绝和离线复跑验证。

### 17.7 完整调用链位置

```text
前端：不经过
→ API：不修改、不调用
→ Schema：复用M2-22.1来源生命周期、许可和磁盘合同
→ Agent/LangGraph：不经过
→ Harness：不经过
→ Tool：不经过；脚本不是Agent Tool
→ Service：不修改生产Service；本步是离线评估数据准备脚本
→ Repository/Model：不经过
→ PostgreSQL/pgvector：不连接、不写入
→ Storage：不经过生产Storage；只写Git忽略的评估raw/processed目录
→ 外部Provider：不调用模型或搜索Provider
→ 互联网：只访问Manifest固定的8个欧盟官方HTTPS文件URL
→ Ragas：不安装、不导入、不运行
→ 评估数据：只有来源文件和Manifest，没有问题、答案、Golden或分数
```

### 17.8 能证明、不能证明、排查方向与下一停止点

能证明：只有Manifest白名单中的已审核小文件能进入下载；预算同时约束声明大小和实际流；断流、伪装内容、维护页重定向、目录越界、旧文件冲突和上游Hash漂移不会被静默接受；8份真实PDF的字节、Hash、路径、版本、许可和转换身份可追溯；普通PDF处理完全确定；合规图片封装在相同输入和版本下产生相同PDF字节；本地复跑幂等且全新环境可按固定Hash重建。

不能证明：这些资料的人工问题和答案是否正确、项目 Parser/OCR 是否恢复全部事实、Chunk 边界是否合理、BGE/pgvector 检索和Reranker是否召回、Context/Citation/回答是否忠实、权限链是否在评估运行中正确、Ragas Judge是否可靠或任何M2-22质量分数。资料只用于版本化工程评估，不构成最新法律意见。

优先排查：

- `license`错误：先看Manifest的`license_status/download_allowed/license_url`，不通过命令行绕过；
- `redirect`错误：人工核查目标仍是官方精确文件后再更新Manifest，绝不自动跟随到维护页或第三方站点；
- `declared/streamed size`错误：核对上游文件是否更新及单来源预算，不自动放大；
- `pinned SHA-256`或`existing file conflict`：先判断本地文件损坏还是官方版本漂移，保留证据并人工决定是否建立新source version；
- `disk preflight`错误：核对可用空间及raw/processed目录实际占用，不删除用户文件或模型缓存；
- 图片转换错误：核对图片Magic、尺寸和ReportLab/Pillow环境；本步不扩大生产上传格式。

当时停止。下一动作是等待用户理解并单独授权 M2-22.3；不得提前创建40条Smoke/人工Golden、实现Runner、摄取数据库/Storage、安装Ragas、运行RAG、修改生产参数或进入后续步骤。该授权后来已于2026-09-08获得，完成情况见第18节。

## 18. M2-22.3 实施记录：40条Smoke与人工Golden（2026-09-08）

### 18.1 授权、目标和边界

用户明确授权开始 M2-22.3。本步只把既有10份合成回归文档和M2-22.2已经验证的8份欧盟官方PDF变成第一批可人工检查的40条Debug Smoke，冻结问题、答案要点、拒答理由、文档ID、原文范围和可信身份夹具。没有实现M2-22.4 Runner，没有摄取数据库或Storage，没有运行项目Parser/OCR、Chunk、检索、Reranker、Agent或Ragas，也没有修改生产参数。

Golden（人工金标准）在本步指“人工从指定原文件核对并冻结的答案要点与证据位置”，不是模型回答，也不根据后续模型输出反向改写。

### 18.2 输入、输出和分层结果

输入：

- `m2-v1`与`m2-complex-v1`共10份合成回归文档及其20条既有事实；
- `m2-cross-border-sources-v1`中8份已验证欧盟官方PDF；
- M2-22.1的`EvaluationCase`、`ExpectedEvidenceSpan`与`EvaluationDataset`严格合同。

输出是`data/evals/m2_cross_border_rag_smoke_v1.jsonl`，共40行，每行一条严格`EvaluationCase`，全部属于`debug` split：

| 类别 | 数量 | 主要目的 |
|---|---:|---|
| `ordinary_fact` | 10 | 普通文本直接事实 |
| `table_formula` | 8 | CSV/XLSX/复杂表格与公式 |
| `ocr_complex_layout` | 6 | 扫描PDF、双栏和图文DOCX |
| `cross_section_process` | 6 | IOSS/OSS、关税、退货和H7流程条件 |
| `multilingual_query` | 4 | 中文、英文和德文提问命中英文证据 |
| `safety_non_answer` | 6 | ACL拒绝2、版本不可用2、无证据1、未知金额1 |

其中34条可回答，必须同时具备文档、原文范围和答案要点；6条不可回答，禁止携带答案材料并必须声明明确拒答原因。来源构成为20条合成工程回归、14条真实资料可回答题和6条拒答题。原始JSONL字节Hash冻结为`1d22afa22c5752463189827dba86502f8bc1d06ab7d70403cb0af463c5c4c46b`，任何无意改题都会使测试失败。

### 18.3 来源元数据校正

人工核对Safety Gate PDF正文时确认：文件内容是告警`A12/01039/20`，PDF页脚`07/09/2026`是本次API导出日期，不是告警发布日期。此前Manifest把API结果元数据误写成`published_on=2026-04-27`和对应版本标签，该结论在Golden冻结前已失效，因此本步按进度规则同步更正：

- `published_on`改为`null`，因为现有文件不足以可靠证明原告警发布日期；
- 名称明确为`Safety Gate alert A12/01039/20 (export 10001641)`；
- 版本明确为`alert-a12-01039-20-export-2026-09-07`。

原始文件、大小和SHA-256没有变化；这只是纠正来源身份，不新增下载或运行能力。

### 18.4 TDD与实际验证

RED：先新增`tests/unit/test_m2_cross_border_eval_smoke_dataset.py`，在数据文件不存在时运行，5项全部按预期失败，失败原因为`FileNotFoundError`，证明测试确实先约束了待实现数据集。

GREEN与回归：

- Smoke专项：`5 passed in 1.83s`；覆盖40条严格反序列化、类别数量、34/6回答边界、固定Hash、问题/答案/来源分离、10份合成文档与8份已验证来源映射、合成DOCX字符范围、可信用户/ACL/版本夹具及6条拒答分布，并用PyMuPDF逐条确认外部Golden原文确实位于声明页；
- M2-22相邻回归：`96 passed in 4.02s`；M2-22.1合同、M2-22.2准备链和本步数据集同时通过；
- 新测试`ruff check`通过，`ruff format`完成；最初只发现导入排序和两处换行格式差异，不是业务逻辑失败；
- 完整单元回归：`948 passed, 2 skipped in 42.27s`；
- `git diff --check`退出码0，仅显示工作区既有LF/CRLF提示。

### 18.5 修改文件与职责

- `data/evals/m2_cross_border_rag_smoke_v1.jsonl`：40条人工Golden的唯一机器可读数据文件；
- `tests/unit/test_m2_cross_border_eval_smoke_dataset.py`：验证数据合同、数量分层、Hash、来源/文档/夹具引用及官方PDF页内原文；若忽略的M2-22.2运行时PDF不在新检出环境，只跳过实际PDF页匹配，其余合同和映射仍运行；
- `data/evals/m2_cross_border_sources_v1.json`：纠正Safety Gate告警身份与导出版本；
- 本记录、`docs/progress/M2/M2_KNOWLEDGE_RAG.md`和`docs/PROJECT_PROGRESS.md`：同步本步状态、证据、风险和下一授权门。

### 18.6 完整调用链位置

```text
前端：不经过
→ API：不修改、不调用
→ Schema：复用M2-22.1 EvaluationCase/Evidence/Dataset合同并实际校验40条JSONL
→ Agent/LangGraph：不经过
→ Harness：不运行；只冻结未来Runner会引用的可信身份/ACL/版本夹具ID
→ Tool：不经过
→ Service：不修改、不调用
→ Repository/Model：不经过
→ PostgreSQL/pgvector：不连接、不写入
→ Storage：不经过生产Storage
→ 外部Provider：不调用模型、搜索或Judge Provider
→ 互联网：不访问；只读取M2-22.2已下载的本地官方PDF
→ Ragas：不安装、不导入、不运行
→ 评估数据：40条Debug Smoke与人工Golden已冻结，但尚未进入真实RAG链
```

### 18.7 能证明、不能证明和排查方向

能证明：40条用例能被严格合同读取；数量和六类分层不会无意漂移；可回答题具有人工答案要点和可定位证据；拒答题明确区分ACL、版本、无证据和未知；每个文档/来源/身份夹具都来自受控注册表；本地8份官方PDF中的外部原文与声明页逐条匹配；数据字节可用固定Hash复核。

不能证明：项目真实上传和Parser/OCR是否能恢复这些文本，DOCX字符位置如何映射为Canonical Artifact，Chunk是否保留答案，BGE/pgvector和Reranker是否召回，Qwen回答与Citation是否正确，运行时ACL/版本过滤是否生效，Ragas指标或任何真实质量分数。非答案题中的夹具ID现在只是冻结引用，M2-22.4才会把它们映射到真实测试身份和版本状态。

优先排查：

- JSONL合同或Hash失败：先检查是否无意改题、改答案、改换行或混入额外字段；有意修订必须重新人工核对并显式更新数据版本/Hash；
- 来源或文档映射失败：先核对两个Seed Manifest和`m2_cross_border_sources_v1.json`，不得临时伪造数据库ID；
- PDF页原文失败：先判断M2-22.2运行时文件缺失、Hash漂移还是文本抽取变化，再决定重建或建立新来源版本；
- 后续答案失败：先按Parser/OCR→Chunk→Retrieval→Reranker→Context→Answer/Citation逐层定位，不直接修改Golden迎合模型。

本节当时停止等待M2-22.4真实摄取、Parser/OCR和基线恢复；该步后来已按第19节完成。当前边界以本文最后一节为准。

## 19. M2-22.4 实施记录：真实摄取、Parser/OCR和基线恢复（2026-09-08）

### 19.1 授权、目标和边界

用户明确授权开始M2-22.4。本步只让10份合成回归文件和8份已验证欧盟官方PDF经过现有公开上传API、文档登记、LocalStorage、PostgreSQL状态链、Parser Router、Native/Docling与Canonical Artifact，并计算严格Golden原文恢复、耗时、进程峰值内存和清理结果。没有运行Chunk、Embedding、pgvector检索、RRF、Reranker、Context、Agent、Qwen或Ragas，也没有开始M2-22.5。

Runner按Fixture注册表在隔离临时租户中物化6个测试用户及其真实角色/市场范围，由其中的公司Owner执行公开上传与建文档；ACL和版本Fixture在本步只保留可信映射，后续安全层获批前不伪造拒答测试。Parser没有公开的“只解析不索引”API，因此文档登记后由Runner以可信`CurrentUser`调用既有`DocumentParserService.parse_version`，没有调用会继续切块/索引的`/index`端点。运行结束后按本次租户和精确Storage key删除评估行与对象，再核对正式Seed基线。

### 19.2 实现与接缝修复

- `app/evals/rag_runner.py`：新增可信用户/ACL/版本Fixture注册表、冻结Evidence与Canonical Artifact的严格恢复判定、报告Schema、来源加载和Hash复核、公开上传/建文档、Parser调用、Artifact读回、逐文件耗时与RSS采样、分组聚合、畸形PDF探针、精确清理、正式基线核对和显式`--enable-docling`离线CLI。恢复只匹配`expected_evidence_spans.exact_text`，不会拿答案变体或模型输出放宽标准。
- `app/evals/__init__.py`：建立离线有界评估包边界。
- `data/evals/m2_cross_border_parser_report_template_v1.json`：提交不含运行数据的严格planned报告模板；实际报告位于Git忽略的`data/evals/runtime/reports/m2_cross_border_parser_report_v1.json`，避免把本地运行目录和不可再分发的原文件一并提交。
- `tests/unit/test_m2_rag_parser_runner.py`：覆盖40条Smoke引用的6个用户、6个ACL和3个版本Fixture、文本/表格/公式恢复、禁止用答案变体冒充Golden命中、报告脱敏及禁止未完成运行虚报`completed`。
- `tests/integration/test_m2_rag_parser_runner.py`：用真实PostgreSQL、临时Storage和公开API跑PDF/DOCX/XLSX/CSV四格式，验证Native解析、8条Golden恢复、畸形PDF拒绝、隔离数据清理与正式Seed不变。
- `app/services/files.py`：真实集成首先发现上传层把Office ZIP展开倍率硬编码为20，而项目自己生成的两份合法DOCX分别为21.23和21.29，导致正式Seed无法经过自己的公开上传入口。最小修复把倍率对齐现有DOCX/XLSX Parser的200倍上限，同时新增100 MiB绝对解压上限；成员数、必需成员、加密、文件大小、MIME和Magic门禁仍保留。该修复只消除摄取接缝的误拒绝，没有改变Parser/Docling路由或质量策略。

### 19.3 TDD RED与GREEN

RED按两层保存：

1. 先新增Runner单元合同，首次收集因`ModuleNotFoundError: No module named 'app.evals'`失败，证明评估包和报告能力尚不存在；
2. 再新增真实集成测试，首次收集因`ImportError: cannot import name 'run_m2_parser_evaluation'`失败，证明缺少真实摄取编排；
3. 最小实现后的首轮真实四格式报告为3份成功、DOCX上传被拒，准确暴露21.23倍合法Office包超过20倍上传常量的生产接缝；对齐已有安全边界后同一测试转绿；
4. 新增“completed不能虚报”测试时先得到`DID NOT RAISE ValidationError`，补上报告时间戳、文档、聚合、畸形输入和基线一致性校验后转绿。

最终聚焦Runner为`6 passed in 13.81s`。完整后端`tests/unit tests/integration`为`1229 passed, 4 skipped, 1 failed in 269.64s`；唯一失败仍是既有`test_parse_failure_marks_first_index_failed_without_creating_index_set`把待删除上传Key写死为`2026/08`，当前真实上传位于`2026/09`，所以没有制造出预期解析失败。本步未把该范围外时间依赖失败伪装成通过，也未越权修改。

工程检查：全范围Ruff通过；本步4个代码/测试文件格式正确；`mypy app`为153个源码文件通过；`compileall`无错误；`pip check`无损坏依赖；`git diff --check`退出码0，仅有现存LF/CRLF提示；Alembic current/heads均为`20260905_0011 (head)`且`alembic check`无新操作，本步不需要迁移。

### 19.4 18文档真实运行结果

显式命令为`.venv\Scripts\python.exe -m app.evals.rag_runner --enable-docling`。Docling/RapidOCR只从`data/model-cache/docling`读取本地ONNX和固定模型缓存，CPU运行，远程服务和外部插件保持关闭，没有下载模型。最终报告严格反序列化成功，`run_status=completed`表示18份摄取和解析均完成且清理成功，不表示质量分数达到某个尚未定义的阈值。

| 指标 | 实测结果 |
|---|---:|
| 文档 / 上传接受 / 解析完成 / 解析失败 | 18 / 18 / 18 / 0 |
| 路由 | Native 5 / Docling 11 / Hybrid 2 |
| Parser事实恢复 | 22 / 34 = 64.71% |
| 合成工程回归组 | 18 / 20 = 90.00% |
| 真实跨境核心组 | 4 / 14 = 28.57% |
| OCR字段准确率 | 2 / 4 = 50.00% |
| 解析延迟p50 / p95 / max | 6,464 / 136,479 / 136,479 ms |
| 进程峰值RSS | 2,721,058,816 bytes（约2.53 GiB） |
| 畸形PDF | 上传边界422拒绝 |

6条安全拒答题不进入Parser事实恢复分母，因为本层只回答“可回答Golden原文是否进入Canonical Artifact”；ACL、版本、无证据和未知拒答必须留到后续获批的安全检索/问答层真实验证，不能在Parser层冒充安全通过。

缺失集中在12条：图文DOCX的2条Office视觉文字均未进入Hybrid选择的Native Artifact；真实跨境组缺10条。此处是M2-22.4基线时的粗分类，第20节后续按源定义复核为1条页眉普通文字、1条正文inline图片文字。逐来源看，`eu-low-value-returns-2022-en`两条全部恢复，OSS与GPSR各恢复一条，其余长VAT说明、关税附录、低价值货物、Safety Gate报告和告警存在完整或部分原文缺失。运行中Docling对若干长PDF打印内部120秒流水线超时、空OCR以及一次OCR线程未在15秒内退出的资源告警，但最终18个`parse_version`都发布了合法Artifact；这些告警与p95约136秒、真实组低恢复率共同说明当前增强解析存在明确性能、线程收束和文本完整性风险，不能只看“18/18解析完成”。

### 19.5 完整调用链位置

```text
前端：不经过
→ API：真实POST /files与POST /documents
→ Schema：File/Document合同 + M2评估Fixture/Report合同
→ Agent/LangGraph：不经过
→ Harness：不经过；本步是离线可信Runner，不是模型Tool调用
→ Tool：不经过
→ Service：FileService → DocumentService → DocumentParserService
→ Repository/Model：FileRepository / DocumentRepository → File / Document / Version
→ PostgreSQL：写入隔离评估租户的摄取和解析状态，结束后精确删除
→ Storage：写入隔离uploads与parsed JSON，结束后精确删除
→ Parser Router：Native优先，按既有质量规则进入Docling或Hybrid
→ Canonical Artifact：重新反序列化、统计并与冻结Evidence逐字匹配
→ pgvector：不经过
→ 外部Provider：只运行本地Docling/RapidOCR；不联网、不调用Qwen/Judge
→ Ragas：未安装、未导入、未运行
```

### 19.6 清理、能证明与不能证明

全量运行后评估租户为0、评估Storage对象为0；随后完整pytest又按既有Seed入口依次恢复M1、M2普通和M2复杂数据。最终只读复核为10 files、10 documents、10 versions、9 ACL、10个parse/index pending、10个正式upload对象、0个M2-22.4评估租户，M1 `LR-TL-MUSH-OR01 / DE-FRA`可售125；正式基线`clean=True`。最终代码复跑生成的实际报告大小28,251字节，未出现`storage_key`、`tenant_id`、口令、数据库URL或本机绝对路径。

能证明：18份选定原件能经过项目公开上传、文档登记、Storage、状态事务、Parser Router和Canonical Artifact；四格式Native链可运行；复杂件能真实调用本地Docling/OCR；Golden恢复是逐字、可重复且不使用答案变体；畸形PDF被拒；单件失败不会阻止清理；报告不能虚报完成；正式演示数据和M1库存可恢复。

不能证明：64.71%解析恢复足以支撑RAG；缺失事实能靠切块或提高TopK补回；Chunk边界、Embedding、pgvector、Dense/Lexical/RRF、Reranker、Context、Citation、Qwen答案、ACL/版本拒答或Ragas质量。本步结果反而证明上游Parser/OCR是当前首个显著质量瓶颈，后续指标必须保留这条归因，不能把漏字归咎于检索。

优先排查：真实PDF低恢复先比较Routed Artifact中的Native与Docling文本、质量路由原因和内部超时告警；图文DOCX先确认Hybrid按设计保留Native事实，因此图片OCR文字不进入selected Artifact；高延迟/高内存先看长PDF页数、Docling 120秒内部预算和CPU模型阶段；上传拒绝先看MIME/Magic、Office必需成员、100 MiB绝对解压上限和200倍倍率；清理失败先按评估租户、File/Version状态和精确Storage key定位，不做全目录删除。

本节当时停止等待M2-22.5切块质量矩阵；随后因Parser缺失插入R-01至R-04前置修复。当前边界以本文最后一节为准，M2-22.5仍暂停。

## 20. M2-22.4 缺失证据诊断（2026-09-08）

### 20.1 授权、目标与边界

用户在理解“解析任务成功不等于文字质量合格”后，明确要求先做诊断、确定具体问题。本步只对M2-22.4基线中8份存在缺失的文档和12条缺失Golden比较Native、Docling与基线最终选择结果，不修改`quality.py`、`routing.py`、Docling配置、Canonical Artifact、数据库状态或任何生产参数，也不运行API、PostgreSQL、Storage、Chunk、Embedding、pgvector、检索、Reranker、Agent、Qwen或Ragas。

输入为固定18文档Parser基线Run `m2-22.4-20260908t031430-a20e3f41`、同一份40条Smoke/34条可回答Golden及原始Hash固定文件。输出是Git忽略的实际报告`data/evals/runtime/reports/m2_parser_diagnostic_report_v1.json`和可提交的空白模板；实际报告不复制Golden原文或不可再分发的官方正文，只记录精确/宽松匹配、声明页匹配、Token Recall、字符数、警告代码和归因类别。

### 20.2 实现、TDD与调用链

- `app/evals/parser_diagnostics.py`：新增严格诊断Schema、基线报告绑定、缺失文档选择、Native/Docling/selected三路信号、页内匹配、无原文Token Recall、归因聚合、脱敏报告和显式离线CLI；最终实现先跑低成本Native，只有Native不能完成归因时才运行Docling，防止重复触发已知长文档资源问题。
- `data/evals/m2_parser_diagnostic_report_template_v1.json`：只含`planned`状态和零计数的可提交模板；不能冒充已执行报告。
- `tests/unit/test_m2_parser_diagnostics.py`：锁定路由选择损失、仅格式差异、Provider部分结果优先归因和模板无运行声明/无原文。
- 本记录、M2入口和项目总看板：当时同步实际结论、暂停M2-22.5并等待Parser修复方案；该方案后续已在第21节获确认并固化。

TDD RED首先得到`ModuleNotFoundError: No module named 'app.evals.parser_diagnostics'`；最小实现后专项`4 passed`。第一次真实实现直接让同一Converter连续重跑8份问题文档，复现120.063秒与120.031秒超时、OCR线程15秒不退出，第二次运行还出现`pypdfium2`页面句柄已失效的`NoneType`参数错误；第三份再于120.016秒超时后人工终止，避免失控线程继续污染后续样本。随后只修改诊断编排为Native先归因、仅未归因件调用增强Provider，未修改生产Parser。

完整调用链位置：

```text
前端 / API：不经过
→ Schema：复用Frozen EvaluationCase与新增Parser Diagnostic Report
→ Agent / LangGraph / Harness / Tool：不经过
→ Service：不调用File/Document/Chunk/Index Service
→ Repository / Model / PostgreSQL / pgvector / Storage：不经过、不写入
→ 本地固定原件：只读并复核Manifest Hash
→ Native Parser → Native Canonical Artifact
→ 仅未归因件：本地Docling/RapidOCR → Docling Canonical Artifact
→ 基线selected结果 + 三路无原文匹配信号 → 逐案例故障归因报告
→ Qwen / Ragas / 互联网：不经过
```

### 20.3 实际诊断结论

最终命令`.venv\Scripts\python.exe -m app.evals.parser_diagnostics --enable-docling`于26.13秒完成，Run ID为`m2-22.4-diagnostic-20260908t042202-c0af09f1`，绑定基线报告Hash `abc5e575248d5d96ee1d8406571ced19c3723461fbb26a903c992b2df3089ea6`。8/8问题文档完成、0诊断失败，12条缺失全部归因如下：

| 归因 | 数量 | 直接证据 |
|---|---:|---|
| `route_selection_loss` | 10 | 10条外部Golden在Native全文及各自声明页均精确命中，`token_recall=1.0`；基线最终Provider为Docling且对应Golden缺失 |
| `ocr_extraction_loss`（自动诊断粗分类） | 2 | 图文DOCX两条Office视觉Golden在Native和Docling中均`exact=false`、`relaxed=false`、`token_recall=0`；继续核对源定义后确认其中1条是页眉普通文字、1条才是正文内嵌图片文字 |
| 评估归一化、阅读顺序、模糊部分/完全漏失 | 0 | 现有12条无需用这些较弱解释兜底 |

七份存在外部缺失的PDF，其Native Artifact均无警告；路由原因却全部包含`complexity_detected_document_table`，其中VAT说明、OSS指南、低价值包裹和GPSR还包含`complexity_detected_two_column`。当前规则只要任一页满足绘图数量或左右块启发式，就把整份PDF路由到Docling；`routing.py`对`docling`路由又直接选择整份Docling Artifact，不比较Native是否更完整。基线中三个长文档尤其明显：

| 文档 | 基线Docling字符 | Native字符 | 丢失比例约值 |
|---|---:|---:|---:|
| VAT explanatory notes | 71,011 | 225,544 | 68.5% |
| OSS guidelines | 31,959 | 117,373 | 72.8% |
| Low-value consignments | 34,221 | 139,843 | 75.5% |

因此真实PDF低分的主因不是PyMuPDF/Native无法读取原文，而是过宽的“任一复杂信号→整文档Docling”路由和“整份Artifact二选一”策略；Docling超时/部分结果又放大了损失。若只做数学上的反事实组合——保留基线已命中的22条，再补回本次Native已证明存在的10条——可得到32/34、外部14/14；这不是生产修复后重跑成绩，不能写成Parser已经达标。

图文DOCX是不同问题：自动诊断因该文档整体标记`requires_ocr`而把两条统一归为`ocr_extraction_loss`，但源定义和既有集成测试进一步证明`QC-VISUAL-17`位于Word页眉普通文字，`QUARANTINE 12 PCS`才位于正文inline shape图片。当前Native只遍历顶层正文段落/表格，Docling标准DOCX路径也没有补回页眉或图片文字，且Hybrid合同固定选择Native。因此后续修复必须分别实现页眉/页脚文字提取和按原位置插入的图片OCR，不能把两条都误认为同一种OCR故障。

### 20.4 验证、能证明与不能证明

- 最终专项及相邻Runner/Router测试：`16 passed in 10.10s`；
- 完整单元回归：`957 passed, 2 skipped in 40.39s`；
- `ruff check`与两个新文件`ruff format --check`通过；
- 全范围`ruff check app tests scripts migrations`通过；`mypy app`为154个源码文件无问题，`compileall app`与`pip check`通过；`git diff --check`退出码0，仅有工作区既有LF/CRLF提示；
- 实际诊断报告16,626字节，SHA-256为`a30e23195753ed44819b0c510815970922d139b98d229dda347b3734f120d5ad`，不含`expected_text`、`storage_key`、`tenant_id`、口令、数据库URL、Windows或Linux绝对路径；
- 本步没有连接或写入数据库/Storage，不需要清理评估租户，正式Seed和M1库存未被改变。

能证明：当前12条缺失并非一个模糊的“解析器效果不好”；其中10条有可复现的Native完整文本和错误最终选择证据，2条有Native/Docling双路0 Token证据；结合源定义又可把这2条细分为1条页眉提取缺失和1条正文图片OCR缺失。当前整文档Docling路由存在事实完整性退化，连续超时后的共享Provider还存在资源状态污染风险。

不能证明：Native对整份文档的表格结构、阅读顺序和所有非Golden事实都优于Docling；32/34反事实等于修复后的正式成绩；图文DOCX只靠现有Docling参数就能修好；任何Chunk、Embedding、检索、回答或安全质量。本步没有修改生产代码，所以现有Parser行为仍然有问题。

当前诊断步骤停止。后续用户已确认Parser修复总体策略，但首先只授权更新文档；具体实施边界和下一停止点以第21节为准。

## 21. M2-22.4R Parser质量修复确认方案（2026-09-08）

### 21.1 用户确认、现状与本次文档边界

用户确认采用“Native健康度保底、Docling只作受控候选、DOCX视觉内容原位恢复、解析后质量门禁”的修复策略，并进一步提出三组具体规则：Native有效文字比例低于阈值才进入Docling候选；DOCX图片OCR文字按inline shape所在段落/Run位置插回并以`[图片内容]`展示；最终产物相对Native文字量突降、逐页空白和图片OCR为空分别形成阻断或告警。用户本次明确要求首先更新相关文档，因此本节只冻结方案、步骤、文件范围、调用链和验收门槛，没有修改任何生产代码、配置、迁移或测试。

当前已有能力是Native四格式解析、Docling/RapidOCR离线Provider、Canonical Artifact、Parser Router和版本化发布；当前缺少的是可靠的Native文本健康判断、增强Provider故障隔离、DOCX页眉/页脚与原位图片OCR、解析后的索引准入门禁。诊断已证明10条外部缺失来自错误整文档选择，另2条Office视觉缺失进一步细分为：

- `QC-VISUAL-17`：Word页眉中的普通文字，需页眉提取，不是图片OCR；
- `QUARANTINE 12 PCS`：正文段落inline shape中的图片文字，需图片提取、OCR和原位插入。

本修复序列编号为`M2-22.4R-01`至`M2-22.4R-04`，是进入原M2-22.5前的插入式质量前置，不把M2-22.5删除或冒充完成。总体方案已经确认，但本次只完成文档固化；每个代码小步骤开始前仍单独说明输入、输出和上下游，并在验证后停下供用户理解。

### 21.2 目标、明确不做与前置条件

目标：

1. 可读Native正文不再被复杂度标签触发的整文档Docling结果覆盖；
2. Native可疑或不可用时，Docling只作为受控候选，必须通过自身质量检查才能发布；
3. Docling超时、OOM或内部线程未收束时隔离失败，不污染下一份文档；
4. DOCX页眉/页脚文字被显式提取，正文inline shape图片经有界OCR后按原Run顺序进入Canonical Artifact；
5. 解析后使用全文和逐页规则拒绝明显截断/空白产物，对非关键DOCX图片OCR空结果保留结构化告警；
6. 只有质量合格的解析产物进入既有`parse_status=ready`，从而沿用现有状态前置阻止不合格内容继续切块和索引。

明确不做：

- 不在本序列运行M2-22.5 Chunk矩阵、Embedding、pgvector、Dense/Lexical/RRF、Reranker、Context、Agent、Qwen或Ragas；
- 不用LLM判断“文字是否可读”，健康度必须是可审计、确定性、版本化的纯计算；
- 不把两份完整Artifact无脑拼接，避免重复正文、阅读顺序错乱和表格事实冲突；
- 不允许Docling部分结果、超时结果或异常后共享状态被当成成功；
- 不用PDF单页“字节数大于10KB”判断页面有内容，因为字体、图片和资源可能共享/压缩，单页字节归属不稳定；
- 第一版不承诺浮动形状、文本框、批注、脚注、手写体、所有页眉图片、任意语言OCR或复杂表格语义完全恢复；这些必须有新Golden再扩展；
- 默认不新增数据库迁移；若既有`ready/failed`无法表达实际产品需求，再单独提交状态扩展方案，不能顺手增加。

前置条件已经满足：固定18份文档/34条Golden、Parser基线与诊断报告均可复现；本地Docling/RapidOCR模型Hash和离线边界已固定；原始文件Hash未漂移；正式Seed保持pending且M1库存基线为125。

### 21.3 总体决策规则

Native健康度计算属于`quality.py`，`routing.py`只执行决策。健康度至少结合有效字符比例、异常/控制/替换字符比例、总字符量、逐页文字覆盖和现有`empty_page/low_text_page/scanned_page_suspected`警告，不能只看单一字符数。具体阈值须在R-01用固定中英文/数字/表格/扫描样本校准后写入有边界的配置和运行身份，禁止运行时静默漂移。

| Native状态 | 复杂度标签 | 路由与选择 |
|---|---|---|
| 健康 | 无或仅表格线/双栏等结构提示 | 选择Native；结构提示只留审计原因，不能覆盖健康正文 |
| 可疑 | 任意 | 在隔离边界运行Docling；比较后只有合格候选才能选择，否则拒绝或保留明确可用的Native |
| 不可用/扫描 | 低文字、空文字且有图片等 | 在隔离边界运行Docling/OCR；增强结果仍不合格则解析失败，不发布脏产物 |
| CSV或无需增强的Office事实 | 任意 | 继续使用确定性Native；Docling不得覆盖XLSX公式、坐标和缓存值 |

复杂表格或双栏在Native文字健康时不再自动触发整文档替换。这一取舍优先保证事实不丢失，但不提前声称Native表格关系或阅读顺序一定最好；后续M2-22.5若用固定Golden证明结构仍不足，再单独设计按页/按块增强，不用猜测扩展。

DOCX顺序采用真实OOXML锚点：在现有`document.iter_inner_content()`顶层顺序中，段落继续遍历`runs`，检查Run XML的`w:drawing/wp:inline/a:blip`并通过内部关系取得受控图片字节；若段落结构为“前文→图片→后文”，Canonical顺序也必须保持“前文→图片OCR块→后文”。`document.inline_shapes`可用于计数和校验，但不能单独承担段落/Run定位。页眉和页脚通过Section关系单独提取并标记来源，不能伪装成正文图片OCR。

Canonical内部保存结构化来源，而不是只依赖可见标签：至少区分`body_text/header/footer/image_ocr`，记录段落或区域定位、图片序号/Hash、OCR Provider/版本和可用置信信息；Markdown/Chunk派生视图再渲染`[页眉]`、`[页脚]`、`[图片内容]`，方便用户溯源。若现有Artifact v1不能无歧义承载这些字段，R-03必须显式版本化并验证旧产物读取，不能悄悄改变v1语义。

### 21.4 四个实施小步骤

#### M2-22.4R-01｜Native文本健康度与PDF无损路由

- 输入：原始字节、Native Artifact、逐页属性、Native警告和复杂度标签；
- 输出：可审计的`healthy/suspect/unusable`决定、理由和确定性路由；
- 预计文件：`app/core/config.py`、`app/services/documents/quality.py`、`app/services/documents/routing.py`、`tests/unit/test_pdf_parser.py`、`tests/unit/test_document_routing.py`、评估诊断/Runner相邻测试及本进度记录；
- 实现重点：有效/异常字符与页面覆盖组合判断；健康Native不因`detected_document_table/two_column`被整文档Docling替换；扫描/低文字仍进入增强候选；路由原因和阈值版本可审计；
- 验证：先以RED证明当前7份问题PDF仍被错误路由，再使10条外部缺失全部由Native正确保留；扫描PDF仍真实进入Docling，CSV/Office公式边界不变；运行Parser/Router聚焦、完整单元、Ruff、Mypy和编译；
- 停止点：只完成R-01并汇报，不提前实现进程隔离、DOCX OCR、质量门禁或M2-22.5。

#### M2-22.4R-02｜Docling故障进程隔离

- 输入：R-01判为确需增强的安全文档；
- 输出：有时间/内存边界的独立Docling任务，成功返回严格Snapshot，超时/崩溃/OOM时销毁任务资源并返回固定安全失败；
- 预计文件：`app/services/documents/parsers/docling.py`、可能新增同目录受控worker模块、`app/core/config.py`、`tests/unit/test_document_routing.py`及显式真实Docling Smoke；
- 实现重点：Windows `spawn`兼容；结果大小有界；超时必须终止子进程而不是只取消Future；下一份文档获得干净进程；远程服务/插件继续关闭；
- 验证：构造第一份超时、第二份成功的连续任务，证明无失效页面句柄和残留共享Converter；真实扫描PDF保持2/2；记录启动开销、总耗时和RSS；
- 停止点：不处理DOCX视觉内容或索引门禁。

#### M2-22.4R-03｜DOCX页眉/页脚与原位图片OCR

- 输入：通过现有ZIP安全门禁的DOCX、Section页眉/页脚、正文段落Run及inline shape关系；
- 输出：带结构化来源的页眉/页脚文字块，以及位于原Run顺序的`image_ocr`块；派生文本显示`[页眉]`、`[页脚]`和`[图片内容]`；
- 预计文件：`app/services/documents/parsers/docx.py`、`app/services/documents/parsers/native.py`、可能新增受控RapidOCR图片Provider、`app/services/documents/artifacts.py`、`app/evals/parser_diagnostics.py`、Markdown/读取/Chunk兼容代码与对应单元/集成测试；
- 实现重点：图片数量、单图/总字节、像素和解压边界；只读取包内关系，不访问外链；保持前文→图片→后文；OCR文字去空白但不伪造；页眉事实与图片事实分开定位；Artifact版本和Hash稳定；
- 验证：当前图文DOCX的页眉`QC-VISUAL-17`与正文图片`QUARANTINE 12 PCS`均恢复且位置正确；图片前后文字顺序、重复图片、空OCR、超限图片、恶意关系和旧Artifact兼容均有测试；诊断报告将页眉提取损失与图片OCR损失分开归因，不再因文档级`requires_ocr`统一归类；
- 停止点：不运行Chunk质量矩阵或建立索引。

#### M2-22.4R-04｜解析后质量门禁与全量回归

- 输入：Native、候选增强结果、最终Artifact、逐页属性和DOCX图片OCR结果；
- 输出：确定性接受/拒绝/警告决定；只有接受结果允许Parser Service完成`ready`，拒绝结果沿用`failed`阻止后续索引；
- 预计文件：`app/services/documents/quality.py`、`app/services/documents/routing.py`、`app/services/documents/parser_service.py`、必要的Artifact/Schema字段、Parser/Index相邻单元与PostgreSQL/Storage集成测试、评估Runner和进度文档；
- 固定第一版规则：
  1. Docling/OCR超时、部分结果、OOM或未收束错误独立阻断，不需要等待字符比例判断；
  2. Native为健康基线时，最终非空字符数小于Native的70%视为全文疑似截断并阻断；70%必须进入配置/报告身份，可显式调节但不能静默漂移；
  3. 最终某页少于10字符且Native同页至少50字符，视为明确逐页退化并阻断；若Native同页也少于10字符但有图片/高图片覆盖，则要求OCR，增强后仍少于10字符时阻断或进入显式人工复核；真正无文字无图片的空白页不阻断；
  4. 不使用单页PDF字节数作为有内容证据；优先使用Native同页文字、图片数量/覆盖和结构化警告；
  5. DOCX图片大于5KiB但OCR为空时默认写结构化`ocr_possible_failure`警告且正文健康时不阻断；如果所在段落只有图片，或整份文档几乎无其他正文，则升级为阻断。页眉Logo、页脚图标等装饰媒体只进入低级告警/忽略规则；
- 验证：质量失败Artifact不能进入`parse_status=ready`，既有Chunk/Index Service状态前置继续拒绝；同一18文档重新经过公开上传、Storage、Parser和清理链，目标为34/34、官方14/14、OCR/Office视觉4/4、无120秒超时或残留线程，正式Seed和M1库存恢复；完整后端、Ruff、Mypy、编译、依赖、Alembic和diff门禁通过；
- 停止点：修复序列完成后向用户解释结果，仍不自动开始M2-22.5。

### 21.5 完整调用链位置

```text
前端：不修改
→ API：R-04全量回归复用POST /files、POST /documents；不新增公开解析参数
→ Schema：必要时只扩展版本化Parser/Artifact质量与来源合同
→ Agent / LangGraph / Harness / Tool：不经过
→ File/Document Service：复用现有摄取；Parser Service在R-04消费质量决定
→ Repository / Model / PostgreSQL：默认复用ready/failed，不预设迁移
→ Storage：原文件不变；只发布通过门禁的Routed Canonical Artifact
→ Native Parser → Native健康度
→ 必要时隔离Docling/RapidOCR
→ DOCX页眉/页脚及原位图片OCR
→ 全文/逐页/OCR质量门禁
├─ 合格：parse_status=ready，后续才可能进入Chunk
└─ 不合格：parse_status=failed，禁止索引
→ Chunk / Embedding / pgvector / Retrieval / Agent / Qwen / Ragas：本序列不运行
```

### 21.6 完成标准、风险与排查方向

整个Parser修复序列只有同时满足以下条件才算完成：

1. 固定18文档全部经过真实摄取/解析/清理闭环，34/34 Golden恢复，官方14/14，四条Office/OCR视觉事实4/4；
2. 健康Native不会因结构复杂度标签被整文档Docling覆盖，扫描/低文字PDF仍能获得真实OCR；
3. Docling超时或崩溃不污染下一任务，部分结果不能发布；
4. DOCX页眉与inline图片事实各有真实位置和Provider/版本来源，派生标签不取代结构化溯源；
5. 70%全文突降、逐页退化和OCR空结果三类规则均有正反例，明确区分阻断与告警；
6. 不合格产物不能进入ready/Chunk/Index，重试、旧active版本、Storage补偿和权限边界保持；
7. 聚焦、完整回归和工程门禁通过，进度文档记录能证明/不能证明的范围；
8. 用户理解并确认Parser修复结果后，才重新提交M2-22.5开始授权。

主要风险与排查：有效字符比例误伤多语言/符号/表格文档时先检查指标分项和固定样本，不直接放宽所有阈值；Native字符多但阅读顺序差时留给后续结构Golden验证，不用文字量冒充语义正确；Windows子进程启动慢或模型重复加载时先测仅对确需OCR的少量文档，不退回共享故障状态；inline与浮动图片混淆时先核对OOXML的`wp:inline/wp:anchor`和关系ID；OCR重复/错位先查Run顺序、图片Hash和去重；全局70%未捕获局部漏字时优先看逐页规则；图片5KiB阈值误报Logo时看所在区域和正文占比；Artifact版本变化导致旧文件不可读时停止发布并先补兼容读取/迁移方案。

本节文档固化步骤完成时只完成方案记录；随后用户已分别单独授权并完成`M2-22.4R-01`至`M2-22.4R-04`，实际记录见第22至25节。M2-22.5和后续RAG/Ragas步骤仍未授权。

### 21.7 本次文档固化完成记录

- 日期与范围：2026-09-08，只更新M2-22过程记录、M2阶段入口、项目总看板和M2-07至11历史Parser记录；没有修改生产代码、配置、迁移、测试数据或评估代码；
- 已固化内容：方案被拆为R-01 Native健康度与无损路由、R-02 Docling子进程隔离、R-03 DOCX页眉/页脚及原位图片OCR、R-04解析后质量门禁与全量回归；同时将DOCX两条粗粒度`ocr_extraction_loss`纠正为1条页眉提取缺失和1条正文图片OCR缺失；
- 调用链位置：本次仅修改设计/进度记录，不经过前端、API、Schema、Agent/LangGraph、Harness、Tool、Service、Repository/Model、PostgreSQL/pgvector、Storage或外部Provider；第21.5节记录的是后续R-01至R-04实现将进入的真实链路；
- 验证方法与实际结果：`git diff --check`通过；对4份相关Markdown做尾随空白、冲突标记、代码栅栏和本地相对链接扫描，全部通过；用`rg`复核顶部状态、第21节标题和旧粗分类表述，当前状态统一为“方案已确认并完成文档固化，等待R-01单独授权”；再对照现有源码与集成夹具，`DocxParser`当前只遍历`document.iter_inner_content()`，夹具明确验证`QC-VISUAL-17`位于页眉且正文有1个`inline_shape`；最后用项目虚拟环境运行`.venv\Scripts\python.exe -m pytest tests/unit/test_m2_baseline.py -q`，实际为`49 passed in 1.99s`；
- 能证明：后续修复范围、顺序、预计文件、验证方式、停止点和两类DOCX故障已在文档中一致且可导航；
- 不能证明：Native健康度阈值已校准、路由已修复、Docling已隔离、DOCX页眉/图片已恢复、质量门禁已阻断脏数据或34/34 Golden已达成；这些都必须由后续每个获授权的代码步骤实际验证；
- 该文档固化步骤当时的风险与下一动作：如后续发现文档与代码不符，先停止实现并核对`quality.py`、`routing.py`、`docx.py`和Artifact合同；当时停止等待M2-22.4R-01，该步骤后续已按第22节完成。

## 22. M2-22.4R-01实施记录：Native文本健康度与PDF无损路由（2026-09-08）

### 22.1 授权、问题与边界

用户明确授权开始第一步。本步只解决“健康Native PDF因表格/双栏标签被整文档Docling覆盖”：输入为原文件、Native Canonical Artifact、逐页属性、Native告警和复杂度标签；输出为版本化`healthy/suspect/unusable`健康结果、可审计理由和路由选择。本步没有实现Docling进程隔离、DOCX页眉/图片OCR、70%突降/逐页空白/空OCR门禁、Chunk、索引、检索或Ragas。

### 22.2 用大白话解释现在如何运行

旧逻辑像是“看到文档里有表格线或双栏，就把整本换一个人重读”，而新逻辑先检查Native读出来的字是不是正常、数量够不够、多少内容页有足够文字。如果是`healthy`，表格/双栏只记在日志中，继续使用Native；如果是`suspect`或`unusable`，例如整页只有两个字、全是替换乱码或扫描图无文字，才进入Docling。真正空白且没有图片的页不计入“内容页”，不会因一张合法空白页误判整份文档。

策略版本固定为`m2-native-text-health-v1`，首版阈值为：整份至少20个非空白字符、有效Unicode字符比例至少90%、健康内容页比例至少80%，每页健康线复用PDF Native已有的20字符阈值。这些数值都由Settings限定边界，并连同实际比例写入`ParseQualityDecision.native_text_health`，不会静默漂移。

### 22.3 修改文件与职责

- `.env.example`：声明三个Native文本健康度配置示例；
- `app/core/config.py`：对整份最低字符、有效字符比例和健康页比例做Pydantic边界校验；
- `app/services/documents/quality.py`：实现确定性、线性且不额外复制全文的Native健康度计算，保存策略版本、指标、阈值和理由，并让健康PDF的结构标签降为审计提示；
- `app/services/documents/routing.py`：把服务端Settings中的实际阈值传给Quality，只执行已计算的路由；
- `app/evals/parser_diagnostics.py`：诊断重跑与生产Router使用同一组Settings阈值；
- `scripts/verify_m2_parser_router.py`：在可审计验证报告中增加完整Native健康度快照；
- `tests/unit/test_document_routing.py`：覆盖健康双栏/表格、合法空白页、低文字、扫描、替换乱码、Settings传递、旧Quality载荷兼容和Office边界；
- `tests/unit/test_m2_baseline.py`：固定默认值、环境变量隔离和非法阈值拒绝；
- 本记录、M2入口和项目总看板：同步实际状态和验证边界。

`tests/unit/test_pdf_parser.py`没有修改，因为Native PDF提取产物本身未改；本步复用并实际重跑其页面/告警合同，避免为了文件数量制造无意义改动。

### 22.4 完整调用链位置

```text
前端：不修改
→ API：不修改；真实Parser Service集成测试复用既有入口
→ Schema：不修改公开API Schema；内部ParseQualityDecision新增可选健康度快照以兼容旧载荷
→ Agent / LangGraph / Harness / Tool：不经过
→ File/Document Service：复用现有DocumentParserService
→ Storage原文件
→ Native Parser
→ Quality：有效字符 + 文字量 + 内容页覆盖 + Native告警
→ Router
├─ healthy PDF：选择Native，结构标签只审计
└─ suspect/unusable PDF：进入现有Docling路径
→ Routed Canonical Artifact
→ Parser Service沿用现有Storage发布和PostgreSQL ready/failed状态
→ Chunk / Embedding / pgvector / Retrieval / Agent / Qwen / Ragas：本步不运行
```

本步没有新增数据库字段或Alembic迁移，也没有改变DOCX/XLSX/CSV的Native/Hybrid选择合同。

### 22.5 TDD与实际验证

1. RED：先改测试再运行Router与Settings集，实际为`9 failed, 54 passed in 13.68s`。失败精确表现为健康复杂PDF仍调用Docling、`ParseQualityDecision`没有`native_text_health`、三个Settings字段不存在；
2. 最小GREEN：实现后Router与Settings为`63 passed in 10.73s`；补齐Settings传递和旧载荷兼容后，Parser/Router/诊断/Runner聚焦扩展集为`85 passed in 14.92s`；
3. 8份固定官方PDF只读复核：使用现有Manifest和原文件Hash加载，不调用Docling；8/8均为`healthy/native`，有效字符比例为`0.999642～1.0`，内容页覆盖均为`1.0`，14/14官方Golden逐字恢复且无缺失；
4. 5份复杂合成文档真实本地Docling/RapidOCR：路由为Native 2 / Docling 1 / Hybrid 2，只有3份进入增强Provider；扫描PDF为`unusable → Docling`并恢复2/2，双栏和复杂表格PDF均为`healthy → Native`并各2/2，XLSX仍2/2，DOCX仍0/2，整体`8/10`；
5. 完整单元：`.venv\Scripts\python.exe -m pytest tests/unit -q`实际为`966 passed, 2 skipped in 39.45s`；
6. 相邻真实集成：Parser Service、File Reading、复杂Seed和M2-22 Parser Runner共`12 passed in 24.53s`；
7. 工程门禁：全范围Ruff通过；Mypy为`Success: no issues found in 154 source files`；`compileall`无错误；`pip check`为`No broken requirements found`；`git diff --check`通过。全仓Ruff格式检查为`327 files already formatted`并仅报告既有、本步未修改的`tests/integration/test_document_chunk_set_migration.py`一处格式差异，本步没有越界改写。

### 22.6 能证明、不能证明与排查方向

能证明：健康PDF不再因表格/双栏启发式被整文档Docling覆盖；既有10条官方选择损失对应的Native事实现保留在最终产物中，8份官方PDF的14/14 Golden都能恢复；扫描和低文字仍进入增强路径；中英文、数字、表格、空白页、配置边界和旧Quality载荷兼容有回归保护。

不能证明：Native的表格关系和阅读顺序对所有PDF都优于Docling；未见语种或特殊符号永不会误判；Docling超时后已安全清理；DOCX页眉/图片已恢复；70%突降或逐页空白门禁已阻断脏产物；整个18文档经真实API/Storage/PostgreSQL重跑后已达34/34。本步的直接Parser复核可推导当前可回复为32/34，但不把它写成R-04才会进行的全链实测成绩。

若后续出现正常文档被判`suspect`，先查`native_text_health.reasons`和报告中的实际比例，不直接放宽所有阈值；表格或双栏内容文字多但顺序错时，留给M2-22.5结构Golden定量验证；扫描件不进Docling时，优先查Native页的`image_count`、`low_text`和`scanned_page_suspected`；配置不生效时，核对Settings值与健康度快照中保存的阈值是否一致。

本节当时停止等待`M2-22.4R-02`；该步后来已获用户单独授权并按第23节完成，R-03和R-04也已按第24、25节完成。当前边界以第25节为准，仍不得运行M2-22.5或进入任何后续RAG/Ragas步骤。

## 23. M2-22.4R-02实施记录：Docling故障进程隔离（2026-09-08）

### 23.1 授权、问题与边界

用户明确授权开始`M2-22.4R-02 Docling故障进程隔离`。R-01之后，只有Native为`suspect/unusable`或既有Office Hybrid规则确需增强的安全文件才进入Docling，但旧`LocalDoclingProvider`仍在主服务进程内懒加载并复用同一个`DocumentConverter`。第三方转换内部即使达到120秒文档超时，OCR线程、PDF页面句柄或模型状态也可能继续留在主进程，导致下一份文档受到上一份故障污染。

本步输入是R-01路由后确需增强的受控文档字节、格式和非秘密Docling配置；输出要么是父进程重新校验的严格`DoclingParseSnapshot`，要么是固定`复杂文档增强解析失败`。本步只建立每文档一次性进程及时间、RSS、结果大小边界，没有实现DOCX页眉/页脚、inline图片OCR、70%全文突降/逐页退化/空OCR质量门禁、Chunk、索引、检索或Ragas。

### 23.2 用大白话解释现在如何运行

旧做法像让Docling一直在主办公室里工作：它卡住或把内部工具弄坏，办公室和下一份文档都会受影响。新做法是每来一份确需增强的文档，就开一间一次性工作室。父进程只把这份文档和经过筛选的设置交进去；Docling的Converter、模型、OCR线程和PDF句柄全部只存在于这间工作室。成功时，子进程只交回一个有大小上限的JSON快照；父进程确认子进程已经正常退出、快照结构和请求格式都正确后才接收。失败、卡死或占用内存过大时，父进程关闭整间工作室和已发现的子进程，不接受“做了一半”的结果，下一份文档再开全新的进程。

这里的`spawn`是Windows创建全新Python进程的方式。它不会继承上一份文档的Converter对象，隔离更干净；代价是每份真正进入Docling的文档都要重新加载Python、模型和OCR，因此会增加冷启动时间。R-01先尽量让健康文本PDF走Native，正是为了把这笔成本只留给确实需要OCR/增强的少数文档。

首版默认边界为：父进程总时限150秒、Worker进程树采样RSS上限4 GiB、返回Snapshot上限64 MiB；现有Docling内部文档时限仍为120秒。父进程每50 ms查看一次Worker及其子进程RSS。这个RSS门禁是父进程采样后主动终止，不是操作系统cgroup/Job Object硬配额，因此能阻断持续超限并隔离进程崩溃，但不能承诺捕获两个采样点之间的瞬时尖峰。

### 23.3 修改文件与职责

- `.env.example`：声明Docling父进程总时限、Worker进程树RSS上限和返回Snapshot字节上限；
- `app/core/config.py`：增加三个带上下界的Settings字段，默认分别为150秒、4 GiB和64 MiB；
- `app/services/documents/parsers/docling.py`：移除主进程共享`DocumentConverter`；增加仅包含Docling本地安全配置的严格Worker合同、Windows `spawn`一次性进程、单向Pipe协议、父进程时间/RSS监控、Snapshot双侧大小限制、成功后格式复验、进程树`terminate → kill`清理和不含原文/异常的结构化运行日志；真正的Converter构造、RapidOCR和Snapshot生成全部移动到子进程；
- `requirements.txt`、`requirements-dev.txt`：把`psutil`从仅开发依赖提升为运行依赖，因为生产父进程现在用它采样并清理Worker进程树；
- `tests/fixtures/docling_process_worker.py`：提供Windows `spawn`可导入的最小假Worker，稳定制造卡死、崩溃、超大结果和成功，不加载真实模型；
- `tests/unit/test_docling_process_isolation.py`：验证超时PID消失、下一份使用不同干净进程、崩溃/RSS/结果超限固定失败及内部状态日志；
- `tests/unit/test_m2_baseline.py`：固定三个默认值、非法边界拒绝、环境变量隔离和`psutil`运行依赖；
- `scripts/verify_m2_parser_router.py`：为显式真实Smoke增加可选单文档和输出路径参数，并开启运行日志，使子进程启动、就绪、总耗时和峰值RSS可审计；默认全语料行为不变；
- 本记录、M2阶段入口、项目总看板和M2-07至11历史修正指引：同步完成状态、验证事实、限制和下一停止点。

`routing.py`本步没有修改：R-01已经只在确需增强时创建并调用`LocalDoclingProvider`，而Provider的`parse → DoclingParseSnapshot`协议没有改变。本步只替换该协议下面的执行边界，避免把隔离逻辑塞进路由决策。

### 23.4 完整调用链位置

```text
前端：不修改
→ API / 公开Schema：不修改
→ File/Document Service：沿用现有调用与ready/failed补偿；本步相邻回归覆盖
→ Storage原文件：沿用受控字节读取
→ Native Parser → R-01 Native健康度 → Router
├─ healthy / 无需增强：仍直接使用Native，不创建Docling进程
└─ suspect/unusable或既有Hybrid：LocalDoclingProvider（本步父进程边界）
   → Windows spawn一次性Worker
   → 离线CPU Docling + RapidOCR（远程服务/插件固定关闭）
   → 有界JSON DoclingParseSnapshot
   → 父进程等待正常退出并重新校验Snapshot
   ├─ 成功：Docling Adapter → Routed Canonical Artifact
   └─ 超时/崩溃/RSS/结果超限：清理进程树 → 固定安全失败，不发布部分结果
→ Repository / Model / PostgreSQL：本步不改；Service实际调用时沿用既有失败状态
→ Chunk / Embedding / pgvector / Retrieval / Agent / Qwen / Ragas：本步不运行
```

显式真实扫描Smoke直接运行正式Router与真实本地Provider，没有经过公开API、PostgreSQL或Storage；相邻12项集成另外验证了既有Parser Service、File Reading、复杂Seed和评估Runner合同，但其中日常集成不会隐式加载真实Docling模型。没有新增数据库字段或Alembic迁移。

### 23.5 TDD与实际验证

1. 测试先行的首轮RED为`9 failed, 50 passed in 8.68s`：生产代码尚不接受隔离Worker、三个Settings字段不存在、`psutil`未声明为运行依赖；首版测试辅助函数还暴露了重复关键字构造错误，先单独修正测试夹具后再实现生产代码，没有用放宽断言制造GREEN；
2. 假Worker隔离测试最终包含5个用例：第一份任务卡死2秒后父进程终止它，日志中的超时PID已不存在；同一个Provider紧接着解析第二份成功，返回PID不同且子进程模块计数为`run_count=1`，证明没有共享上一进程的Converter/全局状态；另一个Worker先发送合法成功Snapshot再故意保持进程不退出，父进程等待2秒收束窗口后仍拒绝结果、记录`shutdown_timeout`并清理，覆盖了原OCR线程不退出故障；
3. 同一测试还让Worker直接`exit(17)`、发送超过1 KiB的返回包，并把RSS门禁降至1 MiB；三者都没有返回Snapshot，只产生固定`复杂文档增强解析失败`，内部日志分别记录`worker_crash/result_too_large/memory_limit`且不含底层异常、原文或路径；
4. Settings、隔离和Router最终聚焦集合为`73 passed in 16.12s`；完整单元为`974 passed, 2 skipped in 43.77s`；Parser Service、File Reading、复杂Seed和M2-22 Parser Runner相邻集成为`12 passed in 27.63s`；
5. 先用现有五份复杂合成文档跑正式Router，实际为5份完成、3份调用Docling、路由Native 2 / Docling 1 / Hybrid 2、选中事实8/10；仍缺的2条正是未进入本步的DOCX页眉/图片事实，没有把它们冒充修复；
6. 再显式只跑真实生成的两页扫描PDF：Native健康度为`unusable`，路由进入一次性Docling进程并恢复`BATCH-SCAN-42`与`20 PCS`两条事实，结果2/2；运行日志为`status=success`、Worker PID 31916、`spawn_ms=4958`、`ready_ms=4975`、`total_ms=77721`、`peak_rss_bytes=1961213952`（约1.83 GiB），低于150秒和4 GiB默认边界，命令完成后复核该PID不存在；
7. 上述扫描报告保存于Git忽略的`output/m2_docling_process_isolation_smoke.json`，共6,123字节，SHA-256为`87e1c6c1f242e19a77fa8938e93a629357e6bdf67c4bf0f7c6a22bc0cc007d89`；报告只包含合成事实检查、Hash、路由和Parser元数据，不提交模型或二进制源文件；
8. 工程门禁：`ruff check app tests scripts migrations`全范围通过；所有R-02代码/测试文件格式正确，全范围为329个文件正确且只保留本步未修改的`tests/integration/test_document_chunk_set_migration.py`一处既有差异；`mypy app`为154个源码通过，包含本步脚本/测试时156个源文件通过；`compileall`、`pip check`和`git diff --check`通过；
9. Alembic current/heads均为`20260905_0011 (head)`，`alembic check`为`No new upgrade operations detected`，本步没有迁移。真实Smoke只读本地模型缓存并保持`HF_HUB_OFFLINE/TRANSFORMERS_OFFLINE`，Docling远程服务和外部插件继续固定关闭。

### 23.6 能证明、不能证明与排查方向

能证明：主服务进程不再持有或复用Docling Converter；超时Worker会被实际终止而不是只取消一个Future；崩溃、持续RSS超限、返回包超限和异常结果不会变成部分Canonical Artifact；下一份文档获得新的Python进程和干净模块状态；严格Snapshot是唯一成功跨进程数据；真实RapidOCR扫描能力在隔离后仍为2/2，且当前机器单任务资源低于默认边界。

不能证明：50 ms采样RSS等同于操作系统硬内存配额；极短瞬时峰值绝不会触发系统级OOM；多个Docling请求同时到来时总内存已由全局队列/背压限制；任意长文档都能在150秒内完成；DOCX页眉/图片已恢复；R-04质量门禁已拒绝所有脏产物；18份文档全链已经达到34/34；Chunk、索引或RAG质量已验证。本步实测还明确显示一次性进程存在约4.96秒启动开销，扫描任务总耗时约77.72秒，不能包装成低延迟能力。

若出现`status=timeout`，先核对总时限、文件页数和Docling内部阶段，不要退回共享Converter；`memory_limit`先看日志中的`peak_rss_bytes`、是否有多个并发任务以及模型是否漂移，不要直接把4 GiB无限放大；`result_too_large/protocol_failure`先查Snapshot条目数、单元格膨胀和Adapter版本；`worker_crash`先在隔离Smoke中复现并检查本地模型/ONNX运行库，公开错误仍保持固定；成功但耗时突增先区分`spawn_ms/ready_ms`与模型推理时间；生产并发时若聚合内存高，后续应设计全局队列、并发配额或独立Worker服务，而不是复用同一故障状态。

本节当时停止等待`M2-22.4R-03`；该步后来已获用户单独授权并按第24节完成，R-04也已按第25节完成。当前边界以第25节为准，仍不得运行M2-22.5或进入任何后续RAG/Ragas步骤。

## 24. M2-22.4R-03实施记录：DOCX页眉/页脚与原位图片OCR（2026-09-08）

### 24.1 用户授权、本步缺口与边界

用户明确授权开始`M2-22.4R-03 DOCX页眉/页脚与原位图片OCR`。编码前的真实缺口是：`DocxParser`只把`document.iter_inner_content()`中的顶层正文段落/表格写入结果，Section页眉/页脚没有进入Artifact，正文图片Run也只留下空段落；旧DOCX复杂度标签还会触发标准Docling，虽然诊断已经证明标准Docling没有补回这两类事实。

本步输入是经过既有ZIP安全门的DOCX字节、Section页眉/页脚容器、正文段落Run及其内部图片关系；输出是保留正文顺序的结构化来源：`document_text/docx_header/docx_footer/docx_image_ocr`。图片来源至少记录原正文Block/段落、Run、出现序号、SHA-256、字节数、像素尺寸、Content-Type、OCR Provider/版本和平均置信度；Markdown派生视图显示`[页眉]`、`[页脚]`、`[图片内容]`。本步没有实现R-04的70%全文突降、逐页空白和大图空OCR门禁，没有运行M2-22.5 Chunk质量矩阵、建立索引或执行检索/Reranker/Agent/Qwen/Ragas。

### 24.2 大白话运行过程与设计取舍

大白话理解：以前程序只读Word纸张中间的正文，所以页眉像写在“纸的上边框”，图片则像只看到一个空相框。现在程序先把每个不重复的页眉、页脚单独抄出来；再进入正文段落，不是一次性拿整段字符串，而是沿Run内部顺序逐项走。如果遇到“前文→图片→后文”，就先保存前文，再从DOCX包内关系取出图片做本地OCR，再保存后文。因此OCR文字不会统一堆到文件末尾，也不会切断原逻辑。

安全上，图片仍是文档解析输入的一部分而不是任意URL：所有`.rels`先检查，图片关系若为External直接拒绝；只接受包内`image/*`部件。默认最多100张图、单图10 MiB、全部图片25 MiB、单图2000万像素，且继续受DOCX源文件、ZIP展开、Block和总字符限制。相同图片重复出现时，SHA-256缓存让OCR只运行一次，但每个物理出现位置仍有自己的`image_number`和Run锚点。图片损坏、关系伪造、超限或真实OCR模型缺失都安全失败；OCR合法返回空文字时只保留空的结构化图片来源，不编造文字，后续由R-04根据图片大小决定告警。

Canonical顶层仍是`m2-canonical-parsed-artifact-v1`。这里没有悄悄给普通Block强塞新字段：`ArtifactTextBlock`新增的`source_kind/docx_source`在普通`document_text`时从序列化中省略，因此旧v1正文/表格JSON和内容Hash计算形状不变；只有新的DOCX特殊来源才出现字段，并由嵌套`contract_version=m2-docx-source-v1`显式标识扩展版本。新应用已验证可以读取旧形状，特殊来源缺字段、来源类型冲突或把DOCX来源放进非DOCX Artifact都会被严格拒绝。这样不需要在本步扩展数据库Schema或迁移，也不会让旧Artifact失读。

Word的Section不是物理页码。`python-docx`能可靠给出Section、段落、Run和关系，却不能在不经过排版引擎的情况下给出稳定渲染页码；本步因此没有把Section 1伪造成第1页。现有图文DOCX Chunk Golden会呈现“页眉内容已命中，但声明的第1页Locator仍不满足”，这是保留真实来源而不是制造假通过。物理页码问题留到R-04之后的M2-22.5 Locator矩阵评审。

### 24.3 修改文件与职责

- `app/services/documents/parsers/docx.py`：Parser版本升到`m2-docx-v2`；新增页眉/页脚区域Block、段落文本/图片OCR Segment、Run内原位遍历、内部图片关系检查、图片Hash/尺寸/数量/字节/像素边界、重复图片缓存和结果计数校验；
- `app/services/documents/parsers/docx_ocr.py`：新增可替换`DocxImageOcrProvider`与离线`LocalRapidOcrProvider`；固定读取`DOCLING_MODEL_CACHE_ROOT/RapidOcr`下三个ONNX模型的明确路径，缺文件先失败，不给RapidOCR留下联网下载路径；
- `app/services/documents/parsers/native.py`与`parsers/__init__.py`：按页眉→正文原位Segment→页脚转换为连续Canonical Block，并公开严格Parser/OCR合同；
- `app/services/documents/artifacts.py`：增加显式版本化DOCX来源元数据、跨字段校验和三类Markdown标签；普通v1文本字段通过条件排除保持旧序列化/Hash形状；
- `app/services/documents/quality.py`：DOCX的`header_footer/image_text/body_visual/detected_embedded_media`成为“Native视觉提取已处理”的审计理由，不再无意义触发标准Docling；PDF的R-01健康度与XLSX既有Hybrid路径不变；
- `app/evals/parser_diagnostics.py`：Artifact诊断汇总分别统计页眉、页脚和图片OCR Block，避免再把三类来源混成同一种OCR问题；
- `app/core/config.py`、`.env.example`、`requirements.txt`：声明OCR开关/线程和四个图片上限；默认启用本地RapidOCR；把直接用于图片尺寸安全检查的Pillow列为运行依赖；
- `tests/fixtures/docx_factory.py`、`tests/unit/test_docx_visual_sources.py`：合成页眉/页脚、前文→图片→后文、重复图片及外链图片关系，验证顺序、来源、Hash缓存、空OCR和安全上限；
- `tests/unit/test_docx_parser.py`、`test_parsed_artifacts.py`、`test_document_routing.py`、`test_m2_parser_diagnostics.py`、`test_m2_chunk_pipeline_verification.py`、`test_m2_baseline.py`：同步Parser版本、旧Artifact兼容、Router/诊断/Chunk读取与配置边界；
- `tests/integration/test_m2_docx_visual_ocr_smoke.py`与`test_seed_m2_complex_files.py`：显式真实RapidOCR Router Smoke和复杂合成原件结构检查；
- 本记录、M2阶段入口、项目总看板和M2-07至11历史修正指引：同步完成状态、实测事实、限制和下一停止点。

### 24.4 完整调用链位置

```text
前端：不修改
→ API / 公开Schema：不修改
→ File / Document Service：沿用既有解析任务与ready/failed补偿，本步不写库验证
→ Storage原文件：正式Service中仍按既有方式读取；本步真实Smoke直接使用固定合成字节
→ DOCX ZIP安全门
   → 拒绝外链图片关系 / 压缩与展开超限
→ DocxParser v2
   ├─ Section header/footer → 独立region来源
   └─ body Paragraph → Run顺序 → wp:inline内部图片
      → 图片数量/字节/像素门禁 → 本地RapidOCR → 原位image_ocr Segment
→ Native Adapter → Canonical Artifact + m2-docx-source-v1来源元数据
→ Router：DOCX视觉标签保留Native并记录审计理由，不调用标准Docling
→ Markdown / 既有Chunk读取兼容：可消费新Block；本步不运行正式Chunk质量矩阵
→ Repository / Model / PostgreSQL / pgvector / Index：不修改、不写入
→ Retrieval / Reranker / Context / Agent / Qwen / Ragas：不经过
```

本步代码主要位于Parser、Adapter、Canonical Schema和确定性Router决策层。未经过的前端、API、Harness、Tool、Repository/Model、PostgreSQL、pgvector与外部Provider均没有被描述为已验证。

### 24.5 TDD、真实文档与工程验证

1. Parser/Artifact首轮运行只有旧测试的Parser版本断言失败，其余23项通过；随后专项加入前后文顺序、页眉/页脚、重复图片、空OCR、三类图片上限、外链关系和旧Artifact读取，Parser/Artifact集合达到`32 passed`；
2. 最终专项与相邻Parser、Artifact、Router、诊断、Chunk兼容、配置及复杂原件为`116 passed in 20.83s`；完整单元为`990 passed, 2 skipped in 46.34s`；
3. 显式真实命令`RUN_REAL_DOCX_OCR_SMOKE=1 ... test_m2_docx_visual_ocr_smoke.py`为`1 passed in 7.96s`。正式Router路由为`native`，审计理由分别记录`body_visual/detected_embedded_media/header_footer/image_text`已由Native视觉提取处理；标准Docling未启动；
4. 同一真实图文DOCX的Canonical Artifact为12个Block、254个非空白字符；`QC-VISUAL-17`和`QUARANTINE 12 PCS`均存在且页眉先于图片。图片为`image_number=1`，SHA-256 `145e1f8967d0964fd48ef4e12e6fcb5afa695729956d45097a01bc8bf8bcf81d`，Provider为`rapidocr-3.9.2+pp-ocrv6-small-onnxruntime-cpu`，三行OCR平均置信度约`0.992757`；Artifact内容Hash为`86c64f396daaa880b88d036c796a88f42cd5f7e0a88e45af5532c6033e9a9dcd`；
5. 按documents技能执行真实版面检查：仓库生成的固定DOCX先尝试技能自带`render_docx.py`，当前Windows运行环境因缺`pdf2image`且没有LibreOffice无法使用该路径；随后经用户批准调用本机Word隐藏只读导出临时PDF，再用PyMuPDF以2倍缩放生成1页PNG并逐页目视检查。页眉`CONTROL CODE: QC-VISUAL-17`、正文图片三行文字和页脚`ESCALATION: QUALITY-LEAD`均清晰，无裁切、重叠、缺字或异常空白；临时文件只在Git忽略的`tmp/m2_r03_visual`，不是交付物；
6. 工程门禁：全范围`ruff check app tests scripts migrations`通过，`mypy app`为155个源码无问题，`compileall app`和`pip check`通过；Pillow已成为直接运行依赖；
7. 全量后端原样运行得到`1259 passed, 14 skipped, 6 failed in 293.13s`。其中5个R-02进程隔离日志断言单独复跑为`5 passed in 9.87s`，确认是全套测试中日志配置顺序污染，不是隔离行为回归；剩余`test_parse_failure_marks_first_index_failed_without_creating_index_set`独立仍失败，因为测试固定删除`.../uploads/2026/08/...`而当前上传对象位于`2026/09`，与此前记录的既有跨月时间依赖相同。本步没有越界修改索引Service或该测试；
8. 本步没有数据库迁移，没有运行索引或修改正式Seed；全量测试连接共享PostgreSQL只执行既有测试夹具及其清理，R-03自身的专项/真实Smoke不连接数据库或Storage。

### 24.6 能证明、不能证明与排查方向

能证明：页眉/页脚普通文字已进入明确来源；正文inline图片OCR按真实Run锚点留在前后文之间；结构化来源包含图片序号/Hash/尺寸与OCR身份/置信度；外链、损坏或超限图片不会变成可发布文字；重复图片缓存不会丢掉出现位置；OCR空结果不会伪造内容；普通旧Artifact v1形状仍可读取；真实固定图文DOCX由正式Router保持Native并找回两条已知文字；Markdown和现有Chunk读取不会因新Block类型崩溃。

不能证明：浮动Shape、文本框、脚注、批注、手写体、任意语言、所有图片格式或页眉图片均能恢复；Section/Run定位等于物理页码；OCR文字一定正确；空OCR、大幅截断或PDF空白页已经被R-04门禁；18份/34条Golden、Chunk Locator、索引、检索、Reranker、Context、回答或安全指标已经重跑达标。真实OCR只验证当前固定英文质检卡和当前本地模型，不能包装成生产多语言OCR质量。

若页眉/页脚缺失，先查Section是否`linked_to_previous`、实际Header/Footer Part及其中是否为文本框而非普通段落；若图片没有Segment，先查是否为`wp:inline`、关系是否`r:embed`且类型为`image/*`，浮动`wp:anchor`不在首版承诺内；若报解析失败，先查External图片关系、图片部件类型或损坏；若报安全上限，先看图片数量、单图/总字节和像素，不直接放大默认值；若报增强解析失败，先核对本地三个RapidOCR ONNX文件和onnxruntime，不允许打开网络下载；若OCR为空，R-03只保留空来源，待R-04按图片大小告警；若Chunk能搜到内容但页码Locator失败，应确认是不是DOCX物理页码不可得，禁止用Section号造假。

本节当时停止等待`M2-22.4R-04 解析质量门禁与拒绝索引`；该步后来已获用户单独授权并按第25节完成。当前边界以第25节为准，仍不得运行M2-22.5 Chunk质量矩阵、为合格文档建立索引或进入任何后续RAG/Ragas步骤。

## 25. M2-22.4R-04实施记录：解析质量门禁与拒绝索引（2026-09-08）

### 25.1 用户授权、本步缺口与边界

用户明确授权正式开始`M2-22.4R-04 解析质量门禁与拒绝索引`。R-01至R-03已经分别解决“健康PDF被错误覆盖”“Docling故障污染主进程”和“DOCX页眉/原位图片文字缺失”，但修复前仍少最后一道发布门：Router即使得到明显截断、某页未恢复或大图OCR为空的结果，也可能把它包装成成功产物，后续索引无法区分干净数据与脏数据。

本步输入是Native Artifact、最终选中的Canonical Artifact、R-01 Native健康决定以及R-03写入的DOCX图片来源；输出是严格、版本化的`m2-post-parse-quality-v1`质量决定。决定通过才允许Parser Service发布Parsed Artifact；决定拒绝时沿既有补偿路径标记Parse/File/Index失败，且不留下解析产物或Index Set。本步只建立“发布前检查与拒绝”并重跑18文档Parser评估，不运行M2-22.5 Chunk质量矩阵，不为通过文档建立索引，也不运行Embedding、pgvector、检索、Reranker、Context、Agent、Qwen或Ragas。

### 25.2 大白话运行过程与确定性规则

大白话理解：R-01至R-03像是把读文件的眼睛修好，R-04则是在仓库门口加一个质检员。解析器读完后，结果先不能直接贴上“可入库”标签；质检员会把Native底稿和最终稿对照，还会逐页看PDF、逐张看DOCX图片。任何明确异常都会退货，普通可疑情况会带着告警放行，只有通过后才写入Parsed Storage并进入`ready`。

规则固定如下：

1. 只有R-01判断为`healthy`且Native有效字符大于0时才做全文保留率比较；最终有效字符数小于Native的70%才拒绝，恰好70%允许通过，避免把本来就需要OCR增强的扫描件拿一个不可靠Native分母误判；
2. PDF按真实`page_number`统计正文和表格文字。最终某页少于10字符，而Native同页至少50字符时拒绝为`pdf_page_text_regression`；Native同页也少于10字符但存在图片/扫描信号，且最终仍少于10字符时拒绝为`pdf_image_page_ocr_unrecovered`；Native少于10字符且没有图片信号时当作真实空白页，不拒绝。Native处于10至49字符的灰区不凭空下结论；页数不一致也拒绝，避免末页整体消失却被总字符数掩盖；
3. DOCX只消费R-03的结构化`docx_image_ocr`来源。图片严格大于5 KiB且OCR为空时产生`ocr_possible_failure`告警；若该图片所在段落没有普通文字，或整份正文少于20字符，则升级为拒绝，防止图片型正文整段丢失。恰好5 KiB不触发该规则，有OCR文字则通过；
4. 决定包含Native/最终字符数、保留率、全部阈值、逐页与逐图评估以及唯一拒绝/告警代码。严格反序列化会从这些信号重新计算预期状态和代码，因此不能只把JSON中的`rejected`手工改成`accepted`绕过门禁；
5. Routed Artifact外层合同继续使用`m2-routed-parsed-document-v1`，新质量字段是为了读取历史v1产物而保持可选；但是新的Parser Service发布路径强制要求该字段存在且状态为接受。这样无需数据库迁移，也不会让旧产物突然失读，同时保证所有新解析不能绕过门禁。

这里没有采用“原始PDF某页文件体积大于10 KiB”的规则，因为普通PDF无法可靠、通用地把整个文件字节拆成每页独立体积；强行估算会把共享字体、图片流和对象表误归到某一页。实际实现用Native逐页文字与Native已存在的图片/扫描信号替代，能直接对应“这页本来有字”或“这页应当OCR”两个可验证问题。

### 25.3 修改文件与职责

- `app/services/documents/quality.py`：新增解析后决定、PDF逐页判断、DOCX图片判断和严格自校验；冻结策略版本及70%、10字符、50字符、5 KiB等运行阈值；
- `app/services/documents/parsers/base.py`、`parsers/__init__.py`：新增携带严格质量决定的`DocumentQualityRejected`，对外仍只暴露固定安全错误；
- `app/services/documents/routing.py`：Native或增强路线选定后统一执行质量门禁；拒绝时只记录策略、代码和计数，不记录文件名、路径或正文；接受决定进入Routed Artifact，旧v1形状仍可读取；
- `app/services/documents/parser_service.py`：在序列化和写Storage前再次要求非空且已接受的决定；质量告警计入发布元数据；拒绝复用现有补偿，清理已写对象并把Parse/File标记为失败；
- `app/services/documents/indexing/service.py`：增加只用于依赖注入的可选Docling Provider入口，默认生产行为不变；集成测试借此稳定制造真实“第二页截断”候选并验证Index Service拒绝；
- `app/core/config.py`、`.env.example`：增加四个有界配置及交叉校验，默认分别为0.7、10、50和5120字节；
- `app/evals/rag_runner.py`、`scripts/verify_m2_parser_router.py`：Parser报告保存每份文档的质量决定；完成态报告不允许缺决定，方便复核运行时阈值而不是只看最终分数；
- `tests/unit/test_post_parse_quality.py`：覆盖70%边界、69%拒绝、PDF总字数增长但单页截断、扫描页未恢复、真实空白页、页数不一致、DOCX大图空OCR告警/拒绝/通过、5 KiB边界和JSON篡改反例；
- `tests/unit/test_document_routing.py`、`test_m2_baseline.py`、`test_m2_parser_evaluation_runner.py`：覆盖Router拒绝、旧v1读取、新配置边界及报告合同；
- `tests/integration/test_document_parser_service.py`、`test_document_index_service.py`：验证发布成功带决定，以及拒绝结果的Parse/File/Index失败、无Parsed Storage和0个Index Set；
- `tests/integration/test_document_index_service.py`：同时把跨月夹具从写死`2026/08`改为使用实际上传返回的Storage Key；只修复测试时间依赖，不放宽生产Storage规则；
- `migrations/env.py`：设置`disable_existing_loggers=False`，避免测试中加载Alembic配置后把应用Logger永久禁用；这是完整回归暴露的测试基础设施修复，不是R-04业务功能；
- 本记录、M2入口与项目总看板：同步实际结果、剩余边界和下一停止点。

### 25.4 完整调用链位置

```text
前端：不修改、不经过
→ 公开API：18文档全量回归复用POST /files与POST /documents；不新增解析参数
→ Schema：公开请求/响应不改；内部Routed Artifact增加可选质量决定
→ Agent / LangGraph / Harness / Tool：不经过
→ File / Document Service：创建解析任务，接收ready或failed结果
→ Storage uploads：读取受控原文件
→ Native Parser → R-01 Native健康决定 → Router选择Native/Docling/Hybrid
→ R-04 Post-Parse Quality Gate
   ├─ accepted：Parser Service复核决定 → 写Parsed Storage → parse_status=ready
   └─ rejected：抛出固定安全失败 → 清理部分对象 → Parse/File失败
      → Index Service停止，0个Index Set
→ Repository / Model / PostgreSQL：沿用既有状态与补偿；无新表、字段或迁移
→ Chunk / Embedding / pgvector / Retrieval / Reranker / Context / Agent / Qwen / Ragas：本步不运行
```

Index Service集成测试只向主链送入一个确定会被质量门禁拒绝的候选，用于证明拒绝后不会建索引；没有对任何合格文档执行Chunk或索引。因此这项验证不能被表述为M2-22.5已经开始。

### 25.5 TDD、全量评估与工程验证

1. 测试先行的首轮RED在导入阶段失败：`POST_PARSE_QUALITY_POLICY_VERSION`尚不存在。先冻结合同和纯函数，再接Router与Service，没有通过删除断言或提高阈值制造GREEN；
2. 纯质量规则最初`6 passed`，加入边界、页数和篡改反例后，与Router合并定向集合为`25 passed`；Parser Service集成为`6 passed`；跨月用例独立为`1 passed in 6.37s`，先运行Alembic再跑R-02日志用例为`6 passed in 11.77s`，质量拒绝的Index Service集成为`1 passed in 7.99s`；
3. 完整单元为`1008 passed, 2 skipped in 48.17s`；Parser/Index/File Reading/Chunk兼容/复杂Seed/Runner相邻集成为`31 passed in 40.91s`；显式真实DOCX RapidOCR Smoke为`1 passed in 8.26s`；
4. 18份正式原件再次经公开上传/建文档API、隔离PostgreSQL/Storage和正式Parser主链，结果`run_status=completed`、18/18解析完成、34/34 Golden、4/4 OCR，事实恢复率均为1.0；路由为Native 16、Docling 1、Hybrid 1，延迟p50/p95/max为186/71,958/71,958 ms；
5. 18个质量决定全部`accepted`且0告警；282个PDF页判断全部接受，1个DOCX图片判断接受；策略均为`m2-post-parse-quality-v1`，运行时阈值统一为0.7/10/50/5120。真实OCR日志只出现固定本地ONNX路径，没有下载；
6. Git忽略报告为`data/evals/runtime/reports/m2_cross_border_parser_report_v1.json`，117,804字节，SHA-256为`f97757f24713d76becb4a9815cee2450a21844e31f45e02965b45fdee8d8d915`。清理后评估数据库行和Storage对象均为0；正式基线恢复为10 files/documents/versions、9 ACL、10个pending版本、10个upload对象，M1库存仍为125；
7. 完整后端原样运行最终为`1287 passed, 14 skipped in 287.79s`，R-03记录的6项失败不再存在：跨月Key夹具改用真实Key，Alembic配置不再关闭既有Logger；
8. 工程门禁：`ruff check app tests scripts migrations`通过；`mypy app`为155个源码通过；`compileall -q app`、`pip check`通过；Alembic current/heads均为`20260905_0011 (head)`，`alembic check`为`No new upgrade operations detected`。本步没有数据库迁移；全范围格式检查仍只报告未修改的`tests/integration/test_document_chunk_set_migration.py`一处既有差异。

### 25.6 能证明、不能证明与排查方向

能证明：70%全文、PDF逐页和DOCX空OCR规则是确定性、版本化且边界已测试的；决定不能靠改状态或删除代码字段绕过；所有新发布解析产物必须带接受决定；明确拒绝会进入失败补偿，不写Parsed Storage、不进入`ready`且不创建Index Set；18份当前固定语料已经恢复34/34原文、4/4 OCR，并在当次阈值下全部通过；完整后端和工程门禁没有遗留失败。

不能证明：34/34原文命中等于所有段落阅读顺序和语义都完美；当前阈值对任意语言、手写体、复杂表格或未来文档都没有误报/漏报；DOCX能提供可靠物理页码；直接在主进程执行的DOCX RapidOCR已经具有R-02那样的硬超时/RSS隔离；高并发总内存和吞吐已达生产要求；Chunk边界、Locator、Embedding、pgvector、检索、Reranker、Context、回答、权限或Ragas质量已经验证。历史已存在且没有质量字段的旧v1 Routed Artifact只是保持可读取，并没有被追溯重验。

若出现`post_parse_quality_rejected`，先看结构化`rejection_codes`，再沿同一决定检查Native/最终字符数、具体PDF页的两路字符数和图片信号，或DOCX图片的字节数、OCR文字、段落文字与正文总量；不要第一反应就降低阈值。若健康文本被70%误拒，先核对R-01健康分类和有效字符统计口径；若扫描页误判为空，先看Native是否真的产生图片信号；若DOCX只告警未阻断，确认正文是否足够且图片所在段落是否有文字；若拒绝后仍出现解析对象或Index Set，优先查Parser Service发布顺序、补偿清理与Index Service异常传播。性能问题则区分Docling子进程和直接DOCX OCR路径，不能把质量阈值当作资源隔离手段。

R-04完成当时在此停止；当时的下一动作是等待用户理解并单独授权`M2-22.5 Chunk质量矩阵`。该授权和实际结果后来已记录在第27节。

## 26. 2026-09-08｜RAG后意图识别与执行分流顺序调整

### 26.1 用户确认与当前缺口

用户明确确认：暂不扩展时间约束、来源权威性评分或复杂对比；完成RAG分层评估后，紧接着先实施意图识别与执行分流，再进入M2-22.9多Agent轨迹评估。

当前公开消息POST已在M2-21.10迁移到唯一Agent Gateway，但还没有在Supervisor前实施独立的意图/复杂度分流。现有真实Business Worker集成基线已记录：单一商品或库存请求也会产生6次模型调用，规格加库存为7次。因此，若在改造前就生成M2-22.9最终轨迹报告，报告只代表即将被替换的旧执行路径。

### 26.2 冻结的顺序与最小范围

后续顺序冻结为：

```text
M2-22.5～M2-22.8 RAG分层评估与用户复核
→ M2-22.8R 意图识别与执行分流
→ M2-22.9 改造后的最终多Agent轨迹评估
→ M2-22.10 正式集、Bad Case和阶段收口
→ M2-23 前端
→ M2-24 最终演示与M2收口
```

M2-22.8R的最小目标不是只给用户消息贴上意图标签，而是让标签真正决定执行路径：

```text
简单单一查询 → 快速路径，绕过Supervisor
固定复合查询 → 受控Pipeline
确需规划的复杂任务 → Supervisor/Worker
信息不足 → 安全追问
当前不支持 → 明确unsupported
```

分流不能被实现为“所有请求先固定调一次LLM分类”。候选策略是两层：程序只对能够稳定验证的高置信明确请求直接分流；无法确定时，再用一次严格结构化模型输出同时给出意图、路径和可校验的业务参数。模型输出低置信、参数不全或Schema非法时安全追问或返回unsupported，不把不确定请求默认升级为高成本Supervisor路径。

这些数字只是后续实施方案要校准的调用目标，不是已实现结果：

| 路径 | 待校准模型调用目标 | 理由 |
|---|---:|---|
| L0直接回答 | 通常1次 | 分类与回答不再拆成两次 |
| 高置信明确Business查询 | 0次 | 程序分流、Tool执行、确定性格式化 |
| 不确定Business查询 | 最多1次 | 一次同时完成意图、路径和参数提取，Tool后不固定再调模型 |
| Knowledge问答 | 通常1至2次 | 高置信程序路由后只需RAG回答；路由不确定时才增加一次结构化判断 |
| 固定复合Pipeline | 通常不超过2次 | 一次理解/参数提取和最多一次有必要的跨源综合，独立Tool并行 |
| L3 Supervisor/Worker | 按树形预算有界计数 | 只有复杂任务支付规划、Handoff和恢复成本 |

本步只使用M2已有Business/Knowledge能力，不新增Worker、Tool、Web研究、时间约束、权威性评分、动态通用DAG或M4能力。详细路由合同、实现文件、模型/规则边界、降级策略和门禁阈值，必须等M2-22.8的实际RAG结果已知后再提交完整方案，本次文档更新不自动授权代码开发。

### 26.3 调用链位置、验证和边界

本次实际只修改总进度看板、M2入口和本过程记录，位于方案/进度层；未经过前端、API、Schema、Agent/LangGraph、Harness、Tool、Service、Repository/Model、PostgreSQL/pgvector、Storage或外部Provider。

后续M2-22.8R必须验证路由准确率、路径选择、任务完成、Tool/Evidence一致性、模型调用数、Token、成本与p50/p95；至少要有单Business、单Knowledge、Business+Knowledge固定复合、复杂Supervisor、需要追问和unsupported用例。M2-22.9只能在该改造完成后评估最终轨迹。

文档验证已完成：对三份文档运行`git diff --check`无错误，仅有Git对现有LF/CRLF工作区转换的提示；`rg`复核确认总看板、M2入口、M2-22步骤、调用链和完成标准均使用“M2-22.8 → M2-22.8R → M2-22.9”顺序，旧版步骤数量和RAG后直接进入.9的表述均已清除；三份文档的Markdown代码栅栏数量均为偶数。

本次能证明用户确认的顺序、最小范围、后续验证方法和停止点已进入正式记录；不能证明意图识别、快速路径或固定Pipeline已实现，也不能证明现有6/7次模型调用已降低。该文档调整完成当时的下一动作是等待用户单独授权M2-22.5；后续授权和结果见第27节。

## 27. M2-22.5实施记录：Chunk质量矩阵（2026-09-08）

### 27.1 用户授权、当前缺口和本步输入输出

用户正式确认并授权只实施`M2-22.5 Chunk质量矩阵`，明确禁止提前实现M2-22.6或后续步骤，禁止安装/运行Ragas，也禁止运行Embedding、pgvector、检索、Reranker、Context、Agent、Qwen和前端功能。

本步开始前缺少的不是另一个Chunk算法，而是一把统一的“尺子”：R04已经证明18份文档的Canonical Parser Artifact恢复34/34事实，但还不知道现有Chunk流程是否会把完整答案、标题、段落、表格、页眉、图片OCR文字和前后文切坏，也不知道当前`600/700/100`与其他完整配置相比表现如何。

输入固定为：18份经过公开上传与建文档API、正式Parser Service和R04质量门禁的Canonical Parser Artifact；34条已有Golden Evidence；四组冻结完整Chunk配置。输出为：首轮4配置矩阵、按冻结规则选出的候选、只改变overlap 80/100/120的第二轮矩阵、逐文档/逐Golden归因、公开安全JSON报告，以及清理后的正式数据库/Storage基线。本步没有用后续检索分数倒推Chunk参数。

### 27.2 实现与指标规则

1. 首轮固定比较`target/max/overlap=400/500/100`、`500/600/100`、`600/700/100`、`700/850/100`，其余`heading_context_max_tokens=120`、`table_row_overlap=1`、`repeated_edge_min_pages=2`、表头重复、隐藏Sheet、归一化器、Chunker和Token Counter身份全部相同；
2. 候选选择只看首轮结构质量，优先Golden完整包含与Locator、证据范围覆盖、边界破坏和标题/表格保留，再看空块、近重复和Chunk数量；没有检索与存储收益证据时不把“大块更少”直接解释为生产最优；
3. 第二轮只对首轮候选`chunk-large`改变`text_overlap_tokens=80/100/120`，其他字段保持不变；
4. Golden先检查证据原文是否存在于Parser Artifact，再检查是否完整落在至少一个Chunk，最后检查该Chunk的真实页码/source span、DOCX来源或表格坐标能否覆盖Golden Locator；失败分别归因`parser_artifact`、`chunk_rule`、`locator`；
5. 结构检查覆盖段落、Parser标题提示、表格行、DOCX页眉/页脚、图片OCR、图片前后文链接、重复页眉/页脚排除和段落/句子边界；基础检查覆盖Token min/p50/p95/max、显式重叠率、空块、近重复、Chunk来源顺序、全量Locator完整性和同输入同配置的字节级重复构建；
6. Evidence跨Canonical换行或多个连续文本来源块时，Locator允许多个真实source span共同覆盖中间仅为空白的间隔；DOCX表格使用Canonical表格坐标。评估器不伪造连续范围或DOCX物理页码。

### 27.3 修改文件与职责

- `app/evals/chunk_metrics.py`：新增纯确定性Chunk质量计算、三层失败归因、结构审计、Token/重叠/重复/顺序/Locator/确定性聚合和首轮候选选择；不修改生产Chunker；
- `app/evals/rag_runner.py`：在既有Parser Runner旁新增显式`--stage chunk`入口；为18份文档建立隔离评估租户，经现有API、Parser Service与`DocumentChunkService`运行矩阵，读取正式发布Chunk Artifact、内存重建比对，最终精确清理租户数据库行和Storage对象；默认Parser入口保持不变；
- `app/schemas/evaluation.py`：让评估配置完整冻结既有`repeated_edge_min_pages=2`，避免报告身份漏掉实际参与Chunk的配置字段；没有改生产默认值；
- `tests/unit/test_rag_chunk_metrics.py`：覆盖DOCX页眉/页脚/图片OCR与前后文、Parser/Chunk/Locator三层归因、候选并列规则和跨换行多source span Locator；
- `tests/unit/test_rag_evaluation_contracts.py`：补充完整Chunk配置身份断言；
- `tests/integration/test_m2_rag_chunk_runner.py`：以4份真实类型子集验证公开摄取、正式Parser/Chunk Service、4组首轮和候选重叠扫描、Golden Locator、确定性、公开安全报告及数据库/Storage恢复；
- 本过程记录、M2阶段入口和项目总看板：同步实际矩阵、失败事实、验证边界与停止点。

### 27.4 完整调用链位置

```text
前端：不经过、不修改
→ API：仅复用 POST /files 与 POST /documents 登记18份评估文档
→ Schema：公开请求/响应不改；内部评估Schema冻结完整Chunk配置与报告
→ Agent / LangGraph / Harness / Tool：不经过
→ File / Document Service → Storage uploads
→ Parser Router / R04质量门禁
→ Canonical Parser Artifact / Parsed Storage
→ 现有 DocumentChunkService
→ StructureAwareDocumentChunker + UnicodeMixedTokenCounter
→ Canonical Chunk Artifact
→ DocumentChunkSet / PostgreSQL + Chunk Storage
→ 项目确定性Chunk评估器
→ 精确清理评估租户、ChunkSet和Storage对象
→ Embedding / pgvector / Retrieval / Reranker / Context / Agent / Qwen / Ragas / 前端：全部停止，未运行
```

### 27.5 正式18文档、34 Golden矩阵结果

正式命令为`.venv\Scripts\python.exe -m app.evals.rag_runner --stage chunk --enable-docling`。最终Run为`m2-22.5-20260908t091241-0ada274d`，`run_status=completed`、18份文档、34条Golden全部完成，但`quality_gate_passed=False`。`completed`只代表矩阵和清理完整，不代表质量通过。

| 配置 | Chunk数 | Token min/p50/p95/max | 显式重叠率 | Golden内容/Locator | 段落保留 | 边界断裂 | 标题 | 表格行 | 门禁 |
|---|---:|---|---:|---|---|---|---|---|---|
| compact 400/500/100 | 800 | 2/387/400/496 | 24.41% | 34/34；34/34 | 9683/9687 | 4/9750 | 109/152 | 45/45 | False |
| medium 500/600/100 | 611 | 2/486/500/598 | 19.19% | 33/34；33/34 | 9686/9687 | 1/9750 | 109/152 | 45/45 | False |
| current 600/700/100 | 506 | 2/586/599/695 | 15.90% | 33/34；33/34 | 9687/9687 | 0/9750 | 109/152 | 45/45 | False |
| large 700/850/100 | 429 | 2/684/699/848 | 13.28% | 34/34；34/34 | 9685/9687 | 2/9750 | 109/152 | 45/45 | False |
| large 700/850/80 | 419 | 2/682/699/847 | 10.62% | 33/34；33/34 | 9686/9687 | 1/9750 | 109/152 | 45/45 | False |
| large 700/850/100 | 429 | 2/684/699/848 | 13.28% | 34/34；34/34 | 9685/9687 | 2/9750 | 109/152 | 45/45 | False |
| large 700/850/120 | 441 | 2/684/699/805 | 16.00% | 34/34；34/34 | 9687/9687 | 0/9750 | 109/152 | 45/45 | False |

所有7组均为18/18文档来源顺序正确、18/18全量Locator完整、18/18重复构建字节一致、0空Chunk；近重复分别为1/1/1/2/1/2/1。合成与真实跨境、digital与OCR分别单列，没有混成一个看不出问题的总分。

首轮候选是`chunk-large`；在它的重叠扫描中，120是本轮结构指标最完整的组合：34/34 Golden与Locator、9687/9687段落、0边界断裂、45/45表格，Token最大805没有超过850，显式重叠16.00%。这只是本步候选证据，不是生产默认参数变更，也不能在检索尚未运行时宣布最终最优。

真实通过项包括：表格行45/45；图文DOCX的页眉1/1、页脚1/1、图片OCR 1/1、图片前后文1/1；OCR组4/4 Golden；所有正确包含的Golden都有真实Locator，最终0个`locator`失败。最初发现的跨换行与DOCX表格误报属于评估器Locator判定缺陷，修正并补反例后重新完整运行，最终报告没有保留错误分数。

真实失败项归因如下：

- 全部配置的标题都是109/152。`m2-complex-v1-two-column-market-brief`为2/6，因为Parser Artifact在一个物理文本行内保存左右栏两个标题，现有Chunker只做整行标题精确匹配；`eu-vat-oss-guidelines-2026-en`为32/64、`eu-gpsr-factsheet-2023-en`为6/11、`eu-safety-gate-alert-10001641-en`为2/4，均是Parser标题提示存在但没有作为对应Chunk正文中的独立标题保留，归因`chunk_rule`；
- `smoke-ext-025-ioss-coverage`在medium/current只由单Chunk覆盖96.59%，在large-overlap-80只覆盖75%，所以三组均为33/34并归因`chunk_rule`；compact、large-overlap-100和120能完整包含它；
- compact/medium/large/large-overlap-80/100分别有4/1/2/1/2个段落或句子边界断裂；current和large-overlap-120为0。没有通过降低R04阈值、放宽Golden或修改生产默认值掩盖这些差异。

### 27.6 测试与工程验证

1. 指标模块首轮RED在导入缺失模块时失败；实现后新增4个专项单测全部通过。最终专项集合`tests/unit/test_rag_chunk_metrics.py + test_rag_evaluation_contracts.py + tests/integration/test_m2_rag_chunk_runner.py`为`84 passed in 36.77s`；
2. 相邻Parser/Artifact/Chunk单元为`173 passed, 2 skipped in 25.10s`；
3. 相邻上传/Parser/Chunk集成组合为`21 passed, 3 skipped, 6 errors in 69.44s`。6个error全部来自旧`tests/integration/test_file_api.py`的module夹具在正式10份文档版本仍引用文件时执行无条件`DELETE FROM files`，PostgreSQL复合外键在setup阶段拒绝；尚未进入本步Runner、指标或Chunk代码。该范围外测试隔离问题没有被删除、改断言或清空正式基线来制造通过；
4. 在明确禁止下游功能的边界内，完整允许范围单元回归为`442 passed, 2 skipped in 31.48s`，完整允许范围数据库/服务集成为`60 passed, 3 skipped in 100.62s`；没有运行全仓原样pytest，因为其中会实际执行用户明令禁止的Embedding、pgvector、检索、Reranker、Context、Agent和Qwen功能；
5. `ruff check app tests scripts migrations`通过；`mypy app`为156个源码通过；`compileall -q app`、`pip check`、`git diff --check`通过；Alembic current/heads均为`20260905_0011 (head)`，`alembic check`为`No new upgrade operations detected`。本步无迁移；
6. 本步3个需要格式化的文件已修正并通过定向格式检查；全范围格式检查为336个文件正确，只剩未修改的既有`tests/integration/test_document_chunk_set_migration.py`一处CRLF差异。

### 27.7 报告、清理和正式基线

Git忽略的正式报告位于`data/evals/runtime/reports/m2_cross_border_chunk_report_v1.json`，大小498,013字节，SHA-256为`37bf809c654af1eb92cfb777165aba274fdf6307e7e8befc220cbcf44c69f3e7`；报告只保存公开Source ID、配置、Hash、计数、比例和失败层，不保存Chunk正文、绝对路径、Storage Key、tenant/user UUID、口令或数据库URL。

Runner退出前的清理结果以及回归后的独立复核均为：评估数据库行0、评估ChunkSet 0、评估Storage对象0；正式files/documents/versions各10、ACL 9、pending版本10、upload对象10、正式ChunkSet 0、M1德国仓可售库存125，`baseline_restored=True`。一次性能诊断期间人工停止的中间运行曾留下1个隔离评估租户和90个ChunkSet，已按精确租户/对象键清理并验证正式基线后才重新运行；该中间结果没有被当作正式报告。

### 27.8 能证明、不能证明与排查方向

能证明：18份当前固定文档在同一R04合格Artifact上真实经过现有Chunk Service；四组完整配置和候选重叠扫描可重复；Golden内容、证据范围与真实Locator可以分层判断；表格、DOCX页眉/页脚/图片OCR及前后文在所有配置均保留；至少`700/850/120`能同时达到34/34、完整段落、0边界断裂、Token上限、顺序、Locator和字节确定性；当前标题保留不足是可复现的Chunk规则问题，不是Parser原文缺失或Locator评估误报；评估数据已经清理且正式基线未被污染。

不能证明：`700/850/120`在真实检索、Reranker、Context或回答中一定最优；109/152标题可以被忽略；近重复率已经达到未来生产目标；18份/34条覆盖所有语言、PDF版面、表格或OCR噪声；DOCX具备物理页码；生产默认配置已经改变；M2-22.6或任何后续RAG/Ragas质量已经验证。M2-22.5的执行工作完成不等于质量门禁通过。

若Golden不完整，先看它在Parser Artifact是否逐字存在；存在但没有单Chunk完整覆盖时查Chunk窗口、段落/句子边界和overlap；内容完整但Locator失败时查页码/source span、DOCX来源或表格坐标。若标题缺失，优先对照`heading_hints`与Artifact原始行，再查Chunker的整行精确匹配和两栏/组合标题拆分，不要降低R04阈值。若表格断裂，查行分组、重复表头与source row；若DOCX图片失去前后文，按段落/Run/图片序号检查Block顺序；若重复构建不同，先查配置Hash、输入Artifact Hash、排序键和非确定性字段。若清理失败，只按隔离评估tenant和已登记对象键排查，禁止全表删除或清空正式Storage。

当前停止。M2-22.5质量矩阵已经完成实际运行，但质量门禁为False；下一动作是等待用户理解本节并决定是否单独授权Chunk规则修复。未经新授权不得修改生产Chunker或默认参数，不得进入M2-22.6，不得安装/运行Ragas，也不得运行Embedding、pgvector、检索、Reranker、Context、Agent、Qwen或前端。

## 28. M2-22.5R确认方案：标题元数据注入与Chunk复验（2026-09-08）

### 28.1 用户确认与当前缺口

用户确认采用标题元数据注入方案，并授权先固化本节文档、随后开始M2-22.5R下一步。核心决定是：不再依赖文本窗口把标题和正文“碰巧切在一起”，而是在切正文前建立可信标题层级，把标题作为正文Chunk的附属属性。

现有实现已经有正确骨架：`DocumentChunk.body_text`保存正文、`heading_path`保存最多9级标题元数据、`retrieval_text`供后续索引使用，数据库`document_chunks.heading_path`也是独立JSONB。当前缺口发生在PDF标题绑定：Chunker把`heading_hints`按规范化文字建表，再用整行`hints.get(line.text)`精确相等判断；一行含编号、标点或多个栏目的标题时，Parser提示虽存在，却不能进入`heading_path`，最终正式矩阵只有109/152。

### 28.2 本修复目标与明确不做

目标：

1. `body_text`只由可定位正文构成，纯标题不作为正文窗口的一部分；
2. `heading_path`保存由Parser Artifact可信提示推导的父子标题层级，并绑定给该标题下至少一个正文Chunk；
3. `retrieval_text`只作为确定性派生视图，由受Token预算约束的标题元数据加正文生成；后续一个章节被拆成多个Chunk时，每个正文Chunk都携带相同标题上下文，不依赖overlap复制标题；
4. 标题元数据必须能回到同一Artifact的提示、页和确定位置；纯标题空壳Chunk、正文短语误报标题、重复页眉/页脚冒充标题、并列标题冒充父子层级均不得算通过；
5. 使用原18份文档、34条Golden和7组矩阵重新验证，并恢复正式数据库/Storage基线。

明确不做：不放宽Golden，不修改R04质量阈值，不用模糊或语义匹配猜标题，不先调整生产Chunk默认参数，不运行Embedding、pgvector、检索、Reranker、Context、Agent、Qwen、Ragas或前端，不进入M2-22.6。Canonical Parser Artifact继续保存原始标题和正文，本修复的“抽离”只发生在Chunk表示中，不删除上游原文。

### 28.3 前置条件与关键语义

- R04正式基线仍为18/18文档、34/34原文、4/4 OCR；
- M2-22.5失败基线固定为标题109/152，当前配置`600/700/100`为33/34 Golden，候选`700/850/120`为34/34、0边界断裂但标题仍109/152；
- 标题、正文和检索视图职责固定如下：

```text
Canonical Parser Artifact：保留原始标题、正文、顺序和Locator
→ 标题绑定器：把可信标题提示转换为当前heading_path
→ body_text：只保存正文及真实source spans
→ heading_path：保存标题层级元数据
→ retrieval_text：在Token预算内渲染 heading_path + body_text
→ Chunk Artifact：同时对正文、标题元数据、来源和Hash负责
```

- `heading_path`中的顺序表示父标题到子标题，不表示左右两栏的并列关系；若现有页级提示不能唯一判断双栏标题对应正文，必须停止并提交Parser Artifact字符范围/坐标补充方案，不能在Chunk层猜测。

### 28.4 按顺序实施的小步骤

#### M2-22.5R-01｜元数据合同、真实模式与RED测试

- 目标：冻结`body_text/heading_path/retrieval_text`职责，新增编号标题、标题与正文同行、多级标题、正文短语误报、纯标题空壳和歧义多标题反例；结合4份真实失败文档确认哪些提示能由现有Artifact唯一绑定；
- 预计文件：`tests/unit/test_document_text_chunker.py`、`tests/unit/test_rag_chunk_metrics.py`，必要时只增加测试辅助代码；
- 验证：新增测试必须在旧实现上以预期断言失败，同时既有精确标题、DOCX、表格、重复页眉/页脚和确定性测试保持通过；
- 停止条件：若真实双栏案例缺少唯一绑定所需位置事实，只记录证据并停止，不进入Parser修改。

#### M2-22.5R-02｜确定性标题绑定实现

- 目标：在Token窗口前处理标题；只把同页、精确文本范围、字符边界明确且无冲突的提示更新到标题栈，按level删除同级及更深旧标题；纯标题不进入正文窗口，同行剩余正文保持原字符映射；
- 预计文件：`app/services/documents/chunking/chunker.py`、`tests/unit/test_document_text_chunker.py`；
- 验证：R-01的RED转绿；标题下正文Chunk携带正确`heading_path`，标题不因Chunk窗口或overlap丢失，正文source spans、Token硬上限和字节确定性不回归；
- 边界：若需要新增Parser字符范围/坐标，先停止并提交本节增补与用户确认，不自动修改`pdf.py`、`native.py`或Artifact合同。

#### M2-22.5R-03｜质量门禁防伪与报告语义

- 目标：标题通过必须同时满足“来自真实提示、位于Chunk元数据、绑定至少一个正文Chunk、层级正确”，不能靠复制字符串或标题空壳制造152/152；
- 预计文件：`app/evals/chunk_metrics.py`、`app/evals/rag_runner.py`、`tests/unit/test_rag_chunk_metrics.py`及Runner集成测试；
- 验证：伪造heading_path、标题仅在`body_text`、只有标题无正文、并列标题伪装层级均失败；每组配置继续独立保存门禁结果。矩阵总完成状态与候选质量状态分离：故意用于比较的失败配置继续保留，只有至少一个按冻结规则选出的候选满足全部质量条件时才能声明候选门禁通过，不用“所有实验配置必须同时通过”制造不可解释结论，也不删除失败配置。

#### M2-22.5R-04｜正式矩阵复验与清理

- 目标：复用原18份文档、34条Golden、4组首轮与候选overlap 80/100/120，重跑正式Parser→Chunk矩阵；
- 预计文件：不预设生产代码；生成Git忽略报告并更新本记录、M2入口和总看板；
- 验证：18/18 R04、34/34内容与Locator、标题152/152且每个标题绑定正文、段落与表格完整、DOCX视觉上下文、Token范围、重叠、顺序、Locator、确定性及精准清理；
- 停止点：无论通过或失败都先向用户解释；不得自动更新生产默认配置或进入M2-22.6。

### 28.5 完整调用链位置

```text
前端：不经过
→ API：仅正式复验时复用上传/建文档入口
→ Schema：公开请求/响应不改；复用Chunk的heading_path元数据
→ Agent / LangGraph / Harness / Tool：不经过
→ Parser/R04 → Canonical Parser Artifact
→ Chunk标题绑定器 → heading_path
→ 正文分组与Token窗口 → body_text
→ 标题元数据 + 正文 → retrieval_text
→ Canonical Chunk Artifact → Chunk Storage / DocumentChunkSet
→ Chunk质量评估与精准清理
→ Embedding / pgvector / Retrieval / Reranker / Context / Agent / Qwen / Ragas / 前端：不运行
```

基础方案复用现有`heading_path`和数据库JSONB，不需要迁移；只有证据证明现有Artifact缺少双栏唯一定位时，才另行讨论Parser元数据扩展。

### 28.6 阶段完成标准

M2-22.5R只有同时满足以下条件才可完成：

- 元数据合同和反例测试已冻结，旧实现RED、修复后GREEN；
- 真实标题不能只靠字符串出现或标题空壳通过；
- 至少一个冻结候选达到34/34 Golden与Locator、152/152标题且全部绑定正文、0可避免边界断裂、45/45表格、DOCX页眉/页脚/图片OCR/前后文完整、18/18顺序/Locator/确定性、0空Chunk并满足Token硬上限；
- 其他失败实验配置和Bad Case仍完整保留；
- 专项、相邻和明确排除下游功能的完整允许范围回归已实际运行；
- 评估租户数据库行、ChunkSet和Storage对象归零，正式10份文档、0正式ChunkSet与M1库存125恢复；
- 三份进度记录同步实际通过或失败，用户理解后再决定生产参数或M2-22.6。

### 28.7 主要风险与排查方向

- 标题误报：先查提示是否在同页唯一精确出现及字符边界，不允许模糊匹配正文短语；
- 标题层级错误：按level维护父子栈，同级标题必须替换旧同级，不把并列栏目标记成父子；
- 标题空壳：要求标题元数据绑定至少一个非标题正文单元，评估器不计只含标题的Chunk；
- 双栏歧义：若页级文字顺序不足，停在Artifact定位层，不凭标题出现顺序猜正文归属；
- Token回归：`retrieval_text`中的标题仍计入`max_tokens`，长标题路径按现有有界策略渲染，完整`heading_path`元数据不因渲染截断而丢失；
- Locator与Hash：正文字符映射保持真实，标题元数据、配置和输入Artifact都参与确定性Chunk Hash；
- 参数混淆：先只改标题绑定，复验后再比较原7组参数，不把算法与生产默认值同时改动。

### 28.8 本次文档固化结果与下一动作

本节已记录用户确认、输入输出、完整链路、四个小步骤、每步文件与验证、完成标准、风险和禁止范围。当前授权允许随后开始R-01元数据合同与RED测试；在R-01完成并记录前不进入R-02，实现期间若发现双栏需要Parser定位扩展则必须停止等待确认。

## 29. 2026-09-08｜意图分流模型调用原则补充

### 29.1 用户确认与本次目标

用户指出：如果先单独调用一次大模型做意图识别，再调用一次大模型生成答案，那么即使增加了L0至L3分流，简单请求仍然至少需要两次模型调用，成本和延迟问题并没有真正解决。用户确认先更新相应文档，本次不授权M2-22.8R代码开发。

因此补充冻结以下设计原则：**意图识别是一层路由能力，但不等于所有请求都固定新增一次LLM调用。** 候选方案采用两级分流：能够被程序高置信识别的明确请求直接进入对应路径；只有表达含糊、信息不足或可能跨路径的请求，才调用一次输出严格结构化结果的模型，并尽量在这一次结果中同时完成意图、执行级别、工具路由和业务参数提取。

暂定模型调用目标如下：

- L0普通问答不把“分类”和“回答”拆成两次独立调用，通常共用一次回答模型调用；
- 明确且高置信的Business查询允许0次模型调用，由程序解析受限参数、调用Tool并用确定性模板返回；无法可靠解析时，最多用1次模型同时完成意图判断和参数提取；
- Knowledge问答只保留必要的检索后有依据回答，通常为1至2次模型调用，是否需要模型路由取决于程序分流置信度；
- 固定复合查询使用受控Pipeline，并行执行相互独立的Tool，典型目标不超过2次模型调用；
- 只有真正需要拆解、追问、冲突处理或多轮研究的L3请求才进入Supervisor与Worker，并受轮次、Token、成本和超时预算约束。

以上数字是M2-22.8R方案阶段需要用轨迹和成本实验验证的**候选目标**，不是当前已经实现或已经达标的能力。具体的高置信规则、置信度阈值、结构化Schema、失败回退和澄清策略，应在M2-22.8完成后提交M2-22.8R完整实施方案时再确认；不得仅用不断扩张的关键词表冒充通用自然语言理解。

### 29.2 本次修改文件与职责

1. `docs/PROJECT_PROGRESS.md`：在总进度看板冻结“不固定新增一次LLM”的项目级决策，并写入近期记录；
2. `docs/progress/M2/M2_KNOWLEDGE_RAG.md`：在M2阶段入口补充执行分流原则、成本风险和后续验证指标；
3. `docs/progress/M2/records/M2_22_CROSS_BORDER_RAG_EVALUATION_PLAN.md`：细化M2-22.8R的范围、暂定模型调用目标、验证维度和本次用户确认记录。

### 29.3 调用链位置

本次只更新设计和进度文档，没有经过或修改“前端 → API → Schema → Agent/LangGraph → Harness → Tool → Service → Repository/Model → PostgreSQL/pgvector/Storage/外部Provider”中的任何运行时代码。未来M2-22.8R实施时，主要位于API之后、Agent/LangGraph和Tool之前的执行分流层，并通过Harness轨迹记录真实调用次数、Token、成本和延迟。

### 29.4 验证、边界与排查方向

验证方法：检查三份文档中的核心原则、层级目标和阶段顺序是否一致；检查Markdown代码围栏、冲突标记和行尾空白；检查本次范围是否只涉及文档。

实际结果：三份文档均检索到“不固定新增一次LLM”“程序高置信分流”“低置信结构化模型”和候选调用目标；Markdown代码围栏数量均为偶数，行尾空白和冲突标记均为0；范围内`git diff --check`无错误，仅提示Git未来可能把现有LF转换为CRLF。

能证明：设计口径已经明确区分“存在意图路由能力”和“固定增加一次模型调用”，并给出了后续可以测量的调用次数目标。

不能证明：意图路由已经实现、程序规则能够覆盖真实用户表达、模型调用次数已经下降，或准确率、Token、成本、p50/p95延迟已经达标。这些必须等M2-22.8R代码实现和真实轨迹实验后才能确认。

未来若实际调用次数超过目标，优先检查：是否把分类和回答机械拆成两次模型调用；明确Tool请求是否被错误送入Supervisor；工具结果是否在不需要推理时又交给模型润色；低置信请求是否缺少结构化路由和澄清回退。

本次文档补充不改变当前开发停点：M2-22.5R标题元数据注入修复方案已经获得授权，下一动作仍是R-01元数据合同、真实失败模式和RED测试；不得因本次文档调整提前开始M2-22.8R代码开发。

## 30. M2-22.5R-01实施记录：合同反例与真实提示审计（2026-09-08）

### 30.1 本步目标、输入输出与调用链

本步只执行已确认方案中的R-01，不修改生产切块策略。输入是现有`ArtifactHeadingHint`、Canonical Parser Artifact中的页级最终文本、现有Chunk输出，以及4份标题指标失败文档；输出是可执行反例、真实提示分类证据和是否具备进入R-02的判断。

调用链位置如下：

```text
R04通过的Canonical Parser Artifact
→ 只读审计heading_hints与最终页文本的关系
→ 现有DocumentTextChunker合同反例
→ Chunk标题质量指标防伪反例
```

本步不经过前端、公开API、Agent/LangGraph、Harness、Tool、Embedding、pgvector、检索、Reranker、Context、Qwen或Ragas，也不写PostgreSQL与Storage。

### 30.2 修改文件与职责

1. `tests/unit/test_document_text_chunker.py`：新增3个合同反例，分别冻结“编号/同行标题进入元数据且不进入正文”“父子标题路径绑定正文且不产生标题空壳”“正文中的标题短语不得被提升为元数据”；
2. `tests/unit/test_rag_chunk_metrics.py`：新增质量门禁反例，要求仅把标题写入`heading_path`、但Chunk没有正文时不得计为标题保留；
3. `docs/PROJECT_PROGRESS.md`：同步R-01真实结论、停止点和验证基线；
4. `docs/progress/M2/M2_KNOWLEDGE_RAG.md`：同步M2阶段当前状态、阻塞和下一动作；
5. 本过程记录：保存完整诊断证据，并明确修订前置条件。

没有修改`app/services/documents/chunking/chunker.py`、Parser、Artifact Schema、R04阈值、生产Chunk默认参数、数据库迁移或任何下游RAG实现。

### 30.3 RED测试实际结果

执行：

```text
.venv\Scripts\python.exe -m pytest tests/unit/test_document_text_chunker.py tests/unit/test_rag_chunk_metrics.py -q
```

实际结果为`3 failed, 14 passed in 8.45s`。3个失败均为R-01预期RED：

- 编号标题`2. IOSS适用范围`没有进入`heading_path`；
- 多级案例只保留父标题，没有把编号子标题绑定给正文；
- 现有标题指标把只有标题、没有正文的空壳Chunk错误计为通过。

正文短语不误提升的反例和原有14个相关测试保持通过。`ruff format --check`显示测试文件无需改格式，`ruff check`定向检查通过。这组RED不是产品回归通过结论，而是用可重复失败冻结待修复合同；生产代码尚未修改，所以本步没有伪称已经完成专项、相邻或完整GREEN回归。完整回归仍属于R-04正式复验的强制完成条件。

### 30.4 真实文档提示审计

使用现有本地评估源和原生PDF解析器，只读比较每条提示与同页规范化最终文本，没有上传、建文档、写数据库或运行Chunk之后的任何功能。分类规则是：整行精确出现、在单一物理行内唯一出现、出现位置歧义、最终页文本中缺失。

| 文档 | 提示总数 | 整行精确 | 同行唯一子串 | 歧义 | 最终页文本缺失 |
|---|---:|---:|---:|---:|---:|
| 双栏市场简报 | 6 | 2 | 4 | 0 | 0 |
| 欧盟VAT OSS指南 | 64 | 24 | 8 | 1 | 31 |
| 欧盟GPSR事实表 | 11 | 2 | 6 | 0 | 3 |
| Safety Gate通报 | 4 | 1 | 3 | 0 | 0 |
| 合计 | 85 | 29 | 21 | 1 | 34 |

代表性事实：双栏文档的“左栏｜销量观察”和“右栏｜动作建议”被压在同一物理文本行内；OSS的若干一级提示实际是正文项目符号句；GPSR的`EUR 11.5 billion per year`是数据而非标题；Safety Gate的`Alert number`和具体编号是字段名/字段值组合。代码合同也把`ArtifactHeadingHint`定义为“保留的来源标题线索，不能提升为保证为真的事实”。

### 30.5 结论与问题重新归因

标题元数据注入这个架构方向仍然成立：可信标题应该进入`heading_path`，正文留在`body_text`，`retrieval_text`由两者确定性派生。但R-01推翻了原验收分母：152条`heading_hints`不是152条可信标题，109/152只能表示现有Chunker消费了多少启发式提示，不能直接解释为“43个真实标题被切坏”。

如果继续要求152/152，最容易出现的假通过就是把项目符号、金额、字段值和缺失提示全部硬塞进Chunk元数据。这既违背“不得放宽或伪造Golden”，也会污染后续检索。因此第28.6节中的`152/152`完成标准自本次证据起暂停使用；它是已确认方案形成时的历史假设，不能在用户确认增补前静默改成另一个数字。

问题现在分成三层：

- `Parser Artifact`层：`heading_hints`是候选线索，且通常只有页码、文本和层级，没有统一字符范围、栏位或正文归属；
- `Chunk规则`层：当前整行精确匹配确实漏掉编号标题和可唯一定位的同行标题，但这种保守行为同时避免了一部分误提升；
- `Locator/评估`层：把所有提示当正式标题Golden是指标合同错误，需要独立的可信结构标题真值集。

### 30.6 建议增补与停止条件

建议在不修改原34条内容Golden的前提下，单独增加人工复核并版本化冻结的“结构标题Golden”。每条至少记录来源文档、页、标题原文、层级、与正文的预期关系以及可验证Locator。152条原始提示继续完整保留，用于衡量Parser候选覆盖率和噪声，不再直接作为Chunk标题质量分母。

确认后再依次执行：

1. 先冻结4份失败文档的可信结构标题Golden和明确反例；
2. Chunk层只消费能够在同页、字符边界和顺序上确定性确认的标题；项目符号、字段值、歧义项不提升；
3. 对双栏标题如果现有Artifact仍无法唯一建立“标题属于哪段正文”，停止并提交Parser字符范围/坐标增补，不用左右出现顺序猜父子关系；
4. 修改防伪指标，只接受“可信标题元数据绑定至少一个正文Chunk”；随后才进入正式矩阵和完整清理回归。

能证明：当前152分母不可信；编号/同行标题和标题空壳分别存在生产合同及评估器缺口；直接注入全部提示会制造错误元数据；本步没有污染正式数据库或Storage。

不能证明：可信结构标题的最终数量、现有Artifact足以绑定全部真实标题、生产Chunk策略已经修复、候选参数已经通过、或M2-22.6任何能力已经验证。

根据第28.4节已经确认的停止条件，R-02未开始。下一动作是等待用户理解并确认：是否把正式标题验收从“全部152条启发式提示”修订为“人工冻结的可信结构标题Golden”，同时保留152条提示作为Parser诊断数据。未经确认不得实现生产标题绑定，也不得进入M2-22.6。

用户随后明确确认该口径并授权开始，实际实施见第31节；本段保留为当时停止点，不再代表当前状态。

## 31. M2-22.5R-01A实施记录：可信结构标题Golden冻结（2026-09-08）

### 31.1 用户确认与本步范围

用户确认把正式标题验收从“全部152条启发式提示”修订为“人工冻结的可信结构标题Golden”，同时保留原提示作为Parser诊断数据，并授权开始实施。本步只冻结4份原标题指标失败文档的真值合同和数据，不修改Parser、R04、生产Chunker、Chunk默认参数、34条内容Golden、数据库或Storage。

输入是4份问题文档的原始PDF视觉版面、Native Parser最终页文本和85条`heading_hints`；输出是版本化候选分类、组合标题、禁止提升反例和“标题路径→正文锚点”关系。调用链只到评估合同：

```text
原始PDF视觉版面 + Native Parser heading_hints/最终页文本
→ 人工逐项分类
→ 可信独立标题 / 组合标题片段 / 非标题
→ 可信heading_path与正文锚点Golden
```

没有经过API、Agent/LangGraph、Harness、Tool、Repository/Model、PostgreSQL、Storage、Embedding、pgvector、检索、Reranker、Context、Qwen、Ragas或前端。

### 31.2 真值数据与合同

新增`m2-chunk-heading-golden-v1`数据，SHA-256为`93428d44fe539ed4eafbed6b80169818fc273c6c675a807de887fa20c3aa9c17`。85条原始提示无遗漏、无重复归属地被分为：

| 来源 | 提示总数 | 可独立作为标题 | 组合标题片段 | 明确不是标题 |
|---|---:|---:|---:|---:|
| 双栏市场简报 | 6 | 6 | 0 | 0 |
| 欧盟VAT OSS指南 | 64 | 28 | 0 | 36 |
| 欧盟GPSR事实表 | 11 | 4 | 2 | 5 |
| Safety Gate通报 | 4 | 0 | 2 | 2 |
| 合计 | 85 | 38 | 4 | 43 |

2个组合标题是`THE NEW GENERAL PRODUCT`+`SAFETY REGULATION`和`Safety Gate`+`Alerts`；它们必须作为一个视觉标题使用，不能把片段伪装成父子章节。43个非标题包括OSS正文项目符号、GPSR栏目眉和金额图表标注、Safety Gate字段名及告警编号。

另冻结26条可信正文绑定案例：双栏4条、OSS 16条、GPSR 5条、Safety Gate 1条。每条都记录来源、文档、物理页、完整`heading_path`、标题原文、非标题正文锚点及`following_flow/same_column`关系。它们是针对已知结构风险的正式Golden，不冒充枚举63页OSS指南中的每一个视觉小标题。

### 31.3 修改文件与职责

1. `app/schemas/evaluation.py`：新增严格、框架无关的标题审计与Golden合同；强制85条提示分区计数一致、每个提示Occurrence只能归类一次、组合标题文本由有序片段构成、正文锚点不得等于标题、同栏关系必须同页、正文与标题必须属于同一文档；
2. `data/evals/m2_cross_border_chunk_headings_v1.json`：保存4份问题文档的38条独立标题、2个组合标题、43条非标题反例和26条可信正文绑定；
3. `tests/unit/test_m2_chunk_heading_golden.py`：冻结版本、数量和文件Hash，重跑Native PDF Parser核对85条提示完整分区，核对26组标题/正文确实存在于声明页，并覆盖分区篡改和跨文档绑定拒绝；
4. 三层进度文档：同步确认、实际结果、停止点和下一方案。

### 31.4 TDD与实际验证

1. 新测试在合同尚不存在时先得到预期RED：收集阶段因无法导入`ChunkHeadingGoldenDataset`而停止；
2. 合同与数据实现后，专项为`5 passed in 14.41s`；
3. 标题Golden、既有评估合同和40条Smoke数据相邻回归为`89 passed in 16.00s`；
4. 全范围Ruff通过，`mypy app`为156个源码文件通过，`compileall -q app`通过；
5. PDF视觉审计临时页图位于受控`tmp/pdfs/m2-heading-audit`，复核后按已验证绝对路径删除，`removed=True`；没有产生数据库/Storage评估数据，因此不需要数据库清理；
6. R-01中故意冻结的3个生产Chunk/指标RED仍等待后续修复，本步没有把它们删除或改成宽松断言。生产代码没有修改，因此完整Chunk矩阵和完整GREEN回归不在本小步伪报为完成。

### 31.5 能证明与不能证明

能证明：4份问题文档的85条Parser提示已经逐项分类；旧152分母中的已知噪声不会再被强行写成标题；26条标题与正文关系有独立、可复查的真值；组合标题、同栏关系和非标题反例已有严格合同；Golden自身防重复、防跨文档和防篡改。

不能证明：生产Chunker已经注入标题；26条案例代表全部文档的所有视觉小标题；双栏标题已经可以由现有Artifact唯一绑定；候选Chunk参数已经通过；18文档正式矩阵、M2-22.6或任何下游能力已经验证。

### 31.6 新发现的确定性阻塞

双栏市场简报视觉上有清晰的左右栏标题和各自正文，但当前Native PDF Artifact把同一高度的左右文字压进同一个页级文本行。例如标题成为“左栏｜销量观察　右栏｜动作建议”，下一行又同时包含左右栏正文。`PdfHeadingHint`只有文字、字体、页码和层级；Native Adapter也没有给提示写入已有的`bounding_box`，正文更没有逐行字符范围与坐标。

因此，Chunk层仅凭当前Artifact无法证明“广告预算属于右栏动作建议”而不是左栏销量观察。按第28节的防猜测停止条件，R-02生产标题绑定没有开始；必须先确认最小Parser Locator增补。

## 32. M2-22.5R-01B已确认方案：PDF行级Locator增补

### 32.1 目标与明确不做

目标是在不改变PDF最终原文、不修改R04阈值的前提下，为Native PDF页增加确定性的行级事实：物理行号、精确文字、在页文本中的真实字符范围、页面坐标，以及标题提示所引用的行。Chunk层随后才能按真实栏位绑定标题与正文。

明确不做：不在Parser里直接生成最终`heading_path`，不使用模糊/语义模型猜标题，不调整Chunk参数，不改34条内容Golden，不运行Embedding、pgvector、检索、Reranker、Context、Agent、Qwen、Ragas、前端，也不进入M2-22.6。

### 32.2 拟按顺序实施

1. **Locator合同与RED**：为PDF Native结果和Canonical Artifact设计有界行级结构；旧Artifact缺省字段仍能读取，新Artifact必须校验页码、行序、字符范围、坐标、提示引用和无重叠关系。先用双栏标题、左右正文、组合标题和映射失败反例冻结测试；
2. **Native提取**：从PyMuPDF现有`dict`行数据保留top-left坐标，并把每个可验证物理行映射回当前页文本的真实字符范围；无法精确映射的行显式省略或拒绝，不伪造offset；
3. **Artifact适配**：Native Adapter确定性写入行级Locator和标题提示坐标/行引用，更新Parser/Adapter身份与Hash；旧v1 Artifact保持向后兼容，新解析的几何字段参与内容Hash；
4. **真实复验并停止**：先验证双栏4组标题正文关系可唯一定位，再验证4份问题PDF及18份R04文档的原文、页数、Golden和质量门禁不回归。通过后仍先向用户解释，才回到既有R-02标题元数据注入。

预计修改`app/services/documents/parsers/pdf.py`、`app/services/documents/artifacts.py`、`app/services/documents/parsers/native.py`及对应Parser/Artifact/路由/真实评估测试；不预设数据库迁移，因为定位事实保存在版本化Artifact中。

### 32.3 完成标准与风险

- 双栏左右标题和正文各自拥有可验证、互不混淆的坐标与真实字符范围；同一视觉行的左右片段不能被合并成一个假标题；
- 标题提示必须引用真实行，正文行不能因字体最大值被提升；组合标题仍由Golden明确判断，不由Parser擅自合并；
- 旧Artifact可读，新Artifact Hash稳定，重复解析字节确定；18份文档R04与34条内容Golden不回归；
- 专项、相邻和禁止下游边界内的完整允许范围回归实际运行；临时数据精准清理并恢复正式基线；
- 如字符范围无法无损映射当前页文本，优先调整Canonical PDF文字组织合同并再次请求确认，不能伪造offset。

主要风险是PyMuPDF的“展示行”与`get_text("text", sort=True)`最终字符串不总是一一对应，尤其是双栏、连字符、旋转文字和图表。排查顺序固定为原始span/line坐标→页文本字符映射→Native Adapter→Artifact校验→Chunk绑定；不能在Chunk层用空格数量或标题出现顺序补猜。

用户随后明确表示“开始下一步”，据此只实施本节R-01B；实际结果见第33节。

## 33. M2-22.5R-01B实施记录：PDF行级Locator增补与验收阻塞（2026-09-08）

### 33.1 本步输入、输出与调用链

本步缺少的不是重新识别152个标题，而是Parser已经看见物理行，却没有把行号、字符位置和坐标交给Artifact。输入是通过既有PDF安全限制的字节流、PyMuPDF `get_text("text", sort=True)`页文本与`get_text("dict", sort=True)`物理行/span；输出是每页有界的`layout_lines`：一基行号、原行文字、可证明时的页文本字符起止、top-left坐标和显式页尺寸，以及每个`heading_hint`引用的物理行与同一坐标。

调用链为：

```text
PDF字节流
→ Native PdfParser（页文本 + 物理行/坐标 + 可证明字符范围）
→ Native Adapter
→ Canonical Parsed Artifact（pdf_layout_lines + heading hint行引用）
→ R04质量门禁
→ 停止
```

专项没有经过Chunker，也没有经过Embedding、pgvector、检索、Reranker、Context、Agent/LangGraph、Harness、Tool、Qwen、Ragas或前端。只有正式R04回归按原有API→Service→Repository/Model→PostgreSQL/Storage链临时摄取18份文档，并在`finally`中精准清理。

### 33.2 实现与防伪规则

1. `app/services/documents/parsers/pdf.py`：Parser身份升为`m2-pdf-v2`；新增严格`PdfBoundingBox`和`PdfLayoutLine`，保留PyMuPDF物理行顺序、页面尺寸和坐标，并用只跨行内空白的逐字匹配回填真实字符范围；找不到不重叠证据时保存`None/None`，不伪造offset；标题提示必须引用同页真实物理行；
2. `app/services/documents/artifacts.py`：新增`ArtifactPdfLayoutLine`和`ArtifactTextBlock.pdf_layout_lines`，校验一基连续行号、页码一致、坐标在页内、字符范围成对/不越界/不重叠、范围原文一致，以及标题引用存在且文字/坐标相同；新字段为空时不参与旧v1载荷序列化，保证旧Artifact Hash可复验，新几何非空时进入内容Hash；
3. `app/services/documents/parsers/native.py`：只把PDF Adapter身份升为`m2-native-pdf-adapter-v2`，DOCX/XLSX/CSV继续使用`m2-native-adapter-v1`；逐项转换行坐标和标题引用；
4. `app/services/documents/parsers/__init__.py`：公开新的PDF行与坐标合同；
5. `tests/fixtures/pdf_factory.py`、`tests/unit/test_pdf_parser.py`、`tests/unit/test_parsed_artifacts.py`：新增同高左右栏合成PDF、真实range/坐标、标题行引用、旧载荷兼容、假range拒绝和几何改变Hash反例；
6. `tests/unit/test_m2_pdf_layout_locator.py`：真实加载4份合成PDF和8份官方PDF，重复解析并核对12/12确定性；检查4份标题问题PDF的38条独立标题和4个组合片段都有真实行/range，并验证双栏4组标题正文位于同一物理半栏。

这里没有把组合标题交给Parser擅自合并，也没有把不能唯一映射的重复表格文字硬塞进某个字符位置。物理行仍保留真实坐标，字符范围明确为空，后续可以区分“有几何事实”和“字符Occurrence不唯一”。

### 33.3 TDD、专项与相邻回归

1. RED：新增测试首次收集因`ArtifactPdfLayoutLine`不存在而报ImportError，证明测试先于实现；
2. Parser/Artifact基础GREEN为`20 passed`；标题Golden与相邻集合随后为`25 passed`；12份PDF真实Locator专项最终通过，4/4双栏同栏关系通过；
3. 禁止下游边界内的完整允许单元范围为`369 passed, 2 skipped, 3 failed in 104.30s`。3个失败与R-01冻结结果相同：编号标题没有进入`heading_path`、父子路径缺少编号子标题、质量指标仍会误收标题空壳；它们等待R-02，不能在本步删除；
4. Parser/Chunk Service、Parser/Chunk Runner和两组合成Seed数据库相邻集成为`21 passed in 86.99s`；
5. `ruff check app tests scripts migrations`通过，`mypy app`为156个源码文件通过，`compileall -q app`与`git diff --check`通过。额外执行的仓库根目录`ruff check .`显示旧`api/`、`config/`、`tools/`、`utils/`等非当前维护目录共98个既有问题，本步没有越界改写这些文件，也不把该命令伪报为通过。

### 33.4 18文档、34条Golden与清理实测

正式Parser/R04命令实际摄取18份文档，结果不是全绿：

| 指标 | 实际结果 |
|---|---:|
| 上传成功 | 18/18 |
| 解析完成 | 17/18 |
| 全部Golden恢复 | 32/34 |
| 8份官方PDF Golden | 14/14 |
| OCR Golden | 2/4 |
| 已完成文档R04 | 17/17 `accepted` |
| 路由 | Native 16、Hybrid 1、Docling 0；扫描件失败 |

唯一失败是`m2-complex-v1-scanned-receiving-ticket`。Docling/RapidOCR Worker已经返回结果，但没有在既有2秒收尾窗口退出，第一次正式运行记录`shutdown_timeout`，总耗时约93.48秒、峰值约1.98GB；随后单件Router/OCR Smoke再次记录同类失败，总耗时约99.29秒、峰值约1.96GB。连续两次相同失败说明不能当作一次偶发噪声；失败位于既有`LocalDoclingProvider`进程生命周期层，不在本次Native PDF Locator、Artifact适配或R04阈值层。本步没有放宽超时、改R04或跳过扫描件。

正式Runner仍完成精准清理：评估数据库行0、评估Storage对象0；正式基线恢复为10个File、10个Document、10个Version、9条ACL、10个Pending Version、10个上传对象，M1守护库存仍为125。临时JSON报告已在读取结果后按确定路径删除；两个失败Worker PID均不存在；未留下本步评估数据。

### 33.5 能证明、不能证明与停止点

能证明：Native PDF不再只有整页字符串；双栏左右标题和正文各自有独立坐标与真实字符范围；42个可信标题/组合片段可回到真实物理行；新坐标参与Hash且重复构建稳定；旧Artifact可读；12份正式PDF的Parser/Adapter结构没有回归；17份完成文档仍通过R04，8份官方PDF仍为14/14；评估清理恢复正式数据库与Storage基线。

不能证明：当前完整18份文档仍能达到18/18、34/34和OCR 4/4；Docling Worker退出问题已经解决；生产Chunker已经消费行级Locator；标题已经按元数据注入正文Chunk；R-02的3个RED已经修复；原7组Chunk矩阵已经用新Artifact重跑；M2-22.6或任何下游能力已经验证。

当前状态为“R-01B实现完成、验收受阻”。排查优先级已经定位为Docling子进程发送Snapshot后的退出/线程句柄收束，而不是Parser Artifact文字、Chunk规则或Locator。按单步协作边界停止，等待用户理解并决定是否单独授权处理或复验该阻塞；不得自动进入R-02或M2-22.6。

## 34. M2-22.5R-01B补充实施记录：Docling一次性Worker确定性退出（2026-09-08）

### 34.1 授权、缺口、输入输出与边界

用户在理解“路由正确，失败发生在OCR结果返回后的Worker收尾”后明确表示开始下一步。本小步只修复第33节暴露的Docling进程生命周期阻塞，不修改Parser选路、R04阈值、Canonical文字内容、Chunk规则或标题Golden。

大白话说，旧流程像是工人已经把OCR结果交到窗口，但身后的工具线程还没有收好，父进程因此按安全规则拒收。输入仍是已经受大小限制、确实被Router判定需要增强解析的扫描PDF字节；输出仍是原来的严格`DoclingParseSnapshot`。本步只保证一次性Worker在同步发送完整结果并关闭单向Pipe后立即结束，让父进程继续执行“结果到达、Worker已退出、退出码正常、Snapshot复验”四道条件；没有把2秒收尾窗口调大，也没有允许仍存活的Worker蒙混通过。

调用链位置为：

```text
公开上传/文档登记
→ Parser Service
→ Router（既有健康度与复杂度规则，本步未改）
→ LocalDoclingProvider父进程边界
→ spawn一次性Worker
→ 本地CPU Docling + RapidOCR
→ 严格Snapshot同步写入Pipe并关闭
→ Worker确定性退出（本步）
→ 父进程确认退出码并复验Snapshot
→ Docling Adapter → Canonical Artifact → R04
→ 停止
```

专项和正式R04复验均未运行Chunker、Embedding、pgvector、检索、Reranker、Context、Agent/LangGraph、Harness、Tool、Qwen、Ragas或前端。相邻回归只运行既有Parser/Chunk的确定性测试与数据库Service合同，没有启动上述下游功能；R-02标题注入仍保持RED。

### 34.2 最小实现与防放宽规则

1. `app/services/documents/parsers/docling.py`：新增只允许一次性子进程调用的`_exit_docling_worker`。Worker成功或固定失败消息已经由`Connection.send_bytes`同步写完后，先关闭连接，再用进程级退出绕过Docling/ONNXRuntime可能残留的非守护线程；最终消息未发送成功时保留非零退出码。父进程的总时限、RSS/Snapshot上限、2秒收尾窗口、活进程拒收、退出码和Snapshot复验全部不变；
2. `tests/fixtures/docling_process_worker.py`：把`lingering.pdf`改成更接近真实故障的“后台非守护线程滞留”，并增加复用正式退出助手的`hard-exit-lingering.pdf`；
3. `tests/unit/test_docling_process_isolation.py`：新增“结果完整发送后即使存在滞留线程也能成功、PID消失”的回归；旧滞留Worker仍必须得到`shutdown_timeout`，证明不是放宽父进程门禁；
4. 本记录、M2入口与项目总看板：同步实际验证、基线、边界和下一停止点。

### 34.3 TDD、真实扫描件与正式18文档结果

1. RED：测试先引入尚不存在的退出助手，首次收集得到预期ImportError；实现后Docling进程隔离专项为`6 passed in 19.88s`，其中故意滞留、不调用正式退出助手的Worker仍被拒绝；
2. 单件正式Router/RapidOCR Smoke为`1 passed in 109.47s`。扫描PDF保持`unusable → docling`并恢复2/2事实；日志为`status=success`、Worker PID 39876、`spawn_ms=5798`、`ready_ms=5820`、`total_ms=101853`、`peak_rss_bytes=1959198720`，随后确认PID不存在；
3. 第一次18文档复跑已经达到18/18解析、34/34 Golden和OCR 4/4，但Runner如实标为`failed`：运行前数据库中的正式M2 Seed为0条，而Storage已有10个上传对象，因此不是干净基线。该次评估租户行与对象仍清理为0；随后只用既有两个M2 Seed入口恢复正式基线，并在运行前确认`10 files / 10 documents / 10 versions / 9 ACL / 10 pending / 10 uploads / M1 125 / clean=True`；
4. 干净基线上的第二次正式Parser/R04运行最终为`run_status=completed`：18/18上传、18/18解析、34/34 Golden、外部14/14、OCR 4/4，Parser事实恢复率和OCR字段准确率均为1.0；路由Native 16、Docling 1、Hybrid 1，18/18 R04决定均为`accepted`。p50/p95/max解析耗时为237/65,040/65,040 ms；
5. 正式Runner清理结果为评估数据库行0、评估Storage对象0；正式基线恢复10个File、10个Document、10个Version、9条ACL、10个Pending Version、10个上传对象，M1守护库存125，`baseline_restored=true`；
6. 随后的21项相邻数据库测试会重置正式M2表，测试后审计实际发现数据库正式记录为0、Storage仍为10。最终再次只运行既有两个M2 Seed入口并复核为`10/10/10/9/10/10/M1 125/clean=True`；临时Parser报告已按确定路径删除，没有留下本步评估数据或Docling Worker。

### 34.4 专项、相邻、完整允许回归与工程门禁

- Docling进程隔离专项在最终格式化后复跑为`6 passed in 14.40s`；禁止下游边界内的完整允许单元范围为`370 passed, 2 skipped, 3 failed in 75.23s`。新增生命周期用例进入通过数；3个失败与R-01时完全相同，分别是编号标题未进入`heading_path`、父子路径缺少编号子标题、标题空壳被指标误收，继续作为R-02的正式RED；
- Parser/Chunk Service、Parser/Chunk Runner和两组合成Seed相邻数据库集成为`21 passed in 59.79s`；
- `ruff check app tests scripts migrations`通过；本步3个代码/测试文件格式检查通过；`mypy app`为156个源码文件通过；`compileall -q app`和`git diff --check`通过。diff检查仅提示若干既有工作区文件未来会按Git配置把LF转换为CRLF，没有空白错误。

### 34.5 能证明、不能证明、风险与停止点

能证明：本次失败不是Router把扫描件送错路径；正式Docling Worker能在完整Snapshot发回后确定性退出；父进程没有通过增加等待时间或接受活进程来制造成功；故意不执行退出协议的滞留Worker仍被拒绝并清理；同一代码状态下已重新得到18/18 Parser、34/34 Golden、OCR 4/4和18/18 R04接受；评估数据已经清零且正式数据库/Storage/M1基线恢复。

不能证明：任意第三方库子进程都应该使用这种退出方式；多个Docling任务并发时已有全局队列或背压；直接DOCX OCR已经获得同样的进程隔离；生产Chunker已经消费新PDF行级Locator；标题元数据已经注入正文Chunk；3个R-02 RED已经修复；7组Chunk矩阵已在新标题规则下重跑；M2-22.6或任何检索/生成能力已经验证。

后续若再次出现`shutdown_timeout`，先看最终消息是否发送、Pipe是否关闭、Worker退出码和是否走了正式`_docling_worker_entry`；若在结果发送前卡住，仍按既有总时限/RSS门禁处理，不能把进程级退出当成推理超时修复。若出现`worker_crash`，先区分消息发送失败与本地模型/ONNX异常。`os._exit`只位于一次性Worker末端，不能搬到主服务或可复用进程。

本小步完成后停止。R-01B的正式验收阻塞已经解除，但M2-22.5标题质量门禁仍未通过；下一动作只能是在用户理解并单独授权后开始既有R-02确定性标题元数据绑定。不得自动进入R-02、M2-22.6或任何后续步骤。

## 35. M2-22.5R-02实施记录：确定性标题绑定与语义层级阻塞（2026-09-08）

### 35.1 本步目标、输入输出和调用链

用户明确授权开始下一步。本步只实施第28.4节R-02，不修改R-03质量评估器，不重跑R-04正式7组矩阵，也不进入M2-22.6。

大白话说，旧Chunker会把标题当普通正文一起塞进切割窗口，而且只认“整行和提示一模一样”；新流程先看Parser已经保存的真实物理行、字符范围和坐标，确认标题后把它从正文里拿出来，放进后续正文Chunk的`heading_path`。正文仍保留自己的真实source span，`retrieval_text`再按现有Token预算把标题上下文和正文拼成检索视图。

```text
R04通过的Canonical Parser Artifact
→ PDF物理行/字符范围/坐标
→ 本步确定性标题候选过滤、合并、层级栈和双栏绑定
→ body_text + heading_path
→ 现有Token窗口与overlap
→ retrieval_text + Canonical Chunk Artifact
→ 停止
```

没有经过前端、Agent/LangGraph、Harness、Tool、Embedding、pgvector、检索、Reranker、Context、Qwen或Ragas。相邻集成只验证Parser/Chunk Service与版本化Artifact落库；没有创建索引或运行下游功能。

### 35.2 实现与防伪边界

1. `app/services/documents/chunking/chunker.py`：PDF先把`pdf_layout_lines`的真实source range映射为独立切片；标题必须引用同页真实物理行，或在旧Artifact中满足独立整行/编号前缀的唯一边界。纯标题不进入正文窗口，同行标题后的正文从标题真实结束位置开始；
2. 同页并列栏标题根据bbox位于页面左/右半栏建立互斥标题栈，正文只继承本栏标题，不能按页级字符串顺序猜；连续同栏、同字号、水平对齐且行距处于真实换行范围的标题确定性合并；
3. 项目符号、纯货币数值、引用编号以及与数据值同排的字段标签不提升；较短全大写栏目眉紧邻更完整的多行主标题时，不绑定正文，由完整主标题替代；`Part/Annex/Chapter/Section + 编号`以通用结构标记开启新根章节，不写死Golden标题全文；
4. `app/services/documents/chunking/contracts.py`：行为身份升级为`m2-structure-aware-chunker-v2`，同时保留旧v1合同可读；Chunk Artifact Schema和数据库没有迁移；
5. `app/schemas/evaluation.py`：新评估配置的默认Chunker身份同步为v2，同时保留历史v1报告可读取；没有修改指标计算或门禁阈值；
6. `tests/unit/test_document_text_chunker.py`：冻结标题抽离、编号/同行正文范围、父子栈、正文短语不误报、双栏同栏归属和重复构建确定性；
7. `tests/unit/test_document_chunk_contracts.py`、`tests/unit/test_rag_evaluation_contracts.py`：冻结v2默认身份及v1兼容；
8. `tests/unit/test_m2_chunk_heading_golden.py`：新增真实4份问题PDF→Native Parser→Artifact→Chunker直接验收，逐条比较26个可信正文路径并确认43个非标题没有进入元数据。该测试保留聚合RED，不把真实失败拆掉或改宽松。

### 35.3 TDD与实际结果

编码前标题相关定向RED为`5 failed, 3 passed, 6 deselected`：旧实现仍把精确标题留在正文，编号/同行与父子绑定失败，双栏正文取不到本栏标题。主体实现后相同Chunk测试为`8 passed, 6 deselected`，最终完整文本Chunk文件为`14 passed`；格式化后的文本Chunk、Chunk合同和评估合同定向集合为`102 passed`。

R-01冻结的3个缺口现在是`2 passed, 1 failed`：编号标题和父子标题的生产绑定已通过；唯一失败仍是`test_heading_quality_rejects_metadata_attached_only_to_a_title_shell`，它属于尚未实施的R-03评估器防伪，本步按边界没有修改`app/evals/chunk_metrics.py`。

新增真实直接验收第一次显示只有4/26路径正确且已知非标题被提升；加入确定性多行合并、根章节、数据/字段过滤后，最终达到：

| 项目 | 实际结果 |
|---|---:|
| 可信标题正文路径 | 21/26 |
| 已知非标题未进入`heading_path` | 43/43 |
| 双栏4组同栏关系 | 4/4 |
| 剩余失败 | 5/26 |

剩余5条为：OSS的`Deregistration`、`Exclusion`、`Date on which...`、`Quarantine period`人工Golden要求放在`Specific details`之下；但PDF原生Outline把它们与`Specific details`列为同一二级，Artifact的字体级别也相同。GPSR的`Consumer detriment`人工Golden要求放在`Better enforcement`之下，但该PDF没有Outline，两者字体级别相同，当前Artifact没有共同容器或显式父节点。仅凭页面先后顺序不能唯一证明父子关系。

因此完整允许单元回归如实为`366 passed, 2 skipped, 2 failed in 93.96s`。两个失败分别是上述5条真实路径的聚合RED，以及R-03标题空壳防伪RED；没有新的Parser、Locator、Chunk Token、表格、DOCX或确定性失败。相邻Parser/Chunk Service与两个Seed集成为`19 passed in 29.76s`。

工程门禁为：`ruff check app tests scripts migrations`通过；`mypy app`为156个源码文件通过；`compileall -q app`、`pip check`和`git diff --check`通过，diff只提示既有LF未来可能转换CRLF，没有空白错误。

### 35.4 数据清理与正式基线

本步没有运行正式评估Runner、没有摄取18份评估文档，也没有创建评估租户或评估Storage对象。数据库相邻测试结束后，按既有流程重新运行`seed_m2_files`和`seed_m2_complex_files`，最终只读审计为10个File、10个Document、10个Version、9条ACL、10个pending版本、10个upload对象、0个正式ChunkSet、M1德国仓可售库存125，`clean=True`。

没有删除或覆盖正式文件；没有生成需要额外清理的临时报告。本步没有重跑原18文档、34内容Golden或7组矩阵，因为R-02真实层级RED尚未通过，提前运行R-04既浪费一次Docling成本，也不能得到可声明通过的标题门禁。

### 35.5 能证明、不能证明与停止点

能证明：标题和正文现在是两个职责；纯标题不会占正文窗口；编号/同行正文保留真实范围；双栏使用物理坐标而非字符串顺序；连续多行标题可合并；43条已知噪声没有污染元数据；Chunker行为有新版本身份且旧v1可读；21条真实标题路径已经绑定到正确正文；Token/表格/DOCX/确定性相邻范围没有新回归；正式数据库和Storage基线干净。

不能证明：26/26语义层级已经正确；R-03标题空壳防伪已经修复；至少一个7组候选通过完整门禁；原18份文档/34条内容Golden在Chunker v2下已经正式复跑；生产默认参数应该改变；M2-22.6或任何下游能力已经验证。

当前R-02状态是“主体实现、真实语义层级验收受阻”，不能标记完成。下一步必须先让用户理解并单独确认5条层级真值的处理原则：若以PDF原生Outline为权威，需要有证据地修订与其冲突的OSS Golden；若坚持人工语义父子关系，就必须为无大纲/同字号版面设计新的可审计结构来源，不能把`Specific details`、`Better enforcement`等Golden词语硬编码进生产Chunker，也不能按页面出现顺序猜。未经确认不得进入R-03、R-04、M2-22.6或任何后续功能。

上述阻塞随后由用户逐页视觉裁决解除：两组标题确为同级，问题在人工Golden而不在Parser或Chunker；最终收口见第36节。

## 36. M2-22.5R-02用户视觉裁决、人工Golden纠正与收口（2026-09-08）

### 36.1 裁决与问题归因

用户查看原PDF对应页面后明确确认：

1. OSS中`Specific details`与`Deregistration`、`Exclusion`、`Date on which deregistration/exclusion becomes effective`、`Quarantine period`是同级标题，不是父子关系；
2. GPSR中`Better enforcement`与`Consumer detriment`也是同级标题；
3. Parser提取的字体层级没有问题。

这5条父子关系来自助手在R-01A人工制作Golden时的错误判断。Parser Artifact、OSS的PDF原生Outline和当前Chunker对这两处的同级输出是一致的，因此本次不能修改Parser或生产Chunk规则去迎合错误答案，也不能放宽R04阈值。

### 36.2 实际修改

1. `data/evals/m2_cross_border_chunk_headings_v2.json`：由v1升级为`m2-chunk-heading-golden-v2`。OSS 4条叶标题的`semantic_level`由3纠正为2，路径移除错误父级`Specific details`；GPSR的`Consumer detriment`由3纠正为2，路径移除错误父级`Better enforcement`。标题原文、页码、正文锚点、绑定方向、26条正文关系总数与43条非标题反例均不变；新文件SHA-256为`c4c4b78313118bc9a9e646cd1e3479f7ba71e9a76eb15e982fee1060d12aa4a6`；
2. `app/schemas/evaluation.py`：正式标题Golden合同接受当前v2身份，同时保留历史v1身份可读；未修改指标阈值；
3. `tests/unit/test_m2_chunk_heading_golden.py`：切换到v2数据并冻结新版本与Hash；
4. `tests/unit/test_m2_pdf_layout_locator.py`：Locator真实文档测试切换到v2数据；
5. `docs/PROJECT_PROGRESS.md`、`docs/progress/M2/M2_KNOWLEDGE_RAG.md`与本文：同步R-02完成状态、证据、边界和下一动作。

本次没有为5条标题修改`chunker.py`，因为生产结果本来就是正确的同级关系。完整调用链只到：

```text
原PDF视觉事实
→ 已有Parser Artifact / PDF行级Locator
→ 已有Chunker v2标题元数据绑定
→ v2人工Golden直接比对
→ 停止
```

没有经过Embedding、pgvector、检索、Reranker、Context、Agent/LangGraph、Harness、Tool、Qwen、Ragas或前端，也没有运行R-04的18文档7组正式矩阵。

### 36.3 实际验证结果

1. R-02专项：`tests/unit/test_m2_chunk_heading_golden.py`、`test_m2_pdf_layout_locator.py`和`test_document_text_chunker.py`为`22 passed in 64.29s`，包含26/26真实标题正文关系、43/43已知非标题拒绝、双栏Locator和文本Chunk合同；
2. 相邻Chunk/Evaluation合同：5个相关文件为`110 passed in 66.84s`；
3. 相邻数据库集成：Parser Service、Chunk Service和两个Seed集成为`19 passed in 32.17s`；
4. 禁止下游边界内完整允许单元回归为`367 passed, 2 skipped, 1 failed in 91.70s`。唯一失败是`test_heading_quality_rejects_metadata_attached_only_to_a_title_shell`，属于尚未实施R-03的评估防伪；R-02真实路径聚合RED已经通过；
5. 数据库集成后重新运行两个正式M2 Seed入口；最终只读审计为10个File、10个Document、10个Version、9条ACL、10个pending版本、10个upload对象、0个ChunkSet、M1德国仓可售库存125，Parser和Chunk基线均`clean=True`；
6. 格式化后再次复跑两个真实Golden/Locator测试文件为`8 passed in 76.63s`；`ruff check app tests scripts migrations`、8个R-02相关Python文件的格式检查、`mypy app`（156个源码文件）、`compileall -q app`、`pip check`和`git diff --check`均通过；
7. 用户复核用的5张临时PNG已经从`tmp/pdfs/m2-heading-dispute`删除，原始PDF未修改。

### 36.4 能证明、不能证明与停止点

能证明：这5条争议的正确关系是同级；此前失败由人工Golden误判造成，不是Parser路由、Parser字体层级、Locator或Chunker错误；纠正后R-02达到26/26真实标题正文路径并保持43/43非标题拒绝；相关合同与相邻数据库流程没有回归；正式数据库和Storage已恢复干净基线。

不能证明：R-03标题空壳评估漏洞已经修复；原18份文档、34条内容Golden和7组Chunk配置已在当前v2状态下正式重跑；至少一组配置已通过完整Chunk质量门禁；生产默认Chunk参数应该改变；M2-22.6或任何下游RAG能力已验证。

R-02至此完成并停止。下一动作只能是在用户理解并单独授权后实施R-03评估器防伪；R-03通过后才可由R-04运行正式18文档、34条内容Golden和7组矩阵。不得自动进入R-03、R-04、M2-22.6或任何后续功能。

## 37. M2-22.5R-03实施记录：标题质量门禁防伪与报告语义（2026-09-08）

### 37.1 本步目标、输入输出与调用链

用户在理解R-02已完成后明确授权开始下一步。本步只实施第28.4节R-03：修复“Chunk只带标题字符串或标题元数据也可能被计为标题保留”的评估漏洞，并纠正报告总门禁必须让所有实验配置同时通过的错误语义。不修改Parser、R04质量阈值、生产Chunk规则或默认Chunk参数，不运行R-04正式矩阵，也不进入M2-22.6。

输入是R04通过的Canonical Parser Artifact、Chunker v2产物、`m2-chunk-heading-golden-v2`的26条可信标题正文关系和现有34条内容Golden；输出是每文档/配置的严格标题保留计数、独立质量门禁及带标题数据身份的v2报告合同。调用链为：

```text
已有Parser Artifact
→ 已有Chunker v2：body_text + heading_path + source_spans
→ 本步严格标题质量评估
→ 每组配置独立门禁
→ 冻结候选总门禁语义
→ 报告v2
→ 停止
```

没有经过Embedding、pgvector、检索、Reranker、Context、Agent/LangGraph、Harness、Tool、Qwen、Ragas或前端。数据库集成只验证Parser/Chunk Service、Runner报告和精准清理。

### 37.2 实现与防伪规则

1. `app/evals/chunk_metrics.py`：`evaluate_chunk_document`接收版本化可信标题正文案例；对有人工Golden的文档，每条标题只有在同一个文本Chunk同时满足以下条件才计为保留：完整规范化`heading_path`精确相等、`body_text`包含Golden非标题正文、`retrieval_text`包含完整标题上下文、Parser Artifact声明页存在对应标题提示或Canonical结构标题、Chunk页码与source span确实覆盖正文原文、正文source slice不是标题本身且真实出现在`body_text`；
2. 原始`heading_hints`继续是Parser候选诊断，不再直接进入正式标题成功分母。没有人工标题Golden的文档只检查Canonical `block.heading_path`，并同样要求绑定真实、可定位的非标题正文；
3. `app/evals/rag_runner.py`：Runner固定加载标题Golden v2并传给每份文档/每组配置；报告升级为`m2-chunk-quality-report-v2`，新增标题数据版本、原始文件SHA-256和本次命中的可信案例数；
4. 每组首轮与重叠配置继续独立保留`quality_gate_passed`。报告总门禁不再要求所有比较实验同时通过，而是要求按冻结质量排序选出的候选中，至少一个重叠配置满足全部质量条件；失败配置和Bad Case不会被删除；
5. `tests/unit/test_rag_chunk_metrics.py`：新增正常绑定，以及标题空壳、只有文本没有元数据、伪造父子路径、错误正文source span、Parser标题来源缺失反例；
6. `tests/unit/test_m2_chunk_heading_golden.py`：既有4份真实问题PDF、26条关系除直接比较Chunker输出外，再逐条进入R-03严格评估函数；
7. `tests/unit/test_m2_rag_parser_runner.py`与`tests/integration/test_m2_rag_chunk_runner.py`：冻结“至少一个选定候选通过”的报告语义、v2数据身份，并在5文档真实Service Runner中让双栏文档的4条标题关系逐组通过。

本步没有改`app/services/documents/chunking/chunker.py`，因为R-02生产输出已经正确；也没有修改标题Golden、34条内容Golden或R04阈值。

### 37.3 TDD、专项、相邻和完整回归

1. 编码前先加入6个R-03用例，旧评估器得到`6 failed, 4 passed in 9.78s`，失败原因是旧函数不接受可信标题案例，也没有正文/Locator联合核验；
2. 实现后`tests/unit/test_rag_chunk_metrics.py`为`10 passed in 7.22s`；定向评估、报告、Golden与合同集合为`101 passed in 29.82s`；
3. 4份真实问题PDF测试为`6 passed in 26.67s`，其中26/26可信标题正文关系逐条通过R-03严格函数；
4. 禁止下游边界内完整允许单元回归为`371 passed, 2 skipped in 121.83s`，此前标题空壳失败已经转绿，没有新增Parser、Chunk、表格、OCR、Locator或确定性失败；
5. 真实Runner专项最终为`1 passed in 53.49s`：5份文档实际经过上传、Parser/R04、Chunk Service、4组首轮配置和候选重叠扫描；双栏标题Golden共4条，在每组配置均为4/4；
6. 相邻Parser Service、Chunk Service、两个Seed和Runner集成为`20 passed in 79.94s`；
7. 工程门禁全部通过：`ruff check app tests scripts migrations`、6个R-03相关文件格式检查、`mypy app`（156个源码文件）、`compileall -q app`、`pip check`和`git diff --check`。diff只有仓库现有LF/CRLF提示，没有空白错误。

### 37.4 数据清理与正式基线

Runner使用隔离评估身份和Storage范围，测试结束后评估数据库行、ChunkSet和Storage对象归零。全部数据库回归完成后再次运行`seed_m2_files`与`seed_m2_complex_files`，最终只读审计为10个File、10个Document、10个Version、9条ACL、10个pending版本、10个upload对象、0个正式ChunkSet、M1德国仓可售库存125，Parser和Chunk基线均`clean=True`。

本步没有生成或保留正式18文档报告；没有运行Ragas、Embedding或任何禁止下游。

### 37.5 能证明、不能证明与停止点

能证明：标题字符串、`heading_path`或Parser提示任意单项都不能制造通过；受审标题必须绑定同一Chunk中的真实非标题正文和正确Locator；伪造父子层级、缺失Parser来源及错误正文source span都会被拒绝；4份真实问题PDF的26条关系通过严格指标；Runner实际消费标题Golden v2并可审计其Hash；失败实验配置与候选总门禁语义已经分离；相关代码、相邻Service和正式基线没有回归。

不能证明：当前18份文档在7组正式配置下全部通过；34条内容Golden与Locator仍为34/34；正式标题总数和每组结果是什么；至少一个冻结候选已经通过完整门禁；最佳生产Chunk参数应该改变；M2-22.6或任何检索、重排、Context、回答与Agent能力已经验证。

R-03至此完成并停止。下一动作只能是在用户理解并单独授权后实施R-04：使用当前Parser/R04、Chunker v2、标题Golden v2和报告v2正式重跑18文档、34条内容Golden及7组矩阵，随后精准清理并如实报告。不得自动进入R-04、M2-22.6或任何后续功能。

## 38. M2-22.5R-04正式矩阵运行、质量受阻与清理（2026-09-09）

### 38.1 本步授权、输入输出与边界

用户明确授权进入M2-22.5R-04。本步没有新增生产能力，输入是已经通过R04的18份正式评估文档、34条内容Golden、Chunker v2、`m2-chunk-heading-golden-v2`的26条人工标题正文关系和`m2-chunk-quality-report-v2`评估器；输出是当前代码状态下的正式Chunk矩阵结果、失败归因、回归证据和清理后的正式基线。

实际调用链为：

```text
受控原文件
→ 公开上传/建文档API
→ DocumentParserService / Router / Native或Docling
→ Canonical Parser Artifact
→ R04质量门禁
→ DocumentChunkService / Chunker v2
→ Canonical Chunk Artifact（body_text + heading_path + retrieval_text + source_spans）
→ 项目确定性Chunk质量矩阵
→ 精准清理与正式基线复核
→ 停止
```

没有运行Embedding、pgvector、检索、Reranker、Context、Agent/LangGraph、Harness Tool、Qwen、Ragas或前端；没有修改生产默认Chunk参数、Parser、R04阈值、34条内容Golden或标题Golden，也没有进入M2-22.6。

### 38.2 正式运行与配置矩阵

运行前只读基线为10个File、10个Document、10个Version、9条ACL、10个pending版本、10个upload对象、0个ChunkSet、M1德国仓可售库存125，`clean=True`。Docker最初未启动导致数据库连接超时；启动仓库既有`deep-search-postgres`容器后重新检查，基线干净，再执行：

```powershell
.venv\Scripts\python.exe -m app.evals.rag_runner --stage chunk --enable-docling --output data\evals\runtime\reports\m2_cross_border_chunk_report_v2.json
```

Run ID为`m2-22.5-20260909t005309-682e5c2b`，UTC运行时间为`2026-09-09T00:53:09.678527Z`至`2026-09-09T01:06:14.664902Z`。运行状态为`completed`，18/18文档完成Parser并通过R04，34条内容Golden全部进入评估。`completed`只说明执行和清理成功，不等于质量门禁通过。

4组首轮实际结果：

| 配置 | 内容Golden | 标题 | 边界断裂 | 表格 | Chunk数 | Token min/p50/p95/max | 重叠冗余 |
|---|---:|---:|---:|---:|---:|---:|---:|
| `400/500/100` | 34/34 | 55/56 | 91/9750 | 45/45 | 779 | 6/388/399/482 | 24.54% |
| `500/600/100` | 34/34 | 55/56 | 90/9750 | 45/45 | 588 | 6/486/499/598 | 19.24% |
| `600/700/100` | 33/34 | 55/56 | 90/9750 | 45/45 | 482 | 6/586/598/667 | 15.90% |
| `700/850/100` | 34/34 | 55/56 | 90/9750 | 45/45 | 406 | 6/685/698/793 | 13.30% |

冻结候选选择策略在结构质量并列时同时保留`chunk-large`与`chunk-medium`，因此本次不是旧记录中的“4+3=7组”，而是4组首轮加2个候选各3个overlap，共10组完整配置；这是R-03已经冻结并由测试验证的候选语义，不是运行中临时改规则。6组overlap扫描中，除`chunk-large-overlap-080`为33/34外，其余5组均为34/34内容和Locator；所有6组均为55/56标题、90/9750边界、45/45表格、18/18顺序/Locator完整性/确定性和0空Chunk，因此全部总门禁False。

代表性`chunk-large-overlap-120`结果为：417个Chunk，Token min/p50/p95/max=`6/685/699/803`，重叠冗余率15.99%，1个近重复Chunk；34/34内容Golden和Locator、证据source span覆盖100%、45/45表格、18/18来源顺序、18/18 Locator完整性、18/18字节确定性、0空Chunk全部通过。DOCX页眉3/3、页脚3/3、图片OCR 1/1、图片前后文关系1/1也全部通过。近重复计数不是当前门禁失败项；实际门禁失败条件是标题未全保留和边界断裂不为0。

### 38.3 失败事实与定位

人工冻结的26条标题正文关系全部通过：双栏4/4、OSS 16/16、GPSR 5/5、Safety Gate 1/1。总体标题55/56中的唯一失败来自没有人工标题Golden的`m2-complex-v1-scanned-receiving-ticket`，其Canonical fallback为4/5。它不是此前用户裁决的同级标题争议，也不能据此改Golden。

总体段落为9598/9687，即89个单位被记为“不在正文”；边界再包含1个未通过的结构标题单位，共90/9750。11份失败PDF分别为：蘑菇灯手册6、扫描入库单1、双栏简报10、合并表头成本表1、VAT解释说明11、OSS指南27、低价值包裹19、退运5、GPSR 6、Safety Gate新闻稿2、Safety Gate通报2。

代码核对得到一个确定的评估合同冲突：

1. Chunker v2识别纯标题后会更新`heading_path`，并按已确认设计跳过纯标题，不让它进入`body_text`；
2. `_audit_structure`仍把Canonical PDF Block中的每一个非空行放入边界分母，并且只在Chunk的`body_text`里查找；
3. `ExcludedChunkSpan`目前只支持空白、重复页眉、重复页脚和噪声，没有“已提升为标题元数据”原因，也没有精确字符起止范围；纯标题以及多行合并标题被跳过时，Chunk Artifact没有保存这段来源审计；
4. 无人工Golden的Canonical fallback还按`source_block_ids`查正文绑定；纯标题独立成块并被抽离后，后续正文Chunk不会自然携带该标题Block ID，因此扫描入库单的1个标题无法由现有合同证明。

因此，当前结果**不能解释为89段正文真的被切坏**。它证明的是：标题抽离策略已经执行，但Chunk Artifact与边界评估没有同步表达“哪一段源文字被合法抽到元数据、绑定给了哪个正文Chunk”。失败位于Chunk Artifact/评估审计合同交界，不是Parser原文恢复、正文Locator、表格、overlap、顺序或确定性；也没有证据要求修改R04阈值。

建议的最小后续修复是M2-22.5R-04A：让Chunker对每个实际提升的标题输出可审计的精确源范围（至少Block、字符起止、页/坐标、标题层级以及所绑定正文Chunk），并纳入Chunk Hash/版本；边界评估只能排除这些真实、可定位、已绑定的标题范围，不能按字符串或所有`heading_hints`宽松忽略；同时用该绑定复核扫描入库单的1个Canonical fallback。该修复必须先写RED反例，再重跑同一正式矩阵。当前未获该代码修改授权，所以本步没有实施。

### 38.4 专项、相邻、完整回归与清理

1. R-04正式Runner：`run_status=completed documents=18 golden=34 quality_gate_passed=False`；这是本步必须保留的真实质量失败；
2. 专项评估/标题/报告合同：`101 passed in 22.85s`；
3. 相邻Parser Service、Chunk Service、两个Seed与5文档Runner集成：`20 passed in 63.69s`；
4. 禁止下游边界内完整Parser/Artifact/Router/Chunk/Evaluation单元回归：`367 passed, 2 skipped in 89.24s`；
5. 首次用文件路径直跑`seed_m2_files.py`因模块搜索路径报`ModuleNotFoundError: app`，在导入阶段退出、没有数据库写入；改用正式模块入口后，`python -m scripts.seed_m2_files`与`python -m scripts.seed_m2_complex_files`均成功；
6. 最终独立只读审计再次得到10 files / 10 documents / 10 versions / 9 ACL / 10 pending / 10 uploads / 0 ChunkSet / M1库存125 / `clean=True`；Runner报告内也记录评估数据库行0、评估ChunkSet 0、评估Storage对象0与`baseline_restored=True`；
7. 临时报告大小713,628字节，SHA-256为`ecf16a31fe77ad1dfc39413b7a9bc3bd8ea2a37644be50dd879c1da1fc425fbd`。必要汇总进入本记录后按用户要求删除；原始18份输入文件和正式10份Seed对象未删除或覆盖。

本步只修改三份进度文档：本文保存完整命令、结果、归因与停止点；`docs/progress/M2/M2_KNOWLEDGE_RAG.md`保存M2当前状态、风险和验证基线；`docs/PROJECT_PROGRESS.md`保存项目级状态与下一动作。没有生产代码、测试、Schema、迁移、Golden或配置变更。

### 38.5 能证明、不能证明与停止点

能证明：当前Parser/R04可处理18/18文档；至少多个候选达到34/34内容Golden与真实Locator；人工标题关系26/26；表格、DOCX视觉文字及前后文、Token硬上限、顺序、Locator完整性和重复构建确定性没有回归；评估器没有因为内容成功而掩盖标题/边界失败；失败已定位到标题元数据来源审计和边界分母合同；专项、相邻和完整允许回归通过；评估数据库与Storage已清理，正式基线恢复。

不能证明：当前Chunk总质量门禁通过；90个边界失败已经逐条由新版来源记录证明为合法标题排除；扫描入库单第5个Canonical标题已绑定；`700/850/120`应成为生产默认值；近重复Chunk在更大语料上没有影响；Embedding、pgvector、检索、Reranker、Context、回答、Agent、Qwen、Ragas、前端或M2-22.6已经验证。

R-04运行与清理已经完成，但质量验收受阻，M2-22.5R不能标记完成。当前停止并等待用户理解及单独授权R-04A最小修复；不得自动修改Chunk Artifact/Chunker/评估器，不得更新生产默认参数，不得进入M2-22.6或任何后续步骤。

## 39. M2-22.5R-04A实施记录：标题来源审计、版面边界校准与正式收口（2026-09-09）

### 39.1 用户授权、缺口、输入输出与边界

用户在确认“标题已经按要求从`body_text`抽到元数据，而旧评价仍要求标题出现在正文”后，明确授权先修改并进入R-04A。本步只修复M2-22.5的Chunk Artifact、Chunker与质量评价合同，不修改34条内容Golden、标题Golden、R04解析质量阈值或生产默认Chunk参数，也不实现M2-22.6。

本步输入是18份已经通过R04的Canonical Parser Artifact、其中PDF的真实Block/字符范围/页码/`pdf_layout_lines`/bbox、DOCX结构来源、34条内容Golden和标题Golden v2；输出是`m2-structure-aware-chunker-v3` Chunk Artifact、标题精确来源审计、与真实版面一致的边界统计，以及重跑后的正式质量矩阵。

实际调用链为：

```text
受控原文件
→ 公开上传/建文档API
→ DocumentParserService / Router / Native或Docling
→ Canonical Parser Artifact
→ R04解析质量门禁
→ DocumentChunkService / Chunker v3
→ Canonical Chunk Artifact
   ├─ body_text：只放正文
   ├─ heading_path：用于检索的标题路径
   ├─ heading_sources：标题的Block/字符起止/页码/bbox来源
   └─ excluded_spans：标题、重复页眉页脚或噪声的精确审计
→ 项目确定性Chunk质量矩阵
→ 精准清理与正式基线复核
→ 停止
```

没有运行Ragas、Embedding、pgvector、检索、Reranker、Context、Agent/LangGraph、Qwen或前端；相邻回归没有启动这些下游能力。本步没有新增迁移或数据库字段。

### 39.2 实现、严格评价规则与防伪边界

1. Chunker版本升为`m2-structure-aware-chunker-v3`。每个真实提升到`heading_path`的标题可带`ChunkHeadingSource`，记录路径下标、规范化标题、真实源文字，以及Block、字符起止、页码、bbox；来源进入Chunk内容Hash。空列表在序列化时省略，历史v1/v2 Artifact继续可读；
2. 标题原文不回填`body_text`。Chunker另外写入`reason=heading_metadata`的精确`ExcludedChunkSpan`；重复页眉/页脚、噪声和被主标题吸收的masthead也保存真实字符范围。表格Chunk重编号保留标题来源；
3. 标题质量和正文边界继续分开：56个结构标题要通过标题门禁，仍必须有真实Parser声明、正确路径、真实非标题正文、检索视图、Locator和精确来源；仅写一个标题字符串或伪造路径仍不能通过；
4. 正文边界不再要求标题重复出现在`body_text`。只有`heading_metadata`的Block、字符范围、Locator、源切片与Parser标题声明全部一致时，该范围才从正文分母排除。封面连续标题或图示标签即使没有可绑定正文，也必须以精确Chunk Artifact元数据证明后才可排除，不能仅凭字符串或所有`heading_hints`宽松忽略；
5. PDF正文审计不再把文本层横向拼接的整行当作唯一段落单位。若Parser提供行级Locator，评价按与Chunker一致的“有真实offset的物理layout line + 行内未覆盖残段”逐项检查；没有layout信息的旧Artifact仍回退到原行审计。这样双栏左右正文和复杂表格单元可以进入不同Chunk，但每个真实来源片段仍必须被找到；
6. 修复一个真实Chunk审计遗漏：全大写masthead被后续多行主标题吸收时，旧判断把它留在`consumed`集合却因仍遍历自身匹配而没有写`noise`。现在只用未消费的保留标题判断覆盖，真实masthead会得到精确噪声记录；组合标题的第二行不会被重复排除；
7. 编号标题审计使用与Chunker相同的确定性编号前缀剥离规则，例如Parser提示`2. IOSS适用范围`仍可证明规范化标题`IOSS适用范围`，没有把业务词或Golden硬编码进规则。

这不是把门禁调松。标题路径质量仍要求标题与正文绑定；正文边界只是不再要求标题同时存在于正文。双栏/表格改用Parser已有的真实物理行和坐标，未删除任何正文检查，也没有修改`boundary_breaks == 0`的正式门禁。

### 39.3 TDD、首轮正式失败与逐条归因

编码前的4个RED分别在“Chunk没有`heading_sources`”“正确抽离标题仍被算作正文缺失”“删除标题来源绑定后标题质量仍通过”等预期位置失败。加入v3合同和首轮评价实现后，定向4项转绿；标题来源还增加了路径下标唯一、正文Chunk限定、精确字符范围、源切片、Locator、排除记录和Hash篡改反例。

首轮R-04A正式运行Run ID为`m2-22.5-20260909t021722-f63212c3`，执行和清理成功，但质量门禁仍为False。它已经把标题从55/56修到56/56，并把边界误报从90降到41；34条内容Golden的候选表现保持不变，正式基线也恢复。因为41不等于0，本步没有在此冒充通过。

随后对41条逐一打印原Block、页码、字符范围、Parser提示、layout line、标题来源、Chunk正文和排除记录，得到三类确定事实：

- 22条来自双栏或复杂表格。PDF文本层把不同横坐标内容拼成一行，而Chunker按真实bbox拆到多个Chunk，所有物理文字行实际都存在；
- 18条是封面连续标题或图示标签，均已有Parser声明和精确`heading_metadata`范围，但没有独立正文可绑定；它们不应进入`body_text`分母；
- 1条`CONSUMER PROTECTION`是masthead的真实审计漏记，既没有正文也没有排除元数据，定位并修复于Chunk规则。

修正后只重跑上述6份Native PDF做离线逐条复核，六份均为`MISSING 0`；临时诊断脚本随后删除，没有成为交付物或留下评估数据。

### 39.4 最终18文档、34 Golden与13组正式矩阵

最终在干净正式基线上执行：

```powershell
.venv\Scripts\python.exe -m app.evals.rag_runner --stage chunk --enable-docling --output data\evals\runtime\reports\m2_cross_border_chunk_report_v2.json
```

Run ID为`m2-22.5-20260909t032311-651ab937`，UTC运行时间为`2026-09-09T03:23:11.474046Z`至`2026-09-09T03:45:39.461101Z`。18/18文档完成真实上传、Parser与R04，路由为Native 16、Docling 1、Hybrid 1；34条内容Golden全部进入评估，最终`run_status=completed`且`quality_gate_passed=True`。

四组首轮结果为：

| 配置 | 内容Golden/Locator | 标题 | 边界断裂 | 表格 | Chunk数 | Token min/p50/p95/max | 重叠冗余 |
|---|---:|---:|---:|---:|---:|---:|---:|
| `400/500/100` | 34/34 | 56/56 | 0/11809 | 45/45 | 779 | 6/388/399/482 | 24.54% |
| `500/600/100` | 34/34 | 56/56 | 0/11809 | 45/45 | 588 | 6/486/499/598 | 19.24% |
| `600/700/100` | 33/34 | 56/56 | 0/11809 | 45/45 | 482 | 6/586/598/667 | 15.90% |
| `700/850/100` | 34/34 | 56/56 | 0/11809 | 45/45 | 406 | 6/685/698/793 | 13.30% |

物理layout line与残段成为正确审计单位后，边界分母由旧文本层拼接行口径的9750变为11809；不能把它描述成简单删除90项。新分母逐项覆盖了拆开的双栏和表格来源，结果为0个断裂。

首轮结构质量并列，冻结选择策略得到`chunk-compact/chunk-large/chunk-medium`三个候选，因此最终是4组首轮加3个候选各3组overlap，共13组，不是运行中临时增加。9组overlap结果为：

| 配置 | 内容Golden/Locator | Chunk数 | 重叠冗余 |
|---|---:|---:|---:|
| compact / 80 | 34/34 | 733 | 19.58% |
| compact / 100 | 34/34 | 779 | 24.54% |
| compact / 120 | 34/34 | 832 | 29.51% |
| large / 80 | 33/34 | 397 | 10.66% |
| large / 100 | 34/34 | 406 | 13.30% |
| large / 120 | 34/34 | 417 | 15.99% |
| medium / 80 | 34/34 | 563 | 15.35% |
| medium / 100 | 34/34 | 588 | 19.24% |
| medium / 120 | 34/34 | 617 | 23.19% |

9组均为56/56标题、0/11809边界断裂、45/45表格、18/18顺序、18/18 Locator完整性、18/18重复构建确定性和0空Chunk。代表性`large/120`另为证据source span覆盖100%、DOCX页眉3/3、页脚3/3、图片OCR 1/1、图片前后文1/1、Token `6/685/699/803`，有1个近重复Chunk。数字只用于矩阵比较；本步没有选择或修改生产默认参数。

### 39.5 专项、相邻、完整回归、工程门禁与清理

1. R-04A关键定向4项为`4 passed`；最终Chunk合同、文本Chunk、指标、报告合同和真实标题Golden专项为`123 passed in 24.29s`；
2. Parser Service、Chunk Service、5文档Runner与两个Seed相邻PostgreSQL集成为`20 passed in 70.96s`；
3. 禁止下游边界内的完整Parser/Artifact/Router/Chunk/Evaluation/Storage单元范围收集387项，结果为`385 passed, 2 skipped in 83.64s`，没有失败；
4. `ruff check app tests scripts migrations`通过；11个本步代码/测试文件格式正确；`mypy app`为156个源码文件通过；`compileall -q app`、`pip check`和`git diff --check`通过。diff只有现有Git换行提示，没有空白错误；
5. 正式报告内记录评估数据库行0、评估ChunkSet 0、评估Storage对象0、`baseline_restored=True`。相邻数据库测试会重置M2表，因此测试后再次运行两个既有Seed入口；最终独立只读审计为10 files / 10 documents / 10 versions / 9 ACL / 10 pending / 10 uploads / 0 ChunkSet / M1库存125 / `clean=True`；
6. 临时正式报告为940,807字节，SHA-256 `857040c692640d286b364589f0963b0eaea7e1b21affaac2ef24cfd28259dd1a`。必要结果进入本记录后按用户要求删除；18份原始评估文档与正式10份Seed对象未删除或覆盖。

### 39.6 能证明、不能证明、风险与停止点

能证明：当前18份固定文档能通过R04并进入真实Chunk Service；Chunker v3在正文不重复标题的前提下可审计标题原文、路径、Block、精确字符范围、页码和bbox；标题56/56、34条内容与Locator在多个候选中34/34、边界0/11809、表格45/45、DOCX视觉来源与前后文、顺序、Locator和确定性均通过；伪造标题字符串、错误路径、错误源切片或缺失排除记录仍不能制造标题质量通过；正式评估数据已清理并恢复基线。

不能证明：`600/700/100`当前生产默认值是最佳选择；近重复Chunk在更大语料没有影响；任意未来PDF的复杂版面、标题或OCR都一定正确；Embedding、pgvector、检索、Reranker、Context、回答、权限、Citation、Agent、Qwen、Ragas、前端或M2-22.6已经验证。本步尤其不能用Chunk Golden包含率替代后续真实检索指标。

M2-22.5及其R-04A至此完成。当前停止并等待用户理解及单独授权M2-22.6；不得自动安装或运行Ragas，也不得自动进入Embedding、pgvector、检索、Reranker、Context、Agent、Qwen、前端或任何后续步骤。

## 40. M2-22.6实施记录：检索评估器完成、真实矩阵受DOCX公开Locator阻塞（2026-09-09）

### 40.1 授权、缺口与本步边界

用户正式授权只实施M2-22.6。M2-22.5已经证明18份文档经过Parser/R04后，冻结候选中的正确原文能够进入Chunk并保留来源；它没有证明查询向量、PostgreSQL FTS或RRF能把正确Chunk排进TopK，也没有验证相似产品、无答案题、ACL/软删除/active版本或排名稳定性。

本步输入固定为既有18份文档、40条Debug Smoke、其中34条可回答Golden Evidence、M2-22.5筛出的9组`compact/medium/large × overlap 80/100/120`和当前生产`600/700/100`基线；候选深度固定10/20/30，先在RRF=60下筛候选深度，再只对所选深度比较RRF 20/60/100，不做无界笛卡尔积。目标输出是Dense、Lexical、Hybrid完整有序候选及其排名/分数/Locator，确定性指标、Ragas检索语义指标、分组延迟/过滤/稳定性和Bad Case报告。

允许调用链为：

```text
18份冻结文档
→ 上传/登记API
→ Parser / R04
→ Chunker v3（只用评估配置覆盖）
→ Index Service
→ 本地BGE-M3 DOCUMENT/QUERY Embedding
→ PostgreSQL FTS + pgvector（排序前共用tenant/ACL/软删除/active代次过滤）
→ Dense / Lexical
→ RRF Hybrid
→ 项目确定性排名指标 + Ragas检索语义指标
→ 分层安全报告
→ 精确清理、正式Seed与M1基线复核
```

没有实现或运行BGE-Reranker、Context/Evidence、Knowledge Tool、Harness、Agent/LangGraph、Supervisor/Worker、项目Qwen回答、Citation、自动路由或前端；没有修改生产SQL、数据库结构、Golden、生产Chunk参数或生产TopK/RRF默认值，也没有进入M2-22.7。

### 40.2 已实现的M2-22.6能力

1. `app/evals/retrieval_metrics.py`实现项目确定性指标：Precision/Recall/Hit Rate `@1/@3/@5/@8/@10/@20`、MRR@10、nDCG@5/@10、首个正确Evidence排名、Evidence单位去重Recall、相似产品串答和无答案误召回；
2. `app/evals/retrieval_report.py`冻结安全报告合同。每条路由保存完整有序候选的Chunk/Document/Version/Index Set ID、排名、Dense/Lexical/RRF分数、逻辑来源、Locator、正文Hash和匹配Evidence ID，不保存正文、向量、tenant、密钥或Judge思维链；确定性结果与Ragas结果分栏；
3. `app/evals/ragas_retrieval.py`固定`ragas==0.4.3`，按该版本真实API适配`ContextPrecisionWithReference`、`ContextRecall`、`ContextRelevance`和`NoiseSensitivity`。只有前三项能在纯检索输入中运行；`NoiseSensitivity`在该版本要求`response`，M2-22.6禁止生成回答，所以必须记录`skipped/input_invalid`而不是伪造0分。异常、网络、超时和Judge失败均无数值；
4. Judge身份固定记录Provider、模型、API别名版本、温度、top-p、最大输出、seed、30秒超时、2次尝试、Prompt实现包Hash和状态，不保存思维链。最小真实探针得到Context Precision约1.0、Context Recall 1.0、Context Relevance 1.0；Noise Sensitivity按上述合同显式跳过。该探针只调用Ragas Judge，没有启动项目最终回答链；
5. `app/evals/retrieval_runner.py`实现18文档真实摄取、冻结Chunk矩阵、BGE精确文本内存缓存、预编码以区分Embedding失败与Index持久化失败、Dense/Lexical真实Service、RRF融合、四类报告分组、顺序筛选、完整Trace、过滤审计、稳定复跑和失败时精确清理；
6. `scripts/run_m2_retrieval_evaluation.py`提供正式模块入口。BGE固定本地revision与离线模型；批量大小16和数据库语句超时30秒只作用于评估Settings副本，并同时记录生产默认批量4、SQL超时2秒和已观测超时，未修改生产默认值；`--config-id/--case-id/--no-ragas`只用于有界诊断；
7. 新增确定性指标、Ragas适配、Runner合同和真实PostgreSQL/pgvector集成测试。集成测试使用Fake Embedding隔离模型质量，但真实执行FTS、vector距离、RRF、ACL/软删除、active代次、稳定复跑及清理；正式Runner另使用真实BGE。

依赖管理沿用`requirements-dev.txt`的开发评估边界，固定新增`ragas==0.4.3`及其当前导入所需的`langchain-community==0.4.1`；没有安装DeepEval。安装前核对了现有venv、依赖文件、模型缓存和磁盘，包安装后`pip show`与`pip check`确认确切版本且无破损依赖。Ragas 0.4.3实际指标模块组成的Prompt实现包SHA-256为`fc347923599df1a73f285372856a462e4ebbdf5a3e7bffdc40fc5a7332323845`。

### 40.3 RED/GREEN与评估器验证

初始RED分别证明项目不存在检索排名指标、Ragas检索适配和M2-22.6 Runner；加入最小实现后，确定性指标和Ragas适配单元逐步达到11项通过，Runner合同达到3项通过。真实集成首先证明PostgreSQL FTS、pgvector、RRF和清理闭环；随后加入无答案软删除样本与Dense安全错误诊断。

正式失败暴露后又增加一条RED：评估器必须保留首个无法映射的Chunk ID和原始校验原因，不能只记录生产安全错误`检索暂时无法完成`。RED在缺少诊断类型/函数处导入失败；GREEN后Runner单元4项通过。稳定性复跑分支第一次漏传新增的`case_id`，同组专项表现为`12 passed, 1 failed`；只补传参数后复跑为`13 passed in 25.44s`。

当前静态工程门禁结果：9个M2-22.6代码/测试文件Ruff format通过；Ruff lint通过；4个评估源码Mypy通过；`compileall`通过；`pip check`无破损依赖；`git diff --check`通过。完整相邻和截至Retrieval层的允许回归尚未运行，因为正式矩阵在第一组第一题已命中必须另行授权的生产数据合同缺口；不得把专项通过冒充本步完整验收。

### 40.4 真实运行、逐层诊断与确定阻塞

真实运行过程中已分开验证以下故障：

1. 首次从标准输入启动模块触发Windows多进程`<stdin>`入口失败，属于Runner启动方式；改用`python -m scripts.run_m2_retrieval_evaluation`后解除；
2. BGE批量32在本机长文档运行不稳定；只把评估吞吐批量降为16，生产默认仍为4；
3. 第一版Evidence映射把无答案题当成可回答题，定位为评估器Golden/Evidence映射并修正；没有改Golden；
4. `eu-vat-explanatory-notes-2026-en`在`compact/80`下产生292个Chunk。BGE已成功返回向量，但Index持久化在生产默认2秒SQL超时下失败；同一数据、同一Chunk与Fake向量在评估30秒超时下成功，索引阶段约43.2秒。因此这是Index/PostgreSQL持久化边界，不是BGE失败，也不构成修改生产超时或选择compact为生产默认的证据；
5. 纠正以上评估器问题后，完整正式运行真实解析18/18文档、预编码40/40查询，并在第一组`chunk-compact-overlap-080`完成18份文档的Chunk、BGE和Index。首题`smoke-syn-001-voltage`执行Dense@10时，pgvector已经返回有序候选，但第4名Chunk `179ca26a-1e5b-5ed5-a1c5-08e6efd02c30`无法构造公开`DocxRetrievalSourceLocator`：页码、段落号、表格号和标题路径全部为空；生产Dense Service因此在结果映射层转换为安全`RetrievalInternalError`；
6. 单题、同候选、全18文档的干净复现得到相同故障形状和具体Chunk，排除旧数据残留。结合当前代码可定位最早缺口：`m2-complex-v1-visual-quality-notice`是本批唯一包含R-03 DOCX页眉/页脚来源的文档；`_adapt_docx_region`把Section/region信息存入`docx_source`，但其通用`SourceLocator`为空；Chunker v3按设计原样保存该Parser来源，M2-22.5的Locator完整性只验证“Chunk与Parser一致”，没有验证“所有Chunk都能形成公开Retrieval Locator”；Dense结果映射又没有读取`docx_source`或`source_block_ids`。因此首个错误层归为**Parser Artifact的DOCX region公开坐标缺口，暴露于Dense结果映射**，不是pgvector Dense召回质量、FTS、ACL、RRF、Ragas或Judge。

这个错误不能通过删除第4名、只评Top3、扩大TopK或从候选中排除页眉/页脚掩盖。继续正式矩阵需要修改生产来源映射或上游Parser/Chunk坐标，超出本次仅允许评估器改动的边界，故按用户要求立即停止。没有生成任何候选质量分数，也没有运行Ragas正式40题评分；所有10组Chunk、三档深度和三档RRF指标均为**未完成/不可报告**，不是0分。

### 40.5 建议的最小修复方案（未实施，等待单独授权）

推荐单独授权`M2-22.6R-01 DOCX region Retrieval Locator修复`，只解决这一阻塞，不进入M2-22.7：

1. 先为DOCX页眉/页脚Chunk分别写Dense与Lexical RED，证明当前公开结果映射失败；再加伪造/非法Block ID反例；
2. 不改数据库结构、排序SQL、过滤条件、TopK/RRF、Golden或Chunk边界。让Dense/Lexical候选记录带上数据库中已经存在的`source_block_ids`，当DOCX `start_locator`没有任何公开坐标时，只允许把第一个格式合法且属于该Chunk的Canonical `bNNNNNN`转换为公开`block_number`；原有段落号、表格号、页码和标题路径优先级不变；
3. 预计只修改`app/repositories/retrieval.py`与`app/services/retrieval/result_mapping.py`，并补Dense/Lexical/Hybrid和权限前置集成测试。因为共享Mapper也被Context读取，修复验证必须确保只改变Locator坐标，不运行或构造Context；
4. 修复后先复跑单题真实BGE阻塞样本；通过后再从干净基线完整重跑本M2-22.6矩阵、Ragas检索指标、专项/相邻/完整允许回归和最终清理。评分仍不得自动改生产默认值。

若用户不接受Canonical Block作为公开DOCX坐标，则备选方案是给Parser Artifact的DOCX region Locator增加稳定Section/region坐标并升级Artifact/适配版本，但这会扩大到Parser重验，成本和影响明显更大，不是推荐的最小修复。

### 40.6 清理、能证明与停止点

失败Runner的`finally`已清除隔离租户、用户、文档、版本、ACL、ChunkSet、IndexSet、Chunk行、向量、Storage上传与Parser/Chunk对象，并清空进程内Embedding缓存。随后重新运行既有`seed_m2_files`与`seed_m2_complex_files`；独立只读审计为10 files、10 documents、10 versions、9 ACL、10 pending版本、10 upload对象、0 ChunkSet、0 IndexSet、0 Chunk、M1德国仓可售库存125、`clean=True`，残留M2-22.6评估租户为0。三个早期诊断报告目录和`dependency-audit`临时目录已按核对后的绝对路径删除；18份受控原文、既有正式Parser/Chunk报告和模型缓存保留。

能证明：M2-22.6评估器合同、确定性算法、Ragas 0.4.3适配、真实FTS/pgvector/RRF集成与清理路径已经实现；Ragas前三个纯检索指标能用固定Judge运行，Noise Sensitivity在禁止回答的边界内必须显式跳过；真实BGE与Index已到达第一组全18文档；生产2秒索引边界和DOCX region公开Locator缺口均已分层定位。

不能证明：任何候选配置、候选深度或RRF常数的完整质量优劣；40题Ragas语义表现；四类分组的Precision/Recall/Hit/MRR/nDCG/延迟；全部ACL/版本过滤和排名稳定性在18文档正式集上通过；生产默认值应当修改；M2-22.6已完成；以及Reranker、Context、Evidence、回答、Citation、Agent或M2-22.7任何能力。

第40节当时的M2-22.6状态为`受阻`而非`已完成`；该Locator修复随后已获用户确认并按第41节完成。历史失败证据保留，但当前停止点以第41节为准。

## 41. M2-22.6R-01与确定性检索矩阵（2026-09-09）

### 41.1 用户决定、RED与最小修复

用户确认采用第40.5节首选方案，并补充要求：缺精确坐标时降级展示；若Canonical Block也损坏，单个候选不能拖垮整个请求，但必须显式记录映射失败并让质量门禁失败，不能静默删除后把后续候选名次前移。该授权只解除M2-22.6的Locator阻塞，不授权Reranker、Context/Evidence、回答、Citation、Agent或M2-22.7。

先写RED并得到预期失败：Repository候选没有`source_block_ids`；公开响应不能表达单候选映射失败和原始排名空洞；Dense/Lexical仍会因一个无Locator候选全局报错。GREEN实现遵守以下顺序：

1. 既有页码、页集合、段落号、表格号、标题路径和原有Block坐标继续优先；
2. 只有DOCX候选的上述公开坐标全部为空时，才检查第一个`source_block_ids`；它必须精确匹配`b[0-9]{6}`、数值大于0，并与首个source span的`block_id`相同，随后才转换为公开`block_number`；
3. 若该校验失败，只捕获专门的Locator映射异常，记录`source_mode + 原始rank + chunk_id + source_locator_mapping + invalid_source_locator`。其他类型/校验错误仍走全局安全错误，避免把任意程序缺陷吞成“降级”；
4. Dense/Lexical结果允许由`results + candidate_failures`共同组成连续原始排名。例如第2名失败时公开结果排名为`1,3`，不会把第3名改成第2名；RRF继续使用route score内的原始排名，因此不会因坏候选获得虚假加分；
5. 每个实验的`candidate_mapping_quality_gate_passed`要求所有路由零映射失败；总`integrity_quality_gate_passed`还要求ACL、软删除、inactive Index Set、tenant和稳定性审计全部通过。Trace同时保存安全失败记录，指标计算为失败名次插入不相关占位，不会静默改善Precision、Recall、MRR或nDCG。

没有按“页眉/页脚”过滤候选。当前公开Retrieval Locator的`source_type`是`docx`而不是`header/footer`，region事实位于Parser的`docx_source`；更重要的是冻结题`smoke-syn-015-visual-control`确实询问页眉控制码`QC-VISUAL-17`，过滤会直接删除正确Evidence并改变真实排序问题。

修改文件与职责：

- `app/repositories/retrieval.py`：只把已有Chunk `source_block_ids`带入Dense/Lexical候选记录；排序SQL和过滤SQL未改；
- `app/services/retrieval/result_mapping.py`：实现精确坐标优先、Canonical Block兜底以及专用Locator映射异常；
- `app/services/retrieval/dense.py`、`lexical.py`：逐候选映射，只隔离专用Locator失败并保留原始排名；
- `app/services/retrieval/hybrid.py`：接受有明确失败记录的route排名空洞，按原始Dense/Lexical rank计算RRF并向报告传递失败；
- `app/schemas/retrieval.py`：新增公开安全的候选失败合同，并验证结果与失败必须覆盖完整原始route排名；
- `app/evals/retrieval_report.py`、`retrieval_runner.py`：Trace、指标占位、实验/总质量门禁和Bad Case接通映射失败；Hybrid只有在至少一个上游route已经把正确Evidence送入Top8、融合后却丢失时才归因RRF，两路都漏召回时不再重复误报为RRF；
- `tests/unit/test_dense_retrieval.py`、`test_lexical_retrieval.py`、`test_retrieval_contracts.py`、`test_rrf.py`、`test_m2_retrieval_runner.py`及相邻集成夹具：覆盖真实Block降级、坏Block隔离、排名不前移、RRF原始rank和质量门禁。

### 41.2 真实阻塞样本与正式运行

最小真实复现Run `m2-22.6-20260909t093211-34c9503d`使用全18文档、`chunk-compact-overlap-080`和单题`smoke-syn-001-voltage`，真实经过上传/登记、Parser/R04、Chunker v3、Index Service、本地BGE-M3、PostgreSQL FTS/pgvector、Dense/Lexical与RRF。733个Chunk和5个有界实验点全部完成；原先导致全局报错的Dense第4名仍是同一Chunk、相似度`0.5581355`、最终rank 4，公开Locator降级为`Docx block_number=1`，没有页码，也没有被过滤或重排。全部Trace映射失败0、完整性门禁True，清理与基线恢复True。临时摘要133,226字节，SHA-256 `a63964c9e775ce38b8b826015f1e966a03ddeaaa5c280030ed6eefef011caaed`。

正式Run `m2-22.6-20260909t095558-22ee87ce`从干净基线完成18份文档、40条查询、10组冻结Chunk配置、10/20/30三档候选深度以及每组所选深度上的RRF 20/60/100；实际只运行30个深度点加20个额外RRF点，不是10×3×3无界笛卡尔积。总计180个Index Set、50份JSONL Trace、2,000个case-experiment、6,000条Dense/Lexical/Hybrid有序列表、106,518个候选，候选映射失败0。运行约2小时59分；摘要7,693,041字节、SHA-256 `446d0a12d4c5f21d1c573ac91c58c0e88a6085f74b01b95fc72c3885d292a112`，50份Trace共81,199,038字节，每份Hash另由摘要记录。Trace保存全部候选的Chunk/Document/Version/Index Set ID、原始排名、Dense/Lexical/RRF分数、逻辑来源、公开Locator、正文Hash和匹配Evidence ID，不只保存最终TopK，也不保存正文、向量、tenant、密钥或Judge思维链。

固定身份：来源`m2-cross-border-sources-v1` / `f0b6c492603a91a9b9eb220ec96a060150b1396a79274f0e5357cacd6680b6c7`；数据集`m2-cross-border-rag-smoke-v1` / `1d22afa22c5752463189827dba86502f8bc1d06ab7d70403cb0af463c5c4c46b`；Embedding `BAAI/bge-m3@5617a9f61b028005a4858fdac845db406aefb181`、评估批量16。查询Embedding 40次的p50/p95/max为`335/406/23149 ms`。生产SQL超时仍为2,000 ms，评估副本为30,000 ms；已观测`compact/80`长VAT文档在生产边界超时，未修改生产设置。

### 41.3 候选深度筛选真实结果

下表使用不能被合成题稀释的`real_cross_border` 14条可回答题、Hybrid route；每格依次为深度10/20/30，RRF固定60。参数为`target/max/overlap`。`miss`是该深度完整候选列表内完全没有正确Evidence的题数，不是`1-Hit@8`。

| Chunk配置 | 参数 | Chunk数 | Index ms | Hit/Recall@8 | MRR@10 | nDCG@10 | miss |
|---|---:|---:|---:|---|---|---|---|
| compact/080 | 400/500/80 | 733 | 1,138,944 | .7857/.7857/.7143 | .3935/.3897/.3775 | .4879/.4986/.4727 | 3/1/1 |
| compact/100 | 400/500/100 | 779 | 1,011,817 | .8571/.7143/.7143 | .4817/.4628/.4513 | .5692/.5528/.5276 | 2/2/2 |
| compact/120 | 400/500/120 | 832 | 1,105,898 | .7143/.5714/.5714 | .4477/.4347/.4340 | .5097/.4977/.4824 | 4/1/1 |
| medium/080 | 500/600/80 | 563 | 942,184 | .7143/.6429/.5714 | .4101/.3852/.3673 | .4831/.4465/.4157 | 3/3/2 |
| medium/100 | 500/600/100 | 588 | 921,936 | .7143/.6429/.5714 | .3757/.3690/.3579 | .4571/.4508/.4263 | 3/2/1 |
| medium/120 | 500/600/120 | 617 | 983,571 | .5714/.5714/.5000 | .3774/.3257/.3234 | .4249/.3854/.3830 | 5/2/1 |
| large/080 | 700/850/80 | 397 | 961,757 | .7143/.7143/.6429 | .4294/.4223/.4333 | .5138/.5070/.5162 | 3/2/1 |
| large/100 | 700/850/100 | 406 | 929,847 | .6429/.6429/.5714 | .4060/.3966/.4008 | .4791/.4705/.4594 | 4/2/0 |
| large/120 | 700/850/120 | 417 | 1,063,132 | .5714/.5714/.5714 | .3571/.3452/.3494 | .4116/.4160/.4190 | 3/2/0 |
| current | 600/700/100 | 482 | 1,053,554 | .6429/.5000/.5714 | .4018/.3889/.3899 | .4595/.4331/.4341 | 5/3/3 |

每组都按冻结选择器选深度10。原因不是“更大TopK一定更差”，而是Hybrid输出由两条更深候选列表重新融合，额外候选会改变前8排序；本步不得扩大TopK掩盖上游失败。`compact/100 depth 10`在真实组Hit/Recall@8、MRR@10和nDCG@10均为本轮最高，因此成为后续RRF筛选与全局候选。生产基线的真实配置是`current depth 30/RRF 60`：真实组Hybrid Hit@8 `.5714`、MRR@10 `.3899`、nDCG@10 `.4341`；它保留作为对照，没有被修改。

### 41.4 RRF常数与所选候选的完整指标

每个Chunk配置只在其已选深度10比较RRF 20/60/100。十组配置的三种RRF常数均产生完全相同的Hybrid候选顺序和所有确定性排名指标；只有RRF数值本身和亚毫秒级融合计时不同。因此没有质量证据证明20或100优于当前60，最终候选保持RRF 60。各配置的`real_cross_border`三常数共同结果如下：

| Chunk配置 | RRF 20/60/100 Hit/Recall@8 | MRR@10 | nDCG@10 |
|---|---:|---:|---:|
| compact/080 | .7857/.7857/.7857 | .3935/.3935/.3935 | .4879/.4879/.4879 |
| compact/100 | .8571/.8571/.8571 | .4817/.4817/.4817 | .5692/.5692/.5692 |
| compact/120 | .7143/.7143/.7143 | .4477/.4477/.4477 | .5097/.5097/.5097 |
| medium/080 | .7143/.7143/.7143 | .4101/.4101/.4101 | .4831/.4831/.4831 |
| medium/100 | .7143/.7143/.7143 | .3757/.3757/.3757 | .4571/.4571/.4571 |
| medium/120 | .5714/.5714/.5714 | .3774/.3774/.3774 | .4249/.4249/.4249 |
| large/080 | .7143/.7143/.7143 | .4294/.4294/.4294 | .5138/.5138/.5138 |
| large/100 | .6429/.6429/.6429 | .4060/.4060/.4060 | .4791/.4791/.4791 |
| large/120 | .5714/.5714/.5714 | .3571/.3571/.3571 | .4116/.4116/.4116 |
| current | .6429/.6429/.6429 | .4018/.4018/.4018 | .4595/.4595/.4595 |

最终只形成候选建议`compact/100 + depth 10 + RRF 60`，没有修改生产默认。下表为该候选全部冻结cutoff；顺序均为`@1/@3/@5/@8/@10/@20`，安全组没有可回答题，其0值只表示确定性排名指标不适用，安全结果看最后一列的误召回。

| 分组 | route | Precision | Recall = Hit Rate | MRR@10 | nDCG@5/@10 | 首个正确均值 | miss | SKU串答 | 无答案误召回 | 候选min/p50/p95/max | 延迟p50/p95/max ms |
|---|---|---|---|---:|---|---:|---:|---:|---:|---|---|
| 全部可回答 | Dense | .5588/.2745/.1882/.1213/.0971/.0485 | .5588/.7941/.9118/.9118/.9118/.9118 | .7010 | .7541/.7541 | 1.6774 | 3 | .1111 | 0 | 10/10/10/10 | 99/108/111 |
| 全部可回答 | Lexical | .3824/.1961/.1294/.0882/.0706/.0353 | .3824/.5882/.6176/.6765/.6765/.6765 | .4821 | .5095/.5298 | 2.0870 | 11 | .2222 | 0 | 4/10/10/10 | 61/364/517 |
| 全部可回答 | Hybrid | .5294/.2647/.1647/.1213/.0971/.0485 | .5294/.7647/.7647/.9118/.9118/.9118 | .6584 | .6702/.7193 | 2.2903 | 3 | .1111 | 0 | 11/17/20/20 | 0/1/1 |
| 真实跨境 | Dense | .5000/.2619/.1857/.1250/.1000/.0500 | .5000/.7143/.8571/.8571/.8571/.8571 | .6429 | .6967/.6967 | 1.7500 | 2 | .5000 | 0 | 10/10/10/10 | 101/108/108 |
| 真实跨境 | Lexical | .0000/.0952/.0714/.0536/.0429/.0214 | .0000/.2857/.2857/.3571/.3571/.3571 | .1310 | .1616/.1870 | 3.2000 | 9 | 1.0000 | 0 | 8/10/10/10 | 114/517/517 |
| 真实跨境 | Hybrid | .3571/.2143/.1429/.1250/.1000/.0500 | .3571/.5714/.5714/.8571/.8571/.8571 | .4817 | .4736/.5692 | 3.4167 | 2 | .5000 | 0 | 13/18/20/20 | 0/1/1 |
| 合成跨境 | Dense | .6000/.3333/.2000/.1250/.1000/.0500 | .6000/1/1/1/1/1 | .7833 | .8393/.8393 | 1.5000 | 0 | 0 | 0 | 10/10/10/10 | 98/107/107 |
| 合成跨境 | Lexical | .6000/.2667/.1800/.1250/.1000/.0500 | .6000/.8000/.9000/1/1/1 | .7226 | .7562/.7895 | 2.2000 | 0 | 0 | 0 | 4/10/10/10 | 61/372/372 |
| 合成跨境 | Hybrid | .7000/.3333/.2000/.1250/.1000/.0500 | .7000/1/1/1/1/1 | .8500 | .8893/.8893 | 1.3000 | 0 | 0 | 0 | 11/17/19/19 | 0/1/1 |
| 通用诊断 | Dense | .6000/.2333/.1800/.1125/.0900/.0450 | .6000/.7000/.9000/.9000/.9000/.9000 | .7000 | .7492/.7492 | 1.7778 | 1 | 0 | 0 | 10/10/10/10 | 95/110/110 |
| 通用诊断 | Lexical | .7000/.2667/.1600/.1000/.0800/.0400 | .7000/.8000/.8000/.8000/.8000/.8000 | .7333 | .7500/.7500 | 1.2500 | 2 | 0 | 0 | 9/10/10/10 | 56/87/87 |
| 通用诊断 | Hybrid | .6000/.2667/.1600/.1125/.0900/.0450 | .6000/.8000/.8000/.9000/.9000/.9000 | .7143 | .7262/.7595 | 1.8889 | 1 | 0 | 0 | 11/15/18/18 | 0/1/1 |
| 安全/ACL/版本 | Dense | 0/0/0/0/0/0 | 0/0/0/0/0/0 | 0 | 0/0 | - | 0 | - | 0 | 10/10/10/10 | 95/111/111 |
| 安全/ACL/版本 | Lexical | 0/0/0/0/0/0 | 0/0/0/0/0/0 | 0 | 0/0 | - | 0 | - | 0 | 6/10/10/10 | 61/172/172 |
| 安全/ACL/版本 | Hybrid | 0/0/0/0/0/0 | 0/0/0/0/0/0 | 0 | 0/0 | - | 0 | - | 0 | 12/14/17/17 | 0/0/0 |

全部34条可回答题之外另有6条无答案题，其中4条ACL/版本/拒绝来源可做确定性泄漏判断，误召回为0；另外2条属于语义未知/无证据，不伪装成确定性0分。过滤审计为ACL 4条、软删除2条route、inactive Index Set 2条route、tenant 80条route，泄漏全部0；所选配置重复120条route，排名变化0。排序前过滤仍由既有Repository SQL完成，本步没有在结果出来后再删禁用候选。

### 41.5 Bad Case与首错层

最终候选在真实跨境、合成跨境和通用诊断中分别保持独立结果。10个唯一问题存在Top8失败；不是笼统的“模型不好”：

- `smoke-syn-011-scan-batch`：Dense和Lexical完整depth 10均无正确Evidence，首错分别位于pgvector Dense召回和PostgreSQL FTS；Hybrid缺失来自两条上游输入，不归咎RRF；
- `smoke-syn-012-scan-sample`：Dense命中，Lexical在depth 10漏召回，首错为PostgreSQL FTS；
- `smoke-ext-024-record-retention`、`025-ioss-coverage`、`027-fixed-duty`、`028-handling-fee-vat`、`030-h7-conditions`、`032-en-ioss-optional`、`034-de-return-window`：Dense/Hybrid可命中，Lexical漏召回，首错为PostgreSQL FTS；
- `smoke-ext-029-return-invalidation`与`031-zh-responsible-person`：Dense和Lexical均漏召回，Hybrid没有可融合的正确输入，首错分别记录在pgvector Dense召回与PostgreSQL FTS，而不是RRF；
- 其余成功题中相似SKU/产品串答为：Dense 1/9、Lexical 2/9、Hybrid 1/9；真实跨境子组分别为1/2、2/2、1/2，说明真实相似产品仍是明确风险；
- Parser Artifact、Chunk范围和Golden/Evidence映射已由上游34/34内容+Locator及本轮Index映射证明通过；本轮没有Locator映射、ACL/active版本或真实RRF融合首错。生产2秒索引超时单独归为Index/PostgreSQL持久化边界。

### 41.6 Ragas正式状态与外部授权阻塞

固定`ragas==0.4.3`、`langchain-community==0.4.1`，Judge身份为`qwen-openai-compatible / qwen3.8-max / api-alias-20260909`，temperature 0、top-p 1、max output 2048、seed 20260909、单次30秒、最多2次，Prompt实现包SHA-256 `fc347923599df1a73f285372856a462e4ebbdf5a3e7bffdc40fc5a7332323845`。只对所选候选的34条可回答Hybrid结果运行，没有启动项目Qwen最终回答链。

正式结果分栏且全部保持非数值：Context Precision 34个`judge_failed/judge_provider_error`；Context Recall 34个同类失败；Context Relevancy 34个`framework_failed/framework_error`，原因是Ragas在底层连接失败后返回无效结果；Noise Sensitivity 34个`skipped/input_invalid`，因为0.4.3要求`response`而本步禁止构造回答。随后只补跑所选候选的外部网络申请被安全审查拒绝：评估问题、Golden摘要和候选原文会发送到外部Qwen API，而现有授权未被视为对这次数据发送的明确同意。没有绕过限制，也没有把失败写成0分或通过。

因此M2-22.6本地确定性部分完成，正式Ragas语义评分仍为`受阻`。只有用户在知情后明确允许上述数据发送，才可只补跑`compact/100 + depth 10 + RRF 60`；不得重新扩成全矩阵，更不得进入M2-22.7。

### 41.7 测试、工程门禁、清理与结论

实际验证结果：

- Locator/指标/报告/真实pgvector专项：`177 passed`；
- Index/Embedding/Retrieval相邻普通测试：`136 passed, 4 skipped`；4个跳过均为默认未开启的真实BGE Smoke，随后显式开启三个本地离线开关补跑为`4 passed`；
- 截至Retrieval的允许单元回归：`625 passed, 2 skipped`；两个跳过均为Windows无法创建测试symlink（errno 22）；
- 截至Retrieval的允许数据库/服务集成：`130 passed, 3 skipped, 1 failed`；3个跳过是默认关闭的重量级Docling/OCR Smoke。唯一失败`test_seed_m1::test_seed_is_repeatable_and_matches_business_contract`发生在测试清场：它先删除仍被正式M2 `document_versions`外键引用的M1 tenant，PostgreSQL正确拒绝；不是本次Locator、FTS、pgvector、RRF、ACL或active版本回归。未为凑绿修改数据库结构或正式数据；
- Ruff format覆盖348文件通过，Ruff lint通过，11个本步/直接相邻源码Mypy通过，`compileall app scripts tests`、`pip check`和`git diff --check`通过；没有安装DeepEval；
- 单题复现与正式矩阵两个目录在记录大小、Hash和汇总后，先核对绝对路径均位于`data/evals/runtime/reports/`，再精确递归删除；本步不再有检索summary/trace临时报告。8份冻结外部原文的raw/processed副本、三个既有Parser/Chunk诊断报告和本地模型缓存属于上游正式资产，未删除；
- 随后实际依次运行`seed_m1`、`seed_m2_files`、`seed_m2_complex_files`。独立使用容器内`psql`直接只读核对：files/documents/versions=`10/10/10`、ACL 9、pending版本10、Chunk Set/Index Set/Chunk=`0/0/0`、名称匹配M2-22.6的评估tenant 0、M1 `LR-TL-MUSH-OR01 @ DE-FRA`可售125；独立文件系统核对Storage仅10个`uploads`对象，无parsed/chunks/index评估对象。Runner的进程内BGE memo cache在`finally`清空，没有持久化查询缓存。最终正式基线恢复；

能证明：正确内容进入Chunk之后，当前BGE/FTS/RRF在这40题上的真实排名能力、四类分组差异、相似产品风险、权限与版本过滤、稳定性、延迟和候选来源均已量化；无坐标DOCX region不会再拖垮请求，坏Block也不能静默改善指标；`compact/100 + depth 10 + RRF 60`是本轮值得保留的候选。

不能证明：该候选应成为生产默认；外部Judge语义质量已经通过；Noise Sensitivity可以在不生成回答时计算；生产2秒SQL超时应该直接调大；困难真实题已解决；以及Reranker、Context/Evidence、回答、Citation、Agent或任何M2-22.7能力。生产默认Chunk、TopK、RRF、SQL和数据库结构均保持不变。

## 42. M2-22.6 Ragas检索语义评分补跑与最终收口（2026-09-10）

### 42.1 目标、输入、边界与调用链

用户明确授权后，本步只补齐M2-22.6缺少的Ragas检索语义判断，不重新海选Chunk或检索参数。输入仍是冻结的18份文档、40条Debug问题，其中只有34条可回答题进入外部Judge；配置严格固定为`compact 400/500 + overlap 100 + candidate depth 10 + RRF 60`。评估Runner新增`--ragas-selected-only`硬边界，并拒绝与baseline、单配置、单题、跳过Ragas等参数组合，避免误跑完整10组/50点矩阵。

真实调用链为：

```text
18份冻结文档
→ 上传/登记 API
→ Parser / R04
→ Chunker v3 compact/100
→ Index Service
→ 本地固定BGE-M3
→ PostgreSQL FTS / pgvector
→ Dense / Lexical
→ RRF 60 Hybrid（最多20个合并候选）
→ Ragas 0.4.3检索语义适配层
→ 外部Qwen仅作为Judge
```

本步没有经过Reranker、Context Builder、Evidence、Harness、Tool、Agent/LangGraph、项目Qwen最终回答或Citation，也没有安装DeepEval。发送范围只包含34条冻结问题、对应Golden摘要和当前Hybrid候选必要原文；没有发送密钥、数据库密码、无关tenant/生产数据、评估范围外内容或Judge思维链。Trace只保存正文SHA-256，不保存正文。

### 42.2 修改文件与职责

- `scripts/run_m2_retrieval_evaluation.py`：增加并冻结`--ragas-selected-only`运行入口，只允许单一Chunk配置、depth 10和RRF 60；
- `app/evals/retrieval_runner.py`：逐题记录不含正文的Ragas进度；可回答Hybrid结果若没有候选则硬失败，不能静默漏评；
- `app/evals/ragas_retrieval.py`：冻结并启动时复核Prompt实现Hash；把最终网络、超时、限流、Provider和框架失败分开，失败不产生数值；
- `app/schemas/evaluation.py`：补充`network_error`失败类别；
- `tests/unit/test_m2_retrieval_runner.py`：验证单配置CLI范围和冲突参数；
- `tests/unit/test_ragas_retrieval_adapter.py`：验证Prompt Hash、失败分类和安全摘要不泄露底层错误正文。

生产Chunk、TopK、RRF、SQL、数据库结构和最终回答链均未修改。

### 42.3 正式运行与确定性复核

正式Run为`m2-22.6-20260909t165858-4a56843a`，UTC时间`2026-09-09T16:58:58Z`至`18:59:33Z`，约2小时。它从干净基线真实完成18份文档解析、40条查询Embedding、18个Index Set、779个Chunk和唯一一个`compact/100 + depth 10 + RRF 60`实验；Trace覆盖40题、120条Dense/Lexical/Hybrid route list和1,430个候选，候选映射失败0，完整性门禁通过，生产默认未变。

本轮Hybrid确定性结果没有覆盖旧矩阵，而是并列保留：

| 分组 | 旧矩阵Hit/Recall@8 | 本轮Hit/Recall@8 | 旧→新 MRR@10 | 旧→新 nDCG@10 | miss |
|---|---:|---:|---:|---:|---:|
| 全部34条可回答 | .9118 | .9118 | .6584 → .6929 | .7193 → .7450 | 3 → 3 |
| 真实跨境14条 | .8571 | .8571 | .4817 → .4940 | .5692 → .5789 | 2 → 2 |
| 合成跨境10条 | 1.0000 | 1.0000 | .8500 → 1.0000 | .8893 → 1.0000 | 0 → 0 |
| 通用诊断10条 | .9000 | .9000 | .7143 → .6643 | .7595 → .7226 | 1 → 1 |

关键结论是召回门槛、安全结果和漏题数复现，但前部名次没有跨清理重建完全复现。本轮全部34题Hybrid Hit@1由`.5294`变为`.5882`，真实组不变、合成组`.7000→1.0000`、通用组`.6000→.5000`。代码只读定位显示Dense与Lexical同分时按`DocumentChunk.id`排序，RRF同分也按运行期`chunk_id`排序；清理重建会产生新数据库UUID，因此同分候选可能换位。当前Run内部120条稳定性复跑仍为0变化，但这只能证明同一批Index内稳定，不能证明跨重建稳定。修复该问题会改变生产排序合同，超出本次授权，故只登记风险，不改代码或参数。

过滤审计复现为ACL 4题泄漏0、软删除2条route泄漏0、inactive Index Set泄漏0、跨tenant 80条route泄漏0；相似产品Hybrid串答仍为1/9。没有重新运行其他9组Chunk配置或其余49个矩阵点。

### 42.4 Judge身份、Ragas汇总与计分口径

依赖保持`ragas==0.4.3`、`langchain-community==0.4.1`，未升级、降级或替换。Judge身份为`qwen-openai-compatible / qwen3.8-max / api-alias-20260909`；temperature 0、top-p 1、max output 2048、seed 20260909、单次超时30秒、最多2次；Prompt身份`ragas-0.4.3-collections-source-v1`，实现包SHA-256为`fc347923599df1a73f285372856a462e4ebbdf5a3e7bffdc40fc5a7332323845`。

下表的均值只对`completed`样本做算术平均；失败和跳过没有数值，也没有按0分混入均值。因此“4/14，均值.7917”表示真实组只有4题Precision得到有效结果，不能解释为14题整体分数。

| 分组 | Context Precision | Context Recall | Context Relevancy | Noise Sensitivity |
|---|---|---|---|---|
| 全部34条 | .8024（21完成/13失败） | .9630（27完成/7失败） | .9815（27完成/7失败） | 34跳过/`input_invalid` |
| 真实跨境14条 | .7917（4完成/10失败） | 1.0000（8完成/6失败） | 1.0000（7完成/7失败） | 14跳过/`input_invalid` |
| 合成跨境10条 | .9571（7完成/3失败） | 1.0000（10完成） | 1.0000（10完成） | 10跳过/`input_invalid` |
| 通用诊断10条 | .6984（10完成） | .8889（9完成/1失败） | .9500（10完成） | 10跳过/`input_invalid` |

最终状态总计：Context Precision为21完成、6个`judge_timeout`、7个`judge_provider_error`；Context Recall为27完成、1个`judge_timeout`、6个`judge_provider_error`；Context Relevancy为27完成、7个`framework_error`；Noise Sensitivity因0.4.3要求`response`而34个全部`skipped/input_invalid`。没有构造项目回答来凑该指标。

### 42.5 34题逐项Ragas结果

表中`T`为`judge_timeout`，`P`为`judge_provider_error`，`F`为`framework_error`，`S`为`skipped/input_invalid`；所有失败/跳过格都没有数值。

| case | 分组 | Precision | Recall | Relevancy | Noise |
|---|---|---:|---:|---:|---|
| smoke-syn-001-voltage | 合成跨境 | 1.000000 | 1.000000 | 1.000000 | S |
| smoke-syn-002-cleaning | 合成跨境 | .700000 | 1.000000 | 1.000000 | S |
| smoke-syn-003-sample-size | 合成跨境 | 1.000000 | 1.000000 | 1.000000 | S |
| smoke-syn-004-exposed-wire | 合成跨境 | 1.000000 | 1.000000 | 1.000000 | S |
| smoke-syn-005-disclaimer | 合成跨境 | T | 1.000000 | 1.000000 | S |
| smoke-syn-006-weee-status | 合成跨境 | T | 1.000000 | 1.000000 | S |
| smoke-syn-007-supplier-price | 合成跨境 | 1.000000 | 1.000000 | 1.000000 | S |
| smoke-syn-008-landed-formula | 合成跨境 | 1.000000 | 1.000000 | 1.000000 | S |
| smoke-syn-009-de-june-sales | 合成跨境 | 1.000000 | 1.000000 | 1.000000 | S |
| smoke-syn-010-fr-row-range | 合成跨境 | T | 1.000000 | 1.000000 | S |
| smoke-syn-011-scan-batch | 通用诊断 | .000000 | .000000 | .500000 | S |
| smoke-syn-012-scan-sample | 通用诊断 | .642857 | 1.000000 | 1.000000 | S |
| smoke-syn-013-ad-budget | 通用诊断 | 1.000000 | 1.000000 | 1.000000 | S |
| smoke-syn-014-reorder-line | 通用诊断 | 1.000000 | 1.000000 | 1.000000 | S |
| smoke-syn-015-visual-control | 通用诊断 | .500000 | 1.000000 | 1.000000 | S |
| smoke-syn-016-visual-quarantine | 通用诊断 | 1.000000 | 1.000000 | 1.000000 | S |
| smoke-syn-017-cost-c | 通用诊断 | 1.000000 | 1.000000 | 1.000000 | S |
| smoke-syn-018-lowest-logistics | 通用诊断 | .500000 | T | 1.000000 | S |
| smoke-syn-019-replenish | 通用诊断 | .340909 | 1.000000 | 1.000000 | S |
| smoke-syn-020-lead-formula | 通用诊断 | 1.000000 | 1.000000 | 1.000000 | S |
| smoke-ext-021-gpsr-date | 真实跨境 | 1.000000 | 1.000000 | 1.000000 | S |
| smoke-ext-022-alert-count | 真实跨境 | 1.000000 | 1.000000 | 1.000000 | S |
| smoke-ext-023-alert-model-risk | 真实跨境 | 1.000000 | 1.000000 | 1.000000 | S |
| smoke-ext-024-record-retention | 真实跨境 | .166667 | 1.000000 | 1.000000 | S |
| smoke-ext-025-ioss-coverage | 真实跨境 | T | 1.000000 | 1.000000 | S |
| smoke-ext-026-oss-return-cycle | 真实跨境 | T | 1.000000 | 1.000000 | S |
| smoke-ext-027-fixed-duty | 真实跨境 | T | 1.000000 | 1.000000 | S |
| smoke-ext-028-handling-fee-vat | 真实跨境 | P | P | F | S |
| smoke-ext-029-return-invalidation | 真实跨境 | P | P | F | S |
| smoke-ext-030-h7-conditions | 真实跨境 | P | 1.000000 | F | S |
| smoke-ext-031-zh-responsible-person | 真实跨境 | P | P | F | S |
| smoke-ext-032-en-ioss-optional | 真实跨境 | P | P | F | S |
| smoke-ext-033-de-risk-categories | 真实跨境 | P | P | F | S |
| smoke-ext-034-de-return-window | 真实跨境 | P | P | F | S |

### 42.6 Judge、网络和框架Bad Case

- 超时：`smoke-syn-005/006/010`与`smoke-ext-025/026/027`的Precision，以及`smoke-syn-018`的Recall，在有界重试后仍超时；最终状态是7个`judge_timeout`，无数值；
- Provider：从`smoke-ext-028`附近起，外部Qwen明确返回HTTP 400 `Arrearage`（账户欠费/账户状态拒绝）。最终安全报告不保存Provider原始错误、请求ID或密钥，只留下13个`judge_provider_error`；涉及028—034的Precision及除030外的Recall；
- 网络：运行中观察到多次瞬时`Connection error`，部分随后成功，正式最终状态中`network_error=0`。当前报告没有持久化“恢复成功的瞬时重试次数”，因此不伪造精确数量；
- 框架：028—034的Context Relevancy在底层Provider失败后由Ragas返回无效语义结果，最终7个`framework_error`；失败没有被写成0分；
- 语义低分：在有效结果中，`smoke-syn-011-scan-batch`的Precision/Recall为0、Relevancy为.5；这与确定性检索完全漏召回一致。`smoke-ext-024-record-retention`Precision仅.166667，说明候选虽命中Golden，但噪声较多。

Provider欠费使7道后段真实题的三项语义指标不完整，因此本轮不是“34题Ragas全量成功”，也不能据此宣称真实跨境语义质量已经整体通过。已完成样本的均值仍可作为局部观察值，失败样本必须保留为缺失状态。

### 42.7 报告、验证、清理与完成标准

正式摘要`summary.json`为232,280字节，SHA-256 `24511d80c2d1b200e05a93e5b71b9a7388fa1616a350bc3b8c41040c791b3d24`；唯一Trace为1,094,678字节，SHA-256 `0d7e00192dc8664dfcaed3946ece51312a0d618c7d4329d34eee2ce6f7eeda7d`。Runner在`finally`中已清空进程内Embedding memo cache，并把评估数据库行和Storage对象清零；本节先记录摘要、逐题结果与Hash，再核对绝对路径确在`data/evals/runtime/reports/`内并精确删除唯一Run目录，最终剩余报告目录0。

实际验证结果：

- Ragas专项：`9 passed`；
- Evaluation Runner、指标与报告合同：`96 passed`；
- Index/Embedding/Retrieval相邻单元与真实数据库集成：`153 passed`；
- 截至Retrieval且排除Reranker/Context/Tool/Harness/Agent的允许单元回归：`680 passed, 2 skipped`，两个跳过为Windows symlink能力限制；
- 截至Retrieval允许数据库/服务集成：`140 passed, 2 skipped, 1 failed`；两个跳过是默认未开启的重量级Docling Smoke，唯一失败仍是历史`test_seed_m1`清场先删被正式M2外键引用的tenant，PostgreSQL正确拒绝，不是本次检索或Ragas回归；
- 显式加载固定本地BGE-M3的Embedding/Index/Retrieval Smoke：`4 passed`；
- Ruff format覆盖348文件、Ruff lint、Mypy 163源码、`compileall app scripts tests`、`pip check`和`git diff --check`全部通过；diff检查只有既有Windows LF/CRLF提示；
- Docker中的`deep-search-postgres`为healthy，pgvector扩展版本`0.8.6`；固定BGE-M3 revision `5617a9f61b028005a4858fdac845db406aefb181`本地32个文件约2.138 GiB，D盘最终清理前可用约148.74 GiB。

删除报告并完成全部测试后，最终再次依次运行`seed_m1`、`seed_m2_files`和`seed_m2_complex_files`。容器内`psql`独立只读核对：files/documents/versions=`10/10/10`，parse/index pending=`10/10`，ACL 9，Chunk Set/Index Set/Chunk=`0/0/0`，名称匹配M2-22.6的评估tenant 0，pgvector `0.8.6`；M1目标库存为on-hand 150、reserved 20、unsellable 5、available 125。文件系统独立核对Storage仅10个正式upload对象、派生或评估对象0，本次检索Run目录0；三个上游Parser/Chunk诊断报告和8份冻结外部原文的raw/processed副本按正式资产保留。最终D盘可用约148.74 GiB。

能证明：这18文档/34条可回答题在所选真实检索链上的部分语义质量得到了外部Judge有效分数；失败状态、权限过滤、候选映射、清理和依赖身份可审计；`smoke-syn-011`和`smoke-ext-024`是明确语义Bad Case；单一配置运行没有修改生产参数。

不能证明：34题三项Ragas已经全量成功；真实跨境组的局部完成均值代表完整14题；Noise Sensitivity可在无回答时计算；候选应该直接成为生产默认；跨重建排序完全稳定；以及Reranker、Context/Evidence、回答、Citation、Agent或M2-22.7任何能力。M2-22.6以“有效分数与失败均真实记录”的标准收口，而不是把外部Provider失败伪装成质量通过。

## 43. M2-22.7详细实施方案与文档同步（2026-09-10）

### 43.1 用户意图、当前现状与缺少的能力

用户先明确要求开始M2-22.7，随后补充必须先同步正式文档并查看M2-22.7的小步骤。因此本节先完成方案和状态同步，不把“开始下一步”扩大解释为已经授权运行全部五个小步；用户确认本节后才实施M2-22.7.1，每个小步完成、验证和讲解后继续停止等待。

M2-22.6已经在18份文档、40条Debug问题上筛出`compact 400/500 + overlap 100 + candidate depth 10 + RRF 60`。34条可回答题的Hybrid Recall@8为`.9118`，其中真实跨境14题为`.8571`；三条最终漏题在所选depth 10的Dense和Lexical上游都没有正确Evidence。真实组把每路候选深度扩大到20/30时，完整融合候选的miss仍为2，因此Reranker不能凭空补回这些不存在于输入候选池的证据。

现有`RerankerRetrievalService`、固定本地`BAAI/bge-reranker-v2-m3@953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e`和`ContextBuilderService`已经实现并在旧10文档小集合上通过工程验证；但旧M2-17的18条可检索Golden、Fake Embedding和最多30条候选不能代替当前18文档/40题真实BGE-M3检索集。当前缺少的是：同一批M2-22.6获权Hybrid候选经过真实BGE-Reranker后是否升排、Top5/Top8如何取舍、邻块0/1和Context 2000/3000/4000预算如何影响Golden覆盖、冗余、Token与CPU资源，以及这些结论能否在清理和权限门禁下复现。

### 43.2 本步目标与明确不做

M2-22.7只完成四件事：

1. 在完全相同且已经获权的Hybrid候选上比较RRF与Reranker，保留上游候选缺失、升排、降排和不变四类结果；
2. 顺序筛选Reranker Top5/Top8，再只对筛出的TopK比较邻块0/1与Context Token上限2000/3000/4000，不做无界笛卡尔积；
3. 用项目确定性Evaluator计算排名、Golden Evidence覆盖、Context冗余、Token和安全结果，记录本地BGE模型身份、缓存身份、p50/p95/max延迟和峰值RSS；
4. 形成Debug集候选建议与Bad Case，恢复正式Seed和Storage基线；不因指标不达标而删除难题、改变分母或直接修改生产默认。

本步不生成最终回答，不运行Ragas生成指标、Qwen、Knowledge Tool、Harness、Agent/LangGraph、公开聊天API、Citation或前端；不新增Worker/Tool，不部署GPU/独立推理服务，不修改BGE-Reranker、Context Builder、生产Chunk/TopK/RRF/Context默认值、数据库结构或正式Golden。若评估暴露生产实现缺陷，必须停止并单独提交最小修复方案。

### 43.3 前置条件与固定口径

- 数据、来源、Golden、Parser、Chunker v3、固定BGE-M3和M2-22.6所选检索配置继续使用第42节身份，不重新海选10组Chunk或RRF常数；
- 固定本地Reranker snapshot必须按既有manifest和文件Hash强制离线加载；外部Qwen欠费不阻塞本步；
- 34条可回答题全部进入排名和Context质量分母，6条无答案/ACL/版本题进入零容忍安全分栏；候选缺失必须记为上游失败，不能从Reranker分母移除；
- RRF与Reranker必须比较同一批候选身份和正文Hash；Reranker只能重排，不能新增、替换或越权读取候选；
- 每题对最大候选并集只做一次真实Reranker评分，评估缓存只在当前Run内复用。缓存身份至少绑定query Hash、候选有序身份及正文Hash、模型ID/revision、最大长度、精度和评分实现版本；缓存不进入生产链、不跨Run冒充可复现结果；
- Context必须通过现有Repository按当前用户、ACL、软删除和active代次重新取回锚点与邻块，不信任评估Runner携带的正文；Token使用项目`m2-unicode-token-counter-v1`，不能冒充Qwen真实Token；
- 当前真实跨境完整候选最多命中12/14，所以仅靠Reranker无法达到第10节建议的`.90` Recall@8门禁。M2-22.7的“评估完成”和“质量门禁通过”必须分开；若正式结果仍未达标，照实收口评估并在进入M2-22.8前单独讨论召回修复。

### 43.4 五个小步骤

#### M2-22.7.1｜评估配置、结果合同与确定性指标

- 输入：冻结的RRF候选身份、Reranker有序评分、Golden Evidence映射和Context片段元数据；
- 输出：严格的TopK/Context顺序实验计划、逐题Reranker对比、逐题Context质量和分组聚合合同；精确定义候选缺失、升排/降排、Golden覆盖、冗余、Token利用率和失败状态；
- 预计文件：`app/schemas/evaluation.py`、新增`app/evals/reranker_context_metrics.py`、新增`tests/unit/test_rag_reranker_context_metrics.py`，以及本记录/阶段入口/总看板；
- 验证：先用缺少合同或实现的RED证明缺口，再做最小GREEN；覆盖Top5/Top8、缺失候选不出分母、重复候选拒绝、邻块不能伪装Anchor、Token超限拒绝、空Context与失败非数值；运行聚焦单元、相邻评估合同、Ruff、Mypy、编译和diff检查；
- 停止点：不创建Runner、不访问数据库、不加载BGE，完成后等待用户确认M2-22.7.2。

#### M2-22.7.2｜Fake Runner、报告和Run内评分缓存

- 输入：M2-22.6所选配置、冻结数据集、确定性Fake Reranker和Fake Context读取器；
- 输出：只运行“Top5/Top8 → 选定TopK下的邻块/Token”顺序筛选的Runner、公开安全报告、逐题Trace Hash和Run内评分缓存；
- 预计文件：新增`app/evals/reranker_context_runner.py`与`app/evals/reranker_context_report.py`、新增`scripts/run_m2_reranker_context_evaluation.py`、对应Runner/报告/CLI单元测试及进度文档；
- 验证：最大候选每题只评分一次、不同query/候选Hash/模型身份不得误命中缓存、失败不缓存、报告不保存正文/路径/Storage Key、顺序计划不是`2×2×3`无界重复推理、重复运行结果确定；
- 停止点：只用Fake和内存夹具，不访问真实PostgreSQL/Storage、不加载真实BGE，完成后等待用户确认M2-22.7.3。

#### M2-22.7.3｜真实PostgreSQL/pgvector、权限重取与清理闭环

- 输入：18份冻结文档、公开摄取身份、所选Chunk/检索配置、Fake Reranker和真实Context Builder/Repository；
- 输出：真实上传、解析、分块、索引、Hybrid、Reranker边界、Context重取、权限/active版本门禁和finally清理的集成闭环；
- 预计文件：`app/evals/reranker_context_runner.py`、真实运行装配接缝、`tests/integration/test_m2_rag_reranker_context_runner.py`及直接相邻夹具/进度文档；
- 验证：候选集合严格不扩大，ACL撤销、软删除、active切代、跨tenant和坏Context来源均安全失败；Context来自数据库当前快照；评估tenant、Index/Chunk/Context/Evidence和Storage派生对象清零，正式10份Seed与M1库存125恢复；
- 停止点：不加载真实BGE、不跑40题正式质量矩阵，完成后等待用户确认M2-22.7.4。

#### M2-22.7.4｜固定本地BGE-Reranker小样本资源探针

- 输入：固定模型snapshot和少量预先指定的中英德、表格、候选缺失及无答案代表题；
- 输出：离线加载身份、单次最大候选评分、缓存复用、截断、CPU延迟与峰值RSS探针；候选缺失题必须保持缺失；
- 预计文件：真实Provider装配/CLI开关、Smoke测试或专用探针测试、报告合同和进度文档；
- 验证：local-only、manifest/Hash、模型ID/revision、一次评分复用、异常脱敏、有限值、进程退出和内存记录；结果只证明资源与链路可运行，不冒充40题质量结论；
- 停止点：不运行完整矩阵，完成后等待用户确认M2-22.7.5。

#### M2-22.7.5｜18文档/40题正式矩阵、回归与收口

- 输入：通过前四步的Runner、固定18文档/40题、所选检索配置和固定本地BGE-Reranker；
- 输出：RRF与Reranker逐题/分组排名差异、Top5/Top8选择、所选TopK下6个Context配置的覆盖/冗余/Token、Bad Case、资源、缓存、清理和候选建议；
- 预计文件：Runner/报告的必要收口、正式运行脚本测试、M2-22记录、M2入口和总看板；不预设必须修改生产文件；
- 验证：34条可回答题与6条安全题全部出现，合成/真实/诊断分组独立；项目指标可从逐题结果复算；安全泄漏0；报告先记录大小/Hash和摘要再精确删除；运行聚焦、相邻、允许单元/集成、显式本地BGE Smoke、Ruff、Mypy、编译、依赖和diff门禁；三套Seed重跑并独立核对数据库/Storage基线；
- 停止点：无论质量是否达标都先向用户讲清升降排、Context取舍、资源和首错层。未获新授权不得修改生产配置、修复召回、进入M2-22.8或运行Qwen。

### 43.5 完整调用链位置

```text
前端：不经过
→ API：M2-22.7.3/.5真实摄取时复用公开文件入口；纯指标与层级复算不经过公开聊天API
→ Schema：Evaluation、Retrieval、Reranker、Context合同
→ Agent/LangGraph：不经过
→ Harness：不经过
→ Tool：不经过
→ Service：Parser → Chunk → Index → Dense/Lexical/RRF → Reranker → Context Builder
→ Repository/Model：当前权限候选、active代次、Chunk与Context重取
→ PostgreSQL/pgvector/Storage：真实集成和正式矩阵经过
→ 外部Provider：不经过；BGE-M3与BGE-Reranker均从本地固定snapshot离线运行，Qwen不运行
```

### 43.6 阶段完成标准

- 五个小步骤各自完成RED/GREEN、相邻回归、完整记录和停止复核；
- RRF与Reranker使用同一候选集，34条可回答题分母不变，三条上游候选缺失不被归咎或隐藏；
- Top5/Top8及邻块0/1、Token 2000/3000/4000按顺序筛选，真实评分不因Context组合重复执行；
- 排名、Context覆盖/冗余/Token、CPU/RSS、模型/缓存身份、三类数据分组与Bad Case可复算；
- ACL、tenant、软删除和active版本泄漏为0，Context重新获权和预算门禁全部通过；
- 临时评估数据、报告和进程清理完成，正式Seed、Storage和M1库存基线恢复；
- “评估运行完成”与“质量达到建议门禁”分开报告；未达标时不得自动进入回答评估或修改生产参数。

### 43.7 主要风险与优先排查方向

- Reranker无法修复候选缺失：先看Dense/Lexical完整候选是否包含Golden，再看重排；不得用扩大分母、删题或邻块碰巧带回正文伪装召回成功；
- CPU与内存：旧M2-17在约15候选时Reranker p50约6.7秒、查询阶段RSS增量约1.29 GiB；先查是否每题只评分一次、batch和文本截断，再判断是否需要缩小本步运行批次，不直接引入GPU服务；
- 缓存串用：先核对query、候选有序身份/正文Hash、模型revision和评分参数是否全部进入缓存键；
- Context覆盖低：按“Reranker Anchor是否正确 → Repository当前授权重取 → 邻块关系 → overlap去重 → Token裁剪”顺序排查，不先放宽预算；
- 跨重建排序变化：M2-22.6已知UUID同分兜底风险继续单列；RRF与Reranker必须在同一Run、同一候选快照内比较，不能把不同重建的名次差归因于模型；
- 报告泄露或过大：Trace只保存公开身份、Locator、分数、正文Hash和Evidence映射，不保存正文、内部路径、Storage Key、向量、密钥或原始异常；
- 数据清理失败：先停止后续层，核对评估tenant、Context/Evidence外键、Storage派生对象和Worker/模型进程，不能在基线不干净时继续下一步。

### 43.8 当前停止点

本节只同步方案与状态，未修改`app/`、`scripts/`、`tests/`、依赖、数据库、Storage或生产配置，未运行Reranker、Context、BGE或测试。下一动作是用户确认上述五步；确认后只实施M2-22.7.1，并在验证和记录后停止。

### 43.9 本次文档同步实施记录

- 日期、阶段与步骤：2026-09-10，M2-22.7方案同步；
- 目标与实际修改：`docs/PROJECT_PROGRESS.md`把项目停止点改为M2-22.7方案待确认；`docs/progress/M2/M2_KNOWLEDGE_RAG.md`修正“仍未接通M2-22.6”和“M2-22受阻”两处过时摘要；本文把M2-22.6状态改为已完成，并新增第43节完整五步方案、边界、调用链、完成标准和风险；
- 调用链位置：只修改进度与方案文档，前端、API、Schema运行代码、Agent/LangGraph、Harness、Tool、Service、Repository/Model、PostgreSQL/pgvector/Storage和外部Provider均未经过；
- 验证方法与实际结果：`rg`复核三份文档的当前停止点、下一动作、M2-22状态、M2-22.6/.7状态和五个子步骤；活动摘要中不再存在“仍未接通M2-22.6”“M2-22.7尚未授权”或“Ragas仍待补”的旧表述。三份文档Markdown代码栅栏数分别为0、22、78，均为偶数；Tracked文档`git diff --check`通过，未跟踪的本文用`git diff --no-index --check`通过，仅有Windows LF/CRLF提示；固定Reranker revision另与`app/core/config.py`和M2-17记录交叉核对一致；
- 能证明：总看板、M2入口和M2-22过程记录现在对当前停止点、五步顺序、禁止范围和下一动作表达一致；
- 不能证明：任何M2-22.7合同、指标、Runner、缓存、真实数据库链、BGE资源或40题质量已经实现或运行；本次没有运行应用测试，也没有重新验证M2-22.6历史指标；
- 风险与排查：当前M2-22代码和记录仍位于有大量未提交变更的工作区，后续只允许在明确目标文件上做最小补丁并持续检查diff，不能覆盖或混入无关文件；
- 下一步：等待用户确认第43节方案；确认后只实施M2-22.7.1，完成验证与记录后停止。
