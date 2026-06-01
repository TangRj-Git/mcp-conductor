# mcp-conductor 项目分析文档

这个目录用于保存 `mcp-conductor` 在正式实现前和实现过程中的需求分析、模块设计、架构决策和讨论结论。

## 当前项目定位

`mcp-conductor` 不是一个完整 MCP Host，而是一个 **MCP Gateway Server**。

它对外表现为一个标准 MCP Server，可以像其他 MCP Server 一样配置到 Claude、Codex、Cursor、Cherry Studio 或其他 MCP Host 中使用。

它对内会作为 MCP Client 连接多个上游 MCP Server，发现它们暴露的 tools、resources、resource templates 和 prompts，然后通过能力路由、工具筛选和结果管理，为外部 Host 提供少量高级调度工具。

一句话：

> `mcp-conductor` 对外是 MCP Server，对内是 MCP Client + 能力路由器。

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

## 维护约定

- 需求讨论结论先写入这里，再进入正式实现。
- 所有文档都应保持“对外 Server、对内 Gateway”的项目定位。
- 新增模块前，先在 `03-module-analysis.md` 中说明职责和边界。
- 涉及工具筛选、结果压缩、权限控制的方案，优先更新 `04-tool-selection-flow.md`。
- 涉及配置和使用方式的方案，优先更新 `06-usage-model.md`。
- 涉及 Host、Server、Client 职责边界的方案，优先更新 `07-host-vs-gateway-server.md`。
- 涉及 Sampling、Roots、Elicitation、Logging、Progress、Cancellation、Pagination、Completion 的方案，优先更新 `08-client-primitives-and-safety.md`。
- 涉及完整执行链路和交互步骤的方案，优先更新 `09-end-to-end-flow.md`。
- 尚未确定的内容写入 `05-open-questions.md`，不要直接写进最终设计。
