# 危险操作确认

## 文档目的

这份文档记录危险操作确认模块的结构边界。

它主要回答三个问题：

1. `mcp-conductor` 遇到非只读或未知风险工具时，为什么不能直接执行。
2. `pending_action_id` 如何绑定一次具体的待确认操作。
3. 当前 Host Elicitation 和 `confirmation_required` 兜底路径如何协作。

## 当前实现

`mcp-conductor` 不会在第一次调用时直接执行非只读或未知风险的工具。

当前第一版已经实现 Host Elicitation 优先确认路径，同时保留 `pending_action_id` 兜底路径。只有外部 Host 支持 Elicitation 并且用户明确接受时，网关才会把待确认操作标记为已确认并重试执行。

第一次对高风险能力发起 `call_upstream_tool` 请求时，会返回：

```json
{
  "status": "confirmation_required",
  "pending_action_id": "pending_...",
  "expires_at": "...",
  "capability_id": "...",
  "risk_level": "destructive",
  "arguments_preview": {},
  "message": "User confirmation is required before this action can run."
}
```

网关会把待确认操作保存在进程内存中。

## 确认调用

当前公开工具不会仅凭返回给模型的 `pending_action_id` 执行高风险调用。
`pending_action_id` 只是待确认操作的记录 ID；必须由 Host Elicitation
或等价的可信外部确认集成把该待确认操作标记为已确认，网关才允许执行。

确认完成后，外部 Host 可以再次调用 `call_upstream_tool`，并携带相同的：

- `recommendation_id`
- `route_token`
- `capability_id`
- `arguments`
- `pending_action_id`

如果待确认操作已经被 Host 标记为确认完成、记录有效、没有过期，并且能力、风险等级和参数都完全匹配，`mcp-conductor` 才会执行上游工具。

待确认操作在校验通过后会被消费，因此同一个 `pending_action_id` 不能重复使用。

## 拒绝规则

以下情况中，`mcp-conductor` 会拒绝确认：

- 高风险执行缺少 `pending_action_id`。
- `pending_action_id` 未知或已经使用过。
- 待确认操作已经过期。
- `capability_id` 发生变化。
- 参数发生变化。
- 能力的风险等级发生变化。

网关不接受简单的 `confirmed=true` 标记。确认必须绑定到具体的待确认操作，避免模型或调用方绕过安全校验。

## Host Elicitation 集成

当前的兜底确认路径使用 `pending_action_id` 记录待确认操作，但不会把
`pending_action_id` 本身当作确认完成凭证。

当前 `server.py` 在收到 `confirmation_required` 后，会尝试通过 FastMCP `Context.elicit()` 请求外部 Host 收集用户确认。推荐流程是：

```text
高风险调用
  -> mcp-conductor 请求 Host 发起 Elicitation
  -> Host 向用户询问确认
  -> 用户接受后映射为待确认操作的确认结果
  -> 网关完成校验后才执行
```

如果 Host 不支持 Elicitation、用户拒绝，或 Elicitation 调用失败，现有的 `confirmation_required` 响应仍然作为兜底方案保留，操作不会被执行。
