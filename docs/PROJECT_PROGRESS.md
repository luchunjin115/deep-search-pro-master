# 项目总进度看板

> 本文档是项目进度的统一入口，只保存当前状态、里程碑摘要、跨阶段决策、阻塞项和阶段链接。
> 详细方案、逐步日志和完整验证结果保存在 `docs/progress/` 对应阶段记录中。
> 状态枚举：待确认、待开始、进行中、受阻、已完成。
> 最近更新：2026-09-02

## 1. 当前状态

| 项目 | 当前内容 |
|---|---|
| 当前阶段 | M2：知识库垂直切片 |
| 阶段状态 | 进行中 |
| 已完成到 | M1已完成；M2-01至M2-20已完成并验证，M2-20已收口 |
| 当前停止点 | 两个受控读取Tool的真实权限/范围/故障矩阵已完成；M2-21方案尚未确认 |
| 下一动作 | 与用户讨论并确认M2-21有界知识路由、LangGraph和基于Evidence回答方案，不自动编码 |
| 尚未具备 | M2-21至M2-24、HTTP知识检索API、知识Agent/LangGraph、Qwen基于Evidence回答和前端知识问答 |
| 当前阻塞 | 无技术硬阻塞；Reranker CPU延迟、图文DOCX定位和既有测试时间依赖属于已知风险 |

## 2. 里程碑总览

| 里程碑 | 内容 | 状态 | 详细记录 |
|---|---|---|---|
| M0 | 产品、技术、数据、评估与协作基线 | 已完成 | [M0详细记录](progress/M0_DESIGN.md) |
| M1 | 库存查询垂直切片 | 已完成 | [M1当前入口](progress/M1/M1_INVENTORY_QUERY.md) |
| M2 | 自建RAG垂直切片 | 进行中 | [M2当前入口](progress/M2/M2_KNOWLEDGE_RAG.md) |
| M3 | 多模态商品分析 | 待开始 | 等待M2完成 |
| M4 | 深度研究与报告 | 待开始 | 等待M3完成 |
| M5 | 评估、加固与作品化 | 待开始 | 等待M4完成 |

M2 的完整历史方案、步骤日志和验证证据位于 [`progress/M2/records/`](progress/M2/records/)；新窗口默认只读取 M2 当前入口，开始具体任务时再按需读取对应过程记录。

## 3. 已确认的跨项目决策

| 决策 | 结论 |
|---|---|
| 大模型 | 千问负责主推理和多模态理解 |
| Agent编排 | LangGraph |
| 业务数据库 | PostgreSQL |
| 向量存储 | pgvector |
| Embedding / Reranker | BGE-M3 / BGE-Reranker |
| RAG | 项目自行实现，不依赖RAGFlow |
| 互联网搜索 | Tavily自定义Tool |
| V1文件存储 | 本地文件系统 + Storage抽象，不部署MinIO |
| 数据 | 明确标注的版本化合成演示数据 |
| Tool权限 | 单个Agent或Skill只获得1至5个允许Tool，模型不能直接访问数据库 |
| Harness | 统一负责上下文、权限、白名单、预算、超时重试、审计、证据和评估钩子 |
| MCP | V1不引入；连接真实外部系统或向外部客户端复用时再评估 |
| 开发方式 | 教学式协作、阶段方案先确认、一次完成一个可验证小步骤 |
| 阶段文档结构 | M1及以后统一使用`docs/progress/M{编号}/`，阶段短入口与`records/`过程记录分离；新窗口按当前任务读取，不默认加载全部历史 |

M2 专属的解析、分块、索引、检索、Reranker、Context和Evidence决策不在总看板重复展开，统一以 [M2入口](progress/M2/M2_KNOWLEDGE_RAG.md) 和对应过程记录为准。

## 4. 当前验证基线

M2-20.6 收口时：

- M2-20聚焦合同、Service、Tool和真实矩阵`93 passed`，M1/M2相邻回归`233 passed`；
- 排除既有跨月测试后`949 passed, 2 skipped, 1 deselected`；
- 默认全量`949 passed, 10 skipped, 1 failed`，唯一失败仍是既有上传Key写死月份的时间依赖用例；
- Ruff、253文件格式、120个`app`源文件Mypy、编译、依赖和Alembic门禁通过；
- Alembic继续为`20260902_0010 (head)`且无漂移，本步没有新增迁移；
- 正式Seed恢复为10 files、10 documents、10 versions、9 ACL，索引、Context、Evidence、ToolContextLink、AgentRun和ToolCall均为0；
- Storage只有10个uploads，M1德国仓可售库存仍为125。

完整命令、逐项结果、能证明和不能证明的边界见 [M2-20过程记录](progress/M2/records/M2_20_FILE_EVIDENCE_TOOLS.md)。

## 5. 当前风险与跨阶段问题

| 风险 | 影响 | 当前处理方向 |
|---|---|---|
| Reranker本机CPU p95约7.24秒 | 不适合未经优化直接进入低延迟同步链 | 后续评估候选裁剪、GPU、批处理或检索路由 |
| 图文DOCX事实级定位不足 | 图片文字可能无法形成可核验Evidence | 继续作为解析上游边界记录，不伪造召回成功 |
| 既有跨月硬编码测试 | 默认全量测试随月份变化失败 | 后续单独修复测试时间依赖，不放宽生产规则 |
| 固定UUID数据库夹具存在顺序耦合 | 人工改变测试顺序可能产生污染 | 后续加固测试隔离和唯一数据身份 |

当前没有阻止M2-21方案讨论的技术硬阻塞；三跳Tool预算与真实Reranker延迟需要在方案中明确处理。

## 6. 最近完成摘要

- 2026-09-02：完成M2-20.6真实权限/范围/故障矩阵并收口M2-20；两个读取Tool在同一真实Harness下覆盖三角色、五授权路径、撤权、软删除、旧代次、解析/locator、Storage/Artifact、数据库故障和Trace脱敏。没有修改生产代码，没有开始M2-21、API、Agent、Qwen或前端。
- 2026-09-02：完成M2-20.5 `GetEvidenceDetailTool`与Harness接入；精确绑定M2 Registry和可信身份，通过角色、重复预算、3000ms超时与Trace门禁，核对Service结果Evidence ID且成功Envelope只携带该ID。没有开始M2-20.6、API、Agent、Qwen或前端。
- 2026-09-02：完成M2-20.4统一Evidence详情Service；保留M1数据库Evidence与HTTP行为，新增文档Evidence按Context请求者、当前ACL/软删除/active代次和完整Chunk来源重新验证，失败统一隐藏。没有创建`GetEvidenceDetailTool`或开始M2-20.5。
- 2026-09-02：完成M2-20.3 `ReadUploadedFileTool`与Harness接入；执行前精确绑定M2 Registry和可信身份，通过角色、重复预算、3000ms超时与Trace门禁，结果核对公开file ID且成功Envelope不伪造Evidence。没有开始Evidence详情Service/Tool或M2-20.4。
- 2026-09-02：完成M2-20.2安全解析产物读取Service；可信`CurrentUser`通过一次性SQL重新获权，Service有界加载并复核Routed/Canonical Artifact、Storage Key与双重源Hash，按四格式locator返回最多8000字符的公开结果。没有创建执行Tool、接入Harness、生成Evidence或开始M2-20.3。
- 2026-09-02：M2-20完整方案和推荐决策已确认；完成M2-20.1四格式有界文件读取合同、统一Evidence详情合同、公开导出及M1两Tool/M2五Tool隔离Registry。没有创建执行Service/Tool、API、Agent、Qwen或前端。
- 2026-09-02：完成M2-19.5真实权限/故障矩阵与阶段收口；owner/company owner/user/role/market ACL、跨tenant/旧代次/软删除排除、跨ToolCall复用、撤权竞态、预算/超时和持久化原子故障均通过。M2-19整体已完成，没有开始M2-20、API、Agent、Qwen或前端。
- 2026-09-02：完成M2-19.4 `SearchKnowledgeTool`与Harness接入，验证可信身份、权限、预算、超时、Trace、Envelope和真实Tool-Context关联；修正ToolCall读取锁与Harness状态回写互锁。
- 2026-09-02：完成M2-19.3 `KnowledgeSearchService`，固定串联Reranker/Hybrid、Context Builder和Evidence原子持久化，并用真实PostgreSQL验证撤权、active切代和回滚。
- 2026-09-02：完成M2-19.2 ToolCall-Context审计关联、0010安全迁移及Document Evidence可复用归一化；M1 database Evidence保持直连。
- 2026-09-02：M2-19完整方案和推荐决策已确认；完成M2-19.1严格query/Context合同、12条Evidence上限及M1两Tool/M2三Tool隔离Registry。
- 2026-09-01：完成M1进度文档治理；M1入口与过程记录分离，历史正文完整性、链接和步骤覆盖验证通过，必读入口体积减少约95.8%。
- 2026-09-01：完成M2进度文档治理；M2入口与过程记录分离，历史正文完整性、链接和步骤覆盖验证通过，必读入口体积减少97.6%。
- 2026-08-29：M1库存查询垂直切片完成，公开演示、API、前端和Chromium整链通过；详细日志见M1记录。
- 2026-08-29至2026-08-31：完成M2-01至M2-15，建立上传、解析、分块、Embedding和幂等索引闭环。
- 2026-09-01：完成M2-16，建立权限前置的Dense、Lexical、Hybrid和RRF检索闭环。
- 2026-09-01：完成M2-17，真实BGE-Reranker提高正式Golden Recall@8，但记录了CPU延迟和内存成本。
- 2026-09-01：完成M2-18，建立Context、文档Evidence、原子幂等持久化和当前权限下的严格引用验证。

更早的逐步完成记录不在总看板重复保存，统一进入对应阶段详细记录。
