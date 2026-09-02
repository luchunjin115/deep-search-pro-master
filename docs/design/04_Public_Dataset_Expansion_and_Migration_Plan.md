# 公开商品数据扩充与跨电脑恢复方案

> 文档状态：已记录，待在另一台电脑上重新确认后实施  
> 记录日期：2026-09-02  
> 当前电脑约束：只保存本方案，不下载数据、不修改数据库、不生成新 Seed、不建立索引  
> 适用范围：M1 商品与库存演示数据、M2 商品知识 RAG 与评估数据，兼顾后续 M3 数据入口  
> 与现有基线的关系：本方案尚未实施，不改变当前 `m1-v1`、`m2-v1` 和“现有业务数据为合成演示数据”的已验证结论

## 1. 为什么需要这份方案

当前项目已经证明了两条小规模链路能够运行：

- M1 能够通过 PostgreSQL 查询商品和库存，并返回数据库 Evidence；
- M2 能够上传、解析、切块、Embedding、混合检索、Reranker、构造 Context 和保存文档 Evidence。

但当前数据量主要用于证明“链路能工作”，还不能充分证明：

- 面对成千上万件商品时，M1 的查询、权限和证据仍然正确；
- 面对更多商品知识时，M2 不会把不同商品的答案串在一起；
- Hybrid Retrieval 和 BGE-Reranker 确实把正确证据排在前面；
- 换电脑后能够恢复同一批演示数据，而不是依赖旧电脑中的 Docker Volume。

本方案的核心不是把几十万条数据一次性全部导入，而是建立一条可解释、可复现、可迁移的数据流水线。

## 2. 本方案目标与明确不做的内容

### 2.1 目标

1. 使用许可相对明确的公开 Amazon 商品数据扩充商品目录；
2. 在公开商品之上生成明确标注的合成 SKU、仓库和库存；
3. 使用公开商品问答和检索标注扩充 M2 语料与 Golden Set；
4. 每个字段都能说明来源，不能把合成库存描述成真实 Amazon 库存；
5. 通过固定版本、文件 Hash、抽样规则和随机种子，使另一台电脑能够重建同一批数据；
6. 同时保留 PostgreSQL 与 Storage 快速备份，缩短迁移时间；
7. 保留当前小型 Seed，新增数据包不能覆盖已经验收的 `m1-v1` 和 `m2-v1`。

### 2.2 本方案暂不做

- 不在当前电脑下载任何公开数据集；
- 不连接真实 Amazon SP-API、Seller Central、ERP 或真实卖家账户；
- 不声称公开商品数据包含真实卖家库存；
- 不把完整公开数据集、商品图片、数据库备份或模型权重提交到 Git；
- 不一次性导入 Amazon-M2 全量约百万商品；
- 不提前实现 M3 图片分析、推荐系统或需求预测；
- 不因为数据扩充而绕过现有 Schema、Service、权限、Harness 和 Evidence 边界；
- 不在未做许可证复核前公开再分发第三方原始数据。

## 3. 推荐数据源

### 3.1 第一优先级：Amazon-M2

用途：为 M1 提供公开商品主数据，并为后续推荐或多语言研究保留入口。

公开字段包括：

- ASIN；
- locale；
- title；
- price；
- brand、color、size；
- model、material、author；
- desc 商品卖点描述；
- 匿名商品交互会话。

与项目的关系：

- 德国站有约 51 万件商品，可用于构造德国市场商品目录；
- 商品字段来自公开数据；
- Seller SKU、仓库、可售、预留、残损和在途库存仍由项目合成；
- 官方不同页面或版本的商品数量略有差异，实施时必须以实际下载文件的行数、版本和 Hash 为准，不能只抄网页数字。

许可证：论文附录说明 Amazon-M2 数据使用 Apache 2.0。实施前仍需把实际下载页面、许可证文件和访问日期写入 Manifest。

官方入口：

- <https://www.aicrowd.com/challenges/amazon-kdd-cup-23-multilingual-recommendation-challenge>
- <https://www.amazon.science/publications/amazon-m2-a-multilingual-multi-locale-shopping-session-dataset-for-recommendation-and-text-generation>
- <https://openreview.net/pdf?id=uXBO47JcJT>

### 3.2 第一优先级：Contextual Product QA

用途：为 M2 提供商品问题、候选证据、相关性标签和标准答案。

优先使用：

- `semiPQA`：商品半结构化属性问答；
- `ePQA`：包含 candidate、context、三档相关性标签和人工答案；
- `xPQA`：包含德语在内的 12 种语言，可支撑德国市场问答评估；
- `hetPQA`：在需要测试多来源证据时再使用，不作为第一批全量导入对象。

这些字段能够映射到当前 M2：

```text
question
→ 检索 candidate/context
→ Reranker 根据 label 排序
→ Context Builder
→ Evidence
→ 使用 answer 做答案评估
```

许可证：CDLA 1.0 Sharing License。实施前必须保留许可证副本和归属说明。

官方入口：

- <https://github.com/amazon-science/contextual-product-qa>

### 3.3 第二优先级：Amazon ESCI Shopping Queries

用途：测试商品检索与 Reranker，不直接充当库存数据。

核心内容：

- 商品标题、描述、卖点、品牌和颜色；
- 查询与商品对；
- `Exact`、`Substitute`、`Complement`、`Irrelevant` 四档人工相关性标签；
- 约 13 万个查询和约 262 万条相关性判断。

适合验证：

- Lexical、Dense、Hybrid 和 RRF 的 Recall@K；
- BGE-Reranker 的 nDCG@K、MRR 和排序提升；
- 完全相关、替代、配套和无关商品是否保持合理顺序。

边界：ESCI 主要覆盖英语、日语和西班牙语，没有德语，不能代替德国市场商品演示数据。

许可证：Apache 2.0。

官方入口：

- <https://github.com/amazon-science/esci-data>
- <https://www.amazon.science/code-and-datasets/shopping-queries-dataset-a-large-scale-esci-benchmark-for-improving-product-search>

### 3.4 后续可选：ABO 与 Amazon Bin Image

ABO 可为 M3 提供商品图片、多语言标题、品牌、型号、尺寸和材质；Amazon Bin Image 可用于仓库货箱商品识别与计数。

这两套数据当前不进入 M1/M2 第一批实施：

- 图片和 3D 数据体积很大；
- 当前 M3 尚未开始；
- ABO 官方页面之间存在 CC BY 4.0 与 CC BY-NC 4.0 的许可表述差异，未澄清前应按更严格的非商业边界处理；
- Amazon Bin Image 使用 CC BY-NC-SA 3.0 US，不能把它当作真实卖家可售库存。

官方入口：

- <https://amazon-berkeley-objects.s3.us-east-1.amazonaws.com/index.html>
- <https://registry.opendata.aws/amazon-bin-imagery/>

### 3.5 暂不优先：Amazon Reviews 2023

Amazon Reviews 2023 数据量很大，但维护者公开说明无法为数据集分配明确许可证，主要按研究用途提供。因此第一版不把它作为公开简历仓库或在线演示的核心数据源。

只有在 Amazon-M2、Contextual Product QA 和 ESCI 无法满足目标，并再次完成许可证评估后，才讨论本地研究性使用；不得提交原始评论或完整商品元数据到 Git。

## 4. 数据真实性分层

每条数据都必须标记来源层级，避免“半真半假”混在一起后无法解释。

| 层级 | 含义 | 示例 | 对外描述 |
|---|---|---|---|
| 公开来源事实 | 原始公开数据直接提供 | ASIN、标题、品牌、公开价格、商品描述 | 来源于指定公开研究数据集 |
| 确定性转换 | 不改变事实，只做格式清洗 | 规范 locale、拆分属性、转换 CSV | 由版本化脚本转换 |
| 合成运营数据 | 项目按规则生成 | Seller SKU、仓库、可售、预留、残损、在途 | 明确标注为合成演示数据 |
| 模型派生数据 | 模型计算结果 | Embedding、Reranker 分数 | 记录模型和快照版本 |
| 人工评估数据 | 人工确认的测试事实 | Golden 问题、证据、预期答案 | 记录标注者和版本 |

建议未来为导入记录或 Manifest 至少保留：

```text
source_dataset
source_version
source_url
source_license
source_file_sha256
source_record_id
source_kind
transform_version
synthetic_seed
generated_at
```

其中 `source_kind` 至少区分：

```text
public_source
deterministic_transform
synthetic_demo
model_derived
human_golden
```

## 5. 数据实际保存在哪里

### 5.1 Git 仓库中保存的内容

Git 负责保存能够重建数据的方法，而不是保存全部大数据。

应提交：

- 数据源说明和许可证记录；
- Manifest；
- 下载、校验、抽样、合成和导入脚本；
- 固定随机种子与字段映射；
- 小型、许可允许的演示 Seed；
- Golden Set 和评估配置；
- 备份与恢复操作说明，但不提交真实备份文件。

不应提交：

- 完整 Parquet、TSV、图片和 3D 文件；
- `data/storage/`；
- PostgreSQL 数据目录或 dump；
- `data/model-cache/`；
- 用户上传文件；
- API Key、数据库密码和登录凭据。

### 5.2 另一台电脑上的外部数据根目录

实施时应新增一个可配置的“公开数据根目录”，放在 Git 仓库之外。具体环境变量名在实施方案确认时决定，不在本记录中提前修改配置。

建议逻辑结构：

```text
public-data-root/
├── raw/                 # 官方原始文件，只读保存
│   ├── amazon-m2/
│   ├── contextual-pqa/
│   └── esci/
├── processed/           # 清洗、抽样和转换结果
│   ├── catalog/
│   ├── inventory/
│   ├── rag/
│   └── evals/
├── manifests/           # 文件Hash、版本、行数、许可和处理结果
└── backups/
    ├── postgres/
    └── storage/
```

`raw/` 原则上只读；处理脚本不得原地覆盖官方原始文件。

### 5.3 PostgreSQL 与 pgvector

导入后的运行数据保存在 PostgreSQL：

- 商品、SKU、仓库和库存；
- 文件、文档、版本、ACL；
- Chunk、FTS 和 pgvector 向量；
- Context、Evidence、AgentRun 和 ToolCall。

当前 PostgreSQL 运行在 Docker 中，Docker Volume 只属于当前电脑，不会跟随 Git 自动迁移。不得把“容器重启后数据还在”误解为“换电脑后数据也会自动出现”。

### 5.4 M2 Local Storage

当前配置默认使用 `data/storage`，保存：

- 上传原文件；
- 解析 Artifact；
- Chunk Artifact；
- 其他文件型中间产物。

数据库只保存这些对象的元数据和 Storage Key。换电脑时如果只恢复 PostgreSQL、不恢复 `data/storage`，会出现数据库记录存在但物理文件缺失的问题。

## 6. 换电脑后的双保险恢复策略

### 6.1 第一种：可重复重建

这是最重要、最适合简历展示的方式：

```text
官方数据 + 固定版本 + SHA-256
→ 固定清洗规则
→ 固定抽样规则和随机种子
→ 固定合成库存规则
→ 导入 PostgreSQL
→ 重新解析、切块和生成 Embedding
```

优点：即使旧电脑完全不可用，也能重建。  
缺点：重新下载、Embedding 和索引会花时间。

### 6.2 第二种：快速备份恢复

需要同时保存：

```text
PostgreSQL逻辑备份
+ data/storage压缩包
+ 对应Manifest和代码commit
```

恢复顺序：

1. 在新电脑检出对应 Git commit；
2. 启动相同主版本的 PostgreSQL 与扩展；
3. 恢复 PostgreSQL 逻辑备份；
4. 把 Storage 恢复到配置指定目录；
5. 校验数据库 Storage Key 对应文件是否存在；
6. 运行 M1/M2 回归、索引和 Evidence 一致性检查。

优点：恢复快。  
缺点：备份和代码版本不匹配时可能失败。

两种方式都要保留，不能只依赖其中一种。

## 7. 推荐实施规模

先按三档推进，不能直接全量导入。

| 数据档位 | M1 商品 | 仓库 | M2 商品/知识 | 评估问题 | 目的 |
|---|---:|---:|---:|---:|---|
| Smoke | 100 | 3 | 50 | 20 | 验证格式、许可记录和完整链路 |
| Demo | 5,000 | 3至5 | 500至2,000 | 200至500 | 公开演示和简历主数据包 |
| Scale | 10,000或按基准调整 | 3至5 | 根据资源基准确定 | 至少1,000个检索查询 | 验证索引时间、查询延迟和质量变化 |

是否进入下一档必须由上一档的磁盘、导入时间、Embedding 时间、检索质量和 Reranker 延迟共同决定。

## 8. 在另一台电脑上的实施顺序

每一步只解决一个问题，完成验证和记录后再进入下一步。

### 步骤 0：重新确认阶段与代码基线

目标：防止这份旧计划覆盖未来已经变化的代码事实。

操作前读取：

- `docs/PROJECT_PROGRESS.md`；
- 当时的当前阶段入口；
- 本方案；
- 与 Seed、Storage、索引直接相关的最新过程记录。

验证：确认 Git commit、数据库迁移 head、Docker/PostgreSQL 版本和当前 Seed 版本。

### 步骤 1：提交正式阶段方案并获得确认

目标：决定数据扩充属于当时的当前里程碑，还是单独建立数据治理能力记录。

必须明确：

- 实际下载哪些数据；
- Smoke/Demo/Scale 做到哪一档；
- 预计磁盘与运行时间；
- 修改文件；
- 失败回退方式；
- 是否允许更新 `.gitignore`、配置、Schema 或迁移。

没有用户明确确认，不开始下载和编码。

### 步骤 2：建立目录、Manifest 和许可证门禁

目标：先能回答“文件从哪里来、能不能用、有没有被改过”。

预计修改或新增：

- `.gitignore`：排除外部原始数据、加工大文件和备份；
- `.env.example` 与配置：增加外部数据根目录，但不写真实绝对路径；
- 数据 Manifest Schema；
- 数据源与许可证记录；
- Manifest 单元测试。

验证：使用一个很小的本地夹具验证路径边界、Hash、许可证必填和 Git 忽略规则，不下载正式数据。

### 步骤 3：只下载并校验一个 Amazon-M2 原始文件

目标：验证官方入口、许可、文件大小、格式和 Hash，不开始全量业务导入。

验证：

- 下载来源为 Manifest 中的白名单 URL；
- 保存 SHA-256、字节数、实际行数和 Schema；
- 重新运行时不会静默覆盖不同 Hash 的文件；
- 原始文件保持只读，不被转换脚本改写。

### 步骤 4：生成 Amazon-M2 Smoke 商品样本

目标：确定性抽取 100 件德国商品，先验证字段质量。

需要检查：

- ASIN 和 locale；
- 标题、品牌、价格、尺寸和材质的缺失率；
- 重复 ASIN；
- 异常价格和乱码；
- 相同随机种子是否产生相同结果和相同 Hash。

本步只输出加工文件，不导入正式数据库。

### 步骤 5：生成合成 SKU、仓库和库存

目标：在公开商品之上建立可解释的 M1 运营数据。

合成字段至少区分：

- `on_hand`：仓库中记录的总量；
- `reserved`：已被订单或流程占用；
- `unfulfillable`：残损或不可售；
- `inbound`：在途，不计入当前可售；
- `available`：按固定公式计算的可售量；
- `as_of`：库存快照时间。

公式和边界必须与现有 M1 Service 一致。所有合成记录必须带数据包版本与随机种子。

验证：相同输入生成相同输出；库存非负；可售公式成立；商品、SKU、仓库外键完整；包含低库存、断货、预留、残损和正常库存等可解释场景。

### 步骤 6：建立新版本数据包并导入 M1

目标：保留 `m1-v1`，以新版本并行导入 Smoke 数据。

调用链位置：

```text
公开数据/合成库存
→ 导入 Schema
→ 数据校验 Service
→ Repository / SQLAlchemy Model
→ PostgreSQL
→ 现有 Inventory Service / Tool / Harness
→ API 与前端查询
```

验证：数据库约束、数量统计、固定问题、权限矩阵、Evidence、重复导入幂等性和 M1 全量回归。

### 步骤 7：转换 Contextual Product QA Smoke 数据

目标：把 20 至 50 个问答转换成当前解析器能够安全接收的 CSV/XLSX 或其他已支持格式。

转换必须保留：

- ASIN；
- question；
- candidate；
- context；
- source；
- label；
- answer；
- 原始记录 ID。

验证：转换前后记录数量、文本 Hash 和标签分布；不得把标准答案混进供检索文档而造成评估泄漏。

### 步骤 8：通过现有 M2 链路导入和索引

调用链位置：

```text
知识文件
→ 文件 API / Schema
→ File / Document Service
→ Local Storage + PostgreSQL
→ Parser Router
→ Canonical Artifact
→ Chunk
→ BGE-M3
→ PostgreSQL FTS + pgvector
→ Hybrid / RRF
→ BGE-Reranker
→ Context / Evidence
```

验证：文件、文档、Chunk、Index Set、向量维度、active 代次、ACL、检索、Reranker、Context 与 Evidence 全链一致。

### 步骤 9：建立 PQA 与 ESCI Golden Set

目标：将“数据多了”转化为可以量化的质量结论。

必须隔离：

- 调试集：开发时允许查看；
- 验证集：用于调整参数；
- 测试集：最终验收前不得用于调参。

至少记录：Recall@K、MRR、nDCG、引用正确率、无答案拒答率、跨商品串答率、p50/p95 延迟和峰值内存。

### 步骤 10：扩大到 Demo 档并做恢复演练

目标：只有 Smoke 全部通过后，才扩展到 5,000 件商品和 500 至 2,000 个知识对象。

最终必须在干净环境完成一次：

```text
代码检出
→ 数据重建或备份恢复
→ 数据库迁移
→ Seed/导入
→ M2索引
→ M1/M2回归
→ 统计和Hash对比
```

没有完成干净环境恢复，不能宣称“换电脑可以复现”。

## 9. 验证矩阵

| 验证对象 | 方法 | 能证明什么 | 不能证明什么 |
|---|---|---|---|
| 下载文件 | URL、许可证、大小、SHA-256 | 下载对象未被静默替换 | 数据内容一定真实完整 |
| 确定性抽样 | 相同版本和随机种子重复运行 | 能生成同一批样本 | 样本代表全部 Amazon 商品 |
| 合成库存 | 公式、约束、边界场景测试 | 数据内部一致、可解释 | 库存是真实卖家数据 |
| PostgreSQL导入 | 行数、外键、唯一约束、幂等测试 | 业务表关系正确 | 高并发生产能力 |
| M2索引 | Chunk/Index Set/向量/active检查 | 索引闭环完整 | 回答质量一定足够 |
| Golden Set | Recall、MRR、nDCG、引用评估 | 检索和排序质量可比较 | 覆盖所有真实用户问题 |
| 备份恢复 | 新目录或干净环境恢复演练 | 备份在指定版本可用 | 任意未来版本都兼容 |
| 重建恢复 | 从 Manifest 和脚本重新生成 | 不依赖旧电脑 Docker Volume | 官方下载地址永远可用 |

## 10. 阶段完成标准

全部满足后，数据扩充能力才可标记为完成：

1. 当前小型 `m1-v1`、`m2-v1` 仍可恢复并通过回归；
2. 每个外部文件都有来源、许可、版本、Hash、行数和访问日期；
3. 同一版本与随机种子可以生成完全相同的 Smoke/Demo 数据包；
4. 公开字段、转换字段、合成字段和模型派生字段能够逐条区分；
5. M1 新数据通过 Schema、Service、Model、PostgreSQL、Tool、Harness、API 和前端查询验证；
6. M2 新数据通过 Storage、Parser、Chunk、Embedding、pgvector、Reranker、Context 和 Evidence 验证；
7. Golden Set 与调试数据隔离，指标和延迟有真实基线；
8. PostgreSQL 与 Storage 已完成一次配对备份和恢复；
9. 已在干净环境完成一次从 Manifest 重建；
10. 文档明确说明公开数据来源和合成库存边界，不暗示 Amazon 背书或真实经营数据。

## 11. 主要风险与优先排查方向

| 风险 | 影响 | 优先排查方向 |
|---|---|---|
| 许可证或下载条款变化 | 无法公开演示或再分发 | 先停用该数据源，核对实际许可证文件和来源日期 |
| 官方文件版本变化 | 同名文件生成不同结果 | SHA-256、版本目录、禁止静默覆盖 |
| 磁盘不足 | 下载或索引中断 | 下载前检查文件大小与可用空间，保留原始、加工、索引和备份余量 |
| 商品字段大量缺失 | M1演示质量低 | 先做 Smoke 缺失率报告，再定抽样过滤规则 |
| 重复ASIN或多locale冲突 | 商品身份错误 | 使用 `locale + ASIN` 复合身份并记录去重规则 |
| 合成库存看起来像真实数据 | 简历和演示表述失真 | UI、Manifest、Evidence 和文档统一显示“合成演示库存” |
| 大规模Embedding耗时 | 新电脑长时间无响应 | 分批、断点、Index Set幂等与资源基准，不直接全量 |
| Reranker CPU延迟扩大 | 聊天响应过慢 | 候选裁剪、批处理、GPU或有证据支持的路由优化 |
| PQA答案泄漏到检索文档 | 评估虚高 | 文档语料、问题和标准答案物理分离 |
| 数据库恢复但Storage缺失 | Evidence无法重取 | PostgreSQL与Storage使用同一备份清单并做文件存在性检查 |
| 只保存Docker Volume | 换电脑无法恢复 | 逻辑备份 + 可重复重建，不手工复制Docker内部目录 |
| 官方下载地址失效 | 无法重建 | 合法范围内保留原始文件备份、Hash和许可副本 |

## 12. 新电脑开始前检查清单

- [ ] 先读取 `docs/PROJECT_PROGRESS.md` 和当时的阶段入口；
- [ ] 确认本方案仍与当前代码、迁移和 Seed 兼容；
- [ ] 确认用户重新批准实施范围；
- [ ] 确认 Git 工作区状态，不能覆盖用户未提交修改；
- [ ] 确认 Docker、PostgreSQL、pgvector、Python 和模型运行条件；
- [ ] 确认外部数据目录与备份目录不在 Git 仓库内；
- [ ] 确认磁盘空间足够容纳原始文件、加工文件、索引、模型和备份；
- [ ] 确认实际许可证允许预期用途；
- [ ] 先执行 Smoke，不直接执行 Demo 或 Scale；
- [ ] 每个小步骤完成后同步阶段 `records/`、阶段入口和必要的总进度摘要。

## 13. 本次记录的实际结果

本次只新增本方案并给现有数据设计增加导航入口：

- 没有下载 Amazon-M2、Contextual Product QA、ESCI、ABO 或 Amazon Bin Image；
- 没有创建外部数据目录；
- 没有修改 `.gitignore`、环境变量、Schema、Service、Model 或迁移；
- 没有改动 PostgreSQL、Docker Volume、`data/storage`、pgvector 或模型缓存；
- 没有改变当前 M1/M2 已验证数据和下一开发停止点。

因此本次只能证明方案已经进入项目文档并可供另一台电脑继续执行，不能证明任何数据已经下载、可解析、可导入或可恢复。
