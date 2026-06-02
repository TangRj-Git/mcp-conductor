# 端到端完整工作流程

## 目标

这份文档描述 `mcp-conductor` 从最开始配置，到外部 Host 使用它完成一次任务的完整过程。

核心定位保持不变：

```text
外部 Host 管用户、模型、对话上下文和最终回答。
mcp-conductor 管内部上游 MCP Server、动态能力推荐、受控调用路由和结果整理。
```

`mcp-conductor` 对外是一个标准 MCP Server。它内部为每个上游 MCP Server 创建独立 MCP Client/session。

这条流程的目标是减少外部模型每轮直接看到的底层工具数量。外部模型先看到 `mcp-conductor` 的少量高级工具，再通过推荐链路获取当前任务所需的候选能力和调用凭证。

## 角色

### 外部 Host

例如 Codex、Claude Code、Cursor 或其他 MCP Host。

职责：

- 接收用户输入。
- 调用外部大模型。
- 决定是否调用 `mcp-conductor` 暴露的工具。
- 将工具结果放回模型上下文。
- 展示最终回答给用户。

### 外部大模型

运行在外部 Host 中。

职责：

- 根据用户问题决定是否调用 `mcp-conductor`。
- 根据 `mcp-conductor` 的推荐结果选择具体能力。
- 按能力类型选择对应公开工具，并填写必要参数。
- 根据工具结果生成最终回答。

### mcp-conductor

对外是 MCP Server，对内是 MCP Gateway。

职责：

- 被外部 Host 像普通 MCP Server 一样配置。
- 读取内部上游 MCP Server 配置。
- 为每个上游 MCP Server 维护独立 Client/session。
- 发现上游 MCP 能力。
- 建立能力注册表。
- 根据用户任务推荐候选能力。
- 校验能力、参数、风险策略和推荐凭证。
- 调用对应上游 MCP Server。
- 对结果做摘要、裁剪、缓存和分页。

### 上游 MCP Server

例如 GitHub、filesystem、database、browser/search 等 MCP Server。

职责：

- 暴露自己的 tools/resources/resource templates/prompts。
- 接收 `mcp-conductor` 内部上游 Client 的调用。
- 返回原始结果。

## 阶段 1：外部 Host 配置

外部 Host 只配置 `mcp-conductor`：

```json
{
  "mcpServers": {
    "mcp-conductor": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "E:\\SoftwareProject\\mcp-conductor",
        "mcp-conductor"
      ]
    }
  }
}
```

推荐不要把上游 MCP Server 同时直接配置到外部 Host 中。

推荐：

```text
外部 Host
  └─ mcp-conductor
```

不推荐：

```text
外部 Host
  ├─ mcp-conductor
  ├─ github MCP Server
  ├─ filesystem MCP Server
  └─ database MCP Server
```

不推荐的原因：

- 外部模型仍然会看到大量底层工具。
- 外部模型可能绕过 `mcp-conductor`。
- 同一个上游 Server 可能被启动多次。
- 写入类操作可能重复执行。
- 固定端口上游服务可能发生端口冲突。

## 阶段 2：mcp-conductor 内部上游配置

`mcp-conductor` 有自己的上游配置文件。

示例：

```json
{
  "upstreamServers": {
    "github": {
      "transport": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_TOKEN": "${GITHUB_TOKEN}"
      },
      "cwd": "E:\\SoftwareProject\\mcp-conductor",
      "disabled": false,
      "risk_policy": "read_only_only"
    },
    "filesystem": {
      "transport": "stdio",
      "command": "npx",
      "args": [
        "-y",
        "@modelcontextprotocol/server-filesystem",
        "E:\\SoftwareProject"
      ],
      "disabled": false,
      "risk_policy": "read_only_only",
      "roots_policy": "host_roots_or_config_allowlist"
    },
    "remote-search": {
      "transport": "streamable_http",
      "url": "https://example.com/mcp",
      "disabled": false,
      "risk_policy": "read_only_only"
    }
  }
}
```

配置原则：

- 凭证优先通过环境变量引用，不在配置文件里写明文 secret。
- `risk_policy` 默认使用保守策略。
- filesystem 类上游能力必须受 Roots 或 allowlist 约束。
- 固定端口 HTTP 上游服务优先使用连接已有 URL，不由 `mcp-conductor` 重复启动。

`risk_policy` 当前第一版语义：

```text
read_only_only
  默认值。只允许风险策略确认后的只读能力自动执行。

confirm_mutations
  允许发现写入/删除/发送/发布等能力，但执行前必须 Elicitation 或 pending_action_id 确认。

disabled
  该上游 Server 或能力不参与推荐和执行。
```

`read_only_hint` 只能作为提示，不能完全信任。未知风险默认按危险处理。

## 阶段 3：启动和连接

外部 Host 启动 `mcp-conductor`：

```text
外部 Host
  └─ 外部 Client ── mcp-conductor 服务
```

`mcp-conductor` 启动后读取内部上游配置。

对于每个启用的上游 Server：

```text
mcp-conductor
  ├─ 上游 Client：github ── GitHub MCP 服务
  ├─ 上游 Client：filesystem ── filesystem MCP Server
  └─ 上游 Client：remote-search ── 远程搜索 MCP Server
```

每个上游 Server 对应独立 Client/session。

启动规则：

- `disabled=true` 的上游 Server 不连接。
- stdio 上游 Server 由 `mcp-conductor` 启动并维护子进程。
- HTTP 上游 Server 优先连接已有 URL。
- 连接失败的上游 Server 标记为 `unavailable`，不阻止其他 Server 工作。
- `mcp-conductor` 关闭时必须关闭内部上游 Client/session，并清理由它启动的 stdio 子进程。

如果多个外部 Host 同时配置并启动 `mcp-conductor`，通常会得到多个独立的 `mcp-conductor` 进程。每个进程都有自己的上游 Client/session、缓存和 stdio 子进程。因此：

- stdio 上游 Server 可能被重复启动。
- 固定端口上游服务可能发生端口冲突。
- 写入类操作可能在不同 Host 中重复触发。
- `result_id`、`recommendation_id`、`pending_action_id` 不跨进程共享。

第一版不做跨 Host/跨进程协调，只在文档中明确限制。

## 阶段 4：能力发现

`mcp-conductor` 对每个上游 Server 执行能力发现：

```text
tools/list
resources/list
resources/templates/list
prompts/list
```

当前第一版完整支持发现：

```text
tools/list
resources/list
resources/templates/list
prompts/list
```

当前第一版受控访问链路：

```text
call_upstream_tool -> tools/call
read_upstream_resource -> resources/read
read_upstream_resource_template -> template expansion + resources/read
get_upstream_prompt -> prompts/get
```

发现结果进入统一能力注册表。

能力注册表记录：

```text
capability_id
capability_type
upstream_server_id
upstream_client_id
original_name_or_uri
description
schema_or_metadata
tags
risk_level
read_only_hint
enabled
```

注意：

- `read_only_hint` 只能作为提示，不能完全信任。
- 最终风险判断由 `risk_policy`、allowlist、工具名/描述规则和用户配置共同决定。
- 未知风险能力默认按危险处理。

能力描述、prompt、resource 内容、工具返回结果都必须视为不可信数据。它们可以作为检索和摘要素材，但不能覆盖 `mcp-conductor` 的系统策略、风险策略、Roots/allowlist 或调用凭证规则。

## 阶段 5：对外暴露高级工具

`mcp-conductor` 不把上游全部工具直接暴露给外部 Host。

第一版对外暴露：

```text
analyze_user_task
list_upstream_capabilities
list_exposed_capabilities
recommend_capabilities
call_upstream_tool
read_upstream_resource
read_upstream_resource_template
get_upstream_prompt
read_result
```

其中：

- `analyze_user_task`：首选入口，根据当前用户任务或 agent loop 步骤推荐候选能力，并返回下一步公开工具调用参数。
- `list_upstream_capabilities`：列出内部发现到的能力摘要，支持分页。
- `list_exposed_capabilities`：列出当前 `exposure` 配置下的 proxy/hybrid 暴露计划，目前仅用于诊断，不动态注册上游工具。
- `recommend_capabilities`：较底层推荐入口，根据用户任务推荐候选能力。
- `call_upstream_tool`：调用某个已推荐、已校验的上游 tool。
- `read_upstream_resource`：读取某个已推荐、已校验的上游 resource。
- `read_upstream_resource_template`：校验参数、展开某个已推荐的 resource template，并读取具体资源 URI。
- `get_upstream_prompt`：获取某个已推荐、已校验的上游 prompt。
- `read_result`：读取缓存的大结果分页。

第二阶段可选增加：

```text
ask_conductor
```

`ask_conductor` 必须依赖 Host Sampling，不能由 `mcp-conductor` 私自配置模型 API 密钥，也不能绕过推荐凭证、风险策略和危险操作确认。

## 阶段 6：用户发起任务

用户在外部 Host 中提问：

```text
帮我看看 PR #12 为什么 CI 失败。
```

外部 Host 调用大模型。

外部大模型看到 `mcp-conductor` 暴露的高级工具后，通常先调用：

```text
analyze_user_task
```

调用参数示例：

```json
{
  "user_task": "帮我看看 PR #12 为什么 CI 失败",
  "context_summary": "用户正在当前仓库中排查 GitHub PR CI 问题"
}
```

## 阶段 7：能力推荐

`mcp-conductor` 收到 `analyze_user_task` 或 `recommend_capabilities` 请求后：

1. 解析用户任务。
2. 使用规则和标签筛选能力。
3. 应用 `risk_policy` 和禁用规则。
4. 可选通过 Sampling 请求 Host 采样路由器做路由推理。
5. 返回推荐结果。

第一版默认不依赖 Sampling。

推荐结果不是把上游工具动态注入外部 Host 的真实工具列表，而是返回当前任务相关的紧凑候选能力、必要 schema、后续调用所需的不透明凭证，以及模型可直接继续使用的 `next_public_tool` 和 `ready_to_call_arguments`。

如果使用 Sampling：

```text
mcp-conductor
  ↓ sampling/createMessage
外部 Host
  ↓ 使用受控模型生成路由判断
mcp-conductor
```

Host 可以拒绝 Sampling，也可以要求用户确认。

如果 Sampling prompt 中包含上游工具描述、resource、prompt 或历史工具结果，必须把这些内容标记为不可信上下文，避免上游内容诱导 Router 忽略安全策略或选择错误工具。

推荐结果示例：

```json
{
  "recommendation_id": "rec_123",
  "expires_at": "2026-06-01T15:30:00+08:00",
  "recommended_capabilities": [
    {
      "capability_id": "github.tools.get_pr_checks",
      "upstream_server_id": "github",
      "capability_type": "tool",
      "name": "get_pr_checks",
      "reason": "需要查看 PR 的 CI 检查结果",
      "risk_level": "read_only",
      "input_schema": {
        "type": "object",
        "properties": {
          "pr_number": {"type": "integer"}
        },
        "required": ["pr_number"]
      },
      "example_arguments": {
        "pr_number": 12
      },
      "next_public_tool": "call_upstream_tool",
      "ready_to_call_arguments": {
        "recommendation_id": "rec_123",
        "route_token": "route_abc",
        "capability_id": "github.tools.get_pr_checks",
        "arguments": {
          "pr_number": 12
        }
      },
      "usage_hint": "Use call_upstream_tool with ready_to_call_arguments to access tool capability github.tools.get_pr_checks.",
      "route_token": "route_abc"
    }
  ]
}
```

重要规则：

- 具体访问工具只能使用当前推荐结果中的能力。
- 推荐结果必须有过期时间。
- `route_token` 是不透明 token，外部模型不能自己构造。
- 如果没有先调用 `analyze_user_task` 或 `recommend_capabilities`，具体访问工具默认拒绝。

## 阶段 8：外部模型生成调用意图和参数

外部大模型读取推荐结果后，优先使用推荐项里的 `next_public_tool` 和 `ready_to_call_arguments`。如果需要人工判断，也可以根据 `capability_type` 决定调用：

```text
call_upstream_tool
read_upstream_resource
read_upstream_resource_template
get_upstream_prompt
```

tool 调用参数示例：

```json
{
  "recommendation_id": "rec_123",
  "route_token": "route_abc",
  "capability_id": "github.tools.get_pr_checks",
  "arguments": {
    "pr_number": 12
  }
}
```

注意：

- 具体调用意图、访问工具和参数由外部大模型产生。
- `mcp-conductor` 不直接替外部模型完成最终工具调用意图。
- `mcp-conductor` 负责校验、路由、调用和结果整理。

## 阶段 9：访问前校验

`mcp-conductor` 收到具体访问工具调用后，必须校验：

```text
recommendation_id 是否存在
recommendation_id 是否过期
route_token 是否匹配
capability_id 是否属于该推荐结果
capability_type 是否匹配当前公开工具
目标能力是否仍然 enabled
arguments 是否符合 input_schema
风险策略是否允许自动执行
Roots / allowlist 是否允许访问相关路径
是否需要用户确认
```

如果校验失败，返回结构化错误，不调用上游 Server。

示例：

```json
{
  "status": "error",
  "error_code": "invalid_route_token",
  "message": "Route token is invalid or expired."
}
```

## 阶段 10：危险操作确认

如果能力是写入、删除、发送、发布、支付或其他会改变外部状态的操作，`mcp-conductor` 不能直接执行。

优先流程：

```text
mcp-conductor
  ↓ elicitation/create
外部 Host
  ↓ 展示确认信息给用户
用户 accept / decline / cancel
  ↓
外部 Host 返回结果
  ↓
mcp-conductor 决定是否继续执行
```

如果 Host 不支持 Elicitation，返回待确认记录：

```json
{
  "status": "confirmation_required",
  "pending_action_id": "pending_123",
  "expires_at": "2026-06-01T15:20:00+08:00",
  "capability_id": "filesystem.tools.delete_file",
  "risk_level": "destructive",
  "arguments_preview": {
    "path": "E:\\SoftwareProject\\demo\\old.txt"
  },
  "message": "User confirmation is required before this action can run."
}
```

二次确认规则：

- `pending_action_id` 只是待确认记录，不是确认完成凭证。
- 只有 Host Elicitation 或等价外部确认集成把该记录标记为已确认后，重新调用才可能执行。
- 确认后重新调用时必须带 `pending_action_id`。
- 参数不能变化。
- `pending_action_id` 必须有过期时间。
- 用户拒绝或超时后不得执行。
- 不能用普通 `confirmed=true` 代替 `pending_action_id`。

第一版默认只自动执行只读能力。

## 阶段 11：调用上游 MCP Server

校验通过后，`mcp-conductor` 根据能力注册表找到上游 Client：

```text
capability_id
  ↓
upstream_server_id
  ↓
upstream_client_id
  ↓
对应 MCP Client/session
```

然后通过该上游 Client 调用对应上游 Server：

```text
mcp-conductor
  ↓
上游 Client：github
  ↓
GitHub MCP 服务
```

长时间调用时：

- 可以向 Host 发送 Progress。
- 如果 Host 发送 Cancellation，`mcp-conductor` 应尝试停止内部任务和上游调用。
- 取消不保证一定成功，但必须清理内部状态。

## 阶段 12：结果整理

上游 Server 返回原始结果后，`mcp-conductor` 处理结果：

1. 判断结果大小。
2. 提取摘要。
3. 生成 preview。
4. 如果结果较大且当前 Host/transport 能提供 session id，生成 `result_id` 并缓存完整结果。
5. 返回结构化结果给外部 Host。

返回示例：

```json
{
  "status": "ok",
  "summary": "PR #12 的 CI 失败在 test-python job，失败原因是一个断言错误。",
  "preview": [
    {
      "job": "test-python",
      "status": "failed",
      "hint": "tests/test_api.py 中出现 AssertionError"
    }
  ],
  "truncated": true,
  "result_id": "result_abc",
  "next_actions": ["read_result"]
}
```

缓存规则：

- `result_id` 只在当前 `mcp-conductor` 进程内有效。
- 默认 TTL 30 分钟。
- 按外部连接/session 或请求上下文隔离。
- 设置最大缓存条数和最大字节数。
- 如果当前 Host/transport 无法提供 session id，大结果只返回摘要和预览，不返回可继续读取的 `result_id`。
- 不缓存 secrets、token、密码和敏感凭证。

第一版摘要策略：

- 默认使用规则摘要、结构化 preview 和截断，不依赖模型。
- 如果后续通过 Sampling 做模型摘要，必须由外部 Host 控制，并且摘要 prompt 不能包含 secrets、token、密码或完整敏感 payload。

## 阶段 13：读取更多结果

如果外部模型需要更多详情，可以调用：

```text
read_result
```

调用示例：

```json
{
  "result_id": "result_abc",
  "cursor": null,
  "limit": 20
}
```

返回示例：

```json
{
  "status": "ok",
  "items": [],
  "next_cursor": "cursor_xyz",
  "has_more": true
}
```

规则：

- cursor 是不透明 token。
- 外部模型不应该解析或构造 cursor。
- `read_result` 只能读取当前 session 可访问的结果。

## 阶段 14：外部模型生成最终回答

外部 Host 把 `mcp-conductor` 返回的结果放回模型上下文。

外部模型基于结果回答用户：

```text
PR #12 的 CI 失败在 test-python job。
主要原因是 tests/test_api.py 中的断言错误。
建议先查看该测试最近相关改动，然后重新运行 pytest。
```

最终回答由外部 Host 展示给用户。

## 完整主链路图

```text
配置阶段
  ↓
外部 Host 只配置 mcp-conductor
  ↓
mcp-conductor 读取 upstream 配置
  ↓
为每个 upstream server 建立独立 Client/session
  ↓
发现上游 tools/resources/resource templates/prompts
  ↓
建立能力注册表
  ↓
对外暴露少量高级工具
  ↓
用户提问
  ↓
外部模型优先调用 analyze_user_task
  ↓
mcp-conductor 推荐候选能力、schema 和下一步公开工具调用参数
  ↓
外部模型使用 next_public_tool / ready_to_call_arguments 调用 call_upstream_tool / read_upstream_resource / read_upstream_resource_template / get_upstream_prompt
  ↓
mcp-conductor 校验 recommendation_id / route_token / schema / risk_policy
  ↓
必要时通过 Elicitation 请求 Host 收集用户确认
  ↓
mcp-conductor 调用对应上游 MCP Server
  ↓
mcp-conductor 裁剪、摘要、缓存结果
  ↓
外部模型基于结果回答用户
```

## 未来 step routing 链路

上面的主链路描述的是当前 Gateway Server 被外部 Host 调用时的流程。它不代表 `mcp-conductor` 已经能够强制接管 Host 的每一次内部循环。

如果后续要实现“每次用户输入和每次 agent loop 步骤都先筛选能力”，流程应增加外层 Orchestrator：

```text
用户输入
  ↓
Host wrapper / Agent Orchestrator
  ↓ 调用
mcp-conductor-core: start_routing_session 或 analyze_user_task
  ↓ 返回
本轮候选能力 + route_token + ready_to_call_arguments
  ↓
Orchestrator 构建本轮模型上下文
  ↓
模型选择候选能力并填写参数
  ↓
Orchestrator 通过 mcp-conductor-core 执行上游访问工具
  ↓
工具结果 summary / preview / result_id
  ↓
Orchestrator 只把当前工具结果或当前 loop 步骤作为 step_content
  ↓ 调用
mcp-conductor-core: analyze_agent_step
  ↓
下一轮候选能力
  ↓
循环直到任务完成
```

这条链路的关键区别是：

- 当前 Gateway 主链路依赖外部 Host/模型主动调用 `analyze_user_task`。
- 未来 step routing 链路由 Orchestrator 主动调用 `mcp-conductor-core`，因此可以强制每轮先筛选。
- `mcp-conductor-core` 仍然不直接管理完整对话，也不直接决定最终回答。
- 每轮传给 core 的是当前 `step_content`，不是把完整历史全部拼进去。

## 第一版和第二阶段的区别

### 第一版

第一版目标是跑通稳定、可验证的 Gateway MVP：

- 外部标准 MCP Server。
- 内部 upstream 配置。
- 每个上游 Server 一个 Client/session。
- tools/resources/resource templates/prompts 能力发现。
- 能力注册表。
- 规则/标签推荐。
- `analyze_user_task`。
- `recommend_capabilities`。
- `call_upstream_tool`。
- `read_upstream_resource`。
- `read_upstream_resource_template`。
- `get_upstream_prompt`。
- 只读能力自动访问。
- 危险操作返回 `confirmation_required` 或使用 Elicitation。
- 结果摘要、preview、可选 `result_id`。
- 上游客户端原语桥接至少具备保守拒绝、受限返回或降级策略。

### 第二阶段

第二阶段增加智能路由和更完整能力：

- Step routing session。
- `analyze_agent_step`。
- 本地 demo orchestrator。
- Host 采样路由器。
- 语义/向量检索。
- 受控的 `ask_conductor`，用于减少多步工具调用摩擦，但不能变成完整 Host 或万能代理。
- 更完整的权限策略和持久化缓存。

### 第三阶段或独立产品线

如果目标是强制接管每次用户输入和每次 agent loop 步骤，需要增加独立 Host/Agent Runtime：

- `mcp-conductor-agent`。
- Codex / Claude Code 外层 wrapper。
- IDE/plugin 层。
- 自己实现的 MCP Host。

这一阶段不再只是 MCP Gateway Server，而是外层编排能力。

## 关键边界

- `mcp-conductor` 不替代外部 Host。
- `mcp-conductor` 不直接管理用户对话。
- `mcp-conductor` 不直接控制外部模型看到的所有工具。
- `mcp-conductor` 不强制接管外部 Host 的每一次 agent loop。
- `mcp-conductor` 不应绕过 Host 自己配置模型 API 密钥。
- `mcp-conductor` 不应绕过 Host 自己向用户确认危险操作。
- `mcp-conductor` 可以请求 Sampling、Roots、Elicitation 等 Host/Client 侧能力，但是否支持和批准由 Host 决定。
