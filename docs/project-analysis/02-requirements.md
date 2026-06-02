# 需求分析

## 最高优先级目标

`mcp-conductor` 的第一目标是解决“外部 Host 直接配置太多 MCP Server”带来的问题：

- 大模型每轮可见工具过多，工具描述和 schema 占用上下文。
- 相似工具互相干扰，模型选择工具的准确率下降。
- 上游工具结果过大，进一步挤占对话上下文。
- 危险或未知风险能力如果直接暴露，容易被错误调用。

项目的设计必须服务于这条主线：

```text
把很多上游 MCP 能力收拢到一个受控入口后面；
每轮根据用户任务推荐少量相关能力；
让模型既能充分使用已配置能力，又不被全部底层工具干扰。
```

## 已确认需求

1. 项目要实现一个 MCP Gateway Server，而不是完整 MCP Host。
2. 它必须能像普通 MCP Server 一样被外部 Host 配置和使用。
3. 它第一版对外主要暴露少量高级 tools；上游 tools、resources、resource templates 和 prompts 都可以进入推荐链路，但必须通过对应的公开工具和推荐凭证受控访问。
4. 它对内作为 MCP Client 连接多个上游 MCP Server。
5. 它需要发现每个上游 MCP Server 暴露的 tools、resources、resource templates 和 prompts。
6. 它需要为每个上游 MCP Server 维护独立的 MCP Client/session。
7. 它需要建立统一的能力注册表。
8. 能力注册表必须记录能力来自哪个上游 Server，以及应该通过哪个上游 Client 调用。
9. 它不应该把全部上游能力原样暴露给外部 Host。
10. 它需要根据用户任务筛选并推荐合适的上游能力；真正调用必须发生在外部模型携带有效推荐凭证和参数之后。
11. 可以在第二阶段引入 Host 采样路由器帮助进行工具筛选和能力路由；不能由 `mcp-conductor` 私自配置模型 API 密钥。
12. 上游 Server 返回的大结果不能直接完整返回给外部 Host。
13. 它需要对上游结果做摘要、分页、缓存或引用管理。
14. 它不负责直接管理用户对话、大模型请求或外部 Host 的完整工具上下文。
15. 它的职责边界是管理上游 MCP 能力，而不是替代 Codex、Claude Code、Cursor 等 Host。
16. 它不能假装自己能动态修改外部 Host 的真实工具列表；它能做的是通过自己的公开工具返回候选能力、schema 和受控调用凭证。
17. 它不能强制外部 Host 在每次用户输入或每次内部 agent loop 步骤都调用自己；如果需要强制每轮筛选，需要新增 Host wrapper、Agent Orchestrator 或 IDE/plugin 层。

## 对外暴露能力

第一版可以优先暴露少量高级工具，而不是暴露全部上游工具：

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

这些工具的目标是让外部模型不必直接面对全部上游 MCP Server。外部模型先看到少量高级工具，再优先通过 `analyze_user_task` 获取当前任务或 agent loop 步骤相关的候选能力和调用凭证。`recommend_capabilities` 作为较底层推荐入口保留。

`list_exposed_capabilities` 是当前新增的 proxy/hybrid 暴露计划诊断工具，只展示哪些 read-only 上游 tool 会被当前 `exposure` 配置选中，不代表这些上游 tool 已经动态注册为 Host 可直接看到的 MCP tools。

`ask_conductor` 不作为第一版必需工具，也不能成为把项目带偏成“万能代理”的入口。它只能作为第二阶段或可选增强能力出现，并且只能通过 Host 支持的 Sampling 发起受控路由推理，不能由 `mcp-conductor` 自己私自配置和调用模型。

第一版对外工具的关键约束：

- `analyze_user_task` 和 `recommend_capabilities` 返回候选能力、必要 schema、`recommendation_id`、不透明 `route_token`、`next_public_tool` 和 `ready_to_call_arguments`。
- `call_upstream_tool` 默认只能调用当前有效推荐结果中的 tool，必须携带 `recommendation_id`、`route_token`、`capability_id` 和 `arguments`。
- 如果没有先调用 `analyze_user_task` 或 `recommend_capabilities`，或推荐结果过期、`route_token` 不匹配，具体访问工具默认拒绝执行。
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

### 触发和 agent loop 筛选

用户期望的理想链路是：

```text
第一次：用户问题 -> 先交给 mcp-conductor 筛选相关上游能力 -> 再交给模型选择和调用
后续：每次 agent loop 新步骤或工具结果 -> 再交给 mcp-conductor 筛选相关上游能力 -> 再交给模型继续处理
```

这个目标拆成两层：

1. Gateway Server 能力：`mcp-conductor` 提供 `analyze_user_task` / 后续可增加 `analyze_agent_step`，接收当前任务或当前步骤内容，返回候选能力和 route-token-gated 调用参数。
2. Host/Agent Orchestrator 能力：外层运行时必须主动在每次用户输入和每次 loop 步骤调用这些工具，并把返回的候选能力作为模型本轮可用工具上下文的一部分。

当前项目只实现了第一层中的 `analyze_user_task`。它可以处理用户任务，也可以通过 `context_summary` 接收当前 loop 状态，但它不能强制 Codex、Claude Code 这类外部 Host 每轮都调用自己。

### 上下文控制

需要控制两类上下文：

- 对外 Host 暴露的工具数量。
- 上游工具返回给外部 Host 的结果大小。

第一类通过“外部 Host 只配置 `mcp-conductor` + `mcp-conductor` 只暴露少量高级工具”解决。第二类通过结果摘要、预览和 `result_id` 管理大结果。

`recommend_capabilities` 返回的 schema 应只覆盖被推荐的候选能力，不能把全部上游 schema 一次性塞回模型上下文。

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

当前第一版已经支持发现这些上游能力：

- `tools/list`
- `resources/list`
- `resources/templates/list`
- `prompts/list`

当前第一版已经支持这些受控访问链路：

- `tools/call` -> `call_upstream_tool`
- `resources/read` -> `read_upstream_resource`
- resource template expansion + `resources/read` -> `read_upstream_resource_template`
- `prompts/get` -> `get_upstream_prompt`

其中 `call_upstream_tool` 只执行 `tool` 类型能力；resources、resource templates 和 prompts 必须先由 `analyze_user_task` 或 `recommend_capabilities` 推荐，再携带 `recommendation_id`、`route_token` 和 `capability_id` 通过对应公开工具访问。资源模板参数需要先通过 schema 校验，再按支持的 URI Template 语法展开。

## 非目标

第一阶段不优先做：

- 完整 MCP Host。
- 完整大模型对话管理。
- 直接接管外部 Host 的工具上下文。
- 阻止外部 Host 直接配置其他 MCP Server。
- 自己私自配置模型 API 密钥并绕过 Host Sampling。
- 让外部模型一次看到全部上游能力或全部上游 schema。
- 根据用户问题自动绕过外部模型直接执行完整任务。
- 将所有上游 tools/resources/resource templates/prompts 原样动态暴露给外部 Host。
- 只靠 MCP Server 本身强制接管 Codex、Claude Code 等 Host 的内部 agent loop。
- 图形化界面。
- 复杂多用户权限系统。
- 所有 MCP Server 的生产级兼容。
- 复杂工作流编排语言。
- 长期记忆系统。

这些可以在 Gateway Server 核心链路稳定后再扩展。
