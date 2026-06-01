# 需求分析

## 已确认需求

1. 项目要实现一个 MCP Gateway Server，而不是完整 MCP Host。
2. 它必须能像普通 MCP Server 一样被外部 Host 配置和使用。
3. 它第一版对外主要暴露少量高级 tools；resources、resource templates 和 prompts 第一版只做发现、摘要和展示，不进入完整调用链路。
4. 它对内作为 MCP Client 连接多个上游 MCP Server。
5. 它需要发现每个上游 MCP Server 暴露的 tools、resources、resource templates 和 prompts。
6. 它需要为每个上游 MCP Server 维护独立的 MCP Client/session。
7. 它需要建立统一的能力注册表。
8. 能力注册表必须记录能力来自哪个上游 Server，以及应该通过哪个上游 Client 调用。
9. 它不应该把全部上游能力原样暴露给外部 Host。
10. 它需要根据用户任务筛选、推荐或调用合适的上游能力。
11. 可以在第二阶段引入 Host 采样路由器帮助进行工具筛选和能力路由；不能由 `mcp-conductor` 私自配置模型 API 密钥。
12. 上游 Server 返回的大结果不能直接完整返回给外部 Host。
13. 它需要对上游结果做摘要、分页、缓存或引用管理。
14. 它不负责直接管理用户对话、大模型请求或外部 Host 的完整工具上下文。
15. 它的职责边界是管理上游 MCP 能力，而不是替代 Codex、Claude Code、Cursor 等 Host。

## 对外暴露能力

第一版可以优先暴露少量高级工具，而不是暴露全部上游工具：

```text
list_upstream_capabilities
recommend_capabilities
call_upstream_tool
read_result
```

这些工具的目标是让外部模型不必直接面对全部上游 MCP Server。

`ask_conductor` 不作为第一版必需工具。它可以作为第二阶段或可选增强能力出现，并且只能通过 Host 支持的 Sampling 发起受控路由推理，不能由 `mcp-conductor` 自己私自配置和调用模型。

第一版对外工具的关键约束：

- `recommend_capabilities` 返回候选能力、必要 schema、`recommendation_id` 和不透明 `route_token`。
- `call_upstream_tool` 默认只能调用当前有效推荐结果中的 tool，必须携带 `recommendation_id`、`route_token`、`capability_id` 和 `arguments`。
- 如果没有先调用 `recommend_capabilities`，或推荐结果过期、`route_token` 不匹配，`call_upstream_tool` 默认拒绝执行。
- `read_result` 只能读取当前外部连接/session 或请求上下文可访问的缓存结果。

## 核心设计问题

### 外部 Host 只看到 mcp-conductor

如果用户希望减少工具数量，外部 Host 应尽量只配置 `mcp-conductor`。其他 MCP Server 放在 `mcp-conductor` 的内部上游配置里。

### 上游工具过多

上游 MCP Server 可能暴露大量工具。`mcp-conductor` 需要区分：

- 内部发现到的全部能力。
- 当前任务可能相关的候选能力。
- 实际执行时选择的具体能力。

每个能力都必须能追踪回：

- 上游 Server ID。
- 上游 Client/session。
- 上游能力原始名称。
- 对外展示或内部路由使用的规范化能力 ID。

### 工具选择

外部模型可以调用 `mcp-conductor` 的高级工具。`mcp-conductor` 第一版内部通过规则和标签选择上游能力；语义检索和 Host 采样路由器作为第二阶段增强。

第一版优先使用规则和标签筛选。路由代理如果启用，必须定义为 Host 采样路由器：由 `mcp-conductor` 通过 MCP Sampling 请求外部 Host 使用其受控模型完成一次路由判断。如果外部 Host 不支持 Sampling 或用户拒绝 Sampling，请求必须回退到规则/标签筛选或返回 `sampling_not_supported`。

### 上下文控制

需要控制两类上下文：

- 对外 Host 暴露的工具数量。
- 上游工具返回给外部 Host 的结果大小。

推荐用结果摘要、预览和 `result_id` 管理大结果。

### 准确性

工具筛选要做到“准确且充分”：

- 准确：不要调用明显无关的上游工具。
- 充分：不要漏掉完成任务所需的关键上游能力。

### 安全性

需要识别上游工具风险：

- 只读工具。
- 写入工具。
- 删除工具。
- 发送消息或提交外部请求的工具。
- 需要用户确认的工具。

第一版默认只允许被风险策略确认后的只读能力自动执行。上游声明或工具卡片中的 `read_only` / `read_only_hint` 只能作为提示，不能完全信任。最终风险判断必须综合 `risk_policy`、allowlist、工具名/描述规则、用户配置和 Roots/路径约束；未知风险能力默认按危险处理。

危险操作确认优先通过 MCP Elicitation 请求外部 Host 收集用户确认；如果 Host 不支持 Elicitation，则返回 `confirmation_required` 和 `pending_action_id`，由外部 Host 和用户完成确认后再重新调用。`pending_action_id` 必须有过期时间，确认后参数不能变化，不能用普通 `confirmed=true` 替代。`mcp-conductor` 负责识别风险和阻止默认执行，不负责自己决定是否替用户同意。

### 结果缓存

第一版结果缓存使用进程内缓存即可，但必须定义边界：

- `result_id` 是不透明、不可猜测的 ID。
- 默认 TTL 为 30 分钟。
- 缓存按外部连接/session 或请求上下文隔离。
- 设置最大缓存条数和最大字节数。
- 不持久化 secrets、token、凭证和敏感内容。
- 进程退出后 `result_id` 失效。

### 上游能力类型范围

第一版优先完整支持 tools：

- `tools/list`
- `tools/call`

resources、resource templates 和 prompts 第一版可以先做发现和列表展示，不进入完整执行链路。后续再补充：

- `read_upstream_resource`
- `resolve_upstream_resource_template`
- `get_upstream_prompt`

## 非目标

第一阶段不优先做：

- 完整 MCP Host。
- 完整大模型对话管理。
- 直接接管外部 Host 的工具上下文。
- 阻止外部 Host 直接配置其他 MCP Server。
- 自己私自配置模型 API 密钥并绕过 Host Sampling。
- 第一版完整支持 resources、resource templates 和 prompts 的调用链路。
- 图形化界面。
- 复杂多用户权限系统。
- 所有 MCP Server 的生产级兼容。
- 复杂工作流编排语言。
- 长期记忆系统。

这些可以在 Gateway Server 核心链路稳定后再扩展。
