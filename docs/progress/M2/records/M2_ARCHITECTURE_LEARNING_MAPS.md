# 项目架构学习图记录

## 2026-09-05：当前项目框架总览图

### 目标

用一张可交互总览图帮助初学者先看清项目当前真实框架、主要调用链和“已实现/尚未接入”的边界。本步只制作第一张总览图，不展开第二张请求时序图，也不修改运行代码。

### 产物与职责

- `docs/diagrams/01_current_architecture.json`：Archify 可编辑图源，包含节点、边界、连线、三条引导视图和仓库源码引用。
- `docs/diagrams/01_current_architecture.html`：可独立打开的交互式架构图，支持明暗主题、引导浏览和导出。
- `docs/diagrams/01_current_architecture.visual-check.*`：多视口浏览器检查回执、联系表和截图证据。

### 调用链位置

图中覆盖：

`前端 → API/Auth/Schema → M1 InventoryQueryAgent → Harness → Tool Registry/适配器 → Service/Repository → PostgreSQL/pgvector`

同时展示 M2 已实现但尚未进入公开聊天入口的知识链：

`文件/文档 API → Service → LocalStorage → 解析/分块 → BGE-M3 → PostgreSQL/pgvector → Hybrid/Rerank → Context/Evidence → 知识 Tool`

图中明确标注：公开聊天当前仍走 M1 固定 Agent；M2 知识 Tool 尚未接入公开聊天；模型不能构造 `RunContext`、真实权限或真实预算；Context/Evidence 每次最多 12 条；Supervisor/Worker 尚未成为运行路径。

### 验证方法与实际结果

1. 使用 Archify `showcase` 配置执行架构校验：9/9 项通过，0 errors，0 warnings；交叉、含糊走廊、容器边线复用、标签间距和桌面可读性问题均为 0。
2. 仓库证据校验通过：仓库 `https://github.com/luchunjin115/deep-search-pro-master`，固定修订 `86fe991fce33b784f68abe8e135fe09b55599ab9`，共验证 27 个源码引用。
3. 最终图源 SHA-256：`5494e6657ff9b84007588505ab011d6eba9d1c71876cda3b2ac29ca95562092b`；HTML SHA-256：`0b158e6db5e84ec0491ebc06bbc06fbe5d8fd84400fef33c982a9553af1752f7`。
4. Chrome 自动检查覆盖 1440×900、1600×1000、1920×1080、2048×1320；所有视口无横纵溢出，可读性、图例和导航停靠均通过。第一次检查曾在 `Runtime.evaluate` 超时，原样重试后通过。
5. 人工查看 1440×900 浅色图和 2048×1320 深色图，节点、连线、说明卡片、图例与引导区均完整清晰。

### 能证明与不能证明

能证明：交付文件结构有效、仓库引用可追溯、常见桌面尺寸能完整浏览；图中的“当前公开链”和“M2 已实现但未接入公开聊天”边界与当前项目记录一致。

不能证明：运行代码的业务正确性、数据库真实数据、模型回答质量或端到端 API 行为；本步没有运行应用测试，也没有实现 Agent Gateway、Supervisor、Worker 或后续 M2-21 能力。固定修订不包含工作区尚未提交的改动，因此图不会把这些改动包装成已进入公开运行链。

### 风险与排查

- 如果打开后布局异常，先确认使用现代 Chromium 浏览器并重新运行 Archify `visual-check`。
- 如果后续调用链变化，先对照真实路由、Agent、Harness、Tool、Service 和 Repository 更新 JSON 源，再重新执行 `validate → deliver → visual-check`；不要只手改生成后的 HTML。
- 图是理解入口，不替代单元测试、集成测试和真实数据库验证。

### 下一步

先由用户按三条引导视图确认理解；未获单独确认前，不制作第二张请求流转图，也不推进 M2-21.3。

## 2026-09-05：M2 知识检索真实调用时序图（已完成）

### 目标与产物

用户已确认制作第二张图。本步只描述已实现的 `search_knowledge` 内部 Tool 链，不把公开知识聊天、真实 Knowledge Worker 或 Agent Gateway 画成已接通。最终产物为可编辑图源 `docs/diagrams/02_knowledge_search_sequence.json`、交互式页面 `docs/diagrams/02_knowledge_search_sequence.html` 及同目录 `visual-check` 回执、联系表和截图。

### 已核对的真实调用顺序

`内部调用方 → SearchKnowledgeTool → Harness/Registry/预算/权限/Trace → ToolExecutionContext身份验真 → KnowledgeSearchService → Reranker（内部Hybrid）→ 获权active代次 → BGE-M3 → Dense/Lexical → RRF → BGE-Reranker → Context Builder重新获权 → Context/Evidence/ToolContextLink原子保存 → ToolEnvelope`

### 验证过程与实际结果

- 首轮候选先把7项布局问题缩小为1项桌面可读性问题；按Archify停止规则保留真实中间记录。续作时把独立门禁参与者合并回Harness，将9个参与者压缩为8个后，Showcase结构校验9/9通过，0 errors、0 warnings。
- 第一版HTML的文字可读性通过，但四种桌面视口出现纵向溢出，`scrollHeight`为1590至1751。只做一轮视觉修正：删除可由注释或隐含返回表达的低价值箭头，保留四段主时序和所有安全语义，并按真实顺序重新排布。
- 最终图源SHA-256为`08e8baa39cab62a1623644d962f983d2eb138310b5fef6289ec311c9c2c5b6f2`，6105 bytes；HTML SHA-256为`719efb2f2bf01a1de0bcf1b193bf4a7958ca83fd0d969bc89a375acaea154d31`，719331 bytes。
- 最终Chrome自动检查覆盖1440×900、1600×1000、1920×1080和2048×1320；全部无横纵溢出，可读性、图例和导航停靠通过，最小节点文字约10.97px。
- 人工查看1440×900浅色图和2048×1320深色图，四段时序、参与者、权限红线、请求/返回线、图例和引导视图均完整清晰，没有进行第二轮视觉修正。

### 能证明与不能证明

能证明交付图的时序事实已按当前 Tool、Harness、KnowledgeSearchService、Hybrid/Reranker、Context Builder和Evidence代码核对，结构有效，并能在常见桌面尺寸完整浏览。不能证明运行代码本身的业务正确性、真实数据库状态或模型质量，也不证明公开聊天、真实Knowledge Worker或Agent Gateway已经接入；本步没有修改生产代码或运行应用测试。

### 下一动作

先由用户按三条引导视图学习第二张图；未获单独确认前，不制作第三张图，也不推进M2-21.6开发。
