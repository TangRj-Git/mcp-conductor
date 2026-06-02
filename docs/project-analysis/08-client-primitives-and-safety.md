# 客户端原语与安全边界

## 核心原则

`mcp-conductor` 是 MCP Server，但 MCP 协议允许 Server 在受控情况下请求 Client/Host 提供一些能力。

这些能力不是 `mcp-conductor` 自己拥有的 Host 权限，而是由外部 Host 声明、控制、展示和批准的协作能力。

一句话：

```text
Server 可以请求使用 Client/Host 侧能力。
Host 决定是否支持、是否批准、如何展示、如何返回结果。
```

同时，`mcp-conductor` 对内又是上游 MCP Server 的 Client。因此需要区分两个方向：

```text
外部方向：mcp-conductor 作为 Server，请求外部 Host/Client 提供能力。
上游方向：mcp-conductor 作为 Client，接收上游 Server 发起的能力请求。
```

第一版原则：

- 外部方向可以请求 Sampling、Roots、Elicitation，但必须接受 Host 拒绝或降级。
- 上游方向不能无条件把上游 Server 的请求透传给外部 Host。
- 上游请求必须经过 `mcp-conductor` 的桥接策略、风险策略和 allowlist。
- 对敏感信息、危险确认、模型推理、工作区边界等请求，默认保守拒绝或返回受限结果。

## Sampling

用途：

- 让 `mcp-conductor` 请求外部 Host 使用其受控模型做一次路由推理。
- 用于由 Host 采样的路由代理。
- 可增强 `recommend_capabilities`；第二阶段也可用于受控的 `ask_conductor`。

边界：

- `mcp-conductor` 不自己配置模型 API 密钥。
- `mcp-conductor` 不能指定 Host 必须使用哪个模型，只能表达模型偏好。
- Host 可以拒绝 Sampling 请求。
- Host 可以要求用户审核 prompt 和结果。
- Sampling 返回只用于推荐能力，不直接拥有工具执行权。
- Sampling 不能把上游工具描述或返回结果当成可信指令；这些内容只能作为不可信候选素材。

如果 Host 不支持 Sampling：

- 回退到规则/标签筛选。
- 或返回 `sampling_not_supported`。

## Elicitation

用途：

- 危险操作确认。
- 缺失参数补充。
- 需要用户选择多个候选方案之一。

边界：

- `mcp-conductor` 不自己直接问用户。
- `mcp-conductor` 通过 Elicitation 请求 Host 收集用户输入。
- Host 负责展示界面，并收集接受、拒绝或取消结果。
- Server 不得用 Elicitation 请求敏感信息，例如 token、密码、密钥。

危险操作策略：

```text
read_only_hint=true
  只能作为提示，不能单独作为自动执行依据。

风险策略确认后的只读能力
  可以自动执行。

写入/删除/发送/发布/支付/网络变更操作
  必须暂停执行。
  优先通过 Elicitation 请求 Host 收集确认。
  如果不支持 Elicitation，则返回带 pending_action_id 的 confirmation_required。
```

二次确认规则：

- `pending_action_id` 必须不透明、不可猜测并有过期时间。
- 确认后重新调用时参数不能变化。
- 用户拒绝或超时后不得执行。
- 不能用普通 `confirmed=true` 代替 `pending_action_id`。

## Roots

用途：

- 获取外部 Host 暴露的工作区边界。
- 限制上游 filesystem 类 Server 的可访问范围。
- 帮助生成默认 upstream filesystem 配置。

边界：

- Roots 是 Host 暴露给 Server 的边界信息。
- `mcp-conductor` 不能假设自己拥有 Roots 外的访问权限。
- 如果 Host 不支持 Roots，则使用内部配置中的 allowlist。

## Logging

用途：

- 向 Host 发送结构化日志。
- 记录上游连接失败、能力发现失败、路由失败、调用失败等事件。

边界：

- 日志不得包含 secrets、token、密码、PII 或完整敏感 payload。
- 日志需要限流。
- 日志级别应可被 Host 控制。

## Progress

用途：

- 长时间上游能力发现。
- 长时间上游工具调用。
- 大结果裁剪或分页准备。

边界：

- 只有当请求包含 progress token 或 Host 支持相关模式时发送进度。
- 进度通知必须停止于操作完成、失败或取消。

## Cancellation

用途：

- 外部 Host 或用户取消长时间操作时，`mcp-conductor` 应停止内部处理。
- 尝试取消上游 MCP 请求或清理相关任务。

边界：

- 取消可能失败，因为上游工具可能已经完成或不可取消。
- 取消后应释放缓存、子任务和进度状态。

## Pagination

用途：

- 处理上游 `tools/list`、`resources/list`、`resources/templates/list`、`prompts/list` 的大列表。
- 对外公开能力列表时使用分页。
- `read_result` 读取大结果时也应采用游标或分页思路。

边界：

- `cursor` 必须视为不透明令牌。
- 不应该让外部模型解析或构造 `cursor`。
- `cursor` 不应跨进程长期持久化。

## Completion

用途：

- 后续用于 MCP completion 能力相关场景。
- 更适合 prompt 参数或 resource template 参数补全。
- 如果后续想补全 `capability_id`，需要先确认目标 Host 是否会把该补全能力暴露给模型或用户界面。

边界：

- 第一版可以不实现。
- 补全结果不能泄露禁用能力或无权限能力。

## 上游客户端原语桥接

当上游 Server 向 `mcp-conductor` 发起 Client/Host 侧能力请求时，第一版采用保守桥接策略：

- 上游 Sampling：默认拒绝或返回 unsupported。只有外部 Host 支持 Sampling、用户允许、且请求内容通过安全检查时，后续版本才考虑转发。
- 上游 Elicitation：默认不允许上游直接向用户索要敏感信息。低风险缺失参数可以由 `mcp-conductor` 转换成自己的 Elicitation 请求，但必须过滤 token、密码、密钥等敏感字段。
- 上游 Roots：返回外部 Host Roots 与内部 allowlist 的受限交集；如果没有 Roots，则只使用内部配置 allowlist。
- 上游 Logging：可以接收并转发安全日志，但必须脱敏、限流，并标记上游来源。
- 上游 Progress：可以聚合成 `mcp-conductor` 对外的 Progress，但不能泄露敏感负载。
- 上游 Cancellation：外部取消时应尽量向上游传播；上游是否真的取消成功不做保证。
- 上游 Pagination：按上游 cursor 读取后，再转换为 `mcp-conductor` 自己对外的不透明 cursor。
- 上游 Completion：第一版不转发。

## 第一版采用策略

第一版必须支持或显式处理：

- Logging：记录安全的结构化事件。
- Pagination：处理上游 list 大结果。
- Cancellation：长任务可取消时尽量取消。
- Progress：长任务可选发送进度。
- 上游客户端原语桥接：至少要有明确拒绝、受限返回或降级策略。

第一版可以可选支持：

- Roots：如果 Host 支持，则用于约束工作区边界。
- Elicitation：如果 Host 支持，则用于危险操作确认。
- Sampling：如果 Host 支持，则用于 Host 采样路由器。

第一版不强制实现：

- Completion。
- `ask_conductor` 的受控高级流程。

## 参考资料

- Sampling 规范：https://modelcontextprotocol.io/specification/2025-06-18/client/sampling
- Elicitation 规范：https://modelcontextprotocol.io/specification/2025-06-18/client/elicitation
- Roots 规范：https://modelcontextprotocol.io/specification/2025-06-18/client/roots
- Progress 规范：https://modelcontextprotocol.io/specification/2025-06-18/basic/utilities/progress
- Cancellation 规范：https://modelcontextprotocol.io/specification/2025-06-18/basic/utilities/cancellation
- Logging 规范：https://modelcontextprotocol.io/specification/2025-06-18/server/utilities/logging
- Pagination 规范：https://modelcontextprotocol.io/specification/2025-06-18/server/utilities/pagination
- Completion 规范：https://modelcontextprotocol.io/specification/2025-06-18/server/utilities/completion
