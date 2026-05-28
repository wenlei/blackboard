# 术语表

> 统一项目内的术语定义，避免沟通歧义。所有文档、代码注释、PR 描述中应使用本表定义的术语。
> 最后更新：2026-05-27

## 术语列表

| 术语 | 全称 / 英文 | 定义 | 首次出现 |
|------|------------|------|----------|
| Blackboard | — | 项目名称，LLM Agent 调度框架 | background.md |
| Agent | — | 可被调度的 LLM 执行单元，封装了 LLM Provider API 的适配器（通过 ChatCompletionsAdapter 统一调用），在 registry 中以唯一实例名注册 | architecture.md |
| Adapter | Agent Adapter | LLM API 的封装层，实现统一的 BaseAgent 接口；当前统一实现为 ChatCompletionsAdapter（OpenAI 兼容接口），替代早期各 Provider 独立适配器 | architecture.md |
| Host | — | Session 内指挥中心（per-session 独立实例），内置 .psc 编译器 + 执行器，负责策略生成、任务分发、结果路由、回复生成 | architecture.md |
| Session Manager | — | Session 生命周期管理（创建/暂停/恢复/关闭），Agent 动态增减，全局配置加载 | architecture.md |
| Session Guard | — | 权限守卫模块，whitelist / approval_first / open 三种模式，分发前校验 + 执行中回调校验 | architecture.md |
| IM Bridge | — | 外部消息渠道适配层（Telegram/Discord/Slack），统一收发接口 | architecture.md |
| Session Logger | — | 全量操作落盘模块（conversation/messages/events），支持回放 | architecture.md |
| System Config | — | 全局配置管理模块：系统参数、Agent 注册表、策略模板库、权限预设 | architecture.md |
| MQ | Message Queue | 消息队列，本项目指 Redis Streams | architecture.md |
| Stream | Redis Stream | Redis 5.0+ 的数据结构，类似 append-only log，支持消费者组 | architecture.md |
| Consumer Group | 消费者组 | Redis Streams 的特性，允许多个消费者共享消费进度，每条消息只被组内一个消费者处理 | architecture.md |
| XADD | — | Redis Streams 命令，向 Stream 追加消息 | architecture.md |
| XREAD | — | Redis Streams 命令，无消费者组的直接读取；SSE 端点用 XREAD（每个客户端维护独立 last_id 游标，实现广播语义） | architecture.md |
| XREADGROUP | — | Redis Streams 命令，消费者组模式读取消息；Worker 消费者（Agent、Host）用此命令（竞争投递，每条消息只被处理一次） | architecture.md |
| XACK | — | Redis Streams 命令，确认消息已处理 | architecture.md |
| PEL | Pending Entries List | 消费者组中已读取但未 ACK 的消息列表，用于故障恢复 | architecture.md |
| Pub/Sub | Publish/Subscribe | 消息模式，发布者不关心消费者身份 | architecture.md |
| SSE | Server-Sent Events | 服务端向客户端推送实时事件的 HTTP 协议 | architecture.md |
| Task | — | 一次 LLM 调用请求，包含 prompt、目标 agent、参数等 | architecture.md |
| Intervention | — | 用户对进行中任务的介入操作（取消/重定向/修改 prompt） | architecture.md |
| Session | — | 一次完整的多 Agent 协作会话，拥有独立的 MQ Stream 组和文件存储 | architecture.md |
| Inbox | — | Session 内的消息入口 Stream，用户消息通过 API 或 IM Bridge 写入，Host 消费 | architecture.md |
| Outbox | — | Session 内的回复出口 Stream，Host 写入回复，API Server 或 IM Bridge 消费并回传用户 | architecture.md |
| agent_mem | Agent Memory | ~~`agents/{name}/agent_mem.md`~~ **已取代**，见 Episodic Memory 和 Agent role LTM | ADR-009（已取代） |
| session_mem | Session Memory | ~~`session_mem.md`~~ **已取代**，见 Dialog 和 Workspace LTM | ADR-009（已取代） |
| Participant | — | Session 内非 Host 的 Agent，执行具体任务（coder / reviewer 等）；与 Host 的区别：无路由职责，无状态，只接收 Host 组装好的 context 执行 | ADR-019 |
| Dialog | — | Session 内的结构化对话记录（`dialog.jsonl`），记录所有消息交换；所有 Agent 均可读；区别于系统运营 Log（errors/warnings/metrics） | ADR-018 |
| Working Memory | — | Per-call 层；持有者：Agent（Host + Participant 各自独立）；Host 为每次 LLM 调用组装的即时 context（soul + dialog 摘要 + LTM 片段 + 当前任务），调用结束后丢弃；不落盘 | ADR-018 |
| Episodic Memory | — | Per-session 层；持有者：Host（session 级统一管理）；包含 `dialog.jsonl`（所有 Agent 可读）和 `agents/{name}/episodic.md`（per-agent 经历）；随 session 生灭，落盘 | ADR-018 |
| Workspace LTM | Workspace Long-Term Memory | Cross-session 层；持有者：Workspace；`config/workspace_ltm.md`；所有 Agent 启动时均加载；存储用户偏好、项目背景、通用规则；永久持久，落盘 | ADR-018 |
| Agent role LTM | Agent Role Long-Term Memory | Cross-session 层；持有者：Workspace；`config/agents/{name}/ltm.md`；仅对应 Agent 加载；存储该角色跨 session 积累的知识和经验；永久持久，落盘 | ADR-018 |
| 热层 | Hot Layer | Episodic Memory 的读取视图层；本质是 `dialog.jsonl` 末尾的滑动窗口，原文 verbatim 注入 context，不独立存储；大小由 token budget 动态计算（非固定 K 轮），上限 MAX_HOT_TURNS=50 | architecture.md |
| 暖层 | Warm Layer | Episodic Memory 的摘要层；热层溢出的 turn 由 Host LLM 滚动压缩为摘要后注入 context；大小有上限（约可用输入 10%），超出时对摘要再次压缩 | architecture.md |
| 冷层 | Cold Layer | Episodic Memory 的主存储层；即 `dialog.jsonl`，每条 turn 实时 append，原文永久保留；热层和暖层均派生自冷层；平时不注入 context，仅在 session 关闭/恢复/用户显式回溯时读取 | architecture.md |
| context_window | — | 模型单次调用可处理的最大 token 总量（输入 + 输出之和），来自 models.dev `limit.context`，存储在 `ModelInfo.context_window` | architecture.md |
| max_output_tokens | — | 模型单次调用可生成的最大输出 token 数（硬上限），来自 models.dev `limit.output`，存储在 `ModelInfo.max_output_tokens`；用于约束 per_call_max_tokens | architecture.md |
| per_call_max_tokens | — | 每次 LLM 调用实际预留的输出 token 数（≤ max_output_tokens），由 Host 按任务类型设定（默认 2048）；budget 计算中扣除的是此值，而非模型硬上限 | architecture.md |
| context_ratio | — | 单次 LLM 调用的 context 压力指标：`tokens_used / context_window`；记录在 `dialog.jsonl` 每条 meta 字段；>0.8 触发 WARNING，>0.95 触发 ERROR | architecture.md |
| Archive | — | Session 归档操作：打包为 archive.tar.gz 推送到远端，远端写入 log.md，本地仅保留 config + strategy.psc；冷层（dialog.jsonl）原文在远端永久保留；本地删除冷层前必须完成 LTM 提炼（门控条件） | architecture.md |
| Sandbox | — | 隔离执行环境，Agent 的 execute_code 等危险操作在受限目录或 Docker 子容器中运行 | architecture.md |
| Registry | Agent Registry | System Config 中的全局 Agent 注册表（registry.yaml），管理可用的 LLM 实例（实例名 → provider / model / api_key） | architecture.md |
| 实例名 | Instance Name | Agent 在 registry 中的唯一标识键，由用户自定义（如 DS1、my-claude）；同一 Provider 可注册多个实例，每个实例独立配置 api_key、model_list、default_model（以实例名为键存储，互不影响） | architecture.md |
| provider_slug | — | Provider 的系统标识符（如 `deepseek`、`openai`），全局唯一且固定；与实例名的区别：slug 用于 base_url 推断和 OpenRouter 查询，不用于凭据存储键（凭据键 = 实例名） | rules/config.md |
| ChatCompletionsAdapter | — | 统一 OpenAI 兼容适配器，替代早期 DeepSeek/Claude/OpenAI 各自独立适配器；通过 base_url + api_key 接入任意 OpenAI 兼容 Provider（含 OpenRouter） | architecture.md |
| Provider Preset | Provider 预设 | provider_presets.yaml 中定义的已知 Provider 配置（base_url / auth_type / protected 标记），供 UI 下拉选择时自动填充 base_url；与 registry.yaml 注册表相互独立 | architecture.md |
| OpenRouter Catalog | — | OpenRouter 公开 API（`GET /api/v1/models`，无需认证）返回的模型目录，包含模型 ID、显示名、context_length、architecture 等属性数据；Add 模式通过 `GET /api/config/providers/{slug}/catalog` 代理拉取，不含 pricing 和 OpenRouter 路由配置 | rules/config.md |
| Strategy Template | — | 预定义的工作流模板（4 套），Host 匹配后由 LLM 动态补充为完整策略 | architecture.md |
| strategy.psc | Strategy Pseudo-Code | 策略伪代码文件（**单一真相源**），人可读的文本格式（`AGENT: 动作 → 输出` + `IF/ELSE` 控制流），来源：Host LLM 生成 / DAG 编辑器导出 / 用户手动编辑 | architecture.md |
| DAG | Directed Acyclic Graph | 可视化工作流编辑器中的有向无环图，节点为 Agent/条件/汇聚，连线为数据流/控制流 | architecture.md |
| PscParser | — | .psc 文本 → AST → DAG 可视化渲染（双向转换的解析方向） | architecture.md |
| DagSerializer | — | DAG 节点/连线 → .psc 伪代码文本（双向转换的导出方向） | architecture.md |
| AST | Abstract Syntax Tree | 抽象语法树，.psc 经编译器解析后的中间表示，执行器遍历 AST 逐步通过 MQ 分发 Agent 执行 | architecture.md |
| PSC Compiler | — | Host 内置组件，将 .psc 伪代码编译为 AST，输出 strategy.json 用于机器执行 | architecture.md |
| PSC Executor | — | Host 内置组件，遍历 AST 逐步执行：Guard 校验 → dispatched Stream 分发 → results Stream 收结果 → 分支/循环/跳转 | architecture.md |
| Tool Registry | — | 工具/技能注册表（config/tools/registry.yaml），定义 7 个内置工具及其 handler，与 Session Guard 权限联动 | architecture.md |
| ToolCall | — | Agent 发起的工具调用请求（tool_name + parameters），经 Guard 校验后由 ToolExecutor 执行 | architecture.md |
| ToolResult | — | 工具调用的返回结果（success + result 或 error） | architecture.md |
| ToolExecutor | — | 工具执行器，接收 ToolCall 分派到 filesystem/sandbox/network/search 对应 handler | architecture.md |
| ToolParameter | — | 工具参数定义（name / type / description / required） | architecture.md |
| BaseAgent | — | Agent Adapter 的抽象基类，定义统一契约：execute / load_memory / save_memory / health_check | architecture.md |
| BaseIMBridge | — | IM Bridge 的抽象基类，定义统一接口：on_message / send_message / send_approval | architecture.md |
| Role | — | Agent 在 Session 中被分配的角色（如架构师、程序员、审查者），影响 Host 分发的 prompt 和行为 | architecture.md |
| target_channel | — | outbox 消息的路由字段，标识目标渠道（web_ui / telegram / discord），消费组据此判断是否投递 | architecture.md |
| whitelist | — | 权限模式：仅声明的操作可用，未声明自动 denied | architecture.md |
| approval_first | — | 权限模式：所有操作默认需先审批确认，适合调试/教学场景 | architecture.md |
| open | — | 权限模式：全部开放，仅 denied 列表拦截，适合信任场景 | architecture.md |
| require_approval | — | 操作权限状态：需推送审批请求到 outbox，等待用户批准或拒绝（5 分钟超时自动拒绝） | architecture.md |
| Approval | — | 审批流程：Guard 对 require_approval 操作推送审批请求，用户回复后决定放行或拒绝 | architecture.md |
| LLM | Large Language Model | 大语言模型 | background.md |
| Animal Island | — | 参考《动物森友会》风格的 UI 设计系统，用于 Web 前端 | decisions.md |
| ADR | Architecture Decision Record | 技术决策记录，记录重要选型及原因 | decisions.md |

---

<!--
新增格式：
| 术语缩写 | Full Term | 在本项目中的具体含义 | architecture.md / background.md 等 |
-->
