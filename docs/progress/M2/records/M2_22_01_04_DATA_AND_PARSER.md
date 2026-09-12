# M2-22.1至.4｜数据、Golden与Parser/OCR记录

> 以下第16至25节从原M2-22总记录按连续区间原样迁入，章节编号、验证数字和历史结论均保留。

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

