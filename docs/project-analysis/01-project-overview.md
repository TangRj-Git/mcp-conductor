# 项目概览

## 项目名称

`mcp-conductor`

中文定位可以称为：MCP 能力调度器。

## 一句话定义

`mcp-conductor` 是一个可以像普通 MCP Server 一样配置使用的 MCP Gateway Server。它把多个上游 MCP Server 收拢到一个受控入口后面，通过能力发现、任务相关工具推荐、受控调用和结果压缩，减少外部 Host 的工具上下文膨胀，并提高大模型每轮选择工具的准确性。

## 项目北极星

这个项目始终围绕一个核心问题设计：

```text
用户希望配置很多 MCP 能力，但不希望外部大模型每轮都直接看到全部底层工具。
```

因此 `mcp-conductor` 的关键作用不是“多做一个工具 Server”，而是：

- 让外部 Host 尽量只配置 `mcp-conductor` 一个 MCP Server。
- 把 GitHub、filesystem、database、browser/search 等上游 MCP Server 放进 `mcp-conductor` 内部配置。
- 启动后发现所有上游能力，但对外只暴露少量高级调度工具。
- 每轮根据用户任务返回紧凑的候选能力、调用凭证和必要 schema。
- 让外部大模型在候选范围内填写参数并发起受控调用。
- 对执行、风险确认和大结果返回做边界控制。

这样目标是同时满足两个方向：

- 充分：用户配置的上游 MCP 能力仍然可以被使用。
- 准确：外部模型不必在过大的工具集合中盲选，减少误选和绕路。

## 不是完整 MCP Host

`mcp-conductor` 当前不定位为完整 MCP Host。

完整 Host 通常负责：

- 管理用户对话。
- 直接和大模型交互。
- 决定每轮给大模型暴露哪些工具。
- 接收模型工具调用意图。
- 调用 MCP Client 执行工具。

`mcp-conductor` 的定位不同：

- 外部 Host 仍然由 Claude、Codex、Cursor 等应用承担。
- `mcp-conductor` 只作为一个 MCP Server 被外部 Host 配置和调用。
- `mcp-conductor` 内部可以连接其他 MCP Server，并对它们做能力发现、筛选、路由和结果管理。
- `mcp-conductor` 不直接管理用户对话，也不直接控制外部模型的完整工具上下文；它只能通过自己暴露的高级工具返回候选能力和受控调用入口。

因此它是：

```text
外部看：标准 MCP Server
内部看：MCP Client + Gateway + Capability Router
```

## MCP Client 和 Server 的对应关系

MCP 中 Host、Client、Server 的常见关系是：

```text
Host
  ├─ MCP Client A ── MCP Server A
  ├─ MCP Client B ── MCP Server B
  └─ MCP Client C ── MCP Server C
```

每个 MCP Client 通常对应一个 MCP Server，并维护与该 Server 的独立连接和会话。Host 通过管理这些 Client 来控制：

- 哪些 Server 被连接。
- 每个 Server 的生命周期。
- 每个 Server 暴露了哪些能力。
- 哪些能力可以交给大模型。
- 模型选择工具后应该路由到哪个 Client。

这也是 `mcp-conductor` 可以做 Gateway 的基础。它对外被外部 Host 的一个 Client 连接；对内则自己维护多个上游 Client，每个上游 Client 对应一个上游 MCP Server。

## Host 和 mcp-conductor 的核心区别

一句话：

```text
Host 管模型。
mcp-conductor 管上游 MCP 能力。
```

Host 的中心职责是用户对话、大模型调用、上下文构建、工具暴露和工具结果回填。

`mcp-conductor` 的中心职责是上游 MCP Server 的连接、能力发现、能力筛选、调用转发和结果整理。

所以 `mcp-conductor` 可以包含 MCP Client 管理能力，但这不等于它是完整 Host。它是一个带有内部 Client 管理器的 MCP Gateway Server。

## 背景问题

当用户直接在外部 Host 中配置很多 MCP Server 时，模型可能看到大量工具：

- 工具（tools）
- 资源（resources）
- 资源模板（resource templates）
- 提示词（prompts）

这会带来几个问题：

- 工具数量过多，占用上下文和注意力。
- 相似工具互相干扰，模型更容易选错。
- 危险工具可能被错误暴露。
- 工具返回结果过大，容易挤占对话上下文。
- 模型需要在过大的工具集合里推理，效率和准确率都会下降。

`mcp-conductor` 的思路是：不要让外部 Host 直接配置全部上游 MCP Server，而是让外部 Host 只配置 `mcp-conductor`，再由 `mcp-conductor` 在内部管理这些上游 Server。

## 整体结构

```text
外部 MCP Host
  └─ 外部 Client ── mcp-conductor 作为标准 MCP Server

mcp-conductor 内部
  ├─ 上游 Client A ── 上游 MCP Server A
  ├─ 上游 Client B ── 上游 MCP Server B
  └─ 上游 Client C ── 上游 MCP Server C
```

在推荐配置下，外部 Host 看到的是 `mcp-conductor` 暴露的少量高级工具。上游 MCP Server 的大量底层工具不会直接暴露给外部 Host，而是在 `mcp-conductor` 内部按任务筛选后以候选能力形式返回。

## 核心目标

`mcp-conductor` 的目标不是替代所有 MCP Server，而是管理上游 MCP 能力：

- 像普通 MCP Server 一样被外部 Host 配置。
- 读取内部上游 MCP Server 配置。
- 连接多个上游 MCP Server。
- 发现每个上游 Server 暴露的能力。
- 建立统一的能力注册表。
- 根据用户任务筛选候选能力，并只返回当前任务需要的紧凑能力信息。
- 可选通过 Host 采样路由器辅助判断应该使用哪些能力。
- 在外部模型携带有效推荐凭证和参数后，调用对应上游 MCP Server。
- 对上游返回结果做摘要、分页、缓存或引用管理。
- 将整理后的结果返回给外部 Host。

## 重要边界

`mcp-conductor` 不能控制外部 Host 中其他 MCP Server 的暴露方式。

如果用户在外部 Host 里同时配置：

```text
mcp-conductor
github-mcp
filesystem-mcp
database-mcp
```

那么外部大模型仍然可能直接看到这些 MCP Server 暴露的工具。

如果希望 `mcp-conductor` 真正发挥“减少工具暴露、统一筛选路由”的作用，推荐配置方式是：

```text
外部 Host 只配置 mcp-conductor
mcp-conductor 内部再配置 github/filesystem/database 等上游 MCP Server
```

还有一个同样重要的边界：

```text
mcp-conductor 作为 MCP Server，不能强制外部 Host 每次用户输入或每次 agent loop 步骤都先调用自己。
```

Codex、Claude Code 这类工具内部有自己的 agent loop。它们会根据用户问题、当前上下文、可见工具和自身策略决定下一步是否调用某个 MCP tool。`mcp-conductor` 可以通过 server instructions、`analyze_user_task` 和可执行推荐结果降低触发门槛，但最终是否触发仍由外部 Host/模型决定。

如果产品目标升级为“每一轮内部思考和每次工具结果之后都必须重新筛选上游能力”，那就已经超出普通 MCP Server 能单独完成的范围，需要新增 Host wrapper、Agent Orchestrator 或 IDE/plugin 层来控制循环。

## 第一阶段范围

第一版优先跑通：

- 对外启动为标准 MCP Server。
- 提供少量高级工具。
- 读取内部上游 MCP Server 配置。
- 连接上游 MCP Server。
- 发现上游 tools/resources/resource templates/prompts。
- 建立能力注册表。
- 根据用户任务推荐候选能力。
- 通过 `analyze_user_task` 或 `recommend_capabilities` 返回 `recommendation_id`、`route_token`、`next_public_tool` 和 `ready_to_call_arguments`。
- 按能力类型通过 `call_upstream_tool`、`read_upstream_resource`、`read_upstream_resource_template` 或 `get_upstream_prompt` 访问已推荐、已校验、风险策略允许的上游能力，并返回裁剪后的结果。
- 对危险操作返回 `confirmation_required` 或通过 Elicitation 请求 Host 收集确认。
- 可选使用 Roots、Logging、Progress、Cancellation 和 Pagination 等协议能力改善边界、安全和体验。

## 当前实现状态快照

截至当前文档状态，项目已经完成 Gateway MVP 的主要链路：

- 对外 FastMCP Server 和九个公开工具已经建立。
- 内部上游配置支持 `mcpServers` 和 `upstreamServers` 两种写法。
- 默认本地配置文件为 `mcp-conductor.config.json`；显式 `--config` 优先。
- 配置文件同目录的 `.env` 会在解析 `${NAME}` 变量前加载。
- 已支持发现和受控访问 tools、resources、resource templates、prompts。
- `learn-mcp-server` 真实上游 smoke 已跑通能力发现、推荐和四类公开访问工具。
- `exposure` 已有 `router`、`proxy`、`hybrid` 配置和诊断计划，但 `proxy/hybrid` 尚未动态注册上游工具。

因此，当前项目已经完成“配置多个上游 MCP Server，并通过一个 Gateway 做发现、推荐、受控调用”的核心部分；还没有完成“强制每次 Host 内部循环都先经过 `mcp-conductor`”这一部分。

## 后续主线

后续开发应分成两条线，不要混在一起：

1. `mcp-conductor-core`：继续完善当前 MCP Gateway Server，包括更多真实上游联调、错误恢复、健康检查、动态 reload、Host Sampling 路由和可选 proxy/hybrid 动态工具注册。
2. `mcp-conductor-agent`：如果确实需要强制每轮筛选，则新增 Host/Agent Orchestrator。它负责接收每次用户输入和每次 loop 步骤，将当前步骤内容交给 `mcp-conductor-core` 筛选，再把筛选后的工具面交给模型。

## 参考资料

- MCP 架构概览：https://modelcontextprotocol.io/docs/learn/architecture
- MCP 架构规范：https://modelcontextprotocol.io/specification/2025-06-18/architecture
- MCP 客户端说明：https://modelcontextprotocol.io/docs/learn/client-concepts
