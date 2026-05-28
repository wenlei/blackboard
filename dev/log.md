# 变更日志

## 2026-05-27 — Memory 热/暖/冷分层细化 + Budget 定义 + models.dev 迁移

### 完成

**Memory 分层机制细化（讨论与文档）：**
- 明确冷层本质：`dialog.jsonl` 是主存储（每条 turn 实时 append），热层是冷层末尾的滑动窗口视图，暖层是离开热层窗口的历史的摘要；三层不是独立存储，都派生自冷层
- 热层 K 不是固定值：按 token budget 从最新 turn 向前填充，budget 耗尽或达 MAX_HOT_TURNS(=50) 停止；`dialog.jsonl` 每条写入时附 `tokens` 估算字段
- 压缩触发时机：每条新 turn 放入前检查空间，不足时逐轮弹出最旧 turn + 更新暖层摘要，循环直到装得下；暖层自身超 budget（约可用输入 10%）时对摘要再次压缩
- 澄清 `max_output_tokens` 与 `per_call_max_tokens` 的区别：前者是模型硬上限（来自 models.dev），后者是每次调用的实际预留值（Host 按任务类型设定，默认 2048）；budget 计算扣除的是后者
- Budget 完整公式：`热层 budget = context_window - per_call_max_tokens - soul - ltm - warm - task - safety_margin(200)`
- 冷层生命周期：本地与 session 同生灭；LTM 提炼是门控条件（提炼完成后方可 archive + 删除本地冷层）；archive.tar.gz 在远端永久保留冷层原文；异常中断时冷层保留等待恢复
- context_ratio（tokens_used / context_window）作为一等监控指标写入每轮 meta；>0.8 WARNING / >0.95 ERROR

**代码变更（`routes.py`、`credentials.py`）：**
- `credentials.py`：`ModelInfo` 新增 `max_output_tokens: int | None = None`
- `routes.py`：移除 `OPENROUTER_MODELS_URL`，将 `_enrich_from_openrouter()`（HTTP 请求）替换为同步 `_enrich_from_models_dev()`（读本地 catalog）；字段映射：`limit.context` → `context_window`，`limit.output` → `max_output_tokens`，`capabilities.tool_call` → `supports_tools`，`modalities.input` 含 `image` → `supports_vision`；移除 `if provider_id != "openrouter":` 特殊分支，所有 provider 统一走 models.dev 富化

**文档更新：**
- `architecture.md`：Memory 章节新增"Episodic Memory 热/暖/冷分层"表格（含本质列）、"Budget 定义"公式、"压缩触发机制"流程、"冷层生命周期"状态表、"Context 使用量 Logging" meta 规范
- `todo.md`：M1 dialog.jsonl schema 补充 `tokens` 字段；M3 细化 budget 公式 + 压缩循环逻辑 + per_call_max_tokens 说明；M4 新增 LTM 提炼门控条件
- `terms.md`：新增 热层 / 暖层 / 冷层 / context_window / max_output_tokens / per_call_max_tokens / context_ratio；更新 Archive 定义（补充冷层生命周期和门控条件）

---

## 2026-05-26 — Memory 架构设计 + Soul 编辑卡 + 链路验证

### 完成

**Soul 编辑卡（`session_chat.html`）：**
- 旧：单一内联表单（provider / model / role / soul 四项混在一起，textarea 5行）
- 新：两张独立卡片
  - **⚙️ Config 卡**：provider / model / role，行内 label + field 布局，独立 Save 按钮
  - **🧠 Soul 卡**：专用大号 textarea（min 180px，可拖拽扩展），header 显示实时字数统计，独立 💾 Save Soul 按钮
- `updateEditModel()` 修复：改为从 `#agent-edit-area` 根节点查 `.agent-edit-model`（原来从 `sel.parentElement` 查，在新布局中找不到）

**PATCH 保存链路验证（`api/routes.py`）：**
- 确认 `PATCH /sessions/{id}/agents/{name}` 已正确实现：
  1. `live_agent.system_prompt` 立即更新（下次 `execute()` 即生效）
  2. 写入 `sessions/{id}/agents/{name}/soul.md`（重启后 restore 时读回）
  3. soul 清空时删除 `soul.md`（不留残留）
  4. config 模板（`config/agent_templates/`）完全不涉及
- 链路完整，无需修复。

**架构澄清：**
- Session soul 与 config 模板完全隔离：模板只在 session 创建时作为兜底读取一次，之后 session 拥有独立的 `soul.md`，模板变化不影响已有 session
- "行为控制"与"性格控制"均放在 soul.md 内，用不同 `##` 段落区分，无需单独的系统级 prompt 机制

**文档更新：**
- `decisions.md` ADR-017：修正 tier-3 路径（`config/agents/{name}/SOUL.md` → `config/agent_templates/{template}.md`）；补充 soul 两个层面的说明；更新"后续影响"反映已完成状态

**Memory 架构设计（讨论与文档）：**
- 确立三层 Memory 模型：per-call（ephemeral）/ per-session（working memory + episodic）/ cross-session（Workspace LTM + Agent role LTM）
- 核心原则：Memory 归属 Agent Role，Session 只产出 Dialog；Agent Instance 生命周期 = Session 生命周期
- 引入 Dialog 术语（对话记录），与系统运营 Log 严格区分
- 引入 Participant 术语（非 Host 的 Agent）
- LTM 写入仅两条路径：session 结束时提炼 + 用户显式"记住"
- 运行时优先级：per-call > per-session > Agent role LTM > Workspace LTM；覆写默认临时不写回
- 确立 Host 为消息唯一入口（ADR-019）：@mention 是给 Host 的路由提示，不是 Participant 直连
- Host 新增三项 memory 职责：层级判断、context 组装、session 结束时 LTM 提炼
- 更新 `architecture.md`：Memory 架构章节重写，文件布局更新（dialog.jsonl / episodic.md / workspace_ltm.md / ltm.md）
- 更新 `decisions.md`：ADR-009 标记为已取代，新增 ADR-018（Memory 三层模型）、ADR-019（Host 唯一入口）
- 更新 `terms.md`：新增 Participant / Dialog / Working Memory / Episodic Memory / Workspace LTM / Agent role LTM；标记 agent_mem / session_mem 为已取代

---

## 2026-05-25 — Soul 模板：通用角色模板 + registry default_template

### 完成

**架构决策：模板按角色命名，不按 agent 实例名**
- `config/agent_templates/` 存放通用角色模板（`host.md`、`philosopher.md`、`config_assistant.md`、`general.md`）
- 模板与 agent 实例解耦：多个 agent 可共用同一模板
- `AgentEntry` 新增 `default_template: str = ""` 字段，指向模板文件名（不含 `.md`）
- `registry.yaml` 各 agent 配置对应模板：`myhost→host`、`Philospher→philosopher`、`config_agent→config_assistant`、`deepseek/xiaomi-bot→general`

**Soul resolution 第 3 层更新（`session/manager.py`）：**
- 旧：`config/agent_templates/{agent_name}/SOUL.md`（按实例名查，错误）
- 新：`registry.yaml[agent_name].default_template` → `config/agent_templates/{template}.md`

**测试：** 248 passed，0 新增失败

---

## 2026-05-25 — Agent 模板结构最终确定

### 完成

**架构澄清（两个错误纠正）：**
- `config/agents/{name}/` 子目录不应存在 —— `config/agents/` 职责是纯技术注册，不含行为定义
- `data/agents/{name}/memory.md` 不应存在 —— agent instance 随 session 生灭，无跨 session 持久化

**最终结构：**
- `config/agents/` → 只有 `registry.yaml` + `credentials.enc`
- `config/agent_templates/{name}/SOUL.md` → agent 默认身份模板（soul resolution 第 3 层回退）
- `sessions/{id}/agents/{name}/soul.md` → session 级 soul（随 session 走）
- `sessions/{id}/agents/{name}/memory.md` → session 级记忆积累（随 session 生灭）

**文件迁移：**
- `config/agents/{name}/SOUL.md` × 5 → `config/agent_templates/{name}/SOUL.md`
- `config/agents/{name}/MEMORY.md` 删除（无跨 session 持久化需求）
- `config/agents/{name}/IDENTITY.md` 已在上一步合并进 SOUL.md 删除

**代码更新（`session/manager.py`）：**
- tier-3 路径 `config/agents/{name}/SOUL.md` → `config/agent_templates/{name}/SOUL.md`

**文档更新：** `architecture.md`、`decisions.md` ADR-017、`log.md`

**测试：** 248 passed，0 新增失败

---

## 2026-05-25 — Agent 全局身份：openclaw 式三文件结构

### 完成

**为每个注册 Agent 建立全局身份目录（`config/agents/{name}/`）：**

| Agent | SOUL.md | IDENTITY.md | MEMORY.md |
|-------|---------|-------------|-----------|
| `config_agent` | 系统配置助手，分步引导，精准 | ConfigAssist ⚙️ | 空（待积累） |
| `myhost` | Session 主持人，中立协调，推进导向 | Host 🎙️ | 空 |
| `Philospher` | 思想探索者，追问根源，多角度 | Philosopher 🦉 | 空 |
| `deepseek` | 通用 AI 助手，务实灵活 | DeepSeek 🔍 | 空 |
| `xiaomi-bot` | 小米生态专家，具体到型号版本 | XiaomiBot 🟠 | 空 |

**Soul Resolution 三层回退（`session/manager.py` `create()` + `add_agent()`）：**
1. 创建 session 时传入的 `system_prompt` → 写入 session 的 `soul.md`
2. Session 已有的 `sessions/{id}/agents/{name}/soul.md`
3. 全局 `config/agents/{name}/SOUL.md`（新增兜底层）

**文档更新（3 处）：**
- `architecture.md`：Config 目录结构新增 `agents/{name}/` 子目录说明；文件说明表补全三个文件
- `decisions.md`：新增 ADR-017（Agent 全局身份 + soul resolution 三层优先级）
- `dev/log.md`：本条记录

**测试：** 248 passed，0 新增失败

---

## 2026-05-25 — ADR-013 完整落地：凭据严格按实例名存储，无 provider 共享

### 完成

**根因分析：**
- `set-key` 端点在保存实例名凭据后，还额外写入 provider slug 作为"共享别名"（违反 ADR-013）
- `_get_api_key` / `_get_base_url` / `_get_model` 三个 resolution 方法都有 provider 级回退逻辑（违反 ADR-013）
- 这意味着同一 provider 下的第一个实例保存 key 后，后续实例无需配置也能用——与"实例间数据完全独立"的决策相悖

**修复（2 个文件，4 处）：**
- `routes.py` `config_set_key`：删除 provider alias 写入（`save_api_key(provider, ...)` 那段代码）
- `session/manager.py` `_get_api_key`：移除 provider fallback，只查实例名；无 key → `MissingApiKeyError`
- `session/manager.py` `_get_base_url`：移除 provider 参数和 provider-level override 回退
- `session/manager.py` `_get_model`：移除 provider 参数和 provider-level default_model 回退

**文档同步（1 处）：**
- `architecture.md` 错误表：`MissingApiKeyError` 状态码 500 → 422，描述"环境变量未设置" → "API Key 未配置"

**测试：** 403 passed，11 skipped，无新增失败

---

## 2026-05-25 — 文档澄清：Soul 归属 per-agent，非 session 根目录

### 完成

**概念确认（无代码改动，代码已正确）：**

- 一个 session 内有多个 agent，每个 agent 各自拥有独立的 `soul.md`
- 物理路径：`sessions/{id}/agents/{name}/soul.md` —— 在 `agents/{name}/` 子目录下，**不在 session 根目录**
- `GET /sessions/{id}` 响应中 `system_prompt` 嵌套在各自 agent 条目内，不是 session 顶层字段
- `config.json` 无 `system_prompt`；`agent_configs` 内存列表无 `system_prompt`

**文档更新（3 处）：**
- `architecture.md`：`agents/` 区块注释改为"per-agent，各自独立"；移除 `soul.md` 的"待实现"标记（已实现）；文件分类表补充 per-agent 说明
- `decisions.md` ADR-016：新增"归属层级澄清"段落，明确 soul 是 per-agent、存于 `agents/{name}/` 子目录、API 响应也是 per-agent 嵌套
- `dev/log.md`：本条记录

---

## 2026-05-24 — 架构修复：凭据存储与 Session 数据分离

### 完成

**根因分析：**
- `CredentialManager` 原先接受 `data_dir` 参数，将 `credentials.enc` 存于 `{data_dir}/settings/`
- `SessionManager`、`Archiver` 使用同一 `data_dir`（`/tmp/blackboard-sessions`）
- 清理 Session 数据时连带删除 API Key，所有 Agent 变为 `not_configured`

**修复（3 个文件）：**
- `credentials.py`：构造参数 `data_dir` → `config_dir`；文件路径 `{data_dir}/settings/settings.json.enc` → `{config_dir}/agents/credentials.enc`
- `main.py`：`CredentialManager(data_dir=data_dir_path)` → `CredentialManager(config_dir=CONFIG_DIR)`
- `test_credentials.py`：所有构造调用同步改为 `CredentialManager(config_dir=temp_dir)`

**文档同步（4 个文件）：**
- `architecture.md`：Config 目录结构更新（添加 `credentials.enc`、移除已删除的 `provider_presets.yaml`）；Session 文件夹补全所有实际存在的文件；新增数据分层说明；部署图路径修正
- `decisions.md`：新增 ADR-014（凭据存储路径迁移决策记录）
- `rules/config.md`：新增第 0 节，明确凭据文件物理位置
- `dev/log.md`：本条记录

**测试：** 11 passed（test_credentials），全量 248 passed，0 新增失败

### 数据分层原则（新约定）

| 目录 | 内容 | 生命周期 |
|------|------|---------|
| `config/` | 系统配置、Agent 注册表、**API Key（credentials.enc）** | 持久，跟随部署 |
| `data/sessions/` | Session 运行时数据（对话记录、策略、日志） | 可清理 |
| `data/archives/` | 归档数据 | 长期保留 |

---

## 2026-05-24 — 架构实现：Soul / 运营日志分层

### 完成

**运营日志移入 `logs/` 子目录（`session_logger.py`）：**
- `agent_calls.jsonl`、`tool_calls.jsonl`、`warnings.jsonl`、`errors.jsonl` 路径统一改为 `{session_dir}/logs/`
- `ensure_dir()` 同步创建 `logs/` 子目录
- 业务数据（`conversation.log`、`events.jsonl`、`messages.jsonl`）保持在 session 根目录

**Soul 归 Session（`session/manager.py` + `api/routes.py`）：**
- `create()`：session 目录提前创建（agent loop 前），每个 agent 的 soul 写入 `agents/{name}/soul.md`；`config.json` 移除 `system_prompt` 字段
- `add_agent()`：soul 写入 `agents/{name}/soul.md`；agent_configs 移除 `system_prompt`
- `restore_sessions()`：从 `soul.md` 读取 soul，无需 config.json 存储
- `routes.py update_session_agent`：`system_prompt` 更新改为写 `soul.md`（原来写 config.json）；soul 清空时删除文件
- `routes.py GET /sessions/{id}`：新增 soul 回填 —— 遍历 `agent_configs` 时读取 `soul.md` 并注入 `entry["system_prompt"]`；若无文件则 fallback 读取 live agent 内存中的 `system_prompt`；确保前端 💬 标志和 Soul 编辑弹窗预填正常显示

**测试：** 248 passed，0 新增失败

### Session 最终目录结构

```
data/sessions/{id}/
├── config.json              # 业务：session 参数（id、name、permissions、agent 名单）
├── strategy.psc / .json     # 业务：协作策略
├── conversation.log         # 业务：对话全文
├── events.jsonl             # 业务：lifecycle 事件
├── messages.jsonl           # 业务：MQ 消息流水（待实现）
├── agents/
│   └── {agent_name}/
│       ├── soul.md          # 业务：角色定义（已实现读写）
│       └── memory.md        # 业务：工作记忆（待实现）
└── logs/
    ├── agent_calls.jsonl    # 运营：调用性能指标
    ├── tool_calls.jsonl     # 运营：工具调用记录
    ├── warnings.jsonl       # 运营：告警
    └── errors.jsonl         # 运营：错误
```

### Session 文件中 `system_prompt` 存储路径变更对比

| 版本 | 写入点 | 读取点 |
|------|--------|--------|
| 旧版 | `agent_configs` 列表 → `config.json` | GET session 直接从 `ses["agent_configs"]` 返回 |
| 新版 | `agents/{name}/soul.md`（文件） | GET session 读取 `soul.md` 注入 `entry["system_prompt"]` |

### 待跟进

- 🟠 实现 `memory.md` 读写：`load_memory()` / `save_memory()` 接入 Host 执行链路
- 🟡 实现 `messages.jsonl` 写入：在 MQ 层或 Host 层调用 `log_message()`

---

## 2026-05-24 — 架构讨论：Soul / Memory / Session 文件结构设计

### 讨论结论

**Soul / Identity 归属：Session，不是 Agent Instance**

- Agent Instance（`registry.yaml`）= 演员：纯技术配置（provider、base_url、model、API Key）
- Session = 剧本：决定演员在这场戏里扮演谁、有什么约束
- 同一个 instance 在不同 session 里可担任完全不同的角色，role 定义属于 session，不属于 instance
- `system_prompt` 字段从 `registry.yaml` 的 `AgentEntry` 移除，改为 session 内每个 agent 的独立文件

**Instance 数量原则**

- Instance 的本质是"技术端点"（provider + API Key + default model）
- 不同 model 档位（如 deepseek-chat vs deepseek-v3）是不同 instance 的正当理由
- 同一技术规格下不应为角色差异创建多个 instance（角色差异在 session 层解决）
- 现有实现：default model 存于 instance，session 创建时可覆盖——此机制已足够，无需改动

**Session 目录结构确认**

```
data/sessions/{id}/
├── config.json              # session 参数：id、name、permissions、agent 名单（纯技术，无 soul）
├── strategy.psc
├── conversation.log
├── messages.jsonl
├── events.jsonl
├── agent_calls.jsonl
├── tool_calls.jsonl
├── warnings.jsonl
├── errors.jsonl
└── agents/
    └── {agent_name}/
        ├── soul.md          # 该 agent 在本 session 的角色定义与约束（待实现）
        └── memory.md        # 工作记忆，session 内积累（待实现）
```

`config.json` 职责：服务重启后恢复 session 的锚点，只存"谁在场"，不存"谁是谁"。

**Soul Template（预留方向）**

常用角色可提取为模板，存于 `config/soul_templates/`，创建 session 时选用并复制到 `agents/{name}/soul.md`，之后可在 session 内独立修改。

### 问题/发现

**`messages.jsonl` — 死文件**
- `log_message()` 方法存在但全库零调用，文件永远为空
- 注释"MQ 消息备份"是未实现的意图

**`events.jsonl` — 名实不符**
- 只记录 API 层管理操作（session_created / paused / closed / agent_added / agent_removed / archived）
- 对话事件、Agent 执行、MQ 消息均未记录
- 实际有效日志在：`conversation.log`、`agent_calls.jsonl`、`tool_calls.jsonl`

**Session 文件分类原则确认：业务数据 vs 运营日志**

- `events.jsonl`、`messages.jsonl` 定性为**业务数据**（session 内容的一部分）
- `agent_calls.jsonl`、`tool_calls.jsonl`、`warnings.jsonl`、`errors.jsonl` 定性为**运营日志**（监控 / debug 用途）
- 运营日志统一移入 `logs/` 子目录，与业务数据物理隔离
- 归档时可选择只保留业务数据、丢弃 `logs/`

最终 Session 目录结构：

```
data/sessions/{id}/
├── config.json              # 业务：session 参数（重启恢复锚点）
├── strategy.psc / .json     # 业务：协作策略
├── conversation.log         # 业务：对话全文
├── events.jsonl             # 业务：lifecycle 事件
├── messages.jsonl           # 业务：MQ 消息流水（待实现）
├── agents/
│   └── {agent_name}/
│       ├── soul.md          # 业务：角色定义（待实现）
│       └── memory.md        # 业务：工作记忆（待实现）
└── logs/
    ├── agent_calls.jsonl    # 运营：调用性能指标
    ├── tool_calls.jsonl     # 运营：工具调用记录
    ├── warnings.jsonl       # 运营：告警
    └── errors.jsonl         # 运营：错误
```

### 待跟进

- ✅ 实现 `soul.md` 读写（已在"架构实现"条目中完成）
- ✅ `SessionLogger` 重构（运营日志移入 `logs/` 子目录已完成）
- 🟠 实现 `memory.md` 读写：`load_memory()` / `save_memory()` 接入 Host 执行链路
- 🟡 实现 `messages.jsonl` 写入：在 MQ 层或 Host 层调用 `log_message()`
- 🟡 明确 `events.jsonl` 扩展：补充对话事件、Agent 执行事件的写入点

---

## 2026-05-24 — Config 功能完善：Provider Catalog 本地化 + Ask Config Agent 工具调用重写 + UI 修复

### 完成

**Provider Catalog 本地化（替代 models.dev 实时拉取）：**
- 新增 `config/agents/models-dev-api-endpoints-full.json`：134 个 Provider 的完整 endpoint 数据（含 openai、anthropic、alibaba 等原先 models.dev 缺失的补充值），由用户手工整理
- 删除 `_SUPPLEMENTAL_BASE_URLS` 硬编码字典（13 项）和 `_get_models_dev()`（网络请求 + 1h 缓存）
- 新增 `_load_local_catalog()`：同步读取本地 JSON，首次调用后模块级缓存，零网络依赖；返回 `{slug: entry}` 同原接口形状
- `_dev_base_url()` 简化：直接读 `api_endpoint` 字段（JSON 已全覆盖，无需 fallback 链）
- `_build_providers()` / `config_providers()` 改为同步函数（无 await）
- `config_provider_catalog()` 改为同步函数；`_models_dev_to_catalog()` 修复 `tool_call`/`reasoning` 读取路径：顶层字段 → `capabilities` 嵌套
- `source` 字段从 `"models.dev"` 改为 `"local_catalog"`
- 测试：`MOCK_DEV_DATA` 字段从 `api` 改为 `api_endpoint`，`capabilities` 改为嵌套格式；所有 `_get_models_dev` patch 改为 `_load_local_catalog`

**Ask Config Agent — 工具调用重写：**
- 完全重写 `config_ask_config_agent` 端点：多轮循环（最多 6 轮），支持 LLM 通过 `probe_url` tool 发起真实 HTTP 探测再给出结论
- 新增模块级 `_execute_probe_url(url)`：GET `{url}/models`，HTTP 200/401/403/404/405/422 均视为可达；连接错误/超时视为不可达
- 去掉 `max_tokens` 限制（原 800），避免 LLM 解释文字把 token 用完、JSON 写不下
- 新增"JSON-only 追问"：若 LLM 返回纯文字（无 JSON），追加 `"Output ONLY the JSON object"` 消息 + `_json_only=True` 标志，下一轮不带 tools、直接拿 JSON
- Prompt 丰富化：发送 Provider ID / Known endpoint / Endpoint type / API key env var / Official docs / Known models（前 8 个）
- 去掉 `display_name` 字段（冗余，LLM 不需要）
- 返回值：`base_url` 直接取 LLM 结果，不再做 fallback（LLM 已拿到 catalog 值，不会返回空）
- 先决条件错误细化：无 api_key → 422（含可操作说明）；无 base_url → 422；无 default_model → 422；无 cred_mgr → 503

**多处 JSON 解析健壮性：**
- `resp.json()` 包裹 try/except，失败返回 502 "non-JSON body"（附原始响应前 300 字节）
- `_extract_result()`：三层修复（Python literal → trailing comma → truncation repair）+ 正则 fallback `\{.*`（截断兜底）
- `_repair_truncated_json()`：处理未关闭字符串、trailing comma、未关闭 `{`/`[`

**实例名显示修复：**
- Agent 列表：第一列改为显示 `display_name`（大字）+ registry key（小字副标题），原先始终显示 key 导致改名无反馈
- 编辑弹窗：`agent-display` 预填改为 `a.display_name || key`，原先预填 key 导致 display_name 信息丢失

**测试：**
- 新增 `tests/phase3/test_api_config_gaps.py`（39 个）：覆盖 `_dev_base_url`、`_repair_truncated_json`、`TestAskConfigAgent`（工具调用全路径）、`TestExecuteProbeUrl`
- 新增 `tests/phase3/test_api_config_extra.py`（32 个）：覆盖 Providers、ProviderCatalog、TestConnection、Settings、SetKey、Credentials 等端点
- 总测试：**380 passed，11 skipped**

### 问题/发现
- `asyncio.get_event_loop()` 在 Python 3.14 中已废弃，async 测试需改用 `@pytest.mark.asyncio` + `async def`
- LLM 在有 `tools` 时返回 `finish_reason: "tool_calls"`，`content` 为 null；旧代码尝试 `json.loads(null or "")` → `char 0` 空字符串错误，现已通过先判断 tool_calls 路径修复
- DeepSeek 等模型倾向先写解释再写 JSON；去掉 token 上限 + 加 JSON-only 追问后解决

### 待跟进
- 🟡 `_LOCAL_CATALOG_PATH` 用 `parents[3]` 相对路径，若包被安装到非源码目录会失效；后续可改为 `importlib.resources`
- 🟡 template URL（含 `{region}` 等占位符）目前原样返回，前端无提示需用户手动替换

---

## 2026-05-24 — Session Chat UI 优化 + Agent Soul 架构 + 运行时模型/Prompt 热更新

### 完成

**Bug Fix — Agent 无回复（`[empty response]`）：**
- 根因：两个 uvicorn 进程同时运行，旧进程（PID 49330）持有旧代码（无 `reasoning_content` fallback），先消费了 Redis inbox 消息
- 修复 `chat_completions.py`：`content = msg_obj.get("content") or msg_obj.get("reasoning_content") or ""`，兼容 deepseek-v4-pro 推理模型返回 `content: null` 的情况
- 操作：`kill -9` 强制终止旧进程；清理 `/tmp/blackboard-sessions/` 保留唯一 `讨论池` session

**Session Chat UI 优化（4 项）：**
- **侧边栏可拖拽**：`resize-handle`（5px 分隔条，hover 高亮）+ JS 鼠标拖拽逻辑，宽度范围 180–640px，`localStorage` 持久化
- **复制按钮改版**：从气泡旁移至时间戳右侧 `ts-row`；图标换用 Google Material Symbols SVG（`content_copy.svg` / `done.svg`），15px，始终淡显（opacity 0.35），hover 加深；复制成功临时换 done 图标
- **Send/Stop 合并为 Toggle**：单个 `#action-btn`，`send-mode`（主色填充）↔ `stop-mode`（红色描边），由 `showThinking()` / `hideThinking()` 驱动状态切换；`stopAgents()` 调用 `POST /api/sessions/{id}/cancel`，4s fallback 保底重置
- **新增 SVG 图标**：`static/icons/content_copy.svg`、`static/icons/done.svg`（Material Symbols 格式 `viewBox="0 -960 960 960"`）

**Agent Soul 架构（`system_prompt` 全链路）：**
- `ChatCompletionsAdapter`：新增 `system_prompt` 字段；`execute()` 消息顺序重排为 `system_prompt → context → memory → user`；有 `system_prompt` 时省略 `[Role: x]` 前缀
- `AgentRegistry.create()`：透传 `system_prompt` 到 adapter
- `SessionManager.create()` / `add_agent()`：从 agent dict 读取并传播 `system_prompt`；存入 `agent_configs`
- `SessionManager._save_config()`：新增方法，将内存状态回写 `config.json`（增减 agent、更新字段后调用）
- `SessionManager`：`_sessions[id]` 新增 `permissions_snapshot` 字段供 `_save_config` 使用
- `routes.py AddAgentRequest`：新增 `system_prompt: str | None = None`
- `routes.py PATCH agent`：更新 `system_prompt`；**热更新** live agent 实例（`live_agent.system_prompt = ...` 立即生效）；调用 `_save_config` 持久化
- `routes.py GET session`：从 live registry 读取真实 `model`（反映热更新），保证 UI 显示与实际一致

**Agent 编辑卡片修复与增强：**
- **Bug fix**：provider 无 models 列表时，model 字段不再显示 `(auto)` 而改为 `<input type="text">`，并预填当前 model 值（如 `deepseek-v4-pro`）
- `updateEditModel()`：切换 provider 时将 select/input 整体替换（`replaceWith`），而非仅更新 innerHTML
- 新增 **System Prompt 文本域**：`agent-edit-soul` textarea（5 行，可拖拽调整），标注"角色设定 / Soul"
- Agent 列表项：有 system_prompt 时显示 💬 标志
- `saveAgentEdit()`：请求体加入 `system_prompt` 字段

**运行时 model 热更新（已验证）：**
- PATCH agent model → 内存 `agent_configs` + live `agent.model` 同步更新 + config.json 落盘
- GET session 返回值实时反映 live registry 中的 model，下一条消息即用新模型

### 问题/发现
- uvicorn `--reload` 模式下存在两个进程（reloader + worker）；`kill -SIGTERM` 不足以终止，需 `kill -9` 或 `pkill -f` 后确认端口释放
- deepseek-v4-pro 是推理模型，`choices[0].message.content` 为空字符串或 null，实际文本在 `reasoning_content`
- `permissions_snapshot` 仅在本次 `create()` 调用后存在于 session 内存；老 session（通过 `restore_sessions` 加载）依赖从原始 config.json 读取的权限，`_save_config` 需处理此 fallback

### 待跟进
- 🟠 memory 文件读写：`BaseAgent.load_memory()` / `save_memory()` 已有实现但未在 `execute()` 中接入；需明确 mem_path 约定（`{data_dir}/{session_id}/{agent_name}/memory.md`）并在 Host 层传入
- 🟡 system_prompt 预设库：为常见角色（主持人、正方/反方辩手、审阅者等）提供模板，session 创建时可选套用
- 🟡 `restore_sessions` 加载时 `permissions_snapshot` 未填充，若该 session 后续有 agent 更新，`_save_config` 写出的 config.json 权限段为空 `{}`

---

## 2026-05-23 — Config UI 完善：实例/Provider 解耦 + 模型发现 + Dashboard 计数修复

### 完成

**后端（routes.py）：**
- 删除 `provider_presets.yaml` 并移除 `ProviderPresets` 数据类；改以 `_KNOWN_BASE_URLS` 内部字典维护已知 base_url
- `_build_providers()` 重写：只返回 OpenRouter 公开列表 + 硬编码 Ollama，不再依赖静态 YAML
- `POST /api/config/test-connection` 扩展：连接成功后调用 provider 原生 `/models`（或 Ollama `/api/tags`）返回真实模型列表；新增 `_parse_models_response()` 辅助函数统一解析格式
- Config Agent 提示词重写：请求 4 个字段 `base_url / openai_compatible / auth_header / notes`，并在响应中返回；max_tokens 从 150 升至 300
- `config_ask_config_agent`：base_url 提示改用 `_KNOWN_BASE_URLS` 而非 preset 查询

**前端（config.html）：**
- `getAllProviders()`（BUG-004 修复）：遍历 `agentConfig` 时改取 `val.provider`（provider slug）而非 `key`（实例名），彻底消除实例名污染下拉列表的 bug
- Registered Agents 表格改为 5 列（去掉 Sync 按钮列）：实例名 / Provider / Default Model / Status / Actions；状态列用彩色小圆点 badge
- `statusBadge()` + `agentStatus(cred)`：从 credential 推导 ready / key_saved / models_synced / not_configured，颜色：绿 / 黄 / 黄 / 灰
- `selectProvider()`：移除 OpenRouter catalog 拉取逻辑，改为提示用户点击 Test Connection 获取真实模型列表
- Test Connection 成功后调用 `_applyModelList()`：将 provider 返回的真实模型写入 credential 并刷新下拉框
- Edit 模态框：Provider 字段改为下拉框（可编辑），预选当前实例的 provider slug
- `updateConfigAgentSelect()` / `updateAskConfigAgentBtn()`：实时根据已注册 Agent 更新 Config Agent 下拉及按钮可见性
- Ask Config Agent 响应展示：`openai_compatible / auth_header / notes` 一起显示在 modal 消息区
- Legend 重组：3 个分组（状态 / Provider 排序 / Action 按钮），Status 使用小圆点图示，Provider 置顶图标改为 ★

**Dashboard（main.py）：**
- `agent_count` 从 `app.state.agent_registry.list()`（始终为空的内存对象）改为每次请求时调用 `config_loader.load_agent_registry().agents`，获取 registry.yaml 的真实数量

**测试修复：**
- `tests/test_config.py`：删除 4 个检查 provider_presets.yaml 内容的测试；移除 `ProviderPresets` import
- `tests/phase3/conftest.py`：移除 `ProviderPreset` / `ProviderPresets` 导入；移除 `load_provider_presets.return_value` mock
- `tests/phase3/test_api_config.py`：`test_get_providers` 简化为只断言 `ollama` 存在

总测试：**309 passed，11 skipped**

---

## 2026-05-22 — Config 组件重构：OpenRouter Catalog + Config Agent + 系统设置

### 完成

**后端（routes.py + loader.py）：**
- 删除 `_fetch_from_openrouter()` 死代码（无调用方）
- 删除 `HostConfig` 类及 `SystemConfig.host` 字段（dead code，从未读取）
- `SystemConfig` 新增 `config_agent: str = ""` 字段；`ConfigLoader` 新增 `save_system_config()` 方法
- 新增 `GET /api/config/providers/{slug}/catalog`：代理 OpenRouter 公开 API，只返回模型属性数据（model_id / display_name / context_window / model_type / supports_tools），不含 pricing / per_request_limits / OpenRouter 路由配置
- 新增 `GET /api/config/settings`、`PATCH /api/config/settings`：读写 system.yaml 中的 `config_agent`
- 新增 `POST /api/config/providers/{slug}/ask-config`：直接 httpx 调用 Config Agent 的 `/chat/completions`，推断目标 Provider 的 base_url，返回 `{base_url, notes, agent}`

**前端（config.html）：**
- Agents Tab 顶部新增 **System Settings 卡片**：Config Agent 下拉框（从已注册 Agent 中选取，可选）+ Save 按钮
- Add/Edit Agent 模态框新增 **Ask Config Agent** 按钮（有 config_agent 时显示）：调用 ask-config 接口，自动填入 base_url
- 模态框新增 **Discover Local Models** 按钮（选中 ollama 类 Provider 时显示）：直接从浏览器访问 `{base_url}/api/tags`，发现已安装模型
- `selectProvider` 改为 async，选中后自动从 OpenRouter catalog 拉模型；Ollama Provider 跳过 catalog，改走 Discover 流程

**删除：**
- `config/agents/fallback_models.yaml` 删除（静态列表已被 OpenRouter catalog 取代）

**测试修复：**
- `tests/phase1/test_config.py`：3 处 `cfg.host.*` 断言改为 `cfg.config_agent == ""`
- `tests/phase1/conftest.py`：`valid_system_yaml` fixture 删除 `host` 块，加入 `config_agent: ""`
- `tests/phase1/test_config.py`：`TestFallbackModels` 删除 3 个检查文件内容的测试，保留 `test_missing_file_returns_empty`

总测试：**313 passed，11 skipped**

---

## 2026-05-22 — Config UI 修复 + OpenRouter 适配 + 文档整理

### 完成

**Config UI 修复（4 项）：**
- 修复 `config_remove_agent`（`routes.py`）：移除 built-in 保护检查，registry 内所有 Agent 均可删除，不存在时返回 404
- 移除 PIN 标签：`config.html` 删除 pinnedModelIds / modSort / `isPinned()` / `.pin-tag` CSS，API 不再返回 `pinned_model_ids`
- 修复 `config_add_agent`（`routes.py`）：409 → upsert 语义，已存在返回 `"updated"`，新增返回 `"added"`
- Add Agent 模态框：legend 从页面底部移入模态框内

**OpenRouter 适配（1 项）：**
- 修复 `~` 前缀处理：OpenRouter "Latest Alias" 模型（如 `~anthropic/claude-opus-4`）在 provider slug 提取和 display name 两处均 `.lstrip("~")`；stripped slug 与已有预设重复时自动跳过（去重）

**实例名重设计（1 项）：**
- `config.html` Add Agent Name 字段语义改为实例名（Instance Name）：唯一标识键，用户自定义，同一 Provider 可创建多个实例；仅当字段为空时 `selectProvider` 才自动填充 Provider slug 作为默认值；Edit 模式加载实例 key 而非 display_name

**运行时修复（2 项）：**
- 修复 `host/host.py` `run()` 死循环不检查会话状态：添加 `_stop_event` / `_paused` 标志 + `pause()`/`resume()`/`stop()` 方法；SessionManager 在暂停/恢复/关闭时调用对应方法
- 移除 `host/strategy.py` `_host_model` 死代码（读取环境变量后从未使用）

**前端修复（2 项）：**
- 修复 `session_chat.html` Agent 列表 HTML 未转义：新增 `escapeAttr()` 函数用于 onclick 属性中的 name/role/provider/model
- 修复 `session_create.html` `autoSessionId` 结果被丢弃 + 两个 ID 生成函数过滤规则不一致 → 统一调用 `generateSessionId`

**后端异常处理（3 项）：**
- `routes.py` `config_tools()` AttributeError → `logger.warning`；加载失败 → `logger.error`
- `routes.py` SSE 流两处异常 → `logger.debug`
- `config.html` 设置默认模型错误 → `console.error`

**测试（1 项）：**
- `test_api_config.py`：`test_remove_builtin_agent_forbidden`（旧，期望 403）→ `test_remove_registered_agent`（期望 200）；新增 `test_remove_nonexistent_agent_404`
- 累计：316 passed

**文档整理：**
- `architecture.md`：更新日期、模块表（统一适配器）、Mermaid 图（Agent 实例 A/B/C + ChatCompletionsAdapter）、SSE Stream 表（XREAD vs XREADGROUP）、Config 目录结构、REST API 表（补全 8+ 端点）
- `background.md`：填入"成功标准"4 阶段表格
- `decisions.md`：全部 12 条 ADR 的决策人 `[待补充]` → 统一替换为"项目负责人"
- `terms.md`：更新 Agent/Adapter 定义；新增 XREAD、实例名、ChatCompletionsAdapter、Provider Preset 4 个术语
- `todo.md`：标记 ChatCompletionsAdapter / PINNED_MODELS / 文档占位符等已完成项

**全量扫描 — 新发现并修复（10 项）：**
- 修复 `session/manager.py:78,155` 注册表查询用 `provider` 而非实例名（实例名重设计后的回归）
- 修复 `chat_completions.py` `time.sleep()` 在 async 函数中阻塞事件循环 → `await asyncio.sleep()`
- 修复 `host/strategy.py` `available_agents` 迭代写反（`{agent_name: role}` → `{role: agent_name}`）；`_build_general_psc` 改用实例名写入 PSC
- 修复 `sandbox/sandbox.py` 路径穿越检查缺少 `os.sep`（同前 `tools/executor.py` 已修复但未同步）
- 修复 `credentials.py` `get_overall_status()` for 循环内提前 return → 遍历全部取最差状态
- 修复 `main.py:60` print 含 HTML 标签 `</p>`
- 修复 `routes.py:345` `config_add_agent` `default_model="unknown"` → `""`
- 修复 `routes.py:790` `sync-models` base_url fallback 用实例名 → `entry.provider`
- 修复 `config.html` `saveAgent()` 调用顺序：registry 创建先于 `set-key`（导致 "Agent not found" 的根因）
- 累计：316 passed

**全量扫描 — 新发现、待修复（3 项，记入 todo）：**
- **Agent Worker 缺失**：executor 分发任务到 `dispatched` Stream 后无人消费，60s 必然超时
- **`AgentRegistry.get()` 大小写不匹配**：PSC 用 `.upper()` 写实例名，executor 用 `.lower()` 查询，与原始 key（如 "DS1"）不匹配
- **权限 fallback 硬编码 "whitelist"**：`session/manager.py:63` 不管请求的 mode 都加载 whitelist 预设

**Agent 删除清理修复（1 项）：**
- 修复 `config_remove_agent`（`routes.py`）：删除实例时原子清理凭据——先解析 `entry.provider`，再删注册条目，最后检查 `provider` 是否仍被其他实例引用，无引用才调用 `cred_mgr.delete(provider_slug)`；用 `getattr(..., None)` 替代直接访问避免测试环境 AttributeError
- 修复 `deleteAgent`（`config.html`）：去掉错误的单独 `DELETE /api/config/credentials/{key}` 调用（用实例名删凭据永远命中不到任何记录），改为单次 `DELETE /api/config/agents/{key}`，由后端统一处理

**Agent 编辑弹窗修复（4 项）：**
- 修复 `config.html` `openAgentModal` 凭据查找：`agentCredentials[key]`（实例名）→ `agentCredentials[a.provider]`（provider slug），修复 Edit 模式 API key / 默认模型不回填
- 修复 `config.html` `renderModelDropdown` 在 Edit 模式传参：`renderModelDropdown(provider, cred)` → `renderModelDropdown(key, cred)`，修复 agentConfig 实例名查找失败导致 Fallback 模型不显示
- 修复 `config.html` `selectModel` 重渲染用实例 key：`providerKey` → `instanceKey`（editKey || providerKey）
- 修复 `config.html` `testAgentConnection` / `syncAgentModels` 在 Add 模式（editKey 为空）不再调用 `ensureAgentExists`（三重 Agent 创建 bug 的第三源），改为提示"请先保存 Agent"
- 累计：316 passed

**Test Connection 重构 + API Key masked 修复（3 项）：**
- 根因：`list_credentials()` 返回 masked api_key（`sk-1234****5678`），Edit 模式回填后 `saveAgent` 把 masked 字符串存为真实 key → 测试时 401 "API key rejected"
- 修复 `openAgentModal` Edit 模式：API key 字段保持空值，placeholder 显示"API key saved — leave blank to keep"；saveAgent 的 `set-key` 步骤仅在字段非空时执行，空 = 保留现有 key
- 新增 `POST /api/config/test-connection` 端点：body 携带 `{api_key, base_url}`，不查注册表，响应包含实际请求的 `endpoint` 字段
- 重构 `testAgentConnection`：Add 模式或有新 key 时调 `/api/config/test-connection`（用表单值直接测）；Edit 模式且 key 字段为空时调 `/api/config/agents/{name}/test`（用已存 key）；移除"请先保存"限制
- 响应显示实际请求 URL（`→ https://api.deepseek.com/v1/models`），便于排查路径问题
- 累计：316 passed

**Model 加载修复（2 项）：**
- 修复 `autoSyncModels`：sync 结果写入 `agentCredentials[provider]` 内存缓存，防止 `selectModel` 重绘时因 key 不匹配（provider slug vs 实例名）丢失 model 列表，导致选完模型后 dropdown 变空
- 修复 `openAgentModal` Edit 模式：若实例凭据为空（如历史数据迁移前的实例），自动触发 `autoSyncModels(key)` 填充 fallback 模型，避免 dropdown 永远空白
- 累计：316 passed

**Save 集成 Sync（UX 优化）：**
- 移除 Add/Edit 模态框中独立的 "Sync Models" 按钮及 `syncAgentModels()` 函数
- `saveAgent()` 新增步骤 3：注册 + set-key 完成后自动调用 `sync-models`，无需用户手动触发
- 步骤 4 default-model：优先使用用户在下拉框的选择，其次取 sync 结果第一项，实现零配置自动选模型
- 保存成功消息追加同步数量（`Agent "DS1" added，同步 14 个模型`）
- 表格行保留独立 Sync 按钮，供事后手动重同步（如 API 上线新模型时）
- 累计：316 passed

**实例数据独立化（重构）：**
- 凭据存储键从 `provider_slug` 改为**实例名**：`CredentialManager` 的 `credentials` 和 `model_lists` 均以实例名为键，实例间数据完全隔离，同一 provider 的多个实例各自拥有独立 api_key、model_list、default_model
- `routes.py` `set-key`：`save_api_key(entry.provider, ...)` → `save_api_key(name, ...)`
- `routes.py` `test`：凭据查找 `entry.provider` → `name`
- `routes.py` `sync-models`：注册路径凭据查找和持久化 `provider_id` → `name`；bare provider 路径不再尝试查凭据（实例不存在，无可查）
- `routes.py` `default-model`：`get/save_model_list(entry.provider, ...)` → `get/save_model_list(name, ...)`
- `routes.py` `remove_agent`：去掉 provider 引用计数检查，直接 `cred_mgr.delete(name)`
- `session/manager.py`：`create()` 和 `add_agent()` 的 `_get_api_key/base_url/model` 调用从 `provider_cfg.provider` 改为 `agent_name`
- `config.html`：所有 `agentCredentials` 查找统一改为实例名（表格渲染、modal 打开、selectModel、syncAgentModels），去掉所有 `a.provider` 转换路径
- `dev/rules/config.md`：同步更新第 1-4、8-9 节，删除 provider-slug 共享语义描述
- 累计：316 passed

**文档结构（1 项）：**
- 新建 `dev/rules/` 目录（功能块专项规则）：`README.md`（索引）+ `config.md`（Config 模块 9 条约定）
- 更新 `instruction.md`：文档地图新增 `dev/rules/` 行，使用原则补充"修改模块前读对应规则文件"
- 更新 `dev/rule.md`：顶部添加 rules 子目录入口说明
- 更新 `AGENTS.md`：`/sync-docs` 文件检查列表加入 `rules/README.md`

**无全局 API Key + 静态 Fallback 模型（重构）：**
- 根因：`selectProvider` 在选择 Provider 时会读取已存凭据（旧 provider-slug 键）并回填 API key 字段，造成"全局 key"假象；Add 模式还通过 OpenRouter 拉取模型列表，但 OpenRouter 返回其平台自有 ID（如 `deepseek/deepseek-chat`），无法直接用于 Provider 原生端点
- 修复 `selectProvider`：API key 字段始终清空，placeholder 恢复默认 `sk-...`；不再读取任何已存凭据
- 修复 Add 模式模型展示：`_build_providers`（`routes.py`）在 Provider 预设响应中附带 `fallback_models` 数组（来自 `fallback_models.yaml`），前端 `selectProvider` 直接使用静态列表展示，无网络调用
- 修复 Edit 模式空模型问题：`openAgentModal` 若实例凭据无模型列表，改为读取 `providerPresets[provider].fallback_models` 展示静态 fallback，不再调用 `autoSyncModels`
- 删除 `autoSyncModels()` 函数：Add 模式模型展示已改为静态 fallback，函数无存在意义；Save 内嵌 sync（步骤 3）已覆盖真实同步需求
- 更新 `dev/rules/config.md` 第 6 节：Add 模式弹窗无 autoSyncModels，模型来自静态 fallback
- 累计：316 passed

### 问题/发现
- OpenRouter `~` 前缀表示 "Latest Alias Router Model"（动态指向最新模型），tokenizer=Router，与具体模型区别仅在于 slug 前缀；实际 API 调用无差异，客户端侧 strip 即可
- `get_overall_status()` 的 for 循环 bug 会导致多 provider 时只返回第一个非 ready provider 的状态
- Agent 编辑失败根因：凭据索引键（provider slug）与注册表索引键（实例名）不同，需在两者之间通过 `a.provider` 显式转换
- OpenRouter 模型 ID 为其平台路由 ID（`provider/model-name`），不适用于直连 Provider 端点；Add 模式已改为静态 fallback，不再依赖 OpenRouter

### 待跟进
- 🔴 实现 `AgentWorker`（消费 `dispatched` → 调用 agent.execute() → 发布 `results`），这是执行管道的缺失核心
- 🟠 统一 `AgentRegistry` key 大小写（lowercase 存储）以匹配 executor/PSC
- 🟠 `Provider 预设数据双源`：`routes.py` 与 `config.html` 各维护一份 PROVIDER_PRESETS，待统一到 `provider_presets.yaml`
- 🟡 `config.html` model sort 假设对象形状：models 为字符串时 `.model_id` 为 undefined
- 🟡 `loadHistory()` regex 截断多行消息

---

## 2026-05-21 — 全量扫描 + 批量修复 17 项关键问题

### 完成

**安全修复（4 项）：**
- 修复 `tools/executor.py` `_handle_filesystem` 路径穿越：`os.path.realpath` + 前缀校验替代裸 `os.path.join`
- 修复 `archive/archiver.py` SFTP `AutoAddPolicy` → `RejectPolicy` + 系统 host keys + 可配置化
- 修复 `archive/archiver.py` write_log 空 catch → 记录 warning
- 修复 `dashboard.html` innerHTML XSS：用户数据注入前 `escapeHtml()` 转义

**模型同步修复（6 项）：**
- 修复 `_fetch_from_openrouter` / `_discover_models` / `_enrich_from_openrouter` 静默吞错 → 添加 logger 记录
- 修复 `config.html` Model 下拉不显示：添加自动同步（选择 Provider 时自动拉取模型）
- 修复 `config.html` Sync Models 错误不显示：增强错误反馈，显示 HTTP 状态码
- 修复 `config.html` 同步返回 0 模型无提示 → 显示错误消息
- 添加 `FALLBACK_MODELS` 静态模型列表（DeepSeek/OpenAI/Claude 等 9 个 Provider）
- 修复 `load_agent_registry` 文件不存在时崩溃 → 返回空注册表

**后端修复（7 项）：**
- 修复 `session/manager.py` `add_agent()` 方法名崩溃（`_resolve_api_key` → `_get_api_key`）
- 修复 `host/host.py` strategy.json 格式：`str(psc)` → `json.dumps()`
- 修复 `host/host.py` `_wait_confirm`：去除非确认文本覆盖策略 + progress 事件 + 轮询提示
- 修复 `host/executor.py` Agent 超时静默返回 → 描述性消息
- 修复 `guard/guard.py` `check_timeouts()` 从未被调用 → `check()` 自动调用
- 修复 `main.py` FERNET_KEY 警告 + shutdown 异常记录
- 修复 `routes.py` `send_message`/`execute_session` 检查 closed 状态

**前端修复（6 项）：**
- 修复 6 处空 catch 块 → `console.error`（dashboard + session_chat）
- 修复 `dashboard.html` 冗余 evtSource + SSE XSS
- 修复 `session_chat.html` SSE 连接泄漏（close + clearTimer + guard）+ `console.log` 残留
- 修复 `sendMessage` 错误后 thinking 动画卡住
- 修复 `pauseSession`/`resumeSession` fire-and-forget → 检查响应
- 修复 `executeStrategy` 3s 硬编码超时 / `archiveSession` 硬编码 / `loadPermissions` 模式下拉 / 缺失图标

**测试：**
- 更新 `test_guard_advanced.py` 适配 `check_timeouts()` 自动调用
- 累计：302 passed, 11 skipped, 2 预存失败（config 注册表测试，非本次改动）

### 问题/发现
- 2 个预存 config 测试失败：测试期望空注册表但 config YAML 有实际条目
- SFTP Storage 构造改为接收参数，但 Archiver 仍无参调用（需后续统一）
- 全量扫描共发现 103 项问题，今日修复 17 项关键项

### 待跟进
- 🔴 统一 Archiver SFTP 实例化方式
- 🟡 Docker 子容器沙箱 / 搜索工具实现 / ELSE 分支 / 归档去重 / 响应式
- 🟡 Sandbox Bridge（沙箱内代码回调外部服务）
- 🟢 config.html Provider 预设双源同步 / 文档占位符

---

## 2026-05-20 — 用户界面全面修复 + Phase 4 测试增强

### 完成
- 修复 StrategyTemplate 未导入导致模板增改崩溃的 bug
- Chat 页面添加 SSE 实时监听 outbox，Agent 回复实时显示
- Chat 页面加载时自动拉取消息历史
- 新增 per-session SSE 端点：`GET /api/sessions/{id}/events/stream`
- Provider 下拉框改为从 API `/api/config/agents` 动态加载，不再硬编码
- Model 选择器添加到 Session 创建和 Chat 侧边栏，根据 Provider 联动
- Config 页面 baseURL 添加快捷按钮（OpenAI/Anthropic/DeepSeek 一键填充）
- Config 页面 Provider 改为下拉选择器
- Session 创建添加人类可读名称字段
- Dashboard 卡片显示 session 名称和创建时间
- Chat 页面消息时间戳
- Chat 页面 Agent 思考中加载动画（thinking indicator）
- Execute 按钮反馈状态变化
- 全局 Toast 通知系统
- Chat 侧边栏添加 Archive 归档按钮
- Chat 侧边栏 Agent 支持点击编辑（角色/Provider/Model）
- Chat 侧边栏权限模式管理 UI
- Dashboard SSE 断线自动重连（5s 间隔）
- 修复 Jinja2 TemplateResponse 在 Python 3.14 下的缓存 bug → 改用直接渲染
- main.py 模板渲染复用 `TEMPLATES_ENV` 而非每请求新建 Environment
- SessionManager 存储 `name`/`created_at`/`agent_configs`
- agent_registry.yaml 补全 Claude 和 OpenAI 条目
- Config 模板 PATCH 端点改为 `ConfigTemplateUpdateRequest`（可选字段）
- 修复移除/更新 Agent 时同步更新 `agent_configs` 列表
- Sandbox：白名单目录隔离 + 路径遍历防护 + Python/Shell 子进程执行 + cleanup
- Archive & Remote Storage：Archiver（打包 tar.gz）+ 3 种远端存储（LocalNasStorage / S3Storage / SftpStorage）+ write_log
- 容量预警：`check_disk_usage()` + health endpoint 返回 `disk_usage_gb`
- 集成到 main.py：Sandbox + Archiver 加入 app.state
- Sandbox 测试从 10 条扩展到 23 条（新增 13 条）
- Archive 测试从 9 条扩展到 18 条（新增 9 条）
- 累计：290 tests pass

### 问题/发现
- Jinja2 TemplateResponse 在 Python 3.14 下 LRUCache 无法缓存含 unhashable `Request` 的 context
- agent_registry.yaml 原先只有 DeepSeek 一个条目，缺失 Claude/OpenAI

### 待跟进
- Phase 5：IM Bridge + DAG 编辑器

---

## 2026-05-19 — Phase 3 接口层搭建完成

### 完成
- API Server：20+ REST 端点（Sessions / Messages / Agents / Permissions / Archive / Config / SSE）+ 全部通过 curl 测试
- Session Logger：conversation.log / messages.jsonl / events.jsonl 写盘 + History API
- Animal Island UI Assets：30 个字体文件 + CSS + favicon 下载到 static/
- Jinja2 Web UI：Dashboard（卡片式 Session 概览）/ Session Create（Agent 选择器）/ Session Chat（对话页 + 侧边栏）
- 修复 Jinja2 TemplateResponse 缓存 bug → 改用直接渲染
- 修复 MQ Layer BUSYGROUP → 优雅降级
- 修复 data_dir 回退到 /tmp/
- 累计：219 tests pass

### 问题/发现
- Jinja2 TemplateResponse 在 Python 3.14 下与 dict 参数有缓存 bug，需 `cache_size=0` 或直接渲染
- 测试 data_dir 硬编码 `/data/sessions` 在 macOS 只读，需用 `DATA_DIR` 环境变量或 `/tmp` 回退

### 待跟进
- Phase 4：Sandbox + Archive + 容量预警

---

## 2026-05-19 — Phase 2 核心运行时搭建完成

### 完成
- Agent Adapters：BaseAgent 基类 + DeepSeek/Claude/OpenAI 适配器 + AgentRegistry（7 tests pass）
- Session Guard：whitelist/approval_first/open 三种模式 + 审批流程 + Agent 级别覆写（11 tests pass）
- Host：.psc 编译器（compile_psc） + 执行器（Executor，Guard 校验 → MQ 分发 → 收结果 → 分支） + 策略生成器（StrategyGenerator，4 模板匹配） + 主循环（consume inbox → 生成 psc → 用户确认 → 编译执行 → outbox 回复）（9 tests pass）
- Session Manager：创建/暂停/恢复/关闭 + 动态增减 Agent + config.json 落盘（8 tests，需 Redis）
- 累计：Phase 1 (29) + Phase 2 (27+8) = 56 unit tests pass + 8 integration tests ready

### 问题/发现
- .psc 编译器 IF/ELSE 嵌套逻辑需仔细处理（branch_stack + pending_else_branch）
- .psc 格式当前不支持缩进语义（REVIEWER 行下的 IF 被解析为平级兄弟节点，而非子节点）

### 待跟进
- Phase 3：API Server + Session Logger + Jinja2 UI
- 启动 Redis 运行 Session Manager 集成测试

---

## 2026-05-19 — Phase 1 地基搭建完成

### 完成
- 项目骨架：pyproject.toml / Dockerfile / docker-compose.yml / .env.example / .venv
- 源码目录结构：src/blackboard/{api,mq,host,guard,agents,session,im_bridge,logger,config,tools}
- System Config 加载器：YAML → Pydantic 模型（system / agent registry / strategy templates / permission presets / tool registry）
- MQ Layer：Redis Streams 封装（publish / consume / ack / pending / init / destroy / session 隔离）
- 消息模型：Task / TaskResult / ApprovalRequest / ApprovalResponse / StreamMessage
- 错误类型：7 种异常（AgentRegistryError / MissingApiKeyError / InvalidApiKeyError / SandboxExecutionError / StorageQuotaError / ArchiveFailedError / ApprovalTimeoutError）
- Tool Registry：7 个内置工具（文件读写 / Python 执行 / Shell 执行 / HTTP 请求 / 网络搜索） + ToolExecutor
- FastAPI 入口：health endpoint + config 加载 + MQ 连接 + 工具加载
- 配置文件：system.yaml / agents/registry.yaml / strategy_templates/templates.yaml / permissions/presets.yaml / tools/registry.yaml
- 测试：29 个 pytest (test_config / test_models / test_tools) 全部通过，0 warning
- Mock Redis 测试跳过机制（conftest.py 自动检测）
- 测试文档：Phase 1 32 个用例（test_phase1.md）

### 待跟进
- Phase 2：Agent Adapters + Session Guard + Host + Session Manager
- 下载 Animal Island UI assets
- 补充 background.md 成功标准

---

## 2026-05-19 — 架构审核与文档全面修复

### 完成
- 18 点架构审核（含模块关系、API 表、MQ Streams 设计、权限模型、部署架构）
- 确认 Guard 中间态拦截、Host per-session 进程模型、Sandbox 沙箱方案
- 新增 System Config 模块（全局配置、Agent 注册表、策略模板库、权限预设）
- 新增沙箱执行环境（初期 subprocess + 白名单目录，后期 Docker 子容器）
- 新增归档与远端存储（local_nas / s3 / sftp，用户手动触发）
- 新增容量预警机制（`warning_threshold_gb` + SSE 推送）
- 新增 7 种错误类型定义
- BaseAgent 接口补充记忆文件读写方法（load_memory / save_memory）
- API 表新增 10 个端点（PATCH Agent、Config CRUD、Archive）
- Events Stream 拆分为两个消费者组（logger / api-sse）
- Outbox Stream 增加 target_channel 路由字段
- 补充 terms.md 14 个新术语（Host、Session Guard、Sandbox、Archive 等）
- 补充 decisions.md 5 条 ADR（Session Guard / Sandbox / 归档存储 / 记忆文件 / IM Bridge）
- 修复 15 处文档不一致（过时引用、路径错误、缺失内容、fixture 冲突）
- 更新 background.md 核心功能描述与项目范围

### 待跟进
- 补充 background.md 成功标准
- 搭建项目骨架（pyproject.toml / Dockerfile / 源码目录）

---

## 2026-05-19 — 项目初始化

### 完成
- 初始化项目文档结构（instruction / background / architecture / rule / log / todo / decisions / terms）
- 确定架构方案：事件驱动 + Agent 编排
- 确定技术栈：Python 3.12 + FastAPI + Redis Streams + Jinja2 + Docker
- 确定 UI 方案：Jinja2 模板 + Animal Island CSS 设计风格
- 创建 AGENTS.md 定义 AI 协作指令

---

<!-- 新日志在上方添加，格式：
## YYYY-MM-DD — 简要说明

### 完成
- 

### 问题/发现
- 

### 待跟进
- 
-->
