# mcp-conductor 项目分析文档

这个目录用于保存 `mcp-conductor` 在正式实现前和实现过程中的需求分析、模块设计、架构决策和讨论结论。

## 当前项目定位

`mcp-conductor` 不是一个完整 MCP Host，而是一个 **MCP Gateway Server**。

它对外表现为一个标准 MCP Server，可以像其他 MCP Server 一样配置到 Claude、Codex、Cursor、Cherry Studio 或其他 MCP Host 中使用。

它要解决的核心问题是：当很多 MCP Server 直接配置在外部 Host 里时，大模型会看到过多 tools/resources/prompts，导致工具上下文膨胀、注意力被分散、工具选择准确性下降。

`mcp-conductor` 的做法是让外部 Host 尽量只配置它一个入口；它再在内部作为 MCP Client 连接多个上游 MCP Server，发现它们暴露的 tools、resources、resource templates 和 prompts，并根据每轮用户任务返回紧凑的候选能力、调用凭证和必要 schema。这样模型仍然可以充分使用已配置的上游 MCP 能力，但不需要每轮直接面对全部底层工具。

一句话：

> `mcp-conductor` 对外是 MCP Server，对内是 MCP Client + 能力调度网关；核心价值是压缩工具上下文，并提高每轮任务的工具选择准确性。

## 关键 MCP 连接模型

MCP 的连接关系通常是：

```text
Host
  ├─ Client A ── Server A
  ├─ Client B ── Server B
  └─ Client C ── Server C
```

也就是说，Host 会为每个配置的 MCP Server 创建或维护一个对应的 MCP Client/session。每个 Client 负责和一个 Server 建立专用连接、完成初始化、能力发现和工具调用。

`mcp-conductor` 的特殊之处是它有两层身份：

```text
外部 Host
  └─ 外部 Client ── mcp-conductor

mcp-conductor
  ├─ 上游 Client A ── 上游 Server A
  ├─ 上游 Client B ── 上游 Server B
  └─ 上游 Client C ── 上游 Server C
```

外部 Host 只把 `mcp-conductor` 当作一个普通 MCP Server。`mcp-conductor` 内部则为每个上游 MCP Server 创建对应的上游 Client。

## 文档结构

- `01-project-overview.md`：项目定位、边界和整体架构。
- `02-requirements.md`：需求分析和核心问题。
- `03-module-analysis.md`：当前计划中的模块拆分。
- `04-tool-selection-flow.md`：工具筛选、路由代理和结果管理流程。
- `05-open-questions.md`：后续需要继续确认的问题。
- `06-usage-model.md`：外部 Host 如何配置使用，以及内部上游 MCP 如何配置。
- `07-host-vs-gateway-server.md`：Host、普通 MCP Server 和 `mcp-conductor` 的职责区别。
- `08-client-primitives-and-safety.md`：Server 如何受控使用 Sampling、Roots、Elicitation 等 Client/Host 侧能力。
- `09-end-to-end-flow.md`：从配置、启动、能力发现、推荐、调用、确认到结果返回的完整工作流程。
- `10-trigger-and-routing-improvements.md`：当前针对 Host 触发、推荐结果可执行性、错误恢复和配置展开能力的改进说明。
- `11-host-orchestrator-and-step-routing.md`：说明“每次用户输入和每次 agent loop 步骤都先筛选能力”为什么需要 Host/Agent Orchestrator，以及当前 Gateway Server 能先实现哪些配套能力。

## 推荐阅读顺序

如果只是想快速判断项目是否符合最初设想，建议按下面顺序阅读：

1. `01-project-overview.md`：先确认项目定位和边界。
2. `07-host-vs-gateway-server.md`：确认 Host、Client、普通 MCP Server 和 `mcp-conductor` 分别负责什么。
3. `04-tool-selection-flow.md`：理解当前推荐链路如何把“上游很多能力”压缩成“当前任务候选能力”。
4. `10-trigger-and-routing-improvements.md`：理解当前 MCP Server 形态下的触发限制。
5. `11-host-orchestrator-and-step-routing.md`：理解如果要强制每轮筛选，下一步应该开发什么。

当前最重要的结论是：

```text
mcp-conductor-core 当前是 MCP Gateway Server。
它能被 Codex、Claude Code 等 Host 调用，但不能强制接管这些 Host 的内部 agent loop。

如果要做到“每次用户输入和每次内部循环都先经过能力筛选”，
必须在 Gateway 外面增加 Host wrapper、Agent Orchestrator 或 IDE/plugin 层。
```

## 维护约定

- 需求讨论结论先写入这里，再进入正式实现。
- 所有文档都应保持“对外 Server、对内 Gateway”的项目定位，并围绕“减少 Host 直接暴露工具数量、动态推荐当前任务所需能力、受控执行上游工具”这条主线展开。
- 文档不能把 `mcp-conductor` 描述成完整 Host、完整聊天代理、全局权限中心，或可以直接控制外部模型完整工具上下文的系统。
- 新增模块前，先在 `03-module-analysis.md` 中说明职责和边界。
- 涉及工具筛选、结果压缩、权限控制的方案，优先更新 `04-tool-selection-flow.md`。
- 涉及配置和使用方式的方案，优先更新 `06-usage-model.md`。
- 涉及 Host、Server、Client 职责边界的方案，优先更新 `07-host-vs-gateway-server.md`。
- 涉及 Sampling、Roots、Elicitation、Logging、Progress、Cancellation、Pagination、Completion 的方案，优先更新 `08-client-primitives-and-safety.md`。
- 涉及完整执行链路和交互步骤的方案，优先更新 `09-end-to-end-flow.md`。
- 涉及每轮 agent loop 筛选、Host wrapper、Agent Orchestrator 或强制触发能力的方案，优先更新 `11-host-orchestrator-and-step-routing.md`。
- 尚未确定的内容写入 `05-open-questions.md`，不要直接写进最终设计。
