# 错误处理和发现容错

## 文档目的

这份文档记录错误处理和能力发现容错的结构边界。

它主要回答三个问题：

1. 上游工具执行失败时，`mcp-conductor` 应该如何向外部 Host 返回结构化错误。
2. 某个上游 Server 或某类能力发现失败时，是否应该影响其他上游能力。
3. `discovery_errors` 和 `unavailable_upstreams` 分别表达什么。

## 上游工具错误

`mcp-conductor` 会包装上游工具执行失败，而不是把异常直接抛给外部 Host。

当上游 `tools/call` 失败时，`call_upstream_tool` 会返回：

```json
{
  "status": "error",
  "error_code": "upstream_tool_error",
  "message": "Upstream tool call failed.",
  "details": {
    "capability_id": "github.tools.get_pr_checks",
    "upstream_server_id": "github",
    "error_type": "RuntimeError",
    "error": "..."
  }
}
```

同步和异步执行路径都使用同一种返回结构，方便外部 Host 统一处理错误。

## 发现容错

能力发现按上游 Server 和能力类型分别进行，整体采用尽力而为的策略。

如果某一次发现操作失败，例如 `tools/list` 失败，网关仍然会继续尝试：

- `resources/list`
- `resources/templates/list`
- `prompts/list`
- 其他上游 Server

发现失败会记录在 `CapabilityDiscoveryService.errors` 中，并通过 `list_upstream_capabilities` 的 `discovery_errors` 暴露出来。

示例：

```json
{
  "discovery_errors": [
    {
      "upstream_server_id": "github",
      "capability_type": "tool",
      "operation": "list_tools",
      "error": "tools unavailable"
    }
  ]
}
```

这和 `unavailable_upstreams` 是两个不同概念。`unavailable_upstreams` 表示连接启动阶段失败的上游 Server，而 `discovery_errors` 表示连接成功后，某类能力发现失败。

## 边界

网关会报告运行时失败和发现失败，但不会自动要求外部模型修复 Server 配置。

Host 或模型可以根据这些错误字段向用户解释为什么某些能力缺失，或者建议用户检查对应的上游配置。
