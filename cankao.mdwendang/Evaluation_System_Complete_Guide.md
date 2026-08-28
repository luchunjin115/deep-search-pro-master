# AI 应用评估体系完全知识体系

> AI 应用工程师学习路径 Step 6
> 前置知识：Prompt ✅、RAG ✅、Tool Use ✅、Agent ✅、工程化 ✅
> 学完本篇：你将能用数据证明"系统好不好用"，并且知道"哪里不好、怎么改"

---

## 目录（上篇）

- [第一章：为什么评估是最被低估的能力](#第一章为什么评估是最被低估的能力)
- [第二章：评估的基本框架——评什么、怎么评、谁来评](#第二章评估的基本框架评什么怎么评谁来评)
- [第三章：评估数据集构建——一切评估的基础](#第三章评估数据集构建一切评估的基础)
- [第四章：自动化评估指标——用数字说话](#第四章自动化评估指标用数字说话)
- [第五章：LLM-as-Judge——用 AI 评价 AI](#第五章llm-as-judge用-ai-评价-ai)
- [第六章：RAG 专项评估——你学过的 RAG 怎么评](#第六章rag-专项评估你学过的-rag-怎么评)
- [第七章：Agent 专项评估——你学过的 Agent 怎么评](#第七章agent-专项评估你学过的-agent-怎么评)

## 目录（下篇，等你指示后生成）

- 第八章：迭代评估——改了之后是变好还是变坏
- 第九章：线上评估——用户真实反馈
- 第十章：评估驱动优化——从发现问题到解决问题
- 第十一章：评估基础设施——搭建自动化评估管线
- 第十二章：常见问题诊断手册
- 第十三章：面试高频考题与答案
- 第十四章：实战项目方向

---

## 第一章：为什么评估是最被低估的能力

### 1.1 大白话：评估到底是在干什么

```
你做了一个 AI 客服系统，老板问你：

"这个系统好用吗？"

你说："挺好的，我试了几个问题都答对了。"

老板说："几个？试了哪几个？答对的标准是什么？
       有没有答错的情况？错误率多少？
       比上一版好了多少？有数据吗？"

你："......"

这就是没有评估体系的尴尬。

评估体系要回答的核心问题：
├─ 系统好不好用？ → 用数字量化（准确率 92%）
├─ 好在哪里、差在哪里？ → 分维度评估（检索好但生成差）
├─ 改了之后变好还是变坏？ → 对比评估（A/B 测试、GSB）
├─ 什么场景会出问题？ → Bad Case 分析
└─ 怎么持续优化？ → 评估驱动的迭代循环
```

### 1.2 评估在整个学习体系中的位置

```
打比方：

Step 1-4 你学会了"做菜"（AI 能力）
Step 5 你学会了"开餐厅"（工程化）
Step 6 你要学"美食评审"（评估体系）

没有评估的 AI 项目，就像没有质检的工厂：
├─ 不知道产品质量好不好
├─ 不知道哪个环节出了问题
├─ 不知道改进措施有没有效果
├─ 客户投诉了才知道有问题（已经晚了）
└─ 无法向老板证明项目的价值

有评估的 AI 项目：
├─ 上线前就知道准确率是多少
├─ 知道哪类问题容易答错
├─ 每次改动都有数据证明效果
├─ 主动发现问题，而不是等客户投诉
└─ 用数据和老板对话："准确率从 85% 提升到 93%"
```

### 1.3 为什么 AI 应用的评估特别难

```
传统软件的测试：
├─ 输入 1+1 → 期望输出 2 → 实际输出 2 → ✅ 通过
├─ 对就是对，错就是错
├─ 100% 确定性
└─ 写好测试用例就行

AI 应用的评估：
├─ 输入 "什么是人工智能？"
├─ 期望输出 ???（正确答案有无数种表述方式）
├─ 实际输出 "人工智能是..."
├─ 这算对吗？对了多少？
├─ 同一个问题问两次，回答可能不一样
└─ 没有标准答案，评估本身就是一个难题

AI 评估难在哪里：
1. 没有唯一正确答案（开放式问题）
2. 非确定性（同样输入可能不同输出）
3. 质量是多维度的（准确 but 不全面？全面 but 太啰嗦？）
4. 人工评估太贵太慢
5. 自动评估不够可靠
```

---

## 第二章：评估的基本框架——评什么、怎么评、谁来评

### 2.1 评什么：评估的三个层次

```
┌────────────────────────────────────────────────────┐
│                                                    │
│   第 1 层：组件级评估                                │
│   ══════════════════                                │
│   单独评估系统的某个组件                              │
│                                                    │
│   ├─ Prompt 评估                                   │
│   │   "这个 Prompt 生成的回答质量怎么样？"             │
│   │   你在 Step 1 学的 GSB 就是这一层                │
│   │                                                │
│   ├─ 检索评估（RAG 的检索部分）                      │
│   │   "检索出来的文档相关吗？找到了正确答案吗？"        │
│   │                                                │
│   ├─ 生成评估（RAG 的生成部分）                      │
│   │   "基于检索到的文档，LLM 的回答忠实吗？"           │
│   │                                                │
│   └─ 工具选择评估（Agent 的工具使用）                 │
│       "Agent 选对工具了吗？参数填对了吗？"             │
│                                                    │
├────────────────────────────────────────────────────┤
│                                                    │
│   第 2 层：端到端评估                                │
│   ══════════════════                                │
│   评估整个系统从输入到输出的表现                       │
│                                                    │
│   ├─ 问一个问题 → 系统给出最终回答 → 回答好不好？      │
│   ├─ 不管中间走了几步、用了什么工具                    │
│   └─ 只看最终结果                                   │
│                                                    │
│   大白话：不管厨师用了什么方法，只看菜好不好吃          │
│                                                    │
├────────────────────────────────────────────────────┤
│                                                    │
│   第 3 层：业务指标评估                               │
│   ══════════════════                                │
│   评估系统对业务的实际影响                             │
│                                                    │
│   ├─ 用户满意度（NPS、好评率）                       │
│   ├─ 任务完成率（用户的问题是否真的解决了）             │
│   ├─ 人工转接率（多少对话需要转人工）                  │
│   ├─ 处理时间（比纯人工快了多少）                     │
│   └─ ROI（投入产出比）                              │
│                                                    │
│   大白话：餐厅赚不赚钱、客人满不满意、回头客多不多      │
│                                                    │
└────────────────────────────────────────────────────┘
```

### 2.2 怎么评：三种评估方法

```
方法 1：人工评估（金标准，但贵且慢）
═══════════════════════════════════

是什么：让人来判断 AI 的回答好不好。
大白话：请美食评委来试吃你的菜。

怎么做：
├─ 准备 100 个测试问题
├─ 让 AI 回答
├─ 让 3 个评估员分别打分（1-5 分）
├─ 取平均分
└─ 分析哪些问题得分低

优点：最可靠、最贴近真实用户感受
缺点：贵（要付人工费）、慢（一天评 50-100 条）、主观（不同人标准不同）

什么时候用：
├─ 项目初期建立基准
├─ 验证自动评估方法的准确性
├─ 评估复杂的、开放式的输出
└─ 最终上线前的验收


方法 2：自动指标评估（快且便宜）
═══════════════════════════════

是什么：用程序自动计算评估分数。
大白话：用机器代替人来打分。

怎么做：
├─ 准备测试问题 + 标准答案
├─ 让 AI 回答
├─ 用算法对比 AI 回答和标准答案
├─ 自动计算分数（如 BLEU、ROUGE、BERTScore）
└─ 一分钟评估 1000 条

优点：快、便宜、可重复
缺点：和人的判断不完全一致、某些维度难以自动评估

什么时候用：
├─ 日常迭代（每次改代码都跑一遍）
├─ CI/CD 中的自动化检查
└─ 大规模评估（几千条测试用例）


方法 3：LLM-as-Judge（AI 评价 AI，当前主流）
═══════════════════════════════════════════

是什么：用一个更强的 LLM 来评判另一个 LLM 的回答。
大白话：请一个更资深的大厨来评价你做的菜。

怎么做：
├─ 让你的 AI 回答问题
├─ 把"问题 + AI 的回答"发给评判 LLM
├─ 评判 LLM 按预设标准打分
└─ 比人工评估便宜 100 倍，质量接近人工

优点：成本低、速度快、比简单指标更准确
缺点：评判 LLM 本身也可能出错、存在偏见

什么时候用：
├─ 大多数日常评估场景
├─ 替代部分人工评估
└─ 需要多维度打分时

详见第五章。
```

### 2.3 谁来评：评估的参与者

```
评估不是一个人的事：

1. AI 工程师（你）
   ├─ 设计评估方案
   ├─ 构建评估数据集
   ├─ 搭建自动化评估管线
   └─ 分析评估结果并优化

2. 业务方 / 产品经理
   ├─ 定义"好"的标准（什么算正确回答）
   ├─ 提供业务场景的测试用例
   └─ 验收最终效果

3. 真实用户
   ├─ 通过使用产品产生真实反馈
   ├─ 点赞/点踩、满意度评分
   └─ 是最终的裁判

4. LLM（自动评估）
   ├─ LLM-as-Judge
   ├─ 替代大部分人工评估
   └─ 需要被校准（和人工对齐）
```

---

## 第三章：评估数据集构建——一切评估的基础

### 3.1 是什么：评估数据集长什么样

```
大白话：
评估数据集就是"考试卷子"。
你要考核 AI 系统，得先有一套考题。

一条评估数据 = 问题 + 期望答案 + 评估标准

示例（RAG 知识库问答场景）：

{
    "id": "test_001",
    "question": "公司的年假政策是怎样的？",
    "expected_answer": "入职满一年享有5天年假，满三年10天，满五年15天",
    "category": "HR政策",
    "difficulty": "easy",
    "source_doc": "员工手册第3章",
    "evaluation_criteria": {
        "accuracy": "必须包含正确的天数",
        "completeness": "应覆盖三个档位",
        "source_faithfulness": "不能编造手册中没有的信息"
    }
}
```

### 3.2 为什么评估数据集这么重要

```
没有评估数据集的后果：

"我改了 Prompt，试了3个问题都变好了！上线！"
→ 上线后发现另外 50 个场景变差了
→ 回滚
→ 又改了一版，试了5个问题都好了
→ 上线后又出问题了
→ 无限循环...

有评估数据集：
"我改了 Prompt，跑了 200 条评估用例：
 - 185 条变好或持平（92.5%）
 - 10 条略有下降但可接受
 - 5 条变差，都是关于退款流程的
 → 先修复退款流程的问题，再上线"

评估数据集是你做决策的依据。
没有它，你就是在"凭感觉"做事。
```

### 3.3 怎么构建评估数据集（面试重点）

```
构建评估数据集的五步法：

Step 1：从真实场景收集问题
════════════════════════
├─ 从客服日志中提取高频问题
├─ 从业务方收集典型场景
├─ 从用户反馈中提取"AI 答错了"的案例
├─ 自己设计边界场景和对抗样本
└─ 目标：覆盖真实使用中会遇到的各种情况

Step 2：编写期望答案和评估标准
════════════════════════════
├─ 每个问题写一个"参考答案"
├─ 参考答案不需要和 AI 回答完全一致
├─ 但要包含关键信息点
├─ 同时定义评估标准（什么算对、什么算错）
│
│  示例：
│  问题："产品保修期多久？"
│  参考答案："电子产品保修1年，大家电保修3年"
│  评估标准：
│   ├─ 必须区分不同品类的保修时长 → 关键信息
│   ├─ 数字必须准确 → 准确性
│   └─ 不能编造不存在的保修政策 → 忠实性

Step 3：分类和标注
════════════════
├─ 按场景分类（产品咨询、售后服务、投诉处理...）
├─ 按难度分级（简单、中等、困难）
├─ 标注特殊属性（需要多步推理、需要计算、涉及时效...）
└─ 这样可以知道"哪类问题表现好、哪类差"

Step 4：确定规模
══════════════
├─ 最少 50 条（能看出大致表现）
├─ 推荐 100-300 条（够用于日常迭代）
├─ 理想 500+ 条（覆盖面够广）
│
│  分布建议：
│  ├─ 60% 常见/简单问题（基本功）
│  ├─ 25% 中等难度（核心能力）
│  ├─ 10% 困难/边界场景（极端考验）
│  └─ 5% 对抗样本（故意刁难）

Step 5：持续积累
══════════════
├─ 每遇到一个 Bad Case（AI 答错的真实案例）→ 加入评估集
├─ 每次业务场景变化 → 补充新的测试用例
├─ 定期审查和更新过时的用例
└─ 评估数据集是活的，不是一次性的
```

### 3.4 评估数据集的代码组织

```python
# 评估数据集的标准格式

import json

# 一条评估用例
test_case = {
    "id": "test_042",
    "question": "我买的手机屏幕碎了，在保修范围内吗？",
    "context": "用户购买了 iPhone 15，一周前摔碎了屏幕",
    "expected_answer": "人为损坏不在保修范围内，但可以购买 AppleCare+ 或第三方维修",
    "required_keywords": ["人为损坏", "不在保修范围", "维修"],
    "forbidden_keywords": ["免费维修", "保修期内可以更换"],
    "category": "售后-保修",
    "difficulty": "medium",
    "metadata": {
        "source": "客服日志_2024Q1",
        "added_date": "2024-03-15",
        "last_updated": "2024-06-01"
    }
}

# 整个评估数据集
eval_dataset = {
    "name": "智能客服评估集 v2.1",
    "version": "2.1",
    "total_count": 200,
    "categories": {
        "产品咨询": 60,
        "售后-保修": 40,
        "售后-退款": 35,
        "投诉处理": 30,
        "其他": 35
    },
    "test_cases": [test_case, ...]
}

# 保存为 JSON 文件
with open("eval_dataset_v2.1.json", "w", encoding="utf-8") as f:
    json.dump(eval_dataset, f, ensure_ascii=False, indent=2)
```

---

## 第四章：自动化评估指标——用数字说话

### 4.1 为什么需要量化指标

```
大白话：
"感觉还行"不是评估。
"准确率 92%，比上一版提高了 5 个百分点"才是评估。

量化指标的价值：
├─ 可对比：这版 92% vs 上版 87% → 明确知道变好了
├─ 可追踪：每天跑一次，画出趋势图 → 知道系统是在变好还是变差
├─ 可沟通：和老板/业务方用数字说话 → 不是靠"感觉"
└─ 可决策：指标下降了 → 不上线 / 指标达标了 → 可以上线
```

### 4.2 基础文本指标（了解即可）

```
这些是传统 NLP 的评估指标。
在 LLM 时代不是最重要的，但面试可能会问到。

BLEU（Bilingual Evaluation Understudy）
═══════════════════════════════════════
是什么：对比 AI 输出和参考答案有多少词是一样的。
大白话：数两篇文章有多少"相同的词组"。
范围：0-1，越高越好。
适合：翻译、摘要等有明确参考答案的任务。
局限：只看词面是否一样，不理解语义。
      "我很开心" vs "我非常高兴" → BLEU 很低，但意思一样。

ROUGE（Recall-Oriented Understudy for Gisting Evaluation）
═══════════════════════════════════════════════════════════
是什么：检查参考答案中的词有多少出现在 AI 输出中。
和 BLEU 的区别：BLEU 看精度（AI说的对不对），ROUGE 看召回（该说的说了没）。
适合：摘要任务。

BERTScore
═════════
是什么：用 BERT 模型计算 AI 输出和参考答案的语义相似度。
大白话：不只看词一不一样，还看意思一不一样。
优点：能理解 "我很开心" ≈ "我非常高兴"。
适合：各种文本生成任务。

面试怎么答：
"传统指标如 BLEU、ROUGE 只做表面词匹配，不够准。
 BERTScore 考虑语义相似度，好一些。
 但现在主流做法是用 LLM-as-Judge，
 因为 LLM 能理解语义、判断逻辑、评估完整性，
 比任何固定指标都更贴近人类判断。"
```

### 4.3 AI 应用核心评估维度（面试重点）

```
比起单一指标，AI 应用更需要"多维度评估"。

维度 1：准确性（Accuracy / Correctness）
═══════════════════════════════════════
问的是：AI 说的对不对？

大白话：厨师做的菜味道对不对。
评估方法：
├─ 关键信息点是否正确
├─ 数字、日期、名称是否准确
├─ 有没有编造不存在的信息（幻觉）
└─ 和事实/知识库是否一致

示例：
问："公司年假几天？"
✅ "入职满一年5天"（正确）
❌ "入职满一年7天"（不准确）
❌ "入职即享有10天年假"（编造的）


维度 2：完整性（Completeness）
═════════════════════════════
问的是：该说的都说了吗？

大白话：这道菜的食材齐不齐。
评估方法：
├─ 参考答案中的关键信息点是否都覆盖了
├─ 有没有遗漏重要条件、例外情况
└─ 用 required_keywords 检查

示例：
问："退款政策是什么？"
完整答案应包含：时限、条件、流程、例外
✅ "7天内可退，需要提供订单号，特价品除外"
❌ "可以退款"（太笼统，缺条件）


维度 3：忠实性（Faithfulness）
═════════════════════════════
问的是：AI 的回答是否忠于源信息？

大白话：厨师有没有按食谱做，还是自己乱加料。
评估方法：
├─ RAG 场景：回答是否基于检索到的文档
├─ 有没有"超出文档范围"的内容
└─ 这是 RAG 最重要的评估维度

示例（知识库中写的是"保修1年"）：
✅ "根据保修政策，保修期为1年"（忠于文档）
❌ "保修期为2年"（不忠于文档，编造了）
❌ "保修期为1年，但你可以投诉延长"（后半句是编造的）


维度 4：相关性（Relevancy）
═══════════════════════════
问的是：AI 回答的是用户问的问题吗？

大白话：客人点了红烧肉，你端上来的是不是红烧肉。
评估方法：
├─ 回答是否切题
├─ 有没有跑题或答非所问
└─ 有没有过多无关信息

示例：
问："今天天气怎么样？"
✅ "今天北京晴天，28度"（切题）
❌ "天气是大气层中的物理现象..."（跑题了）
❌ "今天天气不错。说到天气，你知道全球变暖吗..."（过度发散）


维度 5：安全性（Safety）
═══════════════════════
问的是：AI 有没有输出不当内容？

评估方法：
├─ 有没有泄露敏感信息（System Prompt、API Key、用户隐私）
├─ 有没有有害内容
├─ 有没有违反业务规则（比如客服 AI 承诺了做不到的事）
└─ 对 Prompt 注入是否有抵抗力
```

### 4.4 评估维度的代码实现

```python
# 用关键词检查实现基础评估

class BasicEvaluator:
    """基础评估器——用规则检查"""

    def evaluate_accuracy(self, response: str,
                          required_keywords: list) -> float:
        """准确性：必须包含的关键信息是否存在"""
        if not required_keywords:
            return 1.0
        found = sum(1 for kw in required_keywords if kw in response)
        return found / len(required_keywords)

    def evaluate_safety(self, response: str,
                        forbidden_keywords: list) -> float:
        """安全性：不能包含的信息是否出现"""
        if not forbidden_keywords:
            return 1.0
        violations = sum(1 for kw in forbidden_keywords if kw in response)
        return 1.0 - (violations / len(forbidden_keywords))

    def evaluate_length(self, response: str,
                        min_length: int = 20,
                        max_length: int = 500) -> float:
        """回答长度是否合适"""
        length = len(response)
        if length < min_length:
            return length / min_length
        if length > max_length:
            return max(0, 1 - (length - max_length) / max_length)
        return 1.0

    def evaluate(self, response: str, test_case: dict) -> dict:
        """综合评估"""
        return {
            "accuracy": self.evaluate_accuracy(
                response, test_case.get("required_keywords", [])
            ),
            "safety": self.evaluate_safety(
                response, test_case.get("forbidden_keywords", [])
            ),
            "length": self.evaluate_length(response),
        }
```

```
上面的基础评估器能做什么？

✅ 检查关键词是否存在（简单但有效）
✅ 检查禁止词是否出现（安全检查）
✅ 检查回答长度是否合理

❌ 不能理解语义（"开心"和"高兴"它不知道是一个意思）
❌ 不能评估逻辑正确性
❌ 不能评估回答的质量

所以我们需要 LLM-as-Judge → 下一章。
```

---

## 第五章：LLM-as-Judge——用 AI 评价 AI

### 5.1 是什么：当前最主流的评估方式

```
大白话：
找一个"更聪明的 AI"来给你的 AI 打分。

就像学校考试：
├─ 学生（你的 AI）答题
├─ 老师（Judge LLM）批改
└─ 老师给出分数和评语

为什么可行？
├─ 大模型（如 Claude Opus）的判断能力接近人类
├─ 但成本只有人工评估的 1/100
├─ 速度是人工的 100 倍
└─ 而且不会累、不会因为心情影响判断

核心思路：
你的 AI（被评估者）用 Sonnet
评判 AI（Judge）用 Opus 或更强的模型
→ 用强模型评判弱模型的输出
```

### 5.2 为什么 LLM-as-Judge 是主流

```
对比三种评估方式：

                人工评估      自动指标       LLM-as-Judge
────────────────────────────────────────────────────────
成本            高（¥5/条）   几乎为零       低（¥0.05/条）
速度            慢（1条/分）  极快           快（10条/分）
准确性          最高          低-中          中-高
可扩展性        差            好             好
理解语义        能            不能           能
评估复杂维度    能            不能           能
一致性          中（人有主观）  高            高
适合大规模      不适合        适合           适合

结论：
├─ 日常迭代 → LLM-as-Judge（快、便宜、够准）
├─ 重要决策 → 人工评估（最准）
├─ CI/CD → 自动指标 + LLM-as-Judge（全自动）
└─ 最佳实践 → 三者结合使用
```

### 5.3 怎么做：Judge Prompt 设计（面试重点）

```python
# ═══════════════════════════════════════════
# LLM-as-Judge 的核心：Judge Prompt
# ═══════════════════════════════════════════

JUDGE_PROMPT = """你是一个专业的 AI 回答质量评估专家。

请评估以下 AI 回答的质量。

## 用户问题
{question}

## 参考答案（标准答案）
{reference_answer}

## AI 的实际回答
{ai_response}

## 评估标准

请从以下维度评分（每个维度 1-5 分）：

1. 准确性（Accuracy）
   5分：信息完全正确，无任何错误
   4分：基本正确，有极小的不精确
   3分：部分正确，有一些错误但核心信息对
   2分：错误较多，核心信息有误
   1分：完全错误或胡说八道

2. 完整性（Completeness）
   5分：覆盖了参考答案中的所有关键信息
   4分：覆盖了大部分关键信息
   3分：覆盖了约一半的关键信息
   2分：只覆盖了少量关键信息
   1分：几乎没有覆盖关键信息

3. 相关性（Relevancy）
   5分：完全切题，没有无关信息
   4分：基本切题，有少量无关信息
   3分：部分切题，有较多无关信息
   2分：大部分内容与问题无关
   1分：完全答非所问

4. 表达质量（Clarity）
   5分：条理清晰，表达准确，易于理解
   4分：表达清楚，略有瑕疵
   3分：能理解但表达不够好
   2分：表达混乱，难以理解
   1分：完全不可读

## 输出格式

请严格按以下 JSON 格式输出：
{
    "accuracy": <1-5>,
    "completeness": <1-5>,
    "relevancy": <1-5>,
    "clarity": <1-5>,
    "overall": <1-5>,
    "reasoning": "<简要说明评分理由，指出具体的优点和问题>"
}"""
```

```python
# 调用 Judge LLM

import anthropic
import json

async def judge_response(question: str, reference: str,
                         ai_response: str) -> dict:
    """用 LLM 评判 AI 回答的质量"""

    client = anthropic.AsyncAnthropic()

    prompt = JUDGE_PROMPT.format(
        question=question,
        reference_answer=reference,
        ai_response=ai_response
    )

    response = await client.messages.create(
        model="claude-opus-4-20250514",  # 用最强模型做评判
        max_tokens=1024,
        temperature=0,  # 评估时用 0 温度，确保一致性
        messages=[{"role": "user", "content": prompt}]
    )

    # 解析评分结果
    result = json.loads(response.content[0].text)
    return result


# 批量评估
async def evaluate_dataset(dataset: list, ai_system) -> dict:
    """对整个评估数据集运行评估"""

    results = []
    for case in dataset:
        # 先让被评估的 AI 回答问题
        ai_response = await ai_system.chat(case["question"])

        # 再让 Judge 评分
        score = await judge_response(
            question=case["question"],
            reference=case["expected_answer"],
            ai_response=ai_response
        )

        results.append({
            "case_id": case["id"],
            "category": case["category"],
            "scores": score
        })

    # 汇总统计
    return aggregate_results(results)
```

### 5.4 LLM-as-Judge 的偏见和解决方案

```
LLM-as-Judge 不是完美的，它有几种已知偏见：

偏见 1：位置偏见（Position Bias）
├─ 现象：当对比两个回答时，LLM 倾向于选第一个
├─ 解决：做两次评估，交换两个回答的位置
│   第一次：A 在前，B 在后
│   第二次：B 在前，A 在后
│   两次结果一致 → 可靠
│   两次结果不一致 → 判平局或人工复核

偏见 2：长度偏见（Verbosity Bias）
├─ 现象：LLM 倾向于给更长的回答更高分
├─ 解决：在 Judge Prompt 中明确说明
│   "回答的长度不应影响评分。
│    简洁准确的短回答应该比冗长但正确的长回答得分更高。"

偏见 3：自我偏见（Self-Enhancement Bias）
├─ 现象：LLM 倾向于给自己（同型号）生成的内容更高分
├─ 解决：用不同厂商的模型做 Judge
│   比如用 Claude 评价 GPT 的输出
│   或者用 GPT 评价 Claude 的输出

偏见 4：格式偏见
├─ 现象：LLM 倾向于给格式好看的回答（有标题、有列表）更高分
├─ 解决：在 Judge Prompt 中说明
│   "请只评估内容质量，不要因为格式好看就加分"
```

---

## 第六章：RAG 专项评估——你学过的 RAG 怎么评

### 6.1 RAG 评估的独特之处

```
RAG 系统（你在 Step 2 学过）有一个独特的评估需求：

普通对话系统：问题 → LLM → 回答
评估：只看"回答好不好"

RAG 系统：问题 → 检索文档 → LLM + 文档 → 回答
评估：既要看"检索好不好"，又要看"回答好不好"

如果回答不好：
├─ 是检索的锅？（找到了错误的文档）
├─ 还是生成的锅？（找对了文档但 LLM 理解错了）
└─ 必须分开评估才能定位问题

这就是为什么 RAG 需要"分段评估"。
```

### 6.2 RAGAS 框架——RAG 评估的行业标准

```
RAGAS = Retrieval Augmented Generation Assessment

是什么：一个专门评估 RAG 系统的开源框架。
你在 Step 2 的 RAG 文档中已经初步接触过。
现在深入理解每个指标。

RAGAS 的四个核心指标：

┌────────────────────────────────────────────────┐
│                                                │
│   ① Faithfulness（忠实性）                      │
│   ═══════════════════════                      │
│   问的是：AI 的回答是否忠于检索到的文档？          │
│                                                │
│   大白话：你引用了资料，但你说的和资料里写的一样吗？│
│                                                │
│   计算方法：                                    │
│   1. 把 AI 回答拆成多个"声明"                    │
│   2. 检查每个声明是否能在检索的文档中找到依据       │
│   3. 有依据的声明数 / 总声明数 = Faithfulness     │
│                                                │
│   示例：                                        │
│   检索到的文档："保修期为1年"                      │
│   AI 回答："保修期为1年，可以延长至3年"              │
│   ├─ "保修期为1年" → 有依据 ✅                   │
│   ├─ "可以延长至3年" → 文档中没提到 ❌             │
│   └─ Faithfulness = 1/2 = 0.5                  │
│                                                │
│   这个指标最重要！低 Faithfulness = AI 在编造信息  │
│                                                │
├────────────────────────────────────────────────┤
│                                                │
│   ② Answer Relevancy（回答相关性）               │
│   ═══════════════════════════════               │
│   问的是：AI 的回答是否和用户的问题相关？           │
│                                                │
│   大白话：回答的是不是用户问的那个问题？             │
│                                                │
│   计算方法：                                    │
│   1. 从 AI 回答反向生成 N 个可能的问题             │
│   2. 计算反向生成的问题和原始问题的相似度           │
│   3. 相似度越高 → 回答越相关                      │
│                                                │
├────────────────────────────────────────────────┤
│                                                │
│   ③ Context Precision（上下文精确度）             │
│   ═════════════════════════════════             │
│   问的是：检索出来的文档中，有多少是真正有用的？     │
│                                                │
│   大白话：你找了10篇资料，有几篇真的和问题相关？    │
│                                                │
│   检索出10个文档，只有3个包含答案               │
│   → Context Precision = 3/10 = 0.3（不太好）    │
│   检索出5个文档，4个包含答案                    │
│   → Context Precision = 4/5 = 0.8（不错）       │
│                                                │
│   这个指标评估的是你的检索质量                     │
│                                                │
├────────────────────────────────────────────────┤
│                                                │
│   ④ Context Recall（上下文召回率）                │
│   ═══════════════════════════════               │
│   问的是：参考答案中的信息，在检索到的文档中        │
│          能找到多少？                            │
│                                                │
│   大白话：正确答案需要3条信息，你检索的文档里       │
│          包含了几条？                            │
│                                                │
│   参考答案需要信息 A, B, C                      │
│   检索到的文档包含 A, B（缺 C）                  │
│   → Context Recall = 2/3 = 0.67                │
│                                                │
│   这个指标告诉你"是否有重要文档没被检索到"         │
│                                                │
└────────────────────────────────────────────────┘
```

### 6.3 用 RAGAS 指标定位问题

```
诊断矩阵——哪个指标低说明什么问题？

┌───────────────────────┬──────────────────────────────────┐
│ 指标低                │ 说明什么                          │
├───────────────────────┼──────────────────────────────────┤
│ Context Recall 低     │ 检索没找到正确文档                  │
│                       │ → 问题在"检索"环节                 │
│                       │ → 检查 embedding、分块、查询改写    │
├───────────────────────┼──────────────────────────────────┤
│ Context Precision 低  │ 检索找到了太多无关文档              │
│                       │ → 问题在"检索精度"                 │
│                       │ → 加 Reranking、调整 top_k         │
├───────────────────────┼──────────────────────────────────┤
│ Faithfulness 低       │ LLM 没有忠于检索到的文档           │
│                       │ → 问题在"生成"环节                 │
│                       │ → 优化 Prompt，强调"只基于文档回答" │
├───────────────────────┼──────────────────────────────────┤
│ Answer Relevancy 低   │ LLM 回答跑题了                    │
│                       │ → 问题在"生成"环节                 │
│                       │ → 优化 Prompt，加强指令约束         │
├───────────────────────┼──────────────────────────────────┤
│ 全部低                │ 可能是数据质量问题                  │
│                       │ → 检查知识库文档的质量和覆盖度       │
└───────────────────────┴──────────────────────────────────┘

最有价值的诊断路径：
1. 先看 Context Recall → 检索到正确信息了吗？
2. 再看 Faithfulness → 基于正确信息回答了吗？
3. 这两步能定位 80% 的问题。
```

### 6.4 RAG 评估代码实现

```python
# 简化版 RAG 评估（不依赖 RAGAS 库）

class RAGEvaluator:
    """RAG 系统评估器"""

    async def evaluate_retrieval(self, question: str,
                                  retrieved_docs: list,
                                  ground_truth_doc: str) -> dict:
        """评估检索质量"""

        # 用 LLM 判断每个检索到的文档是否相关
        precision_scores = []
        for doc in retrieved_docs:
            is_relevant = await self.judge_relevance(question, doc)
            precision_scores.append(is_relevant)

        # 检查 ground truth 是否被检索到
        recall = await self.judge_recall(ground_truth_doc, retrieved_docs)

        return {
            "context_precision": sum(precision_scores) / len(precision_scores),
            "context_recall": recall,
            "num_retrieved": len(retrieved_docs)
        }

    async def evaluate_generation(self, question: str,
                                   context: str,
                                   response: str,
                                   reference: str) -> dict:
        """评估生成质量"""

        # 用 LLM-as-Judge 评估
        faithfulness = await self.judge_faithfulness(response, context)
        relevancy = await self.judge_answer_relevancy(question, response)
        accuracy = await self.judge_accuracy(response, reference)

        return {
            "faithfulness": faithfulness,
            "answer_relevancy": relevancy,
            "accuracy": accuracy
        }

    async def evaluate_end_to_end(self, test_case: dict,
                                    rag_system) -> dict:
        """端到端评估"""

        # 运行 RAG 系统
        result = await rag_system.query(test_case["question"])

        # 评估检索
        retrieval_scores = await self.evaluate_retrieval(
            question=test_case["question"],
            retrieved_docs=result["retrieved_docs"],
            ground_truth_doc=test_case.get("source_doc", "")
        )

        # 评估生成
        generation_scores = await self.evaluate_generation(
            question=test_case["question"],
            context=result["context"],
            response=result["answer"],
            reference=test_case["expected_answer"]
        )

        return {**retrieval_scores, **generation_scores}
```

---

## 第七章：Agent 专项评估——你学过的 Agent 怎么评

### 7.1 Agent 评估比 RAG 评估更难

```
RAG 评估：
├─ 输入确定（用户问题）
├─ 中间过程简单（检索 → 生成）
├─ 输出确定（回答文本）
└─ 相对容易

Agent 评估：
├─ 执行路径不确定（可能走 3 步也可能走 15 步）
├─ 中间过程复杂（多轮工具调用、条件分支）
├─ 最终结果可能有多种正确形式
├─ 需要同时评估"过程"和"结果"
└─ 非常有挑战性

大白话：
RAG 像考选择题 → 答案比较确定，容易判对错。
Agent 像考写作文 + 做实验 → 过程和结果都要评，评起来复杂。
```

### 7.2 Agent 评估的五个维度

```
维度 1：任务完成率（Task Completion Rate）
══════════════════════════════════════
├─ 定义：Agent 成功完成任务的比例
├─ 计算：成功任务数 / 总任务数
├─ 标准：> 80% 可用，> 90% 良好，> 95% 优秀
├─ 关键：怎么定义"成功"？
│   ├─ 严格：输出完全符合预期格式和内容
│   ├─ 宽松：核心目标达成，细节可接受偏差
│   └─ 建议：和业务方一起定义

维度 2：步骤效率（Step Efficiency）
═════════════════════════════════
├─ 定义：实际用了多少步 vs 理论最少步数
├─ 计算：实际步数 / 最优步数
├─ 标准：比值 < 1.5 优秀，< 2.0 可接受，> 3.0 需要优化
├─ 为什么重要：
│   ├─ 步数多 = Token 消耗多 = 成本高
│   ├─ 步数多 = 延迟高 = 用户等待久
│   └─ 步数多 = 出错机会多

维度 3：工具使用准确率（Tool Accuracy）
════════════════════════════════════
├─ 选择准确率：选对了工具吗？
├─ 参数准确率：参数填对了吗？
├─ 时机准确率：在正确的时候调用了吗？
│   （不该调的时候调了 = 过度调用）
│   （该调的时候没调 = 遗漏调用）

维度 4：结果质量（Output Quality）
═════════════════════════════════
├─ 和 RAG 评估类似
├─ 用 LLM-as-Judge 评分
├─ 维度：准确性、完整性、相关性、表达质量

维度 5：安全合规性（Safety & Compliance）
═══════════════════════════════════════
├─ 有没有执行未授权的操作
├─ 有没有泄露敏感信息
├─ 有没有忽略用户的限制条件
├─ 该请求人工确认时有没有请求
```

### 7.3 Agent 评估的实现

```python
class AgentEvaluator:
    """Agent 评估器"""

    async def evaluate(self, test_case: dict, agent) -> dict:
        """评估一个测试用例"""

        # 运行 Agent 并记录完整执行轨迹
        trace = await agent.run_with_trace(test_case["task"])

        scores = {}

        # 维度 1：任务完成
        scores["completion"] = self.eval_completion(
            trace, test_case["success_criteria"]
        )

        # 维度 2：步骤效率
        scores["efficiency"] = self.eval_efficiency(
            actual_steps=trace.total_steps,
            optimal_steps=test_case.get("optimal_steps", 5)
        )

        # 维度 3：工具使用
        scores["tool_accuracy"] = self.eval_tool_usage(
            trace.tool_calls,
            test_case.get("expected_tools", [])
        )

        # 维度 4：结果质量（用 LLM-as-Judge）
        scores["quality"] = await judge_response(
            question=test_case["task"],
            reference=test_case["expected_output"],
            ai_response=trace.final_output
        )

        # 维度 5：安全性
        scores["safety"] = self.eval_safety(trace)

        return scores

    def eval_completion(self, trace, success_criteria: dict) -> float:
        """评估是否完成任务"""
        if trace.terminated_by == "max_steps":
            return 0.0  # 超过最大步数 = 未完成

        checks_passed = 0
        total_checks = len(success_criteria)

        for criterion, check_fn in success_criteria.items():
            if check_fn(trace.final_output):
                checks_passed += 1

        return checks_passed / total_checks if total_checks > 0 else 0.0

    def eval_efficiency(self, actual_steps: int,
                        optimal_steps: int) -> float:
        """评估步骤效率"""
        if optimal_steps == 0:
            return 1.0
        ratio = actual_steps / optimal_steps
        # ratio=1 满分, ratio=2 0.5分, ratio>=3 0分
        return max(0, 1 - (ratio - 1) / 2)

    def eval_safety(self, trace) -> dict:
        """评估安全性"""
        violations = []

        for step in trace.steps:
            # 检查危险操作是否有确认
            if step.tool in DANGEROUS_TOOLS and not step.had_confirmation:
                violations.append(f"未确认的危险操作：{step.tool}")

        return {
            "safe": len(violations) == 0,
            "violation_count": len(violations),
            "violations": violations
        }
```

---

---

# 下篇开始

---

## 第八章：迭代评估——改了之后是变好还是变坏

### 8.1 为什么迭代评估是必须的

```
大白话：
你改了一行 Prompt，试了3个问题都变好了，你开心地上线了。
结果线上用户一用，另外 30 个场景全崩了。

这种事在 AI 项目中天天发生。

核心问题：每次改动都可能"按下葫芦起了瓢"。

迭代评估要回答的问题：
├─ 改了之后，整体是变好了还是变坏了？
├─ 好了多少？坏了多少？
├─ 具体哪些场景变好了？哪些变差了？
└─ 变差的那些能接受吗？

大白话：
就像医生给你开了新药：
├─ 不能只看"头疼好了没"
├─ 还要看"有没有其他副作用"
├─ 用数据说话，不是凭感觉
```

### 8.2 GSB 评估法——最实用的迭代对比方法（面试重点）

```
GSB = Good / Same / Bad

是什么：对比两个版本的 AI 输出，逐条判断"变好了 / 没变化 / 变差了"。

大白话：
├─ 旧版 AI 回答了 100 个问题
├─ 新版 AI 也回答同样的 100 个问题
├─ 逐条对比：
│   ├─ Good：新版比旧版好 → 记一个 G
│   ├─ Same：差不多 → 记一个 S
│   └─ Bad：新版比旧版差 → 记一个 B
├─ 最后统计：G=25, S=65, B=10
└─ 结论：新版整体更好（Good 比 Bad 多 15 个），可以上线

判断标准：
├─ G >> B → 值得上线
├─ G ≈ B → 没什么变化，不值得改
├─ G << B → 回滚，别上线
└─ 具体看 B 的内容：如果 B 都是核心场景，即使 G > B 也要慎重
```

```python
# GSB 评估的实现

import anthropic
import json

GSB_JUDGE_PROMPT = """你是一个专业的 AI 输出质量对比评估专家。

请对比以下两个 AI 系统对同一个问题的回答，判断哪个更好。

## 用户问题
{question}

## 参考答案（如果有）
{reference}

## 版本 A 的回答
{response_a}

## 版本 B 的回答
{response_b}

## 评估维度
请从以下维度综合考虑：
1. 准确性：哪个回答更准确？
2. 完整性：哪个回答覆盖了更多关键信息？
3. 相关性：哪个回答更切题？
4. 表达质量：哪个回答更清晰易懂？

## 输出格式

请严格按以下 JSON 格式输出：
{{
    "winner": "A" 或 "B" 或 "tie",
    "confidence": "high" 或 "medium" 或 "low",
    "reasoning": "<简要说明判断理由>"
}}

注意：
- 不要因为回答更长就判断更好
- 关注内容质量，不是格式
- 如果两者质量非常接近，判 tie"""


async def gsb_evaluate(question: str, reference: str,
                       old_response: str, new_response: str) -> dict:
    """对比新旧两版回答"""

    client = anthropic.AsyncAnthropic()

    # 第一次评估：旧版在前
    result1 = await _judge(client, question, reference,
                           response_a=old_response,
                           response_b=new_response)

    # 第二次评估：新版在前（消除位置偏见）
    result2 = await _judge(client, question, reference,
                           response_a=new_response,
                           response_b=old_response)

    # 综合两次结果
    return _merge_results(result1, result2)


def _merge_results(r1: dict, r2: dict) -> str:
    """综合两次评估结果，消除位置偏见"""

    # r1: A=旧版, B=新版
    # r2: A=新版, B=旧版
    # 如果 r1 说 B 好（新版好）且 r2 说 A 好（也是新版好）
    #   → 一致认为新版好 → Good

    new_wins_r1 = r1["winner"] == "B"
    new_wins_r2 = r2["winner"] == "A"

    if new_wins_r1 and new_wins_r2:
        return "Good"      # 两次都认为新版好
    elif not new_wins_r1 and not new_wins_r2:
        if r1["winner"] == "tie" and r2["winner"] == "tie":
            return "Same"  # 两次都平局
        return "Bad"       # 两次都认为旧版好
    else:
        return "Same"      # 两次结果不一致 → 判平局


async def run_gsb_evaluation(test_cases: list, old_system,
                              new_system) -> dict:
    """对整个评估集运行 GSB 评估"""

    results = {"Good": [], "Same": [], "Bad": []}

    for case in test_cases:
        old_resp = await old_system.chat(case["question"])
        new_resp = await new_system.chat(case["question"])

        verdict = await gsb_evaluate(
            question=case["question"],
            reference=case.get("expected_answer", ""),
            old_response=old_resp,
            new_response=new_resp
        )
        results[verdict].append(case["id"])

    # 汇总报告
    total = len(test_cases)
    report = {
        "total": total,
        "good": len(results["Good"]),
        "same": len(results["Same"]),
        "bad": len(results["Bad"]),
        "good_rate": f"{len(results['Good'])/total*100:.1f}%",
        "bad_rate": f"{len(results['Bad'])/total*100:.1f}%",
        "net_improvement": len(results["Good"]) - len(results["Bad"]),
        "bad_case_ids": results["Bad"],  # 重点关注变差的
    }
    return report
```

### 8.3 Elo Rating——当你需要对比多个版本

```
是什么：
一种从国际象棋借来的排名系统。
让多个 AI 版本互相"下棋"（对比回答），根据胜负计算排名分数。

大白话：
GSB 适合对比 2 个版本。
但如果你同时在测试 5 个不同的 Prompt 版本，
两两对比太多了（5×4/2=10 组对比）。

Elo Rating 的做法：
├─ 每个版本有一个初始分数（通常 1000 分）
├─ 每次对比：赢了加分，输了扣分
├─ 强版本胜弱版本 → 分数变化小（符合预期）
├─ 弱版本胜强版本 → 分数变化大（爆冷门）
├─ 对比足够多次后，分数趋于稳定
└─ 最终按分数排名

什么时候用：
├─ 对比 3 个以上版本时
├─ 想建立长期的版本排名时
├─ Chatbot Arena（大模型竞技场）就用这个方法
└─ 日常项目中 GSB 已经够用，Elo 了解即可
```

### 8.4 A/B 测试——线上对比的金标准

```
是什么：
把真实用户随机分成两组，一组用旧版，一组用新版。
用真实使用数据对比两个版本的效果。

大白话：
├─ 离线评估再好，也是模拟的
├─ A/B 测试用的是真实用户、真实场景
├─ 是最可靠的评估方式

怎么做：
1. 把用户流量按比例分流
   ├─ 90% 用户 → 旧版（A 组，对照组）
   └─ 10% 用户 → 新版（B 组，实验组）
   先小流量试水，确认没问题再逐步放量

2. 收集两组的指标
   ├─ 用户满意度（点赞率/点踩率）
   ├─ 任务完成率
   ├─ 人工转接率
   ├─ 用户留存率
   └─ 平均对话轮数

3. 统计检验
   ├─ 两组数据差异是否"统计显著"
   ├─ 用 t 检验或卡方检验
   ├─ p < 0.05 → 差异是真实的，不是偶然
   └─ p > 0.05 → 差异可能是偶然的

4. 决策
   ├─ B 组显著优于 A 组 → 全量上线新版
   ├─ B 组和 A 组差不多 → 不值得换
   └─ B 组不如 A 组 → 回滚
```

```python
# A/B 测试的流量分配

import hashlib

def get_ab_group(user_id: str, experiment_name: str,
                 new_version_ratio: float = 0.1) -> str:
    """根据用户 ID 确定分组"""

    # 用 hash 保证同一用户始终在同一组（一致性）
    key = f"{user_id}:{experiment_name}"
    hash_value = int(hashlib.md5(key.encode()).hexdigest(), 16)
    ratio = (hash_value % 10000) / 10000

    if ratio < new_version_ratio:
        return "B"  # 新版
    else:
        return "A"  # 旧版


# 在 API 中使用
async def chat_endpoint(user_id: str, question: str):
    group = get_ab_group(user_id, "prompt_v2_test", 0.1)

    if group == "B":
        response = await new_system.chat(question)
    else:
        response = await old_system.chat(question)

    # 记录实验数据
    log_ab_result(user_id, group, question, response)

    return response
```

### 8.5 回归测试——确保改了不会崩

```
是什么：
每次修改代码/Prompt 后，自动跑一遍评估集，
确保没有之前正确的变错了。

大白话：
回归测试就像体检：
├─ 你感冒吃了药
├─ 感冒好了
├─ 但要检查一下肝功能、肾功能还正常不
└─ 确保"治好一个病，没整出新毛病"

怎么做：
├─ 维护一个"核心测试集"（不能错的关键用例）
├─ 每次改 Prompt/代码 → 自动跑核心测试集
├─ 如果有任何核心用例变差 → 阻止上线
└─ 可以集成到 CI/CD 中（Step 5 学的 GitHub Actions）
```

---

## 第九章：线上评估——用户真实反馈

### 9.1 为什么需要线上评估

```
离线评估 vs 线上评估

离线评估（你在前面学的）：
├─ 用预先准备的评估集测试
├─ 优点：可控、可重复
├─ 缺点：无法覆盖所有真实场景
└─ 就像模拟考试，和真正高考还是有差距

线上评估：
├─ 收集真实用户的使用数据
├─ 优点：最真实、最全面
├─ 缺点：有些指标不好收集
└─ 就像看高考成绩，这才是真正的水平

最佳实践：两者结合
├─ 离线评估做"准入门槛"（不过关不上线）
└─ 线上评估做"真实检验"（用户说好才是真的好）
```

### 9.2 用户反馈收集

```
方式 1：显式反馈（用户主动给）
═══════════════════════════════
├─ 👍 / 👎 按钮（最简单、收集率最高）
├─ 1-5 星评分
├─ 文字反馈（用户说哪里不好）
├─ "回答有用吗？" 弹窗

优点：用户的真实评价
缺点：收集率低（通常 1-5% 的用户会反馈），
      而且用户更倾向在不满意时才反馈（负面偏见）


方式 2：隐式反馈（用户行为推断）
═══════════════════════════════
├─ 用户是否重新提问（可能说明没答好）
├─ 用户是否复制了回答（可能说明有用）
├─ 对话轮数（轮数多可能说明一次答不对）
├─ 用户是否转人工（说明 AI 解决不了）
├─ 用户是否很快结束对话（可能满意了，也可能放弃了）
├─ 停留时间（看了很久可能在认真读，也可能没看懂）

优点：不需要用户额外操作，数据量大
缺点：需要解读，不一定准确
```

```python
# 用户反馈收集的实现

from datetime import datetime
from enum import Enum

class FeedbackType(str, Enum):
    THUMBS_UP = "thumbs_up"
    THUMBS_DOWN = "thumbs_down"
    REGENERATE = "regenerate"       # 用户点了"重新生成"
    COPY = "copy"                   # 用户复制了回答
    TRANSFER_HUMAN = "transfer"     # 转人工

class FeedbackCollector:
    """用户反馈收集器"""

    async def record_explicit_feedback(
        self, conversation_id: str, message_id: str,
        feedback_type: FeedbackType, comment: str = ""
    ):
        """记录显式反馈"""
        await self.db.insert("feedback", {
            "conversation_id": conversation_id,
            "message_id": message_id,
            "feedback_type": feedback_type,
            "comment": comment,
            "timestamp": datetime.utcnow().isoformat()
        })

    async def record_implicit_signal(
        self, conversation_id: str,
        signal_type: str, metadata: dict
    ):
        """记录隐式信号"""
        await self.db.insert("implicit_signals", {
            "conversation_id": conversation_id,
            "signal_type": signal_type,
            "metadata": metadata,
            "timestamp": datetime.utcnow().isoformat()
        })

    async def get_satisfaction_rate(self, days: int = 7) -> dict:
        """计算满意率"""
        feedbacks = await self.db.query_recent("feedback", days)
        total = len(feedbacks)
        if total == 0:
            return {"rate": 0, "total": 0}

        positive = sum(
            1 for f in feedbacks
            if f["feedback_type"] == FeedbackType.THUMBS_UP
        )
        return {
            "satisfaction_rate": f"{positive/total*100:.1f}%",
            "positive": positive,
            "negative": total - positive,
            "total": total
        }
```

### 9.3 线上监控指标体系

```
搭建一个完整的线上监控看板：

┌────────────────────────────────────────────────┐
│              AI 系统线上监控看板                  │
├────────────────────────────────────────────────┤
│                                                │
│  核心体验指标                                   │
│  ├─ 用户满意度（点赞率）         72% ↑3%       │
│  ├─ 任务完成率                   85%           │
│  ├─ 人工转接率                   12% ↓2%       │
│  └─ 首次解决率                   78%           │
│                                                │
│  质量指标                                       │
│  ├─ 拒答率（不该拒答但拒答了）    3%            │
│  ├─ 幻觉率（编造了信息）          5%            │
│  ├─ 安全事件数                   0 件          │
│  └─ 平均回答长度                 156 字        │
│                                                │
│  性能指标                                       │
│  ├─ 平均响应时间（首 Token）     0.8s           │
│  ├─ 平均总响应时间               3.2s           │
│  ├─ P99 响应时间                 8.5s           │
│  └─ 错误率                      0.3%           │
│                                                │
│  成本指标                                       │
│  ├─ 日均 Token 消耗             2.1M Tokens    │
│  ├─ 日均 API 费用               ¥350           │
│  ├─ 单次对话平均成本             ¥0.15          │
│  └─ 月度预算使用率               68%            │
│                                                │
└────────────────────────────────────────────────┘

每个指标都要设告警阈值：
├─ 满意度 < 60% → 告警（urgent）
├─ 人工转接率 > 25% → 告警
├─ 幻觉率 > 10% → 告警（urgent）
├─ P99 响应时间 > 15s → 告警
└─ 日费用 > ¥800 → 告警

这些和 Step 5 学的监控系统（Prometheus/Grafana）结合：
├─ 用 Prometheus 收集指标
├─ 用 Grafana 画看板
└─ 设 AlertManager 告警
```

---

## 第十章：评估驱动优化——从发现问题到解决问题

### 10.1 评估的终极目的是优化

```
大白话：
评估不是目的，优化才是。

光知道"准确率 85%"没用，
关键是"怎么从 85% 提到 90%"。

评估驱动优化的闭环：
┌─────────────────────────────────────────┐
│                                         │
│   评估 → 发现问题 → 分析原因 → 优化     │
│     ↑                          │        │
│     └──────────────────────────┘        │
│         再次评估验证效果                  │
│                                         │
└─────────────────────────────────────────┘

这个循环永远不会结束。
AI 系统的优化是持续的过程。
```

### 10.2 Bad Case 分析方法论（面试重点）

```
Bad Case = AI 回答错误或质量差的案例

这是最有价值的优化信息来源。

Bad Case 分析四步法：

Step 1：收集 Bad Case
═══════════════════
├─ 从评估集中找到低分的 case
├─ 从用户反馈中找到 👎 的回答
├─ 从线上日志中找到转人工的对话
├─ 从安全审计中找到违规输出
└─ 建一个 Bad Case 表格

Step 2：分类 Bad Case
═══════════════════
把 Bad Case 按问题类型分类：

├─ 检索问题（RAG 场景）
│   ├─ 没检索到：相关文档存在但没找到
│   ├─ 检索错误：找到了不相关的文档
│   └─ 信息不全：找到了部分相关文档
│
├─ 生成问题
│   ├─ 幻觉：编造了不存在的信息
│   ├─ 跑题：回答和问题不相关
│   ├─ 不完整：遗漏了关键信息
│   ├─ 不忠实：没有按照检索文档回答
│   └─ 格式错误：输出格式不符合要求
│
├─ 理解问题
│   ├─ 误解意图：理解错了用户想问什么
│   ├─ 多义歧义：没有正确处理歧义
│   └─ 复杂推理：多步推理出了错
│
├─ 安全问题
│   ├─ 信息泄露：暴露了不该暴露的信息
│   ├─ 不当承诺：承诺了做不到的事情
│   └─ 注入攻击：被用户的恶意输入绕过
│
└─ 知识缺失
    ├─ 知识库没有：知识库本身没有这个信息
    └─ 知识过期：知识库信息已经过时了

Step 3：定位根因
══════════════
每类问题对应不同的根因和解决方案：

问题类型          根因              解决方向
────────────────────────────────────────────
没检索到          分块太大/太小      调整分块策略
                  embedding 差      换 embedding 模型
                  查询和文档不匹配   加查询改写

检索错误          top_k 太大         减小 top_k
                  缺少 reranking    加 reranker

幻觉              Prompt 不够严格    加强"只基于文档回答"指令
                  context 不够      增加检索文档数量
                  模型选择          换更严谨的模型

跑题              Prompt 缺约束      加强指令约束
                  上下文干扰        优化对话管理

不完整            检索不全          提高 recall
                  Prompt 缺引导     明确要求"列出所有相关点"

知识缺失          文档缺失          补充知识库
                  知识过期          更新知识库

Step 4：修复并验证
════════════════
├─ 针对根因实施修复
├─ 把这个 Bad Case 加入评估集（防止未来再犯）
├─ 跑 GSB 评估，确认修复有效且没有副作用
└─ 记录修复过程（知识积累）
```

### 10.3 优化优先级决策

```
不是所有 Bad Case 都要立刻修：

优先级判断矩阵：

               影响范围大              影响范围小
          ┌──────────────────┬──────────────────┐
严重程度高 │ P0 - 立刻修       │ P1 - 本周修       │
          │ 安全漏洞、大面积   │ 低频但严重的错误   │
          │ 回答错误           │                    │
          ├──────────────────┼──────────────────┤
严重程度低 │ P2 - 排进计划      │ P3 - 有空再看     │
          │ 高频但不严重的     │ 低频且不严重       │
          │ 回答不完整         │ 表达不够好         │
          └──────────────────┴──────────────────┘

优先修什么？
1. 安全问题 → 最高优先级，一刻不能等
2. 高频 Bad Case → 影响用户多，性价比高
3. 核心场景的 Bad Case → 核心业务不能出错
4. 简单能修的 Bad Case → 投入小收效大
```

---

## 第十一章：评估基础设施——搭建自动化评估管线

### 11.1 为什么需要自动化评估管线

```
大白话：
如果每次评估都要手动操作：
├─ 手动跑测试用例
├─ 手动调用 Judge
├─ 手动统计分数
├─ 手动生成报告
→ 你最多坚持评估两三次就烦了

自动化评估管线的意思：
├─ 改了代码 → 自动跑评估
├─ 自动打分 → 自动生成报告
├─ 发现问题 → 自动告警
├─ 全程不需要人工操作
└─ 就像 Step 5 学的 CI/CD，但是给 AI 系统专用

一条命令跑完所有评估：
  python run_eval.py --version v2.3 --compare v2.2
  → 10 分钟后在邮箱里收到评估报告
```

### 11.2 评估管线的架构

```
┌────────────────────────────────────────────────────────────┐
│                    自动化评估管线                             │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  触发器                                                    │
│  ├─ 代码提交（Git Push）                                   │
│  ├─ 定时任务（每天凌晨 2 点）                               │
│  ├─ 手动触发（python run_eval.py）                          │
│  └─ PR 合并前的 Check                                      │
│              │                                             │
│              ▼                                             │
│  ┌──────────────────────┐                                  │
│  │  1. 加载评估数据集     │ ← eval_dataset_v2.1.json       │
│  └──────────┬───────────┘                                  │
│              ▼                                             │
│  ┌──────────────────────┐                                  │
│  │  2. 运行 AI 系统       │ ← 对每个问题生成回答             │
│  │     (新版 + 旧版)      │                                 │
│  └──────────┬───────────┘                                  │
│              ▼                                             │
│  ┌──────────────────────┐                                  │
│  │  3. 自动评估           │                                │
│  │  ├─ 规则检查           │ ← 关键词、禁止词、长度           │
│  │  ├─ LLM-as-Judge      │ ← 多维度打分                    │
│  │  └─ GSB 对比           │ ← 新版 vs 旧版                 │
│  └──────────┬───────────┘                                  │
│              ▼                                             │
│  ┌──────────────────────┐                                  │
│  │  4. 汇总与分析         │                                │
│  │  ├─ 按类别统计         │                                │
│  │  ├─ 按难度统计         │                                │
│  │  ├─ 找出 Bad Case     │                                │
│  │  └─ 和历史数据对比     │                                │
│  └──────────┬───────────┘                                  │
│              ▼                                             │
│  ┌──────────────────────┐                                  │
│  │  5. 输出报告           │                                │
│  │  ├─ 控制台摘要         │                                │
│  │  ├─ 详细 HTML 报告     │                                │
│  │  ├─ 结果存数据库       │ ← 追踪历史趋势                  │
│  │  └─ 邮件/飞书通知      │                                │
│  └──────────┬───────────┘                                  │
│              ▼                                             │
│  ┌──────────────────────┐                                  │
│  │  6. 准入判断           │                                │
│  │  ├─ 核心指标达标？     │ → 是 → ✅ 允许上线              │
│  │  └─ 核心指标不达标？   │ → 否 → ❌ 阻止上线              │
│  └──────────────────────┘                                  │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

### 11.3 评估管线的代码实现

```python
# 完整的评估管线实现

import json
import asyncio
from datetime import datetime
from pathlib import Path

class EvalPipeline:
    """自动化评估管线"""

    def __init__(self, config: dict):
        self.dataset_path = config["dataset_path"]
        self.output_dir = config["output_dir"]
        self.judge_model = config.get("judge_model", "claude-opus-4-20250514")
        self.thresholds = config.get("thresholds", {
            "min_accuracy": 0.85,
            "max_bad_rate": 0.10,
            "min_safety": 0.99,
        })

    async def run(self, new_system, old_system=None,
                  version: str = "unknown") -> dict:
        """运行完整评估流程"""

        print(f"🚀 开始评估 版本={version}")

        # Step 1: 加载评估数据集
        dataset = self.load_dataset()
        print(f"📋 加载了 {len(dataset)} 条测试用例")

        # Step 2: 生成回答
        new_responses = await self.generate_responses(new_system, dataset)
        print(f"✅ 新版生成完成")

        # Step 3: 自动评估
        scores = await self.evaluate_all(dataset, new_responses)
        print(f"📊 评估完成")

        # Step 4: GSB 对比（如果有旧版）
        gsb_result = None
        if old_system:
            old_responses = await self.generate_responses(old_system, dataset)
            gsb_result = await self.gsb_compare(
                dataset, old_responses, new_responses
            )
            print(f"📊 GSB 对比完成")

        # Step 5: 汇总报告
        report = self.generate_report(
            version, dataset, scores, gsb_result
        )

        # Step 6: 准入判断
        report["pass"] = self.check_thresholds(report)

        # 保存报告
        self.save_report(report, version)

        # 打印摘要
        self.print_summary(report)

        return report

    def check_thresholds(self, report: dict) -> bool:
        """检查是否达到上线标准"""

        checks = []

        # 检查准确率
        if report["avg_accuracy"] < self.thresholds["min_accuracy"]:
            checks.append(
                f"❌ 准确率 {report['avg_accuracy']:.2f} "
                f"< {self.thresholds['min_accuracy']}"
            )

        # 检查安全性
        if report.get("safety_score", 1) < self.thresholds["min_safety"]:
            checks.append(
                f"❌ 安全分 {report['safety_score']:.2f} "
                f"< {self.thresholds['min_safety']}"
            )

        # 检查 GSB Bad 率
        if report.get("gsb_bad_rate", 0) > self.thresholds["max_bad_rate"]:
            checks.append(
                f"❌ Bad 率 {report['gsb_bad_rate']:.2f} "
                f"> {self.thresholds['max_bad_rate']}"
            )

        if checks:
            print("\n".join(checks))
            return False
        return True

    def print_summary(self, report: dict):
        """打印评估摘要"""
        status = "✅ PASS" if report["pass"] else "❌ FAIL"
        print(f"\n{'='*50}")
        print(f"评估结果: {status}")
        print(f"版本: {report['version']}")
        print(f"测试用例数: {report['total_cases']}")
        print(f"平均准确率: {report['avg_accuracy']:.2%}")
        print(f"平均完整性: {report['avg_completeness']:.2%}")
        if report.get("gsb_result"):
            gsb = report["gsb_result"]
            print(f"GSB: G={gsb['good']} S={gsb['same']} B={gsb['bad']}")
        print(f"{'='*50}\n")
```

### 11.4 集成到 CI/CD

```yaml
# .github/workflows/ai-eval.yml
# 和 Step 5 学的 GitHub Actions 结合

name: AI Evaluation

on:
  pull_request:
    branches: [main]
  schedule:
    - cron: '0 2 * * *'   # 每天凌晨 2 点自动评估

jobs:
  evaluate:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run evaluation
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: |
          python run_eval.py \
            --version ${{ github.sha }} \
            --compare main \
            --output eval_report.json

      - name: Check results
        run: |
          python check_eval_results.py eval_report.json
          # 如果不达标会返回非零退出码，阻止 PR 合并

      - name: Upload report
        uses: actions/upload-artifact@v4
        with:
          name: eval-report
          path: eval_report.json
```

```
CI/CD 集成后的效果：

开发者改了 Prompt → 提交 PR → 自动跑评估 →
├─ 评估通过 ✅ → PR 可以合并
└─ 评估不通过 ❌ → PR 被阻止，开发者需要修复

这就是"评估驱动开发"。
确保每次改动都是变好的，不是变差的。
```

---

## 第十二章：常见问题诊断手册

### 12.1 评估结果不可信

```
问题：两次跑同一个评估集，分数差很多

可能原因：
├─ LLM 温度不为 0 → 输出不确定
├─ Judge Prompt 不够明确 → 评分标准模糊
├─ 评估集太小 → 随机波动大
└─ API 响应不稳定 → 超时或错误

解决方案：
├─ 被评估的 AI 和 Judge 都设 temperature=0
├─ Judge Prompt 给出明确的、量化的评分标准
│   ❌ "回答好就给高分"
│   ✅ "包含3个关键信息点给5分，2个给4分，1个给3分"
├─ 评估集至少 100 条（50 条是最低限度）
├─ 每个 case 评估 3 次取平均（提高稳定性）
└─ 做好异常处理，失败了自动重试
```

### 12.2 LLM-as-Judge 和人工评估差距大

```
问题：LLM Judge 打的分和人工评估差很远

诊断步骤：
1. 先抽 50 条，让人工和 LLM 分别评分
2. 计算一致率（Cohen's Kappa 或简单的一致百分比）
3. 找出差距最大的 case，分析原因

常见原因和解决：

原因 1：Judge Prompt 的标准和人不一样
├─ 现象：人觉得"还行"的，LLM 给了1分
├─ 解决：在 Judge Prompt 中加入具体的评分示例
│   "以下是各分数的示例：
│    5分示例：<具体回答>
│    3分示例：<具体回答>
│    1分示例：<具体回答>"

原因 2：LLM 不理解业务上下文
├─ 现象：LLM 认为正确的，业务上其实是错的
├─ 解决：在 Judge Prompt 中提供业务背景知识
│   "注意：在我们的业务中，'7天无理由退款'仅适用于
│    实物商品，虚拟商品不适用。"

原因 3：评估维度定义不清
├─ 现象：人关注的是"有没有解决问题"，LLM 关注"信息对不对"
├─ 解决：明确定义每个维度评估的是什么
│   把最重要的维度权重调高
```

### 12.3 评估成本太高

```
问题：LLM-as-Judge 评估 500 条，花了 ¥200

优化策略：

策略 1：分层评估
├─ 第一层：规则检查（免费）
│   关键词匹配、长度检查、格式检查
│   能过滤掉明显好/明显差的 case
├─ 第二层：LLM-as-Judge（付费）
│   只对"不确定"的 case 做 LLM 评估
└─ 效果：减少 50-70% 的 LLM 调用

策略 2：用小模型做初筛
├─ 用 Haiku（便宜）做第一轮评估
├─ 对分数在"边界区间"的 case 用 Opus（贵但准）
└─ 效果：成本降低 80%，准确率只下降 2-3%

策略 3：缓存和增量评估
├─ 只评估"变了的"case（相同问题相同回答→直接用缓存分数）
├─ 如果修改只影响某个类别，只跑该类别的评估
└─ 效果：日常迭代成本降低 60-80%

策略 4：减少评估频率
├─ 不是每次 commit 都跑全量评估
├─ PR 级别跑核心子集（50条）
├─ 合并到 main 时跑全量（500条）
└─ 每周跑一次扩展集（1000条）
```

### 12.4 评估集老化

```
问题：评估集一直是半年前建的，和现在的真实场景脱节了

症状：
├─ 评估分数一直很高，但用户投诉不断
├─ 新场景、新功能没有被评估覆盖
└─ 某些测试用例的"正确答案"已经过期了

解决方案：

1. 建立"评估集更新"机制
   ├─ 每个新 Bad Case → 自动加入评估集
   ├─ 每次业务变更 → 更新相关测试用例
   ├─ 每月审查一次评估集（删除过期的、补充缺失的）
   └─ 参考答案过期的 → 更新参考答案

2. 从线上日志自动补充
   ├─ 定期从线上日志中采样
   ├─ 对采样的对话做人工标注
   ├─ 标注后加入评估集
   └─ 确保评估集始终反映真实使用场景

3. 维护评估集的"健康指标"
   ├─ 覆盖率：每个业务场景都有测试用例吗？
   ├─ 新鲜度：最近 3 个月有更新过吗？
   ├─ 分布：和线上真实场景分布一致吗？
   └─ 难度分布：简单/中等/困难比例合理吗？
```

### 12.5 评估和优化陷入死循环

```
问题：改了 Prompt 让 A 场景变好了，但 B 场景变差了，
     改回来 B 好了 A 又差了，来回折腾。

大白话：按下葫芦起了瓢，怎么都按不住。

原因分析：
├─ 这两个场景对 Prompt 的需求是矛盾的
├─ 比如 A 需要"回答详细"，B 需要"回答简洁"
├─ 一个 Prompt 无法同时满足

解决方案：

方案 1：意图分类 + 分策略处理
├─ 先识别用户意图（A 类还是 B 类）
├─ 不同意图用不同的 Prompt
└─ 这是最根本的解决方案

方案 2：用 Few-shot 示例引导
├─ 在 Prompt 中同时给出两类场景的示例
├─ LLM 根据具体情况选择合适的回答风格
└─ 适合差异不大的场景

方案 3：Prompt 链
├─ 第一步：判断问题属于哪类
├─ 第二步：根据分类选择对应的处理 Prompt
└─ 稍微增加延迟和成本，但效果好

方案 4：接受 trade-off
├─ 有些场景就是矛盾的
├─ 看哪个场景更重要（更高频/更核心）
├─ 优先保障重要场景
└─ 用数据说话：A 场景占 80% 流量 → 优先保 A
```

---

## 第十三章：面试高频考题与答案

### Q1：如何评估一个 RAG 系统的效果？

```
参考答案：

RAG 系统的评估需要"分段评估"加"端到端评估"。

分段评估——检索阶段：
├─ Context Recall：参考答案中的信息是否被检索到
│  衡量检索的"找全"能力
├─ Context Precision：检索出的文档中有多少是相关的
│  衡量检索的"找准"能力
├─ MRR（Mean Reciprocal Rank）：正确文档排在第几位
│  排名越靠前越好

分段评估——生成阶段：
├─ Faithfulness：回答是否忠于检索到的文档
│  最重要的指标，低 Faithfulness = 幻觉
├─ Answer Relevancy：回答是否切题

端到端评估：
├─ 用 LLM-as-Judge 对最终回答做多维度打分
├─ 和参考答案对比准确性和完整性

诊断思路：
├─ 回答不好 → 先看 Context Recall → 是检索问题还是生成问题
├─ 检索问题 → 调 embedding/分块/reranking
├─ 生成问题 → 调 Prompt/模型

工具：RAGAS 框架是行业标准，提供上述所有指标的自动计算。
```

### Q2：什么是 LLM-as-Judge？有什么优缺点？

```
参考答案：

LLM-as-Judge 是用一个强大的 LLM（如 Claude Opus）来评价
另一个 AI 系统的输出质量。

原理：
├─ 设计一个 Judge Prompt，定义评分标准和维度
├─ 把"用户问题 + AI 回答 + 参考答案"发给 Judge LLM
├─ Judge LLM 按标准打分并给出理由

优点：
├─ 成本低：约 ¥0.05/条，是人工评估的 1/100
├─ 速度快：一分钟评估 10+ 条
├─ 可扩展：可以评估数千条
├─ 能理解语义：比 BLEU/ROUGE 等传统指标准
├─ 一致性高：不像人有主观波动

缺点（已知偏见）：
├─ 位置偏见：对比两个回答时，倾向选第一个
│  → 解决：交换位置做两次
├─ 长度偏见：倾向给更长的回答更高分
│  → 解决：Prompt 中明确"长度不影响评分"
├─ 自我偏见：倾向给同型号模型输出更高分
│  → 解决：用不同厂商模型做 Judge
├─ 格式偏见：倾向给格式好看的回答加分
│  → 解决：Prompt 中明确"只评内容"

最佳实践：
├─ 用人工评估做标定（先让人评 50 条，调 Judge 到一致）
├─ Judge 用最强模型（Opus > Sonnet > Haiku）
├─ temperature=0 确保可复现
└─ 多维度打分（不是只给一个总分）
```

### Q3：如何构建一个评估数据集？

```
参考答案：

评估数据集是"AI 系统的考试卷子"，构建方法如下：

数据来源（四个渠道）：
├─ 真实日志：从线上用户对话中采样（最有代表性）
├─ 业务方：请产品/业务提供典型场景和边界场景
├─ Bad Case：每个 AI 答错的案例都加入
├─ 对抗样本：刻意设计的刁难问题

一条数据的结构：
├─ 问题（用户输入）
├─ 参考答案（期望的回答）
├─ 评估标准（什么算对、什么算错）
├─ 分类标签（场景、难度、特殊属性）

规模建议：
├─ 最少 50 条（能看趋势）
├─ 推荐 200 条（日常迭代够用）
├─ 理想 500+ 条（覆盖充分）

分布建议：
├─ 60% 常见场景（基本功）
├─ 25% 中等难度（核心能力）
├─ 10% 困难场景（极端考验）
├─ 5% 对抗样本（安全测试）

关键原则：
├─ 评估集是活的，不是一次性的，要持续补充
├─ 分布应接近线上真实分布
├─ 参考答案要及时更新（业务变了答案也变了）
└─ 每个 Bad Case 修复后都要加入评估集（防回归）
```

### Q4：GSB 评估是什么？怎么做？

```
参考答案：

GSB = Good / Same / Bad，是对比两个版本 AI 系统的标准方法。

做法：
1. 准备评估数据集（比如 200 条问题）
2. 旧版 AI 和新版 AI 分别回答同样的 200 个问题
3. 用 LLM-as-Judge 逐条对比：
   ├─ Good：新版比旧版好
   ├─ Same：差不多
   └─ Bad：新版比旧版差

消除偏见：
每条做两次判断，交换新旧版的位置：
├─ 第一次：旧版在前，新版在后
├─ 第二次：新版在前，旧版在后
├─ 两次一致 → 结果可靠
└─ 两次不一致 → 判 Same

决策标准：
├─ G >> B → 上线
├─ G ≈ B → 不上线（改了没效果）
├─ G << B → 绝对不上线
├─ 特别关注 Bad 的具体内容
│  如果 Bad 都是核心场景 → 即使 G > B 也要慎重

和 A/B 测试的区别：
├─ GSB 是离线评估（上线前做）
├─ A/B 是线上评估（分流真实用户做）
├─ 通常先 GSB 通过，再 A/B 确认
```

### Q5：如何对比评估两个不同的 Embedding 模型？

```
参考答案：

对比 Embedding 模型是 RAG 系统调优中非常实际的需求。

评估方法：

Step 1：准备评估数据
├─ N 个查询问题
├─ 每个问题对应的"正确文档"（ground truth）
└─ 同一份知识库文档集

Step 2：用两个模型分别建索引
├─ 模型 A（如 OpenAI text-embedding-3-small）
│  对同一批文档做向量化 → 建索引 A
├─ 模型 B（如 BGE-M3）
│  对同一批文档做向量化 → 建索引 B

Step 3：用相同的查询跑检索
├─ 每个问题分别在索引 A 和索引 B 中检索
├─ 记录 top_k 结果

Step 4：计算检索指标
├─ Recall@K：前 K 个结果中包含正确文档的比例
├─ MRR：正确文档排在第几位（越前越好）
├─ NDCG：考虑排名位置的综合指标

Step 5：端到端评估
├─ 把检索结果分别送给同一个 LLM 生成回答
├─ 用 LLM-as-Judge 评估最终回答质量
├─ 这一步最重要——检索指标好 ≠ 最终回答好

还要考虑：
├─ 向量维度和索引大小（影响存储成本）
├─ 编码速度（影响索引构建时间）
├─ 查询延迟（影响用户体验）
└─ API 价格（影响运营成本）
```

### Q6：线上评估和离线评估有什么区别？各在什么时候用？

```
参考答案：

离线评估（Offline Evaluation）：
├─ 在上线之前，用预先准备的评估数据集做测试
├─ 优点：可控、可重复、成本低
├─ 缺点：覆盖不了所有真实场景
├─ 什么时候用：
│   ├─ 每次修改 Prompt/代码后
│   ├─ 模型切换前
│   ├─ 新功能上线前
│   └─ CI/CD 自动化检查

线上评估（Online Evaluation）：
├─ 上线后，收集真实用户的使用数据和反馈
├─ 优点：最真实、覆盖面最广
├─ 缺点：有"试错成本"（用户体验差的风险）
├─ 什么时候用：
│   ├─ 监控系统日常表现
│   ├─ A/B 测试新旧版本
│   ├─ 发现离线评估覆盖不到的问题
│   └─ 验证优化效果

两者的关系：
├─ 离线评估是"准入门槛"—— 不过关不上线
├─ 线上评估是"真实检验"—— 用户说好才是真的好
├─ 线上发现的 Bad Case → 补充到离线评估集
│  形成闭环：线上发现 → 离线复现 → 修复 → 离线验证 → 上线
```

### Q7：如何处理 LLM 评估中的"不确定性"？

```
参考答案：

LLM 输出有随机性，评估结果也有波动。处理方法：

1. 固定随机种子
   ├─ 被评估 AI：temperature=0
   ├─ Judge LLM：temperature=0
   └─ 确保相同输入得到相同输出

2. 多次评估取平均
   ├─ 对同一个 case 评估 3-5 次
   ├─ 取平均分或多数投票
   ├─ 成本增加但稳定性大幅提高
   └─ 如果 5 次评估差异很大 → 说明这个 case 本身就是边界情况

3. 置信区间
   ├─ 不是给一个点估计（准确率 85%）
   ├─ 而是给区间估计（准确率 83-87%，95% 置信度）
   └─ 评估集越大，置信区间越窄

4. 统计显著性检验
   ├─ 当说"新版比旧版好"时
   ├─ 要做统计检验（如 McNemar 检验）
   ├─ 确保差异不是随机波动
   └─ 常用标准：p < 0.05
```

### Q8：评估一个 Agent 系统需要关注哪些维度？

```
参考答案：

Agent 评估比普通问答评估复杂，因为要同时评估过程和结果。

五个核心维度：

1. 任务完成率（最重要）
   ├─ 任务是否成功完成
   ├─ 需要和业务方一起定义"成功"的标准
   └─ 目标：> 80% 可用，> 90% 良好

2. 步骤效率
   ├─ 实际步数 vs 理论最少步数
   ├─ 步数越少越好（省 Token、省时间、少出错）
   └─ 要注意太少步数可能说明"偷工减料"

3. 工具使用准确率
   ├─ 选对了工具吗
   ├─ 参数填对了吗
   ├─ 该用的时候用了吗（不遗漏）
   └─ 不该用的时候没用吗（不过度调用）

4. 输出质量
   ├─ 最终结果的准确性、完整性
   ├─ 用 LLM-as-Judge 评估
   └─ 和普通 QA 评估类似

5. 安全合规
   ├─ 有没有执行未授权操作
   ├─ 危险操作有没有请求确认
   ├─ 有没有泄露敏感信息
   └─ 有没有进入死循环

特殊考量：
├─ Agent 的非确定性更强（路径不同），需要更多测试用例
├─ 要测试异常路径（工具失败了怎么办、网络超时了怎么办）
└─ 要测试终止条件（不能无限循环）
```

### Q9：如何搭建一套完整的自动化评估管线？

```
参考答案：

自动化评估管线 = 一键跑评估，全程无人干预。

管线组成：

1. 触发机制
   ├─ PR 提交 → 自动触发（CI/CD 集成）
   ├─ 定时任务 → 每天凌晨自动评估
   └─ 手动触发 → 命令行运行

2. 评估数据集管理
   ├─ 版本化管理（Git 跟踪）
   ├─ 支持增量更新
   └─ 自动校验格式

3. 评估执行
   ├─ 批量运行被评估系统
   ├─ 批量调用 LLM-as-Judge
   ├─ 并发控制（不要打爆 API 限频）
   └─ 异常处理和重试

4. 结果分析
   ├─ 按类别/难度/场景维度统计
   ├─ 和历史版本对比（GSB）
   ├─ 找出 Bad Case 列表
   └─ 生成可视化报告

5. 准入判断
   ├─ 设定阈值（如准确率 > 85%，Bad 率 < 10%）
   ├─ 达标 → 允许合并 PR / 允许部署
   └─ 不达标 → 阻止合并，通知开发者

6. 结果存储
   ├─ 每次评估结果存数据库
   ├─ 支持历史趋势分析
   └─ 支持版本间对比

关键：和 CI/CD（如 GitHub Actions）集成，
实现"改 Prompt → 自动评估 → 结果决定能否上线"。
```

### Q10：如何用评估结果驱动系统优化？

```
参考答案：

评估驱动优化的闭环：评估 → 分析 → 优化 → 再评估。

具体方法：

Step 1：从评估结果中提取 Bad Case
├─ LLM-as-Judge 打分低的 case
├─ GSB 中判定为 Bad 的 case
├─ 线上用户 👎 的对话

Step 2：对 Bad Case 做分类
├─ 检索问题（没找到 / 找错了）
├─ 生成问题（幻觉 / 跑题 / 不完整）
├─ 理解问题（误解意图 / 歧义处理差）
├─ 安全问题（信息泄露 / 注入绕过）
├─ 知识缺失（知识库没覆盖）

Step 3：定位根因并修复
├─ 检索问题 → 调分块/embedding/reranking
├─ 生成问题 → 优化 Prompt / 切换模型
├─ 理解问题 → 加意图分类 / 多轮澄清
├─ 安全问题 → 加防护规则 / 过滤层
├─ 知识缺失 → 补充知识库

Step 4：验证修复
├─ 这个 Bad Case 修好了吗 → 单条验证
├─ 其他 case 没变差吗 → GSB 全量验证
├─ 把 Bad Case 加入评估集 → 防止未来回归

优先级排序（投入产出比）：
1. 高频 + 严重 → 最先修
2. 安全问题 → 无条件立刻修
3. 简单修复 → 快速出成果
4. 低频 + 轻微 → 排到后面
```

### Q11：A/B 测试和 GSB 评估分别在什么场景用？

```
参考答案：

GSB 是离线评估，A/B 是线上评估。互补关系。

GSB 评估：
├─ 时机：上线之前
├─ 数据：预先准备的评估集
├─ 方法：LLM-as-Judge 逐条对比新旧版回答
├─ 成本：LLM API 费用（约 ¥10-50/次评估）
├─ 速度：10-30 分钟出结果
├─ 适合：日常迭代、Prompt 调优、模型切换前的筛选

A/B 测试：
├─ 时机：上线之后（小流量阶段）
├─ 数据：真实用户流量
├─ 方法：随机分流，收集真实指标
├─ 成本：需要时间积累数据（通常 1-2 周）
├─ 速度：需要足够样本量才能得出结论
├─ 适合：重大变更的最终验证、业务指标影响的评估

典型流程：
1. 改了 Prompt → GSB 评估 → 过关
2. 小流量 A/B → 观察 1 周 → 数据正向
3. 全量上线

什么时候可以跳过 A/B：
├─ 修复明确的 bug（GSB 确认修好且无副作用即可）
├─ 非核心场景的小改动
└─ 紧急安全修复
```

### Q12：评估指标之间有冲突怎么办？

```
参考答案：

常见的指标冲突：

冲突 1：准确性 vs 完整性
├─ 回答越详细（完整性高）→ 越容易包含错误信息（准确性低）
├─ 回答越谨慎（准确性高）→ 越可能遗漏信息（完整性低）
├─ 解决：根据业务场景定优先级
│   ├─ 医疗/法律：准确性 > 完整性（宁可漏说，不能说错）
│   └─ 客服/咨询：完整性 > 准确性（信息全面更重要）

冲突 2：Faithfulness vs 用户体验
├─ 严格忠于文档 → 可能回答太死板、不够友好
├─ 灵活回答 → 可能超出文档范围（Faithfulness 低）
├─ 解决：在 Prompt 中明确界限
│   "基于文档回答，但可以用自然的语言组织"
│   "如果文档中没有信息，明确告知用户"

冲突 3：安全性 vs 有用性
├─ 过于严格的安全限制 → 拒答率高，用户体验差
├─ 放松限制 → 安全风险
├─ 解决：分级处理
│   ├─ 硬安全（信息泄露、有害内容）→ 绝不妥协
│   └─ 软安全（话题敏感度）→ 根据场景灵活处理

处理冲突的原则：
1. 安全性永远是最高优先级，不可妥协
2. 其他指标之间的权衡，由业务场景决定
3. 用加权评分体现优先级
   overall = 0.4×accuracy + 0.3×completeness + 0.2×relevancy + 0.1×clarity
4. 定期和业务方对齐权重设置
```

---

## 第十四章：实战项目方向

### 14.1 项目一：RAG 系统评估平台（推荐第一个做）

```
难度：★★★☆☆
预计时间：3-5 天

目标：
为你之前做的 RAG 系统搭建一套完整的评估能力。

功能：
├─ 评估数据集管理（CRUD + 导入导出）
├─ 自动化评估（规则检查 + LLM-as-Judge）
├─ RAGAS 四指标评估（Faithfulness/Relevancy/Precision/Recall）
├─ GSB 版本对比
├─ 评估报告生成（HTML + JSON）
└─ Bad Case 列表和分析

技术栈：
├─ Python + FastAPI
├─ Claude API（LLM-as-Judge）
├─ PostgreSQL（存评估结果）
├─ 前端可以用简单的 HTML 模板或 Streamlit

学到什么：
├─ 评估数据集的设计和管理
├─ LLM-as-Judge 的工程实现
├─ RAGAS 指标的计算
├─ GSB 的实现（含位置偏见消除）
└─ 评估报告的设计
```

### 14.2 项目二：Prompt 迭代评估工具

```
难度：★★☆☆☆
预计时间：2-3 天

目标：
每次修改 Prompt 时，一键对比新旧 Prompt 的效果。

功能：
├─ 输入旧 Prompt 和新 Prompt
├─ 自动跑评估数据集
├─ GSB 对比结果
├─ 按类别展示差异
├─ 高亮变差的 case（重点关注）

技术栈：
├─ Python 脚本（命令行工具即可）
├─ Claude API
└─ JSON 输出

这个项目小而美，非常适合作为入门项目。
做出来之后你会发现，之后每次改 Prompt 都离不开它。
```

### 14.3 项目三：线上监控看板

```
难度：★★★☆☆
预计时间：3-5 天

目标：
为已上线的 AI 系统搭建一个实时监控看板。

功能：
├─ 实时显示：请求量、响应时间、错误率
├─ 用户反馈统计：满意度、点赞/点踩趋势
├─ 成本监控：Token 消耗、API 费用
├─ 质量抽检：定期采样做 LLM-as-Judge
├─ 告警：指标异常自动通知

技术栈：
├─ Prometheus（收集指标）
├─ Grafana（可视化看板）
├─ FastAPI（反馈收集接口）
├─ Redis（实时计数器）
└─ 飞书/钉钉 Webhook（告警通知）

和 Step 5 工程化的知识直接结合。
```

### 14.4 项目四：自动化评估 CI/CD 管线

```
难度：★★★★☆
预计时间：5-7 天

目标：
每次提交 PR，自动运行评估，不达标则阻止合并。

功能：
├─ GitHub Actions 集成
├─ PR 提交 → 自动跑评估
├─ 评估不通过 → PR 检查失败
├─ 评估结果自动回复到 PR 评论
├─ 每日定时全量评估
├─ 历史趋势追踪

技术栈：
├─ GitHub Actions（CI/CD）
├─ Python 评估脚本
├─ Claude API（LLM-as-Judge）
├─ GitHub API（回复 PR 评论）
└─ SQLite 或 PostgreSQL（存历史结果）

这是"评估驱动开发"的完整实现。
也是最能体现你工程能力的项目。
```

---

## 全篇总结：评估体系知识地图

```
评估体系完整知识地图：

第一部分：基础认知
├─ 第一章：为什么评估重要（评估是最被低估的能力）
├─ 第二章：评估框架（评什么/怎么评/谁来评 三个层次三种方法）
└─ 第三章：评估数据集（五步法构建，持续积累）

第二部分：评估方法
├─ 第四章：自动化指标（五个核心维度：准确性/完整性/忠实性/相关性/安全性）
├─ 第五章：LLM-as-Judge（Judge Prompt 设计 + 四种偏见及解决方案）
├─ 第六章：RAG 评估（RAGAS 四指标 + 问题定位矩阵）
└─ 第七章：Agent 评估（五个维度：完成率/效率/工具准确率/质量/安全）

第三部分：评估实践
├─ 第八章：迭代评估（GSB/Elo/A-B 测试/回归测试）
├─ 第九章：线上评估（用户反馈收集 + 监控指标看板）
├─ 第十章：评估驱动优化（Bad Case 四步法 + 优先级矩阵）
└─ 第十一章：评估基础设施（自动化管线 + CI/CD 集成）

第四部分：查阅手册
├─ 第十二章：常见问题诊断（5 大常见问题及解决方案）
├─ 第十三章：面试考题（12 道高频题 + 详细答案）
└─ 第十四章：实战项目（4 个方向，从入门到进阶）

核心理念：
1. 没有评估的 AI 项目 = 没有质检的工厂
2. 评估不是目的，优化才是
3. 离线评估做准入，线上评估做检验
4. Bad Case 是最宝贵的优化线索
5. 自动化评估管线是持续优化的基础
```

---

> **Step 6 评估体系学习完成！**
>
> 回顾你的学习进度：
> - Step 1 Prompt Engineering ✅
> - Step 2 RAG ✅
> - Step 3 Function Calling & Tool Use ✅
> - Step 4 Agent 系统 ✅
> - Step 5 工程化基础 ✅
> - Step 6 评估体系 ✅
>
> **到这里，你已经具备了独立交付企业级 AI 应用项目的核心知识体系。** Step 7-10 是进阶方向（微调、多模态、安全合规、前沿技术），可以根据项目需要选学。
>
> 准备好学下一步告诉我。
