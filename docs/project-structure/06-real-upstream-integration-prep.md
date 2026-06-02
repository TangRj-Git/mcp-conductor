# 真实上游联调准备

## 文档目的

这份文档记录真实上游 MCP Server 联调需要的结构、配置和验证路径。

当前项目的基础代码、内存测试和 `learn-mcp-server` smoke 验证已经完成。当前 smoke 已覆盖真实能力发现、推荐，以及 tool/resource/resource template/prompt 四类受控访问。后续重点不是继续扩大功能，而是用更多真实上游 MCP Server 验证 `mcp-conductor` 能否稳定作为 Gateway 跑通完整工作流。

## 联调目标

第一轮联调验证低风险、可控、可重复的链路：

```text
外部 Host 或本地测试入口
  -> mcp-conductor
  -> 读取内部上游配置
  -> 启动或连接上游 MCP Server
  -> 发现 tools/resources/resource templates/prompts
  -> 生成能力注册表和工具卡片
  -> analyze_user_task / recommend_capabilities 推荐候选能力
  -> 按能力类型调用 call_upstream_tool / read_upstream_resource / read_upstream_resource_template / get_upstream_prompt
  -> 结果管理器返回 summary / preview / result_id
```

第一轮不验证危险写入、不验证远程多用户部署、不验证完整 Host Sampling。

当前可用的真实上游 smoke 命令：

```bash
uv run python scripts/smoke_learn_mcp.py
```

如果只需要验证能力发现，不执行后续推荐和访问检查：

```bash
uv run python scripts/smoke_learn_mcp.py --discovery-only
```

## 推荐选择的上游 Server

优先选择满足这些条件的上游：

- stdio 启动方式清晰。
- 不需要真实线上凭证，或者可以只用测试凭证。
- 工具以只读能力为主。
- 返回结果较小，方便观察。
- 可以在本地重复运行，不依赖复杂外部状态。

推荐顺序：

1. 简单测试 MCP Server：最适合验证协议链路和错误处理。
2. filesystem 类 Server：只开放一个临时只读目录，用于验证 Roots/allowlist。
3. 搜索或文档类只读 Server：用于验证稍大结果的 summary / preview / result_id。

第一轮不建议直接使用会写文件、删文件、发请求、发消息、发布内容或操作真实账号的上游。

## 配置文件结构

联调时建议创建一个只用于本地的内部上游配置文件，例如：

```text
config/upstreams.local.json
```

这个文件可以先不提交，或者后续只提交脱敏示例文件。

配置结构应覆盖：

```json
{
  "upstream_servers": {
    "demo": {
      "transport": "stdio",
      "command": "uv",
      "args": ["run", "python", "-m", "demo_mcp_server"],
      "cwd": "E:\\SoftwareProject\\mcp-conductor",
      "env": {},
      "risk_policy": "read_only_only",
      "roots_policy": "config_allowlist_only",
      "allowed_roots": ["E:\\SoftwareProject\\mcp-conductor\\tmp\\mcp-demo"]
    }
  }
}
```

如果上游需要凭证，配置文件只能引用环境变量：

```json
{
  "env": {
    "GITHUB_TOKEN": "${GITHUB_TOKEN}"
  }
}
```

不能把 token、密码、密钥写进配置文件。

## 联调执行路径

第一轮建议按这个顺序验证：

1. 启动 `mcp-conductor`，确认配置文件可以加载。
2. 确认上游 Server 可以启动或连接。
3. 调用 `list_upstream_capabilities`，确认能力发现结果、分页字段、`unavailable_upstreams` 和 `discovery_errors` 正常。
4. 可选调用 `list_exposed_capabilities`，确认 `exposure` 配置下的 proxy/hybrid 暴露计划符合预期。
5. 优先调用 `analyze_user_task`，也可以调用较底层的 `recommend_capabilities`，确认推荐结果包含 `recommendation_id`、`route_token`、`capability_id`、`input_schema`、`next_public_tool` 和 `ready_to_call_arguments`。
6. 使用推荐结果中的 `next_public_tool` 和 `ready_to_call_arguments` 调用 `call_upstream_tool`、`read_upstream_resource`、`read_upstream_resource_template` 或 `get_upstream_prompt`。
7. 确认只读能力可以访问，并返回 `summary`、`preview` 或 `result_id`。
8. 如果返回 `result_id`，继续调用 `read_result` 验证分页读取。
9. 手动制造一个上游发现失败或工具调用失败，确认错误结构符合 `04-error-handling-and-discovery-resilience.md`。

## 安全边界

联调时必须保持这些约束：

- `.env` 只保留在本地，不进入版本管理。
- `.env.example` 只保留变量名和说明，不写真实值。
- `.idea/`、`.venv/`、`__pycache__/` 和 `.pytest_cache/` 不进入版本管理。
- filesystem 类上游必须配置 `allowed_roots`，不要直接开放整个磁盘。
- 第一轮默认使用 `read_only_only`。
- 需要写入或删除的工具必须使用 `confirm_mutations`，并确认 `confirmation_required` 链路可见。
- 不使用 `confirmed=true` 这类绕过确认的标记。

## 成功标准

真实上游联调完成的标准：

- 能通过配置启动至少一个真实上游 MCP Server。
- `list_upstream_capabilities` 能看到来自真实上游的能力摘要。
- `analyze_user_task` / `recommend_capabilities` 能根据用户任务推荐真实上游能力。
- `call_upstream_tool` 能成功调用至少一个只读上游工具。
- `read_upstream_resource`、`read_upstream_resource_template` 和 `get_upstream_prompt` 能分别成功访问至少一个只读上游能力。
- 大结果可以被摘要、预览或缓存为 `result_id`。
- 上游启动失败、发现失败和工具调用失败都有结构化错误返回。
- `uv run pytest -q` 仍然通过。

## 后续可能补充

完成第一轮联调后，再考虑补充：

- 可提交的 `config/upstreams.example.json`。
- 一个专门用于联调的最小 demo MCP Server。
- 真实上游端到端测试。
- Codex / Claude Code 配置示例。
- 更完整的 streamable HTTP 运行说明。
