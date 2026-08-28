# RAG（检索增强生成）完全知识体系

> 从底层原理到生产实战，覆盖 RAG 系统构建的全部核心知识。
> 定位：AI 应用工程师必备技能，学完本篇能独立交付企业级 RAG 项目。

---

## 目录

- [写在前面：学习路线纠偏](#写在前面学习路线纠偏)
- [第一章：RAG 是什么？为什么需要它？](#第一章rag-是什么为什么需要它)
- [第二章：RAG 完整流程全景图](#第二章rag-完整流程全景图)
- [第三章：数据采集与预处理](#第三章数据采集与预处理)
- [第四章：分块策略（Chunking）——最容易做错的环节](#第四章分块策略chunking最容易做错的环节)
- [第五章：Embedding 向量化——理解语义的核心](#第五章embedding-向量化理解语义的核心)
- [第六章：向量数据库——选型与实战](#第六章向量数据库选型与实战)
- [第七章：检索策略——不只是"最相似"](#第七章检索策略不只是最相似)
- [第八章：Reranking 重排序——被低估的关键环节](#第八章reranking-重排序被低估的关键环节)
- [第九章：Context 构建与 Prompt 设计](#第九章context-构建与-prompt-设计)
- [第十章：RAG 评估体系——怎么证明系统好用](#第十章rag-评估体系怎么证明系统好用)
- [第十一章：Advanced RAG——进阶技术](#第十一章advanced-rag进阶技术)
- [第十二章：生产环境落地指南](#第十二章生产环境落地指南)
- [第十三章：常见问题诊断手册](#第十三章常见问题诊断手册)
- [第十四章：完整项目实战案例](#第十四章完整项目实战案例)
- [第十五章：AI 应用工程师成长路线图](#第十五章ai-应用工程师成长路线图)

---

## 写在前面：学习路线纠偏

### 你的认知中需要纠正的几个点

**纠正 1：RAG 的流程顺序**

你列出的顺序是"信息提取 → chunks 分块 → 向量数据库 → context → 向量化 → 提示词"，这个顺序有两个问题：

- **向量化应该在向量数据库之前**——先把文本变成向量，才能存进向量数据库
- **context 不是一个独立步骤**——它是检索结果 + Prompt 模板组合后的产物

**正确的流程顺序：**

```
文档加载 → 预处理/清洗 → 分块(Chunking) → 向量化(Embedding)
→ 存入向量数据库(Indexing) → 用户提问 → 查询改写
→ 检索(Retrieval) → 重排序(Reranking) → Context 构建
→ Prompt 组装 → LLM 生成答案 → 答案后处理
```

**纠正 2：你遗漏了几个关键环节**

| 你没提到的环节 | 重要程度 | 说明 |
|---|---|---|
| **文档预处理/清洗** | ★★★★★ | 垃圾进垃圾出，清洗质量决定一切 |
| **查询改写** | ★★★★☆ | 用户的问题通常不适合直接检索 |
| **Reranking（重排序）** | ★★★★★ | 初次检索的排序经常不准，重排是必须的 |
| **混合检索** | ★★★★☆ | 不只是向量检索，还有关键词检索 |
| **评估体系** | ★★★★★ | 没有评估就无法优化 |
| **元数据过滤** | ★★★★☆ | 不是所有场景都靠语义搜索 |

**纠正 3：学习 RAG 确实是 Prompt Engineering 之后的正确下一步**

```
AI 应用工程师技能树：
Step 1: Prompt Engineering ✅（你已完成）
Step 2: RAG 系统构建 ← 你在这里
Step 3: Agent / Function Calling
Step 4: 多模态应用
Step 5: 评估与优化体系
Step 6: 生产部署与运维
```

---

## 第一章：RAG 是什么？为什么需要它？

### 1.1 一句话定义

**RAG = 检索（Retrieval）+ 增强（Augmented）+ 生成（Generation）**

先从你的知识库中找到相关信息，然后把这些信息喂给 LLM，让它基于这些信息生成答案。

### 1.2 为什么需要 RAG

LLM 有三个根本性局限，RAG 恰好解决它们：

| LLM 的局限 | 后果 | RAG 如何解决 |
|---|---|---|
| **知识截止日期** | 不知道训练后发生的事 | 检索实时数据 |
| **无法访问私有数据** | 不知道你公司的内部文档 | 检索企业知识库 |
| **幻觉问题** | 一本正经地胡说八道 | 答案基于检索到的事实 |

### 1.3 RAG vs Fine-tuning vs 长上下文

这是面试必问题，也是技术选型的关键判断：

| 对比维度 | RAG | Fine-tuning | 长上下文（直接塞全文） |
|---|---|---|---|
| **适合场景** | 知识频繁更新、需要溯源 | 改变模型行为/风格 | 文档少、一次性任务 |
| **数据量要求** | 无限（检索多少用多少） | 数百到数千条标注数据 | 受限于上下文窗口 |
| **更新成本** | 低（更新知识库即可） | 高（需要重新训练） | 低（换文档即可） |
| **可解释性** | 好（可以展示引用来源） | 差（黑盒） | 好 |
| **成本** | 检索基础设施 + API 调用 | GPU 训练成本 | 每次都发送全部文本 |
| **延迟** | 检索 + 生成 | 和普通推理一样 | 长上下文推理较慢 |

**选择建议：**

```
你的数据会不会变？
├─ 经常变 → RAG
└─ 几乎不变
    ├─ 数据量 < 200K tokens → 直接塞上下文
    └─ 数据量 > 200K tokens
        ├─ 需要溯源/引用 → RAG
        └─ 只需改变风格 → Fine-tuning
```

### 1.4 RAG 的核心价值公式

```
RAG 系统的价值 = 检索质量 × 生成质量

其中：
- 检索质量 = 找到正确的信息（重中之重，占 80% 的影响力）
- 生成质量 = 基于正确信息给出好的回答（占 20%）

这意味着：
如果检索不到正确信息，LLM 再强也没用。
RAG 系统 80% 的优化精力应该花在检索侧。
```

---

## 第二章：RAG 完整流程全景图

### 2.1 两大阶段

RAG 系统分为两个阶段，每个阶段有不同的关注点：

```
═══════════════════════════════════════════════════════════════
                    阶段一：离线索引（Indexing）
                    一次性建设，定期更新
═══════════════════════════════════════════════════════════════

  ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌──────────┐
  │ 文档加载 │ →  │ 预处理  │ →  │  分块   │ →  │ 向量化  │ →  │ 存入向量 │
  │ Loading │    │Cleaning │    │Chunking │    │Embedding│    │  数据库  │
  └─────────┘    └─────────┘    └─────────┘    └─────────┘    └──────────┘
   PDF/Word/       去噪、格式     按策略切分     文本→向量       索引+元数据
   HTML/DB...      标准化         成小段落      (数字数组)       持久化存储

═══════════════════════════════════════════════════════════════
                    阶段二：在线查询（Querying）
                    每次用户提问都执行
═══════════════════════════════════════════════════════════════

  ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐
  │ 用户提问 │ →  │ 查询改写│ →  │ 检索    │ →  │ 重排序  │
  │         │    │Query    │    │Retrieval│    │Reranking│
  │         │    │Transform│    │         │    │         │
  └─────────┘    └─────────┘    └─────────┘    └─────────┘
                  扩展/分解       向量检索+       按相关性
                  用户问题       关键词检索       重新排序
                                                    │
                                                    ▼
  ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐
  │ 答案输出 │ ←  │ LLM生成 │ ←  │Prompt   │ ←  │Context  │
  │+ 引用源 │    │         │    │组装     │    │构建     │
  └─────────┘    └─────────┘    └─────────┘    └─────────┘
   返回答案+       基于 context    系统指令+       Top-K 结果
   引用来源        生成回答       context+问题     拼接成上下文
```

### 2.2 每个环节的输入输出

| 环节 | 输入 | 输出 | 关键指标 |
|---|---|---|---|
| 文档加载 | 原始文件 | 纯文本 + 元数据 | 提取完整性 |
| 预处理 | 原始文本 | 清洗后的文本 | 噪声去除率 |
| 分块 | 长文本 | 文本块列表 | 块大小、语义完整性 |
| 向量化 | 文本块 | 向量 (float数组) | 语义保真度 |
| 索引 | 向量 + 元数据 | 可查询的索引 | 写入速度 |
| 查询改写 | 原始问题 | 优化后的查询 | 检索命中率提升 |
| 检索 | 查询向量 | Top-K 相关文档块 | Recall@K |
| 重排序 | Top-K 候选 | 重排后的 Top-N | 排序准确性 |
| Context 构建 | Top-N 文档块 | 拼接好的上下文 | 信息密度 |
| LLM 生成 | Prompt + Context | 最终答案 | 准确性、有据可查 |

---

## 第三章：数据采集与预处理

### 3.1 文档加载（Document Loading）

不同格式的文档需要不同的解析方式：

| 文档格式 | 推荐工具 | 注意事项 |
|---|---|---|
| **PDF（文本型）** | PyMuPDF, pdfplumber | 注意表格和多栏布局 |
| **PDF（扫描型）** | PaddleOCR, Tesseract, Azure Document Intelligence | OCR 准确率是瓶颈 |
| **Word (.docx)** | python-docx, mammoth | 注意嵌入图片和表格 |
| **HTML** | BeautifulSoup, trafilatura | 去除导航栏、广告等噪声 |
| **Markdown** | 直接解析 | 保留标题层级结构 |
| **Excel/CSV** | pandas | 行列关系需要转换为自然语言 |
| **PPT** | python-pptx | 注意 speaker notes |
| **数据库** | SQLAlchemy | 结构化数据需要转换为文本描述 |
| **API 数据** | requests | 需要序列化为文本 |

### 3.2 预处理/清洗（Preprocessing）

**垃圾进垃圾出（Garbage In, Garbage Out）是 RAG 的第一定律。**

```python
def preprocess_document(raw_text: str) -> str:
    """文档预处理管线"""

    # 1. 编码标准化
    text = raw_text.encode('utf-8', errors='ignore').decode('utf-8')

    # 2. 去除无意义字符
    text = remove_control_characters(text)    # 控制字符
    text = remove_excessive_whitespace(text)  # 多余空白
    text = remove_headers_footers(text)       # 页眉页脚
    text = remove_page_numbers(text)          # 页码

    # 3. 格式标准化
    text = normalize_unicode(text)            # Unicode 标准化
    text = normalize_punctuation(text)        # 标点统一（全角/半角）

    # 4. 内容增强
    text = resolve_abbreviations(text)        # 展开缩写（可选）
    text = merge_hyphenated_words(text)       # 合并跨行连字符

    # 5. 表格处理
    text = convert_tables_to_text(text)       # 表格转自然语言

    return text
```

**表格处理是一个经常被忽略的难点：**

```
原始表格：
| 产品 | Q1 | Q2 | Q3 |
|------|-----|-----|-----|
| A    | 100 | 150 | 200 |
| B    | 50  | 75  | 120 |

转换为自然语言（更适合向量检索）：
"产品 A 的季度数据：Q1 销量 100，Q2 销量 150，Q3 销量 200。
产品 B 的季度数据：Q1 销量 50，Q2 销量 75，Q3 销量 120。"

为什么要转换？
因为向量模型理解自然语言远好于理解表格结构。
直接把表格的 Markdown 存进去，检索效果会很差。
```

### 3.3 元数据提取

元数据在后续检索中极其重要，不能只存文本：

```python
metadata = {
    "source": "company_handbook_2024.pdf",  # 来源文件
    "page": 15,                              # 页码
    "chapter": "第三章 薪酬福利",             # 所属章节
    "last_updated": "2024-03-15",            # 最后更新时间
    "author": "HR部门",                      # 作者/部门
    "document_type": "policy",               # 文档类型
    "security_level": "internal",            # 安全等级
    "language": "zh-CN",                     # 语言
}
```

> **为什么元数据重要？** 因为很多检索需求不是纯语义的。比如"去年的薪资政策是什么"——你需要用 `last_updated` 过滤时间，而不是靠向量相似度去猜。

---

## 第四章：分块策略（Chunking）——最容易做错的环节

### 4.1 为什么分块如此关键

```
不分块的问题：
├─ 整篇文档太长，超过 embedding 模型的输入限制
├─ 整篇文档向量化后，语义太泛，检索精度低
└─ 塞给 LLM 的 context 中有大量无关内容

分块太小的问题：
├─ 语义不完整，丢失上下文
├─ "他表示同意" ← "他"是谁？分块太小就丢失了
└─ 检索到的片段无法独立理解

分块太大的问题：
├─ 一个块中包含多个主题，向量化后语义模糊
├─ 噪声信息多，干扰 LLM 生成
└─ 浪费 context window
```

### 4.2 六种分块策略详解

#### 策略一：固定大小分块（Fixed-Size Chunking）

```python
# 最简单的方法：按字符数/token数切分
chunk_size = 500       # 每块 500 个字符
chunk_overlap = 50     # 相邻块重叠 50 个字符

# 示例
text = "这是一段很长的文本..."
chunks = []
for i in range(0, len(text), chunk_size - chunk_overlap):
    chunks.append(text[i:i + chunk_size])
```

| 优点 | 缺点 |
|------|------|
| 实现简单 | 会在句子/段落中间切断 |
| 块大小均匀 | 不考虑语义边界 |
| 可预测 | "他"和"他指代的人"可能被分开 |

**适用场景：** 快速原型、文本格式统一且段落划分不明确的场景

**重叠（Overlap）的作用：**

```
不重叠：
[块1: AAAA][块2: BBBB][块3: CCCC]
↑ 如果关键信息在 A 和 B 的交界处，两个块都不完整

有重叠：
[块1: AAAA BB]
      [块2: BBBBCC]
           [块3: CCCC]
↑ 交界处的信息在两个块中都出现，不会丢失
```

#### 策略二：基于分隔符的分块（Separator-Based）

```python
# 按自然段落、换行符、标点等分隔符切分
separators = ["\n\n", "\n", "。", "！", "？", "；"]

# 先按段落分 → 如果段落太长，按句子分 → 如果句子太长，按字符分
# 这是 LangChain 的 RecursiveCharacterTextSplitter 的逻辑
```

| 优点 | 缺点 |
|------|------|
| 尊重自然段落边界 | 段落大小不均匀 |
| 语义完整性较好 | 一个段落可能包含多个主题 |
| 实现相对简单 | 依赖文档格式质量 |

**适用场景：** 格式规范的文档（政策文件、技术文档）

#### 策略三：基于语义的分块（Semantic Chunking）

```python
# 核心思想：用 embedding 计算相邻句子的语义相似度，
# 在相似度突然下降的地方切分

sentences = split_into_sentences(text)
embeddings = embed_model.encode(sentences)

chunks = []
current_chunk = [sentences[0]]

for i in range(1, len(sentences)):
    similarity = cosine_similarity(embeddings[i-1], embeddings[i])

    if similarity < threshold:  # 语义突变 → 切分
        chunks.append("".join(current_chunk))
        current_chunk = [sentences[i]]
    else:
        current_chunk.append(sentences[i])

chunks.append("".join(current_chunk))
```

| 优点 | 缺点 |
|------|------|
| 语义边界最准确 | 需要额外的 embedding 计算 |
| 每个块主题聚焦 | 实现复杂 |
| 检索精度最高 | 块大小不均匀 |

**适用场景：** 对检索精度要求高的场景（知识库问答、合同审查）

#### 策略四：基于文档结构的分块（Structure-Based）

```python
# 按文档的标题层级切分
# H1 → 大块
#   H2 → 中块
#     H3 → 小块

# Markdown 示例
"# 第一章 公司概况"        → 第一级分块边界
"## 1.1 公司历史"          → 第二级分块边界
"### 1.1.1 创立背景"       → 第三级分块边界
"正文内容..."
```

| 优点 | 缺点 |
|------|------|
| 保留文档层级关系 | 依赖文档有清晰的标题结构 |
| 每个块有明确的主题 | 章节大小差异大 |
| 可以利用标题做元数据 | 不适合无结构文本 |

**适用场景：** 技术文档、规章制度、教材

#### 策略五：递归分块（Recursive Chunking）

```
这是实际项目中最常用的策略，LangChain 的默认方式。

逻辑：
1. 先尝试按 "\n\n"（段落）分
2. 如果某段太长，按 "\n"（换行）分
3. 如果还太长，按 "。"（句子）分
4. 如果还太长，按字符数硬切

每一层都保证不超过 chunk_size，同时尽量保留语义完整性。
```

| 优点 | 缺点 |
|------|------|
| 平衡了语义完整性和大小均匀性 | 需要调参（chunk_size, overlap） |
| 适用范围广 | 对中文分句可能需要定制 |
| 生产级的默认选择 | |

#### 策略六：Agentic Chunking（用 LLM 分块）

```
最前沿的方法：让 LLM 来决定怎么分块。

Prompt：
"以下是一篇长文档。请将其分割成独立的、语义完整的段落。
每个段落应该：
1. 围绕一个核心主题
2. 可以独立理解，不需要其他段落的上下文
3. 长度在 200-500 字之间
如果一个段落引用了前文的代词（如'他'、'该公司'），
请将被指代的实体名称补充完整。"
```

| 优点 | 缺点 |
|------|------|
| 语义完整性最高 | 成本极高（每篇文档都要调 LLM） |
| 可以解决代词指代问题 | 速度慢 |
| 最智能的分块方式 | 大规模文档不实际 |

**适用场景：** 少量高价值文档（核心合同、关键政策）

### 4.3 分块参数怎么选

这是你最关心的问题之一：

```
chunk_size 怎么选？

                检索精度
                  ▲
                  │     ╱──── 最优区间
                  │    ╱      ╲
                  │   ╱        ╲
                  │  ╱          ╲
                  │ ╱
                  │╱
                  └──────────────────→ chunk_size
                100  256  512  1024  2048

经验值：
├─ 问答场景（精确匹配）：256-512 tokens
├─ 摘要/分析场景：512-1024 tokens
├─ 代码检索：按函数/类分块（大小不固定）
├─ 法律/合同：512-1024 tokens（保证条款完整）
└─ 对话历史：按对话轮次分块
```

**chunk_overlap 怎么选？**

```
经验法则：overlap = chunk_size 的 10%-20%

chunk_size = 512 → overlap = 50-100
chunk_size = 1024 → overlap = 100-200

太小的 overlap → 信息断裂风险
太大的 overlap → 存储浪费 + 检索重复
```

### 4.4 分块质量的自检清单

每次分块后用这个清单检查：

- [ ] 随机抽取 20 个块，每个块能否独立理解？
- [ ] 是否有块在句子中间被切断？
- [ ] 是否有块包含多个不相关的主题？
- [ ] 代词（他、它、该公司）是否能在块内找到指代对象？
- [ ] 表格数据是否被保留完整？
- [ ] 代码块是否被切断？
- [ ] 列表项是否被切断？
- [ ] 块大小的分布是否合理（没有特别大或特别小的异常值）？

---

## 第五章：Embedding 向量化——理解语义的核心

### 5.1 什么是 Embedding

```
Embedding 就是把文本转换成一个数字向量（数组），
使得语义相近的文本在向量空间中距离相近。

"猫咪很可爱"   → [0.12, -0.34, 0.56, ..., 0.78]  (1536维)
"小猫很萌"     → [0.11, -0.33, 0.55, ..., 0.77]  (1536维)
                  ↑ 这两个向量非常接近（语义相似）

"今天天气真好" → [0.89, 0.23, -0.45, ..., 0.12]  (1536维)
                  ↑ 这个向量和前两个距离很远（语义不同）
```

### 5.2 Embedding 模型选型

| 模型 | 维度 | 最大输入 | 语言 | 适用场景 | 推荐度 |
|------|------|----------|------|----------|--------|
| **text-embedding-3-large** (OpenAI) | 3072 | 8191 tokens | 多语言 | 通用场景 | ★★★★★ |
| **text-embedding-3-small** (OpenAI) | 1536 | 8191 tokens | 多语言 | 成本敏感 | ★★★★☆ |
| **voyage-3** (Voyage AI) | 1024 | 32000 tokens | 多语言 | 长文本、代码 | ★★★★★ |
| **BGE-M3** (BAAI) | 1024 | 8192 tokens | 多语言 | 开源首选、中文好 | ★★★★★ |
| **bge-large-zh** (BAAI) | 1024 | 512 tokens | 中文 | 中文专用 | ★★★★☆ |
| **Jina-embeddings-v3** | 1024 | 8192 tokens | 多语言 | 多任务 | ★★★★☆ |
| **GTE-Qwen2** (阿里) | 1536 | 8192 tokens | 多语言 | 中文场景 | ★★★★☆ |
| **Cohere embed-v3** | 1024 | 512 tokens | 多语言 | 搜索优化 | ★★★★☆ |

**怎么选？**

```
你的场景是什么？
├─ 纯中文 → BGE-M3 或 GTE-Qwen2
├─ 中英混合 → text-embedding-3-large 或 BGE-M3
├─ 代码检索 → voyage-3（代码理解能力最强）
├─ 成本敏感 → text-embedding-3-small 或开源模型自部署
├─ 数据不能出境 → 开源模型自部署（BGE-M3）
└─ 不确定 → 先用 text-embedding-3-large 基线测试
```

### 5.3 Embedding 的关键概念

#### 相似度度量

```python
# 余弦相似度（最常用）
cosine_similarity = dot(A, B) / (norm(A) * norm(B))
# 范围：-1 到 1，越接近 1 越相似

# 欧几里得距离
euclidean_distance = sqrt(sum((A[i] - B[i])^2))
# 越小越相似

# 点积（内积）
dot_product = sum(A[i] * B[i])
# 越大越相似（前提是向量已归一化）
```

**怎么选相似度度量？**

| 度量方式 | 适用场景 | 说明 |
|---|---|---|
| **余弦相似度** | 大多数场景 | 不受向量长度影响，只看方向 |
| **欧几里得距离** | 向量长度有意义时 | 受向量长度影响 |
| **点积** | 向量已归一化时 | 等价于余弦相似度 |

> 默认选余弦相似度，除非你有明确的理由选其他。

#### Embedding 维度的权衡

```
维度高（3072维）：
├─ 能捕获更细微的语义差异
├─ 存储空间更大
├─ 检索速度更慢
└─ 适合：精度要求高的场景

维度低（256-512维）：
├─ 存储更小
├─ 检索更快
├─ 可能丢失细微语义
└─ 适合：大规模数据、延迟敏感

text-embedding-3-large 的一个好特性：
支持维度缩减（Matryoshka Embeddings），
可以在创建后截断到 256/512/1024 维，灵活权衡精度和效率。
```

### 5.4 Embedding 的常见陷阱

```
陷阱 1：查询和文档用不同的 Embedding 模型
   ❌ 文档用 BGE 做的 embedding，查询用 OpenAI 的 embedding
   ✅ 查询和文档必须用同一个 embedding 模型

陷阱 2：文本长度超过模型的最大输入限制
   ❌ 把 2000 token 的文本喂给只支持 512 token 的模型
   → 超出部分会被截断，信息丢失
   ✅ 分块时确保每块不超过 embedding 模型的最大输入

陷阱 3：忽略 embedding 模型的更新
   ❌ 换了 embedding 模型但没有重新对全部文档做 embedding
   → 新旧向量不在同一个空间中，检索结果错乱
   ✅ 更换模型 = 重建整个向量索引

陷阱 4：中英文混合时 tokenizer 的差异
   ❌ 用纯英文优化的 embedding 处理中文
   → 中文 token 数远多于英文，可能超出限制
   ✅ 选择对中文友好的 embedding 模型
```

---

## 第六章：向量数据库——选型与实战

### 6.1 为什么需要专门的向量数据库

```
普通数据库（MySQL/PostgreSQL）：
  SELECT * FROM docs WHERE content LIKE '%合同%'
  → 只能做关键词匹配，无法理解语义

向量数据库：
  SELECT * FROM docs ORDER BY vector_distance(query_vector, doc_vector) LIMIT 10
  → 基于语义相似度检索，理解"合同"和"协议"是近义词
```

### 6.2 向量数据库选型对比

| 数据库 | 类型 | 适合规模 | 特点 | 推荐场景 |
|---|---|---|---|---|
| **ChromaDB** | 嵌入式 | < 100 万 | 零配置、Python 原生 | 原型开发、个人项目 |
| **FAISS** | 库（非数据库） | 不限 | Meta 开源、性能极高 | 追求极致性能、不需要持久化 |
| **Milvus** | 分布式 | 十亿级 | 功能全、生产级 | 大规模企业应用 |
| **Pinecone** | 云服务 | 不限 | 全托管、开箱即用 | 不想运维、快速上线 |
| **Weaviate** | 自部署/云 | 亿级 | 混合搜索好 | 需要混合检索 |
| **Qdrant** | 自部署/云 | 亿级 | Rust 写的、性能好 | 性能敏感、需要过滤 |
| **pgvector** | PG 插件 | < 1000 万 | 复用已有 PostgreSQL | 已有 PG、不想加新组件 |
| **Elasticsearch** | 搜索引擎 | 亿级 | 混合搜索、生态成熟 | 已有 ES 基础设施 |

### 6.3 怎么选？决策树

```
你的数据量有多大？
├─ < 10 万条 → 开发阶段用 ChromaDB，生产用 pgvector
├─ 10 万 - 1000 万条
│   ├─ 已有 PostgreSQL → pgvector
│   ├─ 需要混合搜索 → Weaviate 或 Elasticsearch
│   ├─ 不想运维 → Pinecone
│   └─ 需要自部署 → Qdrant 或 Milvus
└─ > 1000 万条
    ├─ 不想运维 → Pinecone
    └─ 需要自部署 → Milvus（分布式）

你的部署限制是什么？
├─ 数据不能出境 → 自部署（Milvus/Qdrant/Weaviate）
├─ 没有运维团队 → 云托管（Pinecone）
└─ 预算有限 → 开源方案（ChromaDB/pgvector）
```

### 6.4 向量数据库的核心概念

```python
# 以 ChromaDB 为例，展示核心操作

import chromadb

# 1. 创建客户端和集合
client = chromadb.PersistentClient(path="./chroma_db")
collection = client.create_collection(
    name="company_docs",
    metadata={"hnsw:space": "cosine"}  # 使用余弦相似度
)

# 2. 添加文档（索引）
collection.add(
    ids=["doc1", "doc2", "doc3"],
    documents=["公司年假政策是...", "报销流程如下...", "绩效考核标准..."],
    metadatas=[
        {"source": "handbook.pdf", "chapter": "假期", "year": 2024},
        {"source": "handbook.pdf", "chapter": "财务", "year": 2024},
        {"source": "handbook.pdf", "chapter": "HR", "year": 2024},
    ],
    embeddings=[[0.1, 0.2, ...], [0.3, 0.4, ...], [0.5, 0.6, ...]]
)

# 3. 查询（检索）
results = collection.query(
    query_embeddings=[[0.15, 0.25, ...]],  # 查询的向量
    n_results=5,                            # 返回 Top 5
    where={"year": 2024},                   # 元数据过滤
    where_document={"$contains": "年假"}    # 全文过滤
)

# 4. 更新文档
collection.update(
    ids=["doc1"],
    documents=["更新后的年假政策..."],
    embeddings=[[0.11, 0.21, ...]]
)

# 5. 删除文档
collection.delete(ids=["doc3"])
```

### 6.5 索引类型——为什么检索速度差异巨大

```
暴力搜索（Flat/Brute-Force）：
├─ 和每个向量逐一比较
├─ 精度：100%（精确结果）
├─ 速度：O(n)，数据量大时很慢
└─ 适合：< 10 万条数据

HNSW（Hierarchical Navigable Small World）：
├─ 构建多层图结构，近似搜索
├─ 精度：95-99%（近似）
├─ 速度：O(log n)，非常快
├─ 内存消耗大
└─ 适合：大多数生产场景（最推荐）

IVF（Inverted File Index）：
├─ 先聚类，再在最近的几个类中搜索
├─ 精度：取决于 nprobe 参数
├─ 速度：快，但需要训练
└─ 适合：内存受限的大规模场景

PQ（Product Quantization）：
├─ 压缩向量，减少内存使用
├─ 精度：有损
├─ 速度：快
└─ 适合：超大规模、内存极度受限

实际选择：
├─ 大多数场景 → HNSW（精度高、速度快、配置简单）
├─ 超大规模 + 内存限制 → IVF + PQ
└─ 小数据集 → Flat（精确搜索）
```

---

## 第七章：检索策略——不只是"最相似"

### 7.1 检索方式对比

```
这是很多初学者最大的误解：以为 RAG 就是向量检索。

实际上，生产级 RAG 系统通常使用混合检索（Hybrid Search）。
```

#### 向量检索（Semantic Search）

```
用户问："员工离职需要提前多久通知？"
检索方式：把问题向量化 → 在向量库中找最相似的块
能找到："根据劳动合同法，劳动者提前三十日以书面形式通知用人单位..."

优点：理解语义，"离职"能匹配到"辞职"、"解除合同"
缺点：
├─ 对专有名词/编号不敏感："BUG-2024-001"搜不到
├─ 对精确匹配场景效果差："Python 3.12.1 的 bug"
└─ 语义漂移：可能返回语义相关但不是你要的内容
```

#### 关键词检索（Keyword Search / BM25）

```
用户问："BUG-2024-001 的处理进度"
检索方式：关键词匹配 + TF-IDF/BM25 评分
能找到：包含 "BUG-2024-001" 精确文本的文档

优点：
├─ 精确匹配非常可靠
├─ 对编号、代码、专有名词友好
└─ 不需要向量化，速度快

缺点：
├─ 不理解语义："离职"搜不到"辞职"
└─ 对同义词、近义词不敏感
```

#### 混合检索（Hybrid Search）——生产级首选

```
                    用户查询
                       │
              ┌────────┴────────┐
              ▼                 ▼
         向量检索            关键词检索
        (语义匹配)          (精确匹配)
              │                 │
              ▼                 ▼
         Top-K 结果          Top-K 结果
              │                 │
              └────────┬────────┘
                       ▼
                  融合排序
            (RRF / 加权融合)
                       │
                       ▼
                 最终 Top-K 结果

融合公式（RRF - Reciprocal Rank Fusion）：
RRF_score(d) = Σ 1/(k + rank_i(d))
其中 k 通常 = 60，rank_i(d) 是文档 d 在第 i 个检索结果中的排名

为什么混合检索好？
├─ 向量检索擅长语义理解 → 覆盖同义词、近义词
├─ 关键词检索擅长精确匹配 → 覆盖编号、专有名词
└─ 两者互补，整体 Recall 显著提升
```

### 7.2 查询改写（Query Transformation）

用户的原始问题通常不适合直接用于检索：

#### 技术一：查询扩展（Query Expansion）

```
原始查询："年假怎么算？"

扩展后：
- "年假计算方式"
- "年休假天数规定"
- "带薪休假标准"
- "员工年假政策"

方法：用 LLM 生成同义查询
Prompt："请将以下问题改写成 3 个不同的表述，保持含义不变：{query}"
```

#### 技术二：HyDE（Hypothetical Document Embeddings）

```
核心思想：让 LLM 先"假设性回答"问题，然后用这个假设答案去检索。

原始查询："年假怎么算？"

Step 1：让 LLM 生成假设性答案
"根据国家规定，职工累计工作已满1年不满10年的，年休假5天；
 已满10年不满20年的，年休假10天；已满20年的，年休假15天。"

Step 2：用这个假设答案做 embedding，去检索

为什么有效？
├─ 问题通常很短（5-10 个词），信息密度低
├─ 假设答案更长、更接近文档的表达方式
└─ "答案找答案"比"问题找答案"在向量空间中更容易匹配

局限：
├─ 假设答案可能是错的（但没关系，只用于检索方向）
├─ 多一次 LLM 调用，增加延迟和成本
```

#### 技术三：问题分解（Query Decomposition）

```
复杂问题拆成多个子问题，分别检索后合并。

原始查询："入职不满一年但之前在其他公司工作了8年，年假怎么算？"

分解为：
子问题 1："入职不满一年的年假规定"
子问题 2："跨公司工龄如何计算"
子问题 3："工龄8年对应的年假天数"

每个子问题独立检索 → 合并结果 → 送给 LLM 综合回答
```

### 7.3 元数据过滤（Metadata Filtering）

```
不是所有检索都需要靠语义相似度。

用户问："2024年的薪资调整政策"
│
├─ 语义检索：找所有和"薪资调整"语义相近的文档
│  问题：可能找到 2022、2023 年的旧政策
│
└─ 正确做法：先用元数据过滤年份，再做语义检索
   WHERE year = 2024 AND category = "薪资"
   → 只在 2024 年的薪资文档中做语义检索

常见的元数据过滤维度：
├─ 时间范围（年份、日期）
├─ 文档类型（政策、通知、规范）
├─ 部门/来源
├─ 安全等级
├─ 语言
└─ 版本号
```

---

## 第八章：Reranking 重排序——被低估的关键环节

### 8.1 为什么需要 Reranking

```
向量检索返回的 Top-K 结果，排序往往不够精确。

原因：
├─ Embedding 是在"压缩"语义，必然有信息损失
├─ 一个 1024 维的向量无法完美表达一段文本的全部含义
├─ 向量检索是"快速粗筛"，不是"精确排序"
└─ 混合检索的融合排序也是启发式的

Reranker 是"精排"：
├─ 直接拿 (query, document) 对输入一个 Cross-Encoder 模型
├─ 模型同时看到查询和文档，做精细的相关性判断
├─ 精度远高于 embedding 的余弦相似度
└─ 但速度慢（不能对所有文档做，只能对 Top-K 候选做）
```

### 8.2 Two-Stage 检索架构

```
                用户查询
                   │
                   ▼
        ┌──────────────────┐
        │  Stage 1: 召回   │  ← 快速、粗糙、高召回率
        │  (Bi-Encoder)    │  ← 向量检索 + 关键词检索
        │  返回 Top-50     │  ← 用 embedding 做快速筛选
        └────────┬─────────┘
                 │ 50 个候选
                 ▼
        ┌──────────────────┐
        │  Stage 2: 精排   │  ← 慢速、精确、高精度
        │  (Cross-Encoder) │  ← Reranker 模型
        │  返回 Top-5      │  ← 逐一精细评分
        └────────┬─────────┘
                 │ 5 个最相关的
                 ▼
           Context 构建
```

### 8.3 Reranker 模型选型

| 模型 | 来源 | 特点 | 推荐度 |
|---|---|---|---|
| **Cohere Rerank** | Cohere API | 效果最好之一，云服务 | ★★★★★ |
| **bge-reranker-v2-m3** | BAAI 开源 | 多语言、可自部署 | ★★★★★ |
| **Jina Reranker** | Jina AI | 多语言、API 服务 | ★★★★☆ |
| **cross-encoder/ms-marco** | HuggingFace | 英文、开源 | ★★★☆☆ |

### 8.4 Reranking 的实际效果

```
某企业知识库问答系统的测试数据：

不用 Reranking：
  Top-1 准确率：45%
  Top-3 准确率：62%
  Top-5 准确率：71%

使用 Reranking 后：
  Top-1 准确率：68% (+23pp !)
  Top-3 准确率：82% (+20pp !)
  Top-5 准确率：89% (+18pp !)

结论：Reranking 是 ROI 最高的优化手段之一。
```

---

## 第九章：Context 构建与 Prompt 设计

### 9.1 Context 构建策略

检索到 Top-K 文档块后，怎么组织成 LLM 可用的上下文：

```python
def build_context(retrieved_chunks: list, max_tokens: int = 4000) -> str:
    """构建发送给 LLM 的上下文"""

    context_parts = []
    total_tokens = 0

    for i, chunk in enumerate(retrieved_chunks):
        chunk_tokens = count_tokens(chunk.text)

        if total_tokens + chunk_tokens > max_tokens:
            break  # 超过 token 预算就停止

        # 每个块带上来源信息
        context_parts.append(
            f"[来源 {i+1}] (文件: {chunk.metadata['source']}, "
            f"页码: {chunk.metadata.get('page', 'N/A')})\n"
            f"{chunk.text}"
        )
        total_tokens += chunk_tokens

    return "\n\n---\n\n".join(context_parts)
```

**Context 构建的关键决策：**

| 决策点 | 选项 | 建议 |
|---|---|---|
| 放多少块？ | 3-10 块 | 默认 5 块，根据评估调整 |
| 块的排序？ | 按相关性 / 按原文顺序 | 最相关的放最前面 |
| 是否标注来源？ | 是/否 | 必须标注（支持溯源） |
| 是否去重？ | 是/否 | 是（overlap 可能导致重复内容） |
| 超长怎么办？ | 截断 / 压缩 | 先截断低相关性的块 |

### 9.2 RAG 专用 Prompt 设计

```
System Prompt 模板：

你是{company_name}的智能问答助手。

## 核心规则
1. 仅基于以下【参考资料】回答问题，不要使用你自己的知识
2. 如果参考资料中没有足够的信息来回答问题，请明确说
   "根据现有资料，我无法回答这个问题"
3. 回答时必须标注信息来源，格式为 [来源 X]
4. 如果多个来源的信息有冲突，指出冲突并说明

## 回答要求
- 语言简洁、专业
- 直接回答问题，不要展开无关内容
- 如果问题需要最新数据而参考资料可能过时，提醒用户核实

## 参考资料
{context}

## 用户问题
{question}
```

### 9.3 常见 Prompt 设计错误

```
错误 1：没有告诉模型"只基于参考资料回答"
  → 模型会混合自己的知识和检索结果，可能产生幻觉

错误 2：没有处理"找不到答案"的情况
  → 模型会强行编造一个看似合理的答案

错误 3：没有要求标注来源
  → 用户无法验证答案的可靠性

错误 4：Context 中的块没有标注来源标识
  → 即使要求标注，模型也不知道该引用什么

错误 5：把 Context 放在 Prompt 的中间
  → "Lost in the Middle" 效应，模型可能忽略中间的信息
  → 建议：Context 放在最后，紧接着用户问题
```

### 9.4 答案后处理

```
LLM 生成答案后，还需要做后处理：

1. 引用验证
   ├─ 检查模型标注的 [来源 X] 是否真的在对应来源中
   ├─ 如果模型编造了来源 → 标记为"未验证"
   └─ 提取引用的原文片段展示给用户

2. 幻觉检测
   ├─ 答案中的事实是否都能在 Context 中找到依据
   ├─ 简单方法：检查答案中的关键实体是否出现在 Context 中
   └─ 高级方法：用另一个 LLM 做 Faithfulness 检测

3. 答案格式化
   ├─ 将引用来源格式化为可点击的链接
   ├─ 高亮关键信息
   └─ 添加"此答案基于 X 份参考文档"的置信度说明
```

---

## 第十章：RAG 评估体系——怎么证明系统好用

### 10.1 为什么 RAG 评估特别难

```
普通 AI 系统：输入 → 输出 → 评估输出质量
RAG 系统：输入 → 检索 → 生成 → 需要分别评估检索和生成

如果最终答案不对：
├─ 可能是检索没找到正确文档（检索的问题）
├─ 可能是找到了但 LLM 没用好（生成的问题）
├─ 可能是分块导致信息不完整（分块的问题）
├─ 可能是 embedding 质量不好（向量化的问题）
└─ 需要分层诊断！
```

### 10.2 RAG 评估的四大维度

#### 维度一：检索质量（Retrieval Quality）

| 指标 | 含义 | 计算方式 | 目标 |
|---|---|---|---|
| **Recall@K** | Top-K 结果中包含正确文档的比例 | 正确文档数 / 应返回文档数 | > 85% |
| **Precision@K** | Top-K 结果中相关文档的比例 | 相关文档数 / K | > 60% |
| **MRR** | 第一个正确结果的排名倒数 | 1/正确结果的排名 | > 0.7 |
| **NDCG** | 考虑排序质量的综合指标 | (越前面的越重要) | > 0.75 |

#### 维度二：生成质量（Generation Quality）

| 指标 | 含义 | 评估方式 | 目标 |
|---|---|---|---|
| **Faithfulness（忠实性）** | 答案是否忠于参考资料 | LLM-as-Judge | > 90% |
| **Relevance（相关性）** | 答案是否回答了用户的问题 | LLM-as-Judge | > 85% |
| **Completeness（完整性）** | 答案是否覆盖了所有要点 | 人工评估 | > 80% |
| **Harmfulness（无害性）** | 答案是否包含有害信息 | 规则+LLM | = 0% |

#### 维度三：端到端质量（End-to-End）

| 指标 | 含义 | 评估方式 |
|---|---|---|
| **Answer Accuracy** | 最终答案是否正确 | 和标准答案对比 |
| **Citation Accuracy** | 引用来源是否正确 | 验证引用对应的原文 |
| **Rejection Accuracy** | 该拒绝回答时是否拒绝了 | 用无法回答的问题测试 |

#### 维度四：系统性能

| 指标 | 目标 |
|---|---|
| 端到端延迟（P95） | < 5 秒 |
| 检索延迟 | < 500 毫秒 |
| 每次查询的成本 | 根据业务可接受范围 |
| 可用性 | > 99.9% |

### 10.3 评估工具推荐

| 工具 | 特点 | 适合场景 |
|---|---|---|
| **RAGAS** | 专门为 RAG 设计的评估框架 | 最推荐的起步工具 |
| **LlamaIndex 评估模块** | 和 LlamaIndex 深度集成 | 如果你用 LlamaIndex |
| **DeepEval** | 全面的 LLM 评估框架 | 需要更多评估维度 |
| **自建评估管线** | 完全可控 | 生产级、定制化需求 |

### 10.4 RAGAS 评估示例

```python
from ragas import evaluate
from ragas.metrics import (
    faithfulness,           # 忠实性
    answer_relevancy,       # 答案相关性
    context_precision,      # 上下文精确率
    context_recall,         # 上下文召回率
)

# 准备评估数据
eval_dataset = {
    "question": ["年假怎么计算？", "报销流程是什么？"],
    "answer": ["根据工龄...", "首先提交申请..."],
    "contexts": [["参考资料1...", "参考资料2..."], [...]],
    "ground_truth": ["标准答案1...", "标准答案2..."]
}

# 运行评估
result = evaluate(
    eval_dataset,
    metrics=[
        faithfulness,
        answer_relevancy,
        context_precision,
        context_recall,
    ],
)

print(result)
# {'faithfulness': 0.92, 'answer_relevancy': 0.88,
#  'context_precision': 0.85, 'context_recall': 0.90}
```

---

## 第十一章：Advanced RAG——进阶技术

### 11.1 进阶技术全景图

```
                      Advanced RAG 技术
                           │
      ┌────────────────────┼────────────────────┐
      ▼                    ▼                    ▼
   检索侧优化          索引侧优化           生成侧优化
      │                    │                    │
      ├─ HyDE             ├─ 多级索引          ├─ 自适应检索
      ├─ Multi-Query      ├─ 父文档检索        ├─ Self-RAG
      ├─ Step-Back        ├─ 知识图谱增强      ├─ CRAG
      ├─ 混合检索+RRF     ├─ 假设性问题索引    ├─ 长上下文整合
      └─ 条件路由         └─ 摘要索引          └─ 迭代检索
```

### 11.2 父文档检索（Parent Document Retrieval）

```
核心问题：小块检索精度高，但缺少上下文；大块上下文完整，但检索精度低。

解决方案：存两份！
├─ 小块用于检索（精确匹配）
└─ 大块用于生成（完整上下文）

工作流程：
1. 将文档切成大块（Parent，1000 tokens）
2. 将大块再切成小块（Child，200 tokens）
3. 对小块做 embedding，存入向量库
4. 维护 child → parent 的映射关系
5. 检索时：用小块匹配查询
6. 返回时：返回对应的大块（Parent）给 LLM

效果：
├─ 检索精度 ≈ 小块的精度（高）
└─ 上下文完整性 ≈ 大块的完整性（高）
```

### 11.3 多级索引（Hierarchical Index）

```
对大规模文档库，先做粗检索再做细检索。

Level 1: 文档摘要索引
├─ 每篇文档生成一个摘要（用 LLM）
├─ 对摘要做 embedding
└─ 先找到最相关的 3-5 篇文档

Level 2: 文档块索引
├─ 在 Level 1 找到的文档中做细粒度检索
└─ 返回最相关的 5-10 个文档块

好处：
├─ 搜索范围从"全部文档"缩小到"3-5 篇"
├─ 大幅减少计算量
└─ 避免跨文档的干扰
```

### 11.4 知识图谱增强 RAG（Graph RAG）

```
传统 RAG 只能检索文本片段，无法理解实体之间的关系。

Graph RAG 的做法：
1. 从文档中抽取实体和关系，构建知识图谱
   (张三) --[担任]--> (技术总监)
   (张三) --[负责]--> (项目Alpha)
   (项目Alpha) --[使用]--> (Python)

2. 用户提问："谁负责 Python 相关的项目？"

3. 检索路径：
   Python ←[使用]─ 项目Alpha ←[负责]─ 张三

4. 将图谱路径 + 相关文本块一起作为 Context

适用场景：
├─ 需要多跳推理的问答（"A 的上司的部门？"）
├─ 实体关系密集的领域（组织架构、产品目录）
└─ 需要全局视角的分析（"公司有多少个用 Python 的项目？"）
```

### 11.5 Self-RAG（自适应检索）

```
核心思想：不是每个问题都需要检索。

传统 RAG：不管什么问题都检索 → 有时检索到无关信息反而干扰

Self-RAG 的做法：
1. 用户提问后，先让 LLM 判断是否需要检索
   ├─ "1+1 等于几？" → 不需要检索
   ├─ "公司年假政策？" → 需要检索
   └─ "对比我司和行业的年假标准" → 需要检索（还可能需要联网）

2. 如果需要检索，生成后自我评估：
   ├─ 检索到的内容是否支持我的回答？（Faithfulness）
   ├─ 我的回答是否完全基于检索内容？（Grounding）
   └─ 如果评估不通过 → 重新检索或拒绝回答

好处：
├─ 减少不必要的检索（节省延迟和成本）
├─ 减少检索噪声对生成的干扰
└─ 通过自我反思提高答案质量
```

### 11.6 条件路由（Conditional Routing）

```
不同的问题应该走不同的检索路径。

用户查询
   │
   ▼
路由器（LLM 或分类器）
   │
   ├─ 事实查询 → 向量检索知识库
   ├─ 数据查询 → SQL 查询数据库
   ├─ 最新信息 → 联网搜索
   ├─ 计算问题 → 代码执行
   └─ 闲聊 → 直接回答（不检索）

实现方式：
1. 规则路由：关键词匹配（简单但脆弱）
2. 分类器路由：训练一个意图分类模型
3. LLM 路由：让 LLM 判断查询类型（灵活但慢）
```

---

## 第十二章：生产环境落地指南

### 12.1 从原型到生产的差距

```
原型阶段能跑通 ≠ 生产环境能用

原型中忽略的问题：
├─ 并发：100 个用户同时提问会怎样？
├─ 更新：知识库更新了怎么增量索引？
├─ 权限：不同用户能看到的文档不同
├─ 监控：系统挂了谁来通知？
├─ 成本：每天 1000 次查询要花多少钱？
├─ 安全：用户通过提问泄露了其他用户的数据？
└─ 反馈：用户觉得不好怎么收集反馈？
```

### 12.2 生产级 RAG 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                      前端/API 层                             │
│  ├─ 用户认证 & 权限校验                                     │
│  ├─ 请求限流                                                │
│  └─ 输入校验 & 清洗                                         │
├─────────────────────────────────────────────────────────────┤
│                      应用逻辑层                              │
│  ├─ 查询路由器（决定走哪条检索路径）                          │
│  ├─ 查询改写模块                                            │
│  ├─ 检索模块（向量检索 + 关键词检索 + 元数据过滤）            │
│  ├─ Reranking 模块                                         │
│  ├─ Context 构建器                                         │
│  ├─ LLM 调用（带重试 & 降级策略）                            │
│  └─ 答案后处理（引用验证、格式化）                            │
├─────────────────────────────────────────────────────────────┤
│                      数据层                                  │
│  ├─ 向量数据库（Milvus/Qdrant）                             │
│  ├─ 关键词索引（Elasticsearch）                              │
│  ├─ 元数据存储（PostgreSQL）                                │
│  ├─ 文档原文存储（S3/OSS）                                  │
│  └─ 缓存（Redis）                                          │
├─────────────────────────────────────────────────────────────┤
│                      离线管线                                │
│  ├─ 文档摄入管线（新文档自动处理）                            │
│  ├─ 增量索引（只处理变化的文档）                              │
│  ├─ 定期重建索引（embedding 模型更新时）                      │
│  └─ 评估管线（定期跑回归测试）                               │
├─────────────────────────────────────────────────────────────┤
│                      可观测性                                │
│  ├─ 日志（每次检索和生成的完整链路）                          │
│  ├─ 监控（延迟、错误率、检索命中率）                          │
│  ├─ 用户反馈收集（👍👎 按钮）                                │
│  └─ 告警（异常检测）                                        │
└─────────────────────────────────────────────────────────────┘
```

### 12.3 增量更新策略

```
文档更新时不需要重建整个索引：

新增文档：
├─ 解析 → 分块 → 向量化 → 插入向量库
└─ 不影响已有索引

修改文档：
├─ 删除旧的块 → 重新分块 → 向量化 → 插入
└─ 需要维护 document_id → chunk_ids 的映射

删除文档：
├─ 通过 document_id 找到所有相关的 chunk_ids
└─ 从向量库中批量删除

版本管理：
├─ 保留历史版本（审计需要）
├─ 默认检索最新版本
└─ 支持查询指定版本
```

### 12.4 权限控制

```
关键问题：A 部门的机密文档不能被 B 部门的人通过 RAG 查询到。

方案 1：文档级权限（推荐）
├─ 每个文档块的 metadata 中存储 access_groups
├─ 检索时根据用户的角色做 metadata 过滤
│  WHERE access_groups IN user.groups
└─ 简单可靠

方案 2：独立知识库
├─ 每个部门/项目独立的向量集合
├─ 用户只能查询有权限的集合
└─ 隔离性最好，但管理成本高

方案 3：检索后过滤
├─ 先检索 Top-50，然后过滤掉无权限的
├─ 可能过滤后剩余太少
└─ 不推荐（可能泄露排序信息）
```

### 12.5 缓存策略

```
缓存层级：

Level 1：查询缓存
├─ 相同/极相似的问题直接返回缓存答案
├─ 用 embedding 相似度判断是否命中缓存
├─ TTL：根据知识库更新频率设置
└─ 效果：高频问题响应 < 100ms

Level 2：Embedding 缓存
├─ 相同文本不需要重复调用 embedding API
├─ Hash(text) → embedding
└─ 效果：减少 embedding API 调用次数

Level 3：LLM 响应缓存
├─ 相同的 (context, question) → 缓存 LLM 响应
├─ 适用于 temperature=0 的场景
└─ 效果：减少 LLM API 调用成本
```

---

## 第十三章：常见问题诊断手册

### 13.1 问题诊断流程图

```
最终答案不满意
      │
      ├─ 答案和问题无关 ──────────────── → 问题出在"检索"
      │   ├─ 检索结果里有正确文档吗？
      │   │   ├─ 没有 → 检索召回问题
      │   │   │   ├─ embedding 模型不好 → 换模型
      │   │   │   ├─ 分块太大/太小 → 调分块参数
      │   │   │   ├─ 查询和文档的表达差异大 → 加查询改写
      │   │   │   └─ 文档根本不在知识库中 → 检查文档摄入
      │   │   │
      │   │   └─ 有，但排名很靠后 → 排序问题
      │   │       ├─ 加 Reranker
      │   │       └─ 增大 Top-K
      │   │
      │   └─ 检索结果里有正确文档
      │       → 问题出在"生成"（检索正常但 LLM 没用好）
      │       ├─ Context 构建有问题 → 调 Prompt
      │       ├─ 正确文档排太后面 → LLM 忽略了（Lost in Middle）
      │       └─ Prompt 没有强调"只基于参考资料" → 改 Prompt
      │
      ├─ 答案部分正确部分编造 ────────── → 幻觉问题
      │   ├─ 加强 Prompt 约束"只基于参考资料"
      │   ├─ 降低 temperature
      │   ├─ 加引用验证后处理
      │   └─ 用 Self-RAG 做自我检查
      │
      ├─ 答案正确但不完整 ──────────── → 信息不足
      │   ├─ 增大 Top-K
      │   ├─ 分块太小导致信息碎片化 → 增大 chunk_size
      │   ├─ 用 Parent Document Retrieval
      │   └─ 检查文档是否完整导入
      │
      └─ 答案正确但太慢 ──────────── → 性能问题
          ├─ Embedding 计算慢 → 用更小的模型或加缓存
          ├─ 向量检索慢 → 优化索引类型(HNSW)
          ├─ LLM 生成慢 → 用更快的模型或流式输出
          └─ Reranking 慢 → 减少候选数量
```

### 13.2 高频问题与解决方案速查表

| 问题 | 根因 | 解决方案 | 优先级 |
|------|------|----------|--------|
| 检索不到正确文档 | embedding 质量差 | 换更好的 embedding 模型 | P0 |
| 检索不到正确文档 | 用户问法和文档表述差异大 | 加 HyDE / 查询改写 | P0 |
| 检索到了但排名低 | 向量检索的排序不精确 | 加 Reranker | P0 |
| 答案包含编造内容 | LLM 幻觉 | 强化 Prompt + 降温 + 引用验证 | P0 |
| 同一问题每次答案不同 | temperature 太高 | 设 temperature=0 | P1 |
| 答案缺少关键信息 | 分块切断了完整信息 | 调分块策略 / Parent Doc | P1 |
| PDF 表格数据丢失 | PDF 解析不完整 | 换更好的 PDF 解析工具 | P1 |
| 中文检索效果差 | embedding 模型中文能力弱 | 换中文友好的模型(BGE-M3) | P0 |
| 回答太慢 (>10s) | LLM + 检索双重延迟 | 加缓存 + 流式输出 | P1 |
| 旧文档内容被返回 | 索引未更新 | 建立增量更新管线 | P1 |
| 专有名词搜不到 | 纯向量检索的局限 | 加关键词检索（混合检索） | P0 |
| 跨文档问题答不好 | 检索只看单块 | Multi-hop 检索 / Graph RAG | P2 |

### 13.3 分块问题的诊断与修复

```
症状：答案不完整或缺乏上下文

诊断步骤：
1. 打印检索到的 Top-5 块
2. 人工检查这些块：
   ├─ 块是否在句子中间被切断？ → chunk_overlap 太小
   ├─ 块是否包含多个不相关主题？ → chunk_size 太大
   ├─ 相关信息是否被分散在多个块中？ → chunk_size 太小
   └─ 代词是否找不到指代对象？ → 需要语义分块或 Agentic 分块

修复清单：
□ 尝试不同的 chunk_size（256、512、1024）
□ 增加 chunk_overlap 到 15-20%
□ 换用递归分块策略
□ 对关键文档使用 Agentic Chunking
□ 实现 Parent Document Retrieval
□ 在块的开头添加上下文信息（所属章节、文档标题）
```

---

## 第十四章：完整项目实战案例

### 14.1 项目：企业内部知识库问答系统

**需求：** 一家 500 人的科技公司，员工经常问 HR 重复的问题（年假、报销、绩效考核等）。需要构建一个能自动回答的系统。

**技术选型：**

```
文档来源：
├─ 员工手册 (PDF, 200页)
├─ 规章制度 (Word, 50份)
├─ 通知公告 (HTML, 300+份)
└─ FAQ 数据库 (Excel)

技术栈：
├─ 文档解析：PyMuPDF + python-docx + BeautifulSoup
├─ 分块策略：递归分块，chunk_size=512, overlap=64
├─ Embedding：BGE-M3（中文好，可自部署）
├─ 向量数据库：Qdrant（自部署，性能好）
├─ Reranker：bge-reranker-v2-m3
├─ LLM：Claude Sonnet（平衡性能和成本）
├─ 后端：Python FastAPI
├─ 前端：React + 企业微信集成
└─ 评估：RAGAS
```

### 14.2 实现步骤

```python
# 步骤 1：文档加载与预处理
import fitz  # PyMuPDF

def load_pdf(file_path: str) -> list[dict]:
    doc = fitz.open(file_path)
    pages = []
    for page_num, page in enumerate(doc):
        text = page.get_text()
        text = preprocess(text)  # 清洗
        pages.append({
            "text": text,
            "metadata": {
                "source": file_path,
                "page": page_num + 1,
                "total_pages": len(doc),
            }
        })
    return pages


# 步骤 2：分块
def recursive_chunk(text: str, chunk_size: int = 512,
                    overlap: int = 64) -> list[str]:
    separators = ["\n\n", "\n", "。", "！", "？", "；", " "]
    chunks = []

    for sep in separators:
        if len(text) <= chunk_size:
            chunks.append(text)
            return chunks

        parts = text.split(sep)
        current_chunk = ""

        for part in parts:
            if len(current_chunk) + len(part) <= chunk_size:
                current_chunk += part + sep
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = part + sep

        if current_chunk:
            chunks.append(current_chunk.strip())
        return chunks

    # 如果所有分隔符都无法分，按字符硬切
    for i in range(0, len(text), chunk_size - overlap):
        chunks.append(text[i:i + chunk_size])
    return chunks


# 步骤 3：向量化 + 索引
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct

embedding_model = SentenceTransformer("BAAI/bge-m3")
qdrant = QdrantClient(host="localhost", port=6333)

# 创建集合
qdrant.create_collection(
    collection_name="company_docs",
    vectors_config=VectorParams(
        size=1024,  # BGE-M3 的维度
        distance=Distance.COSINE
    )
)

# 索引文档
def index_documents(chunks: list[dict]):
    points = []
    for i, chunk in enumerate(chunks):
        embedding = embedding_model.encode(chunk["text"])
        points.append(PointStruct(
            id=i,
            vector=embedding.tolist(),
            payload={
                "text": chunk["text"],
                **chunk["metadata"]
            }
        ))

    qdrant.upsert(
        collection_name="company_docs",
        points=points,
        batch_size=100
    )


# 步骤 4：查询管线
import anthropic

client = anthropic.Anthropic()

def rag_query(question: str, top_k: int = 5) -> str:
    # 4.1 查询向量化
    query_embedding = embedding_model.encode(question)

    # 4.2 向量检索
    search_results = qdrant.search(
        collection_name="company_docs",
        query_vector=query_embedding.tolist(),
        limit=top_k * 3,  # 多取一些给 reranker
    )

    # 4.3 Reranking（此处简化，实际用 cross-encoder）
    candidates = [hit.payload["text"] for hit in search_results]
    reranked = rerank(question, candidates, top_n=top_k)

    # 4.4 Context 构建
    context = build_context(reranked)

    # 4.5 LLM 生成
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        system=RAG_SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": f"参考资料：\n{context}\n\n问题：{question}"
        }]
    )

    return response.content[0].text
```

### 14.3 评估结果示例

```
评估集：100 个标注好的 HR 问答对

版本 1（基础 RAG）：
├─ Faithfulness:      0.78
├─ Answer Relevancy:  0.72
├─ Context Precision: 0.65
└─ Context Recall:    0.70

版本 2（+Reranking +混合检索）：
├─ Faithfulness:      0.88 (+0.10)
├─ Answer Relevancy:  0.85 (+0.13)
├─ Context Precision: 0.82 (+0.17)
└─ Context Recall:    0.85 (+0.15)

版本 3（+查询改写 +优化分块 +调优 Prompt）：
├─ Faithfulness:      0.93 (+0.05)
├─ Answer Relevancy:  0.91 (+0.06)
├─ Context Precision: 0.88 (+0.06)
└─ Context Recall:    0.90 (+0.05)
```

---

## 第十五章：AI 应用工程师成长路线图

### 15.1 完整学习路径

```
阶段 1：基础能力（1-2 个月）
├─ ✅ Prompt Engineering（你已完成）
├─ → RAG 系统构建（你正在学）
│   ├─ 分块策略
│   ├─ Embedding 模型
│   ├─ 向量数据库
│   ├─ 检索优化
│   └─ 评估体系
└─ Python 基础 + API 调用

阶段 2：核心技能（2-3 个月）
├─ Agent / Function Calling
│   ├─ ReAct 模式
│   ├─ 工具使用（Tool Use）
│   └─ 多 Agent 编排
├─ 评估与优化
│   ├─ LLM-as-Judge
│   ├─ A/B 测试
│   └─ 持续监控
└─ 数据处理管线
    ├─ ETL for AI
    ├─ 数据清洗
    └─ 质量控制

阶段 3：进阶能力（2-3 个月）
├─ Fine-tuning（微调）
│   ├─ 数据准备
│   ├─ LoRA / QLoRA
│   └─ 评估微调效果
├─ 多模态应用
│   ├─ Vision（图像理解）
│   ├─ 语音（STT/TTS）
│   └─ 视频理解
├─ 安全与合规
│   ├─ Prompt 攻防
│   ├─ 数据隐私
│   └─ 内容安全
└─ 前沿技术
    ├─ Graph RAG
    ├─ MCP（Model Context Protocol）
    └─ Computer Use

阶段 4：工程化能力（持续）
├─ 生产部署
│   ├─ 容器化（Docker/K8s）
│   ├─ CI/CD
│   └─ 监控告警
├─ 性能优化
│   ├─ 缓存策略
│   ├─ 批处理
│   └─ 流式输出
└─ 成本控制
    ├─ Token 优化
    ├─ 模型选择策略
    └─ Prompt Caching
```

### 15.2 面试高频考题

| 考题 | 考察点 |
|------|--------|
| RAG 和 Fine-tuning 什么时候用哪个？ | 技术选型能力 |
| chunk_size 怎么选？依据是什么？ | 分块理解深度 |
| 检索效果不好怎么排查？ | 问题诊断能力 |
| 怎么评估 RAG 系统的质量？ | 评估体系理解 |
| 向量数据库怎么选型？ | 架构设计能力 |
| 怎么处理 PDF 中的表格？ | 工程细节 |
| RAG 系统的幻觉怎么减少？ | 系统优化能力 |
| 生产环境中怎么做增量更新？ | 工程化能力 |
| 怎么处理多语言检索？ | 技术广度 |
| 你做过的最有挑战性的 RAG 项目？ | 实战经验 |

### 15.3 推荐学习资源

**官方文档（必读）：**

- Anthropic Claude 文档（Prompt Engineering 最佳实践）
- OpenAI Cookbook（RAG 相关章节）
- LlamaIndex 文档（RAG 框架使用）
- LangChain 文档（另一个主流框架）

**开源项目（动手做）：**

- LlamaIndex：最成熟的 RAG 框架
- LangChain：生态最大的 LLM 应用框架
- RAGAS：RAG 评估工具
- ChromaDB / Qdrant：向量数据库

**论文（深入理解）：**

- "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks"（RAG 原始论文）
- "Lost in the Middle"（位置效应研究）
- "Self-RAG"（自适应检索）
- "RAPTOR"（递归摘要树增强检索）

### 15.4 下一步学习建议

```
学完这份 RAG 指南后，你应该：

立即做：
├─ 搭建一个最简 RAG demo（用 ChromaDB + Claude API）
├─ 用自己的文档（比如公司手册）测试效果
└─ 建立一个 10-20 个问题的评估集

一周内做：
├─ 尝试不同的分块策略，用评估集对比效果
├─ 试用 2-3 个 embedding 模型，对比检索质量
├─ 加入 Reranker，观察效果提升
└─ 实现混合检索（向量 + BM25）

两周内做：
├─ 用 RAGAS 建立正式的评估管线
├─ 实现查询改写（HyDE / Multi-Query）
├─ 部署到服务器，加入 API 接口
└─ 添加用户反馈收集功能

然后进入下一个主题：Agent / Function Calling
```

---

> **记住：RAG 的核心不是任何单一技术，而是"如何让正确的信息在正确的时间出现在 LLM 的上下文中"。** 围绕这个目标，所有技术选择都应该被评估数据驱动，而不是追逐最新最炫的方案。先做对，再做好，最后做快。
