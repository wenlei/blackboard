# Blackboard 开发路线图

> 最后更新：2026-05-22

---

## 总览

| Phase | 名称 | 状态 | 测试 | 依赖 |
|-------|------|------|------|------|
| **1** | 地基 | ✅ 完成 | 29 | — |
| **2** | 核心 | ✅ 完成 | 190 | Phase 1 |
| **3** | 接口 | ✅ 完成 | 53 | Phase 2 |
| **4** | 运维 | ✅ 完成 | 31 | Phase 3 |
| **5** | 扩展 | ⏳ 待开始 | — | Phase 3 |

---

## Phase 1 — 地基 ✅

> **目标**：项目能启动，Redis 可读写，配置可加载  
> **产出**：`docker compose up -d redis`，`pytest` 290 passed

### 1.1 项目骨架
- `pyproject.toml`：Python 3.12+，FastAPI / Redis / httpx / Pydantic v2 / Jinja2
- `Dockerfile`：python:3.12-slim 镜像
- `docker-compose.yml`：Redis:7-alpine + API 容器 + volume 挂载
- `.env.example`：LLM API key 模板
- `.venv`：隔离的虚拟环境
- 源代码目录：`src/blackboard/{api,mq,host,guard,agents,session,im_bridge,logger,config,tools}`

### 1.2 System Config
- 4 个 YAML 配置文件：`system.yaml` / `agents/registry.yaml` / `strategy_templates/templates.yaml` / `permissions/presets.yaml`
- `ConfigLoader`：YAML → Pydantic 模型，启动时校验
- `config/models.py`：枚举（PermissionMode / OperationType / SessionStatus） + 7 种错误类型

### 1.3 MQ Layer
- `MQLayer` 封装：connect / publish / consume / ack / pending / init_session_streams / destroy_session_streams
- Session 级 Stream 隔离：`session:{id}:inbox/outbox/dispatched/results/approvals/events`
- PEL 故障恢复：`pending()` 拾取未 ACK 消息
- target_channel 字段支持 outbox 多渠道路由

### 1.4 消息模型
- `Task` / `TaskResult` / `ApprovalRequest` / `ApprovalResponse` / `StreamMessage`
- 7 种错误类型：AgentRegistryError / MissingApiKeyError / InvalidApiKeyError / SandboxExecutionError / StorageQuotaError / ArchiveFailedError / ApprovalTimeoutError

### 1.5 Tool Registry
- 7 个内置工具：文件读写 / Python 执行 / Shell 执行 / HTTP GET/POST / 网络搜索
- `ToolRegistry`（注册表） + `ToolExecutor`（执行器，4 类 handler：filesystem / sandbox / network / search）
- 工具与 Guard OperationType 映射

### 关键文件
```
config/              # 5 个 YAML 配置文件
src/blackboard/
  main.py            # FastAPI 入口 + lifespan（config 加载 + MQ 连接 + 工具加载）
  models.py          # 消息模型
  config/            # System Config 加载器 + 枚举/错误类型
  mq/                # Redis Streams MQ Layer
  tools/             # Tool Registry + Executor
tests/               # pytest（29 unit tests）
dev/test-sample/phase1/  # Phase 1 测试计划（32 用例）
```

---

## Phase 2 — 核心 ✅

> **目标**：能创建 Session，Host 生成 .psc 并执行完整的多 Agent 任务  
> **产出**：56 unit tests + 163 integration tests = 219 passed

### 2.1 Agent Adapters
- **BaseAgent**：抽象基类（execute / load_memory / save_memory / health_check）
- **ChatCompletionsAdapter**：统一 OpenAI 兼容适配器（base_url + api_key，429 退避重试、60s 超时、token_usage 统计）；替代早期 DeepSeek/Claude/OpenAI 各自独立适配器
- **AgentRegistry**：运行时注册表（create / get / list / remove / list_by_provider）

### 2.2 Session Guard
- 三种权限模式：**whitelist**（白名单）/ **approval_first**（默认审批）/ **open**（全开放）
- 8 种操作类型：chat / analyze / search / execute_code / http_request / file_read / file_write / file_delete
- 分发前校验 + 执行中回调校验（中间态拦截）
- 审批流程：push outbox → 等待 approvals Stream → 批准/拒绝/超时
- Agent 级别权限覆写（per_agent_overrides）
- 运行时动态修改权限和模式

### 2.3 Host
- **StrategyGenerator**：4 套规则模板匹配（代码审查 / 协作编码 / 分析讨论 / 通用问答） + LLM 动态补充
- **.psc 编译器**：伪代码 → AST（Agent 节点 / Branch 节点 / Return 节点），支持 IF/ELSE/RETURN
- **.psc 执行器**：遍历 AST → Guard 校验 → dispatched Stream 分发 → results Stream 收结果 → 分支跳转
- **Host 主循环**：consume inbox → 生成 .psc → 用户确认 → 编译执行 → outbox 回复
- 策略动态调整（用户中途介入 → 编辑 .psc → 重新编译执行）
- Host 错误处理（Agent 超时/失败 → 重试/切换/跳过）

### 2.4 Session Manager
- Session 生命周期：create（初始化 Stream 组 + 落盘 config.json）→ pause → resume → close
- 动态增减 Agent（add_agent / remove_agent）
- config.json 含 Agent 列表 + 角色 + 权限配置
- per-session Host 实例（互不阻塞）
- Session 文件夹：`/data/sessions/{id}/config.json`

### 关键文件
```
src/blackboard/
  agents/            # BaseAgent + DeepSeek/Claude/OpenAI + Registry
  guard/             # SessionGuard（权限模式 + 审批）
  host/
    host.py          # Host 主循环
    compiler.py      # .psc → AST 编译器
    executor.py      # AST → MQ 分发执行器
    strategy.py      # 策略生成器（模板匹配）
  session/           # SessionManager
tests/
  test_agents.py     # 7 tests
  test_guard.py      # 11 tests
  test_host.py       # 9 tests
  test_mq.py         # 7 tests
  phase2/            # 8 integration tests
dev/test-sample/phase2/  # Phase 2 测试计划（28 用例）
```

---

## Phase 3 — 接口 ✅

> **目标**：用户通过 Web UI 完成全部操作  
> **产出**：浏览器打开 → 创建 Session → 发消息 → 看 Agent 实时执行 → 审批危险操作

### 3.1 API Server
- FastAPI 入口（CORS / 中间件 / 异常处理）
- 20+ REST 端点实现
- OpenAPI 文档（`/docs` 自动生成）
- SSE 事件流（`/api/events/stream`）
- Per-session SSE 事件流（`/api/sessions/{id}/events/stream`）— Chat 页面实时接收 Agent 回复

### 3.2 Session Logger
- `conversation.log` / `messages.jsonl` / `events.jsonl` 写入
- Session 回放 API（`GET /api/sessions/{id}/history`）
- Agent/Session 记忆文件读写

### 3.3 下载 Animal Island UI Assets
- 字体文件（Nunito / Noto Sans SC / Zen Maru Gothic ~30 个）
- CSS 变量提取（`static/css/animal-island.css`）
- favicon

### 3.4 Jinja2 Web UI（4 页面）
- `dashboard.html`：Session 概览卡片（含名称/创建时间） + Agent 状态 + SSE 实时事件（断线重连）
- `session_create.html`：动态 Provider 下拉 + Model 选择器 + 角色分配 + 权限配置 + Session 命名
- `session_chat.html`：消息流（含历史加载/时间戳/加载动画）+ .psc 策略预览 + 审批弹窗 + 执行状态 + 暂停/恢复/归档 + Agent 编辑（角色/Provider/Model） + 权限管理 + Toast 通知
- `config.html`：Agent 注册管理 + baseURL 快捷填充（OpenAI/Anthropic/DeepSeek）+ 策略模板管理 + 权限预设查看

### API 端点
```
POST   /api/sessions              GET    /api/sessions/{id}
POST   /api/sessions/{id}/pause   POST   /api/sessions/{id}/resume
DELETE /api/sessions/{id}         POST   /api/sessions/{id}/messages
POST   /api/sessions/{id}/execute GET    /api/sessions/{id}/history
GET    /api/sessions/{id}/strategy
POST   /api/sessions/{id}/agents  DELETE /api/sessions/{id}/agents/{id}
PATCH  /api/sessions/{id}/agents/{id}
PATCH  /api/sessions/{id}/permissions
POST   /api/sessions/{id}/archive GET    /api/sessions/{id}/archive
GET    /api/events/stream         GET    /api/sessions/{id}/events/stream
GET    /api/config/agents         POST   /api/config/agents
DELETE /api/config/agents/{name}  PATCH  /api/config/agents/{name}
POST   /api/config/agents/{name}/set-key
POST   /api/config/agents/{name}/test
POST   /api/config/agents/{name}/sync-models
POST   /api/config/agents/{name}/default-model
GET    /api/config/providers      GET    /api/config/providers/{slug}/catalog
POST   /api/config/test-connection
GET    /api/config/credentials    DELETE /api/config/credentials/{id}
GET    /api/config/status
GET    /api/config/templates      POST   /api/config/templates
PATCH  /api/config/templates/{id} DELETE /api/config/templates/{id}
GET    /api/config/permissions/presets
GET    /api/config/tools
```

---

## Phase 4 — 运维 ✅

> **目标**：安全执行代码、归档会话、存储监控  
> **产出**：Agent 写文件不污染宿主机、历史 Session 可打包推到 NAS

### 4.1 Sandbox
- Subprocess + 白名单目录（`/tmp/blackboard-sandbox/{session_id}/`）
- 文件操作路径限制
- 路径遍历防护（resolve_path 规范化 + 绝对路径检测）
- 23 tests（文件读写/目录列表/删除/清理/Python 执行/Shell 执行/大文件/错误码/路径穿越）
- Docker 子容器沙箱（后期升级）

### 4.2 Archive & Remote Storage
- `POST /api/sessions/{id}/archive` → 打包 + 推送远端
- `GET /api/sessions/{id}/archive` → 从远端拉取
- 远端存储适配器基类 + 3 种实现（local_nas / s3 / sftp）
- 归档后本地仅保留 config.json + strategy.psc
- 远端写入 log.md
- 18 tests（NAS 存储/下载/S3 路径解析/disk usage/清理验证/多级目录）

### 4.3 容量预警
- `system.yaml` 配置 `warning_threshold_gb`
- 定时检测 `data/` 目录大小
- 触达阈值 → SSE 推送 → 前端弹窗

---

## Phase 5 — 扩展 ⏳

> **产出**：TG/Discord 可接入、可视化拖拽编排工作流

### 5.1 IM Bridge
- `BaseIMBridge` 基类（on_message / send_message / send_approval）
- Telegram Bot 适配器（Webhook + InlineKeyboard）
- Discord Bot 适配器
- outbox 按 `target_channel` 路由
- IM 断线重连 + PEL 恢复

### 5.2 DAG Editor（后期）
- 可视化 DAG 编辑器（节点拖拽 + 连线 + 语义化类型）
- 节点类型：Agent / Gate（条件）/ Merge（汇聚）/ Input / Output
- 连线类型：数据流 / 控制流 / 条件边
- `PscParser`（.psc → DAG 可视化渲染）
- `DagSerializer`（DAG → .psc 导出）
- .psc ↔ DAG 双向同步

---

## 测试总汇

| Phase | Unit Tests | Integration Tests | Total |
|-------|-----------|-------------------|-------|
| 1 | 29 | — | 29 |
| 2 | 27 | 163 | 190 |
| 3 | 13 | 40 | 53 |
| 4 | 31 | — | 31 |
| Config UI | — | — | 10+ |
| 5 | — | — | — |
| **累计** | — | — | **313**（11 skipped 需 Redis） |

---

## 快速启动

```bash
# 启动 Redis
docker compose up -d redis

# 安装依赖
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 运行测试
WITH_REDIS=1 python3 -m pytest tests/ -q

# 启动 API（开发模式）
fastapi dev src/blackboard/main.py
```
