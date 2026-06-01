# 待确认问题

这个文件只记录还没有最终关闭的问题。已经在后续讨论中确定的内容放到“已决策”里，避免后续实现时把旧问题重新当成未决事项。

## 已决策

### 产品定位

1. 第一版明确只做 MCP Gateway Server，不做完整 MCP Host。
2. `mcp-conductor` 对外像普通 MCP Server 一样被配置使用。
3. `mcp-conductor` 对内为每个上游 MCP Server 创建或维护独立 MCP Client/session。
4. 外部 Host 仍然负责用户对话、模型调用、工具暴露和最终回答。
5. `ask_conductor` 不作为第一版核心工具；后续如果增加，必须依赖 Host Sampling，不能私自配置模型 API 密钥。

### 外部使用方式

1. 推荐外部 Host 只配置 `mcp-conductor`。
2. 其他 MCP Server 推荐放入 `mcp-conductor` 的内部上游配置。
3. 不推荐外部 Host 同时直接配置 `mcp-conductor` 和大量上游 MCP Server，否则会削弱工具筛选、上下文压缩和安全控制效果。

### 第一版公开工具

第一版对外公开工具暂定为：

```text
list_upstream_capabilities
recommend_capabilities
call_upstream_tool
read_result
```

约束：

1. `call_upstream_tool` 必须依赖 `recommend_capabilities` 返回的 `recommendation_id` 和 `route_token`。
2. `call_upstream_tool` 默认只能调用当前有效推荐结果中的 tool。
3. `read_result` 只读当前 session 或请求上下文可访问的缓存结果。
4. `ask_conductor` 放到第二阶段或可选增强。

### 安全策略

1. 第一版只允许被风险策略确认后的只读能力自动执行。
2. `read_only` / `read_only_hint` 只能作为提示，不能完全信任。
3. 未知风险能力默认按危险处理。
4. 危险操作优先通过 Elicitation 请求外部 Host 收集确认。
5. 如果 Host 不支持 Elicitation，则返回带 `pending_action_id` 的 `confirmation_required`。
6. `pending_action_id` 必须有过期时间，二次确认时参数不能变化，不能用 `confirmed=true` 替代。

### 结果管理

1. 第一版使用进程内缓存。
2. `result_id` 默认 TTL 30 分钟。
3. `result_id` 不透明、不可猜测，并按外部连接/session 或请求上下文隔离。
4. 进程退出后 `result_id` 失效。
5. 默认使用规则摘要、preview 和截断，不依赖模型摘要。

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

1. 内部上游配置文件使用什么名称？
2. 是否兼容常见 Host 的 `mcpServers` 配置格式？
3. 第一版优先支持 stdio 上游 Server，还是同时支持 streamable HTTP？
4. 配置加载优先级如何定义：默认文件、环境变量、CLI 参数之间谁覆盖谁？
5. `risk_policy` 是否只保留 `read_only_only`、`confirm_mutations`、`disabled` 三种第一版枚举？
6. 凭证环境变量引用语法是否统一为 `${NAME}`？
7. 第一版目标 MCP 协议版本使用哪个 specification 版本？

### 工具筛选

1. 第二阶段是否引入语义/向量检索？
2. 需要确认哪些目标 Host 支持 Sampling。
3. 工具卡片由上游 Server 原始描述生成，还是允许用户手动补充标签和场景？
4. 当路由代理不确定时，是返回澄清问题，还是返回多个候选方案？
5. Sampling prompt 中不可信上游内容的隔离格式如何定义？

### 安全策略

1. 上游工具风险级别枚举如何定义？
2. 工具名/描述风险规则第一版包含哪些关键词和模式？
3. 是否允许用户按上游 Server 或 Tool 禁用能力？
4. filesystem 类能力的 Roots/allowlist 具体匹配规则如何定义？
5. 上游 Server 请求 Sampling、Roots、Elicitation 时，哪些场景允许桥接到外部 Host？

### 结果管理

1. `result_id` TTL 是否允许用户配置？
2. 第一版是否需要支持过滤读取，还是只支持分页读取？
3. 单个缓存结果和总缓存大小的默认上限是多少？
4. `recommendation_id`、`route_token`、`pending_action_id` 是否一次性使用？

## 第一阶段里程碑

第一阶段建议包含：

1. 对外启动为标准 MCP Server。
2. 读取内部上游 MCP Server 配置。
3. 连接并发现上游 MCP 能力。
4. 建立能力注册表。
5. 对外提供 `list_upstream_capabilities`、`recommend_capabilities`、`call_upstream_tool` 和 `read_result`。
6. 用工具卡片完成候选能力筛选。
7. 通过 `recommendation_id` 和 `route_token` 限制执行链路。
8. 只自动执行被风险策略确认后的只读工具。
9. 对危险操作返回 `confirmation_required` 或使用 Elicitation。
10. 对大结果返回 summary、preview 和可选 `result_id`。

如果这条链路确认，再进入正式实现计划。
