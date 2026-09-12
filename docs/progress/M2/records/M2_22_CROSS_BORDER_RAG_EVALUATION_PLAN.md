# M2-22｜跨境电商RAG与多Agent评估导航

> 本文件只负责M2-22当前状态、阅读导航和历史章节定位。
> 原始方案与实施证据已按完整能力拆分，正文没有删除；迁移前入口另有冻结快照。
> 最近更新：2026-09-12

## 1. 当前状态

| 项目 | 当前内容 |
|---|---|
| 状态 | 进行中 |
| 已完成 | M2-22.1至M2-22.7.5；M2-22.8.1至.8.6及`.8.7-A/B/C/D/F/G/H/I/L/M/O/Q`；M仅有界单题诊断完成，B/D为已被F撤销的历史实验，K旧补评已撤销 |
| 当前停止点 | T（A1）本地完成：正文允许重复引用，来源清单按首次出现顺序唯一登记；Prompt/共享校验/独立服务/本地指标已对齐，见第82节。历史S40题报告不改写 |
| 下一动作 | A1收口后停止，等待用户评判其余B/C/D/E疑点；不自动真实调用。T聚焦72/相邻213/完整单元1283 passed、2 skipped，静态门禁通过，新增模型费用0 |
| 已知限制 | 真实跨境Reranker Top5为12/14，未过90%门禁；用户接受暂缓修复，但Bad Case和失败结论继续保留 |
| 后续 | 采集完成不等于质量通过：保留5题引用失败、11检索不足、内容/引用完整性、38版本意图及评分问题；38引用当前有效版本，不等于已证实旧版本泄露。四段历史报告不覆盖 |

## 2. 阅读导航

| 范围 | 内容 | 记录 |
|---|---|---|
| M2-22原始方案 | 数据、指标、实验顺序、门禁、十一项步骤和风险 | [M2_22_00_STAGE_PLAN.md](M2_22_00_STAGE_PLAN.md) |
| M2-22.1至.4 | 来源Manifest、下载与Hash、40题Golden、真实摄取、Parser/OCR修复和质量门禁 | [M2_22_01_04_DATA_AND_PARSER.md](M2_22_01_04_DATA_AND_PARSER.md) |
| M2-22.5 | Chunk矩阵、标题元数据、行级Locator、边界审计和正式收口 | [M2_22_05_CHUNK_EVALUATION.md](M2_22_05_CHUNK_EVALUATION.md) |
| M2-22.6 | Dense/Lexical/RRF矩阵、Ragas检索评分和Bad Case | [M2_22_06_RETRIEVAL_EVALUATION.md](M2_22_06_RETRIEVAL_EVALUATION.md) |
| M2-22.7 | Reranker/Context合同、Fake与真实Runner、资源探针、正式矩阵和漏召回诊断 | [M2_22_07_RERANKER_CONTEXT.md](M2_22_07_RERANKER_CONTEXT.md) |
| M2-22.8 | 回答/Citation/拒答合同、Fake Runner、双Provider方案及后续回答评估 | [M2_22_08_ANSWER_CITATION.md](M2_22_08_ANSWER_CITATION.md) |

实施新步骤时只读本页、对应能力记录和直接上游，不默认加载全部M2-22历史。

## 3. 旧章节位置对照

| 原章节 | 新位置 |
|---|---|
| 第1至15节 | [原始阶段方案](M2_22_00_STAGE_PLAN.md) |
| 第16至25节 | [数据与Parser记录](M2_22_01_04_DATA_AND_PARSER.md) |
| 第26至39节 | [Chunk评估记录](M2_22_05_CHUNK_EVALUATION.md) |
| 第40至42节 | [Retrieval评估记录](M2_22_06_RETRIEVAL_EVALUATION.md) |
| 第43至49节 | [Reranker/Context记录](M2_22_07_RERANKER_CONTEXT.md) |
| 第50至53节及后续M2-22.8 | [Answer/Citation记录](M2_22_08_ANSWER_CITATION.md) |

原章节编号全部保留，因此旧链接只需要更换文件名，章节标题和证据顺序没有改写。

## 4. 当前验证摘要

| 层级 | 当前结果 | 详细证据 |
|---|---|---|
| Q同次现场留存 | RED7失败；聚焦163、最终相邻280、完整单元`1267 passed, 2 skipped`，静态门禁通过；实际资料/输入/两次输出/评分本地分离留存，真实调用0 | [第79节](M2_22_08_ANSWER_CITATION.md#79-m2-2287-q-同次评估现场证据留存2026-09-12) |
| P真实辅助评估 | 聚焦84；业务22完成/1失败/17未执行，三次Judge评分失败可继续；Answer24/Judge185、379064 Token，一次真实Answer修复仍失败；报告/用量/候选/清理/Hash核对通过，无代码变更 | [第78节](M2_22_08_ANSWER_CITATION.md#78-m2-2287-p-辅助评分策略下真实40题评估2026-09-12) |
| O辅助评分解耦 | 聚焦84、相邻179、完整单元`1251 passed, 2 skipped`，静态门禁通过；评分失败/服务停止/预算耗尽不再否决后续Answer，业务保护不变、真实调用0；替代I/K/L的Judge停机旧规则 | [第77节](M2_22_08_ANSWER_CITATION.md#77-m2-2287-o-ragas辅助评分不阻断问答评估2026-09-12) |
| L本地Judge诊断 | 白名单现场记录进入正式报告，原评分/错误分类/重试/停机规则不变；完整单元`1241 passed, 2 skipped`，真实模型调用0 | [第74节](M2_22_08_ANSWER_CITATION.md#74-m2-2287-l-judge本地白名单诊断2026-09-12) |
| K诊断前恢复 | 已撤销K未收口行为并恢复473请求硬上限；完整单元`1219 passed, 2 skipped`、静态检查通过，真实模型调用0 | [第73节](M2_22_08_ANSWER_CITATION.md#73-m2-2287-k-未收口改动撤销与诊断前恢复2026-09-12) |
| `.8.7-I`付费安全对齐 | 每题最多一次Answer修复；三题/40题外部调用硬上限33/440；系统失败后后续题不再付费；安全题允许非空获权候选但必须拒答；完整单元`1214 passed, 2 skipped`，本地Gateway/Fake 40/40通过，外部调用0 | [第71节](M2_22_08_ANSWER_CITATION.md#71-m2-2287-i-正式矩阵付费安全对齐2026-09-12) |
| `.8.7-J`真实Gateway与正式矩阵 | 三题预检3/3通过；正式矩阵前2题完成，第3题Factual Correctness为`judge_provider_error`后停止37题；合计42次DeepSeek请求、79239 tokens、零Answer修复、临时数据清零，状态受阻 | [第72节](M2_22_08_ANSWER_CITATION.md#72-m2-2287-j-真实gateway三题预检与固定40题受阻运行2026-09-12) |
| `.8.7-H`真实DeepSeek三题 | 直接回答、非空无关Context拒答、部分回答三题全部通过；3次调用、3927 tokens、均未触发修复；Qwen/Judge/40题均0次 | [第70节](M2_22_08_ANSWER_CITATION.md#70-m2-2287-h-真实deepseek三题answer小样本2026-09-12) |
| `.8.7-G`Answer拒答与输出修复 | 四类短Few-shot与一次白名单输出修复已完成；RED`11 failed, 44 passed`，聚焦`61 passed`，相邻`221 passed`，完整单元`1209 passed, 2 skipped`；第二次计入预算、ResourceUsage和Provider用量，未调用外部模型 | [第69节](M2_22_08_ANSWER_CITATION.md#69-m2-2287-g-answer拒答few-shot与一次输出修复方案2026-09-11) |
| `.8.7-F`撤销中间硬筛选 | Knowledge Worker完整上交全部获权候选，Supervisor阻止漏交，Answer输入保持Evidence正文单份；旧筛选调用/指标/CLI已删除；完整单元`1194 passed, 2 skipped` | [第68节](M2_22_08_ANSWER_CITATION.md#68-m2-2287-f-撤销knowledge-worker语义硬筛选方案与用户确认2026-09-11) |
| `.8.7-D`正式评估适配器（历史，已由F撤销） | 曾在检索后接回真实Provider筛选Evidence；当前能力和独立筛选用量已删除 | [第66节](M2_22_08_ANSWER_CITATION.md#66-m2-2287-d-正式评估evidence筛选适配器对齐方案与用户确认2026-09-11) |
| `.8.7-E`真实小样本诊断（历史） | 旧架构受阻运行：3次筛选+1次Answer、Judge 0次；失败证据保留，但不再代表当前调用链 | [第67节](M2_22_08_ANSWER_CITATION.md#67-m2-2287-e-真实deepseek-evidence筛选小样本诊断方案与用户授权2026-09-11) |
| `.8.7-C`422安全分型 | 七类固定内部阶段和未知降级已贯通；公开API不泄露；完整单元`1189 passed, 2 skipped`，Mypy 173文件通过，未调用外部Provider | [第65节](M2_22_08_ANSWER_CITATION.md#65-m2-2287-c-422安全分型诊断方案与用户确认2026-09-11) |
| `.8.7-B`Evidence可回答性门控（历史，已由F撤销） | 曾实现Knowledge Worker选择Evidence子集；因可能误删正确Chunk，当前生产代码已删除该能力，仅保留历史验证事实 | [第64节](M2_22_08_ANSWER_CITATION.md#64-m2-2287-b-evidence可回答性门控方案与用户确认2026-09-11) |
| `.8.7-A`证据门控校准 | 真实34+6完成：安全错误Top-1最高`.4835`，正常Golden低至`.0054`；拒绝6/6时最多21/34正常题有非空Context，三信号阈值不可行且未接生产；相邻单元`33 passed` | [第63节](M2_22_08_ANSWER_CITATION.md#63-m2-2287真实预检故障与三信号证据门控校准2026-09-11) |
| `.8.7`真实预检 | 固定40题正式报告不存在；正常题曾完成一次低质量Answer/Judge并在后续出现Provider耗Token后的本地422，安全题无受限Evidence泄露但可能引用无关获权Evidence；中断残留已清零 | [第63节](M2_22_08_ANSWER_CITATION.md#63-m2-2287真实预检故障与三信号证据门控校准2026-09-11) |
| Ragas生成指标与DeepSeek Judge | 好答案四项`1.0/.8536/1.0/.9898`均高于坏答案`0/.4098/0/.4714`；18次Judge调用共20170 tokens，`same_model_bias=true`；全量单元`1164 passed, 2 skipped` | [第62节](M2_22_08_ANSWER_CITATION.md#62-m2-2286-ragas生成指标与deepseek-judge人工校准2026-09-11) |
| DeepSeek真实Answer探针 | `deepseek-v4-flash`真实`/responses` 4/4通过；正常、跨语言、提示注入各合法引用1条，无证据样本零引用；765至1356ms，总计3482 tokens | [第61节](M2_22_08_ANSWER_CITATION.md#61-m2-2285-deepseek真实answer小样本探针2026-09-11) |
| 双Provider与DeepSeek接缝 | `mock/qwen/deepseek`显式选择；DeepSeek `/responses`、严格Schema、thinking关闭、无Web Tool和安全失败合同通过；全量单元`1154 passed, 2 skipped` | [第60节](M2_22_08_ANSWER_CITATION.md#60-m2-2284-b双provider共享核心与deepseek-responses适配2026-09-11) |
| Answer Provider输入投影 | 同一Evidence正文不再经`business_result`和`answer_evidence`重复进入Qwen请求；无Evidence正文保留；相邻回归`53 passed` | [第59节](M2_22_08_ANSWER_CITATION.md#59-m2-2284-a回答provider输入单份evidence投影2026-09-11) |
| Answer/Citation真实Gateway | 固定40题40/40通过；Tool 1016至5703ms，40个Context与401条Evidence等临时数据精确清零，Fake质量门禁仍为`None` | [第58节](M2_22_08_ANSWER_CITATION.md#58-m2-2283固定40题真实gateway收口2026-09-11) |
| CUDA/BGE资源探针 | CUDA版PyTorch与GTX 1650 Ti可用；两个固定`float32`模型分别/轮流运行成功，但各约2.18 GiB、不能在4 GiB显存同时常驻 | [第55节](M2_22_08_ANSWER_CITATION.md#55-m2-2283解阻探针cuda-pytorch与bge显存2026-09-11) |
| CPU/GPU分置单题Gateway探针 | BGE-M3 CPU + Reranker GPU下Tool成功3422ms；429已确定是12条Evidence超过Worker上限8，不是CUDA或本题8秒超时；临时数据归零、18/18/779不变 | [第56节](M2_22_08_ANSWER_CITATION.md#56-m2-2283解阻探针cpugpu分置真实gateway与evidence预算2026-09-11) |
| 评估专用身份与单题GREEN | App局部DI使用CPU/`float32` Embedding、CUDA/`float32` Reranker和`12/0/12` Evidence预算；单题HTTP 200、Tool 2688ms、12条Context Evidence、Golden Citation与清理通过 | [第57节](M2_22_08_ANSWER_CITATION.md#57-m2-2283-a评估专用身份与单题green2026-09-11) |
| Parser/OCR | 18/18解析、34/34恢复、OCR 4/4和18/18质量接受已在修复链收口 | [第25节](M2_22_01_04_DATA_AND_PARSER.md#25-m2-224r-04实施记录解析质量门禁与拒绝索引2026-09-08) |
| Chunk | 最终18文档、13组矩阵门禁True；标题56/56、边界断裂0/11809 | [第39节](M2_22_05_CHUNK_EVALUATION.md#39-m2-225r-04a实施记录标题来源审计版面边界校准与正式收口2026-09-09) |
| Retrieval/Ragas | Hit/Recall@8 `.9118`；Ragas只按完成样本报告，失败样本不伪造数值 | [第42节](M2_22_06_RETRIEVAL_EVALUATION.md#42-m2-226-ragas检索语义评分补跑与最终收口2026-09-10) |
| Reranker/Context | Top5 31/34，Context 32/34；真实跨境12/14，质量门禁False | [第48节](M2_22_07_RERANKER_CONTEXT.md#48-m2-2275实施记录18文档40题正式rerankercontext矩阵2026-09-10) |
| Answer/Citation | .8.1/.8.2合计`21 passed`，相邻回归`135 passed`；Fake门禁为`None` | [第53节](M2_22_08_ANSWER_CITATION.md#53-m2-2282实施记录fake-answer-runner公开安全报告与run内缓存2026-09-11) |

## 5. 数据完整性与维护规则

- 拆分前原文件共3829行；六份新记录按连续区间拆分后仍为3829行，并已逐行比较一致；
- 压缩前的项目总看板和M2入口保存在[2026-09-11冻结快照](M2_DOCUMENTATION_MIGRATION_SNAPSHOT_2026-09-11.md)中；
- 冻结快照只用于证明迁移前内容未丢失，不作为日常入口，也不继续追加；
- 后续M2-22.8.x只追加到Answer/Citation记录；.8R、.9等进入时再按完整能力决定记录位置，不为内部微步骤创建新文件；
- 完整测试命令、RED/GREEN、Hash、失败原因和能证明/不能证明只写在能力记录；本页只更新状态和链接。

## 6. 调用链位置

本次整理只位于文档与协作治理层，没有经过或修改：

```text
前端 → API → Schema → Agent/LangGraph → Harness → Tool
→ Service → Repository/Model → PostgreSQL/pgvector/Storage → 外部Provider
```
