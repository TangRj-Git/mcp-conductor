# 待确认问题

这个文件只记录还没有最终关闭的问题。已经在后续讨论中确定的内容放到“已决策”里，避免后续实现时把旧问题重新当成未决事项。

## 已决策

### 产品定位

1. 第一版明确只做 MCP Gateway Server，不做完整 MCP Host。
2. `mcp-conductor` 对外像普通 MCP Server 一样被配置使用。
3. `mcp-conductor` 对内为每个上游 MCP Server 创建或维护独立 MCP Client/session。
4. 外部 Host 仍然负责用户对话、模型调用、工具暴露和最终回答。
5. 项目核心目标是减少外部 Host 直接暴露的工具数量，降低工具上下文膨胀，并提高每轮任务的工具选择准确性。
6. `ask_conductor` 不作为第一版核心工具；后续如果增加，必须依赖 Host Sampling，不能私自配置模型 API 密钥，也不能绕过推荐凭证和风险策略。

### 外部使用方式

1. 推荐外部 Host 只配置 `mcp-conductor`。
2. 其他 MCP Server 推荐放入 `mcp-conductor` 的内部上游配置。
3. 不推荐外部 Host 同时直接配置 `mcp-conductor` 和大量上游 MCP Server，否则会削弱工具筛选、上下文压缩和安全控制效果。

### 内部上游 MCP 配置

1. 当前配置解析已支持 `upstreamServers`。
2. 当前配置解析已兼容常见 Host 的 `mcpServers` 配置格式。
3. 当前已支持 `stdio` 和 `streamable_http` 两种上游传输类型。
4. 第一版风险策略枚举确定为 `read_only_only`、`confirm_mutations`、`disabled`。
5. 凭证环境变量引用语法使用 `${NAME}`。
6. 默认本地配置文件名确定为当前工作目录下的 `mcp-conductor.config.json`。
7. 配置加载优先级确定为：显式 `--config` 优先；没有 `--config` 时检查当前工作目录的 `mcp-conductor.config.json`；都不存在时使用空配置启动。
8. 配置文件同目录下的 `.env` 会在解析配置变量前加载；`.env` 不覆盖进程中已经存在的同名环境变量。
9. 当前支持在 `command`、`args`、`url`、`cwd`、`env`、`allowed_roots` 中展开 `${NAME}` 环境变量。

### 第一版公开工具

第一版对外公开工具确定为：

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

约束：

1. 具体访问工具必须依赖 `analyze_user_task` 或 `recommend_capabilities` 返回的 `recommendation_id` 和 `route_token`。
2. `call_upstream_tool` 默认只能调用当前有效推荐结果中的 tool。
3. `read_upstream_resource`、`read_upstream_resource_template` 和 `get_upstream_prompt` 默认只能访问当前有效推荐结果中的只读能力。
4. `read_result` 只读当前 session 或请求上下文可访问的缓存结果。
5. `analyze_user_task` 是首选任务分析入口，`recommend_capabilities` 是较底层推荐入口。
6. `list_exposed_capabilities` 只展示当前 `exposure` 配置下的暴露计划，不动态注册或执行上游能力。
7. `ask_conductor` 放到第二阶段或可选增强。

### 安全策略

1. 第一版只允许被风险策略确认后的只读能力自动执行。
2. `read_only` / `read_only_hint` 只能作为提示，不能完全信任。
3. 未知风险能力默认按危险处理。
4. 危险操作优先通过 Elicitation 请求外部 Host 收集确认。
5. 如果 Host 不支持 Elicitation，则返回带 `pending_action_id` 的 `confirmation_required`。
6. `pending_action_id` 必须有过期时间，二次确认时参数不能变化，不能用 `confirmed=true` 替代。
7. 当前风险级别枚举确定为 `read_only`、`mutating`、`destructive`、`unknown`。
8. `destructiveHint` 和工具名/描述中的破坏性关键词优先级高于 `readOnlyHint=true`。
9. `pending_action_id` 在确认后执行成功路径中是单次使用，不能被重复 replay。

### 结果管理

1. 第一版使用进程内缓存。
2. `result_id` 默认 TTL 30 分钟。
3. `result_id` 不透明、不可猜测，并按外部连接/session 或请求上下文隔离。
4. 进程退出后 `result_id` 失效。
5. 默认使用规则摘要、preview 和截断，不依赖模型摘要。
6. 当前结果缓存默认最多保留 100 条，整体最多约 10MB，超过限制时淘汰最早写入的结果。
7. 如果当前 Host/transport 无法提供 session id，大结果只返回摘要和预览，不返回可继续读取的 `result_id`。

### 触发和路由

1. 当前 MCP Server 形态不能强制 Codex、Claude Code 等 Host 每次用户输入都调用 `mcp-conductor`。
2. 当前 MCP Server 形态不能直接插入外部 Host 的每一次内部 agent loop。
3. 强制每轮筛选需要额外的 Host wrapper、Agent Orchestrator 或 IDE/plugin 层。
4. 当前 Gateway Core 后续可以先实现 step routing API 和轻量 routing session，为外层 Orchestrator 做准备。

### 工程入口

1. 当前项目采用 `src/mcp_conductor` 包结构。
2. 当前正式命令入口是 `pyproject.toml` 中的 `[project.scripts] mcp-conductor = "mcp_conductor.cli:main"`。
3. `python -m mcp_conductor` 通过 `src/mcp_conductor/__main__.py` 转发到 `cli.main()`。
4. 顶层 `main.py` 已删除，后续不再作为入口。

## 仍待确认

### 产品定位

1. 项目发布名称是否继续使用 `mcp-conductor`，还是未来改为更直白的 `mcp-gateway-server`？

### 外部使用方式

1. 发布后是否优先支持 `uvx --from mcp-conductor mcp-conductor` 这种使用方式？
2. 发布后是否需要额外提供其他启动方式，例如 Docker 或独立可执行文件？

### 内部上游 MCP 配置

1. 第一版目标 MCP 协议版本使用哪个 specification 版本？
2. 是否需要把 `mcp-conductor.config.json` 的搜索路径扩展到用户配置目录，还是保持只看当前工作目录和显式 `--config`？
3. 是否需要提供可提交的 `config/upstreams.example.json` 示例目录和脱敏模板？

### 工具筛选

1. 第二阶段是否引入语义/向量检索？
2. 需要确认哪些目标 Host 支持 Sampling。
3. 工具卡片由上游 Server 原始描述生成，还是允许用户手动补充标签和场景？
4. 当路由代理不确定时，是返回澄清问题，还是返回多个候选方案？
5. Sampling prompt 中不可信上游内容的隔离格式如何定义？

### 安全策略

1. 工具名/描述风险规则第一版还需要补充哪些关键词和模式？
2. 是否允许用户按单个上游 capability 禁用能力，而不仅是按上游 Server 禁用？
3. filesystem 类能力的 Roots/allowlist 是否需要支持更复杂的匹配规则？
4. 上游 Server 请求 Sampling、Roots、Elicitation 时，哪些场景允许桥接到外部 Host？

### 结果管理

1. `result_id` TTL 是否允许用户配置？
2. 第一版是否需要支持过滤读取，还是只支持分页读取？
3. 单个缓存结果是否需要独立最大字节上限？
4. 结果缓存最大条数和总字节数是否需要从固定默认值改成配置项？
5. `recommendation_id` 和 `route_token` 是否需要未来支持一次性使用或按 routing round 限制？

### Host/Agent Orchestrator

1. 是否要正式新增 `mcp-conductor-agent` 包，还是只先保留 demo orchestrator？
2. `analyze_agent_step` 是否作为第一阶段后续公开工具加入，还是等 Orchestrator 开发时再加入？
3. routing session 是否只服务 step routing，还是也要绑定 `recommendation_id`、`result_id` 和 `pending_action_id` 的可访问边界？
4. 每次 step routing 是否允许使用 Host Sampling，还是第一版仍只用规则/标签筛选？

## 第一阶段里程碑

第一阶段链路必须包含：

1. 对外启动为标准 MCP Server。
2. 读取内部上游 MCP Server 配置。
3. 连接并发现上游 MCP 能力。
4. 建立能力注册表。
5. 对外提供 `analyze_user_task`、`list_upstream_capabilities`、`list_exposed_capabilities`、`recommend_capabilities`、`call_upstream_tool`、`read_upstream_resource`、`read_upstream_resource_template`、`get_upstream_prompt` 和 `read_result`。
6. 用工具卡片完成候选能力筛选。
7. 通过 `recommendation_id` 和 `route_token` 限制执行链路。
8. 只自动访问被风险策略允许的只读能力；非只读 tool 需要确认。
9. 对危险操作返回 `confirmation_required` 或使用 Elicitation。
10. 对大结果返回 summary、preview 和可选 `result_id`。

当前项目已经进入第一版实现和联调准备阶段。后续如果新增里程碑，必须继续围绕“减少工具上下文暴露、动态推荐当前任务能力、受控执行上游工具”这条主线展开。
