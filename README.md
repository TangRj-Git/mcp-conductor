# mcp-conductor

`mcp-conductor` 是一个 MCP Gateway Server。

它对外可以像普通 MCP Server 一样配置到 Codex、Claude Code、Cursor 等外部 Host 中；对内则可以通过自己的 MCP Client/session 管理多个上游 MCP Server，并把大量上游能力收拢到少量受控的对外工具后面。

当前定位：

```text
对外：标准 MCP Server
对内：上游 Client 管理器 + 能力路由 + 网关运行时
```

## 当前状态

项目仍处于早期 MVP 阶段，但主要网关链路已经接起来：

- FastMCP 服务生命周期会启动和关闭网关运行时。
- 运行时可以从 `upstreamServers` 或 `mcpServers` 加载内部上游配置。
- 每个启用的上游 Server 会创建一个独立 Client/session。
- 上游连接失败会被隔离，并通过 `list_upstream_capabilities` 的 `unavailable_upstreams` 返回。
- 能力发现的局部失败会被隔离，并通过 `discovery_errors` 返回。
- tools、resources、resource templates 和 prompts 会被发现并进入能力注册表。
- `recommend_capabilities` 会返回候选工具能力和 `route_token`。
- `call_upstream_tool` 会在执行前校验 `recommendation_id`、`route_token`、schema、能力类型和风险策略。
- 上游工具执行失败会返回结构化的 `upstream_tool_error`。
- 路径类参数可以通过 `roots_policy` 和 `allowed_roots` 约束。
- 只读上游工具可以通过网关执行。
- 非只读或未知风险工具必须在 `risk_policy: "confirm_mutations"` 下进入确认流程。
- 高风险调用需要使用返回的 `pending_action_id` 二次调用；同一个待确认操作只能使用一次，并且参数不能变化。
- 大列表结果会返回预览，并通过 `result_id` 缓存完整结果；小结果会直接放在 `data` 中。

下一步重点是接入一个低风险真实上游 MCP Server，跑通真实的能力发现、推荐、调用和结果返回链路。

## 入口命令

查看 CLI 版本：

```bash
uv run mcp-conductor --version
```

通过 Python 模块入口查看版本：

```bash
uv run python -m mcp_conductor --version
```

使用默认 `stdio` 传输启动 MCP Server：

```bash
uv run mcp-conductor
```

指定内部上游配置启动：

```bash
uv run mcp-conductor --config .\mcp-conductor.config.json
```

## 上游配置示例

内部上游配置可以使用 `mcpServers`：

```json
{
  "mcpServers": {
    "github": {
      "transport": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_TOKEN": "${GITHUB_TOKEN}"
      }
    },
    "filesystem": {
      "transport": "stdio",
      "command": "npx",
      "args": [
        "-y",
        "@modelcontextprotocol/server-filesystem",
        "E:\\SoftwareProject"
      ],
      "roots_policy": "config_allowlist_only",
      "allowed_roots": ["E:\\SoftwareProject\\allowed"],
      "risk_policy": "read_only_only"
    }
  }
}
```

同样的配置结构也可以放在 `upstreamServers` 下。

如果希望某个上游不参与启动和发现，可以设置：

```json
{
  "disabled": true
}
```

或者：

```json
{
  "risk_policy": "disabled"
}
```

真实凭证不要写进配置文件。配置中应该使用 `${ENV_NAME}` 引用环境变量，真实值放在本地 `.env` 或当前 shell 环境中。

## 项目结构

```text
src/mcp_conductor/
  cli.py
  server.py
  runtime.py
  config/
  upstream/
  discovery/
  registry/
  routing/
  execution/
  policy/
  results/
  primitives/
  public_tools/
```

项目分析和架构说明保存在：

- `docs/project-analysis/`
- `docs/project-structure/`

## 第一版范围

第一版聚焦一个保守的 Gateway MVP：

- 对外只暴露少量高级 MCP tools。
- 加载内部上游 MCP Server 配置。
- 为每个上游 Server 维护独立 Client/session。
- 发现上游能力。
- 使用推荐凭证约束后续执行链路。
- 只执行经过校验并被策略允许的上游工具调用。
- 对大结果做裁剪、预览和缓存。

`mcp-conductor` 不是完整 MCP Host。它不管理用户对话，不拥有外部模型生命周期，也不能绕过外部 Host 私自做模型 Sampling 或危险操作确认。
