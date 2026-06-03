# Step Routing And Host-Orchestrator Boundary

## Purpose

This document keeps the engineering boundary clear after the project was
trimmed back to its main product shape:

```text
mcp-conductor is an MCP Gateway Server.
It exposes routing tools to external hosts.
It does not include a standalone model runtime or agent loop.
```

The gateway can support per-step routing through public MCP tools, but an
external host, wrapper, IDE plugin, or future separate orchestrator must decide
when to call those tools.

## Gateway Core Structure

The current repository keeps these server-side step-routing modules:

```text
src/mcp_conductor/
  routing/
    session.py
  public_tools/
    routing_session.py
    analyze_step.py
```

### `routing/session.py`

Responsibilities:

- Store lightweight routing sessions, not complete chat history.
- Track the original task summary, recent step summaries, recommended
  capability ids, called capability ids, and failed capability ids.
- Provide TTL pruning and maximum-session limits.
- Help rerank repeated recommendations within one routing session.

### `public_tools/routing_session.py`

Public tools:

```text
start_routing_session
list_routing_session_state
end_routing_session
```

These tools are useful for Inspector, smoke testing, and future host-side
orchestration. They do not force Codex, Claude Code, or any other MCP host to
call them.

### `public_tools/analyze_step.py`

Public tool:

```text
analyze_agent_step
```

The input is one current loop-step payload:

```json
{
  "session_id": "session_123",
  "step_index": 2,
  "step_type": "tool_result",
  "step_content": "The previous repository search failed; find documentation next.",
  "limit": 8
}
```

The result returns recommended capabilities plus route-token-gated
`ready_to_call_arguments`. It does not execute upstream tools by itself.

## Removed Prototype Layer

The repository no longer includes the standalone local agent/orchestrator
prototype, model-decision providers, or provider-specific smoke scripts. Those pieces were
removed because they made the package look like a full MCP Host or model
runtime, which is not the current product goal.

Removed scope:

```text
standalone agent CLI
local model-decision loop
provider-specific LLM adapters
provider-specific model smoke tests
agent-loop demo scripts
```

This keeps the package focused on the gateway:

```text
external Host
  -> mcp-conductor public routing tools
  -> internal upstream MCP clients
  -> route-token-gated upstream access
```

## Future Host-Orchestrator Shape

If the product later needs hard per-step routing, implement it outside this
gateway package. The outer runtime would:

```text
receive user input
-> call start_routing_session or analyze_user_task
-> expose the selected candidate capabilities to its model
-> receive a tool-call intent from the model
-> call mcp-conductor's route-token-gated public tool
-> pass the current result summary to analyze_agent_step
-> repeat until complete
```

Possible implementation locations:

- A separate Host wrapper.
- A separate CLI prototype outside the main package.
- A Codex or Claude Code hook/plugin layer.
- A custom MCP Host.

## Current Development Boundary

Gateway Core already supports:

- Upstream MCP server configuration.
- Upstream client lifecycle.
- Capability discovery.
- Task and step recommendation.
- Routing sessions.
- Route-token validation.
- Risk policy and controlled execution.
- Result caching and pagination.

Gateway Core does not support:

- Owning the external model lifecycle.
- Managing a complete user conversation.
- Forcing an external host to call routing tools.
- Dynamically changing Codex or Claude Code's internal agent loop.

That boundary is intentional.
