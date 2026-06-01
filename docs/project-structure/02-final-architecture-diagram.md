# 最终目标架构图

这份文档记录 `mcp-conductor` 最终要实现的 MCP Gateway Server 架构图。

核心定位保持不变：

```text
对外：标准 MCP Server
对内：上游 Client 管理器 + 能力路由 + 网关执行 + 结果管理
```

## 总体拓扑

```mermaid
flowchart LR
    User["用户"]
    Host["外部 MCP Host<br/>Codex / Claude Code / Cursor"]
    Model["外部大模型<br/>由 Host 管理"]
    ExternalClient["Host 内部 MCP Client<br/>连接 mcp-conductor"]

    Conductor["mcp-conductor<br/>对外：MCP Server<br/>对内：MCP Gateway"]

    UpstreamClientA["上游 Client A"]
    UpstreamClientB["上游 Client B"]
    UpstreamClientC["上游 Client C"]

    ServerA["GitHub MCP 服务"]
    ServerB["filesystem MCP 服务"]
    ServerC["数据库 / 搜索 / 其他 MCP 服务"]

    User --> Host
    Host --> Model
    Model --> Host
    Host --> ExternalClient
    ExternalClient --> Conductor

    Conductor --> UpstreamClientA
    Conductor --> UpstreamClientB
    Conductor --> UpstreamClientC

    UpstreamClientA --> ServerA
    UpstreamClientB --> ServerB
    UpstreamClientC --> ServerC
```

要点：

- 外部 Host 只把 `mcp-conductor` 当作一个普通 MCP Server。
- 外部大模型只看到 `mcp-conductor` 暴露的少量高级 tools。
- `mcp-conductor` 内部为每个上游 MCP Server 维护独立 Client/session。
- 上游 MCP Server 的大量底层 tools/resources/resource templates/prompts 不直接暴露给外部大模型。

## 内部模块架构

```mermaid
flowchart TB
    subgraph Entry["入口层"]
        CLI["cli.py<br/>命令行入口"]
        Server["server.py<br/>FastMCP 服务"]
        PublicTools["public_tools<br/>对外 MCP 工具"]
    end

    subgraph Runtime["网关运行时"]
        Gateway["GatewayRuntime<br/>内部协调层"]
    end

    subgraph Core["核心能力层"]
        Config["config<br/>配置加载 / env 解析 / schema"]
        Upstream["upstream<br/>上游 Client / session / lifecycle"]
        Discovery["discovery<br/>tools/resources/prompts 发现"]
        Registry["registry<br/>能力注册表 / 工具卡片"]
        Routing["routing<br/>规则推荐 / Host 采样路由器"]
        Execution["execution<br/>调用前校验 / 上游工具执行"]
        Policy["policy<br/>risk_policy / confirmation / roots"]
        Results["results<br/>summary / preview / result_id / pagination"]
        Primitives["primitives<br/>Host 原语适配器<br/>上游原语桥接"]
        Observability["observability<br/>logging / progress"]
    end

    CLI --> Server
    Server --> PublicTools
    PublicTools --> Gateway

    Gateway --> Config
    Gateway --> Upstream
    Gateway --> Discovery
    Gateway --> Registry
    Gateway --> Routing
    Gateway --> Execution
    Gateway --> Policy
    Gateway --> Results
    Gateway --> Primitives
    Gateway --> Observability

    Discovery --> Upstream
    Discovery --> Registry
    Routing --> Registry
    Routing --> Policy
    Execution --> Registry
    Execution --> Policy
    Execution --> Upstream
    Execution --> Results
    Policy --> Primitives
    Upstream --> Primitives
```

边界规则：

- `server.py` 只负责创建 FastMCP 服务和注册对外工具。
- `public_tools` 只调用 `GatewayRuntime`，不直接访问上游 Client。
- `routing` 只负责推荐能力，不执行工具。
- `execution` 必须经过推荐凭证、schema、risk policy、Roots/allowlist 校验后才能调用上游工具。
- `policy` 不依赖 FastMCP。
- `results` 不调用上游工具。
- `primitives` 只处理协议协作能力，不负责业务路由。

## 对外工具

第一版对外暴露的 MCP tools：

```mermaid
flowchart LR
    Host["外部 Host / Model"]
    Tools["mcp-conductor 对外工具"]

    List["list_upstream_capabilities"]
    Recommend["recommend_capabilities"]
    Call["call_upstream_tool"]
    Read["read_result"]

    Host --> Tools
    Tools --> List
    Tools --> Recommend
    Tools --> Call
    Tools --> Read
```

各工具职责：

- `list_upstream_capabilities`：分页列出能力摘要，不返回完整内部状态。
- `recommend_capabilities`：根据用户任务返回候选能力、schema、`recommendation_id` 和 `route_token`。
- `call_upstream_tool`：只调用已推荐、已校验、风险策略允许的上游 tool。
- `read_result`：读取当前 session 可访问的缓存结果。

## 推荐与执行链路

```mermaid
sequenceDiagram
    participant User as 用户
    participant Host as 外部 Host
    participant Model as 外部大模型
    participant Conductor as mcp-conductor
    participant Registry as 能力注册表
    participant Policy as 策略引擎
    participant Upstream as 上游 MCP Server
    participant Results as 结果管理器

    User->>Host: 提出任务
    Host->>Model: 构建上下文并暴露 mcp-conductor tools
    Model->>Host: 工具调用意图 recommend_capabilities
    Host->>Conductor: recommend_capabilities(user_task, context_summary)
    Conductor->>Registry: 查询能力卡片
    Conductor->>Policy: 过滤禁用和明显危险能力
    Conductor-->>Host: recommendation_id + route_token + candidates + schema

    Host->>Model: 将推荐结果放回上下文
    Model->>Host: 工具调用意图 call_upstream_tool
    Host->>Conductor: call_upstream_tool(recommendation_id, route_token, capability_id, arguments)

    Conductor->>Policy: 校验推荐凭证 / schema / risk_policy / Roots

    alt 只读且策略允许
        Conductor->>Upstream: tools/call
        Upstream-->>Conductor: 原始结果
        Conductor->>Results: summary / preview / result_id
        Results-->>Conductor: 整理后的结果
        Conductor-->>Host: summary + preview + optional result_id
    else 危险或未知风险
        Conductor-->>Host: confirmation_required 或 Elicitation 请求
    end

    Host->>Model: 工具结果回填上下文
    Model-->>Host: 最终回答
    Host-->>User: 展示回答
```

## 危险操作确认链路

```mermaid
flowchart TB
    Request["call_upstream_tool 请求"]
    Validate["校验 recommendation_id<br/>route_token<br/>schema<br/>capability_id"]
    Risk["风险判断<br/>risk_policy + allowlist + roots<br/>工具名/描述规则 + 用户配置"]
    Safe["允许自动执行"]
    Elicit["优先请求 Elicitation<br/>由外部 Host 收集用户确认"]
    Pending["Host 不支持 Elicitation<br/>返回 confirmation_required<br/>pending_action_id"]
    Execute["调用上游 tools/call"]
    Reject["拒绝执行"]

    Request --> Validate
    Validate --> Risk
    Risk -->|只读且策略允许| Safe
    Risk -->|写入 / 删除 / 发送 / 支付 / 未知风险| Elicit
    Safe --> Execute
    Elicit -->|用户 accept| Execute
    Elicit -->|用户 decline / cancel| Reject
    Elicit -->|Host 不支持| Pending
    Pending -->|二次调用且 pending_action_id 有效| Execute
    Pending -->|超时 / 参数变化 / confirmed=true| Reject
```

关键约束：

- `read_only_hint` 只能作为提示，不能单独作为自动执行依据。
- 未知风险能力默认按危险处理。
- `pending_action_id` 必须不透明、不可猜测、有过期时间。
- 二次确认时参数不能变化。
- 不能用普通 `confirmed=true` 替代 `pending_action_id`。

## 客户端原语双向边界

```mermaid
flowchart LR
    subgraph ExternalSide["外部方向：mcp-conductor 作为 Server"]
        ConductorServer["mcp-conductor 服务"]
        ExternalHost["外部 Host / Client"]
        ConductorServer -->|"请求 Sampling / Roots / Elicitation"| ExternalHost
        ExternalHost -->|"支持 / 拒绝 / 用户批准 / 结果"| ConductorServer
    end

    subgraph UpstreamSide["上游方向：mcp-conductor 作为 Client"]
        UpstreamServer["上游 MCP Server"]
        Bridge["上游原语桥接"]
        ConductorClient["mcp-conductor 上游 Client"]
        UpstreamServer -->|"请求 Sampling / Roots / Elicitation"| ConductorClient
        ConductorClient --> Bridge
        Bridge -->|"拒绝 / 受限返回 / 安全转发"| ConductorClient
        ConductorClient --> UpstreamServer
    end
```

第一版策略：

- 外部方向可以请求 Sampling、Roots、Elicitation，但是否支持和批准由外部 Host 决定。
- 上游方向不能无条件透传上游 Server 的请求。
- 上游 Sampling 默认拒绝或返回 unsupported。
- 上游 Roots 只能返回 Host Roots 与内部 allowlist 的受限交集。
- 上游 Elicitation 不允许索要 token、密码、密钥。

## 运行形态

```mermaid
flowchart TB
    Local["第一版默认：本地 stdio"]
    Future["后续可扩展：streamable HTTP / 远程部署"]

    HostLocal["本机 Host<br/>启动 mcp-conductor 进程"]
    ConductorLocal["mcp-conductor<br/>stdio transport"]

    HostRemote["外部 Host"]
    ConductorRemote["mcp-conductor<br/>HTTP 服务"]

    Local --> HostLocal
    HostLocal --> ConductorLocal

    Future --> HostRemote
    HostRemote --> ConductorRemote
```

当前第一版优先本地 `stdio`：

- 适合 Codex、Claude Code、Cursor 等本地开发工具。
- Host 启动 `mcp-conductor` 进程。
- Host 通过标准输入/输出与 MCP Server 通信。

后续如果支持远程部署，需要补充：

- HTTP 传输配置。
- 鉴权和访问控制。
- 多用户/session 隔离。
- 远程上游凭证管理。
- 部署文档和安全策略。

## 最终结构总结

```text
外部 Host
  -> mcp-conductor 对外工具
    -> 网关运行时
      -> 配置
      -> 上游客户端
      -> 能力发现
      -> 能力注册
      -> 能力路由
      -> 调用执行
      -> 策略控制
      -> 结果管理
      -> 原语桥接
        -> 上游 MCP Server
```

`mcp-conductor` 最终不是一个完整 Host，而是一个受外部 Host 调用的 MCP Gateway Server。它的核心价值是把大量上游 MCP Server 的能力收拢到一个受控入口里，减少外部模型直接看到的工具数量，并在执行前增加路由、安全、确认和结果管理边界。
