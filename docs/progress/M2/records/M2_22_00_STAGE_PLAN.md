# M2-22｜跨境电商 RAG 与多 Agent 评估方案

> 文档状态：进行中；M2-22.1 至 M2-22.8.2已完成；用户已接受M2-22.7已知限制，并确认保留Qwen、新增DeepSeek；当前停止等待单独授权M2-22.8.3
>
> 方案形成日期：2026-09-07
>
> 当前授权边界：用户已确认M2-22.8七步方案并单独授权完成M2-22.8.1至.8.2；不得自动实施M2-22.8.3或后续步骤，不得运行Knowledge Tool、Gateway、真实模型/Judge或修改检索/Chunk/生产配置
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

- 状态：五步详细方案和M2-22.7.1至.7.5均已完成；评估运行完成、安全门禁通过，但真实跨境12/14低于90%质量门禁；
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

