# Phase 1 Test Samples

> 覆盖 Phase 1 全部模块：System Config / MQ Layer / Message Models / Error Types / Tool Registry

---

## 1. System Config — 配置加载与校验

### 1.1 加载 system.yaml
| 字段 | 值 |
|------|-----|
| **操作** | `config_loader.load_system()` |
| **预期** | 返回 `SystemConfig` 对象，字段值与 `config/system.yaml` 一致 |

### 1.2 加载 agent registry
| 字段 | 值 |
|------|-----|
| **操作** | `config_loader.load_agent_registry()` |
| **预期** | 返回 `AgentRegistry`，含 deepseek/claude/openai 三个 agent，各含 api_key_env / base_url / models |

### 1.3 加载 strategy templates
| 字段 | 值 |
|------|-----|
| **操作** | `config_loader.load_strategy_templates()` |
| **预期** | 返回 `StrategyTemplates`，含 4 套模板（code_review / write_code / analyze / general） |

### 1.4 加载 permission presets
| 字段 | 值 |
|------|-----|
| **操作** | `config_loader.load_permission_presets()` |
| **预期** | 返回 `PermissionPresets`，含 3 套预设（whitelist / approval_first / open） |

### 1.5 非法 YAML 拒绝启动
| 字段 | 值 |
|------|-----|
| **输入** | `system.yaml` 缺少必填字段 `redis.url` |
| **操作** | `config_loader.load_system()` |
| **预期** | 抛出 `ValidationError`（Pydantic 校验不通过），启动失败 |

### 1.6 配置热加载
| 字段 | 值 |
|------|-----|
| **输入** | 运行时修改 `system.yaml` 中的 `approval_timeout_seconds` |
| **操作** | watchfiles 检测文件变更 → 重新 `load_system()` |
| **预期** | 新值即时生效，不影响已创建的 Session |

### 1.7 Agent registry 注册表操作
| 字段 | 值 |
|------|-----|
| **输入** | 运行时新增 agent `mistral` 到 registry.yaml |
| **操作** | 热加载或 API `POST /api/config/agents` |
| **预期** | 新 agent 可被 Session 引用创建实例 |

---

## 2. MQ Layer — Redis Streams 封装

### 2.1 连接与健康检查
| 字段 | 值 |
|------|-----|
| **操作** | `mq.connect()` → `mq.health_check()` |
| **预期** | 返回 True，Redis PING 成功 |

### 2.2 创建 Session Stream 组
| 字段 | 值 |
|------|-----|
| **操作** | `mq.init_session_streams("test-001")` |
| **预期** | 6 个 Stream Key 全部创建（inbox/outbox/dispatched/results/approvals/events），含消费者组 |

### 2.3 消息发布
| 字段 | 值 |
|------|-----|
| **操作** | `mq.publish("test-001", "inbox", {"type":"chat","content":"hello"})` |
| **预期** | 返回 message_id，格式 `{timestamp}-{sequence}` |

### 2.4 消息消费
| 字段 | 值 |
|------|-----|
| **操作** | `mq.consume("test-001", "inbox", "inbox", "host-1", count=1, block_ms=5000)` |
| **预期** | 返回 1 条消息，data 内容与发布一致 |

### 2.5 消息 ACK
| 字段 | 值 |
|------|-----|
| **操作** | 对已消费消息调用 `mq.ack("test-001", "inbox", "inbox", [msg_id])` |
| **预期** | XACK 成功，PEL 中该消息被移除 |

### 2.6 PEL 故障恢复
| 字段 | 值 |
|------|-----|
| **操作** | 消费 2 条消息但不 ACK → 调用 `mq.pending("test-001", "inbox", "inbox")` |
| **预期** | 返回 2 条 PEL 条目，含 consumer name 和 idle_ms |

### 2.7 Session Stream 销毁
| 字段 | 值 |
|------|-----|
| **操作** | `mq.destroy_session_streams("test-001")` |
| **预期** | 6 个 Stream Key 全部删除，`KEYS session:test-001:*` 返回空 |

### 2.8 多 Session 隔离
| 字段 | 值 |
|------|-----|
| **操作** | 同时创建 session-001 和 session-002 → 分别 publish → 分别 consume |
| **预期** | 两个 session 的 Stream 互不干扰，各自独立消费进度 |

### 2.9 消费者组争用
| 字段 | 值 |
|------|-----|
| **操作** | 2 个消费者（host-1, host-2）同时 consume 同一个 inbox 组 |
| **预期** | 同一条消息只被 1 个消费者拿到，另一个返回空 |

### 2.10 断连重连
| 字段 | 值 |
|------|-----|
| **操作** | 模拟 Redis 断连 → `mq.connect()` 重新连接 |
| **预期** | 重连后续操作正常，不丢消息 |

---

## 3. Message Models — Pydantic 序列化/校验

### 3.1 Task 模型创建与序列化
| 字段 | 值 |
|------|-----|
| **操作** | `Task(session_id="s1", target_agent="deepseek", role="程序员", prompt="写代码")` |
| **预期** | 自动生成 id+created_at，`.model_dump_json()` 正常序列化 |

### 3.2 TaskResult 包含 token_usage
| 字段 | 值 |
|------|-----|
| **操作** | `TaskResult(task_id="t1", session_id="s1", agent_name="deepseek", content="...", success=True, token_usage={"input":100,"output":50})` |
| **预期** | 序列化后 token_usage 字段完整 |

### 3.3 ApprovalRequest 与 ApprovalResponse 配对
| 字段 | 值 |
|------|-----|
| **操作** | 创建 ApprovalRequest(id="a1") → 创建 ApprovalResponse(approval_id="a1", decision="approved") |
| **预期** | approval_id 对应一致 |

### 3.4 StreamMessage 含 target_channel
| 字段 | 值 |
|------|-----|
| **操作** | `StreamMessage(stream="outbox", session_id="s1", payload={...}, target_channel="telegram")` |
| **预期** | target_channel 字段被正确序列化，outbox 消费者据此路由 |

---

## 4. Error Types — 异常定义与 HTTP 状态码

### 4.1 AgentRegistryError
| 字段 | 值 |
|------|-----|
| **操作** | `raise AgentRegistryError("unknown-agent")` |
| **预期** | status_code=404, message="Agent not found in registry" |

### 4.2 MissingApiKeyError
| 字段 | 值 |
|------|-----|
| **操作** | `raise MissingApiKeyError("DEEPSEEK_API_KEY")` |
| **预期** | status_code=500 |

### 4.3 InvalidApiKeyError
| 字段 | 值 |
|------|-----|
| **操作** | LLM API 返回 401 → `raise InvalidApiKeyError()` |
| **预期** | status_code=502 |

### 4.4 SandboxExecutionError
| 字段 | 值 |
|------|-----|
| **操作** | 沙箱执行失败 → `raise SandboxExecutionError("syntax error")` |
| **预期** | status_code=500 |

### 4.5 StorageQuotaError
| 字段 | 值 |
|------|-----|
| **操作** | 磁盘超过 `warning_threshold_gb` → `raise StorageQuotaError()` |
| **预期** | status_code=507 |

### 4.6 ArchiveFailedError
| 字段 | 值 |
|------|-----|
| **操作** | NAS 挂载断开 → `raise ArchiveFailedError("NAS unreachable")` |
| **预期** | status_code=500 |

### 4.7 ApprovalTimeoutError
| 字段 | 值 |
|------|-----|
| **操作** | 审批 300s 无响应 → `raise ApprovalTimeoutError()` |
| **预期** | status_code=408 |

---

## 5. Tool Registry — 工具注册表与执行器

### 5.1 加载工具注册表
| 字段 | 值 |
|------|-----|
| **操作** | `load_tool_registry("config")` |
| **预期** | 返回 `ToolRegistry`，含 7 个工具（read_file/write_file/execute_python/execute_shell/http_get/http_post/web_search） |

### 5.2 按操作类型筛选工具
| 字段 | 值 |
|------|-----|
| **操作** | `registry.list_by_operation("execute_code")` |
| **预期** | 返回 [execute_python, execute_shell] |

### 5.3 工具执行 — 文件读取
| 字段 | 值 |
|------|-----|
| **操作** | `executor.execute(ToolCall(tool_name="read_file", parameters={"path":"test.txt"}))` |
| **预期** | 返回 ToolResult(success=True, result=文件内容) |

### 5.4 工具执行 — 文件写入
| 字段 | 值 |
|------|-----|
| **操作** | `executor.execute(ToolCall(tool_name="write_file", parameters={"path":"out.txt","content":"hello"}))` |
| **预期** | 沙箱目录下创建文件，返回 ToolResult(success=True) |

### 5.5 工具执行 — Python 代码
| 字段 | 值 |
|------|-----|
| **操作** | `executor.execute(ToolCall(tool_name="execute_python", parameters={"code":"print(1+1)"}))` |
| **预期** | 返回 ToolResult(success=True, result="2\n") |

### 5.6 工具执行 — HTTP 请求
| 字段 | 值 |
|------|-----|
| **操作** | `executor.execute(ToolCall(tool_name="http_get", parameters={"url":"https://httpbin.org/get"}))` |
| **预期** | 返回 ToolResult(success=True, result=JSON 响应) |

### 5.7 未知工具
| 字段 | 值 |
|------|-----|
| **操作** | `executor.execute(ToolCall(tool_name="non_existent", params={}))` |
| **预期** | 返回 ToolResult(success=False, error="Unknown tool: non_existent") |

### 5.8 工具 → Guard 权限映射
| 字段 | 值 |
|------|-----|
| **操作** | 对每个已加载 tool 检查 `operation_type` 字段 |
| **预期** | 所有 tool 的 `operation_type` 都在 Guard 的 OperationType 枚举中有对应值 |
