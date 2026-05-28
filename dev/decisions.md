# 技术决策记录（ADR）

> 记录重要的技术选型和架构决策，包括被否决的方案及原因。

---

## ADR-001 — 项目文档结构选型

**日期**：2026-05-19
**状态**：已采纳
**决策人**：项目负责人

### 背景
需要为 Blackboard 建立可持续维护的文档体系。

### 候选方案
| 方案 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| 当前方案 | 8 文件标准结构（instruction 在根目录 + 7 个 dev/ 文件） | 覆盖完整、职责清晰 | 初始建立有成本 |
| 单 README | 所有内容放一个文件 | 简单 | 项目增长后难维护 |

### 决策
采用 8 文件标准结构，职责分离，`instruction.md` 放在项目根目录作为入口，配合 `AGENTS.md` 实现 `/sync-docs` 自动同步。

### 后续影响
所有开发和 AI 协作均需遵循 `rule.md` 中的规范。

---

## ADR-002 — 架构模式选择：事件驱动 + Agent 编排

**日期**：2026-05-19
**状态**：已采纳
**决策人**：项目负责人

### 背景
Blackboard 需要编排多个 LLM agent，Agent 集成层预计变化最频繁。需要在解耦、运维成本和扩展性之间取得平衡。

### 候选方案
| 方案 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| 事件驱动 + Agent 编排 | Redis Streams 作为事件总线，各 Agent 作为独立消费者组 | 极低耦合、新增 Agent 即插即用、Docker 单机可跑 | Streams 消费者组管理有学习成本 |
| 模块化单体 | Scheduler + Adapters 合并为单进程 | 简单直接、部署最轻 | 新增 Agent 需改核心代码、耦合度高 |
| 微服务 | 每个 Agent 独立服务 + 服务网格 | 极致解耦和独立扩展 | 运维成本远超当前团队规模、过度设计 |
| Serverless | Agent 作为云函数按需调用 | 零运维 | LLM 调用耗时不确定导致超时风险、成本不可控 |

### 决策
采用事件驱动 + Agent 编排方案。Redis Streams 的消费者组机制天然支持多 Agent 并行消费和故障恢复，适配器模式让新增 LLM provider 无需修改核心调度代码。Docker 单机即可运行，满足个人/小团队的运维能力。

### 后续影响
- 所有组件间通信通过 Redis Streams，不可直接调用
- 新增 Agent 需实现 `BaseAgent` 接口并注册消费者组
- 调度策略在 Host 模块中独立实现，可插拔

---

## ADR-003 — 消息队列选型：Redis Streams

**日期**：2026-05-19
**状态**：已采纳
**决策人**：项目负责人

### 背景
需要一种消息队列支撑 Agent 间通信，要求支持 Pub/Sub 模式、消费者组、消息持久化和 ACK 机制。

### 候选方案
| 方案 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| Redis Streams | Redis 5.0+ 内置 Streams 数据结构 | 零额外依赖（已选 Redis）、消费者组、ACK、持久化、生态成熟 | 复杂路由不如 RabbitMQ |
| RabbitMQ | 传统消息队列 | 功能完整、复杂路由 | 运维重、额外服务、镜像大 |
| NATS | 轻量消息系统 | 超轻量、低延迟、嵌入式可用 | 生态相对小、持久化配置较弱 |
| SQLite + WAL | 文件数据库实现队列 | 零依赖 | 无原生消费者组、高并发表现差 |

### 决策
采用 Redis Streams。Redis 已作为项目的核心基础设施，Streams 是其内置功能无需额外部署。支持消费者组（XREADGROUP）、消息 ACK（XACK）、消息持久化和 PEL（Pending Entries List）提供了完整的消息可靠性保证。

### 后续影响
- MQ 层封装 `redis-py` 的 Streams 操作
- 所有跨组件通信统一使用 Streams
- 消费者组命名规则：`{stream_name}-{consumer_group}`

---

## ADR-004 — UI 风格选型：Animal Island CSS

**日期**：2026-05-19
**状态**：已采纳
**决策人**：项目负责人

### 背景
Web UI 需要一种友好、有辨识度的设计风格。直接使用 React 组件库会增加前端复杂度，与「先 API 后 UI」的路线不一致。

### 候选方案
| 方案 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| Animal Island CSS | 提取 animal-island-ui 的 CSS 变量和设计 Token，配合 Jinja2 模板 | 无前端框架依赖、风格独特、与 FastAPI 无缝集成 | 需手动提取 CSS、无现成 React 组件 |
| React + animal-island-ui | 独立 React 项目安装 npm 包 | 组件完整、功能丰富 | 增加前端项目复杂度、与后端分离部署 |
| Bootstrap/Tailwind | 主流 CSS 框架 | 生态完善、文档丰富 | 风格普通无辨识度 |

### 决策
采用 Animal Island CSS 方案。提取 animal-island-ui 项目的 CSS 变量体系（设计 Token）、字体文件到本地 `static/` 目录，通过 Jinja2 模板引用。保持「先 API 后 UI」的渐进式路线，后续如需更丰富的交互可迁移到 React。

### 后续影响
- 从 `guokaigdg.github.io/animal-island-ui/assets/` 下载字体文件和 CSS 变量
- Jinja2 模板使用 `animal-*` CSS 类名和变量
- UI 页面风格统一为动物森友会主题

---

## ADR-005 — API 框架选型：FastAPI

**日期**：2026-05-19
**状态**：已采纳
**决策人**：项目负责人

### 背景
需要一种 Python Web 框架来构建 REST API，要求支持异步 I/O、自动生成 API 文档、SSE（Server-Sent Events）和 Jinja2 模板渲染。

### 候选方案
| 方案 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| FastAPI | 现代 Python 异步 Web 框架 | 异步原生支持、自动 OpenAPI、Pydantic v2 集成、SSE 支持、Jinja2 支持 | 相对较新 |
| Flask | 传统 Python Web 框架 | 成熟稳定、Jinja2 原生支持 | 无原生异步、无自动 API 文档、需插件 |
| Django | 全栈 Web 框架 | 功能完整 | 太重、ORM 用不上 |
| Litestar | 新兴异步框架 | 轻量异步 | 生态不如 FastAPI |

### 决策
采用 FastAPI。项目核心场景（LLM API 调用、Redis I/O、SSE 推送）都是 I/O 密集型，异步支持至关重要。FastAPI 自动生成 OpenAPI 文档降低 API 调试成本，Pydantic v2 与 FastAPI 深度集成提供类型安全的数据校验。

### 后续影响
- 所有路由处理函数使用 `async def`
- 数据模型统一使用 Pydantic v2
- API 文档自动可通过 `/docs` 访问

---

## ADR-006 — 权限模型选型：Session Guard

**日期**：2026-05-19
**状态**：已采纳
**决策人**：项目负责人

### 背景
Agent 执行过程中可能涉及危险操作（执行代码、写文件、HTTP 请求），需要一套权限机制控制风险。要求支持白名单、审批确认、完全开放三种模式，且运行时可由用户动态调整。

### 候选方案
| 方案 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| Session Guard | 独立的权限守卫模块，whitelist / approval_first / open 三种模式 + 审批流程 + 分布前+执行中双重校验 | 精细控制、用户可介入、中间态拦截 | 增加一次往返延迟（~毫秒级） |
| 全局开关 | 全局二进制开关（开/关） | 极简 | 粒度太粗，无法区分不同操作类型的风险 |
| Agent 自查 | 每个 Agent 内部判断 | 无额外模块 | 可能被 LLM 绕过，不可靠 |

### 决策
采用 Session Guard 方案。8 种操作权限 × 3 种模式，危险操作需用户审批，5 分钟超时自动拒绝。支持分发前校验 + Agent 执行中回调校验。

### 后续影响
- Guard 作为独立模块运行，不依赖 LLM
- 所有 Agent 操作必经 Guard 校验
- 审批通过 outbox/approvals Stream 流转

---

## ADR-007 — 沙箱执行环境选型

**日期**：2026-05-19
**状态**：已采纳
**决策人**：项目负责人

### 背景
Agent 的 `execute_code` 操作需要隔离执行环境，防止污染宿主机或访问敏感文件。

### 候选方案
| 方案 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| Subprocess + 白名单目录 | Python subprocess 运行，限制 `/tmp/blackboard-sandbox/{session_id}/` | 零额外依赖、轻量 | 隔离不如 Docker 彻底 |
| Docker 子容器 | `docker run --rm --network=none --memory=256m` | 完全隔离 | 需要 docker.sock 挂载、镜像体积 |
| gVisor/Firecracker | 微型虚拟机 | 最强隔离 | 运维复杂度高 |

### 决策
分阶段实施：初期采用 subprocess + 白名单目录 + Docker Compose network 隔离；后期升级为 Docker 子容器方案。

### 后续影响
- 初期开发优先完成 subprocess 方案
- 代码架构预留 Docker 子容器切换接口

---

## ADR-008 — 归档与远端存储方案

**日期**：2026-05-19
**状态**：已采纳
**决策人**：项目负责人

### 背景
Session 长时间运行后数据文件累积，需要归档机制将历史 Session 打包转存，且支持多种远端存储类型（本地 NAS、S3、SFTP）。

### 候选方案
| 方案 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| 用户手动 Archive | `POST /api/sessions/{id}/archive` 用户指定远端类型和路径 | 用户控制、灵活 | 需用户操作 |
| 自动归档 | 系统自动判断并归档 | 省心 | 用户可能不知情 |
| 不归档 | 本地存储，用户自行管理 | 简单 | 磁盘可能撑爆 |

### 决策
采用用户手动触发 Archive 方案。用户选择远端类型（local_nas/s3/sftp）和路径，系统打包 → 推送 → 远端记录 log.md。容量阈值为 10GB，触达时 SSE 推送 warning 提示用户。

### 后续影响
- 实现远端存储适配器基类 + 三种实现
- `system.yaml` 增加 `storage.warning_threshold_gb` 配置
- archive 后本地仅保留 config + strategy

---

## ADR-009 — 记忆文件机制

**日期**：2026-05-19
**状态**：~~已采纳~~ → **已取代（见 ADR-018）**
**决策人**：项目负责人

### 背景
Host 和 Agent 在多轮执行中需要记忆上下文（当前步骤、历史任务、前序结果），Redis Streams 消息适合通信但不适合长期记忆。

### 候选方案
| 方案 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| Markdown 文件 | `session_mem.md` + `agents/{name}/agent_mem.md` | 人类可读、可直接编辑、回放友好 | 结构不如 JSON 严谨 |
| JSON 结构化 | 每个记忆条目精确数据结构 | 程序处理方便 | 人工查看和编辑不友好 |
| 向量数据库 | 语义检索历史记忆 | 智能检索 | 过重，MVP 阶段不必要 |

### 决策（已取代）
~~采用结构化 Markdown 文件方案。Host 维护 `session_mem.md`（全局），各 Agent 维护 `agents/{name}/agent_mem.md`（仅自己可见）。Session 启动时 `load_memory()` 载入，每次执行后 `save_memory()` 追加。~~

> 该方案缺乏分层设计，未区分 per-session 与 cross-session，未定义 LTM 写入路径，已被 ADR-018 三层 Memory 架构取代。

---

## ADR-010 — IM Bridge 多渠道适配

**日期**：2026-05-19
**状态**：已采纳
**决策人**：项目负责人

### 背景
用户需要通过 Telegram、Discord 等 IM 渠道与 Session 交互，消息需统一写入 inbox Stream，Host 回复需回传到对应渠道。

### 候选方案
| 方案 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| 适配器模式 | IM Bridge 基类 + 各渠道适配器 | 新增渠道只需实现适配器 | 需维护多个适配器 |
| Webhook 直连 | 各渠道直接写 Stream | 极简 | 无统一收发接口、代码散落 |
| 暂不支持 | 仅 Web UI | 先聚焦核心 | 丧失移动端交互场景 |

### 决策
采用适配器模式。定义 `BaseIMBridge` 接口（on_message / send_message / send_approval），Telegram 和 Discord 作为首批适配器。IM Bridge 放在本阶段开发，但优先级低于核心调度。

### 后续影响
- outbox Stream 增加 `target_channel` 字段路由回复
- IM 审批交互通过 Telegram InlineKeyboard / Discord Interaction 实现
## ADR-011 — Provider 配置外置：告别硬编码

**日期**：2026-05-22
**状态**：已采纳

### 背景
Provider 基础 URL、保护标记、Fallback 模型列表和前端 Pinned 模型 ID 分散在三个地方硬编码：`routes.py`（`BUILTIN_AGENTS`、`FALLBACK_MODELS`、`preset_base_urls`）和 `config.html`（`PROVIDER_PRESETS`、`PINNED_MODELS`）。同一份数据重复维护，新增或修改 Provider 必须改代码。

### 候选方案
| 方案 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| 全部外置到 YAML | 新增两个 YAML 文件 + API 端点 + 前端动态加载 | 单一数据源，无需改代码 | 需要加载逻辑和 API |
| 部分外置（仅 routes.py） | 只处理后端重复 | 改动少 | 前端 JS 仍硬编码 |
| 保持现状 | 不改 | 零风险 | 维护成本持续累积 |

### 决策
全部外置。新增两个配置文件：

- `config/agents/provider_presets.yaml` — 25 个 Provider 的 display_name / base_url / auth_type / protected，替代 `BUILTIN_AGENTS` + `preset_base_urls` + `PROVIDER_PRESETS`
- `config/agents/fallback_models.yaml` — 各 Provider 的 Fallback 模型列表和 Pinned Model IDs，替代 `FALLBACK_MODELS` + `PINNED_MODELS`

新增 `GET /api/config/provider-presets` 端点，前端在页面初始化时加载，不再依赖任何内嵌 JS 常量。

### 后续影响
- 新增 Provider 只需编辑 YAML，无需改 Python 或 HTML
- `protected: true` 替代 `BUILTIN_AGENTS` 集合控制删除保护
- `ConfigLoader` 新增 `load_provider_presets()` 和 `load_fallback_models()` 方法

> **2026-05-22 后续变更**：`fallback_models.yaml` 已删除（静态列表随时会过时，如 DeepSeek 模型更名）；Add 模式模型展示改为调用 `GET /api/config/providers/{slug}/catalog`，实时从 OpenRouter 公开 API 拉取模型属性数据（不含 pricing）。`_fetch_from_openrouter` 和 `_discover_models` 的 `fallback_models` 参数随之移除。

---

## ADR-012 — 删除冗余 Provider 适配器

**日期**：2026-05-22
**状态**：已采纳

### 背景

早期为 DeepSeek、OpenAI、Claude 各写了专用 Adapter（`deepseek.py`、`openai.py`、`claude.py`）。后来引入 `ChatCompletionsAdapter` 作为通用 OpenAI 兼容适配器，ADAPTER_MAP 的所有 Provider 均指向它。三个专用文件由此成为死代码，既不被 ADAPTER_MAP 使用，也不被任何测试直接引用。

### 候选方案
| 方案 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| 删除全部三个 | 保持代码库干净 | 无死代码 | 若日后需 native Anthropic API 需重建 |
| 保留 claude.py，删其余两个 | ClaudeAdapter 使用 `/messages` endpoint | 保留差异实现 | 构造函数签名不兼容 registry.create()，仍是死代码 |
| 保持现状 | 不动 | 零风险 | 误导性：读者不知道该用哪个 |

### 决策

删除全部三个文件。Anthropic 已支持 OpenAI 兼容 endpoint（`/v1/chat/completions`），`ChatCompletionsAdapter` 覆盖所有场景。`__init__.py` 改为只导出 `BaseAgent`、`ChatCompletionsAdapter`、`AgentRegistry`。

### 后续影响
- 若将来需要 native Anthropic `/messages` 端点（流式、工具调用等），可新建 `AnthropicAdapter` 并更新 ADAPTER_MAP
- 测试 `test_all_providers_use_chat_completions` 保持不变（已通过）

---

## ADR-013 — 凭据存储键重设计：provider_slug → 实例名

**日期**：2026-05-22
**状态**：已采纳
**决策人**：项目负责人

### 背景

早期 `CredentialManager` 以 `provider_slug`（如 `"deepseek"`）为键存储 api_key、model_list、default_model。同一 Provider 下多个实例（DS1、DS2）无法各自保存凭据，且前端 `agentConfig`（以实例名为键）与 `agentCredentials`（以 provider_slug 为键）索引不一致，导致 Edit 模式 API key / 默认模型无法正确回填。

### 候选方案

| 方案 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| 实例名作为凭据键 | 完全以实例名存储，实例间数据隔离 | 一致性强，支持多实例 | 需全量迁移现有存储 |
| provider_slug 保留，前端适配 | 继续用 provider_slug，前端通过 `a.provider` 转换 | 改动少 | 多实例无法独立凭据，逻辑复杂 |

### 决策

凭据改为以**实例名**为键存储。`CredentialManager._state["credentials"]` 和 `_state["model_lists"]` 均按实例名组织，实例间数据完全隔离。

### 后续影响
- 同一 Provider 可创建多个实例（DS1、DS2），各自拥有独立 api_key、model_list、default_model
- `routes.py` 的 set-key / test / sync-models / default-model 均以实例名查凭据
- 前端 `agentCredentials` 所有查找改为实例名索引，移除所有 `a.provider` 转换路径
- 删除实例时直接 `cred_mgr.delete(name)`，无需检查 provider 引用计数
- `session/manager.py` 的 `_get_api_key/base_url/model` 调用均以 `agent_name`（实例名）为键
- 详细约定见 `dev/rules/config.md`

---

## ADR-014 — 凭据存储路径迁移：data_dir → config_dir

**日期**：2026-05-24
**状态**：已采纳
**决策人**：项目负责人

### 背景

`CredentialManager` 原先接受 `data_dir` 参数，将加密凭据文件存放在 `{data_dir}/settings/settings.json.enc`。由于 `data_dir` 同时也是 Session 数据目录（`SessionManager`、`Archiver` 使用同一路径），当用户清理 Session 数据时（如 `rm -rf /tmp/blackboard-sessions`）会连带删除 API Key，导致所有 Agent 重新变为 `not_configured` 状态。

### 候选方案

| 方案 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| 迁移到 config_dir | `credentials.enc` 存至 `config/agents/`，与 `registry.yaml` 同级 | 语义清晰、生命周期一致、不受 session 清理影响 | 需改构造函数签名及所有调用方 |
| 保持 data_dir，加保护标记 | 清理脚本跳过 `settings/` 子目录 | 改动少 | 隐式约定，运维容易踩坑 |
| 独立环境变量指定路径 | 新增 `CREDENTIALS_DIR` 环境变量 | 灵活 | 增加配置项，部署复杂度上升 |

### 决策

将 `CredentialManager` 的构造参数从 `data_dir` 改为 `config_dir`，凭据文件存至 `config/agents/credentials.enc`。

**理由**：凭据（API Key + 模型列表）在语义上是配置数据而非运行时数据，与 `registry.yaml` 属同一生命周期（持久，跟随部署），放在 `config/` 下最为自然。Session 清理操作只删除 `data/sessions/`，不触碰 `config/`，从根本上消除误删风险。

### 后续影响

- `CredentialManager.__init__(config_dir: str)` → 文件路径：`{config_dir}/agents/credentials.enc`
- `main.py` 传入 `CONFIG_DIR`（项目根目录下的 `config/`），不再传 `data_dir_path`
- `data/sessions/` 只包含纯 Session 运行时数据，可安全清理
- 测试中 `CredentialManager(temp_dir)` 改为 `CredentialManager(config_dir=temp_dir)`

---

## ADR-015 — Session 文件分类：业务数据 vs 运营日志

**日期**：2026-05-24
**状态**：已采纳
**决策人**：项目负责人

### 背景

Session 目录内的文件混杂了两种性质不同的数据：记录"session 发生了什么"的业务数据，以及记录"系统运行状况"的运营日志。两者混在同一层目录，归档策略难以区分，语义也不清晰。

### 决策

将 Session 目录内文件明确分为两类，运营日志统一移入 `logs/` 子目录：

**业务数据**（session 内容本身，归档时保留）：
`config.json` / `strategy.psc` / `conversation.log` / `events.jsonl` / `messages.jsonl` / `agents/{name}/soul.md` / `agents/{name}/memory.md`

**运营日志**（监控 / debug 用途，归档时可丢弃）：
`logs/agent_calls.jsonl` / `logs/tool_calls.jsonl` / `logs/warnings.jsonl` / `logs/errors.jsonl`

### 后续影响

- `SessionLogger` 中运营日志路径统一改为 `{session_dir}/logs/` 前缀
- 归档流程可配置"仅归档业务数据"选项
- `events.jsonl` 和 `messages.jsonl` 明确为业务数据，不纳入运营统计

---

## ADR-016 — Soul / Identity 归属 Session 而非 Agent Instance

**日期**：2026-05-24
**状态**：已采纳
**决策人**：项目负责人

### 背景

早期实现将 `system_prompt`（soul）作为字段存入 `registry.yaml` 的 `AgentEntry`，后改为在 session 创建请求中传入并存入 `config.json`。两种方式都不够清晰：前者将角色绑定到 instance，后者将 soul 混入技术配置。

### 决策

Soul / Identity 归属 Session，以独立文件 `agents/{agent_name}/soul.md` 存储：

- `registry.yaml`（AgentEntry）= 纯技术配置（provider、base_url、model），不含 `system_prompt`
- `config.json` = session 参数（agent 名单、权限），不含 soul
- `agents/{name}/soul.md` = 该 agent 在本 session 的角色定义与行为约束

**类比**：instance 是演员（技术规格），session 是剧本（角色分工）。同一个 instance 在不同 session 里可扮演完全不同的角色。

**归属层级澄清**：soul 是 per-agent 的，每个 agent 各自拥有独立的 `soul.md`，物理路径在 `agents/{name}/` 子目录下，而非 session 根目录。一个 session 内有多少个 agent，就有多少个独立的 `soul.md`，互不干扰。`GET /sessions/{id}` 响应中 `system_prompt` 字段也是嵌套在各自 agent 条目内，不是 session 顶层字段。

### 后续影响

- `AgentEntry` 移除 `system_prompt` 字段
- `config.json` agent 列表移除 `system_prompt` 字段
- Session 创建时，soul 内容写入 `agents/{name}/soul.md`
- `execute()` 调用前读取 `soul.md` 作为 system_prompt 注入
- 常用角色可提取为 `config/soul_templates/` 模板，创建 session 时选用复制

---

## ADR-017 — Agent 全局身份定义：openclaw 式文件结构

**日期**：2026-05-25
**状态**：已采纳
**决策人**：项目负责人

### 背景

每个注册 Agent 除了技术配置（`registry.yaml`）之外，需要一种标准方式定义其默认身份、行为边界和长期记忆。Openclaw 使用 `SOUL.md + IDENTITY.md + MEMORY.md` 三文件结构管理 Agent 身份，经验证简洁有效。

### 决策

Soul 模板放在 `config/agent_templates/`，按角色命名（与 agent 实例名无关），与注册表物理分离：

- `config/agents/` = 纯技术注册（registry.yaml + credentials.enc），不含行为定义
- `config/agent_templates/{role}.md` = 通用角色模板，可被多个 agent 实例复用
- `AgentEntry.default_template` = 指向模板文件名（不含 `.md`），soul resolution 第 3 层回退依此查找

**放弃 IDENTITY.md：** Soul 和 Identity 是同一事物的两个切面，合并进 SOUL.md header 即可（第一行 `# Name Emoji`，第二行 `**类型：**`）。

**Memory 只存在于 session 内：** Agent instance 随 session 生灭，无跨 session 持久化。`sessions/{id}/agents/{name}/memory.md` 随 session 结束而归档或删除。

**Soul Resolution 三层优先级（已实现）：**

| 优先级 | 来源 | 位置 |
|--------|------|------|
| 1（最高）| 创建 session / add_agent 时传入的 `system_prompt` | 写入 `sessions/{id}/agents/{name}/soul.md` |
| 2 | Session 已有的 `soul.md`（上次写入或恢复） | `sessions/{id}/agents/{name}/soul.md` |
| 3（兜底）| 通用角色模板，由 `registry.yaml` 的 `default_template` 字段指向 | `config/agent_templates/{template}.md` |

Session 级 soul 覆盖模板 soul，模板是兜底默认值。Session soul 一旦写入就与模板完全隔离，后续对模板的修改不会影响已有 session。

**soul 的两个层面均放在同一文件内**，用不同 `##` 段落区分：
- `## 核心行为`：操作层面的行为规则（行为控制）
- `## 风格`：语言、语气、格式偏好（性格控制）

无需单独的系统级 prompt 机制，每个 agent 的 soul 文件已足够表达所有行为约束。

### 与 ADR-016 的关系

ADR-016 确定"soul 归属 session"，ADR-017 在此基础上补充"每个 agent 有通用角色模板作为初始默认值"。两者不矛盾：模板是工厂默认值，session 可在此基础上覆盖或定制。

### 后续影响

- `config/agent_templates/` 已建立（`host.md`、`philosopher.md`、`config_assistant.md`、`general.md`）
- `AgentEntry.default_template` 字段已添加，`registry.yaml` 各 agent 已配置对应模板
- `session/manager.py` `create()` 和 `add_agent()` 已实现三层 soul resolution
- `PATCH /sessions/{id}/agents/{name}` 已实现 soul 持久化（写 `soul.md` + 更新内存，立即生效）
- Web UI 已提供专用 Soul 编辑卡（config 卡 + soul 卡分离，含字数统计）
- 待实现：`memory.md` 的写入机制（独立 session 讨论）

---

## ADR-018 — Memory 架构重设计：三层模型

**日期**：2026-05-26
**状态**：已采纳
**决策人**：项目负责人
**取代**：ADR-009

### 背景
ADR-009 的 `session_mem.md + agent_mem.md` 方案缺乏层级设计：所有 memory 混在 per-session 层，没有 cross-session 持久化，也没有定义写入规则和冲突解决机制。随着需求明确，需要一个更清晰的分层模型。

### 核心决策

**三层结构：**

| 层级 | 生命周期 | 归属 | 存储位置 |
|------|---------|------|---------|
| Per-call context | 单次调用，调用后丢弃 | 无归属，Host 组装 | 不持久化 |
| Per-session working memory | Session 生命周期 | Session（共享） | `data/sessions/{id}/dialog.jsonl` |
| Per-session episodic thread | Session 生命周期 | Agent instance | `data/sessions/{id}/agents/{name}/episodic.md` |
| Cross-session Workspace LTM | 永久 | Workspace | `config/workspace_ltm.md` |
| Cross-session Agent role LTM | 永久 | Agent role | `config/agents/{name}/ltm.md` |

**关键原则：**
- Dialog（对话记录）与 Log（运营日志）严格分离，不混用"log"指代对话内容
- Agent Instance 生命周期 = Session 生命周期；Agent Role LTM 跨 session 持久
- Memory 归属 Agent Role，Session 只产出 dialog
- Participant（非 Host 的 Agent）只管理自己的 episodic memory；Host 负责 session-level 的 memory 组装和 LTM 提炼

**LTM 写入路径（仅两条）：**
1. Session 结束时，Host 从 dialog + episodic thread 提炼，写入各 Agent role LTM 及 Workspace LTM
2. 用户显式说"记住 X"，Host 判断层级后直接写入

**运行时优先级（高 → 低）：**
per-call > per-session working memory > Agent role LTM > Workspace LTM

**Per-session 覆写规则：**
- 有作用域限定词（这个/这次/临时）→ per-call，不进 session memory
- 无限定词 → 默认 per-session
- 冲突且无明确信号 → Host 主动问用户

### 后续影响
- `conversation.log` 迁移为 `dialog.jsonl`（结构化对话记录）
- `agents/{name}/memory.md` 迁移为 `agents/{name}/episodic.md`
- 新增 `config/workspace_ltm.md` 和 `config/agents/{name}/ltm.md`
- Host 新增 memory 层级判断、context 组装、LTM 提炼三项职责
- `BaseAgent.load_memory()` / `save_memory()` 接口保留，加载目标路径调整

---

## ADR-019 — Host 作为消息唯一入口

**日期**：2026-05-26
**状态**：已采纳
**决策人**：项目负责人

### 背景
用户可以通过 @mention 直接指定 Participant Agent（如 `@coder 帮我写个函数`）。原有实现中，Host 解析 @mention 后直接路由调用，但缺少 memory 层级判断和 context 组装步骤，导致 Participant 收到的 context 不完整。

### 决策
所有用户消息（无论是否带 @mention）必须先进入 inbox，由 **Host 作为唯一处理入口**：

```
用户输入（含 @mention）
    → inbox Stream
    → Host
        ├── 解析路由意图（@谁 / 默认 / 多 Agent）
        ├── 判断 memory 覆写层级
        ├── 更新 session working memory（如需要）
        ├── 从各层 memory 组装 context
        └── 发起对 Participant 的调用
            → Participant 执行（只接收组装好的 context）
```

**@mention 是给 Host 的路由提示，不是给 Participant 的直连请求。**  
Participant 是无状态的执行单元，不参与 memory 层级判断，只负责执行任务。

### 候选方案对比
| 方案 | 优点 | 缺点 |
|------|------|------|
| Host 唯一入口（本方案） | memory 判断集中、context 一致、Participant 保持无状态 | Host 是单点，需保证性能 |
| @mention 直连 Participant | 延迟略低 | Participant 需自己管理 memory，破坏无状态性 |

### 后续影响
- `host.py` 的 `_parse_mention` 和 `_direct_chat` 需补充 memory 层级判断逻辑
- Participant 的 `execute()` 接口不变，仍只接收 `Task`（含 context）
- Host 成为 session 内所有 memory 状态的单一管理者

---

## ADR-XXX — 决策标题

**日期**：YYYY-MM-DD
**状态**：草稿 / 已采纳 / 已废弃
**决策人**：

### 背景

### 候选方案
| 方案 | 描述 | 优点 | 缺点 |
...

### 决策

### 后续影响
-->
