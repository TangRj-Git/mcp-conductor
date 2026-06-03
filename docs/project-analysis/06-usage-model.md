# Usage Model

## Recommended Configuration

`mcp-conductor` should be configured as the only external MCP server in hosts
such as Codex, Claude Code, Cursor, or another MCP host:

```text
External Host
  -> mcp-conductor
```

The upstream MCP servers are configured inside `mcp-conductor`:

```text
mcp-conductor
  -> upstream GitHub MCP server
  -> upstream filesystem MCP server
  -> upstream documentation MCP server
```

This is the point of the gateway design. The external host sees a small public
tool surface, while the gateway manages the larger upstream capability set.

## Host Configuration Example

Local development example:

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

Published-package example:

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

## Internal Upstream Configuration

`mcp-conductor` reads its own gateway config file, usually:

```text
mcp-conductor.config.json
```

This file can use either `mcpServers` or `upstreamServers`.

Example:

```json
{
  "mcpServers": {
    "learn-mcp-server": {
      "command": "uvx",
      "args": [
        "--from",
        "learn-mcp-server==0.1.0",
        "learn-mcp-server"
      ],
      "risk_policy": "read_only_only"
    }
  }
}
```

Environment variables are loaded from a `.env` file next to the selected config
file before `${NAME}` placeholders are expanded.

## Public Tool Surface

The host sees the gateway's public tools:

```text
analyze_user_task
start_routing_session
analyze_agent_step
list_routing_session_state
end_routing_session
list_upstream_capabilities
list_exposed_capabilities
recommend_capabilities
call_upstream_tool
read_upstream_resource
read_upstream_resource_template
get_upstream_prompt
read_result
```

Recommended flow:

```text
User task
  -> host calls analyze_user_task
  -> mcp-conductor recommends selected upstream capabilities
  -> host/model chooses one recommendation
  -> host calls next_public_tool with ready_to_call_arguments
  -> mcp-conductor validates route token, risk policy, and arguments
  -> mcp-conductor calls the selected upstream MCP server
  -> mcp-conductor returns a compact result, preview, or result_id
```

## Step Routing

The current repository keeps server-side step-routing APIs:

```text
start_routing_session
analyze_agent_step
list_routing_session_state
end_routing_session
```

These APIs let an external wrapper or custom Host route each current loop step
through the gateway. They do not force Codex or Claude Code to call them.

To force routing before every user message or every loop step, build that logic
outside the MCP server:

```text
Host wrapper / plugin / custom Host
  -> calls mcp-conductor routing tools at the required moments
  -> gives the selected capability surface to its model
  -> sends the chosen route-token-gated call back to mcp-conductor
```

## Removed Non-Core Runtime

The repository no longer includes a standalone local agent runtime, model
provider adapter, or provider-specific smoke script. That keeps the package
focused on its actual product boundary: an MCP Gateway Server.

Future host-side orchestration can still be developed as a separate package,
plugin, wrapper, or example project.

## Important Limits

- `mcp-conductor` cannot force external hosts to call any specific tool.
- `mcp-conductor` cannot own the external model lifecycle.
- `mcp-conductor` cannot hide other MCP servers if the host also configures them
  directly.
- In router mode, upstream capabilities are accessed only after a recommendation
  returns `recommendation_id`, `route_token`, `next_public_tool`, and
  `ready_to_call_arguments`.
