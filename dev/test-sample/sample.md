# 测试用例总览

> 98 个架构级测试用例覆盖 Blackboard 全部 12 个核心模块（+32 个 Phase 1 单元测试用例见 `phase1/test_phase1.md`）。

---

## 覆盖模块一览

| # | 模块 | 用例数 | 测试文件 |
|---|------|--------|----------|
| 1 | **Session Manager** — 会话生命周期管理 | 8 | `test_session_lifecycle.md` |
| 2 | **Host** — 策略生成与任务调度 | 8 | `test_host_strategy.md` |
| 3 | **Session Guard** — 权限守卫与审批流程 | 10 | `test_session_guard.md` |
| 4 | **MQ Layer** — Redis Streams 消息队列 | 8 | `test_mq_layer.md` |
| 5 | **Agent Adapters** — LLM 适配器 | 8 | `test_agent_adapter.md` |
| 6 | **IM Bridge** — 外部消息渠道适配 | 6 | `test_im_bridge.md` |
| 7 | **Dynamic Agent** — 运行时 Agent 动态调整 | 4 | `test_dynamic_agent.md` |
| 8 | **Session Replay** — 会话回放与克隆 | 4 | `test_conversation_replay.md` |
| 9 | **System Config** — 全局配置管理 | — | 见架构文档 `config/` 结构 |
| 10 | **Tool Registry** — 工具/技能注册表（7 个内置工具） | — | 见 `test_phase1.md` § 5 |
| 11 | **Sandbox** — 隔离执行环境（文件操作 + Python/Shell 子进程） | 24 | `phase4/test_phase4.md` § 1 |
| 12 | **Archive & Remote Storage** — 归档与远端存储（tar.gz + 3 种后端） | 22 | `phase4/test_phase4.md` § 2-4 |

---

## 各模块覆盖的功能详述

### 1. Session Manager — 会话生命周期

| 功能 | 用例 |
|------|------|
| 会话创建（配置 Agent 列表/角色/权限/API） | 1.1 |
| Host 自动启动并等待消息 | 1.2 |
| 用户发送首条消息触发策略生成 | 1.3 |
| 会话暂停（停止消费新消息，完成进行中任务） | 1.4 |
| 会话恢复（重新消费 inbox，拾取 PEL 未处理消息） | 1.5 |
| 会话销毁（关闭消费者组，保留文件，标记 closed） | 1.6 |
| 重复创建冲突检测（409 Conflict） | 1.7 |
| 文件落盘完整性校验（5 个文件均非空） | 1.8 |

### 2. Host — 策略生成与任务调度

| 功能 | 用例 |
|------|------|
| 规则模板匹配 + LLM 动态补充生成多步骤策略 | 2.1 |
| 按策略顺序分发到指定 Agent | 2.2 |
| 接收 Agent 结果后路由到下一步 | 2.3 |
| 多轮协作完整链路（架构师→程序员→审查者→回复） | 2.4 |
| 策略未覆盖的意外情况 → Host LLM 动态判断 | 2.5 |
| 用户中途介入（修改需求→调整策略+通知 Agent） | 2.6 |
| Agent 错误重试机制（最多 3 次→通知用户选择） | 2.7 |
| 会话结束后策略完整保留可查看 | 2.8 |

### 3. Session Guard — 权限守卫与审批

| 功能 | 用例 |
|------|------|
| whitelist 模式 — allowed 操作自动放行 | 3.1 |
| whitelist 模式 — 未声明操作自动 denied | 3.2 |
| require_approval — 推送审批请求到 outbox | 3.3 |
| 用户批准 — approvals Stream → Guard 放行 | 3.4 |
| 用户拒绝 — Guard 拒绝 + 日志记录 | 3.5 |
| 审批超时（5 分钟）自动拒绝 | 3.6 |
| approval_first 模式 — 所有操作默认需审批 | 3.7 |
| open 模式 — 仅 denied 列表拦截，其余自动放行 | 3.8 |
| 运行时动态修改权限（PATCH API 即时生效） | 3.9 |
| 按 Agent 身份分别校验（扩展功能） | 3.10 |

### 4. MQ Layer — Redis Streams 消息队列

| 功能 | 用例 |
|------|------|
| Session 初始化创建 6 个 Stream + 消费者组 | 4.1 |
| 消息生产（XADD） | 4.2 |
| 消息消费（XREADGROUP + BLOCK） | 4.3 |
| 消息确认（XACK） | 4.4 |
| 消费者组内竞争（同组消费者互斥消费） | 4.5 |
| 故障恢复（PEL 重分配未 ACK 消息） | 4.6 |
| Session 销毁时 Stream 全部清理 | 4.7 |
| 多 Session 隔离（不同 session 的 Stream 互不干扰） | 4.8 |

### 5. Agent Adapters — LLM 适配器

| 功能 | 用例 |
|------|------|
| Agent 注册（创建消费者组 + 健康检查） | 5.1 |
| Agent 执行（消费 dispatched → 调用 LLM → 写 results） | 5.2 |
| 多 Agent 并行执行（独立消费、不阻塞） | 5.3 |
| 429 限流退避重试（1s→2s→4s，最多 3 次） | 5.4 |
| API 超时处理（60s 无响应 → error） | 5.5 |
| Agent 暂停（完成当前任务 + 停止消费） | 5.6 |
| 运行时新增 Agent（注册+消费者组+config 更新） | 5.7 |
| 运行时移除 Agent（完成当前任务+清理+config 更新） | 5.8 |

### 6. IM Bridge — 外部消息渠道适配

| 功能 | 用例 |
|------|------|
| Telegram 消息 → session inbox 写入 | 6.1 |
| Host outbox 回复 → Telegram Bot API 回传 | 6.2 |
| 审批请求 → Telegram InlineKeyboard 按钮 | 6.3 |
| 用户点击 TG 按钮 → approvals Stream 写入 | 6.4 |
| 多渠道同时接入（消息按时间排序） | 6.5 |
| IM 断线重连 + PEL 恢复（不丢消息） | 6.6 |

### 7. Dynamic Agent — 运行时 Agent 动态调整

| 功能 | 用例 |
|------|------|
| 运行时新增 Agent（注册 + config 更新 + Host 策略刷新） | 7.1 |
| 运行时移除 Agent（清理消费者组 + config + 策略更新） | 7.2 |
| 运行时修改 Agent 角色（prompt 即时生效） | 7.3 |
| 运行时切换 Agent API 模型（model 参数即时生效） | 7.4 |

### 8. Session Replay — 会话回放

| 功能 | 用例 |
|------|------|
| 完整对话时间线回放（时间戳+角色+内容+操作类型） | 8.1 |
| 策略执行路径查看（步骤→Agent→结果→跳转关系） | 8.2 |
| MQ 消息顺序重放（从 messages.jsonl 按时间遍历） | 8.3 |
| 基于旧 Session 克隆新建（继承配置，不含策略和对话） | 8.4 |

### 9. Sandbox — 隔离执行环境

| 功能 | 用例 |
|------|------|
| 沙箱目录初始化（`/tmp/blackboard-sandbox/{session_id}/`） | 9.1 |
| 文件写入与读取（write_file / read_file） | 9.2 |
| 嵌套目录文件操作（自动创建父目录） | 9.3 |
| 路径穿越防护（`../` + 绝对路径 + 符号链接绕过） | 9.4-9.6 |
| 不存在的文件读取（FileNotFoundError） | 9.7 |
| 文件删除（含不存在的文件无异常） | 9.8-9.9 |
| 目录列表（根目录 + 子目录 + 不存在目录） | 9.10-9.12 |
| Python 代码执行（正常/错误/多行/超时/工作目录隔离） | 9.13-9.16, 9.20 |
| Shell 命令执行（正常/错误/管道重定向） | 9.17-9.19 |
| 沙箱清理（cleanup + 多次清理不报错） | 9.21-9.22 |
| 文件覆盖写入 + 大文件读写 | 9.23-9.24 |

### 10. Archive & Remote Storage — 归档与远端存储

| 功能 | 用例 |
|------|------|
| LocalNasStorage 上传/下载/日志写入 | 10.1-10.5 |
| STORAGE_BACKENDS 映射表（local_nas/s3/sftp） | 10.6 |
| S3Storage 路径解析（含 bucket 和子路径） | 10.7-10.8 |
| S3Storage 懒加载客户端 | 10.9 |
| SftpStorage _wrap_stringio 工具方法 | 10.10 |
| 未知远端类型回退到 LocalNas | 10.11 |
| 归档完整流程（tar.gz 打包 + 上传 + 本地清理） | 10.12-10.14 |
| 归档不存在的 Session（FileNotFoundError） | 10.15 |
| tar.gz 文件有效性校验 | 10.16 |
| 归档远端日志写入（log.md 含时间戳+session_id） | 10.17 |
| 归档返回值校验 | 10.18 |
| 临时目录清理 | 10.19 |
| 空会话目录归档 + 重复归档 | 10.20-10.21 |

### 11. Capacity Warning — 容量预警

| 功能 | 用例 |
|------|------|
| check_disk_usage（有文件/空目录/目录不存在） | 11.1-11.3 |
| `/health` 端点集成（超阈值 degraded + 正常 ok） | 11.4-11.5 |

---

## 用例覆盖的边界场景

| 场景类型 | 覆盖的用例 |
|----------|-----------|
| **正常流程** | 1.1-1.3, 2.1-2.4, 3.1, 4.1-4.4, 5.1-5.3, 6.1-6.2, 7.1, 8.1-8.2, 9.1-9.3, 9.10, 9.13, 9.17, 10.1-10.3, 10.12 |
| **故障恢复** | 1.6, 2.7, 4.6, 5.4-5.5, 6.6, 9.14, 9.16, 10.15 |
| **用户介入** | 2.6, 3.3-3.6 |
| **动态变更** | 1.4-1.5, 3.9-3.10, 5.6-5.8, 7.1-7.4 |
| **并发与隔离** | 4.5, 4.8, 5.3, 6.5, 9.20 |
| **数据持久化** | 1.7-1.8, 2.8, 8.3-8.4, 10.5, 10.14, 10.17 |
| **安全与权限** | 3.1-3.10, 9.4-9.6 |
| **沙箱执行** | `phase4/test_phase4.md` § 1 — subprocess + 白名单目录隔离（24 用例） |
| **归档与存储** | `phase4/test_phase4.md` § 2-3 — tar.gz + 3 种后端 + 本地清理（21 用例） |
| **容量管理** | `phase4/test_phase4.md` § 4 — check_disk_usage + `/health` 端点集成（5 用例） |
| **跨平台接入** | 6.1-6.6 |

---

## Fixtures 测试数据

| 文件 | 用途 |
|------|------|
| `fixtures/session_config.json` | 完整 session 配置（3 个 Agent + 角色 + 权限） |
| `fixtures/strategy_template.json` | 4 套规则模板（代码审查/协作编码/分析讨论/通用问答） |
| `fixtures/permissions_config.json` | 3 种权限模式配置 + 默认值 + Agent 级别覆盖示例 |

---

## Session 文件与记忆结构

```
/data/sessions/{id}/
├── config.json           # Agent 列表 + 角色 + API 配置 + 权限设置
├── strategy.psc          # 策略伪代码（**单一真相源**）
├── strategy.json         # 由 .psc 编译得来（只读，仅供机器执行）
├── session_mem.md        # Host 全局记忆（当前步骤、上下文、各 Agent 状态）
├── conversation.log      # 全文聊天日志
├── messages.jsonl        # MQ 消息备份（可回放）
├── events.jsonl          # 系统事件流
└── agents/
    └── {agent_name}/
        └── agent_mem.md  # 该 Agent 的历史任务、上下文、结果记忆（仅自己可见）
```

| 文件 | 维护者 | 性质 |
|------|--------|------|
| `session_mem.md` | Host | 是 Agent 角色（有 LLM），决策/调度时参考 |
| `agent_mem.md` | 各 Agent Adapter | 是 Agent 角色（有 LLM），执行时参考自己的历史 |
| `config.json` | Session Manager | 基础设施（无 LLM），纯配置读写 |
| `strategy.psc` | Host / DAG 编辑器 / 用户 | 伪代码格式（**单一真相源**，来源：Host LLM 生成 / DAG 拖拽导出 / 用户手动编辑） |
| `strategy.json` | Host（编译产物） | 由 .psc 自动编译得来（只读，仅供机器执行） |
| `conversation.log` | Session Logger | 基础设施（无 LLM），纯 I/O 写盘 |
| `messages.jsonl` | Session Logger | 基础设施（无 LLM），纯消息备份 |
| `events.jsonl` | Session Logger | 基础设施（无 LLM），纯事件记录 |
