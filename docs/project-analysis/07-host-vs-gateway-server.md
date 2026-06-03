# Host 与 mcp-conductor 的区别

## 核心结论

`mcp-conductor` 不是完整 MCP Host，而是 MCP Gateway Server。

最短的区别是：

```text
Host 管模型。
mcp-conductor 管上游 MCP 能力。
普通 MCP Server 提供具体能力。
MCP Client 连接具体 Server。
```

## Host 的职责

Codex、Claude Code、Cursor、Cherry Studio 这类应用属于 Host。

Host 负责：

- 接收用户输入。
- 管理对话上下文。
- 调用大模型。
- 决定这一轮给大模型暴露哪些 tools/resources/resource templates/prompts。
- 接收大模型产生的工具调用意图。
- 找到对应 MCP Client。
- 调用对应 MCP Server。
- 把工具结果放回模型上下文。
- 将最终回答展示给用户。

Host 是大模型运行环境和总控层。

## 普通 MCP Server 的职责

普通 MCP Server 负责向 Host 提供能力。

它通常负责：

- 暴露 tools。
- 暴露 resources。
- 暴露 resource templates。
- 暴露 prompts。
- 接收 Host 通过 Client 发来的调用。
- 执行自己的业务逻辑。
- 返回结果。

普通 MCP Server 不直接管理大模型，也不管理其他 MCP Server。

## mcp-conductor 的职责

`mcp-conductor` 对外仍然是一个 MCP Server，但内部会连接多个上游 MCP Server。

它存在的主要原因是：避免外部 Host 直接配置大量 MCP Server 后，把全部底层工具、资源和 prompt 都暴露给大模型，造成上下文膨胀和工具选择准确性下降。

它负责：

- 被外部 Host 像普通 MCP Server 一样配置。
- 对外暴露少量高级调度工具。
- 读取内部上游 MCP Server 配置。
- 为每个上游 MCP Server 创建或维护独立 MCP Client/session。
- 发现上游 MCP Server 的能力。
- 建立统一能力注册表。
- 根据用户任务筛选并推荐上游能力。
- 在外部模型携带有效推荐凭证和参数后，受控访问上游能力。
- 管理上游返回的大结果。
- 将摘要、预览、分页或 `result_id` 返回给外部 Host。

因此它是：

```text
对外：MCP Server
对内：MCP Client Manager + Capability Router + Result Manager
```

## 它为什么不是完整 Host

`mcp-conductor` 不负责：

- 直接接收最终用户界面输入。
- 直接管理完整对话上下文。
- 直接决定外部模型看到的所有工具。
- 直接替代 Codex、Claude Code、Cursor 等 Host。
- 阻止外部 Host 直接配置其他 MCP Server。
- 管理完整模型生命周期。

它可以通过 Host 采样路由器或其他受控模型能力辅助筛选上游能力，但这只是内部路由逻辑，不等于它成为完整 Host。

如果需要模型推理，`mcp-conductor` 应通过 MCP Sampling 请求外部 Host 使用其受控模型。Host 仍然掌握模型选择、权限、用户批准和结果是否返回给 Server 的控制权。

## 连接模型

外部关系：

```text
用户
  ↓
外部 Host
  ↓
外部 Host 的 MCP Client
  ↓
mcp-conductor 服务
```

内部关系：

```text
mcp-conductor
  ├─ 上游 Client A ── 上游 MCP Server A
  ├─ 上游 Client B ── 上游 MCP Server B
  └─ 上游 Client C ── 上游 MCP Server C
```

## 设计边界

`mcp-conductor` 可以做：

- 上游能力发现。
- 上游能力筛选。
- 上游工具调用转发。
- 上游结果压缩。
- 上游结果缓存。
- 对外提供统一高级工具。
- 通过 Sampling 请求 Host 做受控路由推理。
- 通过 Elicitation 请求 Host 收集危险操作确认或缺失参数。
- 通过 Roots 获取 Host 暴露的工作区边界。
- 通过 Logging、Progress、Cancellation、Pagination、Completion 等协议能力改善可观测性、长任务体验和列表/补全交互。
- 作为上游 MCP Server 的 Client 时，对上游发起的 Sampling、Roots、Elicitation 等请求执行保守桥接策略。

`mcp-conductor` 不应该在第一阶段做：

- 完整聊天应用。
- 完整 Host。
- 完整模型上下文调度系统。
- 外部 Host 配置管理器。
- 全局 MCP 权限中心。
- 动态替外部 Host 改写真实工具列表。
- 让外部模型一次看到全部上游能力。
- 绕过 Host 自己配置模型 API 密钥。
- 绕过 Host 自己向用户确认危险操作。

## 推荐配置方式

为了让 `mcp-conductor` 发挥作用，推荐：

```text
外部 Host 只配置 mcp-conductor
其他 MCP Server 配置在 mcp-conductor 内部
```

如果外部 Host 同时配置 `mcp-conductor` 和所有上游 MCP Server，外部模型仍然可能直接看到和调用底层工具，从而绕过 `mcp-conductor` 的筛选与结果管理。

## 对“每轮都先筛选”的结论

用户想要的理想体验可以表述为：

```text
Codex / Claude Code 开始处理用户问题
  -> 先把当前用户问题交给 mcp-conductor 筛选工具
  -> 模型只在筛选后的工具范围内选择
  -> 每次工具结果或内部新步骤出现
  -> 再把当前步骤内容交给 mcp-conductor 筛选工具
  -> 模型继续处理
```

这个体验本质上是 Host/Agent Runtime 的职责，因为只有 Host/Agent Runtime 才能控制：

- 用户输入进入模型之前发生什么。
- 每次模型生成工具调用之前看到哪些工具。
- 工具结果回填模型之前是否要重新筛选能力。
- agent loop 什么时候继续、暂停、重试或结束。

`mcp-conductor` 当前作为 MCP Server，只能在被调用时返回推荐和执行上游能力。它可以成为每轮筛选的核心服务，但不能自己强制成为每轮入口。

因此后续架构应拆成：

```text
mcp-conductor-core
  当前 Gateway Server，负责上游配置、发现、推荐、凭证、执行、安全和结果。

Host wrapper / Agent Orchestrator
  后续 Host wrapper / Agent Orchestrator，负责控制每次用户输入和每次 loop 步骤是否必须调用 core。
```
