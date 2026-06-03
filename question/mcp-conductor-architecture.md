# mcp-conductor 架构设计文档

> 基于 Claude Code 环境下的实际测试与使用体验，对 mcp-conductor 的完整架构设计。
>
> 本文档描述 mcp-conductor "应该是什么样"——组件关系、数据流、模块交互、核心机制。
>
> 日期：2026-06-03

---

## 目录

- [一、架构全景](#一架构全景)
- [二、核心组件](#二核心组件)
- [三、数据流设计](#三数据流设计)
- [四、核心机制](#四核心机制)
- [五、模块交互时序](#五模块交互时序)
- [六、配置体系](#六配置体系)
- [七、状态管理](#七状态管理)
- [八、错误处理架构](#八错误处理架构)
- [九、上下文效率设计](#九上下文效率设计)
- [十、与 Claude Code 的集成边界](#十与-claude-code-的集成边界)

---

## 一、架构全景

### 1.1 系统定位

mcp-conductor 是一个 **MCP 网关（Gateway）**，位于 MCP Host（如 Claude Code）和多个上游 MCP Server 之间。它的核心职责是：

- **统一管理**：一个入口管理所有上游 MCP
- **按需发现**：不预加载所有工具，按任务需要发现和加载
- **安全路由**：对调用进行安全检查、审计、限流
- **可靠调度**：健康检查、超时管理、熔断降级

```
┌──────────────────────────────────────────────────────────────┐
│                     MCP Host（Claude Code）                    │
│                                                              │
│  ┌─────────┐  ┌───────────┐  ┌───────────┐                  │
│  │ ToolSearch│  │ LLM 推理  │  │ 内置工具   │                  │
│  └────┬─────┘  └─────┬─────┘  └───────────┘                  │
│       │              │                                        │
└───────┼──────────────┼────────────────────────────────────────┘
        │              │
        │     MCP 协议（stdio / HTTP / SSE）
        │              │
┌───────▼──────────────▼────────────────────────────────────────┐
│                                                               │
│                    mcp-conductor                               │
│                                                               │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │                   工具层（Tools）                         │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │  │
│  │  │analyze   │ │call_      │ │execute_  │ │list_      │   │  │
│  │  │_user_task│ │upstream   │ │task      │ │capabilities│  │  │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘   │  │
│  └────────────────────────┬────────────────────────────────┘  │
│                           │                                   │
│  ┌────────────────────────▼────────────────────────────────┐  │
│  │                 调度层（Router）                          │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │  │
│  │  │任务分析器 │ │能力注册表 │ │会话缓存  │ │推荐引擎  │   │  │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘   │  │
│  └────────────────────────┬────────────────────────────────┘  │
│                           │                                   │
│  ┌────────────────────────▼────────────────────────────────┐  │
│  │                 安全层（Security）                        │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │  │
│  │  │输入过滤  │ │输出过滤  │ │数据流管控│ │速率限制  │   │  │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘   │  │
│  │  ┌──────────┐ ┌──────────┐                              │  │
│  │  │审计日志  │ │信任评级  │                              │  │
│  │  └──────────┘ └──────────┘                              │  │
│  └────────────────────────┬────────────────────────────────┘  │
│                           │                                   │
│  ┌────────────────────────▼────────────────────────────────┐  │
│  │               连接层（Connection）                        │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │  │
│  │  │连接管理器 │ │健康检查  │ │熔断器    │ │超时/重试  │   │  │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘   │  │
│  │  ┌──────────┐ ┌──────────┐                              │  │
│  │  │stdio 适配│ │HTTP 适配 │                              │  │
│  │  └──────────┘ └──────────┘                              │  │
│  └─────────────────────────────────────────────────────────┘  │
│                                                               │
└───────────────────────────────┬───────────────────────────────┘
                                │
                ┌───────────────┼───────────────┐
                │               │               │
           ┌────▼────┐    ┌────▼────┐    ┌────▼────┐
           │Upstream A│    │Upstream B│    │Upstream C│
           │(stdio)  │    │(HTTP)   │    │(stdio)  │
           └─────────┘    └─────────┘    └─────────┘
```

### 1.2 设计原则

| 原则 | 含义 | 体现 |
|---|---|---|
| **最小上下文** | 向 Host 返回的数据尽量少 | 摘要注册 + 精简推荐 + 按需加载 schema |
| **显式可见** | 上游能力对 LLM 可感知 | 能力摘要注册（即使看不到完整 schema，也知道有什么） |
| **快速失败** | 出错立即返回明确信息 | 结构化错误、超时熔断、健康检查 |
| **优雅降级** | 上游不可用时有替代方案 | 降级链、熔断恢复、部分失败 |
| **安全默认** | 安全检查默认开启 | 输入/输出过滤、速率限制、审计日志 |
| **渐进复杂度** | 简单场景用简单接口 | execute_task（1 步）+ analyze/call（3 步）并存 |
| **可插拔** | 各模块可独立替换 | 适配器接口、推荐策略可配置 |

---

## 二、核心组件

### 2.1 工具层（Tools Layer）

conductor 向 MCP Host 暴露的工具集合。这是 LLM 唯一直接交互的接口。

```
┌───────────────────────────────────────────────────────────┐
│                    Tools Layer                             │
│                                                           │
│  高级接口（推荐 LLM 优先使用）：                              │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  execute_task(task, tool_hint?, arguments?)          │  │
│  │  → 一步完成：分析 → 选择 → 调用                        │  │
│  │  → 适合已知任务类型的场景                               │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                           │
│  底层接口（精细控制）：                                      │
│  ┌──────────────────┐  ┌────────────────────────────┐     │
│  │ analyze_user_task │  │ call_upstream_tool         │     │
│  │ (task)            │  │ (recommendation_id,        │     │
│  │ → 返回推荐列表     │  │  route_token,              │     │
│  │                   │  │  capability_id,            │     │
│  │                   │  │  arguments)                │     │
│  └──────────────────┘  └────────────────────────────┘     │
│                                                           │
│  管理接口：                                                │
│  ┌──────────────────┐  ┌────────────────────────────┐     │
│  │list_upstream_    │  │read_upstream_resource      │     │
│  │capabilities()    │  │(recommendation_id,         │     │
│  │→ 列出所有能力     │  │ route_token, resource_uri) │     │
│  └──────────────────┘  └────────────────────────────┘     │
│                                                           │
│  能力摘要（作为 resource 或 prompt 暴露）：                  │
│  ┌──────────────────────────────────────────────────────┐ │
│  │  capability_summary                                   │ │
│  │  → 启动时自动生成                                      │ │
│  │  → 极简格式，每个上游一行                               │ │
│  │  → 让 LLM 知道背后有什么可用                            │ │
│  └──────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────┘
```

### 2.2 调度层（Router Layer）

负责分析任务、匹配工具、管理能力和缓存。

```
┌───────────────────────────────────────────────────────────┐
│                    Router Layer                            │
│                                                           │
│  ┌─────────────────┐     ┌─────────────────┐             │
│  │  任务分析器       │     │  推荐引擎        │             │
│  │  (Analyzer)      │     │  (Recommender)   │             │
│  │                 │     │                 │             │
│  │  输入：用户任务   │────▶│  输入：分析结果   │             │
│  │  输出：意图+分类  │     │  + 能力注册表    │             │
│  │                 │     │  输出：推荐列表   │             │
│  └─────────────────┘     │  （2~3 个，含    │             │
│                          │   置信度评分）    │             │
│  ┌─────────────────┐     └─────────────────┘             │
│  │  能力注册表       │          │                         │
│  │  (Registry)      │          │                         │
│  │                 │          ▼                         │
│  │  存储内容：       │     ┌─────────────────┐             │
│  │  - 上游 ID       │     │  会话缓存        │             │
│  │  - 工具名称      │     │  (Cache)         │             │
│  │  - 工具描述      │     │                 │             │
│  │  - 参数 schema   │     │  缓存内容：       │             │
│  │  - 风险等级      │     │  - 已发现的能力   │             │
│  │  - 分类标签      │     │  - route_token   │             │
│  │                 │     │  - 推荐结果       │             │
│  │  来源：          │     │                 │             │
│  │  启动时扫描上游   │     │  策略：           │             │
│  │  + 摘要信息      │     │  TTL 5 分钟       │             │
│  └─────────────────┘     │  LRU 淘汰        │             │
│                          └─────────────────┘             │
└───────────────────────────────────────────────────────────┘
```

#### 能力注册表的详细设计

```python
@dataclass
class Capability:
    """单个工具/资源/提示词的注册信息"""
    capability_id: str        # "fetch-1.tools.fetch"
    upstream_id: str          # "fetch-1"
    capability_type: str      # "tool" / "resource" / "prompt"
    name: str                 # "fetch"
    summary: str              # "网页抓取（HTTP/HTTPS）"  ← 摘要注册用
    description: str          # 完整描述 ← 按需加载
    input_schema: dict        # 完整参数定义 ← 按需加载
    risk_level: str           # "read_only" / "mutating" / "destructive"
    category: str             # "web" / "file" / "memory" / "docs" / "reasoning"
    tags: list[str]           # ["http", "fetch", "web", "scrape"]
    trust_level: str          # "verified" / "community" / "untrusted"
    available: bool           # 上游是否可用

@dataclass
class CapabilityRegistry:
    """所有上游能力的注册表"""
    _capabilities: dict[str, Capability]   # {capability_id: Capability}
    _by_category: dict[str, list[str]]     # {category: [capability_ids]}
    _by_upstream: dict[str, list[str]]     # {upstream_id: [capability_ids]}

    def get_summary(self) -> str:
        """生成极简摘要，用于注册到 Host"""
        lines = ["Available upstream capabilities:"]
        for uid, cap_ids in self._by_upstream.items():
            caps = [self._capabilities[cid] for cid in cap_ids]
            # 每个上游一行，只取第一个工具的描述 + 工具数量
            first = caps[0].summary if caps else "unknown"
            count = len(caps)
            lines.append(f"- {uid}: {first} ({count} tools)")
        return "\n".join(lines)

    def search(self, task: str, category: str = None) -> list[Capability]:
        """按任务和分类搜索能力"""
        pool = self._by_category.get(category, []) if category else list(self._capabilities.keys())
        return [self._capabilities[cid] for cid in pool]
```

### 2.3 安全层（Security Layer）

所有调用必经的安全检查管道。

```
┌───────────────────────────────────────────────────────────┐
│                   Security Layer                           │
│                                                           │
│  调用方向：                                                │
│  Host → [输入过滤] → [速率限制] → [数据流检查]              │
│       → [调用上游] → [输出过滤] → [审计记录] → Host        │
│                                                           │
│  ┌──────────────┐                                        │
│  │  输入过滤     │  检查时机：调用前                        │
│  │  (InputGuard)│                                        │
│  │              │  检查内容：                              │
│  │              │  ① 参数类型与 schema 匹配               │
│  │              │  ② 文件路径安全（禁止 ../etc/ ~/.ssh/）  │
│  │              │  ③ URL 格式验证                         │
│  │              │  ④ 注入模式检测（SQL/命令/prompt）       │
│  └──────┬───────┘                                        │
│         │                                                 │
│  ┌──────▼───────┐                                        │
│  │  速率限制     │  检查时机：调用前                        │
│  │  (RateLimiter)│                                       │
│  │              │  检查内容：                              │
│  │              │  ① 每分钟调用次数                        │
│  │              │  ② 每会话调用次数                        │
│  │              │  ③ 循环检测（连续相同调用）               │
│  │              │  ④ 数据传输量                            │
│  └──────┬───────┘                                        │
│         │                                                 │
│  ┌──────▼───────┐                                        │
│  │  数据流管控   │  检查时机：调用前                        │
│  │  (DataFlow)  │                                        │
│  │              │  检查内容：                              │
│  │              │  ① 追踪前序调用的返回数据来源             │
│  │              │  ② 检测参数中是否含敏感数据               │
│  │              │  ③ 判断数据流向是否合规                   │
│  │              │  ④ 跨上游数据传递限制                    │
│  └──────┬───────┘                                        │
│         │                                                 │
│      [调用上游]                                            │
│         │                                                 │
│  ┌──────▼───────┐                                        │
│  │  输出过滤     │  检查时机：调用后                        │
│  │  (OutputGuard)│                                       │
│  │              │  检查内容：                              │
│  │              │  ① Prompt 注入模式检测                   │
│  │              │  ② 敏感数据泄露检测                      │
│  │              │  ③ 响应大小限制                          │
│  │              │  ④ 可疑内容标记（不阻止但降低信任度）     │
│  └──────┬───────┘                                        │
│         │                                                 │
│  ┌──────▼───────┐                                        │
│  │  审计日志     │  记录时机：每次调用                      │
│  │  (AuditLog)  │                                        │
│  │              │  记录内容：                              │
│  │              │  ① 时间戳、会话 ID                      │
│  │              │  ② 调用链（caller → conductor → upstream）│
│  │              │  ③ 参数（脱敏后）                        │
│  │              │  ④ 结果状态 + 延迟                       │
│  │              │  ⑤ 安全标记                             │
│  └──────────────┘                                        │
│                                                           │
└───────────────────────────────────────────────────────────┘
```

### 2.4 连接层（Connection Layer）

管理上游 MCP 的连接、健康、熔断。

```
┌───────────────────────────────────────────────────────────┐
│                  Connection Layer                          │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐  │
│  │              连接管理器 (ConnectionManager)           │  │
│  │                                                     │  │
│  │  ┌───────────┐  ┌───────────┐  ┌───────────┐       │  │
│  │  │ 上游 A    │  │ 上游 B    │  │ 上游 C    │       │  │
│  │  │           │  │           │  │           │       │  │
│  │  │ Adapter   │  │ Adapter   │  │ Adapter   │       │  │
│  │  │ Circuit   │  │ Circuit   │  │ Circuit   │       │  │
│  │  │ Health    │  │ Health    │  │ Health    │       │  │
│  │  │ Retry     │  │ Retry     │  │ Retry     │       │  │
│  │  └───────────┘  └───────────┘  └───────────┘       │  │
│  │                                                     │  │
│  │  每个上游独立管理：                                    │  │
│  │  - Adapter:  连接方式（stdio/HTTP/SSE）               │  │
│  │  - Circuit:  熔断器（CLOSED/OPEN/HALF_OPEN）         │  │
│  │  - Health:   健康状态（healthy/unhealthy/unknown）    │  │
│  │  - Retry:    重试策略（次数/退避/可重试错误类型）      │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐  │
│  │              传输适配器 (Transport Adapter)           │  │
│  │                                                     │  │
│  │  ┌───────────┐  ┌───────────┐  ┌───────────┐       │  │
│  │  │ stdio     │  │ HTTP/SSE  │  │ WebSocket │       │  │
│  │  │           │  │           │  │           │       │  │
│  │  │ 子进程管理 │  │ HTTP 客户端│  │ WS 客户端 │       │  │
│  │  │ stdin/out │  │ SSE 订阅  │  │ 长连接    │       │  │
│  │  └───────────┘  └───────────┘  └───────────┘       │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐  │
│  │              健康检查 (Health Monitor)                │  │
│  │                                                     │  │
│  │  定期（30s）检查所有上游：                             │  │
│  │  - stdio:  发送 ping 请求                            │  │
│  │  - HTTP:   发送 HEAD 请求                            │  │
│  │  - 通用:   调用 list_tools 确认存活                   │  │
│  │                                                     │  │
│  │  状态变化触发事件：                                    │  │
│  │  healthy → unhealthy: UPSTREAM_DOWN 事件             │  │
│  │  unhealthy → healthy: UPSTREAM_RECOVERED 事件        │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐  │
│  │              熔断器 (Circuit Breaker)                 │  │
│  │                                                     │  │
│  │  状态机：                                            │  │
│  │                                                     │  │
│  │  CLOSED ──失败达阈值──▶ OPEN ──冷却结束──▶ HALF_OPEN │  │
│  │    ▲                                          │     │  │
│  │    │                                          │     │  │
│  │    └──────────────────成功────────────────────┘     │  │
│  │                                          │           │  │
│  │                                        失败           │  │
│  │                                          ▼           │  │
│  │                                       OPEN           │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                           │
└───────────────────────────────────────────────────────────┘
```

---

## 三、数据流设计

### 3.1 完整调用数据流

```
LLM 发起调用
│
│  ① 请求进入工具层
│
├── Tool: execute_task(task, tool_hint?, arguments?)
│   │
│   │  ② 工具层委托给调度层
│   │
│   ├── Router: 查缓存
│   │   ├── 命中缓存 → 直接跳到步骤 ⑥
│   │   └── 未命中 → 继续
│   │
│   ├── Router: 任务分析
│   │   │
│   │   │  ③ 分析器提取意图和分类
│   │   │
│   │   ├── Analyzer: classify(task) → category
│   │   │   "抓取网页" → category="web"
│   │   │
│   │   └── Analyzer: extract_intent(task) → intent
│   │       "抓取网页" → intent="fetch_url"
│   │
│   ├── Router: 推荐匹配
│   │   │
│   │   │  ④ 在注册表中搜索 + 排序
│   │   │
│   │   ├── Registry: search(category="web")
│   │   │   → [fetch-1.tools.fetch]
│   │   │
│   │   └── Recommender: rank(candidates, intent)
│   │       → [fetch-1.tools.fetch (confidence=0.95)]
│   │
│   │  ⑤ 安全层入站检查
│   │
│   ├── Security: 输入过滤
│   │   └── 检查参数合法性 → PASS
│   │
│   ├── Security: 速率限制
│   │   └── 检查调用频率 → PASS
│   │
│   ├── Security: 数据流检查
│   │   └── 检查参数中无敏感数据 → PASS
│   │
│   │  ⑥ 连接层执行调用
│   │
│   ├── Connection: 检查熔断器
│   │   └── CLOSED → 允许调用
│   │
│   ├── Connection: 检查健康状态
│   │   └── healthy → 继续
│   │
│   ├── Connection: 带超时执行
│   │   ├── Transport: stdio/HTTP 发送请求到上游
│   │   ├── 等待响应（超时 30s）
│   │   └── 收到响应
│   │
│   │  ⑦ 安全层出站检查
│   │
│   ├── Security: 输出过滤
│   │   └── 检查 prompt 注入 → PASS
│   │   └── 检查敏感数据 → PASS
│   │
│   ├── Security: 审计记录
│   │   └── 写入审计日志
│   │
│   │  ⑧ 更新缓存
│   │
│   ├── Cache: 缓存发现结果
│   │   └── "fetch_web_page" → fetch-1.tools.fetch
│   │
│   │  ⑨ 返回结果
│   │
│   └── Tool: 格式化返回
│       └── { status: "success", data: ..., meta: {...} }
│
▼
LLM 收到结果
```

### 3.2 能力发现数据流（启动时）

```
Conductor 启动
│
├── ① 加载配置
│   └── 读取 upstreams 配置列表
│
├── ② 连接每个上游
│   ├── Transport: 建立 stdio/HTTP 连接
│   ├── Capability Discovery: 查询支持的类型
│   │   ├── list_tools()        → 获取工具列表 + schema
│   │   ├── list_resources()    → 获取资源列表（如果支持）
│   │   ├── list_prompts()      → 获取提示词列表（如果支持）
│   │   └── 不支持的类型优雅跳过（不报错）
│   │
│   └── 存入能力注册表
│       └── Registry.register(capability)
│
├── ③ 生成能力摘要
│   └── Registry.get_summary()
│       → "fetch-1: 网页抓取 (2 tools)"
│       → "memory-1: 知识图谱存储 (9 tools)"
│       → ...
│
├── ④ 启动健康检查
│   └── HealthMonitor.start() → 后台循环（30s 间隔）
│
├── ⑤ 初始化熔断器
│   └── 每个上游一个 CircuitBreaker 实例
│
└── ⑥ 就绪，等待 Host 调用
```

### 3.3 安全数据流（跨调用追踪）

```
调用 #1：LLM 请求读取文件
│
├── Security: 输入过滤 → PASS
├── Security: 数据流记录 → 记录"即将读取 filesystem"
├── Connection: 执行 read_file(".env")
├── Security: 输出过滤
│   └── 检测到返回中包含 DATABASE_URL、JWT_SECRET
│   └── 标记：data_contains_secrets = True
│   └── 输出：正常返回（加警告标记）
│
└── 会话上下文更新：
    last_read = { source: "filesystem", contains_secrets: True }


调用 #2：LLM 请求抓取网页
│
├── Security: 数据流管控
│   └── 检查：上一个调用读了敏感文件
│   └── 检查：当前调用目标是网络上游 (fetch-1)
│   └── 检查：参数中是否包含敏感数据？
│       ├── 包含 → BLOCK：禁止将敏感数据发送到外部
│       └── 不包含 → PASS（但记录警告）
│
└── ...
```

---

## 四、核心机制

### 4.1 能力发现与注册机制

**目标：让 LLM 感知上游能力，同时最小化上下文占用。**

```
三层信息架构：

┌───────────────────────────────────────────┐
│ Layer 1: 摘要（始终可见，~200 tokens）      │
│                                           │
│ "Available upstream capabilities:"         │
│ "- fetch-1: 网页抓取 (2 tools)"            │
│ "- memory-1: 知识图谱存储 (9 tools)"       │
│ "- filesystem: 文件操作 (14 tools)"        │
│ "- context7: 文档查询 (2 tools)"           │
│ "- reasoning: 分步推理 (1 tool)"           │
│ "- learn: MCP 学习 (20 tools)"            │
│                                           │
│ → 让 LLM 知道有什么                        │
│ → 不包含参数、schema 等细节                 │
└───────────────────────────────────────────┘
          │
          │ analyze_user_task
          ▼
┌───────────────────────────────────────────┐
│ Layer 2: 推荐（按需加载，~500 tokens）      │
│                                           │
│ {                                         │
│   "recommendations": [                    │
│     {                                     │
│       "capability_id": "fetch-1.tools.fetch",│
│       "name": "fetch",                    │
│       "summary": "抓取 URL 内容",          │
│       "confidence": 0.95,                 │
│       "params": {                         │
│         "url": "string (required)",       │
│         "max_length": "int (optional)"    │
│       }                                   │
│     }                                     │
│   ],                                      │
│   "route_token": "route_xxx"              │
│ }                                         │
│                                           │
│ → 让 LLM 知道怎么用                        │
│ → 精简参数（类型 + 是否必填）               │
└───────────────────────────────────────────┘
          │
          │ call_upstream_tool（首次调用时）
          ▼
┌───────────────────────────────────────────┐
│ Layer 3: 完整 Schema（按需加载，~300 tokens）│
│                                          │
│ 完整的 JSON Schema 定义                    │
│ 包含所有校验规则、默认值、描述              │
│                                          │
│ → 仅在 LLM 需要精确构造参数时加载          │
└───────────────────────────────────────────┘
```

### 4.2 推荐引擎机制

**目标：从所有能力中筛选出最相关的 2~3 个。**

```
推荐流程：

analyze_user_task("抓取 https://example.com 的内容")
│
├── Step 1: 任务预处理
│   ├── 提取关键词：["抓取", "https", "example.com", "内容"]
│   ├── 分类意图：category = "web"
│   └── 识别实体：url = "https://example.com"
│
├── Step 2: 候选缩小
│   ├── 按 category="web" 过滤注册表 → 2 个候选
│   │   ├── fetch-1.tools.fetch
│   │   └── fetch-1.prompts.fetch
│   └── 按 tool_hint="fetch"（如果提供）进一步缩小
│
├── Step 3: 相关性评分
│   ├── fetch-1.tools.fetch
│   │   ├── 关键词匹配：0.8（"抓取"匹配 description）
│   │   ├── 分类匹配：1.0（精确匹配 web 类）
│   │   └── 综合得分：0.95
│   │
│   └── fetch-1.prompts.fetch
│       ├── 关键词匹配：0.6
│       ├── 分类匹配：0.8
│       └── 综合得分：0.68
│
├── Step 4: 过滤和排序
│   ├── 过滤：得分 < 0.3 的丢弃
│   ├── 排序：按得分降序
│   └── 截断：只保留 top 3
│
└── Step 5: 生成 route_token
    └── 为每个推荐生成一次性 route_token
```

### 4.3 会话缓存机制

**目标：避免重复分析和发现。**

```
缓存结构：

SessionCache
├── _task_pattern_cache: dict    # {任务模式: capability_id}
│   ├── "fetch_web_page" → "fetch-1.tools.fetch"
│   ├── "list_directory" → "filesystem-project.tools.list_directory"
│   └── "query_docs"     → "context7.tools.query-docs"
│
├── _schema_cache: dict          # {capability_id: schema}
│   ├── "fetch-1.tools.fetch" → {...}
│   └── ...
│
└── _route_token_cache: dict     # {capability_id: route_token}
    ├── "fetch-1.tools.fetch" → "route_xxx"
    └── ...


缓存策略：

┌──────────────────┐     缓存命中     ┌──────────────┐
│  LLM 发起调用     │───────────────▶│  直接调用上游  │
│  execute_task()  │                │  (跳过 analyze)│
└──────┬───────────┘                └──────────────┘
       │ 缓存未命中
       ▼
┌──────────────────┐     执行分析    ┌──────────────┐
│  analyze_user    │───────────────▶│  写入缓存     │
│  _task()         │                │  + 调用上游    │
└──────────────────┘                └──────────────┘


缓存失效条件：
  - TTL 过期（默认 5 分钟）
  - 上游不可用（健康检查失败）
  - 配置变更（热更新时清空缓存）
  - 调用失败（该 capability 的缓存条目失效）
```

### 4.4 熔断器机制

**目标：保护频繁失败的上游，避免资源浪费。**

```
状态机详解：

                    连续失败 < 阈值
           ┌────────────────────────────┐
           │                            │
           ▼    连续失败 ≥ 阈值(5次)     │
      ┌─────────┐ ────────────────▶ ┌────────┐
      │ CLOSED  │                   │  OPEN  │
      │ (正常)   │                   │ (熔断)  │
      └─────────┘ ◀───────────────  └────┬───┘
           ▲      成功恢复(探针)         │
           │                            │ 冷却期(60s)
           │                            ▼
           │                       ┌────────────┐
           └───────────────────────│ HALF_OPEN  │
              探针成功             │ (试探)      │
                                   └────────────┘
                                        │
                                   探针失败
                                        │
                                        ▼
                                   ┌────────┐
                                   │  OPEN  │
                                   └────────┘

每个上游独立维护自己的熔断器：

upstream_circuits = {
    "fetch-1":                CircuitBreaker(threshold=3, recovery=30s),
    "memory-1":               CircuitBreaker(threshold=5, recovery=60s),
    "filesystem-project":     CircuitBreaker(threshold=5, recovery=60s),
    "context7":               CircuitBreaker(threshold=3, recovery=30s),
    "sequential-thinking-1":  CircuitBreaker(threshold=5, recovery=120s),
    "learn-mcp-server":       CircuitBreaker(threshold=5, recovery=60s),
}
```

---

## 五、模块交互时序

### 5.1 标准调用时序（execute_task）

```
LLM          Tool层       Router层      Security层    Connection层    上游MCP
 │             │             │              │              │             │
 │ execute_task│             │              │              │             │
 │────────────▶│             │              │              │             │
 │             │             │              │              │             │
 │             │ query_cache │              │              │             │
 │             │────────────▶│              │              │             │
 │             │  cache MISS │              │              │             │
 │             │◀────────────│              │              │             │
 │             │             │              │              │             │
 │             │ analyze     │              │              │             │
 │             │────────────▶│              │              │             │
 │             │             │ classify     │              │             │
 │             │             │──────┐       │              │             │
 │             │             │◀─────┘       │              │             │
 │             │             │              │              │             │
 │             │             │ search + rank│              │             │
 │             │             │──────┐       │              │             │
 │             │             │◀─────┘       │              │             │
 │             │             │              │              │             │
 │             │  recommend  │              │              │             │
 │             │◀────────────│              │              │             │
 │             │             │              │              │             │
 │             │             │              │ check_input  │             │
 │             │             │              │──────┐       │             │
 │             │             │              │◀─────┘       │             │
 │             │             │              │ check_rate   │             │
 │             │             │              │──────┐       │             │
 │             │             │              │◀─────┘       │             │
 │             │             │              │ check_flow   │             │
 │             │             │              │──────┐       │             │
 │             │             │              │◀─────┘ PASS  │             │
 │             │             │              │              │             │
 │             │             │              │              │ check_circuit│
 │             │             │              │              │──────┐      │
 │             │             │              │              │◀─────┘ OK   │
 │             │             │              │              │             │
 │             │             │              │              │ call_tool   │
 │             │             │              │              │────────────▶│
 │             │             │              │              │             │
 │             │             │              │              │   result    │
 │             │             │              │              │◀────────────│
 │             │             │              │              │             │
 │             │             │              │ filter_output│             │
 │             │             │              │──────┐       │             │
 │             │             │              │◀─────┘ PASS  │             │
 │             │             │              │              │             │
 │             │             │              │ audit_log    │             │
 │             │             │              │──────┐       │             │
 │             │             │              │◀─────┘       │             │
 │             │             │              │              │             │
 │             │ update_cache│              │              │             │
 │             │────────────▶│              │              │             │
 │             │             │              │              │             │
 │   result    │             │              │              │             │
 │◀────────────│             │              │              │             │
```

### 5.2 缓存命中时序（快速路径）

```
LLM          Tool层       Router层      Connection层    上游MCP
 │             │             │              │             │
 │ execute_task│             │              │             │
 │────────────▶│             │              │             │
 │             │             │              │             │
 │             │ query_cache │              │             │
 │             │────────────▶│              │             │
 │             │  cache HIT  │              │             │
 │             │◀────────────│              │             │
 │             │             │              │             │
 │             │             │              │ call_tool   │
 │             │             │              │────────────▶│
 │             │             │              │   result    │
 │             │             │              │◀────────────│
 │             │             │              │             │
 │   result    │             │              │             │
 │◀────────────│             │              │             │

  跳过了：分析、推荐、安全入站检查
  只保留：安全出站检查 + 审计日志
```

### 5.3 上游不可用时序（降级）

```
LLM        Tool层     Router层   Security   Connection   上游A   降级方案
 │           │           │          │          │          │       │
 │ execute   │           │          │          │          │       │
 │──────────▶│           │          │          │          │       │
 │           │ analyze   │          │          │          │       │
 │           │──────────▶│          │          │          │       │
 │           │ recommend │          │          │          │       │
 │           │◀──────────│          │          │          │       │
 │           │           │          │          │          │       │
 │           │           │          │          │ check    │       │
 │           │           │          │          │ circuit  │       │
 │           │           │          │          │──────┐   │       │
 │           │           │          │          │◀─────┘   │       │
 │           │           │          │          │ OPEN!    │       │
 │           │           │          │          │          │       │
 │           │           │          │          │ fallback │       │
 │           │           │          │          │─────────────────▶│
 │           │           │          │          │          │       │
 │           │           │          │          │ 降级结果  │       │
 │           │◀──────────│──────────│──────────│─────────────────│
 │ 降级结果   │           │          │          │          │       │
 │◀──────────│           │          │          │          │       │
 │           │           │          │          │          │       │
 │ (附带警告：│           │          │          │          │       │
 │  上游A不可用│           │          │          │          │       │
 │  已使用    │           │          │          │          │       │
 │  降级方案) │           │          │          │          │       │
```

---

## 六、配置体系

### 6.1 配置层次

```
优先级（高 → 低）：

① 环境变量
   CONDUCTOR_LOG_LEVEL=DEBUG
   CONDUCTOR_TIMEOUT_DEFAULT=20

② 命令行参数
   --config ./my-config.yaml

③ 项目配置文件
   ./mcp-conductor.yaml

④ 用户目录配置
   ~/.config/mcp-conductor/default.yaml

⑤ 内置默认值
   conductor 的代码默认值


合并规则：
  高优先级的值覆盖低优先级的值
  数组类型：合并而非覆盖
  对象类型：深度合并
```

### 6.2 配置结构

```yaml
# mcp-conductor.yaml

# 基础配置
conductor:
  name: "mcp-conductor"
  version: "0.2.0"
  log_level: "INFO"                  # DEBUG / INFO / WARNING / ERROR
  log_format: "json"                 # json / text

# 能力发现配置
discovery:
  summary:
    enabled: true                    # 启用能力摘要注册
    max_length_per_upstream: 100     # 每个上游摘要最大字符数

  recommendation:
    max_results: 3                   # 每次最多返回几个推荐
    min_confidence: 0.3              # 最低置信度阈值
    detail_level: "compact"          # full / compact / minimal
    include_schema: true             # 是否包含参数 schema

  cache:
    enabled: true
    ttl_seconds: 300                 # 缓存有效期
    max_entries: 50                  # 最大缓存条目数

# 上游 MCP 配置
upstreams:
  - id: "fetch-1"
    enabled: true
    type: "stdio"                    # stdio / http / sse
    command: "npx"
    args: ["-y", "@anthropic/mcp-fetch"]
    trust_level: "community"         # verified / community / untrusted
    timeout_seconds: 30
    retry:
      max_attempts: 2
      backoff_ms: 1000
    circuit_breaker:
      failure_threshold: 3
      recovery_timeout_seconds: 30
    fallback:
      enabled: true
      chain: ["builtin:WebFetch", "bash:curl -s {url}"]

  - id: "memory-1"
    enabled: true
    type: "stdio"
    command: "npx"
    args: ["-y", "@modelcontextprotocol/server-memory"]
    trust_level: "verified"
    timeout_seconds: 5

  # ... 更多上游

# 安全配置
security:
  enabled: true                      # 全局开关

  input_filter:
    enabled: true
    checks:
      - type: "path_traversal"
        action: "block"
      - type: "url_validation"
        action: "block"
      - type: "injection_pattern"
        action: "block"

  output_filter:
    enabled: true
    checks:
      - type: "prompt_injection"
        action: "redact"             # block / redact / warn
      - type: "sensitive_data"
        action: "mask"
    max_response_size: 100000        # 最大响应字节数

  data_flow:
    enabled: true
    rules:
      - name: "prevent_exfiltration"
        from_category: ["file", "memory"]
        to_category: ["web"]
        condition: "contains_sensitive_data"
        action: "block"

  rate_limit:
    enabled: true
    max_calls_per_minute: 30
    max_calls_per_session: 200
    loop_detection: true
    max_identical_calls: 3
    cooldown_seconds: 30

  audit:
    enabled: true
    output_path: "./logs/audit.jsonl"
    log_arguments: true
    mask_sensitive: true
    log_response_summary: true       # 只记录大小和状态，不记录内容

# 健康检查
health:
  enabled: true
  check_interval_seconds: 30
  failure_threshold: 3

# 连接管理
connection:
  max_concurrent_calls: 10           # 最大并发调用数
  graceful_shutdown_timeout: 10      # 优雅关闭超时（秒）
```

---

## 七、状态管理

### 7.1 状态分类

```
┌─────────────────────────────────────────────────────────┐
│                    状态分类                                │
│                                                         │
│  ① 进程级状态（单次运行生命周期）                            │
│  ├── 能力注册表（启动时构建，运行时更新）                     │
│  ├── 连接池（每个上游的连接状态）                            │
│  ├── 熔断器状态（每个上游的 CLOSED/OPEN/HALF_OPEN）         │
│  └── 健康状态（每个上游的 healthy/unhealthy）                │
│                                                         │
│  ② 会话级状态（单个 MCP 会话生命周期）                       │
│  ├── 会话缓存（已发现的能力、route_token）                   │
│  ├── 调用历史（用于数据流追踪）                              │
│  ├── 速率计数器（当前分钟的调用次数）                        │
│  └── 累积风险评分                                          │
│                                                         │
│  ③ 持久化状态（跨会话）                                    │
│  ├── 审计日志（写入磁盘）                                   │
│  ├── 性能指标（Prometheus 格式）                            │
│  └── 错误统计（用于熔断决策）                               │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### 7.2 状态流转

```
启动
│
├── 加载配置
├── 连接上游 → [connected / failed]
├── 发现能力 → [registered / skipped]
├── 生成摘要 → [ready]
│
├── 等待调用
│   ├── 收到请求 → [analyzing → recommending → calling → responding]
│   ├── 上游掉线 → [unhealthy → circuit_open]
│   ├── 上游恢复 → [healthy → circuit_half_open → circuit_closed]
│   └── 配置变更 → [reloading → updated / rollback]
│
└── 关闭
    ├── 等待进行中的调用完成
    ├── 断开所有上游连接
    └── 写入最终审计日志
```

---

## 八、错误处理架构

### 8.1 错误分类体系

```
ConductorError（基类）
│
├── InputError（输入错误，4xx 类）
│   ├── InvalidArgumentsError     # 参数不合法
│   ├── CapabilityNotFoundError   # 工具不存在
│   ├── PathSecurityError         # 文件路径不安全
│   ├── UrlSecurityError          # URL 不合法
│   └── InjectionDetectedError    # 检测到注入攻击
│
├── SecurityError（安全错误）
│   ├── DataFlowBlockedError      # 数据流被阻断
│   ├── RateLimitExceededError    # 超出速率限制
│   ├── LoopDetectedError         # 检测到循环调用
│   └── RiskThresholdExceededError # 累积风险超限
│
├── UpstreamError（上游错误，5xx 类）
│   ├── UpstreamUnavailableError   # 上游不可用（熔断/掉线）
│   ├── UpstreamTimeoutError       # 上游超时
│   ├── UpstreamResponseError      # 上游返回错误
│   ├── CircuitOpenError          # 熔断器开启
│   └── AllFallbacksFailedError   # 所有降级方案失败
│
├── InternalError（内部错误）
│   ├── ConfigError               # 配置错误
│   ├── DiscoveryError            # 能力发现失败
│   └── CacheError                # 缓存异常
│
└── OutputSecurityError（输出安全）
    ├── PromptInjectionWarning     # 输出包含可疑内容（已清理）
    └── SensitiveDataWarning       # 输出包含敏感数据（已掩码）
```

### 8.2 错误传播

```
上游返回错误
│
├── Connection 层捕获
│   ├── 转换为 UpstreamError 子类
│   ├── 记录到审计日志
│   ├── 更新熔断器状态
│   └── 更新健康状态
│
├── Security 层处理
│   ├── 敏感错误信息脱敏
│   └── 添加安全建议
│
├── Router 层处理
│   ├── 缓存失效（该 capability）
│   └── 检查是否有降级方案
│       ├── 有降级 → 尝试降级
│       └── 无降级 → 继续传播
│
└── Tool 层格式化
    └── 返回统一错误格式给 LLM
        {
          "status": "error",
          "error": {
            "code": "UPSTREAM_TIMEOUT",
            "message": "fetch-1 在 30 秒内未响应",
            "category": "network",
            "suggestion": "可以稍后重试",
            "retry_possible": true
          }
        }
```

---

## 九、上下文效率设计

### 9.1 Token 预算分配

```
Conductor 在 LLM 上下文中的占用预算：2000 tokens

分配方案：

┌─────────────────────────────────────────────┐
│  固定占用（每次会话）：~500 tokens            │
│                                             │
│  - conductor 工具 schema（~300 tokens）      │
│    共 4~6 个工具的名称和参数定义              │
│                                             │
│  - 能力摘要（~200 tokens）                   │
│    6 个上游 × ~30 tokens/个                  │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│  动态占用（按需）：~1500 tokens               │
│                                             │
│  - 每次 analyze 返回：~300~500 tokens        │
│    2~3 个推荐 × ~100~150 tokens/个           │
│                                             │
│  - 每次 call 返回的 meta：~50 tokens         │
│                                             │
│  - 管理策略：                                │
│    · 同时只保留最近 2 次 analyze 的结果       │
│    · 超出预算时降级为 minimal 模式            │
│    · 缓存命中时不触发 analyze                │
└─────────────────────────────────────────────┘
```

### 9.2 三级信息精度

```
                    ┌─────────────┐
                    │   Minimal   │ ← 预算紧张时
                    │  (50 tokens)│
                    │             │
                    │  只有工具名  │
                    │  和 route   │
                    │  token      │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │   Compact   │ ← 默认模式
                    │ (150 tokens)│
                    │             │
                    │  工具名     │
                    │  一句话描述  │
                    │  参数名+类型 │
                    │  置信度     │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │    Full     │ ← 首次使用时
                    │ (300 tokens)│
                    │             │
                    │  完整描述   │
                    │  完整 schema│
                    │  使用示例   │
                    │  注意事项   │
                    └─────────────┘

根据上下文预算自动切换：
  预算 > 1000 tokens → Compact 模式
  预算 > 2000 tokens → Full 模式（首次）
  预算 < 500 tokens  → Minimal 模式
```

---

## 十、与 Claude Code 的集成边界

### 10.1 职责划分

```
┌─────────────────────────────────────────────────────────────┐
│                    Claude Code 负责                           │
│                                                             │
│  ✅ 工具 schema 的懒加载（ToolSearch）                       │
│  ✅ LLM 推理和工具选择                                       │
│  ✅ 上下文管理和对话压缩                                      │
│  ✅ 文件系统操作（Read / Write / Edit / Bash）                │
│  ✅ MCP Server 进程管理（启动/停止/重启）                     │
│  ✅ 用户权限确认（危险操作时询问用户）                         │
│                                                             │
│  ❌ 不知道 conductor 背后有哪些上游                           │
│  ❌ 不做数据流分析                                            │
│  ❌ 不做跨 MCP 的安全检查                                     │
│  ❌ 不做跨 MCP 的审计                                        │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                   mcp-conductor 负责                          │
│                                                             │
│  ✅ 上游 MCP 的连接和生命周期管理                              │
│  ✅ 能力发现和注册                                            │
│  ✅ 任务分析和工具推荐                                        │
│  ✅ 调用路由和安全检查                                        │
│  ✅ 审计日志                                                 │
│  ✅ 健康检查、熔断、降级                                      │
│                                                             │
│  ❌ 不做 LLM 推理                                            │
│  ❌ 不直接操作文件系统                                        │
│  ❌ 不管理自己的进程（由 Claude Code 管理）                    │
│  ❌ 不决定最终使用哪个工具（由 LLM 决定）                      │
└─────────────────────────────────────────────────────────────┘
```

### 10.2 通信协议

```
Claude Code ◀─────────────────▶ mcp-conductor

传输方式：stdio（标准输入输出）

Claude Code → conductor:
  JSON-RPC 2.0 请求
  {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "execute_task",
      "arguments": {
        "task": "抓取网页",
        "arguments": {"url": "https://example.com"}
      }
    }
  }

conductor → Claude Code:
  JSON-RPC 2.0 响应
  {
    "jsonrpc": "2.0",
    "id": 1,
    "result": {
      "content": [
        {
          "type": "text",
          "text": "{\"status\":\"success\",\"data\":{...},\"meta\":{...}}"
        }
      ]
    }
  }
```

### 10.3 启动与关闭流程

```
启动：

Claude Code                    mcp-conductor
    │                              │
    │  启动子进程                    │
    │─────────────────────────────▶│
    │                              │ 加载配置
    │                              │ 连接上游 MCP
    │                              │ 发现能力
    │                              │ 生成摘要
    │                              │ 启动健康检查
    │                              │
    │  initialize（MCP 握手）        │
    │─────────────────────────────▶│
    │                              │
    │  返回工具列表 + 能力摘要       │
    │◀─────────────────────────────│
    │                              │
    │  就绪                         │


关闭：

Claude Code                    mcp-conductor
    │                              │
    │  用户退出 / Ctrl+C            │
    │                              │
    │  发送 SIGTERM                 │
    │─────────────────────────────▶│
    │                              │ 停止接受新调用
    │                              │ 等待进行中的调用完成（最多 10s）
    │                              │ 写入最终审计日志
    │                              │ 断开上游连接
    │                              │ 进程退出
    │◀─────────────────────────────│
    │                              │
```

---

## 附录 A：与现有文档的关系

```
mcp-conductor-issues.md
  "有什么问题"
  → 22 个已发现的问题
  → 测试数据
  → 问题优先级

mcp-conductor-recommendations.md
  "怎么改"
  → 具体改进方案
  → 代码示例
  → 开发路线图

mcp-conductor-architecture.md（本文档）
  "应该长什么样"
  → 组件设计
  → 数据流
  → 状态管理
  → 与 Claude Code 的集成边界
```

## 附录 B：关键数据结构

```python
# 能力
@dataclass
class Capability:
    capability_id: str         # "fetch-1.tools.fetch"
    upstream_id: str           # "fetch-1"
    capability_type: str       # "tool" / "resource" / "prompt"
    name: str                  # "fetch"
    summary: str               # "网页抓取" ← 摘要用
    description: str           # 完整描述 ← 推荐用
    input_schema: dict         # JSON Schema ← 调用用
    risk_level: str            # "read_only" / "mutating" / "destructive"
    category: str              # "web" / "file" / "memory" / "docs" / "reasoning"
    tags: list[str]            # ["http", "fetch"]
    trust_level: str           # "verified" / "community" / "untrusted"
    available: bool            # 上游是否可用

# 推荐结果
@dataclass
class Recommendation:
    capability_id: str
    confidence: float          # 0.0 ~ 1.0
    reason: str                # 推荐理由
    params_summary: dict       # 精简参数 {"url": "string (required)"}
    route_token: str           # 一次性路由令牌

# 调用结果
@dataclass
class CallResult:
    status: str                # "success" / "error" / "partial_success"
    data: Any                  # 上游返回的数据
    error: Optional[ErrorInfo] # 错误信息（如果失败）
    meta: CallMeta             # 元信息

@dataclass
class CallMeta:
    upstream_id: str
    capability_id: str
    latency_ms: int
    from_cache: bool
    fallback_used: bool
    security_flags: list[str]  # 安全标记
    trust_level: str           # 输出信任等级

# 健康状态
@dataclass
class HealthStatus:
    healthy: bool
    last_check: datetime
    last_error: Optional[str]
    consecutive_failures: int
    response_time_ms: Optional[int]

# 审计事件
@dataclass
class AuditEvent:
    timestamp: datetime
    event_type: str            # "tool.call" / "security.block" / ...
    session_id: str
    upstream_id: str
    capability_id: str
    status: str
    latency_ms: int
    security_flags: list[str]
    arguments_redacted: str    # 脱敏后的参数
```
