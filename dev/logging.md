# Log 功能开发总结

> 实现日期：2026-05-24  
> 最后更新：2026-05-24  
> 涉及模块：`logger/`、`host/`、`tools/`、`session/`、`api/`

---

## 更新日志

| 日期 | 版本 | 变更内容 |
|------|------|---------|
| 2026-05-24 | v1.0 | 初版上线：`log_models.py`、`session_logger.py` 扩展、`SystemLogger`、9 个 API 端点、23 个单元测试 |
| 2026-05-24 | v1.1 | 修复 `asyncio.CancelledError` 被误记为 `success=True` 的 bug；新增 `record_agent_call` / `record_tool_call` 的 `CancelledError` 专用分支（`level=WARNING`） |
| 2026-05-24 | v1.2 | 新增 `Host.cancel_tasks()` 和 `_run_as_task()`，支持 `POST /sessions/{id}/cancel` 中断正在运行的 Agent 调用而不停止 Host 主循环 |
| 2026-05-24 | v1.3 | 新增 `SessionManager.restore_sessions()`，容器重启后可恢复所有 Session；JSONL append-only 保证历史日志连续性 |

---

## 一、功能背景

系统原有的 `SessionLogger` 只记录三类信息：对话文本（`conversation.log`）、MQ 消息备份（`messages.jsonl`）、系统事件（`events.jsonl`）。这三类均属于"发生了什么"的事实记录，缺少：

- **操作追溯**：Agent 被调用了几次、每次耗时多久、输入/输出是什么
- **工具追溯**：哪些 Tool 被执行过、参数和结果是什么
- **告警聚合**：WARNING 和 ERROR 级别事件分散在 stdout，无法按 session 查询
- **结构化可查询**：旧日志为纯文本，不能按 agent_name、level、时间段过滤
- **跨 Session 监控**：多 Session 并行时无法在一处看到所有异常，只能逐个打开目录

本次 Log 功能在不引入外部日志服务（如 ELK、Loki）的前提下，通过扩展现有文件落盘机制实现全量结构化日志，同时修复了一个 `asyncio.CancelledError` 导致取消操作被误记为成功的 bug。

---

## 二、日志文件结构

### 2.1 Session 目录内的文件职责划分

同一目录下的文件分属两个不同的职责域，**不要混淆**：

```
/data/sessions/{session_id}/
│
│  ── 消息存档（Message Archive）──────────────────────────────────
├── messages.jsonl         # MQ 原始消息流备份（非 log，见 2.3）
│
│  ── 运营日志（Operational Log，本文档的范围）────────────────────
├── agent_calls.jsonl      # ★ Agent 调用日志（新增）
├── tool_calls.jsonl       # ★ Tool 调用日志（新增）
├── warnings.jsonl         # ★ 本 Session 的 WARNING（新增）
├── errors.jsonl           # ★ 本 Session 的 ERROR（新增）
│
│  ── 其他辅助文件 ─────────────────────────────────────────────
├── config.json            # Session 配置
├── strategy.psc           # 策略文件
├── conversation.log       # 对话文本（人类可读，供调试）
└── events.jsonl           # 系统事件（生命周期节点）
```

### 2.2 系统级日志（cross-session）


当多个 Session 并行运行时，需要一个统一视角监控所有 Session 的告警。每条 WARNING/ERROR 在写入 Session 级文件的同时，**双写**到系统级聚合文件：

```
/data/sessions/_system/
├── warnings.jsonl         # 所有 Session 的 WARNING（含 session_id + timestamp）
└── errors.jsonl           # 所有 Session 的 ERROR（含 session_id + timestamp + traceback）
```

两层日志相互独立：
- **Session 级**：只含本 Session 的数据，适合排查单个 Session 的问题
- **系统级**：所有 Session 的 WARNING/ERROR 按时间顺序追加，适合全局监控和告警聚合

所有运营日志文件均为 **JSONL 格式**（每行一个 JSON 对象），append-only，永不覆盖。文件不存在时自动创建，目录不存在时自动 `mkdir -p`。

### 2.3 消息存档与运营日志的边界

| | `messages.jsonl` | 运营日志（`agent_calls` 等） |
|---|---|---|
| **职责** | MQ 原始消息流的完整备份 | 系统运行质量的结构化记录 |
| **内容** | 每条 MQ 消息的 `stream` + `payload`（原始格式，不解析语义） | Agent 耗时、成功率、Guard 拦截、异常 traceback 等 |
| **用途** | 消息重放、调试通信问题、前端状态恢复 | 性能分析、安全审计、告警聚合、问题排查 |
| **查询入口** | 现有的 `SessionLogger.read_messages()` | 本文档描述的 `read_*` 方法和 `/logs` API 端点 |
| **系统级聚合** | 无（per-session 独立） | WARNING/ERROR 双写至 `_system/` 目录 |

`messages.jsonl` 记录"发送了什么"，运营日志记录"执行得怎样"。两者互补但职责不重叠，`log_summary()` 和 `/logs` API 端点均**不包含** `messages.jsonl` 的统计。

---

## 三、数据模型

### 3.1 公共基类 `LogEntry`

所有日志条目继承此基类，**每条记录都包含 `timestamp` 和 `session_id`**，这两个字段是多 Session 并行场景下溯源的关键：

```python
class LogEntry(BaseModel):
    timestamp: str   # ISO 8601 UTC，e.g. "2026-05-24T10:30:00.123456+00:00"
    session_id: str  # 所属 Session ID，系统级日志靠此字段区分来源
    level: LogLevel  # INFO | WARNING | ERROR
    component: str   # 产生日志的代码位置，e.g. "host._direct_chat"
```

---

### 3.2 `AgentCallEntry` → `agent_calls.jsonl`

记录每一次 Agent 调用的完整生命周期：

| 字段 | 类型 | 说明 |
|------|------|------|
| `agent_name` | str | Agent 实例名（小写），e.g. `"deepseek"` |
| `prompt_preview` | str | 输入提示词前 100 字符（截断，避免完整持久化敏感内容） |
| `response_preview` | str | Agent 回复前 200 字符 |
| `model` | str | 实际使用的模型 ID，e.g. `"deepseek-chat"` |
| `success` | bool | `true` = 正常完成；`false` = 失败或被取消 |
| `error` | str | 失败原因；被取消时固定为 `"cancelled"` |
| `duration_ms` | float | 调用耗时（毫秒，精确到 0.1ms）|
| `level` | LogLevel | 正常 `INFO`；Agent 抛出异常 → `ERROR`；被取消 → `WARNING` |

**示例（正常完成）**：
```json
{
  "timestamp": "2026-05-24T10:30:00.123+00:00",
  "session_id": "abc123",
  "level": "INFO",
  "component": "host._direct_chat",
  "agent_name": "deepseek",
  "prompt_preview": "请分析这段代码的性能瓶颈",
  "response_preview": "该段代码的主要性能问题在于...",
  "model": "deepseek-chat",
  "success": true,
  "error": "",
  "duration_ms": 3210.5
}
```

**示例（用户取消）**：
```json
{
  "timestamp": "2026-05-24T10:31:05.000+00:00",
  "session_id": "abc123",
  "level": "WARNING",
  "component": "agent",
  "agent_name": "deepseek",
  "prompt_preview": "请帮我重写整个系统",
  "response_preview": "",
  "model": "deepseek-chat",
  "success": false,
  "error": "cancelled",
  "duration_ms": 4820.0
}
```

---

### 3.3 `ToolCallEntry` → `tool_calls.jsonl`

记录每一次 Tool 调用（通过 `ToolExecutor`）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `tool_name` | str | 工具名，e.g. `"filesystem.read"`、`"sandbox.python"` |
| `parameters` | dict | 完整参数（如包含代码或文件内容，由调用方控制长度） |
| `result_preview` | str | 执行结果前 200 字符 |
| `success` | bool | 工具执行是否成功 |
| `error` | str | 失败原因；被取消时固定为 `"cancelled"` |
| `duration_ms` | float | 执行耗时（毫秒） |
| `level` | LogLevel | 正常 `INFO`；异常 `ERROR`；取消 `WARNING` |

---

### 3.4 `WarnErrorEntry` → `warnings.jsonl` / `errors.jsonl`

记录 WARNING 和 ERROR 级别的运行时事件：

| 字段 | 类型 | 说明 |
|------|------|------|
| `level` | LogLevel | `WARNING` 或 `ERROR` |
| `component` | str | 来源模块 + 方法，e.g. `"executor._dispatch_agent"` |
| `message` | str | 人类可读的描述 |
| `data` | dict | 结构化上下文（agent 名、操作类型等） |
| `exc_str` | str | 异常 traceback 全文（ERROR 时填充，WARNING 时通常为空） |

---

## 四、埋点位置详表

### 4.1 Agent 调用埋点

所有 Agent 调用均通过 `record_agent_call` 异步上下文管理器包裹，计时在 `finally` 块执行，**保证即使抛出异常或被取消也会落盘**。

| 调用路径 | 代码位置 | 触发条件 |
|---------|---------|---------|
| 用户直接发消息 → 默认 Agent | `host/host.py` `Host._direct_chat` | 每次单 Agent 对话 |
| 用户 `@AgentA ... @AgentB` 多 Agent 链 | `host/host.py` `Host._multi_agent_chat` | 每个 `@mention` 分段各触发一次 |
| PSC 策略执行中分发任务 | `host/executor.py` `Executor._dispatch_agent` | 每个 PSC AST Agent 节点 |

所有 Agent 调用在 `Host.run()` 中都通过 `_run_as_task()` 包裹，支持用户随时通过 `POST /sessions/{id}/cancel` 中断正在执行的调用。被中断时，`record_agent_call` 捕获 `asyncio.CancelledError`，将条目记为 `success=False`、`error="cancelled"`、`level=WARNING`，**不会误记为成功**（这是一个已修复的 bug）。

### 4.2 Tool 调用埋点

| 调用路径 | 代码位置 | 触发条件 |
|---------|---------|---------|
| Tool 执行 | `tools/executor.py` `ToolExecutor.execute` | 传入 `session_logger` 时触发 |

`ToolExecutor.execute` 增加可选参数 `session_logger: SessionLogger | None`，不传则不记录（向下兼容）。同样处理取消场景。

### 4.3 WARNING 埋点

以下情况写入 `warnings.jsonl`（同时保留原有的 `logger.warning` 到 stdout）：

| 触发条件 | 代码位置 | `component` 值 | `data` 内容 |
|---------|---------|---------------|-----------|
| Agent 返回 `success=False`（无异常） | `host/host.py` `_direct_chat` | `host._direct_chat` | `{agent, error}` |
| 多 Agent 链中某个 Agent 失败 | `host/host.py` `_multi_agent_chat` | `host._multi_agent_chat` | `{agent, error}` |
| Guard 拦截操作（`DENIED`） | `host/executor.py` `_dispatch_agent` | `executor._dispatch_agent` | `{operation, agent, action}` |
| 用户在审批弹窗中点击「拒绝」 | `host/executor.py` `_dispatch_agent` | `executor._dispatch_agent` | `{operation, agent}` |
| 审批等待超时（5 分钟） | `host/executor.py` `_dispatch_agent` | `executor._dispatch_agent` | `{operation, agent}` |
| PSC 策略执行中 Agent 失败 | `host/executor.py` `_dispatch_agent` | `executor._dispatch_agent` | `{agent, operation, error}` |
| Agent 调用被用户取消 | `session_logger.py` `record_agent_call` | `"agent"` | 在 `agent_calls.jsonl` 中记为 `level=WARNING` |
| Tool 执行被用户取消 | `session_logger.py` `record_tool_call` | `"tool"` | 在 `tool_calls.jsonl` 中记为 `level=WARNING` |

### 4.4 ERROR 埋点

以下情况写入 `errors.jsonl`（同时保留原有的 `logger.exception` 到 stdout，`exc_str` 包含完整 traceback）：

| 触发条件 | 代码位置 | `component` 值 |
|---------|---------|---------------|
| Agent 调用中抛出未捕获异常 | `host/host.py` `_direct_chat` | `host._direct_chat` |
| 多 Agent 链中某段抛出异常 | `host/host.py` `_multi_agent_chat` | `host._multi_agent_chat` |
| PSC 策略整体执行失败 | `host/host.py` `_run_strategy` | `host._run_strategy` |
| Agent 实例在 registry 中找不到 | `host/executor.py` `_dispatch_agent` | `executor._dispatch_agent` |
| Tool 执行过程中抛出异常 | `tools/executor.py` `ToolExecutor.execute` | `"tool"`（由 `record_tool_call` 捕获，`level` 自动升为 `ERROR`） |

---

## 五、安全级别与告警条件

### 5.1 级别定义

| 级别 | `LogLevel` 值 | 含义 |
|------|--------------|------|
| INFO | `"INFO"` | 正常操作，供性能分析和追溯用 |
| WARNING | `"WARNING"` | 操作被拦截、失败或被用户主动取消，系统仍在正常运行 |
| ERROR | `"ERROR"` | 异常抛出，操作未完成，需要排查 |

### 5.2 安全相关 WARNING 条件（Guard 拦截）

这部分日志与权限守卫（Session Guard）直接关联，是**安全审计的核心来源**：

| 告警场景 | `data` 字段 | 风险说明 |
|---------|------------|---------|
| `DENIED`：操作在 whitelist 模式下被封禁 | `{operation, agent, action}` | Agent 尝试执行了当前权限配置不允许的操作（如 `execute_code`、`file_delete`） |
| `REJECTED`：用户在审批弹窗中主动拒绝 | `{operation, agent}` | 用户判断该操作不安全，手动拦截 |
| `TIMEOUT`：审批等待超时（5 分钟无响应） | `{operation, agent}` | 审批请求未及时处理，操作被自动拒绝 |

可通过 `GET /api/sessions/{id}/logs/warnings` 过滤 `component=executor._dispatch_agent` 的条目，快速审查所有被拦截的 Agent 操作。

### 5.3 ERROR 条件说明

| ERROR 来源 | 常见根因 | 如何排查 |
|-----------|---------|---------|
| `host._direct_chat` / `_multi_agent_chat` | Provider API 超时、API key 无效、网络不通 | 查 `exc_str` 字段获取完整 traceback |
| `host._run_strategy` | PSC 编译失败、Executor 中途异常 | 结合 `errors.jsonl` + `warnings.jsonl` 时序还原执行过程 |
| `executor._dispatch_agent`（找不到 Agent） | Session 中 Agent 被移除、Agent 名拼写错误 | 查 `data.agent` 字段对照当前 Agent 注册表 |
| Tool `record_tool_call` 捕获 | 沙箱代码错误、文件权限问题、HTTP 连接超时 | `tool_calls.jsonl` 中 `level=ERROR` 的条目含 `error` 详情 |

---

## 六、可追溯的信息

### 6.1 Agent 维度（`agent_calls.jsonl`）

- **调用次数**：统计某 Agent 在整个 Session 中被调用的总次数
- **成功/失败/取消率**：`success` 字段 + `error="cancelled"` 区分三种状态
- **平均/最大/最小延迟**：`duration_ms` 字段，可定位响应慢的 Agent 或特定时间段的超时
- **输入摘要**：`prompt_preview`（前 100 字），可还原每次 Agent 收到的任务
- **输出摘要**：`response_preview`（前 200 字），可回看 Agent 每次的核心回答
- **模型信息**：`model` 字段，若 Agent 在 Session 期间切换了模型，可从日志中看到变化
- **调用来源**：`component` 字段区分是来自 direct_chat、multi_agent_chat 还是 PSC 策略执行
- **取消记录**：`level=WARNING` + `error="cancelled"` 标记用户中断的调用，含已耗时

### 6.2 工具维度（`tool_calls.jsonl`）

- **工具使用频率**：统计各工具的调用次数
- **参数记录**：`parameters` 字段完整保留调用参数（`read_file` 的路径、`execute_python` 的代码等）
- **执行结果摘要**：`result_preview` 记录输出前 200 字符
- **执行耗时**：沙箱代码执行慢、HTTP 请求超时等都可从 `duration_ms` 定位
- **失败详情**：`error` 字段记录工具执行失败原因（如路径不存在、Python 语法错误）

### 6.3 权限与安全维度（`warnings.jsonl`）

- **所有被拦截操作的完整记录**：operation、agent、action 三元组
- **拦截时间点**：通过 `timestamp` 可还原操作被拒绝时系统的状态
- **用户审批行为**：`REJECTED` 类型的 warning 记录用户手动拒绝了哪些操作
- **超时模式**：频繁出现 `TIMEOUT` 可能意味着审批流程设计需要调整
- **取消行为**：用户通过「停止」按钮中断的 Agent/Tool 调用，可与 `agent_calls.jsonl` 交叉验证

### 6.4 系统健康维度（`errors.jsonl`）

- **异常时间线**：按 `timestamp` 排列可还原 Session 期间所有异常的发生顺序
- **高频错误**：同一 `component` 反复出现 ERROR 通常意味着配置问题（API key 失效等）
- **Traceback 保留**：`exc_str` 字段保存完整 Python traceback，无需重现 bug 即可远程排查
- **错误与告警的关联**：同一时间段内 `warnings.jsonl` 的 Guard 拦截 + `errors.jsonl` 的执行失败，可组合还原完整事故链

### 6.5 汇总概览

**Session 级**（`GET /api/sessions/{id}/logs`）：
```json
{
  "session_id": "abc123",
  "agent_calls": 15,
  "tool_calls": 3,
  "warnings": 2,
  "errors": 0
}
```

**系统级**（`GET /api/logs`）：
```json
{
  "warnings": 7,
  "errors": 1
}
```

---

## 七、API 查询接口

### 7.1 Session 级（单 Session 查询）

5 个端点挂在 `/api/sessions/{session_id}/` 下，**不要求 Session 仍在运行**（直接读取文件，不走 `session_mgr._sessions`），因此已关闭或重启恢复的 Session 历史数据也可查询：

| 方法 | 路径 | 说明 | 参数 |
|------|------|------|------|
| GET | `/api/sessions/{id}/logs` | 各类型日志条目数汇总 | — |
| GET | `/api/sessions/{id}/logs/agent_calls` | Agent 调用日志，支持分页 | `limit=50`、`offset=0` |
| GET | `/api/sessions/{id}/logs/tool_calls` | Tool 调用日志，支持分页 | `limit=50`、`offset=0` |
| GET | `/api/sessions/{id}/logs/warnings` | 本 Session 的 WARNING 条目 | — |
| GET | `/api/sessions/{id}/logs/errors` | 本 Session 的 ERROR 条目（含 traceback） | — |

### 7.2 系统级（跨 Session 聚合查询）

3 个端点挂在 `/api/logs/` 下，读取 `_system/` 目录的聚合文件，**每条记录含 `session_id` 和 `timestamp`**：

| 方法 | 路径 | 说明 | 参数 |
|------|------|------|------|
| GET | `/api/logs` | 系统级 WARNING 和 ERROR 数量汇总 | — |
| GET | `/api/logs/warnings` | 所有 Session 的 WARNING，按时间排序 | `limit=100`、`offset=0` |
| GET | `/api/logs/errors` | 所有 Session 的 ERROR（含 traceback） | `limit=100`、`offset=0` |

**典型用法**：多个 Session 并行运行时，通过 `/api/logs/errors` 可以立刻看到哪个 Session 出了问题（`session_id` 字段）以及精确发生时间（`timestamp` 字段），而无需逐个访问 per-session 端点。

### 7.3 取消正在执行的 Agent 调用

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/sessions/{id}/cancel` | 取消当前正在执行的 Agent 调用（不关闭 Session） |

取消后，`agent_calls.jsonl` 会新增一条 `level=WARNING`、`error="cancelled"` 的记录，包含实际已耗时（`duration_ms`）。

---

## 八、核心实现说明

### 8.1 自动计时上下文管理器

两个 `asynccontextmanager` 是实现零侵入计时的关键：

```python
async with session_logger.record_agent_call(agent_name, prompt, model) as rec:
    result = await agent.execute(task)
    rec.success = result.success
    rec.response_preview = (result.content or "")[:200]
    rec.error = result.error or ""
```

- `yield` 的是 `AgentCallEntry` 对象，调用方直接修改字段
- `finally` 块写入 `duration_ms` 并落盘，**即使异常或取消也保证落盘**
- 三条异常分支：
  - `asyncio.CancelledError` → `success=False`、`error="cancelled"`、`level=WARNING`，re-raise
  - `Exception` → `success=False`、`error=str(e)`、`level=ERROR`，re-raise
  - 无异常 → 调用方设置的字段，`level=INFO`（默认）

### 8.2 取消机制与日志的交互

`Host` 引入了任务取消能力（2026-05-24 新增）：

```
用户点击「停止」
    │
    POST /api/sessions/{id}/cancel
    │
    Host.cancel_tasks()
    │
    asyncio.Task.cancel()  ← 注入 CancelledError 到当前协程
    │
    _direct_chat / _multi_agent_chat
    │   ├── record_agent_call 的 except CancelledError 捕获
    │   │    → 写 agent_calls.jsonl (level=WARNING, error="cancelled")
    │   └── re-raise → _run_as_task 捕获，静默丢弃
    │
    Host loop 继续等待下一条消息
```

`_run_as_task` 是所有 Agent 调用的包裹器，确保取消只影响当前任务，不会停止整个 Host 主循环。

### 8.3 注入链路

```
SessionManager.create()
    │
    ├── SessionLogger(session_id, data_dir)
    │      │
    │      ├── 写 /data/sessions/{session_id}/warnings.jsonl  ← per-session
    │      └── 写 /data/sessions/_system/warnings.jsonl       ← 系统级（双写）
    │
    └── Host(..., session_logger=session_logger)
            │
            └── Executor(..., session_logger=session_logger)

ToolExecutor（全局单例）
    └── execute(call, session_logger=sl)  ← 调用时传入，不在构造时注入
```

### 8.4 双写策略

所有埋点均保持原有的 `logger.warning(...)` / `logger.exception(...)` 调用（stdout），同时增加对 `session_logger.log_warn()` / `session_logger.log_error()` 的调用（文件）。两套日志互不依赖，任一失败不影响另一套。

### 8.5 Session 重启恢复与日志连续性

`SessionManager.restore_sessions()`（2026-05-24 新增）在容器重启时扫描 `data_dir` 恢复所有 Session。`SessionLogger` 使用 append-only JSONL，**历史日志不会被覆盖**，恢复后的新日志直接追加到已有文件末尾，`timestamp` 和 `session_id` 保证时序正确。

---

## 九、文件清单

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `src/blackboard/logger/log_models.py` | 新建 | `LogLevel`、`LogEntry`（含 `session_id` + `timestamp`）、`AgentCallEntry`、`ToolCallEntry`、`WarnErrorEntry` |
| `src/blackboard/logger/session_logger.py` | 扩展 | `_root_dir`；系统级双写路径；`_write_jsonl` 改为 `path.parent.mkdir`；`log_warn`/`log_error` 双写；`record_agent_call`/`record_tool_call` 增加 `CancelledError` 分支（`level=WARNING`）；`SystemLogger` 类；`read_*` 系列方法 |
| `src/blackboard/logger/__init__.py` | 更新 | 导出 `SessionLogger`、`SystemLogger` 及所有 log model 类型 |
| `src/blackboard/host/host.py` | 修改 | 新增 `session_logger` 参数、`_current_task`、`cancel_tasks()`、`_run_as_task()`；`_direct_chat` 增加 `CancelledError` 处理并通知 UI；`_multi_agent_chat`、`_run_strategy` 埋点；`_log_reply` 复用 `session_logger.log_conversation` |
| `src/blackboard/host/executor.py` | 修改 | 新增 `session_logger` 参数；`_dispatch_agent` 埋点 Agent 调用 + Guard 拒绝/超时/审批拒绝 + Agent 未找到 |
| `src/blackboard/tools/executor.py` | 修改 | `execute()` 新增可选 `session_logger` 参数，Tool 调用埋点 |
| `src/blackboard/session/manager.py` | 修改 | `create()` 中实例化 `SessionLogger` 并传给 `Host`；新增 `restore_sessions()` 支持容器重启恢复 |
| `src/blackboard/api/routes.py` | 修改 | 新增 Session 级 5 个 `/sessions/{id}/logs/*` 端点 + 系统级 3 个 `/logs/*` 端点 + 取消端点 `POST /sessions/{id}/cancel`（共 9 个新端点） |
| `tests/test_logging.py` | 新建 | 23 个单元测试：Session 级 16 个（含 CancelledError 路径 2 个）+ SystemLogger 跨 Session 测试 7 个 |

---

## 十、开发迭代详情

### v1.0 — 结构化日志初版（2026-05-24）

**背景**：原有 SessionLogger 只记录对话文本、MQ 消息备份和系统事件，缺少操作追溯、告警聚合和跨 Session 监控能力。

**新增文件**：
- `src/blackboard/logger/log_models.py`：Pydantic v2 数据模型（`LogEntry`、`AgentCallEntry`、`ToolCallEntry`、`WarnErrorEntry`、`LogLevel`）
- `tests/test_logging.py`：21 个单元测试覆盖所有核心路径

**修改文件**（5 个）：
- `session_logger.py`：添加 `_write_jsonl`、`log_agent_call`、`log_tool_call`、`log_warn`、`log_error`；添加 `SystemLogger` 类；`_write_jsonl` 改用 `path.parent.mkdir`（支持系统级路径）；`log_warn`/`log_error` 双写 `_system/` 目录
- `host/host.py`：新增 `session_logger` 参数；`_direct_chat`、`_multi_agent_chat`、`_run_strategy` 埋点；`_log_reply` 复用 `log_conversation`
- `host/executor.py`：新增 `session_logger` 参数；`_dispatch_agent` 埋点（Guard 拦截、Agent 未找到、Agent 失败）
- `tools/executor.py`：`execute()` 新增可选 `session_logger` 参数，Tool 调用埋点
- `api/routes.py`：新增 Session 级 5 个端点 + 系统级 3 个端点（共 8 个）

---

### v1.1 — 修复 CancelledError 被误记为成功（2026-05-24）

**问题**：Python 3.8+ 中 `asyncio.CancelledError` 继承自 `BaseException` 而非 `Exception`。原版 `record_agent_call` / `record_tool_call` 只有 `except Exception` 分支，Task 被取消时会跳过异常分支直接进入 `finally`，以默认值 `success=True`、`level=INFO` 落盘——操作已被取消但被误记为正常完成。

**修复**（`session_logger.py`）：在 `except Exception` 之前新增 `except asyncio.CancelledError` 分支：
```python
except asyncio.CancelledError:
    entry.success = False
    entry.error = "cancelled"
    entry.level = LogLevel.WARNING
    raise  # 继续传播，不吞掉
```

**同样修复** `record_tool_call`，逻辑相同。

**新增测试**（2 个，`tests/test_logging.py`）：
- `test_record_agent_call_cancelled_logs_warning`
- `test_record_tool_call_cancelled_logs_warning`

总测试数：21 → 23，全部通过。

---

### v1.2 — Host 任务取消机制（2026-05-24）

**背景**：需要支持前端「停止」按钮，中断正在执行的 Agent 调用，但不关闭整个 Session。

**修改**（`host/host.py`）：
- `__init__` 新增 `self._current_task: asyncio.Task | None = None`
- `cancel_tasks()`：调用 `_current_task.cancel()`，仅取消当前任务
- `_run_as_task(coro)`：将 Agent 调用协程包裹为 `asyncio.Task`，Task 被取消只影响该任务，`await _run_as_task()` 的调用点（Host 主循环）不受影响
- `_direct_chat` 内新增 `except asyncio.CancelledError`：取消时向 UI 发送提示消息再 re-raise，保证前端有反馈
- `run()` 中的 MQ 消费错误增加 3 秒 retry，防止瞬断引发 Session 退出

**修改**（`api/routes.py`）：
- 新增 `POST /api/sessions/{id}/cancel` 端点，调用 `host.cancel_tasks()`

日志侧配合 v1.1 修复，取消后 `agent_calls.jsonl` 写入 `level=WARNING`、`error="cancelled"` 记录，含实际已耗时 `duration_ms`。

---

### v1.3 — Session 重启恢复（2026-05-24）

**背景**：容器重启后内存中的 Session 丢失，但磁盘上的 JSONL 日志文件完好。需要自动恢复 Session 以便继续接收请求，同时不覆盖已有日志。

**修改**（`session/manager.py`）：
- `restore_sessions()`：扫描 `data_dir` 下所有子目录，读取 `config.json`，按配置重新创建 `Host` 和 `SessionLogger` 实例，注册到 `_sessions` 字典
- `create()` 中显式实例化 `SessionLogger(session_id, str(self.data_dir))` 并传给 `Host`（确保路径一致）

**日志连续性**：JSONL append-only 设计保证恢复后新日志追加到文件末尾，历史数据不受影响，`timestamp` 字段仍可正确还原时序。

---

## 十二、已知限制与后续方向

| 限制 | 说明 | 可能的后续改进 |
|------|------|-------------|
| `prompt_preview` 只保存前 100 字 | 防止敏感内容完整持久化 | 若需完整审计，可改为可配置长度或加密存储 |
| `parameters` 字段无截断 | Tool 执行时若参数含大段代码或文件内容，`tool_calls.jsonl` 体积可能增大 | 对 `parameters` 中超过阈值的字符串 value 做截断 |
| 日志文件无自动轮转 | 长时间运行的 Session 日志文件持续增长 | 引入按文件大小或按日期的轮转机制（结合归档功能） |
| `agent_calls.jsonl` 无系统级聚合 | 目前只有 WARNING/ERROR 做跨 Session 双写，agent 调用性能数据仍在各 Session 目录 | 如需跨 Session 统计 Agent 延迟，可引入轻量聚合层（SQLite in-process）按需从 JSONL 导入 |
| ToolExecutor 需手动传 `session_logger` | 全局单例 ToolExecutor 不持有 session_logger，调用方需显式传入 | 若 Tool 调用量大，可改为 ToolExecutor 持有 logger 工厂，按 session_id 路由 |
| 无实时告警推送 | WARNING/ERROR 写入文件后无主动通知 | 可在 `log_error()` 内同时向 `outbox` Stream 推送告警消息，前端 SSE 实时展示 |
| MQ consume 重试不写 session_logger | `Host.run()` 的 MQ 消费失败会 retry 但只写 stdout | 如需追踪 MQ 连接不稳定，可在 `log_warn` 中记录重试事件 |
