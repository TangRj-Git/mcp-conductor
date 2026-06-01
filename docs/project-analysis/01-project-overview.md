# 项目概览

## 项目名称

`mcp-conductor`

中文定位可以称为：MCP 能力调度器。

## 一句话定义

`mcp-conductor` 是一个可以像普通 MCP Server 一样配置使用的 MCP Gateway Server。它对外暴露少量高级调度工具，对内连接多个上游 MCP Server，并负责能力发现、工具筛选、调用转发和结果压缩。

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
- `mcp-conductor` 不直接管理用户对话，也不直接控制外部模型的完整工具上下文。

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

外部 Host 看到的是 `mcp-conductor` 暴露的少量高级工具。上游 MCP Server 的大量底层工具不会直接暴露给外部 Host。

## 核心目标

`mcp-conductor` 的目标不是替代所有 MCP Server，而是管理上游 MCP 能力：

- 像普通 MCP Server 一样被外部 Host 配置。
- 读取内部上游 MCP Server 配置。
- 连接多个上游 MCP Server。
- 发现每个上游 Server 暴露的能力。
- 建立统一的能力注册表。
- 根据用户任务筛选候选能力。
- 可选通过 Host 采样路由器辅助判断应该使用哪些能力。
- 代表外部 Host 调用上游 MCP Server。
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

## 第一阶段范围

第一版优先跑通：

- 对外启动为标准 MCP Server。
- 提供少量高级工具。
- 读取内部上游 MCP Server 配置。
- 连接上游 MCP Server。
- 发现上游 tools/resources/resource templates/prompts。
- 建立能力注册表。
- 根据用户任务推荐候选能力。
- 通过 `recommend_capabilities` 返回 `recommendation_id` 和 `route_token`。
- 通过 `call_upstream_tool` 调用一个已推荐、已校验、风险策略允许的只读上游工具，并返回裁剪后的结果。
- 对危险操作返回 `confirmation_required` 或通过 Elicitation 请求 Host 收集确认。
- 可选使用 Roots、Logging、Progress、Cancellation 和 Pagination 等协议能力改善边界、安全和体验。

## 参考资料

- MCP 架构概览：https://modelcontextprotocol.io/docs/learn/architecture
- MCP 架构规范：https://modelcontextprotocol.io/specification/2025-06-18/architecture
- MCP 客户端说明：https://modelcontextprotocol.io/docs/learn/client-concepts
