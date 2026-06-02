# 项目结构文档

这个目录用于保存 `mcp-conductor` 的工程结构、源码目录规划、模块边界和后续功能实现相关的结构说明。

和 `docs/project-analysis` 的区别：

- `docs/project-analysis` 保存需求讨论、定位、流程和边界决策。
- `docs/project-structure` 保存这些决策落到代码工程时应该如何组织目录、文件、模块和入口。

后续约定：

1. 每个较大的功能在实现前，都应该在本目录下创建自己的结构说明文档。
2. 文档命名建议使用递增编号，例如 `02-config-structure.md`、`03-upstream-client-structure.md`。
3. 如果功能会新增目录、模块、配置文件或对外工具，需要在对应文档里说明职责和依赖方向。
4. 不确定的内容先写成“待确认”，不要直接变成实现约束。
5. 架构文档应和 `docs/project-analysis` 保持一致：`mcp-conductor` 对外是 MCP Server，对内是 MCP Client + Gateway。
6. 本目录下的说明文字使用中文；协议名、代码标识、配置字段、命令和文件名可以保留英文。

当前文档：

- `01-project-architecture.md`：第一版推荐项目架构、目录结构、模块职责和顶层 `main.py` 处理策略。
- `02-final-architecture-diagram.md`：最终目标架构图，包括总体拓扑、内部模块、调用链路、安全确认和 primitives 双向边界。
- `03-dangerous-action-confirmation.md`：危险操作确认结构，说明 `pending_action_id`、Host Elicitation、二次确认和拒绝规则。
- `04-error-handling-and-discovery-resilience.md`：错误处理和发现容错结构，说明上游访问错误、能力发现局部失败和 `discovery_errors` / `unavailable_upstreams` 的区别。
- `05-risk-policy-semantics.md`：风险策略语义，说明 `read_only_only`、`confirm_mutations`、`disabled` 三种策略如何影响推荐和执行。
- `06-real-upstream-integration-prep.md`：真实上游 MCP Server 联调准备，说明下一步如何选择低风险上游、配置、启动、发现、推荐、调用和验证。
- `07-step-routing-and-agent-orchestrator-structure.md`：后续 step routing、routing session 和可选 Host/Agent Orchestrator 的工程拆分建议。
