# 秋招目标下的项目范围调整与实施方案

> 文档状态：方向与M4推荐版详细范围已确认
> 记录日期：2026-09-03
> 适用范围：M2后续收口、M3暂缓、M4重新定界、M5精简保留
> 当前开发授权：本文与M4正式阶段文档只记录方案，不授权开始M2-21.1、M3、M4-01或M5代码开发
>
> 2026-09-04更新：M2-21秋招目标复核方案已经用户确认；该复核不删除M2、M4或M5能力。当前先讲清整个M2-21，仍不构成M2-21.1开发授权。

## 1. 为什么需要这份文档

原始路线计划依次完成库存查询、自建RAG、多模态商品分析、深度研究与报告、评估与作品化。随着秋招时间约束变得更重要，继续平均投入所有方向会带来两个问题：

- 图片、OCR、相似SKU、网络研究、表格分析、图表、PDF和多个Skill同时展开，范围过大；
- 每项能力可能只能完成表面Demo，难以留下真实指标、故障矩阵和可讲清楚的Bad Case。

本轮讨论形成的新方向是：优先把多Agent、RAG、Evidence、权限、评估和完整前后端链路做深；M3多模态从秋招主线暂缓；M4必须保留，以避免项目退化为普通企业内部RAG问答。2026-09-03后续讨论已经确认M4采用推荐版，完整有效方案见[M4阶段入口](../progress/M4/M4_DEEP_RESEARCH.md)与[M4-00正式方案](../progress/M4/records/M4_00_STAGE_PLAN.md)；M5中的评估、加固和作品化不能删除。

本文负责保存讨论结论、边界、候选实施范围和后续确认点。原始总体设计继续保留，用于说明项目最初愿景和被主动裁剪的范围。

## 2. 本轮对话形成的共识

### 2.1 已确认结论

1. 秋招目标岗位聚焦AI应用工程师、Agent工程师、RAG工程师和偏AI后端工程师。
2. M1库存查询与M2自建RAG仍然是项目基础，不因范围调整而删减已确认能力。
3. 当前必须先完成M2-21至M2-24，形成多Agent、RAG回答、API、前端、评估和故障验收闭环。
4. M3多模态商品分析暂时退出秋招主线；图片上传、OCR、视觉Schema、相似SKU和多模态评估均不作为当前必做项。
5. M4必须保留。若完全删除M4，项目在产品观感上容易变成企业内部RAG问答，也难以证明多Agent、Handoff、并行、Checkpoint和多来源Evidence的必要性。
6. M4不能写死为“只生成德国/法国蘑菇灯报告”，也不能只等同于调用一次联网搜索。
7. M4目标是构建面向跨境电商业务的通用但有边界的深度研究能力：LLM按用户目标规划并组合企业数据库、内部RAG和公开互联网工具，输出简答、核验、对比、研究备忘录或报告。
8. 德国/法国蘑菇灯研究可以作为Golden Scenario，即标准验收场景，但不能成为硬编码执行逻辑。
9. Agent不是简单的“LLM加一个函数”。LLM接收Tool名称、描述和Schema并提出调用建议；LangGraph管理状态和流程；Harness实施权限、预算、超时和审计；Service与Repository真正执行确定性能力。
10. Tool定义Agent可以对外部世界采取的动作范围，但最终效果还取决于模型、Tool合同、数据质量、上下文、编排、权限和结果验证。
11. M5可以按新范围压缩样本和模块，但RAG/Agent评估、安全故障测试、性能成本、README、架构图、演示视频和简历材料不能删除。
12. M4采用推荐版：复用Supervisor、Business Data Worker和Knowledge Worker，只新增Web Research Worker；Analysis和Report首版使用确定性Service，不作为独立Worker。
13. 联网链路采用`search_public_web`与`read_public_source`两个受控Tool，经Service、Provider调用Tavily API；日常测试使用Fake Provider，V1不引入MCP。
14. M4首版先顺序验证再增加独立只读Worker有界并行，以PostgreSQL保存父子Run、任务租约和Checkpoint；不引入Redis/Celery。
15. M4首版输出结构化结果和Markdown，实现一个`cross-border-market-research` Skill；不做PDF、复杂指标、Pandas图表或额外M4 Skill。

### 2.2 尚未确认的事项

M4上述范围问题均已在正式阶段方案中确认。M5评估集最终规模、分布和质量门槛仍需在M5正式方案中确认；M4每个开发步骤仍需单独授权。本文不得被解释为对运行代码的自动授权。

## 3. 调整前后的项目定位

| 对比项 | 原始路线 | 当前秋招主线 |
|---|---|---|
| 项目定位 | 多模态多Agent深度研究平台 | 权限感知的多Agent企业知识、数据与网络研究平台 |
| 主要输入 | 数据库、文档、图片、网页、表格 | 数据库、内部文档、公开网页；图片暂缓 |
| M3 | 完整多模态商品分析 | 暂缓，不进入当前关键路径 |
| M4 | 多Worker、网络、报价、指标、图表、Markdown/PDF和4个Skill | 推荐版：只新增Web Worker，保留三类Evidence、有界并行、PostgreSQL Checkpoint、Markdown和1个研究Skill |
| M5 | 150条覆盖全部模态的评估与作品化 | 删除多模态评估，保留Agent/RAG/安全/性能与作品化 |
| Tool范围 | V1目标约13个 | 不以数量为目标，只实现研究闭环真正需要的Tool |
| Skill范围 | 5个业务Skill | M4首版只实现`cross-border-market-research`；M3和其他候选Skill不进入当前主线 |
| 求职叙事 | 技术覆盖全面 | Agent、RAG、Evidence和工程可靠性更集中 |

## 4. 调整后的阶段关系

```text
M1：企业业务数据库查询
  已完成
    ↓
M2：自建RAG＋多Agent核心底座＋知识问答前后端闭环
  当前主线，先完成M2-21至M2-24
    ↓
M3：多模态商品分析
  秋招主线暂缓，不作为M4前置条件
    ↓
M4：数据库＋内部RAG＋公开互联网的通用有界深度研究
  推荐版正式方案已确认，等待M2收口后单独授权M4-01
    ↓
M5：Agent/RAG评估、安全加固、性能成本与求职作品化
  必须保留，按新范围精简
```

M4不再等待M3完成。M3未来恢复时，可以把图片Evidence作为新的能力来源接入M4，而不是要求M4当前依赖图片。

## 5. Agent能力模型

### 5.1 大白话解释

- LLM是负责理解和决策的“大脑”；
- Tool是提供给模型的“能力按钮”；
- Service是按钮背后真正执行工作的稳定程序；
- Repository负责受控访问PostgreSQL；
- LangGraph是任务状态、节点、分支和循环；
- Harness是权限、预算、超时、重试和审计护栏；
- Skill是复杂业务任务的可版本化操作手册。

### 5.2 实际Tool调用链

```text
用户目标
→ LLM读取当前Worker允许的Tool名称、描述和输入Schema
→ LLM生成结构化Tool调用建议
→ Harness校验可信身份、Tool白名单、权限、预算和参数
→ Tool调用Service
→ Service调用Repository或外部Provider
→ PostgreSQL / RAG / Tavily返回结果
→ Service生成受控公开结果与Evidence
→ LLM继续规划或生成答案
```

模型只拥有申请Tool调用的能力，不拥有绕过Harness直接执行代码、SQL或网络请求的权限。

### 5.3 Tool设计原则

Tool应当是通用但有边界的能力，例如：

- `search_inventory`
- `get_product_spec`
- `search_knowledge`
- `get_evidence_detail`
- `read_uploaded_file`
- `search_public_web`

不应创建硬编码场景Tool，例如：

```text
generate_germany_france_mushroom_lamp_report
```

固定的是验收样本和业务边界，不是执行逻辑。同一组原子Tool应能按用户目标组合为规则查询、内外部核验、市场对比、风险分析和完整报告。

## 6. M2剩余范围

### 6.1 目标

完成当前已经确认的M2-21至M2-24，使M1业务数据与M2知识库能力通过统一多Agent底座对外提供，并形成可评估的完整产品链。

### 6.2 保留内容

- Supervisor与Business Data、Knowledge首批Worker；
- L0至L3自适应执行；
- Capability Catalog、Task、Action、Delegation、Handoff和Result合同；
- 父子Run、短期状态、树形预算和Evidence交接；
- 真实Qwen回答；
- 知识问答HTTP API；
- 前端上传、问答和Evidence展示；
- RAG最小评估集与Runner；
- 权限、故障、真实演示和Chromium回归。

### 6.3 M2-21复核边界

2026-09-04用户已确认复核后的公开Agent Gateway主路径、旧M1兼容生命周期、Worker自主循环、统一回答和验证顺序；方案不删除Supervisor、两个真实Worker、记忆、Checkpoint、树形预算、并行或后续评估/前端能力。当前只进入整个M2-21实施前讲解，不授权开始M2-21.1；M2继续以其[独立入口](../progress/M2/M2_KNOWLEDGE_RAG.md)和[M2-21唯一记录](../progress/M2/records/M2_21_ENGINEERED_MULTI_AGENT_PLAN.md)为准，每个开发小步骤单独确认。

## 7. M3处理方式

### 7.1 当前决定

M3状态仍使用项目统一枚举中的`待开始`，但从秋招关键路径暂缓。暂缓不等于删除设计，也不等于宣称已经实现。

### 7.2 暂缓能力

- 商品图片上传与安全链；
- 千问多模态结构化理解；
- OCR及区域定位；
- 事实、推断和未知项视觉Schema；
- `analyze_product_images`；
- `search_similar_products`；
- `product-visual-analysis` Skill；
- 多模态评估集与前端展示。

### 7.3 恢复条件

满足以下任一条件后，可重新提交M3阶段方案：

- M2、M4和M5求职主线已经收口且仍有时间；
- 目标岗位明确要求多模态或视觉LLM经验；
- 出现必须依赖商品图片的真实业务需求。

## 8. M4目标与边界

### 8.1 阶段目标

M4要证明系统能够根据用户目标动态规划，在权限和预算范围内组合内部与外部能力，形成可追溯的研究结果，而不是只能完成企业内部文档问答。

已确认的能力结构是：

```text
Supervisor
├─ Business Data Worker：企业数据库Evidence
├─ Knowledge Worker：内部文档Evidence
└─ Web Research Worker：公开互联网Evidence
```

### 8.2 支持的任务形态

M4不能只支持完整报告，应按复杂度支持：

| 任务形态 | 例子 | 典型执行 |
|---|---|---|
| 公开事实查询 | 查询某项欧盟公开规则 | 单Web Worker |
| 内外部核验 | 比较内部说明与官方要求 | Knowledge＋Web |
| 市场对比 | 比较不同市场公开信息 | 一个或多个Web子任务 |
| 综合分析 | 结合库存、内部资料和公开市场 | Business＋Knowledge＋Web |
| 深度报告 | 完整跨市场研究 | 多Worker、Checkpoint和报告输出 |

### 8.3 业务边界

M4追求通用能力原语，但不是万能互联网Agent。首版边界包括：

- 聚焦跨境电商运营与研究任务；
- 只读，不修改库存、不下单、不发布商品；
- 不绕过登录、付费墙或网站访问限制；
- 不承诺法律、医疗或金融高风险结论；
- 不允许无限递归、无限搜索或无限Worker扩展；
- 所有数据库、文档和网络结论必须通过Evidence交接；
- Tool执行继续受用户、Worker、系统策略和预算交集限制。

### 8.4 输出形态

首版输出类型包括：

```text
short_answer
evidence_summary
verification
comparison
research_memo
report
```

输出类型由用户目标和任务复杂度决定。首版由统一Answer Provider完成有证据的内容合成，Report Service只负责确定性Markdown组织；PDF不在当前M4范围，呈现形式不反向决定底层研究逻辑。

### 8.5 Golden Scenario与非硬编码要求

标准复杂验收场景暂定为：

> 综合德国、法国库存、内部产品资料和公开市场信息，形成蘑菇灯市场建议，并展示数据库、文档和网页Evidence。

同时至少需要两个不同形态的验收样本：

1. 单一公开信息查询；
2. 内部资料与公开来源核验。

这样可以证明底层能力能够组合，而不是只对一条固定Prompt工作。

### 8.6 三档比较与最终选择

| 档位 | 能力 | 优点 | 缺点 |
|---|---|---|---|
| 最小版 | Business＋Knowledge，内部两类Evidence，结构化综合回答 | 工作量最小 | 与内部RAG区别仍不够明显 |
| 推荐版 | 增加Web Worker、Tavily Provider、三类Evidence、有界并行、父子Run、预算、Checkpoint、Markdown研究结果和一个研究Skill | 能证明通用多来源研究与工程化Agent | 仍需较完整的安全、质量和成本验证 |
| 完整版 | 继续增加供应商报价、经营指标、Pandas、图表、PDF、更多Tool和4个Skill | 产品能力最完整 | 范围、测试和面试准备成本最高 |

上表保留当时的取舍依据。2026-09-03已经正式选择推荐版，详细边界和十步顺序以[M4阶段入口](../progress/M4/M4_DEEP_RESEARCH.md)与[M4-00正式方案](../progress/M4/records/M4_00_STAGE_PLAN.md)为准。方案确认不自动授权M4-01。

## 9. M5保留范围

### 9.1 必须保留

- Agent路由与Tool选择评估；
- Dense、Lexical、RRF和Reranker分层指标；
- Citation Accuracy与Evidence完整性；
- Forbidden Tool Violation、跨tenant和撤权测试；
- 预算、超时、重试、Checkpoint和故障注入；
- p50/p95、Token、模型费用和资源占用；
- README、架构图、API说明和演示脚本；
- 三至五分钟演示视频；
- 一个有前后指标对比的真实Bad Case；
- 简历表述与面试问答。

### 9.2 随M3暂缓而删除

- 多模态JSON有效率；
- 图片属性和OCR准确率；
- 图片事实、推断与未知项评估；
- 相似SKU视觉场景评估。

### 9.3 评估集规模

原计划约150条只是初始目标。新范围下不按数量凑样本，建议在M5正式方案中根据M2与M4最终能力重新分配约80至120条高价值样本，并冻结独立测试集。最终数字仍需单独确认。

## 10. 实施顺序

### 步骤1：完成M2-21至M2-24

- 预计修改：以M2正式方案中列出的Agent合同、Runtime、Graph、API、前端、测试和M2过程记录为准；
- 调用链：前端 → API → Schema → Agent/LangGraph/Harness → Tool → Service → Model/Repository → PostgreSQL；
- 验证：单元、真实PostgreSQL集成、真实Qwen/BGE Smoke、Chromium端到端、权限与故障矩阵；
- 完成标准：库存和知识Worker通过统一多Agent底座返回可核验Evidence，M2-24正式收口。

### 步骤2：提交M4正式阶段方案（已完成）

- 已新增：`docs/progress/M4/M4_DEEP_RESEARCH.md`与`records/M4_00_STAGE_PLAN.md`；
- 已确认：推荐版、两个Web Tool、只新增Web Research Worker、三类Evidence、PostgreSQL恢复、Markdown和一个研究Skill；
- 调用链：本步只属于方案层，尚未修改运行链；
- 当前边界：M4阶段状态仍是`待开始`，M2收口前不授权M4-01。

### 步骤3：按Walking Skeleton实现M4

以下是正式方案的摘要，精确输入、输出、文件、验证和完成标准以[M4-00正式方案](../progress/M4/records/M4_00_STAGE_PLAN.md)为准：

1. 冻结研究、搜索、正文读取、Web Evidence、任务和结果合同；
2. 建立搜索/正文Provider接口与确定性Fake；
3. 建立`search_public_web` Service/Tool与Harness策略；
4. 建立受控`read_public_source`与长网页Evidence管线；
5. 建立Web Research Worker和单Web查询；
6. 跑通Knowledge＋Web及Business＋Knowledge＋Web顺序协作；
7. 增加PostgreSQL任务、租约、Checkpoint和有界并行恢复；
8. 增加`cross-border-market-research` Skill与Markdown Service；
9. 增加任务API及前端进度、结果、Evidence展示；
10. 接入真实Tavily并完成质量、安全、成本、故障和端到端验收。

### 步骤4：提交并实施精简M5

- 根据M2与M4最终能力冻结评估集；
- 建立或补齐自动Runner与版本记录；
- 完成安全、故障、性能和成本矩阵；
- 完成README、图、视频、简历和面试材料；
- 不重新加入没有真实需要的多模态范围。

## 11. 完整调用链中的位置

| 阶段 | 前端 | API | Schema | Service | Model/Agent | PostgreSQL |
|---|---|---|---|---|---|---|
| 本文档 | 不经过 | 不经过 | 不经过 | 不经过 | 不经过 | 不经过 |
| M2完成态 | 聊天、上传、Evidence | 会话与知识问答 | Agent/Tool/Context | RAG与业务Service | Qwen＋Supervisor/Worker | 业务、文档、向量、Evidence、Trace |
| M4确认范围 | 研究任务、进度、结果 | 任务创建与状态 | 计划、Handoff、Web Evidence | Web Provider与Report Service | Supervisor＋Business/Knowledge/Web三类Worker | 父子Run、任务租约、Checkpoint、网络Evidence |
| M5 | 评估与演示展示 | 评估/诊断入口可选 | 评估样本合同 | Runner与指标 | Judge或真实模型评估 | 运行、指标和回归记录可选 |

## 12. 阶段完成标准

秋招主线完成时至少应满足：

1. M1与M2全部完成并有真实端到端证据；
2. M4不依赖M3，也不把某个商品和国家写死在Tool或Graph中；
3. 至少支持单外部查询、内外部核验和三来源综合研究三类任务；
4. 多Agent具有真实职责、权限、Handoff、父子Run和有界执行；
5. 所有关键结论能够关联数据库、文档或网页Evidence；
6. 评估报告包含真实路由、Tool、RAG、引用、安全、性能和成本数据；
7. README、架构图、演示视频和简历只描述已经完成并验证的能力；
8. 至少准备一个可复现Bad Case及修复前后对比。

## 13. 主要风险与排查方向

| 风险 | 可能表现 | 优先排查方向 |
|---|---|---|
| M4再次范围膨胀 | 同时增加过多Worker、Tool、Skill和输出 | 先冻结一个跨来源闭环，再逐项用真实需求增加能力 |
| Agent只是固定流程换名 | 换商品或任务后无法复用 | 检查Tool、Task和输出合同是否写死场景名 |
| Tool过于通用 | 任意SQL、任意浏览导致安全风险 | 使用通用但有边界的结构化参数和只读Provider |
| Tool过于碎片 | 模型调用次数、错误率和成本增加 | 以单一业务动作划分，稳定内部步骤保留在Service |
| 多Agent没有必要性 | 每个任务都启动全部Worker | 使用L0至L3复杂度和Capability驱动选择 |
| 网络来源不可靠 | 搜索摘要被直接当事实 | 保存来源、时间、正文证据、可信类型和冲突状态 |
| 评估被后置 | 功能完成但无法证明质量 | 每个M4能力先定义验收样本和失败条件 |
| 简历范围失真 | 描述多模态、13 Tool或5 Skill但未实现 | 以Git提交、评估报告和演示能力为唯一依据 |

## 14. 验证计划

本文档完成时只验证设计记录，不验证运行功能：

- 检查已确认结论和待确认事项明确分离；
- 检查M3状态仍符合统一状态枚举，且没有提前创建空M3目录；
- 检查M4已创建阶段入口与正式方案，但阶段状态仍为`待开始`且没有运行代码；
- 检查M4不再以M3为前置条件；
- 检查总体设计原始路线仍被保留并链接到本文；
- 检查总进度看板同步当前跨阶段决策；
- 检查Markdown链接、围栏和空白格式；
- 检查本次Git提交不包含密钥、运行产物或代码改动。

这些检查能够证明范围讨论被准确记录并可追踪，不能证明M2剩余功能、M4联网研究或M5评估已经实现。

## 15. 下一动作

当前先向用户讲清整个M2-21；用户确认理解后，仍需单独授权M2-21.1。M2每个小步骤继续独立开发和验证。

M4推荐版正式方案已经确认，但阶段仍为`待开始`。M2收口后先按M2实际合同复核M4-01输入输出，再向用户申请单步授权；在此之前不创建M4运行代码、不新增Tavily Tool，也不修改简历声称M4已经完成。
