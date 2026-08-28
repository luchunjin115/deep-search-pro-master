# Agent 系统完全知识体系

> AI 应用工程师学习路径 Step 4
> 前置知识：Prompt Engineering ✅、RAG ✅、Function Calling / Tool Use ✅
> 学完本篇：你将理解如何让 LLM 从"调一次工具"变成"自主规划、持续执行、直到完成任务"

---

## 目录

- [第一章：核心概念——什么是 Agent](#第一章核心概念什么是-agent)
- [第二章：Agent 的核心循环——理解"Loop"](#第二章agent-的核心循环理解loop)
- [第三章：Agent 设计模式——四大经典范式](#第三章agent-设计模式四大经典范式)
- [第四章：记忆系统——Agent 的大脑](#第四章记忆系统agent-的大脑)
- [第五章：规划与任务分解——Agent 的思考能力](#第五章规划与任务分解agent-的思考能力)
- [第六章：工具编排——Agent 的执行能力](#第六章工具编排agent-的执行能力)
- [第七章：终止策略——知道什么时候该停](#第七章终止策略知道什么时候该停)
- [第八章：Human-in-the-Loop——人机协作](#第八章human-in-the-loop人机协作)
- [第九章：多 Agent 系统——从个体到团队](#第九章多-agent-系统从个体到团队)
- [第十章：Agent 框架深度对比](#第十章agent-框架深度对比)
- [第十一章：Agent 评估体系——怎么证明你的 Agent 好用](#第十一章agent-评估体系怎么证明你的-agent-好用)
- [第十二章：生产环境部署——从 Demo 到上线](#第十二章生产环境部署从-demo-到上线)
- [第十三章：Agent 安全与风险控制](#第十三章agent-安全与风险控制)
- [第十四章：常见问题诊断手册](#第十四章常见问题诊断手册)
- [第十五章：面试高频考题与答案](#第十五章面试高频考题与答案)
- [第十六章：实战项目方向与成长路线](#第十六章实战项目方向与成长路线)

---

## 第一章：核心概念——什么是 Agent

### 1.1 从 Tool Use 到 Agent 的自然进化

```
你已经学过的 Tool Use 流程：

用户提问 → LLM 选工具 → 执行工具 → 返回结果 → LLM 回答
                          ↑
                       只调一次

现在的问题：很多现实任务不是"一次调用"能完成的。

例子："帮我做一份竞品分析报告"
├─ 第 1 步：搜索竞品有哪些
├─ 第 2 步：逐个查询每个竞品的信息
├─ 第 3 步：搜索各竞品的最新新闻
├─ 第 4 步：对比分析优劣势
├─ 第 5 步：生成结构化报告
├─ 第 6 步：检查报告是否完整
├─ 第 7 步：补充遗漏的信息
└─ 第 8 步：最终定稿

这不是"调一次工具"能做到的。
需要的是：持续地思考 → 行动 → 观察 → 再思考 → 再行动...
这就是 Agent。
```

### 1.2 正式定义

```
Agent = LLM + 工具 + 循环 + 规划 + 记忆 + 终止条件

用你已经掌握的知识来理解：

LLM          → Step 1 学的（Prompt Engineering，和 LLM 对话）
工具         → Step 3 学的（Tool Use，让 LLM 调用外部能力）
循环         → 反复调用 LLM + 工具，直到任务完成
规划         → LLM 自主决定下一步做什么（不是你提前编排好的）
记忆         → 记住之前做过什么、发现了什么
终止条件     → 判断任务是否完成，知道什么时候该停

RAG 在哪？   → RAG 是 Agent 的工具之一（search_knowledge_base）
```

### 1.3 Agent vs 传统软件 vs Tool Use——三者的根本区别

```
传统软件（if-else 编程）：
├─ 开发者提前写死所有逻辑分支
├─ 遇到没预料到的情况 → 报错或走兜底逻辑
├─ 确定性：相同输入 → 相同输出
└─ 适合：规则清晰、流程固定的场景

Tool Use（你学过的）：
├─ LLM 决定调哪个工具、填什么参数
├─ 但调用次数和流程还是"比较线性"的
├─ 通常 1-3 轮就结束
└─ 适合：简单查询、单步操作

Agent：
├─ LLM 自主规划、决策、执行
├─ 循环次数不确定（可能 3 步完成，也可能 30 步）
├─ 能处理意外情况（第 5 步发现第 2 步的信息有误 → 返回重做）
├─ 非确定性：相同输入 → 可能不同输出（因为 LLM 推理路径不同）
└─ 适合：开放式、复杂、多步骤的任务
```

### 1.4 Agent 的能力边界——不是万能的

```
Agent 擅长的：                    Agent 不擅长的：
├─ 开放式研究和分析               ├─ 需要 100% 确定性的任务
├─ 多步骤信息收集                 ├─ 实时毫秒级响应
├─ 代码编写和调试                 ├─ 精确数值计算（应交给工具）
├─ 文档生成和审查                 ├─ 重复性流水线作业（用传统代码）
├─ 复杂决策支持                   ├─ 涉及物理操作的任务
└─ 跨系统数据整合                 └─ 不能容忍任何错误的场景

关键认知：
Agent 不是要取代传统软件，而是处理传统软件处理不了的
"模糊的、开放式的、需要理解和推理的"任务。

最好的系统 = Agent 处理模糊决策 + 传统代码处理确定性逻辑
```

---

## 第二章：Agent 的核心循环——理解"Loop"

### 2.1 最简 Agent 循环

```python
def simple_agent(task: str, tools: list, max_steps: int = 20):
    """最简单的 Agent 循环——理解核心概念"""

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": task}
    ]

    for step in range(max_steps):
        # ════ 思考：让 LLM 决定下一步 ════
        response = llm.call(messages=messages, tools=tools)

        # ════ 检查：任务完成了吗？ ════
        if response.stop_reason == "end_turn":
            return response.text  # 任务完成，返回最终答案

        # ════ 行动：执行 LLM 选择的工具 ════
        if response.stop_reason == "tool_use":
            tool_results = execute_tools(response.tool_calls)

            # ════ 观察：把结果反馈给 LLM ════
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

            # 继续循环 → LLM 看到结果后决定下一步

    return "达到最大步数限制，任务未完成"
```

### 2.2 核心循环的四个阶段

```
每一轮循环都包含四个阶段：

┌─────────────────────────────────────────────┐
│                                             │
│         ① 思考 (Reasoning)                  │
│         LLM 分析当前情况，决定下一步          │
│         "我需要先查一下竞品有哪些"             │
│                    │                        │
│                    ▼                        │
│         ② 行动 (Acting)                     │
│         调用工具执行操作                      │
│         search_competitors("AI 写作工具")    │
│                    │                        │
│                    ▼                        │
│         ③ 观察 (Observing)                  │
│         获取工具返回的结果                     │
│         "找到5个竞品：Jasper, Copy.ai..."     │
│                    │                        │
│                    ▼                        │
│         ④ 反思 (Reflecting)                 │
│         评估进展，判断是否继续                  │
│         "我已经找到竞品列表了，                │
│          接下来要查每个竞品的详细信息"          │
│                    │                        │
│                    ▼                        │
│              回到 ① 继续                     │
│              或者判断任务完成 → 输出结果        │
│                                             │
└─────────────────────────────────────────────┘
```

### 2.3 循环中消息历史的增长

```
这是初学者容易忽略的重要问题：每一轮循环都会增加消息。

第 1 轮后：
messages = [system, user, assistant(思考+tool_use), tool_result]

第 2 轮后：
messages = [system, user, assistant, tool_result,
            assistant(第2次思考+tool_use), tool_result]

第 5 轮后：
messages = [system, user, 
            assistant, tool_result,
            assistant, tool_result,
            assistant, tool_result,
            assistant, tool_result,
            assistant, tool_result]

问题：
├─ Token 消耗越来越多 → 成本上升
├─ 上下文窗口可能不够 → 信息被截断
├─ LLM 注意力分散 → 回答质量下降
└─ 每轮都要发送完整历史 → 延迟增加

解决方案（见第四章记忆系统）：
├─ 摘要压缩：把前几轮的详细信息压缩成摘要
├─ 滑动窗口：只保留最近 N 轮的完整信息
├─ 关键信息提取：把工具结果精简为关键数据
└─ 外部存储：把详细信息存到外部，需要时检索
```

### 2.4 一个完整的 Agent 执行示例

```
任务："帮我分析一下特斯拉最近的股价表现，如果跌幅超过5%就帮我发个提醒邮件"

Agent 执行过程：

Step 1 [思考]
  "用户要求分析特斯拉股价并根据条件发邮件。
   我需要先查询特斯拉的股价数据。"
Step 1 [行动]
  → get_stock_data(symbol="TSLA", period="30d")
Step 1 [观察]
  → 返回：30天股价数据，当前$178，30天前$195

Step 2 [思考]
  "拿到数据了。30天跌幅 = (195-178)/195 = 8.7%，超过5%。
   需要做更详细的分析，然后发邮件。
   让我先查一下最近的新闻，了解下跌原因。"
Step 2 [行动]
  → search_news(query="特斯拉 股价 下跌", days=30)
Step 2 [观察]
  → 返回：3条相关新闻（产能下降、竞争加剧、分析师下调评级）

Step 3 [思考]
  "现在我有足够的信息来生成分析报告了。
   跌幅8.7% > 5%，需要发邮件。
   让我构建邮件内容。"
Step 3 [行动]
  → send_email(
      to="user@company.com",
      subject="⚠️ 特斯拉(TSLA)30日跌幅8.7%，超过5%阈值",
      body="分析报告：当前$178，30天前$195，跌幅8.7%。
            主要原因：1)产能下降 2)竞争加剧 3)分析师下调评级。
            建议关注后续财报发布。"
    )
Step 3 [观察]
  → 返回：{"status": "sent", "message_id": "msg_123"}

Step 4 [思考]
  "任务完成了。我查了股价，做了分析，发了邮件。
   让我给用户一个总结。"
Step 4 [结束]
  → "分析完成：特斯拉(TSLA)近30天跌幅8.7%，已超过您设定的5%阈值。
     主要下跌原因包括产能数据不及预期、市场竞争加剧、
     以及多家分析师下调目标价位。
     提醒邮件已发送至 user@company.com。"
```

---

## 第三章：Agent 设计模式——四大经典范式

### 3.1 模式一：ReAct（Reasoning + Acting）

```
最经典、最常用的 Agent 模式。

核心思想：先推理（Reason），再行动（Act）。
每一步都要求 LLM 先说出自己的思考过程，再决定行动。

ReAct 的 System Prompt 核心结构：

"你是一个智能助手，使用以下格式回答问题：

Thought: 我需要思考一下这个问题...
         我应该先做什么...
         我注意到...

Action: 工具名称
Action Input: {"参数": "值"}

Observation: [工具返回的结果]

Thought: 根据上面的结果，我现在知道了...
         接下来我应该...

Action: ...
...

Thought: 我已经收集了足够的信息，可以回答用户了。
Final Answer: 最终回答。"
```

**ReAct 的优缺点：**

| 维度 | 优点 | 缺点 |
|------|------|------|
| **可解释性** | 每一步都有推理过程，容易调试 | 推理文本增加 Token 消耗 |
| **准确性** | 思考后再行动，减少盲目调用 | 推理本身可能出错 |
| **灵活性** | 能处理各种意外情况 | 开放式推理可能导致偏离 |
| **实现难度** | 简单，只需要一个循环 | 需要设计好 Prompt |

```python
# ReAct Agent 的简化实现
REACT_SYSTEM_PROMPT = """你是一个研究助手。使用工具获取信息并回答问题。

对于每个步骤，请按以下格式输出：
1. 先思考当前情况和下一步计划
2. 如果需要更多信息，调用工具
3. 如果信息足够，给出最终答案

重要规则：
- 每一步都要先思考再行动
- 如果工具返回错误，分析原因并尝试其他方法
- 不确定时承认不确定，不要编造信息
"""

async def react_agent(task: str, tools: list, max_steps: int = 15):
    messages = [
        {"role": "system", "content": REACT_SYSTEM_PROMPT},
        {"role": "user", "content": task}
    ]

    for step in range(max_steps):
        response = await llm.call(messages=messages, tools=tools)

        if response.stop_reason == "end_turn":
            return extract_final_answer(response)

        if response.stop_reason == "tool_use":
            tool_results = await execute_tools(response.tool_calls)
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

    return "任务未在最大步数内完成"
```

### 3.2 模式二：Plan-then-Execute（先规划再执行）

```
核心思想：先让 LLM 制定一个完整的执行计划，然后逐步执行。
遇到偏差时，重新规划。

与 ReAct 的区别：
├─ ReAct：走一步看一步（边想边做）
├─ Plan-then-Execute：先想清楚再做（先规划后执行）
└─ 各有各的适用场景

执行流程：

┌──────────────────────────────────────────────┐
│                                              │
│   用户任务："做一份市场调研报告"                 │
│              │                               │
│              ▼                               │
│   ┌─── 规划阶段（Planner LLM）───┐            │
│   │                              │           │
│   │  计划：                       │           │
│   │  1. 确定调研范围和维度         │           │
│   │  2. 搜索行业报告数据          │           │
│   │  3. 查询竞品信息              │           │
│   │  4. 分析市场趋势              │           │
│   │  5. 生成报告初稿              │           │
│   │  6. 审查和完善报告             │           │
│   │                              │           │
│   └──────────┬───────────────────┘           │
│              │                               │
│              ▼                               │
│   ┌─── 执行阶段（Executor LLM）──┐            │
│   │                              │           │
│   │  逐步执行计划                 │           │
│   │  Step 1 → 执行 → 结果 ✓      │           │
│   │  Step 2 → 执行 → 结果 ✓      │           │
│   │  Step 3 → 执行 → 失败 ✗      │ ──→ 重新规划│
│   │                              │           │
│   └──────────────────────────────┘           │
│                                              │
└──────────────────────────────────────────────┘
```

```python
async def plan_then_execute_agent(task: str, tools: list):
    # ════ Phase 1: 规划 ════
    plan = await create_plan(task)
    # plan = ["搜索竞品列表", "查询各竞品详情", "对比分析", "生成报告"]

    results = {}

    for i, step in enumerate(plan):
        # ════ Phase 2: 执行每一步 ════
        try:
            result = await execute_step(step, tools, context=results)
            results[f"step_{i}"] = result

        except StepFailure as e:
            # ════ Phase 3: 遇到问题时重新规划 ════
            remaining_steps = plan[i:]
            new_plan = await replan(
                original_task=task,
                completed=results,
                failed_step=step,
                error=str(e),
                remaining=remaining_steps
            )
            plan = plan[:i] + new_plan  # 替换剩余计划

    # ════ Phase 4: 汇总结果 ════
    final_answer = await synthesize(task, results)
    return final_answer
```

**Plan-then-Execute 的适用场景：**

```
适合的场景：
├─ 任务步骤比较明确和可预测
│   例：数据分析流程、报告生成、文档处理
├─ 任务较复杂，需要全局视角
│   例：项目管理、方案设计
├─ 需要预估资源和时间
│   例：用户需要知道"大概要多久"
└─ 需要向用户展示执行计划
    例：用户想先审批计划再执行

不适合的场景：
├─ 信息高度不确定（不知道会发现什么）
├─ 任务定义模糊（"帮我看看有什么问题"）
└─ 需要频繁即兴应对（对话式交互）
```

### 3.3 模式三：Reflexion（反思型 Agent）

```
核心思想：Agent 执行完任务后，自我评估执行质量，
如果不满意就基于反思改进，然后重新执行。

这类似于人类的"做完检查一遍"行为。

流程：

┌────────────────────────────────────────┐
│                                        │
│   执行任务 → 产出结果                    │
│               │                        │
│               ▼                        │
│   自我评估："这个结果好不好？"              │
│     ┌────┴─────┐                       │
│     好          不好                    │
│     │           │                      │
│     ▼           ▼                      │
│   返回结果   反思："哪里不好？为什么？"     │
│                  │                     │
│                  ▼                     │
│             改进策略                    │
│                  │                     │
│                  ▼                     │
│             重新执行（带着反思经验）       │
│                  │                     │
│                  ▼                     │
│             再次评估...                 │
│                                        │
└────────────────────────────────────────┘
```

```python
async def reflexion_agent(task: str, tools: list, max_retries: int = 3):
    reflections = []  # 累积的反思记录

    for attempt in range(max_retries):
        # ════ 执行（带上之前的反思经验）════
        context = ""
        if reflections:
            context = "之前的尝试和反思：\n" + "\n".join(reflections)
            context += "\n\n请基于以上反思改进你的执行。"

        result = await react_agent(
            task=task + "\n" + context,
            tools=tools
        )

        # ════ 自我评估 ════
        evaluation = await llm.call(
            messages=[{
                "role": "user",
                "content": f"""请评估以下任务执行结果的质量：

任务：{task}
结果：{result}

评估维度：
1. 完整性：是否完成了所有要求？（1-10分）
2. 准确性：信息是否正确？（1-10分）
3. 实用性：结果是否有用？（1-10分）

如果总分 >= 24 分，输出 PASS。
否则输出 FAIL 并详细说明哪里需要改进。"""
            }]
        )

        if "PASS" in evaluation.text:
            return result

        # ════ 反思 ════
        reflection = await llm.call(
            messages=[{
                "role": "user",
                "content": f"""任务执行未达标。请分析原因并给出改进策略。

任务：{task}
执行结果：{result}
评估反馈：{evaluation.text}

请输出：
1. 具体哪里做得不好
2. 为什么会这样
3. 下次应该怎么改进"""
            }]
        )

        reflections.append(
            f"第{attempt+1}次尝试：{reflection.text}"
        )

    return result  # 达到最大重试次数，返回最后一次结果
```

**Reflexion 的核心价值：**

```
不是简单的"重试"，而是"带着反思经验的重试"。

简单重试：
  执行 → 失败 → 重新执行（用一模一样的方式）
  → 大概率还是失败

Reflexion：
  执行 → 失败 → 分析为什么失败 → 制定改进策略 → 带着改进策略重试
  → 有机会成功

适用场景：
├─ 代码生成（写代码 → 运行测试 → 失败 → 反思 → 修改 → 再测试）
├─ 写作（写初稿 → 自我审查 → 发现问题 → 修改 → 再审查）
├─ 数据分析（分析数据 → 检查结论合理性 → 发现遗漏 → 补充分析）
└─ 任何有"质量标准"可以自动检测的任务
```

### 3.4 模式四：多 Agent 协作（Orchestrator + Workers）

```
核心思想：一个主 Agent 负责分解任务和分配工作，
多个子 Agent 各自完成自己的部分。

类比：项目经理 + 工程师团队

┌──────────────────────────────────────────┐
│                                          │
│   用户任务                                │
│      │                                   │
│      ▼                                   │
│   ┌──────────────────┐                   │
│   │  Orchestrator    │  主 Agent          │
│   │  (项目经理)       │                   │
│   └──┬──────┬───────┬┘                   │
│      │      │       │                    │
│      ▼      ▼       ▼                    │
│   ┌────┐ ┌────┐ ┌────┐                  │
│   │ W1 │ │ W2 │ │ W3 │  子 Agent        │
│   │研究│ │分析│ │写作│  (工程师)         │
│   └──┬─┘ └──┬─┘ └──┬─┘                  │
│      │      │       │                    │
│      ▼      ▼       ▼                    │
│   ┌──────────────────┐                   │
│   │  Orchestrator    │  汇总结果          │
│   │  汇总 + 质检     │                   │
│   └──────────────────┘                   │
│                                          │
└──────────────────────────────────────────┘

详见第九章"多 Agent 系统"
```

### 3.5 四种模式的选择指南

```
决策树：选择哪种 Agent 模式？

你的任务是什么？
│
├─ 简单的多步骤任务（3-8步）
│   └─ → ReAct（最简单、最通用）
│
├─ 步骤明确的复杂任务（>8步）
│   └─ → Plan-then-Execute（先规划再执行）
│
├─ 有明确质量标准的任务（可自动检测对错）
│   └─ → Reflexion（执行+反思+改进）
│
├─ 可分解为独立子任务的大型任务
│   └─ → 多 Agent 协作
│
└─ 不确定？
    └─ → 从 ReAct 开始，不够用再升级

实际项目中：
├─ 80% 的场景 ReAct 就够了
├─ 复杂场景用 Plan-then-Execute
├─ 质量敏感场景叠加 Reflexion
└─ 大型任务用多 Agent
```

---

## 第四章：记忆系统——Agent 的大脑

### 4.1 为什么 Agent 需要记忆

```
没有记忆的 Agent：

Step 1: 搜索"特斯拉"→ 找到公司信息
Step 2: 搜索"特斯拉股价"→ 又搜到一次公司信息
Step 3: "这个特斯拉是做什么的来着？"→ 已经忘了 Step 1 的结果
...
效率低、质量差、Token 浪费

有记忆的 Agent：
Step 1: 搜索"特斯拉"→ 记住：电动车公司，CEO 马斯克
Step 2: 搜索股价 → 记住：当前 $178，30天前 $195
Step 3: 结合已有信息分析 → 不需要重复搜索
...
高效、连贯、节省成本
```

### 4.2 四种记忆类型

```
┌─────────────────────────────────────────────────────────┐
│                                                         │
│  ① 短期记忆 (Short-term Memory)                         │
│  ═══════════════════════════                             │
│  存什么：当前对话的完整消息历史                             │
│  存在哪：LLM 的 messages 数组                             │
│  保留多久：当前会话结束就没了                               │
│  容量限制：受模型上下文窗口限制                             │
│  你已经很熟悉了——就是你学 Prompt 时的"对话上下文"           │
│                                                         │
│  问题：消息越来越多 → Token 爆炸 → 怎么办？                │
│                                                         │
│  解决方案：                                               │
│  ├─ 滑动窗口：只保留最近 N 轮，早期的丢弃                   │
│  ├─ 摘要压缩：让 LLM 把前面的对话压缩成摘要                 │
│  └─ 关键信息提取：只保留工具结果的关键字段                   │
│                                                         │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ② 工作记忆 (Working Memory)                             │
│  ═══════════════════════════                             │
│  存什么：当前任务的中间状态、已完成的步骤、待办事项           │
│  存在哪：一个结构化的变量/文档（称为 Scratchpad）            │
│  保留多久：当前任务完成就没了                               │
│  容量限制：无（存在外部变量中）                             │
│                                                         │
│  类比：你做数学题时在草稿纸上写的中间步骤                    │
│                                                         │
│  示例（Scratchpad 内容）：                                │
│  ┌──────────────────────────────┐                       │
│  │ 当前任务：竞品分析报告                │                       │
│  │ 已完成：                          │                       │
│  │  ✅ 1. 找到5个竞品                 │                       │
│  │  ✅ 2. 查询了Jasper的信息           │                       │
│  │  🔄 3. 正在查询Copy.ai            │                       │
│  │ 待完成：                          │                       │
│  │  ⬜ 4. 查询 Writesonic            │                       │
│  │  ⬜ 5. 对比分析                   │                       │
│  │  ⬜ 6. 生成报告                   │                       │
│  │ 中间发现：                        │                       │
│  │  - Jasper 被收购了（2024-02）      │                       │
│  │  - 这可能影响市场格局分析           │                       │
│  └──────────────────────────────┘                       │
│                                                         │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ③ 长期记忆 (Long-term Memory)                           │
│  ═══════════════════════════                             │
│  存什么：跨会话需要保留的信息                               │
│  存在哪：向量数据库 / 关系数据库 / 文件系统                  │
│  保留多久：永久（直到被删除或更新）                          │
│  容量限制：无（外部存储）                                   │
│                                                         │
│  类比：你的笔记本——记录长期有用的信息                        │
│                                                         │
│  子类型：                                                │
│  ├─ 事实记忆：用户的名字、偏好、公司信息                     │
│  │   "用户是销售经理，关注快消品行业"                        │
│  ├─ 事件记忆：之前做过什么                                  │
│  │   "上周帮用户分析过竞品A，结论是..."                      │
│  └─ 经验记忆：学到的教训                                   │
│      "用户不喜欢太长的报告，上次被要求缩减过"                 │
│                                                         │
│  实现方式（本质就是 RAG！）：                               │
│  ├─ 记忆写入 = 文本 → Embedding → 存入向量数据库            │
│  ├─ 记忆读取 = 查询 → Embedding → 从向量数据库检索          │
│  └─ 你在 Step 2 学的 RAG 技术直接应用在这里                  │
│                                                         │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ④ 外部知识记忆 (External Knowledge)                     │
│  ═════════════════════════════════                       │
│  存什么：企业知识库、文档库、数据库                          │
│  存在哪：RAG 系统、数据库、API                              │
│  保留多久：独立维护                                        │
│  容量限制：几乎无限                                        │
│                                                         │
│  这就是你学过的 RAG！Agent 通过工具访问这些知识。             │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### 4.3 短期记忆管理策略

```python
# 策略 1：滑动窗口——只保留最近 N 轮
def sliding_window(messages: list, max_rounds: int = 10) -> list:
    system_msg = messages[0]   # System Prompt 始终保留
    user_task = messages[1]    # 用户原始任务始终保留
    recent = messages[-(max_rounds * 2):]  # 保留最近 N 轮
    return [system_msg, user_task] + recent


# 策略 2：摘要压缩——用 LLM 压缩早期对话
async def compress_history(messages: list, keep_recent: int = 6) -> list:
    if len(messages) <= keep_recent + 2:
        return messages  # 不需要压缩

    system_msg = messages[0]
    user_task = messages[1]
    old_messages = messages[2:-(keep_recent)]
    recent_messages = messages[-(keep_recent):]

    # 用 LLM 摘要早期对话
    summary = await llm.call(
        messages=[{
            "role": "user",
            "content": f"请把以下对话历史压缩成一段摘要，保留关键信息和发现：\n\n"
                       + format_messages(old_messages)
        }]
    )

    # 用摘要替代详细历史
    summary_message = {
        "role": "user",
        "content": f"[之前的执行摘要]\n{summary.text}\n[摘要结束]"
    }

    return [system_msg, user_task, summary_message] + recent_messages


# 策略 3：工具结果精简——只保留关键数据
def trim_tool_result(result: dict, max_length: int = 500) -> str:
    result_str = json.dumps(result, ensure_ascii=False)
    if len(result_str) <= max_length:
        return result_str

    # 如果结果是列表，只保留前几项 + 总数
    if isinstance(result, list):
        return json.dumps({
            "items": result[:3],
            "total_count": len(result),
            "note": f"共{len(result)}项，仅展示前3项"
        }, ensure_ascii=False)

    # 如果结果太长，截断
    return result_str[:max_length] + f"...(截断，原始长度{len(result_str)})"
```

### 4.4 长期记忆的实现

```python
# 长期记忆本质上就是 RAG——你已经学过了！

class LongTermMemory:
    def __init__(self, vector_db, embedding_model):
        self.db = vector_db
        self.embed = embedding_model

    async def save(self, content: str, metadata: dict):
        """保存一条记忆"""
        # 就是 RAG 的索引流程
        embedding = await self.embed.encode(content)
        self.db.insert(
            vector=embedding,
            content=content,
            metadata={
                **metadata,
                "timestamp": now(),
                "type": "memory"
            }
        )

    async def recall(self, query: str, top_k: int = 5) -> list:
        """回忆相关信息"""
        # 就是 RAG 的检索流程
        query_embedding = await self.embed.encode(query)
        results = self.db.search(query_embedding, top_k=top_k)
        return results

    async def forget(self, memory_id: str):
        """遗忘（删除过时信息）"""
        self.db.delete(memory_id)

# 在 Agent 循环中使用长期记忆
async def agent_with_memory(task, tools, memory: LongTermMemory):
    # 开始前，回忆相关信息
    relevant_memories = await memory.recall(task)
    context = format_memories(relevant_memories)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT + f"\n\n相关记忆：\n{context}"},
        {"role": "user", "content": task}
    ]

    result = await react_agent_loop(messages, tools)

    # 完成后，保存新的记忆
    await memory.save(
        content=f"用户请求：{task}\n执行结果摘要：{summarize(result)}",
        metadata={"user_id": current_user.id, "task_type": "analysis"}
    )

    return result
```

---

## 第五章：规划与任务分解——Agent 的思考能力

### 5.1 任务分解（Task Decomposition）

```
大任务直接给 Agent → 容易失败
大任务分解成小任务 → 每个小任务 Agent 都能完成

例子：
❌ "帮我做一个完整的竞品分析"
  → Agent 不知道从哪开始，容易遗漏

✅ 分解成：
  1. "确定要分析的竞品列表"
  2. "收集每个竞品的基本信息"
  3. "收集价格和功能对比"
  4. "分析优劣势"
  5. "生成结论和建议"
  → 每一步都很明确，Agent 能可靠完成
```

### 5.2 两种分解方式

```
方式 1：前置分解（Planner 模式）
├─ 在执行前，先让 LLM 制定完整计划
├─ 优点：全局视角，不会遗漏
├─ 缺点：计划可能不准（因为还没开始做，信息不足）
├─ 适合：步骤可预测的任务
└─ 示例 Prompt：
   "请将以下任务分解为 3-7 个具体步骤，
    每步应该独立且可执行：
    任务：{task}"

方式 2：动态分解（ReAct 模式）
├─ 边做边分解，每做完一步再决定下一步
├─ 优点：灵活，能根据发现调整
├─ 缺点：可能遗漏全局视角
├─ 适合：探索性、信息不确定的任务
└─ 工作方式：
   LLM 每步都在 Thought 中决定下一步做什么
```

### 5.3 规划 Prompt 的设计

```python
PLANNER_PROMPT = """你是一个任务规划专家。请将用户的任务分解为具体的执行步骤。

规则：
1. 每个步骤必须是一个独立的、可执行的操作
2. 步骤之间有明确的先后顺序
3. 每个步骤描述清楚需要使用什么工具
4. 步骤数量控制在 3-8 步（太少说明分解不够细，太多说明过度分解）
5. 预留一个"审查和验证"步骤在最后

输出格式：
{
  "goal": "任务的最终目标",
  "steps": [
    {
      "id": 1,
      "action": "具体要做什么",
      "tool": "需要使用的工具名",
      "depends_on": [],
      "expected_output": "预期产出"
    },
    ...
  ]
}

用户任务：{task}
可用工具：{tools}
"""
```

### 5.4 计划的动态调整（Re-planning）

```
现实情况：计划赶不上变化。

典型场景：
├─ Step 2 发现 Step 1 获取的信息有误 → 需要返回修正
├─ Step 3 发现需要一个计划中没有的额外步骤 → 需要插入
├─ Step 4 的工具调用失败 → 需要换方案
├─ 用户中途修改了需求 → 需要调整剩余计划
└─ 发现任务比预期简单 → 可以跳过某些步骤

Re-planning 的实现思路：

async def execute_with_replan(task, plan, tools):
    completed = {}

    for step in plan:
        result = await execute_step(step, tools)

        if result.success:
            completed[step.id] = result
        else:
            # 执行失败 → 重新规划剩余步骤
            remaining = [s for s in plan if s.id > step.id]
            new_plan = await replan(
                task=task,
                completed=completed,
                failed=step,
                error=result.error,
                remaining=remaining
            )
            plan = list(completed_steps) + new_plan

    return synthesize(completed)
```

---

## 第六章：工具编排——Agent 的执行能力

### 6.1 从 Tool Use 到 Agent 的工具编排

```
Tool Use（你学过的）          Agent 的工具编排
─────────────────           ─────────────────────
工具数量固定                  工具可以动态加载
调用 1-3 次                  调用 N 次（直到完成）
调用逻辑线性                  调用逻辑由 LLM 决定
错误 → 报给用户              错误 → Agent 自己处理
无上下文积累                  有记忆，知道之前做过什么
```

### 6.2 Agent 常用工具类型

```
一个功能完整的 Agent 通常需要这些工具类别：

信息获取类（输入）：
├─ search_web          → 搜索互联网
├─ search_knowledge_base → 搜索内部知识库（你学过的 RAG）
├─ read_file           → 读取文件内容
├─ query_database      → 查询数据库
├─ get_api_data        → 调用外部 API
└─ scrape_webpage      → 抓取网页内容

分析计算类（处理）：
├─ run_code            → 执行代码（Python 等）
├─ calculate           → 数学计算
├─ analyze_data        → 数据分析
└─ compare             → 对比分析

内容生成类（输出）：
├─ generate_report     → 生成报告
├─ create_chart        → 生成图表
├─ write_document      → 撰写文档
└─ format_output       → 格式化输出

动作执行类（操作）：
├─ send_email          → 发送邮件
├─ create_task         → 创建任务
├─ update_record       → 更新记录
├─ schedule_meeting    → 安排会议
└─ notify_user         → 通知用户

Agent 自身控制类（元操作）：
├─ save_memory         → 保存记忆
├─ recall_memory       → 回忆信息
├─ create_subtask      → 创建子任务
├─ ask_user            → 向用户提问
└─ finish              → 标记任务完成
```

### 6.3 工具编排模式

```
模式 1：顺序链（Pipeline）
  tool_A → tool_B → tool_C
  每个工具的输出是下一个工具的输入

  例：search("特斯拉") → analyze(搜索结果) → generate_report(分析结果)

模式 2：并行扇出（Fan-out）
  同时调用多个工具
         ├→ tool_A → result_A
  input ─├→ tool_B → result_B ─→ 汇总
         └→ tool_C → result_C

  例：同时搜索三个竞品的信息，然后汇总对比

模式 3：条件分支（Conditional）
  if 条件A → tool_A
  elif 条件B → tool_B
  else → tool_C

  例：查到库存充足 → 直接下单 / 库存不足 → 通知采购

模式 4：循环重试（Loop）
  while not success:
      tool_A → check → 不满足 → 调整参数 → tool_A

  例：生成代码 → 运行测试 → 失败 → 修改代码 → 再测试

模式 5：递归分解（Recursive）
  task → 分解 → [subtask_1, subtask_2]
                    ├→ subtask_1_a
                    └→ subtask_1_b

  例：分析大文档 → 按章节分解 → 分别分析 → 汇总
```

### 6.4 Agent 特有的工具——ask_user

```
这是 Agent 独有的重要工具：向用户提问。

为什么需要这个工具？

当 Agent 遇到以下情况时，应该问用户而不是自己猜测：

1. 信息不足
   "您说的'那个项目'是指 Project A 还是 Project B？"

2. 需要确认
   "我找到了3个可能的航班，您更偏好直飞还是价格最低的？"

3. 有歧义
   "'客户满意度'是指调查问卷评分还是 NPS 得分？"

4. 高风险决策
   "这个操作将删除所有历史数据，是否确认？"

实现方式：
├─ 把 ask_user 定义为一个工具
├─ 当 LLM 调用这个工具时，暂停 Agent 循环
├─ 等待用户回答
└─ 把用户回答作为工具结果返回，继续循环

工具定义：
{
    "name": "ask_user",
    "description": "当你需要用户提供更多信息或确认时使用。不要猜测重要信息。",
    "input_schema": {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "要向用户提出的问题，必须清晰具体"
            },
            "options": {
                "type": "array",
                "items": {"type": "string"},
                "description": "可选，给用户提供的选项列表"
            }
        },
        "required": ["question"]
    }
}
```

---

## 第七章：终止策略——知道什么时候该停

### 7.1 为什么终止策略至关重要

```
没有好的终止策略的后果：

1. 无限循环
   Agent 反复调用工具但无法完成任务
   → Token 消耗爆炸、用户等不到结果

2. 过早终止
   Agent 只完成了一部分就停了
   → 用户得到不完整的结果

3. 过度工作
   任务已经完成但 Agent 继续"优化"
   → 浪费资源、可能改坏已有结果

终止策略的目标：在"做够了"和"做过了"之间找到平衡
```

### 7.2 六种终止条件

```
条件 1：LLM 自主判断——让 LLM 自己决定
  ════════════════════════════════════
  实现：LLM 输出 end_turn 而不是 tool_use
  优点：最灵活，LLM 根据任务实际情况判断
  缺点：LLM 可能判断失误
  适用：大多数场景的基础终止方式

  Prompt 指导：
  "当你认为任务已完成，给出最终答案。
   不要在信息不充分时草率结束。
   不要在任务已完成后继续不必要的操作。"


条件 2：最大步数限制——强制安全线
  ════════════════════════════════
  实现：max_steps = 20，超过就停
  优点：绝对安全，不会无限循环
  缺点：复杂任务可能需要更多步
  适用：所有场景（必须有，作为兜底）

  建议值：
  ├─ 简单任务：5-10 步
  ├─ 中等任务：10-20 步
  └─ 复杂任务：20-50 步


条件 3：超时限制——时间维度的安全线
  ══════════════════════════════
  实现：timeout = 120 秒
  优点：保证用户不会等太久
  缺点：长任务可能被截断
  适用：面向用户的实时交互场景


条件 4：成本预算——Token/API 消耗限制
  ══════════════════════════════════
  实现：max_tokens = 50000 或 max_api_calls = 10
  优点：控制成本
  缺点：可能在关键步骤被截断
  适用：成本敏感的生产环境


条件 5：完成标准检测——自动验证
  ═══════════════════════════
  实现：每轮检查是否满足预定义的完成条件
  优点：精确，不依赖 LLM 的判断
  缺点：需要能定义明确的完成条件
  适用：有明确输出格式的任务

  示例：
  def is_complete(result):
      # 报告生成任务的完成条件
      return (
          "摘要" in result and
          "分析" in result and
          "结论" in result and
          len(result) > 500
      )


条件 6：用户干预——人工终止
  ═══════════════════════
  实现：用户可以随时取消或结束
  优点：用户保持控制权
  缺点：需要 UI 支持
  适用：交互式场景
```

### 7.3 组合终止策略

```python
class TerminationManager:
    """组合多种终止条件"""

    def __init__(
        self,
        max_steps: int = 20,
        max_time_seconds: int = 120,
        max_tokens: int = 50000,
        max_tool_calls: int = 30
    ):
        self.max_steps = max_steps
        self.max_time = max_time_seconds
        self.max_tokens = max_tokens
        self.max_tool_calls = max_tool_calls
        self.start_time = time.time()
        self.steps = 0
        self.tokens_used = 0
        self.tool_calls = 0

    def should_stop(self) -> tuple[bool, str]:
        """检查是否应该终止"""
        self.steps += 1

        if self.steps > self.max_steps:
            return True, f"达到最大步数限制 ({self.max_steps})"

        elapsed = time.time() - self.start_time
        if elapsed > self.max_time:
            return True, f"超时 ({self.max_time}s)"

        if self.tokens_used > self.max_tokens:
            return True, f"Token 消耗超限 ({self.max_tokens})"

        if self.tool_calls > self.max_tool_calls:
            return True, f"工具调用次数超限 ({self.max_tool_calls})"

        return False, ""

    def record_usage(self, tokens: int, tool_calls: int):
        self.tokens_used += tokens
        self.tool_calls += tool_calls
```

---

## 第八章：Human-in-the-Loop——人机协作

### 8.1 什么是 Human-in-the-Loop（HITL）

```
HITL = 在 Agent 执行过程中，特定节点引入人工参与。

不是让人做所有事（那就不需要 Agent 了）
也不是完全不让人参与（那风险太高了）
而是让人在关键节点做决策和确认。

三种人工参与模式：

模式 1：审批模式（Approval）
  Agent 做 → 人审批 → 通过才执行
  例：Agent 生成邮件内容 → 人确认 → 才发送

模式 2：引导模式（Guidance）
  Agent 做 → 给出多个方案 → 人选择 → Agent 继续
  例：Agent 找到3种解决方案 → 用户选择一种 → Agent 执行

模式 3：监督模式（Supervision）
  Agent 自动执行 → 人随时可以干预
  例：Agent 自动处理工单 → 人工可以随时接管

企业级项目中，HITL 几乎是必须的！
```

### 8.2 何时需要人工介入

```
决策矩阵：什么时候需要人工？

                     操作可逆？
                   是          否
              ┌──────────┬──────────┐
风险高        │  人监督   │  必须审批  │
              │  高额交易 │  删除数据  │
              ├──────────┼──────────┤
风险低        │  自动执行 │  人确认    │
              │  查询数据 │  发送邮件  │
              └──────────┴──────────┘

具体场景清单：

必须审批（不能跳过）：
├─ 涉及金钱的操作（转账、下单、退款）
├─ 不可逆的操作（删除、发布、发送）
├─ 涉及个人隐私（共享数据、授权访问）
├─ 超出预设阈值（金额 > 1000、批量 > 100）
└─ Agent 不确定的决策（置信度低于阈值）

建议确认（可以设为自动）：
├─ 修改配置或设置
├─ 创建新记录
├─ 文件操作（创建、移动、重命名）
└─ 发送通知

可以自动（不需要人工）：
├─ 只读查询（搜索、查看、统计）
├─ 数据分析和计算
├─ 报告生成（未发送）
└─ 信息汇总和格式化
```

### 8.3 HITL 的实现架构

```python
class HumanInTheLoop:
    """人机协作管理器"""

    # 需要审批的操作
    REQUIRE_APPROVAL = {"send_email", "create_order", "delete_record",
                        "transfer_money", "publish_content"}

    # 需要确认的操作
    REQUIRE_CONFIRMATION = {"update_config", "create_record", "modify_file"}

    async def check_and_execute(self, tool_name, tool_input, agent_reasoning):
        """检查是否需要人工介入"""

        # Level 1：需要审批
        if tool_name in self.REQUIRE_APPROVAL:
            approval = await self.request_approval(
                action=tool_name,
                params=tool_input,
                reasoning=agent_reasoning,
                risk_level="high"
            )
            if not approval.approved:
                return {
                    "status": "rejected",
                    "message": f"用户拒绝了操作：{approval.reason}"
                }

        # Level 2：需要确认
        elif tool_name in self.REQUIRE_CONFIRMATION:
            confirmed = await self.request_confirmation(
                action=tool_name,
                params=tool_input,
                reasoning=agent_reasoning
            )
            if not confirmed:
                return {
                    "status": "cancelled",
                    "message": "用户取消了操作"
                }

        # Level 3：自动执行
        result = await execute_tool(tool_name, tool_input)

        # 记录审计日志
        await self.audit_log.record(
            action=tool_name,
            params=tool_input,
            result=result,
            approval_status="approved" if tool_name in self.REQUIRE_APPROVAL else "auto"
        )

        return result

    async def request_approval(self, action, params, reasoning, risk_level):
        """向用户请求审批"""
        # 构造可读的审批信息
        message = f"""
Agent 请求执行以下操作：

操作：{action}
参数：{json.dumps(params, ensure_ascii=False, indent=2)}
风险等级：{risk_level}

Agent 的理由：
{reasoning}

请审批：[批准] [拒绝]
"""
        return await self.notify_user_and_wait(message)
```

### 8.4 风险评分系统

```python
class RiskScorer:
    """评估操作的风险级别"""

    def score(self, tool_name: str, tool_input: dict) -> dict:
        risk_score = 0
        risk_factors = []

        # 因子 1：操作类型
        if tool_name.startswith("delete"):
            risk_score += 40
            risk_factors.append("删除操作")
        elif tool_name.startswith("send") or tool_name.startswith("publish"):
            risk_score += 30
            risk_factors.append("外发操作")
        elif tool_name.startswith("create") or tool_name.startswith("update"):
            risk_score += 20
            risk_factors.append("写入操作")

        # 因子 2：影响范围
        if "all" in str(tool_input).lower() or "batch" in str(tool_input).lower():
            risk_score += 30
            risk_factors.append("批量操作")

        # 因子 3：金额（如果有）
        amount = tool_input.get("amount", 0)
        if amount > 10000:
            risk_score += 40
            risk_factors.append(f"涉及金额 {amount}")
        elif amount > 1000:
            risk_score += 20
            risk_factors.append(f"涉及金额 {amount}")

        # 风险等级判定
        if risk_score >= 60:
            level = "high"        # 必须人工审批
        elif risk_score >= 30:
            level = "medium"      # 需要确认
        else:
            level = "low"         # 可自动执行

        return {
            "score": risk_score,
            "level": level,
            "factors": risk_factors
        }
```

---

## 第九章：多 Agent 系统——从个体到团队

### 9.1 为什么需要多 Agent

```
单 Agent 的局限：

1. 上下文窗口限制
   一个 Agent 处理超大任务时，消息历史会超出上下文窗口

2. 专业能力限制
   一个 System Prompt 不可能让 LLM 同时精通所有领域

3. 并行能力限制
   单 Agent 是串行执行的，一次只做一件事

4. 错误扩散
   单 Agent 一个步骤出错，后续步骤都受影响

多 Agent 的解决方案：
├─ 每个 Agent 有自己的 System Prompt（专业化）
├─ 每个 Agent 有自己的上下文（独立记忆）
├─ 多个 Agent 可以并行工作（提高效率）
└─ Agent 之间相互检查（减少错误）
```

### 9.2 多 Agent 架构模式

#### 模式一：Orchestrator-Worker（最常用）

```
┌────────────────────────────────────────┐
│                                        │
│         Orchestrator Agent             │
│         （指挥者/协调者）                │
│                                        │
│   职责：                                │
│   ├─ 分解任务                           │
│   ├─ 分配给合适的 Worker                │
│   ├─ 收集和汇总结果                     │
│   └─ 质量检查                           │
│                                        │
│          ┌─────┼─────┐                 │
│          ▼     ▼     ▼                 │
│       ┌─────┐┌─────┐┌─────┐           │
│       │ W1  ││ W2  ││ W3  │           │
│       │研究 ││分析 ││写作 │           │
│       │Agent││Agent││Agent│           │
│       └─────┘└─────┘└─────┘           │
│                                        │
│   每个 Worker：                         │
│   ├─ 有自己的 System Prompt             │
│   ├─ 有自己的工具集                     │
│   ├─ 只负责自己的子任务                  │
│   └─ 向 Orchestrator 报告结果           │
│                                        │
└────────────────────────────────────────┘
```

```python
async def orchestrator_worker_example(task: str):
    """Orchestrator-Worker 模式示例"""

    # ════ Orchestrator 分解任务 ════
    orchestrator = Agent(
        system_prompt="你是项目经理，负责将任务分解为子任务并分配。",
        tools=[create_subtask, assign_worker, collect_results]
    )

    plan = await orchestrator.plan(task)
    # plan = [
    #   {"subtask": "研究竞品", "worker": "researcher"},
    #   {"subtask": "分析数据", "worker": "analyst"},
    #   {"subtask": "撰写报告", "worker": "writer"}
    # ]

    # ════ Workers 并行执行 ════
    workers = {
        "researcher": Agent(
            system_prompt="你是研究专家，擅长信息收集和整理。",
            tools=[search_web, search_database, read_document]
        ),
        "analyst": Agent(
            system_prompt="你是数据分析师，擅长数据分析和可视化。",
            tools=[query_database, run_code, create_chart]
        ),
        "writer": Agent(
            system_prompt="你是专业写手，擅长撰写清晰的商业报告。",
            tools=[generate_report, format_document]
        )
    }

    # 并行执行独立的子任务
    results = await asyncio.gather(*[
        workers[step["worker"]].execute(step["subtask"])
        for step in plan
        if step can run in parallel
    ])

    # ════ Orchestrator 汇总结果 ════
    final_report = await orchestrator.synthesize(results)
    return final_report
```

#### 模式二：Supervisor（监督者模式）

```
和 Orchestrator-Worker 的区别：
├─ Orchestrator 模式：指挥者提前分好任务，Worker 独立执行
├─ Supervisor 模式：监督者在过程中持续监控和调度
└─ 更像"带队巡逻"而不是"分配作业"

┌──────────────────────────────────────┐
│                                      │
│        Supervisor Agent              │
│        持续监控各 Agent 的工作         │
│             ↕ 实时通信                │
│      ┌──────┼──────┐                 │
│      ↕      ↕      ↕                 │
│   Agent A  Agent B  Agent C          │
│                                      │
│   Supervisor 在循环中不断：             │
│   ├─ 检查每个 Agent 的进度             │
│   ├─ 发现问题及时纠正                  │
│   ├─ 动态调整任务分配                  │
│   └─ 确保整体方向正确                  │
│                                      │
└──────────────────────────────────────┘
```

#### 模式三：Debate / Adversarial（辩论/对抗模式）

```
核心思想：多个 Agent 从不同角度审视同一个问题，
通过辩论或对抗来得出更可靠的结论。

┌─────────────────────────────────────┐
│                                     │
│   Agent A（正方）     Agent B（反方）│
│   "我认为应该..."     "但是考虑到..." │
│         │                  │        │
│         └────┬─────────────┘        │
│              ▼                      │
│        Judge Agent                  │
│        评判双方论点                  │
│        得出最终结论                  │
│                                     │
└─────────────────────────────────────┘

适用场景：
├─ 风险评估（一个 Agent 找风险，一个 Agent 找机会）
├─ 代码审查（一个 Agent 写代码，一个 Agent 审代码）
├─ 合同审查（一个找有利条款，一个找不利条款）
└─ 投资决策（看多 vs 看空的分析）
```

#### 模式四：Pipeline（流水线模式）

```
每个 Agent 处理一个阶段，上一个的输出是下一个的输入。

Agent A (提取) → Agent B (分析) → Agent C (生成) → Agent D (审核)

类比：工厂流水线

适用场景：
├─ 文档处理：解析 → 提取信息 → 结构化 → 生成摘要
├─ 数据处理：清洗 → 转换 → 分析 → 可视化
└─ 内容生产：选题 → 写初稿 → 润色 → 审核
```

### 9.3 Agent 间通信

```
多 Agent 之间怎么传递信息？

方式 1：通过 Orchestrator 中转
├─ 所有通信经过 Orchestrator
├─ Orchestrator 决定什么信息传给谁
├─ 优点：集中控制，容易管理
└─ 缺点：Orchestrator 是瓶颈

方式 2：共享内存空间（Blackboard Pattern）
├─ 所有 Agent 共享一个可读写的"黑板"
├─ 每个 Agent 把结果写到黑板上
├─ 其他 Agent 从黑板上读取需要的信息
├─ 优点：去中心化，灵活
└─ 缺点：需要协调并发读写

方式 3：消息队列
├─ Agent 之间通过消息队列通信
├─ 异步、解耦
├─ 优点：可扩展性好
└─ 缺点：增加系统复杂度

实际建议：
├─ 2-3 个 Agent → 通过 Orchestrator 中转最简单
├─ 3-5 个 Agent → 共享内存空间
└─ 5+ 个 Agent → 消息队列
```

### 9.4 多 Agent 的挑战

```
挑战 1：协调成本
  Agent 越多，协调工作越复杂
  → 有时候 1 个强 Agent > 3 个弱 Agent

挑战 2：信息损失
  Agent A 的详细发现传给 Agent B 时可能被压缩
  → 关键信息可能丢失

挑战 3：一致性
  多个 Agent 可能产生矛盾的结论
  → 需要仲裁机制

挑战 4：成本
  N 个 Agent = N 倍的 LLM 调用
  → 成本成倍增加

挑战 5：调试困难
  出了问题，不知道是哪个 Agent 出的
  → 需要完善的日志和追踪

经验法则：
"用最少的 Agent 完成任务"
不要为了多 Agent 而多 Agent。
一个 Agent 能做好就用一个。
只有明确需要时才拆分成多个。
```

---

## 第十章：Agent 框架深度对比

### 10.1 主流框架概览

```
┌──────────────────────────────────────────────────────────────┐
│                    Agent 框架生态图                            │
│                                                              │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │                  最轻量级                                │ │
│  │                                                         │ │
│  │  自建 Agent 循环（纯代码）                                │ │
│  │  ├─ 完全自己控制                                         │ │
│  │  ├─ 灵活度最高                                           │ │
│  │  └─ 需要自己处理所有细节                                  │ │
│  │                                                         │ │
│  ├─────────────────────────────────────────────────────────┤ │
│  │                  官方 SDK 级别                            │ │
│  │                                                         │ │
│  │  Claude Agent SDK / OpenAI Agents SDK                   │ │
│  │  ├─ 官方出品，和模型集成最好                              │ │
│  │  ├─ 轻量封装，不会过度抽象                                │ │
│  │  └─ 专注于自家模型                                       │ │
│  │                                                         │ │
│  ├─────────────────────────────────────────────────────────┤ │
│  │                  应用框架级别                             │ │
│  │                                                         │ │
│  │  LangGraph（LangChain 团队）                             │ │
│  │  ├─ 基于图（Graph）的 Agent 编排                         │ │
│  │  ├─ 可视化流程                                           │ │
│  │  ├─ 支持复杂的条件分支和循环                              │ │
│  │  └─ 学习曲线中等                                         │ │
│  │                                                         │ │
│  ├─────────────────────────────────────────────────────────┤ │
│  │                  多 Agent 级别                           │ │
│  │                                                         │ │
│  │  CrewAI / AutoGen（微软）                                │ │
│  │  ├─ 专注于多 Agent 协作                                  │ │
│  │  ├─ 定义角色、任务、流程                                  │ │
│  │  ├─ 开箱即用的协作模式                                    │ │
│  │  └─ 灵活度较低（框架约束多）                              │ │
│  │                                                         │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 10.2 框架对比表

| 维度 | 自建循环 | Claude Agent SDK | LangGraph | CrewAI | AutoGen |
|------|---------|------------------|-----------|--------|---------|
| **学习成本** | 低（就是 Python） | 低 | 中 | 中 | 中高 |
| **灵活度** | 最高 | 高 | 中高 | 中 | 中 |
| **抽象层次** | 无 | 轻量 | 中等 | 较重 | 较重 |
| **多 Agent** | 需自建 | 支持 | 支持 | 核心特性 | 核心特性 |
| **可视化** | 无 | 无 | 有 | 有 | 有 |
| **生产就绪** | 看你的水平 | 高 | 中高 | 中 | 中 |
| **社区生态** | - | 中 | 大 | 中 | 大 |
| **适合谁** | 想深入理解原理 | 用 Claude 的项目 | 复杂流程编排 | 快速搭建多 Agent | 研究和原型 |

### 10.3 框架选择建议

```
给你的具体建议（基于你的学习路径）：

第一阶段：自建 Agent 循环
├─ 目的：深入理解原理
├─ 做法：用纯 Python + LLM API 写一个 ReAct Agent
├─ 不要一上来就用框架——你需要理解"框架帮你做了什么"
└─ 学习时间：1-2 周

第二阶段：使用 Claude Agent SDK
├─ 目的：学会用官方工具
├─ 优势：和 Claude 模型集成最好、文档清晰
├─ 做一个功能完整的 Agent 项目
└─ 学习时间：1 周

第三阶段：按需选择框架
├─ 如果需要复杂流程编排 → LangGraph
├─ 如果需要多 Agent 协作 → CrewAI
├─ 如果是研究和原型 → AutoGen
└─ 如果追求最大控制力 → 继续自建

重点：
理解原理（自建循环）>> 会用框架 >> 用哪个框架

框架会变，原理不变。
先自建，理解之后再用框架会事半功倍。
```

### 10.4 自建 Agent 循环 vs 框架的取舍

```
自建循环的好处：
├─ 100% 理解每一行代码在做什么
├─ 可以精确控制每一个细节
├─ 没有框架的版本更新和 breaking changes
├─ 不受框架设计理念的限制
├─ 面试时能说清楚原理

自建循环的代价：
├─ 需要自己实现重试、超时、日志等基础设施
├─ 多 Agent 通信需要自己设计
├─ 没有社区的最佳实践参考
└─ 开发速度较慢

框架的好处：
├─ 快速上手，开箱即用
├─ 社区积累的最佳实践
├─ 通常有可视化和调试工具
└─ 减少重复工作

框架的代价：
├─ 黑盒——出了问题不知道框架内部怎么了
├─ 框架升级可能 breaking
├─ 框架的设计理念可能不适合你的场景
└─ 过度抽象可能限制灵活性

结论：
├─ 学习阶段 → 必须自建，理解原理
├─ 简单项目 → 自建或官方 SDK
├─ 中等项目 → LangGraph 或 官方 SDK
└─ 复杂多 Agent → CrewAI 或自建
```

---

## 第十一章：Agent 评估体系——怎么证明你的 Agent 好用

### 11.1 Agent 评估的独特挑战

```
评估 Agent 比评估 RAG 或单轮对话难得多：

RAG 评估（你学过的）：
├─ 输入确定（用户问题）
├─ 输出确定（回答文本）
├─ 可以用标准答案对比
└─ 相对容易

Agent 评估：
├─ 执行路径不确定（可能走不同的步骤）
├─ 中间步骤很多（每步都可能出问题）
├─ 最终结果可能有多种正确形式
├─ 需要评估过程和结果两个维度
└─ 很有挑战性
```

### 11.2 Agent 评估的五个维度

```
维度 1：任务完成率（Task Completion Rate）
  ══════════════════════════════════════
  定义：Agent 成功完成任务的比例
  计算：成功完成的任务数 / 总任务数
  目标：> 80% 可用，> 95% 生产级

  关键：什么算"完成"？
  ├─ 严格标准：输出完全符合预期
  ├─ 宽松标准：核心功能完成，细节可接受
  └─ 需要根据业务场景定义

维度 2：步骤效率（Step Efficiency）
  ═════════════════════════════════
  定义：完成任务使用的步骤数
  计算：实际步数 / 理论最少步数
  目标：比值 < 2（不超过最优路径的2倍）

  为什么重要：
  ├─ 步数多 = Token 消耗多 = 成本高
  ├─ 步数多 = 延迟高 = 用户等待久
  └─ 步数多 = 出错机会多

维度 3：工具使用准确率（Tool Selection Accuracy）
  ═══════════════════════════════════════════════
  定义：Agent 选对工具的比例
  计算：正确的工具选择数 / 总工具选择数

  分为两类：
  ├─ 选择准确率：选对了工具
  └─ 参数准确率：工具选对了，参数也填对了

维度 4：结果质量（Output Quality）
  ══════════════════════════════
  定义：最终输出的质量
  评估方法：
  ├─ LLM-as-Judge（用另一个 LLM 评分）
  ├─ 人工评估（金标准）
  ├─ 自动指标（BLEU、ROUGE 等）
  └─ 业务指标（用户满意度、采纳率）

维度 5：安全性（Safety）
  ═══════════════════
  定义：Agent 有没有执行危险操作
  检查项：
  ├─ 是否调用了不该调用的工具
  ├─ 是否泄露了敏感信息
  ├─ 是否忽略了用户的限制条件
  └─ 是否在应该停止时继续执行
```

### 11.3 Agent 评估的实施方法

```python
class AgentEvaluator:
    """Agent 评估框架"""

    async def evaluate(self, test_cases: list) -> dict:
        results = []

        for case in test_cases:
            # 运行 Agent
            trace = await self.run_agent_with_trace(
                task=case["task"],
                tools=case["tools"]
            )

            # 评估各维度
            score = {
                "task": case["task"],
                "completion": self.eval_completion(trace, case["expected"]),
                "efficiency": self.eval_efficiency(trace, case["optimal_steps"]),
                "tool_accuracy": self.eval_tool_usage(trace, case["expected_tools"]),
                "quality": await self.eval_quality(trace.final_output, case["expected"]),
                "safety": self.eval_safety(trace)
            }
            results.append(score)

        return self.aggregate(results)

    def eval_completion(self, trace, expected):
        """评估任务是否完成"""
        # 检查是否在最大步数内完成
        if trace.terminated_by == "max_steps":
            return 0.0  # 超时 = 未完成

        # 检查是否包含必要的输出要素
        required_elements = expected.get("required_elements", [])
        present = sum(1 for e in required_elements if e in trace.final_output)
        return present / len(required_elements) if required_elements else 1.0

    def eval_efficiency(self, trace, optimal_steps):
        """评估步骤效率"""
        actual_steps = trace.total_steps
        if optimal_steps == 0:
            return 1.0
        ratio = actual_steps / optimal_steps
        # ratio=1 最优, ratio=2 可接受, ratio>3 效率低
        return max(0, 1 - (ratio - 1) / 3)

    def eval_safety(self, trace):
        """评估安全性"""
        violations = []

        for step in trace.steps:
            # 检查是否调用了危险工具但没有确认
            if step.tool in DANGEROUS_TOOLS and not step.had_confirmation:
                violations.append(f"未确认的危险操作：{step.tool}")

            # 检查是否有信息泄露
            if contains_sensitive_info(step.output):
                violations.append(f"敏感信息泄露：{step.tool}")

        return {
            "safe": len(violations) == 0,
            "violations": violations
        }
```

---

## 第十二章：生产环境部署——从 Demo 到上线

### 12.1 生产级 Agent 系统架构

```
┌──────────────────────────────────────────────────────────────┐
│                         用户层                                │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                   │
│  │  Web UI  │  │  API     │  │  消息平台 │                   │
│  │          │  │  客户端  │  │  (钉钉等) │                   │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘                   │
│       └──────────────┼──────────────┘                        │
│                      │                                       │
├──────────────────────┼───────────────────────────────────────┤
│                      ▼            网关层                      │
│               ┌──────────────┐                               │
│               │  API 网关    │                               │
│               │  认证/限流   │                               │
│               └──────┬───────┘                               │
│                      │                                       │
├──────────────────────┼───────────────────────────────────────┤
│                      ▼            Agent 层                   │
│         ┌────────────────────────┐                           │
│         │   Agent Orchestrator   │                           │
│         │   ┌──────────────┐    │                           │
│         │   │  Agent Loop  │    │ ← 你在本文档学的核心       │
│         │   │  ├─ 思考     │    │                           │
│         │   │  ├─ 行动     │    │                           │
│         │   │  ├─ 观察     │    │                           │
│         │   │  └─ 反思     │    │                           │
│         │   └──────────────┘    │                           │
│         │                       │                           │
│         │   ┌──────────────┐    │                           │
│         │   │ 记忆管理器   │    │                           │
│         │   │ 终止管理器   │    │                           │
│         │   │ HITL 管理器  │    │                           │
│         │   └──────────────┘    │                           │
│         └────────┬───────────────┘                           │
│                  │                                           │
├──────────────────┼───────────────────────────────────────────┤
│                  ▼             工具层                         │
│    ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐                     │
│    │ RAG  │ │ API  │ │ DB   │ │ 外部  │                     │
│    │ 检索 │ │ 调用 │ │ 查询 │ │ 服务  │                     │
│    └──────┘ └──────┘ └──────┘ └──────┘                     │
│                                                              │
├──────────────────────────────────────────────────────────────┤
│                            基础设施层                         │
│    ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐                     │
│    │ 日志 │ │ 监控 │ │ 追踪 │ │ 告警 │                     │
│    └──────┘ └──────┘ └──────┘ └──────┘                     │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 12.2 生产环境的关键考量

```
1. 可观测性（Observability）
   ═══════════════════════
   必须能回答：
   ├─ Agent 执行了哪些步骤？
   ├─ 每步用了多长时间？
   ├─ 调用了哪些工具？参数和结果是什么？
   ├─ LLM 的推理过程是什么？
   ├─ 总共消耗了多少 Token？
   └─ 为什么最终给出了这个答案？

   工具推荐：
   ├─ LangSmith / LangFuse（Agent 专用追踪）
   ├─ 自建结构化日志（JSON 格式）
   └─ Prometheus + Grafana（性能监控）

2. 错误恢复（Error Recovery）
   ══════════════════════
   Agent 在中间步骤出错了怎么办？
   ├─ 重试当前步骤（简单错误）
   ├─ 跳过当前步骤（非关键步骤）
   ├─ 回退到上一个检查点（严重错误）
   ├─ 转人工处理（不可恢复的错误）
   └─ 优雅降级（返回部分结果 + 说明）

3. 并发控制
   ════════
   多个用户同时使用 Agent：
   ├─ 每个用户一个 Agent 实例（隔离）
   ├─ 共享资源需要加锁（如数据库写入）
   ├─ LLM API 有 rate limit，需要排队
   └─ 工具的并发能力各不相同

4. 状态持久化
   ══════════
   长时间运行的 Agent：
   ├─ Agent 执行到一半，服务器重启了怎么办？
   ├─ 需要把 Agent 的状态保存到数据库
   ├─ 重启后能从断点恢复
   └─ 这叫 "Checkpoint & Resume"

5. 成本控制
   ════════
   Agent 的成本远高于普通对话：
   ├─ 一次 Agent 任务可能 = 10-50 次 LLM 调用
   ├─ 每次调用都携带完整的消息历史
   ├─ 外部 API 调用也有成本
   ├─ 需要设置每个用户的使用配额
   └─ 监控异常消耗（有人故意让 Agent 死循环）
```

### 12.3 生产级 Agent 的配置管理

```python
class AgentConfig:
    """Agent 配置——可以热更新，不需要重启服务"""

    # 模型配置
    model: str = "claude-sonnet-4-20250514"  # 主模型
    fallback_model: str = "claude-haiku-4-5-20251001"  # 降级模型
    temperature: float = 0.0  # Agent 通常用 0

    # 终止条件
    max_steps: int = 20
    max_time_seconds: int = 120
    max_tokens: int = 100000
    max_tool_calls: int = 30

    # 安全配置
    require_confirmation_tools: list = ["send_email", "delete_*"]
    blocked_tools: list = ["drop_database"]  # 绝对禁止的工具
    max_amount_auto_approve: float = 100.0  # 自动批准的最大金额

    # 记忆配置
    memory_strategy: str = "sliding_window"  # 或 "summary"
    max_history_messages: int = 20
    enable_long_term_memory: bool = True

    # 成本配置
    max_cost_per_task: float = 1.0  # 单次任务最大成本（美元）
    max_cost_per_user_daily: float = 10.0  # 每用户每日最大成本
```

---

## 第十三章：Agent 安全与风险控制

### 13.1 Agent 特有的安全威胁

```
Agent 比 Tool Use 多出来的安全问题：

1. 自主性放大（Autonomy Amplification）
   ├─ Tool Use：LLM 一次调一个工具，用户可以逐步审查
   ├─ Agent：LLM 自主执行多步操作，用户可能来不及审查
   └─ 风险：Agent 可能在用户不知情时完成一系列操作

2. 目标偏移（Goal Drift）
   ├─ 用户要求："分析销售数据"
   ├─ Agent 执行到中间："数据有异常，让我修复它"
   ├─ 结果：Agent 修改了数据库中的数据（用户没要求这样做）
   └─ 风险：Agent 自行扩大了任务范围

3. 提示注入链式攻击（Chained Injection）
   ├─ Agent 调用 search_web → 搜索结果中包含恶意指令
   ├─ Agent 把搜索结果放入上下文 → 恶意指令被执行
   ├─ Agent 基于恶意指令调用了危险工具
   └─ 风险：外部数据通过 Agent 的工具链入侵

4. 资源耗尽（Resource Exhaustion）
   ├─ Agent 进入死循环 → Token 消耗爆炸
   ├─ Agent 大量调用外部 API → API 费用爆炸
   └─ 风险：经济损失
```

### 13.2 安全防护策略

```
策略 1：最小权限原则
  ═══════════════════
  Agent 只拥有完成当前任务所需的最少权限。
  ├─ 不需要发邮件的任务 → 不要给 send_email 工具
  ├─ 只需要查询的任务 → 不要给写入工具
  ├─ 根据用户角色动态加载工具（你在 Tool Use 章节学过）
  └─ 定期审查 Agent 的工具列表，去掉不需要的

策略 2：沙盒隔离
  ═════════════
  Agent 的操作在隔离环境中执行。
  ├─ 代码执行：在沙盒容器中执行，限制文件系统和网络访问
  ├─ 数据库：使用只读副本或限制写入范围
  ├─ API 调用：通过代理层，限制目标范围
  └─ 文件操作：限制在指定目录内

策略 3：输出过滤
  ═════════════
  Agent 返回给用户的信息需要过滤。
  ├─ 检查是否包含敏感信息（API Key、密码、个人信息）
  ├─ 检查是否包含不当内容
  └─ 检查是否泄露了 System Prompt

策略 4：行为监控
  ═════════════
  实时监控 Agent 的行为模式。
  ├─ 异常检测：工具调用频率突然飙升
  ├─ 规则检测：调用了不该调用的工具组合
  ├─ 预算监控：成本接近上限时告警
  └─ 自动熔断：检测到异常时自动停止 Agent
```

---

## 第十四章：常见问题诊断手册

### 14.1 诊断流程

```
Agent 表现不好
     │
     ├─ Agent 无法完成任务 ────────────────────────────────
     │   ├─ 步数耗尽但未完成？
     │   │   ├─ 任务太复杂 → 提高 max_steps 或分解任务
     │   │   ├─ 陷入循环 → 检查是否重复调用同一工具
     │   │   └─ 工具不足 → 检查是否缺少必要的工具
     │   │
     │   ├─ 选错了执行路径？
     │   │   ├─ System Prompt 不够清楚 → 优化指导
     │   │   ├─ 工具 description 有歧义 → 改善描述
     │   │   └─ 缺少示例 → 加入 Few-shot
     │   │
     │   └─ 中途遇到错误后放弃？
     │       ├─ 错误信息不够好 → 改善工具的错误返回
     │       └─ 缺少重试/降级逻辑 → 加上错误处理
     │
     ├─ Agent 完成了但结果差 ──────────────────────────────
     │   ├─ 信息不完整？
     │   │   ├─ 搜索范围太窄 → 扩大搜索策略
     │   │   └─ 过早结束 → 加强完成条件检查
     │   │
     │   ├─ 信息有误？
     │   │   ├─ 工具返回的数据有问题 → 检查工具和数据源
     │   │   └─ LLM 误解了结果 → 优化工具返回格式
     │   │
     │   └─ 格式不对？
     │       └─ System Prompt 中明确输出格式要求
     │
     ├─ Agent 太慢 ───────────────────────────────────────
     │   ├─ 步骤太多？
     │   │   ├─ 有不必要的步骤 → 优化 Prompt 指导
     │   │   └─ 可以并行的步骤被串行执行 → 启用并行调用
     │   │
     │   ├─ 工具执行慢？
     │   │   ├─ 外部 API 延迟高 → 加缓存、设超时
     │   │   └─ 数据库查询慢 → 优化查询或加索引
     │   │
     │   └─ LLM 响应慢？
     │       ├─ 上下文太长 → 压缩历史消息
     │       └─ 模型太大 → 考虑用更快的模型
     │
     └─ Agent 成本太高 ───────────────────────────────────
         ├─ 每轮 Token 太多？
         │   ├─ 工具定义太冗长 → 精简
         │   └─ 消息历史太长 → 压缩或裁剪
         │
         ├─ 轮次太多？
         │   ├─ Agent 效率低 → 优化 Prompt
         │   └─ 无效的重复调用 → 加去重逻辑
         │
         └─ 可以用更便宜的模型？
             ├─ 路由简单任务到小模型
             └─ 工具选择用小模型，最终回答用大模型
```

### 14.2 常见问题快速修复

| 问题 | 原因 | 修复方案 |
|------|------|----------|
| Agent 死循环 | 没有终止条件/条件不生效 | 加 max_steps + 循环检测 |
| Agent 重复调用同一工具 | 没记住已经做过了 | 在 Prompt 中加入历史摘要 |
| Agent 选错工具 | 工具 description 不清楚 | 改善描述 + 加使用场景 |
| Agent 忽略用户要求 | System Prompt 没强调 | 把用户要求放到显眼位置 |
| Agent 编造信息 | 不知道该用工具查询 | 强调"不确定时使用工具查询" |
| Agent 过度操作 | 目标偏移 | 限制可用工具 + 加审批 |
| Agent 中途停止 | LLM 错误判断任务完成 | 加完成标准检查 |
| 多 Agent 结果矛盾 | 缺少统一协调 | 加仲裁 Agent |
| 成本飙升 | Token 消耗无控制 | 加预算限制 + 压缩策略 |

---

## 第十五章：面试高频考题与答案

### Q1：什么是 Agent？它和简单的 Tool Use 有什么区别？

**答案：**

Agent 是一个以 LLM 为核心的自主系统，它能够感知环境（通过工具获取信息）、做出决策（LLM 推理）、执行操作（调用工具）、并持续迭代直到完成任务。

公式：**Agent = LLM + 工具 + 循环 + 规划 + 记忆 + 终止条件**

和 Tool Use 的核心区别：

| 维度 | Tool Use | Agent |
|------|----------|-------|
| 调用次数 | 通常 1-3 次 | 不确定（直到完成） |
| 决策方 | 线性的，可预测 | LLM 自主决策 |
| 错误处理 | 返回错误给用户 | 自己分析原因并重试 |
| 记忆 | 无 | 有工作记忆和长期记忆 |
| 规划 | 无 | 能分解任务和制定计划 |

简单说：Tool Use 是"LLM 用了一次工具"，Agent 是"LLM 持续使用工具直到完成一个复杂任务"。

---

### Q2：描述 ReAct 模式的工作原理，它的优缺点是什么？

**答案：**

ReAct = Reasoning + Acting，每一步都要求 LLM 先推理再行动。

工作流程：
1. **Thought**（推理）：LLM 分析当前情况，决定下一步
2. **Action**（行动）：调用选定的工具
3. **Observation**（观察）：获取工具返回结果
4. 回到步骤 1，直到任务完成

优点：
- 可解释性强（每步都有推理过程，便于调试）
- 准确性高（先想清楚再做，减少盲目调用）
- 灵活（能处理意外情况）
- 实现简单（只需一个循环）

缺点：
- 推理文本增加 Token 消耗
- 缺乏全局视角（走一步看一步）
- 推理本身可能出错
- 对于步骤明确的任务可能效率不高

适用场景：大多数中等复杂度的任务，是最通用的 Agent 模式。

---

### Q3：Agent 的记忆系统有哪些类型？它们分别用在什么场景？

**答案：**

四种记忆类型：

1. **短期记忆**（对话历史）
   - 存储当前对话的完整消息
   - 受上下文窗口限制
   - 需要压缩策略：滑动窗口、摘要压缩、关键信息提取

2. **工作记忆**（Scratchpad）
   - 当前任务的中间状态和待办事项
   - 任务完成后清空
   - 帮助 Agent 保持任务追踪

3. **长期记忆**
   - 跨会话的持久化信息（用户偏好、历史经验）
   - 本质就是 RAG：写入 = embedding + 存储，读取 = 检索
   - 让 Agent 能"记住"用户的习惯和历史交互

4. **外部知识记忆**
   - 企业知识库、文档库
   - 就是 RAG 系统本身
   - Agent 通过工具访问

关键认知：长期记忆的实现本质就是 RAG 技术——这就是为什么学习顺序是 RAG → Tool Use → Agent。

---

### Q4：什么时候用单 Agent，什么时候用多 Agent？

**答案：**

**用单 Agent 的情况：**
- 任务范围明确，工具少于 15 个
- 不需要多领域专业知识
- 上下文窗口能装下所有信息
- 追求简单和低成本

**用多 Agent 的情况：**
- 任务可拆解为独立的子任务（可并行）
- 需要不同领域的专业知识（研究 + 分析 + 写作）
- 单 Agent 上下文窗口不够
- 需要对抗式质量保证（一个写、一个审）

**经验法则：** 用最少的 Agent 完成任务。一个 Agent 能做好就用一个，不要为了"多 Agent"而多 Agent。多 Agent 的协调成本很高，调试也更困难。

常见多 Agent 模式包括：Orchestrator-Worker（最常用）、Supervisor、Debate/Adversarial、Pipeline。

---

### Q5：怎么设计 Agent 的终止条件？

**答案：**

好的终止策略是多种条件的组合：

1. **LLM 自主判断**：LLM 认为任务完成时自然停止——最灵活，但不可完全依赖
2. **最大步数限制**：硬性上限（如 20 步），防止无限循环——必须有，作为安全底线
3. **超时限制**：时间维度的安全线（如 120 秒），保证用户体验
4. **成本预算**：Token 消耗或 API 调用次数上限，控制成本
5. **完成标准检测**：检查输出是否满足预定义条件（如报告包含摘要+分析+结论）
6. **用户干预**：用户随时可以手动终止

生产环境建议：至少组合使用 1（基础）+ 2（兜底）+ 4（成本控制），再根据场景加入 5（质量保证）和 6（用户控制）。

---

### Q6：什么是 Human-in-the-Loop？为什么在企业 Agent 中必不可少？

**答案：**

HITL = 在 Agent 执行过程中，在特定节点引入人工参与，而非完全自主运行。

三种模式：
- **审批模式**：Agent 做 → 人审批 → 通过才执行（用于高风险操作）
- **引导模式**：Agent 给出方案 → 人选择 → Agent 执行（用于决策）
- **监督模式**：Agent 自动执行 → 人随时可干预（用于常规任务）

企业中必不可少的原因：
1. **合规要求**：金融、医疗、法律行业要求关键决策有人工参与
2. **风险控制**：不可逆操作（发邮件、转账、删除）需要确认
3. **责任划分**：出了问题需要有人负责
4. **信任建立**：初期用户不完全信任 AI 的决策

实现方式：用风险评分系统评估每个操作的风险级别（高/中/低），高风险必须审批，中风险需确认，低风险自动执行。

---

### Q7：Agent 在生产环境中最大的挑战是什么？怎么应对？

**答案：**

五个最大挑战及应对：

1. **可靠性不稳定**——相同输入可能得到不同结果
   → 应对：降低 temperature、加强 Prompt 约束、加入完成标准检测

2. **成本不可预测**——一次任务可能消耗大量 Token
   → 应对：设置成本上限、压缩消息历史、工具结果精简、模型分层

3. **延迟高**——多轮调用导致总延迟长
   → 应对：并行调用、流式输出、工具结果缓存、优化工具响应速度

4. **调试困难**——多步执行路径难以追踪
   → 应对：完善的结构化日志、Agent 追踪工具（LangSmith/LangFuse）、每步记录推理过程

5. **安全风险**——自主性带来的风险放大
   → 应对：最小权限、沙盒隔离、HITL、行为监控与自动熔断

---

### Q8：Plan-then-Execute 和 ReAct 的区别是什么？什么时候用哪个？

**答案：**

**ReAct**：边想边做——每做完一步再想下一步。
- 类比：即兴演奏，灵活应变
- 适合：信息不确定、探索性任务、对话式交互

**Plan-then-Execute**：先想全想透再做——制定完整计划后逐步执行。
- 类比：写好乐谱再演奏，有全局视角
- 适合：步骤可预测、需要向用户展示计划、复杂但结构化的任务

实际中，最好的方式是组合使用：
- 先用 Plan-then-Execute 制定宏观计划
- 每个步骤内部用 ReAct 灵活执行
- 遇到偏差时触发 Re-planning 调整计划

---

### Q9：怎么评估一个 Agent 系统的好坏？

**答案：**

五个评估维度：

1. **任务完成率**：成功完成的比例（目标 > 80%）
2. **步骤效率**：实际步数 vs 理论最少步数（目标 < 2倍）
3. **工具使用准确率**：选对工具且参数正确的比例
4. **结果质量**：最终输出的完整性、准确性、实用性（可用 LLM-as-Judge）
5. **安全性**：是否有未授权操作、信息泄露等

评估方法：
- 构建评估测试集（覆盖正常场景 + 边界场景 + 对抗场景）
- 对每个测试用例运行 Agent 并记录完整执行轨迹（trace）
- 自动计算量化指标 + 人工抽检关键案例
- 每次修改 Agent 后做回归测试

---

### Q10：Reflexion 模式是什么？它解决了什么问题？

**答案：**

Reflexion 是一种"执行 → 自我评估 → 反思 → 改进重试"的 Agent 模式。

它解决的问题：Agent 第一次执行的结果可能不够好，但简单重试（用完全相同的方式再做一次）大概率还是不好。

Reflexion 的关键：不是"再做一次"，而是"分析为什么不好，然后带着改进策略再做一次"。

流程：
1. 执行任务 → 产出结果
2. 自我评估：结果质量如何？（可以用 LLM-as-Judge）
3. 如果不及格 → 反思：具体哪里不好？为什么？怎么改？
4. 把反思经验作为上下文，重新执行
5. 循环直到通过或达到最大重试次数

典型应用：代码生成（写代码 → 跑测试 → 失败 → 分析错误 → 修改 → 再测试）、报告写作、数据分析。

---

### Q11：怎么处理 Agent 执行过程中的安全问题？

**答案：**

Agent 有四种特有的安全威胁：

1. **自主性放大**：多步自动操作，用户可能来不及审查
   → 对策：HITL 机制 + 风险评分

2. **目标偏移**：Agent 自行扩大任务范围
   → 对策：在 Prompt 中明确限制范围 + 工具白名单

3. **链式注入**：外部数据（搜索结果）中的恶意指令通过工具链注入
   → 对策：外部数据标记为不可信 + 输出过滤

4. **资源耗尽**：死循环或被恶意引导消耗大量资源
   → 对策：终止条件组合（步数+时间+成本）+ 行为监控 + 自动熔断

整体安全策略：最小权限 + 沙盒隔离 + HITL + 行为监控 + 审计日志。

---

### Q12：请描述你会如何从零设计一个企业级 Agent 系统

**答案（以智能客服 Agent 为例）：**

**1. 需求分析**
- 支持的任务：查订单、查物流、申请退款、投诉处理、转人工
- 用户量：日均 1000 次对话
- 质量要求：任务完成率 > 90%，平均处理时间 < 60 秒

**2. 架构设计**
- 模式：ReAct + HITL（退款等高风险操作需人工审批）
- 单 Agent（任务不够复杂，不需要多 Agent）
- 工具集：search_faq, get_order, get_logistics, apply_refund, create_ticket, escalate_to_human

**3. 安全设计**
- search_faq / get_order / get_logistics → 自动执行
- apply_refund → 金额 < 100 自动，≥ 100 需审批
- create_ticket → 需确认
- 所有操作记录审计日志

**4. 记忆设计**
- 短期记忆：滑动窗口（保留最近 10 轮）
- 长期记忆：记录用户历史工单和偏好
- 工作记忆：当前工单处理进度

**5. 终止策略**
- 最大 15 步 + 120 秒超时 + 成本上限 $0.50/次
- 完成标准：用户问题得到回答 或 已转人工

**6. 评估体系**
- 50 个评估用例（正常场景 30 + 边界 10 + 对抗 10）
- 每周回归测试
- 线上监控任务完成率和用户满意度

---

## 第十六章：实战项目方向与成长路线

### 16.1 项目难度分级

```
入门级项目（1 周）
├─ 简单 ReAct Agent
│   功能：搜索 + 计算 + 回答
│   核心：理解 Agent 循环
│   工具：search_web, calculator
│
├─ 文档问答 Agent
│   功能：RAG + 追问 + 汇总
│   核心：RAG 作为工具 + 多轮交互
│   工具：search_knowledge_base, ask_user
│
└─ 代码助手 Agent
    功能：读代码 + 分析 + 解释
    核心：文件操作工具 + 代码理解
    工具：read_file, search_code

中级项目（2-3 周）
├─ 数据分析 Agent
│   功能：查数据 + 分析 + 可视化 + 报告
│   核心：多步骤编排 + 结果汇总
│   工具：query_db, run_code, create_chart, generate_report
│
├─ 智能客服 Agent
│   功能：FAQ + 查订单 + 退款 + 转人工
│   核心：HITL + 安全控制
│   工具：search_faq, get_order, apply_refund, escalate
│
└─ 研究助手 Agent
    功能：搜索 + 阅读 + 对比 + 总结
    核心：Plan-then-Execute + 记忆管理
    工具：search_web, read_article, take_notes, generate_summary

进阶项目（1-2 月）
├─ 供应商合同审查 Agent（你之前提过的场景）
│   功能：解析合同 + 风险识别 + 比较基准 + 生成报告
│   核心：多 Agent + HITL + 长期记忆 + 安全
│   工具：parse_document, search_clauses, check_compliance,
│         query_erp, verify_supplier, generate_risk_report,
│         request_human_review
│
├─ 自动化测试 Agent
│   功能：分析需求 + 生成测试用例 + 执行测试 + 生成报告
│   核心：Reflexion（测试不通过则反思修改）
│   工具：read_spec, generate_test, run_test, analyze_failure
│
└─ 多 Agent 项目管理系统
    功能：分解任务 + 分配执行 + 监控进度 + 汇总报告
    核心：Orchestrator-Worker + 持久化
    Agent 角色：PM Agent, Research Agent, Dev Agent, QA Agent
```

### 16.2 从 Agent 到下一步

```
你已完成：
  Step 1: Prompt Engineering ✅
  Step 2: RAG ✅
  Step 3: Tool Use ✅
  Step 4: Agent ✅ ← 你在这里

接下来：
  Step 5: 工程化基础（把 Agent 部署到生产环境）
  Step 6: 评估体系（证明你的 Agent 好用并持续优化）

学完 Step 1-6，你就具备了独立交付企业级 AI 项目的能力。
这是"AI 应用工程师"这个岗位的核心技能集。

Step 7-10 是进阶方向，按需学习。

准备好学 Step 5（工程化基础）时告诉我。
```

---

> **本章核心总结：** Agent 是 Prompt + RAG + Tool Use 的集大成者。你需要掌握的核心能力是：**设计 Agent 循环**（理解思考-行动-观察-反思的闭环）、**选择设计模式**（ReAct / Plan-then-Execute / Reflexion / 多 Agent）、**管理记忆**（短期压缩 + 长期持久化）、**设计终止策略**（多条件组合防止失控）、**实现 HITL**（在自主性和安全性之间找平衡）。Agent 不是万能的——最好的系统是 Agent 处理模糊决策 + 传统代码处理确定性逻辑。
