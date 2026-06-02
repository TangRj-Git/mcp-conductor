# Step Routing 与 Agent Orchestrator 结构设计

## 文档目的

这份文档把 `docs/project-analysis/11-host-orchestrator-and-step-routing.md` 中的产品结论落到工程结构上。

核心结论：

```text
当前项目继续保持 mcp-conductor-core：MCP Gateway Server。
每轮强制筛选需要额外的 mcp-conductor-agent：Host wrapper / Agent Orchestrator。
```

## Core 内先新增的结构

即使暂时不实现完整 Host wrapper，Gateway Core 也可以先新增 step routing 能力。

推荐目录：

```text
src/mcp_conductor/
  routing/
    session.py
    step.py
  public_tools/
    routing_session.py
    analyze_step.py
```

### `routing/session.py`

职责：

- 保存轻量路由会话，不保存完整对话。
- 记录 `session_id`、创建时间、过期时间、最初任务摘要。
- 记录最近步骤摘要、推荐过的 `capability_id`、调用过的能力和失败记录。
- 提供 TTL prune 和最大条数限制。

建议模型：

```text
RoutingSession
  session_id
  created_at
  expires_at
  original_task_summary
  recent_steps
  recommended_capability_ids
  called_capability_ids
  failed_capabilities

RoutingSessionStore
  create(...)
  get(session_id)
  record_step(...)
  record_recommendation(...)
  record_call_result(...)
  end(session_id)
  prune_expired()
```

### `routing/step.py`

职责：

- 接收当前单步 `step_content`。
- 构建用于能力筛选的文本。
- 调用现有规则/标签推荐逻辑。
- 将 session 中的失败能力或最近调用能力作为弱信号，降低重复推荐概率。
- 返回本轮 `routing_round_id` 和候选能力。

它不执行上游能力，不生成最终回答。

### `public_tools/routing_session.py`

建议暴露调试和生命周期工具：

```text
start_routing_session
list_routing_session_state
end_routing_session
```

这些工具主要服务本地 demo、Inspector 和未来 Orchestrator，不要求普通 Codex/Claude Code 每次都使用。

### `public_tools/analyze_step.py`

建议新增：

```text
analyze_agent_step
```

输入示例：

```json
{
  "session_id": "task_123",
  "step_index": 2,
  "step_type": "tool_result",
  "step_content": "读取配置文件失败，路径不存在。",
  "limit": 8
}
```

输出示例：

```json
{
  "status": "ok",
  "routing_round_id": "round_456",
  "recommended_capabilities": [],
  "next_step": "Pick one recommended capability and call its next_public_tool with ready_to_call_arguments."
}
```

## Runtime 装配变化

`GatewayRuntime` 仍然是 Core 的总协调对象，但新增功能应避免把所有逻辑塞进 `runtime.py`。

推荐做法：

```text
GatewayRuntime
  -> RoutingSessionStore
  -> StepRoutingService
  -> existing recommender / registry / policy
```

`runtime.py` 只新增薄方法：

```text
start_routing_session(...)
analyze_agent_step(...)
list_routing_session_state(...)
end_routing_session(...)
```

具体状态管理和 step 分析逻辑放到 `routing/session.py` 和 `routing/step.py`。

## 本地 demo 脚本

建议新增：

```text
scripts/agent_loop_demo.py
```

目标不是做真实 LLM agent，而是验证流程：

```text
用户任务
  -> start_routing_session
  -> analyze_agent_step 或 analyze_user_task
  -> 选择一个推荐项
  -> 调用 next_public_tool + ready_to_call_arguments
  -> 把工具结果摘要作为下一次 step_content
  -> 再调用 analyze_agent_step
```

这个 demo 可以证明 Core 已经具备“每步筛选”的 API 能力，同时明确“强制每步触发”仍由外层 Orchestrator 负责。

## Agent Orchestrator 独立结构

如果后续开发 `mcp-conductor-agent`，建议不要把它混进当前 Server 入口。

推荐新包或新目录：

```text
src/mcp_conductor_agent/
  cli.py
  loop.py
  model.py
  tool_surface.py
  conductor_client.py
```

职责：

- `cli.py`：启动 agent/wrapper。
- `loop.py`：控制用户输入、模型调用、工具调用和循环结束。
- `model.py`：接入具体模型或 Host Sampling。
- `tool_surface.py`：把 `mcp-conductor-core` 返回的候选能力转换成本轮模型可理解的工具面。
- `conductor_client.py`：连接当前 Gateway Core，对其公开工具发起调用。

这个包如果出现，就意味着项目开始具备 Host/Agent Runtime 能力。它应和 `mcp_conductor` Gateway Core 保持清晰边界。

## 测试建议

新增 Core step routing 时，优先补这些测试：

- `RoutingSessionStore` 创建、过期、结束和最大条数清理。
- `analyze_agent_step` 只使用当前 `step_content` 和轻量 session 状态，不把完整历史拼进去。
- 失败能力在同一个 session 内降低重复推荐优先级。
- `routing_round_id` 不透明且每轮不同。
- 推荐结果仍然携带 `recommendation_id`、`route_token`、`next_public_tool` 和 `ready_to_call_arguments`。
- 过期 session 不能继续访问 step routing。

## 当前开发边界

下一步可以先做 Gateway Core 的 step routing API。它不会让 Codex/Claude Code 自动每轮调用，但会为未来 Orchestrator 准备好稳定接口。

只有当外层 `mcp-conductor-agent`、Host wrapper 或 IDE/plugin 真正控制了 loop，才能实现强制每轮筛选。
