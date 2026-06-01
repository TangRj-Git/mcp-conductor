# 危险操作确认

## 文档目的

这份文档记录危险操作确认模块的结构边界。

它主要回答三个问题：

1. `mcp-conductor` 遇到非只读或未知风险工具时，为什么不能直接执行。
2. `pending_action_id` 如何绑定一次具体的待确认操作。
3. 后续如果 Host 支持 Elicitation，确认流程应该如何接入。

## 当前实现

`mcp-conductor` 不会在第一次调用时直接执行非只读或未知风险的工具。

当前第一版已经实现的是 `pending_action_id` 兜底确认路径。Elicitation 是后续增强路径，只有外部 Host 支持并批准时才会使用。

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

外部 Host 可以再次调用 `call_upstream_tool`，并携带相同的：

- `recommendation_id`
- `route_token`
- `capability_id`
- `arguments`
- `pending_action_id`

如果待确认操作有效、没有过期，并且能力、风险等级和参数都完全匹配，`mcp-conductor` 才会执行上游工具。

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

## 后续 Elicitation 集成

当前的兜底确认路径使用 `pending_action_id`。

当后续接入 Host Elicitation 时，推荐流程是：

```text
高风险调用
  -> mcp-conductor 请求 Host 发起 Elicitation
  -> Host 向用户询问确认
  -> 用户接受后映射为待确认操作的确认结果
  -> 网关完成校验后才执行
```

如果 Host 不支持 Elicitation，现有的 `confirmation_required` 响应仍然作为兜底方案保留。
