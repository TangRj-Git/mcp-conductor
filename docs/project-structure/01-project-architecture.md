# 项目架构设计

## 当前状态

当前项目已经从 `uv init` 的最小骨架迁移到 `src/` layout：

```text
mcp-conductor/
  pyproject.toml
  uv.lock
  README.md
  docs/
    project-analysis/
    project-structure/
  src/
    mcp_conductor/
      __init__.py
      __main__.py
      cli.py
      server.py
      runtime.py
      ...
  tests/
    unit/
    integration/
```

顶层 `main.py` 原本只是 `uv init` 生成的占位入口：

```python
def main():
    print("Hello from mcp-conductor!")
```

现在已经创建 `src/mcp_conductor/cli.py`、`src/mcp_conductor/__main__.py`，并在 `pyproject.toml` 中绑定 `mcp-conductor` 命令入口。确认 `uv run mcp-conductor --version` 可用后，顶层 `main.py` 已删除，避免出现两个入口。

当前第一版基础代码已经进入可联调状态：

- `src/mcp_conductor` 包结构已经建立。
- FastMCP 对外入口和四个对外工具已经建立。
- 配置加载、环境变量替换、上游 Client 管理、能力发现、能力注册、规则推荐、执行校验、结果缓存、风险策略、危险操作确认和 Roots/allowlist 已经有第一版实现。
- `.env`、`.idea/`、`.venv/`、`__pycache__/` 和 `.pytest_cache/` 已经通过 `.gitignore` 排除；`.env` 和 `.idea/` 已从 Git 索引移除，保留本地使用。
- 当前测试命令 `uv run pytest -q` 已通过，结果为 `49 passed`。

下一步不继续扩大功能范围，而是优先做真实上游 MCP Server 联调，验证从配置、启动、发现、推荐、调用到结果返回的完整链路。

## 架构目标

第一版项目结构要服务于已经确定的定位：

```text
对外：标准 MCP Server
对内：上游 Client 管理器 + 能力路由 + 网关执行 + 结果管理
```

源码结构需要满足几个目标：

1. FastMCP 对外入口要薄，只负责注册对外工具和启动服务。
2. 上游 MCP Client 管理、能力发现、路由、执行、安全策略、结果缓存要拆开。
3. 对外工具不能直接操作上游 Client，必须经过网关运行时。
4. `call_upstream_tool` 必须经过 `recommendation_id`、`route_token`、schema、risk policy 和 Roots/allowlist 校验。
5. 第一版不做完整 Host，不私自配置模型 API 密钥，不直接向用户确认危险操作。
6. 代码目录要能支撑后续增加 resources、resource templates、prompts、Host 采样路由器、语义检索和持久化缓存。

## 推荐源码目录

第一版推荐采用 `src/` layout：

```text
mcp-conductor/
  pyproject.toml
  uv.lock
  README.md
  docs/
    project-analysis/
    project-structure/
  src/
    mcp_conductor/
      __init__.py
      __main__.py
      cli.py
      server.py
      runtime.py
      models.py
      config/
        __init__.py
        loader.py
        schema.py
        env.py
      upstream/
        __init__.py
        manager.py
        client.py
        lifecycle.py
      discovery/
        __init__.py
        service.py
      registry/
        __init__.py
        store.py
        cards.py
      routing/
        __init__.py
        rules.py
        recommender.py
        sampled_router.py
      execution/
        __init__.py
        engine.py
        validation.py
      policy/
        __init__.py
        risk.py
        confirmation.py
        roots.py
      results/
        __init__.py
        manager.py
        cache.py
        pagination.py
        summarizer.py
      primitives/
        __init__.py
        adapter.py
        bridge.py
      public_tools/
        __init__.py
        capabilities.py
        recommend.py
        call_tool.py
        read_result.py
      observability/
        __init__.py
        logging.py
  tests/
    unit/
    integration/
```

包名使用 `mcp_conductor`，因为 Python import 名不能使用连字符。发布包名仍然可以是 `mcp-conductor`。

## 入口层

### `cli.py`

负责命令行入口：

- 解析配置文件路径。
- 设置日志级别。
- 创建网关运行时。
- 启动 FastMCP 服务。

后续 `pyproject.toml` 应增加：

```toml
[project.scripts]
mcp-conductor = "mcp_conductor.cli:main"
```

这样外部 Host 才能使用：

```text
uv run mcp-conductor
```

或者发布后使用：

```text
uvx --from mcp-conductor mcp-conductor
```

### `__main__.py`

用于支持：

```text
python -m mcp_conductor
```

它只应该调用 `cli.main()`，不要放业务逻辑。

### `server.py`

负责 FastMCP 服务创建和对外工具注册：

- 创建 FastMCP app/server。
- 注册 `list_upstream_capabilities`。
- 注册 `recommend_capabilities`。
- 注册 `call_upstream_tool`。
- 注册 `read_result`。

`server.py` 不应该直接连接上游 MCP Server，也不应该直接管理缓存。它只把请求转给 `runtime.py`。

## 网关运行时

### `runtime.py`

`GatewayRuntime` 是内部总协调对象，但不能变成万能大文件。

它负责装配这些服务：

- 配置管理器
- 上游客户端管理器
- 能力发现
- 能力注册表
- 能力路由器
- 策略引擎
- 网关执行引擎
- 结果管理器
- 原语适配器和桥接层

它提供对外工具需要的少量方法：

```text
list_upstream_capabilities(...)
recommend_capabilities(...)
call_upstream_tool(...)
read_result(...)
startup()
shutdown()
```

对外工具只调用这些方法，不跨层访问底层模块。

## 配置层

### `config/loader.py`

负责加载内部上游 MCP 配置。

第一版需要支持：

- 默认配置文件路径。
- 通过 CLI 参数指定配置文件。
- 解析 `${ENV_NAME}` 环境变量引用。
- 识别 `disabled`、`transport`、`command`、`args`、`url`、`cwd`、`env`、`risk_policy`、`roots_policy`。

### `config/schema.py`

定义配置数据结构。

第一版建议明确：

```text
UpstreamServerConfig
TransportType
RiskPolicy
RootsPolicy
```

`risk_policy` 第一版建议只保留：

```text
read_only_only
confirm_mutations
disabled
```

### `config/env.py`

负责环境变量替换和凭证处理。

规则：

- 配置文件不保存明文 secret。
- `${NAME}` 只从当前进程环境变量读取。
- 缺失必需环境变量时，该上游 Server 标记为 unavailable 或启动失败。

## 上游连接层

### `upstream/manager.py`

负责维护所有上游 MCP Server 的 Client/session。

职责：

- 根据配置启动或连接上游 Server。
- 每个上游 Server 一个独立 Client/session。
- 保存 `upstream_server_id -> client_session` 映射。
- 处理连接失败、关闭、重连策略。
- 关闭时清理由本进程启动的 stdio 子进程。

### `upstream/client.py`

封装单个上游连接。

职责：

- 初始化 MCP session。
- 调用上游 `tools/list`、`tools/call`。
- 调用上游 `resources/list`、`resources/templates/list`、`prompts/list`。
- 统一处理超时、错误、取消。

### `upstream/lifecycle.py`

处理进程生命周期。

第一版重点：

- stdio 上游由 `mcp-conductor` 启动。
- HTTP 上游优先连接已有 URL。
- 同一进程内不重复启动同一上游 Server。
- 多外部 Host 启动多个 `mcp-conductor` 进程时，不做跨进程协调。

## 能力发现和注册层

### `discovery/service.py`

负责上游能力发现。

第一版完整支持：

```text
tools/list
tools/call
```

第一版只发现和展示：

```text
resources/list
resources/templates/list
prompts/list
```

### `registry/store.py`

保存统一能力注册表。

每个能力至少包含：

```text
capability_id
capability_type
upstream_server_id
upstream_client_id
original_name_or_uri
description
schema_or_metadata
tags
risk_level
read_only_hint
enabled
```

### `registry/cards.py`

生成工具卡片，给规则路由和后续 Host 采样路由器使用。

工具卡片是压缩信息，不应该把完整 schema、完整敏感描述或大 payload 直接塞给模型。

## 路由层

### `routing/rules.py`

第一版规则和标签筛选。

职责：

- 按能力类型筛选。
- 按启用状态筛选。
- 按 tag、name、description 做基础召回。
- 过滤明显无关能力。
- 限制返回数量。

### `routing/recommender.py`

实现 `recommend_capabilities` 的核心逻辑。

输出：

- `recommendation_id`
- `expires_at`
- `recommended_capabilities`
- 每个候选能力的 `route_token`
- 输入 schema 和示例参数

### `routing/sampled_router.py`

第二阶段使用。

边界：

- 只能通过外部 Host Sampling。
- 不能私自配置模型 API 密钥。
- Sampling prompt 中的上游描述、resource、prompt、工具结果都必须标记为不可信上下文。

## 执行层

### `execution/validation.py`

负责调用前校验：

- `recommendation_id` 是否存在。
- `recommendation_id` 是否过期。
- `route_token` 是否匹配。
- `capability_id` 是否属于推荐结果。
- `capability_type` 是否为 tool。
- 工具是否仍然启用。
- arguments 是否符合 input schema。
- Roots / allowlist 是否允许访问相关路径。
- 风险策略是否允许自动执行。

### `execution/engine.py`

负责真实调用上游 MCP Server。

执行链路：

```text
call_upstream_tool request
  -> validation
  -> policy check
  -> upstream client lookup
  -> upstream tools/call
  -> result manager
```

它不负责生成推荐结果，也不负责最终回答用户。

## 安全策略层

### `policy/risk.py`

判断风险级别。

第一版规则：

- `read_only_hint` 只能作为提示。
- 未知风险默认危险。
- 写入、删除、发送、发布、支付、外部提交、网络状态变更都需要确认。

### `policy/confirmation.py`

负责危险操作确认状态。

第一版支持：

- 通过 Elicitation 请求外部 Host 收集确认。
- 如果 Host 不支持 Elicitation，返回 `confirmation_required`。
- 生成 `pending_action_id`。
- `pending_action_id` 有 TTL。
- 二次调用时参数不能变化。
- 不能接受普通 `confirmed=true`。

### `policy/roots.py`

处理 Roots 和 allowlist。

第一版原则：

- filesystem 类上游必须被 Roots 或 allowlist 约束。
- 如果 Host 支持 Roots，使用 Host Roots 与内部 allowlist 的交集。
- 如果 Host 不支持 Roots，使用内部配置 allowlist。

## 结果层

### `results/manager.py`

统一处理上游返回结果。

职责：

- 判断结果大小。
- 生成 summary。
- 生成 preview。
- 必要时缓存完整结果并返回 `result_id`。
- 提供 `read_result`。

### `results/cache.py`

第一版使用进程内缓存。

规则：

- 默认 TTL 30 分钟。
- `result_id` 不透明、不可猜测。
- 按外部连接/session 或请求上下文隔离。
- 设置最大条数和最大字节数。
- 不缓存 secrets、token、密码和敏感凭证。
- 进程退出后失效。

### `results/summarizer.py`

第一版使用规则摘要和截断，不依赖模型。

第二阶段如果通过 Sampling 做模型摘要，必须由外部 Host 控制。

## 原语层

### `primitives/adapter.py`

处理 `mcp-conductor` 作为 Server 请求外部 Host 的能力：

- Sampling
- Roots
- Elicitation
- Logging
- Progress
- Cancellation

### `primitives/bridge.py`

处理上游 Server 向 `mcp-conductor` 这个 Client 发起的能力请求。

第一版保守策略：

- 上游 Sampling 默认拒绝或返回 unsupported。
- 上游 Elicitation 不允许索要 token、密码、密钥。
- 上游 Roots 返回 Host Roots 与内部 allowlist 的受限交集。
- 上游 Logging 脱敏、限流并标记来源。
- 上游 Progress 可以聚合转发。
- 上游 Cancellation 尽量传播。
- 上游 Pagination 转换成 `mcp-conductor` 自己的不透明 cursor。
- 上游 Completion 第一版不转发。

## 对外工具层

### `public_tools/capabilities.py`

实现 `list_upstream_capabilities`。

只返回摘要、分页和必要元数据，不返回完整内部状态。

### `public_tools/recommend.py`

实现 `recommend_capabilities`。

它调用 `routing/recommender.py`，不直接执行上游工具。

### `public_tools/call_tool.py`

实现 `call_upstream_tool`。

它必须走 `execution/validation.py` 和 `execution/engine.py`，不能直接调用上游 Client。

### `public_tools/read_result.py`

实现 `read_result`。

它只能读取当前 session 或请求上下文可访问的 `result_id`。

## 数据模型

### `models.py`

建议保存跨模块共享的核心模型：

```text
Capability
CapabilityCard
Recommendation
RecommendedCapability
RouteToken
ToolCallRequest
ToolCallResult
ResultReference
PendingAction
GatewayError
```

如果某些模型只属于单个模块，可以放在该模块内部，避免 `models.py` 过早膨胀。

## 测试结构

当前已经保留的测试结构：

```text
tests/
  unit/
    test_config_loader.py
    test_discovery_service.py
    test_execution_engine.py
    test_result_cache.py
    test_runtime_flow.py
    test_runtime_lifecycle.py
    test_server_tools.py
    test_upstream_client.py
  integration/
    test_in_memory_gateway_flow.py
```

优先测试：

- 配置解析和环境变量替换。
- `recommendation_id` / `route_token` 校验。
- `read_only_hint` 不被完全信任。
- 危险操作返回 confirmation。
- `result_id` TTL 和 session 隔离。
- 上游连接失败不影响其他上游。
- 后续真实上游联调应补充端到端测试或手动验证记录，覆盖真实 `tools/list` 和 `tools/call`。

## 依赖方向

推荐依赖方向：

```text
public_tools
  -> runtime
    -> config
    -> upstream
    -> discovery
    -> registry
    -> routing
    -> execution
    -> policy
    -> results
    -> primitives
```

约束：

- `public_tools` 不直接访问 `upstream`。
- `server.py` 不直接访问 `upstream`、`policy`、`results` 的内部细节。
- `execution` 可以调用 `policy`、`registry`、`upstream`、`results`。
- `routing` 只能推荐能力，不能执行能力。
- `policy` 不应该依赖 FastMCP。
- `results` 不应该调用上游工具。
- `primitives` 负责协议协作能力，不负责业务路由。

## 第一版实现顺序

第一版建议实现顺序和当前状态：

1. 已完成：建立 `src/mcp_conductor` 包结构和 CLI 入口。
2. 已完成：创建 FastMCP 服务和四个对外工具。
3. 已完成：实现配置加载和配置 schema。
4. 已完成：实现上游 Client Manager 的生命周期骨架。
5. 已完成：实现 tools/resources/templates/prompts 发现。
6. 已完成：实现能力注册表和工具卡片。
7. 已完成：实现规则推荐和 `recommendation_id` / `route_token`。
8. 已完成：实现 `call_upstream_tool` 调用前校验。
9. 已完成：实现上游 tool 调用转发的第一版链路。
10. 已完成：实现结果管理器和 `read_result`。
11. 已完成：实现风险策略和 `confirmation_required`。
12. 已完成：补上原语适配器和桥接层的保守降级。
13. 下一步：选择一个低风险真实上游 MCP Server，跑通真实发现和工具调用。
14. 下一步：根据联调结果补齐配置样例、错误提示、真实上游端到端测试和 README 使用说明。

## 顶层 main.py 是否需要删除

当前顶层 `main.py` 已删除。

原因：

1. 当前项目已经有 `src/mcp_conductor` 包。
2. `pyproject.toml` 已经有 `[project.scripts]` 命令入口。
3. `uv run mcp-conductor --version` 已验证可用。
4. 保留顶层 `main.py` 会造成两个入口并存，后续容易混淆。

当前入口策略：

```text
命令入口：
  pyproject.toml -> [project.scripts] -> mcp_conductor.cli:main

模块入口：
  python -m mcp_conductor -> src/mcp_conductor/__main__.py -> cli.main()
```

后续业务逻辑不应该写入顶层文件，而应该继续放在 `src/mcp_conductor` 包内。

## 当前结论

当前项目最适合的架构不是把所有逻辑继续写进顶层 `main.py`，而是尽快迁移到 `src/mcp_conductor` 包结构。

第一版应该保持模块边界清晰：

- FastMCP 入口薄。
- 运行时负责协调。
- 配置、上游连接、发现、注册、路由、执行、策略、结果和原语模块分开。
- 对外工具只调用运行时。
- 上游工具执行必须经过推荐凭证和安全策略。

顶层 `main.py` 已删除，当前唯一正式入口是 `mcp_conductor.cli:main`。
