# 跨境电商多 Agent 智能分析平台——数据库、模拟数据、评估与实施计划

> 文档状态：已确认
> 版本：V1.1
> 数据性质：全部业务数据为演示合成数据，不代表真实Amazon经营结果
> 实施原则：先完成可演示的垂直链路，再扩展覆盖面

> 2026-09-04范围调整说明：本文件的业务数据与评估方法继续有效，但原始完整版里程碑和数量目标已被当前秋招主线取代。当前先完成M2多Agent/RAG闭环，M3多模态暂缓，M4推荐版已确认只新增Web Research Worker与一个研究Skill，M5保留评估、加固和作品化；冲突处以[`05_Autumn_Recruitment_Scope_Adjustment_Plan.md`](05_Autumn_Recruitment_Scope_Adjustment_Plan.md)、[M2入口](../progress/M2/M2_KNOWLEDGE_RAG.md)和[M4入口](../progress/M4/M4_DEEP_RESEARCH.md)为准。

> 后续已记录但尚未实施的“公开商品字段 + 合成运营字段”扩充与跨电脑恢复方案，见 [04_Public_Dataset_Expansion_and_Migration_Plan.md](04_Public_Dataset_Expansion_and_Migration_Plan.md)。在该方案完成正式确认和验证前，本文件的现有合成数据基线继续有效。

## 1. 文档目的

本文档确定：

- 模拟公司的业务背景；
- PostgreSQL数据域与核心表；
- 合成数据生成规则；
- RAG、Agent、多模态和安全评估方法；
- 从现有原型到可写入简历项目的最快实施顺序。

## 2. 模拟公司设定

### 2.1 公司档案

| 字段 | 设定 |
|---|---|
| 公司名称 | 澄屿家居跨境有限公司（虚构演示公司） |
| 英文名称 | ClearIsle Home Commerce Demo |
| 品牌 | LUMORIVA HOME（虚构演示品牌） |
| 团队规模 | 12人 |
| 业务类型 | 中国采购、欧洲跨境家居零售 |
| 主要渠道 | Amazon（模拟） |
| 目标市场 | 德国、法国 |
| 结算币种 | EUR，采购以CNY为主 |
| 数据周期 | 2025-09-01至2026-08-31 |

名称必须在所有页面和报告中带“演示”标记，避免被误认为真实公司、品牌或经营数据。

### 2.2 团队角色

- 公司负责人：2人；
- 选品与采购：4人；
- 德国Amazon运营：3人；
- 法国Amazon运营：2人；
- 管理员/数据维护：1人。

系统只实现三种产品角色，管理员作为负责人角色的权限扩展。

### 2.3 产品线与24个SKU

| 产品线 | SKU数量 | 示例 |
|---|---:|---|
| 装饰照明 | 8 | 台灯、落地灯、壁灯 |
| 小型边桌 | 5 | 边几、床头桌、茶几 |
| 收纳家具 | 6 | 置物架、收纳柜、鞋架 |
| 家居装饰 | 5 | 花瓶、托盘、镜子 |

重点新品：

```text
SKU候选编码：LR-TL-MUSH-OR01
名称：LUMORIVA Orange Mushroom Table Lamp
中文：橙色复古蘑菇台灯
状态：候选新品，尚未产生真实销售
主要属性：约30cm高、约20cm灯罩宽、约12cm底座宽、橙色玻璃外观、金属底座、LED、三档开关
```

图中或供应商资料无法确认的属性必须标记为待核验，不能因为演示图片上有英文文案就直接写成已认证事实。

### 2.4 供应商与仓库

供应商：10家虚构供应商，其中：

- 灯具及电气类4家；
- 木制与金属家具3家；
- 家居装饰2家；
- 包装材料1家。

仓库：

| 编码 | 名称 | 类型 |
|---|---|---|
| CN-NGB | 宁波集货仓 | 国内仓 |
| DE-FRA | 德国法兰克福海外仓 | 海外仓 |
| FR-CDG | 法国巴黎地区海外仓 | 海外仓 |

## 3. 数据域划分

```text
身份与权限域
├─ 租户、用户、角色、权限

商品与供应链域
├─ 产品、SKU、规格、供应商、报价、采购、仓库、库存

Amazon经营模拟域
├─ 市场、Listing、销售、广告、退货、费用、竞品快照

知识与文件域
├─ 文件、文档版本、分块、向量、文档权限

Agent运行域
├─ 会话、消息、任务、步骤、工具调用、Checkpoint

证据与报告域
├─ Evidence、结论引用、报告、图表、用户反馈

评估域
└─ 数据集、运行、样本结果、指标、版本对比
```

## 4. PostgreSQL核心表

### 4.1 身份与权限

#### tenants

| 字段 | 类型 | 说明 |
|---|---|---|
| id | uuid | 租户ID |
| name | varchar | 公司名称 |
| is_demo | boolean | 是否演示租户 |
| created_at | timestamptz | 创建时间 |

#### users

| 字段 | 类型 | 说明 |
|---|---|---|
| id | uuid | 用户ID |
| tenant_id | uuid | 所属公司 |
| email | varchar | 登录邮箱 |
| display_name | varchar | 显示名 |
| password_hash | varchar | 密码哈希 |
| status | varchar | active/disabled |

#### roles、permissions、user_roles、role_permissions

角色与权限分离。权限粒度至少覆盖：业务域、市场范围、敏感成本字段、知识库管理和系统管理。

### 4.2 商品与供应链

核心表：

| 表 | 作用 |
|---|---|
| products | SPU级产品 |
| product_variants | SKU、颜色、尺寸、状态 |
| product_specs | 电压、材质、尺寸、重量等可扩展规格 |
| suppliers | 供应商基本信息 |
| supplier_products | 供应商与SKU关系、MOQ、交期 |
| supplier_quotes | 币种、含税价、有效期、报价版本 |
| warehouses | 仓库与国家 |
| inventory_snapshots | 每日库存快照 |
| inventory_movements | 入库、出库、调拨、报损、退货 |
| purchase_orders | 采购单头 |
| purchase_order_items | SKU、数量、单价和入库状态 |

`product_specs`中每个值保存 `value`、`unit`、`source_type`、`source_id` 和 `verification_status`，用于区分供应商声明、图片观察和已核验证据。

### 4.3 Amazon经营模拟

| 表 | 作用 |
|---|---|
| markets | DE、FR市场、币种和时区 |
| listings | 模拟ASIN、标题、Bullet、价格、状态 |
| sales_daily | SKU/市场每日订单、销量、销售额 |
| fees_daily | 佣金、仓储、配送等模拟费用 |
| ad_performance_daily | 曝光、点击、花费、广告销售 |
| returns_daily | 退货数量和原因 |
| keyword_snapshots | 关键词、语言、模拟排名和采集时间 |
| competitors | 竞品主体和公开页面 |
| competitor_snapshots | 价格、评分、评论数、可见卖点快照 |
| fx_rates | CNY/EUR等汇率 |

模拟ASIN使用明显的演示格式，例如 `DEMO-DE-LAMP-001`，不得伪造为真实Amazon ASIN。

### 4.4 文件与RAG

#### files

```text
id, tenant_id, owner_user_id, original_name, storage_key,
extension, mime_type, size_bytes, sha256, category,
status, error_message, created_at, deleted_at
```

#### documents

```text
id, tenant_id, file_id, title, document_type, language,
market, product_id, access_level, active_version_id
```

#### document_versions

```text
id, document_id, version_no, content_hash, parser_name,
parser_version, parse_status, created_at
```

#### document_chunks

```text
id, tenant_id, document_id, version_id, chunk_index,
title_path, page_no, sheet_name, cell_range, content,
token_count, metadata_json, search_vector,
embedding vector(1024), embedding_model, embedding_version
```

#### document_acl

保存文档对角色、用户或市场的授权。RAG SQL必须在检索前关联ACL过滤。

### 4.5 Agent运行与证据

| 表 | 作用 |
|---|---|
| threads | 会话 |
| messages | 用户、模型、工具消息摘要 |
| tasks | 长任务状态和预算 |
| task_steps | 计划、依赖、状态和重试 |
| skill_runs | Skill名称、版本、触发原因、允许工具、状态和完成检查 |
| agent_checkpoints | LangGraph恢复状态 |
| tool_calls | 工具、参数摘要、状态、耗时和错误 |
| evidences | 统一证据 |
| claims | 最终回答或报告中的结论 |
| claim_evidences | 结论与证据多对多关系 |
| reports | Markdown结果、版本与Artifact引用；PDF不在当前M4范围 |
| feedback | 用户反馈和Bad Case标签 |

原始模型输入输出不无限期完整保存；按配置做脱敏、截断或只保存哈希和必要审计字段。

### 4.6 评估

| 表 | 作用 |
|---|---|
| eval_datasets | 数据集名称、版本、范围 |
| eval_cases | 输入、期望轨迹、标准答案和标签 |
| eval_runs | 代码、Prompt、模型和数据版本 |
| eval_case_results | 单样本实际输出和分项得分 |
| eval_metrics | 聚合指标 |
| eval_comparisons | A/B或GSB比较 |

评估原始JSONL也进入Git，数据库表用于运行记录和分析。

## 5. 关键关系

```text
tenant
 ├─ users
 ├─ products ─ variants ─ listings ─ sales/ads/returns
 │               ├─ supplier_quotes
 │               └─ inventory_snapshots
 ├─ files ─ documents ─ versions ─ chunks
 └─ threads ─ messages
          └─ tasks ─ task_steps ─ tool_calls
                    ├─ evidences
                    └─ reports ─ claims ─ claim_evidences
```

所有业务、文件、知识、会话、任务、证据和报告表必须带 `tenant_id` 或能够通过外键唯一追溯到tenant。

## 6. 合成数据设计

### 6.1 原则

- 可追溯：固定随机种子和生成器版本；
- 可复现：清空后可以重新生成同一批基础数据；
- 有业务逻辑：不是互不相关的随机数；
- 有正常数据，也有可解释的异常和边界情况；
- 所有页面和报告显示“演示数据”；
- 不复制真实店铺、真实客户或真实供应商信息。

### 6.2 生成顺序

```text
基础字典
 → 公司/用户/权限
 → 市场/仓库/供应商
 → 产品/规格/SKU
 → 供应商报价/采购
 → 入库与库存
 → Listing与价格
 → 日销售/广告/退货/费用
 → 竞品公开快照
 → 知识库文档和用户文件样本
 → 预计算标准答案与评估问题
```

### 6.3 经营数据公式

库存：

```text
期末库存 = 期初库存 + 采购入库 + 客退入库 - 销售出库 - 报损 - 调出 + 调入
可售库存 = 期末库存 - 预留库存 - 不可售库存
```

销售：

```text
销售额 = 销量 × 当日成交均价
退款额 = 退款数量 × 对应成交价
```

广告：

```text
CTR = clicks / impressions
CPC = spend / clicks
CVR = ad_orders / clicks
ACOS = spend / ad_sales
```

利润：

```text
贡献利润 = 净销售额 - 采购成本 - 头程 - Amazon模拟费用 - 广告费 - 退货损失
贡献利润率 = 贡献利润 / 净销售额
```

所有报表只调用同一指标服务计算，禁止前端、SQL工具和报告Prompt各自定义不同公式。

### 6.4 季节性与异常

生成器应包含：

- 黑五和圣诞前照明、装饰类销量上涨；
- 一月至二月需求回落；
- 德国和法国市场不同的价格、广告和退货分布；
- 新品冷启动期；
- 一次供应延迟导致缺货风险；
- 一个SKU广告ACOS异常上升；
- 一个SKU因包装问题退货率升高；
- 一个过期供应商报价；
- 一个缺少合规文件的候选新品；
- 一个被用户权限隐藏的敏感成本字段。

这些异常同时用于Agent推理和评估集。

### 6.5 知识库演示文件

计划生成或整理：

- 公司产品目录；
- 供应商报价单；
- 质检SOP；
- 包装规范；
- 库存与补货规则；
- 德国、法国市场研究备忘录；
- 灯具合规检查模板；
- Listing内容规范；
- 周报/月报模板；
- 蘑菇灯候选产品说明书。

合规文件只用于展示知识检索，必须注明“演示资料，不构成法律或认证意见”。

## 7. 数据校验

### 7.1 数据库约束

- 数量和金额不得无理由为负；
- 所有金额带币种；
- 比率在合理范围内；
- 市场、仓库和Listing关系有效；
- 销售SKU必须在对应日期已上架；
- 采购入库不能早于采购创建；
- 每日库存与movement账一致；
- 退货不能长期大于累计销售；
- 报价有效期和版本明确；
- 时间统一使用timestamptz，业务日按市场时区解释。

### 7.2 生成后审计

每次生成执行：

- 行数和日期覆盖检查；
- 库存平衡检查；
- 收入、费用和利润重算；
- 主外键孤儿检查；
- 权限隔离检查；
- 预设异常是否出现；
- 数据摘要输出到 `data/seed/manifest.json`。

## 8. 评估体系

### 8.1 原则

评估分层，不只判断最终文字“看起来不错”：

```text
组件层：解析、检索、SQL、工具
轨迹层：路由、计划、调用顺序、终止
结果层：正确性、忠实性、引用、完整性
系统层：延迟、成本、恢复、安全
```

### 8.2 数据集格式

```json
{
  "id": "route_inventory_001",
  "category": "routing",
  "user_role": "amazon_operator",
  "input": {
    "query": "德国仓蘑菇灯还有多少可售库存？",
    "file_ids": []
  },
  "expected": {
    "route": "fast_business_query",
    "skill": null,
    "required_tools": ["search_inventory"],
    "forbidden_tools": ["search_public_web"],
    "answer_facts": {
      "market": "DE"
    }
  },
  "tags": ["de", "inventory", "fast_path"]
}
```

每个样本可包含：标准事实、相关文档ID、期望Skill及版本、期望工具、禁止工具、允许误差、权限身份和故障注入条件。简单查询的期望Skill为`null`，用来防止系统把所有问题都过度包装成复杂流程。

### 8.3 首批评估集

先构建约150条最小基线集，跑通后扩展到300条以上：

| 类别 | 首批数量 | 重点 |
|---|---:|---|
| 意图与路由 | 30 | 普通、DB、RAG、图片、深度任务 |
| 工具选择与参数 | 25 | 必须调用、禁止调用、参数完整性 |
| SQL与业务答案 | 25 | 执行成功、答案事实、权限与安全 |
| RAG检索与引用 | 30 | 多语言、编号、版本、无答案问题 |
| 多模态 | 15 | 商品属性、OCR、推断和未知项 |
| 深度任务与报告 | 10 | 计划、证据覆盖、结论完整性 |
| 安全与故障恢复 | 15 | 注入、越权、超时、重启、损坏文件 |

### 8.4 路由和工具指标

- Route Accuracy；
- Tool Selection Precision/Recall/F1；
- Required Tool Coverage；
- Forbidden Tool Violation Rate；
- 参数Schema有效率；
- 平均工具调用数；
- 无意义重复调用率；
- 任务终止成功率。

Skill上线后增加：

- Skill Activation Precision/Recall/F1：是否在该启用时启用、该保持简单时不启用；
- Skill Completion Rate：规定的必要步骤和输出是否完成；
- Skill Version Traceability：每次运行能否定位到准确版本；
- Skill Tool Policy Violation：Skill是否申请或实际调用了范围外工具；
- Skill Procedure Regression：Skill更新后关键业务步骤是否退化。

工具权限违规由Harness的实际调用轨迹判定，不能只检查模型最终回答中声称使用了什么。

### 8.5 SQL指标

- SQL AST安全校验拦截率；
- Executable SQL Rate；
- Result Accuracy；
- 数据范围与时间解释正确率；
- 越权查询阻断率；
- 禁止写操作阻断率；
- 查询超时和行数限制生效率。

SQL文本不要求与标准SQL完全一致，最终结果和安全性更重要。

### 8.6 RAG指标

检索：

- Recall@5 / Recall@10；
- Precision@5；
- MRR；
- NDCG；
- 权限过滤正确率。

生成：

- Faithfulness；
- Answer Relevance；
- Completeness；
- Citation Accuracy；
- 无答案拒答准确率。

必须分别保存Dense、Lexical、RRF和Reranker各阶段结果，以便定位优化来自哪里。

### 8.7 多模态指标

- JSON Schema有效率；
- 产品类别准确率；
- 颜色、形状、可见部件属性F1；
- OCR字段准确率；
- “事实/推断/未知”分类准确率；
- 隐藏规格幻觉率；
- 多图比较覆盖率。

图片尺寸、材质和认证等不能只看最终答案，要检查模型是否正确表达不确定性。

### 8.8 深度任务和报告

采用规则 + 人工 + LLM-as-Judge组合：

- 计划是否覆盖必要子任务；
- 并行和顺序依赖是否合理；
- 关键结论是否有证据；
- 计算公式是否可复现；
- 是否明确假设和未知项；
- 是否区分模拟数据与公开证据；
- 报告结构、可读性和行动建议；
- 工具失败后是否保留部分结果。

LLM Judge不能作为唯一判定。首批至少20%的样本由人工复核，校准Judge偏差。

### 8.9 暂定质量门槛

以下仅作为首轮目标，生成评估集并运行基线后再冻结：

| 指标 | 暂定目标 |
|---|---:|
| Route Accuracy | ≥ 90% |
| Required Tool Coverage | ≥ 90% |
| Forbidden Tool Violation | 0 |
| SQL安全写操作阻断率 | 100% |
| RAG Recall@5 | ≥ 85% |
| Citation Accuracy | ≥ 90% |
| 多模态JSON有效率 | ≥ 98% |
| 关键属性准确率 | ≥ 85% |
| 深度任务完成率 | ≥ 85% |
| 权限越权阻断率 | 100% |

### 8.10 回归测试

- PR Smoke：20至30条确定性关键样本；
- 本地Full Eval：完整评估集；
- Prompt、模型、Embedding、Reranker、分块参数变化必须生成新run；
- 保存代码commit、模型版本、Prompt版本、数据版本和配置；
- 使用GSB比较旧版、新版，防止平均分提高但关键场景退化。

## 9. 实施优先级

### 9.1 P0：简历核心闭环

- PostgreSQL业务模型与合成数据；
- 登录、RBAC和三类用户；
- qwen3.8-max适配器；
- 安全库存/规格查询；
- 自建RAG：解析、pgvector、混合检索、Reranker、引用；
- Capability驱动的Agent Gateway、Supervisor与Business/Knowledge Worker；
- 分阶段Harness：上下文、权限、工具策略、预算、追踪、恢复和评估钩子；
- M4两个受控Web Tool、Fake/Tavily Provider和Web Research Worker；
- 一个`cross-border-market-research`可版本化Skill；
- Evidence层；
- 聊天工作台、任务过程和证据面板；
- Markdown研究结果；
- 最小评估集和运行报告；
- Docker Compose与演示说明。

### 9.2 P1：工程增强

- 真实压测证明有必要后再评估独立任务队列；
- 模型/搜索缓存；
- qwen3.7-flash任务降本；
- 更完整报表图表；
- Prompt注入测试；
- 评估结果可视化；
- 更细粒度文档ACL；
- 自动数据质量报告。

### 9.3 P2：未来扩展

- MinIO/S3；
- Docling和扫描PDF OCR；
- Amazon SP-API适配器；
- 真实ERP连接器；
- 图片生成和本地化；
- 视频理解；
- SaaS多租户、计费和云部署；
- MCP工具服务化。

MCP属于P2扩展，不作为“技术越多越有含金量”的堆栈项。只有真实外部连接器或跨客户端复用需求出现时才引入。

## 10. 最快实施路线

估时按单人专注开发计算，只用于排序，不作为固定承诺。

### 里程碑M0：设计冻结

产出：三份设计文档、范围清单、ADR和演示脚本。

退出条件：技术栈、数据边界、V1范围和验收场景无冲突。

### 里程碑M1：库存查询垂直切片

工作内容：

- 建立新目录和配置；
- Docker Compose启动PostgreSQL/pgvector；
- Alembic迁移；
- 生成用户、产品、仓库和库存基础数据；
- 接入qwen3.8-max；
- 实现登录、聊天、库存工具和最小前端；
- 建立最小Harness骨架：RunContext、ToolRegistry、PermissionGuard、ExecutionBudget和基础Trace；
- 本阶段只实现`get_product_spec`、`search_inventory`两个Tool，不实现Skill运行时；
- 返回数据库证据。

演示结果：运营人员问一句库存，系统正确查库并显示证据。

### 里程碑M2：知识库垂直切片

- 本地文件存储；
- PDF/DOCX/XLSX解析；
- 分块、BGE-M3、pgvector；
- 混合检索和Reranker；
- 引用面板；
- RAG最小评估集；
- 实现`search_knowledge`、`get_evidence_detail`、`read_uploaded_file`三个Tool；
- 实现Capability驱动的Agent Gateway、Supervisor、Business/Knowledge Worker、统一Answer Provider、记忆/Checkpoint和现有聊天入口迁移；
- 完成最小评估、前端引用展示和整体验收。

演示结果：上传产品说明书后，可以基于文档回答并定位页码。

### 里程碑M3：多模态商品分析

当前秋招主线暂缓；以下内容保留为未来候选，不是M4或M5的前置条件：

- 图片上传；
- Base64调用qwen3.8-max；
- 结构化视觉Schema；
- 图片事实、推断和未知项；
- 相似SKU数据库联查；
- 多模态评估样本；
- 实现`analyze_product_images`、`search_similar_products`两个Tool；
- 建立最小SkillCatalog、Loader、Router和Policy；
- 首个落地Skill为`product-visual-analysis`，并记录版本和允许工具。

演示结果：上传蘑菇灯图片，系统看图后查询公司类似产品。

### 里程碑M4：深度研究与报告

- 复用M2 Supervisor、Business/Knowledge Worker、Answer Provider和Citation Validator；
- 只新增Web Research Worker；
- 实现`search_public_web`、`read_public_source`与Fake/Tavily Provider；
- 建立正文Web Evidence、来源去重/冲突和网页注入防护；
- 先顺序、后独立只读Worker有界并行；
- 使用PostgreSQL父子Run、任务租约与Checkpoint恢复，不引入Redis/Celery；
- 落地`cross-border-market-research`一个Skill与Markdown Service；
- 完成任务API、前端进度/Evidence和真实Tavily/Qwen验收；
- 不做Pandas复杂分析、图表、PDF或独立Analysis/Report Worker。

演示结果：完成数据库、内部文档和公开网页三类Evidence的通用有界研究；德国、法国蘑菇灯只是Golden Scenario，不是硬编码逻辑。

### 里程碑M5：评估与作品化

- 根据M2/M4最终能力冻结约80至120条高价值样本，最终规模在M5正式方案确认；
- 自动评估Runner；
- 安全、权限和故障注入；
- 性能与成本记录；
- Skill激活、完成率、版本追踪和工具策略回归；
- Harness权限、预算、超时、重试、Checkpoint与故障注入验证；
- UI细化；
- README、架构图、演示视频和简历描述。

演示结果：不仅展示系统“能跑”，还展示指标、Bad Case和优化前后对比。

## 11. 开发顺序规则

每个里程碑都使用同一循环：

```text
定义验收样本
 → 实现最小数据和API
 → 接入Agent节点/工具
 → 实现前端可见结果
 → 自动化测试
 → 记录评估与Bad Case
 → 再进入下一个里程碑
```

禁止先写完所有数据库表、所有Agent和所有页面再统一联调。

## 12. 风险与降级

| 风险 | 影响 | 应对 |
|---|---|---|
| qwen3.8-max费用或限流 | 长任务不可用 | Token预算、缓存、后续Flash降级 |
| BGE本地CPU较慢 | 索引/查询延迟 | 批量索引、按需加载、后续远程Provider |
| Tavily无Key或额度不足 | 网络研究缺失 | Mock证据用于测试，任务返回部分结果 |
| 合成数据不可信 | 分析缺少说服力 | 业务公式、固定种子、审计和异常设计 |
| Agent过度调用工具 | 成本和延迟 | 路由分级、工具分组、预算和终止条件 |
| Skill被滥用或步骤漂移 | 简单任务变慢、复杂任务遗漏关键检查 | 明确触发条件、版本化、轨迹评估和回归集 |
| Prompt或Skill声明绕过权限 | 越权访问工具或数据 | Harness在服务端计算权限交集，不信任模型声明 |
| 任意SQL风险 | 数据泄露/破坏 | AST校验、只读账号、白名单、超时 |
| 文档权限泄露 | 严重安全问题 | 检索前SQL过滤、越权评估集 |
| 范围膨胀 | 无法完成 | P0/P1/P2隔离，MinIO/OCR/SP-API后置 |

## 13. 作品交付物

项目最终需要同时交付：

- 可运行代码和Docker Compose；
- 三份设计文档和ADR；
- `cross-border-market-research` Skill定义、版本记录和对应评估样例；
- Harness运行策略、工具注册表和审计轨迹示例；
- ER图、Agent状态图、RAG流程图；
- 合成数据生成器和数据字典；
- 评估数据集、Runner和基线报告；
- API文档；
- 关键安全测试；
- 演示账号和演示脚本；
- 3至5分钟演示视频；
- README中的架构、启动、能力边界和结果指标；
- 已知限制和后续路线。

## 14. 建议演示脚本

```text
1. 以Amazon运营身份登录
2. 在统一聊天入口询问德国仓库存，展示Business Worker自主Tool选择和数据库Evidence
3. 查询内部文档，展示Knowledge Worker、混合检索、Reranker和引用
4. 提出跨数据库与文档的问题，展示Supervisor、Handoff和两类Evidence
5. 提供歧义请求并补充信息，展示短期记忆、Checkpoint和恢复
6. 发起数据库＋内部文档＋公开网页的M4研究任务
7. 展示多Agent步骤、Web正文Evidence、部分失败和Markdown结果
8. 切换受限账号，证明业务数据和文档不可越权
9. 展示Agent/RAG评估与性能成本基线
10. 展示一次故障恢复或Bad Case优化前后对比
```

## 15. 简历表达参考

项目完成且指标真实后，可表达为：

> 设计并实现面向跨境电商场景的权限感知多Agent研究平台，基于LangGraph编排千问、企业数据库、自建RAG与受控互联网检索；通过Capability Resolver、结构化Handoff和Harness实现Worker工具隔离、树形预算、审计与Checkpoint恢复；使用PostgreSQL/pgvector、BGE-M3与Reranker实现权限前置混合检索和可验证引用，并以分层评估、故障矩阵和性能成本数据验证完整应用闭环。

指标必须替换为实际评估结果，不得提前在简历中填写本文暂定目标。

## 16. 开工前剩余配置

以下问题不影响方案评审，但进入对应里程碑前必须解决：

- 阿里云百炼Workspace、Base URL和API Key；
- Tavily API Key或测试Mock策略；
- 两台电脑上BGE-M3与Reranker基准测试；
- 本地数据根目录和磁盘空间；
- Docker Compose可用端口；
- 最终演示账号密码仅通过环境变量或Seed配置生成。

除此之外，没有需要用户现在决定的架构问题。
