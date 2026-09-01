# M1：库存查询垂直切片

> 本文件是 M1 的唯一必读入口，只保存最终状态、关键决策、步骤索引、验证基线和按需阅读指引。
> 完整方案、实施日志和验证证据保存在 [`records/`](records/) 中。
> 阶段完成日期：2026-08-29

## 1. 最终状态

| 项目 | 最终内容 |
|---|---|
| 阶段状态 | 已完成 |
| 完成范围 | M1-01 至 M1-21全部实现并验证 |
| 核心结果 | 登录用户可以用自然语言查询德国仓蘑菇灯库存，得到可售125、数据时间、数据库Evidence和审计轨迹 |
| 数据性质 | 全部业务数据为`m1-v1`合成演示数据，不代表真实Amazon经营数据 |
| 当前关系 | M1是当前M2知识库垂直切片复用的认证、权限、Harness、Trace、聊天和Evidence地基 |
| M1后续动作 | 无；除非M2修改导致M1验证失效，否则只做回归和必要修复 |

M1已经完成，不因为阅读本文件而重新进入M1开发。项目当前状态和下一动作以 [`docs/PROJECT_PROGRESS.md`](../../PROJECT_PROGRESS.md) 为准。

## 2. 新窗口阅读顺序

1. 必读 `docs/PROJECT_PROGRESS.md`，确认当前里程碑和跨阶段问题；
2. 只有任务涉及M1能力或M1回归时才读本入口；
3. 根据第3节选择与当前代码直接相关的过程记录；
4. 排查跨层问题时沿第5节调用链逐层扩展，不默认加载全部M1历史；
5. 代码事实与记录冲突时，以当前代码、迁移和实际验证为准，并同步修正文档。

例如修改库存Tool权限时，优先读取`M1_12_15_SECURITY_HARNESS_TOOLS.md`，再按需要读取库存核心记录；无需默认读取前端和空卷复现日志。

## 3. M1过程记录目录

| 范围 | 内容 | 何时读取 |
|---|---|---|
| [M1_DOCUMENT_GOVERNANCE.md](records/M1_DOCUMENT_GOVERNANCE.md) | M1文档拆分、完整性验证和维护规则 | 排查文档结构或链接时 |
| [M1_00_STAGE_PLAN.md](records/M1_00_STAGE_PLAN.md) | 原始阶段方案、术语、总体设计、21步计划、验证矩阵和风险 | 核对M1原始范围或总体设计时 |
| [M1_01_06_FOUNDATION.md](records/M1_01_06_FOUNDATION.md) | 配置、PostgreSQL、SQLAlchemy事务、身份/库存/审计模型和迁移 | 修改配置、数据库基础或ORM时 |
| [M1_07_11_INVENTORY_CORE.md](records/M1_07_11_INVENTORY_CORE.md) | 合成Seed、Schema、Repository、规格/库存Service和数据库Evidence | 修改库存业务、数据合同或查询时 |
| [M1_12_15_SECURITY_HARNESS_TOOLS.md](records/M1_12_15_SECURITY_HARNESS_TOOLS.md) | 登录、JWT、RunContext、PermissionGuard、Budget、Trace和两个Agent Tool | 修改认证、权限、Harness或Tool时 |
| [M1_16_17_MODEL_AND_GRAPH.md](records/M1_16_17_MODEL_AND_GRAPH.md) | Mock/Qwen Provider边界和五节点LangGraph库存流程 | 修改模型建议、图状态或流程编排时 |
| [M1_18_19_API_AND_FRONTEND.md](records/M1_18_19_API_AND_FRONTEND.md) | FastAPI公开接口和Next.js登录/证据聊天页 | 修改API合同或M1前端时 |
| [M1_20_21_ACCEPTANCE.md](records/M1_20_21_ACCEPTANCE.md) | 故障矩阵、Chromium回归、公开演示、空卷复现和阶段收口 | 做整链回归、演示或环境恢复时 |

这些记录是正式完成证据，不是可删除的临时归档。

## 4. M1目标与范围边界

M1只证明一个垂直闭环：Amazon运营人员登录后，用自然语言查询德国仓蘑菇灯库存；系统在租户、角色、市场、Tool白名单和执行预算约束下查询PostgreSQL，并返回答案、数据时间、数据库Evidence和审计轨迹。

M1明确没有实现：

- 文件上传、RAG、pgvector、Embedding和Reranker；
- 多模态商品分析、互联网深度研究和Tavily；
- Redis、Celery、SSE、MCP或生产分布式任务；
- 真实Amazon SP-API或真实企业数据；
- 高并发、跨区域部署、灾难恢复或完整商业前端。

## 5. 最终调用链

```text
Next.js页面或公开演示脚本
→ FastAPI认证 / 会话 / 聊天 / Evidence API
→ Pydantic Schema
→ JWT身份刷新 + CurrentUser / RunContext
→ LangGraph五节点库存流程
→ Mock或Qwen Provider提出受控Tool建议
→ Harness预算、权限、白名单与Trace
→ get_product_spec / search_inventory
→ 商品规格Service / 库存与Evidence Service
→ Repository + SQLAlchemy Model
→ PostgreSQL合成Seed
→ 回答、数据时间、Evidence和审计结果
```

模型只能提出当前白名单内的Tool调用建议，不能执行Tool或直接访问数据库。LangGraph和Harness审核后由后端调用确定性Service与Repository。

## 6. M1-01至M1-21状态索引

| 步骤 | 状态 | 结果摘要 | 详细记录 |
|---|---|---|---|
| M1-01 | 已完成 | 新目录、集中配置和依赖边界 | [基础记录](records/M1_01_06_FOUNDATION.md) |
| M1-02 | 已完成 | PostgreSQL 17容器、健康检查和持久化卷 | [基础记录](records/M1_01_06_FOUNDATION.md) |
| M1-03 | 已完成 | SQLAlchemy连接和请求事务边界 | [基础记录](records/M1_01_06_FOUNDATION.md) |
| M1-04 | 已完成 | 租户、用户、角色和市场模型及迁移 | [基础记录](records/M1_01_06_FOUNDATION.md) |
| M1-05 | 已完成 | 商品、SKU、仓库和库存模型及迁移 | [基础记录](records/M1_01_06_FOUNDATION.md) |
| M1-06 | 已完成 | 会话、运行、Tool审计和Evidence模型 | [基础记录](records/M1_01_06_FOUNDATION.md) |
| M1-07 | 已完成 | `m1-v1`可重复合成演示数据 | [库存核心](records/M1_07_11_INVENTORY_CORE.md) |
| M1-08 | 已完成 | Pydantic输入、输出和错误合同 | [库存核心](records/M1_07_11_INVENTORY_CORE.md) |
| M1-09 | 已完成 | 受控商品和库存Repository | [库存核心](records/M1_07_11_INVENTORY_CORE.md) |
| M1-10 | 已完成 | 商品规格Service | [库存核心](records/M1_07_11_INVENTORY_CORE.md) |
| M1-11 | 已完成 | 库存查询与数据库Evidence Service | [库存核心](records/M1_07_11_INVENTORY_CORE.md) |
| M1-12 | 已完成 | 登录、JWT和RunContext | [安全与Tool](records/M1_12_15_SECURITY_HARNESS_TOOLS.md) |
| M1-13 | 已完成 | ToolRegistry和PermissionGuard | [安全与Tool](records/M1_12_15_SECURITY_HARNESS_TOOLS.md) |
| M1-14 | 已完成 | ExecutionBudget、Trace和Harness执行外壳 | [安全与Tool](records/M1_12_15_SECURITY_HARNESS_TOOLS.md) |
| M1-15 | 已完成 | 两个正式Agent Tool | [安全与Tool](records/M1_12_15_SECURITY_HARNESS_TOOLS.md) |
| M1-16 | 已完成 | Mock/Qwen Provider和受控Tool建议边界 | [模型与Graph](records/M1_16_17_MODEL_AND_GRAPH.md) |
| M1-17 | 已完成 | 五节点LangGraph库存流程 | [模型与Graph](records/M1_16_17_MODEL_AND_GRAPH.md) |
| M1-18 | 已完成 | FastAPI登录、会话、聊天和Evidence接口 | [API与前端](records/M1_18_19_API_AND_FRONTEND.md) |
| M1-19 | 已完成 | Next.js登录和证据聊天页 | [API与前端](records/M1_18_19_API_AND_FRONTEND.md) |
| M1-20 | 已完成 | 故障矩阵、API集成和Chromium端到端回归 | [验收记录](records/M1_20_21_ACCEPTANCE.md) |
| M1-21 | 已完成 | 演示脚本、空卷复现和阶段收口 | [验收记录](records/M1_20_21_ACCEPTANCE.md) |

## 7. 仍然有效的关键决策

- 库存公式固定为`available = on_hand - reserved - damaged`，演示关键答案为DE-FRA可售125；
- tenant、用户、角色和市场范围只来自后端可信身份，不接受模型或请求参数伪造；
- Repository只实现固定业务查询，不接受模型生成SQL、表名、排序或任意过滤条件；
- Agent Tool只有`get_product_spec`和`search_inventory`，均通过统一Harness执行；
- 明确SKU路径最多一次模型建议和一次Tool，商品名称路径最多两轮建议和两次Tool；
- PermissionGuard、ExecutionBudget、重复签名、超时和Trace均由服务端确定性执行，不依赖Prompt自律；
- 成功库存回答必须绑定数据库Evidence，Evidence按当前用户和市场范围授权读取；
- 默认回归使用确定性Mock；真实Qwen付费冒烟必须显式开启；
- HTTP使用同步请求，M1不引入SSE；Redis和Celery保持后置；
- 所有演示数据必须明确标注为合成数据。

## 8. 最终验证基线

M1-21收口时的实际结果：

- 后端全量`175 passed`，1项真实Qwen付费冒烟按设计跳过；
- Ruff检查通过，97个Python文件格式正确；
- Mypy对64个`app/scripts`源文件通过；Python编译和`pip check`通过；
- 前端组件测试4项通过，TypeScript、ESLint和Next.js生产构建通过；
- Playwright Chromium真实端到端4项通过；
- `npm audit --audit-level=high`为0个漏洞；
- 从全新`deep-search-postgres-data`卷完成三次迁移、Seed、公开API演示、清理、停止和重启；
- Alembic恢复为`20260828_0003 (head)`，四个演示用户存在，运行数据清理为0；
- `LR-TL-MUSH-OR01 / DE-FRA`可售库存为125；
- 公开演示实际验证DE成功查询和Evidence、FR查询DE市场返回403。

这些结果是M1完成时的基线。M2后续已经增加迁移和Evidence能力，因此需要判断M1是否回归时，应以当前代码上的最新M1回归结果为准，不能只引用旧的`0003`迁移状态。

## 9. 能证明、不能证明与排查

### 9.1 能证明

- 在记录的Windows、Python 3.11、Node 24、Docker、PostgreSQL 17和Chromium环境中，M1曾从空数据卷完整恢复并重复演示；
- 公开演示经过真实API和PostgreSQL，不在脚本或前端伪造125；
- 成功回答、Evidence、审计轨迹和权限拒绝形成了最小完整闭环；
- M1-01至M1-21均有实施和实际验证记录。

### 9.2 不能证明

- 真实Qwen对所有表达长期稳定；
- 高并发、跨区域部署、灾难恢复、全部浏览器或移动端商业体验；
- 数据来自真实Amazon或公司系统；
- RAG、pgvector、BGE、多模态、深度研究或M2以后能力在M1已经存在；
- M1完成时的所有验证数字自动适用于后续任意代码版本。

### 9.3 常见问题与优先排查

| 现象 | 优先排查方向 |
|---|---|
| 登录失败 | Seed、演示账号、密码Hash、JWT配置和用户启用状态 |
| 回答不是125 | `m1-v1` Seed、DE-FRA最新库存快照、库存公式和是否误启真实模型 |
| FR账号能查DE | CurrentUser市场范围、PermissionGuard和库存Tool可信参数 |
| 有答案但没有Evidence | 库存Service事务、Evidence写入、AgentRun/ToolCall关联 |
| 模型调用次数异常 | LangGraph节点、预算、重复签名和Provider响应合同 |
| 演示访问本机返回502 | Windows系统代理和本地HTTP客户端`trust_env`边界 |
| 浏览器链失败 | 前端环境变量、API/CORS、PostgreSQL健康和Playwright启动/清理 |

## 10. 维护规则

- M1入口只在最终状态、有效决策、风险或与后续阶段关系变化时更新；
- M1回归或修复的完整日志写入对应`records/`文件，入口只保留最新有效摘要；
- M2及以后不得把自己的逐步日志追加到M1记录；
- 后续代码变化使旧结论失效时，必须在相关过程记录和入口中注明；
- 未实际重新运行的验证不能写成“当前仍通过”。
