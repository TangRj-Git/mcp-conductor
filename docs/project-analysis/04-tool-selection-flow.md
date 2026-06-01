# 工具筛选流程

## 核心原则

`mcp-conductor` 对外是一个标准 MCP Server，不直接控制外部 Host 的全部工具上下文。

它能控制的是：

- 自己对外暴露哪些高级工具。
- 内部连接哪些上游 MCP Server。
- 如何从上游能力中筛选候选能力。
- 如何调用上游工具。
- 如何裁剪和缓存上游返回结果。

## 推荐使用方式

如果想减少外部模型看到的工具数量，推荐：

```text
外部 Host 只配置 mcp-conductor
mcp-conductor 内部配置多个上游 MCP Server
```

不推荐在外部 Host 中同时直接配置大量上游 MCP Server，否则外部模型仍然会看到大量底层工具。

## 内部筛选流程

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
网关执行引擎调用上游 MCP Server
  ↓
Result Manager 裁剪和缓存结果
  ↓
mcp-conductor 返回摘要、预览或 result_id
```

注意：第一版不允许外部模型直接凭空指定任意上游能力执行。推荐链路必须先经过 `recommend_capabilities`，再由 `call_upstream_tool` 携带 `recommendation_id` 和 `route_token` 进入执行链路。

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

当规则筛选或 Host 采样路由器选中某个能力后，网关执行引擎根据 `capability_id` 找到对应上游 Client，再通过这个 Client 调用对应 Server。

## 子代理的作用

路由代理是工具筛选子代理。它负责推荐能力，但不负责真正调用上游工具。

在本项目中，路由代理不由 `mcp-conductor` 自己私自创建模型实例。它应优先实现为 Host 采样路由器：`mcp-conductor` 通过 MCP Sampling 请求外部 Host 使用其受控模型完成一次路由推理。Host 可以拒绝请求、要求用户确认或选择不同模型。

如果 Host 不支持 Sampling，`mcp-conductor` 必须回退到规则/标签筛选。

路由代理输入：

```text
用户当前任务
对话简要上下文
候选工具卡片列表
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
4. 网关执行引擎：只自动执行被风险策略确认后的只读上游工具。

第二阶段再加入：

1. 语义检索：从工具卡片中召回前 30 到前 50 个候选能力。
2. Host 采样路由器：通过 Sampling 从候选能力中选择前 5 到前 15 个能力。
3. `ask_conductor`：完成分析任务、选择能力、调用上游、整理结果的完整流程。

## 对外工具设计

第一版对外不应该暴露上游所有工具，而是暴露少量高级工具：

```text
list_upstream_capabilities
recommend_capabilities
call_upstream_tool
read_result
```

其中：

- `list_upstream_capabilities` 用于查看内部发现到的能力摘要。
- `recommend_capabilities` 用于根据用户任务推荐上游能力。
- `call_upstream_tool` 用于调用指定的上游 tool，必须传入 `recommendation_id`、`route_token`、`capability_id` 和 `arguments`，并通过推荐凭证、schema、安全策略、Roots/allowlist 和风险检查。
- `read_result` 用于读取缓存的大结果分页或完整内容。

`call_upstream_tool` 的执行规则：

- 只能调用当前有效推荐结果中的 tool。
- `route_token` 是不透明 token，外部模型不能构造或修改。
- 推荐结果过期、`route_token` 不匹配、能力已禁用、参数不符合 schema、风险策略不允许时，都必须拒绝执行。
- 未知风险能力默认按危险处理。

`ask_conductor` 是第二阶段或可选增强工具，依赖 Host Sampling。

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
- 不缓存 secrets、token 和敏感凭证。
