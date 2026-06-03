# 模块分析

## 初步模块拆分

### 1. Public MCP Server

`mcp-conductor` 对外暴露的标准 MCP Server。

主要职责：

- 使用 FastMCP 启动服务。
- 注册对外高级 tools；上游 tools、resources、resource templates 和 prompts 不会原样暴露，只能通过推荐凭证和对应公开工具受控访问。
- 接收外部 Host 的 MCP 调用。
- 将调用转交给内部网关运行时。
- 不负责直接和最终大模型对话。
- 不负责管理外部 Host 的完整工具上下文。

### 2. Upstream Config Manager

负责读取内部上游 MCP Server 配置。

主要职责：

- 管理上游 server 名称、启动命令、参数或 HTTP 地址。
- 区分启用和禁用的上游 Server。
- 支持本地开发配置和后续发布后的配置方式。
- 支持 `env`、`cwd`、`disabled`、`transport`、`risk_policy`、`roots_policy` 等字段。
- 不建议在配置示例中直接写入明文 token 或 secret；如需凭证，优先通过环境变量引用。

### 3. 上游客户端管理器

负责连接上游 MCP Server，并维护 MCP Client 实例。

主要职责：

- 启动或连接上游 MCP Server。
- 为每个上游 MCP Server 创建或维护一个独立 MCP Client/session。
- 执行 MCP 初始化和能力协商。
- 处理连接失败、重连和关闭。
- 为后续工具调用提供统一入口。
- 保存 `upstream_server_id -> client_session` 的映射。
- 防止不同上游 Server 的连接状态、能力列表和调用结果混在一起。
- 关闭 `mcp-conductor` 时必须关闭所有上游 Client/session，并清理由它启动的 stdio 子进程。
- 同一个 `mcp-conductor` 进程内不重复启动同一个上游 Server。
- 如果上游是固定端口 HTTP 服务，优先连接已有 URL，不默认重复启动。

### 4. Capability Discovery

负责发现上游 MCP Server 暴露的能力。

主要职责：

- 调用上游 `tools/list`。
- 调用上游 `resources/list`。
- 调用上游 `resources/templates/list`。
- 调用上游 `prompts/list`。
- 将发现结果交给能力注册表。

### 5. Capability Registry

统一保存所有上游 MCP 能力的元数据。

主要职责：

- 保存工具名、描述、参数摘要、所属上游 Server。
- 保存能力对应的上游 Client/session 引用或可解析 ID。
- 为每个能力生成全局唯一 ID，避免不同 Server 中同名工具冲突。
- 保存资源 URI、资源模板和 Prompt 元数据。
- 生成或保存工具卡片。
- 增加标签、适用场景、不适用场景和风险级别。
- 为检索和路由提供统一查询入口。

### 6. Capability Router

根据外部 Host 传入的用户任务筛选候选上游能力。

主要职责：

- 使用规则过滤明显无关或不可用能力。
- 第一版使用规则和标签召回相关能力。
- 第二阶段可加入语义检索召回相关能力。
- 第二阶段可调用 Host 采样路由器做智能筛选。
- 输出紧凑的候选能力卡片和推荐能力列表，避免把全部上游 schema 暴露给外部模型。
- 当前第一版允许 tool、resource、resource template 和 prompt 进入推荐链路；tool 通过 `call_upstream_tool` 执行，resource/template/prompt 通过各自公开工具读取或获取。

### 7. Host 采样路由器（第二阶段可选）

这是第二阶段可选的能力筛选增强，不是第一版核心模块，也不是 `mcp-conductor` 自己私自创建的模型子代理。

主要职责：

- 读取用户任务和候选能力卡片。
- 判断任务意图和所需能力。
- 输出推荐能力、原因和置信度。
- 不直接执行或访问上游能力。
- 如果需要模型推理，必须通过 Host Sampling 请求外部 Host 的受控模型；不得由 `mcp-conductor` 私自使用自己的模型配置。
- 如果 Host 不支持 Sampling，必须回退到规则/标签筛选。
- Sampling 结果只影响推荐排序和筛选范围，不自动获得执行权限。

### 7.5 Exposure Planner

负责根据 `exposure` 配置、能力注册表和风险策略生成“将来可直接暴露给 Host 的上游工具计划”。

主要职责：

- 读取 `exposure.mode`、include/exclude 过滤条件和 `max_exposed_tools`。
- 只选择当前允许直接规划暴露的 read-only tool。
- 为上游 tool 生成稳定、可读、冲突安全的 `exposed_name`。
- 返回 `exposed_capabilities` 和 `skipped_capabilities`，用于 Inspector 或 Host 诊断。
- 不直接注册 FastMCP 动态工具，也不执行任何上游能力。

### 7.6 Step Routing Session

这是为了支持“每次用户输入和每次 agent loop 步骤都重新筛选能力”的 Gateway Core 模块。

主要职责：

- 保存轻量 routing session，不保存完整对话历史。
- 记录最初用户任务摘要、最近步骤摘要、推荐过的能力、调用过的能力和失败记录。
- 接收单次 `step_content`，辅助当前步骤能力筛选。
- 为 `analyze_agent_step` 返回 `routing_round_id`、候选能力、`next_public_tool` 和 `ready_to_call_arguments`。
- 给未来 Host wrapper / Agent Orchestrator 提供稳定接口。

边界：

- 它仍然属于 Gateway Core 的能力筛选配套模块。
- 它不能强制 Codex、Claude Code 等外部 Host 每轮调用。
- 真正强制每轮调用需要外层 Host/Agent Orchestrator。

### 8. 网关执行引擎

负责把筛选结果转成真实上游 MCP 调用。

主要职责：

- 校验目标能力是否存在。
- 校验 `recommendation_id` 是否存在且未过期。
- 校验 `route_token` 是否匹配当前推荐结果。
- 校验 `capability_id` 是否属于该推荐结果。
- 校验参数 schema。
- 根据能力注册表找到对应上游 Server 和上游 Client。
- 根据路由结果调用上游 MCP Server。
- 处理调用失败和重试策略。
- 默认只自动执行被风险策略确认后的只读能力；`read_only` / `read_only_hint` 不能单独作为可信依据。
- 对写入、删除、发送、发布、支付等危险能力，优先使用 Elicitation 请求 Host 收集用户确认；不支持时返回带 `pending_action_id` 的 `confirmation_required`。

### 9. Result Manager

负责管理上游 MCP Server 返回结果。

主要职责：

- 对大结果做摘要。
- 支持分页读取。
- 缓存完整结果。
- 返回 `result_id` 供后续继续读取。
- 控制返回给外部 Host 的结果大小。
- 第一版使用进程内缓存，默认 TTL 30 分钟。
- `result_id` 必须不透明、不可猜测，并按外部连接/session 或请求上下文隔离。
- 设置最大缓存条数和最大字节数，避免无限增长。

### 10. 策略引擎

负责安全策略和权限判断。

主要职责：

- 判断上游工具风险级别。
- 限制危险操作。
- 标记需要用户确认的能力。
- 根据用户配置禁用某些上游工具或 Server。
- 根据 `risk_policy`、allowlist、工具名/描述规则、用户配置和 Roots/路径约束做最终风险判断。
- 对未知风险能力默认按危险处理。

### 11. Public Tool Layer

负责定义 `mcp-conductor` 对外暴露的少量高级工具。

当前第一版公开工具：

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

`analyze_user_task` 是首选任务分析入口，`recommend_capabilities` 是较底层推荐入口。`start_routing_session` 和 `analyze_agent_step` 为外层 Orchestrator 提供每步路由接口，但不强制外部 Host 调用。`ask_conductor` 作为第二阶段或可选增强工具，依赖 Host Sampling。它不能替代 `analyze_user_task/recommend_capabilities -> 具体访问工具` 的受控链路，也不能把项目变成完整 Host 或聊天代理。

### 12. MCP 客户端原语和工具适配器

负责处理 `mcp-conductor` 作为 Server 时可以请求或使用的 MCP 协作能力，以及 `mcp-conductor` 作为上游 Client 时如何处理上游 Server 发起的协作请求。

主要职责：

- Sampling：可选，用于请求外部 Host 执行受控路由推理。
- Roots：可选，用于获取 Host 暴露的工作区边界，并约束上游 filesystem 类能力。
- Elicitation：可选，用于危险操作或缺失参数时请求 Host 收集用户输入。
- Logging：可选，用于向 Host 发送结构化日志，不能包含 secrets。
- Progress：可选，用于长时间上游调用的进度通知。
- Cancellation：可选，用于接收取消通知并尝试取消上游调用。
- Pagination：用于处理上游 list 操作和对外列表工具的大结果分页。
- Completion：后续用于 MCP completion 能力相关场景，第一版可不实现。

额外边界：

- 外部方向：`mcp-conductor` 可以请求外部 Host 提供 Sampling、Roots、Elicitation 等能力，但是否支持和批准由外部 Host 决定。
- 上游方向：上游 Server 如果向 `mcp-conductor` 请求 Sampling、Roots、Elicitation，必须经过本模块的桥接策略；第一版默认不直接替上游完成敏感请求。
- 对上游 Sampling 请求，第一版默认拒绝或显式返回 unsupported，后续可在外部 Host 支持且用户允许时转发。
- 对上游 Roots 请求，第一版只能返回配置 allowlist 或外部 Host Roots 的受限交集。
- 对上游 Elicitation 请求，第一版默认只允许非敏感、低风险参数补充；危险确认仍必须走 `mcp-conductor` 自己的风险策略。

### 13. Host / Agent Orchestrator（独立后续）

这是后续可选方向，不属于当前 MCP Gateway Server 第一版。

主要职责：

- 接收用户输入。
- 控制模型调用和 agent loop。
- 在每次用户输入和每次 loop 步骤前主动调用 `mcp-conductor-core` 的 step routing API。
- 把筛选后的候选能力转换成本轮模型可用工具面。
- 接收模型工具调用意图，再通过 `mcp-conductor-core` 的公开工具执行上游能力。
- 将工具结果作为下一轮 `step_content`，继续循环或结束。

边界：

- 它可以使用 `mcp-conductor-core`，但不能和当前 `mcp_conductor` Gateway 包混成一个入口。
- 当前仓库不再包含独立 agent 原型包、模型决策接口或 provider 适配器；这些能力如果继续开发，应放在 Gateway Server 之外。
- 它才是能强制每轮筛选的层；当前 MCP Server 只能被动响应调用。

## 第一阶段建议优先级

1. 对外 MCP Server
2. 上游配置管理器
3. 上游客户端管理器
4. 能力发现
5. 能力注册表
6. 对外工具层
7. 能力路由器
8. 网关执行引擎
9. 结果管理器
10. MCP 客户端原语和工具适配器

## 后续优先级

Gateway Core 稳定后，下一阶段建议按这个顺序继续：

1. 真实 Host / Agent Orchestrator：如确实需要强制每步路由，应在独立 Host、wrapper、插件或单独示例项目中实现。
2. Host Sampling / 语义检索增强。
3. proxy / hybrid 动态工具注册。
