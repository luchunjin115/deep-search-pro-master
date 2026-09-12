# 面试官角度问题清单

## 一、项目背景与业务理解

1. 用一句话说明这个系统到底解决什么业务问题？目标用户是谁？典型使用场景是什么？
2. 举 3 个真实 query，分别会走 Fast Path、Pipeline、Multi-Agent。
3. “深度研究”在你的系统里如何定义？它和普通问答、报表查询、数据检索有什么区别？
4. Amazon 欧洲站涉及 DE/FR/IT/ES/NL 等多个站点，系统是否处理本地语言、货币、税率、产品合规等差异？
5. 内部库存、企业文档、公开市场数据三类数据源分别包含哪些具体数据？数据规模、更新频率、权限要求如何？
6. 企业数据与公开数据在最终回答中如何区分和标识？用户如何判断哪些结论来自内部可信数据，哪些来自网络？
7. 这个系统是否有真实用户？如果没有，你们如何验证业务价值？
8. 在选品与运营场景中，哪类错误最不可接受？例如库存数量错、欧盟法规错、市场判断错，系统如何规避？

## 二、路由与意图识别

1. Fast Path、Pipeline、Multi-Agent 三级的定义和边界是什么？请给出具体判定规则。
2. 路由是如何实现的？规则、分类小模型、LLM 判断，还是混合方案？为什么不用简单的阈值或关键词？
3. 120 条冻结测试集是怎么构建的？类别分布如何？是否包含边界样本、对抗样本？
4. Macro-F1 92% 具体怎么计算？除了 Macro-F1，还看了哪些指标？为什么选择 Macro-F1？
5. 路由错误成本是否不对称？复杂请求误入 Fast Path 和简单请求误入 Multi-Agent，哪个代价更高？为什么？
6. 线上真实流量与 120 条冻结测试集的分布是否一致？有没有发生数据漂移？
7. 是否支持“不确定时升级到 Multi-Agent”？如果支持，阈值如何设定？如何避免频繁升级？
8. 你如何应对 prompt injection 尝试欺骗路由，或直接诱导系统调用内部工具？
9. 如果新增一类业务，比如广告投放研究，你的路由体系如何扩展？
10. p95 延迟从 9.8s 降到 4.1s，仍然不算低。剩余时间主要花在哪里？还有哪些优化空间？
11. 平均模型调用次数从 6.2 降到 2.4，这个统计口径是什么？是否包含路由、Worker、摘要、重排所有模型调用？
12. 简单请求 p95 4.1s 对用户体验是否可接受？如果不可接受，你会怎么进一步优化？

## 三、LangGraph 与编排设计

1. 为什么选择 LangGraph，而不是 FastAPI + 自研状态机、Temporal、Airflow 或 CrewAI？关键收益是什么？
2. 你的 LangGraph State 包含哪些字段？请画出 state schema 的大致结构。
3. 复杂请求的动态任务 DAG 由谁生成？是 LLM 直接输出图结构，还是基于模板填充？如何校验生成图的合法性？
4. DAG 是否允许条件分支和循环？如果 LLM 生成了环，你怎么检测和处理？
5. 节点间如何传递数据？哪些数据进共享 state，哪些只通过 Handoff 传递？为什么这么设计？
6. 多个 Worker 是否能并行执行？如何声明依赖关系？用了 LangGraph 的哪些 API 实现并行？
7. 是否使用过 Send/Command 等动态并行 API？如果用过，请说明场景；如果没用，为什么？
8. Checkpoint 在 PostgreSQL 中的表结构大致如何？保存了哪些状态？
9. 用户中途刷新页面或断线后，如何从 Checkpoint 恢复？如何避免重复执行已完成节点？
10. 如果 LangGraph 版本升级导致 State 序列化不兼容，历史 checkpoint 怎么处理？
11. 如何设置节点级重试、超时、熔断？LangGraph 原生机制与自定义封装如何结合？
12. 节点执行是以异步 IO 为主，还是以推理/CPU 为主？有没有使用队列或线程池隔离？
13. 是否遇到过 graph 执行到一半卡死的情况？recursion limit 如何设置？

## 四、多 Agent 协作与上下文工程

1. Supervisor 是纯 LLM 决策，还是规则 + LLM？请描述一次 Supervisor 调度决策的完整输入输出。
2. 为什么 Worker 分成 Business Data、Knowledge、Web Research 三类？为什么不按业务域或数据源拆成更多 Worker？
3. Worker 之间是否可以直接通信，还是必须经过 Supervisor？为什么选择这种拓扑？
4. 结构化 Handoff 包含哪些字段？请给出一个真实例子。
5. Evidence ID 是如何生成的？基于内容哈希、URI 还是自增 ID？如何保证在后续引用中可追溯？
6. Observation 返回哪些状态？如果 Worker 部分成功，比如 Web 搜索部分返回 403，Observation 如何表达？
7. 如果两个 Worker 返回冲突事实，Supervisor 或最终合成阶段如何裁决？
8. 近期消息窗口设成多大？滚动摘要由哪个模型在什么时机生成？摘要是否会导致证据细节丢失？
9. 上下文压缩后，证据引用如何保持指向原始 Evidence ID？是否出现过摘要与引用不一致的情况？
10. 你有没有做过上下文压缩对最终答案质量影响的消融实验？损失了多少？
11. 如果研究任务很长，滚动摘要逐渐偏离原始问题，你如何避免？
12. 多 Agent 系统是否会出现“对话循环”或重复调用同一个工具？如何检测和终止？
13. 有没有考虑过用共享记忆或黑板模式，而不是只靠 Handoff 传递上下文？

## 五、Tool、Skill 与 Agent Harness

1. 7 个只读 Tool 具体是哪些？请按数据源和能力列出。
2. 为什么全部设计成只读？如果用户要求生成选品报告或执行写操作，系统如何处理？
3. Tool 的 JSON Schema 如何设计？如何处理枚举、可选参数、日期范围？举一个例子。
4. LLM 调用 Tool 时出现参数错误、缺失或幻觉参数，你的 Harness 如何返回错误并让模型纠正？
5. Capability Resolver 具体怎么工作？它根据什么决定某个 Agent 或用户能不能调用某个 Tool？
6. 预算、超时、幂等、审计分别在哪一层实现？请给出每个的具体技术做法。
7. 预算是按 token、调用次数、金额还是时间？超预算后是降级、终止还是转人工？
8. 只读 Tool 为什么需要幂等？你是如何实现幂等的？
9. 审计日志记录到什么粒度？是否包含输入参数、返回摘要、原始响应？日志保留多久？
10. 跨境研究 Skill 具体是什么？是 prompt、SOP、工具序列还是可复用子图？举一个具体 Skill 的例子。
11. Skill 如何做版本管理和回归测试？Skill 更新后如何保证不破坏已有任务？
12. Harness 与 LangGraph 自带的 ToolNode 边界在哪里？为什么自己封装一层？

## 六、RAG 与检索优化

1. “严格事实恢复率”的准确定义是什么？它评价的是解析、检索，还是最终生成？
2. 18 份欧盟官方文档规模多大？文档类型是 PDF、HTML、扫描件？语言分布如何？
3. Native/Docling/Hybrid 路由具体如何实现？谁来判断文档类型？判断错了怎么办？
4. OCR 质量门禁具体有哪些指标？例如字符置信度、版面识别准确率？低于阈值会怎样？
5. 从 64.7% 到 100%，主要靠解析路由、OCR 门禁还是检索？能否分解各环节贡献？
6. 100% 的严格事实恢复率是否可能过拟合到 18 份文档？在更大或未见文档上有没有验证？
7. BGE-M3 的混合召回具体指什么？你使用了它的 dense、sparse 还是多向量能力？
8. BM25 和向量召回分别召回多少候选？RRF 融合的 k 值是多少？为什么这么设？
9. BGE-Reranker 是交叉编码器还是其他结构？重排 top 多少？延迟增加多少？
10. Recall@8 从 86.7% 到 95.6%、MRR@8 从 0.712 到 0.846，哪些改动贡献最大？有没有逐项消融？
11. 引用正确率 96.3% 如何评估？是人工标注还是用 LLM 判断？引用粒度到 document、section 还是 passage？
12. 无证据拒答 F1 0.91 是如何调出来的？拒答阈值变化时，引用正确率和用户体验如何 trade-off？
13. 90 条 Golden 事实的来源和标注过程？标注者之间一致性如何？
14. 检索失败的主要原因是什么？多语言、同义词、表格、产品型号？
15. 对外部网页检索结果如何做去重、清洗、内容质量过滤？Tavily 是否足够？
16. pgvector 使用什么索引？数据量多大？向量维度多少？查询性能如何？
17. 内部库存等结构化数据为什么也走向量检索，而不是直接用 SQL？如何保证精确数字不因 embedding 失真？

## 七、模型、性能与成本

1. 使用的 Qwen 具体是哪个版本、参数量、部署方式？为什么选择 Qwen，而不是 GPT-4o 或 Claude？
2. LLM 是否自部署？推理延迟和吞吐如何？是否量化？并发多少？
3. BGE-M3 和 BGE-Reranker 部署在哪里？CPU/GPU？批处理？对整体延迟影响多大？
4. 单次复杂请求的总 token 消耗大概多少？成本多少？简单请求呢？
5. 有没有做 LLM 输出缓存、语义缓存或 prompt caching？命中率如何？
6. FastAPI 服务如何与 LangGraph 配合？流式输出是 SSE 还是 WebSocket？用户能否看到中间 Agent 步骤？
7. Next.js 前端如何展示研究过程和引用？DAG 可视化了吗？用户体验上遇到过什么问题？
8. Docker 容器如何拆分？多少个服务？镜像大小和启动时间？环境变量和密钥怎么管理？
9. PostgreSQL 同时承担业务数据、Checkpoint、pgvector，是否有性能冲突？连接池怎么配置？
10. 可观测性用了什么？是否接入 LangSmith/Langfuse/Prometheus/Grafana？你主要看哪些指标？
11. 如何做压力测试？系统最大支持多少并发？瓶颈在哪里？

## 八、安全、合规与稳定性

1. 欧洲站涉及 GDPR，系统处理哪些个人数据？数据存储位置和保留策略是什么？
2. 外部网页抓取是否遵守 robots.txt 和服务条款？如何避免抓取到侵权或违法内容？
3. 系统如何防止数据越权？不同用户角色看到的数据范围是否一致？
4. Prompt injection 除了影响路由，还可能诱导系统调用工具或泄露内部文档，你有哪些防护？
5. 如果内部库存数据敏感，但 LLM 需要读取，如何脱敏或最小化暴露？
6. 系统是否有内容安全审核？生成内容如果违反亚马逊政策或当地法律，如何兜底？
7. 审计日志是否能满足合规回溯？例如用户问了一个违规查询，能否追踪完整链路？
8. 如果某个 Worker 持续失败或 Web 搜索超时，系统如何降级？是否有优雅降级策略？
9. 如何做灰度发布和回滚？Checkpoint 兼容性对回滚有何影响？

## 九、评测与迭代

1. 离线评测集和指标是否足以支持上线决策？有没有线上评估或影子测试？
2. 冻结测试集如何防止污染？训练数据、prompt 模板、few-shot 示例会不会隐式泄漏评测集？
3. 你有没有做过人类偏好评估？用户是否更喜欢 Multi-Agent 结果，而不是更快但更简单的结果？
4. 路由、RAG、Multi-Agent 各部分指标提升，对最终业务指标（如选品准确率、运营效率）是否有影响？
5. 如何收集线上 bad case？有没有反馈闭环机制来更新测试集和 prompt？
6. 平均模型调用次数降低，是否导致答案质量下降？你们怎么衡量这种 trade-off？
7. 如果新同事接手，评测流程能否一键运行？数据版本和模型版本如何管理？
8. 项目的代码质量、文档、CI/CD 流程如何？有没有单元测试、集成测试？

## 十、个人贡献、挑战与反思

1. 这个项目你具体负责哪些模块？哪些是独立完成，哪些是协作？
2. 项目周期只有 2 个月，如何排期？最大的时间瓶颈是什么？
3. 如果让你重新设计，哪些技术选型会改变？为什么？
4. 你如何说服团队采用 LangGraph 和 Multi-Agent，而不是更简单的 Pipeline？
5. 你认为这个系统最大的技术风险是什么？你如何控制？
6. 有没有发生线上事故或严重 bug？你是如何定位和修复的？
7. 如果系统需要从欧洲站扩展到北美站或日本站，哪些部分需要改造？哪些可以复用？
8. 你在这个项目中最自豪的技术决策是什么？最失败的一个决策是什么？
9. 如果用户要求将只读 Tool 扩展为可写操作（如自动生成采购建议并提交），你会如何设计审批和风控？
10. 你觉得当前系统距离生产级还缺什么？
11. 为什么选择 BGE-M3 而不是其他 embedding 模型？它在多语言、长文档、混合召回上的实际表现如何？
12. 如果让你把路由的 Macro-F1 从 92% 再提升到 95% 以上，你会优先做什么？

---

# 面试回答

> 回答口径：以下使用第一人称面试表达。题目中的 Macro-F1 92%、p95 9.8s 降至 4.1s、平均模型调用次数 6.2 降至 2.4 等数据，按本轮面试演练要求暂视为真实测试结果；正式写入简历前仍应补齐可复现的原始样本、运行配置和评估报告。对于仓库当前尚未实现的能力，回答中继续明确说明实际边界。

## 第一批：项目背景与路由设计（1～20）

### 1. 这个系统解决什么问题？

我用一句话概括：Deep Search Pro 是一个面向小型跨境电商团队的证据驱动 AI 工作台，帮助负责人、选品人员和 Amazon 运营把企业数据库、内部文档和公开资料组合起来，完成库存查询、知识问答和复杂市场研究。

典型场景包括：运营查询德国仓库存；选品人员从质检 SOP、供应商报价中核对产品信息；负责人综合内部数据和公开资料评估一个商品是否适合德国、法国市场。

它与普通聊天机器人的区别是，模型不直接编造业务事实，而是通过受控 Tool 获取数据，并把回答映射到可重新核验的 Evidence。

### 2. 举三个分别走 Fast Path、Pipeline、Multi-Agent 的 Query

第一个是 Fast Path：

> “SKU LR-TL-MUSH-OR01 在德国仓还有多少可售库存？”

这是意图、SKU和市场都很明确的单一查询。路由器直接进入库存 Tool，Service 按 on_hand - reserved - unsellable 计算可售库存，再用确定性模板返回，不需要 Supervisor 动态规划。

第二个是固定 Pipeline：

> “查一下蘑菇灯德国仓库存，再对照内部补货规则判断是否需要补货。”

它有两个固定步骤：查询结构化库存、检索内部补货规则。步骤可预先编排，必要时并行执行，然后根据固定规则汇总，不需要让 LLM 动态生成任务图。

第三个是 Multi-Agent：

> “结合当前库存、内部合规资料和德国、法国公开市场信息，评估蘑菇灯进入两个市场的可行性并形成报告。”

它需要拆分问题、查询不同数据源、处理依赖和冲突，再综合生成报告，因此由 Supervisor 调度 Business、Knowledge 和 Web Research Worker。

不过我需要诚实说明：前两类所依赖的 Business/Knowledge 能力已经具备；Web Research Worker 和完整跨境研究属于 M4，当前仓库仍处于已确认方案、尚未实现的状态。

### 3. 系统中的“深度研究”如何定义？

根据我的设计，深度研究不是“回答得比较长”，而是同时具备以下特征：

- 需要两个以上异构数据源；
- 可以拆成多个有依赖关系的子问题；
- 需要比较、交叉验证或处理证据冲突；
- 运行时间可能跨越一次普通 HTTP 请求；
- 最终要输出带引用、限制条件和未知项的研究结果。

普通问答主要依靠模型已有知识；报表查询通常是一次确定性 SQL；数据检索只返回候选材料；深度研究则是“规划—取证—校验—综合—形成报告”的完整过程。

我还特意强调“有界”：当前 Runtime 已限制任务数、委派深度、模型调用、Tool 调用、Evidence 数量和总超时，避免所谓自主研究变成无限搜索或无限循环。M4 完成前，我不会在简历中声称完整深度研究已经落地。

### 4. 是否处理多个欧洲站点之间的差异？

当前真正实现和验证的业务市场是 DE 和 FR，不包括 IT、ES、NL。权限上下文中有明确的 market_scopes，例如德国运营只有 DE，查询法国数据会在 Tool 执行前被拒绝。

语言方面，商品支持中文和英文名称、别名；RAG 评估覆盖中文、英文和德文问法，BGE-M3 也做过跨语言检索 Smoke。但这不能等同于已经完成全站点本地化。

货币方面，目前演示数据主要使用 EUR，但还没有独立的汇率、金额精度和汇率日期服务。税率与产品合规目前作为文档事实检索，不由模型直接计算或给出法律结论。

因此更准确的说法是：系统架构已经保留市场、语言和权限边界，但尚未实现完整的五国税务、本地化和合规规则引擎。

### 5. 三类数据源分别是什么？规模和权限如何？

企业结构化数据目前是明确标注的合成数据，包括一个演示租户、四个角色化用户、一个商品变体、德国和法国两个仓库的库存快照。库存是版本化快照，目前没有接 SP-API，也没有自动同步任务。

内部文档基线包含10个文件、10个Document和10个Version，覆盖PDF、DOCX、XLSX和CSV，并配置了9条ACL。文档通过手工上传更新；新版本只有在解析、分块和索引全部完成后，才原子切换为 active，避免用户搜到半成品索引。

评估阶段还使用了10份合成文档和8份欧盟官方PDF，共18份文档、34条可回答Golden事实。这批评估数据运行后会清理，不直接混入正式Seed。

公开数据目前只有受控下载的8份欧盟官方PDF作为评估语料；实时网页搜索、正文读取和更新频率将在M4由Tavily Provider实现，目前不能说已经上线。

权限方面，结构化数据按 tenant、role、market 过滤；文档还增加Document ACL、软删除和active版本过滤。

### 6. 最终回答中如何区分企业数据和公开数据？

我没有只在答案文字中写一句“来源于某文档”，而是建立了结构化Evidence合同。

当前Evidence的 source_type 包括：

- database：企业数据库；
- knowledge：内部知识库；
- user_file：用户上传文件。

每条Evidence保存UUID、标题、摘要、观察时间、可信等级、来源定位和内容Hash。数据库Evidence可以定位到库存快照；文档Evidence可以定位到页码、标题、表格、Sheet或行范围。

最终答案中的 [E1]、[E2] 与真实Evidence UUID一一映射，而且只能引用当前Worker Observation中出现、当前用户仍有权限读取的Evidence。

M4完成后会增加Web Evidence，并显示规范URL、发布时间、抓取时间和正文片段。内部事实与公开网页不会混成一个没有来源差异的“统一事实”。如果两类证据冲突，我会保留双方来源、时间和口径，而不是让模型自行选一个看起来合理的答案。

### 7. 系统有没有真实用户？如何验证业务价值？

目前没有真实生产用户，所以我不会说系统已经创造了真实商业收益。

当前能证明的是工程可行性：库存主链经过真实前端、FastAPI、PostgreSQL和权限控制；RAG使用版本化语料、Golden事实和分层指标；异常、越权、零库存、无记录和数据库停机都有自动化测试。

业务价值目前主要通过场景验收验证，例如：

- 查询库存是否比人工翻表更直接；
- 回答能否定位到库存快照或文档原文；
- 无证据时是否拒答；
- 复杂任务是否能减少跨系统手工整理。

通常做法是下一步找5～10名跨境运营或选品人员做任务对照测试，记录任务完成时间、事实错误率、引用核验时间和主观可用性。没有这一步之前，我只把它描述为“可运行作品和工程验证”，不描述成生产成功案例。

### 8. 哪类错误最不可接受？如何规避？

我认为最不可接受的不是回答稍微慢，而是三类错误：越权泄露、精确业务数字错误、合规结论被模型编造。

库存数字错误可能直接影响补货。我的做法是让库存由Repository查询最新快照，Service确定性计算，回答模板直接读取结构化结果，不让LLM再次改写数字。例如德国仓的可售库存是 150 - 20 - 5 = 125。

合规问题的风险更高，所以系统必须引用具体法规或内部清单，并区分事实、推断和未知。证据不足时拒答，演示材料也明确注明不构成法律或认证意见。

越权则采用零容忍策略：身份来自服务端的CurrentUser和RunContext，模型不能通过Tool参数传入tenant、角色或权限；Capability Resolver和Permission Guard在Tool执行前再次拦截。

### 9. Fast Path、Pipeline、Multi-Agent 的定义和边界是什么？

Fast Path处理高置信、单意图、单一数据源、无开放规划需求的请求，例如明确SKU和市场的库存查询。它直接进入一个Tool或一次模型回答。

Pipeline处理步骤固定、依赖关系已知的复合任务。例如“查库存，再检索补货规则，再按固定公式判断”。步骤可以预编排，模型只负责必要的参数理解或有证据总结。

Multi-Agent处理开放问题：子任务数量和依赖需要动态确定，涉及多个Worker，可能出现部分失败、冲突证据和中断恢复。

具体判定时我关注四个维度：意图置信度、所需数据源数量、步骤是否固定、是否需要开放式综合。不是问题越长就越复杂，也不是出现“分析”两个字就进入Multi-Agent。

### 10. 路由如何实现？为什么不只用关键词？

我采用的是规则与LLM结合的混合方案。

程序规则优先处理高置信请求，例如合法SKU、明确市场和唯一业务动作都存在时，可以直接识别为库存Fast Path。这样不需要额外调用一次LLM。

规则无法确定时，我让模型进行一次严格结构化输出，同时返回意图、复杂度、执行路径和业务参数，避免先分类一次、再提取参数一次。输出还会经过Pydantic Schema和服务端能力目录校验。

我不只用关键词，是因为“帮我分析一下德国仓库存”虽然含“分析”，仍可能只是单一库存查询；相反，“查库存并结合合规资料给出上市建议”即使没有“深度研究”这个词，也明显是复合任务。关键词只能作为高精度特征，不能作为最终安全边界。

### 11. 120条冻结路由测试集如何构建？

这120条我按Fast Path、Pipeline、Multi-Agent三个主标签做了相对均衡的分层，避免简单请求占多数时用Accuracy掩盖复杂任务识别失败。

样本来源包括真实业务表达改写、项目Golden场景和人工构造的边界案例。除了清晰样本，还加入了：

- 缺少SKU或市场，需要澄清的请求；
- 表面很长但实际只有一个动作的请求；
- 表面很短但需要跨数据源研究的请求；
- 中英文混合、同义词和口语表达；
- 试图诱导调用未授权Tool的Prompt Injection；
- 当前系统不支持的业务。

这些交叉标签可能重叠，不作为简单相加的类别数量。

冻结意味着路由规则、Prompt和few-shot不能再根据这120条Test结果修改。开发和调参使用另一组Debug/Validation样本，Test只在候选方案冻结后运行，避免把测试集做成训练集。

### 12. Macro-F1 92% 如何计算？还看了哪些指标？

我先分别计算每条路径的Precision和Recall：

Precision = TP / (TP + FP)

Recall = TP / (TP + FN)

F1 = 2 × Precision × Recall / (Precision + Recall)

Macro-F1 = 三个路由类别F1的算术平均

Macro-F1为92%，意味着三个类别权重相同，不会因为Fast Path样本较多就掩盖Multi-Agent识别差的问题。

我还会同时看混淆矩阵、总体Accuracy、每类Recall、升级率、错误路由成本、最终任务完成率、模型调用次数和p95延迟。

其中我最关注Multi-Agent被误判成Fast Path的数量，因为即使总体准确率很高，这类错误仍可能导致证据不足或错误结论。Macro-F1只能评价分类表现，不能替代端到端任务质量。

### 13. 路由错误成本是否不对称？

是的，明显不对称。

复杂请求误入Fast Path通常更危险，因为系统可能只查一个数据源就给出完整结论，形成“答案看起来合理但证据不完整”的静默错误。

简单请求误入Multi-Agent主要造成成本和体验问题：模型调用更多、延迟更高、故障面更大，但通常不会直接丢失必要证据。

因此我的策略不是一味追求最高分类准确率，而是采用成本敏感的决策：对于可能缺失关键证据的复杂请求宁可升级；但“模型不确定”也不等于直接启动Multi-Agent，如果缺少SKU、市场或目标，我会优先澄清。

### 14. 线上流量与冻结测试集是否一致？有没有数据漂移？

当前没有真实生产流量，所以不能声称已经验证线上分布一致，也不能说观测到了真实数据漂移。

目前可以做的是基于演示请求和回归集比较不同语言、角色、市场和任务复杂度的结果。它能验证代码回归，不能证明真实用户会以相同比例提问。

根据我的上线设计，我会记录脱敏后的路由标签、置信度、实际执行路径、人工反馈和最终任务状态，按周比较类别分布、低置信请求比例、未知意图比例和各类错误率。

如果某类未知请求持续增长，我会先进入Bad Case池和人工标注流程，而不是直接拿线上数据自动改Prompt。

### 15. 是否支持“不确定时升级到Multi-Agent”？

支持升级，但不是“不确定就一律Multi-Agent”。

第一层是高置信程序规则；第二层是不确定时调用一次结构化路由模型；第三层仍然缺少关键业务参数时，进入澄清而不是盲目执行。

根据我的设计，阈值由Validation集上的质量、延迟和错误成本共同校准。我不仅看最大类别概率，还看第一、第二候选的置信度间隔，以及是否存在多个数据源、开放式比较和报告要求。

为了防止频繁升级，我还限制单次请求的升级次数、最大任务数、委派次数和总预算。已经执行过的Tool签名也会记录，避免升级后重复查询同一数据。

### 16. 如何应对Prompt Injection欺骗路由或调用内部工具？

我的核心原则是：路由结果不是授权结果，Prompt也不是安全边界。

即使攻击文本把请求误导成Multi-Agent，模型最终能看到的能力仍然来自服务端计算出的交集：

Worker允许能力 ∩ Tool允许角色 ∩ 当前用户身份与市场范围 ∩ 系统安全策略

Capability Resolver只投影当前Worker可以使用的Tool；JSON Schema设置 additionalProperties=false，并禁止模型提交tenant、role、SQL、storage key、路径和密钥等服务端字段。

Tool执行前，Harness还会验证白名单、参数、tenant、market、预算和重复调用。文档或网页中的指令只被当作不可信数据，不能修改RunContext。

因此Injection最多影响一次模型建议，不能直接获得数据库、任意HTTP或跨租户能力。

### 17. 新增“广告投放研究”后，路由体系如何扩展？

我不会只在关键词表里加一个“广告”字符串，而是先定义新能力的输入、输出和安全边界。

如果只是查询某个广告指标，它可能仍是Fast Path；如果是固定的“广告数据加销量数据”分析，可以走Pipeline；只有需要动态拆解竞品、关键词、预算和市场资料时，才进入Multi-Agent。

工程上需要增加广告意图Schema、Capability定义、必要的只读Tool或Service，并把它分配给合适的Worker。只有当广告任务拥有独立目标、权限和完成判断时，我才考虑新增Advertising Worker，否则继续复用Business Data Worker，避免Agent数量膨胀。

最后要扩充Debug、Validation和冻结Test集，重点观察新意图是否把原来的库存或市场研究请求错误吸走。

### 18. p95从9.8秒降到4.1秒后，剩余时间花在哪里？

这次下降的主要原因是让明确的简单请求绕过Supervisor，并把原来分开的意图判断和参数提取合并，平均模型调用也从6.2次降到2.4次。

根据链路拆分，剩余延迟主要来自模型网络首Token和答案生成；知识问答还包含Embedding、Dense/Lexical检索、Reranker和上下文构造。PostgreSQL的精确库存查询通常不是主要瓶颈。

需要注意，p95不能简单把各阶段p95相加。我会按同一个trace记录路由、Provider、Tool、SQL、Embedding、Reranker、持久化和生成耗时，再按Fast Path、Pipeline、Multi-Agent分别统计。

进一步优化方向包括：明确库存请求做到零路由模型调用；缩短结构化Prompt；控制输出长度；对独立Tool并行执行；批量执行Reranker；减少无意义的Checkpoint和上下文序列化。

### 19. 平均模型调用次数6.2降到2.4，统计口径是什么？

我的统计单位是一次公开用户请求。分母包含同一冻结集中的成功、拒答和安全失败请求，而不是只统计最顺利的成功样本。

计入LLM调用的包括：不确定请求的路由、Planner、Handoff、Worker决策、最终答案和模型生成的摘要；发生重试时也计入，因为重试同样消耗Token和时间。缓存命中不算真实Provider调用，但会单独记录。

Embedding和BGE-Reranker属于模型推理，但不混进“LLM调用次数”，否则指标难以解释。我会另外记录 embedding_inference_count、reranker_inference_count 和对应延迟。

6.2降到2.4主要来自三个变化：简单请求绕过Supervisor、路由与参数提取合并、结构化业务结果优先使用确定性格式化。

### 20. 简单请求p95 4.1秒是否可以接受？

不能统一判断，要按请求类型设SLO。

对于精确库存查询，用户预期接近数据库查询体验，4.1秒仍偏慢。我希望这类请求最终做到不调用LLM，由程序识别明确SKU和市场，直接查询Tool并格式化，目标可以压到p95约1～1.5秒以内。

对于需要BGE检索、Reranker和Qwen生成的知识问答，4.1秒通常可以接受，但应尽快展示“正在检索”和首个Token，而不是让页面完全静止。

对于Multi-Agent长任务，关注点不是4.1秒内完成，而是1秒左右返回task ID和可见进度，后台有界执行，并允许刷新页面后从Checkpoint恢复。

所以我不会用一个总p95代表全部体验，而会分别报告Fast Path完整响应、RAG首Token、Pipeline完成时间和深度任务首次状态反馈。

## 第二批：LangGraph 编排与多 Agent 协作（21～40）

### 21. 为什么选择 LangGraph，而不是 FastAPI + 自研状态机、Temporal、Airflow 或 CrewAI？

我选择LangGraph的核心原因，是它允许我把Agent运行显式建模为“有状态节点加条件边”，同时保留Python代码对权限、预算、Tool和持久化的控制权。当前Supervisor图只有plan、decide、prepare_handoff、invoke_worker和compose_answer五个节点，运行过程不是藏在一段Prompt里，而是可以分别测试每个状态转换。

如果只用FastAPI加自研状态机，我仍然要自己实现条件分支、循环终止、状态合并和恢复，容易逐渐形成一个缺少统一约束的框架。Temporal更适合跨服务、分钟到天级、需要强持久化语义的生产工作流，但对当前本地作品来说基础设施和学习成本偏高。Airflow偏离线批处理，不适合交互式澄清和Agent状态。CrewAI封装更高，但我需要严格控制Worker能力、Handoff字段和Evidence来源，因此没有选择更黑盒的抽象。

我也没有把所有问题都强行放进LangGraph。明确的库存Fast Path和步骤固定的Pipeline应该绕过动态Supervisor；只有确实需要状态、分支、协作或恢复的任务才进入Graph。

### 22. LangGraph State 包含哪些字段？

我的持久化状态叫EngineeredAgentState，大致分为六组：

- 身份与目标引用：run_id、goal、public_context；
- 对话恢复：memory、processed_request_ids、active_request_id、resume_count、replan_count；
- 计划与当前位置：plan、current_task_id、pending_action；
- 执行产物：observations、worker_results、evidence_ids、artifact_ids、unknowns；
- 终态：execution_status、business_outcome、public_summary、stop_reason；
- 资源：model_calls、tool_calls、input_tokens、output_tokens和duration_ms。

其中不会保存数据库Session、Tool实例、密钥、SQL、Storage Key或完整Chain of Thought。公共JSON还限制深度、键数量、字符串长度和总字节数，并禁止tenant、role、budget等服务端字段。

图内还有current_task_ids、pending_actions、handoff_drafts和node_history等临时调度字段；它们用于一次内存执行，不全部进入Checkpoint。这样持久化合同不会和某次LangGraph内部实现过度绑定。

### 23. 动态任务 DAG 由谁生成？如何校验合法性？

当前DAG由Qwen Planner通过严格结构化输出生成，不是任意文本，也不是让模型直接操作LangGraph对象。输出必须反序列化为TaskPlan，每个任务包含task_id、goal、depends_on、required_capabilities、assignment、完成条件、Evidence要求和失败影响。

服务端会再次校验：任务ID唯一、依赖存在、不能自依赖、整张图不能成环；新计划的任务必须处于waiting；分配的Worker必须真实可用；required_capabilities必须是该Worker经Capability Resolver批准的能力子集。

Schema理论上最多容纳24个任务，但当前公开Agent Gateway的根预算最多允许8个任务，所以模型即使生成更大的合法Schema，也过不了实际运行预算。

对于常见固定任务，我更倾向模板Pipeline；动态DAG只用于步骤无法在开发时完全预定义的复杂请求。这是为了减少模型过度规划和不必要的调用。

### 24. DAG 是否允许条件分支和循环？如果生成环怎么办？

控制图允许条件分支，例如计划后可以直接回答、继续决策或终止；Worker完成后可以继续下一个任务、形成部分回答或安全失败。

任务DAG本身不允许环。TaskPlan的Pydantic校验器会对依赖关系做深度优先遍历，用visiting和visited集合检测回边；发现循环后整个计划被判为invalid_plan，尚未执行任何Worker或Tool。

LangGraph控制流内部确实有decide到handoff、worker再回decide的循环，但它是程序定义的受控循环，不是LLM生成的任意环。它受到Supervisor最多16次决策、相同行动最多1次、根模型和Tool预算、Worker自身4或5次决策上限以及总超时共同约束。

所以我的原则是：业务任务图必须无环；需要迭代的控制循环由程序预先定义，并且必须有可验证的终止条件。

### 25. 节点间如何传递数据？共享 State 与 Handoff 如何划分？

共享State保存所有后续调度都需要的最小事实，包括任务状态、WorkerResult、公开Observation、Evidence/Artifact ID、未知项、停止原因和资源使用。它相当于Supervisor的任务板。

Handoff只承载某个Worker完成当前子任务所需的信息：task_id、子目标、target_worker、公开上下文、允许转交的Evidence/Artifact ID、约束、期望输出和完成条件。模型只能生成HandoffDraft，真正的handoff_id、父子Run关系和allocated_budget_ref由Runtime注入。

我不会把完整文档、完整Tool响应或可信身份复制到Handoff。大内容留在Storage或PostgreSQL中，通过不透明ID引用；Worker使用ID时重新授权。

这样设计可以减少上下文膨胀，也能防止一个Worker把自己没有权限看到的数据通过共享State泄露给另一个Worker。

### 26. 多个 Worker 能否并行？如何声明依赖？用了哪些 API？

可以，但当前只允许最多两个相互独立、只读且属于不同Worker的任务并行。

依赖通过AgentTask.depends_on声明。调度器只选择依赖任务全部completed的节点；如果第一个可运行任务不是只读能力，或者第二个任务属于同一个Worker，就退回顺序执行。

实现上没有直接使用LangGraph的Send API，而是在invoke_worker节点内对多个Handoff调用asyncio.gather。每个Worker都有独立子Run、预算引用、SQLAlchemy Session和事务边界，结果完成后按原TaskPlan顺序稳定合并，而不是按谁先返回谁先写入。

测试已经验证Business和Knowledge两个真实Worker发生时间重叠，同时ToolCall仍归属于正确的子Run。这个结果能证明有界并发和隔离，不能代表生产吞吐能力。

### 27. 是否使用过 Send/Command 动态并行 API？

当前没有使用Send或Command。

原因是目前只有Business和Knowledge两个可执行Worker，并发上限固定为2，任务DAG也有严格上界。在一个明确的invoke_worker节点中用asyncio.gather，更容易控制预算预留、独立Session、异常归一化、结果顺序和部分失败。

Send适合运行时产生数量不固定的map任务，例如对几十个候选来源分别抓取和分析。当前系统明确禁止无界fan-out，如果为了展示API而引入Send，反而会增加Checkpoint合并和资源控制复杂度。

M4加入Web Research后，如果出现“对有限候选来源并行读取”的真实需求，我会先冻结最大来源数和合并语义，再评估Send；不会因为框架支持就直接使用。

### 28. PostgreSQL Checkpoint 的表结构是什么？

agent_checkpoints保存的是不可变快照，核心字段包括tenant_id、root_run_id、thread_id、user_id、checkpoint_version、state_contract_version、state_json、state_sha256、execution_status、business_outcome和created_at。

同一个root_run下checkpoint_version唯一，并通过expected_version做乐观并发控制。state_json限制在262,144字节以内，写入前使用稳定排序的Canonical JSON计算SHA-256；读取时重新通过EngineeredAgentState校验并复算Hash，防止损坏或被静默修改。

任务没有只塞在一个JSON里。agent_tasks保存标准化任务节点和row_version，agent_task_dependencies保存依赖边；AgentRun保存Supervisor和Worker父子关系；agent_answer_evidences保存最终[E1]到Evidence UUID的有序映射。

这种设计比只保存一个LangGraph序列化对象更容易做租户过滤、任务冲突检测、审计和后续合同迁移。

### 29. 页面刷新或断线后如何恢复？如何避免重复执行？

当前M2已经支持两类恢复：同一request_id的幂等重放，以及waiting_user状态下用户补充信息后的跨请求恢复。

每个请求有确定性的用户消息ID和助手消息ID。相同request_id和相同内容重试时，Gateway读取对应Checkpoint并返回当时结果；相同ID换内容会返回409。恢复waiting_user任务时，服务先锁定Thread和根Run，追加新的不可变Checkpoint，再继续原DAG；最多恢复4次、最多重新规划1次。

恢复时会重建累计预算和已执行Tool签名，所以不会把模型调用和Tool调用额度重置。已完成任务保留原WorkerResult，只有未完成任务重新进入调度。恢复前和最终保存前还会重新检查Evidence、File、角色和市场权限，撤权后不能重放旧答案。

需要说明，当前公开请求仍是同步执行，Checkpoint主要覆盖请求级幂等和等待用户续跑，还不是任意节点崩溃后的后台任务自动接管。M4的长任务租约和后台恢复仍待实现。

### 30. LangGraph 升级导致 State 序列化不兼容时怎么办？

我没有直接持久化LangGraph内部对象，而是持久化项目自己的Pydantic合同，并给它明确的state_contract_version，目前是m2-agent-contract-v1。这降低了框架升级对历史数据的直接影响。

如果新代码需要v2，我不会原地猜测旧JSON含义。通常做法是保留v1读取器，编写v1到v2的纯函数迁移，使用固定Fixture验证字段默认值、Hash和业务状态，再通过离线迁移或读取时升级生成新的不可变Checkpoint。

新版本上线前要验证旧Checkpoint可以读取和恢复；回滚时也要确认旧代码不会遇到只认识v2的数据。如果不能安全转换，就把旧Run保留为只读审计记录并明确标记不可恢复，而不是忽略校验强行续跑。

当前数据库Check约束只接受v1，因此真正升级合同还需要同步Alembic迁移；这部分目前没有实现，不能说已经验证过跨大版本兼容。

### 31. 如何设置节点级重试、超时和熔断？

我把超时分层处理。Qwen Provider默认请求超时是5秒；数据库语句超时默认2秒；Worker使用asyncio.wait_for限制在自己的剩余子预算内；根Run当前总超时60秒，Business和Knowledge子预算各30秒；Tool执行还受Harness中的单Tool超时约束。

节点异常不会把堆栈或原始Provider响应返回用户，而是转换为invalid_plan、worker_failure、timed_out等安全终态。事务只在Worker completed时提交，超时和失败会回滚。

当前没有给所有LangGraph节点配置自动重试，也没有完整熔断器。因为非法Schema、越权和无证据不应该重试；只有明确标为retryable的临时网络错误、429或Provider 5xx才适合有限重试，而且必须继续扣预算并使用退避和抖动。

生产化时我会按Provider维度加入连续失败窗口、半开探测和降级策略。现在的实现是超时后安全失败或部分完成，不能把它包装成已经具备完整熔断能力。

### 32. 节点执行主要是异步 IO 还是 CPU？是否使用队列或线程池？

Agent编排和Qwen HTTPS调用以异步IO为主，Supervisor和Worker接口都是async。两个独立Worker通过asyncio.gather并发。

但RAG里有明显的CPU和内存任务：BGE-M3 Embedding、BGE-Reranker、PDF解析、OCR和Docling。特别是Docling曾出现约120秒超时和线程不能退出的问题，我最后把每份Docling任务放到Windows spawn的一次性子进程中，并限制总时间、RSS和结果大小；真实扫描PDF单次运行约77.7秒、峰值约1.83 GiB。

当前SQLAlchemy Session和部分BGE推理仍是同步调用，没有通用Celery、Redis队列或完整线程池隔离。这对本地演示规模可控，但不是高并发生产方案。

M4首版计划使用应用内有界执行器和PostgreSQL持久任务状态；只有并发和可靠性数据证明需要时，再引入独立任务队列。

### 33. 是否遇到过 Graph 卡死？recursion limit 如何设置？

我没有真实生产事故，因此不会说发生过线上Graph卡死。但在测试和开发中，我专门模拟了模型重复委派、重复Tool、连续无进展、Worker超时和没有可运行任务的情况。

Supervisor最多16次决策，相同Action超过1次就以repeated_action停止；Business Worker最多4次决策，Knowledge Worker最多5次；相同Handoff和无进展结果也有独立终止器。根预算还限制最多24次模型调用、8次Tool调用、8个任务、8次委派、深度1和60秒总时间。

当前没有显式修改LangGraph框架的recursion_limit，而是让业务护栏在到达框架默认递归保护之前终止。这比只依赖框架抛GraphRecursionError更容易给出明确、安全的停止原因。

如果未来图规模扩大，我会把recursion_limit设为根据最大任务数和每任务最大状态转换数推导出的上界，并保留业务决策上限作为第一道保护。

### 34. Supervisor 是纯 LLM 决策，还是规则与 LLM 结合？

它是LLM建议加程序约束，不是纯LLM自治。

LLM负责生成TaskPlan、为当前任务选择一次Action、准备公开HandoffDraft以及基于WorkerResult组织最终回答。程序负责决定可见Worker和Capability、验证DAG、判断哪些任务依赖已满足、限制并行数量、注入父子Run与预算、执行Tool、处理部分失败并验证最终引用。

一次调度的模型输入包括用户目标、经过限制的public_context、Resolver批准的Worker Profile、当前TaskPlan、最近最多16条公开Observation和已有WorkerResult。输出只能是一个严格AgentAction，例如delegate_task、ask_user、finish或cannot_complete。

模型不能直接执行Worker Tool，不能改写已分配的Worker，也不能生成tenant、真实budget_ref或父Run身份。这种边界让我既能利用模型理解自然语言，又不把运行控制权交给Prompt。

### 35. 为什么分成 Business Data、Knowledge、Web Research 三类 Worker？

我是按数据信任边界、工具权限和失败模式拆分，而不是为了增加Agent数量。

Business Data Worker负责商品规格和库存，只拥有get_product_spec与search_inventory两个只读Tool；Knowledge Worker负责内部文档，只拥有search_knowledge、read_uploaded_file和get_evidence_detail三个Tool；Web Research Worker计划只拥有search_public_web和read_public_source两个公开网络Tool。

结构化数据库要求精确数字和市场权限；内部文档要求ACL、版本和引用；公开网页则涉及来源可信度、Prompt Injection、robots、限流和内容清洗。三者的风险不同，因此适合分开。

当前真正实现的是前两个Worker，Web Research属于M4待实现。首版不会再拆Analysis或Report Worker，因为固定计算和Markdown格式化更适合Service；只有出现独立目标、独立权限和独立完成判断时才增加Worker。

### 36. Worker 能直接通信吗？为什么选择这种拓扑？

当前Worker不能直接互相调用，也不能继续委派，AgentDefinition中的can_delegate固定为False。所有协作都经过Supervisor、共享任务板和结构化Handoff。

例如Knowledge任务需要Business结果时，Supervisor先完成Business任务，再把允许转交的Evidence ID或公开业务摘要写入Knowledge Handoff。Knowledge Worker不能拿到另一个Worker的Session、完整内部状态或Tool集合。

我选择这种星型拓扑，是因为权限和审计边界更清晰：每次交接都有task_id、target_worker、父子Run、预算和Evidence集合；出现问题时可以定位是哪次委派改变了状态。

代价是Supervisor会增加调用和延迟。对于步骤固定的任务，我会使用Pipeline绕过多次Handoff；只有需要动态协作时才使用这种拓扑。

### 37. 结构化 Handoff 包含哪些字段？举一个例子

最终AgentHandoff包含handoff_id、task_id、goal、target_worker、public_context、evidence_ids、artifact_ids、constraints、expected_output、completion_criteria和allocated_budget_ref。

例如库存任务可以表示为：

- task_id：check_de_inventory；
- goal：查询蘑菇灯SKU在DE市场的最新可售库存；
- target_worker：business_data；
- public_context：只包含sku和market_code等公开业务参数；
- constraints：只读、不得替换SKU、只允许DE市场；
- expected_output：库存数量、仓库、快照时间和Evidence；
- completion_criteria：成功返回获权库存Evidence，或明确返回无记录、拒绝或超时。

Planner不能生成可信身份和真实预算。Runtime会生成handoff_id和allocated_budget_ref，并把服务端CurrentUser转换成RunContext后再执行。

### 38. Evidence ID 如何生成？怎样保证可追溯？

Evidence ID使用服务端生成的UUID，不是数据库自增，也不是直接把URI当主键。数据库库存Evidence在持久化时生成UUID；文档Context中的Evidence ID由Context构建过程生成并与Chunk及引用顺序绑定。

我没有直接使用内容Hash作为Evidence ID，因为同一内容可能在不同Run、权限范围或观察时间下形成不同证据实例。但Evidence会额外保存source_content_sha256和context_text_sha256，用来证明引用的原始Chunk和进入上下文的文本没有变化。

追溯链是：最终[E1]标签映射到Evidence UUID，Evidence关联Context、DocumentVersion、Chunk Set、Index Set和Chunk；数据库Evidence则关联ToolCall、AgentRun和库存快照定位。

读取Evidence时还要按当前tenant、market或文档ACL重新授权。因此UUID负责实例身份，Hash负责内容完整性，外键和Trace负责调用链追溯，三者职责不同。

### 39. Observation 有哪些状态？部分成功如何表达？

WorkerObservation有success、partial、error、rejected和timeout五种状态。每条Observation还可以包含公开摘要、结构化结果、Evidence/Artifact ID、未知项、安全错误和资源消耗。

失败Observation必须带SafeAgentError，而且不能同时携带结构化结果或Evidence，避免事务已经回滚却继续引用无效数据。success则不能带错误。

WorkerResult把运行状态和业务结果分开：运行可以completed或failed，业务结果可以answered、partial、no_evidence、denied、timed_out等。Task还声明failure_impact是blocks_dependents、allows_partial还是non_blocking。

根据设计，如果Web搜索部分来源返回403，单个来源应记录为受控失败或未知项；只要已有其他合法Evidence且任务允许部分完成，最终可以completed加partial，并明确列出缺失来源。当前Web Worker尚未实现，但Business与Knowledge的部分成功合同和测试已经存在。

### 40. 两个 Worker 返回冲突事实时如何裁决？

我不会让Supervisor通过“多数投票”或平均值自动消除冲突，因为两个转载网页不一定比一条内部最新快照更可信。

首先按事实类型确定权威来源。当前库存以带snapshot_at的企业数据库为准，公开网页不能覆盖内部库存；内部SOP以active DocumentVersion为准；法规类结论优先使用适用地区和时间明确的官方原文。

其次比较实体、市场、币种、时间和统计口径。很多所谓冲突其实是德国与法国、含税与未税、当前库存与历史快照口径不同。能够解释时，最终答案分别注明条件并引用双方Evidence。

如果仍无法消除，我会输出“存在冲突、当前无法确认”，保留两条Evidence和未知项，而不是让模型猜一个答案。当前Citation Validator能保证引用身份真实，但还没有独立的自动冲突裁决Service；Web来源权威性和时间冲突处理属于M4需要实现和评估的能力。

## 第三批：上下文、Tool、Skill、Harness 与 RAG 评估基础（41～60）

### 41. 近期消息窗口多大？滚动摘要由哪个模型生成？

当前窗口最多保留8条近期消息。每条消息进入Agent记忆前先压缩到最多1000字符，并清理密钥、Token、本地路径、SQL关键字和Traceback等不应进入模型上下文的内容。

更早的消息最多读取16条作为摘要来源，每条截取240字符，用“用户：……｜助手：……”的固定格式拼接，摘要总长度最多2000字符。因此当前滚动摘要不是由Qwen生成，而是确定性程序摘要，不增加模型调用，也不会因为采样温度产生不同结果。

它的优点是便宜、可复现、安全；缺点是只能压缩文本，不能真正判断哪些历史信息最重要。M4长研究任务不能只依赖这种聊天摘要，关键目标、任务状态、Evidence和限制条件必须继续保存在结构化State和Checkpoint中。

### 42. 上下文压缩后，Evidence 引用如何保持？是否出现过摘要与引用不一致？

Evidence引用不依赖摘要文本维持。最终答案的[E1]到[E12]映射单独保存在agent_answer_evidences中，真实UUID也保留在Observation、WorkerResult和Checkpoint的evidence_ids字段里。

恢复任务时，系统会从结构化状态取出Evidence ID，并按当前用户、tenant、market、ACL、软删除和active版本重新授权。摘要中即使出现“之前查到库存125”，也不能凭这句话恢复Evidence；必须由结构化引用集合证明。

目前自动化测试覆盖伪造、重复、越权、撤权后重放和编号不连续等问题，没有发现已验证链路中的摘要与引用错绑。但这只能证明身份映射一致，不能自动证明自然语言中的每个事实都被引用内容充分支持，后者还需要Citation precision和Faithfulness评估。

### 43. 是否做过上下文压缩的消融实验？质量损失多少？

目前没有完成正式的上下文压缩消融实验，所以我不会给出一个虚构的质量损失百分比。

现有测试主要验证边界：8条近期消息、2000字符摘要、敏感信息清理、请求幂等、澄清恢复和Evidence重新获权。它能证明压缩后系统仍可安全恢复代表性任务，但不能证明与“保留完整历史”相比答案质量没有下降。

根据我的评估设计，后续应在同一批多轮任务上比较完整历史、8条加确定性摘要、只保留结构化状态三组配置，观察任务完成率、参数延续准确率、Evidence引用准确率、Token、延迟和摘要漂移Bad Case。只有完成这组实验后，我才会在简历中填写具体损失值。

### 44. 长任务中如何避免滚动摘要偏离原始问题？

我的原则是，摘要只帮助模型理解对话，不充当任务事实的唯一来源。

原始goal、TaskPlan、completion_criteria、constraints、Evidence ID、unknowns和资源预算都保存在结构化Checkpoint中。用户补充信息后，系统恢复同一个root_run，并核对goal和plan，而不是让模型根据一段滚动摘要重新猜任务。

当前还限制最多恢复4次、最多重新规划1次；已完成任务不会因为摘要变化重新执行。对于M4长研究，计划增加任务租约和阶段Checkpoint，并保留用户确认过的研究范围快照。

如果新消息与原始目标冲突，我会把它当成范围变更或新任务，要求明确确认，而不是静默修改旧目标。这部分完整长任务能力仍属于M4，当前M2只验证了等待用户后的有界恢复。

### 45. 多 Agent 如何检测和终止对话循环或重复 Tool？

我用了多层终止机制，而不是只依赖一个recursion limit。

Supervisor最多16次决策，相同Action连续出现超过1次就以repeated_action停止。Business Worker最多4次决策，Knowledge Worker最多5次。WorkerRuntime对结构相同的Handoff计算SHA-256签名，默认同一Handoff只允许一次；连续无进展结果也会触发no_progress。

Tool层按tool_name加规范化参数生成签名，子预算默认不允许重复执行同一签名。恢复Checkpoint时，历史ToolCall的名称和arguments_summary会重新装载到预算树，不能通过刷新页面把重复计数清零。

最后还有模型调用、Tool调用、任务数、委派次数、Evidence数、深度和总时间预算。命中任何上限都会形成安全终态和审计记录，不会继续让两个Agent互相聊天。

### 46. 是否考虑共享记忆或黑板模式？

考虑过，但我没有采用任意Worker都能自由读写的自然语言共享记忆。

当前的TaskPlan、agent_tasks任务板、WorkerResult、Observation、Checkpoint和Evidence集合，本质上已经是一个结构化黑板。Supervisor可以看到任务状态和公开结果，Worker只通过Handoff接收完成当前任务所需的子集。

这种方式比共享一大段自由文本更容易做权限控制、版本冲突、确定性合并和恢复。Worker不能直接改另一个Worker的结果，也不能读取未转交的Evidence。

代价是合同更严格、开发量更大。如果以后需要跨任务长期知识，我会把它设计为经过授权、带来源和生命周期的独立Memory Service，而不是把聊天历史或模型总结直接当成可信长期记忆。

### 47. 7个只读 Tool 分别是什么？

题目中的7个是M2已实现的5个加M4计划新增的2个。

Business Data Worker有两个：

- get_product_spec：把商品名称、别名或SKU解析成唯一商品规格；
- search_inventory：按准确SKU、市场和可选仓库查询最新库存并生成数据库Evidence。

Knowledge Worker有三个：

- search_knowledge：执行权限前置的混合检索、重排和Context构造；
- read_uploaded_file：按公开file_id和结构定位读取有界解析内容；
- get_evidence_detail：对已有Evidence ID重新授权并展开详情。

Web Research Worker计划有两个：

- search_public_web：通过受控Service和Tavily发现候选来源；
- read_public_source：只读取同一Run中已搜索发现并获准的来源。

因此当前代码中的准确说法是5个，M4完成后才是7个。

### 48. 为什么全部设计成只读？报告或写操作如何处理？

第一版目标是研究和决策支持，不是自动执行经营操作。把Agent Tool限制为只读，可以显著降低模型误操作、越权修改和重复执行的风险，也让并行和重试更容易推理。

生成报告不等于修改业务系统。Worker只负责读取和形成结构化结果，Report Service根据已验证Evidence确定性生成Markdown Artifact；这是系统内部产物，不会自动修改库存、价格、Listing或广告。

文件上传由明确的用户API操作完成，也不作为模型可以自主调用的Tool。这样用户知道自己在上传什么，权限和文件安全检查也有独立入口。

如果以后增加写操作，我会采用“生成建议—展示diff—用户审批—服务端重新鉴权—幂等执行—结果回读”的两阶段模式。高风险操作还需要多人审批、业务限额、撤销或补偿流程，不能只在Prompt里让模型先询问一句。

### 49. Tool JSON Schema 如何设计？如何处理枚举、可选参数和日期范围？

每个Tool使用独立Pydantic输入模型，再将JSON Schema作为模型可见合同。Schema必须是object，并设置additionalProperties=false；tenant、user、role、SQL、路径、Token和budget等字段不能出现在模型参数中。

以search_inventory为例，必填字段是sku和market_code，可选字段是warehouse_code。market_code使用Literal，只允许DE或FR；Pydantic还验证warehouse_code前缀必须与market_code一致。SKU、字符串长度和格式也有边界。

当前库存Tool没有日期范围，因为它的业务语义是读取最新快照。模型如果传start_date或top_k会因额外字段被拒绝。

根据我的设计，如果以后增加历史趋势Tool，日期应使用ISO 8601的date类型，明确start_date小于等于end_date、最大跨度、时区和闭区间语义；不能接受“最近一段时间”这种模糊字符串直接进入Repository。

### 50. 模型参数错误、缺失或幻觉参数时如何纠正？

参数要经过三层验证：Qwen结构化输出Schema、Capability Resolver中注册的参数Schema、真正Tool输入的Pydantic模型。未知字段、缺失必填字段、非法枚举和类型错误都不能到达业务Repository。

对于结构合法但业务不完整的情况，例如市场有多个仓却没有warehouse_code，Tool返回公开安全的业务错误；Worker把它转换成Observation，模型可以在剩余决策和预算内补充参数或向用户追问。

模型不能借纠错过程改SKU、tenant或读取其他Evidence。Business Worker会锁定已经解析出的SKU，Knowledge Worker要求query、file_id和evidence_id必须来自Handoff或本次Observation。

如果Provider输出连基本结构都不合法，系统会安全终止当前决策，而不是把原始错误响应反复喂回模型无限重试。

### 51. Capability Resolver 如何决定 Agent 或用户能调用哪个 Tool？

Capability Catalog保存服务端注册的版本化能力，包括类型、版本、参数Schema、副作用、是否产生Evidence、实现状态、允许角色和允许Agent。

Resolver先定位精确AgentDefinition。例如business_data只能申请get_product_spec和search_inventory，knowledge只能申请三个知识Tool。然后再与当前RunContext中的用户角色求交集，只返回implementation_status为available的能力。

模型看到的是脱敏后的ResolvedCapability，而不是Tool实例、数据库连接、tenant或超时配置。模型选择一个ID后，Runtime仍会再次验证归属，Harness再检查tenant、role、market和side_effect。

因此最终权限不是模型自己决定，而是“Agent允许范围、Tool策略、当前用户权限和系统安全策略”的交集。不存在找不到能力后回退到某个同名或默认Tool的逻辑。

### 52. 预算、超时、幂等和审计分别在哪一层实现？

预算由Runtime中的AgentBudgetTree负责。它原子预留根Run和子Run的模型调用、Tool调用、Token、Evidence、任务、委派深度和时间，避免两个并行Worker各自认为预算还充足。

超时分层实现：Provider有请求超时，Worker由asyncio.wait_for限制，Tool定义自带timeout_ms，Repository使用PostgreSQL transaction-local statement_timeout。

幂等在API、Runtime和业务层共同实现：request_id决定消息和Checkpoint重放；Tool名称加规范化参数形成重复签名；索引、Context和Evidence还有各自的确定性身份或唯一约束。

审计由TraceRecorder和PostgreSQL完成。AgentRun记录父子关系、状态、模型/Tool计数和耗时；ToolCall记录版本、脱敏参数摘要、权限结果、状态、错误和耗时；Evidence与ToolCall、Context和最终回答引用继续关联。

LangGraph只负责控制流，不独自承担这些工程职责。

### 53. 预算按什么计算？超预算后如何处理？

当前预算同时按模型调用次数、Tool调用次数、输入/输出Token、任务数、委派次数、Evidence数量、深度和墙钟时间计算，不只使用单一Token阈值。

公开根Run当前上限是24次模型调用、8次Tool、32,000输入Token、8,000输出Token、8个任务、12条Evidence、8次委派、深度1和60秒。Business与Knowledge子Run各有独立的30秒和调用额度。

金额预算目前没有单独实现，因为模型价格和Provider计费尚未进入统一可信价格表。根据我的设计，可以在记录模型、Token和时间后，由版本化Price Catalog换算金额，但不能只依赖模型自报Token。

超过预算后默认安全终止；已有合法证据且任务允许部分完成时可以返回partial，否则返回timed_out或明确失败。系统不会为了完成答案自动扩大预算，也不会在当前版本中转人工。

### 54. 只读 Tool 为什么仍需要幂等？如何实现？

只读不代表没有副作用。一次查询仍会消耗模型或Provider费用、占用CPU、写ToolCall审计、生成Context和Evidence；重复搜索还可能因为数据时间变化产生不一致结果。

当前通过request_id防止同一公开请求重复落消息，通过Tool名称和规范化arguments_summary生成签名限制同一Worker重复调用。Checkpoint恢复时会从数据库ToolCall重建历史签名。

Context和文档Evidence使用查询、检索快照、配置、用户范围等确定性身份；同一合法Context可以复用，而不是重复生成不同内容的Evidence集合。数据库唯一约束和状态Hash则防止并发覆盖。

真正的幂等不是简单缓存返回值，还要保证重复请求不会重复扣账、重复写审计或引用到不同权限状态。恢复前重新授权仍然必须执行，不能因为缓存命中绕过撤权。

### 55. 审计日志记录多细？是否保存原始响应？保留多久？

AgentRun记录tenant、thread、user、trace、root/parent Run、Agent、任务、预算引用、运行状态、业务结果、模型/Tool调用次数、耗时和安全错误。

ToolCall记录sequence_no、tool_name、tool_version、脱敏arguments_summary、permission_result、status、duration、开始/结束时间和安全错误码。Evidence再记录来源、定位、观察时间、内容Hash及与ToolCall或Context的关系。

我不会把API Key、数据库连接、原始SQL、完整Provider请求响应、完整文档正文或堆栈写入普通审计日志。大结果通过受控Artifact或Evidence ID引用。

当前项目没有实现正式的日志保留和自动归档策略，所以我不能声称“保留180天”。根据生产设计，应按数据分类设置期限，例如运行审计90～180天、原始敏感正文更短，并支持按tenant删除、法律保留和访问审计；具体期限需要业务与合规共同确认。

### 56. 跨境研究 Skill 是什么？

这个Skill不是一个长Prompt，也不是把实时法规写进Markdown文件。它是一个版本化的业务SOP，保存跨境研究中相对稳定的方法：目标澄清、市场拆分、内部与外部证据要求、来源优先级、冲突处理、停止条件、输出检查和评估样例。

例如研究一个商品进入新市场时，Skill要求先确认商品和目标市场，再检查内部库存/规格、内部合规资料和公开来源，最后把事实、推断、假设、未知和冲突分区输出。具体执行顺序仍由任务情况决定，不写死蘑菇灯、德国或法国。

Skill只申请能力范围，实际可用能力还要与Worker、父Agent委派、用户权限、系统策略和资源ACL求交集。

当前它属于M4-08计划，尚未创建app/skills下的正式实现。因此面试时我会把以上内容明确描述为已确认设计，而不是已交付功能。

### 57. Skill 如何做版本管理和回归测试？

当前研究Skill尚未实现，下面是已经确认的工程设计。

每个Skill需要稳定ID、语义版本、输入输出合同、申请的Capability、步骤、停止条件和变更记录。AgentRun应记录实际使用的Skill版本，保证历史报告可以解释。

回归测试至少覆盖固定Fake Provider、真实PostgreSQL、显式Tavily/Qwen Smoke和Chromium端到端；样本不仅包括德法蘑菇灯，还要替换商品和市场，证明Skill没有记住Golden答案。

升级时先在Debug/Validation运行新旧版本，对比任务完成率、Evidence覆盖、引用正确率、调用数、Token和Bad Case；冻结Test只用于最终确认。若存在回归，旧版本继续可用，不能静默覆盖所有历史任务。

### 58. Harness 与 LangGraph ToolNode 的边界是什么？

LangGraph负责“什么时候进入哪个节点”，Harness负责“这次Tool到底能不能、应不应该、以什么边界执行”。

当前没有直接把ToolNode当成安全执行层。模型先提出结构化Action，Worker验证动作与Handoff范围，Capability Resolver验证Tool归属，然后Harness检查白名单、只读副作用、角色、tenant、market、预算和重复签名，再创建ToolCall审计并调用Service。

Tool执行发生异常时，Harness把它转换成安全错误，记录状态和耗时，并保证事务回滚。LangGraph只接收公开Observation，不接触数据库Session、原始异常或密钥。

如果直接使用通用ToolNode而没有这层封装，权限、预算和审计容易散落在每个Tool里。ToolNode仍可以作为未来的调度组件，但不能替代项目的执行安全边界。

### 59. “严格事实恢复率”的准确定义是什么？

严格事实恢复率是Parser/OCR层指标，不是检索Recall，也不是最终答案正确率。

评估集为每个可回答问题冻结expected_evidence_spans.exact_text。Runner读取选中后的Canonical Parsed Artifact，把文本Block、表格单元格和公式组成可搜索文本，只做空白归一化和大小写折叠；一个案例的全部冻结原文片段都能逐字命中，才算recovered。

公式是：恢复案例数除以应恢复案例数。它不会使用答案同义词、可接受变体、模糊匹配或模型输出放宽标准。

初始18文档基线为22/34，即64.71%；问题主要是健康PDF被整文档切到Docling后丢字，以及DOCX页眉和图片文字缺失。经过Native健康度路由、Docling进程隔离、DOCX页眉/图片OCR和发布前质量门禁后达到34/34。

34/34只能证明当前固定Golden原文进入了Canonical Artifact，不能证明文档所有文字都完美、检索一定召回或最终回答一定正确。

### 60. 18份欧盟文档规模、类型和语言如何？

这里需要先纠正一个表述：18份不是全部欧盟官方文档，而是10份版本化合成回归文档加8份欧盟官方PDF。

10份合成文档包括4个PDF、3个DOCX、2个XLSX和1个CSV，合计249,311字节，主要语言是zh-CN。其中包含扫描PDF、双栏PDF、合并表头表格、DOCX页眉与内嵌图片OCR等复杂样本。

8份官方来源全部是英文PDF，来自欧盟委员会、DG TAXUD、GPSR和Safety Gate等来源，总计5,152,421字节、275页。因此整个18文档语料约5.40 MB，共12个PDF、3个DOCX、2个XLSX和1个CSV。

当前34条可回答Golden中，合成组20条、官方跨境组14条，另有4个OCR关键字段。这个规模适合做可解释的工程诊断，但不足以证明对所有欧盟语言、手写扫描件或大规模企业文档都能泛化。

## 第四批：RAG 检索、模型、性能与成本（61～80）

### 61. Native、Docling、Hybrid 路由如何实现？判断依据是什么？判断错了怎么办？

我的实现不是先看扩展名就直接选择某个高级解析器，而是所有支持格式都先经过Native解析和文件安全限制，再基于Native产物做确定性判断。这样至少保留一份可审计的底稿，也避免复杂解析器绕过页数、压缩比、文件大小等安全边界。

具体规则是：CSV始终走Native；PDF先计算非空字符数、有效字符比例和有效页覆盖率，默认阈值分别是20个字符、90%和80%，健康PDF继续用Native，可疑或不可用PDF才进入Docling；DOCX使用项目自己的Native结构解析，并在原位提取页眉、页脚和内嵌图片OCR；XLSX遇到合并单元格等复杂特征时走Hybrid。当前Hybrid不是把两份Markdown简单拼接，而是运行两路并保存比较结果，最终仍以Native保留公式、缓存值、单元格和Sheet结构事实。

选路后还有第二道发布门：健康Native底稿与最终稿的字符保留率不能低于70%，PDF逐页检查不能丢掉原有文本或漏掉图片页OCR，DOCX还要检查大图空OCR。明确失败时整份解析失败，不能静默发布脏Artifact。最近18份固定文档实测路由为Native 16份、Docling 1份、Hybrid 1份。

我也承认这个规则不是万能的。例如一个PDF字符量充足但双栏阅读顺序错误，文本健康度可能仍判为healthy，字符门禁也未必发现语义顺序问题。这类误判要靠版面顺序Golden、Bad Case回放和后续阈值校准发现，不能声称后置门禁可以消除所有误路由。

### 62. OCR 质量门禁如何设计？

我没有把“平均OCR置信度高于某个数”当成唯一门禁，因为高置信度也可能把错误文字稳定识别出来，低置信度的短编号反而可能是关键事实。

门禁分三层。第一层是输入安全：PDF页数、文件大小，DOCX的ZIP成员数、展开大小、压缩比、图片数量、单图/总图片字节和像素数都有限制，外部图片关系直接拒绝。第二层是是否需要OCR：PDF Native文本为空、低文本页或扫描页信号会升级Docling；DOCX内嵌图片由固定RapidOCR本地模型处理，并保留图片Hash、原段落和Run位置。第三层是解析后质量：PDF最终页少于10个有效字符时，会结合Native该页字符数和图片数判断是空白页、文本回退还是OCR未恢复；DOCX图片超过5 KiB且OCR为空时，根据图片所在段落及全文正文量决定拒绝或告警。

OCR置信度会写入结构化来源用于诊断，但当前发布决定主要依据“应有内容是否恢复、位置是否保留、是否发生明显截断”。固定样本中4个OCR关键字段达到4/4，某次报告的平均置信度约0.993；这个结果只能证明当前英文质检卡和扫描样本，不代表手写体、多语言和所有拍照质量都已解决。

### 63. 严格事实恢复率从 64.7% 提升到 100%，各项改进分别贡献多少？

初始分母是34条可回答Golden，22条恢复，严格恢复率是22/34=64.71%。我按失败归因而不是按“换了更强模型”解释提升。

第一项是Native文本健康度路由，修复了10条`route_selection_loss`：这些PDF的Native文本本来完整，却因版面复杂标签整文档切到Docling，最终丢字。改为“健康文本优先Native、复杂标签只作提示”后，从22/34提升到32/34，贡献10条，也就是29.41个百分点。

第二项是DOCX视觉来源提取，补回1条页眉事实和1条正文图片OCR事实，从32/34提升到34/34，贡献2条，也就是5.88个百分点。

Docling一次性子进程隔离和解析后质量门禁对这个内容分数的直接增量都是0，但工程价值不能算0：前者解决约2 GB级模型在超时、崩溃后的进程清理和资源污染；后者阻止字符骤降、逐页丢失或空OCR产物被标记为ready。也就是说，内容恢复的直接贡献是10+2，稳定性和防伪贡献不能硬换算成Recall增量。

### 64. 18份文档是否会过拟合？如何证明泛化能力？

会有过拟合风险，我不会用18份文档和34条事实宣称“对所有企业文档泛化”。这批数据更像可解释的工程回归集：10份合成文档刻意覆盖扫描、双栏、页眉、图片、表格、合并单元格和公式，8份官方PDF提供与合成模板不同的真实版面和英文长文档。

我采取了三点降低自欺。第一，Golden原文和失败类型在修复前冻结，不能修完以后删难题或改成模糊匹配；第二，指标按Parser、Chunk、Retrieval、Reranker、Answer分层，同一个样本不能用最终答案碰巧答对来掩盖上游丢字；第三，参数比较保留全部候选和Bad Case，不只报告最好的一次。

这些措施能证明修复不是针对某一句答案写特判，但还不能充分证明泛化。根据我的评估设计，下一步应按“文档来源”而不是按问题随机切分Debug、Validation和冻结Test，再增加未见过的供应商模板、低质量扫描、多语言官方材料和表格变体。只有在文档级Holdout上保持指标，并且新失败可归因，我才会把它描述为泛化能力，而不是回归集满分。

### 65. BGE-M3 的稠密、稀疏和多向量召回分别如何使用？

这里我要纠正一个容易被模型名称带偏的说法：BGE-M3本身支持Dense、Sparse和Multi-vector能力，但当前项目只启用了Dense，不应说三种模式都已经落地。

我固定使用`BAAI/bge-m3@5617a9f61b028005a4858fdac845db406aefb181`，以CLS池化生成1024维、L2归一化向量；文档和查询使用不同purpose生成cache key，向量通过pgvector余弦距离召回。

项目中的“稀疏路”不是BGE-M3 sparse，而是PostgreSQL全文检索：同一套冻结的Unicode归一化和jieba搜索分词生成FTS文本和查询，再用`ts_rank_cd`排序。Multi-vector/ColBERT式向量目前没有使用，因为它会显著增加存储、索引和在线打分成本，在当前几百个Chunk规模下没有证据证明收益值得复杂度。

我的取舍是先把Dense负责语义和跨语言、FTS负责型号与精确词、RRF负责融合、Cross-Encoder负责精排这条链做完整评估。如果后续Bad Case显示长文档局部匹配仍是主要瓶颈，再用同一冻结集评估BGE sparse或Multi-vector，而不是因为模型支持就全部打开。

### 66. BM25 和向量各召回多少候选？RRF 的 k 如何选择？

当前准确实现不是BM25，而是PostgreSQL FTS加`ts_rank_cd`。Dense和Lexical各最多召回30条获权候选，先各自形成从1开始的稳定排名，再按Chunk ID合并去重。某个Chunk只出现在一路也可以进入融合结果。

RRF分数是各路`1/(k+rank)`之和，当前`k=60`，Hybrid最终也最多保留30条交给Reranker。选择RRF的原因是Dense余弦相似度与FTS分数不在同一量纲，直接加权必须先校准；RRF只依赖名次，对分数尺度变化更稳。

`k=60`目前是冻结的工程基线，不是我在小测试集上搜索几十个值后挑出的最优数字。它能降低第一名对结果的过度支配，让两路共同支持的候选稳定上升。真正调参时我会在Validation集比较`k=20/40/60/80`以及候选数，联合观察Recall@30、Recall@8、MRR、数据库延迟和Reranker成本，最后只在冻结Test上验一次，避免把Test调成训练集。

### 67. BGE-Reranker 的架构是什么？重排多少候选？增加多少延迟？

我使用的是`BAAI/bge-reranker-v2-m3@953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e`。它属于Cross-Encoder：把query和每个passage成对联合编码，直接输出相关性logit；这和BGE-M3先把两边各自编码、再算余弦相似度的Bi-Encoder不同。Cross-Encoder排序更准，但不能像向量一样预计算文档侧，因此只适合第二阶段。

服务端最多把30条Hybrid候选交给它，全部评分后按raw logit排序，sigmoid值只用于展示和合同校验，不当成业务概率；最终保留Top 8，相同分数按原Hybrid rank和Chunk UUID稳定打破平局。Reranker只能删减和重排已获权集合，不能自己查库或引入新Chunk。

延迟必须按硬件说。旧的本地CPU正式验收中，每题约15个候选、batch 2，Reranker p50/p95约为6.70/7.24秒，Hybrid检索本身只有约40.8/48.5毫秒，所以CPU精排是明显瓶颈。另一个6对小基准在模型常驻后是0.545/0.671秒，首次模型加载约7.04秒。两种测量的候选长度和语料不同，不能混成一个数字。前文4.1秒是简单请求路由优化后的请求级指标，也不能拿来冒充这次RAG精排延迟。

### 68. Recall@8 从 86.7% 提升到 95.6%、MRR@8 从 0.712 提升到 0.846，分别由哪些模块贡献？

我先明确口径：Recall@8是可回答问题中“前8条至少包含一条相关证据”的比例；MRR@8取第一条相关证据排名的倒数，超过8或没有命中记0，再求平均。因此Recall更关心有没有进入上下文，MRR更关心正确证据是否靠前。

本轮90条Golden评估中，Dense基线为Recall@8 86.7%、MRR@8 0.712，完整链达到95.6%和0.846。消融结果显示，Hybrid FTS+RRF对Recall贡献最大，主要补回SKU、法规编号、百分比和专有词等Dense容易漏掉的精确匹配；BGE-Reranker对MRR贡献最大，它不创造候选，但把已经在Top 30里的正确段落从后排拉到前排；结构感知切块对表格、标题限定和跨段上下文两项都有贡献。

我不会在没有逐配置报告的情况下继续编造每层精确增加几个百分点。判断贡献时必须使用同一查询、同一权限快照和同一分母，分别比较Dense、Dense+FTS/RRF、再加Reranker、再切换Chunk配置，并保留逐题rank。Bad Case里如果相关Chunk根本不在Top 30，责任在召回或分块；如果在Top 30但没进Top 8，才主要归因于Reranker。

### 69. Citation Accuracy 96.3% 如何评估？人工还是 LLM Judge？粒度多细？

我的主指标按“事实声明—引用”对计算，不是检查答案末尾有没有一个链接。分母是最终答案里实际附带引用的可核验声明，分子是引用内容确实支持该声明、实体和数值口径一致的数量，Citation Accuracy就是两者相除。无引用但应引用的声明另外计入Citation Completeness，不能靠少引用来提高Accuracy。

96.3%的最终口径以人工核验为主，程序先做确定性检查：`[E1]`到真实Evidence UUID必须一一对应，Evidence仍属于当前tenant和用户权限范围，文档版本必须active，locator和内容Hash必须有效。然后人工判断引用片段是否真正蕴含回答中的事实。LLM Judge可以辅助发现可疑样本或做批量预标，但不能成为唯一裁判，尤其不能让生成答案的同类模型给自己打分。

粒度是Chunk/证据片段级，而不是只到文档级。PDF尽量落到页码和bbox，DOCX落到Section、段落和Run，XLSX落到Sheet、行列或单元格，数据库落到SKU、仓库、snapshot_at和参与计算的字段。一个Chunk里包含相关词但不支持具体数字，仍判引用错误。96.3%说明当前测试集上引用大多可支撑声明，不代表事实覆盖率也是96.3%，两项要分开报告。

### 70. 无证据拒答 F1 0.91 如何调出来？阈值变化有什么权衡？

我把“应该拒答”视为正类，同时记录Precision和Recall，再计算`F1=2PR/(P+R)`。评估集必须同时包含确实无答案、权限不可见、旧版本有答案但active版本无答案，以及有弱相关词却不能支持结论的困难负样本；否则把明显无关问题塞进去，很容易得到虚高F1。

阈值不是只看Reranker的sigmoid分数，因为这个值没有校准成事实正确概率。根据我的评估设计，我在Validation集联合扫描Top 1/Top K相关性、证据覆盖、答案可引用声明比例和权限状态：高于回答门槛才生成事实答案，低于拒答门槛则明确no_evidence，中间区间优先澄清或说明证据不足。最终冻结工作点在Test集得到F1 0.91。

提高回答门槛会增加拒答Recall和Citation Accuracy，但也会误拒可回答问题，降低任务完成率；降低门槛会减少用户看到的拒答，却增加“有一段看似相关就强答”的风险。跨境合规和精确库存里，错误回答成本通常高于一次诚实拒答，所以我偏向保守工作点，同时把“权限拒绝”“系统失败”和“确实无证据”分开，不能都包装成no_evidence。具体阈值必须跟模型、Chunk和语料版本一起记录，不能脱离报告口头报一个永恒数字。

### 71. 90条 Golden 事实的来源和标注过程是什么？标注者一致性如何？

90条Golden的单位是原子事实，不是90段模型自由生成的标准答案。每条至少包含query、是否可回答、期望事实或拒答标签、来源文档与版本、原文证据span、locator、关键实体以及允许的答案变体；表格数字还要保留行列语义和单位。

根据我的评估设计，来源覆盖合成业务文档和欧盟官方材料，并有中文、英文、德文问法、精确编号、表格、OCR、跨段和无证据样本。标注时先从原始来源选择可复核事实，再写问题，最后由脚本检查span能在指定Artifact和locator中找到。数据按来源文档切分Debug、Validation和Test，避免同一段落的改写同时出现在调参与测试中。

标注主要由我完成，官方事实再回到原文做第二遍人工复核。这里没有两名独立标注员对同一批样本盲标，所以我不能声称有Cohen's kappa或“标注者一致性95%”；同一人复核只能叫复查，不能叫inter-annotator agreement。若用于正式团队评估，我会抽取至少20%双人独立标注，对answerability、证据span和locator分别计算一致率或kappa，分歧由第三人裁决。

### 72. 检索失败的主要原因是什么？

我把失败按链路分层，否则所有问题都会被笼统归成“Embedding不准”。

多语言和同义表达主要影响Dense，例如中文问法与英文/德文原文的业务术语不一致；SKU、法规编号、百分比和缩写主要需要FTS精确词补回；表格失败常来自标题、表头和数据行被切开，或合并单元格语义没有进入`retrieval_text`；产品型号还可能因连字符、大小写或相似SKU分词不一致而漏召回。

还有两类不是检索算法能修的：Parser/OCR根本没恢复文字时，任何召回都找不到；正确Chunk已在Top 30但被排到Top 8之外时，问题在融合或Reranker。长规则文档还会出现“主规则在一节、例外在下一节”的跨段问题。

我的排查顺序是：先看Golden证据是否在Canonical Artifact，再看是否完整落入Chunk，然后看Dense rank、Lexical rank、RRF rank和Reranker rank，最后检查Context是否因Token预算裁掉。只有定位到具体层，才决定补同义词、改分词、调整分块、扩大候选或重训/更换模型。

### 73. 外部网页如何去重、清洗和过滤？Tavily 是否足够？

当前Web Research Worker尚未实现，所以这部分是已确认设计，不是我已经跑通的能力。

计划中，`search_public_web`只接收有界查询并通过可替换Provider调用Tavily，返回服务端生成的`search_result_id`；`read_public_source`只能读取同一Run里已经发现的ID，模型不能提交任意URL。抓取前会规范化URL，去掉fragment和已知跟踪参数，再以canonical URL、最终重定向URL和正文Hash做精确去重；近重复正文可再用SimHash或MinHash聚类，但这一步需要实测阈值。

清洗层会拒绝非HTTP(S)、私网地址、异常Content-Type和超大响应，移除script、style、导航、页脚和广告，只保留标题、作者/机构、发布时间、正文、表格、规范URL和抓取时间。质量过滤会综合来源等级、域名、发布时间、目标市场/语言、正文完整度和多来源交叉验证；法规优先欧盟或成员国官方原文，搜索摘要本身不能作为最终证据。

Tavily只解决候选发现和部分内容抽取，不等于可信性判断。它的排序、摘要和可访问性都可能变化，也可能返回转载、SEO页面或过期内容。因此Provider必须可替换，原文要重新读取、Hash、引用和审计；关键结论至少用一个权威一手来源，存在冲突就显式保留，而不是盲信Tavily第一名。

### 74. pgvector 使用什么索引？数据量和查询性能如何？

向量列是可空的`vector(1024)`，使用余弦距离，索引是HNSW加`vector_cosine_ops`；词法侧另有GIN索引。Embedding模型、revision和cache key与向量一起保存，active Index Set、tenant、ACL、market和软删除条件在候选查询时就生效。

当前数据仍是作品级规模，不是百万级生产库。最新18文档Chunk矩阵中，代表性的`700/850/120`配置产生417个Chunk；正式评估结束会清理临时索引数据，生产Seed不能被说成长期积累了大量向量。早期真实检索验收中，每题约15个Hybrid候选，Hybrid p50/p95约40.8/48.5毫秒；但这个数字包含Dense、FTS和RRF的小数据链路，不是独立HNSW基准。

我还做过`EXPLAIN`验证：在测试事务中关闭顺序扫描后，向量查询确实使用`ix_document_chunks_embedding_hnsw_cosine`，FTS使用GIN。这能证明索引表达式和SQL匹配，不能证明小表上HNSW比顺序扫描更快，因为优化器在几百行上选择Seq Scan可能反而合理。我没有百万Chunk、并发QPS、HNSW recall/latency曲线，所以不会把当前结果包装成大规模性能；扩容时要实测`m`、`ef_construction`、`ef_search`、分区、过滤选择率和连接池竞争。

### 75. 内部库存为什么也走向量检索？如何保证精确数字？

这个问题的前提需要纠正：内部库存没有走向量检索，而是精确SQL。模型或程序先通过`get_product_spec`把商品名、别名解析成唯一SKU，再由`search_inventory`按tenant、market_code和可选warehouse_code读取最新库存快照。

可售库存由Service使用结构化整数计算：`available = on_hand - reserved - unsellable`。例如德国仓125这个结果必须能回溯到三个原始字段和`snapshot_at`；模型不参与算术，也不能用Embedding相似度决定数字。Repository还负责tenant、市场范围和最新快照边界，查询不到、无权限和零库存是三种不同结果。

向量检索只用于非结构化知识，例如SOP、法规说明和供应商文档。即使文档里出现数字，最终也要引用原Chunk和表格定位；如果同一个精确经营指标已经存在数据库，我会让数据库成为权威来源，文档或网页只能提供解释，不能覆盖最新快照。这样既利用语义检索的召回能力，又不牺牲结构化数据的精确性。

### 76. 使用的 Qwen 是哪个版本、参数量和部署方式？为什么不选 GPT 或 Claude？

当前配置固定的模型标识是`qwen3.8-max`，通过阿里云DashScope的OpenAI-compatible HTTPS接口调用，`base_url`是`https://dashscope.aliyuncs.com/compatible-mode/v1`。它是托管API，不是我下载权重部署的开源参数模型；项目合同和Provider响应也没有给出可核验参数量，所以我不会把一个猜测的参数规模写进简历。

我选择Qwen主要考虑中文指令理解、严格JSON Schema输出、跨境场景的中英多语言、国内网络和账号可用性，以及与现有技术栈的接入成本。实际Provider关闭模型搜索和thinking扩展，temperature为0，分别约束Planner、Decision、Handoff和Answer的结构化输出；即使模型返回合法JSON，服务端仍会二次验证权限、任务和引用。

我没有用当前小样本证明它全面优于GPT或Claude。后两者完全可以作为候选Provider，比较时应该在同一冻结集上看计划合法率、工具选择、Citation Accuracy、拒答、p95、Token和价格，而不是只比较榜单分数。我的架构把模型放在Provider边界后，就是为了以后可以替换；当前选择是工程约束下的最优折中，不是永久绑定。

### 77. LLM 是否自部署？推理延迟、吞吐、量化和并发如何？

LLM没有自部署，因此量化也不是我控制的；推理硬件、参数并行和服务端batch由DashScope负责。应用侧使用异步HTTP客户端，单次Provider超时默认5秒，输出上限4096 tokens，并对超时、429、5xx和坏JSON做类型化安全处理。

我目前有代表性真实Qwen Smoke，整组多角色调用`1 passed in 23.45s`，但它包含Planner、Handoff、Action和Answer等多次调用，不能除一下就冒充单次模型吞吐。题目中的4.1秒是路由优化后的请求级p95，也不是纯Qwen推理延迟。当前Provider适配器还没有把供应商返回的usage可靠写入持久化审计，也没有做正式QPS压力测试，因此没有可信的tokens/s或最大并发数字。

应用编排最多并发两个互不依赖、不同Worker的只读任务；这个“2”是为了根预算、Session隔离和稳定合并设置的系统上限，不代表DashScope只能承受2并发。若进入生产，我会分别压测单Provider调用和完整请求，记录首Token、完整响应、429率、超时率和每模型Token吞吐，再用连接池、全局信号量和队列做背压，而不是无限放大`asyncio.gather`。

### 78. BGE-M3 和 BGE-Reranker 部署在哪里？批处理和延迟如何？

两个模型都以固定revision缓存在本地`data/model-cache`，强制local-only加载，不在运行时下载。已记录的基准机器都使用CPU和float32，没有验证CUDA生产性能；Embedding默认batch 4，Reranker默认batch 2，遇到可识别的内存不足会逐级减半到1，普通异常不会伪装成OOM重试。

BGE-M3的本地报告使用6核/12线程、约16 GB内存机器：加载约20.37秒，7条混合长短文本编码约22.44秒，吞吐0.312 texts/s，进程峰值增量约1.37 GiB。索引阶段可以批量离线执行并复用ready Index Set；在线查询只编码一个query，但目前没有把单query冷暖延迟单独包装成SLA。

BGE-Reranker的另一份CPU报告使用16核/24线程、约31.84 GB内存：加载约7.04秒；6个pair常驻模型基准p50/p95约0.545/0.671秒，而正式约15候选评估为6.70/7.24秒，查询阶段RSS增量约1.29 GiB。两份报告机器与输入不同，不能直接横向相减。

结论是，当前CPU部署足以验证离线模型和质量，但Reranker是知识请求的主要延迟瓶颈。优化顺序会是模型常驻、按真实长度动态batch、减少无收益候选、任务队列限流，再评估GPU或独立推理服务；每次优化必须同时检查Recall@8和MRR，不能只追求速度。

### 79. 单次复杂请求和简单请求消耗多少 Token、成本多少？

我先区分“预算上限”和“实际消耗”。当前根Run上限是32,000输入Token、8,000输出Token和24次模型调用，Business/Knowledge子Run各预留8,000输入、2,000输出；这些是防失控的天花板，不是平均用量。现有Qwen适配器还没有可靠解析并持久化Provider usage，所以我不能把预算数字冒充真实账单。

根据当前上下文合同做容量推断：明确SKU和市场的库存Fast Path可以零LLM调用，模型Token为0；不确定路由若需要一次结构化模型判断，通常会是约500～1,500输入、少于300输出。单次知识问答包含最多4,000个项目计数单位的Context，再加System Prompt、Schema和历史，通常可能落在5,000～8,000输入、300～800输出。包含规划、两个Worker和综合回答的复杂请求，可能累计到10,000～30,000输入、2,000～6,000输出，但必须受根预算截断。这些区间是根据合同的工程推断，不是已审计均值。

成本计算应按每次实际模型分别求和：`输入Token/百万×当时输入单价 + 输出Token/百万×输出单价`，再加外部搜索等非Token费用，并区分缓存输入价格。目前项目还没有版本化Price Catalog，也没有冻结供应商价格，因此我不会编造一个人民币单次成本。补齐usage采集和价格版本后，才能报告普通查询与深度任务的平均、p95和单次费用。

### 80. 是否做了 LLM 输出缓存、语义缓存或 Prompt Caching？命中率如何？

当前没有实现LLM输出缓存、语义答案缓存，也没有在Qwen请求中显式启用Provider Prompt Caching，所以不存在可报告的真实命中率。我不会把temperature=0误称为缓存，也不会把没有埋点的情况写成“命中率0%”。

已经存在的是确定性计算复用：Embedding cache key绑定原文、用途、模型、revision、池化、长度、归一化和精度；相同Chunk Set和Embedding身份会得到相同Index Set，ready结果不会重复索引；DOCX相同图片在单次解析内按SHA-256复用OCR；模型实例使用并发安全的懒加载。这些能减少重复计算，但不等于缓存LLM答案。

我暂时不直接缓存业务回答，是因为库存会随snapshot变化，文档ACL和active版本会变化，复用旧答案可能造成数据过期或越权。如果后续实现，cache key至少要包含tenant、user/role、market scope、ACL版本、模型/Prompt/Schema/Skill版本、active Index Set、业务snapshot和规范化query；命中后仍要重新授权Evidence。语义缓存只适合权限和时效边界明确的低风险问题。

评价缓存也不能只看命中率。我会同时记录`hit/(hit+miss)`、节省的Token和p95、过期命中率、权限拒绝数及答案质量回归；任何一次跨租户或撤权后仍命中都应视为严重安全失败。
