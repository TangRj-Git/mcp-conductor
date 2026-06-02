# 使用模型

## 对外像普通 MCP Server 一样配置

`mcp-conductor` 必须对外保持标准 MCP Server 形态。

推荐的使用模型不是“把所有 MCP Server 都配置到外部 Host”，而是：

```text
外部 Host 只配置 mcp-conductor。
mcp-conductor 内部再配置多个上游 MCP Server。
```

这样外部模型每轮只需要理解少量高级工具，再优先通过 `analyze_user_task` 获取当前任务相关的候选能力。`recommend_capabilities` 保留为较底层入口。

本地开发时，外部 Host 可以这样配置：

```json
{
  "mcpServers": {
    "mcp-conductor": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "E:\\SoftwareProject\\mcp-conductor",
        "mcp-conductor"
      ]
    }
  }
}
```

当前项目已经在 `pyproject.toml` 中定义：

```toml
[project.scripts]
mcp-conductor = "mcp_conductor.cli:main"
```

因此 `uv run mcp-conductor` 是当前正式本地入口。顶层 `main.py` 已删除，后续不要再把业务逻辑写回顶层入口文件。

发布后可以考虑：

```json
{
  "mcpServers": {
    "mcp-conductor": {
      "command": "uvx",
      "args": [
        "--from",
        "mcp-conductor",
        "mcp-conductor"
      ]
    }
  }
}
```

## 内部上游 MCP Server 配置

`mcp-conductor` 内部还需要自己的上游配置文件，用来连接其他 MCP Server。

示例：

```json
{
  "upstreamServers": {
    "github": {
      "transport": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_TOKEN": "${GITHUB_TOKEN}"
      },
      "cwd": "E:\\SoftwareProject\\mcp-conductor",
      "disabled": false,
      "risk_policy": "read_only_only"
    },
    "filesystem": {
      "transport": "stdio",
      "command": "npx",
      "args": [
        "-y",
        "@modelcontextprotocol/server-filesystem",
        "E:\\SoftwareProject"
      ],
      "disabled": false,
      "risk_policy": "read_only_only"
    }
  }
}
```

这份配置由 `mcp-conductor` 读取，不由外部 Host 直接读取。

内部配置当前已经支持 `upstreamServers` 和 `mcpServers` 两种键名，已支持 `stdio` 和 `streamable_http` 两种传输类型。

本地默认加载流程：

```text
uv run mcp-conductor
  -> CLI 检查当前工作目录是否存在 mcp-conductor.config.json
  -> 存在则把它作为内部上游配置文件
  -> load_config 先加载该配置文件同目录下的 .env
  -> parse_config 解析 mcpServers / upstreamServers
  -> 对 command / args / url / cwd / env / allowed_roots 中的 ${NAME} 做环境变量替换
  -> GatewayRuntime 根据解析结果创建上游 Client
```

显式传入 `--config` 时优先使用该路径：

```bash
uv run mcp-conductor --config E:\SoftwareProject\mcp-conductor\mcp-conductor.config.json
```

如果没有显式 `--config`，且当前工作目录没有 `mcp-conductor.config.json`，则使用空配置启动。此时 `mcp-conductor` 仍能启动，但不会发现任何上游能力。

`.env` 加载规则：

- 只加载配置文件同目录下的 `.env`。
- 只支持简单 `KEY=VALUE` 行。
- 空行和 `#` 注释会被忽略。
- 不覆盖当前进程中已经存在的同名环境变量。
- 支持单引号或双引号包裹值。
- 缺失 `${NAME}` 对应环境变量时，配置解析会失败。

`risk_policy` 第一版确定保留少量枚举：

```text
read_only_only
  默认值，只允许风险策略确认后的只读能力自动执行。

confirm_mutations
  允许发现危险能力，但执行前必须 Elicitation 或 pending_action_id 确认。

disabled
  禁用该上游 Server 或能力。
```

## 推荐配置关系

推荐：

```text
外部 Host
  只配置 mcp-conductor

mcp-conductor
  内部配置 github/filesystem/database 等上游 MCP Server
```

在这个推荐关系下，实际连接模型是：

```text
外部 Host
  └─ Client：mcp-conductor ── mcp-conductor 服务

mcp-conductor
  ├─ Client: github ── github MCP Server
  ├─ Client: filesystem ── filesystem MCP Server
  └─ Client: database ── database MCP Server
```

外部 Host 只需要管理一个 MCP Client，也就是连接 `mcp-conductor` 的 Client。上游多个 MCP Server 的 Client 由 `mcp-conductor` 内部管理。

不推荐：

```text
外部 Host
  同时配置 mcp-conductor、github、filesystem、database
```

不推荐的原因是：外部模型仍然可能看到大量底层工具，`mcp-conductor` 无法替外部 Host 隐藏这些工具。

如果 Codex、Claude Code 等多个外部 Host 同时配置 `mcp-conductor`，通常会启动多个独立 `mcp-conductor` 进程。每个进程都会维护自己的上游 Client/session 和缓存，因此 stdio 上游 Server 可能被重复启动，固定端口服务可能冲突，写入类操作也可能被重复触发。第一版不做跨进程协调。

## 对外暴露工具

当前第一版对外暴露少量高层工具：

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

这样外部模型只需要理解 `mcp-conductor` 这几个高级工具，而不是直接面对所有上游工具。

`analyze_user_task` 是推荐的首选入口，适合 Codex、Claude Code 等 Host 在用户任务开始时或 agent loop 中的某个步骤调用。`recommend_capabilities` 保留为较底层的推荐工具。

`list_exposed_capabilities` 是 exposure/proxy/hybrid 方向的诊断入口。它只展示当前配置下哪些 read-only 上游 tool 会进入暴露计划，不代表这些上游 tool 已经被动态注册为 Host 可直接看到的 MCP tools。

`ask_conductor` 是后续可选增强工具。它需要 Host 支持 Sampling，否则只能退化为规则/标签推荐；它不能替代当前 `analyze_user_task/recommend_capabilities -> 具体访问工具` 的受控链路。

## 典型调用流程

更完整的端到端流程见 `09-end-to-end-flow.md`。下面只保留简版主链路。

```text
用户向外部 Host 提问
  ↓
外部模型优先调用 mcp-conductor 的 analyze_user_task
  ↓
mcp-conductor 分析任务，从上游能力中筛选候选能力
  ↓
mcp-conductor 返回候选能力、schema、recommendation_id / route_token、next_public_tool 和 ready_to_call_arguments
  ↓
外部模型使用推荐项中的 next_public_tool 和 ready_to_call_arguments 调用对应公开工具
  ↓
mcp-conductor 校验推荐凭证、schema、risk_policy 和 Roots/allowlist
  ↓
mcp-conductor 根据能力注册表找到对应上游 Client
  ↓
mcp-conductor 通过该 Client 调用对应上游 MCP Server
  ↓
mcp-conductor 裁剪、摘要、缓存结果
  ↓
外部模型拿到整理后的结果并回答用户
```

## 重要限制

`mcp-conductor` 作为 MCP Server，不能强制外部模型一定先调用自己，也不能控制外部 Host 暴露其他 MCP Server 的工具。

它和外部 Host 的职责边界是：

```text
外部 Host
  管用户输入、模型调用、对话上下文、工具暴露和最终回答。

mcp-conductor
  管内部上游 MCP Server、上游 Client、能力筛选、调用转发和结果整理。
```

因此，项目价值依赖于推荐的配置方式：

```text
外部 Host 只配置 mcp-conductor
其他 MCP Server 作为 mcp-conductor 的内部上游
```

如果要让每次用户输入和每次内部 agent loop 步骤都必须先经过能力筛选，需要把 `mcp-conductor` 放到一个更外层的 Host wrapper 或 Agent Orchestrator 后面。这个外层运行时负责主动调用 `analyze_user_task` 或后续 `analyze_agent_step`，而不是等待 Codex、Claude Code 自己决定是否调用。
