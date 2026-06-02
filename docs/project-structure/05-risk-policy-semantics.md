# 风险策略语义

## 文档目的

这份文档记录上游风险策略的语义边界。

它主要回答三个问题：

1. 每个上游 Server 可以配置哪些风险策略。
2. 不同策略如何影响能力推荐和工具执行。
3. 为什么推荐层过滤不能替代执行层校验。

## 策略

`mcp-conductor` 第一版支持三种上游风险策略：

- `read_only_only`
- `confirm_mutations`
- `disabled`

风险策略按上游 Server 单独配置。

## 风险推断优先级

工具 annotations 中的 `readOnlyHint` 只能作为提示，不能作为最终安全事实。

当前本地推断优先级是：

1. `destructiveHint: true` 直接视为 `destructive`。
2. 工具名或描述中出现删除、移除、清空等破坏性信号时，优先视为 `destructive`，即使上游同时给了 `readOnlyHint: true`。
3. 工具名或描述中出现写入、发送、发布、创建、支付等强变更信号时，优先视为 `mutating`。
4. 剩余场景才接受 `readOnlyHint: true` 作为只读提示。
5. `readOnlyHint: false` 不会自动视为 mutating，但会阻止它被简单只读关键词判成只读。

执行层仍以最终 `risk_level` 为准，而不是盲信上游 hint。

## read_only_only 策略

只有 `read_only` 能力可以被推荐和执行。

如果非只读能力通过某种方式进入执行层，执行层仍然会拒绝，并返回：

```json
{
  "status": "error",
  "error_code": "risk_policy_denied"
}
```

这个策略不会为变更型、破坏型或未知风险操作创建 `pending_action_id`。

## confirm_mutations 策略

只读能力在推荐和校验通过后可以直接执行。

变更型、破坏型或未知风险能力可以被推荐，但推荐结果会标记：

```json
{
  "requires_confirmation": true
}
```

执行时会进入危险操作确认流程：

```text
第一次调用 -> confirmation_required + pending_action_id
第二次调用并携带匹配的 pending_action_id -> 只执行一次
```

## disabled 策略

被禁用的上游 Server 会在启动阶段被跳过。

推荐层和执行层也会把 `risk_policy: "disabled"` 作为最终保护：

- 不推荐来自该上游的任何能力。
- 即使存在过期的只读能力缓存，执行时也会被拒绝。

## 分层

风险策略在两个位置生效：

1. 推荐过滤：避免把不可用能力推荐给模型。
2. 执行校验：在任何上游工具调用发生前，作为最后的权限边界。
