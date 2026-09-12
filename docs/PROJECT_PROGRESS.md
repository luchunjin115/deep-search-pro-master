# 项目总进度看板

> 本文档是项目进度的统一入口，只保存当前状态、里程碑摘要、跨阶段决策、活动风险和阶段链接。
> 详细方案、逐步实施过程和完整验证证据保存在 `docs/progress/` 对应阶段记录中。
> 状态枚举：待确认、待开始、进行中、受阻、已完成。
> 最近更新：2026-09-12

## 1. 当前状态

| 项目 | 当前内容 |
|---|---|
| 当前阶段 | M2：知识库垂直切片 |
| 阶段状态 | 进行中 |
| 已完成到 | M1已完成；M2-01至M2-21已收口；M2-22.1至M2-22.7.5、M2-22.8.1至.8.6及M2-22.8.7-A/B/C/D/F/G/H/I/L/M/O/Q；M仅有界单题诊断完成，B/D为已撤销历史实验，K旧补评已撤销 |
| 当前停止点 | T（A1）本地完成：正文允许重复引用，来源清单按首次出现顺序唯一登记；Prompt/共享校验/独立服务/本地指标已对齐，见第82节。历史S40题报告不改写 |
| 下一动作 | A1收口后停止，等待用户评判其余B/C/D/E疑点；不自动真实调用。T聚焦72/相邻213/完整单元1283 passed、2 skipped，静态门禁通过，新增模型费用0 |
| 当前阻塞 | 质量问题仍在：11检索缺失，23/25/27/28/34引用格式失败，部分内容/引用不完整，38未遵守旧版本限定（非已证实旧版本泄露）；代理指标漏认与Judge不可靠评分保留 |
| 尚未具备 | 40题质量门禁通过、M2-22.8R意图与执行分流、最终Agent轨迹评估、M2前端及M4/M5能力 |

## 2. 里程碑总览

| 里程碑 | 内容 | 状态 | 详细记录 |
|---|---|---|---|
| M0 | 产品、技术、数据、评估与协作基线 | 已完成 | [M0详细记录](progress/M0_DESIGN.md) |
| M1 | 库存查询垂直切片 | 已完成 | [M1当前入口](progress/M1/M1_INVENTORY_QUERY.md) |
| M2 | 自建RAG垂直切片 | 进行中 | [M2当前入口](progress/M2/M2_KNOWLEDGE_RAG.md) |
| M3 | 多模态商品分析（秋招主线暂缓） | 待开始 | [秋招范围调整方案](design/05_Autumn_Recruitment_Scope_Adjustment_Plan.md) |
| M4 | 通用有界深度研究与报告 | 待开始 | [M4当前入口](progress/M4/M4_DEEP_RESEARCH.md) |
| M5 | Agent/RAG评估、加固与作品化 | 待开始 | 待M2/M4能力稳定后提交正式方案并单独确认 |

新窗口先读本页，再读当前阶段入口；只有实施或排查具体能力时，才按阶段入口链接读取过程记录。

## 3. 已确认的跨项目决策

| 决策 | 当前有效结论 |
|---|---|
| 项目目标 | 面向秋招AI应用、Agent、RAG和偏AI后端岗位，形成可运行、可观察、可量化且用户能讲清的作品；M4与M5仍是最终主线 |
| 主模型 | 保留Qwen，并新增DeepSeek作为可配置Agent Provider；Provider之间不得静默自动兜底，未实测的能力不得写成已完成 |
| Agent编排 | LangGraph |
| 数据与检索 | PostgreSQL + pgvector；Embedding使用BGE-M3，Reranker使用BGE-Reranker；RAG由项目自行实现 |
| 文件存储 | V1使用本地文件系统并保留Storage抽象，不部署MinIO |
| 数据口径 | 使用明确标注、版本化的合成演示数据；外部评估资料必须保留来源、许可和Hash |
| Tool与权限 | 单个Agent或Skill只获得1至5个允许Tool；模型不能直接访问数据库或提交任意URL/HTTP请求 |
| Harness | 统一负责上下文、权限、白名单、预算、超时重试、审计、证据和评估钩子 |
| MCP | V1不引入；未来连接真实外部系统或对外复用时再评估 |
| 开发方式 | 教学式协作、阶段方案先确认；默认按垂直小能力开发并采用风险驱动测试，同一能力同一层级优先扩展现有测试文件 |
| M2后续顺序 | RAG分层评估与用户复核后，先做M2-22.8R意图识别与执行分流，再做M2-22.9最终Agent轨迹评估 |
| 秋招范围 | M3暂缓；M2后继续M4通用有界深度研究和M5评估作品化，不把后移解释为删除 |
| 文档规则 | 总看板只放当前摘要；阶段入口只放地图和活动状态；完整过程与验证只写入对应能力记录，其他位置用链接引用 |

M2专属的Parser、Chunk、Index、Retrieval、Reranker、Context和Evidence决定统一以[M2入口](progress/M2/M2_KNOWLEDGE_RAG.md)及对应记录为准。

## 4. 当前验证基线

| 范围 | 当前可复核结论 | 证据 |
|---|---|---|
| Q同次现场留存 | RED7失败；聚焦163、最终相邻280、完整单元`1267 passed, 2 skipped`，静态门禁通过；实际资料/输入/两次输出/评分本地分离留存，真实调用0 | [第79节](progress/M2/records/M2_22_08_ANSWER_CITATION.md#79-m2-2287-q-同次评估现场证据留存2026-09-12) |
| P真实辅助评估 | 84项安全回归；真实业务22完成/1失败/17未执行，Judge三次评分失败不阻断后续业务；Answer24/Judge185、379064 Token，修复1次仍失败，清理和报告校验通过 | [第78节](progress/M2/records/M2_22_08_ANSWER_CITATION.md#78-m2-2287-p-辅助评分策略下真实40题评估2026-09-12) |
| O辅助评分解耦 | 聚焦84、相邻179、完整单元`1251 passed, 2 skipped`；报告v4分开业务规则与Ragas辅助结论，评分缺失为null；预算/业务停机仍保留，真实调用0 | [第77节](progress/M2/records/M2_22_08_ANSWER_CITATION.md#77-m2-2287-o-ragas辅助评分不阻断问答评估2026-09-12) |
| L本地Judge诊断 | 请求/响应/解析/评分白名单状态进入正式Case报告；原调用次数、错误类别、473硬限额和失败停机不变；完整单元`1241 passed, 2 skipped`、静态检查通过，真实模型调用0 | [第74节](progress/M2/records/M2_22_08_ANSWER_CITATION.md#74-m2-2287-l-judge本地白名单诊断2026-09-12) |
| K诊断前恢复 | 撤销未收口补评、输出失败后继续矩阵和预算扩大，恢复473请求硬上限；完整单元`1219 passed, 2 skipped`、静态检查通过，Answer与J报告指纹不变，真实调用0 | [第73节](progress/M2/records/M2_22_08_ANSWER_CITATION.md#73-m2-2287-k-未收口改动撤销与诊断前恢复2026-09-12) |
| M2-22.8.7-J | 三题真实Gateway预检3/3通过；正式矩阵前2题完成，第3题Factual Correctness出现`judge_provider_error`后停止37题；合计42次DeepSeek请求、79239 tokens、零Answer修复、临时数据清零，状态受阻 | [第72节](progress/M2/records/M2_22_08_ANSWER_CITATION.md#72-m2-2287-j-真实gateway三题预检与固定40题受阻运行2026-09-12) |
| M2-22.8.7-I | 正式评估接受每题最多一次Answer修复，三题/40题外部请求硬上限33/440、全过程473；系统失败后其余题停止付费，安全题可见无关候选但必须拒答；完整单元`1214 passed, 2 skipped`，真实本地Gateway/Fake 40/40通过并清零，外部调用0 | [第71节](progress/M2/records/M2_22_08_ANSWER_CITATION.md#71-m2-2287-i-正式矩阵付费安全对齐2026-09-12) |
| M2-22.8.7-H | 真实DeepSeek三题依次为`answered/no_evidence/partial`，引用`1/0/1`且只引用支持项；3次调用、3927 tokens、均未修复；Qwen/Judge/40题0次 | [第70节](progress/M2/records/M2_22_08_ANSWER_CITATION.md#70-m2-2287-h-真实deepseek三题answer小样本2026-09-12) |
| M2-22.8.7-G | 四类共享Few-shot与一次白名单输出修复已完成；RED`11 failed, 44 passed`，完整单元`1209 passed, 2 skipped`；第二次调用计入预算/ResourceUsage/Provider用量，外部调用0 | [第69节](progress/M2/records/M2_22_08_ANSWER_CITATION.md#69-m2-2287-g-answer拒答few-shot与一次输出修复方案2026-09-11) |
| M2-22.8.7-F | 中间LLM硬筛选已删除；Worker与Supervisor强制全部候选上交，Answer输入保持单份Evidence正文；完整单元`1194 passed, 2 skipped`，Ruff/Mypy/编译通过，未调用外部Provider | [第68节](progress/M2/records/M2_22_08_ANSWER_CITATION.md#68-m2-2287-f-撤销knowledge-worker语义硬筛选方案与用户确认2026-09-11) |
| M2-22.8.7-C | 七类固定内部诊断与未知安全降级已贯通Provider/Worker/LangGraph/Checkpoint/评估；公开API仍为通用422；完整单元`1189 passed, 2 skipped` | [第65节](progress/M2/records/M2_22_08_ANSWER_CITATION.md#65-m2-2287-c-422安全分型诊断方案与用户确认2026-09-11) |
| M2-22.8.7-D | 历史实验：曾在首次检索后调用真实Provider筛选Evidence；当前能力和独立筛选用量已由F删除 | [第66节](progress/M2/records/M2_22_08_ANSWER_CITATION.md#66-m2-2287-d-正式评估evidence筛选适配器对齐方案与用户确认2026-09-11) |
| M2-22.8.7-E | 旧架构历史运行：3次筛选+1次Answer、Judge 0次；失败证据保留，但不再代表当前调用链 | [第67节](progress/M2/records/M2_22_08_ANSWER_CITATION.md#67-m2-2287-e-真实deepseek-evidence筛选小样本诊断方案与用户授权2026-09-11) |
| M2-22.8.7-B | 历史实验：曾由Knowledge Worker选择Evidence子集；因可能误删正确Chunk，能力已由F撤销 | [第64节](progress/M2/records/M2_22_08_ANSWER_CITATION.md#64-m2-2287-b-evidence可回答性门控方案与用户确认2026-09-11) |
| M2-22.8.7-A | 真实34+6校准完成：安全错误Top-1最高`.4835`，正常Golden低至`.0054`且位于第4；拒绝6/6时最多21/34正常题能形成非空Context，因此三信号阈值不可行且未接生产 | [第63节](progress/M2/records/M2_22_08_ANSWER_CITATION.md#63-m2-2287真实预检故障与三信号证据门控校准2026-09-11) |
| M2-22.8.7预检 | 固定40题正式报告不存在；安全题受限Evidence零泄露但可能引用无关获权Evidence，正常题曾完成一次低质量Answer/Judge且后续出现Provider已耗Token后的本地422；中断残留已定点清零 | [第63节](progress/M2/records/M2_22_08_ANSWER_CITATION.md#63-m2-2287真实预检故障与三信号证据门控校准2026-09-11) |
| M2-22.8.6 | Ragas 0.4.3四项生成指标真实校准：好答案`1.0/.8536/1.0/.9898`均高于坏答案`0/.4098/0/.4714`；DeepSeek Judge 18次、20170 tokens；`same_model_bias=true` | [第62节](progress/M2/records/M2_22_08_ANSWER_CITATION.md#62-m2-2286-ragas生成指标与deepseek-judge人工校准2026-09-11) |
| M2-22.8.5 | `deepseek-v4-flash`真实`/responses` Answer探针4/4通过；正常/跨语言/提示注入样本各合法引用1条，无证据样本零引用；765至1356ms，总计3482 tokens | [第61节](progress/M2/records/M2_22_08_ANSWER_CITATION.md#61-m2-2285-deepseek真实answer小样本探针2026-09-11) |
| M2-22.8.4-B | `mock/qwen/deepseek`显式选择、共享四角色核心、DeepSeek Responses严格Schema/关闭thinking/无Web Tool及安全错误映射已完成；全量单元`1154 passed, 2 skipped` | [第60节](progress/M2/records/M2_22_08_ANSWER_CITATION.md#60-m2-2284-b双provider共享核心与deepseek-responses适配2026-09-11) |
| M2-22.8.4-A | 最终Qwen请求中Evidence正文只保留`answer_evidence`一份，无Evidence的上传文件内容仍保留；Provider与相邻Agent回归`53 passed`，生产代码Mypy 170文件通过 | [第59节](progress/M2/records/M2_22_08_ANSWER_CITATION.md#59-m2-2284-a回答provider输入单份evidence投影2026-09-11) |
| M2-22.8.3 | 固定40题真实Gateway/Fake Answer链40/40通过；Tool 1016至5703ms，6条安全题零泄露，40个Context与401条Evidence等临时数据清零；`quality_gate_passed=None` | [第58节](progress/M2/records/M2_22_08_ANSWER_CITATION.md#58-m2-2283固定40题真实gateway收口2026-09-11) |
| CUDA/BGE资源探针 | `torch 2.13.0+cu130`可见GTX 1650 Ti；BGE-M3/Reranker `float32`分别峰值约2179/2178 MiB，预热后查询/20候选重排约0.112/0.416秒；轮流加载可释放显存，但未接真实Gateway | [第55节](progress/M2/records/M2_22_08_ANSWER_CITATION.md#55-m2-2283解阻探针cuda-pytorch与bge显存2026-09-11) |
| CPU/GPU分置单题Gateway探针 | BGE-M3 CPU + Reranker GPU真实通过API/Harness/Tool/PostgreSQL链；Tool成功3422ms，最终因12条Evidence超过Worker上限8而返回429；临时数据归零、18/18/779不变 | [第56节](progress/M2/records/M2_22_08_ANSWER_CITATION.md#56-m2-2283解阻探针cpugpu分置真实gateway与evidence预算2026-09-11) |
| M2-22.8.2 | 固定40题Fake Answer编排、成功缓存、Trace Hash和脱敏报告完成；.8.1/.8.2合计`21 passed`，相邻评估回归`135 passed`；未接真实Gateway、数据库或模型 | [第53节](progress/M2/records/M2_22_08_ANSWER_CITATION.md#53-m2-2282实施记录fake-answer-runner公开安全报告与run内缓存2026-09-11) |
| M2-22.7.5 | 固定18文档、18 ChunkSet、779逻辑Chunk；Reranker Top5为31/34，邻块1+3000 Token时Context总覆盖32/34；真实跨境12/14，质量门禁仍为False | [第48节](progress/M2/records/M2_22_07_RERANKER_CONTEXT.md#48-m2-2275实施记录18文档40题正式rerankercontext矩阵2026-09-10) |
| M2-22.7诊断 | 三条完整Golden仍在Chunk中，主要问题位于跨语言召回和文档内定位；用户接受暂缓修复，但Bad Case和失败门禁继续保留 | [第49节](progress/M2/records/M2_22_07_RERANKER_CONTEXT.md#49-m2-227漏召回只读原因诊断2026-09-10) |
| M2-22.6 Ragas | 有效样本均值：Precision `.8024`（21/34）、Recall `.9630`（27/34）、Relevancy `.9815`（27/34）；超时、欠费和框架失败样本不伪造数值 | [第42节](progress/M2/records/M2_22_06_RETRIEVAL_EVALUATION.md#42-m2-226-ragas检索语义评分补跑与最终收口2026-09-10) |
| M2运行基线 | M2-21公开Agent Gateway与多Agent闭环已完成；M1德国仓可售库存最近核对仍为125。更早逐步验证数字按对应能力记录查询 | [M2入口](progress/M2/M2_KNOWLEDGE_RAG.md) |

以上保留各步实际验证，Q是当前本地代码基线；I/K/L关于Judge失败停止后续问答的旧结论已由O替代，历史报告不改写。代码后续变化导致结论失效时，先更新对应能力记录，再同步本表。

## 5. 当前风险与阻塞

| 风险或边界 | 当前处理 |
|---|---|
| `.8.7-P`Answer阻断 | 第23题Tool成功但Answer两次输出最终citation_contract，API422；脱敏记录无法还原具体标签错误，不放宽安全规则、不自动付费复现 |
| `.8.7-J/N`历史Judge阻断 | O规则已在P真实证明第5/8/18题评分失败后继续，历史报告不改写；评分截断和低分仍保留，不单独否决业务推进 |
| `.8.7-I`本地Gateway曾有一次性能抖动 | 第一次显式40题Fake Answer运行有至少一题Tool超过8秒，未放宽门禁；第二次相同运行40/40通过，Tool 1204至4797ms且临时数据清零。J步仍必须先跑三题Gateway预检，预检失败不进入40题 |
| `.8.7-H`真实范围有限 | 三个短合成Answer输入真实通过，但没有经过Gateway/数据库/BGE/Reranker，也未真实触发修复；不得外推到长Context、40题或持续可用性 |
| `.8.7-G`修复成功仍未实证 | P第23题真实触发一次修复并计入两次Provider用量，但第二次仍失败；首次阶段/完整ResourceUsage快照未留，完整预算与修复成功分支仍依赖本地测试 |
| `.8.7`不得误记为完成 | 真实预检已经暴露证据门控、422诊断和回答质量问题；用户要求先修已知错误，固定40题付费矩阵保持暂停，不根据不完整运行猜测调用数或Token |
| 旧Evidence筛选小样本受阻 | `.8.7-E`保留为旧架构历史失败；由于中间筛选已由F撤销，不再继续细分或复测这条调用链 |
| 候选不等于答案证据 | 三信号阈值和Knowledge Worker语义硬筛选均已停止；当前全部获权候选进入Answer以避免召回损失。回答后支持性验证尚未实现，不能宣称幻觉已解决 |
| DeepSeek真实证明范围有限 | `.8.5`只证明4个合成Answer输入在一次运行中真实可用；不代表真实Gateway、40题质量、长Context、持续可用性或一般化提示注入防护 |
| DeepSeek同模型评审偏差 | `.8.6`生成模型与Judge均为`deepseek-v4-flash`，真实好坏方向校准通过但强制记录`same_model_bias=true`；不能把自评分数当成独立最终结论 |
| Evidence输入重复与语义近似重复 | `.8.4-A`只消除了同一Evidence正文经`business_result`和`answer_evidence`重复发送；相似但身份不同的Chunk尚未做语义去重，后续必须独立评估召回覆盖率后再决定 |
| Agent证据包大小 | `.8.3`发现12段Context可能超过Agent结构化JSON的16KB边界；现按实际序列化大小等比例缩短各段给模型看的正文副本，保留全部Evidence身份，原始Context/Evidence不改。真实模型回答质量仍需后续验证 |
| 真实跨境召回未过门禁 | 保留12/14、三条Bad Case和`quality_gate_passed=False`；不删题，不把Context邻块补回说成Reranker命中 |
| Fake结果被误读为真实质量 | Fake报告始终为`quality_gate_passed=None`；真实Gateway、Provider和Judge分别在后续步骤验证 |
| Reranker CPU较慢 | 历史CPU 40题总耗时约771.92秒、峰值RSS约3.60 GiB；GPU预热后20候选约0.416秒，但只证明隔离探针，不代表Gateway 8秒门禁已通过 |
| 外部模型和Judge | Key、余额、网络或框架失败保持失败/非数值，不用Fake结果替换真实结论 |
| 固定评估语料可能被测试重置 | 会重建schema的测试先运行，再调用幂等准备器恢复18文档/779 Chunk；普通查询实验不得重新解析和切块 |
| 当前规模有限 | 只证明小型演示语料和有限并发；更大规模、负载、灾难恢复与生产部署留到M5 |
| 文档再次膨胀 | 新完成步骤只在能力记录写完整证据；本页最多同步一行状态、一个活动风险或一条当前基线 |

## 6. 文档入口

- [M2阶段入口](progress/M2/M2_KNOWLEDGE_RAG.md)
- [M2-22导航页](progress/M2/records/M2_22_CROSS_BORDER_RAG_EVALUATION_PLAN.md)
- [本次文档迁移冻结快照](progress/M2/records/M2_DOCUMENTATION_MIGRATION_SNAPSHOT_2026-09-11.md)

本次整理只改变文档组织，没有修改或重新验证前端、API、Schema、Agent/LangGraph、Harness、Tool、Service、Repository/Model、PostgreSQL/pgvector、Storage或外部Provider。
