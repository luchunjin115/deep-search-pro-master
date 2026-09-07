# M4：通用有界深度研究与报告

> 阶段状态：待开始
> 方案状态：推荐版正式方案已确认
> 确认日期：2026-09-03
> 当前开发授权：只完成阶段文档，不授权开始M4运行代码
> 前置阶段：M2完成；M3多模态不是前置条件

## 1. 当前状态

| 项目 | 当前内容 |
|---|---|
| 当前阶段 | 项目仍在M2，M4尚未开始实现 |
| M4定位 | 企业数据库＋内部RAG＋公开互联网的通用有界深度研究 |
| 已确认范围 | 推荐版：三类Evidence、Web Research Worker、有界并行、父子Run、PostgreSQL Checkpoint、Markdown和一个研究Skill |
| 当前已具备 | M1数据库Tool与Evidence；M2-01至M2-20知识检索、文件读取和Evidence能力 |
| 仍依赖 | M2-21至M2-24完成Supervisor、Business Data/Knowledge Worker、统一Runtime、API、前端和评估闭环 |
| 当前未具备 | Web Provider、Web Tool、Web Research Worker、Web Evidence处理、M4任务与前端 |
| 下一动作 | 继续完成M2；M2收口后单独确认是否开始M4-01，不自动开发 |

## 2. 当前有效范围

M4首版复用M2的Supervisor、Business Data Worker、Knowledge Worker、统一Answer Provider与Citation Validator，只新增Web Research Worker。模型负责规划、选择和有证据的总结；联网、正文处理、固定计算和Markdown格式化由受控Tool、Provider与Service执行。

```text
Supervisor
├─ Business Data Worker：企业数据库Evidence
├─ Knowledge Worker：内部文档Evidence
└─ Web Research Worker：公开互联网Evidence
       ├─ search_public_web：发现候选来源
       └─ read_public_source：读取本次搜索发现的受控来源
```

首版不把Analysis和Report独立成Worker：固定计算放入Analysis Service，统一Answer Provider在Supervisor控制下基于三类Evidence完成内容合成与引用，Report Service只做确定性Markdown章节和格式组织。只有后续出现独立目标、上下文、工具权限和完成判断时，才另行提案升级为Worker。

## 3. 已确认决策

| 决策 | 结论 |
|---|---|
| 范围档位 | 推荐版 |
| 新增Agent | 只新增Web Research Worker |
| 分析与报告 | 首版使用确定性Service，不新增Analysis/Report Worker |
| 互联网搜索 | `search_public_web` → Service → Provider → Tavily API |
| 网页正文 | `read_public_source`只读取同一Run中已搜索发现并获准的来源，不接受任意URL |
| Provider | Fake用于日常回归；Tavily用于显式真实Smoke |
| MCP | V1不引入；未来可在Provider后替换适配，不改变Tool合同 |
| 长网页 | 去重、分类、清洗、有界切分、相关片段选择；完整正文不直接塞入模型上下文 |
| 调度 | 先顺序验证，再增加独立只读Worker有界并行 |
| 恢复 | PostgreSQL父子Run、任务状态、租约和Checkpoint是M4完成条件 |
| 长任务基础设施 | 首版不引入Redis/Celery；使用应用内有界执行器与PostgreSQL持久状态 |
| 前端进度 | 通过任务状态API轮询；SSE可后续按真实体验需求评估 |
| 统一编排 | 聊天中发起研究仍经过M2 Agent Gateway；研究任务API只管理task_id生命周期并复用同一Supervisor，不建立第二套Planner |
| 输出 | 简答、Evidence摘要、核验、对比、Markdown研究备忘录/报告 |
| PDF | 首版不做 |
| Skill | 一个通用的`cross-border-market-research`，不写死商品或国家 |
| Golden Scenario | 德国/法国蘑菇灯综合研究只作为验收样本，不作为执行逻辑 |

## 4. 明确不做

- 不恢复M3图片、OCR、视觉Schema和相似SKU范围；
- 不实现供应商报价、任意经营指标、Pandas复杂分析或图表；
- 不生成PDF；
- 不新增独立Analysis Worker或Report Worker；
- 不允许任意SQL、任意HTTP、任意URL读取或通用浏览器控制；
- 不绕过登录、付费墙、robots或网站访问限制；
- 不引入MCP、Redis、Celery、MinIO、真实Amazon SP-API或ERP；
- 不实现写库存、下单、改价格、发邮件或发布商品；
- 不承诺法律、医疗或金融高风险结论；
- 不允许无限搜索、无限递归、无限Worker或无终止条件的自主运行。

## 5. 步骤索引

| 步骤 | 状态 | 单一目标 | 过程记录 |
|---|---|---|---|
| M4-00 | 已完成 | 冻结推荐版阶段方案和授权边界 | [正式阶段方案](records/M4_00_STAGE_PLAN.md) |
| M4-01 | 待开始 | 冻结研究请求、Web搜索、来源读取、Web Evidence和输出合同 | 后续创建 |
| M4-02 | 待开始 | 建立Web Provider接口与确定性Fake | 后续创建 |
| M4-03 | 待开始 | 实现`search_public_web` Service/Tool与Harness接入 | 后续创建 |
| M4-04 | 待开始 | 实现受控`read_public_source`与长网页Evidence管线 | 后续创建 |
| M4-05 | 待开始 | 实现Web Research Worker和单Web事实查询 | 后续创建 |
| M4-06 | 待开始 | 跑通Knowledge＋Web及三来源顺序协作 | 后续创建 |
| M4-07 | 待开始 | 实现PostgreSQL任务、租约、Checkpoint和有界并行恢复 | 后续创建 |
| M4-08 | 待开始 | 实现`cross-border-market-research` Skill与Markdown Service | 后续创建 |
| M4-09 | 待开始 | 实现研究任务API与前端进度、结果、Evidence展示 | 后续创建 |
| M4-10 | 待开始 | 接入真实Tavily并完成质量、安全、成本、故障和端到端验收 | 后续创建 |

每一步开始前都必须说明输入、输出、上下游关系和验证方法，并获得用户对该步的单独授权。M4-00确认不自动授权M4-01。

## 6. 完整调用链位置

M4目标链路为：

```text
前端研究任务/进度/结果
→ FastAPI任务创建与状态API
→ 研究请求、计划、Handoff、Web Evidence和输出Schema
→ Supervisor / Web Research Worker / LangGraph
→ Harness权限、白名单、预算、超时、重试、Trace
→ search_public_web / read_public_source
→ WebSearchService / PublicSourceReadingService
→ Fake或Tavily Provider
→ 公开互联网
→ Web Evidence / Observation
→ PostgreSQL父子Run、任务、Checkpoint和Evidence
→ Supervisor＋统一Answer Provider＋Citation Validator
→ Report Service确定性Markdown格式化
→ Markdown与前端Evidence展示
```

当前M4-00只经过文档方案层，尚未经过上述任何运行层。

## 7. 验证基线

M4开始前必须以M2最终收口基线为准重新记录。当前只能确认：

- M1已完成数据库查询垂直切片；
- M2-01至M2-20已完成知识与文件Evidence底座；
- M2-21至M2-24仍未完成，因此M4运行前置条件尚未满足；
- 仓库尚无M4 Web Provider、Tool、Worker、API或前端实现；
- 本次只验证方案文档的一致性，不能证明真实联网、网页读取、并行恢复或研究质量。

## 8. 主要风险

| 风险 | 优先排查方向 |
|---|---|
| 搜索摘要被误当作正文事实 | 分离搜索与读取，关键主张必须绑定正文Web Evidence |
| 网页又长又杂导致上下文膨胀 | 检查结果上限、正文清洗、切分、相关片段和Context预算 |
| 网页Prompt Injection | 网页按不可信数据处理，检查Tool权限与结构化Observation边界 |
| 重复转载被当成多份独立证据 | 检查规范URL、内容Hash、原始来源和去重规则 |
| 新旧网页或不同市场来源冲突 | 检查时间、地区、口径和来源类型，无法消除时显式标记冲突 |
| Tavily超时、限流或无额度 | 检查错误分类、有限重试、预算扣减和partial/可恢复失败 |
| 三Worker并行污染状态 | 检查独立Session、子Run、原子预算、稳定合并和租约 |
| M4再次膨胀 | 先守住三类Evidence闭环，不顺手加入PDF、图表、MCP或更多Worker |

## 9. 阶段完成标准

M4只有同时满足以下条件才能标记为已完成：

1. 单Web公开事实查询、Knowledge＋Web核验和Business＋Knowledge＋Web综合研究均通过；
2. `search_public_web`与`read_public_source`都受Harness权限、预算、超时和Trace控制；
3. 关键网络结论基于正文Web Evidence，而不是只引用搜索摘要；
4. 三类Evidence能够重新获权、去重、编号并映射到最终结论；
5. 顺序执行通过，独立只读Worker有界并行通过；
6. PostgreSQL父子Run、任务、租约和Checkpoint可以恢复受控任务；
7. `cross-border-market-research`不写死商品、国家或Golden Prompt；
8. 前端能够查看任务进度、部分失败、Markdown结果和三类Evidence；
9. Fake日常回归、真实PostgreSQL矩阵、显式Tavily/Qwen Smoke与Chromium端到端均有记录；
10. Tavily故障、网页注入、重复来源、来源冲突、预算和权限测试通过；
11. 德法蘑菇灯Golden Scenario和至少两个不同任务形态通过；
12. 文档、演示和简历只描述实际实现并验证的能力。

## 10. 下一动作

继续当前M2主线。M2收口后，应先读取本入口和[M4正式阶段方案](records/M4_00_STAGE_PLAN.md)，核对M2最终合同与文件结构，再向用户提交M4-01单步实施说明。没有新的明确授权，不创建M4运行代码。
