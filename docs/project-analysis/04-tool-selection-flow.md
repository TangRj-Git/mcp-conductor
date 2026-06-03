# 工具筛选流程

## 核心原则

`mcp-conductor` 对外是一个标准 MCP Server，不直接控制外部 Host 的全部工具上下文。

它的核心价值是减少外部模型每轮直接看到的底层工具数量，同时保留使用大量上游 MCP 能力的可能性。

它能控制的是：

- 自己对外暴露哪些高级工具。
- 内部连接哪些上游 MCP Server。
- 如何从上游能力中筛选当前任务相关的候选能力。
- 如何把候选能力、schema 和调用凭证以紧凑形式返回给外部模型。
- 如何在外部模型携带有效推荐凭证后访问上游能力。
- 如何裁剪和缓存上游返回结果。

## 推荐使用方式

如果想减少外部模型看到的工具数量，推荐：

```text
外部 Host 只配置 mcp-conductor
mcp-conductor 内部配置多个上游 MCP Server
```

不推荐在外部 Host 中同时直接配置大量上游 MCP Server，否则外部模型仍然会看到大量底层工具。

## 触发边界

当前工具筛选流程只有在外部 Host 或模型调用 `mcp-conductor` 公开工具时才会发生。也就是说：

```text
Host/模型没有调用 analyze_user_task 或 recommend_capabilities
  -> mcp-conductor 不会知道当前用户问题
  -> mcp-conductor 也不会把上游候选能力返回给 Host/模型
```

这不是实现缺陷，而是 MCP Server 和 MCP Host 的职责边界。普通 MCP Server 只能暴露 tools/resources/resource templates/prompts；它不能主动拦截用户输入，也不能主动改写 Host 每一轮给模型的真实工具列表。

当前项目通过三种方式降低触发成本：

1. `analyze_user_task` 作为更自然的首选入口，适合用户任务开始或 agent loop 某一步调用。
2. MCP server instructions 明确提示：当任务可能需要已配置上游能力时，应先调用 `analyze_user_task`。
3. 推荐结果返回 `next_public_tool` 和 `ready_to_call_arguments`，让下一步调用尽量可直接执行。

但这些都不是强制机制。强制每轮筛选需要外层 Host wrapper 或 Agent Orchestrator。

## 内部筛选流程

第一版把“推荐”和“访问”分成两步，避免外部模型绕过筛选直接调用任意上游能力。

推荐阶段：

```text
外部 Host 调用 mcp-conductor 高级工具
  ↓
mcp-conductor 接收用户任务或查询
  ↓
规则过滤
  ↓
规则/标签召回候选上游能力
  ↓
可选 Host 采样路由器选择候选能力
  ↓
策略引擎做权限和风险过滤
  ↓
返回推荐能力、必要 schema、recommendation_id、route_token、next_public_tool 和 ready_to_call_arguments
```

执行阶段：

```text
外部模型优先使用推荐结果中的 next_public_tool 和 ready_to_call_arguments
  ↓
外部 Host 按能力类型调用对应公开工具
  ↓
mcp-conductor 校验 recommendation_id / route_token / schema / risk_policy
  ↓
网关执行引擎访问上游 MCP Server
  ↓
Result Manager 裁剪和缓存结果
  ↓
mcp-conductor 返回摘要、预览或 result_id
```

注意：第一版不允许外部模型直接凭空指定任意上游能力执行。推荐链路必须先经过 `analyze_user_task` 或 `recommend_capabilities`，再由 `call_upstream_tool`、`read_upstream_resource`、`read_upstream_resource_template` 或 `get_upstream_prompt` 携带 `recommendation_id` 和 `route_token` 进入访问链路。

## 三种工具暴露模式

当前项目需要区分三种模式：

### router 模式

这是当前默认模式，也是第一版主线。

```text
Host 只看到 mcp-conductor 的固定公开工具
  -> 模型调用 analyze_user_task
  -> mcp-conductor 返回候选能力和 route_token
  -> 模型再调用 call_upstream_tool / read_upstream_resource / read_upstream_resource_template / get_upstream_prompt
```

优点是安全边界清楚，上游能力不会一次性全部塞给 Host。缺点是依赖 Host/模型愿意先调用 `analyze_user_task`。

### proxy / hybrid 暴露计划

当前 `exposure.mode=proxy` 或 `hybrid` 只生成诊断计划：

```text
list_exposed_capabilities -> 返回哪些 read-only tool 将来可以被直接暴露
```

它目前不会把上游工具动态注册成 FastMCP tools。因此 Host 当前仍然看不到这些计划中的上游工具，只能通过 `mcp-conductor` 固定公开工具访问。

### Host/Agent Orchestrator

如果要实现“每次用户输入和每次 agent loop 步骤都先筛选”，需要外层编排：

```text
step_content
  -> orchestrator 调用 mcp-conductor analyze_agent_step / analyze_user_task
  -> orchestrator 只把筛选后的工具候选交给模型
  -> 模型选择工具
  -> orchestrator 通过 mcp-conductor 执行上游能力
  -> 工具结果进入下一轮 loop
```

这已经不是单纯 MCP Server，而是 Host/Agent Runtime 方向的工作。

## 内部 Client 路由模型

`mcp-conductor` 内部不是用一个 Client 调所有上游 Server，而是为每个上游 MCP Server 维护一个独立 Client/session：

```text
mcp-conductor
  ├─ upstream_client: github ── github MCP Server
  ├─ upstream_client: filesystem ── filesystem MCP Server
  └─ upstream_client: database ── database MCP Server
```

能力注册表中的每个能力都需要记录：

```text
capability_id
upstream_server_id
upstream_client_id
capability_type
original_name_or_uri
schema_or_metadata
```

当规则筛选或 Host 采样路由器选中某个能力后，网关执行引擎根据 `capability_id` 找到对应上游 Client，再通过这个 Client 调用或访问对应 Server。

## Host 采样路由器的作用

Host 采样路由器是第二阶段可选的能力筛选增强。它负责辅助推荐能力，但不负责真正调用或访问上游能力，也不是 `mcp-conductor` 自己创建和持有的模型子代理。

在本项目中，需要模型推理的路由能力必须优先实现为 Host 采样路由器：`mcp-conductor` 通过 MCP Sampling 请求外部 Host 使用其受控模型完成一次路由推理。Host 可以拒绝请求、要求用户确认或选择不同模型。

如果 Host 不支持 Sampling，`mcp-conductor` 必须回退到规则/标签筛选。

路由代理输入：

```text
用户当前任务
对话简要上下文
候选能力卡片列表
当前权限和安全策略摘要
```

路由代理输出：

```json
{
  "intent": "用户当前意图",
  "required_capabilities": ["需要的能力"],
  "selected_tools": [
    {
      "capability_id": "能力 ID",
      "server_name": "上游 MCP Server 名称",
      "client_id": "上游 Client ID",
      "reason": "选择原因",
      "confidence": 0.9
    }
  ],
  "need_clarification": false
}
```

## 工具卡片

为了避免路由代理看到完整 schema，可以先提供压缩后的工具卡片：

```text
tool_id
tool_name
server_name
description
tags
use_when
do_not_use_when
input_summary
output_summary
risk_level
read_only_hint
estimated_result_size
```

## 筛选策略

第一版采用保守策略：

1. 规则过滤：去掉禁用、无权限、明显无关的能力。
2. 标签筛选：根据工具卡片标签、风险级别、能力类型召回候选能力。
3. 策略引擎：做权限、安全和数量控制。
4. 网关执行引擎：自动访问被风险策略允许的只读能力；非只读 tool 必须先经过确认链路。

第二阶段再加入：

1. 语义检索：从工具卡片中召回前 30 到前 50 个候选能力。
2. Host 采样路由器：通过 Sampling 从候选能力中选择前 5 到前 15 个能力。
3. 可选的 `ask_conductor`：在不绕过 Host 和安全策略的前提下，把推荐、受控调用和结果整理串成更顺滑的高级工具；它不是第一版核心目标，也不能变成不受控的万能代理。

## 对外工具设计

第一版对外不应该暴露上游所有工具，而是暴露少量高级工具：

```text
analyze_user_task
start_routing_session
analyze_agent_step
list_routing_session_state
end_routing_session
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

- `analyze_user_task` 用于根据当前用户任务或 agent loop 步骤推荐上游能力，是首选入口。
- `start_routing_session` 用于为一个用户任务创建轻量 routing session，并返回第一轮推荐。
- `analyze_agent_step` 用于在已有 routing session 中只根据当前单步 `step_content` 推荐上游能力。
- `list_routing_session_state` 用于查看 compact routing session 状态，主要服务调试和 Inspector。
- `end_routing_session` 用于释放 routing session 状态。
- `list_upstream_capabilities` 用于查看内部发现到的能力摘要。
- `list_exposed_capabilities` 用于查看当前 `exposure` 配置下的 proxy/hybrid 暴露计划；它只做诊断，不直接执行上游能力。
- `recommend_capabilities` 用于根据用户任务推荐上游能力，是较底层入口。
- `call_upstream_tool` 用于调用指定的上游 tool，必须传入 `recommendation_id`、`route_token`、`capability_id` 和 `arguments`，并通过推荐凭证、schema、安全策略、Roots/allowlist 和风险检查。
- `read_upstream_resource` 用于读取被推荐的上游 resource，必须通过推荐凭证和风险策略校验。
- `read_upstream_resource_template` 用于校验参数、展开被推荐的 resource template，并读取展开后的资源 URI。
- `get_upstream_prompt` 用于获取被推荐的上游 prompt，并校验 prompt 参数。
- `read_result` 用于读取缓存的大结果分页或完整内容。

`call_upstream_tool` 的执行规则：

- 只能调用当前有效推荐结果中的 tool。
- `route_token` 是不透明 token，外部模型不能构造或修改。
- 推荐结果过期、`route_token` 不匹配、能力已禁用、参数不符合 schema、风险策略不允许时，都必须拒绝执行。
- 未知风险能力默认按危险处理。

资源、资源模板和 Prompt 的访问规则：

- 必须来自当前有效推荐结果。
- 必须携带匹配的 `recommendation_id`、`route_token` 和 `capability_id`。
- 只能访问风险策略允许的只读能力。
- resource template 会先校验参数，再展开为具体 URI 后读取。

`ask_conductor` 是第二阶段或可选增强工具，依赖 Host Sampling。它必须继续遵守推荐凭证、风险策略、危险操作确认和结果裁剪规则。

## 结果管理

上游工具返回结果不应该默认全部返回给外部 Host。

推荐返回格式：

```json
{
  "summary": "结果摘要",
  "preview": [],
  "result_id": "result_xxx",
  "next_actions": ["read_result"]
}
```

大结果保存在 `mcp-conductor` 内部，外部模型只看到摘要、预览和后续可执行动作。

第一版结果缓存规则：

- `result_id` 只在当前 `mcp-conductor` 进程内有效。
- 默认 TTL 30 分钟。
- 按外部连接/session 或请求上下文隔离。
- 设置最大缓存条数和最大字节数。
- 如果 Host 不提供 session id，大结果只返回摘要和预览，不返回可继续读取的 `result_id`。
- 不缓存 secrets、token 和敏感凭证。
