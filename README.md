# mcp-conductor

`mcp-conductor` is an MCP gateway server. It exposes a small set of public MCP tools to an external host, then internally connects to and manages multiple upstream MCP servers.

In plain terms:

```text
External host, such as Codex or Claude Code
  -> connects to mcp-conductor as one MCP server
  -> mcp-conductor loads configured upstream MCP servers
  -> mcp-conductor discovers upstream tools/resources/prompts
  -> mcp-conductor recommends and validates which upstream capability may be used
```

The current project is an MVP. It already supports upstream configuration loading, upstream client lifecycle, capability discovery, token/BM25-style recommendation with CJK term matching, lightweight step-routing sessions, route-token validation, controlled tool/resource/template/prompt access, risk policy checks, path allowlists, host elicitation for risky actions when supported, and session-scoped result caching.

The most important public entrypoint is `analyze_user_task`. It lets Codex, Claude Code, or another MCP host ask the gateway which configured upstream capabilities are relevant for the current task or agent-loop step.

For host wrappers or agent runtimes that want to route every loop step, the gateway also exposes `start_routing_session`, `analyze_agent_step`, `list_routing_session_state`, and `end_routing_session`. These tools provide a step-routing API, but they still cannot force Codex or Claude Code to call them automatically; that requires a wrapper/orchestrator outside the MCP server.

## Requirements

- Python `>=3.13`
- `uv`
- Optional upstream runtimes depending on your upstream MCP servers, for example `uvx`, `npx`, or `node`

Install dependencies:

```bash
uv sync
```

Check the CLI:

```bash
uv run mcp-conductor --version
```

## Configuration

The default local config file name is:

```text
mcp-conductor.config.json
```

When you run `mcp-conductor` from a directory containing this file, the CLI automatically uses it. You can also pass an explicit config path:

```bash
uv run mcp-conductor --config .\mcp-conductor.config.json
```

The config supports both `mcpServers` and `upstreamServers`. `mcpServers` is convenient because it matches the common MCP client config shape.

Example:

```json
{
  "mcpServers": {
    "learn-mcp-server": {
      "transport": "stdio",
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

Common upstream fields:

```json
{
  "transport": "stdio",
  "command": "uvx",
  "args": ["--from", "example-package", "example-command"],
  "cwd": ".",
  "env": {
    "EXAMPLE_TOKEN": "${EXAMPLE_TOKEN}"
  },
  "disabled": false,
  "risk_policy": "read_only_only",
  "roots_policy": "config_allowlist_only",
  "allowed_roots": ["E:\\SoftwareProject\\allowed"]
}
```

Supported `risk_policy` values:

```text
read_only_only
confirm_mutations
disabled
```

Supported `roots_policy` values:

```text
host_roots_or_config_allowlist
config_allowlist_only
```

`read_only_only` is the safest default. Mutating or unknown-risk tools are not recommended or executed under that policy. Use `confirm_mutations` only for upstream servers you trust and want to allow through the host confirmation flow.

Optional exposure planning:

```json
{
  "exposure": {
    "mode": "router",
    "include_upstreams": ["learn-mcp-server"],
    "exclude_upstreams": [],
    "include_capability_types": ["tool"],
    "exclude_capability_types": [],
    "include_capabilities": [],
    "exclude_capabilities": [],
    "max_exposed_tools": 50
  }
}
```

Supported `exposure.mode` values:

```text
router
proxy
hybrid
```

`router` is the default and preserves the current gateway behavior: the host sees the fixed public tools, then asks the gateway to recommend and route upstream capabilities.

`proxy` and `hybrid` currently generate a deterministic exposure plan only. They do not dynamically register upstream tools as separate FastMCP tools yet. Use `list_exposed_capabilities` to inspect which read-only upstream tools would be selected by the current filters and risk policy.

`include_capability_types` and `exclude_capability_types` accept only `tool`, `resource`, `resource_template`, and `prompt`. Direct proxy planning currently selects read-only `tool` capabilities only.

## Environment Variables

Yes, this project can read `.env` files.

When `load_config()` reads a config file, it first loads a `.env` file from the same directory as that config file. Existing shell environment variables are not overwritten.

For example, if you have:

```text
mcp-conductor.config.json
.env
```

and the config contains:

```json
{
  "env": {
    "GITHUB_TOKEN": "${GITHUB_TOKEN}"
  }
}
```

then `.env` can contain:

```dotenv
GITHUB_TOKEN=your-token-here
```

Important details:

- `${NAME}` references are resolved in `command`, `args`, `url`, `cwd`, `env`, and `allowed_roots`.
- Embedded references such as `demo-server==${PACKAGE_VERSION}` are supported.
- `.env` is ignored by Git.
- Keep real secrets out of `mcp-conductor.config.json`.

## Run Locally

Start the MCP server with the default `stdio` transport:

```bash
uv run mcp-conductor
```

Start with an explicit config file:

```bash
uv run mcp-conductor --config .\mcp-conductor.config.json
```

Run through the Python module entrypoint:

```bash
uv run python -m mcp_conductor --version
```

## Inspect With FastMCP Inspector

You can use FastMCP Inspector to view and test this MCP server:

```bash
uv run fastmcp dev inspector --module mcp_conductor
```

Why `--module mcp_conductor`?

The project entrypoint is package-based:

```text
src/mcp_conductor/__main__.py
  -> mcp_conductor.cli.main()
  -> create_server(runtime)
```

So the inspector should run the package module, similar to:

```bash
python -m mcp_conductor
```

After the Inspector opens, connect through `STDIO`, then call:

```text
analyze_user_task
list_upstream_capabilities
list_exposed_capabilities
```

With the included `learn-mcp-server` config, this should show the discovered upstream capabilities. If you set `exposure.mode` to `proxy` or `hybrid`, `list_exposed_capabilities` also shows which read-only upstream tools match the exposure filters.

## Step Routing APIs

The repository keeps step-routing support inside the gateway server, but it does
not include a standalone agent runtime or model provider. A host, wrapper, IDE
plugin, or future orchestrator can use this server-side contract:

```text
start_routing_session
-> call the recommendation's next_public_tool with ready_to_call_arguments
-> pass the tool result summary to analyze_agent_step
-> deprioritize capabilities already called or failed in this routing session
-> inspect called_capability_ids and failed_capability_ids
```

This API still does not make Codex or Claude Code call `mcp-conductor`
automatically. Forced per-step routing belongs in host-side instructions, hooks,
wrappers, plugins, or a separate orchestrator.

## Public MCP Tools

`mcp-conductor` exposes these public tools:

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

Typical flow:

```text
1. analyze_user_task
   Pass the current task or agent-loop step.
   The gateway returns recommended capabilities, route tokens, next_public_tool,
   ready_to_call_arguments, example_arguments, and usage hints.

2. list_upstream_capabilities
   Optional diagnostic tool for inspecting discovered upstream capabilities.
   It supports pagination plus capability_type, upstream_server_id, and query filters.

3. start_routing_session
   Create a lightweight routing session for one user task and return the first
   route-token-gated recommendation. Its ready_to_call_arguments include
   routing_session_id so later tool/resource/prompt access can update the
   routing session diagnostics.

4. analyze_agent_step
   Analyze only the current loop step content for an existing routing session.
   It returns a new routing_round_id, recommendation_id, route tokens,
   next_public_tool, and ready_to_call_arguments with routing_session_id.

5. list_routing_session_state
   Inspect compact routing session state. It returns summaries and capability ids,
   not the full conversation.

6. end_routing_session
   Release in-memory routing session state.

7. list_exposed_capabilities
   Optional diagnostic tool for inspecting the current proxy/hybrid exposure plan.
   It supports cursor/limit pagination. Skipped capability details are hidden by default;
   pass include_skipped=true when you need the diagnostic reasons.
   Dynamic proxy registration is not enabled yet.

8. recommend_capabilities
   Lower-level alias for task-based recommendations.

9. call_upstream_tool
   Call one recommended tool with recommendation_id, route_token, capability_id,
   arguments, and optional routing_session_id.

10. read_upstream_resource
   Read one recommended resource with recommendation_id, route_token,
   capability_id, and optional routing_session_id.

11. read_upstream_resource_template
   Expand one recommended resource template with validated arguments, then read it.
   It accepts optional routing_session_id.

12. get_upstream_prompt
   Get one recommended prompt with recommendation_id, route_token, capability_id,
   arguments, and optional routing_session_id.

13. read_result
   Read cached large results when call_upstream_tool returns a result_id.
   Large result caching requires a host session id; without one, the gateway returns
   a summary/preview but no result_id.
```

`list_upstream_capabilities` returns `total_count`, `filtered_count`, `type_counts`, and `upstream_counts` so hosts and humans can quickly understand what was discovered before paging through individual capabilities.

Each recommendation includes a model-friendly continuation payload:

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

## Tests

Run the full test suite:

```bash
uv run pytest
```

Run compile checks:

```bash
uv run python -m compileall -q src tests scripts
```

Run lint checks:

```bash
uv run ruff check .
```

Build the package:

```bash
uv build
```

Optional real-upstream smoke test:

```bash
uv run python scripts/smoke_learn_mcp.py
```

The learn MCP smoke script starts `GatewayRuntime` with `mcp-conductor.config.json`, discovers upstream capabilities, recommends real `learn-mcp-server` capabilities, and verifies route-token-gated access for one tool, one resource, one resource template, and one prompt.

To only verify discovery:

```bash
uv run python scripts/smoke_learn_mcp.py --discovery-only
```

You can also run the discovery-only check inline:

```bash
uv run python - <<'PY'
import asyncio
from mcp_conductor.runtime import GatewayRuntime

async def main():
    runtime = GatewayRuntime(config_path="mcp-conductor.config.json")
    await runtime.async_startup()
    try:
        result = runtime.list_upstream_capabilities(limit=200)
        print(result["status"])
        print(result["total_count"])
        print(result["type_counts"])
        print(result["unavailable_upstreams"])
        print(result["discovery_errors"])
    finally:
        await runtime.async_shutdown()

asyncio.run(main())
PY
```

On Windows PowerShell, use a here-string instead:

```powershell
@'
import asyncio
from mcp_conductor.runtime import GatewayRuntime

async def main():
    runtime = GatewayRuntime(config_path="mcp-conductor.config.json")
    await runtime.async_startup()
    try:
        result = runtime.list_upstream_capabilities(limit=200)
        print(result["status"])
        print(result["total_count"])
        print(result["type_counts"])
        print(result["unavailable_upstreams"])
        print(result["discovery_errors"])
    finally:
        await runtime.async_shutdown()

asyncio.run(main())
'@ | uv run python -
```

## Project Structure

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
  exposure/
  policy/
  results/
  primitives/
  public_tools/

scripts/
  smoke_learn_mcp.py
```

Important files:

```text
src/mcp_conductor/runtime.py
src/mcp_conductor/config/loader.py
src/mcp_conductor/config/env.py
src/mcp_conductor/upstream/client.py
src/mcp_conductor/upstream/manager.py
src/mcp_conductor/discovery/service.py
src/mcp_conductor/routing/rules.py
src/mcp_conductor/routing/session.py
src/mcp_conductor/exposure/planner.py
src/mcp_conductor/policy/risk.py
src/mcp_conductor/policy/roots.py
```

## Current Limitations

- Recommendation is currently token/BM25-style local ranking with lightweight CJK term matching, not full semantic retrieval.
- The gateway cannot force Codex, Claude Code, or another external host to call it on every user message or every internal agent-loop step. The host decides when to call MCP tools.
- The gateway does not act as a full MCP Host or agent runtime.
- Proxy/hybrid exposure planning is implemented through config and `list_exposed_capabilities`, but dynamic registration of upstream tools as separate host-visible MCP tools is not implemented yet.
- Host Sampling based semantic routing is reserved for a future version.
- The gateway does not own the external model lifecycle.
- Risk confirmation uses FastMCP `Context.elicit()` when the connected host supports elicitation. Hosts that do not support elicitation still receive a `confirmation_required` response and the action remains blocked until a trusted host integration confirms the pending action.
- Resource, resource template, and prompt capabilities can now be recommended and accessed through route-token-gated public tools. Resource template arguments are validated and expanded with support for common URI Template operators such as simple variables, reserved path expansion, and query parameters.

More architecture notes are in:

```text
docs/project-analysis/
docs/project-structure/
```
