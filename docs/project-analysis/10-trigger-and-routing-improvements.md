# Trigger and routing improvements

本文记录当前针对 `mcp-conductor` 触发体验、推荐结果可执行性和 Host 边界问题做出的修正。

## 背景

普通 MCP Server 在 Codex、Claude Code 这类 Host 里不会主动接管 agent loop。Host 内部会不断分析任务、选择工具、读取结果并继续循环，但是否调用某个 MCP tool 仍然由 Host/模型决定。

因此，`mcp-conductor` 不能强制每一次用户输入或每一次内部循环都先经过自己。它能做的是：

```text
Host 决定调用 mcp-conductor
  -> mcp-conductor 分析当前任务或当前 loop 状态
  -> 返回推荐能力和安全访问凭证
  -> Host 根据推荐结果继续调用对应公开工具
```

如果未来要强制每轮都先筛选工具，需要在 `mcp-conductor` 外层实现 Host wrapper、agent runtime 或 IDE/plugin 层编排，而不是只靠 MCP Server 本身完成。

## 当前修正

### 1. 新增 `analyze_user_task`

新增公开工具 `analyze_user_task`，作为更适合 Host 自动触发的入口。

它和 `recommend_capabilities` 共享底层推荐逻辑，但命名更贴近模型在 agent loop 中的决策场景：

```text
当前任务可能需要任何已配置上游 MCP 能力
  -> 先调用 analyze_user_task
```

### 2. 强化 server instructions

`server.py` 中的 MCP server instructions 已更新为更明确的跨工具指导：

- 当前 server 是多个上游 MCP server 的 gateway。
- 当任务可能需要外部 MCP 工具、资源、prompt、文档、浏览器、仓库、数据库、文件系统或其他已配置能力时，优先调用 `analyze_user_task`。
- 推荐结果中会提供 `next_public_tool` 和 `ready_to_call_arguments`，Host 可以直接按该字段继续访问上游能力。

这比依赖用户手动在 `CLAUDE.md` 或其他说明文件里写触发规则更稳，但仍然不能保证 Host 每轮一定调用。

### 3. 推荐结果变成下一步可执行

推荐项现在会包含：

```json
{
  "next_public_tool": "read_upstream_resource_template",
  "example_arguments": {
    "name": "tool"
  },
  "ready_to_call_arguments": {
    "recommendation_id": "rec_...",
    "route_token": "route_...",
    "capability_id": "learn.resource_templates....",
    "arguments": {
      "name": "tool"
    },
    "routing_session_id": "session_..."
  },
  "usage_hint": "Use read_upstream_resource_template with ready_to_call_arguments ..."
}
```

这样模型不需要自己猜：

```text
tool -> call_upstream_tool
resource -> read_upstream_resource
resource_template -> read_upstream_resource_template
prompt -> get_upstream_prompt
```

### 4. 补强 `example_arguments`

`example_arguments` 不再只是空字段。当前会根据推荐能力的 schema 生成最小示例参数：

- integer/number -> `1`
- boolean -> `true`
- enum -> 第一个 enum 值
- topic/subject -> `tools`
- level/audience -> `beginner`
- concept/name 类资源模板会根据 URI/描述生成类似 `tool`、`tools` 或 `basic-tool` 的示例值

这主要解决 resource template 容易把 `tool` 填成 `tools` 之类的问题。

### 5. `context_summary` 参与推荐

`recommend_capabilities` 和 `analyze_user_task` 现在会把 `context_summary` 合并进匹配文本。

这让 Host 在 agent loop 中可以传入当前步骤、已有结果、失败原因或子任务状态，从而让推荐更贴近当前循环，而不是只看最初用户问题。

### 6. 能力列表支持过滤和统计

`list_upstream_capabilities` 现在支持：

- `capability_type`
- `upstream_server_id`
- `query`
- `cursor`
- `limit`

返回值新增：

- `total_count`
- `filtered_count`
- `type_counts`
- `upstream_counts`

这样在 69 个或更多上游能力存在时，Host 或用户可以先看整体分布，再定位某一类能力。

### 7. 错误返回包含 `next_step`

常见错误现在会返回下一步修复建议，例如：

- `invalid_route_token`：重新使用该 capability 对应的 route_token，或重新调用 `analyze_user_task`。
- `recommendation_expired`：重新推荐获取新的短期 token。
- `invalid_capability_type`：使用推荐项里的 `next_public_tool`。
- `invalid_arguments`：按照 `input_schema` 修正参数后重试。
- `roots_not_configured`：配置 `allowed_roots` 后再使用路径类参数。

目标是降低 Host/模型在工具调用失败后的卡住概率。

### 8. 配置环境变量展开增强

环境变量引用现在支持：

- `command`
- `args`
- `url`
- `cwd`
- `env`
- `allowed_roots`

并支持嵌入式引用，例如：

```json
{
  "args": ["--from", "demo-server==${PACKAGE_VERSION}"],
  "url": "https://${HTTP_HOST}/mcp"
}
```

### 9. 新增 exposure plan 诊断能力

当前新增了 `exposure` 顶层配置和 `list_exposed_capabilities` 公开工具。

`exposure.mode` 支持：

```text
router
proxy
hybrid
```

其中 `router` 是默认模式，保持当前网关式使用方式：Host 只看到 `mcp-conductor` 的固定公开工具，然后通过 `analyze_user_task` / `recommend_capabilities` 获取推荐结果，再通过 route-token-gated public tools 访问上游能力。

`proxy` 和 `hybrid` 目前先实现为“暴露计划生成器”，不会直接把上游工具动态注册成新的 FastMCP tools。这样可以先验证：

- 哪些上游 read-only tool 会被选中。
- `include_upstreams` / `exclude_upstreams` 是否符合预期。
- `include_capability_types` / `exclude_capability_types` 是否符合预期。
- `include_capabilities` / `exclude_capabilities` 是否符合预期。
- `max_exposed_tools` 是否限制了暴露数量。
- 风险策略、禁用上游、禁用能力是否正确阻止暴露。

这一步是后续真正实现 proxy/hybrid 动态工具注册前的安全前置层。

为了避免上游能力数量很多时诊断结果过大，`list_exposed_capabilities` 现在支持 `cursor` 和 `limit` 分页；`skipped_capabilities` 明细默认不返回，只在调用时显式传入 `include_skipped: true` 才返回。

## 仍未解决的问题

以下问题仍然不是当前 MCP Server 层能完全解决的：

1. `mcp-conductor` 不能强制 Codex/Claude Code 每次用户输入都调用它。
2. `mcp-conductor` 不能直接插入 Codex/Claude Code 内部每一轮 agent loop。
3. Host 仍然只看到 gateway 的公开工具；`list_exposed_capabilities` 只能展示计划，尚不会动态注册上游工具。
4. 当前推荐仍是规则/BM25 风格，不是完整 LLM semantic routing。
5. Proxy mode/hybrid mode 已有配置和计划生成器，但动态工具注册尚未实现。
6. Host Sampling 路由尚未实现。
7. 多上游健康检查、自动重连、动态 reload、持久化缓存仍是后续产品化工作。

## 和用户目标的差距

当前实现已经解决了：

- `mcp-conductor` 内部可以配置多个上游 MCP Server。
- 可以发现 tools/resources/resource templates/prompts。
- 可以把上游能力压缩成当前任务候选能力。
- 可以创建轻量 routing session，并通过 `analyze_agent_step` 只根据当前 loop 步骤重新推荐能力。
- 可以通过 `recommendation_id` 和 `route_token` 控制后续访问。
- 可以通过公开工具访问四类上游能力。
- 可以用 `list_exposed_capabilities` 查看将来 proxy/hybrid 的暴露计划。

当前还没有解决：

- 让 Codex / Claude Code 在每次用户输入开始时一定调用 `analyze_user_task`。
- 让 Codex / Claude Code 在每次内部 agent loop 步骤后一定重新调用 `mcp-conductor`。
- 让 Host 直接看到 `mcp-conductor` 内部筛选后的动态工具列表。
- 让 `proxy/hybrid` 计划真正动态注册为 FastMCP tools。
- 使用 Host Sampling 或语义检索做更强的智能路由。

因此，当前项目已经完成 Gateway 侧的主要配套能力，但还没有完成 Host/Agent Orchestrator 侧的强制编排能力。

## 后续建议

下一阶段优先级建议：

```text
P1: 增加本地 demo orchestrator，证明“每轮筛选 -> 模型选择 -> route-gated 执行 -> 下一轮”的流程
P2: 在已有 exposure plan 基础上实现 proxy / hybrid 动态工具注册
P3: 引入 Host Sampling / 语义检索作为可选增强
P4: 增加多上游健康检查、重连和配置 reload
P5: 如果需要强制接管 Codex / Claude Code，则开发独立 Host wrapper / Agent Orchestrator
```

Gateway Core 的 step-routing API 已经落地。真正强制每轮触发，仍需要独立 Host wrapper / Agent Orchestrator。
