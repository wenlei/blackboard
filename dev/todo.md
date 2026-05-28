# 任务 Backlog

> 状态：`[ ]` 待做 · `[x]` 完成 · `[~]` 进行中 · `[!]` 阻塞

---

## 总体路线

| 阶段 | 内容 | 依赖 | 产出 |
|------|------|------|------|
| **Phase 1 — 地基** | 项目骨架 + System Config + MQ Layer + Tool Registry | — | ✅ `docker compose up` 能跑，Redis 可读写，29 tests pass |
| **Phase 2 — 核心** | Agent Adapters + Session Guard + Host + Session Manager | Phase 1 | ✅ 190 tests pass（含 integration），能创建 Session，Host 生成 .psc 并执行 |
| **Phase 3 — 接口** | API Server + Session Logger + Jinja2 UI | Phase 2 | ✅ 290 tests pass（跨 Phase 累计），API + UI 全部可用 |
| **Phase 4 — 运维** | Sandbox + Archive + 容量预警 | Phase 3 | ✅ 290 tests pass（含 23 sandbox + 18 archive），沙箱隔离 + 归档链路完整 |
| **Phase 5 — 扩展** | IM Bridge + DAG 编辑器 + PSC ↔ DAG | Phase 3 | ⏳ TG/Discord 接入、可视化编排 |

---

## Phase 1 — 地基

> **目标**：项目能启动，Redis 可读写，配置可加载  
> **依赖**：无  
> **产出**：`docker compose up` 看到 "Blackboard ready" 日志

### 1.1 项目骨架
- [x] `pyproject.toml`（Python 3.12+、依赖声明：fastapi/redis/httpx/pydantic/jinja2/ruff/mypy）
- [x] `src/blackboard/` 包目录结构（api/mq/host/guard/agents/session/im_bridge/logger/config/tools）
- [x] `Dockerfile`（Python 3.12-slim + 依赖安装 + 入口）
- [x] `docker-compose.yml`（Redis:7-alpine + API 容器 + volume 挂载）
- [x] `.env.example`（DEEPSEEK_API_KEY / ANTHROPIC_API_KEY / OPENAI_API_KEY）

### 1.2 System Config
- [x] `config/system.yaml`（redis_url / data_dir / approval_timeout / max_retries / log_level）
- [x] `config/agents/registry.yaml`（DeepSeek v3 / Claude Sonnet / GPT-4o）
- [x] `config/strategy_templates/templates.yaml`（4 套模板）
- [x] `config/permissions/presets.yaml`（3 套预设）
- [x] 配置加载器（YAML → Pydantic 模型，启动时校验）

### 1.3 MQ Layer
- [x] Redis 连接管理（连接池、重连）
- [x] `publish(stream, message)` → XADD
- [x] `consume(stream, consumer_group, consumer_name)` → XREADGROUP + BLOCK
- [x] `ack(stream, consumer_group, message_id)` → XACK
- [x] `init_session_streams(session_id)` → 创建 6 个 Stream + 消费者组
- [x] `destroy_session_streams(session_id)` → 删除 Stream + 消费者组
- [x] `recover_pending(stream, consumer_group)` → XPENDING 拾取故障消息

### 1.4 消息与共享模型
- [x] `src/blackboard/models.py` — Task / TaskResult / Approval / StreamMessage Pydantic 模型
- [x] 错误类型定义（7 种异常）

### 1.5 Tool Registry
- [x] `config/tools/registry.yaml` — 7 个内置工具
- [x] `ToolRegistry` / `ToolCall` / `ToolResult` / `ToolDefinition` 模型
- [x] `ToolExecutor` — filesystem / sandbox / network / search 四类 handler
- [x] 工具与 Guard OperationType 映射

### ✅ Phase 1 检验
```bash
docker compose up -d                          # Redis + API 启动
curl http://localhost:8000/health              # {"status":"ok","redis":"connected","tools_loaded":7}
python3 -m pytest tests/ -q                    # 29 passed (29/29)
```

---

## Phase 2 — 核心

> **目标**：能创建 Session，Host 生成策略并执行一个完整的多 Agent 任务  
> **依赖**：Phase 1  
> **产出**：Python 脚本调用 API，3 个 Agent 协作完成一个代码审查任务

### 2.1 Agent Adapters
- [x] `BaseAgent` 抽象基类（execute / load_memory / save_memory / health_check）
- [x] Agent 注册表（从 registry.yaml 加载 → Agent 实例化）
- [x] ~~`DeepSeekAdapter`（httpx 调用 DeepSeek API）~~ → 已重构为 ChatCompletionsAdapter
- [x] ~~`ClaudeAdapter`（httpx 调用 Anthropic API）~~ → 已重构为 ChatCompletionsAdapter
- [x] ~~`OpenAIAdapter`（httpx 调用 OpenAI API）~~ → 已重构为 ChatCompletionsAdapter
- [x] `ChatCompletionsAdapter`（统一 OpenAI 兼容适配器，base_url + api_key 接入任意 Provider，含 OpenRouter ~ 前缀处理）（2026-05-22）
- [x] Agent 并行执行（多 Agent 同时消费同一 dispatched Stream）
- [x] Agent 错误处理（429 退避重试 / 超时 / 失败返回 error）

### 2.2 Session Guard
- [x] 权限配置加载（从 session config.json 读取）
- [x] 三种模式实现（whitelist / approval_first / open）
- [x] 分发前校验：Host 分发 → Guard.check(operation) → allowed / denied / require_approval
- [x] 执行中回调校验：Agent 执行中想额外操作 → results 携带 requested_operation → Host → Guard
- [x] 审批流程：Guard → outbox 推送审批请求 → 等待 approvals Stream → 批准/拒绝/超时
- [x] 运行时动态修改权限（PATCH API）

### 2.3 Host — 策略生成
- [x] Host 消费 session inbox 消息
- [x] .psc 伪代码格式定义（`AGENT: action → output` + `IF/ELSE` + `RETURN`）
- [x] 规则模板匹配（关键词 → 匹配策略模板）
- [x] Host LLM 动态补充（模板 + 用户输入 + Agent 角色列表 → 完整 .psc）
- [x] 用户确认流程（Host → outbox 推送 .psc 预览 → 用户确认 → 落盘）
- [x] 用户手动编辑 .psc 支持（编辑后 Host 重新加载）

### 2.4 Host — 编译与执行
- [x] .psc 编译器（.psc 文本 → AST 抽象语法树）
- [x] .psc → strategy.json 编译（.psc 变更时自动重编译）
- [x] .psc 执行器（遍历 AST → Guard 校验 → dispatched Stream 分发）
- [x] 结果路由（results Stream → AST 下一步节点 → 分支/循环/跳转）
- [x] 执行完毕 → outbox 回复用户
- [x] Host 错误处理（Agent 超时/失败 → 重试 3 次 → 通知用户选择）
- [x] POST `/api/sessions/{id}/execute` 手动激活执行
- [x] 策略动态调整（用户中途介入 → 修改 .psc → 重新编译执行）

### 2.5 Session Manager
- [x] Session 创建（从 registry 选 Agent → 分配角色 → 初始化 Stream 组 → 落盘 config.json）
- [x] Session 文件夹创建（/data/sessions/{id}/ 目录 + agents/{name}/ 子目录）
- [x] Session 暂停/恢复/关闭（控制 Host 消费者组状态）
- [x] Session 运行中动态新增/移除 Agent（更新消费者组 + config.json）
- [x] Session 运行中修改 Agent 角色/模型（PATCH API）
- [x] Session 基于旧 session 克隆（继承 Agent + 角色 + 权限，不含策略和对话）

### ✅ Phase 2 检验
```bash
# 1. 创建 Session 并发送消息
curl -X POST /api/sessions -d '{"agents":[{"name":"deepseek","role":"程序员"}]}'
curl -X POST /api/sessions/{id}/messages -d '{"content":"写一个排序函数"}'

# 2. Host 生成策略 → 用户确认 → 执行
# 日志输出：Host → .psc 生成 → Guard 校验 → dispatched → Agent 执行 → results → 回复

# 3. 验证文件落盘
ls /data/sessions/{id}/  # config.json strategy.psc session_mem.md agents/*/agent_mem.md
```

---

## Phase 3 — 接口

> **目标**：用户通过 Web UI 完成全部操作  
> **依赖**：Phase 2  
> **产出**：浏览器打开 → 创建 Session → 发消息 → 看 Agent 实时执行 → 审批危险操作

### 3.1 API Server
- [x] FastAPI 入口（CORS / 中间件 / 异常处理）
- [x] 所有 REST 端点实现（见 API 表）
- [x] OpenAPI 文档（`/docs` 自动生成）
- [x] SSE 事件流（`/api/events/stream` → 前端实时推送）
- [x] Per-session SSE 事件流（`/api/sessions/{id}/events/stream` → Chat 页面实时接收 Agent 回复）

### 3.2 Session Logger
- [x] `conversation.log` 写入（时间戳 + 角色 + 内容）
- [x] `messages.jsonl` MQ 消息备份
- [x] `events.jsonl` 系统事件流写入
- [x] Session 回放 API（`GET /api/sessions/{id}/history`）
- [x] Agent/Session 记忆文件读写（Host 和 Agent 各自维护）

### 3.3 下载 Animal Island UI Assets
- [x] 从 GitHub Pages 下载字体文件（Nunito / Noto Sans SC / Zen Maru Gothic）
- [x] 提取 CSS 变量到 `static/css/animal-island.css`
- [x] 下载 favicon

### 3.4 Jinja2 Web UI（4 页面）
- [x] `base.html` 基础布局（导航栏 + Animal Island 主题色 + CSS 变量）
- [x] Dashboard 页面（Session 概览卡片 + Agent 状态 + 实时事件 SSE + 断线重连）
- [x] Session 创建页（Agent 选择器 + 角色分配 + 权限配置 + 动态 Provider 下拉 + Model 选择器 + Session 命名）
- [x] Session 对话页（消息流 + .psc 策略预览 + 审批弹窗 + 执行状态 + 暂停/恢复按钮 + 消息历史 + 时间戳 + 加载动画 + 归档按钮 + Agent 编辑 + 权限管理）

### ✅ Phase 3 检验
```bash
open http://localhost:8000
# Dashboard 看到 Session 卡片
# 创建 Session → 选 Agent → 发消息
# 对话页看到 Agent 逐步执行 + 审批弹窗
# SSE 实时推送执行进度
```

---

## Phase 4 — 运维

> **目标**：安全执行代码、归档会话、存储监控  
> **依赖**：Phase 3  
> **产出**：Agent 写文件不污染宿主机、历史 Session 可打包推到 NAS

### 4.1 Sandbox
- [x] Subprocess + 白名单目录（`/tmp/blackboard-sandbox/{session_id}/`）
- [x] 文件操作路径限制（file_read/file_write 仅沙箱目录）
- [ ] Docker 子容器沙箱（后期升级）

### 4.2 Archive & Remote Storage
- [x] `POST /api/sessions/{id}/archive` → 打包 + 推送远端
- [x] `GET /api/sessions/{id}/archive` → 从远端拉取
- [x] 远端存储适配器基类 + 三种实现（local_nas / s3 / sftp）
- [x] 归档后本地仅保留 config.json + strategy.psc
- [x] 远端写入 `log.md` 记录归档操作

### 4.3 容量预警
- [x] `system.yaml` 配置 `warning_threshold_gb`
- [x] 定时检测 `data/` 目录大小
- [x] 触达阈值 → SSE 推送 `storage_warning` → 前端弹窗询问用户是否归档

### ✅ Phase 4 检验
```bash
# Agent 执行 execute_code → 代码在沙箱运行 → 宿主机无副作用
curl -X POST /api/sessions/{id}/archive -d '{"remote_type":"local_nas","remote_path":"/mnt/nas/"}'
# 阈值超限时 SSE 推送 warning → UI 弹窗
```

---

## Memory 实现（ADR-018 / ADR-019）

> **设计文档**：`architecture.md § Memory 架构`、`decisions.md ADR-018、ADR-019`  
> **依赖**：Phase 3（API + Host 基础架构）

### M1 — 存储层迁移
- [ ] `conversation.log` 迁移为 `dialog.jsonl`（结构化，每条含 turn_id / sender / type / content / ts / tokens）
- [ ] `agents/{name}/memory.md` 迁移为 `agents/{name}/episodic.md`
- [ ] 新增 `config/workspace_ltm.md`（Workspace LTM，启动时自动创建空文件）
- [ ] 新增 `config/agents/{name}/ltm.md`（Agent role LTM，Agent 首次激活时创建）

### M2 — Host：Memory 层级判断
- [ ] 解析用户输入中的作用域信号词（这个/这次/永远/从现在起 等）
- [ ] 判断覆写层级：per-call / per-session / cross-session LTM
- [ ] 检测新输入与 session working memory 的冲突，冲突时主动询问用户

### M3 — Host：Context 组装
- [ ] Session 启动时加载 Workspace LTM + 各 Agent role LTM
- [ ] 每次 Agent 调用前，从 dialog（hot 层）+ working memory 摘要（warm 层）+ LTM 组装 context
- [ ] Budget 计算：`热层 budget = context_window - per_call_max_tokens - soul - ltm - warm - task - safety_margin(200)`；`per_call_max_tokens` 由 Host 按任务类型设定（默认 2048，上限为 `ModelInfo.max_output_tokens`）
- [ ] Dialog 热层管理：按 token budget 从最新 turn 向前填充（非固定 K），每条新 turn 放入前检查空间，不足时逐轮弹出最旧 turn 并更新暖层摘要，循环直到装得下；上限 MAX_HOT_TURNS=50
- [ ] 暖层自身超过 warm budget（约可用输入的 10%）时对 warm summary 再次压缩
- [ ] 每次 LLM 调用后，在该轮 `dialog.jsonl` 条目中写入 context 使用 metadata：`context_window` / `per_call_max_tokens` / `tokens_used` / `context_ratio` / 各层分解（soul / ltm / warm / hot / task）/ `hot_turns` / `warm_compressed`
- [ ] 系统 log：`context_ratio > 0.8` 时 WARNING，`> 0.95` 时 ERROR，注明触发层级

### M4 — Host：LTM 提炼（Session 结束时）
- [ ] Session close 时触发（有序关闭流程）：Host 读取完整 dialog.jsonl + episodic threads
- [ ] 为每个 Participant 提炼 episodic 内容，追加写入对应 `config/agents/{name}/ltm.md`
- [ ] 将 session 级通用信息追加写入 `config/workspace_ltm.md`
- [ ] LTM 提炼成功后方可触发 archive 和本地 dialog.jsonl 删除（门控条件）；提炼失败时 session 保持可恢复状态，本地冷层不删除

### M5 — 用户显式"记住"
- [ ] 识别"记住 / 永远记住 / 以后都"等触发词
- [ ] 根据层级判断写入 session working memory 或对应 LTM 文件

### M6 — 测试
- [ ] dialog.jsonl 读写测试
- [ ] memory 层级判断单元测试（各类信号词 → 正确层级）
- [ ] context 组装集成测试（各层 memory 正确注入）
- [ ] LTM 提炼测试（session 结束后文件内容验证）

---

## Phase 5 — 扩展（后期）

> **依赖**：Phase 3  
> **产出**：TG/Discord 可接入、可视化拖拽编排工作流

### 5.1 IM Bridge
- [ ] `BaseIMBridge` 基类（on_message / send_message / send_approval）
- [ ] Telegram Bot 适配器（Webhook + sendMessage + InlineKeyboard）
- [ ] Discord Bot 适配器
- [ ] outbox 按 `target_channel` 路由回复
- [ ] IM 断线重连 + PEL 恢复

### 5.2 DAG Editor
- [ ] 可视化 DAG 编辑器（节点拖拽 + 连线 + 语义化类型）
- [ ] 节点类型：Agent / Gate（条件）/ Merge（汇聚）/ Input / Output
- [ ] 连线类型：数据流 / 控制流 / 条件边
- [ ] `PscParser`（.psc → DAG 可视化渲染，打开已有策略编辑）
- [ ] `DagSerializer`（DAG → .psc 导出保存）
- [ ] .psc 和 DAG 双向同步（修改任一端，另一端自动更新）

---

## 测试（贯穿所有 Phase）

- [x] MQ Layer 单元测试
- [x] System Config 加载校验测试
- [x] Agent Adapter mock 测试
- [x] Session Guard 权限校验测试
- [x] Host .psc 编译器测试
- [x] Host .psc 执行器测试（mock Agent）
- [x] Session Manager 生命周期测试
- [x] Session Logger 读写回放测试
- [x] API 集成测试（完整 Session 创建→执行→回复流程）
- [x] Sandbox 隔离测试（23 tests）
- [x] Archive 存储测试（18 tests）

---

## 技术债

> 随开发过程中发现的问题记录在此（2026-05-21 全量扫描 103 项；2026-05-22 全量扫描新增 11 项）

### 🔴 Critical — 必须修

- [x] **`add_agent()` 崩溃**：`session/manager.py:147-149` 调用 `_resolve_api_key()` 等方法不存在，运行时会 AttributeError → 已修正为 `_get_api_key()` 等（2026-05-21）
- [x] **路径穿越漏洞**：`tools/executor.py:51-66` → 已修复：使用 `os.path.realpath` + 前缀校验（2026-05-21）
- [x] **SSH 安全风险**：`archive/archiver.py:80` → 已修复：`RejectPolicy` + 系统 host keys + 可配置 host/port/credentials（2026-05-21）
- [x] **注册表查询用 provider 而非实例名**（2026-05-22 全量扫描发现）：`session/manager.py:78,155` 实例名重设计后 `agents.get(provider)` 始终返回 None，Session 创建时凭证/base_url/model 全部缺失 → 改为 `agents.get(agent_name)`，凭证同步改为以实例名查询（ADR-013）（2026-05-22）
- [x] **`time.sleep()` 阻塞事件循环**（2026-05-22 发现）：`chat_completions.py:54,101` 在 async 函数中调用同步 `time.sleep()` → 改为 `await asyncio.sleep()`（2026-05-22）
- [x] **`available_agents` 迭代顺序写反**（2026-05-22 发现）：`host/strategy.py:34` `{r.lower(): name for name, r in agent_roles.items()}` 构建出 `{agent_name: role}` 而非 `{role: agent_name}` → 修正为 `{role.lower(): agent_name for role, agent_name in ...}`；`_build_general_psc` 改为使用实例名而非角色名写入 PSC（2026-05-22）
- [x] **`sandbox` 路径穿越检查缺少 `os.sep`**（2026-05-22 发现）：`sandbox/sandbox.py:16` `startswith(sandbox_root)` 会匹配同前缀目录（如 `/tmp/session1Extra`）→ 改为 `startswith(sandbox_root + os.sep)`（2026-05-22）
- [x] **`get_overall_status()` 提前 return**（2026-05-22 发现）：`credentials.py:143-147` for 循环内 `return` 使第一个非 ready provider 就结束 → 改为遍历全部再按优先级返回最差状态（2026-05-22）
- [x] **`main.py` print 含 HTML 标签**（2026-05-22 发现）：`main.py:60` `"disabled.</p>"` → 移除 `</p>`（2026-05-22）
- [x] **`config_add_agent` default_model 哨兵值**（2026-05-22 发现）：`routes.py:345` `"unknown"` → `""`（2026-05-22）
- [x] **`sync-models` base_url fallback 用实例名**（2026-05-22 发现）：`routes.py:790` `f"https://api.{name}.com/v1"` 其中 `name` 是实例名（如 DS1）→ 改为 `entry.provider`（2026-05-22）

### 🟠 High — 功能缺失 / 数据风险

**编译器/执行器：**
- [ ] **ELSE 分支未实现**：`host/compiler.py:79` 解析 `ELSE:` 但 `pass` 无操作，`host/compiler.py:94-96` 不完整分支静默丢弃（注：当前测试均通过，`→ RETURN` 已处理 ELSE 前的状态切换，无需额外修复）
- [x] **Agent 超时静默返回空字符串**：`host/executor.py:85-87` → 已修复：返回描述性消息（2026-05-21）
- [x] **`run()` 死循环不检查会话状态**：`host/host.py` → 已修复：添加 `_stop_event`/`_paused` 标志 + `pause()`/`resume()`/`stop()` 方法；SessionManager 在 pause/resume/close 时调用对应方法（2026-05-22）
- [x] **`strategy.json` 写入格式错误**：`host/host.py:57` → 已修复：`json.dumps()` 替代 `str(psc)`（2026-05-21）
- [x] **用户误输入覆盖策略**：`host/host.py:91-93` → 已修复：移除误输入覆盖路径，仅接受确认/取消（2026-05-21）
- [x] **`_wait_confirm` 轮询 5 分钟无进度反馈**：`host/host.py:78-94` → 已修复：发送 progress 事件 + 每 10 轮提示（2026-05-21）

**安全/权限：**
- [x] **`check_timeouts()` 从未被调用**：`guard/guard.py:55-65` → 已修复：`check()` 中自动调用（2026-05-21）
- [ ] **OPEN 模式下非声明操作默认允许**：`guard/guard.py:79-84` 缺失操作默认 ALLOWED，比预期更宽松
- [x] **FERNET_KEY 缺失 → 凭证系统静默禁用**：`main.py:53-56` → 已修复：改进 warning 消息 + logger 记录（2026-05-21）

**沙箱/工具：**
- [x] **Model 同步不显示**：`_fetch_from_openrouter` 静默失败 + 前端无错误反馈 + 无 fallback 模型 → 已修复：添加日志 + 自动同步 + fallback 列表（2026-05-21）；**2026-05-22**：静态 fallback 列表（`fallback_models.yaml`）已删除，Add 模式改为实时查 `GET /api/config/providers/{slug}/catalog`（OpenRouter 公开 API）
- [ ] **搜索工具是桩**：`tools/executor.py:99-101` 返回 `"[Search stub] Query ignored..."` 未实现
- [ ] **Sandbox Bridge 缺失**：沙箱内代码（Agent 生成的 Python/Shell）无法回调外部服务（HTTP/搜索/文件），需实现 Module Injection 或 Unix Socket RPC bridge，所有调用经 Guard 权限校验
- [ ] **Agent Worker 缺失**（2026-05-22 全量扫描发现）：`host/executor.py` 向 `dispatched` Stream 分发任务后等待 `results` Stream（60s 超时），但全链路无任何代码从 `dispatched` 消费并调用 `agent.execute()`，所有任务必然超时。需实现 `AgentWorker` 类：消费 `dispatched` → 调用 `agent_registry.get(target_agent).execute(task)` → 发布到 `results`；Session 创建时对每个 Agent 启动 `asyncio.create_task(worker.run())`
- [ ] **executor 用 PSC 角色名查 Agent，registry 存实例名**（2026-05-22 发现）：`host/executor.py:42` `agent_name = node.agent.lower()`，PSC 中记录的是实例名大写（经 strategy.py 修复后），但 `AgentRegistry.get()` 区分大小写。AgentWorker 实现时需统一为小写存储或 case-insensitive 查找

**重复逻辑：**
- [ ] **归档逻辑重复**：`routes.py:278-303` 和 `archiver.py:122-152` 两套归档实现，routes 版本不使用 Archiver 类
- [ ] **Provider 预设数据双源**：`routes.py:645-668` 和 `config.html` 各维护一份 PROVIDER_PRESETS
- [ ] **base_url fallback 对非 OpenAI 类 Provider 无效**：`routes.py` `f"https://api.{entry.provider}.com/v1"` 对 Google/Zhipu/Qwen 产生无效 URL（实例名问题已修复，provider slug 问题仍存在）
- [ ] **`AgentRegistry.get()` 区分大小写**（2026-05-22 发现）：PSC 用 `.upper()` 写入实例名，executor 用 `.lower()` 查询，与 registry 中存储的原始大小写（如 "DS1"）不匹配 → 需统一 registry key 为小写，或 `get()` 不区分大小写
- [ ] **`session/manager.py:63` 权限 fallback 硬编码 "whitelist"**（2026-05-22 发现）：`fallback_preset = presets.presets.get("whitelist")` 无论请求的 mode 是什么都加载 whitelist 预设，应加载与 mode 对应的预设

### 🟡 Medium — UI/UX 缺陷

**错误处理（15+ 空 catch）：**
- [x] **空 catch 静默吞错**（2026-05-21 已修复）：
  - `dashboard.html:112` → console.error
  - `session_chat.html:466` → console.error
  - `session_chat.html:222` → console.error
  - `session_chat.html:549` → console.error
  - `session_chat.html:568` → console.error
  - `archive/archiver.py:102` → logger.warning
  - `main.py:81` → logger.exception
- [x] 剩余空 catch（2026-05-22 修复）：
  - `routes.py` `config_tools()` AttributeError → `logger.warning`；加载失败 → `logger.error`
  - `routes.py` SSE 流异常 → `logger.debug`（两处）
  - `config.html` 设置默认模型错误 → `console.error`
- [ ] **`config_tools()` 失败返回空工具**：`routes.py:453-456` 任何 YAML 错误 → `{"tools": {}}`，无失败指示

**连接/状态管理：**
- [x] **SSE 连接泄漏**：`dashboard.html` + `session_chat.html` → 已修复：close + clearTimer + guard（2026-05-21）
- [x] **`sendMessage()` 错误后思考动画不消失**：`session_chat.html:434` → 已修复：catch 中 hideThinking()（2026-05-21）
- [x] **`executeStrategy()` 硬编码 3s 超时**：`session_chat.html:517-520` → 已修复：基于响应状态更新按钮（2026-05-21）
- [x] **`pauseSession`/`resumeSession` fire-and-forget**：`session_chat.html` → 已修复：检查 HTTP 响应（2026-05-21）
- [x] **`send_message()` 不检查 Session 状态**：`routes.py:168-177` → 已修复：检查 closed（2026-05-21）
- [x] **`execute_session()` 同样不检查状态**：`routes.py:181-187` → 已修复（2026-05-21）
- [x] **SSE handler 假设 `payload.content` 存在**：`session_chat.html` → 已修复：添加 `type === "progress"` 处理（2026-05-21）

**数据解析/渲染：**
- [x] **XSS 风险（innerHTML + 未转义用户数据）**：`dashboard.html:111` → 已修复：escapeHtml()（2026-05-21）
- [x] **Agent 列表 HTML 未转义**：`session_chat.html` → 已修复：新增 `escapeAttr()` 函数并用于 onclick 属性中的 name/role/provider/model（2026-05-22）
- [ ] **`loadHistory()` regex 截断多行消息**：`session_chat.html:398-408` 代码块内容解析错误
- [ ] **`config.html` model sort 假设对象形状**：`config.html:592-594` models 为字符串时 `.model_id` 为 undefined
- [ ] **所有模板 `localStorage` 无 try/catch**：隐私模式下可能崩溃

**硬编码值：**
- [x] **`console.log` 残留**：`session_chat.html:469` → 已移除（2026-05-21）
- [x] **`archiveSession` 硬编码**：`session_chat.html:528-530` → 已修复：prompt 交互选择（2026-05-21）
- [ ] **Dashboard 重定向硬编码**：`session_chat.html:506` `window.location.href="/"`
- [ ] **`data_dir` 硬编码 Linux 路径**：`session/manager.py:19` `/data/sessions`，macOS 不可用
- [ ] **`DATA_DIR` fallback 硬编码**：`main.py:44-45` `/tmp/blackboard-sessions`
- [x] **`PINNED_MODELS` 硬编码**：`config.html` pinnedModelIds / modSort / pin-tag 全部移除，API 不再返回 pinned_model_ids（2026-05-22）

**UI 组件：**
- [x] **下载图标文件缺失**：`static/icons/download.svg` → 已修复：文本 fallback（2026-05-21）
- [x] **`config.html` loadPermissions 显示 undefined**：`config.html:1042-1053` 预设数据包含未知 key 时 badge 显示 undefined → 已修复：动态生成表头（2026-05-21）
- [ ] **`agentRow` 双路径代码脆弱**：`session_create.html:109-131` Provider 有/无 config 两条路径
- [ ] **`populateProviderDropdowns` 硬编码 Fallback**：`session_chat.html:175-177` 如果 API 失败，回退到 `["deepseek","openai"]`
- [x] **`autoSessionId` 结果被丢弃**：`session_create.html` → 已修复：`autoSessionId` 复用 `generateSessionId` 并更新 preview div（2026-05-22）
- [x] **两个 ID 生成函数过滤规则不一致**：`session_create.html` → 已修复：`autoSessionId` 统一调用 `generateSessionId`（2026-05-22）
- [x] **`dashboard.html` evtSource 被覆盖**：第 100 行创建后第 120 行覆盖 → 已修复：移除冗余声明（2026-05-21）
- [ ] **`config.html` 全局 click 监听器冲突**：第 541 行 `document.addEventListener("click")` 关闭下拉，未来多 modal 场景冲突
- [ ] **`config.html` loadTools 图标选择脆弱**：`handler` 按 `"."` 分割，格式变化静默失败

**响应式：**
- [ ] **零响应式设计**：所有 4 个模板无 `@media` 查询，移动端横向滚动/裁剪
- [ ] **`session_chat.html` 固定侧边栏 320px**：第 37 行，小屏幕无折叠
- [ ] **`session_chat.html` body `height: 100vh`**：第 10 行，未考虑移动浏览器地址栏
- [ ] **`dashboard.html` status-card 颜色用语义化类名**：`.teal` 设 `background: #82d5bb` 与 CSS 变量主题不匹配

**样式/维护性：**
- [ ] **CSS 单行压缩**：`static/css/animal-island.css` 第 1 行 2000+ 字符，无 source map
- [ ] **4 个模板大量重复内联 `<style>`**：30-70 行/模板，无共享 CSS 类
- [ ] **`alert()` 替代 Toast**：`session_create.html:179-180` 和 `config.html:960` 与全局 Toast 系统不一致
- [ ] **`statusBadge` 下划线替换未普及**：`config.html:329-332` `InitStatusEnum` 值带下划线时部分位置未替换

### 🟢 Low — 代码质量 / 文档

- [x] **`_host_model` 环境变量读取后从未使用**：`host/strategy.py` → 已修复：移除死代码（2026-05-22）
- [ ] **`get_logger()` 每次创建新 SessionLogger**：`routes.py:96-98` 无缓存
- [ ] **`get_session_mgr()` 无 null 检查**：`routes.py:80-82` 返回 None 导致调用方崩溃
- [ ] **`_enrich_from_openrouter()` 重复 HTTP 调用**：`routes.py:536-562` sync 时调用两次
- [ ] **`_model_type_from_architecture` 仅处理 vision**：`routes.py:464-469` text+audio→text 等模态落入 `"chat"`
- [ ] **`_fetch_from_openrouter()` 网络错误静默返回空**：`routes.py:532`
- [ ] **`getPinnedProviders` localStorage 不可用时静默返回 []**：`config.html:430-436`

### ⏭️ 测试覆盖缺口

- [ ] **Redis 依赖测试全量跳过**：`test_mq_layer.py`、`test_session_manager.py`、`test_mq.py` — 无 Redis 时跳过所有 MQ/Session 测试
- [ ] **UI 测试仅检查 HTTP 200**：`test_ui.py` 无页面内容断言、无表单提交测试
- [ ] **SSE 测试仅检查路由注册**：`test_sse.py` 无实际流式传输测试、无重连测试
- [ ] **`routes.py:80-82` `get_session_mgr()` 无 null 检查**

### 📄 文档

- [x] **10 个 ADR 缺失决策人**：`decisions.md` 全部 ADR 的决策人字段统一改为"项目负责人"（2026-05-22）
- [x] **`background.md` 成功标准未填写**：第 37 行 `[待补充]` → 填入 4 阶段成功标准表格（2026-05-22）

### ✅ 已修复

- [x] Jinja2 TemplateResponse 在 Python 3.14 下缓存 bug → 改用直接渲染（2026-05-20）
- [x] StrategyTemplate 未导入导致模板增改崩溃（2026-05-20）
- [x] agent_registry.yaml 缺失 Claude/OpenAI 条目（2026-05-20）
- [x] 测试 data_dir 硬编码 /data/sessions 在 macOS 只读 → 改用 /tmp 回退（2026-05-19）
- [x] MQ Layer BUSYGROUP 冲突 → 优雅降级（2026-05-19）
