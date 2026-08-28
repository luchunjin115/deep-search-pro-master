# AI 应用工程化基础完全知识体系

> AI 应用工程师学习路径 Step 5
> 前置知识：Prompt Engineering ✅、RAG ✅、Tool Use ✅、Agent ✅
> 学完本篇：你将能把"本地跑通的 Demo"变成"别人能用的产品"

---

## 目录（上篇）

- [第一章：为什么工程化是分水岭](#第一章为什么工程化是分水岭)
- [第二章：API 开发——让别人能调用你的 AI 能力](#第二章api-开发让别人能调用你的-ai-能力)
- [第三章：异步编程——AI 应用的必备技能](#第三章异步编程ai-应用的必备技能)
- [第四章：LLM API 调用最佳实践](#第四章llm-api-调用最佳实践)
- [第五章：流式输出——用户体验的关键](#第五章流式输出用户体验的关键)
- [第六章：Docker 容器化——一次打包到处运行](#第六章docker-容器化一次打包到处运行)
- [第七章：数据库基础——AI 应用的数据管理](#第七章数据库基础ai-应用的数据管理)

## 目录（下篇，等你指示后生成）

- 第八章：监控与可观测性——出了问题怎么发现
- 第九章：成本控制——不让老板破产
- 第十章：认证与安全——谁能用你的系统
- 第十一章：部署上线——从本地到云端
- 第十二章：CI/CD——自动化发布流程
- 第十三章：常见问题诊断手册
- 第十四章：面试高频考题与答案
- 第十五章：实战项目方向

---

## 第一章：为什么工程化是分水岭

### 1.1 用大白话说清楚

```
你现在的状态：
├─ 会写 Prompt ✅
├─ 会做 RAG ✅
├─ 会用 Tool Use ✅
├─ 会搭 Agent ✅
└─ 但是...

你做的所有东西都是在你自己电脑上跑的。

老板说："挺好，让全公司200人都用上。"
你的问题来了：
├─ 怎么让别人不装 Python 也能用？          → API 开发
├─ 200 人同时用会不会崩？                 → 异步 & 并发
├─ 用户等 30 秒才出结果会不会骂人？        → 流式输出
├─ 你的电脑关了别人就用不了了？            → 部署上线
├─ 怎么知道系统有没有出问题？             → 监控
├─ 一个月 API 费用 10 万老板会不会杀了你？ → 成本控制
├─ 怎么防止外面的人乱用你的接口？          → 认证安全
└─ 每次改代码都要手动重启服务器？          → CI/CD

这些就是"工程化"要解决的问题。
```

### 1.2 工程化在整个学习体系中的位置

```
打个比方：

Step 1-4 你学会了"做菜"（技术能力）
  ├─ Prompt = 知道怎么调味
  ├─ RAG = 知道去哪找食材
  ├─ Tool Use = 会用各种厨具
  └─ Agent = 能做一桌菜

Step 5 你要学"开餐厅"（工程能力）
  ├─ API = 菜单（客人怎么点菜）
  ├─ 异步 = 多个灶台同时炒菜（不是一个一个来）
  ├─ Docker = 标准化厨房（换个地方也能开）
  ├─ 部署 = 选店面开张
  ├─ 监控 = 装摄像头看厨房有没有着火
  ├─ 成本 = 算账，别亏本
  └─ 安全 = 门锁，别让闲人进厨房

会做菜不等于会开餐厅。
很多人卡在这一步——技术能力有了，但做不出产品。
```

### 1.3 本章你需要掌握的核心技术栈

```
必须掌握（面试必考 + 工作必用）：
├─ FastAPI（Python Web 框架）
├─ 异步编程（async/await）
├─ 流式输出（SSE / WebSocket）
├─ Docker（容器化）
├─ 基本的数据库操作
├─ LLM API 调用最佳实践（重试、超时、降级）
└─ 基本的日志和监控

了解即可（知道概念，用到再深入）：
├─ Kubernetes（容器编排）
├─ CI/CD（自动化部署）
├─ 云服务（AWS / 阿里云）
├─ 消息队列（Redis / RabbitMQ）
└─ 负载均衡
```

---

## 第二章：API 开发——让别人能调用你的 AI 能力

### 2.1 是什么：API 到底是什么

```
大白话解释：

API = Application Programming Interface = 应用程序编程接口

太抽象了？换个说法：

API 就是"菜单"。

你去餐厅吃饭：
├─ 你不需要知道后厨怎么炒菜（内部实现）
├─ 你只需要看菜单点菜（发请求）
├─ 服务员把菜端上来（返回结果）
└─ 菜单就是"接口"

你的 AI 系统也一样：
├─ 前端/其他系统不需要知道你怎么调 LLM、怎么做 RAG
├─ 它们只需要调你的 API："请帮我分析这份合同"
├─ 你的 API 返回分析结果
└─ API 就是你的 AI 能力对外暴露的"菜单"

更技术地说：
API 是一组定义好的 URL 地址（端点），
别人向这些地址发送 HTTP 请求，你的服务处理后返回结果。
```

### 2.2 为什么用 FastAPI

```
Python 的 Web 框架有很多，为什么 AI 应用推荐 FastAPI？

对比表：

框架        速度     异步支持    类型检查   自动文档   学习曲线   AI适合度
─────────────────────────────────────────────────────────────────
Flask       中       需插件     无         无         低         ⭐⭐
Django      中       有限       有限       需插件     高         ⭐
FastAPI     快       原生       原生       自动生成   中         ⭐⭐⭐⭐⭐
Tornado     快       原生       无         无         中高       ⭐⭐

为什么 FastAPI 最适合 AI 应用？

1. 原生异步支持（async/await）
   AI 应用需要等 LLM 返回，异步能同时处理多个请求
   → Flask 做不到（或很麻烦）

2. 原生支持流式输出（SSE）
   LLM 逐字输出需要流式响应
   → FastAPI 天然支持 StreamingResponse

3. 自动生成 API 文档
   写好代码 → 自动有一个可交互的 API 文档页面
   → 前端/测试人员直接看文档就能对接

4. 类型检查（Pydantic）
   请求参数自动校验，写错了立刻报错
   → 减少 Bug

5. 性能好
   基于 Starlette，性能是 Flask 的 2-3 倍
```

### 2.3 怎么用：FastAPI 从零开始

```python
# ═══════════════════════════════════════════
# 最简单的 FastAPI 应用——Hello World
# ═══════════════════════════════════════════

# 安装：pip install fastapi uvicorn

from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def hello():
    return {"message": "Hello, World!"}

# 运行：uvicorn main:app --reload
# 然后打开浏览器访问 http://localhost:8000
# 自动生成的文档：http://localhost:8000/docs
```

```python
# ═══════════════════════════════════════════
# 一个真实的 AI 应用 API
# ═══════════════════════════════════════════

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import anthropic

app = FastAPI(title="AI 问答服务", version="1.0.0")
client = anthropic.Anthropic()

# ---- 定义请求和响应的数据结构 ----

class ChatRequest(BaseModel):
    """用户发来的请求长什么样"""
    message: str                    # 用户的问题（必填）
    model: str = "claude-sonnet-4-20250514"  # 模型（选填，有默认值）
    max_tokens: int = 1024          # 最大输出长度（选填）

class ChatResponse(BaseModel):
    """返回给用户的响应长什么样"""
    answer: str                     # AI 的回答
    model: str                      # 使用的模型
    tokens_used: int                # 消耗的 Token 数


# ---- 定义 API 端点 ----

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    AI 对话接口

    发送一个问题，获取 AI 的回答。
    """
    try:
        response = client.messages.create(
            model=request.model,
            max_tokens=request.max_tokens,
            messages=[
                {"role": "user", "content": request.message}
            ]
        )

        return ChatResponse(
            answer=response.content[0].text,
            model=request.model,
            tokens_used=response.usage.input_tokens + response.usage.output_tokens
        )

    except anthropic.APIError as e:
        raise HTTPException(status_code=502, detail=f"LLM 服务异常：{str(e)}")


@app.get("/health")
async def health_check():
    """健康检查接口——用来确认服务是否正常运行"""
    return {"status": "healthy"}
```

```
上面的代码做了什么？

1. ChatRequest 定义了"用户能发什么过来"
   就像菜单上写清楚了每道菜需要什么配料

2. ChatResponse 定义了"你会返回什么"
   就像告诉客人每道菜包含什么

3. @app.post("/chat") 定义了一个 API 端点
   就像菜单上的一道菜

4. /health 是健康检查
   就像餐厅门口的"营业中"牌子
   监控系统定期访问这个接口，确认你的服务还活着

用户怎么调用？
  POST http://你的服务器:8000/chat
  Body: {"message": "什么是RAG？"}

  返回：
  {
    "answer": "RAG是检索增强生成...",
    "model": "claude-sonnet-4-20250514",
    "tokens_used": 350
  }
```

### 2.4 API 设计的核心原则（面试重点）

```
原则 1：RESTful 设计
═══════════════════

是什么：一套设计 API URL 的约定俗成的规范。

大白话：就是给你的 API 地址起名字的规矩。

规则：
├─ 用名词不用动词：
│   ✅ GET /users        （获取用户列表）
│   ✅ POST /users       （创建用户）
│   ❌ GET /getUsers     （名字里有动词，不好）
│   ❌ POST /createUser  （名字里有动词，不好）
│
├─ 用 HTTP 方法表示操作：
│   GET    = 查询（只读，不会改变数据）
│   POST   = 创建（新增数据）
│   PUT    = 全量更新（替换整个资源）
│   PATCH  = 部分更新（只改某些字段）
│   DELETE = 删除
│
└─ 用 HTTP 状态码表示结果：
    200 = 成功
    201 = 创建成功
    400 = 你的请求有问题（参数错了）
    401 = 没有登录/没有权限
    404 = 你要的东西不存在
    500 = 服务器内部出错了

为什么这样做：
├─ 全世界的开发者都遵循这个规范
├─ 前端看到 GET /users 就知道是查用户，不需要看文档
└─ 面试时这是基础中的基础


原则 2：版本控制
═══════════════

是什么：在 API 地址里加版本号。

├─ ✅ /api/v1/chat    （第一版）
├─ ✅ /api/v2/chat    （第二版，可能参数不同）
└─ 这样老版本和新版本可以同时存在

为什么：
├─ 你改了 API 的参数格式
├─ 已经有 100 个客户端在用旧格式
├─ 如果直接改 → 100 个客户端全部报错
├─ 有版本号 → 新客户端用 v2，旧客户端继续用 v1
└─ 慢慢迁移，不会炸


原则 3：统一的响应格式
═══════════════════════

是什么：所有 API 返回的 JSON 格式保持一致。

✅ 好的做法（统一格式）：
{
    "code": 200,
    "message": "success",
    "data": {
        "answer": "RAG是...",
        "tokens_used": 350
    }
}

❌ 差的做法（每个接口格式不同）：
接口A：{"answer": "..."}
接口B：{"result": "...", "status": "ok"}
接口C：{"data": {"response": "..."}}

为什么：
├─ 前端只需要写一套解析逻辑
├─ 错误处理也是统一的
└─ 维护成本低
```

### 2.5 遇到问题怎么解决

```
常见问题 1：启动报错 "Address already in use"
├─ 原因：端口 8000 被别的程序占了
├─ 解决：换个端口 uvicorn main:app --port 8001
└─ 或者找到占端口的程序杀掉

常见问题 2：跨域错误（CORS）
├─ 现象：前端调你的 API 报错，浏览器拦截了
├─ 原因：浏览器安全策略，不允许不同域名之间互相调用
├─ 解决：
│   from fastapi.middleware.cors import CORSMiddleware
│   app.add_middleware(
│       CORSMiddleware,
│       allow_origins=["*"],  # 生产环境改成具体域名
│       allow_methods=["*"],
│       allow_headers=["*"],
│   )

常见问题 3：大文件上传超时
├─ 原因：默认请求体大小有限制
├─ 解决：调整 max_request_size 配置

常见问题 4：返回中文乱码
├─ 原因：编码问题
├─ 解决：FastAPI 默认用 UTF-8，一般没问题
│   如果有问题检查 ensure_ascii=False
```

---

## 第三章：异步编程——AI 应用的必备技能

### 3.1 是什么：用大白话解释异步

```
想象你在奶茶店点单：

同步（一次只做一件事）：
  顾客A 点单 → 做奶茶（3分钟）→ 给A → 
  顾客B 点单 → 做奶茶（3分钟）→ 给B →
  顾客C 点单 → ...

  3个顾客要等 9 分钟。
  顾客C 内心：我排队等了 6 分钟！！！

异步（同时做多件事）：
  顾客A 点单 → 开始做A的奶茶
  顾客B 点单 → 开始做B的奶茶（A的还在做）
  顾客C 点单 → 开始做C的奶茶（A和B的还在做）
  A做好了 → 给A
  B做好了 → 给B
  C做好了 → 给C

  3个顾客只等了约 3 分钟。
  顾客C 内心：不错嘛。

AI 应用中的"做奶茶" = 等 LLM API 返回结果。
调用一次 LLM 通常要等 2-10 秒。

如果用同步：100 个用户同时问问题，第 100 个人要等 200-1000 秒。
如果用异步：100 个用户同时问问题，大家都只等 2-10 秒。
```

### 3.2 为什么 AI 应用必须用异步

```
AI 应用的特点：大量的"等待"时间。

一次 AI 请求的时间分布：

你的代码处理请求          ←  0.001 秒（几乎不花时间）
等待 LLM API 返回         ←  2-10 秒（大部分时间在等）
你的代码处理响应          ←  0.001 秒

问题：在"等 LLM 返回"的 2-10 秒里，你的程序在干什么？

同步程序：呆坐着等，什么都不干。其他用户排队等着。
异步程序：趁这个空闲去处理其他用户的请求。

这就是为什么 AI 应用天然适合异步——
90% 以上的时间都在"等"，不是在"算"。
在等的时候可以去处理别的请求。
```

### 3.3 怎么用：Python 异步编程

```python
# ═══════════════════════════════════════════
# 同步 vs 异步 对比
# ═══════════════════════════════════════════

# --- 同步版本（慢）---
import time

def make_tea_sync(name):
    print(f"开始做{name}的奶茶")
    time.sleep(3)  # 模拟做奶茶要3秒
    print(f"{name}的奶茶做好了")
    return f"{name}的奶茶"

# 同步执行：依次做，总共 9 秒
make_tea_sync("顾客A")  # 等3秒
make_tea_sync("顾客B")  # 又等3秒
make_tea_sync("顾客C")  # 再等3秒


# --- 异步版本（快）---
import asyncio

async def make_tea_async(name):
    print(f"开始做{name}的奶茶")
    await asyncio.sleep(3)  # 异步等待，让出控制权给其他任务
    print(f"{name}的奶茶做好了")
    return f"{name}的奶茶"

# 异步执行：同时做，总共约 3 秒
async def main():
    results = await asyncio.gather(
        make_tea_async("顾客A"),
        make_tea_async("顾客B"),
        make_tea_async("顾客C"),
    )

asyncio.run(main())
```

```python
# ═══════════════════════════════════════════
# 在 AI 应用中使用异步
# ═══════════════════════════════════════════

import anthropic

# --- 同步调用 LLM（每次只能处理一个请求）---
def chat_sync(message: str) -> str:
    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        messages=[{"role": "user", "content": message}]
    )
    return response.content[0].text


# --- 异步调用 LLM（能同时处理多个请求）---
async def chat_async(message: str) -> str:
    client = anthropic.AsyncAnthropic()  # 注意：用 AsyncAnthropic
    response = await client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        messages=[{"role": "user", "content": message}]
    )
    return response.content[0].text


# --- 在 FastAPI 中使用异步 ---
from fastapi import FastAPI

app = FastAPI()

@app.post("/chat")
async def chat_endpoint(message: str):  # 注意前面的 async
    result = await chat_async(message)  # 注意前面的 await
    return {"answer": result}
```

### 3.4 异步的三个关键词（面试必问）

```
async / await / asyncio —— 三个词搞懂异步

1. async def
   在函数前面加 async，表示"这个函数是异步的"。
   异步函数不会立刻执行，而是返回一个"协程对象"。

   async def fetch_data():
       ...

2. await
   在异步函数内部调用另一个异步操作时，前面加 await。
   意思是"等这个操作完成，但等的时候让别人先用"。

   result = await some_async_function()

   大白话：
   "我在等 LLM 返回结果。
   但我不是傻等——在等的时候其他请求可以先处理。
   LLM 返回了我再回来继续。"

3. asyncio.gather()
   同时启动多个异步任务，等它们全部完成。

   results = await asyncio.gather(
       task_a(),
       task_b(),
       task_c()
   )

   大白话：
   "同时做三件事，全做完了再往下走。"


常见误区：
├─ ❌ 在同步函数里用 await → 会报错
├─ ❌ 在 async 函数里用 time.sleep() → 会阻塞！不是真异步
│   应该用 await asyncio.sleep()
├─ ❌ 忘记写 await → 函数不会被执行，拿到的是协程对象
└─ ✅ async 函数里调另一个 async 函数 → 前面必须加 await
```

### 3.5 遇到问题怎么解决

```
问题 1：RuntimeWarning: coroutine 'xxx' was never awaited
├─ 原因：调用了 async 函数但忘了加 await
├─ 解决：在调用前加 await
│   ❌ chat_async("hello")
│   ✅ await chat_async("hello")

问题 2：在同步代码中无法调用异步函数
├─ 原因：await 只能在 async 函数内使用
├─ 解决：用 asyncio.run() 包裹
│   result = asyncio.run(chat_async("hello"))

问题 3：异步代码反而变慢了
├─ 原因：可能用了同步的库（比如 requests 而不是 httpx）
├─ 同步库会阻塞整个事件循环，让异步失去意义
├─ 解决：用异步版本的库
│   requests（同步）→ httpx 或 aiohttp（异步）
│   anthropic.Anthropic（同步）→ anthropic.AsyncAnthropic（异步）

问题 4：数据库操作也需要异步吗？
├─ 如果数据库查询很快（<10ms）→ 影响不大
├─ 如果数据库查询慢或者并发高 → 建议用异步
├─ 异步数据库库：asyncpg（PostgreSQL）、motor（MongoDB）
```

---

## 第四章：LLM API 调用最佳实践

### 4.1 为什么需要"最佳实践"

```
直接调 LLM API 的问题：

你写的代码：
  response = client.messages.create(...)
  return response

看起来没问题？以下情况你考虑过吗？

1. LLM API 超时了（网络抖动、服务器忙）→ 你的用户看到 500 错误
2. LLM API 返回 429（调用太频繁被限流）→ 你的用户看到"服务不可用"
3. LLM 服务宕机了 → 你的整个服务也跟着瘫痪
4. 一个用户疯狂调用 → 把你的 API 额度用完了 → 其他用户全部受影响
5. 相同的问题反复问 → 每次都花钱调 API → 浪费钱

生产环境 ≠ 本地开发。
本地你可以容忍报错，生产环境不行。
```

### 4.2 重试策略（Retry）——最重要的实践

```
是什么：
API 调用失败时，自动重新尝试，而不是直接报错。

为什么：
LLM API 偶尔会因为网络抖动、服务器过载等原因失败。
大多数情况下，等一会儿再试就好了。

怎么用：
```

```python
import time
import anthropic

def call_llm_with_retry(
    messages: list,
    max_retries: int = 3,
    base_delay: float = 1.0
) -> str:
    """带重试的 LLM 调用"""

    for attempt in range(max_retries + 1):
        try:
            client = anthropic.Anthropic()
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1024,
                messages=messages
            )
            return response.content[0].text

        except anthropic.RateLimitError:
            # 429 被限流 → 等久一点再试
            if attempt < max_retries:
                delay = base_delay * (2 ** attempt)  # 指数退避
                print(f"被限流，等待 {delay} 秒后重试...")
                time.sleep(delay)
            else:
                raise

        except anthropic.APIConnectionError:
            # 网络错误 → 等一下再试
            if attempt < max_retries:
                delay = base_delay * (2 ** attempt)
                print(f"网络错误，等待 {delay} 秒后重试...")
                time.sleep(delay)
            else:
                raise

        except anthropic.APIStatusError as e:
            if e.status_code >= 500:
                # 5xx 服务器错误 → 可以重试
                if attempt < max_retries:
                    delay = base_delay * (2 ** attempt)
                    time.sleep(delay)
                else:
                    raise
            else:
                # 4xx 客户端错误（比如参数错了）→ 不要重试，直接报错
                raise

    raise Exception("重试次数用完，调用失败")
```

```
核心概念：指数退避（Exponential Backoff）

大白话：每次重试等的时间翻倍。

第 1 次重试：等 1 秒
第 2 次重试：等 2 秒
第 3 次重试：等 4 秒

为什么不是每次都等 1 秒？
├─ 如果服务器过载了，100 个客户端都等 1 秒后同时重试
├─ 服务器又被打爆了
├─ 然后又一起等 1 秒重试...无限循环
├─ 指数退避让不同客户端在不同时间重试
└─ 减少对服务器的压力

哪些错误应该重试？
├─ 429（限流）→ ✅ 重试
├─ 500/502/503（服务器错误）→ ✅ 重试
├─ 网络超时/连接失败 → ✅ 重试
├─ 400（参数错误）→ ❌ 不重试（你的参数有问题，重试也没用）
├─ 401（认证失败）→ ❌ 不重试（API Key 有问题）
└─ 404 → ❌ 不重试
```

### 4.3 超时控制（Timeout）

```
是什么：
设定一个最长等待时间，超过就放弃，不要无限等下去。

为什么：
LLM 生成长内容时可能要 30 秒甚至更久。
如果不设超时，用户可能等到地老天荒。

怎么用：
```

```python
# Anthropic SDK 内置超时设置
client = anthropic.Anthropic(
    timeout=30.0  # 最多等 30 秒
)

# 或者单次调用设置超时
response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=1024,
    messages=[...],
    timeout=20.0  # 这次请求最多等 20 秒
)
```

```
超时设多少合适？

场景              建议超时      原因
────────────────────────────────────────
简单问答          10-15 秒      输出不长
长文本生成        30-60 秒      输出可能很长
Agent 调用        60-120 秒     多轮工具调用
流式输出          首 token 5 秒  用户感知的是"第一个字什么时候出来"

重要：超时不等于失败！
超时后你应该：
├─ 重试（如果有重试逻辑）
├─ 或者告诉用户"处理中，请稍后查看"
├─ 或者用更快的模型重新处理
└─ 不要直接返回一个冷冰冰的错误页面
```

### 4.4 模型降级（Fallback）——面试高频

```
是什么：
主模型不可用时，自动切换到备用模型。

大白话：
主厨生病了，副厨顶上。菜可能没那么精致，但至少有饭吃。

为什么：
├─ 任何 API 都不是 100% 可用的
├─ Claude 宕机了 → 你的整个服务不能也跟着宕
├─ 用备用模型（哪怕质量差一点）→ 至少能用
└─ "能用但质量稍差" >> "完全不能用"

怎么用：
```

```python
# 模型降级链
MODEL_FALLBACK_CHAIN = [
    {"model": "claude-sonnet-4-20250514", "provider": "anthropic"},   # 首选
    {"model": "claude-haiku-4-5-20251001", "provider": "anthropic"},  # 备选1：更快更便宜
    {"model": "gpt-4o-mini", "provider": "openai"},                  # 备选2：换厂商
]

async def call_with_fallback(messages: list) -> dict:
    """带降级的 LLM 调用"""

    for i, config in enumerate(MODEL_FALLBACK_CHAIN):
        try:
            result = await call_llm(
                model=config["model"],
                provider=config["provider"],
                messages=messages
            )
            if i > 0:
                # 如果用了备用模型，记录下来
                result["fallback_used"] = True
                result["original_model"] = MODEL_FALLBACK_CHAIN[0]["model"]
                result["actual_model"] = config["model"]
            return result

        except Exception as e:
            if i < len(MODEL_FALLBACK_CHAIN) - 1:
                print(f"模型 {config['model']} 失败，切换到下一个")
                continue
            else:
                raise Exception("所有模型都不可用") from e
```

```
模型降级的决策：

什么时候降级？
├─ API 返回 5xx 错误（服务器故障）
├─ API 超时
├─ API 返回 429 且重试也失败
└─ 不要因为 400 错误降级（那是你的参数有问题）

降级时要注意什么？
├─ 告诉用户"当前使用备用模型，质量可能略有下降"
├─ 记录日志，方便排查
├─ 监控降级频率（频繁降级说明主模型有问题）
└─ 降级模型的 Prompt 可能需要调整（不同模型能力不同）
```

### 4.5 Prompt Caching（提示缓存）——省钱利器

```
是什么：
把重复使用的 Prompt 内容缓存起来，下次调用时不用重新处理。

大白话：
你每次给 LLM 发消息都要带上 System Prompt（可能有 2000 tokens）。
100 次调用 = 重复发送 100 次相同的 System Prompt = 白花钱。
Prompt Caching 让 LLM 记住这些重复内容，只收一次钱。

为什么：
├─ 节省费用（缓存命中的 token 便宜 90%）
├─ 降低延迟（不需要重新处理缓存部分）
└─ 在 Agent 场景特别有用（每轮都重复发送 System Prompt + 工具定义）

怎么用（Claude 的 Prompt Caching）：
```

```python
response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=1024,
    system=[
        {
            "type": "text",
            "text": "你是一个专业的合同审查助手...(很长的 System Prompt)",
            "cache_control": {"type": "ephemeral"}  # 标记为可缓存
        }
    ],
    messages=[
        {"role": "user", "content": "请分析这份合同的风险"}
    ]
)

# 查看缓存效果
print(f"缓存命中 tokens: {response.usage.cache_read_input_tokens}")
print(f"新写入缓存 tokens: {response.usage.cache_creation_input_tokens}")
```

```
Prompt Caching 的效果：

假设你的 System Prompt = 2000 tokens
每天调用 1000 次

没有缓存：
  2000 × 1000 = 2,000,000 input tokens/天
  费用 ≈ $6/天

有缓存：
  第 1 次：2000 tokens（写入缓存，价格正常）
  后 999 次：2000 × 999 = 1,998,000 tokens（缓存命中，价格打1折）
  费用 ≈ $0.6/天

省了 90%！
```

### 4.6 批处理（Batch API）

```
是什么：
把多个请求打包一起发送，而不是一个一个发。

大白话：
寄快递时，寄 100 个包裹可以叫一辆货车，而不是叫 100 辆出租车。

什么时候用：
├─ 不需要实时响应的场景
├─ 比如：批量处理 1000 份文档的摘要
├─ 比如：每天晚上批量分析当天的客服对话
├─ 比如：一次性评估 100 条测试用例

好处：
├─ 费用通常打 5 折
├─ 不受实时 rate limit 限制
└─ 系统负载更均匀

坏处：
├─ 不是实时的，通常几小时才返回结果
└─ 不适合用户等着要答案的场景
```

---

## 第五章：流式输出——用户体验的关键

### 5.1 是什么：为什么 ChatGPT 是一个字一个字蹦出来的

```
大白话解释：

你有没有注意到？
ChatGPT 的回答是一个字一个字出来的，而不是等全部写完才显示。

为什么这样？

非流式（普通方式）：
  用户提问 → 等 5 秒 → 突然出现一大段完整回答
  用户感受："卡了 5 秒，以为坏了"

流式（边生成边返回）：
  用户提问 → 0.3 秒后开始一个字一个字出现 → 5 秒后写完
  用户感受："秒回！它正在思考和打字"

技术上：
  LLM 本来就是一个字一个字生成的（自回归生成）。
  非流式是"等它全部写完再一起发给你"。
  流式是"它每写一个字就发给你一个字"。

  总时间其实一样！但用户感受完全不同。
  这就是"首字延迟 (Time to First Token, TTFT)"的价值。
```

### 5.2 为什么必须做流式

```
对比数据：

场景：用户问了一个需要 1000 tokens 回答的问题

非流式：
├─ 用户等待时间：8 秒（0 输出）
├─ 然后瞬间出现全部内容
├─ 用户感知延迟：8 秒
└─ 用户体验：差（"是不是卡了？"）

流式：
├─ 用户等待时间：0.3 秒后开始出字
├─ 然后一个一个字出现，持续 8 秒
├─ 用户感知延迟：0.3 秒
└─ 用户体验：好（"它在回答了！"）

面试重点：
面试官问"怎么优化 AI 应用的用户体验"
首选答案就是"流式输出"。
这是投入最小、效果最明显的优化。
```

### 5.3 怎么用：两种流式技术

```
技术 1：SSE（Server-Sent Events）
══════════════════════════════════

是什么：服务器主动向客户端推送数据的技术。
大白话：服务器不断地往客户端"扔"数据，客户端接住就行。

特点：
├─ 单向的：只有服务器→客户端（客户端不能往回发）
├─ 基于 HTTP：不需要特殊协议
├─ 简单：实现容易
├─ 自动重连：断了会自动尝试重新连接
└─ 最适合 LLM 流式输出！

技术 2：WebSocket
══════════════════

是什么：双向实时通信协议。
大白话：服务器和客户端之间开了一条"电话线"，双方都能随时说话。

特点：
├─ 双向的：服务器和客户端都能主动发消息
├─ 需要专门的协议（ws://）
├─ 比 SSE 复杂
├─ 适合：实时对话、多人协作
└─ 杀鸡用牛刀——LLM 输出用 SSE 就够了

选择建议：
├─ LLM 回答的流式输出 → 用 SSE（简单够用）
├─ 实时对话（用户可以中途打断）→ 用 WebSocket
└─ 不确定 → 先用 SSE
```

### 5.4 SSE 流式输出的实现（面试重点）

```python
# ═══════════════════════════════════════════
# FastAPI + Claude 流式输出
# ═══════════════════════════════════════════

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
import anthropic
import json

app = FastAPI()

async def generate_stream(message: str):
    """生成器函数——每拿到一段文字就 yield 出去"""

    client = anthropic.Anthropic()

    # 注意 stream=True
    with client.messages.stream(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        messages=[{"role": "user", "content": message}]
    ) as stream:
        for text in stream.text_stream:
            # SSE 格式：data: {JSON}\n\n
            yield f"data: {json.dumps({'text': text}, ensure_ascii=False)}\n\n"

    # 发送结束信号
    yield f"data: {json.dumps({'text': '', 'done': True})}\n\n"


@app.post("/chat/stream")
async def chat_stream(message: str):
    """流式聊天接口"""
    return StreamingResponse(
        generate_stream(message),
        media_type="text/event-stream"  # 告诉客户端这是 SSE
    )
```

```
上面的代码在做什么？

1. client.messages.stream() 
   告诉 Claude："别等写完，边写边发给我"

2. for text in stream.text_stream
   每拿到一小段文字，就执行一次循环

3. yield f"data: ..."
   把这一小段文字"推"给客户端
   yield 是 Python 生成器的关键词，意思是"产出一个值然后暂停"

4. StreamingResponse
   FastAPI 的流式响应，把 yield 的内容一个一个发给客户端

5. media_type="text/event-stream"
   告诉浏览器/客户端"这是 SSE 流式数据"

前端怎么接收？

// JavaScript
const eventSource = new EventSource('/chat/stream?message=你好');

eventSource.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.done) {
        eventSource.close();
        return;
    }
    // 把每个字追加到页面上
    document.getElementById('answer').textContent += data.text;
};
```

---

## 第六章：Docker 容器化——一次打包到处运行

### 6.1 是什么：用大白话解释 Docker

```
你有没有遇到过这种情况？

"在我电脑上明明能跑啊！"

为什么你的代码在你电脑上能跑，换一台电脑就不行？
├─ 你装了 Python 3.11，别人是 3.9
├─ 你装了某个库的特定版本，别人没装
├─ 你的操作系统是 Windows，服务器是 Linux
├─ 你设了某些环境变量，别人没设
└─ 总之：环境不一致

Docker 解决什么问题？

Docker 就像一个"集装箱"：
├─ 你把你的代码 + Python + 所有依赖库 + 配置 → 全部打包进一个箱子
├─ 这个箱子可以搬到任何地方运行
├─ 箱子里面的环境是完全一样的
├─ 不管外面是 Windows/Mac/Linux → 箱子里面都一样
└─ 再也不会出现"在我电脑上能跑"的问题

术语对照：
├─ 镜像（Image）= 集装箱的设计图
│   包含了运行你的应用需要的一切：代码、依赖、配置
├─ 容器（Container）= 根据设计图造出来的实际集装箱
│   是镜像的运行实例，可以启动、停止、删除
├─ Dockerfile = 设计图的说明书
│   告诉 Docker 怎么构建这个镜像
└─ Docker Hub = 集装箱仓库
    存放和分享镜像的地方
```

### 6.2 为什么 AI 应用需要 Docker

```
AI 应用对 Docker 的需求比普通应用更强：

1. 依赖多且版本敏感
   AI 应用通常依赖几十个库（anthropic, langchain, numpy, pandas...）
   版本不对就报错
   Docker 冻结了所有依赖版本

2. 部署到服务器
   你开发在 Windows/Mac，服务器是 Linux
   Docker 消除了这个差异

3. 可复制
   老板说"给测试环境也部署一套"
   用 Docker：一行命令搞定
   没有 Docker：又要装 Python、又要装库、又要配环境变量...

4. 扩缩容
   用户突然变多了？启动更多容器就行
   用户变少了？关掉一些容器
   像水龙头一样灵活
```

### 6.3 怎么用：Docker 从零开始

```dockerfile
# ═══════════════════════════════════════════
# Dockerfile —— 你的 AI 应用的"设计图"
# ═══════════════════════════════════════════

# 第 1 步：选一个基础环境（就像选毛坯房）
FROM python:3.11-slim

# 第 2 步：设定工作目录（在容器里创建一个文件夹）
WORKDIR /app

# 第 3 步：先复制依赖文件，安装依赖
# 为什么先复制 requirements.txt 而不是所有文件？
# 因为依赖不经常变，这样 Docker 可以缓存这一步，加快构建速度
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 第 4 步：复制你的代码
COPY . .

# 第 5 步：告诉 Docker 你的应用用哪个端口
EXPOSE 8000

# 第 6 步：启动命令
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```
# ═══════════════════════════════════════════
# 常用 Docker 命令（你需要记住的）
# ═══════════════════════════════════════════

# 构建镜像（根据 Dockerfile 生成镜像）
docker build -t my-ai-app .
# -t my-ai-app 是给镜像起个名字
# . 表示 Dockerfile 在当前目录

# 运行容器（根据镜像启动容器）
docker run -p 8000:8000 -e ANTHROPIC_API_KEY=你的key my-ai-app
# -p 8000:8000 把容器的 8000 端口映射到你电脑的 8000 端口
# -e 设置环境变量（API Key 不能写死在代码里！）

# 后台运行
docker run -d -p 8000:8000 my-ai-app
# -d 表示在后台运行（detach）

# 查看运行中的容器
docker ps

# 查看日志
docker logs 容器ID

# 停止容器
docker stop 容器ID

# 删除容器
docker rm 容器ID
```

### 6.4 Docker Compose——一键启动多个服务

```
实际的 AI 应用通常不只一个服务：

你的应用 = AI 服务 + 数据库 + Redis缓存 + 向量数据库

一个一个启动太麻烦。
Docker Compose 让你一条命令启动所有服务。
```

```yaml
# docker-compose.yml

version: '3.8'

services:
  # 你的 AI 服务
  ai-app:
    build: .
    ports:
      - "8000:8000"
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - DATABASE_URL=postgresql://user:pass@postgres:5432/mydb
      - REDIS_URL=redis://redis:6379
    depends_on:
      - postgres
      - redis

  # PostgreSQL 数据库
  postgres:
    image: postgres:15
    environment:
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=pass
      - POSTGRES_DB=mydb
    volumes:
      - pgdata:/var/lib/postgresql/data

  # Redis 缓存
  redis:
    image: redis:7-alpine

  # Qdrant 向量数据库
  qdrant:
    image: qdrant/qdrant
    ports:
      - "6333:6333"

volumes:
  pgdata:
```

```
# 一条命令启动所有服务
docker-compose up -d

# 一条命令停止所有服务
docker-compose down

# 查看所有服务的日志
docker-compose logs -f

就这么简单！
四个服务（AI应用 + 数据库 + 缓存 + 向量库）一条命令全部启动。
```

### 6.5 遇到问题怎么解决

```
问题 1：构建镜像时下载依赖很慢
├─ 原因：pip 默认从国外下载
├─ 解决：在 Dockerfile 中换国内镜像源
│   RUN pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

问题 2：镜像太大（好几个 GB）
├─ 原因：基础镜像太大 + 没有清理缓存
├─ 解决：
│   ├─ 用 slim 版本：python:3.11-slim（而不是 python:3.11）
│   ├─ 加 --no-cache-dir：pip install --no-cache-dir
│   └─ 用多阶段构建（进阶技巧）

问题 3：容器里连不上数据库
├─ 原因：容器之间的网络隔离
├─ 解决：
│   ├─ 用 docker-compose（同一个 compose 内的服务可以互相访问）
│   ├─ 数据库地址用服务名而不是 localhost
│   │   ❌ postgresql://user:pass@localhost:5432
│   │   ✅ postgresql://user:pass@postgres:5432
│   └─ postgres 是 docker-compose 中定义的服务名

问题 4：容器重启后数据丢了
├─ 原因：容器是临时的，重启后内部数据会清空
├─ 解决：用 volumes 持久化数据
│   就是上面 docker-compose 中的 volumes 配置
│   把数据库的数据存到容器外面的磁盘上
```

---

## 第七章：数据库基础——AI 应用的数据管理

### 7.1 AI 应用需要存什么数据

```
你可能会想：AI 应用不就是调 LLM API 吗，要什么数据库？

实际上，一个生产级 AI 应用需要存很多东西：

1. 对话历史
   ├─ 用户和 AI 的聊天记录
   ├─ 用户下次来可以继续之前的对话
   └─ 存在哪：关系型数据库（PostgreSQL）

2. 用户信息
   ├─ 用户账号、权限、配置偏好
   └─ 存在哪：关系型数据库

3. 向量数据
   ├─ RAG 用的文档向量
   ├─ 长期记忆的向量
   └─ 存在哪：向量数据库（Qdrant/Milvus）← 你学 RAG 时学过

4. 缓存
   ├─ 相同问题的答案缓存
   ├─ 用户 Session 信息
   └─ 存在哪：Redis

5. 文件
   ├─ 用户上传的文档（PDF、Word）
   ├─ 生成的报告
   └─ 存在哪：文件存储（S3 / 本地磁盘）

6. 日志和审计
   ├─ 每次 LLM 调用的记录
   ├─ Agent 的执行轨迹
   ├─ Token 消耗统计
   └─ 存在哪：日志系统 或 关系型数据库
```

### 7.2 关系型数据库（PostgreSQL）——面试必知

```
是什么：
按照"表格"来组织数据的数据库。
就像 Excel 表格，有行有列。

为什么用 PostgreSQL：
├─ 免费开源
├─ 功能强大且稳定
├─ 有 pgvector 插件 → 一个数据库同时当关系型 + 向量数据库
├─ 行业标准，面试必会
└─ 生态好，各种工具都支持

AI 应用中最常用的表结构：
```

```sql
-- 用户表
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    api_key_hash VARCHAR(256),
    daily_token_limit INT DEFAULT 100000,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 对话表
CREATE TABLE conversations (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(id),
    title VARCHAR(200),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 消息表
CREATE TABLE messages (
    id SERIAL PRIMARY KEY,
    conversation_id INT REFERENCES conversations(id),
    role VARCHAR(20) NOT NULL,          -- 'user' 或 'assistant'
    content TEXT NOT NULL,
    tokens_used INT,
    model VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Token 使用记录表（用于成本控制）
CREATE TABLE token_usage (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(id),
    model VARCHAR(50),
    input_tokens INT,
    output_tokens INT,
    cost_usd DECIMAL(10, 6),
    created_at TIMESTAMP DEFAULT NOW()
);
```

### 7.3 怎么在 FastAPI 中用数据库

```python
# ═══════════════════════════════════════════
# 方式 1：用 SQLAlchemy（最常用的 Python ORM）
# ═══════════════════════════════════════════

# ORM 是什么？
# 大白话：让你用 Python 代码操作数据库，而不是写 SQL 语句。
# 就像翻译官——你说中文（Python），它翻译成英文（SQL）。

# 安装：pip install sqlalchemy asyncpg

from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from datetime import datetime

# 定义数据模型
class Base(DeclarativeBase):
    pass

class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    title = Column(String(200))
    created_at = Column(DateTime, default=datetime.utcnow)

class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)
    conversation_id = Column(Integer, nullable=False)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    tokens_used = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)


# 在 FastAPI 中使用
from fastapi import FastAPI, Depends
from sqlalchemy.ext.asyncio import async_sessionmaker

DATABASE_URL = "postgresql+asyncpg://user:pass@localhost:5432/mydb"
engine = create_async_engine(DATABASE_URL)
async_session = async_sessionmaker(engine)

app = FastAPI()

async def get_db():
    async with async_session() as session:
        yield session

@app.post("/conversations")
async def create_conversation(
    user_id: int,
    title: str,
    db: AsyncSession = Depends(get_db)
):
    conv = Conversation(user_id=user_id, title=title)
    db.add(conv)
    await db.commit()
    return {"id": conv.id, "title": conv.title}
```

### 7.4 Redis 缓存——让系统更快更省钱

```
是什么：
一个把数据存在内存里的数据库，速度极快。
读写速度是普通数据库的 100 倍以上。

大白话：
普通数据库像图书馆——去书架找书，要走路要翻。
Redis 像你桌上的便签——一伸手就拿到。

AI 应用中怎么用 Redis：

用途 1：缓存 LLM 的回答
├─ 相同（或相似）的问题，直接返回缓存的答案
├─ 不需要再调 LLM API
├─ 省钱 + 快
│
│  示例：
│  用户A 问："什么是 RAG？" → 调 LLM → 得到答案 → 存入 Redis
│  用户B 问："什么是 RAG？" → 从 Redis 取 → 直接返回 → 不调 LLM
│  省了一次 API 调用！

用途 2：限流计数
├─ 每个用户今天调用了多少次？
├─ Redis 的计数器非常快
└─ 超过限制就拒绝

用途 3：Session 存储
├─ 用户的登录状态
├─ 对话的临时上下文
└─ 需要快速读写的临时数据
```

```python
# Redis 在 AI 应用中的使用示例

import redis
import hashlib
import json

r = redis.Redis(host='localhost', port=6379, decode_responses=True)

def get_cached_response(message: str, ttl: int = 3600) -> str | None:
    """尝试从缓存获取回答"""
    cache_key = f"chat:{hashlib.md5(message.encode()).hexdigest()}"
    cached = r.get(cache_key)
    if cached:
        return json.loads(cached)
    return None

def set_cached_response(message: str, response: str, ttl: int = 3600):
    """把回答存入缓存"""
    cache_key = f"chat:{hashlib.md5(message.encode()).hexdigest()}"
    r.setex(cache_key, ttl, json.dumps(response, ensure_ascii=False))
    # setex = set with expiration，ttl 秒后自动删除

# 在 API 中使用
@app.post("/chat")
async def chat(message: str):
    # 先查缓存
    cached = get_cached_response(message)
    if cached:
        return {"answer": cached, "from_cache": True}

    # 缓存没有，调 LLM
    answer = await call_llm(message)

    # 存入缓存
    set_cached_response(message, answer)

    return {"answer": answer, "from_cache": False}
```

```
Redis 缓存的注意事项：

1. 设置过期时间（TTL）
   ├─ 天气数据：缓存 15 分钟（数据会变）
   ├─ 知识性问答：缓存 24 小时（不太会变）
   ├─ 实时数据（股票）：不缓存或缓存 1 分钟
   └─ 不设过期时间 → 内存会被撑爆

2. 缓存命中率
   ├─ 如果大家问的问题都不一样 → 缓存命中率低 → 效果差
   ├─ 如果有很多重复问题（FAQ 场景）→ 缓存命中率高 → 效果好
   └─ 监控命中率，低于 20% 可能不值得用缓存

3. 缓存一致性
   ├─ 知识库更新了，缓存的旧答案还在
   ├─ 解决：知识库更新时清空相关缓存
   └─ 或者设置较短的 TTL
```

---

---

## 第八章：监控与可观测性——出了问题怎么发现

### 8.1 是什么：为什么需要监控

```
大白话解释：

你开了一家餐厅（AI 系统上线了）。

没有监控的餐厅：
├─ 厨房着火了 → 不知道 → 客人闻到烟味跑了
├─ 菜做咸了 → 不知道 → 客人投诉才发现
├─ 服务员偷懒 → 不知道 → 生意越来越差
└─ 等出了大问题才知道，已经晚了

有监控的餐厅：
├─ 厨房有烟感器 → 刚冒烟就报警 → 赶紧灭火
├─ 有试菜环节 → 每道菜上桌前检查
├─ 有工作日志 → 每个人做了什么一清二楚
└─ 问题在早期就被发现和解决

对应到 AI 系统：
├─ "厨房着火" = API 报错、LLM 服务宕机
├─ "菜做咸了" = AI 回答质量下降
├─ "服务员偷懒" = 响应时间变长
├─ "烟感器" = 监控告警系统
└─ "工作日志" = 日志系统
```

### 8.2 AI 应用需要监控什么（面试重点）

```
四类核心指标：

第 1 类：可用性指标——"系统还活着吗？"
══════════════════════════════════════
├─ API 成功率（目标：> 99.9%）
├─ 错误率（4xx / 5xx 比例）
├─ 健康检查状态（/health 是否返回 200）
└─ 上游依赖状态（LLM API、数据库、Redis 是否正常）

第 2 类：性能指标——"系统快不快？"
══════════════════════════════════
├─ 响应时间（P50 / P95 / P99）
│   P50 = 50% 的请求在这个时间内完成
│   P95 = 95% 的请求在这个时间内完成
│   P99 = 99% 的请求在这个时间内完成
│
│   大白话：
│   P50 是"大多数情况"
│   P95 是"比较慢的情况"
│   P99 是"最慢的情况"
│   面试常考：通常关注 P95，而不是平均值
│   因为平均值会掩盖少数特别慢的请求
│
├─ TTFT（首字延迟）—— 流式输出第一个字出来的时间
├─ 吞吐量（QPS/RPM）—— 每秒/每分钟处理多少请求
└─ 并发数 —— 同时在处理多少个请求

第 3 类：业务指标——"系统好不好用？"
══════════════════════════════════════
├─ Token 消耗（每天 / 每用户 / 每请求）
├─ API 调用费用（每天花多少钱）
├─ 模型降级频率（多久用一次备用模型）
├─ 缓存命中率（多少请求命中了缓存）
├─ Agent 完成率（Agent 任务成功完成的比例）
└─ 用户满意度（如果有反馈功能）

第 4 类：安全指标——"有没有人搞破坏？"
══════════════════════════════════════
├─ 异常请求检测（频率异常、内容异常）
├─ 认证失败次数
├─ 限流触发次数
└─ 敏感信息泄露检测
```

### 8.3 日志系统——最基础最重要的监控手段

```
是什么：
把系统运行过程中的关键信息记录下来。

大白话：
就像写日记。
出了问题翻日记就能知道"那天发生了什么"。

AI 应用的日志应该记什么：
```

```python
import logging
import json
from datetime import datetime

# 配置结构化日志（JSON 格式）
# 为什么用 JSON？因为方便机器解析和搜索

class AILogger:
    def __init__(self):
        self.logger = logging.getLogger("ai_app")
        self.logger.setLevel(logging.INFO)

    def log_request(self, request_id: str, user_id: str,
                    message: str, model: str):
        """记录每次请求"""
        self.logger.info(json.dumps({
            "event": "request_received",
            "request_id": request_id,
            "user_id": user_id,
            "message_length": len(message),
            # 注意：不要记录用户的完整消息！可能包含隐私
            "model": model,
            "timestamp": datetime.utcnow().isoformat()
        }))

    def log_llm_call(self, request_id: str, model: str,
                     input_tokens: int, output_tokens: int,
                     latency_ms: float, success: bool):
        """记录每次 LLM 调用"""
        self.logger.info(json.dumps({
            "event": "llm_call",
            "request_id": request_id,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "latency_ms": latency_ms,
            "success": success,
            "cost_usd": self.calculate_cost(model, input_tokens, output_tokens),
            "timestamp": datetime.utcnow().isoformat()
        }))

    def log_error(self, request_id: str, error_type: str,
                  error_message: str):
        """记录错误"""
        self.logger.error(json.dumps({
            "event": "error",
            "request_id": request_id,
            "error_type": error_type,
            "error_message": error_message,
            "timestamp": datetime.utcnow().isoformat()
        }))

    def log_tool_call(self, request_id: str, tool_name: str,
                      success: bool, latency_ms: float):
        """记录 Agent 的工具调用"""
        self.logger.info(json.dumps({
            "event": "tool_call",
            "request_id": request_id,
            "tool_name": tool_name,
            "success": success,
            "latency_ms": latency_ms,
            "timestamp": datetime.utcnow().isoformat()
        }))
```

```
日志的关键原则：

1. 用 request_id 串联一次请求的所有日志
   ├─ 用户请求进来 → 生成一个唯一 ID
   ├─ 这次请求的所有日志都带上这个 ID
   ├─ 出了问题 → 用 ID 搜索 → 一次请求的完整过程一目了然
   └─ 这叫"链路追踪"

2. 不要记录敏感信息
   ├─ ❌ 记录用户的完整对话内容
   ├─ ❌ 记录 API Key
   ├─ ❌ 记录用户密码
   ├─ ✅ 记录消息长度（message_length）而不是内容
   └─ ✅ 如果必须记录内容，做脱敏处理

3. 日志分级
   ├─ DEBUG：开发调试用，生产环境不开
   ├─ INFO：正常运行记录（请求来了、处理完了）
   ├─ WARNING：值得注意但不影响功能（降级了、重试了）
   ├─ ERROR：出错了但系统还能运行（某次请求失败）
   └─ CRITICAL：系统级故障（数据库连不上、内存不够）
```

### 8.4 告警系统——主动通知你出了问题

```
有了监控数据，还需要"告警"——主动通知你。

不然监控数据只是放在那里，没人看就没用。

什么时候应该告警：

紧急告警（立刻通知，打电话/短信）：
├─ API 错误率 > 5%（持续 5 分钟）
├─ 所有 LLM API 都不可用
├─ 数据库连不上
└─ 服务器 CPU/内存 > 95%

重要告警（发消息到钉钉/飞书/邮件）：
├─ API 错误率 > 1%（持续 10 分钟）
├─ P95 响应时间 > 10 秒
├─ 模型降级频率 > 10%
├─ 某个用户的 Token 消耗异常高
└─ 日费用超过预算的 80%

信息通知（日报/周报）：
├─ 每日 Token 消耗统计
├─ 缓存命中率变化趋势
├─ 用户量变化趋势
└─ 错误类型分布
```

### 8.5 AI 应用专用的追踪工具

```
通用的监控工具（Prometheus + Grafana）：
├─ 适合：监控系统层面的指标（CPU、内存、请求量）
└─ 不适合：追踪 LLM 的具体调用过程

AI 应用专用的追踪工具：
├─ LangSmith（LangChain 团队出品）
│   ├─ 记录每次 LLM 调用的完整过程
│   ├─ 可视化 Agent 的执行步骤
│   ├─ 支持评估和对比
│   └─ 和 LangChain 生态集成好
│
├─ LangFuse（开源替代品）
│   ├─ 功能类似 LangSmith
│   ├─ 可以自己部署（数据不出企业）
│   └─ 适合对数据安全要求高的企业
│
└─ 自建追踪系统
    ├─ 用结构化日志 + 数据库
    ├─ 灵活度最高
    └─ 工作量最大

建议：
├─ 学习阶段 → 用 LangSmith（免费额度够用）
├─ 企业项目 → 用 LangFuse 自部署 或 自建
└─ 不管用什么，追踪能力是生产级 AI 应用必须有的
```

---

## 第九章：成本控制——不让老板破产

### 9.1 AI 应用的成本构成

```
大白话：AI 应用花钱的地方比你想象的多。

成本构成：

1. LLM API 费用（最大头）
   ├─ 按 Token 计费
   ├─ Input tokens（你发给 LLM 的）
   ├─ Output tokens（LLM 回给你的，通常更贵）
   ├─ 不同模型价格差异巨大
   │   Claude Haiku: $0.25 / 百万 input tokens
   │   Claude Sonnet: $3 / 百万 input tokens
   │   Claude Opus:  $15 / 百万 input tokens
   │   → Opus 比 Haiku 贵 60 倍！
   └─ Agent 调用多轮 → 费用倍增

2. 基础设施费用
   ├─ 服务器（云服务器 / 自建服务器）
   ├─ 数据库
   ├─ 向量数据库
   ├─ Redis
   └─ 带宽

3. 外部 API 费用
   ├─ 搜索 API（Google、Bing）
   ├─ 其他第三方 API
   └─ 地图、天气等服务

4. 人力成本
   ├─ 运维
   ├─ 数据标注
   └─ 知识库维护

实际案例：
一个中等规模的 AI 客服系统
├─ 日均 5000 次对话
├─ 每次对话约 3000 tokens
├─ 用 Claude Sonnet
├─ 月 LLM 费用 ≈ $1350
├─ 基础设施 ≈ $200/月
└─ 总计 ≈ $1550/月 ≈ ¥11000/月
```

### 9.2 八大成本优化策略

```
策略 1：模型分层（最有效的策略）
═══════════════════════════════

是什么：不同复杂度的任务用不同价格的模型。

大白话：
不是所有菜都要米其林大厨来做。
炒个青菜让学徒来就行，做满汉全席才请大厨。

怎么做：
├─ 简单任务（分类、提取、格式化）→ Haiku（便宜）
├─ 中等任务（问答、总结、翻译）→ Sonnet（性价比）
├─ 复杂任务（推理、分析、创作）→ Opus（最强但最贵）
└─ 意图识别 → 用 Haiku 判断任务复杂度 → 路由到对应模型

省多少钱？
用 Haiku 处理 60% 的简单任务 → 这部分省 90% 以上


策略 2：缓存（第七章已讲）
═══════════════════════
重复问题直接返回缓存 → 不调 LLM → 0 成本
FAQ 场景缓存命中率可达 30-50% → 省 30-50% 的费用


策略 3：Prompt 精简
═══════════════════
├─ System Prompt 越短 → input tokens 越少 → 越便宜
├─ 去掉不必要的示例
├─ 压缩工具定义的 description
├─ 但不能影响效果！精简不等于删到看不懂
└─ 每省 500 tokens × 10000 次调用 = 省 500 万 tokens


策略 4：Prompt Caching（第四章已讲）
═══════════════════════════════════
缓存命中的 tokens 只收 1/10 的价格


策略 5：限制输出长度
═══════════════════
├─ 设合理的 max_tokens
├─ 不需要 4000 字回答的场景就设 500
├─ 在 Prompt 中要求"简洁回答"
└─ output tokens 通常比 input tokens 贵


策略 6：消息历史压缩（Agent 章节已讲）
════════════════════════════════════
├─ Agent 每轮都发完整历史 → tokens 越来越多
├─ 压缩早期消息为摘要 → 大幅减少 input tokens
└─ 滑动窗口 → 只保留最近 N 轮


策略 7：批处理替代实时处理
════════════════════════
├─ 不需要实时的任务 → 攒一批一起处理
├─ Batch API 通常半价
└─ 比如：每天晚上批量处理当天的数据


策略 8：用户配额限制
═══════════════════
├─ 每个用户每天最多 N 次调用
├─ 每个用户每天最多 N tokens
├─ 超过限制 → 提示升级或次日重置
└─ 防止个别用户消耗过多资源
```

### 9.3 成本监控代码实现

```python
class CostTracker:
    """成本追踪器"""

    # 价格表（每百万 tokens，美元）
    PRICING = {
        "claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0},
        "claude-haiku-4-5-20251001": {"input": 0.25, "output": 1.25},
        "claude-opus-4-20250514": {"input": 15.0, "output": 75.0},
    }

    def calculate_cost(self, model: str,
                       input_tokens: int, output_tokens: int) -> float:
        """计算单次调用费用"""
        pricing = self.PRICING.get(model, self.PRICING["claude-sonnet-4-20250514"])
        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]
        return round(input_cost + output_cost, 6)

    async def check_budget(self, user_id: str) -> bool:
        """检查用户是否还有预算"""
        today_cost = await self.get_today_cost(user_id)
        daily_limit = await self.get_user_limit(user_id)
        return today_cost < daily_limit

    async def record_usage(self, user_id: str, model: str,
                           input_tokens: int, output_tokens: int):
        """记录使用量"""
        cost = self.calculate_cost(model, input_tokens, output_tokens)
        await db.insert("token_usage", {
            "user_id": user_id,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": cost,
        })

        # 检查是否接近预算上限
        today_cost = await self.get_today_cost(user_id)
        daily_limit = await self.get_user_limit(user_id)
        if today_cost > daily_limit * 0.8:
            await self.send_alert(
                f"用户 {user_id} 今日消耗已达预算的 "
                f"{today_cost/daily_limit*100:.0f}%"
            )
```

---

## 第十章：认证与安全——谁能用你的系统

### 10.1 为什么需要认证

```
大白话：
你做了一个 AI 服务，API 地址是 http://你的服务器:8000/chat

如果不做认证：
├─ 任何人都可以调用你的 API
├─ 有人写个脚本疯狂调用 → API 费用爆炸
├─ 竞争对手白嫖你的服务
├─ 恶意用户发送不当内容
└─ 老板：你被开除了

所以必须知道"谁在调用"并且"控制谁能调用"。
```

### 10.2 三种常用认证方式

```
方式 1：API Key（最简单最常用）
══════════════════════════════

是什么：给每个用户一个唯一的密钥字符串。
大白话：就像门禁卡，每人一张，刷卡才能进。

怎么用：
用户在请求头里带上 API Key：
  Authorization: Bearer sk-xxxxxxxxxxxx

服务端检查这个 Key 是否有效。

优点：简单、容易实现
缺点：Key 泄露了别人就能冒充你
适用：B2B 场景（给其他系统提供 API）
```

```python
# FastAPI 中实现 API Key 认证

from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

app = FastAPI()
security = HTTPBearer()

# 实际中从数据库查，这里简化
VALID_API_KEYS = {
    "sk-abc123": {"user_id": "user_1", "daily_limit": 1000},
    "sk-def456": {"user_id": "user_2", "daily_limit": 500},
}

async def verify_api_key(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    """验证 API Key"""
    api_key = credentials.credentials
    user_info = VALID_API_KEYS.get(api_key)

    if not user_info:
        raise HTTPException(status_code=401, detail="无效的 API Key")

    return user_info

@app.post("/chat")
async def chat(
    message: str,
    user: dict = Depends(verify_api_key)  # 自动验证
):
    # 到这里说明 API Key 验证通过了
    # user 包含用户信息
    return {"answer": "...", "user_id": user["user_id"]}
```

```
方式 2：JWT（JSON Web Token）
════════════════════════════

是什么：一种包含用户信息的加密令牌。
大白话：像身份证——上面写了你是谁，有防伪标记。

和 API Key 的区别：
├─ API Key：只是一串随机字符，服务端要查数据库才知道是谁
├─ JWT：令牌本身就包含了用户信息，不需要查数据库

适用：有用户登录系统的 Web 应用


方式 3：OAuth 2.0
═════════════════

是什么：让用户用第三方账号（微信、Google）登录。
大白话：像"微信扫码登录"。

适用：面向普通用户的 C 端应用

对于 AI 应用：
├─ 后端 API 服务 → 用 API Key 最合适
├─ 有前端登录界面 → 用 JWT
├─ 面向普通用户 → 用 OAuth
└─ 初学者先掌握 API Key，够用了
```

### 10.3 限流（Rate Limiting）——面试重点

```
是什么：
限制每个用户的调用频率。

为什么：
├─ 防止恶意用户刷你的 API（DDoS 攻击）
├─ 防止某个用户占用太多资源（影响其他用户）
├─ 控制 LLM API 成本（你的 API Key 也有限额）
└─ 保护系统稳定性

常见的限流策略：
├─ 每分钟最多 N 次请求（RPM）
├─ 每天最多 N 次请求
├─ 每天最多消耗 N tokens
└─ 不同等级的用户有不同的限额
```

```python
# 用 Redis 实现限流

import redis
from fastapi import HTTPException

r = redis.Redis()

async def rate_limit(user_id: str, max_rpm: int = 10):
    """每分钟最多 max_rpm 次请求"""
    key = f"rate_limit:{user_id}:{int(time.time()) // 60}"
    current = r.incr(key)

    if current == 1:
        r.expire(key, 60)  # 60 秒后自动删除

    if current > max_rpm:
        raise HTTPException(
            status_code=429,
            detail=f"请求过于频繁，每分钟最多 {max_rpm} 次"
        )

# 在 API 中使用
@app.post("/chat")
async def chat(message: str, user: dict = Depends(verify_api_key)):
    await rate_limit(user["user_id"], max_rpm=10)
    # ... 正常处理
```

### 10.4 环境变量管理——API Key 的正确姿势

```
最重要的安全原则：
永远不要把 API Key 写在代码里！

❌ 绝对不要这样做：
client = anthropic.Anthropic(api_key="sk-ant-xxxxx")

为什么？
├─ 代码提交到 Git → Key 泄露
├─ 别人看到你的代码 → Key 泄露
├─ 代码被反编译 → Key 泄露
└─ Key 被盗用 → 你的钱被别人花

✅ 正确做法：用环境变量

方法 1：操作系统环境变量
  export ANTHROPIC_API_KEY=sk-ant-xxxxx
  # SDK 会自动读取环境变量

方法 2：.env 文件（开发环境常用）
  # .env 文件（加到 .gitignore 里！）
  ANTHROPIC_API_KEY=sk-ant-xxxxx
  DATABASE_URL=postgresql://user:pass@localhost:5432/mydb

  # Python 中读取
  from dotenv import load_dotenv
  import os

  load_dotenv()  # 读取 .env 文件
  api_key = os.getenv("ANTHROPIC_API_KEY")

方法 3：Docker 环境变量
  docker run -e ANTHROPIC_API_KEY=sk-ant-xxxxx my-app

方法 4：云平台的密钥管理服务（生产环境推荐）
  AWS Secrets Manager / 阿里云密钥管理 / HashiCorp Vault
```

---

## 第十一章：部署上线——从本地到云端

### 11.1 部署方式对比

```
你的代码写好了、Docker 打包好了，现在要让别人用。
代码在你电脑上 → 需要部署到服务器上。

三种主要部署方式：

方式 1：云服务器（最传统）
═══════════════════════
是什么：租一台云上的电脑，把你的代码放上去运行。
大白话：就像租一间办公室，你在里面开公司。

代表：阿里云 ECS、腾讯云 CVM、AWS EC2

优点：
├─ 完全控制，想装什么装什么
├─ 适合长期运行的服务
└─ 可以按需选配置

缺点：
├─ 需要自己维护（系统更新、安全补丁）
├─ 需要自己处理扩缩容
└─ 不管有没有请求都要付费

费用参考：
├─ 2核4G：约 ¥100-200/月
├─ 4核8G：约 ¥200-400/月
└─ AI 应用通常 2核4G 起步就够


方式 2：Serverless / 云函数（按调用计费）
══════════════════════════════════════
是什么：不需要服务器，代码上传后自动运行，按调用次数计费。
大白话：就像共享厨房，做一道菜收一次钱，不做菜不收钱。

代表：AWS Lambda、阿里云函数计算、Vercel

优点：
├─ 不需要管服务器
├─ 自动扩缩容
├─ 没有请求时不花钱
└─ 适合流量不稳定的应用

缺点：
├─ 冷启动延迟（几秒到十几秒）
├─ 运行时间有限制（通常 5-15 分钟）
├─ Agent 这种长时间运行的不太适合
└─ 流量大的时候可能比服务器更贵

适合：轻量级 API、Webhook、定时任务


方式 3：容器服务（Docker 部署到云端）
═══════════════════════════════════
是什么：把你的 Docker 容器部署到云端的容器平台。
大白话：把集装箱运到码头（云端），码头帮你管理。

代表：AWS ECS/Fargate、阿里云容器服务、Railway、Fly.io

优点：
├─ Docker 本地怎么跑，云端就怎么跑
├─ 平台帮你管理扩缩容
├─ 比纯 Serverless 更灵活
└─ 适合 AI 应用

缺点：
├─ 比纯云服务器贵一些
└─ 需要学 Docker（你已经学了）

推荐：AI 应用最推荐这种方式
```

### 11.2 最简部署流程（云服务器 + Docker）

```
Step 1：准备云服务器
├─ 买一台阿里云 / 腾讯云 ECS（2核4G起步）
├─ 选 Ubuntu 22.04 系统
├─ 记住服务器的 IP 地址
└─ 开放 8000 端口（在安全组配置中）

Step 2：在服务器上安装 Docker
├─ SSH 连接到服务器
├─ 安装 Docker 和 Docker Compose
└─ 一般云服务商有一键安装脚本

Step 3：上传代码到服务器
├─ 方式A：git clone（推荐）
│   在服务器上 clone 你的代码仓库
├─ 方式B：scp 上传
│   scp -r ./your-project user@服务器IP:/home/user/
└─ 方式C：用 CI/CD 自动部署（见第十二章）

Step 4：启动服务
├─ cd your-project
├─ 设置环境变量
│   export ANTHROPIC_API_KEY=sk-ant-xxxxx
├─ docker-compose up -d
└─ 完成！访问 http://服务器IP:8000 就能用了

Step 5：配置域名和 HTTPS（可选但推荐）
├─ 买一个域名（如 ai.yourcompany.com）
├─ DNS 指向你的服务器 IP
├─ 用 Nginx 反向代理 + Let's Encrypt 免费证书
└─ 用户通过 https://ai.yourcompany.com 访问
```

### 11.3 Nginx 反向代理（面试常问）

```
是什么：
放在你的 AI 服务前面的"门卫"，帮你处理一些事情。

大白话：
Nginx 就像餐厅的前台。
客人（用户请求）先到前台 → 前台安排到合适的桌子（后端服务）。

为什么需要：
├─ HTTPS 加密（Nginx 处理证书，你的代码不用管）
├─ 域名绑定（让用户用域名而不是 IP 访问）
├─ 负载均衡（多台服务器时分发请求）
├─ 静态文件（前端的 HTML/CSS/JS 由 Nginx 直接返回，不经过你的 Python）
└─ 安全防护（隐藏真实端口、基本的 DDoS 防护）
```

```nginx
# nginx.conf 配置示例

server {
    listen 80;
    server_name ai.yourcompany.com;

    # HTTP 自动跳转到 HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl;
    server_name ai.yourcompany.com;

    # HTTPS 证书
    ssl_certificate /etc/letsencrypt/live/ai.yourcompany.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/ai.yourcompany.com/privkey.pem;

    # 把请求转发给你的 FastAPI 服务
    location /api/ {
        proxy_pass http://localhost:8000/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;

        # SSE 流式输出需要的配置
        proxy_buffering off;           # 关闭缓冲，让流式数据直接透传
        proxy_cache off;               # 关闭缓存
        proxy_read_timeout 300s;       # Agent 可能需要较长时间
    }
}
```

```
注意：Nginx 配置流式输出时容易踩坑！

默认情况下 Nginx 会缓冲后端的响应。
对于 SSE 流式输出，必须关闭缓冲：
  proxy_buffering off;

否则用户会看到：等很久 → 突然所有内容一起出来
而不是：一个字一个字出来

这是面试和实际工作中的高频坑。
```

---

## 第十二章：CI/CD——自动化发布流程

### 12.1 是什么：为什么需要 CI/CD

```
大白话解释：

没有 CI/CD 的发布流程：
1. 你改了代码
2. 手动运行测试 → 有时候忘了测试
3. 手动 SSH 连上服务器
4. 手动 git pull 拉代码
5. 手动 docker build
6. 手动 docker-compose restart
7. 手动检查有没有问题
8. 有时候上线后才发现有 bug
9. 凌晨 3 点被叫起来修 bug

有 CI/CD 的发布流程：
1. 你改了代码，push 到 Git
2. 自动运行测试 → 测试不过不让上线
3. 自动构建 Docker 镜像
4. 自动部署到服务器
5. 自动检查是否正常
6. 有问题自动回滚
7. 你安心睡觉

CI = Continuous Integration（持续集成）
  每次提交代码 → 自动测试 → 确保没有引入 bug

CD = Continuous Deployment（持续部署）
  测试通过 → 自动部署到服务器 → 用户立刻能用新版本

大白话总结：
CI = "每次提交都自动测试"
CD = "测试过了就自动上线"
```

### 12.2 GitHub Actions 简单示例

```yaml
# .github/workflows/deploy.yml
# 当代码 push 到 main 分支时，自动测试并部署

name: Test and Deploy

on:
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run tests
        run: pytest tests/

  deploy:
    needs: test  # 测试通过才部署
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Deploy to server
        run: |
          # SSH 连接服务器并部署
          ssh user@your-server "cd /app && git pull && docker-compose up -d --build"
```

```
上面的配置做了什么？

1. 你 push 代码到 main 分支
2. GitHub 自动开始运行：
   ├─ 安装 Python 3.11
   ├─ 安装项目依赖
   ├─ 运行所有测试（pytest tests/）
   │   ├─ 如果测试失败 → 停止，不部署 → 你收到通知
   │   └─ 如果测试通过 → 继续部署
   └─ SSH 连接你的服务器 → 拉代码 → 重启服务

以后你改代码的流程就是：
  改代码 → git push → 等 2 分钟 → 新版本自动上线

再也不用手动 SSH 到服务器了。
```

---

## 第十三章：常见问题诊断手册

### 13.1 生产环境常见问题速查表

| 现象 | 可能原因 | 解决方案 |
|------|----------|----------|
| API 返回 500 错误 | LLM API 调用失败 | 检查 API Key、加重试逻辑 |
| 响应时间突然变长 | LLM 服务过载 / 上下文太长 | 加超时、压缩历史、模型降级 |
| 内存持续增长 | 对话历史没有清理 | 加消息历史长度限制 |
| Redis 连接失败 | Redis 服务挂了 / 连接数满了 | 检查 Redis 状态、配置连接池 |
| Docker 容器自动重启 | 内存不足被 OOM Killed | 增加内存限制或优化代码 |
| CORS 跨域报错 | 没配 CORS 中间件 | 添加 CORSMiddleware |
| 流式输出不流畅 | Nginx 缓冲没关 | 设置 proxy_buffering off |
| 费用异常飙升 | 有用户疯狂调用 / Agent 死循环 | 加限流 + 预算上限 |
| 数据库连接失败 | 连接数用完了 | 用连接池、增加最大连接数 |
| 上线后行为和本地不同 | 环境变量不一致 | 检查 .env 和服务器环境变量 |

### 13.2 性能优化检查清单

```
你的 AI 应用慢？按这个清单逐项检查：

□ 是否使用了流式输出？
  不是 → 用 SSE，用户感知延迟可从 8 秒降到 0.3 秒

□ 是否使用了异步编程？
  不是 → 改为 async/await，并发能力提升 10 倍以上

□ 是否有缓存？
  不是 → 加 Redis 缓存，重复问题直接返回

□ 是否用了 Prompt Caching？
  不是 → 开启，减少 LLM 处理 System Prompt 的时间

□ System Prompt 是否过长？
  是 → 精简，每减少 1000 tokens 约快 0.5 秒

□ 消息历史是否过长？
  是 → 压缩历史 / 滑动窗口

□ 是否有不必要的工具定义？
  是 → 只传必要的工具，减少 LLM 选择时间

□ 外部工具是否有超时设置？
  不是 → 所有外部调用加 timeout

□ 数据库查询是否有索引？
  不是 → 给常用查询字段加索引

□ Nginx 是否关闭了 SSE 缓冲？
  不是 → 加 proxy_buffering off
```

---

## 第十四章：面试高频考题与答案

### Q1：AI 应用为什么要用 FastAPI 而不是 Flask？

**答案：**

FastAPI 比 Flask 更适合 AI 应用，主要原因：

1. **原生异步支持**：AI 应用大量时间在等 LLM API 返回，异步编程能同时处理多个请求。Flask 是同步的，需要额外配置。

2. **原生流式输出**：LLM 的逐字输出需要 SSE/流式响应，FastAPI 原生支持 StreamingResponse，Flask 实现更复杂。

3. **自动数据校验**：通过 Pydantic 模型自动校验请求参数，减少 Bug。

4. **自动生成 API 文档**：写好代码自动有交互式文档（/docs），方便前端对接。

5. **性能**：基于 Starlette，性能是 Flask 的 2-3 倍。

---

### Q2：什么是异步编程？为什么 AI 应用必须用异步？

**答案：**

异步编程允许程序在等待一个操作（比如 LLM API 返回）时，去处理其他任务，而不是傻等。

AI 应用必须用异步的原因：一次 LLM 调用通常耗时 2-10 秒，其中 99% 的时间是在"等待网络响应"。同步程序在等待时什么都不做，10 个并发用户就需要 10 个线程。异步程序在等待时去处理其他请求，单线程就能处理上百个并发。

核心关键词：`async def` 声明异步函数，`await` 等待异步操作并让出控制权，`asyncio.gather` 并行执行多个异步任务。

常见陷阱：在 async 函数中用同步库（如 `requests`、`time.sleep`）会阻塞整个事件循环，应该用对应的异步库（`httpx`、`asyncio.sleep`）。

---

### Q3：什么是指数退避（Exponential Backoff）？为什么要用它？

**答案：**

指数退避是一种重试策略：每次重试的等待时间翻倍。比如第 1 次等 1 秒，第 2 次等 2 秒，第 3 次等 4 秒。

为什么不用固定间隔重试：如果 LLM 服务过载了，1000 个客户端同时固定等 1 秒后重试，会再次同时打到服务器上造成"惊群效应"。指数退避让不同客户端在不同时间重试，给服务器喘息的空间。

哪些错误该重试：429（限流）、5xx（服务器错误）、网络超时。哪些不该重试：400（参数错误）、401（认证失败）——这些重试也不会成功。

---

### Q4：什么是模型降级？怎么设计降级链？

**答案：**

模型降级是当主模型不可用时，自动切换到备用模型以保证服务可用性。

设计原则：
- **降级链**：主模型（高质量）→ 备选1（同厂商更快模型）→ 备选2（跨厂商模型）
- 例如：Claude Sonnet → Claude Haiku → GPT-4o-mini
- **只对可重试错误降级**（5xx、超时、429），不对参数错误降级
- **记录降级日志**：告诉用户当前使用的是备用模型，监控降级频率
- **降级时可能需要调整 Prompt**：不同模型能力不同，Prompt 可能需要适配

核心价值："能用但质量稍差"远好于"完全不能用"。

---

### Q5：SSE 和 WebSocket 有什么区别？AI 应用用哪个？

**答案：**

| 维度 | SSE | WebSocket |
|------|-----|-----------|
| 方向 | 单向（服务器→客户端） | 双向 |
| 协议 | HTTP | ws:// |
| 实现复杂度 | 简单 | 复杂 |
| 断线重连 | 自动 | 需手动实现 |
| 适用场景 | LLM 流式输出 | 实时对话、协作 |

AI 应用推荐用 SSE：LLM 的流式输出本质是"服务器不断推送数据给客户端"，是单向的，SSE 完全够用且实现简单。只有当需要实时双向通信（如用户中途打断生成）时才需要 WebSocket。

部署注意：Nginx 反向代理需要关闭缓冲（`proxy_buffering off`），否则 SSE 数据会被缓冲住而不是实时推送。

---

### Q6：Docker 是什么？为什么 AI 应用需要它？

**答案：**

Docker 是容器化技术，把应用代码和所有依赖打包成一个"容器"，在任何环境中都能一致运行。

AI 应用特别需要 Docker 的原因：
1. **依赖多且敏感**：AI 项目依赖几十个库，版本不对就报错。Docker 冻结了所有依赖。
2. **开发与生产环境一致**：开发用 Windows，生产用 Linux，Docker 消除差异。
3. **可复制**：一条命令就能复制整套环境。
4. **扩缩容**：流量增加时启动更多容器即可。

核心概念：Image（镜像=设计图）、Container（容器=运行实例）、Dockerfile（构建说明）、Docker Compose（多服务编排）。

---

### Q7：怎么控制 AI 应用的成本？

**答案：**

最有效的五个策略：

1. **模型分层**：简单任务用便宜模型（Haiku），复杂任务才用贵模型（Sonnet/Opus）——可省 60-80%
2. **缓存**：Redis 缓存重复问题的回答——FAQ 场景可省 30-50%
3. **Prompt Caching**：缓存重复的 System Prompt——可省 90% 的重复 token 费用
4. **用户配额**：限制每用户每日调用量和 token 消耗——防止个别用户消耗过多
5. **消息历史压缩**：Agent 场景中压缩早期对话——减少每轮的 input tokens

同时必须有成本监控：记录每次调用的 token 消耗和费用，设置日预算告警线。

---

### Q8：生产环境中，你会怎么设计 AI 应用的日志系统？

**答案：**

四个关键设计点：

1. **结构化日志**：用 JSON 格式而非纯文本，方便机器解析和搜索
2. **request_id 串联**：每次用户请求生成唯一 ID，该请求的所有日志（收到请求、LLM 调用、工具调用、返回结果）都携带该 ID，便于追踪完整链路
3. **分级记录**：INFO 记正常流转、WARNING 记降级/重试、ERROR 记失败，生产环境不开 DEBUG
4. **不记录敏感信息**：不记用户的完整对话内容（记长度即可），不记 API Key，必要时做脱敏

AI 应用专用日志字段：model、input_tokens、output_tokens、cost_usd、latency_ms、tool_calls、cache_hit。

---

### Q9：描述一个完整的 AI 应用部署流程

**答案：**

1. **本地开发完成** → 所有测试通过
2. **Docker 打包** → 编写 Dockerfile + docker-compose.yml
3. **推送代码** → git push 到 main 分支
4. **CI 自动测试** → GitHub Actions 运行 pytest
5. **CD 自动部署** → 测试通过后自动 SSH 到服务器，执行 git pull + docker-compose up
6. **Nginx 反向代理** → HTTPS 终止 + 域名绑定 + SSE 缓冲关闭
7. **监控确认** → 检查健康检查接口、错误率、响应时间
8. **上线完成** → 用户通过 https://domain.com 访问

回滚方案：如果新版本出问题，docker-compose 回退到上一个镜像版本。

---

### Q10：什么是限流？怎么实现？

**答案：**

限流是控制每个用户的 API 调用频率，防止滥用和保护系统。

实现方式：用 Redis 的 INCR 命令实现滑动窗口计数器——key 为 `rate_limit:{user_id}:{当前分钟}`，每次请求加 1，超过阈值返回 429。key 设 60 秒过期，自动清理。

设计要点：
- 不同用户等级不同限额（免费用户 10 RPM，付费用户 100 RPM）
- 限流后返回明确的错误信息（告诉用户还需等多久）
- 同时限制 RPM（每分钟次数）和日 Token 总量
- 限流信息通过响应头返回（X-RateLimit-Remaining）

---

## 第十五章：实战项目方向

### 15.1 工程化实战项目

```
项目 1（入门）：把你的 RAG 系统包装成 API
├─ 用 FastAPI 封装 RAG 查询接口
├─ 加上流式输出
├─ 加上 API Key 认证
├─ 加上基本日志
├─ 用 Docker 打包
└─ 核心技能：FastAPI + SSE + Docker

项目 2（中等）：完整的对话服务
├─ 用户注册/登录
├─ 对话历史存 PostgreSQL
├─ 流式回答
├─ Redis 缓存 + 限流
├─ Token 消耗统计
├─ Docker Compose 一键部署
└─ 核心技能：全栈 + 数据库 + 缓存

项目 3（进阶）：生产级 Agent 服务
├─ Agent 任务执行 + 工具调用
├─ HITL 审批流程
├─ 模型降级 + 重试策略
├─ 完整的监控和告警
├─ 成本控制和用户配额
├─ CI/CD 自动部署
├─ Nginx + HTTPS
└─ 核心技能：全部工程化知识

项目 4（实战）：企业接入
├─ 对接企业微信/钉钉/飞书
├─ 多租户隔离
├─ 审计日志
├─ 权限管理
└─ 核心技能：企业级工程化
```

### 15.2 从工程化到下一步

```
你已完成：
  Step 1: Prompt Engineering ✅
  Step 2: RAG ✅
  Step 3: Tool Use ✅
  Step 4: Agent ✅
  Step 5: 工程化基础 ✅ ← 你在这里

下一步：
  Step 6: 评估体系——怎么证明你的系统好用，怎么持续优化

学完 Step 1-6，你就是一个能独立交付企业级 AI 项目的工程师。

准备好学 Step 6（评估体系）时告诉我。
```

---

> **全篇核心总结：** 工程化是把"能跑的 Demo"变成"能用的产品"的关键一步。核心技能包括：**FastAPI**（API 开发）、**async/await**（异步并发）、**SSE**（流式输出，用户体验的关键优化）、**重试+超时+降级**（LLM 调用的三板斧）、**Docker**（标准化部署）、**PostgreSQL+Redis**（数据存储和缓存）、**监控告警**（出问题及时发现）、**成本控制**（模型分层+缓存+配额）、**认证限流**（安全防护）。掌握这些，你就能把前面学的 Prompt/RAG/Agent 能力包装成一个真正的产品。
